#!/usr/bin/env bash
# EKO-1-39 — proves that the names PR #30's "K-n — test:" lines quote are labels of ok lines that a
# real run of tests/doc-checks/EKO-1-01.sh prints, and that EKO-1-01.sh exits 2 on a depth-1 clone
# (Issue #230, criteria K-01..K-07).
#
#   bash tests/doc-checks/EKO-1-39.sh                      # judge the EKO-1-01.sh of this tree
#   bash tests/doc-checks/EKO-1-39.sh --pr-body <file>     # also compare the names with a saved PR #30 body
#   bash tests/doc-checks/EKO-1-39.sh --self-test          # built-in contrasts in throwaway clones
#
#   gh pr view 30 --json body --jq .body > pr-30.md        # the body --pr-body expects
#
# Output. One line per sub-check, "ok   <name> — <detail>" or "FAIL <name> — <detail>: <why>"; the
# names are what a "K-n — test:" line of this task's PR quotes. Exit codes: 0 = every sub-check
# passed, 1 = at least one failed, 2 = the script could not run (a bad argument, not a git
# repository, a temporary directory inside the repository) — never read 2 as a pass.
#
# What is judged. EKO-1-01.sh as it is in this working tree, uncommitted edits included: it is run
# in place (K-01, K-03), and copied over a throwaway depth-1 clone of this repository's HEAD (K-04).
# The reference list below is PR #30's seven names, copied by hand from its body; it is never read
# from EKO-1-01.sh, so renaming a label there cannot rename the reference (Issue #230 K-02). PR #30
# is frozen history; --pr-body re-checks the copy against a body fetched with gh.
#
# Writes. Only under temporary directories outside the repository; every mutation the self-test
# makes is made in a throwaway clone. The K-07 sub-check compares the repository's status, refs,
# worktrees, stash and the bytes of EKO-1-01.sh before and after the run.
#
# What this proves: that the quoted names are printed as ok labels and that the exit codes hold. It
# does not prove that the sub-checks printed under a label belong to that criterion.

set -uo pipefail

# PR #30's "K-n — test:" names, in criterion order (byte-equal to its body on 2026-11-22).
REF_IDS=(K-01 K-02 K-03 K-04 K-05 K-06 K-07)
REF_NAMES=(
  'QA document check K-01 (closed list over ADR-0001 Decision)'
  'QA document check K-02 (closed list over ADR-0002 Decision)'
  'QA document check K-03 (template sections, options, controls)'
  'QA document checks K-04(1), K-04-2, K-04(3)'
  'QA document checks K-05(1)(2)(3)(5), K-05-4, K-05-4f, K-05-fe'
  'QA document checks K-06(1), K-06(2), K-06-new'
  'QA document check K-07 (git diff scope, capabilities.md unchanged)'
)

S_K01='EKO-1-39 K-01 every PR #30 name labels an ok line'
S_K01X='EKO-1-39 K-01 no ok label outside PR #30'"'"'s seven'
S_K02='EKO-1-39 K-02 reference list is PR #30'"'"'s seven names'
S_K03='EKO-1-39 K-03 EKO-1-01.sh exits 0'
S_K04='EKO-1-39 K-04 depth-1 clone exits 2'
S_K04U='EKO-1-39 K-04 unshallowed clone exits 0'
S_K07='EKO-1-39 K-07 repository untouched by the run'

DOC0101='tests/doc-checks/EKO-1-01.sh'
HELPERS=(scripts/layer-check.sh scripts/risk-check.sh)
STOP_TEXT='the checks did not run'

die() { echo "EKO-1-39 doc-check: $* — the check did not run" >&2; exit 2; }

