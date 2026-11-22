"""EKO-1-35: the frontend's hand-written API types against the OpenAPI document of this commit.

ADR-0001 Constraint 3 and checklist rule 12. The document is generated in-process from
`create_app()` (`api_surface.real_app`), never read from a stored copy; the files under
`frontend/src/api/` are read as data (rule 7 is about imports and paths, not this).

Three checks, each returning its findings: K-01 compares each type of `CHECKED` with its target;
K-02 compares the country list and its default with the request enum of `CustomerCreate.country`;
K-03 fails an exported type that is neither checked nor on `FRONTEND_ONLY`. The TypeScript reader
reads a small subset and fails closed: a declaration outside it is a finding, never skipped.

"Agrees" is G-A A: identical, except that a response field the frontend does not declare, a
request enum gaining a value, and a request field the frontend always sends becoming optional
pass. `pipeline` class in the sensitive-paths register: a pull request runs its own copy.
"""

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.support.api_surface import real_app
from tests.support.repo import REPO_ROOT

Files = Mapping[str, str]
Document = dict[str, Any]
API_DIR = "frontend/src/api/"
SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
AUTH = "frontend/src/api/auth.ts"
CUSTOMERS = "frontend/src/api/customers.ts"
CLIENT = "frontend/src/api/client.ts"
COUNTRY_FILE = "frontend/src/api/countries.ts"
REFERENCE = "frontend/src/api/reference.ts"
REQUEST, RESPONSE = "request", "response"
# EKO-3-04 (Q-6 A): the query parameters a frontend type says it sends. Judged as a request, except
# that an optional parameter it does not send passes: a query parameter left out is just absent.
QUERY = "query"
QUERY_TARGET = "query"


@dataclass(frozen=True)
class Pair:
    """A frontend type and what it mirrors: a component, `Component.property`,
    `METHOD /path status` (that response's JSON schema), or `METHOD /path query` (that
    operation's query parameters, as an object whose properties are the parameters)."""

    file: str
    name: str
    target: str
    direction: str


# G-C A. Request types are judged as "what the frontend sends is accepted", response types as
# "what the frontend reads is sent".
CHECKED: tuple[Pair, ...] = (
    Pair(AUTH, "SessionInfo", "SessionInfo", RESPONSE),
    Pair(AUTH, "LoggedOut", "LoggedOut", RESPONSE),
    Pair(AUTH, "Problem", "Problem", RESPONSE),
    Pair(CUSTOMERS, "ContactKind", "ContactIn.kind", REQUEST),
    Pair(CUSTOMERS, "ContactInput", "ContactIn", REQUEST),
    Pair(CUSTOMERS, "CustomerInput", "CustomerCreate", REQUEST),
    Pair(CUSTOMERS, "ContactRecord", "ContactOut", RESPONSE),
    Pair(CUSTOMERS, "CustomerRecord", "CustomerOut", RESPONSE),
    Pair(CUSTOMERS, "CustomerSummary", "CustomerItem", RESPONSE),
    Pair(CUSTOMERS, "CustomerList", "CustomerList", RESPONSE),
    Pair(CUSTOMERS, "ValidationProblem", "POST /api/customers 422", RESPONSE),
    # EKO-3-02 (Issue #161): the voivodeship reference client.
    Pair(REFERENCE, "VoivodeshipList", "VoivodeshipList", RESPONSE),
    Pair(REFERENCE, "VoivodeshipEntry", "VoivodeshipOut", RESPONSE),
    # EKO-3-04 (Issue #215, Q-6 A): the list's search parameters the SPA sends.
    Pair(CUSTOMERS, "CustomerListQuery", "GET /api/customers query", QUERY),
)

# K-03: exported types with no schema behind them, keyed by file and name. Adding one is an edit
# here and to the K-03 test, which the Reviewer sees.
FRONTEND_ONLY: frozenset[tuple[str, str]] = frozenset(
    {
        (AUTH, "SessionRead"),
        (AUTH, "LogoutResult"),
        (CUSTOMERS, "RejectedField"),
        (CUSTOMERS, "CreateResult"),
        (CUSTOMERS, "ReadResult"),
        (CUSTOMERS, "ListResult"),
        (CLIENT, "ApiResponse"),
        (CLIENT, "RequestOptions"),
        # EKO-3-02 (Issue #161): frontend-only result union of the reference client.
        (REFERENCE, "VoivodeshipsResult"),
    }
)

