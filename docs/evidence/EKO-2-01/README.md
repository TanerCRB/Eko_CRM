# EKO-2-01 — infrastructure runtime evidence (developer-infrastructure)

Task: EKO-2-01 (Issue #21), locked criteria K-01..K-07 (scope fingerprint
`ca7cd81c2d416cbf70f81f19bea10d5b82645999`). Worktree branch `EKO-2-01-login`, base
`cd91504782a234253b675d93a7ff1fb89b9f9b2c`, with this role's changes uncommitted at the time of
every run below. Every run used a throwaway composition with its own project name, a fresh
synthetic environment file from `scripts/dev-env.sh` and its own volumes, removed afterwards. All
accounts, addresses and markers are the invented ones in `backend/tests/support/eko201_keycloak.py`
and `backend/tests/support/eko112_fixtures.py`. No credential, token, cookie, session identifier,
OTP secret, one-time code or real personal value is recorded here. Local runs on one Windows 11
host with Docker Engine 29.8.2; nothing here claims production behavior.

## Images

| Image | Identifier | Note |
|---|---|---|
| Official base `quay.io/keycloak/keycloak:26.8.1` | index digest `sha256:3f3c5f8e03c614774b4bd9173b88391fefa4153bfc010d8012d59ad825377332` | Upstream republished the 26.8.1 tag; the copy this host held before (`sha256:a78d6b79…`, the base EKO-1-12 recorded) is older (its JDK is 21.0.12, the current one 21.0.13). The build resolved the current one. |
| Custom `localhost/eko-crm/keycloak:26.8.1-eko112` (theme-bearing, final, F-4) | image ID `sha256:2c7036e35c1050fbf3492e443e8518c13e8ecc363e52ebff48c2c8fa894e4deb`, built 2026-11-13T08:30Z by `docker compose build keycloak` | Differs from the R4 image only in `login/messages/messages_pl.properties` (the `loginTotpStep3` override, human decision F-4). Local build: image (config) digest, no registry digest; not a checked-image digest (EKO-1-12/R-02, #118). |
| Custom `localhost/eko-crm/keycloak:26.8.1-eko112`, rebuilt from the same `identity/` context | `sha256:4f2d5265a7244eaac5f471063a0bf37b1d0e458b57dc9e12f0f555ba232a2b24` (R8), `sha256:cdb4bc4a1bace33967feba4a7e7c4fa1aeaa3fa0359212737367352684e026ea` (R10) | A rebuild of an unchanged context without a warm cache gives a new image ID: the build is not bit-reproducible. The image carrier re-proves the byte-for-byte theme copy and the C35 file difference on every build. |
| Custom `localhost/eko-crm/keycloak:26.8.1-eko112` (theme-bearing, R4) | image ID `sha256:6d6e87bc0ded6395a814d22ca21306f73eb3e0fb18d6f15e58ddb579b4b49960`, built 2026-11-13T01:54Z by `docker compose build keycloak` | Tag kept (G-D A); the identifier tells it apart from EKO-1-12's `sha256:387f615a…`. A local build has no registry digest; this is its image (config) digest. Not a checked-image digest (exception EKO-1-12/R-02, #118). |
| Custom, previous theme-bearing build | image ID `sha256:dae740477a69737b03aacd3ca0e4c99e0989274d1c0831080d026c088ff6ce73` | Run R3 only. Differs from the final one only in `login/resources/css/eko-crm.css` (the header colour fix). |

The tag is shared by every worktree on a host. Rebuilding it here replaced the image that other
worktrees' compositions start.

## Probes (scratch Keycloak 26.8.1, `start-dev`, one container, removed afterwards)

### 2026-11-12 — event types MFA makes emittable (ADR-0005 reachable-set addendum, G-E A)

Scenario: the versioned export imported into a scratch realm with `enabledEventTypes` emptied
(every type stored), then one invented account enrols an OTP credential at login, logs in with a
code, submits one wrong code, has its credential removed through the admin REST API, and enrols
again.

Observed stored user-event types: `LOGIN`, `LOGIN_ERROR` (error `invalid_user_credentials` for the
wrong code), `UPDATE_CREDENTIAL`, `UPDATE_TOTP`. The removal produced only an admin event
(`ACTION` on `USER`, resource path `users/<id>/credentials/<id>`). The secret appeared in no event.

Meaning: enrolment makes `UPDATE_CREDENTIAL` and `UPDATE_TOTP` emittable. They are not in the
application realm's stored set (`enabledEventTypes` is unchanged, G-E A), so nothing new is
stored; the reachable-set addendum of 2026-11-11 is re-opened for the record (see the report).

### 2026-11-12 — an explicit default port in `KC_HOSTNAME`

Scenario: `KC_HOSTNAME=https://auth.example.test:443`; read the master realm's discovery document.

Observed issuer: `https://auth.example.test/realms/master` — Keycloak drops the explicit `:443`.

Meaning: `compose.yaml` builds `APP_OIDC_ISSUER` and `APP_ORIGIN` with the published HTTPS port,
as `KC_HOSTNAME` and the proxy's redirect already do. With any port other than 443 they equal
what Keycloak writes and what a browser sends; with 443 they would not (open point in the report).

## Page captures

`pages/` holds the redacted HTML of each page state the K-07 page check walked in a real browser
(Chromium through the composition's public listener). The redaction removes every per-flow
identifier, the enrolment secret, its QR image and the auth-session hash. Screenshots are binary
and are not kept in the repository: the change-set scans read every added file as text. Regenerate
them with `EKO201_SCREENSHOT_DIR=<directory outside the checkout>` (and
`EKO201_EVIDENCE_DIR=<directory>` for the HTML) set on
`uv run pytest -m runtime tests/runtime/test_eko201_k07_pages.py`.

The automated check decides Polish language, the Eko_CRM name and the absence of default-English
text on each page. Linguistic adequacy, wording in each state and visual acceptability, restrained
branding included, are for the human review (evaluators: UNDECIDABLE).

## Runs

All commands ran from `backend/` with `uv run pytest -p no:cacheprovider`; runtime ones with
`-m runtime`. Times are UTC.

| # | Started | Scenario | Image | Observed |
|---|---|---|---|---|
| R0 | 2026-11-12 | Fail-first, static: `tests/static/test_eko201_realm_export.py`, `test_eko201_k07_theme.py`, `test_eko201_k07_image_and_composition.py`, `test_eko201_composition_wiring.py` before the export, theme, Dockerfile and composition changes | — | Red for the missing behavior: `failureFactor` 30 ≠ 5, no `ssoSessionIdleTimeout`, no browser flow, no password policy, no `loginTheme`, the `.invalid` callback; no theme directory; "expected one theme COPY, found 0"; the backend received none of the five settings. The C2 sum (240 + 30 + 30 ≤ 300) and the absence of theme mounts and cache settings already held. |
| R0b | 2026-11-12 | Fail-first, image: the image-theme reader against the pre-theme custom image `eko-crm/keycloak:checked` (`sha256:f1b3f489…`, 2026-11-10) | pre-theme | `docker cp` of `/opt/keycloak/themes/eko-crm` fails: no such path; the themes directory holds only the base `README.md`. |
| R1 | 2026-11-12T22:14 | `tests/runtime/test_eko201_keycloak_login.py` on the first wiring | theme-bearing (first build) | Red at bootstrap: Keycloak refused the realm import ("A redirect URI is not a valid URI") for the `${APP_ORIGIN}` placeholder. The export now records the relative path `/api/auth/callback`; the bootstrap sets the client root URL from the backend's `APP_ORIGIN`. |
| R2 | 2026-11-12T22:30 | The EKO-2-01 Keycloak carriers (login, OTP scan, pages, image) | `sha256:dae74047…` | 6 passed, 3 failed — all carrier defects, fixed: the logout carrier shared an account with the login carrier (two SSO sessions), and the image listing ended non-zero on dangling symbolic links of the base image. |
| R3 | 2026-11-12T22:44 → 2026-11-13T01:48 | Every `test_eko112_*` runtime carrier (12 files) and every EKO-2-01 Keycloak carrier except the image ones (`test_eko201_keycloak_login.py`, `test_eko201_k06_otp_secret.py`, `test_eko201_k07_pages.py`, `test_eko201_k07_c36_startup.py`): 44 tests | `sha256:dae74047…` | 43 passed, 1 failed: `test_eko112_k04_reset_and_log_privacy.py::test_k04_every_required_event_type_is_stored`. Cause, from a probe on a kept scratch composition: Keycloak's default reset-credentials flow makes an enrolled account enrol again, and the shared helper reused the account's device label, which Keycloak refuses. Fixed in the helper (a fresh label per enrolment); no assertion changed. |
| R4 | 2026-11-13T01:53 | `tests/runtime/test_eko201_k07_theme_image.py` (builds the final image), then `test_eko112_k04_reset_and_log_privacy.py` and the four EKO-2-01 Keycloak carrier files, with `EKO201_EVIDENCE_DIR` and `EKO201_SCREENSHOT_DIR` set | `sha256:6d6e87bc…` (final) | 4 passed in 37.5 s; 10 passed in 660.5 s. The HTML in `pages/` is this run's. |
| R5 | 2026-11-12/13 | The H6-1 planted-revision suites (13 files) on the composed backend, which starts now that the five settings are wired; rerun of their failures alone on a quiet host | — | First run, alongside two other compositions: 65 passed, 6 failed. Alone: the four timing and harness-race failures pass; two fail deterministically, `test_adr0004_c13_migrate_revision_check_ancestor_is_upgraded_with_its_lineage` and `test_adr0004_c13_qa_contrast_without_the_alembic_version_table_migrate_upgrades`, with `psycopg.errors.DuplicateTable` at `0003_sessions_and_login_transactions.py:upgrade:24` (the lab's reset leaves revision 0003's tables in place). Backend migration and harness, not this role's paths. |
| R6 | 2026-11-13 | `tests/runtime/eko201` (backend carriers) and the default suite | — | 83 passed; 2121 passed, 542 deselected, 0 failed. |
| R7 | 2026-11-13T08:28 | F-4: `loginTotpStep3` overridden. `tests/static/test_eko201_k07_theme.py` before the review entry (1 failed, 28 passed: the key was unlisted), after it with `test_eko201_k07_image_and_composition.py` (50 passed); `tests/runtime/test_eko201_k07_theme_image.py` (builds the image; 4 passed); `tests/runtime/test_eko201_k07_pages.py` with the HTML captured outside the checkout (2 passed) | `sha256:2c7036e3…` | The enrolment page's step 3 now reads "… i kliknij Zatwierdź, aby zakończyć konfigurację", matching its button; the parent's "kliknij Prześlij" fails the page check (in-test contrast). Only `pages/mfa-enrolment.html` was replaced from this run; the other pages are R4's, whose content this change does not touch. |
| R8 | 2026-11-13T09:39 | K-03 composed browser carrier, `tests/runtime/test_eko201_k03_shell_browser.py` (Chromium through the public listener, real backend and Keycloak with MFA, frontend at `c520f69`) | built by the run | 1 passed in 340.6 s. Screenshots of the 7 states outside the repository. |
| R9 | 2026-11-13T09:45 | Fail-first for R8: the same scenario (`run_k03`) on a composition whose `frontend` is built from `825f1d8`, the shell before the session gate (scratch override and script outside the repository) | built by the run | Red in step 1: the anonymous `/` never left `<app-host>` for Keycloak (30 s `TimeoutError` waiting for `<auth-host>`). The served bundle has the shell's "Bliżej Twoich klientów" and neither "Sprawdzanie sesji" nor `api/auth/login`, so the red is the missing gate, not an environment failure. |
| R10 | 2026-11-13T09:52 | F-1 A bootstrap wiring: `tests/static/test_eko201_bootstrap_origin.py` before and after `application_origin()` in `scripts/keycloak-bootstrap.py`; `bash scripts/keycloak-bootstrap.sh --self-test`; then `test_eko201_k07_theme_image.py`, `test_eko201_keycloak_login.py`, `test_eko201_k07_pages.py`, `test_eko201_k03_shell_browser.py` | `sha256:cdb4bc4a…` (rebuilt by the image carrier) | Before: 10 failed, 8 passed (no `application_origin`); after: 18 passed. Self-test 12/12 (3 new origin cases: 443 dropped, 8443 kept, http on 443 kept). Runtime: 9 passed in 396.2 s. |
| R11 | 2026-11-13 | Default suite (`uv run pytest`) after R10 | — | 2152 passed, 543 deselected, 0 failed. |
