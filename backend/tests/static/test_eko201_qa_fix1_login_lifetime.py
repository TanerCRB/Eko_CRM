"""EKO-2-01 QA (fix round 1, R-03 realm half): the Keycloak login-page lifetime the export sets
(`accessCodeLifespanLogin` 600, matching the backend's ten-minute login transaction) is one of the
settings the bootstrap re-applies and verifies before the public listener opens, so a live realm
that drifted from it keeps the listener closed. The export's own value is pinned elsewhere
(`test_eko201_realm_export.py`); this reads the bootstrap's live precondition."""

import json

import pytest

from tests.static.test_eko201_bootstrap_preconditions import (
    EXPORT,
    FakeKeycloak,
    bootstrap,
    emitted,
)

FLOWS = ["browser", "eko browser", "eko browser forms"]


def exported_realm() -> dict[str, object]:
    realm: dict[str, object] = json.loads(EXPORT.read_text(encoding="utf-8"))
    return realm


@pytest.mark.parametrize(("live", "verified"), [(600, True), (1800, False)])
def test_qa_r03_live_login_page_lifetime_is_a_precondition_of_the_public_listener(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    live: int,
    verified: bool,
) -> None:
    module = bootstrap(monkeypatch)
    realm = {**exported_realm(), "accessCodeLifespanLogin": live}
    fake = FakeKeycloak(module, realm, FLOWS)
    if verified:
        module.verify_application_settings(fake, "token", module.export_settings())
        assert emitted(capsys) == ["application security settings verified"]
    else:
        with pytest.raises(SystemExit) as stopped:
            module.verify_application_settings(fake, "token", module.export_settings())
        assert stopped.value.code == 7
        assert emitted(capsys) == ["application security settings not applied"]


def test_qa_r03_the_bootstrap_reapplies_the_exported_login_page_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = bootstrap(monkeypatch)
    assert module.export_settings().get("accessCodeLifespanLogin") == 600
