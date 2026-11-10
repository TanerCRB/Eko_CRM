# EKO-1-12 amended runtime stop record

Date: 2026-11-04
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the run: 6d7b1b4b3dbcecbe65efe5c83c3995150b028494 (cost-register-only advance)

## Six-role K-03 result

The test was first amended to require exactly `manage-users`, `view-users`, `query-users`, `query-groups`, `query-clients`, and `view-clients`. Against the previous five-role export, the exact-composite test failed only because `view-clients` was missing. Only `view-clients` was then added to the export.

The live six-role account could select the application client and perform account and application-role operations, so the earlier console-role stop did not recur. The amended run instead reached the excluded-role denial checks and attempted to grant `view-authorization`. Keycloak returned HTTP 204, not the required refusal. This fails K-03 and returns the authority boundary to the human. No further role was added or removed to obtain a pass.

Command:

`uv run pytest -m runtime tests/runtime/test_eko112_k03_runtime_roles_and_events.py --tb=native -q`

Observed result: `3 failed in 178.76s (0:02:58)`. The first failure was `view-authorization: 204` instead of HTTP 401/403.

The same run also reported an empty administrator application-role mapping in the reviewer test and an admin event without a representation in the event-content test. Those are unresolved secondary observations, not passes and not independent root-cause claims; work stopped at the excluded-role denial failure before investigating them.

K-04 and K-05 were not run after this stop. Reset/log privacy, D-5, reset timing, and the human distinguishability decision remain unchecked. No gate-3 proposal was produced.
