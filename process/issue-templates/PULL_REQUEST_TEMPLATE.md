<!--
Gate 2. A human approves the merge — this template exists so they approve
with proof in hand, not from the author's description.

Leave an unfilled field empty and write why. An entry of "not applicable" without justification is
worse than empty, because it looks like it was checked.

Default variant, for changes under backend/. The frontend variant is
.github/PULL_REQUEST_TEMPLATE/frontend.md; a change touching both sides fills both invariant lists.
-->

<!--
Refs, not Closes: merging this PR must leave the Issue open, waiting for gate 3 (state:evidence).
The gate-3 documentation PR is the one that says "Closes #<N>".
-->
Refs #

Verified at: <!-- the VERIFIED SHA from the task command, step 11a; every report below refers to it -->

## What is changing and why

<!-- Why, not just what. One to three sentences. -->

## Definition of done — proof

<!--
Quote the *Definition of done:* line from the story and point to what satisfies it: a test class
name, a query, an artifact. Code that exists but has no passing test does not check off the task.

Then one line per test, for every criterion judged by a test, with the name as it appears in the
test file — scripts/evidence-chain.sh finds it there before gate 2:
- K-01 — test: <test name>
-->

- Condition:
- Proof:

## Mutation

<!--
Required if the PR carries a strong claim (isolation, idempotency, a database constraint, permissions).
Remove the mechanism, confirm that the test actually fails, and propose a line for the mutation register
(e.g. docs/architecture/walking-skeleton.md#checking-that-tests-are-not-empty).

One line per mutation, for every criterion judged by a test — scripts/evidence-chain.sh reads them:
- K-01 — removed: <mechanism> — result: killed, <n> tests failed
- K-03 — removed: <mechanism> — result: SURVIVED — <why>
-->
- Proposed row for the mutation register (entered at gate 3, not before):
- Mutation patch — the exact change QA made, against the checkpoint (`Base: <SHA>` on its first line), so anyone can rerun it with `git apply` on that SHA:

<details><summary>mutation.patch</summary>

```diff
```

</details>

## Contrast test

<!--
A negative test without contrast also passes when the mechanism blocks everything.
What case proves that the mechanism does not simply always deny?
-->

## Invariant Guardian report

<!-- Verdict PASS / STOP. On STOP — what was done with the findings. -->

## Undecidable — the human's decisions

<!--
Every criterion a role returned as UNDECIDABLE (marked Judged by: human, or depending on a fact
outside the change): the criterion, what was missing, what the tests show, and the human's
decision at gate 2. "None" if no role returned one.

For a criterion marked Judged by: human, the decision is one line — scripts/evidence-chain.sh
reads it:
- K-02 — decision: <the human's decision>
-->

## Assumptions — the human's decisions

<!--
Every gap in the spec the Developer closed by assumption (the developer report's ledger): A-01,
the criterion, what was unclear, what was assumed, the test that shows it — and the human's
decision at gate 2. Accepted: the assumption is written into the criteria as an amendment.
Rejected: the decision says what the behavior must be instead. "None" if the ledger is empty.

Scope lock: holds / re-locked at gate 2 (fingerprint) — see the task command, "Scope lock".
-->

## Recorded exceptions

<!--
Every finding the human let through without a fix (a STOP finding, a reservation, a weakening
finding), one line each, in the team contract's format (§3a) — nothing else on the line:

Exception <task>/<finding> — owner: @<handle> — reason: <one sentence> — blocks again: <YYYY-MM-DD>

Write the lines outside this comment. scripts/exception-check.sh reads them back before gate 2;
at gate 3 they move to the exception register. "None" if nothing was let through.
-->

## Invariants affected by this change

<!--
Check what the change affects. Unchecked = not applicable. One item = one rule checkable in the
diff; the full list is the Invariant Guardian's checklist (agents/invariant-guardian.md). Items
marked "pending" cite a decision that isn't accepted yet (docs/PLAN.md, EKO-1-01).
-->

- [ ] New endpoint — Pydantic request and response models, `response_model` set, access declared through the shared dependency
- [ ] New request model — `extra="forbid"`, bounded lengths, typed formats
- [ ] Response carries personal data — only the fields the screen needs; nothing hidden by the frontend instead of not sent
- [ ] Personal data — never in logs, error messages or test fixtures copied from real data
- [ ] New permission — has a denial case in the tests
- [ ] Schema change — only through the migration tool of the persistence decision (pending ADR-0002), expand → deploy → contract
- [ ] New query — parameterized; dynamic identifiers from an allow-list
- [ ] New time value — timezone-aware, from the injected clock
- [ ] New configuration or secret — read only through the settings module, `.env.example` updated
- [ ] New dependency — manifest and lock file change together, with a reason in the PR
- [ ] New import across layers — allowed by docs/architecture/layer-dependencies.md

## Out of scope for this PR

<!-- What is deliberately left for later, and where that is recorded. -->
