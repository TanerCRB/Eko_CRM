# EKO-1-12 U-01 — OIDC client secret absent from stored admin events — 2026-11-09

Date: 2026-11-09
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 69843bd32f4f248e35ab5590bd36d742a99e8c8b (clean tree; audited fix code at
eada866 "checkpoint: EKO-1-12 fix"; the QA run had every mutation reverted and the accepted-shape
Keycloak image rebuilt locally — see Limits)
observed by QA (the closing cycle's report declared this record missing; the QA round-2 run produced it)

## What was asserted, live

`backend/tests/runtime/test_eko112_k03_runtime_roles_and_events.py::test_k03_client_secret_absent_from_stored_admin_events`
ran standalone on a fresh, freshly bootstrapped development composition
(project label `ekort-keycloak-f37da3dc`, pytest session `pytest-2688`, composition brought up from
no volumes and removed with `down -v` afterwards):

- the synthetic environment carries an `OIDC_CLIENT_SECRET` value, and the test asserts it is
  non-empty before scanning (the scan cannot pass vacuously on an unset value);
- `GET /admin/realms/eko/admin-events?max=500` and `GET /admin/realms/master/admin-events?max=500`
  (break-glass one token) are both non-empty — the realm import and the post-import client PUT
  really stored admin events this boot — and neither store's JSON contains the secret value;
- `GET /admin/realms/eko/events` and `GET /admin/realms/master/events` (the authentication-event
  store) likewise hold no occurrence of the secret value.

Result: `1 passed in 147.84s` (run completed 2026-11-09 ~12:05 local, ~11:05Z). The same test also
passed inside the QA round-2 final battery on composition `ekort-keycloak-41e2aaaf`
(`5 passed in 517.18s`, with the K-04 privacy/D-5/sessionId tests and the K-02 full-order test).

## What this closes

The security auditor's U-01 (round 1: secret-bearing admin events unproven for the eko-realm
client write path) — the observation now has a committed test plus this dated record. All values in
the composition are synthetic; no real credential appears here or in any tracked file.

## Limits

Local development composition on this host only; no shared/production host claim. The record is
the read the reviewer role can perform with `view-events` — it does not assert Keycloak will never
store a rotated secret representation in some future version, only that this accepted
import + PUT sequence stores none.
