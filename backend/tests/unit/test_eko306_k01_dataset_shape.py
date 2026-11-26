"""EKO-3-06 K-01 shape assertions and ADR-0005-C23 on the dataset itself, without a database: three
shares of the stated size, the mix C-5 A asks for, every NIP with the reserved `000` prefix (G-1 A),
every e-mail address in a reserved domain (A-1 A), and one fixed value set pinned by the committed
fingerprint, the same under other hash seeds in other processes.

The stored side (the same fingerprint read back from PostgreSQL after a load into two fresh
databases) is `tests/runtime/eko306/test_eko306_k01_each_rep_owns_its_share.py`.
"""

import subprocess
import sys
import unicodedata
from collections import Counter

import pytest

from app.seed_dataset import SHARE_SIZE, SHARES, records
from tests.support.eko306_dataset import FINGERPRINT, dataset_rows, fingerprint
from tests.support.pg_instance import BACKEND
from tests.support.repo_checks import RESERVED_DOMAIN

KEY, NAME, COUNTRY, STREET, POSTAL, TOWN, VOIVODESHIP, COUNTY, NIP, FOREIGN, CONTACTS = range(11)
POLISH_LETTERS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")


def test_k01_three_shares_each_of_the_stated_size_about_two_hundred() -> None:
    found = records()
    assert SHARES == 3 and 180 <= SHARE_SIZE <= 220
    assert Counter(r.share for r in found) == {0: SHARE_SIZE, 1: SHARE_SIZE, 2: SHARE_SIZE}
    assert len({r.key for r in found}) == len(found)


def test_k01_the_dataset_has_the_mix_of_customers_c5_asks_for() -> None:
    rows = dataset_rows()
    polish = [r for r in rows if r[COUNTRY] == "PL"]
    foreign = [r for r in rows if r[COUNTRY] != "PL"]
    assert any(r[NIP] for r in polish) and any(r[NIP] is None for r in polish)
    assert any(r[FOREIGN] for r in foreign) and any(r[FOREIGN] is None for r in foreign)
    assert any(len(r[CONTACTS]) == 1 for r in rows)
    assert any(len(r[CONTACTS]) > 1 for r in rows)
    only_name_and_country = [
        r for r in rows if all(r[i] is None for i in range(STREET, FOREIGN + 1)) and not r[CONTACTS]
    ]
    assert only_name_and_country


def test_k01_names_and_towns_carry_polish_diacritics_in_nfc() -> None:
    rows = dataset_rows()
    assert any(POLISH_LETTERS & set(r[NAME]) for r in rows)
    assert any(r[TOWN] and POLISH_LETTERS & set(r[TOWN]) for r in rows)
    for row in rows:
        for value in (row[NAME], row[STREET], row[TOWN], row[COUNTY]):
            assert value is None or unicodedata.is_normalized("NFC", value)


def test_c23_every_nip_has_the_reserved_prefix_and_none_repeats() -> None:
    nips = [r[NIP] for r in dataset_rows() if r[NIP] is not None]
    assert len(nips) > SHARE_SIZE
    assert all(nip.startswith("000") and len(nip) == 10 for nip in nips)
    assert len(set(nips)) == len(nips)


def test_c23_every_email_address_is_in_a_reserved_domain() -> None:
    addresses = [c[1] for r in dataset_rows() for c in r[CONTACTS] if c[0] == "email"]
    assert addresses
    assert [a for a in addresses if not RESERVED_DOMAIN.search(a.rsplit("@", 1)[1])] == []


def test_c23_the_value_set_is_the_committed_fingerprint() -> None:
    assert fingerprint(dataset_rows()) == FINGERPRINT


PROBE = (
    "from tests.support.eko306_dataset import dataset_rows, fingerprint; "
    "print(fingerprint(dataset_rows()))"  # leftovers-allow: subprocess probe source, not output
)


@pytest.mark.parametrize("hash_seed", ["1", "4242"])
def test_c23_another_process_under_another_hash_seed_builds_the_same_set(hash_seed: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env={"PYTHONHASHSEED": hash_seed, "SYSTEMROOT": _systemroot(), "PATH": _path()},
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    assert done.stdout.strip() == FINGERPRINT


def _systemroot() -> str:
    import os

    return os.environ.get("SYSTEMROOT", "")


def _path() -> str:
    import os

    return os.environ.get("PATH", "")
