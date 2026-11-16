#!/usr/bin/env bash
# EKO-1-33 K-05(c): no rerun or flaky mechanism masks the EKO-2-01 runtime carriers. Fails when
# a pytest rerun plugin or option, a flaky marker or decorator, or a CI re-run step appears in
# backend/pyproject.toml, backend/tests/ or .github/workflows/ci.yml.
#
#   bash tests/doc-checks/EKO-1-33.sh              check the working tree
#   bash tests/doc-checks/EKO-1-33.sh --self-test  plant each pattern in a copy of the tracked
#                                                  files and show the matching check red
#
# EKO133_ROOT overrides the tree the checks read (the self-test points it at its copy).
# "rerun" alone is not a pattern: the bootstrap tests use it for the existing-volume path.

set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || {
  echo "EKO-1-33 doc-checks: cannot enter repository root" >&2
  exit 2
}
ROOT="${EKO133_ROOT:-$REPO}"

# pytest-rerunfailures (plugin, `--reruns`, `reruns =`, `--only-rerun`), the `flaky` package,
# pytest-retry (`--retries`, `retries =`), and a rerun of the last failures (`--lf`).
PYPROJECT_PATTERN='rerunfailures|--reruns|(^|[^a-z_])reruns[[:space:]]*=|--only-rerun|(^|[^a-z_-])flaky([^a-z_]|$)|pytest-retry|--retries|(^|[^a-z_])retries[[:space:]]*=|--lf([^a-z-]|$)|--last-failed'
# In tests: the markers and decorators of those plugins, their imports and plugin registration.
TESTS_PATTERN='mark\.flaky|@flaky|(from|import)[[:space:]]+flaky|rerunfailures|--reruns|(^|[^a-z_])reruns[[:space:]]*=|mark\.retry|pytest_retry|--lf([^a-z-]|$)|--last-failed'
# In CI: the same pytest options, a retry action, a re-run of the workflow, and a second pytest
# started when the first one failed.
CI_PATTERN='rerunfailures|--reruns|(^|[^a-z_-])flaky([^a-z_]|$)|--lf([^a-z-]|$)|--last-failed|gh[[:space:]]+run[[:space:]]+re-?run|actions/runs/[^[:space:]]*/rerun|/retry@|wretry|retry-action|max_attempts|retry_on|\|\|[[:space:]]*(uv[[:space:]]+run[[:space:]]+)?(python[[:space:]]+-m[[:space:]]+)?pytest'

passed=0
failed=0
WHY=""

check() {
  local name="$1"
  shift
  WHY=""
  if "$@"; then
    echo "ok   $name"
    passed=$((passed + 1))
  else
    echo "FAIL $name -- ${WHY:-check failed}"
    failed=$((failed + 1))
  fi
}

# The file must exist, so a moved or renamed target cannot pass by being absent.
no_match_in_file() {
  local file="$ROOT/$1" pattern="$2" hits
  [ -s "$file" ] || {
    WHY="missing or empty $1"
    return 1
  }
  hits="$(grep -nE -- "$pattern" "$file")"
  [ -z "$hits" ] || {
    WHY="$1: $(echo "$hits" | head -3 | tr '\n' ' ')"
    return 1
  }
}

no_match_in_tests() {
  local dir="$ROOT/backend/tests" hits count
  [ -d "$dir" ] || {
    WHY="missing backend/tests"
    return 1
  }
  count="$(find "$dir" -name '*.py' -not -path '*/__pycache__/*' | wc -l | tr -d ' ')"
  [ "$count" -gt 0 ] || {
    WHY="no Python files under backend/tests"
    return 1
  }
  hits="$(grep -rnIE --exclude-dir=__pycache__ --exclude-dir=.pytest_cache -- "$TESTS_PATTERN" "$dir")"
  [ -z "$hits" ] || {
    WHY="$(echo "$hits" | head -3 | sed "s|$ROOT/||" | tr '\n' ' ')"
    return 1
  }
}

run_checks() {
  check 'K-05(c) no rerun or flaky mechanism in backend/pyproject.toml' \
    no_match_in_file backend/pyproject.toml "$PYPROJECT_PATTERN"
  check 'K-05(c) no rerun or flaky mechanism in backend/tests' no_match_in_tests
  check 'K-05(c) no re-run step in .github/workflows/ci.yml' \
    no_match_in_file .github/workflows/ci.yml "$CI_PATTERN"
  echo "EKO-1-33 doc-checks: $passed passed, $failed failed"
  [ "$failed" -eq 0 ]
}

# Self-test -----------------------------------------------------------------------------------

