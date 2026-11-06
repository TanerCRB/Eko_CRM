# EKO-1-12 reset-timing record

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Machine-readable companion: reset-timing.json (same run)

Local development composition and mail catcher only; nothing here is a production claim.
Both requests returned HTTP 200 with identical page text for every request in the series
(asserted by `backend/tests/runtime/test_eko112_k05_reset_timing.py`). Addresses are the
declared synthetic fixtures; no real personal data and no identifier values appear here.

## Measured wall-clock request times (milliseconds, local composition)

- known address (existing synthetic account) — known_ms: [34.356, 30.126, 26.296, 30.117]
- unknown address — unknown_ms: [19.759, 21.553, 21.563, 31.4]

## Observed mail-side effects

- known address: every request delivered exactly one message (known mail messages per
  request: [1, 1, 1, 1]) — 1 message delivered per known-address request
- unknown address: zero messages (unknown mail messages per request: [0, 0, 0, 0]) — no
  message for any unknown-address request

## Reading of the observation (facts only)

On this local composition the raw response status and text were identical across the
address cases, while the measured timings overlapped (the unknown-address series was
numerically lower in three of four pairs) and the mail catcher observably distinguished the
address cases (one message versus none). Whether an attacker could turn these local
observations into reliable account existence knowledge under production deployment, mail
routing, and load is not decidable from this record.

Human distinguishability finding: UNDECIDABLE — returned to the human, per the task's stop
rule; the timing test records the numbers and the mail deltas only, and the status/text
equality is the automated assertion.
