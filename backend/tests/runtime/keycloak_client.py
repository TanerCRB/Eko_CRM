"""Live Keycloak operations through the composed listeners; never log credential material."""

import base64
import hashlib
import html
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from tests.runtime.conftest import Composition, Started

FORM_ACTION = re.compile(r'<form[^>]+action="([^"]+)"', re.IGNORECASE)


class TypedUsernameStop(AssertionError):
    pass


def msys_path(path: Path) -> str:
    posix = path.as_posix()
    if os.name == "nt":
        return re.sub(r"^([A-Za-z]):/", lambda match: f"/{match.group(1).lower()}/", posix)
    return posix


def bash_executable() -> str:
    if os.name == "nt":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    return "bash"


def run_bootstrap(
    composition: Composition,
    evidence: Path | None = None,
    overrides: dict[str, str] | None = None,
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    from tests.support.repo import REPO_ROOT

    args = [bash_executable(), "scripts/keycloak-bootstrap.sh", msys_path(composition.env_file)]
    if evidence is not None:
        args += ["--evidence", msys_path(evidence)]

    environment = dict(os.environ)
    environment.update(overrides or {})
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        # The bootstrap's own ceilings (compose --wait 420 s, gate reachability deadline
        # 420 s) plus two gate cycles must fit under the harness timeout; the previous
        # 900 s could fail the contrast runs that legitimately spend ~420 s verifying a
        # listener that never serves.
        timeout=1800,
    )
    logs = ""
    if result.returncode != expected:
        log_result = composition.compose("logs", "--tail", "100", "keycloak", check=False)
        logs = (log_result.stdout + log_result.stderr)[-8000:]
    assert result.returncode == expected, (
        f"bootstrap exited {result.returncode}, expected {expected}\n"
        f"{result.stdout[-2000:]}\n{result.stderr[-2000:]}\n{logs}"
    )
    return result


def prepare(composition: Composition) -> None:
    composition.compose(
        "up",
        "--build",
        "--wait",
        "--wait-timeout",
        "600",
        "proxy",
        "frontend",
        "backend",
        "migrate",
        "worker",
        "postgres",
        "backup",
        "mailcatcher",
        timeout=900,
    )


def listener_open(composition: Composition, listener: str) -> bool:
    path = (
        "/realms/master/.well-known/openid-configuration"
        if listener == "admin"
        else "/realms/eko/.well-known/openid-configuration"
    )
    try:
        response = composition.through_proxy(listener, path)
    except (httpx.HTTPError, OSError):
        return False
    return response.status_code != 503


class RealmClient:
    def __init__(self, composition: Composition, realm: str, listener: str = "admin") -> None:
        self.composition = composition
        self.realm = realm
        self.listener = listener
        self._client = httpx.Client(verify=False, timeout=30, follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        data: dict[str, str] | None = None,
        json_body: Any = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        env = self.composition.env
        port = env["PROXY_ADMIN_PORT"] if self.listener == "admin" else env["PROXY_HTTPS_PORT"]
        host = env["AUTH_ADMIN_HOST"] if self.listener == "admin" else env["AUTH_HOST"]
        url = httpx.URL(scheme="https", host="127.0.0.1", port=int(port), raw_path=path.encode())
        headers = {"Host": host}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = self._client.build_request(
            method,
            url,
            headers=headers,
            data=data,
            json=json_body,
            params=params,
        )
        request.extensions["sni_hostname"] = host
        return self._client.send(request)

    def direct_master_token(self, username: str, password: str) -> str:
        response = self.request(
            "POST",
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            },
        )
        assert response.status_code == 200, f"master token status {response.status_code}"
        token: str = response.json()["access_token"]
        return token

    def browser_token(
        self,
        username: str,
        password: str,
        *,
        client_id: str = "admin-cli",
        client_secret: str | None = None,
    ) -> dict[str, Any]:
        redirect_uri = "https://eko112.invalid/callback"
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        query = httpx.QueryParams(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        login = self.request("GET", f"/realms/{self.realm}/protocol/openid-connect/auth?{query}")
        assert login.status_code == 200, f"login page status {login.status_code}"
        match = FORM_ACTION.search(login.text)
        assert match is not None, "login form not found"
        action = html.unescape(match.group(1))
        parsed = urlparse(action)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        submitted = self.request("POST", path, data={"username": username, "password": password})
        assert submitted.status_code in (302, 303), (
            f"login submission status {submitted.status_code}"
        )
        location = submitted.headers.get("location", "")
        location_parts = urlparse(location)
        location_query = parse_qs(location_parts.query)
        code = location_query.get("code", [""])[0]
        assert code, (
            f"authorization code missing at {location_parts.path}; "
            f"query keys {sorted(location_query)}"
        )
        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
        if client_secret is not None:
            form["client_secret"] = client_secret
        exchanged = self.request(
            "POST", f"/realms/{self.realm}/protocol/openid-connect/token", data=form
        )
        assert exchanged.status_code == 200, f"code exchange status {exchanged.status_code}"
        result: dict[str, Any] = exchanged.json()
        result["_authorization_code"] = code
        return result

    def refresh(self, client_id: str, refresh_token: str, client_secret: str) -> dict[str, Any]:
        response = self.request(
            "POST",
            f"/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
                "client_secret": client_secret,
            },
        )
        assert response.status_code == 200, f"refresh status {response.status_code}"
        result: dict[str, Any] = response.json()
        return result

    def logout(self, client_id: str, refresh_token: str, client_secret: str) -> None:
        response = self.request(
            "POST",
            f"/realms/{self.realm}/protocol/openid-connect/logout",
            data={
                "client_id": client_id,
                "refresh_token": refresh_token,
                "client_secret": client_secret,
            },
        )
        assert response.status_code in (200, 204), f"logout status {response.status_code}"

    def admin(
        self,
        token: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, str] | None = None,
        realm: str | None = None,
    ) -> httpx.Response:
        return self.request(
            method,
            f"/admin/realms/{realm or self.realm}/{path.lstrip('/')}",
            token=token,
            json_body=json_body,
            params=params,
        )

    def admin_json(
        self,
        token: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, str] | None = None,
        expected: int = 200,
        realm: str | None = None,
    ) -> Any:
        response = self.admin(token, method, path, json_body=json_body, params=params, realm=realm)
        assert response.status_code == expected, f"{method} {path}: status {response.status_code}"
        if not response.content:
            return None
        return response.json()


