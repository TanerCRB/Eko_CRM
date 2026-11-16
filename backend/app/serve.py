"""Entry point of the `backend` service: `python -m app.serve`."""

import uvicorn

from app.core.logs import install_process_logging, log_config
from app.core.settings import AuthSettings, WebSettings, load_settings
from app.data.schema_revision import refuse_unless_servable

FACTORY = "app.main:create_app"


def main(factory: str = FACTORY) -> None:
    # `factory` is set only by a test variant image (ADR-0005 addendum 2026-11-02); no variable
    # and no argument of the shipped command sets it.
    install_process_logging("backend")
    # Read before uvicorn starts: its supervisor restarts a worker that dies on a missing secret,
    # so a check inside the workers would never stop the process (ADR-0004-C10).
    settings = load_settings(WebSettings)
    load_settings(AuthSettings)
    # Here for the same reason: a refusal in the workers would be restarted, never exit.
    refuse_unless_servable(settings, "backend")
    uvicorn.run(
        factory,
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=settings.web_concurrency,
        # Applied again in every worker process before it imports the factory.
        log_config=log_config("backend"),
        # Uvicorn's access line carries the query string; `backend` writes its own request line.
        access_log=False,
    )


if __name__ == "__main__":
    main()
