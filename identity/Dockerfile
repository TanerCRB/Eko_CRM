# syntax=docker/dockerfile:1
FROM maven:3.9.14-eclipse-temurin-21 AS provider-build
WORKDIR /workspace
COPY provider/pom.xml pom.xml
RUN mvn -q dependency:go-offline
COPY provider/src src
# The provider behavior test executes in this Maven stage against the pinned Keycloak 26.8.1
# provided dependencies resolved by Maven (the official image is JRE-only and its class layers
# are not a supported interface; see the accepted Architect correction of 2026-11-06). A
# non-zero exit of the test fails this RUN, and therefore the image build.
RUN mvn -q package && mvn -q dependency:build-classpath -Dmdep.outputFile=target/classpath.txt && java -cp "target/classes:target/test-classes:$(cat target/classpath.txt)" org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderTest

FROM quay.io/keycloak/keycloak:26.8.1
COPY --chown=keycloak:keycloak --chmod=644 --from=provider-build /workspace/target/eko112-event-store-1.0.0.jar /opt/keycloak/providers/
# Timestamp normalization per the official container guide (reproducible builds): the build's
# provider last-modified tracking configuration then does not depend on the building machine's
# clock. The provider is in place before the build, which selects the same-ID custom factory.
RUN touch -d "@0" /opt/keycloak/providers/eko112-event-store-1.0.0.jar && /opt/keycloak/bin/kc.sh build --spi-events-store--provider=jpa
