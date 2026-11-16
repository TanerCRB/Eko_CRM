# EKO-1-12 bootstrap provider-verification contrast record

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the run: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa (dirty worktree)
Custom image under test: `localhost/eko-crm/keycloak:26.8.1-eko112`
(`sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`)

## Purpose

The bootstrap now verifies, before either listener opens, that the custom same-ID factory is the
active eventsStore provider and that its required filtering holds in the live store. This record
establishes that the carrier for that check is decisive: the same live scenario stores a
non-excepted `details.code_id` on the built-in `jpa` path and does not store it on the custom
path. All containers were created in one throwaway project prefixed `eko112-d18-` and removed
afterwards with their own volumes; no pre-existing volume or state was deleted and no prune was
run. The contrast image was built from a throwaway Dockerfile outside the repository (official
26.8.1 base, `kc.sh build --spi-events-store--provider=jpa`, no provider JAR); it is not a
versioned artifact.

## Observed pair (shape and booleans only; no value, log line, or event body is recorded)

Against a running composition with the master realm configured through the existing bootstrap
code path, the carrier is a master-realm browser (PKCE code) login failure for the declared
synthetic verification account through the existing `security-admin-console` client:

1. Built-in contrast image (provider absent): the running server's log contains no
   `KC-SERVICES0047` line naming the custom factory (grep count 0), and the stored `LOGIN_ERROR`
   carrier contains a non-empty `details.code_id` alongside `details.username`. The new
   verification exited non-zero with
   `bootstrap failed: RuntimeError: non-excepted code_id reached the live store: built-in JPA path`.
   Both listeners stayed closed (no gate file is written before the verification).
2. Custom image (accepted shape): the running server logs the `KC-SERVICES0047` line naming
   `org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory` for the internal SPI
   `eventsStore` (grep count 1), and the same carrier is stored with `details.username` retained
   and no `details.code_id` anywhere in the window. Verification emitted
   `{"event":"filtering verified"}` with exit code 0.

The full end-to-end fresh bootstrap, restart and closed-listener contrasts against the final
custom image are recorded in `bootstrap.md`.

## Meaning

The absence of `details.code_id` in the custom run is not an empty-store artifact: the carrier is
provably produced and provably persisted with its other detail (`username`), and the same carrier
reaches the store with `code_id` when the built-in factory is active. A missing, unselected or
filtering-broken provider therefore fails verification and keeps both listeners closed.

No credential, identifier value, token, cookie, raw event, raw log, marker or personal data
appears in this record.
