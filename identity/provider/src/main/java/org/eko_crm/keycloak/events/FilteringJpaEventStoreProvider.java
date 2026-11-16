package org.eko_crm.keycloak.events;

import jakarta.persistence.EntityManager;
import java.util.Set;
import org.keycloak.events.Details;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.jpa.JpaEventStoreProvider;
import org.keycloak.models.KeycloakSession;

public final class FilteringJpaEventStoreProvider extends JpaEventStoreProvider {

    // The accepted exceptions (ADR-0005 addenda of 2026-11-05; ADR-0007-C3 and C5) are limited to
    // the application realm. Keycloak's container logs, master-realm events and admin events
    // contain no session identifier and no unknown-account typed username (G-01, S-01), so this
    // store clears the prohibited fields on every event outside the accepted scope before the
    // single inherited persist. Admin events (onEvent(AdminEvent)) are inherited unchanged: the
    // stored admin-event representation carries no top-level session identifier field and records
    // operations on resolved resources, never an unknown-account typed login value; the
    // destination scans prove that at runtime.

    private static final String APPLICATION_REALM = "eko";
    private static final String UNKNOWN_ACCOUNT_ERROR = "user_not_found";

    // The authentication types required by ADR-0005 Retention, as exported in identity/eko-realm.json.
    // The accepted top-level sessionId exception applies only to a stored application-realm event of
    // one of these types; every other stored event loses the field before persisting. Keycloak 26.8.1
    // has no USER_DISABLED_BY_BRUTE_FORCE type (see the gate-2 record); its absence here matches the
    // reachable store and changes no accepted rule.
    private static final Set<EventType> REQUIRED_TYPES = Set.of(
            EventType.LOGIN,
            EventType.LOGIN_ERROR,
            EventType.LOGOUT,
            EventType.UPDATE_PASSWORD,
            EventType.UPDATE_PASSWORD_ERROR,
            EventType.RESET_PASSWORD,
            EventType.RESET_PASSWORD_ERROR,
            EventType.SEND_RESET_PASSWORD,
            EventType.REFRESH_TOKEN_ERROR);

    public FilteringJpaEventStoreProvider(KeycloakSession session, EntityManager entityManager) {
        super(session, entityManager);
    }

    @Override
    public void onEvent(Event event) {
        boolean applicationRealm = APPLICATION_REALM.equals(event.getRealmName());

        // Accepted duplicate path: application-realm LOGIN whose non-empty details.code_id equals
        // the same event's non-empty accepted top-level sessionId. Every other code_id is removed
        // before storage and subsequent local delivery (ADR-0007-C3). Read sessionId first: the
        // top-level clear below must not decide this exception.
        if (event.getDetails() != null && event.getDetails().containsKey(Details.CODE_ID)) {
            String codeId = event.getDetails().get(Details.CODE_ID);
            boolean accepted = applicationRealm
                    && event.getType() == EventType.LOGIN
                    && codeId != null
                    && !codeId.isEmpty()
                    && codeId.equals(event.getSessionId());
            if (!accepted) {
                event.getDetails().remove(Details.CODE_ID);
            }
        }

        // Top-level user-session identifier: permitted only in an application-realm event of a
        // Retention-required type; cleared on master-realm events and on any other destination.
        if (!applicationRealm || event.getType() == null || !REQUIRED_TYPES.contains(event.getType())) {
            event.setSessionId(null);
        }

        // Unknown-account typed username: permitted only at application-realm LOGIN_ERROR
        // details.username (accepted D-5 exception). On any other realm, a LOGIN_ERROR whose
        // error is user_not_found is by definition "a failed login naming no existing account",
        // so its typed username is removed before persisting. A known-account LOGIN_ERROR keeps
        // its username under the base rule (staff account username may appear in events), which
        // also keeps the bootstrap's live verification carrier identifiable.
        if (!applicationRealm
                && event.getType() == EventType.LOGIN_ERROR
                && UNKNOWN_ACCOUNT_ERROR.equalsIgnoreCase(event.getError())
                && event.getDetails() != null) {
            event.getDetails().remove(Details.USERNAME);
        }

        super.onEvent(event);
    }
}
