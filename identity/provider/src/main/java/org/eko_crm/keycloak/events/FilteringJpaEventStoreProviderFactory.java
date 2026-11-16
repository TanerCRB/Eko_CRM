package org.eko_crm.keycloak.events;

import jakarta.persistence.EntityManager;
import org.keycloak.connections.jpa.JpaConnectionProvider;
import org.keycloak.events.EventStoreProvider;
import org.keycloak.events.jpa.JpaEventStoreProviderFactory;
import org.keycloak.models.KeycloakSession;

public final class FilteringJpaEventStoreProviderFactory extends JpaEventStoreProviderFactory {
    @Override
    public EventStoreProvider create(KeycloakSession session) {
        EntityManager entityManager = session.getProvider(JpaConnectionProvider.class).getEntityManager();
        return new FilteringJpaEventStoreProvider(session, entityManager);
    }

    @Override
    public int order() {
        return 100;
    }
}
