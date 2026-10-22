# P2 requirement map

Source of truth: `docs/product/project-brief.md`. “Working” below means local synthetic interaction only, not production capability evidence.

| Requirements | Prototype coverage | Limit |
| --- | --- | --- |
| ACC-1–3 | Deliberately not simulated with a fake login | No identity server, session or admin UI |
| ACC-4, ACC-7–8, PRH-4 | Persona-scoped customer/visit/action lists, owner guards, private NIP conflict wording | Browser fixtures remain inspectable; production authorization is absent |
| ACC-5–6, PRH-6 | Manager reassignment, attributed notes/actions and closing; no other-owner visit edits or note edits | No full audit ledger |
| CUS-1–2 | Required name/country; optional address/tax ID; repeatable annotated contacts and one primary | Voivodeship and county deferred |
| CUS-3–5 | Polish postcode, tax checksum/normalisation; foreign tax ID and postcode free-form | Regional catalogue and server validation deferred |
| CUS-6 | NIP collision blocks save; rep wording hides other-owner identity | Manager sees conflict name, not a navigable conflict link |
| CUS-7–8 | Accessible duplicate warning after non-blocking save, phone normalisation and email validation | No comprehensive international phone library |
| CUS-9, PRH-5 | Confirm archive; cancel only matching future visits/open actions; restore; preserve history | Calendar effects are local flags |
| CUS-10 | Single-customer manager reassignment and preservation of original history | Bulk reassignment and real calendar transfer deferred |
| SEED-1 | Original synthetic fixture dataset plus reset | No operator import script or environment seeding |
| VIS-1–6, PRH-1–2 | Owner/customer relationship, time/address context, explicit integration boundaries in connection UI | OAuth, event payloads, Google Maps, two-way merge, network timing not implemented |
| VIS-7–8, PRH-3 | Save disconnected, not-synced flag, expired-access notice, simulated reconnect | No background worker or real retry queue |
| VIS-9–11 | Move flag, cancellation confirmation with move alternative, persistent deletion decision | App cancellation uses an explicit Cancel visit flow rather than an ambiguous delete icon |
| VIS-12–13 | Notes survive cancellation; held visit can be marked Did not happen | Demo clock is fixed |
| NOT-1–2 | Add visit notes in any state, author-only editing, manager customer notes | No rich-text editor or revision history |
| ACT-1–4 | Follow-up from a new note, owner/author, valid transitions, due/overdue filtering and reminder count | Latest status actor only; one action per new note in this UI |
| DSH-1–5 | Later-release manager view, inclusive custom period / this week, per-owner totals, held/planned/moved/cancelled and separate decision count | Other presets and rep dashboard deferred; day agenda is the main rep view |
| REC-1–4 | Explicitly labelled as a later release | No recurring-series UI or scheduling |
| IMP-1–4 | Outside this prototype | No import UI, as import follows MVP |

No offers, invoices, sales revenue, farm acreage/crop/livestock records, route optimisation, customer email/SMS, native mobile app or unrelated calendar events were introduced.
