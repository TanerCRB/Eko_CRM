# EKO-1-12 fix round 4 — the release-mode red FAMILY: image-name assumption, shipped marker-removal path, stale blind-touch test — 2026-11-11

Date: 2026-11-11
Baseline SHA: 752a65c (branch `EKO-1-12-bootid`; PR #135 refs #53; CI head at cancellation was 25966f9)
Refs: Issue #126 (boot-identity correction, itself the correction of the 2026-11-10 ADR-0004 addendum)
CI forensics: run 42897088542 (jobs 130113003662 composition / 130113500495 checked-images), run
42711869762 (jobs 129483303120 / 129483706091) — both cancelled at their ceilings, no traceback section;
the failure sets were read from the live progress markers and cross-checked against main (round-3 finding 1).
developer-infrastructure invocation 31. Builds on invocation 30's uncommitted work (the
admin-privacy restart-bind hardening and the 110 -> 140 ceilings), which this round keeps unchanged.

## Verdict

READY FOR REVIEW. The release-mode red family is THREE distinct defects, not one race:

1. IMAGE-NAME ASSUMPTION (release-only, five tests): `marker_value` in
   `backend/tests/runtime/keycloak_client.py` and the inlined twin in
   `test_eko112_qa_fail_closed_proxy_gate.py::test_qa_keycloak_start_that_cannot_rotate_the_token_dies_loudly`
   ran their one-off `docker run` from the locally built `<project>-proxy:latest` tag. A release run
   (EKO-1-15 K-02, `EKO_CHECKED_IMAGES`) resets the build config and loads `eko-crm/proxy:checked`;
   the convention tag never exists there, so every marker reader died with
   `Unable to find image ...` — the k02 marker-binding and qa open_gate FAILEDs, the r21 FAILED, the
   cannot_rotate FAILED, and the boot-identity-carrier ERRORs (the failure sat in the module-scope
   `live_boot` fixture, which is why it is an ERROR and why all ten shape params died 60 ms apart
   while `test_k04_control_a_valid_token_reopens_serving` — the one consumer that never reads a
   marker through the one-off — passed). This is NOT the restart-bind race. Fix: both sites read
   `Config.Image` of the composition's own proxy container — the convention the rest of the suite
   already uses (`write_boot_token`, the labs, `test_k04_image_checks`); `docker compose ps -a`
   finds the container exactly in the crash-looping state this reader exists for.
   Locally reproduced RED under the release env BEFORE the fix (carrier `len-head-7`, checked-env
   invoke, ERROR at setup: `Unable to find image 'ekort-k04-fda6037d-proxy:latest'`) and GREEN
   after. The same tag pattern in the SHIPPED script — see 2 — had the same effect on the wire.

2. SHIPPED MARKER-REMOVAL PATH (release-only, production defect): `scripts/keycloak-bootstrap.sh`
   `open_gate`'s failure tail resolved its one-off removal image with
   `docker image ls --filter reference=${COMPOSE_PROJECT_NAME}-proxy:latest` — the build-mode tag.
   Under `EKO_CHECKED_IMAGES` the list is empty, the resolution fails closed, and a failed gate's
   marker STAYS ON THE VOLUME with no `marker removed` record: the residual-state contract of R-06
   and R-21 is unenforceable in release mode. Even with defect 1 fixed, qa open_gate and r21 would
   remain red in the release job for this reason. Fix: resolve the image the same way as the tests
   — `Config.Image` of the project's proxy container (`compose ps -a -q proxy`) — keeping the
   fail-closed contract: no container, no image, no removal, the run ends. Both stderr messages and
   every record string are byte-identical.

3. STALE BLIND-TOUCH TEST (BOTH modes, predates this branch):
   `test_adr0004_proxy_routing.py::test_adr0004_admin_listener_refuses_a_source_outside_the_company_network`
   opens the admin gate with `touch /data/admin-open`. Since the boot-bound marker landed (round-1
   checkpoint, on main since #117), an empty marker names no boot and the entrypoint serves closed —
   the test's poll died at "the admin listener never became reachable behind its marker" in BOTH
   runtime jobs (the driver's "release-only, 35%" read was the pytest progress marker, not a rate;
   confirmed red locally, build mode, before the change). EKO-1-12 mechanism collateral on an
   EKO-1-06 test, unfixed by the correction.
   Decision — fix here, not a separate Issue: the breakage is caused by the gate semantics this very
   branch owns, the fix is one test file inside the write boundary, and the runtime gate this PR
   rides cannot go green without it. The phase now starts Keycloak (its wrapper rotates the boot
   token as the first act of every start — no bootstrap, which cannot run under the foreign CIDR
   set anyway), reads `boot_identity` once (bounded: the `up --wait` health gate already proves the
   rotation happened), and writes the marker through `write_gate_marker` — the same primitive
   `open_gate` uses. The restart gained the family's proven waits: `wait_for_proxy_running` (120 s,
   container start) then `wait_for_serving` (90 s, "any HTTP status = bound") — replacing the
   bespoke one-shot 60 s window. The criterion is unchanged: the observed status must be 403, the
   proxy's own refusal; behind the marker the listener now has an un-bootstrapped Keycloak, so a
   leaked request would be Keycloak's own 503/200 — never a proxy 403 (file docstring corrected).