def decode_sid(token: str) -> str:
    payload = token.split(".")[1]
    decoded: dict[str, Any] = json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )
    return str(decoded["sid"])


def matching_value_paths(value: Any, candidates: set[str], path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [
            match
            for key, item in value.items()
            for match in matching_value_paths(item, candidates, f"{path}.{key}" if path else key)
        ]
    if isinstance(value, list):
        return [
            match
            for index, item in enumerate(value)
            for match in matching_value_paths(item, candidates, f"{path}[{index}]")
        ]
    if isinstance(value, str):
        folded = value.casefold()
        if any(candidate and candidate.casefold() in folded for candidate in candidates):
            return [path or "<root>"]
    return []


def assert_absent(text: str, values: dict[str, str], destination: str) -> None:
    for label, value in values.items():
        if value and value in text:
            raise AssertionError(f"{destination} contains forbidden value class: {label}")


def keycloak_logs(started: Started) -> str:
    result = started.composition.compose("logs", "--no-color", "keycloak", check=False)
    return result.stdout + result.stderr


# Gate markers bound to the verified Keycloak boot (ADR-0004-C33, addendum 2026-11-10):
# open_gate records the boot identity the proxy container itself reads, and the proxy
# entrypoint opens a listener only while the marker names the live boot. These helpers are
# the same primitives the script and the entrypoint use, so a test can neither fake the
# gate nor accidentally weaken it.
IDENTITY_SCRIPT = "/usr/local/bin/eko-keycloak-boot-identity.sh"
BOOT_IDENTITY = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")


def boot_identity(composition: Composition) -> str:
    """The boot identity the proxy container itself observes for the running Keycloak.

    The helper inside the proxy image reads the per-boot token file from the shared boot
    volume — the UUID the Keycloak entrypoint wrapper rotated as the first act of the
    container's CURRENT start (ADR-0004-C33) — validates its shape and prints it. A
    missing, empty or malformed token file exits non-zero and prints nothing; the
    observation is a pure file read, no network lookup of Keycloak (the withdrawn
    2026-11-06 primitive forced a TCP attempt and read the ARP table instead)."""
    return composition.compose(
        "exec", "-T", "proxy", "sh", IDENTITY_SCRIPT, check=False
    ).stdout.strip()


def marker_value(composition: Composition, gate: str) -> str:
    """The marker's CONTENT, read through a one-off mount of the markers' volume: the proxy
    container may be crash-looping (the exact state a failed gate check examines), where
    `compose exec` fails and a naive reader would report "no marker" vacuously.

    The one-off runs the image the composition's own proxy container uses — its
    `Config.Image` — not a guessed local build tag: a release run (EKO-1-15 K-02, the
    checked images) resets the build config and loads `eko-crm/proxy:checked`, so a
    `<project>-proxy:latest` name simply does not exist there. CI runs 42897088542 and
    42711869762 showed every marker reader dying in release mode alone
    (`Unable to find image ...`) while green in the composition job — this helper, or the
    same tag pattern inlined in the rotation-refusal test, was the single cause of four
    release-mode reds and the boot-identity-carrier ERROR. The container object exists and
    is inspectable even while crash-looping (`compose ps -a` finds it), which is exactly
    the state this reader exists for; the one-off needs an image with `sh` and the mount,
    and the proxy image is that image in both modes."""
    assert gate in ("admin", "public"), gate
    tag = composition.inspect("proxy")["Config"]["Image"]
    result = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{composition.project}_proxy-data:/data",
            "--entrypoint", "sh", tag, "-c",
            f"cat /data/{gate}-open 2>/dev/null || true",
        ],
        capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr[-500:]
    return result.stdout.strip()


def write_gate_marker(composition: Composition, gate: str, identity: str) -> None:
    """The same primitive `open_gate` uses: a marker naming the verified boot."""
    assert BOOT_IDENTITY.fullmatch(identity), "a boot identity, never a free-form value"
    composition.compose(
        "exec",
        "-T",
        "proxy",
        "sh",
        "-c",
        f"printf '%s\\n' '{identity}' > '/data/{gate}-open'",
    )
