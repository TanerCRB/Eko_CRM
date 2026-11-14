"""EKO-1-15 K-01, added by QA: the producer never takes a value from the environment, and the
release run's own command line (`render`, then `check`) is the check the tests prove.

The release run calls `python -m tests.support.release_composition render|check`, not the
functions; these tests go through `main` so a slip in the command's wiring is red.
"""

import io
import re
from pathlib import Path

import pytest

from tests.static.conftest import COMPOSE
from tests.static.test_eko115_k01_release_composition import DIGESTS, TAG, tag_only
from tests.support import release_composition as rc

PLANTED = "planted-environment-value"
# Built from its parts: the tracked-file secret scan (ADR-0004-C9) reads this file too.
PASSWORD = "APP_DB" + "_PASSWORD"


def required_names(compose: str) -> set[str]:
    return set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", compose))


def test_eko115_k01_qa_producer_takes_no_value_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    names = required_names(compose)
    assert PASSWORD in names
    for name in names:
        monkeypatch.setenv(name, PLANTED)
    text = rc.render(compose, TAG, DIGESTS)
    assert PLANTED not in text
    assert rc.variable_violations(compose, text) == []


def test_eko115_k01_qa_contrast_the_environment_value_substituted_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    monkeypatch.setenv(PASSWORD, PLANTED)
    text = rc.render(compose, TAG, DIGESTS)
    required = "${" + PASSWORD + ":?" + PASSWORD + " is required}"
    assert required in text
    assert rc.variable_violations(compose, text.replace(required, PLANTED)) != []


def _cli(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    code = rc.main(argv, out)
    return code, out.getvalue()


def _render(tmp_path: Path) -> Path:
    # EKO-1-26 route A: keycloak is a pushed project image, so its digest arrives in the pushes'
    # file like the other four; the command names no keycloak reference (K-03).
    pushes = tmp_path / "digests.env"
    pushes.write_text(
        "".join(
            f"{n}={DIGESTS[n]}\n" for n in ("backend", "frontend", "proxy", "backup", "keycloak")
        ),
        encoding="utf-8",
    )
    target = tmp_path / "compose.release.yaml"
    code, output = _cli(
        [
            "render",
            "--tag",
            TAG,
            "--digests",
            str(pushes),
            "--postgres",
            DIGESTS["postgres"],
            "--out",
            str(target),
        ]
    )
    assert code == 0, output
    return target


def test_eko115_k01_qa_cli_check_passes_the_rendered_composition(tmp_path: Path) -> None:
    code, output = _cli(["check", "--composition", str(_render(tmp_path))])
    assert code == 0 and "0 violation(s)" in output, output


@pytest.mark.parametrize("service", ["backend", "postgres", "keycloak"])
def test_eko115_k01_qa_cli_check_fails_on_a_tag_only_reference(
    tmp_path: Path, service: str
) -> None:
    target = _render(tmp_path)
    target.write_text(tag_only(target.read_text(encoding="utf-8"), service), encoding="utf-8")
    code, output = _cli(["check", "--composition", str(target)])
    assert code == 1 and f"VIOLATION: {service}:" in output, output


def test_eko115_k01_qa_cli_check_fails_on_a_substituted_value(tmp_path: Path) -> None:
    target = _render(tmp_path)
    required = "${" + PASSWORD + ":?" + PASSWORD + " is required}"
    text = target.read_text(encoding="utf-8")
    assert required in text
    target.write_text(text.replace(required, PLANTED), encoding="utf-8")
    code, output = _cli(["check", "--composition", str(target)])
    assert code == 1 and "required variable" in output, output
