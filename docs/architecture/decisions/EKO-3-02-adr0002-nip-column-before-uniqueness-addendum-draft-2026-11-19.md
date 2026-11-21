# EKO-3-02 — The `nip` column before its unique constraint; the foreign tax identifier's rules — ADR-0002 addendum draft — 2026-11-19

**Status:** Draft — pending approval
<!-- Only a human changes this status. If accepted, the section "Addendum text" is appended to
ADR-0002 as a dated addendum (date = human acceptance) in this task's gate-3 documentation PR.
This file is never itself appended to or edited inside ADR-0002's accepted text. -->

## Context

EKO-3-02 (Issue #208) adds the customer's Polish NIP and foreign tax identifier. It is the first
task that creates the `nip` column. ADR-0002, *Polish text, case-insensitive comparison, NIP
uniqueness*, fixes that column:

> `nip` holds only a Polish NIP in its canonical form (CUS-5: ten digits, without hyphens, spaces
> or the `PL` prefix), declared `COLLATE "C"`, with a check constraint admitting only ten digits.
> Company-wide uniqueness (CUS-6) is enforced by a **unique constraint in the database** on `nip`,
> not only by a check in a service, so two concurrent saves cannot both succeed.

and ADR-0002-C9 requires that "a second customer with an existing `nip` fails with a unique
violation (SQLSTATE `23505`)".

The Product Owner placed CUS-6 (blocking a duplicate NIP, with its role-dependent messages and the
ACC-8 wording) in EKO-3-03 (Issue #208, clarification C-4 A, 2026-11-19): "Until it merges the
server accepts the same NIP on two customers; safe only because no real data is loaded." The
Analyst's criterion K-04 therefore requires that a valid NIP already held by another rep's
customer gets exactly the answer a NIP nobody holds gets, and lists "a uniqueness constraint or
check on the NIP" as a mutation its tests must kill.

The two cannot both hold. With the unique constraint in place, a second customer with the same NIP
cannot be stored, so its answer must differ from the answer for an unused NIP, and any answer that
differs tells a rep that some customer, possibly another rep's, holds that NIP (PRH-4, ACC-8).
Without the constraint, the `nip` column exists in a shape ADR-0002 does not allow, and
ADR-0002-C9's first half fails.

ADR-0002 also forwards two product rules to EKO-3-03: "Normalising it [`foreign_tax_id`], and
whether a customer may hold both identifiers, are product rules for EKO-3-03." EKO-3-02's Story
decides both: a foreign tax identifier is free text with a length bound (CUS-5), and the customer's
country decides which of the two identifiers its single tax ID is.

## Decision (proposed)

### 1. The interval without the unique constraint (a declared deviation)

- EKO-3-02's revision creates `nip` as ADR-0002 requires in every respect but one: `COLLATE "C"`,
  the check constraint admitting only ten digits, `NULL` for a customer without a Polish NIP, and a
  column separate from `foreign_tax_id`. It does **not** create the unique constraint on `nip`.
- The unique constraint is created by EKO-3-03 (CUS-6), together with the answer to a duplicate
  that EKO-3-03's gate 1 decides. From EKO-3-03's merge, *NIP uniqueness* and ADR-0002-C9 hold as
  written.
- Until then, two customers may hold the same `nip`. This is acceptable only while every
  environment holds synthetic customer data (ADR-0005, *Synthetic customer data until the impact
  assessment*). No release that contains EKO-3-02 and not EKO-3-03 is deployed to an environment
  that holds real customer data.
- No `data` function reads the customer table across owners to detect a duplicate NIP in the
  interval: such a read would break ADR-0003-C35's "no `data` function serving a request reads an
  owned table without it [the scope]".

### 2. EKO-3-03's constraint is a contract step

- Under ADR-0004, *Expand → deploy → contract*, "adding a constraint old code violates" is a
  contract migration. EKO-3-02's code stores duplicate NIPs, so the unique constraint is one: it
  ships in a later release than the code that stops writing duplicates, never in the same release,
  and only once no running release writes them (ADR-0004, release step 3).
- A shared environment may hold duplicate synthetic NIPs by then. Creating the constraint on such
  a table fails; under ADR-0004 *Migrations* the revision is rolled back and the previous release
  keeps serving. What happens to those rows (refusing the deployment until an operator resolves
  them, or a data step in the revision) is decided at EKO-3-03's gate 1.
- This makes EKO-3-03 the first task that carries a contract migration on a product table, the
  item EKO-1-11 forwarded ("the first expand → contract", `docs/PLAN.md`, EKO-1-11 entry).

### 3. The foreign tax identifier and the single tax ID (decides what ADR-0002 forwarded)

- A customer holds at most one tax identifier. Its country decides where it is stored: for `PL`,
  sent or defaulted, the canonical NIP in `nip`; for any other country, the value in
  `foreign_tax_id`. The other column stays `NULL`. A foreign value never enters `nip`, as ADR-0002
  requires.
- A foreign tax identifier is stored as free text: trimmed, normalised to NFC (*Polish text*), and
  bounded in length (the bound is the Story's, decided at gate 1 of EKO-3-02). It has no checksum,
  no format beyond that, and no unique constraint, as ADR-0002 says.
- What EKO-3-03 still decides: the answer to a duplicate NIP and the constraint (section 2), and
  whether foreign tax identifiers are compared for duplicate warnings.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. `nip` without its unique constraint until EKO-3-03, as a declared deviation** (recommended; matches the Product Owner's C-4 A) | ADR-0002-C9's unique half fails for one task's span; EKO-3-03's constraint becomes a contract migration that ships a release after its code and can fail on duplicate synthetic rows in a shared environment; the human must not deploy the interval to real data | Nothing permanently: ADR-0002 holds as written from EKO-3-03's merge |
| B. The unique constraint now, no deviation | A second customer with an existing NIP cannot be stored, so EKO-3-02 must answer it: either CUS-6's role-dependent messages and ACC-8 wording (the Product Owner's C-4 option B, roughly doubling the Story), or a generic refusal that tells a rep another customer holds the NIP (PRH-4, ACC-8); K-04's PRH-4 edge and mutation (f) are rewritten | The Product Owner's C-4 A as decided |
| C. Move CUS-5's NIP half to EKO-3-03, no deviation | EKO-3-02 keeps the address and the foreign tax identifier only; the Story, its Definition of done and K-04 are rewritten and go back through the Product Owner; the column appears with its constraint and its duplicate answer in one task, so no contract migration is needed | The first contract migration on a product table being exercised soon (the EKO-1-11 forward stays open longer) |

## Addendum text

The following is the text proposed for ADR-0002 as a dated addendum, appended in the gate-3
documentation PR of EKO-3-02. It is written for option A.

> ### <acceptance date> — The `nip` column before its unique constraint; the foreign tax identifier's rules
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-02, Issue #208).
>
> **What it changes.** *Polish text, case-insensitive comparison, NIP uniqueness* requires a unique
> constraint on `nip`, and ADR-0002-C9 a unique violation for a second customer with an existing
> `nip`. EKO-3-02 creates the column and EKO-3-03 (CUS-6) decides the answer to a duplicate. From
> this date:
>
> - EKO-3-02 creates `nip` with `COLLATE "C"`, the ten-digit check constraint and `NULL` for a
>   customer without a Polish NIP, separate from `foreign_tax_id`, and **without** the unique
>   constraint. EKO-3-03 creates the unique constraint. From EKO-3-03's merge, the rule and
>   ADR-0002-C9 hold as written.
> - Until then two customers may hold the same `nip`. No release containing EKO-3-02 without
>   EKO-3-03 is deployed to an environment holding real customer data (ADR-0005). No `data`
>   function reads the customer table across owners to detect a duplicate (ADR-0003-C35).
> - EKO-3-03's unique constraint is a contract migration (ADR-0004, *Expand → deploy → contract*):
>   it ships in a later release than the code that stops writing duplicates. Its treatment of
>   duplicate rows already stored in a shared environment is decided at EKO-3-03's gate 1.
> - A customer holds at most one tax identifier, placed by its country: for `PL`, sent or
>   defaulted, the canonical NIP in `nip`; otherwise the value in `foreign_tax_id`, the other
>   column `NULL`. A foreign tax identifier is trimmed, stored as NFC and bounded in length, with no
>   checksum and no unique constraint. This decides the two rules this decision forwarded to
>   EKO-3-03 for `foreign_tax_id`; EKO-3-03 keeps the duplicate rules.
> - **ADR-0002-C9 restated** (table below) for the interval.
>
> Every other rule and control of this decision is unchanged.
>
> **Why.** The Product Owner placed CUS-6 in EKO-3-03 (C-4 A). With the constraint in place,
> EKO-3-02 would have to answer a duplicate NIP, and any answer other than the one for an unused NIP
> tells a rep that another customer holds it (PRH-4, ACC-8). Leaving the constraint out for one
> task's span, while only synthetic data exists, is a deviation from this decision's text, so it is
> declared here with its end condition rather than left as a silent gap between the schema and this
> decision. Approved by the human at gate 1 of EKO-3-02 on <acceptance date> (Issue #208).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0002-C9 (restated for the interval) | Until EKO-3-03 merges: a test inserting directly through SQL, bypassing the services, finds that `nip` value `PL1234567890` or `DE123456789` fails with a check violation (SQLSTATE `23514`); two customers with `nip` `NULL` are both stored; two customers with the same `foreign_tax_id` are both stored; and a second customer with an existing `nip` is stored. From EKO-3-03's merge, ADR-0002-C9 as written. |

## Open questions for gate 1

- **N-1, the interval without the unique constraint.** A (recommended): accept this addendum.
  B: the constraint now, and EKO-3-02 answers a duplicate (CUS-6 pulled in, or a disclosing
  refusal). C: move the NIP half of CUS-5 to EKO-3-03.
- **N-2, the foreign tax identifier and the single tax ID** (section 3). A (recommended): decided
  here as written. B: leave both with EKO-3-03 as ADR-0002 forwards them; EKO-3-02 then stores no
  foreign tax identifier, and the Story's line "a foreign tax ID is stored as free text" moves to
  EKO-3-03.