PR_BODY=""; SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pr-body) [ $# -ge 2 ] || die "--pr-body needs a file"; PR_BODY="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    *) die "unknown argument '$1' (usage: $0 [--pr-body <file>] | --self-test)" ;;
  esac
done
[ "$SELF_TEST" -eq 0 ] || [ -z "$PR_BODY" ] || die "--self-test takes no other argument"
[ -z "$PR_BODY" ] || [ -r "$PR_BODY" ] || die "cannot read the PR body '$PR_BODY'"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || die "cannot enter the repository root"
TOP="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null)" || die "not a git repository"

WORK="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$WORK"' EXIT
tmp_top="$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)"
[ "$tmp_top" != "$TOP" ] || die "the temporary directory $WORK lies inside the repository"

# file_url <dir> — a file:// URL; a plain local path would make "clone --depth 1" a full clone.
file_url() { case "$1" in /*) printf 'file://%s' "$1" ;; *) printf 'file:///%s' "$1" ;; esac; }
qgit() { git -c core.autocrlf=false -c advice.detachedHead=false "$@"; }

# ---- one run of EKO-1-01.sh --------------------------------------------------------------------

# run_0101 <tree> <dir> — run the tree's EKO-1-01.sh into <dir>/out and <dir>/err; RUN_CODE is its
# exit code, or "missing". Output goes to files and is read from files, never through a pipe.
RUN_CODE=""
run_0101() {
  : > "$2/out"; : > "$2/err"
  if [ ! -f "$1/$DOC0101" ]; then RUN_CODE=missing; return; fi
  bash "$1/$DOC0101" > "$2/out" 2> "$2/err" < /dev/null; RUN_CODE=$?
}

# ---- K-01: the printed ok labels against the seven names --------------------------------------

# ok_labels <output file> — LABELS gets one entry per ok line: the text after "ok" and exactly three
# spaces, up to the first " — ". No trimming, so a trailing or extra space stays part of the label.
LABELS=()
ok_labels() {
  local line rest
  LABELS=()
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in "ok   "*) ;; *) continue ;; esac
    rest="${line#"ok   "}"
    LABELS+=("${rest%%" — "*}")
  done < "$1"
}

k01_names() {
  local i label hit missing=""
  ok_labels "$1"
  for i in "${!REF_NAMES[@]}"; do
    hit=0
    for label in "${LABELS[@]}"; do [ "$label" != "${REF_NAMES[$i]}" ] || { hit=1; break; }; done
    [ "$hit" -eq 1 ] || missing="$missing${missing:+; }${REF_IDS[$i]} '${REF_NAMES[$i]}'"
  done
  [ -z "$missing" ] || { WHY="no ok line under PR #30's name for $missing (${#LABELS[@]} ok lines read)"; return 1; }
}

# G-5 A: an ok label that is not one of the seven means the file has drifted from PR #30.
k01_extra() {
  local label ref known extra=""
  ok_labels "$1"
  for label in "${LABELS[@]}"; do
    known=0
    for ref in "${REF_NAMES[@]}"; do [ "$label" != "$ref" ] || { known=1; break; }; done
    [ "$known" -eq 1 ] || [[ "$extra" == *"'$label';"* ]] || extra="$extra'$label'; "
  done
  [ -z "$extra" ] || { WHY="ok lines under labels PR #30 does not quote: ${extra%; }"; return 1; }
}

# ---- K-02: the reference list --------------------------------------------------------------------

# pr_test_names <body> — "K-n<TAB>name" for each test line in the "## Definition of done" section,
# outside HTML comments, by the rule of links() in scripts/evidence-chain.sh (CR dropped, the name
# trimmed of white space and backticks).
pr_test_names() {
  tr -d '\r' < "$1" | awk '
    function trim(v) { gsub(/^[[:space:]`]+|[[:space:]`]+$/, "", v); return v }
    {
      line = $0
      if (incomment) { if (index(line, "-->")) { incomment = 0; line = substr(line, index(line, "-->") + 3) } else next }
      while (index(line, "<!--")) {
        pre = substr(line, 1, index(line, "<!--") - 1); rest = substr(line, index(line, "<!--") + 4)
        if (index(rest, "-->")) line = pre substr(rest, index(rest, "-->") + 3)
        else { line = pre; incomment = 1 }
      }
    }
    /^## / { sec = index($0, "## Definition of done") == 1; next }
    !sec || line !~ /^[[:space:]]*[-*][[:space:]]+K-[0-9]+/ { next }
    {
      s = line; sub(/^[[:space:]]*[-*][[:space:]]+/, "", s)
      id = s; sub(/[^A-Za-z0-9-].*/, "", id); rest = substr(s, length(id) + 1)
      if (match(rest, "^[[:space:]]+(—|–|-)[[:space:]]+test:")) { v = trim(substr(rest, RLENGTH + 1)); if (v != "") print id "\t" v }
    }'
}

