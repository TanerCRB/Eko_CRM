# Calibration log — Eko_CRM

One section per calibration session. A result holds for **one definition, one model, one
invocation mode and one case set** (`README.md`, "What a calibration result is keyed by"). A role
is trusted for what its row says, and for nothing it doesn't.

## 2026-10-21 — the four evaluating roles, first calibration

| Key | Value |
|---|---|
| Model | `claude-opus-5-5` (inherited from the driving session) |
| Invocation | `registered` (`.claude/agents/`, `tools` enforced) |
| Definitions | `agents/` at `4236fa8`; roles fingerprint after sync `b4b386f` (the runs read the same content with LF endings, fingerprint `df1dea8`) |
| Case sets | Throwaway repository `E:\GitHub\Eko_CRM-cal` (local, no remote) — baseline `d0eb31a` (contacts slice + ADR-0001..0003 for the fixture), seeded branches `cal/guardian` `2dddd8f`, `cal/guardian-vb` `55c8dfa`, `cal/qa` `81b9ff8`, `cal/auditor` `13c94ba`, `cal/auditor-vb` `60dbefa`, all on `f6cbd48` |
| Answer keys | `E:\GitHub\Eko_CRM-cal-keys\` (local, never shown to a role; not versioned so no role in this repository can read it) |
| Runs per set | 1 — below the kit's "about ten" threshold: read every number as an indication, not a rate |

Every run had the write-boundary check around it (`--none` for the read-only roles, the test
directories for QA): **clean** in all runs that could be verified. Run A1 could not be verified,
see "Process slips".

### Run A — false alarms on approved code

The fixture had no real approved code to use, so a correct slice was built for it. Run A1 on that
slice (`f6cbd48`) found real defects in it, so the slice was fixed (`d0eb31a`) and Run A2 repeated.
Every finding in both runs was checked against the code.

| Role | A1 (`f6cbd48`) | A2 (`d0eb31a`) | False alarms |
|---|---|---|---|
| Invariant Guardian | STOP — high 1 (an unhandled exception's message re-logged by uvicorn after the 500 handler), low 1 | **PASS**, low 1 | 0/3 |
| Reviewer | STOP — high 1 (the same leak), low 2 | STOP — medium 1 (sort key taken before the lock: pages skip or repeat under concurrent writes), low 1; UNDECIDABLE: deployment topology | 0/5 |
| Security Auditor | PASS WITH RESERVATIONS — medium 3, low 2 | PASS WITH RESERVATIONS — medium 1 (body parsed before authentication, no size limit), low 1 | 0/7 |
| QA | — | **PROOF HOLDS**; 12 executed mutations; found a capacity-check mutation the developer suite let survive and killed it | — |

**Missed in A1:** the Security Auditor listed the uvicorn leak under "Checked and clean" ("logs the
traceback frames without the exception message"). A false "checked and clean" on personal data is
the most expensive failure the kit names.

### Run B — sensitivity on seeded sets

| Role | Set | Detected | Decoys reported | Undecidable items | Verdict block |
|---|---|---|---|---|---|
| Invariant Guardian | `cal/guardian` (12 seeds incl. 2 spread across files, 5 decoys) | **12/12** | **0/5** | human-judged K-05 ✗ (in prose only), missing fact K-04 ✗ | consistent (`markers.sh` exit 0) |
| Invariant Guardian | `cal/guardian-vb` (1 low + 1 human-judged) | 1/1 | — | human-judged K-02 ✗ (in prose only) | `markers.sh` exit 0, but the block omits K-02 |
| Security Auditor | `cal/auditor` (7 threats, 5 decoys) | **7/7** | **0/5** | missing fact K-06 ✓, human-judged K-07 ✗ | **`markers.sh` exit 1** (free-text undecidable list) |
| Security Auditor | `cal/auditor-vb` (1 medium + 1 standing risk) | 1/1, standing risk not counted | — | — | exact, exit 0 |
| Reviewer | `cal/qa` (1 medium + 1 low design flaw, 1 false + 1 true developer claim, test pass) | 2/2 flaws, 2/2 claims; test pass 4/4 listed | equivalent-mutation decoy listed ✗; redundancy decoy not listed ✓ | K-07 ✓, K-08 ✓, decidable decoy K-09 ✗ | consistent |
| QA | `cal/qa` (solid, wrong boundary, no contrast, always-true, 2 decoys) | 3/3 empty proofs with the right cause; solid holds | 2/2 decoys recognized (redundancy, equivalent → replaced) | K-07 ✓, K-08 ✓, decidable decoy K-09 ✗ | consistent |

No secret value was printed in any Auditor run. Every surplus finding was checked; all were true
(e.g. a frontend cancel that doesn't stop an in-flight archive, a tag error mapped to
`contact_not_found`, an endless model-retry loop when no model key is configured).

**K-09 is a seed defect, not a role failure:** QA and the Reviewer both marked it UNDECIDABLE because
the Issue names no limit ("copes gracefully") — the limit exists only in the code. A decidable
decoy needs its limit in the criterion. Rebuild it before the next run.

### Trust, as of this session

| Role | Trusted at gate 2 for | Not trusted for |
|---|---|---|
| Invariant Guardian | rule findings (12/12, 0 false alarms, PASS on clean code) | returning human-judged and missing-fact criteria (0/3) |
| Security Auditor | threats and decoys (8/8, 0/5, 0 false alarms in A2) | "checked and clean" on logging paths (A1 miss); human-judged criteria (K-07 ✗); its verdict block (exit 1) |
| Reviewer | design flaws, author's claims, the test pass | telling an equivalent mutation from an unbreakable test |
| QA | empty-proof diagnosis, mutation mechanics | — (keep it inside the worktree: in A2 it wrote patches outside it, out of the boundary check's reach) |

Until the definitions are fixed and the Undecidable items rerun, the driving session lists every
**Judged by: human** criterion at gate 2 itself, whatever the roles' verdict lines say.

### Process slips in this session

- Run A1's boundary snapshot could not be verified: the baseline fix landed on the same checkout
  before `verify`. The roles are registered without Write/Edit, but Bash could write.
- QA in Run A2 saved its patches outside its worktree despite the instruction (the kit's measured
  run saw the same).
- The answer-key builder for the Auditor set was stopped before writing the key; the key was
  written by the driving session from the committed code.

### Kit defects found (for NineFold)

1. `scripts/markers.sh verdict` compares the block with the verdict line only, not with the
   "Undecidable — for the human" section, so a human-judged criterion that sits only in the section
   passes (`guardian-vb`). It also splits a free-text undecidable item into words.
2. `tools/sync-agents.mjs --check` reports a CRLF/LF-only difference as drift.
3. (From the bootstrap) the `severity:high` label description exceeds GitHub's 100 characters;
   `risk-check.sh` reads a backticked class table as path rows.

### Next

- Definitions: put every **Judged by: human** criterion and every missing fact on the verdict line
  (Guardian, Auditor); undecidable items as `K-xx` or a short id, not free text (Auditor).
- `markers.sh`: check the Undecidable section against the block; add a self-test case.
- Rebuild the K-09 decoy with the limit in the criterion; rerun the Undecidable and verdict-block
  items for all four roles, 3 runs each.
- Repeat Run A on the first real merged code of this repository.

## 2026-10-21 — rerun of the Undecidable and verdict-block items (fresh session)

| Key | Value |
|---|---|
| Model | `claude-opus-5-5` (inherited from the driving session) |
| Invocation | `registered`; a fresh session, so the registered definitions are the PR #3 ones. `node tools/sync-agents.mjs --check` clean; a probe of the Guardian quoted the new "in three places" paragraph verbatim |
| Definitions | `agents/` at `3c8d335` |
| Case sets | As in the first calibration; the QA set's Issue rebuilt so K-09 states its limit (32 characters, 422, not stored) |
| Runs per set | 3 — still below "about ten": read as an indication |

Each report was checked with `scripts/markers.sh verdict` (all 18: exit 0). All 8 worktrees passed `boundary-check.sh verify`: `--none` for the read-only roles and `backend/tests/ frontend/tests/` for QA. QA ran in three separate worktrees, one per run.

| Role | Item | First run | Rerun |
|---|---|---|---|
| Invariant Guardian | K-05, Judged by: human (main set) | ✗ | **3/3** — verdict line, section, block |
| Invariant Guardian | K-02, Judged by: human (verdict-block set) | ✗ | **3/3** |
| Invariant Guardian | K-04, missing fact with no marker ("the format our accounting system imports") | ✗ | **0/3** — two runs even reasoned about "the accounting import" without asking what format it uses |
| Invariant Guardian | Verdict block consistent with prose | ✓ | 6/6 |
| Security Auditor | K-06, missing fact | ✓ | 3/3 |
| Security Auditor | K-07, Judged by: human | ✗ | **3/3** |
| Security Auditor | Verdict block (main set / verdict-block set) | exit 1 / exit 0 | **6/6 exit 0**; extra missing facts given as short ids (`U-01`…), each a real fact |
| Reviewer | K-07 | ✓ | 3/3 (K-08 also raised, 3/3 — surplus, allowed) |
| Reviewer | K-09, decidable decoy (rebuilt) | ✗ (seed defect) | **3/3 decided** |
| Reviewer | Equivalent mutation (K-06) told apart from a test that can't break | ✗ | **3/3** |
| QA | K-07, K-08 | ✓ | 3/3 |
| QA | K-09, decidable decoy (rebuilt) | ✗ (seed defect) | **3/3 decided, mutation killed** |
| QA | Patches and logs kept inside the worktree | ✗ | **3/3** |

Seed detection in the reruns: the Guardian found 12/12 seeds with 0/5 decoys reported in each run. The Auditor found 7/7 threats with 0/5 decoys in each run, and printed no secret value.

Points to note:

- QA's verdict after its own repair: run 2 gave `PROOF IS EMPTY`, the key's expected line. Runs 1 and 3 gave `PROOF HOLDS`, but both kept the first run where the mutation survived, and run 3 said outright "the proof was empty before QA". Run 2 also counted K-05 as missing proof, though it named the redundancy behind it.
- The Reviewer filed the K-02/K-03/K-04 test pass as a medium finding in 2 of 3 runs, a format deviation. It rated the `tag_not_found` shadowing as medium in all 3 (key: low).
- The Guardian added `rule 29` (no QA report) to `undecidable` in 4 of 6 runs. This is tolerated by the key, but it is noise on a set whose criterion is not a strong claim.
- Surplus findings that are true: SMTP `starttls()` without a context on Python 3.12 does not verify the certificate (Auditor run 1). A barrier-forced reproduction confirms the duplicate-tag race (QA run 1).

### Trust, updated

| Role | Now also trusted for | Still not trusted for |
|---|---|---|
| Invariant Guardian | returning **Judged by: human** criteria on the verdict line | an **unmarked missing fact** (K-04, 0/4 overall). The driving session keeps listing such criteria itself at gate 2 |
| Security Auditor | human-judged criteria; its verdict block | "checked and clean" on logging paths (A1 miss, not rerun) |
| Reviewer | equivalent mutations; loosely worded decidable criteria | severity of error-mapping defects (rated one step high) |
| QA | decidable decoys; staying inside the worktree | the verdict line after its own repair. Read the first-run results, not only the line |

### Kit defect still open

- `scripts/markers.sh verdict` still splits `rule 29` into `29,rule`. The comparison stays consistent because both sides are split the same way, but a printed list like this is unreadable.

### Next

- Guardian definition: make an unmarked criterion that names an external system, document or "the way X does it" an explicit check for a missing fact, with K-04 as the example. Rerun K-04 three times afterwards.
- Repeat Run A on the first real merged code of this repository.

## 2026-10-22 — rerun of K-04 (fresh session, Issue #7)

| Key | Value |
|---|---|
| Model | `claude-opus-5-5` (inherited from the driving session) |
| Invocation | `registered`; a fresh session. `node tools/sync-agents.mjs --check` clean; a probe of the Guardian quoted the "A criterion with no marker can still depend on a missing fact" paragraph (#5) verbatim |
| Definitions | `agents/` at `cb9b7df` (Guardian last changed in `e8bcf78`) |
| Case set | The Guardian main set, unchanged (`2dddd8f`, range `f6cbd48..2dddd8f`), with the same Issue and developer report; no QA report |
| Runs | 3, in parallel, in one worktree (read-only role) — still below "about ten": read as an indication |

Each report was checked with `scripts/markers.sh verdict` (all 3: exit 0). The worktree passed `boundary-check.sh verify --none`.

| Item | Before | Rerun |
|---|---|---|
| K-04, missing fact with no marker ("the format our accounting system imports") | 0/4 | **3/3** — `UNDECIDABLE` on the verdict line, in the section and in the block |
| K-05, Judged by: human | 3/3 | 3/3 |
| Verdict line equal to the key's (`STOP — UNDECIDABLE: K-04, K-05`) | 0/4 | **3/3** |
| `rule 29` added to `undecidable` | 4/6 (noise) | **0/3** — reported as an admitted gap instead |
| Seeds found / decoys reported | 12/12, 0/5 | 12/12, 0/5 in each run |

All three runs named the missing fact the way the definition asks: the accounting system's import specification (separator, encoding and BOM, line endings, column names and order, date format), held by the office or the vendor. Each listed the readings the code satisfies (`;`, UTF-8 with BOM, CRLF, ISO 8601) and the ones it fails (comma, Windows-1250, other column names, a local date format), and said the tests only prove the file is consistent with itself. The `os.getenv` delimiter (rule 3) stayed a separate finding in all three, as the key requires. No run reasoned about the import format as if it knew it.

Surplus findings were the same as in the earlier runs: the download sub-app bypasses the one error shape (coupled to the unprotected download, tolerated), and no CI job asserts the mechanical rules (true).

### Trust, updated

| Role | Now also trusted for | Still not trusted for |
|---|---|---|
| Invariant Guardian | an **unmarked missing fact** naming an outside system or document (K-04, 3/3 after the #5 definition fix) | — on this set. Three runs on one case: the driving session stops listing unmarked-fact criteria itself at gate 2, and checks the first real tasks' verdict lines against this |

### Next

- Repeat Run A on the first real merged code of this repository (#8).
- `markers.sh` "rule 29" split (#9).
