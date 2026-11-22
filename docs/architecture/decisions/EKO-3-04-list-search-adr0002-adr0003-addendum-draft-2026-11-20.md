# EKO-3-04 — Case-insensitive substring search; a list narrowed within the visibility scope — ADR-0002 and ADR-0003 addendum draft — 2026-11-20

**Status:** Draft — pending approval
<!-- Only a human changes this status. Each "Addendum text" section below is appended to its
decision (ADR-0002, ADR-0003) as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-3-04 (Issue #215) adds a text query `q` and an owner filter `owner` to `GET /api/customers`.
The query matches a customer's name, town (EKO-3-02, #208) or a contact value, ignoring case
(ACC-4, PRH-4, ACC-8). It is the first operation where a request value narrows a list of owned
records and the first operation that compares text by substring while ignoring case.

What the accepted decisions already settle:

- ADR-0002 *Polish text, case-insensitive comparison, NIP uniqueness*: text is stored in NFC;
  "**Case-insensitive equality does not depend on the ICU collation.** Where a rule compares text
  ignoring case and edge spaces (CUS-7, name in the same town), the application computes a
  comparison key with one domain function (NFC, trim of leading and trailing whitespace, Unicode
  case folding) and the `data` layer stores it beside the displayed value and indexes it."
- ADR-0003 addendum of 2026-11-17, *Where it is enforced*: "One `domain` function turns the caller
  value into a visibility scope ... Every `data` function that reads or changes rows of an owned
  table takes that scope as a required argument with no default and applies it in the statement
  that selects by identifier."
- ADR-0005 *What may appear in logs* and *The user's browser* (query strings never logged; a
  search term never in the SPA's location). Already proven for every component (capability rows
  17 and 50). This draft changes nothing in ADR-0005.

What they leave open:

1. **Substring search that ignores case.** ADR-0002 decides case-insensitive *equality* only. Its
   mechanism, a stored whole-value key with a byte-wise index, does not answer a substring match.
   The columns the search reads also have different collations. `customer.name` and (EKO-3-02)
   `customer.town` use the database default, ICU `pl-PL`. `customer_contact.value` is
   `COLLATE "C"`. So an `ILIKE` or `lower()` in the statement folds case through ICU on two fields
   and only for ASCII letters on the third.
2. **A list narrowed by request values.** ADR-0003-C33 reads: "every list answers a caller holding
   `rep` without `manager` exactly the records it owns and a caller holding `manager` all of
   them". A searched or owner-filtered list answers a subset, so it fails C33 as worded even when
   the scope is kept. Also, no accepted text says what a request value that names an owner may do.
   It is the first such value, since a create ignores any owner it names.

## Decision (proposed)

### 1. Case-insensitive substring search (ADR-0002)

- **A search term** is the query as sent, with leading and trailing whitespace removed, in NFC
  (G-4 A). A term holding U+0000 or a lone surrogate is refused on its form. One `domain` function
  produces it, and its refusal message never repeats the value (ADR-0005).
- **Folding happens in the statement, on PostgreSQL's builtin provider, never on ICU or on a
  column's collation.** Both the searched value and the term are folded with PostgreSQL 18's
  `casefold()` under the builtin-provider collation `pg_unicode_fast`. A field matches when its
  folded value contains the folded term as a substring. The result is the same for `name`, `town`
  and a contact value whatever their declared collation. It does not change when the ICU library
  of the image changes. It changes only with a PostgreSQL major version, which is already recorded
  as an addendum to this decision (*Engine, migration tool, data access*).
- **Literal matching.** The term reaches the statement only as a bound parameter. Before binding,
  the `data` layer escapes the pattern characters `%`, `_` and the escape character itself, and
  the statement names its escape character explicitly. No part of the term is ever statement text.
- **No index and no schema change.** At the brief's scale (about ten users, a few thousand
  customers; ADR-0002 *Context*) the search reads the caller's scope sequentially. No extension
  (`pg_trgm`) and no expression index is added. An index, or a stored search key, is a later
  addendum when a measured list makes it necessary.
- **Precondition.** If the pinned image (`postgres:18.6-trixie`) does not provide `casefold()` or
  `pg_unicode_fast`, the implementing task stops and returns here before it falls back to any
  other folding.
- This adds a rule for a case that *Polish text* does not resolve, and restates none.
  Case-insensitive equality (CUS-7) keeps its `_match_key` mechanism unchanged.

### 2. A list narrowed within the visibility scope (ADR-0003)

- **The scope comes only from the caller.** `OwnedBy` and `AllRecords` values are built only by
  the `domain` function of *Where it is enforced*, from the caller value. A request value never
  becomes a visibility scope.
- **A search or filter only narrows.** A list operation may take request values (a search term,
  an owner filter) that select records *within* the scope. The `data` function applies them in the
  same statement as the scope, joined to it by AND, so a record outside the scope is never loaded,
  whatever the values name.
