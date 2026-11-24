"""Customers as the brief defines them (CUS-1 to CUS-5, CUS-8) and the value rules gate 1 fixed
(EKO-3-01, G-1 A to G-6 A; EKO-3-02, C-1 A to C-3 A, G-1 A to G-5 A, Q-4 A).

Text is stored as Unicode NFC, normalised here before it is written (ADR-0002 *Polish text*);
every length bound is counted on that form. A rule that refuses a value raises `ValueError` with
a fixed message that never repeats the value (ADR-0005: no personal data in a message).
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from uuid import UUID

from app.domain import regions

NAME_LIMIT = 120
NOTE_LIMIT = 500
CONTACT_LIMIT = 50
# HS10 (b) A on Issue #195 (2026-11-18), counted on the trimmed NFC form.
EMAIL_LIMIT = 254
DEFAULT_COUNTRY = "PL"
# Raw caps, checked on the value as sent before trimming and NFC run (fix round 1, R-01 A). NFC
# composes at most four code points into one character (U+1F82 from its four-code-point NFD, the
# most in Unicode 15), so four times a bound never refuses a value whose NFC is within it.
NFC_COMPOSITION_LIMIT = 4
NAME_RAW_LIMIT = NFC_COMPOSITION_LIMIT * NAME_LIMIT
# The e-mail bound is the larger of the two kinds; a valid phone is at most 16 characters once
# its separators are dropped.
VALUE_RAW_LIMIT = NFC_COMPOSITION_LIMIT * EMAIL_LIMIT
NOTE_RAW_LIMIT = NFC_COMPOSITION_LIMIT * NOTE_LIMIT
NATIONAL_PREFIX = "+48"
# EKO-3-02 G-1 A, counted on the trimmed NFC form; a Polish NIP is bounded as sent instead.
STREET_LIMIT = 150
TOWN_LIMIT = 100
FOREIGN_POSTAL_CODE_LIMIT = 20
FOREIGN_TAX_ID_LIMIT = 32
NIP_SENT_LIMIT = 32
STREET_RAW_LIMIT = NFC_COMPOSITION_LIMIT * STREET_LIMIT
TOWN_RAW_LIMIT = NFC_COMPOSITION_LIMIT * TOWN_LIMIT
# A Polish postal code is six characters once trimmed, well inside the foreign bound's cap.
POSTAL_CODE_RAW_LIMIT = NFC_COMPOSITION_LIMIT * FOREIGN_POSTAL_CODE_LIMIT
TAX_ID_RAW_LIMIT = NFC_COMPOSITION_LIMIT * FOREIGN_TAX_ID_LIMIT
REGION_RAW_LIMIT = NFC_COMPOSITION_LIMIT * regions.NAME_LIMIT
# EKO-3-04 G-6 A: the longest searchable value (an e-mail address), counted on the trimmed NFC form.
SEARCH_LIMIT = EMAIL_LIMIT
SEARCH_RAW_LIMIT = NFC_COMPOSITION_LIMIT * SEARCH_LIMIT

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
# CUS-3: `00-000` in ASCII digits only (`[0-9]`, never `\d`, which takes any Unicode digit).
POLISH_POSTAL_CODE = re.compile(r"[0-9]{2}-[0-9]{3}")
# CUS-5, P2 `domain.js` l. 39-53: a leading `PL` in either case (G-4 A), then hyphens and spaces.
NIP_PREFIX = re.compile(r"\A[Pp][Ll]")
NIP_SEPARATORS = re.compile(r"[ -]")
NIP_DIGITS = re.compile(r"[0-9]{10}")
NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


class ContactKind(StrEnum):
    PHONE = "phone"
    EMAIL = "email"


class CustomerNotFound(Exception):
    """No customer with this identifier is visible to the caller: missing and not visible are
    the same answer (ADR-0003 addendum of EKO-3-01, section 3)."""


class CustomerArchived(Exception):
    """An archived customer inside the caller's scope is not edited; it is restored first
    (EKO-3-05 G-4 A). Raised only after the scope selected the customer, never for one outside
    it (ADR-0003 addendum draft of EKO-3-05, scope before state)."""


class Unchanged(Enum):
    """Why a change by identifier changed nothing: the customer is outside the caller's scope or
    exists nowhere, or it is archived and the change needs an active customer."""

    MISSING = "missing"
    ARCHIVED = "archived"


class StateFilter(StrEnum):
    """The list's state filter (EKO-3-05 Q-5): a closed set compared byte-wise; it selects
    records within the scope and is never part of it (Q-2 A)."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    BOTH = "both"


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


def given(raw: str | None) -> str | None:
    """`None`, `""` and whitespace only are a value not given (EKO-3-02 G-2 A)."""
    if raw is None or not raw.strip():
        return None
    return raw


def _bounded(raw: str, limit: int) -> str:
    text = _text(raw.strip())
    if len(text) > limit:
        raise ValueError(f"at most {limit} characters")
    return text


def street(raw: str | None) -> str | None:
    """Street and number: trimmed, NFC, at most `STREET_LIMIT` characters, stored as text."""
    value = given(raw)
    return None if value is None else _bounded(value, STREET_LIMIT)


def town(raw: str | None) -> str | None:
    """Post office or town: trimmed, NFC, at most `TOWN_LIMIT` characters."""
    value = given(raw)
    return None if value is None else _bounded(value, TOWN_LIMIT)


def is_polish(country: str) -> bool:
    return country == DEFAULT_COUNTRY


