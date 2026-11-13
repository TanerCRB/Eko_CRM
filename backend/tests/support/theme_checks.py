"""EKO-2-01 K-07: the restricted login theme's rules (ADR-0003-C29, C31; ADR-0004-C35).

Every check works on a mapping of theme-relative POSIX paths to file bytes, so one rule set
reads both the repository's theme directory and the same directory taken out of the built
custom image. Each finding names the file it is about; an empty list is the only pass.
"""

import re
import tarfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from tests.support.repo import REPO_ROOT

THEME_NAME = "eko-crm"
THEME_DIR = REPO_ROOT / "identity" / "themes" / THEME_NAME
REVIEW_RECORD = REPO_ROOT / "identity" / "theme-review.md"
DOCKERFILE = REPO_ROOT / "identity" / "Dockerfile"
IMAGE_THEME_DIR = f"/opt/keycloak/themes/{THEME_NAME}"
# The login themes the official quay.io/keycloak/keycloak:26.8.1 image ships in
# lib/lib/main/org.keycloak.keycloak-themes-26.8.1.jar (theme/<name>/login/theme.properties).
SHIPPED_LOGIN_PARENTS = frozenset({"base", "keycloak", "keycloak.v2"})
MESSAGE_FILE = "login/messages/messages_pl.properties"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

FORBIDDEN_CONTENT = (
    ("inline script", re.compile(rb"(?i)<script")),
    ("HTML event attribute", re.compile(rb"(?i)(?<![a-z0-9_.-])on[a-z]+\s*=")),
    ("absolute URL", re.compile(rb"(?i)\b[a-z][a-z0-9+.-]*://")),
    (
        "protocol-relative URL",
        re.compile(rb"(?i)(?:(?:src|href|action)\s*=\s*[\"']?|url\(\s*[\"']?|@import\s+[\"']?)//"),
    ),
    ("remote @import", re.compile(rb"(?i)@import\s+(?:url\()?\s*[\"']?(?:[a-z][a-z0-9+.-]*:|//)")),
    ("remote url()", re.compile(rb"(?i)url\(\s*[\"']?(?:[a-z][a-z0-9+.-]*:|//)")),
    ("FreeMarker ?new", re.compile(rb"\?new\b")),
    ("FreeMarker ?api", re.compile(rb"\?api\b")),
    ("FreeMarker ?eval", re.compile(rb"\?eval")),
    ("FreeMarker ?interpret", re.compile(rb"\?interpret\b")),
    ("FreeMarker ?no_esc", re.compile(rb"\?no_esc\b")),
)


def repository_theme(root: Path = THEME_DIR) -> dict[str, bytes]:
    """The theme directory as {relative path: bytes}; directories themselves are implied."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def theme_from_tar(archive: bytes, prefix: str = "") -> dict[str, bytes]:
    """Regular files of a tar stream keyed like `repository_theme`; `prefix` is the top
    directory `docker cp <container>:<dir> -` puts in front of every member."""
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        for member in tar.getmembers():
            name = member.name.removeprefix("./").removeprefix(prefix)
            if not name:
                continue
            if member.isfile():
                extracted = tar.extractfile(member)
                assert extracted is not None
                files[name] = extracted.read()
            elif not member.isdir():
                files[name] = b"<not a regular file>"
    return files


def parse_properties(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def file_kind_violations(files: dict[str, bytes]) -> list[str]:
    problems: list[str] = []
    if not files:
        return ["<theme>: no file at all"]
    type_dirs = {name.split("/", 1)[0] for name in files}
    if type_dirs != {"login"}:
        problems.append(f"<theme>: type directories {sorted(type_dirs)}, expected only login")
    messages = sorted(name for name in files if "/messages/" in f"/{name}")
    if messages != [MESSAGE_FILE]:
        problems.extend(f"{name}: not the single Polish message file" for name in messages)
        if MESSAGE_FILE not in messages:
            problems.append(f"{MESSAGE_FILE}: missing")
    for name, content in files.items():
        if name in messages:
            continue
        if name == "login/theme.properties":
            continue
        if name.endswith((".ftl", ".css")):
            continue
        if name.endswith(".png"):
            if not content.startswith(PNG_MAGIC):
                problems.append(f"{name}: not a PNG image")
            continue
        problems.append(f"{name}: file type not allowed")
    if "login/theme.properties" not in files:
        problems.append("login/theme.properties: missing")
    return problems


def properties_violations(
    files: dict[str, bytes], parents: frozenset[str] = SHIPPED_LOGIN_PARENTS
) -> list[str]:
    content = files.get("login/theme.properties")
    if content is None:
        return []
    values = parse_properties(content.decode("utf-8"))
    problems: list[str] = []
    parent = values.get("parent", "")
    if not parent or " " in parent or "," in parent or parent not in parents:
        problems.append(f"login/theme.properties: parent {parent!r} is not one shipped theme")
    if values.get("locales") != "pl":
        problems.append(f"login/theme.properties: locales {values.get('locales')!r}, not pl only")
    if "scripts" in values:
        problems.append("login/theme.properties: declares scripts")
    return problems


def content_violations(files: dict[str, bytes]) -> list[str]:
    return [
        f"{name}: {label}"
        for name, content in sorted(files.items())
        for label, pattern in FORBIDDEN_CONTENT
        if pattern.search(content)
    ]


def theme_violations(
    files: dict[str, bytes], parents: frozenset[str] = SHIPPED_LOGIN_PARENTS
) -> list[str]:
    """ADR-0003-C29's file-type, theme.properties and forbidden-content rules."""
    return (
        file_kind_violations(files)
        + properties_violations(files, parents)
        + content_violations(files)
    )


