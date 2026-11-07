"""EKO-1-10 K-06: the OpenAPI document against the previous release's (ADR-0004, #19 G-1 A)."""

import ast
import copy
import io
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.release_doubles import ReachDouble, RecordDouble
from tests.static.test_k07_changeset import at_base, in_worktree
from tests.support import api_surface as api
from tests.support import changeset_checks as cc
from tests.support import openapi_compat as oc
from tests.support import workflow_checks as wc
from tests.support.releases import Release
from tests.support.repo import REPO_ROOT, bash

Document = dict[str, Any]
COMPARED = re.compile(r"compared \d+ operation")
VISIT = "/api/visits/{visit_id}"
VISITS = "/api/visits"


def ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def json_content(schema: dict[str, Any]) -> dict[str, Any]:
    return {"application/json": {"schema": schema}}


def base() -> Document:
    return {
        "openapi": "3.1.0",
        "info": {"title": "fixture", "version": "1"},
        "paths": {
            VISIT: {
                "get": {
                    "operationId": "get_visit",
                    "parameters": [
                        {
                            "name": "visit_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "ok", "content": json_content(ref("Visit"))}
                    },
                }
            },
            VISITS: {
                "post": {
                    "operationId": "create_visit",
                    "requestBody": {"required": True, "content": json_content(ref("VisitIn"))},
                    "responses": {
                        "200": {"description": "ok", "content": json_content(ref("Visit"))}
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Visit": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "status": {"type": "string", "enum": ["planned", "done"]},
                        "notes": {"type": "array", "items": ref("Note")},
                        "visited_on": {"type": "string", "format": "date"},
                    },
                    "required": ["id", "title", "status", "notes", "visited_on"],
                },
                "Note": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "maxLength": 2000}},
                    "required": ["text"],
                },
                "VisitIn": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "kind": {"type": "string", "enum": ["field", "phone"]},
                        "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "contact": {"type": "string"},
                        "name": {"type": "string", "maxLength": 100},
                    },
                    "required": ["title"],
                },
            }
        },
    }


Change = Callable[[Document], None]


def schema(doc: Document, name: str) -> dict[str, Any]:
    found: dict[str, Any] = doc["components"]["schemas"][name]
    return found


def get_op(doc: Document) -> dict[str, Any]:
    found: dict[str, Any] = doc["paths"][VISIT]["get"]
    return found


def rename_path(doc: Document) -> None:
    doc["paths"]["/api/visit/{visit_id}"] = doc["paths"].pop(VISIT)


def change_method(doc: Document) -> None:
    doc["paths"][VISITS]["put"] = doc["paths"][VISITS].pop("post")


def add_parameter(where: str, required: bool) -> Change:
    def apply(doc: Document) -> None:
        get_op(doc)["parameters"].append(
            {"name": "region", "in": where, "required": required, "schema": {"type": "string"}}
        )

    return apply


def add_body_property(required: bool) -> Change:
    def apply(doc: Document) -> None:
        schema(doc, "VisitIn")["properties"]["region"] = {"type": "string"}
        if required:
            schema(doc, "VisitIn")["required"].append("region")

    return apply


def replace_status(doc: Document) -> None:
    get_op(doc)["responses"]["201"] = get_op(doc)["responses"].pop("200")


def add_status(doc: Document) -> None:
    get_op(doc)["responses"]["201"] = copy.deepcopy(get_op(doc)["responses"]["200"])


def body_on_get(doc: Document) -> None:
    get_op(doc)["requestBody"] = {"required": True, "content": json_content(ref("Note"))}


BREAKING: dict[str, Change] = {
    "operation-removed": lambda d: d["paths"][VISITS].pop("post"),
    "path-renamed": rename_path,
    "method-changed": change_method,
    "required-query-parameter-added": add_parameter("query", True),
    "required-header-parameter-added": add_parameter("header", True),
    "optional-parameter-made-required": lambda d: get_op(d)["parameters"][1].update(required=True),
    "parameter-type-changed": lambda d: get_op(d)["parameters"][0]["schema"].update(type="string"),
    "required-body-property-added": add_body_property(required=True),
    "optional-body-property-made-required": lambda d: schema(d, "VisitIn")["required"].append(
        "note"
    ),
    "request-property-removed-under-forbid": lambda d: schema(d, "VisitIn")["properties"].pop(
        "note"
    ),
    "request-enum-value-removed": lambda d: schema(d, "VisitIn")["properties"]["kind"][
        "enum"
    ].remove("phone"),
    "request-property-type-changed": lambda d: schema(d, "VisitIn")["properties"]["title"].update(
        type="integer"
    ),
    "request-nullable-removed": lambda d: schema(d, "VisitIn")["properties"].update(
        note={"type": "string"}
    ),
    "required-body-added": body_on_get,
    "response-property-removed": lambda d: schema(d, "Visit")["properties"].pop("title"),
    "nested-array-response-property-removed": lambda d: schema(d, "Note")["properties"].pop("text"),
    "response-property-made-nullable": lambda d: schema(d, "Visit")["properties"].update(
        title={"anyOf": [{"type": "string"}, {"type": "null"}]}
    ),
    "response-property-type-changed": lambda d: schema(d, "Visit")["properties"]["id"].update(
        type="string"
    ),
    "response-enum-value-added": lambda d: schema(d, "Visit")["properties"]["status"][
        "enum"
    ].append("cancelled"),
    "response-property-no-longer-required": lambda d: schema(d, "Visit")["required"].remove(
        "title"
    ),
    "success-status-removed": replace_status,
    "response-media-type-removed": lambda d: get_op(d)["responses"]["200"].update(
        content={"text/plain": {"schema": {"type": "string"}}}
    ),
}


