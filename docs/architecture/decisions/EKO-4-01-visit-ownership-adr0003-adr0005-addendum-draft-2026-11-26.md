# EKO-4-01 — Visits as owned records: the owner rule, the customer a visit names, the scope of what a visit shows, the visit owner in the display-name reference set, and the customer reference under the erasure rule — ADR-0003 and ADR-0005 addendum draft — 2026-11-26

**Status:** Draft — pending approval
<!-- Only a human changes this status. Each "Addendum text" section below is appended to its
decision (ADR-0003, ADR-0005) as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-4-01 (Issue #268) creates the first record after the customer: the visit (VIS-1, app side).
A rep plans a visit for one of its own customers and reads its agenda; the manager reads every
visit. The visit table is created by revision `0010` on `0009_customer_archived_at`.

What the accepted decisions already settle:

- ADR-0003 addendum of 2026-11-17, *Where it is enforced*: "The owned tables at this date are the
  customer table and its contact table; a later task adding an owned record names its tables and
  owner rule at its gate 1." *Owner*: "Creating a customer requires `rep`; a caller with `manager`
  and without `rep` is refused (403)". *Outside the scope means missing*: "A record outside the
  caller's scope is answered exactly as a well-formed identifier that exists nowhere".
- ADR-0003 addendum of 2026-11-20: "`OwnedBy` and `AllRecords` are built only by the `domain`
  function of *Where it is enforced*, from the caller value."
- The EKO-3-05 addendum draft of 2026-11-24 (approved at EKO-3-05's gate 1, appended at its
  gate 3, documentation PR #267), section 2: "The archived state is a value of the record. It is
  never part of `OwnedBy` or `AllRecords`" and *Scope before state*.
- Brief ACC-5: the manager "cannot create, move or cancel another user's visits — only the visit's
  owner can". ACC-7: "A rep plans visits only for their own customers." CUS-10: on reassignment
  "past visits and notes keep their original owner".
- ADR-0005 addendum of 2026-11-22: "A column holding a staff subject is named with the suffix
  `_subject`, and the task that adds one adds it to the set in the same release and names it at
  its gate 1." ADR-0005-C21: "a copy whose subject only one column of the set holds is kept past
  180 days after the last login, for each column of the set."
- ADR-0005 *Erasure*: every visit of an erased customer "loses its customer reference, its own
  address and every customer value. A visit row is kept only stripped in that way, so that
  dashboard counts stay; whether it is kept is decided by the erasure feature."
- ADR-0006 *Visit identifiers are never reused*, "also after a restore from an earlier backup set
  ... This binds the task that creates the visit table (EKO-4-01)".

What they leave open:

1. **The visit's owner rule.** Which subject owns a visit, and whose scope a visit read applies:
   the visit's own owner or its customer's owner. Today they always coincide; after reassignment
   (CUS-10) they differ for past visits.
2. **The customer a create names.** `creation_scope` decides the owner of the new record. Nothing
   decides the scope under which a create looks up *another* owned record it refers to. Under the
   visibility scope, a caller holding `rep` and `manager` could plan a visit for another rep's
   customer, against ACC-5 and ACC-7.
3. **What a `rep`+`manager` caller is told** when it names another rep's customer. That customer
   is inside its visibility scope, so *Outside the scope means missing* does not apply to it.
4. **Customer values shown through a visit.** A visit answer that carries its customer's name or
   current address reads the customer table. ADR-0003-C35 has the scope applied "in the statement
   that selects", and does not say which table's owner the scope is compared with in such a read.
5. **The visit owner in the reference set**, and the customer reference under the erasure rule.

## Decision (proposed)

### 1. The visit is an owned record; its owner rule (ADR-0003; adds a rule)

- The visit table is an owned table. Its owner is the visit's own owner column
  (`visit.owner_subject`), the subject of the caller that planned it, taken from the caller value
  and stored as received. A request value never sets it. A visit's visibility is decided by that
  column, never by its customer's owner.
- A caller holding `rep` without `manager` reads only the visits it owns; a caller holding
  `manager` reads every visit. Reading names a visit by identifier or lists visits; a list given a
  period, or any other selecting value, applies it within the scope, joined by AND, in the same
  statement (addendum of 2026-11-20).
- Every `data` function that reads or changes rows of the visit table takes the visibility or
  creation scope as a required argument and applies it to `visit.owner_subject` in the statement
  that selects or writes the rows (ADR-0003-C35). No function is added to the closed system-read
  list. The deletion of unreferenced display-name copies, already on it, reads the visit table only
  to test whether a row refers to a subject (section 5).
- The customer's archived state narrows no visit read or list: it is a value of the customer, never
  part of a scope (EKO-3-05 section 2). The effect of archiving on visits is EKO-4-06's.

### 2. Creating a visit: the customer must be the caller's own (ADR-0003; adds a rule)

- Creating a visit takes `creation_scope`: it needs `rep`, and the owner is the caller. A caller
  holding `manager` without `rep` is refused (403) and nothing is stored.
- **The customer a create names is looked up under the caller's own-records scope**, `OwnedBy`
  the caller's subject, for every caller, a caller holding `manager` included. The visibility
  scope never decides which customer a visit may be planned for. The scope is built in
  `backend/app/domain/ownership.py` (ADR-0003-C36) and applied in the statement that selects the
  customer, in the transaction that inserts the visit.
- **Order of the answers on a create**, each judged only when the ones before it passed:
  1. the access decision (401, the `Origin` 403, the role 403), before the body is read
     (ADR-0003-C34);
  2. the body alone (422): field form, the wall-time resolution of ADR-0002 *Wall time entered by
     a user* (nonexistent, ambiguous) and the end after the start, before any record is read;
  3. `creation_scope` (403 for a caller without `rep`);
  4. the customer under the own-records scope: a customer outside it, or nowhere, answers 404
     `{"detail":"not found"}`, except as item 5 says;
  5. for a caller whose visibility scope is all records, a customer outside its own-records scope
     but inside its visibility scope answers **403 `{"detail":"not permitted"}`** *(pending gate-1
     question A-2; under A-2 B it answers the 404 of item 4)*. The `domain` function that builds
     the scopes decides who may be told this, from the caller value; a caller holding `rep`
     without `manager` never reaches the read that tells it;
  6. the customer's state, judged on the row the scoped statement selected: an archived customer
     answers 409 `{"detail":"restore it first"}` (gate-1 G-1 A).
  Every refused create stores nothing.
- The state check and the insert are in one transaction on the row the scoped statement selected.
  A concurrent archive that commits after that read can leave a visit on a just-archived customer;
  that case is carried by EKO-4-06, which decides what archiving does to visits.

### 3. Customer values shown through a visit (ADR-0003; adds a rule)

- A visit answer may carry values of its customer that the visit needs to be shown: the
  customer's identifier, name and current address (VIS-3 location rule, gate-1 G-8 A). They are
  read **under the visit's scope**: a caller reading a visit it may read gets them, whoever owns the
  customer now. No customer value is returned through a visit the caller may not read. *(Pending
  gate-1 question A-3.)*
- Until reassignment exists (EKO-3-07) the visit's owner and its customer's owner always coincide,
  so this rule discloses nothing new. EKO-3-07 decides at its gate 1 whether a past visit that keeps
  its original owner (CUS-10) still shows its customer's current name and address to that owner.

### 4. Identifiers (ADR-0006, ADR-0005; records a reading, no change)

- Visit identifiers are UUIDv4 values the application issues, with no sequence, identity or
  database default, as customer identifiers are (ADR-0005-C17, revision `0004`). A restored backup
  set restores no counter, so no identifier is issued again after a restore (ADR-0006 *Visit
  identifiers are never reused*). Every path parameter of a visit operation is that identifier
  (ADR-0005-C13), and the request-line rule of ADR-0005's addendum of 2026-11-02 holds unchanged.
  A database sequence would be restored with the backup set and issue the same values again, so it
  is excluded by ADR-0006 as written, not by this addendum. *(Pending gate-1 question A-1, which
  corrects line 21 of the Issue's Definition of done.)*

### 5. The visit owner joins the display-name reference set (ADR-0005; records the set)

- `visit.owner_subject` is a column holding a staff subject. From EKO-4-01's release the reference
  set of the ADR-0005 addendum of 2026-11-22 is exactly `customer.owner_subject` and
  `visit.owner_subject`. A display-name copy whose subject only a visit refers to is kept past
  180 days after the last login (ADR-0005-C21, "for each column of the set"). Sessions and login
  transactions are still not referring records.

### 6. The customer reference under the erasure rule (ADR-0005; records a reading)

- `visit.customer_id` is `NOT NULL`, with a foreign key to `customer.id` and no cascading action,
  so a visit always has exactly one customer (VIS-1) and no customer row can be deleted while a
  visit refers to it. *(Pending gate-1 question A-4.)*
- A visit holds no copy of a customer value (gate-1 G-8 A): its only customer values are the
  customer reference and its own address (PD-C2), the latter nullable. The strip of *Erasure* is
  then the removal of the reference and of the own address.
- *Erasure* leaves to the erasure feature whether a stripped visit row is kept. If it keeps one,
  that feature carries its own expand step that lets the reference be empty, and decides how such a
  visit is answered and counted; if it does not, it deletes the customer's visits before the
  customer. Neither is decided here.

## Options considered

### Q-A, the identifier of a visit (A-1)

| Option | Cost | Closes off |
|---|---|---|
| **A. UUIDv4 issued by the application; the C17 restore test applied to visits; the Issue's "sequence" line corrected** (recommended) | One more restore test (the `test_eko301_backup_customers.py` pattern). | Nothing: the Issue's intent, never reused, is met. |
| B. A database sequence, as the Issue's line says | A restore re-issues identifiers, against ADR-0006 as written; a decimal identifier in a path changes ADR-0005's request-line rule first. Needs deviations from ADR-0005 and ADR-0006 before code. | ADR-0006's marker rule (an event marker could match a different visit after a restore). |

### Q-B, a `rep`+`manager` caller naming another rep's customer (A-2, the Analyst's G-7)

| Option | Cost | Closes off |
|---|---|---|
| **A. 403 `not permitted`, nothing stored** (recommended) | A second read under the visibility scope after the own-scope lookup selects nothing, decided in `ownership.py`; one more contrast in C42. | Nothing. |
| B. The 404 of a missing customer | One lookup only. The answer is untrue for a caller that can open that customer by identifier, and the SPA cannot tell "not yours to plan" from "gone". | A truthful refusal for the manager. |

### Q-C, the scope of customer values shown through a visit (A-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. The visit's scope; EKO-3-07 re-decides for past visits after reassignment** (recommended) | After reassignment the old owner of a past visit would see the customer's current name and address, unless EKO-3-07 changes it. Unreachable until EKO-3-07. | Nothing now. |
| B. The visit's scope for the visit, the customer's scope for its values (values absent when the customer is outside the caller's customer scope) | Every visit answer carries optional customer values and a second scope in its statement; the K-02 planted-row case answers a visit with no customer name. | A simple visit answer. |

### Q-D, the customer reference column (A-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. `NOT NULL`, foreign key, no cascade** (recommended) | If the erasure feature keeps stripped rows, it ships an expand step and reconsiders the visit answer then. | Nothing: *Erasure* leaves keeping to that feature. |
| B. Nullable now | The database no longer enforces "exactly one customer"; only the service does. If the API declared the field nullable now, every reader handles a case nothing produces; if not, the later change makes a response property nullable, a breaking change for `openapi_compat`. | A schema-enforced VIS-1. |

## Addendum text — ADR-0003

> ### <acceptance date> — Visits as owned records; a create that names another owned record; values of a customer shown through a visit
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-4-01, Issue #268).
>
> **What it adds.** The addendum of 2026-11-17 has a later task adding an owned record name its
> tables and owner rule at its gate 1. It decides the scope of the record a create makes, not of an
> owned record that create refers to. From this date:
>
> - The visit table is an owned table. Its owner is `visit.owner_subject`, the subject of the
>   caller that planned the visit, stored as received; a request value never sets it. Visibility of
>   a visit is decided by that column, never by its customer's owner: a caller holding `rep`
>   without `manager` reads only the visits it owns, a caller holding `manager` every visit. The
>   customer's archived state narrows no visit read or list.
> - Creating a visit needs `rep` (`creation_scope`). The customer it names is looked up under
>   `OwnedBy` the caller's subject for every caller, a caller holding `manager` included; the
>   visibility scope never decides which customer a visit may be planned for.
> - On a create the answers come in this order, each judged only when the ones before it passed:
>   the access decision; the body alone (422), the wall-time resolution and the end after the
>   start included; `creation_scope` (403); the customer under the own-records scope (404 when it
>   selects nothing); for a caller whose visibility scope is all records, a customer inside that
>   scope but not its own (403 `not permitted`); the customer's archived state (409
>   `restore it first`). A refused create stores nothing. The state is judged on the row the scoped
>   statement selected, in the transaction that inserts the visit.
> - A visit answer may carry its customer's identifier, name and current address. They are read
>   under the visit's scope and returned only through a visit the caller may read. EKO-3-07 decides
>   at its gate 1 whether a past visit that keeps its original owner still shows them.
> - No function is added to the closed system-read list.
>
> **New control ADR-0003-C42** (table below). Every other rule and control of this decision is
> unchanged; the session-exempt, role-free and non-CRM lists are unchanged, and no visit operation
> is marked non-CRM.
>
> **Why.** ACC-5 forbids the manager to create another user's visits and ACC-7 limits a rep to its
> own customers; a customer looked up under the visibility scope would let a `rep`+`manager`
> account plan for any customer. CUS-10 keeps a past visit's original owner after reassignment, so
> the visit's own owner, not its customer's, decides who reads it. A state answer before the scope
> would tell a rep that another rep's customer exists (ACC-8). This adds rules and restates none,
> so it is not a deviation. Approved by the human at gate 1 of EKO-4-01 on <acceptance date>
> (Issue #268).

## Addendum text — ADR-0005

> ### <acceptance date> — The visit owner in the reference set; the visit's customer reference under *Erasure*
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-4-01, Issue #268).
>
> **What it adds.** From this date:
>
> - The reference set of the addendum of 2026-11-22 is exactly `customer.owner_subject` and
>   `visit.owner_subject`. ADR-0005-C21 holds for each of them.
> - `visit.customer_id` is `NOT NULL`, with a foreign key to the customer and no cascading action.
>   A visit holds no copy of a customer value: its customer values are that reference and its own
>   address (PD-C2), which is nullable. *Erasure*'s strip of a visit is the removal of those two.
>   Whether a stripped visit row is kept stays the erasure feature's decision; if it keeps one, it
>   carries the expand step that lets the reference be empty.
> - Visit identifiers are UUIDv4 values the application issues, with no sequence, identity or
>   database default (ADR-0006 *Visit identifiers are never reused*); the request-line rule of the
>   addendum of 2026-11-02 holds unchanged.
>
> Every rule and control of this decision is unchanged; no category is added.
>
> **Why.** The addendum of 2026-11-22 has the task that adds a `_subject` column name it at its
> gate 1; recording the set keeps its "at this date" sentence from going stale. A visit that copied
> the customer's address would hold a second customer value for *Erasure* to find. This adds no
> rule beyond the two it applies, so it is not a deviation. Approved by the human at gate 1 of
> EKO-4-01 on <acceptance date> (Issue #268).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C42 | With customers and visits of reps A and B stored: a caller holding `rep` without `manager` creates a visit only for a customer it owns, and the stored owner is its subject whatever owner the request names; naming another owner's customer, active or archived, answers equal to naming a well-formed customer identifier that exists nowhere (status, body, headers other than `Eko-Correlation-Id`) and stores nothing; naming its own archived customer answers 409 `{"detail":"restore it first"}` and stores nothing; a caller holding `manager` without `rep` gets 403 and nothing is stored; a caller holding `rep` and `manager` creates visits for its own customers, and naming another owner's customer answers 403 `{"detail":"not permitted"}` (under A-2 B: the missing-customer 404) and stores nothing; a body failing validation gets its 422 whoever owns the named customer; every visit read and list answers a caller holding `rep` without `manager` exactly the visits whose `owner_subject` is its subject, a visit it owns on a customer another subject owns included, and a caller holding `manager` every visit; another owner's visit by identifier answers equal to a well-formed visit identifier that exists nowhere; archiving a customer changes no visit list; the visit table is an owned table of the ADR-0003-C35 check, and removing the owner condition from the statement of the visit read, the visit list or the customer lookup of the create fails a test. |

## Open questions for gate 1

- **A-1, the visit identifier** (Q-A; the Analyst's G-10). A, recommended: UUIDv4, C17's restore
  test applied to visits, Issue line 21 corrected. B: a sequence, which needs ADR-0005 and
  ADR-0006 deviations first.
- **A-2, a `rep`+`manager` caller naming another rep's customer** (Q-B; the Analyst's G-7). A,
  recommended: 403 `not permitted`. B: the missing-customer 404.
- **A-3, the scope of customer values shown through a visit** (Q-C). A, recommended: the visit's
  scope, re-decided by EKO-3-07. B: the customer's scope for its values.
- **A-4, the customer reference column** (Q-D). A, recommended: `NOT NULL`, foreign key, no
  cascade. B: nullable now.
- **A-5, accept these addendum texts** (A, recommended), or reject them (B). If rejected, the
  visit table is still an owned table by the 2026-11-17 text, but the customer lookup's scope, the
  answer order and the scope of joined customer values are decided in code only, and the
  reference-set sentence of the 2026-11-22 addendum goes stale.
