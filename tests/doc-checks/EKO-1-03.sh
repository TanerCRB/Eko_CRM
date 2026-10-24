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
# Fix round 1 (decisions A-H on #16, 2026-10-24) added the checks of the revised mechanisms and
# tightened the ones the Reviewer broke on paper. Fix round 2 (decisions on the findings at be73027,
# 2026-10-24) withdrew the K-01 exception for a rolled-back release: every deployment and every
# restart runs migrate, which changes nothing on a revision descending from its head (R-12). It
# added the checks of R-10..R-15, B-01, B-05, B-08 and B-09 and tightened the six checks the
# Reviewer broke on paper at be73027.
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
CONTROLS_ALL="$(printf '%s\n' "$ADR4_TEXT" | section '^## Controls' | paras | grep -E '^\| ADR-0004-C[0-9]+ \|')"
# Only a well-formed row counts as a Control row: one identifier, one criterion, three cell
# separators. Two rows run together on one line ("| C14 | ... || C15 | ... |") render as one row
# whose extra cells are dropped, so the second control is not in the table.
CONTROLS="$(printf '%s\n' "$CONTROLS_ALL" | awk '{ s = $0; n = gsub(/\|/, "", s); t = $0; c = gsub(/ADR-0004-C[0-9]+/, "", t); if (n == 3 && c == 1) print }')"
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
# has <text> <ERE> — case-insensitive match somewhere in the text. The text is given to grep as a
# here-string, not through a pipe: with pipefail, a writer still writing when "grep -q" exits on
# its first match dies of SIGPIPE and fails the pipeline. Git Bash on Windows rarely shows it;
# Linux (WSL, a CI runner) does on the larger texts (fix round 2).
has() { grep -Eiq -- "$2" <<< "$1"; }
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
  grep -Fq -- "**$1**" <<< "$PLAN_TEXT" || { WHY="$1 is not an entry of $PLAN"; return 1; }
  grep -Fxq -- "$1 $2" <<< "$PAIRS" || { WHY="$1 (#$2) does not match the identifier's Issue ($(printf '%s\n' "$PAIRS" | grep -E "^$1 " | sed -E 's/^[^ ]+ /#/' ))"; return 1; }
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
  grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]*$' <<< "$st" || { WHY="status line: $st"; return 1; }
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
  grep -Eiq "\b$fams\b" <<< "$rows" || { WHY="the chosen runtime '$fams' is not an option row"; return 1; }
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
    grep -Eiq -- "$r" <<< "$roles" || { WHY="no composition row whose role matches /$r/"; return 1; }
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

# K-01 "runs on every deployment and every restart", with no exception (fix round 2, R-12: the
# exception of fix round 1 for a rolled-back release is withdrawn; migrate is a no-op on a
# revision descending from its head). The sentence carries no exception word, and no Decision
# sentence lets a start skip migrate. No excuse is read from the line: the first version excused a
# whole line naming the rolled-back release, so "A start after a host reboot skips migrate, as the
# starts of a rolled-back release do." passed (EKO-1-03-M108). The one kept sentence, a backend
# container restarted alone by the restart policy (not a start of the environment), is removed by
# its exact text before the bans.
k01_every_deploy() {
  local s rest all
  s="$(printf '%s\n' "$MIG" | grep -Ei 'migrate runs on every deployment and every restart of the environment')"
  [ -n "$s" ] || { WHY="missing in Migrations: 'migrate runs on every deployment and every restart of the environment'"; return 1; }
  has "$s" 'migrate runs on every deployment and every restart of the environment \(every docker compose up\), with no exception, a rollback to the previous release and every start of the rolled-back release included; backend \(and any worker\) starts only after migrate has exited with success' || { WHY="the every-deployment sentence does not read '... every restart of the environment (every docker compose up), with no exception, a rollback to the previous release and every start of the rolled-back release included; backend (and any worker) starts only after migrate has exited with success': $(printf '%s' "$s" | cut -c1-200)"; return 1; }
  rest="$(printf '%s\n' "$s" | sed -E 's/\(every docker compose up\)//; s/, with no exception, a rollback to the previous release and every start of the rolled-back release included;/;/')"
  forbid "$rest" '\b(except|exception|unless|but not|other than|apart from|save for|skips?|skipped|without|only (on|at|when)|excluded)\b' || { WHY="the every-deployment sentence carries an exception: ${WHY#forbidden statement: }"; return 1; }
  all="$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/^A container of backend restarted alone by the runtime.s restart policy does not migrate; its revision check below decides whether it serves\.$/KEPT-RESTART-POLICY-SENTENCE/')"
  forbid "$all" '\b(skips?|skipped|skipping|without running|without|bypass(es|ed|ing)?|omits?|omitted) migrate\b' || return 1
  forbid "$all" '\bmigrate\b[^.]*\b(is|are|was|be) (skipped|not run|omitted|bypassed)\b' || return 1
  forbid "$all" '\b(does not|do not|need not|never|no longer) (run |start )?migrate\b|\bmigrate (does not|need not|is not) (run|start)( at| on| when| after| for|[,.;]|$)' || return 1
}
check 'the migration runs on every deployment and every restart, with no exception' k01_every_deploy

# R-12 (fix round 2): migrate makes backend's descent check, is a no-op on a revision descending
# from its head and fails on one it cannot place; C13 tests both.
k01_migrate_noop() {
  need "$MIG" '^- migrate changes nothing on a newer schema\.' 'Migrations' || return 1
  need "$MIG" 'Before it applies a revision, migrate reads the database.s Alembic revision and makes the same descent check as backend: when the revision is not the head its code ships but descends from that head, migrate exits with success and changes nothing' 'Migrations' || return 1
  need "$MIG" 'A revision the check cannot place as that head, as a revision before it or as a descendant of it fails the run, and the schema is left unchanged' 'Migrations' || return 1
  need "$MIG" 'So a rollback to the previous release, every later start of that release, a secret rotation that restarts the environment and a restore all run migrate like any other start' 'Migrations' || return 1
  forbid "$DECISION_SENTS" '\b(cannot place|cannot establish|unknown revision|unplaceable)\b[^.]*\b(exits with success|exits 0|is accepted|passes|is a no-op|serves)\b' || return 1
  control 'runs the previous release.s migrate against a database at the next release.s head after an expand migration: it exits 0 and leaves a schema dump identical to the one before it' 'migrate as a no-op on a descending revision (C13)' || return 1
  control 'runs migrate against a database at a revision its code cannot place: it exits non-zero and leaves the schema unchanged' 'migrate refusing an unplaceable revision (C13)' || return 1
}
check 'migrate changes nothing on a revision descending from its head and fails on one it cannot place' k01_migrate_noop

k01_serialised() { need "$MIG" 'Two runs at once are (serialised|serialized|prevented)' 'Migrations'; }
check 'two migration runs at once are serialised' k01_serialised

