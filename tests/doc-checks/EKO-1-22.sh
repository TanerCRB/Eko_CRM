#!/usr/bin/env bash
# EKO-1-22 — document checks for the corrected sensitive-paths preamble (Issue #48), criteria
# K-01..K-05.
#
#   bash tests/doc-checks/EKO-1-22.sh                       # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-22.sh --head <ref>          # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-22.sh --base <ref> [...]    # another base than origin/main
#
# Expected runtime: the checks themselves are seconds — K-05's pytest leg dominates (tens of seconds
# on a warm backend env). The status lookups build ONE map per decisions directory (a single awk pass
# over the ADR files) and then resolve ids by in-process string operations — one awk per walk of the
# register. The earlier shape of an ls/tr/grep/awk spawn per citation took minutes on Git Bash/MSYS
# and is the defect this design removes; keep it that way when editing.
#
# Reads. The register and the protected files are read from the same place as the change set — the
# working tree by default, or the commit named by --head (the EKO-1-05 convention) — always with
# CR removed (.gitattributes stores these files with LF; a Windows checkout may hold CRLF). The
# decisions-directory lookups of K-02 and K-03 read the working tree: the registry's current state
# is the ground the consistency rule compares against. K-05 runs the machine consumers as they
# actually run — scripts/risk-check.sh and the working-tree register, the backend static tests
# from backend/ — no --head indirection, so the criterion proves the real consumers, not a copy.
#
# Each check is one line, "ok   <name>", "FAIL <name> — <why>" or "skip <name> — <why>". The names
# are the ones the PR's "K-<n> — test:" evidence lines quote. Exit codes: 0 = every check that ran
# passed, 1 = at least one check failed, 2 = the script itself could not run (bad argument,
# missing file, not a repository, no merge base) — never read 2 as a pass. A check that finds its
# own comparison unable to run prints FAIL, never ok and never skip.
#
# Every criterion carries its contrast as a copy built inside the script, differing from the live
# text by exactly one element (the fixtures live under one mktemp -d directory, removed on exit;
# nothing else is ever written):
#   K-01a  the original l.11-12 restored → caught.      K-01b  the rule sentence deleted → caught.
#          A "pending" claim wrapped across two physical lines (QA contrast, added at the gate-2
#          QA run: the per-line rule let it through) → caught by the fold-pair detector below.
#   K-02   pending ADR-0007 with a Draft status → the rule passes; the same claim with an Accepted
#          status → the rule fails; with no decision file at all → the rule reports "could not
#          run", never a silent pass.
#   K-03   a row citing ADR-0007 with no file → fails; a fixture decisions directory holding an
#          exact copy of the real one → passes; the same copy with ADR-0006's head status set to
#          Draft → fails.
#   K-04a  planted paths (README.md, CLAUDE.md — refused by C-1 gate-1 A — the sibling register,
#          risk-check.sh) → refused; the allow list's own four paths → accepted.
#   K-04b  a one-character edit of risk-check.sh / of a static test → read as changed.
#   K-04c  a dropped table row, a planted class-cell flip → read as changed (a row-count
#          comparison would miss the flip; this is a string comparison of the whole slice).
#   K-05   the same register copy with one preamble line written as a row → the classes query
#          exits 2 (never read as "no risk"); the clean copy → exits 0 with the real classes.
#
# Bases. The K-04 change set is `git diff <merge base of --base and the head>` plus untracked
# files. After the merge, re-run with main's commit before the merge as base and the PR's head
# commit — the inert-after-merge lesson: diff the two refs, never a live PR base:
#
#   bash tests/doc-checks/EKO-1-22.sh --base <merge>^1 --head <merge>^2
#
# Without --base, once origin/main already holds the citation-rule preamble (the task is merged),
# the three K-04 checks print "skip" with that command and are not counted. With an explicit
# --base nothing is skipped, and an empty change set fails.
#
# What these checks are: line, cell and string matching over the register's prose and table, and
# status lookups in docs/architecture/decisions/. They prove what the register states and that its
# machine consumers still read it — not that any running system behaves in any other way.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
HEAD_REF=""
die() { echo "EKO-1-22 doc-checks: $* — the checks did not run" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || die "--base needs a ref"; BASE_REF="$2"; BASE_GIVEN=1; shift 2 ;;
    --head) [ $# -ge 2 ] || die "--head needs a ref"; HEAD_REF="$2"; shift 2 ;;
    *) die "unknown argument '$1' (usage: $0 [--base <ref>] [--head <ref>])" ;;
  esac
