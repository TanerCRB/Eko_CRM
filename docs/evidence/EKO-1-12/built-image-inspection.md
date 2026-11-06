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
