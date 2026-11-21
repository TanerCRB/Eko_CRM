#!/usr/bin/env bash
# EKO-1-01 — document checks for the stack and persistence decisions (ADR-0001, ADR-0002),
# criteria K-01..K-07 of Issue #6, proven by this file instead of by QA scratch scripts (EKO-1-37).
#
#   bash tests/doc-checks/EKO-1-01.sh                        # judge the pinned EKO-1-01 commits
#   bash tests/doc-checks/EKO-1-01.sh --head <rev>           # judge another head (QA's throwaway commits)
#   bash tests/doc-checks/EKO-1-01.sh --base <rev> [...]     # another base than the pinned one
#   bash tests/doc-checks/EKO-1-01.sh --merge <rev> [...]    # another merge commit for the date bound
#
# What is read. Every document is read from a commit, never from the working tree, HEAD or
# origin/main: ADR-0001/0002 and both registers have changed in later tasks, so #6's literal claims
# (no ADR-0003..0006, "byte-identical capabilities.md", ...) are true only of the commits EKO-1-01
# merged. The default run judges
#   base  34c9071561e9929befc5b664e5b952ec7fc3fa40  the commit the task branched from
#   head  8398cfcfd22f50f09ea1f963ccc63c861da36068  the last commit of the task branch
#   merge adbb152b244a2a88aa543364cb5c28d9cd63d276  PR #30's merge commit (its second parent is head)
# PR #30's proof was "Verified at 90af4f9"; `git diff --name-only 90af4f9 8398cfc` names only three
# docs/cost-register files, so neither an ADR nor a register differs between the verified commit
# and the merged head, and the checks judge what merged.
#
# Output. One line per sub-check, "ok   <label> — <detail>" or "FAIL <label> — <detail>: <why>". The
# label is the name PR #30's "K-n — test:" line quotes; several sub-checks of one criterion share
# its label. The seven labels are the L01..L07 constants below, and the last block fails any label
# that printed no "ok" line, so a name kept only in a comment proves nothing.
# There is no "skip": every check runs on every run, and the summary always reports 0 skipped.
# Exit codes: 0 = every check passed, 1 = at least one failed, 2 = the script could not run (a bad
# argument or revision, a pinned commit that is absent, as in a depth-1 clone, or today's
# risk-check.sh / layer-check.sh unable to read the registers of the pinned commits) — never read 2
# as a pass.
# Helper scripts (#226 K-03). Before any check, today's layer-check.sh and risk-check.sh are run over
# the 2026-10-23 registers, read from the pinned base and head; an exit 2 there is tooling that can
# no longer parse that format, and the run exits 2. Once that holds, a helper exit 2 on a register
# of another --head or --base is that register's damage (e.g. a deleted cell separator), reported
# as a FAIL of the sub-check that ran the helper, next to the script's own predicates (K-05-4, ...).
#
# Non-default head (--head). The documents, the changed files (K-07) and the history base..head
# (K-04) come from that head. K-04(3) judges that history generically — for each ADR, the commit
# adding it must read as a Draft, and every commit where an Accepted status first appears must be
# a single-parent commit changing only status lines — so it holds for histories QA rebuilds with
# other commit ids; the pinned draft and acceptance commits of PR #30 are additionally checked as
# the facts they are. The upper date bound of K-04(2) stays the committer date of the pinned merge
# commit unless --merge names another one; the lower bound is the committer date of the first
# commit in base..head that adds the ADR. K-06-new compares against the register at the pinned
# head, whatever --head is.
#
# K-04 "granted by the human" is human-judged (#6 K-04, #226 K-05): nothing here reads an author or
# a committer identity, because every commit runs on the human's account.
#
# What these checks are: line, sentence and table matching over prose, and runs of today's
# layer-check.sh and risk-check.sh over registers read from commits. They prove that a statement is
# present or absent in the decisions, not that it is true of a running system.

set -uo pipefail

PIN_BASE=34c9071561e9929befc5b664e5b952ec7fc3fa40
PIN_HEAD=8398cfcfd22f50f09ea1f963ccc63c861da36068
PIN_MERGE=adbb152b244a2a88aa543364cb5c28d9cd63d276
# The Architect's three drafts and the three commits that accepted them, as PR #30 records them.
PIN_DRAFTS=(5be8eade708106c41d429454ce04c3ceb132a3a8 6bc18a7314f1650dc6eda508e5c282d0227c771b b9c5052d10d10da25a3337429bed8962e1e58486)
PIN_ACCEPTS=(a8c269be51732fcae2bb9820a6f698bed35e040d 364c65c32cf94c35af9d7b737a82d982eb83d09c b6e442e95b0d7492fe102358b1090fc33fcd8a63)

L01='QA document check K-01 (closed list over ADR-0001 Decision)'
L02='QA document check K-02 (closed list over ADR-0002 Decision)'
L03='QA document check K-03 (template sections, options, controls)'
L04='QA document checks K-04(1), K-04-2, K-04(3)'
L05='QA document checks K-05(1)(2)(3)(5), K-05-4, K-05-4f, K-05-fe'
L06='QA document checks K-06(1), K-06(2), K-06-new'
L07='QA document check K-07 (git diff scope, capabilities.md unchanged)'

die() { echo "EKO-1-01 doc-checks: $* — the checks did not run" >&2; exit 2; }

BASE="$PIN_BASE"; HEAD_REV="$PIN_HEAD"; MERGE="$PIN_MERGE"
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || die "--base needs a rev"; BASE="$2"; shift 2 ;;
    --head) [ $# -ge 2 ] || die "--head needs a rev"; HEAD_REV="$2"; shift 2 ;;
    --merge) [ $# -ge 2 ] || die "--merge needs a rev"; MERGE="$2"; shift 2 ;;
    *) die "unknown argument '$1' (usage: $0 [--base <rev>] [--head <rev>] [--merge <rev>])" ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || die "cannot enter the repository root"
cd "$REPO" || die "cannot enter the repository root"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git repository"

# The pinned commits must exist; a missing one is named, never skipped over.
pinned() { git cat-file -e "$1^{commit}" 2>/dev/null || die "pinned commit $1 ($2) is not in this repository"; }
pinned "$PIN_BASE" "EKO-1-01 base"
pinned "$PIN_HEAD" "EKO-1-01 merged head"
pinned "$PIN_MERGE" "PR #30 merge commit"
for i in 0 1 2; do
  pinned "${PIN_DRAFTS[$i]}" "Architect draft $((i + 1))"
  pinned "${PIN_ACCEPTS[$i]}" "acceptance commit $((i + 1))"
done
[ "$(git rev-parse "$PIN_MERGE^2" 2>/dev/null)" = "$PIN_HEAD" ] || die "pinned merge commit $PIN_MERGE does not have $PIN_HEAD as its second parent"

