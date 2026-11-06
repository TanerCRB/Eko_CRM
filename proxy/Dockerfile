# syntax=docker/dockerfile:1
# The entry point image: pinned Caddy with the release's routing configuration (ADR-0004).
FROM caddy:2.11.7
COPY Caddyfile Caddyfile.admin Caddyfile.closed /etc/caddy/
COPY entrypoint.sh /usr/local/bin/eko-proxy-entrypoint.sh
RUN chmod 755 /usr/local/bin/eko-proxy-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/eko-proxy-entrypoint.sh"]
