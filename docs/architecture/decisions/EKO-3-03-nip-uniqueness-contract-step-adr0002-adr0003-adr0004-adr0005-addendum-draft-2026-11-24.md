# EKO-3-03 — The unique constraint on `nip` as the first contract step, shipped with its refusal; the duplicate-NIP refusal and the manager's reference; the migration's duplicate count — ADR-0002, ADR-0003, ADR-0004 and ADR-0005 addendum draft — 2026-11-24

**Status:** Draft — pending approval
<!-- Only a human changes this status. If accepted, each section of "Addendum text" is appended to
the decision it names as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-3-03 (Issue #252) carries CUS-6: a second customer whose Polish NIP equals a stored one is
refused company-wide, a rep learns nothing beyond "the NIP is taken", and the manager gets a way to
the existing customer. EKO-3-02 created `nip` without its unique constraint, as a declared
deviation (ADR-0002 addendum of 2026-11-19) that ends when EKO-3-03 merges. That addendum says:

> EKO-3-03's unique constraint is a contract migration (ADR-0004, *Expand → deploy → contract*):
> it ships in a later release than the code that stops writing duplicates.

ADR-0004, *Expand → deploy → contract*, release step 3, says a contract migration "ships in a later
release than its expand migration and the code change it follows, never in the same release, and
only once no running release reads or writes the old shape".

The facts at this date:

- The only published release is v0.1.2, published from `be0c5f7` at schema head `0004`
  (`docs/PLAN.md`, EKO-3-02 entry). Its code has no `nip` field: every customer it stores has
  `nip` `NULL`, so it cannot break a unique constraint on `nip`.
- Revisions `0005` (EKO-3-02, the expand that adds `nip`) and `0006` (EKO-3-08) are on `main` and
  have never been released. The code that writes `nip` (EKO-3-02) has never been released either.
- Without the constraint, only a read of the customer table across owners could stop a duplicate
  before the insert, and the ADR-0002 addendum of 2026-11-19 and ADR-0003-C35 (as restated on
  2026-11-22, with its closed system-read list) forbid that read.

So no release can "stop writing duplicates" before the constraint exists without that forbidden
read. The constraint is itself the thing that stops them. Meanwhile, the release-ordering danger
step 3 guards against (a running release that writes the shape the contract narrows) does not
exist: no published release writes `nip`.

## Decision (proposed)

### 1. The constraint and its refusal ship in one merge and one release (a declared deviation from ADR-0002 and ADR-0004)

- EKO-3-03 adds revision `0007` on `0006`. It creates one unique constraint on `customer.nip` and
  nothing else. With PostgreSQL's default, `NULL` values stay distinct, so any number of customers
  may have no Polish NIP. `foreign_tax_id` gets no constraint.
- The constraint and the code that answers a duplicate ship in the same merge, and so in the same
  release. That release also carries the unreleased expand `0005` and `0006`. This is a declared
  deviation from two texts. The first is the ADR-0002 addendum of 2026-11-19 ("it ships in a later
  release than the code that stops writing duplicates"). The second is ADR-0004 release step 3
  ("never in the same release" as its expand), for this one step only.
- The deviation holds only while the conditions behind it hold:
  - every published release, the previous one included, has a schema head that is an ancestor of
    `0005` (today v0.1.2 at `0004`);
  - so no published release writes `nip`.
  If the human publishes a release from `main` holding `0005` or `0006` but not `0007` before
  EKO-3-03 merges, this section lapses and the task returns to gate 1. The previous-release test
  (section 1, last bullet) fails in that state, so the lapse cannot pass unnoticed.
- The rest of release step 3 is kept as written. Its clause "only once no running release reads or
  writes the old shape" holds: v0.1.2 never writes `nip`.
- A rollback from the release carrying `0007` to v0.1.2 stays a rollback, not a restore. The
  database stays at `0007`, which descends from `0004`. v0.1.2's `migrate` changes nothing, and its
  backend serves and stores customers with `nip` `NULL` (ADR-0004 *Rollback to the previous
  release*).
- The previous-release half of ADR-0004-C13 for this step runs v0.1.2's images through the
  existing previous-release harness, against a database at `0007`. Its creates and reads of
  customers succeed, and a rep-shaped create through it stores `nip` `NULL`. The test fails when
  the previous release's head is `0005` or `0006` (the lapse above). It skips once the previous
  release's head is `0007` or a descendant.

### 2. Duplicates already stored: the revision refuses to run (G-2 A)

- Before its DDL, revision `0007` counts the NIP values that more than one customer holds (G-6 A).
  It does this in SQL, inside `migrate`'s one transaction, after the advisory lock and the
  timeouts. No NIP value is selected into Python.
- If the count is above zero, the revision ends the run with the existing `migrate refused: …`
  form, naming only that count and the revision. The transaction rolls back: no constraint is
  created, `alembic_version` stays where it was, and no row is changed (ADR-0004-C14). The revision
  holds no data step: it never clears, moves or deletes a NIP.
- If a duplicate were stored between the count and the DDL, the DDL fails with a unique violation
  and rolls back in the same way. That error is written as its type and location only (ADR-0005
  addendum of 2026-11-02). PostgreSQL writes no line for it (ADR-0005, PostgreSQL log values).
- The count lives in a revision under `backend/migrations/`, not in `backend/app/data/`, and serves
  no request. It is not a `data` function, so it is not a cross-owner read under ADR-0003-C35.

### 3. The refusal and the manager's reference (an addition to ADR-0003)

- The database constraint decides: a create is refused because the insert raised a unique
  violation on the `nip` constraint, never because a read before the insert found a match. The
  `data` layer recognises the violation by the constraint's name. SQLSTATE `23505` alone is not
  enough, because the contact table's one-primary index raises the same code. The `data` layer
  turns it into one domain refusal that carries no value, and reads none of the driver's message.
  Any other storage failure keeps the existing path (503 `temporarily unavailable`).
- The answer is HTTP 409. The body is `{"detail": "a customer with this NIP already exists -
  contact your manager"}`. For every caller holding `rep` without `manager` it is byte-equal
  (status, body, headers other than `Eko-Correlation-Id`), whoever owns the stored customer, the
  caller included. It names no identifier, owner, name, count or NIP.
- A caller whose visibility scope is all records (`manager`; a creator also holds `rep`) gets the
  same status and body, plus one field, `existing_customer_id`, the stored customer's identifier
  (a UUID). For any other caller the field is absent (not `null`). This is the only difference.
  - The identifier comes from a read made after the violation. That read is a `data` function
    taking the caller's visibility scope as a required parameter and applying it in its statement
    (ADR-0003-C35), and it returns the identifier only.
  - The domain function that builds scopes decides whether the caller gets a reference, from the
    caller value. The read is called only with all-records scope.
  - No function is added to the closed system-read list.
- The access decision comes first. `creation_scope` refuses a caller without `rep` (403) before
  any insert, so a manager-only caller never reaches the NIP (ADR-0003-C34). Body validation
  comes before the insert, so a malformed body probes nothing.

### 4. The migration's duplicate count in `migrate`'s output (an addition to ADR-0005)

- Under *What may appear in logs*, *What each component may write*, `migrate` may also write the
  number of NIP values held by more than one customer, in the refusal of section 2. A count is not
  a customer field value. The NIP values themselves stay under *Never written*.

## Options considered

### G-4 — How the constraint and its refusal ship

| Option | Cost | Closes off |
|---|---|---|
| **A. One merge, one release, declared deviation from the ADR-0002 addendum sentence and ADR-0004 step 3 for this step** (recommended) | Two accepted texts are restated for one step. The deviation depends on the human publishing no release from `main` holding `0005`/`0006` but not `0007` before EKO-3-03 merges, and a test enforces that. The next release carries `0005`..`0007` together. | Nothing permanently: ADR-0004 step 3 binds every later contract step as written. |
| B. The human first publishes a release from `main` (with `0005`, `0006` and EKO-3-02's code), then EKO-3-03 ships as the contract in the release after it | ADR-0004's "never in the same release" is met by the letter. But that intermediate release writes duplicate NIPs, so step 3's "only once no running release reads or writes the old shape" fails for as long as it runs. The ADR-0002 addendum sentence still fails, so a deviation is still needed. The intermediate release is not deployable to real data. It becomes the previous release: on the constrained schema its duplicate create answers 503 and stores nothing, which K-05 must also prove. | Nothing. It costs a release and a deviation, and buys no safety A lacks. |
| C. Deviate on ADR-0003-C35 instead: a system read (or a scoped-to-all read on every create) checks for a duplicate before the insert, shipped one release before the constraint | A cross-owner read on every rep's create, and an addition to the closed system-read list reached from a request path, which the restated C35 forbids (no listed function reachable from `api`). A prior read is not the concurrency arbiter, so the constraint is still needed later. Two releases, so the Story splits and K-01..K-04 cannot pass in this task. | The guarantee that no request-serving `data` function reads an owned table outside the caller's scope. |
| D. Split the Story: constraint and refusal in one task, release in between, nothing else | Same as A or B, depending on whether a release sits between them. It adds a task and no safety, because both halves must still ship together to avoid either 503s on duplicates or stored duplicates. | Nothing. |

### The refusal's status and shape

| Option | Cost | Closes off |
|---|---|---|
| **A. 409 with `{"detail": <fixed text>}` and, for an all-records caller only, `existing_customer_id`** (recommended) | A new documented response on `customer_create`, a new frontend type registered in the contract check, and a new SPA branch mapping 409 to the tax-ID field. | Nothing. It matches the existing `{"detail": "<text>"}` problem form. |
| B. 422 with one error at `["body", "tax_id"]`, type `nip_taken`, reference in `ctx` | The SPA's field mapping is reused. But a state conflict mixes with value validation, whose answers EKO-3-01/02 keep free of stored state. The 422 shape rules (type, loc, msg, ctx, bounded) would carry a record identifier in `ctx`, and a client cannot tell "malformed" from "taken" by status. | Keeping 422 a pure function of the request body. |

### The manager's reference

| Option | Cost | Closes off |
|---|---|---|
| **A. A scoped read after the violation, called only when the domain function gives the caller all-records scope** (recommended) | One more `data` function under ADR-0003-C35 as written, and a second statement on the manager's refusal path. | Nothing. |
| B. Read the identifier out of the violation | PostgreSQL's `DETAIL` carries the NIP, not the identifier. It would mean parsing a message ADR-0005 keeps out of every log, and it still needs a read. | — |
| C. Give the reference to any caller whose scope contains the stored customer (a rep's own) | The rep's answers differ for its own customer versus another rep's, so a rep learns whose the NIP is (PRH-4; K-02 mutation (b)). | The byte-equal rep refusal. |

## Addendum text

The following text is proposed for four decisions, each as a dated addendum appended in EKO-3-03's
gate-3 documentation PR. It is written for option A of each choice above.

### For ADR-0002

> ### <acceptance date> — The unique constraint on `nip`: a contract step shipped with its refusal; stored duplicates refuse the revision
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-03, Issue #252).
>
> **What it changes.** The addendum of 2026-11-19 ends: from EKO-3-03's merge, *NIP uniqueness*
> and ADR-0002-C9 hold as written, and ADR-0002-C9 as restated for the interval no longer applies.
> Its sentence "it ships in a later release than the code that stops writing duplicates" is
> replaced for this one step by: revision `0007` creates the unique constraint on `nip`, with
> `NULL` values distinct and nothing on `foreign_tax_id`, and ships in the same release as the code
> that answers a duplicate, because that code is the refusal the constraint raises and no
> published release writes `nip` (ADR-0004 addendum of the same date). Before its DDL the revision
> counts, in SQL, the NIP values held by more than one customer; when the count is above zero it
> refuses the run naming only the count, and changes nothing. No revision clears, moves or deletes
> a stored NIP. The count is part of a revision, serves no request and is not a `data` function.
>
> Every other rule and control of this decision is unchanged.
>
> **Why.** Before the constraint exists, a release can stop writing duplicates only by a read
> across owners, which ADR-0003-C35 forbids. The constraint is the only arbiter of two concurrent
> creates. A data step would need a "which customer wins" rule the brief does not give. Approved by
> the human at gate 1 of EKO-3-03 on <acceptance date> (Issue #252).

### For ADR-0004

> ### <acceptance date> — *Expand → deploy → contract*: the first contract step ships with its unreleased expand
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-03, Issue #252).
>
> **What it changes.** Release step 3's "It ships in a later release than its expand migration
> and the code change it follows, never in the same release" does not apply to revision `0007`
> (the unique constraint on `customer.nip`, ADR-0002 addendum of the same date). It ships in the
> same release as its expand `0005`, as `0006`, and as the code that writes `nip`, because:
> - none of them has been published;
> - the only published release, v0.1.2 at head `0004`, never writes `nip`, so the clause "only
>   once no running release reads or writes the old shape" holds.
> This holds only while every published release's schema head is an ancestor of `0005`. If a
> release holding `0005` or `0006` but not `0007` is published before EKO-3-03 merges, it lapses
> and the task returns to gate 1. A rollback from that release to v0.1.2 keeps the database at
> `0007` and is a rollback, not a restore. Release step 3 binds every later contract step as
> written.
>
> Every other rule and control of this decision is unchanged.
>
> **Why.** The rule keeps a contract migration from breaking a release that still writes the old
> shape. Here no release has ever written it. Publishing an intermediate release only to meet the
> letter would create such a release. Approved by the human at gate 1 of EKO-3-03 on
> <acceptance date> (Issue #252).

### For ADR-0003

> ### <acceptance date> — A create refused by a company-wide unique constraint; the reference for an all-records caller
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-03, Issue #252).
>
> **What it adds.** The addendum of 2026-11-17 decides what a caller may read, not what a refused
> write may tell it. From this date, for a create refused because the database's unique
> constraint on `customer.nip` refused its insert:
> - the refusal is decided by that constraint, never by a read made before the insert;
> - every caller holding `rep` without `manager` gets one answer, whoever owns the stored customer,
>   the caller included. It is equal in status, body and headers other than
>   `Eko-Correlation-Id`, and tells only that the value is taken;
> - a caller whose visibility scope is all records also gets the stored customer's identifier. It
>   is read after the refusal by a `data` function that takes that scope as a required parameter
>   and applies it in its statement. The `domain` function of *Where it is enforced* decides,
>   from the caller value, whether a caller gets it.
> No function is added to the closed system-read list. **New control ADR-0003-C38** (table
> below).
>
> Every other rule and control of this decision is unchanged.
>
> **Why.** A company-wide constraint necessarily tells a rep that a value exists outside its
> scope. CUS-6 accepts exactly that one fact (gate-1 G-3), so it is written down as the only
> disclosure, rather than left as an unstated exception to *Outside the scope means missing*.
> Approved by the human at gate 1 of EKO-3-03 on <acceptance date> (Issue #252).

### For ADR-0005

> ### <acceptance date> — `migrate` may write the count of duplicated NIP values
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-03, Issue #252).
>
> **What it adds.** *What each component may write*, the backend item: `migrate` may also write,
> in the refusal of the unique-constraint revision (ADR-0002 addendum of the same date), the number
> of NIP values held by more than one customer. The NIP values stay under *Never written*. Every
> other rule and control of this decision is unchanged.
>
> **Why.** The operator needs to know that stored rows block the revision before resolving them by
> hand. A count is not a customer field value, and naming the NIPs would be one. Approved by the
> human at gate 1 of EKO-3-03 on <acceptance date> (Issue #252).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C38 | A test stores a customer with NIP N for rep A. A create with N by rep B, and by rep B for B's own customer holding M, answers 409 with equal status, body and headers other than `Eko-Correlation-Id`, and the body holds no identifier, subject, field value, count or NIP. The same create by a caller holding `rep` and `manager` answers the same status and body plus `existing_customer_id`, which `GET /api/customers/<id>` resolves to the stored customer under that caller. A caller holding `manager` without `rep` gets 403 whether N is taken or not, and nothing is stored. Of two overlapping creates with N, one is stored and the other gets the 409. |
