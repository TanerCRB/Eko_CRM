# EKO-1-12 custom Keycloak image build record

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa (dirty worktree: this invocation's uncommitted implementation)

## What was built

Command: `docker build -t localhost/eko-crm/keycloak:26.8.1-eko112 identity`

Result: exit code 0. This record replaces the stopped build record
`provider-build-stop.md`; the accepted Architect correction of 2026-11-06 moved the provider
behavior test from a `java -cp` RUN against the official image's class layers (three disproved
hypotheses) into the Maven build stage, and the final image keeps only the supported shape.

## Exact identities

- Official base: `quay.io/keycloak/keycloak:26.8.1`, image ID
  `sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b`
- Custom image: `localhost/eko-crm/keycloak:26.8.1-eko112`, image ID and registry digest
  `sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`

## Build-stage observations (from the build output)

1. `mvn -q package` produced `eko112-event-store-1.0.0.jar` and the test classes.
2. The behavior test ran in the same Maven stage against the pinned 26.8.1 provided dependencies
   resolved by Maven (`dependency:build-classpath`): the single RUN
   `package && build-classpath && java -cp target/classes:target/test-classes:$DEPS
   org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderTest` exited 0 (the build continued
   to the final stage; a non-zero exit would have failed the image build).
3. Final stage: the provider JAR `COPY` (`--chown=keycloak:keycloak --chmod=644`) is the only
   addition before `kc.sh build --spi-events-store--provider=jpa`; the build printed
   "installing your custom providers" and `KC-SERVICES0047: jpa
   (org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory) is implementing the
   internal SPI eventsStore`, then "Quarkus augmentation completed".
4. Provider timestamp normalized to the Unix epoch (`touch -d "@0"`) before the build, so the
   build's provider last-modified tracking configuration does not depend on the building
   machine's clock (official container guide, reproducible builds; ADR-0004 *Images* full-version
   pinning unchanged).

## Shape controls

The versioned `identity/Dockerfile` and `identity/**` carry no `java -cp` command against the
Keycloak installation internals, no test-class copies in the final stage, and no reference to the
official image's `lib` layout; `backend/tests/static/test_eko112_k01_custom_provider_image.py`
asserts each of those and fails when the test execution or the providers COPY is moved (red
observed for the new controls before the Dockerfile was rewritten, green after).

## Not proven here

This record proves the artifacts build; provider runtime selection and filtering are proven by
the bootstrap verification (`bootstrap.md`) and the final-image runtime checks (`k02-k06-runtime-results.md`),
and the built image's contents by `built-image-inspection.md`. Local evidence makes no production
claim. No credential, identifier value, or personal data appears in this record.
