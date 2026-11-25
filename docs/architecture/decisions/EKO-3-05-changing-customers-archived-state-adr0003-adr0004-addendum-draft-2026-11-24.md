# EKO-3-05 — Changing a customer: who may edit, archive and restore; a change refused by the NIP unique constraint; the archived state is a filter, never a scope; the default list; the archived-state expand step and a rollback over it — ADR-0003 and ADR-0004 addendum draft — 2026-11-24

**Status:** Draft — pending approval
<!-- Only a human changes this status. Each "Addendum text" section below is appended to its
decision (ADR-0003, ADR-0004) as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

Round 2, 2026-11-25 (gate-1 decision D-5 on Issue #253): EKO-3-03 merged into `main` first (PR
#256). This draft is revised to stand on it: the archived-state revision is `0008` on
`0007_customer_nip_unique`; the change control is renumbered **ADR-0003-C39**, because EKO-3-03's
draft claims ADR-0003-C38; a change refused by the NIP unique constraint is added (section 4,
**ADR-0003-C40**); ADR-0004-C37 stays, being still free. The round-1 text of sections 1 to 3 is
otherwise unchanged in substance.

## Context

EKO-3-05 (Issue #253) adds the first operations that change an existing customer: edit, archive
and restore. It also adds an archived state to the `customer` table, and an active/archived filter
on `GET /api/customers`. The Product Owner decided C-2 A and C-3 A: the manager archives and
restores any customer, and a rep only its own. Edit follows ACC-5: the manager edits any customer.

What the accepted decisions already settle:

- ADR-0003 addendum of 2026-11-17, *Owner*: "A caller without `manager` reads only customers it
  owns; a caller with `manager` reads every customer." *Where it is enforced*: "Every `data`
  function that reads or changes rows of an owned table takes that scope as a required argument
  with no default and applies it in the statement that selects by identifier." *Outside the scope
  means missing*: "A record outside the caller's scope is answered exactly as a well-formed
  identifier that exists nowhere."
- ADR-0003 addendum of 2026-11-20: "`OwnedBy` and `AllRecords` are built only by the `domain`
  function of *Where it is enforced*, from the caller value. A request value never becomes a
  visibility scope." and "A list operation may take request values ... that select records within
  the scope ... joined by AND."
- ADR-0002 *NIP uniqueness*: "Company-wide uniqueness (CUS-6) is enforced by a **unique constraint
  in the database** on `nip`, not only by a check in a service, so two concurrent saves cannot both
  succeed." It holds as written from EKO-3-03's merge (EKO-3-03 addendum draft of 2026-11-24, for
  ADR-0002).
- EKO-3-03 addendum draft of 2026-11-24, for ADR-0003 (approved at EKO-3-03's gate 1, appended at
  its gate 3), for "a create refused because the database's unique constraint on `customer.nip`
  refused its insert": the refusal "is decided by that constraint, never by a read made before the
  insert"; every caller holding `rep` without `manager` gets one answer "whoever owns the stored
  customer, the caller included"; "a caller whose visibility scope is all records also gets the
  stored customer's identifier", read after the refusal by a scoped `data` function. Its control
  is **ADR-0003-C38**. Its revision is `0007_customer_nip_unique`.
- ADR-0005 *Archiving*: "Archiving a customer (CUS-9) keeps all of its personal data, in every place
  that holds it, until the customer is restored or erased. Restoring a customer from the archive
  keeps its data." PD-C4 already names "the customer's owner and its archived state".
- ADR-0004 *Expand → deploy → contract*, release step 1: "Its migrations only add (tables, nullable
  or defaulted columns, indexes) or backfill, so the release before it keeps working on the new
  schema ... and a rollback to the previous release's images needs no schema downgrade."
  *Rollback to the previous release*: "A release that adds or tightens an access rule (a rule
  restricting what a user may read or change) cannot be rolled back".

What they leave open:

