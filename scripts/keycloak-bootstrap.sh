#!/usr/bin/env bash
# Ordered local/shared bootstrap through the existing composition; no new service or image.

set -Eeuo pipefail
export MSYS2_ARG_CONV_EXCL='*'

cleanup_checked_placement() {
  # The placement-override directory of a release run (EKO-1-26): removed on EVERY exit path —
  # the ERR traps, the named explicit exits after the placement exists, and the success tail.
  # Development runs never set CHECKED_DIR, so the call is a no-op there. Defined before the
  # first trap so any early failure already resolves the name; rm -rf is idempotent, so a path
  # that already cleaned and kept the variable set cannot fail on the repeat.
  if [ -n "${CHECKED_DIR:-}" ]; then
    rm -rf "$CHECKED_DIR"
  fi
}

# The placement-override directory (release runs only) never outlives a failed closed run.
trap 'cleanup_checked_placement; echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"

usage() {
  echo "usage: bash scripts/keycloak-bootstrap.sh <env-file> [--evidence <jsonl-path>] [--shared]" >&2
  exit 2
}

# --self-test: process-ci sweeps `bash scripts/<name>.sh --self-test` over every script; this
# mode proves the bootstrap's own refusal paths offline. No case starts a container, contacts
# the composition or writes into the repository: (a) and (b) run the script as a sub-process
# that stops before the first compose call; (c) runs this file's own extracted open_gate with
# only the composition side stubbed, so the boot-identity character class is exercised as
# written, never re-implemented here; (e) drives the whole script against a recording `docker`
# double on PATH — fake ids, canned provider log line and boot identity, no daemon, container
# or volume — to prove the release-mode keycloak starts carry the checked-images placement
# override and the development ones keep their byte-identical arguments (EKO-1-26 F-1); (d)
# re-runs the whole self-test from a scratch directory
# and checks nothing was left behind (EKO112_SELFTEST_NESTED bounds the recursion). Live
# composition behavior (marker removal, reachability, residual-state records) is carried by
# backend/tests/runtime, not by these offline cases.
self_test() {
  local self self_dir root repo_before open_gate_src out rc status failures=0 total=0
  trap - ERR
  set +e
  # Line 9 already moved the cwd to ROOT, so a relative BASH_SOURCE must be resolved against
  # the launch directory (OLDPWD from that cd), not against ROOT: `cd scripts && bash ./…`
  # and `bash Eko_CRM/scripts/…` from a sibling directory would otherwise build a wrong path.
  self_dir="$(dirname "${BASH_SOURCE[0]}")"
  case "$self_dir" in
    /* | [A-Za-z]:/*) ;; # absolute already (POSIX-style or MSYS drive-style)
    *) self_dir="$OLDPWD/$self_dir" ;;
  esac
  self="$(cd "$self_dir" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  root="$(mktemp -d)"
  repo_before="$(git -C "$ROOT" status --porcelain 2>/dev/null)"

  ok() { total=$((total + 1)); echo "ok   $1"; }
  fail() { total=$((total + 1)); echo "FAIL $1 — $2"; failures=$((failures + 1)); }

  # No argument: the usage line with exit 2 (the same refusal exit (a) asserts).
  out="$(bash "$self" 2>&1)"
  rc=$?
  if [ "$rc" -eq 2 ] \
    && [ "$out" = "usage: bash scripts/keycloak-bootstrap.sh <env-file> [--evidence <jsonl-path>] [--shared]" ]; then
    ok "no argument prints the usage line and exits 2"
  else
    fail "no argument prints the usage line and exits 2" "exit $rc: $out"
  fi

  # (a) A missing environment file is refused with the named message and exit 2, before any
  # compose call: the sub-run's own output shows which line ended it.
  out="$(bash "$self" "$root/does-not-exist.env" 2>&1)"
  rc=$?
  if [ "$rc" -eq 2 ] && [ "$out" = "keycloak-bootstrap: environment file is not readable" ]; then
    ok "a missing environment file is refused with the named message and exit 2"
  else
    fail "a missing environment file is refused with the named message and exit 2" "exit $rc: $out"
  fi

  # (b) An environment file without the composition's required project name (ADR-0004,
  # 2026-10-28) names that variable and stops with the failed-expansion exit, before any
  # compose call. The chmod-000 unreadable variant is not asserted here: read denial is not
  # enforced on this repository's Windows development filesystems, so the case would be a
  # local failure rather than an honest check.
  printf 'AUTH_HOST=auth.localhost\nCOMPANY_NETWORK_CIDRS=private_ranges\n' > "$root/no-project.env"
  out="$(bash "$self" "$root/no-project.env" 2>&1)"
  rc=$?
  if [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q "COMPOSE_PROJECT_NAME: missing project name"; then
    ok "an environment file without COMPOSE_PROJECT_NAME names the variable and exits 1"
  else
    fail "an environment file without COMPOSE_PROJECT_NAME names the variable and exits 1" "exit $rc: $out"
  fi

  # (c) The gate-marker identity checks run the script's own open_gate: the function text is
  # extracted from this file at run time, and only the composition side (compose, record,
  # keycloak_boot_identity) is stubbed. An extraction miss fails the cases below loudly.
  open_gate_src="$(awk '/^open_gate\(\) \{/,/^\}/' "$self")"
  if printf '%s\n' "$open_gate_src" | grep -q "unusable Keycloak boot identity"; then
    ok "open_gate is exercised from this file's own text, not re-implemented"
  else
    fail "open_gate is exercised from this file's own text, not re-implemented" "no open_gate text in $self"
  fi

  identity_case() {
    # identity_case <name> <identity> <reject|accept> — one open_gate run against stubs; the
    # marker file is the stub's recorded call argument, so nothing touches a real /data.
    local name="$1" identity="$2" expect="$3" dir calls
    dir="$root/identity"
    rm -rf "$dir"
    mkdir -p "$dir"
    calls="$dir/calls"
    : > "$calls"
    status="$(
      FAKE_IDENTITY="$identity"
      record() { :; }
      compose() { printf '%s\n' "$*" >> "$calls"; return 0; }
      keycloak_boot_identity() { printf '%s\n' "$FAKE_IDENTITY"; return 0; }
      eval "$open_gate_src"
      rc=0
      open_gate admin auth-admin.localhost 8443 master 2> "$dir/gate.err" || rc=$?
      printf 'rc=%s marker_writes=%s evil=%s\n' "$rc" \
        "$(grep -c admin-open "$calls")" \
        "$([ -e "$dir/evil-marker" ] && echo present || echo absent)"
    )"
    if [ "$expect" = reject ]; then
      if [ "$status" = "rc=1 marker_writes=0 evil=absent" ] \
        && grep -q "unusable Keycloak boot identity" "$dir/gate.err"; then
        ok "$name"
      else
        fail "$name" "status '$status', gate stderr: $(tr '\n' ' ' < "$dir/gate.err")"
      fi
    else
      if [ "$status" = "rc=0 marker_writes=1 evil=absent" ] && grep -qF -- "$identity" "$calls"; then
        ok "$name"
      else
        fail "$name" "status '$status', gate stderr: $(tr '\n' ' ' < "$dir/gate.err")"
      fi
    fi
  }
  identity_case "an empty boot identity keeps the gate marker unwritten" "" reject
  # The embedded command stays data: its invalid characters are outside the UUID character
  # class, it must be refused before any marker write, and its target file must not appear.
  identity_case "a malformed boot identity is refused and stays inert" \
    "123e4567-e89b-12d3-a456-426614174000 \$(touch '$root/identity/evil-marker')" reject
  # ADR-0004-C33 (addendum 2026-11-10): a marker names the per-boot UUID token the Keycloak
  # container rotated at its current start, so the ARP-era hardware-address form is not a
  # usable identity and must be refused before any marker write.
  identity_case "a hardware-address boot identity is refused before the marker write" \
    "02:42:ac:12:00:03" reject
  identity_case "a valid UUID boot identity is accepted and reaches the marker write" \
    "123e4567-e89b-12d3-a456-426614174000" accept

  # (e) Release placement through the recording docker double (EKO-1-26 QA F-1): a bootstrap
  # whose environment exports the checked-image pairs must compose every keycloak start through
  # the same placement override the runtime harness applies (backend/tests/runtime/conftest.py),
  # and must refuse a list naming no image for one of the five families BEFORE any compose call;
  # without the variable the keycloak starts keep exactly the development file arguments. No
  # daemon, container or volume is touched: the double on PATH answers fake ids, the provider
  # log line, a synthetic boot identity and the master-ready event, logs every invocation and
  # copies every -f file it is handed into a snapshot directory. The checked pairs are the
  # synthetic names of ci.yml.
  local checked_five checked_missing placement_path placement_dir
  mkdir -p "$root/bin" "$root/snap.e2"
  cat > "$root/bin/docker" <<'SHIM'
#!/usr/bin/env bash
# recording docker double: logs the call, copies every readable -f file into the snapshot
# directory, answers the canned outputs that let the bootstrap finish offline. Never a daemon.
printf '%s\n' "$*" >> "$EKO112_FAKE_LOG"
if [ "${1:-}" = "compose" ]; then
  shift
  prev=""
  for a in "$@"; do
    if [ "$prev" = "-f" ] && [ -r "$a" ]; then
      mkdir -p "$EKO112_FAKE_SNAP"
      cp -- "$a" "$EKO112_FAKE_SNAP/$(basename -- "$a")" 2>/dev/null
    fi
    prev="$a"
  done
fi
case "$*" in
  *test\ -f\ /data/master-initialized)
    [ "${EKO112_FAKE_RERUN:-false}" = true ] || exit 1 ;;
  *python\ /tmp/eko112-bootstrap.py*) printf '{"event":"master accounts ready"}\n' ;;
  *ps\ -q\ backend) printf 'fake-backend-container\n' ;;
  *ps\ -q\ keycloak) printf 'fake-keycloak-container\n' ;;
  *up\ -d\ --force-recreate\ --wait*)
    if printf '%s' "$*" | grep -q '\.override\.'; then :; else
      [ "${EKO112_FAKE_FAIL_UP2:-false}" = true ] && exit 1
    fi ;;
  *logs\ keycloak*)
    printf '%s\n' 'KC-SERVICES0047: jpa (org.eko_crm.keycloak.events.FilteringJpaEventStoreProviderFactory) is active' ;;
  *eko-keycloak-boot-identity.sh*) printf '123e4567-e89b-12d3-a456-426614174000\n' ;;
esac
exit 0
SHIM
  chmod +x "$root/bin/docker"
  printf 'COMPOSE_PROJECT_NAME=e112-selftest\nAUTH_HOST=auth.localhost\nAUTH_ADMIN_HOST=auth-admin.localhost\n' \
    > "$root/release.env"
  checked_five="backend=eko-crm/backend:checked frontend=eko-crm/frontend:checked proxy=eko-crm/proxy:checked backup=eko-crm/backup:checked keycloak=eko-crm/keycloak:checked"

  out="$(EKO_CHECKED_IMAGES="$checked_five" EKO112_FAKE_LOG="$root/calls.e1" EKO112_FAKE_SNAP="$root/snap.e1" \
    PATH="$root/bin:$PATH" bash "$self" "$root/release.env" 2>&1)"
  rc=$?
  placement_path="$(tr ' ' '\n' < "$root/calls.e1" 2>/dev/null | grep -m1 'checked-images\.yaml$')"
  placement_dir="${placement_path%/*}"
  if [ "$rc" -eq 0 ] \
    && [ "$(grep ' up -d --force-recreate' "$root/calls.e1" \
        | grep -c 'compose\.yaml -f [^ ]*checked-images\.yaml')" = "2" ] \
    && grep -q -- '--profile dev -f [^ ]*\.override\.[^ ]* up' "$root/calls.e1" \
    && sed -n '/^  keycloak:/,+3p' "$root/snap.e1/checked-images.yaml" \
      | grep -qF 'image: eko-crm/keycloak:checked' \
    && sed -n '/^  keycloak:/,+3p' "$root/snap.e1/checked-images.yaml" | grep -qF 'pull_policy: never' \
    && sed -n '/^  keycloak:/,+3p' "$root/snap.e1/checked-images.yaml" | grep -qF 'build: !reset null' \
    && grep -qF 'BACKUP_MANIFEST_KEYCLOAK_IMAGE: eko-crm/keycloak:checked' "$root/snap.e1/checked-images.yaml" \
    && [ -n "$placement_path" ] && [ ! -e "$placement_dir" ]; then
    ok "under EKO_CHECKED_IMAGES both keycloak starts carry the placement override and it leaves no directory behind"
  else
    fail "under EKO_CHECKED_IMAGES both keycloak starts carry the placement override and it leaves no directory behind" \
      "exit $rc, override path '$placement_path', output: $(tr '\n' '|' <<< "$out")"
  fi

  out="$(env -u EKO_CHECKED_IMAGES EKO112_FAKE_LOG="$root/calls.e2" EKO112_FAKE_SNAP="$root/snap.e2" \
    PATH="$root/bin:$PATH" bash "$self" "$root/release.env" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ] \
    && [ "$(grep -c ' up -d --force-recreate' "$root/calls.e2")" = "2" ] \
    && ! grep -q 'checked-images\.yaml' "$root/calls.e2" \
    && ! [ -e "$root/snap.e2/checked-images.yaml" ] \
    && grep -q 'compose\.yaml -f [^ ]*\.override\.[^ ]* up' "$root/calls.e2" \
    && grep -q -- '--profile dev up -d --force-recreate' "$root/calls.e2"; then
    ok "without EKO_CHECKED_IMAGES the keycloak starts keep the development file arguments byte for byte"
  else
    fail "without EKO_CHECKED_IMAGES the keycloak starts keep the development file arguments byte for byte" \
      "exit $rc, output: $(tr '\n' '|' <<< "$out")"
  fi

  checked_missing="backend=eko-crm/backend:checked frontend=eko-crm/frontend:checked proxy=eko-crm/proxy:checked backup=eko-crm/backup:checked"
  out="$(EKO_CHECKED_IMAGES="$checked_missing" EKO112_FAKE_LOG="$root/calls.e3" EKO112_FAKE_SNAP="$root/snap.e3" \
    PATH="$root/bin:$PATH" bash "$self" "$root/release.env" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -q 'names no image for keycloak' \
    && ! [ -s "$root/calls.e3" ]; then
    ok "a checked list naming no keycloak image is refused before any compose call"
  else
    fail "a checked list naming no keycloak image is refused before any compose call" \
      "exit $rc, calls $([ -s "$root/calls.e3" ] && echo present || echo absent), output: $(tr '\n' '|' <<< "$out")"
  fi

  # (e4) Trap window (EKO-1-26 F-3): after the RERUN=false block restores the ERR trap, a failing
  # SECOND keycloak start must still delete the placement directory — the restored text carries
  # the same cleanup arm as the file-top and bootstrap-override texts. The named-exit windows
  # (backend helper, provider not active) are carried by backend/tests/static, not by this file.
  out="$(EKO_CHECKED_IMAGES="$checked_five" EKO112_FAKE_FAIL_UP2=true EKO112_FAKE_LOG="$root/calls.e4" \
    EKO112_FAKE_SNAP="$root/snap.e4" PATH="$root/bin:$PATH" bash "$self" "$root/release.env" 2>&1)"
  rc=$?
  placement_path="$(tr ' ' '\n' < "$root/calls.e4" 2>/dev/null | grep -m1 'checked-images\.yaml$')"
  placement_dir="${placement_path%/*}"
  if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -q 'failed closed' \
    && [ -n "$placement_path" ] && [ ! -e "$placement_dir" ]; then
    ok "a failing second keycloak start under the restored trap removes the placement directory"
  else
    fail "a failing second keycloak start under the restored trap removes the placement directory" \
      "exit $rc, override path '$placement_dir', output: $(tr '\n' '|' <<< "$out")"
  fi

  # (d) The whole self-test re-run from a scratch directory: nothing is left there, and the
  # repository's working state is byte-identical before and after (git porcelain, read-only).
  if [ -z "${EKO112_SELFTEST_NESTED:-}" ]; then
    local scratch leftover repo_after
    scratch="$(mktemp -d)"
    out="$(cd "$scratch" && EKO112_SELFTEST_NESTED=1 bash "$self" --self-test 2>&1)"
    rc=$?
    leftover="$(find "$scratch" -mindepth 1 2>/dev/null | head -n 1)"
    repo_after="$(git -C "$ROOT" status --porcelain 2>/dev/null)"
    if [ "$rc" -eq 0 ] && [ -z "$leftover" ] && [ "$repo_after" = "$repo_before" ]; then
      ok "--self-test from a scratch directory leaves no files behind and mutates nothing"
    else
      fail "--self-test from a scratch directory leaves no files behind and mutates nothing" \
        "exit $rc, leftover '$leftover', repo state '$repo_after' vs '$repo_before'"
    fi
    rm -rf "$scratch"
  fi

  rm -rf "$root"
  echo "Self-test: $total cases ran, $((total - failures)) passed, $failures failed."
  [ "$failures" -eq 0 ]
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

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

# EKO-1-26 (QA F-1): when the environment exports the checked-image pairs (the release-mode job
# does, for the runtime harness too), this bootstrap must compose the SAME placement — otherwise
# a fresh CI runner builds the custom Keycloak image inside the test session (the K-04 guard's
# red, run 42954811816's shape) and a host with a pre-existing anchor starts an image that
# `check-identity` never verified. COMPOSE_PLACEMENT is the file pair the harness gives its
# compositions: the repository file plus the rendered override, passed to every compose call of
# the run. Outside a release run it stays empty and compose() keeps exactly the arguments this
# script has always passed. The override renders in a directory beside the environment file
# (docker_path() translates drive paths for the Compose CLI; a bare /tmp name would not survive
# that translation), and cleanup_checked_placement deletes it on every exit path of the run:
# all three ERR-trap texts, the explicit exits that can fire after its creation (backend
# helper, provider not active, the refusal below) and the tail. Fail closed: a pair list
# naming no image for one of the five families is refused before the run touches the
# composition at all, with the harness's message wording.
CHECKED_DIR=""
COMPOSE_PLACEMENT=()

checked_override_content() {
  # Render the placement override of backend/tests/runtime/conftest.py (checked_images_override):
  # the same service order, the same `build: !reset null` reset form for the built five, the same
  # backup-manifest mirror lines. A static carrier compares the two renderings byte for byte.
  local item service name pair missing
  local -a items=()
  local -A images=()
  read -r -a items <<< "$EKO_CHECKED_IMAGES"
  for item in "${items[@]}"; do
    [[ "$item" == *=* ]] || continue
    images["${item%%=*}"]="${item#*=}"
  done
  missing=""
  for name in backend backup frontend keycloak proxy; do
    [ -n "${images[$name]:-}" ] || missing="${missing:+$missing, }$name"
  done
  if [ -n "$missing" ]; then
    printf 'keycloak-bootstrap: EKO_CHECKED_IMAGES names no image for %s\n' "$missing" >&2
    return 1
  fi
  printf 'services:\n'
  # CHECKED_SERVICES of the harness as "service=image-family" pairs, in its order; BUILT_SERVICES
  # (proxy frontend backup backend keycloak) additionally get their build block reset.
  for pair in "proxy=proxy" "frontend=frontend" "backup=backup" "backend=backend" \
    "migrate=backend" "worker=backend" "keycloak=keycloak"; do
    service="${pair%%=*}"
    name="${pair#*=}"
    printf '  %s:\n    image: %s\n    pull_policy: never\n' "$service" "${images[$name]}"
    case " proxy frontend backup backend keycloak " in
      *" $service "*) printf '    build: !reset null\n' ;;
    esac
    if [ "$service" = "backup" ]; then
      printf '    environment:\n      BACKUP_MANIFEST_BACKEND_IMAGE: %s\n      BACKUP_MANIFEST_KEYCLOAK_IMAGE: %s\n' \
        "${images[backend]}" "${images[keycloak]}"
    fi
  done
}

if [ -n "${EKO_CHECKED_IMAGES:-}" ]; then
  CHECKED_DIR="$(mktemp -d "${ENV_FILE}.checked.XXXXXX")"
  if ! checked_override_content > "$CHECKED_DIR/checked-images.yaml"; then
    cleanup_checked_placement
    CHECKED_DIR=""
    exit 1
  fi
  COMPOSE_PLACEMENT=(-f "$DOCKER_ROOT/compose.yaml" -f "$(docker_path "$CHECKED_DIR/checked-images.yaml")")
fi

compose() {
  docker compose "${COMPOSE_PLACEMENT[@]}" -p "$COMPOSE_PROJECT_NAME" --env-file "$DOCKER_ENV_FILE" --profile dev "$@"
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
# The ERR trap never fires on an explicit exit (EKO-1-26 F-3): exits after the placement exists
# run the cleanup themselves, under their own named codes.
[ -n "$BACKEND_ID" ] || { echo "keycloak-bootstrap: backend helper is not running" >&2; cleanup_checked_placement; exit 1; }
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
    cleanup_checked_placement
    exit 6
  fi
  record "custom provider selected"
  run_mode verify
}

keycloak_boot_identity() {
  # ADR-0004-C33 (addendum 2026-11-10; verification-before-open itself is C34): every gate
  # marker names the Keycloak boot whose provider pair this run verified. The identity is
  # the per-boot token the running Keycloak container rotated as the first act of its
  # current start (compose.yaml entrypoint wrapper); the proxy's own helper reads it from
  # the shared carrier volume — a pure file read, no network lookup of Keycloak — so the
  # marker and the entrypoint compare the same observation. A later proxy start against a
  # restarted or recreated Keycloak finds a mismatch and keeps every listener closed until
  # a bootstrap runs again (R-05/S-03).
  compose exec -T proxy sh /usr/local/bin/eko-keycloak-boot-identity.sh
}

open_gate() {
  local gate="$1" host="$2" port="$3" realm="$4" identity deadline
  identity="$(keycloak_boot_identity)" || {
    echo "keycloak-bootstrap: no Keycloak boot identity for the $gate gate; listeners stay closed" >&2
    return 1
  }
  case "$identity" in
    # The boot token's alphabet: lower-case hex and hyphens (a UUID, ADR-0004-C33). The
    # guard runs before any marker write; anything else — empty, a hardware address, an
    # embedding attempt — keeps the gate closed (the helper validated the shape too; this
    # is the second, marker-writer-side half).
    *[!0-9a-f-]* | '')
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
  # The image is the one the composition's own proxy CONTAINER runs (`Config.Image` of the
  # project's proxy container, read through `ps -a` so it resolves while the entrypoint
  # crash-loops), not the `${COMPOSE_PROJECT_NAME}-proxy:latest` build-tag list: a release
  # run (EKO-1-15 K-02, on the checked images) loads `eko-crm/proxy:checked` with the build
  # config reset, no such tag exists, and the marker removal — the fail-closed half of this
  # very branch — died at image resolution and left the failed gate's marker on the volume
  # (CI runs 42897088542 and 42711869762, release job: the qa fail-closed and r21 reds;
  # reproduced red locally with the pre-fix line restored under the same env — the residual
  # marker survived the failed gate, exactly the state this branch promises is impossible).
  # Resolution still fails closed: no container, no image, no removal, the run ends.
  local proxy_image="" proxy_container=""
  proxy_container="$(compose ps -a -q proxy | head -n 1)"
  if [ -n "$proxy_container" ]; then
    proxy_image="$(docker inspect --format '{{.Config.Image}}' "$proxy_container")" || proxy_image=""
  fi
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
  trap 'rm -f "$OVERRIDE"; cleanup_checked_placement; echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR
  cat > "$OVERRIDE" <<'YAML'
services:
  keycloak:
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_BOOTSTRAP_ADMIN_USERNAME:?required}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD:?required}
YAML
  if [ "${#COMPOSE_PLACEMENT[@]}" -gt 0 ]; then
    # The base file and the placement override already come from compose(); listing the base
    # again here would re-apply its `build:` after the reset and undo the freeze.
    compose -f "$DOCKER_OVERRIDE" up -d --force-recreate --wait --wait-timeout 420 keycloak >/dev/null
  else
    compose -f "$DOCKER_ROOT/compose.yaml" -f "$DOCKER_OVERRIDE" up -d --force-recreate --wait \
      --wait-timeout 420 keycloak >/dev/null
  fi
  EKO112_USE_BOOTSTRAP=true
  export EKO112_USE_BOOTSTRAP
  run_mode master
  rm -f "$OVERRIDE"
  # The restored trap must carry the cleanup arm (EKO-1-26 F-3, window 1): the second keycloak
  # start and every gate after it fail closed under THIS text, bare would leak the directory.
  trap 'cleanup_checked_placement; echo "keycloak-bootstrap: failed closed (line $LINENO)" >&2' ERR
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
# The placement override served every start of this run; it leaves nothing behind (EKO-1-26).
cleanup_checked_placement
