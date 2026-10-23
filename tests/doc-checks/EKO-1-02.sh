#!/usr/bin/env bash
# EKO-1-02 — document checks for the identity decision (ADR-0003), criteria K-01..K-07 of Issue #15.
#
#   bash tests/doc-checks/EKO-1-02.sh                       # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-02.sh --head <ref>          # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-02.sh --base <ref> [...]    # another base than origin/main
#
# Every document is read from the same place as the change set: the working tree by default (so a
# mutation applied to a file, committed or not, is seen by every check, including the git-diff
# checks of K-07, which then compare the merge base of <base> and HEAD with the working tree plus
# untracked files), or the commit named by --head (then `git diff <base>...<head>`).
#
# Each check is one line of output, "ok   <name>", "FAIL <name> — <why>" or (K-07 only, see below)
# "skip <name> — <why>". The names are the ones the PR's "K-<n> — test:" lines quote. Exit codes:
# 0 = every check that ran passed, 1 = at least one check
# failed, 2 = the script itself could not run (bad argument, missing file, not a repository) —
# never read 2 as a pass.
#
# K-07 is bound to the pull request: it judges the task's own change set, which exists only
# between the commit the task branched from and the task's last commit. The task branched from
# 03faa3ca45f00ef59be0122b7e445054ea29251f. After the merge, re-run every check, K-07 included,
# with that base pinned and the PR's head commit (the merge commit's second parent):
#
#   bash tests/doc-checks/EKO-1-02.sh --base 03faa3ca45f00ef59be0122b7e445054ea29251f --head <merge>^2
#
# Without --base, when ADR-0003 already exists at origin/main (the task is merged, so the change
# set against origin/main is empty or belongs to later work), the K-07 checks print "skip" with
# that command and are not counted; K-01..K-06 still run. With an explicit --base nothing is
# skipped. During the PR ADR-0003 does not exist at origin/main, so K-07 always runs there.
#
# What these checks are: line and sentence matching over prose. They prove that a statement is
# present (or absent) in the decision, not that the statement is true of any running system.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
TASK_BASE="03faa3ca45f00ef59be0122b7e445054ea29251f"
HEAD_REF=""
die() { echo "EKO-1-02 doc-checks: $* — the checks did not run" >&2; exit 2; }
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

DECISIONS="docs/architecture/decisions"
ADR1="$DECISIONS/ADR-0001-application-stack.md"
ADR2="$DECISIONS/ADR-0002"
LAYERS="docs/architecture/layer-dependencies.md"
PATHS="docs/architecture/architecture-sensitive-paths.md"

# ---- reading -------------------------------------------------------------------------------

# content <path> — the file from the working tree or from --head, without carriage returns.
content() {
  if [ -z "$HEAD_REF" ]; then
    [ -r "$1" ] || return 1
    tr -d '\r' < "$1"
  else
    git show "$HEAD_REF:$1" 2>/dev/null | tr -d '\r'
  fi
}

# The one ADR-0003 file.
if [ -z "$HEAD_REF" ]; then
  adr3_list="$(ls "$DECISIONS"/ADR-0003-*.md 2>/dev/null)"
else
  adr3_list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/" | grep -E '/ADR-0003-[^/]*\.md$')"
fi
[ "$(printf '%s\n' "$adr3_list" | grep -c .)" -eq 1 ] || die "expected exactly one $DECISIONS/ADR-0003-*.md, found: '${adr3_list}'"
ADR3="$adr3_list"
for f in "$ADR3" "$ADR1" "$LAYERS" "$PATHS"; do content "$f" >/dev/null || die "cannot read $f"; done

