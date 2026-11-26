# EKO-3-06 — The operator seed: the owner the operator names, the dataset's record identity, the synthetic-only declaration, and where and how the seed runs — ADR-0003, ADR-0004 and ADR-0005 addendum draft — 2026-11-25

**Status:** Draft — pending approval
<!-- Only a human changes this status. If accepted, each section of "Addendum text" is appended to
the decision it names as a dated addendum (date = human acceptance) in this task's gate-3
documentation PR. This file is never itself appended to or edited inside an accepted text. -->

## Context

EKO-3-06 (Issue #258) carries SEED-1: an operator script loads a committed synthetic dataset (three
reps named by the operator, about 200 customers each) into an environment declared synthetic-only.
Gate-1 round 1 chose C-1..C-5 A. This is the first code that writes product data outside an HTTP
request.

What the accepted decisions already settle:

- ADR-0005 *Synthetic customer data*: "Tests (`backend/tests/`, `frontend/tests/`), fixtures, the
  seed script (SEED-1) and CI hold only synthetic data and are not holders of personal data under
  this decision." ADR-0005-C16: "By the human's statement per shared environment, recorded with its
  date: the environment holds only synthetic customer data, until the GDPR impact assessment is
  done."
- ADR-0005 *Erasure*: "Customer identifiers are never reused. An identifier once issued to a
  customer is never issued to another customer, also after a restore from an earlier backup set".
  ADR-0005-C17 tests it; the application issues random UUIDv4 values (`backend/app/data/models.py`,
  capability row 50).
- ADR-0004 *Composition and placement* lists exactly the services of an environment
  (ADR-0004-C1); *Cloud-agnostic constraints* 2: "Configuration that differs between environments,
  and every secret, reach it only through environment variables (for the backend, read only in
  `backend/app/core/settings.py`)". The backup addendum of 2026-10-30 is the one precedent for an
  operator command: "a one-off container of the `backup` service, with that service's
  environment, removed when it ends and starting no other service".
- ADR-0001 addendum of 2026-10-29: "`layer-dependencies.md` may also hold a row for one file
  outside the layer directories, such as `backend/app/worker.py` ... Such a row is not a layer
  directory and gets no `TID251` scope."

What they leave open, or forbid:

1. **The owner.** ADR-0003 addendum of 2026-11-17, *Owner*: "Every customer has one owner, the
   subject identifier of the caller that created it, taken from the caller value and stored as
   received. A request value never sets it." The addendum of 2026-11-20: "`OwnedBy` and
   `AllRecords` are built only by the `domain` function of *Where it is enforced*, from the caller
   value." The seed has no caller: the owner is a subject the operator names (C-2 A). *Roles*:
   "the backend reads a caller's roles **only** from that client's role claim in a token it
   verified", so the seed may not make up a caller holding `rep` either.
2. **The record identity** C-3 A requires ("each record has a stable identity, so a second run
   adds nothing and an interrupted run can be resumed"). The schema has no column for it, and an
   identifier derived from the dataset would be issued again after a restore, against C17.
3. **The declaration.** C16 is a human's dated statement with no machine-readable carrier, and
   covers shared environments only, while C-1 A requires the seed to refuse every environment,
   developer and test included, that does not carry it.
4. **Where the seed runs**, which service's environment and connections it uses, and that the
   migration and revision rules of ADR-0004 *Migrations*, written for `backend` "(and any
   worker)", bind it.
5. **The connection budget.** ADR-0003-C19 sums "the backend's configured workers × (pool size +
   max overflow) plus the background jobs' pools plus one migration connection"; an operator
   one-off is not in the sum.

## Decision (proposed)

### 1. Where the seed lives and how it runs (ADR-0001 fits; ADR-0004 addendum)

- The seed's entry point is one file, `backend/app/seed.py`, run as `python -m app.seed`; its
  dataset is one file beside it, `backend/app/seed_dataset.py`. Both ship in the backend image like
  every file under `backend/app/`. Each gets its own single-file row in
  `docs/architecture/layer-dependencies.md` (the `worker.py` precedent). No console script, no new
  ruff configuration, no new layer directory.
- `seed.py` must not depend on `api`, `auth` or `integrations`. `seed_dataset.py` depends on
  `domain` only, and on no other layer, `core` included, so it can read no clock and no
  environment.
