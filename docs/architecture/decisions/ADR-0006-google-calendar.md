# ADR-0006 — Google Calendar integration: linking, tokens, event content, change detection and background work

**Status:** Accepted 2026-10-27
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

Each visit is mirrored as an event in the owner's primary calendar in their private Gmail account
([`project-brief.md`](../../product/project-brief.md), VIS-1..VIS-11, PRH-1..PRH-3, section 5
*Google*). The EKO-5 tasks need a decided OAuth flow, token storage, event recognition, change
detection, conflict rule and retry before they can be built. The riskiest parts of the MVP are
here: testing-mode expiry and the user cap, deletions in Google going unnoticed (brief section 1),
and customer personal data leaving for accounts the company does not control. ADR-0001, ADR-0002,
ADR-0003, ADR-0004 and ADR-0005 forward duties to this decision. Each forwarded item is listed under
*Items forwarded to this decision*.

Nothing about Google's behaviour is proven in this repository. Every fact about Google that this
decision relies on is listed under *Assumptions about Google*, with what it rests on and what
happens if it turns out false.

## Decision

### Who links, and what linking is not

- A Google account is linked for the calendar only. Linking a Google account creates,
  authenticates and alters no account, and is not done through Keycloak's identity brokering
  (ADR-0003, *Accounts never depend on Google*). Keycloak has no Google identity provider; the
  Google OAuth client is the backend's own client, separate from the application's Keycloak client.
- Login works with no Google account linked (ACC-2). No page, operation or role requires a link.
  A staff member with no link works in the application, and their visits are flagged
  Unsynchronised (VIS-7) until they link.
- A link is made only by the staff member whose calendar it is, from their own application
  session. No one links, relinks or unlinks a calendar for another staff member, the manager and
  the administrator included. An account holding only `administrator` cannot link (ADR-0003:
  `administrator` grants no CRM data).
- Each staff member has at most one link. A link names the staff member by the Keycloak subject
  identifier only (ADR-0003, *Identifier the application stores*).
- The Google OAuth client code lives in `backend/app/integrations/`, not in `backend/app/auth/`:
  Google is an external system in the sense of ADR-0001, and `auth` must not depend on
  `integrations` (ADR-0003, *Layers*).

### OAuth flow and scope

- **Flow.** The OAuth 2.0 authorization code flow for a web server application, with PKCE, between
  the backend (a confidential client holding the Google OAuth client secret) and Google, requesting
  offline access so that Google issues a refresh token, and requesting consent at every link so a
  relink receives a new refresh token.
- **Scope.** Exactly one scope is requested:

  | Scope | Reason |
  |---|---|
  | `https://www.googleapis.com/auth/calendar.events.owned` | create, change, read and delete the app's events in the rep's own primary calendar (VIS-1, VIS-3, VIS-6, VIS-11); it reaches only events of calendars the rep owns, not calendars shared with the rep |

  No other scope is requested: not `openid`, `email` or `profile` (so Google returns no ID token and
  no e-mail address, and the application holds no staff e-mail address, ADR-0003 *Staff personal
  data*), and no scope reaching mail, contacts, drive or calendar settings. A grant that lacks this
  scope, or holds any other, is refused: its tokens are revoked at Google and not stored. If the
  task that builds linking (EKO-5-01) finds that Google does not offer this scope for the primary
  calendar of a private Gmail account, that task stops and the scope returns to the human as an
  addendum to this decision, before any other scope is requested.
- **Binding to the rep's own session.**
  1. The rep starts a link from their own application session with a state-changing request
     (ADR-0003's `Origin` check applies). The backend creates a **link transaction** server-side
     holding the OAuth `state`, the PKCE verifier, the subject of the session and the hash of that
     session's identifier. It holds no other personal data, is single use, and is deleted at
     completion, whether completion succeeds or is refused, and no later than 10 minutes after it
     was created.
  2. Google redirects the browser to the **callback path `https://<app-host>/google-link/callback`**,
     a route of the single-page application on the application's one origin (ADR-0004, *HTTPS
     exposure*). It is registered as the only authorised redirect URI of the shared environment's
     Google OAuth client. Developer environments register their own local address.
  3. The single-page application replaces its location at once, so that the authorization code
     and `state` stay neither in the address bar nor in the browser history, and sends them to the
     backend in the body of a same-origin, state-changing request carrying the session cookie.
  4. The backend completes the link only when that request's session is the session that started
     the transaction (same subject and same session-identifier hash) and the `state` equals the
     transaction's. Only then does it exchange the code, with the PKCE verifier and the client
     secret, and store the token for that subject. Otherwise it refuses, stores nothing and
     deletes the transaction. A second completion of one transaction is refused, because the
     transaction no longer exists.

  No backend endpoint is served without a session for linking: the callback is a static route of
  the single-page application, and the authorization code is useless without the PKCE verifier
  and the client secret, which never leave the backend. No access or refresh token is ever
  returned to the single-page application (ADR-0003).
- **Relinking a different Google account.** The application stores no identifier of the Google
  account (see *Token storage*). At every link and relink, before any change is sent or read, the
  backend lists, in the newly linked primary calendar, the live events carrying this environment's
  marker, and compares them with every confirmed event the application records for that owner
  (*Background work*, *A record counts once Google confirms it*), past and planned alike, in the
  calendar in use and in each calendar the owner left by confirming another account. Until the
  outcome below is settled, the link is held unused, no event counts as deleted, no visit state
  changes and no prompt is raised. A record whose create Google has not confirmed is neither
  compared nor read directly here; its create runs once the link is used.
  - When the list holds an event the application records in another owner's calendar, the link
    stays held unused whatever else is found, and no choice of the owner lifts the hold
    (*Ownership*).
  - When it finds confirmed events of a calendar the owner left and none of the calendar in use,
    that earlier calendar is the one linked again, and the link is used without the choice below:
    its records are tracked again, each removal recorded as not carried out for it is taken up
    again (*Removals not carried out*), each of its confirmed events not found is read directly by
    its identifier, as polling does, and the calendar just left is handled as under *Lost access*
    (*When the owner confirms another account*). A planned visit whose confirmed event that
    calendar holds keeps that event, brought up to date with the visit's latest data (*Read before
    write*); only a planned visit with no confirmed event there is created in it, with a new event
    identifier.
  - When it finds every confirmed event of the calendar in use, or the owner has no confirmed
    event at all (a first link included), the link is used, without the choice below.
  - When it finds some confirmed events of the calendar in use and not others, the link is used,
    and each confirmed event not found is read directly by its identifier, as polling does
    (*Change detection*).
  - When it finds none of them while the owner has some, the owner chooses one of three: relink
    the account they used before; confirm that this is the same calendar, after which each
    confirmed event not found is read directly by its identifier, as polling does, and a deletion
    found so counts under VIS-11; or confirm a new calendar, which is handled under *Lost access*
    (*When the owner confirms another account*).

### Testing mode and the path to Google verification

- The pilot runs the Google OAuth client in Google's **testing mode**, with the user type that
  admits private Gmail accounts. Two limits follow, and the decision accepts both for the pilot:
  - **The 7-day expiry.** A grant expires 7 days after it was given. On expiry the owner sees the
    VIS-8 reconnect notice, no visit state changes and no prompt is raised (PRH-3), pending changes
    are kept and synchronise after relinking, and the owner relinks at least once every 7 days.
  - **The cap of 100 test users.** Only Gmail accounts entered as test users in the Google Cloud
    project can grant access, and at most 100 can be entered. A rep whose account is not entered,
    or who is past the cap, cannot complete a link: Google refuses the consent, the application
    stores nothing, the application works for them as with no link, and their visits are
    Unsynchronised (VIS-7) until they link. The pilot has about ten users.
