# EKO-1-12 non-LOGIN session-path stop record

Date: 2026-11-05
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the run: 99153f674ba623fc303640bc2a9cf08d7544142e

## Result

The accepted same-event duplicate `LOGIN details.code_id == sessionId` check was implemented with non-empty evidence and explicit mismatch/missing-counterpart mutations. The real application-realm event inspection then found `details.code_id` on a non-LOGIN event, which remains outside all three accepted local exceptions.

The earlier safe failure projection had identified a `RESET_PASSWORD_ERROR details.code_id` match. The amended structural assertion rejects that event type rather than permitting it through the LOGIN-only exception.

Command:

`uv run pytest -m runtime tests/runtime/test_eko112_k04_reset_and_log_privacy.py --tb=native -q`

Observed result: `1 failed, 1 passed in 310.34s (0:05:10)`. The passing test was the mismatch/missing-counterpart mutation set. The real-runtime failure was `session identifier at non-excepted application:details.code_id` for a non-LOGIN event.

No identifier value, marker, credential, token, cookie, raw event, raw log or personal data is included here. No exception was widened and no required event type, realm, listener, provider, image, log-level or credential configuration was changed.

## Unchecked work

Independent D-5 remains separately implemented and previously green; it was not rerun in this stopped invocation. Fresh K-02/K-03, remaining K-04 event coverage, K-05 both-order timing and mail outcomes, the human distinguishability decision, QA evaluation and the K-07 gate-3 proposal remain unchecked. No timing result or gate-3 artifact was invented.
