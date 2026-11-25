"""EKO-3-06, ADR-0003-C39 (A-6 A, G-3 A, G-4 A): the operator creation scope judges a named
subject on the owner form alone (1 to 255 characters in U+0021..U+007E, the addendum of
2026-11-20) and stores it as received; it reads no account and builds no caller.
"""

import pytest

from app.domain.ownership import OwnedBy, operator_creation_scope

ACCEPTED = [
    "5a1e0306-0000-4000-8000-00000000000a",
    "x",
    "~" * 255,
    "Rep-A",
    "rep-a",
]
REFUSED = {
    "empty": "",
    "a-space": "rep a",
    "leading-space": " rep",
    "non-ascii": "rep-ł",
    "256-characters": "r" * 256,
    "a-tab": "rep\ta",
    "a-newline": "rep\n",
}


@pytest.mark.parametrize("subject", ACCEPTED)
def test_c39_a_subject_of_the_owner_form_becomes_its_scope_as_received(subject: str) -> None:
    assert operator_creation_scope(subject) == OwnedBy(subject)


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_c39_a_subject_outside_the_owner_form_is_refused_naming_no_value(case: str) -> None:
    subject = REFUSED[case]
    with pytest.raises(ValueError) as refused:
        operator_creation_scope(subject)
    if subject.strip():
        assert subject.strip() not in str(refused.value)


def test_c39_subjects_that_differ_only_in_case_are_distinct_scopes() -> None:
    assert operator_creation_scope("Rep-A") != operator_creation_scope("rep-a")
