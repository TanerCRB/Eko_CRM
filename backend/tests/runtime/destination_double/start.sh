#!/bin/sh
# Fresh keys for every double: the host key, the backup account's credential and the
# administrative credential (root, which may delete and overwrite). Synthetic, test-only.
set -eu
rm -f /etc/ssh/ssh_host_*
ssh-keygen -q -t ed25519 -N '' -C eko-double-host -f /etc/ssh/ssh_host_ed25519_key
for account in eko-backup root; do
  rm -f "/keys/$account" "/keys/$account.pub"
  ssh-keygen -q -t ed25519 -N '' -C "eko-double-$account" -f "/keys/$account"
  cp "/keys/$account.pub" "/etc/ssh/authorized_keys/$account"
done
exec /usr/sbin/sshd -D -e
