"""EKO-3-06, QA contrast (K-01, K-05; ADR-0005-C22 end to end, ADR-0004-C37): the operator's own
command, `docker compose run --rm --no-deps worker python -m app.seed <s1> <s2> <s3>`, run in a
one-off of the built `worker` image against a fresh composition's own PostgreSQL.

The developer tests run the seed in-process or as a host subprocess with the worker's values, and
the composition test runs a probe in place of the seed. This one joins the two halves: the
declaration the environment file holds reaches the seed inside the container, and the seed there
judges it.

- Without the declaration line the one-off exits non-zero, names the declaration variable and
  stores no customer.
- Contrast, one changed element: the same composition with only `APP_SYNTHETIC_DATA_ONLY=declared`
  added to its environment file loads the whole dataset, each share under its named subject, and
  the one-off leaves no container behind.

Every value is synthetic; the subjects are made-up identifiers, and nothing but counts is read.
"""

import pytest

from app.seed_dataset import SHARE_SIZE, SHARES
from tests.runtime.conftest import Composition, read_env, write_env

pytestmark = pytest.mark.runtime

VARIABLE = "APP_SYNTHETIC_DATA_ONLY"
SUBJECTS = (
    "5a1e0306-0000-4000-8000-0000000000a1",
    "5a1e0306-0000-4000-8000-0000000000a2",
    "5a1e0306-0000-4000-8000-0000000000a3",
)
UP_SECONDS = 900


def _seed(composition: Composition) -> tuple[int, str]:
    done = composition.compose(
        "run", "--rm", "--no-deps", "-T", "worker", "python", "-m", "app.seed", *SUBJECTS,
        check=False, timeout=900,
    )  # fmt: skip
    return done.returncode, done.stdout + done.stderr


def _owners(composition: Composition) -> dict[str, int]:
    query = (
        "SELECT owner_subject, count(*) FROM customer WHERE dataset_key IS NOT NULL "
        "GROUP BY owner_subject ORDER BY 1"
    )
    done = composition.compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "eko", "-AtXq", "-F", "\t",
        "-c", query,
    )  # fmt: skip
    found = {}
    for line in done.stdout.splitlines():
        if "\t" in line:
            subject, count = line.split("\t")
            found[subject] = int(count)
    return found


def _customers(composition: Composition) -> int:
    done = composition.compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "eko", "-AtXq",
        "-c", "SELECT count(*) FROM customer",
    )  # fmt: skip
    return int(done.stdout.strip().splitlines()[-1])


def test_qa_eko306_the_operator_command_loads_only_a_declared_target(
    fresh: Composition,
) -> None:
    up = fresh.compose(
        "up", "--build", "--wait", "--wait-timeout", str(UP_SECONDS), "backend",
        check=False, timeout=UP_SECONDS + 300,
    )  # fmt: skip
    assert up.returncode == 0, up.stderr[-3000:]
    assert VARIABLE not in read_env(fresh.env_file)

    code, output = _seed(fresh)
    assert code != 0, output[-2000:]
    assert VARIABLE in output
    assert _customers(fresh) == 0

    values = read_env(fresh.env_file)
    values[VARIABLE] = "declared"
    write_env(fresh.env_file, values)
    code, output = _seed(fresh)
    assert code == 0, output[-3000:]
    total = SHARES * SHARE_SIZE
    assert f"seed finished: {total} records, {total} added, 0 already loaded, 0 refused" in output
    assert _owners(fresh) == dict.fromkeys(SUBJECTS, SHARE_SIZE)
    running = fresh.compose("ps", "-a", "--format", "{{.Service}}").stdout.split()
    assert "worker" not in running
