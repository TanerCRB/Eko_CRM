# syntax=docker/dockerfile:1
# Built from the pinned PostgreSQL image so pg_dump matches the server's major version (ADR-0004).
FROM postgres:18.6-trixie
COPY --chmod=0755 entrypoint.sh /usr/local/bin/eko-backup-entrypoint.sh
USER postgres
ENTRYPOINT ["/usr/local/bin/eko-backup-entrypoint.sh"]
