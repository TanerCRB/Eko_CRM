"""EKO-1-13 K-01, QA addition: the `postgres` command sets no log setting the addendum's value table
does not list (ADR-0005 addendum of 2026-11-02, *PostgreSQL: the values*: "The settings not listed
keep the pinned image's defaults").

`test_adr0005_c3_postgres_settings_in_release` checks that every row of the table is a literal
`-c` pair with the table's value. It does not look at pairs outside the table, so a pair such as
`debug_print_parse=on` or `log_statement_stats=on` (each writes statement-derived text at LOG,
which `log_min_messages = log` lets through) passed it. Mutation EKO-1-13/M46 showed that.

Contrast: the released command passes; the same command with one such pair added fails.
"""

import re

import pytest
import yaml

from tests.static.test_adr0005_c3_postgres_settings_in_release import (
    COMPOSE,
    command_pairs,
    value_table,
)

# Settings that make the server write a line: every `log_*` parameter, the collector, the
# debug printers and the syslog/event-log destinations' own settings.
WRITES_A_LINE = re.compile(
    r"^(log_[a-z_]+|logging_collector|debug_print_[a-z]+|debug_pretty_print|syslog_[a-z_]+|"
    r"event_source|trace_[a-z_]+)$"
)
# The two pairs the command carries for ADR-0004-C28; they write nothing.
NOT_LOG_SETTINGS = {"max_connections", "superuser_reserved_connections"}


def postgres_command(compose_text: str) -> list[str]:
    source = yaml.safe_load(compose_text)
    return [str(word) for word in source["services"]["postgres"].get("command") or []]


def outside_the_table(compose_text: str) -> list[str]:
    pairs, _ = command_pairs(postgres_command(compose_text))
    table = value_table()
    problems = []
    for name in sorted(pairs):
        if name in table or name in NOT_LOG_SETTINGS:
            continue
        if WRITES_A_LINE.match(name):
            problems.append(f"{name}: a log setting the value table does not list")
        else:
            problems.append(f"{name}: a -c pair neither in the table nor known to write nothing")
    return problems


def test_adr0005_c3_qa_no_log_setting_outside_the_table() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert outside_the_table(compose) == []
    # Not vacuous: the command was read, with every row of the table and the two C28 pairs.
    assert len(command_pairs(postgres_command(compose))[0]) == len(value_table()) + 2


@pytest.mark.parametrize(
    "pair", ["debug_print_parse=on", "log_statement_stats=on", "log_parser_stats=on"]
)
def test_adr0005_c3_qa_no_log_setting_outside_the_table_contrast(pair: str) -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    anchor = "      - log_timezone=UTC\n"
    assert compose.count(anchor) == 1
    planted = compose.replace(anchor, f"{anchor}      - -c\n      - {pair}\n")
    problems = outside_the_table(planted)
    assert problems == [f"{pair.split('=')[0]}: a log setting the value table does not list"]
