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
in EKO-2 fits the architecture until this is decided. The administrator's permissions in Keycloak,
the network exposure of Keycloak's pages, the hand-over of temporary passwords and who may change a
staff member's name follow the human's decisions of 2026-10-23 on the verification findings of
EKO-1-02.

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
secrets) never appear in that export (secret handling: ADR-0004). The export holds **no staff
account**: it has no `users` entries and no separate user files, so no username, e-mail address,
password hash or one-time-password secret of a staff member is in the repository. Every
secret-bearing field in it (client secrets, the SMTP password) is absent or an environment
placeholder replaced at import, never the mask string Keycloak writes in place of a secret.

### Identity server storage

Keycloak stores its data in **its own database on the same PostgreSQL 18 server** as the
application database (ADR-0002), under its own database role. Keycloak shares the application's
PostgreSQL server; it does not share the application's database. The application's database role
has no privilege on Keycloak's database and Keycloak's role none on the application's. Keycloak
never runs on its embedded development database outside a developer's machine. ADR-0002's collation and
schema rules (ICU `pl-PL`, Alembic, the controls ADR-0002-C1 to C15) govern the application
database only; Keycloak manages its own schema. Both databases are covered by the same backup and
restore (ADR-0004).

Keycloak cannot use up the shared server's connections: Keycloak's database role and the
application's database role each carry a connection limit (`CONNECTION LIMIT`), Keycloak's
connection pool maximum (`db-pool-max-size`) is set no higher than its role's limit, the
application's connections at their most (backend workers × (pool size + overflow), plus background
jobs, plus a migration run) stay within its role's limit, and the two
limits together stay below `max_connections` minus the connections reserved for superusers. The
values are set by the walking skeleton (EKO-1-06) within the composition decided by ADR-0004.

### Browser flow: backend session, no token in the browser

The browser flow is a **backend session**: the backend is the only OpenID Connect client the
browser deals with (a backend-for-frontend), and the single-page application holds no token.

- Login and password reset happen only on Keycloak's pages. Login is the authorization code flow
  with PKCE between the backend (a confidential client) and Keycloak. The user types the password **only on Keycloak's pages**; no backend endpoint receives
  it (ADR-0001-C6). The direct-access (resource-owner password) grant is disabled on every client
  of the realm.
- The tokens Keycloak issues are held **server-side** by the backend, in the application database
  (through the `data` layer, ADR-0002), encrypted with a key read through
  `backend/app/core/settings.py` (key handling: ADR-0004). When logged in, the browser holds only an
  opaque, random session identifier in a cookie named with the `__Host-` prefix and marked
  `HttpOnly`, `Secure` and `SameSite=Strict`
  (and, between the start of a login and its callback, the login-transaction cookie below); the
  database stores only a hash of that identifier. No access, refresh or ID token is ever returned to
  the single-page application or readable by its JavaScript.
- **Login transaction.** Starting a login creates a login transaction (the OIDC `state`, the
  `nonce` and the PKCE verifier) stored server-side and bound to the browser by a separate cookie
  named with the `__Host-` prefix and marked `HttpOnly`, `Secure` and `SameSite=Lax`, valid for at most 10 minutes and holding only a
  random transaction identifier. `Lax` is required because the callback from Keycloak is a top-level
  navigation that is cross-site whenever Keycloak's pages are on another site (ADR-0004). The
  callback is refused, and creates no session, unless it arrives with that cookie and a `state`
  equal to the transaction's; the transaction and its cookie are deleted at the callback, whether it
  succeeds or is refused.
- **New identifier at login.** A successful login always creates a new session with a new random
  identifier. A session identifier the browser presented before the login is never reused, and the
  earlier session it names, if any, is deleted.
- A session whose cookie the browser no longer presents (a lost cookie, another browser) stays in
  the table until the retention rule of ADR-0005 deletes it; that rule must delete it, with its
  encrypted tokens, no later than the realm's SSO session maximum lifespan after it was created.
- A state-changing request (any method other than `GET`, `HEAD`, `OPTIONS`) is refused unless its
  `Origin` header equals the application's own origin. The login callback is a `GET` and is
  protected by the login transaction above.
- The single-page application and the API are served from **one origin** (forwarded to ADR-0004 as
  a constraint on composition and HTTPS exposure).
- Tokens issued to the application carry the subject, the given and family name and the roles, and
  **no e-mail address and no username**: neither the `email` nor the `profile` client scope is
  assigned to the application's client, and the name claims come from mappers on that client that
  emit only `given_name`, `family_name` and `name` (the subject through Keycloak's `basic` scope
  where the version has one).

### How a request is verified, and the 5-minute bound

On every request, one application-wide FastAPI dependency (ADR-0001, Constraint 2) resolves the
session cookie to its stored session and verifies the access token held for it: signature against
the realm's published keys, issuer, audience (the application's client) and expiry. A request
without a session, or whose session cannot be resolved or verified, gets HTTP 401. When the access
token has expired, the backend renews it with the stored refresh token. Renewal is **serialised per
session** across every backend process: at most one refresh for a session is in flight, a
concurrent request on the same session waits for it and uses the tokens it stored, and no request
sends a refresh token that another request has replaced. The refresh call to Keycloak times out
after at most 5 seconds, and a request waits for another request's refresh at most 5 seconds; when
that refresh fails or the wait runs out, the waiting request answers 503 at once and does not
refresh itself. The per-session lock holds no database transaction open across the call to
Keycloak. Refresh-token rotation is on in the realm
(`revokeRefreshToken` true, `refreshTokenMaxReuse` 0), so each refresh token is used once.

- **Refused.** If Keycloak refuses the refresh with an OAuth error (such as `invalid_grant`:
  account disabled, Keycloak session ended, token revoked), the session is deleted and the request
  gets 401.
