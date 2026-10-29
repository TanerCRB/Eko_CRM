"""Where a call or a name may appear in the source trees: each check returns its findings."""

import ast
import re
from collections.abc import Iterable, Mapping
from functools import cache

from tests.support.repo import REPO_ROOT, tracked_files

Files = Mapping[str, str]
BACKEND_APP = "backend/app/"
MIGRATIONS = "backend/migrations/"


def under(path: str, *directories: str) -> bool:
    """Each directory ends with `/`: `backend/app/data/` never matches `backend/app/data_x/`."""
    return any(path.startswith(d) for d in directories)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _findings(
    files: Files, scope: Iterable[str], patterns: Iterable[re.Pattern[str]], rule: str
) -> list[str]:
    directories = tuple(scope)
    found = []
    for path, text in sorted(files.items()):
        if not under(path, *directories):
            continue
        for pattern in patterns:
            for match in pattern.finditer(text):
                found.append(f"{path}:{line_of(text, match.start())}: {rule}: {match.group(0)!r}")
    return found


@cache
def repository_sources() -> dict[str, str]:
    """Every file Git tracks or would track, decoded leniently so no file is skipped.

    CRLF from a Windows checkout is normalised, as Git stores the file (`text=auto`).
    """
    return {
        path: (REPO_ROOT / path)
        .read_bytes()
        .decode("utf-8", errors="replace")
        .replace("\r\n", "\n")
        for path in tracked_files()
    }


C12_TOKENS = re.compile(r"jwt|jose|id_token|access_token", re.IGNORECASE)


def c12_tokens(files: Files) -> list[str]:
    """ADR-0003-C12: `grep -rli -e jwt -e jose -e id_token -e access_token` on the two layers."""
    scope = ("backend/app/services/", "backend/app/domain/")
    return _findings(files, scope, [C12_TOKENS], "ADR-0003-C12 token handling")


def _except(files: Files, allowed: str) -> dict[str, str]:
    """The one allowed place is an exact file, never its directory or a name beginning like it."""
    return {path: text for path, text in files.items() if path != allowed}


# ADR-0001-C10 as restated: whole names only, so `environment` and `ConfigDict` are no finding.
ENV_READS = [
    re.compile(r"\b(?:environb?|getenvb?|putenv)\b"),
    re.compile(r"\bpydantic_settings\b|\bBaseSettings\b"),
    re.compile(r"dotenv"),
    re.compile(r"\bstarlette\.config\b"),
    re.compile(r"\bfrom\s+starlette\s+import\s+(?:\([^)]*\bconfig\b[^)]*\)|[^\n]*\bconfig\b)"),
]
SETTINGS = "backend/app/core/settings.py"


def env_reads(files: Files) -> list[str]:
    return _findings(_except(files, SETTINGS), [BACKEND_APP], ENV_READS, "ADR-0001-C10 environment")


# ADR-0002-C13 as restated: the existing list, the timestamp functions and the special values.
CLOCK_FIXED = [
    "datetime.now(",
    "utcnow(",
    "date.today(",
    "datetime.today(",
    "func.now(",
    "current_date",
    "current_time",
    "localtime",
    " now()",
    "(now()",
    "=now()",
    ",now()",
    "'now()",
    '"now()',
    "clock_timestamp()",
    "statement_timestamp()",
    "transaction_timestamp()",
    "timeofday()",
]
CLOCK_READS = [
    re.compile("|".join(re.escape(token) for token in CLOCK_FIXED), re.IGNORECASE),
    # A call of the `time` module only: `datetime.time(9, 0)` reads no clock.
    re.compile(r"(?<![\w.])time\.time(?:_ns)?\(", re.IGNORECASE),
    re.compile(r"'(?:now|today|tomorrow|yesterday)'", re.IGNORECASE),
]
CLOCK = "backend/app/core/clock.py"


def clock_reads(files: Files) -> list[str]:
    scope = [BACKEND_APP, MIGRATIONS]
    return _findings(_except(files, CLOCK), scope, CLOCK_READS, "ADR-0002-C13 clock")