# R-05 fix (decision E): migrate runs with a lock and a statement timeout once it holds the
# advisory lock, and backup takes the same lock (K-01 serialisation; edges "a deployment during
# the scheduled backup", K-04 "a backup during a migration").
k01_lock_timeout() {
  need "$MIG" 'Once it holds the advisory lock, migrate runs its statements with a lock timeout and a statement timeout' 'Migrations' || return 1
  need "$MIG" 'A statement that waits longer for a table lock, or runs longer, fails the run' 'Migrations' || return 1
  forbid "$DECISION_SENTS" '\b(no|without( a| any)?) (lock|statement) timeouts?\b' || return 1
  forbid "$DECISION_SENTS" '\b(lock|statement) timeouts?\b[^.]*\b(is|are) (off|disabled|unset|optional|not set)\b' || return 1
}
check 'migrate runs with a lock timeout and a statement timeout' k01_lock_timeout

k01_backup_lock() {
  need "$MIG" 'The backup service takes the same advisory lock for the whole of its dumps' 'Migrations' || return 1
  need "$MIG" 'A backup therefore does not start while migrate runs, and migrate does not start changing the schema while a backup runs' 'Migrations' || return 1
  need "$(sub_sents '^### Deployment and expand')" 'advisory lock \(\*?Migrations\*?\) keeps a migration and a backup from running at the same time, in both directions' 'Deployment and expand → deploy → contract' || return 1
  forbid "$DECISION_SENTS" '\bbackup\b[^.]*\b(does not|never|need not|without)\b[^.]*\badvisory lock\b' || return 1
}
check 'backup takes the same advisory lock as migrate, in both directions' k01_backup_lock

# R-01 fix (decision B): the revision check accepts the code's head or a revision descending from
# it, never an older or unknown one; the equality wording of the first draft fails here.
k01_no_old_code() {
  need "$MIG" 'No code serves on a schema older than itself' 'Migrations' || return 1
  need "$MIG" 'exits without serving when it is not the head revision its code ships and not a revision that descends from that head; it never migrates' 'Migrations' || return 1
  need "$MIG" 'A revision older than that head, or one the check cannot establish as that head or a descendant of it, is always refused' 'Migrations' || return 1
  need "$MIG" 'The previous release may serve on a newer schema only within the expand → deploy → contract rule' 'Migrations' || return 1
  forbid "$DECISION_SENTS" '\b(accepts?|serves?( on)?|starts? on|runs? on)\b[^.]*\b(any|older|earlier|ancestor|unknown|previous) (revision|schema)s?\b' || return 1
  # A revision the check cannot read or establish still served (the Reviewer's paper break at
  # be73027: "If the revision cannot be read, backend logs a warning and serves."; EKO-1-03-M109).
  # "exits without serving" and "never serves" are the refusal itself; only those words are
  # neutralised, so a line that refuses and then serves still fails (contrast EKO-1-03-C11).
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/\b(exits without serving|without serving|never serves)\b/REFUSES/g')" '\b(cannot|can.t|could not|fails? to|unable to|does not) (be )?(read|reach|establish|place|determine|find|query)\b[^.]*\b(serves?|serving|answers|continues|keeps running|starts anyway|proceeds)\b' || return 1
  forbid "$DECISION_SENTS" '\b(backend|worker|revision check)\b[^.]*\b(logs?|records?|emits?|raises?) (a |an )?(warning|notice|alert)\b[^.]*\b(serves?|serving|starts?|continues|proceeds)\b' || return 1
  forbid "$DECISION_SENTS" '\b(unreadable|missing|empty|absent) (alembic )?(revision|alembic_version)\b' || return 1
}
check 'no code serves on a schema older than itself; the revision check accepts only its head or a descendant' k01_no_old_code

# Fix round 2 (R-12): a rollback starts the previous release with migrate first, as a no-op.
k01_rollback() {
  local d; d="$(sub_sents '^### Deployment and expand')"
  need "$d" '^Rollback to the previous release\.$' 'Deployment and expand → deploy → contract' || return 1
  need "$d" 'the operator starts the previous release by the digests its composition names, migrate first and then backend \(and any worker\) and frontend' 'Deployment and expand → deploy → contract' || return 1
  need "$d" 'the database stays at the newer head, which descends from the previous release.s head, so the previous release.s migrate exits with success and changes nothing, and the previous release.s revision check accepts that head' 'Deployment and expand → deploy → contract' || return 1
  need "$d" '^Every later start of the environment runs migrate in the same way\.$' 'Deployment and expand → deploy → contract' || return 1
  need "$d" '^A rollback goes back to the previous release only; going back further is a restore\.$' 'Deployment and expand → deploy → contract' || return 1
  need "$d" 'going back to an older Keycloak image is a restore' 'Deployment and expand → deploy → contract' || return 1
  need "$d" 'Going back past a contract migration is a restore' 'Deployment and expand → deploy → contract' || return 1
  forbid "$DECISION_SENTS" '\b(downgrade migration|alembic downgrade)\b' 'No downgrade migration is run' || return 1
  forbid "$DECISION_SENTS" '\b(rollback|roll(s|ed)? back|going back|goes back)\b[^.]*\b(two|several|multiple|more than one|any number of|earlier|older) releases?\b' || return 1
  control 'runs the previous release.s migrate against a database at the next release.s head after an expand migration: it exits 0 and leaves a schema dump identical to the one before it; the previous release.s backend started after it answers requests and leaves the schema unchanged' 'the rollback (C13)' || return 1
}
check 'a rollback goes one release back and runs migrate as a no-op; further back, and any Keycloak rollback, is a restore' k01_rollback

# R-13 (fix round 2): the one-release limit is the operator's rule, which the check does not enforce.
k01_rollback_procedural() {
  local d; d="$(sub_sents '^### Deployment and expand')"
  need "$d" '^This limit is a procedural rule of the operator, not one the revision check enforces: the check accepts every revision that descends from its code.s head and does not establish how many releases lie between the two\.$' 'Deployment and expand → deploy → contract' || return 1
  local all; all="$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/^This limit is a procedural rule of the operator, not one the revision check enforces: the check accepts every revision that descends from its code.s head and does not establish how many releases lie between the two\.$/PROCEDURAL-RULE-SENTENCE/')"
  forbid "$all" '\b(revision check|the check|migrate)\b[^.]*\b(enforces|bounds|limits|guarantees|ensures|refuses)\b[^.]*\b(one release|previous release only|one-release|how many releases|more than one release|rollback)\b' || return 1
  forbid "$all" '\b(revision check|the check)\b[^.]*\b(establishes|counts|knows) how many releases\b' || return 1
}
check 'the one-release limit of a rollback is a procedural rule the revision check does not enforce' k01_rollback_procedural

