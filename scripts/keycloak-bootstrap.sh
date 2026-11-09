#!/usr/bin/env bash
# Ordered local/shared bootstrap through the existing composition; no new service or image.

set -Eeuo pipefail
export MSYS2_ARG_CONV_EXCL='*'
trap 'echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

usage() {
  echo "usage: bash scripts/keycloak-bootstrap.sh <env-file> [--evidence <jsonl-path>] [--shared]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
ENV_FILE="$1"
shift
EVIDENCE=""
EKO112_DEVELOPMENT=true
while [ "$#" -gt 0 ]; do
  case "$1" in
    --evidence)
      [ "$#" -eq 2 ] || usage
      EVIDENCE="$2"
      shift 2
      ;;
    --shared)
      EKO112_DEVELOPMENT=false
      shift
      ;;
    *) usage ;;
  esac
done
[ -r "$ENV_FILE" ] || { echo "keycloak-bootstrap: environment file is not readable" >&2; exit 2; }
export EKO112_DEVELOPMENT
export EKO112_USE_BOOTSTRAP="${EKO112_USE_BOOTSTRAP:-false}"
export EKO112_MASTER_BRUTE_FORCE="${EKO112_MASTER_BRUTE_FORCE:-true}"
export EKO112_APPLICATION_IMPORT="${EKO112_APPLICATION_IMPORT:-true}"
export EKO112_APPLICATION_BRUTE_FORCE="${EKO112_APPLICATION_BRUTE_FORCE:-true}"
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
: "${COMPOSE_PROJECT_NAME:?missing project name}"

docker_path() {
  if [[ "$1" =~ ^/(mnt/)?([a-z])/(.*)$ ]]; then
    printf '%s:/%s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
  else
    printf '%s\n' "$1"
  fi
}

DOCKER_ENV_FILE="$(docker_path "$ENV_FILE")"
DOCKER_ROOT="$(docker_path "$ROOT")"
compose() {
  docker compose -p "$COMPOSE_PROJECT_NAME" --env-file "$DOCKER_ENV_FILE" --profile dev "$@"
}

BASELINE="2dcb057f818fd9a1e4142fbf0c71276f542f6ffa"
record() {
  local event="$1"
  if [ -n "$EVIDENCE" ]; then
    printf '{"time":"%s","baseline":"%s","event":"%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$BASELINE" "$event" >> "$EVIDENCE"
  else
    printf '%s\n' "$event"
  fi
}

BACKEND_ID="$(compose ps -q backend)"
[ -n "$BACKEND_ID" ] || { echo "keycloak-bootstrap: backend helper is not running" >&2; exit 1; }
docker cp "$DOCKER_ROOT/scripts/keycloak-bootstrap.py" "$BACKEND_ID:/tmp/eko112-bootstrap.py" >/dev/null
docker cp "$DOCKER_ROOT/identity/eko-realm.json" "$BACKEND_ID:/tmp/eko112-realm.json" >/dev/null
docker cp "$DOCKER_ROOT/identity/eko-role-mapping-policy.json" "$BACKEND_ID:/tmp/eko112-role-mapping-policy.json" >/dev/null

