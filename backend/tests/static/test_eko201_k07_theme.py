"""EKO-2-01 K-07, repository half: the one restricted login theme and its review record.

ADR-0003-C29 (theme content) and C31 (upgrade review) on the repository copy. The same rule
set reads the copy inside the built image in
`tests/runtime/test_eko201_k07_theme_image.py`; a check of the repository alone
proves nothing about the image (K-07 *Boundary*).
"""

from collections.abc import Callable

import pytest

from tests.support import theme_checks as tc
from tests.support.repo import REPO_ROOT

Files = dict[str, bytes]


@pytest.fixture
def theme() -> Files:
    return tc.repository_theme()


def test_k07_c29_the_theme_is_the_only_theme_directory_under_identity() -> None:
    themes = REPO_ROOT / "identity" / "themes"
    assert sorted(path.name for path in themes.iterdir()) == [tc.THEME_NAME]


def test_k07_c29_unmodified_theme_passes_every_rule(theme: Files) -> None:
    assert theme, "the theme directory holds no file"
    assert tc.theme_violations(theme) == []


def test_k07_c29_theme_properties_extends_one_shipped_parent_in_polish_only(theme: Files) -> None:
    values = tc.parse_properties(theme["login/theme.properties"].decode("utf-8"))
    assert values["parent"] in tc.SHIPPED_LOGIN_PARENTS
    assert values["locales"] == "pl"
    assert "scripts" not in values


def plant(name: str, content: bytes) -> Callable[[Files], Files]:
    def apply(files: Files) -> Files:
        return {**files, name: content}

    return apply


def edit_properties(old: bytes, new: bytes) -> Callable[[Files], Files]:
    def apply(files: Files) -> Files:
        content = files["login/theme.properties"]
        assert old in content, f"fixture premise: {old!r} not in theme.properties"
        return {**files, "login/theme.properties": content.replace(old, new, 1)}

    return apply


# Each fixture is one violation; the finding must name the file it is about.
FIXTURES = [
    ("added-js", plant("login/resources/js/extra.js", b"void 0;\n"), "login/resources/js/extra.js"),
    (
        "svg",
        plant("login/resources/img/logo.svg", b"<svg xmlns='x'></svg>\n"),
        "login/resources/img/logo.svg",
    ),
    (
        "inline-script",
        plant("login/login.ftl", b"<#import 'template.ftl' as layout>\n<script>1</script>\n"),
        "login/login.ftl",
    ),
    (
        "event-attribute",
        plant("login/info.ftl", b'<a href="#" onclick="go()">x</a>\n'),
        "login/info.ftl",
    ),
    (
        "remote-font-url",
        plant(
            "login/resources/css/font.css",
            b"@font-face { src: url(https://fonts.example.org/x.woff2); }\n",
        ),
        "login/resources/css/font.css",
    ),
    (
        "protocol-relative-url",
        plant(
            "login/resources/css/rel.css", b"body { background: url(//cdn.example.org/a.png); }\n"
        ),
        "login/resources/css/rel.css",
    ),
    (
        "remote-import",
        plant("login/resources/css/imp.css", b'@import "https://cdn.example.org/a.css";\n'),
        "login/resources/css/imp.css",
    ),
    ("no-esc", plant("login/error.ftl", b"${message.summary?no_esc}\n"), "login/error.ftl"),
    ("new", plant("login/code.ftl", b'<#assign x = "a"?new()>\n'), "login/code.ftl"),
    ("api", plant("login/code.ftl", b"${realm?api}\n"), "login/code.ftl"),
    ("eval", plant("login/code.ftl", b'${"1+1"?eval}\n'), "login/code.ftl"),
    ("interpret", plant("login/code.ftl", b'<@"x"?interpret />\n'), "login/code.ftl"),
    (
        "second-message-file",
        plant("login/messages/messages_en.properties", b"loginAccountTitle=Sign in\n"),
        "login/messages/messages_en.properties",
    ),
    ("font-file", plant("login/resources/fonts/a.woff2", b"wOF2"), "login/resources/fonts/a.woff2"),
    ("fake-png", plant("login/resources/img/logo.png", b"<svg/>"), "login/resources/img/logo.png"),
    (
        "second-type-directory",
        plant("account/theme.properties", b"parent=keycloak.v3\n"),
        "<theme>",
    ),
    (
        "scripts-entry",
        edit_properties(b"locales=pl", b"locales=pl\nscripts=js/extra.js"),
        "login/theme.properties",
    ),
    (
        "second-locale",
        edit_properties(b"locales=pl", b"locales=pl,en"),
        "login/theme.properties",
    ),
    (
        "unshipped-parent",
        edit_properties(b"parent=keycloak.v2", b"parent=eko-other"),
        "login/theme.properties",
    ),
]


