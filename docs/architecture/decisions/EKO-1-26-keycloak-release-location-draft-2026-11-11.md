# EKO-1-26 — Release location and naming of the custom Keycloak image — addendum draft — 2026-11-11

**Status:** Accepted 2026-11-11 — route A (human, gate 1 of EKO-1-26, Issue #118; the choice was made in-session and recorded by the driving session on the human's instruction: route A — push to GHCR as a fifth project image — selected, scope K-01..K-06 approved, fingerprint f5e632ff85e530ea2144a8b7d1d655f21b9566dc locked)
<!-- The section "Addendum text if route A is accepted" is appended to ADR-0004 as a dated addendum
in this task's gate-3 documentation PR; this file is never itself appended to or edited inside
ADR-0004's accepted text. -->

## Context

ADR-0004's accepted addendum of 2026-11-06 (in force: ADR-0007 option A and the paired ADR-0003
addendum were accepted the same day — ADR-0007:36, ADR-0003:761-800, ADR-0004:1863-1911) says:
"Deployment, rollback, and restore use the release's custom Keycloak image by digest"
(ADR-0004:1880) and "Image references and release composition continue to use the
full-version/digest rules of *Images* and ADR-0004-C2" (ADR-0004:1875-1876). Since PR #117 the
`keycloak` service builds from `identity/` and is named
`localhost/eko-crm/keycloak:26.8.1-eko112` (`compose.yaml:126-129`).

