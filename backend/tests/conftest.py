"""Synthetic values for the settings `create_app()` needs since EKO-2-01 (ADR-0005 synthetic rule).

Tests that build the application in-process, or in a child process inheriting this environment,
set only the database variables they need; the authentication settings (`AuthSettings`) are
required too, with no default for a secret (ADR-0004). These are set only where unset, and a test
that judges them sets or removes them itself. The names are the backend's own: none is a
variable the composition interpolates, so no runtime composition reads them.
"""

import os

SYNTHETIC_AUTH_SETTINGS = {
    "APP_ORIGIN": "https://synthetic-app.invalid",
    "APP_OIDC_ISSUER": "https://synthetic-auth.invalid/realms/eko",
    "APP_OIDC_CLIENT_SECRET": "synthetic-oidc-secret-only-for-tests",
    # URL-safe base64 of 32 bytes of 0x01.
    "APP_SESSION_ENCRYPTION_KEY": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
}

for _name, _value in SYNTHETIC_AUTH_SETTINGS.items():
    os.environ.setdefault(_name, _value)
