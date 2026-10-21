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
