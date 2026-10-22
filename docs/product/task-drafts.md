# Task drafts — MVP

Draft, not the plan. Sources: `docs/product/project-brief.md` (requirement identifiers) and the
design prototype `docs/prototype/P2/` (screens, components, state rules in `HANDOFF.md`). The
identifiers below are **proposals**: one is reserved in `docs/PLAN.md` (its own commit) and gets a
Story Issue only when the human accepts the draft. The shape of EKO-1 can still change at gate 1
of #6.

Each draft follows the plan entry format: a title that is an action, *Done when* (an observable
condition), explicit out of scope. "Req" lists the brief's requirements the task carries;
"P2" names the prototype material to reuse; "After" lists dependencies.

Common rule for every product task: the authorization and validation criteria are proven on the
server (a contrast test per rule), never only in the UI — P2's UI filtering is not a security
boundary (`P2/HANDOFF.md`). All test data is synthetic.

---

## EKO-1 — Foundations (decisions and a proven skeleton; no product features)

- **EKO-1-01** — Record the stack and persistence decisions (ADR-0001 stack, ADR-0002 database
  and migration tool). *Already in the plan — Issue #6.*

- **EKO-1-02** — Record the identity decision (ADR-0003).
  *Done when:* ADR-0003 is Accepted and fixes: the identity server (Keycloak preferred), how
  roles rep / manager / administrator reach the backend, account deactivation, password reset
  over the company SMTP mailbox, and that accounts never depend on Google.
  **Out of scope:** any implementation; Google account linking (EKO-1-05).
  Req: ACC-1–3. After: EKO-1-01.

- **EKO-1-03** — Record the deployment and backup decision (ADR-0004).
  *Done when:* ADR-0004 is Accepted and fixes: container runtime and composition, cloud-agnostic
  constraints, HTTPS exposure under a company domain, secret handling, daily off-server database
  backup and a restore procedure; the company IT department is named as operator.
  **Out of scope:** provisioning the real server; the domain (the human provides it later).
  Req: brief §5 Hosting. After: EKO-1-01.

- **EKO-1-04** — Record the personal-data handling decision (ADR-0005).
  *Done when:* ADR-0005 is Accepted and names the files/modules that hold customer personal data,
  what is logged and what never is, archiving vs. erasure, and that only synthetic data is used
  until the GDPR impact assessment; `docs/architecture/architecture-sensitive-paths.md` lists
  those paths.
  **Out of scope:** the GDPR impact assessment itself (after the MVP); erasure (later).
  Req: brief §5 Personal data; TEAM-CONTRACT hard stop 6. After: EKO-1-01.

- **EKO-1-05** — Record the Google Calendar integration decision (ADR-0006).
  *Done when:* ADR-0006 is Accepted and fixes: OAuth flow and scope, token storage and
  encryption, how app-created events are recognised, change detection (push notifications vs.
  polling) able to meet VIS-6, conflict rule VIS-5, retry of unsynchronised visits, and the
  testing-mode limits (7-day expiry, 100 users) with the path to Google verification.
  **Out of scope:** implementation; Google verification itself (later).
  Req: VIS-1–8, PRH-1–3. After: EKO-1-01, EKO-1-02.

- **EKO-1-06** — Build a walking skeleton that runs in containers.
  *Done when:* one compose command starts backend, frontend, database and identity server
  locally; a test proves the backend health endpoint answers and the first migration applies on
  an empty database; CI runs backend and frontend tests on every PR; the capability register
  lists these capabilities as proven with links to the tests.
  **Out of scope:** any product feature; production server setup.
  P2: none. After: EKO-1-01–1-04.

- **EKO-1-07** — Build the frontend shell and shared UI components from the chosen prototype
  (P2 assumed below; see "Points for the human", 2).
  *Done when:* the app shell (navigation, header, responsive collapse at 1000px / 700px) and the
  shared components Button, IconButton, StatusBadge, Field, ConfirmDialog, EmptyState and Toast
  exist in `frontend/` with P2's design tokens and SVG assets; component tests prove StatusBadge
  always renders text or an icon (never colour alone) and ConfirmDialog shows the exact
  consequence text; UI copy is in Polish.
  **Out of scope:** feature screens; P2's global state, innerHTML rendering and persona switch
  (must not be copied).
  P2: `styles/tokens.css`, `styles/app.css`, `src/components.js`, `assets/`, `HANDOFF.md`
  component table. After: EKO-1-06.

