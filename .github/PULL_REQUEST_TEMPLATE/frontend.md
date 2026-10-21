<!--
Gate 2. A human approves the merge — this template exists so they approve
with proof in hand, not from the author's description.

Leave an unfilled field empty and write why. An entry of "not applicable" without justification is
worse than empty, because it looks like it was checked.

This is the frontend variant (changes under frontend/). The backend variant is the default
.github/PULL_REQUEST_TEMPLATE.md; both are synced from process/issue-templates/.
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
Quote the _Definition of done:_ line from the story or from docs/PLAN.md and point to
what satisfies it: a test name, an artifact, a command result. Code that exists but has no passing
test does not check off the task.

A screenshot is not proof. It shows one theme, one locale, one data state, and one
window width — and it is usually the other half of each pair that breaks.

Then one line per test, for every criterion judged by a test, with the name as it appears in the
test file — scripts/evidence-chain.sh finds it there before gate 2:
- K-01 — test: <test name>
-->

- Condition:
- Proof:

## Mutation

<!--
Required if the PR carries a strong claim: that a screen does NOT show something, that it denies,
that it does not miscalculate, that it does not drop the locale. Remove the mechanism, confirm that
the test actually fails, and propose a line for the frontend state register (entered at gate 3).

The mutation should target the layer the criterion is about. Removing a key from the translation
catalog is not a mutation for a claim computed by the date library.

One line per mutation, for every criterion judged by a test — scripts/evidence-chain.sh reads them:
- K-01 — removed: <mechanism> — result: killed, <n> tests failed
- K-03 — removed: <mechanism> — result: SURVIVED — <why>
-->
- Proposed row for the frontend state register (entered at gate 3, not before):
- Mutation patch — the exact change QA made, against the checkpoint (`Base: <SHA>` on its first line), so anyone can rerun it with `git apply` on that SHA:

<details><summary>mutation.patch</summary>

```diff
```

</details>

## Contrast test

<!--
An assertion without contrast also passes when the mechanism blocks everything. A screen rendering
an empty list satisfies "no items outside scope are visible" flawlessly and forever.

What case proves that the mechanism does not simply always deny? A 200 response gives a table where
a 403 gives a screen with no buttons.
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

## Dependency on the backend

<!--
What this PR takes from `backend/`, and where it comes from: the same PR, or a backend PR already
merged (link it). An API shape the backend doesn't expose yet is not invented here.
-->

## Invariants affected by this change

<!--
Check what the change affects. Unchecked = not applicable. They all share one trait: breaking them
still renders correctly. Nothing throws, so the only defense is this list and a test.
-->

- [ ] New API call — through the typed client in `frontend/src/api/`, types checked against the backend's OpenAPI schema; no `fetch` in components
- [ ] New form — validation mirrors the backend's; a 422 maps back to its fields; the backend stays the authority
- [ ] Personal data — not in localStorage, sessionStorage, IndexedDB, URLs, the console or analytics
- [ ] Sign-out — per-user cache and storage cleared
- [ ] New screen reading data — loading, empty, error and populated states all explicit
- [ ] New mutation — double submit doesn't send a second command; the server-state cache is invalidated
- [ ] New UI text — in the translation catalog, not in the component
- [ ] New color — through a theme token, no hex outside the centralized source
- [ ] New date/time on screen — through the shared formatting helper; calendar dates not shifted through `new Date`
- [ ] Raw HTML or a user-supplied URL — no `dangerouslySetInnerHTML`, no `javascript:` URL
- [ ] New navigation item — never unlocks without its route
- [ ] New `VITE_*` variable — holds nothing secret (the bundle is public)

## Out of scope for this PR

<!-- What is deliberately left for later, and where that is recorded. -->
