#!/bin/sh
set -eu

if [ -f /data/public-open ] && [ ! -f /data/admin-open ]; then
	echo "proxy: public listener requires the admin bootstrap gate" >&2
	exit 1
fi

if [ -f /data/public-open ]; then
	config=/etc/caddy/Caddyfile
elif [ -f /data/admin-open ]; then
	config=/etc/caddy/Caddyfile.admin
else
	config=/etc/caddy/Caddyfile.closed
fi

exec caddy run --config "$config" --adapter caddyfile
