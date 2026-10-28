"""Checks on tracked files and on the change set (K-04, K-07): each returns its violations."""

import fnmatch
import json
import re
from collections.abc import Iterable, Mapping

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from tests.support.image_refs import (
    image_ref_violations,
    keycloak_text_references,
    postgres_text_references,
)

COMPOSE_GLOB = "*compose*.y*ml"
# K-04 edge: the checks' own negative fixtures, named one by one; never a directory.
CHECK_FIXTURES = frozenset(
    {
        "backend/tests/static/fixtures/image_references.txt",
        "backend/tests/static/fixtures/composition_cases.yaml",
        "backend/tests/static/fixtures/reference_files.yaml",
        "backend/tests/static/fixtures/changeset_cases.yaml",
    }
)

Files = Mapping[str, str]


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def is_compose_file(path: str) -> bool:
    return fnmatch.fnmatch(_basename(path), COMPOSE_GLOB)


def c12_postgres_references(files: Files, rendered_images: Iterable[str]) -> list[str]:
    """ADR-0002-C12 as restated 2026-10-28: tracked files and the rendered composition."""
    problems = [f"composition: {p}" for ref in rendered_images for p in _postgres_only(ref)]
    for path, text in files.items():
        if path in CHECK_FIXTURES or path.endswith(".md") or is_compose_file(path):
            continue
        for ref in postgres_text_references(text):
            problems += [f"{path}: {ref}: {p}" for p in image_ref_violations(ref)]
    return problems


def _postgres_only(reference: str) -> list[str]:
    name = reference.split("@", 1)[0].rsplit(":", 1)[0] if ":" in reference else reference
    if name.split("@", 1)[0] in {"postgres", "library/postgres", "docker.io/library/postgres"}:
        return image_ref_violations(reference)
    return []


def adr0003_c3_keycloak_references(files: Files, rendered_images: Iterable[str]) -> list[str]:
    problems = [
        f"composition: {ref}: {p}"
        for ref in rendered_images
        if "keycloak/keycloak" in ref
        for p in image_ref_violations(ref)
    ]
    for path, text in files.items():
        if path in CHECK_FIXTURES or path.endswith(".md") or is_compose_file(path):
            continue
        for ref in keycloak_text_references(text):
            problems += [f"{path}: {ref}: {p}" for p in image_ref_violations(ref)]
    return problems


def _dependency_names(dependencies: Iterable[str]) -> dict[str, str]:
    named = {}
    for spec in dependencies:
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(\[[^\]]*\])?\s*(.*)", spec)
        if match:
            named[match.group(1).lower()] = match.group(3)
    return named


def adr0001_c1_pyproject(pyproject: Mapping[str, object]) -> list[str]:
    """ADR-0001-C1 (static half; `uv lock --locked` runs separately)."""
    problems = []
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return ["no [project] table"]
    specifier = SpecifierSet(str(project.get("requires-python", "")))
    if Version("3.12.0") not in specifier:
        problems.append("requires-python does not admit 3.12")
    for lower in ("3.11.99", "3.11.0", "3.10.0"):
        if Version(lower) in specifier:
            problems.append(f"requires-python admits {lower}")
            break
    names = _dependency_names(project.get("dependencies", []))
    if "fastapi" not in names:
        problems.append("fastapi is not a dependency")
    pydantic = names.get("pydantic")
    if pydantic is None:
        problems.append("pydantic is not a dependency")
    else:
        spec = SpecifierSet(pydantic.split(";")[0].strip())
        if not any(Version(f"2.{minor}.0") in spec for minor in range(100)):
            problems.append("pydantic admits no 2.x version")
        if Version("1.10.0") in spec or Version("3.0.0") in spec:
            problems.append("pydantic admits a major version other than 2")
    return problems


def adr0001_c2_frontend(package_json: str | None, tracked: Iterable[str]) -> list[str]:
    """ADR-0001-C2 (static half; `pnpm install --frozen-lockfile` runs in the frontend job)."""
    problems = []
    for path in tracked:
        if _basename(path) in {"package-lock.json", "yarn.lock", "npm-shrinkwrap.json"}:
            problems.append(f"{path}: lock file of another package manager")
    if package_json is None:
        return [*problems, "frontend/package.json is missing"]
    manifest = json.loads(package_json)
    declared = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    for name in ("react", "typescript", "vite"):
        if name not in declared:
            problems.append(f"frontend/package.json does not list {name}")
    if not str(manifest.get("packageManager", "")).startswith("pnpm@"):
        problems.append("frontend/package.json packageManager is not pnpm")
    return problems


def strip_jsonc(text: str) -> str:
    """tsconfig files are JSON with comments and trailing commas."""
    out = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\":
                out.append(text[i + 1 : i + 2])
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def adr0001_c3_strict(tsconfigs: Files) -> list[str]:
    """ADR-0001-C3: every frontend tsconfig with compiler options sets "strict": true."""
    if not tsconfigs:
        return ["no frontend/tsconfig*.json"]
    problems = []
    with_options = 0
    for path, text in tsconfigs.items():
        options = json.loads(strip_jsonc(text)).get("compilerOptions")
        if options is None:
            continue
        with_options += 1
        if options.get("strict") is not True:
            problems.append(f'{path}: "strict" is not true')
    if with_options == 0:
        problems.append("no frontend tsconfig sets compilerOptions")
    return problems


