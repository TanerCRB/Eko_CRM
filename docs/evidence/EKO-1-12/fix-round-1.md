# EKO-1-12 fix round 1 — evaluator STOP findings — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the runs: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: this fix round's uncommitted implementation)
Image under the runtime runs: `localhost/eko-crm/keycloak:26.8.1-eko112`
(<image-digest after the provider rebuild>), rebuilt per `custom-image-build.md` with the
provider field-enforcement extension (G-01/S-01); see `custom-image-build-fix1.md`.

## What this round changes (finding map)

| Finding | Mechanism | Test / record |
|---|---|---|
| G-01 + S-01 | Provider: master/admin destinations stripped of any session identifier (top-level `sessionId` cleared outside the accepted application-realm *Retention* scope) and of unknown-account typed usernames (`LOGIN_ERROR` with error `user_not_found` outside the application realm loses `details.username`; known-account usernames remain under the base rule) | `identity/provider` behavior test (gates the image build); runtime `test_eko112_k04_unknown_username_d5.py::test_eko112_unknown_username_d5_master_realm`; `test_eko112_k04_reset_and_log_privacy.py` sessionId-column assertion no longer skipped for master/admin |
| R-01 | `proxy/Caddyfile.admin` carries the same `log default` restriction and `import access_log` as the full file's admin site | static `test_eko112_k04_caddy_admin_log_parity.py` (committed, red before the Caddyfile change: 3 failing checks observed at the pre-change baseline run); runtime `test_eko112_k04_admin_listener_log_privacy.py` (admin-only window console login; proxy log line for the `?code=…` redirect carries no query, no remote address, matches the documented C4 form) |
| R-05 = S-03 | Gate markers are bound to the current Keycloak boot: `open_gate` records the boot identity the proxy itself observes (ARP-resolved hardware address of the running `keycloak` container — assigned per container creation); `proxy/entrypoint.sh` opens a listener only while the marker names the live boot | static: helper shipped in the proxy image (`proxy/Dockerfile`); runtime `test_eko112_k02_marker_boot_binding.py` (bootstrap → recreate Keycloak without bootstrap → proxy restart → both listeners connection-dead → rerun reopens) |
| R-06 | Failed gate verification removes its own marker, re-closes the proxy, and records the residual state; wait ceilings raised past the healthcheck worst case (`--wait-timeout` 420 s; gate reachability deadline 420 s wall clock) | `scripts/keycloak-bootstrap.sh` `open_gate`; QA contrast test 3 + the residual-state assertion in `test_eko112_qa_fail_closed_proxy_gate.py` |
| R-07 | `find_user` reads the filtered `username`+`exact` admin query | runtime `test_eko112_k02_bootstrap_order.py::test_k02_rerun_after_the_realm_grew_past_the_default_page` (seed >100 master-realm users, page-cap premise asserted, rerun succeeds) |
| S-04 | kcadm session teardown (`$HOME/.kcadm` in the Keycloak container) at the end of `import_with_kcadm` | runtime `test_eko112_k02_bootstrap_order.py::test_k02_bootstrap_leaves_no_kcadm_session` (folded into the paging test's run) |
| R-03 | Every reset-mail delta is a bounded, recipient-specific poll (arrival wait + settle) instead of a single global snapshot; the unknown-address assertion is recipient-scoped | `test_eko112_k04_reset_and_log_privacy.py` helpers; `test_eko112_k05_reset_timing.py`; K-05 green standalone-cold twice |
| R-04 = G-04 | Restore half of C29 executed: on-demand backup through the accepted path, `DROP DATABASE keycloak` + `pg_restore` of the set's keycloak dump, bootstrap rerun asserting the provider pair precedes both listener opens; break-glass divergence observed (env rotated → exit 1 with both listeners closed → matching env reopens) | runtime `test_eko112_k02_restore_reverification.py`; dated record `restore-reverification.md` |
| G-03 | Inherited expiry paths probed through the custom store: `ClearExpiredEvents` → `EventStoreProvider.clearExpiredEvents()` (inherited unchanged) and `ClearExpiredAdminEvents` → the factory's `JPA_EVENT_STORE` invalidation handler that casts to `JpaEventStoreProvider` (the subtype satisfies the cast); expired rows removed at 30-day (eko auth) / 90-day (eko+master admin, master auth) while controls survive | runtime `test_eko112_k04_event_expiry.py`; dated record `event-expiry-probe.md`; mechanism pre-observed in a throwaway standalone Keycloak (same custom image) |
| S-02 | `offline_access` dropped from the application client's `optionalClientScopes` (export + live read) | static exact-set guard in `test_eko112_k01_realm_export.py` (red before the export change); live assertion `test_k03_application_client_carries_no_offline_access_capability`; U-02 note in `offline-scope-removal.md` |
| R-08 | doc-check accepted-text guard run against a diff base (`origin/main...HEAD`, overridable with `EKO112_DIFF_BASE`) | `tests/doc-checks/EKO-1-12.sh` |
| U-01 | OIDC client secret value asserted absent from stored eko-realm and master-realm admin events after both writes (import + PUT) | `test_eko112_k03_runtime_roles_and_events.py::test_k03_client_secret_absent_from_stored_admin_events`; result recorded in `admin-event-secret-probe.md` |
| R-02 | no in-scope fix — needs the release workflow and a publishing decision | report section "For a human" |
| G-02 | no code change possible — Keycloak does not emit what the locked criterion names (and 26.8.1's `EventType` has no `USER_DISABLED_BY_BRUTE_FORCE` constant at all; the real 26.8.1 lockout types are `USER_DISABLED_BY_PERMANENT_LOCKOUT`/`USER_DISABLED_BY_TEMPORARY_LOCKOUT`, neither in the accepted `enabledEventTypes`) | report section "For a human" |

## Red-before-change observations (this round)

- static parity + offline exact set, run against the un-fixed tree:
  `uv run pytest -q tests/static/test_eko112_k01_realm_export.py tests/static/test_eko112_k04_caddy_admin_log_parity.py`
  → `4 failed, 19 passed` (2026-11-07) — the three admin-site/`log default`/`access_log`
  drift failures plus `test_k01_application_token_...` failing the exact `optionalClientScopes`
  set while the export still named `offline_access`.
- runtime master-realm D-5 + sessionId-column, red batch on the PRE-rebuild image:
  `uv run pytest -m runtime … -q` → `2 failed, 4 passed in 570.07s`; the failures verbatim:
  `D-5 STOP: unknown typed username matched a master events field path` (G-01) and
  `session identifier at non-excepted master:sessionId` (S-01). The known-account master
  carrier kept its username in the red run too, so the assertions distinguish unknown-account
  removal from indiscriminate removal.
- marker boot binding, red before the mechanism: the batch failed at
  `the proxy could not observe a Keycloak boot identity after a bootstrap` (no helper in the
  image, marker content empty) — `test_eko112_k02_marker_boot_binding` red.
- admin-only log window, red before the parity fix: no restricted access line for the
  `?code=…` console redirect (the admin-only Caddyfile had no log directive at all):
  `no access line for the console redirect`. (Observed sub-finding: Caddy 2.11.7 with no log
  directive emits no per-request line at all; the drift fixed here is silence-vs-restricted-
  line against the full configuration's same site, which the docs claim is one restricted line
  per request on every listener.)
- paging (R-07), red before `find_user` used the exact query: the rerun after seeding 150
  master-realm users died with `Keycloak POST /admin/realms/master/users: HTTP 409` —
  deterministic demonstration that the unfiltered page-capped read misses accounts (batch 1
  trace). kcadm teardown had no red here because the S-04 path in the finding
  (`~/.kcadm/config`) is not where Keycloak 26.8.1's kcadm writes; a probe on this image
  shows it writes `$HOME/.keycloak/kcadm.config` — the teardown and the k02 check use the
  probed path, and the script aborts if removal misses, so the check cannot pass vacuously.

## Green-after-change runs

- provider/shared-session batch (rebuilt image `387f615a…`): `uv run pytest -m runtime
  tests/runtime/test_eko112_k03_runtime_roles_and_events.py
  test_eko112_k04_reset_and_log_privacy.py test_eko112_k04_unknown_username_d5.py
  test_eko112_k05_reset_timing.py -q` — `11 passed in 447.47s` (one bootstrapped composition).
  Confirms: G-01/S-01 (master D-5 + tightened sessionId column now green), U-01 (client secret
  absent from both realms' stored admin events), S-02 (live offline-scope absence), R-03 (mail
  deltas via bounded recipient polls) — all previously red or unproven.
- gate batch (fresh compositions): `1 failed, 9 passed, 1 error in 3973.17s` — passed: all
  five K-02 order/contrast tests (including the new past-the-page rerun + kcadm-absence test),
  the marker-boot-binding test, the admin-only-window log test, QA contrasts 1 and 2 (a blind
  empty `touch` no longer opens; the current-identity marker opens exactly the admin
  listener). The failure was QA contrast 3: the failed gate's marker survived because
  `compose exec` cannot reach the crash-looping proxy — replaced by a one-off volume-mount
  removal. The error was the developer editing the script while the offline test re-ran the
  bootstrap (half-written file read) — no product defect; clean rerun below.
- rerun batch: QA contrast 3 (marker removed by the failure path, residual-state record
  line present, auth connection-dead) + the live offline-scope test — both PASSED; the
  first restore and expiry runs failed on harness bugs of this round (a compose-level call
  for `docker network connect`; psql `-c` does not substitute `-v` variables; then the
  realm-scoped SQL matched on realm NAME while Keycloak 26 stores the realm UUID — the
  census diagnostic surfaced this; all replaced by repo-proven patterns), and the expiry
  readback reused an access token past its 240 s lifespan (re-minted before the readback).
- restore batch: PASSED — `1 failed, 1 passed in 376.98s` (the co-run expiry failed on the
  UUID/NAME issue then; the restore chain ran end-to-end green, `restore-reverification.md`).
- expiry: PASSED — `1 passed in 1003.79s (0:16:43)` on its own fresh bootstrapped composition;
  the server's own 900 s cycle (observed fire ≈ boot + 900 s) removed the 31-day-aged eko
  `LOGIN_ERROR`, the 91-day-aged master `LOGIN`, and both 91-day-aged admin events
  (eko UPDATE, master CREATE) while the un-aged controls survived — counts asserted by row
  identifier via SQL (`after == before - 2` on each table) and the controls re-read through
  the reviewer-visible admin queries with a freshly-minted break-glass token. Record:
  `event-expiry-probe.md`.
- standalone-cold K-05 ×2: `1 passed in 131.57s` then `1 passed in 133.11s`, each its own
  fresh bootstrapped composition with a cold mail queue — the exact scenario QA and the
  reviewer observed red (`[0,0,0,0]` vs `[1,1,1,1]`); the first run regenerated
  `reset-timing.json` (known deltas `[1,1,1,1]`, unknown `[0,0,0,0]`, cold first known_ms
  192.066 showing the warm-up effect) and `reset-timing.md` keeps the human finding
  UNDECIDABLE. The race is observed dead on two consecutive cold runs. Closing-cycle
  reproduction (2026-11-09): two further standalone cold compositions, each its own fresh
  bootstrapped composition, both `1 passed` (recording run completed 07:21:20Z,
  confirming run 07:28:03Z); `reset-timing.json` and `reset-timing.md` now carry the
  regenerated 2026-11-09 series (cold first known_ms 268.661, same structure), human
  finding unchanged at UNDECIDABLE.
- static gates (final tree): full default suite `uv run pytest -q` →
  **`1596 passed, 398 deselected, 2 warnings in 505.98s (0:08:25)`, exit 0** (the 5 added
  statics: parity ×4 + the offline exact-set mutation guard); `ruff check .` exit 0;
  `mypy .` — No issues found; doc-checks `4 passed, 0 failed` with the fork-base guard
  reactive (the old worktree-only diff could not see committed edits; the merge-base diff
  catches line moves as deletions); `node tools/check-links.mjs` — 100 links in 96 files,
  0 broken; teardown audit: 0 stray containers/volumes from this round.

## For a human

Restored by the closing cycle 2026-11-09 from the invocation's state ledger wording — the
finding map references this section, but the round's stack died before it was written in.

- R-02 — NEEDS A HUMAN. No in-scope fix: the switch to the locally built custom Keycloak image
  breaks the accepted release flow (`scripts/release-images.sh pulled-digests` demands a registry
  digest a locally built image does not carry; keycloak is absent from NAMES/CHECKED_SERVICES and
  from the workflow image step). What is required is a release-workflow change plus a publishing
  decision for the custom image — both outside this task's scope lock. A passing
  `pulled-digests` run on this host proves only an id-mirrored digest on this host.
- G-02 — NEEDS A HUMAN. No code change is possible: Keycloak does not emit what the locked
  criterion names — 26.8.1's `EventType` has no `USER_DISABLED_BY_BRUTE_FORCE` constant at all;
  the real 26.8.1 lockout types are `USER_DISABLED_BY_PERMANENT_LOCKOUT` and
  `USER_DISABLED_BY_TEMPORARY_LOCKOUT`, neither in the accepted `enabledEventTypes`. In the
  accepted configuration a completed reset stores `UPDATE_PASSWORD`, not `RESET_PASSWORD`
  (the type exists but is unemitted here). The committed test encodes the reachable set instead
  (G-02's own disclosure); the transcription ruling — an ADR-0005 Retention addendum, an
  amended criterion text, or a recorded gate-2 exception — is the human's, not the developer's.

## Limits

Local development composition only; no production claim. Synthetic values only; no credential,
token, cookie, session identifier, marker value or personal data appears in any record here.
The boot-identity mechanism proves the listener boundary for composition bring-ups on this host;
it is not a production host-control mechanism. The expiry probe rides on the server's own
default 900 s schedule (`scheduled.interval` default; observed cycle timing recorded in
`event-expiry-probe.md`); it does not claim timing for any other deployment.
