# EKO-4-02 — Changing a visit: only its owner changes it, the answer order of a change, and ADR-0003-C41 limited to customers — ADR-0003 addendum draft — 2026-11-28

**Status:** Draft — pending approval
<!-- Only a human changes this status. The "Addendum text" section below is appended to ADR-0003
as a dated addendum (date = human acceptance) in this task's gate-3 documentation PR. This file is
never itself appended to or edited inside an accepted text. -->

## Context

EKO-4-02 (Issue #279) adds the first operations that change a visit: a change of its start, end
and own address (VIS-9, Moved), a reschedule from the delete prompt, and a cancel (VIS-10), which
also serves "did not happen" on a Held visit (VIS-13). Brief ACC-5: the manager "cannot create,
move or cancel another user's visits — only the visit's owner can".

What the accepted decisions already settle:

- ADR-0003 addendum of 2026-11-17, *Outside the scope means missing*: "A record outside the
  caller's scope is answered exactly as a well-formed identifier that exists nowhere: the same
  status, body and headers other than `Eko-Correlation-Id`." *Access first*: the access
  dependency's answers are given "whatever the request body holds".
- ADR-0003 addendum of 2026-11-17, *Where it is enforced*: "Every `data` function that reads or
  changes rows of an owned table takes that scope as a required argument with no default and
  applies it in the statement that selects by identifier."
- ADR-0003 addendum of 2026-11-26 (customer changes), fifth bullet: "For an operation naming a
  record by identifier, a record outside the scope gets the not-found answer whatever its state; a
  state-dependent answer is given only inside the scope, judged on the row the scoped statement
  selected, in the transaction that writes it." This is written for every operation naming a
  record, so it binds the visit changes as it stands.
- ADR-0003 addendum of 2026-11-26 (visits), ADR-0003-C42: the visit table is an owned table whose
  owner is `visit.owner_subject`, "never by its customer's owner"; a create needs `rep`, looks the
  customer up under `OwnedBy` the caller "for every caller, a caller holding `manager` included",
  and tells a `rep`+`manager` caller 403 `not permitted` for another rep's customer.

What they leave open:

1. **Who may change a visit.** C42 decides create, read and list. The only rule on changes is the
   customer one of 2026-11-26: "Editing, archiving and restoring a customer take the visibility
   scope: a caller holding `manager` changes every customer, with or without `rep`". Applied to a
   visit, that rule would let the manager move and cancel any rep's visit, which ACC-5 forbids.
2. **ADR-0003-C41's opening words** reach visits. C41 opens "For every operation that changes an
   owned record named by identifier (at this date: edit, archive and restore of a customer): a
   caller holding `manager`, with or without `rep`, changes a customer of any owner". The visit is
   an owned record, so from this task's release the letter of C41 covers a visit change and
   demands what ACC-5 forbids.
3. **What a `rep`+`manager` caller is told** when it names another rep's visit in a change. That
   visit is inside its visibility scope, so *Outside the scope means missing* does not decide it.
4. **The order of the answers on a change**, which C42 fixes for a create only.

## Decision (proposed)

### 1. Changing a visit takes the caller's own records, for every caller (ADR-0003; adds a rule)

- Every operation that changes a visit named by identifier (at this date: the change of its start,
  end and own address, the reschedule and the cancel) needs `rep`. The visit it names is selected
  under `OwnedBy` the caller's subject for every caller, a caller holding `manager` included. The
  visibility scope never decides which visit may be changed. The scope is built only in
  `backend/app/domain/ownership.py` (ADR-0003-C36) and applied in the statement that writes the
  row; a read that selects the row for a state check takes the same scope in the same transaction.
- A caller holding `manager` without `rep` is refused (403) and nothing changes, also on a visit
  whose `visit.owner_subject` is its own subject.
- A change never sets or alters the visit's identifier, customer or owner. A request value naming
  any of them is refused with the 422 of an unknown field.
- The visit's cancelled state and its Moved flag are values of the record, never part of a scope.
  A cancelled visit stays inside its owner's and the manager's visibility scope and is read and
  listed as any other visit (gate-1 G-5 decides only how the SPA shows and counts it).
- No function is added to the closed system-read list; no visit operation is marked non-CRM.

### 2. The answer order of a change (ADR-0003; adds a rule)

Each answer is judged only when the ones before it passed:

1. the access decision (401, the `Origin` 403, the role 403), before the body is read
   (ADR-0003-C34);
2. the body alone (422): field form, the wall-time resolution of ADR-0002 *Wall time entered by a
   user* and the end after the start, judged on the body's own values before any record is read;
3. the `rep` requirement (403);
4. the visit under the own-records scope: a visit outside it, or nowhere, answers 404
   `{"detail":"not found"}`, except as item 5 says;
5. for a caller whose visibility scope is all records, a visit outside its own-records scope but
   inside its visibility scope answers **403 `{"detail":"not permitted"}`** *(pending gate-1
   question A-2; under A-2 B it answers the 404 of item 4)*. The `domain` function that builds the
   scopes decides who may be told this, from the caller value; a caller holding `rep` without
   `manager` never reaches the read that tells it;
6. the state-dependent answers (a Held or a cancelled visit, an archived customer if gate 1 makes
   that a refusal), judged on the row the own-records statement selected, in the transaction that
   writes it.

A refused change changes nothing.

### 3. ADR-0003-C41 limited to customers (ADR-0003; restates a control — a declared deviation)

ADR-0003-C41's opening words "For every operation that changes an owned record named by
identifier (at this date: edit, archive and restore of a customer)" read "For every operation that
changes a customer named by identifier (at this date: edit, archive and restore)". The rest of
C41, and the customer-change text of the addendum of 2026-11-26, are unchanged. Visit changes are
governed by the new control ADR-0003-C43.

## Options considered

### Q-A, the scope a visit change takes (A-1)

| Option | Cost | Closes off |
|---|---|---|
| **A. `OwnedBy` the caller for every caller; `rep` required** (recommended) | One more scope use in `ownership.py`; the planted manager-only visit is the only test that separates "needs `rep`" from "is the owner" (the EKO-4-01 M-02 lesson). | Nothing the brief asks for: ACC-5 forbids the manager's change. |
| B. The visibility scope, as for customers (C41) | Nothing to build beyond the customer pattern. | ACC-5 ("only the visit's owner can"); the manager moves and cancels any visit, and EKO-5-02 would then write into another owner's calendar. |

### Q-B, a `rep`+`manager` caller naming another rep's visit (A-2, the Story's G-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. 403 `not permitted`, nothing changes** (recommended) | A second read under the visibility scope after the own-scope statement selects nothing, decided in `ownership.py`, as C42 does for a create. | Nothing. |
| B. The 404 of a missing visit | One statement only. The answer is untrue for a caller that reads that visit by identifier, and the SPA cannot tell "not yours" from "gone". No deviation is needed: *Outside the scope means missing* does not forbid it, but C42's create answers the opposite way. | A truthful refusal for the manager; one answer pattern for create and change. |

### Q-C, C41's opening words (A-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. Restate C41 to customer changes, a declared deviation; C43 governs visit changes** (recommended) | The `adr-deviation` label on #279, which the Issue does not apply today; one restated row, carried by the restatement check of `backend/tests/static/test_eko110_k07_changeset.py`. | Nothing. |
| B. Leave C41 as written and rely on its "at this date" parenthesis | No deviation label. | Two accepted controls whose letters contradict each other on every visit change: an evaluator reading C41 must fail the owner-only rule, and one reading C43 must fail C41. |

## Addendum text — ADR-0003

> ### <acceptance date> — Changing a visit: only its owner changes it; the answer order of a change; ADR-0003-C41 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-4-02, Issue #279).
>
> **What it adds.** The addendum of 2026-11-26 on visits decides who creates, reads and lists a
> visit, not who changes one, and the addendum of 2026-11-26 on customers lets a caller holding
> `manager` change any customer, which ACC-5 forbids for visits. From this date:
>
> - Every operation that changes a visit named by identifier (at this date: the change of its
>   start, end and own address, the reschedule and the cancel) needs `rep`. The visit is selected
>   under `OwnedBy` the caller's subject for every caller, a caller holding `manager` included,
>   in the statement that writes the row; the visibility scope never decides which visit may be
>   changed. A caller holding `manager` without `rep` is refused (403) and nothing changes.
> - A change never sets or alters the visit's identifier, customer or owner. The cancelled state
>   and the Moved flag are values of the record, never part of a scope; a cancelled visit is read
>   and listed as any other.
> - On a change the answers come in this order, each judged only when the ones before it passed:
>   the access decision; the body alone (422), the wall-time resolution and the end after the
>   start included; the `rep` requirement (403); the visit under the own-records scope (404 when it
>   selects nothing); for a caller whose visibility scope is all records, a visit inside that scope
>   but not its own (403 `not permitted`); the state-dependent answers, judged on the row the
>   own-records statement selected, in the transaction that writes it. A refused change changes
>   nothing.
> - No function is added to the closed system-read list.
>
> **What it restates.** ADR-0003-C41's opening words "For every operation that changes an owned
> record named by identifier (at this date: edit, archive and restore of a customer)" read "For
> every operation that changes a customer named by identifier (at this date: edit, archive and
> restore)". The rest of C41 is unchanged.
>
> **New control ADR-0003-C43** (table below). Every other rule and control of this decision is
> unchanged; the session-exempt, role-free and non-CRM lists are unchanged, and no visit operation
> is marked non-CRM.
>
> **Why.** ACC-5 lets only a visit's owner move or cancel it, and a caller holding `manager` may
> hold `rep` as well, so the visibility scope cannot be the change scope. A state answer before the
> scope would tell a rep that another rep's visit exists and what state it is in (ACC-8). C41's
> opening words cover every owned record, so without the restatement two accepted controls would
> contradict each other on every visit change. Restating an accepted control is a declared
> deviation, following the addenda of 2026-11-20 (C33), 2026-11-22 (C35) and 2026-11-26 (C33).
> Approved by the human at gate 1 of EKO-4-02 on <acceptance date> (Issue #279).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C43 | With visits of reps A and B stored, and a visit of rep A planted on a customer rep B owns: for every operation that changes a visit named by identifier (at this date: the change of start, end and own address, the reschedule and the cancel), a caller holding `rep` without `manager` changes only visits whose `owner_subject` is its subject, the planted visit included, and rep B cannot change the planted visit although B owns its customer; a rep naming another owner's visit, Planned, Held or cancelled, gets an answer equal to the same request on a well-formed visit identifier that exists nowhere (status, body, headers other than `Eko-Correlation-Id`), never a state-dependent answer, and that visit's row is byte-identical afterwards; a caller holding `manager` without `rep` gets 403 and nothing changes, also on a visit whose `owner_subject` is its own subject; a caller holding `rep` and `manager` changes its own visits, and naming another owner's visit answers 403 `{"detail":"not permitted"}` and changes nothing; administrator-only and role-less callers get 403, a request without a session 401; a body failing validation gets its 422 whoever owns the named visit; a body naming an owner, a customer or an identifier is a 422 and changes nothing; after every change the visit's identifier, `customer_id` and `owner_subject` are the stored ones; the own-records scope is applied in the statement that writes the row, so removing it from that statement alone, with any scoped read kept, fails a test or is recorded as a redundant layer by QA. |
| ADR-0003-C41 (restated) | As ADR-0003-C41 of 2026-11-26, its opening words reading "For every operation that changes a customer named by identifier (at this date: edit, archive and restore)"; every clause after them is unchanged. |

## Open questions for gate 1

- **A-1, the scope a visit change takes** (Q-A). A, recommended: `OwnedBy` the caller for every
  caller, `rep` required. B: the visibility scope, against ACC-5.
- **A-2, a `rep`+`manager` caller naming another rep's visit** (Q-B; the Story's G-4). A,
  recommended: 403 `not permitted`. B: the missing-visit 404, which needs no deviation but departs
  from C42's create.
- **A-3, C41's opening words** (Q-C). A, recommended: restated to customer changes, a declared
  deviation (label `adr-deviation` on #279). B: left as written, with the two controls in conflict.
- **A-4, accept this addendum text** (A, recommended), or reject it (B). If rejected, no accepted
  text says who may change a visit; the owner-only rule, the answer order and the `not permitted`
  answer are decided in code only, and C41's letter applies to visit changes.
