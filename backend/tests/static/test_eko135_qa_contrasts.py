"""EKO-1-35 K-01, QA contrasts: three relaxations of the comparison that the developer's tests
let through (mutations EKO-1-35/M-13, M-14, M-15 survived them).

- The plain-string exemption for a value list (A-01) holds at `CustomerInput.country` only; a
  frontend field typed `string` against any other enum or literal still fails.
- A request enum gaining a value passes (G-A A); a response enum gaining one does not, because
  the frontend then reads a value it does not declare. The direction is the one changed element.
- A field typed with a paired frontend type passes without a deep comparison only when its
  document `$ref` is that type's own component; another paired type, or another component,
  is compared and fails.
"""

from typing import Any

import pytest

from tests.static.test_eko135_k01_frontend_types import (
    AUTH,
    CUSTOMERS,
    Document,
    Plant,
    judged,
    kind_enum,
    named,
    planted,
    schema,
    set_property,
    sources,
)
from tests.support import frontend_contract as fc

# M-13: the value-list exemption is not a general "string against an enum passes" ---------------


def test_eko135_qa_k01_value_lists_is_exactly_the_country_field() -> None:
    assert fc.VALUE_LISTS == {"CustomerInput.country"}


PLAIN_STRING: dict[str, tuple[tuple[str, str, str], tuple[str, ...]]] = {
    "request-enum-typed-string": (
        (CUSTOMERS, "  kind: ContactKind;", "  kind: string;"),
        ("ContactInput against ContactIn", "ContactInput.kind"),
    ),
    "response-literal-typed-string": (
        (AUTH, '  status: "logged_out";', "  status: string;"),
        ("LoggedOut against LoggedOut", "LoggedOut.status"),
    ),
}


@pytest.mark.parametrize("case_id", sorted(PLAIN_STRING))
def test_eko135_qa_k01_plain_string_against_an_enum_outside_the_value_list_fails(
    case_id: str,
) -> None:
    edit, parts = PLAIN_STRING[case_id]
    assert named(judged(planted(*edit)), *parts), case_id


def test_eko135_qa_k01_plain_string_against_the_country_enum_passes() -> None:
    # The pristine `CustomerInput.country: string` against the 249-code enum: the one exemption.
    assert sources()[CUSTOMERS].count("  country: string;\n  contacts: ContactInput[];") == 1
    assert judged(sources()) == []


# M-15: an enum gaining a value passes in a request only ----------------------------------------


def _logged_out_status(*values: str) -> Plant:
    return set_property(
        "LoggedOut", "status", {"type": "string", "enum": list(values), "title": "Status"}, True
    )


def test_eko135_qa_k01_response_enum_gaining_a_value_fails() -> None:
    problems = judged(sources(), _logged_out_status("logged_out", "signed_out"))
    assert named(problems, "LoggedOut against LoggedOut", "LoggedOut.status", "signed_out")


def test_eko135_qa_k01_response_enum_gaining_a_value_declared_by_the_frontend_passes() -> None:
    files = planted(AUTH, '  status: "logged_out";', '  status: "logged_out" | "signed_out";')
    assert judged(files, _logged_out_status("logged_out", "signed_out")) == []


def test_eko135_qa_k01_request_enum_gaining_the_same_kind_of_value_passes() -> None:
    assert judged(sources(), kind_enum("phone", "email", "fax")) == []


# M-14: the paired-type shortcut needs the type's own component -------------------------------


def _contacts_ref(component: str) -> Plant:
    def apply(doc: Document) -> None:
        contacts: dict[str, Any] = schema(doc, "CustomerOut")["properties"]["contacts"]
        contacts["items"] = {"$ref": f"#/components/schemas/{component}"}

    return apply


def test_eko135_qa_k01_field_retyped_with_another_paired_type_fails() -> None:
    files = planted(CUSTOMERS, "  contacts: ContactRecord[];", "  contacts: ContactInput[];")
    assert named(judged(files), "CustomerRecord against CustomerOut", "CustomerRecord.contacts")


def test_eko135_qa_k01_document_field_pointing_at_another_component_fails() -> None:
    problems = judged(sources(), _contacts_ref("ContactIn"))
    assert named(problems, "CustomerRecord against CustomerOut", "CustomerRecord.contacts")


def test_eko135_qa_k01_field_pointing_at_its_own_component_passes() -> None:
    assert judged(sources(), _contacts_ref("ContactOut")) == []