# Request fields typed as a plain string whose enum K-02 checks as a list instead (A-01):
# `CustomerInput.country` against `CustomerCreate.country`.
VALUE_LISTS = frozenset({"CustomerInput.country"})
COUNTRY_COMPONENT, COUNTRY_PROPERTY = "CustomerCreate", "country"


class Unreadable(Exception):
    """A declaration or schema outside what the reader reads: reported, never skipped."""


def api_sources(root: Path = REPO_ROOT) -> dict[str, str]:
    """Every file under `frontend/src/api/`, subdirectories included, CRLF normalised."""
    base = root / API_DIR
    if not base.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        .decode("utf-8", errors="replace")
        .replace("\r\n", "\n")
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def sources_in(files: Files) -> dict[str, str]:
    return {path: text for path, text in sorted(files.items()) if path.startswith(API_DIR)}


# The TypeScript reader ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    kind: str  # name, string, number, template, regex, punct
    text: str
    line: int
    substituted: bool = False


# After these a `/` starts a regular expression, not a division.
REGEX_AFTER_NAMES = frozenset(
    {"return", "typeof", "case", "in", "of", "new", "delete", "void", "throw", "else", "do"}
    | {"yield", "await", "instanceof"}
)
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "b": "\b", "f": "\f", "v": "\v"}
NAME_START = re.compile(r"[A-Za-z_$]")
NAME = re.compile(r"[A-Za-z0-9_$]*")
NUMBER = re.compile(r"0[xXoObB][0-9a-fA-F_]+|[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9]+)?")


class Lexer:
    def __init__(self, text: str) -> None:
        self.text, self.at, self.depth = text, 0, 0
        self.tokens: list[Token] = []
        # The brace depth at which each open `${` of a template began.
        self.substitutions: list[int] = []

    def line(self) -> int:
        return self.text.count("\n", 0, self.at) + 1

    def run(self) -> list[Token]:
        text = self.text
        while self.at < len(text):
            char = text[self.at]
            if char.isspace():
                self.at += 1
            elif text.startswith("//", self.at):
                end = text.find("\n", self.at)
                self.at = len(text) if end < 0 else end
            elif text.startswith("/*", self.at):
                end = text.find("*/", self.at + 2)
                if end < 0:
                    raise Unreadable(f"line {self.line()}: unterminated comment")
                self.at = end + 2
            elif char in "'\"":
                self.string(char)
            elif char == "`":
                self.at += 1
                self.template(self.line())
            elif char == "}" and self.substitutions and self.substitutions[-1] == self.depth:
                self.substitutions.pop()
                self.at += 1
                self.template(self.line(), continued=True)
            elif char == "/" and self.regex_allowed():
                self.regex()
            elif NAME_START.match(char):
                match = NAME.match(text, self.at + 1)
                end = match.end() if match else self.at + 1
                self.tokens.append(Token("name", text[self.at : end], self.line()))
                self.at = end
            elif char.isdigit():
                number = NUMBER.match(text, self.at)
                end = number.end() if number else self.at + 1
                self.tokens.append(Token("number", text[self.at : end], self.line()))
                self.at = end
            else:
                self.depth += {"{": 1, "}": -1}.get(char, 0)
                self.tokens.append(Token("punct", char, self.line()))
                self.at += 1
        if self.substitutions:
            raise Unreadable("unterminated template")
        return self.tokens

    def regex_allowed(self) -> bool:
        if not self.tokens:
            return True
        last = self.tokens[-1]
        if last.kind == "name":
            return last.text in REGEX_AFTER_NAMES
        return last.kind == "punct" and last.text not in ")]}"

    def string(self, quote: str) -> None:
        line, at, value = self.line(), self.at + 1, []
        while True:
            if at >= len(self.text) or self.text[at] == "\n":
                raise Unreadable(f"line {line}: unterminated string")
            char = self.text[at]
            if char == quote:
                break
            if char == "\\":
                if at + 1 >= len(self.text):
                    raise Unreadable(f"line {line}: unterminated string")
                escaped = self.text[at + 1]
                if escaped in "xu":
                    raise Unreadable(
                        f"line {line}: a \\{escaped} escape the reader does not decode"
                    )
                value.append(ESCAPES.get(escaped, escaped))
                at += 2
                continue
            value.append(char)
            at += 1
        self.tokens.append(Token("string", "".join(value), line))
        self.at = at + 1

    def template(self, line: int, continued: bool = False) -> None:
        at, raw = self.at, []
        while True:
            if at >= len(self.text):
                raise Unreadable(f"line {line}: unterminated template")
            char = self.text[at]
            if char == "\\":
                raw.append(self.text[at : at + 2])
                at += 2
            elif char == "`":
                self.tokens.append(Token("template", "".join(raw), line, continued))
                self.at = at + 1
                return
            elif self.text.startswith("${", at):
                self.tokens.append(Token("template", "".join(raw), line, True))
                self.substitutions.append(self.depth)
                self.at = at + 2
                return
            else:
                raw.append(char)
                at += 1

    def regex(self) -> None:
        line, at, in_class = self.line(), self.at + 1, False
        while True:
            if at >= len(self.text) or self.text[at] == "\n":
                raise Unreadable(f"line {line}: unterminated regular expression")
            char = self.text[at]
            if char == "\\":
                at += 2
                continue
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                break
            at += 1
        flags = NAME.match(self.text, at + 1)
        end = flags.end() if flags else at + 1
        self.tokens.append(Token("regex", self.text[self.at : end], line))
        self.at = end


