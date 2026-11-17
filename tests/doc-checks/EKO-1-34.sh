#!/usr/bin/env bash
# EKO-1-34 (#192) K-07: the PR head changes nothing outside the runtime test harness and the
# task's evidence, and the evidence holds no raw sensitive material.
#
#   bash tests/doc-checks/EKO-1-34.sh <base-sha> <head-sha>   judge base...head (full SHAs)
#   bash tests/doc-checks/EKO-1-34.sh --self-test              plants in a throwaway repository,
#                                                              each judged on two bases
#
# The base is the PR's merge base with main, recorded in the PR; the check never reads the live
# PR base, origin/main or the working tree. It judges the net difference `git diff base...head`
# (the merge base of the two, then head), so commits inside the branch do not count, and a base
# at a later main that already contains the PR gives an empty difference (inert after merge).
#
# Checks:
#   scope      no changed path matches a glob of docs/architecture/architecture-sensitive-paths.md
#              as it is AT THE BASE, nor backend/app/**, proxy/**, the register itself, the
#              Chromium pin files or backend/tests/support/release_*.py;
#              backend/tests/runtime/conftest.py is judged by the conftest check instead;
#   workflows  no file under .github/workflows/ differs from base at head (the transient probe
#              workflow may live inside the branch, never at its head);
#   conftest   conftest.py is unchanged, or the K-01 record at head names the `fresh` fixture as
#              the cause site and CHECKED_SERVICES, BUILT_SERVICES, checked_images_override and
#              Composition.base_args are byte-identical to base;
#   hygiene    no file under docs/evidence/EKO-1-34/ at head holds a cookie or set-cookie header,
#              an authorization code= or state= with a value, a `docker inspect` shape, or a
#              NAME=value of a variable the harness's env file defines (head's dev-env.sh run on
#              head's compose.yaml, plus make_env_file's own names). A value starting with `<`
#              (a redaction placeholder) is not a value. This check reads head's tree, so a
#              planted secret stays red after merge too.
#
# Each check prints "ok   <name>" or "FAIL <name> -- <why>". Exit 0 = all passed, 1 = at least one
# failed, 2 = the check itself could not run (never read 2 as a pass).
# EKO134_REPO overrides the repository the checks read (the self-test points it at its fixture).

set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REAL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || {
  echo "EKO-1-34 doc-checks: cannot enter the repository root" >&2
  exit 2
}
REPO="${EKO134_REPO:-$REAL_REPO}"

REGISTER="docs/architecture/architecture-sensitive-paths.md"
EVIDENCE="docs/evidence/EKO-1-34"
CONFTEST="backend/tests/runtime/conftest.py"
WORKFLOWS=".github/workflows/"
EXTRA_GLOBS=(
  'backend/app/**'
  'proxy/**'
  "$REGISTER"
  'backend/tests/support/chromium_archives.json'
  'backend/tests/support/chromium.py'
  'backend/tests/support/release_*.py'
)
MAKE_ENV_NAMES="COMPOSE_PROJECT_NAME BACKEND_IMAGE_TAG PROXY_HTTP_PORT PROXY_HTTPS_PORT PROXY_ADMIN_PORT"
CAUSE_SITE='cause site is the `fresh` fixture'
COOKIE_RE='(^|[^[:alnum:]_-])(set-)?cookie[[:space:]]*:'
AUTH_PARAMETER_RE='(^|[^[:alnum:]_])(code|state)=[^[:space:]<&"'"'"'`|,;)]'
INSPECT_RE='"Env"[[:space:]]*:[[:space:]]*\[|"NetworkSettings"'

g() { git -C "$REPO" "$@"; }

die() {
  echo "EKO-1-34 doc-checks: $*" >&2
  exit 2
}

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