def postal_code(country: str, raw: str | None) -> str | None:
    """Poland, sent or defaulted: `00-000` once trimmed (CUS-3). Elsewhere: free text, trimmed,
    NFC, at most `FOREIGN_POSTAL_CODE_LIMIT` characters (CUS-4)."""
    value = given(raw)
    if value is None:
        return None
    if not is_polish(country):
        return _bounded(value, FOREIGN_POSTAL_CODE_LIMIT)
    code = value.strip()
    if not POLISH_POSTAL_CODE.fullmatch(code):
        raise ValueError("not a Polish postal code (00-000)")
    return code


def _region_name(raw: str) -> str:
    # Exactly as sent but for NFC: no trimming and no case folding (G-3 A).
    return _text(raw)


def voivodeship(country: str, raw: str | None) -> str | None:
    """One of the register's 16 for Poland; refused for any other country (C-3 A)."""
    value = given(raw)
    if value is None:
        return None
    if not is_polish(country):
        raise ValueError("only a Polish address has a voivodeship")
    return regions.voivodeship(_region_name(value))


def county(country: str, voivodeship_name: str | None, raw: str | None) -> str | None:
    """A county of the chosen voivodeship for Poland, never without one (C-2 A; G-5 A: the error
    is the county's); refused for any other country (C-3 A). `voivodeship_name` is the value
    `voivodeship()` returned."""
    value = given(raw)
    if value is None:
        return None
    if not is_polish(country):
        raise ValueError("only a Polish address has a county")
    if voivodeship_name is None:
        raise ValueError("a county needs its voivodeship")
    return regions.county(voivodeship_name, _region_name(value))


def polish_nip(raw: str) -> str:
    """At most `NIP_SENT_LIMIT` characters as sent; trimmed, a leading `PL` and then every
    hyphen and space removed; ten ASCII digits whose weighted sum modulo 11 is the last digit, a
    remainder of 10 being no NIP (CUS-5). The ten digits are the canonical form."""
    if len(raw) > NIP_SENT_LIMIT:
        raise ValueError(f"at most {NIP_SENT_LIMIT} characters")
    digits = NIP_SEPARATORS.sub("", NIP_PREFIX.sub("", raw.strip(), count=1))
    if not NIP_DIGITS.fullmatch(digits):
        raise ValueError("not a Polish NIP")
    check = sum(int(d) * w for d, w in zip(digits, NIP_WEIGHTS, strict=False)) % 11
    if check == 10 or check != int(digits[9]):
        raise ValueError("not a Polish NIP: the check digit does not match")
    return digits


def tax_id(country: str, raw: str | None) -> str | None:
    """Poland: the canonical NIP. Elsewhere: free text, trimmed, NFC, at most
    `FOREIGN_TAX_ID_LIMIT` characters, no checksum (CUS-5; ADR-0002 addendum of EKO-3-02)."""
    value = given(raw)
    if value is None:
        return None
    if is_polish(country):
        return polish_nip(value)
    return _bounded(value, FOREIGN_TAX_ID_LIMIT)


def search_term(raw: str) -> str | None:
    """The query of a customer search (ADR-0002 addendum of EKO-3-04): trimmed, then NFC (G-4
    A); empty or whitespace only is no query (G-5 A); at most `SEARCH_LIMIT` characters (G-6 A)."""
    if not raw.strip():
        return None
    return _bounded(raw, SEARCH_LIMIT)


def state_filter(raw: str) -> StateFilter:
    """Exactly one of the closed set, no trimming or case folding; `""` is not given, which is
    active (EKO-3-05 Q-5, G-2 A). The message names the set, never the value sent."""
    if raw == "":
        return StateFilter.ACTIVE
    if raw not in {state.value for state in StateFilter}:
        raise ValueError("not a customer state: active, archived or both")
    return StateFilter(raw)


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
class Address:
    """One address per customer (CUS-1), every part optional; voivodeship and county only for
    Poland, as the register names them (Q-4 A)."""

    street: str | None = None
    postal_code: str | None = None
    town: str | None = None
    voivodeship: str | None = None
    county: str | None = None


@dataclass(frozen=True)
class TaxId:
    """At most one tax identifier, placed by the country: a Polish customer's canonical NIP in
    `nip`, any other customer's text in `foreign`, the other one `None` (ADR-0002 addendum of
    EKO-3-02, section 3)."""

    nip: str | None = None
    foreign: str | None = None

    @classmethod
    def placed(cls, country: str, value: str | None) -> "TaxId":
        if value is None:
            return cls()
        return cls(nip=value) if is_polish(country) else cls(foreign=value)

    @property
    def value(self) -> str | None:
        return self.nip if self.nip is not None else self.foreign


@dataclass(frozen=True)
class CustomerDraft:
    """A customer as a create request asks for it, every value already normalised; contacts in
    the order sent (G-6 A)."""

    name: str
    country: str
    contacts: tuple[Contact, ...]
    address: Address = Address()
    tax_id: TaxId = TaxId()


@dataclass(frozen=True)
class Customer:
    id: UUID
    name: str
    country: str
    contacts: tuple[Contact, ...]
    address: Address = Address()
    tax_id: TaxId = TaxId()
    # The stored state, never derived from a request (EKO-3-05 K-05 M-s2); no default, so every
    # reader of the row states it.
    archived: bool = field(kw_only=True)


@dataclass(frozen=True)
class CustomerSearch:
    """What a list request narrows the caller's scope by: a search term, an owner subject and a
    state, each already judged; term and owner `None` when not given, the state active. It
    selects records within the scope and never replaces it (ADR-0003 addendum of EKO-3-04)."""

    term: str | None = None
    owner: str | None = None
    state: StateFilter = StateFilter.ACTIVE


@dataclass(frozen=True)
class CustomerSummary:
    id: UUID
    name: str
    country: str
    archived: bool