k02_reference() {
  local i j want got
  [ "${#REF_NAMES[@]}" -eq 7 ] && [ "${#REF_IDS[@]}" -eq 7 ] || { WHY="the reference list has ${#REF_NAMES[@]} names, not 7"; return 1; }
  for i in "${!REF_NAMES[@]}"; do
    [ -n "${REF_NAMES[$i]}" ] || { WHY="the name for ${REF_IDS[$i]} is empty"; return 1; }
    [[ "${REF_NAMES[$i]}" != *$'\r'* ]] || { WHY="the name for ${REF_IDS[$i]} carries a carriage return"; return 1; }
    for ((j = i + 1; j < ${#REF_NAMES[@]}; j++)); do
      [ "${REF_NAMES[$i]}" != "${REF_NAMES[$j]}" ] || { WHY="${REF_IDS[$i]} and ${REF_IDS[$j]} share a name"; return 1; }
    done
  done
  [ -n "$1" ] || return 0
  want="$(for i in "${!REF_NAMES[@]}"; do printf '%s\t%s\n' "${REF_IDS[$i]}" "${REF_NAMES[$i]}"; done)"
  got="$(pr_test_names "$1")"
  [ "$want" = "$got" ] && return 0
  WHY="the body's test lines differ: $(diff <(printf '%s\n' "$want") <(printf '%s\n' "$got") | grep -E '^[<>]' | tr '\t\n' '  ' | cut -c1-400)"
  return 1
}

# ---- K-03: the exit code of the run ------------------------------------------------------------------

k03_exit() {
  case "$RUN_CODE" in
    0) return 0 ;;
    missing) WHY="$DOC0101 is missing from the tree"; return 1 ;;
    *) WHY="$DOC0101 exited $RUN_CODE ($( [ "$RUN_CODE" = 1 ] && echo 'a check failed' || echo 'could not run'))"; return 1 ;;
  esac
}

# ---- K-04: a real depth-1 clone --------------------------------------------------------------------

# overlay <tree> <clone> — the tree's EKO-1-01.sh and its two helpers over the clone, so the clone
# runs the file as it is in the tree, uncommitted edits included.
overlay() {
  local f
  for f in "$DOC0101" "${HELPERS[@]}"; do
    [ -f "$1/$f" ] || { WHY="$f is missing from the tree"; return 1; }
    mkdir -p "$(dirname "$2/$f")" && cp -- "$1/$f" "$2/$f" || { WHY="cannot copy $f into the clone"; return 1; }
  done
}

# k04_depth1 <tree> <dir> — clone the tree's HEAD with --depth 1 over file:// into <dir>/clone; the
# clone must say it is shallow, else the sub-check fails rather than judge a full clone.
k04_depth1() {
  local c="$2/clone" code err shallow
  rm -rf "$2"; mkdir -p "$2" || { WHY="cannot create $2"; return 1; }
  qgit clone --quiet --depth 1 --no-tags "$(file_url "$1")" "$c" 2> "$2/clone.err" || { WHY="git clone --depth 1 failed: $(tail -n 1 "$2/clone.err")"; return 1; }
  shallow="$(git -C "$c" rev-parse --is-shallow-repository 2>&1)"
  [ "$shallow" = true ] || { WHY="the clone is not shallow (is-shallow-repository: $shallow)"; return 1; }
  overlay "$1" "$c" || return 1
  bash "$c/$DOC0101" > "$2/out" 2> "$2/err" < /dev/null; code=$?
  [ "$code" -eq 2 ] || { WHY="$DOC0101 exited $code on the depth-1 clone, not 2"; return 1; }
  err="$(cat "$2/err")"
  [[ "$err" == *"$STOP_TEXT" ]] || { WHY="stderr does not end with '$STOP_TEXT': $(tail -n 1 "$2/err" | cut -c1-160)"; return 1; }
}

