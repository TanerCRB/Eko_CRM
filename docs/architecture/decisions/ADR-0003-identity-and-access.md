# ADR-0003 — Identity server, browser session, roles and account lifecycle

**Status:** Accepted 2026-10-23
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

ADR-0001 (Constraint 2) delegates authentication to an external identity server over OpenID
Connect, keeps no password store in the application, and has the backend accept a caller's identity
and roles only as asserted by that server, verified on every request. It forwards to this decision
the product, where the identity server stores its data, the browser flow, how the roles are
carried, deactivation and password reset; ADR-0002 forwards whether the identity server shares the
PostgreSQL server. The brief ([`project-brief.md`](../../product/project-brief.md)) fixes the rules
this decision must meet: section 2 (roles rep, manager, administrator; one person may hold two;
the administrator sees no CRM data), section 5 (own accounts independent of Google, no
self-registration, password reset by e-mail from the identity server through a company SMTP
mailbox that does not exist yet; on-premises, containerised) and ACC-1 to ACC-3. No product task
in EKO-2 fits the architecture until this is decided.

## Decision

### Identity server product

The identity server is **Keycloak**, run as its official container image. Every reference to the
image names a full version (`<major>.<minor>.<patch>`) or a digest, never a floating tag such as
`latest` or a bare major; the version first used is chosen by the walking skeleton (EKO-1-06)
among releases whose documentation lists PostgreSQL 18 as a supported database, and is recorded as
an addendum to this decision. If no such release exists when EKO-1-06 runs, that task stops and
the storage choice below returns to the human as an addendum to this decision, before any Keycloak
container is added. Every later image change that crosses a major version is recorded as an
addendum.

The application uses **one Keycloak realm**. Its configuration (clients, roles, client scopes,
token lifespans, registration and reset settings, SMTP settings without credentials) is kept as a
versioned realm export in the repository under `identity/`, and an environment's realm is created
from it; a realm setting changed only in a console is a defect. Credentials (SMTP password, client
secrets) never appear in that export (secret handling: ADR-0004).

### Identity server storage

Keycloak stores its data in **its own database on the same PostgreSQL 18 server** as the
application database (ADR-0002), under its own database role. Keycloak shares the application's
PostgreSQL server; it does not share the application's database. The application's database role
has no privilege on Keycloak's database and Keycloak's role none on the application's. Keycloak
never runs on its embedded development database outside a developer's machine. ADR-0002's collation and
schema rules (ICU `pl-PL`, Alembic, the controls ADR-0002-C1 to C15) govern the application
database only; Keycloak manages its own schema. Both databases are covered by the same backup and
restore (ADR-0004).

### Browser flow: backend session, no token in the browser

The browser flow is a **backend session**: the backend is the only OpenID Connect client the
browser deals with (a backend-for-frontend), and the single-page application holds no token.

- Login and password reset happen only on Keycloak's pages. Login is the authorization code flow
  with PKCE between the backend (a confidential client) and Keycloak. The user types the password **only on Keycloak's pages**; no backend endpoint receives
  it (ADR-0001-C6). The direct-access (resource-owner password) grant is disabled on every client
  of the realm.
- The tokens Keycloak issues are held **server-side** by the backend, in the application database
  (through the `data` layer, ADR-0002), encrypted with a key read through
  `backend/app/core/settings.py` (key handling: ADR-0004). The browser receives only an opaque,
  random session identifier in a cookie marked `HttpOnly`, `Secure` and `SameSite=Strict`; the
  database stores only a hash of that identifier. No access, refresh or ID token is ever returned to
  the single-page application or readable by its JavaScript.
- A state-changing request (any method other than `GET`, `HEAD`, `OPTIONS`) is refused unless its
  `Origin` header equals the application's own origin.
- The single-page application and the API are served from **one origin** (forwarded to ADR-0004 as
  a constraint on composition and HTTPS exposure).
- Tokens issued to the application carry the subject, the name claims and the roles, and **no
  e-mail address** (the e-mail client scope is not assigned to the application's client).

### How a request is verified, and the 5-minute bound

On every request, one application-wide FastAPI dependency (ADR-0001, Constraint 2) resolves the
session cookie to its stored session and verifies the access token held for it: signature against
the realm's published keys, issuer, audience (the application's client) and expiry. A request
without a session, or whose session cannot be resolved or verified, gets HTTP 401. When the access
token has expired, the backend uses the stored refresh token once to obtain a new one; if Keycloak
refuses (account disabled, session ended), the session is deleted and the request gets 401.

**Bound (at most 5 minutes).**