def secret_assignments(files: Files, secrets: Iterable[str]) -> list[str]:
    """ADR-0004-C9: no tracked file assigns a value to a secret; only `${NAME:?…}` is allowed."""
    names = sorted(set(secrets))
    if not names:
        return ["empty secret inventory"]
    alternatives = "|".join(re.escape(n) for n in names)
    assignment = re.compile(
        r"(?:^|[\s{,(])(?:export\s+)?[\"']?(?P<name>" + alternatives + r")[\"']?\s*(?:=|:)(?!=)"
        r"\s*(?P<value>[^\s#,}][^#]*?)?\s*(?:#.*)?$"
    )
    allowed = re.compile(r"[\"']?\$\{[A-Z][A-Z0-9_]*:?\?[^}]*\}[\"']?,?")
    problems = []
    for path, text in files.items():
        if path in CHECK_FIXTURES:
            continue
        in_workflow = path.startswith(".github/workflows/")
        for number, line in enumerate(text.splitlines(), 1):
            match = assignment.search(line)
            if not match:
                continue
            value = (match.group("value") or "").strip()
            if in_workflow:
                problems.append(f"{path}:{number}: {match.group('name')} in a workflow")
            elif value and not allowed.fullmatch(value):
                problems.append(f"{path}:{number}: {match.group('name')} is assigned a value")
    return problems


def dockerignore_violations(files: Files, build_contexts: Iterable[str]) -> list[str]:
    """ADR-0004-C9: every build context has a .dockerignore excluding `.env*`."""
    problems = []
    for context in sorted(set(build_contexts)):
        path = f"{context}/.dockerignore" if context else ".dockerignore"
        text = files.get(path)
        if text is None:
            problems.append(f"{path}: missing")
            continue
        lines = {line.strip() for line in text.splitlines()}
        if not {".env*", "**/.env*"} <= lines:
            problems.append(f"{path}: does not exclude .env* and **/.env*")
    return problems


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
RESERVED_DOMAIN = re.compile(
    r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost)$", re.IGNORECASE
)
NIP = re.compile(
    r"(?<![0-9A-Za-z.-])(\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3}|\d{10})(?![0-9A-Za-z-])"
)
PHONE = re.compile(r"(?<![0-9A-Za-z])(\+48[\s-]?)?\d{3}[\s-]\d{3}[\s-]\d{3}(?![0-9A-Za-z])")


def personal_data(added_lines: Mapping[str, Iterable[str]]) -> list[str]:
    """K-07: no real-looking e-mail address, NIP or phone number in added lines."""
    problems = []
    for path, lines in added_lines.items():
        for line in lines:
            for match in EMAIL.finditer(line):
                if not RESERVED_DOMAIN.search(match.group("domain")):
                    problems.append(f"{path}: e-mail address outside reserved domains")
            if NIP.search(line):
                problems.append(f"{path}: NIP-shaped value")
            if PHONE.search(line):
                problems.append(f"{path}: phone-shaped value")
    return problems


ADDENDUM_HEADING = re.compile(r"### \d{4}-\d{2}-\d{2} — \S")


def adr_append_only(base: str, head: str) -> list[str]:
    """K-07: the base text is a byte prefix of head, and only dated `###` addenda follow it."""
    if head == base:
        return []
    if not head.startswith(base):
        return ["accepted text or an earlier addendum changed"]
    appended = head[len(base) :]
    if "## Addenda" not in base:
        return ["no ## Addenda section at base"]
    body = appended.lstrip("\n")
    if not ADDENDUM_HEADING.match(body):
        return ["appended text does not start with a dated ### addendum"]
    for line in body.splitlines():
        if line.startswith("#") and not line.startswith("### ") and line.strip():
            return [f"appended text holds a heading other than an addendum: {line!r}"]
        if line.startswith("### ") and not ADDENDUM_HEADING.match(line):
            return [f"appended heading is not dated: {line!r}"]
    return []


COMPOSE_ROW = re.compile(r"^\| `\*compose\*\.y\*ml` \|")
NEW_ROWS = {"`.gitignore`", "`**/.gitignore`"}


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def register_edits(base: str, head: str) -> list[str]:
    """K-07: the sensitive-paths register changes only by the two edits approved on 2026-10-28."""
    problems = []
    head_lines = head.split("\n")
    added = [line for line in head_lines if line.startswith("|") and _cells(line)[0] in NEW_ROWS]
    if sorted(_cells(line)[0] for line in added) != sorted(NEW_ROWS):
        problems.append("the .gitignore and **/.gitignore rows are not both present once")
    for line in added:
        cells = _cells(line)
        if cells[1] != "secrets" or cells[2] != "ADR-0004" or len(cells) != 4 or not cells[3]:
            problems.append(f"row {cells[0]}: not class secrets, governing ADR-0004")
    compose = [line for line in head_lines if COMPOSE_ROW.match(line)]
    if len(compose) != 1:
        problems.append("the *compose*.y*ml row is not present once")
    else:
        cells = _cells(compose[0])
        if cells[1] != "dependencies, schema, auth, secrets":
            problems.append(f"compose row classes {cells[1]!r}")
        if cells[2] != "ADR-0002, ADR-0003, ADR-0004":
            problems.append(f"compose row governing decisions {cells[2]!r}")
    base_compose = [line for line in base.split("\n") if COMPOSE_ROW.match(line)]
    rebuilt = [
        (base_compose[0] if COMPOSE_ROW.match(line) and base_compose else line)
        for line in head_lines
        if line not in added
    ]
    if "\n".join(rebuilt) != base:
        problems.append("a row, the class table or the explanation text changed")
    return problems


def identity_users(files: Files) -> list[str]:
    """K-07 / ADR-0003-C14: no file under identity/ holds users."""
    return [
        f"{path}: holds users"
        for path, text in files.items()
        if path.startswith("identity/") and re.search(r"[\"']users[\"']\s*:", text)
    ]