# B-09 (fix round 2): a release adding or tightening an access rule is never rolled back.
k01_access_rule_rollback() {
  local d; d="$(sub_sents '^### Deployment and expand')"
  need "$d" '^A release that adds or tightens an access rule \(a rule restricting what a user may read or change\) cannot be rolled back; going back past it is a restore\.$' 'Deployment and expand → deploy → contract' || return 1
  forbid "$DECISION_SENTS" '\baccess rules?\b[^.]*\b(can|may|is allowed to) (be )?(rolled back|roll back)\b' || return 1
  forbid "$DECISION_SENTS" '\b(rollback|roll(s|ed)? back)\b[^.]*\b(past|over|across|before) (a|an|the) (release that (adds|tightens)|access rule)\b' || return 1
}
check 'a release that adds or tightens an access rule cannot be rolled back' k01_access_rule_rollback

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
  grep -Eiq '^[0-9]+\. Release N \(expand\)' <<< "$steps" || { WHY="no release step 'Release N (expand)'"; return 1; }
  grep -Eiq '^[0-9]+\. Release N\+1 or later \(contract\)' <<< "$steps" || { WHY="no release step 'Release N+1 or later (contract)'"; return 1; }
  need "$(printf '%s\n' "$dep" | sents)" 'ships in a later release than its expand migration' 'Deployment and expand → deploy → contract' || return 1
  need "$(printf '%s\n' "$dep" | sents)" 'never in the same release, and only once no running release reads or writes the old shape' 'Deployment and expand → deploy → contract' || return 1
  # "same release" may appear only as the ban itself, the negation directly in front of it ("never
  # in the same release", "never ships in the same release"); any other mention, even one with a
  # "not" elsewhere in the line ("may ship in the same release when it is not urgent"), fails.
  # Tightened after the Reviewer's paper break of the first version, which excused every line
  # holding not/never (EKO-1-03-M59; contrast EKO-1-03-C06).
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/\b(never|not) (ships? |shipped |goes |go )?in the same release\b/NEGATED-BAN/Ig')" '\bsame release\b|\b(one|a single) release\b[^.]*\b(expand|contract)\b|\b(expand|contract)\b[^.]*\b(one|a single) release\b' || return 1
  forbid "$DECISION_SENTS" '\bcontract\b[^.]*\b(together with|alongside|along with|with) (its|the) expand\b' || return 1
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
  control 'migrate exits non-zero within its lock timeout' 'the lock timeout (C26)' || return 1
  control 'while backup holds the advisory lock a migrate run applies no DDL until it is released, and that while migrate holds it backup starts no dump' 'backup and migrate excluding each other (C26)' || return 1
}
check 'Control rows exist for the composition, the cloud-agnostic constraints and the migration process' k01_controls

# The criteria's preamble: each topic has at least one ADR-0004-Cn row. A row only counts when it
# is a row (see CONTROLS); this check names every line that is not one.
k01_control_rows() {
  local bad ids
  bad="$(printf '%s\n' "$CONTROLS_ALL" | grep . | grep -Fxv -- "$CONTROLS")"
  [ -z "$bad" ] || { WHY="a Controls line is not one well-formed row (one identifier, one criterion): $(printf '%s' "$bad" | head -n 1 | cut -c1-120)"; return 1; }
  ids="$(printf '%s\n' "$CONTROLS" | sed -E 's/^\| ADR-0004-C([0-9]+) \|.*/\1/')"
  printf '%s\n' "$ids" | awk '$1 != NR { exit 1 }' || { WHY="the Controls identifiers are not C1..Cn in order: $(printf '%s' "$ids" | tr '\n' ' ')"; return 1; }
}
check 'every line of the Controls table is one well-formed row, numbered C1..Cn' k01_control_rows

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

# R-07/B-03 fix (decision F): the admin listener is published only on the company-network
# interface, the source-network check is a second guard, and the public listener refuses SNI/Host
# <auth-admin-host>.
k02_admin_binding() {
  need "$HTTPS" 'The admin listener.s port is published only on the host.s company-network interface, never on an address the internet reaches' 'HTTPS exposure' || return 1
  need "$HTTPS" 'so the source-network check is a second guard and not the only one' 'HTTPS exposure' || return 1
  need "$HTTPS" 'A request that reaches the public listener with SNI or Host <auth-admin-host> is refused' 'HTTPS exposure' || return 1
  forbid "$DECISION_SENTS" '\badmin listener\b[^.]*\b(published|bound|listens?|exposed|served)\b[^.]*(0\.0\.0\.0|all (the )?(host.s )?(interfaces|addresses)|every (host )?(interface|address)|public (address|interface|IP)|internet-facing (address|interface))' || return 1
  # Any other statement of where the admin listener is published or bound (the Reviewer's paper
  # break at be73027: "the admin listener's port is also published on the host's WAN interface"
  # passed the closed list above; EKO-1-03-M110). The one required sentence is removed by its
  # exact text; whatever else says where the admin listener or its port is published fails.
  local others; others="$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/The admin listener.s port is published only on the host.s company-network interface, never on an address the internet reaches, so the source-network check is a second guard and not the only one\./REQUIRED-BINDING-SENTENCE./')"
  forbid "$others" '\badmin listener\b[^.]*\b(published|publishes|bound|binds|listens?|exposed|mapped|reachable on|forwarded)\b' || return 1
  # Scoped to the admin side: the same words about the public listener are its normal place
  # (contrast EKO-1-03-C09, which failed the first, unscoped version of this ban).
  # (<auth-admin-host> stands outside the \b groups: a word boundary never falls next to "<" or
  # ">", so the first version's "\b(...|<auth-admin-host>)\b" could not match it; EKO-1-03-M156.)
  forbid "$others" '(\b(admin listener|admin port|administration console)\b|<auth-admin-host>)[^.]*\b(WAN|uplink|external|outside|public-facing|internet-facing) (interface|address|port|IP)s?\b|\b(WAN|uplink|external|outside|public-facing|internet-facing) (interface|address|port|IP)s?\b[^.]*(\b(admin listener|admin port|administration console)\b|<auth-admin-host>)' || return 1
  forbid "$others" '\b(proxy|listeners?)\b[^.]*\b(published|bound)\b[^.]*\b(all|every|any) (host )?(interfaces|addresses|interface|address)\b' || return 1
  forbid "$DECISION_SENTS" '\bpublic listener\b[^.]*\b(forwards|serves|accepts|routes)\b[^.]*<auth-admin-host>' || return 1
  forbid "$DECISION_SENTS" '\bsource-network check is the only\b' || return 1
  control 'admin listener is bound to the host.s company-network address only, not to 0\.0\.0\.0, :: or an address the internet reaches' 'the admin listener binding (C3)' || return 1
  control 'over IPv4, and over IPv6 where the host has a public IPv6 address, with SNI and Host <auth-admin-host>, gets neither the administration console nor any /admin/ response' 'SNI/Host <auth-admin-host> on the public address (C5)' || return 1
}
check 'the admin listener is published only on the company-network interface and the public listener refuses <auth-admin-host>' k02_admin_binding

