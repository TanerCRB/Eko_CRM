# EKO-1-28 mutation rounds — 2026-11-12

Date: 2026-11-12. Baseline SHA: `3b93d1e0f2df8a35ac393282099c965ae2a84714`. Worktree:
`E:\GitHub\Eko_CRM-EKO-1-28` (branch `EKO-1-28-reclose-guard`). Mutations were applied
in-tree to `scripts/keycloak-bootstrap.sh`, exercised against the committed runtime test
`backend/tests/runtime/test_eko128_reclose_failed_branch.py` and the script's own
`--self-test` (offline corroboration), then reverted by re-editing the exact hunk. No
restore-from-copy was used at any point; each revert is checked byte-for-byte against the
shipped-form witness recorded before the mutation rounds. Synthetic values only. Local
evidence: it shows the committed guard is not empty on this machine; it is not the CI-run
evidence K-04 also names (that arrives with this task's PR runtime jobs).

## Shape history (disclosed)

The hook was implemented twice during the task. Shape v1 (`120 2` against HEAD) folded the
guard into the re-close condition line (`[ -z ... ] && compose restart proxy`). A driver
notice mid-cycle bound the resting tree to a PURE ADDITION over HEAD (deletions == 0), so
v1 was reworked to shape v2: the shipped `if/else/fi/return 1` lines are untouched and the
knob, consulted only inside the failure tail after the marker removal, replaces `compose`
for the single later `restart proxy` call (any other call is refused loudly). v1's matrix,
guards and mutation reds are therefore INTERMEDIATE; the canonical evidence below is the
v2 set, and the final green session (matrix + guards) reruns on the v2 resting tree.
Witnesses: v1 `6f85645e4f936bf04b53a489a629ab93935c36f8674debb858026470ad96fa3e`,
v2 `ea9a8a168208e2f8a6374d468307ebcdb6ce3fcbdffb7b7fe687a000a7a752e7`
(`git diff HEAD --numstat`: v1 `120 2`, v2 `133 0`).

## Pre-hook red (test-first, on the untouched HEAD script)

- `test_eko128_hook_set_records_the_reclose_failure_and_exits_one` — FAILED, 1 failed in
  752.13s. Reason (missing behavior, not environment): the scenario's single failure record
  carried the shipped success tail ("marker removed; admin listener remains open") and not
  the re-close clause — `AssertionError: the re-close-failure branch did not record its
  clause: {...,"event":"public verification failed; marker removed; admin listener remains
  open"}`. Exit 1, exactly-one-failure-line, marker-absence and no-"public listener open"
  all passed against the pre-hook script.

## Mutation rounds — shape v2 (shipped)

| # | Mutation (exact hunk) | Offline `--self-test` | Committed runtime test | Revert |
|---|---|---|---|---|
| a | re-close-failed `record` call replaced by `:` stub | `13 cases ran, 10 passed, 3 failed` — both refusal-record cases FAIL with `event=` (empty), nested scratch FAILs | `test_eko128_hook_set_records_the_reclose_failure_and_exits_one` FAILED — `AssertionError: expected exactly one failure record line` (zero failure lines; recorded events end at "application bruteForceProtected true") — 1 failed in 999.08s (982.05s call) | re-edit restored; sha256 == `ea9a8a16…`, `grep -c MUTATION` = 0 |
| b | re-close branch's `return 1` deleted | `13 cases ran, 8 passed, 5 failed` — all four reclose cases FAIL with `rc=0`, nested scratch FAILs | `test_eko128_hook_set_records_the_reclose_failure_and_exits_one` FAILED — `AssertionError: bootstrap exited 2, expected 1` (after the tail swallowed the failure, the still-active hook replacement refused the later cleanup compose call — an exit-assertion red either way) — 1 failed in 921.91s (899.10s call) | re-edit restored; sha256 == `ea9a8a16…` |
| c | guard default flipped: `${EKO128_FORCE_RECLOSE_FAIL:-fail}` (activation when unset) | `13 cases ran, 9 passed, 4 failed` — the two shipped-state cases (unset, empty-string) FAIL with the refusal record, the failing-restart case drops to `restarts=1`, nested scratch FAILs | `test_eko128_hook_unset_records_the_success_path_tail` FAILED — `AssertionError: the unset hook changed the shipped residual record: {...,"event":"public verification failed; marker removed; proxy re-close failed; listeners not confirmed closed"}` — 1 failed in 935.10s (921.03s call) | re-edit restored; sha256 == `ea9a8a16…`, `grep -c MUTATION` = 0, `git diff HEAD --numstat` == `133 0`; self-test back to `13 cases ran, 13 passed, 0 failed` |

## Superseded shape-v1 observations (same mutations, same target lines)

| # | Committed runtime test | Result |
|---|---|---|
| a | `...hook_set_records_the_reclose_failure_and_exits_one` | FAILED — `expected exactly one failure record line` — 1 failed in 1189.20s (1150.77s call) |
| b | same test | FAILED — `bootstrap exited 0, expected 1` — 914.10s call (v1 had no loud compose guard; the run completed green-looking) |

Both shapes turned the same committed assertion red with the same one-line reason; the v2
runs are the ones that count for the shipped artifact.

## Final reverification on the resting tree

See `runs-2026-11-12.md` (shape-v2 green matrix of all four `test_eko128_*` cases and the
two pre-existing guards, run after the last revert).
