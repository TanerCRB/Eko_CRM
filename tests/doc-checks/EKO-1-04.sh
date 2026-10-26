#!/usr/bin/env bash
# EKO-1-04 — document checks for the personal-data decision (ADR-0005), criteria K-01..K-04,
# K-06 and K-07 of Issue #17. K-05 is judged by the human at gate 2 and has no check here.
#
#   bash tests/doc-checks/EKO-1-04.sh                       # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-04.sh --head <ref>          # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-04.sh --base <ref> [...]    # another base than origin/main
#   bash tests/doc-checks/EKO-1-04.sh --offline [...]       # skip the checks that ask GitHub
#
# Every document is read from the same place as the change set: the working tree by default (so a
# mutation applied to a file, committed or not, is seen by every check, including the git-diff
# checks of K-07, which then compare the merge base of <base> and HEAD with the working tree plus
# untracked files), or the commit named by --head (then `git diff <merge base>..<head>`).
#
# Each check is one line of output, "ok   <name>", "FAIL <name> — <why>" or "skip <name> — <why>".
# The names are the ones the PR's "K-<n> — test:" lines quote. Exit codes: 0 = every check that ran
# passed, 1 = at least one check failed, 2 = the script itself could not run (bad argument,
# missing file, not a repository) — never read 2 as a pass.
#
# Content checks on ADR-0005 read it with every HTML comment removed (inline and multi-line); an
# opening "<!--" with no closing "-->" fails its own check and hides the rest of the file from the
# others. They are scoped to "## Decision" or to one of its "###" sections, as each check says.
#
# Bases. TASK_BASE below is the commit the task branched from (00b776d). The forwards K-06 counts
# are read from ADR-0001..0004 as they stand there, and K-07 compares ADR-0001..0004 with it blob
# for blob. The K-07 change set is `git diff <merge base of --base and head>`, the change set a pull
# request against main shows. The branch merged origin/main (59949ea, which reserved EKO-1-09 in
# docs/PLAN.md) after it started, so the change set from TASK_BASE itself also lists docs/PLAN.md,
# a change that is main's, not the task's. After the merge, re-run every check with main's commit
# before the merge as base and the PR's head commit:
#
#   bash tests/doc-checks/EKO-1-04.sh --base <merge>^1 --head <merge>^2
#
# Without --base, when ADR-0005 already exists at origin/main (the task is merged), the K-07
# change-set checks print "skip" with that command and are not counted. With an explicit --base
# nothing is skipped.
#
# Checks that ask GitHub through `gh` (the identifier/Issue pairs match the Issue titles; Issue
# #17 records no approved deviation, or the one ADR-0005 names) fail when `gh` cannot answer;
# --offline prints them as "skip" instead, by name.
#
# The gate-1 figures of K-03 are the constants under "G-2" below, copied from the human's G-2
# answer recorded in Issue #17 on 2026-10-25. Durations are compared in minutes after the unit is
# normalised (1 week = 7 days, 1 month = 30 days, 1 year = 365 days).
#
# What these checks are: line and sentence matching over prose. They prove that a statement is
# present (or absent) in the decision, not that the statement is true of any running system.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
TASK_BASE="00b776d2108b414bd37ef8853c706de6f84d9919"
HEAD_REF=""
OFFLINE=""
REPO_SLUG="TanerCRB/Eko_CRM"
ISSUE=17
die() { echo "EKO-1-04 doc-checks: $* — the checks did not run" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || die "--base needs a ref"; BASE_REF="$2"; BASE_GIVEN=1; shift 2 ;;
    --head) [ $# -ge 2 ] || die "--head needs a ref"; HEAD_REF="$2"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    *) die "unknown argument '$1' (usage: $0 [--base <ref>] [--head <ref>] [--offline])" ;;
  esac
done

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || die "cannot enter the repository root"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git repository"
git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || die "base '$BASE_REF' is not a commit"
git rev-parse --verify --quiet "$TASK_BASE^{commit}" >/dev/null || die "task base $TASK_BASE is not in this clone"
if [ -n "$HEAD_REF" ]; then
  git rev-parse --verify --quiet "$HEAD_REF^{commit}" >/dev/null || die "head '$HEAD_REF' is not a commit"
fi
MB="$(git merge-base "$BASE_REF" "${HEAD_REF:-HEAD}")" || die "no merge base of '$BASE_REF' and '${HEAD_REF:-HEAD}'"

DECISIONS="docs/architecture/decisions"
ADR1="$DECISIONS/ADR-0001-application-stack.md"
ADR2="$DECISIONS/ADR-0002-database-and-migrations.md"
ADR3="$DECISIONS/ADR-0003-identity-and-access.md"
ADR4="$DECISIONS/ADR-0004-deployment-and-recovery.md"
PATHS="docs/architecture/architecture-sensitive-paths.md"
PLAN="docs/PLAN.md"

# The register's identifiers with the Issue whose title carries "[EKO-x-yy]", read from GitHub on
# 2026-10-25 and re-checked by the named gh check.
PAIRS='EKO-1-01 6
EKO-1-02 15
EKO-1-03 16
EKO-1-04 17
EKO-1-05 18
EKO-1-06 19
EKO-1-07 20
EKO-1-08 36
EKO-1-09 41
EKO-2-01 21'

# G-2 (gate 1, Issue #17, 2026-10-25): the retention figures, in minutes.
G2_LOGIN_TX=60                 # login transactions: 1 hour after creation
G2_ADMIN_APP=129600            # admin events, application realm: 90 days
G2_ADMIN_MASTER=129600         # admin events, master realm: 90 days
G2_LOGIN_MASTER=129600         # master-realm login events: 90 days
G2_LOGIN_APP=43200             # application-realm login events: stored, authentication types, 30 days
G2_DISPLAY=259200              # display-name copy no record refers to: 180 days after the last login
G2_LOGS=20160                  # logs of every service: 14 days, by time
G2_COPY_ADMIN=525600           # off-server copy: admin events and master-realm login events, 365 days
G2_COPY_APPLOGIN=129600        # off-server copy: application-realm login events, 90 days
C1_SHIP=5                      # C-1: a shipment at least every 5 minutes
C1_ALERT=60                    # C-1: an off-server alert after 1 hour without a shipment
REVIEW_INTERVAL=10080          # ADR-0004 Operator duties: the review every 7 days

# ---- reading -------------------------------------------------------------------------------

content() {
  if [ -z "$HEAD_REF" ]; then
    [ -r "$1" ] || return 1
    tr -d '\r' < "$1"
  else
    git show "$HEAD_REF:$1" 2>/dev/null | tr -d '\r'
  fi
}
at() { git show "$1:$2" 2>/dev/null | tr -d '\r'; }

if [ -z "$HEAD_REF" ]; then
  adr5_list="$(ls "$DECISIONS"/ADR-0005-*.md 2>/dev/null)"
else
  adr5_list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/" | grep -E '/ADR-0005-[^/]*\.md$')"
fi
[ "$(printf '%s\n' "$adr5_list" | grep -c .)" -eq 1 ] || die "expected exactly one $DECISIONS/ADR-0005-*.md, found: '${adr5_list}'"
ADR5="$adr5_list"
for f in "$ADR5" "$ADR1" "$ADR2" "$ADR3" "$ADR4" "$PATHS" "$PLAN"; do content "$f" >/dev/null || die "cannot read $f"; done
for f in "$ADR1" "$ADR2" "$ADR3" "$ADR4" "$PATHS" "$PLAN"; do at "$TASK_BASE" "$f" >/dev/null || die "cannot read $f at $TASK_BASE"; done

# strip_comments — stdin without HTML comments; exits 3 when a "<!--" is never closed.
strip_comments() {
  awk '
    { line = $0; out = ""; had = inc
      while (1) {
        if (inc) { p = index(line, "-->"); if (!p) { line = ""; break }; line = substr(line, p + 3); inc = 0 }
        p = index(line, "<!--"); if (!p) { out = out line; break }
        had = 1; out = out substr(line, 1, p - 1); line = substr(line, p + 4); inc = 1
      }
      if (had && out ~ /^[[:space:]]*$/) next
      print out }
    END { if (inc) exit 3 }'
}
# section <heading regex> — from the matching heading to the next heading of the same or higher level.
section() {
  awk -v re="$1" '
    function level(s) { match(s, /^#+/); return RLENGTH }
    !on && /^#+ / && $0 ~ re { on = 1; lv = level($0); print; next }
    on && /^#+ / && level($0) <= lv { exit }
    on { print }'
}
# paras — one record per paragraph, list item, heading or table row; ** and ` removed.
paras() {
  awk '
    function flush() { if (buf != "") { gsub(/\*\*|`/, "", buf); gsub(/[[:space:]]+/, " ", buf); sub(/^ /, "", buf); sub(/ $/, "", buf); print buf }; buf = "" }
    /^[[:space:]]*$/ { flush(); next }
    /^(#|\||[[:space:]]*- |\* |[0-9]+\. )/ { flush(); buf = $0; if ($0 ~ /^(#|\|)/) flush(); next }
    { buf = (buf == "" ? $0 : buf " " $0) }
    END { flush() }'
}
sents() { sed -E 's/\. ([A-Z(])/.\n\1/g'; }

ADR5_RAW="$(content "$ADR5")"
ADR5_TEXT="$(printf '%s\n' "$ADR5_RAW" | strip_comments)"; STRIP_RC=$?
DECISION_TEXT="$(printf '%s\n' "$ADR5_TEXT" | section '^## Decision')"
DECISION_SENTS="$(printf '%s\n' "$DECISION_TEXT" | paras | sents)"
sub_text() { printf '%s\n' "$DECISION_TEXT" | section "$1"; }
sub_paras() { sub_text "$1" | paras; }
sub_sents() { sub_paras "$1" | sents; }
PLAN_TEXT="$(content "$PLAN")"
ADR4_TEXT="$(content "$ADR4")"

# ---- the check runner ----------------------------------------------------------------------

passed=0; failed=0; skipped=0
WHY=""
check() {
  local name="$1"; shift
  WHY=""
  if "$@"; then echo "ok   $name"; passed=$((passed + 1))
  else echo "FAIL $name — ${WHY:-check failed}"; failed=$((failed + 1)); fi
}
skip() { echo "skip $1 — $2"; skipped=$((skipped + 1)); }
# has <text> <ERE> — case-insensitive match; a here-string, never "printf | grep -q" (SIGPIPE
# under pipefail, found in EKO-1-03).
has() { grep -Eiq -- "$2" <<< "$1"; }
need() { has "$1" "$2" || { WHY="missing${3:+ in $3}: /$2/"; return 1; }; }
forbid() {  # forbid <text> <ERE> [<ERE that excuses the line>]
  local hits
  if [ -n "${3:-}" ]; then hits="$(grep -Ei -- "$2" <<< "$1" | grep -Eiv -- "$3")"
  else hits="$(grep -Ei -- "$2" <<< "$1")"; fi
  # DEBUG_HITS=1 prints every line a ban matches (to stderr), not only the first.
  [ -z "${DEBUG_HITS:-}" ] || [ -z "$hits" ] || printf 'HIT %s\n' "$hits" >&2
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | head -n 1 | cut -c1-220)"; return 1; }
}
# without <text> <exact sentence>... — the text with each listed sentence (a whole line, compared
# literally) replaced by a marker. A ban then excuses a restating sentence only by its exact text.
without() {
  local t="$1"; shift
  # Compared with emphasis marks (*) removed on both sides. One awk for all the sentences (a
  # process per sentence made a run take minutes on Windows); the result is the same.
  local IFS=$'\037'
  X="$*" awk 'BEGIN { n = split(ENVIRON["X"], xs, "\037"); for (i = 1; i <= n; i++) { x = xs[i]; gsub(/\*/, "", x); ex[x] = 1 } }
    { l = $0; gsub(/\*/, "", l); if (l in ex) { print "EXCUSED-SENTENCE"; next }; print }' <<< "$t"
}

pair_ok() {
  grep -Fq -- "**$1**" <<< "$PLAN_TEXT" || { WHY="$1 is not an entry of $PLAN"; return 1; }
  grep -Fxq -- "$1 $2" <<< "$PAIRS" || { WHY="$1 (#$2) does not match the identifier's Issue ($(grep -E "^$1 " <<< "$PAIRS" | sed -E 's/^[^ ]+ /#/'))"; return 1; }
}
# task_pairs <text> — every "EKO-x-yy (#n)" and "EKO-x-yy, #n" of the text, as "EKO-x-yy n".
task_pairs() {
  grep -Eo 'EKO-[0-9]+-[0-9]+( \(#[0-9]+\)|, #[0-9]+)' <<< "$1" | sed -E 's/ \(#([0-9]+)\)$/ \1/; s/, #([0-9]+)$/ \1/'
}
pairs_ok() {
  local id n
  while read -r id n; do
    [ -n "$id" ] || continue
    pair_ok "$id" "$n" || return 1
  done < <(task_pairs "$1")
}

# ---- durations ---------------------------------------------------------------------------

NUMW='[0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fourteen|thirty|sixty|ninety|a|an'
UNITW='minutes?|hours?|days?|weeks?|months?|years?'
# to_min <number> <unit> — the duration in minutes.
to_min() {
  awk -v n="$1" -v u="$2" 'BEGIN {
    n = tolower(n); u = tolower(u)
    w["one"]=1; w["a"]=1; w["an"]=1; w["two"]=2; w["three"]=3; w["four"]=4; w["five"]=5; w["six"]=6
    w["seven"]=7; w["eight"]=8; w["nine"]=9; w["ten"]=10; w["twelve"]=12; w["fourteen"]=14
    w["thirty"]=30; w["sixty"]=60; w["ninety"]=90
    if (n in w) n = w[n]
    sub(/s$/, "", u)
    m["minute"]=1; m["hour"]=60; m["day"]=1440; m["week"]=10080; m["month"]=43200; m["year"]=525600
    print n * m[u] }'
}
# fig <text> <anchor ERE> — minutes of the first "<anchor> <number> <unit>" in the text, or nothing.
fig() {
  local hit; hit="$(grep -Eio -- "$2 ($NUMW) ($UNITW)\b" <<< "$1" | head -n 1)"
  [ -n "$hit" ] || return 0
  to_min "$(awk '{ print $(NF-1) }' <<< "$hit")" "$(awk '{ print $NF }' <<< "$hit")"
}
# fig_eq <text> <anchor> <constant> <what>
fig_eq() {
  local v; v="$(fig "$1" "$2")"
  [ -n "$v" ] || { WHY="$4: no figure after /$2/"; return 1; }
  [ "$v" -eq "$3" ] || { WHY="$4 is $v minutes, the gate-1 figure is $3 minutes"; return 1; }
}

# ---- ADR-0005 structures ---------------------------------------------------------------------

CATS_TEXT="$(sub_text '^### Categories of personal data')"
CAT_ROWS="$(printf '%s\n' "$CATS_TEXT" | paras | grep -E '^\| PD-[CS][0-9]+ ')"
CAT_IDS="$(awk -F'|' '{ v = $2; gsub(/^ +/, "", v); split(v, a, " "); print a[1] }' <<< "$CAT_ROWS")"
HELD_TEXT="$(sub_text '^### Where personal data is held')"
# Raw table rows (backticks kept) of the two tables of "Where personal data is held".
PATH_ROWS="$(awk '/^\*\*Paths under the ADR-0001 layout\.\*\*/ { on = 1; next } /^\*\*Places off the paths\.\*\*/ { on = 0 } on && /^\| `/' <<< "$HELD_TEXT")"
PLACE_ROWS="$(awk '/^\*\*Places off the paths\.\*\*/ { on = 1; next } on && /^\| / && !/^\| Place \|/ && !/^\|---/' <<< "$HELD_TEXT")"

# expand_cats — stdin category cells, stdout one category id per line ("all", ranges, singles).
expand_cats() {
  awk -v ids="$(tr '\n' ' ' <<< "$CAT_IDS")" '
    BEGIN { n = split(ids, all, " ") }
    { s = $0
      if (s ~ /(^|[^a-z])all([^a-z]|$)/) { for (i = 1; i <= n; i++) print all[i] }
      while (match(s, /PD-[CS][0-9]+\.\.PD-[CS][0-9]+/)) {
        r = substr(s, RSTART, RLENGTH); s = substr(s, 1, RSTART - 1) " " substr(s, RSTART + RLENGTH)
        k = substr(r, 4, 1); a = substr(r, 5) + 0; b = substr(r, index(r, "..") + 6) + 0
        for (j = a; j <= b; j++) print "PD-" k j }
      while (match(s, /PD-[CS][0-9]+/)) { print substr(s, RSTART, RLENGTH); s = substr(s, RSTART + RLENGTH) } }' | sort -u
}
cell() { awk -F'|' -v c="$2" '{ v = $c; gsub(/^ +| +$/, "", v); print v }' <<< "$1"; }
HELD_CATS="$( { cell "$PATH_ROWS" 4; cell "$PLACE_ROWS" 4; } | expand_cats)"
# The categories a holder names explicitly (a range or an identifier). "all" (the volume, the
# backup destination, the verification host) holds every category there is, a new one too, so it
# names none: the first version counted it, and a category no path or place names passed
# (EKO-1-04-M02b).
NAMED_CATS="$( { cell "$PATH_ROWS" 4; cell "$PLACE_ROWS" 4; } | sed -E 's/(^|[^a-z])all([^a-z]|$)/\1\2/g' | expand_cats)"
# cats_of <C|S> <item ERE> — the category ids whose items hold the item. Customer items are
# matched against single items (the cell split at ";"), staff items against the whole cell.
cats_of() {
  local kind="$1" re="$2" row id items
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    id="$(cell "$row" 2 | awk '{ print $1 }')"
    case "$id" in PD-"$kind"*) ;; *) continue ;; esac
    items="$(cell "$row" 3)"
    if [ "$kind" = C ]; then
      tr ';' '\n' <<< "$items" | sed -E 's/^ +| +$//g' | grep -Eiq -- "$re" && echo "$id"
    else
      has "$items" "$re" && echo "$id"
    fi
  done <<< "$CAT_ROWS"
}

# ==== K-01 ===================================================================================

k01_comments() { [ "$STRIP_RC" -eq 0 ] || { WHY="an opening <!-- is never closed"; return 1; }; }
check 'ADR-0005 has no unterminated comment' k01_comments

k01_status() {
  local st; st="$(grep -E '^\*\*Status:\*\*' <<< "$ADR5_TEXT")"
  [ "$(grep -c . <<< "$st")" -eq 1 ] || { WHY="expected one status line, found: $(tr '\n' '/' <<< "$st")"; return 1; }
  grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' <<< "$st" || { WHY="status line: $st"; return 1; }
}
check 'ADR-0005 status reads Accepted' k01_status

# (1) The closed customer list: item | ERE of one item of a PD-C row.
CUST_ITEMS="name|customer.s name
address|^the address\b
NIP|^the NIP\b
phones|^(every|each|the|all) phones?( numbers?)?$
e-mails|^(every|each|the|all) e-mails?( address(es)?)?$
contact note|^the note on (each|every|the) phone and e-mail
note text (NOT-1/2)|^the note text\b.*NOT-1.*NOT-2
action description (ACT-1)|^the action description\b
status-change author (ACT-2)|^the author of each action status change\b
visit's customer and owner|^the visit.s customer and owner\b"
STAFF_ITEMS="username|\busername\b
e-mail address|\be-mail address\b
first and last name|\bfirst and last name\b
password hash|\bpassword hash\b
role assignments|\brole assignments\b
enabled state|\benabled state\b
active sessions with IP address and times|\bactive sessions \(with their IP address and times\)
admin events with their representation|\badmin events with their representation\b
login events|\blogin events\b
subject identifier|\bsubject identifier\b
display-name copy|\bdisplay-name copy\b
server-side sessions|\bserver-side sessions\b"

items_held() {  # items_held <C|S> <list>
  local kind="$1" label re ids id ok
  while IFS='|' read -r label re; do
    [ -n "$label" ] || continue
    ids="$(cats_of "$kind" "$re")"
    [ -n "$ids" ] || { WHY="no PD-$kind category row holds the item '$label' (/$re/)"; return 1; }
    ok=""
    for id in $ids; do grep -Fxq -- "$id" <<< "$NAMED_CATS" && ok=1; done
    [ -n "$ok" ] || { WHY="the item '$label' is in $(tr '\n' ' ' <<< "$ids")but no path or place names that category"; return 1; }
  done <<< "$2"
}
k01_customer_items() { items_held C "$CUST_ITEMS"; }
check 'every customer item of the closed list is in a category held by a named path or place' k01_customer_items

k01_staff_items() {
  items_held S "$STAFF_ITEMS" || return 1
  # ADR-0003's login transactions: held in a PD-S row or stated to hold no personal data.
  [ -n "$(cats_of S 'login transactions')" ] || need "$(sub_sents '^### Categories of personal data')" 'login transactions hold no personal data' 'Categories of personal data' || return 1
}
check 'every staff item of both ADR-0003 Staff personal data rows is in a category held by a named path or place' k01_staff_items

k01_no_orphan_category() {
  local id
  [ -n "$CAT_IDS" ] || { WHY="no PD-xx category row"; return 1; }
  for id in $CAT_IDS; do
    grep -Fxq -- "$id" <<< "$NAMED_CATS" || { WHY="category $id is named by no path and no place (only by 'all')"; return 1; }
  done
  # Every category a holder names exists.
  for id in $HELD_CATS; do
    grep -Fxq -- "$id" <<< "$CAT_IDS" || { WHY="a holder names $id, which is not a category"; return 1; }
  done
}
check 'every category is named by at least one path or place, and every holder names existing categories' k01_no_orphan_category

k01_path_cells() {
  local row p cats
  [ -n "$PATH_ROWS" ] || { WHY="the path table of Where personal data is held is empty"; return 1; }
  while IFS= read -r row; do
    p="$(cell "$row" 2)"
    grep -Eq '^`(backend|frontend)/[^`]+`(, `(backend|frontend)/[^`]+`)*$' <<< "$p" || { WHY="path cell is not a path under the ADR-0001 layout: '$p'"; return 1; }
    cats="$(cell "$row" 4)"
    [ -n "$cats" ] || { WHY="path row '$p' has an empty category cell"; return 1; }
  done <<< "$PATH_ROWS"
}
check 'every holder path is a path under the ADR-0001 layout with a category cell' k01_path_cells

# (2) The places off the paths: label | ERE of the Place cell | ERE the categories cell must hold.
PLACES="Keycloak's database|^Keycloak.s database\b|PD-S
the PostgreSQL volumes|^The PostgreSQL volume\b|all|PD-
the backup destination|^The backup destination\b|all|PD-
the IT verification host|\bverification host\b|all|PD-
container logs|^Container logs\b|PD-S
the off-server Keycloak event copy|^The off-server copy of Keycloak events\b|PD-S
Google Calendar|^Google Calendar\b|PD-C
the user's browser|^The user.s browser\b|PD-"
k01_places() {
  local label re catre row r v c h
  while IFS='|' read -r label re catre; do
    [ -n "$label" ] || continue
    row=""
    while IFS= read -r r; do
      [ -n "$r" ] || continue
      v="$(cell "$r" 2)"
      if has "$v" "$re"; then row="$r"; break; fi
    done <<< "$PLACE_ROWS"
    [ -n "$row" ] || { WHY="no place row for $label (/$re/)"; return 1; }
    h="$(cell "$row" 3)"; c="$(cell "$row" 4)"
    [ -n "$h" ] && [ "$h" != "—" ] || { WHY="the place row for $label says nothing it holds"; return 1; }
    has "$c" "$catre" || { WHY="the place row for $label holds no category matching /$catre/: '$c'"; return 1; }
  done <<< "$PLACES"
}
check 'the places outside the code are listed with what they hold' k01_places

k01_event_copy_staff() {
  local c; c="$(awk -F'|' 'tolower($2) ~ /off-server copy of keycloak events/ { print $4 }' <<< "$PLACE_ROWS")"
  has "$c" 'PD-S1' && has "$c" 'PD-S2' || { WHY="the off-server event copy is not listed as a holder of PD-S1 account fields and PD-S2: '$c'"; return 1; }
}
check 'the off-server event copy is a holder of staff personal data' k01_event_copy_staff

# (3) Every environment, pilot included, holds only synthetic customer data until the assessment.
SYN="$(sub_sents '^### Synthetic customer data until the impact assessment')"
k01_synthetic() {
  local s; s="$(grep -Ei 'holds? only synthetic customer data' <<< "$DECISION_SENTS")"
  [ -n "$s" ] || { WHY="no Decision sentence says what holds only synthetic customer data"; return 1; }
  grep -Eiq '^(- )?Until the GDPR impact assessment, every environment, the pilot included, holds only synthetic customer data\.$' <<< "$s" \
    || { WHY="the synthetic-data sentence does not read 'Until the GDPR impact assessment, every environment, the pilot included, holds only synthetic customer data.': $(head -n 1 <<< "$s" | cut -c1-200)"; return 1; }
  # A narrower scope anywhere ("Production holds only synthetic ..."), or real customer data allowed.
  forbid "$s" '^(- )?(production|the production environment|shared environments?|go-live)\b' || return 1
  forbid "$DECISION_SENTS" '\breal customer data\b[^.]*\b(may|can|is allowed|are allowed|is permitted)\b' || return 1
  forbid "$DECISION_SENTS" '\bpilot\b[^.]*\b(may|can) (hold|contain|use|receive)\b[^.]*\breal\b' || return 1
}
check 'every environment, the pilot included, holds only synthetic customer data until the GDPR impact assessment' k01_synthetic

# (4) Staff personal data is real from the first shared environment (C-2 A).
k01_staff_real() {
  need "$SYN" '^(- )?Staff personal data is real from the first shared environment, the pilot included, and falls under this decision.s staff rules' 'Synthetic customer data until the impact assessment' || return 1
  local all; all="$(sed -E 's/Developer and test environments, which are not shared environments, hold only invented staff accounts\./EXCUSED-DEV-ENV./' <<< "$DECISION_SENTS")"
  forbid "$all" '\b(staff|accounts?)\b[^.]*\b(pilot|shared environments?|production)\b[^.]*\b(test|synthetic|invented|dummy|fake|sample) (staff )?accounts?\b' || return 1
  forbid "$all" '\b(pilot|shared environments?)\b[^.]*\b(staff|accounts?)\b[^.]*\b(are|is) (test|synthetic|invented|dummy|fake)\b' || return 1
}
check 'staff personal data is real from the first shared environment and falls under the staff rules' k01_staff_real

# Edges of K-01.
k01_free_text() {
  local c; c="$(sub_sents '^### Categories of personal data')"
  need "$c" 'PD-C3 items are treated as able to hold any personal data' 'Categories of personal data' || return 1
  need "$c" 'of a third person' 'Categories of personal data' || return 1
  local ids; ids="$(cats_of C '^the note on (each|every|the) phone'; cats_of C '^the note text'; cats_of C '^the action description')"
  [ "$(sort -u <<< "$ids" | grep -c .)" -eq 1 ] && grep -Fxq 'PD-C3' <<< "$(sort -u <<< "$ids")" || { WHY="the contact note, note text and action description are not all in PD-C3: $(tr '\n' ' ' <<< "$ids")"; return 1; }
}
check 'free-text fields are classified as able to hold any personal data, a third person included' k01_free_text

k01_natural_person() {
  local c; c="$(sub_sents '^### Categories of personal data')"
  need "$c" '^Every customer is treated as a natural person, whatever its legal form' 'Categories of personal data' || return 1
  need "$c" 'sole trader.s NIP identifies a person' 'Categories of personal data' || return 1
  forbid "$DECISION_SENTS" '\b(company|companies|legal persons?|business(es)?)\b[^.]*\b(is|are) not personal data\b' || return 1
}
check "every customer is treated as a natural person and a sole trader's NIP is personal data" k01_natural_person

k01_assessment_revises() {
  need "$DECISION_SENTS" 'impact assessment; it may revise this decision' 'the Decision' || return 1
  # Not written as a forward to a task: the assessment has no PLAN entry.
  local fr; fr="$(sub_paras '^### Forward references' | grep -E '^- ' | grep -Ei 'impact assessment; it may revise')"
  grep -Eq '^- Not decided' <<< "$fr" || { WHY="the impact-assessment forward reference is not 'Not decided': $(cut -c1-120 <<< "$fr")"; return 1; }
  forbid "$fr" 'EKO-[0-9]+-[0-9]+' || return 1
}
check 'the Decision says the impact assessment may revise it, without a forward to a task' k01_assessment_revises

k01_browser() {
  local b; b="$(sub_sents '^### The user.s browser')"
  need "$b" 'holds personal data only in the memory of an open page' 'The user.s browser' || return 1
  need "$b" 'localStorage, sessionStorage, IndexedDB or the Cache Storage API' 'The user.s browser' || return 1
  need "$b" 'does not put a customer field value or a search term into its own location' 'The user.s browser' || return 1
  need "$b" 'Cache-Control: no-store' 'The user.s browser' || return 1
}
check "the user's browser is a listed place with its cache and URL history addressed" k01_browser

k01_google() {
  local g; g="$(sub_sents '^### Data sent to Google')"
  need "$g" '^(- )?Only the data a visit.s calendar event needs is sent to Google' 'Data sent to Google' || return 1
  need "$g" 'Never an e-mail address, a NIP or foreign tax identifier, the note on a phone or e-mail, note text or an action' 'Data sent to Google' || return 1
  # Fix round 1 (D-3): the forward names the receiving task and lets ADR-0006 decide the list.
  need "$g" '^- This decision forwards to EKO-1-05 \(#18\), for ADR-0006 to decide: the list of each field sent, within this rule;' 'Data sent to Google' || return 1
  pairs_ok "$g" || return 1
}
check 'Google Calendar carries only the data a visit needs and ADR-0006 (EKO-1-05, #18) lists the fields' k01_google

# ==== K-02 ===================================================================================

LOGS_P="$(sub_paras '^### What may appear in logs')"
LOGS="$(sents <<< "$LOGS_P")"
NEVER="$(awk '/^Never written to any log/ { on = 1; next } on && /^- / { print; next } on { exit }' <<< "$LOGS_P")"

k02_components() {
  need "$LOGS_P" '^- The backend \(backend, migrate and any worker\) may write:' 'What may appear in logs' || return 1
  need "$LOGS_P" '^- Keycloak may write:' 'What may appear in logs' || return 1
  need "$LOGS_P" '^- PostgreSQL may write:' 'What may appear in logs' || return 1
  need "$LOGS_P" '^- The HTTPS entry point \(proxy\) may write' 'What may appear in logs' || return 1
}
check 'the backend, Keycloak, PostgreSQL and the HTTPS entry point each have a statement of what they may log' k02_components

k02_container_logs() {
  need "$LOGS" '^Never written to any log, by any component, at any level, on any path, error paths included:' 'What may appear in logs' || return 1
  need "$(sub_sents '^### Who reads logs')" '^- Container logs on the server are read only by' 'Who reads logs' || return 1
  local r; r="$(awk -F'|' 'tolower($2) ~ /container logs/ { print $3 }' <<< "$PLACE_ROWS")"
  has "$r" 'never customer data' || { WHY="the container-log place does not exclude customer data: '$r'"; return 1; }
}
check 'the logging rules cover every component at every level and container logs' k02_container_logs

k02_never_list() {
  local item
  [ -n "$NEVER" ] || { WHY="no never-list under 'Never written to any log'"; return 1; }
  for item in '^- customer field values\b' '^- note text\b' '^- request and response bodies, and the input a validation error rejected' \
              '^- query strings\b' '^- SQL statement text and statement parameters, and a database error.s detail' \
              '^- an exception.s message or arguments' '^- session identifiers\b' '^- tokens\b' \
              '^- passwords, temporary passwords included, and credential values' '^- secret values\b'; do
    has "$NEVER" "$item" || { WHY="the never-list has no item /$item/"; return 1; }
  done
}
check 'the never-list holds customer field values, note text, bodies, query strings, SQL detail, session identifiers, tokens, passwords and secret values' k02_never_list

k02_error_paths() {
  need "$NEVER" 'HTTP 422 echoing the request' 'the never-list' || return 1
  need "$NEVER" 'DETAIL of a unique violation names the duplicated value, for example the NIP of a CUS-6' 'the never-list' || return 1
  need "$NEVER" 'Pydantic validation error, a database driver error' 'the never-list' || return 1
  need "$NEVER" 'cookie value' 'the never-list' || return 1
}
check 'error paths are in the never-list: a 422 echo, the unique-violation detail and exception messages' k02_error_paths

# (3) The secrets item is ADR-0004 l.175's rule, with no exception added (K-07 edge too).
k02_secret_rule() {
  local s
  need "$LOGS" '^No component writes a secret value to its log\.$' 'What may appear in logs' || return 1
  need "$LOGS" '^This is ADR-0004.s rule \(\*Secret handling\*\), restated without change\.$' 'What may appear in logs' || return 1
  grep -Fq 'No component writes a secret value to its log; what else may appear in logs is decided by' <<< "$(paras <<< "$ADR4_TEXT")" || { WHY="ADR-0004 no longer holds the rule restated"; return 1; }
  s="$(grep -Ei '\bsecrets?( values?)?\b' <<< "$DECISION_SENTS" | grep -Ei '\blogs?\b')"
  forbid "$s" '\b(except|unless|but|other than|apart from|save|only (at|in|when)|at (debug|trace) level|in (developer|test|development) environments?|may|can)\b' || return 1
}
check "the secrets item restates ADR-0004's rule without an exception" k02_secret_rule

# (4) Readers named by function, pilot included.
k02_readers() {
  local w; w="$(sub_sents '^### Who reads logs')"
  need "$w" '^- Container logs on the server are read only by the IT department.s staff who hold administrative rights over the container runtime' 'Who reads logs' || return 1
  need "$w" 'This holds for the pilot as for production, because pilot logs hold real staff data' 'Who reads logs' || return 1
  need "$w" 'receives only an extract that the IT department hands over for a named incident or defect' 'Who reads logs' || return 1
}
check 'the readers of logs are named by function, the pilot included' k02_readers

# (5) No Decision sentence lets a never-list item into a log. Sentences that state the ban are
# excused by their exact text only; any other sentence pairing a log verb with an item fails.
LOG_VERB='\b(logs?|logged|logging|writes?|wrote|written|prints?|printed|emits?|emitted|dumps?|dumped|echo(es|ed)?|recorded|traces?|traced)\b'
# Fix round 1 (R-05, B-02): an error's message and the typed username are items too. The first
# version had no "message", so "errors with their SQLSTATE and primary message" passed (reviewer).
# Fix round 2: a literal or a failing value is an item too; "PostgreSQL may also write the failing
# literal of an error." passed the round-1 suite (reviewer, round 1).
LOG_ITEM='\b(request|response) bod(y|ies)\b|\brejected (request|input|body|value)s?\b|\bquery strings?\b|\bstatements?\b|\bparameters?\b|\bDETAIL\b|\berror detail\b|\bsession identifiers?\b|\bsession id\b|\bcookies?\b|\btokens?\b|\bauthorization codes?\b|\bpasswords?\b|\bcredential values?\b|\bsecret values?\b|\bNIP\b|\bnote text\b|\baction descriptions?\b|\bcustomer (field )?(values?|names?|data)\b|\bphones?\b|\be-mail address(es)?\b|\bstack traces?\b|\bexception.s message\b|\bheaders?\b|\bpayloads?\b|\b(error|primary|exception|failure|database|driver)( primary)? messages?\b|\bmessages? texts?\b|\b(its|their|the) messages?\b|\btyped usernames?\b|\binput values?\b|\bsearch terms?\b|\b(failing |offending |invalid |rejected )?literals?\b|\b(failing|offending|invalid) (values?|inputs?)\b'
K02_EXCUSED=(
  "- an exception's message or arguments where they can carry a value of the request or of a row (a Pydantic validation error, a database driver error); the exception's type and code location may be written;"
  "Logs and the off-server copy of Keycloak events: they hold no customer data (What may appear in logs, Keycloak events off the server)."
  "It writes no customer data and no staff data to localStorage, sessionStorage, IndexedDB or the Cache Storage API, and registers no service worker that caches API responses (the brief excludes offline mode)."
  "| Container logs on the server | what What may appear in logs allows: staff data only, never customer data | PD-S2, PD-S3 subject identifiers |"
  "- query strings;"
  "- tokens: access, refresh and ID tokens, authorization codes, the OIDC state and nonce, the PKCE verifier, and Google tokens;"
  "No component writes a secret value to its log."
  "It writes no error message text, no statement text, no statement parameters and no error detail, for the application's database and Keycloak's alike: an error's primary message can carry an input value (an invalid date, a full-text search term)."
  "It writes no query string and no request or response header value other than the host name."
  "Staff IP addresses in its log are staff personal data under PD-S2."
  "- The other services (frontend's static file server, backup) write no personal data: frontend writes no per-request log or one under the entry point's rule above; backup writes its run's times, outcome and row counts, never a row's content."
  "- The HTTPS entry point (proxy) may write, per request: the time, the client IP address, the host name, the method, the path without its query string, the status, the size and the duration; and its own certificate and listener messages."
  "It carries no token, no credential value and no session or authentication-session identifier, and, for a failed login naming no existing account, not the typed username."
  "- Keycloak may write: its start, stop and configuration messages without secret values; errors; and, for each event, the event type, realm, client, the staff account's identifier and username, the IP address and the error code."
  "Each copied event carries its type, realm, time, client, acting and affected account, IP address, error, and for an admin event its resource path and representation."
  # Fix round 1: the typed-username ban (B-02) and PostgreSQL's error bound (R-05), by exact text.
  "For a failed login naming no existing account, the typed username is not logged, not stored in an event and not shipped: it may be a password typed into the wrong field."
  "- PostgreSQL may write: connection and authentication events (the role, the database, the client address inside the composition), its own start, stop, checkpoint and recovery messages, and, for an error, at most its SQLSTATE and its position in the statement."
  # A forward of the log settings to EKO-1-06, not an allowance (fix round 2: with its D-5 stop).
  "- EKO-1-06 (#19) receives: the application realm's event settings in the export under identity/, the master realm's event settings at bootstrap, the log settings of each service (PostgreSQL's error logging and Keycloak's typed username of a failed login naming no existing account included) and the time-bound deletion of logs in the composition, the backend's log and error-handling rules, and Cache-Control: no-store; it stops under What may appear in logs if the official Keycloak image cannot keep that typed username out."
  # Fix round 2: the entry's content, which states a ban ("recorded" is said of the commit time).
  # Fix round 2: the EKO-1-09 forward, which now names "What may appear in logs" in its D-5 stop.
  "- EKO-1-09 (#41) receives: shipping Keycloak events off the server, without the typed username of a failed login naming no existing account; it stops under What may appear in logs if the official Keycloak image cannot keep that typed username out."
  "An entry holds the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, never a customer field value."
)
k02_no_allowance() {
  local all; all="$(without "$DECISION_SENTS" "${K02_EXCUSED[@]}")"
  forbid "$all" "($LOG_VERB)[^.]*($LOG_ITEM)" || return 1
  forbid "$all" "($LOG_ITEM)[^.]*\\b(is|are|may be|gets?|get) (logged|written|recorded|printed)\\b" || return 1
  forbid "$all" "($LOG_ITEM)[^.]*\\bappears? in\\b[^.]*\\blogs?\\b" "\\b(no|not|never|neither)\\b[^.]*\\bappears?\\b" || return 1
}
check "no Decision sentence lets a never-list item into any component's log" k02_no_allowance

# (6) No sentence gives the log reader container-runtime rights.
K02_RUNTIME_EXCUSED=(
  "- The reviewer reads no container log and is given no right over the container runtime for it (ADR-0004 Operator duties)."
  "- Container logs on the server are read only by the IT department's staff who hold administrative rights over the container runtime (ADR-0004 Secret handling), for operating the environment and handling incidents."
)
k02_no_runtime_reader() {
  local all; all="$(without "$DECISION_SENTS" "${K02_RUNTIME_EXCUSED[@]}")"
  forbid "$all" '\bdocker (logs|exec|inspect)\b|\b(kubectl|podman) logs\b' || return 1
  forbid "$all" '\b(reviewer|developers?|anyone else|administrator role|holders? of the application role)\b[^.]*\b(container runtime|container logs?|docker|superuser)\b' || return 1
  forbid "$all" '\b(container runtime|container logs?)\b[^.]*\b(reviewer|developers?)\b' || return 1
  forbid "$all" '\breads?\b[^.]*\bcontainer logs?\b' || return 1
}
check 'no Decision sentence gives the log reader container-runtime rights' k02_no_runtime_reader

k02_access_log() {
  need "$LOGS" 'the path without its query string' 'What may appear in logs' || return 1
  need "$LOGS" '^It writes no query string\b' 'What may appear in logs' || return 1
}
check "the entry point's access log carries no query string" k02_access_log

k02_staff_in_logs() {
  need "$LOGS" 'the staff account.s identifier and username, the IP address and the error code' 'What may appear in logs' || return 1
  need "$LOGS" '^Staff IP addresses in its log are staff personal data under PD-S2\.$' 'What may appear in logs' || return 1
  need "$LOGS" 'Keycloak does not run at debug or trace level in a shared environment' 'What may appear in logs' || return 1
}
check "staff usernames and IP addresses in Keycloak's and the entry point's logs are stated" k02_staff_in_logs

# ---- fix round 1 (R-05, B-02, S-02) ----
CONTROLS_P="$(printf '%s\n' "$ADR5_TEXT" | section '^## Controls' | paras)"
control() { grep -E "^\| ADR-0005-$1 \|" <<< "$CONTROLS_P"; }

# R-05: PostgreSQL logs an error by its SQLSTATE and position only; no message text.
k02_postgres_errors() {
  local pg; pg="$(grep -E '^- PostgreSQL may write:' <<< "$LOGS_P")"
  [ "$(grep -c . <<< "$pg")" -eq 1 ] || { WHY="expected one PostgreSQL bullet"; return 1; }
  need "$pg" '^- PostgreSQL may write: connection and authentication events \(the role, the database, the client address inside the composition\), its own start, stop, checkpoint and recovery messages, and, for an error, at most its SQLSTATE and its position in the statement\. ' 'the PostgreSQL bullet' || return 1
  need "$pg" ' It writes no error message text, no statement text, no statement parameters and no error detail, for the application.s database and Keycloak.s alike: an error.s primary message can carry an input value' 'the PostgreSQL bullet' || return 1
  # Nothing else in the Decision lets an error's message into PostgreSQL's log.
  local all; all="$(without "$DECISION_SENTS" "${K02_EXCUSED[@]}")"
  forbid "$all" '\b(postgres(ql)?|database)\b[^.]*\b(primary )?messages?\b' '\b(its own start, stop|start, stop and configuration messages)\b' || return 1
  forbid "$all" '\bSQLSTATE\b' || return 1
  # Fix round 2: the PostgreSQL bullet is the only allowance for PostgreSQL's log. Any other
  # sentence letting PostgreSQL write something fails, whatever the item (reviewer, round 1:
  # "PostgreSQL may also write the failing literal of an error." passed).
  forbid "$all" '\bpostgres(ql)?\b[^.]*\b(may|can|is allowed to)( also)? (write|log|record|emit|print|keep)\b|\bpostgres(ql)?\b[^.]*\b(also )?(writes|logs|records|emits|prints)\b' || return 1
  need "$(control C3)" 'a statement that fails PostgreSQL.s input parsing on a marker value leaves the marker in no line of PostgreSQL.s log' 'ADR-0005-C3' || return 1
}
check "PostgreSQL logs an error by its SQLSTATE and position in the statement only, never its message text" k02_postgres_errors

# B-02: the username typed in a failed login naming no existing account (it may be a password).
K02_TYPED_EXCUSED=(
  "For a failed login naming no existing account, the typed username is not logged, not stored in an event and not shipped: it may be a password typed into the wrong field."
  "It carries no token, no credential value and no session or authentication-session identifier, and, for a failed login naming no existing account, not the typed username."
  "- EKO-1-06 (#19) receives: the application realm's event settings in the export under identity/, the master realm's event settings at bootstrap, the log settings of each service (PostgreSQL's error logging and Keycloak's typed username of a failed login naming no existing account included) and the time-bound deletion of logs in the composition, the backend's log and error-handling rules, and Cache-Control: no-store; it stops under What may appear in logs if the official Keycloak image cannot keep that typed username out."
  "- EKO-1-09 (#41) receives: shipping Keycloak events off the server, without the typed username of a failed login naming no existing account; it stops under What may appear in logs if the official Keycloak image cannot keep that typed username out."
  # Fix round 2 (D-5): the stop rule and the human's decision recording it, by exact text.
  "If the official image cannot keep the typed username out."
  "The rule on the typed username works with the official Keycloak image (ADR-0004)."
  "If the implementing task, EKO-1-06 (#19) or EKO-1-09 (#41), finds that the official Keycloak image cannot leave the typed username of a failed login naming no existing account out of its log and its stored events, that task stops and the change returns to the human as an addendum to this decision, before any provider or image is added and before the stored event types of Retention are changed."
  "On 2026-10-26, after the second evaluation, the human decided that a restore re-applies every entry of the erasure record not marked failed or cancelled, that the IT department reconciles the record with the live application database, and that an official Keycloak image unable to keep the typed username of a failed login naming no existing account out of its log and stored events returns the change to the human as an addendum to this decision."
)
k02_typed_username() {
  local kc; kc="$(grep -E '^- Keycloak may write:' <<< "$LOGS_P")"
  need "$kc" 'For a failed login naming no existing account, the typed username is not logged, not stored in an event and not shipped' 'the Keycloak bullet' || return 1
  need "$(sub_paras '^### Keycloak events off the server' | grep -Ei '^- Which events\.')" 'and, for a failed login naming no existing account, not the typed username\.' 'Which events' || return 1
  local fr; fr="$(sub_paras '^### Forward references')"
  need "$(grep -E '^- EKO-1-09 ' <<< "$fr")" 'without the typed username of a failed login naming no existing account' 'the EKO-1-09 forward' || return 1
  need "$(grep -E '^- EKO-1-06 ' <<< "$fr")" 'Keycloak.s typed username of a failed login naming no existing account included' 'the EKO-1-06 forward' || return 1
  need "$(control C5)" 'a failed login whose typed username is a marker naming no existing account' 'ADR-0005-C5' || return 1
  need "$(control C5)" 'session identifier or the marker' 'ADR-0005-C5' || return 1
  need "$(control C11)" 'or, for a failed login naming no existing account, the typed username' 'ADR-0005-C11' || return 1
  # Every other Decision sentence naming the typed username is a new statement about it: fail.
  forbid "$(without "$DECISION_SENTS" "${K02_TYPED_EXCUSED[@]}")" '\btyped (user ?names?|logins?|account names?)\b|\busername (typed|entered|given)\b' || return 1
}
check "the typed username of a failed login naming no existing account is never logged, stored in an event or shipped" k02_typed_username

# Fix round 2 (D-5, U-02/U-05): if the official Keycloak image cannot keep the typed username out,
# the implementing task stops and the change returns to the human, written as the G-9 shipping rule.
K02_STOP_EXCUSED=(
  "If the implementing task, EKO-1-06 (#19) or EKO-1-09 (#41), finds that the official Keycloak image cannot leave the typed username of a failed login naming no existing account out of its log and its stored events, that task stops and the change returns to the human as an addendum to this decision, before any provider or image is added and before the stored event types of Retention are changed."
  "If the implementing task finds that it cannot, that task stops and the change returns to the human as an addendum to ADR-0004, before any service or image is added."
)
k02_keycloak_stop() {
  local kc fr; kc="$(grep -E '^- Keycloak may write:' <<< "$LOGS_P")"
  need "$kc" ' If the official image cannot keep the typed username out\. The rule on the typed username works with the official Keycloak image \(ADR-0004\)\. If the implementing task, EKO-1-06 \(#19\) or EKO-1-09 \(#41\), finds that the official Keycloak image cannot leave the typed username of a failed login naming no existing account out of its log and its stored events, that task stops and the change returns to the human as an addendum to this decision, before any provider or image is added and before the stored event types of \*?Retention\*? are changed\.' 'the Keycloak bullet' || return 1
  # The same form as the G-9 shipping rule it is modelled on, which must still read so.
  need "$DECISION_SENTS" '^If the implementing task finds that it cannot, that task stops and the change returns to the human as an addendum to ADR-0004, before any service or image is added\.$' 'the G-9 shipping rule' || return 1
  fr="$(sub_paras '^### Forward references')"
  need "$(grep -E '^- EKO-1-06 ' <<< "$fr")" '; it stops under \*?What may appear in logs\*? if the official Keycloak image cannot keep that typed username out\.$' 'the EKO-1-06 forward' || return 1
  need "$(grep -E '^- EKO-1-09 ' <<< "$fr")" '; it stops under \*?What may appear in logs\*? if the official Keycloak image cannot keep that typed username out\.$' 'the EKO-1-09 forward' || return 1
  need "$(sub_sents '^### Changes to accepted decisions')" 'and that an official Keycloak image unable to keep the typed username of a failed login naming no existing account out of its log and stored events returns the change to the human as an addendum to this decision\.$' 'Changes to accepted decisions' || return 1
  # No other sentence adds a provider, an extension or another image, or stops storing the event
  # types of Retention, instead of returning the change to the human.
  local all; all="$(without "$DECISION_SENTS" "${K02_STOP_EXCUSED[@]}")"
  forbid "$all" '\b(providers?|extensions?|SPIs?|event listeners?|plugins?|custom (images?|builds?|themes?)|(another|own|derived|patched) images?)\b' '\bcloud provider\b' || return 1
  forbid "$all" '\b(LOGIN_ERROR|login errors?|stored event types?)\b[^.]*\b(not|never|no longer) (be )?(stored|kept)\b|\b(stored event types?)\b[^.]*\b(changed|reduced|removed|dropped)\b' || return 1
}
check "if the official Keycloak image cannot keep the typed username out, the implementing task stops and the change returns to the human (D-5)" k02_keycloak_stop

# S-02: the backend's correlation identifier, its own, never a client value.
k02_correlation() {
  local be; be="$(grep -E '^- The backend \(backend, migrate and any worker\) may write:' <<< "$LOGS_P")"
  need "$be" 'the request.s correlation identifier \(generated by the backend, never taken from a client value, and also carried by the error response\)' 'the backend bullet' || return 1
  local n; n="$(grep -Eic '\b(correlation|request|trace) (identifier|id)s?\b' <<< "$DECISION_SENTS")"
  [ "$n" -eq 1 ] || { WHY="$n Decision sentences name a correlation, request or trace identifier; only the backend bullet may"; return 1; }
}
check "the backend may log a correlation identifier it generates itself, never one taken from a client value" k02_correlation

# ==== K-03 ===================================================================================

RET_P="$(sub_paras '^### Retention')"
RET="$(sents <<< "$RET_P")"
ret() {  # ret <bullet start ERE> — the one Retention bullet starting so
  grep -Ei -- "^- $1" <<< "$RET_P"
}
one_ret() {  # one_ret <start ERE> <what>
  local b; b="$(ret "$1")"
  [ "$(grep -c . <<< "$b")" -eq 1 ] || { WHY="expected one Retention bullet for $2, found $(grep -c . <<< "$b")"; return 1; }
}
EVC="$(sub_paras '^### Keycloak events off the server')"

k03_sessions() {
  one_ret 'Server-side sessions,' 'server-side sessions' || return 1
  local b; b="$(ret 'Server-side sessions,')"
  need "$b" '^- Server-side sessions, abandoned ones included, are deleted together with their encrypted tokens no later than the realm.s SSO session maximum lifespan after the session was created\.' 'the session bullet' || return 1
  forbid "$RET" '\bsessions?\b[^.]*\b(after|from|since) (the |its )?(last use|last used|last activity|last request|inactivity|being idle|logout)\b' || return 1
  forbid "$RET" '\bsessions?\b[^.]*\b(was|were|is|are) last used\b' || return 1
  forbid "$(grep -Ei '\bsessions?\b' <<< "$RET" | grep -Eiv 'inside backup sets')" "\\b($NUMW) ($UNITW)\\b" '\baccess token of at most\b' || return 1
}
check 'server-side sessions, abandoned ones included, are deleted with their encrypted tokens no later than the SSO session maximum after creation' k03_sessions

k03_login_tx() {
  one_ret 'Login transactions,' 'login transactions' || return 1
  local b; b="$(ret 'Login transactions,')"
  need "$b" 'abandoned ones included, are deleted no later than' 'the login-transaction bullet' || return 1
  need "$b" 'after they were created' 'the login-transaction bullet' || return 1
  fig_eq "$b" 'no later than' "$G2_LOGIN_TX" 'login-transaction retention' || return 1
}
check 'login transactions are deleted no later than the gate-1 figure after creation' k03_login_tx

# Keycloak events kept on the server: item start | anchor | constant | must be longer than the review
EVENT_ITEMS="Admin events of the application realm are stored and kept in Keycloak|$G2_ADMIN_APP|admin events of the application realm
Admin events of the master realm are stored and kept in Keycloak|$G2_ADMIN_MASTER|admin events of the master realm
Login events of the master realm are stored and kept in Keycloak|$G2_LOGIN_MASTER|master-realm login events"
k03_event_bound() {
  local start c what b v
  while IFS='|' read -r start c what; do
    [ -n "$start" ] || continue
    one_ret "$start" "$what" || return 1
    b="$(ret "$start")"
    v="$(fig "$b" 'for')"
    [ -n "$v" ] || { WHY="$what: no number with its unit"; return 1; }
    [ "$v" -gt 0 ] || { WHY="$what: zero"; return 1; }
    [ "$v" -gt "$REVIEW_INTERVAL" ] || { WHY="$what kept $v minutes, not longer than the 7-day review interval ($REVIEW_INTERVAL)"; return 1; }
    need "$b" 'after the event' "the $what bullet" || return 1
  done <<< "$EVENT_ITEMS"
}
check 'admin events of both realms and master-realm login events are kept longer than the 7-day review interval' k03_event_bound

k03_event_figures() {
  local start c what
  while IFS='|' read -r start c what; do
    [ -n "$start" ] || continue
    fig_eq "$(ret "$start")" 'for' "$c" "$what" || return 1
  done <<< "$EVENT_ITEMS"
}
check 'admin events of both realms and master-realm login events equal the gate-1 figures' k03_event_figures

K03_ZERO_EXCUSED=("- No retention of admin events is zero, and admin events are never switched off in any realm of any shared environment (ADR-0003 Administrator permissions in Keycloak).")
k03_never_zero() {
  need "$RET" '^- No retention of admin events is zero, and admin events are never switched off in any realm of any shared environment' 'Retention' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K03_ZERO_EXCUSED[@]}")"
  forbid "$all" '\badmin events?\b[^.]*(\b(switched off|turned off|disabled|not stored|zero|0 (days?|minutes?|hours?))\b|\b(is|are|be|stays?) off([^-a-z]|$))' || return 1
  forbid "$all" '\b(switch|turn)(es|ed|ing)? off\b[^.]*\badmin events?\b' || return 1
  forbid "$RET" "\\b(zero|0) ($UNITW)\\b" || return 1
}
check 'admin events are never zero and never switched off' k03_never_zero

k03_app_login() {
  one_ret 'Login events of the application realm' 'application-realm login events' || return 1
  local b; b="$(ret 'Login events of the application realm')"
  if has "$b" '^- Login events of the application realm are not stored\b'; then
    WHY="application-realm login events are 'not stored'; the gate-1 answer (G-2) stores them for 30 days"; return 1
  fi
  need "$b" '^- Login events of the application realm are stored, for the authentication event types only, and kept in Keycloak for' 'the application-realm login-event bullet' || return 1
  fig_eq "$b" 'kept in Keycloak for' "$G2_LOGIN_APP" 'application-realm login-event retention' || return 1
  need "$b" 'Successful token refreshes \(REFRESH_TOKEN\) and code-to-token exchanges \(CODE_TO_TOKEN\) are never stored' 'the application-realm login-event bullet' || return 1
  local t
  for t in '\blogin, login error\b' '\blogout\b' '\bpassword update and its error\b' '\bpassword reset, its error and the sending of a reset e-mail\b' '\brefresh error\b' '\baccount lockout by brute-force detection\b'; do
    has "$b" "$t" || { WHY="the stored application-realm types miss /$t/"; return 1; }
  done
}
check 'application-realm login events are stored for the authentication types only, at the gate-1 figure' k03_app_login

k03_display_name() {
  one_ret 'The display-name copy' 'the display-name copy' || return 1
  local b; b="$(ret 'The display-name copy')"
  need "$b" 'is kept while at least one record in the application refers to the subject, and is deleted together with the last such record' 'the display-name bullet' || return 1
  need "$b" 'A copy that no record refers to is deleted no later than [^.]* after the subject.s last login' 'the display-name bullet' || return 1
  fig_eq "$b" 'no later than' "$G2_DISPLAY" 'display-name copy retention' || return 1
}
check 'the display-name copy ends with the last record referring to it, or the gate-1 figure after the last login' k03_display_name

k03_logs() {
  one_ret 'Logs of every service' 'logs' || return 1
  local b s; b="$(ret 'Logs of every service')"
  for s in backend migrate keycloak postgres proxy frontend backup; do
    has "$b" "\\b$s\\b" || { WHY="the log bullet does not name the service $s"; return 1; }
  done
  need "$b" 'are deleted no later than [^.]* after they were written, also when they are small' 'the log bullet' || return 1
  fig_eq "$b" 'no later than' "$G2_LOGS" 'log retention' || return 1
  need "$b" 'deletion is by time, and rotation by size alone does not meet this rule' 'the log bullet' || return 1
  local all; all="$(sed -E 's/rotation by size alone does not meet this rule/EXCUSED-SIZE/' <<< "$DECISION_SENTS")"
  forbid "$all" '\b(rotat\w*|delet\w*|kept|keeps?|retain\w*|logs?)\b[^.]*\b(by size|max-size|max-file|megabytes?|MB|GB|size limit)\b' || return 1
  forbid "$all" '\b(by size|max-size|max-file|size limit)\b[^.]*\b(rotat\w*|delet\w*|kept|retain\w*|logs?)\b' || return 1
}
check 'logs of every service are deleted by time at the gate-1 figure, not by size alone' k03_logs

k03_no_forever() {
  forbid "$RET" '\b(forever|indefinitely|unlimited|without (a |any )?(limit|end)|with no end|no (time )?limit|permanently|for ever)\b' || return 1
  forbid "$(sents <<< "$EVC")" '\b(forever|indefinitely|unlimited|without (a |any )?(limit|end)|with no end|no (time )?limit|permanently|for ever)\b' || return 1
}
check 'no retention reads forever, indefinitely or unlimited' k03_no_forever

# The off-server copy of Keycloak events (C-1 A): which, where to, how often, how long, by whom.
k03_copy_which() {
  local w; w="$(grep -Ei '^- Which events\.' <<< "$EVC")"
  need "$w" 'The admin events of the application realm and of the master realm, with their representation; the login events of the master realm; and the login events of the application realm that \*Retention\* stores' 'Which events' || return 1
}
check 'the off-server copy names which events of which realms are copied' k03_copy_which

K03_DEST_EXCUSED=("Append-only storage on a host operated by the IT department that is off the server in the sense of ADR-0004 Backup (Destination: off the server): another host, not a second disk, volume or directory of the server's own host.")
k03_copy_where() {
  local w; w="$(grep -Ei '^- Where to\.' <<< "$EVC")"
  [ -n "$w" ] || { WHY="no 'Where to.' item in Keycloak events off the server"; return 1; }
  need "$w" 'Append-only storage on a host operated by the IT department that is off the server in the sense of ADR-0004 \*?Backup\*?' 'Where to' || return 1
  need "$w" 'another host, not a second disk, volume or directory of the server.s own host' 'Where to' || return 1
  need "$w" 'can add events but cannot delete or overwrite any' 'Where to' || return 1
  local all; all="$(without "$(sents <<< "$EVC")" "${K03_DEST_EXCUSED[@]/#/- Where to. }")"
  all="$(without "$all" "${K03_DEST_EXCUSED[@]}")"
  forbid "$all" '\b(second|separate|another|other|dedicated|extra) (disk|volume|directory|partition|folder)\b' || return 1
  forbid "$all" '\b(on|of|in) the (application )?server\b[^.]*\b(volume|disk|directory)\b|\b(volume|disk|directory)\b[^.]*\bon the (application )?server\b' || return 1
}
check 'the off-server copy goes to append-only storage on another host, off the server in ADR-0004 Backup sense' k03_copy_where

k03_copy_often() {
  local w; w="$(grep -Ei '^- How often\.' <<< "$EVC")"
  [ -n "$w" ] || { WHY="no 'How often.' item"; return 1; }
  fig_eq "$w" 'at least every' "$C1_SHIP" 'the shipment interval' || return 1
  need "$w" 'also when no event is new \(a heartbeat\)' 'How often' || return 1
  need "$w" 'a check that does not run on the server alerts the IT department when no shipment has arrived for' 'How often' || return 1
  fig_eq "$w" 'has arrived for' "$C1_ALERT" 'the missing-shipment alert' || return 1
}
check 'the off-server copy runs at a stated interval with a heartbeat and an off-server alert' k03_copy_often

k03_copy_long() {
  local w r; w="$(grep -Ei '^- How long kept there\.' <<< "$EVC")"
  [ -n "$w" ] || { WHY="no 'How long kept there.' item"; return 1; }
  fig_eq "$w" 'master-realm login events:' "$G2_COPY_ADMIN" 'the off-server copy of admin and master-realm login events' || return 1
  fig_eq "$w" 'Application-realm login events:' "$G2_COPY_APPLOGIN" 'the off-server copy of application-realm login events' || return 1
  need "$w" 'Admin events of both realms and master-realm login events:' 'How long kept there' || return 1
  need "$w" 'Deletion is done by the destination.s own housekeeping, not by the server' 'How long kept there' || return 1
  # The Retention bullet says the same.
  one_ret 'The off-server copy of Keycloak events' 'the off-server event copy' || return 1
  r="$(ret 'The off-server copy of Keycloak events')"
  fig_eq "$r" 'master-realm login events for' "$G2_COPY_ADMIN" 'the Retention bullet of the copy (admin and master-realm login events)' || return 1
  fig_eq "$r" 'application-realm login events for' "$G2_COPY_APPLOGIN" 'the Retention bullet of the copy (application-realm login events)' || return 1
}
check 'the off-server copy is kept for the gate-1 figures, in Retention and in its own section alike' k03_copy_long

k03_copy_task() {
  local w; w="$(grep -Ei '^- Implemented by ' <<< "$EVC")"
  [ "$(grep -c . <<< "$w")" -eq 1 ] || { WHY="expected one 'Implemented by' item in Keycloak events off the server"; return 1; }
  grep -Eq '^- Implemented by EKO-[0-9]+-[0-9]+ \(#[0-9]+\)\.$' <<< "$w" || { WHY="the implementing task is not given as EKO-x-yy (#n): $w"; return 1; }
  pairs_ok "$w" || return 1
  grep -Fq 'EKO-1-09 (#41)' <<< "$w" || { WHY="the implementing task is not the one C-1 created (EKO-1-09, #41): $w"; return 1; }
  need "$(sub_paras '^### Forward references' | grep -E '^- EKO-1-09')" 'shipping Keycloak events off the server' 'Forward references' || return 1
}
check 'the off-server copy names its implementing task as EKO-x-yy (#n), resolving in docs/PLAN.md' k03_copy_task

# Fix round 1 (B-01): what shipping does not close, and the reviewer's break-glass check.
K03_B02_EXCUSED=(
  "- Exception EKO-1-03/B-02 lifts only when that task ships; the change to the exception register is the human's own edit."
  "Shipping closes the risk of exception EKO-1-03/B-02 only for events already shipped."
)
k03_residual() {
  local w; w="$(grep -Ei '^- What shipping does not close\.' <<< "$EVC")"
  [ "$(grep -c . <<< "$w")" -eq 1 ] || { WHY="expected one 'What shipping does not close.' item in Keycloak events off the server"; return 1; }
  need "$w" 'Shipping closes the risk of exception EKO-1-03/B-02 only for events already shipped\.' 'What shipping does not close' || return 1
  need "$w" 'An actor with administrative rights over the server.s container runtime or its PostgreSQL can suppress or alter events before they are shipped, and the heartbeat proves that shipping runs, not that it is complete\.' 'What shipping does not close' || return 1
  need "$w" 'This residual case stays open after EKO-1-09 \(#41\) ships\.' 'What shipping does not close' || return 1
  need "$w" 'The reviewer checks each announced break-glass use \(ADR-0004 \*?Operator duties\*?\) against its events in the off-server copy\.' 'What shipping does not close' || return 1
  grep -Fq 'break-glass' <<< "$ADR4_TEXT" || { WHY="ADR-0004 names no break-glass use"; return 1; }
  need "$(control C11)" 'each announced break-glass use was checked against its events in the copy' 'ADR-0005-C11' || return 1
  # No other sentence says shipping closes or lifts B-02 (or the residual case) outright.
  forbid "$(without "$DECISION_SENTS" "${K03_B02_EXCUSED[@]}")" '\b(clos(e|es|ed)|lift(s|ed)?|remov(e|es|ed)|resolv(e|es|ed)|eliminat(e|es|ed))\b[^.]*\b(B-02|residual case)\b|\b(B-02|residual case)\b[^.]*\b(is|are) (closed|lifted|removed|resolved)\b' || return 1
}
check "the residual case of exception B-02 is stated and the reviewer checks each break-glass use against the off-server copy" k03_residual

k03_erasure_record() {
  one_ret 'The off-server erasure record' 'the off-server erasure record' || return 1
  # Fix round 1 (D-2, R-02): counted from the erasure's commit time against the snapshot start.
  # Fix round 2 (D-4): every entry not marked failed or cancelled is kept, unmarked ones too, and
  # only once it holds a commit time does the backup-set bound start.
  need "$(ret 'The off-server erasure record')" '^- The off-server erasure record keeps each entry not marked failed or cancelled, completed entries and entries not yet marked alike, until it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination \(\*?Erasure and backups\*?\)\.$' 'the erasure-record bullet' || return 1
  forbid "$RET" '\bbackup sets? taken before\b' || return 1
  # The round-1 wording kept completed entries only (R-08): no Retention sentence keeps only those.
  forbid "$RET" '\b(keeps?|kept|retains?)\b[^.]*\b(each|every|only|the) completed entr(y|ies)\b|\bcompleted entr(y|ies) only\b' || return 1
}
check 'the off-server erasure record is kept until no backup set from before the erasure remains' k03_erasure_record

k03_all_pairs() { pairs_ok "$ADR5_TEXT"; }
check 'every EKO-x-yy task pair in ADR-0005 matches docs/PLAN.md' k03_all_pairs

k03_gh_pairs() {
  command -v gh >/dev/null 2>&1 || { WHY="gh is not installed (use --offline to skip by name)"; return 1; }
  local id n title
  while read -r id n; do
    title="$(gh issue view "$n" --repo "$REPO_SLUG" --json title -q .title 2>/dev/null)" || { WHY="gh could not read Issue #$n"; return 1; }
    case "$title" in "[$id]"*) ;; *) WHY="Issue #$n is titled '$title', not [$id]"; return 1 ;; esac
  done <<< "$PAIRS"
}
if [ -n "$OFFLINE" ]; then skip 'the identifier/Issue pairs match the Issue titles on GitHub' '--offline'
else check 'the identifier/Issue pairs match the Issue titles on GitHub' k03_gh_pairs; fi

# ==== K-04 ===================================================================================

ARCH="$(sub_sents '^### Archiving')"
ERA_P="$(sub_paras '^### Erasure$')"
ERA="$(sents <<< "$ERA_P")"
REMOVES="$(grep -Ei '^- What it removes\.' <<< "$ERA_P")"
EXCUSED_P="$(grep -Ei '^- Places excused, and why\.' <<< "$ERA_P")"
EB="$(sub_sents '^### Erasure and backups')"

k04_archive() {
  need "$ARCH" '^- Archiving a customer \(CUS-9\) keeps all of its personal data, in every place that holds it, until the customer is restored or erased\.$' 'Archiving' || return 1
  need "$ARCH" '^Until it does, the end event of an archived customer.s data is its erasure\.$' 'Archiving' || return 1
  need "$ARCH" 'Restoring a customer from the archive keeps its data' 'Archiving' || return 1
  forbid "$ARCH" '\barchiv\w*\b[^.]*\b(deletes?|removes?|anonymi[sz]es?|purges?|strips?)\b' || return 1
}
check "archiving keeps a customer's personal data until a stated end event" k04_archive

# (2) The erasure list against K-01's customer entries: item label | ERE in "What it removes".
ERASE_ITEMS="name|row with its name
NIP|\bNIP\b
address|\baddress\b
phones|every phone and e-mail
e-mails|every phone and e-mail
contact note|every phone and e-mail with its note
notes (NOT-1/2)|every note on the customer or on its visits, of every author, the manager.s notes \(NOT-2\) included
action description (ACT-1)|every action created from those notes, with its description
status-change author (ACT-2)|with its description and its status changes
visit's customer and owner|Every visit of the customer, past and future, of every owner[^.]*loses its customer reference"
k04_erasure_items() {
  local label re
  [ -n "$REMOVES" ] || { WHY="no 'What it removes.' item in Erasure"; return 1; }
  need "$REMOVES" 'Erasing a customer removes, from the application database:' 'What it removes' || return 1
  while IFS='|' read -r label re; do
    [ -n "$label" ] || continue
    has "$REMOVES" "$re" || { WHY="the erasure list does not remove the customer item '$label' (/$re/)"; return 1; }
  done <<< "$ERASE_ITEMS"
  need "$REMOVES" 'every value derived from them \(comparison and search keys\)' 'What it removes' || return 1
}
check "the erasure rule removes every customer item of K-01's inventory from the application database" k04_erasure_items

# Every place of K-01 holding a customer category: in the erasure list or excused with a reason.
# A place whose "Holds" cell is "both databases above" is held through those databases.
k04_erasure_places() {
  local row place cats holds reason
  [ -n "$EXCUSED_P" ] || { WHY="no 'Places excused, and why.' item in Erasure"; return 1; }
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    place="$(cell "$row" 2)"; holds="$(cell "$row" 3)"; cats="$(cell "$row" 4 | expand_cats)"
    grep -q '^PD-C' <<< "$cats" || continue
    has "$holds" '^both databases above$' && continue
    case "$(tr 'A-Z' 'a-z' <<< "$place")" in
      *"application database"*) reason="$(grep -Ei 'from the application database' <<< "$REMOVES")" ;;
      *"backup destination"*) reason="$(grep -Eio 'Backups: \*Erasure and backups\* below' <<< "$EXCUSED_P")" ;;
      *"google calendar"*) reason="$(grep -Eio 'Google Calendar: [^.]*forwarded to EKO-1-05 \(#18\) for ADR-0006 to decide' <<< "$EXCUSED_P")" ;;
      *"browser"*) reason="$(grep -Eio 'The user.s browser: it holds customer data only in an open page.s memory' <<< "$EXCUSED_P")" ;;
      *) reason="" ;;
    esac
    if has "$place" 'verification host'; then
      has "$EXCUSED_P" 'verification host: its decrypted copy is deleted after the check' || { WHY="the place '$place' is neither erased nor excused: the verification host"; return 1; }
      # Fix round 2 (C19): the identifiers the reconciliation compares go with the decrypted copy.
      if has "$holds" 'customer identifiers the reconciliation compares'; then
        has "$EXCUSED_P" 'verification host: its decrypted copy is deleted after the check \(ADR-0004 \*?Backup\*?\), and the customer identifiers the reconciliation compares are deleted with it' || { WHY="the verification-host excuse does not delete the customer identifiers the reconciliation compares"; return 1; }
      fi
      if has "$place" 'restore host'; then
        has "$EXCUSED_P" '\brestore host\b' || { WHY="the place '$place' is neither erased nor excused: the restore host (the excuse names only the verification host)"; return 1; }
        # Fix round 1 (F-01): the excuse says why, for the restored database and the decrypted set.
        has "$EXCUSED_P" 'A restore host: the application database restored on it is covered by the re-apply' || { WHY="the restore-host excuse does not cover the restored application database by the re-apply"; return 1; }
        has "$EXCUSED_P" 'the decrypted backup set it received at ADR-0004 restore step 3 is deleted once the restore is recorded at step 14 or abandoned' || { WHY="the restore-host excuse does not delete the decrypted backup set"; return 1; }
        # Fix round 2 (R-09, B-06): "recorded or abandoned", and an abandoned restore on any host.
        has "$EXCUSED_P" 'a restore host that does not become the server, a test restore.s host included, has its restored databases and volumes deleted once the restore is recorded or abandoned' || { WHY="the restore-host excuse does not cover a host that does not become the server, recorded or abandoned"; return 1; }
        has "$EXCUSED_P" 'an abandoned restore, on any host, has its restored databases and volumes deleted once it is abandoned' || { WHY="the restore-host excuse does not cover an abandoned restore"; return 1; }
      fi
      continue
    fi
    [ -n "$reason" ] || { WHY="the place '$place' holds customer data and is neither in the erasure list nor excused with a reason"; return 1; }
  done <<< "$PLACE_ROWS"
  need "$EXCUSED_P" 'Logs and the off-server copy of Keycloak events: they hold no customer data' 'Places excused' || return 1
}
check 'every place holding customer data is in the erasure list or excused with a reason' k04_erasure_places