The release machinery still classifies `keycloak` as a third-party pull:
`scripts/release-images.sh:75-90` (`pulled-digests`) demands a registry `RepoDigest` for the
compose anchor's name — one that a locally built image never has — and
`backend/tests/support/release_composition.py:31` keeps `THIRD_PARTY = ("postgres", "keycloak")`,
so a rendered release composition would reference `localhost/...@sha256:...`: a name no operator
can pull at *Deployment* step 2 (ADR-0004:249) or *Restore* step 7 (ADR-0004:362-363). The project
image family is pinned at four in `release_composition.py:29` and
`backend/tests/support/release_workflow.py:121,166-167` ("builds other than the four project
images").

What the accepted text does **not** decide is **where the release publishes the custom image and
under what name it is referenced**. Issue #118's definition-of-done clause 2 leaves that to the
human at gate 1: "built once outside the session, identity-verified, under a name the release can
publish and the composition can reference, BY WHICHEVER ROUTE THE HUMAN ACCEPTS AT GATE 1". This
draft records the question, the routes, and the exact ADR-0004 text each route would carry, so the
choice is made with the consequences visible. This draft selects nothing and authorizes no
implementation.

## Options considered

| Option | Cost | Closes off |
|---|---|---|
| **A. Fifth project image** — CI builds the custom image from `identity/` in the release run, the publish job pushes it to `ghcr.io/tanercrb/eko-crm/keycloak`, the release composition names it by the run's pushed digest | A fifth GHCR package: the first push needs the human's package-access step (precedent #99, `docs/architecture/capabilities.md:30-31`); the `checked-images` job gains a fifth build (its time bound is EKO-1-25/#133 territory); the PROJECT_IMAGES-family constants and the "four project images" wordings move to five with the route | Nothing architectural. Dev path unchanged (`compose.yaml` keeps `build:` + the localhost anchor); `packages: write` stays publish-only (ADR-0004-C30); a gate-3 addendum still fixes the stale *Image versions first used* row (ADR-0004:884) and the composition-table row (ADR-0004:57). |
| **B. Build-identity rule** — the image stays local: each environment builds it from `identity/` and identity is established by recorded image-ID equality against the release run's record | A dated **declared deviation**: the release composition then carries a `localhost/...` reference with no registry digest, against ADR-0004-C29 ("every `image:` ... carries `@sha256:` ... a fixture with one tag-only reference ... fails naming it", ADR-0004:1636), C31 ("the digests a release composition names equal the registry's for those references", ADR-0004:1638), *Deployment* step 2 ("pulls ... by the digests its composition names", ADR-0004:249), *Restore* step 7 ("the image of the release fetched in step 2", ADR-0004:362-363), and the accepted sentence ADR-0004:1880 itself. The `keycloak` service becomes the single exception to the by-digest rule the B-01 widening created — and B-01 named the Keycloak credential store as one of the three images the widening protects (ADR-0004:910, 927-931). Deploy-time identity rests on reproducibility of a Maven + `kc.sh build` image, which no accepted evidence establishes. | The tested==deployed guarantee by digest for the identity server; the operator's uniform pull-by-digest procedure; any later claim that the release record alone names what runs. |
| **C. Another mechanism** (unbounded until the human names it) | If it publishes a **pullable digest** somewhere (e.g. a different registry): fits ADR-0004:1880 like A, but an addendum must name the location (the 2026-11-04 addendum fixes the project registry, ADR-0004:1591-1593) and any second credential against the *Secret handling* inventory (ADR-0004:197 lists only the read-only registry pull credential; C30 ties logins to `GITHUB_TOKEN`). If it publishes **nothing** (e.g. an artifact loaded at deploy): it violates the same sentences as B, plus the R-1 A consequence that the operator retrieves images with the read-only pull credential (ADR-0004:1647). | For any non-publishing C: the same as B, and per the Analyst's gap note (`E:/GitHub/Eko_CRM-EKO-1-26/.task/handoff/3-analyst-2.md:60`) criterion K-03 must be rewritten, not bent. |

## Recommendation

**Route A.** The recommendation is carried by the accepted text, not by preference:

- ADR-0004:1880 requires the release's custom Keycloak image **by digest** at deployment, rollback
  and restore; ADR-0004:1587-1588 already says "project-built images name the digests of the
  images the release run checked and pushed"; ADR-0004:1875-1587 *Images* rules continue to apply.
  Route A is the only candidate that satisfies all three sentences without restating any of them.
- The 2026-10-28 widening made the `keycloak` reference digest-bound because "a publisher or
  registry account that re-points the tag ... runs code CI never tested ... in `keycloak` (the
  credential store)" (ADR-0004:927-931). Routes B and non-publishing C re-open exactly that class
  for the highest-value image: identity by name-plus-recorded-ID at deploy time instead of by the
  digest the release run pushed.
- ADR-0003's accepted addendum states the provider code "is unsandboxed and receives the server
  process's privileges, so it is part of the trusted identity-image supply chain"
  (ADR-0003:785-786). Route A puts that trusted artifact in the same admission-gated,
  published-never-changes record as every other release image (ADR-0004:1579-1590); route B leaves
  the trusted artifact outside the record, rebuilt wherever it runs.
- The two real costs of A are one-time and precedented: the #99 package-access step
  (`capabilities.md:31`: "each new GHCR package needed repository Write access set by hand before
  its first push (#99)") and the family-pin wording move (release_workflow.py:121,166-167). Neither
  conflicts with an accepted control: C30 binds *who may hold `packages: write`*, not *how many
  packages the publish job pushes*; C31's wording ("the images the release run's checks ran on")
  covers a fifth checked image; EKO-1-15's dev-profile rule ("the development profile builds
  locally and never names the project registry", `capabilities.md:31`) is untouched because
  `compose.yaml:126-129` keeps the localhost anchor and `build:` for the dev path, and the
  release-mode freeze arrives through the `EKO_CHECKED_IMAGES` override mechanism
  (`backend/tests/runtime/conftest.py:77-111`), not through a dev-path registry name.

## Addendum text if route A is accepted

The following is the text proposed for ADR-0004 as a dated addendum (date = human acceptance),
appended in the gate-3 documentation PR. It changes no rule of the decision; it records a
classification and refreshes the two stale table rows.

> ### <acceptance date> — The custom Keycloak image is a project-built image
>
> **What it records.** The addendum of 2026-11-06 made the `keycloak` service run a custom image
> built from `identity/`; the *Images* rule of the Decision and the addendum of 2026-11-04 already
> carry every image "built at the release tag, checked and pushed by the release run, and
> referenced by digest in the release composition". From this date the custom Keycloak image
> belongs to that set: the release run builds it from `identity/` once, runs its checks on that
> build, and the `publish` job pushes it to the project registry under
> `ghcr.io/tanercrb/eko-crm/keycloak` and records its digest, like the project images already
> there. A release composition references it by that digest; *Deployment* and *Restore procedure*
> pull it like the other release images. The development profile is unchanged: `compose.yaml`
> keeps the `localhost/eko-crm/keycloak:<full-version>` anchor and the `build:` from `identity/`,
> and the registry is used at deployment only.
>
> Two recorded references are read as superseded for the shared environments: the `keycloak` row
> of the table of *Image versions first used* (the base of `identity/Dockerfile` remains the
> official `quay.io/keycloak/keycloak:26.8.1`) and the `keycloak` row of *Composition and
> placement* ("the official Keycloak image, pinned"): the service runs the custom image, per the
> accepted addendum of 2026-11-06.
>
> No rule or control changes: ADR-0004-C29, C30 and C31 apply to this image unchanged, and C30's
> reading of the publish job is not widened.
>
> **Why.** The release machinery named a keycloak digest it could not obtain from a registry that
> did not hold the image (exception EKO-1-12/R-02, closed by EKO-1-26, Issue #118). Approved by
> the human at gate 1 of EKO-1-26 (route A). This is not a deviation: it records how the image the
> project builds meets rules already accepted.

## Deviation text if route B, or a non-publishing C, is accepted

If the human instead accepts a route in which the custom image is **not** published to a registry
the operator pulls from, the accepted text is **not** followed as written and this decision must
carry a declared deviation. The deviation would have to restate, for the `keycloak` service alone:

1. **ADR-0004-C29** — replace "every `image:` of the shared-environment profile carries `@sha256:`"
   with a build-identity form for the one local image (name plus recorded image ID), and say what
   the "fails naming it" fixture now fails on for that reference.
2. **ADR-0004-C31** — replace "the digests a release composition names equal the registry's for
   those references" with the mechanism that binds the deployed image to the image the run checked
   without a registry (and state the reproducibility assumption for `identity/Dockerfile`, or drop
   the guarantee and record the drop).
3. ***Deployment* step 2 and *Restore procedure* steps 2/7** — the operator no longer "pulls" the
   keycloak image "by the digest" its composition names; the addendum must name what happens
   instead at deploy and at restore.
4. **ADR-0004:1880** — the accepted sentence "Deployment, rollback, and restore use the release's
   custom Keycloak image by digest" is superseded for that route; the addendum says so explicitly.
5. **The B-01 rationale (ADR-0004:927-931)** — the deviation must state that the credential-store
   image is now the one image outside the by-digest rule the B-01 finding created, and what guard
   replaces the digest for it.

Drafting that text is deferred: a decision paper should not pre-write the wording of a route the
recommended route makes unnecessary. If the human selects B or a non-publishing C at gate 1, the
Architect drafts the full addendum for gate-2 approval before any implementation proceeds, and the
Analyst rewrites K-03 (per `3-analyst-2.md:60`) rather than bending it.

## Controls

No new control is proposed. Route A adds no rule; ADR-0004-C29, C30 and C31 (addendum of
2026-11-04) and C2 already bind the accepted outcome. Routes B and non-publishing C would not add
a control either — they would have to restate the acceptance criteria of C29 and C31, which is why
each is a declared deviation rather than a clarification.

## Registry note (independent of the route)

ADR-0004 carries two different controls under the identifier **C29**: the release-composition
control introduced 2026-11-04 (ADR-0004:1636, cited by `architecture-sensitive-paths.md:64-65` and
`capabilities.md:31`) and the event-filtering control introduced 2026-11-06 (ADR-0004:1892).
Any gate-3 addendum for EKO-1-26 should carry a one-line human-directed correction — a dated
addendum restating that the 2026-11-06 control is read as the next free identifier (C33) — never a
silent edit of the accepted tables. This draft does not make that correction itself.

## What acceptance does at gate 1 / gate 3 (process, not decision content)

- **Gate 1 (human):** select A, B or a defined C; accept or reject this draft. Until then the
  EKO-1-26 implementation tasks that touch `PROJECT_IMAGES`-family constants,
  `pulled-digests`/`third_party_digest_violations`, or any release reference to keycloak remain
  **REQUIRES A HUMAN DECISION**.
- **Gate 2 (human):** merge; if A, record the one-time GHCR package-access step for a new
  `eko-crm/keycloak` package before the first release run pushes it (#99 precedent), and the
  rebase observation of PR #135 (DoD clause 5).
- **Gate 3 (human, documentation PR):** append the accepted addendum text to ADR-0004 by dated
  append only (`test_k07_adr_files_change_only_by_appended_dated_addenda` shape), refresh the
  two stale table rows, raise the capability register rows for this task's verified claims, and
  register this decision file in the `docs/PLAN.md` decision index. No dedicated
  documentation-publication configuration exists in this worktree (same finding as
  `EKO-1-12-impact-map-amendment-2026-11-06.md`, *Required process steps* item 3).
