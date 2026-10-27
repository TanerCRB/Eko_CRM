#!/usr/bin/env bash
# EKO-1-05 — document checks for the Google Calendar decision (ADR-0006), criteria K-01..K-07 of
# Issue #18.
#
#   bash tests/doc-checks/EKO-1-05.sh                       # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-05.sh --head <ref>          # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-05.sh --base <ref> [...]    # another base than origin/main
#   bash tests/doc-checks/EKO-1-05.sh --offline [...]       # skip the check that asks GitHub
#
# Every document is read from the same place as the change set: the working tree by default (so a
# mutation applied to a file, committed or not, is seen by every check, including the change-set
# checks of K-07, which then compare the merge base of <base> and HEAD with the working tree plus
# untracked files), or the commit named by --head (then `git diff <merge base>..<head>`).
#
# Each check is one line of output, "ok   <name>", "FAIL <name> — <why>" or "skip <name> — <why>".
# The names are the ones the PR's "K-<n> — test:" lines quote. Exit codes: 0 = every check that ran
# passed, 1 = at least one check failed, 2 = the script itself could not run (bad argument,
# missing file, not a repository) — never read 2 as a pass.
#
# Content checks on ADR-0006 read it with every HTML comment removed (inline and multi-line); an
# opening "<!--" with no closing "-->" fails its own check and hides the rest of the file from the
# others. They are scoped to "## Decision" or to one of its "###" sections, as each check says.
# Tables are read cell by cell from the raw section text (an indented table is a table too).
#
# Bases. TASK_BASE below is the commit the task branched from (4273cb3). The forwards K-07 counts
# are read from ADR-0001..0005 as they stand there, ADR-0001..0005 are compared with it, and the
# two registers are compared with it row by row. The K-07 change set is
# `git diff <merge base of --base and head>`, the change set a pull request against main shows.
# After the merge, re-run every check with main's commit before the merge as base and the PR's
# head commit:
#
#   bash tests/doc-checks/EKO-1-05.sh --base <merge>^1 --head <merge>^2
#
# Without --base, when ADR-0006 already exists at origin/main (the task is merged), the K-07
# change-set checks print "skip" with that command and are not counted. With an explicit --base
# nothing is skipped.
#
# The check that asks GitHub through `gh` (Issue #18 carries no adr-deviation label, or one that
# ADR-0006 names) fails when `gh` cannot answer; --offline prints it as "skip" instead, by name.
#
# The figures of K-01 (7-day expiry, 100 test users) are brief section 5's; the bounds of K-04
# (about 1 minute app to Google, 5 minutes Google to app) are VIS-6's. Durations are compared in
# minutes after the unit is normalised.
#
# What these checks are: line, cell and sentence matching over prose. They prove that a statement
# is present (or absent) in the decision, not that the statement is true of any running system or
# of Google.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
TASK_BASE="4273cb36c09811368b6a76e0f8777ffd1e4eca37"
HEAD_REF=""
OFFLINE=""
REPO_SLUG="TanerCRB/Eko_CRM"
ISSUE=18
die() { echo "EKO-1-05 doc-checks: $* — the checks did not run" >&2; exit 2; }
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
ADR5="$DECISIONS/ADR-0005-personal-data.md"
PATHS="docs/architecture/architecture-sensitive-paths.md"
LAYERS="docs/architecture/layer-dependencies.md"

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
  adr6_list="$(ls "$DECISIONS"/ADR-0006-*.md 2>/dev/null)"
else
  adr6_list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/" | grep -E '/ADR-0006-[^/]*\.md$')"
