# EKO-3-08 — The staff display-name copy: what it holds, what it may decide, which records keep it, and the retention sweep's read of owned tables — ADR-0003 and ADR-0005 addendum draft — 2026-11-22

**Status:** Draft — pending approval
<!-- Only a human changes this status. Each "Addendum text" section below is appended to its
decision (ADR-0003, ADR-0005) as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-3-08 (Issue #216) builds the display-name copy that ADR-0003 *Staff display name* option A
chose, a manager-only list of reps read from it, and `roles` on `GET /api/auth/session`, so that
the SPA can offer the manager the EKO-3-04 owner filter. The copy is the first staff record of
the application other than sessions and login transactions.

What the accepted decisions already settle:

- ADR-0003 *Staff personal data*, Application row: "a copy of the display name (given and family
  name) taken from the verified token at each login, kept after deactivation so attribution of
  past records stays readable". ADR-0005 PD-S3 lists "the display-name copy (given and family
  name)".
- ADR-0003 *Roles*: "the backend reads a caller's roles **only** from that client's role claim in
  a token it verified".
- ADR-0005 *Retention*: "**The display-name copy** is kept while at least one record in the
  application refers to the subject, and is deleted together with the last such record. A copy
  that no record refers to is deleted no later than 180 days after the subject's last login; the
  next login takes it again." ADR-0005-C9 tests it.
- ADR-0003 addendum of 2026-11-17, *Where it is enforced*: "Every `data` function that reads or
  changes rows of an owned table takes that scope as a required argument with no default ... No
  `data` function serving a request reads an owned table without it." ADR-0003-C35 checks the
  first sentence for every function under `backend/app/data/`. The addendum of 2026-11-20: "`OwnedBy`
  and `AllRecords` are built only by the `domain` function of *Where it is enforced*, from the
  caller value."

What they leave open:

1. **What else the copy holds.** The 180-day rule needs the last-login instant, and the PO's G-1 A
   needs the roles (or at least `rep`) of the last login to select the reps. Neither item is in
   ADR-0003's Application row or in ADR-0005 PD-S3, and ADR-0005 *Classifying columns* has every
   new column named against those items.
2. **What the stored roles may decide.** *Roles* binds a *caller's* roles. No text says that a
   stored copy of roles is never read as a caller's roles or into any access decision.
3. **Which records "refer to the subject".** At this date only `customer.owner_subject` holds a
   staff subject in an owned record. Sessions also hold a subject. Later tasks add visit owners,
   note and action authors and status-change authors (ADR-0005 PD-C4). Nothing says which columns
   keep a copy, so a later column can be forgotten and its author's name deleted while still
   referred to.
4. **The sweep must read an owned table without a caller.** To keep a referred-to copy, the
   retention run must ask whether any customer is owned by a subject. It runs in the worker, with
   no caller and so with no visibility scope. ADR-0003-C35's check fails on such a function, and
   building a scope value for it would break the 2026-11-20 rule ("from the caller value").
5. **How "180 days" is counted.** Session and login-transaction retention count elapsed time
   between instants; ADR-0002 computes Europe/Warsaw calendar days only for dates and day ranges.
   The copy's bound is not stated either way.
6. **"Deleted together with the last such record".** No product path deletes a customer or
   changes its owner yet (erasure is a later feature; reassignment is EKO-3-07). Whether a
   reassignment that removes a subject's last reference counts as "the last such record" being
   deleted is not said.

## Decision (proposed)

### 1. The copy's items (ADR-0003 and ADR-0005, inventory)

The copy holds, per subject, exactly: the subject identifier (stored as received and compared
byte-wise, as every staff subject is); the display name, the verified access token's `name`
claim, or none when the token carries none, stored in NFC (ADR-0002 *Polish text*); **whether the
token of that login held `rep`** (Q-1 A; under Q-1 B, the set of the three application roles the
token held); and the instant of that login. Nothing else of the token. These items are PD-S3.