def is_text(tokens: list[Token], index: int, *texts: str) -> bool:
    return index < len(tokens) and tokens[index].kind != "string" and tokens[index].text in texts


def name_at(tokens: list[Token], index: int, what: str) -> str:
    if index >= len(tokens) or tokens[index].kind != "name":
        line = tokens[min(index, len(tokens) - 1)].line if tokens else 1
        raise Unreadable(f"line {line}: {what} without a name the reader can read")
    return tokens[index].text


@dataclass(frozen=True)
class Prim:
    name: str  # string, number, boolean, null, unknown


@dataclass(frozen=True)
class Lit:
    value: str | float | bool


@dataclass(frozen=True)
class Arr:
    item: "Type"


@dataclass(frozen=True)
class Field:
    name: str
    type: "Type"
    optional: bool


@dataclass(frozen=True)
class Obj:
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Union:
    alternatives: tuple["Type", ...]


@dataclass(frozen=True)
class Ref:
    """A named frontend type, or (`component=True`) a component of the document."""

    name: str
    component: bool = False


Type = Prim | Lit | Arr | Obj | Union | Ref
FRONTEND_PRIMITIVES = frozenset({"string", "number", "boolean", "null", "unknown"})


class TypeParser:
    def __init__(self, tokens: list[Token], at: int) -> None:
        self.tokens, self.at = tokens, at

    def peek(self, *texts: str) -> bool:
        return is_text(self.tokens, self.at, *texts)

    def take(self, text: str) -> None:
        if not self.peek(text):
            raise Unreadable(f"{self.where()}: expected `{text}`")
        self.at += 1

    def where(self) -> str:
        if self.at >= len(self.tokens):
            return "end of file"
        token = self.tokens[self.at]
        return f"line {token.line}, `{token.text}`"

    def declaration(self, keyword: str) -> Type:
        if keyword == "interface":
            if not self.peek("{"):
                raise Unreadable(f"{self.where()}: an interface with `extends` or parameters")
            return self.object()
        if not self.peek("="):
            raise Unreadable(f"{self.where()}: a type alias with parameters")
        self.at += 1
        found = self.type()
        self.take(";")
        return found

    def type(self) -> Type:
        if self.peek("|"):
            self.at += 1
        alternatives = [self.postfix()]
        while self.peek("|"):
            self.at += 1
            alternatives.append(self.postfix())
        if self.peek("&"):
            raise Unreadable(f"{self.where()}: an intersection")
        return alternatives[0] if len(alternatives) == 1 else Union(tuple(alternatives))

    def postfix(self) -> Type:
        found = self.primary()
        while self.peek("["):
            self.at += 1
            if not self.peek("]"):
                raise Unreadable(f"{self.where()}: an indexed access type")
            self.at += 1
            found = Arr(found)
        return found

    def primary(self) -> Type:
        if self.at >= len(self.tokens):
            raise Unreadable("a type cut off at the end of the file")
        token = self.tokens[self.at]
        self.at += 1
        if token.kind == "string":
            return Lit(token.text)
        if token.kind == "number":
            try:
                return Lit(float(token.text))
            except ValueError:
                raise Unreadable(f"line {token.line}: a number the reader does not read") from None
        if token.kind == "name" and token.text in FRONTEND_PRIMITIVES:
            return Prim(token.text)
        if token.kind == "name" and token.text in ("true", "false"):
            return Lit(token.text == "true")
        if token.kind == "punct" and token.text == "{":
            self.at -= 1
            return self.object()
        if token.kind == "punct" and token.text == "(" and not self.peek(")"):
            inner = self.type()
            self.take(")")
            if self.peek("="):
                raise Unreadable(f"{self.where()}: a function type")
            return inner
        if token.kind == "name" and not self.peek("<", ".") and token.text not in RESERVED:
            return Ref(token.text)
        raise Unreadable(f"line {token.line}, `{token.text}`: not a type the reader reads")

    def object(self) -> Obj:
        self.take("{")
        fields: list[Field] = []
        while not self.peek("}"):
            if self.at >= len(self.tokens):
                raise Unreadable("an object type cut off at the end of the file")
            token = self.tokens[self.at]
            if token.kind not in ("name", "string") or token.text in MODIFIERS:
                raise Unreadable(f"{self.where()}: a member the reader does not read")
            self.at += 1
            optional = self.peek("?")
            if optional:
                self.at += 1
            self.take(":")
            if any(field.name == token.text for field in fields):
                raise Unreadable(f"line {token.line}: `{token.text}` declared twice")
            fields.append(Field(token.text, self.type(), optional))
            if self.peek(";", ","):
                self.at += 1
            elif not self.peek("}"):
                raise Unreadable(f"{self.where()}: expected `;` or `}}`")
        self.at += 1
        return Obj(tuple(fields))


