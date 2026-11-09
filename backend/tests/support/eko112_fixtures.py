"""Closed set of invented EKO-1-12 runtime identifiers; credentials are generated at run time."""

ACCOUNTS = {
    "breakglass_one": "eko112-breakglass-one",
    "breakglass_two": "eko112-breakglass-two",
    "reviewer": "eko112-reviewer",
    "administrator": "eko112-administrator",
    "known": "eko112-known",
    "disabled": "eko112-disabled",
    "managed": "eko112-managed",
    "timing": "eko112-timing",
    "locked": "eko112-locked",
    "verification_probe": "eko112-verification-probe",
}

ADDRESSES = {
    "breakglass_one": "eko112-breakglass-one@example.org",
    "breakglass_two": "eko112-breakglass-two@example.org",
    "reviewer": "eko112-reviewer@example.org",
    "administrator": "eko112-administrator@example.org",
    "known": "eko112-known@example.org",
    "unknown": "eko112-unknown@example.org",
    "disabled": "eko112-disabled@example.org",
    "managed": "eko112-managed@example.org",
    "timing": "eko112-timing@example.org",
    "locked": "eko112-locked@example.org",
    "verification_probe": "eko112-verification-probe@example.org",
}

UNKNOWN_MARKERS = (
    "eko112-unknown-Zażółć",
    "  eko112-unknown-whitespace  ",
    "eko112-unknown-<marker>&value",
    "eko112-unknown-" + "x" * 240,
)

PASSWORD_VARIABLES = {
    "breakglass_one": "EKO112_BREAKGLASS_ONE_PASSWORD",
    "breakglass_two": "EKO112_BREAKGLASS_TWO_PASSWORD",
    "reviewer": "EKO112_REVIEWER_PASSWORD",
    "administrator": "EKO112_ADMINISTRATOR_PASSWORD",
}
