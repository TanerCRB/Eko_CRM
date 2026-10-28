# Plan

One entry per task; the identifier is reserved before work starts, as its own commit
(`FrameworkDoc.md`, section 9 — identifiers are a shared resource). A task is checked off only at
gate 3, by a human, with a link to the test or artifact that proves it. Entry format:
`process/registers/plan.md`.

Identifiers: `EKO-<block>-<nn>`, e.g. `EKO-1-01`.

## EKO-1 — Foundations

- [x] **EKO-1-01** — Record the stack and persistence decisions (ADR-0001 stack, ADR-0002
  database and migration tool).
  *Done when:* both decisions are in `docs/architecture/decisions/` with status "Accepted
  <date>", and `docs/architecture/layer-dependencies.md` and
  `docs/architecture/architecture-sensitive-paths.md` cite them instead of "pending".
  **Out of scope (explicit):** any product code — the decisions come first.
  **Done 2026-10-23:**
  [`ADR-0001-application-stack.md`](architecture/decisions/ADR-0001-application-stack.md) and
  [`ADR-0002-database-and-migrations.md`](architecture/decisions/ADR-0002-database-and-migrations.md)
  (status "Accepted 2026-10-23"), both registers citing them, merged in
  [PR #30](https://github.com/TanerCRB/Eko_CRM/pull/30) — QA's document checks verified at
  `90af4f9`, every named mutation killed; seven recorded exceptions for the evidence chain
  (`docs/architecture/exception-register.md`, follow-up #29).

- [x] **EKO-1-02** — Record the identity decision (ADR-0003).
  *Done when:* ADR-0003 is in `docs/architecture/decisions/` with status "Accepted <date>" and
  fixes the identity server (Keycloak preferred), how the roles rep / manager / administrator
  reach the backend, account deactivation, password reset over the company SMTP mailbox, and that
  accounts never depend on Google.
  **Out of scope (explicit):** any implementation; Google account linking — EKO-1-05.
  **Done 2026-10-23:**
  [`ADR-0003-identity-and-access.md`](architecture/decisions/ADR-0003-identity-and-access.md)
  (status "Accepted 2026-10-23", after two fix rounds), the ADR-0001 addendum on the `auth` layer and
  both registers citing ADR-0003, merged in [PR #34](https://github.com/TanerCRB/Eko_CRM/pull/34) —
  QA's document checks (`tests/doc-checks/EKO-1-02.sh`) verified at `50e6e6d`, every named
  mutation killed; no recorded exceptions. Forwarded: who reviews admin events and ADR-0003-C22
  (ADR-0004, #16); the Keycloak behaviours behind ADR-0003-C1, C7, C10 and C14..C20 (EKO-1-06, #19).

- [x] **EKO-1-03** — Record the deployment and backup decision (ADR-0004).
  *Done when:* ADR-0004 is "Accepted <date>" and fixes the container runtime and composition, the
  cloud-agnostic constraints, HTTPS exposure under a company domain, secret handling, a daily
  off-server database backup and the restore procedure, with the company IT department as
  operator.
  **Out of scope (explicit):** provisioning the real server; the domain — the human provides it
  later.
  **Done 2026-10-25:**
  [`ADR-0004-deployment-and-recovery.md`](architecture/decisions/ADR-0004-deployment-and-recovery.md)
  (status "Accepted 2026-10-24", revised in place in two fix rounds), the dated ADR-0003 addendum
  on the backup role's connection budget and the sensitive-paths register citing ADR-0004, merged
  in [PR #39](https://github.com/TanerCRB/Eko_CRM/pull/39) — QA's document checks
  (`tests/doc-checks/EKO-1-03.sh`) verified at `2642526`, all 157 named mutations killed; eleven
  recorded exceptions (`architecture/exception-register.md`), their fixes entry conditions of
  EKO-1-08 (#36) and EKO-1-06 (#19). Forwarded: the first tested restore, the network topology
  and the backup and restore controls (EKO-1-08, #36); the composition and the controls behind
  migrations, bootstrap and the backup role (EKO-1-06, #19); shipping Keycloak events off the
  server and erasure in backups (EKO-1-04, #17); self-service resets in the off-server record (#38).

- [x] **EKO-1-04** — Record the personal-data handling decision (ADR-0005).
  *Done when:* ADR-0005 is "Accepted <date>" and names the modules holding customer personal
  data, what is logged and what never is, archiving vs. erasure, and that only synthetic data is
  used until the GDPR impact assessment; `docs/architecture/architecture-sensitive-paths.md`
  lists those paths.
  **Out of scope (explicit):** the GDPR impact assessment — after the MVP; erasure — later.
  **Done 2026-10-27:**
  [`ADR-0005-personal-data.md`](architecture/decisions/ADR-0005-personal-data.md) (status
  "Accepted 2026-10-25", revised in place in four fix rounds under the human's decisions
  D-1..D-12) and the sensitive-paths register citing ADR-0005 with the `personal-data` class,
  merged in [PR #44](https://github.com/TanerCRB/Eko_CRM/pull/44) — QA's document checks
  (`tests/doc-checks/EKO-1-04.sh`, 93 checks) verified at `60add45`, all 262 named mutations
  killed; six recorded exceptions (`architecture/exception-register.md`), fixed by an ADR-0005
  addendum in #43. Forwarded: the fields sent to Google, token storage and erasure's effect on
  calendar events (EKO-1-05, #18); the re-apply at the first tested restore and restore-host
  cleanup (EKO-1-08, #36); shipping Keycloak events off the server (EKO-1-09, #41); the Keycloak
  log and event settings (EKO-1-06, #19); recording an erased identifier with a time taken after
  the commit (the task that builds the permanent-erasure feature, carried in #43 until planned).

- [x] **EKO-1-05** — Record the Google Calendar integration decision (ADR-0006).
  *Done when:* ADR-0006 is "Accepted <date>" and fixes the OAuth flow and scope, token storage
  and encryption, how app-created events are recognised, change detection able to meet VIS-6
  (`docs/product/project-brief.md`), the conflict rule VIS-5, retry of unsynchronised visits, and
  the testing-mode limits with the path to Google verification. Within ADR-0005's rule that only
  the VIS-3 customer name, address and phone, the visit times and sync identifiers go to Google,
  ADR-0006 also lists each field sent to Google, decides how Google tokens are stored, what a
  customer's erasure and the re-apply of erasures at a restore do to app-created calendar events,
  past ones included, and what happens to those events when the owner's Google access is lost
  (entry conditions from EKO-1-04, #17). It also decides the background-work mechanism and any
  worker service, the Google OAuth client secret and token encryption key and the Google callback
  path (forwarded by ADR-0004), and Google account linking outside Keycloak (forwarded by
  ADR-0003).
  **Out of scope (explicit):** implementation (EKO-5); the Google verification itself, until the
  task for brief §3 item 10 is planned before go-live; runtime proof of Google behaviour (EKO-5).
  **Done 2026-10-28:**
  [`ADR-0006-google-calendar.md`](architecture/decisions/ADR-0006-google-calendar.md) (status
  "Accepted 2026-10-27", revised in place in two fix rounds), the ADR-0004 addendum adding the
  `worker` service, and both registers citing ADR-0006, merged in
  [PR #49](https://github.com/TanerCRB/Eko_CRM/pull/49) — QA's document checks
  (`tests/doc-checks/EKO-1-05.sh`, 84 checks) verified at `3cab315`, all 159 named kill
  mutations killed; seven recorded exceptions (`architecture/exception-register.md`), fixed by an
  ADR-0006 addendum in #46 before the EKO-5 synchronisation code. Forwarded: the layer check for
  `backend/app/worker.py` (#47); the sensitive-paths preamble (#48); the IT rule admitting one
  Gmail account per rep as a Google test user (gate-2 decision on B-02, for the EKO-5 linking
  task and the pilot); manual control ADR-0006-C23 before the pilot; the "removals not carried
  out" display for the owner and the manager (EKO-5).

- [ ] **EKO-1-06** — Build a walking skeleton that runs in containers.
  *Done when:* one compose command starts backend, frontend, database and identity server
  locally; a test proves the backend health endpoint answers and the first migration applies on
  an empty database; CI runs the backend and frontend tests on every PR; the capability register
  lists these capabilities as proven, with links to the tests.
  **Out of scope (explicit):** any product feature; production server setup.

- [ ] **EKO-1-07** — Build the frontend shell and shared UI components from the chosen prototype.
  *Done when:* the app shell (navigation, header, responsive collapse) and the shared components
  Button, IconButton, StatusBadge, Field, ConfirmDialog, EmptyState and Toast exist in
  `frontend/` with the prototype's design tokens; component tests prove StatusBadge always renders
  text or an icon, never colour alone, and ConfirmDialog shows the exact consequence text; UI copy
  is Polish.
  **Out of scope (explicit):** feature screens; the prototypes' global state, innerHTML rendering
  and persona switch.

- [ ] **EKO-1-08** — Provision the production server and prove a restore before go-live.
  *Done when:* the company IT department has provisioned the production server as ADR-0004
  decides, recorded in a dated provisioning record that accounts for every `ADR-0004-Cn` control;
  and a restore from an off-server backup of both the application and the Keycloak database onto
  a host like production, following ADR-0004's restore procedure with nothing taken from the
  source server, is carried out and recorded in a dated restore record — both before go-live.
  From ADR-0005 (entry conditions from EKO-1-04, #17): the restore includes ADR-0005's re-apply
  duty — every entry of the IT department's off-server erasure record not marked failed or
  cancelled is carried out again on the restored application database after `migrate` (restore
  step 12) and before `backend` and any worker start (step 13), with no backup set written from
  the restored database before the re-apply has run; the re-apply itself is proven once erasure
  exists (ADR-0005-C15). The restore record names re-applied erasures by count and entry
  reference only. The decrypted set on a restore host is deleted once the restore is recorded or
  abandoned, and a restore host that does not become the server, the test restore's host
  included, keeps no restored database or volume (ADR-0005-C18). The Keycloak event settings,
  the 14-day log bound and the off-server event copy are proven on production.
  **Out of scope (explicit):** anything ADR-0004 does not decide — a restore-time target (none set
  by the business; a new task when one is); retention and personal data in backups — EKO-1-04;
  the Google secrets — EKO-1-05; zero-downtime deployment (G-3 A); later restore tests.

- [ ] **EKO-1-09** — Ship Keycloak events off the application server before go-live.
  *Done when:* tests in the EKO-1-06 composition prove that admin events of both realms,
  master-realm login events and the stored application-realm login types are shipped with no
  token, credential or session identifier, at least every 5 minutes with a heartbeat, within
  ADR-0004's seven services and the official Keycloak image; and, before go-live and no later
  than 2027-03-31, a dated record confirmed by the IT department shows ADR-0005-C10 met on
  production against an append-only IT host off the server, with the destination's housekeeping
  set to 365 days (admin events, master-realm login events) and 90 days (application-realm login
  events); the capability register lists event shipping as proven.
  **Out of scope (explicit):** lifting exception EKO-1-03/B-02 — the human's own edit; the
  recurring review of the copy — an ADR-0004 operator duty; a reading interface; shipping logs or
  application events; other alerts; self-service resets in the off-server record — #38; server
  and destination provisioning — EKO-1-08. A new service or image stops the task as an ADR-0004
  addendum (G-9 A).

- [ ] **EKO-1-10** — Build the code-level architecture controls in CI (#51).
  *Done when:* ADR-0001-C6, C8..C11, C13, C14 (greps), ADR-0002-C4, C13, ADR-0003-C9, C12 and the
  ADR-0005-C12 grep run on every PR, each shown failing on a fixture, with the holes of R-09,
  R-11, R-12 and R-13 closed (word-bounded C10, `starlette.config`, C13 on `datetime.time(` and the
  PostgreSQL time functions and `backend/migrations/`, a ruff config other than the expected ones
  fails, `toISOString` serialisation not flagged); the layer check covers `backend/app/worker.py`
  (#47).
  **Out of scope (explicit):** the Warsaw-time helpers themselves (first task with dates). After
  EKO-1-06; before EKO-1-07 and EKO-2-01.

- [ ] **EKO-1-11** — Make migrations safe against concurrent runs, older and newer schemas and
  stalls (#52).
  *Done when:* ADR-0004-C12, C13, C14 and C26's migrate half pass; the lock and statement timeout
  values are set; the revision descent check of `backend`, `migrate` and `worker` passes;
  ADR-0006-C13's runtime half (the worker refuses an older revision) passes.
  **Out of scope (explicit):** expand → contract of a real product migration (first product task
  that alters a table). After EKO-1-06; before EKO-3-01.

- [ ] **EKO-1-12** — Configure Keycloak in the composition as ADR-0003..ADR-0005 require (#53).
  *Done when:* the realm export meets ADR-0003-C1, C14, C15, C17 and ADR-0005-C7; bootstrap opens
  the public listener only after the realm import and the C8 check (exception EKO-1-03/R-22
  lifted); ADR-0003-C10, C16, ADR-0004-C23, C24 and ADR-0005-C5 pass against the running
  composition; the reset-timing measurement is recorded. The console-role and typed-username stop
  rules apply.
  **Out of scope (explicit):** login to the application (EKO-2-01); event shipping (EKO-1-09).
  After EKO-1-06; before EKO-2-01.

- [ ] **EKO-1-13** — Set the log settings and log bounds of every service (#54).
  *Done when:* ADR-0005-C3 (with a marker statement), C4 and C6's composition half pass; backend
  log lines and error responses carry one backend-generated correlation identifier; responses carry
  `Cache-Control: no-store`; ADR-0005-C2 is built and shown failing on a fixture endpoint.
  **Out of scope (explicit):** Keycloak's log (EKO-1-12); C6 on a shared host (EKO-1-08). After
  EKO-1-06; before EKO-2-01.

- [ ] **EKO-1-14** — Build the backup service against a destination test double (#55).
  *Done when:* a nightly run under the backup role's connection limit completes (ADR-0004-C19);
  backup and migrate exclude each other (C26's backup half); C15 and C16 pass against a local
  append-only destination double.
  **Out of scope (explicit):** the real destination and the C17 off-server alert (EKO-1-08). After
  EKO-1-11; before EKO-1-08.

- [ ] **EKO-1-15** — Build the release pipeline that publishes images by digest (#56).
  *Done when:* a release tag makes CI build the backend, frontend and backup images and push them
  to the registry by digest as ADR-0004 *Images* decides; the composition used for a deployment
  references those digests; the capability register lists the release pipeline as proven.
  **Out of scope (explicit):** the deployment itself and production setup (EKO-1-08). After
  EKO-1-06; before EKO-1-08's first deployment.

## EKO-2 — Access

- [ ] **EKO-2-01** — Require login for the whole application.
  *Done when:* a test proves every API operation except login answers 401 without a valid session
  (contrast: the same call with a valid session succeeds); the frontend sends an unauthenticated
  user to login; a user with no Google account linked can log in.
  **Out of scope (explicit):** user administration screens — the administrator uses the identity
  server's console.

- [ ] **EKO-2-02** — Carry roles and account state into every request.
  *Done when:* tests prove a deactivated account cannot log in and its data stays; the backend
  knows the caller's role and user id; one person holding manager and administrator roles gets
  both; there is no self-registration path.
  **Out of scope (explicit):** per-resource ownership rules — each feature task proves its own.
