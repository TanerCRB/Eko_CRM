#!/bin/sh
set -eu

if [ -f /data/public-open ] && [ ! -f /data/admin-open ]; then
	echo "proxy: public listener requires the admin bootstrap gate" >&2
	exit 1
fi

# A gate marker records its gate only for the Keycloak boot the bootstrap verified (ADR-0004
# C29, addendum 2026-11-06: the provider pair is verified before either listener opens on
# every bootstrap, restart and restore). The marker's value is the boot identity — the
# hardware address Docker assigns to the Keycloak container at creation — so a plain
# `compose up`, an image swap or a host reboot re-reads the markers against the CURRENT
# boot: a marker that no longer names it is not an open gate, and every listener stays
# closed until scripts/keycloak-bootstrap.sh verifies the running boot again (R-05/S-03).
# The observation is the same the bootstrap itself used to write the marker (the helper in
# this image), so no host-level or credential-level state enters the proxy.
identity="$(sh /usr/local/bin/eko-keycloak-boot-identity.sh 2>/dev/null)" || identity=""

marker_names_current_boot() {
	[ -s "/data/$1-open" ] || return 1
	[ -n "$identity" ] || return 1
	[ "$(cat "/data/$1-open")" = "$identity" ]
}

if marker_names_current_boot admin && marker_names_current_boot public; then
	config=/etc/caddy/Caddyfile
elif marker_names_current_boot admin; then
	config=/etc/caddy/Caddyfile.admin
else
	if [ -f /data/admin-open ] || [ -f /data/public-open ]; then
		echo "proxy: gate markers do not name the running Keycloak boot; serving closed" >&2
	fi
	config=/etc/caddy/Caddyfile.closed
fi

exec caddy run --config "$config" --adapter caddyfile
