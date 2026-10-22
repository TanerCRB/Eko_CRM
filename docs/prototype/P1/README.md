# Prototype P1 — interactive demo and UI kit

A clickable prototype of Eko_CRM built from [`docs/product/project-brief.md`](../../product/project-brief.md),
plus the design tokens, components and domain rules meant to carry over into `frontend/`.
It is a **design artifact, not product code**: no backend, synthetic data in memory, no build step.
It decides nothing about the stack (`EKO-1-01`) and proves no capability.

UI copy is Polish, because the users are Polish sales reps; code, comments and this file are in English.

## Open it

The pages load files by relative path, so serve the folder instead of opening `index.html` from disk:

```bash
py -m http.server 8417 --directory docs/prototype/P1
```

Then open `http://localhost:8417/` (demo) and `http://localhost:8417/ui-kit.html` (component gallery).
Fonts come from Google Fonts; without a network the pages fall back to system fonts.

On the login screen pick a person; no password is needed. The **Demo** button (bottom right)
switches users, simulates an event deleted in Google, toggles the theme and resets the data. The demo
clock is fixed at 11:40 today, so the agenda always tells the same story.

| Demo user | Shows |
|---|---|
| Anna Wróbel, rep | A full day, an event deleted in Google (decision prompt), overdue actions, a manager's note on her customer, an unsynchronised visit |
| Piotr Nowicki, rep | Google access expired: the reconnect notice; reconnecting synchronises pending visits |
| Katarzyna Lis, rep | Google not linked; her own "Jan Pietrzak" is invisible to Anna's duplicate check |
| Marek Zając, manager | All customers, the reassignment screen, the team dashboard, close-only rights on reps' actions |

## Files

| Path | What it is | Carries into `frontend/`? |
|---|---|---|
| `assets/tokens.css` | Colour, type, space, radius, motion tokens as CSS custom properties; light and dark | Yes, as is |
| `assets/components.css` | Framework-agnostic `ek-` components that read only tokens | Yes: class names map to components below |
| `assets/app.css` | App shell: rail, top bar, tab bar, page grid, demo panel | The shell layout, not the demo panel |
| `handoff/tokens.json` | The same tokens in W3C design-token form, for tooling | Optional |
| `handoff/domain.ts` | Typed domain rules: NIP checksum, address, phone and e-mail checks, visit state, action transitions, overdue, reminders, dashboard counts | Yes, as `src/domain/`; needs tests |
| `js/domain.js` | Plain-JS mirror of `domain.ts` used by the demo | No |
| `js/icons.js` | 24×24 stroke icon paths and the brand mark | Yes, as an `<Icon>` component |
| `js/data.js` | Synthetic seed (invented names, valid-checksum NIPs) | Shape only; fixtures for tests |
| `js/app.js` | The demo: hash routing, screens, simulated server rules | No — reference for behaviour and copy |
| `index.html`, `ui-kit.html` | Demo and component gallery | No |

## Design direction

- **Palette.** Rapeseed yellow — Polish fields in May — is the only accent: the "now" line, the active
  navigation item, anything waiting for a decision. Primary actions are loam brown-black. The paper is
  a cool field-frost grey, not cream. Green belongs only to *Held* and *Done*, so it keeps its meaning.
- **Type.** Bricolage Grotesque for headings; Atkinson Hyperlegible Next for text, chosen for reading
  a phone in sunlight in the field. Tabular figures everywhere; body text never below 15 px.
- **Motif.** A diagonal furrow hatch marks things that are waiting: a visit awaiting decision, a visit
  not yet in Google. A state is a filled chip with a dot; a flag (*Moved*, *Unsynchronised*) is an
  outlined chip, because a visit has one state and any number of flags.
- **Signature element.** The day agenda on *Dziś*: hour rails like field strips, visits in their real
  time slot, a yellow line at the current time. Everything else stays quiet.
- **Radius by hierarchy:** controls 6 px, surfaces 10 px, state chips round. Shadows only on floating
  layers (dialogs, toasts).
- **Phone first where it matters:** tab bar below 900 px, dialogs become bottom sheets below 600 px,
  44 px touch targets, call and navigate buttons on the next visit.

## Component map

