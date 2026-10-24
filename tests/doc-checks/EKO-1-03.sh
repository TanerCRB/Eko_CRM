#!/usr/bin/env bash
# EKO-1-03 — document checks for the deployment and recovery decision (ADR-0004), criteria
# K-01..K-07 of Issue #16.
#
#   bash tests/doc-checks/EKO-1-03.sh                       # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-03.sh --head <ref>          # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-03.sh --base <ref> [...]    # another base than origin/main
#   bash tests/doc-checks/EKO-1-03.sh --offline [...]       # skip the two checks that ask GitHub
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
# Content checks on ADR-0004 read it with every HTML comment removed (inline and multi-line); an
# opening "<!--" with no closing "-->" fails its own check and hides the rest of the file from the
# others. They are scoped to "## Decision" or to one of its "###" sections, as each check says.
# Byte comparisons of ADR-0001..0003 (K-07) read the files unstripped.
#
# Bases. TASK_BASE below is the commit the task branched from; the forward references K-05 counts
# are read from ADR-0001..0003 as they stand there, and the register rows K-05 compares are read
# from it too. The K-07 change set is `git diff <merge base of --base and head>`, the change set a
# pull request against main shows. The branch merged origin/main (ea06765, which only added the
# EKO-1-08 entry to docs/PLAN.md) after it started, so the change set from TASK_BASE itself also
# lists docs/PLAN.md, a change that is main's, not the task's. After the merge, re-run every check
# with main's commit before the merge as base and the PR's head commit:
#
#   bash tests/doc-checks/EKO-1-03.sh --base <merge>^1 --head <merge>^2
#
# Without --base, when ADR-0004 already exists at origin/main (the task is merged, so the change
# set against origin/main is empty or belongs to later work), the K-07 change-set checks print
# "skip" with that command and are not counted; K-01..K-06 and the K-07 contradiction checks still
# run. With an explicit --base nothing is skipped. During the PR ADR-0004 does not exist at
# origin/main, so K-07 always runs there.
#
# Two checks ask GitHub through `gh` (K-05: the identifier/Issue pairs match the Issue titles;
# K-07: Issue #16 records the gate-1 approval of the deviation). They fail when `gh` cannot answer;
# --offline prints them as "skip" instead, by name.
#
# A task given as `EKO-x-yy (#n)` resolves when EKO-x-yy is an entry of docs/PLAN.md and the pair
# is in PAIRS below; PAIRS is the register's identifiers with the Issue whose title carries
# "[EKO-x-yy]", read from GitHub on 2026-10-24 and re-checked by the named gh check.
#
# What these checks are: line and sentence matching over prose. They prove that a statement is
# present (or absent) in the decision, not that the statement is true of any running system.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
TASK_BASE="5d85dfe0b188e88f4925dd15fe92d0334eea86d0"
HEAD_REF=""
OFFLINE=""
REPO_SLUG="TanerCRB/Eko_CRM"
die() { echo "EKO-1-03 doc-checks: $* — the checks did not run" >&2; exit 2; }
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
PATHS="docs/architecture/architecture-sensitive-paths.md"
PLAN="docs/PLAN.md"

PAIRS='EKO-1-01 6
EKO-1-02 15
EKO-1-03 16
EKO-1-04 17
EKO-1-05 18
EKO-1-06 19
EKO-1-07 20
EKO-1-08 36'

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
# at <ref> <path> — the file at a commit, without carriage returns.
at() { git show "$1:$2" 2>/dev/null | tr -d '\r'; }

if [ -z "$HEAD_REF" ]; then
  adr4_list="$(ls "$DECISIONS"/ADR-0004-*.md 2>/dev/null)"
else
  adr4_list="$(git ls-tree --name-only "$HEAD_REF" "$DECISIONS/" | grep -E '/ADR-0004-[^/]*\.md$')"
fi
[ "$(printf '%s\n' "$adr4_list" | grep -c .)" -eq 1 ] || die "expected exactly one $DECISIONS/ADR-0004-*.md, found: '${adr4_list}'"
ADR4="$adr4_list"
for f in "$ADR4" "$ADR1" "$ADR2" "$ADR3" "$PATHS" "$PLAN"; do content "$f" >/dev/null || die "cannot read $f"; done
for f in "$ADR1" "$ADR2" "$ADR3" "$PATHS"; do at "$TASK_BASE" "$f" >/dev/null || die "cannot read $f at $TASK_BASE"; done

# strip_comments — stdin without HTML comments (inline or spanning lines). A line that held only
# comment text is dropped, so a comment between two lines of a paragraph does not split it. Exits
# 3 when a "<!--" is never closed (everything after it is then dropped).
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
    /^(#|\||[[:space:]]*- |\* |[0-9]+\. )/ { flush(); buf = $0; if ($0 ~ /^(#|\|)/) flush(); next }
    { buf = (buf == "" ? $0 : buf " " $0) }
    END { flush() }'
}

# sents — stdin (already paras) split into sentences at ". " followed by a capital or "(".
sents() { sed -E 's/\. ([A-Z(])/.\n\1/g'; }

ADR4_RAW="$(content "$ADR4")"
ADR4_TEXT="$(printf '%s\n' "$ADR4_RAW" | strip_comments)"; STRIP_RC=$?
ADR4_SENTS="$(printf '%s\n' "$ADR4_TEXT" | paras | sents)"
DECISION_TEXT="$(printf '%s\n' "$ADR4_TEXT" | section '^## Decision')"
DECISION_SENTS="$(printf '%s\n' "$DECISION_TEXT" | paras | sents)"
sub_text() { printf '%s\n' "$DECISION_TEXT" | section "$1"; }
sub_paras() { sub_text "$1" | paras; }
sub_sents() { sub_paras "$1" | sents; }
OPTIONS_TEXT="$(printf '%s\n' "$ADR4_TEXT" | section '^## Options considered')"
CONTROLS="$(printf '%s\n' "$ADR4_TEXT" | section '^## Controls' | paras | grep -E '^\| ADR-0004-C[0-9]+ \|')"
PLAN_TEXT="$(content "$PLAN")"

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
skip() { echo "skip $1 — $2"; skipped=$((skipped + 1)); }
# has <text> <ERE> — case-insensitive match somewhere in the text.
has() { printf '%s\n' "$1" | grep -Eiq -- "$2"; }
need() { has "$1" "$2" || { WHY="missing${3:+ in $3}: /$2/"; return 1; }; }
forbid() {  # forbid <text> <ERE> [<ERE that excuses the line>]
  local hits
  if [ -n "${3:-}" ]; then hits="$(printf '%s\n' "$1" | grep -Ei -- "$2" | grep -Eiv -- "$3")"
  else hits="$(printf '%s\n' "$1" | grep -Ei -- "$2")"; fi
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | head -n 1 | cut -c1-200)"; return 1; }
}
# control <ERE> <what> — a row of the Controls table matches.
control() { has "$CONTROLS" "$1" || { WHY="no ADR-0004-Cn row for $2 (/$1/)"; return 1; }; }
# numbered <text> — the numbered list items of a section's paras.
numbered() { printf '%s\n' "$1" | grep -E '^[0-9]+\. '; }