fi
[ "$(printf '%s\n' "$adr6_list" | grep -c .)" -eq 1 ] || die "expected exactly one $DECISIONS/ADR-0006-*.md, found: '${adr6_list}'"
ADR6="$adr6_list"
for f in "$ADR6" "$ADR1" "$ADR2" "$ADR3" "$ADR4" "$ADR5" "$PATHS" "$LAYERS"; do content "$f" >/dev/null || die "cannot read $f"; done
for f in "$ADR1" "$ADR2" "$ADR3" "$ADR4" "$ADR5" "$PATHS" "$LAYERS"; do [ -n "$(at "$TASK_BASE" "$f")" ] || die "cannot read $f at $TASK_BASE"; done

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
    /^[[:space:]]*\|/ { flush(); buf = $0; flush(); next }
    /^(#|[[:space:]]*- |\* |[[:space:]]*[0-9]+\. )/ { flush(); buf = $0; if ($0 ~ /^#/) flush(); next }
    { buf = (buf == "" ? $0 : buf " " $0) }
    END { flush() }'
}
sents() { sed -E 's/\. ([A-Z(])/.\n\1/g'; }
# trows — the body rows of every table in the text (header and separator dropped), leading
# blanks removed, ** and ` removed.
trows() {
  awk '
    /^[[:space:]]*\|/ { l = $0; sub(/^[[:space:]]+/, "", l)
      if (!intab) { intab = 1; next }
      if (l ~ /^\|[-:| ]+\|[[:space:]]*$/) next
      gsub(/\*\*|`/, "", l); print l; next }
    { intab = 0 }'
}
# theads — the header row of every table in the text, ** and ` removed.
theads() {
  awk '/^[[:space:]]*\|/ { l = $0; sub(/^[[:space:]]+/, "", l); if (!intab) { gsub(/\*\*|`/, "", l); print l }; intab = 1; next } { intab = 0 }'
}
# cell <row> <n> — the n-th cell (1-based) of a table row, trimmed.
cell() { awk -F'|' -v c="$(($2 + 1))" '{ v = $c; gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); print v }' <<< "$1"; }
ncells() { awk -F'|' '{ print NF - 2 }' <<< "$1"; }
# bullet <text> <ERE> — the top-level list item ("- " at column 0) whose first line, with ** and `
# removed, matches the ERE (passed through the environment, so no awk escape processing), with
# its continuation and nested items, up to the next top-level item or heading.
bullet() {
  RE="$2" awk '
    BEGIN { re = ENVIRON["RE"] }
    on && (/^- / || /^#/) { exit }
    !on && /^- / { l = $0; gsub(/\*\*|`/, "", l); if (l ~ re) on = 1 }
    on { print }' <<< "$1"
}
flat() { paras | sents; }

ADR6_RAW="$(content "$ADR6")"
ADR6_TEXT="$(printf '%s\n' "$ADR6_RAW" | strip_comments)"; STRIP_RC=$?
DECISION_TEXT="$(printf '%s\n' "$ADR6_TEXT" | section '^## Decision')"
DECISION_SENTS="$(printf '%s\n' "$DECISION_TEXT" | flat)"
sub_text() { printf '%s\n' "$DECISION_TEXT" | section "$1"; }
sub_sents() { sub_text "$1" | flat; }
ADR5_TEXT="$(content "$ADR5")"
CAT_IDS="$(grep -Eo '^\| \*\*PD-[CS][0-9]+' <<< "$ADR5_TEXT" | grep -Eo 'PD-[CS][0-9]+' | sort -u)"
[ -n "$CAT_IDS" ] || die "no PD- category found in $ADR5"

S_LINK="$(sub_text '^### Who links')"
S_OAUTH="$(sub_text '^### OAuth flow and scope')"
S_TEST="$(sub_text '^### Testing mode')"
S_TOKEN="$(sub_text '^### Token storage')"
S_SECRETS="$(sub_text '^### Secrets')"
S_BG="$(sub_text '^### Background work')"
S_EVENT="$(sub_text '^### Event content')"
S_RECOG="$(sub_text '^### Recognising')"
S_CHANGE="$(sub_text '^### Change detection')"
S_CONFLICT="$(sub_text '^### Conflict rule')"
S_RETRY="$(sub_text '^### Retry')"
S_ERASE="$(sub_text '^### Erasure and calendar events')"
S_LOST="$(sub_text '^### Lost access')"
S_CHANGES="$(sub_text '^### Changes to accepted decisions')"
S_FWD="$(sub_text '^### Items forwarded')"

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
  [ -z "${DEBUG_HITS:-}" ] || [ -z "$hits" ] || printf 'HIT %s\n' "$hits" >&2
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | head -n 1 | cut -c1-220)"; return 1; }
}
# without <text> <exact sentence>... — the text with each listed sentence (a whole line, compared
# literally, emphasis marks removed on both sides) replaced by a marker. A ban then excuses a
# restating sentence only by its exact text: an edit of it brings it back under the ban.
without() {
  local t="$1"; shift
  local IFS=$'\037'
  X="$*" awk 'BEGIN { n = split(ENVIRON["X"], xs, "\037"); for (i = 1; i <= n; i++) { x = xs[i]; gsub(/\*/, "", x); ex[x] = 1 } }
    { l = $0; gsub(/\*/, "", l); if (l in ex) { print "EXCUSED-SENTENCE"; next }; print }' <<< "$t"
}
# A sentence of <text> that matches every ERE given (case-insensitive).
sent_with() {
  local t="$1"; shift
  local re
  for re in "$@"; do t="$(grep -Ei -- "$re" <<< "$t")"; [ -n "$t" ] || return 1; done
  printf '%s\n' "$t"
}
need_sent() {  # need_sent <text> <where> <ERE>... — one sentence matching all
  local t="$1" w="$2"; shift 2
  sent_with "$t" "$@" >/dev/null || { WHY="no sentence${w:+ in $w} matching all of: $(printf '/%s/ ' "$@")"; return 1; }
}

# ---- durations ---------------------------------------------------------------------------

NUMW='[0-9]+|one|two|three|five|ten|fifteen|thirty|a|an'
UNITW='seconds?|minutes?|hours?|days?|weeks?'
to_min() {
  awk -v n="$1" -v u="$2" 'BEGIN {
    n = tolower(n); u = tolower(u)
    w["one"]=1; w["a"]=1; w["an"]=1; w["two"]=2; w["three"]=3; w["five"]=5; w["ten"]=10
    w["fifteen"]=15; w["thirty"]=30
    if (n in w) n = w[n]
    sub(/s$/, "", u)
    m["second"]=1/60; m["minute"]=1; m["hour"]=60; m["day"]=1440; m["week"]=10080
    print n * m[u] }'
}
# figs <text> <anchor ERE> — minutes of every "<anchor> <number> <unit>" in the text, one per line.
figs() {
  local hit
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    to_min "$(awk '{ print $(NF-1) }' <<< "$hit")" "$(awk '{ print $NF }' <<< "$hit")"
  done < <(grep -Eio -- "$2 ($NUMW)[ -]($UNITW)\b" <<< "$1")
}
# figs_all_eq <text> <anchor> <minutes> <what> — at least one figure, and every figure equal.
figs_all_eq() {
  local v vs; vs="$(figs "$1" "$2")"
  [ -n "$vs" ] || { WHY="$4: no figure after /$2/"; return 1; }
  while IFS= read -r v; do
    awk -v a="$v" -v b="$3" 'BEGIN { exit !(a == b) }' || { WHY="$4 is $v minutes, the required figure is $3 minutes"; return 1; }
  done <<< "$vs"
}

# ==== K-01 ===================================================================================

k01_comments() { [ "$STRIP_RC" -eq 0 ] || { WHY="an opening <!-- is never closed"; return 1; }; }
check 'ADR-0006 has no unterminated comment' k01_comments

k01_status() {
  local st; st="$(grep -E '^\*\*Status:\*\*' <<< "$ADR6_TEXT")"
  [ "$(grep -c . <<< "$st")" -eq 1 ] || { WHY="expected one status line, found: $(tr '\n' '/' <<< "$st")"; return 1; }
  grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' <<< "$st" || { WHY="status line: $st"; return 1; }
}
check 'ADR-0006 status reads Accepted' k01_status

k01_flow() {
  need_sent "$(flat <<< "$(bullet "$S_OAUTH" '^- Flow[.]')")" 'Flow' '\bauthorization code flow\b' '\bPKCE\b' '\boffline access\b'
}
check 'the Decision names the OAuth flow: authorization code with PKCE and offline access' k01_flow

# The scope table of "OAuth flow and scope": every row a scope with its reason, every scope a
# Google Calendar events scope; the stated count equals the rows; no other Google scope URL in the
# Decision, and the sentence excluding every other scope stays.
SCOPE_OK='^https://www\.googleapis\.com/auth/calendar\.events(\.owned)?$'
k01_scopes() {
  local rows r s why n count
  rows="$(trows <<< "$(awk '/^[[:space:]]*\| *Scope *\| *Reason *\|/ { on = 1 } on && !/^[[:space:]]*\|/ { exit } on' <<< "$S_OAUTH")")"
  [ -n "$rows" ] || { WHY="no Scope | Reason table in OAuth flow and scope"; return 1; }
  n=0
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    n=$((n + 1))
    s="$(cell "$r" 1)"; why="$(cell "$r" 2)"
    [ "$(ncells "$r")" -eq 2 ] || { WHY="scope row with $(ncells "$r") cells: $r"; return 1; }
    grep -Eq "$SCOPE_OK" <<< "$s" || { WHY="scope '$s' is not a Google Calendar events scope"; return 1; }
    [ "$(wc -w <<< "$why")" -ge 5 ] || { WHY="scope '$s' has no reason ('$why')"; return 1; }
  done <<< "$rows"
  count="$(grep -Eio '\bexactly (one|two|three|[0-9]+) scopes? (is|are) requested\b' <<< "$(flat <<< "$S_OAUTH")" | awk '{ print tolower($2) }')"
  case "$count" in one) count=1 ;; two) count=2 ;; three) count=3 ;; esac
  [ -n "$count" ] || { WHY="no 'Exactly <n> scope(s) is/are requested' sentence"; return 1; }
  [ "$count" -eq "$n" ] || { WHY="the Decision says $count scope(s), the table has $n"; return 1; }
  local urls; urls="$(grep -Eo 'https://www\.googleapis\.com/auth/[A-Za-z0-9._/-]+' <<< "$DECISION_TEXT" | sed -E 's/[.]$//' | grep -Ev "$SCOPE_OK")"
  [ -z "$urls" ] || { WHY="another Google scope in the Decision: $(head -n 1 <<< "$urls")"; return 1; }
  # A scope added in prose, by name rather than URL (a send-mail, contacts or drive scope).
  forbid "$DECISION_SENTS" '\b(requests?|requested|asks? for|grants?)\b[^.;]*\b(gmail\.[a-z]+|mail\.google\.com|contacts(\.readonly)?|drive(\.[a-z]+)?|userinfo\.[a-z]+|send-mail|mail-sending|mail|e-mail sending)\b scopes?\b|\b(gmail\.[a-z]+|send-mail|mail|contacts|drive)\b scopes? (is|are) (also )?(requested|added|asked for)\b' || return 1
  need_sent "$(flat <<< "$S_OAUTH")" 'OAuth flow and scope' '^No other scope is requested\b' '\bmail\b' '\bcontacts\b' || return 1
}
check 'exactly the stated scopes are requested, each with its reason, none beyond calendar events' k01_scopes

k01_own_session() {
  need_sent "$(flat <<< "$S_LINK")" 'Who links' '^- A link is made only by the staff member whose calendar it is, from their own application session\.$' || return 1
  need_sent "$(flat <<< "$S_LINK")" 'Who links' '^No one links, relinks or unlinks a calendar for another staff member' || return 1
}
check 'a link is made only by the staff member whose calendar it is, from their own application session' k01_own_session

k01_binding() {
  local b; b="$(flat <<< "$(bullet "$S_OAUTH" 'Binding to the rep.s own session')")"
  need_sent "$b" 'Binding' '\blink transaction\b' '\bstate\b' '\bPKCE verifier\b' '\bsubject of the session\b' '\bhash of that session.s identifier\b' || return 1
  need_sent "$b" 'Binding' '\bcompletes the link only when\b' '\bsession is the session that started the transaction\b' '\bsame subject and same session-identifier hash\b' '\bstate equals the transaction.s\b' || return 1
  need_sent "$b" 'Binding' '^Otherwise it refuses, stores nothing\b' || return 1
}
check 'the callback is tied to the session that started the link: same subject, same session, same state' k01_binding

k01_double_submit() {
  need_sent "$(flat <<< "$S_OAUTH")" 'OAuth flow and scope' '\bsecond completion of one transaction is refused\b' || return 1
  need_sent "$(flat <<< "$S_OAUTH")" 'OAuth flow and scope' '\bsingle use\b' '\bdeleted at completion\b' || return 1
}
check 'a second completion of one link transaction is refused' k01_double_submit

k01_shared_account() {
  need_sent "$(flat <<< "$(bullet "$S_RECOG" 'Ownership')")" 'Ownership' '\banother owner.s visit\b' '\btwo staff members linking one Google account\b' '\bnever changed or deleted\b' '\bcounts nowhere\b'
}
check "one Google account linked by two staff members never carries one owner's change to the other's event" k01_shared_account

# Fix round 1 (B-02): a calendar holding another owner's marked event holds the link unused, at
# link or relink and at every poll, and no choice of the owner lifts the hold.
K01_HOLD_EXCUSED=(
  "- When the list holds an event the application records in another owner's calendar, the link stays held unused whatever else is found, and no choice of the owner lifts the hold (*Ownership*)."
)
k01_ownership_hold() {
  local o; o="$(flat <<< "$(bullet "$S_RECOG" 'Ownership')")"
  need_sent "$o" 'Ownership' '^Such an event also holds that link unused: at a link or relink\b' '\band at every poll\b' "\\ba link whose calendar holds a live event carrying this environment.s marker that the application records in another owner.s calendar is no longer used\\b" "\\bits owner.s jobs are suspended\\b" '\bwith no customer value and no staff member named\b' || return 1
  need_sent "$o" 'Ownership' '^The hold sends nothing more into that calendar\b' || return 1
  need_sent "$(flat <<< "$S_OAUTH")" 'Relinking a different Google account' "^- When the list holds an event the application records in another owner.s calendar, the link stays held unused whatever else is found, and no choice of the owner lifts the hold\\b" || return 1
  # No sentence lets an owner's choice, or a confirmation, lift that hold.
  local all; all="$(without "$DECISION_SENTS" "${K01_HOLD_EXCUSED[@]}")"
  forbid "$all" '\b(lifts?|lifted|releases?|released|ends?|ended|removes?|removed)\b[^.]*\bhold\b|\bhold\b[^.]*\b(is|are) (lifted|released|ended|removed)\b' 'until they unlink or relink another account' || return 1
}
check "a calendar holding another owner's marked event holds the link unused, at link, relink and every poll, and no choice of the owner lifts the hold" k01_ownership_hold

k01_callback() {
  local b; b="$(flat <<< "$(bullet "$S_OAUTH" 'Binding to the rep.s own session')")"
  need_sent "$b" 'Binding' '\bcallback path https://<app-host>/[a-z0-9/_-]+\b' || return 1
  forbid "$DECISION_SENTS" '\bcallback\b[^.]*<(auth|auth-admin)-host>|<(auth|auth-admin)-host>[^.]*\bcallback\b' || return 1
  need_sent "$b" 'Binding' '\bonly authorised redirect URI\b' || return 1
}
check 'the Google callback path is on <app-host> and is the only authorised redirect URI' k01_callback

K01_BROKER_EXCUSED=(
  "Linking a Google account creates, authenticates and alters no account, and is not done through Keycloak's identity brokering (ADR-0003, *Accounts never depend on Google*)."
  "Keycloak has no Google identity provider; the Google OAuth client is the backend's own client, separate from the application's Keycloak client."
  "It works within ADR-0001's single backend language and image and its layer rules, ADR-0002's database-backed queue and instants, ADR-0003's backend session, Origin check, Keycloak without identity providers and the rule that the application holds no staff e-mail address, ADR-0004's one origin, secret rules, migration rules and restore steps, and ADR-0005's rule on data sent to Google, its categories, its logging rules and its re-apply."
)
k01_no_account() {
  need_sent "$(flat <<< "$S_LINK")" 'Who links' '^Linking a Google account creates, authenticates and alters no account, and is not done through Keycloak.s identity brokering\b' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K01_BROKER_EXCUSED[@]}")"
  forbid "$all" '\bbroker(ing|ed)?\b|\bidentity providers?\b|\b(through|via) Keycloak\b|\bKeycloak (links?|brokers?)\b|\blink(s|ed|ing)? (in|by|with) Keycloak\b' 'message broker' || return 1
  forbid "$all" '\blink(ing|ed)?\b[^.]*\b(creates?|authenticates?|signs? in|logs? in)\b[^.]*\baccount\b' 'creates, authenticates and alters no account' || return 1
}
check 'linking creates, authenticates and alters no account and does not use Keycloak brokering' k01_no_account

K01_LOGIN_EXCUSED=(
  "No page, operation or role requires a link."
)
k01_login() {
  need_sent "$(flat <<< "$S_LINK")" 'Who links' '^- Login works with no Google account linked \(ACC-2\)\.$' || return 1
  need_sent "$(flat <<< "$S_LINK")" 'Who links' '^No page, operation or role requires a link\.$' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K01_LOGIN_EXCUSED[@]}")"
  forbid "$all" '\b(requires?|required|must|needs?|needed|mandatory)\b[^.]*\b(a |the )?(Google )?(link|linked|linking)\b[^.]*\b(log ?in|login|sign[- ]in|first use|access)\b|\b(log ?in|login|sign[- ]in)\b[^.]*\b(requires?|required|needs?|only after|depends on)\b[^.]*\b(link|Google)\b' || return 1
  forbid "$all" '\b(link|linking|linked)\b[^.]*\b(required|mandatory|needed|a precondition|a condition)\b[^.]*\b(before|for|to)\b[^.]*\b(log ?in|login|sign[- ]in|first use|use the application)\b' || return 1
}
check 'login works with no Google account linked and no page, operation or role requires a link' k01_login

k01_expiry() {
  local b; b="$(flat <<< "$(bullet "$S_TEST" 'testing mode')")"
  need_sent "$b" 'Testing mode' '^- The 7-day expiry\.' || return 1
  need_sent "$b" 'Testing mode' '\bVIS-8 reconnect notice\b' '\bno visit state changes\b' '\bpending changes are kept\b' '\bsynchronise after relinking\b' || return 1
  # Every day figure tied to the expiry or the relink, anywhere in the Decision, is 7 days.
  local v; v="$(grep -Ei 'expir|relink' <<< "$DECISION_SENTS" | grep -Eio '\b[0-9]+[ -](days?|weeks?)\b' | sed -E 's/[ -]/ /' | sort -u)"
  [ -n "$v" ] || { WHY="no day figure tied to the expiry"; return 1; }
  [ "$(awk '{ print $1 }' <<< "$v" | sort -u)" = "7" ] && ! grep -Eiq 'week' <<< "$v" || { WHY="expiry or relink figures in the Decision: $(tr '\n' ' ' <<< "$v") (the expiry is 7 days)"; return 1; }
}
check 'the 7-day expiry is in the Decision with the VIS-8 notice, no visit state change and pending changes kept' k01_expiry

k01_cap() {
  local b; b="$(flat <<< "$(bullet "$S_TEST" 'testing mode')")"
  need_sent "$b" 'Testing mode' '^- The cap of 100 test users\.' || return 1
  need_sent "$b" 'Testing mode' '\bpast the cap\b' '\bcannot complete a link\b' '\bworks for them as with no link\b' '\bUnsynchronised \(VIS-7\)' || return 1
  local v; v="$(grep -Eio '\b(cap of|at most|more than) [0-9]+( test users| can be entered)?|\b[0-9]+ test users\b' <<< "$DECISION_SENTS" | grep -Eo '[0-9]+' | sort -u)"
  [ "$v" = "100" ] || { WHY="test-user figures in the Decision: $(tr '\n' ' ' <<< "$v") (the cap is 100)"; return 1; }
}
check 'the cap of 100 test users is in the Decision, with what a rep past the cap gets' k01_cap

k01_verification() {
  local s; s="$(flat <<< "$S_TEST")"
  need_sent "$s" 'Testing mode' '^- Verification path\.' '\bverification\b' || return 1
  need_sent "$s" 'Testing mode' '\bdomain\b' '\bprivacy policy\b' "\\bGoogle.s review\\b" || return 1
}
check "the verification path names what it needs: a verified domain, a privacy policy and Google's review" k01_verification

k01_closing() {
  local s; s="$(flat <<< "$(bullet "$S_TEST" 'When it closes')")"
  need_sent "$s" 'When it closes' '\bbrief section 3\b' '\bitem 10\b' '\bbefore go-live\b' '\bearlier if the pilot needs more than testing mode allows\b' || return 1
}
check 'the verification closes before go-live, or earlier if the pilot needs more than testing mode allows' k01_closing

# ==== K-02 ===================================================================================

k02_stored() {
  local tab rows r item cat id n=0
  tab="$(awk '/^[[:space:]]*\| *Item *\| *Category/ { on = 1 } on && !/^[[:space:]]*\|/ { exit } on' <<< "$S_TOKEN")"
  rows="$(trows <<< "$tab")"
  [ -n "$rows" ] || { WHY="no Item | Category table in Token storage"; return 1; }
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    n=$((n + 1))
    item="$(cell "$r" 1)"; cat="$(cell "$r" 2)"
    [ "$(ncells "$r")" -eq 2 ] || { WHY="stored-item row with $(ncells "$r") cells: $r"; return 1; }
    if grep -Eiq '^not personal data$' <<< "$cat"; then continue; fi
    grep -Eq '^PD-[CS][0-9]+(, PD-[CS][0-9]+)*$' <<< "$cat" || { WHY="stored item '$item' has no ADR-0005 category ('$cat')"; return 1; }
    for id in $(grep -Eo 'PD-[CS][0-9]+' <<< "$cat"); do
      grep -Fxq "$id" <<< "$CAT_IDS" || { WHY="stored item '$item': $id is not an ADR-0005 category"; return 1; }
    done
  done <<< "$rows"
  grep -Eiq '^\| *the Google refresh token, encrypted *\|' <<< "$rows" || { WHY="no stored-item row for the encrypted refresh token"; return 1; }
  grep -Eiq '^\| *the subject identifier\b' <<< "$rows" || { WHY="no stored-item row for the subject identifier"; return 1; }
  need_sent "$(flat <<< "$S_TOKEN")" 'Token storage' '\band nothing else\b' || return 1
  need_sent "$(flat <<< "$S_TOKEN")" 'Token storage' '^Every item falls under an existing ADR-0005 category or is not personal data\b' || return 1
}
check 'every item a link stores is listed with an ADR-0005 category or "not personal data"' k02_stored

k02_tokens() {
  local s; s="$(flat <<< "$S_TOKEN")"
  need_sent "$s" 'Token storage' '\brefresh token is encrypted at rest\b' || return 1
  need_sent "$s" 'Token storage' '^The access token is never stored\b' || return 1
  need_sent "$s" 'Token storage' '^No Google account identifier, e-mail address, name or ID token is stored\.$' || return 1
}
check 'the refresh token is encrypted at rest, the access token and any Google account identifier are never stored' k02_tokens


k02_key_location() {
  local s k; s="$(flat <<< "$S_TOKEN")"
  k="$(sent_with "$s" '\b(the|Google token encryption) key\b' '\b(neither in|not in|outside|never in)\b[^.:;]*\bapplication database\b' '\b(nor in|not in|outside|never in)\b[^.:;]*\b(any|every) backup set\b')" \
    || { WHY="no sentence placing the key outside the application database and every backup set"; return 1; }
  need_sent "$s" 'Token storage' '\bkey\b' '\benvironment variable\b' '\benvironment file\b' || return 1
  # No sentence of the Decision places the key in the database, a column, a table or a backup set.
  local all; all="$(without "$DECISION_SENTS" "$k" "${K02_KEY_EXCUSED[@]}")"
  forbid "$all" '\b(encryption key|the key)\b[^.;]*\b(is|are)? ?(held|kept|stored|placed|saved|written|lives?|sits?)\b[^.;:]*\b(in|inside|into|beside|next to|with)\b[^.;:]*\b(application database|database|column|table|backup sets?)\b' || return 1
  forbid "$all" '\b(application database|database|column|table|backup sets?)\b[^.;]*\b(holds?|stores?|keeps?|contains?)\b[^.;]*\b(encryption key|the key)\b' || return 1
  # Fix round 1 (R-07 (3)): a verb list misses "is also in", "a copy of the key goes to". Any
  # sentence naming a key together with the database, a column, a table or a backup set fails,
  # unless it is one of the excused sentences by its exact text.
  local hits; hits="$(grep -Ei '\bkeys?\b' <<< "$all" | grep -Ei '\b(application database|database|column|table|backups?|backup sets?|dump)\b')"
  [ -z "$hits" ] || { WHY="a sentence names a key with the database or a backup set: $(head -n 1 <<< "$hits" | cut -c1-220)"; return 1; }
}
K02_KEY_EXCUSED=(
  "A link whose token was encrypted before a key replacement made after the backup set was taken cannot be decrypted, and is handled as under *Token storage*: access lost, the token kept until the owner relinks."
  "A restore takes the Google token encryption key from its master copy like every other secret (ADR-0004 restore step 2) and does not replace it, so restored links keep working; a link whose grant was revoked since the backup is refused by Google at its first use and handled as lost access."
)
check 'the token encryption key is held neither in the application database nor in any backup set' k02_key_location

k02_rotation() {
  local r; r="$(trows <<< "$S_SECRETS" | grep -Ei '^\| *Google token encryption key *\|')"
  need "$(cell "$r" 6)" '\bevery stored refresh token undecryptable\b[^|]*\brelinks\b' 'the Rotation cell of the Google token encryption key' || return 1
  need_sent "$(flat <<< "$S_TOKEN")" 'Token storage' '\bcannot be decrypted with the key in use\b' '\baccess lost\b' '\brelinks\b' || return 1
}
check 'a key rotation makes every stored link unusable and every linked rep relinks' k02_rotation

# Fix round 1 (R-09): a token the key in use cannot decrypt is kept, not deleted, until relink or a
# corrected key value; it is not one of the events that delete a token.
K02_UNDECRYPTABLE_EXCUSED=(
  "- A token that cannot be decrypted with the key in use (after a key replacement, after a restore from a set taken before the last key replacement, or with a wrong key value) is not deleted: the link state becomes \"access lost\" and the owner relinks, which replaces the token."
)
k02_undecryptable_kept() {
  local b; b="$(flat <<< "$(bullet "$S_TOKEN" '^- A token that cannot be decrypted')")"
  [ -n "$b" ] || { WHY="no top-level 'A token that cannot be decrypted' item in Token storage"; return 1; }
  need_sent "$b" 'Token storage' '^- A token that cannot be decrypted with the key in use\b' '\bis not deleted: the link state becomes "access lost"' '\bwhich replaces the token\.$' || return 1
  need_sent "$b" 'Token storage' '^When the key value is corrected and the token decrypts again, the link works again\b' || return 1
  need_sent "$(flat <<< "$S_SECRETS")" 'Secrets' '\bcannot be decrypted\b' '\bthe token kept until the owner relinks\.$' || return 1
  # The deletion list names no undecryptable token, and no sentence deletes one.
  local d; d="$(flat <<< "$(bullet "$S_TOKEN" 'When a stored token is deleted')")"
  forbid "$d" '\b(decrypt|undecryptable|key)\b' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K02_UNDECRYPTABLE_EXCUSED[@]}")"
  forbid "$all" '\b(cannot be decrypted|undecryptable|does not decrypt)\b[^.]*\b(is|are|gets?) (then )?(deleted|removed|erased|dropped)\b|\b(delet(e|es|ed)|remov(e|es|ed))\b[^.]*\b(undecryptable|cannot be decrypted)\b' || return 1
}
check 'a token the key in use cannot decrypt is kept, not deleted, and works again when the key value is corrected' k02_undecryptable_kept

# Fix round 1 (B-01): on suspected compromise the grants are revoked first, the client secret is
# rotated with the key, and every client-secret rotation deletes the old secret in the project.
k02_compromise_rotation() {
  local rk rs
  rk="$(cell "$(trows <<< "$S_SECRETS" | grep -Ei '^\| *Google token encryption key *\|')" 6)"
  rs="$(cell "$(trows <<< "$S_SECRETS" | grep -Ei '^\| *Google OAuth client secret *\|')" 6)"
  need "$rk" '\bon suspected compromise, every grant whose token is on record is first revoked at Google while the key in use still decrypts it\b' 'the Rotation cell of the Google token encryption key' || return 1
  need "$rk" '\band the Google OAuth client secret is rotated with it\b' 'the Rotation cell of the Google token encryption key' || return 1
  need "$rs" '\bevery rotation ends by deleting the old secret in the Google Cloud project\b' 'the Rotation cell of the Google OAuth client secret' || return 1
  need "$rs" '\bwhenever the Google token encryption key is replaced on suspected compromise\b' 'the Rotation cell of the Google OAuth client secret' || return 1
  forbid "$rs" '\b(keeps?|kept|leaves?|left)\b[^|;]*\bold secret\b|\bold secret\b[^|;]*\b(stays|remains|is kept|is left)\b' || return 1
}
check 'a key replacement on suspected compromise first revokes every grant on record and rotates the client secret, and every client-secret rotation deletes the old secret' k02_compromise_rotation

k02_token_deleted() {
  local b; b="$(flat <<< "$(bullet "$S_TOKEN" 'When a stored token is deleted')")"
  need_sent "$b" 'When a stored token is deleted' '^- When a stored token is deleted\.' || return 1
  need_sent "$b" 'When a stored token is deleted' '^- at unlink by the owner\b' '\brevokes the token at Google\b' || return 1
  # Fix round 1: the token is deleted only once Google confirms or calls the grant invalid, the
  # link is never used after unlink, and a failed revocation is retried.
  need_sent "$b" 'When a stored token is deleted' '^- at unlink by the owner\b' '\bdeletes it once Google confirms the revocation or answers that the grant is no longer valid\b' '\bfrom the unlink on the link is never used\b' '\ba revocation request that fails is retried\b' || return 1
  need_sent "$b" 'When a stored token is deleted' '\bwhen Google refuses a refresh\b' '\bexpired or was revoked\b' || return 1
}
check 'the events that delete a stored token are stated: unlink, and a refresh Google refuses' k02_token_deleted

k02_deactivated() {
  need_sent "$(flat <<< "$(bullet "$S_TOKEN" 'Deactivated staff')")" 'Deactivated staff' "\\bdeactivated staff member.s link is (not )?deleted\\b"
}
check "the ADR states whether a deactivated staff member's link is deleted" k02_deactivated

k02_secrets() {
  local base_head head r name c i bad
  base_head="$(at "$TASK_BASE" "$ADR4" | grep -E '^\| Secret \|' | head -n 1 | tr -d '`*')"
  head="$(theads <<< "$S_SECRETS" | head -n 1)"
  [ -n "$base_head" ] || { WHY="no secret table header in $ADR4 at $TASK_BASE"; return 1; }
  [ "$head" = "$base_head" ] || { WHY="the Secrets table's columns are not ADR-0004's: '$head'"; return 1; }
  for name in 'Google OAuth client secret' 'Google token encryption key'; do
    r="$(trows <<< "$S_SECRETS" | grep -E "^\| *$name *\|")"
    [ "$(grep -c . <<< "$r")" -eq 1 ] || { WHY="expected one Secrets row for '$name'"; return 1; }
    [ "$(ncells "$r")" -eq 6 ] || { WHY="'$name' row has $(ncells "$r") cells"; return 1; }
    for i in 2 3 4 5 6; do
      c="$(cell "$r" "$i")"
      [ -n "$c" ] && [ "$c" != "—" ] && [ "$c" != "-" ] || { WHY="'$name': column $i ($(cell "$head" "$i")) is empty"; return 1; }
    done
    for i in 3 4; do
      c="$(cell "$r" "$i")"
      bad="$(grep -Eio '\b(repositor(y|ies)|image|VITE_[A-Z_*]*|frontend|single-page|browser|build|database|backup)\b' <<< "$c" | head -n 1)"
      [ -z "$bad" ] || { WHY="'$name' is kept or delivered in '$bad' ($(cell "$head" "$i"))"; return 1; }
    done
  done
  need_sent "$(flat <<< "$S_SECRETS")" 'Secrets' '^Both secrets follow ADR-0004 \*?Secret handling\*? as a class\b' '\bnever in the repository, an image, a VITE_\* variable, the application database or a backup set\b' || return 1
  forbid "$DECISION_SENTS" '\b(client secret|encryption key)\b[^.;]*\b(in|into|to|through)\b[^.;]*\b(frontend|VITE_|single-page application|browser|repository|the image|backend image)\b' 'which never leave the backend' || return 1
}
check "both Google secrets have every column of ADR-0004's secret table and none is kept in the repository, an image, VITE_*, the database or a backup set" k02_secrets

# ==== K-03 ===================================================================================

k03_marker() {
  local b; b="$(flat <<< "$(bullet "$S_RECOG" 'The marker')")"
  need_sent "$b" 'The marker' "\\bAn event is the application.s own when its private extended properties carry this environment.s identifier and a visit identifier\\b" || return 1
  need_sent "$b" 'The marker' '\bprivate extended property cannot be set by hand\b' || return 1
}
check "the marker is named: private extended properties carrying the environment's and the visit's identifier" k03_marker

k03_unmarked() {
  need_sent "$(flat <<< "$S_RECOG")" 'Recognising' '^- An event without the marker is never imported, changed or deleted\b' '\bnever counts anywhere\b'
}
check 'an event without the marker is never imported, changed or deleted' k03_unmarked

k03_marked() {
  need_sent "$(flat <<< "$S_RECOG")" 'Recognising' '^- An event with the marker is synchronised\b' "\\bis that visit.s event\\b" '\bflow back\b'
}
check 'an event with the marker is synchronised' k03_marked

K03_TITLE_EXCUSED=(
  "- A hand-made event is not recognised."
  "An event made by hand in Google with the same title, location and description as an application event carries no marker and is not recognised; title and description are never used to recognise an event."
)
k03_handmade() {
  need_sent "$(flat <<< "$S_RECOG")" 'Recognising' '\bmade by hand in Google with the same title, location and description\b' '\bis not recognised\b' '\btitle and description are never used to recognise an event\b' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K03_TITLE_EXCUSED[@]}")"
  forbid "$all" '\b(recogni[sz](e|es|ed|ing)|identif(y|ies|ied)|match(es|ed)?|is the application.s own|are the application.s own)\b[^.;]*\b(title|summary|description|location|Wizyta:)\b' || return 1
  forbid "$all" '\b(title|summary)\b[^.;]*\b(starts?|begins?) with\b' || return 1
}
check 'a hand-made event with the same title, location and description is not recognised' k03_handmade

k03_primary() {
  need_sent "$(flat <<< "$S_RECOG")" 'Recognising' "^- Only each owner.s primary calendar is read and written \\(VIS-1\\)\\.$" || return 1
  need_sent "$(flat <<< "$S_RECOG")" 'Recognising' "^No other calendar of the owner is read\\.$" || return 1
  forbid "$DECISION_SENTS" "\\b(any|all|every|each|several) (of )?(the )?(owner.s|rep.s|their) calendars\\b|\\bevery calendar\\b|\\ball calendars\\b|\\bsecondary calendars?\\b[^.]*\\b(read|written|synchroni[sz]ed)\\b" || return 1
}
check "only each owner's primary calendar is read and written" k03_primary

k03_twins() {
  need_sent "$(flat <<< "$(bullet "$S_RECOG" 'Twins')")" 'Twins' "\\bnot that visit.s event\\b" '\bcreates no visit\b' || return 1
  need_sent "$(flat <<< "$(bullet "$S_RECOG" 'Twins')")" 'Twins' '\bcreate retried after a lost response produces no twin\b' || return 1
}
check "a twin carrying a known visit's marker is not that visit's event and creates no visit" k03_twins

# ==== K-04 ===================================================================================

k04_app_to_google() {
  local b; b="$(bullet "$S_CHANGE" '^- App to Google')"
  [ -n "$b" ] || { WHY="no 'App to Google' item in Change detection"; return 1; }
  local f; f="$(flat <<< "$b")"
  need_sent "$f" 'App to Google' '^- App to Google: no later than about 1 minute\.$' || return 1
  figs_all_eq "$f" '(^- App to Google: no later than|visible in Google no later than)( about)?' 1 'the App-to-Google bound' || return 1
  need_sent "$f" 'App to Google' '\bwrites its job in the same database transaction\b' || return 1
  need_sent "$f" 'App to Google' '\bvisible in Google no later than about 1 minute after it was saved\b' || return 1
}
check 'App to Google: a change is visible in Google no later than about 1 minute, through the job queued with it' k04_app_to_google

k04_google_to_app() {
  local b; b="$(bullet "$S_CHANGE" '^- Google to app')"
  [ -n "$b" ] || { WHY="no 'Google to app' item in Change detection"; return 1; }
  local f; f="$(flat <<< "$b")"
  need_sent "$f" 'Google to app' '^- Google to app: no later than 5 minutes, or when a page is opened\.$' || return 1
  figs_all_eq "$f" '(^- Google to app: no later than|visible in the application no later than)( about)?' 5 'the Google-to-app bound' || return 1
  need_sent "$f" 'Google to app' '^- Polling\.' || return 1
  need_sent "$f" 'Google to app' '\bthe worker reads the primary calendar at least every\b' || return 1
  local p; p="$(figs "$(sent_with "$f" '\breads the primary calendar at least every\b')" '\bat least every')"
  [ -n "$p" ] && awk -v p="$p" 'BEGIN { exit !(p < 5) }' || { WHY="the polling interval ($p minutes) does not fit the 5-minute bound"; return 1; }
  need_sent "$f" 'Google to app' '\bA Google change is therefore visible in the application no later than 5 minutes\b' || return 1
}
check 'Google to app: a change is visible in the application no later than 5 minutes, through polling' k04_google_to_app

k04_page_open() {
  local f; f="$(flat <<< "$(bullet "$S_CHANGE" '^- Google to app')")"
  need_sent "$f" 'Google to app' '^- When a page is opened\.' || return 1
  need_sent "$f" 'Google to app' "\\bOpening a page of the application asks the backend to read the owner.s own calendar at once\\b" || return 1
}
check 'Google to app: opening a page reads the owner calendar at once' k04_page_open

k04_unavailable() {
  local f; f="$(flat <<< "$(bullet "$S_CHANGE" '^- Google to app')")"
  need_sent "$f" 'Google to app' '^- When polling is unavailable\b' '\b5-minute bound is not met\b' || return 1
  need_sent "$f" 'Google to app' '\bno visit state changes\b' || return 1
  need_sent "$f" 'Google to app' '\bfailed or refused read never counts as a deletion\b' || return 1
}
check 'when polling is unavailable the bound is stated as not met, no visit state changes and no failed read counts as a deletion' k04_unavailable

k04_instant() {
  local s; s="$(flat <<< "$S_CONFLICT")"
  need_sent "$s" 'Conflict rule' '\bthe later change wins\b' || return 1
  need_sent "$s" 'Conflict rule' '^Each change is compared by an instant\b' "\\bthe application.s change by the instant of its commit\\b" "\\bGoogle.s change by the event.s updated instant\\b" || return 1
  need_sent "$s" 'Conflict rule' '\bcompared as instants\b' '\btime zone\b' '\bdaylight-saving\b' || return 1
}
check "VIS-5: each side's change is compared by an instant, the later wins" k04_instant

k04_tie() {
  need_sent "$(flat <<< "$S_CONFLICT")" 'Conflict rule' '^- Tie rule\.' || return 1
  need_sent "$(flat <<< "$S_CONFLICT")" 'Conflict rule' "^When the two instants are equal, the (application|Google).s change wins\\b" || return 1
}
check 'VIS-5 has a tie rule for equal instants' k04_tie

K04_DELETION_EXCUSED=(
  "- A deletion in Google always puts the visit into Awaiting decision (VIS-11), whatever the instants: a later application change does not undo it."
  "An application change made after the deletion stays on the visit, and rescheduling from the prompt creates the event with it."
)
k04_deletion_wins() {
  # Fix round 1 (R-07 (1)): the sentence is anchored whole, so a tail that limits it fails.
  need_sent "$(flat <<< "$S_CONFLICT")" 'Conflict rule' '^- A deletion in Google always puts the visit into Awaiting decision \(VIS-11\), whatever the instants: a later application change does not undo it\.$' || return 1
  need_sent "$(flat <<< "$S_CONFLICT")" 'Conflict rule' '^An application change made after the deletion stays on the visit, and rescheduling from the prompt creates the event with it\.$' || return 1
  need_sent "$(flat <<< "$S_CONFLICT")" 'Conflict rule' '\bdeletion or cancellation in the application\b' '\bis final against a Google change\b' || return 1
  # No other sentence lets an application change re-create, restore or undo a Google deletion.
  local all; all="$(without "$DECISION_SENTS" "${K04_DELETION_EXCUSED[@]}")"
  forbid "$all" '\b(later|subsequent|newer|next) (application|app) change\b[^.]*\b(re-?creates?|restores?|undoes|undo|overrides?|wins|revives?|brings? back)\b|\bdeletion in Google\b[^.]*\buntil\b[^.]*\b(application|app) change\b|\b(application|app) change\b[^.]*\b(re-?creates?|restores?|undoes|revives?)\b[^.]*\bdeleted\b' || return 1
}
check 'a deletion on either side wins over a later change of the other' k04_deletion_wins

# Fix round 1 (R-03): every update job reads before it writes, a later Google change wins, the
# write is conditional on the etag it read, and suspended jobs run only after a first read.
k04_read_before_write() {
  local b; b="$(flat <<< "$(bullet "$S_CONFLICT" '^- Read before write[.]')")"
  [ -n "$b" ] || { WHY="no 'Read before write' item in Conflict rule"; return 1; }
  need_sent "$b" 'Read before write' '^- Read before write\.$' || return 1
  need_sent "$b" 'Read before write' '^Every update job first reads the visit.s event by its identifier\b' '\bapplies this rule to what it reads before it writes\b' || return 1
  need_sent "$b" 'Read before write' '\blater than the application.s change, the Google date, time and duration win and are applied to the visit\b' '\bthe job writes only the values Google does not own\b' || return 1
  need_sent "$b" 'Read before write' '^Otherwise the job writes, conditional on the event version it read \(the event.s etag\); a write Google refuses because the event changed since that read goes back to the read\.$' || return 1
  need_sent "$b" 'Read before write' '^Jobs suspended while access was lost run only after a first read of the owner.s calendar at the link or relink\b' || return 1
  need_sent "$(flat <<< "$S_RETRY")" 'Retry' "^Before they run, the worker reads the owner.s calendar once as polling does\\b" '\bcompared under \*?Conflict rule\b' || return 1
  need_sent "$(flat <<< "$S_EVENT")" 'What is read back' '\bid, status, start, end, updated, etag and the private extended properties\b' || return 1
  forbid "$DECISION_SENTS" '\b(writes?|updates?|sent|sends?)\b[^.]*\b(without|before) (first )?reading\b|\bunconditional(ly)?\b[^.]*\b(write|update)\b|\b(write|update)\b[^.]*\bunconditional(ly)?\b' || return 1
}
check 'every update job reads the event before it writes, a later Google change wins, and the write is conditional on the etag it read' k04_read_before_write

# Fix round 1 (R-01): every create other than a retry of the same create chooses a new identifier.
k04_new_identifier() {
  local b; b="$(flat <<< "$(bullet "$S_RETRY" '^- A new create uses a new identifier[.]')")"
  [ -n "$b" ] || { WHY="no 'A new create uses a new identifier' item in Retry"; return 1; }
  need_sent "$b" 'A new create uses a new identifier' '^- A new create uses a new identifier\.$' || return 1
  need_sent "$b" 'A new create uses a new identifier' '^Every create other than a retry of the same create\b' '\brescheduling after a deletion in Google\b' '\breassignment to a new owner\b' '\bconfirmed relink\b' '\bany later create for the same visit\b' '\bchooses a new event identifier\b' '\bnever meets an identifier Google already holds\b' || return 1
  local idv; idv="$(cell "$(trows <<< "$S_EVENT" | grep -E '^\| *id *\|')" 2)"
  need "$idv" '\bchooses for each create before its first attempt\b' 'the id field' || return 1
  need "$idv" '\bthe environment identifier and a random value new to that create, and kept across that create.s retries$' 'the id field' || return 1
  need_sent "$(flat <<< "$S_CHANGE")" 'Reassignment' '\bcreated in the new owner.s with a new event identifier\b' || return 1
  forbid "$DECISION_SENTS" '\breus(e|es|ed|ing)\b[^.]*\b(event )?identifier\b|\b(same|previous|old|earlier) event identifier\b[^.]*\b(re-?creat|later create|new calendar|new owner)' 'Visit identifiers are never reused' || return 1
}
check 'every create other than a retry of the same create chooses a new event identifier' k04_new_identifier

# Fix round 1 (R-04): answers that show a retry cannot succeed end the job, and an ended job never
# holds back later jobs.
k04_answers_end() {
  local b; b="$(flat <<< "$(bullet "$S_RETRY" '^- Answers that end a job[.]')")"
  [ -n "$b" ] || { WHY="no 'Answers that end a job' item in Retry"; return 1; }
  need_sent "$b" 'Answers that end a job' '^- Answers that end a job\.$' || return 1
  need_sent "$b" 'Answers that end a job' '^A job is not retried when Google.s answer shows that a retry cannot succeed\.$' || return 1
  need_sent "$b" 'Answers that end a job' '^An update answered that the event is deleted or absent ends, and the event is read directly by its identifier as polling does\b' '\bVIS-11\b' || return 1
  need_sent "$b" 'Answers that end a job' '^A deletion answered that the event is already deleted or absent is done\b' || return 1
  need_sent "$b" 'Answers that end a job' '^Any other refusal of the request itself\b' '\bends the job; the visit stays flagged Unsynchronised\b' || return 1
  need_sent "$b" 'Answers that end a job' '^An ended job never holds back the later jobs of its visit\.$' || return 1
  forbid "$b" '\b(refusal|refused|rejected|not found|gone|absent)\b[^.;]*\b(is|are) retried\b|\bretried (indefinitely|forever|until (it|they) succeeds?)\b' || return 1
  local all; all="$(without "$DECISION_SENTS" 'An ended job never holds back the later jobs of its visit.')"
  forbid "$all" '\bended job\b[^.]*\b(holds?|blocks?|stops?) (back )?(the )?later jobs\b|\blater jobs\b[^.]*\bwait\b[^.]*\bended job\b' || return 1
}
check 'answers that show a retry cannot succeed end the job, and an ended job never holds back the later jobs of its visit' k04_answers_end

k04_retry() {
  local s; s="$(flat <<< "$S_RETRY")"
  need_sent "$s" 'Retry' '^- Trigger\.' || return 1
  need_sent "$s" 'Retry' '\bflagged Unsynchronised when its change cannot be carried to Google\b' || return 1
  need_sent "$s" 'Retry' '^- Cadence\.' || return 1
  local c; c="$(sent_with "$s" '^- Cadence\.|\bretried after\b')"
  figs_all_eq "$(grep -Ei 'retried after' <<< "$c")" '\bretried after' 0.5 'the first retry wait' || return 1
  need_sent "$s" 'Retry' '\bup to 15 minutes\b' '\bthen every 15 minutes\b' || return 1
}
check 'retry of an Unsynchronised visit has its trigger and its cadence' k04_retry

K04_DISCARD_EXCUSED=(
  "- While access is lost or the owner has no link (expired, revoked, unlinked, never linked, or held unused after a relink), the owner's jobs are suspended, never discarded; no visit state changes and no prompt is raised (VIS-8, PRH-3)."
)
k04_suspended() {
  local s; s="$(flat <<< "$S_RETRY")"
  need_sent "$s" 'Retry' '^- While access is lost\b' "\\bthe owner.s jobs are suspended, never discarded\\b" '\bno visit state changes\b' '\bVIS-8\b' || return 1
  need_sent "$s" 'Retry' '^They run in order once the owner links or relinks\b' || return 1
  local all; all="$(without "$DECISION_SENTS" "${K04_DISCARD_EXCUSED[@]}")"
  forbid "$all" '\b(discard(s|ed|ing)?|dropp(ed|s)?|thrown away|lost for good|abandon(ed|s)?)\b[^.]*\b(changes?|jobs?|removals?|deletions?)\b|\b(changes?|jobs?|removals?|deletions?)\b[^.]*\b(are|is|get|gets) (discarded|dropped|abandoned)\b' || return 1
}
check "while access is lost the owner's jobs are suspended, never discarded, and run at relink with no visit state change" k04_suspended

k04_no_second() {
  local s; s="$(flat <<< "$S_RETRY")"
  need_sent "$s" 'Retry' '^- No second event\.' || return 1
  need_sent "$s" 'Retry' '\bretried create uses the event identifier fixed before the first attempt\b' || return 1
  need_sent "$s" 'Retry' '^A retried create therefore produces no second event\.$' || return 1
}
check 'a retried create produces no second event' k04_no_second

WORKER_ADDED=""
has "$(flat <<< "$S_BG")" '\bruns in one worker service\b' && WORKER_ADDED=1
k04_mechanism() {
  local s; s="$(flat <<< "$S_BG")"
  need_sent "$s" 'Background work' '^- Mechanism\.' || return 1
  need_sent "$s" 'Background work' '\bBackground work runs in one worker service started from the backend image\b' || return 1
  need_sent "$s" 'Background work' '\bjob queue held in the application database\b' || return 1
  need_sent "$s" 'Background work' '^No message broker and no other image is added\.$' || return 1
}
check 'the background-work mechanism is named: one worker service from the backend image, a queue in PostgreSQL' k04_mechanism

K04_ALEMBIC_EXCUSED=(
  "The worker never runs alembic upgrade head, neither at start nor at any other time; it starts only after migrate has exited with success, as backend does; and at start it reads the database's Alembic revision and exits without working when that revision is not its code's head or a revision descending from it, so it never works on a schema older than its code (ADR-0004, *Migrations*)."
)
k04_worker_migrations() {
  local s; s="$(flat <<< "$S_BG")"
  need_sent "$s" 'Background work' '^The worker never runs alembic upgrade head, neither at start nor at any other time\b' || return 1
  need_sent "$s" 'Background work' '\bit starts only after migrate has exited with success\b' || return 1
  need_sent "$s" 'Background work' '\bexits without working when that revision is not its code.s head or a revision descending from it\b' || return 1
}
check 'the worker never runs alembic upgrade head, starts only after migrate succeeds and refuses an older schema' k04_worker_migrations

# The addendum under ADR-0004's "## Addenda": the text appended after the task base's file.
ADR4_BASE="$(at "$TASK_BASE" "$ADR4")"
ADR4_HEAD="$(content "$ADR4")"
ADR4_PREFIX=""; ADR4_APPENDED=""
if [ "${ADR4_HEAD:0:${#ADR4_BASE}}" = "$ADR4_BASE" ]; then ADR4_PREFIX=1; ADR4_APPENDED="${ADR4_HEAD:${#ADR4_BASE}}"; fi
ADDENDUM=""
has "$ADR4_APPENDED" '^- \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}:\*\* ADR-0006 \(EKO-1-05, #18\) adds the `worker` service\b' && ADDENDUM=1
k04_addendum() {
  if [ -n "$WORKER_ADDED" ]; then
    [ -n "$ADDENDUM" ] || { WHY="ADR-0006 adds a worker service, and ADR-0004 has no dated addendum recording it"; return 1; }
    local a; a="$(flat <<< "$ADR4_APPENDED")"
    need_sent "$a" 'ADR-0004 addendum' '\bImage: the backend image\b' || return 1
    need_sent "$a" 'ADR-0004 addendum' '\bnever runs alembic upgrade head\b' '\bdepends on migrate with condition service_completed_successfully\b' || return 1
    need_sent "$(flat <<< "$S_BG")" 'Background work' "\\bIt is recorded in ADR-0004.s addendum of [0-9]{4}-[0-9]{2}-[0-9]{2}\\." || return 1
  else
    [ -z "$ADDENDUM" ] || { WHY="ADR-0004 carries a worker addendum, and ADR-0006 adds no worker service"; return 1; }
  fi
}
check 'a worker service in ADR-0006 is recorded by a dated ADR-0004 addendum, and only then' k04_addendum

# ==== K-05 ===================================================================================

# The field table of "Event content": Google field | Value | Category | Why the sync needs it.
FIELD_TAB="$(awk '/^[[:space:]]*\| *Google field *\| *Value *\| *Category/ { on = 1 } on && !/^[[:space:]]*\|/ { exit } on' <<< "$S_EVENT")"
FIELD_ROWS="$(trows <<< "$FIELD_TAB")"
frow() { grep -E "^\| *$1 *\|" <<< "$FIELD_ROWS"; }
FIELDS_OK='^(summary|location|description|start, end|start|end|id|extendedProperties\.private|visibility)$'
# The one clause of a Value cell that names a forbidden value to say it is NOT sent (the
# Architect's hazard note, 07-architect-2.md): excused by its exact text, nothing else.
DESC_EXCUSE='if no contact is marked primary, or the primary contact is an e-mail address, the description is empty and no phone is sent'
LOC_EXCUSE='never the voivodeship or county'
FORBIDDEN_VALUE='\be-?mails?\b|\bNIP\b|\btax identifier\b|\bnotes?\b|\baction\b|\bstate\b|\bflags?\b|\battendees?\b|\borgani[sz]er\b|\bguests?\b|\b(every|each|all|any|other|second) (contact )?phones?\b|\bphones? (numbers )?(of|from) (every|all)\b|\bowner\b|\barchived\b|\bcomment\b'
k05_closed_list() {
  local r f v c w n=0
  [ -n "$FIELD_ROWS" ] || { WHY="no Google field | Value | Category | Why table in Event content"; return 1; }
  [ "$(theads <<< "$FIELD_TAB" | head -n 1)" = '| Google field | Value | Category (ADR-0005) | Why the sync needs it |' ] || { WHY="the field table's header changed"; return 1; }
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    n=$((n + 1))
    [ "$(ncells "$r")" -eq 4 ] || { WHY="field row with $(ncells "$r") cells: $r"; return 1; }
    f="$(cell "$r" 1)"; v="$(cell "$r" 2)"; c="$(cell "$r" 3)"; w="$(cell "$r" 4)"
    grep -Eq "$FIELDS_OK" <<< "$f" || { WHY="field '$f' is outside the decided set of event fields"; return 1; }
    [ -n "$v" ] && [ "$v" != "—" ] || { WHY="field '$f' has no value"; return 1; }
    grep -Eq '^(PD-C[0-9]+|not personal data\b.*)$' <<< "$c" || { WHY="field '$f' has no ADR-0005 category ('$c')"; return 1; }
    if grep -Eq '^PD-' <<< "$c"; then grep -Fxq "$c" <<< "$CAT_IDS" || { WHY="field '$f': $c is not an ADR-0005 category"; return 1; }; fi
    [ "$(wc -w <<< "$w")" -ge 2 ] || { WHY="field '$f' has no reason the sync needs it ('$w')"; return 1; }
  done <<< "$FIELD_ROWS"
  [ "$(cut -d'|' -f2 <<< "$FIELD_ROWS" | sort | uniq -d | grep -c .)" -eq 0 ] || { WHY="a field is listed twice"; return 1; }
  need_sent "$(flat <<< "$S_EVENT")" 'Event content' '\bholds exactly these fields, and no other field is set\b' || return 1
}
check 'the event fields form a closed table, each field with its value, its ADR-0005 category and why the sync needs it' k05_closed_list

# The Event content sentences that name a forbidden value to say it is NOT sent or NOT read back.
K05_PROSE_EXCUSED=(
  "- No attendee is ever set, and no notification or invitation is sent."
  "Every insert, update and delete is sent with notifications to guests switched off (sendUpdates none)."
  "The customer is never an attendee (VIS-3, PRH-1)."
  "- Never sent: an e-mail address, the NIP, the foreign tax identifier, the note on a phone or an e-mail, note text, an action, the visit's state or flags, any other phone, and any other customer value (ADR-0005)."
  "The application never reads back summary, location, description, attendees, or the creator's or organiser's e-mail address."
)
k05_no_forbidden() {
  local r f v
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    f="$(cell "$r" 1)"; v="$(cell "$r" 2)"
    v="${v//"$DESC_EXCUSE"/EXCUSED}"; v="${v//"$LOC_EXCUSE"/EXCUSED}"
    if has "$v" "$FORBIDDEN_VALUE"; then WHY="field '$f' sends '$(grep -Eio -- "$FORBIDDEN_VALUE" <<< "$v" | head -n 1)': $v"; return 1; fi
    if has "$v" '\b(NIP|tax|e-?mail)\b'; then WHY="field '$f' sends a forbidden value: $v"; return 1; fi
  done <<< "$FIELD_ROWS"
  # Fix round 1 (R-07 (2)): the prose of Event content, outside the table, adds no forbidden value
  # either; only the sentences that say what is NOT sent are excused, by their exact text.
  local prose; prose="$(without "$(flat <<< "$S_EVENT" | grep -v '^|')" "${K05_PROSE_EXCUSED[@]}")"
  forbid "$prose" "$FORBIDDEN_VALUE" || return 1
  forbid "$prose" '\b(NIP|tax|e-?mail)\b' || return 1
  # Nowhere in the Decision is a customer value added to an event, as a guest or in any field.
  local all; all="$(without "$DECISION_SENTS" "${K05_PROSE_EXCUSED[@]}")"
  forbid "$all" "\b(customer.s|their) (e-?mail( address)?|NIP|tax identifier|notes?|note text|actions?|other phones?)\b[^.]*\b(is|are) (also )?(added|sent|set|written|included|copied|put)\b|\b(add|adds|added|send|sends|write|writes|include|includes|copy|copies|put|puts)\b[^.]*\b(customer.s )?(e-?mail( address)?|NIP|tax identifier|note text)\b[^.]*\b(event|Google|calendar|description|summary|location|guest|attendee)\b" || return 1
  # Identifiers: derived only from the visit's opaque record identifier and the environment.
  local id; id="$(cell "$(frow id)" 2)"
  need "$id" "\\bderived from the visit.s opaque record identifier\\b" 'the id field' || return 1
  need "$(cell "$(frow 'extendedProperties\.private')" 2)" "^the marker: the environment identifier and the visit.s opaque record identifier$" 'the marker field' || return 1
}
check 'no event field sends an e-mail, NIP, tax identifier, note, action, state, flag, attendee or other phone' k05_no_forbidden

k05_vis3() {
  local v
  v="$(cell "$(frow summary)" 2)"; need "$v" '<customer name>' 'the summary field' || return 1
  v="$(cell "$(frow location)" 2)"
  need "$v" "\\bthe visit.s own address if given, else the customer.s address\\b" 'the location field' || return 1
  need "$v" '\bstreet and number, postal code, post office or town, country\b' 'the location field' || return 1
  v="$(cell "$(frow description)" 2)"
  need "$v" "^one contact phone number, alone: the customer.s phone marked primary;" 'the description field' || return 1
  v="$(cell "$(frow 'start, end')" 2)"
  need "$v" "\\bthe visit.s start and end\\b" 'the start, end field' || return 1
  need "$v" '\btimeZone Europe/Warsaw\b' 'the start, end field' || return 1
}
check "the field list covers VIS-3: the customer's name, the address with its parts, one contact phone by the primary rule, start and end in Europe/Warsaw" k05_vis3

k05_no_attendee() {
  local s; s="$(flat <<< "$S_EVENT")"
  need_sent "$s" 'Event content' '^- No attendee is ever set, and no notification or invitation is sent\.$' || return 1
  need_sent "$s" 'Event content' '\bsendUpdates none\b' || return 1
  need_sent "$s" 'Event content' '^The customer is never an attendee \(VIS-3, PRH-1\)\.$' || return 1
  # Fix round 1 (R-07 (2)): the positive sentences alone pass a list that also adds a guest. No
  # other Decision sentence names a guest, attendee, invitation or organiser.
  # The two assumption rows (A-10, A-11) name attendees and the organiser to state what Google does.
  local rows_ok=(
    "| A-10 | Partial-response field selection limits the fields Google returns, the creator's and organiser's e-mail address included | Google APIs' standard fields parameter | *What is read back* |"
    "| A-11 | With no attendee and sendUpdates none, Google sends no invitation or notification to anyone | Calendar API events.insert/update/delete reference | *Event content* |"
  )
  local all; all="$(without "$DECISION_SENTS" "${K05_PROSE_EXCUSED[@]}" "${rows_ok[@]}")"
  forbid "$all" '\b(guests?|attendees?|invit(e|es|ed|ing|ation|ations)|organi[sz]ers?|participants?)\b' || return 1
}
check 'no attendee is set and no notification or invitation is sent' k05_no_attendee

k05_no_address() {
  need_sent "$(flat <<< "$S_EVENT")" 'Event content' '^- A customer with no address and a visit with no address give an event with no location\.$'
}
check 'a customer and a visit with no address give an event with no location' k05_no_address

# ==== K-06 ===================================================================================

k06_past() {
  local b; b="$(flat <<< "$(bullet "$S_ERASE" 'What erasure does in Google')")"
  need_sent "$b" 'Erasure' '^Erasing a customer \(ADR-0005, \*?Erasure\*?\) deletes from Google every application event of every visit of that customer, past and future events alike\b' || return 1
  need_sent "$b" 'Erasure' '^CUS-9 archiving removes only future events; erasure removes the past ones too\.$' || return 1
}
check "erasure deletes the customer's events from Google, past ones named explicitly, not only CUS-9's future ones" k06_past

k06_every_owner() {
  local b; b="$(flat <<< "$(bullet "$S_ERASE" 'What erasure does in Google')")"
  need_sent "$b" 'Erasure' '\bin the calendar of every owner the event was created in\b' "\\bthe original owner.s for past visits kept under CUS-10\\b" || return 1
  need_sent "$b" 'Erasure' '\bkeeps, for each event it created, the owner in whose calendar the event lives\b' || return 1
  forbid "$(flat <<< "$S_ERASE")" "\\bonly\\b[^.]*\\bcurrent owner.s calendar\\b|\\bcurrent owner.s calendar only\\b" || return 1
}
check "erasure reaches the events in every owner's calendar, the original owner's for past visits included" k06_every_owner

k06_inflight() {
  need_sent "$(flat <<< "$S_ERASE")" 'Erasure' '^- In-flight sync\.' || return 1
  need_sent "$(flat <<< "$S_ERASE")" 'Erasure' "\\bjob of the erased customer.s visit that is queued or running when the erasure commits sends none of the customer.s data afterwards\\b" || return 1
  # Fix round 1 (R-07 (4)): the half R-02 depends on, a request already sent, is anchored too.
  need_sent "$(flat <<< "$S_ERASE")" 'Erasure' "\\bit reads the stripped visit when it runs and sends nothing for it\\b" '\band a request already sent when the erasure commits is followed by the deletion job of that event, which runs after it\.$' || return 1
}
check "a sync of the erased customer's visit queued or running at erasure sends none of its data afterwards" k06_inflight

# Fix round 1 (R-02): an erasure's deletion job is ordered as a job of its visit, after every
# earlier job (a request already sent included); the event record is written before the first
# attempt; and "absent" after an unanswered create is read again before it counts as done.
k06_erasure_order() {
  local bg; bg="$(flat <<< "$S_BG")"
  need_sent "$bg" 'Background work' '^Jobs of one visit run one at a time, in the order they were queued\.$' || return 1
  need_sent "$bg" 'Background work' '^A deletion job queued by an erasure counts, for this order, as a job of the visit whose event it deletes, so it runs only after every earlier job of that visit has ended, a request already sent included\.$' || return 1
  local h; h="$(flat <<< "$(bullet "$S_ERASE" '^- How[.]')")"
  [ -n "$h" ] || { WHY="no 'How' item in Erasure and calendar events"; return 1; }
  need_sent "$h" 'Erasure, How' "^Each such job runs only after every earlier job of that event.s visit has ended\\b" || return 1
  need_sent "$h" 'Erasure, How' '\bexcept after a create of that identifier that Google never answered: then the job reads the event again at its next retry step\b' '\bdeletes it if it is there, and counts as done only when that read also finds it deleted or absent\.$' || return 1
  forbid "$DECISION_SENTS" '\b(erasure|deletion) jobs?\b[^.]*\b(runs?|is run|are run|starts?) (at once|immediately|first|ahead of|before)\b|\b(erasure|deletion) jobs?\b[^.]*\b(skips?|jumps?|bypass(es)?) the (queue|order)\b' || return 1
}
check "an erasure's deletion job runs as a job of its visit, after every earlier job, and absent after an unanswered create is read again" k06_erasure_order

k06_record_first() {
  local b; b="$(flat <<< "$(bullet "$S_BG" '^- The event record comes first[.]')")"
  [ -n "$b" ] || { WHY="no 'The event record comes first' item in Background work"; return 1; }
  need_sent "$b" 'The event record comes first' '^The record of an event \(its identifier and the owner in whose calendar it is created\) is written in the same transaction that queues its create, before the first attempt\b' '\bsent and never answered is still recorded, and erasure finds it\.$' || return 1
  forbid "$DECISION_SENTS" '\b(event )?record\b[^.]*\b(is|are) written\b[^.]*\b(after|once|when)\b[^.]*\b(Google (confirms|answers)|the create (succeeds|is confirmed))\b' || return 1
}
check 'the event record is written in the transaction that queues its create, before the first attempt, so erasure finds an unanswered create' k06_record_first

# Fix round 1 (R-06): a confirmed other account records every removal due for the earlier calendar
# as not carried out, never sends it to the new one, and leaves the data there to the GDPR impact
# assessment, not accepted.
k06_account_switch() {
  local b; b="$(flat <<< "$(bullet "$S_LOST" '^- When the owner confirms another account')")"
  [ -n "$b" ] || { WHY="no 'When the owner confirms another account' item in Lost access"; return 1; }
  need_sent "$b" 'Lost access' '^- When the owner confirms another account\b' '\bno longer tracked and never counts as deleted\b' '\bis recorded as not carried out and is never sent to the new calendar\.$' || return 1
  need_sent "$b" 'Lost access' "\\bthe customers. names, addresses and phones left in the earlier account are not settled by this decision: they are a question for the GDPR impact assessment\\b" || return 1
  need_sent "$(flat <<< "$S_ERASE")" 'Erasure' '^- The owner.s access lost\.' || return 1
  need_sent "$(flat <<< "$S_ERASE")" 'Erasure' '\bunless the owner confirms another account, when it is recorded as not carried out\b' || return 1
  forbid "$b" '\b(accept(s|ed)?|tolerat(e|es|ed)|acceptable|settled by this decision:? (it|they) (is|are) accepted)\b' || return 1
}
check 'a confirmed other account records the removals due there as not carried out and names the data left there for the GDPR impact assessment, not accepted' k06_account_switch

k06_reapply() {
  local b; b="$(flat <<< "$(bullet "$S_ERASE" 'The re-apply at restore')")"
  need_sent "$b" 'Re-apply' '^- The re-apply at restore\.' || return 1
  need_sent "$b" 'Re-apply' '^The re-apply queues the same deletion jobs for every event the restored database records\b' || return 1
  need_sent "$b" 'Re-apply' '^No sync of restored data runs before the re-apply: the worker starts only after it\.$' || return 1
}
check 'the re-apply at restore queues the same deletions, and no sync of restored data runs before it' k06_reapply

K06_REAPPLY_EXCUSED=(
  "No sync of restored data runs before the re-apply: the worker starts only after it."
  "ADR-0005's re-apply carries out each erasure again on the restored application database, after migrate at ADR-0004 restore step 12 and before backend and the worker start at step 13 (ADR-0005, *Re-apply at restore*)."
)
k06_no_sync_before() {
  local all; all="$(without "$DECISION_SENTS" "${K06_REAPPLY_EXCUSED[@]}")"
  forbid "$all" '\b(sync(hronisation|hronization)?|worker|jobs?|polling)\b[^.]*\b(starts?|runs?|begins?|resumes?|is started)\b[^.]*\bbefore\b[^.]*\bre-apply\b' || return 1
  forbid "$all" '\bre-apply\b[^.]*\bafter\b[^.]*\b(the )?(sync|worker|backend) (starts?|runs?|has started)\b' || return 1
}
check 'no Decision sentence lets a sync run before the ADR-0005 re-apply' k06_no_sync_before

k06_orphans() {
  local b; b="$(flat <<< "$(bullet "$S_ERASE" 'Events a restored database does not know')")"
  need_sent "$b" 'Orphans' '\bis an orphan\b' || return 1
  need_sent "$b" 'Orphans' '\beach orphan is deleted from Google\b' '\bno customer value\b' || return 1
}
check 'app-marked events a restored database does not know are deleted at the first read, and the owner told without customer values' k06_orphans

k06_lost_kinds() {
  local tab rows k r ev rm
  tab="$(awk '/^[[:space:]]*\| *Kind *\| *Events already in Google *\|/ { on = 1 } on && !/^[[:space:]]*\|/ { exit } on' <<< "$S_LOST")"
  rows="$(trows <<< "$tab")"
  [ -n "$rows" ] || { WHY="no Kind | Events already in Google | Removals table in Lost access"; return 1; }
  theads <<< "$tab" | grep -Eiq '\| *Removals due during the loss\b' || { WHY="the Lost access table has no 'Removals due during the loss' column"; return 1; }
  for k in Expired Revoked Unlinked; do
    r="$(grep -E "^\| *$k\b" <<< "$rows")"
    [ "$(grep -c . <<< "$r")" -eq 1 ] || { WHY="no Lost access row for '$k'"; return 1; }
    ev="$(cell "$r" 2)"; rm="$(cell "$r" 3)"
    [ -n "$ev" ] && [ "$ev" != "—" ] || { WHY="'$k': nothing said about the events already in Google"; return 1; }
    has "$rm" '\bcarried out at relink\b' || has "$rm" '\bnever carried out\b' || { WHY="'$k': no statement whether removals due during the loss are carried out at relink ('$rm')"; return 1; }
  done
  need_sent "$(flat <<< "$S_LOST")" 'Lost access' '^For each kind of loss, no visit state changes\b' '\bno event counts as deleted in Google\b' || return 1
}
check 'for each kind of lost access (expired, revoked, unlinked) the ADR says what happens to the events in Google and to removals due' k06_lost_kinds

k06_never_relinked() {
  local b; b="$(flat <<< "$(bullet "$S_LOST" 'When relink never comes')")"
  need_sent "$b" 'Lost access' '^- When relink never comes\b' "\\bkeep the customers. names, addresses and phones\\b" '\bremovals due there are never carried out\b' || return 1
  need_sent "$b" 'Lost access' '^This decision does not accept that residual: it is a question for the GDPR impact assessment\b' || return 1
  local all; all="$(without "$DECISION_SENTS" "$(sent_with "$b" '^This decision does not accept that residual')")"
  forbid "$all" '\b(accept(s|ed)?|tolerat(e|es|ed))\b[^.]*\bresidual\b|\bresidual\b[^.]*\b(is|are) (accepted|tolerated|acceptable)\b' || return 1
}
check 'a calendar never relinked is named as a residual for the GDPR impact assessment, not accepted' k06_never_relinked

# ==== K-07 ===================================================================================

# (1) Forwards. The lines K-07 lists (task base 4273cb3), "<file key> <first line>".
FORWARDS='ADR-0001 172
ADR-0001 185
ADR-0002 123
ADR-0002 136
ADR-0003 269
ADR-0003 318
ADR-0004 61
ADR-0004 200
ADR-0004 562
ADR-0004 585
ADR-0005 304
ADR-0005 375
ADR-0005 446
ADR-0005 523'
# Base lines naming ADR-0006 or EKO-1-05 that are not forwards: the ADR-0004-C1 control (a
# condition on the addendum) and ADR-0005's option rows that chose its own rule.
NOT_FORWARDS='ADR-0004 692
ADR-0005 589
ADR-0005 590'
adr_file() { case "$1" in ADR-0001) echo "$ADR1" ;; ADR-0002) echo "$ADR2" ;; ADR-0003) echo "$ADR3" ;; ADR-0004) echo "$ADR4" ;; ADR-0005) echo "$ADR5" ;; esac; }
FWD_ROWS="$(trows <<< "$(awk '/^[[:space:]]*\| *Source *\| *Line *\|/ { on = 1 } on && !/^[[:space:]]*\|/ { exit } on' <<< "$S_FWD")")"
DEC_HEADS="$(grep -E '^### ' <<< "$DECISION_TEXT" | sed -E 's/^### //')"
# fwd_row_for <src> <line> — the first forwards-table row whose Source is <src> and some "l.N" or
# "l.N-M" of whose Line cell contains the line.
fwd_row_for() {
  SRC="$1" LN="$2" awk -F'|' '
    function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
    { if (trim($2) != ENVIRON["SRC"]) next
      c = $3; x = ENVIRON["LN"] + 0
      while (match(c, /l\.[0-9]+(-[0-9]+)?/)) {
        r = substr(c, RSTART + 2, RLENGTH - 2); c = substr(c, RSTART + RLENGTH)
        n = split(r, ab, "-"); a = ab[1] + 0; b = (n > 1 ? ab[2] + 0 : a)
        if (x >= a && x <= b) { print; found = 1; exit }
      } }
    END { exit !found }' <<< "$FWD_ROWS"
}
k07_forwards() {
  local src ln r dec name ok
  [ -n "$FWD_ROWS" ] || { WHY="no Source | Line | What it forwards | Decided in table under Items forwarded"; return 1; }
  while read -r src ln; do
    [ -n "$src" ] || continue
    r="$(fwd_row_for "$src" "$ln")" || { WHY="no entry for $src l.$ln"; return 1; }
    [ "$(wc -w <<< "$(cell "$r" 3)")" -ge 2 ] || { WHY="$src l.$ln: what it forwards is not stated"; return 1; }
    dec="$(cell "$r" 4)"
    [ -n "$dec" ] || { WHY="$src l.$ln: no Decision section decides it"; return 1; }
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      [ "$name" = "this whole decision" ] && continue
      ok=""
      while IFS= read -r h; do [ "${h:0:${#name}}" = "$name" ] && ok=1; done <<< "$DEC_HEADS"
      [ -n "$ok" ] || { WHY="$src l.$ln: '$name' is not a section of the Decision"; return 1; }
    done < <(sed -E 's/\*([^*]+)\*/\n\1\n/g' <<< "$dec" | sed -E 's/^[;, ]+|[;, ]+$//g' | grep -Ev '^(and|;|,)?$')
  done <<< "$FORWARDS"
}
check 'every forward of ADR-0001..0005 to ADR-0006 or EKO-1-05 has an entry naming its source, line and the Decision section that decides it' k07_forwards

