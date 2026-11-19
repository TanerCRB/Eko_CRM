# EKO-1-34 K-02 and K-04: fixed-tree probe record (2026-11-18)

This record covers one instrumented run of the fixed tree on the CI runner, taken from the run's
artifact. The cause it tests is the one named in
[`pre-fix-probe-2026-11-17.md`](pre-fix-probe-2026-11-17.md). No result in this record comes from
a local machine, and it claims nothing about production.

## Run

| Field | Value (from the artifact's `run-identity.txt`) |
|---|---|
| Workflow run | 44261867387, attempt 1 (`eko134-probe`) |
| Recorded | 2026-11-18T07:49:32Z |
| Commit the run checked out (`git rev-parse HEAD`) | `5685e327ce6cd28d52a45eb4bb2143cf5c26bbcd` |
| Runner image | `ImageOS=ubuntu26`, `ImageVersion=20261111.196.1`. This is the same image as pre-fix run 44169988387 (G-4). |
| Loop | 20 iterations. Each runs the `both` order (k06, then r01) and the `r01` order (r01 alone). Iterations 01-05 also run the `k02` order (the K-02 module). Every order is a separate pytest invocation: 45 in total. |

**Verdict:** green.
- `verdict.txt` reports `problems=0`.
- All 45 invocations exited 0, with no skip.
- The host recorders covered the whole loop.
- `parse-report.txt`: `ip -ts monitor all` gave 123,538 lines and 79,492 events; `docker events` gave 31,710 lines and 30,280 events.

The probe recorded settle calls through a logging-only plugin, one mark per `settle_host_network`
call: `settle start`, `settle returned applies=<bool> waited=<s> interfaces=<n>`, or
`settle raised <name>`.

## K-02: the cause reproduced on demand (5 repetitions)

Each `k02` invocation ran all four tests of
`tests/runtime/test_eko134_k02_network_change_during_login.py` on one bootstrapped composition.

| Invocation | Pre-fix harness, interference | Fixed harness, interference | Contrast, no interference | Continuous interference | Duration |
|---|---|---|---|---|---|
| it01 k02 | passed | passed | passed | passed | 122.66 s |
| it02 k02 | passed | passed | passed | passed | 123.51 s |
| it03 k02 | passed | passed | passed | passed | 124.08 s |
| it04 k02 | passed | passed | passed | passed | 124.65 s |
| it05 k02 | passed | passed | passed | passed | 126.45 s |

### Pre-fix harness test: ERR_NETWORK_CHANGED raised, bridge unsettled, new veth present

What the artifact shows directly, in every repetition:

| Invocation | Interference veth, created | Its `network connect` (container `…-eko134-prefix`) | Its IPv6 link-local address | `browser_login raised` | Address to error |
|---|---|---|---|---|---|
| it01 | `vethb39dcc4`, 07:57:51.980 | 07:57:52.034 | 07:57:53.852 | 07:57:53.861 | 9.6 ms |
| it02 | `veth7ad7e22`, 08:05:05.043 | 08:05:05.093 | 08:05:07.003 | 08:05:07.011 | 7.9 ms |
| it03 | `vethb77b4e0`, 08:12:25.656 | 08:12:25.705 | 08:12:27.131 | 08:12:27.140 | 8.7 ms |
| it04 | `veth5a74d77`, 08:19:33.852 | 08:19:33.918 | 08:19:35.803 | 08:19:35.809 | 6.2 ms |
| it05 | `veth4c4463a`, 08:26:42.395 | 08:26:42.467 | 08:26:43.963 | 08:26:43.971 | 8.2 ms |

- The composition's own proxy was paused before the interference: one `container pause` of
  `…-proxy-1` per test that holds the login, three per invocation, each matched by an `unpause`.
- The test's hold log line reads `hold: settled at first request False, members [...]`. In all
  five, that member list contains the interference veth named above.
- The host's only change inside the login window was that veth's link-local address. The error
  followed it 6-10 ms later, the same order and gap as the pre-fix flake (11-17 ms).
- Playwright's `pw:api` log for the test shows the first navigation committing
  `navigated to "chrome-error://chromewebdata/"`, which is Chromium's error page. No navigation to
  the auth host follows.

**Not established from captured text (A-02).** The string `ERR_NETWORK_CHANGED` appears nowhere
in the artifact. The test catches the error with `pytest.raises(PlaywrightError)` and then asserts
`"net::ERR_NETWORK_CHANGED" in str(raised.value)`. A passing test therefore means that assertion
held, but the probe captured neither the error object nor its text.
- The artifact directly shows: the test passed, the chrome-error commit, the unsettled bridge with
  the new veth present, and the address 6-10 ms before the raise.
- The error's text rests on the test's own assertion.
- If the human wants the text itself in the record, the test or the probe must log
  `str(raised.value)`.

### Fixed harness test: the same interference, then the fix, then a completed login

| Invocation | Interference veth (`…-eko134-fixed`) | Its link-local address | Settle returned | `browser_login start` | Login |
|---|---|---|---|---|---|
| it01 | `veth946698f` | 07:57:57.819 | 07:57:57.831, `applies=True waited=1.63 interfaces=7` | 07:57:57.831 | returned |
| it02 | `veth743e2ba` | 08:05:10.779 | 08:05:10.784, `waited=1.17 interfaces=7` | 08:05:10.784 | returned |
| it03 | `veth3670e1d` | 08:12:31.931 | 08:12:31.964, `waited=1.99 interfaces=7` | 08:12:31.965 | returned |
| it04 | `veth891122f` | 08:19:40.219 | 08:19:40.238, `waited=1.38 interfaces=7` | 08:19:40.238 | returned |
| it05 | `veth587582e` | 08:26:48.827 | 08:26:48.879, `waited=1.68 interfaces=7` | 08:26:48.879 | returned |

- `interfaces=7` is one more than the six the settle saw without the interference, so the settle
  read the new veth.
- In all five it returned 5-52 ms after that veth's address appeared, and the login started right
  after.
- The hold log line reads `settled at first request True`, with the interference veth among the
  members.

### Contrast and continuous interference

- **Contrast** (pre-fix harness, no interference): passed in all five, with `browser_login`
  returned and `settled at first request True`. Its settle returned `waited=0.00 interfaces=6`.
- **Continuous interference:** in every repetition the settle first returned `applies=True` and
  then `settle raised HostNetworkNotSettled`. That raise is the test's expected, named failure.
  - It is the one `settle_raised` per `k02` invocation in `invocations.tsv`.
  - The test asserts the message `did not settle within 10 s` and an elapsed time in `[10, 15)` s.
  - The marks give 10.148, 10.160, 10.118, 10.121 and 10.163 s from start to raise: bounded, no
    hang.

### K-02 edges (Q-5 A)

The edge assertions (image ids, other projects' ids, leftovers) run in each test's clean-up, and
all 20 tests passed. The Docker event stream agrees with them:
- **No image pulled, tagged or built:** no `image` event between the first K-02 test's call and the
  last one's teardown, in any of the five invocations.
- **Other compose projects:** no container or network lifecycle event of any other project in the
  same span. In this isolated loop no other compose project was up, so this edge is met trivially.
  It is not a contrast against live session compositions.
- **No leftovers:** every interference container (`…-eko134-prefix`, `…-eko134-fixed`,
  `…-eko134-churn0..2`) has one `create` and one `destroy`, and every proxy `pause` has its
  `unpause`. `interfaces-after.txt` shows only the runner's default Docker networks, the same three
  as `interfaces-before.txt`.

K-02 mutations (a) to (c) are QA's to run. This record does not cover them.

## K-04: 20 iterations of both orders, 0 ERR_NETWORK_CHANGED

| Order | Invocations | Tests passed | ERR_NETWORK_CHANGED | HostNetworkNotSettled |
|---|---|---|---|---|
| `both` (k06, then r01) | 20 | 40 / 40 | 0 | 0 |
| `r01` alone | 20 | 20 / 20 | 0 | 0 |

**Settle.** In the 60 K-06 test runs, every settle call returned `applies=True`. That is 60 calls,
none raised and none not applicable, with no `HostNetworkNotApplicable` warning.
- Waited 0.00-0.41 s, mean 0.055 s.
- Interfaces 6 in all 60.

**Timing against the test's own steps (fixed tree):**
- The proxy veth's link-local address came 0.96-1.99 s after the bootstrap's last proxy restart.
- `browser_login start` came 1.54-2.03 s after it. In the pre-fix run that gap was 1.46-1.66 s.
- In all 60, that address appeared before `browser_login start`, by 0.008-0.729 s.

**Login windows.** Not one of the 60 first-redirect windows held an `ip` event. Six held Docker
`exec` events: health checks, which create no interface.

**Contrast with pre-fix run 44169988387** (same image `20261111.196.1`, 20 iterations of `both`):

| | Pre-fix run | Fixed run |
|---|---|---|
| ERR_NETWORK_CHANGED | 5 in 40 test runs (it03 k06, it06 r01, it08 r01, it12 k06, it14 r01) | 0 in 60 |
| Other failures | 1 TimeoutError at the first `wait_for_url` (it05 r01), a different, unexplained symptom | none |
| Proxy veth link-local address during the login's first navigations | 12 of 40 test runs (5 aborted, 1 timed out, 6 passed) | 0 of 60 |

So the green loop has a red contrast and carries proof, in the sense of K-04.

## What this record does not prove

- **The error's text.** That the pre-fix-harness test's error text was `ERR_NETWORK_CHANGED` comes
  from the test's assertion, not from captured text.
- **That the flake is gone everywhere.**
  - The two runtime jobs on the PR head and two consecutive `main` runs (K-05) are separate
    evidence.
  - The release-mode job and the full suite with session compositions up were not looped.
  - Neither was any other runner image.
- **That the it05 TimeoutError of the pre-fix run shared this cause.** It did not recur on the
  fixed tree in 60 test runs, which is consistent with a shared cause but does not show one.
- **That the "other projects unchanged" edge holds with other compositions up.** None was up in
  this loop.
- **That a passing loop rules out masking.** K-03 carries that.
- **The weakening-check skip** (exception EKO-1-34/weakening-1) is the human's recorded decision;
  this record does not judge it.
- **Production, Docker Desktop, or the product's frontend-replacement behaviour.**