# Names that are not a plain reference to a declared type: read as "cannot read", never as a name.
RESERVED = frozenset(
    {"any", "never", "undefined", "void", "object", "symbol", "bigint", "keyof", "typeof"}
    | {"infer", "readonly", "unique", "asserts", "is", "new", "abstract", "this"}
)
MODIFIERS = frozenset({"readonly", "get", "set", "static", "public", "private", "protected"})


@dataclass
class SourceFile:
    tokens: list[Token]
    declarations: dict[str, tuple[str, int]]  # type name: (keyword, index after its name)


def read_file(text: str) -> SourceFile:
    """Every type declaration (exported or not) of the file, by name."""
    tokens = Lexer(text).run()
    declarations: dict[str, tuple[str, int]] = {}
    for index, token in enumerate(tokens):
        if token.kind != "name" or token.text not in ("interface", "type"):
            continue
        if is_text(tokens, index - 1, ".") or is_text(tokens, index + 1, ":", "=", "{", "*"):
            continue
        if index + 1 < len(tokens) and tokens[index + 1].kind == "name":
            name = tokens[index + 1].text
            if name in declarations:
                raise Unreadable(f"line {token.line}: `{name}` declared twice")
            declarations[name] = (token.text, index + 2)
    return SourceFile(tokens, declarations)


def declared_type(source: SourceFile, name: str) -> Type:
    if name not in source.declarations:
        raise Unreadable(f"`{name}` is not declared in this file")
    keyword, at = source.declarations[name]
    return TypeParser(source.tokens, at).declaration(keyword)


# The document side -----------------------------------------------------------------------------

# Validation keywords and annotations: bounds and patterns are server validation (limits).
SCHEMA_IGNORED = frozenset(
    {"title", "description", "default", "examples", "example", "deprecated", "format"}
    | {"maxLength", "minLength", "pattern", "maxItems", "minItems", "uniqueItems"}
    | {"maximum", "minimum", "exclusiveMaximum", "exclusiveMinimum", "multipleOf"}
    | {"readOnly", "writeOnly", "additionalProperties"}
)
COMPONENT_REF = "#/components/schemas/"
JSON_TYPES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean"}


