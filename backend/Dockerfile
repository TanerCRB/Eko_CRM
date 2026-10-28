# syntax=docker/dockerfile:1
# One image for backend, migrate and worker (ADR-0004). Python and the locked dependencies are
# installed at build time; the host needs only a container runtime (ADR-0001 Constraint 1).
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12.16-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

FROM python:3.12.16-slim-trixie
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
USER app
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
