"""The operator seed's committed synthetic dataset (SEED-1; EKO-3-06 C-5 A, G-1 A, G-2 A, A-1 A).

Three shares of the same size, one per rep the operator names, of Polish customers with and
without a NIP, a few foreign ones with and without a tax ID, single- and multi-contact customers,
and some with only a name and a country. Every value is built here, from the stems below, by plain
index arithmetic: no clock, environment, network, file or random source is read, so every run of
every process builds the same records in the same order (ADR-0005 addendum of EKO-3-06, C23).

Every NIP has the prefix `000`, which is no tax office's prefix, and its check digit is computed
here; phones are assembled here too, so no line of this file holds a NIP or phone shape (the
repository's personal-data scan is unchanged). Every e-mail address is in a reserved domain.
Every record is valid under create's rules: invalid records exist in tests only (G-2 A).

This module depends on `app.domain` only (layer row `seed_dataset`).
"""

from collections.abc import Iterator
from dataclasses import dataclass

from app.domain.customers import NIP_WEIGHTS, ContactInput, CustomerInput

VERSION = "v1"
SHARES = 3
SHARE_SIZE = 200
# No tax office's prefix (the `backend/tests/support/eko302_nip.py` precedent).
NIP_PREFIX = "000"
# The six digits after the prefix start here; test-only NIPs stay below it.
NIP_STEM_START = 500_000
EMAIL_DOMAINS = (
    "example.com",
    "example.org",
    "example.net",
    "gospodarstwo.example",
    "rolnik.test",
    "agro.invalid",
)

