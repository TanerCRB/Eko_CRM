# P2 validation record

Date: 2026-10-22. Scope: this local prototype only. This is the author's validation record, not an independent Ninefold role verdict, production acceptance or capability-register update.

## Automated checks

- `npm run check`: syntax checks for the local server and all four browser scripts passed.
- `npm test`: **20 tests passed**, zero failures, zero skipped tests, using Node's built-in test runner.
- Local HTTP readiness check: **200** for the demo entry page.

The rule tests cover owner visibility and mutation restrictions; derived held status; changed-start versus changed-duration flags; Google deletion and recovery; unchanged visit state on expiry; disconnected save and reconnect; archive isolation and retained notes; reassignment and historical attribution; note/action ownership; manager closing restrictions; transitions and overdue computation; NIP validation and private conflict wording; duplicate-warning scope; foreign addresses; Warsaw DST conversion; and dashboard counting.

## Browser walkthrough performed

The demo was exercised in the Codex in-app Chromium browser through its UI:

| Check | Observed result |
| --- | --- |
| Initial day | Four Thursday visits, one held, two ahead, one decision notice |
| Google deletion recovery | Changed Green Acre Farm to Friday; saved Planned + Moved; decision notice disappeared |
| Customer search | “meadow” reduced the list to Meadow & Grain |
| New customer | Saved a name containing `<Field>` and `&` as literal text; no injected markup |
| Customer edit | Updated the synthetic name and saw it in the side sheet |
| New visit | Planned a visit from the new customer's sheet; visit count increased |
| Note + action | Saved a visit note with a follow-up; both appeared linked in Notes |
| Archive and restore | Confirmation showed one future visit and one open action; restored customer retained its cancelled visit |
| Calendar expiry | Reconnect notice appeared and existing visit states remained intact |
| Reconnect | Pending-sync list cleared in the simulated connection screen |
| Manager reassignment | Changed Oakfield Growers from Alex to Julia; sheet showed Julia, historic note retained Alex |
| Follow-up transitions | To do → In progress → Done → To do worked |
| Manager restrictions | Other-owner action selector offered Done/Cancelled, not In progress; closing showed “Status set by Robin Ellis · Manager” |
| Team overview | Manager-only navigation and filtered-period metric view rendered |
| Form error | Invalid Polish postal code `1234` produced the inline correction message |
| Component catalogue | Palette, typography, badges, icon set, real form actions and handoff links rendered |
| Mobile navigation | Menu opened, selected Follow-ups and closed; icon-only search retained its accessible label |
| Desktop layout | Inspected at 1440 × 1000; page width 1425px with scrollbar, no page-level horizontal overflow |
| Mobile layout | Inspected at 390 × 844; page width 375px with scrollbar, no page-level horizontal overflow |
| Browser console | Final error/warning log query returned no entries |
| Reset | Restored all original synthetic fixtures after walkthrough changes |

Temporary viewport overrides were reset. Screenshots are in `screenshots/desktop.png`, `mobile.png`, `customer.png` and `components.png`.

## Corrections made during validation

- Form submission now reads the form's ID attribute explicitly: an input named `id` can shadow the form's DOM property.
- Start-time comparison uses parsed instants, so equivalent ISO representations do not incorrectly set Moved.
- Desktop menu visibility uses a selector that is not overridden by the shared icon-button class.
- Mobile navigation is removed from focus when hidden; search has a persistent accessible name.
- Manager action attribution is present in agenda follow-ups and note previews as well as the follow-up board.
- Skip-to-content focuses the main region without changing the route.

## Not verified

Real authentication, server authorization, Google OAuth/events/sync timing, concurrent edits, deployment, backup, real-data handling, full screen-reader compatibility, non-Chromium browsers and direct-file browser storage behaviour. No real credentials or customer records were used. See `REQUIREMENTS.md` for intentionally deferred product requirements.
