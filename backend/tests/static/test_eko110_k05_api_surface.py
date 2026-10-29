"""EKO-1-10 K-05: no credential-shaped request input, no e-mail from a route, Pydantic responses.

ADR-0001-C6 (OpenAPI half) and ADR-0003-C9 as restated 2026-10-29; checklist rule 9. Every check
runs on the application `create_app()` builds, and on fixture applications or documents.
"""

import copy
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Cookie, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tests.support import api_surface as api
from tests.support import source_checks as sc

Document = dict[str, Any]


class Out(BaseModel):
    ok: bool


def credential_problems(document: Document) -> list[str]:
    return api.credential_body_properties(document) + api.credential_parameters(document)


# Request bodies --------------------------------------------------------------------------------


class NewPasswordIn(BaseModel):
    new_password: str


class DisplayNameIn(BaseModel):
    display_name: str


def body_app(field: str) -> FastAPI:
    app = FastAPI()
    if field == "new_password":

        @app.post("/api/change")
        def change(body: NewPasswordIn) -> Out:
            return Out(ok=True)

    else:

        @app.post("/api/change")
        def rename(body: DisplayNameIn) -> Out:
            return Out(ok=True)

    return app


def test_eko110_k05_no_credential_property_in_request_bodies() -> None:
    assert api.credential_body_properties(api.real_app().openapi()) == []
    assert api.credential_body_properties(body_app("new_password").openapi()) != []
    assert api.credential_body_properties(body_app("display_name").openapi()) == []


