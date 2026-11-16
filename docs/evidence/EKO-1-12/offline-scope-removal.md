# EKO-1-12 S-02 — offline_access removed from the application client; U-02 path — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)

## What was decided

The security auditor (S-02) found `offline_access` in the application client's
`optionalClientScopes` with no accepted decision naming it (grep across ADR-0003, ADR-0005,
Issue #53 K-01, `identity/` outside the export, and every `docs/evidence/EKO-1-12/` record
finds it nowhere). It rode through the K-01 disjoint scope checks because those name only
`email`/`profile`. The fix removes it from the versioned export and from the live client;
no accepted decision is cited, because none names it, and hard rule says an unassigned
capability cannot be justified by "harmless".

## Static guard (red before the export change)

`tests/static/test_eko112_k01_realm_export.py`:
- `test_k01_application_token_contains_no_email_or_username_scope_or_mapper` now asserts
  `optionalClientScopes == []` exactly (so any unapproved capability, including
  `offline_access`, fails) — red with the old export, green after removal.
- `test_k01_offline_access_on_the_application_client_fails_the_exact_set_guard` — the
  mutation: put `offline_access` back in a deep copy → the exact-set guard raises.

Pre-change observed: `1 failed, 18 passed` for this file (the exact-set failure), and
`4 failed, 19 passed` across the static batch (Caddy parity 3 + offline exact-set 1) —
recorded in `fix-round-1.md`.

## Live guard (runtime)

`test_k03_application_client_carries_no_offline_access_capability` (live, after the realm
import **and** the post-import client PUT):
- reads the live eko-backend client representation and asserts neither `defaultClientScopes`
  nor `optionalClientScopes` contains `offline_access` — the capability surface the finding
  named is gone at runtime, and every Keycloak path that mints an offline token requires the
  scope to be assigned to the client, so the U-02 offline refresh path is unreachable by
  configuration;
- deliberately NOT asserted: the server-side shape of an unassigned-scope authorization
  request (drop vs refuse vs consent). That shape is Keycloak's own behavior, not a property
  of this configuration, and the finding's fact is fully carried by the scope-absence
  assertion; a browser-flow probe here would assert version behavior or pass vacuously.

## U-02 resolution for the human

S-02 made U-02 (offline-session deactivation bound) reachable; with `offline_access`
removed, U-02's offline refresh path is unreachable by configuration, so the only refresh
tokens in play are online-bound (covered by the K-04 disabled-account REFRESH_TOKEN_ERROR
projection). The residual offline-refresh behavior question is closed for this task: no
application-client path mints an offline token. No production claim. Synthetic accounts only.
