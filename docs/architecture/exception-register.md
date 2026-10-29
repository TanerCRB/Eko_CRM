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

Accepted at gate 2 of EKO-1-03 in [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39); fixes are
entry conditions of EKO-1-08 (#36) and, for R-22, EKO-1-12 (#53):

- Exception EKO-1-03/F-01 — owner: @TanerCRB — reason: port 80 also serves the ACME challenge path, a consequence of the accepted ACME auto-renewal (C-6), accepted 2026-10-24 — blocks again: 2027-03-31
- Exception EKO-1-03/B-02 — owner: @TanerCRB — reason: a break-glass holder with Docker or PostgreSQL superuser rights can clear master-realm and application-realm events stored only on the server, accepted 2026-10-24; ADR-0005 (EKO-1-04, #17) closes it for events already shipped once EKO-1-09 (#41) ships them, and the residual case stays open: such a holder can suppress or alter events before they are shipped, checked by the reviewer against each announced break-glass use — blocks again: 2027-03-31
- Exception EKO-1-03/B-05 — owner: @TanerCRB — reason: a server-root attacker can write backup sets that pass the monthly verification because the application dump is checked only against itself; a check against a fact from outside the server is an entry condition of EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/B-10 — owner: @TanerCRB — reason: a restore leaves the backup private key, destination read access and the decrypted set on the restored server; their removal at step 14, checked in C25, is an entry condition of EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-16 — owner: @TanerCRB — reason: a restore onto empty volumes has no certificate for the public names while the company-only public listener blocks ACME; settled before the first tested restore in EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-17 — owner: @TanerCRB — reason: a repeat restore test beside live production writes into production's backup destination; a test-restore rule is an entry condition of EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-18 — owner: @TanerCRB — reason: restore step 2 forces the release that was rolled back after the backup; corrected in EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-19 — owner: @TanerCRB — reason: an entered but not yet performed approval fails the monthly record comparison; corrected in EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-20 — owner: @TanerCRB — reason: restore step 10 names the console, which only regenerates the client secret, instead of the admin REST API; corrected in EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-21 — owner: @TanerCRB — reason: restore step 9 says "the previous value" where two rotations since the backup need the value in effect at the backup's time; corrected in EKO-1-08 (#36) — blocks again: 2027-03-31
- Exception EKO-1-03/R-22 — owner: @TanerCRB — reason: bootstrap opens the public listener before the application realm import and the C8 check; corrected in EKO-1-12 (#53), moved from EKO-1-06 (#19) at its gate 1 — blocks again: 2027-03-31

Accepted at gate 2 of EKO-1-04 in [PR #44](https://github.com/TanerCRB/Eko_CRM/pull/44); fixed by
an ADR-0005 addendum tracked in #43:

- Exception EKO-1-04/R-17 — owner: @TanerCRB — reason: an erasure withdrawn while its run is in flight is carried out and its entry marked completed with no report to the human; fixed by an ADR-0005 addendum tracked in #43 — blocks again: 2027-03-31
- Exception EKO-1-04/R-18 — owner: @TanerCRB — reason: a report carrying only the identifier and the entry reference cannot name its condition, the set that holds the customer or when that set expires, and naming the customer needs a decrypted set on an unlisted occasion; fixed in #43 — blocks again: 2027-03-31
- Exception EKO-1-04/R-19 — owner: @TanerCRB — reason: the D-12 condition rests on whether a restore's host became the server, a fact ADR-0004's restore record does not hold; fixed in #43 — blocks again: 2027-03-31
- Exception EKO-1-04/B-09 — owner: @TanerCRB — reason: the live-database check guarding a failed or cancelled mark is not required to come after the erasure can no longer commit; fixed in #43 — blocks again: 2027-03-31
- Exception EKO-1-04/F-01 — owner: @TanerCRB — reason: row ADR-0005-C19 does not carry D-10's condition on a cancelled mark, which C15 carries; fixed in #43 — blocks again: 2027-03-31
- Exception EKO-1-04/F-02 — owner: @TanerCRB — reason: the channel that carries a report to the human and any copy the human keeps are not listed holders bound by the deletion rule (security auditor U-07); fixed in #43 — blocks again: 2027-03-31

Accepted at gate 2 of EKO-1-05 in [PR #49](https://github.com/TanerCRB/Eko_CRM/pull/49); fixed by
an ADR-0006 addendum tracked in #46:

- Exception EKO-1-05/R-16 — owner: @TanerCRB — reason: the Ownership hold of every link on a shared calendar also suspends deletion jobs through those links with no exit and nothing shown, so an erased customer's data can stay in another rep's calendar (security auditor B-05); fixed by an ADR-0006 addendum tracked in #46 before the EKO-5 synchronisation code — blocks again: 2027-03-31
- Exception EKO-1-05/R-15 — owner: @TanerCRB — reason: a sweep suspended for one staff member's lost access never ends and, under the per-visit order, holds back every later job of the visit; fixed in #46 — blocks again: 2027-03-31
- Exception EKO-1-05/R-11 — owner: @TanerCRB — reason: the conflict rule compares with the values the application last wrote, so a Google time move already applied by polling followed by any later Google edit reverts the rep's rescheduling; fixed in #46 — blocks again: 2027-03-31
- Exception EKO-1-05/R-17 — owner: @TanerCRB — reason: a pending record at a confirmed switch to a new calendar has no defined calendar, giving two events for one visit or an untracked twin in the earlier calendar; fixed in #46 — blocks again: 2027-03-31
- Exception EKO-1-05/R-18 — owner: @TanerCRB — reason: a sweep recorded as not carried out has no event record, so its take-up and its notice are undefined; fixed in #46 — blocks again: 2027-03-31
- Exception EKO-1-05/B-06 — owner: @TanerCRB — reason: a rep with edit rights on a colleague's calendar can hold the colleague's link by moving one application event into their own calendar (availability only); fixed in #46 — blocks again: 2027-03-31
- Exception EKO-1-05/Q-01 — owner: @TanerCRB — reason: the id row of the closed field table does not state the identifier prefix that the sweep by marker relies on (A-21); fixed in #46 — blocks again: 2027-03-31

Accepted at gate 2 of EKO-1-06 in [PR #57](https://github.com/TanerCRB/Eko_CRM/pull/57); B-01 is fixed by EKO-1-15 (#56), R23 and R18 record surviving mutations whose mechanism stays covered as the PR describes:

- Exception EKO-1-06/B-01 — owner: @TanerCRB — reason: third-party images run by full-version tag, not digest, until EKO-1-15 pins them by digest — blocks again: 2027-03-31
- Exception EKO-1-06/R23 — owner: @TanerCRB — reason: the proxy's OpenAPI refusal on the app site is a deliberate second layer (A-08) over backend serving its docs outside /api/, so removing it alone fails no test — blocks again: 2027-03-31
- Exception EKO-1-06/R18 — owner: @TanerCRB — reason: the root-decoy mutation could not reach any image; the mechanism is covered by QA's decoy test (R18c) and the vacuous CI step was removed — blocks again: 2027-03-31
