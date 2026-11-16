# EKO-1-12 privacy stop record

Date: 2026-11-04
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the run: c71a3c77ae948f7ffd38dc5550d93aaa6acf84bc

## K-04 result

The real local composition completed the reset response/mail checks, disabled-account refusal, successful PKCE login, token refresh, failed-login probes, and logout. Stored-event inspection then found the exact session identifier decoded from the issued access token in the stored events.

Command:

`uv run pytest -m runtime tests/runtime/test_eko112_k04_reset_and_log_privacy.py --tb=native -q`

Observed result: `1 failed in 209.71s (0:03:29)` with `stored events contains forbidden value class: session-id`.

This violates ADR-0005-C5. No accepted configuration change or exception covers it. No provider, image, event type, or logging rule was changed in response. The task returns to the human before another mechanism or scope decision.

The session-identifier assertion runs before the unknown-marker scan in the current test. Therefore the D-5 marker result is unchecked, not passed and not alleged to have leaked. K-05 timing was not run after this stop; no timing record or human distinguishability finding was invented.

One earlier attempt failed before Keycloak because Docker could not reach `ghcr.io`; the unchanged command was rerun successfully into the composition. That network failure is not treated as privacy evidence.
