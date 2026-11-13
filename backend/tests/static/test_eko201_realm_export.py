"""EKO-2-01: the gate-1 values recorded in the versioned application realm export.

K-06 (export half): G-1 A session limits, G-3 A password minimum, brute-force lockout and MFA
for every account, asserted as the selected values, each with a one-value-changed contrast.
K-07 / ADR-0003-C30 (export half): theme selection, Polish-only localisation, display name.
ADR-0003-C2 static sum: the realm's access-token lifespan plus the backend's clock leeway and
maximum clock offset stays within 300 seconds. The application client's real callback,
audience and logout settings complete the browser flow the backend implements.
"""

import copy
import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from tests.support.repo import REPO_ROOT
from tests.support.theme_checks import THEME_NAME

EXPORT = REPO_ROOT / "identity" / "eko-realm.json"
BOOTSTRAP = REPO_ROOT / "scripts" / "keycloak-bootstrap.py"
Realm = dict[str, Any]


@pytest.fixture
def realm() -> Realm:
    loaded: Realm = json.loads(EXPORT.read_text(encoding="utf-8"))
    return loaded


def client(realm: Realm, client_id: str) -> dict[str, Any]:
    return next(item for item in realm["clients"] if item["clientId"] == client_id)


def flow(realm: Realm, alias: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        item for item in realm.get("authenticationFlows", []) if item["alias"] == alias
    ]
    assert len(matches) == 1, f"flow {alias!r}: {len(matches)} definitions"
    return matches[0]


def policy(realm: Realm) -> dict[str, str]:
    """`length(12) and notUsername(undefined)` as {name: argument}."""
    text = realm.get("passwordPolicy", "")
    return dict(re.findall(r"([A-Za-z]+)\(([^)]*)\)", text))


# K-06 checks: each reads the actual selected value ------------------------------------------


def check_session_limits(realm: Realm) -> None:
    assert realm["ssoSessionIdleTimeout"] == 30 * 60
    assert realm["ssoSessionMaxLifespan"] == 10 * 60 * 60


def check_password_minimum(realm: Realm) -> None:
    rules = policy(realm)
    assert rules.get("length") == "12", f"password policy {realm.get('passwordPolicy')!r}"


def check_brute_force(realm: Realm) -> None:
    assert realm["bruteForceProtected"] is True
    assert realm["permanentLockout"] is False
    assert realm["failureFactor"] == 5
    # Keycloak's temporary lockout waits `waitIncrementSeconds` per `failureFactor` failures,
    # capped at `maxFailureWaitSeconds`: both are the 15 minutes of G-3 A.
    assert realm["waitIncrementSeconds"] == 15 * 60
    assert realm["maxFailureWaitSeconds"] == 15 * 60


def otp_required_path(realm: Realm) -> list[str]:
    """Why the realm's browser flow lets a login finish without a one-time code, if it does.

    The accepted shape: the top-level flow offers only the SSO cookie and one forms sub-flow as
    alternatives; the forms sub-flow requires the password form and the OTP form, and enables
    nothing else. A REQUIRED OTP form makes Keycloak demand enrolment of an account that has no
    OTP credential, so every account, including one whose credential was removed, ends with a
    one-time code.
    """
    problems: list[str] = []
    top = flow(realm, realm.get("browserFlow", ""))
    enabled = [
        item for item in top["authenticationExecutions"] if item["requirement"] != "DISABLED"
    ]
    shape = sorted((item.get("authenticator") or "flow", item["requirement"]) for item in enabled)
    if shape != [("auth-cookie", "ALTERNATIVE"), ("flow", "ALTERNATIVE")]:
        problems.append(f"top-level executions {shape}")
    forms = [item for item in enabled if item.get("authenticatorFlow")]
    if len(forms) != 1:
        return problems + ["no single forms sub-flow"]
    inner = flow(realm, forms[0]["flowAlias"])
    inner_enabled = sorted(
        (item.get("authenticator") or item.get("flowAlias", "flow"), item["requirement"])
        for item in inner["authenticationExecutions"]
        if item["requirement"] != "DISABLED"
    )
    if inner_enabled != [
        ("auth-otp-form", "REQUIRED"),
        ("auth-username-password-form", "REQUIRED"),
    ]:
        problems.append(f"forms executions {inner_enabled}")
    actions = {item["alias"]: item for item in realm.get("requiredActions", [])}
    if "CONFIGURE_TOTP" in actions and actions["CONFIGURE_TOTP"].get("enabled") is not True:
        problems.append("CONFIGURE_TOTP required action disabled")
    return problems


def check_mfa_for_every_account(realm: Realm) -> None:
    assert otp_required_path(realm) == []


def test_k06_export_session_limits_are_30_minutes_idle_and_10_hours_absolute(realm: Realm) -> None:
    check_session_limits(realm)


def test_k06_export_password_minimum_is_12_characters(realm: Realm) -> None:
    check_password_minimum(realm)