# resolve <variable> <what> — the variable's revision as a full commit id; runs in this shell, not in
# $(...), so a bad revision exits 2 here instead of leaving the variable empty.
resolve() {
  local id
  id="$(git rev-parse --verify --quiet "${!1}^{commit}" 2>/dev/null)" && [ -n "$id" ] || die "$2 '${!1}' is not a commit in this repository"
  printf -v "$1" '%s' "$id"
}
resolve BASE base; resolve HEAD_REV head; resolve MERGE merge
git merge-base --is-ancestor "$BASE" "$HEAD_REV" || die "base $BASE is not an ancestor of head $HEAD_REV"
SCRIPTS="$REPO/scripts"
for f in risk-check.sh layer-check.sh; do [ -r "$SCRIPTS/$f" ] || die "cannot read scripts/$f"; done

TMP="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$TMP"' EXIT

DECISIONS="docs/architecture/decisions"
ADR1_PATH="$DECISIONS/ADR-0001-application-stack.md"
ADR2_PATH="$DECISIONS/ADR-0002-database-and-migrations.md"
LAYERS="docs/architecture/layer-dependencies.md"
PATHS="docs/architecture/architecture-sensitive-paths.md"
CAPS="docs/architecture/capabilities.md"

# ---- reading -------------------------------------------------------------------------------

# doc <rev> <path> — the file at that commit, without carriage returns.
doc() { git show "$1:$2" 2>/dev/null | tr -d '\r'; }

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

ADR1="$(doc "$HEAD_REV" "$ADR1_PATH")"
ADR2="$(doc "$HEAD_REV" "$ADR2_PATH")"
ADR1_P="$(printf '%s\n' "$ADR1" | paras)"
ADR2_P="$(printf '%s\n' "$ADR2" | paras)"
ADR1_DEC_P="$(printf '%s\n' "$ADR1" | section '^## Decision' | paras)"
ADR2_DEC_P="$(printf '%s\n' "$ADR2" | section '^## Decision' | paras)"

# ---- today's helpers can read the pinned registers ------------------------------------------

# Only exit 2 ("cannot run") stops here; a finding (exit 1) on the pinned registers is left to K-05(5).
preflight() {
  local out code f mode
  doc "$PIN_HEAD" "$LAYERS" > "$TMP/pin-layers-head.md"
  doc "$PIN_BASE" "$PATHS" > "$TMP/pin-paths-base.md"
  doc "$PIN_HEAD" "$PATHS" > "$TMP/pin-paths-head.md"
  out="$(bash "$SCRIPTS/layer-check.sh" --register "$TMP/pin-layers-head.md" "$PIN_BASE" "$PIN_HEAD" 2>&1)"; code=$?
  [ "$code" -ne 2 ] || die "scripts/layer-check.sh exited 2 on the layer register of pinned head $PIN_HEAD, so today's tool cannot read the 2026-10-23 format: $(printf '%s' "$out" | tail -n 1 | cut -c1-140)"
  for f in pin-paths-base.md pin-paths-head.md; do
    for mode in classes explain; do
      out="$(bash "$SCRIPTS/risk-check.sh" --register "$TMP/$f" "$mode" --paths - <<< 'backend/app/api/sample.py' 2>&1)"; code=$?
      [ "$code" -ne 2 ] || die "scripts/risk-check.sh $mode exited 2 on the sensitive-paths register $f, so today's tool cannot read the 2026-10-23 format: $(printf '%s' "$out" | tail -n 1 | cut -c1-140)"
    done
  done
}
preflight

# ---- the check runner ----------------------------------------------------------------------

