# EKO-1-12 R-05/S-03 — gate markers bound to the verified Keycloak boot — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the runs: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112` (`sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`)

## Mechanism

`open_gate` no longer records a bare `touch` marker: it asks the proxy container itself for
the running Keycloak's boot identity — `proxy/keycloak-boot-identity.sh`, the hardware address
the `keycloak` service name resolves to on the composition network (Docker assigns it per
container creation; a refused TCP attempt still completes the ARP resolution) — and records
that value as the marker's content. `proxy/entrypoint.sh` opens a listener only while a
marker exists AND names the CURRENT boot; any other state selects `Caddyfile.closed` (no
listener at all) and says so on stderr. The same-container-identity equivalence between
the proxy-side ARP view and the host-side assignment was probed before implementation on a
throwaway two-container network.

Defense under ADR-0004 C29 (2026-11-06 addendum): every boot whose markers can open a
listener is a boot `scripts/keycloak-bootstrap.sh` verified (provider selection + filtering
carrier precede every marker write in the same run). A recreation — image swap,
`up -d --build keycloak`, force-recreate, host boot with a recreated container — yields a
new identity, so a later proxy start finds the markers stale and opens nothing until a
bootstrap re-verifies. What the mechanism does NOT gate is a proxy process that keeps
running across a Keycloak recreation (no listener can be revoked from a live caddy whose
admin API is off) — recorded under "does not prove".

## Runs (green batch 2, 2026-11-08; batch summary `1 failed, 9 passed, 1 error in 3973.17s`)

`backend/tests/runtime/test_eko112_k02_marker_boot_binding.py::test_k02_markers_are_bound_to_the_current_keycloak_boot` — PASSED:
1. fresh bootstrap → both listeners serve; `/data/admin-open` and `/data/public-open` both
   carry exactly the identity the proxy observes for the current Keycloak;
2. `compose up -d --force-recreate --wait keycloak` with NO bootstrap → observed identity
   differs from the markers' value;
3. `compose restart proxy` (the R-05 reopen path) → both listeners closed at the connection
   level (transport death, not a status code);
4. `run_bootstrap` rerun (re-verifies the pair for the current boot) → both listeners open
   again, markers re-recorded with the new identity.

Red before the mechanism (pre-fix batch 1): the same test failed with
`the proxy could not observe a Keycloak boot identity after a bootstrap` (no helper in the
image, empty marker content) — the mechanism was absent, not merely unproven.

`test_qa_admin_marker_opens_only_the_admin_listener` (QA file, updated to the new primitive) —
PASSED: a blind empty `touch` leaves the admin listener connection-dead; the marker written
through the `open_gate` primitive with the current identity opens exactly the admin listener
while the auth listener stays dead; the public-without-admin guard still refuses the proxy.
Removing the entrypoint's identity comparison makes the blind-touch phase serve and kills the
test (QA mutation target).

`test_qa_open_gate_verification_stops_the_bootstrap_before_the_next_gate` — the failed-gate
marker REMOVAL (R-06) needed the crash-loop-safe fix (one-off volume mount; `compose exec`
cannot reach a crash-looping container): first observed failing on the pre-fix removal path
(`the failed admin gate left its marker on the volume`, the marker value was the correctly
bound identity), re-run with the one-off volume-mount removal: PASSED in the green batch 3 rerun (`2 failed, 2 passed in 848.83s` — the two passes being this contrast and the live offline-scope test; the two failures were the restore/expiry harness bugs fixed since).

## Limits

Local composition only. The identity is not a secret (a MAC address), carries no user data,
and is never logged. The binding proves the listener boundary for composition bring-ups on
this host; it is not a host-control or production mechanism (an operator with host control
can always do what Docker itself allows; exception EKO-1-03/B-02 already covers the
host-control tier).
