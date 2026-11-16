# syntax=docker/dockerfile:1
# The entry point image: pinned Caddy with the release's routing configuration (ADR-0004).
# The digest pins the base the release names (ADR-0004 addendum 2026-10-28, B-01; C29).
FROM caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e
COPY Caddyfile Caddyfile.admin Caddyfile.closed /etc/caddy/
# The boot-identity helper (ADR-0004-C33 marker binding, addendum 2026-11-10): the entrypoint
# calls it to compare each gate marker against the boot token of the running Keycloak — a
# pure file read of the shared carrier below — and scripts/keycloak-bootstrap.sh execs it so
# the value open_gate records is observed from inside this network, never from host metadata.
COPY keycloak-boot-identity.sh /usr/local/bin/eko-keycloak-boot-identity.sh
COPY entrypoint.sh /usr/local/bin/eko-proxy-entrypoint.sh
RUN chmod 755 /usr/local/bin/eko-proxy-entrypoint.sh /usr/local/bin/eko-keycloak-boot-identity.sh
# The boot-token carrier mount path, seeded exactly as identity/Dockerfile seeds it (dir
# 755 owner 1000:1000, one 644 placeholder): whichever of the two containers first attaches
# the empty named volume leaves the directory owned by uid/gid 1000, so the Keycloak
# container's wrapper can always rotate the token. Byte-identical content in both images is
# what makes the first-attach order immaterial.
RUN mkdir -p /etc/eko/keycloak-boot && chown 1000:1000 /etc/eko/keycloak-boot && chmod 755 /etc/eko/keycloak-boot && printf '%s\n' 'seed placeholder: the boot token lives at /etc/eko/keycloak-boot/token, rotated by the Keycloak entrypoint wrapper' > /etc/eko/keycloak-boot/.seed && chown 1000:1000 /etc/eko/keycloak-boot/.seed && chmod 644 /etc/eko/keycloak-boot/.seed
ENTRYPOINT ["/usr/local/bin/eko-proxy-entrypoint.sh"]