# pair_ok <identifier> <issue> — the identifier is an entry of docs/PLAN.md and the pair is known.
pair_ok() {
  printf '%s\n' "$PLAN_TEXT" | grep -Fq -- "**$1**" || { WHY="$1 is not an entry of $PLAN"; return 1; }
  printf '%s\n' "$PAIRS" | grep -Fxq -- "$1 $2" || { WHY="$1 (#$2) does not match the identifier's Issue ($(printf '%s\n' "$PAIRS" | grep -E "^$1 " | sed -E 's/^[^ ]+ /#/' ))"; return 1; }
}
# pairs_ok <text> — every "EKO-x-yy (#n)" in the text resolves.
pairs_ok() {
  local id n
  while read -r id n; do
    [ -n "$id" ] || continue
    pair_ok "$id" "$n" || return 1
  done < <(printf '%s\n' "$1" | grep -Eo 'EKO-[0-9]+-[0-9]+ \(#[0-9]+\)' | sed -E 's/ \(#([0-9]+)\)/ \1/')
}
NOT='\b(not|never|no|neither|nor|without|refuses?|refused)\b'

# ==== K-01 ===================================================================================

k01_comments() { [ "$STRIP_RC" -eq 0 ] || { WHY="an opening <!-- is never closed"; return 1; }; }
check 'ADR-0004 has no unterminated comment' k01_comments

k01_status() {
  local st; st="$(printf '%s\n' "$ADR4_TEXT" | grep -E '^\*\*Status:\*\*')"
  [ "$(printf '%s\n' "$st" | grep -c .)" -eq 1 ] || { WHY="expected one status line, found: $(printf '%s' "$st" | tr '\n' '/')"; return 1; }
  printf '%s\n' "$st" | grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' || { WHY="status line: $st"; return 1; }
}
check 'ADR-0004 status reads Accepted' k01_status

k01_no_marker() {
  local hits; hits="$(printf '%s\n' "$ADR4_RAW" | grep -nE 'G-[0-9]+ = ')"
  [ -z "$hits" ] || { WHY="marker left: $(printf '%s' "$hits" | head -n 1 | cut -c1-160)"; return 1; }
}
check 'no G-n marker remains in ADR-0004' k01_no_marker

RUNTIMES='docker|podman|containerd|nerdctl|kubernetes|k3s|k8s|cri-o|lxc|lxd|nomad|openshift'
k01_one_runtime() {
  local s chosen fams rows
  s="$(sub_sents '^### Container runtime' | grep -Ei 'container runtime on the server is ' | head -n 1)"
  [ -n "$s" ] || { WHY="no sentence 'The container runtime on the server is ...' in Decision/Container runtime"; return 1; }
  chosen="$(printf '%s\n' "$s" | sed -E 's/.*container runtime on the server is //I; s/\.$//')"
  if has "$chosen" '( or |\beither\b|\bany\b|/|\bOCI\b|\bTBD\b|\bcompatible\b)'; then WHY="the runtime sentence does not name one runtime: '$chosen'"; return 1; fi
  fams="$(printf '%s\n' "$chosen" | grep -Eio "\b($RUNTIMES)\b" | tr 'A-Z' 'a-z' | sort -u)"
  [ "$(printf '%s\n' "$fams" | grep -c .)" -eq 1 ] || { WHY="the runtime sentence names $(printf '%s\n' "$fams" | grep -c .) runtimes: '$chosen'"; return 1; }
  rows="$(printf '%s\n' "$OPTIONS_TEXT" | section '^### Container runtime' | paras | grep -E '^\| [A-Z]\. ')"
  [ "$(printf '%s\n' "$rows" | grep -c .)" -ge 2 ] || { WHY="Options considered / Container runtime has fewer than two option rows"; return 1; }
  printf '%s\n' "$rows" | grep -Eiq "\b$fams\b" || { WHY="the chosen runtime '$fams' is not an option row"; return 1; }
  # No other runtime named anywhere in the Decision.
  local other; other="$(printf '%s\n' "$DECISION_SENTS" | grep -Eio "\b($RUNTIMES)\b" | tr 'A-Z' 'a-z' | sort -u | grep -Fxv -- "$fams")"
  [ -z "$other" ] || { WHY="the Decision also names $(printf '%s' "$other" | tr '\n' ' ')"; return 1; }
}
check 'ADR-0004 names one container runtime' k01_one_runtime

k01_composition() {
  local rows roles r
  rows="$(sub_paras '^### Composition and placement' | grep -E '^\| `?[a-z]')"
  roles="$(printf '%s\n' "$rows" | awk -F'|' '{ v = $4; gsub(/^ +| +$/, "", v); print v }')"
  for r in '^the backend' 'static file server' '^the PostgreSQL server' '^(the )?Keycloak\b|^the identity server' 'HTTPS entry point' 'produces[^|]*backup'; do
    printf '%s\n' "$roles" | grep -Eiq -- "$r" || { WHY="no composition row whose role matches /$r/"; return 1; }
  done
  need "$(sub_paras '^### Composition and placement')" 'Background work\. [^.]*ADR-0006' 'Composition and placement' || return 1
}
check 'the composition names every runtime component and places background work' k01_composition

k01_cloud_agnostic() {
  local s; s="$(sub_sents '^### Cloud-agnostic constraints')"
  need "$s" 'portable between OCI runtimes' 'Cloud-agnostic constraints' || return 1
  need "$s" 'reach it only through environment variables' 'Cloud-agnostic constraints' || return 1
  need "$s" 'persistent state lives only in the named volumes' 'Cloud-agnostic constraints' || return 1
  need "$s" 'No component depends on a cloud vendor.s managed service' 'Cloud-agnostic constraints' || return 1
  forbid "$DECISION_SENTS" '\b(AWS|Amazon|Azure|Google Cloud|GCP|RDS|Cloud SQL|S3|EKS|AKS|GKE)\b' || return 1
}
check 'the cloud-agnostic constraints are listed' k01_cloud_agnostic

k01_clocks() {
  local s; s="$(printf '%s\n' "$DECISION_SENTS" | grep -Ei 'clock' | grep -Ei 'within the offset ADR-0003-C2 allows')"
  [ -n "$s" ] || { WHY="no Decision sentence keeps the clocks within the offset ADR-0003-C2 allows"; return 1; }
  has "$s" 'backend' && has "$s" 'Keycloak' || { WHY="the clock sentence does not name the backend and Keycloak"; return 1; }
}
check "the backend's and Keycloak's clocks stay within the ADR-0003-C2 offset" k01_clocks

MIG="$(sub_sents '^### Migrations')"
k01_one_migrator() {
  local s svc row
  s="$(printf '%s\n' "$MIG" | grep -Ei '^(- )?Exactly one process runs alembic upgrade head: the one-shot [a-z-]+ service')"
  [ -n "$s" ] || { WHY="no 'Exactly one process runs alembic upgrade head: the one-shot <name> service' in Migrations"; return 1; }
  svc="$(printf '%s\n' "$s" | sed -E 's/.*the one-shot ([a-z-]+) service.*/\1/I')"
  row="$(sub_paras '^### Composition and placement' | grep -E "^\| $svc \|")"
  has "$row" 'one-shot[^|]*alembic upgrade head' || { WHY="the composition has no one-shot row for '$svc' running alembic upgrade head"; return 1; }
  forbid "$DECISION_SENTS" '\b(each|every|all|any)\b[^.]*\b(backend )?containers?\b[^.]*\b(runs?|run|migrates?)\b[^.]*\b(alembic|migration|it at start)' "$NOT|does not migrate" || return 1
  forbid "$DECISION_SENTS" '\b(web process|worker|backend)\b[^.]{0,60}\b(runs?|executes?|performs?) (it|alembic upgrade head|the migrations?)\b' "$NOT|only after|one-shot" || return 1
}
check 'exactly one named process runs alembic upgrade head' k01_one_migrator

