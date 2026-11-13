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


Accepted at gate 2 of EKO-1-06 in [PR #57](https://github.com/TanerCRB/Eko_CRM/pull/57); B-01 was fixed by EKO-1-15 (#56) and left this register at its gate 3, when the `v0.1.1` release composition named `proxy` (on a digest-pinned `caddy` base), `keycloak` and `postgres` by digest; R23 and R18 record surviving mutations whose mechanism stays covered as the PR describes:

- Exception EKO-1-06/R23 — owner: @TanerCRB — reason: the proxy's OpenAPI refusal on the app site is a deliberate second layer (A-08) over backend serving its docs outside /api/, so removing it alone fails no test — blocks again: 2027-03-31
- Exception EKO-1-06/R18 — owner: @TanerCRB — reason: the root-decoy mutation could not reach any image; the mechanism is covered by QA's decoy test (R18c) and the vacuous CI step was removed — blocks again: 2027-03-31

Accepted at gate 2 of EKO-1-10 in [PR #65](https://github.com/TanerCRB/Eko_CRM/pull/65) (decided by the human on 2026-10-29 at the developer checkpoint, recorded on #51); both cover `scripts/weakening-check.sh` findings on test data inside EKO-1-10's own test files, which the check sees only in that task's change set:

- Exception EKO-1-10/weakening-1 — owner: @TanerCRB — reason: the seven noqa strings are test data of the rule-19 suppression check and suppress nothing — blocks again: 2026-11-30
- Exception EKO-1-10/weakening-2 — owner: @TanerCRB — reason: the type ignore makes the rule-9 fixture's bare dict return possible, which is the violation under test — blocks again: 2026-11-30

Accepted at gate 2 of EKO-1-14 in [PR #77](https://github.com/TanerCRB/Eko_CRM/pull/77) (decided by the human on 2026-10-31 and 2026-11-02, recorded on #55):

- Exception EKO-1-14/weakening-1 — owner: @TanerCRB — reason: `# noqa: S108` on a path QA plants inside the run container as the at-rest scan's contrast (`test_adr0004_backup_no_dump_at_rest.py`), not a temporary file of the test — blocks again: 2027-05-02
- Exception EKO-1-14/weakening-2 — owner: @TanerCRB — reason: `# noqa: S108` on the run-directory pattern the cleanup tests look for inside the backup container (`backup_lab.py`), never opened by the test — blocks again: 2027-05-02
- Exception EKO-1-14/weakening-3 — owner: @TanerCRB — reason: `# noqa: S608` on test SQL whose table name is a hex value the test generates (`test_adr0004_c15_backup_set_contents.py`) — blocks again: 2027-05-02
- Exception EKO-1-14/M12 — owner: @TanerCRB — reason: a backup point read milliseconds after the snapshot export cannot be told apart by any test without a hold point inside the shipped image, which the addendum forbids; the code reads the export statement's own time — blocks again: 2027-05-02

Accepted at gate 2 of EKO-1-13 in [PR #81](https://github.com/TanerCRB/Eko_CRM/pull/81) (decided by the human on 2026-11-02 and 2026-11-04, recorded on #54):

- Exception EKO-1-13/weakening-1 — owner: @TanerCRB — reason: `# type: ignore[method-assign]` on the `build_middleware_stack` override that places the request layer outside ServerErrorMiddleware, as the accepted ADR-0005 addendum requires (`backend/app/main.py`) — blocks again: 2027-05-04
- Exception EKO-1-13/weakening-2 — owner: @TanerCRB — reason: `# type: ignore[method-assign]` on a planted `Database.from_settings` failure in test support (`backend/tests/support/fixture_app.py`) — blocks again: 2027-05-04
- Exception EKO-1-13/weakening-3 — owner: @TanerCRB — reason: `# noqa: S608` on a test statement built from a synthetic marker identifier (`backend/tests/runtime/test_adr0005_c3_postgres_error_log.py`) — blocks again: 2027-05-04
- Exception EKO-1-13/weakening-4 — owner: @TanerCRB — reason: `# noqa: S102` on test-only `exec` of a constant probe compiled under an `app/` file name, the only kill of M61/M62 (`backend/tests/unit/test_adr0005_qa_warning_location.py`) — blocks again: 2027-05-04

Accepted at gate 2 of EKO-1-15 in [PR #85](https://github.com/TanerCRB/Eko_CRM/pull/85) (decided by the human on 2026-11-05, recorded on #56); security-1 is tracked in #84. EKO-1-15/security-2 (Security Auditor B-02) is not entered: EKO-1-18 (#83) closed it before the first release tag, in PR #88, raised to proven at gate 3 in PR #93:

- Exception EKO-1-15/weakening-1 — owner: @TanerCRB — reason: read_only_token narrowed so that ci.yml's backend and runtime jobs that read the release record may hold packages: read (C-3, C-8), guarded by three contrast cases. — blocks again: 2027-11-05
- Exception EKO-1-15/weakening-2 — owner: @TanerCRB — reason: EKO-1-10 test test_eko110_k06_no_previous_release_says_compared_nothing amended to run the step's arguments against an empty record double, with a subprocess contrast requiring exit 2 without the token (C-9). — blocks again: 2027-11-05
- Exception EKO-1-15/weakening-3 — owner: @TanerCRB — reason: pytest.skip in test_eko115_k06_c13_previous_release.py:37 while no release is reachable from main (K-06(1)); CannotTell fails, never skips. — blocks again: 2027-11-05
- Exception EKO-1-15/security-1 — owner: @TanerCRB — reason: a push-triggered workflow with packages: write can plant or overwrite a release-record entry whose revision annotation the reachability guard accepts; CI readers are narrowed to run only its backend digest under the head's compose, but that image still decides the compat-check and C13 outcomes and a planted higher version blocks admission of every real release (B-01, B-03; provenance in #84, blocks earlier if EKO-1-08 starts reading the record). — blocks again: 2027-02-05

Accepted at gate 2 of EKO-1-19 in [PR #96](https://github.com/TanerCRB/Eko_CRM/pull/96) (decided by the human on 2026-11-07, recorded on #95); follow-up #98:

- Exception EKO-1-19/M17 — owner: @TanerCRB — reason: a branch on the resolved image name passes both modes, so the literal-name mode-branch grep cannot see it; left to review, follow-up #98 — blocks again: 2027-05-07
- Exception EKO-1-19/M21 — owner: @TanerCRB — reason: weakening-check sees patterns, not a looser assertion; K-05 (b) is judged by evaluator review, which found none in this diff — blocks again: 2027-05-07

Accepted at gate 2 of EKO-1-20 in [PR #113](https://github.com/TanerCRB/Eko_CRM/pull/113) (decided by the human on 2026-11-09, recorded on #76); follow-up #110:

- Exception EKO-1-20/M3 — owner: @TanerCRB — reason: the surviving mutation removes a redundant mechanism, because psql under ON_ERROR_STOP already ends the control session on the 55P03 error — blocks again: 2027-05-09
- Exception EKO-1-20/weakening-1 — owner: @TanerCRB — reason: the EKO-1-15 K-07 and EKO-1-19 K-03 existing-CI-job checks no longer report a changed integer job-level timeout-minutes or the one comment line directly above it, so the runtime jobs could be raised to 75 minutes (CI run 42591459348); removing or adding the key, a non-integer value and every other job change stay red (mutations EKO-1-20/M13–M18); the live-base defect itself is #110 — blocks again: 2027-05-09

Accepted at gate 2 of EKO-1-22 in [PR #132](https://github.com/TanerCRB/Eko_CRM/pull/132) (decided by the human on 2026-11-10, recorded on #48); follow-up #131:

- Exception EKO-1-22/M-05-narrow — owner: @TanerCRB — reason: the surviving mutation removes guards whose job the retained Accepted-comparison already does (duplicate-file and Status-less citations both fail there; QA proved it by hand at `27fe842`), and planting the missing contrasts would open a third fix round against the two-round limit — blocks again: 2027-01-15

Accepted at gate 2 of EKO-1-23 in [PR #129](https://github.com/TanerCRB/Eko_CRM/pull/129) (decided by the human on 2026-11-10, recorded on #110):

- Exception EKO-1-23/weakening-1 — owner: @TanerCRB — reason: the five findings in backend/tests/static/test_eko120_ci_timeout_retune.py (:38, :52, :113, :220, :228) keep the same assertions and only move their input from the live worktree to EKO-1-20's own PR #113 base/head pair, which is the change this Story makes — blocks again: 2026-12-10
- Exception EKO-1-23/M20c — owner: @TanerCRB — reason: the surviving mutation removes the is_eko_1_06_change_set() guard of test_k07_register_check_fails_on_any_other_edit, an equivalent mutation because without the guard the test still asserts that every register variant is flagged and every variant is; hardening that permanently vacuous test is out of scope by gate 1 — blocks again: 2026-12-10

Accepted at gate 2 of EKO-1-24 in [PR #125](https://github.com/TanerCRB/Eko_CRM/pull/125) (decided by the human on 2026-11-10, recorded on #71); follow-ups #127, #128:

- Exception EKO-1-24/M5 — owner: @TanerCRB — reason: the widened-gate mutant is equivalent on every surface K-01..K-04 pin and differs only in the dual-failure corner the Story declares out of scope — blocks again: 2027-05-10
- Exception EKO-1-24/B-01 — owner: @TanerCRB — reason: no charset rule binds revision identifiers reaching the pre-existing plain-text refusal sink; the same actor can already ship arbitrary migration code — blocks again: 2027-02-10

Accepted at gate 2 of EKO-1-25 in [PR #139](https://github.com/TanerCRB/Eko_CRM/pull/139) (decided by the human on 2026-11-11, recorded on #133); follow-ups #137, #138, #140–#144:

- Exception EKO-1-25/weakening-1 — owner: @TanerCRB — reason: the two skip-added findings in backend/tests/static/test_eko125_k04_runtime_collection_unchanged.py (:272, :301) are the text of K-04's skip plants, written only into throwaway repositories so the check is shown to turn red on an added skip marker; no test in the suite is skipped, and removing them would remove K-04's skip mutations — blocks again: 2026-12-11
- Exception EKO-1-25/boundary-1 — owner: @TanerCRB — reason: developer-infrastructure edited .github/workflows/ci.yml (the two runtime jobs' timeout-minutes and the one comment line above each) outside its closed write set, approved by the human on Issue #133 on 2026-11-11 (precedent EKO-1-20, G-4 A); the role gap is follow-up #137 — blocks again: 2026-12-11
- Exception EKO-1-25/B-01 — owner: @TanerCRB — reason: a hung runtime job now holds a runner up to 6 h — up to 720 Actions minutes across both jobs — against the private repository's monthly allowance, which is not known (Auditor B-01, option A accepted at gate 2); at `timeout-minutes: 360` (C-5, GitHub's job maximum) removing the key falls back to the same 360, so the EKO-1-20/weakening-1 mask no longer separates any behaviour — that entry is flagged for the human's revisit — blocks again: 2026-12-11

Accepted at gate 2 of EKO-1-12 in [PR #117](https://github.com/TanerCRB/Eko_CRM/pull/117) (decided by the human on 2026-11-09, recorded on #53); the boot-identity correction [PR #135](https://github.com/TanerCRB/Eko_CRM/pull/135) added no new exception and removed none; entry conditions: #118 (R-02); #119 (R-32) was met and its entry removed at gate 3 of EKO-1-28 ([PR #151](https://github.com/TanerCRB/Eko_CRM/pull/151)); #120 (Q3-1) was met and its entry removed at gate 3 of EKO-1-29 ([PR #159](https://github.com/TanerCRB/Eko_CRM/pull/159)):

- Exception EKO-1-12/qa2-7 — owner: @TanerCRB — reason: the async-mail race behind the pre-fix snapshot shape is host-time-dependent and did not reproduce on demand; the recorded red-before history (QA round 1, reviewer, dev) stands as the evidence for the bounded poll — blocks again: 2026-12-15
- Exception EKO-1-12/G-02 — owner: @TanerCRB — reason: Keycloak 26.8.1 emits neither RESET_PASSWORD nor any brute-force-disable event under the accepted configuration; the reachable-set encoding is sanctioned by the gate-3 ADR-0005 Retention amendment — blocks again: 2026-11-30
- Exception EKO-1-12/S-03 — owner: @TanerCRB — reason: a proxy kept running across a Keycloak recreation is not revoked — host-tier race accepted inside the operator trust tier of EKO-1-03/B-02 until EKO-1-08 — blocks again: 2027-01-31
- Exception EKO-1-12/R-02 — owner: @TanerCRB — reason: the release-flow integration and publishing decision for the custom image are carried by the named successor Issue, not by this composition task — blocks again: 2026-12-15
