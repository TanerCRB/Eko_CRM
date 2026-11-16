"""EKO-2-02 K-03 (ADR-0003 *Roles* last bullet, *Identifier the application stores*, C12): the
caller identity passed inward is a `domain` value holding the token's subject, byte for byte,
and the union of the application client's roles present in the verified token; `auth` builds it.

The shipped `create_app()` is built with its session store swapped for an in-memory one holding
one planted session whose access token the local OIDC stub signed; the probe's handler hands what
it received to a recording double standing in for a `services` entry point.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.crypto import digest, new_opaque
from app.auth.oidc import TokenSet
from app.auth.sessions import Authenticator
from app.data.sessions import SessionStore, StoredSession
from app.main import create_app
from tests.support import eko202_probe as probe
from tests.support import oidc_stub

SESSION_COOKIE = "__Host-eko_session"
APP_ROOT = Path(__file__).resolve().parents[2] / "app"
INNER_LAYERS = ("services", "domain")


@dataclass
class MemoryStore:
    """The two reads a request on an unexpired access token makes; nothing else is reached."""

    sessions: dict[str, StoredSession] = field(default_factory=dict)

    def find(self, session_hash: str) -> StoredSession | None:
        return self.sessions.get(session_hash)

    def touch(self, session_id: int, now: datetime) -> None:
        pass


@dataclass
class Harness:
    app: FastAPI
    auth: Authenticator
    store: MemoryStore
    stub: oidc_stub.Stub
    recorder: probe.Recorder
    client: TestClient

    def plant(self, sub: str, claims: dict[str, Any]) -> str:
        """A session for `sub` whose access token carries `claims`; returns its cookie."""
        self.stub.access_overrides = claims
        minted = self.stub.mint(oidc_stub.User(sub=sub), "sid-eko202", None)
        cookie = new_opaque()
        key = digest(cookie)
        tokens = TokenSet(minted["access_token"], minted["refresh_token"], minted["id_token"])
        now = datetime.now(UTC)
        self.store.sessions[key] = StoredSession(
            id=len(self.store.sessions) + 1,
            session_hash=key,
            subject=sub,
            tokens=self.auth.sealer.seal(tokens.to_bytes(), key),
            access_expires_at=now + timedelta(seconds=self.stub.access_lifespan_seconds),
            created_at=now,
            last_used_at=now,
        )
        return cookie

    def read_customers(self, cookie: str) -> int:
        answer = self.client.get(probe.CUSTOMERS, cookies={SESSION_COOKIE: cookie})
        self.client.cookies.clear()
        return int(answer.status_code)


@pytest.fixture
def harness(backend_env: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    with oidc_stub.StubServer() as stub:
        monkeypatch.setenv("APP_OIDC_ISSUER", stub.issuer)
        monkeypatch.setenv("APP_OIDC_CLIENT_SECRET", oidc_stub.CLIENT_SECRET)
        app = create_app()
        auth: Authenticator = app.state.auth
        store = MemoryStore()
        auth.store = cast(SessionStore, store)
        recorder = probe.install_probe(app)
        with TestClient(app) as client:
            yield Harness(app, auth, store, stub, recorder, client)


SUB = "4b1c2d3e-0000-4000-8000-000000000202"


def test_k03_identity_passed_inward_is_the_domain_value_with_subject_and_role_union(
    harness: Harness,
) -> None:
    from app.domain.caller import Caller, Role

    cookie = harness.plant(SUB, probe.role_claims(client=["rep", "manager"]))
    assert harness.read_customers(cookie) == 200
    [received] = harness.recorder.received
    assert type(received) is Caller
    assert type(received).__module__ == "app.domain.caller"
    assert received.subject == SUB
    assert received.roles == frozenset({Role.REP, Role.MANAGER})


@pytest.mark.parametrize(
    "claims, expected",
    [
        (probe.role_claims(client=["rep"]), {"rep"}),
        (probe.role_claims(client=["manager"]), {"manager"}),
        (probe.role_claims(client=["manager", "rep"]), {"rep", "manager"}),
        (probe.role_claims(client=["rep", "manager", "administrator"]), {"rep", "manager",
                                                                       "administrator"}),
        (probe.role_claims(client=["rep", "auditor", "Manager"]), {"rep"}),
        (probe.role_claims(client=["rep"], realm=["manager", "administrator"]), {"rep"}),
        (probe.role_claims(client=["rep"], other_clients={"account": ["manager"]}), {"rep"}),
        (probe.role_claims(client=["rep", "rep"]), {"rep"}),
    ],
    ids=["rep", "manager", "order", "three", "unknown-and-case", "realm", "other-client",
         "duplicate"],
)  # fmt: skip
def test_k03_roles_are_the_set_of_application_client_roles_only(
    harness: Harness, claims: dict[str, Any], expected: set[str]
) -> None:
    cookie = harness.plant(SUB, claims)
    assert harness.read_customers(cookie) == 200
    [received] = harness.recorder.received
    assert {str(role) for role in received.roles} == expected


@pytest.mark.parametrize(
    "sub", [SUB + " ", " " + SUB, SUB.upper(), "Subject-With-Case", "x" + SUB[1:]]
)
def test_k03_subject_is_carried_byte_exact(harness: Harness, sub: str) -> None:
    cookie = harness.plant(sub, probe.role_claims(client=["rep"]))
    assert harness.read_customers(cookie) == 200
    [received] = harness.recorder.received
    assert received.subject.encode("utf-8") == sub.encode("utf-8")
    assert (received.subject == SUB) is (sub == SUB)


@pytest.mark.parametrize(
    "claims",
    [
        probe.role_claims(realm=["rep", "manager", "administrator"]),
        probe.role_claims(client="manager"),
        probe.role_claims(client=[]),
        probe.role_claims(),
    ],
    ids=["realm-only", "string-claim", "empty", "absent"],
)
def test_k03_no_application_role_builds_an_empty_role_set_and_nothing_crosses_inward(
    harness: Harness, claims: dict[str, Any]
) -> None:
    cookie = harness.plant(SUB, claims)
    # The value `auth` builds, read where it is built ...
    built = harness.auth.authenticate(cookie)
    assert built.subject == SUB
    assert built.roles == frozenset()
    # ... and refused before any inner entry point receives it.
    assert harness.read_customers(cookie) == 403
    assert harness.recorder.received == []


def test_k03_missing_subject_is_refused_and_no_identity_is_built(harness: Harness) -> None:
    cookie = harness.plant(SUB, {**probe.role_claims(client=["rep"]), "sub": None})
    assert harness.read_customers(cookie) == 401
    assert harness.recorder.received == []


TOKEN_WORDS = re.compile(r"jwt|jose|id_token|access_token", re.IGNORECASE)


def test_k03_c12_token_grep_over_services_and_domain_is_empty() -> None:
    """The C12 command `grep -rli -e jwt -e jose -e id_token -e access_token` over both layers."""
    files = [p for layer in INNER_LAYERS for p in (APP_ROOT / layer).rglob("*") if p.is_file()]
    assert any(p.name == "caller.py" for p in files)
    named = [
        str(p.relative_to(APP_ROOT))
        for p in files
        if p.suffix != ".pyc" and TOKEN_WORDS.search(p.read_text(encoding="utf-8"))
    ]
    assert named == []


def test_k03_domain_caller_module_imports_nothing_from_auth_or_a_token_library() -> None:
    tree = ast.parse((APP_ROOT / "domain" / "caller.py").read_text(encoding="utf-8"))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
         for alias in node.names}  # fmt: skip
    assert not {m for m in imported if m.startswith(("app.auth", "app.api", "jwt", "jose"))}
