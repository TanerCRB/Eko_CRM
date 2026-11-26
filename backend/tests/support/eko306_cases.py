"""EKO-3-06 K-02 cases shared by the unit and the runtime parity tests: one invalid value per
case, chosen so the database alone would accept it (no nine-digit NIP, no second primary), each
with its one-value correction. Every value is synthetic (ADR-0005); every NIP is built at run time
(`eko302_nip`), never written as a literal.
"""

import unicodedata
from dataclasses import dataclass, replace
from typing import Any

from app.domain.customers import ContactInput, CustomerInput
from tests.support import eko302_nip as nips

VALID_NIP = nips.valid_nip(306_001)
# A county of `łódzkie`, sent with a `mazowieckie` address.
OTHER_VOIVODESHIPS_COUNTY = "kutnowski"


@dataclass(frozen=True)
class Case:
    family: str
    # The field the seed's report names; a contact's is `contacts.<field>`.
    field: str
    refused: CustomerInput
    corrected: CustomerInput


def base(name: str) -> CustomerInput:
    return CustomerInput(name=name, town="Kutno", postal_code="99-300")


def spaced(*groups: int) -> str:
    """A phone written with spaces, built at run time so no source line holds a phone shape."""
    return " ".join(f"{group:03d}" for group in groups)


def _phone(value: str) -> ContactInput:
    return ContactInput("phone", value)


def _email(value: str) -> ContactInput:
    return ContactInput("email", value)


def _cases() -> dict[str, Case]:
    many = tuple(_email(f"k02.kontakt{i}@seed.example") for i in range(51))
    return {
        "cus2-empty-name": Case(
            "CUS-2", "name", CustomerInput(name="  "), CustomerInput(name="Gospodarstwo K02 A")
        ),
        "cus2-121-code-points": Case(
            "CUS-2", "name", CustomerInput(name="Ż" * 121), CustomerInput(name="Ż" * 120)
        ),
        "cus2-country-xx": Case(
            "CUS-2",
            "country",
            CustomerInput(name="Hof K02 XX", country="XX"),
            CustomerInput(name="Hof K02 XX", country="DE"),
        ),
        "cus3-postal-code-00000": Case(
            "CUS-3/CUS-4",
            "postal_code",
            replace(base("Gospodarstwo K02 B"), postal_code="00000"),
            replace(base("Gospodarstwo K02 B"), postal_code="00-000"),
        ),
        "cus3-county-of-another-voivodeship": Case(
            "CUS-3/CUS-4",
            "county",
            replace(
                base("Gospodarstwo K02 C"),
                voivodeship="mazowieckie",
                county=OTHER_VOIVODESHIPS_COUNTY,
            ),
            replace(
                base("Gospodarstwo K02 C"), voivodeship="łódzkie", county=OTHER_VOIVODESHIPS_COUNTY
            ),
        ),
        "cus4-voivodeship-on-de": Case(
            "CUS-3/CUS-4",
            "voivodeship",
            CustomerInput(name="Hof K02 DE", country="DE", voivodeship="mazowieckie"),
            CustomerInput(name="Hof K02 DE", country="DE"),
        ),
        "cus5-wrong-check-digit": Case(
            "CUS-5",
            "tax_id",
            CustomerInput(name="Gospodarstwo K02 D", tax_id=nips.wrong_check_digit(VALID_NIP)),
            CustomerInput(name="Gospodarstwo K02 D", tax_id=VALID_NIP),
        ),
        "cus5-remainder-ten": Case(
            "CUS-5",
            "tax_id",
            CustomerInput(name="Gospodarstwo K02 E", tax_id=nips.remainder_ten_digits(306_100)),
            CustomerInput(name="Gospodarstwo K02 E", tax_id=nips.valid_nip(306_100)),
        ),
        "cus8-phone-12345": Case(
            "CUS-8",
            "contacts.value",
            CustomerInput(name="Gospodarstwo K02 F", contacts=(_phone("12345"),)),
            CustomerInput(
                name="Gospodarstwo K02 F", contacts=(_phone("+48 " + spaced(600, 306, 306)),)
            ),
        ),
        "cus8-email-without-a-dot": Case(
            "CUS-8",
            "contacts.value",
            CustomerInput(name="Gospodarstwo K02 G", contacts=(_email("biuro@seed"),)),
            CustomerInput(name="Gospodarstwo K02 G", contacts=(_email("biuro@seed.example"),)),
        ),
        "cus1-51-contacts": Case(
            "CUS-1",
            "contacts",
            CustomerInput(name="Gospodarstwo K02 H", contacts=many),
            CustomerInput(name="Gospodarstwo K02 H", contacts=many[:50]),
        ),
    }


CASES = _cases()


def normalised_record() -> CustomerInput:
    """(3) of K-02: a nine-digit national phone (stored `+48...`), a name in NFD with surrounding
    spaces (stored trimmed, NFC) and a NIP spelled `PL 000-...` (stored as ten digits)."""
    nip = nips.valid_nip(306_200)
    return CustomerInput(
        name="  " + unicodedata.normalize("NFD", "Gospodarstwo Łąkowe Źrebię K02") + "  ",
        street="ul. Polna 3",
        postal_code="99-300",
        town=unicodedata.normalize("NFD", "Kutno-Łąkoszyn"),
        voivodeship="łódzkie",
        county="kutnowski",
        tax_id="PL " + nips.hyphenated(nip),
        contacts=(
            ContactInput("phone", spaced(600, 306, 200), "biuro", True),
            ContactInput("email", "  k02.norm@seed.example  "),
        ),
    )


def body(given: CustomerInput) -> dict[str, Any]:
    """The same record as a `POST /api/customers` body; absent optional values are omitted."""
    found: dict[str, Any] = {"name": given.name, "country": given.country}
    for field in ("street", "postal_code", "town", "voivodeship", "county", "tax_id"):
        value = getattr(given, field)
        if value is not None:
            found[field] = value
    found["contacts"] = [
        {"kind": c.kind, "value": c.value, "note": c.note, "primary": c.primary}
        for c in given.contacts
    ]
    return found
