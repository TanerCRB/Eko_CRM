# P2 design direction

Source: `docs/product/project-brief.md` (2026-10-22). This is a new, local-only design study. No P1 files, assets, data or implementation were read or reused. All fixtures are synthetic.

## Design plan

An agricultural sales representative needs to see their next appointment, the contact context and unfinished follow-ups quickly, including on a phone. The signature element is a quiet green appointment panel with abstract cultivated-field lines. It represents field work, not a map, farm record or route planner.

Palette: forest `#244B3B`, young leaf `#D8E8B3`, ink `#253B35`, mist `#F3F6F3`, paper `#FFFFFF`, harvest `#A36518`. Status meaning always includes text or an icon, never colour alone.

Type: locally available Bahnschrift for headings and prominent times; Segoe UI for controls and text; system sans-serif fallbacks. No remote fonts or network assets. Body 14–16px, page title 32px, next appointment 28px; compact labels remain sentence case.

Layout: persistent forest navigation, restrained utility header, left-aligned workspace, five-day date strip, broad visit agenda and narrower follow-up column. Customer records open in a side sheet so list context remains visible. Editing uses labelled dialogs. Below 900px the columns stack; below 700px navigation becomes a labelled menu and tables scroll in their own region.

```text
Navigation | Workspace / section                   Search / persona
           | Today                                 Plan a visit
           | Mon       Tue       Wed       Thu       Fri
           | Next visit / contact context   | Follow-ups
           | Remaining appointments         | Calendar connection
           |                                | Demo guidance
```

## Review before implementation

A four-card KPI dashboard would look generic and prioritise a later-stage feature over field work. Replace it with the next appointment and a real agenda. Keep the later team dashboard behind a labelled navigation item. Avoid crop-area metrics, maps, weather, sales revenue and quotes: none is supported by the brief. The field-line illustration is the single visual flourish; other surfaces use quiet separators and few shadows. Preview controls are separated from the product navigation.

## Interaction principles

- Distinguish visit state from moved and unsynchronised flags.
- Google deletion requires an explicit owner decision; losing calendar access does not.
- Actions originate in notes. Preserve attribution, particularly manager status changes.
- Archive and reassignment show consequences before confirmation.
- All editable content is escaped on rendering. Demo persona changes are presentation simulations, not authentication.
- Freeze the demo clock at 22 October 2026, 10:15 Europe/Warsaw for repeatable scenarios.
- Build reusable CSS tokens, view helpers, icon primitives, domain functions and typed contracts without selecting the production stack.

## Scope

Working local flows: day/week visits, customer search/filter/create/edit/archive/restore, customer reassignment, visit planning/moving/cancellation, notes with follow-ups, action transitions, simulated sync decisions and reconnection, role-specific presentation, team metrics preview and component catalogue. Full recurring-series editing, real identity, APIs, Google OAuth/sync, persistence on a server and regional address catalogues are outside this prototype. No architecture decision or product capability status is raised.
