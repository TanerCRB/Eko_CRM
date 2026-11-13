"""The one place configuration and secrets are read (ADR-0001 Constraint 1, ADR-0001-C10)."""

import base64
import binascii
import re

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # No env_file: values reach the process only as environment variables (ADR-0004).
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_db_host: str = "postgres"
    app_db_port: int = Field(default=5432, ge=1, le=65535)
    app_db_name: str = "eko"
    app_db_user: str = "eko_app"
    app_db_password: SecretStr
    # Required, not defaulted: the connection budget (ADR-0003-C19) is checked against the values
    # the running containers actually received.
    app_db_pool_size: int = Field(ge=1)
    app_db_max_overflow: int = Field(ge=0)
    app_db_connect_timeout_seconds: int = Field(default=3, ge=1)

    @field_validator("app_db_password")
    @classmethod
    def _not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("empty")
        return value


class WebSettings(Settings):
    # Uvicorn worker processes of `backend`; counted in the connection budget (ADR-0003-C19).
    web_concurrency: int = Field(ge=1)


class MigrateSettings(Settings):
    """`migrate` only (ADR-0004 addendum 2026-10-29); backend and worker never read these."""

    # Single-bigint advisory-lock key, written once in compose.yaml (`x-migration-advisory-lock`).
    migration_advisory_lock_key: int = Field(ge=-(2**63), le=2**63 - 1)
    # Required and positive: PostgreSQL reads 0 as "no timeout".
    migration_lock_timeout_seconds: int = Field(gt=0)
    migration_statement_timeout_seconds: int = Field(gt=0)

    @field_validator("migration_advisory_lock_key")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("zero")
        return value


_ORIGIN = re.compile(r"https?://[^/\s?#@]+")
_BASE_URL = re.compile(r"https?://[^\s?#@]+[^/\s?#@]")
_AUTHORITY = re.compile(r"(?P<scheme>https?)://(?P<host>\[[^\]/]*\]|[^:/\[\]]+)(?::(?P<port>\d+))?")
_DEFAULT_PORTS = {"https": 443, "http": 80}
# ADR-0003-C2: the realm's `accessTokenLifespan` (240 s, identity/eko-realm.json) plus these two
# is at most 300 s.
MAX_LEEWAY_PLUS_OFFSET_SECONDS = 60


class AuthSettings(BaseSettings):
    """`backend` only (EKO-2-01): the OIDC client, the browser origin and the session-token key.

    A separate class, not a field of `Settings`: `worker` and `migrate` never receive these.
    """

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # The application's own origin, `https://<app-host>` (ADR-0004 *HTTPS exposure*): compared
    # with `Origin` on state-changing requests and the base of the callback URL.
    app_origin: str
    # The realm's issuer exactly as Keycloak writes `iss`; browser-facing URLs are built on it.
    app_oidc_issuer: str
    # The realm's base URL for the backend's own calls inside the composition; the issuer if unset.
    app_oidc_internal_url: str | None = None
    app_oidc_client_id: str = "eko-backend"
    app_oidc_client_secret: SecretStr
    # URL-safe base64 of 32 random bytes (AES-256-GCM).
    app_session_encryption_key: SecretStr
    app_oidc_clock_skew_leeway_seconds: int = Field(default=30, ge=0)
    app_oidc_max_clock_offset_seconds: int = Field(default=30, ge=0)

    @field_validator("app_origin")
    @classmethod
    def _origin(cls, value: str) -> str:
        if not _ORIGIN.fullmatch(value):
            raise ValueError("not an origin")
        return without_default_port(value)

    @field_validator("app_oidc_issuer", "app_oidc_internal_url")
    @classmethod
    def _base_url(cls, value: str | None) -> str | None:
        if value is not None and not _BASE_URL.fullmatch(value):
            raise ValueError("not a base URL")
        return value

    @field_validator("app_oidc_issuer")
    @classmethod
    def _issuer_as_keycloak_writes_it(cls, value: str) -> str:
        return without_default_port(value)

    @field_validator("app_oidc_client_secret")
    @classmethod
    def _secret_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("empty")
        return value

    @field_validator("app_session_encryption_key")
    @classmethod
    def _key_32_bytes(cls, value: SecretStr) -> SecretStr:
        if len(_decode_key(value)) != 32:
            raise ValueError("not 32 bytes")
        return value

    @field_validator("app_oidc_max_clock_offset_seconds")
    @classmethod
    def _c2_bound(cls, value: int, info: ValidationInfo) -> int:
        leeway = info.data.get("app_oidc_clock_skew_leeway_seconds")
        if isinstance(leeway, int) and leeway + value > MAX_LEEWAY_PLUS_OFFSET_SECONDS:
            raise ValueError("leeway plus offset above the ADR-0003-C2 bound")
        return value

    def session_key(self) -> bytes:
        return _decode_key(self.app_session_encryption_key)


def without_default_port(url: str) -> str:
    """The URL with an explicit default port (443 for https, 80 for http) removed.

    Keycloak writes `iss` and a browser writes `Origin` without it (EKO-2-01, F-1 A); any other
    port is kept.
    """
    match = _AUTHORITY.match(url)
    if match is None or match.group("port") is None:
        return url
    if int(match.group("port")) != _DEFAULT_PORTS[match.group("scheme")]:
        return url
    return f"{match.group('scheme')}://{match.group('host')}{url[match.end():]}"


def _decode_key(value: SecretStr) -> bytes:
    raw = value.get_secret_value().strip()
    try:
        return base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return b""


def load_settings[T: BaseSettings](cls: type[T]) -> T:
    """Read the settings, or stop the process naming the variables at fault and nothing else."""
    try:
        return cls()
    except ValidationError as exc:
        names = sorted({str(error["loc"][0]).upper() for error in exc.errors() if error["loc"]})
        # `from None`: the validation error carries the input values, secrets included.
        raise SystemExit(
            "configuration error: missing, empty or invalid environment variable(s): "
            + ", ".join(names)
        ) from None