def schema_type(node: Any) -> Type:
    """A JSON schema as the reader's types; TypeScript's `number` stands for JSON's integer too."""
    if not isinstance(node, dict):
        raise Unreadable(f"a schema that is not an object: {node!r}")
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith(COMPONENT_REF) or len(node) > 1:
            raise Unreadable(f"a reference the check does not follow: {ref!r}")
        return Ref(ref[len(COMPONENT_REF) :], component=True)
    unknown = set(node) - SCHEMA_IGNORED - {"type", "enum", "const", "anyOf", "items"}
    unknown -= {"properties", "required"}
    if unknown:
        raise Unreadable(f"schema keywords the check does not read: {sorted(unknown)}")
    if "anyOf" in node:
        if set(node) & {"type", "enum", "const"}:
            raise Unreadable("`anyOf` beside a type")
        return Union(tuple(schema_type(sub) for sub in node["anyOf"]))
    if "const" in node:
        return literal(node["const"])
    if "enum" in node:
        values = node["enum"]
        if not isinstance(values, list) or not values:
            raise Unreadable("an empty enum")
        found = tuple(literal(value) for value in values)
        return found[0] if len(found) == 1 else Union(found)
    kind = node.get("type")
    if kind is None:
        if set(node) - SCHEMA_IGNORED:
            raise Unreadable("a schema with no type")
        return Prim("unknown")
    if kind == "null":
        return Prim("null")
    if kind in JSON_TYPES:
        return Prim(JSON_TYPES[kind])
    if kind == "array" and "items" in node:
        return Arr(schema_type(node["items"]))
    if kind == "object" and "properties" not in node:
        return Prim("object")
    if kind == "object":
        required = node.get("required", [])
        return Obj(
            tuple(
                Field(name, schema_type(sub), name not in required)
                for name, sub in node["properties"].items()
            )
        )
    raise Unreadable(f"a schema of type {kind!r} the check does not read")


def literal(value: Any) -> Lit:
    if isinstance(value, bool | str):
        return Lit(value)
    if isinstance(value, int | float):
        return Lit(float(value))
    raise Unreadable(f"a literal the check does not read: {value!r}")


def target_schema(document: Document, target: str) -> Any:
    """The schema a pair's target names; None when the document has no such thing."""
    schemas = (document.get("components") or {}).get("schemas") or {}
    if " " in target:
        method, path, status = target.split(" ")
        operation = ((document.get("paths") or {}).get(path) or {}).get(method.lower()) or {}
        if status == QUERY_TARGET:
            return query_schema(operation)
        response = (operation.get("responses") or {}).get(status) or {}
        return ((response.get("content") or {}).get("application/json") or {}).get("schema")
    component, _, field = target.partition(".")
    if not field:
        return schemas.get(component)
    return ((schemas.get(component) or {}).get("properties") or {}).get(field)


def query_schema(operation: Any) -> Any:
    """An operation's query parameters as one object schema; None when it has none or is absent.
    A parameter `in` anything but the query (a header, a path, a cookie) is not one of them."""
    parameters = [
        p
        for p in operation.get("parameters") or []
        if isinstance(p, dict) and p.get("in") == "query"
    ]
    if not parameters:
        return None
    for parameter in parameters:
        if set(parameter) - {"name", "in", "required", "schema", "description"}:
            raise Unreadable(f"a query parameter the check does not read: {parameter.get('name')}")
    return {
        "type": "object",
        "properties": {p["name"]: p.get("schema", {}) for p in parameters},
        "required": [p["name"] for p in parameters if p.get("required")],
    }


# The comparison --------------------------------------------------------------------------------


def show(found: Type) -> str:
    if isinstance(found, Prim | Ref):
        return found.name
    if isinstance(found, Lit):
        return f'"{found.value}"' if isinstance(found.value, str) else str(found.value).lower()
    if isinstance(found, Arr):
        return f"{show(found.item)}[]"
    if isinstance(found, Union):
        return " | ".join(show(alternative) for alternative in found.alternatives)
    inner = "; ".join(f"{f.name}{'?' if f.optional else ''}: {show(f.type)}" for f in found.fields)
    return "{ " + inner + " }"


