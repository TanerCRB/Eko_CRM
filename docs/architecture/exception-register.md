# Exception register

Holds every **recorded exception** that outlived the pull request it was accepted in:
a finding the human let through gate 2 on purpose, with an owner and a date after which it
blocks again (`TEAM-CONTRACT.md`, §3a). Without this file, an exception lives
only in a merged PR description, and nobody reads that again once the date passes.

Rules:

- **One exception per line, in the §3a format** — `scripts/exception-check.sh` reads this file,
  and a line in any other shape counts as no exception at all.
- An entry arrives through the gate-3 documentation PR, like every other register entry. It leaves
  through the gate-3 documentation PR of the task that fixed the finding. A renewal — a new date
  and a new reason — is the human's own edit, in a PR they merge.
- An agent never changes a date here. An expired entry is reported, not repaired.

Check:

```bash
bash scripts/exception-check.sh docs/architecture/exception-register.md
```

## Exceptions

Accepted at gate 2 of EKO-1-01 in [PR #30](https://github.com/TanerCRB/Eko_CRM/pull/30); fixed
by #29:

- Exception EKO-1-01/EC-K-01 — owner: @TanerCRB — reason: the K-01 document check is a QA scratch script, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-02 — owner: @TanerCRB — reason: the K-02 document check is a QA scratch script, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-03 — owner: @TanerCRB — reason: the K-03 document check is a QA scratch script, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-04 — owner: @TanerCRB — reason: the K-04 document checks are QA scratch scripts, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-05 — owner: @TanerCRB — reason: the K-05 document checks are QA scratch scripts, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-06 — owner: @TanerCRB — reason: the K-06 document checks are QA scratch scripts, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
- Exception EKO-1-01/EC-K-07 — owner: @TanerCRB — reason: the K-07 document check is a QA scratch script, not a tracked test file (K-07 forbids adding files; follow-up #29) — blocks again: 2026-11-23