- Every dataset record becomes a `CustomerDraft` through the same `domain` function that the API's
  create uses. No rule of CUS-1..CUS-8 is held only in `api`; what stays in `api` is the wire's raw
  length caps and strict JSON types (Q-5 A).
- In an environment the seed runs only as a one-off container of the `worker` service, with that
  service's environment, removed when it ends and starting no other service:
  `docker compose run --rm --no-deps worker python -m app.seed <subject> <subject> <subject>`. The
  exact text is kept in the operator documentation. No service is added (ADR-0004-C1 unchanged).
  The worker's environment carries no OIDC client secret and no session-encryption key, and the
  seed needs neither.
- The seed is bound like `backend` and any worker by *Migrations*: it never runs
  `alembic upgrade`, and at start it refuses, writing nothing, every revision other than its code's
  head and a lineage-recorded descendant (G-7 A).
- The seed holds at most one database connection (section 6).

### 2. The owner the operator names (ADR-0003, declared deviation)

- A customer the seed loads is owned by the subject the operator names for its share, stored as
  received. The subject is judged on its form alone (the owner form of the addendum of 2026-11-20:
  1 to 255 characters in U+0021..U+007E), never on whether an account holds it (G-4 A).
- The creation scope for that subject is built by one function in
  `backend/app/domain/ownership.py`, the **operator creation scope**. It is reached only from
  `backend/app/seed.py`. No module under `backend/app/api/` or `backend/app/auth/`, nor
  `backend/app/main.py` or `backend/app/worker.py`, imports it. ADR-0003-C36 stays as written.
- No caller value is built by the seed, and no role is assumed for the named subject. The seed
  calls no Keycloak interface and reads no display-name copy. A named subject that has no copy is
  allowed, and the seed writes none.

### 3. The dataset's record identity (ADR-0005 inventory; ADR-0002 and ADR-0004 fit)

- One nullable column on `customer` holds the **dataset key** of a seeded record. It has a unique
  index and no default, and is "not personal data" (ADR-0005-C1): an opaque index into the
  committed dataset, derived from no field value. It is added by one expand revision on the head
  current at merge (ADR-0004 release step 1: a nullable column and an index).
- The API's create never writes it (it stays `NULL`), and no API answer carries it; the OpenAPI
  document is unchanged.
- Whether a record is already loaded is decided by that unique index in the insert itself, never
  by a read of the customer table made before it. A record already loaded adds nothing; a record
  whose NIP another customer holds is refused by `uq_customer_nip` and reported (CUS-6). A record
  and its contacts are one transaction. This keeps ADR-0003-C35 as written: no function is added to
  the closed system-read list.
- Customer and contact identifiers stay random UUIDv4 values issued at insert. ADR-0005-C17 is
  unchanged.
