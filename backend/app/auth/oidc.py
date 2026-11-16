"""The backend's OpenID Connect client of Keycloak (ADR-0003 *Browser flow*, *How a request is
verified*; Keycloak is the identity server, not an integration, so this lives in `auth`).

Keycloak's fixed endpoint paths under the realm are used, so building the application needs no
call to Keycloak. Browser-facing URLs use the public issuer; the backend's own calls (token,
keys, logout) go to the internal base URL, which defaults to the issuer. Every call is bounded by
a five-second timeout. Nothing here logs a token, code, state, nonce, verifier or secret.
"""

import json
import logging
import re
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt

from app.core.clock import Clock
from app.core.settings import AuthSettings
from app.domain.caller import Role

logger = logging.getLogger(__name__)

CALL_TIMEOUT_SECONDS = 5.0
_PROTOCOL = "/protocol/openid-connect"
# A token carrying either is never stored (ADR-0003 *Browser flow*, ADR-0003-C20).
FORBIDDEN_CLAIMS = ("email", "preferred_username")
# The key set is fetched at most this often, a failed attempt included (Reviewer R-01).
_REFETCH_SECONDS = 10.0
# The only OAuth error that means the user's grant was refused; any other code is the backend's
# own fault (a wrong client secret) or Keycloak's, never the session's (Reviewer R-02).
REFUSAL_CODE = "invalid_grant"
_ERROR_CODE = re.compile(r"[a-z_]{1,64}")


class IdentityRefused(Exception):
    """Keycloak answered with an OAuth error (for example `invalid_grant`)."""


class IdentityUnavailable(Exception):
    """Keycloak could not be reached, timed out, failed, or answered something unusable."""


class TokenInvalid(Exception):
    """Signature, issuer, audience, type, time or claim set refused."""


class TokenExpired(Exception):
    """A token that is otherwise valid has reached its `exp`."""


@dataclass(frozen=True)
class TokenSet:
    access: str
    refresh: str
    id: str | None

    def to_bytes(self) -> bytes:
        return json.dumps({"a": self.access, "r": self.refresh, "i": self.id}).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "TokenSet":
        loaded = json.loads(raw)
        return cls(loaded["a"], loaded["r"], loaded["i"])


@dataclass(frozen=True)
class VerifiedAccess:
    subject: str
    name: str | None
    expires_at: datetime
    roles: frozenset[Role]


def client_roles(claims: dict[str, Any], client_id: str) -> frozenset[Role]:
    """The application's roles named in this client's role claim, `resource_access.<client>.roles`
    (ADR-0003 *Roles*). Realm roles, other clients' roles and unknown names are ignored; a name
    matches only exactly, and a claim of any other shape grants nothing."""
    resource = claims.get("resource_access")
    entry = resource.get(client_id) if isinstance(resource, dict) else None
    listed = entry.get("roles") if isinstance(entry, dict) else None
    if not isinstance(listed, list):
        return frozenset()
    names = {role.value for role in Role}
    return frozenset(Role(name) for name in listed if isinstance(name, str) and name in names)


def http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(CALL_TIMEOUT_SECONDS), follow_redirects=False)


def _unverified_claims(token: str) -> dict[str, Any] | None:
    try:
        claims: dict[str, Any] = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return None
    return claims


def carries_forbidden_claim(tokens: TokenSet) -> bool:
    """Read from every token's payload, the refresh token's included when it is a JWT."""
    for token in (tokens.access, tokens.refresh, tokens.id):
        claims = _unverified_claims(token) if token else None
        if claims is not None and any(name in claims for name in FORBIDDEN_CLAIMS):
            return True
    return False


