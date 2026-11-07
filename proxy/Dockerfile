# syntax=docker/dockerfile:1
# The entry point image: pinned Caddy with the release's routing configuration (ADR-0004).
# The digest pins the base the release names (ADR-0004 addendum 2026-10-28, B-01; C29).
FROM caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e
COPY Caddyfile Caddyfile.admin Caddyfile.closed /etc/caddy/
COPY entrypoint.sh /usr/local/bin/eko-proxy-entrypoint.sh
RUN chmod 755 /usr/local/bin/eko-proxy-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/eko-proxy-entrypoint.sh"]
