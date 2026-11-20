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

- [x] **EKO-1-12** — Configure Keycloak in the composition as ADR-0003..ADR-0005 require (#53).
  *Done when:* the realm export meets ADR-0003-C1, C14, C15, C17 and ADR-0005-C7; bootstrap opens
  the public listener only after the realm import and the C8 check (exception EKO-1-03/R-22
  lifted); ADR-0003-C10, C16, ADR-0004-C23, C24 and ADR-0005-C5 pass against the running
  composition; the reset-timing measurement is recorded. The console-role and typed-username stop
  rules apply.
  **Out of scope (explicit):** login to the application (EKO-2-01); event shipping (EKO-1-09).
  After EKO-1-06; before EKO-2-01.
  **Done 2026-11-11:** merged in [PR #117](https://github.com/TanerCRB/Eko_CRM/pull/117) with the
  self-test fix [PR #122](https://github.com/TanerCRB/Eko_CRM/pull/122) and the boot-identity
  correction [PR #135](https://github.com/TanerCRB/Eko_CRM/pull/135) (#126): a versioned realm
  export for both realms; the custom image `localhost/eko-crm/keycloak:26.8.1-eko112`
  (`sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`,
  `docs/evidence/EKO-1-12/custom-image-build-fix1.md`) baking the ADR-0007 option-A provider —
  same-ID order-100 `jpa` override filtering `details.code_id`, `sessionId` and unknown-account
  `details.username`; the ordered bootstrap (`scripts/keycloak-bootstrap.sh`) verifying provider
  selection AND filtering before either listener opens with per-gate brute-force preconditions;
  gate markers bound to a per-boot UUID token rotated by the compose wrapper as its first act
  (ADR-0004 addendum 2026-11-10, C33; the numbering correction C29→C34 cited by verification).
  Exception EKO-1-03/R-22 lifted — its register line is removed by this check-off. Reset timing
  measured 2026-11-09 cold (`docs/evidence/EKO-1-12/reset-timing.md`); K-05's mail-window case
  accepted as exception EKO-1-12/qa2-7. Gate 2 accepted G-02 (ADR-0005 *Retention* reachable-set
  amendment recorded in this PR), K-07, U-02 moot-by-config and assumptions A-01..A-04; six
  exceptions recorded (this PR). Verification: QA four rounds (16 mutations of the qa4 set,
  `docs/evidence/EKO-1-12/`), guardian/reviewer/auditor final re-verifications green at the
  correction head; CI run [43078488149](https://github.com/TanerCRB/Eko_CRM/actions/runs/43078488149)
  green on both runtime jobs at `70647ee`, the first ubuntu proof of the token primitive and of
  release-mode K-04 with the keycloak pre-build step (option A1; digest integration stays #118 —
  exception EKO-1-12/R-02; #126 correction ratified by the human 2026-11-10). Follow-ups #118..#121
  (#121 closed by #122); deviations D-01..D-05 of inv-33 (freeze-list job-gate, comment byte-pin)
  and the human's merge-before-CI-completion at gate 2 are ratified by this check-off.

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
- [x] **EKO-1-20** — Bound the backup control session's lock wait after the advisory lock is granted (#76).
  *Done when:* with an application table held `ACCESS EXCLUSIVE`, a backup run fails with
  `reason=dump-application`, SQLSTATE 55P03, within the stated bound, leaves no set object and
  releases the advisory lock; the same run without the lock succeeds; the advisory-lock wait stays
  unbounded; the ADR-0004 text states the bound.
  **Out of scope (explicit):** the advisory-lock wait itself (accepted cost); retry after a failure;
  the off-server alert (EKO-1-08). After EKO-1-14.
  **Done 2026-11-09:** merged in [PR #113](https://github.com/TanerCRB/Eko_CRM/pull/113), verified at `83e85a9`: the control session sets `SET LOCAL lock_timeout = '180s'` right after the export statement and before the revision read (`bound_control_lock_waits()` in `backup/eko-backup`, ADR-0004 addendum of 2026-11-08, ADR-0004-C32); a run held past it by an `ACCESS EXCLUSIVE` table lock or a held `alembic_version` fails with `reason=dump-application sqlstate=55P03`, leaves no set object and releases the advisory lock, and the advisory-lock wait stays unbounded — `backend/tests/runtime/test_eko120_control_lock_wait.py`, `test_eko120_qa_control_lock_wait.py` and two static checks; both runtime jobs of [run 42633372226](https://github.com/TanerCRB/Eko_CRM/actions/runs/42633372226) green. The CI runtime jobs' `timeout-minutes` raised to 75 under exception EKO-1-20/weakening-1. K-06 confirmed by the human at gate 2. 18 mutations, 17 killed; M3 survived as a redundant mechanism (exception EKO-1-20/M3). Follow-ups #108, #110.
- [x] **EKO-1-21** — Check EKO-1-15's "no change under `backup/`" claim against EKO-1-15's own change set (#109).
  *Done when:* the manifest-digest runtime test no longer asserts the claim against the live branch; the claim is checked on EKO-1-15's fixed base/head pair, a branch that changes `backup/` passes, and a planted `backup/` change inside EKO-1-15's pair fails; the rest of `test_eko115_k02_manifest_names_the_release_digests` is unchanged.
  **Out of scope (explicit):** any change to `backup/` (EKO-1-20); other live-base change-set tests (follow-up Issue). Before EKO-1-20's merge.
  **Done 2026-11-09:** merged in [PR #111](https://github.com/TanerCRB/Eko_CRM/pull/111), verified at `65e245c`: `test_eko115_k02_manifest_names_the_release_digests` now asserts `eko_1_15_backup_changes() == []` on EKO-1-15's pair `14e9576`..`0d22122`, proven by `backend/tests/runtime/test_eko115_k02_claim_on_own_pair.py` (22 cases); both runtime jobs of [run 42522741112](https://github.com/TanerCRB/Eko_CRM/actions/runs/42522741112) listed every case PASSED, none skipped. K-05 and K-06 judged by the human on one-time evidence (amended at gate 2). 11 mutations, all killed; follow-up #110.
- [x] **EKO-1-22** — Correct the sensitive-paths register's stale "pending ADR-0006" preamble (#48).
  *Done when:* the preamble of `docs/architecture/architecture-sensitive-paths.md` names no decision as pending and every pending claim the file makes matches a decision whose status in `docs/architecture/decisions/` is not "Accepted" (none, ADR-0001..ADR-0006 all accepted); the table, class list and `scripts/risk-check.sh` are unchanged and the static tests that read the file pass unedited.
  **Out of scope (explicit):** other files with the same stale claim (the CLAUDE.md sentence — gate-1 call); re-pinning past doc-checks to the live register (follow-up #110); any change to the register's rows, classes or `scripts/risk-check.sh`.
  **Done 2026-11-10:** merged in [PR #132](https://github.com/TanerCRB/Eko_CRM/pull/132), verified at `27fe842`: preamble l.11-12 replaced by the gate-1 F2 conditional citation rule (C-2), proven by the committed carrier `tests/doc-checks/EKO-1-22.sh` (named checks K-01a…K-05; 8/8 green on the merged tree, exit 0, incl. the 236-case static-test leg); 20 mutation labels over three QA rounds — all killed except M-05-narrow (survived; the retained Accepted-comparison covers both arms — exception EKO-1-22/M-05-narrow, follow-up #131); M-10 (claim wrapped across two lines) and M-11c (live-loop call removed) survived their first version and were killed in-round by the fold-pair contrast and the BC_CALLS count guard. The human accepted A-01..A-10 at gate 2 and the K-03 instance substitution to ADR-9999 (scope re-locked `3185224b`); the CLAUDE.md l.65 fold stays the human's own edit (C-1=A). Follow-ups #114, #130, #131.
- [x] **EKO-1-24** — Make migrate refuse a branched revision tree with a message that names the heads (#71).
  *Done when:* a test running `env.py` on a two-head tree shows a "migrate refused:" line naming both
  heads, the contrast shows an unresolvable identifier still reading "unknown destination revision",
  the run still applies nothing and exits non-zero before connecting, and EKO-1-11's refusal tests
  pass unchanged.
  **Out of scope (explicit):** which commands `migrate` accepts (proven by EKO-1-11; change needs an
  ADR-0004 addendum); the fix mechanism (Analyst's); `backend`/`worker` texts (already name the
  heads); branched-image prevention (exists, CI one-head check); alerting on refusal (EKO-1-08).
  After EKO-1-11.
  **Done 2026-11-10:** merged in [PR #125](https://github.com/TanerCRB/Eko_CRM/pull/125), verified at `8993816`: the refusal observed as `migrate refused: the code's tree has 2 heads: ['t_sibling_a', 't_sibling_b']` — unit carriers green inside the 1746-passing local suite at the merged checkpoint, and K-01's four runtime carriers PASSED in both modes of [run 43043176502](https://github.com/TanerCRB/Eko_CRM/actions/runs/43043176502) (their jobs on the PR itself were cancelled at the then-75-minute CI ceiling, the defect EKO-1-25 fixed); EKO-1-11's 18 refusal files byte-unchanged, zero diff overlap, all green (K-04); 6 mutations M1–M6, 5 killed (4/4/13/1/9 tests each), M5 (widened `MultipleHeads` gate) survived as an equivalent mutant on every pinned surface — accepted by the human at gate 2 as exception EKO-1-24/M5; exception EKO-1-24/B-01 (no charset rule binds identifiers reaching the plain-text refusal sink, follow-up #128); scope re-locked at gate 2 (`5c15ff43`); the migration-safety capability row carries the branched-tree refusal. Follow-ups #127, #128.

- [x] **EKO-1-23** — Recheck past tasks' change-set claims on their own base/head pair, not on the live branch (#110).
  *Done when:* every test in the verified candidate list is classified live invariant (left, one-line docstring reason) or past claim (rechecked on that task's fixed pair); for each rechecked test a later branch touching the same paths passes and a planted change inside the original pair fails.
  **Out of scope (explicit):** `changed_paths()`/`merge_base()`; `.github/workflows/ci.yml`; past `tests/doc-checks/*.sh` (G-1, follow-up); any new or tightened rule.
  **Done 2026-11-10:** merged in [PR #129](https://github.com/TanerCRB/Eko_CRM/pull/129), verified at `7d7c39b`: the PR body classifies every candidate — five live invariants left with a one-line docstring reason (`test_k07_changeset.py`, `test_eko119_k01_mode_parity.py`, `test_adr0005_eko113_changeset_adr_files_only_gain_addenda`); the EKO-1-13, EKO-1-15, EKO-1-19 and EKO-1-20 claims rechecked on their own PR merge-commit pairs (#81, #85, #96, #113) through `backend/tests/support/fixed_pair.py`, where a later-branch change passes and a one-change plant inside the pair or a missing pair commit fails; the guards of candidates 8, 9 and 12 confirmed already inert — `backend/tests/static/test_eko123_*.py`; the `backend` job of [run 42812654518](https://github.com/TanerCRB/Eko_CRM/actions/runs/42812654518) listed all 390 new and rechecked node IDs PASSED, none skipped (K-06, observed at gate 2). 23 mutation runs, 22 killed; M20c survived as an equivalent mutation of the permanently vacuous `test_k07_register_check_fails_on_any_other_edit` (exception EKO-1-23/M20c). Exception EKO-1-23/weakening-1. Follow-ups #116, #133.

- [x] **EKO-1-25** — Restore the CI runtime jobs: name why they hit their 75-minute timeout since PR #117 and make them complete (#133).
  *Done when:* both runtime jobs of `ci.yml` conclude success or failure, not cancelled, under `timeout-minutes: 360` (C-5): on this task's own PR run (URL in the PR) and on the first `main` run at the merge commit (URL in the gate-3 documentation PR); the cause is named from the per-file timings of a completed run, and the completed durations are stated against 360; a new EKO-1-25 exception entry lands in the gate-3 documentation PR, which also flags EKO-1-20/weakening-1 for revisit (C-6); the collected runtime tests, and everything in the runtime jobs except the bound, are unchanged; every failed runtime test and the `release.yml` runtime bound are listed, each with its own follow-up Issue.
  **Out of scope (explicit):** splitting the runtime suite beyond what the cause requires; reopening EKO-1-23; re-judging PRs merged while the jobs were cancelled; raising the bound without a named cause; splitting or parallelising the suite (C-3); fixing the hidden runtime failures and the `release.yml` runtime bound — follow-up Issues (C-4).
  **Done 2026-11-11:** merged in [PR #139](https://github.com/TanerCRB/Eko_CRM/pull/139) as a merge commit `ce1f5b0` — R-01's instruction, keeping the pinned pair `bf55c4d`..`4d1380e` reachable; verified at `3c86efa`. Cause (b) named from per-file timings (K-02, human at gate 2): EKO-1-12's runtime files add ~3630 s to the suite; no test hung or ran past its own bound. PR run [43043176502](https://github.com/TanerCRB/Eko_CRM/actions/runs/43043176502): both runtime jobs concluded `failure`, not `cancelled`, in 126.4 / 122.6 min under the 360-min bound. First `main` run at the merge: [43074142146](https://github.com/TanerCRB/Eko_CRM/actions/runs/43074142146) — both runtime jobs completed: composition 125.3 min (2 failures), release mode 115.3 min (6 failures) — K-01 gate-3 half observed, not assumed. Five of the six release-mode failures are the listed table's (#140–#144); the sixth — `test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement`, `playwright: net::ERR_NETWORK_CHANGED` — passed on the same tree in the PR run and is flagged flaky, raised as an Issue if it repeats on the next `main` run. Bound guards `test_eko125_k04/k05_*` on the pinned pair, mutations M0–M14 all killed (M0 by CI observation). Exceptions EKO-1-25/weakening-1, EKO-1-25/boundary-1, EKO-1-25/B-01; EKO-1-20/weakening-1 flagged for the human's revisit (C-6). `main`'s runtime stays red until #140–#144 land (C-4); `release.yml` bound #138.

- [x] **EKO-1-26** — Integrate the custom Keycloak image into the release flow (EKO-1-12/R-02 successor) (#118).
  *Done when:* the release-mode CI runtime job reaches its K-04 image guard green on a CI run — the checked-images family covers `localhost/eko-crm/keycloak:26.8.1-eko112` so no runtime test builds it in session; the release pipeline names the custom Keycloak image the route ADR-0004 requires; PR #135 rebased on this merge goes green.
  **Out of scope (explicit):** the boot-identity mechanism of PR #135; the remaining release-mode red tests #140-#144; `backup/` content; the ADR-0004 image-table row moves only through this task's gate 3.
  **Done 2026-11-14:** merged in [PR #157](https://github.com/TanerCRB/Eko_CRM/pull/157) as merge commit `3ca9195`, verified at `e70986a`: route A (fifth project image, accepted at gate 1 from the draft `EKO-1-26-keycloak-release-location-draft-2026-11-11.md`, recorded as the ADR-0004 addendum of 2026-11-14) — `ci.yml` and `release.yml` build/check/save/load/identity five images with `KEYCLOAK_ID` at every site, the harness override freezes `keycloak` (`image:`, `build: !reset null`, `pull_policy: never`) and mirrors `BACKUP_MANIFEST_KEYCLOAK_IMAGE`, `scripts/keycloak-bootstrap.sh` renders the same placement under `EKO_CHECKED_IMAGES` with cleanup armed on every trap, named exit and tail, `release-images.sh` pushes `ghcr.io/tanercrb/eko-crm/keycloak` (first GHCR push needs the human #99 access step) and the release composition names it by the run's own digest; `pulled-digests` is postgres-only. Guard observation delivered: step `No image built by the tests (K-04)` SUCCESS at `e70986a` ([run 43501516163](https://github.com/TanerCRB/Eko_CRM/actions/runs/43501516163) release-mode job) and the whole head green (ci + process-ci at `942d69b`). #135's rebase clause was overtaken by events — #135 merged first (2026-11-11); this task's branch carried its merged state through two `origin/main` merges with all gates re-run (PLAN-row resolution mechanical; the transitional prebuild subsystem removed under Exception EKO-1-26/weakening-1, human-named 2026-11-12). QA PROOF HOLDS: 19 mutations across two rounds, 18 killed, 1 EQUIVALENT (empty-operand guard inert on GNU rm — Exception EKO-1-26/M-R2e pending the human's acceptance at this gate); Guardian PASS×3, Reviewer PASS (Low R-01 refusal-path assertion gap → follow-up #172; Low R-02 build-bound ownership — disproof met: five builds completed with margin), Auditor PASS (U-01 package-access scope at the first push — human action). The composition carries the custom image by digest for deployment/rollback/restore as ADR-0004 (2026-11-06) requires; the first executed release naming it rides on the next human-pushed tag (#138 lineage). `main`'s runtime signal: the release-mode job is the task's own green; the composition job showed one transient bootstrap-deadline flake at `e70986a` attempt 1, green on rerun and at `942d69b` — raise an Issue only on recurrence. Exception EKO-1-12/R-02 discharged; its register entry removed in this commit.

- [x] **EKO-1-27** — Set the release.yml runtime job bound from the recorded suite durations so the next release tag's runtime job completes instead of cancelling (#138).
  *Done when:* the `runtime` job of `release.yml` carries `timeout-minutes` equal to the value decided at gate 1 (G-1, recommended 360 to match `ci.yml`'s C-5 jobs) and ≥ the longest completed duration of the same suite on this task's tree (EKO-1-25 recorded 126.4 / 122.6 min); a static bound guard (Analyst-named, house style `test_eko125_k04/k05_*`) passes and a planted wrong value fails it; the PR body states the value against the recorded durations observed on this task's CI runs (URL in the PR, first `main` run in the gate-3 PR); a duration reaching the bound returns the value to gate 1; no release tag is pushed by the task; everything in `release.yml` except the one bound is unchanged. Confirmation at the next human-pushed release tag: the runtime job completes, not cancelled (G-2).
  **Out of scope (explicit):** fixing runtime failures (#140–#144, closed); other release.yml job bounds; shortening/splitting the suite (EKO-1-25 C-3); pushing a tag or making a release (human-only); hang-detection beyond the bound value; EKO-1-20/weakening-1 (EKO-1-25 C-6).
  After EKO-1-25 (its C-4 deferred this Issue).
  **Done 2026-11-13:** merged in [PR #154](https://github.com/TanerCRB/Eko_CRM/pull/154) as a merge commit `105450a` (merge-commit, not squash — the pinned pair `044e957`..`bb5f855` verified reachable from `main`); verified at `728f204` (surface byte-identical from `ea4e3ab` through the EKO-1-28 merge-in; Guardian round 1 PASS on the merge diff). The bound 60→360 (C-1) with the one provenance comment (C-3); guards `backend/tests/static/test_eko127_k01/k02/k03_*.py` — 53 nodes, k01 a live invariant, k02/k03 pair-frozen — green locally and in CI; QA round 0: mutations M-1a/b/c, M-2b, M-3b and guard-gutting M-4..M-8 all killed (Base `bb5f855`, patches in the PR). K-04 (human, accepted at gate 2): PR run [43406013490](https://github.com/TanerCRB/Eko_CRM/actions/runs/43406013490) — `runtime-checked` 148.5 min, composition 154.1 min, completed not-cancelled under 360 on the merged suite; first `main` run at the merge [43416999762](https://github.com/TanerCRB/Eko_CRM/actions/runs/43416999762) — 147.7 / 155.7 min, both success (observed, not assumed). K-05 (human, accepted): origin tags still only `v0.1.0`/`v0.1.1`, no release run in the window, no tag pushed by the task. The release variant of the job stays untimed as a whole (C-2): the next human-pushed tag confirms, a follow-up Issue is due if its runtime job cancels. Guardian and Auditor PASS; Reviewer PASS with 3 Low → follow-ups #152, #153; exception EKO-1-27/boundary-1 entered in the exception register; role write-set gap #137 stands.

- [x] **EKO-1-28** — Committed regression guard for the bootstrap re-close failure branch (#119).
  *Done when:* a committed runtime test drives `open_gate`'s re-close-failure path (the
  `proxy re-close failed; listeners not confirmed closed` record and `exit 1`) through a
  forced-fail mode or stub hook, contrasted with the success path on the same mechanism; deleting
  the record call or the `return 1` turns that committed test red (qa3-3's ad-hoc stub result is
  reproduced in-tree); the shipped failure semantics of `scripts/keycloak-bootstrap.sh` are
  unchanged for every caller that does not set the hook; exception EKO-1-12/R-32 is removed at
  this task's gate 3.
  **Out of scope (explicit):** any other bootstrap branch's coverage; the secret-scan raw-format
  teeth (#120, EKO-1-29); behavior changes to the real restart path; CI bound changes.
  After EKO-1-12.
  **Done 2026-11-13:** merged in [PR #151](https://github.com/TanerCRB/Eko_CRM/pull/151) as `28196a1`:
  test-only hook `EKO128_FORCE_RECLOSE_FAIL` consulted only at the re-close point (pure addition
  `133/0`, shipped `if/else/return 1` byte-identical, reviewer-traced leak-bounded by `set -e`),
  `backend/tests/runtime/test_eko128_reclose_failed_branch.py` four cases (clause-content
  discrimination, unset/empty shipped path, healthy-composition reach boundary), `--self-test`
  9→13 reclose cases. Verification: guardian/reviewer/auditor PASS (reviewer Lows: budget carried
  at ~42.2 min per runtime job, sed-verify diagnosability); QA PROOF HOLDS — Q-1/Q-2/Q-3/Q-6
  independently killed with sha-witnessed reverts; Q-4/Q-5/Q-7 not run under host memory
  exhaustion (pre-hook control on the dev trail; the order and stub-fallthrough contrasts keep
  only the offline restart-count teeth) — accepted by the human at gate 2 with the merge; K-04
  closed by the PR-head run [43318789453](https://github.com/TanerCRB/Eko_CRM/actions/runs/43318789453):
  both runtime jobs pass, the four `test_eko128_*` IDs PASSED un-skipped in the listings.
  Exception EKO-1-12/R-32 removed by this check-off. Dev assumptions A-01/A-02 ratified at gate 2.

- [x] **EKO-1-29** — Give the tracked-additions secret scan raw-format teeth (#120).
  *Done when:* `SECRET_ENV_ASSIGNMENT` in `backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py`
  flags raw `NAME=value` assignment shapes in scanned files (not only diff-form `+`-prefixed lines),
  proven by a committed plaintext plant turning the scan red and its removal turning it green, in a
  scanned path beyond `proxy/` if the plant design demands; the widened prefix set from EKO-1-12 stays
  intact; exception EKO-1-12/Q3-1 is removed at this task's gate 3; the Q3-2 formatter-drift half is
  re-checked against current main and recorded as already fixed or given its own carrier.
  **Out of scope (explicit):** changing what counts as a secret value beyond assignment shape; CI
  wiring; the runtime-side log scans.
  After EKO-1-12.
  **Done 2026-11-13:** merged in [PR #159](https://github.com/TanerCRB/Eko_CRM/pull/159) as `412fc81`
  (CI green at the head: static 2m33s, process-ci; runtime jobs skipping — paths outside their
  triggers). The predicate now enumerates every assignment candidate (zero-width wrapper; the
  leftmost-hold swallow that round 1 left — and that base's greedy match hid — is killed and
  pinned): raw `NAME=literal` shapes fire under each of the four EKO-1-12 prefixes across
  line-start, `;|&`, Unicode-separator, `env`/`-e`/`--env` (incl. attached) and quoted/comma-slot
  contexts; diff-form teeth kept (guardian's full-tree base-vs-head floor scan: 0 lost fires);
  self-reference hold narrowed to the statement-comma kwarg shape; linear prefilter and bounded
  quantifiers (worst adversarial probe 589 ms/320k, tree scan ~7 ms). 242 committed guard items
  (11 pre-existing + 116 + 65 + 50); QA M1..M7 killed one-mechanism-each, M8 behaviour-inert
  confirmed with timing; live plant `proxy/qa129-plant.sh` red naming lines [2,3] then green.
  Gate-2 human decisions: the `++`/`+++` glued-artifact family named as accepted-pass
  (`cc62826`, census 0, QA M5 proves the guard is its cause); the pre-existing realm-value CI
  traceback echo raised as follow-up #162. Ledger B-01..B-12 and the three supersessions
  (census 14→17, slot-exclusion rationale, order-insensitivity comment) ratified with the merge.
  Q3-2 recorded as already swept by PR #122. Exception EKO-1-12/Q3-1 removed by this check-off.

- [x] **EKO-1-30** — Separate live from record bound constants in the EKO-1-27 guards so a future retune moves named nodes only, not history (#152).
  *Done when:* a named retune-simulation test drives the imported violation functions with a bound ≠ 360 and every pair-frozen eko127 node stays green with no bare `AssertionError`, only docstring-classified must-move nodes redden; the guard docstring classifies every eko127 node must-move/must-stay-pinned and the simulation agrees node for node; the RAISE annotation no longer claims enforcement k02's claim node lacks (align: a new named plant rejects a rewritten provenance comment; drop: the sentence is gone); `BASE`/`HEAD`/recorded-360 and `release.yml` bytes unchanged, all existing plant names keep their verdicts.
  **Out of scope (explicit):** an actual retune (no duration has reached 360; closing condition: first reaching run); the pair-frozen ci.yml k05 family (retune-inert by construction); comment-content rules beyond C-3 (needs a new gate decision); a repo-wide live-guard sweep (finding none today, verified).
  After EKO-1-27 (its Reviewer findings R-01/R-02).
  **Done 2026-11-14:** merged in [PR #165](https://github.com/TanerCRB/Eko_CRM/pull/165) as merge commit `2125962` (not squashed; the pinned pair `044e957`..`bb5f855` verified ancestors of `main` by the Guardian — reachability no longer branch-dependent); verified at `ef80aa8` (all four evaluating roles read the QA checkpoint `e91de3f`; `ef80aa8` carries only a `ruff format` fix — the Guardian re-ran on the fix diff: whole-file AST-identity with a positive control, the ten QA-cited mutation refs re-verified at both SHAs, corrected list 261, 272, 289, 323, 340, 355, 383, 399, 417, 438). Gate 1: C-1..C-5 — G-1 A (live `BOUND`/`BOUND_LINE` + `RECORDED_*` in k01, k02/k03 import the record pair), G-2 A (drop — the RAISE overclaim sentence removed, mechanism stays exactly as #138 C-3 recorded), Q-A A (parameterized violation functions, no monkeypatch — import-time from-import binding made patching unsound, Analyst fact 7), Q-B A (machine-readable classification in k01's docstring: 55 lines, 1 `move` / 54 `pinned`, agreement test-enforced); scope lock `0ea38245d4168ade1ce05463d63f6748215535c3` accepted unchanged. Mechanism: `backend/tests/static/test_eko130_retune_simulation_separates_live_from_record.py` (9 nodes; `SIMULATED_BOUND = 300` applied through bound-defaulted signatures only — Guardian verified pytest's `getfuncargnames` exclusion) + `test_eko130_qa_contrasts.py` (5 nodes; one-element-changed reversals through the real callables) + `tests/doc-checks/EKO-1-30.sh` (real 5/5, `--self-test` 6/6 incl. M-6a/b/c). Static family 2086→2102 collected (eko127 53→55: the mixed value node split into live/record siblings + a derivation-equality node; all 53 pre-existing names and rejection fragments byte-preserved), QA surface 64→69 passed, ruff/mypy/format clean at the merged head; `.github/workflows/release.yml` untouched by every branch commit. QA: EKO-1-30/M-1a (1/64), M-1b (1/9; first attempt invalidated by a parallel restore, redone sequentially — disclosed), M-2 (5/9 + 16/58, R-01's exact 13 bare plant deaths reproduced in-tree), M-3 (2/2), M-4' (1/1 + paraphrase grammar), M-5 (21/46), M-7a (1/2), M-7b (1/28) — **all killed, none survived**; patches Base `5c9690d` in the PR description. Verdicts: QA PROOF HOLDS, Guardian PASS 0/0/0/0 (×2 incl. fix re-run), Reviewer PASS 7 Low, Security Auditor PASS 0/0/0/0 (conditional: new CI-gate script; premise correction: doc-checks are task-discipline-run, not workflow-wired). The M-1 criterion-text tension (K-01's symptom sentence assumes the Q-A B/C mechanics gate 1 rejected; the criterion's own Edges clause governs — wiring-only observability) was adjudicated concordantly by developer, QA, reviewer and Guardian and confirmed by the human at gate 2 with the merge; assumptions A-01..A-06 ratified with the merge. The 7 Reviewer Lows became follow-up Issues #166 (driver-loop coverage + k01 default direction + 9th unrun mutation), #167 (`SIMULATED_BOUND ≠ live` invariant), #168 (seam polish R-04..R-07); the CI format failure exposed a local-gate gap — recorded as #169. CI note: PR checks green at the merged head (`backend unit tests and static checks` 2m44s; `changes`/`layer check` red there are branch-deletion artifacts — `Invalid symmetric difference expression bf776ef...0cffe20`, same content passed both on `ef80aa8` run 43638010649); the first `main` push run (43638645194) was cancelled 2 s after start with empty jobs (same as 3ca9195's) — infrastructure pattern, main's green rests on the PR-head runs. This gate-3 PR carries the two cost rows the merge window missed (`code_developer-backend_2`, `verification_invariant-guardian_2`).

- [x] **EKO-1-31** — Stop CI tracebacks echoing realm secret values when the k06 realm scan fails (#162).
  *Done when:* a committed guard test drives the real k06 realm-scan machinery to a failing report over
  an in-memory realm carrying one synthetic planted secret and asserts the report names the field path
  and nowhere contains the value (reverting the reporting fix reddens the guard), proven together with a
  QA plant-and-remove cycle whose captured CI log shows the same on the static job; the scan still fails
  the planted realm, every existing k06 node keeps name and verdict, failure reports outside this family
  are unchanged, the new test's own synthetic values pass the k06 scans, the suite is green at the
  merged tip.
  **Out of scope (explicit):** the detection predicate and the raw-format scan (closed EKO-1-12/EKO-1-29
  decisions); a repo-wide traceback policy; runtime-side log scans (carried from EKO-1-29); the
  users-dict personal-data echo (ADR-0005 lens, own task); Actions log retention; pytest-version changes
  to failure-report rendering beyond the pinned 9.2.0 (analyst-proposed line approved at gate 1).
  After EKO-1-29.
  **Done 2026-11-15:** merged in [PR #175](https://github.com/TanerCRB/Eko_CRM/pull/175) as `842138d`
  (CI green at the head `84d845a`: backend static 2m49s, frontend/layer/process-ci pass, runtime jobs
  skipping — paths outside their triggers). Mechanism: `assert_no_forbidden_secret_fields` reports via
  `__tracebackhide__ = True` + explicit `raise AssertionError(path)` — QA's M1/M2 prove the two echo
  channels (frame-argument block ⇔ frame hide; rewritten breakdown ⇔ explicit raise) are orthogonal and
  each mechanism load-bearing; detection trio byte-unchanged. Committed guard
  `backend/tests/static/test_eko131_reporting.py` (18 nodes: subprocess failure-report capture — a new
  use of the proven house harness, converted from planned to executed by QA's mutation run — plus
  fire/hold, 242-id collection snapshot at `bf776ef`, family-scope parse of addopts+ci.yml, C9 fire/hold)
  + QA positive control `test_eko131_qa_contrast.py` (closes the vacuity vector QA found: under blanket
  `--tb=no` the absence claim passes while nothing renders; the control reddens). QA M1..M6 all killed
  with right-reason evidence (patches Base `e9c6453` in the PR description); K-05 CI plant-and-remove
  cycle: plant `88ddce4` → run [43736848440](https://github.com/TanerCRB/Eko_CRM/actions/runs/43736848440)
  static job red on `test_k06_every_export_secret_is_absent_or_an_environment_placeholder`, complete
  2,689-line log names `clients[0].secret` and contains the plant string 0 times (collateral:
  `test_eko112_k01` direct-access node also reddened by the plant client — recorded); removal `f083902`;
  green `84d845a`; record `docs/evidence/EKO-1-31/ci-plant-cycle-2026-11-15.md` (carried by this gate-3
  PR; `f083902` itself received no Actions run — anomaly disclosed there). Full suite 2296 passed at
  `1611c7b`, static 2121 incl. the control. Gate-1 decisions A/A/A + identifier ratified; scope lock
  `3e59204d4629e1b11eeb80f064bbcd8f53eafced` accepted unchanged and held through the PR. Gate 2 taken by
  the human through the merge itself (2026-11-15): dev assumptions A-01..A-05 accepted with the merge;
  K-05 accepted with the CI cycle record (provenance = the human's call per criterion text).
  Verdicts: QA PROOF HOLDS (F-1 criteria-text coupling, F-2 channel orthogonality), Guardian PASS
  0/0/0/0 ×2 (round 0 @ `1611c7b`; fix+merge re-run @ `6d74d42`, incoming eko127/130/132 verified
  orthogonal), Reviewer PASS 2 Low, Security Auditor PASS 1 Low — the two evaluators' converged residual
  (K-04 parse misses `env: PYTEST_ADDOPTS`, `--override=` equals form, `--showlocals` class — the locals
  channel wider than S-1) became follow-up #183; CI-side pre-fix contrast left optional per the evidence
  record. CI fix round 1: the QA checkpoint shipped an annotation defect (`tmp_path: pytest.TempPathFactory`)
  caught only by CI's mypy — fixed at `13b802e` (annotation-only, nothing else rode in, Guardian
  verified); process lesson: step 11a must re-run the type/lint gates on QA's files, not only
  weakening/leftovers. Mutation row: `docs/architecture/capabilities.md` (EKO-1-31); capability row for
  the report-shape silence raised here for the first time (QA's condition — K-05 artifacts now land).

- [x] **EKO-1-32** — Pin the retune simulation's driven-node coverage and bind every k01 `bound_violations` call site to its declared constant pair (EKO-1-30 R-01/R-02 + the 9th mutation, #166).
  *Done when:* `_drive` returns the driven id set and baseline/simulated nodes assert `driven == collected` — a truncated loop or silent `continue` fails a named test (QA mutation killed, recorded); new-`test_eko127_*`-module escape resolved per gate-1 variant (glob test fails, or documented deliberate freeze); QA mutations "record call site drops the `bound` argument" and "record call site names `BOUND`" each fail a named test; the `RECORDED_RAISE = raise_for(BOUND)` rewiring is run as a mutation and killed by the wiring AST node; `RECORDED_BOUND`/`BASE`/`HEAD`, plant names and verdicts, `release.yml` bytes and the Q-A A signature-parameterization mechanics unchanged.
  **Out of scope (explicit):** #167 and #168 items (own Issues; closing: scheduled); an actual retune (closing: first reaching run); the live node's own `bound` default (driver contract, Q-A A); repo-wide live-default sweep (Reviewer verified single site; closing: a future finding); pair-frozen ci.yml k05 family; comment rules beyond C-3.
  After EKO-1-30 (its Reviewer findings R-01/R-02).
  **Done 2026-11-15:** merged in [PR #177](https://github.com/TanerCRB/Eko_CRM/pull/177) as merge commit `9eaf75e`; verified at `3b10d0f` (QA checkpoint; mutation Base `59cd2ed` developer checkpoint — Guardian proved the two differ only by the QA contrast file + cost rows, every patch applies to both). Gate 1: K-01..K-07 all test-judged, G-1 A (`bound` required) + G-2 A (glob==MODULES) chosen by the human, fast lane approved (risk classes empty, no API surface, no unproven foundation — Architect skipped, record on #166); scope lock `bc3bdbef09941dc2cd98d317a85ee14d0489da2a` accepted unchanged, amended at gate 2 for A-01..A-04. Mechanism: `test_eko127_k01_*` (required `bound` + docstring), `test_eko130_retune_simulation_*` (`_drive` returns the driven set; both driving nodes assert `driven == collected`), new `test_eko132_coverage_bound_pair.py` (glob / requiredness / call-site scan) + `test_eko132_qa_contrasts.py` (5 mirrors). Static family 2102→2110 (2105 dev, 2110 QA), full static green in CI 2m31s; `release.yml` 0-line diff, `RECORDED_BOUND`/`BASE`/`HEAD` and all plant names/verdicts byte-preserved. QA: EKO-1-32/M-1 (2), M-1c (2 — mechanism removal; added after the Reviewer's hand-off so no named mutation stayed paper), M-2 (2), M-3 (1), M-4 (7), M-4b (2), M-5 (scan + mirror; the 9/9-green sim leg demonstrated R-02's value-blindness), M-6 (**the ninth mutation retired**, 3), M-7 (9 + doc-check anchor rc=1), M-8 (5), M-7a-repro (1/2, exact EKO-1-30 signature) — **all killed, none survived**; the eight EKO-1-30 labels reproducible on the post-task tree (2 re-run on disk, 6 cited through in-tree teeth). Verdicts: QA PROOF HOLDS, Guardian PASS 0/0/0/0, Reviewer PASS 5 Low, Security Auditor skipped (no trigger — skip row in the register). Gate 2: A-01..A-04 accepted with the merge by the human (amendments inside the criteria markers; A-03's red-side test owed — recorded as #181, merged without it by the human's decision). The 5 Reviewer Lows became follow-up Issues #178 (R-02/R-04/R-05 driven-surface fidelity), #179 (R-03 callee-alias scan), #180 (R-01 mirror literal vs retune day), #181 (A-03 contrast test); #167/#168 remain scheduled siblings. Mutation patches: [PR #177](https://github.com/TanerCRB/Eko_CRM/pull/177) description (inline hunks, Base `59cd2ed`). No recorded exceptions; no capability claim beyond the row below.
- [x] **EKO-1-33** — Stop EKO-2-01 runtime login tests failing intermittently on main CI (#186).
  *Done when:* cause named with evidence; a deterministic test fails before / passes after the fix; the three named K-04/K-05 tests pass in a loop and both runtime jobs are green on `main` in consecutive runs.
  **Out of scope (explicit):** weakening the product's strict token-expiry rule; loosening K-04/K-05 assertions; #183, #178, EKO-2-02; retry/re-run masking.
  After EKO-2-01; before EKO-2-02 gate 2.
  **Done 2026-11-17:** merged in [PR #190](https://github.com/TanerCRB/Eko_CRM/pull/190) as `06f8075` by the human on 2026-11-17; verified at `9708fce` (QA checkpoint of fix round 1; the PR head `eadc276` differs from it only by cost-register rows). Cause: the EKO-2-01 K-04/K-05 runtime carriers logged in with a 1-second access token; the OIDC stub truncates `iat` to the whole second, so a token had 0-1 s of life at minting, and the callback's strict no-leeway check (`exp <= now`, ADR-0003, unchanged under G-1 A) refused it on a slow runner. Fix, test code only (no change under `backend/app/`): `expired_logins` in `backend/tests/runtime/eko201/processes.py` logs in with a 6-second token, restores the 240-second lifespan, waits on the wall clock until the real `exp` has passed and asserts one access token per login; the three carrier files use it (G-2 A). Evidence: K-01 `test_eko133_k01_short_lived_login_is_refused_by_expiry_at_the_pre_fix_harness` with its 6-second contrast; K-02 `test_eko133_k02_short_lived_login_survives_a_slow_callback`, red at the pre-fix harness; K-03 `test_eko133_k03_callback_refuses_a_token_at_its_expiry_instant` pins the strict rule; QA's `test_eko133_qa_contrasts.py` (K-04 premise, K-05 refused once); `tests/doc-checks/EKO-1-33.sh` (no re-run step). Verdicts: QA PROOF HOLDS at `94d740c` and `9708fce`; Invariant Guardian PASS at `7c115af` and `9708fce`; Reviewer STOP at `7c115af` (R-01, thin timing margins in the new tests), fixed in round 1, PASS at `9708fce`; Security Auditor skipped (no trigger); Architect skipped (fast lane approved at gate 1). Gate 2: A-01..A-07 accepted (amendments inside the criteria markers, scope lock `76755b84`), K-06 judged met by the human, M-11 let through as a recorded exception. CI on `main`: [run 44049048871](https://github.com/TanerCRB/Eko_CRM/actions/runs/44049048871) at `06f8075` fully green, both runtime jobs included; [run 44056698733](https://github.com/TanerCRB/Eko_CRM/actions/runs/44056698733) at `949a97e` (the merge of #191) red in both runtime jobs with one test each, `test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement` with `net::ERR_NETWORK_CHANGED` (#192, a separate flake), with no `__Host-eko_session` failure and all 90 runs of the EKO-2-01/EKO-1-33 login-carrier tests passed; the human accepted the "consecutive green runs" condition as met on that evidence on 2026-11-17. The local 20-iteration loop failed only on the pre-existing pool-exhausted 503 (#188, Exception EKO-1-33/K-06a). Mutation patches: [PR #190](https://github.com/TanerCRB/Eko_CRM/pull/190) description.

- [x] **EKO-1-34** — Stop the frontend-replacement runtime browser tests failing intermittently with `net::ERR_NETWORK_CHANGED` (#192).
  *Done when:* cause named with evidence; a deterministic test fails before / passes after the fix; the two named K-06 tests pass in a loop and both runtime jobs are green on the PR head and on `main` in consecutive runs; what the tests prove is not reduced.
  **Out of scope (explicit):** `__Host-eko_session` (EKO-1-33); changing frontend-replacement behavior; retry/re-run masking; loosening or skipping the K-06 assertions; #188 and runner load.
  After EKO-1-33.
  **Done 2026-11-19:** merged in [PR #197](https://github.com/TanerCRB/Eko_CRM/pull/197) as `de155ba` by the human on 2026-11-19; verified at `64a37b3` (QA checkpoint of fix round 1; the PR head `52e8c78` differs from it only by cost-register rows and evidence documents). Cause (K-01, judged by the human): the `fresh` fixture's `--force-recreate` gives the proxy a new veth, and its IPv6 link-local address leaving duplicate address detection landed inside `browser_login`'s first redirect, which Chromium aborts with `net::ERR_NETWORK_CHANGED` (pre-fix instrumented run 44169988387, `docs/evidence/EKO-1-34/pre-fix-probe-2026-11-17.md`). Fix, test harness only (no change under `backend/app/`, `frontend/`, `scripts/` or any workflow; K-07 `tests/doc-checks/EKO-1-34.sh`): `settle_host_network` in `backend/tests/runtime/eko134_host_network.py`, called right before `browser_login` in both K-06 tests, waits until every interface on the composition's bridges has left address detection, bounded at 10 s with a named `HostNetworkNotSettled`. Evidence: K-02 `test_eko134_k02_network_change_during_login.py` (red with `ERR_NETWORK_CHANGED` at the pre-fix harness, green at the fixed one, 5 of 5 on the Linux probe; Linux-only, skips on Docker Desktop, Exception EKO-1-34/weakening-1); K-03 `test_eko134_k03_one_time_login_fault.py`, QA's `test_qa_eko134_k03_redirect_fault.py` and the static `test_eko134_login_site.py`; K-04 fixed-tree loop 40 of 40 and 20 of 20 with 0 `ERR_NETWORK_CHANGED` against 5 in 40 pre-fix on the same image (`docs/evidence/EKO-1-34/fixed-tree-probe-2026-11-18.md`). Verdicts: QA PROOF HOLDS at `c075cf3` and `64a37b3`; Invariant Guardian PASS at `c1b311b` and `64a37b3`; Reviewer STOP at `c1b311b` (R-01, the K-02 tests raced address detection), fixed in round 1 (privileged DAD hold, Q-5 A), PASS at `64a37b3` (R-02 is #205); Security Auditor PASS at `c1b311b` and `64a37b3` (S-01, a probe redaction gap: the full-job artifact of run 44387692426 and the artifact of run 44169988387 were deleted, the round-0 artifact expires on 2026-12-18). Gate 2: K-01, K-02, K-04 and the PR-head part of K-05 accepted; A-01..A-10 and the infrastructure A-01/A-02 accepted (amendments inside the criteria markers, scope lock `7089b17c`); follow-ups #199–#206; the probe commits are kept as tag `EKO-1-34-probe-r2`. CI on `main`: [run 44523115642](https://github.com/TanerCRB/Eko_CRM/actions/runs/44523115642) at `de155ba` fully green, both runtime jobs included; [run 44532033531](https://github.com/TanerCRB/Eko_CRM/actions/runs/44532033531) at `416fa46` (the merge of #198, the next push to `main`) fully green, both runtime jobs included. Mutation patches: [PR #197](https://github.com/TanerCRB/Eko_CRM/pull/197) description and tag `EKO-1-34-probe-r2`.

- [ ] **EKO-1-35** — Check the frontend API types (auth, customers, country list) against the backend OpenAPI document (#161).
  *Done when:* a CI check (or generation) fails when `SessionInfo`, a customer type, or the `country` code list disagrees with the OpenAPI document; renaming `SessionInfo.name` in the backend alone fails it; swapping one country code for a non-ISO pair fails it.
  **Out of scope (explicit):** choosing generation vs comparison; backend schema changes; runtime response validation; types for endpoints not yet built (they must join the check in their own Story).
  After EKO-3-01.

- [ ] **EKO-1-36** — Prove the two gate-2 behaviors of the frontend contract check with tests (#214).
  *Done when:* a test shows an unknown schema keyword on a checked component failing the contract check naming the type (contrast: each ignored keyword passes; removing the fail-closed branch fails it); the K-05, K-06 and K-07 live base comparisons are shown inert against a base that already contains `backend/tests/support/frontend_contract.py` and live against one without it, neither reading the moving `origin/main`.
  **Out of scope (explicit):** changing the ignored keywords or relaxing the fail-closed reader (A-07); changes to `frontend_contract.py` or to the existing EKO-1-35 tests; types for endpoints not yet built.
  After EKO-1-35.

## EKO-2 — Access

- [x] **EKO-2-01** — Require login for the whole application.
  *Done when:* a test proves every API operation except login answers 401 without a valid session
  (contrast: the same call with a valid session succeeds); the frontend sends an unauthenticated
  user to login; a user with no Google account linked can log in.
  **Out of scope (explicit):** user administration screens — the administrator uses the identity
  server's console.
  **Done 2026-11-16:** merged in [PR #176](https://github.com/TanerCRB/Eko_CRM/pull/176) as `7772141` by the
  human on 2026-11-16; code verified at `a522c07` (QA PROOF HOLDS at `1f074dc`, the last QA checkpoint,
  test-code-only fix round 3 after it; Invariant Guardian PASS at `a522c07`; Reviewer PASS at `41a0e3f`;
  Security Auditor PASS at `6cce13a` after PASS WITH RESERVATIONS at the earlier checkpoints; the Reviewer
  and the Auditor were not re-run in later rounds by the human's decisions, as the PR description states).
  Mechanism: every API operation except login start, login callback and health requires a server-side
  session established through the company Keycloak realm (app-wide access dependency with exactly three
  exemptions; OIDC login, callback, session, refresh and logout; sessions and login transactions in
  migration `0003_sessions_and_login_transactions`; one cross-process refresh per session under a
  session-level advisory lock; a 0.5-second pool checkout bound), the SPA session gate and logout, the
  gate-1 realm policy (30-minute idle / 10-hour absolute session, MFA for every staff account,
  12-character passwords, 15-minute lock after 5 failures) and one restricted Polish login theme in the
  custom Keycloak image. Three fix rounds; round 3 (test code only: the API-compatibility step built the
  application without the four authentication settings, and the EKO-1-07 browser carriers were not
  adapted to the login) went beyond the two-round limit with the human's approval. CI, stated plainly: at
  the head `1b735c2` eight of nine checks were green; "runtime tests on the composition" was red, 1
  failed / 592 passed — `test_k06_frontend_replacement.py::test_r01_two_consecutive_lazy_chunk_failures_stop_after_one_recovery`
  failed in `browser_login` with `net::ERR_NETWORK_CHANGED`, judged environmental by the driving session
  (the same test was green in the release-mode runtime job at the same SHA); the human merged without a
  rerun. Gate 2 taken by the human through the merge itself. The UNDECIDABLE items K-07 (human judgement
  of the Polish wording and look of the Keycloak pages, captured in `docs/evidence/EKO-2-01/pages/`),
  U-01 (is there a per-address rate limit in front of the application host) and U-03 (provenance of the
  two pinned images) were carried in the PR description as pending decisions; the description records no
  human decision on them, so they remain open for the human. Five SURVIVED mutations (M-24, M-102, M-103,
  M-116, M-117; QA explains each as equivalent or redundant) were listed for the human in the PR
  description under the `schema` risk class and sit in the mutation table; the PR was merged with them.
  Recorded exceptions B-03 (one anonymous caller can fill the open login-transaction cap; blocks again
  2026-12-15; follow-up #170) and `weakening-1`..`weakening-5` (blocks again 2027-05-15; owner and date
  were proposals in the PR description) are entered in `docs/architecture/exception-register.md`.
  Follow-ups named in the PR description: #161 (G-01, the hand-written frontend auth types are not
  checked against the OpenAPI document), #170 (per-address limit on login starts and a Polish page for a
  refused login start; blocks go-live of the application host to the internet), #171 (tie U-02 to the
  pinned base image).

- [x] **EKO-2-02** — Carry roles and account state into every request.
  *Done when:* tests prove a deactivated account cannot log in and its data stays; the backend
  knows the caller's role and user id; one person holding manager and administrator roles gets
  both; there is no self-registration path.
  **Out of scope (explicit):** per-resource ownership rules — each feature task proves its own.
  **Done 2026-11-17:** merged in [PR #189](https://github.com/TanerCRB/Eko_CRM/pull/189) as `77d2643` by the human on 2026-11-17; code verified at
  `857486a` (QA PROOF HOLDS at `d953190`, product code byte-identical at `857486a`; Invariant Guardian,
  Reviewer and Security Auditor PASS at `857486a`, 0 findings). Mechanism: the application-wide access
  dependency refuses by client role — role-less 403 everywhere outside the three session-exempt routes
  except logout, administrator-only 403 outside the non-CRM list, `manager`+`administrator` as manager;
  roles only from the verified token, rebuilt on every refresh; caller identity typed as
  `app.domain.Caller`; against the running Keycloak, disable and role removal reach existing sessions
  within 300 s while data stays; the SPA no-role screen with a working logout. One fix round (B-01, a
  role-less session could not log out; R-01, the administrator exclusion was opt-in per route), decided by
  the dated ADR-0003 addendum of 2026-11-16, appended in this commit to
  [`ADR-0003-identity-and-access.md`](architecture/decisions/ADR-0003-identity-and-access.md) from the draft
  [`EKO-2-02-adr0003-roles-addendum-draft-2026-11-16.md`](architecture/decisions/EKO-2-02-adr0003-roles-addendum-draft-2026-11-16.md);
  it restates ADR-0003-C5 and supersedes gate-1 OQ-1 A. Gate 2: every developer assumption (backend
  A-01..A-07, frontend A-01..A-04) accepted by the human on 2026-11-17 and recorded as amendment lines
  under the criteria of #22 (scope fingerprint `44af1eb9`); no UNDECIDABLE; no recorded exceptions. The
  K-04 tests are keyed under K-05 in the PR description. CI, stated plainly: at the head `f2ad9ad` (a
  merge of `main` bringing EKO-1-33, no product change after verification) eight of nine checks were
  green; "runtime tests on the composition" was red, 1 failed / 703 passed —
  `test_k06_frontend_replacement.py::test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement`
  with `net::ERR_NETWORK_CHANGED`, a pre-existing flake outside this change (#192); the human merged
  with that classification. Follow-ups: #187 (the `eko-backend` client's full role scope), #192.

## EKO-3 — Customers

- [x] **EKO-3-01** — Let a rep create and view their own customers with contacts (#195).
  *Done when:* tests prove: a customer is saved with name and country only, country defaulting to
  Poland (CUS-2); any number of phones and e-mails, each with an optional note on who answers, at
  most one contact primary (CUS-1); phones stored in international format, `+48` by default, and a
  malformed e-mail rejected by the server (CUS-8); a rep sees and creates only own customers; a rep
  reading another rep's customer by id gets a denial that discloses no data, while the manager gets
  the record (ACC-4, PRH-4); an administrator-only account is refused; the SPA lets a rep create a
  customer with contacts and view it, built on the P2 CustomerSheet and ContactEditor material.
  **Out of scope (explicit):** address and NIP validation (EKO-3-02); duplicates (EKO-3-03); list
  search (EKO-3-04); archiving (CUS-9); reassignment (CUS-10); the manager editing another rep's
  customer (ACC-5 edit half); visits, notes, actions, Google Calendar; real customer data. After
  EKO-2-02 and EKO-1-07.
  **Done 2026-11-19:** merged in [PR #198](https://github.com/TanerCRB/Eko_CRM/pull/198) as `416fa46` by the human on 2026-11-19; code verified at
  `8e0c5cc` (QA's checkpoint of fix round 3; its production code is byte-identical to QA's round-3 base
  `e421d12`, which differs only by QA's unit test file; QA PROOF HOLDS at `9ebcc55`, `6228f00`, `f6033ba`
  and `e421d12`; Invariant Guardian, Reviewer and Security Auditor PASS at `8e0c5cc`, 0 findings). Mechanism:
  revision `0004_customers_and_contacts` creates the first product tables, `customer` and
  `customer_contact` (create-only, UUIDv4 keys issued by the application, no sequence or database
  default); `POST /api/customers`, `GET /api/customers` and `GET /api/customers/{customer_id}`; the
  ownership rule enforced by one visibility scope built in `app.domain.ownership` from the caller and
  required by every `data` function on an owned table, applied in the selecting statement (gate-1 O-1 A,
  ADR-0003-C35); another rep's customer answered exactly as an identifier that exists nowhere (C33);
  the access answer given before the request body is decoded, on every route, by `AccessFirstRoute` and
  the `AccessFirstApp` build guard (O-2 A, C34); a `manager`-only account refused when it creates; the
  server-side value rules of CUS-1, CUS-2 and CUS-8; the SPA customer list, create form with its contact
  editor and customer view under `/klienci`. Three fix rounds, all on Reviewer R-01 / Security Auditor B-01
  (the cost of the first body-accepting route) and Reviewer R-02 (the session resolved once per request):
  round 1 (human decision A, 2026-11-18) added the 2 MiB body limit after the access decision, raw-length
  caps before normalisation and the request-scope access cache; round 2 (decision D, 2026-11-18) removed
  `input` from every 422 error and bounded its text to 200 characters and its list to 50 errors; round 3
  (decision D, 2026-11-18, beyond the two-round limit with the human's approval) answers unknown keys with
  one `extra_forbidden` error per request model instead of one per key. The record-ownership addendum of
  2026-11-17, accepted at gate 1 (O-3 A), is appended in this commit to
  [`ADR-0003-identity-and-access.md`](architecture/decisions/ADR-0003-identity-and-access.md) from the draft
  [`EKO-3-01-adr0003-record-ownership-addendum-draft-2026-11-17.md`](architecture/decisions/EKO-3-01-adr0003-record-ownership-addendum-draft-2026-11-17.md),
  with the G-01 sentence (decision A, 2026-11-18) and the request-body rules of the fix rounds, the
  unknown-key validator recorded as `mode="wrap"`, as the human decided at gate 2; it adds controls
  ADR-0003-C33..C35 and restates none. Gate 2: every developer assumption (backend A-01..A-12, frontend
  A-01..A-08, frontend A-05 a deviation from K-07's literal phone value) accepted as built by the human on
  2026-11-19 and recorded as amendment lines under the criteria of #195 (scope re-locked, fingerprint
  `7ee0b16d`); no UNDECIDABLE; the human also kept M09 (the visibility scope's refusal of a caller with no
  CRM role, shadowed by the role gate) as defence in depth, kept the lone-surrogate 422 fallback as a guard
  against a library change, accepted the 200-character and 50-error bounds as part of the contract,
  accepted `ctx.error` of `value_error` as the rule's message text instead of `{}`, and accepted as a known
  limit that a `PydanticCustomError` added later to a request model could answer 500 on the unknown-key
  path. One recorded exception, EKO-3-01/H6-D (the K-07 changeset guard's exact-value allowance for
  K-03's criterion value in its one test file; blocks again 2027-05-19), is entered in
  `docs/architecture/exception-register.md`. CI, stated plainly: at the head `d6c69b7` (only cost-register
  rows after verification) every check was green except "runtime tests on the composition", red with 2
  failed / 857 passed — `test_k06_frontend_replacement.py::test_k06_open_spa_recovers_unloaded_lazy_chunk_after_frontend_replacement`
  and `::test_r01_two_consecutive_lazy_chunk_failures_stop_after_one_recovery`, both with
  `net::ERR_NETWORK_CHANGED` in `browser_login`, the pre-existing flake #192 (fixed on `main` by #197 after
  that run started); the release-mode runtime job ran the same tests green (859 passed); the human merged
  with that classification. CI on `main` at `416fa46` when this entry was written:
  [run 44532033598](https://github.com/TanerCRB/Eko_CRM/actions/runs/44532033598) (`process-ci`) green;
  [run 44532033531](https://github.com/TanerCRB/Eko_CRM/actions/runs/44532033531) (`ci`) still pending, so
  no result of it is claimed here. Mutation patches: the two comments on
  [PR #198](https://github.com/TanerCRB/Eko_CRM/pull/198) (round 0; fix rounds 1-3). Follow-ups: #196 (a
  request-body limit and timeout at the proxy), #161 (frontend API types, now including the customer
  types and the hand-copied country list, checked against the OpenAPI document).
