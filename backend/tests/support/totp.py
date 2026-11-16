"""RFC 6238 time-based one-time passwords with the standard library only (EKO-2-01, Q-2 A).

Keycloak's defaults are used as they are (the Issue puts OTP policy parameters out of scope):
HMAC-SHA1, six digits, a 30-second period. Keycloak computes the code over the UTF-8 bytes of
the credential's raw secret (the value of the enrolment form's hidden `totpSecret` input); the
base32 text the page shows is the encoding of those same bytes. Nothing here prints a secret or
a code.
"""

import base64
import hashlib
import hmac
import struct
import time

PERIOD_SECONDS = 30
DIGITS = 6


def time_step(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // PERIOD_SECONDS)


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP: dynamic truncation of HMAC-SHA1 over the 8-byte big-endian counter."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def totp(key: bytes, step: int | None = None) -> str:
    return hotp(key, time_step() if step is None else step)


def keycloak_key(raw_secret: str) -> bytes:
    """The HMAC key Keycloak uses for a TOTP credential: the raw secret's UTF-8 bytes."""
    return raw_secret.encode("utf-8")


def displayed_secret(raw_secret: str) -> str:
    """The base32 form Keycloak shows at enrolment, without its grouping spaces or padding."""
    return base64.b32encode(keycloak_key(raw_secret)).decode("ascii").rstrip("=")
