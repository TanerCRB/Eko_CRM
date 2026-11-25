"""EKO-3-06 K-02, unit half (gate 1 A-5 A): the raw-values-to-`CustomerDraft` composition is held
once in `app.domain.customers`, and the API's `CustomerCreate` judges every field through it.

- Every K-02 case is refused by the domain composition, naming its field, and by `CustomerCreate`
  at the same field; with its one value corrected, both accept it.
- One normalised record gives the same `CustomerDraft` from both.
- The API's model judges its fields in the domain's order, so a country-dependent rule sees the
  same fields before it on both paths.

The runtime half (the seed's run and `POST /api/customers` on PostgreSQL) is
`tests/runtime/eko306/test_eko306_k02_same_rules_as_create.py`.
"""

import pytest
from pydantic import ValidationError

from app.api.customers import CustomerCreate
from app.domain.customers import CUSTOMER_FIELDS, CustomerRefused, customer_draft
from tests.support.eko306_cases import CASES, body, normalised_record


def api_refused_fields(raw: dict[str, object]) -> set[str]:
    with pytest.raises(ValidationError) as refused:
        CustomerCreate.model_validate(raw)
    return {str(error["loc"][0]) for error in refused.value.errors(include_url=False)}


@pytest.mark.parametrize("case", sorted(CASES))
def test_eko306_k02_each_case_is_refused_by_the_domain_and_by_create_at_one_field(
    case: str,
) -> None:
    found = CASES[case]
    with pytest.raises(CustomerRefused) as refused:
        customer_draft(found.refused)
    assert refused.value.fields == (found.field,)
    assert api_refused_fields(body(found.refused)) == {found.field.split(".")[0]}


@pytest.mark.parametrize("case", sorted(CASES))
def test_eko306_k02_contrast_each_corrected_case_is_accepted_by_both(case: str) -> None:
    found = CASES[case]
    assert (
        customer_draft(found.corrected)
        == CustomerCreate.model_validate(body(found.corrected)).draft()
    )


def test_eko306_k02_a_normalised_record_gives_the_same_draft_on_both_paths() -> None:
    record = normalised_record()
    draft = customer_draft(record)
    assert draft == CustomerCreate.model_validate(body(record)).draft()
    assert draft.name == "Gospodarstwo Łąkowe Źrebię K02"
    assert draft.contacts[0].value.startswith("+48")
    assert draft.tax_id.nip is not None and len(draft.tax_id.nip) == 10


def test_eko306_k02_the_api_judges_its_fields_in_the_domain_order() -> None:
    assert tuple(CustomerCreate.model_fields) == (*CUSTOMER_FIELDS, "contacts")


def test_eko306_k02_the_refusal_carries_field_names_only() -> None:
    record = CASES["cus5-wrong-check-digit"].refused
    with pytest.raises(CustomerRefused) as refused:
        customer_draft(record)
    assert record.tax_id is not None
    assert record.tax_id not in str(refused.value) + repr(refused.value.args)
