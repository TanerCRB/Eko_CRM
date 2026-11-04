"""EKO-1-13 K-05 (QA, kills EKO-1-13/M16): a `CommandError` raised while `migrate` upgrades is
written as one `app.migrations` error line, and its message, holding a marker, is in no line.

ADR-0005 addendum of 2026-11-02, *An error outside a request*, `migrate`, as amended at
verification (QA low): the wrap in `env.py` and the interpreter hook are two guards, neither
standing in for the other. Alembic 1.20.1's `CommandLine.run_cmd` catches `CommandError` and
prints `FAILED: <message>` (and logs the message on `alembic`), so for this exception the hook is
never reached and only the wrap keeps the message out of the log. A database error, the case of
`test_adr0005_uncaught_driver_error.py`, is caught by both, which is why removing the wrap alone
survived there.

Contrast: the same revision with the wrap removed from `env.py` (one element: the hook stays
installed) puts `FAILED:` and the marker in the log, so the check can fail.
"""

import pytest

from tests.runtime.lab import Lab, configuration_values
from tests.runtime.test_adr0005_uncaught_driver_error import error_line_problems
from tests.support import log_lines as ll

pytestmark = pytest.mark.runtime

REVISION = "t_eko113_command_error.py"
MARKER = "marker-k05-e113cmd"
WRAP = (
    "    try:\n        dispatch()\n    except Exception:\n"
    '        logger.error("migrate failed", exc_info=True)\n'
    "        raise SystemExit(1) from None\n"
)
UNWRAPPED = "    dispatch()\n"


def test_adr0005_qa_migrate_command_error_written_as_its_type(lab: Lab) -> None:
    lab.reset()
    code, logs = lab.run_migrate(lab.variant("eko113_command_error", (REVISION,)))
    assert code != 0, logs
    assert error_line_problems(logs, "migrate") == []
    errors = [x for x in ll.json_lines(logs)[0] if x.get("event") == "error"]
    assert len(errors) == 1, errors
    [line] = errors
    assert (line["logger"], line["error"]) == ("app.migrations", "alembic.util.exc.CommandError")
    assert line["at"].startswith("migrations/versions/t_eko113_command_error.py:upgrade:"), line
    assert ll.leaks(logs, MARKER, "FAILED", "revision refused", *configuration_values(lab)) == []


def test_adr0005_qa_migrate_command_error_contrast_without_the_wrap(lab: Lab) -> None:
    lab.reset()
    image = lab.planted_env_py("eko113_command_error_unwrapped", WRAP, UNWRAPPED, (REVISION,))
    code, logs = lab.run_migrate(image)
    assert code != 0, logs
    assert f"FAILED: revision refused {MARKER}" in logs