done

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || die "cannot enter the repository root"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git repository"
git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || die "base '$BASE_REF' is not a commit"
if [ -n "$HEAD_REF" ]; then
  git rev-parse --verify --quiet "$HEAD_REF^{commit}" >/dev/null || die "head '$HEAD_REF' is not a commit"
fi
MB="$(git merge-base "$BASE_REF" "${HEAD_REF:-HEAD}")" || die "no merge base of '$BASE_REF' and '${HEAD_REF:-HEAD}'"

PATHS="docs/architecture/architecture-sensitive-paths.md"
DECISIONS="docs/architecture/decisions"
RISK="scripts/risk-check.sh"
STATIC=(
  backend/tests/static/test_k05_workflow.py
  backend/tests/static/test_k07_changeset.py
  backend/tests/static/test_eko110_k07_changeset.py
)

content() {
  if [ -z "$HEAD_REF" ]; then
    [ -r "$1" ] || return 1
    tr -d '\r' < "$1"
  else
    git show "$HEAD_REF:$1" 2>/dev/null | tr -d '\r'
  fi
}
at() { git show "$1:$2" 2>/dev/null | tr -d '\r'; }

# ---- preflight: the inputs every check stands on ---------------------------------------------

[ -n "$(content "$PATHS")" ] || die "cannot read $PATHS (${HEAD_REF:-working tree})"
[ -n "$(at "$MB" "$PATHS")" ] || die "cannot read $PATHS at the merge base $MB"
[ -d "$DECISIONS" ] || die "the decisions directory $DECISIONS is not there"
for f in "$RISK" "${STATIC[@]}"; do
  [ -n "$(at "$MB" "$f")" ] || die "cannot read $f at the merge base $MB"
done

tmp="$(mktemp -d)" || die "mktemp failed"
# Deferred expansion: $tmp is read when the trap runs, inside double quotes — an apostrophe or a
# space in a TMPDIR path cannot break the rm command or turn part of it into a repo-relative path.
trap 'rm -rf "$tmp"' EXIT

REG="$(content "$PATHS")" || die "cannot read $PATHS"

# The two preamble lines this task replaced (the EKO-1-05 L-01 finding), word for word.
OLD1='Rows that mark a decision as "pending" (ADR-0006) are governed by a decision not yet accepted;'
OLD2='that task edits its own rows.'
# The class-table row the K-04c contrast flips (one element: the two "no — it is fixed" cells).
ROW_SCHEMA='| schema | migrations, the data schema | yes | no — it is fixed |'
ROW_SCHEMA_FLIPPED='| schema | migrations, the data schema | no | no |'
# The fixture pending claim (K-02): a marker "pending ADR-0007", in prose and in a table cell.
PENDING_SENTENCE="The data row below waits on pending ADR-0007; this fixture line plants a legitimate pending claim."

# ---- text helpers ------------------------------------------------------------------------------

