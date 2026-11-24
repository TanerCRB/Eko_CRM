# EKO-3-05 — Changing a customer: who may edit, archive and restore; the archived state is a filter, never a scope; the default list; the archived-state expand step and a rollback over it — ADR-0003 and ADR-0004 addendum draft — 2026-11-24

**Status:** Draft — pending approval
<!-- Only a human changes this status. Each "Addendum text" section below is appended to its
decision (ADR-0003, ADR-0004) as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

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

- The revision that adds the archived state is an expand step under release step 1. It adds the
  column nullable, or `NOT NULL` with a constant default that the database does not evaluate from
  its clock (ADR-0002-C13). Then an `INSERT` by a release that does not name the column stores an
  **active** customer. It rewrites no existing row's personal data, and every existing customer is
  active after it.
- **A release that does not know a record state** keeps working on the expanded schema in this
  sense: its reads and writes succeed, it changes no stored state, and it answers a record in a
  state it does not know as that state's default meaning. For the archived state, the default is
  active: such a release lists archived customers among the active ones. On a rollback to such a
  release, that effect is accepted and announced with the rollback. Archived customers are
  archived again, unchanged, as soon as the newer release serves.
- This release may be rolled back under *Rollback to the previous release*. Under G-3 A the
  archived state restricts no one's reading. The release that adds it adds change operations, and
  a rollback removes them rather than widening them. So it adds or tightens no access rule in the
  sense of that paragraph. **If gate 1 chooses G-3 B** (an archived customer answered as missing
  to everyone), the archived state *is* an access rule, and this release cannot be rolled back.
  Going back past it is a restore.
- **New control ADR-0004-C37** (below) is the carrier: it shows the step and the rollback effect
  against the published previous release.

## Options considered

### Q-A, who may change a customer

| Option | Cost | Closes off |
|---|---|---|
| **A. The visibility scope; manager any, rep own; creation keeps needing `rep`** (recommended; matches ACC-5, C-2 A, C-3 A) | A `manager` without `rep` may change customers it could not create; one more control (C38). | Nothing. |
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
| **A. Rollback allowed; the older release lists archived customers as active, announced with the rollback; carrier C37 against the published previous release** (recommended) | One more composition test on the previous release, with a skip once a release holding the revision is published (a recorded exception, as EKO-3-02/weakening-2); runtime CI time. | Nothing. |
| B. Rollback allowed; the effect proven only by an SQL simulation of the previous release's statements (the EKO-3-08 precedent, `test_eko308_qa_expand_only.py`) | Cheaper, never skips; it does not run the previous image, so a statement the old code builds differently is not seen. | Proof on the real previous image. |
| C. Rollback allowed; the effect stated, not proven | None now; a named residual in the capability register. | Any evidence that the older release survives archived rows. |
| D. Treat the release as not rollback-able (going back is a restore) | Every failed deployment of this release costs a restore and the loss of changes since the backup. | A cheap rollback for a release that restricts no reading. |

## Addendum text — ADR-0003

