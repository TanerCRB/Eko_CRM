# EKO-1-12 K-02 live bootstrap record

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the runs: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa (dirty worktree: this invocation's uncommitted implementation)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112` (`sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`),
built per `custom-image-build.md`. The prior record on the official image is kept renamed as
`bootstrap-official-image-2026-11-04-superseded.md`; it does not carry forward.

## What proves the order

`backend/tests/runtime/test_eko112_k02_bootstrap_order.py` drives the real composition
(`scripts/keycloak-bootstrap.sh` against the actual `compose.yaml`) on fresh volumes and records
every accepted-state event to the run's evidence file. The recorded sequence asserted by the
test on this run (all four tests passed, 13:18 total, 2026-11-06):

Live master bruteForceProtected true, then the two provider checks —
`custom provider selected` (the running server's own log names
`org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory` for the internal `eventsStore`
SPI) and `filtering verified` (a live master-realm carrier event is stored with its `username`
detail and without any `code_id` detail) — then admin listener open, then the
application realm import complete, then Live application bruteForceProtected true, then public
listener open. Both listener opens therefore follow the provider-verification pair, and the
admin listener still precedes the application-realm import and its brute-force check.
The provider pair itself is decisive rather than vacuous: the same carrier stores a `code_id`
against the built-in `jpa` factory (red), which is when both listeners stay closed — see
`provider-verification-contrast.md`.

## Restart and contrasts (all observed on this run, exit codes asserted by the tests)

- A rerun against the existing volume replays the live checks without recreating accounts
  (rerun with existing volume keeps all live checks green): the rerun evidence file carries a
  second `rerun existing volume live checks complete` line and re-records
  `custom provider selected` and `filtering verified` before reopening the listeners.
- master-realm precondition contrast (`EKO112_MASTER_BRUTE_FORCE=false`, read live): the
  bootstrap fails closed (exit 3) and the master contrast keeps the admin listener closed as
  well as the public listener.
- application-import contrast (`EKO112_APPLICATION_IMPORT=false`): bootstrap fails closed
  (exit 4); the application contrast keeps the public listener closed while the admin listener,
  opened earlier in the accepted order, stays open; restoring the condition and rerunning opens
  both listeners.
- application-brute-force contrast (`EKO112_APPLICATION_BRUTE_FORCE=false`, read live from the
  realm representation): bootstrap fails closed (exit 5); the same application contrast holds —
  public listener closed — and the restoring rerun completes the accepted sequence.

## Machine-readable events

Each accepted step is appended as a JSON line to the run's evidence file
(`scripts/keycloak-bootstrap.sh` `record`), including `Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa`
in every event, the custom-provider pair, the live `bruteForceProtected` confirmations, and both
listener opens. The test asserts the event order, the exit codes above, and the listener states
through the proxy only; the Keycloak ports stay unpublished in `compose.yaml`.

## Restoration of the selected provider

When the unverified provider state is restored (the accepted custom image back in place, the
conditions true), the rerun emits the full accepted sequence and both listeners open — the
contrast failures are the mechanism failing closed, not a permanent lock.

## Limits

Local composition only; no production claim. The records name synthetic accounts and boolean
states — no credential, identifier value, raw log, or raw event appears here. QA's for-QA list
additionally mutates the versioned provider artifact (registration removed, factory order lowered)
and rebuilds; that mutation pair belongs to gate-2 QA, and the built-in fallback variant of the
same contrast is recorded in `provider-verification-contrast.md`.
