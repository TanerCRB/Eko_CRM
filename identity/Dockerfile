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
# The boot-token carrier mount path (ADR-0004-C33, addendum 2026-11-10), seeded byte-for-byte
# as proxy/Dockerfile seeds it (dir 755 owner 1000:1000, one 644 placeholder): whichever of
# the two containers first attaches the empty named volume leaves the directory owned by
# uid/gid 1000 — this image's own user — so the entrypoint wrapper in compose.yaml can
# rotate the token at every container start. The base image's USER is keycloak (uid 1000),
# so the /etc write runs under root and the user is restored after it.
USER root
RUN mkdir -p /etc/eko/keycloak-boot && chown 1000:1000 /etc/eko/keycloak-boot && chmod 755 /etc/eko/keycloak-boot && printf '%s\n' 'seed placeholder: the boot token lives at /etc/eko/keycloak-boot/token, rotated by the Keycloak entrypoint wrapper' > /etc/eko/keycloak-boot/.seed && chown 1000:1000 /etc/eko/keycloak-boot/.seed && chmod 644 /etc/eko/keycloak-boot/.seed
USER keycloak