# restore_old — the register with the new citation-rule lines swapped back for the original
# l.11-12 (the K-01a contrast: one changed element).
restore_old() {
  O1="$OLD1" O2="$OLD2" awk '
    BEGIN { o1 = ENVIRON["O1"]; o2 = ENVIRON["O2"]; d = 0; sw = 0 }
    sw == 1 && /rewritten by that decision/ { sw = 0; next }
    d == 0 && /cites the decision that governs it/ { print o1; print o2; d = 1; sw = 1; next }
    { print }'
}
# strip_rule — the register without the citation-rule sentence (the K-01b contrast).
strip_rule() {
  awk '/cites the decision that governs it/ { next } /rewritten by that decision/ { next } { print }'
}
# plant_pending_claim — the register with a "pending ADR-0007" marker added in the preamble and
# in one table row's Governing-decisions cell (the K-02 fixture; the register's other content
# untouched).
plant_pending_claim() {
  PL="$PENDING_SENTENCE" awk '
    BEGIN { pl = ENVIRON["PL"]; d1 = 0; d2 = 0 }
    d1 == 0 && /is accepted[.][[:space:]]*$/ { print; print pl; d1 = 1; next }
    d2 == 0 && index($0, "ADR-0002, ADR-0003, ADR-0005") > 0 {
      sub(/ADR-0002, ADR-0003, ADR-0005/, "ADR-0002, ADR-0003, pending ADR-0007"); d2 = 1 }
    { print }'
}
# plant_wrap — the register with the original claim re-added WRAPPED across two lines: "pending"
# ends one line, "(ADR-0006)" starts the next (a markdown reflow of the very sentence this task
# removed — the K-01a wrap contrast, QA run 2026-11-09; the per-line grep alone missed it).
plant_wrap() {
  awk '{ print } /when it is accepted[.][[:space:]]*$/ && !p {
    print "Rows that mark a decision as \"pending\""; print "(ADR-0006) are governed by a decision not yet accepted."; p = 1 }'
}
# fold_pairs — every adjacent pair of lines joined into one; a claim split by a hard wrap is a
# single-line claim again in its pair. Used by k01a's wrap detector and pending_claims.
fold_pairs() { awk '{ if (NR > 1) print prev " " $0; prev = $0 } END { if (NR) print prev }'; }
# slice_from_table — stdin to end of file from the register's first table line.
slice_from_table() { awk 'ex || index($0, "| Path (glob) | Risk classes") { ex = 1; print }'; }
# build_status_map <decisions dir> — ONE pass over the directory's ADR files, printing tab lines
# "ADR-<id>\t<file count>\t<first **Status:** line>". An id enters the map only through a file named
# "ADR-<id>-*.md" (the same grammar the old per-citation glob used; TEMPLATE.md never enters). The
# head status is each file's FIRST "**Status:**" line — addendum status lines come later and are
# never read (the real files carry up to four); CR and TAB inside it fold to spaces so the map parses
# by tab. Prints nothing when the directory holds no ADR file; returns 1 only when the directory is
# missing. This is the runtime fix: citations_check and pending_rule read the map in-process.
build_status_map() {
  local dir="$1" f
  [ -d "$dir" ] || return 1
  local files=()
  for f in "$dir"/ADR-*.md; do
    [ -e "$f" ] || continue
    files+=("$f")
  done
  [ ${#files[@]} -gt 0 ] || return 0
  awk '
    !seen[FILENAME] && /^[*][*]Status:[*][*]/ { seen[FILENAME] = 1; st[FILENAME] = $0 }
    END {
      for (i = 1; i < ARGC; i++) {
        n = split(ARGV[i], s, "/")
        base = s[n]
        if (base !~ /^ADR-[0-9][0-9][0-9][0-9]-/) continue
        id = substr(base, 1, 8)
        cnt[id]++
        if (!(id in first)) first[id] = ARGV[i]
      }
      for (id in cnt) {
        line = st[first[id]]
        gsub(/[\r\t]/, " ", line)
        print id "\t" cnt[id] "\t" line
      }
    }' "${files[@]}"
}
# map_get <id> <map text> — in-process lookup: sets MAP_COUNT (0 when the id is not in the map) and
# MAP_STATUS (the head status line, or empty); returns 0 when found, 1 when absent. Spawns nothing.
MAP_COUNT="0"; MAP_STATUS=""
map_get() {
  local lid lcnt lst
  MAP_COUNT="0"; MAP_STATUS=""
  while IFS=$'\t' read -r lid lcnt lst; do
    if [ "$lid" = "$1" ]; then MAP_COUNT="$lcnt"; MAP_STATUS="$lst"; return 0; fi
  done <<< "$2"
  return 1
}

# ---- the check runner --------------------------------------------------------------------------

passed=0; failed=0; skipped=0; WHY=""
check() {
  local name="$1"; shift
  WHY=""
  if "$@"; then echo "ok   $name"; passed=$((passed + 1))
  else echo "FAIL $name — ${WHY:-check failed}"; failed=$((failed + 1)); fi
}
skip() { echo "skip $1 — $2"; skipped=$((skipped + 1)); }
# has <text> <ERE> — case-insensitive; a here-string, never "printf | grep -q" (SIGPIPE under
# pipefail, found in EKO-1-03).
has() { grep -Eiq -- "$2" <<< "$1"; }

# ---- K-01: the register's own claim -------------------------------------------------------------

# pending_claims <register text> — the ADR identifiers a "pending <id>" marker names (marker
# presence keys the lookup, C-3; the marker may be adjacent "pending ADR-0007" or the original
# punctuation-separated form, up to six non-alphanumeric characters). Read through fold_pairs: a
# claim split by a hard line wrap is extracted from its line pair (QA wrap contrast, 2026-11-09).
pending_claims() {
  printf '%s\n' "$1" | fold_pairs | tr -d '*`' | grep -Eoi -- 'pending[^[:alnum:]]{0,6}ADR-[0-9]{4}' | grep -Eo 'ADR-[0-9]{4}' | sort -u
}

k01a() {
  local hits fa fw fwp
  hits="$(printf '%s\n' "$REG" | tr -d '*`' | grep -Ei 'pending' | grep -E 'ADR-[0-9]{4}')"
  [ -z "$hits" ] || { WHY="a line claims a decision pending: $(printf '%s' "$hits" | head -n 1 | cut -c1-200)"; return 1; }
  fw="$(printf '%s\n' "$REG" | fold_pairs | tr -d '*`' | grep -Eoi -- 'pending[^[:alnum:]]{0,6}ADR-[0-9]{4}' | head -n 1)"
  [ -z "$fw" ] || { WHY="a pending claim is wrapped across lines (fold-pair hit): $fw"; return 1; }
  fa="$(printf '%s\n' "$REG" | restore_old | tr -d '*`' | grep -Ei 'pending' | grep -E 'ADR-[0-9]{4}')"
  [ -n "$fa" ] || { WHY="insensitive: the copy with the original l.11-12 restored is not caught either"; return 1; }
  fwp="$(printf '%s\n' "$REG" | plant_wrap | fold_pairs | tr -d '*`' | grep -Eoi -- 'pending[^[:alnum:]]{0,6}ADR-[0-9]{4}' | head -n 1)"
  [ -n "$fwp" ] || { WHY="insensitive: the copy with the pending claim wrapped across two lines is not caught"; return 1; }
  return 0
}
check 'K-01a the register claims no decision pending' k01a

# rule_sentence <text> — the preamble (everything before the first table line) carries the
# accepted citation-rule sentence, keyed to the final wording in its three parts.
rule_sentence() {
  local pre; pre="$(awk '/^\| Path \(glob\) \|/ { exit } { print }' <<< "$1")"
  has "$pre" 'cites the decision that governs it' || { WHY="the preamble lacks the citation-rule opening: /cites the decision that governs it/"; return 1; }
  has "$pre" 'unmarked citation names an accepted decision' || { WHY="the preamble lacks the Accepted half: /unmarked citation names an accepted decision/"; return 1; }
  has "$pre" 'is rewritten by that decision.s own task when it is accepted' || { WHY="the preamble lacks the rewrite half: /is rewritten by that decision's own task when it is accepted/"; return 1; }
  return 0
}
k01b() {
  rule_sentence "$REG" || return 1
  local fb; fb="$(printf '%s\n' "$REG" | strip_rule)"
  if rule_sentence "$fb"; then
    WHY="insensitive: the copy with the rule sentence deleted still contains it"
    return 1
  fi
  return 0
}
check 'K-01b the preamble carries the citation-rule sentence' k01b

# ---- K-02: the pending/accepted consistency rule, conditional -----------------------------------

# pending_rule <register text> <decisions dir> — every identifier a pending marker names must have
# a status other than "Accepted"; echoes a one-line verdict in RULE_MSG; 0 = consistent,
# 1 = inconsistent (a pending claim names an Accepted decision), 2 = could not run (a claimed
# identifier resolves to no file, more than one, or no status line) — 2 is never a silent pass.
RULE_MSG=""
pending_rule() {
  local reg="$1" dir="$2" ids id map
  ids="$(pending_claims "$reg")"
  [ -n "$ids" ] || { RULE_MSG="no pending claim"; return 0; }
  [ -d "$dir" ] || { RULE_MSG="decisions dir '$dir' is not there"; return 2; }
  map="$(build_status_map "$dir")" || { RULE_MSG="decisions dir '$dir' could not be read"; return 2; }
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    map_get "$id" "$map"
    [ "$MAP_COUNT" -eq 1 ] || { RULE_MSG="$id is called pending but resolves to $MAP_COUNT decision files under $dir"; return 2; }
    [ -n "$MAP_STATUS" ] || { RULE_MSG="$id is called pending but its decision file has no **Status:** line"; return 2; }
    case "$MAP_STATUS" in
      "**Status:** Accepted"*)
        RULE_MSG="$id is called pending and its status reads Accepted: $MAP_STATUS"
        return 1 ;;
    esac
  done <<< "$ids"
  RULE_MSG="every pending claim names a decision whose status is not Accepted"
  return 0
}

k02() {
  local reg_a rc claims
  mkdir -p "$tmp/k02/decisions-a" "$tmp/k02/decisions-b" "$tmp/k02/decisions-c" || { WHY="the fixture dirs could not be made"; return 1; }
  printf '**Status:** Draft — pending approval\n\n# ADR-0007 — fixture decision for the EKO-1-22 checks (not accepted)\n' > "$tmp/k02/decisions-a/ADR-0007-fixture.md"
  printf '**Status:** Accepted 2026-11-09\n\n# ADR-0007 — fixture decision for the EKO-1-22 checks (planted as accepted)\n' > "$tmp/k02/decisions-b/ADR-0007-fixture.md"
  reg_a="$(printf '%s\n' "$REG" | plant_pending_claim)"
  claims="$(pending_claims "$reg_a")"
  [ "$claims" = "ADR-0007" ] || { WHY="the fixture did not plant exactly the ADR-0007 pending claim (got: $(tr '\n' ' ' <<< "$claims"))"; return 1; }
  # live: the edited register holds no pending claim and the rule passes.
  pending_rule "$REG" "$DECISIONS"; rc=$?
  [ $rc -eq 0 ] || { WHY="the live register breaks the consistency rule (rc $rc): $RULE_MSG"; return 1; }
  # fixture (a): pending ADR-0007 whose head status reads Draft → the rule passes (a legitimate
  # pending state stays green — a flat "nothing may ever be pending" check would fail here).
  pending_rule "$reg_a" "$tmp/k02/decisions-a"; rc=$?
  [ $rc -eq 0 ] || { WHY="fixture (a): a pending claim naming a Draft decision must pass, got rc $rc: $RULE_MSG"; return 1; }
  # fixture (b): the same claim, status Accepted → the rule fails (the status lookup is consulted;
  # a rule matching only the word "pending" would pass here).
  pending_rule "$reg_a" "$tmp/k02/decisions-b"; rc=$?
  [ $rc -eq 1 ] || { WHY="fixture (b): a pending claim naming an Accepted decision must fail, got rc $rc: $RULE_MSG"; return 1; }
  # fixture (c): the same claim, no decision file at all → could not run, never a silent pass.
  pending_rule "$reg_a" "$tmp/k02/decisions-c"; rc=$?
  [ $rc -eq 2 ] || { WHY="fixture (c): a pending claim naming no decision file must report could-not-run, got rc $rc: $RULE_MSG"; return 1; }
  return 0
}
check 'K-02 pending claims are checked against the decisions directory, conditionally' k02

# ---- K-03: unmarked citations resolve to Accepted decisions ---------------------------------------

# citations_check <register text> <status map> <decisions dir (for messages only)> — every
# identifier a path row's Governing-decisions cell cites without a pending marker resolves to exactly
# one ADR-<id>-*.md in the dir whose FIRST **Status:** line reads Accepted; "—" and marker-bearing
# segments pass (the marker's claims are K-02's clause). The row walk, the cell split and the map
# lookups all happen in the one awk below — no process per row, cell or id. Echoes the first
# violation; 0 = every citation resolves.
citations_check() {
  local reg="$1" map="$2" dir="$3"
  [ -d "$dir" ] || { echo "decisions dir '$dir' is not there — the check could not run"; return 1; }
  M="$map" D="$dir" awk -F'|' '
    BEGIN {
      nm = split(ENVIRON["M"], ml, "\n")
      for (i = 1; i <= nm; i++) {
        if (ml[i] == "") continue
        nf = split(ml[i], mf, "\t")
        cnt[mf[1]] = mf[2] + 0
        st[mf[1]] = (nf >= 3 ? mf[3] : "")
      }
    }
    /^\|/ {
      g = $2; c = $4
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", g)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", c)
      if (g !~ /^`[^`]+`$/) next
      if (g ~ /</) next
      gsub(/[*`]/, "", c)
      ns = split(c, seg, ",")
      for (i = 1; i <= ns; i++) {
        if (tolower(seg[i]) ~ /pending/) continue
        rest = seg[i]
        while (match(rest, /ADR-[0-9][0-9][0-9][0-9]/)) {
          id = substr(rest, RSTART, RLENGTH)
          rest = substr(rest, RSTART + RLENGTH)
          if (!(id in cnt) || cnt[id] != 1) {
            printf "the row %s cites %s with no pending marker, but it resolves to %d decision files under %s\n", g, id, cnt[id], ENVIRON["D"]
            exit 1
          }
          if (st[id] == "") {
            printf "the row %s cites %s with no pending marker, but its decision file has no **Status:** line\n", g, id
            exit 1
          }
          if (st[id] !~ /^[*][*]Status:[*][*] Accepted/) {
            printf "the row %s cites %s with no pending marker, but its head status is not Accepted: %s\n", g, id, st[id]
            exit 1
          }
        }
      }
    }' <<< "$reg"
}

