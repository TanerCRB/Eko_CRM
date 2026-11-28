# EKO-3-09 — What a successful save may tell its caller about other records; the likely-duplicate warning's scope and order; CUS-7 equality decided in the statement, without a stored comparison key — ADR-0002 and ADR-0003 addendum draft — 2026-11-28

**Status:** Draft — pending approval
<!-- Only a human changes this status. If accepted, each "Addendum text" section below is appended
to the decision it names as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-3-09 (Issue #254) carries CUS-7: a create or an edit whose phone or e-mail equals another
customer's, or whose name equals another customer's name in the same town, is saved and warned,
never blocked. A rep is warned only about its own customers and the manager company-wide, and no
warning may let a rep learn anything about another rep's customers (PRH-4, ACC-8).

What the accepted decisions already settle:

- ADR-0003 addendum of 2026-11-17, *Where it is enforced*: "Every `data` function that reads or
  changes rows of an owned table takes that scope as a required argument with no default and
  applies it in the statement that selects by identifier. No `data` function serving a request
  reads an owned table without it." *Outside the scope means missing*: "A record outside the
  caller's scope is answered exactly as a well-formed identifier that exists nowhere."
- ADR-0003 addendum of 2026-11-20: "`OwnedBy` and `AllRecords` are built only by the `domain`
  function of *Where it is enforced*, from the caller value. A request value never becomes a
  visibility scope."
- ADR-0003 addendum of 2026-11-24 (C38): "The addendum of 2026-11-17 decides what a caller may
  read, not what a refused write may tell it." The addendum of 2026-11-26 (C40, C41) extends that
  to a refused change and fixes the order "the access decision, then the body, then the scope, then
  the state, then the constraint".
- ADR-0003 addendum of 2026-11-26: "The archived state is a value of the record, never part of a
  visibility scope."
- ADR-0002 *Polish text, case-insensitive comparison, NIP uniqueness*: "Where a rule compares text
  ignoring case and edge spaces (CUS-7, name in the same town), the application computes a
  comparison key with one domain function (NFC, trim of leading and trailing whitespace, Unicode
  case folding) and the `data` layer stores it beside the displayed value and indexes it. The key
  is written only by that function. A comparison-key column is named with the suffix `_match_key`
  and declared `COLLATE "C"` ... CUS-7 warns and does not block, so this key carries no unique
  constraint."
- ADR-0002 addendum of 2026-11-20 (EKO-3-04, C17): a substring search "folds both the searched
  value and the term in the statement with `casefold()` under the builtin-provider collation
  `pg_unicode_fast`, never through ICU or a column's own collation", and "adds no index, no
  extension and no stored key". It also says: "Case-insensitive equality (CUS-7) and its
  `_match_key` mechanism are unchanged."
- ADR-0005 *What may appear in logs*: customer field values are never written; the backend may
  write "the record identifiers concerned".
- ADR-0004 addendum of 2026-10-29: the previous build calling the new release's API is checked by
  comparing the OpenAPI document with the previous release's; "The check stops being vacuous at the
  second release."

What they leave open:

1. **What a successful write may tell its caller about other records.** C38 and C40 decide what a
   *refused* write discloses. No text decides whether a write that succeeds may carry facts about
   other records, under which scope, or what it must never carry. CUS-7 is the first such answer.
2. **Where the warning sits in the order of answers**, and what a failure of its lookup does to a
   save that already succeeded.
3. **How CUS-7's equality is computed.** ADR-0002 binds it to a stored, indexed `_match_key`
   written by one domain function. No such column exists (revisions `0001`..`0010`), and the
   capability register shows ADR-0002-C10 and the `_match_key` half of ADR-0002-C11 never built. A
   stored key is a schema change on two populated tables, with a backfill that processes personal
   data in `migrate`, and the published previous release (v0.1.2) would write rows without it
   during a rollback, leaving them unwarned. The EKO-3-04 search already folds in the statement,
   proven on the ICU-collated name and town and on the `COLLATE "C"` contact value (ADR-0002-C17).

## Decision (proposed)

### 1. What a successful save may tell its caller about other records (ADR-0003; adds a rule)

- A successful create or change of an owned record may carry, beside the record it wrote, facts
  about **other records only inside the caller's visibility scope**: the scope of *Where it is
  enforced*, built from the caller value (a caller holding `manager` every record, with or without
  `rep`; a caller holding `rep` without `manager` only its own). The creation scope never widens or
  narrows it. The reference scope of the EKO-3-03 addendum is not used for it: that scope gives a
  rep nothing, and a rep is warned about its own customers.
- Those facts are read by a `data` function that takes that scope as a required parameter and
  applies it in its statement (ADR-0003-C35 as restated on 2026-11-22). The function returns record
  identifiers only, never another column of an owned table. No function is added to the closed
  system-read list.
- **The answer depends only on the record written and the records inside the scope.** For a caller
  holding `rep` without `manager` it is equal, in status, body and headers other than
  `Eko-Correlation-Id`, whatever records outside its scope hold, with the written record's own
  identifier the only value that may differ. It carries no count, flag, "more" marker, ordering or
  other trace of records outside the scope.
- **Absent, not empty.** When no record inside the scope qualifies, the answer carries no trace of
  the rule: it equals the answer the operation gave before this rule. The part is added only when
  something qualifies.
- **Last in the order, after the commit.** The facts are read only after the write committed, in a
  transaction of their own, so the order of the addenda of 2026-11-17, 2026-11-24 and 2026-11-26
  gains a last step: a refused write (401, 403, 413, 422, 404, the state's 409, the NIP's 409)
  carries none of it and runs no such read. *(G-4 A: a failure of that read leaves the write as
  committed and answers it without the part. Under G-4 B this bullet's second sentence changes:
  see Open questions.)*
- The archived state is not a scope here either. Whether archived records count is a selection
  inside the scope (G-1), joined by AND.

### 2. CUS-7 equality decided in the statement (ADR-0002; a declared deviation, under K-B)

- For CUS-7 (a phone, an e-mail, or a name in the same town equal to another customer's), equality
  is decided in one statement, on the stored values, with no stored comparison key:
  - a phone is compared byte-wise on its stored E.164 form (CUS-8);
  - an e-mail *(G-2 A)*, a name and a town are compared after folding both sides in the statement
    with `casefold()` under `pg_unicode_fast`, never through ICU or a column's own collation, the
    same folding the EKO-3-04 addendum fixes for search *(G-9 A)*;
  - edge whitespace and Unicode normalisation are not repeated in the statement: every stored name,
    town and e-mail is already trimmed and NFC by the domain functions that judge a request, and
    the new values are judged by the same functions before the write;
  - a customer with no town never matches by name; a record is never compared with itself.
- No migration adds a column, an index or an extension for CUS-7. One is added by a later addendum
  when a measured lookup needs it; that addendum then also decides how rows written by a release
  without the key are covered.
- *Polish text, case-insensitive comparison, NIP uniqueness*, the paragraph "Case-insensitive
  equality does not depend on the ICU collation", is restated for CUS-7 (Addendum text below).
  ADR-0002-C10 is restated to the rule as built. ADR-0002-C11 is unchanged: it holds for `nip`, and
  no `_match_key` column exists.

### 3. Unchanged

- ADR-0004: no schema change (under K-B), so no expand step and no previous-release half of
  ADR-0004-C13 for a revision. The API change is additive and is judged by the OpenAPI
  compatibility step as written.
- ADR-0005: the warning carries record identifiers (G-13 A), which the backend may log as "the
  record identifiers concerned"; every field value of either customer stays under *Never written*.
  The single-page application keeps the warning in page memory and puts no customer field value in
  its location, its history or browser storage (*The user's browser*, as written).

## Options considered

### Q-1, where the rule for a successful write's extra content is written

| Option | Cost | Closes off |
|---|---|---|
| **A. An ADR-0003 addendum: a successful write may carry facts about records inside the caller's visibility scope only, read under that scope after the commit, absent when none; new control ADR-0003-C43** (recommended) | One addendum and one control. A rep's warning about its own customers is allowed explicitly, which C38's reasoning withheld only for a refusal that had to be equal whoever owns the holder. | Nothing. |
| B. No addendum; rely on C33 and C35 as written | None now. | A written rule for the next answer of this kind (a visit-overlap warning, an import report): each would decide in code what a success may say about other records, and the evaluators would have no control to judge "no trace of out-of-scope records" against. |
| C. Allow the manager's company-wide warning through `reference_scope`, and no rep warning | No rep-side answer to prove equal. | CUS-7's rep warning; the Story's DoD lines "Rep A creating a customer with P is warned". |

### Q-2, the lookup's scope

| Option | Cost | Closes off |
|---|---|---|
| **A. The caller's visibility scope (`visibility_scope`), for create and edit alike** (recommended) | A manager holding `rep` creates under `OwnedBy` (creation scope) and is warned under `AllRecords`; two scopes in one use case, both built in `ownership.py` (C36). | Nothing. |
| B. `reference_scope` for the manager, the creation scope for a rep | Two scope paths for one rule; on edit a `manager`-only caller has no creation scope, so a third path. | One rule for create and edit. |
| C. A system read listed in `SYSTEM_READS`, filtered afterwards in `services` | An addition to the closed list reached from `api`, which the restated C35 forbids, and a filter after the read is the "denial computed after the record was loaded" the addendum of 2026-11-17 rejects. | The guarantee that no request-serving read sees out-of-scope rows. |

### Q-3 (= G-4), the lookup failing alone, in PostgreSQL terms

A statement that PostgreSQL refuses aborts its transaction: every later statement fails until
rollback. So a lookup run inside the save's transaction and refused would lose the save, and one
run after the commit cannot.

| Option | Cost | Closes off |
|---|---|---|
| **A. The lookup in a transaction of its own after the commit; a failure answers the success without the warning and logs the error's type only** (recommended; G-4 A) | A save can succeed unwarned when the lookup fails; the lookup sees committed state (it may see a concurrent save, which is no harm). Precedent: `find_by_nip` reads after the refusal "in a transaction of its own". | "Every matched save is warned" as a guarantee. |
| B. The lookup inside the save's transaction, under a savepoint released or rolled back before the commit | One snapshot for save and lookup. The save holds its row locks during the lookup; a savepoint rollback must be proven to leave the save intact for both an in-process raise and a refused statement; a lost connection still loses both. | Nothing, but it costs a harness the foundation does not yet have. |
| C. G-4 B: a lookup failure fails the save (503), the lookup inside the save's transaction so the save rolls back | The "always warned" promise; a lookup fault blocks work, against CUS-7 "warn, do not block". | Saving while the lookup is broken. |

### Q-4 (= G-2, G-9), how CUS-7 equality is computed

| Option | Cost | Closes off |
|---|---|---|
| A. ADR-0002 as written: `_match_key` columns (name with town; e-mail under G-2 A) written by one domain function, indexed, `COLLATE "C"` | An expand revision `0011` on two populated tables; a backfill of every customer and contact in `migrate`, in Python, processing personal data; the create, edit and seed paths all write the key; ADR-0004-C13's previous-release half; ADR-0005-C1 classification; a rollback to v0.1.2 writes rows with no key, so they go unwarned until a second backfill or an edit, which needs its own rule. ADR-0002-C10 and C11 become live as written. | Nothing permanently. |
| **B. Fold in the statement with `casefold()` under `pg_unicode_fast`, phone byte-wise, no stored key, no index; ADR-0002's equality paragraph restated for CUS-7** (recommended) | A declared deviation. Every save in a manager's scope compares against every customer unindexed (a few thousand rows, ADR-0002 *Context*; unmeasured). The folding is PostgreSQL's, not Python's, on both sides, so no second rule exists to drift. | An indexed lookup until a later addendum adds one. |
| C. A stored generated column `casefold(... COLLATE pg_unicode_fast)` with an index | Indexed, and the database computes it, so a previous release's rows carry it. Adding a stored generated column rewrites the table under `ACCESS EXCLUSIVE`; the key is no longer "written only by that function", so it is a deviation too; `casefold()` under a builtin collation in a generated column is unproven on the pinned image. | Nothing. |

Under B, G-9 B (simple lowercase) is a further deviation, because ADR-0002 names "Unicode case
folding" and the EKO-3-04 addendum `casefold()`; G-9 A needs none.

### Q-5 (= G-7), the shape of a warned success, and the previous release

| Option | Cost | Closes off |
|---|---|---|
| **A. The same status and the same body, plus one optional top-level field, absent (never `null` or empty) when nothing in scope matches** (recommended) | A new documented field on `customer_create`'s 201 and `customer_edit`'s 200, a new frontend type registered in the frontend contract check; the unmatched answer is byte-identical, so the pre-existing runtime suites pass unedited. | Nothing. |
| B. Wrap the customer: `{"customer": {...}, "warning": ...}` | Every client's success parsing changes; the previous SPA breaks on every save; `openapi_compat` fails it as a removed property. | A release that can be rolled out under open SPAs. |
| C. Another success status for a warned save (for example 200 vs 201 on create) | Against the DoD's "same success status"; a status branch in the SPA; `openapi_compat` judges the success status. | — |
| D. A response header | Bodies byte-identical; a header carrying record identifiers; the entry point logs no header values but the header set becomes part of the equality the rep tests mask. | A body-typed contract the frontend contract check can judge. |

### Q-6 (= G-13, new), what a warning names about a matched customer (ADR-0005)

| Option | Cost | Closes off |
|---|---|---|
| **A. Each matched customer's identifier once, and which rules matched (phone, e-mail, name and town), no field value** (recommended) | The SPA shows a link and the G-6 sentence, not the twin's name; the user opens the link to see it. | Showing the twin's name inline. |
| B. Identifier and the matched customer's name | Another rep's customer's name in a manager's write answer; allowed by the scope, but it is PD-C1 in one more answer, and the SPA must keep it out of router state, which the browser stores with its history (ADR-0005 *The user's browser*). | — |
| C. No identifier, text only (G-3 B) | The manager cannot reach the twin. | The manager's way to the twin. |

## Addendum text

The following text is proposed for two decisions, each as a dated addendum appended in EKO-3-09's
gate-3 documentation PR. It is written for option A of Q-1, Q-2, Q-3, Q-5, Q-6 and option B of
Q-4.

### For ADR-0003

> ### <acceptance date> — What a successful write may tell its caller about other records; the likely-duplicate warning
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-09, Issue #254).
>
> **What it adds.** The addenda of 2026-11-24 and 2026-11-26 decide what a refused write may tell
> its caller, not what a write that succeeds may tell it. From this date, for a create or a change
> of an owned record that succeeds:
>
> - its answer may carry, beside the record written, facts about other records only inside the
>   caller's visibility scope of *Where it is enforced*, never the creation scope or the reference
>   scope; they are read by a `data` function that takes that scope as a required parameter,
>   applies it in its statement and returns record identifiers only;
> - for a caller holding `rep` without `manager` the answer is equal, in status, body and headers
>   other than `Eko-Correlation-Id`, whatever records outside its scope hold, the written record's
>   own identifier excepted; it carries no count, flag or other trace of them;
> - when no record inside the scope qualifies, the answer equals the answer the operation gave
>   before this addendum; the added part is absent, not empty;
> - the facts are read after the write committed, in a transaction of their own; a refused write
>   carries none of them and runs no such read; a failure of that read leaves the write as
>   committed and answers it without them.
>
> The first such answer is CUS-7's likely-duplicate warning on `customer_create` and
> `customer_edit`. No function is added to the closed system-read list. **New control
> ADR-0003-C43** (table below).
>
> Every other rule and control of this decision is unchanged; ADR-0003-C38, C40 and C41 and their
> addendum texts are unchanged.
>
> **Why.** CUS-7 warns a rep about its own customers and the manager about every customer. A
> warning read under any scope but the caller's would either tell a rep about another rep's
> customer (PRH-4, ACC-8) or leave the rep unwarned. A trace of out-of-scope records (a count, a
> flag) would be the same disclosure in a smaller form. A read inside the save's transaction that
> PostgreSQL refuses aborts the save, and CUS-7 must never cost a save. Approved by the human at
> gate 1 of EKO-3-09 on <acceptance date> (Issue #254).

### For ADR-0002

> ### <acceptance date> — CUS-7 equality decided in the statement, without a stored comparison key; ADR-0002-C10 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-09, Issue #254).
>
> **What it restates.** *Polish text, case-insensitive comparison, NIP uniqueness*, the paragraph
> beginning "Case-insensitive equality does not depend on the ICU collation", reads for CUS-7:
> "Where CUS-7 compares a name and a town, or an e-mail address, ignoring case, both sides are
> folded in the statement with `casefold()` under the builtin-provider collation
> `pg_unicode_fast`, never through ICU or a column's own collation, on the stored values, which
> the domain functions that judge a request have already trimmed and normalised to NFC; a phone is
> compared byte-wise on its stored E.164 form. No comparison key is stored and no index or
> extension is added for it; a later addendum adds one when a measured lookup needs it, and
> decides then how rows written by a release without the key are covered." The `_match_key`
> naming and collation rule stays for any key a later addendum adds. ADR-0002-C10 is restated
> (table below). ADR-0002-C11 is unchanged.
>
> **New control ADR-0002-C18** (table below). Every other rule and control of this decision is
> unchanged.
>
> **Why.** No key exists. A stored key is an expand step on two populated tables with a backfill
> processing personal data in `migrate`, and the published previous release would write rows
> without it during a rollback, leaving them unwarned. The search addendum of 2026-11-20 already
> folds in the statement, proven on the ICU-collated and the `COLLATE "C"` columns
> (ADR-0002-C17), and builtin-provider folding is the same for every column and moves only with a
> major version, which keeps the paragraph's purpose: equality never depends on ICU. Restating an
> accepted rule and control is a declared deviation, following the addenda of 2026-10-28 (C12)
> and 2026-11-19 (C9). Approved by the human at gate 1 of EKO-3-09 on <acceptance date>
> (Issue #254).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C43 | A test stores customer X for rep A holding phone P, e-mail E, and name N in town T. Rep A's create with P, with E, and with N in T, and rep A's edit of its own Y setting each, answer the unmatched success status with a warning naming X; rep B's same create and edit, while only X holds the value, answer equal to rep B's same request in a world where X holds another value (status, body and headers other than `Eko-Correlation-Id`, the saved customer's own identifier excepted); rep B owning Y' that holds P gets, with and without X also holding P, the same answer naming only Y'; a caller holding `manager` and `rep` creating with P, and a caller holding `manager` without `rep` editing rep B's customer to P, get a warning whose identifiers `GET /api/customers/<id>` resolves under that caller; an answer with no in-scope match equals the answer of EKO-3-01..EKO-3-05 for the same request; a create or edit refused by 401, 403, 413, 422, 404, the state's 409 or the NIP's 409 carries no warning and equals its answer without the match; with the warning's read refused by the database alone the save answers its success status without the warning and the customer and its contacts are stored once; the warning's `data` function takes a visibility scope as a required parameter and `SYSTEM_READS` is unchanged. |
| ADR-0002-C10 (restated) | A test against the pinned PostgreSQL stores a customer named `"  Łukasz Żółć "` in town `"ŁÓDŹ"` and finds that a save of `"łukasz żółć"` in `"Łódź"` matches it under CUS-7, including when `ó` is given decomposed (`o` + U+0301); the same name in another town, and `"Lukasz Zolc"` in `"Lodz"`, do not match. |
| ADR-0002-C18 | A test against the pinned PostgreSQL finds that, under CUS-7, `600 100 200` matches a stored `+48600100200` and `600 100 201` does not; `Jan@Example.PL` matches a stored `jan@example.pl` on the `COLLATE "C"` contact value and `jan@example.pk` does not; `STRASSE` matches `straße` in name and town; after `alembic upgrade head` no column whose name ends in `_match_key`, and no index or extension, has been added for CUS-7. |

## Open questions for gate 1

- **A-1, accept the ADR-0003 addendum text and ADR-0003-C43** (Q-1 A, recommended), or B (no
  addendum; the impact map then carries "no written rule for what a success may disclose" as a
  named residual), or C (manager-only warning; the Story's rep lines drop).
- **A-2, the lookup's scope** (Q-2). A, recommended: the caller's visibility scope. B: reference
  scope plus creation scope. C: a system read (not recommended; forbidden by the restated C35).
- **A-3, G-4 in PostgreSQL terms** (Q-3). A, recommended: after the commit, in its own
  transaction. B: a savepoint inside the save's transaction. C: G-4 B, the lookup inside the
  save's transaction and a failure answered 503 with the save rolled back; the ADR-0003 addendum's
  last bullet then reads "a failure of that read rolls the write back and answers it as the storage
  failure it is".
- **A-4, how CUS-7 equality is computed** (Q-4). B, recommended: in the statement, the ADR-0002
  restatement and C10 restated, C18. A: ADR-0002 as written, a stored `_match_key` (the ADR-0002
  addendum text above is then dropped, and the task gains an expand revision, a backfill, an
  ADR-0004-C13 previous-release proof and an ADR-0005-C1 classification). C: a generated column
  (a different deviation, drafted only if chosen).
- **A-5, the warned answer's shape** (Q-5). A, recommended: one optional top-level field, absent
  when nothing matches. B, C, D as in the table.
- **A-6, what a warning names** (Q-6 = G-13). A, recommended: identifiers and the matched rules.
  B: plus the twin's name. C: text only (= G-3 B).
