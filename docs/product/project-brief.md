# Eko_CRM — project brief

Input for starting work: the result of two discovery rounds between the human, the Product Owner
and the Analyst (2026-10-22). It records **what** is built and why, not how. Architecture choices
named here (Keycloak, containers) are the human's stated preferences and go to the Architect as
input for decisions; they are not accepted decisions until an ADR says so.

Requirement identifiers (`ACC-`, `CUS-`, `VIS-`, …) are stable references for Stories and
acceptance criteria. Changing a rule here is a product decision, made by the human.

## 1. Vision

Eko_CRM is an internal CRM for one agricultural sales company. Each sales rep keeps their own
customers — mostly farmers — plans field visits (one-off and recurring) that appear in their own
Google Calendar, and records notes and follow-up actions after each visit. Managers get a reliable
count of visits held, moved and cancelled, which replaces manual reporting.

## 2. Users and roles

| Role | What they do | What they see |
|---|---|---|
| **Sales rep** | Owns customers (about 200 each at the start). Plans and performs visits, writes notes, works through actions. Links their own private Gmail account, for the calendar only. Uses a phone in the field and a desktop in the office. | Only their own customers, visits, notes and actions. |
| **Manager** | Reassigns customers between reps. Edits customer data. Adds own notes and actions, closes actions (always visibly attributed to the manager). | Everything, including the team dashboard. |
| **Administrator** | Creates, deactivates and assigns roles to accounts in the identity server. | — |
| **Customer (farmer)** | Not a user. The data subject: a natural person whose personal data the company processes. | — |

One person may hold two roles (e.g. manager and administrator). Scale at the start: up to 10 reps
and 1–2 managers. No fixed deadline; sync quality is the priority.

## 3. Success measures

- After rollout, 100% of customer visits are planned through the app; none only in Google Calendar.
- The dashboard replaces manual visit reports for the manager.
- No visit deleted in Google Calendar goes unnoticed: each one surfaces in the app as awaiting a
  decision.

## 4. Scope

### MVP, in priority order

1. **Foundations (EKO-1).** EKO-1-01 stack and persistence decisions. Two more decisions are
   needed: authentication with an own identity server (Keycloak preferred), and containerised,
   cloud-agnostic on-premises deployment with backup. Whether they widen EKO-1-01 or become new
   EKO-1 tasks is decided at gate 1 of #6.
2. **Login and roles** — own accounts independent of Google; roles rep, manager, administrator.
3. **Customer register** — create, edit, archive and restore; one owner per customer; multiple
   phones and e-mails, each with a note.
4. **Customer reassignment** — manager moves customers between reps.
5. **Seed script** — loads initial customer data into an environment; an operator tool, not a user
   feature (replaces the Excel import for the MVP).
6. **Visits, notes and actions** — plan, move, cancel; automatic "held"; notes with actions and
   statuses; in-app reminders.
7. **Google Calendar sync, basic two-way** — private Gmail, primary calendar, app-created events
   only, deletion in Google surfaces as a decision prompt, visible reconnect notice.

### Later

8. Recurring visits.
9. Dashboard.
10. Google app verification for production use (before go-live; moves earlier if the pilot needs it).
11. Excel import of customers.
12. E-mail reminders for actions.
13. GDPR impact assessment — before any real customer data is loaded.
14. Permanent GDPR erasure of a customer (moves earlier if the impact assessment requires erasure
    from go-live).

### Out of scope (explicit)

- Offers, quotes, invoices.
- Sending e-mail or SMS to customers from the app. (Password-reset e-mail from the identity server
  is not covered by this exclusion.)
- Route planning across visits — the address on the calendar event opens Google Maps.
- Native mobile app and offline mode.
- Farm data (areas, crops, livestock) — re-evaluate after the MVP is in use.
- Integrations other than Google Calendar; Google Workspace-specific features.
- Importing calendar events not created by the app; importing visit history.
- Several companies on one installation (multi-tenancy).

## 5. Constraints

