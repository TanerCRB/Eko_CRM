# ADR-0001 — Application stack and backend layering

**Status:** Accepted 2026-10-23
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

No code exists, and every product task (EKO-2 onwards) needs a recorded stack and layout. The
layer table and the sensitive-paths register
([`layer-dependencies.md`](../layer-dependencies.md),
[`architecture-sensitive-paths.md`](../architecture-sensitive-paths.md)) are provisional until this
decision exists. Two requirements from the brief
([`project-brief.md`](../../product/project-brief.md), section 5) are **constraints this choice
must satisfy**, not open questions: the system runs on-premises in containers, cloud-agnostic; and
user accounts live in an external identity server, independent of Google.

## Decision

### Stack

| Part | Choice |
|---|---|
| Backend language and runtime | Python 3.12 (CPython) |
| Backend web framework | FastAPI |
| Validation and API schemas | Pydantic v2 |
| Backend packaging | uv: `backend/pyproject.toml` is the manifest, `backend/uv.lock` the lock file |
| Backend tests and lint | pytest; ruff |
| Frontend language | TypeScript, compiler option `strict` on |
| Frontend UI library | React |
| Frontend build tool | Vite, producing a static single-page application |
| Frontend package manager | pnpm: `frontend/package.json` is the manifest, `frontend/pnpm-lock.yaml` the lock file |
| Frontend tests | Vitest |

This matches the stack named in `CLAUDE.md`, with one addition: `CLAUDE.md` names no Python
package manager; uv is chosen because it produces one cross-platform lock file that matches the
existing `backend/*.lock` row of the sensitive-paths register and installs reproducibly inside a
container build. Updating `CLAUDE.md` to name uv is a follow-up outside EKO-1-01.

### Constraint 1 — every component runs as a container image

Every runtime component (backend, frontend, and later the database and identity server) runs as a
container image; no component depends on a runtime installed on the host. The stack meets this as
follows:

- The backend image installs Python and the locked dependencies (`uv sync --locked`) at build time;
  the host needs only a container runtime.
- The frontend is built by Vite into static files at image build time. Node.js and pnpm are
  **build-time only**: the production frontend image serves static files and contains no Node.js
  runtime.
- Configuration and secrets reach the backend only as environment variables read in one place,
  `backend/app/core/settings.py`; nothing is read from host paths outside the container. "Read"
  covers every route to the process environment — `os.environ` in any import form, `os.getenv`,
  a pydantic-settings `BaseSettings` class, a dotenv loader — so none of them appears in another
  file under `backend/app/`.

