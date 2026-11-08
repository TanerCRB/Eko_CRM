# ADR-0004 — Deployment, HTTPS exposure, secrets, backup and restore

**Status:** Accepted 2026-10-24
<!-- Only a human changes this to "Accepted <YYYY-MM-DD>". -->

## Context

ADR-0001 (Constraint 1) runs every component as a container image and forwards the container
runtime, the composition, HTTPS exposure, the static file server and secret handling to this
decision. ADR-0002 forwards the database container, its credentials, the daily off-server backup,
the restore procedure, encryption at rest, and which single process runs `alembic upgrade head` and
how expand → deploy → contract is carried out. ADR-0003 forwards one origin for the SPA and the API,
the placement of Keycloak's public pages and of its administration console (company network only),
time synchronisation, the session-encryption key, client secrets and SMTP credentials, who reads
admin events and reviews the live realm, the Keycloak database in the backup, and the bootstrap of
the first administrator and recovery when none remains. Each of these items is listed, with the
section that decides it or the task it is forwarded to, under *Items forwarded to this decision*.
The brief ([`project-brief.md`](../../product/project-brief.md), section 5) fixes the frame: an
on-premises server run by the company IT department, containerised and cloud-agnostic, reachable
from reps' phones over HTTPS under a company domain, a daily database backup kept off the server
and one tested restore before go-live. The design choices were settled by the human at gate 1 of
EKO-1-03 (Issue #16) on 2026-10-24, and the findings of that task's verification were decided by
the human on the same day.

## Decision

### Operator

The **company IT department** is the operator of every shared environment (pilot and production).
It provisions and patches the host, runs deployments, holds the secrets, receives backup and
certificate alerts, performs restores and the restore test, and carries out the duties under
*Operator duties* below. The domain and its hostnames are provided by the human later; every
hostname in this decision is a placeholder: `<company-domain>`, `<app-host>`, `<auth-host>` and
`<auth-admin-host>`. That the IT department accepts these duties is a commitment outside the
repository.

### Container runtime

The container runtime on the server is **Docker Engine with the Docker Compose v2 plugin**.

The whole composition is started, stopped and updated with `docker compose` from one composition
file kept in the repository. The images themselves are plain OCI images and the composition uses
only features of the Compose Specification, so they stay portable to another OCI runtime; that
portability is a constraint below (*Cloud-agnostic constraints*), not a second runtime choice.

### Composition and placement

All components of one environment run on **a single host**. The composition consists of exactly
these services:

| Service | Image | Role |
|---|---|---|
| `proxy` | the entry-point product (Caddy), pinned, with the release's routing configuration | the only HTTPS entry point: terminates TLS, redirects plain HTTP, routes by hostname and path, enforces the public/admin split |
| `frontend` | built from `frontend/Dockerfile` | the frontend's static file server: serves the Vite build with Caddy, plain HTTP on the internal network only, no Node.js runtime (ADR-0001-C5) |
| `backend` | built from `backend/Dockerfile` | the backend: the FastAPI web process |
| `migrate` | the same backend image | one-shot step that runs `alembic upgrade head` and exits (*Migrations*) |
| `keycloak` | the official Keycloak image, pinned (ADR-0003) | Keycloak, the identity server |
| `postgres` | the pinned PostgreSQL 18 image (ADR-0002) | the PostgreSQL server holding the application database and Keycloak's database (ADR-0003) |
| `backup` | built from the pinned PostgreSQL 18 image, so `pg_dump` matches the server's major version | the component that produces, encrypts and ships the daily backup (*Backup*) |

- **Background work.** Its mechanism is decided by ADR-0006 (EKO-1-05, #18). If ADR-0006 adds a
  worker process, it is a further service started from the backend image, it never runs
  `alembic upgrade head`, and it starts only after `migrate` has succeeded, as `backend` does.
  ADR-0006 records the added service as an addendum to this decision.
- Developer and test environments add a local mail-catching container (ADR-0003, *Password
  reset*); it is never part of a shared environment.
- **Networks and ports.** The services talk over a private network of the composition. Only `proxy`
  publishes ports on the host. `postgres`, `keycloak`, `backend`, `frontend` and `backup` publish
  none; PostgreSQL is not reachable from outside the composition.
- **Images.** Every image reference names a full version (`<major>.<minor>.<patch>`, with the base
  OS release for PostgreSQL as ADR-0002 requires) or a digest, never a floating tag. The backend and
  frontend images are built by CI from a release tag and pushed to the project's container registry;
  a release's composition references them by digest, so the image deployed is the image CI tested.
  The registry is used at deployment only; a running environment does not depend on it.
- **Clocks.** Because the backend and Keycloak run on the same host, they read the same host clock,
  so the offset between their clocks is zero and stays within the offset ADR-0003-C2 allows. The IT
  department keeps the host clock synchronised by NTP. If a later addendum places the backend and
  Keycloak on different hosts, both hosts are kept in step by NTP within the offset the backend is
  configured to allow, and that placement is a defect until this holds.
- **Connection limits.** The values of ADR-0003-C19 are set by the walking skeleton, EKO-1-06
  (#19), within this composition. The `backup` service connects with its own database role, which
  also carries a connection limit of at least the number of sessions a backup holds at the same
  time (the session holding the advisory lock, the `pg_dump` session, and the session counting rows
  inside the dump's snapshot, wherever these are separate sessions), and the limits of the
  application, Keycloak and
  backup roles together stay below `max_connections` minus `superuser_reserved_connections`. This
  is the restatement of ADR-0003-C19 recorded as ADR-0003's addendum of 2026-10-24 (*Changes to
  accepted decisions*).

### Cloud-agnostic constraints

Every component of the composition meets each of these:

1. **Portable images.** Its image is an OCI image, portable between OCI runtimes; no service relies
   on a feature specific to one runtime or one host operating system beyond the Compose
   Specification.
2. **Configuration only through the environment.** Configuration that differs between environments,
   and every secret, reach it only through environment variables (for the backend, read only in
   `backend/app/core/settings.py`, ADR-0001 Constraint 1 and ADR-0001-C10). Configuration that is
   the same in every environment is part of the release, in its image built at the release tag.
3. **State only in named volumes.** Its persistent state lives only in the named volumes of the
   composition: `pgdata` (PostgreSQL) and `proxy-data` (the entry point's certificates and ACME
   account). No service writes state to a host path.
4. **No managed cloud service.** No component depends on a cloud vendor's managed service: no
   managed database, identity, secret, logging or load-balancing service. Moving the composition to
   another host, on premises or rented, needs a host with an OCI runtime, the volumes restored from
   a backup, and the secrets.

### HTTPS exposure

- **One origin for the SPA and the API.** The single-page application and the API are served from
  one origin, `https://<app-host>`: `proxy` routes `/api/` to `backend` and every other path to
  `frontend`. The OIDC callback is a backend path on that origin.
- **Keycloak's own hostname.** Keycloak's internet-facing pages are served at `https://<auth-host>`.
  `<app-host>` and `<auth-host>` are both names under `<company-domain>`, so they are the same site:
  the login callback is a same-site navigation, and ADR-0003's `SameSite=Lax` login-transaction
  cookie works in that case as in the cross-site one.
- **What the internet reaches on `<auth-host>`.** Keycloak's login, password-reset and
  required-action pages of the application realm are reachable from the internet. The public
  listener of `proxy` forwards to Keycloak only those pages, the realm's OIDC endpoints, keys and
  discovery document under `/realms/<application-realm>/`, and the static resources those pages
  load (`/resources/`). It refuses every other request, in particular every request to `/admin/`
  (the administration console and the admin REST API for every realm, the master realm included),
  every path of the master realm (`/realms/master/`), and the account console
  (`/realms/<application-realm>/account`).
- **What only the company network reaches.** The administration console and the admin REST API, for every realm including the master realm, are reachable only from the company network.
  They are served only through a second listener of `proxy` at `https://<auth-admin-host>`, which
  refuses connections from every network other than those the IT department designates as the
  company network (the office network, and the company VPN if IT runs one). Keycloak's admin
  hostname is set to that address. The admin listener's port is published only on the host's
  company-network interface, never on an address the internet reaches, so the source-network check
  is a second guard and not the only one. A request that reaches the public listener with SNI or
  Host `<auth-admin-host>` is refused like every other request outside its allowlist.
- **The account console** is reachable from neither the internet nor the company network: both
  listeners refuse it (ADR-0003, *Names*).
- **Plain HTTP** on port 80 serves nothing except a redirect to the same URL over HTTPS and the ACME
  challenge path the certificate issuance needs. `<app-host>` sends `Strict-Transport-Security`.
- **Certificates.** `proxy` obtains and renews the publicly trusted certificates for `<app-host>`
  and `<auth-host>` automatically over ACME, and the IT department's monitoring alerts it when any
  certificate served is within 14 days of expiry. The certificate of `<auth-admin-host>`, a name not
  reachable from the internet, is provided and renewed by the IT department.
- **Brute-force protection is a precondition.** No login page of a shared environment is
  reachable from the internet until the live realm has brute-force detection on (ADR-0003, *Network
  exposure*). The master realm also has brute-force detection on before the admin listener of any
  shared environment is started.
- **Reset-response timing.** While the company mailbox does not exist, the reset e-mail is off in
  shared environments (ADR-0003, *Password reset*), so no internet-facing page sends a reset
  message and there is no timing difference to observe. The walking skeleton, EKO-1-06 (#19),
  measures against its mail catcher the response time of a reset request for a known and for an
  unknown address. If the two are distinguishable, ADR-0003's rule that the response is the same
  for both is not met, and the reset e-mail is not turned on in any shared environment until it is;
  the finding returns to the human.

### Secret handling

Every secret's **master copy is kept off the server**, in the IT department's password manager.
On the server, each component's secrets are held in an environment file outside the repository
checkout, readable only by the account that runs `docker compose` (file mode `0600`), and reach the
container only as environment variables.

Secrets are in neither the repository nor any image. The repository half: no committed file holds
a secret value — no composition file, no `.env*` file, no Dockerfile, no realm export under
`identity/` (it holds only environment placeholders, ADR-0003-C14) and no `VITE_*` variable; `.env*`
files are excluded by `.gitignore`. The image half: `.env*` files are excluded from every image
build context by every `.dockerignore`, and no build argument carries a secret.

Every shared environment has its own values; no secret is shared between pilot and production or
taken from a developer environment. A missing secret stops its component: the composition declares
each secret variable as required with no default, and `settings.py` has no default value for any
secret.

Anyone holding administrative rights over the container runtime on the server can read a running
container's environment (for example through `docker inspect`); those rights are held only by the
IT department, never by the reviewer (*Operator duties*), and are equivalent to root on the host.
No component writes a secret value to its log; what else may appear in logs is decided by
ADR-0005 (EKO-1-04, #17).

Every rotation of a secret replaces its value in the off-server master copy and in every
environment file on the server that holds it, at the same time, so a restore that takes the secrets
from the master copies (*Restore procedure*) uses the values in effect.

| Secret | Used by | Kept on the server (besides the off-server master copy) | Delivered | Readers | Rotation |
|---|---|---|---|---|---|
| PostgreSQL superuser password | `postgres` (initialisation), the operator | `postgres` environment file | environment variable of `postgres` | IT department | on suspected compromise and when a holder leaves IT |
| Application database role password | `backend`, `migrate` (and a worker, if any) | `backend` environment file | environment variable | IT department | as above; restart of `backend` and `migrate` |
| Keycloak database role password | `keycloak` | `keycloak` environment file | environment variable | IT department | as above |
| Backup database role password | `backup` | `backup` environment file | environment variable | IT department | as above |
| Session-token encryption key (ADR-0003) | `backend` | `backend` environment file | environment variable, read in `settings.py` | IT department | as above; replacing it makes every stored session undecryptable, so every user logs in again — accepted for about ten users; also at every restore (*Restore procedure*) |
| OIDC client secret of the application's client | `backend`; Keycloak stores it in its database | `backend` and `keycloak` environment files; Keycloak's database, and so every backup set | environment variable; injected into the realm at import | IT department | regenerated in Keycloak and set in `backend` together; restart of `backend`; also on compromise of the backup encryption private key |
| SMTP credentials of the company mailbox (once it exists) | `keycloak` (realm SMTP settings) | `keycloak` environment file; Keycloak's database, and so every backup set | environment variable, injected into the realm at import | IT department | when the mailbox password changes, and on compromise of the backup encryption private key |
| Keycloak bootstrap admin credential | `keycloak`, first start only | nowhere after bootstrap: removed from the environment file once used | environment variable, first start only | IT department | single use (*Bootstrap of the first administrator*) |
| Master-realm break-glass admin credentials | the holders, in person | nowhere on the server | typed into the administration console on `<auth-admin-host>` | each holder its own (*Operator duties*) | after every use and when a holder leaves; every rotation is entered in the record of account changes and re-applied at restore step 9 |
| Reviewer's read-only master-realm account credential | the reviewer | nowhere on the server | typed into the administration console on `<auth-admin-host>` | the reviewer | yearly and when the reviewer changes; every rotation is entered in the record of account changes and re-applied at restore step 9 |
| Backup encryption private key | restores and the backup verification only | **never on the server**: two copies kept off the server by the IT department | brought only to the restore host at restore step 2 and to the off-server host of the backup verification (*Backup*), both meeting the restore-host requirements (*Restore procedure*) | IT department | yearly and when a holder leaves; older backups keep their key |
| Backup encryption public key (not secret) | `backup` | `backup` environment file | environment variable | — | with the private key |
| Backup destination write credential | `backup` | `backup` environment file | environment variable | IT department | on suspected compromise |
| Container registry pull credential (read-only) | the operator at deployment | the operator's runtime login on the server | not delivered to any container | IT department | yearly |
| TLS private keys of `<app-host>` and `<auth-host>` | `proxy` | `proxy-data` volume | generated inside `proxy` by ACME, never delivered | IT department | renewed with the certificate |
| TLS private key of `<auth-admin-host>` | `proxy` | `proxy` environment file | environment variable | IT department | renewed with the certificate |
| Google OAuth client secret, Google token encryption key | — | decided by ADR-0006 (#18), task EKO-1-05 (#18) | as a class, under the rules of this section | — | ADR-0006 |

### Migrations

- **Exactly one process runs `alembic upgrade head`: the one-shot `migrate` service.** The `backend` web process, and any worker process started from the backend image, do not run it, neither at start nor at any other time.
- `migrate` runs on every deployment and every restart of the environment (every `docker compose
  up`), with no exception, a rollback to the previous release and every start of the rolled-back
  release included; `backend` (and any worker) starts only after `migrate` has
  exited with success. A restart with no new revision runs `migrate` as a no-op that changes no
  schema. A container of `backend`
  restarted alone by the runtime's restart policy does not migrate; its revision check below
  decides whether it serves.
- **Two runs at once are serialised.** `migrate` holds a PostgreSQL advisory lock on the
  application database for the whole run; a second run started meanwhile waits for the lock, then
  finds the schema at head and changes nothing.
- **`migrate` does not stall the serving release.** Once it holds the advisory lock, `migrate` runs
  its statements with a lock timeout and a statement timeout. A statement that waits longer for a
  table lock, or runs longer, fails the run; PostgreSQL rolls the revision back and the
  failed-migration rule below applies.
- **Backup and migration exclude each other.** The `backup` service takes the same advisory lock
  for the whole of its dumps. A backup therefore does not start while `migrate` runs, and `migrate`
  does not start changing the schema while a backup runs; each waits for the other to release the
  lock.
- **No code serves on a schema older than itself.** At start, `backend` (and any worker) reads the
  database's Alembic revision and exits without serving when it is not the head revision its code
  ships and not a revision that descends from that head; it never migrates. A revision older than
  that head, or one the check cannot establish as that head or a descendant of it, is always
  refused. The previous release may serve on a newer schema only within the expand → deploy →
  contract rule below.
- **`migrate` changes nothing on a newer schema.** Before it applies a revision, `migrate` reads
  the database's Alembic revision and makes the same descent check as `backend`: when the revision
  is not the head its code ships but descends from that head, `migrate` exits with success and
  changes nothing. A revision the check cannot place as that head, as a revision before it or as a
  descendant of it fails the run, and the schema is left unchanged. So a rollback to the previous
  release, every later start of that release, a secret rotation that restarts the environment and a
  restore all run `migrate` like any other start.
- **A failed migration leaves the previous release running.** PostgreSQL rolls the failing
  revision back (ADR-0002), `migrate` exits with failure, and the new `backend` is not started; the
  previous release keeps serving on the unchanged schema. At the first deployment, where no
  previous release exists, a failed migration leaves the service stopped.
- **The first deployment** runs `migrate` on an empty application database, which brings it to
  head (ADR-0002-C1).

### Deployment and expand → deploy → contract

A short, announced interruption during a deployment is acceptable. A deployment on the single host
follows these steps, announced to staff beforehand:

1. The operator runs an on-demand backup (*Backup*) and waits for it to reach the destination.
2. The operator pulls the release's images by the digests its composition names.
3. `migrate` runs while the previous release keeps serving.
4. On success, `backend` (and any worker) and `frontend` are replaced by the new release; requests
   during the replacement may fail for the seconds it takes (the announced interruption). On
   failure, nothing is replaced (*Migrations*).

A deployment does not start while the scheduled backup is running. Apart from that rule, the
advisory lock (*Migrations*) keeps a migration and a backup from running at the same time, in both
directions.

**Rollback to the previous release.** When a new release fails after its `migrate` has succeeded,
the operator starts the previous release by the digests its composition names, `migrate` first and
then `backend` (and any worker) and `frontend`: the database stays at the newer head, which
descends from the previous release's head, so the previous release's `migrate` exits with success
and changes nothing, and the previous release's revision check accepts that head (*Migrations*).
Every later start of the environment runs `migrate` in the same way. A rollback goes back to the
previous release only; going back further is a restore. This limit is a procedural rule of the
operator, not one the revision check enforces: the check accepts every revision that descends from
its code's head and does not establish how many releases lie between the two. A release that adds
or tightens an access rule (a rule restricting what a user may read or change) cannot be rolled
back; going back past it is a restore. Keycloak migrates its own schema forward when a newer
Keycloak image starts, so Keycloak has no rollback: going back to an older Keycloak image is a
restore (*Restore procedure*).

**Expand → deploy → contract** is carried out across releases in these release steps:

1. **Release N (expand).** Its migrations only add (tables, nullable or defaulted columns, indexes)
   or backfill, so the release before it keeps working on the new schema while deployment step 3
   runs, and a rollback to the previous release's images needs no schema downgrade. Its code works
   with both the old and the new shape.
2. **Deploy.** Release N is deployed as above, and the code that reads or writes the old shape is
   removed in Release N or a later release.
3. **Release N+1 or later (contract).** A migration that removes or narrows what an earlier release
   uses (dropping or renaming a column or table, adding a constraint old code violates) is a
   contract migration. It ships in a later release than its expand migration and the code change it
   follows, never in the same release, and only once no running release reads or writes the old
   shape.

No downgrade migration is run in a shared environment. Going back past a contract migration is a
restore (*Restore procedure*), not a rollback.

### Backup

- **Frequency.** A backup runs once every day at 01:00 UTC (a fixed UTC time, so a daylight-saving
  change in Europe/Warsaw neither skips nor repeats it), and on demand before every deployment.
- **Scope.** Each backup set holds the application database and Keycloak's database, dumped
  with `pg_dump` (each dump a consistent snapshot while writes continue), the cluster's roles
  without their passwords, and a manifest naming the time, the Alembic revision of the application
  database, the image references of `backend`, `keycloak` and `postgres` in use, and the row count
  of each application table, counted inside the dump's own snapshot so the counts are those of the
  dump and not of the live database.
- **Order.** The application database is dumped first and Keycloak's database second, so every
  Keycloak subject the application dump refers to exists in the Keycloak dump (ADR-0003 forbids
  deleting such an account).
- **Encryption of backups.** A backup set is encrypted on the server with the backup public key
  before it leaves the `backup` container; the private key that decrypts it is kept off the server,
  in two copies held by the IT department, and is never on the server. A compromised server
  therefore cannot read earlier backups.
- **Destination: off the server.** Each backup set is written to storage on another host operated
  by the IT department, in a different room or building where the company has one. A second disk,
  volume or directory of the server's own host is not off the server and does not count as a
  backup destination. The `backup` service's credential can add new backup sets at the destination
  but cannot delete or overwrite existing ones.
- **Retention.** The destination keeps the backup sets of the last **30 days**, and beyond them the
  last three sets that passed the monthly verification below, each until three newer sets have
  passed it; older sets are deleted by the destination's own housekeeping, not by the server.
  Personal data of customers erased in the application therefore remains in backups for up to 30
  days, and longer in those verified sets while they are older than 30 days (ADR-0005, EKO-1-04
  (#17), decides how erasure treats backups).
- **Verification off the server.** At least once every calendar month, the IT department fetches
  the newest backup set from the destination, decrypts it on a host that is not the server with the
  backup private key, and checks it against its manifest (both dumps complete and readable, every
  field of the manifest present, its row counts equal to those of the dump). The same check compares
  the set with the IT department's off-server record of account changes (*Operator duties*): the
  newest entries of that record made before the set's time are present in the set's Keycloak dump,
  a fact a compromised server cannot fabricate. The host of the check meets the restore-host
  requirements (*Restore procedure*). The result is recorded in the IT department's operations
  record, a set that fails either comparison is handled as a failed backup, and the decrypted copy
  is deleted after the check.
- **A failed or missing backup reaches the operator.** The `backup` service reports a failed run
  to the IT department's monitoring, and a check that does not run on the server (on the
  destination or in IT's monitoring) alerts the IT department when the newest backup set is older
  than 26 hours. A job that silently does not run is caught by the second check.
- **Encryption at rest of the volumes.** The server's storage holding the composition's volumes
  is encrypted at rest from installation (full-disk or volume encryption set up by the IT
  department), so a disk taken from the server reveals no data. The recovery key of that encryption
  is kept off the server in the IT department's password manager, and the unlock at boot never uses
  a key stored on the encrypted disk itself; the unlock mechanism is otherwise the IT department's
  choice.

### Restore procedure

A restore uses nothing kept only on the lost server: the backup set comes from the destination,
the private key and every secret from the IT department's off-server copies, and the composition
from the repository at the release tag.

**Restore-host requirements.** Every host that receives the backup private key or a decrypted
backup set, the restore host and the host of the monthly verification (*Backup*) alike, is held by
the company, has its disk encrypted, and is not used for e-mail or web browsing.

1. Provide a host that meets the restore-host requirements, with the container runtime and empty
   volumes (the original host, wiped, or a replacement).
2. Fetch the chosen backup set from the destination, the backup private key and the environment's
   secrets from the IT department's off-server copies, and the repository at the release tag
   currently deployed (not older than the release named in the manifest).
3. Decrypt the backup set and check it against its manifest; a set that fails is not used and the
   previous day's set is taken.
4. Start `postgres` alone, with no published port and `proxy` not started. Create the roles from the
   backup set and set their passwords from the secrets.
5. Restore the application database and then Keycloak's database, both from the same backup set,
   so the two are at mutually consistent points.
6. Compare the restored application tables' row counts with the manifest, before any migration
   runs; the restore goes on only when they are equal.
7. Start `keycloak` with the image of the release fetched in step 2, no older than the one named in
   the manifest; Keycloak migrates its own schema forward if the image is newer.
8. Start `proxy` with its admin listener on `<auth-admin-host>` and with the public listener closed
   to the internet: from this step until step 14, the public listener accepts connections only from
   the company network, as the admin listener does, and still refuses every request outside its
   allowlist. The administration console, the application and Keycloak's login pages are then
   reachable only from the company network.
9. Through that console, re-apply every account change made after the backup's time that the IT
   department's off-server record of account changes holds (*Operator duties*): every deactivation
   and role removal, so that no account disabled since the backup is active again, and every
   password reset, by disabling the account until its user receives a new temporary password under
   ADR-0003's reset rule. Also re-apply every rotation of a break-glass or reviewer credential the
   record holds, so that no value rotated out since the backup works again: the break-glass holder
   carrying out this step sets their own account's password to the value in effect, and sets every
   other such account to a temporary password handed to its holder in person, which the holder
   replaces with the value in effect at their next login. The holder carrying out this step logs in
   with the credential the restored master realm holds for their account, which is the previous
   value when theirs was rotated after the backup's time; the password manager keeps that previous
   value until no backup set from before the rotation remains at the destination. Then sign out every session
   that the restored Keycloak database holds, in the application realm and in the master realm.
10. Through the same console, set the application client's OIDC client secret and, once the company
    mailbox exists, the application realm's SMTP credentials to the values of their off-server
    master copies fetched in step 2, so that Keycloak holds the values in effect and not those of
    the backup's time.
11. Replace the session-token encryption key with a newly generated value, in the off-server master
    copy and in the `backend` environment file, so that no session restored in the application
    database can be decrypted and every user logs in again.
12. Run `migrate` with the release fetched in step 2. It brings the restored application database
    forward to the head that release ships or, when the restored revision already descends from
    that head (a set taken while a rolled-back release served), exits with success and changes
    nothing (*Migrations*). The restored data runs with that release's images, never older than
    those named in the manifest, and with the schema at that release's head or at a head descending
    from it within the expand → deploy → contract rule; it never runs on a schema older than its
    backend code.
13. Start `backend` and `frontend`. From the company network, through the public listener, which
    accepts connections only from there (step 8), log in at `https://<app-host>` with a test
    account. The restore is verified when the login works and the counts compared at step 6 are
    equal.
14. Only then open the public listener to the internet, take a fresh backup, and record the restore
    (date, backup set used, who performed it, the account changes and credential rotations
    re-applied, the Keycloak-stored secrets set at step 10) in the IT department's operations
    record.

**First tested restore.** The restore is first tested before go-live, on the provisioned production
host or a host like it, into empty volumes, from a backup set taken from the destination, by
EKO-1-08 (#36) (production provisioning and the first tested restore). Until EKO-1-08 (#36) is done,
the system does not go live. The test is repeated after every major-version upgrade of PostgreSQL
or Keycloak.

### Operator duties

- **Staffing.** The IT department staffs these duties with at least three people, so that the
  reviewer and the break-glass holders are different people.
- **Who reviews the administrator.** A person in the IT department named by it as **reviewer**
  reads the application realm's admin events and the master realm's login and admin events,
  compares the live holders of `administrator`, `manager` and `rep` with the IT department's record
  of approved assignments (*Record of account changes*), and runs the live-realm review of
  ADR-0003-C22 (and ADR-0003-C21) **every 7 days**, and after every use of a break-glass credential.
  The reviewer may not hold the application role `administrator`, and may not hold any master-realm
  role that can change the application realm. The reviewer holds no administrative rights over the
  container runtime and no PostgreSQL superuser access, and has no access to the PostgreSQL
  superuser password or to any database role password.
- **Master-realm events.** The master realm stores login events and admin events, so every login
  with a break-glass credential and every change made with one is a stored event the reviewer
  reads. Their retention is decided by ADR-0005 (EKO-1-04, #17); the reviewer's reading needs it to
  be longer than the 7-day review interval.
- **Through which account.** The reviewer reads through a dedicated read-only account in the
  **master realm** that holds only read roles of the application realm's management client in the
  master realm and of the master realm's own management client (`view-events`, `view-users`,
  `view-realm`, `view-clients`, `query-*`), and no `manage-*`, `realm-admin`, `impersonation` or
  master-realm `admin` role. With it the reviewer can see login events, admin events and role
  mappings but can neither change an account nor alter or switch off events.
- **Who holds master-realm administration.** Full master-realm administration is a **break-glass
  credential**: one named master-realm account per holder, at most two holders, both in the IT
  department and neither of them the reviewer, kept in the IT department's password manager. It is
  used only for bootstrap, recovery, realm-configuration changes from the export under `identity/`,
  and Keycloak upgrades; every use is announced to the reviewer, who reviews the events of both
  realms of that day.
- **Record of account changes.** An administrator who disables an account, removes a role, assigns
  `administrator`, `manager` or `rep`, or sets a temporary password tells the IT department at the
  time, through IT's own request system, which is not on this server; an assignment is entered
  there, with who approved it, before it is made. An assignment of `administrator`, `manager` or
  `rep` is approved by the company management (a person the business owner names) and carried out
  by an administrator; the approver is never the administrator who makes the change. The approver
  enters the approval in the request record personally, never the administrator who makes the
  change, and the administrator makes the assignment only once that approval is there. Every
  rotation of a break-glass or reviewer credential is entered in the same record when it is made
  (the account and the time, never the value). That
  off-server record is what restore step 9
  re-applies and what the reviewer compares the live role holders with. Resets that users make
  themselves through the reset e-mail, possible only once the company mailbox exists, are not in
  this record; before the reset e-mail is turned on in a shared environment, that gap returns to
  the human.
- **New-account handover.** The first temporary password of a new account follows the same rule as
  a reset: it is set only right before the user logs in, and handed over only in person or in a call
  the administrator makes to a phone number the company already holds for that person, never to an
  incoming caller, and never in writing. This rule is a rule of this decision; it stays within the
  hand-over ADR-0003's *Password reset* already allows and does not change ADR-0003.
- **Other duties.** The IT department patches the host, keeps its clock synchronised, applies
  image updates (PostgreSQL and Keycloak upgrades included) only through a release of the
  repository, watches certificate and backup alerts, and keeps the off-server copies of every secret
  and of the backup private key. A PostgreSQL major-version upgrade is also recorded as ADR-0002
  requires, and is followed by a repeat of the tested restore.

### Bootstrap of the first administrator

1. On the first start of `keycloak`, the IT department sets the Keycloak bootstrap admin credential
   in its environment file.
2. Before `proxy` is started, and so with neither listener running, the IT department works from
   inside the `keycloak` container (for example `kcadm.sh` against Keycloak's internal port,
   through `docker exec`). With that temporary account, it turns on the master realm's login
   events, admin events and brute-force detection, creates the named break-glass master-realm accounts and the
   reviewer's read-only master-realm account, then deletes the temporary bootstrap account and
   removes the bootstrap credential from the environment file. Only then is `proxy` started.
3. It imports the application realm from the export under `identity/`, injecting the client
   secret (and, once the mailbox exists, the SMTP credentials) from the environment.
4. It creates the first application-realm account holding `administrator` for the person the
   company's management names, and hands over its temporary password under the new-account rule
   (*Operator duties*).
5. The reviewer confirms the creation in the admin events.

### Recovery when no administrator remains

When no active account holds `administrator` (all disabled, or the holders unavailable):

1. The company's management names, in writing, the person who is to hold `administrator`.
2. A holder of a break-glass credential, from the company network on `<auth-admin-host>`, enables
   that person's existing account or creates a new one, assigns `administrator`, and sets a
   temporary password.
3. The holder hands over the temporary password under the new-account rule (*Operator duties*).
4. The holder announces the use of the credential to the reviewer, who reviews that day's events
   of both realms, and the credential is rotated.

### Changes to accepted decisions

This decision changes exactly one accepted decision, by one declared deviation approved at gate 1
on 2026-10-24 (G-10 A, Issue #16): ADR-0003's addendum of 2026-10-24 restates ADR-0003-C19's
connection budget so that the backup database role is part of the sum (*Composition and
placement*, *Connection limits*). That is the only change to an accepted decision. ADR-0001 and
ADR-0002 are not changed, and no other rule of ADR-0003 is changed.

### Items forwarded to this decision

Every item ADR-0001, ADR-0002 and ADR-0003 forward to ADR-0004, with its source and either the
section of this Decision that decides it or the task it is forwarded on to:

- **Container runtime** — ADR-0001 l.56-57, l.181 → decided in *Container runtime*.
- **Image composition** — ADR-0001 l.56-57, l.181 → decided in *Composition and placement*.
- **Database container composition** — ADR-0002 l.129 → decided in *Composition and placement*.
- **HTTPS exposure** — ADR-0001 l.56-57, l.181 → decided in *HTTPS exposure*.
- **Static file server** — ADR-0001 l.56-57 → decided in *Composition and placement*.
- **Secret handling** — ADR-0001 l.56-57, l.181 → decided in *Secret handling*.
- **Database credentials and secret handling** — ADR-0002 l.129 → decided in *Secret handling*.
- **Backup** — ADR-0001 l.181 → decided in *Backup*.
- **Restore** — ADR-0001 l.181 → decided in *Restore procedure*.
- **Daily off-server backup** — ADR-0002 l.129-130 → decided in *Backup*.
- **Restore procedure** — ADR-0002 l.130 → decided in *Restore procedure*.
- **Encryption at rest of volumes and backups** — ADR-0002 l.130 → decided in *Backup*.
- **When and by which single process `alembic upgrade head` runs (web and worker excluded)** —
  ADR-0001 l.181-182, ADR-0002 l.34-36, l.130-132 → decided in *Migrations*.
- **Expand → deploy → contract** — ADR-0001 l.182-183, ADR-0002 l.132-133 → decided in
  *Deployment and expand → deploy → contract*.
- **Operating and upgrading the database server** — ADR-0002 l.146 → decided in *Operator duties*.
- **Credentials kept out of the realm export** — ADR-0003 l.39-40 → decided in *Secret handling*.
- **Keycloak's database in the same backup** — ADR-0003 l.54-55, l.314, l.380 → decided in
  *Backup*.
- **Keycloak's database in the same restore** — ADR-0003 l.54-55, l.380 → decided in *Restore
  procedure*.
- **Connection-limit frame within the composition** — ADR-0003 l.57-63 → decided in *Composition
  and placement*.
- **Connection-limit values** — ADR-0003 l.63, l.313 → forwarded on to EKO-1-06 (#19).
- **Session-encryption key handling** — ADR-0003 l.76, l.313 → decided in *Secret handling*.
- **Cross-site callback depending on Keycloak's placement** — ADR-0003 l.86, l.347 → decided in
  *HTTPS exposure*.
- **One origin for the SPA and the API** — ADR-0003 l.99-100, l.309, l.339 → decided in *HTTPS
  exposure*.
- **Clock synchronisation of the backend and Keycloak** — ADR-0003 l.147, l.312-313, ADR-0003-C2
  (l.420) → decided in *Composition and placement*.
- **The operator reading admin events, and the ADR-0003-C22 review** — ADR-0003 l.204, l.314 →
  decided in *Operator duties*.
- **Bootstrap of the first administrator** — ADR-0003 l.242-243, l.314-315 → decided in *Bootstrap
  of the first administrator*.
- **Recovery when no administrator remains** — ADR-0003 l.242-243, l.315 → decided in *Recovery
  when no administrator remains*.
- **Placement, hostnames and HTTPS of Keycloak's public pages and of the administration console,
  and brute-force protection as a precondition** — ADR-0003 l.272-281, l.309-311 → decided in
  *HTTPS exposure*.
- **Reset-response timing** — ADR-0003 l.311-312 → decided in *HTTPS exposure*; the measurement is
  forwarded on to EKO-1-06 (#19).
- **Client secrets and SMTP credentials** — ADR-0003 l.313-314 → decided in *Secret handling*.

Forwarded on from this decision to named tasks:

- **The composition file, Dockerfiles and entry-point configuration; the backup role's limit; the
  image versions first used; the values of the lock and statement timeouts of `migrate`; how the
  revision check of `backend` and the same check in `migrate` establish that a newer revision
  descends from their code's head** → EKO-1-06 (#19).
- **What may appear in logs (container logs included); retention of admin events of both realms,
  of the master realm's login events, of sessions and of logs; how erasure treats backups, the
  verified sets kept beyond 30 days included** → EKO-1-04 (#17).
- **The background-work mechanism and any worker service; the Google secrets; the Google callback
  path on `<app-host>`** → EKO-1-05 (#18).
- **Production provisioning (the real server, the domain and hostnames, the IT department's host OS,
  disk-encryption unlock and monitoring) and the first tested restore; the production network
  topology (which host interface only the company network reaches, whether the client address
  reaches `proxy` unchanged through any NAT or upstream proxy, IPv6, and which address ranges are
  the company network)** → EKO-1-08 (#36).
- **Keeping single-page applications already open on reps' phones working when `frontend` is
  replaced (lazy chunks of the previous build no longer served; the previous build calling the new
  release's API)** → EKO-1-07 (#20) and EKO-1-06 (#19).

### Forward references (not decided here)

- EKO-1-06 (#19) — the composition file, Dockerfiles and entry-point configuration; the values of
  ADR-0003-C19, of the backup role's limit and of the lock and statement timeouts of `migrate`; how
  the revision check of `backend` and the same check in `migrate` establish descent from their
  head; the reset-timing measurement above; the image versions first used; with EKO-1-07
  (#20), keeping open single-page applications working across a `frontend` replacement.
- EKO-1-07 (#20) — the frontend build's lazy chunks and how an open single-page application
  behaves when `frontend` is replaced, together with EKO-1-06 (#19).
- EKO-1-04 (#17), ADR-0005 — what may appear in logs (including container logs), retention of admin
  events of both realms, of the master realm's login events, of sessions and of logs, and how
  erasure treats backups, the verified sets kept beyond 30 days included.
- EKO-1-05 (#18), ADR-0006 — the background-work mechanism and any worker service; the Google
  secrets and the Google callback path on `<app-host>`.
- EKO-1-08 (#36) — provisioning the real server, the domain and hostnames, the IT department's
  choice of host OS, disk-encryption unlock and monitoring, the production network topology, and
  the first tested restore.
- Not decided: a restore-time target (RTO) and a recovery point tighter than one day; the business
  has set neither. It closes when the business states one, as a new task.

## Options considered

### Container runtime

| Option | Cost | Closes off |
|---|---|---|
| **A. Docker Engine with Docker Compose v2** (chosen at gate 1; matches EKO-1-06's "one compose command") | The Docker daemon runs as root; whoever administers it is root on the host. | Nothing: the images and the Compose Specification stay portable. |
| B. Rootless Podman with podman compose or Quadlet systemd units | No root daemon; podman compose covers the Compose Specification less completely, and Quadlet units are a second description of the composition. | One composition file used unchanged in developer environments. |
| C. Single-node Kubernetes (k3s) | A cluster to operate for seven containers and about ten users; manifests instead of a compose file. | Nothing, but costs far more than it gives at this size. |

### HTTPS entry point and static file server

| Option | Cost | Closes off |
|---|---|---|
| **A. Caddy as the entry point (automatic ACME) and as the frontend image's static file server** (chosen) | One more product to pin and update; one product for both roles. | Nothing. |
| B. nginx with a separate ACME client (certbot) | A second container or a cron job for renewal; renewal failures are a known outage cause. | Nothing. |
| C. Traefik | Configuration through container labels ties routing to the runtime's API. | Routing independent of the runtime. |

### Certificates

| Option | Cost | Closes off |
|---|---|---|
| **A. ACME auto-renewal by the entry point for the public names; IT provides the internal admin hostname's certificate** (chosen at gate 1) | The ACME challenge path stays open on port 80. | Nothing. |
| B. The IT department buys and renews every certificate | A yearly manual renewal; the expiry alert is the only guard. | Nothing, but an expired certificate stops every phone. |

### Keycloak placement

| Option | Cost | Closes off |
|---|---|---|
| **A. Own hostname `<auth-host>` under the company domain; admin console on `<auth-admin-host>`, company network only** (chosen) | Two public names and one internal name with certificates. | Nothing. |
| B. Keycloak under a path of `<app-host>` | Keycloak's pages share the origin the session cookie belongs to; a flaw in a Keycloak page runs with the application's origin. | Isolating Keycloak's pages from the application's origin. |
| C. The whole server only over VPN | Reps on phones in the field need a VPN client; breaks brief §5. | Reaching the application from a phone without a VPN. |

### Migration placement

| Option | Cost | Closes off |
|---|---|---|
| **A. One-shot `migrate` service, advisory lock, startup revision check in `backend`** (chosen) | One more service definition; `backend` reads the revision at start. | Nothing. |
| B. Every backend container runs `alembic upgrade head` at start | Several containers from one image migrate concurrently (ADR-0002 forbids). | Adding a worker without a migration race. |
| C. The operator runs migrations by hand | A forgotten step leaves new code on an old schema. | Unattended restarts. |

### Deployment interruption

| Option | Cost | Closes off |
|---|---|---|
| **A. A short, announced interruption during a deployment** (chosen at gate 1) | Requests fail for seconds during the replacement. | Nothing for about ten users. |
| B. Zero downtime with two backend instances behind the entry point | A second instance, draining, and expand → contract binding every request path. | Nothing, but costs more than it gives at this size. |

### Backup method

| Option | Cost | Closes off |
|---|---|---|
| **A. Daily logical dumps (`pg_dump`) of both databases, encrypted with a public key, shipped to a write-only destination** (chosen) | Up to a day of data lost on a server loss; restore time grows with data size (small here). | Point-in-time recovery. |
| B. Physical base backup with continuous WAL archiving | Point-in-time recovery to minutes; more moving parts to operate and test, and a restore needs the same PostgreSQL major. | Restoring one database alone. |
| C. Snapshots of the host's volumes | Depends on the host's storage features (not cloud-agnostic); a snapshot taken while PostgreSQL writes is crash-consistent only. | Moving to a host with other storage. |

### Backup destination

| Option | Cost | Closes off |
|---|---|---|
| **A. Another host run by the IT department, in another room or building where there is one** (chosen at gate 1) | A second host to keep running; a site-wide disaster can take both where the company has one building. | Nothing. |
| B. An object storage bucket at an external provider (S3-compatible API) | An external contract and personal data leaving the company. | Keeping backups on company premises. |
| C. A removable medium rotated daily by IT | A missed rotation is a missing backup. | Unattended backups. |

### Reviewer of the administrator

| Option | Cost | Closes off |
|---|---|---|
| **A. The reviewer holds neither `administrator` nor a master-realm role that can change the application realm; reads through a read-only master-realm account; break-glass master-realm administration with at most two holders** (chosen at gate 1) | At least three people in the IT department. | Nothing. |
| B. The reviewer may hold `administrator` | A planted second administrator has no effective detection. | Detecting an administrator's own misuse. |

### Account changes after the backup point

| Option | Cost | Closes off |
|---|---|---|
| **A. Re-apply deactivations, role removals, password resets and rotations of break-glass and reviewer credentials from the IT department's off-server record, set the Keycloak-stored client secret and SMTP credentials from their master copies, sign out every restored Keycloak session and replace the session-token encryption key, all before the public listener opens to the internet** (chosen at gate 1 for deactivations and role removals; extended by the human on 2026-10-24) | Administrators report every deactivation, role removal, role assignment and password reset to IT; every user logs in again after a restore. | Nothing. |
| B. Re-apply only deactivations and role removals | A password reset after the backup point is undone, and a session ended after it is accepted again. | Relying on a reset or an ended session after a restore. |
| C. Accept that they are lost on restore | A disabled account can log in again after a restore. | Relying on deactivation after a restore. |

### Revision check and rollback

| Option | Cost | Closes off |
|---|---|---|
| **A. The revision check accepts the code's head or a revision descending from it; `migrate` makes the same check and changes nothing on such a revision, so a rollback to the previous release runs `migrate` like every start** (chosen by the human on 2026-10-24) | The check must establish descent for a revision its own code does not ship, in `backend` and in `migrate`; the one-release limit of a rollback stays procedural. | Nothing. |
| B. The revision check accepts only the code's head | After a successful expand migration the previous release cannot start, so a failed release is a full outage until a fix-forward or a restore. | Rolling back to the previous release. |

### Backup verification

| Option | Cost | Closes off |
|---|---|---|
| **A. The IT department decrypts the newest set off the server every calendar month, on a host meeting the restore-host requirements, and checks it against its manifest and against its off-server record of account changes; the last three verified sets are kept beyond 30 days** (chosen by the human on 2026-10-24) | A monthly task for IT; personal data in the verified sets may stay longer than 30 days. | Nothing. |
| B. Freshness alert only, restore tested before go-live and after major upgrades | An unusable or forged set goes unnoticed until the next restore, by which time retention may have removed every good set. | Relying on any backup between restore tests. |

## Controls

Identifier and acceptance criterion only.

| Control | Acceptance criterion |
|---|---|
| ADR-0004-C1 | `docker compose config --services` on the repository's composition (shared-environment profile) lists exactly `proxy`, `frontend`, `backend`, `migrate`, `keycloak`, `postgres` and `backup` (plus a worker only after an ADR-0006 addendum adds it), and no mail catcher. |
| ADR-0004-C2 | Every `image:` reference in the composition names a full version tag (for PostgreSQL `18.<minor>-<OS release>`) or carries `@sha256:`; none is `latest`, a bare major or `<major>-<OS release>`. |
| ADR-0004-C3 | In the rendered composition only `proxy` has `ports`; `postgres`, `keycloak`, `backend`, `frontend` and `backup` have none; the port mapping of `proxy`'s admin listener is bound to the host's company-network address only, not to `0.0.0.0`, `::` or an address the internet reaches. |
| ADR-0004-C4 | The rendered composition declares only the named volumes `pgdata` and `proxy-data` for persistent state, mounts no host path into `postgres`, `keycloak`, `backend` or `migrate`, and uses no vendor-specific extension or logging driver of a cloud provider. |
| ADR-0004-C5 | Against the running composition from an address outside the company network: `https://<app-host>/` and a route under `/api/` answer from `frontend` and `backend`; the application realm's authorization endpoint and login page on `<auth-host>` answer; `/admin/`, `/admin/realms/master/`, `/admin/realms/<application-realm>/users`, `/realms/master/`, `/realms/<application-realm>/account` and a path under `/realms/<application-realm>/` outside the public allowlist (for example `/realms/<application-realm>/clients-registrations/`) on `<auth-host>` are refused; connecting to the public address of `<auth-host>` over IPv4, and over IPv6 where the host has a public IPv6 address, with SNI and Host `<auth-admin-host>`, gets neither the administration console nor any `/admin/` response; `<auth-admin-host>` accepts no connection. From the company network, the administration console loads at `https://<auth-admin-host>` and `/realms/<application-realm>/account` is refused there. |
| ADR-0004-C6 | A plain-HTTP request to `<app-host>` or `<auth-host>` gets only a redirect (301 or 308) to the same URL over HTTPS, except the ACME challenge path; HTTPS responses from `<app-host>` carry `Strict-Transport-Security`. |
| ADR-0004-C7 | The certificates served for `<app-host>` and `<auth-host>` validate against a stock mobile browser trust store, and the IT department's monitoring raises an alert for a test certificate expiring within 14 days. |
| ADR-0004-C8 | Before a shared environment's public listener is opened, the live application realm reports `bruteForceProtected` true, and before its admin listener is started, the live master realm reports `bruteForceProtected` true (each recorded with the date of the check). |
| ADR-0004-C9 | No tracked file assigns a value to any secret variable of the inventory (the composition references each as a required variable with no default); `.gitignore` and every `.dockerignore` exclude `.env*`; listing the files of the built backend and frontend images finds no `.env` file. |
| ADR-0004-C10 | Starting `backend`, `migrate`, `keycloak` or `backup` with one of its required secrets unset fails before serving or connecting, with a non-zero exit naming the missing variable; `backend/app/core/settings.py` declares no default for a secret field. |
| ADR-0004-C11 | In the rendered composition, only the `migrate` service's command contains `alembic upgrade`; the commands and entrypoints of `backend` (and of any worker) do not; `backend` depends on `migrate` with condition `service_completed_successfully`. |
| ADR-0004-C12 | A test starts two `migrate` runs at the same time against an empty database: both exit 0, `alembic heads` and the database's `alembic_version` agree on one revision, and each revision's DDL was applied once. |
| ADR-0004-C13 | A test starts `backend` against a database at an older revision than its code's head: it exits non-zero without answering a request and without changing the schema. A test runs the previous release's `migrate` against a database at the next release's head after an expand migration: it exits 0 and leaves a schema dump identical to the one before it; the previous release's `backend` started after it answers requests and leaves the schema unchanged. A test runs `migrate` against a database at a revision its code cannot place: it exits non-zero and leaves the schema unchanged. A second `migrate` run at head exits 0 and leaves a schema dump identical to the one before it. |
| ADR-0004-C14 | A test applies a failing revision through `migrate`: it exits non-zero, the schema is unchanged, and the previously running `backend` still answers. |
| ADR-0004-C15 | At the destination, a backup set exists for each of the last 7 days and for the most recent deployment; each holds both databases' dumps, the roles and a manifest with the fields named under *Backup*; none can be decrypted with any key present on the server. |
| ADR-0004-C16 | With the `backup` service's credential, deleting or overwriting an existing backup set at the destination is refused. |
| ADR-0004-C17 | With no new backup set for 26 hours (simulated by stopping `backup`), the IT department receives an alert from a check that does not run on the server. |
| ADR-0004-C18 | Manual `<YYYY-MM-DD>`: the restore procedure, carried out on a host holding nothing from the original server, from a backup set at the destination and the off-server key and secrets, ends with a test login working from the company network while the public listener accepted no connection from the internet, and the row counts matching the manifest when compared before `migrate` runs; in the restored data every staff subject identifier of the application database exists in Keycloak's database. Recorded before go-live and after every PostgreSQL or Keycloak major upgrade. |
| ADR-0004-C19 | On the PostgreSQL server, the backup role has a connection limit of at least the number of sessions a backup holds at the same time (the advisory-lock session, the `pg_dump` session and the row-count session, wherever these are separate), a nightly backup run with that limit completes, and the connection limits of the application, Keycloak and backup roles together are below `max_connections` minus `superuser_reserved_connections`. |
| ADR-0004-C20 | `backend` and `keycloak` are services of one composition on one host, and the host reports its clock synchronised by NTP (recorded with the date of the check). |
| ADR-0004-C21 | The block device holding the composition's volumes on each shared-environment host is an encrypted device (recorded with the date of the check). |
| ADR-0004-C22 | By review of the IT department's operations record: the admin-event reading and the ADR-0003-C22 review were done at intervals of at most 7 days and after every break-glass use, each by a person holding neither `administrator` nor a master-realm role that can change the application realm, nor administrative rights over the container runtime, PostgreSQL superuser access, the PostgreSQL superuser password or a database role password; each review read the master realm's login and admin events and recorded a comparison of the live holders of `administrator`, `manager` and `rep` with the record of approved assignments, in which every assignment names an approver from the company management who is not the administrator who made it, and whose approval that approver entered in the request record. |
| ADR-0004-C23 | In the live master realm: login events and admin events are stored; the reviewer's account holds only `view-*` and `query-*` roles of the application realm's and the master realm's management clients and no `manage-*`, `realm-admin`, `impersonation` or `admin` role; at most two other accounts hold master-realm administration; no temporary bootstrap admin account exists; and the running `keycloak` container's environment holds no bootstrap admin variable. |
| ADR-0004-C24 | Against a running composition, the account used by the reviewer reads the application realm's admin events, the master realm's login and admin events, and an account's role mappings, and is refused when it tries to disable an account, assign a role, or change either realm's event settings. |
| ADR-0004-C25 | By review of the IT department's operations record after a restore, for the time before the public listener was opened to the internet, while it accepted connections only from the company network: the OIDC client secret and the SMTP credentials stored in Keycloak equal their off-server master copies; every rotation of a break-glass or reviewer credential recorded after the backup's time is in effect, so the previous value is refused; every deactivation and role removal recorded after the backup's time is in effect in the restored realm; every account with a password reset recorded after that time is disabled or has received a new temporary password; no user session of either realm restored from the backup set is still active; and the session-token encryption key in use differs from the one in use at the backup's time. |
| ADR-0004-C26 | A test holds a conflicting lock on a table an expand revision alters: `migrate` exits non-zero within its lock timeout, the schema is unchanged, and the previously running `backend` still answers requests that read that table. A test shows that while `backup` holds the advisory lock a `migrate` run applies no DDL until it is released, and that while `migrate` holds it `backup` starts no dump. |
| ADR-0004-C27 | By review of the IT department's operations record and of the destination: the newest backup set was decrypted off the server and checked against its manifest at intervals of at most one calendar month, each check on a host meeting the restore-host requirements and finding the newest entries of the record of account changes made before the set's time in the set's Keycloak dump; and the destination still holds the last three sets that passed the check, also when they are older than 30 days. |

## Addenda

<!-- A change to an accepted decision is a dated addendum with a reason, never an edit of the text
above. -->

- **2026-10-27:** ADR-0006 (EKO-1-05, #18) adds the `worker` service under *Composition and
  placement* (*Background work*). Image: the backend image. Role: background work of the Google
  Calendar integration, on a job queue in the application database. It never runs
  `alembic upgrade head`, depends on `migrate` with condition `service_completed_successfully`,
  refuses at start a revision that is not its code's head or a descendant of it, publishes no
  port, reads the whole `backend` environment file (it uses the application database role
  password, the Google OAuth client secret and the Google token encryption key, and also holds the
  file's session-token encryption key and OIDC client secret, which it does not use), and counts
  in the application role's connection
  budget. It is started and replaced with `backend` at every deployment and rollback, and at a
  restore it starts at step 13 with `backend`, after ADR-0005's re-apply. ADR-0004-C1 therefore
  lists eight services in shared environments. No other rule of this decision changes. Reason:
  this decision's *Background work* rule requires ADR-0006 to record an added worker service as an
  addendum here, and ADR-0006 chose a worker service from the backend image with a queue in
  PostgreSQL.

### 2026-10-28 — Forwards to EKO-1-06 reassigned after its split

**What it restates.** EKO-1-06 (#19) was split into EKO-1-06 and EKO-1-10..EKO-1-15 (#51..#56).
This addendum changes only which task receives a duty this decision names. No rule, consequence or
control changes. From this date:

- **Kept by EKO-1-06 (#19):**
  - the composition file, the Dockerfiles and the entry-point configuration;
  - the values of ADR-0003-C19 and the backup role's limit (*Composition and placement*,
    *Connection limits*);
  - the image versions first used.
  That the backup role's limit covers the sessions a backup holds, and that a nightly run under it
  completes (ADR-0004-C19), is shown by **EKO-1-14 (#55)**, which builds the backup.
- **To EKO-1-11 (#52):** the values of the lock and statement timeouts of `migrate`, and how the
  revision check of `backend` and the same check in `migrate` establish that a newer revision
  descends from their code's head (*Forwarded on from this decision*, *Forward references*).
- **To EKO-1-12 (#53):**
  - the reset-response timing measurement (*HTTPS exposure*, "The walking skeleton, EKO-1-06
    (#19), measures …"; *Items forwarded to this decision*; *Forward references*). Its
    consequence is unchanged: if the two response times are distinguishable, the reset e-mail is
    not turned on in any shared environment, and the finding returns to the human.
  - the correction of the bootstrap order found as exception EKO-1-03/R-22 (*Bootstrap of the
    first administrator*). Because it changes the order of that section's steps, EKO-1-12 records
    it as its own addendum to this decision.
- **To EKO-1-10 (#51):** the half of "keeping single-page applications already open on reps'
  phones working" that concerns the previous build calling the new release's API, as a check
  that compares the OpenAPI document with the previous release's (*Forwarded on from this
  decision*; *Forward references*, "with EKO-1-07 (#20)"). EKO-1-07 (#20) keeps the lazy-chunk
  half, together with EKO-1-10 (#51) where the *Forward references* say "together with EKO-1-06
  (#19)".
- **Newly named:** building the backend and frontend images from a release tag, pushing them to the
  registry, and referencing them by digest in a release's composition (*Composition and
  placement*, *Images*) is carried out by **EKO-1-15 (#56)**, before EKO-1-08's (#36) first
  deployment.

**Why.** These passages name EKO-1-06 as the task receiving duties it no longer carries after the
split. Left unchanged, the reset-timing consequence would bind a task that no longer measures, and
the tasks that do carry these duties would find nothing in this decision naming them. Approved by
the human at gate 1 of EKO-1-06 on 2026-10-28 (G-5 B, Issue #19). This is not a deviation: no rule
changes.

### 2026-10-28 — Initialising PostgreSQL: roles, limits, privileges and the two databases

**What it adds.** This decision lists the PostgreSQL roles, their connection limits and the two
databases, but it does not say what creates them on an empty data volume. It also forbids a host
path mounted into `postgres` (ADR-0004-C4), and its secret inventory does not deliver the three
role passwords to `postgres`. From this date:

- **The pinned image initialises itself.** `postgres` stays the pinned PostgreSQL 18 image itself:
  an `image:` reference under ADR-0004-C2 and ADR-0002-C12, with no `build:`. It creates the roles
  and databases from **init content** that the official image runs from
  `/docker-entrypoint-initdb.d/`. The image runs that content only when the data directory is
  empty, so it runs once per `pgdata` volume.
- **The init content is inline in the one composition file.** It is a top-level `configs` entry of
  the composition file, with inline `content` and no `file` source, attached to `postgres` with a
  target under `/docker-entrypoint-initdb.d/`. It is therefore neither a host path nor a second
  file. The content holds no secret value and no Compose interpolation (`${…}` would be replaced
  at render time and put the value into `docker compose config` output; a literal `$` is written
  `$$`). It reads the three role passwords from the container's environment while it runs, never
  from a command line. If the Compose release in use delivers inline config content as a bind
  mount of a host file, ADR-0004-C4 fails. In that case the mechanism returns to the human as an
  addendum, before any other mechanism is used.
- **What it creates.** All of this runs in one database session, which keeps statement text out of
  the server log for its own errors (ADR-0005), so a failing statement cannot log a password:
  - three login roles, the application role, Keycloak's role and the backup role. None is a
    superuser, and none may create roles or databases. Each has its password from the environment
    and its own `CONNECTION LIMIT` (ADR-0003-C19 and its 2026-10-24 addendum).
  - the application database, owned by the application role, with encoding `UTF8` and default
    collation from the ICU provider with locale `pl-PL` (ADR-0002, ADR-0002-C5).
  - Keycloak's database, owned by Keycloak's role, with encoding `UTF8`.
  - on both databases, `REVOKE CONNECT … FROM PUBLIC`. `CONNECT` is held only by the owning role and
    by the backup role (ADR-0003, *Identity server storage*; ADR-0003-C11). The backup role's read
    privileges are set by the task that builds the backup (EKO-1-14, #55).
  The limit values and `max_connections` are configuration that is the same in every environment.
  They are part of the release: the limits are written in the init content, and `max_connections`
  is set in the `postgres` command of the composition.
- **Missing or empty passwords.** An unset or empty role password stops the first initialisation
  with a non-zero exit naming the variable, as ADR-0004-C10 requires. A volume whose first
  initialisation failed is removed before the next start, never started again: the official image
  would treat its data directory as initialised and skip the init content.
- **Existing volumes.** Because the content runs only on an empty data directory, a release that
  changes a role, a limit or a privilege the content sets also carries that change for existing
  volumes, as an operator step announced with the release.
- **Secret inventory.** The rows *Application database role password*, *Keycloak database role
  password* and *Backup database role password* each read, in addition to what they say:
  - Used by: `postgres` (first initialisation).
  - Kept on the server: also the `postgres` environment file.
  - Delivered: also as an environment variable of `postgres`.
  - The composition declares each of them, in `postgres` as in the other services, as required
    with no default (ADR-0004-C9).
- **After first initialisation.** After the first initialisation PostgreSQL does not read these
  copies again. They stay in the `postgres` environment file, because the composition requires
  them. They are kept in step with the other copies at every rotation (*Secret handling*: every
  environment file that holds a secret). Because initialisation does not run again, a rotation
  also sets the new value in PostgreSQL (`ALTER ROLE … PASSWORD`), carried out by the operator.
  The extra copy has the same readers as the others: the IT department, through a file of mode
  `0600` owned by the account that runs `docker compose`. Anyone who can inspect the running
  `postgres` container can already read every container's environment (*Secret handling*).
- **Restore.** At restore step 4, `postgres` starts on an empty volume, so the init content creates
  the three roles with the passwords in effect (taken from the master copies at step 2), their
  limits and privileges, and the two empty databases. Step 4 then creates only those roles of the
  backup set that the init content does not create. Step 5 restores each dump into the database
  the init content created, which keeps the application database's ICU `pl-PL` collation.
- **Development and CI.** The development profile and CI use the same mechanism. Their untracked
  environment file holds synthetic values for the same variables.
- **New control ADR-0004-C28:**
  - In the rendered composition, `postgres` has an `image:` and no `build:`, and its init content
    is a top-level `configs` entry with inline `content`, no `file` source and no `${`.
  - On a running composition started from no volumes, `docker inspect` of `postgres` lists the
    named volume `pgdata` as its only mount.
  - The application, Keycloak and backup roles exist, each with `rolsuper`, `rolcreaterole` and
    `rolcreatedb` false and a connection limit greater than zero.
  - Neither database grants `CONNECT` to `PUBLIC`.
  - Started from no volumes with one role password empty, `postgres` exits non-zero and creates
    neither database.

Every other rule and control of this decision is unchanged. ADR-0004-C1 is unchanged: no service
is added.

**Why.** The walking skeleton (EKO-1-06, #19) has to create the ICU application database, the
three roles and their limits and privileges within this composition. Several routes would each
change a rule of this decision: a host-path init directory breaks ADR-0004-C4, a `postgres` built
from the pinned image breaks the image named in *Composition and placement*, and a further
one-shot service breaks ADR-0004-C1. Roles created without passwords would make development and
shared initialisation differ. Inline init content in the pinned image keeps the service list, the
image and C4, and it changes only the secret inventory. Approved by the human at gate 1 of
EKO-1-06 on 2026-10-28 (G-6 A, Issue #19). This is a declared deviation, because it changes the
secret inventory of *Secret handling*.

### 2026-10-28 — Image versions first used

**What it records.** *Forwarded on from this decision* and *Forward references* have the walking
skeleton (EKO-1-06, #19) choose the image versions first used; that duty stayed with EKO-1-06 after
its split (addendum of 2026-10-28). Each reference below names a full version, with the base OS
release for PostgreSQL as ADR-0002 requires (*Images*, ADR-0004-C2):

| Service or image | Reference | Where |
|---|---|---|
| `proxy` | `caddy:2.11.7` | `FROM` of `proxy/Dockerfile` |
| `frontend`, build stage | `node:22.23.4-alpine3.24` | `frontend/Dockerfile` |
| `frontend`, final stage (static file server) | `caddy:2.11.7`, the same release as `proxy` | `frontend/Dockerfile` |
| `backend`, `migrate`, `worker`, build stages | `ghcr.io/astral-sh/uv:0.13.6`, `python:3.12.16-slim-trixie` | `backend/Dockerfile` |
| `backend`, `migrate`, `worker`, final stage | `python:3.12.16-slim-trixie` | `backend/Dockerfile` |
| `keycloak` | `quay.io/keycloak/keycloak:26.8.1` (ADR-0003, addendum of 2026-10-28) | `image:` in `compose.yaml` |
| `postgres` | `postgres:18.6-trixie` (ADR-0002, addendum of 2026-10-28) | `image:` in `compose.yaml` |
| `backup` | `postgres:18.6-trixie`, the same image as `postgres` | `FROM` of `backup/Dockerfile` |
| mail catcher, development profile only | `axllent/mailpit:v1.32.0` | `image:` in `compose.yaml` |

`backend`, `migrate` and `worker` run one image, built once from `backend/Dockerfile`. The
composition tags it locally as `localhost/eko-crm/backend:<tag>` and never pulls it; a release
references it by digest (EKO-1-15, #56). The mail catcher is never part of a shared environment
(*Composition and placement*).

No rule or control of this decision changes. A later change to any of these references is made
through a release of the repository (*Operator duties*); PostgreSQL and Keycloak changes are also
recorded as ADR-0002 and ADR-0003 require.

**Why.** The image versions first used are forwarded to EKO-1-06 by this decision. Approved by the
human at gate 2 of EKO-1-06 on 2026-10-28 (Issue #19, PR #57). This is not a deviation.

### 2026-10-28 — *Images*: release by digest also for `proxy`'s base, `postgres` and `keycloak`

**What it changes.** *Images* has CI build the backend and frontend images from a release tag, and
has a release's composition reference them by digest, "so the image deployed is the image CI
tested". Every other image reference needs only a full version tag, and the publisher can re-point
a tag. From this date, the release-by-digest rule also covers the third-party images that run in a
shared environment:

- the PostgreSQL image of the `postgres` service;
- the Keycloak image of the `keycloak` service;
- the Caddy base image of `proxy` (the `FROM` of `proxy/Dockerfile`).

In a release for a shared environment, each of these references carries `@sha256:` followed by 64
lower-case hexadecimal digits. The tag may stay beside the digest (`<tag>@sha256:<digest>`), so
ADR-0002-C12 (as restated on 2026-10-28), ADR-0003-C3 and ADR-0004-C2 still hold. The `frontend`
and `backup` images also build on third-party bases (Caddy, and node at build time; PostgreSQL),
but CI builds both and a release references them by digest under *Images* (EKO-1-15, #56), so the
bases they ran with are fixed in the image CI built.

- **Who carries it.** EKO-1-15 (#56), which builds the release pipeline, carries this widening,
  before EKO-1-08's (#36) first deployment, as it carries the rest of *Images*.
- **Until then.** The tag pins of `caddy` (the `proxy` base), `postgres` and `keycloak` are the
  recorded exception EKO-1-06/B-01, which blocks again on 2027-03-31.

Every other rule and control of this decision is unchanged.

**Why.** The security auditor's finding B-01 on EKO-1-06: a publisher or registry account that
re-points the tag of one of these images runs code CI never tested, at the next pull, build or
restore, in `proxy` (the TLS private keys), `keycloak` (the credential store) or `postgres` (all
data and the role passwords). "The image deployed is the image CI tested" covered only the images
the project builds. Widening a rule of this decision is a declared deviation, approved by the human
at gate 2 of EKO-1-06 on 2026-10-28 (Issue #19, PR #57).

### 2026-10-28 — The composition requires a project name

**What it adds.** *Cloud-agnostic constraints*, item 3, keeps persistent state only in the named
volumes `pgdata` and `proxy-data`. Docker Compose prefixes a volume's name with the project name,
and without one it takes the project name from the directory the composition is started in. From
this date, the composition requires `COMPOSE_PROJECT_NAME`, with no default
(`name: ${COMPOSE_PROJECT_NAME:?…}` in `compose.yaml`), so a start without it is refused. A shared
environment's `<project>_pgdata` and `<project>_proxy-data` therefore do not depend on the
directory a release is unpacked in. The value is configuration that differs between environments
and reaches the composition through the environment file (*Cloud-agnostic constraints*, item 2).
The operator's rule for keeping one project name in a shared environment is forwarded to EKO-1-08
(#36).

Every other rule and control of this decision is unchanged.

**Why.** With a project name taken from the directory, a release unpacked in a new directory would
start on new, empty volumes and leave the environment's data in the old ones. Approved by the human
at gate 2 of EKO-1-06 on 2026-10-28 (Issue #19, PR #57). This is not a deviation: it records how
the composition meets item 3.

### 2026-10-29 — The previous release's OpenAPI document: its source forwarded to EKO-1-15

**Status:** Accepted 2026-10-29 (gate 1 of EKO-1-10, Issue #51).

**What it restates.** This decision's addendum of 2026-10-28 on the split of EKO-1-06 gives
EKO-1-10 (#51) "a check that compares the OpenAPI document with the previous release's". No
release exists yet. Building images from a release tag and referencing them by digest is
EKO-1-15's (#56), and nothing yet fixes what a release tag is. This addendum changes only which
task carries each part of that duty. From this date:

- **EKO-1-10 (#51)** builds the comparison and runs it on every pull request. Given the previous
  release's OpenAPI document and the document the pull request's backend generates, it fails on a
  change that breaks a client built against the previous document. While no previous release
  exists, its output says that it compared nothing, and it does not report a comparison.
- **EKO-1-15 (#56)** gives the check its input: which release counts as the previous one, and how
  CI obtains that release's document. Both documents are taken from the backend directly, never
  through `proxy`, as ADR-0003's addendum of 2026-10-28 requires.
- The check stops being vacuous at the second release.
- EKO-1-07 (#20) keeps the lazy-chunk half, unchanged.

No rule or control of this decision changes.

**Why.** If EKO-1-10 defined "the previous release", it would fix the release tag's form before
the task that builds releases. If the previous document were committed to the repository, a pull
request could change it together with the break it hides. Approved by the human at gate 1 of
EKO-1-10 on 2026-10-29 (G-12 A, Issue #51). This is not a deviation: no rule
changes.

### 2026-10-29 — `migrate`'s advisory lock and timeouts, and how the revision check establishes descent

**Status:** Accepted 2026-10-29 (gate 1 of EKO-1-11, Issue #52; accepted by the human in the driving session, recorded on the Issue).

**What it settles.** *Migrations* has `migrate` hold an advisory lock for the whole run, run its
statements with a lock timeout and a statement timeout once it holds that lock, and has `backend`,
any worker and `migrate` accept a database revision that descends from their code's head. It
forwards the timeout values and how descent is established for a revision the running code does
not ship (*Forwarded on from this decision*, *Forward references*), and the addendum of 2026-10-28
on the split of EKO-1-06 gives both to EKO-1-11 (#52). From this date:

- **The advisory lock's identity.**
  - It is one PostgreSQL advisory lock on the application database, taken with the
    single-`bigint`-key form of the advisory-lock functions. The two-`integer`-key form is a
    different lock and never counts as "the same advisory lock".
  - Its key is a fixed, non-zero integer written **once** in the repository: as a literal in a
    top-level extension field of `compose.yaml` (`x-migration-advisory-lock`), delivered to
    `migrate` as the environment variable `MIGRATION_ADVISORY_LOCK_KEY` and read only through
    `backend/app/core/settings.py` (ADR-0001-C10). The `backup` service (EKO-1-14, #55) receives
    the same field by reference, never as a second literal. Its build context, `backup/`, cannot
    read a file of the backend image, which is why the composition and not a backend module is the
    one place.
  - This decision does not repeat the value, so that the value stays in one tracked file outside
    `backend/tests/`. Changing it is a change to this addendum, because `migrate` and `backup` must
    change it together.
  - The key is the same in every environment and part of the release, as the connection limits are
    (addendum of 2026-10-28 on initialising PostgreSQL). It is not a secret.
- **One connection, in this order.** A `migrate` run opens exactly one database connection and does
  everything on it, inside the one transaction of the run (`backend/migrations/env.py`,
  ADR-0003-C19 counts one connection for `migrate`):
  1. it takes the advisory lock as a transaction-level lock, as the first statement of the run's
     transaction, and waits for it with no time limit (*Migrations*: "waits for the lock");
  2. once the lock is granted, it sets the lock timeout and the statement timeout for the rest of
     that transaction only;
  3. it reads the database's revision and makes the descent check below;
  4. it applies the pending revisions, or none;
  5. when it applied at least one revision, it writes the revision lineage record (below);
  6. it commits, which releases the lock, or it fails and PostgreSQL rolls everything back,
     which also releases the lock.

  The revision is never read before the lock is granted. No second connection is opened, for the
  lock, for the revision read or for the lineage record. The whole run stays one transaction
  (Alembic's `transaction_per_migration` stays off), as ADR-0004-C14 requires. A transaction-level
  lock conflicts with a session-level lock on the same key, so `backup` may hold it either way.
- **Timeout values.**

  | Setting | Value | Why this value |
  |---|---|---|
  | lock timeout | **5 seconds** | While `migrate` waits for a table lock, its queued exclusive request also holds back every later read of that table, so reps' requests touching that table wait as long as `migrate` waits. Five seconds is a pause a rep notices but does not take for a failure. It stays well below the 30-second pool checkout wait after which a request fails (ADR-0002, addendum of 2026-10-28). In a system of about ten users a DDL lock is normally granted at once. It waits only behind a long transaction, and a failed run leaves the previous release serving (*Migrations*), so the operator retries the deployment later at no cost to data. |
  | statement timeout | **30 seconds** | It bounds one runaway statement. A statement that holds an exclusive table lock stalls reps' requests on that table for as long as it runs. With a few thousand customers (brief, section 5), an index build or a backfill takes well under a second, so 30 seconds leaves a wide margin. At 30 seconds a rep's request waiting behind the statement fails on pool checkout at about the same time anyway. |

  - **Where they are set.** Both values are literals in the `environment` of the `migrate` service
    in `compose.yaml`, with no Compose interpolation, so no environment file changes them. They are
    read only through `backend/app/core/settings.py`, which refuses a missing, zero or negative
    value (PostgreSQL reads `0` as "no timeout"). `env.py` applies them on the run's one connection
    as transaction-local settings, after the advisory lock is granted (step 2 above).
  - They are **not** set in the connection's start-up options, on the application role, on the
    database or in the server configuration. Each of those would also bound the advisory-lock
    wait, which must stay unbounded, or would bind `backend` and `worker` sessions, which this
    decision does not ask for.
  - **No revision changes them.** No revision sets `lock_timeout`, `statement_timeout` or
    `transaction_timeout`. A revision that needs more time is split into several revisions, or
    this addendum is changed first.
- **The revision lineage record.** Chosen at gate 1 of EKO-1-11 (Q-1 A; options B and C are
  in the impact map of EKO-1-11). A revision the running code does not ship cannot be placed from that code's own tree. It is
  placed from a record in the application database that the newer `migrate` wrote:
  - The record is one table, `schema_revision_lineage`, with one column `revision` (text, the
    primary key, compared byte-wise). It holds exactly the revisions from the base to the
    database's current head, that head included. It holds no personal data and no time value
    (ADR-0002, *Now, today*: no column default read from the database clock).
  - **It is created by a revision of the real tree, `0002`**, a pure expand revision on top of the
    baseline `0001`. That keeps *Versioned migrations* of ADR-0002 as written: the table is a
    schema change made by an Alembic revision, and `migrate` writes only its rows, never its
    schema. ADR-0002-C2 keeps one head. ADR-0002-C3 keeps holding, either through a model
    declaration in the `data` layer or by excluding the table from Alembic's comparison, as the
    developer chooses.
  - **Only `migrate` writes it**, in the run's own transaction (step 5 above), right after the
    last revision it applied, so it commits together with `alembic_version` or not at all. It
    replaces the rows with the lineage of its own tree's head. A run that applies nothing writes
    nothing, so a no-op run leaves both the schema and the record unchanged (ADR-0004-C13).
  - It is part of the application database's dump, so a restore brings it back with the data, and
    restore step 12 (*Restore procedure*) places a restored revision the same way.
- **The descent check.** `backend`, `worker` and `migrate` run one function of the `data` layer
  (`backend/app/data/`, ADR-0002-C4). It takes the code's head `H` and its tree from the image's
  `migrations/` directory, and reads `alembic_version` and the lineage record:

  | Database state | `backend`, `worker` | `migrate` |
  |---|---|---|
  | no `alembic_version` table | refuse | the empty application database: upgrade from the base (*The first deployment*) |
  | `alembic_version` with no row, or with more than one row | refuse | fail, change nothing |
  | one row `r`, `r` = `H` | serve or work | exit 0, change nothing |
  | one row `r` in its own tree, `r` ≠ `H` (an ancestor, the history being linear) | refuse | upgrade to `H` |
  | one row `r` not in its own tree, with both `r` and `H` in the lineage record | serve or work (a descendant) | exit 0, change nothing |
  | one row `r` not in its own tree, and the lineage record missing or lacking `r` or `H` | refuse | fail, change nothing |

  - A revision recorded beside `H` in the lineage and absent from the code's tree cannot be an
    ancestor of `H`, because every ancestor of `H` is in that tree, so it descends from `H`. A
    sibling of `H` (same parent, other revision) has a lineage without `H` and is refused. So is
    an identifier no `migrate` wrote.
  - "Refuse" means: exit non-zero before serving a request or taking a job, change nothing, and
    log one line naming the process and the reason (older, unplaceable, missing). The line may
    name revision identifiers. It never names the database URL, a host, a role or a password
    (ADR-0005; the log format is EKO-1-13's).
  - `backend` and `worker` neither take the advisory lock nor wait for it. A `migrate` run is one
    transaction, so they read the revision as it was before it or as it is after it.
- **Where each process runs the check.**
  - **`migrate`:** in `backend/migrations/env.py`, at step 3 above, before Alembic resolves any
    revision. Alembic itself fails on a revision missing from its tree, which would turn a
    descendant into a failed run.
  - **`backend`:** in `backend/app/serve.py`, after the settings are loaded (ADR-0004-C10 keeps
    its order: a missing secret is named before any connection) and before `uvicorn.run`. It runs
    in the one process that is the container's main process. A check in the application factory or
    its lifespan would run in each uvicorn worker, whose supervisor restarts a worker that dies, so
    the container would never exit (the same trap `serve.py` records for the secrets check). The
    check uses its own single connection and closes it before `uvicorn.run`. It therefore never
    adds to the 2 × (5 + 5) connections of ADR-0003-C19's budget.
  - **`worker`:** in `backend/app/worker.py`, in its main process, after the settings are loaded
    and before any job is taken, within its pool of 2.
  - Only `migrate`'s command contains `alembic upgrade` (ADR-0004-C11). The check never migrates.
- **Test-only revisions and the previous-release stand-in.** These never reach the image a release
  ships:
  - Test-only revisions live under `backend/tests/`, which `backend/.dockerignore` keeps out of the
    build context, and never under `backend/migrations/versions/`.
  - A test variant is an image built `FROM` the image the repository's normal build produced. It
    only adds revision files to `/app/migrations/versions/`, so a variant runs the shipped
    `env.py`, `app/` and entry points.
  - The previous-release stand-in is the shipped image itself. The "next release" is a variant
    that adds one expand test-only revision on top of the shipped head.
  - No runtime configuration adds a revision location: `alembic.ini`'s `script_location` stays
    fixed, and no environment variable sets `version_locations`.
  - A fixture that changes `env.py` or an entry point, such as the lock removed, is a planted
    contrast. A claim is never proven on it.
- **What this does not bound (a stated cost).** Chosen at gate 1 of EKO-1-11 (Q-3 A).
  - The wait for the advisory lock has no limit. Any session connected to the application database
    that holds the same advisory lock stalls `migrate` for as long as it holds it: a stuck backup,
    but equally an operator's `psql` session, or a hung or compromised process running as
    `eko_app` or `eko_backup`. Taking an advisory lock needs no privilege, and the key is a
    non-secret literal in `compose.yaml`. A run waiting behind any of them does not finish, and
    the deployment does not go ahead. The previous release keeps serving, because no table lock
    is held while waiting. This is accepted as a cost; this addendum adds no mitigation for it.
  - The lock timeout bounds a rep's stall only while `migrate` *waits* for a table lock. Once
    `migrate` holds an exclusive lock, the run's single transaction keeps it until commit. Reps'
    requests on that table then wait for the rest of the run, which is bounded per statement by
    the statement timeout but not as a whole. At this data size a run takes seconds. Adding a
    bound on the whole run (`transaction_timeout`) would be a change to this addendum.
  - The values are proven to be in effect, not to be the right size for a future large backfill.

Every other rule and control of this decision is unchanged. ADR-0004-C11..C14 and C26 are carried
out on this mechanism. The backup half of ADR-0004-C26 stays with EKO-1-14 (#55), which takes the
lock under the identity recorded here.

**Consequence for EKO-1-11's Story.** The real tree becomes `0001` → `0002`. Definition of done
item 9 ("keeps the single baseline `0001`") and criterion K-07 ("exactly `{0001}`") read
"exactly `{0001, 0002}`, one head".

**Why.** *Revision check and rollback*, option A, accepts a revision that descends from the code's
head, and names the cost: "the check must establish descent for a revision its own code does not
ship". The running code holds only its own tree, so that fact can come only from the database, and
only the `migrate` that applied the newer revision knows it. A record written by `migrate` in the
same transaction as `alembic_version` is the smallest store that cannot disagree with it. Creating
it by a revision keeps ADR-0002 unchanged. The timeout values bound the stall reps feel within the
"short, announced interruption" this decision accepts. Taking the lock and the timeouts on the run's
one connection, in that order, keeps ADR-0003-C19's budget (23 of 30) and leaves the advisory wait
unbounded, as *Migrations* says. This is not a deviation from ADR-0004 or ADR-0002: it decides what
this decision forwarded. Approved by the human at gate 1 of EKO-1-11 on 2026-10-29 (G-1 A,
Issue #52).

### 2026-10-30 — The backup run: lock and snapshot, the set, its encryption and destination, the schedule and the failure line

**Status:** Accepted 2026-10-30 (gate 1 of EKO-1-14, Issue #55; accepted by the human in the driving session with every recommended option, recorded on the Issue).

**What it settles.** *Backup* decides what a set holds and in which order, that it is encrypted
with a public key before it leaves `backup`, that `backup`'s credential can add sets but cannot
delete or overwrite them, the daily time and the on-demand run, and that a failed run is reported.
*Migrations* has `backup` take the advisory lock "for the whole of its dumps". The addendum of
2026-10-28 on initialising PostgreSQL leaves the backup role's read privileges to the task that
builds the backup. None of these says how the destination is written to, in what format a set is
encrypted and in what form the IT department holds the key, what the manifest's "time" is, how the
schedule is kept, what the report of a failed run looks like, or how a test holds a run at a given
point. EKO-1-14 (#55) builds `backup` against a destination double. From this date:

- **One run: its sessions, the lock and the snapshot.**
  - A run holds at most **two** database sessions at the same time: its control session on the
    application database, open for the whole run, and the session of the one dump tool running at
    that moment. The dumps run one after another, never in parallel jobs. The run therefore fits
    `eko_backup`'s `CONNECTION LIMIT 5` (ADR-0003, addendum of 2026-10-28, value table). A design
    that needs more than five sessions stops the work, and the change returns here.
  - Each session sets a fixed application name naming its part: `eko-backup-control`,
    `eko-backup-dump-application`, `eko-backup-dump-keycloak` and `eko-backup-dump-roles`.
  - On the control session, in this order:
    1. it takes the advisory lock under the identity of the addendum of 2026-10-29 (one lock,
       single-`bigint` form), and waits for it with no time limit, as `migrate` does. The key
       reaches `backup` as `MIGRATION_ADVISORY_LOCK_KEY`, the name `migrate` uses, by YAML
       reference to `x-migration-advisory-lock`, never as a second literal;
    2. only once the lock is granted, it begins a `REPEATABLE READ`, read-only transaction. The
       first statement of that transaction establishes and exports its snapshot and returns the
       backup point (below);
    3. in that transaction it reads the Alembic revision and counts the rows of every application
       table;
    4. the application database is dumped on the exported snapshot, so the dump, the revision and
       the counts are those of one snapshot (*Scope*: "counted inside the dump's own snapshot");
    5. after the application dump has ended, Keycloak's database is dumped, and then the cluster's
       roles without their passwords;
    6. it releases the lock only after the Keycloak dump has ended. On a failure, ending the control
       session releases it.
  - The lock is never first taken inside the transaction whose snapshot the dump uses. In
    `REPEATABLE READ` that snapshot is fixed at the transaction's first statement, so a lock waited
    for there would leave a snapshot older than the grant. A session-level lock taken before that
    transaction begins meets this rule. The addendum of 2026-10-29 ("`backup` may hold it either
    way") is unchanged: this rule adds only the order.
  - An **application table** is every ordinary or partitioned table of the application database
    outside `pg_catalog` and `information_schema`. The counts list each by its schema-qualified
    name, and a table with no rows has the count 0.
  - **Two runs at once.** <!-- GATE-1: Q-3 (G-7) — options and recommendation in EKO-1-14's
    impact map --> A second run, scheduled or on demand, waits for the lock like any other holder,
    then takes its own snapshot and leaves its own set. A waiting run holds one session, so while
    one run is active (two sessions) at most three more can wait within the limit of 5. A further
    run is refused a session by the server (SQLSTATE 53300) and fails with the failure line. The
    unbounded wait is the cost recorded in the addendum of 2026-10-29 (*What this does not
    bound*); it now also covers a backup waiting behind a stuck backup.
- **The backup point and the manifest.**
  - The manifest's time is the **backup point** of ADR-0005 (*Erasure and backups*, *The backup
    point*): the start of the application dump's snapshot. It is read from the PostgreSQL server's
    clock, in the control session, as `statement_timestamp()` of the statement that establishes
    and exports the snapshot. That value is no earlier than the lock's grant and no later than the
    snapshot. It is never the `backup` container's clock, never the run's start, and never a clock
    read after the snapshot was taken. A time slightly earlier than the true snapshot can only make
    a set count as older, which is the side ADR-0005 treats as safe ("counts as started before
    it").
  - It is written in UTC with an explicit zone, as RFC 3339 with the suffix `Z` and microseconds
    (for example `2026-10-30T01:00:00.123456Z`), never in local time and never without a zone.
  - ADR-0002 *Now, today* binds `backend/app/` and `backend/migrations/`; `backup` is neither.
    The server clock read here is the clock ADR-0005 *The commit time* refers to ("on the clock
    behind the snapshot start"), so the task that builds erasure reads its commit time from the
    same PostgreSQL server.
  - The manifest is one UTF-8 JSON document with: `format` (`eko-backup-manifest/1`), `set` (the
    set's name), `backup_point`, `alembic_revision`, `images` (`backend`, `keycloak`, `postgres`)
    and `row_counts`.
  - The three image references reach `backup` as non-secret environment values,
    `BACKUP_MANIFEST_BACKEND_IMAGE`, `BACKUP_MANIFEST_KEYCLOAK_IMAGE` and
    `BACKUP_MANIFEST_POSTGRES_IMAGE`, each a YAML reference to the `image:` value of its service in
    `compose.yaml`, so they cannot differ from what the composition runs. `backup` never queries
    the container runtime and is never given access to its socket. When a release names images by
    digest (EKO-1-15, #56), the manifest names the digests with no change to `backup`.
- **The set: its objects, its name and when it is complete.**
  - A set is four encrypted objects and one completion record, all in the destination's incoming
    directory (the account cannot create directories, below):
    - `<set>.application.dump.age`: the application database, `pg_dump` custom archive format;
    - `<set>.keycloak.dump.age`: Keycloak's database, `pg_dump` custom archive format;
    - `<set>.roles.sql.age`: the cluster's roles, as `pg_dumpall --roles-only
      --no-role-passwords` writes them;
    - `<set>.manifest.json.age`: the manifest;
    - `<set>.complete`: the completion record, written last.
  - **Naming rule.** `<set>` is `eko-` followed by the backup point as `YYYYMMDDTHHMMSS.ffffffZ`,
    a hyphen, and 16 lower-case hexadecimal digits read from the kernel's random source. A name
    holds only those characters and no host, environment, project or account name. Two runs never
    share a name, also within one microsecond or after the clock is set back. A run writes only
    names it generated itself, each once, and no name that a reader would follow to "the latest"
    set.
  - **The completion record** <!-- GATE-1: Q-5 — plaintext completion record; options in
    EKO-1-14's impact map --> is plaintext UTF-8, one line per encrypted object: its name, its size
    in bytes, and the SHA-256 digest of its bytes as uploaded (the ciphertext). It holds nothing of
    the set's contents: no manifest field other than the set's name, no count, no personal data.
    It lets a check that has no private key, such as the 26-hour check of ADR-0004-C17, tell a
    complete set from a partial one.
  - **Completeness rule.** A set is complete when its completion record exists, lists exactly the
    four objects above, and each listed object exists at the destination with exactly the recorded
    size and SHA-256 digest. Anything else under a set name is an incomplete set: objects without a
    record, a record that does not parse, an object of another size or digest. An incomplete set is
    not a backup set: not for ADR-0004-C15, not for the 26-hour check, not for the monthly
    verification and not for a restore. The destination is append-only, so a failed or interrupted
    run leaves its partial objects there. This rule, not a deletion, keeps them from counting. The
    destination's own housekeeping removes them with the others (*Retention*).
  - A run reports success only once the destination has confirmed the set: after each upload it
    reads the object's size at the destination and compares it with the bytes it sent, and it does
    the same for the completion record. Only then does it exit 0.
- **Encryption.** <!-- GATE-1: Q-2 — encryption format and key form; options in EKO-1-14's impact
  map -->
  - **Format.** Each object is a separate file in the **age** format, version 1
    (`age-encryption.org/v1`), binary (not armoured), with exactly one X25519 recipient: the
    configured public key. No passphrase recipient and no second recipient. It is encrypted as a
    stream from the dump tool's output. The format authenticates every chunk, so a truncated or
    altered object fails to decrypt.
  - **Key form the IT department holds.** The private key is an age identity, one line beginning
    `AGE-SECRET-KEY-1`. The IT department keeps its two off-server copies (*Secret handling*) as
    that line, and may keep each copy passphrase-protected; that choice is the IT department's,
    recorded at EKO-1-08 (#36). The public key is the matching recipient, one line beginning
    `age1`, delivered in `BACKUP_ENCRYPTION_PUBLIC_KEY`. Because a set does not name its key, the
    IT department records the date of every key rotation, and a set is decrypted with the key in
    effect at its backup point ("older backups keep their key").
  - **Executable outside the composition.** The reference `age` command-line tool, or any
    implementation of the format, generates the key pair and decrypts a set on any host. A test
    generates the pair outside the composition and gives the composition only the recipient.
  - In `backup`, the tool comes from the Debian `trixie` package of the pinned base image, at an
    exact package version written in `backup/Dockerfile`. If the package does not exist for that
    base, the work stops and returns here before any other source of the tool is used.
  - No file of the `backup` image, of its running container, or of any environment file of the
    composition holds an age identity.
- **The destination: write protocol and how write-only is enforced.** <!-- GATE-1: Q-1 —
  destination write protocol; options in EKO-1-14's impact map -->
  - **Protocol.** SFTP (the SSH File Transfer Protocol, as OpenSSH's `internal-sftp` serves it) on
    the IT department's destination host, with one account per environment for `backup`,
    authenticated by public key only.
  - **Write-only is enforced by the destination, not by `backup`:**
    - the account's sessions are forced to `internal-sftp`, with no shell, no command execution
      and no forwarding, and are confined (`ChrootDirectory`) to a directory owned by root that
      holds one incoming directory;
    - `internal-sftp` runs with an **allow list** of requests: open, write, close, the three stat
      requests and realpath. Every other request is refused: remove, rename and its extensions,
      mkdir, rmdir, the setstat requests, symlink, hardlink, read, opendir, readdir and every
      other extension;
    - its umask is `0377`, so every file the account creates is read-only to its owner from the
      moment it is created. The descriptor of the create that made it stays writable until it is
      closed. Any later open of an existing name for writing or truncation is refused by the file
      system;
    - the account can neither read nor list what it wrote.
  - **What counts as what.** An *add* is the creation of a name that did not exist, its writes and
    its close. An *overwrite* is any open for writing or truncation of an existing name, a rename
    onto it, or a change of its attributes. A *delete* is a remove, or a rename away from the name.
    A *rewritten pointer* is an overwrite of, or a create of, a name a reader would follow to "the
    latest" set; the naming rule has no such name.
  - **The destination's record of attempts.** The destination keeps a record of every request each
    account makes, refused requests included, with the account and key that made it: the
    `internal-sftp` log at level `VERBOSE` and the SSH server's authentication record, kept by the
    IT department off the server. EKO-1-08 (#36) shows that this record lists refused requests.
  - **The destination's identity.** `backup` checks the destination's host key against
    `BACKUP_DESTINATION_HOST_KEY` and refuses any other key; it never accepts a key on first use.
  - **The credential.** An Ed25519 key in OpenSSH format, delivered in
    `BACKUP_DESTINATION_CREDENTIAL` as the base64 encoding of the key file on one line. Inside
    `backup` it reaches the client only through process memory, a pipe or an agent. It is never
    written to a file of the image, of the container or of a volume.
  - **Transport.** Each object is streamed from the encryption step to the destination. The client
    comes from a Debian `trixie` package of the pinned base, at an exact version. If no such client
    can stream an upload from a pipe under these rules, the work stops and returns here.
  - Retention and housekeeping stay the destination's own (*Retention*). The same host may serve
    ADR-0005 *Keycloak events off the server* with an account of its own under the same rules; that
    is EKO-1-09's (#41) decision.
- **The destination double, in the test harness only.**
  - It lives only in the test harness, never in `compose.yaml`, so ADR-0004-C1 is unchanged. A test
    attaches it to the composition's network while it runs.
  - It is built from a pinned image with an OpenSSH server. The exact destination fragment above
    (`ChrootDirectory`, `ForceCommand internal-sftp`, the allow list, the umask) is kept with the
    harness, as the fragment handed to the IT department at EKO-1-08 (#36). The double itself does
    not run that fragment as written, because a double configured that way cannot keep the access
    record below: the stock `sftp-server` logs a refused request without its name, nothing logs
    whether a name existed, and a chrooted `internal-sftp` has no `/dev/log`.
  - Instead, the double's SSH server forces a small recorder, present in the double's image only.
    For each client request the recorder writes one JSON line (the credential, the request type,
    the name, the open flags and whether the name existed at that moment) and passes the bytes on
    to `/usr/lib/openssh/sftp-server` with the destination's flags:
    `-l VERBOSE -u 0377 -p open,write,close,stat,lstat,fstat,realpath`. The double container's own
    `/` stands in for the chroot root, so `backup` sees the same `/incoming/...` paths.
  - What that difference costs: the double runs the same `sftp-server` code with the same flags,
    but not `internal-sftp` inside the SSH server and not the chroot. It therefore does not prove
    the IT fragment itself; that is EKO-1-08's (#36).
  - It has a second, administrative credential that may delete and overwrite. That credential is
    the contrast that shows a refusal is bound to `backup`'s credential.
  - Its access record is the recorder's lines: every request it receives, refused or not. It can
    also run with refusal switched off (no allow list, an ordinary umask), so a test can show that
    the record sees a non-add.
  - What it refuses proves nothing about the real destination (EKO-1-08, #36).
  - Amended at gate 1 of EKO-1-14, 2026-10-30 (developer stop 2 A).
- **Nothing of a set at rest on the server.** `backup` writes no file holding any part of a set
  (a plaintext dump, an encrypted object, the manifest or the completion record) in its image, its
  container (a tmpfs included) or a volume. Each dump flows from the dump tool through the
  encryption to the upload as one pipeline. The manifest and the completion record are built in
  memory. A failure of any stage of a pipeline fails the run; no stage's exit status is lost. If a
  design needs a staging file, the work stops and returns to the Architect as an ADR-0005 question
  (*Places off the paths*). The diagnostic output of the tools (`pg_dump`, `pg_dumpall`, `psql`,
  `age`, the SFTP client) never reaches the log. The run maps it to the fields of the failure line.
- **The schedule and the on-demand run.**
  - The scheduler is `backup`'s own main process, not `cron`. Debian's `cron` would run the job as
    root and without the container's environment, so the secrets would have to be written to a
    file for it.
  - It reads its table from one schedule file in the image, kept in the repository at
    `backup/schedule`. The file holds exactly one entry: the time `01:00`, the zone written `UTC`,
    and the run command. The scheduler refuses to start, with the failure line, when the file holds
    no entry, more than one, or any zone other than `UTC`. Once started, it writes the table it
    loaded, as parsed, to one non-secret file in the container, `/run/eko-backup/loaded-schedule`,
    and into its start-up log line. A test reads that file through `docker compose exec`.
  - It compares the entry with the UTC clock, whatever the container's zone. The container's zone
    is UTC, and the scheduler refuses to start when its effective zone is anything else, so a zone
    set to Europe/Warsaw fails visibly. It starts at most one run per UTC date, in the minute 01:00
    UTC, and makes up no missed run (ADR-0004-C17 catches a missing set).
  - The schedule entry and the on-demand command run the same entry point, `eko-backup run`.
  - **The on-demand command** is a one-off container of the `backup` service, with that service's
    environment, removed when it ends and starting no other service:
    `docker compose run --rm --no-deps backup eko-backup run`. Its exact text is kept in
    `backup/README.md`. It exits 0 only once the set at the destination is complete under the
    completeness rule. *Deployment* step 1 is this command.
  - `backup` is a dependency of no other service, so starting another service never starts it.
    ADR-0005's *No backup before the re-apply* therefore holds at a restore: `backup` runs only
    once the operator starts it, at restore step 14.
- **A failed run is one line.**
  - Every failed run exits non-zero and writes exactly one line of this form to standard error,
    which is the container log for a scheduled run and the operator's terminal for an on-demand
    run: `eko-backup: run failed reason=<reason> set=<set name, or -> at=<RFC 3339 UTC time>`,
    optionally followed by ` sqlstate=<five-character SQLSTATE>`.
  - `<reason>` is one of a closed list: `schedule`, `database` (connection or authentication,
    refusal for the connection limit included), `lock`, `dump-application`, `dump-keycloak`,
    `dump-roles`, `encryption`, `destination` (unreachable, refused, wrong host key, an upload
    broken off, or a confirmation that failed) and `interrupted`.
  - The line holds no other field and no free text: no tool's message, no host, address, port,
    account, path or connection string, no credential and no row value (ADR-0005 *What may appear
    in logs*).
  - A required variable that is unset or empty stops `backup` before any connection, with the
    message every service uses for ADR-0004-C10 (`configuration error: missing or empty
    environment variable: <NAME>`). That is a refusal to start, not a failed run.
  - A successful run writes one line holding its start and end times, the set's name, its outcome
    and the row counts, and no line of the failure form.
  - **The one place it is documented** is `backup/README.md`. It holds the line's exact pattern,
    the reason list, the on-demand command and the operator step for existing volumes (below). The
    test reads the pattern from there, and the IT department's monitoring is connected to that
    document at EKO-1-08 (#36). A change to the line's form is a change to this addendum.
- **An interrupted run.** <!-- GATE-1: Q-4 (G-8) — options and recommendation in EKO-1-14's
  impact map --> On `SIGTERM` (for example `docker compose stop`), the run stops its tools, writes
  the failure line with `reason=interrupted` and exits non-zero within the composition's stop grace
  period. On `SIGKILL` it writes nothing. Either way, no file holds any part of the set, no
  completion record is written, so the set is incomplete, and the server releases the lock when the
  control session ends.
- **Where a test holds a run.** No hold point is a lock that `migrate` can wait for, except where
  the advisory lock is itself the subject:
  - **H0, before the snapshot.** A test session holds the advisory lock, same key and same form,
    and no other lock. `backup` waits at step 1. It is used where the advisory lock is the subject
    (the backup half of ADR-0004-C26, `migrate` holding the lock) or the reference time (the
    backup point is no earlier than the release).
  - **H1, during the Keycloak dump, after the application dump has ended.** A test session holds
    an `ACCESS EXCLUSIVE` lock on one table of Keycloak's database that Keycloak does not use after
    its start. `backup`'s Keycloak dump waits on that table with its session open. No `migrate` run
    can contend with that lock, because the application role cannot connect to Keycloak's database
    (ADR-0003-C11), so an exclusion seen at H1 can come only from the advisory lock. If no
    Keycloak table qualifies, the work returns here.
  - Never a hold point: a lock on any object of the application database; a hook, variable or
    pause built into the shipped `backup` image or its scripts. A changed entry point is a planted
    contrast, and a claim is never proven on it (addendum of 2026-10-29, *Test-only revisions*).
- **`eko_backup`'s read privileges.** Amended in fix round 1 of EKO-1-14, 2026-10-31 (B-01 A):
  explicit grants replace membership in the predefined role `pg_read_all_data`, which also reads
  `pg_authid` and cannot be narrowed.
  - **What it is granted.** The schema is `public` in both databases: in the application database
    `eko`, and in Keycloak's database `keycloak`. `compose.yaml` sets no `KC_DB_SCHEMA`, and no
    schema named `eko_keycloak` exists, so Keycloak's tables land in `public`. In each of the two
    databases, `eko_backup` gets:
    - `USAGE` on schema `public`;
    - `SELECT` on every table and every sequence that already exists in it
      (`GRANT SELECT ON ALL TABLES IN SCHEMA public`, `GRANT SELECT ON ALL SEQUENCES IN SCHEMA
      public`). "Tables" here includes views, materialized views and foreign tables;
    - default privileges for the role that owns the database, `eko_app` in `eko` and `eko_keycloak`
      in `keycloak`. They are written without `IN SCHEMA`, so they apply in every schema of that
      database: `ALTER DEFAULT PRIVILEGES FOR ROLE <owner> GRANT SELECT ON TABLES TO eko_backup`,
      the same `ON SEQUENCES`, and `GRANT USAGE ON SCHEMAS TO eko_backup`. A table, sequence or
      schema that the owning role creates later is then readable with no new grant (K-03
      point 8). That covers a migration run by `migrate` as `eko_app` and Keycloak's own schema
      updates run as `eko_keycloak`.

    It gets no write privilege. Its attributes are unchanged (ADR-0004-C28), `CONNECT` is
    unchanged, and `TEMPORARY` stays revoked from `PUBLIC`.
  - **Who runs the grants, and where.** The init content in `compose.yaml` runs them as the
    PostgreSQL superuser (`POSTGRES_USER`), in the same `psql` run as the rest, after the
    statements that create the roles and databases. Grants on objects and default privileges
    each belong to one database, so the run connects to `eko` and runs that database's
    statements, then does the same in `keycloak`. Default privileges apply only to objects created
    by the role they name. The statements are therefore always written `FOR ROLE eko_app` and
    `FOR ROLE eko_keycloak`, never for the superuser that runs them; a superuser may set them for
    any role. On an empty volume no table exists yet, so at first initialisation it is the default
    privileges that take effect, and the `ON ALL TABLES`/`ON ALL SEQUENCES` statements matter for
    existing volumes. The two per-database connections are sessions of their own. They carry no
    secret, so the one-session rule of the addendum of 2026-10-28 (*What it creates*) does not
    cover them. That rule keeps a password out of the server log, and its list leaves the backup
    role's read privileges to this task.
  - **What it cannot read.** `eko_backup` belongs to no predefined role and is not a superuser.
    It cannot read `pg_authid`, so it cannot read any role's password verifier, the superuser's
    included.
  - **The roles object without `pg_authid`.** With `--no-role-passwords`, `pg_dumpall` reads the
    roles from the view `pg_roles` instead of `pg_authid`. That is documented PostgreSQL behaviour
    since version 10 and still holds in 18. Memberships come from `pg_auth_members` and per-role
    settings from `pg_db_role_setting`, and every role can read both. So
    `pg_dumpall --roles-only --no-role-passwords` runs as `eko_backup`. The object is complete
    except for passwords: every role other than the predefined `pg_` roles, with its attributes,
    `CONNECTION LIMIT` and `VALID UNTIL`, its memberships with their options, and its settings. A
    run that drops `--no-role-passwords` makes `pg_dumpall` read `pg_authid`. It then fails with
    `reason=dump-roles` and SQLSTATE 42501 instead of putting verifiers in the set.
  - `SELECT` does not bypass row-level security, and `eko_backup` keeps `NOBYPASSRLS`. `pg_dump`
    then fails on a table with row-level security, rather than dumping it partially. A task that
    enables row-level security on a table changes this addendum first.
  - **What is not covered (residual).** Default privileges cover only objects created by
    `eko_app` in `eko` and by `eko_keycloak` in `keycloak`. Three kinds of object get no grant:
    - an object created by any other role, such as the superuser by hand or a role added later;
    - on an existing volume, an object in a schema other than `public`;
    - a large object.

    The dump then fails with `reason=dump-application` or `reason=dump-keycloak` and SQLSTATE
    42501. It fails closed: there is never a set that silently lacks the object (the K-03
    contrast). A task that adds a role creating objects in either database changes this addendum
    first.
  - **Existing volumes** (addendum of 2026-10-28, *Existing volumes*). The release that brings these
    grants announces one operator step, as the PostgreSQL superuser on the running `postgres`:
    - connected to `eko`: `GRANT USAGE ON SCHEMA public TO eko_backup;`,
      `GRANT SELECT ON ALL TABLES IN SCHEMA public TO eko_backup;`,
      `GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO eko_backup;`, and
      `ALTER DEFAULT PRIVILEGES FOR ROLE eko_app GRANT SELECT ON TABLES TO eko_backup;` with the
      same for `ON SEQUENCES` and `GRANT USAGE ON SCHEMAS`;
    - connected to `keycloak`: the same six statements, with `FOR ROLE eko_keycloak`;
    - once, in either database: `REVOKE pg_read_all_data FROM eko_backup;`. This brings a volume
      first initialised by an earlier content of this task to the same state. On any other volume
      it changes nothing beyond a warning.

    The step is written in `backup/README.md`. Without it, a run fails with
    `reason=dump-application` and SQLSTATE 42501. Running it again changes nothing.
  - At restore step 4 the init content sets these privileges on the empty volume.
- **Secret inventory: the variable names.** The two rows read, in addition to what they say:
  - *Backup destination write credential* — variable `BACKUP_DESTINATION_CREDENTIAL`.
  - *Backup encryption public key* — variable `BACKUP_ENCRYPTION_PUBLIC_KEY`.

  No other cell of either row changes. Both are required in `compose.yaml` with no default
  (ADR-0004-C9). Unset, empty or whitespace-only, either one stops `backup` before it connects to
  the server or the destination (ADR-0004-C10). Two further values differ between environments
  and are not secret (*Cloud-agnostic constraints*, item 2): `BACKUP_DESTINATION`
  (`sftp://<account>@<host>:<port>/<incoming directory>`) and `BACKUP_DESTINATION_HOST_KEY` (the
  destination host's public key line). They are required and refused in the same way, and they
  are not in the inventory. `backup` receives no other service's environment file, `backend`'s in
  particular, so no Google token encryption key can reach a set (ADR-0006-C3).

Every other rule and control of this decision is unchanged. ADR-0004-C1 is unchanged: no service
is added. ADR-0004-C15's seven days, ADR-0004-C16 at the real destination and ADR-0004-C17 remain
EKO-1-08's (#36).

**The IT department's acceptance.** The protocol, its configuration, the encryption format and
the key form are a proposal that the IT department has not yet accepted (Issue #55, C-1 A).
EKO-1-08 (#36) records its acceptance. If the IT department refuses, this addendum changes and the
transport and encryption step of `backup` is reworked. That rework risk is accepted.

**Consequence for EKO-1-14's Story.**

- Definition of done item 6 and criterion K-03, static check: "a private key" reads "a backup
  encryption private key (an age identity)". `BACKUP_DESTINATION_CREDENTIAL` in `backup`'s
  environment file is itself an SSH private key, and the check must not count it.
- Criterion K-02 (a) holds `backup` at H1; K-02 (b) and K-03 point 6 at H0.
- Criterion K-05 reads the failure pattern from `backup/README.md`.
- Criterion K-06's ADR-0004-C10 checks also cover `BACKUP_DESTINATION` and
  `BACKUP_DESTINATION_HOST_KEY`.
- Criterion K-03's existing-volume contrast uses the operator step above.

**Options considered for this addendum.**

| Question | Option | Cost | Closes off |
|---|---|---|---|
| Destination protocol (Q-1) | **A. SFTP on OpenSSH, request allow list and umask `0377`** (proposed) | the IT department configures one restricted account and keeps its `VERBOSE` log; the write credential is an SSH private key in `backup`'s environment file; the client must stream from a pipe without a key file | nothing |
| | B. An S3-compatible object store on the IT department's host, with put-only access and object lock | the IT department runs an object-store product; refusing an overwrite, not only keeping the old version, depends on that product; the double must implement request signing | nothing |
| | C. HTTPS `PUT` to a receiver the IT department runs | stock WebDAV servers overwrite on `PUT`, so create-only needs software the IT department maintains | nothing |
| Encryption (Q-2) | **A. age v1, one X25519 recipient, one-line keys** (proposed) | a tool the IT department may not know | nothing |
| | B. OpenPGP with GnuPG | a multi-line public key encoded for one variable; a keyring written inside the container; more modes to get wrong | nothing |
| Completion record (Q-5) | **A. Plaintext, names, sizes and digests only** (proposed) | the destination sees set names and sizes, which the object names already show | nothing |
| | B. Encrypted, or none | a check without the private key cannot tell a complete set from a partial one, so ADR-0004-C17 counts a partial upload as fresh | a freshness check off the server that needs no private key |
| Scheduler | **A. `backup`'s own main process, one-entry schedule file** (chosen) | a small loop to maintain | nothing |
| | B. `cron` in the image | jobs run as root without the container's environment; the secrets would be written to a file | secrets only as environment variables |
| | C. A third-party scheduler binary | a download outside the base's packages, pinned by checksum | nothing |
| Read privileges | A. `pg_read_all_data` (chosen at gate 1; withdrawn in fix round 1 of EKO-1-14, 2026-10-31, B-01 A) | it also reads `pg_authid`, so every role's password verifier, the superuser's included, and PostgreSQL cannot narrow a predefined role | keeping password verifiers out of `backup`'s reach |
| | **B. `USAGE` and `GRANT SELECT` on schema `public`, plus `ALTER DEFAULT PRIVILEGES` for the owning role of each database** (chosen in fix round 1 of EKO-1-14, 2026-10-31, B-01 A, because `pg_read_all_data` exposes `pg_authid`) | an object created by another role, an object in another schema on an existing volume, or a large object is not granted, and the run fails with 42501; one set of statements per database | reading objects created later by a role other than the owners with no new grant |
| Hold points | **A. H0 (the advisory lock) and H1 (a lock in Keycloak's database only)** (chosen) | H1 needs a Keycloak table unused after start | nothing |
| | B. A test variant of the `backup` image that pauses the dump tool | the claim is proven on an image that differs from the one shipped | proving the claim on the shipped image |
| | C. A pause hook in the shipped service | test code in the release | a release free of test hooks |

**Why.** Each rule here decides something *Backup*, *Migrations* and the addendum of 2026-10-28
leave open. The task cannot be built without these decisions, and the choices that bind the IT
department are reviewed by a human before code depends on them (Issue #55, G-1 A). Two sessions
keep the run within the limit of 5 that ADR-0003 records. One control session that holds the lock,
then exports the snapshot and counts in it, gives the order *Migrations* asks for and the counts
*Scope* asks for. It also gives a backup point that ADR-0005 can use. Streaming through the
encryption keeps every part of a set off the server's disks, as ADR-0005 *Places off the paths*
requires. A completeness rule replaces the deletion that an append-only destination forbids.
Enforcing write-only at the destination keeps ADR-0004-C16 true against a compromised server. This
is not a deviation from ADR-0004, ADR-0003 or ADR-0005: it decides what they leave open. To be
approved by the human at gate 1 of EKO-1-14 (G-1 A, Issue #55).

### 2026-11-04 — Releases: the release tag, the release composition and its record, the registry write credential, and what a release run guards

**Status:** Accepted 2026-11-04
<!-- Accepted by the human at gate 1 of EKO-1-15 (Issue #56), 2026-11-04: R-1 A, G-6 A+, G-1, G-5, G-7, G-8 and G-9 A, the release-tag form as written. -->

**What it settles.** *Images* has CI build images "from a release tag" and push them to the
project's container registry, and has "a release's composition" reference them by digest. The
addendum of 2026-10-28 on *Images* widens the digest rule to `postgres`, `keycloak` and `proxy`'s
base. The addendum of 2026-10-29 says that "nothing yet fixes what a release tag is" and gives
EKO-1-15 (#56) the choice of which release is the previous one. None of these says what a release
is, where its composition lives, or what the readers of releases (CI, the operator) count as a
published release. Three passages of this decision also take the composition from the repository:
*Container runtime* ("from one composition file kept in the repository"), *Restore procedure*
("the composition from the repository at the release tag", step 2), and *Deployment* (steps 2 and
rollback, by "the digests its composition names"). The repository at a release tag holds tag pins
and local builds, not digests. A restore that takes its composition from there runs what the B-01
widening forbids. From this date:

- **A release tag.** A release tag is a tag of the form `v<major>.<minor>.<patch>`, each part a
  decimal number with no leading zero. A tag with any other form, a pre-release suffix
  included (Issue #56, G-7), is not a release tag. Release tags are ordered by their numbers, never
  as text. A release tag lower than a published one is refused (G-8). A release is made only from a
  commit on `main` (G-5).
- **A release.** A release is a release tag whose release run passed every check on the tagged
  commit and then produced its release composition. A release-form tag whose run was refused,
  failed or stopped before the release composition exists is not a release (G-9). A release, once
  published, never changes: no later run replaces its release composition, and no later run pushes
  under its name.
- **The release composition.** It is the one composition file kept in the repository at the
  release tag, rendered with only these differences: every image reference of the
  shared-environment profile is in digest form (`<tag>@sha256:<64 lower-case hex>` or the bare
  digest), project-built images name the digests of the images the release run checked and pushed,
  and no service of that profile has `build:`. Required variables stay required variables. No
  environment value is substituted into it, and it holds no secret value (*Secret handling*). It is
  the composition file *Container runtime* means for every shared environment.
- **Where the release composition and the record of releases live.** An OCI artifact in the
  project registry (`ghcr.io/tanercrb/eko-crm/…`), one per release tag (R-1 A, chosen at gate 1). The record that CI and the operator read as "the published releases"
  is the same place that holds the release compositions. A file in the repository is never that
  record (addendum of 2026-10-29, *Why*).
- **The previous release** is the highest release in release-tag order other than the one being
  built (G-1) whose tagged commit is reachable from `main` when the record is read (G-6 A+). A
  release whose tagged commit is not reachable from `main` is not counted; when reachability
  cannot be determined, the reader fails as "the check itself failed". Both the API-compatibility check (addendum of 2026-10-29) and the previous-release
  half of ADR-0004-C13 read it from the record above: the OpenAPI document as that release's
  backend, started by digest, serves it directly (ADR-0003, addendum of 2026-10-28), and its
  backend image by digest. While the record lists no release, each says it compared nothing and
  reports no pass. When the record cannot be read, or lists a release whose composition, image or
  document cannot be obtained, the check fails as "the check itself failed", never as "no release".
- **Deployment, rollback and restore take the release composition from the record.** *Deployment*
  step 2 and *Rollback to the previous release* use the release composition of the release
  deployed. *Restore procedure* step 2 fetches the release composition of the release currently
  deployed from the record, together with the repository at its release tag for everything else it
  needs. Exception EKO-1-03/R-18 on that step's choice of release is unchanged and stays EKO-1-08's
  (#36).
- **The registry write credential.** Writing to the project registry happens only in a release
  run, with that run's own short-lived `GITHUB_TOKEN` granted `packages: write` in the jobs that
  push and nowhere else. No long-lived registry write credential exists: none is a repository or
  environment secret, none is in a tracked file, an image or a server. This is not a secret of the
  inventory under *Secret handling*: it has no master copy, and nothing holds it after the run. The
  row *Container registry pull credential (read-only)* is unchanged. Who holds it, and how the
  operator reaches the record, stays EKO-1-08's (#36).
- **What the release run guards, and what it does not.** On a tag push GitHub runs the workflow
  file of the tagged commit. On the free plan for a private repository, as the human confirms in
  the repository settings, there are no tag rulesets or branch rulesets, and no environment
  protection rules. The package setting for Actions access is per repository, not per ref or
  workflow. Any workflow on any pushed ref of this repository can therefore request
  `packages: write`. The release run's own checks (the tag form, the commit on `main`, the
  account) bind only a tagged commit that carries `main`'s release workflow. Agent sessions act
  through the account `TanerCRB`, so no check in CI can tell an agent's tag from the human's. Under
  G-6 A+ (chosen at gate 1), "an agent never pushes a release tag" rests on the agent sessions'
  permission settings (Issue #83) and the human's push approval, and every reader of releases (CI's
  previous-release selection now, the operator's procedure in EKO-1-08) accepts a release only
  when its tagged commit is reachable from `main` at read time. That closes a branch tag's bypass
  of the release run's checks for the readers; it does not cover the account. Both limits are
  stated in the capability register's *What this does not prove* for the release pipeline.

**New controls.**

| Control | Acceptance criterion |
|---|---|
| ADR-0004-C29 | In every published release composition, every `image:` of the shared-environment profile carries `@sha256:` and 64 lower-case hexadecimal digits, no service of that profile has `build:`, and the `FROM` of `proxy/Dockerfile` at the release tag carries a digest; a fixture with one tag-only reference (a project image, `postgres`, `keycloak`, `proxy`'s `FROM`) fails naming it. |
| ADR-0004-C30 | Across every file in `.github/workflows/`, only jobs of the release path hold `packages: write` (a job or workflow with no `permissions` key counts as holding it), and only behind the release admission; registry login uses no credential other than `GITHUB_TOKEN`; the repository's secrets list holds no registry credential. |
| ADR-0004-C31 | The digests a release composition names equal the registry's for those references and the images the release run's checks ran on; a second release run for a published release tag fails before pushing, and the release composition and its digests are unchanged after it. |

Every other rule and control of this decision is unchanged. ADR-0004-C1 is unchanged: no service is
added.

**Options considered for this addendum.**

| Question | Option | Cost | Closes off |
|---|---|---|---|
| R-1: where the release composition and the record of releases live | A. **An OCI artifact in the project registry** (`ghcr.io/tanercrb/eko-crm/…`), one per release tag | the release path needs only `packages: write`; PR runs need `packages: read` to list releases; listing tags of a private user-owned package with `GITHUB_TOKEN` is unproven here; a registry tag can be re-pointed by any workflow holding `packages: write`, so "never changes" rests on the release run's refusal and on readers taking the composition's own digest | nothing; the operator retrieves it with the read-only pull credential already in the inventory, and *Images*' "the registry is used at deployment only" holds |
| | B. **A GitHub release on the release tag, the composition as its asset** | the release job also needs `contents: write`, which on this plan (no branch protection) also lets that job push to `main` and move tags; the operator needs read access to the private repository besides the registry credential, a credential the inventory does not list (restore step 2 already assumes repository access); release assets can be replaced by the account | nothing |
| | C. A file committed to the repository | the digests exist only after the run, so a second commit on `main` follows every tag, made by CI with `contents: write` or through a pull request that can edit the record | a record no pull request can change (addendum of 2026-10-29, *Why*); DoD 7 of #56 |
| | D. An artifact of the release run | Actions artifacts expire (at most 90 days on this plan) | rollback and restore of any release older than that |
| G-6: a guard outside the tagged commit's workflow | **A. Accept the stated limit** (proposed): the release run's checks bind a tagged commit carrying `main`'s release workflow; "never an agent" rests on session settings and push approval | two claims are stated as unproven in the capability register | nothing now; a later Story can add B |
| | A+. As A, and every reader (CI's previous-release selection, the operator's procedure) also accepts a release only when its tagged commit is reachable from `main` at read time | one more check in each reader; it does not cover the account (C-2) | nothing |
| | B. A guard GitHub enforces | needs a paid plan (tag rulesets) **and** agents on their own GitHub identity without the admin role, because the owner bypasses rulesets; neither exists, and both are outside this task | nothing, but it is a new Story |

**Why.** Without a definition of a release and of its record, the previous-release checks of the
addendum of 2026-10-29 have nothing to read, and EKO-1-08 (#36) has nothing to pull. Taking the
composition from the repository at the release tag would make deployment, rollback and restore run
tag-pinned third-party images, which the B-01 widening of 2026-10-28 forbids for shared
environments. This is a declared deviation: it restates where *Container runtime*, *Deployment*
and *Restore procedure* step 2 take the composition from, and it adds controls. Approved by the
human at gate 1 of EKO-1-15 (Issue #56), 2026-11-04: R-1 A and G-6 A+.

### 2026-11-06 — *Releases*: the readers' reachability rule does not close a planted record entry

**What it corrects.** The addendum of 2026-11-04 on *Releases*, in its item *What the release run
guards, and what it does not*, says of the readers' reachability rule: "That closes a branch tag's
bypass of the release run's checks for the readers". **That sentence does not hold.** The same
item already states that any workflow on any pushed ref of this repository can request
`packages: write`. Such a workflow needs no tag and no pull request. It can push images under
`ghcr.io/tanercrb/eko-crm/…` and write a record entry under a release-form tag, a new one or an
already published one, because the registry overwrites a tag on write. The refusal to replace a
published release lives only in the release run. The entry's tagged commit, as readers see it, is
the `org.opencontainers.image.revision` annotation, and the writer sets it. A planted entry that
names any commit on `main` therefore passes the reachability rule. From this date, the text of
2026-11-04 is read with this correction:

- **What the reachability rule guards.** An honest record entry, written by a release run, whose
  tagged commit is not reachable from `main` when the record is read: for example, a release-form
  tag pushed on a branch whose run published. Readers do not count it as a release.
- **What it does not guard.** A planted or overwritten record entry, written by any workflow that
  holds `packages: write`, whose revision annotation names a commit on `main`. Readers cannot tell
  such an entry from a release (*A release*: a release tag whose release run passed every check).
  The rule checks the annotation, not who wrote the entry. *A release, once published, never
  changes* binds release runs. It does not bind such a workflow.
- **The narrowing in place (EKO-1-15, PR #85).** The CI readers, the API-compatibility check
  (addendum of 2026-10-29) and the previous-release half of ADR-0004-C13, take only the backend
  image digest from the record entry. They run it under the `compose.yaml` of the commit under
  test. The entry's own composition is never given to Docker Compose, so a planted entry cannot
  bring services, mounts, volumes or dependencies of its own into a CI run.
- **The residual risk.** A planted or overwritten entry still decides which backend image runs as
  "the previous release" in every CI job that reads the record. That image serves the OpenAPI
  document the API-compatibility check compares against. It is also the image the C13 test
  migrates and health-checks. So it controls the outcome of both checks: it can make them pass or
  fail as its author chooses. A planted entry with a release tag higher than every real release
  also makes the release admission refuse every real release ("a release tag lower than a
  published one is refused"), which blocks releasing until the entry is removed.
- **Where it is recorded.** This residual is the recorded exception **EKO-1-15/security-1**
  (owner @TanerCRB, blocks again on 2027-02-05, or earlier if EKO-1-08 starts reading the record).
  Provenance of record entries is Issue **#84**, which is not decided.
- **For EKO-1-08 (#36).** The operator's procedure reads the same record (*Deployment, rollback and
  restore take the release composition from the record*). Until #84 is decided, that procedure
  must not treat the record, or the reachability rule, as establishing that an entry is a release
  produced by a release run, or that its composition and digests are the ones that run checked.
  When EKO-1-08 starts reading the record, exception EKO-1-15/security-1 blocks again.

The second half of the corrected sentence, "it does not cover the account", is unchanged. The
capability register's *What this does not prove* for the release pipeline must state the planted
entry as well as those two limits.

**Controls.** ADR-0004-C29, C30 and C31 do not change. Their wording does not depend on the
corrected sentence:

- C29 states what every published release composition holds. It does not claim who wrote an entry.
- C30 binds the workflow files of the ref under test. It does not claim that a workflow on another
  pushed ref cannot hold `packages: write`, and the addendum of 2026-11-04 already says one can.
- C31 binds a second release run for a published release tag. It does not claim that another
  workflow cannot overwrite the entry.

None of them is to be read as closing the planted-entry path. No control is added. Every other rule
and control of this decision is unchanged.

**Why.** The security auditor's finding B-01 on EKO-1-15 showed that the reachability rule checks a
revision the writer sets. Finding B-03 showed that this decision still said the bypass was closed.
A reader of the decision, or the author of EKO-1-08's procedure, would then rely on a guard that
does not hold. B-03 was accepted by the human at gate 2 of EKO-1-15 (Issue #56, PR #85), as part
of exception EKO-1-15/security-1, with this correction to be made in the documentation PR. This is
not a deviation. It withdraws a claim that the text of 2026-11-04 made, and it states the residual
risk that exception covers. No rule chosen at gate 1 (R-1 A, G-6 A+) changes.