- After an administrator deactivates an account, a session already issued for that account stops
  being accepted within at most 5 minutes.
- After an administrator removes one role from an account that stays active, a session already
  issued for that account stops being granted that role within at most 5 minutes.

The mechanism is the access-token lifespan: the realm's access-token lifespan plus the backend's
clock-skew leeway is at most 300 seconds, and a new access token is obtained only through a
Keycloak refresh, which Keycloak refuses for a disabled account and builds from the roles held at
that moment. No per-request call to Keycloak is made. Every other session and idle timeout value is
decided by EKO-2-01 and does not relax this bound.

### Roles

- The application's roles are **`rep`, `manager` and `administrator`**, defined as client roles of
  the application's client in the realm. Roles come only from the identity server's verified
  assertion, never from a value the client sends: the backend reads a caller's roles **only** from
  that client's role claim in a token it verified as above. Realm roles, roles of other clients,
  and any role named in a request header, query, body or cookie other than the session cookie are
  ignored. An unknown role name in the claim is ignored.
- One account may hold several roles; the caller is granted all of its roles, that is the union of
  what each role grants. An account holding `manager` and `administrator` has manager rights.
- **`administrator` grants no CRM data.** An account holding only `administrator` is denied every
  API operation that reads or changes customers, visits, notes, actions or dashboards (HTTP 403).
  The administrator manages accounts in Keycloak's administration console of the application realm
  (through Keycloak's own user-management permissions in that realm, granted to holders of
  `administrator`), not through the application.
- **An authenticated account with none of the three roles is denied every API operation** (HTTP
  403). No role is assumed by default: the rights of `rep` require the `rep` role in the claim.
- The identity of the caller passed inward from the access dependency is a value defined in the
  `domain` layer (the subject identifier and the set of roles). `auth` builds it; `services` and
  `domain` receive it and never read a token, a claim or the session.

### Identifier the application stores

The application refers to a staff member **only by the Keycloak subject identifier** (the `sub`
claim) of the one realm. It is stored as received, compared exactly (byte-wise, case-sensitive),
and unique among staff. Username and e-mail are never used as a reference: a change of either, or
two e-mail addresses differing only in case, leave the application's records linked to the same
account.

### Account lifecycle

- **Creation.** Accounts are created only by an administrator in Keycloak's console. User
  self-registration is disabled in the realm; no application endpoint creates an account.
- **Deactivation.** An administrator deactivates an account by disabling it in Keycloak. A disabled
  account cannot log in; its sessions stop being accepted within the bound above. The application
  deletes, changes and reassigns no data on deactivation: records owned or authored by that account
  keep its subject identifier.
- **Deactivation is the only removal** for an account the application's data refers to. Deleting
  such an account in Keycloak is forbidden by this decision. Keycloak does not prevent it
  mechanically; the consequence of breaking the rule is that the records keep a subject no account
  holds, and an account created again for the same person gets a new subject with no access to
  them.
- **Reactivation.** Enabling a disabled account restores access to the same records, because its
  subject identifier is unchanged.
- **Role removal** takes effect within the same bound of at most 5 minutes and changes no data.
- Recovery when no active administrator remains, and the bootstrap of the first administrator, are
  not decided here (ADR-0004).

### Password reset

- Password reset is Keycloak's own forgot-password flow on Keycloak's pages, sending the reset
  e-mail through the **company SMTP mailbox** configured in the realm. The backend sends no reset
  e-mail, has no reset endpoint, and never receives a password.
- The response to a reset request does not reveal whether the address has an account: it is the
  same for an address that belongs to an account and for one that does not.
- A reset does not enable a disabled account: a disabled account still cannot log in after it.
- **Until the company mailbox exists**, the reset e-mail is disabled in shared environments; an
  administrator sets a temporary password in Keycloak's console with the "update password"
  required action, so the user replaces it at the next login on Keycloak's pages. Developer and test
  environments point Keycloak at a local mail-catching container that delivers nothing outside the
  composition. No personal or third-party mailbox (including Gmail) is used as a stand-in.

### Accounts never depend on Google

No identity provider (Google or any other) is configured in the realm, and Keycloak's identity
brokering is not used: no one signs in, and no account is created, through an external provider.
Login works with no Google account linked. Linking a Google account for the calendar (ADR-0006)
creates, authenticates and alters no account, and is not done through Keycloak's brokering.

### Staff personal data

| Held by | Staff personal data |
|---|---|
| Keycloak | username, e-mail address, first and last name, password hash, role assignments, enabled state, active sessions (including their IP address and times); login and admin events only if event storage is turned on |
| Application | the subject identifier, in every record that refers to a staff member; a copy of the display name (given and family name) taken from the verified token at each login, kept after deactivation so attribution of past records stays readable; server-side sessions (hashed session identifier, subject, encrypted tokens, created and last-used instants) |

