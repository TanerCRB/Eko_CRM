"""The documented line forms (docs/operations/log-format.md) and checks of lines against them.

The key sets are read from the document, never restated here, so a line that drifts from the
documented form fails whichever side moved.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from tests.support.repo import REPO_ROOT

LOG_FORMAT_DOC = REPO_ROOT / "docs" / "operations" / "log-format.md"
_ROW = re.compile(r"^\| `(?P<line>[a-z]+\.[a-z]+)` \| (?P<keys>.+?) \|\s*$", re.MULTILINE)
_KEY = re.compile(r"`(?P<key>[a-z_.]+)`(?P<optional> \*\(optional\)\*)?")
CORRELATION_ID = re.compile(r"[0-9a-f]{32}")
CODE_LOCATION = re.compile(r"[A-Za-z0-9_./<>-]+:[A-Za-z0-9_.<>]+:[0-9]+")
TS_MICRO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
TS_NANO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9}Z")


@dataclass(frozen=True)
class KeySet:
    ordered: tuple[str, ...]
    optional: frozenset[str]

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(k for k in self.ordered if k not in self.optional)


def documented_key_sets() -> dict[str, KeySet]:
    text = LOG_FORMAT_DOC.read_text(encoding="utf-8")
    sets = {}
    for row in _ROW.finditer(text):
        keys = list(_KEY.finditer(row["keys"]))
        sets[row["line"]] = KeySet(
            tuple(k["key"] for k in keys), frozenset(k["key"] for k in keys if k["optional"])
        )
    return sets


def flatten(line: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """`{"request": {"uri": …}}` as `{"request.uri": …}`, in the line's own key order."""
    flat: dict[str, Any] = {}
    for key, value in line.items():
        if isinstance(value, dict):
            flat.update(flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def json_lines(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The JSON objects of a log, and every other non-empty line."""
    objects, others = [], []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except ValueError:
            others.append(raw)
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
        else:
            others.append(raw)
    return objects, others


def app_line_problems(line: dict[str, Any]) -> list[str]:
    """One backend/migrate/worker line against its documented key set and value forms."""
    event = line.get("event")
    sets = documented_key_sets()
    form = sets.get(f"app.{event}")
    if form is None:
        return [f"unknown event {event!r}: {line}"]
    keys = list(line)
    problems = []
    if not set(form.required) <= set(keys) or not set(keys) <= set(form.ordered):
        problems.append(f"keys {keys} are not the documented {list(form.ordered)}")
    if [k for k in keys if k in form.ordered] != [k for k in form.ordered if k in keys]:
        problems.append(f"key order {keys} differs from {list(form.ordered)}")
    if not TS_MICRO.fullmatch(str(line.get("ts"))):
        problems.append(f"ts {line.get('ts')!r}")
    if line.get("process") not in {"backend", "migrate", "worker"}:
        problems.append(f"process {line.get('process')!r}")
    if "correlation_id" in line and not CORRELATION_ID.fullmatch(str(line["correlation_id"])):
        problems.append(f"correlation_id {line['correlation_id']!r}")
    if event == "error" and not CODE_LOCATION.fullmatch(str(line.get("at"))):
        problems.append(f"at {line.get('at')!r}")
    return problems


def proxy_line_problems(line: dict[str, Any], form_name: str) -> list[str]:
    """One Caddy line against `proxy.access` or `proxy.error`: the exact key set."""
    form = documented_key_sets()[form_name]
    flat = flatten(line)
    problems = []
    if set(flat) != set(form.ordered):
        problems.append(f"keys {sorted(flat)} are not {sorted(form.ordered)}")
    if not TS_NANO.fullmatch(str(line.get("ts"))):
        problems.append(f"ts {line.get('ts')!r}")
    if "?" in str(flat.get("request.uri", "")):
        problems.append(f"uri {flat.get('request.uri')!r} holds a query")
    return problems


def leaks(text: str, *needles: str) -> list[str]:
    """Which needles occur in a log, as written or once its JSON escapes are decoded: a non-ASCII
    or control-character value is escaped in a JSON line, so the raw text alone would miss it."""
    objects, _ = json_lines(text)
    decoded = text + "\n" + json.dumps(objects, ensure_ascii=False)
    return sorted({n for n in needles if n and n in decoded})