- **Unreachable.** If Keycloak cannot be reached, times out or answers with a server error, the
  session is kept, the request is not served and gets HTTP 503, and a later request tries the
  refresh again. The single-page application treats 503 as "try again", not as a logout. No request
  is served on an expired access token, so the bound below holds while Keycloak is down. A refresh
  that times out may already have been carried out by Keycloak, which has then replaced the refresh
  token the backend still holds; the next refresh with it is refused and the session is deleted as
  under *Refused*. This decision accepts that logout (`refreshTokenMaxReuse` stays 0): the user
  logs in again, and the request answered 401 is not carried out.

**Bound (at most 5 minutes).**

- After an administrator deactivates an account, a session already issued for that account stops
  being accepted within at most 5 minutes.
- After an administrator removes one role from an account that stays active, a session already
  issued for that account stops being granted that role within at most 5 minutes.

The mechanism is the access-token lifespan: the realm's access-token lifespan plus the backend's
clock-skew leeway plus the largest clock offset allowed between the backend's and Keycloak's clocks
is at most 300 seconds, and a new access token is obtained only through a Keycloak refresh, which
Keycloak refuses for a disabled account and builds from the roles held at that moment. The backend
and Keycloak read time from synchronised clocks: the same host clock, or hosts kept in step by NTP
within that allowed offset (placement: ADR-0004); an offset larger than the allowance breaks the
bound and is a defect. No per-request call to Keycloak is made. Every other session and idle
timeout value is decided by EKO-2-01 and does not relax this bound.

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
  The administrator manages accounts in Keycloak's administration console of the application realm,
  not through the application, with the user-management permissions set out under *Administrator
  permissions in Keycloak* below. The rule binds the role and is checked per token: a person whose
  account holds `administrator` and also `manager` (assigned by anyone, including by themselves, as
  brief section 2 allows) has manager rights, and every such assignment is a stored admin event.
- **An authenticated account with none of the three roles is denied every API operation** (HTTP
  403). No role is assumed by default: the rights of `rep` require the `rep` role in the claim.
- The identity of the caller passed inward from the access dependency is a value defined in the
  `domain` layer (the subject identifier and the set of roles). `auth` builds it; `services` and
  `domain` receive it and never read a token, a claim or the session.

### Administrator permissions in Keycloak

- The client role `administrator` is a composite role whose composites are exactly these client
  roles of the realm's `realm-management` client, and not any other: `manage-users`, `view-users`,
  `query-users`, `query-groups`, `query-clients`. With them a holder of `administrator` manages
  accounts: creates, disables and enables them, assigns and unassigns the application's roles
  (including on their own account, brief section 2) and sets temporary passwords.
- Excluded from the role, and held by no account or group of the application realm: `realm-admin`,
  `impersonation`, `manage-realm`, `manage-clients`, `manage-events`, `manage-identity-providers`,
  `manage-authorization`, `create-client`, `view-realm`, `view-clients`, `view-events`,
  `view-identity-providers`, `view-authorization`. A holder of `administrator` therefore cannot
  impersonate anyone, change realm or client settings (grants, token lifespans, identity providers,
  client secrets), or view, alter or switch off the admin events below.
- If EKO-1-06 finds that Keycloak's console cannot assign the application's client roles with this
  set, that task stops and any additional role returns to the human as an addendum to this
  decision; `realm-admin`, `impersonation`, `manage-realm` and `manage-clients` are never added.
- Keycloak runs with its impersonation feature disabled, so no account in any realm, the master
  realm included, can impersonate a user.
- Keycloak refuses to let an account grant a `realm-management` role it does not hold itself, but
  holding `manage-users` lets it give any account the ones it holds (those of the composite). This
  decision forbids giving a `realm-management` role to any account other than through the
  `administrator` composite. Keycloak does not prevent that mechanically; every such mapping is a
  stored admin event, and ADR-0003-C22 finds an account holding one. ADR-0003-C16 proves only the
  refusal of the roles outside the composite; if it fails, the task running it stops and returns
  to the human.
