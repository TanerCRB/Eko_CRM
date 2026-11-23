"""EKO-3-08 K-02 (ADR-0003 *Staff personal data*; ADR-0005 PD-S3; G-1 A as refined by Q-1 A,
G-2 A): a manager reads exactly the staff whose last login's token held `rep`, each entry holding
only the subject and the display name.
"""

import unicodedata

import pytest

from tests.runtime.eko301.conftest import created_id
from tests.runtime.eko308.conftest import A1, M1, M2, R1, R2, Staff, rep_entries, rep_subjects

pytestmark = pytest.mark.runtime

NAMES = {
    R1: unicodedata.normalize("NFD", "Żaneta Łuczyńska-Gęś"),
    R2: "Robert Testowy",
    M1: "Marek Kierowniczy",
    M2: "Maria Kierownicza",
    A1: "Adam Administracyjny",
}
ROLES = {
    R1: ["rep"],
    R2: ["rep"],
    M1: ["rep", "manager"],
    M2: ["manager"],
    A1: ["administrator"],
}


@pytest.fixture
def five(staff: Staff) -> Staff:
    for subject, roles in ROLES.items():
        staff.login(subject, roles, NAMES[subject])
    return staff


def test_k02_the_manager_reads_exactly_the_reps_as_subject_and_name(five: Staff) -> None:
    entries = rep_entries(five.login(M2, ["manager"], NAMES[M2]))
    assert {entry["subject"] for entry in entries} == {R1, R2, M1}
    for entry in entries:
        assert set(entry) == {"subject", "name"}, entry
        assert entry["name"] == unicodedata.normalize("NFC", NAMES[entry["subject"]])


def test_k02_contrast_the_list_follows_each_subjects_latest_login(five: Staff) -> None:
    five.login(A1, ["administrator", "rep"], NAMES[A1])
    five.login(R2, ["manager"], NAMES[R2])
    assert rep_subjects(five.login(M2, ["manager"], NAMES[M2])) == {R1, M1, A1}


def test_k02_edge_no_reps_stored_gives_an_empty_list(staff: Staff) -> None:
    assert rep_entries(staff.login(M2, ["manager"], NAMES[M2])) == []


def test_k02_edge_one_rep_gives_one_entry(staff: Staff) -> None:
    staff.login(R2, ["rep"], NAMES[R2])
    assert rep_entries(staff.login(M2, ["manager"])) == [{"subject": R2, "name": NAMES[R2]}]


def test_k02_edge_a_caller_holding_rep_and_manager_sees_itself(staff: Staff) -> None:
    assert rep_subjects(staff.login(M1, ["rep", "manager"], NAMES[M1])) == {M1}


def test_k02_edge_two_reps_with_one_name_give_two_entries(staff: Staff) -> None:
    staff.login(R1, ["rep"], "Jan Testowy")
    staff.login(R2, ["rep"], "Jan Testowy")
    entries = rep_entries(staff.login(M2, ["manager"]))
    assert sorted((e["subject"], e["name"]) for e in entries) == [
        (R1, "Jan Testowy"),
        (R2, "Jan Testowy"),
    ]


def test_k02_edge_a_copy_with_no_name_is_listed_with_null(staff: Staff) -> None:
    staff.login(R1, ["rep"], None)
    assert rep_entries(staff.login(M2, ["manager"])) == [{"subject": R1, "name": None}]


def test_k02_edge_an_owner_without_a_copy_is_absent_until_its_next_login(staff: Staff) -> None:
    rep = staff.login(R1, ["rep"], NAMES[R2])
    created_id(rep, {"name": "Ferma K02"})
    # As if the owner had last logged in before this release.
    with staff.pg.connect() as connection:
        connection.execute("DELETE FROM staff_display_name WHERE subject = %s", (R1,))
    manager = staff.login(M2, ["manager"])
    assert rep_subjects(manager) == set()
    staff.login(R1, ["rep"], NAMES[R2])
    assert rep_subjects(manager) == {R1}
