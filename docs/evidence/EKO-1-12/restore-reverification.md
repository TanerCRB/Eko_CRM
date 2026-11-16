# EKO-1-12 K-02 item 5 — restore-boundary reverification record — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112` (`sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`)

## Scenario (committed test)

`backend/tests/runtime/test_eko112_k02_restore_reverification.py` on its own throwaway
composition:

1. fresh bootstrap (accepted order, provider pair before the first listener);
2. the documented on-demand backup (`backup/README.md` command, `compose run --rm --no-deps
   backup eko-backup run`) into the destination double — exactly one new complete set;
3. damage inside the test's own composition only: `compose stop keycloak`, `DROP DATABASE
   keycloak`, then the restore side of the accepted path — `pg_restore --create --exit-on-error`
   of the set's `keycloak` dump (EKO-1-14 machinery; no volume deletion; the application
   database and the proxy-data volume are left in place);
4. `scripts/keycloak-bootstrap.sh` rerun (the existing-volume path: `master-initialized`
   survives in `proxy-data`): the recorded order —
   `master bruteForceProtected true` → `custom provider selected` → `filtering verified` →
   `admin listener open` → `application realm import complete` → `application
   bruteForceProtected true` → `public listener open` → `rerun existing volume live checks
   complete` — and both listeners open only after the pair;
5. read-back through the restored store: the eko realm exists, the bootstrap administrator
   is present, the event store answers;
6. the R-04 unknown — break-glass password divergence — OBSERVED (see below).

## Observed (green batch 5, 2026-11-08: the test PASSED inside
`1 failed, 1 passed in 376.98s`; the failure was the co-run expiry harness issue,
recorded separately)

- rerun across the restore: exit 0; the recorded event positions satisfy
  `custom provider selected < filtering verified < admin listener open < public listener open`
  (the assertion the test enforces), the rerun line `rerun existing volume live checks` is
  present, both listeners open only after the pair, and the restored store reads back the
  eko realm, the bootstrap administrator account (exactly one match) and a well-formed
  authentication-event list;
- divergence branch (only the environment file's `EKO112_BREAKGLASS_ONE_PASSWORD` rotated;
  the restored database keeps the dumped value): the rerun exited 1; its evidence file —
  absent or empty is the observed shape, because the run dies at `run_mode master` before
  any accepted-state event is recorded — contains neither listener-open line; BOTH listeners
  stayed closed at the connection level (transport death, the QA gate probe's rule); the
  matching-environment rerun reopened both gates — a fail-closed disagreement, not a
  permanent lock. This is the R-04 unknown now OBSERVED, not reasoned: the rerun path
  authenticates from the environment against the restored database, and any divergence
  keeps every listener closed rather than serving unverified state.
- No unfiltered event path was active during any of it: the same `filtering verified`
  carrier check (built-in fallback fails the run — `provider-verification-contrast.md`)
  ran before every listener open in this scenario too.

## Limits

Local composition, local restore boundary, synthetic accounts only; the EKO-1-14 backup
format/destination rules are proven there, not here; no production restore claim. The
rotation direction tested here is environment-versus-database; the opposite direction
(newer database, older environment) takes the same authentication path and therefore the
same fail-closed branch.
