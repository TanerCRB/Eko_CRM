# EKO-1-12 local bootstrap record

Date: 2026-11-04
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the record: e8428f4f2274260ecb7e6d4f50a4bba09eaeb190 (cost-register-only advances)

Scope: synthetic local development compositions only. This does not prove production listeners, interfaces, certificates, timing, or availability.

## Fresh composition and rerun

Command: `uv run pytest -m runtime tests/runtime/test_eko112_k02_bootstrap_order.py::test_k02_fresh_bootstrap_order_and_existing_volume_rerun -q`

Observed result: `1 passed in 154.76s (0:02:34)`. The test observed this order against the running composition:

1. Live master bruteForceProtected true before the admin gate was opened.
2. admin listener open and reachable.
3. application realm import complete through `kcadm.sh`.
4. Live application bruteForceProtected true before the public gate was opened.
5. public listener open and reachable.

The second invocation against the same volumes began with both gates closed and repeated the live checks. rerun existing volume live checks completed; prior import state was not accepted as the current run's evidence.

## Independent closed-listener contrasts

- master contrast with `EKO112_MASTER_BRUTE_FORCE=false`: bootstrap exited 3 and the admin listener closed; with the precondition restored, the master contrast and both listeners passed. Final command: `uv run pytest -m runtime tests/runtime/test_eko112_k02_bootstrap_order.py::test_k02_master_precondition_contrast_keeps_only_admin_listener_closed -q`; observed `1 passed in 164.14s (0:02:44)`.
- application contrast with import incomplete: bootstrap exited 4 and the public listener closed while the admin listener remained open.
- application contrast with brute force false: bootstrap exited 5 and the public listener closed while the admin listener remained open. The two application contrasts passed in the collected run `1 failed, 2 passed, 1 deselected in 669.44s (0:11:09)`; the one failure was the separate master rerun issue corrected above.

No volume or state outside the test-owned fresh compositions was deleted to obtain these results.