k03() {
  local v flip1 draftdir copydir f0 live_map copy_map draft_map
  # one map per decisions directory; the live walk and the flip1 contrast share the live map.
  live_map="$(build_status_map "$DECISIONS")"
  v="$(citations_check "$REG" "$live_map" "$DECISIONS")" || { WHY="a live citation does not resolve: $v"; return 1; }
  # contrast 1: one cell's ADR-0005 flipped to ADR-0007 — no such decision file → fails.
  flip1="$(sed 's/ADR-0002, ADR-0003, ADR-0005/ADR-0002, ADR-0003, ADR-0007/' <<< "$REG")"
  if citations_check "$flip1" "$live_map" "$DECISIONS" >/dev/null; then
    WHY="insensitive: a row citing ADR-0007 with no decision file passes"; return 1
  fi
  # fixture dirs: an exact copy of the real decisions directory (sanity: the live rows pass there
  # too) and the same copy with ADR-0006's head status set to Draft (one changed element).
  draftdir="$tmp/k03/draft"; copydir="$tmp/k03/copy"
  mkdir -p "$draftdir/decisions" "$copydir/decisions" || { WHY="the fixture dirs could not be made"; return 1; }
  cp "$DECISIONS"/ADR-*.md "$draftdir/decisions/" && cp "$DECISIONS"/ADR-*.md "$copydir/decisions/" || { WHY="the fixture decisions copy could not be made"; return 1; }
  copy_map="$(build_status_map "$copydir/decisions")"
  if ! citations_check "$REG" "$copy_map" "$copydir/decisions" >/dev/null; then
    WHY="the exact-copy fixture dir fails the live rows (the copy itself would be the changed element)"; return 1
  fi
  f0="$(ls -1 "$draftdir/decisions"/ADR-0006-*.md | head -n 1)"
  [ -n "$f0" ] || { WHY="no ADR-0006 file to plant the Draft status on"; return 1; }
  awk '/^[*][*]Status:[*][*]/ && !d { print "**Status:** Draft — pending approval"; d = 1; next } { print }' "$f0" > "$f0.new" && mv "$f0.new" "$f0"
  draft_map="$(build_status_map "$draftdir/decisions")"
  v="$(citations_check "$REG" "$draft_map" "$draftdir/decisions")" && { WHY="insensitive: ADR-0006 with a Draft head status passes the unmarked citations"; return 1; }
  grep -q 'ADR-0006' <<< "$v" || { WHY="the Draft-status contrast failed for the wrong reason: $v"; return 1; }
  return 0
}
check 'K-03 every unmarked citation resolves to an Accepted decision' k03

