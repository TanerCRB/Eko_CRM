# P2 walkthrough

Use **Reset demo** before starting. All values are synthetic. The fixed clock makes held/overdue results repeatable.

1. **Start the day.** Alex sees four Thursday visits: Willow Farm held, Meadow & Grain planned, Oakfield Growers moved and not synced, Green Acre Farm awaiting decision. The follow-up badge shows two due/overdue actions.
2. **Recover a Google deletion.** Review the notice. Choose a new time for Green Acre Farm, e.g. 23 October 15:00–16:00. Save. The decision notice disappears, Friday gains a planned visit with Moved. Alternatively cancel and verify Cancelled.
3. **Capture a conversation.** Open Willow Farm's held visit. Add a note and a follow-up due 22 October. Save; open Follow-ups and locate the new action. Read source note. Move it to In progress, Done, then To do.
4. **Create a customer.** Search for a nonexistent synthetic name. Add a customer with only name and country. Add a phone and email with notes, marking one primary. Polish postal code `1234` fails validation; `00-001` passes. Invalid Polish NIP checksum fails.
5. **Plan while disconnected.** In Google Calendar, simulate expired access. Existing visit states stay unchanged and a reconnect notice appears. Plan a future visit: it is saved as Not synced. Reconnect clears pending flags.
6. **Archive safely.** Open Oakfield Growers. Archive and inspect the consequence counts. Its future visit and open action cancel; the previous held visit, note and completed action remain. Restore returns the customer without reopening cancelled items.
7. **Reassign as manager.** Switch to Robin, open Oakfield Growers, choose Reassign → Julia. The future visit and open action move; historical visit ownership and note authorship remain Alex. Switch to Alex and then Julia to compare accessible customer lists.
8. **Check manager restrictions.** As Robin, open Alex's visit: move/cancel controls are absent. Alex's note has no edit control. An open follow-up offers Done/Cancelled but not In progress. Add a manager note to a customer; the attribution is visible.
9. **Review the team.** As Robin, open Team overview. The initial week has Planned 8, Held 4, Moved 2, Cancelled 1, Awaiting decision 1. Planned includes held. Filter Alex: 6, 3, 2, 1, 1. Reset first if previous scenarios changed data.
10. **Use a phone.** At 390px width, open the navigation menu. The agenda becomes one column, dialogs fit the viewport and customer/week tables scroll within their own region. Navigate by keyboard, dismiss dialogs with Escape and use `/` to focus customer search.
11. **Inspect the reusable UI.** Open Design library. Its buttons open the actual shared forms and its badges come from the same renderer used in the app.

The calendar week selector is a fixed demonstration week, not a general scheduling widget. Choose All visits to see appointments outside that week.
