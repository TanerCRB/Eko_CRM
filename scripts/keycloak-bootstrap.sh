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

# --self-test: process-ci sweeps `bash scripts/<name>.sh --self-test` over every script; this
# mode proves the bootstrap's own refusal paths offline. No case starts a container, contacts
# the composition or writes into the repository: (a) and (b) run the script as a sub-process
# that stops before the first compose call; (c) runs this file's own extracted open_gate with
# only the composition side stubbed, so the boot-identity character class is exercised as
# written, never re-implemented here; (d) re-runs the whole self-test from a scratch directory
# and checks nothing was left behind (EKO112_SELFTEST_NESTED bounds the recursion). Live
# composition behavior (marker removal, reachability, residual-state records) is carried by
# backend/tests/runtime, not by these offline cases.
# (e) EKO-1-28 adds the reclose_case block below: the offline selection of the re-close
# arm — which record the unset / empty / failing-restart / active-knob states produce, and
# how many restarts each attempts.
# (f) EKO-2-01 adds the origin_case block: the client root URL's default-port rule, run
# offline against keycloak-bootstrap.py's own application_origin().
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

  # (e) EKO-1-28: the re-close arm's BRANCH SELECTION, run from the same extracted open_gate
  # text as (c) with only the composition side stubbed. A step-counting `date` stub puts the
  # reachability loop past its deadline on the first check (no 420 s wait offline); the
  # compose stub succeeds the first restart and answers the re-close restart with the
  # scenario's rc; `docker` is stubbed so the marker-removal one-off never spawns a
  # container (this mode's contract: no case starts one). The restart-call count pins where
  # the hook reaches: unset or empty, both restarts hit the logged stub; active, the
  # replacement composes answers the re-close before the stub sees it (count 1), and a hook
  # WIDENED to the first restart would drop the count to 0. These cases cannot prove live
  # restart behavior — that is
  # backend/tests/runtime/test_eko128_reclose_failed_branch.py on the real composition.
  reclose_case() {
    # reclose_case <name> <hook-state> <reclose-restart-rc> <expected status line> —
    # hook-state is __unset__ (never set), "" (set empty) or a literal activation value.
    local name="$1" hook="$2" restart_rc="$3" expected="$4"
    local dir events calls status
    dir="$root/reclose"
    rm -rf "$dir"
    mkdir -p "$dir"
    events="$dir/events"
    calls="$dir/calls"
    : > "$events"
    : > "$calls"
    printf '0\n' > "$dir/tick"
    status="$(
      FAKE_IDENTITY="123e4567-e89b-12d3-a456-426614174000"
      FAKE_RESTART_RC="$restart_rc"
      RECLOSE_RESTART_SEEN=0
      # open_gate's marker-removal one-off names the project's volume; the `docker` stub
      # below never spawns it, but the expansion must be defined under `set -u`.
      COMPOSE_PROJECT_NAME=eko-selftest-stub
      unset EKO128_FORCE_RECLOSE_FAIL
      if [ "$hook" != __unset__ ]; then
        EKO128_FORCE_RECLOSE_FAIL="$hook"
        export EKO128_FORCE_RECLOSE_FAIL
      fi
      record() { printf '%s\n' "$1" >> "$events"; }
      compose() {
        printf '%s\n' "$*" >> "$calls"
        case "$1" in
          ps) printf 'fake-proxy-container\n' ;;
          exec)
            # The gate's wget verification fails on every check; the deadline stub below
            # leaves the loop before any retry, so one call is the worst case.
            if [ "${4:-}" = wget ]; then return 1; fi
            ;;
          restart)
            RECLOSE_RESTART_SEEN=$((RECLOSE_RESTART_SEEN + 1))
            if [ "$RECLOSE_RESTART_SEEN" -ge 2 ] && [ "$FAKE_RESTART_RC" != 0 ]; then
              return "$FAKE_RESTART_RC"
            fi
            ;;
        esac
        return 0
      }
      docker() {
        printf 'docker %s\n' "$*" >> "$calls"
        if [ "$1" = inspect ]; then printf 'fake-proxy-image\n'; fi
        return 0
      }
      keycloak_boot_identity() { printf '%s\n' "$FAKE_IDENTITY"; return 0; }
      # First call seeds the deadline, the next already exceeds it: the loop exits at its
      # condition, and the run falls into the failure tail with no real waiting.
      date() {
        local step
        step=$(( $(cat "$dir/tick") + 1 ))
        printf '%s\n' "$step" > "$dir/tick"
        printf '%s\n' "$((step * 1000))"
      }
      eval "$open_gate_src"
      rc=0
      open_gate public auth.localhost 443 eko 2> "$dir/gate.err" || rc=$?
      printf 'rc=%s restarts=%s event=%s\n' "$rc" \
        "$(grep -c '^restart proxy$' "$calls")" \
        "$(tail -n 1 "$events")"
    )"
    if [ "$status" = "$expected" ] \
      && grep -q "did not become reachable" "$dir/gate.err"; then
      ok "$name"
    else
      fail "$name" "status '$status', gate stderr: $(tr '\n' ' ' < "$dir/gate.err")"
    fi
  }
  # Shipped path (K-02): unset and empty are byte-identical — the real restart decides,
  # and a succeeding re-close records the gate-specific residual, never the refusal.
  reclose_case "re-close: unset hook with a succeeding restart records the residual tail" \
    __unset__ 0 \
    "rc=1 restarts=2 event=public verification failed; marker removed; admin listener remains open"
  reclose_case "re-close: empty-string hook behaves as unset" \
    "" 0 \
    "rc=1 restarts=2 event=public verification failed; marker removed; admin listener remains open"
  # The live branch, faithfully simulated: a FAILING re-close restart records the refusal
  # even with the hook absent — the pre-hook behavior of this arm is preserved unchanged.
  reclose_case "re-close: unset hook with a failing restart records the re-close refusal" \
    __unset__ 1 \
    "rc=1 restarts=2 event=public verification failed; marker removed; proxy re-close failed; listeners not confirmed closed"
  # The hook arm: the refusal record WITHOUT a re-close attempt at all (one restart in the
  # call log) — the knob never touches the first restart, and never re-closes while the
  # record claims closure is unconfirmed.
  reclose_case "re-close: active hook skips the restart and records the refusal" \
    fail 0 \
    "rc=1 restarts=1 event=public verification failed; marker removed; proxy re-close failed; listeners not confirmed closed"

  # (f) EKO-2-01 F-1 A: the client root URL is APP_ORIGIN as the backend uses it, a default port dropped
  # and any other kept. Runs this repository's keycloak-bootstrap.py function itself, offline.
  origin_case() {
    local name="$1" raw="$2" expected="$3" got candidate
    local -a python=()
    # The first interpreter that really runs (a Windows store alias answers but runs nothing).
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'pass' >/dev/null 2>&1; then
        python=("$candidate")
        break
      fi
    done
    if [ "${#python[@]}" -eq 0 ] && command -v uv >/dev/null 2>&1 \
      && uv run --no-project python -c 'pass' >/dev/null 2>&1; then
      python=(uv run --no-project python)
    fi
    if [ "${#python[@]}" -eq 0 ]; then
      fail "$name" "no Python interpreter for the offline origin case"
      return
    fi
    # A native Windows interpreter reads Windows paths, not Git Bash ones.
    local script="$ROOT/scripts/keycloak-bootstrap.py"
    if command -v cygpath >/dev/null 2>&1; then script="$(cygpath -m "$script")"; fi
    got="$(APP_ORIGIN="$raw" "${python[@]}" -c 'import importlib.util, sys
spec = importlib.util.spec_from_file_location("b", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.application_origin())' "$script" 2>&1)"
    if [ "$got" = "$expected" ]; then ok "$name"; else fail "$name" "got '$got'"; fi
  }
  origin_case "an https origin on 443 loses the default port" \
    "https://app.example.test:443" "https://app.example.test"
  origin_case "an https origin on another port keeps it" \
    "https://app.example.test:8443" "https://app.example.test:8443"
  origin_case "an http origin on 443 keeps it (443 is not http's default)" \
    "http://app.example.test:443" "http://app.example.test:443"

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
  # EKO-1-28 test-only hook (regression guard for THIS arm, Issue #119; pure addition — the
  # if/else/fi/return lines below are byte-identical to the shipped text). A non-empty
  # EKO128_FORCE_RECLOSE_FAIL answers the re-close restart as failed without the
  # composition being touched, so backend/tests/runtime/test_eko128_reclose_failed_branch.py
  # drives the else branch below — the same shared `record`/`return 1` a real restart fault
  # takes (a hook arm with its own duplicated record would survive deletion of either, which
  # is exactly the guardless state EKO-1-12/R-32 recorded); the --self-test reclose cases
  # exercise the selection offline. The knob is consulted ONLY here — inside the
  # verification-failure tail, after the marker removal — never at the first restart above
  # or anywhere else the gate serves. Unset or empty skips the whole block (house `${VAR:-}`
  # pattern), so every shipped caller — run_bootstrap without overrides, scripts/dev-env.sh,
  # operator runs, --self-test — takes the real `compose restart proxy` decision. The
  # replacement answers `restart proxy` itself: the record says closure is NOT confirmed, so
  # silently re-closing while recording the refusal would fake the wire for the guard's
  # sake, and nothing else can reach `compose` from here — this tail's only later call is
  # the restart below, and the `return 1` ends the run before any other compose call.
  # Nothing guards the knob from being set outside tests (Issue #119 "not proven"); it is
  # test-only by documentation, and its name carries the task identifier.
  if [ -n "${EKO128_FORCE_RECLOSE_FAIL:-}" ]; then
    compose() {
      if [ "${1:-}" = restart ] && [ "${2:-}" = proxy ]; then
        return 1
      fi
      printf 'keycloak-bootstrap: EKO128 re-close hook: unexpected compose call: %s\n' "$*" >&2
      return 2
    }
  fi
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