k07_forwards_complete() {
  local src f n
  for src in ADR-0001 ADR-0002 ADR-0003 ADR-0004 ADR-0005; do
    f="$(adr_file "$src")"
    while IFS= read -r n; do
      [ -n "$n" ] || continue
      grep -Fxq "$src $n" <<< "$NOT_FORWARDS" && continue
      fwd_row_for "$src" "$n" >/dev/null || { WHY="$src l.$n names ADR-0006 or EKO-1-05 and has no forwards entry: $(at "$TASK_BASE" "$f" | sed -n "${n}p" | cut -c1-120)"; return 1; }
    done < <(at "$TASK_BASE" "$f" | grep -nE 'ADR-0006|EKO-1-05' | cut -d: -f1)
  done
}
check 'every base line of ADR-0001..0005 naming ADR-0006 or EKO-1-05 is a listed forward or a known non-forward' k07_forwards_complete

DEV_SENT="$(grep -Ei '^(- )?The only deviation from an accepted decision is\b' <<< "$DECISION_SENTS")"
k07_change_sentence() {
  local c; c="$(flat <<< "$S_CHANGES")"
  need_sent "$c" 'Changes to accepted decisions' '^This decision changes no accepted decision: not ADR-0001, ADR-0002, ADR-0003, ADR-0004 or ADR-0005, by edit\.$' || return 1
  [ -n "$DEV_SENT" ] || need_sent "$c" 'Changes to accepted decisions' '^No deviation from an accepted decision is proposed\.$' || return 1
}
check 'the Decision says it changes no accepted decision and proposes no deviation' k07_change_sentence