FIRST_NAMES = (
    "Jan", "Józef", "Stanisław", "Krzysztof", "Andrzej", "Tomasz", "Grzegorz", "Paweł",
    "Łukasz", "Michał", "Anna", "Maria", "Małgorzata", "Krystyna", "Barbara", "Elżbieta",
    "Zofia", "Jadwiga", "Agnieszka", "Halina", "Wojciech", "Zbigniew", "Bożena", "Jerzy",
)  # fmt: skip
SURNAMES = (
    "Nowak", "Wójcik", "Kowalczyk", "Mazur", "Krawczyk", "Kaczmarek", "Zając", "Król",
    "Wróbel", "Dudek", "Pawlak", "Sikora", "Baran", "Szewczyk", "Michalak", "Kozieł",
    "Gołąb", "Bąk", "Żak", "Łuczak", "Cieślak", "Kubiak", "Pietrzak", "Głowacz", "Sowa",
)  # fmt: skip
FARM_KINDS = ("Drobiu", "Trzody", "Bydła", "Indyków", "Kur Niosek")
CROPS = ("Zbożowe", "Sadownicze", "Warzywnicze", "Ekologiczne", "Nasienne")
STREETS = (
    "ul. Polna", "ul. Lipowa", "ul. Kwiatowa", "ul. Leśna", "ul. Słoneczna", "ul. Ogrodowa",
    "ul. Łąkowa", "ul. Szkolna", "ul. Kościelna", "ul. Źródlana", "ul. Długa", "ul. Wiejska",
)  # fmt: skip
# Post towns as the TERYT register names their voivodeship and county (EKO-3-02).
PLACES = (
    ("Kutno", "99-300", "łódzkie", "kutnowski"),
    ("Łowicz", "99-400", "łódzkie", "łowicki"),
    ("Sieradz", "98-200", "łódzkie", "sieradzki"),
    ("Grójec", "05-600", "mazowieckie", "grójecki"),
    ("Płońsk", "09-100", "mazowieckie", "płoński"),
    ("Sochaczew", "96-500", "mazowieckie", "sochaczewski"),
    ("Garwolin", "08-400", "mazowieckie", "garwoliński"),
    ("Łuków", "21-400", "lubelskie", "łukowski"),
    ("Kraśnik", "23-200", "lubelskie", "kraśnicki"),
    ("Biłgoraj", "23-400", "lubelskie", "biłgorajski"),
    ("Hrubieszów", "22-500", "lubelskie", "hrubieszowski"),
    ("Września", "62-300", "wielkopolskie", "wrzesiński"),
    ("Gniezno", "62-200", "wielkopolskie", "gnieźnieński"),
    ("Kościan", "64-000", "wielkopolskie", "kościański"),
    ("Gostyń", "63-800", "wielkopolskie", "gostyński"),
    ("Brodnica", "87-300", "kujawsko-pomorskie", "brodnicki"),
    ("Chełmno", "86-200", "kujawsko-pomorskie", "chełmiński"),
    ("Żnin", "88-400", "kujawsko-pomorskie", "żniński"),
    ("Augustów", "16-300", "podlaskie", "augustowski"),
    ("Grajewo", "19-200", "podlaskie", "grajewski"),
    ("Bielsk Podlaski", "17-100", "podlaskie", "bielski"),
    ("Bochnia", "32-700", "małopolskie", "bocheński"),
    ("Miechów", "32-200", "małopolskie", "miechowski"),
    ("Jędrzejów", "28-300", "świętokrzyskie", "jędrzejowski"),
    ("Busko-Zdrój", "28-100", "świętokrzyskie", "buski"),
    ("Sandomierz", "27-600", "świętokrzyskie", "sandomierski"),
    ("Bartoszyce", "11-200", "warmińsko-mazurskie", "bartoszycki"),
    ("Działdowo", "13-200", "warmińsko-mazurskie", "działdowski"),
    ("Chojnice", "89-600", "pomorskie", "chojnicki"),
    ("Bytów", "77-100", "pomorskie", "bytowski"),
    ("Głubczyce", "48-100", "opolskie", "głubczycki"),
    ("Kluczbork", "46-200", "opolskie", "kluczborski"),
    ("Bolesławiec", "59-700", "dolnośląskie", "bolesławiecki"),
    ("Dzierżoniów", "58-200", "dolnośląskie", "dzierżoniowski"),
    ("Jarosław", "37-500", "podkarpackie", "jarosławski"),
    ("Dębica", "39-200", "podkarpackie", "dębicki"),
    ("Międzyrzecz", "66-300", "lubuskie", "międzyrzecki"),
    ("Nowa Sól", "67-100", "lubuskie", "nowosolski"),
    ("Białogard", "78-200", "zachodniopomorskie", "białogardzki"),
    ("Goleniów", "72-100", "zachodniopomorskie", "goleniowski"),
    ("Cieszyn", "43-400", "śląskie", "cieszyński"),
    ("Będzin", "42-500", "śląskie", "będziński"),
)
# Foreign customers: country, a town, a postal code, the tax ID's letters (or none), the
# international dialling code and the subscriber number's length.
FOREIGN = (
    ("DE", "Frankfurt (Oder)", "15230", "DE", "49", 10),
    ("CZ", "Ostrava", "702 00", "CZ", "420", 9),
    ("LT", "Marijampolė", "68001", None, "370", 8),
    ("SK", "Žilina", "010 01", "SK", "421", 9),
    ("UA", "Lwów", "79000", None, "380", 9),
)
MOBILE_PREFIXES = ("500", "600", "660", "690", "720", "790", "880")
NOTES = ("biuro", "właściciel", "księgowość", "syn właściciela", "magazyn", None)
# One record in this many is foreign; one in `BARE_EVERY` has only a name and a country.
FOREIGN_EVERY = 23
BARE_EVERY = 29


@dataclass(frozen=True)
class Record:
    """A dataset record: its key, the share (0-based position of the named subject) it belongs
    to, and its values as given, before create's rules."""

    key: str
    share: int
    customer: CustomerInput


def _pick[T](values: tuple[T, ...], index: int, stride: int = 1) -> T:
    return values[(index * stride) % len(values)]


def nip_check(nine: str) -> int:
    """The CUS-5 weighted sum modulo 11; 10 is no NIP."""
    return sum(int(digit) * weight for digit, weight in zip(nine, NIP_WEIGHTS, strict=True)) % 11


def _nips() -> Iterator[str]:
    """The dataset's checksum-valid NIPs in order, from the stem counter."""
    stem = NIP_STEM_START
    while True:
        nine = NIP_PREFIX + f"{stem:06d}"
        check = nip_check(nine)
        if check != 10:
            yield nine + str(check)
        stem += 1