- **Revision order.** EKO-3-05 (#253) may add a revision on `0007` in parallel. The tree stays
  linear (ADR-0002-C2; `migrate` refuses a branched tree, EKO-1-24). Whichever of the two merges
  second re-parents its revision on the other's and renumbers it before its gate 2, never with an
  Alembic merge revision. The shipped-tree check is updated in that same PR.

### 4. The synthetic-only declaration (ADR-0005)

- An environment declares itself synthetic-only through one environment variable of the `worker`
  service, read only in `backend/app/core/settings.py`. It is not a secret. Only one exact value
  declares it; absent, empty, whitespace-only or any other value means "not declared". The seed
  checks it before it opens any connection that writes, and an undeclared target ends the run
  non-success with nothing written. `backend` and `worker` serve whether it is set or not.
- In a shared environment the IT department sets it only after the human's dated C16 statement for
  that environment exists, and removes it when that statement is withdrawn. The statement stays the
  record; the variable is its carrier.
- In developer and test environments, which C16 does not cover, setting the variable is the
  developer's own statement. No dated record is required.
- Production never sets it before the impact assessment.

### 5. The dataset and the seed's output (ADR-0005)

- Every value is generated inside the repository from committed seeds by a deterministic
  procedure. No value comes from the clock, the environment, the network, a file outside the
  repository, or an unseeded random source. A committed fingerprint of the generated set pins it.
- Every NIP has the prefix `000` with a valid checksum computed at run time (G-1 A, the
  `backend/tests/support/eko302_nip.py` precedent: no tax office's prefix). Every e-mail domain is
  a reserved one (`example.com`, `example.org`, `example.net`, `.example`, `.test`, `.invalid`).
  Phones are also built at run time, so no committed line carries a NIP or phone shape. The
  repository's personal-data shape scan (capability row 19) is unchanged and gets no allowance
  (Q-1 A).
- Realistic names, towns and phone numbers may coincide with a real person, business or
  subscriber. The human accepts this residual in writing at this gate.
- The seed's output and logs are bound by *What may appear in logs* as "any worker". A record is
  named only by its dataset key and the rule (or field) that refused it. Totals are counts. No
  customer field value appears, nor a validation error's input or a driver message. On a NIP
  refusal the seed does not look the holder up.

### 6. The connection budget (ADR-0003, declared deviation)

ADR-0003-C19's sum also counts one connection for the seed, which holds at most one. With the
values in `compose.yaml` (application role limit 30; backend 2 × (5 + 5), worker 2, migrate 1) the
sum becomes 24.

## Options considered

### Q-1 — The dataset against the personal-data shape scan (Analyst gap 1)

| Option | Cost | Closes off |
|---|---|---|
| **A. Build NIPs (`000` prefix, checksum) and phones at run time from committed seeds; reserved e-mail domains; the scan unchanged** (recommended) | A small generator. The committed fingerprint has to be a digest, not the values. | Nothing. |
| B. Commit the values and add a path allowance for the dataset file to the scan | A weakening the human must accept, bound to one path. Any real value later pasted into that file passes CI. | The scan as a guard on the one file most likely to receive real customer data. |
| C. Commit only customers without a NIP and with no phone | Weak CUS-5/CUS-6 coverage at volume (G-1 B). Phones never exercised. | A realistic list and search. |

### Q-2 — How a record's identity is kept (Analyst gap 2)

| Option | Cost | Closes off |
|---|---|---|
| **A. A nullable dataset-key column on `customer` with a unique index; the index arbitrates in the insert** (recommended) | One expand revision (schema class, ordering with EKO-3-05). A column the API ignores. | Nothing. Overlapping runs also cannot duplicate, so G-6 B costs only a test. |
| B. A separate table of dataset key → customer identifier, written in the create's transaction | A new table and its ADR-0005 classification. A second insert in the create. Deciding whether it is an owned table (C35). | Nothing, but more surface than A. |
| C. Deterministic identifiers derived from the dataset key (for example UUIDv5) | A declared deviation from ADR-0005 *Customer identifiers are never reused*. ADR-0005-C17 fails after a restore to a set taken before the seed. Every environment holds the same identifiers. | Relying on an identifier to name one customer across restores (the erasure record). |
| D. Identity from record content (name, town, NIP, or a digest of all values) | No schema change. A rep's identical customer is taken as seeded (K-06 name twin). A NIP match cannot tell a seeded holder from a rep's (K-04 twin). A read across owners needs a system-read entry and C35 restated. | The K-04 and K-06 contrasts. |

### Q-3 — How an environment declares itself synthetic-only (Analyst gap 3)

| Option | Cost | Closes off |
|---|---|---|
| **A. One non-secret environment variable of `worker`, read in `settings.py`, exact value; set in a shared environment only after the C16 statement; also required in developer and test environments** (recommended) | One `compose.yaml` entry (a sensitive path). An ADR-0005 addendum. The IT department keeps the variable in step with the statement. | Nothing. |
| B. A marker row in the application database, written by the operator | A table or column and its revision. Who may write it (superuser SQL). It travels with backups, so a pilot set restored elsewhere carries the pilot's declaration. | Nothing, but the declaration follows the data rather than the environment. |
| C. A command-line flag of each run (`-e ...` or `--synthetic`) | No `compose.yaml` change. | A declaration that belongs to the environment: every run carries its own, one flag away from seeding any target. |
| D. The human's record alone, no machine check | None. | K-05 and C-1 A's refusal. |

### Q-4 — Where the seed lives and which service it runs as (Analyst gap 4)

| Option | Cost | Closes off |
|---|---|---|
| **A. `backend/app/seed.py` + `backend/app/seed_dataset.py`, two single-file layer rows; a one-off of `worker`** (recommended) | Two layer rows, two sensitive-path rows, a whole-file import test (the #47 precedent for `worker.py`: single-file rows get no `TID251` scope). | Nothing. Row 44's admin-API scan, ADR-0001-C10 and ADR-0002-C4/C13 reach it because it is under `backend/app/`. |
| B. A one-off of `backend` | The seed's container receives the OIDC client secret and the session key it never needs. | Least privilege for an operator tool. |
| C. A package `backend/app/seed/` as a new layer | A seventh `ruff.toml` breaks ADR-0001-C8 as restated (exactly six), so an ADR-0001 addendum. | Nothing. |
| D. Outside `backend/app/` (for example `backend/scripts/`) | Escapes row 44's scan, ADR-0001-C10, ADR-0002-C13, the layer check and the ruff bans; may not ship in the image. | K-06's "the scan reaches the script". |
| E. A new `seed` service in the composition | ADR-0004-C1 lists exactly the services: a deviation. | Nothing. |

### Q-5 — Where the seed gets create's rules (part of gap 4, K-02)

| Option | Cost | Closes off |
|---|---|---|
| **A. The raw-values-to-`CustomerDraft` composition held once in `domain`; `CustomerCreate` and the seed both call it; the seed never imports `api`** (recommended) | A refactor of `backend/app/api/customers.py` and `backend/app/domain/customers.py`. Every EKO-3-01/02/03 server suite must pass unedited. | Nothing. |
| B. The seed validates through `app.api.customers.CustomerCreate` | `seed.py`'s row allows `api`. Importing it pulls `app.auth.gate` and the API's dependencies into an operator process. | The rule "only `api` and `main.py` depend on `auth`" (ADR-0001 addendum of 2026-10-23), unless the import is proven transitive-free. |
| C. The seed keeps its own copy of the rules | None. | K-02 ("no weaker path"). |

### Q-6 — The owner of a seeded customer (not routed by the Analyst; follows from C-2 A)

| Option | Cost | Closes off |
|---|---|---|
| **A. An operator creation scope in `ownership.py`, reached only from `seed.py`; ADR-0003 *Owner* and "from the caller value" restated** (recommended) | A declared deviation; one function and its static check (ADR-0003-C39). | Nothing. |
| B. The seed makes up a caller holding `rep` for each subject and calls the existing create use case | Against *Roles* ("roles ... only from ... a token it verified"). A caller value with no verified token exists in the process. | The meaning of a caller value as "what the identity server asserted". |
| C. The seed calls `POST /api/customers` as each rep | Needs a session per rep: real credentials, or a token obtained from Keycloak. Against C-2 A and ADR-0003's identity boundary. | Seeding a pilot without the reps' credentials. |

### Q-7 — The connection budget

| Option | Cost | Closes off |
|---|---|---|
| **A. ADR-0003-C19 restated to count the seed's one connection** (recommended) | A declared deviation of a control; the C19 test counts one more term. | Nothing. |
| B. No text change; the seed is read as one of "the background jobs' pools" | None. | Nothing now, but the reading lives only in this impact map, and a later pool change may fill the limit without the seed's connection counted. |

## Addendum text — ADR-0003

> ### <acceptance date> — Customers loaded by the operator seed: the owner the operator names; ADR-0003-C19 restated
>
> **Status:** Accepted <acceptance date>, as a declared deviation (gate 1 of EKO-3-06, Issue #258).
>
> **What it adds.** The addenda of 2026-11-17 and 2026-11-20 decide the owner of a customer a
> caller creates. They do not decide the owner of a customer that no caller creates. From this
> date:
>
> - The operator seed (`backend/app/seed.py`, ADR-0004 addendum of the same date) creates
>   customers owned by subjects the operator names. A named subject is judged on the owner form of
>   the addendum of 2026-11-20 alone, never on whether an account holds it, and is stored as
>   received.
> - The creation scope for such a subject is built by one function of
>   `backend/app/domain/ownership.py`, the operator creation scope. Only `backend/app/seed.py`
>   imports it. No module under `backend/app/api/` or `backend/app/auth/`, nor
>   `backend/app/main.py` or `backend/app/worker.py`, reaches it.
> - The seed builds no caller value and assumes no role. It calls no Keycloak interface and neither
>   reads nor writes the display-name copy.
>
> **What it restates.**
>
> - The addendum of 2026-11-17, *Owner*: "Every customer has one owner, the subject identifier of
>   the caller that created it, taken from the caller value and stored as received" reads: "...
>   taken from the caller value, or, for a customer the operator seed loads, the subject the
>   operator names for it, and stored as received". "A request value never sets it" is unchanged.
> - The addendum of 2026-11-20: "`OwnedBy` and `AllRecords` are built only by the `domain`
>   function of *Where it is enforced*, from the caller value" reads: "... from the caller value,
>   except the operator creation scope, which builds an `OwnedBy` from a subject the operator names
>   and is reached only from the operator seed". The addendum of 2026-11-22's "stay built only
>   from a caller value" is read the same way. ADR-0003-C36 is unchanged.
> - ADR-0003-C19 is restated (table below).
>
> **New control ADR-0003-C39.** Every other rule and control of this decision is unchanged. The
> closed system-read list, the session-exempt, role-free and non-CRM lists are unchanged.
>
> **Why.** SEED-1 needs customers that real reps' logins see (C-2 A), and no rep is logged in when
> the operator loads them. Making up a caller for each subject would put into the process a
> caller value that no identity server asserted, which *Roles* forbids. A scope built from an
> operator value and reachable from one entry point keeps every request path deciding from the
> verified token. Restating an accepted rule and control is a declared deviation, following the
> addenda of 2026-11-20 (C33) and 2026-11-22 (C35). Approved by the human at gate 1 of EKO-3-06 on
> <acceptance date> (Issue #258).

## Addendum text — ADR-0004

> ### <acceptance date> — The operator seed: a one-off of `worker`, bound by *Migrations*
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-06, Issue #258).
>
> **What it adds.** From this date:
>
> - The operator seed is `python -m app.seed`, shipped in the backend image. In an environment it
>   runs only as a one-off container of the `worker` service, with that service's environment,
>   removed when it ends and starting no other service:
>   `docker compose run --rm --no-deps worker python -m app.seed <subject> <subject> <subject>`.
>   Its exact text is kept in the operator documentation. No service is added; ADR-0004-C1 is
>   unchanged.
> - *Migrations* binds the seed as it binds `backend` and any worker. It never runs
>   `alembic upgrade`. At start it refuses, writing nothing, every revision other than its code's
>   head and a lineage-recorded descendant of it, and it never waits for the migration advisory
>   lock.
> - The seed holds at most one database connection.
> - In a shared environment the IT department runs it only where the declaration of ADR-0005's
>   addendum of the same date is set.
>
> **New control ADR-0004-C37.** This adds rules and restates none, so it is not a deviation. Every
> other rule and control of this decision is unchanged.
>
> **Why.** The seed writes product data outside a request. Run as a one-off of `backend`, it would
> receive the OIDC client secret and the session key it never needs. A new service would change
> the composition's service list. *Migrations* names `backend` "and any worker", and the seed must
> not load into a schema without the constraints its rules rely on (`uq_customer_nip`). Approved by
> the human at gate 1 of EKO-3-06 on <acceptance date> (Issue #258).

## Addendum text — ADR-0005

> ### <acceptance date> — The operator seed: the synthetic-only declaration, the dataset, its record key and its output
>
> **Status:** Accepted <acceptance date> (gate 1 of EKO-3-06, Issue #258).
>
> **What it adds.** From this date:
>
> - **The declaration.** An environment declares that it holds only synthetic customer data
>   through one environment variable of the `worker` service, read only in
>   `backend/app/core/settings.py`. It is not a secret. Only one exact value declares it, and any
>   other state is "not declared". The operator seed refuses an undeclared target before it writes
>   anything.
> - In a shared environment the variable is set only after the human's dated statement of
>   ADR-0005-C16 for that environment exists, and is removed when that statement is withdrawn; the
>   statement stays the record. In developer and test environments, which C16 does not cover,
>   setting it is the developer's own statement, with no dated record. Production does not set it
>   before the GDPR impact assessment.
> - **The dataset.** Every value is generated inside the repository from committed seeds by a
>   deterministic procedure. It reads no clock, environment, network, outside file or unseeded
>   random source. A committed fingerprint pins the result. Every NIP has the prefix `000` and a
>   valid checksum, computed at run time. Every e-mail address is in a reserved domain. Phones are
>   built at run time. The human accepted, at gate 1 of EKO-3-06, that a realistic name, town or
>   phone number may coincide with a real person, business or subscriber.
> - **The dataset key.** The `customer` column holding a seeded record's dataset key is "not
>   personal data" under *Classifying columns*. The key is an opaque index into the dataset,
>   derived from no field value. The API's create never writes it and no API answer carries it.
> - **The seed's output.** The seed writes under *What may appear in logs* as "any worker". It
>   names a record only by its dataset key and the rule or field that refused it, gives totals as
>   counts, and writes no customer field value, no validation error's input and no database
>   driver message.
>
> **New controls ADR-0005-C22 and C23.** This adds items and rules and restates none, so it is
> not a deviation. ADR-0005-C16 and C17 are unchanged. Every other rule and control of this
> decision is unchanged.
>
> **Why.** C-1 A has the seed refuse every environment that has not declared itself synthetic-only,
> and C16's human statement cannot be read by a program. The seed's dataset is the one place in the
> repository built to look like customer data, so its provenance must be provable, and its key
> needs a classification like every new column. Approved by the human at gate 1 of EKO-3-06 on
> <acceptance date> (Issue #258).

## Controls

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C39 | Under `backend/app/`, the operator creation scope function of `backend/app/domain/ownership.py` is imported only by `backend/app/seed.py`; a fixture import of it from a module under `backend/app/api/`, `backend/app/auth/`, from `backend/app/main.py` or `backend/app/worker.py` fails the check; a seed run with three named subjects stores each share with exactly its named subject as `customer.owner_subject`, refuses a subject outside the owner form before any write, succeeds with Keycloak unreachable, and leaves `staff_display_name` byte-equal. |
| ADR-0003-C19 (restated) | On the PostgreSQL server, Keycloak's database role and the application's database role each have a connection limit greater than zero, Keycloak's configured `db-pool-max-size` does not exceed its role's limit, the backend's configured workers × (pool size + max overflow) plus the background jobs' pools plus one migration connection plus one connection of the operator seed does not exceed the application role's limit, and the two limits together are below `max_connections` minus `superuser_reserved_connections`; a seed run holds at most one connection to the application database. |
| ADR-0004-C37 | The operator seed started against a database at a revision older than its code's head, or at one it cannot place, exits non-zero and leaves every application table and the schema byte-equal; a seed run at head leaves `alembic_version`, `schema_revision_lineage` and the schema dump unchanged; `docker compose config --services` is unchanged by this task. |
| ADR-0005-C22 | Against a target whose declaration variable is absent, empty, whitespace only or any value other than the accepted one, the operator seed exits non-zero, names the missing declaration, and leaves every application table byte-equal; the same target with only the accepted value set loads the dataset; no file under `backend/app/` other than `backend/app/core/settings.py` reads the variable. |
| ADR-0005-C23 | Two seed runs into two fresh databases, at different clock instants and under different process random and hash seeds, store identical customer and contact values (identifiers and owners aside), equal to the committed fingerprint; every stored NIP begins with `000`; every stored e-mail address is in a reserved domain; `backend/app/seed_dataset.py` imports no layer but `domain`; across a full load, a re-run, every refused-record case and a refused target, no customer field value of the dataset or of an injected record appears in the seed's output or in any in-process log line, and each refused record is named by its dataset key and rule only; `POST /api/customers` stores the dataset-key column as `NULL` and no OpenAPI response schema carries it. |

## Open questions for gate 1

- **Q-1 (A-1), the dataset against the shape scan.** A, recommended: NIPs and phones built at run
  time, reserved e-mail domains, scan unchanged. B: a path allowance (a weakening). C: no NIPs or
  phones.
- **Q-2 (A-2), record identity.** A, recommended: a dataset-key column with a unique index as the
  arbiter. B: a mapping table. C: deterministic identifiers (against ADR-0005-C17). D: identity
  from content.
- **Q-3 (A-3), the declaration's carrier.** A, recommended: an environment variable of `worker`,
  also required in developer and test environments. B: a database marker. C: a per-run flag.
  D: no machine check.
- **Q-4 (A-4), location and service.** A, recommended: `backend/app/seed.py` and
  `backend/app/seed_dataset.py`, a one-off of `worker`. B: a one-off of `backend`. C: a new layer
  package. D: outside `backend/app/`. E: a new service.
- **Q-5 (A-5), where create's rules come from.** A, recommended: one `domain` composition shared
  with `CustomerCreate`. B: the seed imports the API model. C: a copy.
- **Q-6 (A-6), the owner of a seeded customer.** A, recommended: an operator creation scope, ADR-0003
  restated. B: a made-up caller. C: the HTTP API as each rep.
- **Q-7 (A-7), the connection budget.** A, recommended: C19 restated. B: read into the existing sum.
- **Q-8 (A-8), accept these addendum texts** (A, recommended), or reject them (B). If they are
  rejected, the seed has no owner rule it can follow without breaking ADR-0003, no carrier for the
  refusal of C-1 A, and no record identity for C-3 A. The DoD lines on owners, refusal and
  re-runs then leave the task.
