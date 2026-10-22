# Screens, states and copy — prototype P3

Inventory for the frontend developer: every screen the demo has, which requirement it shows,
and which states it must handle. Routes are the demo's hash routes; the product can keep the
Polish paths. Strings come from `pl.json` (key in brackets where it matters).

| Route | Screen | Requirements shown | States to handle |
|---|---|---|---|
| `#/logowanie` | Login | ACC-1, ACC-2, ACC-3 | error (wrong credentials), password reset by e-mail from the identity server |
| every page | Band + notices | VIS-8 reconnect bar (`notice.expired*`), VIS-11 decision bar (`notice.decisionTitle`), ACT-4 reminder count on *Zadania* | bars stack; only the owner sees the decision bar |
| `#/tydzien` | Week (rep) | VIS-* states and flags, ACT-4 reminders, next visit with call and Maps | empty day (`week.free`), no next visit, no reminders; phone: day strip |
| `#/tydzien` | Week (manager) | DSH-4 team view by rep | empty cell; click cell → list |
| `#/klienci` | Customers | ACC-4 scope, archived view, manager filter by rep | no match, no archived, none at all |
| `#/klienci/:id` | Customer | CUS-1 contacts with "who", CUS-9 archive with consequences, restore, NOT-2 manager note, ACC-6 attribution | archived, no notes, no visits, no contact; "not found" that discloses nothing (`customers.notFound*`) |
| `#/klienci/nowy`, `/:id/edycja` | Customer form | CUS-2…CUS-8, ACC-8 (rep gets no link on NIP conflict) | field errors after blur (`err.*`), NIP conflict blocks (`conflict.*`), duplicate warnings do not (`warn.*`), foreign address hides voivodeship/county |
| `#/wizyty` | Visits | ACC-7, ACC-5 (manager cannot plan) | upcoming / past tabs, empty |
| `#/wizyty/nowa`, `/:id/edycja` | Plan / move | VIS-3 event preview, VIS-7 unsynced when Google not linked, VIS-9 moved on start change only | customer not picked, Google not linked |
| `#/wizyty/:id` | Visit | VIS-10 delete asks reschedule or cancel, VIS-13 "did not happen", NOT-1, ACT-1, VIS-12 notes survive | planned / held / cancelled / awaiting; manager read-only with owner-only note (`visit.ownerOnly`) |
| sheet | Decision | VIS-10, VIS-11 | from Google (postpone allowed) vs from the app ("keep") |
| `#/zadania` | Tasks | ACT-2 transitions, ACT-3 late, ACC-5 manager closes only, who changed status | open / late / all tabs, empty |
| `#/zespol` | Team (manager) | CUS-10 single and bulk reassignment | nothing selected (button disabled) |
| `#/pulpit` | Dashboard (after MVP) | DSH-1 presets, DSH-3 metrics, DSH-4/5 own vs team | custom range not in the demo |
| `#/konto` | Account and calendar | VIS-7, VIS-8, unlink keeps events in Google | linked / expired / none |

## Copy rules the catalogue follows

- The button names the result; the toast repeats the same verb ("Zaplanuj wizytę" → "Zaplanowano…").
- Errors say what to fix, never apologise, never blame (`err.nipChecksum`).
- Empty states invite an action, not a mood (`customers.none` + "Dodaj klienta").
- The manager's entries are always marked (`role.manager`) wherever a note or task shows (ACC-6).
- Nothing in the rep's interface ever names another rep or their customer (ACC-8, PRH-4).
- Counts use the three Polish plural forms (`pluralIndex` in `rules.ts`).

## Not in the demo

Recurring visits (REC-*), Excel import (IMP-*), custom dashboard range, administrator's account
management, the real identity-server login, real Google OAuth. Day boundaries use the browser
time zone; production uses Europe/Warsaw.
