# EKO-1-12 fix round 3 — ubuntu restart-bind hardening, self-diagnostics, CI ceiling retune — 2026-11-11

Date: 2026-11-11
Baseline SHA: 25966f92e51e327ddef74265bd80219b84750b06 (PR #135 head; worktree HEAD 752a65c, three local
cost-row commits on top)
Refs: Issue #126 (refs #53); CI run 42897088542; developer-infrastructure invocation 30
Local host: Docker Desktop engine 29.8.2 (Windows) — the fix-round-2 host
Status of this artifact: the invocation's report channel was consumed before the final delivery, so this
dated record carries the complete round (verdict, root cause, runs, findings, limits).

Verdict: READY FOR REVIEW (scope of this round, below), with two further reds found and NOT fixed here.

## Task

Root-cause the ubuntu-only CI red of `backend/tests/runtime/test_eko112_k04_admin_listener_log_privacy.py::
test_k04_admin_only_window_logs_the_console_redirect_restricted` in run 42897088542; harden its waits and
assertions the way its siblings were hardened; add self-diagnostics so any future red explains itself;
retune both runtime jobs' `timeout-minutes` 110 -> 140 in `.github/workflows/ci.yml` with their single
dated comment lines; prove locally; run the gates.

## CI observations (gh run view --job … --log, run 42897088542, retrieved 2026-11-11)

- `runtime tests on the composition` (job 130113003662): 20:37:27Z -> cancelled 22:27:42Z (the 110-min
  ceiling), last marker `[ 97%]`. Reds: the target test FAILED 21:23:14Z `[ 53%]`;
  `test_adr0004_proxy_routing.py::test_adr0004_admin_listener_refuses_a_source_outside_the_company_network`
  FAILED 21:03:15Z. No FAILURES section (cancellation ate the traceback).
- `runtime tests on the checked images (release mode)` (job 130113500495): 20:38:20Z -> cancelled
  22:28:35Z, last marker `[ 66%]`. Reds: the target test FAILED 21:30:31Z; the same adr0004 test FAILED;
  `marker_boot_binding` FAILED 21:23:19Z; `qa_open_gate_verification` FAILED 21:59:15Z;
  `qa_keycloak_start_that_cannot_rotate` FAILED 21:59:29Z; `r21_public_gate_residual_state` FAILED
  22:09:05Z; the ten `k04_boot_identity_carrier` shape tests ERRORed 21:32:09Z sixty milliseconds apart
  (one cached module-fixture failure of `live_boot`) while `test_k04_control_a_valid_token_reopens_serving`
  PASSED.
- Cross-check on main: run 42859268609, job 129988913751 — the adr0004 source-refusal test FAILED at
  17:33Z `[ 35%]` before the 75-min cancellation. It is PRE-EXISTING on main, not this branch's doing;
  it was invisible because main's runtime job never completes under its ceiling.

## Root cause (target test)

The test entered the admin-only window (`rm /data/public-open`, `compose restart proxy`) and then asserted
`listener_open(fresh, "admin")` as a one-shot probe, immediately after the restart command returned.
`compose restart` returns when the container has STARTED, not when Caddy has bound the configuration
`proxy/entrypoint.sh` selected. On the ubuntu runners the next TCP attempt lands inside that window, the
connection is refused, `listener_open` returns False and the assertion "the admin listener closed in its
own open window" fires — deterministically enough to lose in both jobs while the same code passed
standalone-cold on Docker Desktop twice. This is exactly the race the EKO-1-12/qa2-3 mutation finding
(F-04) recorded; every sibling now guards it (`wait_for_proxy_running` + settle in the marker/restore
tests, `wait_for_serving` in the qa and r21 tests, both in the boot-identity carrier). This file was the
only family member still unguarded.

Corroboration (not a traceback — the FAILURES section was eaten): the test consumed 69 s in the
composition job and 100 s in the checked job, while each job's own `prepare + run_bootstrap` measured
~65-70 s / ~95 s (carrier module-fixture timings) — the failure sits a few seconds after the bootstrap
returned, in the restart transition, not in the login flow (which needs 10+ s of Keycloak round-trips)
or the log-read asserts. The probes below independently show the window's shape: on this host a fully
broken (zero-budget) wait fails where the 1-second version passes — Desktop's restart round-trip alone
outlasts the bind and hides the race; the runners do not.

Suspects examined and demoted: the "Running-while-restarting" qa2-3 class needs a crash-looping proxy;
here the entrypoint selects Caddyfile.admin and stays up — the imported `wait_for_proxy_running` guards
it anyway. Log flush (suspect c): the c4 `window(...).text(settle=1.0)` family passed on the same
runners, so the single `settle=2.0` read became a bounded poll (the sibling 90 s budget) — a late flush
can now only be caught, never raced; the final leak scan uses a fresh settled read after the access line
appears, so later lines cannot escape it.