## Restart-bind hardening (the family member that IS the race)

Invocation 30's `test_eko112_k04_admin_listener_log_privacy.py` rewrite is kept as written and is
the template (`wait_for_proxy_running` -> `wait_for_serving` -> death claims after the entrypoint
demonstrably bound; `phase_note` diagnostics naming states and field names only). On top:

- k02 marker-binding: the recreate-phase identity read now uses the file's own
  `wait_for_rotated_identity` (90 s) instead of a single-shot read; both stale-marker phases read
  the sockets only after `wait_for_closed_selection` — a new shared helper in the qa hub file that
  waits for the entrypoint's OWN closed-decision line ("gate markers do not name the running
  Keycloak boot; serving closed") as the positive bind proof for the state where no listener may
  answer — then the sibling-proven 3.0 s settle. An occurrence delta against a baseline read before
  the restart (no `--since`, no dependence on host-vs-daemon clock agreement; container logs
  persist across restarts). Without it, a death read inside the bind window passes vacuously —
  the qa2-3 false-pass shape.
- qa open_gate tail: the failing bootstrap's re-close restart is waited out (Running + the same
  3.0 s settle) before the auth-death read; with no marker left there is no decision line, so the
  comment names the mutation carriers honestly (exit code + events; this settle only prevents the
  vacuous wire pass).
- No new timeout numbers anywhere: 120 s = `wait_for_proxy_running`'s budget, 90 s =
  `wait_for_rotated_identity`/`wait_for_serving`'s, 3.0 s = the blind-touch phase's settle.

## Timeout verdict (EKO-1-19 K-03 / EKO-1-20 carriers unchanged)

