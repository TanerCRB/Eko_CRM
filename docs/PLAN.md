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

- [ ] **EKO-1-03** — Record the deployment and backup decision (ADR-0004).
  *Done when:* ADR-0004 is "Accepted <date>" and fixes the container runtime and composition, the
  cloud-agnostic constraints, HTTPS exposure under a company domain, secret handling, a daily
  off-server database backup and the restore procedure, with the company IT department as
  operator.
  **Out of scope (explicit):** provisioning the real server; the domain — the human provides it
  later.

- [ ] **EKO-1-04** — Record the personal-data handling decision (ADR-0005).
  *Done when:* ADR-0005 is "Accepted <date>" and names the modules holding customer personal
  data, what is logged and what never is, archiving vs. erasure, and that only synthetic data is
  used until the GDPR impact assessment; `docs/architecture/architecture-sensitive-paths.md`
  lists those paths.
  **Out of scope (explicit):** the GDPR impact assessment — after the MVP; erasure — later.

- [ ] **EKO-1-05** — Record the Google Calendar integration decision (ADR-0006).
  *Done when:* ADR-0006 is "Accepted <date>" and fixes the OAuth flow and scope, token storage
  and encryption, how app-created events are recognised, change detection able to meet VIS-6
  (`docs/product/project-brief.md`), the conflict rule VIS-5, retry of unsynchronised visits, and
  the testing-mode limits with the path to Google verification.
  **Out of scope (explicit):** implementation; the Google verification itself — later.

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