- **Hosting.** On-premises server run by the company's IT department, containerised and
  cloud-agnostic so a later migration stays open. Reachable from the internet over HTTPS under a
  company domain (reps work from phones in the field; Google needs a callback address). Daily
  database backup kept off the server, with one tested restore before go-live.
- **Authentication.** Own accounts in an identity server (Keycloak preferred), independent of
  Google. No self-registration. Password reset by e-mail from the identity server through a company
  SMTP mailbox (the company will provide it).
- **Google.** Private Gmail accounts, calendar access through OAuth. In Google's testing mode
  calendar access expires every 7 days and is capped at 100 test users; production use needs Google
  app verification (domain and privacy policy required, days to weeks). The pilot runs in testing
  mode.
- **Personal data (GDPR).** Customers are mostly natural persons: name, address, NIP, phones,
  e-mails. The company is the data controller. Archiving keeps the data; permanent erasure is
  separate. Changing a file concerning personal data requires an architecture decision covering it
  (`TEAM-CONTRACT.md`, hard stop 6), so the EKO-1 decisions must include personal-data handling.
  During the MVP only synthetic data is used; the formal GDPR impact assessment is done after the
  MVP, before any real customer data is loaded.
- **Foundations not proven.** The capability register is empty; every product Story rests on
  unproven capabilities until EKO-1 is done.
- **Client.** Responsive web app in a browser, online only. Time zone Europe/Warsaw.

## 6. Glossary

- **Customer** — a farmer or agriculture-related party; belongs to exactly one sales rep (its owner).
- **Visit** — a scheduled meeting with one customer; has an owner and a start and end time; mirrored
  as an event in the owner's primary Google calendar.
- **Visit states:**
  - **Planned** — not cancelled, end time (Europe/Warsaw) not passed.
  - **Held** — not cancelled, end time passed. Automatic; no manual confirmation.
  - **Cancelled** — deleted in the app or in Google and not rescheduled, or explicitly cancelled
    (including "did not happen").
  - **Awaiting decision** — the event was deleted in Google and the owner has not yet chosen
    reschedule or cancel.
- **Moved** — a flag, not a state: the start date or time changed at least once (in the app or in
  Google), or a deleted visit was rescheduled from the prompt. Counted at most once per visit.
  Changes of place, duration or description do not set it.
- **Unsynchronised** — a flag: the app could not mirror the visit to Google yet.
- **Series** — a recurring visit definition producing occurrences; each occurrence is a visit.
- **Note** — free text attached to a visit and therefore to its customer; has an author; survives
  deletion of the visit.
- **Action** — a to-do created from a note: description, optional due date, owner, author.
- **Action statuses** — To do, In progress, Done, Cancelled. Transitions: To do → In progress →
  Done or Cancelled; To do → Done or Cancelled; any status → To do.
- **Overdue** — computed, not a status: due date passed and the action is neither Done nor
  Cancelled.
- **Archived customer** — removed from active use; can be restored.

## 7. Requirements

### Access

- **ACC-1.** Every page and every API operation requires an authenticated session, except login.
- **ACC-2.** User accounts exist independently of Google: a user can log in without having linked
  any Google account.
- **ACC-3.** No self-registration. Only the administrator creates and deactivates accounts and
  assigns roles. A deactivated account cannot log in; its data is retained.
- **ACC-4.** A rep can read and modify only their own customers, visits, notes and actions. A
  direct request for another rep's record is denied by the server and discloses none of its data.
  Contrast: the manager making the same request gets the record.
- **ACC-5.** Manager rights:
  - reads all data;
  - edits customer data of any rep and reassigns customers (CUS-10);
  - **cannot edit or delete a rep's notes**; can add own notes to any customer;
  - **cannot edit a rep's actions**; can create actions (from own notes) and can close any action
    (Done or Cancelled);
  - cannot create, move or cancel another user's visits — only the visit's owner can, because the
    visit lives in the owner's Google calendar.
- **ACC-6.** Every note and action created by the manager, and every action status change made by
  the manager, is attributed to the manager and shown as such wherever the note or action is
  displayed.
