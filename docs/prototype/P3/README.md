# Prototype P3 — the week board, Polish first

A clickable prototype of Eko_CRM built from [`docs/product/project-brief.md`](../../product/project-brief.md),
with the pieces meant to carry into `frontend/`: tokens, components, a typed rule set, and a
Polish string catalogue. It is a **design artifact, not product code**: no backend, synthetic
data in memory, no build step, nothing decided about the stack (`EKO-1-01`), no capability proven.

Made without looking at P1 or P2, as asked. The interface is Polish; code, comments and this file
are English.

## Open it

ES modules need a server with the right MIME type (Windows' `python -m http.server` serves `.js`
as `text/plain`), so use the bundled one:

```bash
py docs/prototype/P3/serve.py 8419
```

Then open `http://localhost:8419/` (demo) and `http://localhost:8419/components.html` (gallery).
Fonts come from Google Fonts; offline, the pages fall back to Georgia and Segoe UI.

Pick a person on the login screen, no password. The **Demo** button in the band switches users,
simulates an event deleted in Google, simulates expired Google access, toggles the theme and
resets the data. The clock is fixed at 14:15 today, so Monday to Wednesday are past, today has a
held visit and one still ahead, and Friday holds the visit deleted in Google.

| Demo user | What it shows |
|---|---|
| Tomasz Krawczyk, rep | Full week; the decision prompt (visit deleted in Google); late tasks; a manager's note and task on his customer |
| Agnieszka Dudek, rep | Google access expired: the red bar, two unsynchronised visits that synchronise on reconnect |
| Michał Sroka, rep | Google never linked; the hint bar; a Saturday visit |
| Beata Wilk, manager | Lanes per rep on the week; all customers; reassignment; team dashboard; close-only rights on reps' tasks; NIP conflict with a link |

## Design direction

**Subject.** A sales rep's week among farms in Kujawy and Mazowsze, planned in the app and
mirrored to a private Google calendar; a manager who needs an honest count; one thing that must
never slip: a visit deleted in Google.

**The one bold element.** The week board on *Tydzień*. Seven equal columns, today marked by a
red rule, visits as blocks in the order of the day (reps want the sequence, not the geometry).
The manager sees the same week as lanes per rep with counts per state. On a phone the board
folds into a day strip and a list. Everything else stays quiet: rules, not cards.

**Palette.** White paper and a dark green band, like the cab of a tractor looking out over a
field in October. Signal red (the enamel of Polish farm machinery) has exactly one meaning:
something needs a decision or is late. It never fills a button. Field green is the primary action
and the *Odbyta* state. Amber is *W toku* and "not yet in Google". No cream, no terracotta, no
black page.

**Type.** Two Polish typefaces. *Brygada 1918* (the revived Warsaw antiqua) for the voice: page
titles, customer names, dashboard numbers, the week's date range. *Lato* (Łukasz Dziedzic) for the
work: body, forms, lists. Scale 1.25 from 16 px; tabular figures; text never below 15 px except
metadata.

**Structure as information.** A state is a boxed chip and a visit has exactly one; a flag is a
glyph with a word and a visit may carry several. *Odwołana* is dashed because it does not count
like the others. The manager's notes and tasks carry a band-coloured *Kierownik* chip wherever
they appear (ACC-6). Radius by role: controls 4 px, chips 2 px, floating sheets 8 px.

**Language.** Every string the interface shows lives in `i18n/pl.js` and goes through `t()`
with Polish plural forms (`one / few / many`). A second language is a second file.

## Files

