"""A local OpenID Connect provider standing in for Keycloak in the EKO-2-01 backend carriers.

It holds its own test-generated RSA signing keys and serves the Keycloak paths the backend uses
under `/realms/<realm>/protocol/openid-connect/`: `auth`, `token`, `certs` and `logout`. The token
endpoint answers, refuses (an OAuth `invalid_grant`), fails (HTTP 500) or accepts the request and
never answers until released, per grant type. Refresh-token rotation is on, as in the realm
(`revokeRefreshToken` true, `refreshTokenMaxReuse` 0): a superseded refresh token is refused and
recorded. Every value is synthetic (ADR-0005).
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

REALM = "eko"
CLIENT_ID = "eko-backend"
CLIENT_SECRET = "synthetic-oidc-client-secret-201"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    numbers = key.public_key().public_numbers()
    return {
        "kid": kid,
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64(numbers.n),
        "e": _b64(numbers.e),
    }


@dataclass
class User:
    sub: str = "4b1c2d3e-0000-4000-8000-000000000201"
    given_name: str = "Synthetic"
    family_name: str = "Rep"


@dataclass
class SsoSession:
    sid: str
    user: User
    current_refresh: str
    ended: bool = False
    old: list[str] = field(default_factory=list)


@dataclass
class Code:
    user: User
    nonce: str | None
    challenge: str | None
    method: str | None
    redirect_uri: str
    used: bool = False


@dataclass
class TokenCall:
    grant_type: str
    sid: str | None
    superseded: bool
    started: float
    finished: float | None = None


@dataclass
class Stub:
    """The provider's state; tests change the public fields between requests."""

    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    access_lifespan_seconds: int = 240
    signing_key: rsa.RSAPrivateKey = field(default_factory=new_key)
    kid: str = "stub-key-1"
    published: list[dict[str, str]] = field(default_factory=list)
    # "answer", "refuse", "error" or "hang", per grant type.
    code_mode: str = "answer"
    refresh_mode: str = "answer"
    logout_mode: str = "answer"
    # Seconds an answering refresh waits before it answers.
    refresh_delay_seconds: float = 0.0
    # Overrides of the issued tokens' claims, and claims added to them.
    access_overrides: dict[str, Any] = field(default_factory=dict)
    id_overrides: dict[str, Any] = field(default_factory=dict)
    next_user: User = field(default_factory=User)
    authorize_requests: list[dict[str, str]] = field(default_factory=list)
    token_calls: list[TokenCall] = field(default_factory=list)
    logout_calls: list[str] = field(default_factory=list)
    # Every token string the stub issued, so a test can look for it where it must not be.
    issued: list[str] = field(default_factory=list)
    sessions: dict[str, SsoSession] = field(default_factory=dict)
    codes: dict[str, Code] = field(default_factory=dict)
    release: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    base_url: str = ""

    def __post_init__(self) -> None:
        if not self.published:
            self.published = [public_jwk(self.signing_key, self.kid)]

    @property
    def issuer(self) -> str:
        return f"{self.base_url}/realms/{REALM}"

    def refreshes(self, sid: str | None = None) -> list[TokenCall]:
        with self.lock:
            return [
                c for c in self.token_calls
                if c.grant_type == "refresh_token" and (sid is None or c.sid == sid)
            ]

    def superseded_uses(self) -> list[TokenCall]:
        with self.lock:
            return [c for c in self.token_calls if c.superseded]

    def sso_alive(self, sid: str) -> bool:
        with self.lock:
            session = self.sessions.get(sid)
            return session is not None and not session.ended

    # Token minting ---------------------------------------------------------------------------

    def _sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid": self.kid})

    def _common(self, user: User, sid: str) -> dict[str, Any]:
        issued = int(self.now().timestamp())
        return {
            "iss": self.issuer,
            "sub": user.sub,
            "iat": issued,
            "exp": issued + self.access_lifespan_seconds,
            "sid": sid,
            "azp": CLIENT_ID,
            "given_name": user.given_name,
            "family_name": user.family_name,
            "name": f"{user.given_name} {user.family_name}",
        }

    def mint(self, user: User, sid: str, nonce: str | None) -> dict[str, Any]:
        access = {**self._common(user, sid), "aud": [CLIENT_ID], "typ": "Bearer",
                  "jti": secrets.token_hex(8), **self.access_overrides}  # fmt: skip
        id_claims = {**self._common(user, sid), "aud": CLIENT_ID, "typ": "ID",
                     **({"nonce": nonce} if nonce is not None else {}),
                     **self.id_overrides}  # fmt: skip
        tokens = {
            "access_token": self._sign({k: v for k, v in access.items() if v is not None}),
            "id_token": self._sign({k: v for k, v in id_claims.items() if v is not None}),
            "refresh_token": "stub-refresh-" + secrets.token_urlsafe(24),
        }
        self.issued.extend(tokens.values())
        return {
            **tokens,
            "token_type": "Bearer",
            "expires_in": self.access_lifespan_seconds,
        }


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _handler(stub: Stub) -> type[BaseHTTPRequestHandler]:
    prefix = f"/realms/{REALM}/protocol/openid-connect"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send(
            self, status: int, body: Any = None, headers: dict[str, str] | None = None
        ) -> None:
            data = b"" if body is None else json.dumps(body).encode("utf-8")
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _hang(self) -> None:
            # Accepts the request and never answers until the test releases it.
            stub.release.wait(timeout=120)
            self.close_connection = True

        def do_GET(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            if parsed.path == f"{prefix}/certs":
                with stub.lock:
                    keys = list(stub.published)
                self._send(200, {"keys": keys})
            elif parsed.path == f"{prefix}/auth":
                with stub.lock:
                    stub.authorize_requests.append(query)
                    code = secrets.token_urlsafe(16)
                    stub.codes[code] = Code(
                        user=stub.next_user,
                        nonce=query.get("nonce"),
                        challenge=query.get("code_challenge"),
                        method=query.get("code_challenge_method"),
                        redirect_uri=query.get("redirect_uri", ""),
                    )
                target = query.get("redirect_uri", "") + "?" + urllib.parse.urlencode(
                    {"code": code, "state": query.get("state", ""), "iss": stub.issuer}
                )
                self._send(302, headers={"Location": target})
            else:
                self._send(404, {"error": "not_found"})

        def _form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("ascii")
            return dict(urllib.parse.parse_qsl(raw))

        def _client_ok(self, form: dict[str, str]) -> bool:
            basic = self.headers.get("Authorization", "")
            if basic.startswith("Basic "):
                decoded = base64.b64decode(basic[6:]).decode("utf-8")
                given_id, _, given_secret = decoded.partition(":")
                given_id = urllib.parse.unquote_plus(given_id)
                given_secret = urllib.parse.unquote_plus(given_secret)
            else:
                given_id, given_secret = form.get("client_id", ""), form.get("client_secret", "")
            return given_id == CLIENT_ID and given_secret == CLIENT_SECRET

        def do_POST(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            form = self._form()
            if parsed.path == f"{prefix}/token":
                self._token(form)
            elif parsed.path == f"{prefix}/logout":
                self._logout(form)
            else:
                self._send(404, {"error": "not_found"})

        def _token(self, form: dict[str, str]) -> None:
            grant = form.get("grant_type", "")
            call = TokenCall(grant, None, False, time.monotonic())
            with stub.lock:
                stub.token_calls.append(call)
            if not self._client_ok(form):
                self._send(401, {"error": "unauthorized_client"})
                return
            mode = stub.code_mode if grant == "authorization_code" else stub.refresh_mode
            if grant == "refresh_token":
                with stub.lock:
                    token = form.get("refresh_token", "")
                    owner = next(
                        (s for s in stub.sessions.values() if token == s.current_refresh), None
                    )
                    stale = next(
                        (s for s in stub.sessions.values() if token in s.old),
                        None,
                    )
                    found = owner or stale
                    call.sid = found.sid if found is not None else None
                    call.superseded = owner is None and stale is not None
            if mode == "hang":
                self._hang()
                return
            if mode == "error":
                self._send(500, {"error": "server_error"})
                return
            if mode == "refuse":
                self._send(400, {"error": "invalid_grant"})
                return
            if grant == "authorization_code":
                self._exchange(form)
            elif grant == "refresh_token":
                if stub.refresh_delay_seconds:
                    time.sleep(stub.refresh_delay_seconds)
                self._refresh(form, call)
            else:
                self._send(400, {"error": "unsupported_grant_type"})
            call.finished = time.monotonic()

        def _exchange(self, form: dict[str, str]) -> None:
            with stub.lock:
                code = stub.codes.get(form.get("code", ""))
                if code is None or code.used or code.redirect_uri != form.get("redirect_uri"):
                    self._send(400, {"error": "invalid_grant"})
                    return
                code.used = True
                verifier = form.get("code_verifier", "")
                if code.method != "S256" or code.challenge != _challenge(verifier):
                    self._send(400, {"error": "invalid_grant"})
                    return
                sid = secrets.token_hex(8)
                issued = stub.mint(code.user, sid, code.nonce)
                stub.sessions[sid] = SsoSession(sid, code.user, issued["refresh_token"])
            self._send(200, issued)

        def _refresh(self, form: dict[str, str], call: TokenCall) -> None:
            with stub.lock:
                token = form.get("refresh_token", "")
                session = next(
                    (s for s in stub.sessions.values() if s.current_refresh == token), None
                )
                if session is None or session.ended:
                    self._send(400, {"error": "invalid_grant"})
                    return
                issued = stub.mint(session.user, session.sid, None)
                session.old.append(token)
                session.current_refresh = issued["refresh_token"]
            self._send(200, issued)

        def _logout(self, form: dict[str, str]) -> None:
            if not self._client_ok(form):
                self._send(401, {"error": "unauthorized_client"})
                return
            if stub.logout_mode == "hang":
                self._hang()
                return
            if stub.logout_mode == "error":
                self._send(500, {"error": "server_error"})
                return
            with stub.lock:
                token = form.get("refresh_token", "")
                stub.logout_calls.append(token)
                session = next(
                    (s for s in stub.sessions.values() if s.current_refresh == token), None
                )
                if session is None or session.ended:
                    self._send(400, {"error": "invalid_grant"})
                    return
                session.ended = True
            self._send(204)

    return Handler


class _Server(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        # A client closing its kept-alive connection is not a stub failure; nothing is printed.
        pass


class StubServer:
    """The stub on a free local port, served from daemon threads."""

    def __init__(self, stub: Stub | None = None) -> None:
        self.stub = stub or Stub()
        self.server = _Server(("127.0.0.1", 0), _handler(self.stub))
        self.server.daemon_threads = True
        self.stub.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> Stub:
        self.thread.start()
        return self.stub

    def __exit__(self, *exc: object) -> None:
        self.stub.release.set()
        self.server.shutdown()
        self.server.server_close()
