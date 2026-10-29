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
- **2026-10-23:** ADR-0003 (identity and access, EKO-1-02) adds the backend layer `auth`
  (`backend/app/auth/`), which must not depend on `services`, `api` or `integrations`. The rows
  `domain`, `services`, `data`, `core` and `integrations` of the layer table above add `auth` to
  "Must not depend on"; the row `api` is unchanged, and only `api` and `backend/app/main.py` depend
  on `auth`. The ruff `TID251` bans of ADR-0001-C11 follow these rows. Reason: the caller's
  identity enters the inner layers as a value defined in `domain`, so no inner layer reads a
  token, a claim or the session; without this rule an import of `auth` from `domain` would pass
  the layer check.

### 2026-10-29 — ADR-0001-C6, C8, C10, C13 and C14 restated; the scope of C11 stated

**Status:** Accepted 2026-10-29, as a declared deviation (gate 1 of EKO-1-10, Issue #51).

**What it restates.** EKO-1-10 (#51) builds the code-level controls of this decision as checks
that CI runs on every pull request. Read to the letter, five of them fail where their rule holds or
pass where it is broken (holes R-09, R-12 and R-13, forwarded from #19):

- ADR-0001-C10's pattern `environ` also matches the word `environment` in a field name, a string
  or a docstring, which reads nothing. Its list misses `starlette.config`, a route to the process
  environment that *Constraint 1* forbids ("'Read' covers every route to the process
  environment").
- ADR-0001-C13's list misses reads of the device's zone that *Constraint 3* forbids: the
  local-zone setters, `toDateString`, `toTimeString`, and a `Date` turned into text by
  interpolation.
- Neither list names `toJSON`, which gives the same UTC text as `toISOString`. ADR-0001-C14's
  list also misses the UTC setters, and it does not name the browser's clock (`Date.now()`,
  `new Date()`), from which *Constraint 3* has the helper take the current instant.
- ADR-0001-C8 still holds while a second ruff configuration replaces `backend/pyproject.toml` for
  some files. Ruff applies the configuration nearest to a file, so a root `pyproject.toml` with
  `[tool.ruff]`, or a nested `ruff.toml` without `extend`, drops `TID252`, `TID251` and the `S`
  rules for the files below it, and `ruff check backend` still exits 0.
- ADR-0001-C6 names neither the case of `password` nor the media type of the body. The password
  form a client would send is `application/x-www-form-urlencoded`, and FastAPI places a body's
  schema behind a `$ref`.

From this date:

- **ADR-0001-C10 reads:** No file under `backend/app/` other than `backend/app/core/settings.py`
  reads the process environment. In every other file under `backend/app/`, comments and
  docstrings included, each of these is a finding, matched as a whole name and never as part of a
  longer word:
  - `os.environ`, and `environ` imported from `os` in any form, `from os import environ as env`
    included;
  - `os.getenv`, and `getenv` imported from `os`;
  - `os.putenv`;
  - an import of `pydantic_settings`, and a class deriving from `BaseSettings`;
  - an import of `dotenv` or of any of its loaders;
  - an import of `starlette.config`, or of its `Config` or `environ`;
  - `os.environb` and `os.getenvb`, and either name imported from `os`.

  The word `environment` in an identifier, a string or a docstring is not a finding, and neither
  is `ConfigDict`. The exemption is that one file. Neither `backend/app/core/` nor a file such as
  `backend/app/core/settings_extra.py` shares it.
- **ADR-0001-C13 reads:** the Vitest half is unchanged. Grep half: none of these appears in any
  file under `frontend/src/`, `frontend/src/time/warsaw.ts` included. Each is judged by name,
  comments included:
  - the local-zone getters `.getFullYear(`, `.getMonth(`, `.getDate(`, `.getDay(`, `.getHours(`
    and `.getMinutes(`, and `getTimezoneOffset`;
  - the local-zone setters `.setDate(`, `.setHours(`, `.setFullYear(`, `.setMonth(`,
    `.setMinutes(`, `.setSeconds(` and `.setMilliseconds(`;
  - `toDateString` and `toTimeString`, and `Date(` called without `new`;
  - a value of type `Date` in a template literal or in string concatenation. It is judged by its
    TypeScript type, a value reached through a variable included;
  - `.toJSON(`, on any value.
- **ADR-0001-C14 reads:** the Vitest half is unchanged. Grep half: none of these appears in any
  file under `frontend/src/` other than `frontend/src/time/warsaw.ts`. The exemption is that one
  file, not its directory and not a file whose name begins with `warsaw`. Each is judged by name,
  comments included:
  - the existing list: `toISOString`, `getUTC`, `Date.UTC`, `toLocale`, `Intl.DateTimeFormat`,
    `Temporal.`, `date-fns`, `dayjs`, `luxon`, `'moment` and `"moment`, with no exemption for
    `frontend/src/api/`;
  - `new Date(` with two or more arguments, as before;
  - the UTC setters `.setUTC…(` (`.setUTCFullYear(`, `.setUTCHours(` and the others);
  - `Date.now(`, `new Date()` with no argument, and `new Date` with no parentheses.

  `new Date(` with one argument (an instant from a number or from an RFC 3339 string) and
  `performance.now()` are not findings.
- **ADR-0001-C8 gains a second sentence:** The ruff configuration in effect for every file under
  `backend/` is `backend/pyproject.toml`. For the directories ADR-0001-C11 scopes, it is extended
  by one `ruff.toml` in each of `backend/app/domain/`, `backend/app/services/`,
  `backend/app/data/`, `backend/app/integrations/`, `backend/app/core/` and `backend/app/auth/`,
  each with `extend = "../../pyproject.toml"`. Every other tracked ruff configuration fails:
  - a `[tool.ruff]` table in any `pyproject.toml` other than `backend/pyproject.toml`, the
    repository root's included;
  - any other `ruff.toml` or `.ruff.toml`, including `backend/ruff.toml`, `backend/.ruff.toml`
    and one in `backend/app/api/`;
  - one of the six whose `extend` names any other file.

  Each of the six holds only its `extend` and the `banned-api` entries of its layer's row, so
  none can switch off a rule that `backend/pyproject.toml` selects.
- **ADR-0001-C6 reads:** the migrations half is unchanged. OpenAPI half: the OpenAPI document of
  the backend contains no request-body property whose name contains `password`, compared without
  regard to case. This covers any media type of the body (JSON, form, multipart), any depth, and a
  property reached through a `$ref`. It also contains no query, header, cookie or path
  parameter whose name contains `password`.

**What it states about ADR-0001-C11.** "The layer table" of ADR-0001-C11 is the table of
*Repository layout and layers*, with this decision's addendum of 2026-10-23. Its rows are
`domain`, `services`, `data`, `integrations`, `core`, `auth` and `api`, each scoped to its
directory. `layer-dependencies.md` may also hold a row for one file outside the layer
directories, such as `backend/app/worker.py` (ADR-0006, *Background work*). Such a row is not a
layer directory and gets no `TID251` scope. Ruff applies a configuration to a directory, and
`backend/app/` also holds `main.py`, which may depend on every layer. That file's rule is enforced
by ADR-0001-C9's layer check. A static test also reads every import of that file, so the form
`from app import api` is caught as well. The text of ADR-0001-C11 is unchanged.

Every other rule and control of this decision is unchanged.

**Why.** A control must fail where its decision's rule is broken and pass where it holds. A check
built to the letter of these five would do neither reliably. Two items do more than restate a
control: they widen a rule of *Constraint 3*.
- Outside the helper, the frontend does not read the browser's clock (`Date.now()`,
  `new Date()`). So "now" has one source in the frontend, as it has `clock.py` in the backend
  (ADR-0002).
- `toJSON` is banned everywhere in `frontend/src/`, `warsaw.ts` included. It gives the same UTC
  text as `toISOString`, and the helper has no need for it.

The parameter half of ADR-0001-C6 follows *Constraint 2* ("no backend endpoint accepts a
user's password"), which names no channel. A password sent as a query parameter also ends up in
logs. Restating accepted controls is a declared deviation. It follows the precedent of ADR-0002's
addendum of 2026-10-28 on ADR-0002-C12. Approved by the human at gate 1 of EKO-1-10 on 2026-10-29 (G-4 A,
Issue #51).