- **An owner filter** names a subject, compared byte-wise and stored as received (*Identifier the
  application stores*), with no trimming, case folding or normalisation. It is a value of 1 to 255
  characters, each in U+0021..U+007E (the OpenID Connect bound on `sub`). Outside that form it is
  refused (422) on its form alone. The refusal does not depend on whether a staff member or a
  record with that subject exists. For a caller holding `rep` without `manager`, a well-formed
  owner filter gives the scope intersected with the filter. So the rep's own subject gives the
  rep's own records, and any other subject, existing or not, gives the answer of a search that
  matches nothing (G-3 A).
- **ADR-0003-C33 is restated** (below), because its letter fails on a narrowed list where the
  rule holds. Restating an accepted control is a declared deviation.
- **New control ADR-0003-C36** keeps the first bullet static.

## Options considered

### How case is ignored in a substring search (Q-1)

| Option | Cost | Closes off |
|---|---|---|
| **A. `casefold()` under the builtin collation `pg_unicode_fast` on both sides, in the statement** (recommended) | Every search reads and folds the scoped rows (sequential); the implementing task must confirm both names exist on 18.6 first. Unicode tables move with the PostgreSQL major version. | Nothing: an index or a stored key can still be added by addendum. |
| B. Stored `_search_key` columns (NFC, trim, Unicode case folding by the domain function), `COLLATE "C"`, matched with `LIKE` on the folded term | A migration (expand, backfill, contract under ADR-0002 *Versioned migrations*), a key kept current on every write path (create now, edit later), ADR-0005-C1 classification and erasure of each key (*Erasure*); partly anticipates EKO-3-03's CUS-7 keys. | Nothing, but it pulls schema work into a task that otherwise needs none. |
| C. `ILIKE` / `lower()` on the columns as declared | Folding follows each column's collation: ICU on `name`/`town` (Polish letters fold), ASCII-only on `customer_contact.value` (`COLLATE "C"`). The result can change with an ICU upgrade without any index rebuild noticing. | One folding rule across the three fields; ADR-0002's independence from ICU for case. |

### Index (Q-2)

| Option | Cost | Closes off |
|---|---|---|
| **A. None at this scale** (recommended) | A sequential read of the caller's scope per search; no performance proof (the Analyst's "do not prove"). | Nothing. |
| B. `pg_trgm` GIN index on the folded expressions | `CREATE EXTENSION` in a migration under the application role (privileges of ADR-0004-C28 to be checked), the extension in every backup set and restore, a migration under expand → deploy → contract. | Keeping the schema free of extensions. |

### The owner filter's value (Q-3, the Analyst's G-6 owner bound)

| Option | Cost | Closes off |
|---|---|---|
| **A. 1..255 printable ASCII characters, byte-wise, else 422 on form only** (recommended) | One more refusal rule to test (K-06). | A subject outside the OIDC bound, which Keycloak never issues. |
| B. Canonical UUID only | Ties the API to Keycloak's present `sub` form, which ADR-0003 does not fix ("stored as received"). | A future identity server with non-UUID subjects, without changing the API. |
| C. Only the raw cap of the query (4 × 254), no character rule | NUL and control characters reach the driver: a 503 (storage error) instead of a 422 or an empty list. | Nothing, but costs a failure mode. |

### Where the narrowing rule lives (Q-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. Restate C33 and add C36 (static: scope types built only in `domain/ownership.py`)** (recommended) | A declared deviation (a restated control) and one static check in `backend/tests/support/ownership_checks.py`. | A route or service that turns a request's owner into a scope, caught statically and not only by K-03's behaviour. |
| B. Restate C33 only | None beyond the restatement. | Nothing structurally; the "filter replaces the scope" mutation is caught by K-03's tests only. |
| C. No change; read C33's "every list" as the unfiltered list | None now. | A control whose letter fails on every searched list: the Invariant Guardian or Reviewer would have to judge it by interpretation, against this repository's precedent of restating such controls. |

## Addendum text — ADR-0002

