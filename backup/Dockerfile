# syntax=docker/dockerfile:1
# Built from the pinned PostgreSQL image so pg_dump matches the server's major version (ADR-0004).
FROM postgres:18.6-trixie
# Exact trixie package versions (ADR-0004 addendum 2026-10-30): age encrypts each object, curl
# streams it to the destination over SFTP, and openssh-client holds the credential in ssh-agent
# and confirms what the destination received.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      age=1.2.1-1+b5 \
      curl=8.14.1-2+deb13u7 \
      openssh-client=1:10.0p1-7+deb13u4 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /etc/eko-backup /run/eko-backup \
 && chown postgres:postgres /run/eko-backup
COPY --chmod=0644 schedule /etc/eko-backup/schedule
COPY --chmod=0755 entrypoint.sh /usr/local/bin/eko-backup-entrypoint.sh
COPY --chmod=0755 eko-backup /usr/local/bin/eko-backup
USER postgres
ENTRYPOINT ["/usr/local/bin/eko-backup-entrypoint.sh"]
CMD ["eko-backup", "schedule"]