The container runtime, image composition, HTTPS exposure, the static file server and secret
handling are **not** decided here — forward reference: ADR-0004 (EKO-1-03, #16).

### Constraint 2 — authentication is delegated to an external identity server

The application keeps **no password store of its own**: no table, column or file holds user
passwords or password hashes, and no backend endpoint accepts a user's password. Authentication is
delegated to an external identity server over **OpenID Connect** (on OAuth 2.0). The backend
accepts a caller's identity and roles only as asserted by that identity server, verified on every
request by one application-wide FastAPI dependency (wired in `backend/app/main.py`, implemented
under `backend/app/auth/`). Accounts never depend on Google; a Google account is linked later for
the calendar only.

Not decided here — forward reference: ADR-0003 (EKO-1-02, #15): the identity server product, where
its own data is stored, the browser flow (tokens held by the single-page application or a backend
session), how roles rep / manager / administrator are carried, account deactivation and password
reset.

### Constraint 3 — the HTTP API is the contract between `backend/` and `frontend/`

The API is JSON over HTTP(S). The OpenAPI document that FastAPI generates from the Pydantic schemas
is the single description of that contract; the frontend's typed client in `frontend/src/api/`
follows it. Three kinds of time value cross the API, and each has one form:

- **An instant** (a point in time the system produced or received, e.g. a change or sync
  timestamp) crosses as an RFC 3339 string with an explicit offset, in both directions. A request
  value without an offset is rejected at the boundary: every Pydantic field holding an instant is
  typed `AwareDatetime` (or an equivalent that refuses naive values), never plain `datetime`.
- **A wall time entered by a user** (e.g. a visit's start and end as typed into a form) crosses as
  a local date `YYYY-MM-DD` and a local time `HH:MM`, with no offset and no zone; both mean
  Europe/Warsaw. The frontend does not convert it to an instant. The backend resolves it to an
  instant and rejects an ambiguous or nonexistent local time (ADR-0002, "Wall time entered by a
  user").
- **A calendar date** with no time of day crosses as `YYYY-MM-DD`, meaning a Europe/Warsaw date.

The frontend displays every instant and every date in the `Europe/Warsaw` zone named explicitly,
never in the browser's or device's zone; a user whose device is set to another zone sees the same
values as a user in Poland.

**The frontend's "today" and its day and week bounds come from one helper module,**
`frontend/src/time/warsaw.ts`. It takes the current instant from the browser's clock and is the
only frontend code that turns an instant into a Europe/Warsaw calendar date, wall time or display
text, always through `Intl.DateTimeFormat` with `timeZone: 'Europe/Warsaw'`. "Today", the days of
the My day date strip (EKO-4-01), and the bounds of the DSH-1 presets (today, the Mon–Sun week and
the longer periods) are computed there from that Europe/Warsaw date. No other frontend code derives
a calendar date or a wall time from an instant — neither in UTC (`toISOString`, the `getUTC*`
getters, `Date.UTC`) nor in the device's zone (the local `get*` getters, a date library's
local-zone functions such as date-fns `format` or `startOfWeek`, `toLocale*String`,
`Intl.DateTimeFormat` without `timeZone`, `Temporal.Now`, `new Date(y, m, d)`). The helper imports
none of the frontend layers (`fe-api`, `fe-components`, `fe-features`), so each of them may use it.

The helper is chosen over taking "today" from the backend's clock (e.g. returned by the API)
because the date strip and the presets then render without a prior request and roll over at
midnight without a reload or a refetch. Its cost: the frontend's date follows the device's clock
(not its zone), so a device whose clock is off by minutes can, in those minutes around midnight,
show a different "today" than the one the backend's clock uses for due-today and overdue
(ADR-0002); the backend's comparison stays authoritative.

### Repository layout and layers

```
backend/
  pyproject.toml, uv.lock, Dockerfile
  app/                 Python package `app`; imports are absolute (`app.<layer>`)
    main.py            application factory; wires the access dependency and error handling
    core/              settings.py — the one place configuration and secrets are read;
                       clock.py — the one source of "now" and "today" (ADR-0002)
    domain/            entities and rules; knows no storage, transport or external system
    services/          use cases; call domain, data and integrations
    data/              persistence (ADR-0002)
    integrations/      adapters to external systems (Google Calendar: ADR-0006)
    auth/              access dependency and permissions (ADR-0003)
    api/               FastAPI routers and HTTP schemas — the outermost layer
  migrations/          schema migrations (ADR-0002)
  tests/
frontend/
  package.json, pnpm-lock.yaml, vite.config.ts, Dockerfile
  src/api/  src/components/  src/features/
  src/time/warsaw.ts   the one source of "today" and of Europe/Warsaw dates (Constraint 3)
  tests/               mirrors src/
```

Backend layer rules (enforced through the layer table and `scripts/layer-check.sh`):

| Layer | Must not depend on |
|---|---|
| domain | services, data, api, integrations |
| services | api |
| data | services, api, integrations |
| integrations | services, data, api |
| core | domain, services, data, api, integrations |
| api | — |

The rows for domain, services, data and api keep every rule of the provisional table and add
`integrations`; `integrations` and `core` are new layers. `auth` gets no layer row until ADR-0003
fixes what it may depend on. Frontend layers (`fe-api`, `fe-components`, `fe-features`) are kept
as provisionally recorded.

Backend imports between layers are absolute (`from app.data …`): `scripts/layer-check.sh` does not
resolve Python relative imports, so relative imports are banned by lint rather than left
unchecked.

`scripts/layer-check.sh` also misses a layer imported as a member of the package
(`from app import data`), because it reads only the module name `app`. The same rules are
therefore enforced a second time by ruff's banned-api rule (flake8-tidy-imports, `TID251`), scoped
to each layer's directory and listing the layers that layer must not depend on, so every import
form — `from app import data`, `import app.data`, `from app.data import x`,
`import app.data as d` — is a lint error where the table forbids it. The layer table above is the
source; the ruff configuration follows it, and a difference between the two is a defect in the
ruff configuration.

### Background work

Visit synchronisation needs work outside a request (VIS-6 latency, VIS-7 retry of Unsynchronised
visits). ADR-0001 fixes only that this work is written in Python inside `backend/`, under the same
layer rules, and ships in the backend image — no second language runtime. The mechanism (in-process
scheduler, separate worker process, database-backed queue or message broker) is **forwarded to
ADR-0006** (EKO-1-05, #18), because the choice depends on facts only that decision establishes:
push notifications versus polling, retry cadence, and the token handling of the Google
integration. ADR-0002's database engine keeps a database-backed queue available, so ADR-0006 is not
forced to add a broker.

### Forward references (not decided here)

- ADR-0003 (#15) — identity server product and its storage, login flow, roles, deactivation.
- ADR-0004 (#16) — container runtime and composition, HTTPS, secret handling, backup and restore;
  when and by which single process schema migrations run on deploy and restart, and how
  expand → deploy → contract is carried out across releases.
- ADR-0005 (#17) — personal data: which modules hold it, logging, retention, archiving vs. erasure.
- ADR-0006 (#18) — Google Calendar integration and the background-work mechanism.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. Python 3.12 / FastAPI / Pydantic v2 with uv; React / TypeScript / Vite static SPA with pnpm** (chosen) | Persistence, migrations and auth are assembled from separate libraries (ADR-0002, ADR-0003) rather than bundled. Python 3.12 is in its security-only phase, with end of life in October 2028: a minor-version upgrade is due within the project's life, recorded as an addendum. Two languages in the monorepo, two toolchains in CI. | Server-side rendering of pages; a single language across backend and frontend. |
| B. Django with Django REST Framework; same frontend | Django's built-in user and password model must be switched off to meet Constraint 2; the admin and session features that justify Django go largely unused with an external identity server and an SPA. Departs from the stack in `CLAUDE.md`. | ADR-0002's choice of migration tool and data access (Django's ORM and migrations come bundled); FastAPI's generated OpenAPI contract without an extra library. |
| C. TypeScript backend (Node.js, e.g. NestJS); same frontend | One language across the repository, but departs from `CLAUDE.md` and from the backend role's Python setup; the process scripts' Python import patterns and the planned `app.*` layout need rewriting. | The Python ecosystem for the backend; the `developer-backend` role as configured. |
| D. Server-rendered React (e.g. Next.js) instead of a Vite SPA | A Node.js runtime in production, a second server-side component holding session state and calling the backend; more surface for Constraint 2. | A frontend image that is only static files; a frontend with no server-side secrets. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0001-C1 | `backend/pyproject.toml` declares `requires-python` admitting 3.12 and no lower minor, and lists `fastapi` and `pydantic` (major version 2) as dependencies; `uv lock --locked` run in `backend/` exits 0. |
| ADR-0001-C2 | `frontend/package.json` lists `react`, `typescript` and `vite`, and its `packageManager` field names pnpm; `pnpm install --frozen-lockfile` run in `frontend/` exits 0; no `package-lock.json` or `yarn.lock` exists in the repository. |
| ADR-0001-C3 | `frontend/tsconfig*.json` sets `"strict": true`. |
| ADR-0001-C4 | `backend/Dockerfile` and `frontend/Dockerfile` exist, and each image builds with exit 0 in a CI job that installs no Python or Node.js on the runner. |
| ADR-0001-C5 | Running `node --version` inside the production frontend image fails (no Node.js runtime present). |
| ADR-0001-C6 | `grep -rniE "passw(or)?d" backend/migrations` returns no column definition, and the OpenAPI document served by the backend contains no request-body property whose name contains `password`. |
| ADR-0001-C7 | A test fetches the backend's OpenAPI document and gets a valid OpenAPI 3.x document. |
| ADR-0001-C8 | `ruff check backend` runs with relative imports banned (rule `TID252`, `ban-relative-imports = "all"`) and exits 0. |
| ADR-0001-C9 | `bash scripts/layer-check.sh origin/main HEAD` exits 0 on every pull request that changes `backend/app/` or `frontend/src/`. |
| ADR-0001-C10 | No file under `backend/app/` other than `backend/app/core/settings.py` reads the process environment: `grep -rl -e environ -e getenv -e putenv -e pydantic_settings -e BaseSettings -e dotenv backend/app` lists only that file (the pattern catches `os.environ`, `from os import environ`, `os.getenv`, a pydantic-settings import or `BaseSettings` subclass, and a dotenv loader). |
| ADR-0001-C11 | `ruff check backend` reports `TID251` on each line of a fixture file placed in `backend/app/domain/` that contains, one per line, `from app import data`, `import app.data`, `from app.data import x` and `import app.data as d`, and exits non-zero; the same four lines in a fixture under `backend/app/services/` produce no `TID251`. For every row of the layer table, each layer in "Must not depend on" is banned in that layer's directory: a fixture `from app import <forbidden>` in each layer directory is reported. |
| ADR-0001-C12 | A test walks every request and response model reachable from the application's routes and finds no field whose annotation is, or contains, plain `datetime.datetime` (instants are `AwareDatetime`); and a test sending an instant without an offset (`2026-10-25T02:30:00`) to each endpoint that accepts an instant gets HTTP 422. |
| ADR-0001-C13 | With the test process's zone set to a zone other than Europe/Warsaw (`TZ=America/New_York`), a Vitest test renders the instant `2026-10-24T23:30:00Z` as 25 October 2026, 01:30 and `2026-03-29T01:00:00Z` as 29 March 2026, 03:00; and `grep -rnF -e ".getFullYear(" -e ".getMonth(" -e ".getDate(" -e ".getDay(" -e ".getHours(" -e ".getMinutes(" -e "getTimezoneOffset" frontend/src` returns nothing (no date part read in the browser's zone). |
| ADR-0001-C14 | With the test process's zone set to `TZ=America/New_York` and Vitest's fake time, a test of `frontend/src/time/warsaw.ts` gets "today" = `2026-10-23` at `2026-10-22T22:30:00Z`, "today" = `2027-01-01` at `2026-12-31T23:30:00Z`, and "this week" = `2026-10-26` to `2026-11-01` at `2026-10-25T23:30:00Z`; `grep -rnF -e "toISOString" -e "getUTC" -e "Date.UTC" -e "toLocale" -e "Intl.DateTimeFormat" -e "Temporal." -e "date-fns" -e "dayjs" -e "luxon" -e "'moment" -e "\"moment" frontend/src` lists only lines in that file; and `grep -rnE "new Date\([^)]*," frontend/src` lists only lines in that file. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->
