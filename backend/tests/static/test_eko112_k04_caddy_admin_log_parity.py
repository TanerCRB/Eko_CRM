"""EKO-1-12 K-04 (log privacy, ADR-0005 addendum 2026-11-02 C4): the admin-only Caddyfile
serves exactly the same field restriction on every line it writes as the full configuration's
admin site.

The proxy selects `proxy/Caddyfile.admin` while only the admin gate is open and
`proxy/Caddyfile` afterwards. Identical traffic therefore has to produce identical log
content in both windows; a missing `log default` block or a missing `import access_log`
in the admin-only file leaves the default logger unrestricted (full URI with the query
string, remote address and headers). This check compares the directive sets of the two
files' admin site, their global log blocks, and their shared snippets, so any drift
between them fails without executing anything. It is broken by removing either log
directive from either file (a committed one-change contrast, run by QA).
"""

from tests.support.repo import REPO_ROOT

FULL = REPO_ROOT / "proxy" / "Caddyfile"
ADMIN_ONLY = REPO_ROOT / "proxy" / "Caddyfile.admin"
ADMIN_SITE = "https://{$AUTH_ADMIN_HOST}:8443 {"


def brace_block(text: str, opener: str) -> list[str]:
    """The lines of the brace-balanced block whose first line strips to `opener`, comment
    and blank lines removed and surrounding whitespace collapsed; absence of the opener
    fails rather than passing through absence."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((index for index, line in enumerate(lines) if line.strip() == opener), None)
    assert start is not None, f"no block opens with {opener!r}"
    depth = 0
    block: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            block.append(" ".join(stripped.split()))
        depth += line.count("{") - line.count("}")
        if depth == 0 and len(block) > 1:
            break
    assert depth == 0, f"unbalanced braces after {opener!r}"
    return block


def log_default_lines(text: str) -> list[str]:
    """The `log default { ... }` block inside the global options, normalized."""
    return brace_block(text, "log default {")


def test_k04_admin_site_directives_are_identical_between_the_two_caddyfiles() -> None:
    """The same admin site must log the same way whether or not the bootstrap is mid-run:
    removing only `import access_log` from either file makes the directive sets drift."""
    full = brace_block(FULL.read_text(encoding="utf-8"), ADMIN_SITE)
    admin = brace_block(ADMIN_ONLY.read_text(encoding="utf-8"), ADMIN_SITE)
    assert full == admin, (
        "the admin site's directives differ between Caddyfile and Caddyfile.admin:\n"
        f"full-only:    {sorted(set(full) - set(admin))}\n"
        f"admin-only:  {sorted(set(admin) - set(full))}"
    )
    assert "import access_log" in full, "the full admin site stopped importing its access log"


def test_k04_admin_only_global_block_carries_the_default_logger_restriction() -> None:
    """`Caddyfile.admin` must restrict its default logger exactly like the full file: no
    header, cookie, remote address or port, protocol, TLS detail or query string."""
    full = log_default_lines(FULL.read_text(encoding="utf-8"))
    admin = log_default_lines(ADMIN_ONLY.read_text(encoding="utf-8"))
    assert full, "the full Caddyfile lost its log default block"
    assert full == admin, (
        "the default logger's field restriction differs between Caddyfile and "
        f"Caddyfile.admin: full-only {sorted(set(full) - set(admin))}, "
        f"admin-only {sorted(set(admin) - set(full))}"
    )
    for forbidden in (
        "request>remote_ip delete",
        "request>remote_port delete",
        "request>proto delete",
        "request>headers delete",
        "request>tls delete",
        'request>uri regexp "\\?.*$" ""',
        "resp_headers delete",
    ):
        assert forbidden in admin, f"Caddyfile.admin default logger lacks {forbidden!r}"


def test_k04_access_log_snippet_is_identical_in_both_caddyfiles() -> None:
    """`import access_log` resolves inside each file, so both must define the same
    snippet; a drift is a drift in what every site logs."""
    full = brace_block(FULL.read_text(encoding="utf-8"), "(access_log) {")
    admin = brace_block(ADMIN_ONLY.read_text(encoding="utf-8"), "(access_log) {")
    assert full, "the full Caddyfile lost the access_log snippet"
    assert admin, "Caddyfile.admin has no access_log snippet for its import to resolve"
    assert full == admin, (
        f"the access_log snippet differs: full-only {sorted(set(full) - set(admin))}, "
        f"admin-only {sorted(set(admin) - set(full))}"
    )


def test_k04_shared_refusal_snippets_are_identical_in_both_caddyfiles() -> None:
    """The admin-only window refuses the same paths the full configuration refuses;
    comparing them keeps a routing drift from hiding behind the log parity."""
    for opener in ("(no_api_description) {", "(no_account_console) {"):
        full = brace_block(FULL.read_text(encoding="utf-8"), opener)
        admin = brace_block(ADMIN_ONLY.read_text(encoding="utf-8"), opener)
        assert full == admin, f"{opener} differs between the two Caddyfiles"