# (3) Backups keep erased data only within ADR-0004's retention.
k04_backups() {
  need "$EB" '^- Erased personal data stays in the backup sets taken before the erasure until ADR-0004.s retention removes them: the sets of the last 30 days, and the verified sets kept beyond them until three newer sets have passed the verification\.$' 'Erasure and backups' || return 1
  local n; n="$(grep -Eio 'the last \*\*[0-9]+ days\*\*' <<< "$ADR4_TEXT" | grep -Eo '[0-9]+' | head -n 1)"
  [ "$n" = 30 ] || { WHY="ADR-0004's retention reads $n days"; return 1; }
}
check "erased data stays in backups only until ADR-0004's 30 days and the verified sets expire" k04_backups

# (4) G-3 A: the re-apply draws on the off-server erasure record, before the public listener opens.
# Fix round 1 (D-1): after migrate at step 12 and before backend and any worker start at step 13.
ADR4_STEPS="$(sed -n '/^### Restore procedure/,/^### /p' <<< "$ADR4_TEXT" | paras | grep -E '^[0-9]+\. ')"
ADR4_PARAS="$(paras <<< "$ADR4_TEXT")"
# A customer value, or an identifier of the customer, in a sentence about a record of erasures.
CUST_VALUE='\bname\b|\bcustomer.s names?\b|\bNIP\b|\baddress(es)?\b|\bphones?\b|\be-mails?\b|\btax identifiers?\b|\bfield values?\b|\bcustomer identifiers?\b'
K04_RECORD_EXCUSED=(
  "An entry holds the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, never a customer field value."
  "The IT department records the re-applied erasures with the restore record that step 14 writes, by their count and by their entries' own references in the erasure record only, never by a customer identifier or field value."
  # Fix round 2 (C19): the reconciliation compares customer identifiers with the record's entries.
  "At every monthly verification of ADR-0004 Backup, the IT department reconciles the erasure record with the live application database, by customer identifier only:"
  "- every customer identifier that the set verified at that check, or the verified set before it, holds and the live application database does not hold has an entry not marked failed or cancelled; an identifier without one is an erasure carried out with no entry, and the IT department writes its entry, marked completed with a time known to be no earlier than the commit (An entry whose commit time cannot be read)."
)
k04_record() {
  need "$EB" '^- The off-server erasure record\.$' 'Erasure and backups' || return 1
  need "$EB" '^Only the IT department writes the erasure record, off the server, after the erasure is approved and before it is carried out; the server holds no credential that can write it\.$' 'Erasure and backups' || return 1
  need "$EB" '^An entry holds the customer.s internal record identifier, the entry.s time, its mark and, once recorded, the erasure.s commit time, never a customer field value\.$' 'Erasure and backups' || return 1
  local r; r="$(awk -F'|' 'tolower($2) ~ /off-server erasure record/' <<< "$PLACE_ROWS")"
  need "$(cell "$r" 3)" "^for each approved erasure, the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, nothing else; every entry not marked failed or cancelled is re-applied at every restore \\(\\*Erasure and backups\\*\\)$" 'the erasure-record place row' || return 1
  need "$(cell "$r" 4)" '^none beyond the identifier$' 'the erasure-record place row' || return 1
  # Any other sentence putting a customer value into the erasure record, an entry or the restore
  # record fails, whatever its verb. The first version needed a verb from a list, and "The restore
  # record lists each re-applied customer's name and NIP." passed (reviewer, round 0).
  local all; all="$(without "$DECISION_SENTS" "${K04_RECORD_EXCUSED[@]}" | sed -E 's/\b[Ee]ntry point/ENTRYPOINT/g')"
  # Fix round 2: any record the IT department keeps (reconciliation, operations, verification).
  local recs='erasure record|restore record|(reconciliation|operations|verification|monthly) records?|the record'
  forbid "$all" "\\b($recs|an entry|the entry|each entry|every entry|entries)\\b[^.]*($CUST_VALUE)" || return 1
  forbid "$all" "($CUST_VALUE)[^.]*\\b($recs|an entry|the entry|entries)\\b" || return 1
}
check 'the off-server erasure record is written by the IT department before the erasure and holds only the identifier, the times and the mark' k04_record