passed=0; failed=0; skipped=0
WHY=""
OKS=""
# check <label> <detail> <function> [args] — the function sets WHY and returns non-zero on a failure.
check() {
  local label="$1" detail="$2"; shift 2
  WHY=""
  if "$@"; then
    echo "ok   $label — $detail"; passed=$((passed + 1)); OKS="$OKS"$'\n'"$label"
  else
    echo "FAIL $label — $detail: ${WHY:-check failed}"; failed=$((failed + 1))
  fi
}
# A grep -q never reads from a pipe here: it exits on the first match, the writer then dies of
# SIGPIPE, and pipefail turns a match into a miss (Q-01). It reads a here-string or a file instead.
# has <text> <ERE> — case-insensitive match; hasc — case-sensitive.
has() { grep -Eiq -- "$2" <<< "$1"; }
hasc() { grep -Eq -- "$2" <<< "$1"; }
# sel_has <text> <line ERE> <ERE> — some line matching the first ERE also matches the second (no case).
sel_has() { local sel; sel="$(grep -E -- "$2" <<< "$1")"; grep -Eiq -- "$3" <<< "$sel"; }
need() { has "$1" "$2" || { WHY="missing: /$2/"; return 1; }; }
# forbid <text> <ERE> [case-sensitive] — fails when a line of the text matches.
forbid() {
  local hits
  if [ "${3:-}" = cs ]; then hits="$(printf '%s\n' "$1" | grep -E -- "$2" | head -n 1)"
  else hits="$(printf '%s\n' "$1" | grep -Ei -- "$2" | head -n 1)"; fi
  [ -z "$hits" ] || { WHY="forbidden statement: $(printf '%s' "$hits" | cut -c1-160)"; return 1; }
}
# part <text> <heading regex> — a non-empty sub-section of a text, or a failure naming it.
part() {
  PART="$(printf '%s\n' "$1" | section "$2" | paras)"
  [ -n "$PART" ] || { WHY="no section matching /$2/ in the Decision"; return 1; }
}
# row_cell <paras text> <first cell regex> <cell number> — a cell of the first matching table row.
row_cell() {
  printf '%s\n' "$1" | grep -E "^[|] *$2 *[|]" | head -n 1 \
    | awk -F'|' -v c="$3" '{ v = $c; gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); print v }'
}
# norm_list "<a, b>" — a comma list as sorted, comma-joined names; the dash for "none" is dropped.
norm_list() {
  printf '%s\n' "$1" | tr ',' '\n' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/`//g' \
    | grep -v '^$' | grep -vx '—' | sort | paste -sd, -
}

# ==== K-01 ===================================================================================

k01_a_stack() {
  local r
  for r in 'Backend language and runtime [|] Python 3\.12' 'Backend web framework [|] FastAPI' \
           'Frontend language [|] TypeScript' 'Frontend UI library [|] React' \
           'Frontend build tool [|] Vite' 'Frontend package manager [|] pnpm'; do
    need "$ADR1_DEC_P" "$r" || return 1
  done
  need "$ADR1_DEC_P" 'matches the stack named in CLAUDE\.md' || return 1
}
check "$L01" "(a) Decision names the backend and frontend stack and its relation to CLAUDE.md" k01_a_stack

k01_b_container() {
  local s; part "$ADR1_DEC_P" '^### Constraint [0-9]+[^a-z]+every component runs as a container image' || return 1; s="$PART"
  need "$s" 'no component depends on a runtime installed on the host' || return 1
  need "$s" 'The stack meets this as follows' || return 1
  need "$s" 'not decided here' || return 1
  forbid "$ADR1_P" '(may|might|could|should) run in (a )?container'
}
check "$L01" "(b) container-image constraint stated in the Decision, with how the stack meets it" k01_b_container

k01_c_identity() {
  local s; part "$ADR1_DEC_P" '^### Constraint [0-9]+[^a-z]+authentication is delegated to an external identity server' || return 1; s="$PART"
  need "$s" 'no password store of its own' || return 1
  need "$s" 'delegated to an external identity server' || return 1
  need "$s" 'OpenID Connect' || return 1
  need "$s" 'verified on every request by one application-wide FastAPI dependency' || return 1
  need "$s" 'Not decided here' || return 1
  forbid "$ADR1_P" 'application (keeps|stores|has) (a |its own )?(password|password store)'
}
check "$L01" "(c) no password store, delegation to an external identity server over OpenID Connect" k01_c_identity

k01_c_not_open() {
  local heads
  heads="$(printf '%s\n' "$ADR1" | grep -E '^#{1,6} ' | grep -Ei 'open questions?|unresolved|to be decided')"
  [ -z "$heads" ] || { WHY="a section for open questions: $(printf '%s' "$heads" | head -n 1)"; return 1; }
}
check "$L01" "(b)(c) the constraints are not parked under open questions" k01_c_not_open

k01_d_layering() {
  local r
  for r in '| domain | services, data, api, integrations |' '| services | api |' '| data | services, api, integrations |' \
           '| integrations | services, data, api |' '| core | domain, services, data, api, integrations |' '| api | — |'; do
    grep -Fxq -- "$r" <<< "$ADR1_DEC_P" || { WHY="the layer rules table lacks the row: $r"; return 1; }
  done
  need "$ADR1_DEC_P" 'keep every rule of the provisional table' || return 1
}
check "$L01" "(d) backend layering fixed: the six layer rules and their relation to the provisional table" k01_d_layering

k01_e_forward() {
  local fw r hit
  part "$ADR1_DEC_P" '^### Forward references' || return 1; fw="$PART"
  sel_has "$fw" '^- ADR-0003' 'identity server product' || { WHY="no forward reference to ADR-0003 for the identity server product"; return 1; }
  sel_has "$fw" '^- ADR-0004' 'container runtime' || { WHY="no forward reference to ADR-0004 for the container runtime"; return 1; }
  sel_has "$fw" '^- ADR-0004' 'backup' || { WHY="no forward reference to ADR-0004 for backup"; return 1; }
  sel_has "$fw" '^- ADR-0005' 'personal data' || { WHY="no forward reference to ADR-0005 for personal data"; return 1; }
  sel_has "$fw" '^- ADR-0006' 'Google Calendar' || { WHY="no forward reference to ADR-0006 for Google Calendar"; return 1; }
  # A topic named outside a forward reference must still cite the decision that owns it.
  for r in 'Google Calendar' 'backup' 'personal.data'; do
    hit="$(grep -Ei -- "$r" <<< "$ADR1_P" | grep -Ev 'ADR-000[3-6]' | head -n 1)"
    [ -z "$hit" ] || { WHY="a paragraph names '$r' without citing ADR-0003..0006: $(cut -c1-120 <<< "$hit")"; return 1; }
  done
}
check "$L01" "(e) identity server, container runtime, backup, personal data, Google Calendar only as forward references" k01_e_forward

k01_e_no_product() {
  forbid "$ADR1_P" '\b(Keycloak|Authentik|Authelia|Zitadel|Okta|Auth0|FusionAuth|Casdoor|Gluu|Ory Hydra|Kratos)\b' || return 1
  forbid "$ADR1_P" '\b(Docker Engine|Docker Compose|docker-compose|Podman|Kubernetes|k3s|containerd|Nomad|Swarm)\b' || return 1
  forbid "$ADR1_P" '\b(pg_dump|pgBackRest|WAL-G|Barman|restic)\b' || return 1
  forbid "$ADR1_P" 'identity server (product )?(is|will be|:) *[A-Z]' cs
}
check "$L01" "(e) no identity server product, container runtime or backup tool is named" k01_e_no_product

# ==== K-02 ===================================================================================

k02_name_of() { printf '%s\n' "$1" | sed -E 's/[,;(].*//; s/^[[:space:]]+//; s/[[:space:]]+$//'; }

k02_a_one_each() {
  local engine tool en tn chosen what
  engine="$(row_cell "$ADR2_DEC_P" 'Database engine' 3)"
  tool="$(row_cell "$ADR2_DEC_P" 'Migration tool' 3)"
  [ -n "$engine" ] || { WHY="no 'Database engine' row in the Decision"; return 1; }
  [ -n "$tool" ] || { WHY="no 'Migration tool' row in the Decision"; return 1; }
  en="$(k02_name_of "$engine")"; tn="$(k02_name_of "$tool")"
  for what in "$en" "$tn"; do
    if has "$what" '( or |/|TBD|later|undecided|either|to be decided)'; then WHY="not one choice: '$what'"; return 1; fi
    [ -n "$what" ] || { WHY="an empty choice cell"; return 1; }
  done
  chosen="$(printf '%s\n' "$ADR2_P" | grep -E '^[|] .*\(chosen\)' | head -n 1)"
  [ -n "$chosen" ] || { WHY="no option marked (chosen) in Options considered"; return 1; }
  has "$chosen" "$en" || { WHY="the chosen option does not name the engine '$en'"; return 1; }
  has "$chosen" "$tn" || { WHY="the chosen option does not name the migration tool '$tn'"; return 1; }
  forbid "$ADR2_DEC_P" '\b(MariaDB|MySQL|SQLite|Flyway|Sqitch|Liquibase|MongoDB|SQL Server)\b'
}
check "$L02" "(a) exactly one engine and one migration tool in the Decision, matching the chosen option" k02_a_one_each

k02_b_on_prem() {
  need "$ADR2_DEC_P" 'run from a container image' || return 1
  need "$ADR2_DEC_P" 'On-premises, no cloud vendor' || return 1
  need "$ADR2_DEC_P" 'runs as an ordinary container on the company.s server' || return 1
  need "$ADR2_DEC_P" 'nothing in this decision depends on a managed database service' || return 1
  forbid "$ADR2_DEC_P" '\b(AWS|Azure|Google Cloud|GCP|Amazon RDS|Cloud SQL|Aurora|Supabase)\b' || return 1
  local hit; hit="$(grep -Ei 'managed' <<< "$ADR2_DEC_P" | grep -Eiv '(nothing|not assumed|no managed|stays possible)' | head -n 1)"
  [ -z "$hit" ] || { WHY="a managed-service statement: $(cut -c1-120 <<< "$hit")"; return 1; }
}
check "$L02" "(b) container, on-premises, not tied to one cloud vendor" k02_b_on_prem

k02_c_migrations() {
  need "$ADR2_DEC_P" 'Versioned migrations' || return 1
  need "$ADR2_DEC_P" 'Every schema change is an Alembic revision' || return 1
  need "$ADR2_DEC_P" 'alembic upgrade head brings an empty database to the current schema' || return 1
}
check "$L02" "(c) versioned migrations bring an empty database to the current schema" k02_c_migrations

k02_d_time_text() {
  need "$ADR2_DEC_P" 'timestamp with time zone' || return 1
  need "$ADR2_DEC_P" 'Europe/Warsaw' || return 1
  need "$ADR2_DEC_P" 'half-open range of instants' || return 1
  need "$ADR2_DEC_P" '23-hour or 25-hour DST day' || return 1
  need "$ADR2_DEC_P" 'one injected clock' || return 1
  need "$ADR2_DEC_P" 'ICU provider with locale pl-PL' || return 1
  need "$ADR2_DEC_P" 'Unicode NFC' || return 1
  need "$ADR2_DEC_P" 'Case-insensitive equality does not depend on the ICU collation' || return 1
  need "$ADR2_DEC_P" '_match_key' || return 1
  need "$ADR2_DEC_P" 'unique constraint in the database on nip' || return 1
  need "$ADR2_P" 'CUS-6' || return 1
  need "$ADR2_P" 'CUS-7' || return 1
  need "$ADR2_P" 'EKO-4-01' || return 1
}
check "$L02" "(d) points in time, Europe/Warsaw days and DST, Polish text, case-insensitive match and NIP uniqueness" k02_d_time_text

k02_e_forward() {
  local fw hit
  part "$ADR2_DEC_P" '^### Forward references' || return 1; fw="$PART"
  sel_has "$fw" '^- ADR-0003' 'identity server stores its own data' || { WHY="no forward reference to ADR-0003 for the identity server's storage"; return 1; }
  sel_has "$fw" '^- ADR-0004' 'backup' || { WHY="no forward reference to ADR-0004 for backup"; return 1; }
  sel_has "$fw" '^- ADR-0004' 'encryption at rest' || { WHY="no forward reference to ADR-0004 for encryption at rest"; return 1; }
  sel_has "$fw" '^- ADR-0005' 'retention' || { WHY="no forward reference to ADR-0005 for personal-data retention"; return 1; }
  hit="$(grep -Ei 'backup|encryption at rest|retention|identity server.s own data' <<< "$ADR2_P" | grep -Ev 'ADR-000[3-6]' | head -n 1)"
  [ -z "$hit" ] || { WHY="a paragraph names a forwarded topic without citing ADR-0003..0006: $(cut -c1-120 <<< "$hit")"; return 1; }
  forbid "$ADR2_DEC_P" '\b(pg_dump|pgBackRest|WAL-G|Barman|restic|LUKS|dm-crypt|pgcrypto|Keycloak)\b'
}
check "$L02" "(e) backup, encryption at rest, identity server storage, retention only as forward references" k02_e_forward

# ==== K-03 ===================================================================================

# table_rows <paras text> — the data rows of a table: cells separated by tabs, header and separator dropped.
table_rows() {
  printf '%s\n' "$1" | awk -F'|' '
    /^[|]/ { if ($0 ~ /^[|] *-+/ || seen++ == 0) next
             line = ""; for (i = 2; i < NF; i++) { v = $i; gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); line = line (i > 2 ? "\t" : "") v }
             print NF - 2 "\t" line }'
}

k03_one_adr() {
  local num="$1" text="$2" opt ctl n bad id crit
  [ -n "$text" ] || { WHY="ADR-000$num cannot be read at the head"; return 1; }
  hasc "$text" '^\*\*Status:\*\* ' || { WHY="ADR-000$num has no Status line"; return 1; }
  local last=0 h ln
  for h in '## Context' '## Decision' '## Options considered' '## Controls' '## Addenda'; do
    ln="$(printf '%s\n' "$text" | grep -nxF -- "$h" | head -n 1 | cut -d: -f1)"
    [ -n "$ln" ] || { WHY="ADR-000$num has no '$h' section"; return 1; }
    [ "$ln" -gt "$last" ] || { WHY="ADR-000$num: '$h' is out of order"; return 1; }
    last="$ln"
  done
  opt="$(table_rows "$(printf '%s\n' "$text" | section '^## Options considered' | paras)")"
  n="$(printf '%s\n' "$opt" | grep -c .)"
  [ "$n" -ge 2 ] || { WHY="ADR-000$num: Options considered has $n row(s), needs at least 2"; return 1; }
  bad="$(printf '%s\n' "$opt" | awk -F'\t' '$1 != 3 || $2 == "" || $3 == "" || $4 == ""' | head -n 1)"
  [ -z "$bad" ] || { WHY="ADR-000$num: an Options row lacks an option, a Cost or a Closes off cell: $(printf '%s' "$bad" | cut -c1-100)"; return 1; }
  ctl="$(table_rows "$(printf '%s\n' "$text" | section '^## Controls' | paras)")"
  n="$(printf '%s\n' "$ctl" | grep -c .)"
  [ "$n" -ge 1 ] || { WHY="ADR-000$num: Controls has no row"; return 1; }
  while IFS=$'\t' read -r cells id crit; do
    [ -n "$id" ] || continue
    [ "$cells" = 2 ] && [ -n "$crit" ] || { WHY="ADR-000$num: control '$id' is not an identifier and a criterion"; return 1; }
    grep -Eq "^ADR-000$num-C[0-9]+\$" <<< "$id" || { WHY="ADR-000$num: control id '$id' is malformed"; return 1; }
    # A proxy for "checkable by a test or command": a test, a command or a code span in the criterion.
    has "$crit" '(\btests?\b|\bgrep\b|\bexits?\b|\bruns?\b|\bstarts\b|\bSHOW\b|\bSELECT\b|\.(json|toml|ya?ml|py|ts)\b|[`]|\bfails?\b|\breturns?\b|\blists?\b|\bexists?\b|\bbuilds?\b|\bgets\b|--[a-z]+)' || { WHY="ADR-000$num: control $id names no test or command: $(printf '%s' "$crit" | cut -c1-100)"; return 1; }
  done <<< "$ctl"
}
k03_sections_counts_controls() {
  k03_one_adr 1 "$ADR1" || return 1
  k03_one_adr 2 "$ADR2" || return 1
}
check "$L03" "each ADR: Status/Context/Decision/Options/Controls/Addenda, 2+ options with Cost and Closes off, observable controls" k03_sections_counts_controls

