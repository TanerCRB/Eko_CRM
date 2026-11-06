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