k01_web_worker() { need "$MIG" 'web process, and any worker process started from the backend image, do not run it, neither at start nor at any other time' 'Migrations'; }
check 'the web process and any worker never run the migration' k01_web_worker

k01_every_deploy() { need "$MIG" 'runs on every deployment and every restart' 'Migrations'; }
check 'the migration runs on every deployment and every restart' k01_every_deploy

k01_serialised() { need "$MIG" 'Two runs at once are (serialised|serialized|prevented)' 'Migrations'; }
check 'two migration runs at once are serialised' k01_serialised

k01_no_old_code() {
  need "$MIG" 'No code serves on a schema older than itself' 'Migrations' || return 1
  need "$MIG" 'exits without serving when it is not the head revision' 'Migrations' || return 1
}
check 'no code serves on a schema older than itself' k01_no_old_code

k01_failed_migration() { need "$MIG" 'failed migration leaves (the previous release running|the service stopped)' 'Migrations'; }
check 'a failed migration leaves the previous release running or the service stopped' k01_failed_migration

k01_noop_restart() { need "$MIG" 'restart with no new revision[^.]*changes no schema' 'Migrations'; }
check 'a restart with no new revision changes no schema' k01_noop_restart

k01_first_deploy() { need "$MIG" 'first deployment runs [a-z-]+ on an empty application database' 'Migrations'; }
check 'the first deployment migrates an empty database' k01_first_deploy

k01_edc() {
  local dep steps
  dep="$(sub_paras '^### Deployment and expand')"
  steps="$(numbered "$dep")"
  printf '%s\n' "$steps" | grep -Eiq '^[0-9]+\. Release N \(expand\)' || { WHY="no release step 'Release N (expand)'"; return 1; }
  printf '%s\n' "$steps" | grep -Eiq '^[0-9]+\. Release N\+1 or later \(contract\)' || { WHY="no release step 'Release N+1 or later (contract)'"; return 1; }
  need "$(printf '%s\n' "$dep" | sents)" 'ships in a later release than its expand migration' 'Deployment and expand → deploy → contract' || return 1
  forbid "$DECISION_SENTS" 'contract[^.]*\bin the same release\b' '\b(never|not)\b' || return 1
}
check 'expand → deploy → contract is written as release steps with the contract in a later release' k01_edc

k01_backup_vs_deploy() { need "$(sub_sents '^### Deployment and expand')" 'deployment does not start while the scheduled backup is running'; }
check 'a deployment does not run during the scheduled backup' k01_backup_vs_deploy

k01_no_floating_tag() {
  forbid "$DECISION_SENTS" '\b[a-z][a-z0-9._/-]*:(latest|[0-9]+)([^.0-9a-z]|$)' || return 1
  forbid "$DECISION_SENTS" '\blatest\b' || return 1
}
check 'no floating image tag in the Decision' k01_no_floating_tag

k01_controls() {
  control 'docker compose config --services' 'the composition' || return 1
  control 'named volumes' 'the cloud-agnostic constraints' || return 1
  control 'only the migrate service.s command contains alembic upgrade' 'the migration process' || return 1
}
check 'Control rows exist for the composition, the cloud-agnostic constraints and the migration process' k01_controls

# ==== K-02 ===================================================================================

HTTPS="$(sub_sents '^### HTTPS exposure')"

k02_one_origin() { need "$HTTPS" 'single-page application and the API are served from one origin' 'HTTPS exposure'; }
check 'SPA and API are served from one origin' k02_one_origin

k02_plain_http() { need "$HTTPS" 'Plain HTTP[^.]*serves nothing except a redirect[^.]*HTTPS' 'HTTPS exposure'; }
check 'plain HTTP serves only a redirect to HTTPS' k02_plain_http

k02_certificates() {
  need "$HTTPS" 'obtains and renews the publicly trusted certificates for <app-host> and <auth-host>' 'HTTPS exposure' || return 1
  need "$HTTPS" 'certificate of <auth-admin-host>[^.]*provided and renewed by the IT department' 'HTTPS exposure' || return 1
}
check 'who provides and renews each certificate' k02_certificates

k02_public_pages() {
  need "$HTTPS" 'login, password-reset and required-action pages of the application realm are reachable from the internet' 'HTTPS exposure' || return 1
  forbid "$DECISION_SENTS" '\b(whole|entire|every part of the)\b[^.]*\b(application|server|system|composition)\b[^.]*\bonly\b[^.]*\b(company network|VPN)\b' || return 1
}
check "Keycloak's public pages are reachable from the internet" k02_public_pages

k02_admin_internal() {
  need "$HTTPS" 'administration console and the admin REST API, for every realm including the master realm, are reachable only from the company network' 'HTTPS exposure' || return 1
  need "$HTTPS" 'refuses every other request, in particular every request to /admin/' 'HTTPS exposure' || return 1
}
check 'the admin console and admin REST API of every realm, master included, are company-network only' k02_admin_internal

k02_account_console() { need "$HTTPS" 'account console is reachable from neither the internet nor the company network' 'HTTPS exposure'; }
check 'the account console is reachable from neither' k02_account_console

k02_no_public_admin() {
  forbid "$DECISION_SENTS" '(admin(istration)? console|admin REST API|/admin/)[^.]*\b(reachable|served|available|exposed|open|accessible)\b[^.]*(from the internet|internet-facing|publicly|on <auth-host>|on <app-host>|public listener)' "$NOT|\bonly from the company network\b" || return 1
}
check 'no Decision sentence puts the admin console on an internet-facing hostname' k02_no_public_admin

k02_bruteforce() { need "$HTTPS" 'No login page of a shared environment is reachable from the internet until the live realm has brute-force detection on' 'HTTPS exposure'; }
check 'brute-force protection is on before a login page is public' k02_bruteforce

k02_reset_timing() {
  local s; s="$(printf '%s\n' "$HTTPS" | grep -Ei 'response time of a reset request for a known and for an unknown address')"
  [ -n "$s" ] || { WHY="reset-response timing is neither decided nor forwarded in HTTPS exposure"; return 1; }
  has "$s" 'EKO-[0-9]+-[0-9]+ \(#[0-9]+\)' || { WHY="the reset-timing measurement names no task: $(printf '%s' "$s" | cut -c1-160)"; return 1; }
  pairs_ok "$s" || return 1
}
check 'reset-response timing is decided or forwarded to a named task' k02_reset_timing

k02_placeholders() {
  forbid "$ADR4_SENTS" '\b([a-z0-9-]+\.)+(com|pl|eu|net|org|io|info|biz|local|lan|internal|corp|intra|intranet|home|app|dev|cloud|online)\b' || return 1
  forbid "$ADR4_SENTS" 'https?://[^<]' || return 1
  need "$DECISION_SENTS" 'every hostname in this decision is a placeholder' || return 1
}
check 'hostnames appear only as placeholders' k02_placeholders

k02_samesite() { need "$HTTPS" '(same-site|cross-site) navigation' 'HTTPS exposure'; }
check "the ADR says which case of the login callback's site applies" k02_samesite

k02_control() { control '/admin/[^|]*refused' 'the public/admin split'; }
check 'a Control row exists for the public/admin split' k02_control

# ==== K-03 ===================================================================================

SECRETS_TEXT="$(sub_text '^### Secret handling')"
SECRETS="$(printf '%s\n' "$SECRETS_TEXT" | paras | sents)"
INVENTORY="$(printf '%s\n' "$SECRETS_TEXT" | paras | grep -E '^\| ' | grep -Ev '^\| Secret \||^\|---')"

