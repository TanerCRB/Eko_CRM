"""EKO-3-06, composition half of ADR-0005-C22 and ADR-0004-C37, live: the declaration reaches a
one-off of `worker` exactly as the environment file holds it, and only there.

The operator's run mode is `docker compose run --rm --no-deps worker python -m app.seed ...`; the
one-off below is the same command with a probe in place of the seed (the seed is
developer-backend's). Its environment is the worker's: without a line in the environment file the
variable is present and empty ("not declared"); with the accepted value it is exactly that value.
`--no-deps` starts no other service and `--rm` leaves no container behind.

What the backend accepts is not proven here: the probe reports the raw value only.
"""

import pytest

from tests.runtime.conftest import Composition, checked_images_override, read_env, write_env

pytestmark = pytest.mark.runtime

VARIABLE = "APP_SYNTHETIC_DATA_ONLY"
ACCEPTED = "declared"
# The value is not a secret (ADR-0005 addendum); the probe prints only this one variable.
PROBE = (
    "import os, sys; value = os.environ.get('" + VARIABLE + "'); "
    "sys.stdout.write('UNSET' if value is None else 'VALUE[' + value + ']')"
)


def _one_off(composition: Composition) -> str:
    result = composition.compose(
        "run", "--rm", "--no-deps", "-T", "worker", "python", "-c", PROBE, timeout=300
    )
    return result.stdout.strip().splitlines()[-1]


def _containers(composition: Composition) -> list[str]:
    return composition.compose("ps", "-a", "-q").stdout.split()


def test_eko306_c22_one_off_worker_carries_the_environment_files_declaration(
    fresh: Composition,
) -> None:
    if checked_images_override() is None:
        fresh.compose("build", "backend", timeout=900)
    assert VARIABLE not in fresh.env

    assert _one_off(fresh) == "VALUE[]"
    assert _containers(fresh) == []

    values = read_env(fresh.env_file)
    values[VARIABLE] = ACCEPTED
    write_env(fresh.env_file, values)
    assert _one_off(fresh) == f"VALUE[{ACCEPTED}]"
    assert _containers(fresh) == []

    # Contrast: any other value is carried as written, for the backend to refuse.
    values[VARIABLE] = "false"
    write_env(fresh.env_file, values)
    assert _one_off(fresh) == "VALUE[false]"
