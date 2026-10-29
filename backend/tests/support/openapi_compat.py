"""Does the backend's OpenAPI document still serve a client built against the previous release's?

ADR-0004 (forward to EKO-1-10) and its addendum of 2026-10-29: EKO-1-10 builds the comparison;
which release is previous, and how CI obtains its document, is EKO-1-15's (#56).

    uv run python -m tests.support.openapi_compat [--previous FILE] [--current FILE]

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
from dataclasses import dataclass, field
from typing import Any, Literal, TextIO

from tests.support.api_surface import operations, real_app, resolve
from tests.support.openapi import openapi_3_errors

Document = dict[str, Any]
Direction = Literal["request", "response"]
SUCCESS = re.compile(r"2(\d\d|XX)")
MAX_DEPTH = 64


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
    variants: list[str] | None = None


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
    union = [resolve(doc, b) for key in ("anyOf", "oneOf") for b in node.get(key) or []]
    if union:
        result.nullable = result.nullable or any(_is_null(b) for b in union)
        rest = [b for b in union if not _is_null(b)]
        if len(rest) == 1:
            _merge(result, shape(doc, rest[0], depth + 1))
        elif rest:
            result.variants = sorted(json.dumps(b, sort_keys=True) for b in rest)
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
    into.variants = other.variants if into.variants is None else into.variants


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
        if p.variants is not None and c.variants is not None:
            small, large = (
                (c.variants, p.variants) if direction == "response" else (p.variants, c.variants)
            )
            if not set(small) <= set(large):
                self.problems.append(f"{where}: the alternatives of a union changed")
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

    def operation(self, name: str, old: tuple[Any, Any], new: tuple[Any, Any]) -> None:
        self.seen = set()
        self._parameters(name, old, new)
        self._body(name, old[1], new[1])
        self._responses(name, old[1], new[1])

    def _params(self, doc: Document, item: Any, op: Any) -> dict[tuple[str, str], Any]:
        found = {}
        for parameter in [*(item.get("parameters") or []), *(op.get("parameters") or [])]:
            parameter = resolve(doc, parameter)
            found[(str(parameter.get("in")), str(parameter.get("name")))] = parameter
        return found

    def _parameters(self, name: str, old: tuple[Any, Any], new: tuple[Any, Any]) -> None:
        before = self._params(self.previous, *old)
        for key, parameter in sorted(self._params(self.current, *new).items()):
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
    after = {(m, p): (item, op) for m, p, item, op in operations(current)}
    for method, path, item, op in sorted(operations(previous), key=lambda o: (o[1], o[0])):
        name = f"{method} {path}"
        if (method, path) not in after:
            comparison.problems.append(f"{name}: operation removed")
            continue
        comparison.operation(name, (item, op), after[(method, path)])
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


def main(argv: list[str], out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.support.openapi_compat")
    parser.add_argument("--previous", help="the previous release's OpenAPI document (JSON)")
    parser.add_argument("--current", help="default: generated in-process from create_app()")
    args = parser.parse_args(argv)
    try:
        current = load(args.current) if args.current else real_app().openapi()
        if args.previous is None:
            print(
                f"{PREFIX} no previous release document was supplied, so it compared nothing. "
                "Which release is previous, and how CI obtains its document, is EKO-1-15's (#56).",
                file=out,
            )
            return 0
        previous = load(args.previous)
    except CheckFailed as exc:
        print(f"{PREFIX} the check itself failed: {exc}", file=out)
        return 2
    problems = breaking_changes(previous, current)
    for problem in problems:
        print(f"BREAKING: {problem}", file=out)
    count = len(operations(previous))
    verdict = f"{len(problems)} breaking change(s)" if problems else "no breaking change"
    print(f"{PREFIX} compared {count} operation(s) of the previous release: {verdict}", file=out)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