run_mode() {
  local mode="$1" output code event
  set +e
  output="$(compose exec -T \
    -e KC_BOOTSTRAP_ADMIN_USERNAME -e KC_BOOTSTRAP_ADMIN_PASSWORD \
    -e EKO112_BREAKGLASS_ONE_PASSWORD -e EKO112_BREAKGLASS_TWO_PASSWORD \
    -e EKO112_REVIEWER_PASSWORD -e EKO112_ADMINISTRATOR_PASSWORD \
    -e OIDC_CLIENT_SECRET -e EKO112_USE_BOOTSTRAP -e EKO112_DEVELOPMENT \
    -e EKO112_MASTER_BRUTE_FORCE -e EKO112_APPLICATION_IMPORT \
    -e EKO112_APPLICATION_BRUTE_FORCE -e AUTH_ADMIN_HOST -e PROXY_ADMIN_PORT \
    backend python /tmp/eko112-bootstrap.py "$mode" 2>&1)"
  code=$?
  set -e
  if [[ "$output" == *'{"event":"master accounts ready"}'* ]]; then
    compose exec -T proxy touch /data/master-initialized >/dev/null
  fi
  if [ "$code" -ne 0 ]; then
    printf '%s\n' "$output" >&2
    return "$code"
  fi
  while IFS= read -r event; do
    [ -n "$event" ] || continue
    event="$(printf '%s\n' "$event" | sed -E 's/^\{"event":"([^"]+)"\}$/\1/')"
    record "$event"
  done <<< "$output"
}

import_with_kcadm() {
  local keycloak_id
  keycloak_id="$(compose ps -q keycloak)"
  [ -n "$keycloak_id" ] || { echo "keycloak-bootstrap: Keycloak is not running" >&2; return 1; }
  docker cp "$DOCKER_ROOT/identity/eko-realm.json" "$keycloak_id:/tmp/eko112-realm.json" >/dev/null
  compose exec -T -e EKO112_BREAKGLASS_ONE_PASSWORD keycloak bash -c '
    set -e
    /opt/keycloak/bin/kcadm.sh config credentials --server http://127.0.0.1:8080 \
      --realm master --user eko112-breakglass-one \
      --password "$EKO112_BREAKGLASS_ONE_PASSWORD" >/dev/null
    if /opt/keycloak/bin/kcadm.sh get realms/eko >/dev/null 2>&1; then
      /opt/keycloak/bin/kcadm.sh create partialImport -r eko \
        -s ifResourceExists=OVERWRITE -f /tmp/eko112-realm.json
    else
      /opt/keycloak/bin/kcadm.sh create realms -f /tmp/eko112-realm.json
    fi
  '
  compose exec -T -u 0 keycloak rm -f /tmp/eko112-realm.json >/dev/null
  # S-04: `config credentials` above persisted the master-admin session under the container
  # user's home — Keycloak 26.8.1's kcadm writes ~/.keycloak/kcadm.config (probed on this
  # image: HOME=/opt/keycloak as uid 1000), mintable into admin access for the rest of the
  # container's life. The import is the last step that needs it, so the session is torn down
  # next to the /tmp cleanup, under the same user that wrote it.
  compose exec -T keycloak sh -c 'rm -rf "${HOME}/.keycloak"' >/dev/null
  compose exec -T keycloak sh -c 'test ! -e "${HOME}/.keycloak/kcadm.config"' >/dev/null
}

verify_custom_provider() {
  # Live pre-listener checks (ADR-0004 addendum 2026-11-06), never exported flags alone: the
  # running server itself reports the custom same-ID factory as the eventsStore provider, and a
  # carrier event proves the required filtering in the live store. A missing, unselected or
  # unverified provider leaves both listeners closed.
  local factory="org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory"
  # `grep -c` drains the whole log; `grep -q` can exit early and SIGPIPE the writer, which
  # pipefail would turn into a spurious "not active" under a large log.
  local count
  count="$(compose logs keycloak 2>/dev/null | grep -F -c "KC-SERVICES0047: jpa (${factory})")" || count=0
  if [ "$count" -eq 0 ]; then
    echo "keycloak-bootstrap: custom event-store provider not active in the running server" >&2
    exit 6
  fi
  record "custom provider selected"
  run_mode verify
}

keycloak_boot_identity() {
  # ADR-0004 C29 (addendum 2026-11-06): every gate marker names the Keycloak boot whose
  # provider pair this run verified. The identity is the hardware address the running
  # Keycloak container answers with on the composition network (assigned per container
  # creation); the proxy's own helper observes it, so the marker and the entrypoint compare
  # the same view. A later proxy start against a recreated Keycloak finds a mismatch and
  # keeps every listener closed until a bootstrap runs again (R-05/S-03).
  compose exec -T proxy sh /usr/local/bin/eko-keycloak-boot-identity.sh
}

open_gate() {
  local gate="$1" host="$2" port="$3" realm="$4" identity deadline
  identity="$(keycloak_boot_identity)" || {
    echo "keycloak-bootstrap: no Keycloak boot identity for the $gate gate; listeners stay closed" >&2
    return 1
  }
  case "$identity" in
    *[!0-9a-f:]* | '')
      echo "keycloak-bootstrap: unusable Keycloak boot identity for the $gate gate" >&2
      return 1
      ;;
  esac
  compose exec -T proxy sh -c "printf '%s\n' '${identity}' > '/data/${gate}-open'" >/dev/null
  compose restart proxy >/dev/null
  # R-06: the reachability deadline is raised past the healthcheck's own worst case
  # (start_period 30 s + 30 retries x 10 s = 330 s), so a slow-but-serving boot is recorded
  # open; a gate that never serves removes its own marker and re-closes the proxy, so the
  # recorded closed state and the wire agree, and the record names the residual state.
  deadline=$(( $(date +%s) + 420 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if compose exec -T proxy wget --no-check-certificate \
      --header="Host: $host" -qO- \
      "https://$host:$port/realms/$realm/.well-known/openid-configuration" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "keycloak-bootstrap: $gate listener did not become reachable" >&2
  # Residual state of this failed gate: the marker is removed and the proxy restarted onto
  # the closed configuration before the script exits non-zero. The removal runs through a
  # one-off mount of the markers' own volume — a failing proxy may be crash-looping, and
  # `compose exec` cannot reach it between restart attempts; a marker that survives a failed
  # gate must end the run, not be papered over.
  local proxy_image
  proxy_image="$(docker image ls --format '{{.Repository}}:{{.Tag}}' \
    --filter "reference=${COMPOSE_PROJECT_NAME}-proxy:latest" | head -n 1)"
  [ -n "$proxy_image" ] || {
    echo "keycloak-bootstrap: cannot resolve the proxy image to remove the $gate marker" >&2
    return 1
  }
  docker run --rm -v "${COMPOSE_PROJECT_NAME}_proxy-data:/data" --entrypoint sh "$proxy_image" \
    -c "rm -f /data/${gate}-open && test ! -e /data/${gate}-open" >/dev/null || {
    echo "keycloak-bootstrap: the $gate marker could not be removed after the failed gate" >&2
    return 1
  }
  # R-21 (reviewer re-review round 2): the residual state is GATE-SPECIFIC. The admin gate is
  # the first marker written — its failure leaves no marker at all, so no listener serves and
  # "listeners closed" is true. The public gate fails while the ADMIN marker still names the
  # live boot: after the re-close the proxy selects Caddyfile.admin and the admin listener
  # remains open, so the record must name that surviving state, not claim both listeners
  # closed. The re-close restart is part of the claim: a failed restart (old configuration
  # still loaded, marker gone) is recorded and ends the run — `|| true` swallowed exactly
  # that disagreement.
  local residual
  case "$gate" in
    public) residual="admin listener remains open" ;;
    *) residual="listeners closed" ;;
  esac
  if compose restart proxy >/dev/null; then
    record "${gate} verification failed; marker removed; ${residual}"
  else
    record "${gate} verification failed; marker removed; proxy re-close failed; listeners not confirmed closed"
  fi
  return 1
}