def sqlalchemy_outside_data(files: Files) -> list[str]:
    """ADR-0002-C4: `grep -rl "sqlalchemy" backend/app` lists only files under `app/data/`."""
    outside = {p: t for p, t in files.items() if not under(p, "backend/app/data/")}
    return _findings(outside, [BACKEND_APP], [re.compile("sqlalchemy")], "ADR-0002-C4 sqlalchemy")


def schema_creation(files: Files) -> list[str]:
    scope = [BACKEND_APP, MIGRATIONS]
    return _findings(files, scope, [re.compile("create_all|drop_all")], "ADR-0002-C4 schema")


PASSWORD = re.compile(r"passw(?:or)?d", re.IGNORECASE)


def _docstrings(tree: ast.Module) -> set[int]:
    nodes: list[ast.AST] = [tree]
    nodes += [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    found = set()
    for node in nodes:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            found.add(id(body[0].value))
    return found


def _code_names(tree: ast.Module) -> list[tuple[int, str]]:
    """Strings and identifiers of the code; comments and docstrings name no column."""
    docstrings = _docstrings(tree)
    names: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                names.append((node.lineno, node.value))
        elif isinstance(node, ast.Name):
            names.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute):
            names.append((node.lineno, node.attr))
        elif isinstance(node, ast.keyword) and node.arg:
            names.append((node.lineno, node.arg))
    return names


def password_columns(files: Files) -> list[str]:
    """ADR-0001-C6, migrations half: no `passw(or)?d` (any case) in a migration's code."""
    found = []
    for path, text in sorted(files.items()):
        if not under(path, MIGRATIONS):
            continue
        try:
            names = _code_names(ast.parse(text.replace("\r\n", "\n")))
        except SyntaxError:
            # Not Python (the revision template): every line outside a comment counts.
            names = [(n, line.split("#", 1)[0]) for n, line in enumerate(text.split("\n"), 1)]
        for line, name in names:
            if PASSWORD.search(name):
                found.append(f"{path}:{line}: ADR-0001-C6 password column: {name!r}")
    return found


NOQA = re.compile(
    r"#\s*(?:(?P<file>ruff|flake8)\s*:\s*)?noqa(?:\s*:\s*(?P<codes>[A-Z0-9]+(?:[\s,]+[A-Z0-9]+)*))?",
    re.IGNORECASE,
)
S608_PREFIXES = {"S", "S6", "S60", "S608"}


def s608_noqa(files: Files) -> list[str]:
    """Checklist rule 19: no inline or file-level suppression that can cover S608 in app/."""
    found = []
    for path, text in sorted(files.items()):
        if not under(path, BACKEND_APP):
            continue
        for match in NOQA.finditer(text):
            codes = match.group("codes")
            listed = {c.upper() for c in re.split(r"[\s,]+", codes)} if codes else set()
            if not listed or listed & S608_PREFIXES or match.group("file") == "flake8":
                where = f"{path}:{line_of(text, match.start())}"
                found.append(f"{where}: rule 19: {match.group(0)!r} can suppress S608")
    return found


# ADR-0003-C9 "no route sends e-mail", judged by name over the whole application: a route reaches
# a sender through any layer, so no file under backend/app/ holds one.
EMAIL_SENDERS = [
    re.compile(r"\b(?:aio)?smtplib\b|\bSMTP(?:_SSL)?\s*\("),
    re.compile(r"\bemail\.(?:message|mime)\b|\bEmailMessage\b|\bMIME(?:Text|Multipart)\b"),
    re.compile(r"\b(?:fastapi_mail|flask_mail|yagmail|sendgrid|mailgun|postmarker)\b"),
    re.compile(r"\bsend_?e?mail\b", re.IGNORECASE),
]


def email_senders(files: Files) -> list[str]:
    return _findings(files, [BACKEND_APP], EMAIL_SENDERS, "ADR-0003-C9 e-mail")


FRONTEND = "frontend/"
FRONTEND_SRC = "frontend/src/"
HELPER = "frontend/src/time/warsaw.ts"