k03_inventory() {
  local r
  for r in 'PostgreSQL superuser' 'Application database role' 'Keycloak database role' 'Backup database role' \
           'Session-token encryption key' 'OIDC client secret' 'SMTP credentials' 'Keycloak bootstrap admin credential' \
           'Master-realm[^|]*admin credential' 'Backup encryption private key' 'Backup destination[^|]*credential' 'TLS private key'; do
    printf '%s\n' "$INVENTORY" | awk -F'|' '{ print $2 }' | grep -Eiq -- "$r" || { WHY="no inventory row for /$r/"; return 1; }
  done
  printf '%s\n' "$INVENTORY" | grep -Ei '^\| Google' | grep -Eq 'ADR-0006[^|]*\(#18\)|EKO-1-05 \(#18\)' || { WHY="no inventory row forwarding the Google secrets as a class to ADR-0006 (#18)"; return 1; }
}
check 'the secret inventory names every required secret' k03_inventory

k03_columns() {
  local row bad
  bad="$(printf '%s\n' "$INVENTORY" | awk -F'|' '
    NF < 8 { print "too few cells: " $0; next }
    { exempt = ($2 ~ /\(not secret\)/ || $4 ~ /ADR-0006/)
      for (i = 4; i <= 7; i++) { v = $i; gsub(/^ +| +$/, "", v); if (v == "" || (v == "—" && !exempt)) { print "empty cell " i ": " $2; next } }
      d = $5; if (d ~ /(^|[^a-z])(file|files|mounted|mount)([^a-z]|$)/) print "delivered through a file: " $2 }')"
  [ -z "$bad" ] || { WHY="$(printf '%s' "$bad" | head -n 1 | cut -c1-160)"; return 1; }
}
check 'every inventory entry says where it is kept, how it is delivered, who reads it and how it is rotated' k03_columns

k03_neither() {
  need "$SECRETS" 'Secrets are in neither the repository nor any image' 'Secret handling' || return 1
  need "$SECRETS" 'The repository half: no committed file holds a secret value' 'Secret handling' || return 1
  need "$SECRETS" 'The image half: .env\* files are excluded from every image build context by every .dockerignore' 'Secret handling' || return 1
}
check 'secrets are in neither the repository nor any image' k03_neither

k03_own_values() { need "$SECRETS" 'Every shared environment has its own values' 'Secret handling'; }
check 'each environment has its own secret values' k03_own_values

k03_no_default() {
  need "$SECRETS" 'A missing secret stops its component' 'Secret handling' || return 1
  need "$SECRETS" 'required with no default' 'Secret handling' || return 1
}
check 'a missing secret stops its component' k03_no_default

k03_no_committed_secret() {
  forbid "$DECISION_SENTS" '\b(password|secret|credential|key)s?\b[^.]*\b(is|are)? ?(set|stored|kept|written|placed|committed|hard-?coded|defined)\b[^.]*\b(docker-compose|compose\.ya?ml|composition file|Dockerfile|realm export|VITE_)' "$NOT|only environment placeholders|\bout of\b" || return 1
}
check 'no Decision sentence places a secret value in a committed file, an image or a VITE_ variable' k03_no_committed_secret

k03_inspect_logs() {
  need "$SECRETS" 'docker inspect' 'Secret handling' || return 1
  need "$SECRETS" 'No component writes a secret value to its log' 'Secret handling' || return 1
}
check 'secrets visible through docker inspect or in logs are addressed' k03_inspect_logs

k03_control() { control 'secret[^|]*\.dockerignore|\.dockerignore[^|]*secret|secret variable' 'secret handling'; }
check 'a Control row exists for secret handling' k03_control

# ==== K-04 ===================================================================================

BACKUP="$(sub_sents '^### Backup')"
RESTORE_P="$(sub_paras '^### Restore procedure')"
RESTORE="$(printf '%s\n' "$RESTORE_P" | sents)"

k04_frequency() {
  need "$BACKUP" 'A backup runs once every day' 'Backup' || return 1
  forbid "$BACKUP" '\b(weekly|monthly|once a week|every week|every [2-9][0-9]* days|every (two|three|four|five|six|seven) days|every [0-9]{3,} hours|every (2[5-9]|[3-9][0-9]) hours)\b' || return 1
}
check 'a backup runs at least once every 24 hours' k04_frequency

k04_destination() {
  need "$BACKUP" 'Each backup set is written to storage on another host' 'Backup' || return 1
  need "$BACKUP" 'second disk, volume or directory of the server.s own host is not off the server' 'Backup' || return 1
  forbid "$DECISION_SENTS" '\b(second|separate|another|dedicated) (disk|volume|directory|partition)\b[^.]*\bsame (host|server)\b' "$NOT" || return 1
}
check 'the backup destination is off the server and the same host is excluded' k04_destination

k04_scope() { need "$BACKUP" 'Each backup set holds the application database and Keycloak.s database' 'Backup'; }
check 'the backup holds both the application database and Keycloak.s database' k04_scope

k04_encryption() {
  need "$BACKUP" 'encrypted on the server with the backup public key' 'Backup' || return 1
  need "$BACKUP" 'private key that decrypts it is kept off the server' 'Backup' || return 1
  need "$BACKUP" 'encrypted at rest from installation' 'Backup' || return 1
  need "$BACKUP" 'recovery key of that encryption is kept off the server' 'Backup' || return 1
}
check 'encryption at rest is decided for backups and volumes, with the keys off the server' k04_encryption

k04_retention() {
  local n; n="$(sub_paras '^### Backup' | grep -Ei '^- Retention\.' | grep -Eio 'last [0-9]+ days' | grep -Eo '[0-9]+' | head -n 1)"
  [ -n "$n" ] || { WHY="the retention sentence states no number of days"; return 1; }
  [ "$n" -ge 2 ] || { WHY="retention of $n day(s) leaves no previous set for restore step 3"; return 1; }
}
check 'retention is a number of days' k04_retention

k04_alerts() {
  need "$BACKUP" 'reports a failed run' 'Backup' || return 1
  need "$BACKUP" 'a check that does not run on the server[^.]*alerts the IT department when the newest backup set is older than [0-9]+ hours' 'Backup' || return 1
}
check 'a failed and a missing backup both reach the operator, the missing one by an off-server check' k04_alerts

k04_consistent() { need "$BACKUP" 'consistent snapshot while writes continue' 'Backup'; }
check 'the backup stays consistent while writes continue' k04_consistent

k04_restore_list() {
  local steps; steps="$(numbered "$RESTORE_P")"
  [ "$(printf '%s\n' "$steps" | grep -c .)" -ge 3 ] || { WHY="the restore procedure is not a numbered list"; return 1; }
  need "$steps" 'both from the same backup set, so the two are at mutually consistent points' 'the numbered restore steps' || return 1
  need "$steps" 'restored data runs with that release.s images' 'the numbered restore steps' || return 1
  need "$steps" 'with the schema at that release.s head' 'the numbered restore steps' || return 1
  need "$steps" 'with the public listener closed' 'the numbered restore steps' || return 1
  need "$steps" 'Only then open the public listener' 'the numbered restore steps' || return 1
  need "$RESTORE" 'uses nothing kept only on the lost server' 'Restore procedure' || return 1
}
check 'the restore procedure is numbered steps restoring both databases consistently, with nothing from the lost server' k04_restore_list

