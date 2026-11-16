# EKO-1-12 inherited expiry probe through the custom store — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)
Image: `localhost/eko-crm/keycloak:26.8.1-eko112` (`sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`)

## What was probed (G-03 / K-04 expiry halves)

The Keycloak 26.8.1 expiry paths for stored events, exercised against the selected custom
same-ID provider through the real composition:

- authentication expiry: the periodic `ClearExpiredEvents` task calls
  `EventStoreProvider.clearExpiredEvents()` on the selected provider — inherited unchanged
  by the custom subtype (JPA source read: it deletes `EventEntity` rows per realm where
  `eventsExpiration > 0`, by `event.time`);
- admin expiry: the periodic `ClearExpiredAdminEvents` task calls
  `KeycloakSession.invalidate(PeriodicEventInvalidation.JPA_EVENT_STORE)`; the built-in
  factory's `invalidate` handler **casts the selected provider to `JpaEventStoreProvider`**
  and calls `clearExpiredAdminEvents()` — the accepted compatibility boundary ADR-0007 names
  ("JPA subtype preserving the admin-expiry cast"); the custom subtype satisfies the cast.

Mechanism pre-observation (throwaway standalone Keycloak on the same custom image, H2 not
used — postgres, master realm with `eventsExpiration=60s`/`adminEventsExpiration=60s`,
rows time-travelled by SQL): the periodic cycle deleted the time-travelled rows of both
kinds and left the fresh controls; the cycle ran on the server's default schedule
(`scheduled.interval` default 900 s). The image for that probe predates the provider
field-enforcement rebuild; the expiry code path is provider-inherited and does not read the
filtered fields, but the committed test below re-observes it on the final image.

## Command and result

```
uv run pytest -m runtime tests/runtime/test_eko112_k04_event_expiry.py -q
1 passed in 1003.79s (0:16:43)   (2026-11-08, final image 387f615a…)
```

## Observed behaviour (final image)

- planted and aged (SQL `event_time`/`admin_event_time` shifted): the oldest application-realm
  `LOGIN_ERROR` past 30 days, the oldest master `LOGIN` past 90 days, and the oldest eko-realm
  and master-realm admin events past 90 days; the newest of each set stayed un-aged as the
  control;
- the server's own periodic tasks removed exactly the four aged rows (2 authentication,
  2 admin) and preserved the controls: `after_auth == before_auth - 2` and
  `after_admin == before_admin - 2` (plain-SQL row counts), and every surviving row is still
  within its realm retention via the reviewer-visible admin reads
  (`eko: LOGIN_ERROR control present, all rows < 30 d; master: LOGIN control present,
  all rows < 90 d; eko and master admin-event ids: aged id gone, control present`);
- a `2026-11-08` live cross-check during the run confirmed the aged rows visible
  (`31 days` / `91 days`) before the task cycle and gone after — the removal is the
  inherited `ClearExpiredEvents` (auth) and the factory's `JPA_EVENT_STORE` invalidation
  handler (`clearExpiredAdminEvents`, the accepted admin-expiry cast) running on the selected
  custom subtype, not a bypass;
- both listener gates passed the provider verification pair in the same run before opening.

## Limits

Local composition only; the 900 s default schedule means wall-clock duration varies with
where in the cycle the test starts (bounded wait of 1500 s asserted in the test). No
production timing claim. Synthetic accounts only; no event body, identifier or credential
value appears here.
