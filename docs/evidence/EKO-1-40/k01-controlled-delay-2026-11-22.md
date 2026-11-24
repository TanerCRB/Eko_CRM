# EKO-1-40 K-01: the controlled checkout delay, its contrasts and its magnitudes (2026-11-22)

Local evidence from one Windows host (`DESKTOP-B7OHL9E`; tree and host notes as in
[`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md)). No load was added to any run
in this file, but other sessions' Docker work ran on the host the whole time.

The delay is `backend/tests/support/eko140_checkout_delay.py`. Once a request of a process holds
the session's refresh lock, every session-store checkout of that process keeps its connection
`DELAY_SECONDS` (0.2 s) longer after acquiring it: `find`, `refresh_holder`, and every probe. No
checkout before that instant is delayed. `create_delayed_on_non_holder` applies the same delay
instead on the process whose request found the lock taken and that holds no lock itself.
`EKO140_DELAY_SECONDS` replaces the magnitude for the recorded runs below; the tests never set it.

## The named test, 10 invocations

`uv run pytest -m runtime tests/runtime/eko201/test_eko140_k01_checkout_delay.py -q -rA`, 10
consecutive invocations between 17:16:11Z and 17:26:54Z, every one exiting 0:

| Test | Passed (S asserted from the record, delay in effect on the holder's process only) |
|---|---|
| `test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]` | 10 of 10 |
| `test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]` | 10 of 10 |
| `test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find` | 10 of 10 (holder on b, asserted) |

**Seen failing first (M-1):** with `DELAY_SECONDS = 0.0` in the module (17:15:04Z), all three
failed with `Failed: DID NOT RAISE AssertionError`. The carrier went green, so S was absent. The
value was then set back to 0.2.

**Holder on b:** left to the race, the holder was on process a in every delayed run recorded for
this task in which the race decided (64 of 64 below: every delayed set except the forced
schedules of [`fix-attempts-2026-11-22.md`](fix-attempts-2026-11-22.md)). Process a's pool is warm from the login. The edge is therefore
covered by the forced twin (request 1 sent first, as in EKO-1-38's
`test_eko138_qa_holder_on_b.py`). Its one change against the carrier body is the send order. One
real undelayed loaded red shows S with the holder on b (run set A, run 2, in
[`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md)).

## Recorded runs (temporary harness, [README](README.md#the-harness))

| Set | Factory, delay | Runs | Red with S | Red without S | Green |
|---|---|---|---|---|---|
| First delayed runs, from 16:04Z | on holder, 0.2 s | 6 (3 × both bodies) | 6 | 0 | 0 |
| Contrast (1a), interleaved with the delayed runs | `eko138_observed_app:create_with_blockers` (no delay layer) | 20 (10 × both bodies) | 0 | 0 | 20 |
| Delayed, interleaved with (1a) | on holder, 0.2 s | 20 | 20 | 0 | 0 |
| Contrast (1b), interleaved with the delayed runs | on holder, `EKO140_DELAY_SECONDS=0` | 10 (5 × both bodies) | **1** | 0 | 9 |
| Delayed, interleaved with (1b) | on holder, 0.2 s | 10 | 10 | 0 | 0 |
| Contrast (2) | on the non-holder process only, 0.2 s | 10 (5 × both bodies) | 0 | **10** | 0 |
| Magnitude | on holder, 0.05 s | 6 | 1 | 0 | 5 |
| Magnitude | on holder, 0.1 s | 6 | 6 | 0 | 0 |
| Magnitude | on holder, 0.15 s | 6 | 6 | 0 | 0 |

"Green" in a recorded run means the settle passed and all ten answered 200. The harness did not
re-check the carrier's other assertions.

What the contrasts show:

- **(1) Delay 0.** 29 of 30 undelayed runs had no S. The one with S is run 9 of (1b) (16:59:56Z):
  its undelayed checkouts lasted up to 0.52 s, against 0.00 – 0.06 s in the neighbouring delay-0
  runs. That is a host latency spike, and its record is in
  [`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md). So K-01's "10 of 10 without
  S on a quiet host" was not met as written, because this host was not quiet. The miss itself is
  the cause appearing without the delay.
- **(2) Non-holder only.** There was no S in 10 of 10 runs, so the explanation is not refuted by
  K-01's rule. **But every one of those runs went red** with a 503 from `find` on the delayed
  non-holder process: one request per run, `unavailable` after 0.500 – 0.516 s, before any
  blocker. That process has **two** free connections and five requests that probe. So the single
  free connection makes the holder's process the more exposed one (it fails at every delay of at
  least 0.1 s). It is not a necessary condition. The cause is checkout latency against the waiters'
  probes and a non-retried `find` bounded at 0.5 s, on either process. The Issue should say so
  rather than claim the single free connection as the whole cause.
- **Magnitude.** S appears in every run from 0.1 s up and in 1 of 6 runs at 0.05 s. The 0.2-s
  delay of the test sits inside the range of the real loaded checkout durations (K-07, in the
  [README](README.md)).

Mutations M-2 (the delay holds no connection) and M-3 (the unbounded factory) were not run here;
they are QA's.

## Runs

First delayed runs (on holder, 0.2 s):

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:04:36 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/4: 0.516 a/6: 0.516 | 0.2/11, 0.2/0 | 0:0.172 2:0.266 4:0.516x 6:0.516x 8:0.640 | 1:0.203 3:0.218 5:0.281 7:0.188 9:0.235 |
| 2 | 16:04:54 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/0: 0.500 | 0.2/11, 0.2/0 | 0:0.500x 2:0.078 4:0.047 6:0.375 8:0.453 | 1:0.094 3:0.063 5:0.094 7:0.047 9:0.078 |
| 3 | 16:05:16 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.515 a/8: 0.515 | 0.2/11, 0.2/0 | 0:0.640 2:0.218 4:0.000 6:0.515x 8:0.515x | 1:0.063 3:0.031 5:0.015 7:0.031 9:0.015 |
| 4 | 16:05:33 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/0: 0.500 a/6: 0.500 | 0.2/10, 0.2/0 | 0:0.500x 2:0.703 4:0.266 6:0.500x 8:0.031 | 1:0.063 3:0.063 5:0.094 7:0.110 9:0.094 |
| 5 | 16:05:55 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.500 a/8: 0.500 a/4: 0.515 | 0.2/6, 0.2/0 | 0:0.547 2:0.172 4:0.515x 6:0.500x 8:0.500x | 1:0.609 3:0.344 5:0.359 7:0.266 9:0.250 |
| 6 | 16:06:15 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.516 | 0.2/11, 0.2/0 | 0:0.015 2:0.250 4:0.516x 6:0.594 8:0.656 | 1:0.093 3:0.063 5:0.094 7:0.016 9:0.047 |

Contrast (1a) interleaved with the delayed runs:

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:45:20 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.093 2:0.016 4:0.047 6:0.546 8:0.140 | 1:0.172 3:0.172 5:0.125 7:0.250 9:0.375 |
| 2 | 16:45:42 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/4: 0.516 a/8: 0.500 | 0.2/11, 0.2/0 | 0:0.234 2:0.032 4:0.516x 6:0.625 8:0.500x | 1:0.016 3:0.078 5:0.031 7:0.016 9:0.032 |
| 3 | 16:46:00 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.109 2:0.219 4:0.297 6:0.016 8:0.422 | 1:0.156 3:0.204 5:0.125 7:0.110 9:0.204 |
| 4 | 16:46:19 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/0: 0.500 | 0.2/11, 0.2/0 | 0:0.500x 2:0.015 4:0.218 6:0.532 8:0.625 | 1:0.031 3:0.047 5:0.031 7:0.015 9:0.031 |
| 5 | 16:46:35 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.032 2:0.062 4:0.094 6:0.078 8:0.093 | 1:0.094 3:0.015 5:0.047 7:0.047 9:0.031 |
| 6 | 16:46:52 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.516 a/2: 0.516 | 0.2/7, 0.2/0 | 0:0.016 2:0.516x 4:0.687 6:0.516x 8:0.219 | 1:0.063 3:0.031 5:0.016 7:0.047 9:0.031 |
| 7 | 16:47:10 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.046 2:0.078 4:0.140 6:0.078 8:0.203 | 1:0.110 3:0.078 5:0.156 7:0.062 9:0.125 |
| 8 | 16:47:37 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.500 | 0.2/12, 0.2/0 | 0:0.015 2:0.219 4:0.500x 6:0.500 8:0.625 | 1:0.062 3:0.000 5:0.016 7:0.016 9:0.016 |
| 9 | 16:47:51 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.016 2:0.046 4:0.062 6:0.078 8:0.094 | 1:0.047 3:0.093 5:0.109 7:0.031 9:0.047 |
| 10 | 16:48:05 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.516 a/4: 0.516 | 0.2/11, 0.2/0 | 0:0.000 2:0.219 4:0.516x 6:0.516x 8:0.625 | 1:0.047 3:0.063 5:0.016 7:0.016 9:0.016 |
| 11 | 16:48:21 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.063 2:0.047 4:0.015 6:0.016 8:0.046 | 1:0.094 3:0.031 5:0.031 7:0.000 9:0.015 |
| 12 | 16:48:35 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/2: 0.500 | 0.2/12, 0.2/0 | 0:0.016 2:0.500x 4:0.625 6:0.547 8:0.218 | 1:0.016 3:0.016 5:0.016 7:0.078 9:0.062 |
| 13 | 16:48:49 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.016 2:0.031 4:0.031 6:0.047 8:0.062 | 1:0.078 3:0.015 5:0.000 7:0.031 9:0.047 |
| 14 | 16:49:05 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/8: 0.500 a/0: 0.500 | 0.2/11, 0.2/0 | 0:0.500x 2:0.016 4:0.687 6:0.234 8:0.500x | 1:0.032 3:0.031 5:0.016 7:0.078 9:0.016 |
| 15 | 16:49:35 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.015 2:0.016 4:0.032 6:0.000 8:0.032 | 1:0.000 3:0.062 5:0.016 7:0.031 9:0.016 |
| 16 | 16:49:51 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/2: 0.516 | 0.2/12, 0.2/0 | 0:0.235 2:0.516x 4:0.016 6:0.578 8:0.625 | 1:0.078 3:0.016 5:0.031 7:0.032 9:0.032 |
| 17 | 16:50:05 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.000 2:0.032 4:0.047 6:0.016 8:0.031 | 1:0.047 3:0.016 5:0.016 7:0.016 9:0.016 |
| 18 | 16:50:22 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/4: 0.516 a/6: 0.515 | 0.2/11, 0.2/0 | 0:0.234 2:0.000 4:0.516x 6:0.515x 8:0.625 | 1:0.032 3:0.016 5:0.078 7:0.031 9:0.031 |
| 19 | 16:50:49 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.016 2:0.031 4:0.046 6:0.016 8:0.031 | 1:0.063 3:0.031 5:0.015 7:0.047 9:0.031 |
| 20 | 16:51:04 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 | 0.2/12, 0.2/0 | 0:0.016 2:0.235 4:0.641 6:0.516 8:0.516x | 1:0.015 3:0.063 5:0.062 7:0.015 9:0.031 |
| 21 | 16:51:19 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.016 2:0.016 4:0.047 6:0.062 8:0.031 | 1:0.063 3:0.015 5:0.031 7:0.015 9:0.015 |
| 22 | 16:51:34 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.516 a/2: 0.516 | 0.2/10, 0.2/0 | 0:0.219 2:0.516x 4:0.016 6:0.516x 8:0.641 | 1:0.063 3:0.031 5:0.015 7:0.015 9:0.015 |
| 23 | 16:52:10 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.016 2:0.047 4:0.031 6:0.015 8:0.016 | 1:0.063 3:0.078 5:0.031 7:0.015 9:0.031 |
| 24 | 16:52:27 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 a/4: 0.515 | 0.2/9, 0.2/0 | 0:0.094 2:0.312 4:0.515x 6:0.579 8:0.516x | 1:0.172 3:0.141 5:0.047 7:0.063 9:0.031 |
| 25 | 16:52:52 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.000 2:0.016 4:0.047 6:0.062 8:0.031 | 1:0.031 3:0.063 5:0.031 7:0.015 9:0.031 |
| 26 | 16:53:07 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.516 a/8: 0.500 | 0.2/11, 0.2/0 | 0:0.016 2:0.516x 4:0.234 6:0.625 8:0.500x | 1:0.016 3:0.016 5:0.062 7:0.078 9:0.016 |
| 27 | 16:53:22 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.016 2:0.032 4:0.047 6:0.016 8:0.000 | 1:0.063 3:0.063 5:0.031 7:0.031 9:0.016 |
| 28 | 16:53:36 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.500 | 0.2/12, 0.2/0 | 0:0.235 2:0.016 4:0.641 6:0.532 8:0.500x | 1:0.015 3:0.015 5:0.063 7:0.015 9:0.031 |
| 29 | 16:53:51 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.046 2:0.031 4:0.000 6:0.031 8:0.062 | 1:0.078 3:0.032 5:0.016 7:0.047 9:0.032 |
| 30 | 16:54:04 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/0: 0.500 a/6: 0.500 | 0.2/11, 0.2/0 | 0:0.500x 2:0.015 4:0.219 6:0.500x 8:0.625 | 1:0.047 3:0.015 5:0.015 7:0.015 9:0.000 |
| 31 | 16:54:18 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.016 2:0.047 4:0.031 6:0.015 8:0.079 | 1:0.016 3:0.015 5:0.031 7:0.031 9:0.078 |
| 32 | 16:54:36 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.516 | 0.2/12, 0.2/0 | 0:0.218 2:0.015 4:0.516x 6:0.532 8:0.625 | 1:0.015 3:0.015 5:0.047 7:0.015 9:0.015 |
| 33 | 16:54:52 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.063 4:0.078 6:0.078 8:0.047 | 1:0.015 3:0.047 5:0.078 7:0.031 9:0.031 |
| 34 | 16:55:09 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.516 a/4: 0.516 | 0.2/11, 0.2/0 | 0:0.656 2:0.516x 4:0.516x 6:0.031 8:0.250 | 1:0.078 3:0.016 5:0.031 7:0.031 9:0.016 |
| 35 | 16:55:23 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.000 2:0.032 4:0.031 6:0.016 8:0.031 | 1:0.063 3:0.015 5:0.062 7:0.031 9:0.015 |
| 36 | 16:55:40 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.516 | 0.2/12, 0.2/0 | 0:0.000 2:0.219 4:0.516x 6:0.547 8:0.641 | 1:0.015 3:0.047 5:0.015 7:0.062 9:0.031 |
| 37 | 16:55:55 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.031 4:0.031 6:0.000 8:0.046 | 1:0.063 3:0.031 5:0.015 7:0.031 9:0.031 |
| 38 | 16:56:11 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.516 a/8: 0.516 | 0.2/10, 0.2/0 | 0:0.016 2:0.656 4:0.234 6:0.516x 8:0.516x | 1:0.078 3:0.000 5:0.031 7:0.032 9:0.016 |
| 39 | 16:56:33 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.047 2:0.094 4:0.141 6:0.015 8:0.062 | 1:0.094 3:0.125 5:0.078 7:0.062 9:0.016 |
| 40 | 16:56:47 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 | 0.2/12, 0.2/0 | 0:0.625 2:0.219 4:0.016 6:0.531 8:0.516x | 1:0.015 3:0.062 5:0.063 7:0.015 9:0.015 |

Contrast (1b), delay 0 against 0.2 s on the same factory, interleaved:

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:58:05 | `create_delayed_on_holder` | on-time | a | green | none | 0.0/0, 0.0/0 | 0:0.031 2:0.000 4:0.047 6:0.047 8:0.031 | 1:0.047 3:0.015 5:0.062 7:0.031 9:0.015 |
| 2 | 16:58:18 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/6: 0.516 a/8: 0.516 | 0.2/11, 0.2/0 | 0:0.000 2:0.219 4:0.625 6:0.516x 8:0.516x | 1:0.047 3:0.015 5:0.032 7:0.031 9:0.015 |
| 3 | 16:58:31 | `create_delayed_on_holder` | one-late | a | green | none | 0.0/0, 0.0/0 | 0:0.016 2:0.000 4:0.032 6:0.016 8:0.032 | 1:0.047 3:0.016 5:0.000 7:0.063 9:0.016 |
| 4 | 16:58:45 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/2: 0.516 | 0.2/12, 0.2/0 | 0:0.219 2:0.516x 4:0.000 6:0.500 8:0.609 | 1:0.047 3:0.015 5:0.015 7:0.015 9:0.015 |
| 5 | 16:58:59 | `create_delayed_on_holder` | on-time | a | green | none | 0.0/0, 0.0/0 | 0:0.047 2:0.016 4:0.047 6:0.016 8:0.031 | 1:0.015 3:0.000 5:0.063 7:0.031 9:0.015 |
| 6 | 16:59:13 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.500 a/6: 0.515 | 0.2/11, 0.2/0 | 0:0.016 2:0.500x 4:0.234 6:0.515x 8:0.625 | 1:0.062 3:0.032 5:0.016 7:0.078 9:0.032 |
| 7 | 16:59:26 | `create_delayed_on_holder` | one-late | a | green | none | 0.0/0, 0.0/0 | 0:0.015 2:0.016 4:0.016 6:0.016 8:0.016 | 1:0.032 3:0.015 5:0.032 7:0.015 9:0.000 |
| 8 | 16:59:39 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/0: 0.515 | 0.2/12, 0.2/0 | 0:0.515x 2:0.234 4:0.031 6:0.547 8:0.641 | 1:0.015 3:0.016 5:0.078 7:0.015 9:0.016 |
| 9 | 16:59:56 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/8: 0.516 | 0.0/0, 0.0/0 | 0:0.062 2:0.281 4:0.515 6:0.390 8:0.516x | 1:0.406 3:0.250 5:0.187 7:0.172 9:0.266 |
| 10 | 17:00:17 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/4: 0.515 a/8: 0.500 | 0.2/11, 0.2/0 | 0:0.031 2:0.265 4:0.515x 6:0.672 8:0.500x | 1:0.094 3:0.156 5:0.094 7:0.109 9:0.109 |
| 11 | 17:00:32 | `create_delayed_on_holder` | one-late | a | green | none | 0.0/0, 0.0/0 | 0:0.016 2:0.047 4:0.031 6:0.000 8:0.047 | 1:0.032 3:0.016 5:0.062 7:0.016 9:0.032 |
| 12 | 17:00:48 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 | 0.2/12, 0.2/0 | 0:0.234 2:0.016 4:0.656 6:0.547 8:0.516x | 1:0.063 3:0.015 5:0.031 7:0.031 9:0.016 |
| 13 | 17:01:04 | `create_delayed_on_holder` | on-time | a | green | none | 0.0/0, 0.0/0 | 0:0.047 2:0.016 4:0.031 6:0.031 8:0.046 | 1:0.078 3:0.032 5:0.016 7:0.016 9:0.016 |
| 14 | 17:01:19 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.515 a/8: 0.515 | 0.2/11, 0.2/0 | 0:0.218 2:0.515x 4:0.000 6:0.640 8:0.515x | 1:0.016 3:0.046 5:0.032 7:0.032 9:0.062 |
| 15 | 17:01:35 | `create_delayed_on_holder` | one-late | a | green | none | 0.0/0, 0.0/0 | 0:0.031 2:0.016 4:0.031 6:0.015 8:0.046 | 1:0.078 3:0.032 5:0.032 7:0.047 9:0.032 |
| 16 | 17:01:50 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 | 0.2/12, 0.2/0 | 0:0.016 2:0.641 4:0.234 6:0.547 8:0.516x | 1:0.031 3:0.063 5:0.047 7:0.047 9:0.078 |
| 17 | 17:02:05 | `create_delayed_on_holder` | on-time | a | green | none | 0.0/0, 0.0/0 | 0:0.046 2:0.000 4:0.047 6:0.062 8:0.062 | 1:0.078 3:0.031 5:0.016 7:0.031 9:0.047 |
| 18 | 17:02:19 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/4: 0.500 a/8: 0.500 | 0.2/11, 0.2/0 | 0:0.000 2:0.625 4:0.500x 6:0.219 8:0.500x | 1:0.047 3:0.015 5:0.015 7:0.015 9:0.015 |
| 19 | 17:02:34 | `create_delayed_on_holder` | one-late | a | green | none | 0.0/0, 0.0/0 | 0:0.016 2:0.000 4:0.031 6:0.000 8:0.031 | 1:0.047 3:0.016 5:0.031 7:0.015 9:0.015 |
| 20 | 17:02:50 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.516 | 0.2/12, 0.2/0 | 0:0.016 2:0.219 4:0.516x 6:0.531 8:0.610 | 1:0.015 3:0.063 5:0.015 7:0.015 9:0.015 |

Contrast (2), the delay on the non-holder process only (the holder's process is undelayed):

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:03:12 | `create_delayed_on_non_holder` | on-time | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.016 2:0.032 4:0.031 6:0.031 8:0.047 | 1:0.063 3:0.219 5:0.219 7:0.500x 9:0.625 |
| 2 | 17:03:26 | `create_delayed_on_non_holder` | one-late | a | red: refresh ended before all waited | none | 0.2/0, 0.2/20 | 0:0.000 2:0.016 4:0.031 6:0.000 8:0.031 | 1:0.500x 3:0.250 5:0.625 7:0.203 9:0.047 |
| 3 | 17:03:40 | `create_delayed_on_non_holder` | on-time | a | red: refresh ended before all waited | none | 0.2/0, 0.2/20 | 0:0.016 2:0.032 4:0.047 6:0.031 8:0.031 | 1:0.235 3:0.063 5:0.203 7:0.625 9:0.500x |
| 4 | 17:03:54 | `create_delayed_on_non_holder` | one-late | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.016 2:0.031 4:0.031 6:0.016 8:0.016 | 1:0.500x 3:0.250 5:0.047 7:0.625 9:0.203 |
| 5 | 17:04:08 | `create_delayed_on_non_holder` | on-time | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.000 2:0.031 4:0.016 6:0.047 8:0.031 | 1:0.047 3:0.500x 5:0.203 7:0.219 9:0.625 |
| 6 | 17:04:21 | `create_delayed_on_non_holder` | one-late | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.016 2:0.000 4:0.032 6:0.000 8:0.032 | 1:0.047 3:0.218 5:0.218 7:0.625 9:0.515x |
| 7 | 17:04:34 | `create_delayed_on_non_holder` | on-time | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.016 2:0.016 4:0.031 6:0.047 8:0.031 | 1:0.047 3:0.219 5:0.625 7:0.219 9:0.516x |
| 8 | 17:04:47 | `create_delayed_on_non_holder` | one-late | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.016 2:0.032 4:0.016 6:0.016 8:0.000 | 1:0.235 3:0.609 5:0.032 7:0.515x 9:0.203 |
| 9 | 17:05:00 | `create_delayed_on_non_holder` | on-time | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.015 2:0.016 4:0.016 6:0.032 8:0.032 | 1:0.032 3:0.625 5:0.218 7:0.203 9:0.500x |
| 10 | 17:05:13 | `create_delayed_on_non_holder` | one-late | a | red: refresh ended before all waited | none | 0.2/0, 0.2/22 | 0:0.031 2:0.000 4:0.016 6:0.000 8:0.031 | 1:0.063 3:0.203 5:0.250 7:0.500x 9:0.609 |

Record of contrast (2), run 1:

Run 1 (on-time), carrier red: `refresh ended before all waited`; instants in s from the run's first checkout.

| Process | held_at | checked_out | Tag | Phase | Status | Checkouts: step, outcome, start, duration |
|---|---|---|---|---|---|---|
| a | null | 0 | 0 | held | 200 | find, ok, 0.000, 0.016; refresh_holder, holder, 0.016, 0.000 |
| a | null | 0 | 2 | waiting | - | find, ok, 0.000, 0.032; refresh_holder, lock taken, 0.032, 0.015 |
| a | null | 0 | 4 | waited | 200 | find, ok, 0.016, 0.031; refresh_holder, lock taken, 0.047, 0.000 |
| a | null | 0 | 6 | waited | 200 | find, ok, 0.016, 0.031; refresh_holder, lock taken, 0.047, 0.016 |
| a | null | 0 | 8 | waited | 200 | find, ok, 0.016, 0.047; refresh_holder, lock taken, 0.063, 0.000 |
| b | null | 2 | 1 | waiting | - | find, ok, 0.000, 0.063; refresh_holder, lock taken, 0.063, 0.015 |
| b | null | 2 | 3 | waited | 200 | find, ok, 0.063, 0.219; refresh_holder, lock taken, 0.282, 0.203 |
| b | null | 2 | 5 | waiting | - | find, ok, 0.063, 0.219; refresh_holder, lock taken, 0.282, 0.203 |
| b | null | 2 | 7 | arrived | 503 | find, unavailable, 0.063, 0.500 |
| b | null | 2 | 9 | waited | 200 | find, ok, 0.063, 0.625; refresh_holder, lock taken, 0.688, 0.203 |

Magnitudes:

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:05:34 | `create_delayed_on_holder` | on-time | a | green | none | 0.05/26, 0.05/0 | 0:0.016 2:0.062 4:0.281 6:0.172 8:0.453 | 1:0.063 3:0.031 5:0.015 7:0.000 9:0.015 |
| 2 | 17:05:47 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/0: 0.500 | 0.1/21, 0.1/0 | 0:0.500x 2:0.546 4:0.125 6:0.016 8:0.343 | 1:0.062 3:0.016 5:0.078 7:0.031 9:0.031 |
| 3 | 17:06:00 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.516 | 0.15/15, 0.15/0 | 0:0.016 2:0.516x 4:0.328 6:0.656 8:0.031 | 1:0.078 3:0.016 5:0.016 7:0.062 9:0.016 |
| 4 | 17:06:13 | `create_delayed_on_holder` | one-late | a | green | none | 0.05/32, 0.05/0 | 0:0.000 2:0.281 4:0.062 6:0.094 8:0.172 | 1:0.047 3:0.062 5:0.015 7:0.015 9:0.000 |
| 5 | 17:06:26 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.500 | 0.1/21, 0.1/0 | 0:0.016 2:0.125 4:0.328 6:0.172 8:0.500x | 1:0.047 3:0.031 5:0.016 7:0.016 9:0.016 |
| 6 | 17:06:42 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/0: 0.516 | 0.15/15, 0.15/0 | 0:0.516x 2:0.172 4:0.484 6:0.234 8:0.000 | 1:0.015 3:0.062 5:0.015 7:0.047 9:0.015 |
| 7 | 17:06:55 | `create_delayed_on_holder` | on-time | a | green | none | 0.05/26, 0.05/0 | 0:0.297 2:0.078 4:0.000 6:0.469 8:0.187 | 1:0.031 3:0.015 5:0.015 7:0.015 9:0.047 |
| 8 | 17:07:08 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/8: 0.500 | 0.1/21, 0.1/0 | 0:0.141 2:0.328 4:0.016 6:0.546 8:0.500x | 1:0.078 3:0.062 5:0.078 7:0.016 9:0.032 |
| 9 | 17:07:21 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/0: 0.516 a/8: 0.516 | 0.15/14, 0.15/0 | 0:0.516x 2:0.188 4:0.000 6:0.500 8:0.516x | 1:0.047 3:0.016 5:0.016 7:0.000 9:0.016 |
| 10 | 17:07:34 | `create_delayed_on_holder` | one-late | a | green | none | 0.05/32, 0.05/0 | 0:0.000 2:0.281 4:0.172 6:0.078 8:0.062 | 1:0.047 3:0.031 5:0.015 7:0.015 9:0.015 |
| 11 | 17:07:49 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/8: 0.516 | 0.1/22, 0.1/0 | 0:0.016 2:0.328 4:0.125 6:0.172 8:0.516x | 1:0.063 3:0.015 5:0.031 7:0.015 9:0.015 |
| 12 | 17:08:02 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/4: 0.500 | 0.15/15, 0.15/0 | 0:0.172 2:0.016 4:0.500x 6:0.234 8:0.469 | 1:0.000 3:0.016 5:0.031 7:0.016 9:0.047 |
| 13 | 17:08:15 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/8: 0.516 | 0.05/31, 0.05/0 | 0:0.156 2:0.046 4:0.234 6:0.391 8:0.516x | 1:0.125 3:0.062 5:0.046 7:0.078 9:0.078 |
| 14 | 17:08:29 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/2: 0.500 | 0.1/21, 0.1/0 | 0:0.015 2:0.500x 4:0.328 6:0.547 8:0.140 | 1:0.016 3:0.062 5:0.016 7:0.031 9:0.031 |
| 15 | 17:08:43 | `create_delayed_on_holder` | on-time | a | red: refresh ended before all waited | a/8: 0.516 a/4: 0.516 | 0.15/14, 0.15/0 | 0:0.016 2:0.172 4:0.516x 6:0.469 8:0.516x | 1:0.046 3:0.032 5:0.031 7:0.015 9:0.015 |
| 16 | 17:08:57 | `create_delayed_on_holder` | one-late | a | green | none | 0.05/31, 0.05/0 | 0:0.000 2:0.062 4:0.172 6:0.094 8:0.281 | 1:0.016 3:0.047 5:0.016 7:0.031 9:0.016 |
| 17 | 17:09:10 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/2: 0.516 | 0.1/21, 0.1/0 | 0:0.016 2:0.516x 4:0.125 6:0.140 8:0.328 | 1:0.015 3:0.063 5:0.000 7:0.031 9:0.015 |
| 18 | 17:09:24 | `create_delayed_on_holder` | one-late | a | red: refresh ended before all waited | a/2: 0.515 | 0.15/15, 0.15/0 | 0:0.187 2:0.515x 4:0.016 6:0.250 8:0.485 | 1:0.078 3:0.000 5:0.031 7:0.015 9:0.015 |

Named-test invocations (`-rA` lines):

```text
it01 start 2026-11-22T17:16:11Z
it01 end 2026-11-22T17:17:40Z exit=0 3 passed, 1 warning in 76.64s (0:01:16)
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it02 start 2026-11-22T17:17:40Z
it02 end 2026-11-22T17:18:30Z exit=0 3 passed, 1 warning in 47.30s
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it03 start 2026-11-22T17:18:30Z
it03 end 2026-11-22T17:19:37Z exit=0 3 passed, 1 warning in 64.90s (0:01:04)
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it04 start 2026-11-22T17:19:38Z
it04 end 2026-11-22T17:20:35Z exit=0 3 passed, 1 warning in 53.59s
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it05 start 2026-11-22T17:20:35Z
it05 end 2026-11-22T17:21:26Z exit=0 3 passed, 1 warning in 48.52s
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it06 start 2026-11-22T17:21:27Z
it06 end 2026-11-22T17:22:50Z exit=0 3 passed, 1 warning in 71.99s (0:01:11)
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it07 start 2026-11-22T17:22:50Z
it07 end 2026-11-22T17:23:44Z exit=0 3 passed, 1 warning in 51.73s
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it08 start 2026-11-22T17:23:44Z
it08 end 2026-11-22T17:24:50Z exit=0 3 passed, 1 warning in 63.60s (0:01:03)
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it09 start 2026-11-22T17:24:50Z
it09 end 2026-11-22T17:25:43Z exit=0 3 passed, 1 warning in 50.40s
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
it10 start 2026-11-22T17:25:43Z
it10 end 2026-11-22T17:26:54Z exit=0 3 passed, 1 warning in 67.39s (0:01:07)
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[on-time]
PASSED test_eko140_k01_checkout_delay_on_the_holder_process_answers_503_from_find_before_any_blocker[one-late]
PASSED test_eko140_k01_checkout_delay_with_the_holder_on_process_b_answers_503_from_find
```