K07_DEV_EXCUSED=(
  "No deviation from an accepted decision is proposed."
  "This decision changes no accepted decision: not ADR-0001, ADR-0002, ADR-0003, ADR-0004 or ADR-0005, by edit."
)
k07_no_deviation() {
  local all; all="$(without "$DECISION_SENTS" "${K07_DEV_EXCUSED[@]}")"
  [ -n "$DEV_SENT" ] && all="$(without "$all" "$DEV_SENT")"
  forbid "$all" '\bdeviat(e|es|ed|ing|ion|ions)\b' || return 1
  forbid "$all" '\b(replaces?|supersedes?|overrides?|amends?|changes|revokes?|redefines?)\b[^.;]*\bADR-000[1-5]\b|\bADR-000[1-5]\b[^.;]*\b(is|are) (replaced|superseded|overridden|amended|changed)\b' 'no other change is made to ADR-0004|does not change ADR-0002' || return 1
}
check 'no Decision sentence names a deviation or replaces a rule of ADR-0001..0005' k07_no_deviation

k07_gh_deviation() {
  command -v gh >/dev/null 2>&1 || { WHY="gh is not installed (use --offline to skip by name)"; return 1; }
  local labels
  labels="$(gh issue view "$ISSUE" --repo "$REPO_SLUG" --json labels -q '.labels[].name' 2>/dev/null)" || { WHY="gh could not read Issue #$ISSUE"; return 1; }
  if [ -z "$DEV_SENT" ]; then
    ! grep -Fxq 'adr-deviation' <<< "$labels" || { WHY="Issue #$ISSUE carries adr-deviation, but ADR-0006 names no deviation"; return 1; }
    return 0
  fi
  grep -Fxq 'adr-deviation' <<< "$labels" || { WHY="ADR-0006 names a deviation, but Issue #$ISSUE has no adr-deviation label"; return 1; }
}
if [ -n "$OFFLINE" ]; then skip "Issue #18 carries no adr-deviation label, or one ADR-0006 names" '--offline'
else check "Issue #18 carries no adr-deviation label, or one ADR-0006 names" k07_gh_deviation; fi

