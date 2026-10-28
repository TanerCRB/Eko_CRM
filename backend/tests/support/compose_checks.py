"""Checks on the composition (K-04): each returns the violations it finds, empty when it holds.

`rendered` is `docker compose config --format json` (interpolated, profiles applied); `source` is
the composition file parsed as written, for the declaration checks the interpolated rendering
cannot answer (K-04: a `${` check on the interpolated rendering is vacuous).
"""

import re
from pathlib import PurePosixPath
from typing import Any

from tests.support.image_refs import image_ref_violations

DEV_SERVICES = {
    "proxy",
    "frontend",
    "backend",
    "migrate",
    "worker",
    "keycloak",
    "postgres",
    "backup",
    "mailcatcher",
}
SHARED_SERVICES = DEV_SERVICES - {"mailcatcher"}
MAIL_CATCHER_IMAGES = re.compile(r"(mailpit|mailhog|mailcatcher|maildev|smtp4dev|greenmail)", re.I)
STATE_VOLUMES = {"pgdata", "proxy-data"}
NO_HOST_PATH_SERVICES = ("postgres", "keycloak", "backend", "migrate", "worker", "backup")
CLOUD_LOG_DRIVERS = {"awslogs", "gcplogs", "logentries", "splunk", "etwlogs"}
UNSPECIFIED_ADDRESSES = {"", "0.0.0.0", "::", "[::]"}
ADMIN_TARGET_PORT = 8443
APP_SERVICES_ON_BACKEND_IMAGE = ("migrate", "worker")
INIT_DIR = PurePosixPath("/docker-entrypoint-initdb.d")

Rendered = dict[str, Any]


def _services(rendered: Rendered) -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = rendered.get("services", {})
    return services


