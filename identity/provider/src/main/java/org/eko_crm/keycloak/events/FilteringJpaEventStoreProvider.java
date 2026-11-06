package org.eko_crm.keycloak.events;

import jakarta.persistence.EntityManager;
import org.keycloak.events.Details;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.jpa.JpaEventStoreProvider;
import org.keycloak.models.KeycloakSession;

public final class FilteringJpaEventStoreProvider extends JpaEventStoreProvider {
    public FilteringJpaEventStoreProvider(KeycloakSession session, EntityManager entityManager) {
        super(session, entityManager);
    }

    @Override
    public void onEvent(Event event) {
        if (event.getDetails() != null && event.getDetails().containsKey(Details.CODE_ID)) {
            String codeId = event.getDetails().get(Details.CODE_ID);
            boolean accepted = "eko".equals(event.getRealmName())
                    && event.getType() == EventType.LOGIN
                    && codeId != null
                    && !codeId.isEmpty()
                    && codeId.equals(event.getSessionId());
            if (!accepted) {
                event.getDetails().remove(Details.CODE_ID);
            }
        }
        super.onEvent(event);
    }
}