class OidcClient:
    def __init__(self, settings: AuthSettings, http: httpx.Client) -> None:
        self.issuer = settings.app_oidc_issuer
        self._internal = settings.app_oidc_internal_url or settings.app_oidc_issuer
        self.client_id = settings.app_oidc_client_id
        self._secret = settings.app_oidc_client_secret
        self.redirect_uri = f"{settings.app_origin}/api/auth/callback"
        self._leeway = settings.app_oidc_clock_skew_leeway_seconds
        self._http = http
        self._keys: dict[str, Any] = {}
        self._keys_lock = threading.Lock()
        self._attempted_at: float | None = None
        self._last_attempt_failed = False
        self._fetching: threading.Event | None = None

    # Calls -------------------------------------------------------------------------------------

    def authorization_url(self, state: str, nonce: str, challenge: str) -> str:
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "openid",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.issuer}{_PROTOCOL}/auth?{query}"

    def _post(self, path: str, form: dict[str, str], expected: int) -> dict[str, Any]:
        credentials = {
            "client_id": self.client_id,
            "client_secret": self._secret.get_secret_value(),
        }
        try:
            answer = self._http.post(
                f"{self._internal}{_PROTOCOL}{path}", data={**form, **credentials}
            )
        except httpx.HTTPError as exc:
            logger.warning("identity server unreachable: %s", type(exc).__name__)
            raise IdentityUnavailable from None
        if answer.status_code >= 500:
            logger.warning("identity server failed: status %s", answer.status_code)
            raise IdentityUnavailable
        body: Any = None
        if answer.content:
            try:
                body = answer.json()
            except ValueError:
                body = None
        if answer.status_code in (400, 401) and isinstance(body, dict):
            code = body.get("error")
            if code == REFUSAL_CODE:
                raise IdentityRefused
            if isinstance(code, str):
                named = code if _ERROR_CODE.fullmatch(code) else "unrecognised"
                logger.warning("identity server rejected the backend's request: %s", named)
                raise IdentityUnavailable
        if answer.status_code != expected:
            logger.warning("identity server answered status %s", answer.status_code)
            raise IdentityUnavailable
        return body if isinstance(body, dict) else {}

    def _tokens(self, body: dict[str, Any]) -> TokenSet:
        access, refresh, id_token = (
            body.get(name) for name in ("access_token", "refresh_token", "id_token")
        )
        if not isinstance(access, str) or not isinstance(refresh, str):
            logger.warning("identity server answer holds no usable tokens")
            raise IdentityUnavailable
        return TokenSet(access, refresh, id_token if isinstance(id_token, str) else None)

    def exchange_code(self, code: str, verifier: str) -> TokenSet:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": verifier,
        }
        return self._tokens(self._post("/token", form, 200))

    def refresh(self, refresh_token: str) -> TokenSet:
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        return self._tokens(self._post("/token", form, 200))

    def end_session(self, refresh_token: str) -> None:
        """Ends the Keycloak SSO session the refresh token belongs to (G-2 A)."""
        self._post("/logout", {"refresh_token": refresh_token}, 204)

    # Verification ------------------------------------------------------------------------------

    def _fetch_keys(self, timeout: float) -> dict[str, Any]:
        try:
            answer = self._http.get(f"{self._internal}{_PROTOCOL}/certs", timeout=timeout)
            answer.raise_for_status()
            listed = answer.json().get("keys", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("identity server keys unavailable: %s", type(exc).__name__)
            raise IdentityUnavailable from None
        keys = {}
        for entry in listed if isinstance(listed, list) else []:
            if not isinstance(entry, dict) or entry.get("kty") != "RSA":
                continue
            if entry.get("use", "sig") != "sig" or not isinstance(entry.get("kid"), str):
                continue
            try:
                keys[entry["kid"]] = jwt.PyJWK(entry, algorithm="RS256").key
            except jwt.PyJWKError:
                continue
        return keys

    def _key(self, kid: object, clock: Clock, deadline: float) -> Any:
        """The key for `kid`: a cached key needs no lock; otherwise one fetch is in flight for
        every request, and a request waits for it no longer than its own deadline."""
        if not isinstance(kid, str):
            raise TokenInvalid
        cached = self._keys.get(kid)
        if cached is not None:
            return cached
        while True:
            with self._keys_lock:
                cached = self._keys.get(kid)
                if cached is not None:
                    return cached
                pending = self._fetching
                if pending is None:
                    now = clock.monotonic()
                    last = self._attempted_at
                    if last is not None and now - last < _REFETCH_SECONDS:
                        # Within the interval the last attempt's outcome stands.
                        if self._last_attempt_failed:
                            raise IdentityUnavailable
                        raise TokenInvalid
                    self._attempted_at = now
                    self._fetching = threading.Event()
            if pending is None:
                return self._fetch_for(kid, clock, deadline)
            remaining = deadline - clock.monotonic()
            if remaining <= 0 or not pending.wait(remaining):
                raise IdentityUnavailable

    def _fetch_for(self, kid: str, clock: Clock, deadline: float) -> Any:
        fetched: dict[str, Any] | None = None
        try:
            timeout = max(0.1, min(CALL_TIMEOUT_SECONDS, deadline - clock.monotonic()))
            fetched = self._fetch_keys(timeout)
        finally:
            with self._keys_lock:
                if fetched is not None:
                    self._keys = fetched
                self._last_attempt_failed = fetched is None
                done, self._fetching = self._fetching, None
            if done is not None:
                done.set()
        key = self._keys.get(kid)
        if key is None:
            raise TokenInvalid
        return key

    def _claims(self, token: str, kind: str, clock: Clock) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise TokenInvalid from None
        if header.get("alg") != "RS256":
            raise TokenInvalid
        key = self._key(header.get("kid"), clock, clock.monotonic() + CALL_TIMEOUT_SECONDS)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "require": ["iss", "aud", "sub", "exp", "iat"],
                },
            )
        except jwt.InvalidTokenError:
            raise TokenInvalid from None
        if claims.get("typ") != kind or not isinstance(claims.get("sub"), str):
            raise TokenInvalid
        if "azp" in claims and claims["azp"] != self.client_id:
            raise TokenInvalid
        if any(name in claims for name in FORBIDDEN_CLAIMS):
            raise TokenInvalid
        now = clock.now().timestamp()
        times = [claims.get(name) for name in ("exp", "iat", "nbf")]
        if not all(value is None or isinstance(value, int | float) for value in times):
            raise TokenInvalid
        if claims["iat"] > now + self._leeway or claims.get("nbf", 0) > now + self._leeway:
            raise TokenInvalid
        # Strict: no leeway on expiry, so no request is served on an expired token.
        if claims["exp"] <= now:
            raise TokenExpired
        return claims

    def verify_access(self, token: str, clock: Clock) -> VerifiedAccess:
        claims = self._claims(token, "Bearer", clock)
        name = claims.get("name")
        return VerifiedAccess(
            subject=claims["sub"],
            name=name if isinstance(name, str) else None,
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
            roles=client_roles(claims, self.client_id),
        )

    def verify_id(self, token: str | None, clock: Clock) -> dict[str, Any]:
        if token is None:
            raise TokenInvalid
        return self._claims(token, "ID", clock)
