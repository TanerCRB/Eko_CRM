# ADR-0007 — Keycloak authentication-event field filtering

**Status:** Accepted 2026-11-06
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

ADR-0005 requires a closed set of application-realm authentication events while prohibiting session
identifiers in stored events except for its accepted local-only deviations. The EKO-1-12 diagnostic
found ten events with non-empty `details.code_id`: two `LOGIN` events have an equal non-empty
same-event top-level `sessionId`; six `LOGIN_ERROR` and two `RESET_PASSWORD_ERROR` events have no
top-level `sessionId`. The accepted `LOGIN details.code_id` exception therefore remains usable for
its narrow case, but the pending same-event draft cannot cover the other eight carriers.

The values and semantics of `details.code_id` are not established for every required event type or
for other Keycloak versions. This decision must remove prohibited field material before local
storage without inferring broader privacy semantics, removing required audit events, or widening
the accepted exceptions for top-level `sessionId`, `LOGIN details.code_id`, or unknown-login
`LOGIN_ERROR details.username`.

The authorized official-source assessment for Keycloak 26.8.1 establishes that the built-in JPA
store serializes the complete details map and that the supported realm and provider configurations
do not expose selective authentication-event detail filtering before that store. The event manager
calls the store before invoking listeners, so a listener cannot remove a field from the JPA copy.
The official 26.8.1 API lists `JpaEventStoreProvider` as the only known `EventStoreProvider`
implementation. Alternative listener/store implementations require a custom provider and are
outside option B.

## Decision

**B is closed for Keycloak 26.8.1.** No supported configuration or built-in persistence mechanism
in the inspected official image satisfies B's selective pre-storage filtering and sole-local-copy
boundary. The previous conditional recommendation of B is withdrawn. This does not claim that
custom code could not change the behavior; it establishes that such a change is outside B.

**A is selected and accepted on 2026-11-06**, together with its paired ADR-0003/ADR-0004 addenda.
A has a supported source-level custom-provider replacement path, but no concrete provider has been
implemented or verified. The acceptance approves the architectural direction and its evidence
duties, not runtime capability.

The selected mechanism is subject to these common boundaries:

- Filtering occurs before the prohibited value reaches any local event store. An unfiltered shadow
  store does not satisfy the decision.
- Every application-realm authentication event type required by ADR-0005 *Retention* remains
  stored with every required audit field and its accepted retention period. Successful
  `REFRESH_TOKEN` and `CODE_TO_TOKEN` events remain excluded. Removing an event type or required
  audit field is not a privacy remedy.
- The selected mechanism removes `details.code_id` wherever ADR-0005 prohibits it. It does not
  introduce a field-only exception for unclassified `code_id` values.
- The accepted local-only exceptions remain separate and unchanged:
  - a required application-realm authentication event may carry the Keycloak user-session
    identifier only at top-level `sessionId` under ADR-0005's accepted addendum;
  - an application-realm `LOGIN` event may carry only the exact non-empty same-event duplicate at
    `details.code_id` under its accepted addendum;
  - an unknown-account application-realm `LOGIN_ERROR` event may carry the typed username only at
    `details.username` under the accepted D-5 addendum.
- No exception extends to container logs, master-realm events, admin events, another field or event
  type, or an off-server copy. No credential, token, authorization code, cookie, password,
  authentication-session identifier, application session identifier, or unknown typed username
  receives a new exception.
- ADR-0005-C11 and all off-server prohibitions remain unchanged. Shipping must omit top-level
  `sessionId`, `details.code_id` wherever present, and unknown-account `LOGIN_ERROR
  details.username`, while retaining every field required off-server. Raw replication of a locally
  permitted field is non-compliant. Shipping remains EKO-1-09.
- A provider, custom image, service, persistent store, network path, or configuration mechanism is
  not authorized until the selected option and every required ADR-0003/ADR-0004 addendum are
  accepted by the human.
