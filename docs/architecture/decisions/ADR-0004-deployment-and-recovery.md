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
