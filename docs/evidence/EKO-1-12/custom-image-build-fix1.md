# EKO-1-12 custom Keycloak image — fix round 1 provider rebuild record — 2026-11-08

Date: 2026-11-08
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Worktree HEAD at the build: 37adca49f5f7cf9dccfa3d94183847503c1cc5e8 (dirty worktree: fix round 1, uncommitted)
Supersedes for the current artifact: the image identity in `custom-image-build.md`
(2026-11-06, `sha256:e49ed47d…`) — that record stays as the dated history of its run.

## What changed in the image

The provider source gained the accepted-destination enforcement required by ADR-0005
(addendum 2026-11-05) and ADR-0007-C5 (G-01/S-01): outside the accepted application-realm
exception scope, the custom store clears the top-level `sessionId` and removes the
unknown-account typed username (`LOGIN_ERROR` with error `user_not_found`) from
`details.username` before the single inherited persist. The `code_id` rule and the accepted
same-event duplicate are unchanged. The Maven build-stage behavior test now covers each new
branch and still gates the image build (a non-zero test exit fails the build).

## Build

Command: `docker build -t localhost/eko-crm/keycloak:26.8.1-eko112 identity`

Result: exit code 0; image ID (content digest): `sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`
(the image's `RepoDigests` on this host mirror this ID — a `localhost/…` reference is not a
registry push; see the R-02 note in the fix-round report).

The host additionally carries a `localhost/eko-crm/keycloak@sha256:…` RepoDigests entry
from local tagging history — the value recorded as the image identity here is the **image
ID** (content), never that host-local digest: the release-flow question for the custom
image (R-02) is open and belongs to the human (see the fix round report).

## Build-stage observations

1. `mvn -q package` built the provider and test classes;
2. the behavior test ran in the same Maven stage against the pinned 26.8.1 provided
   dependencies and exited 0 (the runtime half of the same branches failed RED against the
   pre-fix image in the fix-round red batch, `fix-round-1.md`) — its assertions now include: master-realm LOGIN loses the
   top-level session identifier (event object and persisted `EventEntity.sessionId`),
   unknown-account master `LOGIN_ERROR` loses `details.username` (event and persisted JSON),
   known-account master `LOGIN_ERROR` keeps it, application-realm required-type events keep
   the accepted `sessionId` and the accepted `details.username`, and a non-*Retention*
   application-realm event loses its `sessionId`;
3. final stage: single providers COPY, `touch -d "@0"` epoch normalization, `kc.sh build
   --spi-events-store--provider=jpa`, KC-SERVICES0047 line naming the custom factory;
4. shape re-checked: one jar in `/opt/keycloak/providers`, 644, epoch mtime.

## Not proven here

Runtime selection and filtering are proven by `bootstrap.md` + the fix-round runtime records
rerun on this image; secret/personal-data freedom of the image is the K-06 walk +
`built-image-inspection.md` (rebuilt-image re-inspection: <result>). Local build only; no
registry push, no production claim.
