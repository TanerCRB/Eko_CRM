#!/usr/bin/env bash
# release-images.sh — the release run's checked images (EKO-1-15, #56; ADR-0004-C31).
#
#   bash scripts/release-images.sh check-identity   # each eko-crm/<name>:checked has the ID the
#                                                   # build recorded (BACKEND_ID, FRONTEND_ID, ...)
#   bash scripts/release-images.sh push <tag>       # pushes the checked images under <tag>;
#                                                   # stdout: <name>=sha256:<digest> per image
#   bash scripts/release-images.sh pulled-digests   # stdout: postgres= and keycloak= digests of
#                                                   # the images the runtime tests pulled by tag
#   bash scripts/release-images.sh --self-test      # contrast cases against a stand-in docker
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

usage() { echo "usage: $0 check-identity | push <tag> | pulled-digests | --self-test" >&2; exit 2; }

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

# ---------------------------------------------------------------------------------- self-test
# Every case runs this script's real modes against a stand-in docker on PATH (no daemon, no
# registry) and would fail if the rule it targets were removed.

self_test() {
  local self root failures=0 total=0 code tag
  self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  root="$(mktemp -d)"
  trap - ERR
  set +e

  mkdir -p "$root/bin"
  cat > "$root/bin/docker" <<'STAND_IN'
#!/usr/bin/env bash
# Answers image IDs from STUB_ID_<NAME>, repository digests from STUB_DIGEST_<NAME>; omits the
# digest of STUB_NO_DIGEST and fails the push of STUB_FAIL_PUSH.
printf '%s\n' "$*" >> "$STUB_LOG"
upper() { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }
ref="${*: -1}"
case "$1" in
  image)
    if [[ "$4" == *RepoDigests* ]]; then
      repo="${ref%:*}"; var="STUB_DIGEST_$(upper "${repo##*/}")"
      [ "${STUB_NO_DIGEST:-}" = "${repo##*/}" ] || printf '%s@%s\n' "$repo" "${!var:-}"
    else
      name="${ref#eko-crm/}"; var="STUB_ID_$(upper "${name%%:*}")"
      printf '%s\n' "${!var:-}"
    fi ;;
  push)
    name="${ref##*/}"
    [ "${STUB_FAIL_PUSH:-}" != "${name%%:*}" ] || exit 1 ;;
esac
exit 0
STAND_IN
  chmod +x "$root/bin/docker"

  sha() { printf 'sha256:%064d' "$1"; }
  # run_release [VAR=value...] -- <mode> [args]: stdout in $root/out, docker calls in $root/log
  run_release() {
    local overrides=()
    while [ "$1" != -- ]; do overrides+=("$1"); shift; done
    shift
    : > "$root/log"
    env PATH="$root/bin:$PATH" STUB_LOG="$root/log" STUB_FAIL_PUSH= STUB_NO_DIGEST= \
      BACKEND_ID="$(sha 1)" FRONTEND_ID="$(sha 2)" PROXY_ID="$(sha 3)" BACKUP_ID="$(sha 4)" \
      STUB_ID_BACKEND="$(sha 1)" STUB_ID_FRONTEND="$(sha 2)" STUB_ID_PROXY="$(sha 3)" \
      STUB_ID_BACKUP="$(sha 4)" STUB_DIGEST_BACKEND="$(sha 11)" STUB_DIGEST_FRONTEND="$(sha 12)" \
      STUB_DIGEST_PROXY="$(sha 13)" STUB_DIGEST_BACKUP="$(sha 14)" \
      "${overrides[@]}" bash "$self" "$@" > "$root/out" 2> "$root/err"
  }
  expect() {
    local description="$1"
    shift
    total=$((total + 1))
    if "$@"; then
      echo "ok   $description"
    else
      echo "FAIL $description"
      failures=$((failures + 1))
    fi
  }
  exit_is() { [ "$code" -eq "$1" ]; }
  out_is() { [ "$(cat "$root/out")" = "$1" ]; }
  no_call() { ! grep -qE "$1" "$root/log"; }
  refused_before_docker() { [ "$code" -eq 2 ] && [ ! -s "$root/log" ]; }
  digests() {
    local line lines=() name
    for name in "$@"; do
      case "$name" in backend) line=11 ;; frontend) line=12 ;; proxy) line=13 ;; backup) line=14 ;; esac
      lines+=("$name=$(sha "$line")")
    done
    printf '%s\n' "${lines[@]}"
  }

  run_release -- check-identity; code=$?
  expect "check-identity passes when every checked image has its recorded ID" exit_is 0
  expect "check-identity inspects all four images" [ "$(grep -c '^image inspect' "$root/log")" -eq 4 ]

  run_release STUB_ID_FRONTEND="$(sha 99)" -- check-identity; code=$?
  expect "check-identity fails (1) on a changed image ID" exit_is 1

  run_release BACKUP_ID= -- check-identity; code=$?
  expect "check-identity fails (2) when an ID was not recorded" exit_is 2

  run_release -- push v1.2.0; code=$?
  expect "push accepts the release tag v1.2.0" exit_is 0
  expect "push prints the registry digest of every image, in order" \
    out_is "$(digests backend frontend proxy backup)"
  expect "push tags the checked image under the release tag" \
    grep -qx "tag eko-crm/proxy:checked $REGISTRY_PREFIX/proxy:v1.2.0" "$root/log"
  expect "push runs no build" no_call build

  for tag in 1.2.0 v1.2 v01.2.0 v1.2.0-rc.1 V1.2.0 "v1.2.0 " ""; do
    run_release -- push "$tag"; code=$?
    expect "push refuses the tag '$tag' (2) before any docker call" refused_before_docker
  done

  run_release STUB_ID_PROXY="$(sha 99)" -- push v1.2.0; code=$?
  expect "push refuses (1) when an image is not the checked one" exit_is 1
  expect "push of a changed image tags and pushes nothing" no_call '^(tag|push) '
  expect "push of a changed image prints no digest" out_is ""

  run_release STUB_FAIL_PUSH=proxy -- push v1.2.0; code=$?
  expect "a failed third push ends the step non-zero" [ "$code" -ne 0 ]
  expect "a failed third push leaves only the digests pushed before it" \
    out_is "$(digests backend frontend)"
  expect "a failed third push pushes nothing after it" no_call '^push .*/backup:'

  run_release STUB_NO_DIGEST=frontend -- push v1.2.0; code=$?
  expect "push fails (1) when the registry gives no digest" exit_is 1
  expect "a missing digest leaves only the digests before it" out_is "$(digests backend)"

  rm -rf "$root"
  echo "Self-test: $total cases ran, $((total - failures)) passed, $failures failed."
  [ "$failures" -eq 0 ]
}

case "${1:-}" in
  check-identity) [ $# -eq 1 ] || usage; check_identity ;;
  push) [ $# -eq 2 ] || usage; push "$2" ;;
  pulled-digests) [ $# -eq 1 ] || usage; pulled_digests ;;
  --self-test) [ $# -eq 1 ] || usage; self_test ;;
  *) usage ;;
esac
