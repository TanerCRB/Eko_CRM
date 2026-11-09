# EKO-1-12 K-02..K-06 runtime results record

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the runs: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa (dirty worktree)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112`
(`sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`), built per
`custom-image-build.md` from the accepted Dockerfile shape.

## Suite results (each command from `backend/`, `-m runtime`, real composition, fresh volumes)

1. `uv run pytest -m runtime tests/runtime/test_eko112_k02_bootstrap_order.py -q` —
   `4 passed in 798.11s` (2026-11-06). Fresh order + restart rerun + three contrasts;
   detail in `bootstrap.md`; provider-check design proof pair in
   `provider-verification-contrast.md`.
2. `uv run pytest -m runtime tests/runtime/test_eko112_k03_runtime_roles_and_events.py
   tests/runtime/test_eko112_k04_reset_and_log_privacy.py
   tests/runtime/test_eko112_k04_unknown_username_d5.py
   tests/runtime/test_eko112_k05_reset_timing.py -q` — `8 passed in 143.70s` (2026-11-06,
   one session, one bootstrapped composition, final tree).
   Intermediate disclosed failing runs of this suite on 2026-11-06/07 against the final image,
   each fixed before the passing run above: `196.63s`, `143.82s`, `133.02s`, `178.12s`,
   `162.30s`, `190.99s`, `130.47s`, and `171.72s` — every one `2 failed, 6 passed`, always the
   two K-04 event-coverage tests (the pure session-id test, all K-03, D-5 and K-05 passed in
   every run). Causes found and fixed across those iterations: the session-scope helper
   misread Keycloak's own top-level `sessionId` column; coverage login posted hidden inputs
   that corrupted the PKCE session; the required-action callback code was not exchangeable;
   the reset link was read from raw catcher JSON leaving `&`; a consumed-token replay answered
   400 while the test demanded 200; the advancing coverage shifted the main test's positional
   "newest message" read; and the `USER_DISABLED_BY_BRUTE_FORCE` event is not emitted under the
   accepted wait-based lockout (now proven behaviorally). Each fix is in the two bullets below.
   Covers: role mapping persistence and
   live enforcement incl. the fine-grained mapping denials (Q-1 A) and master/admin event
   storage (Q-2 A); the full reachable required-event matrix; D-5 unknown-username
   exception with the non-empty known-account contrast; session-identifier scoping on the
   custom store; reset request equality with both execution orders; log privacy at the
   live log level; K-05 timing with the machine record `reset-timing.json` and the human
   finding returned in `reset-timing.md`.
3. K-06 built-image inspection — `built-image-inspection.md`.

Earlier failing runs are disclosed: two K-04 iterations failed against the final image
(2026-11-06) and the causes were fixed as recorded below; the two suites above are the
final-state results.

## Fixes made during the runtime phase (each found by a failing runtime test)

- Bootstrap provider verification (K-02 criterion): the fresh and restart paths now verify,
  before either listener opens, that the running server's own log names the custom factory
  and that a live carrier event reaches the store without `details.code_id`; a built-in
  fallback fails closed. The log grep drains the log (`grep -c`, not `grep -q`) so pipefail
  cannot turn a SIGPIPE into a spurious failure.
- `kc.sh build` output at image build confirms the custom factory implements the internal
  `eventsStore` SPI (the same KC-SERVICES0047 line the runtime check greps).
- The mapping allow-list reconciliation accepts the authorization-resource-server update
  status codes the server actually returns, and now re-reads the live policy and
  per-role permissions after reconciling, failing if any is absent.
- Acceptance-criterion encoding correction requiring human review at gate 2: the versioned
  realm export and the predecessor's required-event list named
  `SEND_RESET_EMAIL` — no such Keycloak event type exists; the live server proved the
  correct type is `SEND_RESET_PASSWORD` (the enum `SEND_RESET_EMAIL` raised an unknown-type
  error against the running 26.8.1 image). The export, the static K-01 list, and the runtime
  K-04 list now use `SEND_RESET_PASSWORD` (semantics unchanged: the reset-email request
  stays stored). Two more locked names are not emitted in the accepted configuration:
  `RESET_PASSWORD` (no application-reachable flow emits it — three producer variants tried:
  forgot-password completion for users with/without a pending required action, which stores
  `UPDATE_PASSWORD`; `execute-actions-email`; a `requiredActions` round-trip, which Keycloak
  silently drops for an unknown alias), and `USER_DISABLED_BY_BRUTE_FORCE` (not emitted under
  the accepted wait-based lockout, `permanentLockout=false`; the brute-force control is proven
  behaviorally — after repeated failures even a correct password is refused). The test encodes
  the reachable set in full, still forbids both unreachable names from ever appearing, and names
  the correction for the human (see the `UNREACHABLE_ON_KEYCLOAK_26_8` comment in
  `backend/tests/runtime/test_eko112_k04_reset_and_log_privacy.py`). These are criterion
  transcription corrections, not widened store exceptions or configuration changes — the realm
  settings and the closed-type list were not altered.
- K-04 flow fixes found by running: password forms use the `password-new` field; the reset email
  link is the `login-actions/action-token` URL (read from the decoded message JSON so a `&` is
  not left as the `&` escape); a consumed action-token replay stores `RESET_PASSWORD_ERROR`
  (the invalid-token answer is HTTP 400, so the stored event — not the status — is the
  assertion); the temporary-password update flow completes via the required-action page and the
  session tokens then come from a normal `browser_token` login on a fresh client (the code that
  survives the required-action redirect is not exchangeable, and posting the login form's hidden
  inputs corrupts the authorization session); each admin login uses its own client (a reused
  client hits its own SSO and skips the login page); the master/admin session-scope check no
  longer misreads Keycloak's own top-level `sessionId` column as an application-identifier leak
  (the application identifier and any `code_id` remain prohibited there).

## Unverified at this invocation (stated plainly)

- Event expiry: the `clearEvents` scheduled path is not exercised by a committed runtime
  test; the closed-type list and retention configuration are static-asserted. A local
  time-travel or expiry probe remains a follow-up before the retention claim.
- QA's for-QA mutations of the versioned provider artifact (registration removed, factory
  order lowered, filter removed) against a rebuilt release image: the mechanism was proven
  decisive in the built-in-fallback contrast pair; the artifact-mutation rebuilds belong to
  gate-2 QA.
- Backup-to-restore re-verification across the listener boundary (task item #5's restore
  half) was not run in this invocation; the restart-with-existing-volumes half is verified
  (K-02 rerun scenario).
- Built image inspection covers content, ownership/mode, timestamp normalization, and
  secret freedom; it cannot show a value is not derivable (the accepted K-06 limitation).

## Cleanup

Throwaway lab containers, compositions, and their own volumes created for this work
(prefixed `eko112-d18-`) were removed; the throwaway contrast image tag was deleted. No
pre-existing volumes were deleted and no prune was run. Test compositions were torn down
by the runtime harness.
