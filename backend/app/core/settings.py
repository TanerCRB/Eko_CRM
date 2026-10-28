"""The one place configuration and secrets are read (ADR-0001 Constraint 1, ADR-0001-C10)."""

from pydantic import Field, SecretStr, ValidationError, field_validator
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


def load_settings[T: Settings](cls: type[T]) -> T:
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