## EKO-2 — Access

- **EKO-2-01** — Require login for the whole application.
  *Done when:* a test proves every API operation except login answers 401 without a valid
  session (contrast: the same call with a valid session succeeds); the frontend redirects an
  unauthenticated user to login; a user with no Google account linked can log in.
  **Out of scope:** user administration screens (administrator uses the identity-server console).
  Req: ACC-1, ACC-2. After: EKO-1-02, EKO-1-06.

- **EKO-2-02** — Carry roles and account state into every request.
  *Done when:* tests prove: a deactivated account cannot log in and its data stays; the backend
  knows the caller's role (rep / manager / administrator) and user id; one person holding manager
  and administrator roles gets both; there is no self-registration path.
  **Out of scope:** per-resource ownership rules (each feature task proves its own).
  Req: ACC-3. After: EKO-2-01.

## EKO-3 — Customers

- **EKO-3-01** — Let a rep create and view their own customers with contacts.
  *Done when:* tests prove: a customer is saved with name and country only (default Poland);
  any number of phones and e-mails, each with an optional note, one marked primary; phones
  stored in international format (default +48); a malformed e-mail is rejected; a rep reading
  another rep's customer by id gets a denial that discloses no data (contrast: the manager gets
  the record).
  **Out of scope:** address/NIP validation (EKO-3-02), duplicates (EKO-3-03), list search
  (EKO-3-04).
  Req: CUS-1, CUS-2, CUS-8, ACC-4, PRH-4. P2: CustomerSheet, ContactEditor. After: EKO-2-02,
  EKO-1-07.

- **EKO-3-02** — Validate Polish addresses and tax IDs.
  *Done when:* server tests prove: postcode `00-000` enforced for Poland; voivodeship from the 16;
  a county outside the chosen voivodeship is rejected; both optional but valid when given;
  foreign postcode and tax ID free-form; Polish NIP normalised (hyphens, spaces, `PL`) and
  checksum-validated.
  **Out of scope:** postal-code-to-town lookup.
  Req: CUS-3, CUS-4, CUS-5. P2: `src/domain.js` NIP/postcode rules and tests. After: EKO-3-01.

- **EKO-3-03** — Block duplicate NIPs and warn about likely duplicates without leaking data.
  *Done when:* tests prove: a second customer with an existing NIP is blocked company-wide; the
  rep's message names neither the customer nor its owner, the manager's links to the existing
  customer; same phone/e-mail or same name+town (case- and edge-space-insensitive) warns without
  blocking; a rep is warned only within own customers, the manager company-wide.
  **Out of scope:** merging duplicates.
  Req: CUS-6, CUS-7, ACC-8, PRH-4. After: EKO-3-02.

- **EKO-3-04** — Let users find customers in a list.
  *Done when:* a rep's list shows only own customers and filters active/archived; search matches
  name, town and contact; the manager's list shows all customers with an owner filter; tests
  prove search never returns another rep's customer to a rep.
  **Out of scope:** export.
  Req: ACC-4, PRH-4. P2: Customers screen. After: EKO-3-01.

- **EKO-3-05** — Let users edit, archive and restore customers.
  *Done when:* tests prove: owner and manager can edit customer data, another rep cannot;
  archiving asks for confirmation showing the consequences, hides the customer from the active
  list and can be undone by restore; restore does not reopen anything cancelled by archiving;
  archiving changes no other customer's data.
  **Out of scope:** the effect on visits and actions (EKO-4-06), erasure (later).
  Req: CUS-9 (customer part), ACC-5, PRH-5. P2: archive/restore flow. After: EKO-3-01.

