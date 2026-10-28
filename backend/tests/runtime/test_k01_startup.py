"""K-01: the documented command starts the development profile; health is readiness, status only."""

import json
import re
import time

import pytest

from tests.runtime.conftest import Started, parse_instant
from tests.support.compose_checks import DEV_SERVICES

pytestmark = pytest.mark.runtime

HEALTH = "/api/health"
HASHED_ASSET = re.compile(r"""(?:src|href)=["'](/assets/[\w.-]+-[\w-]{8,}\.(?:js|css))["']""")


def test_k01_documented_command_exits_zero(running: Started) -> None:
    assert running.up.returncode == 0


def test_k01_all_nine_services_exist(running: Started) -> None:
    listed = running.composition.compose("ps", "-a", "--format", "json").stdout
    services = {json.loads(line)["Service"] for line in listed.splitlines() if line.strip()}
    assert services == DEV_SERVICES


def test_k01_migrate_exits_zero_before_backend_and_worker_start(running: Started) -> None:
    composition = running.composition
    migrate = composition.inspect("migrate")["State"]
    assert migrate["Status"] == "exited"
    assert migrate["ExitCode"] == 0
    finished = parse_instant(migrate["FinishedAt"])
    for service in ("backend", "worker"):
        started = parse_instant(composition.inspect(service)["State"]["StartedAt"])
        assert finished < started, service


def test_k01_worker_and_migrate_run_the_backend_image(running: Started) -> None:
    composition = running.composition
    backend = composition.inspect("backend")["Image"]
    assert composition.inspect("worker")["Image"] == backend
    assert composition.inspect("migrate")["Image"] == backend


def test_k01_built_spa_and_its_hashed_asset_load_through_proxy(running: Started) -> None:
    page = running.composition.through_proxy("app", "/")
    assert page.status_code == 200
    assert re.search(r"""<div id=["']root["']""", page.text)
    assets = HASHED_ASSET.findall(page.text)
    assert assets, "no hashed bundle asset referenced"
    asset = running.composition.through_proxy("app", assets[0])
    assert asset.status_code == 200
    assert asset.content


def test_k01_health_get_and_head_succeed_without_a_cookie_status_only(running: Started) -> None:
    composition = running.composition
    get = composition.through_proxy("app", HEALTH)
    assert get.status_code == 200
    assert get.json() == {"status": "ok"}
    assert "set-cookie" not in get.headers
    head = composition.through_proxy("app", HEALTH, method="HEAD")
    assert head.status_code == 200
    assert head.content == b""


def test_k01_health_post_is_not_success(running: Started) -> None:
    for method in ("POST", "PUT", "DELETE"):
        response = running.composition.through_proxy("app", HEALTH, method=method)
        assert not 200 <= response.status_code < 300, method


def wait_for_health(started: Started, status: int, seconds: int = 90) -> int:
    deadline = time.monotonic() + seconds
    last = -1
    while time.monotonic() < deadline:
        last = started.composition.through_proxy("app", HEALTH).status_code
        if last == status:
            return last
        time.sleep(1)
    return last


def test_k01_contrast_postgres_stopped_backend_answers_failure_status_only(
    running: Started,
) -> None:
    composition = running.composition
    backend_before = composition.inspect("backend")["State"]
    composition.compose("stop", "postgres")
    try:
        assert wait_for_health(running, 503) == 503
        down = composition.through_proxy("app", HEALTH)
        # A proxy 502/504 has no JSON body; this answer is backend's own.
        assert down.status_code == 503
        assert down.headers["content-type"].startswith("application/json")
        assert down.json() == {"status": "unavailable"}
        head = composition.through_proxy("app", HEALTH, method="HEAD")
        assert head.status_code == 503
        assert composition.inspect("backend")["State"]["Running"] is True
    finally:
        composition.compose("start", "postgres")
    # Back without restarting backend.
    assert wait_for_health(running, 200) == 200
    backend_after = composition.inspect("backend")["State"]
    assert backend_after["StartedAt"] == backend_before["StartedAt"]
    assert composition.inspect("backend")["RestartCount"] == 0