@pytest.mark.parametrize(
    ("mutation", "named"),
    [pytest.param(mutation, named, id=fixture_id) for fixture_id, mutation, named in FIXTURES],
)
def test_k07_c29_each_one_violation_fixture_fails_naming_its_file(
    theme: Files, mutation: Callable[[Files], Files], named: str
) -> None:
    assert tc.theme_violations(theme) == []
    found = tc.theme_violations(mutation(theme))
    assert found, "the one-violation fixture passed"
    assert any(problem.startswith(f"{named}:") for problem in found), found


def test_k07_c29_one_differing_byte_between_copies_is_named(theme: Files) -> None:
    assert tc.byte_differences(theme, dict(theme)) == []
    name = "login/theme.properties"
    changed = {**theme, name: theme[name] + b"\n"}
    assert tc.byte_differences(theme, changed) == [f"{name}: bytes differ"]
    extra = {**theme, "login/resources/css/extra.css": b"a{}"}
    assert tc.byte_differences(theme, extra) == ["login/resources/css/extra.css: only in the image"]


# ADR-0003-C31 --------------------------------------------------------------------------------


def review_inputs() -> tuple[str, str]:
    return (
        tc.DOCKERFILE.read_text(encoding="utf-8"),
        tc.REVIEW_RECORD.read_text(encoding="utf-8"),
    )


def test_k07_c31_review_record_sits_outside_the_copied_directory() -> None:
    assert tc.REVIEW_RECORD.is_file()
    assert tc.THEME_DIR not in tc.REVIEW_RECORD.parents


def test_k07_c31_latest_entry_matches_the_base_version_and_lists_every_override(
    theme: Files,
) -> None:
    dockerfile, record = review_inputs()
    assert tc.base_version(dockerfile) == "26.8.1"
    assert tc.review_violations(theme, dockerfile, record) == []
    entry = tc.latest_review_entry(record)
    assert entry.message_keys, "the latest entry lists no message key"
    assert entry.message_keys == tc.overridden_message_keys(theme)


def test_k07_c31_a_patch_only_base_version_change_fails(theme: Files) -> None:
    dockerfile, record = review_inputs()
    bumped = dockerfile.replace(
        "quay.io/keycloak/keycloak:26.8.1", "quay.io/keycloak/keycloak:26.8.2"
    )
    assert bumped != dockerfile
    assert any("base is 26.8.2" in item for item in tc.review_violations(theme, bumped, record))


def test_k07_c31_an_added_template_without_a_matching_entry_fails(theme: Files) -> None:
    dockerfile, record = review_inputs()
    added = {**theme, "login/login.ftl": b"<#import 'template.ftl' as layout>\n"}
    found = tc.review_violations(added, dockerfile, record)
    assert any("templates listed" in item and "login.ftl" in item for item in found), found


def test_k07_c31_an_unlisted_message_key_fails(theme: Files) -> None:
    dockerfile, record = review_inputs()
    name = tc.MESSAGE_FILE
    added = {**theme, name: theme[name] + b"\nunlistedEko201Key=Tekst\n"}
    found = tc.review_violations(added, dockerfile, record)
    assert any("unlistedEko201Key" in item for item in found), found


def test_k07_c31_a_newer_entry_against_another_version_is_the_one_compared(theme: Files) -> None:
    dockerfile, record = review_inputs()
    newer = record + "\n## 2099-01-01 — reviewed against Keycloak 99.0.0\n"
    found = tc.review_violations(theme, dockerfile, newer)
    assert any("latest entry reviewed 99.0.0" in item for item in found), found