## What changed

- `backend/tests/runtime/test_eko112_k04_admin_listener_log_privacy.py`:
  restart -> `wait_for_proxy_running` (120 s, imported from `test_eko112_k02_marker_boot_binding`) ->
  `wait_for_serving("admin")` (90 s, imported from `test_eko112_qa_fail_closed_proxy_gate`) ->
  `admin_status == 200` -> `listener_open` -> `assert_connection_death("auth")` — the death claim is now
  made only after the entrypoint demonstrably bound, so it names the admin-only selection, not the
  nothing-bound-yet window (the correction qa2-3 forced on the blind-touch phase, applied here before it
  was ever red on Desktop);
  access-line read -> original settled read, bounded poll until the line appears (90 s sibling budget),
  final settled read for the leak scan;
  every assertion in the test and its login helper carries `phase_note`: proxy container state,
  `boot identity observed=` and per-gate `marker present=/names_current_boot=` as BOOLEANS, and the last
  12 proxy log lines as JSON field-name sets (`docker logs` raw, like the window itself — `compose logs`
  prefixes lines and would defeat the parse). No raw line, no marker/token/uri value ever enters a
  message: the unrestricted shape this test exists to catch is a line whose uri holds the authorization
  code; `proxy_line_problems` output is additionally `<redacted>` against the code value. The old message
  that echoed raw log lines (`others[:3] mine[:3]`) is gone for the same reason.
  Docstring records the finding, the host split and the discipline. Test count unchanged (1).
- `.github/workflows/ci.yml`: `runtime` and `runtime-checked` `timeout-minutes: 110 -> 140`, each with
  its ONE dated comment line directly above rewritten, mask shape preserved (single `    # ` line).
- This evidence file.

## Local runs on this host, 2026-11-11 (synthetic accounts/ports only; no secret values read or printed)

- hardened file standalone-cold: `uv run pytest tests/runtime/test_eko112_k04_admin_listener_log_privacy.py
  -m runtime -q` -> `1 passed in 345.32s (0:05:45)`.
- mutation probe 1 (the serving wait broken to a 1 s budget): -> `1 passed in 352.84s (0:05:52)` —
  the red did not fire at 1 s on this host; informative: Desktop answers within that second, which is
  why two cold Desktop runs never saw the window the runners lose.
- mutation probe 2 (the same wait broken to a 0 s budget — one window, then restored):
  -> `1 failed in 405.50s (0:06:45)` with the failure message carrying the phase state:
  `AssertionError: the admin listener never became reachable: not attempted | phase: proxy running=True
  status=running exit=0; boot identity observed=True; admin marker present=True names_current_boot=True;
  public marker present=False names_current_boot=False; proxy log tail field names: adapter,level,msg,ts |
  level,logger,msg,ts | cache,level,logger,msg,ts | level,logger,msg,server_name,ts | instance,level,logger,
  msg,storage,try_again,try_again_in,ts | level,logger,msg,ts | level,logger,msg,path,ts | addr,level,
  logger,msg,ts | level,logger,msg,name,protocols,ts | domains,level,logger,msg,ts | file,level,msg,ts |
  level,msg,ts` — field names only, exactly as designed. During probe 2 a defect in the new diagnostic
  helper itself was found and fixed (the `compose logs` prefix above); that code runs only on the failure
  path, so the green run's flow-code is byte-identical to the final file's.
- gates after restore: `uv run ruff check .` / `ruff format --check .` / `mypy .` (backend) ->
  All checks passed / 229 files already formatted / Success, no issues;
  `uv run pytest tests/static/test_eko119_k03_release_mode_ci.py tests/static/test_eko120_ci_timeout_retune.py -q`
  -> `102 passed`;
  `uv run pytest tests/static/test_k04_composition.py -q` -> `73 passed` (see the stale-cache note below);
  `bash tests/doc-checks/EKO-1-12.sh` (repo root) -> `4 passed, 0 failed`;
  `node tools/check-links.mjs` -> clean (131 links, 99 files);
  full default suite `uv run pytest -q` -> `1746 passed, 448 deselected, 2 warnings in 2646.49s (0:44:06)`,
  exit 0 (overlapped the two cold docker runs, hence the wall time; collected and ran against the final
  ci.yml — the only later edit was inside a runtime-marked file, deselected in that suite);
  clean un-contended re-run of the same command -> `1746 passed, 448 deselected, 2 warnings in
  3204.68s (0:53:24)`, exit 0 — both default-suite sessions agree;
  `weakening-check.sh / leftovers-check.sh / layer-check.sh origin/main` -> clean on HEAD, and re-run
  against a `git stash create` revision so the verdict covers the uncommitted worktree.