- **Verification path.** Production use needs Google's app verification of the OAuth client for
  the scope above: the company domain (`<company-domain>`) verified with Google, the application's
  home page and a privacy policy published under that domain, the scope's justification, and
  Google's review, which takes days to weeks. Verification ends both testing-mode limits.
- **When it closes.** The verification is carried out by the task for brief section 3, *Later*
  item 10, which must be planned and done before go-live, or earlier if the pilot needs more than
  testing mode allows (more than 100 test users, or the 7-day relink becoming unacceptable to the
  pilot). Until then every shared environment runs in testing mode.
- **Who holds the Google Cloud project.** The IT department holds the Google Cloud project and its
  OAuth client under a Google account the company controls, keeps the client secret's master copy
  (*Secrets*), and keeps the list of test users. That list holds the reps' private Gmail addresses
  in Google's console, outside this application; it is the IT department's own record, like its
  request system (ADR-0005, *Where personal data is held*), and its retention is not decided here.

### Token storage

- **What is stored.** For each link, in the application database through the `data` layer
  (ADR-0002), and nothing else:

  | Item | Category (ADR-0005) |
  |---|---|
  | the subject identifier of the staff member who linked | PD-S3 |
  | the Google refresh token, encrypted | PD-S3 |
  | the scope Google granted | not personal data |
  | the link state (linked; access lost; unlinked; held unused after a link or relink, or under *Ownership*) | PD-S3 |
  | the instants the link was made, last used successfully and lost | PD-S3 |

  Every item falls under an existing ADR-0005 category or is not personal data; no new category
  is created. The access token is never stored: the backend and the worker hold it in memory only, and obtain a
  new one from the refresh token when it expires. No Google account identifier, e-mail address,
  name or ID token is stored. A task that creates the link table names these categories for its
  columns (ADR-0005-C1).
- **Encryption.** The refresh token is encrypted at rest with authenticated encryption under the
  **Google token encryption key**, which is a separate key from ADR-0004's session-token encryption
  key. The key is held neither in the application database nor in any backup set: it reaches the
  `backend` and the worker only as an environment variable from the `backend` environment file
  (*Secrets*). The database and every backup set therefore hold only ciphertext.
- **When a stored token is deleted.**
  - at unlink by the owner; the backend also revokes the token at Google, and deletes it once
    Google confirms the revocation or answers that the grant is no longer valid; from the unlink
    on the link is never used, and a revocation request that fails is retried on the cadence of
    *Retry* until Google gives one of those answers, except as the bullet after this list says;
  - when Google refuses a refresh (the grant expired or was revoked) — the link state becomes
    "access lost";
  - when a refused or failed grant check makes a link unusable (*OAuth flow and scope*);
  - when the owner relinks: the new token replaces it.
- **A token that cannot be decrypted with the key in use** (after a key replacement, after a
  restore from a set taken before the last key replacement, or with a wrong key value) is not
  deleted: the link state becomes "access lost" and the owner relinks, which replaces the token.
  When the key value is corrected and the token decrypts again, the link works again, so a wrong
  key value loses no link for good. At unlink by the owner, a token that cannot be decrypted with
  the key in use is deleted at once and no revocation is sent, because none can be sent without
  the token in clear; the owner is told that the application could not withdraw its access and
  how to remove it in their Google account, with no customer value. This is safe: the ciphertext
  is of no use without a key value no longer in use; after a replacement on suspected compromise
  its grant was revoked first (*Secrets*); after any other replacement, a refresh of that grant
  also needs the client secret, which is rotated with the key and its old value deleted (A-18);
  with a wrong key value, the grant left at Google is the exposure option G-10 A already names
  for restored data, until the owner's own removal ends it; and in testing mode the grant expires
  7 days after it was given. Deleting the ciphertext only shortens the time it is kept.
- **Deactivated staff.** The application does not learn of a deactivation in Keycloak (ADR-0005,
  *Options considered*, G-8 B), so a deactivated staff member's link is not deleted on
  deactivation. It stays until it is unlinked, Google refuses it, or (in testing mode) it expires
  after 7 days. While it works, it lets the application remove that staff member's future events
  when their customers are reassigned (CUS-10) and carry out removals due under *Erasure*.
- **Link transactions** hold no personal data beyond the subject and the session hash, and are
  deleted as stated under *OAuth flow and scope*.

### Secrets

Both secrets follow ADR-0004 *Secret handling* as a class: master copy in the IT department's
password manager, never in the repository, an image, a `VITE_*` variable, the application database
or a backup set; a missing value stops its component.

| Secret | Used by | Kept on the server (besides the off-server master copy) | Delivered | Readers | Rotation |
|---|---|---|---|---|---|
| Google OAuth client secret | `backend` (code exchange at link, revocation at unlink), the worker (refresh) | `backend` environment file | environment variable, read in `settings.py` | IT department | regenerated in the Google Cloud project and set in the `backend` environment file together; restart of `backend` and the worker; every rotation ends by deleting the old secret in the Google Cloud project once `backend` and the worker run with the new one; on suspected compromise, when a holder leaves IT, and whenever the Google token encryption key is replaced on suspected compromise |
| Google token encryption key | `backend`, the worker | `backend` environment file | environment variable, read in `settings.py` | IT department | on suspected compromise and when a holder leaves IT; on suspected compromise, every grant whose token is on record is first revoked at Google while the key in use still decrypts it, and the Google OAuth client secret is rotated with it; replacing it makes every stored refresh token undecryptable, so every linked rep relinks — accepted for about ten users |

The worker reads the whole `backend` environment file, so it also holds the secrets of that file
it does not use (the session-token encryption key and the OIDC client secret); it runs the backend
image, so this opens no path the `backend` service does not already have.

A restore takes the Google token encryption key from its master copy like every other secret
(ADR-0004 restore step 2) and does not replace it, so restored links keep working; a link whose
grant was revoked since the backup is refused by Google at its first use and handled as lost
access. A link whose token was encrypted before a key replacement made after the backup set was
taken cannot be decrypted, and is handled as under *Token storage*: access lost, the token kept
until the owner relinks. This adds no step to ADR-0004's restore procedure.

### Background work

- **Mechanism.** Background work runs in one **`worker` service** started from the backend image,
  with a job queue held in the application database (PostgreSQL row locking with
  `SELECT … FOR UPDATE SKIP LOCKED`, and `LISTEN`/`NOTIFY` to wake the worker; ADR-0002 *Background
  work*). No message broker and no other image is added. The worker's code is Python inside
  `backend/`, under ADR-0001's layer rules, shipped in the backend image (ADR-0001 *Background
  work*). Its entry point is the module `backend/app/worker.py`, outside the layer directories as
  `backend/app/main.py` is, and it does not depend on `api` or `auth` (ADR-0003, *Layers*: only
  `api` and `main.py` depend on `auth`). That module is listed in
  [`architecture-sensitive-paths.md`](../architecture-sensitive-paths.md).