k04_first_test() {
  local s; s="$(printf '%s\n' "$RESTORE" | grep -Ei 'restore is first tested')"
  [ -n "$s" ] || { WHY="no sentence says when the restore is first tested"; return 1; }
  has "$s" 'before go-live' || { WHY="the first test is not before go-live"; return 1; }
  has "$s" 'host like it|like production' || { WHY="the first test is not on a host like production"; return 1; }
  has "$s" 'EKO-[0-9]+-[0-9]+ \(#[0-9]+\)' || { WHY="the first-test sentence names no task as EKO-x-yy (#n): $(printf '%s' "$s" | cut -c1-200)"; return 1; }
  pairs_ok "$s" || return 1
  forbid "$s" '\b(periodically|convenient|from time to time|regularly)\b' || return 1
}
check 'the first tested restore is before go-live by a named task' k04_first_test

k04_controls() {
  control 'backup set exists for each of the last' 'the backup' || return 1
  control 'restore procedure, carried out on a host holding nothing from the original server' 'the restore' || return 1
}
check 'Control rows exist for the backup and the restore' k04_controls

# ==== K-05 ===================================================================================

FWD="$(sub_paras '^### Items forwarded to this decision')"
FWD_ENTRIES="$(printf '%s\n' "$FWD" | grep -E '^- ')"
DECISION_HEADINGS="$(printf '%s\n' "$DECISION_TEXT" | grep -E '^###+ ' | sed -E 's/^#+ //; s/[[:space:]]+$//')"

# heading_ok <name> [<ERE the section must mention>]
heading_ok() {
  printf '%s\n' "$DECISION_HEADINGS" | grep -Fxq -- "$1" || { WHY="'$1' is not a heading of ADR-0004's Decision"; return 1; }
  if [ -n "${2:-}" ]; then
    local re; re="$(printf '%s' "$1" | sed -E 's/[][\\.*^$+?(){}|/]/\\&/g')"
    sub_text "^###+ $re\$" | paras | grep -Eiq -- "$2" || { WHY="section '$1' does not mention /$2/"; return 1; }
  fi
}

# The closed list of K-05: source ADR | entry-title ERE | ERE the "decided in" section must mention.
ITEMS='ADR-0001|^- container runtime —|Docker Engine
ADR-0001|^- image composition —|composition consists of
ADR-0001|^- HTTPS exposure —|HTTPS
ADR-0001|^- static file server —|static file server
ADR-0001|^- secret handling —|secret
ADR-0001|^- backup( and restore)? —|backup
ADR-0001|^- (backup and )?restore —|restore
ADR-0001|alembic upgrade head|alembic upgrade head
ADR-0001|^- expand → deploy → contract —|contract
ADR-0002|^- database container composition —|PostgreSQL
ADR-0002|^- database credentials and secret handling —|database role password
ADR-0002|^- daily off-server backup —|once every day
ADR-0002|^- restore procedure —|restore
ADR-0002|^- encryption at rest of volumes and backups —|encrypted at rest
ADR-0002|alembic upgrade head|alembic upgrade head
ADR-0002|^- expand → deploy → contract —|contract
ADR-0003|^- credentials kept out of the realm export —|realm export
ADR-0003|^- Keycloak.s database in the same backup( and restore)? —|Keycloak.s database
ADR-0003|^- Keycloak.s database in the same (backup and )?restore —|Keycloak.s database
ADR-0003|^- connection-limit values —|connection limit
ADR-0003|^- session-encryption key handling —|encryption key
ADR-0003|^- cross-site callback depending on Keycloak.s placement —|site
ADR-0003|^- one origin for the SPA and the API —|one origin
ADR-0003|^- clock synchronisation of the backend and Keycloak —|clock
ADR-0003|^- the operator reading admin events, and the ADR-0003-C22 review —|admin events
ADR-0003|^- bootstrap of the first administrator —|bootstrap
ADR-0003|^- recovery when no administrator remains —|no active account holds administrator
ADR-0003|^- placement, hostnames and HTTPS of Keycloak.s public pages and of the administration console|administration console
ADR-0003|^- reset-response timing —|reset
ADR-0003|^- client secrets and SMTP credentials —|SMTP'

k05_items() {
  local src title sec entries e ok name
  while IFS='|' read -r src title sec; do
    [ -n "$src" ] || continue
    entries="$(printf '%s\n' "$FWD_ENTRIES" | grep -Ei -- "$title" | grep -E "— [^→]*\b$src\b")"
    [ -n "$entries" ] || { WHY="no entry for '$title' citing $src"; return 1; }
    ok=""
    while IFS= read -r e; do
      while IFS= read -r name; do
        [ -n "$name" ] || continue
        heading_ok "$name" "$sec" && ok=1
      done < <(printf '%s\n' "$e" | grep -Eo 'decided in \*[^*]+\*' | sed -E 's/^decided in \*//; s/\*$//')
      if printf '%s\n' "$e" | grep -Eq 'forwarded on to EKO-[0-9]+-[0-9]+ \(#[0-9]+\)'; then
        pairs_ok "$(printf '%s\n' "$e" | sed -E 's/^[^—]*— //; s/^[^→]*→//')" && ok=1
      fi
    done <<< "$entries"
    [ -n "$ok" ] || { WHY="the entry for '$title' ($src) points to no Decision section mentioning /$sec/ and no named task${WHY:+: $WHY}"; return 1; }
  done <<< "$ITEMS"
}
check 'every item ADR-0001..0003 forward to ADR-0004 has an entry with its source and a resolving pointer' k05_items

k05_pointers() {
  local e tail name
  [ -n "$FWD_ENTRIES" ] || { WHY="the list of forwarded items is empty"; return 1; }
  while IFS= read -r e; do
    case "$e" in *"→"*) ;; *) WHY="entry without a pointer: $(printf '%s' "$e" | cut -c1-120)"; return 1 ;; esac
    tail="$(printf '%s\n' "$e" | sed -E 's/^[^—]*— //; s/^[^→]*→ ?//')"
    printf '%s\n' "$tail" | grep -Eq '^(decided in \*[^*]+\*|(forwarded on to )?EKO-[0-9]+-[0-9]+ \(#[0-9]+\))' \
      || { WHY="pointer is neither a Decision section nor EKO-x-yy (#n): → $(printf '%s' "$tail" | cut -c1-100)"; return 1; }
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      heading_ok "$name" || return 1
    done < <(printf '%s\n' "$tail" | grep -Eo 'decided in \*[^*]+\*' | sed -E 's/^decided in \*//; s/\*$//')
    pairs_ok "$tail" || return 1
  done <<< "$FWD_ENTRIES"
  # Forward references: every bullet names a task as EKO-x-yy (#n), or says it is not decided.
  local fr; fr="$(sub_paras '^### Forward references' | grep -E '^- ')"
  while IFS= read -r e; do
    [ -n "$e" ] || continue
    printf '%s\n' "$e" | grep -Eq '^- (EKO-[0-9]+-[0-9]+ \(#[0-9]+\)|Not decided)' || { WHY="forward reference names no task as EKO-x-yy (#n): $(printf '%s' "$e" | cut -c1-120)"; return 1; }
    pairs_ok "$e" || return 1
  done <<< "$fr"
}
check 'every pointer of the forwarded-items list resolves to a Decision section or a planned task' k05_pointers

