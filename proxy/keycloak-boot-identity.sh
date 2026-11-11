#!/bin/sh
# The boot identity of the running Keycloak container (ADR-0004-C33, addendum 2026-11-10):
# the per-boot token the Keycloak entrypoint wrapper rotated as the FIRST act of its current
# container start, read here from the shared named volume mounted read-only at this path.
# This replaced the 2026-11-06 primitive (a TCP attempt plus an ARP-table lookup of the
# hardware address) because that observation was not reliably available: a restarted proxy
# sandbox starts with an empty neighbour table and under CI load the resolution/flag timing
# missed, false-closing a verified boot's admin window. There is no network lookup of
# Keycloak here at all: no getent, no wget, no ARP, no retry loop, no sleep. A missing,
# empty or malformed token file names no boot — exit 1 with empty stdout, and the callers
# fail closed. The token is not a secret: it is a drift detector, never an authentication
# factor (EKO-1-03/B-02 records the host-control tier), and it never reaches stderr or any
# log; the marker's writer (scripts/keycloak-bootstrap.sh `open_gate`) and the proxy's
# entrypoint both call this same helper, so a marker and a start compare one observation.
set -eu

TOKEN_FILE=/etc/eko/keycloak-boot/token

# `-s`: exists and non-empty. The seed placeholder (`.seed`) is deliberately NOT a token
# file: on a composition whose Keycloak has not started (so has not rotated), this path
# holds nothing and the observation fails closed.
if [ ! -s "$TOKEN_FILE" ]; then
	echo "boot-identity: no boot token at $TOKEN_FILE" >&2
	exit 1
fi

identity="$(cat "$TOKEN_FILE")"
token="$identity"
malformed() {
	echo "boot-identity: malformed boot token at $TOKEN_FILE" >&2
	exit 1
}
# Lower-case hex and hyphens only (also refuses whitespace, embedded newlines, any other
# byte); then the exact UUID segment lengths 8-4-4-4-12. The validation is what the callers
# rely on, not trust in the writer: open_gate re-guards the same alphabet before any
# marker write.
case "$token" in
'' | *[!0-9a-f-]*) malformed ;;
esac
for want in 8 4 4 4; do
	field="${token%%-*}"
	[ "${#field}" -eq "$want" ] || malformed
	token="${token#*-}"
done
[ "${#token}" -eq 12 ] || malformed
printf '%s\n' "$identity"