### 2. Written at login, never an authority (ADR-0003)

- The copy is written only by the login callback, after every check of *Browser flow* has passed
  (transaction, `state`, `nonce`, token verification, the forbidden-claim refusal), and in the
  same database transaction as the new session. A refused callback writes nothing. A token
  refresh does not write it. One subject has one copy; a later login replaces its items.
- **The copy is never an authority.** No `Caller` is built from it; no role check, visibility
  scope, ownership decision or access answer reads it. Every operation decides from the token
  verified for that request, as *How a request is verified* and *Roles* say. The stored role item
  serves only to select the entries of the manager-only list of reps.
- The copy table is not an owned table: it is not a CRM record, and ADR-0003-C33 and C35 do not
  bind it.

### 3. The records that keep a copy (ADR-0005)

- A record refers to a subject when one of the columns of the **reference set** holds it. At this
  date the set is exactly `customer.owner_subject`. Sessions and login transactions are not
  referring records.
- A task that adds a column holding a staff subject adds it to the reference set in the same
  release, and its gate-1 impact map names it. A column holding a staff subject is named with the
  suffix `_subject` (Q-3 A), so a check can find one that is missing from the set.

### 4. The retention sweep's reference read (ADR-0003, declared deviation from ADR-0003-C35)

- A `data` function may read an owned table without a visibility scope only when it is on a
  **closed system-read list** held in the C35 check, and only to test whether a row refers to a
  subject: it returns no column of an owned table, and no module under `backend/app/api/` or
  `backend/app/auth/` reaches it. At this date the list holds one function, the deletion of copies
  past their bound that no record of the reference set refers to.
- Adding a function to the list is a gate-1 decision of the task that adds it, on the Architect's
  impact map, in the same way as a non-CRM mark (ADR-0003 addendum of 2026-11-16).
- `OwnedBy` and `AllRecords` stay built only from a caller value; no scope value is made for
  background work.

### 5. Counting the 180 days (ADR-0005)

The bound is 180 × 24 hours after the last-login instant, between UTC instants from the injected
clock (ADR-0002 *Now, today*). "No later than" includes the bound, and the worker's interval
between runs counts within it (*Retention*, preamble).

### 6. "Together with the last such record" (ADR-0005, forward)

Until a product path deletes a referring record or changes the subject a column of the reference
set holds, the clause has nothing to act on. It is forwarded to the first task that adds such a
path: EKO-3-07 (reassignment) or the permanent-erasure feature. That task's gate 1 decides whether
a copy that loses its last reference is deleted at once or falls under the 180-day bound. Until
then ADR-0005-C9 is met for its two other clauses (a copy no record refers to is deleted within
the bound; a copy a record refers to is kept), and its first clause is untested.

## Options considered

### What the copy keeps of the roles (Q-1; the PO's G-1)