k05_complete() {
  local refs f adr n hit
  refs="$(printf '%s\n' "$FWD_ENTRIES" | sed -E 's/^[^—]*— //; s/→.*//' | awk '
    { s = $0; cur = ""
      while (match(s, /ADR-000[1-3]|l\.[0-9]+(-[0-9]+)?/)) {
        t = substr(s, RSTART, RLENGTH); s = substr(s, RSTART + RLENGTH)
        if (t ~ /^ADR/) { cur = t; continue }
        if (cur == "") continue
        sub(/^l\./, "", t); split(t, r, "-"); print cur, r[1], (r[2] == "" ? r[1] : r[2])
      } }')"
  for f in "$ADR1" "$ADR2" "$ADR3"; do
    adr="$(basename "$f" | grep -Eo '^ADR-000[1-3]')"
    while IFS= read -r n; do
      [ -n "$n" ] || continue
      hit="$(printf '%s\n' "$refs" | awk -v a="$adr" -v n="$n" '$1 == a && $2 <= n && n <= $3 { print; exit }')"
      [ -n "$hit" ] || { WHY="$adr l.$n (at $TASK_BASE) mentions ADR-0004 and no entry covers it: $(at "$TASK_BASE" "$f" | sed -n "${n}p" | cut -c1-120)"; return 1; }
    done < <(at "$TASK_BASE" "$f" | grep -n 'ADR-0004' | cut -d: -f1)
  done
}
check 'every line of ADR-0001..0003 that mentions ADR-0004 is covered by an entry' k05_complete

k05_all_pairs() { pairs_ok "$ADR4_TEXT"; }
check 'every EKO-x-yy (#n) in ADR-0004 matches docs/PLAN.md' k05_all_pairs

k05_gh_pairs() {
  command -v gh >/dev/null 2>&1 || { WHY="gh is not installed (use --offline to skip by name)"; return 1; }
  local id n title
  while read -r id n; do
    title="$(gh issue view "$n" --repo "$REPO_SLUG" --json title -q .title 2>/dev/null)" || { WHY="gh could not read Issue #$n"; return 1; }
    case "$title" in "[$id]"*) ;; *) WHY="Issue #$n is titled '$title', not [$id]"; return 1 ;; esac
  done <<< "$PAIRS"
}
if [ -n "$OFFLINE" ]; then skip 'the identifier/Issue pairs match the Issue titles on GitHub' '--offline'
else check 'the identifier/Issue pairs match the Issue titles on GitHub' k05_gh_pairs; fi

REG_HEAD="$(content "$PATHS")"
REG_BASE="$(at "$TASK_BASE" "$PATHS")"
reg_rows() { printf '%s\n' "$1" | grep -E '^\| `'; }
reg_note() { printf '%s\n' "$1" | grep -Ev '^\|'; }
# reg_cell <register text> <glob> <column> — 3 = risk classes, 4 = governing decisions.
reg_cell() { reg_rows "$1" | awk -F'|' -v g="\`$2\`" -v c="$3" '{ n = $2; gsub(/^ +| +$/, "", n); if (n == g) { v = $c; gsub(/^ +| +$/, "", v); print v; exit } }'; }
reg_globs() { reg_rows "$1" | awk -F'|' '{ n = $2; gsub(/^ +| +$/, "", n); gsub(/`/, "", n); print n }'; }

k05_no_pending() {
  local hits; hits="$(printf '%s\n' "$REG_HEAD" | tr '\n' ' ' | grep -Eio 'pending[[:space:]]+ADR-0004[^|]{0,30}')"
  [ -z "$hits" ] || { WHY="$PATHS still reads '$(printf '%s' "$hits" | head -n 1)'"; return 1; }
}
check "no 'pending ADR-0004' remains in the sensitive-paths register" k05_no_pending

k05_rows_cite() {
  local g cell
  while IFS= read -r g; do
    [ -n "$g" ] || continue
    reg_cell "$REG_BASE" "$g" 4 | grep -Eiq 'pending[^;]*ADR-0004' || continue
    cell="$(reg_cell "$REG_HEAD" "$g" 4)"
    [ -n "$cell" ] || { WHY="row '$g' is gone"; return 1; }
    has "$cell" 'ADR-0004' || { WHY="row '$g' no longer cites ADR-0004: '$cell'"; return 1; }
  done < <(reg_globs "$REG_BASE")
}
check "every register row that read 'pending ADR-0004' now cites ADR-0004" k05_rows_cite

k05_other_pending() {
  local b h
  for p in 'pending ADR-0005' 'ADR-0006'; do
    b="$(reg_rows "$REG_BASE" | grep -o -- "$p" | grep -c .)"; h="$(reg_rows "$REG_HEAD" | grep -o -- "$p" | grep -c .)"
    [ "$b" -eq "$h" ] || { WHY="the register rows hold '$p' $h time(s), $b at base"; return 1; }
  done
  reg_note "$REG_HEAD" | tr '\n' ' ' | grep -Eiq 'pending[^.]*0005[^.]*0006' || { WHY="the register note no longer says ADR-0005/0006 rows are pending"; return 1; }
}
check "the register's ADR-0005 and ADR-0006 markers are unchanged" k05_other_pending

# ==== K-06 ===================================================================================

DUTIES="$(sub_sents '^### Operator duties')"

k06_operator() { need "$(sub_sents '^### Operator$')" 'company IT department is the operator of every shared environment' 'Operator'; }
check 'the company IT department is named as operator' k06_operator

k06_reviewer_frequency() {
  need "$DUTIES" 'named by it as reviewer' 'Operator duties' || return 1
  local s; s="$(printf '%s\n' "$DUTIES" | grep -Ei 'reviewer reads the application realm.s admin events')"
  [ -n "$s" ] || { WHY="no sentence has the reviewer read the admin events"; return 1; }
  has "$s" 'ADR-0003-C22' || { WHY="the reviewer sentence does not run the ADR-0003-C22 review"; return 1; }
  has "$s" 'every [0-9]+ days' || { WHY="the review frequency is not a number of days: $(printf '%s' "$s" | cut -c1-200)"; return 1; }
}
check 'the reviewer is named by function and reviews at a stated number of days' k06_reviewer_frequency

k06_reviewer_roles() {
  if has "$DECISION_SENTS" 'reviewer may hold (the application role )?administrator'; then
    need "$DECISION_SENTS" 'no effective detection' || { WHY="the reviewer may hold administrator and no accepted-risk sentence says a planted administrator has no effective detection"; return 1; }
  else
    need "$DUTIES" 'reviewer may not hold the application role administrator' 'Operator duties' || return 1
  fi
  need "$DUTIES" 'may not hold any master-realm role that can change the application realm' 'Operator duties' || return 1
}
check 'whether the reviewer may hold administrator or a master-realm role is stated' k06_reviewer_roles

k06_reviewer_account() {
  local s; s="$(printf '%s\n' "$DUTIES" | grep -Ei 'reviewer reads through a dedicated read-only account in the master realm')"
  [ -n "$s" ] || { WHY="no sentence names the reviewer's account and realm"; return 1; }
  has "$s" 'no manage-\*' || { WHY="the reviewer's account is not stated to hold no manage-* role"; return 1; }
}
check "the reviewer's account and realm are stated and hold no manage-* role" k06_reviewer_account

k06_break_glass() {
  local s; s="$(printf '%s\n' "$DUTIES" | grep -Ei 'Full master-realm administration is a break-glass credential')"
  [ -n "$s" ] || { WHY="no sentence names who holds full master-realm administration"; return 1; }
  has "$s" 'at most (two|three|[0-9]+) holders' || { WHY="the number of master-realm holders is not bounded"; return 1; }
  has "$s" 'neither of them the reviewer' || { WHY="the master-realm holders are not kept apart from the reviewer"; return 1; }
}
check 'the holders of full master-realm rights are named and bounded' k06_break_glass