# ---- K-04: the change set and the untouched region -----------------------------------------------

if [ -n "$HEAD_REF" ]; then
  CHANGED="$(git diff --name-only --no-renames "$MB" "$HEAD_REF" | sort -u)"
else
  CHANGED="$( { git diff --name-only --no-renames "$MB"; git ls-files --others --exclude-standard; } | sort -u)"
fi

ALLOWED_RE='^(docs/architecture/architecture-sensitive-paths\.md|tests/doc-checks/EKO-1-22\.sh|docs/cost-register/.+|docs/PLAN\.md)$'
# C-1 (gate 1, option A): CLAUDE.md is NOT allowed — the human folds that line at gate 3.
PLANTED_BAD=(README.md CLAUDE.md docs/architecture/layer-dependencies.md scripts/risk-check.sh docs/architecture/decisions/TEMPLATE.md)
PLANTED_OK=(docs/architecture/architecture-sensitive-paths.md tests/doc-checks/EKO-1-22.sh docs/cost-register/2026-11-09_EKO-1-22_architect_1.json docs/PLAN.md)

k04a() {
  local p outside
  [ -n "$CHANGED" ] || { WHY="the change set is empty against merge base ${MB:0:7} — the comparison would prove nothing (re-run with --base <merge>^1 --head <merge>^2)"; return 1; }
  outside="$(grep . <<< "$CHANGED" | grep -Ev "$ALLOWED_RE")"
  [ -z "$outside" ] || { WHY="outside the allowed set: $(tr '\n' ' ' <<< "$outside")"; return 1; }
  for p in "${PLANTED_BAD[@]}"; do
    printf '%s\n' "$p" | grep -Eq "$ALLOWED_RE" && { WHY="insensitive: a planted change to '$p' passes the allow list"; return 1; }
  done
  for p in "${PLANTED_OK[@]}"; do
    printf '%s\n' "$p" | grep -Eqv "$ALLOWED_RE" && { WHY="the allow list refuses its own path '$p'"; return 1; }
  done
  return 0
}

