"""EKO-1-12 K-04 (G-03): the inherited expiry paths run through the selected custom store.

Keycloak 26.8.1 clears expired events on its periodic datastore tasks
(`ClearExpiredEvents` → `EventStoreProvider.clearExpiredEvents()`,
`ClearExpiredAdminEvents` → the `JpaEventStoreProviderFactory` invalidation handler, which
casts the selected provider to `JpaEventStoreProvider` and calls `clearExpiredAdminEvents()`).
The custom provider inherits both methods unchanged, so the scheduled path deletes at the
accepted retentions through the same-ID override — not around it.

This test, on its own bootstrapped composition:

1. produces application-realm authentication events (`LOGIN_ERROR` — two of them), application-
   realm admin events (user create + delete as `administrator`), master-realm login events
   (two successful `admin-cli` grants) and master-realm admin events (two user writes as the
   break-glass holder);
2. time-travels the oldest of each set past its accepted retention (31 days for eko login
   events, 91 days for eko admin events, 91 days for master login and admin events) by SQL —
   inside this test's own composition, as the retention claim is about the deletion rule, not
   about the wall clock;
3. waits (bounded, past the worst-case 900 s schedule the server reports) for the periodic
   run, and asserts: every time-travelled row is gone, every untravelled control of the same
   type remains, and the reads happen through the reviewer-visible admin queries (non-empty
   store on both sides — absence of an event is proven by identifier, not by an empty list).

The 30-day/90-day boundaries are the accepted realm settings (`eventsExpiration`,
`adminEventsExpiration`); the test shifts past them and waits. Removing the custom provider's
selection would not change this path (it is inherited), but the listener boundary means this
composition can only be read through the bootstrapped, verified store — K-02's pair ran first.
"""

import re
import time
from typing import Any

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    RealmClient,
    listener_open,
    prepare,
    run_bootstrap,
)
from tests.runtime.test_eko112_k04_reset_and_log_privacy import (
    assert_refused_login,
    ensure_account,
)
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime
EXPIRY_WAIT_SECONDS = 1500  # the 900 s default schedule plus a full settle margin
POLL_SECONDS = 20
DAY_MS = 86_400_000


ROW_ID = re.compile(r"[0-9a-f-]{36}")
REALMS = {"eko", "master"}
AGE_TYPES = {"LOGIN", "LOGIN_ERROR", "LOGOUT"}
PSQL_NAME = re.compile(r"[a-z_][a-z0-9_]*")
PSQL_VALUE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def psql(composition: Composition, statement: str, **variables: str) -> list[list[str]]:
    """One statement against the Keycloak database with every value carried as a psql
    variable (`:'name'` / `:name`), never interpolated into the statement text — the same
    rule `backup_lab.restore_psql` follows: the values reach the client as `\\set` lines of
    a script on stdin (server-side `-c` does not substitute them), and the values stay
    identifier-shaped."""
    lines: list[str] = []
    for name, value in variables.items():
        assert PSQL_NAME.fullmatch(name), name
        assert PSQL_VALUE.fullmatch(value), f"{name}: psql variable value shape"
        lines.append(f"\\set {name} {value}")
    script = "\n".join([*lines, statement.strip().rstrip(";") + ";"]) + "\n"
    result = composition.compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "keycloak",
        "-AtX", "-v", "ON_ERROR_STOP=1", "-f", "-", stdin=script,
    )  # fmt: skip
    return [line.split("\t") for line in result.stdout.splitlines() if line]


def scalar(composition: Composition, statement: str, **variables: str) -> str:
    rows = psql(composition, statement, **variables)
    return rows[0][0] if rows and rows[0] else ""


# Keycloak 26.8 stores the realm UUID in an event row's `realm_id` (the admin REST filters it
# back to the realm NAME); every realm-scoped statement here is a plain literal joining
# through `realm` so realms are addressed by name and no SQL is ever string-built. Values
# still travel as psql variables.
def event_census(composition: Composition) -> str:
    """What the authentication store actually holds (realm, type, count) — named in the
    "nothing to age" failure so a missing event is visible, not just asserted away."""
    rows = psql(
        composition,
        "SELECT r.name || '=' || e.type || ':' || count(*)"
        " FROM event_entity e JOIN realm r ON r.id = e.realm_id"
        " GROUP BY r.name, e.type ORDER BY r.name, e.type",
    )
    return "; ".join(row[0] for row in rows) or "(empty event_entity)"


