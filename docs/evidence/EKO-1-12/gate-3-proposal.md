# EKO-1-12 gate-3 documentation proposal — remove exactly EKO-1-03/R-22

Date: 2026-11-06
Baseline SHA: 2dcb057f818fd9a1e4142fbf0c71276f542f6ffa
Updated: 2026-11-08 (the fix-round provider rebuild; eligibility now names the final image)

## Eligibility

K-02 was verified on the final custom image with the corrected bootstrap order: master
brute-force check before the admin listener, application-realm import and its brute-force
check before the public listener, and the custom-provider selection and filtering
verification before either listener opens. The final image is
`localhost/eko-crm/keycloak:26.8.1-eko112`, `sha256:387f615a11a75e6ee2289206f2e9098113933d83f3a9084bbd8c3882cbc631f8`
(the fix-round rebuild carrying the ADR-0007 option-A provider with the master-realm and
unknown-account field enforcement, `custom-image-build-fix1.md`); it supersedes the
2026-11-06 build image `sha256:e49ed47d8d3677d5f26c9d27d2bb9e76b74a9f54d8b74c1f08258c51d8502b69`.
Runtime evidence: docs/evidence/EKO-1-12/bootstrap.md and the fix-round reruns in
docs/evidence/EKO-1-12/fix-round-1.md

## Proposed register change (the only line removed)

In `docs/architecture/exception-register.md`, delete this single entry and no other:

- Exception EKO-1-03/R-22

Every other exception entry stays byte-identical. The removal applies only when the human merges
the gate-3 documentation PR for EKO-1-12 (#53); until then R-22 remains recorded and blocks
again on 2027-03-31.

## Scope discipline

This proposal removes exactly one line and proposes no other register edit. It does not touch
the ADRs, the capability register, or the plan; those carry their own gate-3 rows. It is a
proposal, not an action: the developer role does not edit `docs/architecture/exception-register.md`.