k03_no_status_fields() {
  local t n
  for n in 1 2; do
    t="$ADR1"; [ "$n" = 2 ] && t="$ADR2"
    forbid "$t" '^[-*> ]*(\*\*)?(Implemented|Implementation status|Owner|Proof)(\*\*)?[[:space:]]*:' || return 1
    forbid "$t" '(^|[^A-Za-z])Implemented(\*\*)?[[:space:]]*:' || return 1
    forbid "$t" '^[|] *(Implemented|Implementation|Owner|Proof|Evidence) *[|]' || return 1
    forbid "$t" 'Status:\*\* *(Implemented|Done|Complete)' || return 1
  done
}
check "$L03" "no Implemented, owner or proof field in either ADR" k03_no_status_fields

k03_english() {
  local t n words
  for n in 1 2; do
    t="$ADR1"; [ "$n" = 2 ] && t="$ADR2"
    forbid "$t" '\b(oraz|który|która|które|jest|się|żeby|ponieważ|zostaje|wszystkie)\b' || return 1
    words="$(printf '%s\n' "$t" | grep -oiw 'the' | wc -l | tr -d ' ')"
    [ "$words" -ge 20 ] || { WHY="ADR-000$n reads as not English ($words occurrences of 'the')"; return 1; }
  done
}
check "$L03" "both ADRs are written in English" k03_english