class Comparison:
    """One pair's comparison: the frontend file's declarations and the document's components."""

    MAX_DEPTH = 32

    def __init__(self, pair: Pair, source: SourceFile, document: Document) -> None:
        self.source, self.direction = source, pair.direction
        self.schemas = (document.get("components") or {}).get("schemas") or {}
        self.paired = {p.name: p.target for p in CHECKED if p.file == pair.file}

    def frontend(self, found: Type, depth: int) -> Type:
        while isinstance(found, Ref):
            found = declared_type(self.source, found.name)
            depth += 1
            if depth > self.MAX_DEPTH:
                raise Unreadable("types nested too deeply")
        return found

    def backend(self, found: Type, depth: int) -> Type:
        while isinstance(found, Ref):
            if found.name not in self.schemas:
                raise Unreadable(f"the document has no component {found.name}")
            found = schema_type(self.schemas[found.name])
            depth += 1
            if depth > self.MAX_DEPTH:
                raise Unreadable("schemas nested too deeply")
        return found

    def compare(self, front: Type, back: Type, path: str, depth: int = 0) -> list[str]:
        if (
            isinstance(front, Ref)
            and isinstance(back, Ref)
            and back.component
            and self.paired.get(front.name) == back.name
        ):
            # A paired type in a field: checked against its own component, once.
            return []
        front, back = self.frontend(front, depth), self.backend(back, depth)
        if path in VALUE_LISTS and front == Prim("string") and is_string_enum(back):
            return []
        if isinstance(front, Union) or isinstance(back, Union):
            return self.union(front, back, path, depth)
        if isinstance(front, Obj) and isinstance(back, Obj):
            return self.object(front, back, path, depth)
        if isinstance(front, Arr) and isinstance(back, Arr):
            return self.compare(front.item, back.item, f"{path}[]", depth + 1)
        if front == back:
            return []
        return [f"{path}: {show(front)} against the document's {show(back)}"]

    def flat(self, found: Type, front: bool, depth: int) -> tuple[Type, ...]:
        """A union's alternatives, named types and nested unions resolved."""
        found = self.frontend(found, depth) if front else self.backend(found, depth)
        if not isinstance(found, Union):
            return (found,)
        return tuple(a for sub in found.alternatives for a in self.flat(sub, front, depth + 1))

    def union(self, front: Type, back: Type, path: str, depth: int) -> list[str]:
        fronts, backs = self.flat(front, True, depth), self.flat(back, False, depth)

        def covered(one: Type, others: tuple[Type, ...], one_is_front: bool) -> bool:
            return any(
                not (
                    self.compare(one, other, path, depth + 1)
                    if one_is_front
                    else self.compare(other, one, path, depth + 1)
                )
                for other in others
            )

        missing = [show(f) for f in fronts if not covered(f, backs, True)]
        extra = [show(b) for b in backs if not covered(b, fronts, False)]
        # G-A A: a request enum gaining a value passes, since the frontend never sends it.
        if self.direction in (REQUEST, QUERY) and all(isinstance(b, Lit) for b in backs):
            extra = []
        problems = []
        if missing:
            problems.append(f"{path}: {', '.join(missing)} not in the document's {show(back)}")
        if extra:
            problems.append(f"{path}: the document's {', '.join(extra)} not in {show(front)}")
        return problems

    def object(self, front: Obj, back: Obj, path: str, depth: int) -> list[str]:
        problems = []
        backs = {field.name: field for field in back.fields}
        fronts = {field.name: field for field in front.fields}
        for field in front.fields:
            where = f"{path}.{field.name}"
            other = backs.get(field.name)
            if other is None:
                problems.append(f"{where}: not a property of the document's object")
                continue
            if field.optional and not other.optional:
                problems.append(f"{where}: optional here, required by the document")
            # G-A A: a request field the frontend always sends may be optional in the document.
            if other.optional and not field.optional and self.direction == RESPONSE:
                problems.append(f"{where}: required here, optional in the document")
            problems += self.compare(field.type, other.type, where, depth + 1)
        for name, other in backs.items():
            # G-A A: a response field the frontend does not declare passes; a request one fails.
            # A query parameter the frontend does not send fails only when it is required.
            if name not in fronts and self.direction == QUERY and other.optional:
                continue
            if name not in fronts and self.direction in (REQUEST, QUERY):
                state = "optional" if other.optional else "required"
                problems.append(f"{path}.{name}: {state} in the document, not sent by the type")
        return problems


def is_string_enum(found: Type) -> bool:
    alternatives = found.alternatives if isinstance(found, Union) else (found,)
    return all(isinstance(a, Lit) and isinstance(a.value, str) for a in alternatives)


