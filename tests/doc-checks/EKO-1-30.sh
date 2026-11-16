#!/usr/bin/env bash
# EKO-1-30 (#152) K-04: the history is not re-pinned and release.yml is untouched by the task.
#
#   bash tests/doc-checks/EKO-1-30.sh                    # task branch (merge-base origin/main) vs working tree
#   bash tests/doc-checks/EKO-1-30.sh --head <ref>       # a commit (e.g. the PR head) instead of the working tree
#   bash tests/doc-checks/EKO-1-30.sh --base <ref> [...] # another base than origin/main
#   bash tests/doc-checks/EKO-1-30.sh --self-test        # planted failure states on a throwaway repo (M-6a/b/c)
#
# Checks: (1) the task branch's changed files exclude .github/workflows/release.yml — the
# prohibition's live-diff half, which no in-tree eko127 node may judge (pair guards read Git
# objects only and are live-tree-blind by design); (2) the record anchors are present in the
# post-task tree: #138's BASE/HEAD full SHAs and the recorded-bound assignment exactly as
# gate 1 of #152 froze them; (3) the 21 k02 + 8 k03 plant names and the 9 k01 shape names
# survive (K-04: every existing case keeps its name).
#
# Each check prints "ok   <name>" or "FAIL <name> -- <why>"; exit 0 = all passed, 1 = at least
# one failed, 2 = the script itself could not run (never read 2 as a pass). After the task is
# merged the default base makes check 1 inert: it prints "skip" with the re-run command and is
# not counted; checks 2-3 read the post-task tree and keep running. Re-run on a merged PR:
#   bash tests/doc-checks/EKO-1-30.sh --base <merge>^1 --head <merge>^2

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
HEAD_REF=""
SELF_TEST=""
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

RELEASE=".github/workflows/release.yml"
K01="backend/tests/static/test_eko127_k01_release_runtime_bound_is_the_recorded_value.py"
K02="backend/tests/static/test_eko127_k02_release_yml_changes_only_the_runtime_bound.py"
K03="backend/tests/static/test_eko127_k03_nothing_outside_the_bound_changes.py"
BASE_SHA="044e957891d5f1d256d1b9ae8e62d4f7e3f02061"
HEAD_SHA="bb5f8554aa7911a626d1f428d973df067a38faff"
RECORDED_BOUND_LINE_TEXT="RECORDED_BOUND = 360"

K02_PLANT_NAMES=(
  a-second-bound-line-in-another-job
  a-second-bound-line-in-the-runtime-job
  a-second-comment-line-above-the-bound
  a-step-level-timeout
  a-trailing-inline-comment-on-the-bound-line
  bound-moved-to-another-job
  bound-restored-to-60
  continue-on-error-beside-the-bound
  keys-reordered-in-the-runtime-job
  or-true-on-the-run-line
  publish-bound-retuned
  runtime-needs-changed
  runtime-permissions-widened
  the-concurrency-group-edited
  value-361
  value-boolean
  value-float
  value-negative
  value-quoted
  value-zero
  whitespace-only-in-another-job
)
K03_PLANT_NAMES=(
  a-runtime-test-added
  a-runtime-test-file-edited
  ci-runtime-checked-bound-retuned
  label-guard-workflow-changed
  runtime-conftest-changed
  support-helper-added
  support-helper-edited
  the-pyproject-changed
)
K01_SHAPE_NAMES=(
  above-the-platform-maximum
  boolean
  bound-plus-one
  float
  key-dropped
  negative
  quoted
  restored-to-60
  zero
)

die() { echo "EKO-1-30 doc-checks: $* — the checks did not run" >&2; exit 2; }