k07_no_migrate_other() {
  local all; all="$(without "$DECISION_SENTS" "${K04_ALEMBIC_EXCUSED[@]}")"
  forbid "$all" '\balembic upgrade\b|\b(runs?|applies|apply|performs?) (the )?migrations?\b|\bmigrates? the (schema|database)\b' || return 1
}
check 'no Decision sentence lets a worker or any process other than migrate run alembic upgrade head' k07_no_migrate_other

# --- accepted files and the change set ---

blob_now() {
  if [ -n "$HEAD_REF" ]; then git rev-parse --verify --quiet "$HEAD_REF:$1"
  else [ -f "$1" ] && git hash-object -- "$1"; fi
}
k07_adrs_identical() {
  local f a b
  for f in "$ADR1" "$ADR2" "$ADR3" "$ADR5"; do
    a="$(git rev-parse --verify --quiet "$TASK_BASE:$f")"; b="$(blob_now "$f")"
    [ -n "$b" ] || { WHY="$f is gone"; return 1; }
    [ "$a" = "$b" ] || { WHY="$f differs from $TASK_BASE (blob $b, base $a)"; return 1; }
  done
  local list; if [ -n "$HEAD_REF" ]; then list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/")"; else list="$(ls "$DECISIONS"/*.md | sort)"; fi
  local extra; extra="$(grep -E '/ADR-[0-9]{4}' <<< "$list" | grep -Ev '/ADR-000[1-6]-')"
  [ -z "$extra" ] || { WHY="another decision file: $(tr '\n' ' ' <<< "$extra")"; return 1; }
}
check 'ADR-0001, ADR-0002, ADR-0003 and ADR-0005 are byte-identical to the task base' k07_adrs_identical

