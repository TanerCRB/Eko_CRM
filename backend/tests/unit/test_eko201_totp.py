"""EKO-2-01: the standard-library RFC 6238 helper the runtime carriers type codes with, the
OTP-secret scan and page redaction they rely on, and the invented account set they use
(Q-2 A; ADR-0005 synthetic-data rule)."""

import pytest

from tests.support import eko201_keycloak as accounts
from tests.support import totp

# RFC 6238 Appendix B, SHA-1 rows: the 20-byte ASCII seed, 8 digits.
RFC_SEED = b"12345678901234567890"
RFC_VECTORS = [
    (59, "94287082"),
    (1_111_111_109, "07081804"),
    (1_111_111_111, "14050471"),
    (1_234_567_890, "89005924"),
    (2_000_000_000, "69279037"),
    (20_000_000_000, "65353130"),
]


@pytest.mark.parametrize(("at", "expected"), RFC_VECTORS)
def test_rfc6238_sha1_vectors(at: int, expected: str) -> None:
    assert totp.hotp(RFC_SEED, totp.time_step(at), digits=8) == expected


def test_six_digit_codes_are_the_low_digits_and_differ_by_step() -> None:
    assert totp.hotp(RFC_SEED, totp.time_step(59)) == "287082"
    assert totp.totp(RFC_SEED, 1) != totp.totp(RFC_SEED, 2)


def test_displayed_secret_is_the_base32_of_the_raw_secret_bytes() -> None:
    assert totp.displayed_secret("12345678901234567890") == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    forms = accounts.secret_forms("12345678901234567890")
    assert forms["base32-grouped"].startswith("GEZD GNBV GY3T")


def test_eko201_accounts_are_invented() -> None:
    assert all(name.startswith("eko201-") for name in accounts.ACCOUNTS.values())
    assert all(address.endswith("@example.org") for address in accounts.ADDRESSES.values())
    assert len(set(accounts.ACCOUNTS.values())) == len(accounts.ACCOUNTS)
    assert "unknown" in accounts.MARKUP_USERNAME and "<" in accounts.MARKUP_USERNAME


def test_scan_finds_each_form_and_a_bounded_code_but_not_a_longer_number() -> None:
    material = accounts.OtpMaterial(secrets=["12345678901234567890"], codes=["287082"])
    clean = {"log": "line 1287082 and 2870829 and nothing else"}
    assert accounts.scan_findings(clean, material) == []
    assert accounts.scan_findings({"log": "x 287082 y"}, material) == ["log: typed code 0"]
    for label, form in accounts.secret_forms("12345678901234567890").items():
        found = accounts.scan_findings({"log": f"... {form.lower()} ..."}, material)
        assert f"log: secret 0 ({label})" in found
    # A bytea hex literal is not a code carrier: ciphertext hex holds digit runs by chance.
    hexed = {"db": "\\x" + "ab287082cd" * 4}
    assert accounts.scan_findings(hexed, material) == []


def test_redaction_removes_the_enrolment_secret_and_flow_identifiers() -> None:
    raw = "SyntheticRawSecret01"
    page = (
        '<form action="https://a.example/x?session_code=abc&amp;execution=def&tab_id=ghi">'
        f'<input type="hidden" id="totpSecret" name="totpSecret" value="{raw}" />'
        f'<span id="kc-totp-secret-key">{totp.displayed_secret(raw)}</span>'
        '<img src="data:image/png;base64,iVBORw0KGgo=" />'
        '<img src="data:image/png;base64, iVBORw0KGgoAAAANSUhEUg=" />'
        'checkAuthSession("hash-value")'
    )
    redacted = accounts.redact_page(page, [raw])
    for value in (
        raw,
        totp.displayed_secret(raw),
        "abc",
        "def",
        "ghi",
        "iVBORw0KGgo",
        "AAAANSUhEUg",
        "hash-value",
    ):
        assert value not in redacted


def test_page_check_accepts_a_polish_eko_crm_page_and_names_each_defect() -> None:
    page = (
        '<html lang="pl"><head><title>Zaloguj się do Eko_CRM</title>'
        '<link href="/resources/x/login/eko-crm/css/eko-crm.css"></head>'
        "<body><h1>Zaloguj się do Eko_CRM</h1></body></html>"
    )
    assert accounts.page_findings("login", page) == []
    assert accounts.page_findings("login", page.replace('lang="pl"', 'lang="en"'))
    assert accounts.page_findings("login", page.replace("/login/eko-crm/", "/login/keycloak.v2/"))
    english = page.replace("<h1>Zaloguj się do Eko_CRM</h1>", "<h1>Sign in to your account</h1>")
    assert any("English default" in item for item in accounts.page_findings("login", english))
