# ADR-0002 — Database engine, migration tool and data access

**Status:** Accepted 2026-10-23
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

No product task that persists data fits the architecture until the database is decided. The
choice is bounded by ADR-0001 (Python backend, container images) and by the brief
([`project-brief.md`](../../product/project-brief.md), section 5): on-premises and cloud-agnostic,
about 10 users and a few thousand customers, time zone Europe/Warsaw, Polish text. Requirements
already known shape the storage: day boundaries and DST for visits (EKO-4-01, DSH-1), company-wide
NIP uniqueness (CUS-6), case- and edge-space-insensitive name-and-town matching (CUS-7), and
background synchronisation running beside the web process (ADR-0001, "Background work").

## Decision

### Engine, migration tool, data access

| Part | Choice |
|---|---|
| Database engine | PostgreSQL, major version 18, run from a container image pinned to a full version (see "Image pinning and ICU") |
| Migration tool | Alembic; revisions live in `backend/migrations/` |
| Data access | SQLAlchemy 2.x, confined to the `data` layer (`backend/app/data/`) and to `backend/migrations/` |
| Driver | psycopg 3 |

- **On-premises, no cloud vendor.** PostgreSQL is open source and runs as an ordinary container on
  the company's server; nothing in this decision depends on a managed database service. A later
  move to a managed PostgreSQL offering stays possible but is not assumed.
- **Versioned migrations.** Every schema change is an Alembic revision in `backend/migrations/`;
  no application code creates or alters schema at run time. Revision history is linear (one head).
  `alembic upgrade head` brings an empty database to the current schema. Changes that would break
  the running version follow expand → deploy → contract. PostgreSQL runs DDL inside transactions,
  so a failing revision leaves the schema unchanged. When and by which single process
  `alembic upgrade head` runs on deploy and restart is not decided here (forward reference:
  ADR-0004).
- **Data access stays in its layer.** The domain layer never imports SQLAlchemy; services reach
  persistence only through the `data` layer (ADR-0001 layer rules).
- **Major-version upgrades** of PostgreSQL are recorded as an addendum to this decision.

### Image pinning and ICU

- Every reference to the PostgreSQL image (composition, CI, test fixtures) names a full version
  and base OS release — a tag of the form `18.<minor>-<OS release>` — or an image digest; never a
  floating tag such as `18`, `18-<OS release>` or `latest`. The ICU library comes from the image,
  so a re-pull cannot change it silently.
- Changing that reference is therefore an explicit upgrade. If the new image carries a different
  ICU version, the upgrade includes rebuilding every index on an ICU-collated column (`REINDEX`) and
  then `ALTER DATABASE … REFRESH COLLATION VERSION`, and it is recorded as an addendum to this
  decision.

### Now, today, and Europe/Warsaw days

- **"Now" and "today" come from one injected clock.** The clock is one module,
  `backend/app/core/clock.py`; it returns the current instant as a timezone-aware UTC value, and
  "today" is the Europe/Warsaw calendar date of that instant. Code that needs the current instant
  or the current date receives the clock rather than reading the system time, so a test fixes it at
  any instant. No other code under `backend/app/` reads the system time: no `datetime.now()`,
  `datetime.utcnow()`, `date.today()`, `time.time()`, and no SQL that evaluates the database's
  current time or date (`CURRENT_DATE`, `CURRENT_TIMESTAMP`, `now()`, `LOCALTIMESTAMP`, or
  `now()::date`), including as a column default. The result does not depend on the zone of the
  container, the process or the database session.
- A **point in time** (visit start and end, change timestamps, sync timestamps) is stored as
  `timestamp with time zone`, i.e. an absolute instant. `timestamp without time zone` is not used
  for points in time. Application connections run with session time zone UTC.