k07_adr4_addenda() {
  [ -n "$ADR4_PREFIX" ] || { WHY="$ADR4 is changed above its end at $TASK_BASE (the text up to and under ## Addenda is not the base's)"; return 1; }
  [ "$(grep -E '^## ' <<< "$ADR4_BASE" | tail -n 1)" = "## Addenda" ] || { WHY="## Addenda is not the last section of $ADR4 at $TASK_BASE"; return 1; }
  forbid "$ADR4_APPENDED" '^#' || { WHY="the text appended to $ADR4 opens a heading: $WHY"; return 1; }
  if [ -n "$(grep -c . <<< "$ADR4_APPENDED" | grep -v '^0$')" ] && [ -z "$ADDENDUM" ]; then
    WHY="text appended to $ADR4 is not the worker addendum"; return 1
  fi
}
check 'ADR-0004 is byte-identical to the task base except for text appended under ## Addenda' k07_adr4_addenda

changed_files() {
  if [ -n "$HEAD_REF" ]; then git diff --name-only "$MB" "$HEAD_REF"
  else { git diff --name-only "$MB"; git ls-files --others --exclude-standard; } | sort -u; fi
}
CHANGED="$(changed_files)"

K07_SKIP=""
if [ -z "$BASE_GIVEN" ] && git cat-file -e "$BASE_REF:$ADR6" 2>/dev/null; then
  K07_SKIP="$ADR6 already exists at $BASE_REF (the task is merged); re-run with --base <merge>^1 --head <merge>^2"