k06_handover() {
  forbid "$DECISION_SENTS" 'in person or (by|over the|on the) (tele)?phone' || return 1
  forbid "$DECISION_SENTS" '(temporary password|first password)[^.]*\bby (tele)?phone\b' || return 1
  if has "$DUTIES" 'onboarding is always in person'; then return 0; fi
  local s; s="$(printf '%s\n' "$DUTIES" | grep -Ei 'first temporary password of a new account')"
  [ -n "$s" ] || { WHY="no new-account handover sentence in Operator duties"; return 1; }
  need "$s" 'set only right before the user logs in' 'the handover sentence' || return 1
  need "$s" 'only in person or in a call the administrator makes to a phone number the company already holds' 'the handover sentence' || return 1
  need "$s" 'never to an incoming caller' 'the handover sentence' || return 1
  need "$s" 'never in writing' 'the handover sentence' || return 1
}
check "the new-account handover applies the reset rule or is always in person" k06_handover

k06_steps() {
  local b r
  b="$(numbered "$(sub_paras '^### Bootstrap of the first administrator')")"
  r="$(numbered "$(sub_paras '^### Recovery when no administrator remains')")"
  [ "$(printf '%s\n' "$b" | grep -c .)" -ge 2 ] || { WHY="bootstrap is not numbered steps"; return 1; }
  [ "$(printf '%s\n' "$r" | grep -c .)" -ge 2 ] || { WHY="recovery is not numbered steps"; return 1; }
  need "$b" 'under the new-account rule' 'the bootstrap steps' || return 1
  need "$r" 'under the new-account rule' 'the recovery steps' || return 1
}
check 'bootstrap and recovery are numbered steps that use the new-account rule' k06_steps

k06_control() { control 'ADR-0003-C22 review were done at intervals of at most [0-9]+ days' 'the review'; }
check 'a Control row exists for the review' k06_control

# ==== K-07 ===================================================================================

# --- (2), (3): the Decision itself, independent of the change set ---

k07_change_sentence() {
  local s; s="$(printf '%s\n' "$DECISION_SENTS" | grep -Ei '^This decision changes (no accepted decision|exactly one accepted decision|[a-z]+ accepted decisions?)')"
  [ -n "$s" ] || { WHY="no Decision sentence says which accepted decisions it changes"; return 1; }
}
check 'the Decision says which accepted decisions it changes' k07_change_sentence

k07_named_deviation() {
  local dev; dev="$(printf '%s\n' "$DECISION_SENTS" | grep -Ei '\bdeviations?\b')"
  [ -n "$dev" ] || { WHY="no Decision sentence names a deviation"; return 1; }
  has "$dev" 'ADR-0003-C19' || { WHY="the named deviation is not ADR-0003-C19's connection budget"; return 1; }
  forbid "$dev" '.' 'ADR-0003-C19|connection budget' || return 1
  forbid "$DECISION_SENTS" '(\baddend(um|a) (to|of) ADR-000[1-3]|ADR-000[1-3].s addend(um|a)|\bchanges ADR-000[1-3])' 'ADR-0003-C19|connection budget' || return 1
  forbid "$DECISION_SENTS" '^This decision changes no accepted decision' || return 1
}
check 'the Decision names the ADR-0003-C19 deviation and nothing else as one' k07_named_deviation

k07_env_only() {
  forbid "$DECISION_SENTS" '(/run/secrets|docker secrets?|secrets? files?|mounted (as )?(a |the )?files?|files? mounted|\bfrom (a |the )?(mounted )?files?\b)' "$NOT" || return 1
  # Any other carrier than the environment: a secret provided, passed or made available through a
  # volume, tmpfs, file or mount (added after mutation EKO-1-03-M56 survived the first version).
  forbid "$DECISION_SENTS" '\b(secrets?|credentials?|passwords?|keys?)\b[^.]*\b(provided|delivered|passed|supplied|given|handed|reach(es)?|injected|made available|read)\b[^.]*\b(volumes?|tmpfs|files?|mounts?|mounted)\b' "$NOT|only as environment variables" || return 1
}
check 'the Decision delivers no secret to a component as a file' k07_env_only

k07_shared_pg() {
  need "$(sub_paras '^### Composition and placement')" 'PostgreSQL server holding the application database and Keycloak.s database' 'Composition and placement' || return 1
  forbid "$DECISION_SENTS" '\b(second|separate|own|dedicated|another) (PostgreSQL|database|Postgres) (server|container|instance|service)\b' "$NOT" || return 1
}
check "the Decision keeps Keycloak's database on the shared PostgreSQL server" k07_shared_pg

k07_reset_rule() {
  forbid "$DECISION_SENTS" '\b(temporary|first|reset|new) password[^.]*\b(e-mail(ed|s)?|by email|SMS|text message|letter|on paper|in writing|written)\b' '\b(never|not|no)\b' || return 1
  # The same, verb first ("the holder e-mails the temporary password"; added after mutation
  # EKO-1-03-M48 survived the first version, which read only "password ... e-mail").
  forbid "$DECISION_SENTS" '\b(e-mails?|e-mailed|emails?|texts?|texted|sends?|sent|posts?|writes?|written)\b[^.]*\b(temporary|first|reset|new) password' '\b(never|not|no)\b' || return 1
  forbid "$DECISION_SENTS" '\b(incoming caller|calls? (in|the administrator))\b' '\bnever\b' || return 1
}
check 'the Decision hands over no password in writing or to an incoming caller' k07_reset_rule

k07_reset_mail_off() {
  need "$DECISION_SENTS" 'the reset e-mail is off in shared environments' || return 1
  forbid "$DECISION_SENTS" 'reset e-mail[^.]*\b(is|are) (on|enabled|sent|turned on|active)\b' '\b(not|off|until|while)\b' || return 1
}
check 'the Decision keeps the reset e-mail off until the company mailbox exists' k07_reset_mail_off

k07_no_idp() {
  forbid "$DECISION_SENTS" '(identity provider|(sign(s|ing)?|log(s|ging)?) ?in (with|through|via) (Google|an? (external|identity|social) provider)|Google (login|sign-in|SSO|identity))' "$NOT" || return 1
}
check 'the Decision configures no identity provider' k07_no_idp

k07_three_role_sum() { need "$(sub_sents '^### Composition and placement')" 'limits of the application, Keycloak and backup roles together stay below max_connections minus superuser_reserved_connections' 'Composition and placement'; }
check "the Decision's connection budget is the three-role sum the approved addendum restates" k07_three_role_sum

# --- (1), (4), (5): the change set ---

changed_files() {
  if [ -n "$HEAD_REF" ]; then git diff --name-only "$MB" "$HEAD_REF"
  else { git diff --name-only "$MB"; git ls-files --others --exclude-standard; } | sort -u; fi
}
file_diff() {
  if [ -n "$HEAD_REF" ]; then git diff -U0 --no-color --no-ext-diff "$MB" "$HEAD_REF" -- "$1"
  else git diff -U0 --no-color --no-ext-diff "$MB" -- "$1"; fi | tr -d '\r'
}
CHANGED="$(changed_files)"

K07_SKIP=""
if [ -z "$BASE_GIVEN" ] && git cat-file -e "$BASE_REF:$ADR4" 2>/dev/null; then
  K07_SKIP="$ADR4 already exists at $BASE_REF (the task is merged); re-run with --base <merge>^1 --head <merge>^2"