| CSS block | Future component | Notes |
|---|---|---|
| `ek-btn` (`--primary`, `--ghost`, `--danger`, `--sm`, `--icon`) | `Button` | The label says what happens; the toast repeats the same verb |
| `ek-field`, `ek-input`, `ek-select`, `ek-textarea`, `ek-check`, `ek-fieldset` | `Field`, `TextInput`, `Select`, `Textarea`, `Checkbox`, `Fieldset` | `aria-invalid="true"` drives the error style |
| `ek-chip--{planned,held,cancelled,awaiting}` | `VisitStateChip` | Driven by `visitState()` |
| `ek-chip--{todo,planned,done,cancelled,overdue}` | `ActionStatusChip` | *Overdue* is computed, shown beside the status |
| `ek-flag`, `ek-flag--unsynced` | `VisitFlags` | |
| `ek-chip--manager`, `ek-note--manager`, `ek-avatar--manager` | `AuthorTag` | ACC-6 attribution, everywhere a note or action appears |
| `ek-banner--{decision,warn,info}` | `PageNotice` | Decision prompt (VIS-11) and reconnect notice (VIS-8) on every page |
| `ek-agenda` | `DayAgenda` | Props: visits, now, start hour; height proportional to time |
| `ek-note`, `ek-action` | `NoteItem`, `ActionItem` | The status menu lists only `allowedTransitions()` |
| `ek-contact` | `ContactLine` | Phone is a `tel:` link; e-mail is copy-only (the app sends no e-mail) |
| `ek-dialog`, `ek-choice` | `Dialog`, `ChoiceCard` | Native `<dialog>`; bottom sheet on phones |
| `ek-list`, `ek-row`, `ek-table`, `ek-seg`, `ek-stat`, `ek-empty`, `ek-count`, `ek-toast` | `List`, `Row`, `Table`, `Segmented`, `Stat`, `EmptyState`, `CountBadge`, `Toast` | |

## Screens and the requirements they show

| Screen (route) | Requirements |
|---|---|
| Login (`#/login`) | ACC-1, ACC-2, ACC-3 — own accounts, no self-registration, reset by e-mail |
| Today (`#/today`) | ACT-4 reminders; agenda of the owner's visits; next visit with call and Maps |
| Every page | VIS-8 reconnect notice; VIS-11 decision banner, dialog after login, can be postponed |
| Customers (`#/customers`) | ACC-4 rep sees own only; manager filters by rep; archived view |
| Customer (`#/customers/:id`) | CUS-1 contacts with notes and primary; CUS-9 archive with consequences; restore; NOT-2 manager note; ACC-4 "not found" that discloses nothing |
| Customer form (`#/customers/new`, `/:id/edit`) | CUS-2…CUS-8: required fields, postal code, voivodeship and county, NIP checksum and uniqueness (manager gets a link, rep does not — ACC-8), duplicate warnings within the viewer's scope (CUS-7), phone normalisation |
| Visits (`#/visits`), plan or move (`#/visits/new`, `/:id/edit`) | ACC-7 own customers only; ACC-5 manager cannot plan; VIS-3 event preview without attendees; VIS-7 unsynchronised when Google is not linked; VIS-9 Moved on date or time change only |
| Visit (`#/visits/:id`) | VIS-10 delete asks reschedule or cancel; VIS-13 "did not happen"; NOT-1 notes in any state; ACT-1 action from a note |
| Actions (`#/actions`) | ACT-2 transitions, ACT-3 overdue, ACC-5 manager closes only, history of who changed the status |
| Reassignment (`#/team`, manager) | CUS-10 single and bulk, with what moves along |
| Dashboard (`#/dashboard`, after MVP) | DSH-1 presets (no custom range yet), DSH-3 metrics, DSH-4/DSH-5 own vs team view |
| Account and calendar (`#/settings`) | VIS-8 reconnect, unlinking keeps events in Google |

## Known gaps

- The county list is a sample of five voivodeships; production needs the full TERYT register from the API.
- Day boundaries use the browser time zone; production must compute them in Europe/Warsaw.
- Recurring visits (REC-*), Excel import (IMP-*), custom dashboard ranges and the administrator's
  account management are not in the prototype.
- Rules the server must enforce (ACC-4, CUS-3, CUS-6, ACT-2) are only simulated in the browser.
- `handoff/domain.ts` has no tests yet; they belong with the frontend once the stack is decided.
- Fonts load from Google Fonts here; self-host them in the product (privacy and offline install).
