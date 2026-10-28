"""F-01: the composed keycloak healthcheck is healthy only when readiness as a whole is UP.

The check is run exactly as composed, inside a container serving a stand-in `/health/ready` on
port 9000: Keycloak's DOWN body (503, with a nested `"UP"` check) and its UP body (200).
"""

import subprocess
from pathlib import Path

import pytest

from tests.support.repo import render, write_synthetic_env

pytestmark = pytest.mark.runtime

IMAGE = "python:3.12.16-slim-trixie"
DOWN = (
    503,
    '{"status":"DOWN","checks":[{"name":"Graceful Shutdown","status":"UP"},'
    '{"name":"Keycloak Initialized","status":"DOWN"}]}',
)
UP = (200, '{"status":"UP","checks":[{"name":"Keycloak Initialized","status":"UP"}]}')
SERVER = """
import http.server, sys, threading
status, body = int(sys.argv[1]), sys.argv[2].encode()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 9000), H).serve_forever()
"""


def composed_healthcheck(tmp_path: Path) -> str:
    rendered = render(write_synthetic_env(tmp_path / "e.env"), dev_profile=True)
    test = rendered["services"]["keycloak"]["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL"
    command: str = test[1]
    return command


def probe(command: str, status: int, body: str) -> int:
    # Keycloak's /bin/sh is bash; the stand-in image's is dash, so bash is named explicitly.
    script = (
        f"python -c {_quote(SERVER)} {status} {_quote(body)} & "
        "for i in $(seq 50); do (exec 3<>/dev/tcp/127.0.0.1/9000) 2>/dev/null && break; "
        "sleep 0.1; done; "
        f"bash -c {_quote(command)}"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", IMAGE, "bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode


def _quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def test_k01_keycloak_healthcheck_fails_while_readiness_is_down(tmp_path: Path) -> None:
    assert probe(composed_healthcheck(tmp_path), *DOWN) != 0


def test_k01_keycloak_healthcheck_passes_when_readiness_is_up(tmp_path: Path) -> None:
    assert probe(composed_healthcheck(tmp_path), *UP) == 0