fi
check07() { if [ -n "$K07_SKIP" ]; then skip "$1" "$K07_SKIP"; return 0; fi; check "$@"; }

k07_adr12_identical() {
  local f d
  for f in "$ADR1" "$ADR2"; do
    d="$(file_diff "$f")"
    [ -z "$d" ] || { WHY="$f differs from $MB: $(printf '%s\n' "$d" | grep -E '^[-+][^-+]' | head -n 1 | cut -c1-140)"; return 1; }
  done
}
check07 'ADR-0001 and ADR-0002 are byte-identical to base' k07_adr12_identical

k07_adr3_no_removed() {
  local removed; removed="$(file_diff "$ADR3" | grep -E '^-' | grep -Ev '^--- ')"
  [ -z "$removed" ] || { WHY="removed or changed line in ADR-0003: $(printf '%s' "$removed" | head -n 1 | cut -c1-160)"; return 1; }
}
check07 'ADR-0003 has no removed or changed line' k07_adr3_no_removed

adr3_added() {
  file_diff "$ADR3" | awk '
    /^@@/ { match($0, /\+[0-9]+/); n = substr($0, RSTART + 1, RLENGTH - 1) + 0; next }
    /^\+\+\+ / { next }
    /^\+/ { print n "\t" substr($0, 2); n++; next }'
}
k07_adr3_after_addenda() {
  local start first_bad
  start="$(content "$ADR3" | awk '
    /^## Addenda[[:space:]]*$/ { h = NR; next }
    h && !e && /-->/ { e = NR }
    END { if (!h) print 0; else print (e ? e : h) }')"
  [ "$start" -gt 0 ] || { WHY="ADR-0003 has no '## Addenda' heading"; return 1; }
  first_bad="$(adr3_added | awk -F'\t' -v s="$start" '$1 <= s { print; exit }')"
  [ -z "$first_bad" ] || { WHY="added line $(printf '%s' "$first_bad" | cut -f1) is above the end of the Addenda heading and comment (line $start): $(printf '%s' "$first_bad" | cut -f2 | cut -c1-120)"; return 1; }
}
check07 'every added ADR-0003 line comes after its Addenda heading and comment' k07_adr3_after_addenda

k07_adr3_one_addendum() {
  local added dated body
  added="$(adr3_added | cut -f2)"
  [ -n "$added" ] || { WHY="ADR-0003 has no addendum, but ADR-0004 names a deviation (G-10 A)"; return 1; }
  dated="$(printf '%s\n' "$added" | grep -cE '^(#+ |- \*\*)[0-9]{4}-[0-9]{2}-[0-9]{2}')"
  [ "$dated" -eq 1 ] || { WHY="$dated dated addenda added to ADR-0003, one approved deviation (G-10 A)"; return 1; }
  printf '%s\n' "$added" | grep -Ev '^[[:space:]]*$' | head -n 1 | grep -Eq '^(#+ |- \*\*)[0-9]{4}-[0-9]{2}-[0-9]{2}' || { WHY="the first added line is not the dated addendum"; return 1; }
  body="$(printf '%s\n' "$added" | paras)"
  need "$body" 'What it restates' 'the ADR-0003 addendum' || return 1
  need "$body" 'ADR-0003-C19' 'the ADR-0003 addendum' || return 1
  need "$body" '^Why\.' 'the ADR-0003 addendum' || return 1
  need "$body" 'declared deviation, approved by the human at gate 1' 'the ADR-0003 addendum' || return 1
}
check07 'ADR-0003 gains exactly one dated addendum, restating ADR-0003-C19 with its reason' k07_adr3_one_addendum

ALLOWED_RE='^(docs/architecture/decisions/ADR-0004-[^/]*\.md|docs/architecture/decisions/ADR-0003-identity-and-access\.md|tests/doc-checks/EKO-1-03\.sh|docs/architecture/architecture-sensitive-paths\.md|docs/cost-register/.*)$'
k07_only_allowed() {
  local extra; extra="$(printf '%s\n' "$CHANGED" | grep . | grep -Ev "$ALLOWED_RE")"
  [ -z "$extra" ] || { WHY="outside the allowed set: $(printf '%s' "$extra" | tr '\n' ' ')"; return 1; }
}
check07 'the change set touches only ADR-0004, its document checks, the register, cost bookkeeping and ADR-0003' k07_only_allowed

k07_no_impl() {
  local bad; bad="$(printf '%s\n' "$CHANGED" | grep -E '^(backend/|frontend/|identity/|\.github/)|(^|/)([^/]*compose[^/]*\.ya?ml|Dockerfile[^/]*|\.env[^/]*|\.dockerignore|Caddyfile[^/]*)$')"
  [ -z "$bad" ] || { WHY="listed: $(printf '%s' "$bad" | tr '\n' ' ')"; return 1; }
}
check07 'the change set adds no code, realm export, workflow, composition, Dockerfile, env, dockerignore or Caddyfile' k07_no_impl

k07_register_rows() {
  local base_reg g bc hc c
  base_reg="$(at "$MB" "$PATHS")"
  while IFS= read -r g; do
    [ -n "$g" ] || continue
    bc="$(reg_cell "$base_reg" "$g" 3)"; hc="$(reg_cell "$REG_HEAD" "$g" 3)"
    [ -n "$hc" ] || { WHY="register row '$g' is gone"; return 1; }
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      printf '%s\n' "$hc" | tr ',' '\n' | sed -E 's/^ +| +$//g' | grep -Fxq -- "$c" || { WHY="register row '$g' lost the risk class '$c' ('$hc')"; return 1; }
    done < <(printf '%s\n' "$bc" | tr ',' '\n' | sed -E 's/^ +| +$//g')
  done < <(reg_globs "$base_reg")
}
check07 'every base row of the register remains with its glob and every risk class' k07_register_rows

k07_gh_approval() {
  command -v gh >/dev/null 2>&1 || { WHY="gh is not installed (use --offline to skip by name)"; return 1; }
  local labels body must
  labels="$(gh issue view 16 --repo "$REPO_SLUG" --json labels -q '.labels[].name' 2>/dev/null)" || { WHY="gh could not read Issue #16"; return 1; }
  printf '%s\n' "$labels" | grep -Fxq 'adr-deviation' || { WHY="Issue #16 has no adr-deviation label"; return 1; }
  body="$(gh issue view 16 --repo "$REPO_SLUG" --json body -q .body 2>/dev/null | tr -d '\r')"
  must="$(printf '%s\n' "$body" | grep -E '^Must stay' | head -n 1)"
  has "$must" 'exactly one approved deviation' || { WHY="the Must stay clause of Issue #16 names no approved deviation"; return 1; }
  has "$must" 'ADR-0003-C19' || { WHY="the Must stay clause of Issue #16 does not name ADR-0003-C19"; return 1; }
  has "$must" 'approved at gate 1' || { WHY="the Must stay clause of Issue #16 does not record the gate-1 approval"; return 1; }
}
if [ -n "$OFFLINE" ]; then skip 'Issue #16 records the gate-1 approval of the deviation' '--offline'
else check 'Issue #16 records the gate-1 approval of the deviation' k07_gh_approval; fi

# ---- result --------------------------------------------------------------------------------

echo "EKO-1-03 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE_REF, merge base $MB, head ${HEAD_REF:-working tree})"
[ "$failed" -eq 0 ]