def _fixed(*tokens: str) -> re.Pattern[str]:
    return re.compile("|".join(re.escape(token) for token in tokens))


# `Date(` called without `new`: `new Date(0)`, `Date.now(` and `.getDate(` are other names.
DATE_WITHOUT_NEW = re.compile(r"(?<![\w$.])Date\s*\(")
NEW_BEFORE = re.compile(r"\bnew\s*$")

# ADR-0001-C13 as restated: nowhere in frontend/src/, the helper included.
DEVICE_ZONE = [
    _fixed(
        ".getFullYear(",
        ".getMonth(",
        ".getDate(",
        ".getDay(",
        ".getHours(",
        ".getMinutes(",
        "getTimezoneOffset",
        ".setDate(",
        ".setHours(",
        ".setFullYear(",
        ".setMonth(",
        ".setMinutes(",
        ".setSeconds(",
        ".setMilliseconds(",
        "toDateString",
        "toTimeString",
    ),
]


def device_zone_reads(files: Files) -> list[str]:
    found = _findings(files, [FRONTEND_SRC], DEVICE_ZONE, "ADR-0001-C13 device zone")
    for path, text in sorted(files.items()):
        if not under(path, FRONTEND_SRC):
            continue
        for match in DATE_WITHOUT_NEW.finditer(text):
            if not NEW_BEFORE.search(text[max(0, match.start() - 40) : match.start()]):
                where = f"{path}:{line_of(text, match.start())}"
                found.append(f"{where}: ADR-0001-C13 device zone: Date( without new")
    return found


def to_json(files: Files) -> list[str]:
    return _findings(files, [FRONTEND_SRC], [_fixed(".toJSON(")], "ADR-0001-C13 toJSON")


# ADR-0001-C14 as restated: only in the helper file itself.
HELPER_ONLY = [
    _fixed(
        "toISOString",
        "getUTC",
        "Date.UTC",
        "toLocale",
        "Intl.DateTimeFormat",
        "Temporal.",
        "date-fns",
        "dayjs",
        "luxon",
        "'moment",
        '"moment',
    ),
    re.compile(r"\.setUTC\w*\s*\("),
    re.compile(r"\bDate\s*\.\s*now\b"),
    re.compile(r"\bnew\s+Date\s*\(\s*\)"),
    re.compile(r"\bnew\s+Date\b(?!\s*\()"),
]


NEW_DATE_CALL = re.compile(r"\bnew\s+Date\s*\(")
OPENING, CLOSING = "([{", ")]}"


def _skip_literal(text: str, i: int) -> int:
    """The index after the string, template or comment starting at `i`; `i` when there is none."""
    if text.startswith("//", i):
        end = text.find("\n", i)
        return len(text) if end == -1 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return len(text) if end == -1 else end + 2
    if text[i] in "'\"`":
        quote, j = text[i], i + 1
        while j < len(text) and text[j] != quote:
            j += 2 if text[j] == "\\" else 1
        return j + 1
    return i


def argument_count(text: str, start: int) -> int:
    """Arguments of the call whose `(` is at `start`; a spread counts as two (unknown, many).

    Brackets are balanced and strings, templates and comments skipped, so the commas inside
    `Number(year)` or `'10, 00'` are not argument separators. A trailing comma adds none.
    """
    depth, i, count, pending = 0, start + 1, 0, False
    while i < len(text):
        skipped = _skip_literal(text, i)
        if skipped != i:
            pending, i = True, skipped
            continue
        ch = text[i]
        if ch in OPENING:
            depth += 1
        elif ch in CLOSING:
            if depth == 0:
                return count + (1 if pending else 0)
            depth -= 1
        elif depth == 0 and ch == ",":
            count, pending = count + (1 if pending else 0), False
            i += 1
            continue
        elif depth == 0 and text.startswith("...", i):
            count += 1
        if not ch.isspace():
            pending = True
        i += 1
    return count + (1 if pending else 0)