k03_numbers() {
  local names nums n
  names="$(git ls-tree --name-only "$HEAD_REV" "$DECISIONS/" | sed 's|.*/||' | grep -E '^ADR-[0-9]{4}-.*\.md$')"
  nums="$(printf '%s\n' "$names" | cut -c5-8)"
  [ "$(printf '%s\n' "$nums" | sort | uniq -d | head -n 1)" = "" ] || { WHY="duplicate ADR number $(printf '%s\n' "$nums" | sort | uniq -d | head -n 1)"; return 1; }
  for n in 0001 0002; do grep -qx "$n" <<< "$nums" || { WHY="no ADR-$n in $DECISIONS"; return 1; }; done
  for n in 0003 0004 0005 0006; do
    ! grep -qx "$n" <<< "$nums" || { WHY="ADR-$n exists in $DECISIONS at the head"; return 1; }
  done
}
check "$L03" "no duplicate ADR number, and none of ADR-0003..0006, in the decisions directory" k03_numbers

# ==== K-04 ===================================================================================

DRAFT_LINE='**Status:** Draft — pending approval'

# status_at <rev> <path> — the first Status line of the file at that commit, or nothing.
status_at() { doc "$1" "$2" | grep -m1 '^\*\*Status:\*\*'; }
is_accepted() { case "$1" in '**Status:** Accepted'*) return 0 ;; *) return 1 ;; esac; }

# valid_date YYYY-MM-DD — a real calendar date.
valid_date() {
  local y m d dim
  [[ "$1" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})$ ]] || return 1
  y=$((10#${BASH_REMATCH[1]})); m=$((10#${BASH_REMATCH[2]})); d=$((10#${BASH_REMATCH[3]}))
  [ "$m" -ge 1 ] && [ "$m" -le 12 ] || return 1
  case "$m" in
    1|3|5|7|8|10|12) dim=31 ;;
    4|6|9|11) dim=30 ;;
    *) if [ $((y % 4)) -eq 0 ] && { [ $((y % 100)) -ne 0 ] || [ $((y % 400)) -eq 0 ]; }; then dim=29; else dim=28; fi ;;
  esac
  [ "$d" -ge 1 ] && [ "$d" -le "$dim" ]
}

k04_1_format() {
  local f line
  for f in "$ADR1_PATH" "$ADR2_PATH"; do
    line="$(status_at "$HEAD_REV" "$f")"
    grep -Eq '^\*\*Status:\*\* Accepted [0-9]{4}-[0-9]{2}-[0-9]{2}$' <<< "$line" || { WHY="$f status line reads '$line'"; return 1; }
    valid_date "${line##* }" || { WHY="$f date '${line##* }' is not a calendar date"; return 1; }
  done
}
check "$L04" "(1) both ADRs read 'Accepted YYYY-MM-DD' with a real calendar date at the head" k04_1_format

k04_2_dates() {
  local f line date add low high
  # The committer date in the commit's own recorded offset, date part only.
  high="$(git log -1 --format=%cI "$MERGE")"; high="${high:0:10}"
  for f in "$ADR1_PATH" "$ADR2_PATH"; do
    line="$(status_at "$HEAD_REV" "$f")"; date="${line##* }"
    valid_date "$date" || { WHY="$f has no valid acceptance date to compare ('$line')"; return 1; }
    add="$(git log --reverse --no-merges --diff-filter=A --format=%H "$BASE..$HEAD_REV" -- "$f" | head -n 1)"
    [ -n "$add" ] || { WHY="no commit in base..head adds $f"; return 1; }
    low="$(git log -1 --format=%cI "$add")"; low="${low:0:10}"
    [[ "$date" < "$low" ]] && { WHY="$f is dated $date, before $low, the date of the commit that first adds it"; return 1; }
    [[ "$date" > "$high" ]] && { WHY="$f is dated $date, after $high, the date of the merge commit"; return 1; }
  done
  return 0
}
check "$L04" "(2) each acceptance date lies between the first commit adding the ADR and the merge commit" k04_2_dates

# status_only_commit <commit> — the commit has one parent and changes nothing but ADR Status lines.
status_only_commit() {
  local c="$1" names bad
  [ "$(git rev-list --parents -n 1 "$c" | wc -w | tr -d ' ')" -eq 2 ] || { WHY="$(git rev-parse --short "$c") is a merge commit, which never counts as the separate acceptance commit"; return 1; }
  names="$(git diff --name-only --no-renames "$c^1" "$c" | grep -Ev "^$DECISIONS/ADR-[0-9]{4}-[^/]*\.md$")"
  [ -z "$names" ] || { WHY="$(git rev-parse --short "$c") changes a file other than an ADR: $(printf '%s' "$names" | head -n 1)"; return 1; }
  bad="$(git diff -U0 --no-color --no-ext-diff "$c^1" "$c" | tr -d '\r' | grep -E '^[-+]' | grep -Ev '^(\+\+\+|---) ' | grep -Ev '^[-+]\*\*Status:\*\* ' | head -n 1)"
  [ -z "$bad" ] || { WHY="$(git rev-parse --short "$c") changes more than the Status line: $(printf '%s' "$bad" | cut -c1-100)"; return 1; }
}

# k04_history_one <file> — in base..head, the commit adding the file reads Draft, and each commit
# where an Accepted status first appears is a separate status-only commit.
k04_history_one() {
  local f="$1" add st c p pst
  add="$(git log --reverse --no-merges --diff-filter=A --format=%H "$BASE..$HEAD_REV" -- "$f" | head -n 1)"
  [ -n "$add" ] || { WHY="no commit in base..head adds $f"; return 1; }
  st="$(status_at "$add" "$f")"
  [ "$st" = "$DRAFT_LINE" ] || { WHY="the commit that adds $f ($(git rev-parse --short "$add")) reads '$st', not Draft — pending approval"; return 1; }
  while read -r c; do
    st="$(status_at "$c" "$f")"
    is_accepted "$st" || continue
    p="$(git rev-parse "$c^1" 2>/dev/null)"
    pst=""; [ -z "$p" ] || pst="$(status_at "$p" "$f")"
    ! is_accepted "$pst" || continue
    [ "$c" != "$add" ] || { WHY="$f reads Accepted in the commit that adds it"; return 1; }
    status_only_commit "$c" || { WHY="$f first reads Accepted at a commit that is not a separate status-only commit: $WHY"; return 1; }
  done < <(git rev-list --reverse --topo-order "$BASE..$HEAD_REV")
}
k04_3_history() { k04_history_one "$ADR1_PATH" && k04_history_one "$ADR2_PATH"; }
check "$L04" "(3) in base..head each ADR is added as a Draft and first reads Accepted in a separate status-only commit" k04_3_history

