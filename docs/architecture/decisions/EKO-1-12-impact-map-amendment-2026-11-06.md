# Impact-map amendment — EKO-1-12 / Issue #53 — 2026-11-06

**Verdict: REQUIRES A HUMAN DECISION**

Basis for this A source-assessment revision: HEAD
`8442e0e2a8e734c6ca165c4111af3119fc9bc11f` and the pre-existing dirty worktree read on
2026-11-06. Earlier draft/source bases were `81404401b9d58b0cd237078f6c3f4fa729484284` and
`840fa036bf429498c5324e615d2acd958b0c5e69`; the latest intervening commit is cost-register
bookkeeping only. Pre-existing modified files remain `backend/tests/runtime/conftest.py`,
`compose.yaml`, `proxy/Dockerfile`, `scripts/dev-env.sh`, and accepted-addendum carriers ADR-0003,
ADR-0004, and ADR-0005. Pre-existing untracked implementation, tests, fixtures, identity
configuration, proxy/bootstrap files, `docs/evidence/`, and `tests/doc-checks/EKO-1-12.sh` also
remain. No clean, reset, commit, or push was performed.

## Task

Determine from official Keycloak 26.8.1 sources whether option A provides a supported custom-provider
path that removes non-excepted `details.code_id` before every local event store, including built-in
JPA, while preserving every required event and audit field and adding no service or new store.

*Done when:* “Every runtime condition below is demonstrated by a passing check against the running
composition, with a contrast that fails when the protection being checked is removed or the required
order is reversed.” K-04 remains stopped.

The human first rejected the disproved same-event `details.code_id == sessionId` draft as
sufficient, selected B only for official-source assessment, and then selected A **only for
official-source evidence assessment**. Neither direction accepted ADR-0007, selected an
implementation, authorized a runtime probe, or chose a fallback.

## Evidence read

Repository evidence:

- `.task/issue-gate1.md`, especially the locked Definition of done, explicit out-of-scope list, and
  K-01..K-07; K-04 contains the now-disproved conditional same-event draft.
- `.task/handoff/4-architect-9.md`, the prior rejection analysis.
- `.task/handoff/7-developer-infrastructure-diagnostic-3.md`, the synthetic-safe projection, its ten
  carriers, destination results, and explicit limits.
- `docs/evidence/EKO-1-12/session-path-stop.md` and `session-event-stop.md`, the earlier accepted
  `LOGIN` finding and the later non-`LOGIN` STOP.
- `docs/PLAN.md`, the decision index linking ADR-0001 through ADR-0006.
- `docs/architecture/decisions/TEMPLATE.md`, ADR-0003, ADR-0004, ADR-0005, and
  `docs/architecture/capabilities.md`.
- `docs/architecture/architecture-sensitive-paths.md`, for the identity, composition, image, and
  personal-data boundaries.

Official Keycloak 26.8.1 documentation/source inspected:

- [Server Administration Guide 26.8.1](https://www.keycloak.org/docs/26.8.1/server_admin/): user and
  admin event save/expiration settings, event types, listener IDs, logging/email listeners, and
  admin representation; no authentication-event detail-field selector is documented.
- [Server Developer Guide 26.8.1](https://www.keycloak.org/docs/26.8.1/server_development/): the
  Event Listener SPI is internal and requires implementing/deploying a custom provider.
- [26.8.1 `EventStoreProvider` Javadoc](https://www.keycloak.org/docs-api/26.8.1/javadocs/org/keycloak/events/EventStoreProvider.html):
  `JpaEventStoreProvider` is the only known implementation.
- [26.8.1 `EventListenerProvider` Javadoc](https://www.keycloak.org/docs-api/26.8.1/javadocs/org/keycloak/events/EventListenerProvider.html):
  separately lists logging, email, JPA, and workflow listeners.
- [`RealmEventsConfigRepresentation`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/core/src/main/java/org/keycloak/representations/idm/RealmEventsConfigRepresentation.java):
  exactly the six event/admin configuration fields; no detail filter.
- [`RealmManager`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/managers/RealmManager.java),
  `updateRealmEventsConfig`, and [`RealmAdminResource`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/resources/admin/RealmAdminResource.java),
  `updateRealmEventsConfig`: apply those fields and validate listener IDs; no field-filter path.
- [`EventBuilder`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventBuilder.java),
  `send`/`sendNow`: store selection is independent of listeners; JPA receives the event before
  tracing and listeners; `enabledEventTypes` gates store event types, not detail keys.
- [`JpaEventStoreProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java),
  `onEvent`/`convertEvent`/`setDetails`: persists the full details map as JSON.
- [`JpaEventStoreProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProviderFactory.java):
  ID `jpa`, empty `init`; its [service registration](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/resources/META-INF/services/org.keycloak.events.EventStoreProviderFactory)
  names that factory.
- [`EventStoreProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventStoreProvider.java)
  and [`EventStoreProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventStoreProviderFactory.java):
  store SPI contracts, not a built-in alternative.
- [`EventListenerProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventListenerProvider.java)
  and [`EventListenerProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventListenerProviderFactory.java):
  listener contract and global-listener switch, not a pre-store filter.
- [`JBossLoggingEventListenerProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/log/JBossLoggingEventListenerProvider.java)
  and [factory](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/log/JBossLoggingEventListenerProviderFactory.java):
  log levels, sanitization, quotes, and representation only; every details entry is logged when
  enabled, and JPA is unaffected.
- [`EmailEventListenerProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/email/EmailEventListenerProvider.java)
  and [factory](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/email/EmailEventListenerProviderFactory.java):
  event-type inclusion for email only; JPA and detail keys are unaffected.
- [`WorkflowsEventListenerFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/models/workflow/WorkflowsEventListenerFactory.java)
  and [`WorkflowEventListener`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/models/workflow/WorkflowEventListener.java):
  feature-gated global listener receives the event after the store and schedules workflows; no
  pre-store filter.
- [`Event`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/Event.java)
  and [`EventEntity`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/EventEntity.java):
  in-memory details map and database details-JSON fields.
- [`Details`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/Details.java):
  `CODE_ID` is the key `code_id`; the name alone is not used as semantic evidence.
- [`LoginActionsService`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/resources/LoginActionsService.java),
  [`AuthenticationProcessor`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/authentication/AuthenticationProcessor.java),
  [`AuthenticationManager`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/managers/AuthenticationManager.java),
  and [`ResetCredentialEmail`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/authentication/authenticators/resetcred/ResetCredentialEmail.java):
  inspected producers set `Details.CODE_ID` directly; no supported selective omission setting was
  found in those paths. This is not an exhaustive producer or event-type claim.

Additional official 26.8.1 sources for A:

- [`EventStoreSpi`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventStoreSpi.java)
  and the [private-SPI notice](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/documentation/server_development/topics/partial-private-spi.adoc):
  SPI name `eventsStore`, internal status, and no-prior-notice upgrade risk.
- [Server Developer Guide — providers](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/documentation/server_development/topics/providers.adoc):
  factory/provider and service-file registration, unique/default IDs, and same-ID higher-order
  built-in override.
- [Configuring providers](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/guides/server/configuration-provider.adoc):
  `--spi-events-store--provider=<id>`, `--spi-events-store--provider-default=<id>`, build-time
  provider registry, and the unsandboxed full-privilege provider warning.
- [`MicroProfileConfigProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/configuration/MicroProfileConfigProvider.java)
  and [`ConfigArgsConfigSource`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/configuration/ConfigArgsConfigSource.java):
  mapping of SPI/provider/property names into `kc.spi-events-store--provider` and CLI options.
- [Container guide](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/guides/server/containers.adoc)
  and [Developer Guide preface](https://www.keycloak.org/docs/26.8.1/server_development/): provider
  JARs before `kc.sh build` in a custom image and OpenJDK 21 in the official image.
- [`DefaultProviderLoader`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/provider/DefaultProviderLoader.java)
  and [`ProviderManager`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/provider/ProviderManager.java):
  Java service loading, highest-order same-ID selection, and custom-over-internal tie behavior.
- [`ProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi/src/main/java/org/keycloak/provider/ProviderFactory.java):
  default `order()` 0, factory lifecycle, and dependency contracts.
- [`DefaultKeycloakSessionFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/DefaultKeycloakSessionFactory.java)
  and [`DefaultKeycloakSession`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/DefaultKeycloakSession.java):
  configured/default provider selection, missing-selection exception, per-session provider cache,
  and invalidation broadcast.
- [`JpaConnectionProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/connections/jpa/JpaConnectionProvider.java):
  session `EntityManager` access through a different provider class.
- [`ClearExpiredAdminEvents`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/storage-private/src/main/java/org/keycloak/services/scheduled/ClearExpiredAdminEvents.java),
  [`ClearExpiredEvents`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/storage-private/src/main/java/org/keycloak/services/scheduled/ClearExpiredEvents.java),
  and [`PeriodicEventInvalidation`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/storage-private/src/main/java/org/keycloak/storage/datastore/PeriodicEventInvalidation.java):
  scheduled authentication/admin expiry and the JPA invalidation path that the replacement must
  preserve.
- [`JpaEventQuery`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventQuery.java)
  and [`JpaAdminEventQuery`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaAdminEventQuery.java):
  reviewer query contracts over the same JPA entities.
- [`EventListenerTransaction`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventListenerTransaction.java)
  and [`KeycloakTransactionManager`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi/src/main/java/org/keycloak/models/KeycloakTransactionManager.java):
  listener commit/rollback handling and transaction-manager contracts; neither supplies a pre-JPA
  listener filter.

No `main`, `latest`, another release, third-party source, runtime event/log, credential, marker, or
private infrastructure was used.

## Confirmed evidence and limits

- Ten observed events contain non-empty `details.code_id`.
- Two `LOGIN` carriers have equal, non-empty, same-event top-level `sessionId` values.
- Six `LOGIN_ERROR` and two `RESET_PASSWORD_ERROR` carriers have no top-level `sessionId`.
- No carrier value occurred at another field on its own event, in master/admin events, or in
  container logs. Some cross-event matches exist, but not for every carrier; they do not satisfy the
  rejected same-event condition.
- Only `LOGIN`, `LOGIN_ERROR`, `LOGOUT`, and `RESET_PASSWORD_ERROR` were observed. Values and
  semantics for every required event type and other Keycloak versions remain unestablished.
- The accepted local `LOGIN details.code_id == sessionId` exception remains unchanged and covers
  only its own narrow case. The accepted application-realm top-level `sessionId` and unknown-login
  `LOGIN_ERROR details.username` exceptions also remain unchanged.
- The 26.8.1 JPA path serializes the full details map before any listener invocation. Supported
  realm and built-in provider configuration does not remove a selected detail key before JPA.
- No off-server copy exists in this task; off-server runtime behavior remains unchecked.

## Affected decisions

| Decision | Title | Resolution | Justification |
|---|---|---|---|
| ADR-0003 | Identity server, browser session, roles and account lifecycle | Draft addendum prepared for A; B cannot fit for 26.8.1; C conditionally needs an addendum | *Identity server product*: “The identity server is **Keycloak**, run as its official container image.” The 2026-11-06 draft records the custom-image deviation and internal event-store SPI boundary; accepted text is unchanged. |
| ADR-0004 | Deployment, HTTPS exposure, secrets, backup and restore | Draft addendum prepared for A; C needs an addendum | *Composition and placement*: “The composition consists of exactly these services.” The 2026-11-06 draft keeps the same service/database/store and adds custom-image build, selection, listener, release, and recovery conditions; accepted text is unchanged. |
| ADR-0005 | Personal data: holders, logging, retention, archiving and erasure | Fits only for a mechanism that filters before every local copy; unchanged | *What may appear in logs* prohibits “Keycloak's session and authentication-session identifiers”; *Retention* requires the closed authentication event set; *Keycloak events off the server* says each copied event “carries no … session or authentication-session identifier.” The three accepted local exceptions remain separate and unchanged. |
| ADR-0007 | Keycloak authentication-event field filtering | New decision required; B closed; A source-level path established but runtime unproven | The official 26.8.1 source assessment excludes B and establishes the narrow same-ID/higher-order JPA-subtype path for A. `ADR-0007-keycloak-event-filtering.md` remains `Draft — pending approval`; no concrete provider/image is verified. |

## Requires a human decision

### Option A — Provider in a custom Keycloak image

**Outcome: a supported source-level architectural path is established; the concrete provider remains
technically plausible but unproven at runtime.** The compliant path is narrower than a generic
listener or independent store:

1. Register a custom `EventStoreProviderFactory` through
   `META-INF/services/org.keycloak.events.EventStoreProviderFactory`, retain ID `jpa`, and give it a
   higher `order()` than the built-in factory. `ProviderManager.compareFactories` selects that
   higher-order custom factory; the session factory does not retain a second factory under that ID.
2. `EventBuilder` and `DefaultKeycloakSession` therefore obtain the custom provider as the active
   store. Selecting `--spi-events-store--provider=jpa` at build time names the overridden entry.
3. The active store must be a `JpaEventStoreProvider` subtype. Before the inherited `onEvent`, it
   removes every non-excepted `details.code_id` from the event subsequently persisted and delivered.
   The inherited method then performs one JPA persist into the existing `EVENT_ENTITY` store. No
   second unfiltered JPA copy remains on this path. Filtering only a persistence clone would leave
   the original event for tracing/listeners and would not satisfy A.
4. The subtype preserves the built-in query/admin/authentication-expiry methods and satisfies the
   JPA factory's invalidation cast. `ClearExpiredAdminEvents` triggers that cast through
   `JPA_EVENT_STORE`; `ClearExpiredEvents` invokes the active store directly.
5. The custom JAR is included before `kc.sh build` in the custom image. The SPI is internal and may
   change without notice; provider code is unsandboxed and has server-process privileges.

- **Delegation finding:** calling `session.getProvider(EventStoreProvider.class)` within the custom
  store resolves the same cached active store and recurses. Requesting built-in `jpa` from a
  separate provider creates another provider and leaves the built-in factory registered. No
  supported event-store wrapper/decorator contract was established. Directly constructing a JPA
  delegate is technically plausible but unproven and is not the path drafted here.
- **Does not satisfy A:** ordinary listeners; an independent unique-ID replacement leaving the JPA
  factory's cast active; or a clone-only filter leaving downstream local delivery unfiltered.
- **Failure behavior:** an explicitly configured missing provider throws during selection, and an
  event-store exception is not caught by `sendNow`. Neither fact establishes the complete request or
  privacy outcome. If the custom same-ID override is absent, built-in JPA remains available; absence
  is not shown to fail closed. Custom selection and filtering must be verified before listeners open.
- **ADR-0003/0004 impact:** conditional dated `Draft — pending approval` addenda are now attached
  for the custom image, provider override, build, release, listener, and recovery boundaries. They
  select nothing without human acceptance.
- **ADR-0005 impact:** unchanged. All required event types/fields, retention, reviewer evidence,
  accepted local exceptions, and off-server omissions remain binding.
- **Runtime evidence still required:** actual factory registration/order/selection; sole-store and
  downstream filtering; all required events/fields; query/admin behavior; both expiry paths;
  missing-provider and persistence-failure behavior; custom-image build; bootstrap/restart/restore;
  and upgrade compatibility.

### Option B — Closed for Keycloak 26.8.1

B is **proven unsupported for the required selective pre-storage filtering within the inspected
supported 26.8.1 paths**:

- `EventBuilder.sendNow` calls `targetStore.onEvent(event)` before tracing and listeners, so a
  listener cannot remove a field from the JPA copy.
- `JpaEventStoreProvider.convertEvent` serializes `event.getDetails()` in full; its factory exposes
  no filtering setting, and the 26.8.1 API lists it as the only known event-store implementation.
- The realm configuration exposes only enablement, expiration, listener IDs, enabled event types,
  and admin-representation switches. No detail-field selector reaches the store.
- Logging, email, and workflow interfaces are **present but do not satisfy B**. Event Listener and
  Event Store SPI customization requires a custom provider and therefore belongs to A, not B.
- `EventBuilder.removeDetail` is a programmatic builder method, not a supported realm setting.
  Inspected producers set `CODE_ID` directly. This does not assert that every producer was
  exhaustively reviewed.

Confidence is high for the built-in 26.8.1 event storage and supported configuration paths
inspected. This is not a claim that arbitrary modification is impossible or that another/future
release behaves identically. Only new official 26.8.1 evidence of a supported pre-storage selector
in the unmodified image could reopen B.

### Option C — Composition-level filtering before storage

Use a composition-level mechanism that receives events through a supported identity-product path,
filters them, and stores the filtered events as the sole local copy.

- **ADR-0003 impact:** the official product/image remains only if the emitting path needs no custom
  provider or image; otherwise a dated ADR-0003 addendum is also required. Official support for the
  emitting path must be cited either way.
- **ADR-0004 impact:** requires a dated addendum for any new service or image and its exact service
  list, networking and ports, environment/secrets, persistent volumes, deployment, bootstrap,
  backup, restore, and recovery. Existing backup of two databases and existing restore steps do not
  cover a separate event store. Listener opening must not race an unfiltered path.
- **ADR-0005 impact:** remains unchanged only if the filtered store is the sole local event store,
  required reviewer reads and retention still work, and all off-server omissions remain. A raw
  stream, log, queue, or staging copy must not become a prohibited local event copy.
- **Evidence still required:** official support for the identity-product emission path; filtering
  before all storage; queue/staging/log privacy; reviewer access and retention; full required-event
  matrix; startup/restart/failure behavior; backup/restore and listener-order evidence.
- **Consequence:** adds the largest operational and recovery surface and changes ADR-0004's closed
  composition. It may avoid a custom Keycloak image only if an official emission path exists. No
  service, store, or runtime probe is authorized by this comparison.

### Option D — Select no mechanism and keep EKO-1-12 stopped

- **ADR impact:** ADR-0003, ADR-0004, ADR-0005, their accepted addenda, and required audit coverage
  remain unchanged.
- **Consequence:** K-04 cannot pass and EKO-1-12 cannot complete. This is preferable to accepting
  unclassified identifier material or removing required events when A–C lack evidence.

A field-only `details.code_id` exception is not offered: it would revive the rejected privacy
expansion without establishing values or semantics. Removing `LOGIN_ERROR`,
`RESET_PASSWORD_ERROR`, or any other required event type is not offered: it would weaken ADR-0005
*Retention* and required audit coverage.

## Recommendation and what would change it

**Recommend A only for gate-1 evaluation, not as an accepted or proven implementation.** It is the
only remaining option with an established source-level provider path, and its conditional
ADR-0003/ADR-0004 drafts preserve required audit and privacy boundaries. The recommendation is based
on the documented provider override and actual selection/JPA/expiry source, not on SPI existence or
Java inheritance alone. Its costs are custom trusted code, a custom image, and an internal SPI with
unannounced-change risk.

The human may accept/reject A and both paired drafts, request a separate C assessment, or retain D.
This report does not make that choice. A runtime failure of provider selection, filtering,
event/field coverage, query/expiry, failure handling, bootstrap/restart/restore, or upgrade review
returns A to the human rather than silently moving to C. C becomes a candidate only after its own
supported-path and recovery assessment. D remains the evidence-preserving default if the A costs or
runtime results are unacceptable. B remains closed unless new official 26.8.1 evidence identifies a
supported pre-storage selector in the unmodified image.

## Foundation status

The capability register proves the local development composition, PostgreSQL roles and privileges,
connection budget, composition/image controls, and local mail catcher. It explicitly says Keycloak
has no proven application realm or settings for this task and that Keycloak logs/events do not yet
meet ADR-0005. The shared profile is only rendered except for proxy-routing evidence; production
proof remains EKO-1-08.

The diagnostic is local evidence from the pre-existing dirty tree, not a capability-register entry,
independent QA proof, or final-SHA verification. Accepted ADR exceptions establish design direction
only. No provider, alternative event store, composition filter, or recovery behavior is verified.
K-04 remains stopped.

## Invariants to watch during implementation

- **Rule 1 — no prohibited values in artifacts:** projections and reports must contain no identifier
  values, markers, credentials, tokens, cookies, raw events, or raw logs; compare and report only
  paths and booleans/counts.
- **Rule 8 — accepted architecture boundaries:** provider, image, identity configuration,
  composition, listeners, storage, and future shipping must match the selected accepted ADR and
  paired addenda, not an implementation-time assumption.
- **Rule 26 — no implementation tracking in decisions:** ADR-0007 carries controls and acceptance
  criteria only; capability and verification status stay in their designated registers/reports.
- **Rule 29 — evidence chain:** final claims need non-empty contrasts and executed mutations at one
  reviewed SHA; absence of a prohibited value or an empty event store is not sufficient evidence.
- **ADR-0005 retention boundary:** every required event type and audit field remains present;
  successful token refresh and code-to-token events remain excluded.
- **ADR-0005 destination boundary:** local exceptions never extend to logs, master/admin events,
  other fields/types, or off-server copies. EKO-1-09 must omit every locally excepted field.
- **D-5 independence:** unknown-username inspection runs and reports separately even if a session
  assertion fails; neither exception widens the other.
- **Backend/frontend contract:** this task does not authorize application login or request-level
  identity behavior. If a later selected option changes the HTTP API surface, backend and frontend
  developers must agree on that contract explicitly; no such change is proposed here.

## Exact conditional Analyst changes after a human selects an option

No acceptance-criterion edit is authorized before human selection and acceptance of ADR-0007 plus
every required paired addendum. After that selection, the Analyst must amend the Issue and obtain a
new gate-1 scope lock before implementation resumes.

### Common K-04 correction for A or C

1. Remove every clause conditional on “the new `details.code_id` option A” that generalizes the
   non-empty same-event exception beyond `LOGIN`, including the corresponding Observable,
   Contrast, Mutation, Edges, Foundation, and Judged-by text. Do not alter the accepted
   `LOGIN`-only duplicate exception.
2. Keep the accepted top-level `sessionId`, accepted `LOGIN details.code_id`, and accepted D-5
   `LOGIN_ERROR details.username` rules as three separate local exceptions. Keep their existing
   wrong-field, wrong-event, wrong-realm, log, and off-server mutations.
3. Replace the stopped broader-draft requirement with the accepted ADR-0007 mechanism boundary:
   filtering before every local store; every required event type and audit field retained; no
   unfiltered shadow copy; and the exact event-type/realm/field/destination matrix of the selected
   option.
4. Retain non-empty known-account and accepted-path contrasts, independent D-5 execution, and
   mutations for filter removal/failure, required-event removal, audit-field removal, wrong field,
   wrong event type, wrong realm, logs, and off-server copies. A missing event or empty store must
   fail rather than pass as privacy.
5. Replace the Foundation statement that the broader same-event addendum remains pending with the
   accepted ADR-0007 selection and its evidence limits. Keep K-04 stopped until final-SHA runtime,
   contrast, mutation, and QA evidence exists.
6. Preserve all off-server omissions and EKO-1-09 ownership. Do not add off-server shipping to
   EKO-1-12.

### Additional changes if A is selected

- Amend the Definition of done and K-01/K-06 boundaries to include the accepted custom provider and
  image as versioned, pinned, secret-free artifacts; clarify that K-01's “no provider, service, or
  image” phrase applies only to the separate fine-grained role-mapping decision, not to the newly
  accepted event-filtering mechanism.
- Extend K-02 to prove bootstrap/restart with the accepted image and filtering active before either
  listener opens, without changing the accepted brute-force order.
- Extend K-03 to rerun administrator/reviewer and required admin/login-event checks on the final
  image with no authority expansion.
- Extend K-04 to cover provider failure, upgrade/version compatibility, and absence of an
  unfiltered JPA/secondary copy, in addition to the common privacy matrix.
- Amend K-07 so “exactly one dated addendum” refers specifically to the 2026-11-02 bootstrap-order
  addendum and does not forbid the separately accepted ADR-0003/ADR-0004 mechanism addenda. Keep
  R-22 removal exact and gate-3-only.

### If B is reconsidered

B is closed for Keycloak 26.8.1, so there are no Analyst changes to make. Do not amend K-01,
K-02, K-03, or K-04 to an official-image filtering configuration. Only new official 26.8.1
evidence sufficient to reopen B would permit a fresh architectural assessment and, after human
acceptance, a new conditional Analyst amendment.

### Additional changes if C is selected

- Amend the Definition of done and K-01/K-06 boundaries to include every accepted composition
  service/image/configuration and its secret-free, pinned, private-network, named-volume boundary.
- Extend K-02 to prove the selected filtered event path is effective before listener opening on
  fresh bootstrap and restart, preserving both accepted brute-force preconditions and their closed-
  listener contrasts.
- Extend K-03 to prove reviewer read-only access, retention, and required event/role-mapping reads
  against the filtered store, with no new write authority.
- Extend K-04 to inspect the filtered store and every queue, staging area, raw stream, log, or other
  local copy; prove sole-local-store behavior and filter-failure closed behavior in addition to the
  common matrix.
- Add explicit backup/restore acceptance coverage for any event state outside the application and
  Keycloak databases, including privacy after restore and no listener opening over an unfiltered
  path. Keep production restore proof with EKO-1-08.
- Amend K-07's singular-addendum wording as for A so the accepted ADR-0004 composition addendum and
  any required ADR-0003 addendum coexist with the distinct bootstrap-order addendum; R-22 removal
  remains exact and separate.

### If D is selected

Make no criterion amendment and resume no implementation. Record that K-04 remains stopped and all
accepted decisions and criteria remain unchanged.

## Remaining evidence and duties

1. Version-pinned official support evidence for the selected mechanism and every identity-product
   interface it uses; no runtime probe is authorized by this document.
2. Values and producer semantics for all required event types/versions only where needed to assess
   privacy; no broader semantics may be inferred from the four observed types.
3. A synthetic-safe full required-event matrix showing field paths, non-empty audit evidence,
   filtering before every local store, and destination-specific privacy without exposing values.
4. For A: runtime proof of the actual service registration, higher-order same-ID selection, custom
   subtype, filtering before the single JPA persist and subsequent local delivery, no second store,
   all event/query/admin/expiry behavior, missing-provider and persistence-failure handling,
   custom-image build/release, bootstrap/restart/restore, and every upgrade. The official source
   loading/selection path is established, but no runtime claim is established.
5. B needs no further assessment for 26.8.1 unless new official evidence for that exact version
   identifies a supported pre-storage selector; failure to find one elsewhere must not be treated as
   proof for another release.
6. For C: emission-path support, queue/staging/log privacy, sole-store behavior, reviewer access,
   startup ordering, and backup/restore of any new event state.
7. Fresh final-configuration K-02 and K-03 verification.
8. Remaining K-04 event-type, audit-field, field-path, destination, contrast, and mutation evidence,
   plus independent D-5 rerun.
9. K-05 both-order timings, mail outcomes, and human distinguishability finding.
10. QA evaluation and executed mutations at one final `VERIFIED` SHA.
11. K-07 gate-3 proposal and exact R-22 documentation action.
12. EKO-1-09 off-server omission of top-level `sessionId`, `details.code_id` wherever present, and
    unknown-account `LOGIN_ERROR details.username`, while retaining required off-server fields.

## Required process steps

1. Human selection of A, C, or D and acceptance/rejection of ADR-0007; implementation remains
   stopped. B is closed for 26.8.1 and is not a selectable implementation. A or C also requires
   acceptance of every paired ADR-0003/ADR-0004 addendum identified by the selected mechanism
   before implementation.
2. After selection, the Analyst must make the exact conditional changes above and obtain a new
   gate-1 scope lock. No current criterion change is authorized by this amendment.
3. An authorized documentation role must register the new ADR-0007 document in the decision index,
   `docs/PLAN.md`, at the appropriate gate. No dedicated documentation-publication configuration
   was found in this worktree. The Architect did not edit the index or any publication mechanism.
4. Run the documentation validator covering ADR-0007 and its index registration once that
   registration is made. The existing `tests/doc-checks/EKO-1-12.sh` checks bootstrap/timing/gate-3
   evidence and does not validate this new decision; no documentation or runtime validator was run
   by this Architect.
5. Keep all pre-existing implementation and accepted addenda intact. Any later mechanism work uses
   its own authorized implementation phase and evidence chain; this report is not that authorization.

## Draft and exact changed paths

- `docs/architecture/decisions/ADR-0007-keycloak-event-filtering.md` — updated source assessment,
  `Draft — pending approval`.
- `docs/architecture/decisions/EKO-1-12-impact-map-amendment-2026-11-06.md` — this amendment.
- `docs/architecture/decisions/ADR-0003-identity-and-access.md` — appended only the conditional
  2026-11-06 custom-image addendum, `Draft — pending approval`.
- `docs/architecture/decisions/ADR-0004-deployment-and-recovery.md` — appended only the conditional
  2026-11-06 custom-image build/startup/recovery addendum, `Draft — pending approval`.

The disproved pending ADR-0005 draft and every accepted ADR section/addendum were left untouched;
ADR-0005 itself was not edited. No provider, code, image build, service, dependency, runtime probe,
criterion, Issue, implementation, decision acceptance, capability status, commit, or push was
performed or authorized.
