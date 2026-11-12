"""Login, per-request session verification with serialised refresh, and logout (ADR-0003 *Browser
flow*, *How a request is verified*, addendum of 2026-11-02: G-1 A, G-2 A, G-5 A; ADR-0002 addendum
of 2026-11-02, G-6 A).

Outcomes are typed: `Unauthenticated` (401), `Unavailable` (503), `LoginRefused` (a callback that
creates no session). Refused refresh deletes the session; an unreachable, hanging or failing
identity server, or a pool checkout that times out, keeps it.
"""

import hmac
import logging
from dataclasses import dataclass, field

from app.auth.crypto import (
    SealBroken,
    Sealer,
    digest,
    is_opaque,
    new_opaque,
    new_verifier,
    pkce_challenge,
)
from app.auth.oidc import (
    IdentityRefused,
    IdentityUnavailable,
    OidcClient,
    TokenExpired,
    TokenInvalid,
    TokenSet,
    VerifiedAccess,
    carries_forbidden_claim,
)
from app.core.clock import Clock
from app.data.database import POOL_TIMEOUT_SECONDS
from app.data.sessions import RefreshHolder, SessionStore, StorageUnavailable, StoredSession
from app.domain.caller import Caller
from app.domain.session_policy import SessionTimes, login_transaction_valid_at

logger = logging.getLogger(__name__)

# A request waits for another request's refresh at most this long (ADR-0003).
WAIT_BOUND_SECONDS = 5.0
PROBE_INTERVAL_SECONDS = 0.1
# A probe is not started unless its checkout and query can end inside the wait bound.
_PROBE_BUDGET_SECONDS = PROBE_INTERVAL_SECONDS + POOL_TIMEOUT_SECONDS + 0.1
_RETURN_LIMIT = 2048


class Unauthenticated(Exception):
    """No session, or one that cannot be resolved, verified or renewed: HTTP 401."""


class Unavailable(Exception):
    """The session may be fine, but it cannot be verified or renewed now: HTTP 503."""


class LoginRefused(Exception):
    """A login callback that creates no session."""


@dataclass(frozen=True)
class LoginStart:
    transaction: str
    location: str


@dataclass(frozen=True)
class LoginDone:
    session: str
    return_to: str


def safe_return_to(value: str | None) -> str:
    """A path of the single-page application on this origin, or `/`."""
    if (
        not value
        or len(value) > _RETURN_LIMIT
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)
        or value == "/api"
        or value.startswith("/api/")
    ):
        return "/"
    return value


