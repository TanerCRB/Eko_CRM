# EKO-1-34 fix round 1 (R-01): probe-r1 record (2026-11-18)

This record covers the instrumented run that tested the Reviewer's R-01 fix on the CI runner. R-01
said that two K-02 runtime tests depended on runner speed. The values come from the run's job
artifacts and the jobs' set-up logs. Nothing here comes from a local machine, and nothing here
claims production behaviour.

> **Correction, 2026-11-19 (Reviewer finding R-03).** Two readings in the isolation section below
> were too strong. The text below is left as first written.
>
> 1. **The 1.3–2.2 s interval.** It runs from the held first request to the first failure. It is
>    not purely the kernel's address-detection time. `interfered_at` is taken before
>    `interference.new_veth("prefix")` runs, so the interval also contains that call's `docker run`
>    and its bridge-member wait. That part was not measured separately. The kernel's detection is
>    one part of the interval, of unknown share.
> 2. **`in_flight_at < interfered_at < failed_at`.** The first half holds by construction: the hold
>    thread sets `interfered_at` only after `in_flight` is set. So it is a guard on the test's
>    structure, not an observation about the runner.
>    - Probe run 44480047835, mutation o1 (see
>      [`fix-round-1-probe-r2-2026-11-19.md`](fix-round-1-probe-r2-2026-11-19.md)), shows the guard
>      catches a reordering. With the interference moved before the wait, the assertion went red
>      with `in_flight_at` later than `interfered_at`.
>    - The second half (`interfered_at < failed_at`) is observed.

## Run

