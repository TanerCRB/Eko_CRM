# EKO-1-12 non-excepted session-path stop record

Date: 2026-11-05
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the run: d965f8d6f39694091618d03e29bd7c1b04729963

## Result

The amended K-04 check used the exact issued user-session identifier and recursive field-path inspection. It found accepted top-level `sessionId` occurrences on required LOGIN and LOGOUT events, but also found the same value at `LOGIN details.code_id`. That path is outside both accepted local exceptions and remains prohibited as authentication-session material.

Command:

`uv run pytest -m runtime tests/runtime/test_eko112_k04_reset_and_log_privacy.py --tb=native -q`

Observed result: `1 failed in 195.36s (0:03:15)` with `session identifier at non-excepted application:details.code_id`.

This is distinct from the accepted top-level sessionId exception and from the independently accepted/executed D-5 unknown-username path. Neither exception was widened, and no required event type, provider, image, realm, listener, log-level or credential configuration was changed.

No identifier value, marker, credential, token, cookie, raw event, raw log or personal data is included in this record.

## Independent D-5 and unchecked work

The field-path-aware independent D-5 test passed before this failure: `1 passed in 148.73s (0:02:28)`. It permits only application-realm `LOGIN_ERROR details.username`, retains the known-account contrast and rejects log/other-path matches.

The non-excepted session-path failure stops further runtime work. Final-configuration K-02/K-03 reruns, remaining K-04 event coverage, K-05 both-order timing and mail outcomes, the human distinguishability decision, and the K-07 gate-3 proposal remain unchecked. No timing conclusion or gate-3 artifact was invented.
