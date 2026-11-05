"""Does the backend's OpenAPI document still serve a client built against the previous release's?

ADR-0004 (forward to EKO-1-10) and its addendum of 2026-10-29: EKO-1-10 builds the comparison;
which release is previous, and how CI obtains its document, is EKO-1-15's (#56).

    uv run python -m tests.support.openapi_compat [--previous FILE] [--current FILE]
    uv run python -m tests.support.openapi_compat --from-record [--exclude TAG]

With `--from-record` the previous document is the one the previous published release's backend,
started by digest, serves directly (EKO-1-15, #56; tests/support/releases.py selects it); no
release reachable from `main` is "compared nothing", and a release that cannot be obtained is 2.

Without `--current`, the document is generated in-process from `create_app()`, never through
`proxy` (ADR-0003). Exit contract: 0 = compatible, or nothing compared; 1 = breaking changes;
2 = the check itself failed (a previous document that cannot be read is never "no release").

The comparison is one-way: the previous client against the new backend. A response may narrow and
a request may widen; the opposite breaks that client.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TextIO

from tests.support.api_surface import operations, real_app, resolve
from tests.support.openapi import openapi_3_errors
from tests.support.release_backend import served_document
from tests.support.releases import (
    CannotTell,
    Reachability,
    Record,
    Release,
    previous_release,
    reach_from_environment,
    record_from_environment,
)

Document = dict[str, Any]
Direction = Literal["request", "response"]
SUCCESS = re.compile(r"2(\d\d|XX)")
MAX_DEPTH = 64
PATH_PARAMETER = re.compile(r"\{([^}]*)\}")


def template(path: str) -> str:
    """`/api/visits/{id}` and `/api/visits/{visit_id}` are the same URL to a client (R-05)."""
    return PATH_PARAMETER.sub("{}", path)


class CheckFailed(Exception):
    pass


@dataclass
class Shape:
    """A schema with `$ref`, `allOf`, `const` and nullability resolved into one place."""

    types: frozenset[str] | None = None
    nullable: bool = False
    enum: list[str] | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    required: set[str] = field(default_factory=set)
    items: Any = None
    closed: bool = False
    bounds: dict[str, Any] = field(default_factory=dict)
    branches: list[Any] | None = None


# R-01: what narrows a value, by keyword. An upper bound narrows when it falls or appears, a lower
# bound when it rises or appears; `format`, `pattern` and `multipleOf` narrow on any new value.
UPPER = ("maxLength", "maxItems", "maxProperties", "maximum", "exclusiveMaximum")
LOWER = ("minLength", "minItems", "minProperties", "minimum", "exclusiveMinimum")
EXACT = ("format", "pattern", "multipleOf")


def _is_null(node: Any) -> bool:
    return isinstance(node, dict) and node.get("type") == "null" and len(node) == 1


def shape(doc: Document, node: Any, depth: int = 0) -> Shape:
    node = resolve(doc, node)
    result = Shape()
    if not isinstance(node, dict) or depth > MAX_DEPTH:
        return result
    for branch in node.get("allOf") or []:
        _merge(result, shape(doc, branch, depth + 1))
    declared = node.get("type")
    types = set(declared) if isinstance(declared, list) else {declared} if declared else set()
    result.nullable = result.nullable or "null" in types or node.get("nullable") is True
    types.discard("null")
    if types:
        result.types = frozenset(types)
    if "enum" in node:
        result.enum = [json.dumps(v, sort_keys=True) for v in node["enum"] if v is not None]
        result.nullable = result.nullable or None in node["enum"]
    if "const" in node:
        result.enum = [json.dumps(node["const"], sort_keys=True)]
    result.properties.update(node.get("properties") or {})
    result.required |= set(node.get("required") or [])
    if "items" in node:
        result.items = node["items"]
    result.closed = result.closed or node.get("additionalProperties") is False
    for key in (*UPPER, *LOWER, *EXACT, "uniqueItems"):
        if key in node:
            result.bounds[key] = node[key]
    union = [b for key in ("anyOf", "oneOf") for b in node.get(key) or []]
    if union:
        result.nullable = result.nullable or any(_is_null(resolve(doc, b)) for b in union)
        rest = [b for b in union if not _is_null(resolve(doc, b))]
        if len(rest) == 1:
            _merge(result, shape(doc, rest[0], depth + 1))
        elif rest:
            result.branches = rest
    if result.types is None and (result.properties or "items" in node):
        result.types = frozenset({"object"} if result.properties else {"array"})
    return result


def _merge(into: Shape, other: Shape) -> None:
    into.types = other.types if into.types is None else into.types
    into.nullable = into.nullable or other.nullable
    into.enum = other.enum if into.enum is None else into.enum
    into.properties.update(other.properties)
    into.required |= other.required
    into.items = other.items if into.items is None else into.items
    into.closed = into.closed or other.closed
    into.bounds = {**other.bounds, **into.bounds}
    into.branches = other.branches if into.branches is None else into.branches


def _narrower(than: dict[str, Any], bounds: dict[str, Any]) -> list[str]:
    """The keywords on which `bounds` admits less than `than` does."""
    found = []
    for key, value in bounds.items():
        before = than.get(key)
        if key in UPPER and (before is None or value < before):
            found.append(key)
        elif key in LOWER and (before is None or value > before):
            found.append(key)
        elif key in EXACT and value != before:
            found.append(key)
        elif key == "uniqueItems" and value is True and before is not True:
            found.append(key)
    return found


def _branch_key(doc: Document, node: Any) -> str:
    """A union branch is the same branch in both documents by its component, else by its type."""
    if _ref(node):
        return _ref(node).rsplit("/", 1)[-1]
    resolved = resolve(doc, node)
    return "type:" + json.dumps(resolved.get("type") if isinstance(resolved, dict) else None)


def _keyed(doc: Document, branches: list[Any]) -> dict[str, Any]:
    keyed: dict[str, Any] = {}
    for branch in branches:
        key = _branch_key(doc, branch)
        while key in keyed:
            key += "'"
        keyed[key] = branch
    return keyed


def _ref(node: Any) -> str:
    return str(node.get("$ref") or "") if isinstance(node, dict) else ""


def _covered(types: frozenset[str], by: frozenset[str]) -> bool:
    return all(t in by or (t == "integer" and "number" in by) for t in types)


@dataclass
class Comparison:
    previous: Document
    current: Document
    problems: list[str] = field(default_factory=list)
    seen: set[tuple[str, str, str]] = field(default_factory=set)

    def schema(self, old: Any, new: Any, direction: Direction, where: str, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            return
        # A component pair is compared once per operation and direction: the location grows with
        # every level, so keying on it would never stop a recursive component.
        refs = (_ref(old), _ref(new), direction)
        if refs[0] and refs[1]:
            if refs in self.seen:
                return
            self.seen.add(refs)
        p, c = shape(self.previous, old), shape(self.current, new)
        widened, narrowed = (c, p) if direction == "response" else (p, c)
        if widened.nullable and not narrowed.nullable:
            self.problems.append(
                f"{where}: may now be null"
                if direction == "response"
                else f"{where}: no longer accepts null"
            )
        self._types(p, c, direction, where)
        self._enum(p, c, direction, where)
        # A request may not admit less than before; a response may not give more.
        tighter = _narrower(p.bounds, c.bounds) if direction == "request" else []
        looser = _narrower(c.bounds, p.bounds) if direction == "response" else []
        for key in tighter:
            self.problems.append(f"{where}: request {key} narrowed")
        for key in looser:
            self.problems.append(f"{where}: response {key} widened or removed")
        self._union(p, c, direction, where, depth)
        if direction == "response":
            for name, sub in p.properties.items():
                if name not in c.properties:
                    self.problems.append(f"{where}.{name}: response property removed")
                    continue
                if name in p.required and name not in c.required:
                    self.problems.append(f"{where}.{name}: response property may now be absent")
                self.schema(sub, c.properties[name], direction, f"{where}.{name}", depth + 1)
        else:
            for name, sub in c.properties.items():
                if name not in p.properties:
                    if name in c.required:
                        self.problems.append(f"{where}.{name}: required request property added")
                    continue
                if name in c.required and name not in p.required:
                    self.problems.append(f"{where}.{name}: request property made required")
                self.schema(p.properties[name], sub, direction, f"{where}.{name}", depth + 1)
            if c.closed:
                for name in sorted(set(p.properties) - set(c.properties)):
                    self.problems.append(f"{where}.{name}: request property no longer accepted")
        if p.items is not None and c.items is not None:
            self.schema(p.items, c.items, direction, f"{where}[]", depth + 1)

    def _union(self, p: Shape, c: Shape, direction: Direction, where: str, depth: int) -> None:
        """R-01, R-05: union branches are paired and compared, never dumped as text."""
        if p.branches is None and c.branches is None:
            return
        before = _keyed(self.previous, p.branches or [])
        after = _keyed(self.current, c.branches or [])
        if direction == "response":
            for key in sorted(set(after) - set(before)):
                self.problems.append(f"{where}: response union gains the alternative {key}")
        else:
            for key in sorted(set(before) - set(after)):
                self.problems.append(f"{where}: request union loses the alternative {key}")
        for key in sorted(set(before) & set(after)):
            self.schema(before[key], after[key], direction, f"{where}<{key}>", depth + 1)

    def _types(self, p: Shape, c: Shape, direction: Direction, where: str) -> None:
        if direction == "response":
            broken = (
                c.types is None
                and p.types is not None
                or (p.types is not None and c.types is not None and not _covered(c.types, p.types))
            )
        else:
            broken = (
                p.types is None
                and c.types is not None
                or (p.types is not None and c.types is not None and not _covered(p.types, c.types))
            )
        if broken:
            old, new = sorted(p.types or {"any"}), sorted(c.types or {"any"})
            self.problems.append(f"{where}: type changed from {old} to {new}")

    def _enum(self, p: Shape, c: Shape, direction: Direction, where: str) -> None:
        if direction == "response":
            if p.enum is not None and (c.enum is None or set(c.enum) - set(p.enum)):
                added = sorted(set(c.enum or ["any value"]) - set(p.enum))
                self.problems.append(f"{where}: response enum gains {added}")
        elif c.enum is not None and (p.enum is None or set(p.enum) - set(c.enum)):
            removed = sorted(set(p.enum or ["any value"]) - set(c.enum))
            self.problems.append(f"{where}: request enum loses {removed}")

    def operation(
        self, name: str, old: tuple[Any, Any], new: tuple[Any, Any], paths: tuple[str, str]
    ) -> None:
        self.seen = set()
        self._parameters(name, old, new, paths)
        self._body(name, old[1], new[1])
        self._responses(name, old[1], new[1])

    def _params(self, doc: Document, path: str, item: Any, op: Any) -> dict[tuple[str, str], Any]:
        # R-05: a path parameter is its position in the template; its name is not on the wire.
        positions = {name: f"#{i}" for i, name in enumerate(PATH_PARAMETER.findall(path))}
        found = {}
        for parameter in [*(item.get("parameters") or []), *(op.get("parameters") or [])]:
            parameter = resolve(doc, parameter)
            where, name = str(parameter.get("in")), str(parameter.get("name"))
            found[(where, positions.get(name, name) if where == "path" else name)] = parameter
        return found

    def _parameters(
        self, name: str, old: tuple[Any, Any], new: tuple[Any, Any], paths: tuple[str, str]
    ) -> None:
        before = self._params(self.previous, paths[0], *old)
        for key, parameter in sorted(self._params(self.current, paths[1], *new).items()):
            where = f"{name}: {key[0]} parameter {key[1]!r}"
            if key not in before:
                if parameter.get("required"):
                    self.problems.append(f"{where}: required parameter added")
                continue
            if parameter.get("required") and not before[key].get("required"):
                self.problems.append(f"{where}: parameter made required")
            self.schema(before[key].get("schema"), parameter.get("schema"), "request", where)

    def _body(self, name: str, old: Any, new: Any) -> None:
        before = resolve(self.previous, old.get("requestBody")) or {}
        after = resolve(self.current, new.get("requestBody")) or {}
        if after.get("required") and not before.get("required"):
            self.problems.append(f"{name}: request body made required")
        for media, content in (before.get("content") or {}).items():
            if not after:
                continue
            if media not in (after.get("content") or {}):
                self.problems.append(f"{name}: request media type {media} no longer accepted")
                continue
            new_schema = after["content"][media].get("schema")
            self.schema((content or {}).get("schema"), new_schema, "request", f"{name}: body")

    def _responses(self, name: str, old: Any, new: Any) -> None:
        after = new.get("responses") or {}
        for status, response in (old.get("responses") or {}).items():
            if not SUCCESS.fullmatch(str(status)):
                continue
            if status not in after:
                self.problems.append(f"{name}: success status {status} removed")
                continue
            before_content = resolve(self.previous, response).get("content") or {}
            after_content = resolve(self.current, after[status]).get("content") or {}
            for media, content in before_content.items():
                where = f"{name}: response {status} {media}"
                if media not in after_content:
                    self.problems.append(f"{where}: media type removed")
                    continue
                new_schema = after_content[media].get("schema")
                self.schema((content or {}).get("schema"), new_schema, "response", where)


def breaking_changes(previous: Document, current: Document) -> list[str]:
    """Every change that breaks a client built against `previous`, per operation."""
    comparison = Comparison(previous, current)
    after = {(m, template(p)): (p, item, op) for m, p, item, op in operations(current)}
    for method, path, item, op in sorted(operations(previous), key=lambda o: (o[1], o[0])):
        name = f"{method} {path}"
        if (method, template(path)) not in after:
            comparison.problems.append(f"{name}: operation removed")
            continue
        current_path, *new = after[(method, template(path))]
        comparison.operation(name, (item, op), (new[0], new[1]), (path, current_path))
    return comparison.problems


def load(path: str) -> Document:
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CheckFailed(f"{path}: cannot be read as JSON ({type(exc).__name__})") from None
    errors = openapi_3_errors(document)
    if errors or not isinstance(document, dict):
        raise CheckFailed(f"{path}: not a valid OpenAPI 3.x document ({errors[:1]})")
    return document


PREFIX = "openapi-compat:"


def report(out: TextIO, line: str) -> None:
    """The command's result, one line each: the CLI's output, not logging."""
    out.write(line + "\n")


def validated(document: Any, where: str) -> Document:
    errors = openapi_3_errors(document)
    if errors or not isinstance(document, dict):
        raise CheckFailed(f"{where}: not a valid OpenAPI 3.x document ({errors[:1]})")
    return document


def main(
    argv: list[str],
    out: TextIO = sys.stdout,
    record: Record | None = None,
    reach: Reachability | None = None,
    served: Callable[[Release], Any] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.support.openapi_compat")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--previous", help="the previous release's OpenAPI document (JSON)")
    source.add_argument(
        "--from-record",
        action="store_true",
        help="the previous published release's document, as its backend serves it (EKO-1-15)",
    )
    parser.add_argument("--exclude", help="with --from-record: the release being built")
    parser.add_argument("--current", help="default: generated in-process from create_app()")
    args = parser.parse_args(argv)
    if args.exclude and not args.from_record:
        parser.error("--exclude needs --from-record")
    try:
        current = load(args.current) if args.current else real_app().openapi()
        if args.from_record:
            found = previous_release(
                record or record_from_environment(), reach or reach_from_environment(), args.exclude
            )
            if found is None:
                report(
                    out,
                    f"{PREFIX} no published release is reachable from main, so it compared "
                    "nothing.",
                )
                return 0
            report(out, f"{PREFIX} previous release {found.tag} at {found.commit}")
            previous = validated((served or served_document)(found), found.tag)
        elif args.previous is None:
            report(
                out,
                f"{PREFIX} no previous release document was supplied, so it compared nothing. "
                "Which release is previous, and how CI obtains its document, is EKO-1-15's (#56).",
            )
            return 0
        else:
            previous = load(args.previous)
    except (CheckFailed, CannotTell) as exc:
        report(out, f"{PREFIX} the check itself failed: {exc}")
        return 2
    problems = breaking_changes(previous, current)
    for problem in problems:
        report(out, f"BREAKING: {problem}")
    count = len(operations(previous))
    verdict = f"{len(problems)} breaking change(s)" if problems else "no breaking change"
    report(out, f"{PREFIX} compared {count} operation(s) of the previous release: {verdict}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