k02_account_console() { need "$HTTPS" 'account console is reachable from neither the internet nor the company network' 'HTTPS exposure'; }
check 'the account console is reachable from neither' k02_account_console

k02_no_public_admin() {
  forbid "$DECISION_SENTS" '(admin(istration)? console|admin REST API|/admin/)[^.]*\b(reachable|served|available|exposed|open|accessible)\b[^.]*(from the internet|internet-facing|publicly|on <auth-host>|on <app-host>|public listener)' "$NOT|\bonly from the company network\b" || return 1
}
check 'no Decision sentence puts the admin console on an internet-facing hostname' k02_no_public_admin

k02_bruteforce() {
  need "$HTTPS" 'No login page of a shared environment is reachable from the internet until the live realm has brute-force detection on' 'HTTPS exposure' || return 1
  need "$HTTPS" 'The master realm also has brute-force detection on before the admin listener of any shared environment is started' 'HTTPS exposure' || return 1
  forbid "$DECISION_SENTS" '\bbrute-force (detection|protection)\b[^.]*\b(off|disabled|optional|not needed)\b' || return 1
  control 'live application realm reports bruteForceProtected true, and before its admin listener is started, the live master realm reports bruteForceProtected true' 'brute force in both realms (C8)' || return 1
}
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

# R-06 fix: a rotation replaces every copy, so a restore from the master copies uses live values
# (K-03 "how it is rotated").
k03_rotation_copies() {
  need "$SECRETS" 'Every rotation of a secret replaces its value in the off-server master copy and in every environment file on the server that holds it, at the same time' 'Secret handling' || return 1
  forbid "$SECRETS" '\b(rotation|rotated|regenerated)\b[^.]*\b(master copy|off-server copy)\b[^.]*\b(later|afterwards|need not|is not updated|stays)\b' || return 1
}
check 'every rotation replaces the off-server master copy and every on-server copy of the secret' k03_rotation_copies

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
  local b
  need "$BACKUP" 'A backup runs once every day' 'Backup' || return 1
  # "the monthly verification" names the off-server check's interval, not the backup's (fix round
  # 2, the Retention item): only that exact noun phrase is taken out before the bans, so "a backup
  # runs monthly" or "monthly backups" still fail (contrast EKO-1-03-C07, mutation EKO-1-03-M111).
  b="$(printf '%s\n' "$BACKUP" | sed -E 's/\bthe monthly verification\b/the VERIFICATION/g')"
  forbid "$b" '\b(weekly|monthly|once a week|every week|every [2-9][0-9]* days|every (two|three|four|five|six|seven) days|every [0-9]{3,} hours|every (2[5-9]|[3-9][0-9]) hours)\b' || return 1
  # Less than daily without a number (added after the Reviewer's paper break "every other day").
  forbid "$b" '\b(every|each) (other|second|alternate) (day|night)s?\b|\balternate (days|nights)\b|\b(once|twice|three times) (a|per) (week|fortnight|month)\b|\bfortnightly\b|\b(on )?(weekdays|working days|business days|workdays)\b|\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)days?\b' || return 1
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

# R-04/B-05 fix (decision D): a monthly off-server decryption and manifest check of the newest
# set, and the last verified set kept beyond the retention (K-04: the restore works with nothing
# from the lost server; a failed run reaches the operator).
k04_verification() {
  need "$BACKUP" 'At least once every calendar month, the IT department fetches the newest backup set from the destination, decrypts it on a host that is not the server with the backup private key, and checks it against its manifest' 'Backup' || return 1
  need "$BACKUP" 'its row counts equal to those of the dump' 'Backup' || return 1
  need "$BACKUP" 'a set that fails either comparison is handled as a failed backup' 'Backup' || return 1
  need "$(sub_paras '^### Backup' | grep -Ei '^- Retention\.')" 'and beyond them the last three sets that passed the monthly verification below, each until three newer sets have passed it' 'the retention item' || return 1
  # "... and is never on the server" is the key's own ban, not a place it is decrypted.
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/,? and is never on the server//')" '\bdecrypt(s|ed|ing|ion)?\b[^.]*\b(on|at|in) the server\b' || return 1
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/,? and is never on the server//')" '\b(private key|decryption key)\b[^.]*\b(is|are) (kept|stored|copied|held|placed)\b[^.]*\bon the server\b' || return 1
  # The verification left out after a while or on a condition (the Reviewer's paper break at
  # be73027: "After the first year the check may be skipped while the 26-hour alert stays green.";
  # EKO-1-03-M112). Every sentence that names the verification or the check and lets it be skipped,
  # dropped or made optional fails, whatever it is conditioned on.
  # A negated skip ("may not be skipped") is the ban itself; only that phrase is neutralised
  # (contrast EKO-1-03-C12).
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/\b(may|must|can|shall|is|are) (not|never) be (skipped|omitted|dropped|suspended|waived|paused|postponed|stopped|discontinued|replaced)\b/NEGATED-SKIP/g')" '\b(verification|the check|monthly check|this check|that check)\b[^.]*\b(may|can|need not|is allowed to|is|are)\b[^.]*\b(skipped|omitted|dropped|suspended|optional|waived|paused|postponed|stopped|discontinued|replaced)\b' || return 1
  forbid "$DECISION_SENTS" '\b(skip|omit|drop|suspend|waive|pause|postpone|stop|discontinue)s?\b[^.]*\b(the verification|the monthly check|the check off the server|verifying)\b' || return 1
  forbid "$DECISION_SENTS" '\b(verification|monthly check)\b[^.]*\b(only|until|unless|except)\b[^.]*\b(first|year|month|alert|season|deployment|failure)\b' || return 1
  control 'decrypted off the server and checked against its manifest at intervals of at most one calendar month' 'the monthly verification (C27)' || return 1
  control 'the destination still holds the last three sets that passed the check, also when they are older than 30 days' 'the verified sets kept (C27)' || return 1
}
check 'the newest backup set is decrypted and checked off the server every month, and the last three verified sets are kept' k04_verification

# B-05 (fix round 2): the monthly check also compares the set with the off-server record of account
# changes, a fact the server cannot fabricate; C27 records it.
k04_verification_record() {
  need "$BACKUP" 'The same check compares the set with the IT department.s off-server record of account changes \(\*?Operator duties\*?\): the newest entries of that record made before the set.s time are present in the set.s Keycloak dump, a fact a compromised server cannot fabricate' 'Backup' || return 1
  forbid "$DECISION_SENTS" '\brecord of account changes\b[^.]*\b(need not|is not|are not|never) (be )?(compared|checked|read)\b' || return 1
  forbid "$DECISION_SENTS" '\b(compar\w*|check\w*)\b[^.]*\brecord of account changes\b[^.]*\b(optional|when available|if available|where possible|at the IT department.s discretion)\b' || return 1
  control 'each check on a host meeting the restore-host requirements and finding the newest entries of the record of account changes made before the set.s time in the set.s Keycloak dump' 'the record comparison (C27)' || return 1
}
check 'the monthly check compares the set with the off-server record of account changes' k04_verification_record

