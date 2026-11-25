"""EKO-3-06, gate 1 A-4 A (ADR-0001 addendum of 2026-10-29; ADR-0005-C23): the seed's two files
are judged whole against their single-file layer rows, as `worker.py` is (#47 precedent: a
single-file row gets no `TID251` scope, and the layer check reads added lines only).

- `backend/app/seed.py` must not depend on `api`, `auth` or `integrations`.
- `backend/app/seed_dataset.py` depends on `domain` only: no other layer, `core` included, and no
  module of the standard library that reads a clock, the environment, the network, a file or a
  random source.

The rows are proposed for `docs/architecture/layer-dependencies.md` at gate 3 (this task's
report). Until they are there the test judges against them as written here; once they are, the
register's own rows must say the same.
"""

import ast

import pytest

from tests.support import layer_table as lt
from tests.support.repo import REPO_ROOT

SEED = "backend/app/seed.py"
DATASET = "backend/app/seed_dataset.py"
PROPOSED = {
    "seed": lt.Row("seed", SEED, (), ("api", "auth", "integrations")),
    "seed_dataset": lt.Row(
        "seed_dataset",
        DATASET,
        (),
        ("services", "data", "api", "integrations", "auth", "core"),
    ),
}
# Standard-library modules through which a value could come from outside the repository.
OUTSIDE_SOURCES = frozenset(
    {"os", "sys", "time", "datetime", "random", "secrets", "uuid", "socket", "pathlib", "io"}
    | {"importlib", "urllib", "http", "subprocess", "zoneinfo", "locale", "platform", "json"}
)


def rows() -> list[lt.Row]:
    """The register's rows, with the seed's two as proposed when the register has none yet."""
    table = lt.table_rows()
    names = {row.name for row in table}
    for name, row in PROPOSED.items():
        if name in names:
            [registered] = [r for r in table if r.name == name]
            assert registered == row, f"the register's {name} row differs from this task's"
    return table + [row for name, row in PROPOSED.items() if name not in names]


@pytest.mark.parametrize("path", [SEED, DATASET])
def test_a4_each_seed_file_is_judged_whole_against_its_row(path: str) -> None:
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    assert [row.name for row in rows() if row.matches(path)] != []
    assert lt.whole_file_findings(path, source, rows()) == []


def top_level_modules(source: str) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return found


def dataset_problems(source: str) -> list[str]:
    problems = []
    application = {
        module
        for _, module in lt.imported_modules(source, DATASET)
        if module == "app" or module.startswith("app.")
    }
    outside_domain = sorted(m for m in application if not m.startswith("app.domain"))
    if outside_domain:
        problems.append(f"imports outside domain: {outside_domain}")
    reading = sorted(top_level_modules(source) & OUTSIDE_SOURCES)
    if reading:
        problems.append(f"imports a module that reads outside the repository: {reading}")
    calls = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if calls & {"open", "input", "hash", "id"}:
        problems.append(f"calls {sorted(calls & {'open', 'input', 'hash', 'id'})}")
    return problems


def test_c23_the_dataset_reads_nothing_from_outside_the_repository() -> None:
    assert dataset_problems((REPO_ROOT / DATASET).read_text(encoding="utf-8")) == []


SEED_VIOLATIONS = {
    "api": "from app.api.customers import CustomerCreate\n",
    "auth": "import app.auth.gate\n",
    "integrations": "from app import integrations\n",
}


@pytest.mark.parametrize("layer", sorted(SEED_VIOLATIONS))
def test_a4_contrast_the_seed_importing_a_forbidden_layer_is_found(layer: str) -> None:
    findings = lt.whole_file_findings(SEED, SEED_VIOLATIONS[layer], rows())
    assert len(findings) == 1 and f"must not depend on {layer}" in findings[0], findings


DATASET_VIOLATIONS = {
    "core-clock": "from app.core.clock import SystemClock\n",
    "data": "from app.data.models import CustomerRow\n",
    "random": "import random\n",
    "environment": "import os\n",
    "clock": "from datetime import datetime\n",
    "a-file": "x = open('values.csv').read()\n",
    "identifiers": "from uuid import uuid4\n",
}


@pytest.mark.parametrize("case", sorted(DATASET_VIOLATIONS))
def test_c23_contrast_a_dataset_reading_from_outside_is_found(case: str) -> None:
    source = DATASET_VIOLATIONS[case]
    assert dataset_problems(source) != [] or lt.whole_file_findings(DATASET, source, rows()) != []


def test_a4_contrast_the_seed_using_core_domain_services_and_data_passes() -> None:
    source = (
        "from app.core.settings import SeedSettings\nfrom app.data.customers import CustomerStore\n"
        "from app.domain.ownership import operator_creation_scope\nimport app.services\n"
    )
    assert lt.whole_file_findings(SEED, source, rows()) == []