- **The worker and migrations.** The worker never runs `alembic upgrade head`, neither at start nor
  at any other time; it starts only after `migrate` has exited with success, as `backend` does; and
  at start it reads the database's Alembic revision and exits without working when that revision
  is not its code's head or a revision descending from it, so it never works on a schema older
  than its code (ADR-0004, *Migrations*). It publishes no port.
- **Within ADR-0004.** The worker is the further service ADR-0004 foresees (*Composition and
  placement*, *Background work*). It is recorded in ADR-0004's addendum of 2026-10-27. It uses the
  application database role, and its connection pool counts in that role's budget (ADR-0003-C19, "background jobs"). It is started and replaced with `backend` at every
  deployment, rollback and restore; at a restore it starts at ADR-0004 step 13, after ADR-0005's
  re-apply of erasures.
- **Jobs carry identifiers only.** A job names the visit, owner or link it concerns by record
  identifier, never by a customer field value, and reads the current data when it runs. Jobs of
  one visit run one at a time, in the order they were queued. A deletion job queued by an erasure
  counts, for this order, as a job of the visit whose event it deletes, so it runs only after
  every earlier job of that visit has ended, a request already sent included.
- **The event record comes first.** The record of an event (its identifier and the owner in whose
  calendar it is created) is written in the same transaction that queues its create, before the
  first attempt, so an event whose create was sent and never answered is still recorded, and
  erasure finds it.
- **A record counts once Google confirms it.** An event record counts as an event in its calendar
  only once Google has confirmed its create: answered it as created, or, after an "already exists"
  answer, shown it live with this environment's marker for that visit (*Retry*, *No second
  event*). Until then the record is pending, whether its create was never sent, is suspended, is
  waiting for its next retry step or was never answered: the link check (*Relinking a different
  Google account*) and polling neither compare it with the calendar nor read it directly, and it
  never counts as a deletion in Google. Its create runs under *Retry*, and erasure still deletes
  it (*Erasure and calendar events*, *How*).

### Event content: each field sent to Google

Within ADR-0005 *Data sent to Google*, an event the application writes holds exactly these fields,
and no other field is set:

| Google field | Value | Category (ADR-0005) | Why the sync needs it |
|---|---|---|---|
| `summary` | `Wizyta: <customer name>` | PD-C1 | VIS-3 title |
| `location` | the visit's own address if given, else the customer's address: street and number, postal code, post office or town, country; never the voivodeship or county | PD-C2 | VIS-3 location; opens Google Maps |
| `description` | one contact phone number, alone: the customer's phone marked primary; if no contact is marked primary, or the primary contact is an e-mail address, the description is empty and no phone is sent | PD-C2 | VIS-3 description |
| `start`, `end` | the visit's start and end, each as `dateTime` with `timeZone` `Europe/Warsaw` | PD-C4 | VIS-1, VIS-6 |
| `id` | an event identifier the application chooses for each create before its first attempt, derived from the visit's opaque record identifier, the environment identifier and a random value new to that create, and kept across that create's retries | not personal data beyond the visit identifier | a retried create produces no second event, and a later create never meets an identifier Google already holds (*Retry*) |
| `extendedProperties.private` | the marker: the environment identifier and the visit's opaque record identifier | not personal data beyond the visit identifier | recognises the application's own events (*Recognising the application's events*) |
| `visibility` | `private` | not personal data | people the rep shares the calendar with see the time slot, not the customer |

- **No attendee is ever set, and no notification or invitation is sent.** Every insert, update and
  delete is sent with notifications to guests switched off (`sendUpdates` `none`). The customer is
  never an attendee (VIS-3, PRH-1).
- **Never sent:** an e-mail address, the NIP, the foreign tax identifier, the note on a phone or an
  e-mail, note text, an action, the visit's state or flags, any other phone, and any other customer
  value (ADR-0005). No customer field value appears in the URL or query string of a request to
  Google: paths and query parameters carry only opaque identifiers.
- A customer with no address and a visit with no address give an event with no `location`.
- **What is read back.** Every request to Google asks only for the fields it needs (Google's
  partial-response field selection): `id`, `status`, `start`, `end`, `updated`, `etag` and the
  private extended properties, and on a list the page and paging fields. The application never reads back
  `summary`, `location`, `description`, attendees, or the creator's or organiser's e-mail address.

### Recognising the application's events

- Only each owner's primary calendar is read and written (VIS-1). No other calendar of the owner is
  read.
- **The marker.** An event is the application's own when its private extended properties carry
  this environment's identifier and a visit identifier. The environment identifier is
  configuration that differs per environment (pilot, production, each developer environment), so
  one Gmail calendar linked in two environments keeps each environment's events apart. A private
  extended property cannot be set by hand in Google Calendar's own interface.
- **An event without the marker is never imported, changed or deleted**, never appears in the
  application and never counts anywhere (VIS-2, PRH-2).
- **An event with the marker is synchronised**: the event whose identifier is the one the
  application stored for a visit is that visit's event, and its date, time, duration and deletion
  flow back under VIS-4 and *Change detection*.
- **A hand-made event is not recognised.** An event made by hand in Google with the same title,
  location and description as an application event carries no marker and is not recognised; title
  and description are never used to recognise an event.
- **Twins.** An event carrying the marker of a known visit whose identifier is not the one stored
  for that visit (a copy made in Google) is not that visit's event: it is never imported, changed
  or deleted, creates no visit and counts nowhere. A create retried after a lost response produces
  no twin, because the event identifier is fixed before the first attempt. The one exception is
  the erasure sweep (*Erasure and calendar events*, *Sweep by marker*): an erased visit's marked
  event whose identifier has the form the application chooses was created by the application, and
  the sweep deletes it.
- **Ownership.** An event is matched only to a visit whose event record names the same owner as
  the link whose calendar holds it. An event of another owner's visit found in a calendar (two staff
  members linking one Google account) is never changed or deleted through that calendar's link and
  counts nowhere. Such an event also holds that link unused: at a link or relink (*Relinking a
  different Google account*) and at every poll, a link whose calendar holds a live event carrying
  this environment's marker that the application records in another owner's calendar is no longer
  used, its owner's jobs are suspended (*Retry*), and its owner is told, with no customer value and
  no staff member named, until they unlink or relink another account. When a link is held so,
  every other link whose owner's recorded events were found in that calendar is held unused in the
  same way, and its owner is told in the same way, so the link that wrote them is held too. The
  hold sends nothing more into that calendar; events written there before it was found stay there.
  The erasure sweep is the one exception to the rule that another owner's visit's event is never
  deleted through that calendar's link (*Erasure and calendar events*, *Sweep by marker*).
- **An application event moved by the rep to another calendar** is absent from the primary
  calendar; it is handled as a deletion in Google (VIS-11).
- **Visit identifiers are never reused**, also after a restore from an earlier backup set, so an
  event's marker can never match a different visit. This binds the task that creates the visit
  table (EKO-4-01) and does not change ADR-0002.

### Change detection

- **App to Google: no later than about 1 minute.** A change to a visit writes its job in the same
  database transaction as the change. The worker is woken by `LISTEN`/`NOTIFY` and also reads the
  queue at least every 10 seconds, so the first attempt starts no later than 15 seconds after the
  commit, and the change is visible in Google no later than about 1 minute after it was saved,
  while Google is reachable and the owner's link works. Otherwise the visit is flagged
  Unsynchronised (*Retry*).
