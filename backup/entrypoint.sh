#!/bin/sh
# Refuses to start without a required variable, before any connection to the server or the
# destination (ADR-0004-C10); a whitespace-only value counts as empty.
set -eu

for name in BACKUP_DB_PASSWORD BACKUP_DESTINATION_CREDENTIAL BACKUP_ENCRYPTION_PUBLIC_KEY \
  BACKUP_DESTINATION BACKUP_DESTINATION_HOST_KEY MIGRATION_ADVISORY_LOCK_KEY \
  BACKUP_MANIFEST_BACKEND_IMAGE BACKUP_MANIFEST_KEYCLOAK_IMAGE BACKUP_MANIFEST_POSTGRES_IMAGE; do
  if [ -z "$(printenv "$name" | tr -d '[:space:]')" ]; then
    echo "configuration error: missing or empty environment variable: $name" >&2
    exit 1
  fi
done

exec "$@"
