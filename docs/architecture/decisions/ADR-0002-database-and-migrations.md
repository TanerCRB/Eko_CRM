# ADR-0002 — Database engine, migration tool and data access

**Status:** Draft — pending approval
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
| Database engine | PostgreSQL, major version 18, run from a container image pinned to that major version |
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
  so a failing revision leaves the schema unchanged.
- **Data access stays in its layer.** The domain layer never imports SQLAlchemy; services reach
  persistence only through the `data` layer (ADR-0001 layer rules).
- **Major-version upgrades** of PostgreSQL are recorded as an addendum to this decision.

### Points in time and Europe/Warsaw days

- A **point in time** (visit start and end, change timestamps, sync timestamps) is stored as
  `timestamp with time zone`, i.e. an absolute instant. `timestamp without time zone` is not used
  for points in time. Application connections run with session time zone UTC.
- A **calendar date** with no time of day (an action's due date) is stored as `date`, interpreted
  as a Europe/Warsaw calendar date.
- **Europe/Warsaw days are computed in the application**, with the IANA zone `Europe/Warsaw` from
  Python's `zoneinfo`. A day, a week or a period becomes a half-open range of instants
  `[start of first local day, start of the day after the last)`, so a 23-hour or 25-hour DST day is
  covered exactly; queries filter instants by that range. The backend ships the IANA time-zone data
  as a Python dependency (`tzdata`), so the result does not depend on the image's operating system.
- An ambiguous local time (the repeated hour in October) maps to two distinct instants, and both
  can be stored. Rejecting nonexistent and ambiguous local input is a validation rule of the task
  that accepts it (EKO-4-01), not a storage rule.

### Polish text, case-insensitive comparison, NIP uniqueness

- The database is created with encoding `UTF8`. Its default collation uses the ICU provider with
  locale `pl-PL`, so ordering follows the Polish alphabet (Ł after L, not after Z). An ICU library
  change in a new image can change that ordering; PostgreSQL reports a collation version mismatch,
  and the affected indexes are rebuilt as part of the upgrade.
- Text is stored in Unicode NFC, normalised by the application before it is written, so a composed
  and a decomposed "ó" are the same stored value.
- **Case-insensitive equality does not depend on a database collation.** Where a rule compares text
  ignoring case and edge spaces (CUS-7, name in the same town), the application computes a
  comparison key with one domain function (NFC, trim of leading and trailing whitespace, Unicode
  case folding) and the `data` layer stores it beside the displayed value and indexes it. The key
  is written only by that function. CUS-7 warns and does not block, so this key carries no unique
  constraint.
- **NIP** is stored only in its canonical form (CUS-5: a Polish NIP without hyphens, spaces or the
  `PL` prefix). Company-wide uniqueness (CUS-6) is enforced by a **unique constraint in the
  database**, not only by a check in a service, so two concurrent saves cannot both succeed. A
  customer without a NIP stores `NULL`, and any number of customers may have none. The stored form
  keeps a Polish NIP distinguishable from a foreign tax ID, so either answer to whether foreign tax
  IDs share the uniqueness rule (a product rule, decided in EKO-3-03) can be enforced.

### Background work

PostgreSQL row locking (`SELECT … FOR UPDATE SKIP LOCKED`) and `LISTEN`/`NOTIFY` keep a
database-backed job queue available. Whether background work uses it is decided in ADR-0006.

### Forward references (not decided here)

- ADR-0003 (#15) — where the identity server stores its own data, and whether it shares this
  PostgreSQL server.
- ADR-0004 (#16) — database container composition, credentials and secret handling, daily
  off-server backup, restore procedure, encryption at rest of volumes and backups.
- ADR-0005 (#17) — which tables and columns hold personal data, retention, archiving vs. erasure,
  what may appear in logs.
- ADR-0006 (#18) — storage and encryption of Google tokens; the background-work mechanism.

Also not decided here: whether the `data` layer uses SQLAlchemy's synchronous or asynchronous
session API. The walking skeleton (EKO-1-06) proposes it, and it is recorded as an addendum before
the first product task that persists data.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. PostgreSQL 18 + Alembic + SQLAlchemy 2** (chosen) | A database server to operate, back up and upgrade (ADR-0004). Alembic's autogenerated revisions must be read and corrected by hand. An ICU upgrade can require an index rebuild. | Storing data in a format other engines read directly; a database-free deployment. |
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
| ADR-0002-C5 | On the application database, `SHOW server_encoding` returns `UTF8`, and `pg_database` reports `datlocprovider = 'i'` and `datlocale = 'pl-PL'`. |
| ADR-0002-C6 | After `alembic upgrade head`, `information_schema.columns` lists no column of type `timestamp without time zone` in the application schema. |
| ADR-0002-C7 | A test stores the two instants `2026-10-25T02:30:00+02:00` and `2026-10-25T02:30:00+01:00` and reads back two distinct values equal to the inputs. |
| ADR-0002-C8 | A test computes the instant range of the Europe/Warsaw days 2026-03-29 and 2026-10-25 and gets lengths of 23 and 25 hours; `python -c "from zoneinfo import ZoneInfo; ZoneInfo('Europe/Warsaw')"` exits 0 inside the backend image. |
| ADR-0002-C9 | A test inserting a second customer with an existing canonical NIP directly through SQL, bypassing the services, fails with a unique violation (SQLSTATE `23505`); two customers without a NIP are both stored. |
| ADR-0002-C10 | A test proves the comparison key of `"  Łukasz Żółć "` in `"ŁÓDŹ"` equals that of `"łukasz żółć"` in `"Łódź"`, including when `ó` is given decomposed (`o` + U+0301). |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->