fi
check07() { if [ -n "$K07_SKIP" ]; then skip "$1" "$K07_SKIP"; return 0; fi; check "$@"; }

ALLOWED_RE='^(docs/architecture/decisions/ADR-0006-[^/]*\.md|tests/doc-checks/EKO-1-05\.sh|docs/cost-register/.*|docs/architecture/decisions/ADR-0004-deployment-and-recovery\.md|docs/architecture/architecture-sensitive-paths\.md|docs/architecture/layer-dependencies\.md)$'
k07_only_allowed() {
  local extra; extra="$(grep . <<< "$CHANGED" | grep -Ev "$ALLOWED_RE")"
  [ -z "$extra" ] || { WHY="outside the allowed set: $(tr '\n' ' ' <<< "$extra")"; return 1; }
}
check07 'the change set touches only ADR-0006, its document checks, the ADR-0004 addendum, the two registers and cost bookkeeping' k07_only_allowed

k07_no_impl() {
  local bad; bad="$(grep -E '^(backend/|frontend/|identity/|\.github/)' <<< "$CHANGED")"
  [ -z "$bad" ] || { WHY="listed: $(tr '\n' ' ' <<< "$bad")"; return 1; }
}
check07 'the change set holds nothing under backend/, frontend/, identity/ or .github/' k07_no_impl

