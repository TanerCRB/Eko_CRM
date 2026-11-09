package org.eko_crm.keycloak.events;

import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;

import jakarta.persistence.EntityManager;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.jpa.EventEntity;

public final class FilteringJpaEventStoreProviderTest {
    private static Object persisted;

    private static EntityManager entityManager() {
        return (EntityManager) Proxy.newProxyInstance(
                EntityManager.class.getClassLoader(),
                new Class<?>[] {EntityManager.class},
                (proxy, method, args) -> {
                    if (method.getName().equals("persist")) {
                        persisted = args[0];
                        return null;
                    }
                    if (method.getReturnType().equals(boolean.class)) {
                        return false;
                    }
                    if (method.getReturnType().equals(int.class)) {
                        return 0;
                    }
                    return null;
                });
    }

    private static Event event(EventType type, String realm, String code, String session) {
        Event event = new Event();
        event.setType(type);
        event.setRealmName(realm);
        event.setSessionId(session);
        Map<String, String> details = new HashMap<>();
        details.put("code_id", code);
        details.put("username", "synthetic-account");
        event.setDetails(details);
        return event;
    }

    private static Event loginError(String realm, String error, String userId, String session) {
        Event event = new Event();
        event.setType(EventType.LOGIN_ERROR);
        event.setRealmName(realm);
        event.setSessionId(session);
        event.setError(error);
        event.setUserId(userId);
        Map<String, String> details = new HashMap<>();
        details.put("username", "synthetic-marker");
        details.put("code_id", "synthetic-id");
        event.setDetails(details);
        return event;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void deliver(Event event) {
        persisted = null;
        new FilteringJpaEventStoreProvider(null, entityManager()).onEvent(event);
        require(persisted instanceof EventEntity, "inherited JPA persist did not run");
    }

    private static void filteredBeforePersistAndSubsequentDelivery(Event event) {
        deliver(event);
        require(!event.getDetails().containsKey("code_id"), "subsequent local delivery is unfiltered");
        String json = ((EventEntity) persisted).getDetailsJson();
        require(json != null && json.contains("username"), "required audit detail was removed");
        require(!json.contains("code_id"), "non-excepted code_id reached EVENT_ENTITY");
    }

    private static void masterSessionIdCleared(Event event) {
        deliver(event);
        require(event.getSessionId() == null, "subsequent local delivery kept the master sessionId");
        require(((EventEntity) persisted).getSessionId() == null,
                "session identifier reached EVENT_ENTITY outside the accepted scope");
    }

    private static void unknownAccountUsernameRemoved(Event event) {
        deliver(event);
        require(!event.getDetails().containsKey("username"),
                "unknown-account typed username survived subsequent local delivery");
        require(!((EventEntity) persisted).getDetailsJson().contains("synthetic-marker"),
                "unknown-account typed username reached EVENT_ENTITY");
        require(event.getSessionId() == null, "master LOGIN_ERROR kept the top-level sessionId");
    }

    public static void main(String[] args) {
        // Accepted code_id exception and the realm-agnostic non-excepted removal (unchanged rules).
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN_ERROR, "eko", "synthetic-id", null));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.RESET_PASSWORD_ERROR, "eko", "synthetic-id", null));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "master", "synthetic-id", "synthetic-id"));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "eko", "synthetic-id", "different-id"));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "eko", "", ""));

        Event accepted = event(EventType.LOGIN, "eko", "synthetic-id", "synthetic-id");
        deliver(accepted);
        require(accepted.getDetails().get("code_id").equals("synthetic-id"), "accepted duplicate was removed");
        require(((EventEntity) persisted).getDetailsJson().contains("code_id"), "accepted duplicate was not persisted");
        // The accepted duplicate requires the same event's accepted top-level sessionId to survive.
        require("synthetic-id".equals(accepted.getSessionId()), "accepted top-level sessionId was cleared");

        // S-01 / G-01 (ADR-0005 addendum 2026-11-05, ADR-0007-C5): no session identifier on a
        // master-realm stored event outside the accepted application-realm exception.
        masterSessionIdCleared(event(EventType.LOGIN, "master", null, "master-session-value"));
        masterSessionIdCleared(event(EventType.LOGOUT, "master", null, "master-session-value"));

        // S-01 accepted-path counter-check: the application realm keeps the exception for its
        // Retention-required types only.
        Event ekoRequired = event(EventType.LOGIN, "eko", null, "application-session-value");
        deliver(ekoRequired);
        require("application-session-value".equals(((EventEntity) persisted).getSessionId()),
                "accepted application-realm sessionId did not reach EVENT_ENTITY");
        Event ekoNotRequired = event(EventType.CLIENT_LOGIN, "eko", null, "application-session-value");
        deliver(ekoNotRequired);
        require(((EventEntity) persisted).getSessionId() == null,
                "non-Retention application event kept the top-level sessionId");

        // G-01: the unknown-account typed username exists only at the accepted D-5 path. The
        // provider keys on the event's own user_not_found error: master-realm (and any other
        // realm's) unknown-account LOGIN_ERROR loses details.username and its top-level
        // sessionId; a known-account failure keeps the username (base rule; the bootstrap's
        // live verification carrier relies on it); the eko realm is the accepted exception.
        unknownAccountUsernameRemoved(loginError("master", "user_not_found", null, "master-session-value"));
        Event ekoUnknown = loginError("eko", "user_not_found", null, "application-session-value");
        deliver(ekoUnknown);
        require("synthetic-marker".equals(ekoUnknown.getDetails().get("username")),
                "the accepted D-5 details.username path was removed");
        require("application-session-value".equals(ekoUnknown.getSessionId()),
                "the accepted application-realm sessionId was removed");
        Event carrier = loginError("master", "invalid_user_credentials", "synthetic-user-id", "master-session-value");
        deliver(carrier);
        require("synthetic-marker".equals(carrier.getDetails().get("username")),
                "known-account master LOGIN_ERROR lost its username (indiscriminate removal)");

        // Empty or absent error is not a proven unknown-account failure: the username remains
        // (the destination runtime scans prove no unknown marker reaches the store; the field
        // rule is the named exception class, not every LOGIN_ERROR).
        Event silent = loginError("master", null, "synthetic-user-id", "master-session-value");
        deliver(silent);
        require(silent.getDetails().containsKey("username"), "unrelated LOGIN_ERROR lost its username");
        require(silent.getSessionId() == null, "master event kept the top-level sessionId");
    }
}