def visit_in(doc: Document, name: str) -> dict[str, Any]:
    found: dict[str, Any] = schema(doc, "VisitIn")["properties"][name]
    return found


def visited_on(doc: Document) -> dict[str, Any]:
    found: dict[str, Any] = schema(doc, "Visit")["properties"]["visited_on"]
    return found


def rename_path_parameter(doc: Document) -> None:
    item = doc["paths"].pop(VISIT)
    item["get"]["parameters"][0]["name"] = "id"
    doc["paths"]["/api/visits/{id}"] = item


# R-01: `format` and constraint keywords, by direction (a request may widen, a response narrow).
BREAKING.update(
    {
        "response-format-changed": lambda d: visited_on(d).update(format="date-time"),
        "response-format-removed": lambda d: visited_on(d).pop("format"),
        "request-format-added": lambda d: visit_in(d, "contact").update(format="email"),
        "request-max-length-tightened": lambda d: visit_in(d, "name").update(maxLength=50),
        "request-pattern-added": lambda d: visit_in(d, "name").update(pattern="^[A-Z]"),
        "request-minimum-added": lambda d: get_op(d)["parameters"][1]["schema"].update(minimum=2),
        "request-min-length-added": lambda d: visit_in(d, "name").update(minLength=3),
        "response-max-length-removed": lambda d: schema(d, "Note")["properties"]["text"].pop(
            "maxLength"
        ),
    }
)


def changed(change: Change) -> Document:
    doc = base()
    change(doc)
    return doc


@pytest.mark.parametrize("case_id", sorted(BREAKING))
def test_eko110_k06_breaking_pairs_fail(case_id: str) -> None:
    assert oc.breaking_changes(base(), changed(BREAKING[case_id])) != [], case_id


def test_eko110_k06_breaking_change_in_a_component_counts_against_every_operation() -> None:
    found = oc.breaking_changes(base(), changed(BREAKING["response-property-removed"]))
    assert any(f"GET {VISIT}" in f for f in found) and any(f"POST {VISITS}" in f for f in found)


def reverse_keys(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: reverse_keys(node[key]) for key in reversed(list(node))}
    if isinstance(node, list):
        return [reverse_keys(item) for item in node]
    return node


def add_operation(doc: Document) -> None:
    doc["paths"]["/api/notes"] = {
        "get": {"responses": {"200": {"description": "ok", "content": json_content(ref("Note"))}}}
    }


ADDITIVE: dict[str, Change] = {
    "identical": lambda d: None,
    "operation-added": add_operation,
    "optional-body-property-added": add_body_property(required=False),
    "optional-parameter-added": add_parameter("query", False),
    "response-property-added": lambda d: schema(d, "Visit")["properties"].update(
        region={"type": "string"}
    ),
    "success-status-added": add_status,
    "request-enum-value-added": lambda d: schema(d, "VisitIn")["properties"]["kind"]["enum"].append(
        "visit"
    ),
    "key-and-operation-order": lambda d: d.update(reverse_keys(copy.deepcopy(d))),
    # R-01 contrasts: a request widening and a response narrowing break no previous client.
    "request-max-length-loosened": lambda d: visit_in(d, "name").update(maxLength=200),
    "request-max-length-removed": lambda d: visit_in(d, "name").pop("maxLength"),
    "response-format-added": lambda d: schema(d, "Visit")["properties"]["title"].update(
        format="email"
    ),
    "response-max-length-tightened": lambda d: schema(d, "Note")["properties"]["text"].update(
        maxLength=500
    ),
    # R-05: documentation text and path-parameter names are no part of the wire contract.
    "description-changed": lambda d: schema(d, "Visit").update(
        title="Visit (renamed)", description="A field visit."
    ),
    "path-parameter-renamed": rename_path_parameter,
}