def shift_auth_events(composition: Composition, realm: str, event_type: str, age_ms: int) -> str:
    """Move the OLDEST event of (realm, type) `age_ms` into the past; return its row id.

    The newest of the same type stays untravelled as the control (the test produced exactly
    two of each before calling this)."""
    assert realm in REALMS and event_type in AGE_TYPES
    row_id = scalar(
        composition,
        "SELECT e.id FROM event_entity e JOIN realm r ON r.id = e.realm_id"
        " WHERE r.name = :'realm' AND e.type = :'etype'"
        " ORDER BY e.event_time ASC LIMIT 1",
        realm=realm,
        etype=event_type,
    )
    assert row_id, (
        f"no stored {event_type} event in realm {realm} to age: {event_census(composition)}"
    )
    assert ROW_ID.fullmatch(row_id), row_id
    psql(
        composition,
        "UPDATE event_entity SET event_time = event_time - :age WHERE id = :'row_id'",
        age=str(age_ms),
        row_id=row_id,
    )
    return row_id


def admin_census(composition: Composition) -> str:
    """What the admin-event store actually holds (realm, operation, count)."""
    rows = psql(
        composition,
        "SELECT r.name || '=' || e.operation_type || ':' || count(*)"
        " FROM admin_event_entity e JOIN realm r ON r.id = e.realm_id"
        " GROUP BY r.name, e.operation_type ORDER BY r.name, e.operation_type",
    )
    return "; ".join(row[0] for row in rows) or "(empty admin_event_entity)"


def shift_admin_events(composition: Composition, realm: str, age_ms: int) -> str:
    assert realm in REALMS
    row_id = scalar(
        composition,
        "SELECT e.id FROM admin_event_entity e JOIN realm r ON r.id = e.realm_id"
        " WHERE r.name = :'realm' ORDER BY e.admin_event_time ASC LIMIT 1",
        realm=realm,
    )
    assert row_id, f"no stored admin event in realm {realm} to age: {admin_census(composition)}"
    assert ROW_ID.fullmatch(row_id), row_id
    psql(
        composition,
        "UPDATE admin_event_entity SET admin_event_time = admin_event_time - :age"
        " WHERE id = :'row_id'",
        age=str(age_ms),
        row_id=row_id,
    )
    return row_id


def auth_row_count(composition: Composition, row_id: str) -> int:
    assert ROW_ID.fullmatch(row_id), row_id
    statement = "SELECT count(*) FROM event_entity WHERE id = :'row_id'"
    return int(scalar(composition, statement, row_id=row_id))


def admin_row_count(composition: Composition, row_id: str) -> int:
    assert ROW_ID.fullmatch(row_id), row_id
    statement = "SELECT count(*) FROM admin_event_entity WHERE id = :'row_id'"
    return int(scalar(composition, statement, row_id=row_id))


def remaining_rows(composition: Composition, aged: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, row_id in aged.items():
        if label.endswith("_admin"):
            counts[label] = admin_row_count(composition, row_id)
        else:
            counts[label] = auth_row_count(composition, row_id)
    return counts


def admin_event_ids(events: list[dict[str, Any]]) -> set[str]:
    return {str(event["id"]) for event in events}


def auth_events_by_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event["type"] == event_type]