The application holds no staff e-mail address, username or password. Retention of sessions,
Keycloak events and the display-name copy, and what may appear in logs, are decided by ADR-0005.
How names are rendered is decided by the tasks that display them.

### Layers

`backend/app/auth/` is a layer that may depend on `core`, `domain` and `data`, and **must not
depend on `services`, `api` or `integrations`**. Keycloak is the identity server of this
decision, not an external system in the sense of `integrations` (ADR-0001), so its OIDC client code
lives in `auth`.

**No inner layer may depend on `auth`.** Only `api` and `backend/app/main.py` depend on `auth`;
the layers `domain`, `services`, `data`, `core` and `integrations` each list `auth` under "Must not
depend on" in [`layer-dependencies.md`](../layer-dependencies.md). Because the layer table is
ADR-0001's, this rule is recorded there as the addendum of 2026-10-23.

### Forward references (not decided here)

- ADR-0004 (#16) — one origin for the SPA and the API, Keycloak's exposure over HTTPS (and of its
  administration console), the session-encryption key, client secrets and SMTP credentials, backup
  of Keycloak's database, bootstrap of the first administrator and recovery when none remains.
- ADR-0005 (#17) — retention of sessions, Keycloak events and the display-name copy; logging.
- ADR-0006 (#18) — Google account linking, outside Keycloak.
- EKO-2-01 — session and idle timeout values other than the 5-minute bound; language, branding
  and wording of Keycloak's pages; logout.
- EKO-1-06 / EKO-2-01 — password policy, MFA, brute-force protection.

## Options considered

### Identity server product

| Option | Cost | Closes off |
|---|---|---|
| **A. Keycloak** (chosen; brief §5 preference) | A JVM service needing more memory than the others; frequent major releases, each upgrade an addendum; realm export kept in step with the console. | A lighter identity server; an identity server written in the backend's language. |
| B. Authentik | Python, PostgreSQL-backed; a server and a worker container. Smaller ecosystem of OIDC client documentation; departs from the stated preference. | Keycloak's console and realm export as the administrator's tool. |
| C. Zitadel | Go, PostgreSQL-backed, event-sourced storage that is harder to inspect and restore selectively; departs from the stated preference. | Same as B. |
| D. Accounts in the application itself | Breaks ADR-0001 Constraint 2 (a password store in the application). | Rejected by ADR-0001. |

### Browser flow

| Option | Cost | Closes off |
|---|---|---|
| **A. Backend session (backend-for-frontend), tokens server-side** (chosen) | A session table and encrypted token storage in the application database; an Origin check on state-changing requests; SPA and API on one origin (ADR-0004); `auth` depends on `data`. | Calling the API from another origin with a bearer token; a stateless backend. |
| B. SPA as a public client (code + PKCE), access token in browser memory, sent as a bearer token | No server-side session state, no CSRF surface; but tokens (and a refresh token, or reliance on Keycloak's cookie for silent renewal) are readable by any script running in the page, which renders free text from notes and customers. | Keeping tokens out of reach of a cross-site-scripting flaw. |
| C. An authenticating reverse proxy in front of the backend (e.g. oauth2-proxy) passing identity headers | One more container; the backend must still verify a token, or it trusts headers, which ADR-0001 Constraint 2 forbids. | Verification inside the backend on every request, unless the proxy forwards a token the backend verifies anyway. |

### Meeting the 5-minute bound

| Option | Cost | Closes off |
|---|---|---|
| **A. Access-token lifespan plus leeway ≤ 300 s, renewed only through Keycloak** (chosen) | One refresh call to Keycloak per active session at most every 5 minutes; Keycloak unavailable means sessions end within 5 minutes. | Long-lived access tokens. |
| B. Token introspection on every request | A Keycloak call on every API request; Keycloak's availability and latency become the API's. | Local verification; an API that answers while Keycloak is briefly down. |
| C. Back-channel logout or admin-event push to the backend | Covers deactivation only if Keycloak's event delivery is reliable; role removal is not a logout event. | Nothing, but does not meet the bound alone. |

### Identity server storage

| Option | Cost | Closes off |
|---|---|---|
| **A. Own database on the shared PostgreSQL 18 server** (chosen) | Shared failure domain and resources; a PostgreSQL major upgrade must be supported by both Keycloak and the application. | Upgrading PostgreSQL for one of them alone. |
| B. A second PostgreSQL container for Keycloak | A second database server to operate, back up and restore (ADR-0004), for about ten users. | Nothing. |
| C. Keycloak's embedded development database | Not supported by Keycloak for production use. | Rejected. |

### Identifier the application stores

| Option | Cost | Closes off |
|---|---|---|
| **A. Keycloak subject identifier (`sub`)** (chosen) | Opaque; a person recreated as a new account is a new subject. | Joining application records to a person by e-mail or username. |
| B. Username | Changeable in Keycloak; case questions. | Renaming a username without breaking records. |
| C. E-mail address | Changeable; case variants; puts staff e-mail into every referring record. | Same as B, and a minimal staff-data footprint. |

### Staff display name

| Option | Cost | Closes off |
|---|---|---|
| **A. Copy of the display name from the verified token at each login** (chosen) | A name changed in Keycloak shows in the application only after that person's next login. | Nothing. |
| B. Subject identifier only; names read from Keycloak's admin API by the backend | The backend holds an administrative credential to Keycloak and depends on it to render any attribution. | Rendering attribution while Keycloak is down. |

### Reset e-mail before the company mailbox exists

| Option | Cost | Closes off |
|---|---|---|
| **A. Reset e-mail off; administrator sets a temporary password with a required change; local mail catcher in developer and test environments** (chosen) | The administrator knows a temporary password until the user's next login; self-service reset waits for the mailbox. | Self-service reset before the mailbox exists. |
| B. A personal or third-party mailbox as a stand-in | Credentials of an account the company does not control; a Gmail mailbox makes reset depend on Google. | Accounts independent of Google, in spirit. |
| C. No shared environment until the mailbox exists | Blocks the pilot on the company. | Starting the pilot early. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C1 | The realm export under `identity/` has `registrationAllowed` false, an empty `identityProviders` list, `directAccessGrantsEnabled` false on every client, the application's client confidential with PKCE required, and no `email` client scope assigned to the application's client. |
| ADR-0003-C2 | The realm export's `accessTokenLifespan` plus the backend's configured clock-skew leeway is at most 300 seconds. |
| ADR-0003-C3 | Every reference to the Keycloak image in the repository names a full `<major>.<minor>.<patch>` tag or carries `@sha256:`. |
| ADR-0003-C4 | A test walking every API route: with no session cookie, or a session whose token has a wrong signature, issuer or audience, or has expired and cannot be renewed, each route answers 401. |
| ADR-0003-C5 | A test walking every API route with a verified token holding none of `rep`, `manager`, `administrator` (including one holding realm roles with those names) gets 403 on each route; with only `administrator` it gets 403 on every route reading or changing customers, visits, notes, actions or dashboards; with `manager` and `administrator` it gets the same answers as with `manager` alone. |
| ADR-0003-C6 | A test with a `rep` token adding a header, query parameter or body field naming the role `manager` gets the same answer as without it. |
| ADR-0003-C7 | Against a running Keycloak: a session accepted for an active account is refused (401) within 300 seconds after the account is disabled; a session of an account holding `manager` loses manager rights within 300 seconds after that role is removed; in both cases the application's rows referring to the account are unchanged, and after the account is enabled again (and the role restored) a new login reaches the same records. |
| ADR-0003-C8 | No response body or non-`HttpOnly` cookie sent to the browser contains an access, refresh or ID token; the session cookie is `HttpOnly`, `Secure` and `SameSite=Strict`; a state-changing request with a foreign `Origin` header is refused. |
| ADR-0003-C9 | The OpenAPI document contains no operation whose request body has a property named `password`, `username` or `grant_type`, and no route sends e-mail. |
| ADR-0003-C10 | Against a running Keycloak with a mail-catching SMTP server: a reset request for an existing address and one for an unknown address return pages with the same text and status; exactly one message reaches the catcher, for the existing address; for a disabled account, login is still refused after the reset. |
| ADR-0003-C11 | On the PostgreSQL server, the application's database role cannot connect to Keycloak's database and Keycloak's role cannot connect to the application's. |
| ADR-0003-C12 | `bash scripts/layer-check.sh origin/main HEAD` exits 0 with an `auth` row whose "Must not depend on" lists `services`, `api`, `integrations`, with `auth` listed under "Must not depend on" in the rows `domain`, `services`, `data`, `core` and `integrations`, and not in the row `api`; `grep -rli -e jwt -e jose -e id_token -e access_token backend/app/services backend/app/domain` returns nothing. |
| ADR-0003-C13 | After `alembic upgrade head`, no column in the application schema is named or holds a staff e-mail address, username or password; staff are referenced by the subject identifier. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->