# Fix round 2 (D-4): "The re-apply is carried out ...", and "every such erasure" (every entry not
# marked failed or cancelled) instead of round 1's "every completed erasure".
PLACE_RE='^The re-apply is carried out after migrate has run at ADR-0004 restore step ([0-9]+) and before backend and any worker are started at step ([0-9]+), so that every such erasure is in effect before the backend or any worker serves or synchroni[sz]es the restored data, and so before the public listener is opened to the internet at step ([0-9]+)\.$'
PLACE_SENT="$(grep -E "$PLACE_RE" <<< "$EB")"
place_n() { sed -E "s/$PLACE_RE/\\$1/" <<< "$PLACE_SENT"; }
# The sentences on the re-apply, its window or the listener: the ones that state the placement
# above, or restate it, are excused by their exact text only.
REAPPLY_SEL='re-appl|carried out again|\bpublic listener\b|\bbackend (and|or) any worker\b|\berasures? (is|are) (applied|carried out|in effect)\b'
REAPPLY_EXCUSED=(
  "The re-apply is carried out after migrate has run at ADR-0004 restore step 12 and before backend and any worker are started at step 13, so that every such erasure is in effect before the backend or any worker serves or synchronises the restored data, and so before the public listener is opened to the internet at step 14."
  "Because the re-apply covers every entry not marked failed or cancelled, whatever its time, an erasure that committed while a backup ran is either absent from the set or re-applied; the instant of the backup point does not decide it."
  "A restore host: the application database restored on it is covered by the re-apply (Erasure and backups); the decrypted backup set it received at ADR-0004 restore step 3 is deleted once the restore is recorded at step 14 or abandoned; a restore host that does not become the server, a test restore's host included, has its restored databases and volumes deleted once the restore is recorded or abandoned; and an abandoned restore, on any host, has its restored databases and volumes deleted once it is abandoned."
  "The IT department records the re-applied erasures with the restore record that step 14 writes, by their count and by their entries' own references in the erasure record only, never by a customer identifier or field value."
  "If the erasure feature finds that it cannot carry out the re-apply within ADR-0004's composition before backend or any worker starts, that task stops and the change returns to the human."
  "On 2026-10-25, after the first evaluation, the human placed the re-apply after migrate at ADR-0004 restore step 12 and before backend and any worker start at step 13, within gate 1's \"between steps 12 and 14\"."
  "The re-apply itself cannot be proven at EKO-1-08, because erasure is a later feature (brief section 4, Later 14); it is proven once erasure exists (ADR-0005-C15)."
  "Step 13's verification is unaffected: the row counts it relies on are those compared at step 6, before any migration and before the re-apply."
  # Fix round 2: gate 1's ruling ("not deviations" is said of ADR-0004, not of the re-apply), and
  # the reconciliation's stated limit ("the erasure is carried out" is the erasure itself).
  "Gate 1 of EKO-1-04 (#17), on 2026-10-25, ruled that the restore re-apply of erasures and the shipping of Keycloak events off the server are within ADR-0004 and not deviations; no deviation from an accepted decision was approved."
  "The reconciliation does not catch an erasure with no entry of a customer that neither compared set holds; against that case only the order of The off-server erasure record holds, the entry written before the erasure is carried out."
  # Fix round 2 (D-4, R-10): what is re-applied, the unreadable commit time, no backup before it.
  "| The off-server erasure record | for each approved erasure, the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, nothing else; every entry not marked failed or cancelled is re-applied at every restore (Erasure and backups) | none beyond the identifier |"
  "An entry is marked failed or cancelled only after the live application database is shown to still hold its identifier, and an entry marked failed or cancelled is never re-applied."
  "Every other entry, completed or not yet marked, is re-applied at every restore (Re-apply at restore)."
  "When the commit time cannot be read from the server (for example, the server was lost before the IT department marked the entry), the entry keeps being re-applied at every restore, and it is never deleted on the strength of a time earlier than the true commit."
  "At every restore, every entry of the record that is not marked failed or cancelled, completed entries and entries not yet marked alike, is carried out again on the restored application database."
  "Because erasure is idempotent by identifier, re-applying an entry whose erasure is not yet confirmed is safe."
  "No backup set is written to the destination from a restored application database before the re-apply has run on it: the backup service is not started on a restore host before then."
  "ADR-0004's procedure takes its first backup at step 14, after the re-apply."
  "On 2026-10-26, after the second evaluation, the human decided that a restore re-applies every entry of the erasure record not marked failed or cancelled, that the IT department reconciles the record with the live application database, and that an official Keycloak image unable to keep the typed username of a failed login naming no existing account out of its log and stored events returns the change to the human as an addendum to this decision."
)
REAPPLY_TIMING='\b(after(wards)?|later|once|then|subsequently|when(ever)?|while|until|if|unless|except|otherwise|optional(ly)?|may|can|could|might|need not|skip(s|ped)?|defer(s|red)?|postpone[sd]?|delay(s|ed)?|in parallel|meanwhile)\b'
# Fix round 2: a negation or a restriction of the re-apply, and a re-apply that stops. The round-1
# suite let "An unmarked entry is not re-applied." (R-08 a, written down) and "An identifier not
# found in the restored database stops the re-apply." through (reviewer, round 1).
REAPPLY_NEG='\b(not|never|neither|nor|except|unless|only|no longer|without|instead|exclud\w*|omit\w*)\b|\bno (entr(y|ies)|erasures?|unmarked|pending|unconfirmed)\b'
REAPPLY_STOP='\b(stops?|stopped|halts?|halted|aborts?|aborted|fails?|interrupt\w*|blocks?|blocked|cancels?)\b'
reapply_rest() { without "$(grep -Ei -- "$REAPPLY_SEL" <<< "$DECISION_SENTS")" "${REAPPLY_EXCUSED[@]}" | grep -v '^EXCUSED-SENTENCE$'; }

