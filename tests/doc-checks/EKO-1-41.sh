#!/usr/bin/env bash
# EKO-1-41 — proves that the two sub-check names of tests/doc-checks/EKO-1-39.sh that carry an
# apostrophe link in scripts/evidence-chain.sh as a real run prints them, that the link stands on
# EKO-1-39.sh's own constants and on nothing else, that the printed names are those of 4b7c2e4,
# and that the frozen records stay as they were (Issue #235, criteria K-01..K-04).
#
#   bash tests/doc-checks/EKO-1-41.sh --issue <issue-230.md> --pr <pr-234.md> --pr30 <pr-30.md>
#   bash tests/doc-checks/EKO-1-41.sh ... --range origin/main...HEAD   # adds the K-04 diff check
#   bash tests/doc-checks/EKO-1-41.sh --k05-search                     # prints the K-05 search hits
#   bash tests/doc-checks/EKO-1-41.sh --self-test                      # built-in contrasts, offline
#
#   gh issue view 230 --json body --jq .body > issue-230.md          # the bodies the run expects
#   gh pr view 234 --json body --jq .body > pr-234.md
#   gh pr view 30 --json body --jq .body > pr-30.md
#
# Output. One line per sub-check, "ok   <name> — <detail>" or "FAIL <name> — <detail>: <why>".
# Exit codes: 0 = every sub-check passed, 1 = at least one failed, 2 = the check could not run (a
# bad argument, a missing body, 4b7c2e4 not in this repository's history) — never read 2 as a pass.
#
# The trap this file must not fall into (Issue #235 K-01): the chain greps every tracked test file
# for a fixed string, so this file never holds the two printed names. It takes them from the ok
# lines of two real runs of EKO-1-39.sh, as the only labels there with an apostrophe, and its own
# M-1 sub-check reruns the chain on a clone that carries this file too.
#
# Writes. Only under a temporary directory outside the repository; the M-1 and self-test changes
# are made in throwaway clones or throwaway repositories.
#
# What this proves: that the chain finds the two names and loses them on a one-character change or
# on the 4b7c2e4 quoting of lines 46-47; that the run's labels equal 4b7c2e4's constants in the
# order the run prints them; that the PR #234 chain is clean; the K-04 diff and record hashes.
# It does not prove the self-test case names of EKO-1-39.sh (recorded by QA), the K-05
# classification (judged by the human), or anything under Linux bash.

set -uo pipefail

BASE_REV='4b7c2e49ef9a2d9337c6287caa5606c1d3c538dd'
DOC0139='tests/doc-checks/EKO-1-39.sh'
CHAIN='scripts/evidence-chain.sh'
SUMMARY_0139='EKO-1-39 doc-check: 7 passed, 0 failed'
# sha256 of the two frozen bodies, recorded at gate 1 (Issue #235, Analyst notes).
HASH_PR234='fe402683e7e984a53ed12f11104bd1223f9f18d3482f6fb076a0d9b2351fa042'
HASH_IS230='0452ace8df0dd0a0832bd01f6a3b629997e7f06deba24ec5a1cd8ba73e7399b9'
NOT_FOUND='which no test file contains'

S_K01A='EKO-1-41 K-01 the two apostrophe names are printed by EKO-1-39.sh'
S_K01='EKO-1-41 K-01 the printed names link and the chain is clean'
S_K01C1='EKO-1-41 K-01 contrast PR #30s unlinks the K-01 line only'
S_K01C2='EKO-1-41 K-01 contrast U+2019 apostrophe unlinks the K-02 line only'
S_K01M='EKO-1-41 K-01 M-1 the 4b7c2e4 quoting of lines 46-47 unlinks both names'
S_K02='EKO-1-41 K-02 printed labels equal the 4b7c2e4 constants'
S_K03='EKO-1-41 K-03 the PR #234 chain is clean'
S_K04='EKO-1-41 K-04 the diff stays inside the allow-list'
S_K04H='EKO-1-41 K-04 Issue #230 and PR #234 bodies hash as at gate 1'

die() { echo "EKO-1-41 doc-check: $* — the check did not run" >&2; exit 2; }