# k04_unshallow <dir> — the clone k04_depth1 left, with its history fetched: the only difference.
k04_unshallow() {
  local c="$1/clone" code shallow
  [ -d "$c/.git" ] || { WHY="no depth-1 clone to unshallow"; return 1; }
  [ "$(git -C "$c" rev-parse --is-shallow-repository 2>&1)" = true ] || { WHY="the clone was not shallow before the fetch"; return 1; }
  qgit -C "$c" fetch --quiet --unshallow 2> "$1/fetch.err" || { WHY="git fetch --unshallow failed: $(tail -n 1 "$1/fetch.err")"; return 1; }
  shallow="$(git -C "$c" rev-parse --is-shallow-repository 2>&1)"
  [ "$shallow" = false ] || { WHY="the clone is still shallow ($shallow)"; return 1; }
  bash "$c/$DOC0101" > "$1/out-full" 2> "$1/err-full" < /dev/null; code=$?
  [ "$code" -eq 0 ] || { WHY="$DOC0101 exited $code on the unshallowed clone: $(tail -n 1 "$1/out-full" | cut -c1-160)"; return 1; }
}

# snapshot <file> — the repository state K-07 compares: status, refs, worktrees, stash, EKO-1-01.sh.
snapshot() {
  {
    echo '## status'; git -C "$TOP" --no-optional-locks status --porcelain --untracked-files=all
    echo '## refs'; git -C "$TOP" for-each-ref --format='%(objectname) %(refname)'
    echo '## worktrees'; git -C "$TOP" worktree list --porcelain
    echo '## stash'; git -C "$TOP" stash list
    echo '## EKO-1-01.sh'; git -C "$TOP" hash-object -- "$TOP/$DOC0101" 2>&1
  } > "$1" 2>&1
}

# ---- the runner -------------------------------------------------------------------------------

passed=0; failed=0; WHY=""
# sub <name> <detail> <function> [args] — the function sets WHY and returns non-zero on a failure.
sub() {
  local name="$1" detail="$2"; shift 2
  WHY=""
  if "$@"; then echo "ok   $name — $detail"; passed=$((passed + 1))
  else echo "FAIL $name — $detail: ${WHY:-check failed}"; failed=$((failed + 1)); fi
}

main_run() {
  local target="$TOP"
  snapshot "$WORK/before"
  mkdir -p "$WORK/run" || die "cannot create $WORK/run"
  run_0101 "$target" "$WORK/run"
  sub "$S_K01" "the ok labels of a run of $DOC0101 include each of the seven names, compared as exact strings" k01_names "$WORK/run/out"
  sub "$S_K01X" "every ok label of that run is one of the seven names" k01_extra "$WORK/run/out"
  sub "$S_K02" "seven distinct names for K-01..K-07${PR_BODY:+, byte-equal to the test lines of $PR_BODY}" k02_reference "$PR_BODY"
  sub "$S_K03" "that run of $DOC0101 exited 0" k03_exit
  sub "$S_K04" "in a throwaway clone verified shallow, $DOC0101 exits exactly 2 and its stderr ends with '$STOP_TEXT'" k04_depth1 "$target" "$WORK/k04"
  sub "$S_K04U" "the same clone after git fetch --unshallow: $DOC0101 exits 0" k04_unshallow "$WORK/k04"
  snapshot "$WORK/after"
  sub "$S_K07" "status, refs, worktrees, stash and the bytes of $DOC0101 are the same after the run" same_snapshot "$WORK/before" "$WORK/after"
  echo "EKO-1-39 doc-check: $passed passed, $failed failed"
  [ "$failed" -eq 0 ]
}

