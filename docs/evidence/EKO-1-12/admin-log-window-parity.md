# EKO-1-12 R-01 — admin-only window logs the console redirect restricted — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112` (`sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`)

## Command and result (green batch 2, 2026-11-08)

```
uv run pytest -m runtime tests/runtime/test_eko112_k04_admin_listener_log_privacy.py ... -q
# batch summary: 1 failed, 9 passed, 1 error in 3973.17s — this test among the 9 passed
```

`test_k04_admin_only_window_logs_the_console_redirect_restricted` (its own fresh composition,
real bootstrap):

1. after the bootstrap both listeners serve; the public gate marker is then removed and the
   proxy restarted — the composition enters the admin-only window (`Caddyfile.admin` selected
   by the entrypoint, the public listener connection-dead);
2. a master-realm console login (security-admin-console, PKCE, the break-glass synthetic
   account) completes over the admin listener and its redirect `GET /admin/master/console/?code=…`
   is fetched;
3. the proxy's own log window for that request: exactly one access line, `request.uri` equals
   `/admin/master/console/` (no query string), no `request.remote_ip`, no `request.headers`,
   the line matches the documented restricted `proxy.access` form
   (`tests/support/log_lines.py`, the EKO-1-13 C4 rules), and the issued authorization-code
   value appears nowhere in the proxy output.

Red before the fix (same test): no restricted access line existed at all — the pre-fix
`Caddyfile.admin` carried no log directive, so the admin-only window logged nothing for the
request while the full configuration's same site logs one restricted line (the drift R-01
named; on Caddy 2.11.7 the unrestricted-default-line variant was not observed — silence was).

The committed static pair (`tests/static/test_eko112_k04_caddy_admin_log_parity.py`) fails on
any directive drift between the two Caddyfiles (observed red 3 checks pre-fix, green after).

## Limits

Local composition; the company-network CIDR fence and the admin listener's exposure remain
EKO-1-08 territory. No credential, code value, address or personal data appears here — the
probes assert absence, never values.
