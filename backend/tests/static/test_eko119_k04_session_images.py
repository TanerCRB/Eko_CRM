"""EKO-1-19 K-04 (ii): after the release-mode session, no image a Compose build of the composition
left behind exists; the planted contrasts' tags are the only named exceptions."""

from pathlib import Path

import pytest

from tests.support import session_images as si

COMPOSE_LABEL = {"com.docker.compose.project": "ekort-bkp-1a2b3c4d"}
CHECKED: dict[str, dict[str, str]] = {
    f"eko-crm/{name}:checked": {} for name in ("backend", "frontend", "proxy", "backup")
}


def test_eko119_k04_exceptions_are_exactly_the_planted_contrast_tags() -> None:
    assert si.EXCEPTIONS == ("localhost/eko-crm/*-variant:*", "localhost/eko-crm/frontend-test:*")


def test_eko119_k04_a_session_that_built_nothing_passes() -> None:
    after = {
        **CHECKED,
        "postgres:18.6-trixie": {},
        "localhost/eko-crm/backend-variant:ekort-lab-1a2b3c4d-sleep": {},
        "localhost/eko-crm/backup-planted:test-x0": {},
    }
    assert si.violations(set(CHECKED), after) == []


@pytest.mark.parametrize(
    ("reference", "labels"),
    [
        ("ekort-bkp-1a2b3c4d-backup:latest", {}),
        ("ekort-dev-1a2b3c4d-proxy:latest", COMPOSE_LABEL),
        ("ekort-dev-1a2b3c4d-unset-frontend:latest", {}),
        ("localhost/eko-crm/backend:0.1.0-ekort-dev-1a2b3c4d", COMPOSE_LABEL),
        ("eko-compat-1a2b3c4d-worker:latest", {}),
    ],
)
def test_eko119_k04_an_image_a_compose_build_left_fails(
    reference: str, labels: dict[str, str]
) -> None:
    assert si.violations(set(CHECKED), {**CHECKED, reference: labels}) != []


def test_eko119_k04_a_name_present_before_the_session_is_not_this_sessions() -> None:
    stale = "ekort-fresh-374762d9-backup:latest"
    assert si.violations({*CHECKED, stale}, {**CHECKED, stale: COMPOSE_LABEL}) == []


def test_eko119_k04_an_exception_tag_with_a_compose_label_is_allowed() -> None:
    variant = "localhost/eko-crm/backend-variant:ekort-lab-1a2b3c4d-slow"
    assert si.violations(set(CHECKED), {**CHECKED, variant: COMPOSE_LABEL}) == []


def test_eko119_k04_snapshot_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "before.txt"
    si.write_snapshot(path, set(CHECKED))
    assert si.read_snapshot(path) == set(CHECKED)