- **ACC-7.** A rep plans visits only for their own customers.
- **ACC-8.** Messages caused by another rep's data (e.g. a NIP conflict) disclose neither that
  customer's data nor the rep's name.

### Customers

- **CUS-1.** Fields: name; one address (street and number, postal code, post office/town,
  voivodeship, county, country); NIP; any number of phones and e-mails, each with an optional note
  saying who it reaches; one contact may be marked primary.
- **CUS-2.** Required: name and country (default Poland). Everything else is optional.
- **CUS-3.** Polish addresses: postal code matches `00-000`; voivodeship is one of the 16; county
  belongs to the chosen voivodeship (a mismatch is rejected). Voivodeship and county are optional
  but must be valid when given. Enforced by the server, not only the form.
- **CUS-4.** Foreign addresses: voivodeship and county not required; postal code free-form.
- **CUS-5.** Polish NIP: hyphens, spaces and a `PL` prefix are removed, then it must be 10 digits
  with a valid checksum. A foreign tax ID is free text with no checksum.
- **CUS-6.** NIP is unique across the company. Saving a second customer with an existing NIP is
  blocked; the manager gets a link to the existing customer, a rep gets "a customer with this NIP
  already exists — contact your manager".
- **CUS-7.** Duplicate warnings (warn, do not block): another customer with the same phone or
  e-mail; the same name in the same town, ignoring case and leading/trailing spaces. A rep is warned
  only within their own customers, the manager across the company.
- **CUS-8.** Phones are stored in international format (default `+48`); e-mails must be
  well-formed.
- **CUS-9.** Deleting a customer archives it; it can be restored. On archiving: future visits are
  cancelled and removed from Google without the reschedule prompt; past visits and notes remain and
  still count on the dashboard; open actions become Cancelled; no other customer's data changes.
- **CUS-10.** Reassignment (manager only, single or bulk): the customer, its future visits and its
  open actions move to the new owner; future events move from the old owner's calendar to the new
  owner's, counting neither as moved nor cancelled; past visits and notes keep their original owner
  and author.

### Seed data (MVP)

- **SEED-1.** An operator script loads synthetic customers (test data, no real personal data)
  into an environment, each with an owner. Loaded
  customers satisfy CUS-2 to CUS-8; an invalid record is reported, not loaded. Running it twice
  creates no duplicates.

### Import (later)

- **IMP-1.** One-time Excel import in a fixed template, run by the manager or administrator; one
  owner chosen per file; no visit history.
- **IMP-2.** Rows checked against CUS-2 to CUS-8; valid rows imported; invalid rows skipped and
  reported with row number and reason.
- **IMP-3.** A row whose NIP already exists (in the file or the system) is rejected; a row without
  NIP matching name and town of an existing customer of the same owner is rejected. Importing the
  same file twice creates no duplicates.
- **IMP-4.** Multiple phones or e-mails in one cell are separated by `;`.

### Visits and Google sync

- **VIS-1.** A visit belongs to one customer and one owner, and is mirrored to the owner's primary
  calendar in their private Gmail account.
- **VIS-2.** Only events created by the app are synchronised. Other calendar events never appear
  in the app and never count anywhere. Contrast: an app-created event is synchronised.
- **VIS-3.** Event content: title `Wizyta: <customer name>`; location the customer's address, or a
  per-visit address if given; description the contact phone. The customer is never added as an
  attendee; no invitation or e-mail is sent to anyone.
- **VIS-4.** From Google to the app only date, time, duration and deletion flow back. Title and
  location belong to the app; changes to them in Google are ignored.
- **VIS-5.** When the same visit changes on both sides, the later change wins.
- **VIS-6.** An app change is visible in Google within about 1 minute; a Google change is visible
  in the app within 5 minutes, or when a page is opened.
- **VIS-7.** Google unavailable or not linked: the visit is saved, flagged Unsynchronised, and
  synchronised later.
- **VIS-8.** Loss of Google access (token expired or revoked, account unlinked) never changes any
  visit's state and never raises the reschedule prompt. The owner sees a reconnect notice. Pending
  changes synchronise after reconnecting. Unlinking does not delete events from Google.