# The alert bound: the first missing daily run must be caught before a second one is due, so the
# bound lies above 24 and below 48 hours (added after the Reviewer's paper break "older than 260
# hours"), and the C17 row tests the same bound.
k04_alerts() {
  local n
  need "$BACKUP" 'reports a failed run' 'Backup' || return 1
  need "$BACKUP" 'a check that does not run on the server[^.]*alerts the IT department when the newest backup set is older than [0-9]+ hours' 'Backup' || return 1
  n="$(printf '%s\n' "$BACKUP" | grep -Eio 'newest backup set is older than [0-9]+ hours' | grep -Eo '[0-9]+' | head -n 1)"
  { [ "$n" -gt 24 ] && [ "$n" -lt 48 ]; } || { WHY="the freshness alert fires after $n hours; a daily backup needs a bound above 24 and below 48"; return 1; }
  control "With no new backup set for $n hours[^|]*alert from a check that does not run on the server" "the freshness alert at the same $n hours (C17)" || return 1
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

# The restore's step order (R-02, R-03, R-08 fixes; decisions A and C; C-3/G-4). Positions are the
# list positions, and the list must be numbered 1..n so a position is the step number the rest of
# the Decision cites.
RSTEPS="$(numbered "$RESTORE_P")"
rpos() { printf '%s\n' "$RSTEPS" | grep -Ein -- "$1" | head -n 1 | cut -d: -f1; }
rstep() { printf '%s\n' "$RSTEPS" | sed -n "${1}p"; }
# Fix round 2 (R-10, R-11): step 8 starts proxy with the admin listener and the public listener
# accepting the company network only; step 10 sets the Keycloak-stored secrets; step 14 opens the
# public listener to the internet. The step names below are matched by their opening words.
rs_fetch() { rpos '^[0-9]+\. Fetch the chosen backup set from the destination, the backup private key and the environment.s secrets'; }
rs_cnt() { rpos '^[0-9]+\. Compare the restored application tables. row counts with the manifest, before any migration runs; the restore goes on only when they are equal'; }
rs_adm() { rpos '^[0-9]+\. Start proxy with its admin listener on <auth-admin-host> and with the public listener closed to the internet'; }
rs_re() { rpos '^[0-9]+\. Through that console, re-apply every account change made after the backup.s time'; }
rs_sec() { rpos '^[0-9]+\. Through the same console, set the application client.s OIDC client secret'; }
rs_be() { rpos '^[0-9]+\. Start backend and frontend\.'; }
rs_open() { rpos '^[0-9]+\. Only then open the public listener to the internet'; }
k04_restore_order() {
  local pg db cnt kc adm re sec key mig be open n p name t
  printf '%s\n' "$RSTEPS" | awk '{ split($1, a, "."); if (a[1] + 0 != NR) exit 1 }' || { WHY="the restore steps are not numbered 1..n in order"; return 1; }
  n="$(printf '%s\n' "$RSTEPS" | grep -c .)"
  pg="$(rpos '^[0-9]+\. Start postgres alone, with no published port and proxy not started')"
  db="$(rpos '^[0-9]+\. Restore the application database and then Keycloak.s database')"
  cnt="$(rs_cnt)"
  kc="$(rpos '^[0-9]+\. Start keycloak')"
  adm="$(rs_adm)"
  re="$(rs_re)"
  sec="$(rs_sec)"
  key="$(rpos '^[0-9]+\. Replace the session-token encryption key with a newly generated value')"
  mig="$(rpos '^[0-9]+\. Run migrate')"
  be="$(rs_be)"
  open="$(rs_open)"
  for p in pg db cnt kc adm re sec key mig be open; do
    [ -n "${!p}" ] || { WHY="restore step missing: $p"; return 1; }
  done
  # name <a> <b> — step a comes before step b.
  before() { [ "${!1}" -lt "${!2}" ] || { WHY="restore step $1 (${!1}) is not before $2 (${!2})"; return 1; }; }
  before pg db && before db cnt && before cnt mig || return 1           # counts compared before migrate (R-08)
  before kc adm && before adm re && before adm sec || return 1           # the company-only proxy exists before the console work (R-03, R-10)
  before re open && before key be && before key open || return 1         # revocations and the new key before the public listener (R-02)
  before sec be && before sec open || return 1                           # Keycloak holds the secrets in effect before the test login (R-11)
  before mig be && before be open || return 1
  [ "$open" -eq "$n" ] || { WHY="opening the public listener to the internet is step $open, not the last step ($n)"; return 1; }
  # Before the opening step, proxy is started only at the company-only step, and no other step
  # names a listener except the test login through the company-only public listener. The first
  # version matched only "start(s) proxy" and "open(s) the public listener", so "Start keycloak and
  # proxy with both of its listeners" at step 7 passed (the Reviewer's paper break at be73027;
  # EKO-1-03-M113).
  for p in $(seq 1 $((open - 1))); do
    [ "$p" -ne "$adm" ] || continue
    t="$(rstep "$p" | sed -E 's/\bproxy (is |still |stays )?not (yet )?started( yet)?\b//g;s/through the public listener, which accepts connections only from there \(step [0-9]+\)/VIA-COMPANY-ONLY-PATH/')"
    if grep -Eiq '\bproxy\b|\bentry point\b|\bCaddy\b' <<< "$t"; then WHY="restore step $p starts or names proxy before the opening step, other than step $adm"; return 1; fi
    if grep -Eiq '\blisteners?\b|\bport (80|443)\b' <<< "$t"; then WHY="restore step $p names a listener other than through the company-only public listener"; return 1; fi
    if grep -Eiq '\bopen(s|ed|ing)?\b[^.]*\b(internet|public)\b|\b(internet|public)\b[^.]*\bopen(s|ed)?\b' <<< "$t"; then WHY="restore step $p opens something to the internet before step $open"; return 1; fi
  done
  # The company-only step itself does not start the public listener open.
  if rstep "$adm" | grep -Eiq '\bboth (of its )?listeners\b|\bopens? the public listener\b|\bpublic listener (is )?open(ed)?\b|\b(open|reachable|accepts connections) (to|from) (the internet|every network|any network|all networks)\b'; then WHY="restore step $adm starts the public listener open"; return 1; fi
  return 0
}
check 'the restore steps run in order: counts before migrate, the company-only proxy before the re-apply, revocations, Keycloak-stored secrets and a new session key before the public listener opens to the internet' k04_restore_order

# R-10 (fix round 2): from step 8 to the opening step the public listener accepts the company
# network only, so the test login runs through it; C18 and C25 state the same listener state.
k04_restore_company_only() {
  local adm be open cnt s
  adm="$(rs_adm)"; be="$(rs_be)"; open="$(rs_open)"; cnt="$(rs_cnt)"
  [ -n "$adm" ] && [ -n "$be" ] && [ -n "$open" ] && [ -n "$cnt" ] || { WHY="restore step missing: the company-only proxy, the test login, the opening or the count comparison"; return 1; }
  s="$(rstep "$adm")"
  need "$s" "closed to the internet: from this step until step $open, the public listener accepts connections only from the company network, as the admin listener does, and still refuses every request outside its allowlist" "restore step $adm" || return 1
  need "$s" 'The administration console, the application and Keycloak.s login pages are then reachable only from the company network' "restore step $adm" || return 1
  s="$(rstep "$be")"
  need "$s" "From the company network, through the public listener, which accepts connections only from there \\(step $adm\\), log in at https://<app-host> with a test account" "restore step $be" || return 1
  need "$s" "The restore is verified when the login works and the counts compared at step $cnt are equal" "restore step $be" || return 1
  need "$(rstep "$open")" '^[0-9]+\. Only then open the public listener to the internet, take a fresh backup, and record the restore' "restore step $open" || return 1
  control 'ends with a test login working from the company network while the public listener accepted no connection from the internet' 'the test login through the company-only listener (C18)' || return 1
  control 'for the time before the public listener was opened to the internet, while it accepted connections only from the company network' 'the listener state of the re-apply (C25)' || return 1
}
check 'during the restore the public listener accepts the company network only until the last step opens it to the internet' k04_restore_company_only

# R-11 (fix round 2): the restore sets the Keycloak-stored secrets from their master copies and
# re-applies break-glass and reviewer rotations from the record, which holds every such rotation.
k04_restore_keycloak_secrets() {
  local re sec open fetch s n row
  re="$(rs_re)"; sec="$(rs_sec)"; open="$(rs_open)"; fetch="$(rs_fetch)"
  [ -n "$re" ] && [ -n "$sec" ] && [ -n "$open" ] && [ -n "$fetch" ] || { WHY="restore step missing: the fetch, the re-apply, the Keycloak-stored secrets or the opening"; return 1; }
  need "$(rstep "$sec")" "Through the same console, set the application client.s OIDC client secret and, once the company mailbox exists, the application realm.s SMTP credentials to the values of their off-server master copies fetched in step $fetch, so that Keycloak holds the values in effect and not those of the backup.s time" "restore step $sec" || return 1
  s="$(rstep "$re")"
  need "$s" 'Also re-apply every rotation of a break-glass or reviewer credential the record holds, so that no value rotated out since the backup works again' "restore step $re" || return 1
  need "$s" 'the break-glass holder carrying out this step sets their own account.s password to the value in effect, and sets every other such account to a temporary password handed to its holder in person, which the holder replaces with the value in effect at their next login' "restore step $re" || return 1
  need "$s" 'The holder carrying out this step logs in with the credential the restored master realm holds for their account' "restore step $re" || return 1
  need "$(rstep "$open")" "the account changes and credential rotations re-applied, the Keycloak-stored secrets set at step $sec\\)" "restore step $open" || return 1
  need "$(sub_sents '^### Operator duties')" 'Every rotation of a break-glass or reviewer credential is entered in the same record when it is made \(the account and the time, never the value\)' 'Operator duties' || return 1
  for row in 'Master-realm break-glass admin credentials' "Reviewer.s read-only master-realm account credential"; do
    s="$(printf '%s\n' "$INVENTORY" | grep -Ei "^\\| $row \\|")"
    n="$(printf '%s\n' "$s" | grep -Eio 'every rotation is entered in the record of account changes and re-applied at restore step [0-9]+' | grep -Eo '[0-9]+$')"
    [ -n "$n" ] || { WHY="the inventory row '$row' does not enter its rotations in the record and re-apply them at a restore step"; return 1; }
    [ "$n" -eq "$re" ] || { WHY="the inventory row '$row' cites restore step $n for its rotations; the re-apply is step $re"; return 1; }
  done
  forbid "$DECISION_SENTS" '\b(client secret|SMTP credentials?|Keycloak-stored secrets?)\b[^.]*\b(kept|left|taken|used|restored) (as|from) (restored|the backup|the backup set|the restored database)\b' || return 1
  forbid "$DECISION_SENTS" '\b(rotation|rotations)\b[^.]*\b(break-glass|reviewer)\b[^.]*\b(need not be|is not|are not|never) (entered|recorded|re-applied)\b' || return 1
  forbid "$DECISION_SENTS" '\b(reads?|uses?|types?|learns?)\b[^.]*\b(another|other) holder.s (credential|password)\b' || return 1
  control 'the OIDC client secret and the SMTP credentials stored in Keycloak equal their off-server master copies; every rotation of a break-glass or reviewer credential recorded after the backup.s time is in effect, so the previous value is refused' 'the Keycloak-stored secrets and rotations (C25)' || return 1
}
check 'the restore sets the Keycloak-stored secrets from their master copies and re-applies break-glass and reviewer rotations' k04_restore_keycloak_secrets

k04_restore_reapply() {
  local re key
  re="$(rstep "$(rpos '^[0-9]+\. Through that console, re-apply')")"
  key="$(rstep "$(rpos '^[0-9]+\. Replace the session-token encryption key')")"
  [ -n "$re" ] || { WHY="no restore step re-applies the account changes"; return 1; }
  need "$re" 'that the IT department.s off-server record of account changes holds' 'the re-apply step' || return 1
  need "$re" 'every deactivation and role removal, so that no account disabled since the backup is active again' 'the re-apply step' || return 1
  need "$re" 'every password reset, by disabling the account until its user receives a new temporary password under ADR-0003.s reset rule' 'the re-apply step' || return 1
  need "$re" 'sign out every session that the restored Keycloak database holds, in the application realm and in the master realm' 'the re-apply step' || return 1
  need "$key" 'in the off-server master copy and in the backend environment file, so that no session restored in the application database can be decrypted' 'the session-key step' || return 1
  need "$(sub_sents '^### Operator duties')" 'or sets a temporary password tells the IT department at the time, through IT.s own request system, which is not on this server' 'Operator duties' || return 1
  control 'every deactivation and role removal recorded after the backup.s time is in effect in the restored realm; every account with a password reset recorded after that time is disabled or has received a new temporary password; no user session of either realm restored from the backup set is still active; and the session-token encryption key in use differs' 'the restore re-apply (C25)' || return 1
}
check 'the restore re-applies deactivations, role removals and password resets, signs out every session of both realms and replaces the session-token key' k04_restore_reapply

# Every "restore step <n>" the Decision cites is the step it means.
k04_restore_refs() {
  local n s
  while IFS= read -r n; do
    [ -n "$n" ] || continue
    [ -n "$(rstep "$n")" ] || { WHY="the Decision cites restore step $n, which does not exist"; return 1; }
  done < <(printf '%s\n' "$DECISION_SENTS" | grep -Eio 'restore step [0-9]+' | grep -Eo '[0-9]+' | sort -u)
  n="$(printf '%s\n' "$DECISION_SENTS" | grep -Eio 'off-server record is what restore step [0-9]+' | grep -Eo '[0-9]+$' | head -n 1)"
  [ -n "$n" ] || { WHY="Operator duties does not name the restore step that re-applies its record"; return 1; }
  rstep "$n" | grep -Eiq 're-apply every account change' || { WHY="Operator duties cites restore step $n for the re-apply, which is: $(rstep "$n" | cut -c1-80)"; return 1; }
  n="$(printf '%s\n' "$INVENTORY" | grep -Ei '^\| Backup encryption private key' | grep -Eio 'restore step [0-9]+' | grep -Eo '[0-9]+' | head -n 1)"
  [ -n "$n" ] || { WHY="the private-key row names no restore step"; return 1; }
  rstep "$n" | grep -Eiq 'backup private key' || { WHY="the private-key row cites restore step $n, which does not fetch the private key"; return 1; }
}
check 'every restore step the Decision cites is the step it means' k04_restore_refs

# B-08 (fix round 2): every host receiving the private key or a decrypted set, the verification
# host included, meets the restore-host requirements.
k04_restore_host() {
  need "$RESTORE" '^Restore-host requirements\.$' 'Restore procedure' || return 1
  need "$RESTORE" '^Every host that receives the backup private key or a decrypted backup set, the restore host and the host of the monthly verification \(\*?Backup\*?\) alike, is held by the company, has its disk encrypted, and is not used for e-mail or web browsing\.$' 'Restore procedure' || return 1
  need "$BACKUP" '^The host of the check meets the restore-host requirements \(\*?Restore procedure\*?\)\.$' 'Backup' || return 1
  need "$(rstep 1)" '^1\. Provide a host that meets the restore-host requirements' 'restore step 1' || return 1
  need "$(printf '%s\n' "$INVENTORY" | grep -Ei '^\| Backup encryption private key')" 'brought only to the restore host at restore step 2 and to the off-server host of the backup verification \(\*?Backup\*?\), both meeting the restore-host requirements' 'the private-key row' || return 1
  forbid "$DECISION_SENTS" '\b(verification|the check)\b[^.]*\b(any|a personal|an? (IT )?(laptop|workstation|own))\b[^.]*\bhost\b|\b(host|laptop|workstation)\b[^.]*\b(need not|does not need to|is not required to) meet\b' || return 1
  forbid "$DECISION_SENTS" '\bexcept (the|for the) (host of the|verification)|\brestore-host requirements\b[^.]*\b(do not|does not|need not) apply\b' || return 1
  control 'each check on a host meeting the restore-host requirements' 'the verification host (C27)' || return 1
}
check 'every host receiving the backup private key or a decrypted set meets the restore-host requirements' k04_restore_host

k04_counts() {
  need "$BACKUP" 'row count of each application table, counted inside the dump.s own snapshot' 'Backup' || return 1
  control 'row counts matching the manifest when compared before migrate runs' 'the count comparison (C18)' || return 1
}
check 'the manifest counts are the dump snapshot.s and are compared before migrate' k04_counts

# R-15 (fix round 2): the backup role's connection limit covers every session a backup holds at the
# same time; "greater than zero" (a limit of 1, with which every run fails) is gone, and C19 runs a
# nightly backup with that limit.
k04_backup_conn_limit() {
  need "$(sub_sents '^### Composition and placement')" 'The backup service connects with its own database role, which also carries a connection limit of at least the number of sessions a backup holds at the same time \(the session holding the advisory lock, the pg_dump session, and the session counting rows inside the dump.s snapshot, wherever these are separate sessions\)' 'Composition and placement' || return 1
  forbid "$DECISION_SENTS" '\bbackup\b[^.]*\bconnection limit (greater than zero|above zero|of (at least )?(one|1)|of one session)\b|\bconnection limit\b[^.]*\bbackup\b[^.]*\b(greater than zero|of (at least )?(one|1)\b)' || return 1
  forbid "$CONTROLS" 'backup role has a connection limit (greater than zero|of (at least )?(one|1)\b)' || return 1
  control 'the backup role has a connection limit of at least the number of sessions a backup holds at the same time \(the advisory-lock session, the pg_dump session and the row-count session, wherever these are separate\), a nightly backup run with that limit completes' 'the backup role.s limit (C19)' || return 1
}
check "the backup role's connection limit covers the sessions a backup holds at the same time" k04_backup_conn_limit

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
  grep -Fxq -- "$1" <<< "$DECISION_HEADINGS" || { WHY="'$1' is not a heading of ADR-0004's Decision"; return 1; }
  if [ -n "${2:-}" ]; then
    local re; re="$(printf '%s' "$1" | sed -E 's/[][\\.*^$+?(){}|/]/\\&/g')"
    # Collected first, then matched: "sub_text | paras | grep -q" fails by SIGPIPE under pipefail
    # on Linux whenever paras is still writing after grep's first match (see has).
    local t; t="$(sub_text "^###+ $re\$" | paras)"
    has "$t" "$2" || { WHY="section '$1' does not mention /$2/"; return 1; }
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
      if grep -Eq 'forwarded on to EKO-[0-9]+-[0-9]+ \(#[0-9]+\)' <<< "$e"; then
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
    grep -Eq '^(decided in \*[^*]+\*|(forwarded on to )?EKO-[0-9]+-[0-9]+ \(#[0-9]+\))' <<< "$tail" \
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
    grep -Eq '^- (EKO-[0-9]+-[0-9]+ \(#[0-9]+\)|Not decided)' <<< "$e" || { WHY="forward reference names no task as EKO-x-yy (#n): $(printf '%s' "$e" | cut -c1-120)"; return 1; }
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
  # Decisions G and H: the same weekly sentence reads the master realm's events and compares the
  # live role holders with the approved assignments.
  has "$s" 'admin events and the master realm.s login and admin events' || { WHY="the reviewer sentence does not read the master realm's login and admin events"; return 1; }
  has "$s" 'compares the live holders of administrator, manager and rep with the IT department.s record of approved assignments' || { WHY="the reviewer sentence does not compare the live role holders with the approved assignments"; return 1; }
}
check 'the reviewer is named by function and reviews at a stated number of days' k06_reviewer_frequency

