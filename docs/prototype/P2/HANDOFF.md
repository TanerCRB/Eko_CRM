# P2 development handoff

## Reusable material

Copy candidates are the semantic CSS variables, original SVG assets, state vocabulary, interaction patterns and pure-rule examples. Review the typed contracts against accepted ADRs before adopting them. This prototype does not create database tables, product API routes or production dependencies.

| Component | Current source | Inputs / behaviour | Suggested production boundary |
| --- | --- | --- | --- |
| AppShell | `src/app.js` / `styles/app.css` | Active section, user presentation, mobile menu | Layout with authenticated route outlet |
| Button / IconButton | `src/components.js` | Label, visual priority, icon, action | Presentational, callback prop |
| StatusBadge | `src/components.js` | State or independent flag; icon plus text | Presentational, no fetching |
| DateStrip | `src/app.js` | Selected day, count, selection | Calendar feature |
| VisitCard / AgendaRow | `src/app.js` | Visit, customer, open callback | Presentational; derive status separately |
| CustomerSheet | `src/app.js` | Customer, contacts, visits, notes | Customer feature composition |
| ContactEditor | `src/app.js` | Repeatable phone/email entries; one primary | Form component with controlled values |
| NoteCard / NoteForm | `src/app.js` | Author, visit link, note, optional action | Notes feature; permissions from server |
| FollowUpCard | `src/app.js` | Action, allowed transitions, due state | Action feature |
| SyncNotice | `src/app.js` | Owner decision vs expired connection | Session-level notice, separate states |
| ConfirmDialog | `src/app.js` | Exact consequence text and explicit action | Shared accessible overlay |
| EmptyState / Toast | `src/components.js`, `src/app.js` | Useful next step / completed result | Shared feedback components |

`src/contracts.d.ts` gives framework-independent props. If React and TypeScript are adopted, convert view helpers to JSX and pass callbacks; reuse tokens and assets directly. Keep data access in the client layer and orchestration in features, as proposed in `docs/architecture/layer-dependencies.md`. Do not copy the prototype's global state, innerHTML orchestration or persona switch into production.

## Tokens and layout

CSS variables cover semantic colours, 4/8/12/16/24/32/48 spacing, text scale, control/panel/pill radii and overlay shadow. The sidebar is 224px at wide desktop widths. The day workspace uses a roughly 1.8:1 agenda-to-follow-up split. At 1000px it stacks; at 700px navigation collapses. Tables and the week grid scroll inside labelled regions. No imagery, font or analytics request leaves the page.

Native dialogs provide modal focus containment, Escape dismissal and a labelled heading. Forms have visible labels, required markers and inline error feedback. Native validation may be localised by the browser. Off-screen mobile navigation is hidden from focus. State labels do not rely on colour. Respect reduced-motion preferences. Run a formal accessibility audit and screen-reader testing before product adoption.

## State and integration contracts to preserve

- Store instants consistently; display and filter calendar days in Europe/Warsaw. The demo explicitly rejects nonexistent and ambiguous DST local times instead of silently choosing.
- Held is derived from end time. Moved and unsynchronised are independent flags. Do not create a single enum containing all three concepts.
- Deletion in Google enters a persistent owner decision. A reconnect failure leaves visit states intact. Notices remain across page navigation until resolved.
- Archive cancels the selected customer's future visits and open actions. Restore does not reopen cancelled records. Retain notes and history.
- Reassignment changes customer/future-visit/open-action ownership, not historical visit ownership or note authors. Calendar movement must be implemented as an integration workflow; the prototype only changes local ownership and pending-sync flags.
- Every action is linked to a note. Its owner and author may differ. Show manager attribution for creation and status changes.
- Production duplicate/NIP checks and authorization must happen server-side, including error-message privacy. UI filtering is not a security boundary.
- Dashboard “planned” includes held; decision rows are reported separately. A moved visit contributes at most once. Use visit ownership, not current customer ownership.

## Deferred production work

Authentication/identity administration, real Google OAuth and token storage, permission checks on every request, sync conflict resolution and retries, a full change audit, data retention/erasure, regional address catalogues, NIP-conflict links for managers, bulk reassignment, recurring rules and Google Maps links all need product implementation. There are no fake external requests or disabled controls implying these integrations work.

The prototype stores only the latest action-status actor. Production must retain the complete status-change audit required by ACT-2. Connections are local flags; timing guarantees and two-way network behaviour are unproven. The week grid deliberately shows a fixed demo week; all other created dates remain visible in All visits. A single follow-up can be added when creating a note; adding further actions to an existing note is a handoff extension.

## Product questions left for design review

Confirm English versus Polish product localisation, the density of the agenda for roughly 200 customers per representative, and how much manager functionality belongs on mobile. These do not block use of the current demo. None of these choices changes the source brief.