usage() { die "usage: $0 [--base <ref>] [--head <ref>] | --self-test"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || usage; BASE_REF="$2"; BASE_GIVEN=1; shift 2 ;;
    --head) [ $# -ge 2 ] || usage; HEAD_REF="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    *) die "unknown argument '$1'" ;;
  esac
done

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

# ---- self-test: planted failure states on a throwaway repository (M-6a/b/c) --------------------

self_test() {
  local root total=0 failures=0
  root="$(mktemp -d)" || { echo "self-test: cannot create a throwaway directory" >&2; return 2; }
  cd "$root" || return 2
  git init -q -b main repo || return 2
  cd repo || return 2
  git config user.name plant
  git config user.email plant@example.invalid
  git config commit.gpgsign false
  mkdir -p .github/workflows backend/tests/static tests/doc-checks
  printf 'jobs:\n  runtime:\n    timeout-minutes: 360\n' > "$RELEASE"
  {
    printf 'BASE = "%s"\n' "$BASE_SHA"
    printf 'HEAD = "%s"\n' "$HEAD_SHA"
    printf '%s\n' "$RECORDED_BOUND_LINE_TEXT"
    printf 'SHAPES = {\n'
    local name
    for name in "${K01_SHAPE_NAMES[@]}"; do printf '    "%s": ("x", "y"),\n' "$name"; done
    printf '}\n'
  } > "$K01"
  {
    printf 'PLANTS = {\n'
    for name in "${K02_PLANT_NAMES[@]}"; do printf '    "%s": (change, "fragment"),\n' "$name"; done
    printf '}\n'
  } > "$K02"
  {
    printf 'PLANTS = {\n'
    for name in "${K03_PLANT_NAMES[@]}"; do printf '    "%s": (change, "fragment"),\n' "$name"; done
    printf '}\n'
  } > "$K03"
  cp "$SELF" tests/doc-checks/EKO-1-30.sh
  git add -A
  git commit -qm base
  git update-ref refs/remotes/origin/main HEAD
  git checkout -qb task
  printf '# task edit\n' >> "$K01"
  git commit -qam task

  verdict() {
    local desc="$1" want="$2" frag="$3"
    shift 3
    local out rc
    out="$("$@" 2>&1)"
    rc=$?
    total=$((total + 1))
    if [ "$rc" -ne "$want" ] || { [ -n "$frag" ] && ! grep -qF -- "$frag" <<< "$out"; }; then
      echo "FAIL self-test: $desc — exit $rc (want $want), fragment '$frag' missing"
      sed 's/^/      /' <<< "$out" | head -n 25
      failures=$((failures + 1))
    else
      echo "ok   self-test: $desc"
    fi
  }

  verdict "clean task tree passes" 0 "" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task
  printf 'x\n' >> "$RELEASE"
  git commit -qam m6a
  verdict "M-6a a one-byte release.yml edit fails the changed-files check" 1 \
    "FAIL K-04 task-branch changed files exclude release.yml" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task
  git reset -q --hard HEAD~1
  sed -i "s/$BASE_SHA/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/" "$K01"
  git commit -qam m6b
  verdict "M-6b a moved record SHA fails the anchor check" 1 \
    "FAIL K-04 record anchors present in the post-task tree" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task
  git reset -q --hard HEAD~1
  sed -i 's/"value-361":/"value-999":/' "$K02"
  git commit -qam m6c
  verdict "M-6c a renamed k02 plant key fails the name check" 1 \
    "FAIL K-04 k02 plant names intact" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task
  git reset -q --hard HEAD~1
  sed -i "s/^$RECORDED_BOUND_LINE_TEXT\$/RECORDED_BOUND = 361/" "$K01"
  git commit -qam m6d
  verdict "a moved recorded-bound assignment fails the anchor check" 1 \
    "FAIL K-04 record anchors present in the post-task tree" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task
  git reset -q --hard HEAD~1

  verdict "clean task tree still passes after every planted state was reverted" 0 "" \
    bash tests/doc-checks/EKO-1-30.sh --base main --head task

  cd / || true
  rm -rf "$root"
  echo "EKO-1-30 self-test: $((total - failures)) of $total passed"
  [ "$failures" -eq 0 ]
}

if [ -n "$SELF_TEST" ]; then
  [ -z "$BASE_GIVEN$HEAD_REF" ] || die "--self-test takes no other argument"
  self_test
  exit $?
fi

# ---- the checks ---------------------------------------------------------------------------------

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || die "cannot enter the repository root"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git repository"
git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || die "base '$BASE_REF' is not a commit"
if [ -n "$HEAD_REF" ]; then
  git rev-parse --verify --quiet "$HEAD_REF^{commit}" >/dev/null || die "head '$HEAD_REF' is not a commit"
fi
MB="$(git merge-base "$BASE_REF" "${HEAD_REF:-HEAD}")" || die "no merge base of '$BASE_REF' and '${HEAD_REF:-HEAD}'"

post_task_text() { # <path> — the file as the post-task tree holds it
  if [ -n "$HEAD_REF" ]; then
    git show "$HEAD_REF:$1" 2>/dev/null
  else
    cat "$1" 2>/dev/null
  fi
}

changed_files() {
  if [ -n "$HEAD_REF" ]; then
    git diff --name-only --no-renames "$MB" "$HEAD_REF"
  else
    git diff --name-only --no-renames "$MB"
    git ls-files --others --exclude-standard
  fi
}

release_untouched() {
  local changed
  changed="$(changed_files | sort -u)"
  if [ -z "$changed" ]; then
    WHY="the change set against '$BASE_REF' ($MB) is empty; the comparison would prove nothing"
    return 1
  fi
  if grep -qx -- "$RELEASE" <<< "$changed"; then
    WHY="$RELEASE is changed by the task branch ($MB..${HEAD_REF:-worktree})"
    return 1
  fi
  return 0
}

record_anchors() {
  local text missing=""
  text="$(post_task_text "$K01")"
  [ -n "$text" ] || { WHY="cannot read $K01 in the post-task tree"; return 1; }
  grep -qE "^BASE = \"$BASE_SHA\"\r?$" <<< "$text" || missing="$missing BASE-SHA"
  grep -qE "^HEAD = \"$HEAD_SHA\"\r?$" <<< "$text" || missing="$missing HEAD-SHA"
  grep -qE "^$RECORDED_BOUND_LINE_TEXT\r?$" <<< "$text" || missing="$missing recorded-bound"
  [ -z "$missing" ] || { WHY="missing or moved in $K01:$missing"; return 1; }
  return 0
}

names_intact() { # <file> <names...>
  local file="$1" text missing=""
  shift
  text="$(post_task_text "$file")"
  [ -n "$text" ] || { WHY="cannot read $file in the post-task tree"; return 1; }
  local name
  for name in "$@"; do
    grep -qF "\"$name\":" <<< "$text" || missing="$missing $name"
  done
  [ -z "$missing" ] || { WHY="renamed or dropped in $file:$missing"; return 1; }
  return 0
}

k02_names() { names_intact "$K02" "${K02_PLANT_NAMES[@]}"; }
k03_names() { names_intact "$K03" "${K03_PLANT_NAMES[@]}"; }
k01_shapes() { names_intact "$K01" "${K01_SHAPE_NAMES[@]}"; }

if [ -z "$BASE_GIVEN" ] && [ -z "$(changed_files | head -n 1)" ]; then
  # merged: the default base makes the live-diff comparison inert (EKO-1-18 precedent)
  echo "skip K-04 task-branch changed files exclude release.yml — the change set is empty (task merged); re-run with --base <merge>^1 --head <merge>^2"
else
  check 'K-04 task-branch changed files exclude release.yml' release_untouched
fi
check 'K-04 record anchors present in the post-task tree' record_anchors
check 'K-04 k02 plant names intact (21)' k02_names
check 'K-04 k03 plant names intact (8)' k03_names
check 'K-04 k01 shape names intact (9)' k01_shapes

echo "EKO-1-30 doc-checks: $passed passed, $failed failed (tree: ${HEAD_REF:-working tree}; base: ${MB:0:7})"
[ "$failed" -eq 0 ]