def union_base() -> Document:
    """A response and a request carrying a two-model union, FastAPI's discriminated shape."""
    doc = base()
    schemas = doc["components"]["schemas"]
    schemas["Address"] = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }
    schemas["FieldVisit"] = {
        "type": "object",
        "title": "FieldVisit",
        "properties": {"kind": {"const": "field"}, "address": ref("Address")},
        "required": ["kind", "address"],
    }
    schemas["PhoneVisit"] = {
        "type": "object",
        "title": "PhoneVisit",
        "properties": {"kind": {"const": "phone"}, "number": {"type": "string"}},
        "required": ["kind", "number"],
    }
    union = {"oneOf": [ref("FieldVisit"), ref("PhoneVisit")]}
    get_op(doc)["responses"]["200"]["content"] = json_content(union)
    doc["paths"][VISITS]["post"]["requestBody"]["content"] = json_content(copy.deepcopy(union))
    return doc


def union_changed(change: Change) -> Document:
    doc = union_base()
    change(doc)
    return doc


def add_branch(where: str) -> Change:
    def apply(doc: Document) -> None:
        doc["components"]["schemas"]["EmailVisit"] = {
            "type": "object",
            "properties": {"kind": {"const": "email"}},
        }
        if where == "response":
            content = get_op(doc)["responses"]["200"]["content"]
        else:
            content = doc["paths"][VISITS]["post"]["requestBody"]["content"]
        content["application/json"]["schema"]["oneOf"].append(ref("EmailVisit"))

    return apply


def drop_request_branch(doc: Document) -> None:
    content = doc["paths"][VISITS]["post"]["requestBody"]["content"]
    content["application/json"]["schema"]["oneOf"].pop()


UNION_BREAKING: dict[str, Change] = {
    "nested-removal-through-a-branch": lambda d: schema(d, "Address")["properties"].pop("city"),
    "response-gains-a-branch": add_branch("response"),
    "request-loses-a-branch": drop_request_branch,
}
UNION_COMPATIBLE: dict[str, Change] = {
    "identical": lambda d: None,
    "optional-property-in-one-branch": lambda d: schema(d, "PhoneVisit")["properties"].update(
        extension={"type": "string"}
    ),
    "branch-description-changed": lambda d: schema(d, "FieldVisit").update(
        description="Visited on site."
    ),
    "request-gains-a-branch": add_branch("request"),
}


@pytest.mark.parametrize("case_id", sorted(UNION_BREAKING))
def test_eko110_k06_breaking_change_through_a_union_fails(case_id: str) -> None:
    found = oc.breaking_changes(union_base(), union_changed(UNION_BREAKING[case_id]))
    assert found != [], case_id


@pytest.mark.parametrize("case_id", sorted(UNION_COMPATIBLE))
def test_eko110_k06_compatible_change_through_a_union_passes(case_id: str) -> None:
    found = oc.breaking_changes(union_base(), union_changed(UNION_COMPATIBLE[case_id]))
    assert found == [], (case_id, found)


def test_eko110_k06_additive_pair_passes() -> None:
    doc = base()
    add_operation(doc)
    add_body_property(required=False)(doc)
    assert oc.breaking_changes(base(), doc) == []


@pytest.mark.parametrize("case_id", sorted(ADDITIVE))
def test_eko110_k06_compatible_pair_passes(case_id: str) -> None:
    assert oc.breaking_changes(base(), changed(ADDITIVE[case_id])) == [], case_id


def test_eko110_k06_recursive_component_terminates_and_still_compares() -> None:
    doc = base()
    schema(doc, "Note")["properties"].update(
        replies={"type": "array", "items": ref("Note")}, parent=ref("Note")
    )
    broken = copy.deepcopy(doc)
    schema(broken, "Note")["properties"].pop("text")
    assert oc.breaking_changes(doc, copy.deepcopy(doc)) == []
    assert oc.breaking_changes(doc, broken) != []