def _words(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def c1_services(dev: Rendered, shared: Rendered) -> list[str]:
    """ADR-0004-C1 with the 2026-10-27 worker addendum: nine services in dev, eight shared."""
    problems = []
    if set(_services(dev)) != DEV_SERVICES:
        problems.append(f"development profile services {sorted(_services(dev))}")
    if set(_services(shared)) != SHARED_SERVICES:
        problems.append(f"shared profile services {sorted(_services(shared))}")
    for name, service in _services(shared).items():
        if MAIL_CATCHER_IMAGES.search(str(service.get("image", ""))):
            problems.append(f"shared profile runs a mail catcher as {name}")
    return problems


def c2_images(rendered: Rendered) -> list[str]:
    """ADR-0004-C2 (and ADR-0002-C12, ADR-0003-C3 for their images): every image is pinned."""
    problems = []
    for name, service in _services(rendered).items():
        if "image" in service:
            problems += [f"{name}: {p}" for p in image_ref_violations(str(service["image"]))]
    return problems


def c3_ports(rendered: Rendered) -> list[str]:
    """ADR-0004-C3, DoD item 12: only proxy publishes; its admin listener not on every address."""
    problems = []
    for name, service in _services(rendered).items():
        if service.get("network_mode") == "host":
            problems.append(f"{name}: network_mode host publishes every port")
        if name != "proxy" and service.get("ports"):
            problems.append(f"{name}: publishes ports")
    proxy = _services(rendered).get("proxy", {})
    admin = [p for p in proxy.get("ports", []) if p.get("target") == ADMIN_TARGET_PORT]
    if not admin:
        problems.append("proxy: no admin listener port mapping")
    for mapping in admin:
        if str(mapping.get("host_ip", "")) in UNSPECIFIED_ADDRESSES:
            problems.append("proxy: admin listener published on every address")
    return problems


def c3_admin_bind_declared(source: dict[str, Any]) -> list[str]:
    """K-04 edge: the admin bind address comes from a required variable with no default."""
    proxy = source.get("services", {}).get("proxy", {})
    for mapping in proxy.get("ports", []):
        if isinstance(mapping, dict) and mapping.get("target") == ADMIN_TARGET_PORT:
            host_ip = str(mapping.get("host_ip", ""))
            if re.fullmatch(r"\$\{[A-Z][A-Z0-9_]*:\?[^}]*\}", host_ip):
                return []
            return [f"proxy: admin host_ip {host_ip!r} is not a required variable"]
    return ["proxy: admin listener not declared in long port syntax"]


def c4_state(rendered: Rendered) -> list[str]:
    """ADR-0004-C4: only pgdata and proxy-data, no host path, no cloud logging driver."""
    problems = []
    declared = set(rendered.get("volumes", {}) or {})
    if declared != STATE_VOLUMES:
        problems.append(f"named volumes {sorted(declared)}")
    for name, service in _services(rendered).items():
        for volume in service.get("volumes", []) or []:
            kind = volume.get("type")
            if kind == "bind":
                problems.append(f"{name}: host path {volume.get('source')} mounted")
            elif kind == "volume" and volume.get("source") not in STATE_VOLUMES:
                problems.append(f"{name}: volume {volume.get('source')} outside the state volumes")
        driver = (service.get("logging") or {}).get("driver")
        if driver in CLOUD_LOG_DRIVERS:
            problems.append(f"{name}: cloud logging driver {driver}")
    for name in NO_HOST_PATH_SERVICES:
        if name not in _services(rendered):
            problems.append(f"{name}: missing")
    return problems


def c11_migrations(rendered: Rendered, backend_dockerfile: str) -> list[str]:
    """ADR-0004-C11 and the composition half of ADR-0006-C13."""
    problems = []
    services = _services(rendered)
    for name, service in services.items():
        runs_upgrade = "alembic upgrade" in " ".join(
            [_words(service.get("command")), _words(service.get("entrypoint"))]
        )
        if runs_upgrade and name != "migrate":
            problems.append(f"{name}: command or entrypoint runs alembic upgrade")
    if "alembic upgrade" not in _words(services.get("migrate", {}).get("command")):
        problems.append("migrate: command does not run alembic upgrade")
    if "alembic upgrade" in backend_dockerfile:
        problems.append("backend image: Dockerfile runs alembic upgrade")
    for name in ("backend", "worker"):
        condition = (services.get(name, {}).get("depends_on") or {}).get("migrate", {})
        if condition.get("condition") != "service_completed_successfully":
            problems.append(f"{name}: does not wait for migrate to complete successfully")
    for name, service in services.items():
        for dependency, spec in (service.get("depends_on") or {}).items():
            if (
                dependency == "migrate"
                and spec.get("condition") != "service_completed_successfully"
            ):
                problems.append(f"{name}: depends on migrate with {spec.get('condition')}")
    return problems


def c13_worker_image(rendered: Rendered) -> list[str]:
    """ADR-0006-C13 composition half: worker (and migrate) run the image backend builds."""
    services = _services(rendered)
    backend = services.get("backend", {})
    if not backend.get("build") or not backend.get("image"):
        return ["backend: does not build and name its image"]
    problems = []
    for name in APP_SERVICES_ON_BACKEND_IMAGE:
        service = services.get(name, {})
        if service.get("image") != backend["image"] or "build" in service:
            problems.append(f"{name}: does not run the backend image")
        if service.get("ports"):
            problems.append(f"{name}: publishes ports")
    return problems


def c28_rendered(rendered: Rendered) -> list[str]:
    """ADR-0004-C28 static half on the rendering: image only, inline init content attached."""
    problems = []
    postgres = _services(rendered).get("postgres", {})
    if "build" in postgres:
        problems.append("postgres: has build")
    if "image" not in postgres:
        problems.append("postgres: has no image")
    attached = [
        c
        for c in postgres.get("configs", []) or []
        if PurePosixPath(str(c.get("target", ""))).parent == INIT_DIR
    ]
    if not attached:
        problems.append("postgres: no config attached under /docker-entrypoint-initdb.d/")
    for config in attached:
        top = (rendered.get("configs") or {}).get(config.get("source"), {})
        if "file" in top or "environment" in top:
            problems.append(f"config {config.get('source')}: not inline content")
        if "content" not in top:
            problems.append(f"config {config.get('source')}: has no inline content")
    return problems


def unescaped_dollars(text: str) -> list[str]:
    """Every `$` not written `$$`: Compose interpolates `$NAME` exactly as it does `${NAME}`."""
    found = []
    i = 0
    while i < len(text):
        if text[i] == "$":
            if text.startswith("$$", i):
                i += 2
                continue
            found.append(text[i : i + 12])
        i += 1
    return found


def c28_source(source: dict[str, Any]) -> list[str]:
    """ADR-0004-C28 on the source: init content inline, no `file`, no interpolation."""
    problems = []
    postgres = source.get("services", {}).get("postgres", {})
    names = [c.get("source") if isinstance(c, dict) else c for c in postgres.get("configs", [])]
    if not names:
        problems.append("postgres: no config")
    for name in names:
        config = (source.get("configs") or {}).get(name, {})
        if "file" in config:
            problems.append(f"config {name}: file source")
        content = config.get("content")
        if not isinstance(content, str):
            problems.append(f"config {name}: no inline content")
            continue
        for fragment in unescaped_dollars(content):
            problems.append(f"config {name}: interpolation {fragment!r}")
    return problems


def secret_declaration_violations(source: dict[str, Any], secrets: set[str]) -> list[str]:
    """ADR-0004-C9, C10 on the source: a secret is only `${NAME:?...}`, never a value or default."""
    problems = []
    required = re.compile(r"\$\{(?P<name>[A-Z][A-Z0-9_]*):?\?[^}]*\}")
    for service_name, service in (source.get("services") or {}).items():
        environment = service.get("environment") or {}
        if isinstance(environment, list):
            pairs = [
                tuple(item.split("=", 1)) if "=" in item else (item, None) for item in environment
            ]
            environment = dict(pairs)
        for key, value in environment.items():
            text = "" if value is None else str(value)
            named = {key} | set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)", text))
            if not named & secrets:
                continue
            match = required.fullmatch(text.strip())
            if match is None:
                problems.append(f"{service_name}: {key} is not a required variable with no default")
            elif match.group("name") not in secrets:
                problems.append(f"{service_name}: {key} takes a non-secret variable")
    return problems
