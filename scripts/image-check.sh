#!/usr/bin/env bash
# image-check.sh — checks on built images (K-04, K-07).
#
#   bash scripts/image-check.sh --frontend <frontend image> <image>...
#   bash scripts/image-check.sh --self-test        # builds two tiny fixture images; needs Docker
#
#   ADR-0001-C5   `node --version` fails inside the frontend image, and no file named `node` is
#                 on its filesystem;
#   ADR-0004-C9   no file named `.env` or `.env.*` exists in any listed image.
#
# Each check prints "ok   <name>" or "FAIL <name> — <why>". Exit codes: 0 = every check passed,
# 1 = at least one failed, 2 = usage or the script itself failed (never read 2 as a pass).

set -Eeuo pipefail
trap 'echo "image-check: the script itself failed (line $LINENO)" >&2; exit 2' ERR

FIXTURE_BASE="busybox:1.37.0"
fails=0

report() { if [ "$2" = ok ]; then echo "ok   $1"; else echo "FAIL $1 — $2"; fails=$((fails + 1)); fi; }

# Fail closed: every failure below is a FAIL naming the image, never an empty, "clean" listing.

image_present() { docker image inspect "$1" > /dev/null 2>&1; }

# The image's file list on stdout; non-zero when the image is missing or any step fails.
file_list() {
  local id listing code=0
  image_present "$1" || { echo "image not found locally" >&2; return 1; }
  # Created, never started: the entrypoint path is not resolved, and nothing is pulled.
  id="$(docker create --pull never --entrypoint /nonexistent "$1" 2> /dev/null)" || { echo "docker create failed" >&2; return 1; }
  listing="$(docker export "$id" | tar -t)" || code=$?
  docker rm "$id" > /dev/null 2>&1 || true
  [ "$code" -eq 0 ] || { echo "docker export or tar failed (exit $code)" >&2; return 1; }
  # Positive control: Docker writes /.dockerenv into every container filesystem, so a listing
  # without it did not come from this image.
  grep -qxE '\.?/?\.dockerenv' <<< "$listing" || { echo "listing lacks /.dockerenv; not a container filesystem" >&2; return 1; }
  printf '%s\n' "$listing"
}

check_no_env_file() {
  local listing found why
  if ! listing="$(file_list "$1" 2> "$TMP_ERR")"; then
    why="$(tr '\n' ' ' < "$TMP_ERR")"
    report "no .env file in $1" "cannot list the image: ${why:-unknown error}"
    return
  fi
  found="$(grep -E '(^|/)\.env(\.[^/]*)?$' <<< "$listing" || true)"
  if [ -z "$found" ]; then report "no .env file in $1" ok; else report "no .env file in $1" "found: $(echo "$found" | tr '\n' ' ')"; fi
}

check_no_node() {
  local listing code=0 why
  if ! image_present "$1"; then report "no Node.js runtime in $1" "image not found locally"; return; fi
  docker run --rm --pull never --network none --entrypoint node "$1" --version > /dev/null 2>&1 || code=$?
  case "$code" in
    0) report "no Node.js runtime in $1" "node --version succeeded"; return ;;
    126 | 127) ;; # the runtime could not find or execute `node`: absent, as required
    *) report "no Node.js runtime in $1" "docker run failed with exit $code, so the check could not decide"; return ;;
  esac
  if ! listing="$(file_list "$1" 2> "$TMP_ERR")"; then
    why="$(tr '\n' ' ' < "$TMP_ERR")"
    report "no Node.js runtime in $1" "cannot list the image: ${why:-unknown error}"
    return
  fi
  listing="$(grep -E '(^|/)node$' <<< "$listing" || true)"
  if [ -n "$listing" ]; then report "no Node.js runtime in $1" "file present: $listing"; else report "no Node.js runtime in $1" ok; fi
}

TMP_ERR="$(mktemp)"
trap 'rm -f "$TMP_ERR"' EXIT

self_test() {
  local dir; dir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$dir'; docker rmi -f eko-image-check-bad:selftest eko-image-check-good:selftest > /dev/null 2>&1 || true" RETURN
  mkdir -p "$dir/bad" "$dir/good"
  printf 'FROM %s\nRUN mkdir -p /app && echo DECOY=1 > /app/.env.local && printf "#!/bin/sh\\necho v22\\n" > /bin/node && chmod +x /bin/node\n' "$FIXTURE_BASE" > "$dir/bad/Dockerfile"
  printf 'FROM %s\nRUN mkdir -p /app && echo ok > /app/index.html\n' "$FIXTURE_BASE" > "$dir/good/Dockerfile"
  docker build -q -t eko-image-check-bad:selftest "$dir/bad" > /dev/null
  docker build -q -t eko-image-check-good:selftest "$dir/good" > /dev/null
  local out
  out="$( fails=0; check_no_env_file eko-image-check-bad:selftest; check_no_node eko-image-check-bad:selftest )"
  if [ "$(grep -c '^FAIL' <<< "$out")" -eq 2 ]; then echo "ok   self-test: .env file and node binary are found"; else echo "FAIL self-test: bad image passed: $out"; return 1; fi
  out="$( fails=0; check_no_env_file eko-image-check-good:selftest; check_no_node eko-image-check-good:selftest )"
  if [ "$(grep -c '^ok' <<< "$out")" -eq 2 ]; then echo "ok   self-test: a clean image passes"; else echo "FAIL self-test: clean image failed: $out"; return 1; fi
  # A missing image must never read as clean (an empty listing is not an empty image).
  local missing="eko-image-check-missing:selftest-$$" code=0
  out="$( bash "$0" --frontend "$missing" "$missing" 2>&1 )" || code=$?
  if [ "$code" -ne 0 ] && ! grep -q '^ok' <<< "$out" && grep -q "$missing" <<< "$out"; then echo "ok   self-test: a missing image fails, naming it"; else echo "FAIL self-test: missing image passed (exit $code): $out"; return 1; fi
}

case "${1:-}" in
  --self-test)
    self_test || exit 1
    ;;
  --frontend)
    [ $# -ge 2 ] || { echo "usage: $0 --frontend <image> <image>... | --self-test" >&2; exit 2; }
    frontend="$2"; shift 2
    check_no_node "$frontend"
    for image in "$@"; do check_no_env_file "$image"; done
    [ "$fails" -eq 0 ] || exit 1
    ;;
  *)
    echo "usage: $0 --frontend <image> <image>... | --self-test" >&2; exit 2
    ;;
esac
