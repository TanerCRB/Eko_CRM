"""EKO-2-02 K-05 (ADR-0003-C7 application half, *Bound*, *Account lifecycle*): sessions already
issued lose their rights within 300 seconds of a deactivation or a role removal, the rows naming
the account stay, and after re-enabling (and restoring the role) a new login reaches the same
records.

Against the running Keycloak configured by EKO-1-12 with its own token lifespan, and the shipped
`create_app()` built in this process with EKO-2-02's probe (`eko202_live`). One window, four
accounts with live sessions, changed at the same moment t0 and polled together:

- (a) disable: a `rep` account is disabled; its session must answer 401;
- (b) role removal: a `rep`+`manager` account loses `manager`; the manager operation must answer
  403 while the `rep` operation keeps answering 200;
- last role: a `manager`-only account loses `manager`; it must answer 403 (no roles), never 401;
- control: a `rep`+`manager` account nothing happens to keeps every answer 200 past 300 s.

Elapsed time is measured on the test host's monotonic clock from just before the first
administrator change is sent, and recorded per run as test properties; backend and Keycloak
share that host's clock (ADR-0004 *Clocks*).
"""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest

from tests.runtime import eko202_live as live
from tests.runtime.conftest import Started
from tests.support import eko202_probe as probe
from tests.support.pg_instance import Postgres, postgres

pytestmark = pytest.mark.runtime

BOUND_SECONDS = 300.0
# The control is polled one second past the bound and a little more (K-05 edge).
WINDOW_SECONDS = BOUND_SECONDS + 10.0
POLL_SECONDS = 2.0
SESSION = ("GET", "/api/auth/session")
CUSTOMERS = ("GET", probe.CUSTOMERS)
TEAM = ("GET", probe.TEAM)
RecordProperty = Callable[[str, object], None]


@dataclass
class Account:
    username: str
    password: str
    user_id: str
    session: str = ""
    # (elapsed seconds since t0, operation, status) for every poll answer.
    seen: list[tuple[float, tuple[str, str], int]] = field(default_factory=list)

    def first(self, operation: tuple[str, str], status: int) -> float | None:
        return next((t for t, op, s in self.seen if op == operation and s == status), None)

    def statuses(self, operation: tuple[str, str]) -> set[int]:
        return {s for _, op, s in self.seen if op == operation}


@dataclass
class Window:
    app: live.LiveApp
    realm: live.Realm
    accounts: dict[str, Account]
    planted: list[tuple[int, str, str]]
    after_window: list[tuple[int, str, str]]
    elapsed: float


def records(pg: Postgres) -> list[tuple[int, str, str]]:
    rows = pg.rows(live.SELECT_RECORDS)
    return [(int(i), str(s), str(label)) for i, s, label in rows]


POLLED = {
    "disable": (SESSION, CUSTOMERS),
    "removal": (TEAM, CUSTOMERS),
    "last-role": (TEAM, SESSION),
    "control": (TEAM, CUSTOMERS),
}
ROLES = {
    "disable": ["rep"],
    "removal": ["rep", "manager"],
    "last-role": ["manager"],
    "control": ["rep", "manager"],
}


@pytest.fixture(scope="module")
def window(keycloak_running: Started) -> Iterator[Window]:
    composition = keycloak_running.composition
    realm = live.Realm(composition)
    with postgres() as pg, live.live_app(composition, pg) as app:
        with pg.connect() as connection:
            connection.execute(live.CREATE_RECORDS)
        accounts: dict[str, Account] = {}
        for key, roles in ROLES.items():
            username, password = live.unique(key), live.new_password()
            accounts[key] = Account(
                username, password, realm.create_account(username, password, roles)
            )
        with pg.connect() as connection:
            for key, account in accounts.items():
                connection.execute(live.INSERT_RECORD, (account.user_id, f"k05-{key}"))
        planted = records(pg)
        for account in accounts.values():
            account.session = app.login(account.username, account.password)
            assert app.subject(account.session) == account.user_id
        # Before t0 every account is served as its roles say.
        assert app.status(*TEAM, accounts["removal"].session) == 200
        assert app.status(*TEAM, accounts["last-role"].session) == 200
        assert app.status(*CUSTOMERS, accounts["disable"].session) == 200

        # t0 is taken before the first change is sent, so every elapsed value overstates.
        t0 = time.monotonic()
        realm.set_enabled(accounts["disable"].user_id, False)
        realm.change_roles(accounts["removal"].user_id, "DELETE", ["manager"])
        realm.change_roles(accounts["last-role"].user_id, "DELETE", ["manager"])
        for _ in live.wait_until(t0 + WINDOW_SECONDS, POLL_SECONDS):
            for key, account in accounts.items():
                if key == "disable" and account.first(SESSION, 401) is not None:
                    continue
                for operation in POLLED[key]:
                    status = app.status(*operation, account.session)
                    account.seen.append((time.monotonic() - t0, operation, status))
        elapsed = time.monotonic() - t0
        after_window = records(pg)

        # Reactivation and role restoration, then a new login of each changed account.
        realm.set_enabled(accounts["disable"].user_id, True)
        realm.change_roles(accounts["removal"].user_id, "POST", ["manager"])
        realm.change_roles(accounts["last-role"].user_id, "POST", ["manager"])
        for key in ("disable", "removal", "last-role"):
            account = accounts[key]
            account.session = app.login(account.username, account.password)
        yield Window(app, realm, accounts, planted, after_window, elapsed)