@dataclass
class Authenticator:
    origin: str
    store: SessionStore
    oidc: OidcClient
    sealer: Sealer
    clock: Clock
    public_routes: tuple[object, ...] = field(default=())

    # Sealing -----------------------------------------------------------------------------------

    def _open(self, session: StoredSession) -> TokenSet:
        try:
            return TokenSet.from_bytes(self.sealer.open(session.tokens, session.session_hash))
        except SealBroken:
            logger.warning("stored session tokens do not open; the session is deleted")
            self.store.delete(session.id)
            raise Unauthenticated from None

    # Login -------------------------------------------------------------------------------------

    def start_login(self, return_to: str | None) -> LoginStart:
        transaction, state, nonce = new_opaque(), new_opaque(), new_opaque()
        verifier = new_verifier()
        key = digest(transaction)
        self.store.add_transaction(
            key,
            digest(state),
            digest(nonce),
            self.sealer.seal(verifier.encode("ascii"), key),
            safe_return_to(return_to),
            self.clock.now(),
        )
        location = self.oidc.authorization_url(state, nonce, pkce_challenge(verifier))
        return LoginStart(transaction, location)

    def finish_login(
        self,
        transaction: str | None,
        code: str | None,
        state: str | None,
        error: str | None,
        presented: str | None,
    ) -> LoginDone:
        if not is_opaque(transaction):
            raise LoginRefused
        key = digest(transaction or "")
        stored = self.store.take_transaction(key)
        if stored is None or not login_transaction_valid_at(stored.created_at, self.clock.now()):
            raise LoginRefused
        if error is not None or not code or not state:
            raise LoginRefused
        if not hmac.compare_digest(digest(state), stored.state_hash):
            raise LoginRefused
        try:
            verifier = self.sealer.open(stored.verifier, key).decode("ascii")
            tokens = self.oidc.exchange_code(code, verifier)
        except (SealBroken, IdentityRefused):
            raise LoginRefused from None
        except IdentityUnavailable:
            raise Unavailable from None
        try:
            id_claims = self.oidc.verify_id(tokens.id, self.clock)
            access = self.oidc.verify_access(tokens.access, self.clock)
        except (TokenInvalid, TokenExpired):
            logger.warning("tokens from the login callback failed verification")
            raise LoginRefused from None
        except IdentityUnavailable:
            raise Unavailable from None
        nonce = id_claims.get("nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(digest(nonce), stored.nonce_hash):
            raise LoginRefused
        if id_claims["sub"] != access.subject or carries_forbidden_claim(tokens):
            raise LoginRefused
        session = new_opaque()
        session_key = digest(session)
        self.store.create_session(
            session_key,
            access.subject,
            self.sealer.seal(tokens.to_bytes(), session_key),
            access.expires_at,
            self.clock.now(),
            digest(presented) if presented is not None and is_opaque(presented) else None,
        )
        return LoginDone(session, stored.return_to)

    # Every request -----------------------------------------------------------------------------

    def authenticate(self, cookie: str | None) -> Caller:
        if not is_opaque(cookie):
            raise Unauthenticated
        session = self.store.find(digest(cookie or ""))
        if session is None:
            raise Unauthenticated
        now = self.clock.now()
        if not SessionTimes(session.created_at, session.last_used_at).usable_at(now):
            self.store.delete(session.id)
            raise Unauthenticated
        if session.access_expires_at > now:
            try:
                access = self._verify(self._open(session).access)
            except TokenExpired:
                return self._refresh(session)
            self.store.touch(session.id, now)
            return Caller(access.subject, access.name)
        return self._refresh(session)

    def _verify(self, token: str) -> VerifiedAccess:
        """Raises TokenExpired for the caller to renew; every other failure is typed here."""
        try:
            return self.oidc.verify_access(token, self.clock)
        except TokenInvalid:
            raise Unauthenticated from None
        except IdentityUnavailable:
            raise Unavailable from None

    def _serve_renewed(self, session: StoredSession) -> Caller:
        """Tokens another holder stored: served only if they verify now, never renewed here."""
        try:
            access = self._verify(self._open(session).access)
        except TokenExpired:
            raise Unavailable from None
        return Caller(access.subject, access.name)

    def _refresh(self, seen: StoredSession) -> Caller:
        deadline = self.clock.monotonic() + WAIT_BOUND_SECONDS
        with self.store.refresh_holder(seen.id) as holder:
            if holder is not None:
                return self._hold(holder, seen)
        return self._wait(seen, deadline)

    def _hold(self, holder: RefreshHolder, seen: StoredSession) -> Caller:
        current = holder.read()
        if current is None:
            raise Unauthenticated
        now = self.clock.now()
        if not SessionTimes(current.created_at, current.last_used_at).usable_at(now):
            holder.delete()
            raise Unauthenticated
        if current.tokens != seen.tokens and current.access_expires_at > now:
            # Another holder finished between this request's read and its lock.
            return self._serve_renewed(current)
        tokens = self._open(current)
        try:
            fresh = self.oidc.refresh(tokens.refresh)
        except IdentityRefused:
            logger.info("identity server refused a token refresh; the session is deleted")
            holder.delete()
            raise Unauthenticated from None
        except IdentityUnavailable:
            raise Unavailable from None
        renewed = TokenSet(fresh.access, fresh.refresh, fresh.id or tokens.id)
        try:
            access = self.oidc.verify_access(renewed.access, self.clock)
            forbidden = carries_forbidden_claim(renewed)
        except (TokenInvalid, TokenExpired):
            forbidden = True
        except IdentityUnavailable:
            raise Unavailable from None
        if forbidden or access.subject != current.subject:
            logger.warning("refreshed tokens failed verification; the session is deleted")
            holder.delete()
            raise Unauthenticated
        sealed = self.sealer.seal(renewed.to_bytes(), current.session_hash)
        holder.store_tokens(sealed, access.expires_at, self.clock.now())
        return Caller(access.subject, access.name)

    def _wait(self, seen: StoredSession, deadline: float) -> Caller:
        """Non-blocking probes, no connection held between them, never a refresh of its own."""
        while deadline - self.clock.monotonic() >= _PROBE_BUDGET_SECONDS:
            self.clock.sleep(PROBE_INTERVAL_SECONDS)
            try:
                probe = self.store.probe(seen.id)
            except StorageUnavailable:
                continue
            if probe.session is None:
                raise Unauthenticated
            now = self.clock.now()
            if probe.session.tokens != seen.tokens and probe.session.access_expires_at > now:
                return self._serve_renewed(probe.session)
            if probe.lock_free:
                # The holder ended without fresh tokens: its refresh failed or it died.
                raise Unavailable
        raise Unavailable

    # Logout ------------------------------------------------------------------------------------

    def logout(self, cookie: str | None) -> None:
        """Ends the Keycloak SSO session, then deletes the application session (G-2 A)."""
        if not is_opaque(cookie):
            raise Unauthenticated
        session = self.store.find(digest(cookie or ""))
        if session is None:
            raise Unauthenticated
        try:
            self.oidc.end_session(self._open(session).refresh)
        except IdentityRefused:
            # Keycloak no longer holds that session; nothing is left to end there.
            logger.info("identity server session already ended at logout")
        except IdentityUnavailable:
            raise Unavailable from None
        self.store.delete(session.id)