- **Google to app: no later than 5 minutes, or when a page is opened.**
  - **Polling.** For every owner with a working link, the worker reads the primary calendar at
    least every 2 minutes: it lists the live events carrying this environment's marker with the
    field selection above, compares them with the visits the application holds as synchronised in
    that calendar (their confirmed events, *A record counts once Google confirms it*), and applies
    changed date, time and duration (VIS-4, VIS-9). A confirmed event missing from the list is
    read directly by its identifier, and only a read that Google answered under a working link,
    stating the event deleted or absent, counts as a deletion in Google (VIS-11). A Google change is therefore visible in the application no later than 5 minutes
    after it was made.
  - **When a page is opened.** Opening a page of the application asks the backend to read the
    owner's own calendar at once, through the same job, at most once every 30 seconds per owner;
    the page shows the result when the read completes.
  - **When polling is unavailable** (Google unreachable, quota exhausted, a read failing): the
    5-minute bound is not met for that owner while it lasts; the application shows its last known
    data, no visit state changes and no prompt is raised, and the next cycle reads again. A failed
    or refused read never counts as a deletion.
- **No push notifications.** Google's push notifications are not used, so no public endpoint is
  served without a session and no notification channel needs renewing.
- **The application's own writes** are recognised by the `updated` instant Google returned for
  them and never count as Google changes; an event the application itself deleted never counts as
  a deletion in Google.
- **What does not flow back.** Title, location and description are not read back (*What is read
  back*), so changes to them in Google are ignored (VIS-4). A Google change the visit cannot hold
  (an all-day event, an end before its start) is not applied, and the application's own values are
  sent again.
- **Reassignment (CUS-10).** A future event moved to a new owner is deleted from the old owner's
  calendar and created in the new owner's with a new event identifier (*Retry*, *A new create
  uses a new identifier*). Until the deletion is carried out, the old event keeps its record,
  which names the old owner, and counts nowhere: it is no longer the visit's event, its changes in
  Google do not flow back, and it does not hold the old owner's link under *Ownership*, which
  concerns only an event the application records in another owner's calendar. The move itself is
  built by EKO-5-06.

### Conflict rule (VIS-5)

- When the same visit changes in the application and in Google before either change has been
  carried to the other side, **the later change wins**. Each change is compared by an instant: the
  application's change by the instant of its commit taken from the backend's clock
  (`backend/app/core/clock.py`, ADR-0002), Google's change by the event's `updated` instant. Both
  are compared as instants, so a change made in another time zone or across a daylight-saving
  change compares correctly.
- **Tie rule.** When the two instants are equal, the application's change wins and is sent to
  Google.
- **A deletion in Google** always puts the visit into Awaiting decision (VIS-11), whatever the
  instants: a later application change does not undo it. An application change made after the
  deletion stays on the visit, and rescheduling from the prompt creates the event with it.
- **A deletion or cancellation in the application** (VIS-10, CUS-9) is final against a Google
  change: the event is deleted in Google when the job runs.