def test_eko110_k06_real_document_against_itself_and_a_removal() -> None:
    real = api.real_app().openapi()
    assert oc.breaking_changes(copy.deepcopy(real), real) == []
    previous = copy.deepcopy(real)
    previous["paths"]["/api/visits"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    assert oc.breaking_changes(previous, real) != []
    widened = copy.deepcopy(real)
    status = widened["components"]["schemas"]["HealthStatus"]["properties"]["status"]
    status["enum"] = [*status["enum"], "degraded"]
    assert oc.breaking_changes(real, widened) != []


# The command and the CI step ------------------------------------------------------------------


def run_main(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = oc.main(list(argv), out)
    return code, out.getvalue()


def ci_step() -> tuple[dict[str, Any], dict[str, Any]]:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    found = [
        (job, step)
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "tests.support.openapi_compat" in str(step.get("run", ""))
    ]
    assert len(found) == 1, "exactly one ci.yml step runs the comparison"
    return found[0]


def no_document(release: Release) -> Any:
    raise AssertionError(f"{release.tag}: no document is fetched when no release is published")


def test_eko110_k06_no_previous_release_says_compared_nothing() -> None:
    code, output = run_main()
    assert code == 0 and "compared nothing" in output and not COMPARED.search(output), output

    job, step = ci_step()
    assert "if" not in job and "if" not in step
    assert wc.failures_fail_the_run({"jobs": {"backend": job}}) == []
    # The step's own arguments against a record holding no release (EKO-1-15 C-9).
    command = shlex.split(step["run"])
    module = ["uv", "run", "python", "-m", "tests.support.openapi_compat"]
    assert command[: len(module)] == module, step["run"]
    out = io.StringIO()
    empty, reach = RecordDouble(), ReachDouble()
    code = oc.main(command[len(module) :], out, record=empty, reach=reach, served=no_document)
    assert code == 0, out.getvalue()
    assert "compared nothing" in out.getvalue() and not COMPARED.search(out.getvalue())


def test_eko110_k06_contrast_the_step_without_a_record_token_exits_2() -> None:
    _, step = ci_step()
    env = {k: v for k, v in os.environ.items() if k != wc.RECORD_TOKEN}
    result = subprocess.run(
        [bash(), "-c", step["run"]],
        cwd=REPO_ROOT / step.get("working-directory", "."),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "compared nothing" not in result.stdout


def test_eko110_k06_supplied_previous_release_reports_a_comparison(tmp_path: Path) -> None:
    previous = tmp_path / "previous.json"
    real = api.real_app().openapi()
    previous.write_text(json.dumps(real), encoding="utf-8")
    code, output = run_main("--previous", str(previous))
    assert code == 0 and COMPARED.search(output) and "compared nothing" not in output, output

    extra = copy.deepcopy(real)
    extra["paths"]["/api/visits"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    previous.write_text(json.dumps(extra), encoding="utf-8")
    code, output = run_main("--previous", str(previous))
    assert code == 1 and COMPARED.search(output) and "GET /api/visits" in output, output


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("missing", None),
        ("empty", ""),
        ("not-json", "{ not json"),
        ("array", "[]"),
        (
            "swagger-2",
            json.dumps({"swagger": "2.0", "info": {"title": "x", "version": "1"}, "paths": {}}),
        ),
        ("invalid-3x", json.dumps({"openapi": "3.1.0", "paths": {}})),
    ],
)
def test_eko110_k06_unreadable_previous_release_fails(
    tmp_path: Path, name: str, content: str | None
) -> None:
    previous = tmp_path / f"{name}.json"
    if content is not None:
        previous.write_text(content, encoding="utf-8")
    code, output = run_main("--previous", str(previous))
    assert code == 2, output
    assert "compared nothing" not in output and not COMPARED.search(output)


# No dependency (G-13 A) -----------------------------------------------------------------------


def test_eko110_k06_comparator_adds_no_dependency() -> None:
    manifest, lock = at_base("backend/pyproject.toml"), at_base("backend/uv.lock")
    manifest_now, lock_now = in_worktree("backend/pyproject.toml"), in_worktree("backend/uv.lock")
    assert manifest and lock and manifest_now and lock_now
    in_base = at_base(cc.COMPARATOR) is not None
    assert cc.package_additions((manifest, lock), (manifest_now, lock_now), in_base) == []
    tree = ast.parse(
        (REPO_ROOT / "backend/tests/support/openapi_compat.py").read_text(encoding="utf-8")
    )
    imported = {
        name.split(".")[0]
        for node in ast.walk(tree)
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
            if isinstance(node, ast.ImportFrom) and node.module
            else []
        )
    }
    assert imported - set(sys.stdlib_module_names) <= {"tests"}, imported


def with_package(manifest: str, lock: str) -> tuple[str, str]:
    added_manifest = manifest.replace(
        '    "pytest>=8.4",\n', '    "oasdiff-py>=1.0",\n    "pytest>=8.4",\n'
    )
    assert added_manifest != manifest
    return added_manifest, lock + '\n[[package]]\nname = "oasdiff-py"\nversion = "1.0.0"\n'


def test_eko110_k06_package_check_fails_on_an_added_package_in_this_change_set() -> None:
    manifest, lock = at_base("backend/pyproject.toml"), at_base("backend/uv.lock")
    assert manifest and lock
    added = with_package(manifest, lock)
    assert cc.package_additions((manifest, lock), added, comparator_in_base=False) != []
    lock_only = (manifest, added[1])
    assert cc.package_additions((manifest, lock), lock_only, comparator_in_base=False) != []
    # Once the comparator is in the base, a later task's packages are its own business (R-04).
    assert cc.package_additions((manifest, lock), added, comparator_in_base=True) == []