k04_reapply() {
  local c
  need "$EB" '^- Re-apply at restore\.$' 'Erasure and backups' || return 1
  need "$EB" '^At every restore, every entry of the record that is not marked failed or cancelled, completed entries and entries not yet marked alike, is carried out again on the restored application database\.$' 'Erasure and backups' || return 1
  need "$EB" '^Because erasure is idempotent by identifier, re-applying an entry whose erasure is not yet confirmed is safe\.$' 'Erasure and backups' || return 1
  [ "$(grep -c . <<< "$PLACE_SENT")" -eq 1 ] || { WHY="expected one placement sentence 'The re-apply is carried out after migrate has run at ADR-0004 restore step <a> and before backend and any worker are started at step <b>, ..., and so before the public listener is opened to the internet at step <c>.'"; return 1; }
  c="$(place_n 3)"
  grep -Eq "^$c\\. Only then open the public listener to the internet" <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step $c is not the opening of the public listener: $(grep -E "^$c\\. " <<< "$ADR4_STEPS" | cut -c1-80)"; return 1; }
  [ "$(place_n 2)" -lt "$c" ] || { WHY="the re-apply is placed before step $(place_n 2), which is not before the listener opens at step $c"; return 1; }
  forbid "$(grep -Ei 're-appl|carried out again|is carried out' <<< "$EB")" '\b(after|once) (the restore is recorded|step 14|the public listener (is |has been )?open)|\bafter ADR-0004 restore step 14\b' || return 1
  forbid "$DECISION_SENTS" '\berasures?\b[^.]*\b(are|is) not re-applied\b|\bre-appl\w*\b[^.]*\b(optional|may be skipped|need not)\b' || return 1
  # Fix round 1: any other sentence on the re-apply or the listener that times, conditions or
  # defers it. The first version banned only "after step 14 / the restore is recorded / the
  # listener open", and "If the erasure record cannot be reached, the public listener is opened
  # and the erasures are re-applied afterwards." passed (reviewer, round 0).
  forbid "$(reapply_rest)" "$REAPPLY_TIMING" || return 1
  forbid "$(reapply_rest)" "$REAPPLY_NEG" || return 1
  forbid "$(reapply_rest)" "$REAPPLY_STOP" || return 1
}
check 'every entry not marked failed or cancelled, completed or not yet marked, is re-applied at restore before the public listener opens (ADR-0004 step 14)' k04_reapply