- **EKO-3-06** — Provide a seed script with synthetic customers.
  *Done when:* an operator script loads a synthetic dataset (several reps, ~200 customers each)
  into an environment; every record passes CUS-2–CUS-8; an invalid record is reported and not
  loaded; running it twice creates no duplicates (test).
  **Out of scope:** real customer data; Excel import (later).
  Req: SEED-1. P2: `src/fixtures.js` as a style reference only. After: EKO-3-03.

- **EKO-3-07** — Let the manager reassign customers between reps.
  *Done when:* tests prove: only the manager can reassign (contrast: a rep is denied); single and
  bulk; the customer, its future visits and open actions move to the new owner; past visits keep
  their owner and notes their author; no other customer changes; future visits are marked for
  calendar transfer.
  **Out of scope:** the actual move between Google calendars (EKO-5-06).
  Req: CUS-10, ACC-5, PRH-5. P2: reassignment dialog. After: EKO-4-04.

## EKO-4 — Visits, notes and actions (without Google)

- **EKO-4-01** — Let a rep plan visits and see their agenda.
  *Done when:* tests prove: a visit belongs to one customer and one owner; a rep can plan only for
  own customers (contrast: another rep's customer is denied); a visit is Planned until its end
  time passes and Held afterwards, derived, never stored; times are stored as instants and
  displayed/filtered by Europe/Warsaw days; nonexistent/ambiguous DST local times are rejected;
  the "My day" view shows the next visit, the day's agenda and a five-day strip; a per-visit
  address can override the customer's.
  **Out of scope:** Google sync (EKO-5), recurring visits (later).
  Req: VIS-1 (app side), ACC-7, glossary visit states. P2: My day, Visits (week/all), DateStrip,
  VisitCard. After: EKO-3-01.

- **EKO-4-02** — Let the owner move and cancel visits.
  *Done when:* tests prove: changing start date/time sets Moved at most once; changing place,
  duration or description does not; deleting asks reschedule (Moved) or cancel (Cancelled); a
  held visit can be marked "did not happen" and becomes Cancelled; only the visit's owner can
  move or cancel (contrast: the manager is denied).
  **Out of scope:** changes coming from Google (EKO-5-03).
  Req: VIS-9, VIS-10, VIS-13, ACC-5. P2: move/cancel dialogs. After: EKO-4-01.

- **EKO-4-03** — Let users write notes on visits and customers.
  *Done when:* tests prove: a note can be added to a visit in any state and is linked to its
  customer; only its author can edit it (contrast: the manager cannot edit a rep's note); the
  manager can add a note to any customer, shown as the manager's; cancelling or deleting a visit
  keeps its note.
  **Out of scope:** rich text, revision history.
  Req: NOT-1, NOT-2, VIS-12, ACC-5, ACC-6, PRH-6. P2: NoteCard, NoteForm. After: EKO-4-01.

- **EKO-4-04** — Let users create actions from notes and move them through statuses.
  *Done when:* tests prove: an action exists only from a note; description required, due date
  optional; owner defaults to the note's author, and for a manager-created action is the
  customer's owner; allowed transitions only (others rejected by the server); every status change
  records who made it (full history, not only the latest); the manager can close (Done /
  Cancelled) but not edit a rep's action; manager-made changes are shown as the manager's;
  Overdue is computed.
  **Out of scope:** several actions per note in one form if P2's single-action form is kept —
  decide at gate 1.
  Req: ACT-1–3, ACC-5, ACC-6, PRH-6. P2: FollowUpCard, Follow-ups screen. After: EKO-4-03.

- **EKO-4-05** — Show in-app reminders for due actions.
  *Done when:* after login the user sees a count and a list of their actions due today or earlier
  and not Done/Cancelled; actions without a due date never appear; test with a frozen clock in
  Europe/Warsaw covers the day boundary.
  **Out of scope:** e-mail reminders (later).
  Req: ACT-4. P2: follow-up column and count. After: EKO-4-04.

- **EKO-4-06** — Apply archiving to a customer's visits and actions.
  *Done when:* tests prove: archiving cancels only that customer's future visits (without the
  reschedule prompt) and sets its open actions to Cancelled; past visits and notes remain;
  restore reopens none of them; no other customer's records change.
  **Out of scope:** removal from Google (covered by EKO-5-02 once sync exists).
  Req: CUS-9, PRH-5. After: EKO-3-05, EKO-4-04.

## EKO-5 — Google Calendar sync (basic, two-way)

- **EKO-5-01** — Let a rep link and relink their Google account.
  *Done when:* a rep links a private Gmail account for the calendar only; the token is stored per
  ADR-0006; the app works with no account linked; an expired or revoked link shows a persistent
  "reconnect" notice until relinked; unlinking deletes no Google events.
  **Out of scope:** using Google for login.
  Req: ACC-2, VIS-8 (notice). P2: Google Calendar screen, SyncNotice. After: EKO-1-05, EKO-4-01.

- **EKO-5-02** — Mirror app visits into the owner's Google Calendar.
  *Done when:* integration tests against a Google test double prove: create/move/cancel in the
  app creates/updates/deletes the event in the primary calendar; event title `Wizyta: <customer>`,
  location the visit address, description the contact phone; no attendee and no invitation is
  ever sent; when Google is unavailable or not linked the visit is saved as Unsynchronised and
  synchronised later; a manual check against a real test account is recorded.
  **Out of scope:** reading changes from Google (EKO-5-03).
  Req: VIS-1, VIS-3, VIS-6 (app→Google), VIS-7, PRH-1. After: EKO-5-01, EKO-4-02.

- **EKO-5-03** — Bring Google-side changes back into the app.
  *Done when:* tests prove: only app-created events are read — other events never appear or count
  (contrast: an app event is synchronised); only date, time, duration and deletion flow back,
  title/location changes in Google are ignored; a start change sets Moved; the later change wins
  on conflict; a change in Google is visible within 5 minutes or on page open.
  **Out of scope:** the deletion decision UI (EKO-5-04).
  Req: VIS-2, VIS-4, VIS-5, VIS-6, VIS-9, PRH-2. After: EKO-5-02.

- **EKO-5-04** — Ask the owner to decide on visits deleted in Google.
  *Done when:* tests prove: an event deleted in Google puts the visit into Awaiting decision; the
  owner sees a prompt on any page after login with reschedule (counts as Moved) or cancel for
  good; postponing keeps it returning until decided; no other user sees it.
  **Out of scope:** recurring occurrences (later).
  Req: VIS-11. P2: sync decision notice. After: EKO-5-03.

- **EKO-5-05** — Keep visits intact when Google access is lost.
  *Done when:* tests prove: an expired/revoked token or unlinked account changes no visit state
  and raises no deletion prompt (contrast: a real deletion does); pending changes synchronise
  after relinking.
  **Out of scope:** —
  Req: VIS-8, PRH-3. After: EKO-5-04.

- **EKO-5-06** — Move future events between calendars on reassignment.
  *Done when:* after a reassignment, future events disappear from the old owner's calendar and
  appear in the new owner's; this counts neither as Moved nor Cancelled; failure leaves the visits
  Unsynchronised for retry.
  **Out of scope:** —
  Req: CUS-10. After: EKO-3-07, EKO-5-02.

---

## After the MVP (not drafted in detail)

| Block | Content | Req |
|---|---|---|
| EKO-6 Recurring visits | series rules, edit scope, single-occurrence changes, Google recurrence | REC-1–4 |
| EKO-7 Dashboard | periods and presets, metrics, team view, per-rep filter | DSH-1–5 |
| EKO-8 Go-live | Google app verification; GDPR impact assessment; Excel import; e-mail reminders; erasure | IMP-1–4, brief §4 Later |

## Points for the human

1. EKO-1-02–1-05 assume the decisions become separate tasks; if gate 1 of #6 widens EKO-1-01
   instead, they fold into it.
2. EKO-1-07 names P2 as the design source; `docs/prototype/` also holds P1 and P3. The human
   chooses the direction (or a mix: one prototype's look, another's rules) at gate 1 of
   EKO-1-07; the drafts' P2 references then change accordingly.
3. Order inside the MVP: EKO-1 → EKO-2 → EKO-3-01…3-06 → EKO-4 → EKO-3-07 → EKO-5. The sync
   block is last and largest; EKO-1-05 front-loads its risk.