- **VIS-9.** Changing the start date or time, in the app or in Google, updates the visit and sets
  the Moved flag.
- **VIS-10.** Deleting a visit in the app asks immediately: reschedule (counts as Moved) or cancel
  (counts as Cancelled).
- **VIS-11.** Deleting the event in Google puts the visit into Awaiting decision. The owner sees a
  prompt on any page after login with two choices, reschedule or cancel for good. It can be
  postponed but returns on every later visit until decided. It applies to single occurrences of a
  series. No other user sees it.
- **VIS-12.** Deleting a visit never deletes its note; the note stays with the customer.
- **VIS-13.** A visit marked "did not happen" becomes Cancelled.

### Recurring visits (later)

- **REC-1.** Rules: every N days; every N weeks on chosen weekdays; every N months on the same day
  of the month.
- **REC-2.** A series ends on a date or after a number of occurrences; series without an end are
  not allowed.
- **REC-3.** An edit applies to "this occurrence", "this and following" or "the whole series".
- **REC-4.** Moving or deleting one occurrence, in the app or in Google, affects only that
  occurrence and follows VIS-9 to VIS-11.

### Notes and actions

- **NOT-1.** A note can be added to a visit in any state and edited later by its author. It is
  linked to the visit's customer.
- **NOT-2.** The manager can add a note to any customer; it is marked as the manager's (ACC-6).
- **ACT-1.** An action is always created from a note. Description required, due date optional.
  Owner defaults to the note's author; for an action created by the manager, the owner is the
  customer's owner.
- **ACT-2.** Status transitions follow the glossary; any other transition is rejected by the
  server. The user who made each status change is recorded.
- **ACT-3.** Overdue is computed, never stored or set by hand.
- **ACT-4.** Reminders (MVP): in the app only. After login the user sees a count and a list of
  their actions due today or earlier that are not Done or Cancelled. Actions without a due date
  produce no reminder.

### Dashboard (later)

- **DSH-1.** Period: calendar days in Europe/Warsaw, both ends inclusive. Presets: today, this week
  (Mon–Sun), this month, this quarter, this year, custom range.
- **DSH-2.** A visit falls in a period by its current start time; a cancelled visit by its last
  start time before cancellation.
- **DSH-3.** Metrics: Planned — all non-cancelled visits in the period, including held; Held — the
  subset of Planned whose end time has passed; Moved — visits in the period with the Moved flag;
  Cancelled — cancelled visits in the period. Visits awaiting decision are reported separately and
  not counted as cancelled.
- **DSH-4.** Default view: the logged-in user's own visits. The manager sees the team total, a
  breakdown per rep, and a per-rep filter. A visit counts for its owner, not the customer's current
  owner.
- **DSH-5.** A rep's dashboard never includes another rep's visits. Contrast: the manager's team
  view does.

### Prohibitions

- **PRH-1.** The app never invites or e-mails a customer through Google (VIS-3).
- **PRH-2.** Calendar events not created by the app are never imported, changed or deleted (VIS-2).
- **PRH-3.** Losing Google access never changes visit states or raises prompts (VIS-8).
- **PRH-4.** A rep can never read another rep's data through any API call, search, duplicate
  warning or error message (ACC-4, ACC-8, CUS-7).
- **PRH-5.** Archiving or reassigning a customer changes no other customer's data (CUS-9, CUS-10).
- **PRH-6.** The manager can never alter a note or action written by someone else, except closing
  an action (ACC-5).

## 8. Open points

- **Domain.** A company domain for HTTPS and Google verification — the human provides it later.
- **Architecture decisions.** Identity server, deployment/backup and personal-data handling: widen
  EKO-1-01 or add EKO-1 tasks — the Architect proposes, decided at gate 1 of #6.
- **Real customer data.** Loading it (by import or otherwise) waits for the GDPR impact assessment,
  scheduled after the MVP.
- **Google verification path.** The Architect resolves it before the sync Story; the 7-day expiry
  in testing mode comes from the roles' knowledge of Google's OAuth policy, not a verified
  capability.