# bytes_unchanged <base text> <candidate text> — THE byte-identity comparison (CR-normalized). The
# k04b live loop and the sensitivity contrast both call this one helper: the contrast is not a copy
# of the comparison's shape, so deleting or weakening the comparison breaks the contrast too.
# BC_CALLS self-evidences the LIVE use — the QA round-2 mutation EKO-1-22-M-11c (removing only the
# live loop's call, contrast kept) left the check GREEN on a3beb36: the contrast proves the helper
# works, nothing there proved the loop calls it. The helper now counts its invocations and k04b
# demands all eight arms ran (4 live files + 4 contrast).
BC_CALLS=0
bytes_unchanged() { BC_CALLS=$((BC_CALLS + 1)); [ "$1" = "$2" ]; }
k04b() {
  local f a b risk edit s sedit
  for f in "$RISK" "${STATIC[@]}"; do
    a="$(at "$MB" "$f")"
    b="$(content "$f")" || { WHY="$f is not readable in the ${HEAD_REF:-working tree}"; return 1; }
    [ -n "$b" ] || { WHY="$f is gone from the ${HEAD_REF:-working tree}"; return 1; }
    bytes_unchanged "$a" "$b" || { WHY="$f is not byte-identical to the merge base (CR-normalized, as every reader here does)"; return 1; }
  done
  # Contrast through the same helper the live loop just used: an unedited copy of the base text
  # reads unchanged (positive), the same text with one appended character reads changed (negative);
  # the pair runs for risk-check.sh and for the first static test. A helper that always answers
  # "unchanged" dies on a negative; one that always answers "changed" dies on a positive and on the
  # live loop itself.
  risk="$(at "$MB" "$RISK")"
  edit="$(printf '%s\n' "$risk" | awk 'NR == 1 { print $0 " x"; next } { print }')"
  bytes_unchanged "$risk" "$risk" || { WHY="the shared comparison calls an unedited copy changed — K-04b's live check would always fail"; return 1; }
  bytes_unchanged "$risk" "$edit" && { WHY="insensitive: a one-character edit of $RISK passes the same comparison the live files are checked with"; return 1; }
  s="$(at "$MB" "${STATIC[0]}")"
  sedit="$(printf '%s\n' "$s" | awk 'NR == 1 { print "# x" $0; next } { print }')"
  bytes_unchanged "$s" "$s" || { WHY="the shared comparison calls an unedited copy changed (static-test leg)"; return 1; }
  bytes_unchanged "$s" "$sedit" && { WHY="insensitive: a one-character edit of ${STATIC[0]} passes the same comparison the live files are checked with"; return 1; }
  # Every protected file must have been compared for real: 4 live + 4 contrast arms (M-11c fix).
  [ "$BC_CALLS" -eq 8 ] || { WHY="insensitive: only $BC_CALLS byte-identity comparisons ran — the live loop must call the helper once per protected file"; return 1; }
  # The two negative-contrast lines above leave status 1 on the SUCCESS path (the comparison
  # correctly answers "changed", the && branch does not run) — the function must close with 0.
  return 0
}