# The register's globs at a commit: the first cell of each table row, in backticks.
register_globs() {
  g show "$1:$REGISTER" 2> /dev/null | tr -d '\r' | awk '
    /^\|/ {
      split($0, cell, "|"); glob = cell[2]
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", glob)
      if (glob ~ /^`[^`]+`$/ && glob !~ /</) print substr(glob, 2, length(glob) - 2)
    }'
}

# The guarded list: the register at the base, then the task's own additions.
guarded_globs() {
  register_globs "$1"
  printf '%s\n' "${EXTRA_GLOBS[@]}"
}

# The glob a path matches, if any. In a case pattern `*` already crosses `/`, as in risk-check.sh.
guarded_by() {
  local path="$1" glob
  while IFS= read -r glob; do
    # shellcheck disable=SC2254
    case "$path" in ${glob//\*\*/*})
      printf '%s\n' "$glob"
      return 0
      ;;
    esac
  done < "$GLOBS"
  return 1
}

changed_paths() { g diff --name-only --no-renames "$BASE...$HEAD"; }

scope_unchanged() {
  local path glob hits=""
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    [ "$path" != "$CONFTEST" ] || continue
    if glob="$(guarded_by "$path")"; then
      hits+="$path ($glob); "
    fi
  done < "$CHANGED"
  [ -z "$hits" ] || {
    WHY="${hits%; }"
    return 1
  }
}

workflows_unchanged() {
  local hits
  hits="$(grep -F "$WORKFLOWS" "$CHANGED" | grep -c '^'"$WORKFLOWS")"
  [ "$hits" -eq 0 ] || {
    WHY="$(grep '^'"$WORKFLOWS" "$CHANGED" | tr '\n' ' ')differ from base at head"
    return 1
  }
}

# A top-level statement or a method, with the decorators right above it: $1 = indent, $2 = the
# start of its first line after the indent (an ERE). Prints nothing when it is not found once.
block() {
  tr -d '\r' | awk -v ind="$1" -v start="$2" '
    function lead(s) { match(s, /^ */); return RLENGTH }
    { line[NR] = $0 }
    END {
      n = length(ind); found = 0
      for (i = 1; i <= NR; i++)
        if (lead(line[i]) == n && substr(line[i], n + 1) ~ ("^" start)) { found++; s = i }
      if (found != 1) exit 3
      b = s
      while (b > 1 && lead(line[b - 1]) == n && substr(line[b - 1], n + 1) ~ /^@/) b--
      e = s
      for (i = s + 1; i <= NR; i++) {
        if (line[i] ~ /^[[:space:]]*$/) continue
        if (lead(line[i]) > n || (lead(line[i]) == n && substr(line[i], n + 1) ~ /^[]})]/)) {
          e = i
          continue
        }
        break
      }
      for (i = b; i <= e; i++) print line[i]
    }'
}

OVERRIDE_BLOCKS=(
  '|CHECKED_SERVICES = '
  '|BUILT_SERVICES = '
  '|def checked_images_override[(]'
  '    |def base_args[(]'
)

override_lines_identical() {
  local entry indent start at_base at_head
  for entry in "${OVERRIDE_BLOCKS[@]}"; do
    indent="${entry%%|*}"
    start="${entry#*|}"
    at_base="$(g show "$BASE:$CONFTEST" | block "$indent" "$start")" || at_base=""
    at_head="$(g show "$HEAD:$CONFTEST" 2> /dev/null | block "$indent" "$start")" || at_head=""
    if [ -z "$at_base" ] || [ -z "$at_head" ]; then
      WHY="conftest.py: '$start' not found exactly once at base and at head"
      return 1
    fi
    [ "$at_base" = "$at_head" ] || {
      WHY="conftest.py: the block starting '$start' differs from base"
      return 1
    }
  done
}

record_names_the_cause_site() {
  local path
  while IFS= read -r path; do
    case "$path" in *.md) ;; *) continue ;; esac
    if g show "$HEAD:$path" | grep -qF -- "$CAUSE_SITE"; then
      return 0
    fi
  done < <(g ls-tree -r --name-only "$HEAD" -- "$EVIDENCE/")
  return 1
}

conftest_allowed() {
  grep -qxF "$CONFTEST" "$CHANGED" || return 0
  record_names_the_cause_site || {
    WHY="conftest.py changed, and no record in $EVIDENCE/ at head names the \`fresh\` fixture as the cause site"
    return 1
  }
  override_lines_identical
}

# The names the harness's env file defines, from head's own dev-env.sh and compose.yaml.
env_names() {
  local work="$1"
  mkdir -p "$work/scripts"
  g show "$HEAD:scripts/dev-env.sh" > "$work/scripts/dev-env.sh" 2> /dev/null || return 1
  g show "$HEAD:compose.yaml" > "$work/compose.yaml" 2> /dev/null || return 1
  COMPOSE_FILE_PATH="$work/compose.yaml" bash "$work/scripts/dev-env.sh" "$work/synthetic.env" \
    > /dev/null 2>&1 || return 1
  {
    cut -d= -f1 "$work/synthetic.env"
    printf '%s\n' $MAKE_ENV_NAMES
  } | grep -E '^[A-Z][A-Z0-9_]*$' | sort -u
}

evidence_clean() {
  local path content hits="" count=0
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    count=$((count + 1))
    content="$(g show "$HEAD:$path" | tr -d '\r')"
    grep -qiE -- "$COOKIE_RE" <<< "$content" && hits+="$path: cookie header; "
    grep -qiE -- "$AUTH_PARAMETER_RE" <<< "$content" && hits+="$path: code= or state= with a value; "
    grep -qE -- "$INSPECT_RE" <<< "$content" && hits+="$path: docker inspect shape; "
    grep -qE -- "$ENV_RE" <<< "$content" && hits+="$path: env-file NAME=value; "
  done < <(g ls-tree -r --name-only "$HEAD" -- "$EVIDENCE/")
  [ "$count" -gt 0 ] || {
    WHY="no file under $EVIDENCE/ at head: nothing to judge"
    return 1
  }
  [ -z "$hits" ] || {
    WHY="${hits%; }"
    return 1
  }
}

run_checks() {
  BASE="$1"
  HEAD="$2"
  local sha
  for sha in "$BASE" "$HEAD"; do
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "'$sha' is not a full 40-character SHA"
    g cat-file -e "$sha^{commit}" 2> /dev/null || die "$sha is not a commit of $REPO"
  done
  WORK="$(mktemp -d)" || die "cannot create a work directory"
  trap 'rm -rf "$WORK"' EXIT
  GLOBS="$WORK/globs"
  CHANGED="$WORK/changed"
  register_globs "$BASE" > "$WORK/register"
  [ -s "$WORK/register" ] || die "no glob read from $REGISTER at $BASE"
  guarded_globs "$BASE" > "$GLOBS"
  changed_paths > "$CHANGED" || die "git diff $BASE...$HEAD failed"
  local names
  names="$(env_names "$WORK/env")" || die "cannot list the env file's names from head"
  [ -n "$names" ] || die "the env file at head defines no name"
  ENV_RE="(^|[^[:alnum:]_])($(tr '\n' '|' <<< "$names" | sed 's/|$//'))=[^[:space:]<]"

  check 'K-07 scope: no guarded path differs from base at head' scope_unchanged
  check 'K-07 workflows: no file under .github/workflows/ differs from base at head' \
    workflows_unchanged
  check 'K-07 conftest.py: unchanged, or allowed by name with its override lines intact' \
    conftest_allowed
  check "K-07 hygiene: $EVIDENCE/ at head holds no raw sensitive material" evidence_clean
  echo "EKO-1-34 doc-checks: $passed passed, $failed failed"
  [ "$failed" -eq 0 ]
}

# Self-test -----------------------------------------------------------------------------------

SCOPE='K-07 scope: no guarded path differs from base at head'
FLOWS='K-07 workflows: no file under .github/workflows/ differs from base at head'
CONF='K-07 conftest.py: unchanged, or allowed by name with its override lines intact'
HYG="K-07 hygiene: $EVIDENCE/ at head holds no raw sensitive material"

# $1 = label, $2 = base, $3 = head, then the names of the checks expected red ("" = all green).
# WHY_WANTED, when set, must appear in the output: the red is for the planted reason.
expect() {
  local label="$1" base="$2" head="$3" out status want got
  shift 3
  out="$(EKO134_REPO="$FIX" bash "$SELF" "$base" "$head" 2>&1)"
  status=$?
  if [ -n "${WHY_WANTED:-}" ] && ! grep -qF -- "$WHY_WANTED" <<< "$out"; then
    echo "self-test FAIL $label: the output does not say '$WHY_WANTED':"
    echo "$out"
    return 1
  fi
  want="$(printf '%s\n' "$@" | sed '/^$/d' | sort)"
  got="$(sed -n 's/^FAIL \(.*\) -- .*/\1/p' <<< "$out" | sort)"
  if [ "$status" -ne 2 ] && [ "$want" = "$got" ] && { [ -n "$want" ] || [ "$status" -eq 0 ]; } \
    && { [ -z "$want" ] || [ "$status" -eq 1 ]; }; then
    echo "self-test ok   $label: ${want:+red on }$(tr '\n' ',' <<< "${want:-green}" | sed 's/,$//')"
    return 0
  fi
  echo "self-test FAIL $label: expected ${want:-green}, got (exit $status):"
  echo "$out"
  return 1
}

expect_exit_2() {
  local label="$1" out status
  shift
  out="$(EKO134_REPO="$FIX" bash "$SELF" "$@" 2>&1)"
  status=$?
  if [ "$status" -eq 2 ]; then
    echo "self-test ok   $label: the check could not run (exit 2)"
    return 0
  fi
  echo "self-test FAIL $label: expected exit 2, got $status:"
  echo "$out"
  return 1
}

f() { git -C "$FIX" "$@"; }

commit_all() {
  f add -A > /dev/null && f commit -qm "$1" > /dev/null
  f rev-parse HEAD
}

# A branch from the change under test with one more commit made by "$@" (run in the fixture).
plant() {
  local name="$1"
  shift
  f checkout -q -b "$name" "$PR" || return 1
  (cd "$FIX" && "$@") || return 1
  commit_all "plant $name"
}

# A later main that merged $1, plus one unrelated commit.
later_main() {
  f checkout -q -b "main-after-$2" "$BASE_SHA" || return 1
  f merge -q --no-ff -m "merge $2" "$1" > /dev/null || return 1
  printf 'after\n' > "$FIX/docs/after-$2.md"
  commit_all "after $2"
}

append() { printf '%s\n' "$2" >> "$1"; }

self_test() {
  local bad=0 sha later sample
  FIX="$(mktemp -d)" || return 2
  trap 'rm -rf "$FIX"' EXIT
  git init -q -b main "$FIX" || return 2
  f config core.autocrlf false
  f config user.email eko134@example.invalid
  f config user.name eko134-self-test
  local tracked
  for tracked in "$REGISTER" compose.yaml scripts/keycloak-bootstrap.sh scripts/dev-env.sh \
    backend/tests/support/chromium_archives.json "$CONFTEST" \
    backend/tests/runtime/test_k06_frontend_replacement.py; do
    mkdir -p "$FIX/$(dirname "$tracked")"
    git -C "$REAL_REPO" show "HEAD:$tracked" > "$FIX/$tracked" || {
      echo "self-test FAIL cannot copy $tracked"
      return 1
    }
  done
  mkdir -p "$FIX/docs"
  BASE_SHA="$(commit_all base)"

  # The change under test: a harness file and the evidence directory as it is in the worktree.
  f checkout -q -b pr
  append "$FIX/backend/tests/runtime/test_k06_frontend_replacement.py" '# harness change'
  mkdir -p "$FIX/$EVIDENCE"
  for sample in "$REAL_REPO/$EVIDENCE"/*; do
    [ -f "$sample" ] && tr -d '\r' < "$sample" > "$FIX/$EVIDENCE/$(basename "$sample")"
  done
  [ -n "$(ls "$FIX/$EVIDENCE")" ] || {
    echo "self-test FAIL no evidence file to copy from $EVIDENCE/"
    return 1
  }
  PR="$(commit_all 'change under test')"

  expect 'the change under test, at its merge base' "$BASE_SHA" "$PR" || bad=1
  later="$(later_main "$PR" pr)"
  expect 'the change under test, at a later main that merged it (inert)' "$later" "$PR" || bad=1

  # Plants: each red at the merge base, and green at a later main that merged it.
  local -a cases=(
    "compose|$SCOPE|compose.yaml (*compose*.y*ml)|append compose.yaml '# planted'"
    "bootstrap|$SCOPE|scripts/keycloak-bootstrap.sh (scripts/**)|sed -i '0,/^compose restart proxy/s//compose restart proxy --timeout 1/' scripts/keycloak-bootstrap.sh"
    "chromium-pin|$SCOPE|chromium_archives.json (backend/tests/support/chromium_archives.json)|sed -i 's/\"chromiumRevision\": \"[0-9]*\"/\"chromiumRevision\": \"1\"/' backend/tests/support/chromium_archives.json"
    "app|$SCOPE|backend/app/planted.py (backend/app/**)|mkdir -p backend/app && append backend/app/planted.py '# planted'"
    "proxy|$SCOPE|proxy/Caddyfile (|mkdir -p proxy && append proxy/Caddyfile '# planted'"
    "register|$SCOPE|$REGISTER ($REGISTER)|append $REGISTER '| \`planted/**\` | pipeline | - | planted |'"
    "conftest-unnamed|$CONF|names the \`fresh\` fixture as the cause site|append $CONFTEST '# planted' && sed -i '/cause site is the/d' $EVIDENCE/*.md"
    "conftest-override|$CONF|'def checked_images_override[(]' differs from base|sed -i 's/    pull_policy: never\"\]/    pull_policy: missing\"]/' $CONFTEST"
    "conftest-checked|$CONF|'CHECKED_SERVICES = ' differs from base|sed -i 's/^    \"proxy\": \"proxy\",/    \"proxy\": \"frontend\",/' $CONFTEST"
    "conftest-built|$CONF|'BUILT_SERVICES = ' differs from base|sed -i 's/^BUILT_SERVICES = (\"proxy\", /BUILT_SERVICES = (/' $CONFTEST"
    "conftest-base-args|$CONF|'def base_args[(]' differs from base|sed -i 's/\"--profile\", \"dev\"\]/\"--profile\", \"test\"]/' $CONFTEST"
  )
  local entry name want why action head
  for entry in "${cases[@]}"; do
    IFS='|' read -r name want why action <<< "$entry"
    head="$(plant "$name" bash -c "$(declare -f append); $action")" || {
      echo "self-test FAIL cannot plant $name"
      bad=1
      continue
    }
    if f diff --quiet "$PR" "$head"; then
      echo "self-test FAIL plant $name changed nothing"
      bad=1
      continue
    fi
    WHY_WANTED="$why" expect "plant $name, at its merge base" "$BASE_SHA" "$head" "$want" || bad=1
    later="$(later_main "$head" "$name")"
    expect "plant $name, at a later main that merged it (inert)" "$later" "$head" || bad=1
  done

  # The workflow left at head: added in one commit, followed by a commit touching another file,
  # so a check judging only the last commit would read it green.
  f checkout -q -b workflow-left "$PR"
  mkdir -p "$FIX/.github/workflows" && printf 'name: probe\n' > "$FIX/.github/workflows/eko134-probe.yml"
  commit_all 'probe workflow' > /dev/null
  append "$FIX/backend/tests/runtime/test_k06_frontend_replacement.py" '# a later harness commit'
  head="$(commit_all 'later harness commit')"
  expect 'plant a workflow left at head, at its merge base' "$BASE_SHA" "$head" "$SCOPE" "$FLOWS" \
    || bad=1
  # The exception: the workflow lived inside the branch and is gone at head.
  f rm -q .github/workflows/eko134-probe.yml
  head="$(commit_all 'probe workflow removed')"
  expect 'a workflow added and removed inside the branch' "$BASE_SHA" "$head" || bad=1

  # conftest.py allowed by name: a line outside the override blocks, the record naming `fresh`.
  head="$(plant conftest-named sed -i 's/^    """A separate composition for a scenario/    """EKO-1-34: a separate composition for a scenario/' "$CONFTEST")"
  if f diff --quiet "$PR" "$head" -- "$CONFTEST"; then
    echo "self-test FAIL plant conftest-named changed nothing"
    bad=1
  else
    expect 'conftest.py changed outside the override lines, record names fresh' "$BASE_SHA" "$head" \
      || bad=1
  fi

  # Evidence hygiene: red at head whatever the base (it reads head's tree), green for placeholders.
  # The secret-named variable is spelled in two parts, so this file assigns no secret itself.
  local -a dirty=(
    'Cookie: __Host-eko_session=0123456789abcdef'
    'set-cookie: __Host-eko_login=0123; Secure'
    'https://auth.localhost/realms/eko/callback?code=8f1c2d3e&iss=x'
    'GET /api/auth/callback?state=ab12cd34'
    '    "Env": ['
    '  "NetworkSettings": {'
    "$(printf '%s_%s' KC_BOOTSTRAP_ADMIN PASSWORD)=synthetic-0123abcd"
    'the run used PROXY_HTTPS_PORT=8443 here'
  )
  local line number=0
  for line in "${dirty[@]}"; do
    number=$((number + 1))
    head="$(plant "dirty-$number" bash -c "printf '%s\n' '$line' > $EVIDENCE/planted.md")" || {
      echo "self-test FAIL cannot plant dirty-$number"
      bad=1
      continue
    }
    expect "evidence plant '$line', at its merge base" "$BASE_SHA" "$head" "$HYG" || bad=1
    later="$(later_main "$head" "dirty-$number")"
    expect "evidence plant '$line', at a later main (head's tree)" "$later" "$head" "$HYG" || bad=1
  done
  local -a placeholders=(
    'code=<redacted> state=<redacted>'
    'the exit code was 1; the state is settled; a cookie jar'
    'ImageOS=ubuntu26 and head_sha=0496115'
    'env-file `NAME=value` lines are withheld'
  )
  number=0
  for line in "${placeholders[@]}"; do
    number=$((number + 1))
    head="$(plant "placeholder-$number" bash -c "printf '%s\n' '$line' > $EVIDENCE/planted.md")"
    expect "evidence placeholder '$line'" "$BASE_SHA" "$head" || bad=1
  done

  # Every path K-07 names is guarded, read from the fixture's register at the base.
  WORK="$(mktemp -d)"
  GLOBS="$WORK/globs"
  REPO="$FIX"
  guarded_globs "$BASE_SHA" > "$GLOBS"
  for sample in frontend/src/main.tsx frontend/vite.config.ts frontend/index.html \
    frontend/public/favicon.svg frontend/package.json frontend/pnpm-lock.yaml \
    backend/pyproject.toml backend/uv.lock compose.yaml proxy/Caddyfile frontend/Caddyfile \
    proxy/Dockerfile backend/Dockerfile .dockerignore backend/.env.example identity/realm.json \
    backup/eko-backup backend/migrations/versions/x.py scripts/keycloak-bootstrap.sh \
    backend/tests/support/release_mode_ci.py backend/tests/support/workflow_checks.py \
    .githooks/pre-push agents/qa.md .claude/settings.json .github/workflows/ci.yml \
    backend/app/main.py proxy/entrypoint.sh "$REGISTER" \
    backend/tests/support/chromium_archives.json backend/tests/support/chromium.py; do
    if guarded_by "$sample" > /dev/null; then
      echo "self-test ok   $sample is guarded"
    else
      echo "self-test FAIL $sample is not guarded"
      bad=1
    fi
  done
  for sample in backend/tests/runtime/test_eko134_k02_network_change_during_login.py \
    backend/tests/runtime/eko134_host_network.py backend/tests/unit/test_eko134_host_network.py \
    backend/tests/support/eko134_probe_timing.py tests/doc-checks/EKO-1-34.sh \
    "$EVIDENCE/pre-fix-probe-2026-11-17.md" docs/PLAN.md; do
    if guarded_by "$sample" > /dev/null; then
      echo "self-test FAIL $sample is guarded"
      bad=1
    else
      echo "self-test ok   $sample is not guarded"
    fi
  done
  rm -rf "$WORK"

  # A check that cannot run is never a pass.
  expect_exit_2 'an abbreviated base' "${BASE_SHA:0:12}" "$PR" || bad=1
  expect_exit_2 'a head that is not a commit' "$BASE_SHA" "$(printf '%040d' 0)" || bad=1
  expect_exit_2 'no arguments' || bad=1
  f checkout -q -b no-register "$BASE_SHA"
  f rm -q "$REGISTER"
  sha="$(commit_all 'register removed')"
  expect_exit_2 'a base without the register' "$sha" "$PR" || bad=1

  if [ "$bad" -eq 0 ]; then
    echo "EKO-1-34 doc-checks self-test: all cases behaved"
  else
    echo "EKO-1-34 doc-checks self-test: FAILED"
  fi
  return "$bad"
}

case "${1:-}" in
  --self-test)
    self_test
    exit $?
    ;;
  "") die "usage: $0 <base-sha> <head-sha> | --self-test" ;;
esac
[ $# -eq 2 ] || die "usage: $0 <base-sha> <head-sha> | --self-test"
run_checks "$1" "$2"
