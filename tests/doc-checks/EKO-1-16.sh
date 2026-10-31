#!/usr/bin/env bash
# EKO-1-16 -- document checks for the 2026-10-29 ADR-0006 addendum (Issue #46).
#
# Run with: bash tests/doc-checks/EKO-1-16.sh
#
# The checks read only the dated addendum. They establish that its nine resolutions retain their
# stated contrasts; they do not prove the future EKO-5 implementation or Google behaviour.
# Each K-01..K-07 and R-01..R-02 comment names the Analyst mutation that must make that check fail.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || {
  echo "EKO-1-16 doc-checks: cannot enter repository root" >&2
  exit 2
}

ADR="docs/architecture/decisions/ADR-0006-google-calendar.md"
[ -r "$ADR" ] || {
  echo "EKO-1-16 doc-checks: cannot read $ADR" >&2
  exit 2
}

ADDENDUM="$(tr -d '\r' < "$ADR" | awk '
  /^### 2026-10-29/ { in_addendum = 1 }
  in_addendum && /^### / && !/^### 2026-10-29/ { exit }
  in_addendum { print }
')"
[ -n "$ADDENDUM" ] || {
  echo "EKO-1-16 doc-checks: 2026-10-29 addendum is missing" >&2
  exit 2
}

# Normalising line wrapping and Markdown emphasis makes every assertion span prose rather than a
# particular physical line while keeping the check limited to this addendum.
TEXT="$(printf '%s\n' "$ADDENDUM" | tr '\n' ' ' | sed -E 's/[\*`]//g; s/[[:space:]]+/ /g')"

passed=0
failed=0
WHY=""

has() { grep -Eiq -- "$2" <<< "$1"; }

need() {
  local expression="$1"
  if ! has "$TEXT" "$expression"; then
    WHY="missing /$expression/"
    return 1
  fi
}

all() {
  local expression
  for expression in "$@"; do
    need "$expression" || return 1
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

# K-01 -- ownership/erasure disposition and notice.
# Contrast: an Ownership hold may suspend ordinary synchronisation, but cannot hide or block an
# erasure removal. Mutation K01-M1: remove "run even when ... suspended by Ownership".
k01() {
  all \
    'erasure removals run even when its ordinary synchronisation jobs are suspended by Ownership' \
    'deletion or sweep cannot be carried out, the removal is recorded as not carried out and that job ends' \
    'record supplies the existing owner-and-manager notice'
}

# K-02 -- per-calendar progress across access loss.
# Contrast: one unavailable calendar neither holds a later job nor redirects that removal to a
# different calendar. Mutation K02-M1: replace "does not hold a later job" with "holds later jobs".
k02() {
  all \
    'a suspended sweep does not hold a later job of that visit' \
    'taken up .* when that same calendar is linked again or its link works' \
    'never sent to a different calendar'
}

# K-03 -- synchronised Google-time baseline.
# Contrast: a later non-time Google edit must not make an already-applied Google time change appear
# new and revert it. Mutation K03-M1: remove the last-synchronised comparison baseline.
k03() {
  all \
    'event record holds the last synchronised start and end' \
    'last applied from a Google time change' \
    'another field only does not make the already-applied Google time change look new again' \
    'comparison .* last synchronised values, not only .* last written by the application'
}

# K-04 -- pending-create disposition on calendar switch.
# Contrast: a confirmed switch leaves an earlier pending create tracked there; only a new create
# under a new identifier may use the new calendar. Mutation K04-M1: discard the earlier record.
k04() {
  all \
    'confirms a different calendar, every pending create record remains tied to the earlier calendar' \
    'neither discarded nor treated as an event in the new calendar' \
    'new create in the confirmed new calendar only under a new identifier' \
    'never becomes an untracked twin or a candidate for synchronisation in the new calendar'
}

# K-05 -- failed-sweep durable record, notice and take-up.
# Contrast: a failed sweep is not merely an event record or a transient failure. Mutation K05-M1:
# remove the distinct removal record or its owner-and-manager notice.
k05() {
  all \
    'sweep removal recorded as not carried out has a record distinct from an event record' \
    'visit identifier, environment marker, calendar owner, chosen identifier prefix' \
    'record supplies the existing owner-and-manager notice and the same-calendar take-up rule' \
    'cleared only after Google confirms deletion or answers that the event is deleted or absent'
}

# K-06 -- moved-event no-hold contrast.
# Contrast: a confirmed deletion from its recorded calendar clears the other owner's link; a live
# recorded event still invokes Ownership. Mutation K06-M1: make the absent/deleted event hold.
k06() {
  all \
    'reads the event in its recorded owner.s calendar' \
    'read confirms it absent or deleted.*does not hold the other owner.s link' \
    'remains live in its recorded owner.s calendar, the existing Ownership hold still applies' \
    'never synchronised or changed through the calendar where it was found'
}

# K-07 -- identifier-prefix bounded sweep.
# Contrast: the matching marker alone cannot authorise deletion; the application-generated prefix
# for that visit and environment is also required. Mutation K07-M1: remove the prefix condition.
k07() {
  all \
    'id field .* begins with an application-generated prefix' \
    'encoding of the environment identifier and the visit.s opaque identifier' \
    'marker names that visit and environment and its identifier begins with that prefix' \
    'Google-generated identifier does not satisfy that condition'
}

# R-01 -- marker/prefix discovery requires validated provenance.
# Contrast: an event found only by its marker and identifier prefix is unresolved, not an automatic
# deletion candidate. Mutation R01-M1: permit automatic deletion from marker and prefix alone.
r01() {
  all \
    'event discovered only from its marker and identifier prefix is never deleted automatically' \
    'recorded as unresolved pending validated provenance as an application-generated event' \
    'marker and prefix alone are not that validation' \
    'provenance must be validated before any real-data use'
}

# R-02 -- failed recorded-owner read does not change the candidate or hold every link.
# Contrast: the failed read leaves the candidate unchanged while verification retries and notices;
# it cannot impose a link-wide or propagated Ownership hold. Mutation R02-M1: remove retry.
r02() {
  all \
    'recorded-owner calendar read fails, the candidate enters non-blocking pending ownership verification' \
    'candidate event is not altered' \
    'verification is retried' \
    'operational notice with no customer value is issued' \
    'No link-wide Ownership hold, including the hold propagated to other links, is imposed until that read succeeds'
}

check 'K-01 ownership erasure disposition and notice' k01
check 'K-02 per-calendar progress across access loss' k02
check 'K-03 synchronised Google-time baseline' k03
check 'K-04 pending-create disposition on calendar switch' k04
check 'K-05 failed-sweep durable record notice and take-up' k05
check 'K-06 moved-event no-hold contrast' k06
check 'K-07 identifier-prefix bounded sweep' k07
check 'R-01 marker-prefix discovery requires validated provenance' r01
check 'R-02 failed recorded-owner read remains non-blocking' r02

echo "EKO-1-16 doc-checks: $passed passed, $failed failed"
[ "$failed" -eq 0 ]