- residue: no `MUTATION-PROBE` string anywhere in the tree; no `ekort-*` containers or volumes left
  (the `fresh` fixture's own `down -v` teardown).

## Cache artifact worth recording

`.pytest_cache/v/cache/lastfailed` carries `tests/static/test_k04_composition.py::
test_k04_c4_fails_on_a_fourth_named_volume` — that nodeid does not exist in the current tree (no "fourth"
matches under tests/, the file runs green alone, and 2b7f871 rewrote that section, its comment pinning
the superset half elsewhere). The entry is a stale survivor from the invocation-28 static-carrier attempt
reverted at its clean stop; pytest keeps lastfailed entries for nodeids it can no longer collect. The
exit-0 default-suite run is the authoritative state: 1746 passed.

## Findings for the driving session — found in this round's log forensics, deliberately NOT fixed here

1. `test_adr0004_admin_listener_refuses_a_source_outside_the_company_network` fails on ubuntu in both
   jobs AND on main (run 42859268609). Mechanism from code: its entry path is `touch /data/admin-open`
   with no Keycloak in the bring-up — under the accepted boot-bound marker (ADR-0004-C33, on main since
   the round-1 checkpoint) a blind empty touch names no boot and the identity helper itself reads no
   token without the keycloak container, so the entrypoint selects Caddyfile.closed and the 60 s poll
   dies at "the admin listener never became reachable behind its marker". EKO-1-12 gate-semantics
   collateral predating this invocation; the CI re-run will still be red here unless it is fixed.
   Probable fix shape: write a synthetic token through the carrier's one-off `write_boot_token` plus
   `write_gate_marker`, keeping the foreign-CIDR 403 contrast intact — a design call for gate 2/QA,
   not this round's approved criteria.
2. The checked-images job (`EKO_CHECKED_IMAGES`) red set: `marker_value` in
   `backend/tests/runtime/keycloak_client.py` (and the same `{project}-proxy:latest` reseed in
   `test_eko112_qa_fail_closed_proxy_gate.py::test_qa_keycloak_start_that_cannot_rotate_the_token_dies_loudly`)
   runs `docker run {project}-proxy:latest`, an image name compose only produces in BUILD mode; in
   release mode the proxy image is `eko-crm/proxy:checked` loaded from the artifact, the convention tag
   does not exist, and every test using the helper fails at its returncode assert. Exactly the
   job-only reds and the ten carrier ERRORs are the marker_value users; every non-user passed
   (`test_k04_control_a_valid_token_reopens_serving`, `test_qa_admin_marker_opens_only_the_admin_listener`,
   `test_qa_boot_carrier_seeds...`). Fix shape already proven in `write_boot_token`: resolve
   `composition.inspect("proxy")["Config"]["Image"]` instead of the naming convention. Out of this
   round's approved scope; needs its own task (it breaks the release-mode gate this PR rides on).
3. Capacity: 140 is shaped on the composition job's measurement (~112 min extrapolated from 97% at ~105
   min of test time). The checked-images job was at 66% when cancelled; nothing here proves 140 fits it.
   The runtime-checked ci.yml comment says so explicitly and names a second cancellation as the retune
   signal.

## What this round does NOT prove

- the exact CI assertion text of the ubuntu failures (traceback swallowed) — the attribution rests on
  two-runner determinism, the timing fit and the sibling precedent; the phase note exists so the next
  red states it itself;
- green on ubuntu for the hardened test — that requires the re-run (the hardening reuses patterns that
  ARE proven green on ubuntu runners, which is the argument, not the proof);
- 140 min sufficing for the checked-images job (finding 3);
- production behavior of anything — all observations are the local composition and one CI runner;
- QA's independent mutation of THIS hardening (removing the serving wait must bring the runner red back;
  restoring the one-shot probe must not turn the test green) — the zero-budget probe is a developer
  self-check, not QA's mutation under the write boundary;
- the two findings above are not fixed, and the re-run will not be fully green until the driving session
  decides on them.

## For gate 3 — proposed entries (proposals only; nothing checked here)

- PLAN/mutation note: EKO-1-12 fix round 3 — hardening of `k04_admin_listener_log_privacy` (restart-bind
  waits + failure-phase diagnostics); QA mutation candidate: delete the `wait_for_serving("admin")` guard
  -> the pre-hardening red must return on a runner.
- Exception register: none new. The runtime ceilings at 140 min are an operational bound recorded in the
  ci.yml comments themselves; no capability status claim.
