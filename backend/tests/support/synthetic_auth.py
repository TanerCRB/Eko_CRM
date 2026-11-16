"""Synthetic values for the authentication settings `create_app()` needs since EKO-2-01.

ADR-0005 synthetic rule; `AuthSettings` has no default for a secret (ADR-0004). One source for
both the root `tests/conftest.py` (pytest) and `api_surface.synthetic_settings()` (the
`openapi_compat` command line, which never loads conftest). No imports: conftest loads it before
any application module.
"""

SYNTHETIC_AUTH_SETTINGS = {
    "APP_ORIGIN": "https://synthetic-app.invalid",
    "APP_OIDC_ISSUER": "https://synthetic-auth.invalid/realms/eko",
    "APP_OIDC_CLIENT_SECRET": "synthetic-oidc-secret-only-for-tests",
    # URL-safe base64 of 32 bytes of 0x01.
    "APP_SESSION_ENCRYPTION_KEY": "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE",
}
