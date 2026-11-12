"""Opaque identifiers, their stored hashes, PKCE, and sealing of stored tokens (ADR-0003 *Browser
flow*; key handling ADR-0004 *Secret handling*)."""

import base64
import hashlib
import re
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 32 random bytes, URL-safe base64 without padding.
OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}")
_NONCE_BYTES = 12


def new_opaque() -> str:
    return secrets.token_urlsafe(32)


def is_opaque(value: str | None) -> bool:
    return value is not None and OPAQUE.fullmatch(value) is not None


def digest(value: str) -> str:
    """What is stored for a browser identifier, state or nonce: never the value itself."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_verifier() -> str:
    # 64 characters, within RFC 7636's 43..128.
    return secrets.token_urlsafe(48)


def pkce_challenge(verifier: str) -> str:
    raw = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class SealBroken(Exception):
    """A sealed value does not open with this key and context (key rotated, row swapped)."""


class Sealer:
    """AES-256-GCM; the context (the row's own hash) is bound as associated data, so a sealed
    value copied to another row does not open there."""

    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)

    def seal(self, plaintext: bytes, context: str) -> bytes:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, plaintext, context.encode("ascii"))

    def open(self, sealed: bytes, context: str) -> bytes:
        try:
            return self._aead.decrypt(
                sealed[:_NONCE_BYTES], sealed[_NONCE_BYTES:], context.encode("ascii")
            )
        except (InvalidTag, ValueError):
            raise SealBroken from None
