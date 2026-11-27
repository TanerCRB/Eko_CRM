#!/usr/bin/env bash
# EKO-3-11 — proves K-05 of Issue #266: the task adds new tests and changes no backend file and no
# existing test; a production file changes only as the minimal fix of a defect a new test showed
# red (the red run recorded in the PR description); scripts/weakening-check.sh finds nothing.
#
#   bash tests/doc-checks/EKO-3-11.sh --pr <pr-body.md>                  # BASE...CHECKPOINT
#   bash tests/doc-checks/EKO-3-11.sh --pr <pr-body.md> --head <rev>     # BASE...<rev>, e.g. the PR head
#   bash tests/doc-checks/EKO-3-11.sh --self-test                        # built-in contrasts, offline
#
#   gh pr view <n> --json body --jq .body > pr-body.md                   # the body the run expects
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
#               on the base side at BASE's line numbers and on the head side at HEAD's.
#   red-run     every M entry has a red-run record in the PR body, and every record stands for an
#               M entry. A record is one line
#                 - Red run — K-0n — <frontend/tests/...test.tsx>::<test name> — failed on: <assertion>
#               whose test file is an A entry of the range containing the quoted test name at HEAD,
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

PR=""; HEAD_REV=""; MODE=run
while [ $# -gt 0 ]; do
  case "$1" in
    --pr|--head)
      [ $# -ge 2 ] || die "$1 needs a value"
      case "$1" in --pr) PR="$2" ;; --head) HEAD_REV="$2" ;; esac
      shift 2 ;;
    --self-test) MODE=self; shift ;;
    *) die "unknown argument '$1' (usage: $0 --pr <file> [--head <rev>] | --self-test)" ;;
  esac
done
if [ "$MODE" = run ]; then
  [ -n "$PR" ] && [ -r "$PR" ] || die "--pr needs a readable file"
elif [ -n "$PR$HEAD_REV" ]; then
  die "--self-test takes no other argument"
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || die "cannot enter the repository root"
TOP="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null)" || die "not a git repository"

WORK="$(mktemp -d)" || die "cannot create a temporary directory"
trap 'rm -rf "$WORK"' EXIT
[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" != "$TOP" ] || die "the temporary directory $WORK lies inside the repository"

qgit() { git -c core.autocrlf=false -c advice.detachedHead=false -c user.name=qa -c user.email=qa@example.invalid "$@"; }

# ---- helpers -------------------------------------------------------------------------------------

# blob <repo> <rev> <path> — the file at <rev>, carriage returns removed.
blob() { git -C "$1" show "$2:$3" 2>/dev/null | tr -d '\r'; }

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
  git -C "$1" diff -U0 "$2...$3" -- docs/PLAN.md | tr -d '\r' > "$d"
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
  NAMES="$(git -C "$1" diff --name-status -M "$2...$3" 2> "$WORK/names.err")" || die "git diff $2...$3 failed: $(tail -n 1 "$WORK/names.err")"
}

# m_entries — the production paths with an M entry, one per line.
m_entries() { awk -F'\t' '$1 == "M" && ($2 == "'"$DETAIL"'" || $2 == "'"$LIST"'") { print $2 }' <<< "$NAMES"; }
# a_test <path> — the path is an A entry under frontend/tests/.
a_test() { awk -F'\t' -v p="$1" '$1 == "A" && $2 == p { f = 1 } END { exit !f }' <<< "$NAMES" && [[ "$1" == frontend/tests/* ]]; }

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
  local repo="$1" base="$2" head="$3" p bs be hs he os oc ns nc bad="" hunks=0 line
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    read -r bs be <<< "$(span "$repo" "$base" "$p")"
    read -r hs he <<< "$(span "$repo" "$head" "$p")"
    [ -n "${bs:-}" ] && [ -n "${be:-}" ] || { bad="$bad$p: the function is not found at the base; "; continue; }
    [ -n "${hs:-}" ] && [ -n "${he:-}" ] || { bad="$bad$p: the function is not found at the head; "; continue; }
    while IFS= read -r line; do
      [[ "$line" =~ ^@@\ -([0-9]+)(,([0-9]+))?\ \+([0-9]+)(,([0-9]+))?\ @@ ]] || continue
      os="${BASH_REMATCH[1]}"; oc="${BASH_REMATCH[3]:-1}"; ns="${BASH_REMATCH[4]}"; nc="${BASH_REMATCH[6]:-1}"
      hunks=$((hunks + 1))
      inside "$os" "$oc" "$bs" "$be" || bad="$bad$p: base lines $os,$oc outside $bs-$be; "
      inside "$ns" "$nc" "$hs" "$he" || bad="$bad$p: head lines $ns,$nc outside $hs-$he; "
    done < <(git -C "$repo" diff -U0 "$base...$head" -- "$p")
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
    if ! blob "$repo" "$head" "$file" | grep -qF -- "\"$name\""; then bad="$bad$k record names '$name', not a test in $file; "; continue; fi
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

# st_case <name> <want> <shell edit after fx_good> <pr body lines...> — <want> is "<failed keys>"
# or "<failed keys>|<text the report must hold>", so a case fails for its own reason, not another.
st_case() {
  local name="$1" want="${2%%|*}" has="" edit="$3" head
  case "$2" in *"|"*) has="${2#*|}" ;; esac
  shift 3
  st_total=$((st_total + 1))
  qgit -C "$FX" checkout --quiet --force "$FXBASE" && qgit -C "$FX" clean --quiet -fdx || die "self-test: cannot reset the fixture"
  ( cd "$FX" && fx_good && eval "$edit" ) || die "self-test: the edit for '$name' failed"
  qgit -C "$FX" add -A && qgit -C "$FX" commit --quiet --allow-empty -m "$name" || die "self-test: commit for '$name' failed"
  head="$(git -C "$FX" rev-parse HEAD)"
  printf '%s\n' '## Summary' 'Tests only.' "$@" > "$WORK/st-body.md"
  run_all "$FX" "$FXBASE" "$head" "$WORK/st-body.md" > "$WORK/st.out"
  if [ "$FAILED_KEYS" = "$want" ] && { [ -z "$has" ] || grep -qF -- "$has" "$WORK/st.out"; }; then
    echo "ok   self-test $name — failed: ${want:-none}${has:+ (reports '$has')}"
  else
    echo "FAIL self-test $name — expected failed '${want:-none}'${has:+ reporting '$has'}, got '${FAILED_KEYS:-none}'"; sed 's/^/       /' "$WORK/st.out"
    st_fail=$((st_fail + 1))
  fi
}

sl() { sed -i "$1" "$2"; }

self_test() {
  local dfix lfix fd="frontend/src/features/customers" ft="frontend/tests/features/customers"
  dfix="sl '5s/=== (which === \"archive\")/!== (which === \"restore\")/' '$DETAIL'"
  lfix="sl '4s/?? \"active\"/|| \"active\"/' '$LIST'"
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

echo "EKO-3-11 doc-check: range $BASE_SHA...$HEAD_SHA"
run_all "$TOP" "$BASE_SHA" "$HEAD_SHA" "$PR"
n_fail=$(wc -w <<< "$FAILED_KEYS")
echo "EKO-3-11 doc-check: $((4 - n_fail)) passed, $n_fail failed"
[ "$n_fail" -eq 0 ]