k04_reapply_window() {
  local a b
  [ "$(grep -c . <<< "$PLACE_SENT")" -eq 1 ] || { WHY="expected one placement sentence (see the re-apply check)"; return 1; }
  a="$(place_n 1)"; b="$(place_n 2)"
  grep -Eq "^$a\\. Run migrate\\b" <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step $a is not the migrate run: $(grep -E "^$a\\. " <<< "$ADR4_STEPS" | cut -c1-80)"; return 1; }
  grep -Eq "^$b\\. Start backend\\b" <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step $b does not start backend: $(grep -E "^$b\\. " <<< "$ADR4_STEPS" | cut -c1-80)"; return 1; }
  [ "$b" -eq $((a + 1)) ] || { WHY="steps $a and $b are not consecutive: another ADR-0004 step runs between migrate and the re-apply, or between the re-apply and backend"; return 1; }
  # ADR-0004: backend and any worker start only after migrate succeeded.
  grep -Fq 'backend (and any worker) starts only after migrate has exited with success' <<< "$ADR4_PARAS" || { WHY="ADR-0004 Migrations no longer says backend and any worker start only after migrate"; return 1; }
  # Step 13's verification uses the counts compared at step 6, so the re-apply does not change it.
  need "$EB" "^Step $b.s verification is unaffected: the row counts it relies on are those compared at step 6, before any migration and before the re-apply\\.$" 'Erasure and backups' || return 1
  grep -Eq "^$b\\. .*the counts compared at step 6 are equal" <<< "$ADR4_STEPS" || { WHY="ADR-0004 step $b does not verify by the counts compared at step 6"; return 1; }
  grep -Eq '^6\. Compare the restored application tables. row counts with the manifest, before any migration runs' <<< "$ADR4_STEPS" || { WHY="ADR-0004 step 6 is not the row-count comparison before any migration"; return 1; }
  need "$(sub_sents '^### Changes to accepted decisions')" "the human placed the re-apply after migrate at ADR-0004 restore step $a and before backend and any worker start at step $b, within gate 1.s \"between steps 12 and 14\"" 'Changes to accepted decisions' || return 1
  need "$EB" '^If the erasure feature finds that it cannot carry out the re-apply within ADR-0004.s composition before backend or any worker starts, that task stops and the change returns to the human\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'every entry not marked failed or cancelled, completed or not yet marked, was in effect before .?backend.? or any worker served or synchronised the restored data' 'ADR-0005-C15' || return 1
  # No other sentence places the re-apply only before a later step or the listener.
  forbid "$(reapply_rest)" '\bbefore (the public listener|the listener|step 1[4-9]|ADR-0004 restore step 1[4-9]|the restore is recorded)\b|\bstep 1[3-9]\b' || return 1
}
check 're-apply runs after migrate at ADR-0004 restore step 12 and before backend and any worker start at step 13' k04_reapply_window

# The deletion rule of an entry, which the "either absent or re-applied" claim relies on (R-02).
# Fix round 2 (D-4): every entry not marked failed or cancelled, and only once it holds a commit time.
K04_DELETE_EXCUSED=(
  "An entry not marked failed or cancelled is deleted only once it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination."
  "An entry that holds no commit time is kept."
  "- The off-server erasure record keeps each entry not marked failed or cancelled, completed entries and entries not yet marked alike, until it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination (Erasure and backups)."
  "- Not decided: how long an entry of the off-server erasure record marked failed or cancelled is kept; it closes when the permanent-erasure feature is planned."
  "- When an entry is deleted."
  # They keep an entry, or forbid its deletion ("keep" in the human's record is the typed username's).
  "On 2026-10-26, after the second evaluation, the human decided that a restore re-applies every entry of the erasure record not marked failed or cancelled, that the IT department reconciles the record with the live application database, and that an official Keycloak image unable to keep the typed username of a failed login naming no existing account out of its log and stored events returns the change to the human as an addendum to this decision."
  "When the commit time cannot be read from the server (for example, the server was lost before the IT department marked the entry), the entry keeps being re-applied at every restore, and it is never deleted on the strength of a time earlier than the true commit."
  "A mark that contradicts the database is corrected: an entry marked failed or cancelled whose identifier the live database does not hold is marked completed, with a time under the same rule; a completed entry whose identifier the live database still holds is reported to the human, and the entry is not deleted while that stands."
)
# "the entry point" (the proxy) is not an entry of the erasure record.
no_entry_point() { sed -E 's/\b[Ee]ntry point/ENTRYPOINT/g'; }
k04_backup_point() {
  need "$EB" '^Because the re-apply covers every entry not marked failed or cancelled, whatever its time, an erasure that committed while a backup ran is either absent from the set or re-applied; the instant of the backup point does not decide it\.$' 'Erasure and backups' || return 1
  # The claim holds only when no entry is deleted while a set from before its erasure exists.
  need "$EB" '^An entry not marked failed or cancelled is deleted only once it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination\.$' 'Erasure and backups' || return 1
  need "$EB" '^An entry that holds no commit time is kept\.$' 'Erasure and backups' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K04_DELETE_EXCUSED[@]}" | no_entry_point)"
  forbid "$all" '\b(entry|entries|erasure record)\b[^.]*\b(delet\w*|remov\w*|purg\w*|kept|keeps?|expir\w*|discard\w*|retain\w*|dropped)\b' || return 1
  forbid "$all" '\b(delet\w*|remov\w*|purg\w*|expir\w*|discard\w*)\b[^.]*\b(entry|entries|erasure record)\b' || return 1
}
check 'an erasure committing during a backup run is either in the set or re-applied' k04_backup_point

