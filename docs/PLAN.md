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
  (ADR-0004, #16); the Keycloak behaviours behind ADR-0003-C1, C7, C10 and C14..C20 (EKO-1-06, #19; reassigned
  to EKO-1-12, #53, at EKO-1-06's gate 1).

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

- [x] **EKO-1-06** — Build a walking skeleton that runs in containers.
  *Done when:* one compose command starts backend, frontend, database and identity server
  locally; a test proves the backend health endpoint answers and the first migration applies on
  an empty database; CI runs the backend and frontend tests on every PR; the capability register
  lists these capabilities as proven, with links to the tests.
  **Out of scope (explicit):** any product feature; production server setup.
  **Done 2026-10-28:** narrowed at gate 1 (the rest went to EKO-1-10..1-15, #51–#56) and merged in
  [PR #57](https://github.com/TanerCRB/Eko_CRM/pull/57), verified at `833c3c1` after two fix
  rounds — one composition (development profile of nine services, shared profile of eight), the
  backend with a readiness health route and the first Alembic revision, the P2 SPA shell, the
  PostgreSQL initialisation of the ADR-0004 2026-10-28 addendum and CI, proven by
  `backend/tests/runtime/`, `backend/tests/static/`, `backend/tests/unit/` and `frontend/tests/`
  (rows in `architecture/capabilities.md`), the CI runs linked there and a manual run on Windows on
  2026-10-28; three recorded exceptions (`architecture/exception-register.md`). Forwarded: the
  admin listener's source-address check and the fixed shared project name (EKO-1-08, #36);
  assertions for checklist rules 4, 7 and 9 (EKO-1-10, #51); digests for the `proxy` base,
  `postgres` and `keycloak` (EKO-1-15, #56); sensitive-path rows for `backup/**` and
  `backend/app/serve.py` (#61).

- [x] **EKO-1-07** — Build the frontend shell and shared UI components from the chosen prototype.
  *Done when:* the app shell (navigation, header, responsive collapse) and the shared components
  Button, IconButton, StatusBadge, Field, ConfirmDialog, EmptyState and Toast exist in
  `frontend/` with the prototype's design tokens; component tests prove StatusBadge always renders
  text or an icon, never colour alone, and ConfirmDialog shows the exact consequence text; UI copy
  is Polish.
  **Out of scope (explicit):** feature screens; the prototypes' global state, innerHTML rendering
  and persona switch.
  **Done 2026-11-02:** P2 shell and seven primitives, Polish built-in copy, non-colour status
  communication, exact dialog consequences, and one-deployment lazy-chunk recovery merged in
  [PR #75](https://github.com/TanerCRB/Eko_CRM/pull/75), verified at `418a378`. All 18 executed
  mutations were killed; 1145 backend and 73 frontend tests passed, and composition CI passed all
  202 runtime tests on Linux. Gate-2 assumptions A-01–A-07 were accepted and recorded as K-01/K-06
  amendments, with scope re-locked at `d959a406`. Feature screens, old/new API compatibility,
  concurrent deployments, formal accessibility audits and native-dialog/screen-reader proof remain
  outside this claim.

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

- [x] **EKO-1-10** — Build the code-level architecture controls in CI (#51).
  *Done when:* ADR-0001-C6, C8..C11, C13, C14 (greps), ADR-0002-C4, C13, ADR-0003-C9, C12 and the
  ADR-0005-C12 grep run on every PR, each shown failing on a fixture, with the holes of R-09,
  R-11, R-12 and R-13 closed (word-bounded C10, `starlette.config`, C13 on `datetime.time(` and the
  PostgreSQL time functions and `backend/migrations/`, a ruff config other than the expected ones
  fails, `toISOString` serialisation not flagged); the layer check covers `backend/app/worker.py`
  (#47).
  **Out of scope (explicit):** the Warsaw-time helpers themselves (first task with dates). After
  EKO-1-06; before EKO-1-07 and EKO-2-01.
  **Done 2026-10-29:** widened at gate 1 by checklist rules 4, 7, 9 and 19 (PR #57 S-03) and an
  OpenAPI comparison with the previous release (#19 G-1 A); every gate-1 recommendation G-1..G-14
  accepted, with the restated controls written as accepted 2026-10-29 addenda to ADR-0001..ADR-0004
  (ADR-0001-C6, C8, C10, C13, C14 and the scope of C11; ADR-0002-C13 and C4; ADR-0003-C9; the
  ADR-0004 forwards). Merged in [PR #65](https://github.com/TanerCRB/Eko_CRM/pull/65), verified at
  `2cec564` after one fix round: the CI job `layers` against the PR base (red on a planted import in
  throwaway [PR #66](https://github.com/TanerCRB/Eko_CRM/pull/66)), six nested
  `backend/app/*/ruff.toml` holding only the layer bans, the frontend `pnpm lint` step and the
  backend API-compatibility step, proven by `backend/tests/static/test_eko110_k01..k07_*.py`,
  `test_eko110_qa_contrasts.py` and `frontend/tests/eslint-config.test.ts` (rows in
  `architecture/capabilities.md`), 175 mutations killed; two recorded exceptions for test-data
  suppressions (`architecture/exception-register.md`). Forwarded: the low findings S-01, F-01,
  R-07, R-08 and R-09 (#67); which release is previous and how CI obtains its OpenAPI document
  (EKO-1-15, #56); the Warsaw-time helpers and R-12's Sunday-late case (the first task with dates).

- [x] **EKO-1-11** — Make migrations safe against concurrent runs, older and newer schemas and
  stalls (#52).
  *Done when:* ADR-0004-C12, C13, C14 and C26's migrate half pass; the lock and statement timeout
  values are set; the revision descent check of `backend`, `migrate` and `worker` passes;
  ADR-0006-C13's runtime half (the worker refuses an older revision) passes.
  **Out of scope (explicit):** expand → contract of a real product migration (first product task
  that alters a table). After EKO-1-06; before EKO-3-01.
  **Done 2026-10-30:** the values and the descent mechanism were recorded in the ADR-0004 addendum
  of 2026-10-29, accepted at gate 1 (lock key in `compose.yaml`'s `x-migration-advisory-lock`,
  5 s / 30 s, the real expand revision `0002` creating `schema_revision_lineage`). Merged in
  [PR #70](https://github.com/TanerCRB/Eko_CRM/pull/70), verified at `2a88d4b` after one fix
  round (`migrate` refuses every migration-running command except `alembic upgrade head`), proven
  by `backend/tests/runtime/test_adr0004_c12_concurrent_migrate.py`,
  `test_adr0004_c26_advisory_lock_shared.py`, `test_adr0004_c13_backend_revision_check.py`,
  `test_adr0004_c13_migrate_revision_check.py`, `test_adr0004_c13_migrate_command_refusal.py`,
  `test_adr0006_c13_worker_revision_check.py`, `test_adr0004_c14_failing_revision.py`,
  `test_adr0004_c26_lock_timeout.py`, `test_adr0004_c26_statement_timeout.py`,
  `test_adr0003_c19_migrate_one_connection.py`, `test_adr0002_c2_shipped_revision_tree.py` and
  `backend/tests/static/test_adr0004_c26_lock_key_recorded_once.py` (rows in
  `architecture/capabilities.md`), 48 mutations killed. Forwarded: the backup half of C26
  (EKO-1-14, #55); a published previous release (EKO-1-15, #56); C26's read through a product
  endpoint and the first expand → contract (EKO-3-01); the reviewer's low finding R-02 (a
  branched tree is reported as "unknown destination revision").

- [ ] **EKO-1-12** — Configure Keycloak in the composition as ADR-0003..ADR-0005 require (#53).
  *Done when:* the realm export meets ADR-0003-C1, C14, C15, C17 and ADR-0005-C7; bootstrap opens
  the public listener only after the realm import and the C8 check (exception EKO-1-03/R-22
  lifted); ADR-0003-C10, C16, ADR-0004-C23, C24 and ADR-0005-C5 pass against the running
  composition; the reset-timing measurement is recorded. The console-role and typed-username stop
  rules apply.
  **Out of scope (explicit):** login to the application (EKO-2-01); event shipping (EKO-1-09).
  After EKO-1-06; before EKO-2-01.

- [x] **EKO-1-13** — Set the log settings and log bounds of every service (#54).
  *Done when:* ADR-0005-C3 (with a marker statement), C4 and C6's composition half pass; backend
  log lines and error responses carry one backend-generated correlation identifier; responses carry
  `Cache-Control: no-store`; ADR-0005-C2 is built and shown failing on a fixture endpoint.
  **Out of scope (explicit):** Keycloak's log (EKO-1-12); C6 on a shared host (EKO-1-08). After
  EKO-1-06; before EKO-2-01.
  **Done 2026-11-04:** built as the ADR-0005 addenda of 2026-11-02 decide. Gate 1 accepted them
  with the deviation Q-7 H (`adr-deviation`); they were amended at implementation (S-2, S-3) and
  at verification (R-01/B-01, S-5). What was built:
  - 23 literal PostgreSQL `-c` settings;
  - one filtered Caddy access line per request;
  - `app.core.logs`, which writes JSON lines whose exceptions and warnings carry only type and
    location;
  - a backend-generated `Eko-Correlation-Id` on every response, and `no-store` on `/api/`;
  - no `logging` key in the composition.

  The form is documented in `docs/operations/log-format.md`. Merged in [PR #81](https://github.com/TanerCRB/Eko_CRM/pull/81), verified at
  `49d9459` after one fix round. Proven by:
  - `backend/tests/runtime/`: `test_adr0005_c3_postgres_error_log.py`,
    `test_adr0005_c4_proxy_access_log.py`, `test_adr0005_frontend_request_log.py`,
    `test_adr0005_backend_request_log_line.py`, `test_adr0005_correlation_identifier.py`,
    `test_adr0005_backend_error_handling_runtime.py`, `test_adr0005_uncaught_driver_error.py`,
    `test_adr0005_serving_process_hooks.py`, `test_adr0005_qa_migrate_command_error.py`,
    `test_adr0005_c12_no_store_through_proxy.py`, `test_adr0005_no_secret_in_logs.py`;
  - `backend/tests/static/`: `test_adr0005_c3_postgres_settings_in_release.py`,
    `test_adr0005_c3_qa_no_log_setting_outside_the_table.py`, `test_adr0005_c6_no_logging_key.py`,
    `test_adr0005_eko113_changeset.py`;
  - `backend/tests/unit/test_adr0005_*.py`.

  The rows are in `architecture/capabilities.md`. Every mutation of a criterion's mechanism was
  killed; M16 was killed after QA added a `CommandError` case. Four exceptions are recorded
  (EKO-1-13/weakening-1..4). Deleting container logs by time on each shared host is EKO-1-08's
  (#36), under Q-7 H.

- [x] **EKO-1-14** — Build the backup service against a destination test double (#55).
  *Done when:* a nightly run under the backup role's connection limit completes (ADR-0004-C19);
  backup and migrate exclude each other (C26's backup half); C15 and C16 pass against a local
  append-only destination double.
  **Out of scope (explicit):** the real destination and the C17 off-server alert (EKO-1-08). After
  EKO-1-11; before EKO-1-08.
  **Done 2026-11-02:** built as the ADR-0004 addendum of 2026-10-30 decides (accepted at gate 1;
  amended at gate 1 in its destination-double bullet and in fix round 1 in its read-privileges
  bullet): one control session holding the advisory lock shared with `migrate` and an exported
  snapshot, the dumps streamed through `age` to an append-only SFTP destination, a manifest and a
  plaintext completion record, a UTC scheduler, one documented failure line, and explicit read
  grants instead of `pg_read_all_data`. Merged in [PR #77](https://github.com/TanerCRB/Eko_CRM/pull/77),
  verified at `ce9ddfc` after one fix round, proven by `backend/tests/runtime/test_adr0004_c19_backup_run_within_limit.py`,
  `test_adr0004_c26_backup_excludes_migrate.py`, `test_adr0004_c15_backup_set_contents.py`,
  `test_adr0004_c15_backup_sets_coexist.py`, `test_adr0004_c16_backup_cannot_delete_or_overwrite.py`,
  `test_adr0004_backup_schedule_utc.py`, `test_adr0004_backup_on_demand.py`,
  `test_adr0004_backup_failure_line.py`, `test_adr0004_backup_no_dump_at_rest.py`,
  `test_adr0004_backup_cleanup.py`, `test_adr0004_c28_backup_read_only.py`,
  `test_adr0005_backup_log_content.py` and `backend/tests/static/test_adr0004_c26_backup_lock_by_reference.py`,
  `test_adr0004_backup_script_rules.py` (rows in `architecture/capabilities.md`); every mutation of a
  criterion's mechanism killed except M12 (recorded exception); four recorded exceptions
  (`architecture/exception-register.md`). Forwarded: the real destination, C15's 7 days, C16 and
  C17 there, and the IT department's acceptance of SFTP and age (EKO-1-08, #36, noted there);
  manifest digests (EKO-1-15, #56); product-table counts (EKO-3-01); the control session's unbounded
  table-lock wait (#76).

- [x] **EKO-1-15** — Build the release pipeline that publishes images by digest (#56).
  *Done when:* a release tag makes CI build the backend, frontend and backup images and push them
  to the registry by digest as ADR-0004 *Images* decides; the composition used for a deployment
  references those digests and, by the 2026-10-28 ADR-0004 addendum, also the `proxy` base,
  `postgres` and `keycloak` by digest (EKO-1-06 B-01); the capability register lists the release
  pipeline as proven.
  **Out of scope (explicit):** the deployment itself and production setup (EKO-1-08). After
  EKO-1-06; before EKO-1-08's first deployment.
  **Done 2026-11-08:** merged in [PR #85](https://github.com/TanerCRB/Eko_CRM/pull/85), verified at `852b0b5`; the first release
  attempt `v0.1.0` failed in its runtime tests and published nothing (fixed by EKO-1-19, #95);
  release [run 42363349085](https://github.com/TanerCRB/Eko_CRM/actions/runs/42363349085) published `v0.1.1` on `794c04a` (record
  `sha256:52f8dcb0…`), its composition naming the four project images, `keycloak` and `postgres` by
  digest, with `proxy` on a digest-pinned `caddy` base; the first `main` run after it
  ([run 42380237367](https://github.com/TanerCRB/Eko_CRM/actions/runs/42380237367)) compared the API with `v0.1.1` and ran C13's previous-release half.
  Mutations M01–M47, Q01–Q60 and R1–R5, every one killed counting QA's added tests; exception
  EKO-1-06/B-01 closed; follow-ups #84, #98, #99.
- [x] **EKO-1-16** — Amend ADR-0006 to close the EKO-1-05 exceptions (#46).
  *Done when:* a dated ADR-0006 addendum resolves EKO-1-05/R-11, R-15, R-16, R-17, R-18, B-06 and
  Q-01; `tests/doc-checks/EKO-1-16.sh` proves the stated contrasts; the corresponding exception
  entries leave the exception register through this task's gate-3 documentation PR; and the
  completed EKO-1-05 plan entry remains unchanged.
  **Out of scope (explicit):** EKO-5 implementation and runtime Google proof; real customer-data
  processing until the DPIA's approval conditions are evidenced; and new Google data, scopes,
  calendars or product behavior.
  **Done 2026-10-30:** merged in [PR #73](https://github.com/TanerCRB/Eko_CRM/pull/73), verified by `tests/doc-checks/EKO-1-16.sh` (nine passing contrasts). The accepted DPIA remains synthetic-data-only; Google runtime behavior is explicitly unproven pending EKO-5 and pre-go-live evidence.
- [x] **EKO-1-18** — Add agent-session permission rules for release-tag, release and re-run
  actions outside git push (#83).
  *Done when:* `.claude/settings.json` stops, in an agent session, `gh release create`, `gh api`
  calls that create a ref, a tag or a release, `gh run rerun` in every form and `gh api` calls to
  the three actions re-run endpoints; a repository check against the real file shows each rule
  stopping its named command and not stopping the named ordinary reads, and fails when a rule is
  removed, narrowed or over-widened; the existing deny/ask rules and hooks are unchanged; the
  capability register states what the rules do not prove; exception EKO-1-15/security-2 is
  closed.
  **Out of scope (explicit):** a separate agent identity or paid-plan ruleset (G-6 B, new Story);
  the release workflow (EKO-1-15, #56); wrapped or scripted invocations, local and user-level
  settings, bypassed permission checks (stated limits); `workflow_dispatch` (until the release
  workflow gains it); release-record deletion (#84). Before the first release tag and by
  2026-12-05 (EKO-1-15/security-2).
  **Done 2026-11-06:** merged in [PR #88](https://github.com/TanerCRB/Eko_CRM/pull/88), verified at
  `0aa781e` by `tests/doc-checks/EKO-1-18.sh` (74 checks; self-test 89) and 61 mutations; 21 new scoped
  `Bash(...)` deny rules (incl. the `gh release new` alias); live attempts in agent sessions on
  2026-11-06 (Claude Code 2.1.319) recorded on #83. Limits are in the capability register;
  follow-ups #86 (other agent tools) and #87 (hook and rule-file edits).
- [x] **EKO-1-19** — Make the runtime tests pass on the checked images and run that mode on every pull request (#95).
  *Done when:* on one commit the runtime tests pass with and without `EKO_CHECKED_IMAGES`, with the
  same tests collected and skipped in both; each failure of release run 42276738866 has a named
  cause; CI runs release mode on every pull request that runs the runtime tests and on `main`, and
  fails on a planted Compose-name image lookup; `ci.yml` pushes nothing; [per G-1] a `v0.1.1`
  release run on `main` publishes a release.
  **Out of scope (explicit):** what the release pipeline checks or publishes (EKO-1-15); the runtime
  trigger (K-05); tag `v0.1.0`; EKO-1-15's gate-3 documentation (#56); new runtime tests; ADR changes
  (Architect). After EKO-1-15's code; before EKO-1-15's gate 3 and EKO-1-08's first deployment.
  **Done 2026-11-07:** merged in [PR #96](https://github.com/TanerCRB/Eko_CRM/pull/96), verified at `bb150c1`: on PR #96 build and
  release mode each 374 passed, 1 skipped, `mode_parity` exit 0 ([run 42320667987](https://github.com/TanerCRB/Eko_CRM/actions/runs/42320667987)); the planted
  Compose-name lookup on [PR #97](https://github.com/TanerCRB/Eko_CRM/pull/97) failed release mode with exactly rows 1–9 while build
  mode passed ([run 42353040687](https://github.com/TanerCRB/Eko_CRM/actions/runs/42353040687)); the first `main` run passed on its first attempt
  ([run 42362952882](https://github.com/TanerCRB/Eko_CRM/actions/runs/42362952882)); release [run 42363349085](https://github.com/TanerCRB/Eko_CRM/actions/runs/42363349085) passed its tests on the first attempt and
  published `v0.1.1` on attempt 4, after GHCR package access was set by hand (#99). 21 mutations;
  follow-ups #98 and #99.
- [ ] **EKO-1-21** — Check EKO-1-15's "no change under `backup/`" claim against EKO-1-15's own change set (#109).
  *Done when:* the manifest-digest runtime test no longer asserts the claim against the live branch; the claim is checked on EKO-1-15's fixed base/head pair, a branch that changes `backup/` passes, and a planted `backup/` change inside EKO-1-15's pair fails; the rest of `test_eko115_k02_manifest_names_the_release_digests` is unchanged.
  **Out of scope (explicit):** any change to `backup/` (EKO-1-20); other live-base change-set tests (follow-up Issue). Before EKO-1-20's merge.

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
