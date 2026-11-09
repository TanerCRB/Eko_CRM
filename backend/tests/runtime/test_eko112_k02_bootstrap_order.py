"""EKO-1-12 K-02: live listener order and independent closed-listener contrasts."""

from pathlib import Path

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    RealmClient,
    listener_open,
    prepare,
    run_bootstrap,
)
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime


def live_brute_force(composition: Composition, realm: str) -> bool:
    client = RealmClient(composition, "master")
    try:
        token = client.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            composition.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        body = client.admin_json(token, "GET", "", realm=realm)
        return body["bruteForceProtected"] is True
    finally:
        client.close()


def test_k02_fresh_bootstrap_order_and_existing_volume_rerun(
    fresh: Composition, tmp_path: Path
) -> None:
    prepare(fresh)
    assert not listener_open(fresh, "admin")
    assert not listener_open(fresh, "auth")
    evidence = tmp_path / "bootstrap.jsonl"
    run_bootstrap(fresh, evidence)
    assert live_brute_force(fresh, "master")
    assert live_brute_force(fresh, "eko")
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")
    events = [line for line in evidence.read_text(encoding="utf-8").splitlines() if line]
    order = [
        "master bruteForceProtected true",
        "custom provider selected",
        "filtering verified",
        "admin listener open",
        "application realm import complete",
        "application bruteForceProtected true",
        "public listener open",
    ]
    positions = [next(i for i, line in enumerate(events) if expected in line) for expected in order]
    assert positions == sorted(positions)
    assert positions[0] < positions[1] < positions[2] < positions[3], (
        "provider selection and filtering verification must precede the first listener"
    )
    run_bootstrap(fresh, evidence)
    rerun = evidence.read_text(encoding="utf-8")
    assert "rerun existing volume live checks" in rerun
    rerun_lines = [line for line in rerun.splitlines() if "filtering verified" in line]
    assert len(rerun_lines) >= 2, "restart against the existing volume must re-verify filtering"
    provider_lines = [line for line in rerun.splitlines() if "custom provider selected" in line]
    assert len(provider_lines) >= 2, "restart must re-establish the custom provider selection"


def test_k02_master_precondition_contrast_keeps_only_admin_listener_closed(
    fresh: Composition,
) -> None:
    prepare(fresh)
    run_bootstrap(fresh, overrides={"EKO112_MASTER_BRUTE_FORCE": "false"}, expected=3)
    assert not listener_open(fresh, "admin")
    assert not listener_open(fresh, "auth")
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")


@pytest.mark.parametrize(
    ("override", "exit_code"),
    [
        ({"EKO112_APPLICATION_IMPORT": "false"}, 4),
        ({"EKO112_APPLICATION_BRUTE_FORCE": "false"}, 5),
    ],
)
def test_k02_application_precondition_contrast_keeps_public_listener_closed(
    fresh: Composition, override: dict[str, str], exit_code: int
) -> None:
    prepare(fresh)
    run_bootstrap(fresh, overrides=override, expected=exit_code)
    assert listener_open(fresh, "admin")
    assert not listener_open(fresh, "auth")
    run_bootstrap(fresh)
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")


def test_k02_rerun_past_the_default_page_and_without_a_kcadm_session(
    fresh: Composition, tmp_path: Path
) -> None:
    """R-07 + S-04 on the same bootstrapped composition.

    R-07: the unfiltered `GET /admin/realms/{realm}/users` returns at most Keycloak's
    default page (100 rows); a rerun against a realm grown past it must still find every
    bootstrap account (`find_user` reads with the filtered `username`+`exact` query, the
    way the tests do) rather than miss one, attempt a create and die on the uniqueness
    conflict after the admin gate had opened. Seed the master realm past the page,
    observe the page cap as the premise, and rerun.

    S-04: the bootstrap authenticated kcadm for the realm import; the master-admin
    session it persists (Keycloak 26.8.1 kcadm writes `$HOME/.keycloak/kcadm.config` inside
    the long-lived Keycloak container — probed on this image) must be removed when the
    import step finishes, the way `/tmp/eko112-realm.json` was. The script's own post-check
    aborts the run if the removal misses, so this external read cannot pass vacuously.
    """
    prepare(fresh)
    run_bootstrap(fresh)

    leftover = fresh.compose(
        "exec", "-T", "keycloak", "sh", "-c",
        'test -e "${HOME}/.keycloak/kcadm.config" && echo kept || echo gone',
    ).stdout.strip()  # fmt: skip
    assert leftover == "gone", "the kcadm master-admin session survived the bootstrap"

    master = RealmClient(fresh, "master")
    try:
        token = master.direct_master_token(
            fixtures.ACCOUNTS["breakglass_one"],
            fresh.env[fixtures.PASSWORD_VARIABLES["breakglass_one"]],
        )
        for index in range(150):
            created = master.admin(
                token,
                "POST",
                "users",
                realm="master",
                json_body={"username": f"eko112-page-{index:03d}", "enabled": False},
            )
            assert created.status_code == 201, created.status_code
        page = master.admin_json(token, "GET", "users", realm="master")
        assert len(page) == 100, (
            f"the unfiltered endpoint showed no page cap ({len(page)} rows); this contrast "
            "exercises nothing unless Keycloak truncates the list"
        )
    finally:
        master.close()

    evidence = tmp_path / "bootstrap-past-page.jsonl"
    run_bootstrap(fresh, evidence)
    assert "rerun existing volume live checks" in evidence.read_text(encoding="utf-8")
    assert listener_open(fresh, "admin")
    assert listener_open(fresh, "auth")