def _spelled_nip(nip: str, index: int) -> str:
    """The NIP as people write it: plain, hyphenated, with spaces, or with `PL` in front."""
    groups = (nip[0:3], nip[3:6], nip[6:8], nip[8:10])
    spelling = index % 4
    if spelling == 1:
        return "-".join(groups)
    if spelling == 2:
        return " ".join(groups)
    if spelling == 3:
        return "PL" + nip
    return nip


def _polish_phone(index: int) -> str:
    prefix = _pick(MOBILE_PREFIXES, index, 3)
    rest = f"{(index * 7919 + 13) % 1_000_000:06d}"
    groups = (prefix, rest[:3], rest[3:])
    if index % 3 == 0:
        return " ".join(groups)
    if index % 3 == 1:
        return "+48" + "".join(groups)
    return "".join(groups)


def _foreign_phone(code: str, length: int, index: int) -> str:
    number = f"{(index * 104_729 + 7) % (10**length):0{length}d}"
    return "+" + code + " " + str(1 + index % 8) + number[1:]


def _email(local: str, index: int) -> str:
    return f"{local}.{index:03d}@{_pick(EMAIL_DOMAINS, index, 5)}"


def _ascii_local(surname: str) -> str:
    table = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return surname.translate(table).lower()


def _name(index: int, first: str, surname: str, town: str) -> str:
    form = index % 6
    if form == 0:
        return f"{first} {surname}"
    if form == 1:
        return f"Gospodarstwo Rolne {first} {surname}"
    if form == 2:
        return f"{surname} Agro Sp. z o.o."
    if form == 3:
        return f"Ferma {_pick(FARM_KINDS, index)} {surname}"
    if form == 4:
        return f"Gospodarstwo {_pick(CROPS, index, 2)} {town}"
    return f"Usługi Rolnicze {first} {surname} s.c."


def _contacts(index: int, surname: str, phone: str, count: int) -> tuple[ContactInput, ...]:
    local = _ascii_local(surname)
    found = []
    for position in range(count):
        note = _pick(NOTES, index + position)
        if position % 2 == 0:
            found.append(ContactInput("phone", phone, note, position == 0 and index % 2 == 0))
        else:
            found.append(ContactInput("email", _email(local, index + position), note))
    return tuple(found)


def _record(index: int, nips: Iterator[str]) -> CustomerInput:
    first = _pick(FIRST_NAMES, index, 7)
    surname = _pick(SURNAMES, index, 11)
    if index % BARE_EVERY == 0:
        return CustomerInput(name=f"{first} {surname}", country="PL")
    contact_count = (0, 1, 1, 2, 1, 3)[index % 6]
    if index % FOREIGN_EVERY == 5:
        country, town, code, letters, dial, length = _pick(FOREIGN, index // FOREIGN_EVERY)
        tax_id = None if letters is None else f"{letters}{(index * 31_337) % 10**8:08d}"
        phone = _foreign_phone(dial, length, index)
        return CustomerInput(
            name=f"{surname} Agrar {town}",
            country=country,
            street=f"{_pick(STREETS, index)} {index % 90 + 1}" if index % 2 else None,
            postal_code=code,
            town=town,
            tax_id=tax_id,
            contacts=_contacts(index, surname, phone, max(contact_count, 1)),
        )
    town, code, voivodeship, county = _pick(PLACES, index, 5)
    with_nip = index % 5 != 4
    tax_id = None
    if with_nip:
        tax_id = _spelled_nip(next(nips), index)
    address = index % 7
    return CustomerInput(
        name=_name(index, first, surname, town),
        country="PL",
        street=None if address in (2, 5) else f"{_pick(STREETS, index, 3)} {index % 120 + 1}",
        postal_code=None if address == 5 else code,
        town=None if address == 5 else town,
        voivodeship=None if address in (3, 5) else voivodeship,
        county=None if address in (3, 4, 5) else county,
        tax_id=tax_id,
        contacts=_contacts(index, surname, _polish_phone(index), contact_count),
    )


def records() -> tuple[Record, ...]:
    """Every record, share by share, in dataset order; built afresh on each call."""
    nips = _nips()
    found = []
    for share in range(SHARES):
        for position in range(SHARE_SIZE):
            index = share * SHARE_SIZE + position
            key = f"seed-{VERSION}-{share + 1}-{position + 1:03d}"
            found.append(Record(key, share, _record(index, nips)))
    return tuple(found)
