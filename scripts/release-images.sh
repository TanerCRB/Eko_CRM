#!/usr/bin/env bash
# release-images.sh — the release run's checked images (EKO-1-15, #56; ADR-0004-C31).
#
#   bash scripts/release-images.sh check-identity   # each eko-crm/<name>:checked has the ID the
#                                                   # build recorded (BACKEND_ID, FRONTEND_ID, ...)
#   bash scripts/release-images.sh push <tag>       # pushes the checked images under <tag>;
#                                                   # stdout: <name>=sha256:<digest> per image
#   bash scripts/release-images.sh pulled-digests   # stdout: postgres= and keycloak= digests of
#                                                   # the images the runtime tests pulled by tag
#
# Nothing is built here: every image pushed is one the image checks and runtime tests ran on.
#
# Exit codes: 0 = done, 1 = an identity or a digest does not match, 2 = usage or the script
# itself failed.

set -Eeuo pipefail
trap 'echo "release-images: the script itself failed (line $LINENO)" >&2; exit 2' ERR

HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$HERE/../compose.yaml"
NAMES="backend frontend proxy backup"
REGISTRY_PREFIX="ghcr.io/tanercrb/eko-crm"
RELEASE_TAG_RE='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
DIGEST_RE='sha256:[0-9a-f]{64}'

usage() { echo "usage: $0 check-identity | push <tag> | pulled-digests" >&2; exit 2; }

expected_id() {
  local variable
  variable="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')_ID"
  printf '%s' "${!variable:-}"
}

check_identity() {
  local name want got
  for name in $NAMES; do
    want="$(expected_id "$name")"
    [ -n "$want" ] || { echo "release-images: no recorded ID for $name" >&2; exit 2; }
    got="$(docker image inspect --format '{{.Id}}' "eko-crm/$name:checked")"
    if [ "$got" != "$want" ]; then
      echo "release-images: eko-crm/$name:checked is $got, not the checked $want" >&2
      exit 1
    fi
  done
  echo "release-images: every image is the checked one" >&2
}

# The digest the registry answered for <repository>, from the image's repository digests.
registry_digest() {
  local name="${1//./\\.}"
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$2" \
    | sed -nE "s#^$name@($DIGEST_RE)\$#\\1#p" | head -n 1
}

push() {
  local tag="$1" name target digest
  [[ "$tag" =~ $RELEASE_TAG_RE ]] || usage
  check_identity
  for name in $NAMES; do
    target="$REGISTRY_PREFIX/$name:$tag"
    docker tag "eko-crm/$name:checked" "$target"
    docker push --quiet "$target" >&2
    digest="$(registry_digest "$REGISTRY_PREFIX/$name" "$target")"
    [ -n "$digest" ] || { echo "release-images: no registry digest for $name" >&2; exit 1; }
    echo "$name=$digest"
  done
}

# The tag each third-party service names in compose.yaml, through its YAML anchor.
composition_reference() {
  tr -d '\r' < "$COMPOSE" | sed -nE "s/^    image: &$1-image ([^ ]+)\$/\\1/p"
}

pulled_digests() {
  local service reference name digest
  for service in postgres keycloak; do
    reference="$(composition_reference "$service")"
    [ -n "$reference" ] || { echo "release-images: no $service image in compose.yaml" >&2; exit 2; }
    if ! docker image inspect "$reference" > /dev/null 2>&1; then
      echo "release-images: $reference was not pulled by the runtime tests" >&2
      exit 1
    fi
    # Docker Hub's official images are named without their library/ prefix in RepoDigests.
    name="${reference%:*}"
    digest="$(registry_digest "$name" "$reference")"
    [ -n "$digest" ] || { echo "release-images: no registry digest for $reference" >&2; exit 1; }
    echo "$service=$digest"
  done
}

case "${1:-}" in
  check-identity) [ $# -eq 1 ] || usage; check_identity ;;
  push) [ $# -eq 2 ] || usage; push "$2" ;;
  pulled-digests) [ $# -eq 1 ] || usage; pulled_digests ;;
  *) usage ;;
esac
