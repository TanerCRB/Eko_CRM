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

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void filteredBeforePersistAndSubsequentDelivery(Event event) {
        persisted = null;
        new FilteringJpaEventStoreProvider(null, entityManager()).onEvent(event);
        require(!event.getDetails().containsKey("code_id"), "subsequent local delivery is unfiltered");
        require(persisted instanceof EventEntity, "inherited JPA persist did not run");
        String json = ((EventEntity) persisted).getDetailsJson();
        require(json != null && json.contains("username"), "required audit detail was removed");
        require(!json.contains("code_id"), "non-excepted code_id reached EVENT_ENTITY");
    }

    public static void main(String[] args) {
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN_ERROR, "eko", "synthetic-id", null));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.RESET_PASSWORD_ERROR, "eko", "synthetic-id", null));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "master", "synthetic-id", "synthetic-id"));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "eko", "synthetic-id", "different-id"));
        filteredBeforePersistAndSubsequentDelivery(event(EventType.LOGIN, "eko", "", ""));

        Event accepted = event(EventType.LOGIN, "eko", "synthetic-id", "synthetic-id");
        persisted = null;
        new FilteringJpaEventStoreProvider(null, entityManager()).onEvent(accepted);
        require(accepted.getDetails().get("code_id").equals("synthetic-id"), "accepted duplicate was removed");
        require(((EventEntity) persisted).getDetailsJson().contains("code_id"), "accepted duplicate was not persisted");
    }
}