def test_k06_export_locks_for_15_minutes_after_5_failures(realm: Realm) -> None:
    check_brute_force(realm)


def test_k06_export_requires_a_one_time_code_for_every_account(realm: Realm) -> None:
    check_mfa_for_every_account(realm)


def set_key(key: str, value: Any) -> Callable[[Realm], None]:
    return lambda realm: realm.__setitem__(key, value)


def set_requirement(alias: str, authenticator: str, requirement: str) -> Callable[[Realm], None]:
    def apply(realm: Realm) -> None:
        for item in flow(realm, alias)["authenticationExecutions"]:
            if item.get("authenticator") == authenticator:
                item["requirement"] = requirement

    return apply


def add_execution(alias: str, authenticator: str, requirement: str) -> Callable[[Realm], None]:
    def apply(realm: Realm) -> None:
        executions = flow(realm, alias)["authenticationExecutions"]
        executions.append(
            {
                "authenticator": authenticator,
                "authenticatorFlow": False,
                "requirement": requirement,
                "priority": 99,
                "autheticatorFlow": False,
                "userSetupAllowed": False,
            }
        )

    return apply


# One value changed per contrast: one below, one above and the opposite of each selection.
EXPORT_CONTRASTS = [
    ("idle-1801", set_key("ssoSessionIdleTimeout", 1801), check_session_limits),
    ("idle-1799", set_key("ssoSessionIdleTimeout", 1799), check_session_limits),
    ("max-36001", set_key("ssoSessionMaxLifespan", 36001), check_session_limits),
    ("max-35999", set_key("ssoSessionMaxLifespan", 35999), check_session_limits),
    ("password-11", set_key("passwordPolicy", "length(11)"), check_password_minimum),
    ("password-13", set_key("passwordPolicy", "length(13)"), check_password_minimum),
    ("password-none", set_key("passwordPolicy", ""), check_password_minimum),
    ("failures-6", set_key("failureFactor", 6), check_brute_force),
    ("failures-4", set_key("failureFactor", 4), check_brute_force),
    ("wait-899", set_key("waitIncrementSeconds", 899), check_brute_force),
    ("wait-901", set_key("waitIncrementSeconds", 901), check_brute_force),
    ("max-wait-60", set_key("maxFailureWaitSeconds", 60), check_brute_force),
    ("permanent", set_key("permanentLockout", True), check_brute_force),
    ("unprotected", set_key("bruteForceProtected", False), check_brute_force),
    (
        "otp-conditional",
        set_requirement("eko browser forms", "auth-otp-form", "CONDITIONAL"),
        check_mfa_for_every_account,
    ),
    (
        "otp-alternative",
        set_requirement("eko browser forms", "auth-otp-form", "ALTERNATIVE"),
        check_mfa_for_every_account,
    ),
    (
        "otp-disabled",
        set_requirement("eko browser forms", "auth-otp-form", "DISABLED"),
        check_mfa_for_every_account,
    ),
    (
        "bypass-alternative",
        add_execution("eko browser", "identity-provider-redirector", "ALTERNATIVE"),
        check_mfa_for_every_account,
    ),
    ("built-in-browser-flow", set_key("browserFlow", "browser"), check_mfa_for_every_account),
]


@pytest.mark.parametrize(
    ("mutation", "check"),
    [pytest.param(mutation, check, id=name) for name, mutation, check in EXPORT_CONTRASTS],
)
def test_k06_each_one_value_contrast_fails_its_assertion(
    realm: Realm, mutation: Callable[[Realm], None], check: Callable[[Realm], None]
) -> None:
    check(realm)
    mutated = copy.deepcopy(realm)
    mutation(mutated)
    assert mutated != realm
    with pytest.raises(AssertionError):
        check(mutated)


# K-07 / ADR-0003-C30 -------------------------------------------------------------------------

THEME_KEYS = ("loginTheme", "accountTheme", "adminTheme", "emailTheme")


def check_selection(realm: Realm) -> None:
    assert realm.get("loginTheme") == THEME_NAME
    assert realm.get("internationalizationEnabled") is True
    assert realm.get("supportedLocales") == ["pl"]
    assert realm.get("defaultLocale") == "pl"
    assert realm.get("displayName") == "Eko_CRM"
    assert [key for key in THEME_KEYS[1:] if realm.get(key)] == []


def test_k07_c30_export_selects_the_theme_polish_only_and_the_display_name(realm: Realm) -> None:
    check_selection(realm)


SELECTION_CONTRASTS = [
    ("login-theme-removed", lambda realm: realm.pop("loginTheme")),
    ("login-theme-parent", set_key("loginTheme", "keycloak.v2")),
    ("i18n-off", set_key("internationalizationEnabled", False)),
    ("second-locale", set_key("supportedLocales", ["pl", "en"])),
    ("english-default", set_key("defaultLocale", "en")),
    ("display-name", set_key("displayName", "Eko CRM")),
    ("account-theme", set_key("accountTheme", THEME_NAME)),
    ("email-theme", set_key("emailTheme", "keycloak")),
]