| Option | Cost | Closes off |
|---|---|---|
| **A. One item: whether the login's token held `rep`** (recommended) | K-01, K-02 and K-04 read "the rep flag" where they say "roles". A role change shows in the list only after the next login (the PO's stated G-1 A cost). | Listing managers or administrators from the copy without an expand migration adding an item. |
| B. The set of the three application roles of the last login (G-1 A as worded) | `manager` and `administrator` assignments are held in the application although nothing reads them; a larger PD-S3 footprint and a larger tamper surface. | Nothing. |
| C. No role item (the PO's G-1 B or C) | B lists administrator-only and manager-only accounts, against the Story's own DoD line 2. C reads customers across owners in the request (allowed under the manager's `AllRecords` scope), lists only reps that own a customer, and gives EKO-3-07 no list of reassignment targets. | Under C, a rep with no customers in the selector. |

### How the sweep learns that a copy is referred to (Q-2)

| Option | Cost | Closes off |
|---|---|---|
| **A. A closed system-read list in `data`; ADR-0003-C35 restated** (recommended) | A declared deviation; one list entry and its check; each later entry a gate-1 item. | A system-wide read of an owned table appearing silently in `data`. |
| B. A scope value for background work built in `domain/ownership.py` | Keeps the letter of C35 and C36 but breaks the 2026-11-20 rule "from the caller value"; an `AllRecords` obtainable without a caller can reach a request path and no check tells it apart. | The meaning of a scope as "what this caller may see". |
| C. No read of the owned table: a foreign key from `customer.owner_subject` to the copy, or a reference counter kept on every write | The key needs a copy for every existing owner (a backfill of name-less copies, then a constraint old code violates, a contract migration); a counter drifts and every later referring table must maintain it. | Creating a customer for a subject that has no copy. |
| D. No copy retention in this task | ADR-0005-C9 unmet and the Story's DoD line 5 dropped; an exception-register entry. | Nothing, but staff data has no end. |

### How the reference set is kept complete (Q-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. A closed set plus a naming rule: every column whose name ends in `_subject` is in the set (ADR-0005-C20)** (recommended) | One static check; a later column named otherwise escapes it, so the naming rule is part of the decision. | Forgetting a column named by the rule. |
| B. A closed set only, named at each task's gate 1 | No check. | Nothing structurally: a forgotten column deletes a referred-to author's name after 180 days, and attribution of past records shows no name. |

### "Together with the last such record" (Q-4; the Analyst's G-5)

| Option | Cost | Closes off |
|---|---|---|
| **A. Forward it to the first task that removes a reference (EKO-3-07 or erasure)** (recommended) | ADR-0005-C9 met in part, named in the capability row's "does not prove". | Nothing. |
| B. Build it now, proven by a deletion through the data layer in a test | Code and a test for a path no product operation reaches; the reassignment reading is still open. | Nothing, but decides ahead of the task that owns the path. |

## Addendum text — ADR-0003

> ### <acceptance date> — The staff display-name copy: its items, written at login, never an authority; the retention sweep's reference read; ADR-0003-C35 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-08, Issue #216).
>
> **What it adds.** *Staff personal data* names the display-name copy but not what else it holds
> or what it may decide. From this date:
>
> - The Application row of *Staff personal data* reads, for the copy: the subject identifier; the
>   display name, the verified access token's `name` claim or none, in NFC; whether that login's
>   token held `rep`; the instant of that login. Nothing else of the token is kept in it.
> - The copy is written only by the login callback, after every check of *Browser flow* has passed,
>   in the same database transaction as the new session; a refused callback writes nothing and a
>   token refresh does not write it. One subject has one copy; a later login replaces its items.
> - The copy is never an authority. No caller value is built from it, and no role check,
>   visibility scope, ownership decision or access answer reads it. Every operation decides from
>   the token verified for that request. Its role item only selects the entries of the
>   manager-only list of reps.
> - The copy table is not an owned table.
>
> **What it restates.** The addendum of 2026-11-17, *Where it is enforced*: "Every `data` function
> that reads or changes rows of an owned table takes that scope as a required argument with no
> default" reads: "... with no default, except a function on the closed system-read list. A
> function on that list reads an owned table only to test whether a row refers to a subject,
> returns no column of an owned table, and is reached from no module under `backend/app/api/` or
> `backend/app/auth/`. At this date the list holds only the deletion of display-name copies that no
> referring record keeps (ADR-0005 addendum of the same date). Adding a function to it is a gate-1
> decision of the task that adds it, on the Architect's impact map." `OwnedBy` and `AllRecords`
> stay built only from a caller value. ADR-0003-C35 is restated (table below).
>
> **New control ADR-0003-C37.** Every other rule and control of this decision is unchanged; the
> session-exempt, role-free and non-CRM lists are unchanged.
>
> **Why.** The 180-day rule needs the last-login instant and the list of reps needs the `rep`
> role of the last login, and neither was in the inventory. A stored role that some later code
> read as a caller's role would let a database row grant a right the identity server withdrew.
> The retention run has no caller, so it cannot hold a scope, and making one for it would make
> "all records" obtainable without a caller. Restating an accepted rule and control is a declared
> deviation, following the addenda of 2026-10-28 (C4) and 2026-11-20 (C33). Approved by the human
> at gate 1 of EKO-3-08 on <acceptance date> (Issue #216).

## Addendum text — ADR-0005

> ### <acceptance date> — The display-name copy: items of PD-S3, the records that keep it, and the count of its 180 days
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-08, Issue #216).
>
> **What it adds.** From this date:
>
> - **PD-S3** also holds, as part of the display-name copy, whether the token of the subject's last
>   login held `rep`, and the instant of that login.
> - **Referring records.** A record refers to a subject when a column of the reference set holds
>   it. At this date the set is exactly `customer.owner_subject`. Sessions and login transactions
>   are not referring records. A column holding a staff subject is named with the suffix
>   `_subject`, and the task that adds one adds it to the set in the same release and names it at
>   its gate 1.
> - **The 180 days** of *Retention* for the copy are 180 × 24 hours after the last-login instant,
>   between UTC instants of the injected clock; "no later than" includes the bound, and the
>   interval between runs counts within it.
> - **"Deleted together with the last such record"** is forwarded to the first task that deletes a
>   referring record or changes the subject a column of the set holds (EKO-3-07, reassignment, or
>   the permanent-erasure feature). That task's gate 1 decides whether a copy losing its last
>   reference is deleted at once or falls under the 180-day bound. Until then ADR-0005-C9's first
>   clause is not tested.
> - The retention run writes counts only, never a subject or a name.
>
> **New control ADR-0005-C20.** This adds items and rules and restates none, so it is not a
> deviation. Every other rule and control of this decision is unchanged.
>
> **Why.** *Classifying columns* has each new column named against an item of this decision, and
> the copy needs two items PD-S3 did not list. A referring column the retention does not know
> would delete an author's name while records still show that author. Approved by the human at
> gate 1 of EKO-3-08 on <acceptance date> (Issue #216).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C35 (restated) | Every function under `backend/app/data/` that reads or changes rows of an owned table takes a visibility scope as a required parameter with no default, or is on the closed system-read list held in the check; the list in the check equals the list held in the test; a fixture function on an owned table with neither fails, a listed function that returns a column of an owned table fails, and a listed function imported by a module under `backend/app/api/` or `backend/app/auth/` fails; no module outside `backend/app/data/` refers to an owned table. |
| ADR-0003-C37 | After `alembic upgrade head` the copy table has exactly the columns of the subject, the display name, the `rep` item and the last-login instant; a refused login callback leaves it unchanged; a copy rewritten in the database to the opposite `rep` item, or to any role, changes no answer of any operation for that subject, its session read included. |
| ADR-0005-C20 | Every column in the application schema whose name ends in `_subject` is in the retention's reference set held in the code, and the set equals the list held in the test; a fixture column with that suffix outside the set fails; a copy whose subject only one column of the set holds is kept past 180 days after the last login, for each column of the set. |

## Open questions for gate 1

- **Q-1, what the copy keeps of the roles** (the PO's G-1). A, recommended: only whether the
  login's token held `rep`. B: the three-role set. C: no role item (G-1 B or C).
- **Q-2, how the sweep learns a copy is referred to.** A, recommended: a closed system-read list
  and C35 restated. B: a system scope value. C: a foreign key or a counter. D: no copy retention
  now.
- **Q-3, keeping the reference set complete.** A, recommended: the `_subject` naming rule and
  ADR-0005-C20. B: the closed set only.
- **Q-4, "together with the last such record"** (the Analyst's G-5). A, recommended: forward to
  EKO-3-07 or erasure. B: build it now.
- **Q-5, accept these addendum texts** (A, recommended), or reject them (B). If rejected, the
  copy's role item and last-login instant have no inventory entry (ADR-0005-C1 cannot name them),
  and the retention sweep cannot be built without failing ADR-0003-C35, so DoD line 5 leaves the
  task.
