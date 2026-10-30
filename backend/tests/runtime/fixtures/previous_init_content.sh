# Test fixture (EKO-1-14): compose.yaml's init content before pg_read_all_data was granted.
# Sourced by the image's entrypoint (config modes are ignored outside Swarm): no `set -u`,
# prefixed names, and `exit 1` stops the first initialisation with a non-zero exit.
eko_missing=""
for eko_name in APP_DB_PASSWORD KEYCLOAK_DB_PASSWORD BACKUP_DB_PASSWORD; do
  eko_value="$${!eko_name:-}"
  if [ -z "$${eko_value//[[:space:]]/}" ]; then eko_missing="$$eko_missing $$eko_name"; fi
done
if [ -n "$$eko_missing" ]; then
  echo "eko-init: configuration error: missing or empty environment variable(s):$$eko_missing" >&2
  exit 1
fi
unset eko_missing eko_name eko_value
psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$$POSTGRES_USER" --dbname postgres <<'SQL'
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
\getenv app_password APP_DB_PASSWORD
\getenv keycloak_password KEYCLOAK_DB_PASSWORD
\getenv backup_password BACKUP_DB_PASSWORD
CREATE ROLE eko_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 30 PASSWORD :'app_password';
CREATE ROLE eko_keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 25 PASSWORD :'keycloak_password';
CREATE ROLE eko_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 5 PASSWORD :'backup_password';
CREATE DATABASE eko OWNER eko_app ENCODING 'UTF8'
  LOCALE_PROVIDER icu ICU_LOCALE 'pl-PL' TEMPLATE template0;
CREATE DATABASE keycloak OWNER eko_keycloak ENCODING 'UTF8' TEMPLATE template0;
REVOKE CONNECT, TEMPORARY ON DATABASE eko FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE keycloak FROM PUBLIC;
GRANT CONNECT ON DATABASE eko TO eko_backup;
GRANT CONNECT ON DATABASE keycloak TO eko_backup;
SQL
# Written last: its absence marks a volume whose first initialisation did not complete.
touch "$$PGDATA/eko-init-complete"