def test_k05_a_disabled_account_s_session_is_refused_401_within_300_seconds(
    window: Window, record_property: RecordProperty
) -> None:
    account = window.accounts["disable"]
    refused_at = account.first(SESSION, 401)
    record_property("k05_disable_401_s", refused_at)
    assert refused_at is not None, account.statuses(SESSION)
    assert refused_at <= BOUND_SECONDS, f"401 after {refused_at} s, bound {BOUND_SECONDS} s"
    # Never a 403 on the way: the loss is authentication, not a role.
    assert 403 not in account.statuses(SESSION) | account.statuses(CUSTOMERS)


def test_k05_b_a_removed_role_is_refused_403_within_300_seconds_while_rep_keeps_working(
    window: Window, record_property: RecordProperty
) -> None:
    account = window.accounts["removal"]
    refused_at = account.first(TEAM, 403)
    record_property("k05_removal_403_s", refused_at)
    assert refused_at is not None, account.statuses(TEAM)
    assert refused_at <= BOUND_SECONDS, f"403 after {refused_at} s, bound {BOUND_SECONDS} s"
    assert account.statuses(CUSTOMERS) == {200}
    # Once refused, the manager operation stays refused for the rest of the window.
    after = {s for t, op, s in account.seen if op == TEAM and t >= refused_at}
    assert after == {403}


def test_k05_removing_the_last_role_answers_403_not_401(
    window: Window, record_property: RecordProperty
) -> None:
    account = window.accounts["last-role"]
    refused_at = account.first(TEAM, 403)
    record_property("k05_last_role_403_s", refused_at)
    assert refused_at is not None, account.statuses(TEAM)
    assert refused_at <= BOUND_SECONDS, f"403 after {refused_at} s, bound {BOUND_SECONDS} s"
    assert 401 not in account.statuses(TEAM) | account.statuses(SESSION)
    # With no role left, every non-exempt route refuses it, the session view included.
    assert account.first(SESSION, 403) is not None


def test_k05_contrast_an_unchanged_account_keeps_every_answer_past_300_seconds(
    window: Window, record_property: RecordProperty
) -> None:
    account = window.accounts["control"]
    record_property("k05_window_s", window.elapsed)
    assert window.elapsed > BOUND_SECONDS + 1, f"window {window.elapsed} s"
    assert max(t for t, _, _ in account.seen) > BOUND_SECONDS + 1
    assert account.statuses(TEAM) == account.statuses(CUSTOMERS) == {200}


def test_k05_rows_naming_the_accounts_are_unchanged(window: Window) -> None:
    assert len(window.planted) == len(ROLES)
    assert window.after_window == window.planted
    assert records(window.app.pg) == window.planted


def test_k05_reactivation_and_role_restoration_reach_the_same_records(window: Window) -> None:
    app, accounts = window.app, window.accounts
    subjects = {subject for _, subject, _ in window.planted}
    for key in ("disable", "removal", "last-role"):
        account = accounts[key]
        assert app.subject(account.session) == account.user_id
        assert account.user_id in subjects
    assert app.status(*CUSTOMERS, accounts["disable"].session) == 200
    assert app.status(*TEAM, accounts["removal"].session) == 200
    assert app.status(*TEAM, accounts["last-role"].session) == 200