def test_k04_inherited_expiry_paths_delete_at_accepted_retentions(fresh: Composition) -> None:
    prepare(fresh)
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin") and listener_open(fresh, "auth")

    master = RealmClient(fresh, "master")
    app = RealmClient(fresh, "eko")
    public = RealmClient(fresh, "eko", listener="auth")
    try:
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            fresh.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        administrator_token = app.browser_token(
            fixtures.ACCOUNTS["administrator"],
            fresh.env[fixtures.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=fresh.env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        # eko authentication events: two LOGIN_ERROR for a KNOWN account (oldest gets aged,
        # newest is the control). The account is created here — this composition's fixture is
        # its own `fresh`, and the refused logins must fail on a wrong password, not on a
        # missing account, so the aged rows are genuine known-account LOGIN_ERROR events.
        ensure_account(
            app,
            administrator_token,
            fixtures.ACCOUNTS["known"],
            fixtures.ADDRESSES["known"],
            "synthetic-" + str(time.time_ns()),
            True,
        )
        wrong = "synthetic-wrong-" + str(time.time_ns())
        assert_refused_login(public, fixtures.ACCOUNTS["known"], wrong)
        time.sleep(2.0)  # keep the two carriers' stored times strictly ordered
        assert_refused_login(public, fixtures.ACCOUNTS["known"], wrong + "-second")
        # master authentication events: two LOGIN (grants)
        master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_two"],
            fresh.env[fixtures.PASSWORD_VARIABLES["breakglass_two"]],
        )
        master.direct_master_token(
            fixtures.ACCOUNTS["reviewer"],
            fresh.env[fixtures.PASSWORD_VARIABLES["reviewer"]],
        )
        # eko admin events: create + delete of a throwaway account, as the administrator
        created = ensure_account(
            app,
            administrator_token,
            fixtures.ACCOUNTS["managed"],
            fixtures.ADDRESSES["managed"],
            "synthetic-" + str(time.time_ns()),
            True,
        )
        app.admin(administrator_token, "DELETE", f"users/{created['id']}")
        # master admin events: two user writes as the break-glass holder
        holder = master.admin_json(
            breakglass,
            "GET",
            "users",
            params={"username": fixtures.ACCOUNTS["verification_probe"], "exact": "true"},
            realm="master",
        )
        if not holder:
            master.admin(
                breakglass,
                "POST",
                "users",
                realm="master",
                json_body={
                    "username": fixtures.ACCOUNTS["verification_probe"],
                    "email": fixtures.ADDRESSES["verification_probe"],
                    "enabled": False,
                },
            )
        found = master.admin_json(
            breakglass,
            "GET",
            "users",
            params={"username": fixtures.ACCOUNTS["verification_probe"], "exact": "true"},
            realm="master",
        )
        assert len(found) == 1
        master.admin(breakglass, "DELETE", f"users/{found[0]['id']}", realm="master")
        time.sleep(2.0)  # the store write is part of the request; a small settle bound

        aged = {
            "eko_auth": shift_auth_events(fresh, "eko", "LOGIN_ERROR", 31 * DAY_MS),
            "master_auth": shift_auth_events(fresh, "master", "LOGIN", 91 * DAY_MS),
            "eko_admin": shift_admin_events(fresh, "eko", 91 * DAY_MS),
            "master_admin": shift_admin_events(fresh, "master", 91 * DAY_MS),
        }
        before_auth = int(scalar(fresh, "SELECT count(*) FROM event_entity"))
        before_admin = int(scalar(fresh, "SELECT count(*) FROM admin_event_entity"))
        deadline = time.monotonic() + EXPIRY_WAIT_SECONDS
        remaining = remaining_rows(fresh, aged)
        while time.monotonic() < deadline:
            remaining = remaining_rows(fresh, aged)
            if all(count == 0 for count in remaining.values()):
                break
            time.sleep(POLL_SECONDS)
        else:
            raise AssertionError(
                "the inherited expiry tasks did not delete the time-travelled rows within "
                f"{EXPIRY_WAIT_SECONDS}s: {remaining}"
            )

        # Controls survive: the newest event of each aged set is still stored and readable
        # through the accepted admin queries (presence is asserted by row, not by absence).
        after_auth = int(scalar(fresh, "SELECT count(*) FROM event_entity"))
        after_admin = int(scalar(fresh, "SELECT count(*) FROM admin_event_entity"))
        assert after_auth == before_auth - 2, (
            "expiry removed a different number of authentication rows than planted (2 aged)"
        )
        assert after_admin == before_admin - 2, (
            "expiry removed a different number of admin rows than planted (2 aged)"
        )

        # The wait can exceed the 240 s application access-token lifespan; re-mint the
        # break-glass token before the readback so the controls are read through a fresh,
        # non-expired admin session (the count SQL above is token-independent).
        breakglass = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            fresh.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        eko_events = master.admin_json(
            breakglass, "GET", "events", realm="eko", params={"max": "500"}
        )
        login_errors = auth_events_by_type(eko_events, "LOGIN_ERROR")
        assert login_errors, "the untravelled LOGIN_ERROR control did not remain"
        assert all(event["time"] > time.time() * 1000 - 30 * DAY_MS for event in eko_events), (
            "an authentication event older than the 30-day retention remains "
            "in the application realm"
        )
        master_events = master.admin_json(
            breakglass, "GET", "events", realm="master", params={"max": "500"}
        )
        master_logins = auth_events_by_type(master_events, "LOGIN")
        assert master_logins, "the untravelled master LOGIN control did not remain"
        assert all(event["time"] > time.time() * 1000 - 90 * DAY_MS for event in master_events), (
            "an authentication event older than the 90-day master retention remains"
        )
        eko_admin = master.admin_json(breakglass, "GET", "admin-events", realm="eko")
        master_admin = master.admin_json(breakglass, "GET", "admin-events", realm="master")
        assert aged["eko_admin"] not in admin_event_ids(eko_admin)
        assert aged["master_admin"] not in admin_event_ids(master_admin)
        assert admin_event_ids(eko_admin), "the untravelled eko admin-event control did not remain"
        assert admin_event_ids(master_admin), (
            "the untravelled master admin-event control did not remain"
        )
    finally:
        master.close()
        app.close()
        public.close()
