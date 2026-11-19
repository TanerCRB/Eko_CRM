# EKO-1-34 K-01: pre-fix probe record (2026-11-17)

This record covers one instrumented run of the unchanged K-06 tests on the CI runner. It is taken
from the run's artifact. No test result in it comes from a local machine, and it claims nothing
about production.

## Run

| Field | Value (from the artifact's `run-identity.txt`) |
|---|---|
| Workflow run | 44169988387, attempt 1 (`eko134-probe`) |
| Recorded | 2026-11-17T20:30:35Z |
| Commit the run checked out (`git rev-parse HEAD`) | `0496115ee0c637115bf365ed836802ebc9e5bd7e` |
| Probe commit (as the supervisor named it) | `58ab4aabea51acaea6c98bde59f5a1ad968b354a` |
| Runner image | `ImageOS=ubuntu26`, `ImageVersion=20261111.196.1` |
| Kernel, Docker, Compose | `7.0.0-1019-azure`, Docker 29.4.2, Compose 5.1.3 |

- `git merge-base --is-ancestor` confirms that the probe commit is an ancestor of the run's
  commit. The only change between the two is one cost-register line.
- The runner image version comes from the job's `ImageVersion` environment variable, not from the
  set-up log.
- Pre-fix tree: neither `browser_login`, nor the two tests, nor `conftest.py` changed. The timing
  marks come from a logging-only `-p` plugin and from Playwright's `DEBUG=pw:api` log.

**Verdict line:** "iterations: 20 of 20, failed: 6, instrumentation: ok".

**Instrumentation coverage (`parse-report.txt`):**

| Source | Lines read | Events parsed |
|---|---|---|
| `ip -ts monitor all` | 46,874 | 30,533 |
| `docker events` | 18,678 | 17,798 |

The `ip` events parsed are fewer than the lines read because multi-line events are joined into
one.

## How the numbers below were derived

- **Test steps** come from the probe's marks: `run_bootstrap` returned, `provision_browser_account`
  returned, `browser_login start`, and `browser_login raised` or `returned`.
- **Host events** come from `ip -ts monitor all` and `docker events`, on one UTC clock on the same
  host.
- **Last proxy restart** is the last Docker `container restart` event of the test's own
  `ekort-fresh-*-proxy-1` before `browser_login start`.
  - It is the `kill`, `network disconnect`, `stop`, `die`, `network connect`, `start`, `restart`
    sequence of `compose restart proxy`.
  - In every test it is the restart that ends `run_bootstrap`: `run_bootstrap` returns 0.41-0.52 s
    later.
  - The events do not show which script line issued it. The Analyst's reading is `open_gate`'s
    `compose restart proxy`.
- **The event** in this record is the host-side IPv6 link-local address of the restarted proxy's
  new veth. It shows in `ip monitor` as `[ADDR] <veth> inet6 fe80::…/64 scope link proto kernel_ll`,
  followed by its `[ROUTE] local fe80::…` line. The `<veth>` is the one created and attached to the
  test's own `ekort-fresh-*_default` bridge at the proxy's `network connect`.

The artifact's computed window for it03 k06 is wrong: its start is later than its end. The probe
looked for the first `"load" event fired` after `browser_login start` without stopping at
`browser_login raised`, and in it03 the failing `page.goto` never fired `load`. That window was
re-derived by hand from `iteration-03/timeline.txt`. Every other window below matches
`iterations.tsv`.

## The failing iterations

### ERR_NETWORK_CHANGED (5 of 40 test runs)

| It. | Test | Where it failed | Navigation window (UTC) | Host events inside the window | Event to error |
|---|---|---|---|---|---|
| 03 | k06 | `page.goto` of the app origin, before commit | 20:41:02.735 (goto) .. 20:41:02.782 (raised) | `vethb6d65a3` IPv6 link-local ADDR + ROUTE, at 20:41:02.766. Docker: none | 16 ms |
| 06 | r01 | first `wait_for_url`, line 318 | 20:54:04.978 (load) .. 20:54:05.181 (raised) | `veth70e9731` IPv6 link-local ADDR + ROUTE, at 20:54:05.166. Docker: none | 15 ms |
| 08 | r01 | first `wait_for_url` | 21:01:38.609 .. 21:01:38.815 | `vethe0a5b08` IPv6 link-local ADDR + ROUTE, at 21:01:38.799. Docker: none | 17 ms |
| 12 | k06 | first `wait_for_url` | 21:13:41.277 .. 21:13:41.369 | `veth1abe0fb` IPv6 link-local ADDR + ROUTE, at 21:13:41.358. Docker: none | 11 ms |
| 14 | r01 | first `wait_for_url` | 21:21:52.429 .. 21:21:52.635 | `veth0780337` IPv6 link-local ADDR + ROUTE, at 21:21:52.621. Docker: none | 15 ms |

**Where the event came from.** Each veth is the host side of the test's own proxy container,
created by its last restart:

| It. | veth created | veth UP | proxy `network connect` | Bridge |
|---|---|---|---|---|
| 03 | 20:41:01.139 | 20:41:01.177 | 20:41:01.253 | `br-708d3e49f43a` |
| 06 | 20:54:03.264 | 20:54:03.291 | 20:54:03.354 | `br-c9bc794545ea` |
| 08 | 21:01:36.842 | 21:01:36.874 | 21:01:36.941 | `br-0fd80f1611c4` |
| 12 | 21:13:39.557 | 21:13:39.583 | 21:13:39.640 | `br-53236ac9694f` |
| 14 | 21:21:50.761 | 21:21:50.793 | 21:21:50.852 | `br-92f6bde026a9` |

Each `network connect` attaches the test's own `ekort-fresh-<id>_default` network to its
`ekort-fresh-<id>-proxy-1`. The link-local address appeared 1.59-1.93 s after the veth came UP.

**What the windows held.**
- Inside every failing window, those two `ip` lines are the **only** host events. There is no
  Docker event and no other interface, address or route change.
- The other compose projects were idle: no session composition runs in this isolated loop.
- Short excerpt (it06; MAC-derived address suffix elided):
  `20:54:05.166378Z ip [ADDR]295: veth70e9731 inet6 fe80::…/64 scope link proto kernel_ll`, then
  `20:54:05.181170Z mark browser_login raised`.
- The first window that failed (it03) failed at `page.goto`, before commit. All eight earlier CI
  failures and the other four here failed at the first `wait_for_url`. Both are document
  navigations in flight on the login's first redirect chain.

### it05 r01: a TimeoutError, reported separately

`TimeoutError: Timeout 30000ms exceeded.` at `eko201_login.py:318`, the same first `wait_for_url`.

**What the timeline shows.**
- The same event, from the same source, during the same login: the `veth66b233b` IPv6
  link-local ADDR + ROUTE at 20:49:47.118.
- It is the restarted proxy's veth: created 20:49:45.473, UP 20:49:45.499, then
  `network connect` of `ekort-fresh-6d22327f-proxy-1` at 20:49:45.558.
- It came 10 ms after the `page.goto` of the app origin committed and before `load`.
- `page.goto` then completed: `load` at 20:49:47.138 and `networkidle` at 20:49:47.668.
- The application never started the redirect to the auth host. There is no further `pw:api`
  navigation line until the 30 s timeout.

**Classification.** This is **not counted as ERR_NETWORK_CHANGED**. It is a different symptom.
- A plausible reading: the same event aborted one of the page's sub-requests rather than the
  document navigation, so the page never started the redirect. That reading is **not
  established**. The probe recorded no request-failure or console events, so which request
  failed, if any, is not in the evidence.
- It is not the pool-exhausted 503 (#188) and not `__Host-eko_session not set` (EKO-1-33). No such
  text is in the iteration's log.

## Contrast: the 34 passing test runs

The other 34 test runs passed. it05 r01 is excluded, as above. In every one of the 40 test runs,
the restarted proxy's veth got its link-local address 0.97-1.97 s after the last proxy restart.

**Login windows that contain the same event without aborting.** Six passing runs have the same
kind of event inside the login's first navigations:

| It. | Test | Phase in which the event landed | Event relative to the next step |
|---|---|---|---|
| 07 | r01 | the redirect chain, 211 ms after `load` | 21 ms before the auth-host commit |
| 11 | r01 | the redirect chain, 200 ms after `load` | 26 ms before the auth-host commit |
| 17 | k06 | the redirect chain, 223 ms after `load` | 11 ms before the auth-host commit |
| 19 | r01 | the redirect chain, 229 ms after `load` | 39 ms before the auth-host commit |
| 13 | r01 | after the app document committed | 11 ms after commit, 57 ms before `load` |
| 20 | k06 | after the app document committed | 20 ms after commit, 49 ms before `load` |

In 07, 11, 17 and 19 that is the K-01 window, from `load` to the auth-host commit. The other 30
passing runs had no `ip` event in that window. The event landed before `browser_login start` or
after the auth-host commit.

Docker events did appear inside four passing K-01 windows: it07, it09, it18 and it19, all r01.
They are health-check `exec_create`, `exec_start` and `exec_die` events of the test's own postgres
or frontend container, which create no interface. No such event is inside any failing window.

**Why these did not abort is not proven.** No Chromium net-log was taken. The timing is consistent
with this reading:
- In the four failing `wait_for_url` cases the event came 80-192 ms after `load`. In the four
  passing ones it came 200-229 ms after `load`. In the passing ones the auth host's response had
  most likely arrived already, and the commit 11-39 ms later is the renderer's work.
- In it13 and it20 the document had already committed, so only sub-requests could be affected.
  it05 r01 is the same position, 10 ms after commit, and it ended in the timeout.

So the record does **not** say the event always aborts. It says that every abort was preceded,
11-17 ms earlier, by this event and by no other host event.

## Timing relative to the test's own steps

Ranges are over all 40 test runs. Failing runs are listed where they differ.

| Step | Timing |
|---|---|
| Last keycloak container start, before `browser_login start` | 33.4-43.2 s. It is not near the window. |
| Last proxy restart, then `run_bootstrap` returns | +0.41 to +0.52 s |
| `provision_browser_account` returned, before `browser_login start` | 0.86-1.00 s (Chromium launch and context set-up) |
| Last proxy restart, then `browser_login start` | +1.46 to +1.66 s |
| Last proxy restart, then the veth's IPv6 link-local address | +0.97 to +1.97 s. Failing runs: it03 +1.50, it05 +1.55, it06 +1.80, it08 +1.84, it12 +1.71, it14 +1.76 s |
| The address, relative to `browser_login start` | -0.60 to +0.47 s. Failing runs: +0.04 to +0.33 s |

The login's first navigations take about 0.10-0.42 s from `browser_login start` to the auth-host
commit. The address arrives on a random-looking schedule 1-2 s after the restart, and the login
starts about 1.5 s after the restart. The two therefore overlap in a sizeable share of runs.

## Named cause (for the human to confirm under K-01)

The record names `ERR_NETWORK_CHANGED` as caused by **the host-side IPv6 link-local address
(`[ADDR] … inet6 fe80::/64 scope link proto kernel_ll`, with its local route) of the new veth that
the bootstrap's last `compose restart proxy` creates for the test's own proxy container.**
- The address appears 1.6-1.9 s after the veth comes up.
- When it lands while a document navigation of `browser_login`'s first redirect chain is in
  flight, the navigation fails 11-17 ms later.
- The source is the harness's sequencing. The `fresh` fixture's composition is bootstrapped inside
  the test, and the browser login starts about 1.5 s after the last proxy restart, before the
  host's view of that restart has settled.
- **The cause site is the `fresh` fixture's sequencing** (the test's own composition), not the
  runner and not the session compositions.

This is an observed correlation in 5 of 5 failures with a named source and a 34-run contrast. The
mechanism inside Chromium was not instrumented: no net-log was taken, and the claim that its Linux
address tracker treats a new link-local address as a network change is not observed here. K-02 is
what must show the cause on demand.

## What this record does not prove

- That the event causes the abort. It shows the event and the abort together, in that order, in
  5 of 5 cases, with no competing host event. K-02 must reproduce it.
- Why six windows with the same event passed (see the contrast section).
- That it05's timeout has this cause.
- Anything for the release-mode job, the full suite with session compositions up, other runner
  image versions, or Docker Desktop on Windows.
  - On Docker Desktop the veths live in a VM. That this makes local runs unable to show it is an
    unverified expectation.
- Anything about production or the product's frontend-replacement behaviour.