- Official version-pinned documentation or source must establish the selected identity-product
  interface and its compatibility with Keycloak 26.8.1. Runtime evidence must then establish the
  complete event, privacy, bootstrap, and recovery boundary. Absence of that evidence leaves the
  option unproven rather than feasible by assumption.

### Official 26.8.1 source assessment

All sources below are official Keycloak documentation or source pinned to 26.8.1. Findings describe
code behavior and exposed configuration, not merely similarly named settings.

| Official source | Relevant finding |
|---|---|
| [Server Administration Guide 26.8.1 — auditing and event configuration](https://www.keycloak.org/docs/26.8.1/server_admin/) | Documents save/expiration and event-type controls, `eventsListeners`, logging/email listeners, and admin-event representation. It documents no authentication-event detail-field selector. |
| [`RealmEventsConfigRepresentation`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/core/src/main/java/org/keycloak/representations/idm/RealmEventsConfigRepresentation.java) | The configuration model contains only `eventsEnabled`, `eventsExpiration`, `eventsListeners`, `enabledEventTypes`, `adminEventsEnabled`, and `adminEventsDetailsEnabled`. |
| [`RealmManager.updateRealmEventsConfig`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/managers/RealmManager.java) and [`RealmAdminResource.updateRealmEventsConfig`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/resources/admin/RealmAdminResource.java) | The update path applies those six settings, validates listener IDs, and delegates to the realm model. It supplies no detail-field filtering path. |
| [`EventBuilder`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventBuilder.java), `send`/`sendNow` | Obtains the store independently of realm listeners. `sendNow` calls `targetStore.onEvent(event)` before tracing and before every listener's `onEvent(event)`. `enabledEventTypes` gates only whether the store receives the type. `removeDetail` is a programmatic builder method, not a supported realm configuration. |
| [`JpaEventStoreProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProvider.java), `onEvent`/`convertEvent`/`setDetails` | Persists the event and serializes `event.getDetails()` as a complete map into `detailsJson`; there is no key exclusion before persistence. |
| [`JpaEventStoreProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProviderFactory.java) | Uses provider ID `jpa`; its empty `init` exposes no field-filtering configuration. Its [service registration](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/resources/META-INF/services/org.keycloak.events.EventStoreProviderFactory) names this factory. |
| [26.8.1 `EventStoreProvider` Javadoc](https://www.keycloak.org/docs-api/26.8.1/javadocs/org/keycloak/events/EventStoreProvider.html) | Lists `JpaEventStoreProvider` as the only known implementation. The 26.8.1 [`EventListenerProvider` Javadoc](https://www.keycloak.org/docs-api/26.8.1/javadocs/org/keycloak/events/EventListenerProvider.html) separately lists logging, email, JPA, and workflow listeners. |
| [Server Developer Guide 26.8.1 — Event Listener SPI](https://www.keycloak.org/docs/26.8.1/server_development/) | Describes an internal SPI whose behavior can change between releases and directs implementation and deployment of a custom provider. That is option A, not supported configuration within the unmodified official image. |
| [`JBossLoggingEventListenerProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/log/JBossLoggingEventListenerProvider.java) and [factory](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/log/JBossLoggingEventListenerProviderFactory.java) | `success-level`, `error-level`, `sanitize`, `quotes`, and `include-representation` govern only log output. The provider iterates every event detail; these options do not filter JPA or selectively deny `code_id`. |
| [`EmailEventListenerProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/email/EmailEventListenerProvider.java) and [factory](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/events/email/EmailEventListenerProviderFactory.java) | `include-events`/`exclude-events` select event types for email only. They do not alter JPA or provide field filtering. |
| [`WorkflowsEventListenerFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/models/workflow/WorkflowsEventListenerFactory.java) and [`WorkflowEventListener`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/models/workflow/WorkflowEventListener.java) | The feature-gated global listener receives the same event after the store and dispatches workflow events. It offers no pre-JPA field-filtering configuration. |
| [`LoginActionsService`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/resources/LoginActionsService.java), [`AuthenticationProcessor`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/authentication/AuthenticationProcessor.java), [`AuthenticationManager`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/managers/AuthenticationManager.java), and [`ResetCredentialEmail`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/authentication/authenticators/resetcred/ResetCredentialEmail.java) | Inspected login/reset producers call `detail(Details.CODE_ID, ...)` directly. Reset email exposes only its force-login setting. These call sites offer no supported selective `code_id` omission setting; this is not a claim that every producer or event type has been exhaustively enumerated. |

**Outcome classification.** The supported JPA/realm configuration is **proven unsupported for B**
by the positive persistence and configuration evidence above. The logging, email, workflow, and
builder interfaces are **present but do not satisfy B**. No mechanism was found that is **supported
and satisfies B**. An uninspected or future version is **not established** by this assessment; no
claim is made about another Keycloak release. Confidence is high for the 26.8.1 built-in event
storage and supported configuration paths inspected, not a claim that arbitrary modification of the
image is impossible.

### Official 26.8.1 assessment of A

The human authorized assessment of A only, not its implementation or acceptance. The sources below
establish a narrow custom-provider replacement path; they do not prove a concrete provider or image.

| Official 26.8.1 source | Relevant finding |
|---|---|
| [`EventStoreSpi`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/server-spi-private/src/main/java/org/keycloak/events/EventStoreSpi.java) | SPI name is `eventsStore`; `isInternal()` is true. The [private-SPI notice](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/documentation/server_development/topics/partial-private-spi.adoc) says a new release may change an internal SPI without prior notice. |
| [Server Developer Guide — SPI implementation and override](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/documentation/server_development/topics/providers.adoc) | A provider requires factory/provider implementations and a `META-INF/services` factory file. It documents unique IDs plus explicit defaults, and overriding a built-in factory with the same ID and a higher `order()`. Only the highest-order same-ID implementation is used. |
| [Configuring providers](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/guides/server/configuration-provider.adoc) | `--spi-events-store--provider=<id>` selects one provider at build time; `--spi-events-store--provider-default=<id>` selects a default. Provider JARs go in `providers/` and require a build for an optimized image. Provider code is unsandboxed and shares the application class loader. |
| [Container guide](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/docs/guides/server/containers.adoc) and [Developer Guide preface](https://www.keycloak.org/docs/26.8.1/server_development/) | A customized image includes provider JARs in `/opt/keycloak/providers` before `kc.sh build`; the official 26.8.1 image uses OpenJDK 21. |
| [`DefaultProviderLoader`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/provider/DefaultProviderLoader.java) and [`ProviderManager.compareFactories`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/provider/ProviderManager.java) | Java `ServiceLoader` loads registered factories. Same-ID factories are resolved by higher `order()`, then a custom rather than internal factory. |
| [`DefaultKeycloakSessionFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/DefaultKeycloakSessionFactory.java), `loadFactories`/`checkProvider`/`resolveDefaultProvider`/`invalidate` | Loads the selected factory, applies configured/default/highest-order selection, throws when an explicitly selected provider is missing, and sends invalidation to every registered handler. A same-ID higher-order override leaves the built-in factory out of that ID's registry entry. |
| [`DefaultKeycloakSession.getProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/services/src/main/java/org/keycloak/services/DefaultKeycloakSession.java) | Creates and caches the selected provider by provider class and optional ID. `EventBuilder` therefore receives the selected event-store provider, not every available store. |
| [`JpaConnectionProvider`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/connections/jpa/JpaConnectionProvider.java) and [`JpaEventStoreProviderFactory`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/jpa/src/main/java/org/keycloak/events/jpa/JpaEventStoreProviderFactory.java) | JPA access uses a different provider class and returns the session `EntityManager`. The event factory implements `InvalidationHandler`; on `JPA_EVENT_STORE` it casts the active store to `JpaEventStoreProvider` and invokes admin-event expiry. |
| [`ClearExpiredAdminEvents`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/storage-private/src/main/java/org/keycloak/services/scheduled/ClearExpiredAdminEvents.java) and [`ClearExpiredEvents`](https://raw.githubusercontent.com/keycloak/keycloak/26.8.1/model/storage-private/src/main/java/org/keycloak/services/scheduled/ClearExpiredEvents.java) | Scheduled admin expiry triggers the invalidation above; authentication-event expiry calls the active store's `clearExpiredEvents()`. Both belong to the replacement contract. |

#### Supported architectural path

A custom image can register an `EventStoreProviderFactory` through
`META-INF/services/org.keycloak.events.EventStoreProviderFactory`, retain the built-in ID `jpa`, and
use an order higher than the built-in factory. The documented override and actual loading/session
source establish that the custom factory, rather than a second concurrently active store, is used.
The custom store must be a `JpaEventStoreProvider` subtype so that the existing admin-expiry cast
remains valid and the inherited query, admin-event, and authentication-expiry behavior remains
available.

Before calling the inherited `onEvent`, the custom store must remove every non-excepted
`details.code_id` from the event that will be persisted and subsequently delivered. The inherited
method then performs its single `EntityManager.persist(convertEvent(event))` on the filtered event.
This preserves the same `EVENT_ENTITY` store and avoids a second unfiltered JPA store. Filtering a
clone used only for persistence would not satisfy A because `EventBuilder.sendNow` subsequently
passes the original event to tracing and listeners.

The path needs no added service or new store. It does require custom provider code and a custom
image, and it relies on an internal SPI and built-in implementation classes with upgrade risk.
Source-level selection and persistence are established; runtime correctness, complete event
coverage, privacy, and failure handling are not.

#### Paths that do not satisfy A or remain unproven

- An ordinary `EventListenerProvider` **does not satisfy A**: it runs after the store.
- Calling `session.getProvider(EventStoreProvider.class)` from the custom store **does not satisfy
  A**: it resolves the active cached store and recurses into itself. Requesting built-in `jpa` from
  a separate custom provider instead creates another provider instance and leaves the built-in
  factory registered; it is not an acceptable delegation boundary.
- An independent unique-ID replacement that leaves the built-in JPA factory registered **does not
  satisfy A as shown**: the built-in invalidation handler casts the active custom store to
  `JpaEventStoreProvider`. A non-subtype fails that contract.
- Directly constructing a JPA delegate is **technically plausible but unproven** as a supported
  wrapping contract. The sources provide no supported event-store wrapper/decorator API. The path
  above therefore relies on the documented built-in-provider override and subtype contract, not on
  an inferred wrapper.
- Provider failure during event persistence is not caught by `EventBuilder.sendNow`, but the
  resulting request/transaction/security behavior is **not established** by that fact alone. A
  missing explicitly configured provider throws during selection; however, if a same-ID custom
  override is absent, built-in `jpa` remains available. There is no evidence here that the absence
  of the custom override fails closed, so selection must be verified before listeners open.

### Required impact of each remaining mechanism class

**A — Provider in a custom Keycloak image.** The narrow path above requires dated ADR-0003 and
ADR-0004 addenda because ADR-0003 selects the official container image and ADR-0004 names that image
for `keycloak`. Draft addenda are attached, conditional on human acceptance of A and of each other.
They authorize no implementation by themselves. Every upgrade must reassess the internal SPI and
subtype boundary. The accepted service list, database, backup, and restore scope can remain
unchanged only because this path uses the existing JPA event store.

**C — Composition-level filtering before storage.** This requires a dated ADR-0004 addendum for
any added service or image and for its service list, private networking and ports, environment and
secrets, persistent volumes, deployment, bootstrap, backup, restore, and recovery. The existing
backup covers the application and Keycloak databases only; a different event store is not covered
by implication. Bootstrap and recovery must establish that no listener opens while an unfiltered
path is active. ADR-0003 also needs an addendum if the composition path depends on a custom
provider or image. ADR-0005 remains unchanged only if the filtered store is the sole local event
copy and reviewer access and retention remain intact.

### Evidence that can change the recommendation

A is now the only option with an established source-level custom-provider path, but its concrete
provider remains technically plausible and unproven until runtime verification. A failed selection,
privacy, event-field, query, retention, failure, bootstrap, restart, or restore check closes the
candidate as implemented and returns it to the human. If the internal-SPI/custom-image cost is
unacceptable, C still needs its own official-source assessment and D remains the evidence-preserving
default. Only new official 26.8.1 evidence identifying a supported pre-storage field-filtering
mechanism in the unmodified image could reopen B.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. Provider in a custom Keycloak image — source-level path established, runtime unproven** | Custom provider/image maintenance; internal-SPI upgrade risk; ADR-0003/ADR-0004 deviations; selection, failure, event, expiry, and recovery proof | Claiming to use the official image unchanged; an ordinary listener or unsupported JPA wrapper as the mechanism |
| **B. Product-supported persistence or filtering within the official image — closed for 26.8.1** | The built-in store persists the full details map; supported realm/provider settings have no pre-storage detail selector, and listeners run after the store | Selecting B for Keycloak 26.8.1; new official evidence for that exact version would be required to reopen it |
| **C. Composition-level filtering before storage** | ADR-0004 service/composition deviation and possible ADR-0003 provider/image deviation; new state, backup, restore, bootstrap, and recovery duties | Keeping the accepted service, volume, backup, and recovery boundaries unchanged |
| **D. Select no mechanism and keep EKO-1-12 stopped** | K-04 cannot pass and the task cannot complete | A privacy or audit-coverage weakening presented as a workaround |

A field-only local exception for all `details.code_id` carriers is not an option: the eight
non-`LOGIN` carriers have no same-event counterpart and their general semantics are unestablished.
Removing `LOGIN_ERROR`, `RESET_PASSWORD_ERROR`, or any other required event type is also not an
option.

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0007-C1 | The accepted decision and its paired addenda name the selected mechanism class and cite official version-pinned documentation or source establishing its Keycloak 26.8.1 interface and compatibility; the repository records no provider, image, service, dependency, or runtime change outside that accepted boundary. |
| ADR-0007-C2 | Against the running final configuration, the local application-realm event store contains every authentication event type named by ADR-0005 *Retention*, each with event type, realm, time, client, account where applicable, IP address, and error where applicable, with the accepted retention; successful `REFRESH_TOKEN` and `CODE_TO_TOKEN` remain absent. |
| ADR-0007-C3 | For every required event type exercised, no local stored event contains `details.code_id` except an application-realm `LOGIN` event whose non-empty value exactly equals its non-empty accepted top-level `sessionId`; the accepted top-level `sessionId` and unknown-account `LOGIN_ERROR details.username` exceptions remain limited to their existing paths, and no other local event copy contains material prohibited by ADR-0005-C5. |
| ADR-0007-C4 | Disabling or removing only the selected filtering mechanism makes the privacy check fail; removing a required event type or required audit field also fails, and non-empty known-account and accepted-path contrasts prove that event inspection is not satisfied by an empty store. |
| ADR-0007-C5 | Keycloak container logs, master-realm events, and admin events contain no session identifier, unknown-account typed username, token, authorization code, cookie value, password, or other material prohibited by ADR-0005; the independent D-5 check runs and reports separately even when another privacy assertion fails. |
| ADR-0007-C6 | Every off-server application-realm event omits top-level `sessionId`, `details.code_id` wherever present, and unknown-account `LOGIN_ERROR details.username`, while retaining every field ADR-0005 requires off-server; no locally permitted value is raw-replicated. |
| ADR-0007-C7 | The rendered composition and images match the accepted ADR-0003/ADR-0004 addenda for the selected option, including pinned images, the closed service list, private networking and published ports, environment-only configuration, named-volume state, and secret-free tracked files and images. |
| ADR-0007-C8 | Fresh-bootstrap, restart, backup, and restore checks establish that the selected event path retains every required event and the same field-level privacy boundary; no listener opens while an unfiltered path is active, and any event state outside the two existing databases is explicitly covered by the accepted backup and restore decision. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->

- None.
