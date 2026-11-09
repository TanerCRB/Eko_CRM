# EKO-1-12 built-image inspection record (K-06)

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Image inspected: `localhost/eko-crm/keycloak:26.8.1-eko112`,
ID `sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`

Command: `docker run --rm --name eko112-d18-inspect --entrypoint sh
localhost/eko-crm/keycloak:26.8.1-eko112 -c '<inspection script>'` plus
`docker history --no-trunc localhost/eko-crm/keycloak:26.8.1-eko112`.
Throwaway container removed; no volumes or networks created.

## Observed results

| Check | Result |
|---|---|
| `/opt/keycloak/providers` contents | only `eko112-event-store-1.0.0.jar` (4184 bytes, mode 644, owner uid 1000 = `keycloak`, timestamp normalized to the Unix epoch) and the base image's own `README.md` |
| Behavior-test class residue anywhere in the filesystem (`find / -xdev -name '*FilteringJpaEventStoreProviderTest*'`) | 0 hits — the test never entered the final stage; the previous layer-residue risk is structurally gone |
| `/tmp` residue of the task name | 0 |
| `.env*` / `*.env` files anywhere in the image (`find / -xdev`) | 0 |
| `lib/quarkus/quarkus-application.dat` | contains the application root `providers/eko112-event-store-1.0.0.jar` — the provider JAR is a registered runtime class-loader input of the built image |
| Layer history | `COPY --chown=keycloak:keycloak --chmod=644` of the provider JAR, then the `RUN touch -d "@0" ... && kc.sh build --spi-events-store--provider=jpa` line — provider before build, nothing else added |
| Base lineage | built directly on the official `quay.io/keycloak/keycloak:26.8.1` layer stack (base ID `sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b`) |

The build inputs were already secret-free by the versioned-file controls (`identity/.dockerignore`
keeps `.env*` out of the build context; the static K-06 tests scan every tracked file under
`identity/` and the provider source for literal secrets); this record closes K-06's built-artifact
half: the image itself contains no credential, secret value, `.env` file, staff user, or real
personal data, and no test-class residue.

## Limits

An automated scan shows only what was declared to it: it cannot prove that an invented fixture
value bears no accidental resemblance to a real person (stated residual limitation, K-06), and it
inspects the local build, not a registry-pushed or production image.

---

# Re-inspection — rebuilt shipped image (guardian G-21 / reviewer R-22)

Date: 2026-11-09
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD: 83555e1 (`identity/` clean at that commit; none of this round's edits are image
context)
Image inspected: `localhost/eko-crm/keycloak:26.8.1-eko112`,
ID `sha256:1a1fd4d33b232ca9e312b28fc3bddd17a07b79acc82167b8a67b0184ea5a532f`

Provenance. The build ran the round's exact command,
`docker build -t localhost/eko-crm/keycloak:26.8.1-eko112 identity`, exit 0. Every layer was a
cache hit, including the Maven build stage and the `touch -d "@0" && kc.sh build` layer — the
reused layers were produced on this host on 2026-11-09 (config timestamp 10:35:11Z) from a
byte-identical committed `identity/` context, which is what a full cache hit certifies. The two
historical artifact IDs on this task — `387f615a…` (the fix-round-1 provider rebuild recorded in
`custom-image-build-fix1.md`) and the `e49ed47d…` build above — are no longer present on the host,
so this section re-executes the artifact walk on the current clean build rather than a historical
ID; the runtime-run attribution in `fix-round-1.md` keeps pointing at the fix-round-1 record.

Commands: `docker run --rm --entrypoint sh <image ID> -c '<walk>'` (two throwaway containers,
self-removed; default bridge only; no volumes created) plus
`docker history --no-trunc` and `docker image inspect`.

| Check | Observed result |
|---|---|
| `/opt/keycloak/providers` contents | only `eko112-event-store-1.0.0.jar` — 4706 bytes, mode 644, owner uid 1000 (`keycloak`), mtime normalized to the Unix epoch (`1970-01-01 00:00:00`) — plus the base image's own `README.md`; the jar size difference against the 2026-11-06 entry (4184 bytes) is the accepted fix-round-1 provider extension, so the inspected artifact carries the shipped source |
| Test-class residue: `find / -xdev -name '*FilteringJpaEventStoreProviderTest*'` | 0 |
| Test-class residue: `find / -xdev -name '*Test*.class'` | 0; `find /opt/keycloak -name '*Test*' -type f` printed nothing |
| `.env*` / `*.env` anywhere in the image (`find / -xdev`) | 0 |
| Container mounts (`/proc/self/mountinfo` minus overlay/virtual filesystems) | 3 lines, all Docker-standard per-container bind files (`/etc/hostname`, `/etc/hosts`, `/etc/resolv.conf`); no task files, no volumes, nothing else from the host visible |
| `lib/quarkus/quarkus-application.dat` | contains `eko112-event-store-1.0.0.jar` (1 hit) — the provider JAR is a registered runtime class-loader input of this build |
| Layer history (`docker history --no-trunc`) | top lines are `RUN touch -d "@0" …/eko112-event-store-1.0.0.jar && kc.sh build --spi-events-store--provider=jpa` over `COPY --chown=keycloak:keycloak --chmod=644 …/eko112-event-store-1.0.0.jar /opt/keycloak/providers/`, then the base stack — provider before build, nothing else added |
| Base lineage | base `quay.io/keycloak/keycloak:26.8.1` on this host is ID `sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b` — the same base ID the 2026-11-06 record names |

K-06's built-artifact half for the current build stands: no credential, secret value, `.env`
file, staff user or real personal data, and no test residue. Same limits as the 2026-11-06
section: a local build only, no registry or production claim; synthetic values only appear here.
