"""Customers as the brief defines them (CUS-1, CUS-2, CUS-8) and the value rules gate 1 fixed
(EKO-3-01, G-1 A to G-6 A).

Text is stored as Unicode NFC, normalised here before it is written (ADR-0002 *Polish text*);
every length bound is counted on that form. A rule that refuses a value raises `ValueError` with
a fixed message that never repeats the value (ADR-0005: no personal data in a message).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

NAME_LIMIT = 120
NOTE_LIMIT = 500
CONTACT_LIMIT = 50
# HS10 (b) A on Issue #195 (2026-11-18), counted on the trimmed NFC form.
EMAIL_LIMIT = 254
DEFAULT_COUNTRY = "PL"
NATIONAL_PREFIX = "+48"

# ISO 3166-1 alpha-2, the officially assigned codes: the closed list of G-3 A.
COUNTRY_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR
    BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ
    EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW
    GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY
    KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV
    MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY
    QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG
    TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM
    ZW
    """.split()
)


# P2 `domain.js` l. 58-62 (G-3 A), with ASCII digits only: a phone is `+` and 8-15 digits, the
# first not 0; nine digits alone are a Polish number and get `+48`.
PHONE_SEPARATORS = re.compile(r"[\s()-]")
NATIONAL_NUMBER = re.compile(r"[0-9]{9}")
INTERNATIONAL_NUMBER = re.compile(r"\+[1-9][0-9]{7,14}")
EMAIL_SHAPE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


class ContactKind(StrEnum):
    PHONE = "phone"
    EMAIL = "email"


class CustomerNotFound(Exception):
    """No customer with this identifier is visible to the caller: missing and not visible are
    the same answer (ADR-0003 addendum of EKO-3-01, section 3)."""


def _text(raw: str) -> str:
    # PostgreSQL's UTF-8 text holds neither U+0000 nor a lone surrogate, which a JSON escape can
    # still produce; refused here, as a value, instead of failing at the database.
    if "\x00" in raw or any("\ud800" <= c <= "\udfff" for c in raw):
        raise ValueError("contains a character that cannot be stored")
    return unicodedata.normalize("NFC", raw)


def customer_name(raw: str) -> str:
    """Trimmed, then NFC; required and at most `NAME_LIMIT` characters (G-1 A)."""
    name = _text(raw.strip())
    if not name:
        raise ValueError("a name is required")
    if len(name) > NAME_LIMIT:
        raise ValueError(f"at most {NAME_LIMIT} characters")
    return name


def country_code(raw: str) -> str:
    """Exactly a code of `COUNTRY_CODES`: no trimming or case folding (G-2 A, G-3 A)."""
    if raw not in COUNTRY_CODES:
        raise ValueError("not a country code of the list")
    return raw


def contact_note(raw: str | None) -> str | None:
    """NFC of the note as sent, not trimmed; `None` or `""` is no note (G-4 A, G-5 A)."""
    if raw is None or raw == "":
        return None
    note = _text(raw)
    if len(note) > NOTE_LIMIT:
        raise ValueError(f"at most {NOTE_LIMIT} characters")
    return note


def phone_number(raw: str) -> str:
    """E.164: separators dropped, `+48` before nine national digits (CUS-8, G-3 A)."""
    number = PHONE_SEPARATORS.sub("", _text(raw.strip()))
    if NATIONAL_NUMBER.fullmatch(number):
        number = NATIONAL_PREFIX + number
    if not INTERNATIONAL_NUMBER.fullmatch(number):
        raise ValueError("not an international phone number")
    return number


def email_address(raw: str) -> str:
    """Trimmed, NFC, case kept; one `@` and a dot in the domain, no whitespace (P2 l. 56-58)."""
    address = _text(raw.strip())
    if len(address) > EMAIL_LIMIT:
        raise ValueError(f"at most {EMAIL_LIMIT} characters")
    if not EMAIL_SHAPE.fullmatch(address):
        raise ValueError("not an e-mail address")
    return address


def contact_value(kind: ContactKind, raw: str) -> str:
    if kind is ContactKind.PHONE:
        return phone_number(raw)
    return email_address(raw)


@dataclass(frozen=True)
class Contact:
    kind: ContactKind
    value: str
    note: str | None
    primary: bool


def check_contacts(contacts: Sequence[Contact]) -> None:
    """At most `CONTACT_LIMIT` contacts, and at most one primary across kinds (CUS-1, G-5 A)."""
    if len(contacts) > CONTACT_LIMIT:
        raise ValueError(f"at most {CONTACT_LIMIT} contacts")
    if sum(1 for contact in contacts if contact.primary) > 1:
        raise ValueError("at most one contact is primary")


@dataclass(frozen=True)
class CustomerDraft:
    """A customer as a create request asks for it, every value already normalised; contacts in
    the order sent (G-6 A)."""

    name: str
    country: str
    contacts: tuple[Contact, ...]


@dataclass(frozen=True)
class Customer:
    id: UUID
    name: str
    country: str
    contacts: tuple[Contact, ...]


@dataclass(frozen=True)
class CustomerSummary:
    id: UUID
    name: str
    country: str