# Runs the script against the copy; $1 is the expected outcome ("pass" or the failing check).
expect() {
  local want="$1" label="$2" out status
  out="$(EKO133_ROOT="$COPY" bash "$SELF" 2>&1)"
  status=$?
  if [ "$want" = pass ]; then
    if [ "$status" -eq 0 ]; then
      echo "self-test ok   $label: green"
      return 0
    fi
    echo "self-test FAIL $label: expected green, got:"
    echo "$out"
    return 1
  fi
  if [ "$status" -ne 0 ] && echo "$out" | grep -qF "FAIL $want --" \
    && [ "$(echo "$out" | grep -c '^FAIL ')" -eq 1 ]; then
    echo "self-test ok   $label: red on '$want'"
    return 0
  fi
  echo "self-test FAIL $label: expected only '$want' red, got (exit $status):"
  echo "$out"
  return 1
}

# Appends a line to a file of the copy, runs the expectation, restores the file.
plant() {
  local file="$COPY/$1" line="$2" want="$3" result
  cp "$file" "$file.orig"
  printf '%s\n' "$line" >> "$file"
  expect "$want" "plant '$line' in $1"
  result=$?
  mv "$file.orig" "$file"
  return "$result"
}

# Creates a test file in the copy, runs the expectation ($2, default: the tests check red),
# deletes it.
plant_test() {
  local line="$1" want="${2:-K-05(c) no rerun or flaky mechanism in backend/tests}" result
  local file="$COPY/backend/tests/test_eko133_selftest_planted.py"
  printf 'import pytest\n\n%s\ndef test_planted() -> None:\n    pass\n' "$line" > "$file"
  expect "$want" "plant '$line' in backend/tests"
  result=$?
  rm -f "$file"
  return "$result"
}

self_test() {
  local bad=0 t
  COPY="$(mktemp -d)"
  trap 'rm -rf "$COPY"' EXIT
  (cd "$REPO" && git ls-files -z -- backend/pyproject.toml backend/tests .github/workflows/ci.yml \
    | tar --null -T - -cf - | tar -xf - -C "$COPY") || {
    echo "self-test FAIL cannot copy the tracked files"
    return 1
  }
  expect pass "tracked tree, unchanged" || bad=1
  # The word the bootstrap tests use is not a mechanism.
  plant backend/pyproject.toml '# the existing-volume rerun path' pass || bad=1
  plant .github/workflows/ci.yml '      # rerun of the bootstrap on the existing volume' pass || bad=1
  plant_test '# a rerun of the bootstrap; retry the cheap alternatives' pass || bad=1
  local py='K-05(c) no rerun or flaky mechanism in backend/pyproject.toml'
  for t in '"pytest-rerunfailures>=14.0",' 'addopts = "-m not runtime --reruns 2"' \
    'reruns = 3' '"flaky>=3.8",' '"pytest-retry>=1.6",' 'retries = 2' \
    'addopts = "--lf"'; do
    plant backend/pyproject.toml "$t" "$py" || bad=1
  done
  local ts='K-05(c) no rerun or flaky mechanism in backend/tests'
  for t in '@pytest.mark.flaky(reruns=3)' '@pytest.mark.flaky' 'from flaky import flaky' \
    'import flaky' '@flaky(max_runs=3)' 'pytest_plugins = ["pytest_rerunfailures"]' \
    '@pytest.mark.retry(2)' 'import pytest_retry'; do
    plant_test "$t" || bad=1
  done
  local ci='K-05(c) no re-run step in .github/workflows/ci.yml'
  for t in '        run: uv run pytest -m runtime --reruns 2' \
    '        run: uv run pytest -m runtime || uv run pytest -m runtime --lf' \
    '        run: uv run pytest -m runtime || pytest -m runtime' \
    '        uses: nick-fields/retry@v3' '          max_attempts: 3' \
    '        run: gh run rerun "$GITHUB_RUN_ID" --failed' \
    '        uses: Wandalen/wretry.action@v3' \
    '        run: uv run pip install pytest-rerunfailures' \
    '        run: uv run pytest -p flaky'; do
    plant .github/workflows/ci.yml "$t" "$ci" || bad=1
  done
  # A target that vanishes cannot pass by being absent.
  mv "$COPY/.github/workflows/ci.yml" "$COPY/ci.yml.away"
  expect "$ci" "ci.yml removed" || bad=1
  mv "$COPY/ci.yml.away" "$COPY/.github/workflows/ci.yml"
  if [ "$bad" -eq 0 ]; then
    echo "EKO-1-33 doc-checks self-test: all cases behaved"
  else
    echo "EKO-1-33 doc-checks self-test: FAILED"
  fi
  return "$bad"
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi
run_checks