1. **Who may change a customer.** The ownership rule decides who *reads* a customer and who
   *creates* one, but not who changes one. `creation_scope` needs `rep`. Nothing says whether a
   change takes the read rule (manager any, rep own) or the creation rule (needs `rep`). ACC-5
   requires the manager to edit a customer of any rep, and the manager may hold no `rep`.
2. **What the archived state is to the scope.** If the archived state were folded into the
   visibility scope (for example "a rep's scope is its own *active* customers"), the scope would
   depend on a record value, and a filter value of `archived` or `both` would *widen* a scope. No
   text forbids that.
3. **ADR-0003-C33 under a default-active list.** C33, as restated on 2026-11-20, reads: "every
   list given no search or filter answers a caller holding `rep` without `manager` exactly the
   records it owns and a caller holding `manager` all of them". Under gate-1 item G-2 A, a list
   given no filter answers only *active* records. C33's letter then fails on every unfiltered list,
   even where the rule holds. This is the same kind of conflict that EKO-3-04 resolved by
   restating C33.
4. **The order of the scope and the state answer.** An edit of an archived customer (G-4 A,
   "restore it first") and any other state answer must not tell a rep that another rep's customer
   exists. C33's by-identifier clause implies the order. It does not name a state answer.
5. **What "keeps working" means for a state column.** On a rollback to a release that does not
   know the archived state, that release reads archived customers as ordinary ones and lists
   them. ADR-0004 does not say whether that counts as the previous release "working" on the new
   schema. It also does not say whether such a release may be rolled back at all.