k04c() {
  local base head drop flip
  base="$(at "$MB" "$PATHS" | slice_from_table)"
  [ -n "$base" ] || { WHY="the register at the merge base has no table header line — the comparison could not run"; return 1; }
  head="$(content "$PATHS" | slice_from_table)"
  [ -n "$head" ] || { WHY="the register has no table header line in the ${HEAD_REF:-working tree}"; return 1; }
  [ "$base" = "$head" ] || { WHY="the register changed from its first table row to end of file (only lines above the table may differ)"; return 1; }
  drop="$(printf '%s\n' "$base" | grep -vF '| `backend/app/worker.py` |')"
  [ "$base" != "$drop" ] || { WHY="insensitive: a copy with one dropped table row reads as unchanged"; return 1; }
  flip="$(R="$ROW_SCHEMA" W="$ROW_SCHEMA_FLIPPED" awk '
    BEGIN { r = ENVIRON["R"]; w = ENVIRON["W"]; d = 0 }
    d == 0 && $0 == r { print w; d = 1; next }
    { print }' <<< "$base")"
  [ "$base" != "$flip" ] || { WHY="insensitive: the planted class-cell flip reads as unchanged (a row-count comparison would pass it)"; return 1; }
  return 0
}

# inert-after-merge: without --base, when origin/main already holds the new preamble, the base is
# the merged state and these three comparisons would prove nothing — skip them by name with the
# command to use instead.
K04_SKIP=""
BASE_REG="$(at "$BASE_REF" "$PATHS")"
if [ -z "$BASE_GIVEN" ] && grep -qF 'cites the decision that governs it' <<< "$BASE_REG"; then
  K04_SKIP="$PATHS already carries the citation-rule preamble at $BASE_REF (the task is merged); re-run with --base <merge>^1 --head <merge>^2"