def byte_differences(repository: dict[str, bytes], image: dict[str, bytes]) -> list[str]:
    """Every file present in only one copy, or holding different bytes, by name."""
    found: list[str] = []
    for name in sorted(set(repository) | set(image)):
        if name not in image:
            found.append(f"{name}: only in the repository")
        elif name not in repository:
            found.append(f"{name}: only in the image")
        elif repository[name] != image[name]:
            found.append(f"{name}: bytes differ")
    return found


# ADR-0003-C31: the review record -----------------------------------------------------------

ENTRY = re.compile(
    r"^## (?P<date>\d{4}-\d{2}-\d{2}) — reviewed against Keycloak (?P<version>\S+)\s*$"
)
LISTED = re.compile(r"`([^`]+)`")


def base_version(dockerfile_text: str) -> str:
    found: list[str] = re.findall(
        r"^FROM quay\.io/keycloak/keycloak:(\S+)\s*$", dockerfile_text, re.MULTILINE
    )
    assert len(found) == 1, f"expected one official Keycloak base, found {found}"
    return found[0]


@dataclass
class ReviewEntry:
    version: str
    templates: set[str] | None = None
    message_keys: set[str] | None = None


def latest_review_entry(record_text: str) -> ReviewEntry:
    """The last `## <date> — reviewed against Keycloak <version>` entry with its two lists."""
    entries: list[ReviewEntry] = []
    listing: set[str] | None = None
    for line in record_text.splitlines():
        heading = ENTRY.match(line)
        if heading:
            entries.append(ReviewEntry(heading["version"]))
            listing = None
            continue
        if not entries:
            continue
        stripped = line.strip()
        if stripped.startswith("- Overridden templates:"):
            listing = entries[-1].templates = set(LISTED.findall(stripped))
        elif stripped.startswith("- Overridden message keys:"):
            listing = entries[-1].message_keys = set(LISTED.findall(stripped))
        elif listing is not None and line.startswith("  ") and stripped:
            # A wrapped list item continues on indented lines.
            listing.update(LISTED.findall(stripped))
        else:
            listing = None
    assert entries, "the review record has no entry"
    return entries[-1]


def overridden_templates(files: dict[str, bytes]) -> set[str]:
    return {name.rsplit("/", 1)[-1] for name in files if name.endswith(".ftl")}


def overridden_message_keys(files: dict[str, bytes]) -> set[str]:
    content = files.get(MESSAGE_FILE, b"")
    return set(parse_properties(content.decode("utf-8")))


def review_violations(files: dict[str, bytes], dockerfile_text: str, record_text: str) -> list[str]:
    entry = latest_review_entry(record_text)
    problems: list[str] = []
    version = base_version(dockerfile_text)
    if entry.version != version:
        problems.append(
            f"identity/theme-review.md: latest entry reviewed {entry.version}, base is {version}"
        )
    if entry.templates is None or entry.message_keys is None:
        problems.append("identity/theme-review.md: latest entry lacks a template or key listing")
        return problems
    templates = overridden_templates(files)
    if entry.templates != templates:
        problems.append(
            "identity/theme-review.md: templates listed "
            f"{sorted(entry.templates)} vs present {sorted(templates)}"
        )
    keys = overridden_message_keys(files)
    if entry.message_keys != keys:
        problems.append(
            "identity/theme-review.md: message keys listed "
            f"{sorted(entry.message_keys)} vs present {sorted(keys)}"
        )
    return problems
