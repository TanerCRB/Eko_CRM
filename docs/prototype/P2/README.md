# Eko CRM · P2

An independent interactive design prototype for agricultural customer relationships. Based on `docs/product/project-brief.md`. P1 was not read, copied or used for inspiration. Everything in this delivery lives in this directory; all people, businesses and contacts are synthetic.

## Open the demo

Open `index.html` in a modern browser. No package installation, build or internet connection is needed. If the browser restricts local-file scripts or storage, use the included local server:

```powershell
cd E:\GitHub\Eko_CRM\docs\prototype\P2
npm start
```

Open http://127.0.0.1:4174. Stop the server with Ctrl+C. It serves only this directory and binds only to this computer. `PORT` can select another local port.

The demo clock is fixed at **22 October 2026, 10:15 Europe/Warsaw**. Changes persist in this browser under the isolated `eko-crm-p2-v1` storage key. The footer's **Reset demo** restores the original examples. The persona itself resets to Alex on reload. Local-file and HTTP origins have separate storage.

## Explore

| Screen | Working interactions |
| --- | --- |
| My day | Choose weekday, open visits, complete follow-ups, inspect sync decisions |
| Customers | Search by name/town/contact, filter active/archive, add/edit contacts, view history, archive/restore |
| Visits | Weekly and all-visits views, plan, move, cancel, add a visit note |
| Follow-ups | To do / in progress / closed, due-date filtering, valid status transitions, source note |
| Google Calendar | Simulate expiry, reconnect/retry, simulate Google deletion |
| Team overview | Manager persona only; period and owner filters; labelled as a later release |
| Design library | Shared palette, typography, buttons, states, fields, empty state and icons |

Switch **Demo persona** in the footer to Alex, Julia or Robin (manager). Robin can reassign customers, add attributed notes and close others' follow-ups, but cannot move or cancel another person's visit or edit their note. Julia starts with an expired calendar connection.

## Delivery map

| File | Purpose |
| --- | --- |
| `index.html` | Direct-open demo entry |
| `styles/tokens.css` | Reusable design tokens |
| `styles/app.css` | Responsive shell, components and states |
| `src/components.js` | Shared icons, escaped render helpers, fields, badges, buttons |
| `src/domain.js` | Testable prototype domain rules independent of DOM |
| `src/fixtures.js` | Original synthetic scenarios |
| `src/contracts.d.ts` | TypeScript entity and presentation contracts for discussion |
| `assets/` | Original SVG identity and field-line illustration |
| `DESIGN.md` | Design plan and critique against the brief |
| `HANDOFF.md` | Component inventory and implementation guidance |
| `REQUIREMENTS.md` | Requirement coverage and explicit gaps |
| `SCENARIOS.md` | Repeatable demo walkthrough |
| `VALIDATION.md` | Checks performed and limits of evidence |
| `tests/domain.test.cjs` | Node built-in tests, no test dependencies |
| `screenshots/` | Desktop, mobile, customer sheet and component catalogue previews |

## Checks

```powershell
npm run check
npm test
```

## Boundaries

This is a local design artifact, not product implementation or an accepted architecture decision. It has no authentication, backend, real calendar integration or production data protection. Role behaviour is a UI/domain simulation; every synthetic record is in the browser. Do not enter real customer data. The product remains an online-only web application: the demo's local storage is not a proposed product offline mode.

The prototype UI, accessible labels, validation messages, dates and sample content are in Polish, as requested. Technical documentation and domain contracts remain in English. Native browser date controls may use the operating system's language. `src/locale-pl.js` translates unchanged sample content in existing browser saves without resetting user edits or workflow state.
