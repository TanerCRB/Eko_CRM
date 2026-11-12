"""EKO-1-13 K-01, static half: every setting of the ADR-0005 addendum's value table (2026-11-02,
*PostgreSQL: the values*) is a literal `-c` pair in the `postgres` service's command, with the
table's value, and no log setting is made anywhere else: no Compose interpolation, not in the
environment-file generator, not in the init content (beyond its password session's two `SET`s),
not in a `postgresql.conf`, an `ALTER SYSTEM`, `ALTER DATABASE … SET` or `ALTER ROLE … SET`.

The table is read from the ADR, so the release and the decision cannot drift apart unseen.
Contrast: each planted fixture below breaks one rule and fails the check.
"""

import re
from typing import Any

import pytest
import yaml

from tests.support.repo import REPO_ROOT, tracked_files

ADR = REPO_ROOT / "docs" / "architecture" / "decisions" / "ADR-0005-personal-data.md"
COMPOSE = REPO_ROOT / "compose.yaml"
ENV_GENERATOR = REPO_ROOT / "scripts" / "dev-env.sh"
TABLE_START = "- **PostgreSQL: the values.**"
TABLE_END = "- **PostgreSQL: what its log is, and what a line holds.**"
ROW = re.compile(r"^\s*\| `(?P<name>[a-z_]+)` \| `(?P<value>[^`]*)` \|", re.MULTILINE)
# Log settings by name: every `log_*` parameter, the collector and the debug printers.
LOG_SETTING = re.compile(r"\b(log_[a-z_]+|logging_collector|debug_print_[a-z]+)\b", re.IGNORECASE)
PER_SCOPE = re.compile(
    r"ALTER\s+(SYSTEM|DATABASE\s+\S+|ROLE\s+\S+(\s+IN\s+DATABASE\s+\S+)?)\s+SET\s+"
    r"(log_[a-z_]+|logging_collector)",
    re.IGNORECASE,
)
INIT_SESSION_SETS = ["SET log_statement = 'none';", "SET log_min_error_statement = 'panic';"]


def value_table() -> dict[str, str]:
    text = ADR.read_text(encoding="utf-8")
    section = text[text.index(TABLE_START) : text.index(TABLE_END)]
    return {row["name"]: row["value"] for row in ROW.finditer(section)}


def command_pairs(command: list[str]) -> tuple[dict[str, str], list[str]]:
    pairs, problems = {}, []
    for index, word in enumerate(command):
        if word == "-c":
            name, _, value = command[index + 1].partition("=")
            if name in pairs:
                problems.append(f"{name}: set twice on the command line")
            pairs[name] = value
    return pairs, problems


def release_problems(compose_text: str, generator_text: str, conf_files: list[str]) -> list[str]:
    source: dict[str, Any] = yaml.safe_load(compose_text)
    command = [str(w) for w in source["services"]["postgres"].get("command") or []]
    pairs, problems = command_pairs(command)
    for name, value in value_table().items():
        if name not in pairs:
            problems.append(f"{name}: not a -c pair of the postgres command")
        elif pairs[name] != value:
            problems.append(f"{name}: {pairs[name]!r}, the table says {value!r}")
    for name, value in pairs.items():
        if "$" in value or "$" in name:
            problems.append(f"{name}: interpolated ({value!r})")
    init = source.get("configs", {}).get("postgres-init", {}).get("content", "")
    init_logs = [line.strip() for line in init.splitlines() if LOG_SETTING.search(line)]
    if init_logs != INIT_SESSION_SETS:
        problems.append(f"init content log settings {init_logs}, not only {INIT_SESSION_SETS}")
    for match in PER_SCOPE.finditer(compose_text):
        problems.append(f"per-scope log setting: {match.group(0)!r}")
    for name in sorted(set(re.findall(r"\$\{([A-Za-z0-9_]+)", compose_text))):
        if LOG_SETTING.search(name) or name.upper().startswith(("PG", "POSTGRES_LOG", "LOG")):
            problems.append(f"compose reads {name} from the environment file")
    if LOG_SETTING.search(generator_text):
        problems.append("the environment-file generator names a log setting")
    problems += [
        f"{path}: a PostgreSQL configuration file in the repository" for path in conf_files
    ]
    return problems


def conf_files() -> list[str]:
    return [p for p in tracked_files() if p.rsplit("/", 1)[-1].startswith("postgresql")]


def released() -> tuple[str, str]:
    return COMPOSE.read_text(encoding="utf-8"), ENV_GENERATOR.read_text(encoding="utf-8")


def test_adr0005_c3_postgres_settings_in_release_table_is_read() -> None:
    table = value_table()
    assert len(table) == 23, table
    assert table["log_min_messages"] == "log"
    assert table["log_line_prefix"] == "%m [%p] %e %q%u@%d %h "


def test_adr0005_c3_postgres_settings_in_release() -> None:
    compose, generator = released()
    assert release_problems(compose, generator, conf_files()) == []


# Planted contrasts: (old, new) applied once to compose.yaml, or a generator / conf file added.
CONNECT = "\\connect eko\n"
PLANTS: dict[str, tuple[str, str]] = {
    "value-changed": ("- log_min_error_statement=panic", "- log_min_error_statement=error"),
    "pair-removed": ("\n      - -c\n      - log_parameter_max_length_on_error=0", ""),
    "interpolated": ("log_min_messages=log", "log_min_messages=${PG_LOG_LEVEL:-log}"),
    "alter-database": (
        CONNECT,
        CONNECT + "      ALTER DATABASE eko SET log_min_messages = 'log';\n",
    ),
    "alter-role": (CONNECT, CONNECT + "      ALTER ROLE eko_app SET log_statement = 'none';\n"),
    "init-session-set-dropped": ("      SET log_min_error_statement = 'panic';\n", ""),
}


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_adr0005_c3_postgres_settings_in_release_contrast(plant: str) -> None:
    compose, generator = released()
    old, new = PLANTS[plant]
    assert compose.count(old) == 1, f"{plant}: {old!r} must occur once"
    assert release_problems(compose.replace(old, new), generator, conf_files()) != []


def test_adr0005_c3_postgres_settings_in_release_contrast_generator_and_conf() -> None:
    compose, generator = released()
    assert release_problems(compose, generator + "\nLOG_MIN_MESSAGES=error\n", []) != []
    assert release_problems(compose, generator, ["postgres/postgresql.conf"]) != []
