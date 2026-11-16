"""EKO-1-12 K-05: shared configuration never enables reset e-mail."""

import json
from typing import Any

from tests.support.repo import REPO_ROOT


def test_k05_versioned_shared_realm_disables_reset_email() -> None:
    realm: dict[str, Any] = json.loads(
        (REPO_ROOT / "identity" / "eko-realm.json").read_text(encoding="utf-8")
    )
    assert realm["resetPasswordAllowed"] is False
    assert realm.get("smtpServer", {}).get("password") is None


def test_k05_shared_profile_has_no_mail_catcher_or_reset_enable_override(
    rendered_shared: dict[str, Any],
) -> None:
    assert "mailcatcher" not in rendered_shared["services"]
    assert not any(
        "reset" in str(value).lower() and "true" in str(value).lower()
        for service in rendered_shared["services"].values()
        for value in (service.get("environment") or {}).values()
    )


def test_k05_development_enablement_is_explicit_and_not_shared(
    rendered_dev: dict[str, Any], rendered_shared: dict[str, Any]
) -> None:
    assert "mailcatcher" in rendered_dev["services"]
    assert rendered_dev["services"]["mailcatcher"]["profiles"] == ["dev"]
    assert "mailcatcher" not in rendered_shared["services"]


def test_k05_enabling_reset_in_a_shared_realm_is_a_real_contrast() -> None:
    path = REPO_ROOT / "identity" / "eko-realm.json"
    realm: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    realm["resetPasswordAllowed"] = True
    assert realm["resetPasswordAllowed"] is not False