> ### <acceptance date> — Case-insensitive substring search
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-04, Issue #215).
>
> **What it adds.** *Polish text, case-insensitive comparison, NIP uniqueness* decides
> case-insensitive equality only. From this date, a search that matches text by substring
> ignoring case:
>
> - takes a search term made by one `domain` function: the query trimmed of leading and trailing
>   whitespace, in NFC; a term holding U+0000 or a lone surrogate is refused on its form, with a
>   message that never repeats it;
> - folds both the searched value and the term in the statement with `casefold()` under the
>   builtin-provider collation `pg_unicode_fast`, never through ICU or a column's own collation;
>   a value matches when its folded form contains the folded term;
> - binds the term as a parameter, escapes `%`, `_` and the escape character before binding, and
>   names its escape character in the statement;
> - adds no index, no extension and no stored key; one is added by a later addendum when a measured
>   list requires it.
>
> If the pinned image provides neither `casefold()` nor `pg_unicode_fast`, the implementing task
> stops and the change returns here. Case-insensitive equality (CUS-7) and its `_match_key`
> mechanism are unchanged. Every other rule and control of this decision is unchanged.
>
> **New control ADR-0002-C17** (table below).
>
> **Why.** The searched columns have different collations (ICU `pl-PL` for name and town,
> `COLLATE "C"` for contact values), so folding through them would give one rule per field and
> would follow the ICU library this decision keeps case-insensitivity away from. The builtin
> provider's folding is the same for every column and moves only with a major version. This adds a
> rule and restates none, so it is not a deviation. Approved by the human at gate 1 of EKO-3-04 on
> <acceptance date> (Issue #215).

## Addendum text — ADR-0003

> ### <acceptance date> — A list narrowed within the visibility scope; ADR-0003-C33 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-04, Issue #215).
>
> **What it adds.** The addendum of 2026-11-17 decides where the visibility scope comes from and
> where it is applied, but not what a request value that narrows a list may do. From this date:
>
> - `OwnedBy` and `AllRecords` are built only by the `domain` function of *Where it is enforced*,
>   from the caller value. A request value never becomes a visibility scope.
> - A list operation may take request values (a search term, an owner filter) that select records
>   within the scope. The `data` function applies them in the same statement as the scope, joined
>   by AND.
> - An owner filter is 1 to 255 characters, each in U+0021..U+007E, compared byte-wise and never
>   trimmed, folded or normalised. Outside that form it is refused (422) on its form alone, never
>   depending on whether that subject exists. A caller holding `rep` without `manager` gets its
>   scope intersected with the filter: another subject, existing or not, gives the answer of a
>   search that matches nothing.
>
> **What it restates.** ADR-0003-C33's clause "every list answers a caller holding `rep` without
> `manager` exactly the records it owns and a caller holding `manager` all of them" reads: "every
> list given no search or filter answers a caller holding `rep` without `manager` exactly the
> records it owns and a caller holding `manager` all of them; a list given a search or filter
> answers exactly the records of that set which the search or filter selects, so a caller holding
> `rep` without `manager` is never answered a record it does not own, and its answer to a search or
> filter that selects only another owner's records equals its answer to one that selects no record
> at all (status, body, and headers other than `Eko-Correlation-Id`)". The rest of C33 is
> unchanged.
>
> **New control ADR-0003-C36** (table below). Every other rule and control of this decision is
> unchanged.
>
> **Why.** C33's letter fails on every searched or filtered list even when the scope holds. A
> filter that replaced the scope would widen a rep's list by a request value (PRH-4). Restating an
> accepted control is a declared deviation. It follows the precedent of the addenda of 2026-10-28
> (C4) and 2026-10-29 (C9). Approved by the human at gate 1 of EKO-3-04 on <acceptance date>
> (Issue #215).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0002-C17 | A test against the pinned PostgreSQL stores a customer named `ŁĄKOWA` with town `ŻÓŁTE` and an e-mail contact `ŁUKASZ.KOS@example.com`, and gets that customer for each of the queries `łąk`, `żół` and `łukasz.kos` (the last matching a `COLLATE "C"` column on a non-ASCII letter), and for `ŁĄK` given in NFD; a customer named `100% _a\b` is returned for `%`, `_` and `\` and a customer without those characters is not; a query consisting of `%` alone does not return every customer; no migration adds an index, an extension or a column for the search. |
| ADR-0003-C36 | Under `backend/app/`, an `OwnedBy` or `AllRecords` value is constructed only in `backend/app/domain/ownership.py`; a fixture module elsewhere under `backend/app/` that constructs either fails the check. |
| ADR-0003-C33 (restated) | As in the addendum text above: the unfiltered list as before; a searched or filtered list answers only records of the caller's scope that the search or filter selects, and a rep's answer to a search or filter that selects only another owner's records equals its answer to one that selects nothing (status, body, and headers other than `Eko-Correlation-Id`). |

## Open questions for gate 1

- **Q-1, how case is ignored** (section 1). A, recommended: `casefold()` under `pg_unicode_fast`
  in the statement. B: stored search keys (migration, backfill, write-path upkeep). C: `ILIKE` on
  the columns as declared (ICU on name and town, ASCII-only on contact values).
- **Q-2, an index.** A, recommended: none at this scale. B: `pg_trgm` GIN (an extension and an
  ADR-0004 privilege question).
- **Q-3, the owner filter's form.** A, recommended: 1..255 printable ASCII, byte-wise, 422 on form
  only. B: canonical UUID. C: length cap only.
- **Q-4, the narrowing rule.** A, recommended: restate C33 and add C36. B: restate C33 only.
  C: no change.
- **Q-5, accept these addendum texts** (A, recommended), or reject them (B). If rejected, the
  impact map of EKO-3-04 carries C33's letter conflict and the per-field folding as named
  residual risks.