# Decision H (B-02): the master realm stores its login and admin events, turned on at bootstrap.
k06_master_events() {
  need "$DUTIES" 'The master realm stores login events and admin events, so every login with a break-glass credential and every change made with one is a stored event the reviewer reads' 'Operator duties' || return 1
  need "$(numbered "$(sub_paras '^### Bootstrap of the first administrator')")" 'turns on the master realm.s login events, admin events and brute-force detection' 'the bootstrap steps' || return 1
  forbid "$DECISION_SENTS" '\bmaster realm\b[^.]*\b(does not store|stores no|need not store|without)\b[^.]*\bevents\b' || return 1
  control 'In the live master realm: login events and admin events are stored' 'the master-realm events (C23)' || return 1
  control 'reads the application realm.s admin events, the master realm.s login and admin events' 'the reviewer reading master-realm events (C24)' || return 1
}
check "the master realm stores login and admin events and the reviewer reads them" k06_master_events

# Decision G (B-01): the approver rule and the reviewer's separation from the runtime and the database.
k06_approver() {
  need "$DUTIES" 'an assignment is entered there, with who approved it, before it is made' 'Operator duties' || return 1
  need "$DUTIES" 'An assignment of administrator, manager or rep is approved by the company management \(a person the business owner names\) and carried out by an administrator; the approver is never the administrator who makes the change' 'Operator duties' || return 1
  forbid "$DECISION_SENTS" '\bapprov(er|es|ed|al)\b[^.]*\b(may|can|is allowed to)\b[^.]*\b(be|also be)\b[^.]*\badministrator who\b' || return 1
  forbid "$DECISION_SENTS" '\b(administrators?|an administrator)\b[^.]*\bapproves? (its|their|his|her) own\b' || return 1
  # B-01 (fix round 2): the approver enters the approval, and the assignment waits for it.
  need "$DUTIES" 'The approver enters the approval in the request record personally, never the administrator who makes the change, and the administrator makes the assignment only once that approval is there' 'Operator duties' || return 1
  # An assignment made first and approved afterwards, on any condition (the Reviewer's paper break
  # at be73027: "In an emergency an administrator may assign a role first and enter the approval
  # afterwards."; EKO-1-03-M114), and an approval entered by the administrator.
  forbid "$DECISION_SENTS" '\b(assign(s|ed|ment|ments)?|approv(al|als|ed|es|er))\b[^.]*\b(afterwards|retroactively|after the (fact|assignment|change)|later|subsequently|once (it|the role) is (made|assigned))\b' || return 1
  forbid "$DECISION_SENTS" '\bassign\w*\b[^.]*\bfirst\b[^.]*\bapprov\w*' || return 1
  forbid "$(printf '%s\n' "$DECISION_SENTS" | sed -E 's/^The approver enters the approval in the request record personally, never the administrator who makes the change, and the administrator makes the assignment only once that approval is there\.$/APPROVER-ENTERS-SENTENCE/')" '\badministrators?\b[^.]*\b(enters?|records?|writes?|types?|files?|logs?) (the|an|its|their) approval\b' || return 1
  control 'recorded a comparison of the live holders of administrator, manager and rep with the record of approved assignments, in which every assignment names an approver from the company management who is not the administrator who made it, and whose approval that approver entered in the request record' 'the assignment comparison and the approver entering the approval (C22)' || return 1
}
check 'role assignments are approved by the company management, never by the administrator who makes them, and compared weekly' k06_approver

