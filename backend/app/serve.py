"""Entry point of the `backend` service: `python -m app.serve`."""

import uvicorn

from app.core.settings import WebSettings, load_settings


def main() -> None:
    # Read before uvicorn starts: its supervisor restarts a worker that dies on a missing secret,
    # so a check inside the workers would never stop the process (ADR-0004-C10).
    settings = load_settings(WebSettings)
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=settings.web_concurrency,
        # Uvicorn's access line carries the query string; request logging is EKO-1-13's.
        access_log=False,
    )


if __name__ == "__main__":
    main()