k04_backup_point_def() {
  need "$EB" '^- The backup point\.$' 'Erasure and backups' || return 1
  need "$EB" '^The backup point of a set is the start of its application-database dump.s snapshot\.$' 'Erasure and backups' || return 1
  need "$EB" '^A set whose backup point cannot be shown to be after an erasure.s commit time counts as started before it\.$' 'Erasure and backups' || return 1
  need "$EB" '^- When an entry is deleted\.$' 'Erasure and backups' || return 1
  grep -Fq "each dump a consistent snapshot while writes continue" <<< "$ADR4_PARAS" || { WHY="ADR-0004 no longer says each dump is a consistent snapshot"; return 1; }
  # Fix round 2 (D-4): no entry deleted while it holds no commit time, nor before the bound.
  need "$(control C15)" 'no entry was deleted while it held no commit time or while a backup set whose snapshot started before its commit time remained' 'ADR-0005-C15' || return 1
  # The backup point is never the end of a dump, its upload, the manifest time or Keycloak's dump,
  # and no rule counts from a set "taken before" an erasure (the round-0 wording R-02 found).
  forbid "$DECISION_SENTS" '\bbackup point\b[^.]*\b(end|ends|finish(es|ed)?|completion|upload(ed)?|written|shipped|manifest|Keycloak)\b' || return 1
  forbid "$DECISION_SENTS" '\b(set|sets) taken before (its|the|an) erasure\b[^.]*\b(entry|entries|record)\b|\b(entry|entries|record)\b[^.]*\b(set|sets) taken before (its|the|an) erasure\b' || return 1
}
check 'the backup point is the start of the application-database snapshot, and an entry is deleted only when no set whose snapshot started before its commit time remains' k04_backup_point_def

# Fix round 2 (D-4): the commit time is the transaction's, in UTC, from the server's clock.
K04_COMMIT_EXCUSED=(
  "A time taken elsewhere (the approval, a user's report, a workstation's clock) is not a commit time."
  "An entry holds the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, never a customer field value."
  "| The off-server erasure record | for each approved erasure, the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, nothing else; every entry not marked failed or cancelled is re-applied at every restore (Erasure and backups) | none beyond the identifier |"
)
COMMIT_ELSEWHERE='\b(approv\w*|(user|staff|customer|rep|manager).s reports?|workstations?|local (time|clock)|time ?zones?|client|browser|entry.s time|time of the entry|wall[- ]clock|laptop|IT department.s clock)\b'
k04_commit_time() {
  need "$EB" '^- The commit time\.$' 'Erasure and backups' || return 1
  need "$EB" '^The commit time of an erasure is the commit time of its database transaction, in UTC, taken from the server: the clock behind the snapshot start of \*?The backup point\*?\.$' 'Erasure and backups' || return 1
  need "$EB" '^A time taken elsewhere \(the approval, a user.s report, a workstation.s clock\) is not a commit time\.$' 'Erasure and backups' || return 1
  need "$EB" '^An entry is marked completed with the erasure.s commit time\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'every commit time recorded is the erasure transaction.s commit time in UTC taken from the server, or a time known to be no earlier than it' 'ADR-0005-C15' || return 1
  # No other sentence takes a commit time from anywhere else.
  local all; all="$(without "$DECISION_SENTS" "${K04_COMMIT_EXCUSED[@]}")"
  forbid "$all" "\\bcommit(ted)? times?\\b[^.]*$COMMIT_ELSEWHERE|$COMMIT_ELSEWHERE[^.]*\\bcommit(ted)? times?\\b" || return 1
}
check 'the commit time of an erasure is its transaction commit time, in UTC, taken from the server (D-4)' k04_commit_time

# Fix round 2 (D-4, R-08 a): an entry whose commit time cannot be read keeps being re-applied, is
# never deleted on an earlier time, and a time recorded later is no earlier than the commit.
k04_unreadable_commit() {
  need "$EB" '^- An entry whose commit time cannot be read\.$' 'Erasure and backups' || return 1
  need "$EB" '^When the commit time cannot be read from the server \(for example, the server was lost before the IT department marked the entry\), the entry keeps being re-applied at every restore, and it is never deleted on the strength of a time earlier than the true commit\.$' 'Erasure and backups' || return 1
  need "$EB" '^If a commit time is recorded for it later, it is a time known to be no earlier than the commit, such as the time the IT department confirmed the identifier absent from the live application database\.$' 'Erasure and backups' || return 1
  need "$EB" '^An entry that holds no commit time is kept\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'no entry was deleted while it held no commit time' 'ADR-0005-C15' || return 1
  # A later time is never one earlier than the commit (the approval, the entry's own time).
  forbid "$DECISION_SENTS" '\b(earlier|before|older)\b[^.]*\bthan the (true )?commit\b[^.]*\b(may|can|is) (be )?(recorded|used)\b|\bcommit time\b[^.]*\b(may|can) be (an? )?(earlier|estimated|approximate)\b' || return 1
}
check 'an entry whose commit time cannot be read keeps being re-applied and is never deleted on a time earlier than the commit (D-4)' k04_unreadable_commit

# D-2: who writes the record. Fix round 2: the reconciliation's own entry, written by the IT department.
K04_WRITER_EXCUSED=(
  "Only the IT department writes the erasure record, off the server, after the erasure is approved and before it is carried out; the server holds no credential that can write it."
  "- every customer identifier that the set verified at that check, or the verified set before it, holds and the live application database does not hold has an entry not marked failed or cancelled; an identifier without one is an erasure carried out with no entry, and the IT department writes its entry, marked completed with a time known to be no earlier than the commit (An entry whose commit time cannot be read)."
)
k04_writer() {
  need "$EB" '^Only the IT department writes the erasure record, off the server, after the erasure is approved and before it is carried out; the server holds no credential that can write it\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'written by the IT department after the erasure was approved and before it was carried out' 'ADR-0005-C15' || return 1
  need "$(control C15)" 'the server holds no credential that can write the record' 'ADR-0005-C15' || return 1
  # "off-server" says where the record is, not who writes it.
  local all; all="$(without "$DECISION_SENTS" "${K04_WRITER_EXCUSED[@]}" | no_entry_point | sed -E 's/\boff-server\b/OFFSERVER/g')"
  forbid "$all" '\b(server|backend|application|worker|erasure feature|migrate|the feature)\b[^.]*\b(writes?|appends?|adds?|marks?|updates?|creates?|makes?|records?)\b[^.]*\b(erasure record|an entry|the entry|entries|its entry)\b' || return 1
  forbid "$all" '\b(erasure record|entry|entries)\b[^.]*\b(written|made|appended|added|marked|updated|created|recorded) by (the )?(server|backend|application|worker|erasure feature|feature)\b' || return 1
  forbid "$all" '\b(server|backend|worker)\b[^.]*\b(holds?|has|gets?|is given|uses?)\b[^.]*\b(credential|right|access)\b[^.]*\berasure record\b' || return 1
  forbid "$all" '\b(before|without) (the erasure is |it is )?approv' || return 1
}
check 'only the IT department writes the erasure record, after the erasure is approved, and the server holds no credential that can write it' k04_writer

# D-2 marks, revised by D-4: failed or cancelled only after the database is shown to still hold the
# identifier; every other entry, completed or not yet marked, is re-applied.
K04_MARK_EXCUSED=(
  "At every restore, every entry of the record that is not marked failed or cancelled, completed entries and entries not yet marked alike, is carried out again on the restored application database."
  "An entry is marked failed or cancelled only after the live application database is shown to still hold its identifier, and an entry marked failed or cancelled is never re-applied."
  "| The off-server erasure record | for each approved erasure, the customer's internal record identifier, the entry's time, its mark and, once recorded, the erasure's commit time, nothing else; every entry not marked failed or cancelled is re-applied at every restore (Erasure and backups) | none beyond the identifier |"
  "A mark that contradicts the database is corrected: an entry marked failed or cancelled whose identifier the live database does not hold is marked completed, with a time under the same rule; a completed entry whose identifier the live database still holds is reported to the human, and the entry is not deleted while that stands."
)
k04_marks() {
  need "$EB" '^An entry is marked completed with the erasure.s commit time\.$' 'Erasure and backups' || return 1
  need "$EB" '^An entry is marked failed or cancelled only after the live application database is shown to still hold its identifier, and an entry marked failed or cancelled is never re-applied\.$' 'Erasure and backups' || return 1
  need "$EB" '^Every other entry, completed or not yet marked, is re-applied at every restore \(\*?Re-apply at restore\*?\)\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'every entry marked failed or cancelled was so marked only after the live application database was shown to still hold its identifier' 'ADR-0005-C15' || return 1
  need "$(control C15)" 'every entry not marked failed or cancelled, completed or not yet marked, was in effect before' 'ADR-0005-C15' || return 1
  need "$(control C15)" 'no entry marked failed or cancelled was re-applied' 'ADR-0005-C15' || return 1
  # D-4 reverses round 1's "only completed entries": a re-apply sentence that limits the re-apply
  # to completed entries is R-08 again. (Round 1 banned "every entry" here; D-4 makes it the rule.)
  forbid "$(grep -Ei -- "$REAPPLY_SEL" <<< "$DECISION_SENTS")" '\b(every|each|all|only)( of)?( the)? completed (entr(y|ies)|erasures?)\b|\bcompleted (entr(y|ies)|erasures?) only\b' || return 1
  # Failed or cancelled entries are never re-applied.
  local all; all="$(without "$DECISION_SENTS" "${K04_MARK_EXCUSED[@]}")"
  forbid "$all" '\b(failed|cancell?ed)\b[^.]*\b(are|is|may be|gets?|get) (also )?(re-applied|carried out again)\b' || return 1
  # No other rule marks an entry failed or cancelled (an error report, a timeout, a request).
  forbid "$all" '\b(is|are|gets?|get|be|been) marked (as )?(failed|cancell?ed)\b|\bmarks?\b[^.]*\b(failed|cancell?ed)\b' || return 1
}
check 'an entry is marked failed or cancelled only after the database is shown to still hold its identifier, and every other entry, completed or not yet marked, is re-applied' k04_marks

# D-2: idempotent erasure and identifiers never reused (C14, C17).
K04_REUSE_EXCUSED=("- Customer identifiers are never reused.")
ABSENT_WORD='\b(absent|not found|missing|unknown|not present|no longer (exists?|present)|does not exist|cannot be found)\b'
ABSENT_FAIL='\b(fails?|failure|errors?|raises?|aborts?|stops?|halts?|blocks?|interrupts?)\b'
k04_idempotent() {
  need "$EB" '^- Erasure is idempotent by identifier\.$' 'Erasure and backups' || return 1
  need "$EB" '^Erasing an identifier that is absent from the database is a no-op, not a failure, and erasing an identifier again changes nothing further\.$' 'Erasure and backups' || return 1
  need "$EB" '^- Customer identifiers are never reused\.$' 'Erasure and backups' || return 1
  need "$EB" '^An identifier once issued to a customer is never issued to another customer, also after a restore from an earlier backup set, so an old entry can never match a new customer\.$' 'Erasure and backups' || return 1
  # Fix round 2 (Guardian note): the binding task named in words, no bare "(EKO-3)".
  need "$EB" '^ADR-0002 fixes no key type; this rule binds the task that creates the first customer table and does not change ADR-0002\.$' 'Erasure and backups' || return 1
  need "$(control C14)" 'erasing the same identifier again, and erasing an absent identifier, succeeds and changes nothing' 'ADR-0005-C14' || return 1
  need "$(control C17)" 'restores the database from that set, creates a customer, and finds that its identifier is none of those issued after the set' 'ADR-0005-C17' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K04_REUSE_EXCUSED[@]}")"
  forbid "$all" '\breus(e|es|ed|ing|able)\b|\bre-?issu(e|es|ed|ing)\b|\brecycl\w*\b' || return 1
  # Fix round 2: an absent identifier in any wording, failing in either order. The round-1 ban
  # needed "absent", and "An identifier not found in the restored database stops the re-apply."
  # passed (reviewer, round 1).
  forbid "$all" "$ABSENT_WORD[^.]*$ABSENT_FAIL|$ABSENT_FAIL[^.]*$ABSENT_WORD" 'is a no-op, not a failure' || return 1
}
check 'erasure is idempotent by identifier, and customer identifiers are never reused (C14, C17)' k04_idempotent

# F-01: the restore host (C18). Fix round 2 (R-09, B-06): abandoned restores are recorded, and their
# restored databases and volumes deleted, on any host.
K04_ABANDON_EXCUSED=(
  "A restore host: the application database restored on it is covered by the re-apply (Erasure and backups); the decrypted backup set it received at ADR-0004 restore step 3 is deleted once the restore is recorded at step 14 or abandoned; a restore host that does not become the server, a test restore's host included, has its restored databases and volumes deleted once the restore is recorded or abandoned; and an abandoned restore, on any host, has its restored databases and volumes deleted once it is abandoned."
  "The IT department records an abandoned restore in its operations record, with its date, the backup set used, who performed it, the host and the step at which it stopped."
)
k04_restore_host() {
  grep -Eq '^3\. Decrypt the backup set\b' <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step 3 is not the decryption of the set"; return 1; }
  grep -Eq '^14\. .*\brecord the restore\b' <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step 14 does not record the restore"; return 1; }
  grep -Eq '^14\. .*\brecord the restore \(date, backup set used, who performed it\b.*\bin the IT department.s operations record\b' <<< "$ADR4_STEPS" || { WHY="ADR-0004 step 14's restore record no longer holds the date, the set and who performed it in the operations record"; return 1; }
  need "$EXCUSED_P" 'A restore host: the application database restored on it is covered by the re-apply \(\*?Erasure and backups\*?\); the decrypted backup set it received at ADR-0004 restore step 3 is deleted once the restore is recorded at step 14 or abandoned; a restore host that does not become the server, a test restore.s host included, has its restored databases and volumes deleted once the restore is recorded or abandoned; and an abandoned restore, on any host, has its restored databases and volumes deleted once it is abandoned\. The IT department records an abandoned restore in its operations record, with its date, the backup set used, who performed it, the host and the step at which it stopped\.' 'Places excused' || return 1
  need "$(control C18)" '^\| ADR-0005-C18 \| By the IT department.s dated record of each restore, abandoned restores included: every abandoned restore is recorded with its date, the backup set used, who performed it, the host and the step at which it stopped; the decrypted backup set was deleted once the restore was recorded or abandoned; the restored databases and volumes of an abandoned restore, and of a restore host that did not become the server, were deleted once the restore was recorded or abandoned\. \|$' 'ADR-0005-C18' || return 1
  # The place row still names the restore host as a holder.
  awk -F'|' 'tolower($2) ~ /restore host/' <<< "$PLACE_ROWS" | grep -q . || { WHY="no place row names the restore host"; return 1; }
  # Any other sentence on an abandoned restore is a new rule about it (kept, not recorded, later).
  forbid "$(without "$DECISION_SENTS" "${K04_ABANDON_EXCUSED[@]}")" '\babandon\w*\b[^.]*\brestor\w*|\brestor\w*\b[^.]*\babandon\w*' || return 1
}
check 'a restore host is excused: its restored database is re-applied, its decrypted set is deleted, a host that does not become the server keeps nothing, and an abandoned restore is recorded and keeps nothing (C18)' k04_restore_host

# Fix round 2 (R-10): no backup set is written from a restored database before the re-apply.
K04_NOBACKUP_EXCUSED=(
  "No backup set is written to the destination from a restored application database before the re-apply has run on it: the backup service is not started on a restore host before then."
  "ADR-0004's procedure takes its first backup at step 14, after the re-apply."
)
k04_no_backup_before_reapply() {
  need "$EB" '^- No backup before the re-apply\.$' 'Erasure and backups' || return 1
  need "$EB" '^No backup set is written to the destination from a restored application database before the re-apply has run on it: the backup service is not started on a restore host before then\.$' 'Erasure and backups' || return 1
  need "$EB" '^ADR-0004.s procedure takes its first backup at step 14, after the re-apply\.$' 'Erasure and backups' || return 1
  need "$(control C15)" 'no backup set was written to the destination from the restored database before the re-apply' 'ADR-0005-C15' || return 1
  # ADR-0004: step 14 takes the fresh backup, and no earlier restore step starts the backup service.
  grep -Eq '^14\. Only then open the public listener to the internet, take a fresh backup\b' <<< "$ADR4_STEPS" || { WHY="ADR-0004 restore step 14 does not take the fresh backup"; return 1; }
  local early; early="$(grep -E '^([1-9]|1[0-3])\. ' <<< "$ADR4_STEPS" | grep -Ei '\b(start|run|take)s?\b[^.]*\bbackup\b' | grep -Eiv '\b(fetch|decrypt|restore)\b[^.]*\bbackup set\b')"
  [ -z "$early" ] || { WHY="an ADR-0004 restore step before 14 starts or runs a backup: $(head -n 1 <<< "$early" | cut -c1-100)"; return 1; }
  # Any other sentence on the backup service or a backup taken at a restore is a new rule about it.
  local all; all="$(without "$DECISION_SENTS" "${K04_NOBACKUP_EXCUSED[@]}")"
  forbid "$all" '(\bbackup (service|runs?|jobs?)\b|\b(takes?|taken|writes?|written|starts?|started) [^.]*\bbackups?\b|\bbackup sets? (is |are )?(written|taken)\b)[^.]*\b(re-appl\w*|restor\w*)\b|\b(re-appl\w*|restor\w*)\b[^.]*(\bbackup (service|runs?|jobs?)\b|\bbackup sets? (is |are )?(written|taken)\b|\b(takes?|taken|starts?|started) [^.]*\bbackups?\b)' || return 1
}
check 'no backup set is written to the destination from a restored database before the re-apply has run on it (R-10)' k04_no_backup_before_reapply