k06_reviewer_no_runtime() {
  need "$DUTIES" 'The reviewer holds no administrative rights over the container runtime and no PostgreSQL superuser access, and has no access to the PostgreSQL superuser password or to any database role password' 'Operator duties' || return 1
  need "$(sub_sents '^### Secret handling')" 'those rights are held only by the IT department, never by the reviewer' 'Secret handling' || return 1
  forbid "$DECISION_SENTS" '\breviewer\b[^.]*\b(may|can|also)\b[^.]*\b(hold|have|has|access|run|use)\b[^.]*\b(container runtime|docker|superuser|database role password)' || return 1
  control 'nor administrative rights over the container runtime, PostgreSQL superuser access, the PostgreSQL superuser password or a database role password' 'the reviewer without runtime or superuser access (C22)' || return 1
}
check 'the reviewer holds no container-runtime rights, no PostgreSQL superuser access and no database password' k06_reviewer_no_runtime

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

# R-14 (fix round 2): the master realm is configured from inside the keycloak container before
# proxy starts, so brute-force detection is on before the admin listener exists (C8).
k06_bootstrap_inside() {
  local b s pos p
  b="$(numbered "$(sub_paras '^### Bootstrap of the first administrator')")"
  pos="$(printf '%s\n' "$b" | grep -Ein 'turns on the master realm.s login events, admin events and brute-force detection' | head -n 1 | cut -d: -f1)"
  [ -n "$pos" ] || { WHY="no bootstrap step turns on the master realm's events and brute-force detection"; return 1; }
  s="$(printf '%s\n' "$b" | sed -n "${pos}p")"
  need "$s" '^[0-9]+\. Before proxy is started, and so with neither listener running, the IT department works from inside the keycloak container \(for example kcadm\.sh against Keycloak.s internal port, through docker exec\)' 'the bootstrap step configuring the master realm' || return 1
  need "$s" 'Only then is proxy started\.$' 'the bootstrap step configuring the master realm' || return 1
  forbid "$s" '\b(administration console|admin console|admin listener|public listener|through proxy|over HTTPS)\b|<auth-admin-host>' || return 1
  for p in $(seq 1 $((pos - 1))); do
    if printf '%s\n' "$b" | sed -n "${p}p" | sed -E 's/\bproxy (is |still |stays )?not (yet )?started( yet)?\b//g' | grep -Eiq '\bproxy\b|\blisteners?\b|<auth-admin-host>|\b(administration|admin) console\b'; then WHY="bootstrap step $p, before the master realm is configured, starts or uses proxy or the console"; return 1; fi
  done
  forbid "$DECISION_SENTS" '\bbootstrap\b[^.]*\b(through|on|via) (the )?((administration console|admin console)\b|<auth-admin-host>)' || return 1
}
check 'bootstrap configures the master realm from inside the keycloak container before proxy starts' k06_bootstrap_inside

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
  # A second deviation named in the same sentence as C19 (the Reviewer's paper break of the first
  # version, whose excuse covered the whole line): no other rule or decision is named in a
  # deviation sentence, and no word counts more than one.
  local other; other="$(printf '%s\n' "$dev" | grep -Eo 'ADR-[0-9]{4}(-C[0-9]+)?' | sort -u | grep -Fxv -e 'ADR-0003' -e 'ADR-0003-C19')"
  [ -z "$other" ] || { WHY="a deviation sentence also names $(printf '%s' "$other" | tr '\n' ' ')"; return 1; }
  forbid "$dev" '\b(deviations|addenda|second|another|further|additional|other|two|both|also|as well)\b' || return 1
  forbid "$dev" '\b(new-account|first (temporary )?password|hand-?over|reset|retention|backup frequency|runtime)\b' || return 1
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
  grep -Fxq 'adr-deviation' <<< "$labels" || { WHY="Issue #16 has no adr-deviation label"; return 1; }
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