RERUN=false
if compose exec -T proxy test -f /data/master-initialized >/dev/null 2>&1; then
  RERUN=true
fi
compose exec -T proxy rm -f /data/admin-open /data/public-open >/dev/null
compose restart proxy >/dev/null

if [ "$RERUN" = false ]; then
  OVERRIDE="$(mktemp "${ENV_FILE}.override.XXXXXX")"
  DOCKER_OVERRIDE="$(docker_path "$OVERRIDE")"
  trap 'rm -f "$OVERRIDE"; echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR
  cat > "$OVERRIDE" <<'YAML'
services:
  keycloak:
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_BOOTSTRAP_ADMIN_USERNAME:?required}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD:?required}
YAML
  compose -f "$DOCKER_ROOT/compose.yaml" -f "$DOCKER_OVERRIDE" up -d --force-recreate --wait \
    --wait-timeout 420 keycloak >/dev/null
  EKO112_USE_BOOTSTRAP=true
  export EKO112_USE_BOOTSTRAP
  run_mode master
  rm -f "$OVERRIDE"
  trap 'echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR
  compose up -d --force-recreate --wait --wait-timeout 420 keycloak >/dev/null
  compose exec -T proxy touch /data/master-initialized >/dev/null
else
  compose up -d --force-recreate --wait --wait-timeout 420 keycloak >/dev/null
  EKO112_USE_BOOTSTRAP=false
  export EKO112_USE_BOOTSTRAP
  run_mode master
fi

verify_custom_provider
open_gate admin "$AUTH_ADMIN_HOST" 8443 master
record "admin listener open"
if [ "$EKO112_APPLICATION_IMPORT" = true ]; then
  import_with_kcadm
fi
run_mode application
open_gate public "$AUTH_HOST" 443 eko
record "public listener open"
if [ "$RERUN" = true ]; then
  record "rerun existing volume live checks complete"
fi
compose exec -T -u 0 backend rm -f \
  /tmp/eko112-bootstrap.py /tmp/eko112-realm.json /tmp/eko112-role-mapping-policy.json >/dev/null