same_snapshot() {
  cmp -s "$1" "$2" && return 0
  WHY="changed: $(diff "$1" "$2" | grep -E '^[<>]' | head -n 3 | tr '\n' ' ' | cut -c1-200)"
  return 1
}

# ---- self-test ----------------------------------------------------------------------------------
# Every contrast runs on a throwaway file:// clone of this repository's HEAD, with this tree's
# EKO-1-01.sh and helpers copied over it; a mutation edits that copy only.

st_total=0; st_fail=0
st_report() {
  st_total=$((st_total + 1))
  if [ "$2" = ok ]; then echo "ok   self-test $1${3:+ — $3}"; else echo "FAIL self-test $1 — $3"; st_fail=$((st_fail + 1)); fi
}
# expect <case> <pass|fail> <must-contain|-> <must-not-contain|-> <function> [args]
expect() {
  local name="$1" want="$2" has="$3" hasnt="$4" got; shift 4
  WHY=""
  if "$@"; then got=pass; else got=fail; fi
  if [ "$got" != "$want" ]; then st_report "$name" FAIL "expected $want, got $got${WHY:+ ($WHY)}"; return; fi
  if [ "$has" != - ] && [[ "$WHY" != *"$has"* ]]; then st_report "$name" FAIL "the report does not contain '$has': $WHY"; return; fi
  if [ "$hasnt" != - ] && [[ "$WHY" == *"$hasnt"* ]]; then st_report "$name" FAIL "the report contains '$hasnt': $WHY"; return; fi
  st_report "$name" ok "$WHY"
}

# mutate <file> <old> <new> — replace the first occurrence of a fixed string, or stop (exit 2).
mutate() {
  local text
  text="$(cat "$1"; printf x)"; text="${text%x}"
  [[ "$text" == *"$2"* ]] || die "self-test: the text to mutate is not in $1: $2"
  printf '%s' "${text/"$2"/"$3"}" > "$1" || die "self-test: cannot write $1"
}

# synthetic <file> <line>... — an EKO-1-01.sh output made of the given lines.
synthetic() { local f="$1"; shift; printf '%s\n' "$@" > "$f"; }
okl() { printf 'ok   %s — synthetic detail' "$1"; }

