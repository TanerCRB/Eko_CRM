#!/usr/bin/env bash
# EKO-1-12: document completeness, accepted bootstrap order and exact gate-3 proposal.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || {
  echo "EKO-1-12 doc-checks: cannot enter repository root" >&2
  exit 2
}

EVIDENCE_DIR="${EKO112_EVIDENCE_DIR:-docs/evidence/EKO-1-12}"
ADR="${EKO112_ADR:-docs/architecture/decisions/ADR-0004-deployment-and-recovery.md}"
REGISTER="${EKO112_EXCEPTION_REGISTER:-docs/architecture/exception-register.md}"
BOOTSTRAP="$EVIDENCE_DIR/bootstrap.md"
TIMING="$EVIDENCE_DIR/reset-timing.md"
PROPOSAL="$EVIDENCE_DIR/gate-3-proposal.md"
BASELINE="2dcb057f818fd9a1e4142fbf0c71276f542f6ffa"
ADDENDUM_FILE="$(mktemp)"
trap 'rm -f "$ADDENDUM_FILE"' EXIT
awk '
  /^### 2026-11-02 — Bootstrap order:/ { in_addendum = 1 }
  in_addendum && /^### / && !/^### 2026-11-02 — Bootstrap order:/ { exit }
  in_addendum { print }
' "$ADR" > "$ADDENDUM_FILE"
passed=0
failed=0
WHY=""

need_file() {
  [ -s "$1" ] || {
    WHY="missing or empty $1"
    return 1
  }
}

need_text() {
  local file="$1" expression="$2"
  grep -Eiq -- "$expression" "$file" || {
    WHY="$file lacks /$expression/"
    return 1
  }
}

need_order() {
  local file="$1"
  shift
  local previous=0 offset expression
  for expression in "$@"; do
    offset="$(tr -d '\r' < "$file" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g' | grep -Eibo -- "$expression" | awk -F: -v previous="$previous" '$1 > previous { print $1; exit }')"
    [ -n "$offset" ] && [ "$offset" -gt "$previous" ] || {
      WHY="$file has wrong or missing order at /$expression/"
      return 1
    }
    previous="$offset"
  done
}

check() {
  local name="$1"
  shift
  WHY=""
  if "$@"; then
    echo "ok   $name"
    passed=$((passed + 1))
  else
    echo "FAIL $name -- ${WHY:-check failed}"
    failed=$((failed + 1))
  fi
}

k02_record() {
  need_file "$BOOTSTRAP" || return 1
  need_text "$BOOTSTRAP" '^Date: 2026-[0-9]{2}-[0-9]{2}$' || return 1
  need_text "$BOOTSTRAP" "Baseline SHA: $BASELINE" || return 1
  need_order "$BOOTSTRAP" \
    'Live master bruteForceProtected true' \
    'admin listener open' \
    'application realm import complete' \
    'Live application bruteForceProtected true' \
    'public listener open' || return 1
  need_text "$BOOTSTRAP" 'master.*contrast.*admin listener.*closed' || return 1
  need_text "$BOOTSTRAP" 'application.*contrast.*public listener.*closed' || return 1
  need_text "$BOOTSTRAP" 'rerun.*existing volume.*live checks' || return 1
}

k05_record() {
  need_file "$TIMING" || return 1
  need_text "$TIMING" '^# EKO-1-12 reset-timing record$' || return 1
  need_text "$TIMING" '^Date: 2026-[0-9]{2}-[0-9]{2}$' || return 1
  need_text "$TIMING" "Baseline SHA: $BASELINE" || return 1
  need_text "$TIMING" 'known.*\[([1-9][0-9]*|0\.[0-9]*[1-9][0-9]*)' || return 1
  need_text "$TIMING" 'unknown.*\[([1-9][0-9]*|0\.[0-9]*[1-9][0-9]*)' || return 1
  need_text "$TIMING" 'known.*mail.*(delivered|message)' || return 1
  need_text "$TIMING" 'unknown.*mail.*(zero|0|none)' || return 1
  need_text "$TIMING" 'Human distinguishability finding: UNDECIDABLE.*returned to the human' || return 1
  ! grep -Eiq 'Human distinguishability finding: (PASS|indistinguishable|distinguishable)' "$TIMING" || {
    WHY="timing record invents the human's decision"
    return 1
  }
}

k07_addendum() {
  need_file "$ADR" || return 1
  [ "$(grep -c '^### 2026-11-02 — Bootstrap order: each listener opens only after its own brute-force precondition$' "$ADR")" -eq 1 ] || {
    WHY="expected exactly one dated bootstrap addendum"
    return 1
  }
  need_text "$ADR" '^\*\*Status:\*\* Accepted 2026-11-02.*G-1 A' || return 1
  need_order "$ADDENDUM_FILE" \
    'Verify that the live master realm reports `bruteForceProtected` true' \
    'Only then open the admin listener' \
    'import the application realm' \
    'After the import has completed, verify that the live application' \
    'realm reports `bruteForceProtected` true' \
    'Only then open the public listener' || return 1
  if git diff -- "$ADR" | grep -E '^-[^-]' | grep -q .; then
    WHY="accepted ADR text was deleted or edited"
    return 1
  fi
}

k07_proposal() {
  need_file "$PROPOSAL" || return 1
  need_text "$BOOTSTRAP" '^Date:' || return 1
  [ "$(grep -c '^- Exception EKO-1-03/R-22$' "$PROPOSAL")" -eq 1 ] || {
    WHY="proposal must remove exactly R-22"
    return 1
  }
  [ "$(grep -c '^- Exception ' "$PROPOSAL")" -eq 1 ] || {
    WHY="proposal removes another exception"
    return 1
  }
  need_text "$PROPOSAL" 'docs/evidence/EKO-1-12/bootstrap.md' || return 1
  need_text "$REGISTER" 'Exception EKO-1-03/R-22' || return 1
  need_text "$REGISTER" '2027-03-31' || return 1
}

check 'K-02 dated live bootstrap order and contrasts' k02_record
check 'K-05 dated reset-timing record and undecided human finding' k05_record
check 'K-07 accepted append-only ADR-0004 addendum' k07_addendum
check 'K-07 exact R-22 gate-3 proposal with runtime evidence' k07_proposal

echo "EKO-1-12 doc-checks: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
