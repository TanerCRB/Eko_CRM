"""EKO-2-01 runtime support against running Keycloak: invented accounts, the OTP-secret scan
and the automated page-policy checks. Pure functions; the runtime modules feed them.

Every account, address and marker here is invented for the throwaway compositions the runtime
tests start and remove (ADR-0005 synthetic-data rule).
"""

import base64
import re
from dataclasses import dataclass, field

ACCOUNTS = {
    "login": "eko201-login",
    "logout": "eko201-logout",
    "mfa": "eko201-mfa",
    "pages": "eko201-pages",
    "locked": "eko201-locked",
    "required": "eko201-required",
    "shell": "eko201-shell",
}
ADDRESSES = {key: f"{name}@example.org" for key, name in ACCOUNTS.items()}
FIRST_NAME = "EKO201"
LAST_NAME = "Synthetic"
DISPLAY_NAME = f"{FIRST_NAME} {LAST_NAME}"
# An unknown username with markup, typed into the login form for the escaped-error-page edge.
MARKUP_USERNAME = "eko201-unknown-<b>marker</b>&x"
# MFA event types Keycloak 26.8.1 can emit for enrolment or removal; none may be stored (G-E A).
MFA_EVENT_TYPES = frozenset(
    {"UPDATE_TOTP", "REMOVE_TOTP", "UPDATE_CREDENTIAL", "REMOVE_CREDENTIAL"}
)


# OTP secret and typed-code scan (ADR-0003-C32) ------------------------------------------------


@dataclass
class OtpMaterial:
    """Every raw secret Keycloak issued and every code typed for the scanned account."""

    secrets: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)


def secret_forms(raw: str) -> dict[str, str]:
    """The stored form (raw), the forms shown at enrolment (base32, grouped by four as the
    manual-entry page prints it) and a hex copy (a bytea column would hold that)."""
    encoded = base64.b32encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "raw": raw,
        "base32": encoded,
        "base32-grouped": " ".join(
            encoded[index : index + 4] for index in range(0, len(encoded), 4)
        ),
        "hex": raw.encode("utf-8").hex(),
    }


HEX_LITERAL = re.compile(r"\\\\?x[0-9a-fA-F]{16,}")


def scan_findings(sources: dict[str, str], material: OtpMaterial) -> list[str]:
    """`<source>: <what>` for every secret form or typed code found; empty is the only pass.

    Secrets are matched case-insensitively. A code is matched as a six-digit run with no digit
    on either side; long bytea hex literals are left out of the code match (ciphertext hex
    would otherwise hold any six digits by chance) but not out of the secret match.
    """
    found: list[str] = []
    for name, text in sources.items():
        folded = text.casefold()
        for index, raw in enumerate(material.secrets):
            for label, form in secret_forms(raw).items():
                if form and form.casefold() in folded:
                    found.append(f"{name}: secret {index} ({label})")
        code_text = HEX_LITERAL.sub(" ", text)
        for index, code in enumerate(material.codes):
            if re.search(rf"(?<![0-9]){re.escape(code)}(?![0-9])", code_text):
                found.append(f"{name}: typed code {index}")
    return found


# Automated page-policy checks (K-07 *Page policy*) -----------------------------------------

# English defaults of the parent theme for the texts these pages show; any of them on a page
# means a default-English replacement of the Polish wording.
ENGLISH_DEFAULTS = (
    "Sign in to your account",
    "Username or email",
    "Forgot Password?",
    "Sign In",
    "Invalid username or password.",
    "Mobile Authenticator Setup",
    "One-time code",
    "Update password",
    "Forgot Your Password?",
    "Back to Login",
    "Invalid authenticator code.",
    "Install one of the following applications on your mobile",
    "New Password",
    "Confirm password",
    "You need to set up Mobile Authenticator",
    "You should receive an email shortly",
)
# One Polish phrase each page state must show (the parent's or the theme's Polish messages).
POLISH_MARKERS = {
    "login": "Zaloguj się do Eko_CRM",
    "login-error": "Nieprawidłowa nazwa użytkownika lub hasło.",
    "lockout": "Nieprawidłowa nazwa użytkownika lub hasło.",
    "reset": "Nie pamiętasz hasła?",
    "reset-sent": "Powinieneś otrzymywać wkrótce pocztę z dalszymi instrukcjami.",
    "mfa-enrolment": "Konfiguracja aplikacji uwierzytelniającej",
    "mfa-code": "Kod jednorazowy",
    "mfa-code-error": "Nieprawidłowy kod uwierzytelnienia.",
    "required-password": "Aktualizacja hasła",
}


# F-4 (Issue #21, 2026-11-13): the enrolment instruction must name the button the page shows
# ("Zatwierdź", the parent's `doSubmit`), not the parent's "Prześlij".
MISNAMED_BUTTONS = {"mfa-enrolment": ("kliknij Prześlij",)}
ENROLMENT_INSTRUCTION = "kliknij Zatwierdź, aby zakończyć konfigurację"


def visible_text(document: str) -> str:
    without = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", document)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", without)).strip()


def page_findings(state: str, document: str) -> list[str]:
    """Why a captured page fails the selected page policy, if it does."""
    problems: list[str] = []
    if not re.search(r'<html\b[^>]*\blang="pl"', document):
        problems.append(f"{state}: page language is not Polish")
    if "/login/eko-crm/" not in document:
        problems.append(f"{state}: page does not come from the eko-crm theme")
    if "login-select-toggle" in document:
        problems.append(f"{state}: a language selector is offered")
    text = visible_text(document)
    title = re.search(r"(?is)<title>(.*?)</title>", document)
    if "Eko_CRM" not in text and (title is None or "Eko_CRM" not in title.group(1)):
        problems.append(f"{state}: the Eko_CRM name is missing")
    marker = POLISH_MARKERS[state]
    if marker not in text:
        problems.append(f"{state}: Polish wording {marker!r} missing")
    problems.extend(
        f"{state}: English default {phrase!r}" for phrase in ENGLISH_DEFAULTS if phrase in text
    )
    for phrase in MISNAMED_BUTTONS.get(state, ()):
        if phrase in text:
            problems.append(f"{state}: instruction names a button not shown {phrase!r}")
    return problems


REDACTED = "[redacted]"
QUERY_SECRETS = re.compile(
    r"(?P<name>session_code|execution|tab_id|client_data|code_challenge|state|nonce|code|"
    r"session_state|key)=(?P<value>[^&\"'\s<>]+)"
)


def redact_page(document: str, secrets_to_drop: list[str]) -> str:
    """A captured page with every per-flow identifier, the enrolment secret, its QR image and
    the auth-session hash removed, so the evidence file holds only page content."""
    redacted = QUERY_SECRETS.sub(lambda match: f"{match['name']}={REDACTED}", document)
    redacted = re.sub(r'(name="totpSecret" value=")[^"]*(")', rf"\g<1>{REDACTED}\g<2>", redacted)
    redacted = re.sub(r'(id="kc-totp-secret-key">)[^<]*(<)', rf"\g<1>{REDACTED}\g<2>", redacted)
    redacted = re.sub(
        r"data:image/[a-z]+;base64,\s*[A-Za-z0-9+/=\s]+", f"data:{REDACTED}", redacted
    )
    redacted = re.sub(r"(checkAuthSession\(\s*)\"[^\"]*\"", rf'\g<1>"{REDACTED}"', redacted)
    for secret in secrets_to_drop:
        for form in secret_forms(secret).values():
            redacted = re.sub(re.escape(form), REDACTED, redacted, flags=re.IGNORECASE)
    return redacted
