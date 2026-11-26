"""EKO-3-06, ADR-0005-C23 (the draft's section 3): the dataset key is the seed's alone. No schema
of the OpenAPI document the shipped `create_app()` serves names it, and `CustomerCreate` refuses
it as an unknown field, so no request sets it. That the API's create stores it as NULL is the
runtime half, `tests/runtime/eko306/test_eko306_adr0005_c23_create_leaves_the_key_null.py`.
"""

import json

import pytest
from pydantic import ValidationError

from app.api.customers import CustomerCreate
from tests.support.api_surface import real_app

KEY = "dataset_key"


def test_c23_no_openapi_schema_or_operation_names_the_dataset_key() -> None:
    document = json.dumps(real_app().openapi())
    assert "tax_id" in document, "the document read is not the customers' one"
    assert KEY not in document


def test_c23_a_create_body_naming_the_dataset_key_is_refused() -> None:
    with pytest.raises(ValidationError) as refused:
        CustomerCreate.model_validate({"name": "Gospodarstwo C23", KEY: "seed-v1-1-001"})
    assert [e["type"] for e in refused.value.errors()] == ["extra_forbidden"]