> ### <acceptance date> — Changing a customer; the archived state is a filter, never a scope; ADR-0003-C33 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-05, Issue #253).
>
> **What it adds.** The addendum of 2026-11-17 decides who reads and who creates a customer, not
> who changes one. From this date:
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
> **New control ADR-0003-C38** (table below). Every other rule and control of this decision is
> unchanged; the session-exempt, role-free and non-CRM lists are unchanged, and no change
> operation is marked non-CRM.
>
> **Why.** ACC-5 has the manager edit any rep's customer, and C-2 A and C-3 A have the manager
> archive and restore any customer. The manager may hold no `rep`, so the creation rule cannot be
> the change rule. A state folded into the scope would let a request value widen it (PRH-4). A
> state answer given before the scope would tell a rep that another rep's customer exists
> (ACC-8). C33's letter fails on a default-active list where the rule holds. Restating an accepted
> control is a declared deviation, following the addenda of 2026-11-20 (C33) and 2026-11-22
> (C35). Approved by the human at gate 1 of EKO-3-05 on <acceptance date> (Issue #253).

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
>   state's default meaning. For the customer's archived state (EKO-3-05) the default is active.
>   On a rollback to such a release it lists archived customers among the active ones; that is
>   announced with the rollback, and the stored state is unchanged when the newer release serves
>   again.
> - A record state that restricts no one's reading is not an access rule under *Rollback to the
>   previous release*. One that makes records unreadable to a caller who could read them is one,
>   and its release cannot be rolled back.
>
> **New control ADR-0004-C37** (table below). Every other rule and control of this decision is
> unchanged.
>
> **Why.** EKO-3-05 adds the first record state on a table holding rows. Without this text, the
> previous release's reading of archived customers as active would be judged by each evaluator as
> either "working" or "not working" on the new schema, and a rollback over it would be decided
> during an incident. This adds a rule and restates none. Approved by the human at gate 1 of
> EKO-3-05 on <acceptance date> (Issue #253).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C38 | For every operation that changes an owned record named by identifier (at this date: edit, archive and restore of a customer): a caller holding `manager`, with or without `rep`, changes a customer of any owner; a caller holding `rep` without `manager` changes its own; administrator-only and role-less callers get 403 and nothing changes; a rep's change of another owner's customer, active or archived, answers equal to the same change on a well-formed identifier that exists nowhere (status, body, headers other than `Eko-Correlation-Id`), gives no state-dependent answer, and leaves that customer's row and contacts byte-identical; after any change by any caller the owner is the stored one; the scope is applied in the statement that writes the row, so removing it from that statement alone, with any scoped read kept, fails a test or is recorded as a redundant layer by QA. |
| ADR-0003-C33 (restated) | As in the addendum text above: with no filter other than the default state, a rep gets exactly its own active customers and the manager all active customers; with the every-state value, exactly its own and all customers; a searched or filtered list answers only records of the caller's scope that the search or filter selects, for every state value; and a rep's answer to a search or filter that selects only another owner's records equals its answer to one that selects nothing (status, body, and headers other than `Eko-Correlation-Id`). |
| ADR-0004-C37 | Against the published previous release found as ADR-0004-C13's previous-release half finds it, while that release's head is below the revision adding the archived state: customers and contacts stored by the previous release read back unchanged and active after the step; the previous backend keeps reading, listing and creating customers on the expanded schema, and a customer it creates reads back active from the head backend; after the head backend archives a customer and the previous backend serves again, the previous backend's by-id read and list answer that customer and change nothing of it, and when the head backend serves again the customer is still archived with every field and contact unchanged. Once that release's head is at or past the revision, the test skips naming why; an older, missing or non-numeric head fails. |

## Open questions for gate 1

- **A-1, who may change a customer** (Q-A). A, recommended: the visibility scope, C38. B: the
  creation scope. C: no addendum.
- **A-2, the archived state and the default list** (Q-B). A, recommended with G-2 A: a filter
  within the scope, default `active`, C33 restated. B, with G-2 B: no restatement. C: state in the
  scope (not recommended).
- **A-3, the rollback over the archived state** (Q-C). A, recommended: rollback allowed, C37 on
  the published previous release. B: SQL simulation only. C: stated, not proven. D: not
  rollback-able.
- **A-4, accept these addendum texts** (A, recommended), or reject them (B). If rejected, the
  impact map of EKO-3-05 carries C33's letter conflict, the unwritten change rule and the
  unclassified rollback effect as named residual risks.
- **Conditional on G-4 B** (editing an archived customer allowed): ADR-0005 *Archiving* says
  archiving "keeps all of its personal data ... until the customer is restored or erased". Read
  literally, an edit of an archived customer is excluded. G-4 B then needs an ADR-0005 addendum
  stating that *Archiving* forbids removal by archiving, not later edits. No text for it is
  drafted here, because G-4 A is recommended.