def type_findings(files: Files, document: Document) -> list[str]:
    """K-01: each pair of `CHECKED`, compared with its target in `document`."""
    problems = []
    for pair in CHECKED:
        label = f"{pair.file}: {pair.name} against {pair.target}"
        if pair.file not in files:
            problems.append(f"{label}: the file is missing")
            continue
        target = target_schema(document, pair.target)
        if target is None:
            problems.append(f"{label}: the document has no such component")
            continue
        try:
            source = read_file(files[pair.file])
            if pair.name not in source.declarations:
                problems.append(f"{label}: {pair.name} is not declared in the file")
                continue
            comparison = Comparison(pair, source, document)
            front = declared_type(source, pair.name)
            back = schema_type(target)
            problems += [f"{label}: {p}" for p in comparison.compare(front, back, pair.name)]
        except Unreadable as exc:
            problems.append(f"{label}: the check cannot read it ({exc})")
    return problems


# K-02: the country list ------------------------------------------------------------------------


def shape(tokens: list[Token], start: int, length: int) -> list[tuple[str, str]]:
    return [(token.kind, token.text) for token in tokens[start : start + length]]


def exported_const(tokens: list[Token], name: str) -> int:
    """The index of the value of the one `export const <name> =`; any other count raises."""
    starts = [
        index
        for index in range(len(tokens))
        if shape(tokens, index, 4)
        == [("name", "export"), ("name", "const"), ("name", name), ("punct", "=")]
    ]
    if len(starts) != 1:
        raise Unreadable(f"`export const {name} =` found {len(starts)} times, not once")
    return starts[0] + 4


# `.trim().split(/\s+/);` after the template: the only form whose list is the template's words.
SPLIT_ON_WHITESPACE = [
    ("punct", "."),
    ("name", "trim"),
    ("punct", "("),
    ("punct", ")"),
    ("punct", "."),
    ("name", "split"),
    ("punct", "("),
    ("regex", "/\\s+/"),
    ("punct", ")"),
    ("punct", ";"),
]


def frontend_countries(text: str) -> tuple[list[str], str]:
    """`COUNTRY_CODES` and `DEFAULT_COUNTRY` of `countries.ts`; any other form raises."""
    tokens = Lexer(text).run()
    at = exported_const(tokens, "COUNTRY_CODES")
    template = tokens[at] if at < len(tokens) else None
    if (
        template is None
        or template.kind != "template"
        or template.substituted
        or "\\" in template.text
        or shape(tokens, at + 1, len(SPLIT_ON_WHITESPACE)) != SPLIT_ON_WHITESPACE
    ):
        raise Unreadable("COUNTRY_CODES is not one plain template split on whitespace")
    at_default = exported_const(tokens, "DEFAULT_COUNTRY")
    if shape(tokens, at_default + 1, 1) != [("punct", ";")] or tokens[at_default].kind != "string":
        raise Unreadable("DEFAULT_COUNTRY is not one string literal")
    return template.text.split(), tokens[at_default].text


def document_countries(document: Document) -> tuple[list[str], str]:
    """The request enum of `CustomerCreate.country` and its default: the response has no enum."""
    schemas = (document.get("components") or {}).get("schemas") or {}
    field = ((schemas.get(COUNTRY_COMPONENT) or {}).get("properties") or {}).get(COUNTRY_PROPERTY)
    where = f"{COUNTRY_COMPONENT}.{COUNTRY_PROPERTY}"
    if not isinstance(field, dict):
        raise Unreadable(f"the document has no {where}")
    codes, default = field.get("enum"), field.get("default")
    if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
        raise Unreadable(f"{where} has no enum of strings")
    if not isinstance(default, str):
        raise Unreadable(f"{where} has no string default")
    return codes, default


def repeated(codes: list[str]) -> list[str]:
    return sorted({code for code in codes if codes.count(code) > 1})


def country_findings(files: Files, document: Document) -> list[str]:
    """K-02: the frontend's list and default against the document's, compared as sets."""
    label = f"{COUNTRY_FILE}: COUNTRY_CODES against {COUNTRY_COMPONENT}.{COUNTRY_PROPERTY}"
    if COUNTRY_FILE not in files:
        return [f"{label}: the file is missing"]
    try:
        front, front_default = frontend_countries(files[COUNTRY_FILE])
        back, back_default = document_countries(document)
    except Unreadable as exc:
        return [f"{label}: the check cannot read it ({exc})"]
    problems = []
    if not front:
        problems.append(f"{label}: the frontend list is empty")
    for side, codes in (("frontend", front), ("document", back)):
        if repeated(codes):
            problems.append(f"{label}: repeated in the {side} list: {', '.join(repeated(codes))}")
    unknown, missing = sorted(set(front) - set(back)), sorted(set(back) - set(front))
    if unknown:
        problems.append(f"{label}: not accepted by the document: {', '.join(unknown)}")
    if missing:
        problems.append(f"{label}: missing from the frontend list: {', '.join(missing)}")
    if front_default != back_default:
        problems.append(
            f"{label}: DEFAULT_COUNTRY {front_default!r} against the document's default "
            f"{back_default!r}"
        )
    return problems