- A **calendar date** with no time of day (an action's due date) is stored as `date`, interpreted
  as a Europe/Warsaw calendar date. A comparison with "today" (due today, overdue) compares it with
  the clock's Europe/Warsaw date, passed into the query as a parameter.
- **Europe/Warsaw days are computed in the application**, with the IANA zone `Europe/Warsaw` from
  Python's `zoneinfo`. A day, a week or a period becomes a half-open range of instants
  `[start of first local day, start of the day after the last)`, so a 23-hour or 25-hour DST day is
  covered exactly; queries filter instants by that range. The backend ships the IANA time-zone data
  as a Python dependency (`tzdata`), so the result does not depend on the image's operating system.

### Wall time entered by a user

- A wall time a user enters reaches the backend as a local date and a local time with no offset
  (ADR-0001, Constraint 3), meaning Europe/Warsaw. One domain function resolves it to an instant
  with `zoneinfo` `Europe/Warsaw`, and rejects it with a validation error (HTTP 422) that names
  which of the two reasons applies. The function resolves the local date and time with `fold=0`
  and with `fold=1`, converts each resulting instant back to Europe/Warsaw, and compares the local
  date and time it gets (ignoring `fold`) with the input. The two conditions are disjoint:
  - **nonexistent** — the local time is skipped (the missing hour in March): for at least one
    `fold` value the round trip does not return the input's local date and time (in the gap,
    PEP 495 gives the two `fold` values different offsets, and neither round-trips);
  - **ambiguous** — the local time occurs twice (the repeated hour in October): for both `fold`
    values the round trip returns the input's local date and time, and the two give different UTC
    offsets.
- Only the resolved instant is stored. The frontend never chooses the offset, so a device set to
  another zone cannot shift the stored instant.
- An instant that arrives already resolved (e.g. from an external calendar) is stored as given;
  two instants with the same Europe/Warsaw wall time in the repeated hour are two distinct stored
  values.

### Polish text, case-insensitive comparison, NIP uniqueness

- The database is created with encoding `UTF8`. Its default collation uses the ICU provider with
  locale `pl-PL`, so ordering follows the Polish alphabet (Ł after L, not after Z). Indexes on
  columns that use it are governed by "Image pinning and ICU".
- Text is stored in Unicode NFC, normalised by the application before it is written, so a composed
  and a decomposed "ó" are the same stored value.
- **Case-insensitive equality does not depend on the ICU collation.** Where a rule compares text
  ignoring case and edge spaces (CUS-7, name in the same town), the application computes a
  comparison key with one domain function (NFC, trim of leading and trailing whitespace, Unicode
  case folding) and the `data` layer stores it beside the displayed value and indexes it. The key
  is written only by that function. A comparison-key column is named with the suffix `_match_key`
  and declared `COLLATE "C"`, so its comparison and index order are byte-wise and cannot change
  with an ICU upgrade. CUS-7 warns and does not block, so this key carries no unique constraint.
- **A Polish NIP and a foreign tax ID are stored in separate columns.**
  - `nip` holds only a Polish NIP in its canonical form (CUS-5: ten digits, without hyphens,
    spaces or the `PL` prefix), declared `COLLATE "C"`, with a check constraint admitting only
    ten digits. Company-wide uniqueness (CUS-6) is enforced by a **unique constraint in the
    database** on `nip`, not only by a check in a service, so two concurrent saves cannot both
    succeed. A customer without a Polish NIP stores `NULL`, and any number of customers may have
    none.
  - `foreign_tax_id` holds a foreign tax identifier as free text, with no unique constraint; it
    never enters the `nip` column, so it cannot collide with a Polish NIP. Normalising it, and
    whether a customer may hold both identifiers, are product rules for EKO-3-03.

### Background work

PostgreSQL row locking (`SELECT … FOR UPDATE SKIP LOCKED`) and `LISTEN`/`NOTIFY` keep a
database-backed job queue available. Whether background work uses it is decided in ADR-0006.

### Forward references (not decided here)

