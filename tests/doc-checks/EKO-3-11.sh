#!/usr/bin/env bash
# EKO-3-11 — proves K-05 of Issue #266: the task adds new tests and changes no backend file and no
# existing test; a production file changes only as the minimal fix of a defect a new test showed
# red (the red run recorded in the PR description); scripts/weakening-check.sh finds nothing.
#
#   bash tests/doc-checks/EKO-3-11.sh --pr <pr-body.md>                  # BASE...CHECKPOINT
#   bash tests/doc-checks/EKO-3-11.sh --pr <pr-body.md> --head <rev>     # BASE...<rev>, e.g. the PR head
#   bash tests/doc-checks/EKO-3-11.sh --pr <pr-body.md> --head <rev> --base origin/main
#                                                                        # after main was merged in
#   bash tests/doc-checks/EKO-3-11.sh --self-test                        # built-in contrasts, offline
#
#   gh pr view <n> --json body --jq .body > pr-body.md                   # the body the run expects
#
# The range. Without --base it starts at the pinned BASE, and a range holding a merge commit is
# refused (exit 2): after "Merge main into the branch" BASE...HEAD would attribute main's files to
# the task. With --base <rev> it starts at M = git merge-base <rev> <head>, the last main commit
# merged in when <rev> is origin/main (run `git fetch origin main` first). M is accepted only when
# BASE is an ancestor of M, M is an ancestor of refs/remotes/origin/main, and the checkpoint is
# not an ancestor of M. So --base can only move the start along main's own history: the diff
# M...HEAD is the head tree against a main tree, and a task change - including one made while
# resolving the merge - disappears from it only if main itself already holds it. A base on the
# branch, the head itself, or a commit main never had is refused. The one thing trusted is the
# local origin/main ref.
#
# Git configuration. Every git call reading the range runs with the user's diff-shaping
# configuration overridden through GIT_CONFIG_COUNT (command scope, above the system, global and
# repository files; GIT_CONFIG_PARAMETERS, GIT_EXTERNAL_DIFF and GIT_DIFF_OPTS are unset), and the
# diff calls also pass --no-color --no-ext-diff --no-textconv and fixed prefixes and algorithm.
# The weakening check inherits the same environment. An M of a production file whose diff yields
# no parsed hunk fails closed, and so does a line opening "@@" that does not parse.
#
# Output. One line per sub-check, "ok   <name> — <detail>" or "FAIL <name> — <why>".
# Exit codes: 0 = every sub-check passed, 1 = at least one failed, 2 = the check could not run (a
# bad argument, a missing body, a pinned SHA not in this repository's history) — never read 2 as a
# pass.
#
# The sub-checks (K-05 Observable):
#   paths       every entry of `git diff --name-status -M BASE...HEAD` is one of: an A under
#               frontend/tests/; A tests/doc-checks/EKO-3-11.sh; an M of exactly
#               frontend/src/features/customers/CustomerDetail.tsx or CustomerList.tsx; or the
#               pre-authorized bookkeeping K-05 does not name (assumption, stated for gate 2): an A
#               of docs/cost-register/<YYYY-MM-DD>_EKO-3-11_<name>.json, and an M of docs/PLAN.md
#               whose diff only adds lines, in one hunk, opening with the "- [ ] **EKO-3-11**" entry
#               line and holding no other entry line (continuation lines indented, or blank).
#               Anything else fails: backend/, any A/D/R under frontend/src/, any M/D/R under
#               frontend/tests/, any package, lock or config file, a cost row of another task.
#   mechanism   every -U0 hunk of an M of CustomerDetail.tsx lies inside the body of `change`
#               (strictly between `const change = async (which: Change) => {` and its `  };`), and
#               of CustomerList.tsx inside the body of `function chooseState` (up to its `  }`),
#               on the base side at the range start's line numbers and on the head side at HEAD's.
#               An M with no parsed hunk (a mode-only change, or a diff git printed differently)
#               fails closed.
#   red-run     every M entry has a red-run record in the PR body, and every record stands for an
#               M entry. A record is one line
#                 - Red run — K-0n — <frontend/tests/...test.tsx>::<test name> — failed on: <assertion>
#               whose test file is an A entry of the range under frontend/tests/ ending .test.tsx
#               and declares the test at HEAD: a line that, after indentation (so also inside a
#               describe), opens it("<test name>" or test("<test name>" (or single quotes), the
#               closing quote followed by "," or ")". Any other quoted literal - a button label, a
#               describe title, a name that is only a prefix - is not a test (it.each, .only and
#               .skip forms are not accepted either),
#               whose assertion text is not empty, and whose criterion matches the file: K-01 or
#               K-02 for CustomerDetail.tsx, K-03 or K-04 for CustomerList.tsx. A line opening
#               "- Red run" that does not parse fails. No M entry => no record allowed.
#   weakening   bash scripts/weakening-check.sh BASE HEAD exits 0.
#
# Writes. Only under a temporary directory outside the repository (the self-test fixtures).
#
# What this does not prove: that the suite is green (QA's run and the CI frontend job carry that),
# that a fix is minimal in meaning rather than in place (a hunk inside `change` can still change
# other behaviour — the Reviewer reads it), that the recorded red run happened (the record is a
# statement in the PR body; QA reruns the base `change`/`chooseState` mutation to reproduce it),
# or a weakening the weakening-check patterns do not see.