- **Read before write.** Every update job first reads the visit's event by its identifier, with
  the field selection of *What is read back*, and applies this rule to what it reads before it
  writes. When the event carries a Google change (its start or end differs from the values the
  application last wrote to it, and its `updated` instant is not the application's own write)
  later than the application's change, the Google date, time and duration win and are applied to
  the visit (VIS-4, VIS-9), and the job writes only the values Google does not own. A change in
  Google to any other field (the title, a reminder, the colour) moves `updated` but is not a Google
  change for this rule, as it is not for polling (*What does not flow back*). Otherwise the job
  writes, conditional on the event version it read (the event's `etag`); a write Google refuses because the event changed since that read goes back to
  the read. Jobs suspended while access was lost run only after a first read of the owner's
  calendar at the link or relink (*Retry*).

### Retry of Unsynchronised visits (VIS-7)

- **Trigger.** A visit is flagged Unsynchronised when its change cannot be carried to Google: the
  owner has no working link, Google is unreachable or answers with an error, or the change is not
  confirmed by Google within 1 minute of the commit. The flag is cleared when Google confirms the
  visit's latest change.
- **Cadence.** A failed job is retried after 30 seconds, then with the wait doubling up to 15
  minutes, and then every 15 minutes for as long as the owner's link works. When Google answers
  that a rate limit is exceeded, the next attempt waits at least as long as Google asks.
- **While access is lost or the owner has no link** (expired, revoked, unlinked, never linked, or
  held unused after a relink), the owner's jobs are suspended, never discarded; no visit state
  changes and no prompt is raised (VIS-8, PRH-3). They run in order once the owner links or
  relinks, with the visits' latest data. Before they run, the worker reads the owner's calendar
  once as polling does, so a Google change made during the loss is compared under *Conflict rule*
  (*Read before write*). A link held unused under *Relinking a different Google account* or
  *Ownership* suspends its owner's jobs in the same way.
- **No second event.** A retried create uses the event identifier fixed before the first attempt;
  when Google answers that the identifier already exists, the job reads that event: when it is
  live and carries this environment's marker for that visit, it is taken as created; when it is
  cancelled, the earlier attempt reached Google and the event was deleted since, which counts as
  a deletion in Google (VIS-11). A retried create therefore produces no second event.
- **A new create uses a new identifier.** Every create other than a retry of the same create
  (rescheduling after a deletion in Google, a reassignment to a new owner, the creation in a new
  calendar after a confirmed relink, and any later create for the same visit) chooses a new event
  identifier (*Event content*), so it never meets an identifier Google already holds (A-8).
  Because the identifier carries the environment identifier, two environments never choose the
  same identifier for one visit.
- **Answers that end a job.** A job is not retried when Google's answer shows that a retry cannot
  succeed. An update answered that the event is deleted or absent ends, and the event is read
  directly by its identifier as polling does, so a deletion in Google counts under VIS-11
  (*Change detection*). A deletion answered that the event is already deleted or absent is done,
  except as *Erasure and calendar events* says for an unanswered create. Any other refusal of the
  request itself (Google rejecting a value, or refusing that one event) ends the job; the visit
  stays flagged Unsynchronised until a later job of the visit is confirmed, and Google's error
  reason code is logged (*Logging*). A removal ended this way (a deletion for a cancellation, an
  archiving, a reassignment or an erasure, the erasure sweep included) is recorded as not carried
  out (*Removals not carried out*). A rate-limit answer is retried as above, and a refused refresh
  is lost access (*Token storage*). An ended job never holds back the later jobs of its visit.
- **Removals not carried out.** A removal recorded as not carried out keeps its event record and
  the calendar it is due in. Until it is carried out, it is shown to the owner of that calendar
  and to the manager, as the date and time of the event and the owner's name, with no customer
  value, so that the event can also be deleted by hand. It is taken up again, as a new deletion job
  of that event, at each link or relink of that calendar and at least every 24 hours while its
  link works, and is carried out once Google confirms the deletion or answers that the event is
  deleted or absent. A removal recorded as not carried out for a calendar the owner left (*When
  the owner confirms another account*) is taken up again only when that calendar is linked again
  (*Relinking a different Google account*), and is never sent to another calendar.

### Erasure and calendar events

- **What erasure does in Google.** Erasing a customer (ADR-0005, *Erasure*) deletes from Google
  every application event of every visit of that customer, past and future events alike, in the
  calendar of every owner the event was created in — the current owner's, and the original owner's
  for past visits kept under CUS-10 — including any event whose deletion was still pending from a
  reassignment or an archiving. The application keeps, for each event it created, the owner in
  whose calendar the event lives until it is deleted there, so that erasure can reach it. CUS-9
  archiving removes only future events; erasure removes the past ones too.
- **How.** The erasure transaction queues one deletion job per such event, naming the event
  identifier and the calendar's owner only; the visits are stripped as ADR-0005 says. Each such job
  runs only after every earlier job of that event's visit has ended (*Background work*). A deletion
  that Google answers as already deleted or absent counts as done, except after a create of that
  identifier that Google never answered: then the job reads the event again at its next retry
  step (*Retry*), deletes it if it is there, and counts as done only when that read also finds it
  deleted or absent.
- **Sweep by marker.** The erasure transaction also queues, for each visit of the erased customer
  and in the calendar of each staff member who has a link, one deletion job that lists the live
  events carrying this environment's marker for that visit (A-9) and deletes every one whose
  identifier has the form the application chooses, whether or not the database records that
  identifier, so an event the application created after the backup set a restore used is reached
  too. Every event identifier the application chooses begins with a part derived from the
  environment identifier and the visit identifier alone, so the application can tell, for a given
  visit, whether an identifier is one it chose for it; an identifier Google gives to an event
  copied or made in Google has no such part (A-21). This sweep is the one exception to *Twins* and
  to *Ownership*: it deletes such an event in whichever calendar holds it, and nothing else. Like
  every deletion job queued by an erasure, it counts as a job of its visit for the order of
  *Background work*, and while that staff member's access is lost it waits, suspended, as *The
  owner's access lost* says.
- **In-flight sync.** A job of the erased customer's visit that is queued or running when the
  erasure commits sends none of the customer's data afterwards: it reads the stripped visit when it
  runs and sends nothing for it, and a request already sent when the erasure commits is followed by
  the deletion job of that event, which runs after it.
- **The owner's access lost.** A deletion due while the owner's access is lost waits, suspended,
  and is carried out at relink, unless the owner confirms another account, when it is recorded as
  not carried out (*Lost access*, *When the owner confirms another account*).
- **The re-apply at restore.** ADR-0005's re-apply carries out each erasure again on the restored
  application database, after `migrate` at ADR-0004 restore step 12 and before `backend` and the
  worker start at step 13 (ADR-0005, *Re-apply at restore*). The re-apply queues the same deletion
  jobs for every event the restored database records for the erased customers' visits, and the
  same sweep by marker for each of those visits (*Sweep by marker*). No sync of
  restored data runs before the re-apply: the worker starts only after it. A deletion of an event
  the original erasure already removed counts as done.
- **Events a restored database does not know.** An event carrying this environment's marker whose
  visit identifier the database does not hold (an event created after the backup set a restore used) is an **orphan**. At its owner's first read of
  the calendar after a restore, each orphan is deleted from Google, and the owner sees a notice
  listing the date and time of each removed event, and no customer value, so that they can plan
  those visits again. An orphan is the application's own event, so PRH-2 does not protect it; a twin
  of an orphan is never touched.
- **What erasure cannot reach.** A copy of an event made in Google (a twin) is not the
  application's event and is never deleted (PRH-2); its identifier is the one Google gave it, so
  the sweep by marker does not reach it either, and a customer's name in it stays in the rep's
  calendar.

### Lost access

For each kind of loss, no visit state changes and no reschedule prompt is raised (VIS-8, PRH-3),
no event counts as deleted in Google, and the owner sees the reconnect notice until they relink:

| Kind | Events already in Google | Removals due during the loss (cancellations, archiving, reassignment, erasure) |
|---|---|---|
| **Expired** (the 7-day testing-mode expiry, or another expiry Google applies) | left as they are | kept, suspended, carried out at relink |
| **Revoked** (by the rep in their Google account, or by Google) | left as they are | kept, suspended, carried out at relink |
| **Unlinked** (by the rep in the application) | left as they are; unlinking deletes no event (VIS-8) | kept, suspended, carried out at relink |

- **When relink never comes** (for example a rep who leaves the company and never relinks), the
  events in that rep's calendar, past and future, keep the customers' names, addresses and phones,
  and removals due there are never carried out. This decision does not accept that residual: it is
  a question for the GDPR impact assessment (ADR-0005, *Forward references*, on private Gmail
  calendars), which may require an offboarding removal while the
  link still works. Until then every environment holds only synthetic customer data (ADR-0005).
- **When the owner confirms another account** (*Relinking a different Google account*), every
  event the application records in that owner's earlier calendar is left there, out of reach: it
  is no longer tracked and never counts as deleted, and every removal due for it (a cancellation,
  an archiving, a reassignment or an erasure, due before the confirmation or after it) is recorded
  as not carried out and is never sent to the new calendar. The records of the earlier calendar
  are kept, tied to it, together with every removal recorded as not carried out for it, and are
  taken up again if that calendar is linked again (*Relinking a different Google account*,
  *Removals not carried out*). The events of the owner's planned
  visits are then created in the new calendar, each with a new event identifier (*Retry*). As
  with a calendar never relinked, the customers' names, addresses and phones left in the earlier
  account are not settled by this decision: they are a question for the GDPR impact assessment
  (ADR-0005, *Forward references*, on private Gmail calendars).
- A relink to a different Google account is otherwise handled under *OAuth flow and scope*.

### Logging

Within ADR-0005 *What may appear in logs*, which already forbids Google tokens and customer field
values in every log: the backend and the worker never log a Google request or response body, an
authorization code, the OAuth `state` or PKCE verifier, or the message of a Google error. They may
log the HTTP status, Google's error reason code, the job and record identifiers and the subject.

### Changes to accepted decisions

This decision changes no accepted decision: not ADR-0001, ADR-0002, ADR-0003, ADR-0004 or ADR-0005,
by edit. It adds one addendum foreseen by an accepted decision: the `worker` service is recorded in
ADR-0004's addendum of 2026-10-27, as ADR-0004 *Composition and placement* (*Background work*)
requires of ADR-0006, and no other change is made to ADR-0004. It works within ADR-0001's single backend
language and image and its layer rules, ADR-0002's database-backed queue and instants, ADR-0003's
backend session, `Origin` check, Keycloak without identity providers and the rule that the
application holds no staff e-mail address, ADR-0004's one origin, secret rules, migration rules and
restore steps, and ADR-0005's rule on data sent to Google, its categories, its logging rules and
its re-apply. No deviation from an accepted decision is proposed.

### Items forwarded to this decision

Line numbers are those of each source as accepted (task base 4273cb3).

| Source | Line | What it forwards | Decided in |
|---|---|---|---|
| ADR-0001 | l.126 | Google Calendar adapters in `integrations` | *Who links, and what linking is not*; *Event content* |
| ADR-0001 | l.172-176 | the background-work mechanism | *Background work* |
| ADR-0001 | l.185 | the Google Calendar integration and the background-work mechanism | this whole decision; *Background work* |
| ADR-0002 | l.123 | whether background work uses the database-backed job queue | *Background work* |
| ADR-0002 | l.136 | storage and encryption of Google tokens; the background-work mechanism | *Token storage*; *Background work* |
| ADR-0003 | l.269 (sentence l.269-270) | linking a Google account for the calendar, outside Keycloak | *Who links, and what linking is not*; *OAuth flow and scope* |
| ADR-0003 | l.318 | Google account linking, outside Keycloak | *Who links, and what linking is not*; *OAuth flow and scope* |
| ADR-0004 | l.61-64 | the background-work mechanism; a worker service and its addendum | *Background work* |
| ADR-0004 | l.200 | the Google OAuth client secret and the Google token encryption key | *Secrets* |
| ADR-0004 | l.562-563 | the background-work mechanism and any worker service; the Google secrets; the Google callback path on `<app-host>` | *Background work*; *Secrets*; *OAuth flow and scope* |
| ADR-0004 | l.585-586 | the same, as a forward reference to EKO-1-05 | *Background work*; *Secrets*; *OAuth flow and scope* |
| ADR-0005 | l.304 (bullet l.301-304) | what erasure does to app-created events, past ones included; what happens when the owner's Google access is lost | *Erasure and calendar events*; *Lost access* |
| ADR-0005 | l.375 (sentence l.374-375) | what the re-apply at restore does to app-created events | *Erasure and calendar events* |
| ADR-0005 | l.446-448 | the list of each field sent; how Google tokens are stored; erasure and the re-apply, past events included | *Event content*; *Token storage*; *Erasure and calendar events* |
| ADR-0005 | l.523-525 | the same, as a forward reference to EKO-1-05 | *Event content*; *Token storage*; *Erasure and calendar events* |

### Assumptions about Google (unproven)

None of these is proven in this repository. Each rests on the roles' knowledge of Google's public
documentation and policy, not on a test. Integration tests against a Google test double (EKO-5)
prove the application's side only; Google's side is proven only by a dated manual check against a
real test account, and by the pilot. A task that finds an assumption false stops and the affected
rule returns to the human as an addendum to this decision.

| # | Assumption | Rests on | Rule that depends on it |
|---|---|---|---|
| A-1 | In testing mode, a grant for a non-basic scope expires 7 days after it was given | brief section 5 and section 8; Google's OAuth documentation on refresh-token expiry | *Testing mode* |
| A-2 | Testing mode admits at most 100 test users, entered by their Google account in the project | brief section 5; Google's consent-screen documentation | *Testing mode* |
| A-3 | Private Gmail accounts need the external user type; the internal type needs a Workspace organisation | Google's consent-screen documentation | *Testing mode* |
| A-4 | `calendar.events.owned` exists and covers events of the rep's primary calendar; it, and `calendar.events`, are sensitive, not restricted, scopes, so verification needs no third-party security assessment | Google's list of Calendar API scopes and its verification policy | *OAuth flow and scope*, *Verification path* |
| A-5 | Verification needs a verified domain, a home page and privacy policy under it, a scope justification and Google's review of days to weeks, and it ends both testing-mode limits | brief section 5; Google's verification documentation | *Verification path* |
| A-6 | The web server flow supports PKCE, offline access with a refresh token, a refresh token issued again when consent is requested, a token response naming the granted scopes, a revocation endpoint, and `invalid_grant` on a refused refresh; granular consent may grant fewer scopes than asked | Google's OAuth 2.0 documentation for web server applications | *OAuth flow and scope*, *Token storage* |
| A-7 | Without `openid`, `email` or `profile`, Google returns no ID token and no e-mail address | Google's OpenID Connect documentation | *OAuth flow and scope* |
| A-8 | An event can be inserted with an identifier the client chooses, within the characters and length Google allows for one; inserting an existing identifier is refused as a conflict; a deleted event's identifier cannot be used again, and reading it shows the event cancelled | Calendar API `events.insert` reference | *Event content*, *Retry*, *Conflict rule* |
| A-9 | Private extended properties are set through the API, cannot be set in Google Calendar's own interface, and can be filtered on in `events.list`; whether Google's "duplicate" copies them is unknown | Calendar API extended-properties guide | *Recognising the application's events*; *Erasure and calendar events* (*Sweep by marker*) |
| A-10 | Partial-response field selection limits the fields Google returns, the creator's and organiser's e-mail address included | Google APIs' standard `fields` parameter | *What is read back* |
| A-11 | With no attendee and `sendUpdates` `none`, Google sends no invitation or notification to anyone | Calendar API `events.insert`/`update`/`delete` reference | *Event content* |
| A-12 | An event's `updated` is the instant of its last change, returned also in the response to the application's own write | Calendar API event resource | *Change detection*, *Conflict rule* |
| A-13 | Reading a deleted event by its identifier answers that it is cancelled or absent; an event moved to another calendar is absent from the primary calendar; an update of a deleted event is answered as not found or gone, and a rate-limit refusal is told apart from other refusals by Google's reason code | Calendar API `events.get`, `events.update` and `events.move` reference; Calendar API error reference | *Change detection*, *Retry* |
| A-14 | The project's default Calendar API quota and per-user rate limits hold about ten owners read every 2 minutes (about 7,200 list requests a day, plus writes and direct reads), and an exceeded limit is answered with a rate-limit error that may name a wait | Calendar API quota documentation | *Change detection*, *Retry* |
| A-15 | `dateTime` with `timeZone` `Europe/Warsaw` is stored and returned as the same instant | Calendar API event resource | *Event content* |
| A-16 | An SPA route under `<app-host>` can be registered as the OAuth client's authorised redirect URI, and developer environments can register a local address | Google's OAuth client configuration documentation | *OAuth flow and scope* |
| A-17 | An event's `private` visibility hides its details from people the calendar is shared with | Calendar API event resource | *Event content* |
| A-18 | Rotating the client secret in the Google Cloud project allows the new and old secret for a short overlap, or else costs a short loss of sync; an old secret deleted in the project no longer refreshes any grant | Google Cloud console documentation | *Secrets* |
| A-19 | An event update can be made conditional on the event's `etag`, and Google refuses it when the event changed since that version | Calendar API reference; Google APIs' ETag support | *Conflict rule* (*Read before write*) |
| A-20 | A create request Google did not answer has taken effect, if it ever does, by the time of the next retry step (at least 30 seconds later) | none beyond general experience of HTTP APIs; not documented by Google | *Erasure and calendar events* (*How*) |
| A-21 | An event identifier the client chooses is stored and returned unchanged; an event copied or made in Google's own interface gets an identifier Google chooses, which in practice never begins with the part the application derives for a visit | Calendar API `events.insert` reference on client-chosen identifiers | *Erasure and calendar events* (*Sweep by marker*) |

## Options considered

At gate 1 (2026-10-27) the human chose option A in every table below; the chosen option is the
one in *Decision*. The other rows are the alternatives considered, and their cost and what they
close off are why they lost.

### Change detection (G-2)

| Option | Cost | Closes off |
|---|---|---|
| **A. Polling every 2 minutes, filtered to marked events, with a direct read of each missing tracked event** (chosen at gate 1, 2026-10-27) | More requests than a change stream; relies on A-9, A-13, A-14. | Nothing: B or C can be added later by addendum. |
| B. Polling with Google's incremental change stream (sync token) | The stream cannot be filtered by marker, so the adapter receives every changed event of the rep's private calendar (its identifier, status and times, even with field selection): staff personal data ADR-0005 does not list, needing an ADR-0005 addendum. | Keeping ADR-0005 unchanged in this task. |
| C. Push notifications, with polling as fallback | A public backend endpoint served without a session for Google's calls, which ADR-0003's 401 rule does not except; notification channels to renew; the stream of B behind it. | Keeping every backend endpoint behind a session. |

### Background mechanism (G-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. A `worker` service from the backend image, with a queue in PostgreSQL** (chosen at gate 1, 2026-10-27) | One more service and an ADR-0004 addendum (foreseen by ADR-0004); its connections in the application role's budget. | Nothing. |
| B. A scheduler inside the `backend` web process | No new service; the jobs stop at every `backend` restart and replacement, and several web workers each run the scheduler unless they lock in the database. | Running sync independently of the web process. |
| C. A message broker (for example Redis or RabbitMQ) | A new image and service beyond ADR-0004's foresight, and a second state store to back up: a deviation from ADR-0004. | Keeping ADR-0004's composition and backup scope. |

### Callback and session binding (G-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. Redirect to an SPA route; completion by an authenticated same-origin request bound to the starting session** (chosen at gate 1, 2026-10-27) | The authorization code passes through the page's JavaScript and location (removed at once; useless without the server-held verifier and secret). | Nothing. |
| B. A backend callback served without a session, bound by a `SameSite=Lax` link-transaction cookie, parking the code; completion as in A | A second session-less backend endpoint beside the login callback, which ADR-0003's 401 rule does not except: needs the human's ruling or an ADR-0003 addendum. | Keeping every non-login backend endpoint behind a session. |
| C. A backend callback that completes the link on the link-transaction cookie alone | As B, and the grant is bound only to the subject recorded at the start, not to a live session at completion. | As B. |

The session cookie is `SameSite=Strict` (ADR-0003), so the browser does not send it on Google's
cross-site redirect; every option needs a second step or a second cookie.

### Scope (G-5)

| Option | Cost | Closes off |
|---|---|---|
| **A. `calendar.events.owned`, with a stop if EKO-5-01 finds it unavailable** (chosen at gate 1, 2026-10-27) | Relies on A-4 for a narrower, newer scope. | Nothing. |
| B. `calendar.events` | Reaches events of every calendar the rep can access, shared calendars included. | The narrower grant. |

### Conflict rule (G-6)

| Option | Cost | Closes off |
|---|---|---|
| **A. Later change wins by instant; a tie goes to the application; a Google deletion always becomes Awaiting decision; an application cancellation is final** (chosen at gate 1, 2026-10-27) | None. | Nothing. |
| B. As A, but a tie goes to Google | None. | The application as the side of record on a tie. |
| C. Later wins also against deletions | A later app edit silently undoes a deletion in Google. | Brief section 1: no deletion in Google goes unnoticed. |

### Erasure in Google (G-7)

| Option | Cost | Closes off |
|---|---|---|
| **A. Delete every event of the customer's visits, past and future, in every owner's calendar** (chosen at gate 1, 2026-10-27) | Reps lose the past entries from their calendars. | Nothing. |
| B. Keep the events but replace title, location and description with neutral text | A further update per event; times stay in the rep's calendar. | Nothing, but every event of the customer stays as a trace. |

### Orphans after a restore (G-8)

| Option | Cost | Closes off |
|---|---|---|
| **A. Deleted from Google at the owner's first read after the restore; the owner told the dates and times** (chosen at gate 1, 2026-10-27) | Reps lose the calendar entries of the visits the restore lost. | Nothing. |
| B. Left in Google, never touched | None. | Erasure of those events: no later erasure can find them. |

### Never-relinked calendars (G-9)

| Option | Cost | Closes off |
|---|---|---|
| **A. The residual named for the GDPR impact assessment; nothing more now** (chosen at gate 1, 2026-10-27) | Customer data stays in a leaver's calendar; acceptable only while data is synthetic. | Nothing: B stays possible. |
| B. An offboarding removal of a leaver's events while the link works, started by the manager | A new feature in EKO-5; past events vanish from a leaver's calendar. | Nothing. |

### Google token key at a restore (G-10)

| Option | Cost | Closes off |
|---|---|---|
| **A. Taken from its master copy, not replaced** (chosen at gate 1, 2026-10-27) | A stolen backup set and the key together give the refresh tokens of its time. | Nothing. |
| B. Replaced at every restore | Every rep relinks after a restore; a new restore step, so an ADR-0004 addendum. | Keeping ADR-0004's restore steps unchanged. |

### Event visibility (G-11)

| Option | Cost | Closes off |
|---|---|---|
| **A. `private`** (chosen at gate 1, 2026-10-27) | People the rep shares the calendar with see only a busy slot. | Nothing. |
| B. The calendar's default | Customer names visible to anyone the rep shares the calendar with. | Nothing. |

### Relinking a different account (G-12)

| Option | Cost | Closes off |
|---|---|---|
| **A. Check the newly linked calendar for the owner's events before use** (chosen at gate 1, 2026-10-27) | One filtered list of the calendar's marked events at each link and relink, compared with every event recorded for the owner, past ones included; when none is found, the owner's choice decides (fix round 1, 2026-10-27: the gate-1 text read "a few direct reads at each relink; an owner with no planned synchronised visit is not checked"). | Nothing. |
| B. Store a keyed hash of the Google account's primary-calendar identifier | The identifier is the rep's Google e-mail address; a value derived from it sits against ADR-0003's "no staff e-mail address" and ADR-0005's rule that a derived value has its source's category. | Keeping ADR-0003 unchanged. |
| C. No check | A relink to another account makes every event look deleted: a mass of Awaiting-decision prompts. | Brief section 1's reliability of the deletion signal. |

### Classification of what the link stores (Q-2)

| Option | Cost | Closes off |
|---|---|---|
| **A. Every stored item under an existing ADR-0005 category or "not personal data"; a task that finds an item fitting none stops and returns it to the human as an ADR-0005 addendum** (chosen at gate 1, 2026-10-27) | No Google account identifier can be stored (G-12 B is excluded). | Nothing. |
| B. An ADR-0005 addendum allowed in this task | A second accepted decision changed in this task, reviewed for personal data alongside this one. | Checking byte for byte that this task changes ADR-0005 in no way. |

### The contact phone in the event (Q-3)

| Option | Cost | Closes off |
|---|---|---|
| **A. The phone marked primary; no phone when none is primary or the primary contact is an e-mail address** (chosen at gate 1, 2026-10-27) | Some events carry no phone. | Nothing. |
| B. The phone marked primary, else the first phone entered | Which phone reaches Google depends on entry order; more customers' phones in accounts the company does not control. | Nothing. |

### Where orphans after a restore are decided (Q-4)

| Option | Cost | Closes off |
|---|---|---|
| **A. In this decision, as part of what the re-apply at restore does** (chosen at gate 1, 2026-10-27) | None beyond G-8. | Nothing. |
| B. Out of scope, forwarded to EKO-1-08 (#36) | Customer data in orphans escapes erasure until that task decides it. | Nothing, but the risk stays open with no rule. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0006-C1 | A test of linking: the authorization request names exactly the decided scope and no `openid`, `email` or `profile`; a completion from a session other than the one that started the transaction, or with another `state`, is refused and stores nothing; a second completion of one transaction is refused; a grant holding any other scope or lacking the scope is refused and its token revoked; a link transaction older than 10 minutes is refused. |
| ADR-0006-C2 | A test: a staff member with no link logs in and uses the application; their visits are saved and flagged Unsynchronised. |
| ADR-0006-C3 | A test of storage: the link table holds the refresh token only as ciphertext, no access token, no Google account identifier or e-mail address; the Google token encryption key is read only from the environment and appears in no table and in no backup set; with the key replaced, every link becomes "access lost" and its token is kept; with the original key value back, every such link works again; a relink replaces the kept token. |
| ADR-0006-C4 | A test: at unlink the link is never used again, a revocation request reaches the test double, and the token is deleted only once the double confirms the revocation or answers the grant invalid; a revocation the double fails is retried; a stored token is deleted at a refused refresh; at unlink, a token the key in use cannot decrypt is deleted, no revocation request reaches the double, and the owner's notice holds no customer value. |
| ADR-0006-C5 | Against the Google test double, every insert and update body holds only the fields of *Event content*, no attendee, and `sendUpdates` `none`; the description holds only the primary phone, or nothing when none is primary or the primary contact is an e-mail; no request URL or query string holds a customer field value; every request names a field selection without `summary`, `location`, `description`, attendees, creator or organiser. |
| ADR-0006-C6 | Against the test double: an event without the marker, an event with another environment's marker, a twin carrying a known visit's marker, and another owner's event are never changed, deleted or imported, and count nowhere; an event carrying the marker and the stored identifier is synchronised; a hand-made event with an application event's title, location and description is not recognised. |
| ADR-0006-C7 | With the clock fixed, against the test double: an application change reaches the double no later than 60 seconds after its commit; a change in the double is applied no later than 5 minutes after it, and at once when a page is opened; a failed or refused read changes no visit; the application's own write does not set Moved. |
| ADR-0006-C8 | A test of VIS-5: of two changes before either is carried over, the later instant wins; equal instants give the application's change; a Google deletion gives Awaiting decision also when an application change is later; an application cancellation deletes the event also when the Google change is later. |
| ADR-0006-C9 | A test of retry: a failed create is retried with the stated cadence and produces one event when the first attempt succeeded at Google with a lost response; jobs of an owner whose access is lost are kept and run in order at relink; no visit state changes and no prompt is raised while access is lost. |
| ADR-0006-C10 | Once erasure exists: erasing a customer queues the deletion of every event of its visits, past and future, in every owner's calendar it lives in; a job of that customer's visit queued before the commit sends no customer value; the re-apply at restore queues the same deletions; a deletion answered "already deleted" counts as done. |
| ADR-0006-C11 | A test of a restore from an earlier database: an event carrying this environment's marker and an unknown visit identifier is deleted at the owner's first read, and the owner's notice lists its date and time and no customer value. |
| ADR-0006-C12 | A test of relink to another account: when the new calendar holds none of the owner's recorded events, past and planned, the link is held unused, no visit state changes and no prompt is raised until the owner chooses; an owner whose recorded events are all past is checked too; choosing "same calendar" makes each recorded event the double reports deleted count under VIS-11; when some recorded events are found, the ones not found are read directly; only confirmed events are compared; relinking a calendar the owner left by confirming another account is used with no choice offered, takes its records up again and creates no second event for a planned visit whose event it holds. |
| ADR-0006-C13 | In the rendered composition (once the ADR-0004 addendum adds it), the `worker` service uses the backend image, its command and entrypoint contain no `alembic upgrade`, it depends on `migrate` with condition `service_completed_successfully`, and it publishes no port; a test starts the worker against a database at an older revision than its code's head and it exits non-zero without working and without changing the schema. |
| ADR-0006-C14 | A test makes the test double answer errors whose messages carry a marker value; the marker, the authorization code, the `state` and every token appear in no log line of `backend` or the worker. |
| ADR-0006-C15 | Manual `<YYYY-MM-DD>`: against a real Google test account in testing mode, linking with the decided scope works, an application event appears with the decided content, no notification reaches any address, a deletion in Google becomes Awaiting decision within 5 minutes, and the grant's expiry after 7 days shows the reconnect notice with no visit state change. |
| ADR-0006-C16 | Against the test double: rescheduling after a deletion in the double, a reassignment from A to B and back to A, and a confirmed relink each create a live event under an identifier not used before for that visit; a create answered "already exists" for a cancelled event gives Awaiting decision, not "created"; two environments create events for one visit identifier under different identifiers. |
| ADR-0006-C17 | Against the test double: the event record exists before the first create attempt; an erasure committed while that visit's create is unanswered or running queues a deletion that runs only after that job has ended; a deletion answered "absent" after an unanswered create reads the event again at the next retry step and deletes it when it appears. |
| ADR-0006-C18 | With the clock fixed, against the test double: an update job reads the event first; a Google change later than the application's change wins and is not overwritten, also for a change made while access was lost and replayed at relink; a conditional write the double refuses for a changed `etag` goes back to the read; an event whose title or reminder alone changed in the double, with start and end as the application last wrote them, does not win over the application's change, also when its `updated` instant is later. |
| ADR-0006-C19 | Against the test double: an update answered "not found" or "gone" is not retried, the event is read directly and the deletion counts under VIS-11, and a later create of that visit runs; an update answered with another non-rate-limit refusal ends, the visit stays Unsynchronised, and the next job of that visit runs. |
| ADR-0006-C20 | Against the test double: a link or relink whose calendar holds a marked event recorded in another owner's calendar is held unused, no choice lifts the hold, and the owner's notice holds no customer value and names no staff member; the same holds when such an event first appears at a poll; when the hold falls on one link, every other link whose owner's recorded events were found in that calendar is held too, the link that linked it first included; a reassignment from A to B leaves A's link working, and the old event in A's calendar is deleted through it and never applied to the visit. |
| ADR-0006-C21 | A test of a confirmed relink to another account: no event of the earlier calendar counts as deleted, no removal due for one is sent to the new calendar, each such removal is recorded as not carried out, and the planned visits' events are created in the new calendar; when the earlier account is then linked again, each removal recorded as not carried out for it is carried out there, and no planned visit gets a second event in it. |
| ADR-0006-C22 | A test of key replacement on suspected compromise: every grant on record is revoked at the test double before the key value changes. |
| ADR-0006-C23 | Manual `<YYYY-MM-DD>`: in the Google Cloud project, after a client-secret rotation that deleted the old secret, a refresh with the old secret is refused (A-18). |
| ADR-0006-C24 | Against the test double: a staff member whose only records are creates not yet confirmed (never sent, suspended, or never answered) links for the first time and the link is used with no choice offered; at a relink after lost access, a visit whose create was suspended is neither read directly nor counted as deleted, and its create then runs; a create waiting for its next retry step is not read directly by a poll and gives no Awaiting decision. |
| ADR-0006-C25 | Against the test double: a deletion for an erasure, a cancellation, an archiving and a reassignment, each answered with a refusal that is not a rate limit, is recorded as not carried out, shown to the calendar's owner and the manager with no customer value, taken up again at the next relink and after 24 hours, and no longer shown once the double accepts it. |
| ADR-0006-C26 | Against the test double: after a restore from a set taken before an event was created for a visit the restored database holds, erasing that visit's customer deletes that event in the calendar of each linked staff member, the re-apply at restore does the same, and an event carrying the same marker under an identifier the double chose is not deleted. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->
