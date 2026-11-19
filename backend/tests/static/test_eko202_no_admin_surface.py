"""EKO-2-02 K-06 leg 3 (ADR-0003 *Account lifecycle*: "no application endpoint creates an
account"): the composed application's OpenAPI document exposes no account-creating operation,
and no file under `backend/app/` reaches Keycloak's admin REST surface (`admin/realms`).

A 401 walk alone cannot see an account-creating route kept behind a session that calls the
admin API; these two checks can, and each is shown failing on a planted counterpart.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from tests.support.api_surface import real_app

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
# Words an operation creating or registering an account would carry in its path or identifier.
ACCOUNT_WORDS = re.compile(
    r"regist|sign-?up|enrol|user|account|member|staff|invit|admin|role", re.IGNORECASE
)
ADMIN_API = re.compile(r"admin/realms", re.IGNORECASE)
CHANGING = ("post", "put", "patch", "delete")


def account_operations(document: dict[str, Any]) -> list[str]:
    found = []
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            named = f"{path} {operation.get('operationId', '')}"
            if ACCOUNT_WORDS.search(named):
                found.append(f"{method.upper()} {path}")
    return found


def admin_api_references(files: dict[str, str]) -> list[str]:
    return sorted(name for name, text in files.items() if ADMIN_API.search(text))


def application_sources() -> dict[str, str]:
    return {
        str(p.relative_to(APP_ROOT)): p.read_text(encoding="utf-8")
        for p in APP_ROOT.rglob("*")
        if p.is_file() and p.suffix != ".pyc"
    }


def test_k06_openapi_document_exposes_no_account_operation() -> None:
    document = real_app().openapi()
    assert document["paths"], "an empty document would pass vacuously"
    assert account_operations(document) == []


def test_k06_the_only_changing_operations_are_logout_and_customer_create() -> None:
    document = real_app().openapi()
    changing = {
        f"{method.upper()} {path}"
        for path, item in document["paths"].items()
        for method in item
        if method in CHANGING
    }
    # EKO-3-01 adds customer creation (decision H6-B A on Issue #195); it creates no account.
    assert changing == {"POST /api/auth/logout", "POST /api/customers"}


def test_k06_no_application_source_calls_keycloak_admin_api() -> None:
    sources = application_sources()
    assert "auth/oidc.py" in {name.replace("\\", "/") for name in sources}
    assert admin_api_references(sources) == []


@pytest.mark.parametrize(
    "path, operation_id",
    [
        ("/api/auth/register", "register"),
        ("/api/users", "create_user"),
        ("/api/staff/{subject}", "staff_create"),
        ("/api/eko/x", "signup"),
        ("/api/accounts", "create"),
    ],
)
def test_k06_contrast_a_planted_account_operation_is_found(path: str, operation_id: str) -> None:
    app: FastAPI = real_app()

    @app.post(path, operation_id=operation_id)
    def planted() -> dict[str, bool]:
        return {"created": True}

    assert account_operations(app.openapi()) != []


@pytest.mark.parametrize(
    "text",
    [
        'URL = f"{base}/admin/realms/eko/users"\n',
        'client.post("https://auth.invalid/ADMIN/REALMS/eko/users")\n',
    ],
)
def test_k06_contrast_a_planted_admin_api_call_is_found(text: str) -> None:
    assert admin_api_references({"services/accounts.py": text}) == ["services/accounts.py"]
