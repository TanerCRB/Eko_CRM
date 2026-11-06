# ADR-0005 — Personal data: holders, logging, retention, archiving and erasure

**Status:** Accepted 2026-10-25
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

Customers are mostly natural persons and the company is their data controller
([`project-brief.md`](../../product/project-brief.md), section 5). `TEAM-CONTRACT.md` hard stop 6
forbids changing a file concerning personal data without a decision covering it, so every
customer, visit, note and action task (EKO-3 onward) waits for this decision. ADR-0001 to ADR-0004
forward to it which modules hold personal data, what may be logged, how long sessions, Keycloak
events, the display-name copy and logs are kept, and what archiving and erasure do, backups
included. Each forwarded item is listed under *Items forwarded to this decision*.

This decision is written ahead of the GDPR impact assessment, which the brief schedules after the
MVP and before any real customer data is loaded (section 4, Later 13; section 8). The impact
assessment may revise this decision; a revision is a dated addendum.

## Decision

### Synthetic customer data until the impact assessment

- Until the GDPR impact assessment, every environment, the pilot included, holds only synthetic
  customer data.
- Synthetic customer data is data invented for the purpose that describes no real person or
  business. A value copied from a real customer (a real farmer's name, phone or NIP typed into the
  pilot) is real customer data, whatever environment it is in. Everything the application holds
  about customers counts: customers, their contacts, visits, notes and actions.
- Pilot users are told, before they receive access, that only synthetic customer data may be
  entered.
- Staff personal data is real from the first shared environment, the pilot included, and falls
  under this decision's staff rules (*Staff personal data*). Developer and test environments,
  which are not shared environments, hold only invented staff accounts.
- Tests (`backend/tests/`, `frontend/tests/`), fixtures, the seed script (SEED-1) and CI hold only
  synthetic data and are not holders of personal data under this decision.

### Categories of personal data

Every customer is treated as a natural person, whatever its legal form: the data of a company, a
sole trader and a farmer get the same treatment. A sole trader's NIP identifies a person, and the
phones and e-mails of a company reach persons.

| Category | Items | Source |
|---|---|---|
| **PD-C1 Customer identification** | the customer's name; the NIP; the foreign tax identifier | CUS-1, CUS-5; ADR-0002 |
| **PD-C2 Customer contact and place** | the address (street and number, postal code, post office or town, voivodeship, county, country); every phone; every e-mail address; a visit's own address where one is given | CUS-1, CUS-8, VIS-3 |
| **PD-C3 Free text** | the note on each phone and e-mail (who it reaches); the note text (NOT-1, NOT-2); the action description (ACT-1) | CUS-1, NOT-1, NOT-2, ACT-1 |
| **PD-C4 Customer activity** | the visit's customer and owner, its times, state and flags; the action's owner, author, due date and status; the author of each action status change (ACT-2); the author of each note; the customer's owner and its archived state | VIS-1, ACT-1, ACT-2, NOT-1, CUS-9, CUS-10 |
| **PD-S1 Staff account** | username, e-mail address, first and last name, password hash, role assignments, enabled state | ADR-0003 *Staff personal data*, Keycloak row |
| **PD-S2 Staff sessions and events** | Keycloak's active sessions (with their IP address and times); admin events with their representation (acting account, the account changed, its fields, role mappings and credential changes, times); login events (with their IP address and times); staff IP addresses and usernames in logs | ADR-0003 *Staff personal data*, Keycloak row |
| **PD-S3 Staff in the application** | the subject identifier, in every record that refers to a staff member; the display-name copy (given and family name); the server-side sessions (hashed session identifier, subject, encrypted tokens carrying only the claims ADR-0003 names, created and last-used instants) | ADR-0003 *Staff personal data*, Application row |

- **Free text holds anything.** The PD-C3 items are treated as able to hold any personal data,
  of the customer, of a third person (a family member, a neighbour, an employee) and of staff,
  not only the customer's. Every rule of this decision that names customer field values applies
  to them in full.
- ADR-0003's short-lived login transactions hold no personal data.

### Where personal data is held

**Paths under the ADR-0001 layout.**

| Path | Holds or processes | Categories |
|---|---|---|
| `backend/app/api/**` | receives and returns personal data in HTTP schemas | PD-C1..PD-C4, PD-S3 |
| `backend/app/services/**` | every read and write of customers, visits, notes and actions | PD-C1..PD-C4, PD-S3 |
| `backend/app/domain/**` | the entities and rules that carry personal data | PD-C1..PD-C4, PD-S3 |
| `backend/app/data/**` | stores every application-side category, sessions and the display-name copy included | PD-C1..PD-C4, PD-S3 |
| `backend/migrations/**` | defines the tables and columns holding personal data; a data migration processes it | PD-C1..PD-C4, PD-S3 |
| `backend/app/auth/**` | the session, the subject and the display name taken from the verified token | PD-S3 |
| `backend/app/main.py` | error handling of requests whose bodies carry personal data | PD-C1..PD-C4 |
| `backend/app/integrations/**` | sends visit data to Google Calendar (*Data sent to Google*) | PD-C1, PD-C2, PD-C4 |
| `frontend/src/**` | renders and edits personal data in the browser | PD-C1..PD-C4, PD-S3 |
| `frontend/index.html`, `frontend/public/**` | hold none, but run in the origin that renders it and carries the session cookie | — |

`identity/**` holds no personal data: the realm export holds no staff account (ADR-0003-C14).

**Places off the paths.**

| Place | Holds | Categories |
|---|---|---|
| The application database (in the `pgdata` volume) | every application-side category | PD-C1..PD-C4, PD-S3 |
| Keycloak's database (in the `pgdata` volume) | accounts, sessions, stored admin and login events | PD-S1, PD-S2 |
| The PostgreSQL volume `pgdata` | both databases above | all |
| The backup destination | every backup set: both databases' dumps (ADR-0004 *Backup*) | all |
| The IT department's verification host and a restore host | a decrypted backup set, during the monthly check or a restore (ADR-0004); on the verification host, also the customer identifiers the reconciliation compares, during the check (*Erasure and backups*) | all |
| Container logs on the server | what *What may appear in logs* allows: staff data only, never customer data | PD-S2, PD-S3 subject identifiers |
| The off-server copy of Keycloak events | the events of *Keycloak events off the server* | PD-S1 fields inside admin-event representations, PD-S2 |
| The off-server erasure record | for each approved erasure, the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, nothing else; every entry not marked failed or cancelled is re-applied at every restore (*Erasure and backups*) | none beyond the identifier |
| A report to the human from the reconciliation | only the customer identifier and, where an entry exists, its entry reference in the erasure record, never a customer field value; kept by the IT department off the server with the erasure record, and deleted once the human's decision on it is carried out (*Erasure and backups*) | none beyond the identifier |
| Google Calendar of each rep | the app-created events of their visits (*Data sent to Google*) | PD-C1, PD-C2, PD-C4 |
| The user's browser | what a page shows, in the page's memory only (*The user's browser*) | PD-C1..PD-C4, PD-S3 |

The IT department's off-server record of account changes and its request system are its own
systems outside this application (ADR-0004 *Operator duties*); they hold staff account names and
times, never a credential value, and their retention is not decided here.

### Classifying columns

No table exists yet. This decision classifies personal data by category and path, not by column.
Every task that creates or alters a table names, in its pull request, the category of this
decision (PD-C1..PD-C4, PD-S3) of each new column, or "not personal data". A column holding a
value derived from personal data (a `_match_key` comparison key, ADR-0002; a search or sort key)
has the category of its source. A new category is an addendum to this decision.

### The user's browser

- The single-page application holds personal data only in the memory of an open page. It writes
  no customer data and no staff data to `localStorage`, `sessionStorage`, IndexedDB or the Cache
  Storage API, and registers no service worker that caches API responses (the brief excludes
  offline mode).
- Every API response carrying personal data is sent with `Cache-Control: no-store`.
- No customer field value appears in a URL path, of the API or of the single-page application:
  path parameters are opaque record identifiers. The single-page application does not put a
  customer field value or a search term into its own location (the address bar and the browser
  history); a search term reaches the API in a request's query string or body only.

### What may appear in logs

**Never written to any log**, by any component, at any level, on any path, error paths included:

- customer field values — every item of PD-C1, PD-C2 and PD-C3, and the values of PD-C4 other
  than record identifiers and staff subject identifiers;
- note text, action descriptions and the notes on phones and e-mails (PD-C3);
- request and response bodies, and the input a validation error rejected (an HTTP 422 echoing the
  request);
- query strings;
- SQL statement text and statement parameters, and a database error's detail (PostgreSQL's
  `DETAIL` of a unique violation names the duplicated value, for example the NIP of a CUS-6
  conflict);