def _new_date_with_arguments(files: Files) -> list[str]:
    """ADR-0001-C14 as restated: `new Date(` with two or more arguments, outside the helper."""
    found = []
    for path, text in sorted(files.items()):
        if path == HELPER or not under(path, FRONTEND_SRC):
            continue
        for match in NEW_DATE_CALL.finditer(text):
            if argument_count(text, match.end() - 1) >= 2:
                where = f"{path}:{line_of(text, match.start())}"
                found.append(
                    f"{where}: ADR-0001-C14 date API: new Date( with two or more arguments"
                )
    return found


def date_apis_outside_helper(files: Files) -> list[str]:
    scope = [FRONTEND_SRC]
    return _findings(
        _except(files, HELPER), scope, HELPER_ONLY, "ADR-0001-C14 date API"
    ) + _new_date_with_arguments(files)


STORAGE = re.compile(r"localStorage|sessionStorage|indexedDB|caches\.open|serviceWorker")


def client_storage(files: Files) -> list[str]:
    return _findings(files, [FRONTEND_SRC], [STORAGE], "ADR-0005-C12 client storage")


VITE_BUILTINS = frozenset({"MODE", "BASE_URL", "PROD", "DEV", "SSR"})
ENV_ACCESS = re.compile(
    r"import\.meta\.env\b"
    r"(?:\s*\??\.\s*(?P<dot>[A-Za-z_$][\w$]*)"
    r"|\s*(?:\?\.)?\s*\[\s*(?P<quote>['\"`])(?P<key>[^'\"`]*)(?P=quote)\s*\])?"
)
VITE_NAME = re.compile(r"\bVITE_\w*")


def frontend_env_reads(files: Files, allowed: frozenset[str]) -> list[str]:
    """Checklist rule 4: `import.meta.env` gives only Vite's built-ins or allow-listed names."""
    found = []
    for path, text in sorted(files.items()):
        if not under(path, FRONTEND):
            continue
        for match in ENV_ACCESS.finditer(text):
            name = match.group("dot") or match.group("key")
            if name is None or (name not in VITE_BUILTINS and name not in allowed):
                read = name or "the whole object, or a computed name"
                found.append(
                    f"{path}:{line_of(text, match.start())}: rule 4: import.meta.env {read}"
                )
        for match in VITE_NAME.finditer(text):
            if match.group(0) not in allowed:
                where = f"{path}:{line_of(text, match.start())}"
                found.append(f"{where}: rule 4: {match.group(0)} is not on the allow-list")
    return found


VITE_INJECTION = re.compile(r"\benvPrefix\b|\bdefine\b")


def vite_env_injection(files: Files) -> list[str]:
    """Checklist rule 4 (G-2 A): no `envPrefix` or `define` in any `vite.config.*`."""
    configs = {p: t for p, t in files.items() if p.rsplit("/", 1)[-1].startswith("vite.config.")}
    return _findings(configs, [FRONTEND], [VITE_INJECTION], "rule 4 Vite env injection")


def _tree_reference(other: str, quotes: str) -> list[re.Pattern[str]]:
    q = re.escape(quotes)
    return [
        # A path string naming the other tree as a segment, or a segment string built into one.
        re.compile(rf"(?P<q>[{q}])(?:[^{q}\n]*/)?{other}(?:/[^{q}\n]*)?(?P=q)"),
        # A relative path reaching it, quoted or not (comments included).
        re.compile(rf"(?<![\w@-])\.{{1,2}}/(?:[\w.@-]+/)*{other}(?![\w-])"),
    ]


FRONTEND_TO_BACKEND = _tree_reference("backend", "'\"`")
BACKEND_TO_FRONTEND = [
    *_tree_reference("frontend", "'\""),
    re.compile(r"^\s*(?:from|import)\s+frontend\b", re.MULTILINE),
]


def cross_tree_references(files: Files) -> list[str]:
    """Checklist rule 7: no import of, or relative path to, the other tree, in either direction."""
    return _findings(
        files, [FRONTEND], FRONTEND_TO_BACKEND, "rule 7 frontend refers to backend"
    ) + _findings(
        files, [BACKEND_APP, MIGRATIONS], BACKEND_TO_FRONTEND, "rule 7 backend refers to frontend"
    )
