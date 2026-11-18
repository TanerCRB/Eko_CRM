# EKO-3-01 — Record ownership of customers; the access decision before the request body — ADR-0003 addendum draft — 2026-11-17

**Status:** Draft — pending approval
<!-- Only a human changes this status. The section "Addendum text" is appended to ADR-0003 as a
dated addendum (date = human acceptance) in this task's gate-3 documentation PR. This file is never
itself appended to or edited inside ADR-0003's accepted text. -->

## Context

EKO-3-01 (Issue #195) adds the first CRM-data operations: create a customer with contacts, read one
by identifier, and a plain list. It is the first task that must prove the server-side ownership
rule of the brief (ACC-4, PRH-4). The human's clarifications of 2026-11-17 fix the product answers:
a rep asking for another rep's customer gets the same answer as for an identifier that exists
nowhere (C-1 A); the list holds the caller's own customers for a rep and every customer for the
manager (C-2 A); an account holding `manager` without `rep` cannot create a customer, and an
account holding both creates customers it owns (C-3 A).

What the accepted decisions already settle:

- ADR-0003 *Roles*: roles come only from the verified token; the caller passed inward is a
  `domain` value (subject and roles); `services` and `domain` never read a token, claim or session.
- ADR-0003 *Identifier the application stores*: a staff member is referred to only by the subject
  identifier, "stored as received, compared exactly (byte-wise, case-sensitive)".
- ADR-0003 addendum of 2026-11-16: "CRM-data refusal is the default" — the application-wide
  dependency refuses every operation to a caller holding neither `rep` nor `manager` unless it is
  marked non-CRM.
- ADR-0004 addendum of 2026-10-30, `eko_backup`'s read privileges: "`eko_backup` keeps
  `NOBYPASSRLS`. `pg_dump` then fails on a table with row-level security ... A task that enables
  row-level security on a table changes this addendum first."

What they leave open:

1. **Where per-record ownership is enforced.** The accepted EKO-2-02 draft says: "Rights inside
   that class (for example `manager_caller`) and per-record ownership (ACC-4/ACC-5) stay with each
   route and its feature task." That is per-route opt-in, the shape EKO-2-02 Reviewer finding R-01
   showed fails open on the first route that forgets it. No accepted text says where the rule
   lives, what a denial looks like, or how a later task (visits, notes, actions) reuses it.
2. **Whether the access decision precedes body parsing.** *How a request is verified* says: "A
   request without a session, or whose session cannot be resolved or verified, gets HTTP 401", and
   ADR-0003-C4 (as restated on 2026-10-28) fails "when a route outside that list answers a request
   without a session cookie with anything other than 401". In the FastAPI version locked in
   `backend/uv.lock`, a route with a JSON body parameter reads and decodes the body **before** it
   solves any dependency (`fastapi/routing.py`, `get_request_handler`: `request.json()` and the
   `json_invalid` `RequestValidationError` come before `solve_dependencies`). The application-wide
   access dependency is a dependency. So on the first route with a body, a request whose body is
   not valid JSON is answered 422 without a session, with a foreign `Origin` and for an
   administrator-only caller, where ADR-0003 says 401 or 403. Today no route has a body, so this
   has never been observable.

## Decision (proposed)

### 1. The ownership rule for customers

- **Owner.** Every customer has exactly one owner: the subject identifier of the caller that
  created it, taken from the `domain` caller value and stored as received (ADR-0003 *Identifier
  the application stores*). A request value never sets or changes it. The owner column is not
  nullable and compares byte-wise.
- **Create.** Creating a customer requires the `rep` role. A caller holding `manager` without
  `rep` is refused (403) and nothing is stored (C-3 A).
- **Read.** A caller holding `rep` without `manager` reads only customers it owns, by identifier
  and in any list. A caller holding `manager` reads every customer (ACC-4, read half). Roles are
  combined as *Roles* says, so `rep` plus `manager` reads every customer.
- **A customer's contacts** belong to that customer and are reached only through it; they carry no
  owner of their own.
- **Not decided here:** editing, archiving, reassignment (CUS-10) and the manager's edit rights
  (ACC-5). Each is decided by its own task, under section 2.

### 2. Where ownership is enforced

- **In `services`, through one visibility scope.** The rule of section 1 is one pure function in
  `domain` that turns the caller value into a visibility scope (all records, or the records of one
  subject) and decides whether the caller may create. Every `services` use case on customers
  receives the caller value and obtains the scope only from that function.
- **Every `data` function that reads or changes rows of an owned table takes the scope as a
  required argument, with no default, and applies it in the same statement that selects by
  identifier.** No `data` function serving a request reads an owned table without a scope. A
  record outside the scope is therefore never loaded, so there is no "found, then denied" branch.
- **`api` decides nothing about ownership.** A route handler passes the caller value to the
  service. No route dependency, route attribute or per-route check carries the rule, so a new
  route cannot opt out by omission; it can reach owned rows only through scoped `data` functions.
- **Owned tables** at this addendum's date are the customer table and its contact table. A later
  task that adds an owned record (visits, notes, actions) names its tables and its owner rule at
  its gate 1, on the Architect's impact map, and uses this mechanism.
- **No row-level security.** PostgreSQL row-level security is not used for ownership: it would
  break `backup` (ADR-0004 addendum of 2026-10-30) and need a per-transaction setting carrying the
  caller on the one application role.

### 3. The answer to a record outside the scope

- An operation that names a record by identifier answers a record outside the caller's scope
  **exactly as it answers a well-formed identifier that exists nowhere**: the same status (404),
  the same body, and the same headers other than `Eko-Correlation-Id`. It carries no field of the
  record and does not reveal that it exists (C-1 A).
- A malformed identifier may be refused on its own terms (422). That answer depends only on the
  identifier's form, never on any record.
- The role gate keeps its place before this: an administrator-only or role-less caller gets the
  gate's 403 and no record is looked up (addendum of 2026-11-16).

### 4. The access decision comes before the request body

- **Option A (recommended, no deviation).** For every operation, the answers of the
  application-wide access dependency (401, 503, the `Origin` refusal, the role refusals) are given
  whatever the request body holds, a body that is not valid JSON included. A request that the
  dependency refuses is never answered 422 or 400. This is enforced for every route by default,
  not per route, and proven by control ADR-0003-C34.
- **Option B (a declared deviation).** A body that is not valid JSON is answered 422 before the
  access decision, on every route that accepts a body. The 422 carries only the decode position
  and message, reads and changes nothing, and stores nothing. *How a request is verified*,
  ADR-0003-C4 and ADR-0003-C5 are restated to exclude that case.

## Options considered

### Where ownership is enforced

| Option | Cost | Closes off |
|---|---|---|
| **A. Scope from a `domain` function, required by every `data` function on an owned table, applied in the selecting statement** (recommended) | Every `data` function on an owned table carries the scope argument; a static control (C35) must keep the "no unscoped function" property. | A route serving another rep's record because its author forgot a check. |
| B. A per-route dependency in `auth` or `api` (`owned_customer`) | Each route must remember it: R-01's failure mode. `services` cannot raise `auth`'s refusals (layer row `services`: must not depend on `auth`). | Nothing structurally; the next route that forgets it fails open. |
| C. PostgreSQL row-level security with a per-transaction caller setting | A change to ADR-0004 first (`backup` fails on such tables); the caller's subject travels into the database session; the manager branch becomes a policy. | Keeping `backup` and the application on plain privileges. |
| D. Load, then compare the owner in the service | A "found, then denied" branch: the not-visible and the missing answer come from two code paths, which C-1 A requires to be indistinguishable. | Nothing, but makes C-1 depend on two branches staying identical. |

### The answer to a record outside the scope

| Option | Cost | Closes off |
|---|---|---|
| **A. Exactly the missing-identifier answer (404)** (the human's C-1 A) | A rep cannot tell "not yours" from "does not exist". | Nothing. |
| B. 403 for a record that exists but is not visible | Discloses that the identifier exists. | Rejected by C-1 A. |

### Access decision before the body

| Option | Cost | Closes off |
|---|---|---|
| **A. Access answers first, whatever the body** (recommended) | A mechanism in the application (not per route) so FastAPI's body decoding cannot answer first, and a walk test over every body-accepting operation. | Nothing. |
| B. Accept 422 for an undecodable body before access, as a declared deviation | Without a session, a caller can tell operations that take a body from those that do not, and reach FastAPI's body decoder; three rules of this decision gain an exception. | An access answer that does not depend on the body. |

## Addendum text

The following is the text proposed for ADR-0003 as a dated addendum, appended in the gate-3
documentation PR of EKO-3-01. It is written for option A of each question; another choice
changes the bullet named.

> ### <acceptance date> — Record ownership of customers; the access decision before the request body
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-01, Issue #195).
>
> **What it adds.** *Roles* and the addendum of 2026-11-16 decide who may reach CRM data at all,
> but not which records a caller may reach, nor where that rule is enforced. From this date:
>
> - **Owner.** Every customer has one owner, the subject identifier of the caller that created it,
>   taken from the caller value and stored as received. A request value never sets it. Creating a
>   customer requires `rep`; a caller with `manager` and without `rep` is refused (403) and nothing
>   is stored. A caller without `manager` reads only customers it owns; a caller with `manager`
>   reads every customer. A customer's contacts are reached only through it.
> - **Where it is enforced.** One `domain` function turns the caller value into a visibility scope
>   and decides creation. Every `data` function that reads or changes rows of an owned table takes
>   that scope as a required argument with no default and applies it in the statement that selects
>   by identifier. No `data` function serving a request reads an owned table without it. `api`
>   passes the caller value inward and decides nothing about ownership. Row-level security is not
>   used. The owned tables at this date are the customer table and its contact table; a later task
>   adding an owned record names its tables and owner rule at its gate 1.
> - **Outside the scope means missing.** A record outside the caller's scope is answered exactly
>   as a well-formed identifier that exists nowhere: the same status, body and headers other than
>   `Eko-Correlation-Id`. A malformed identifier may be refused on its own terms.
> - **Access first.** For every operation, the access dependency's answers (401, 503, the `Origin`
>   refusal, the role refusals) are given whatever the request body holds, a body that is not valid
>   JSON included; a request the dependency refuses is never answered 422 or 400.
> - **New controls ADR-0003-C33, C34 and C35** (table below).
>
> Every other rule and control of this decision is unchanged. The session-exempt, role-free and
> non-CRM lists are unchanged; no customer operation is marked non-CRM.
>
> **Why.** The brief makes the ownership rule a server-side guarantee (ACC-4, PRH-4). A rule that
> each route must remember fails open on the first route that forgets it (EKO-2-02 Reviewer
> finding R-01), and a denial computed after the record was loaded makes "not yours" and "missing"
> depend on two branches staying identical. FastAPI decodes a JSON body before it solves the
> access dependency, so without the access-first rule the first route with a body would answer an
> unauthenticated request 422 against *How a request is verified*. This adds rules and controls
> and restates none, so it is not a deviation. Approved by the human at gate 1 of EKO-3-01 on
> <acceptance date> (Issue #195).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C33 | For every operation that names an owned record by identifier, a caller holding `rep` without `manager` that does not own the record gets an answer equal to the answer for a well-formed identifier that exists nowhere (status, body, and headers other than `Eko-Correlation-Id`), containing no field value of the record, while its owner and a caller holding `manager` get the record; every list answers a caller holding `rep` without `manager` exactly the records it owns and a caller holding `manager` all of them; a create stores the caller's subject as owner whatever owner the request names, and a caller holding `manager` without `rep` is refused and stores nothing. |
| ADR-0003-C34 | A test walking every API operation that accepts a request body sends, without a session cookie, with a foreign `Origin`, with a role-less session and with an administrator-only session, a body that is not valid JSON and a body that fails validation; each answer equals the answer the same request gets with a valid body (401, 403 `origin refused`, 403 `not permitted`), and nothing is stored. |
| ADR-0003-C35 | Every function under `backend/app/data/` that reads or changes rows of an owned table takes a visibility scope as a required parameter with no default; a fixture function on an owned table without one fails the check, and no module outside `backend/app/data/` refers to an owned table. |

## Open questions for gate 1

- **O-1, where ownership is enforced** (section 2). A, recommended: scoped `data` access, the
  scope built in `domain`. B: a per-route dependency. C: row-level security (needs an ADR-0004
  addendum first). D: load-then-compare in the service.
- **O-2, access before the body** (section 4). A, recommended: access answers first on every
  route, proven by C34. B: accept 422 for an undecodable body before access, as a declared
  deviation from *How a request is verified*, C4 and C5; this draft's addendum text then gains a
  restating bullet instead of "Access first", and C34 is dropped.
- **O-3, accept this addendum text** (A, recommended), or reject it (B). If rejected, ownership is
  enforced per route as the EKO-2-02 draft left it, the impact map of EKO-3-01 names that as a
  residual risk, and O-2 still needs an answer, since C4's letter fails on the first body route.