- an exception's message or arguments where they can carry a value of the request or of a row
  (a Pydantic validation error, a database driver error); the exception's type and code location
  may be written;
- session identifiers: the application's session cookie value and its stored hash, the
  login-transaction identifier, Keycloak's session and authentication-session identifiers and
  cookie values;
- tokens: access, refresh and ID tokens, authorization codes, the OIDC `state` and `nonce`, the
  PKCE verifier, and Google tokens;
- passwords, temporary passwords included, and credential values;
- secret values.

No component writes a secret value to its log. This is ADR-0004's rule (*Secret handling*),
restated without change.

**What each component may write.**

- **The backend** (`backend`, `migrate` and any worker) may write: the time, the HTTP method, the
  route template or a path holding only opaque identifiers, the status, the duration, the record
  identifiers concerned, the caller's subject identifier, the request's correlation identifier
  (generated by the backend, never taken from a client value, and also carried by the error
  response), the type and code location of an error, and its own start, stop and migration
  progress (revision identifiers).
- **Keycloak** may write: its start, stop and configuration messages without secret values;
  errors; and, for each event, the event type, realm, client, the staff account's identifier and
  username, the IP address and the error code. For a failed login naming no existing account, the
  typed username is not logged, not stored in an event and not shipped: it may be a password typed
  into the wrong field. Keycloak does not run at debug or trace level in a shared environment.
  **If the official image cannot keep the typed username out.** The rule on the typed username
  works with the official Keycloak image (ADR-0004). If the implementing task, EKO-1-06 (#19) or
  EKO-1-09 (#41), finds that the official Keycloak image cannot leave the typed username of a failed
  login naming no existing account out of its log and its stored events, that task stops and the
  change returns to the human as an addendum to this decision, before any provider or image is
  added and before the stored event types of *Retention* are changed.
- **PostgreSQL** may write: connection and authentication events (the role, the database, the
  client address inside the composition), its own start, stop, checkpoint and recovery messages,
  and, for an error, at most its SQLSTATE and its position in the statement. It writes no error
  message text, no statement text, no statement parameters and no error detail, for the
  application's database and Keycloak's alike: an error's primary message can carry an input
  value (an invalid date, a full-text search term).
- **The HTTPS entry point** (`proxy`) may write, per request: the time, the client IP address, the
  host name, the method, the path without its query string, the status, the size and the
  duration; and its own certificate and listener messages. It writes no query string and no
  request or response header value other than the host name. Staff IP addresses in its log are
  staff personal data under PD-S2.
- **The other services** (`frontend`'s static file server, `backup`) write no personal data:
  `frontend` writes no per-request log or one under the entry point's rule above; `backup` writes
  its run's times, outcome and row counts, never a row's content.

### Who reads logs

- Container logs on the server are read only by the IT department's staff who hold administrative
  rights over the container runtime (ADR-0004 *Secret handling*), for operating the environment
  and handling incidents. This holds for the pilot as for production, because pilot logs hold real
  staff data.
- Anyone else (a developer investigating a defect, the reviewer) receives only an extract that the
  IT department hands over for a named incident or defect and has checked against this section.
- The reviewer reads no container log and is given no right over the container runtime for it
  (ADR-0004 *Operator duties*).

### Staff personal data

- Staff personal data is held in the places ADR-0003 *Staff personal data* names, and in the
  places of *Where personal data is held* above that list a PD-S category. It falls under this
  decision from the first shared environment.
- How long a deactivated account's username, e-mail address and password hash stay in Keycloak is
  not decided here (*Forward references*); ADR-0003 forbids deleting an account the application's
  data refers to.

### Retention

Every retention below counts from the stated start event. "No later than" includes the bound
itself. The interval at which a deletion runs counts within the bound, never beyond it.

- **Server-side sessions**, abandoned ones included, are deleted together with their encrypted
  tokens no later than the realm's SSO session maximum lifespan after the session was created.
  The SSO session maximum is set by EKO-2-01 (ADR-0003 *Forward references*); this rule is
  relative to it. A session is also deleted at logout and when Keycloak refuses its refresh
  (ADR-0003).
- **Login transactions**, abandoned ones included, are deleted no later than 1 hour after they
  were created.
- **Admin events of the application realm** are stored and kept in Keycloak for 90 days after the
  event.
- **Admin events of the master realm** are stored and kept in Keycloak for 90 days after the
  event.
- **Login events of the master realm** are stored and kept in Keycloak for 90 days after the
  event.
- **Login events of the application realm** are stored, for the authentication event types only,
  and kept in Keycloak for 30 days after the event. The stored types are login, login error,
  logout, password update and its error, password reset, its error and the sending of a reset
  e-mail, refresh error, and account lockout by brute-force detection. Successful token refreshes
  (`REFRESH_TOKEN`) and code-to-token exchanges (`CODE_TO_TOKEN`) are never stored, because with an
  access token of at most 5 minutes (ADR-0003) they record each staff member's use of the
  application minute by minute.
- **The display-name copy** is kept while at least one record in the application refers to the
  subject, and is deleted together with the last such record. A copy that no record refers to is
  deleted no later than 180 days after the subject's last login; the next login takes it again.
- **Logs** of every service of the composition (`backend`, `migrate`, `keycloak`, `postgres`,
  `proxy`, `frontend`, `backup`) are deleted no later than 14 days after they were written, also
  when they are small; deletion is by time, and rotation by size alone does not meet this rule.
  The mechanism uses no logging driver of a cloud provider (ADR-0004-C4).
- **The off-server copy of Keycloak events** keeps admin events of both realms and master-realm
  login events for 365 days after the event, and application-realm login events for 90 days after
  the event (*Keycloak events off the server*).
- **The off-server erasure record** keeps each entry not marked failed or cancelled, completed
  entries and entries not yet marked alike, until it holds a commit time and no backup set whose
  snapshot started before that commit time remains at the destination (*Erasure and backups*).
- No retention of admin events is zero, and admin events are never switched off in any realm of
  any shared environment (ADR-0003 *Administrator permissions in Keycloak*).
- Keycloak events and sessions inside backup sets are kept as long as their set (ADR-0004
  *Backup*); this decision shortens no backup set.

### Keycloak events off the server

- **Which events.** The admin events of the application realm and of the master realm, with their
  representation; the login events of the master realm; and the login events of the application
  realm that *Retention* stores. Each copied event carries its type, realm, time, client, acting
  and affected account, IP address, error, and for an admin event its resource path and
  representation. It carries no token, no credential value and no session or
  authentication-session identifier, and, for a failed login naming no existing account, not the
  typed username.
- **Where to.** Append-only storage on a host operated by the IT department that is off the server
  in the sense of ADR-0004 *Backup* (*Destination: off the server*): another host, not a second
  disk, volume or directory of the server's own host. The backup destination's host may serve.
  The credential the server uses there can add events but cannot delete or overwrite any.
- **How often.** A shipment runs at least every 5 minutes, also when no event is new (a
  heartbeat), and a check that does not run on the server alerts the IT department when no
  shipment has arrived for 1 hour.
- **How long kept there.** Admin events of both realms and master-realm login events: 365 days
  after the event. Application-realm login events: 90 days after the event. Deletion is done by
  the destination's own housekeeping, not by the server.
- **Who reads the copy.** The reviewer (ADR-0004 *Operator duties*), read-only, and the IT
  department for incident investigation. No holder of the application role `administrator` reads
  it through that role.
- **Within the composition.** The shipping works within ADR-0004's composition, its seven
  services and the official Keycloak image. If the implementing task finds that it cannot, that
  task stops and the change returns to the human as an addendum to ADR-0004, before any service
  or image is added. Adding a service would be a deviation from ADR-0004.
- **Implemented by** EKO-1-09 (#41).
- Exception EKO-1-03/B-02 lifts only when that task ships; the change to the exception register
  is the human's own edit.
- **What shipping does not close.** Shipping closes the risk of exception EKO-1-03/B-02 only for
  events already shipped. An actor with administrative rights over the server's container runtime
  or its PostgreSQL can suppress or alter events before they are shipped, and the heartbeat proves
  that shipping runs, not that it is complete. This residual case stays open after EKO-1-09 (#41)
  ships. The reviewer checks each announced break-glass use (ADR-0004 *Operator duties*) against
  its events in the off-server copy.

### Archiving

- Archiving a customer (CUS-9) keeps all of its personal data, in every place that holds it,
  until the customer is restored or erased. Restoring a customer from the archive keeps its data.
- The business sets no retention period for active or archived customers now. Until it does, the
  end event of an archived customer's data is its erasure. The impact assessment may set a period;
  that is an addendum to this decision.

### Erasure

Permanent erasure is a later feature (brief section 4, Later 14). This section fixes the rule it
follows when it is built.

- **What it removes.** Erasing a customer removes, from the application database: the customer's
  row with its name, NIP, foreign tax identifier and address; every phone and e-mail with its note;
  every note on the customer or on its visits, of every author, the manager's notes (NOT-2)
  included; every action created from those notes, with its description and its status changes;
  every value derived from them (comparison and search keys); and every record of background work
  that carries the customer's data. Every visit of the customer, past and future, of every owner
  (past visits keep their original owner after a reassignment, CUS-10), loses its customer
  reference, its own address and every customer value. A visit row is kept only stripped in that
  way, so that dashboard counts stay; whether it is kept is decided by the erasure feature.
- **Places excused, and why.** Backups: *Erasure and backups* below. Google Calendar: the
  app-created events of the customer's visits, past ones included (CUS-9 removes only future
  events), carry its name, address and phone; what erasure does to them, and what happens when
  the owner's Google access is lost, is forwarded to EKO-1-05 (#18) for ADR-0006 to decide. Logs
  and the off-server copy of Keycloak events: they hold no customer data (*What may appear in
  logs*, *Keycloak events off the server*). Keycloak's database: it holds no customer data. The
  user's browser: it holds customer data only in an open page's memory (*The user's browser*). The
  IT department's verification host: its decrypted copy is deleted after the check (ADR-0004
  *Backup*), and the customer identifiers the reconciliation compares are deleted with it
  (*Erasure and backups*). A restore host: the application database restored on it is covered by
  the re-apply (*Erasure and backups*); the decrypted backup set it received at ADR-0004 restore
  step 3 is deleted once the restore is recorded at step 14 or abandoned; a restore host that does
  not become the server, a test restore's host included, has its restored databases and volumes
  deleted once the restore is recorded or abandoned; and an abandoned restore, on any host, has
  its restored databases and volumes deleted once it is abandoned. The IT department records an
  abandoned restore in its operations record, with its date, the backup set used, who performed
  it, the host and the step at which it stopped.
- **What it leaves unchanged.** Erasing one customer changes no other customer's data and no
  staff attribution of another record (as PRH-5). An archived customer can be erased.

### Erasure and backups

- Erased personal data stays in the backup sets taken before the erasure until ADR-0004's
  retention removes them: the sets of the last 30 days, and the verified sets kept beyond them
  until three newer sets have passed the verification. No backup set is purged, shortened or
  overwritten because of an erasure, and the server gets no right to delete at the destination.
- **The off-server erasure record.** Only the IT department writes the erasure record, off the
  server, after the erasure is approved and before it is carried out, except the entry that
  *Reconciliation* allows for an erasure already carried out with no entry; the server holds no
  credential that can write it. An entry holds the customer's internal record identifier, the
  entry's time, its mark and, once recorded, the erasure's commit time, never a customer field
  value. An entry is marked completed with the erasure's commit time. An entry is marked failed
  only after the live application database is shown to still hold its identifier, and only once
  the erasure can no longer commit: no request for it is in flight and no run of it is queued. An
  entry is marked cancelled when the withdrawal of its erasure is received, after the live
  application database is shown to still hold its identifier, and only once the erasure can no
  longer commit: no request for it is in flight and no run of it is queued. An entry marked failed
  or cancelled is never re-applied. Any further attempt to erase an identifier whose entry is
  marked failed or cancelled needs a new entry, written before the attempt runs. Every other
  entry, completed or not yet marked, is re-applied at every restore (*Re-apply at restore*).
- **The commit time.** The commit time of an erasure is a time in UTC taken from the server, on
  the clock behind the snapshot start of *The backup point*, after the erasure's database
  transaction has committed. The transaction's start, which PostgreSQL's `now()` and
  `transaction_timestamp()` return, is not a commit time. A time taken elsewhere (the approval, a
  user's report, a workstation's clock) is not a commit time.
- **An entry whose commit time cannot be read.** When the commit time cannot be read from the
  server (for example, the server was lost before the IT department marked the entry), the entry
  keeps being re-applied at every restore, and it is never deleted on the strength of a time
  earlier than the true commit. If a commit time is recorded for it later, it is a time known to be
  no earlier than the commit, such as the time the IT department confirmed the identifier absent
  from the live application database.
- **The backup point.** The backup point of a set is the start of its application-database
  dump's snapshot. A set whose backup point cannot be shown to be after an erasure's commit time
  counts as started before it.
- **When an entry is deleted.** An entry not marked failed or cancelled is deleted only once it
  holds a commit time and no backup set whose snapshot started before that commit time remains at
  the destination. An entry that holds no commit time is kept.
- **Erasure is idempotent by identifier.** Erasing an identifier that is absent from the database
  is a no-op, not a failure, and erasing an identifier again changes nothing further.
- **Customer identifiers are never reused.** An identifier once issued to a customer is never
  issued to another customer, also after a restore from an earlier backup set, so an old entry can
  never match a new customer. ADR-0002 fixes no key type; this rule binds the task that creates
  the first customer table and does not change ADR-0002.
- **Re-apply at restore.** At every restore, every entry of the record that is not marked failed
  or cancelled, completed entries and entries not yet marked alike, is carried out again on the
  restored application database. Because erasure is idempotent by identifier, re-applying an entry
  whose erasure was already carried out changes nothing further. An approved erasure that a
  restore reaches before it is carried out or cancelled is carried out by the re-apply, and can no
  longer be cancelled. The re-apply is carried out after `migrate` has run at
  ADR-0004 restore step 12 and before `backend` and any worker are started at step 13, so that
  every such erasure is in effect before the backend or any worker serves or synchronises the
  restored data, and so before the public listener is opened to the internet at step 14. Step 13's
  verification is unaffected: the row counts it relies on are those compared at step 6, before any
  migration and before the re-apply. What the re-apply does to app-created Google Calendar events
  is forwarded to EKO-1-05 (#18) for ADR-0006 to decide. Because the re-apply covers every entry
  not marked failed or cancelled, whatever its time, an erasure that committed while a backup ran
  is either absent from the set or re-applied; the instant of the backup point does not decide it.
- **No backup before the re-apply.** No backup set is written to the destination from a restored
  application database before the re-apply has run on it: the `backup` service is not started on a
  restore host before then. ADR-0004's procedure takes its first backup at step 14, after the
  re-apply.
- **Reconciliation.** At every monthly verification of ADR-0004 *Backup*, the IT department
  reconciles the erasure record with the live application database, by customer identifier only.
  The reconciliation never writes an entry or changes a mark on its own; it does only what the
  points below say:
  - **The sets compared.** The live application database is compared with the set verified at
    that check and with the verified set before it. When a restore into the server's live
    application database from a set older than the verified set before it has been recorded since
    that verified set, only the set verified at that check is compared; after any other restore, a
    test restore on a separate host included, both sets are compared.
  - **An identifier absent with no entry.** An identifier that a compared set holds and the live
    application database does not hold, with no entry that is not marked failed or cancelled, is
    reported to the human. An entry is written for it only against a shown approved erasure of
    that customer, marked completed with the time the IT department confirmed the identifier
    absent from the live application database. Such an entry does not make that erasure meet the
    order of *The off-server erasure record*: the erasure was carried out with no entry. Without a
    shown approval, the human decides; the customer can be recovered from a compared set that
    holds it, while that set remains at the destination, only by ADR-0004's full restore of the
    application database from that set, and every change made after that set was taken is then
    lost.
  - **Entries not yet marked.** Every entry not yet marked is resolved. When the live application
    database does not hold its identifier, the entry is marked completed with the time the IT
    department confirmed the identifier absent. When it holds it, the IT department checks the
    erasure's approval: the entry of a withdrawn erasure is marked cancelled once the erasure can
    no longer commit, and the entry of an erasure still pending stays unmarked. An entry that is
    unmarked, and whose identifier the live application database holds, at two consecutive
    reconciliations is reported to the human.
  - **Entries marked completed.** The identifier of every entry marked completed is absent from the
    live application database. A completed entry whose identifier the live database still holds is
    reported to the human, and the entry is not deleted while that stands.
  - **Entries marked failed or cancelled.** An entry marked failed or cancelled whose identifier the
    live application database does not hold, with no other entry for that identifier that is not
    marked failed or cancelled, is reported to the human and is not marked completed.

  The customer identifiers compared are deleted after the check, with the decrypted copies. A
  report to the human carries only the customer identifier and, where an entry exists, its entry
  reference in the erasure record, never a customer field value. The IT department keeps each
  report off the server with the erasure record, and deletes it once the human's decision on it is
  carried out. What the human decides on a report is the human's decision and is not decided here.
  The reconciliation does not catch an erasure with no entry of a customer that no compared set
  holds. Nor does it catch an erasure with no entry, or a mark made false later, that a restore reaches
  before the next check: the restore brings the customer back, and the live application database
  then agrees with the record. Against these cases only the order of *The off-server erasure
  record* holds: the entry written before the erasure is carried out, a failed or cancelled mark
  only once the erasure can no longer commit, and a new entry before any further attempt.
- **The restore record.** The IT department records the re-applied erasures with the restore
  record that step 14 writes, by their count and by their entries' own references in the erasure
  record only, never by a customer identifier or field value.
- The re-apply is a rule of this decision, carried out inside the window ADR-0004 already keeps the
  public listener closed to the internet, between steps 12 and 14. It adds no step to ADR-0004's
  procedure, changes none of its steps or their order, and does not change ADR-0004; ADR-0004's
  text is not edited for it, and a cross-reference there would be a dated addendum to ADR-0004.
  If the erasure feature finds that it cannot carry out the re-apply within ADR-0004's composition
  before `backend` or any worker starts, that task stops and the change returns to the human.
- The reconciliation is likewise a duty of this decision, carried out by the IT department on the
  occasion and the host of ADR-0004's monthly verification. It changes none of that check's own
  comparisons and does not change ADR-0004.

### Data sent to Google

- Only the data a visit's calendar event needs is sent to Google: the content VIS-3 fixes (the
  customer's name in the title, the customer's or the visit's address as the location, the contact
  phone in the description), the visit's times, and the identifiers the synchronisation needs.
  Never an e-mail address, a NIP or foreign tax identifier, the note on a phone or e-mail, note
  text or an action.
- This decision forwards to EKO-1-05 (#18), for ADR-0006 to decide: the list of each field sent,
  within this rule; how Google tokens are stored; and what erasure and the re-apply at restore do
  to app-created calendar events, past ones included.

### Changes to accepted decisions

This decision changes no accepted decision: not ADR-0001, ADR-0002, ADR-0003 or ADR-0004, by
neither edit nor addendum. It works within ADR-0004's backup retention (30 days and the verified
sets), ADR-0004's destination to which the server can only add, ADR-0004's seven services and the
official Keycloak image, ADR-0003's bound on deleting abandoned sessions, and ADR-0003's rule that
admin-event retention is never zero. Gate 1 of EKO-1-04 (#17), on 2026-10-25, ruled that the
restore re-apply of erasures and the shipping of Keycloak events off the server are within
ADR-0004 and not deviations; no deviation from an accepted decision was approved. On 2026-10-25,
after the first evaluation, the human placed the re-apply after `migrate` at ADR-0004 restore
step 12 and before `backend` and any worker start at step 13, within gate 1's "between steps 12
and 14". On 2026-10-26, after the second evaluation, the human decided that a restore re-applies
every entry of the erasure record not marked failed or cancelled, that the IT department
reconciles the record with the live application database, and that an official Keycloak image
unable to keep the typed username of a failed login naming no existing account out of its log
and stored events returns the change to the human as an addendum to this decision. On 2026-10-26,
after the third evaluation, the human decided that the reconciliation never writes or promotes an
entry on its own and reports to the human an identifier absent with no entry and a failed or
cancelled entry whose identifier is absent; that every entry not yet marked is resolved at each
monthly reconciliation, and a withdrawn erasure's entry is marked cancelled when the withdrawal is
received; that an entry is marked failed only once its erasure can no longer commit, that a
further attempt on such an identifier needs a new entry, and that the reconciliation leaves out
the verified set before the newest one only after a restore from a set older than it; and that
the commit time is a time taken after the erasure transaction commits. On 2026-10-26, after the
fourth evaluation, the human decided that an entry is marked cancelled only once its erasure can
no longer commit; that a report to the human carries only the customer identifier and the entry
reference, is kept by the IT department off the server with the erasure record and is
deleted once the human's decision on it is carried out, that recovering a customer from a
compared set is ADR-0004's full restore of the application database, which loses every change
made after that set, and that what the human decides on a report is not decided here; and that
the reconciliation leaves out the verified set before the newest one only after a restore into
the server's live application database, not after a test restore on a separate host.

### Items forwarded to this decision

- **Which modules hold personal data** — ADR-0001 l.184 → decided in *Where personal data is
  held*.
- **Logging** — ADR-0001 l.184 → decided in *What may appear in logs*.
- **Retention** — ADR-0001 l.184 → decided in *Retention*.
- **Archiving vs. erasure** — ADR-0001 l.184 → decided in *Archiving* and *Erasure*.
- **Which tables and columns hold personal data** — ADR-0002 l.134 → decided in *Classifying
  columns*.
- **Retention, archiving vs. erasure, what may appear in logs** — ADR-0002 l.134-135 → decided in
  *Retention*, *Archiving*, *Erasure* and *What may appear in logs*.
- **Deleting abandoned sessions with their encrypted tokens within the SSO session maximum** —
  ADR-0003 l.93-95 → decided in *Retention*.
- **Admin-event retention, never zero** — ADR-0003 l.204 → decided in *Retention*.
- **Whether application-realm login events are stored** — ADR-0003 l.287 → decided in
  *Retention*.
- **Retention of sessions, Keycloak events and the display-name copy; what may appear in logs** —
  ADR-0003 l.291-292 → decided in *Retention* and *What may appear in logs*.
- **Retention of sessions, admin events, login events and the display-name copy; logging** —
  ADR-0003 l.316-317 → decided in *Retention* and *What may appear in logs*.
- **What else may appear in logs** — ADR-0004 l.175-176 → decided in *What may appear in logs*.
- **How erasure treats backups** — ADR-0004 l.316-317 → decided in *Erasure and backups*.
- **Master-realm event retention longer than the review interval** — ADR-0004 l.426-427 → decided
  in *Retention*.
- **Logs (container logs included); retention of admin events of both realms, master-realm login
  events, sessions and logs; erasure in backups, verified sets included** — ADR-0004 l.559-561 →
  decided in *What may appear in logs*, *Retention* and *Erasure and backups*.
- **The same items** — ADR-0004 l.582-584 → decided in *What may appear in logs*, *Retention* and
  *Erasure and backups*.
- **Shipping Keycloak events off the server** — `docs/PLAN.md` l.56-57 → decided in *Keycloak
  events off the server*.
- **Erasure in backups** — `docs/PLAN.md` l.56-57 → decided in *Erasure and backups*.

ADR-0003 l.396 names ADR-0005's retention in an option that was not chosen; it is not a forward.

### Forward references (not decided here)

Each forward below names the task that receives the duty. It does not state that the duty is
already in that task's *Done when*.

- EKO-1-05 (#18), ADR-0006, receives: the fields sent to Google within *Data sent to Google*;
  Google token storage; what erasure and the re-apply at restore do to app-created calendar
  events, past ones included.
- EKO-1-06 (#19) receives: the application realm's event settings in the export under
  `identity/`, the master realm's event settings at bootstrap, the log settings of each service
  (PostgreSQL's error logging and Keycloak's typed username of a failed login naming no existing
  account included) and the time-bound deletion of logs in the composition, the backend's log and
  error-handling rules, and `Cache-Control: no-store`; it stops under *What may appear in logs* if
  the official Keycloak image cannot keep that typed username out.
- EKO-2-01 (#21) receives: the SSO session maximum, and the deletion of sessions and login
  transactions.
- EKO-1-09 (#41) receives: shipping Keycloak events off the server, without the typed username of
  a failed login naming no existing account; it stops under *What may appear in logs* if the
  official Keycloak image cannot keep that typed username out.
- EKO-1-08 (#36) receives: proving in production the event settings, the log bound and the
  off-server copy, and making the re-apply duty of *Erasure and backups* part of the restore it
  carries out. The re-apply itself cannot be proven at EKO-1-08, because erasure is a later
  feature (brief section 4, Later 14); it is proven once erasure exists (ADR-0005-C15).
- The task that builds the permanent-erasure feature receives: recording each erased customer's
  identifier with a time in UTC taken from the server after the erasure transaction commits, so
  that the IT department can read the commit time of *Erasure and backups* (*The commit time*).
- Not decided: the GDPR impact assessment; it may revise this decision and has no PLAN entry yet.
- Not decided: whether reps' private Gmail calendars (VIS-1, VIS-3), which put customer names,
  addresses and phones into accounts the company does not control, are acceptable; it is a
  question for the GDPR impact assessment.
- Not decided: a retention period for active and archived customers; it closes with the impact
  assessment.
- Not decided: the permanent-erasure feature; it closes when the feature is planned, or earlier if
  the impact assessment requires erasure from go-live.
- Not decided: how long an entry of the off-server erasure record marked failed or cancelled is
  kept; it closes when the permanent-erasure feature is planned.
- Not decided: what the human decides on a report to the human from the reconciliation of
  *Erasure and backups*; it is the human's decision on each report.
- Not decided: how long a deactivated account's username, e-mail address and password hash stay
  in Keycloak; it closes with the impact assessment.

## Options considered

### Erasure and backups (G-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. Erased data stays in backups until ADR-0004's retention removes them; an off-server erasure record re-applied at every restore before the public listener opens** (chosen at gate 1, 2026-10-25) | An off-server record kept by IT; one more duty in the restore window; the erasure feature must be idempotent by identifier. | Nothing. |
| B. Erased data stays in backups; a restore does not re-apply erasures | None now. | Relying on an erasure after a restore: a restore brings an erased customer back silently. |
| C. Purge erased customers from backup sets | Deviation from ADR-0004 (append-only destination, retention of the verified sets); every verified set re-written. | The write-only destination that protects backups from a compromised server. |

### Application-realm login events (G-2)

| Option | Cost | Closes off |
|---|---|---|
| **A. Stored, authentication types only, 30 days** (chosen at gate 1, 2026-10-25) | Staff IP addresses and login times kept 30 days on the server and 90 off it. | Nothing. |
| B. All types stored | Successful refreshes every 5 minutes become a minute-level record of each staff member's use of the application. | A proportionate staff-data footprint. |
| C. Not stored | None. | Evidence of an administrator logging in first with a temporary password they set (ADR-0003), and of attacks on the internet-facing login page. |

### Shipping Keycloak events off the server (C-1, G-9)

| Option | Cost | Closes off |
|---|---|---|
| **A. Within ADR-0004's composition; the implementing task chooses the means and returns to the human if none fits** (chosen at gate 1, 2026-10-25) | The means is constrained (an existing service, the runtime's own logging, Keycloak's own features). | Nothing: an addendum to ADR-0004 stays possible. |
| B. A dedicated shipping service added now | A deviation from ADR-0004's seven services, which the Story of EKO-1-04 forbids. | Keeping ADR-0004 unchanged in this task. |
| C. Only through the daily backup set | None: the backup already holds Keycloak's database. | Detecting events cleared in the day before the next backup (exception EKO-1-03/B-02 stays). |

### Data sent to Google (G-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. ADR-0005 sets the rule, ADR-0006 lists the fields** (chosen at gate 1, 2026-10-25) | None now. | Sending any field outside VIS-3 without an addendum here. |
| B. Left entirely to ADR-0006 | None now. | Nothing, but Google Calendar has no rule from this decision. |

### Display-name copy (G-8)

| Option | Cost | Closes off |
|---|---|---|
| **A. Kept while a record refers to the subject; a copy no record refers to deleted 180 days after the last login** (chosen at gate 1, 2026-10-25) | A staff member with no records and no login for 180 days drops out of name lists until the next login. | Nothing. |
| B. A number after deactivation | The application does not learn of a deactivation, so the rule cannot be applied. | Nothing, but not enforceable. |
| C. Kept with no end | None. | A bound on staff data after a person leaves. |

### Classification granularity (G-5)

| Option | Cost | Closes off |
|---|---|---|
| **A. Category and path now, columns by each table-creating task** (chosen at gate 1, 2026-10-25) | Each such task names its columns' categories. | Nothing. |
| B. Columns now | No table exists, so the column list would be invented ahead of the design. | Nothing, but rewritten by EKO-3. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0005-C1 | Every pull request that creates or alters a table names, for each new column, its category from *Categories of personal data* or "not personal data". |
| ADR-0005-C2 | A test sends to each endpoint that accepts a body a request that fails validation and carries a marker value in every field; the marker appears in no line the backend logs. |
| ADR-0005-C3 | A test saves a second customer with an existing NIP; the NIP appears neither in the backend's log nor in PostgreSQL's log, and PostgreSQL's log holds no statement text for it; a statement that fails PostgreSQL's input parsing on a marker value leaves the marker in no line of PostgreSQL's log. |
| ADR-0005-C4 | A request through `proxy` with a marker in its query string and a session cookie: `proxy`'s log line for it holds the path without the query string, and neither the marker nor the cookie value. |
| ADR-0005-C5 | After a login, a token refresh, a failed login, a failed login whose typed username is a marker naming no existing account, and a logout against a running Keycloak, Keycloak's container log and stored events hold no token, authorization code, cookie value, password, session identifier or the marker, and its log level is neither debug nor trace. |
| ADR-0005-C6 | The rendered composition and each shared host delete container logs no later than 14 days after they were written; by review of each shared host, no container log line older than 14 days exists (recorded with the date of the check). |
| ADR-0005-C7 | The realm export under `identity/` stores admin events with their representation, expires them after 90 days, stores login events of only the types *Retention* names, and expires them after 30 days; in each live master realm, login and admin events are stored and expire after 90 days (recorded with the date of the check). |
| ADR-0005-C8 | With the clock fixed, a test finds no session, and none of its encrypted tokens, whose age since creation exceeds the realm's SSO session maximum, and no login transaction older than 1 hour. |
| ADR-0005-C9 | A test of the display-name copy: deleting the last record referring to a subject deletes its copy; a copy no record refers to is deleted 180 days after the subject's last login; a copy any record refers to is kept. |
| ADR-0005-C10 | Against a shared environment: an admin event in each realm and a master-realm login event appear in the off-server copy within 5 minutes; with the server's credential, deleting or overwriting an event in the copy is refused; with shipping stopped, the IT department receives an alert within 1 hour from a check that does not run on the server. |
| ADR-0005-C11 | By review of the off-server copy: it holds admin events and master-realm login events of the last 365 days and application-realm login events of the last 90 days, and none older (recorded with the date of the check); no copied event holds a token, a credential value, a session identifier or, for a failed login naming no existing account, the typed username; each announced break-glass use was checked against its events in the copy. |
| ADR-0005-C12 | `grep -rnE "localStorage|sessionStorage|indexedDB|caches\.open|serviceWorker" frontend/src` returns nothing; every API response carrying personal data has `Cache-Control: no-store`. |
| ADR-0005-C13 | Every path parameter in the backend's OpenAPI document is an opaque record identifier; no route of the single-page application puts a customer field value or a search term into its location. |
| ADR-0005-C14 | Once erasure exists: a test erases a customer and then finds, in the application schema, none of its field values, no reference to its identifier, no note or action of it of any author, and every other customer's rows and every staff attribution of other records unchanged; erasing the same identifier again, and erasing an absent identifier, succeeds and changes nothing. |
| ADR-0005-C15 | Once erasure exists: by review of the IT department's records, every erasure has an entry in the off-server erasure record, written by the IT department after the erasure was approved and before it was carried out, holding only the identifier, the entry's time, its mark and the commit time; an erasure that the reconciliation found carried out with no entry does not meet this, also once its entry is written; the server holds no credential that can write the record; every commit time recorded is a time in UTC taken from the server after the erasure transaction committed, never the transaction's start, or a time known to be no earlier than the commit; every entry marked failed was so marked only after the live application database was shown to still hold its identifier and once no request for the erasure was in flight and no run of it was queued; every entry marked cancelled was so marked on the withdrawal of its erasure, after the live application database was shown to still hold its identifier and once no request for the erasure was in flight and no run of it was queued; every attempt to erase an identifier whose entry was marked failed or cancelled had a new entry written before it ran; after every restore, every entry not marked failed or cancelled, completed or not yet marked, was in effect before `backend` or any worker served or synchronised the restored data, no entry marked failed or cancelled was re-applied, no backup set was written to the destination from the restored database before the re-apply, and the restore record names the re-applied erasures by count and entry reference only; no entry was deleted while it held no commit time or while a backup set whose snapshot started before its commit time remained. |
| ADR-0005-C16 | By the human's statement per shared environment, recorded with its date: the environment holds only synthetic customer data, until the GDPR impact assessment is done. |
| ADR-0005-C17 | A test creates customers after a backup set was taken, restores the database from that set, creates a customer, and finds that its identifier is none of those issued after the set. |
| ADR-0005-C18 | By the IT department's dated record of each restore, abandoned restores included: every abandoned restore is recorded with its date, the backup set used, who performed it, the host and the step at which it stopped; the decrypted backup set was deleted once the restore was recorded or abandoned; the restored databases and volumes of an abandoned restore, and of a restore host that did not become the server, were deleted once the restore was recorded or abandoned. |
| ADR-0005-C19 | Once erasure exists: by the IT department's dated record of each monthly verification, the reconciliation of *Erasure and backups* was carried out; the live application database was compared with the set verified at that check and with the verified set before it, or, only after a restore into the server's live application database from a set older than that verified set, with the set verified at that check alone; every customer identifier that a compared set holds and the live application database does not hold has an entry not marked failed or cancelled, or was reported to the human, and an entry was written for it only against a shown approved erasure, marked completed with the time the IT department confirmed the identifier absent; every entry not yet marked was marked completed with the time its identifier was confirmed absent, marked cancelled for a withdrawn erasure, or left unmarked for an erasure still pending, and an entry left unmarked with its identifier present at two consecutive reconciliations was reported to the human; the identifier of every entry marked completed is absent from the live application database, or the entry was reported to the human and not deleted; every entry marked failed or cancelled whose identifier the live application database does not hold, with no other entry for that identifier not marked failed or cancelled, was reported to the human and not marked completed; no entry was written or had its mark changed by the reconciliation other than as that section says; every report to the human carries only the customer identifier and, where an entry exists, its entry reference, never a customer field value, is kept by the IT department off the server with the erasure record, and none was kept after the human's decision on it was carried out; the customer identifiers compared were deleted after the check. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->

### 2026-10-28 — Forwards to EKO-1-06 reassigned after its split

**What it restates.** EKO-1-06 (#19) was split into EKO-1-06 and EKO-1-10..EKO-1-15 (#51..#56).
This addendum changes only which task receives a duty this decision names. No rule, stop rule or
control changes. From this date:

- *What may appear in logs*, "If the official image cannot keep the typed username out": the
  implementing task named there is **EKO-1-12 (#53)** or EKO-1-09 (#41), in place of EKO-1-06 (#19)
  or EKO-1-09 (#41). The stop rule is otherwise unchanged: the task stops, and the change returns to
  the human as an addendum to this decision before any provider or image is added and before the
  stored event types of *Retention* are changed.
- *Forward references*, "EKO-1-06 (#19) receives":
  - The following go to **EKO-1-12 (#53)**, which also carries the typed-username stop rule above:
    - the application realm's event settings in the export under `identity/`;
    - the master realm's event settings at bootstrap;
    - Keycloak's log settings, including the typed username of a failed login naming no existing
      account.
  - The following go to **EKO-1-13 (#54)**:
    - the log settings of every other service, PostgreSQL's error logging and the log of `proxy`
      included;
    - the time-bound deletion of logs in the composition;
    - the backend's log and error-handling rules, with its correlation identifier;
    - `Cache-Control: no-store`.

**Why.** These passages name EKO-1-06 as the task receiving duties it no longer carries after the
split. Left unchanged, the typed-username stop rule would bind a task that no longer configures
Keycloak, and the tasks that do would find nothing in this decision naming them. Approved by the
human at gate 1 of EKO-1-06 on 2026-10-28 (G-5 B, Issue #19). This is not a deviation: no rule
changes.

### 2026-11-04 — Off-server copy of the administrator password-reset ACTION event

**Status:** Accepted 2026-11-04 (repeated gate 1 of EKO-1-12, Issue #53; Q-2 A accepted by the human in the driving session, recorded on the Issue).

**What it changes.** This addendum takes effect only if the human also accepts ADR-0003's addendum
of 2026-11-04, *Administrator password-reset events: audit fields without credential
representation*. For the single administrator operation `PUT users/{id}/reset-password` recorded as
an `ACTION` admin event, *Keycloak events off the server* permits the copied event to have no
representation. The copy must still carry the acting account, the affected account through its
resource path, the operation and resource path, the realm and the time. It carries no password or
other credential value.

Every other admin event keeps the existing representation requirement. Shipping frequency,
heartbeat, append-only destination, retention, reviewer access, and every privacy prohibition remain
unchanged. ADR-0005-C7's requirement that admin-event details are enabled also remains unchanged.

**Why.** The local EKO-1-12 diagnostic found that this ACTION event has no representation even with
admin-event details enabled. Shipping cannot supply a representation absent from the source event.
Pairing this addendum with ADR-0003 prevents the local event rule and the off-server evidence rule
from diverging. The retained fields preserve the security audit of who reset whose password and
when; no credential representation is shipped.

**Options requiring a human choice.**

- **A — Accept this addendum together with the ADR-0003 pair (recommended).** This preserves the
  same narrow, credential-free audit record locally and off the server without adding a provider,
  service or image.
- **B — Reject this addendum.** The existing off-server representation duty remains unchanged and
  the ADR-0003 exception cannot operate alone. EKO-1-12 remains stopped until a supported mechanism
  meets the original requirement through a separate architecture and privacy decision.

### 2026-11-05 — Application-realm stored events: the top-level user-session identifier

**Status:** Accepted 2026-11-05 (repeated gate 1 of EKO-1-12, Issue #53; option A accepted by the human in the driving session, recorded on the Issue).

**What it changes.** On acceptance, ADR-0005-C5 has one narrow declared deviation: a stored
application-realm authentication event of a type required by *Retention* may carry the Keycloak
user-session identifier in its top-level `sessionId` field. The exception applies to that field and
those stored events only. It does not apply to Keycloak's container log, master-realm events, admin
events, authentication-session identifiers, application session identifiers, cookies, tokens,
authorization codes, passwords, other credentials, or the typed username of an unknown account.

Every event type required by *Retention* remains stored. This addendum permits no removal or
substitution of event types and changes no retention period, log-level rule, or other privacy rule.
The D-5 unknown-username stop is independent and unchanged.

ADR-0005-C11 and the off-server rule are unchanged: no session identifier may be shipped. Before an
application-realm event leaves the server, the shipping mechanism must omit the top-level `sessionId`
field while retaining every field the off-server rule requires. Raw replication of the locally
permitted field does not satisfy this rule. No off-server addendum is required for this local-only
exception.

**Why.** The EKO-1-12 runtime evidence establishes that serialized stored events contain the exact
user-session identifier decoded from an issued access token. It does not establish the individual
field or the affected event types. The official Keycloak 26.8.1 source establishes the storage
mechanism: [`EventBuilder.session(...)`](https://github.com/keycloak/keycloak/blob/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventBuilder.java)
sets the event's top-level `sessionId`; the [JPA event store](https://github.com/keycloak/keycloak/blob/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java)
persists and returns that field; and successful login and logout paths set it from the user session.
The JPA store factory exposes no field-filtering setting, and its `onEvent` conversion persists the
field independently of event-listener configuration. Removing required event types is therefore the
only way the accepted realm settings alone could avoid the stored value, and that would destroy
required audit evidence.

The exception retains session-level correlation for the reviewer's local audit while keeping the
longer-lived off-server copy free of session identifiers. It is not a finding that a session
identifier is harmless or a credential; it is an explicit choice to retain one identifier in the
bounded local event store rather than add an unproven provider or weaken event coverage.

**Options requiring a human choice.**

- **A — Accept this local-only addendum (recommended).** Preserve all required stored event types
  and the off-server prohibition while allowing only the top-level user-session `sessionId` in
  application-realm stored events. This avoids a new provider, service or image and retains local
  audit correlation; its cost is the explicit relaxation of C5 for that field.
- **B — Reject the exception and preserve C5 unchanged.** EKO-1-12 remains stopped. A separate
  decision must select and assess a mechanism that removes the field before storage, which the
  accepted official-image configuration does not provide. Any provider, image or composition change
  requires its own ADR-0003/ADR-0004 decision before implementation.

### 2026-11-05 — Unknown typed usernames in application-realm LOGIN_ERROR events

**Status:** Accepted 2026-11-05 (repeated gate 1 of EKO-1-12, Issue #53; D-5 option A accepted by the human in the driving session, recorded on the Issue).

**What it changes.** If the human explicitly chooses a local stored-event exception, D-5 and
ADR-0005-C5 receive only this declared deviation: an application-realm `LOGIN_ERROR` event for a
failed login naming no existing account may retain the typed username in `details.username`. The
exception covers neither the container log nor any other event type, realm, field or destination.
The username of an existing account remains governed by the existing rule and known-account audit
contrast.

Every required event type and retention period remains unchanged. No credential, token,
authorization code, cookie, session or authentication-session prohibition changes, including the
accepted local-only top-level `sessionId` exception. This addendum does not decide that the typed
value is harmless, personal data, or a credential; the existing reason for D-5 is that it may be a
password typed into the wrong field.

ADR-0005-C11 and the off-server rule remain unchanged. Before shipping an application-realm
`LOGIN_ERROR` event naming no existing account, the shipping mechanism must omit `details.username`
while retaining every field the off-server rule requires. Raw replication of the locally permitted
field is non-compliant. No off-server addendum is required for this local-only exception.

This exception addresses only stored events. The existing D-5 evidence combines container logs and
stored events and does not identify the destination or field. Before this addendum can be accepted
as a sufficient resolution, a synthetic-safe read-only projection must establish that the marker is
absent from the container log and present only at the covered stored-event path. A marker in the
container log or any other field leaves the task stopped and requires a separate decision.

**Why.** The independently executed D-5 test proves that at least one unknown typed marker was
retained in Keycloak logs or stored events. Its known-account contrast was a non-empty `LOGIN_ERROR`
event carrying the known username in `details.username`. Neither result identifies where an unknown
marker appeared.

The official Keycloak 26.8.1 source establishes the relevant mechanism without resolving that
runtime ambiguity. The [browser username authenticator](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/authentication/authenticators/browser/AbstractUsernameFormAuthenticator.java)
trims the submitted value and calls `event.detail(Details.USERNAME, username)` before looking up the
account; an unknown account then produces `USER_NOT_FOUND`. The [JPA event store](https://github.com/keycloak/keycloak/blob/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java)
serializes the complete details map, and its factory exposes no field-filtering setting. The
required `LOGIN_ERROR` type cannot simply be removed without weakening the accepted audit coverage.

Container logging is separate. The current realm export has `eventsListeners: []`, so the built-in
logging event listener is not enabled by that configuration. If enabled, the [logging listener](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/events/log/JBossLoggingEventListenerProvider.java)
writes every event detail; its `sanitize` option addresses line breaks and quoting, not exclusion of
`username`. This neither establishes nor excludes a current container-log leak and offers no
supported selective-denial setting. Only the destination projection can establish the actual runtime
destinations without exposing a marker value.

**Options requiring a human choice.**

- **A — Accept this local-only stored-event exception after the projection confirms its scope.**
  This preserves every required event type and the off-server prohibition without a new provider,
  service or image. Its cost is explicit local retention of input that may be credential-like; it is
  insufficient for any marker in the container log or at another event path.
- **B — Reject the exception and preserve D-5 unchanged.** EKO-1-12 remains stopped. A separate
  decision must select a mechanism that removes the unknown typed username before storage or logging.
  Any provider, authenticator, event store, image or composition change requires its own
  ADR-0003/ADR-0004 assessment before implementation.
- **C — Remove `LOGIN_ERROR` from stored events.** This is not an acceptable resolution: it weakens
  required audit coverage and the accepted retention rule instead of removing only the prohibited
  value.

### 2026-11-05 — Application-realm LOGIN events: the duplicate user-session identifier in details.code_id

**Status:** Accepted 2026-11-05 (repeated gate 1 of EKO-1-12, Issue #53; option A accepted by the human in the driving session, recorded on the Issue).

**What it changes.** On acceptance, ADR-0005-C5 has one further narrow declared deviation: a stored
application-realm `LOGIN` event may carry in `details.code_id` only the Keycloak user-session
identifier already carried by that same event's top-level `sessionId` field under the accepted
addendum of 2026-11-05. The exception applies to that one event type, field and duplicate value in
the local stored event only. It does not apply to another value, another `details` field, another
event type, Keycloak's container log, master-realm events, admin events, or an off-server copy.

The accepted top-level `sessionId` exception is unchanged and is not widened. The accepted D-5
exception remains limited to an unknown typed username at application-realm `LOGIN_ERROR`
`details.username`; it neither covers nor is widened by this addendum. No authentication-session
identifier, application session identifier, credential, password, token, authorization code, cookie,
or unknown typed username receives an exception here.

Every event type required by *Retention*, including `LOGIN`, and every required audit field and
retention period remains unchanged. Removing `LOGIN` or any other required event type is not a
permitted privacy remedy. No log-level rule changes.

ADR-0005-C11 and the off-server rule remain unchanged: no session identifier may be shipped. Before
an application-realm `LOGIN` event leaves the server, the shipping mechanism must omit both the
top-level `sessionId` field and `details.code_id` while retaining every field the off-server rule
requires. Raw replication of either locally permitted field is non-compliant. No off-server
addendum is required for this local-only exception.

**Why.** The EKO-1-12 field-path-aware runtime check compared the exact issued user-session
identifier with stored-event values without disclosing that identifier. It confirmed the same value
at application-realm `LOGIN` `details.code_id` in addition to the accepted top-level `sessionId`.
For that observed event, `details.code_id` therefore is the same user-session identifier by direct
value equality, not an inference from the field name. This evidence does not claim that every value
ever named `code_id` is a user-session identifier or extend the exception to another occurrence.

The official Keycloak 26.8.1 source previously reviewed for the accepted local exceptions establishes
the storage side: the [JPA event store](https://github.com/keycloak/keycloak/blob/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java)
serializes the complete event details map, and its factory exposes no field-filtering setting. Its
storage conversion persists event details independently of event-listener configuration. This is
source-based evidence about persistence and configurability; it is not what establishes the runtime
value equality above. No supported official-image configuration has been established that excludes
only `LOGIN` `details.code_id` while retaining the required event and its other audit fields.

The exception preserves the required local login audit event while keeping the longer-lived
off-server copy free of session identifiers. It is not a finding that a session identifier is
harmless or a credential; it is an explicit choice to retain this duplicate identifier in the
bounded local event store rather than add an unproven provider or weaken event coverage.

**Options requiring a human choice.**

- **A — Accept this local-only addendum (recommended).** Preserve every required event type and the
  off-server prohibition while allowing only the confirmed duplicate user-session value at
  application-realm `LOGIN` `details.code_id`. This avoids a new provider, service or image; its cost
  is one additional explicit relaxation of C5 at one field, with fresh field-path and destination
  evidence required.
- **B — Reject the exception and preserve C5 unchanged.** EKO-1-12 remains stopped. A separate
  decision must select and assess a mechanism that removes the field before storage. Any provider,
  authenticator, event store, image or composition alternative requires its own ADR-0003/ADR-0004
  assessment and human approval before implementation; none is selected or authorized here.
- **C — Remove `LOGIN` or another required stored event type.** This is not an acceptable resolution:
  it weakens required audit coverage and the accepted retention rule instead of removing only the
  prohibited value.

### 2026-11-05 — Required application-realm authentication events: duplicate user-session identifier in details.code_id

**Status:** Draft — pending approval

**What it changes.** On acceptance, ADR-0005-C5 has one further narrow declared deviation: a stored
application-realm authentication event whose type is required by *Retention* may carry a session
identifier in `details.code_id` only when that non-empty value exactly duplicates the non-empty
Keycloak user-session identifier in the same event's top-level `sessionId` field under the accepted
addendum of 2026-11-05. An arbitrary or different `details.code_id` value receives no exception. An
absent or empty `details.code_id` counterpart at top-level `sessionId`, or a mismatch between the two
values, fails the rule.

The exception applies only to that field in those local stored application-realm events. It does not
apply to another field, an event type not required by *Retention*, a successful `REFRESH_TOKEN` or
`CODE_TO_TOKEN` event, Keycloak's container log, master-realm events, admin events, or an off-server
copy. No authentication-session identifier, application session identifier, credential, password,
token, authorization code, cookie, or unknown typed username receives an exception here.

This addendum supplements the accepted 2026-11-05 `LOGIN` `details.code_id` addendum by extending
only its event-type scope to the other application-realm authentication event types required by
*Retention*, under the same non-empty same-event equality condition. The accepted `LOGIN` addendum
remains unchanged. The accepted top-level `sessionId` exception and the accepted D-5 exception are
also unchanged, and neither is widened by this addendum.

Every event type required by *Retention*, including `LOGIN` and `RESET_PASSWORD_ERROR`, and every
required audit field and retention period remains unchanged. Removing any required event type is not
a permitted privacy remedy. No log-level rule changes.

ADR-0005-C11 and the off-server rule remain unchanged: no session identifier may be shipped. Before
an application-realm event leaves the server, the shipping mechanism must omit top-level `sessionId`
and, wherever present, `details.code_id`, while retaining every field the off-server rule requires.
The unknown-account `LOGIN_ERROR` `details.username` omission is also unchanged. Raw replication of
any locally permitted field is non-compliant. No off-server addendum is required for this local-only
exception.

**Why.** The EKO-1-12 runtime evidence confirms a real application-realm `RESET_PASSWORD_ERROR`
event carrying `details.code_id`, outside the accepted `LOGIN`-only rule. The projection did not
establish that this event had a non-empty top-level `sessionId` or that the two fields were equal.
Accordingly, this assessment does not claim same-event equality or identify the `code_id` value as
the same user-session identifier for `RESET_PASSWORD_ERROR`. The field name alone proves neither
fact.

The official Keycloak 26.8.1 source previously reviewed for the accepted local exceptions establishes
that the [JPA event store](https://github.com/keycloak/keycloak/blob/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java)
serializes the complete event details map, exposes no field-filtering setting, and persists details
independently of event-listener configuration. No supported official-image configuration has been
established that selectively removes `details.code_id` from only the affected required event types
while retaining those events and their other audit fields.

Before this addendum can be accepted as a sufficient resolution, a separately authorized,
synthetic-safe read-only projection must establish, without recording any identifier value, that
every application-realm stored event relying on it has non-empty values at both fields and that those
values are exactly equal. In particular, it must establish that condition for the observed
`RESET_PASSWORD_ERROR` event. The projection must also identify every event type using the exception
and establish that the value occurs at no non-excepted field, event type, realm, or container-log
destination. If equality, non-empty counterparts, or destination scope are not established, this
addendum is insufficient and the STOP remains; no value or behavior may be guessed.

The exception preserves required local audit events while keeping the longer-lived off-server copy
free of session identifiers. It is not a finding that a session identifier is harmless or a
credential; it is an explicit choice to retain only an exact duplicate in the bounded local event
store rather than add an unproven provider or weaken event coverage.

**Options requiring a human choice.**

- **A — Accept this local-only addendum only after the projection confirms its conditions
  (recommended).** This preserves every required event type and the off-server prohibition without a
  new provider, service or image. Its cost is an explicit relaxation of C5 for `details.code_id`
  across the closed set of required application-realm authentication event types, strictly limited
  to non-empty same-event duplicates. Acceptance alone is not runtime proof; fresh equality,
  field-path, destination, contrast and mutation evidence is still required before K-04 can pass.
- **B — Reject the exception and preserve C5 unchanged.** EKO-1-12 remains stopped. A separate
  decision must select and assess a mechanism that removes the field before storage. Any provider,
  authenticator, event store, image or composition alternative requires its own ADR-0003/ADR-0004
  assessment and human approval before implementation; none is selected or authorized here.
- **C — Remove `RESET_PASSWORD_ERROR`, `LOGIN`, or another required stored event type.** This is not
  an acceptable resolution: it weakens required audit coverage and the accepted retention rule
  instead of removing only the prohibited value.
