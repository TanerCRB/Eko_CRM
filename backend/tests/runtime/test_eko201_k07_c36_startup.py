"""EKO-2-01 K-07 / ADR-0004-C36 (fresh-bootstrap and restart half) on the theme-bearing image.

- A fresh composition's bootstrap verifies the provider selection and its filtering
  (ADR-0004-C34) and binds the gate markers to the current boot (C33) before either listener
  opens, and the running Keycloak is the theme-bearing image; a restart against the existing
  volume re-verifies both before the listeners reopen.
- The application realm's security settings are a live precondition of the public listener:
  drift in the live realm is reconciled from the versioned export on the rerun, and a realm that
  lacks the export's browser flow keeps the public listener closed.
- Contrast: the same image with only the provider JAR removed keeps both listeners closed.

The restore half of C36 (re-applying OTP-credential removals at restore step 9) is EKO-1-08's
(#36, G-H A); nothing here restores.
"""

import os
import secrets
import subprocess
from pathlib import Path

import pytest

from tests.runtime.conftest import Composition
from tests.runtime.keycloak_client import (
    RealmClient,
    boot_identity,
    listener_open,
    marker_value,
    prepare,
    run_bootstrap,
)
from tests.support import eko112_fixtures as eko112
from tests.support.repo import REPO_ROOT
from tests.support.theme_checks import IMAGE_THEME_DIR, THEME_NAME

pytestmark = pytest.mark.runtime
IMAGE = "localhost/eko-crm/keycloak:26.8.1-eko112"
EXPORT = REPO_ROOT / "identity" / "eko-realm.json"
THEME_FILE = f"{IMAGE_THEME_DIR}/login/theme.properties"
PROVIDER_JAR = "/opt/keycloak/providers/eko112-event-store-1.0.0.jar"


def image_id(reference: str) -> str:
    return subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


def events(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def position(lines: list[str], expected: str, after: int = -1) -> int:
    return next(index for index, line in enumerate(lines) if index > after and expected in line)


def breakglass(composition: Composition) -> tuple[RealmClient, str]:
    client = RealmClient(composition, "master")
    token = client.direct_master_token(
        eko112.ACCOUNTS["breakglass_one"],
        composition.env[eko112.PASSWORD_VARIABLES["breakglass_one"]],
    )
    return client, token


def test_c36_fresh_bootstrap_and_restart_verify_before_opening_on_the_theme_image(
    fresh: Composition, tmp_path: Path
) -> None:
    prepare(fresh)
    assert not listener_open(fresh, "admin") and not listener_open(fresh, "auth")
    record = tmp_path / "bootstrap.jsonl"
    run_bootstrap(fresh, record)

    # The running server is the theme-bearing image.
    running = fresh.inspect("keycloak")["Image"]
    assert running == image_id(IMAGE)
    present = fresh.compose("exec", "-T", "keycloak", "test", "-f", THEME_FILE, check=False)
    assert present.returncode == 0, "the running Keycloak has no theme"

    lines = events(record)
    order = [
        position(lines, "custom provider selected"),
        position(lines, "filtering verified"),
        position(lines, "admin listener open"),
        position(lines, "application security settings verified"),
        position(lines, "public listener open"),
    ]
    assert order == sorted(order), lines
    assert listener_open(fresh, "admin") and listener_open(fresh, "auth")
    identity = boot_identity(fresh)
    assert identity and marker_value(fresh, "admin") == identity == marker_value(fresh, "public")

    # Restart against the existing volume: a new boot, verified again before reopening.
    first = len(lines)
    run_bootstrap(fresh, record)
    lines = events(record)
    assert "rerun existing volume live checks" in "\n".join(lines[first:])
    rerun = [
        position(lines, "custom provider selected", first - 1),
        position(lines, "filtering verified", first - 1),
        position(lines, "admin listener open", first - 1),
        position(lines, "application security settings verified", first - 1),
        position(lines, "public listener open", first - 1),
    ]
    assert rerun == sorted(rerun), lines[first:]
    restarted = boot_identity(fresh)
    assert restarted and restarted != identity
    assert marker_value(fresh, "admin") == restarted == marker_value(fresh, "public")

    # Live drift is reconciled from the export on the next run.
    master, token = breakglass(fresh)
    try:
        realm = master.admin_json(token, "GET", "", realm="eko")
        realm.update(failureFactor=30, ssoSessionIdleTimeout=600, loginTheme="", passwordPolicy="")
        assert master.admin(token, "PUT", "", json_body=realm, realm="eko").status_code == 204
        run_bootstrap(fresh, record)
        live = master.admin_json(token, "GET", "", realm="eko")
        assert (live["failureFactor"], live["ssoSessionIdleTimeout"]) == (5, 1800)
        assert (live["loginTheme"], live["passwordPolicy"]) == (THEME_NAME, "length(12)")
        assert listener_open(fresh, "auth")

        # A realm without the export's browser flow (as one created before it) fails closed.
        realm = master.admin_json(token, "GET", "", realm="eko")
        realm["browserFlow"] = "browser"
        assert master.admin(token, "PUT", "", json_body=realm, realm="eko").status_code == 204
        flows = master.admin_json(token, "GET", "authentication/flows", realm="eko")
        ours = next(item for item in flows if item["alias"] == "eko browser")
        deleted = master.admin(token, "DELETE", f"authentication/flows/{ours['id']}", realm="eko")
        assert deleted.status_code == 204, deleted.status_code
    finally:
        master.close()
    refused = run_bootstrap(fresh, record, expected=7)
    assert "application security settings not applied" in refused.stdout + refused.stderr
    assert listener_open(fresh, "admin")
    assert not listener_open(fresh, "auth")


def test_c36_without_the_provider_jar_both_listeners_stay_closed(
    fresh: Composition, tmp_path: Path
) -> None:
    tag = f"localhost/eko-crm/eko201-fixture:no-provider-{secrets.token_hex(4)}"
    (tmp_path / "Dockerfile").write_text(
        f"FROM {IMAGE}\n"
        "RUN rm /opt/keycloak/providers/eko112-event-store-1.0.0.jar && "
        "/opt/keycloak/bin/kc.sh build --spi-events-store--provider=jpa\n",
        encoding="utf-8",
    )
    build = ["docker", "build", "-q", "-t", tag, str(tmp_path)]
    subprocess.run(build, capture_output=True, check=True, timeout=900)
    override = tmp_path / "no-provider.yaml"
    override.write_text(
        "services:\n  keycloak:\n"
        f"    image: {tag}\n    build: !reset null\n    pull_policy: never\n",
        encoding="utf-8",
    )
    try:
        fresh.extra_files.append(override)
        prepare(fresh)
        # The bootstrap's own compose calls read the same file list from COMPOSE_FILE.
        files = os.pathsep.join([str(REPO_ROOT / "compose.yaml"), str(override)])
        run_bootstrap(fresh, overrides={"COMPOSE_FILE": files}, expected=6)
        assert fresh.inspect("keycloak")["Config"]["Image"] == tag
        missing = fresh.compose("exec", "-T", "keycloak", "test", "-e", PROVIDER_JAR, check=False)
        assert missing.returncode != 0, "the contrast image still has the provider"
        theme = fresh.compose("exec", "-T", "keycloak", "test", "-f", THEME_FILE, check=False)
        assert theme.returncode == 0, "the contrast image lost the theme too"
        assert not listener_open(fresh, "admin")
        assert not listener_open(fresh, "auth")
    finally:
        fresh.down()
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)