set -uo pipefail

BASE_SHA='5fcfeb898e63b7e15c9c9bbbbf1cd007aa791005'
CHECKPOINT_SHA='9d00ea9ef004b57518c5535cb5481fb6bf60aca3'
DETAIL='frontend/src/features/customers/CustomerDetail.tsx'
LIST='frontend/src/features/customers/CustomerList.tsx'
SELF_PATH='tests/doc-checks/EKO-3-11.sh'
WEAK='scripts/weakening-check.sh'

S_PATHS='EKO-3-11 K-05 paths every changed path is an allowed kind'
S_MECH='EKO-3-11 K-05 mechanism every production hunk lies inside change or chooseState'
S_RED='EKO-3-11 K-05 red-run every production change has its record and no record stands alone'
S_WEAK='EKO-3-11 K-05 weakening scripts/weakening-check.sh exits 0'

die() { echo "EKO-3-11 doc-check: $* — the check did not run" >&2; exit 2; }

MAIN_REF='refs/remotes/origin/main'

PR=""; HEAD_REV=""; BASE_REV=""; MODE=run
while [ $# -gt 0 ]; do
  case "$1" in
    --pr|--head|--base)
      [ $# -ge 2 ] && [ -n "$2" ] || die "$1 needs a value"
      case "$1" in --pr) PR="$2" ;; --head) HEAD_REV="$2" ;; --base) BASE_REV="$2" ;; esac
      shift 2 ;;
    --self-test) MODE=self; shift ;;
    *) die "unknown argument '$1' (usage: $0 --pr <file> [--head <rev>] [--base <rev>] | --self-test)" ;;
  esac
done
if [ "$MODE" = run ]; then
  [ -n "$PR" ] && [ -r "$PR" ] || die "--pr needs a readable file"
elif [ -n "$PR$HEAD_REV$BASE_REV" ]; then
  die "--self-test takes no other argument"
fi

# neutralize_git — override, for this shell and its children, the configuration that changes what
# git diff prints. GIT_CONFIG_COUNT entries are command scope: they win over every config file.
NEUTRAL_CFG=(color.ui=never color.diff=never diff.noprefix=false diff.mnemonicPrefix=false
  diff.srcPrefix=a/ diff.dstPrefix=b/ core.quotePath=true diff.relative=false diff.algorithm=myers
  diff.indentHeuristic=true diff.interHunkContext=0 diff.renames=true diff.suppressBlankEmpty=false
  core.autocrlf=false)
neutralize_git() {
  local i="${GIT_CONFIG_COUNT:-0}" kv
  [[ "$i" =~ ^[0-9]+$ ]] || i=0
  unset GIT_CONFIG_PARAMETERS GIT_EXTERNAL_DIFF GIT_DIFF_OPTS GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
  for kv in "${NEUTRAL_CFG[@]}"; do
    export "GIT_CONFIG_KEY_$i=${kv%%=*}" "GIT_CONFIG_VALUE_$i=${kv#*=}"
    i=$((i + 1))
  done
  export GIT_CONFIG_COUNT="$i"
}
neutralize_git
# the flags every diff of the range carries, on top of the environment above
DIFF_FLAGS=(--no-color --no-ext-diff --no-textconv --no-relative --src-prefix=a/ --dst-prefix=b/
  --diff-algorithm=myers --indent-heuristic --inter-hunk-context=0)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || die "cannot enter the repository root"
TOP="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null)" || die "not a git repository"

WORK="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$WORK"' EXIT
[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" != "$TOP" ] || die "the temporary directory $WORK lies inside the repository"

qgit() { git -c core.autocrlf=false -c advice.detachedHead=false -c user.name=qa -c user.email=qa@example.invalid "$@"; }

# ---- helpers -------------------------------------------------------------------------------------

# blob <repo> <rev> <path> — the file at <rev>, carriage returns removed.
# cat-file is plumbing: no colour, no textconv, no external driver.
blob() { git -C "$1" cat-file blob "$2:$3" 2>/dev/null | tr -d '\r'; }

# span <repo> <rev> <path> — "start end": the line of the function's opening line and of its
# closing line; empty when either is missing.
span() {
  local start_re end_re
  case "$3" in
    "$DETAIL") start_re='^  const change = async \(which: Change\) => \{$'; end_re='^  \};$' ;;
    "$LIST") start_re='^  function chooseState\(filter: StateFilter\) \{$'; end_re='^  \}$' ;;
    *) return 0 ;;
  esac
  blob "$1" "$2" "$3" | SPAN_S="$start_re" SPAN_E="$end_re" awk '
    start == 0 && $0 ~ ENVIRON["SPAN_S"] { start = NR; next }
    start > 0 && $0 ~ ENVIRON["SPAN_E"] { print start, NR; exit }'
}

# inside <s> <c> <start> <end> — a hunk side starting at line s with c lines lies strictly inside
# the body; a side with c = 0 is an insertion or deletion point after line s.
inside() {
  local s="$1" c="$2" start="$3" end="$4"
  if [ "$c" -eq 0 ]; then [ "$s" -ge "$start" ] && [ "$s" -lt "$end" ]
  else [ "$s" -gt "$start" ] && [ $((s + c - 1)) -lt "$end" ]; fi
}