# Fix round 2 (D-4 c, B-05, C19): the monthly reconciliation of the record with the live database.
K04_RECON_EXCUSED=(
  "| The IT department's verification host and a restore host | a decrypted backup set, during the monthly check or a restore (ADR-0004); on the verification host, also the customer identifiers the reconciliation compares, during the check (Erasure and backups) | all |"
  "The IT department's verification host: its decrypted copy is deleted after the check (ADR-0004 Backup), and the customer identifiers the reconciliation compares are deleted with it (Erasure and backups)."
  "- Reconciliation."
  "At every monthly verification of ADR-0004 Backup, the IT department reconciles the erasure record with the live application database, by customer identifier only:"
  "The reconciliation does not catch an erasure with no entry of a customer that neither compared set holds; against that case only the order of The off-server erasure record holds, the entry written before the erasure is carried out."
  "- The reconciliation is likewise a duty of this decision, carried out by the IT department on the occasion and the host of ADR-0004's monthly verification."
  "On 2026-10-26, after the second evaluation, the human decided that a restore re-applies every entry of the erasure record not marked failed or cancelled, that the IT department reconciles the record with the live application database, and that an official Keycloak image unable to keep the typed username of a failed login naming no existing account out of its log and stored events returns the change to the human as an addendum to this decision."
)
k04_reconciliation() {
  need "$EB" '^- Reconciliation\.$' 'Erasure and backups' || return 1
  need "$EB" '^At every monthly verification of ADR-0004 \*?Backup\*?, the IT department reconciles the erasure record with the live application database, by customer identifier only:$' 'Erasure and backups' || return 1
  # (c) an erasure carried out with no entry, from the two newest verified sets.
  need "$EB" '^- every customer identifier that the set verified at that check, or the verified set before it, holds and the live application database does not hold has an entry not marked failed or cancelled; an identifier without one is an erasure carried out with no entry, and the IT department writes its entry, marked completed with a time known to be no earlier than the commit \(\*?An entry whose commit time cannot be read\*?\)\.$' 'Erasure and backups' || return 1
  need "$EB" '^When a restore has been recorded since the verified set before it, only the set verified at that check is compared;$' 'Erasure and backups' || return 1
  # B-05: a mark that contradicts the database.
  need "$EB" '^- the identifier of every entry marked completed is absent from the live application database, and the identifier of every entry marked failed or cancelled is present in it, unless another entry for the same identifier is not marked failed or cancelled\.$' 'Erasure and backups' || return 1
  need "$EB" '^A mark that contradicts the database is corrected: an entry marked failed or cancelled whose identifier the live database does not hold is marked completed, with a time under the same rule; a completed entry whose identifier the live database still holds is reported to the human, and the entry is not deleted while that stands\.$' 'Erasure and backups' || return 1
  need "$EB" '^The customer identifiers compared are deleted after the check, with the decrypted copies\.$' 'Erasure and backups' || return 1
  need "$EB" '^The reconciliation does not catch an erasure with no entry of a customer that neither compared set holds; against that case only the order of \*?The off-server erasure record\*? holds, the entry written before the erasure is carried out\.$' 'Erasure and backups' || return 1
  need "$EB" '^- The reconciliation is likewise a duty of this decision, carried out by the IT department on the occasion and the host of ADR-0004.s monthly verification\.$' 'Erasure and backups' || return 1
  need "$EB" '^It changes none of that check.s own comparisons and does not change ADR-0004\.$' 'Erasure and backups' || return 1
  local r; r="$(awk -F'|' 'tolower($2) ~ /verification host/' <<< "$PLACE_ROWS")"
  need "$(cell "$r" 3)" 'on the verification host, also the customer identifiers the reconciliation compares, during the check \(\*Erasure and backups\*\)$' 'the verification-host place row' || return 1
  # ADR-0004 runs the monthly verification on which the reconciliation is carried out.
  grep -Fq 'decrypts the newest set off the server every calendar month' <<< "$ADR4_PARAS" || { WHY="ADR-0004 no longer runs a monthly verification of the newest set"; return 1; }
  local c; c="$(control C19)"
  [ "$(grep -c . <<< "$c")" -eq 1 ] || { WHY="expected one ADR-0005-C19 row"; return 1; }
  need "$c" '^\| ADR-0005-C19 \| Once erasure exists: by the IT department.s dated record of each monthly verification, the reconciliation of \*Erasure and backups\* was carried out; every customer identifier that a compared verified set holds and the live application database does not hold has an entry not marked failed or cancelled; the identifier of every entry marked completed is absent from the live application database and that of every entry marked failed or cancelled is present in it, or the contradiction was corrected or reported to the human as that section says; the customer identifiers compared were deleted after the check\. \|$' 'ADR-0005-C19' || return 1
  # Any other sentence on the reconciliation is a new rule about it (skipped, deferred, narrowed).
  local all; all="$(without "$DECISION_SENTS" "${K04_RECON_EXCUSED[@]}")"
  forbid "$all" '\breconcil\w*' || return 1
  # The compared identifiers are kept nowhere after the check.
  forbid "$all" '\b(customer identifiers?|identifiers? compared)\b[^.]*\b(kept|keeps?|retained|stored|archived|copied|listed)\b|\b(kept|keeps?|retains?|stores?|archives?|copies|lists?)\b[^.]*\b(customer identifiers?|identifiers? compared)\b' || return 1
}
check 'the IT department reconciles the erasure record with the live database at every monthly verification, catching an erasure with no entry and a mark that contradicts the database (C19)' k04_reconciliation

# R-07: the restore record names re-applied erasures by count and entry reference only.
k04_restore_record() {
  need "$EB" '^- The restore record\.$' 'Erasure and backups' || return 1
  need "$EB" '^The IT department records the re-applied erasures with the restore record that step 14 writes, by their count and by their entries. own references in the erasure record only, never by a customer identifier or field value\.$' 'Erasure and backups' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K04_RECORD_EXCUSED[@]}")"
  forbid "$(grep -Ei '\brestore record\b|\brecords? (the )?re-applied\b|\brecord(s|ed)? (of )?the restore\b' <<< "$all")" "\\bidentifiers?\\b|$CUST_VALUE|\\b(lists?|names?|shows?|includes?|mentions?) (each|every|the) (re-applied )?customers?\\b" || return 1
}
check 'the restore record names the re-applied erasures by count and erasure-record entry reference only' k04_restore_record

k04_edges() {
  need "$EXCUSED_P" 'Google Calendar: the app-created events of the customer.s visits, past ones included \(CUS-9 removes only future events\)' 'Places excused' || return 1
  need "$ERA" 'Erasing one customer changes no other customer.s data and no staff attribution of another record \(as PRH-5\)' 'Erasure' || return 1
  need "$ERA" 'An archived customer can be erased' 'Erasure' || return 1
  need "$REMOVES" 'past visits keep their original owner after a reassignment, CUS-10' 'What it removes' || return 1
}
check 'erasure covers every owner and author, past calendar events are forwarded, and no other customer changes' k04_edges

# ==== K-06 ===================================================================================

FWD="$(sub_paras '^### Items forwarded to this decision')"
FWD_ENTRIES="$(grep -E '^- ' <<< "$FWD")"
DECISION_HEADINGS="$(grep -E '^###+ ' <<< "$DECISION_TEXT" | sed -E 's/^#+ //; s/[[:space:]]+$//')"
heading_ok() {
  grep -Fxq -- "$1" <<< "$DECISION_HEADINGS" || { WHY="'$1' is not a heading of ADR-0005's Decision"; return 1; }
  if [ -n "${2:-}" ]; then
    local re t; re="$(printf '%s' "$1" | sed -E 's/[][\\.*^$+?(){}|/]/\\&/g')"
    t="$(sub_text "^###+ $re\$" | paras)"
    has "$t" "$2" || { WHY="section '$1' does not mention /$2/"; return 1; }
  fi
}
# entry_sections <entry> — every *Heading* named after the arrow.
entry_sections() { sed -E 's/^[^→]*→//' <<< "$1" | grep -Eo '\*[^*]+\*' | sed -E 's/^\*//; s/\*$//'; }

# The closed list: source | ERE of the cited line(s) | ERE of the entry title | ERE a decided-in section must mention
ITEMS='ADR-0001|l\.184|Which modules hold personal data|backend/app
ADR-0001|l\.184|^- Logging —|Never written to any log
ADR-0001|l\.184|^- Retention —|deleted no later than
ADR-0001|l\.184|Archiving vs\. erasure|archiv|erasure
ADR-0002|l\.134|tables and columns|each new column
ADR-0002|l\.134-135|.|retention|Retention
ADR-0003|l\.93-95|abandoned sessions|abandoned ones included
ADR-0003|l\.204|Admin-event retention|admin events
ADR-0003|l\.287|application-realm login events|Login events of the application realm
ADR-0003|l\.291-292|.|display-name copy
ADR-0003|l\.316-317|.|display-name copy
ADR-0004|l\.175-176|.|Never written to any log
ADR-0004|l\.316-317|How erasure treats backups|backup sets
ADR-0004|l\.426-427|Master-realm event retention|master realm
ADR-0004|l\.559-561|.|backups?
ADR-0004|l\.582-584|.|backups?
docs/PLAN.md|l\.56-57|Shipping Keycloak events off the server|off the server
docs/PLAN.md|l\.56-57|Erasure in backups|backup sets'
k06_items() {
  local src line title sec entries e ok name
  while IFS='|' read -r src line title sec; do
    [ -n "$src" ] || continue
    entries="$(grep -Ei -- "$title" <<< "$FWD_ENTRIES" | grep -F -- "— " | S="$src" L="$line" awk '{ t = $0; sub(/→.*/, "", t); if (index(t, ENVIRON["S"]) && t ~ (ENVIRON["S"] " " ENVIRON["L"] "( |$)")) print }')"
    [ -n "$entries" ] || { WHY="no entry for '$title' citing $src ${line//\\/}"; return 1; }
    ok=""
    while IFS= read -r e; do
      while IFS= read -r name; do
        [ -n "$name" ] || continue
        heading_ok "$name" "$sec" && ok=1
      done < <(entry_sections "$e")
      # Or a planned task: "→ EKO-x-yy (#n)" resolving in docs/PLAN.md.
      if grep -Eq '→ EKO-[0-9]+-[0-9]+ \(#[0-9]+\)\.?$' <<< "$e"; then
        pairs_ok "$(sed -E 's/^[^→]*→//' <<< "$e")" && ok=1
      fi
    done <<< "$entries"
    [ -n "$ok" ] || { WHY="the entry for $src ${line//\\/} points to no Decision section mentioning /$sec/${WHY:+: $WHY}"; return 1; }
  done <<< "$ITEMS"
}
check 'every forwarded item of the closed list has an entry citing its source and line, decided in a section that mentions it' k06_items

k06_pointers() {
  local e tail name
  [ -n "$FWD_ENTRIES" ] || { WHY="the list of forwarded items is empty"; return 1; }
  while IFS= read -r e; do
    case "$e" in *"→"*) ;; *) WHY="entry without a pointer: $(cut -c1-120 <<< "$e")"; return 1 ;; esac
    tail="$(sed -E 's/^[^→]*→ ?//' <<< "$e")"
    grep -Eq '^(decided in \*[^*]+\*((, | and )\*[^*]+\*)*\.?$|EKO-[0-9]+-[0-9]+ \(#[0-9]+\)\.?$)' <<< "$tail" \
      || { WHY="pointer is neither 'decided in *<Decision heading>*' nor EKO-x-yy (#n): → $(cut -c1-100 <<< "$tail")"; return 1; }
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      heading_ok "$name" || return 1
    done < <(entry_sections "$e")
    pairs_ok "$tail" || return 1
  done <<< "$FWD_ENTRIES"
  local fr; fr="$(sub_paras '^### Forward references' | grep -E '^- ')"
  [ -n "$fr" ] || { WHY="no forward references"; return 1; }
  while IFS= read -r e; do
    grep -Eq '^- (EKO-[0-9]+-[0-9]+ \(#[0-9]+\)|Not decided)' <<< "$e" || { WHY="forward reference names no task as EKO-x-yy (#n) and is not 'Not decided': $(cut -c1-120 <<< "$e")"; return 1; }
    pairs_ok "$e" || return 1
  done <<< "$fr"
}
check 'every pointer of the forwarded-items list resolves to a Decision section or a planned task' k06_pointers

# Fix round 1 (D-3, R-06): a forward names the task that receives the duty and claims nothing about
# that task's Done when; ADR-0004 gets no cross-reference from this task.
K06_FWD_EXCUSED=(
  "It does not state that the duty is already in that task's Done when."
  "It adds no step to ADR-0004's procedure, changes none of its steps or their order, and does not change ADR-0004; ADR-0004's text is not edited for it, and a cross-reference there would be a dated addendum to ADR-0004."
)
k06_forwards() {
  local fs e
  fs="$(sub_sents '^### Forward references')"
  need "$fs" '^Each forward below names the task that receives the duty\.$' 'Forward references' || return 1
  need "$fs" '^It does not state that the duty is already in that task.s \*?Done when\*?\.$' 'Forward references' || return 1
  while IFS= read -r e; do
    [ -n "$e" ] || continue
    grep -Eq '^- EKO-[0-9]+-[0-9]+ \(#[0-9]+\)(, ADR-[0-9]{4},)? receives: ' <<< "$e" || { WHY="a forward to a task does not read '- EKO-x-yy (#n) receives:': $(cut -c1-100 <<< "$e")"; return 1; }
  done < <(sub_paras '^### Forward references' | grep -E '^- EKO-')
  need "$(sub_paras '^### Forward references' | grep -E '^- EKO-1-08 ')" 'The re-apply itself cannot be proven at EKO-1-08, because erasure is a later feature' 'the EKO-1-08 forward' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K06_FWD_EXCUSED[@]}")"
  forbid "$all" '\bDone[- ]when\b|\bdefinition of done\b' || return 1
  forbid "$all" '\bcross-references?\b' || return 1
  forbid "$all" '\bfirst (tested )?restore with the (erasure )?re-apply\b|\bre-apply (duty )?in place\b' || return 1
}
check "every forward names the task that receives the duty and none claims it is already in that task's Done when" k06_forwards

# (3) Completeness: every line of ADR-0001..0004 at TASK_BASE naming ADR-0005, EKO-1-04 or #17 is
# covered by an entry; the single exemption is ADR-0003 l.396, stated in ADR-0005.
k06_complete() {
  local refs f adr n hit
  refs="$(sed -E 's/→.*//' <<< "$FWD_ENTRIES" | awk '
    { s = $0; cur = ""
      while (match(s, /ADR-000[1-4]|docs\/PLAN\.md|l\.[0-9]+(-[0-9]+)?/)) {
        t = substr(s, RSTART, RLENGTH); s = substr(s, RSTART + RLENGTH)
        if (t !~ /^l\./) { cur = t; continue }
        if (cur == "") continue
        sub(/^l\./, "", t); split(t, r, "-"); print cur, r[1], (r[2] == "" ? r[1] : r[2])
      } }')"
  for f in "$ADR1" "$ADR2" "$ADR3" "$ADR4"; do
    adr="$(basename "$f" | grep -Eo '^ADR-000[1-4]')"
    while IFS= read -r n; do
      [ -n "$n" ] || continue
      if [ "$adr" = ADR-0003 ] && [ "$n" -eq 396 ]; then continue; fi
      hit="$(awk -v a="$adr" -v n="$n" '$1 == a && $2 <= n && n <= $3 { print; exit }' <<< "$refs")"
      [ -n "$hit" ] || { WHY="$adr l.$n (at $TASK_BASE) forwards to ADR-0005 and no entry covers it: $(at "$TASK_BASE" "$f" | sed -n "${n}p" | cut -c1-120)"; return 1; }
    done < <(at "$TASK_BASE" "$f" | grep -nE 'ADR-0005|EKO-1-04|#17' | cut -d: -f1)
  done
  need "$(sub_sents '^### Items forwarded to this decision')" '^ADR-0003 l\.396 names ADR-0005.s retention in an option that was not chosen; it is not a forward\.$' 'Items forwarded to this decision' || return 1
  # No second exemption: no other "is not a forward" / "not a forward" sentence.
  local ex; ex="$(grep -Ei '\bnot (a )?forwards?\b|\bexempt' <<< "$DECISION_SENTS")"
  [ "$(grep -c . <<< "$ex")" -eq 1 ] || { WHY="more than one exemption: $(tr '\n' '/' <<< "$ex" | cut -c1-200)"; return 1; }
}
check 'every line of ADR-0001..0004 forwarding to ADR-0005 is covered by an entry, ADR-0003 l.396 the only exemption' k06_complete

REG_HEAD="$(content "$PATHS")"
REG_BASE="$(at "$TASK_BASE" "$PATHS")"
reg_rows() { grep -E '^\| `' <<< "$1"; }
reg_note() { grep -Ev '^\|' <<< "$1"; }
reg_cell() { reg_rows "$1" | awk -F'|' -v g="\`$2\`" -v c="$3" '{ n = $2; gsub(/^ +| +$/, "", n); if (n == g) { v = $c; gsub(/^ +| +$/, "", v); print v; exit } }'; }
reg_globs() { reg_rows "$1" | awk -F'|' '{ n = $2; gsub(/^ +| +$/, "", n); gsub(/`/, "", n); print n }'; }

k06_no_pending() {
  local hits; hits="$(tr '\n' ' ' <<< "$REG_HEAD" | grep -Eio 'pending[^|.]{0,40}ADR-0005|pending[[:space:]]+\(?ADR-0005[^|]{0,30}|ADR-0005 (or|and) (ADR-)?0006')"
  [ -z "$hits" ] || { WHY="$PATHS still reads '$(head -n 1 <<< "$hits")'"; return 1; }
}
check "no 'pending ADR-0005' remains in the sensitive-paths register" k06_no_pending

