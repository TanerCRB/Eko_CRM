#!/usr/bin/env bash
# dev-env.sh — write an untracked environment file of synthetic values for compose.yaml.
#
#   bash scripts/dev-env.sh <path>          # e.g. ../eko-dev.env, outside the checkout
#   bash scripts/dev-env.sh --self-test
#
# The variable list is read from compose.yaml (every `${NAME:?…}`), so the file always holds every
# required variable. A variable whose name marks a secret gets a fresh random value; every other
# one gets the development value below, and an unknown one stops the script, so a new variable is
# never silently left empty. No value is real (ADR-0004-C9, ADR-0005 synthetic-data rule).
#
# Exit codes: 0 = written, 1 = refused (file exists, unknown variable), 2 = usage or the script
# itself failed.

set -Eeuo pipefail
trap 'echo "dev-env: the script itself failed (line $LINENO)" >&2; exit 2' ERR

COMPOSE_FILE="${COMPOSE_FILE_PATH:-$(dirname "$0")/../compose.yaml}"
SECRET_NAME_RE='(PASSWORD|SECRET|KEY|CREDENTIAL|TOKEN)'

dev_value() {
  case "$1" in
    APP_HOST) echo "localhost" ;;
    AUTH_HOST) echo "auth.localhost" ;;
    AUTH_ADMIN_HOST) echo "auth-admin.localhost" ;;
    COMPANY_NETWORK_CIDRS) echo "private_ranges" ;;
    PROXY_PUBLIC_BIND | PROXY_ADMIN_BIND) echo "127.0.0.1" ;;
    PROXY_HTTP_PORT) echo "8080" ;;
    PROXY_HTTPS_PORT) echo "8443" ;;
    PROXY_ADMIN_PORT) echo "9443" ;;
    BACKEND_IMAGE_TAG) echo "0.1.0-$CHECKOUT_ID" ;;
    KC_BOOTSTRAP_ADMIN_USERNAME) echo "eko112-bootstrap-temporary" ;;
    # Under G-2 A no destination exists in development: the scheduled run fails visibly.
    BACKUP_DESTINATION) echo "sftp://eko-backup@destination.invalid:22/incoming" ;;
    *) return 1 ;;
  esac
}

# The same for one checkout on every run, different for two checkouts: the project name and the
# backend image tag derive from it, so two worktrees on one Docker host never share either.
checkout_id() {
  (cd "$(dirname "$1")" && pwd -P) | tr -d '\r\n' | sha256sum | cut -c1-12
}

required_names() {
  tr -d '\r' < "$1" | grep -oE '\$\{[A-Z][A-Z0-9_]*:\?' | sed -E 's/^\$\{//; s/:\?$//' | sort -u
}

random_value() { od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; }

write_env() {
  local compose="$1" target="$2" name value
  [ -r "$compose" ] || { echo "dev-env: cannot read $compose" >&2; return 2; }
  [ ! -e "$target" ] || { echo "dev-env: $target exists; remove it first" >&2; return 1; }
  local names; names="$(required_names "$compose")"
  [ -n "$names" ] || { echo "dev-env: no required variable found in $compose" >&2; return 2; }
  names="$(printf '%s\n' "$names" \
    KC_BOOTSTRAP_ADMIN_USERNAME KC_BOOTSTRAP_ADMIN_PASSWORD \
    EKO112_BREAKGLASS_ONE_PASSWORD EKO112_BREAKGLASS_TWO_PASSWORD \
    EKO112_REVIEWER_PASSWORD EKO112_ADMINISTRATOR_PASSWORD | sort -u)"
  CHECKOUT_ID="$(checkout_id "$compose")"
  local out="COMPOSE_PROJECT_NAME=eko-crm-$CHECKOUT_ID"$'\n'
  while IFS= read -r name; do
    # Written above for every file; compose.yaml requires it as `name:`.
    [ "$name" != COMPOSE_PROJECT_NAME ] || continue
    if [[ "$name" =~ $SECRET_NAME_RE ]]; then
      value="synthetic-$(random_value)"
    elif ! value="$(dev_value "$name")"; then
      echo "dev-env: no development value for $name; add it to dev_value" >&2
      return 1
    fi
    out+="$name=$value"$'\n'
  done <<< "$names"
  (umask 077 && printf '%s' "$out" > "$target")
}

self_test() {
  local dir fails=0; dir="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$dir'" RETURN
  check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }

  printf 'a: ${APP_HOST:?x}\nb: ${DB_PASSWORD:?x}\nc: "${PROXY_HTTP_PORT:?x}"\nd: ${OPTIONAL:-x}\n' > "$dir/c.yaml"
  write_env "$dir/c.yaml" "$dir/one.env"
  check "every required variable is written" "grep -qx 'APP_HOST=localhost' '$dir/one.env' && grep -qx 'PROXY_HTTP_PORT=8080' '$dir/one.env'"
  check "a secret gets a synthetic random value" "grep -qE '^DB_PASSWORD=synthetic-[0-9a-f]{48}$' '$dir/one.env'"
  check "a variable with a default is not written" "! grep -q OPTIONAL '$dir/one.env'"
  write_env "$dir/c.yaml" "$dir/two.env"
  check "two runs give different secrets" "[ \"\$(grep DB_PASSWORD '$dir/one.env')\" != \"\$(grep DB_PASSWORD '$dir/two.env')\" ]"
  check "an existing file is not overwritten" "! write_env '$dir/c.yaml' '$dir/one.env' 2>/dev/null"
  check "one checkout gets one project name on every run" "[ \"\$(grep COMPOSE_PROJECT_NAME '$dir/one.env')\" = \"\$(grep COMPOSE_PROJECT_NAME '$dir/two.env')\" ]"
  mkdir -p "$dir/other" && cp "$dir/c.yaml" "$dir/other/c.yaml"
  write_env "$dir/other/c.yaml" "$dir/other.env"
  check "another checkout gets another project name" "[ \"\$(grep COMPOSE_PROJECT_NAME '$dir/one.env')\" != \"\$(grep COMPOSE_PROJECT_NAME '$dir/other.env')\" ]"
  check "the project name is a valid Compose name" "grep -qxE 'COMPOSE_PROJECT_NAME=eko-crm-[0-9a-f]{12}' '$dir/one.env'"
  printf 'a: ${SOMETHING_NEW:?x}\n' > "$dir/u.yaml"
  check "an unknown non-secret variable stops the script" "! write_env '$dir/u.yaml' '$dir/u.env' 2>/dev/null && [ ! -e '$dir/u.env' ]"
  check "the repository's compose.yaml is covered" "write_env '$COMPOSE_FILE' '$dir/repo.env' && [ -s '$dir/repo.env' ]"

  [ "$fails" -eq 0 ] || { echo "dev-env: $fails self-test case(s) failed" >&2; return 1; }
}

case "${1:-}" in
  --self-test) self_test ;;
  "" | -*) echo "usage: $0 <path> | --self-test" >&2; exit 2 ;;
  *) write_env "$COMPOSE_FILE" "$1" ;;
esac