# plan_entry_only <repo> <base> <head> — docs/PLAN.md only gains the EKO-3-11 entry.
plan_entry_only() {
  local d="$WORK/plan.diff" added
  git -C "$1" diff -U0 "${DIFF_FLAGS[@]}" "$2...$3" -- docs/PLAN.md > "$d.raw" 2>/dev/null || return 1
  tr -d '\r' < "$d.raw" > "$d"
  [ "$(grep -c '^@@' "$d")" -eq 1 ] || return 1
  ! grep -E '^-' "$d" | grep -qvE '^--- ' || return 1
  added="$(grep -E '^\+' "$d" | grep -vE '^\+\+\+ ')"
  [[ "$(grep -vE '^\+[[:space:]]*$' <<< "$added" | head -n 1)" == '+- [ ] **EKO-3-11** '* ]] || return 1
  [ "$(grep -cE '^\+[-*] ' <<< "$added")" -eq 1 ] || return 1
  ! grep -vE '^\+[[:space:]]*$|^\+  |^\+- \[ \] \*\*EKO-3-11\*\* ' <<< "$added" | grep -q . || return 1
}

# ---- the four sub-checks on <repo> <base> <head> <pr body> ---------------------------------------
# Each sets WHY and returns 0 (pass) or 1 (fail). NAMES holds the name-status lines.

NAMES=""
read_names() {
  NAMES="$(git -C "$1" diff --name-status -M --no-color --no-ext-diff --no-relative "$2...$3" 2> "$WORK/names.err")" || die "git diff $2...$3 failed: $(tail -n 1 "$WORK/names.err")"
}