# section <heading regex> — stdin from the matching heading to the next heading of the same or a
# higher level (the heading line included).
section() {
  awk -v re="$1" '
    function level(s) { match(s, /^#+/); return RLENGTH }
    !on && /^#+ / && $0 ~ re { on = 1; lv = level($0); print; next }
    on && /^#+ / && level($0) <= lv { exit }
    on { print }'
}

# paras — stdin as one record per paragraph, list item, heading or table row; emphasis and code
# marks removed, white space collapsed. A wrapped sentence becomes one line.
paras() {
  awk '
    function flush() { if (buf != "") { gsub(/\*\*|`/, "", buf); gsub(/[[:space:]]+/, " ", buf); sub(/^ /, "", buf); sub(/ $/, "", buf); print buf }; buf = "" }
    /^[[:space:]]*$/ { flush(); next }
    /^(#|\||- |\* |[0-9]+\. |<!--)/ { flush(); buf = $0; if ($0 ~ /^(#|\|)/) flush(); next }
    { buf = (buf == "" ? $0 : buf " " $0) }
    END { flush() }'
}

# sents — stdin (already paras) split into sentences at ". " followed by a capital or "(".
sents() { sed -E 's/\. ([A-Z(])/.\n\1/g'; }

ADR3_TEXT="$(content "$ADR3")"
ADR3_SENTS="$(printf '%s\n' "$ADR3_TEXT" | paras | sents)"
DECISION_TEXT="$(printf '%s\n' "$ADR3_TEXT" | section '^## Decision')"
DECISION_SENTS="$(printf '%s\n' "$DECISION_TEXT" | paras | sents)"
sub_sents() { printf '%s\n' "$DECISION_TEXT" | section "$1" | paras | sents; }

# ---- the check runner ----------------------------------------------------------------------

passed=0; failed=0; skipped=0
WHY=""
# check '<name>' <function> — runs the function; it sets WHY and returns non-zero on a failure.
check() {
  local name="$1"; shift
  WHY=""
  if "$@"; then echo "ok   $name"; passed=$((passed + 1))
  else echo "FAIL $name — ${WHY:-check failed}"; failed=$((failed + 1)); fi
}
# has <text> <ERE> — case-insensitive match somewhere in the text.
has() { printf '%s\n' "$1" | grep -Eiq -- "$2"; }
need() { has "$1" "$2" || { WHY="missing: /$2/"; return 1; }; }
forbid() {  # forbid <text> <ERE> [<ERE that excuses the line>]
  local hits
  if [ -n "${3:-}" ]; then hits="$(printf '%s\n' "$1" | grep -Ei -- "$2" | grep -Eiv -- "$3")"
  else hits="$(printf '%s\n' "$1" | grep -Ei -- "$2")"; fi
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | head -n 1 | cut -c1-200)"; return 1; }
}

# bound_ok <sentences> — among the given sentences at least one states "within (at most) N
# minutes" with N <= 5, and none states a larger bound or "until ... expires".
bound_ok() {
  local s="$1"
  [ -n "$s" ] || { WHY="no sentence states the bound"; return 1; }
  if has "$s" 'until [^.]*(expire|end)'; then WHY="the bound is open-ended: $(printf '%s\n' "$s" | grep -Ei 'until [^.]*(expire|end)' | head -n 1 | cut -c1-200)"; return 1; fi
  local nums; nums="$(printf '%s\n' "$s" | grep -Eio 'within (at most |no more than )?[0-9]+ minutes?' | grep -Eo '[0-9]+')"
  [ -n "$nums" ] || { WHY="no 'within N minutes' bound in: $(printf '%s' "$s" | head -n 1 | cut -c1-200)"; return 1; }
  local n; for n in $nums; do
    [ "$n" -le 5 ] || { WHY="the stated bound is $n minutes, more than 5"; return 1; }
  done
}

# ==== K-01 ===================================================================================

k01_status() {
  printf '%s\n' "$ADR3_TEXT" | grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' \
    || { WHY="status line: $(printf '%s\n' "$ADR3_TEXT" | grep -E '^\*\*Status' | head -n 1)"; return 1; }
}
check 'ADR-0003 status reads Accepted' k01_status

k01_one_product() {
  local options names chosen n other
  options="$(printf '%s\n' "$ADR3_TEXT" | section '^## Options considered' | section '^### Identity server product' | paras)"
  names="$(printf '%s\n' "$options" | grep -E '^\| [A-Z]\. ' | sed -E 's/^\| [A-Z]\. ([^(|]*).*/\1/; s/[[:space:]]+$//')"
  n="$(printf '%s\n' "$names" | grep -c .)"
  [ "$n" -ge 2 ] || { WHY="the identity-server Options table has $n row(s), needs the chosen one and at least one other"; return 1; }
  chosen="$(sub_sents '^### Identity server product' | grep -Eo 'The identity server is [^,.(;]*' | head -n 1 | sed -E 's/^The identity server is //; s/[[:space:]]+$//')"
  [ -n "$chosen" ] || { WHY="no sentence 'The identity server is <product>' in the Decision"; return 1; }
  if has "$chosen" '( or |/|TBD|compliant|^an? |^any )'; then WHY="the Decision does not name one product: '$chosen'"; return 1; fi
  printf '%s\n' "$names" | grep -Fxq -- "$chosen" || { WHY="'$chosen' is not one of the options: $(printf '%s' "$names" | tr '\n' ',')"; return 1; }
  while IFS= read -r other; do
    [ -n "$other" ] && [ "$other" != "$chosen" ] || continue
    if printf '%s\n' "$DECISION_TEXT" | grep -Fq -- "$other"; then WHY="the Decision also names '$other'"; return 1; fi
  done <<< "$names"
}
check 'ADR-0003 names one identity server' k01_one_product

k01_personal_data() {
  local table idp app
  table="$(printf '%s\n' "$DECISION_TEXT" | section '^### Staff personal data' | paras | grep -E '^\|')"
  idp="$(printf '%s\n' "$table" | grep -E '^\| (Keycloak|Identity server|The identity server) \|' | awk -F'|' '{print $3}' | sed -E 's/^ +| +$//g')"
  app="$(printf '%s\n' "$table" | grep -E '^\| (Application|The application) \|' | awk -F'|' '{print $3}' | sed -E 's/^ +| +$//g')"
  [ -n "$idp" ] || { WHY="no row naming the staff personal data the identity server holds"; return 1; }
  [ -n "$app" ] || { WHY="no row naming the staff personal data the application holds"; return 1; }
  has "$app" 'subject identifier' || { WHY="the application row does not name the stored identifier: '$app'"; return 1; }
  has "$idp" 'e-mail' || { WHY="the identity-server row does not name the e-mail address: '$idp'"; return 1; }
}
check 'ADR-0003 names the staff personal data held by the identity server and by the application' k01_personal_data

# ==== K-02 ===================================================================================

k02_roles_source() {
  local roles; roles="$(sub_sents '^### Roles')"
  need "$roles" 'roles are rep, manager and administrator' || return 1
  need "$roles" 'Roles come only from the identity server.s verified assertion, never from a value the client sends' || return 1
  # No other role source anywhere in the decision: a client, browser or frontend that sends,
  # selects or passes a role, or a role taken from a header/query/body/cookie, unless the sentence
  # says it is ignored.
  forbid "$ADR3_SENTS" '\b(frontend|client|browser|single-page application|SPA|user)( application)? (sends|passes|supplies|provides|selects|picks|chooses|sets) (the |a |its |their )?(user.s |caller.s )?(active |current |selected )?roles?\b' || return 1
  forbid "$ADR3_SENTS" '\broles?\b[^.]*\b(request header|header|query|body|cookie)\b' '(ignored|never|\bnot\b)' || return 1
}
check 'ADR-0003 names the three roles and their single source' k02_roles_source

k02_multi_role() {
  local roles; roles="$(sub_sents '^### Roles')"
  need "$roles" 'One account may hold several roles' || return 1
  need "$roles" 'granted all of its roles' || return 1
  need "$roles" 'holding manager and administrator has manager rights' || return 1
}
check 'ADR-0003 grants all roles of a multi-role account' k02_multi_role

k02_admin_no_crm() {
  local roles; roles="$(sub_sents '^### Roles')"
  need "$roles" 'administrator grants no CRM data' || return 1
  need "$roles" 'holding only administrator is denied every API operation that reads or changes customers, visits, notes, actions or dashboards' || return 1
  # A sentence giving administrator read or change access to CRM data. Only a negation excuses it,
  # or the multi-role case (administrator together with manager or rep), which K-02 requires.
  local hits
  hits="$(printf '%s\n' "$ADR3_SENTS" \
    | grep -Ei '\badministrators?\b[^.]{0,40}\b(has|have|gets|get|is granted|are granted|grants|grant|may|can|is able to|are able to|sees|reads|views)\b' \
    | grep -Ei '\b(read|reads|access|see|sees|view|views|change|changes|reach)\b' \
    | grep -Ei '\b(CRM|customers?|visits?|notes?|actions?|dashboards?|manager|rep)\b' \
    | grep -Eiv '(no CRM|\bnot\b|never|denied|cannot)' \
    | grep -Eiv '\b(manager|rep) and administrator\b|\badministrator and (also )?(manager|rep)\b')"
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | head -n 1 | cut -c1-200)"; return 1; }
}
check 'administrator alone reads no CRM data' k02_admin_no_crm

k02_no_role_denied() {
  local roles; roles="$(sub_sents '^### Roles')"
  need "$roles" 'authenticated account with none of the three roles is denied every API operation' || return 1
  forbid "$ADR3_SENTS" '(no (app )?role|none of the (three )?roles|without a role)[^.]*(treated as|defaults? to|is given|gets the rights of|assumed)' '(No role is assumed|\bnot\b|never)' || return 1
}
check 'an authenticated account with no app role is denied every API operation' k02_no_role_denied

# ==== K-03 ===================================================================================

LIFECYCLE="$(sub_sents '^### Account lifecycle')"
BOUND="$(sub_sents '^### How a request is verified')"

k03_no_self_registration() {
  need "$LIFECYCLE" 'Accounts are created only by an administrator' || return 1
  need "$LIFECYCLE" 'self-registration is disabled' || return 1
  forbid "$ADR3_SENTS" '\b(users|staff|anyone|a user|people)\b[^.]*\b(may|can|are able to)\b[^.]*\b(register|sign up|create (their|an) (own )?account)' '(\bnot\b|never|disabled|\bno\b)' || return 1
}
check 'no self-registration' k03_no_self_registration

k03_deactivated_no_login() { need "$LIFECYCLE" 'disabled account cannot log in'; }
check 'deactivated account cannot log in' k03_deactivated_no_login

k03_session_after_deactivation() {
  local s; s="$(printf '%s\n' "$BOUND" | grep -Ei 'deactivat' | grep -Ei 'session' | grep -Ei 'already issued')"
  bound_ok "$s" || return 1
  need "$BOUND" 'The mechanism is ' || return 1
  # The mechanism must not state a figure larger than the bound: no "N seconds" over 300, no
  # "N minutes" over 5, no hours or days, anywhere in the section that states the bound.
  local fig n
  fig="$(printf '%s\n' "$BOUND" | grep -Eio '[0-9]+ (seconds?|minutes?|hours?|days?)\b')"
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    case "$n" in
      *[Ss]econd*) [ "${n%% *}" -le 300 ] || { WHY="the bound's section states $n, more than 300 seconds"; return 1; } ;;
      *[Mm]inute*) [ "${n%% *}" -le 5 ] || { WHY="the bound's section states $n, more than 5 minutes"; return 1; } ;;
      *) WHY="the bound's section states $n, more than 5 minutes"; return 1 ;;
    esac
  done <<< "$fig"
}
check 'existing session refused within 5 minutes after deactivation' k03_session_after_deactivation

k03_session_after_role_removal() {
  local s; s="$(printf '%s\n' "$DECISION_SENTS" | grep -Ei '(remov[a-z]* (one |a )?role|role removal)' | grep -Ei 'session')"
  bound_ok "$s" || return 1
  has "$s" 'stays active' || { WHY="the role-removal bound does not say the account stays active"; return 1; }
}
check 'removed role refused within 5 minutes' k03_session_after_role_removal

k03_data_kept() {
  need "$LIFECYCLE" 'deletes, changes and reassigns no data on deactivation' || return 1
  need "$LIFECYCLE" 'keep its subject identifier' || return 1
}
check 'deactivation keeps app data and its link to the account' k03_data_kept

k03_stored_identifier() {
  local idn; idn="$(sub_sents '^### Identifier the application stores')"
  need "$idn" 'only by the Keycloak subject identifier|only by the identity server.s subject identifier' || return 1
  need "$idn" 'change of either, or two e-mail addresses differing only in case, leave the application.s records linked' || return 1
}
check 'ADR-0003 names the stored identifier and that it survives a username or e-mail change' k03_stored_identifier

k03_reset_no_reactivate() { need "$(sub_sents '^### Password reset')" 'reset does not enable a disabled account'; }
check 'password reset does not reactivate' k03_reset_no_reactivate

k03_only_removal() {
  need "$LIFECYCLE" 'Deactivation is the only removal' || return 1
  forbid "$ADR3_SENTS" '\baccounts?\b[^.]*\b(may|can|are allowed to)\b[^.]*\bbe (deleted|removed)' '(\bnot\b|never|forbidden)' || return 1
}
check 'deactivation is the only removal for an account that app data refers to' k03_only_removal

k03_reactivation() { need "$LIFECYCLE" 'Enabling a disabled account restores access to the same records'; }
check 'reactivation restores access to the same records' k03_reactivation

# ==== K-04 ===================================================================================

RESET="$(sub_sents '^### Password reset')"

k04_idp_pages() {
  need "$DECISION_SENTS" 'Login and password reset happen only on (Keycloak|the identity server)(.s)? pages' || return 1
  need "$DECISION_SENTS" 'types the password only on (Keycloak|the identity server)(.s)? pages' || return 1
}
check "login and reset happen on the identity server's pages" k04_idp_pages

k04_company_smtp() {
  local s; s="$(printf '%s\n' "$RESET" | grep -Ei 'reset e-mail' | grep -Ei 'company SMTP mailbox')"
  [ -n "$s" ] || { WHY="no sentence in Password reset sends the reset e-mail through the company SMTP mailbox"; return 1; }
  forbid "$RESET" 'backend.s mail sender|backend sends the reset' || return 1
}
check 'the identity server sends the reset e-mail through the company SMTP mailbox' k04_company_smtp

k04_until_mailbox() { need "$RESET" 'Until the company mailbox exists'; }
check 'ADR-0003 states what the identity server uses until the company mailbox exists' k04_until_mailbox

k04_backend_no_password() {
  need "$RESET" 'backend sends no reset e-mail, has no reset endpoint, and never receives a password' || return 1
  need "$DECISION_SENTS" 'no backend endpoint receives it' || return 1
  forbid "$ADR3_SENTS" '\b(backend|endpoint|API)\b[^.]*\b(passes|forwards|sends|accepts|receives|posts|takes|relays)\b[^.]*\b(username and password|password)' '(\bno\b|never|\bnot\b|disabled|forbid)' || return 1
  forbid "$ADR3_SENTS" '(password grant|direct-access[^.]*grant|resource-owner password[^.]*grant)[^.]*\b(enabled|used|allowed)\b' '(disabled|\bnot\b|never)' || return 1
}
check 'the backend sends no reset e-mail and receives no password' k04_backend_no_password

k04_no_enumeration() {
  need "$RESET" 'does not reveal whether the address has an account' || return 1
  need "$RESET" 'same for an address that belongs to an account and for one that does not' || return 1
  forbid "$ADR3_SENTS" '(unknown address|address (with|that has) no account|address without an account)[^.]*\b(is|gets|are) (told|informed|shown|warned|notified)' || return 1
  forbid "$ADR3_SENTS" 'told (that )?(no|the) account (exists|does not exist)' || return 1
}
check 'the reset response does not reveal whether the address has an account' k04_no_enumeration

# ==== K-05 ===================================================================================

GOOGLE="$(sub_sents '^### Accounts never depend on Google')"

k05_no_google_login() {
  need "$GOOGLE" 'No identity provider \(Google or any other\) is configured' || return 1
  need "$GOOGLE" 'no one signs in, and no account is created, through an external provider' || return 1
  forbid "$ADR3_SENTS" '(sign(s|ing)?[ -]in with google|log(s|ging)?[ -]in with google|google (login|sign-in|sso)|login with google|through google)' '(\bno\b|\bnot\b|never)' || return 1
  forbid "$ADR3_SENTS" '(google|external (identity )?provider)[^.]*\b(offered|optional|alternative|second method|allowed to sign)' '(\bno\b|\bnot\b|never)' || return 1
}
check 'no Google login' k05_no_google_login

k05_linking() { need "$GOOGLE" 'Linking a Google account[^.]*creates, authenticates and alters no account'; }
check 'Google linking creates, authenticates or alters no account' k05_linking

k05_login_without_google() { need "$GOOGLE" 'Login works with no Google account linked'; }
check 'login works with no Google account linked' k05_login_without_google

# ==== K-06 ===================================================================================

k06_storage() {
  local st; st="$(sub_sents '^### Identity server storage')"
  need "$st" 'stores its data in [^.]*database' || return 1
  need "$st" '(shares|does not share) the application.s PostgreSQL server' || return 1
}
check 'ADR-0003 settles where the identity server stores its data, and whether it shares the PostgreSQL server' k06_storage

k06_browser_flow() {
  local bf; bf="$(sub_sents '^### Browser flow')"
  need "$bf" 'The browser flow is (a|an) [a-z]' || return 1
  # The chosen flow: the words after "The browser flow is", up to the first ":", ";", "," or ".".
  local flow fam=0
  flow="$(printf '%s\n' "$bf" | grep -Eio 'The browser flow is [^:;,.]*' | head -n 1 | sed -E 's/^The browser flow is //I')"
  if has "$flow" '( or |\beither\b|\bchoice\b|\bbetween\b|\boptions?\b|\bTBD\b|decided|undecided|\blater\b)'; then
    WHY="the browser flow is not one choice: '$flow'"; return 1
  fi
  # It names exactly one of the three families of the Options table.
  has "$flow" '(backend session|backend-for-frontend|\bBFF\b|server-side session)' && fam=$((fam + 1))
  has "$flow" '(\bSPA\b|single-page application|public client|token in the browser|browser token|bearer)' && fam=$((fam + 1))
  has "$flow" '(proxy)' && fam=$((fam + 1))
  [ "$fam" -eq 1 ] || { WHY="the browser flow names $fam of the flows (backend session, SPA token, proxy), expected exactly 1: '$flow'"; return 1; }
}
check 'ADR-0003 fixes the browser flow' k06_browser_flow

# layer_cell <layer> <column> — a cell of a layer row (3 = path, 5 = must not depend on, 6 = why).
layer_cell() { content "$LAYERS" | awk -F'|' -v l="\`$1\`" -v c="$2" '{ n = $2; gsub(/^ +| +$/, "", n); if (n == l) { v = $c; gsub(/^ +| +$/, "", v); print v; exit } }'; }
lists() { printf '%s\n' "$1" | tr ',' '\n' | sed -E 's/^ +| +$//g' | grep -Fxq -- "$2"; }

k06_auth_row() {
  local path forbidden why
  path="$(layer_cell auth 3)"; forbidden="$(layer_cell auth 5)"; why="$(layer_cell auth 6)"
  [ "$path" = '`backend/app/auth/**`' ] || { WHY="no auth row for backend/app/auth/** (path cell: '$path')"; return 1; }
  has "$why" 'ADR-0003' || { WHY="the auth row does not cite ADR-0003"; return 1; }
  local l; for l in services api integrations; do lists "$forbidden" "$l" || { WHY="the auth row does not forbid $l"; return 1; }; done
}
check 'layer-dependencies.md has an auth row citing ADR-0003' k06_auth_row

k06_no_pending() {
  local f hits
  for f in "$LAYERS" "$PATHS"; do
    hits="$(content "$f" | paras | grep -Eio 'pending[^|;]*' | grep -E '(ADR-0003|/0003\b)')"
    [ -z "$hits" ] || { WHY="$f still reads '$(printf '%s' "$hits" | head -n 1)'"; return 1; }
    hits="$(content "$f" | paras | grep -Eio 'until ADR-0003[^.|]*')"
    [ -z "$hits" ] || { WHY="$f still reads '$(printf '%s' "$hits" | head -n 1)'"; return 1; }
  done
}
check "no 'pending ADR-0003' remains in the two registers" k06_no_pending

k06_inner_forbid_auth() {
  local l cell
  for l in domain services data core integrations; do
    cell="$(layer_cell "$l" 5)"
    [ -n "$cell" ] || { WHY="no $l row"; return 1; }
    lists "$cell" auth || { WHY="the $l row does not list auth under 'Must not depend on' ('$cell')"; return 1; }
  done
  cell="$(layer_cell api 5)"
  [ -n "$cell" ] || { WHY="no api row"; return 1; }
  if lists "$cell" auth; then WHY="the api row forbids auth, but api is the layer that depends on it"; return 1; fi
}
check 'inner layers forbid auth' k06_inner_forbid_auth

k06_adr1_addendum() {
  local add
  add="$(content "$ADR1" | section '^## Addenda' | paras | grep -E '^- [0-9]{4}-[0-9]{2}-[0-9]{2}:')"
  [ -n "$add" ] || { WHY="ADR-0001 has no dated addendum"; return 1; }
  printf '%s\n' "$add" | grep -E 'ADR-0003' | grep -Eq '\bauth\b' || { WHY="no dated addendum of ADR-0001 names auth and ADR-0003"; return 1; }
}
check "ADR-0001's addendum records the auth rule" k06_adr1_addendum

k06_layer_check() {
  local reg out
  reg="$(mktemp)"; content "$LAYERS" > "$reg"
  out="$(bash scripts/layer-check.sh --register "$reg" "$BASE_REF" "${HEAD_REF:-HEAD}" 2>&1)"; local code=$?
  rm -f "$reg"
  [ "$code" -eq 0 ] || { WHY="layer-check.sh exited $code: $(printf '%s' "$out" | tail -n 1)"; return 1; }
}
check 'layer-check.sh exits 0' k06_layer_check

# ==== K-07 ===================================================================================

# The change set: --head → git diff <base>...<head>; otherwise the merge base against the working
# tree (tracked changes, staged or not) plus untracked, non-ignored files.
changed_files() {
  if [ -n "$HEAD_REF" ]; then git diff --name-only "$MB" "$HEAD_REF"
  else { git diff --name-only "$MB"; git ls-files --others --exclude-standard; } | sort -u; fi
}
adr1_diff() {
  if [ -n "$HEAD_REF" ]; then git diff -U0 --no-color --no-ext-diff "$MB" "$HEAD_REF" -- "$ADR1"
  else git diff -U0 --no-color --no-ext-diff "$MB" -- "$ADR1"; fi | tr -d '\r'
}
CHANGED="$(changed_files)"

# The PR-bound skip (see the header): only without an explicit --base, and only when ADR-0003 is
# already part of the base, which is never the case while the task's PR is open.
K07_SKIP=""
if [ -z "$BASE_GIVEN" ] && git cat-file -e "$BASE_REF:$ADR3" 2>/dev/null; then
  K07_SKIP="$ADR3 already exists at $BASE_REF (the task is merged); re-run with --base $TASK_BASE --head <merge>^2"
fi
# check07 '<name>' <function> — check, or a printed skip that counts neither as passed nor failed.
check07() {
  if [ -n "$K07_SKIP" ]; then echo "skip $1 — $K07_SKIP"; skipped=$((skipped + 1)); return 0; fi
  check "$@"
}
ALLOWED_RE='^(docs/architecture/decisions/ADR-0003-[^/]*\.md|docs/architecture/decisions/ADR-0001-application-stack\.md|tests/doc-checks/EKO-1-02\.sh|docs/architecture/layer-dependencies\.md|docs/architecture/architecture-sensitive-paths\.md|docs/cost-register/.*)$'

k07_only_allowed() {
  local extra; extra="$(printf '%s\n' "$CHANGED" | grep . | grep -Ev "$ALLOWED_RE")"
  [ -z "$extra" ] || { WHY="outside the allowed set: $(printf '%s' "$extra" | tr '\n' ' ')"; return 1; }
}
check07 'the change set touches only ADR-0003, its document checks, the two registers, ADR-0001 and cost-register bookkeeping' k07_only_allowed

k07_no_code_no_adr2() {
  local bad; bad="$(printf '%s\n' "$CHANGED" | grep -E "^(backend/|frontend/|$ADR2)")"
  [ -z "$bad" ] || { WHY="listed: $(printf '%s' "$bad" | tr '\n' ' ')"; return 1; }
}
check07 'the change set lists nothing under backend/ or frontend/ and not ADR-0002' k07_no_code_no_adr2

k07_adr1_no_removed() {
  local removed; removed="$(adr1_diff | grep -E '^-' | grep -Ev '^--- ')"
  [ -z "$removed" ] || { WHY="removed line in ADR-0001: $(printf '%s' "$removed" | head -n 1 | cut -c1-160)"; return 1; }
}
check07 'ADR-0001 diff has no removed line' k07_adr1_no_removed

# Added lines of ADR-0001 as "<new line number>\t<text>".
adr1_added() {
  adr1_diff | awk '
    /^@@/ { match($0, /\+[0-9]+/); n = substr($0, RSTART + 1, RLENGTH - 1) + 0; next }
    /^\+\+\+ / { next }
    /^\+/ { print n "\t" substr($0, 2); n++; next }'
}
k07_adr1_after_addenda() {
  local start first_bad
  start="$(content "$ADR1" | awk '
    /^## Addenda[[:space:]]*$/ { h = NR; next }
    h && !e && /-->/ { e = NR }
    END { if (!h) print 0; else print (e ? e : h) }')"
  [ "$start" -gt 0 ] || { WHY="ADR-0001 has no '## Addenda' heading"; return 1; }
  first_bad="$(adr1_added | awk -F'\t' -v s="$start" '$1 <= s { print; exit }')"
  [ -z "$first_bad" ] || { WHY="added line $(printf '%s' "$first_bad" | cut -f1) is above the end of the Addenda heading and comment (line $start): $(printf '%s' "$first_bad" | cut -f2 | cut -c1-120)"; return 1; }
}
check07 'every added ADR-0001 line comes after the Addenda heading and its comment' k07_adr1_after_addenda

k07_adr1_one_dated() {
  local added dated first
  added="$(adr1_added)"
  [ -n "$added" ] || { WHY="ADR-0001 has no added line"; return 1; }
  dated="$(printf '%s\n' "$added" | cut -f2 | grep -cE '^- \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}:\*\*')"
  [ "$dated" -eq 1 ] || { WHY="$dated added lines start a dated item, expected exactly 1"; return 1; }
  first="$(printf '%s\n' "$added" | head -n 1 | cut -f2)"
  printf '%s\n' "$first" | grep -Eq '^- \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}:\*\*' || { WHY="the first added line is not the dated item: $(printf '%s' "$first" | cut -c1-120)"; return 1; }
}
check07 'ADR-0001 gains exactly one dated addendum, as its first added line' k07_adr1_one_dated

# ---- result --------------------------------------------------------------------------------

echo "EKO-1-02 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE_REF, head ${HEAD_REF:-working tree})"
[ "$failed" -eq 0 ]