k04_3_pinned() {
  local i d a f st
  for i in 0 1 2; do
    d="${PIN_DRAFTS[$i]}"; a="${PIN_ACCEPTS[$i]}"
    for f in "$ADR1_PATH" "$ADR2_PATH"; do
      st="$(status_at "$d" "$f")"
      [ "$st" = "$DRAFT_LINE" ] || { WHY="Architect draft $(git rev-parse --short "$d") reads '$st' in $f"; return 1; }
      is_accepted "$(status_at "$a" "$f")" || { WHY="acceptance commit $(git rev-parse --short "$a") does not read Accepted in $f"; return 1; }
    done
    [ "$a" != "$d" ] && git merge-base --is-ancestor "$d" "$a" || { WHY="acceptance commit $(git rev-parse --short "$a") does not follow its draft $(git rev-parse --short "$d")"; return 1; }
    status_only_commit "$a" || return 1
  done
}
check "$L04" "(3) PR #30's three Architect drafts read Draft; their three acceptance commits are separate and later" k04_3_pinned

# ==== K-05 ===================================================================================

# layer_tsv — stdin: a layer register; one line per row whose first cell is in backticks:
# cell count, layer, glob, referenced as, must not depend on (backticks removed).
layer_tsv() {
  awk -F'|' '
    /^[|][[:space:]]*`/ {
      c[2] = ""; c[3] = ""; c[4] = ""; c[5] = ""
      for (i = 2; i < NF && i <= 5; i++) { c[i] = $i; gsub(/^[[:space:]]+|[[:space:]]+$/, "", c[i]); gsub(/`/, "", c[i]) }
      printf "%d\t%s\t%s\t%s\t%s\n", NF - 2, c[2], c[3], c[4], c[5]
    }'
}
# globs_of — stdin: a sensitive-paths register; the glob of every row whose first cell is in backticks.
globs_of() {
  awk -F'|' '/^[|]/ { g = $2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", g); if (g ~ /^`[^`]+`$/) print substr(g, 2, length(g) - 2) }'
}

LAYERS_HEAD="$TMP/layers-head.md"; PATHS_HEAD="$TMP/paths-head.md"
LAYERS_BASE="$TMP/layers-base.md"; PATHS_BASE="$TMP/paths-base.md"; PATHS_PIN="$TMP/paths-pin.md"
doc "$HEAD_REV" "$LAYERS" > "$LAYERS_HEAD"; doc "$HEAD_REV" "$PATHS" > "$PATHS_HEAD"
doc "$BASE" "$LAYERS" > "$LAYERS_BASE"; doc "$BASE" "$PATHS" > "$PATHS_BASE"
doc "$PIN_HEAD" "$PATHS" > "$PATHS_PIN"
LAYER_ROWS="$(layer_tsv < "$LAYERS_HEAD")"

k05_1_no_pending() {
  local f hits
  for f in "$LAYERS_HEAD" "$PATHS_HEAD"; do
    [ -s "$f" ] || { WHY="a register cannot be read at the head"; return 1; }
    hits="$(grep -nE 'pending ADR-000[12]' "$f" | head -n 1)"
    [ -z "$hits" ] || { WHY="a row still reads: $(printf '%s' "$hits" | cut -c1-120)"; return 1; }
  done
}
check "$L05" "(1) no 'pending ADR-0001/0002' remains in the two registers" k05_1_no_pending

# adr_file <n> — the path of ADR-000<n> in the decisions directory at the head.
adr_file() { git ls-tree --name-only "$HEAD_REV" "$DECISIONS/" | grep -E "/ADR-000$1-[^/]*\.md$" | head -n 1; }

k05_2_citations() {
  local n file cites
  cites="$(cat "$LAYERS_HEAD" "$PATHS_HEAD" | grep -Eo 'ADR-000[12]' | sort -u)"
  [ -n "$cites" ] || { WHY="neither register cites ADR-0001 or ADR-0002"; return 1; }
  for n in 1 2; do
    grep -qx "ADR-000$n" <<< "$cites" || continue
    file="$(adr_file "$n")"
    [ -n "$file" ] || { WHY="a register cites ADR-000$n, which does not exist at the head"; return 1; }
    is_accepted "$(status_at "$HEAD_REV" "$file")" || { WHY="a register cites ADR-000$n, whose status is '$(status_at "$HEAD_REV" "$file")'"; return 1; }
  done
}
check "$L05" "(2) every ADR-0001/0002 citation points at an existing Accepted file" k05_2_citations

k05_3_provisional() {
  local f above
  for f in "$LAYERS_HEAD" "$PATHS_HEAD"; do
    ! grep -Eiq 'Provisional' "$f" || { WHY="a register still has a Provisional paragraph: $(grep -Ei 'Provisional' "$f" | head -n 1 | cut -c1-100)"; return 1; }
    above="$(sed -n '1,/^[|]/p' "$f")"
    grep -Eq 'ADR-0001' <<< "$above" || { WHY="the paragraph above a register's table does not cite ADR-0001"; return 1; }
    grep -Eq 'ADR-0002' <<< "$above" || { WHY="the paragraph above a register's table does not cite ADR-0002"; return 1; }
  done
}
check "$L05" "(3) the two Provisional paragraphs are rewritten to cite the ADRs" k05_3_provisional

k05_6_still_pending() {
  local n
  for n in 3 4 5 6; do
    grep -Eq "pending[^|]*ADR-000$n" "$LAYERS_HEAD" "$PATHS_HEAD" || { WHY="no row keeps 'pending ADR-000$n'"; return 1; }
  done
}
check "$L05" "rows governed by ADR-0003..0006 keep their pending reference" k05_6_still_pending

k05_5_tools() {
  local out code
  out="$(bash "$SCRIPTS/layer-check.sh" --register "$LAYERS_HEAD" "$BASE" "$HEAD_REV" 2>&1)"; code=$?
  [ "$code" -eq 0 ] || { WHY="layer-check.sh exited $code on the layer register: $(printf '%s' "$out" | tail -n 1 | cut -c1-140)"; return 1; }
  out="$(bash "$SCRIPTS/risk-check.sh" --register "$PATHS_HEAD" classes --paths - <<< 'backend/app/api/sample.py' 2>&1)"; code=$?
  [ "$code" -eq 0 ] || { WHY="risk-check.sh exited $code on the sensitive-paths register: $(printf '%s' "$out" | tail -n 1 | cut -c1-140)"; return 1; }
}
check "$L05" "(5) layer-check.sh and risk-check.sh read the two registers without exit 2" k05_5_tools