ISSUE=""; PR=""; PR30=""; RANGE=""; MODE=run
while [ $# -gt 0 ]; do
  case "$1" in
    --issue|--pr|--pr30|--range)
      [ $# -ge 2 ] || die "$1 needs a value"
      case "$1" in --issue) ISSUE="$2" ;; --pr) PR="$2" ;; --pr30) PR30="$2" ;; --range) RANGE="$2" ;; esac
      shift 2 ;;
    --self-test) MODE=self; shift ;;
    --k05-search) MODE=k05; shift ;;
    *) die "unknown argument '$1' (usage: $0 --issue <f> --pr <f> --pr30 <f> [--range <a>...<b>] | --k05-search | --self-test)" ;;
  esac
done
if [ "$MODE" = run ]; then
  for f in "$ISSUE" "$PR" "$PR30"; do [ -n "$f" ] && [ -r "$f" ] || die "--issue, --pr and --pr30 each need a readable file"; done
elif [ -n "$ISSUE$PR$PR30$RANGE" ]; then
  die "--$MODE takes no other argument"
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || die "cannot enter the repository root"
TOP="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null)" || die "not a git repository"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

WORK="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$WORK"' EXIT
[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" != "$TOP" ] || die "the temporary directory $WORK lies inside the repository"

file_url() { case "$1" in /*) printf 'file://%s' "$1" ;; *) printf 'file:///%s' "$1" ;; esac; }
qgit() { git -c core.autocrlf=false -c advice.detachedHead=false -c user.name=qa -c user.email=qa@example.invalid "$@"; }

# ---- reading runs ------------------------------------------------------------------------------

# ok_labels <file> — LABELS: the text of each ok line after "ok" and three spaces, up to " — "
# (the rule of EKO-1-39.sh's ok_labels).
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

# apostrophe_names <plain run> <pr-body run> — N_K01: the only plain-run label holding an ASCII
# apostrophe; N_K02: the only pr-body-run label holding one that the plain run does not print.
N_K01=""; N_K02=""
apostrophe_names() {
  local l found=() plain=()
  N_K01=""; N_K02=""
  ok_labels "$1"; plain=("${LABELS[@]}")
  for l in "${plain[@]}"; do [[ "$l" != *"'"* ]] || found+=("$l"); done
  [ "${#found[@]}" -eq 1 ] || { WHY="${#found[@]} plain-run labels hold an apostrophe, not 1"; return 1; }
  N_K01="${found[0]}"; found=()
  ok_labels "$2"
  for l in "${LABELS[@]}"; do [[ "$l" != *"'"* ]] || [ "$l" = "$N_K01" ] || found+=("$l"); done
  [ "${#found[@]}" -eq 1 ] || { WHY="${#found[@]} new pr-body-run labels hold an apostrophe, not 1"; N_K01=""; return 1; }
  N_K02="${found[0]}"
  WHY="${#plain[@]} and ${#LABELS[@]} ok lines read"
}

# ---- the chain -----------------------------------------------------------------------------------

# body_with <pr body> <k01 name> <k02 name> <out> — the PR body with every K-01 and K-02 test line
# of "## Definition of done" replaced by one line each naming the given names. The names go through
# ENVIRON, never awk -v, which would read a backslash as an escape.
body_with() {
  N1="$2" N2="$3" awk '
    /^## / { sec = index($0, "## Definition of done") == 1; print; if (sec) { print "- K-01 — test: " ENVIRON["N1"]; print "- K-02 — test: " ENVIRON["N2"] }; next }
    sec && /^[-*][[:space:]]+K-0[12][[:space:]]+—[[:space:]]+test:/ { next }
    { print }' "$1" > "$4"
}

# chain_out <repo> <issue> <body> <out> — CHAIN_CODE: the exit code of the repo's own chain.
CHAIN_CODE=""
chain_out() {
  bash "$1/$CHAIN" chain "$2" "$3" --repo "$1" > "$4" 2>&1 < /dev/null; CHAIN_CODE=$?
}

# not_found_ids <out> — the criterion ids of the "which no test file contains" findings, one line.
not_found_ids() { grep -F -- "$NOT_FOUND" "$1" | awk '{ print $2 }' | sort | tr '\n' ' ' | sed 's/ $//'; }

# chain_clean <repo> <issue> <body> — the chain exits 0, says clean and finds every name.
chain_clean() {
  local o="$WORK/chain.$RANDOM"
  chain_out "$1" "$2" "$3" "$o"
  WHY="exit $CHAIN_CODE; $(tail -n 1 "$o" | cut -c1-160)"
  [ "$CHAIN_CODE" -eq 0 ] && [[ "$(tail -n 1 "$o")" == "evidence-chain: clean"* ]] && ! grep -qF -- "$NOT_FOUND" "$o" && return 0
  WHY="$WHY; unlinked: $(not_found_ids "$o")"
  return 1
}

# chain_unlinked <repo> <issue> <body> <ids> — exactly these ids are unlinked, and nothing else is
# found: the chain's only findings are the "which no test file contains" lines for <ids>.
chain_unlinked() {
  local o="$WORK/chain.$RANDOM" got n
  chain_out "$1" "$2" "$3" "$o"
  got="$(not_found_ids "$o")"; n="$(grep -c '^FINDING' "$o" || true)"
  WHY="exit $CHAIN_CODE; unlinked: ${got:-none}; $n finding(s)"
  [ "$CHAIN_CODE" -eq 1 ] && [ "$got" = "$4" ] && [ "$n" -eq "$(wc -w <<< "$4")" ]
}

# ---- K-01 M-1: a clone of the tree with lines 46-47 back in their 4b7c2e4 bytes ----------------

# tree_clone <dir> — a file:// clone of HEAD with this tree's tests/doc-checks/*.sh copied over it
# and added to the index (the chain reads git ls-files), this file included.
tree_clone() {
  qgit clone --quiet --no-tags "$(file_url "$TOP")" "$1" 2> "$WORK/clone.err" || die "cannot clone $TOP: $(tail -n 1 "$WORK/clone.err")"
  cp -- "$TOP"/tests/doc-checks/*.sh "$1/tests/doc-checks/" || die "cannot copy the doc-checks into the clone"
  qgit -C "$1" add -- tests/doc-checks || die "cannot add the doc-checks in the clone"
}

# requote <file> <base lines file> — lines 46-47 of <file> replaced by <base lines file>; the two
# lines must be the S_K01X and S_K02 constants before, and differ after.
requote() {
  local f="$1" a b
  a="$(sed -n '46p' "$f")"; b="$(sed -n '47p' "$f")"
  [[ "$a" == S_K01X=* && "$b" == S_K02=* ]] || { WHY="lines 46-47 are not S_K01X and S_K02"; return 1; }
  { sed -n '1,45p' "$f"; cat "$2"; sed -n '48,$p' "$f"; } > "$WORK/requoted" && cp -- "$WORK/requoted" "$f" || { WHY="cannot rewrite $f"; return 1; }
  [ "$(sed -n '46,47p' "$f")" != "$a"$'\n'"$b" ] || { WHY="lines 46-47 already had the 4b7c2e4 bytes"; return 1; }
}

k01_m1() {
  local c="$WORK/m1"
  rm -rf "$c"; tree_clone "$c"
  git -C "$TOP" show "$BASE_REV:$DOC0139" | sed -n '46,47p' > "$WORK/base-46-47" || die "cannot read $DOC0139 at $BASE_REV"
  requote "$c/$DOC0139" "$WORK/base-46-47" || return 1
  chain_unlinked "$c" "$ISSUE" "$WORK/body" "K-01 K-02"
}

# ---- K-02: the printed labels against 4b7c2e4's constants ----------------------------------------

# labels_equal <run output> <expected labels file> — the ok labels, in order, byte-equal to the file,
# and the run's last line is the 7-passed summary.
labels_equal() {
  ok_labels "$1"
  printf '%s\n' "${LABELS[@]}" > "$1.labels"
  [ "$(tail -n 1 "$1")" = "$SUMMARY_0139" ] || { WHY="the run ends '$(tail -n 1 "$1" | cut -c1-120)'"; return 1; }
  cmp -s "$1.labels" "$2" && { WHY="${#LABELS[@]} labels"; return 0; }
  WHY="differ: $(diff "$2" "$1.labels" | grep -E '^[<>]' | tr '\n' ' ' | cut -c1-300)"
  return 1
}

# k02_labels — the 4b7c2e4 constants, evaluated from that commit's file, in the order main_run
# prints them; the --pr-body run prints S_K02 where the plain run prints S_K02S.
k02_labels() {
  local src="$WORK/base-0139" w
  git -C "$TOP" show "$BASE_REV:$DOC0139" > "$src" 2>/dev/null || die "cannot read $DOC0139 at $BASE_REV"
  ( set -u; eval "$(grep -E '^S_K[0-9]+[A-Z]*=' "$src")"
    printf '%s\n' "$S_K01" "$S_K01X" "$S_K02S" "$S_K03" "$S_K04" "$S_K04U" "$S_K07" > "$WORK/want-plain"
    printf '%s\n' "$S_K01" "$S_K01X" "$S_K02" "$S_K03" "$S_K04" "$S_K04U" "$S_K07" > "$WORK/want-prb" ) || die "cannot read the $BASE_REV constants"
  ! grep -qx '' "$WORK/want-plain" "$WORK/want-prb" || die "an S_K constant is empty at $BASE_REV"
  labels_equal "$WORK/plain.out" "$WORK/want-plain" || { WHY="plain run: $WHY"; return 1; }
  w="$WHY"
  labels_equal "$WORK/prb.out" "$WORK/want-prb" || { WHY="--pr-body run: $WHY"; return 1; }
  WHY="plain $w, --pr-body $WHY"
}

# ---- K-04 ------------------------------------------------------------------------------------------

# k04_range <repo> <a...b> — every changed path is on the allow-list: EKO-1-39.sh changed on lines
# 46-47 only, EKO-1-41.sh, cost rows only added, and docs/PLAN.md only added lines that open with
# the EKO-1-41 entry (the plan-number reservation, task.md step 2; K-04 does not name it — the
# detail says so whenever it is accepted).
k04_range() {
  local r="$1" range="$2" p bad="" note="" hunks plus first
  git -C "$r" diff --name-only "$range" > "$WORK/k04.names" 2> "$WORK/k04.err" || die "git diff $range failed: $(tail -n 1 "$WORK/k04.err")"
  while IFS= read -r p; do
    case "$p" in
      "$DOC0139")
        hunks="$(git -C "$r" diff -U0 "$range" -- "$p" | grep '^@@' | sed 's/ @@.*/ @@/' | sort -u | tr '\n' ' ')"
        [ "$hunks" = "@@ -46,2 +46,2 @@ " ] || bad="$bad$p (hunks: $hunks); " ;;
      tests/doc-checks/EKO-1-41.sh) ;;
      docs/cost-register/*.json)
        ! git -C "$r" diff "$range" -- "$p" | grep -qE '^-([^-]|$)' || bad="$bad$p (lines removed); " ;;
      docs/PLAN.md)
        git -C "$r" diff -U0 "$range" -- "$p" > "$WORK/k04.plan"
        plus="$(grep -cE '^\+([^+]|$)' "$WORK/k04.plan" || true)"
        first="$(grep -m 1 -E '^\+([^+]|$)' "$WORK/k04.plan")"
        if grep -qE '^-([^-]|$)' "$WORK/k04.plan" || [ "$(grep -c '^@@' "$WORK/k04.plan")" -ne 1 ] || [[ "$first" != '+- [ ] **EKO-1-41** '* ]]; then
          bad="$bad$p (not only the EKO-1-41 entry added); "
        else note="; $p: $plus lines added, the EKO-1-41 reservation (not named by K-04)"; fi ;;
      *) bad="$bad$p; " ;;
    esac
  done < "$WORK/k04.names"
  WHY="$(wc -l < "$WORK/k04.names" | tr -d ' ') paths$note"
  [ -z "$bad" ] || { WHY="outside the allow-list: ${bad%; }"; return 1; }
}

k04_hashes() {
  local a b
  a="$(sha256sum < "$1" | cut -d' ' -f1)"; b="$(sha256sum < "$2" | cut -d' ' -f1)"
  WHY="Issue #230 $a, PR #234 $b"
  [ "$a" = "$HASH_IS230" ] && [ "$b" = "$HASH_PR234" ]
}

# ---- K-05: the search for printed names written in another form than they print ------------------

# The written forms whose bytes differ from the printed bytes (Issue #235 K-05 boundary).
k05_patterns() {
  printf '%s\n' "'\"'\"'" "[\\]'" '[\]"' '[\][\]' '[\][$]' "[\$]'"
}
# k05_search <repo> — "file:line:text" for each tracked doc-check line holding one of the forms.
k05_search() {
  k05_patterns > "$WORK/k05.pat"
  ( cd "$1" && git ls-files tests/doc-checks/ | tr '\n' '\0' | xargs -0 grep -HnE -f "$WORK/k05.pat" -- 2>/dev/null || true )
}

# ---- the runner --------------------------------------------------------------------------------

passed=0; failed=0; WHY=""
sub() {
  local name="$1" detail="$2"; shift 2
  WHY=""
  if "$@"; then echo "ok   $name — $detail${WHY:+ ($WHY)}"; passed=$((passed + 1))
  else echo "FAIL $name — $detail: ${WHY:-check failed}"; failed=$((failed + 1)); fi
}

run_0139() {
  bash "$TOP/$DOC0139" > "$WORK/plain.out" 2>&1 < /dev/null
  bash "$TOP/$DOC0139" --pr-body "$PR30" > "$WORK/prb.out" 2>&1 < /dev/null
}

k01_link() { body_with "$PR" "$N_K01" "$N_K02" "$WORK/body"; chain_clean "$TOP" "$ISSUE" "$WORK/body"; }
k01_contrast() {  # k01_contrast <k01 name> <k02 name> <id expected unlinked>
  body_with "$PR" "$1" "$2" "$WORK/body-c"; chain_unlinked "$TOP" "$ISSUE" "$WORK/body-c" "$3"
}
have_names() { [ -n "$N_K01" ] && [ -n "$N_K02" ] || { WHY="no names were read from the runs"; return 1; }; }

main_run() {
  git -C "$TOP" cat-file -e "$BASE_REV^{commit}" 2>/dev/null || die "$BASE_REV is not in this repository's history (a shallow clone?)"
  run_0139
  sub "$S_K01A" "the only apostrophe label of a plain run and the only new one of a --pr-body run of $DOC0139" apostrophe_names "$WORK/plain.out" "$WORK/prb.out"
  local q="'" r=$'’'
  sub "$S_K01" "PR #234's body with its K-01/K-02 test lines replaced by those two labels: no '$NOT_FOUND', chain clean" eval 'have_names && k01_link'
  sub "$S_K01C1" "'PR #30${q}s' written 'PR #30s' in the K-01 name only" eval 'have_names && k01_contrast "${N_K01/"#30${q}s"/"#30s"}" "$N_K02" K-01'
  sub "$S_K01C2" "the K-02 name's apostrophe written as U+2019 only" eval 'have_names && k01_contrast "$N_K01" "${N_K02//"$q"/"$r"}" K-02'
  sub "$S_K01M" "a clone of HEAD with this tree's doc-checks (this file included), lines 46-47 of $DOC0139 from $BASE_REV" eval 'have_names && k01_m1'
  sub "$S_K02" "the ok labels of both runs, in order, against the $BASE_REV constants; both runs end '$SUMMARY_0139'" k02_labels
  sub "$S_K03" "Issue #230 and PR #234 as merged, chained over this tree" chain_clean "$TOP" "$ISSUE" "$PR"
  [ -z "$RANGE" ] || sub "$S_K04" "git diff --name-only $RANGE" k04_range "$TOP" "$RANGE"
  sub "$S_K04H" "sha256 of the given bodies against the gate-1 record" k04_hashes "$ISSUE" "$PR"
  local tail=""; [ -n "$RANGE" ] || tail="; the K-04 diff was not run (no --range)"
  echo "EKO-1-41 doc-check: $passed passed, $failed failed$tail"
  [ "$failed" -eq 0 ]
}

# ---- self-test -------------------------------------------------------------------------------------
# Offline: a throwaway repository with this tree's evidence-chain.sh and synthetic names in the
# shape of the real ones (an apostrophe, written double-quoted), never the real names.

st_total=0; st_fail=0
expect() {  # expect <case> <pass|fail> <must-contain|-> <function> [args]
  local name="$1" want="$2" has="$3" got; shift 3
  WHY=""
  if "$@"; then got=pass; else got=fail; fi
  st_total=$((st_total + 1))
  if [ "$got" != "$want" ]; then echo "FAIL self-test $name — expected $want, got $got${WHY:+ ($WHY)}"; st_fail=$((st_fail + 1)); return; fi
  if [ "$has" != - ] && [[ "$WHY" != *"$has"* ]]; then echo "FAIL self-test $name — the report does not contain '$has': $WHY"; st_fail=$((st_fail + 1)); return; fi
  echo "ok   self-test $name${WHY:+ — $WHY}"
}

st_commit() { qgit -C "$1" add -A && qgit -C "$1" commit --quiet -m "$2" || die "self-test: cannot commit in $1"; }

self_test() {
  local st="$WORK/st" r q="'" a b
  r="$st/repo"; mkdir -p "$r/scripts" "$r/tests/doc-checks" "$r/docs/cost-register" || die "cannot create $r"
  qgit init --quiet "$r" || die "self-test: git init failed"
  cp -- "$TOP/$CHAIN" "$r/$CHAIN" || die "self-test: cannot copy $CHAIN"
  a="ST-1 K-01 no label outside Q${q}s list"; b="ST-1 K-02 the list is Q${q}s names"
  { for i in $(seq 1 45); do echo "# line $i"; done
    printf 'S_K01X="%s"\nS_K02="%s"\n' "$a" "$b"; echo '# line 48'; } > "$r/$DOC0139"
  { echo '# plan'; echo '- [x] **EKO-1-39** — the frozen entry.'; } > "$r/docs/PLAN.md"
  echo '{"row":1}' > "$r/docs/cost-register/row-1.json"
  st_commit "$r" base
  ISSUE="$st/issue.md"; PR="$st/pr.md"
  { echo '### Acceptance criteria'; echo '<!-- criteria:start -->'
    for k in K-01 K-02; do printf '### %s — claim\n**Contrast:** c\n**Mutation that must kill it:** m\n**Judged by:** test\n' "$k"; done
    echo '<!-- criteria:end -->'; } > "$ISSUE"
  { echo '## Definition of done — proof'; echo '- K-01 — test: # line 3'; echo '- K-02 — test: # line 4'
    echo '## Mutation'; echo '- K-01 — removed: x — result: killed, 1 test failed'; echo '- K-02 — removed: y — result: killed, 1 test failed'; } > "$PR"

  # Name extraction from synthetic runs.
  printf 'ok   ST plain — d\nok   %s — d\nok   ST shape — d\n' "$a" > "$st/plain.out"
  printf 'ok   ST plain — d\nok   %s — d\nok   %s — d\n' "$a" "$b" > "$st/prb.out"
  expect "K-01 one apostrophe label per run is read" pass "3 and 3" apostrophe_names "$st/plain.out" "$st/prb.out"
  [ "$N_K01" = "$a" ] && [ "$N_K02" = "$b" ] && echo "ok   self-test K-01 the names read are the printed ones" || { echo "FAIL self-test K-01 the names read are the printed ones — got '$N_K01' / '$N_K02'"; st_fail=$((st_fail + 1)); }
  st_total=$((st_total + 1))
  printf 'ok   ST plain — d\nok   %s — d\nok   ST it%ss — d\n' "$a" "$q" > "$st/plain2.out"
  expect "K-01 (Twins) two apostrophe labels in the plain run fail" fail "2 plain-run" apostrophe_names "$st/plain2.out" "$st/prb.out"
  expect "K-01 (Nothing) no apostrophe label in the pr-body run fails" fail "0 new" apostrophe_names "$st/plain.out" "$st/plain.out"

  # The chain over the synthetic repository.
  body_with "$PR" "$a" "$b" "$st/body"
  expect "K-01 the double-quoted names link" pass "clean" chain_clean "$r" "$ISSUE" "$st/body"
  body_with "$PR" "${a/"Q${q}s"/"Qs"}" "$b" "$st/body-c1"
  expect "K-01 (Text) one character changed in the K-01 name unlinks K-01 only" pass "unlinked: K-01;" chain_unlinked "$r" "$ISSUE" "$st/body-c1" "K-01"
  expect "K-01 (Text) that body is not clean" fail "K-01" chain_clean "$r" "$ISSUE" "$st/body-c1"
  body_with "$PR" "${a% *}" "$b" "$st/body-t"
  expect "K-01 (Limit) a truncated name still links, so it is no contrast" pass "clean" chain_clean "$r" "$ISSUE" "$st/body-t"
  { echo '## Definition of done — proof'; echo '- K-01 — test: one'; echo '- K-02 — test: two'; echo '- K-03 — test: kept'; echo '## Other'; echo '- K-01 — test: outside'; } > "$st/pr-shape.md"
  printf '%s\n' '## Definition of done — proof' '- K-01 — test: n\1' '- K-02 — test: n2' '- K-03 — test: kept' '## Other' '- K-01 — test: outside' > "$st/shape.want"
  shape_ok() { body_with "$st/pr-shape.md" 'n\1' 'n2' "$st/shape.out"; WHY="$(tr '\n' '|' < "$st/shape.out")"; cmp -s "$st/shape.out" "$st/shape.want"; }
  expect "K-01 the body keeps the other lines and a backslash in a name" pass - shape_ok

  # M-1 on the synthetic repository: the escaped form of the two lines.
  printf "S_K01X='%s'\nS_K02='%s'\n" "${a//"$q"/"$q\"$q\"$q"}" "${b//"$q"/"$q\"$q\"$q"}" > "$st/escaped"
  cp -r "$r" "$st/m1"
  expect "M-1 requote rewrites lines 46-47" pass - requote "$st/m1/$DOC0139" "$st/escaped"
  expect "M-1 (requote twice) lines already in the escaped form are refused" fail "already had" requote "$st/m1/$DOC0139" "$st/escaped"
  expect "M-1 the escaped form unlinks both names" pass "unlinked: K-01 K-02;" chain_unlinked "$st/m1" "$ISSUE" "$st/body" "K-01 K-02"
  printf '# a copy: %s\n' "$a" > "$st/m1/tests/doc-checks/EKO-9-99.sh"; qgit -C "$st/m1" add -- tests/doc-checks/EKO-9-99.sh
  expect "M-1 (the K-01 trap) a literal copy in another test file keeps that name linked" fail "unlinked: K-02;" chain_unlinked "$st/m1" "$ISSUE" "$st/body" "K-01 K-02"
  printf '# a copy: %s\n' "$a" > "$st/m1/docs/notes.md"; qgit -C "$st/m1" rm --quiet --cached -- tests/doc-checks/EKO-9-99.sh; rm -f -- "$st/m1/tests/doc-checks/EKO-9-99.sh"; qgit -C "$st/m1" add -- docs/notes.md
  expect "M-1 a copy outside the test files does not link" pass "unlinked: K-01 K-02;" chain_unlinked "$st/m1" "$ISSUE" "$st/body" "K-01 K-02"

  # K-02 label comparison.
  printf 'ok   %s — d\nok   %s — d\n%s\n' "$a" "$b" "$SUMMARY_0139" > "$st/run.out"
  printf '%s\n' "$a" "$b" > "$st/want"
  expect "K-02 equal labels pass" pass "2 labels" labels_equal "$st/run.out" "$st/want"
  printf 'ok   %s — d\nok   %s — d\n%s\n' "${a/"${q}s"/"\\${q}s"}" "$b" "$SUMMARY_0139" > "$st/run2.out"
  expect "K-02 (M-2) a printed backslash before the apostrophe fails on that name" fail "\\${q}s" labels_equal "$st/run2.out" "$st/want"
  printf 'ok   %s — d\nok   %s — d\n%s\n' "${a/"$q"/}" "$b" "$SUMMARY_0139" > "$st/run3.out"
  expect "K-02 (M-2) a dropped apostrophe fails on that name" fail "Qs list" labels_equal "$st/run3.out" "$st/want"
  printf 'ok   %s — d\nok   %s — d\nEKO-1-39 doc-check: 6 passed, 1 failed\n' "$a" "$b" > "$st/run4.out"
  expect "K-02 a run that does not end 7 passed fails" fail "6 passed" labels_equal "$st/run4.out" "$st/want"

  # K-04 over a branch of the synthetic repository.
  local base; base="$(git -C "$r" rev-parse HEAD)"
  k04_case() {  # k04_case <name> <pass|fail> <must-contain|-> <edit command>
    local c="$st/k04"; rm -rf "$c"; cp -r "$r" "$c"
    ( cd "$c" && eval "$4" ) || die "self-test: the edit for '$1' failed"
    st_commit "$c" change
    expect "$1" "$2" "$3" k04_range "$c" "$base...HEAD"
  }
  local edit_ok="sed -i '46s/Q/R/' $DOC0139 && sed -i '47s/Q/R/' $DOC0139 && echo x > tests/doc-checks/EKO-1-41.sh && echo '{}' > docs/cost-register/row-2.json && printf '%s\n' '- [ ] **EKO-1-41** — reserved.' '  *Done when:* x.' >> docs/PLAN.md"
  k04_case "K-04 the allowed set passes, the reservation named" pass "the EKO-1-41 reservation" "$edit_ok"
  k04_case "K-04 (M-4) one character appended to the EKO-1-39 entry fails" fail "docs/PLAN.md" "$edit_ok && sed -i 's/frozen entry\\./frozen entry.x/' docs/PLAN.md"
  k04_case "K-04 (M-4) a touched evidence-chain.sh fails" fail "$CHAIN" "$edit_ok && echo '# touched' >> $CHAIN"
  k04_case "K-04 an edited cost row fails" fail "row-1.json" "$edit_ok && echo '{\"row\":2}' > docs/cost-register/row-1.json"
  k04_case "K-04 a change to EKO-1-39.sh off lines 46-47 fails" fail "hunks" "$edit_ok && sed -i '48s/48/49/' $DOC0139"
  k04_case "K-04 a plan entry other than EKO-1-41 fails" fail "not only the EKO-1-41 entry" "printf '%s\n' '- [ ] **EKO-1-42** — other.' >> docs/PLAN.md"

  # K-04 hashes: the recorded bytes pass, one byte more fails.
  printf 'x' > "$st/h1"; printf 'y' > "$st/h2"
  expect "K-04 (One) a body that is not the gate-1 body fails" fail "Issue #230" k04_hashes "$st/h1" "$st/h2"

  # K-05: one planted printed name per written form; every one is listed.
  local k="$st/k05"; mkdir -p "$k/tests/doc-checks"; qgit init --quiet "$k" || die "self-test: git init failed"
  {
    printf '%s\n' "N1='a'\"'\"'b'" "N2=\"a\\'b\"" "N3=\"a\\\"b\"" "N4=\"a\\\\b\"" "N5=\"a\\\$b\"" "N6=\$'a\\'b'" "N7='plain name'"
  } > "$k/tests/doc-checks/EKO-9-98.sh"
  qgit -C "$k" add -A
  k05_count() { local n; n="$(k05_search "$k" | grep -c 'EKO-9-98.sh:[1-6]:' || true)"; WHY="$n of 6 planted forms listed"; [ "$n" -eq 6 ] && ! k05_search "$k" | grep -q 'EKO-9-98.sh:7:'; }
  expect "K-05 every planted written form is listed, the plain name is not" pass "6 of 6" k05_count

  echo "EKO-1-41 self-test: $((st_total - st_fail)) of $st_total passed"
  [ "$st_fail" -eq 0 ]
}

case "$MODE" in
  self) self_test ;;
  k05) k05_search "$TOP" ;;
  *) main_run ;;
esac
