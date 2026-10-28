#!/bin/sh
# The walking skeleton's backup service takes no backup: producing, encrypting and shipping sets
# is EKO-1-14's. It only refuses to start without its required secret (ADR-0004-C10).
set -eu

if [ -z "$(printenv BACKUP_DB_PASSWORD | tr -d '[:space:]')" ]; then
  echo "configuration error: missing or empty environment variable: BACKUP_DB_PASSWORD" >&2
  exit 1
fi

echo "backup: no backup is configured in this release (EKO-1-14)"
trap 'exit 0' TERM INT
while :; do
  sleep 3600 &
  wait $!
done