# row_of <layer> — the single register row of a layer as "cells<TAB>layer<TAB>glob<TAB>prefix<TAB>forbidden".
row_of() {
  local n; ROW="$(printf '%s\n' "$LAYER_ROWS" | awk -F'\t' -v l="$1" '$2 == l')"
  n="$(printf '%s\n' "$ROW" | grep -c .)"
  [ "$n" -eq 1 ] || { WHY="layer '$1' has $n row(s) in the layer register, expected 1 (a row without its leading or inner '|' does not count)"; return 1; }
}
# expect_row <layer> <glob> <prefix> <forbidden list> — the row matches the layout and rules ADR-0001 fixes.
expect_row() {
  local cells glob prefix forb
  row_of "$1" || return 1
  IFS=$'\t' read -r cells _ glob prefix forb <<< "$ROW"
  [ "$cells" = 5 ] || { WHY="the '$1' row has $cells cells, expected 5"; return 1; }
  [ "$glob" = "$2" ] || { WHY="the '$1' row has path '$glob', expected '$2'"; return 1; }
  [ "$(norm_list "$prefix")" = "$(norm_list "$3")" ] || { WHY="the '$1' row is referenced as '$prefix', expected '$3'"; return 1; }
  [ "$(norm_list "$forb")" = "$(norm_list "$4")" ] || { WHY="the '$1' row must not depend on '$forb', expected '$4'"; return 1; }
}

k05_4_backend_layers() {
  local rows name forb
  rows="$(printf '%s\n' "$ADR1_DEC_P" | awk -F'|' '/^[|] *(domain|services|data|integrations|core|api) *[|]/ { a = $2; b = $3; gsub(/^[[:space:]]+|[[:space:]]+$/, "", a); gsub(/^[[:space:]]+|[[:space:]]+$/, "", b); print a "\t" b }')"
  [ "$(printf '%s\n' "$rows" | grep -c .)" -eq 6 ] || { WHY="the layer rules table of ADR-0001 does not have the six backend layers"; return 1; }
  while IFS=$'\t' read -r name forb; do
    expect_row "$name" "backend/app/$name/**" "app.$name" "$forb" || return 1
  done <<< "$rows"
}
check "$L05" "(4) backend layer rows match the layout and layer rules of ADR-0001" k05_4_backend_layers