# reg_diff <base text> <head text> <allowed new row ERE or empty> — prints the first violation:
# a base line gone or changed other than in a cell holding "pending ADR-0006", a changed cell that
# still says "pending", or a new line other than one row matching the allowed ERE.
reg_diff() {
  B="$1" H="$2" NEWRE="$3" awk '
    function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
    BEGIN {
      nb = split(ENVIRON["B"], b, "\n"); nh = split(ENVIRON["H"], h, "\n"); re = ENVIRON["NEWRE"]
      for (i = 1; i <= nh; i++) hc[h[i]]++
      for (i = 1; i <= nb; i++) {
        if (b[i] !~ /pending ADR-0006/) {
          if (hc[b[i]] > 0) { hc[b[i]]--; used[b[i]]++; continue }
          print "base line gone or changed: " substr(b[i], 1, 160); exit 1
        }
        # a pending line: a head line not in base with equal cells except the pending ones
        nbc = split(b[i], bc, "|"); found = 0
        for (j = 1; j <= nh && !found; j++) {
          if (hc[h[j]] <= 0 || h[j] in taken) continue
          if (split(h[j], xc, "|") != nbc) continue
          ok = 1
          for (k = 1; k <= nbc; k++) {
            if (bc[k] ~ /pending ADR-0006/) { if (xc[k] ~ /pending/ || trim(xc[k]) == "") ok = 0 }
            else if (bc[k] != xc[k]) ok = 0
          }
          if (ok) { found = 1; taken[h[j]] = 1; hc[h[j]]-- }
        }
        if (!found) { print "row changed beyond its pending ADR-0006 cell: " substr(b[i], 1, 160); exit 1 }
      }
      extra = 0
      for (j = 1; j <= nh; j++) if (hc[h[j]] > 0) {
        hc[h[j]]--
        if (re != "" && h[j] ~ re && !extra) { extra = 1; continue }
        print "new line: " substr(h[j], 1, 160); exit 1
      }
    }'
}
REG_PATHS_HEAD="$(content "$PATHS")"
WORKER_MODULE="$(grep -Eo "Its entry point is the module [a-z/_]+\\.py" <<< "$(flat <<< "$S_BG")" | awk '{ print $NF }')"
k07_registers() {
  local v re
  re=""
  [ -n "$WORKER_MODULE" ] && re="^\\| \`${WORKER_MODULE//./\\.}\` \\|"
  v="$(reg_diff "$(at "$TASK_BASE" "$PATHS")" "$REG_PATHS_HEAD" "$re")" || { WHY="$PATHS: $v"; return 1; }
  v="$(reg_diff "$(at "$TASK_BASE" "$LAYERS")" "$(content "$LAYERS")" "")" || { WHY="$LAYERS: $v"; return 1; }
}
check 'the two registers change only their "pending ADR-0006" cells, plus one row for the worker entry module' k07_registers

k07_worker_row() {
  [ -n "$WORKER_MODULE" ] || { WHY="ADR-0006 Background work names no entry module"; return 1; }
  local r; r="$(grep -E "^\\| \`${WORKER_MODULE//./\\.}\` \\|" <<< "$REG_PATHS_HEAD")"
  [ "$(grep -c . <<< "$r")" -eq 1 ] || { WHY="no single row for $WORKER_MODULE in $PATHS"; return 1; }
  need "$(cell "$r" 2)" '\bschema\b' "the row's risk classes" || return 1
  need "$(cell "$r" 3)" '\bADR-0006\b' "the row's decisions" || return 1
  need_sent "$(flat <<< "$S_BG")" 'Background work' '^That module is listed in \[?architecture-sensitive-paths\.md\b' || return 1
}
check "the sensitive-paths register has a row for the worker's entry module ADR-0006 names" k07_worker_row

# ---- result --------------------------------------------------------------------------------

echo "EKO-1-05 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE_REF, merge base $MB, head ${HEAD_REF:-working tree})"
[ "$failed" -eq 0 ]
