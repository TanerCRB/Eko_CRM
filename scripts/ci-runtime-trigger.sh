#!/usr/bin/env bash
# ci-runtime-trigger.sh — do the runtime tests and image builds run for this event? (K-05)
#
#   bash scripts/ci-runtime-trigger.sh decide <event> <base> <head>   # prints runtime=true|false
#   printf '%s\n' compose.yaml | bash scripts/ci-runtime-trigger.sh --paths -
#   bash scripts/ci-runtime-trigger.sh --self-test
#
# Yes on every event other than a pull request (a push to main runs every job), and on a pull
# request touching a path of docs/architecture/architecture-sensitive-paths.md or the runtime
# tests' own files (AQ-2 A). The register is read through scripts/risk-check.sh, so the filter is
# the register itself and cannot drift from it. A failing register read answers "yes": a check
# that cannot decide never skips the runtime tests.
#
# Exit codes: 0 = decided, 2 = usage or the script itself failed.

set -Eeuo pipefail
trap 'echo "ci-runtime-trigger: the script itself failed (line $LINENO)" >&2; exit 2' ERR

HERE="$(cd "$(dirname "$0")" && pwd)"
RISK_CHECK="$HERE/risk-check.sh"
REGISTER="${RUNTIME_TRIGGER_REGISTER:-docs/architecture/architecture-sensitive-paths.md}"
# The runtime tests and the helpers they import.
RUNTIME_TEST_PREFIXES="backend/tests/runtime/ backend/tests/support/"

usage() { echo "usage: $0 decide <event> <base> <head> | --paths - | --self-test" >&2; exit 2; }

# stdin: one path per line. stdout: "true" or "false" and a reason on stderr.
runtime_for_paths() {
  local paths prefix path classes code=0
  paths="$(tr -d '\r' | sed '/^[[:space:]]*$/d')"
  [ -n "$paths" ] || { echo "no changed path" >&2; echo false; return; }
  while IFS= read -r path; do
    for prefix in $RUNTIME_TEST_PREFIXES; do
      case "$path" in "$prefix"*) echo "runtime test file: $path" >&2; echo true; return ;; esac
    done
  done <<< "$paths"
  classes="$(printf '%s\n' "$paths" | bash "$RISK_CHECK" --register "$REGISTER" classes --paths - 2>&1)" || code=$?
  if [ "$code" -ne 0 ]; then
    echo "register could not be read (exit $code): $classes" >&2
    echo true
    return
  fi
  if [ -n "$classes" ]; then
    echo "architecture-sensitive classes: $(echo "$classes" | tr '\n' ' ')" >&2
    echo true
  else
    echo "no architecture-sensitive path" >&2
    echo false
  fi
}

decide() {
  local event="$1" base="$2" head="$3"
  if [ "$event" != "pull_request" ]; then
    echo "event $event runs every job" >&2
    echo "runtime=true"
    return
  fi
  # Both sides of a rename count: moving a file out of a sensitive path is a change to it.
  local paths
  paths="$(git diff --name-status -M "$base...$head" | awk -F '\t' '{ for (i = 2; i <= NF; i++) print $i }')"
  echo "runtime=$(printf '%s\n' "$paths" | runtime_for_paths)"
}

self_test() {
  local fails=0
  check() {
    local got; got="$(printf '%s\n' "$2" | runtime_for_paths 2>/dev/null)"
    if [ "$got" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (got $got)"; fails=$((fails + 1)); fi
  }
  check "a non-sensitive path skips the runtime job" "README.md" false
  check "the composition runs it" "compose.yaml" true
  check "a runtime test file alone runs it" "backend/tests/runtime/test_k01_startup.py" true
  check "a runtime test helper alone runs it" "backend/tests/support/repo.py" true
  check "a .gitignore runs it" ".gitignore" true
  check "a Dockerfile runs it" "backend/Dockerfile" true
  check "one sensitive path among others runs it" "$(printf 'README.md\nproxy/Caddyfile')" true
  check "no path skips it" "" false
  local got
  got="$(printf 'README.md\n' | RUNTIME_TRIGGER_REGISTER=/nonexistent runtime_for_paths 2>/dev/null)"
  REGISTER_SAVED="$REGISTER"; REGISTER=/nonexistent
  got="$(printf 'README.md\n' | runtime_for_paths 2>/dev/null)"; REGISTER="$REGISTER_SAVED"
  if [ "$got" = true ]; then echo "ok   an unreadable register runs it"; else echo "FAIL an unreadable register runs it"; fails=$((fails + 1)); fi
  got="$(decide push HEAD HEAD 2>/dev/null)"
  if [ "$got" = "runtime=true" ]; then echo "ok   a push runs it"; else echo "FAIL a push runs it"; fails=$((fails + 1)); fi
  [ "$fails" -eq 0 ] || { echo "ci-runtime-trigger: $fails self-test case(s) failed" >&2; return 1; }
}

case "${1:-}" in
  --self-test) self_test || exit 1 ;;
  --paths) [ "${2:-}" = "-" ] || usage; runtime_for_paths ;;
  decide) [ $# -eq 4 ] || usage; decide "$2" "$3" "$4" ;;
  *) usage ;;
esac