k06_rows_cite() {
  local g cell
  while IFS= read -r g; do
    [ -n "$g" ] || continue
    reg_cell "$REG_BASE" "$g" 4 | grep -Eiq 'pending[^;]*ADR-0005' || continue
    cell="$(reg_cell "$REG_HEAD" "$g" 4)"
    [ -n "$cell" ] || { WHY="row '$g' is gone"; return 1; }
    has "$(sed -E 's/pending.*//' <<< "$cell")" 'ADR-0005' || { WHY="row '$g' does not cite ADR-0005 as accepted: '$cell'"; return 1; }
  done < <(reg_globs "$REG_BASE")
}
check "every register row that read 'pending ADR-0005' now cites ADR-0005" k06_rows_cite

k06_adr6_pending() {
  local c; c="$(reg_cell "$REG_HEAD" 'backend/app/integrations/**' 4)"
  [ -n "$c" ] || { WHY="the backend/app/integrations/** row is gone"; return 1; }
  has "$c" 'pending ADR-0006' || { WHY="the integrations row no longer reads 'pending ADR-0006': '$c'"; return 1; }
  local b h; b="$(reg_rows "$REG_BASE" | grep -o 'ADR-0006' | grep -c .)"; h="$(reg_rows "$REG_HEAD" | grep -o 'ADR-0006' | grep -c .)"
  [ "$b" -eq "$h" ] || { WHY="the register rows hold 'ADR-0006' $h time(s), $b at base"; return 1; }
  local note; note="$(reg_note "$REG_HEAD" | tr '\n' ' ')"
  has "$note" 'pending" \(ADR-0006\)|pending[^.]{0,20}ADR-0006' || { WHY="the header note does not mention ADR-0006 as pending"; return 1; }
  forbid "$note" 'pending[^.]{0,40}ADR-0005|ADR-0005 or 0006' || return 1
}
check "the integrations row keeps 'pending ADR-0006' and the header note names only ADR-0006 as pending" k06_adr6_pending

k06_register_classes() {
  local row g c
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    has "$(cell "$row" 4)" 'PD-' || continue
    for g in $(cell "$row" 2 | grep -Eo '`[^`]+`' | tr -d '`'); do
      c="$(reg_cell "$REG_HEAD" "$g" 3)"
      [ -n "$c" ] || { WHY="ADR-0005 names '$g' as holding personal data and the register has no row with that exact glob"; return 1; }
      tr ',' '\n' <<< "$c" | sed -E 's/^ +| +$//g' | grep -Fxq 'personal-data' || { WHY="register row '$g' lacks personal-data ('$c')"; return 1; }
      has "$(reg_cell "$REG_HEAD" "$g" 4)" 'ADR-0005' || { WHY="register row '$g' does not cite ADR-0005"; return 1; }
    done
  done <<< "$PATH_ROWS"
}
check 'every path ADR-0005 names as holding personal data is a register row with personal-data citing ADR-0005' k06_register_classes

# ==== K-07 ===================================================================================

# (4) Bans: no sentence purges backups or gives the server delete rights, allows a session beyond
# ADR-0003's bound, switches admin events off, or gives the reviewer runtime or superuser access —
# except one deviation approved at gate 1 on Issue #17 and named in ADR-0005 as the only one.
DEV_SENT="$(grep -Ei '^(- )?The only deviation from an accepted decision is\b' <<< "$DECISION_SENTS")"
dev_excuses() { [ -n "$DEV_SENT" ] && has "$DEV_SENT" "$1"; }

k07_change_sentence() {
  local c; c="$(sub_sents '^### Changes to accepted decisions')"
  if [ -z "$DEV_SENT" ]; then
    need "$c" '^This decision changes no accepted decision: not ADR-0001, ADR-0002, ADR-0003 or ADR-0004, by neither edit nor addendum\.$' 'Changes to accepted decisions' || return 1
    need "$c" 'no deviation from an accepted decision was approved' 'Changes to accepted decisions' || return 1
  fi
  need "$(sub_sents '^### Erasure and backups')" 'It adds no step to ADR-0004.s procedure, changes none of its steps or their order, and does not change ADR-0004' 'Erasure and backups' || return 1
}
check 'the Decision says it changes no accepted decision' k07_change_sentence

K07_DEV_EXCUSED=(
  "Adding a service would be a deviation from ADR-0004."
  "If the implementing task finds that it cannot, that task stops and the change returns to the human as an addendum to ADR-0004, before any service or image is added."
  "Gate 1 of EKO-1-04 (#17), on 2026-10-25, ruled that the restore re-apply of erasures and the shipping of Keycloak events off the server are within ADR-0004 and not deviations; no deviation from an accepted decision was approved."
  # Fix round 1: says that ADR-0004 is not edited, and what a cross-reference would need.
  "It adds no step to ADR-0004's procedure, changes none of its steps or their order, and does not change ADR-0004; ADR-0004's text is not edited for it, and a cross-reference there would be a dated addendum to ADR-0004."
)
k07_named_deviation() {
  local all; all="$(without "$DECISION_SENTS" "${K07_DEV_EXCUSED[@]}")"
  if [ -z "$DEV_SENT" ]; then
    forbid "$all" '\bdeviations?\b|\baddend(um|a) (to|of) ADR-000[1-4]\b|\bchanges ADR-000[1-4]\b' || return 1
    return 0
  fi
  [ "$(grep -c . <<< "$DEV_SENT")" -eq 1 ] || { WHY="more than one 'The only deviation' sentence"; return 1; }
  has "$DEV_SENT" 'approved by the human at gate 1 of EKO-1-04 \(#17\)' || { WHY="the named deviation does not say it was approved by the human at gate 1 of EKO-1-04 (#17)"; return 1; }
  local other; other="$(grep -Eo 'ADR-[0-9]{4}' <<< "$DEV_SENT" | sort -u)"
  [ "$(grep -c . <<< "$other")" -eq 1 ] || { WHY="the deviation sentence names more than one decision: $(tr '\n' ' ' <<< "$other")"; return 1; }
  forbid "$DEV_SENT" '\b(deviations|second|another|further|additional|also|as well|and (the|a) )\b' || return 1
  forbid "$(without "$all" "$DEV_SENT")" '\bdeviations?\b' || return 1
}
check 'the Decision names no deviation, or exactly one approved at gate 1 on Issue #17' k07_named_deviation

K07_BACKUP_EXCUSED=(
  "- Logs of every service of the composition (backend, migrate, keycloak, postgres, proxy, frontend, backup) are deleted no later than 14 days after they were written, also when they are small; deletion is by time, and rotation by size alone does not meet this rule."
  # Fix round 2: the verification host's excuse now also deletes the compared identifiers.
  "The IT department's verification host: its decrypted copy is deleted after the check (ADR-0004 Backup), and the customer identifiers the reconciliation compares are deleted with it (Erasure and backups)."
  "- Erased personal data stays in the backup sets taken before the erasure until ADR-0004's retention removes them: the sets of the last 30 days, and the verified sets kept beyond them until three newer sets have passed the verification."
  "No backup set is purged, shortened or overwritten because of an erasure, and the server gets no right to delete at the destination."
  "- Keycloak events and sessions inside backup sets are kept as long as their set (ADR-0004 Backup); this decision shortens no backup set."
  "Deletion is done by the destination's own housekeeping, not by the server."
  "The credential the server uses there can add events but cannot delete or overwrite any."
  # Fix round 1 (D-2, F-01): the entry's deletion bound and the restore host's decrypted copy,
  # which are not backup sets at the destination. The round-0 entry sentences are gone.
  # Fix round 2 (D-4, R-09): the entry deletion bound and the restore host, as revised. Each is a
  # bound on an entry of the erasure record or on a restore host's copies, not on a backup set.
  "An entry not marked failed or cancelled is deleted only once it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination."
  "- The off-server erasure record keeps each entry not marked failed or cancelled, completed entries and entries not yet marked alike, until it holds a commit time and no backup set whose snapshot started before that commit time remains at the destination (Erasure and backups)."
  "A restore host: the application database restored on it is covered by the re-apply (Erasure and backups); the decrypted backup set it received at ADR-0004 restore step 3 is deleted once the restore is recorded at step 14 or abandoned; a restore host that does not become the server, a test restore's host included, has its restored databases and volumes deleted once the restore is recorded or abandoned; and an abandoned restore, on any host, has its restored databases and volumes deleted once it is abandoned."
)
k07_no_backup_purge() {
  dev_excuses 'backup|purge|verified sets' && return 0
  local all; all="$(without "$DECISION_SENTS" "${K07_BACKUP_EXCUSED[@]}")"
  forbid "$all" '\b(purge[sd]?|purging|shorten(s|ed)?|overwrit(e|es|ten|ing)|delet(e|es|ed|ing)|remov(e|es|ed|ing)|rewrit(e|es|ten)|prune[sd]?|wipe[sd]?)\b[^.]*\b(backup sets?|verified sets?|sets holding|backups?|destination)\b' || return 1
  forbid "$all" '\b(backup sets?|verified sets?|backups?|destination)\b[^.]*\b(purge[sd]?|shorten(s|ed)?|overwrit(e|es|ten)|delet(e|es|ed)|remov(e|es|ed)|rewrit(e|es|ten)|prune[sd]?)\b' || return 1
  forbid "$all" '\bserver\b[^.]*\b(can|may|gets?|is given|has|holds?)\b[^.]*\b(delete|overwrite|purge)\b' || return 1
}
check 'no Decision sentence purges, shortens or overwrites backup sets or gives the server delete rights at the destination' k07_no_backup_purge

K07_SESSION_EXCUSED=(
  "- Server-side sessions, abandoned ones included, are deleted together with their encrypted tokens no later than the realm's SSO session maximum lifespan after the session was created."
  "- Keycloak events and sessions inside backup sets are kept as long as their set (ADR-0004 Backup); this decision shortens no backup set."
)
k07_no_long_session() {
  dev_excuses 'session' && return 0
  local all; all="$(without "$DECISION_SENTS" "${K07_SESSION_EXCUSED[@]}")"
  forbid "$all" '\bsessions?\b[^.]*\b(kept|retained|stored|deleted|removed|purged|live|lives|remain|remains|survive)\b[^.]*\b(beyond|longer than|more than|past|exceed)\b' || return 1
  forbid "$all" '\bsessions?\b[^.]*\b(kept|retained|stored|deleted|removed|purged)\b[^.]*\b(last use|last used|last activity|idle|inactivity|indefinitely|forever)\b' || return 1
  forbid "$all" "\\bsessions?\\b[^.]*\\b(kept|retained|stored|deleted|removed|purged)\\b[^.]*\\b($NUMW) ($UNITW)\\b" || return 1
}
check "no Decision sentence lets a session outlive ADR-0003's bound" k07_no_long_session

K07_ADMIN_EXCUSED=("${K03_ZERO_EXCUSED[@]}" "- Admin-event retention, never zero — ADR-0003 l.204 → decided in Retention." "It works within ADR-0004's backup retention (30 days and the verified sets), ADR-0004's destination to which the server can only add, ADR-0004's seven services and the official Keycloak image, ADR-0003's bound on deleting abandoned sessions, and ADR-0003's rule that admin-event retention is never zero.")
k07_no_admin_off() {
  dev_excuses 'admin event' && return 0
  local all; all="$(without "$DECISION_SENTS" "${K07_ADMIN_EXCUSED[@]}")"
  forbid "$all" '\badmin events?\b[^.]*\b(may|can|are|is|need not)\b[^.]*\b(switched off|turned off|disabled|not stored|off|zero)\b' || return 1
  forbid "$all" '\b(switch|turn)(es|ed|ing)? off\b[^.]*\badmin events?\b|\badmin[- ]event retention\b[^.]*\b(zero|0)\b' || return 1
}
check 'no Decision sentence sets admin-event retention to zero or switches admin events off' k07_no_admin_off

K07_REVIEWER_EXCUSED=("${K02_RUNTIME_EXCUSED[@]}")
k07_no_reviewer_runtime() {
  dev_excuses 'reviewer' && return 0
  local all; all="$(without "$DECISION_SENTS" "${K07_REVIEWER_EXCUSED[@]}")"
  forbid "$all" '\breviewer\b[^.]*\b(container runtime|docker|superuser|database role password|postgres(ql)? role|root)\b' || return 1
  forbid "$all" '\b(container runtime|superuser)\b[^.]*\breviewer\b' || return 1
}
check 'no Decision sentence gives the reviewer container-runtime or superuser access' k07_no_reviewer_runtime

k07_gh_deviation() {
  command -v gh >/dev/null 2>&1 || { WHY="gh is not installed (use --offline to skip by name)"; return 1; }
  local labels body
  labels="$(gh issue view "$ISSUE" --repo "$REPO_SLUG" --json labels -q '.labels[].name' 2>/dev/null)" || { WHY="gh could not read Issue #$ISSUE"; return 1; }
  if [ -z "$DEV_SENT" ]; then
    ! grep -Fxq 'adr-deviation' <<< "$labels" || { WHY="Issue #$ISSUE carries adr-deviation, but ADR-0005 names no deviation"; return 1; }
    return 0
  fi
  grep -Fxq 'adr-deviation' <<< "$labels" || { WHY="ADR-0005 names a deviation, but Issue #$ISSUE has no adr-deviation label (no gate-1 approval recorded)"; return 1; }
  body="$(gh issue view "$ISSUE" --repo "$REPO_SLUG" --json body -q .body 2>/dev/null | tr -d '\r')"
  has "$(grep -E '^Must stay|approved deviation' <<< "$body")" 'approved at gate 1' || { WHY="Issue #$ISSUE records no gate-1 approval of the deviation"; return 1; }
}
if [ -n "$OFFLINE" ]; then skip "Issue #17 records the deviation ADR-0005 names, or none" '--offline'
else check "Issue #17 records the deviation ADR-0005 names, or none" k07_gh_deviation; fi

# --- (1), (2), (3): the accepted decisions and the change set ---

changed_files() {
  if [ -n "$HEAD_REF" ]; then git diff --name-only "$MB" "$HEAD_REF"
  else { git diff --name-only "$MB"; git ls-files --others --exclude-standard; } | sort -u; fi
}
CHANGED="$(changed_files)"

K07_SKIP=""
if [ -z "$BASE_GIVEN" ] && git cat-file -e "$BASE_REF:$ADR5" 2>/dev/null; then
  K07_SKIP="$ADR5 already exists at $BASE_REF (the task is merged); re-run with --base <merge>^1 --head <merge>^2"
fi
check07() { if [ -n "$K07_SKIP" ]; then skip "$1" "$K07_SKIP"; return 0; fi; check "$@"; }

# Blob identity: the working-tree file (through git's clean filter) or the --head blob has the
# same object id as the file at TASK_BASE.
blob_now() {
  if [ -n "$HEAD_REF" ]; then git rev-parse --verify --quiet "$HEAD_REF:$1"
  else [ -f "$1" ] && git hash-object -- "$1"; fi
}
k07_adrs_identical() {
  local f a b
  for f in "$ADR1" "$ADR2" "$ADR3" "$ADR4"; do
    a="$(git rev-parse --verify --quiet "$TASK_BASE:$f")"; b="$(blob_now "$f")"
    [ -n "$b" ] || { WHY="$f is gone"; return 1; }
    [ "$a" = "$b" ] || { WHY="$f differs from $TASK_BASE (blob $b, base $a)"; return 1; }
  done
  # No other accepted decision file appears or disappears.
  local list; if [ -n "$HEAD_REF" ]; then list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/")"; else list="$(ls "$DECISIONS"/*.md | sort)"; fi
  local extra; extra="$(grep -E '/ADR-[0-9]{4}' <<< "$list" | grep -Ev '/ADR-000[1-4]-|/ADR-0005-')"
  [ -z "$extra" ] || { WHY="another decision file: $(tr '\n' ' ' <<< "$extra")"; return 1; }
}
check 'ADR-0001..0004 are byte-identical to the task base' k07_adrs_identical

ALLOWED_RE='^(docs/architecture/decisions/ADR-0005-[^/]*\.md|tests/doc-checks/EKO-1-04\.sh|docs/architecture/architecture-sensitive-paths\.md|docs/cost-register/.*)$'
k07_only_allowed() {
  local extra; extra="$(grep . <<< "$CHANGED" | grep -Ev "$ALLOWED_RE")"
  [ -z "$extra" ] || { WHY="outside the allowed set: $(tr '\n' ' ' <<< "$extra")"; return 1; }
}
check07 'the change set touches only ADR-0005, its document checks, the register and cost bookkeeping' k07_only_allowed

k07_no_impl() {
  local bad; bad="$(grep -E '^(backend/|frontend/|identity/|\.github/)' <<< "$CHANGED")"
  [ -z "$bad" ] || { WHY="listed: $(tr '\n' ' ' <<< "$bad")"; return 1; }
}
check07 'the change set holds nothing under backend/, frontend/, identity/ or .github/' k07_no_impl

k07_register_rows() {
  local base_reg g bc hc c
  base_reg="$(at "$MB" "$PATHS")"
  [ -n "$(reg_globs "$base_reg")" ] || { WHY="no register rows at $MB"; return 1; }
  while IFS= read -r g; do
    [ -n "$g" ] || continue
    bc="$(reg_cell "$base_reg" "$g" 3)"; hc="$(reg_cell "$REG_HEAD" "$g" 3)"
    [ -n "$hc" ] || { WHY="register row '$g' is gone"; return 1; }
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      tr ',' '\n' <<< "$hc" | sed -E 's/^ +| +$//g' | grep -Fxq -- "$c" || { WHY="register row '$g' lost the risk class '$c' ('$hc')"; return 1; }
    done < <(tr ',' '\n' <<< "$bc" | sed -E 's/^ +| +$//g')
  done < <(reg_globs "$base_reg")
}
check07 'every base row of the register remains with its glob and every risk class' k07_register_rows

# ---- result --------------------------------------------------------------------------------

echo "EKO-1-04 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE_REF, merge base $MB, head ${HEAD_REF:-working tree})"
[ "$failed" -eq 0 ]