| Field | Value |
|---|---|
| Workflow run | 44387692426, attempt 1 (`eko134-probe-r1`) |
| Branch | `EKO-1-34-probe-r1` |
| Head (`git rev-parse HEAD` in every job's `run-identity.txt`, and `gh run view`) | `0d6c525c6a4dc2f3c58324b0e9460fee318c46be` |
| Probe commit | `aa150cbaa584d0b0c8313d4020afb147f06a1a7d` |
| Fix checkpoint on the task branch that the probe branch started from | `0f12217554d04346210e965bd9909b0ec60161ae` |
| Runner image | `ubuntu-26.04`, version `20261111.196.1` (the isolation job's set-up log; every job's `ImageVersion` agrees). It is the same image as runs 44169988387 and 44261867387. |
| Kernel, Docker | `7.0.0-1019-azure`, Docker 29.4.2 |

**The probe branch is a throwaway.**
- `EKO-1-34-probe-r1` carried the transient workflow `.github/workflows/eko134-probe-r1.yml`, its
  support files under `.github/eko134-probe-r1/`, and the five mutation patches.
- It was written under the conditions of boundary exception EKO-1-34/boundary-1, as the human
  approved for this branch.
- It is not part of the PR, and none of its files is on the task branch.

## Run conclusion: red, for one reason only

| Job | Conclusion |
|---|---|
| K-02 module in isolation, 5 repetitions | success |
| K-02 module inside the composition job's runtime invocation | success |
| Mutation k02-b | success |
| Mutation k02-b-prime | success |
| Mutation k02-c | success |
| Mutation k02-dad | success |
| Mutation k02-a | **failure** |
| Verdict | **failure** (because k02-a failed) |

**The k02-a job is red because of a defect in the probe's kill matcher, not in the tested
mutation.**
- The mutated test went red exactly as expected. `mutation-k02-a/pytest.log` shows, at the
  `with pytest.raises(PlaywrightError) as raised:` line
  (`test_eko134_k02_network_change_during_login.py:366`):
  `E   Failed: DID NOT RAISE Error`.
- The probe matched for `DID NOT RAISE <class 'playwright._impl._errors.Error'>`. That is the
  wording in the QA notes, but this pytest prints only the class name: `DID NOT RAISE Error`. The
  dad job in the same run shows the same form: `DID NOT RAISE HostNetworkNotSettled`.
- The analyzer therefore reported "the red does not hold the expected kill", and the job and the
  verdict went red.
- The mutation itself was killed: the pre-fix-harness test failed, and the only reason given is
  that the Playwright error was not raised.
- **No re-run was made.** The run stays red on record. Its verdict is red for this reason only.

## Isolation: the K-02 module 5 times, alone

20 of 20 tests passed (4 tests × 5 repetitions).

### Pre-fix-harness test

The values come from the hold log line.
- "Interference started" is the delay from the moment the first document request went out to the
  start of the interference.
- "First failure" is the delay from that same moment to the first failed request.

| Repetition | Settled at first request | Members at first request | Interference veth | Interference started | First failure | Of the first request | Failure after | Settled at failure | Interference veth among the members at failure |
|---|---|---|---|---|---|---|---|---|---|
| 1 | True | 5 veths, without `vethf6e1d64` | `vethf6e1d64` | 0.000 s | `net::ERR_NETWORK_CHANGED` | True | 1.327 s | True | yes (6 members) |
| 2 | True | 5, without `veth344644a` | `veth344644a` | 0.000 s | `net::ERR_NETWORK_CHANGED` | True | 2.150 s | True | yes (6) |
| 3 | True | 5, without `veth3b4b5b6` | `veth3b4b5b6` | 0.000 s | `net::ERR_NETWORK_CHANGED` | True | 1.617 s | True | yes (6) |
| 4 | True | 5, without `veth6ba92ec` | `veth6ba92ec` | 0.000 s | `net::ERR_NETWORK_CHANGED` | True | 1.725 s | True | yes (6) |
| 5 | True | 5, without `vethace3212` | `vethace3212` | 0.000 s | `net::ERR_NETWORK_CHANGED` | True | 2.075 s | True | yes (6) |

- **Order.** The bridge was quiet when the held request went out, and the interference began after
  it. The failure came 1.3–2.2 s later, which is the kernel's address-detection time and not
  runner latency.
- **Asserted.** The test asserts `in_flight_at < interfered_at < failed_at`. The 0.000 s value is
  rounded to milliseconds; the strict order is the test's assertion, and the test passed.
- **Error text.** The failure text `net::ERR_NETWORK_CHANGED` is now logged directly. That closes
  the gap A-02 left open in the 2026-11-18 fixed-tree record.

### Fixed-harness test and contrast

- **Fixed-harness test:** `settled at first request True` in all 5 repetitions. The members already
  included the test's interference veth (6 members), so the fix's settle ran before the login.
- **Contrast** (no interference): `settled at first request True`, with 5 members and no
  interference, in all 5.

### Continuous interference (DAD held by the kernel)

| Repetition | Outcome | Settle start to raise | Pending interface in the message |
|---|---|---|---|
| 1 | `HostNetworkNotSettled` | 10.090 s | `veth4e5a745: link-local address 0xc0` |
| 2 | `HostNetworkNotSettled` | 10.056 s | `vethe19a5da: link-local address 0xc0` |
| 3 | `HostNetworkNotSettled` | 10.066 s | `vethd627bfb: link-local address 0xc0` |
| 4 | `HostNetworkNotSettled` | 10.103 s | `veth192fbd0: link-local address 0xc0` |
| 5 | `HostNetworkNotSettled` | 10.082 s | `vethacd6177: link-local address 0xc0` |

- Every message reads `did not settle within 10 s` and names the test's own veth with its address
  still tentative (flags `0xc0`).
- The elapsed times are the settle plugin's measure of the raising call, 10.06–10.10 s. They lie
  inside the test's asserted bound of `[10, 15)` s; the test's own `elapsed` covers the same call.
- **`dad_transmits` read-back:** the test asserts that the value it reads back is 60
  (`DAD_HOLD_TRANSMITS`), and all five passed. The value itself is not logged. That it was 60 rests
  on the passing assertion.

### Edges (Q-5 A)

The image, other-project and leftover edges are asserted in each test's clean-up, also when the
test body fails. All 20 tests passed, so the edges held in every test: no image changed, no other
project's containers or networks changed, and nothing the interference created remained. The
run's own contrast is mutation k02-c below, where that same edge check went red.

## Full job: the K-02 module inside the composition job's runtime invocation

This job ran ci.yml's `uv run pytest -m "runtime or previous_release" tests/runtime -v`, with live
INFO logging added. Result: **711 passed, 1 error.**

- **K-02 module:** 4 of 4 passed under the load of the full runtime suite.
  - Pre-fix-harness test: `settled at first request True`. Interference veth `veth22a470b`, started
    0.000 s after the first request. First failure `net::ERR_NETWORK_CHANGED`, of the first
    request, 1.440 s after it, with the interference veth among the 6 members at failure.
  - Continuous test: `HostNetworkNotSettled` after 10.101 s, naming the test's veth with address
    flags `0xc0`.
- **The one error, named and not counted:**
  `test_eko115_k06_c13_previous_release_on_the_next_head` errored on set-up with
  "C13 previous-release half: the check itself failed: no token to read the release record".
  - This is the expected red. The probe has no registry login and no record token, by its security
    conditions.
  - It is outside K-02 and was not part of this job's verdict.

## Mutations: one per job, only the named test

| Mutation | Change | Test | Observed red (first line) | Expected kill | Result |
|---|---|---|---|---|---|
| K-02(a) | interference removed: `HeldLogin(interference, page)` | pre-fix harness | `Failed: DID NOT RAISE Error` | the Playwright error is not raised | **killed**, but the job is red because of the matcher defect above |
| K-02(b) | fix reverted at its site: the settle replaced by `host.Outcome(True, "", 0.0, ())` | fixed harness | `playwright._impl._errors.Error: Page.goto: net::ERR_NETWORK_CHANGED at https://localhost:<port>/` | uncaught Playwright error with `net::ERR_NETWORK_CHANGED` | killed |
| K-02(b′) | `settle_host_network` returns at once, before any wait | fixed harness | `playwright._impl._errors.Error: Page.goto: net::ERR_NETWORK_CHANGED at https://localhost:<port>/` | same as (b) | killed |
| K-02(c) | the interference's container clean-up removed | pre-fix harness | `AssertionError: EKO-1-34 K-02 interference edges: (3) interference containers remain: [<container id>]; (3) bridge members differ: ['vetha08ba4e']` | `(3) interference containers remain` | killed |
| dad (new) | the `dad_transmits` write removed from `hold_in_detection` | continuous interference | `Failed: DID NOT RAISE HostNetworkNotSettled` | the settle is not held past its bound | killed |

In the dad mutation, the settle returned normally (`waited=0.97 interfaces=7`). Without the
`dad_transmits` write, a link down/up alone does not keep the address tentative long enough.

## What this record does not prove

- **A green run.** The run is red on record, because of the k02-a matcher defect. Mutation (a) was
  killed according to its log, but the probe's own matcher did not confirm it, and there was no
  re-run.
- **The `dad_transmits` value itself.** It was not logged. Only the passing read-back assertion
  shows it was 60.
- **The release-mode job.** The release-mode runtime job ("runtime tests on the checked images")
  was not run with the K-02 module. Load is shown for the composition job's invocation only, and
  in only one run.
- **The full job's exact load.** It ran without the registry login and record token. So the
  previous-release test errored at set-up instead of running, and the load is slightly less than
  CI's.
- **Other runner images, or a runner whose host does not allow `--privileged --network host`.**
- **The K-02 and K-04 records.** The fixed-tree record of 2026-11-18 stands for K-02 and K-04 as
  run at `5685e327ce6cd28d52a45eb4bb2143cf5c26bbcd`. This record shows the R-01 fix on the same
  image, and does not replace that record's K-04 loop.
- **Production, Docker Desktop, or the product's frontend-replacement behaviour.**