| Path | What it is | Into `frontend/`? |
|---|---|---|
| `css/tokens.css` | Colour, type, space, radius, motion; light and dark; in a cascade layer | Yes, as is |
| `css/base.css` | Reset, document type, focus, utilities | Yes |
| `css/components.css` | Components; domain states as `data-state`, flags as `data-flag` | Yes: class names map to components below |
| `css/app.css` | Band, page grid, week page, login; demo-only bits marked | The layout, not the demo bits |
| `i18n/pl.js`, `handoff/pl.json` | The Polish string catalogue (342 keys), plural arrays | Yes, as the first locale |
| `app/i18n.js` | `t()`, `pluralIndex()`, Intl formatters for `pl-PL` | Yes, the helper shape |
| `app/rules.js`, `handoff/rules.ts` | Domain rules returning codes: NIP checksum, address, phone, e-mail, duplicate scope, visit state, task transitions, late, reminders, dashboard counts, week helpers | Yes, as `src/domain/`; needs tests |
| `app/icons.js` | 24-unit stroke icons, square caps; the brand mark | Yes, as `<Icon name>` |
| `app/store.js` | In-memory state and mutations that play the server (ACC-4, CUS-9, CUS-10, VIS-9…13, ACT-1, ACT-2) | The behaviour, as a reference for API contract tests |
| `app/views/*.js`, `app/main.js` | Screens, sheets, router, event wiring | No; reference for behaviour and copy |
| `data/seed.js` | Synthetic people, farms, visits, notes, tasks; valid-checksum NIPs | Shape only; test fixtures |
| `handoff/tokens.json` | Tokens for tooling | Optional |
| `handoff/screens.md` | Screen inventory: requirements shown, states to handle, copy rules | Yes, as the build checklist |
| `index.html`, `components.html`, `serve.py` | Demo, gallery, server | No |

## Component map

| CSS | Future component | Notes |
|---|---|---|
| `.btn[data-kind=primary\|quiet\|band\|destructive]` | `Button` | Destructive is ink-outlined, never red |
| `.field`, `.input`, `.select`, `.textarea`, `.check`, `.form-section`, `.search` | `Field`, `TextInput`, `Select`, `Textarea`, `Checkbox`, `FormSection`, `Search` | `aria-invalid` drives the error style; error after blur |
| `.state[data-state]` | `StateChip` | Values: `planned held cancelled awaiting` (visit), `todo progress done cancelled late` (task), `manager` |
| `.flag[data-flag]` | `VisitFlags` | `moved`, `unsynced` |
| `.count` | `CountBadge` | Red only for reminders |
| `.notice[data-tone]` | `PageNotice` | `decision`, `blocked`, `warning`, `hint` |
| `.week`, `.week__day`, `.visit` | `WeekBoard`, `DayColumn`, `VisitBlock` | Today: `data-today`; past: `data-past` |
| `.lanes`, `.lanes__cell`, `.lanes__n` | `TeamLanes` | Manager only |
| `.daystrip` | `DayStrip` | Below 900 px |
| `.next` | `NextVisit` | Call and Maps actions |
| `.event` | `CalendarEventPreview` | VIS-3: what Google will show |
| `.rows`, `.row`, `.person`, `.table`, `.tabs`, `.kv`, `.empty` | `List`, `Row`, `Avatar`, `Table`, `Segmented`, `KeyValue`, `EmptyState` | |
| `.contact` | `ContactLine` | `tel:` link; e-mail copies only (the app sends no e-mail) |
| `.note[data-by=manager]`, `.task[data-late]` | `NoteItem`, `TaskItem` | Status menu lists `taskTransitions()` only |
| `.sheet[data-tone=decision]`, `.choice` | `Sheet`, `ChoiceCard` | Native `<dialog>`; bottom sheet below 600 px |
| `.tile[data-state]`, `.bar` | `StatTile`, `ShareBar` | Numbers in ink; one hue, no legend |
| `.toasts`, `.toast` | `Toast` | Repeats the button's verb |
| `.band`, `.nav`, `.menu` | `AppBand`, `Nav`, `PhoneMenu` | Popover for demo controls is not product |

## Screens and requirements

See [`handoff/screens.md`](handoff/screens.md) for the full table. In short: login (ACC-1…3),
week (VIS states and flags, ACT-4), customers and form (CUS-1…10, ACC-4, ACC-8), visits and
form (ACC-5, ACC-7, VIS-3, VIS-7, VIS-9…13), tasks (ACT-1…4, ACC-5, ACC-6), team (CUS-10),
dashboard (DSH-1…5), account (VIS-7, VIS-8). The decision prompt (VIS-11) opens once after
login and stays as a bar on every page until decided.

## Known gaps

- County list is a sample (five voivodeships); production loads the full TERYT register.
- Day boundaries use the browser time zone; production must use Europe/Warsaw.
- No recurring visits, Excel import, custom dashboard range, or administrator screens.
- Server rules are simulated in the browser; `rules.ts` has no tests yet.
- Fonts load from Google Fonts; self-host them in the product.
- Checked in Chromium on desktop (1366 px) and phone (375 px) widths, light and dark; not in
  Safari or Firefox.