@pytest.mark.parametrize(
    "mutation", [pytest.param(mutation, id=name) for name, mutation in SELECTION_CONTRASTS]
)
def test_k07_c30_each_selection_contrast_fails(
    realm: Realm, mutation: Callable[[Realm], Any]
) -> None:
    mutated = copy.deepcopy(realm)
    mutation(mutated)
    assert mutated != realm
    with pytest.raises(AssertionError):
        check_selection(mutated)


def test_k07_c30_the_master_realm_configuration_sets_no_theme() -> None:
    """The master realm has no versioned export; the bootstrap's own master update is the
    only place that could select a theme there, so it must name none (the live read is in
    the runtime half)."""
    text = BOOTSTRAP.read_text(encoding="utf-8")
    master = text[
        text.index("def configure_master") : text.index("def configure_mapping_allow_list")
    ]
    assert not re.search(r"(?i)theme", master)


def test_k07_c30_no_composition_setting_selects_a_theme_server_wide() -> None:
    text = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(?i)KC_SPI_THEME|--spi-theme|theme-default|THEME_DEFAULT", text)


# ADR-0003-C2 static sum ----------------------------------------------------------------------


def c2_total(realm: Realm) -> int:
    from app.core.settings import AuthSettings

    fields = AuthSettings.model_fields
    leeway = fields["app_oidc_clock_skew_leeway_seconds"].default
    offset = fields["app_oidc_max_clock_offset_seconds"].default
    assert isinstance(leeway, int) and isinstance(offset, int)
    lifespan = realm["accessTokenLifespan"]
    assert isinstance(lifespan, int)
    return lifespan + leeway + offset


def test_c2_realm_lifespan_plus_backend_leeway_and_offset_is_at_most_300(realm: Realm) -> None:
    assert realm["accessTokenLifespan"] == 240
    assert c2_total(realm) <= 300
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    # The composition does not override the backend's defaults the sum is computed from.
    assert "APP_OIDC_CLOCK_SKEW_LEEWAY_SECONDS" not in compose
    assert "APP_OIDC_MAX_CLOCK_OFFSET_SECONDS" not in compose


def test_c2_one_second_more_lifespan_breaks_the_sum(realm: Realm) -> None:
    longer = copy.deepcopy(realm)
    longer["accessTokenLifespan"] = 241
    assert c2_total(longer) > 300


# The application client: real callback, audience, back-channel logout -----------------------

# The path only: its origin is the client root URL the bootstrap sets from APP_ORIGIN.
CALLBACK = "/api/auth/callback"


def check_application_client(realm: Realm) -> None:
    application = client(realm, "eko-backend")
    assert application["redirectUris"] == [CALLBACK]
    # The origin is never versioned: the bootstrap sets it from the environment.
    assert "rootUrl" not in application and "baseUrl" not in application
    audience = [
        mapper
        for mapper in application.get("protocolMappers", [])
        if mapper.get("protocolMapper") == "oidc-audience-mapper"
    ]
    assert len(audience) == 1
    config = audience[0]["config"]
    assert config.get("included.client.audience") == "eko-backend"
    assert config.get("access.token.claim") == "true"
    # G-2 A: the backend ends the SSO session itself over the back channel; no browser-side
    # logout redirect is registered.
    assert application.get("frontchannelLogout") is False
    assert application.get("attributes", {}).get("post.logout.redirect.uris", "") == ""


def test_k02_application_client_uses_the_real_callback_audience_and_back_channel_logout(
    realm: Realm,
) -> None:
    check_application_client(realm)
    assert "eko112.invalid" not in EXPORT.read_text(encoding="utf-8")


def drop_audience(realm: Realm) -> None:
    application = client(realm, "eko-backend")
    application["protocolMappers"] = [
        mapper
        for mapper in application["protocolMappers"]
        if mapper.get("protocolMapper") != "oidc-audience-mapper"
    ]


CLIENT_CONTRASTS = [
    ("placeholder-callback", lambda realm: client(realm, "eko-backend").__setitem__(
        "redirectUris", ["https://eko112.invalid/callback"])),
    ("wildcard-callback", lambda realm: client(realm, "eko-backend").__setitem__(
        "redirectUris", ["/*"])),
    ("no-audience", drop_audience),
    ("post-logout-redirect", lambda realm: client(realm, "eko-backend")["attributes"].__setitem__(
        "post.logout.redirect.uris", "+")),
]  # fmt: skip


@pytest.mark.parametrize(
    "mutation", [pytest.param(mutation, id=name) for name, mutation in CLIENT_CONTRASTS]
)
def test_k02_each_client_contrast_fails(realm: Realm, mutation: Callable[[Realm], Any]) -> None:
    mutated = copy.deepcopy(realm)
    mutation(mutated)
    assert mutated != realm
    with pytest.raises(AssertionError):
        check_application_client(mutated)