self_test() {
  local st="$WORK/st" clone f i all=() n1 n3 n5 n7
  n1="${REF_NAMES[0]}"; n3="${REF_NAMES[2]}"; n5="${REF_NAMES[4]}"; n7="${REF_NAMES[6]}"
  snapshot "$WORK/before"
  mkdir -p "$st" || die "cannot create $st"

  # Label comparison over synthetic outputs (K-01 edges, G-5 A).
  for i in 0 1 2 3 4 5 6; do all+=("$(okl "${REF_NAMES[$i]}")"); done
  f="$st/syn"
  synthetic "$f" "${all[@]}" 'EKO-1-01 doc-checks: 7 passed, 0 failed, 0 skipped'
  expect "K-01 the seven labels pass" pass - - k01_names "$f"
  expect "K-01 G-5 the seven labels have no extra" pass - - k01_extra "$f"
  : > "$f"
  expect "K-01 (Nothing) no output fails, naming all seven" fail "$n7" - k01_names "$f"
  k01_names "$st/absent" && st_report "K-01 (Nothing) a missing output fails" FAIL "passed" || st_report "K-01 (Nothing) a missing output fails" ok
  synthetic "$f" "${all[@]:0:2}" "${all[@]:3}" "FAIL ${n3} — synthetic: failed"
  expect "K-01 (One) one unmatched name is the only one reported" fail "$n3" "$n1" k01_names "$f"
  synthetic "$f" "${all[@]:1}" "$(okl "$n1 extra")"
  expect "K-01 (Text) an appended word does not match" fail "$n1" - k01_names "$f"
  expect "K-01 G-5 an appended word is an extra label" fail "$n1 extra" - k01_extra "$f"
  synthetic "$f" "${all[@]:0:6}" "$(okl "${n7% *}")"
  expect "K-01 (Text) a dropped last word does not match" fail "$n7" - k01_names "$f"
  synthetic "$f" "${all[@]:0:4}" "$(okl 'QA document checks K-051235, K-05-4, K-05-4f, K-05-fe')" "${all[@]:5}"
  expect "K-01 (Text) parentheses are literal, not a pattern" fail "$n5" - k01_names "$f"
  synthetic "$f" "${all[@]:1}" "ok   $n1  — trailing space in the label"
  expect "K-01 (Text) a trailing space does not match" fail "$n1" - k01_names "$f"
  synthetic "$f" "${all[@]:1}" "ok    $n1 — four spaces after ok"
  expect "K-01 (Text) a wider separator does not match" fail "$n1" - k01_names "$f"
  synthetic "$f" "${all[@]}" "${all[@]}" "${all[@]}"
  expect "K-01 (Twins) repeated labels pass" pass - - k01_names "$f"
  synthetic "$f" "${all[6]}" "${all[5]}" "${all[4]}" "${all[3]}" "${all[2]}" "${all[1]}" "${all[0]}"
  expect "K-01 (Order) reversed labels pass" pass - - k01_names "$f"
  synthetic "$f" "${all[@]}" "$(okl 'QA document check K-08 (not quoted by PR #30)')"
  expect "K-01 (Limit) G-5 an eighth label fails" fail 'K-08 (not quoted' - k01_extra "$f"
  expect "K-01 (Limit) an eighth label does not hide the seven" pass - - k01_names "$f"

  # K-02 against a body in PR #30's format: equal, then one word of one name changed.
  f="$st/body"
  { echo '## Definition of done — proof'; for i in 0 1 2 3 4 5 6; do printf -- '- %s — test: %s\r\n' "${REF_IDS[$i]}" "${REF_NAMES[$i]}"; done; } > "$f"
  expect "K-02 a body with the seven names passes, CR stripped" pass - - k02_reference "$f"
  mutate "$f" 'template sections' 'template headings'
  expect "K-02 a body with one word changed fails on that name only" fail 'template headings' "$n1" k02_reference "$f"
  expect "K-02 no body: the list itself is seven distinct names" pass - - k02_reference ""

  # Real runs in a throwaway clone.
  clone="$st/clone"
  qgit clone --quiet --single-branch --no-tags "$(file_url "$TOP")" "$clone" 2>"$st/clone.err" || die "self-test: cannot clone $TOP: $(tail -n 1 "$st/clone.err")"
  for f in "$DOC0101" "${HELPERS[@]}"; do cp -- "$TOP/$f" "$clone/$f" || die "self-test: cannot copy $f"; done
  cp -- "$clone/$DOC0101" "$st/pristine" || die "self-test: cannot keep a pristine copy"
  local p="$clone/$DOC0101"
  restore() { cp -- "$st/pristine" "$p" || die "self-test: cannot restore the clone's EKO-1-01.sh"; }
  case_run() { rm -rf "$st/run"; mkdir -p "$st/run"; run_0101 "$clone" "$st/run"; }

  case_run
  expect "baseline K-01 every name labels an ok line" pass - - k01_names "$st/run/out"
  expect "baseline K-01 no extra label" pass - - k01_extra "$st/run/out"
  expect "baseline K-03 exit 0" pass - - k03_exit
  expect "baseline K-04 depth-1 clone exits 2" pass - - k04_depth1 "$clone" "$st/k04"
  expect "baseline K-04 unshallowed clone exits 0" pass - - k04_unshallow "$st/k04"

  mutate "$p" "L05='$n5'" "# $n5"$'\n'"L05='QA document checks K-05 (registers)'"
  case_run
  expect "M-EC-b (L05 renamed, its name in a comment) K-01 fails naming it" fail "$n5" "$n1" k01_names "$st/run/out"
  expect "M-EC-b K-01 G-5 the renamed label is an extra" fail 'K-05 (registers)' - k01_extra "$st/run/out"
  expect "M-EC-b EKO-1-01.sh's own guard still exits 0" pass - - k03_exit
  restore

  mutate "$p" "L03='QA document check K-03 (template sections" "L03='QA document check K-03 (template headings"
  case_run
  expect "M-EC-a (one word of L03) K-01 fails naming PR #30's L03 name" fail "$n3" - k01_names "$st/run/out"
  # QA contrast (EKO-1-39/M-4): this file, run whole beside the renamed L03, must still compare
  # against PR #30's name; a reference list read from EKO-1-01.sh at load time would follow the
  # rename and pass. The functions above cannot see that, as they share this run's list.
  whole_run() {
    local code
    cp -- "${BASH_SOURCE[0]}" "$clone/tests/doc-checks/EKO-1-39.sh" || die "self-test: cannot copy this file into the clone"
    bash "$clone/tests/doc-checks/EKO-1-39.sh" > "$st/whole.out" 2>&1 < /dev/null; code=$?
    WHY="exit $code; $(grep -F -- "FAIL $S_K01 — " "$st/whole.out" | cut -c1-400)"
    [ "$code" -eq 0 ]
  }
  expect "M-EC-a whole run: the reference list does not follow the renamed L03 (K-02)" fail "'$n3'" - whole_run
  restore

  mutate "$p" '    file="$(adr_file "$n")"' '    file="$(adr_file "$n")"; [ "$n" != 2 ] || file=""'
  case_run
  expect "exit-1 sub-check (ADR-0002 citation check fails) K-01 still passes" pass - - k01_names "$st/run/out"
  expect "exit-1 sub-check K-03 fails reporting exit 1" fail 'exited 1' - k03_exit
  restore

  mutate "$p" 'BASE="$PIN_BASE"; HEAD_REV=' 'die "self-test stop"'$'\n''BASE="$PIN_BASE"; HEAD_REV='
  case_run
  expect "exit-2 (die before any check) K-01 fails, naming all seven" fail "$n7" - k01_names "$st/run/out"
  expect "exit-2 K-03 fails reporting exit 2" fail 'exited 2' - k03_exit
  restore

  mutate "$p" "$STOP_TEXT\" >&2; exit 2; }" "$STOP_TEXT\" >&2; exit 0; }"
  case_run
  expect "M-14 (die exits 0) K-01 passes on the full clone" pass - - k01_names "$st/run/out"
  expect "M-14 K-03 passes on the full clone" pass - - k03_exit
  expect "M-14 K-04 fails on its own" fail 'exited 0' - k04_depth1 "$clone" "$st/k04"
  # QA contrast (EKO-1-39/M-11b): taken while the mutation is applied, so a mutation written into
  # this repository and restored before the end, which the closing K-07 case cannot see, fails here.
  snapshot "$WORK/mid"
  expect "K-07 the repository is untouched while the M-14 copy is mutated" pass - - same_snapshot "$WORK/before" "$WORK/mid"
  restore

  mutate "$p" "$STOP_TEXT\" >&2; exit 2; }" "$STOP_TEXT\" >&2; exit 1; }"
  expect "die exits 1: K-04 fails (exactly 2)" fail 'exited 1' - k04_depth1 "$clone" "$st/k04"
  restore

  rm -f -- "$p"
  case_run
  expect "missing EKO-1-01.sh: K-01 fails" fail "$n1" - k01_names "$st/run/out"
  expect "missing EKO-1-01.sh: K-03 fails" fail 'missing' - k03_exit
  restore

  snapshot "$WORK/after"
  expect "K-07 the repository is untouched by the self-test" pass - - same_snapshot "$WORK/before" "$WORK/after"
  echo "EKO-1-39 self-test: $((st_total - st_fail)) of $st_total passed"
  [ "$st_fail" -eq 0 ]
}

if [ "$SELF_TEST" -eq 1 ]; then self_test; else main_run; fi