def form_document(
    properties: dict[str, Any], media: str = "application/x-www-form-urlencoded"
) -> Document:
    """The shape FastAPI gives an OAuth2 password form: a form body behind a `$ref`."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "fixture", "version": "1"},
        "paths": {
            "/api/token": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {media: {"schema": {"$ref": "#/components/schemas/Body_token"}}},
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {"schemas": {"Body_token": {"type": "object", "properties": properties}}},
    }


STRING = {"type": "string"}
OAUTH2_FORM = {"grant_type": STRING, "username": STRING, "password": STRING}


@pytest.mark.parametrize(
    "document",
    [
        form_document(OAUTH2_FORM),
        form_document({"username": STRING}),
        form_document({"grant_type": STRING}),
        form_document({"Password": STRING}),
        form_document({"PASSWORD": STRING}),
        form_document({"Username": STRING}),
        form_document({"x_password_hint": STRING}),
        form_document({"password": STRING}, "multipart/form-data"),
        form_document({"password": STRING}, "application/json"),
        form_document({"credentials": {"type": "object", "properties": {"password": STRING}}}),
        form_document(
            {
                "accounts": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"password": STRING}},
                }
            }
        ),
        form_document(
            {
                "x": {
                    "anyOf": [
                        {"type": "object", "properties": {"username": STRING}},
                        {"type": "null"},
                    ]
                }
            }
        ),
    ],
    ids=[
        "oauth2-form",
        "username",
        "grant-type",
        "Password",
        "PASSWORD",
        "Username",
        "contains",
        "multipart",
        "json",
        "nested-object",
        "array-items",
        "nullable-object",
    ],
)
def test_eko110_k05_credential_property_fails(document: Document) -> None:
    assert api.credential_body_properties(document) != []


def test_eko110_k05_credential_property_behind_a_request_body_ref_fails() -> None:
    document = form_document(OAUTH2_FORM)
    body = document["paths"]["/api/token"]["post"].pop("requestBody")
    document["components"]["requestBodies"] = {"Token": body}
    document["paths"]["/api/token"]["post"]["requestBody"] = {
        "$ref": "#/components/requestBodies/Token"
    }
    assert api.credential_body_properties(document) != []


def test_eko110_k05_credential_property_contrast_passes() -> None:
    assert credential_problems(form_document({"code": STRING, "state": STRING})) == []


# Parameters (G-6 A) ----------------------------------------------------------------------------


def parameter_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/query")
    def query(password: str) -> Out:
        return Out(ok=True)

    return app


def test_eko110_k05_no_credential_parameter() -> None:
    assert api.credential_parameters(api.real_app().openapi()) == []
    assert api.credential_parameters(parameter_app().openapi()) != []

    app = FastAPI()

    @app.get("/api/page")
    def page(page: int) -> Out:
        return Out(ok=True)

    assert api.credential_parameters(app.openapi()) == []


def test_eko110_k05_credential_header_cookie_and_path_parameters_fail() -> None:
    header, cookie, path = FastAPI(), FastAPI(), FastAPI()

    @header.get("/api/h")
    def h(x_password: Annotated[str, Header()]) -> Out:
        return Out(ok=True)

    @cookie.get("/api/c")
    def c(username: Annotated[str | None, Cookie()] = None) -> Out:
        return Out(ok=True)

    @path.get("/api/p/{password}")
    def p(password: str) -> Out:
        return Out(ok=True)

    for app in (header, cookie, path):
        assert api.credential_parameters(app.openapi()) != []


@pytest.mark.parametrize("name", ["PASSWORD", "Grant_Type", "USERNAME"])
def test_eko110_k05_credential_parameter_any_case_fails(name: str) -> None:
    document = copy.deepcopy(parameter_app().openapi())
    document["paths"]["/api/query"]["get"]["parameters"][0]["name"] = name
    assert api.credential_parameters(document) != []


def test_eko110_k05_credential_parameter_behind_a_ref_and_at_path_level_fails() -> None:
    document = form_document({"code": STRING})
    document["components"]["parameters"] = {
        "Pw": {"name": "password", "in": "query", "schema": STRING}
    }
    document["paths"]["/api/token"]["parameters"] = [{"$ref": "#/components/parameters/Pw"}]
    assert api.credential_parameters(document) != []


# E-mail ----------------------------------------------------------------------------------------

ROUTE_CALLING_SERVICE = (
    "from app.services.notify import send_welcome\n\n\n"
    '@router.post("/api/contacts")\n'
    "def create() -> Out:\n    send_welcome()\n    return Out(ok=True)\n"
)


@pytest.mark.parametrize(
    "files",
    [
        {"backend/app/api/notify.py": "import smtplib\n"},
        {"backend/app/api/notify.py": "import aiosmtplib\n"},
        {"backend/app/api/notify.py": "from fastapi_mail import FastMail\n"},
        {"backend/app/api/notify.py": "server = SMTP('mail.example.com')\n"},
        {
            "backend/app/api/contacts.py": ROUTE_CALLING_SERVICE,
            "backend/app/services/notify.py": "from email.message import EmailMessage\n",
        },
        {"backend/app/services/notify.py": "def send_email(to: str) -> None: ...\n"},
        {"backend/app/services/fixtures/notify.py": "import smtplib\n"},
    ],
    ids=[
        "smtplib",
        "aiosmtplib",
        "fastapi-mail",
        "smtp-class",
        "through-services",
        "send-email",
        "fixtures",
    ],
)
def test_eko110_k05_sending_email_fails(files: dict[str, str]) -> None:
    assert sc.email_senders(files) != []


def test_eko110_k05_no_route_sends_email() -> None:
    assert sc.email_senders(sc.repository_sources()) == []
    validating = (
        "from pydantic import BaseModel, EmailStr\n\n\n"
        "class ContactIn(BaseModel):\n    email: EmailStr\n"
    )
    assert sc.email_senders({"backend/app/api/contacts.py": validating}) == []


# Checklist rule 9 ------------------------------------------------------------------------------


def test_eko110_k05_every_route_declares_a_pydantic_response() -> None:
    app = api.real_app()
    assert {"GET /api/health", "HEAD /api/health"} <= set(api.judged_routes(app))
    assert api.route_response_problems(app) == []


def rule9_app(kind: str) -> FastAPI:
    app = FastAPI()
    if kind == "dict":

        @app.get("/api/x")
        def x() -> dict:  # type: ignore[type-arg]  # the bare `dict` is the fixture's violation
            return {}

    elif kind == "dict-any":

        @app.get("/api/x")
        def x2() -> dict[str, Any]:
            return {}

    elif kind == "any":

        @app.get("/api/x")
        def x3() -> Any:
            return {}

    elif kind == "json-response":

        @app.get("/api/x")
        def x4() -> JSONResponse:
            return JSONResponse({})

    elif kind == "no-annotation":
        app.add_api_route("/api/x", lambda: {})
    elif kind == "hidden":

        @app.get("/api/x", include_in_schema=False)
        def x5() -> dict[str, Any]:
            return {}

    elif kind == "included-router":
        router = APIRouter()

        @router.get("/x")
        def x8() -> dict[str, Any]:
            return {}

        nested = APIRouter()
        nested.include_router(router, prefix="/v1")
        app.include_router(nested, prefix="/api")
    elif kind == "starlette-route":
        app.add_route("/api/x", lambda request: JSONResponse({}))
    elif kind == "model":

        @app.get("/api/x")
        def x6() -> Out:
            return Out(ok=True)

    elif kind == "json-response-with-model":

        @app.get("/api/x", response_model=Out)
        def x7() -> JSONResponse:
            return JSONResponse({"ok": True})

    return app


@pytest.mark.parametrize(
    "kind",
    [
        "dict",
        "dict-any",
        "any",
        "json-response",
        "no-annotation",
        "hidden",
        "included-router",
        "starlette-route",
    ],
)
def test_eko110_k05_route_without_a_pydantic_response_fails(kind: str) -> None:
    assert api.route_response_problems(rule9_app(kind)) != [], kind


@pytest.mark.parametrize("kind", ["model", "json-response-with-model"])
def test_eko110_k05_route_with_a_pydantic_response_passes(kind: str) -> None:
    app = rule9_app(kind)
    assert "GET /api/x" in api.judged_routes(app)
    assert api.route_response_problems(app) == []
