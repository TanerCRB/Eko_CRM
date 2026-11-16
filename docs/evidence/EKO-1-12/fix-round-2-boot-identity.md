# EKO-1-12 fix round 2 — boot-identity correction (per-boot token replaces the ARP binding) — 2026-11-10

Date: 2026-11-10
Baseline SHA: 9927d7d (main at the correction branch's cut; the accepted addenda are carried at worktree HEAD f32f27a)
Worktree HEAD at the runs: f32f27a (dirty worktree: this fix round's uncommitted implementation; PR #122 content — `scripts/keycloak-bootstrap.sh` and six reformatted test files — imported as the editing base, not merged here)
Refs: Issue #126 (refs #53 / #121); ADR-0004 addendum of 2026-11-10 (new control C33) and the dated numbering correction of the same date (C34)
Answers (does not edit): `marker-boot-binding.md` — its dated record stands as the observation of the withdrawn ARP primitive.

## Mechanism (what replaced what)

The marker's boot binding is no longer read from the network. The Keycloak entrypoint wrapper
in `compose.yaml` now, as the FIRST act of every container start (before the empty-password
refusal, before `exec kc.sh`), reads `/proc/sys/kernel/random/uuid`, writes it to
`/etc/eko/keycloak-boot/token.tmp.$$` and renames it atomically over
`/etc/eko/keycloak-boot/token`; a start that cannot rotate prints
`configuration error: the Keycloak boot token could not be rotated; refusing to start` and
exits non-zero — a loud, fail-closed refusal, never a silent unrotated boot. The token lives
in the new named volume `keycloak-boot`, mounted rw in `keycloak` and read-only in `proxy` at
the same path — the composition's only addition, per the declared deviation accepted with the
addendum (ADR-0004-C4 as amended). `open_gate` records the file's content read through the
proxy's own helper; `proxy/keycloak-boot-identity.sh` is now the same pure file read (`-s`
check, UUID-shape validation — lower-case hex, exact 8-4-4-4-12 segments — then print;
missing/empty/malformed exits 1 with empty stdout). No getent, wget, ARP, retry loop or sleep
remains in either observation path, and the bootstrap's marker-write guard accepts only the
UUID alphabet. Boot means every Keycloak container start (C33): a restart, recreation, image
swap, restore bring-up or host reboot invalidates prior markers before any later proxy start
consults them.

## Carrier seeding — the ownership proof the addendum left unverified

Both `identity/Dockerfile` and `proxy/Dockerfile` create `/etc/eko/keycloak-boot` (dir 755,
owner uid/gid 1000) containing the byte-identical placeholder `/etc/eko/keycloak-boot/.seed`
(644), so whichever container first attaches the empty named volume leaves the directory
owned by uid 1000 — Keycloak's user — and the placeholder exists in every seeding. The
identity image seeds under a `USER root` run followed by `USER keycloak`, keeping the image's
runtime user unchanged (uid 1000, verified `id` after the rebuild).

Standalone daemon-semantics probe on this host (same pinned Caddy digest, a seed-layer probe
image, a throwaway named volume; artifacts removed the same day):

- volume first attached by a seeded image at uid 1000: `ls -ldn` showed
  `drwxr-xr-x 2 1000 1000 … /etc/eko/keycloak-boot` and `-rw-r--r-- 1 1000 1000 … .seed` —
  the daemon copied the source directory's ownership onto the volume root, and a uid-1000
  process created a file in it (`WRITABLE-BY-UID-1000`);
- a second, DIFFERENT image attaching the already-initialized volume saw the first image's
  content unchanged (`seed`, same 1000:1000 modes) — first attach wins, as designed.

Real-composition observations:

- keycloak image rebuild, seed layer inspected (2026-11-10): `drwxr-xr-x 1000 1000 4096
  /etc/eko/keycloak-boot`, `-rw-r--r-- 1000 1000 115 /etc/eko/keycloak-boot/.seed`, runtime
  `uid=1000(keycloak) gid=0(root)`;
- proxy-first (the `prepare` bring-up order — the proxy image initializes the empty volume,
  then Keycloak's first start must rotate into that directory): proven by every full
  bootstrap this round, explicitly by `test_k02_markers_are_bound_to_the_current_keycloak_boot`
  (2026-11-10, `1 passed in 1129.82s`): prepare brings up the proxy without Keycloak, the
  bootstrap recreates Keycloak, the wrapper rotates on the proxy-seeded volume root,
  `open_gate` reads the token through the proxy and both listeners serve — a root-owned
  volume root would have died at the rotation refusal instead;
- keycloak-first (`up -d --wait keycloak` with the proxy out of the bring-up): PASSED in
  `test_qa_boot_carrier_seeds_keycloak_writable_ownership_in_either_attach_order`
  (2026-11-10, file `1190.43s` total): volume root observed `stat -c '%u %g %a'` =
  `1000 1000 755` INSIDE the Keycloak container (the identity image seeded the empty volume
  first), the wrapper's rotated token is a full lowercase UUID read back from
  `/etc/eko/keycloak-boot/token`, the `.seed` placeholder is present and not UUID-shaped, and
  the proxy — attaching the already-initialized volume read-only afterwards — observes the
  SAME token through the shipped helper. The daemon copied the seeding directory's ownership
  onto the volume root in both attach orders; the ownership claim is now runtime-observed,
  not assumed.

## Docker Desktop observation that qualifies the withdrawn primitive's failure model

Probe of the OLD (ARP) primitive on this host, throwaway project, same day: a
same-container `docker compose restart keycloak` REASSIGNED the container's hardware address
(`ea:51:61:6c:ca:89` → `1e:b0:6e:67:a0:3a`, container id unchanged — Docker Desktop
regenerates the veth-side MAC per start), and the helper run from a fresh one-off container
on the project network printed NOTHING (empty stdout) before and for 90 s after a restart.
Consequences, stated honestly:

- the new K-02 restart-closes phase could NOT be observed red under the old primitive on
  this host (the restart did rotate the observable here) — it measured green under ARP
  (`1 passed`, 2026-11-10 10:58→11:26); the hole the phase closes is the one the accepted
  addendum and Issue #126 record for the CI ubuntu runners, where restart keeps the
  creation-keyed MAC and a verified boot's listeners survive a re-verified-restart;
- the empty-read behavior reproduced here is the mis-observation class itself;
- the token primitive removes the host-dependence entirely: rotation is the container's own
  act, identical on every host, and restart-closes holds by construction — verified by the
  marker run above.

## Red before the configuration (observed verbatim)

- `bash scripts/keycloak-bootstrap.sh --self-test` with the UUID cases in place and the old
  `[0-9a-f:]` guard in `open_gate` (2026-11-10, before the config batch):
  `FAIL a hardware-address boot identity is refused before the marker write — status 'rc=0 marker_writes=1 evil=absent', gate stderr:`
  and
  `FAIL a valid UUID boot identity is accepted and reaches the marker write — status 'rc=1 marker_writes=0 evil=absent', gate stderr: keycloak-bootstrap: unusable Keycloak boot identity for the admin gate`
  (+ the scratch-recursion case reporting the nested exit-1) — `Self-test: 9 cases ran, 6 passed, 3 failed.`
  After the guard moved to the UUID alphabet: `Self-test: 9 cases ran, 9 passed, 0 failed.`
- static volume-set checks against the two-volume composition (2026-11-10, full-suite tail):
  `FAILED tests/static/test_eko112_k01_custom_provider_image.py::test_k01_compose_uses_custom_image_without_adding_state_or_services`
  (verbatim assertion tail: `Left contains one more item: "named volumes ['pgdata', 'proxy-data']"`
  on the amended-C4 check), plus `test_k04_composition.py::test_k04_c4_state_only_in_the_three_named_volumes[dev]`
  and `[shared]`. After the configuration: full `tests/static` run exit 0 (green).
- a fourth named volume cannot fail the RENDERED check (a single-file mutation cannot
  produce it: compose drops an unused top-level declaration, and mounting an undeclared
  volume fails the render) — the superset half of the amendment is pinned on the unrendered
  source set (`compose_source["volumes"] == {pgdata, proxy-data, keycloak-boot}`), noted in
  the test comment; the vacuous rendered-case attempt was removed before handoff (it was
  this round's own addition, never a shipped assertion).
- the same run's five `FAILED …timeout…/byte-identical` lines (`test_eko120_qa_a_retuned_timeout_line_is_not_a_changed_job`,
  4 ids, + `test_eko119_k03_every_existing_ci_job_is_byte_identical`) were the ci.yml shape
  defect this round's own edit caused — the carrier masks only the timeout line and the ONE
  comment line directly above it. Fixed by collapsing each dated comment to a single line
  (the carriers were NOT adapted); rerun: `102 passed in 37.28s`. Load-bearing pairing the
  Architect names: the ceiling raise rides with the determinism fix.
- runtime restart-closes phase: not locally observable as red (see the probe section); green
  under both primitives here; CI (ubuntu runners) is the first place the old primitive
  cannot pass it.

## Green runs (local composition, synthetic values only, this correction)

- `bash scripts/keycloak-bootstrap.sh --self-test` → `9 cases ran, 9 passed, 0 failed`
- `bash tests/doc-checks/EKO-1-12.sh` → `4 passed, 0 failed`
- `uv run pytest tests/static -q` → `1570 passed in 2908.12s (0:48:28)` on the final tree
  (after the ci.yml comment collapse and the fourth-volume-case removal; earlier
  before/after states in the red section)
- `uv run ruff check .` / `ruff format --check .` / `mypy .` (backend) → all clean;
  `node tools/check-links.mjs` → clean (131 links, 0 broken)
- `test_eko112_k04_admin_listener_log_privacy.py` STANDALONE cold ×2 (the CI-defect
  reproduction pair, previously red on CI):
  `1 passed in 429.67s` and `1 passed in 507.84s`
- `test_eko112_k02_marker_boot_binding.py` (incl. the new same-container restart-closes
  phase): `1 passed in 1129.82s`
- `test_eko112_qa_fail_closed_proxy_gate.py` (5 tests, incl. the rotation-dies carrier and
  the keycloak-first seeding carrier): `5 passed in 1190.43s` — per test:
  `test_qa_both_listeners_are_closed_without_the_bootstrap PASSED`,
  `test_qa_admin_marker_opens_only_the_admin_listener PASSED`,
  `test_qa_open_gate_verification_stops_the_bootstrap_before_the_next_gate PASSED`,
  `test_qa_keycloak_start_that_cannot_rotate_the_token_dies_loudly PASSED`,
  `test_qa_boot_carrier_seeds_keycloak_writable_ownership_in_either_attach_order PASSED`
- `test_eko112_r21_public_gate_residual_state.py` — reported green by the driving session
  (1 passed) but no developer-session artifact of the corrected tree was observable in this
  round's log directory at report time: UNVERIFIED-HERE, confirm at gate 2.
- `test_eko112_k02_bootstrap_order.py` (full K-02 order) — same status: driver-reported
  green, no developer-session artifact observed: UNVERIFIED-HERE, confirm at gate 2.
- remaining eko112 runtime set (k03, k04 reset/expiry, d5, k05) + full default
  `uv run pytest -q` — same status: driver-reported green (default 1739 matching baseline
  count), no developer-session artifact observed: UNVERIFIED-HERE, confirm at gate 2.

## Limits / what this record does not prove

- Local Docker Desktop only; no production claim. CI green on both runtime jobs at this
  correction's final SHA is the remaining gate-2 evidence — the first real run of the new
  primitive on ubuntu runners (where the ARP observation failed), at the 110-minute ceiling;
  the release-mode (checked-images) job is the first real run of this composition shape.
- The token is a drift detector, not authentication (EKO-1-03/B-02 tier unchanged); forging
  it needs container-tier access on the host — recorded, not defended.
- The addendum's own limits carry over: a live caddy is not revocable; a cold bring-up where
  the proxy reads before the current Keycloak start has rotated can momentarily name the
  previous boot (same recorded class); a stale marker while Keycloak is fully stopped opens
  listeners against a dead upstream (C33 binds identity, not liveness — the healthcheck's
  job). The rotation-refusal carrier shows a start that cannot rotate never reaches serving;
  it does not gate those cases.
- Mutation re-execution at the final SHA (identity comparison removed; rotation skipped;
  guard charset widened) is QA's per EKO-1-12's own contrast rule; the new carriers name the
  expected color changes.
