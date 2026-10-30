"""K-05 static half: migrate's 5 s lock timeout and 30 s statement timeout are literals in its
environment in compose.yaml, no other service receives them, and no revision of the real tree sets a
timeout (ADR-0004 addendum 2026-10-29, *Timeout values*)."""

from typing import Any

import pytest

from tests.static.conftest import COMPOSE
from tests.support import migration_checks as mc
from tests.support.source_checks import repository_sources

COMPOSE_TEXT = COMPOSE.read_text(encoding="utf-8")


def test_adr0004_c26_timeouts_are_literals_in_migrate_environment() -> None:
    assert mc.timeout_literal_violations(COMPOSE_TEXT) == []


@pytest.mark.parametrize(
    "replacement", ["${MIGRATION_LOCK_TIMEOUT:-5}", '"10"', '"0"', '"5s"', "$LOCK_TIMEOUT"]
)
def test_adr0004_c26_timeout_check_fails_on_another_or_interpolated_value(
    replacement: str,
) -> None:
    old = f'{mc.LOCK_TIMEOUT_VARIABLE}: "5"'
    assert COMPOSE_TEXT.count(old) == 1
    planted = COMPOSE_TEXT.replace(old, f"{mc.LOCK_TIMEOUT_VARIABLE}: {replacement}")
    assert mc.timeout_literal_violations(planted) != []


def test_adr0004_c26_timeout_check_fails_without_the_statement_timeout() -> None:
    planted = "\n".join(
        line for line in COMPOSE_TEXT.splitlines() if mc.STATEMENT_TIMEOUT_VARIABLE not in line
    )
    assert mc.timeout_literal_violations(planted) != []


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_adr0004_c26_only_migrate_receives_the_lock_and_timeouts(
    profile: str, rendered_dev: dict[str, Any], rendered_shared: dict[str, Any]
) -> None:
    rendered = rendered_dev if profile == "dev" else rendered_shared
    assert mc.other_services_with_timeouts(rendered) == []
    environment = rendered["services"]["migrate"]["environment"]
    assert {mc.LOCK_VARIABLE, *mc.TIMEOUTS} <= set(environment)


def test_adr0004_c26_only_migrate_check_fails_on_backend_with_a_timeout(
    rendered_shared: dict[str, Any],
) -> None:
    planted = {
        "services": {
            **rendered_shared["services"],
            "backend": {"environment": {mc.STATEMENT_TIMEOUT_VARIABLE: "30"}},
        }
    }
    assert mc.other_services_with_timeouts(planted) != []


def test_adr0004_c26_no_revision_sets_a_timeout() -> None:
    assert mc.revision_timeout_violations(repository_sources()) == []


@pytest.mark.parametrize(
    "statement",
    [
        "SET LOCAL lock_timeout = '1min'",
        "SET statement_timeout TO 0",
        "SELECT set_config('transaction_timeout', '0', true)",
        "SET Statement_Timeout = 0",
    ],
)
def test_adr0004_c26_revision_timeout_check_fails_on_a_planted_revision(statement: str) -> None:
    planted = {"backend/migrations/versions/0003_x.py": f'op.execute("{statement}")\n'}
    assert mc.revision_timeout_violations(planted) != []