k05_4_path_globs() {
  local globs g
  globs="$(globs_of < "$PATHS_HEAD")"
  [ -n "$globs" ] || { WHY="the sensitive-paths register has no rows"; return 1; }
  while IFS= read -r g; do
    case "$g" in
      backend/app/main.py|backend/app/core/settings.py|backend/migrations/**) ;;
      backend/app/core/*|backend/app/domain/*|backend/app/services/*|backend/app/data/*|backend/app/integrations/*|backend/app/auth/*|backend/app/api/*) ;;
      backend/app/*) WHY="glob '$g' is under backend/app but not in a layer directory of the ADR-0001 layout"; return 1 ;;
      backend/alembic.ini|backend/pyproject.toml|backend/uv.toml|'backend/*.lock') ;;
      backend/*) WHY="glob '$g' is under backend/ but names no place of the ADR-0001/0002 layout"; return 1 ;;
      frontend/src/**|frontend/package.json|frontend/pnpm-lock.yaml|frontend/pnpm-workspace.yaml|frontend/index.html|frontend/public/**) ;;
      'frontend/vite.config.*'|'frontend/tsconfig*.json') ;;
      frontend/*) WHY="glob '$g' is under frontend/ but names no place of the ADR-0001 layout"; return 1 ;;
    esac
  done <<< "$globs"
  for g in 'backend/app/data/**' 'backend/migrations/**' 'backend/app/auth/**' 'backend/app/api/**' 'backend/app/main.py' \
           'backend/app/domain/**' 'backend/app/services/**' 'backend/app/core/**' 'backend/app/integrations/**' 'frontend/src/**'; do
    grep -Fxq -- "$g" <<< "$globs" || { WHY="no sensitive-paths row for the layout place '$g'"; return 1; }
  done
}
check "$L05" "(4) sensitive-path globs lie inside the ADR-0001/0002 layout, and every layout place has a row" k05_4_path_globs

k05_4f_frontend() {
  local r forb
  expect_row fe-api 'frontend/src/api/**' '@/api' 'fe-components, fe-features' || return 1
  expect_row fe-components 'frontend/src/components/**' '@/components' 'fe-api, fe-features' || return 1
  expect_row fe-features 'frontend/src/features/**' '@/features' '—' || return 1
  # ADR-0001, Constraint 3: the date helper imports none of the frontend layers, each may use it.
  expect_row fe-time 'frontend/src/time/**' '@/time' 'fe-api, fe-components, fe-features' || return 1
  for r in fe-api fe-components fe-features; do
    forb="$(norm_list "$(printf '%s\n' "$LAYER_ROWS" | awk -F'\t' -v l="$r" '$2 == l { print $5 }')" | tr ',' '\n')"
    ! grep -qx 'fe-time' <<< "$forb" || { WHY="the '$r' row forbids fe-time, which every frontend layer may use"; return 1; }
  done
}
check "$L05" "(4) frontend layer rows, including fe-time: path, prefix and rules" k05_4f_frontend

# fe_case <name> <expected exit> <file> <line> — one added line in a scratch repository, judged
# by layer-check.sh against the head's register.
FE_REPO="$TMP/fe-repo"
fe_git() { git -C "$FE_REPO" -c user.name=doc-check -c user.email=doc-check@example.invalid -c commit.gpgsign=false -c core.autocrlf=false "$@"; }
fe_case() {
  local want="$1" file="$2" line="$3" out code
  fe_git reset -q --hard "$FE_BASE" || { WHY="cannot reset the scratch repository"; return 1; }
  printf '%s\n' "$line" > "$FE_REPO/$file"
  fe_git add -A && fe_git commit -q -m case || { WHY="cannot commit in the scratch repository"; return 1; }
  out="$(cd "$FE_REPO" && bash "$SCRIPTS/layer-check.sh" --register "$LAYERS_HEAD" "$FE_BASE" HEAD 2>&1)"; code=$?
  [ "$code" -eq "$want" ] || { WHY="'$line' in $file: layer-check.sh exited $code, expected $want: $(printf '%s' "$out" | tail -n 1 | cut -c1-120)"; return 1; }
}
k05_fe_imports() {
  local d
  mkdir -p "$FE_REPO" && fe_git init -q || { WHY="cannot create the scratch repository"; return 1; }
  for d in api components features time; do
    mkdir -p "$FE_REPO/frontend/src/$d"; printf 'export const v = 1;\n' > "$FE_REPO/frontend/src/$d/base.ts"
  done
  fe_git add -A && fe_git commit -q -m base || { WHY="cannot commit in the scratch repository"; return 1; }
  FE_BASE="$(fe_git rev-parse HEAD)"
  fe_case 1 frontend/src/time/a.ts "import { a } from '@/api/client';" || return 1
  fe_case 1 frontend/src/time/b.ts "import { b } from '../features/screen';" || return 1
  fe_case 1 frontend/src/time/c.ts "import { c } from '@/components/button';" || return 1
  fe_case 0 frontend/src/api/d.ts "import { t } from '@/time/warsaw';" || return 1
  fe_case 0 frontend/src/components/e.ts "import { t } from '@/time/warsaw';" || return 1
  fe_case 0 frontend/src/features/f.ts "import { t } from '../time/warsaw';" || return 1
}
check "$L05" "fe-time: forbidden imports from time are findings, '@/time' imported by the other layers passes" k05_fe_imports

# ==== K-06 ===================================================================================

# sample_of <glob> — a path the glob matches.
sample_of() { printf '%s\n' "$1" | sed 's/\*\*/sample/g; s/\*/x/g'; }

# class_map <register file> <samples file> — "<path><TAB><class>" for every class risk-check.sh gives a sample.
class_map() {
  local out code
  out="$(bash "$SCRIPTS/risk-check.sh" --register "$1" explain --paths - < "$2" 2>&1)"; code=$?
  [ "$code" -eq 0 ] || { WHY="risk-check.sh exited $code on a register: $(printf '%s' "$out" | tail -n 1 | cut -c1-140)"; return 1; }
  printf '%s\n' "$out" | awk -F'\t' 'NF >= 2 { print $2 "\t" $1 }' | sort -u
}

# lost_classes <reference register> <edited register> <samples file> — fails on a class the edited register no longer gives.
lost_classes() {
  local ref edited lost
  ref="$(class_map "$1" "$3")" || return 1
  edited="$(class_map "$2" "$3")" || return 1
  [ -n "$ref" ] || { WHY="the reference register gives no sample a class"; return 1; }
  lost="$(printf '%s\n' "$ref" | grep -Fxv -f <(printf '%s\n' "$edited") | head -n 1)"
  [ -z "$lost" ] || { WHY="the edited register lost class '$(printf '%s' "$lost" | cut -f2)' for the sample path $(printf '%s' "$lost" | cut -f1)"; return 1; }
}

k06_1_classes() {
  local g
  : > "$TMP/samples-base"
  while IFS= read -r g; do sample_of "$g" >> "$TMP/samples-base"; done < <(globs_of < "$PATHS_BASE")
  lost_classes "$PATHS_BASE" "$PATHS_HEAD" "$TMP/samples-base"
}
check "$L06" "(1) every sample path of the base register keeps all its risk classes in the edited register" k06_1_classes

k06_2_layer_rules() {
  local name forb f row items
  while IFS=$'\t' read -r _ name _ _ forb; do
    for f in $(printf '%s\n' "$forb" | tr ',' ' '); do
      [ "$f" != "—" ] || continue
      row="$(printf '%s\n' "$LAYER_ROWS" | awk -F'\t' -v l="$name" '$2 == l { print $5 }' | head -n 1)"
      items="$(printf '%s\n' "$row" | tr ',' '\n' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
      grep -qx -- "$f" <<< "$items" \
        || { WHY="the '$name' row no longer forbids '$f' (a replacement stated by ADR-0001 is not recognised; none is needed for EKO-1-01)"; return 1; }
    done
  done < <(layer_tsv < "$LAYERS_BASE")
}
check "$L06" "(2) every 'Must not depend on' entry of the base layer register is still in the edited one" k06_2_layer_rules

k06_new_rows() {
  local g n=0 base_globs
  base_globs="$(globs_of < "$PATHS_BASE")"
  : > "$TMP/samples-new"
  while IFS= read -r g; do
    grep -Fxq -- "$g" <<< "$base_globs" && continue
    sample_of "$g" >> "$TMP/samples-new"; n=$((n + 1))
  done < <(globs_of < "$PATHS_PIN")
  [ "$n" -gt 0 ] || { WHY="the pinned register has no row that the base register lacks"; return 1; }
  lost_classes "$PATHS_PIN" "$PATHS_HEAD" "$TMP/samples-new"
}
check "$L06" "rows EKO-1-01 added (ruff, npmrc, index.html, ...) keep the classes they have at the pinned head" k06_new_rows

# ==== K-07 ===================================================================================

MB="$(git merge-base "$BASE" "$HEAD_REV")"
CHANGED="$(git diff --name-only --no-renames "$MB" "$HEAD_REV")"
ALLOWED_RE="^($DECISIONS/ADR-0001-[^/]*\.md|$DECISIONS/ADR-0002-[^/]*\.md|$LAYERS|$PATHS|docs/cost-register/.*)\$"

k07_1_allowed() {
  local extra; extra="$(printf '%s\n' "$CHANGED" | grep . | grep -Ev "$ALLOWED_RE" | head -n 3 | tr '\n' ' ')"
  [ -z "$extra" ] || { WHY="outside the allowed set: $extra"; return 1; }
  grep -Eq "^$ADR1_PATH\$" <<< "$CHANGED" || { WHY="the change set does not include ADR-0001"; return 1; }
}
check "$L07" "(1) the change set lists only the two ADRs, the two registers and the cost register" k07_1_allowed

k07_2_no_code() {
  local bad
  bad="$(printf '%s\n' "$CHANGED" | grep -E '^(backend|frontend)/|(^|/)Dockerfile[^/]*$|(^|/)\.env[^/]*$|(^|/)(pyproject\.toml|package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|uv\.toml)$|\.lock$' | head -n 3 | tr '\n' ' ')"
  [ -z "$bad" ] || { WHY="listed: $bad"; return 1; }
}
check "$L07" "(2) nothing under backend/ or frontend/, no Dockerfile, .env, manifest or lock file" k07_2_no_code

k07_3_capabilities() {
  local a b
  a="$(git rev-parse "$MB:$CAPS" 2>/dev/null)"; b="$(git rev-parse "$HEAD_REV:$CAPS" 2>/dev/null)"
  [ -n "$a" ] || { WHY="$CAPS cannot be read at the base"; return 1; }
  [ "$a" = "$b" ] || { WHY="$CAPS differs between the base and the head"; return 1; }
}
check "$L07" "(3) capabilities.md is byte-identical between the base and the head" k07_3_capabilities

# ---- every label printed an ok line -----------------------------------------------------------

for label in "$L01" "$L02" "$L03" "$L04" "$L05" "$L06" "$L07"; do
  if ! grep -Fxq -- "$label" <<< "$OKS"; then
    echo "FAIL $label — no check printed an ok line under this label"; failed=$((failed + 1))
  fi
done

echo "EKO-1-01 doc-checks: $passed passed, $failed failed, $skipped skipped (base $BASE, head $HEAD_REV)"
[ "$failed" -eq 0 ]