6. **A change refused by the NIP unique constraint.** The EKO-3-03 text speaks of "a create
   refused because the database's unique constraint ... refused its insert". An edit that sets a
   NIP another customer holds is refused by the same constraint on an `UPDATE`, not an insert, and
   reaches it through the visibility scope, not `creation_scope`: a caller holding `manager`
   without `rep`, which EKO-3-03's create refuses 403 before any NIP is judged, reaches it here.
   Nothing says which answer comes first when the target is out of scope, archived, or the NIP is
   taken. Gate-1 decision D-5 fixed the behavior ("refused exactly as EKO-3-03's create"; keeping
   the customer's own NIP is not a conflict); the rule needs writing down.

## Decision (proposed)

### 1. Who may change a customer (ADR-0003; adds a rule)

- Changing a customer (edit, archive, restore) takes the **visibility scope** of *Where it is
  enforced*. A caller holding `manager` changes every customer, whether or not it holds `rep`. A
  caller holding `rep` without `manager` changes only the customers it owns. A caller holding
  neither is refused (403), as by the role gate. Creation keeps its own rule (needs `rep`).
- A change never sets or alters the owner. A request value naming an owner is refused on a strict
  route (gate-2 decision G-01 of EKO-3-01), and the owner stays the stored one. Changing the owner
  is reassignment (CUS-10, EKO-3-07). That task decides its own rule at its gate 1.
- The `data` function that writes the change applies the scope in the statement that writes the
  row. A scoped read before an unscoped write does not meet this rule. A customer's contacts are
  changed only through a customer selected under the scope, and only that customer's contacts.

### 2. The archived state is a record state, never a scope (ADR-0003; adds a rule, restates C33)

- The archived state is a value of the record. It is never part of `OwnedBy` or `AllRecords`, and
  no visibility scope is built from it. Archived customers stay inside their owner's and the
  manager's scope (G-3 A). They are read by identifier and changed exactly as active ones are,
  except where a state rule refuses the change.
- **The state filter only narrows.** A list selects by state (`active`, `archived`, both) as a
  request value within the scope, joined to it by AND in the same statement. With no state given,
  the list selects `active` (G-2 A). No state value widens a scope; `both` removes the state
  condition and never the scope.
- **Scope before state.** For an operation that names a record by identifier, the answer for a
  record outside the caller's scope is the not-found answer, whatever the record's state. A
  state-dependent answer (a refusal such as "restore it first", or the success of a repeated
  archive or restore) is given only for a record inside the scope. The state is judged on the row
  the scoped statement selected, in the same transaction as the write. So a change that passed the
  state check never lands on a record whose state changed before the write.
- **ADR-0003-C33 restated** (below), because its letter fails on a default-active list where the
  rule holds. Restating an accepted control is a declared deviation.

### 3. The archived-state expand step, and a rollback over it (ADR-0004; adds a rule)

- The revision that adds the archived state, `0008` on `0007_customer_nip_unique`, is an expand
  step under release step 1. It adds the column nullable, or `NOT NULL` with a constant default
  that the database does not evaluate from its clock (ADR-0002-C13). Then an `INSERT` by a release
  that does not name the column stores an **active** customer. It rewrites no existing row's
  personal data, and every existing customer is active after it.
- It ships in the release that also carries EKO-3-03's contract step `0007` and the unreleased
  expand steps `0005` and `0006`. The EKO-3-03 addendum (for ADR-0004) governs `0007` only; this
  section governs `0008` only. `0008` is an expand step, so release step 3 does not apply to it.
- **A release that does not know a record state** keeps working on the expanded schema in this
  sense: its reads and writes succeed, it changes no stored state, and it answers a record in a
  state it does not know as that state's default meaning. For the archived state, the default is
  active: such a release lists archived customers among the active ones. On a rollback to such a
  release, that effect is accepted and announced with the rollback. Archived customers are
  archived again, unchanged, as soon as the newer release serves.
- This release may be rolled back under *Rollback to the previous release*. Under G-3 A the
  archived state restricts no one's reading. The release that adds it adds change operations, and
  a rollback removes them rather than widening them. So it adds or tightens no access rule in the
  sense of that paragraph. A rollback to v0.1.2 (head `0004`) keeps the database at `0008`, a
  descendant of `0004`, as the EKO-3-03 addendum states for `0007`. **If gate 1 had chosen G-3 B**
  (an archived customer answered as missing to everyone), the archived state *would be* an access
  rule, and this release could not be rolled back.
- **New control ADR-0004-C37** (below) is the carrier: it shows the step and the rollback effect
  against the published previous release, whose head may be `0004` (v0.1.2) or, if a release is
  published from `main` before EKO-3-05 merges, `0007`. Both are below `0008`, so the carrier runs.

### 4. A change refused by the NIP unique constraint (ADR-0003; extends the EKO-3-03 addendum to changes)

- An edit whose Polish NIP another customer holds is refused by the database's unique constraint
  on `customer.nip`, exactly as EKO-3-03 refuses a create: never by a read before the write, the
  violation recognised by the constraint's name, the same HTTP status (409), the same body, a
  `rep` without `manager` answered byte-equal whoever owns the holder (the caller included), and
  the holder's identifier (`existing_customer_id`) added only for a caller whose visibility scope
  is all records, read after the refusal by a `data` function that takes that scope and applies it
  in its statement. The `domain` function that builds scopes decides who gets it, from the caller
  value. No function is added to the closed system-read list.
- **Keeping the customer's own NIP is not a conflict.** The constraint compares a row with other
  rows only, so an edit that sends the NIP the edited customer already holds passes it. No
  application rule is added for it.
- **A caller holding `manager` without `rep`** may edit (section 1), so unlike EKO-3-03's create
  it reaches the constraint. Its scope is all records, so its refusal carries the reference. That
  is the one difference from the create, and it follows from the two rules as written.
- **Order of the answers on an edit**, each judged only when the ones before it passed:
  1. the access decision (401, the `Origin` 403, the role 403), before the body is read
     (ADR-0003-C34);
  2. body validation (422), on the body alone, before any record is read;
  3. the scope: a record outside it, or nowhere, gets 404 `not found`;
  4. the state: an archived record gets 409 `{"detail":"restore it first"}`;
  5. the NIP constraint: 409 with the NIP-taken body (and the reference, as above).
  Steps 3 to 5 are decided by the one scoped, state-conditioned statement that writes the row: a
  row outside the scope or archived is not written, so the constraint is never reached for it,
  and a NIP-taken answer never tells a caller anything about a record it cannot change.
- The refused edit stores nothing: the customer row and its contacts are as before, in the same
  transaction rule as section 1. Of two overlapping writes (edit and edit, or edit and create)
  setting one NIP, one is stored and the other gets the NIP-taken refusal, never a 503.
- **An archived customer keeps holding its NIP** (ADR-0002 *NIP uniqueness* as written: the
  constraint is on `nip`, with no condition on the state; ADR-0005 *Archiving*: archiving keeps all
  of its personal data). A create or edit to an archived customer's NIP is refused, and the
  manager's reference may name an archived customer, which stays readable by identifier (G-3 A).
  A restore never meets the constraint, because the NIP was held throughout.
- **New control ADR-0003-C40** (below). EKO-3-03's ADR-0003-C38 and its addendum text are
  unchanged; this section extends their rule from a create to a change, and is not an edit of
  them.

## Options considered

### Q-A, who may change a customer

| Option | Cost | Closes off |
|---|---|---|
| **A. The visibility scope; manager any, rep own; creation keeps needing `rep`** (recommended; matches ACC-5, C-2 A, C-3 A) | A `manager` without `rep` may change customers it could not create; one more control (C39). | Nothing. |
| B. The creation scope (needs `rep`) | A manager without `rep` cannot edit, which breaks ACC-5 for that account. | ACC-5 for a manager without `rep`. |
| C. No addendum; rely on C33's by-identifier clause and the task's tests | None now. | A written rule for the next change operation (reassignment, erasure): each would decide it in code. |

### Q-B, the archived state and the default list

| Option | Cost | Closes off |
|---|---|---|
| **A. State is a filter within the scope; default `active`; C33 restated** (recommended; with G-2 A) | A declared deviation (a restated control); every unfiltered-list assertion of earlier tasks that names its exact items is re-read under the new default. | Folding a record value into a scope. |
| B. State is a filter; the unfiltered list shows every state (G-2 B); C33 unchanged | No deviation. Every client that forgets the filter shows archived customers as active, and the SPA must send `active` on every list. | A safe default for the next list client. |
| C. State folded into the scope | No restatement of C33's list clause, but `archived` and `both` widen a scope by a request value, against the addendum of 2026-11-20 and C36's intent. | "A request value never becomes a scope" as a structural rule. |

### Q-C, the rollback over the archived state

| Option | Cost | Closes off |
|---|---|---|
| **A. Rollback allowed; the older release lists archived customers as active, announced with the rollback; carrier C37 against the published previous release** (recommended) | One more composition test on the previous release, with a skip once a release holding `0008` is published (a recorded exception, as EKO-3-02/weakening-2); runtime CI time. | Nothing. |
| B. Rollback allowed; the effect proven only by an SQL simulation of the previous release's statements (the EKO-3-08 precedent, `test_eko308_qa_expand_only.py`) | Cheaper, never skips; it does not run the previous image, so a statement the old code builds differently is not seen. | Proof on the real previous image. |
| C. Rollback allowed; the effect stated, not proven | None now; a named residual in the capability register. | Any evidence that the older release survives archived rows. |
| D. Treat the release as not rollback-able (going back is a restore) | Every failed deployment of this release costs a restore and the loss of changes since the backup. | A cheap rollback for a release that restricts no reading. |

### Q-D, how the NIP refusal on a change is recorded

| Option | Cost | Closes off |
|---|---|---|
| **A. A section of this addendum and a new control ADR-0003-C40; EKO-3-03's text and C38 untouched** (recommended) | One more control and capability row. | Nothing. |
| B. Widen ADR-0003-C38's criterion to cover a change | One control fewer, but it rewrites another task's approved draft before its gate 3 appends it, and C38's "a caller holding `manager` without `rep` gets 403" would become false for an edit. | A clean trail from each control to the task that proved it. |
| C. Fold it into ADR-0003-C39 | One control fewer; C39 then mixes who may change with what a refused change says. | Tracking the two halves separately in the capability register. |

### Q-E, whether an archived customer keeps holding its NIP

Both Stories deferred this to the other: EKO-3-05's out-of-scope list says "closes at EKO-3-03",
EKO-3-03's says "archived-NIP reservation (EKO-3-05)". The constraint EKO-3-03 shipped decides it
de facto; this records it.

| Option | Cost | Closes off |
|---|---|---|
| **A. Yes: the constraint stays unconditional; an archived customer's NIP refuses a create or edit, and the manager's reference may name an archived customer** (recommended; ADR-0002 *NIP uniqueness* and ADR-0005 *Archiving* as written; CUS-6 says "unique across the company" with no state) | No schema change. A rep who meets an archived holder must ask the manager, who restores or edits it. | Re-using a NIP of a customer no longer served without the manager. |
| B. No: replace the constraint by a unique index on active rows only | A second contract step on a populated table, an ADR-0002 addendum (uniqueness no longer company-wide), and a restore that can now collide, so restore needs its own NIP refusal; EKO-3-03's C38 tests change. | A restore that always succeeds. |

### Q-F, two 409 answers on one operation

| Option | Cost | Closes off |
|---|---|---|
| **A. The edit declares its 409 with EKO-3-03's `NipTakenProblem` schema (`detail` required, `existing_customer_id` optional and never `null`); `{"detail":"restore it first"}` is a valid body of it; the SPA tells the two apart by the exact `detail` text and treats any other 409 as a generic failure** (recommended) | The schema name reads as NIP-only. The SPA compares `detail` on the edit, which the create path does not do. | Nothing. |
| B. Declare `anyOf` of `Problem` and `NipTakenProblem` on the edit's 409 | Exact, but needs a hand-written response schema, and the frontend contract check (row 59) is not shown to read `anyOf`. | — |
| C. Move restore-first to another status | Reopens D-2 S-2 A. | The decision already taken. |

## Addendum text — ADR-0003

> ### <acceptance date> — Changing a customer; a change refused by the NIP unique constraint; the archived state is a filter, never a scope; ADR-0003-C33 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-05, Issue #253).
>
> **What it adds.** The addendum of 2026-11-17 decides who reads and who creates a customer, not
> who changes one, and the EKO-3-03 addendum (C38) decides what a create refused by the unique
> constraint on `customer.nip` tells its caller, not what a refused change tells it. From this
> date:
>
> - Editing, archiving and restoring a customer take the visibility scope: a caller holding
>   `manager` changes every customer, with or without `rep`; a caller holding `rep` without
>   `manager` only those it owns. Creation still needs `rep`. A change never sets or alters the
>   owner; changing it is reassignment (EKO-3-07).
> - The `data` function that writes a change applies the scope in the statement that writes the
>   row; a customer's contacts are changed only through a customer selected under the scope.
> - The archived state is a value of the record, never part of a visibility scope. A list selects
>   by state as a request value within the scope, joined by AND; with no state given it selects
>   active customers. An archived customer stays in its owner's and the manager's scope and is read
>   by identifier as an active one is.
> - For an operation naming a record by identifier, a record outside the scope gets the not-found
>   answer whatever its state; a state-dependent answer is given only inside the scope, judged on
>   the row the scoped statement selected, in the transaction that writes it.
> - An edit refused because the unique constraint on `customer.nip` refused its write is answered
>   as the EKO-3-03 addendum answers a refused create: decided by the constraint, never by a read
>   before the write; one answer for every caller holding `rep` without `manager`, whoever holds
>   the NIP, the caller included; the holder's identifier added only for a caller whose visibility
>   scope is all records, read after the refusal under that scope. A caller holding `manager`
>   without `rep` gets it too. An edit keeping the customer's own NIP is not refused. The NIP is
>   judged only for a record inside the scope and in a state that may be changed: the access
>   decision, then the body, then the scope, then the state, then the constraint. An archived
>   customer keeps holding its NIP.
>
> **What it restates.** ADR-0003-C33's list clause, as restated on 2026-11-20, reads: "every list
> given no search or filter other than the default state answers a caller holding `rep` without
> `manager` exactly the active records it owns and a caller holding `manager` all active records;
> a list given the state that selects every state, and no other search or filter, answers them
> every record it owns, and all records, respectively; a list given a search or filter answers
> exactly the records of that set which the search or filter selects, so a caller holding `rep`
> without `manager` is never answered a record it does not own, and its answer to a search or
> filter that selects only another owner's records equals its answer to one that selects no record
> at all (status, body, and headers other than `Eko-Correlation-Id`)". The rest of C33 is
> unchanged.
>
> **New controls ADR-0003-C39 and ADR-0003-C40** (table below). ADR-0003-C38 and the EKO-3-03
> addendum text are unchanged. Every other rule and control of this decision is unchanged; the
> session-exempt, role-free and non-CRM lists are unchanged, no change operation is marked
> non-CRM, and no function is added to the closed system-read list.
>
> **Why.** ACC-5 has the manager edit any rep's customer, and C-2 A and C-3 A have the manager
> archive and restore any customer. The manager may hold no `rep`, so the creation rule cannot be
> the change rule. A state folded into the scope would let a request value widen it (PRH-4). A
> state or NIP answer given before the scope would tell a rep that another rep's customer exists
> (ACC-8). CUS-6 accepts one disclosure, that a NIP is taken; an edit reaching the same constraint
> must disclose no more than a create does. C33's letter fails on a default-active list where the
> rule holds. Restating an accepted control is a declared deviation, following the addenda of
> 2026-11-20 (C33) and 2026-11-22 (C35). Approved by the human at gate 1 of EKO-3-05 on
> <acceptance date> (Issue #253).

## Addendum text — ADR-0004

> ### <acceptance date> — An expand step adding a record state, and a rollback over it
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-05, Issue #253).
>
> **What it adds.** *Expand → deploy → contract* requires the release before an expand step to
> keep working on the new schema, but does not say what that means for a column that holds a
> record's state. From this date:
>
> - A revision that adds a record state adds its column nullable, or `NOT NULL` with a constant
>   default not evaluated from the database's clock. An `INSERT` that does not name it stores the
>   state's default meaning. The revision rewrites no existing row's personal data.
> - A release that does not know a state keeps working on the expanded schema when its reads and
>   writes succeed, it changes no stored state, and it answers a record in an unknown state as the
>   state's default meaning. For the customer's archived state (EKO-3-05, revision `0008`) the
>   default is active. On a rollback to such a release it lists archived customers among the
>   active ones; that is announced with the rollback, and the stored state is unchanged when the
>   newer release serves again.
> - A record state that restricts no one's reading is not an access rule under *Rollback to the
>   previous release*. One that makes records unreadable to a caller who could read them is one,
>   and its release cannot be rolled back.
>
> **New control ADR-0004-C37** (table below). The EKO-3-03 addendum of the same release, on
> revision `0007`, is unchanged. Every other rule and control of this decision is unchanged.
>
> **Why.** EKO-3-05 adds the first record state on a table holding rows. Without this text, the
> previous release's reading of archived customers as active would be judged by each evaluator as
> either "working" or "not working" on the new schema, and a rollback over it would be decided
> during an incident. This adds a rule and restates none. Approved by the human at gate 1 of
> EKO-3-05 on <acceptance date> (Issue #253).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C39 | For every operation that changes an owned record named by identifier (at this date: edit, archive and restore of a customer): a caller holding `manager`, with or without `rep`, changes a customer of any owner; a caller holding `rep` without `manager` changes its own; administrator-only and role-less callers get 403 and nothing changes; a rep's change of another owner's customer, active or archived, and with a body whose NIP another customer holds, answers equal to the same change on a well-formed identifier that exists nowhere (status, body, headers other than `Eko-Correlation-Id`), gives no state-dependent or NIP-taken answer, and leaves that customer's row and contacts byte-identical; after any change by any caller the owner is the stored one; the scope is applied in the statement that writes the row, so removing it from that statement alone, with any scoped read kept, fails a test or is recorded as a redundant layer by QA. |
| ADR-0003-C40 | A test stores customer X with NIP N for rep A, and customers Y of rep A and Z of rep B, neither holding N. Rep A's edit of Y setting N and rep B's edit of Z setting N answer 409 with status, body and headers other than `Eko-Correlation-Id` equal to each other and to EKO-3-03's refused create, and the body holds no identifier, subject, field value, count or NIP; the edit of Y setting N by a caller holding `manager` with `rep`, and by one holding `manager` without `rep`, answers the same status and body plus `existing_customer_id`, which `GET /api/customers/<id>` resolves to X under that caller; after each refused edit the edited customer's row and contacts are byte-identical; an edit of X that keeps N succeeds; with X archived the same edit of Y is still refused; with Y archived the owner's edit setting N answers `{"detail":"restore it first"}`, and a rep's edit of another rep's customer setting N answers the missing-identifier 404; of two overlapping edits setting N on two customers, one is stored and the other gets the 409. |
| ADR-0003-C33 (restated) | As in the addendum text above: with no filter other than the default state, a rep gets exactly its own active customers and the manager all active customers; with the every-state value, exactly its own and all customers; a searched or filtered list answers only records of the caller's scope that the search or filter selects, for every state value; and a rep's answer to a search or filter that selects only another owner's records equals its answer to one that selects nothing (status, body, and headers other than `Eko-Correlation-Id`). |
| ADR-0004-C37 | Against the published previous release found as ADR-0004-C13's previous-release half finds it, while that release's head is below `0008`, the revision adding the archived state, and at least `0004`: customers and contacts stored by the previous release read back unchanged and active after the step; the previous backend keeps reading, listing and creating customers on the expanded schema, and a customer it creates reads back active from the head backend; after the head backend archives a customer and the previous backend serves again, the previous backend's by-id read and list answer that customer and change nothing of it, and when the head backend serves again the customer is still archived with every field and contact unchanged. Once that release's head is at or past `0008`, the test skips naming why; an older, missing or non-numeric head fails. |

## Open questions for gate 1

- **A-1, who may change a customer** (Q-A). A, recommended: the visibility scope, C39. B: the
  creation scope. C: no addendum. *(Decided round 1: Q-3 A; only the control number changes.)*
- **A-2, the archived state and the default list** (Q-B). A, recommended with G-2 A: a filter
  within the scope, default `active`, C33 restated. B, with G-2 B: no restatement. C: state in the
  scope (not recommended). *(Decided round 1: Q-2 A.)*
- **A-3, the rollback over the archived state** (Q-C). A, recommended: rollback allowed, C37 on
  the published previous release. B: SQL simulation only. C: stated, not proven. D: not
  rollback-able. *(Decided round 1: Q-1 A; the revision becomes `0008`.)*
- **A-4, accept these addendum texts** (A, recommended), or reject them (B). If rejected, the
  impact map of EKO-3-05 carries C33's letter conflict, the unwritten change rule, the unwritten
  NIP rule on a change and the unclassified rollback effect as named residual risks.
- **A-5, how the NIP refusal on a change is recorded** (Q-D). A, recommended: section 4 and
  C40, C38 untouched. B: widen C38. C: fold into C39.
- **A-6, whether an archived customer keeps holding its NIP** (Q-E). A, recommended: yes, the
  constraint as shipped. B: active-only uniqueness (a new contract step and ADR-0002 addendum).
- **A-7, the edit's two 409 answers** (Q-F). A, recommended: `NipTakenProblem` declared on the
  edit's 409, told apart by `detail`. B: `anyOf`. C: another status for restore-first.
- **Conditional on G-4 B** (editing an archived customer allowed; round 1 chose G-4 A): ADR-0005
  *Archiving* says archiving "keeps all of its personal data ... until the customer is restored or
  erased". Read literally, an edit of an archived customer is excluded. G-4 B would need an
  ADR-0005 addendum. No text for it is drafted here.
