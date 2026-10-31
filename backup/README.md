# backup

The `backup` service takes one backup set a day at 01:00 UTC and on demand, encrypts it on the
server to the IT department's public key and writes it to the IT department's destination. The
design is the ADR-0004 addendum of 2026-10-30
([ADR-0004](../docs/architecture/decisions/ADR-0004-deployment-and-recovery.md)). This file is the
**one place** where the interface that operators and the IT department's monitoring read is
written down. A change to the failure line's form is a change to that addendum.

## Run a backup now

This is step 1 of a deployment. It runs one backup in a one-off container of the `backup`
service, with that service's environment, and starts no other service. Run it from the
directory of `compose.yaml`, with the same `--env-file` (and project name) as the running
composition:

<!-- on-demand-command -->
```sh
docker compose run --rm --no-deps backup eko-backup run
```

It exits 0 only once the set at the destination is complete (below). Any other exit status is a
failed run, and its one failure line is the last thing it writes to the terminal.

## The failure line

Every failed run, scheduled or on demand, exits non-zero and writes exactly one line to standard
error: the container log for a scheduled run, the terminal for an on-demand run. The line holds
nothing else: no tool's message, no host, address, port, account, path or connection string, no
credential and no row value.

```text
eko-backup: run failed reason=<reason> set=<set name, or -> at=<RFC 3339 UTC time>[ sqlstate=<SQLSTATE>]
```

Its exact pattern (an extended regular expression, matching the whole line):

<!-- failure-line-pattern -->
```regex
^eko-backup: run failed reason=(schedule|database|lock|dump-application|dump-keycloak|dump-roles|encryption|destination|interrupted) set=(eko-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{16}|-) at=[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z( sqlstate=[0-9A-Z]{5})?$
```

| `reason` | What failed |
|---|---|
| `schedule` | the scheduler refused to start: the schedule file holds no entry, more than one, or a zone other than UTC, or the container's zone is not UTC |
| `database` | a connection to the database server, or its authentication, a refusal for the connection limit included (`sqlstate=53300`) |
| `lock` | taking or releasing the advisory lock shared with `migrate` |
| `dump-application` | the application database's snapshot, revision, row counts, dump or manifest; without the operator step below, `sqlstate=42501` |
| `dump-keycloak` | Keycloak's database dump; a table lock it waited for more than 180 s, `sqlstate=57014` |
| `dump-roles` | the dump of the cluster's roles |
| `encryption` | encrypting an object to the public key (for example a malformed key) |
| `destination` | the destination: unreachable, refused, a wrong host key, an upload broken off, or a size the destination did not confirm |
| `interrupted` | the run was stopped (`SIGTERM`, for example `docker compose stop`) |

`sqlstate` is the server's SQLSTATE where the failure carries one. A set named in a failure line
is incomplete and is not a backup set; the destination's own housekeeping removes it.

A variable that `backup` needs and that is unset, empty or whitespace-only stops the container
before any connection with `configuration error: missing or empty environment variable: <NAME>`.
That is a refusal to start, not a failed run.

A successful run writes one line and no failure line:

```text
eko-backup: run succeeded set=<set name> started=<RFC 3339 UTC> ended=<RFC 3339 UTC> row_counts=<JSON object>
```

## A set at the destination

A set `eko-<backup point as YYYYMMDDTHHMMSS.ffffffZ>-<16 hexadecimal digits>` is five files in
the destination's incoming directory:

| File | Holds |
|---|---|
| `<set>.application.dump.age` | the application database, `pg_dump` custom format |
| `<set>.keycloak.dump.age` | Keycloak's database, `pg_dump` custom format |
| `<set>.roles.sql.age` | the cluster's roles without passwords (`pg_dumpall --roles-only --no-role-passwords`) |
| `<set>.manifest.json.age` | `format`, `set`, `backup_point` (UTC), `alembic_revision`, `images`, `row_counts` |
| `<set>.complete` | the completion record, written last, in plaintext |

The four `.age` files are age v1 (binary), each to the one configured X25519 recipient. The
completion record has one line per encrypted object, `<name> <size in bytes> <SHA-256 of the bytes
as uploaded>`, separated by single spaces. A set is **complete** only when its record exists,
lists exactly those four objects, and each one is at the destination with exactly the recorded
size and digest. Anything else under a set name is incomplete and is not a backup set. This holds
for the 26-hour check, the monthly verification and a restore. The check needs no private key.

## Existing volumes: the operator step

The release that brings this service grants `eko_backup` read access by explicit grants: `USAGE`
on schema `public` and `SELECT` on its tables and sequences in both databases, plus default
privileges for the role that owns each database (`eko_app` in `eko`, `eko_keycloak` in
`keycloak`), so tables those roles create later are readable with no new grant. `eko_backup`
belongs to no predefined role, so it cannot read `pg_authid` or any password verifier. A new
`pgdata` volume gets the grants from the init content. On a volume that an earlier release
initialised, run the two blocks below once, as the PostgreSQL superuser on the running `postgres`
service, before the first backup: the first connected to `eko`, the second connected to
`keycloak`.

<!-- existing-volume-step-eko -->
```sql
GRANT USAGE ON SCHEMA public TO eko_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO eko_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_app GRANT SELECT ON TABLES TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_app GRANT SELECT ON SEQUENCES TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_app GRANT USAGE ON SCHEMAS TO eko_backup;
REVOKE pg_read_all_data FROM eko_backup;
```

<!-- existing-volume-step-keycloak -->
```sql
GRANT USAGE ON SCHEMA public TO eko_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO eko_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_keycloak GRANT SELECT ON TABLES TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_keycloak GRANT SELECT ON SEQUENCES TO eko_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE eko_keycloak GRANT USAGE ON SCHEMAS TO eko_backup;
```

For example: `docker compose exec -T postgres psql -U postgres -d eko -v ON_ERROR_STOP=1` with
the first block on standard input, then the same with `-d keycloak` and the second block. The
`REVOKE` brings a volume first initialised with an earlier content of this release, which granted
`pg_read_all_data`, to the same state; on any other volume it changes nothing beyond a warning.
Without the step, a run fails with `reason=dump-application` and `sqlstate=42501`. Running it
again changes nothing.

What the grants do not cover fails closed, never as a set that silently lacks an object: a table
or sequence created by another role (the superuser by hand, for example), on an existing volume
an object in a schema other than `public`, or a large object. The run then fails with
`reason=dump-application` or `reason=dump-keycloak` and `sqlstate=42501`.

## Configuration

`backup` receives these variables from `compose.yaml`; each is required, and none has a default:

| Variable | Holds |
|---|---|
| `BACKUP_DB_PASSWORD` | `eko_backup`'s database password (secret) |
| `BACKUP_DESTINATION_CREDENTIAL` | the destination account's Ed25519 key in OpenSSH format, base64 on one line (secret) |
| `BACKUP_ENCRYPTION_PUBLIC_KEY` | the age recipient, one line beginning `age1` (secret by inventory) |
| `BACKUP_DESTINATION` | `sftp://<account>@<host>:<port>/<incoming directory>` |
| `BACKUP_DESTINATION_HOST_KEY` | the destination host's Ed25519 public key line, as in its `/etc/ssh/ssh_host_ed25519_key.pub` (`ssh-ed25519 AAAA…`); the run verifies that key, whatever other host keys the destination offers, and accepts no other |

The private key that decrypts a set is never given to the composition.