# K-03: coverage --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Export:
    name: str
    kind: str  # type or value


def exports(text: str) -> tuple[list[Export], list[str]]:
    """Every `export` of a file, classified; one the reader cannot classify is a problem."""
    try:
        tokens = Lexer(text).run()
    except Unreadable as exc:
        return [], [f"the check cannot read the file ({exc})"]
    found: list[Export] = []
    problems: list[str] = []
    for index, token in enumerate(tokens):
        if token.kind != "name" or token.text != "export":
            continue
        if is_text(tokens, index - 1, ".") or is_text(tokens, index + 1, ":"):
            continue
        try:
            found += classified(tokens, index)
        except Unreadable as exc:
            problems.append(f"line {token.line}: the check cannot read this export ({exc})")
    return found, problems


def classified(tokens: list[Token], index: int) -> list[Export]:
    word = tokens[index + 1].text if index + 1 < len(tokens) else ""
    if word == "type" and is_text(tokens, index + 2, "{", "*"):
        return reexported(tokens, index + 2)
    if word in ("interface", "type"):
        return [Export(name_at(tokens, index + 2, word), "type")]
    if word in ("{", "*"):
        return reexported(tokens, index + 1)
    if word == "function":
        return [Export(name_at(tokens, index + 2, word), "value")]
    if word == "async" and is_text(tokens, index + 2, "function"):
        return [Export(name_at(tokens, index + 3, "function"), "value")]
    if word in ("const", "let", "var") and not is_text(tokens, index + 2, "enum"):
        return [Export(name_at(tokens, index + 2, word), "value")]
    raise Unreadable(f"`export {word}` is not a form the reader classifies")


def reexported(tokens: list[Token], index: int) -> list[Export]:
    """`export { … } from "…"` and `export * from "…"` are judged at the declaring file."""
    depth = 0
    for at in range(index, len(tokens)):
        if is_text(tokens, at, "{"):
            depth += 1
        elif is_text(tokens, at, "}"):
            depth -= 1
        elif depth == 0 and is_text(tokens, at, "from"):
            return []
        elif depth == 0 and is_text(tokens, at, ";"):
            break
    raise Unreadable("an export list without `from`")


def coverage_findings(
    files: Files, frontend_only: frozenset[tuple[str, str]] = FRONTEND_ONLY
) -> list[str]:
    """K-03: each exported type of each file under `frontend/src/api/` is checked or listed."""
    sources = sources_in(files)
    if not sources:
        return [f"{API_DIR}: no source files, so nothing was checked"]
    allowed = {(pair.file, pair.name) for pair in CHECKED} | frontend_only
    problems: list[str] = []
    declared: set[tuple[str, str]] = set()
    for path, text in sources.items():
        if not path.endswith(SOURCE_SUFFIXES):
            problems.append(f"{path}: not a TypeScript source, so the check cannot read it")
            continue
        found, unreadable = exports(text)
        problems += [f"{path}: {problem}" for problem in unreadable]
        for export in (e for e in found if e.kind == "type"):
            declared.add((path, export.name))
            if (path, export.name) not in allowed:
                problems.append(
                    f"{path}: {export.name}: an exported type neither checked against the "
                    "document nor on the frontend-only list"
                )
    for path, name in sorted(frontend_only - declared):
        problems.append(f"{path}: {name}: on the frontend-only list, but not exported there")
    return problems


def exported_names(text: str) -> set[str]:
    """K-05 (iii): every name a file exports, types and values; an unreadable export raises."""
    found, problems = exports(text)
    if problems:
        raise Unreadable("; ".join(problems))
    return {export.name for export in found}


def findings(files: Files, document: Document) -> list[str]:
    return (
        coverage_findings(files)
        + type_findings(files, document)
        + country_findings(files, document)
    )


def main() -> int:
    problems = findings(api_sources(), real_app().openapi())
    for problem in problems:
        sys.stdout.write(problem + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