- **Admin events are stored.** The realm stores admin events with their representation
  (`adminEventsEnabled` and `adminEventsDetailsEnabled` true). Every creation, update, enabling,
  disabling and deletion of an account, every password set by an administrator, and every
  role-mapping change (a role assigned or unassigned, for any account including the actor's own)
  is a stored admin event naming the acting account and the time. Their retention is decided by
  ADR-0005, which may not set it to zero; they are read by the operator (ADR-0004), not through the
  `administrator` role.
- A password an administrator sets is always temporary (the "update password" required action is
  set), for a new account and for a reset alike; the hand-over rule under *Password reset* applies.
- Because the role assigns roles and sets passwords, a person holding it is able to reach CRM data
  by giving their own account `manager` or `rep`, or by setting a user's temporary password and
  logging in first. This decision does not prevent either mechanically; it makes each one a stored
  admin event, and the user whose password was set sees the change at their next login.

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
  mechanically, but every deletion is a stored admin event; the consequence of breaking the rule is
  that the records keep a subject no account holds, and an account created again for the same
  person gets a new subject with no access to them.
- **Reactivation.** Enabling a disabled account restores access to the same records, because its
  subject identifier is unchanged.
- **Role removal** takes effect within the same bound of at most 5 minutes and changes no data.
- **Names.** Staff do not change their own first or last name; only an administrator changes it,
  in Keycloak's console, as a stored admin event. In the realm's user profile `firstName` and
  `lastName` are editable by `admin` only, and the realm's default roles do not include the
  `account` client's `manage-account` or `view-profile` role, so Keycloak's account console is not
  usable by staff and is not exposed (*Network exposure*).
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
  required action, so the user replaces it at the next login on Keycloak's pages. The temporary
  password is handed over in person or in a phone call, never written in an e-mail, a messenger or
  any other written message, and it is set only right before the user logs in. For a reset, the
  administrator hands it over only in person or in a call the administrator makes to a phone number
  the company already holds for that person, never to an incoming caller. An account whose
  temporary password is still unused 7 days after it was set (the "update password" required action
  still pending) is disabled by the administrator. Developer and test environments point Keycloak
  at a local mail-catching container that delivers nothing outside the composition. No personal or
  third-party mailbox (including Gmail) is used as a stand-in.

### Accounts never depend on Google

No identity provider (Google or any other) is configured in the realm, and Keycloak's identity
brokering is not used: no one signs in, and no account is created, through an external provider.
Login works with no Google account linked. Linking a Google account for the calendar (ADR-0006)
creates, authenticates and alters no account, and is not done through Keycloak's brokering.

### Network exposure (constraint on ADR-0004)

Keycloak's login, password-reset and required-action pages are reachable from the internet. Its
administration console, and the admin REST API behind it, for every realm including the master
realm, are reachable only from the company network; its account console is reachable from
neither. ADR-0004 decides the placement, hostnames and
HTTPS that realise this; this decision fixes only who may reach which pages. Brute-force detection
is a precondition of that exposure: it is on in the realm (`bruteForceProtected` true) before the
login page of any shared environment is reachable from the internet. Its thresholds are decided
with the password policy (EKO-1-06 / EKO-2-01).

### Staff personal data

| Held by | Staff personal data |
|---|---|
| Keycloak | username, e-mail address, first and last name, password hash, role assignments, enabled state, active sessions (including their IP address and times); admin events with their representation (acting account, the account changed, its fields, role mappings and credential changes, times); login events only if their storage is turned on (ADR-0005) |
| Application | the subject identifier, in every record that refers to a staff member; a copy of the display name (given and family name) taken from the verified token at each login, kept after deactivation so attribution of past records stays readable; server-side sessions (hashed session identifier, subject, encrypted tokens carrying only the claims named under Browser flow, created and last-used instants); short-lived login transactions holding no personal data |

The application holds no staff e-mail address, username or password, neither in a column nor
inside a stored token. Retention of sessions, Keycloak events and the display-name copy, and what
may appear in logs, are decided by ADR-0005. How names are rendered is decided by the tasks that
display them.

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

- ADR-0004 (#16) — one origin for the SPA and the API; placement, hostnames and HTTPS of Keycloak's
  internet-facing pages and of its administration console (company network only), under the
  exposure constraint above, including the timing of the reset response for known and unknown
  addresses on an internet-facing page; time synchronisation of the backend's and Keycloak's hosts
  within the allowed clock offset; the connection-limit values; the session-encryption key, client
  secrets and SMTP credentials; who reads admin events; backup of Keycloak's database; bootstrap of
  the first administrator and recovery when none remains.
- ADR-0005 (#17) — retention of sessions (abandoned ones within the limit above), Keycloak admin
  events (never zero) and login events, and the display-name copy; logging.
- ADR-0006 (#18) — Google account linking, outside Keycloak.
- EKO-2-01 — session and idle timeout values other than the 5-minute bound; language, branding
  and wording of Keycloak's pages; logout.
- EKO-1-06 / EKO-2-01 — password policy, MFA, brute-force thresholds (the protection itself is on,
  above).

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

### Binding the login callback to the browser

| Option | Cost | Closes off |
|---|---|---|
| **A. Short-lived `SameSite=Lax` login-transaction cookie, new session identifier at login** (chosen) | A second cookie during login. Works wherever ADR-0004 places Keycloak's pages. | Nothing. |
| B. The `Strict` session cookie only, with Keycloak's pages on the application's site | Login fails whenever Keycloak's pages are on another site. | Placing Keycloak on its own domain. |
| C. Login transaction kept server-side without a browser binding | Login CSRF: a colleague's browser can end up logged in as another account, and entries are stored under that account's subject. | Nothing; rejected. |

### Meeting the 5-minute bound

| Option | Cost | Closes off |
|---|---|---|
| **A. Access-token lifespan plus leeway plus allowed clock offset ≤ 300 s, renewed only through Keycloak** (chosen) | One refresh call to Keycloak per active session at most every 5 minutes; while Keycloak is unreachable, requests on a session whose access token has expired get 503. | Long-lived access tokens. |
| B. Token introspection on every request | A Keycloak call on every API request; Keycloak's availability and latency become the API's. | Local verification; an API that answers while Keycloak is briefly down. |
| C. Back-channel logout or admin-event push to the backend | Covers deactivation only if Keycloak's event delivery is reliable; role removal is not a logout event. | Nothing, but does not meet the bound alone. |

### Renewal: concurrency and Keycloak outages

| Option | Cost | Closes off |
|---|---|---|
| **A. Rotation on, refresh serialised per session; refused means 401 and the session deleted, unreachable means 503 and the session kept** (chosen) | A per-session lock shared by every backend process; the SPA handles 503 as a retry; a refresh that times out after Keycloak rotated the token ends the session. | Nothing. |
| B. Rotation off, refresh not serialised | A stolen refresh token stays usable for the whole Keycloak session; concurrent refreshes race and the last write wins. | Detecting a reused refresh token. |
| C. 401 both when Keycloak refuses and when it is unreachable | Every Keycloak restart logs out the users whose access token expires during it. | Riding out a Keycloak restart. |

### Administrator's permissions in Keycloak

| Option | Cost | Closes off |
|---|---|---|
| **A. User-management roles only, impersonation feature off, admin events stored** (chosen) | A holder of the role can still reach CRM data by giving their own account a role or by setting a user's temporary password, visible after the fact in admin events, and can give another account the composite's `realm-management` roles, found by ADR-0003-C22; console role assignment may need one more read-only role (gate in EKO-1-06). | Delegating realm or client configuration to the role. |
| B. `realm-admin` for the role | Simplest to configure; brings impersonation and realm and client settings, so the live realm can drift from the export and CRM data can be reached under any user's identity. | Separating account management from realm configuration. |
| C. Account management through the application, with the backend calling Keycloak's admin API | An administrative credential to Keycloak in the backend and an admin surface in the API. | Keycloak's console as the only admin tool. |

### Identity server storage

| Option | Cost | Closes off |
|---|---|---|
| **A. Own database on the shared PostgreSQL 18 server, per-role connection limits** (chosen) | Shared failure domain and resources; a PostgreSQL major upgrade must be supported by both Keycloak and the application. | Upgrading PostgreSQL for one of them alone. |
| B. A second PostgreSQL container for Keycloak | A second database server to operate, back up and restore (ADR-0004), for about ten users. | Nothing. |
| C. Keycloak's embedded development database | Not supported by Keycloak for production use. | Rejected. |

### Identifier the application stores

| Option | Cost | Closes off |
|---|---|---|
| **A. Keycloak subject identifier (`sub`)** (chosen) | Opaque; a person recreated as a new account is a new subject. | Joining application records to a person by e-mail or username. |
| B. Username | Changeable in Keycloak; case questions. | Renaming a username without breaking records. |
| C. E-mail address | Changeable; case variants; puts staff e-mail into every referring record. | Same as B, and a minimal staff-data footprint. |

### Claims in the application's tokens

| Option | Cost | Closes off |
|---|---|---|
| **A. No `email` or `profile` scope; name mappers on the client** (chosen) | Mappers kept in the realm export. | Using the username anywhere in the application. |
| B. Default `profile` scope, the username listed as held inside stored tokens | The username in every session row, under ADR-0005's retention. | A minimal staff-data footprint. |

### Staff display name

| Option | Cost | Closes off |
|---|---|---|
| **A. Copy of the display name from the verified token at each login** (chosen) | A name changed in Keycloak shows in the application only after that person's next login. | Nothing. |
| B. Subject identifier only; names read from Keycloak's admin API by the backend | The backend holds an administrative credential to Keycloak and depends on it to render any attribution. | Rendering attribution while Keycloak is down. |

### Reset e-mail before the company mailbox exists

| Option | Cost | Closes off |
|---|---|---|
| **A. Reset e-mail off; administrator sets a temporary password with a required change, handed over in person or by phone, unused after 7 days means disabled; local mail catcher in developer and test environments** (chosen) | The administrator knows a temporary password until the user's next login; self-service reset waits for the mailbox. | Self-service reset before the mailbox exists. |
| B. A personal or third-party mailbox as a stand-in | Credentials of an account the company does not control; a Gmail mailbox makes reset depend on Google. | Accounts independent of Google, in spirit. |
| C. No shared environment until the mailbox exists | Blocks the pilot on the company. | Starting the pilot early. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0003-C1 | The realm export under `identity/` has `registrationAllowed` false, `bruteForceProtected` true, an empty `identityProviders` list, `directAccessGrantsEnabled` false on every client, the application's client confidential with PKCE required, `revokeRefreshToken` true with `refreshTokenMaxReuse` 0, neither the `email` nor the `profile` client scope assigned to the application's client, and no protocol mapper on that client emitting `email` or `preferred_username`; its user profile makes `firstName` and `lastName` editable by `admin` only, and its default roles include neither the `account` client's `manage-account` nor its `view-profile` role. |
| ADR-0003-C2 | The realm export's `accessTokenLifespan` plus the backend's configured clock-skew leeway plus its configured maximum clock offset is at most 300 seconds, and the deployment (ADR-0004) keeps the backend's and Keycloak's clocks within that offset. |
| ADR-0003-C3 | Every reference to the Keycloak image in the repository names a full `<major>.<minor>.<patch>` tag or carries `@sha256:`. |
| ADR-0003-C4 | A test walking every API route: with no session cookie, or a session whose token has a wrong signature, issuer or audience, or whose expired token Keycloak refuses to renew, each route answers 401, and a session whose renewal was refused is deleted; with an expired token and Keycloak unreachable, each route answers 503 and the session is kept. |
| ADR-0003-C5 | A test walking every API route with a verified token holding none of `rep`, `manager`, `administrator` (including one holding realm roles with those names) gets 403 on each route; with only `administrator` it gets 403 on every route reading or changing customers, visits, notes, actions or dashboards; with `manager` and `administrator` it gets the same answers as with `manager` alone. |
| ADR-0003-C6 | A test with a `rep` token adding a header, query parameter or body field naming the role `manager` gets the same answer as without it. |
| ADR-0003-C7 | Against a running Keycloak: a session accepted for an active account is refused (401) within 300 seconds after the account is disabled; a session of an account holding `manager` loses manager rights within 300 seconds after that role is removed; in both cases the application's rows referring to the account are unchanged, and after the account is enabled again (and the role restored) a new login reaches the same records. |
| ADR-0003-C8 | No response body or non-`HttpOnly` cookie sent to the browser contains an access, refresh or ID token; the session cookie is `HttpOnly`, `Secure` and `SameSite=Strict`; both cookies' names start with `__Host-`; the only other cookie the backend sets is the login-transaction cookie, `HttpOnly`, `Secure`, `SameSite=Lax`, valid for at most 10 minutes and cleared at the callback; a callback without that cookie or with a `state` that does not match its transaction is refused and creates no session; the session identifier after a login differs from any the browser presented before it; a state-changing request with a foreign `Origin` header is refused. |
| ADR-0003-C9 | The OpenAPI document contains no operation whose request body has a property named `password`, `username` or `grant_type`, and no route sends e-mail. |
| ADR-0003-C10 | Against a running Keycloak with a mail-catching SMTP server: a reset request for an existing address and one for an unknown address return pages with the same text and status; exactly one message reaches the catcher, for the existing address; for a disabled account, login is still refused after the reset. |
| ADR-0003-C11 | On the PostgreSQL server, the application's database role cannot connect to Keycloak's database and Keycloak's role cannot connect to the application's. |
| ADR-0003-C12 | `bash scripts/layer-check.sh origin/main HEAD` exits 0 with an `auth` row whose "Must not depend on" lists `services`, `api`, `integrations`, with `auth` listed under "Must not depend on" in the rows `domain`, `services`, `data`, `core` and `integrations`, and not in the row `api`; `grep -rli -e jwt -e jose -e id_token -e access_token backend/app/services backend/app/domain` returns nothing. |
| ADR-0003-C13 | After `alembic upgrade head`, no column in the application schema is named or holds a staff e-mail address, username or password; staff are referenced by the subject identifier. |
| ADR-0003-C14 | The realm export under `identity/` has no `users` entries and no file holding users, and every client secret field and the SMTP password field in it is absent or an environment placeholder, never the mask string. |
| ADR-0003-C15 | In the realm export, the application's client role `administrator` is a composite whose composites are exactly the `realm-management` client roles `manage-users`, `view-users`, `query-users`, `query-groups` and `query-clients`, and not `realm-admin`, `impersonation`, `manage-realm`, `manage-clients`, `manage-events`, `manage-identity-providers`, `manage-authorization`, `create-client`, `view-realm`, `view-clients`, `view-events`, `view-identity-providers` or `view-authorization`; no group and no other role in the export includes a `realm-management` role. |
| ADR-0003-C16 | Against a running Keycloak started as the repository configures it, with the impersonation feature disabled: an account holding only `administrator` creates, disables and enables an account, sets a temporary password and assigns the application's roles, including to itself; the same account is denied each of impersonating a user, changing a realm or client setting, viewing or changing admin events, and giving any account a `realm-management` role outside the composite (at least `realm-admin`, `manage-realm`, `manage-clients`, `impersonation` and `view-events`). |
| ADR-0003-C17 | The realm export has `adminEventsEnabled` and `adminEventsDetailsEnabled` true; against a running Keycloak, creating an account, changing it, disabling and enabling it, setting its password, deleting a test account, and assigning or unassigning one of the application's roles each leave a stored admin event with its representation and the acting account, and no stored representation holds a password value. |
| ADR-0003-C18 | A test sending at least ten concurrent requests on one session whose access token has expired: every request is answered as authenticated, Keycloak receives exactly one refresh request for that session, and the session still exists afterwards; with Keycloak accepting the connection but never answering, every one of them gets 503 within 6 seconds of being sent and Keycloak receives exactly one refresh request. |
| ADR-0003-C19 | On the PostgreSQL server, Keycloak's database role and the application's database role each have a connection limit greater than zero, Keycloak's configured `db-pool-max-size` does not exceed its role's limit, the backend's configured workers × (pool size + max overflow) plus the background jobs' pools plus one migration connection does not exceed the application role's limit, and the two limits together are below `max_connections` minus `superuser_reserved_connections`. |
| ADR-0003-C20 | After a test login against a running Keycloak, the access, refresh and ID tokens stored for the session, once decrypted, carry no `email` and no `preferred_username` claim. |
| ADR-0003-C21 | By review of stored admin events and account state in each shared environment before the company mailbox exists: no enabled account still carries the "update password" required action more than 7 days after the admin event that set its temporary password. |
| ADR-0003-C22 | By review of the live application realm in each shared environment: no account and no group has a `realm-management` role in its own role mappings; such roles are held only through the `administrator` composite. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->

### 2026-10-24 — The connection budget of ADR-0003-C19 includes the backup database role

**What it restates.** The connection budget of *Identity server storage* and of ADR-0003-C19 sums
two database roles: "the two limits together" of Keycloak's role and the application's role stay
below `max_connections` minus `superuser_reserved_connections`. ADR-0004 adds a third role that
connects to the same PostgreSQL server: the `backup` role, which runs `pg_dump` against both
databases. From this date the budget reads: Keycloak's database role, the application's database
role and the backup database role each have a connection limit greater than zero, and **the three
limits together** are below `max_connections` minus `superuser_reserved_connections`. Every other
clause of ADR-0003-C19 is unchanged. ADR-0004-C19 checks the three-role sum.

**Why.** Kept outside the sum, the backup role's connections would leave ADR-0003-C19 true in
letter while its guarantee — that no role can use up the shared server's connections — is gone.
ADR-0004 (deployment and backup) cannot meet the two-role sum as written, so the restatement is a
declared deviation, approved by the human at gate 1 of EKO-1-03 on 2026-10-24 (G-10 A, Issue #16).

### 2026-10-28 — Forwards to EKO-1-06 reassigned after its split

**What it restates.** EKO-1-06 (#19) was split into EKO-1-06 and EKO-1-10..EKO-1-15 (#51..#56).
This addendum changes only which task receives a duty this decision names. No rule, stop rule or
control changes. From this date:

- *Identity server product*: the walking skeleton, EKO-1-06 (#19), still chooses the Keycloak
  version first used, and it still stops when no release lists PostgreSQL 18. This is unchanged.
- *Identity server storage*: EKO-1-06 (#19) still sets the connection-limit values. This is
  unchanged.
- *Administrator permissions in Keycloak*, the console-role stop rule ("If EKO-1-06 finds that
  Keycloak's console cannot assign the application's client roles with this set, that task
  stops"): the task that makes this finding, and that stops, is **EKO-1-12 (#53)**. The rule is
  otherwise unchanged: any additional role returns to the human as an addendum to this decision,
  and `realm-admin`, `impersonation`, `manage-realm` and `manage-clients` are never added. The
  same applies to "gate in EKO-1-06" in the *Administrator's permissions in Keycloak* options
  table.
- *Network exposure* and *Forward references*, "EKO-1-06 / EKO-2-01 — password policy, MFA,
  brute-force thresholds": the receiving task is **EKO-2-01 (#21)**. Until EKO-2-01 sets the
  thresholds, EKO-1-12 (#53) keeps brute-force detection on (`bruteForceProtected` true) with
  provisional values. The precondition that detection is on before any login page of a shared
  environment is reachable from the internet is unchanged.

**Why.** Each of these passages names EKO-1-06. Left unchanged, the stop rule of *Administrator
permissions in Keycloak* would bind a task that no longer runs the console check, and the task
that does run it would find no rule naming it. Approved by the human at gate 1 of EKO-1-06 on
2026-10-28 (G-5 B, Issue #19). This is not a deviation: no rule changes.

### 2026-10-28 — Routes served without a session; the OpenAPI document in shared environments

**What it adds.** *How a request is verified* says that a request without a session, or whose
session cannot be resolved or verified, gets HTTP 401. ADR-0003-C4 tests that on every API route.
The decision implies two exceptions, the start of a login and its callback, but it names none, and
the walking skeleton (EKO-1-06, #19) adds a health route. From this date:

- **Exactly three routes are served without a session:** the route that starts a login, the login
  callback (still protected by the login transaction under *Browser flow*), and the health route.
  The access dependency exempts these three and no other route. Adding a route to this list is a
  change to this decision, recorded as an addendum.
- **The health route answers status only.** It is a readiness check: it answers success only when
  the backend can reach the application database, and failure otherwise. Its response holds the
  status and nothing else: no version, Alembic revision, host name, dependency name, error text,
  configuration value, personal data or secret. It accepts only `GET` and `HEAD`.
- **The OpenAPI document is not served through `proxy` in shared environments.** In the
  shared-environment profile, neither listener of `proxy` forwards a request for the backend's
  OpenAPI document or for FastAPI's documentation pages. They are reachable only inside the
  composition's network. ADR-0001-C7's test fetches the document from the backend directly,
  never through `proxy`, and so does any check that compares it between releases. The
  development profile may serve it through `proxy`.
- **ADR-0003-C4 reads:** a test walking every API route other than the start of a login, the login
  callback and the health route — this exemption list is held in the test explicitly — makes the
  checks below, and the test fails when a route outside that list answers a request without a
  session cookie with anything other than 401:
  - with no session cookie, or with a session whose token has a wrong signature, issuer or
    audience, or whose expired token Keycloak refuses to renew, each route answers 401, and a
    session whose renewal was refused is deleted;
  - with an expired token and Keycloak unreachable, each route answers 503 and the session is
    kept.
- **New control ADR-0003-C23:** without a session cookie, the health route answers success with a
  body holding only its status while the application database is reachable, and a failure status
  from `backend` while it is not. Through either listener of `proxy` in the shared-environment
  profile, a request for the backend's OpenAPI document or its documentation pages gets no
  OpenAPI content. The access dependency's exemption list holds exactly the start of a login, the
  login callback and the health route.

Every other rule and control of this decision is unchanged.

**Why.** The single-entry-point composition (ADR-0004) routes the health check through `proxy`,
and in shared environments `proxy` is reachable from the internet. Without a closed exemption
list, ADR-0003-C4 would fail on the health route the moment the access dependency exists, and each
later exemption would be decided in code instead of here. A health response that names versions
or errors, or an OpenAPI document served to the internet, would describe the system to anyone who
asks, with no login. Restating ADR-0003-C4 is a declared deviation, approved by the human at gate
1 of EKO-1-06 on 2026-10-28 (G-7 A, Issue #19).

### 2026-10-28 — Keycloak version first used

**What it records.** *Identity server product* has the walking skeleton (EKO-1-06, #19) choose the
Keycloak version first used, among releases whose documentation lists PostgreSQL 18 as a supported
database, and record it here. EKO-1-06 first uses **`quay.io/keycloak/keycloak:26.8.1`**, the
`image:` of the `keycloak` service in `compose.yaml`, a full `<major>.<minor>.<patch>` tag as
ADR-0003-C3 requires.

- **Source.** Keycloak's database guide, https://www.keycloak.org/server/db, read 2026-10-28 with
  26.8.1 shown as the current release. Its table of supported databases lists PostgreSQL with
  tested version 18 and supported versions 18.x, 17.x, 16.x, 15.x and 14.x.
- **The page is not version-pinned.** It tracks the latest release, and no version-pinned URL of it
  was found. The human keeps a capture of the page as read on 2026-10-28; that capture, not the
  live page, is the evidence for this choice.
- The stop rule of *Identity server product* ("If no such release exists when EKO-1-06 runs, that
  task stops") did not apply.

From this version on, every image change that crosses a major version is recorded as an addendum to
this decision (*Identity server product*). How a release references this image by digest is
recorded in ADR-0004's addendum of 2026-10-28 on *Images*.

No rule or control of this decision changes.

**Why.** *Identity server product* requires the version first used, and the documentation that
shows it supports PostgreSQL 18, to be recorded here. Approved by the human at gate 2 of EKO-1-06
on 2026-10-28 (Issue #19, PR #57). This is not a deviation.

### 2026-10-28 — Connection-limit values of ADR-0003-C19

**What it records.** *Identity server storage* has the walking skeleton (EKO-1-06, #19) set the
connection-limit values within the composition decided by ADR-0004, under the three-role budget of
this decision's addendum of 2026-10-24. EKO-1-06 sets these values. They are the same in every
environment and part of the release (ADR-0004's addendum of 2026-10-28 on initialising PostgreSQL):

| Value | Set to | Where |
|---|---|---|
| `max_connections` | 100 | the `postgres` command in `compose.yaml` |
| `superuser_reserved_connections` | 3 | the `postgres` command in `compose.yaml` |
| Application role `eko_app`, `CONNECTION LIMIT` | 30 | the init content in `compose.yaml` |
| Keycloak's role `eko_keycloak`, `CONNECTION LIMIT` | 25 | the init content in `compose.yaml` |
| Backup role `eko_backup`, `CONNECTION LIMIT` | 5 | the init content in `compose.yaml` |
| Keycloak `db-pool-max-size` | 20 | `KC_DB_POOL_MAX_SIZE` of `keycloak` in `compose.yaml` |
| `backend` | 2 workers (`WEB_CONCURRENCY`), each pool size 5 and max overflow 5 | `compose.yaml` |
| `worker` | pool size 2, max overflow 0 | `compose.yaml` |
| `migrate` | pool size 1, max overflow 0 | `compose.yaml` |

The budget these values meet:

- Keycloak's pool maximum, 20, does not exceed its role's limit, 25.
- The application's connections at their most are 2 × (5 + 5) for `backend`, plus 2 for `worker`,
  plus 1 for `migrate`, which is 23. This does not exceed the application role's limit, 30.
- The three role limits together, 30 + 25 + 5 = 60, are below `max_connections` minus
  `superuser_reserved_connections`, 100 − 3 = 97.

That the backup role's limit of 5 covers the sessions a backup holds, and that a nightly run under
it completes (ADR-0004-C19), is shown by EKO-1-14 (#55), as ADR-0004's addendum of 2026-10-28 on
the split of EKO-1-06 says.

No rule or control of this decision changes. A later change to any of these values keeps the
budget of ADR-0003-C19 and of the addendum of 2026-10-24.

**Why.** *Identity server storage* forwards the values to EKO-1-06, and ADR-0003-C19 can be checked
only against values recorded somewhere. Approved by the human at gate 2 of EKO-1-06 on 2026-10-28
(Issue #19, PR #57). This is not a deviation.

### 2026-10-29 — ADR-0003-C9 restated: any media type, any case, and request parameters

**Status:** Accepted 2026-10-29, as a declared deviation (gate 1 of EKO-1-10, Issue #51).

**What it restates.** EKO-1-10 (#51) builds ADR-0003-C9 as a check on the OpenAPI document the
application generates. Its letter reads only request-body properties "named" `password`,
`username` or `grant_type`. The flow this decision forbids, the resource-owner password grant,
arrives as an `application/x-www-form-urlencoded` body, and FastAPI places that body's schema
behind a `$ref`. *Browser flow* also says that no backend endpoint receives the password, and it
names no channel. From this date:

- **ADR-0003-C9 reads:** The OpenAPI document contains no operation with a request-body property
  named `username` or `grant_type`, or whose name contains `password`. Names are compared without
  regard to case. This covers any media type of the body, any depth, and a property reached
  through a `$ref`. The document also contains no operation with a query, header, cookie
  or path parameter named in the same way. No route sends e-mail.

Every other rule and control of this decision is unchanged. ADR-0001's addendum of 2026-10-29
restates ADR-0001-C6 in the same way.

**Why.** A check built to the letter of ADR-0003-C9 would pass the password grant in exactly the
shape it takes, a form body behind a `$ref`. It would also pass a credential sent in a
URL, which ends up in logs. Restating an accepted control is a declared deviation. It follows the
precedent of this decision's addendum of 2026-10-28 on ADR-0003-C4. Approved by the human at
gate 1 of EKO-1-10 on 2026-10-29 (G-4 A, Issue #51).

### 2026-11-04 — Application administrator: read-only client selection for application-role assignment

**Status:** Accepted 2026-11-04 (repeated gate 1 of EKO-1-12, Issue #53; option A accepted by the human in the driving session, recorded on the Issue).

**What it changes.** On acceptance, *Administrator permissions in Keycloak* and ADR-0003-C15 are
amended as a declared deviation so that the application client role `administrator` is a composite
whose composites are exactly these six client roles of the application realm's `realm-management`
client, and not any other: `manage-users`, `view-users`, `query-users`, `query-groups`,
`query-clients`, and `view-clients`. The sole addition is the read-only `view-clients` role, so the
administrator can select a client and resolve its identifier when assigning or unassigning the
application's roles.

`view-clients` is removed from the exclusions only to the extent that it is held through the
`administrator` composite. Every other excluded role remains forbidden: `realm-admin`,
`impersonation`, `manage-realm`, `manage-clients`, `manage-events`, `manage-identity-providers`,
`manage-authorization`, `create-client`, `view-realm`, `view-events`, `view-identity-providers`,
and `view-authorization` remain excluded from `administrator` and held by no account or group of
the application realm. No group and no other exported role includes a `realm-management` role.
ADR-0003-C16 continues to require refusal of the authority outside this composite, including
`realm-admin`, `impersonation`, `manage-realm`, `manage-clients`, and `view-events`.

This addendum changes no reviewer or master-realm role. The reviewer's dedicated read-only account,
the prohibition on reviewer administration, the break-glass account boundaries, and ADR-0004-C23
and C24 remain unchanged. Every other rule and control of this decision is unchanged.

**Why.** The local runtime stop record at `docs/evidence/EKO-1-12/console-role-stop.md` shows that
an account holding only the exact five-role `administrator` composite could authenticate, create,
disable, and enable a synthetic account, and set its password. `GET clients?clientId=eko-backend`
then returned an empty list both without and with `search=true`. The account therefore could not
resolve the client UUID needed to assign an application client role. The console-role stop rule
fired, and no role was added. Adding only `view-clients` is the smallest correction that addresses
the failed client-selection step without delegating client or realm administration.

That record is local runtime evidence from uncommitted work, not independent QA proof or a
shared-SHA verification. It does not prove that the amended composite succeeds; that remains to be
verified after approval. Before implementation resumes, K-01 and K-03 must be amended to the
six-role composite and the changed Issue scope and acceptance criteria must be relocked at a new
gate 1. The previous scope lock does not authorize this expansion, and this addendum does not
become accepted without the human's decision at that gate.

### 2026-11-04 — Administrator role mapping: an explicit allow-list, not composite membership

**Status:** Accepted 2026-11-04 (repeated gate 1 of EKO-1-12, Issue #53; accepted by the human in the driving session, recorded on the Issue).

**What it changes.** The statement in *Administrator permissions in Keycloak* that Keycloak refuses
to let an account grant a `realm-management` role it does not hold itself is withdrawn as incorrect
for the Keycloak version in use. Membership in the accepted six-role `administrator` composite is
not, by itself, a preventative boundary on which roles that account can assign.

On acceptance, the six-role composite and every exclusion in its addendum of 2026-11-04 remain
unchanged. The administrator may assign and unassign only the application client roles `rep`,
`manager` and `administrator` of `eko-backend`, including on its own account. Every direct
`realm-management` role mapping is refused, whether the requested role belongs to the composite or
is excluded from it. This enforces the existing rule that accounts and groups hold no direct
`realm-management` mappings; ADR-0003-C22 remains a recurring review, not a substitute for refusal.

Keycloak's built-in fine-grained admin permissions are the permitted additional boundary. The
versioned realm configuration carries an allow-list for exactly the three application roles above.
No account receives an additional `realm-management` role, and no provider, service or image is
added. If this built-in mechanism cannot satisfy the boundary, the task stops and returns to the
human before another mechanism or any additional authority is introduced.

ADR-0003-C16 is extended accordingly: the existing account-management, application-role and denial
checks remain, and a live check attempts every direct `realm-management` role mapping available to
the administrator. Each attempt must be refused and an independent privileged read must establish
that no mapping persisted. A successful HTTP response without a persisted mapping does not count as
a refusal. Every other rule and control of this decision is unchanged.

**Why.** The authorized local diagnostic on EKO-1-12 found that the administrator's assignment of
the excluded `view-authorization` role returned HTTP 204 and persisted, independently confirmed by
administrator and break-glass reads. This conflicts with the preventative denial required by
ADR-0003-C16 and with the prohibition on any account or group holding that role. Detection through
admin events or ADR-0003-C22 would leave the grant active and therefore cannot replace denial.

Keycloak's [Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/#_restrict_user_role_mapping)
documents per-role and per-client `map-role`/`map-roles` policies for restricting which roles an
administrator may assign. Its Users permission description says that user management permits role
mapping but does not select which roles may be mapped; those privileges must be defined per role or
per client role set. This establishes a candidate within the official image, not runtime proof that
it satisfies this decision.

**Options requiring a human choice.**

- **A — Accept this addendum (recommended).** Keep the six-role composite and all exclusions, and
  add the built-in allow-list boundary. This preserves preventative denial without new authority or
  components; its cost is additional versioned authorization policy and fresh denial evidence.
- **B — Reject it and require a different delegation model.** The current criteria remain stopped.
  A new decision must establish that model before implementation, with possible changes to the
  console-only and role-composite decisions.
- **C — Permit out-of-composite grants and rely on after-the-fact review.** This abandons the
  accepted exclusions and preventative security boundary, leaves privilege grants active until
  detected, and would require separate explicit deviations from ADR-0003-C16 and C22. It is not
  recommended.

### 2026-11-04 — Administrator password-reset events: audit fields without credential representation

**Status:** Accepted 2026-11-04 (repeated gate 1 of EKO-1-12, Issue #53; accepted by the human in the driving session, recorded on the Issue).

**What it changes.** On acceptance, ADR-0003-C17 has one narrow exception to its representation
rule, applying only to the administrator operation `PUT users/{id}/reset-password` recorded as an
`ACTION` admin event. That event may have no representation. It must still identify the acting
account, the affected account through its resource path, the operation and resource path, and the
time. No field of the event may contain a password or another credential value.

Every other account creation, change, enabling, disabling, deletion and application-role assignment
or unassignment event must still have a non-empty representation, acting account and time.
`adminEventsEnabled` and `adminEventsDetailsEnabled` remain true. The seven-day temporary-password
review continues to use the event's time, and the reviewer continues to read these events. No other
event type receives this exception. The paired ADR-0005 addendum of the same date is required so
that off-server shipping applies the same narrow rule.

**Why.** The authorized local diagnostic found no representation on reset-password `ACTION` events
while admin-event details were enabled and the other probed CREATE, UPDATE and DELETE events had
representations. The current ADR-0003-C17 wording therefore cannot be met by the observed behavior
of the official image through that setting alone. No accepted configuration that adds the missing
representation has been established.

This is security evidence, not merely observability convenience: an administrator can reach another
account by setting its password, so the reviewer needs a durable record of who changed whose
password and when. The narrow exception preserves that record. It does not preserve the request
representation, which describes a credential change and must never disclose the credential itself.

**Options requiring a human choice.**

- **A — Accept this addendum and its ADR-0005 pair (recommended).** Preserve actor, affected
  account, operation, resource path and time while explicitly allowing no representation for this
  one ACTION event. This keeps the audit and privacy duties without adding a component.
- **B — Reject the exception and preserve the existing representation requirement.** EKO-1-12
  remains stopped. A separate architecture and privacy decision must first establish a supported
  mechanism that supplies a useful, credential-free representation; no provider, image, version or
  custom extension is authorized or known to satisfy it by this assessment.

### 2026-11-06 — Custom Keycloak image for authentication-event detail filtering

**Status:** Accepted 2026-11-06

**Condition.** This addendum takes effect only if the human accepts ADR-0007 option A and its paired
ADR-0004 addendum of the same date. It does not select or implement A by itself.

**What it changes.** On acceptance, *Identity server product* receives a declared deviation for
EKO-1-12: the `keycloak` service uses a custom image built from the official Keycloak 26.8.1 image
with a custom `EventStoreProvider` and factory. The custom factory uses Keycloak's documented
same-ID, higher-order override of the built-in `jpa` factory. The custom store remains a
`JpaEventStoreProvider` subtype, removes non-excepted `details.code_id` before the inherited JPA
persist and subsequent local event delivery, and retains the inherited authentication/admin event,
query, and expiry behavior. It uses the existing Keycloak database and `EVENT_ENTITY` store; no
ordinary event listener, custom authenticator, added service, or new event store is substituted.

Every event type and audit field required by ADR-0005 *Retention*, every administrator/reviewer
permission, and every accepted local/off-server exception remains unchanged. Only non-excepted
`details.code_id` is removed. ADR-0007 supplies the filtering and runtime acceptance boundary.

**Compatibility and security boundary.** `EventStoreSpi` is internal and may change without prior
notice. Every Keycloak release or provider/image change requires review and fresh verification of
provider loading, selection, persistence, expiry, and recovery before deployment; the existing
major-version addendum rule remains unchanged. Provider code is unsandboxed and receives the server
process's privileges, so it is part of the trusted identity-image supply chain. No additional
Keycloak authority or application role is granted.

**Why.** ADR-0007's official 26.8.1 source assessment establishes that realm settings cannot filter
the field before built-in JPA and that an ordinary listener runs too late. It also establishes the
documented custom-provider override, session selection, JPA persistence, and expiry path above.
That is architectural direction only: no concrete provider or custom image has been built or run.

**Options requiring a human choice.**

- **A — Accept this addendum together with ADR-0007 option A and the paired ADR-0004 draft.** This
  permits the custom-image direction, with its internal-SPI and supply-chain costs, while retaining
  all required audit and privacy boundaries. Runtime proof remains mandatory.
- **B — Reject this addendum.** The official-image rule and EKO-1-12 STOP remain unchanged; no
  custom provider or image is authorized.