# m_entries — the production paths with an M entry, one per line.
m_entries() { awk -F'\t' '$1 == "M" && ($2 == "'"$DETAIL"'" || $2 == "'"$LIST"'") { print $2 }' <<< "$NAMES"; }
# a_test <path> — the path is an A entry under frontend/tests/.
a_test() { awk -F'\t' -v p="$1" '$1 == "A" && $2 == p { f = 1 } END { exit !f }' <<< "$NAMES" && [[ "$1" == frontend/tests/* ]]; }

# declares_test <repo> <rev> <file> <name> — a line of the file, indentation removed, opens
# it("<name>" or test("<name>" (either quote), the closing quote followed by "," or ")".
declares_test() {
  blob "$1" "$2" "$3" | TNAME="$4" awk '
    BEGIN { n = ENVIRON["TNAME"]; ln = length(n) }
    {
      l = $0; sub(/^[ \t]+/, "", l)
      if (substr(l, 1, 3) == "it(") r = substr(l, 4)
      else if (substr(l, 1, 5) == "test(") r = substr(l, 6)
      else next
      q = substr(r, 1, 1)
      if (q != "\"" && q != "\047") next
      after = substr(r, ln + 3, 1)
      if (substr(r, 2, ln) == n && substr(r, ln + 2, 1) == q && (after == "," || after == ")")) { f = 1; exit }
    }
    END { exit !f }'
}

# resolve_base <repo> <pinned base> <checkpoint> <--base value or empty> <head sha> <main ref> —
# sets RBASE to the commit the range starts from, or sets RERR and returns 1 ("The range" above).
RBASE=""; RERR=""
resolve_base() {
  local repo="$1" pinned="$2" cp="$3" arg="$4" head="$5" main="$6" mb
  RBASE=""; RERR=""
  if [ -z "$arg" ]; then
    if [ -n "$(git -C "$repo" rev-list --merges "$pinned..$head" 2>/dev/null)" ]; then
      RERR="the range $pinned..$head holds a merge commit; rerun with --base origin/main"; return 1
    fi
    RBASE="$pinned"; return 0
  fi
  git -C "$repo" rev-parse --verify --quiet "$arg^{commit}" > /dev/null || { RERR="--base $arg is not a commit"; return 1; }
  mb="$(git -C "$repo" merge-base "$arg" "$head" 2>/dev/null)" || { RERR="--base $arg has no merge base with $head"; return 1; }
  git -C "$repo" merge-base --is-ancestor "$pinned" "$mb" || { RERR="the merge base $mb of --base $arg does not contain BASE $pinned"; return 1; }
  git -C "$repo" rev-parse --verify --quiet "$main^{commit}" > /dev/null || { RERR="$main is missing (git fetch origin main)"; return 1; }
  git -C "$repo" merge-base --is-ancestor "$mb" "$main" || { RERR="the merge base $mb of --base $arg is not on $main"; return 1; }
  ! git -C "$repo" merge-base --is-ancestor "$cp" "$mb" || { RERR="the merge base $mb of --base $arg already holds the checkpoint $cp"; return 1; }
  RBASE="$mb"
}

check_paths() {
  local repo="$1" base="$2" head="$3" st p rest bad="" n=0 note=""
  while IFS=$'\t' read -r st p rest; do
    [ -n "$st" ] || continue
    n=$((n + 1))
    case "$st" in
      A)
        case "$p" in
          frontend/tests/*) ;;
          "$SELF_PATH") ;;
          docs/cost-register/*)
            if [[ "$p" =~ ^docs/cost-register/[0-9]{4}-[0-9]{2}-[0-9]{2}_EKO-3-11_[A-Za-z0-9._-]+\.json$ ]]; then note="bookkeeping"
            else bad="$bad$st $p; "; fi ;;
          *) bad="$bad$st $p; " ;;
        esac ;;
      M)
        case "$p" in
          "$DETAIL"|"$LIST") ;;
          docs/PLAN.md)
            if plan_entry_only "$repo" "$base" "$head"; then note="bookkeeping"
            else bad="${bad}M $p (not only the EKO-3-11 entry added); "; fi ;;
          *) bad="$bad$st $p; " ;;
        esac ;;
      *) bad="$bad$st $p${rest:+ -> $rest}; " ;;
    esac
  done <<< "$NAMES"
  WHY="$n entries${note:+, the cost rows and PLAN entry read as EKO-3-11 bookkeeping (assumption)}"
  [ -z "$bad" ] || { WHY="not an allowed kind: ${bad%; }"; return 1; }
}

check_mechanism() {
  local repo="$1" base="$2" head="$3" p bs be hs he os oc ns nc bad="" hunks=0 ph line d="$WORK/mech.diff"
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    read -r bs be <<< "$(span "$repo" "$base" "$p")"
    read -r hs he <<< "$(span "$repo" "$head" "$p")"
    [ -n "${bs:-}" ] && [ -n "${be:-}" ] || { bad="$bad$p: the function is not found at the base; "; continue; }
    [ -n "${hs:-}" ] && [ -n "${he:-}" ] || { bad="$bad$p: the function is not found at the head; "; continue; }
    git -C "$repo" diff -U0 "${DIFF_FLAGS[@]}" "$base...$head" -- "$p" > "$d" 2>/dev/null || { bad="$bad$p: git diff failed; "; continue; }
    ph=0
    while IFS= read -r line; do
      line="${line%$'\r'}"
      case "$line" in @@*) ;; *) continue ;; esac
      [[ "$line" =~ ^@@\ -([0-9]+)(,([0-9]+))?\ \+([0-9]+)(,([0-9]+))?\ @@ ]] || { bad="$bad$p: unparsed hunk header; "; continue; }
      os="${BASH_REMATCH[1]}"; oc="${BASH_REMATCH[3]:-1}"; ns="${BASH_REMATCH[4]}"; nc="${BASH_REMATCH[6]:-1}"
      ph=$((ph + 1))
      inside "$os" "$oc" "$bs" "$be" || bad="$bad$p: base lines $os,$oc outside $bs-$be; "
      inside "$ns" "$nc" "$hs" "$he" || bad="$bad$p: head lines $ns,$nc outside $hs-$he; "
    done < "$d"
    # an M entry is a change; a diff that shows none of it cannot be placed, so it fails closed
    [ "$ph" -gt 0 ] || bad="$bad$p: M entry with no parsed hunk (fails closed); "
    hunks=$((hunks + ph))
  done <<< "$(m_entries)"
  WHY="$hunks production hunk(s)"
  [ -z "$bad" ] || { WHY="${bad%; }"; return 1; }
}

check_red_run() {
  local repo="$1" head="$3" body="$4" line rest k ref file name failed bad="" recs=0 p
  local have_detail=0 have_list=0 m_detail=0 m_list=0
  while IFS= read -r p; do
    case "$p" in "$DETAIL") m_detail=1 ;; "$LIST") m_list=1 ;; esac
  done <<< "$(m_entries)"
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[-*][[:space:]]+[Rr]ed[[:space:]-]run ]] || continue
    recs=$((recs + 1))
    rest="${line#?}"; rest="${rest#"${rest%%[![:space:]]*}"}"
    if [[ "$rest" != "Red run — "* ]]; then bad="${bad}malformed record '$line'; "; continue; fi
    rest="${rest#"Red run — "}"
    k="${rest%%" — "*}"; rest="${rest#*" — "}"
    ref="${rest%%" — "*}"; failed="${rest#*" — "}"
    file="${ref%%::*}"; name="${ref#*::}"
    if ! [[ "$k" =~ ^K-0[1-4]$ ]] || [ "$ref" = "$rest" ] || [ "$file" = "$ref" ] || [ -z "$name" ] \
       || [[ "$failed" != "failed on: "?* ]]; then bad="${bad}malformed record '$line'; "; continue; fi
    if ! a_test "$file"; then bad="$bad$k record names $file, not a test file this range adds; "; continue; fi
    if [[ "$file" != *.test.tsx ]]; then bad="$bad$k record names $file, not a .test.tsx file; "; continue; fi
    if ! declares_test "$repo" "$head" "$file" "$name"; then bad="$bad$k record names '$name', not a test in $file (no it()/test() declares it); "; continue; fi
    case "$k" in
      K-01|K-02) if [ "$m_detail" -eq 1 ]; then have_detail=1; else bad="$bad$k record without an M of $DETAIL; "; fi ;;
      K-03|K-04) if [ "$m_list" -eq 1 ]; then have_list=1; else bad="$bad$k record without an M of $LIST; "; fi ;;
    esac
  done < "$body"
  [ "$m_detail" -eq 0 ] || [ "$have_detail" -eq 1 ] || bad="${bad}M $DETAIL without a K-01/K-02 red-run record; "
  [ "$m_list" -eq 0 ] || [ "$have_list" -eq 1 ] || bad="${bad}M $LIST without a K-03/K-04 red-run record; "
  WHY="$((m_detail + m_list)) production change(s), $recs record(s)"
  [ -z "$bad" ] || { WHY="${bad%; }"; return 1; }
}

check_weakening() {
  local repo="$1" base="$2" head="$3" code
  [ -f "$repo/$WEAK" ] || { WHY="$WEAK missing"; return 1; }
  ( cd "$repo" && bash "$WEAK" "$base" "$head" ) > "$WORK/weak.out" 2>&1; code=$?
  WHY="exit $code; $(tail -n 1 "$WORK/weak.out" | tr -d '\r' | cut -c1-160)"
  [ "$code" -eq 0 ]
}

# run_all <repo> <base> <head> <pr body> — prints the four lines; FAILED_KEYS lists the failed ones.
FAILED_KEYS=""; WHY=""
run_all() {
  local key name fn
  FAILED_KEYS=""
  read_names "$1" "$2" "$3"
  for key in paths mechanism red-run weakening; do
    case "$key" in
      paths) name="$S_PATHS"; fn=check_paths ;;
      mechanism) name="$S_MECH"; fn=check_mechanism ;;
      red-run) name="$S_RED"; fn=check_red_run ;;
      weakening) name="$S_WEAK"; fn=check_weakening ;;
    esac
    WHY=""
    if "$fn" "$@"; then echo "ok   $name — $WHY"
    else echo "FAIL $name — $WHY"; FAILED_KEYS="$FAILED_KEYS $key"; fi
  done
  FAILED_KEYS="${FAILED_KEYS# }"
}

# ---- self-test -------------------------------------------------------------------------------------

st_total=0; st_fail=0
FX=""; FXBASE=""

fx_init() {
  FX="$WORK/fx"; mkdir -p "$FX"
  qgit init --quiet "$FX" || die "self-test: git init failed"
  mkdir -p "$FX/scripts" "$FX/frontend/src/features/customers" "$FX/frontend/tests/support" \
    "$FX/frontend/tests/features/customers" "$FX/docs/cost-register" "$FX/backend/app"
  cp -- "$TOP/$WEAK" "$FX/$WEAK" || die "self-test: cannot copy $WEAK"
  cat > "$FX/$DETAIL" <<'EOF'
export function CustomerDetail() {
  const before = 1;
  const change = async (which: Change) => {
    const result = await act(which);
    if (result.kind === "changed" && result.customer.archived === (which === "archive")) {
      return ok();
    }
    return fail();
  };
  const after = 2;
}
EOF
  cat > "$FX/$LIST" <<'EOF'
export function CustomerList() {
  const before = 1;
  function chooseState(filter: StateFilter) {
    if (filter === (request.filter ?? "active")) {
      return;
    }
    load(filter);
  }
  const after = 2;
}
EOF
  printf '%s\n' 'export function stubListScreen() {' '  return 1;' '}' > "$FX/frontend/tests/support/customer-list-screen.ts"
  printf '%s\n' 'it("keeps one", () => {' '  expect(1).toBe(1);' '});' 'it("keeps two", () => {' '  expect(2).toBe(2);' '});' \
    > "$FX/frontend/tests/features/customers/k07-eko305-list-state.test.tsx"
  printf '%s\n' 'print("app")' > "$FX/backend/app/main.py"
  printf '%s\n' '{ "name": "fixture" }' > "$FX/frontend/package.json"
  printf '%s\n' '{ "task": "EKO-3-10" }' > "$FX/docs/cost-register/2026-11-26_EKO-3-10_code_developer-frontend_1.json"
  printf '%s\n' '# Plan' '' '- [x] **EKO-3-10** — an earlier task.' '  *Done when:* it was done.' > "$FX/docs/PLAN.md"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet -m base || die "self-test: base commit failed"
  FXBASE="$(git -C "$FX" rev-parse HEAD)"
}

# the passing change set: two new tests, the doc-check, a cost row, the PLAN entry.
fx_good() {
  printf '%s\n' 'it("claim one", () => {' '  expect(1).toBe(1);' '});' > "$FX/frontend/tests/features/customers/eko311-new.test.tsx"
  mkdir -p "$FX/tests/doc-checks" && printf '%s\n' '#!/usr/bin/env bash' > "$FX/$SELF_PATH"
  printf '%s\n' '{ "task": "EKO-3-11" }' > "$FX/docs/cost-register/2026-11-27_EKO-3-11_code_developer-frontend_1.json"
  printf '%s\n' '' '- [ ] **EKO-3-11** — Add the owed tests (#266).' '  *Done when:* the tests fail under their mutations.' >> "$FX/docs/PLAN.md"
}

REC_K01='- Red run — K-01 — frontend/tests/features/customers/eko311-new.test.tsx::claim one — failed on: expect(alert) found nothing'
REC_K03='- Red run — K-03 — frontend/tests/features/customers/eko311-new.test.tsx::claim one — failed on: expect(lists).toEqual([])'

# hostile_env — user configuration that reshapes or empties git diff output: colour forced, an
# external diff driver printing nothing, no prefixes, another algorithm, merged hunks, renames off.
hostile_env() {
  local ext="$WORK/ext-diff.sh"
  printf '%s\n' '#!/bin/sh' 'exit 0' > "$ext" && chmod +x "$ext"
  printf '%s\n' '[color]' '	ui = always' '	diff = always' '[diff]' "	external = $ext" '	noprefix = true' \
    '	mnemonicPrefix = true' '	algorithm = patience' '	interHunkContext = 40' '	renames = false' \
    '	relative = true' '[core]' '	quotePath = false' > "$WORK/hostile.gitconfig"
  export GIT_CONFIG_GLOBAL="$WORK/hostile.gitconfig" GIT_EXTERNAL_DIFF="$ext" \
    GIT_CONFIG_PARAMETERS="'color.diff=always' 'diff.noprefix=true'" \
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=color.ui GIT_CONFIG_VALUE_0=always
}

# st_judge <name> <want> <head> <checkpoint> <--base value or empty> — runs the check the way the
# runner does (range resolution, then the four sub-checks); under ST_HOSTILE=1 hostile_env is set
# first and neutralized after, as a user's environment would be at the script's start.
ST_HOSTILE=0
st_judge() {
  local name="$1" want="${2%%|*}" has="" head="$3" cp="$4" arg="$5" got
  case "$2" in *"|"*) has="${2#*|}" ;; esac
  st_total=$((st_total + 1))
  rm -f "$WORK/st.keys"
  (
    if [ "$ST_HOSTILE" = 1 ]; then hostile_env; neutralize_git; fi
    if resolve_base "$FX" "$FXBASE" "$cp" "$arg" "$head" "$MAIN_REF"; then
      run_all "$FX" "$RBASE" "$head" "$WORK/st-body.md"
    else
      FAILED_KEYS=range; echo "FAIL range — $RERR"
    fi
    echo "$FAILED_KEYS" > "$WORK/st.keys"
  ) > "$WORK/st.out" 2>&1
  got="$(cat "$WORK/st.keys" 2>/dev/null || echo '<the run died>')"
  if [ "$got" = "$want" ] && { [ -z "$has" ] || grep -qF -- "$has" "$WORK/st.out"; }; then
    echo "ok   self-test $name — failed: ${want:-none}${has:+ (reports '$has')}"
  else
    echo "FAIL self-test $name — expected failed '${want:-none}'${has:+ reporting '$has'}, got '${got:-none}'"; sed 's/^/       /' "$WORK/st.out"
    st_fail=$((st_fail + 1))
  fi
}

fx_reset() { qgit -C "$FX" checkout --quiet --force "$FXBASE" && qgit -C "$FX" clean --quiet -fdx || die "self-test: cannot reset the fixture"; }

# st_case <name> <want> <shell edit after fx_good> <pr body lines...> — <want> is "<failed keys>"
# or "<failed keys>|<text the report must hold>", so a case fails for its own reason, not another.
st_case() {
  local name="$1" want="$2" edit="$3" head
  shift 3
  fx_reset
  ( cd "$FX" && fx_good && eval "$edit" ) || die "self-test: the edit for '$name' failed"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet --allow-empty -m "$name" || die "self-test: commit for '$name' failed"
  head="$(git -C "$FX" rev-parse HEAD)"
  printf '%s\n' '## Summary' 'Tests only.' "$@" > "$WORK/st-body.md"
  st_judge "$name" "$want" "$head" "$head" ""
}

# st_merge_case <name> <want> <none|main|task> <shell edit amended into the merge> <pr body lines...>
# — main gains a line above `change` in CustomerDetail.tsx and a backend file; the branch makes the
# K-01 fix (its checkpoint), then takes "Merge main"; origin/main points at main's commit. The range
# starts at: none = no --base; main = --base origin/main; task = --base <the checkpoint>.
st_merge_case() {
  local name="$1" want="$2" choice="$3" edit="$4" mainc task head arg=""
  shift 4
  fx_reset
  ( cd "$FX" && sl '1a\  const fromMain = 0;' "$DETAIL" && printf 'print(3)\n' > backend/app/other.py ) || die "self-test: main edit failed"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet -m main || die "self-test: main commit failed"
  mainc="$(git -C "$FX" rev-parse HEAD)"
  qgit -C "$FX" checkout --quiet --force "$FXBASE" || die "self-test: checkout failed"
  ( cd "$FX" && fx_good && eval "$ST_DFIX" ) || die "self-test: task edit failed"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet -m task || die "self-test: task commit failed"
  task="$(git -C "$FX" rev-parse HEAD)"
  qgit -C "$FX" merge --quiet --no-edit -m "Merge main" "$mainc" > /dev/null || die "self-test: the merge failed"
  ( cd "$FX" && eval "$edit" ) || die "self-test: the merge edit for '$name' failed"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet --amend --no-edit || die "self-test: amend failed"
  head="$(git -C "$FX" rev-parse HEAD)"
  qgit -C "$FX" update-ref "$MAIN_REF" "$mainc" || die "self-test: update-ref failed"
  case "$choice" in main) arg=origin/main ;; task) arg="$task" ;; esac
  printf '%s\n' '## Summary' 'Tests only.' "$@" > "$WORK/st-body.md"
  st_judge "$name" "$want" "$head" "$task" "$arg"
}

sl() { sed -i "$1" "$2"; }

self_test() {
  local dfix lfix fd="frontend/src/features/customers" ft="frontend/tests/features/customers"
  dfix="sl '5s/=== (which === \"archive\")/!== (which === \"restore\")/' '$DETAIL'"
  lfix="sl '4s/?? \"active\"/|| \"active\"/' '$LIST'"
  ST_DFIX="$dfix"
  fx_init
  # the passing outcomes
  st_case 'no defect: only new tests and bookkeeping pass' '' ':'
  st_case 'defect: a K-01 record and a hunk inside change pass' '' "$dfix" "$REC_K01"
  st_case 'twins: both fixes with one record each pass' '' "$dfix && $lfix" "$REC_K01" "$REC_K03"
  # K-05 contrasts
  st_case 'contrast no-defect: an unrecorded line of CustomerList.tsx fails red-run' \
    "red-run|M $LIST without a K-03/K-04 red-run record" "$lfix"
  st_case 'contrast wrong file: a K-03 record for a CustomerDetail.tsx fix fails red-run' \
    "red-run|K-03 record without an M of $LIST" "$dfix" "${REC_K01/K-01/K-03}"
  st_case 'contrast outside the mechanism: a K-01 fix hunk moved outside change fails mechanism' \
    "mechanism|$DETAIL: base lines 2,1 outside 3-9" "sl '2s/before = 1/before = 3/' '$DETAIL'" "$REC_K01"
  # K-05 planted mutations
  st_case 'planted: a new file under frontend/src fails paths' "paths|A $fd/helper.ts" \
    "printf 'export const x = 1;\n' > $fd/helper.ts"
  st_case 'planted: a file under backend fails paths' 'paths|M backend/app/main.py' \
    "printf 'print(2)\n' >> backend/app/main.py"
  st_case 'planted: a one-line edit of customer-list-screen.ts fails paths' 'paths|M frontend/tests/support/customer-list-screen.ts' \
    "sl '2s/return 1/return 2/' frontend/tests/support/customer-list-screen.ts"
  st_case 'planted: a deleted test case of k07-eko305-list-state fails paths and weakening' \
    "paths weakening|M $ft/k07-eko305-list-state.test.tsx" "sl '4,6d' $ft/k07-eko305-list-state.test.tsx"
  st_case 'planted: a package file change fails paths' 'paths|M frontend/package.json' \
    "printf '{ \"name\": \"changed\" }\n' > frontend/package.json"
  st_case 'planted: a renamed test file fails paths' "paths|$ft/k07-eko305-list-state.test.tsx -> $ft/k07-moved.test.tsx" \
    "git mv $ft/k07-eko305-list-state.test.tsx $ft/k07-moved.test.tsx"
  # the bookkeeping allowance does not open the paths
  st_case 'bookkeeping: a cost row of another task fails paths' 'paths|A docs/cost-register/2026-11-27_EKO-3-10_qa_1.json' \
    "printf '{}\n' > docs/cost-register/2026-11-27_EKO-3-10_qa_1.json"
  st_case 'bookkeeping: an edited existing cost row fails paths' 'paths|M docs/cost-register/2026-11-26_EKO-3-10' \
    "printf '{ \"task\": \"EKO-3-10\", \"x\": 1 }\n' > docs/cost-register/2026-11-26_EKO-3-10_code_developer-frontend_1.json"
  st_case 'bookkeeping: a PLAN.md line of another entry changed fails paths' 'paths|M docs/PLAN.md (not only the EKO-3-11 entry added)' \
    "sl '3s/\[x\]/[ ]/' docs/PLAN.md"
  st_case 'bookkeeping: a PLAN.md line added to another entry fails paths' 'paths|M docs/PLAN.md (not only the EKO-3-11 entry added)' \
    "sl '4a\  *Note:* added to EKO-3-10.' docs/PLAN.md"
  st_case 'bookkeeping: a second PLAN.md entry added with EKO-3-11 fails paths' 'paths|M docs/PLAN.md (not only the EKO-3-11 entry added)' \
    "printf -- '- [ ] **EKO-3-12** — another.\n' >> docs/PLAN.md"
  # the red-run record itself
  st_case 'red-run: a record with no production change fails' "red-run|K-01 record without an M of $DETAIL" ':' "$REC_K01"
  st_case 'red-run: a record naming a test that does not exist fails' 'red-run|not a test in' \
    "$dfix" "${REC_K01/claim one/claim nine}"
  st_case 'red-run: a record naming an existing test file fails' 'red-run|not a test file this range adds' \
    "$dfix" "${REC_K01/eko311-new.test.tsx::claim one/k07-eko305-list-state.test.tsx::keeps one}"
  st_case 'red-run: a record without the failing assertion fails' 'red-run|malformed record' \
    "$dfix" "${REC_K01%% — failed on:*}"
  st_case 'red-run: twins with one record fail' "red-run|M $LIST without a K-03/K-04 red-run record" \
    "$dfix && $lfix" "$REC_K01"
  # R-01: the record must name an it()/test() declaration in an added .test.tsx file
  st_case 'red-run R-01: a record naming a button label in the test file fails' 'red-run|not a test in' \
    "$dfix && printf '%s\n' 'const label = \"Archiwizuj klienta\";' >> $ft/eko311-new.test.tsx" \
    "${REC_K01/claim one/Archiwizuj klienta}"
  st_case 'red-run R-01: a record naming a describe title fails' 'red-run|not a test in' \
    "$dfix && printf '%s\n' 'describe(\"K-01 group\", () => {' '  it(\"claim two\", () => {});' '});' >> $ft/eko311-new.test.tsx" \
    "${REC_K01/claim one/K-01 group}"
  st_case 'red-run R-01: a record naming only a prefix of a test name fails' 'red-run|not a test in' \
    "$dfix && printf '%s\n' 'const prefix = \"claim\";' >> $ft/eko311-new.test.tsx" "${REC_K01/claim one/claim}"
  st_case 'red-run R-01: a record naming an it() inside describe passes' '' \
    "$dfix && printf '%s\n' 'describe(\"K-01 group\", () => {' '  it(\"claim two\", () => {});' '});' >> $ft/eko311-new.test.tsx" \
    "${REC_K01/claim one/claim two}"
  st_case 'red-run R-01: a record naming an added non-test file fails' 'red-run|not a .test.tsx file' \
    "$dfix && printf '%s\n' 'it(\"claim one\", () => {});' > $ft/eko311-helper.ts" \
    "${REC_K01/eko311-new.test.tsx::/eko311-helper.ts::}"
  # R-02: user configuration cannot empty or reshape the diffs, and an M with no hunk fails closed
  ST_HOSTILE=1
  st_case 'R-02 hostile config: a K-01 fix hunk outside change still fails mechanism' \
    "mechanism|$DETAIL: base lines 2,1 outside 3-9" "$dfix && sl '2s/before = 1/before = 3/' '$DETAIL'" "$REC_K01"
  st_case 'R-02 hostile config: a deleted test case still fails paths and weakening' \
    "paths weakening|M $ft/k07-eko305-list-state.test.tsx" "sl '4,6d' $ft/k07-eko305-list-state.test.tsx"
  st_case 'R-02 hostile config: a K-01 record and a hunk inside change still pass' '' "$dfix" "$REC_K01"
  ST_HOSTILE=0
  st_case 'R-02: a mode-only M of CustomerDetail.tsx (no hunk) fails mechanism closed' \
    "mechanism|$DETAIL: M entry with no parsed hunk" "git update-index --chmod=+x '$DETAIL'" "$REC_K01"
  # R-03: a branch that took a merge from main
  st_merge_case 'R-03 merged main, --base origin/main: main files are not the task, the fix passes' '' main ':' "$REC_K01"
  st_merge_case 'R-03 merged main, no --base: the run refuses the merge range' 'range|holds a merge commit' none ':' "$REC_K01"
  st_merge_case 'R-03 merged main, --base at the checkpoint: refused, a base off main cannot hide the task' \
    'range|is not on refs/remotes/origin/main' task ':' "$REC_K01"
  st_merge_case 'R-03 merged main, --base origin/main: a backend file added in the merge commit fails paths' \
    'paths|A backend/app/evil.py' main "printf 'print(4)\n' > backend/app/evil.py" "$REC_K01"
  st_merge_case 'R-03 merged main, --base origin/main: the fix without its record fails red-run' \
    "red-run|M $DETAIL without a K-01/K-02 red-run record" main ':'
  echo "EKO-3-11 self-test: $((st_total - st_fail)) of $st_total passed"
  [ "$st_fail" -eq 0 ]
}

# ---- the runner --------------------------------------------------------------------------------

case "$MODE" in
  self) self_test; exit $? ;;
esac

HEAD_REV="${HEAD_REV:-$CHECKPOINT_SHA}"
for rev in "$BASE_SHA" "$HEAD_REV"; do
  git -C "$TOP" rev-parse --verify --quiet "$rev^{commit}" > /dev/null || die "$rev is not a commit in this repository"
done
HEAD_SHA="$(git -C "$TOP" rev-parse "$HEAD_REV^{commit}")"
git -C "$TOP" merge-base --is-ancestor "$BASE_SHA" "$HEAD_SHA" || die "$BASE_SHA is not an ancestor of $HEAD_SHA"
git -C "$TOP" merge-base --is-ancestor "$CHECKPOINT_SHA" "$HEAD_SHA" || die "$CHECKPOINT_SHA is not an ancestor of $HEAD_SHA"
resolve_base "$TOP" "$BASE_SHA" "$CHECKPOINT_SHA" "$BASE_REV" "$HEAD_SHA" "$MAIN_REF" || die "$RERR"
[ "$RBASE" != "$HEAD_SHA" ] || die "the range $RBASE...$HEAD_SHA is empty"

echo "EKO-3-11 doc-check: range $RBASE...$HEAD_SHA${BASE_REV:+ (--base $BASE_REV)}"
run_all "$TOP" "$RBASE" "$HEAD_SHA" "$PR"
n_fail=$(wc -w <<< "$FAILED_KEYS")
echo "EKO-3-11 doc-check: $((4 - n_fail)) passed, $n_fail failed"
[ "$n_fail" -eq 0 ]