KEEP 140 (invocation 30's change, untouched). Composition job: 97% of 448 tests in 110 min ->
~113-115 min full, fits. Checked job: its pace was close to the composition job's in every
milestone readable from the two logs (proxy_routing 34% at 21:03 vs 21:06; open_gate starts 21:51
vs 21:50); reds in the release job were FAST failures (image-not-found returns in seconds), so the
fixed suite does not gain their old budget but does now run the scenarios they aborted (carrier's
ten restarts are ~4 s apart in the composition job; k02's full phases add ~5 min; cannot_rotate
~2 min) — estimated release completion ~125-135 min, inside 140. The margin is not proven; the
first fixed release-mode run is the judge, and a second cancellation is the retune signal already
named in the ci.yml comment.

## Assumptions

- A-01 (criterion: proxy_routing refusal contrast): unclear whether the 502 argument in the file's
  docstring is a requirement or an artifact of the old marker semantics. Assumed: the criterion is
  "the proxy itself refuses with 403", the upstream state behind an open gate is not part of it;
  started Keycloak (needed for a real boot token) and recorded the corrected 503/200 contrast in
  the docstring. Reversible in this PR (a synthetic-token variant via `write_boot_token` +
  `write_gate_marker` with no Keycloak preserves the original 502 wording — round 3 finding 1's
  "probable fix shape"; rejected because writing a token no Keycloak rotated fabricates a state
  C33 says cannot exist, and the keycloak-up pattern is proven in the qa file in both modes).
- A-02 (criterion: release-mode marker reads): assumed reading `Config.Image` of the proxy
  container is valid even while it crash-loops (`compose ps -a` shows it). This is the pattern the
  suite already proves green (`write_boot_token` reads keycloak's `Config.Image` in release mode).

## Local runs on this host (Docker Desktop 29.8.2), 2026-11-11 — synthetic names only

Release-path fidelity note: a faithful checked-images environment was stood up locally — the four
project images built once, loaded under `ekochecked-*`/`localhost/eko-crm/backend:0.1.0-ekochecked`,
and the checked-image env set for pytest exactly as the `runtime-checked` job sets it. The helper and
script fixes are therefore proven against the REAL release-mode image naming (image-not-found /
image-ls-empty), not a simulation; what this host cannot reproduce is the ubuntu bind window itself
(round-3 established Desktop answers inside it), so the restart-bind waits are proven for
correctness here and for runner timing only in CI.

- proxy_routing source-refusal: PRE-FIX RED (build): `AssertionError: the admin listener never
  became reachable behind its marker` — reproduces the both-jobs CI red on this host, proving the
  cause is the marker semantics, not the runner. POST-FIX: `1 passed`.
- carrier `len-head-7` under the checked env: PRE-FIX ERROR at the `live_boot` module fixture:
  `Unable to find image 'ekort-k04-fda6037d-proxy:latest' locally ... pull access denied` —
  the release-job ERROR's exact signature (fixture-level, all ten params, control passing).
  POST-FIX under the same env: `1 passed`; the module fixture ran its full `prepare` + real
  `run_bootstrap` — the bootstrap's open_gate marker WRITE path works under checked unchanged.
- qa pair under the checked env (open_gate + cannot_rotate): `2 passed` — cannot_rotate's reseed
  via `Config.Image` and open_gate's residual assertions on release-mode naming.
- RED PROBE of the shipped-script fix (pre-fix `docker image ls --filter {project}-proxy:latest`
  line restored, checked env, open_gate alone): -> `1 failed` at `AssertionError: the failed admin
  gate left its marker on the volume` — with the helper already fixed, the residual marker survives
  because the SCRIPT cannot resolve its removal image. This separates defect 2 from defect 1: the
  script fix is load-bearing, not the helper alone. The fixed line was then restored (byte-identical
  to the text the `2 passed` checked-env pair executed); `bash -n` clean; no `PROBE-REVERT` string
  remains in the tree; doc-check re-passed after restore.
- qa file (all five), build: `5 passed`. r21, build: `1 passed`. k02 marker-binding with the new
  closed-decision waits, build: `1 passed`. admin-privacy (invocation 30's file, unchanged),
  build: `1 passed`. carrier `len-head-7 + control`, build: `2 passed`.
- statics after every edit round: `uv run ruff check .` clean; `ruff format --check` 229 files
  formatted; `uv run mypy .` no issues; `uv run pytest -m runtime --collect-only` 447/448 collected
  (1 previous_release deselected) — import order verified (proxy_routing -> k02 -> qa is a DAG;
  the qa hub imports no test module); `bash tests/doc-checks/EKO-1-12.sh` -> 4 passed 0 failed;
  `tests/static/test_eko119_k01_mode_parity.py` -> 14 passed (the first full-suite run caught a
  literal checked-env variable name in the new docstrings — K-01's parity rule treats a naming
  line as a mode branch; reworded, no logic touched); static subsets around the touched files
  (`-k "eko112 or eko115 or eko119 or eko120 or k04_composition"`) -> 526 passed; eko119/eko120 CI
  statics -> 102 passed; FINAL full default suite (`uv run pytest -q`, everything above included,
  run after the last edit) -> `1746 passed` (448 runtime deselected), exit 0

## Discarded run results (recorded honestly)

Three runs (k02, admin privacy, carrier build subset, first attempt) died with
`scripts/keycloak-bootstrap.sh: line 4xx: ed}: command not found` — the developer edited the
bootstrap script WHILE those boots were executing it (bash re-reads the script as it runs, and the
file's byte layout changed). Self-inflicted interference, not a code or config failure; re-run
with no edits on the hot path. Recorded because the failure signature (line 73 `run_bootstrap`
`bootstrap exited 127`) could otherwise read as a real defect.

## What this change does NOT prove

- ubuntu runner behavior: every local proof here ran on Docker Desktop with locally-built images
  (plus the faithful `EKO_CHECKED_IMAGES` release path for the helper/script fixes — the local
  checked run loads the same named images but on a faster-binding host; the restart-bind race
  itself cannot reproduce on this host, per round 3's probes). The fixed first release-mode CI
  run is the judge for both the ubuntu timing family and the ceiling.
- the exact CI assertion texts of run 42897088542 (cancelled, no traceback section): the per-test
  attribution rests on the local reproduction of the identical signature (defect 1 ERROR), the
  code-path determinism of defect 2/3 (red at the same asserts in both jobs, main included), and
  the one consumer that passed while its fixture-mates errored.
- the script fix's discriminating probe (pre-fix hunk restored, checked env, open_gate red at the
  residual-marker assert) is a developer self-check, not QA's mutation under the write boundary;
  the other new waits and helper changes have had NO mutation executed here at all — removing
  `wait_for_closed_selection` under the qa2-3 entrypoint mutation, restoring the blind touch,
  restoring the build-tag resolution in `marker_value` under the checked env — all QA's job;
  the expected-failing list is in the report.
- production behavior; anything about the frontend; the `previous_release` marker.
