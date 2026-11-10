# EKO-1-12 typed-username D-5 stop record

Date: 2026-11-05
Baseline SHA: 5724a6de92462e0e1e9fe3b1981b2ad1d4f151ba
Worktree HEAD at the run: c931cc8d0eebce9a32978307503f269fd1397162

## Independent D-5 result

Command executed against the real local composition:

`uv run pytest -m runtime tests/runtime/test_eko112_k04_unknown_username_d5.py --tb=native -q`

Observed result: `1 failed in 221.33s (0:03:41)` with the mandatory `D-5 STOP`: the official Keycloak image retained an unknown typed username in Keycloak logs or stored events. The independently executed known-account contrast retained its username in a login-error event, proving that the event inspection was non-empty and could find a username where storage is permitted.

This is a confirmed typed-username D-5 stop, not a failure of the earlier top-level `sessionId` assertion and not evidence that the accepted local-only sessionId addendum has passed. The D-5 test has its own file and result, so the earlier session assertion cannot hide or skip it.

No marker value, credential, token, log line, representation, or personal data is included in this record. No provider, image, required event type, configuration, or locked criterion was changed in response.

## Unchecked work

- K-02 final-configuration runtime revalidation is unchecked.
- K-03 final-SHA reviewer/event revalidation is unchecked.
- The amended top-level sessionId K-04 checks were not completed after this D-5 stop.
- K-05 reset timing in both orders, its measurements, mail outcomes, and human distinguishability decision are unchecked.
- Final-SHA K-02 verification and the K-07 gate-3 proposal were not produced.

The next step must return to the human/Architect for an ADR-0005 decision before any provider, image, or required-event-type change. No implementation workaround is authorized.