fi
check04() { if [ -n "$K04_SKIP" ]; then skip "$1" "$K04_SKIP"; return 0; fi; check "$@"; }

check04 'K-04a the change set is limited to the register, its doc-check and the bookkeeping' k04a
check04 'K-04b risk-check.sh and the three static tests are unchanged from the base' k04b
check04 'K-04c the register is byte-identical from its first table row to end of file' k04c

# ---- K-05: the machine consumers still read the register ------------------------------------------

k05() {
  local out rc expect runner
  expect="$(printf 'auth\npersonal-data')"
  # (a) the parser's self-test.
  out="$(bash "$RISK" --self-test 2>&1)"; rc=$?
  [ $rc -eq 0 ] || { WHY="$RISK --self-test exited $rc: $(tail -n 3 <<< "$out" | tr '\n' ' ' | cut -c1-300)"; return 1; }
  # (b) the real working-tree register answers the classes query.
  out="$(printf '%s\n' backend/app/main.py | bash "$RISK" classes --paths - 2>&1)"; rc=$?
  if [ $rc -ne 0 ]; then WHY="the real-register classes query exited $rc — exit 2 is never read as no risk: $out"; return 1; fi
  [ "$out" = "$expect" ] || { WHY="backend/app/main.py reads as '$(tr '\n' '/' <<< "$out")', expected auth then personal-data"; return 1; }
  # (b, contrast) one preamble line written as a row must fail the check itself, never read as
  # "no risk"; the clean copy of the same file must still answer — the planted line is the only
  # changed element. The copies take the working-tree register, the text the real query just read.
  local wreg
  [ -r "$PATHS" ] || { WHY="K-05 runs the real working tree, but $PATHS is not readable there"; return 1; }
  wreg="$(tr -d '\r' < "$PATHS")"
  printf '%s\n' "$wreg" > "$tmp/k05-clean.md"
  { printf '| `zzz/**` | governance | ADR-0001 | x |\n'; printf '%s\n' "$wreg"; } > "$tmp/k05-planted.md"
  out="$(printf '%s\n' backend/app/main.py | bash "$RISK" --register "$tmp/k05-clean.md" classes --paths - 2>&1)"; rc=$?
  [ $rc -eq 0 ] && [ "$out" = "$expect" ] || { WHY="the clean fixture copy itself reads wrong (exit $rc: $out) — the contrast would not prove one element"; return 1; }
  out="$(printf '%s\n' backend/app/main.py | bash "$RISK" --register "$tmp/k05-planted.md" classes --paths - 2>&1)"; rc=$?
  [ $rc -eq 2 ] || { WHY="insensitive: the row-shaped preamble line gave exit $rc, expected 2"; return 1; }
  # (c) the three static tests that read the register pass unedited. No doc-check before this one
  # ran pytest; the invocation follows CI (uv inside backend/), with a bare python -m pytest
  # tried first. No runner is a FAIL of this criterion, never a skip.
  runner=""
  if command -v python >/dev/null 2>&1 && (cd backend && python -m pytest --version >/dev/null 2>&1); then
    runner="python -m pytest"
  elif command -v uv >/dev/null 2>&1; then
    runner="uv run python -m pytest"
  fi
  [ -n "$runner" ] || { WHY="no pytest runner (python without pytest, uv not on PATH) — the static tests could not be run"; return 1; }
  # Word-splitting of $runner below is deliberate: it holds exactly the one- or two-word command
  # prefix chosen above ("python -m pytest" or "uv run python -m pytest") and must split into argv
  # words; the path arguments are fixed literals. The suppression covers only that unquoted use.
  # shellcheck disable=SC2086
  out="$(cd backend && $runner tests/static/test_k05_workflow.py tests/static/test_k07_changeset.py tests/static/test_eko110_k07_changeset.py -q 2>&1)"; rc=$?
  [ $rc -eq 0 ] || { WHY="the static tests failed (exit $rc, runner: $runner): $(tail -n 8 <<< "$out" | tr '\n' ' ' | cut -c1-500)"; return 1; }
  return 0
}
check 'K-05 the machine consumers still read the register' k05

# ---- result ---------------------------------------------------------------------------------------

echo "EKO-1-22 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE_REF, merge base $MB, head ${HEAD_REF:-working tree})"
[ "$failed" -eq 0 ]