- ADR-0003 (#15) — where the identity server stores its own data, and whether it shares this
  PostgreSQL server.
- ADR-0004 (#16) — database container composition, credentials and secret handling, daily
  off-server backup, restore procedure, encryption at rest of volumes and backups; when and by
  which single process `alembic upgrade head` runs on deploy and restart (so that web and worker
  containers started from one image never run it concurrently), and how expand → deploy → contract
  is carried out across releases.
- ADR-0005 (#17) — which tables and columns hold personal data, retention, archiving vs. erasure,
  what may appear in logs.
- ADR-0006 (#18) — storage and encryption of Google tokens; the background-work mechanism.

Also not decided here: whether the `data` layer uses SQLAlchemy's synchronous or asynchronous
session API. The walking skeleton (EKO-1-06) proposes it, and it is recorded as an addendum before
the first product task that persists data.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. PostgreSQL 18 + Alembic + SQLAlchemy 2** (chosen) | A database server to operate, back up and upgrade (ADR-0004). Alembic's autogenerated revisions must be read and corrected by hand. An image change that brings a new ICU version requires an index rebuild on ICU-collated columns. | Storing data in a format other engines read directly; a database-free deployment. |
| B. MariaDB or MySQL + Alembic + SQLAlchemy 2 | DDL commits implicitly, so a failing migration can leave a half-applied schema. `TIMESTAMP` converts through the session time zone and has a limited range (2038, or 2106 in recent MariaDB); `DATETIME` is a local time with no zone. Polish case-insensitive collations are built in, which helps CUS-7. | Transactional migrations; a dedicated instant type. |
| C. SQLite + Alembic + SQLAlchemy 2 | One writer at a time on a file in a container volume; the web process and background sync contend for it. `ALTER TABLE` is limited (Alembic batch mode recreates tables). No date or time types at all; instants are text or numbers by convention. | A separate worker or second backend instance using the same database over the network; sharing the server with the identity server. |
| D. PostgreSQL 18 with plain-SQL migrations (e.g. Flyway, Sqitch) and no ORM | A second toolchain (Flyway needs a JVM in a container). No model-to-schema comparison, so drift between code and schema is caught only by tests. Hand-written queries for every table. | Alembic's `check` and autogenerate; one Python toolchain for code and schema. |
| E. A managed cloud database service | No server to operate. | The on-premises, cloud-agnostic constraint — rejected by the brief, section 5. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0002-C1 | A test starts PostgreSQL from the pinned 18.x image on an empty database and runs `alembic upgrade head` with exit 0; `SHOW server_version_num` returns a value from 180000 to 189999. |
| ADR-0002-C2 | `alembic heads` run in `backend/` prints exactly one revision. |
| ADR-0002-C3 | After `alembic upgrade head`, `alembic check` exits 0 (models and schema agree). |
| ADR-0002-C4 | `grep -rn "create_all" backend/app` and `grep -rn "drop_all" backend/app` return nothing, and `grep -rl "sqlalchemy" backend/app` lists only files under `backend/app/data/`. |
| ADR-0002-C5 | On the application database, `SHOW server_encoding` returns `UTF8`; `pg_database` reports `datlocprovider = 'i'` and `datlocale = 'pl-PL'`; and `SELECT datcollversion = pg_database_collation_actual_version(oid) FROM pg_database WHERE datname = current_database()` returns `true`. |
| ADR-0002-C6 | After `alembic upgrade head`, `information_schema.columns` lists no column of type `timestamp without time zone` in the application schema. |
| ADR-0002-C7 | A test stores the two instants `2026-10-25T02:30:00+02:00` and `2026-10-25T02:30:00+01:00` and reads back two distinct values equal to the inputs. |
| ADR-0002-C8 | A test computes the instant range of the Europe/Warsaw days 2026-03-29 and 2026-10-25 and gets lengths of 23 and 25 hours; `python -c "from zoneinfo import ZoneInfo; ZoneInfo('Europe/Warsaw')"` exits 0 inside the backend image. |
| ADR-0002-C9 | A test inserting directly through SQL, bypassing the services: a second customer with an existing `nip` fails with a unique violation (SQLSTATE `23505`); `nip` value `PL1234567890` or `DE123456789` fails with a check violation (SQLSTATE `23514`); two customers with `nip` `NULL` are both stored; two customers with the same `foreign_tax_id` are both stored. |
| ADR-0002-C10 | A test proves the comparison key of `"  Łukasz Żółć "` in `"ŁÓDŹ"` equals that of `"łukasz żółć"` in `"Łódź"`, including when `ó` is given decomposed (`o` + U+0301). |
| ADR-0002-C11 | After `alembic upgrade head`, `SELECT column_name, collation_name FROM information_schema.columns WHERE table_schema = 'public' AND (column_name = 'nip' OR column_name LIKE '%\_match\_key')` returns `C` as the collation of every row. |
| ADR-0002-C12 | Every PostgreSQL image reference in the repository is pinned: `grep -rhoE "postgres:[^[:space:]\"'@]+" --include="*.y*ml" --include="Dockerfile*" --include="*.py" .` prints only tags matching `^postgres:18\.[0-9]+-[a-z]+$`, and any reference without a tag carries `@sha256:`. |
| ADR-0002-C13 | `grep -rniF -e "datetime.now(" -e "utcnow(" -e "date.today(" -e "datetime.today(" -e "time.time(" -e "time.time_ns(" -e "func.now(" -e "current_date" -e "current_time" -e "localtime" -e " now()" -e "(now()" -e "=now()" -e ",now()" -e "'now()" -e "\"now()" backend/app` lists only lines in `backend/app/core/clock.py` (`current_time` also matches `CURRENT_TIMESTAMP`; `localtime` also matches `LOCALTIMESTAMP` and `time.localtime`). |
| ADR-0002-C14 | With the process zone and the database session zone both UTC, a test fixes the clock at `2026-10-22T22:30:00Z` (00:30 on 23 October in Warsaw) and gets "today" = `2026-10-23` with day range `[2026-10-22T22:00:00Z, 2026-10-23T22:00:00Z)`; fixed at `2026-12-31T23:30:00Z` it gets `2027-01-01`. |
| ADR-0002-C15 | A test of the wall-time resolver: `2026-10-25` `01:30` resolves to `2026-10-24T23:30:00Z`; `2026-10-25` `03:30` to `2026-10-25T02:30:00Z`; `2026-03-29` `03:00` to `2026-03-29T01:00:00Z`; `2026-10-25` `02:30` is rejected with the reason ambiguous and `2026-03-29` `02:30` with the reason nonexistent (the test asserts the reason for each input, not only the rejection); an endpoint receiving either rejected value answers HTTP 422 and stores nothing. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->

### 2026-10-28 — ADR-0002-C12 restated to match *Image pinning and ICU*

**What it restates.** *Image pinning and ICU* requires every reference to the PostgreSQL image to
name "a full version and base OS release — a tag of the form `18.<minor>-<OS release>` — or an
image digest", never a floating tag, so that a re-pull cannot change the ICU library silently.
ADR-0002-C12 as written accepts tags matching `^postgres:18\.[0-9]+-[a-z]+$`. That pattern passes
`postgres:18.1-alpine`, whose Alpine release moves with each re-pull, and fails
`postgres:18.1-alpine3.22`, which names the Alpine release. Its `grep` also reads files Git does not
track (`.venv`, `node_modules`), reads a `postgres://` connection string as an image reference,
never sees a reference with no tag (`image: postgres`), and does not check the form of a digest.
From this date:

- An **OS release** in `18.<minor>-<OS release>` is either `alpine` followed by its release number
  (for example `alpine3.22`) or a Debian release codename (lower-case letters only, for example
  `bookworm` or `trixie`). `alpine` with no release number is not an OS release; a tag ending in it
  is a floating tag. ADR-0004 (*Composition and placement*, *Images*, and ADR-0004-C2), which
  requires "the base OS release for PostgreSQL as ADR-0002 requires", reads the term with this
  meaning.
- ADR-0002-C12 reads: every reference to the PostgreSQL image (`postgres`, also written
  `library/postgres` or `docker.io/library/postgres`) in a file tracked by Git — an `image:` of the
  composition as `docker compose config` renders it, a `FROM` of a Dockerfile, a CI workflow, a
  test fixture — either has a tag matching `^18\.[0-9]+-(alpine[0-9]+\.[0-9]+|[a-z]+)$` other than
  `18.<minor>-alpine`, optionally followed by `@sha256:` and 64 lower-case hexadecimal digits, or
  has no tag and carries `@sha256:` followed by 64 lower-case hexadecimal digits. Each of these
  fails: a reference with neither a tag nor a digest; the tags `latest`, `18`, `18-<OS release>`,
  `18.<minor>` and `18.<minor>-alpine`; a digest that is not 64 lower-case hexadecimal digits; a
  tag given by a variable anywhere other than in the rendered composition. A file Git does not
  track is not read, and a connection string (`postgres://…`, `postgresql://…`) is not an image
  reference.

Every other rule and control of this decision is unchanged.

**Why.** A control must fail where its decision's rule is broken and pass where it holds. For
Alpine-based tags ADR-0002-C12 does the reverse of *Image pinning and ICU*, and it misses an
untagged reference entirely, so a check built to its letter would pass the floating tag the rule
forbids. Restating an accepted control is a declared deviation, approved by the human at gate 1 of
EKO-1-06 on 2026-10-28 (AQ-1 A, Issue #19).

### 2026-10-28 — PostgreSQL image first used

**What it records.** The walking skeleton (EKO-1-06, #19) first uses the PostgreSQL image
**`postgres:18.6-trixie`**: PostgreSQL 18.6 on the Debian release `trixie`, in the Debian-codename
form of an OS release that the addendum of 2026-10-28 on ADR-0002-C12 defines. It is the `image:` of
the `postgres` service in `compose.yaml` and the `FROM` of `backup/Dockerfile`, so `pg_dump` in
`backup` matches the server's major version (ADR-0004). The running server reports
`server_version_num` 180006, within the range ADR-0002-C1 requires.

Under *Image pinning and ICU*, this reference is now the baseline: a change to it is an explicit
upgrade, and an upgrade that brings a different ICU version includes the `REINDEX` and
`ALTER DATABASE … REFRESH COLLATION VERSION` and is recorded as an addendum to this decision. A
major-version upgrade is also recorded here (*Engine, migration tool, data access*). How a release
references this image by digest is recorded in ADR-0004's addendum of 2026-10-28 on *Images*.

No rule or control of this decision changes.

**Why.** *Image pinning and ICU* makes the image reference the only thing that fixes the ICU
library, so the version first used is the point every later upgrade is compared against. Approved
by the human at gate 2 of EKO-1-06 on 2026-10-28 (Issue #19, PR #57). This is not a deviation.

### 2026-10-28 — The `data` layer uses SQLAlchemy's synchronous API

**What it adds.** *Forward references* leaves open whether the `data` layer uses SQLAlchemy's
synchronous or asynchronous session API: the walking skeleton (EKO-1-06) proposes it, and it is
recorded as an addendum before the first product task that persists data. From this date:

- The `data` layer uses SQLAlchemy's **synchronous** API (`Engine`, `Session`) with psycopg 3 in
  synchronous mode. `AsyncEngine` and `AsyncSession` are not used.
- A route handler, or a dependency of one, that reaches the `data` layer, directly or through a
  service, is a plain `def`, which FastAPI runs in its thread pool. No `async def` handler or
  dependency calls the `data` layer.
- Alembic (`backend/migrations/`) and the worker use the same synchronous API.

**How a request waits for a connection.** In each backend process, the engine built by
`create_app_engine` (`backend/app/data/database.py`) holds a pool of `pool_size` connections and
opens at most `max_overflow` more. The composition sets 5 + 5, so one process holds at most 10
connections, and the two web processes at most 20 (ADR-0003's addendum of 2026-10-28 on the
connection budget). FastAPI runs plain `def` handlers in a thread pool of 40 threads per process,
the default of its AnyIO thread limiter. The thread pool is therefore larger than the connection
pool: up to 40 requests per process can run at once, and when more than 10 of them need a
connection at the same time, those beyond 10 wait on pool checkout, each holding its thread while
it waits. `create_app_engine` sets no `pool_timeout`, so a waiting request waits up to
SQLAlchemy's default of 30 seconds and then fails.

**Why this is acceptable.** The system has about ten users (brief, section 5). More than 10
concurrent database requests in one process means more requests holding a connection at the same
instant than the company has users. A request that waits on checkout waits for another request's
database work to finish, not for the full 30 seconds, unless a request holds its connection that
long. An asynchronous engine would not remove this wait: it has the same pool and the same
checkout, and it frees only the thread, which is not the scarce resource here. The synchronous API
keeps one style across handlers, Alembic, the worker and tests. It avoids the pitfalls of the
asynchronous one: lazy loading raising `MissingGreenlet`, a session shared across tasks, and a
blocking call hidden in an `async def`. The walking skeleton already runs this way (its health
route is a plain `def`).

**Cost.**

- A request holds a thread while it waits on the database, including on pool checkout.
- Under a burst of more than 10 concurrent database requests in one process, the requests beyond
  10 queue for up to 30 seconds before they fail. `pool_timeout` stays at SQLAlchemy's default;
  this addendum leaves that wait as a stated cost. Setting `pool_timeout` is a change to this
  decision, recorded as an addendum.
- A future long-polling or streaming endpoint needs an `async def` handler with no `data` access,
  or a revisit of this decision by addendum.

**Rejected.** `AsyncSession` with an asynchronous psycopg engine: a second style for Alembic
(`run_sync`) and the worker, and stricter loading rules, with the same pool checkout wait, for no
gain at this scale.

Every other rule and control of this decision is unchanged.

**Why.** This closes the open point named under *Forward references*, before the first product task
that persists data. The developer's draft proposed the synchronous API but gave its reason the wrong
way round, as if the thread pool were smaller than the connection pool; the Reviewer showed this
(EKO-1-06, U-01), and this addendum states the actual mechanism. Approved by the human at gate 2 of
EKO-1-06 on 2026-10-28 (Issue #19, PR #57). This is not a deviation: it decides a point this
decision left open.
