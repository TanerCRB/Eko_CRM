#!/bin/sh
# The boot identity of the running Keycloak container, as seen from inside this network:
# the hardware address Keycloak's service name resolves to. Docker assigns it per container
# creation, so it names the current boot exactly: a recreated Keycloak (image swap, force
# recreate) has a different identity even when everything else looks the same.
#
# The identity is obtained by resolving `keycloak`, forcing one TCP attempt to its HTTP port
# (an attempt that is refused still completes the ARP resolution), and reading the resolved
# hardware address back out of the kernel's ARP table. No credential, token or host value
# appears in the output; the result is a MAC address. An unresolvable or unreachable
# Keycloak prints nothing and exits non-zero — callers fail closed on that.
#
# The two small retry loops only cover start-up races (compose may start the proxy moments
# before the Keycloak container exists or its ARP entry resolves). A wrong-but-present
# identity is still a mismatch and keeps the gate closed, so retries cannot open anything.
set -eu

TARGET="${EKO_KEYCLOAK_HOST:-keycloak}"

ip=""
attempt=0
while [ "$attempt" -lt 5 ]; do
	attempt=$((attempt + 1))
	ip="$(getent hosts "$TARGET" 2>/dev/null | awk '$1 !~ /:/ { print $1; exit }')" || ip=""
	[ -n "$ip" ] && break
	sleep 1
done
if [ -z "$ip" ]; then
	echo "boot-identity: cannot resolve $TARGET" >&2
	exit 1
fi

hw=""
attempt=0
while [ "$attempt" -lt 5 ]; do
	attempt=$((attempt + 1))
	wget -q -T 3 -O /dev/null "http://$TARGET:8080/" 2>/dev/null || true
	hw="$(awk -v ip="$ip" '$1 == ip && $3 == "0x2" { print $4; exit }' /proc/net/arp)"
	[ -n "$hw" ] && break
	sleep 1
done
if [ -z "$hw" ]; then
	echo "boot-identity: no resolved ARP entry for $ip" >&2
	exit 1
fi
printf '%s\n' "$hw"
