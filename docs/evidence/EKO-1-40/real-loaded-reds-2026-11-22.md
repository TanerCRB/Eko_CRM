# EKO-1-40 K-01 / K-07: undelayed runs of the carrier under load, with their records (2026-11-22)

Local evidence from one Windows host. It claims nothing about the CI runners or production.
Every value in the records is synthetic: request tags, process-local monotonic instants, and
loopback ports are all that the records hold.

## How the runs were made

| Field | Value |
|---|---|
| Host | `DESKTOP-B7OHL9E` (Windows 11 Pro, 16 logical CPUs, Docker Desktop with 16 CPUs). This is the host of the #188 / #228 observations. Other sessions' Docker work ran on the host during every run here (one composition stack, other projects' `testcontainers` PostgreSQL containers), so no run below is on a quiet host. |
| Tree | branch `EKO-1-40-pool-checkout-latency`, `HEAD` `6575393` (= `5ac1a36` plus bookkeeping commits). The carrier file `test_eko201_k04_refresh_concurrency.py` is byte-identical to `b099acc`. |
| Body | The carrier's own `pool_exhausted_responsive(pg, stub, all_waiting, late)` on `tests.support.eko138_observed_app:create_with_blockers` (no delay), called by a temporary harness (see [the harness](README.md#the-harness)). When `all_waiting` fails, the harness reads `/__eko201/state` from both processes before they stop. A green run keeps the run's `final` record. |
| Verdict | Signature S as K-01 defines it, computed by `backend/tests/support/eko140_signature.py` from the record. |
| Load | `load.py N T`: N Python busy-loop processes (`x = (x * 31 + 7) % 1000003` until T seconds have passed), started 3 s before pytest. Run set A: N = 24, T = 330 s. Run set B: N = 32, T = 420 s. Two attempts that also ran busy-loop containers inside the Docker VM (16 or 4 containers of `postgres:18.6-trixie` running `sh -c 'while :; do :; done'`) were dropped. All 12 + 10 of their runs errored in setup (the throwaway PostgreSQL never answered, with `ConnectionTimeout` or "server closed the connection unexpectedly"), so they produced no carrier record. |

## Result

| Run set | Load | Runs | Red | Red with S | S on process (holder) | Red without S |
|---|---|---|---|---|---|---|
| A | 24 busy loops, 330 s | 12 (6 × on-time, one-late) | 2 | 2 | a (holder a), b (holder b) | 0 |
| B | 32 busy loops, 420 s | 10 (5 × on-time, one-late) | 1 | 1 | a (holder a) | 0 |
| Interleaved delay-0 run 9 of [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md) | none added (a host latency spike while other sessions ran) | 1 of 10 at delay 0 | 1 | 1 | a (holder a) | 0 |

Every real red recorded here shows S: a tagged request on the holder's process, whose only
checkout is a `find` that ended `unavailable` after 0.500 to 0.516 s and answered 503, with no
blocker placed yet (`held_at` null). In every one of them the carrier went red inside `all_waiting`
("refresh ended before all waited"), as K-01 predicts.

In run set A's first red, three `find`s of the **non-holder** process b also ended `unavailable`.
Process b has two free connections. So under real load the 503 from `find` is not confined to the
holder's single free connection. The controlled contrast (2) shows the same thing
([`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md)).

All reds came in the first one or two runs of a pytest session, while the load was on. Later runs
under the same load were green. The busy-loop load raised the `find` durations of the later runs
only a little (see the tables). So these runs do not show that this load generator reproduces the
cause at a steady rate. They show what the records of real reds look like, and how long `find`
took in them.

## `find` durations of the undelayed runs (K-07)

From the tables below, seconds per `find` (an `x` marks `unavailable`):

| | Holder's process | Other process |
|---|---|---|
| Red runs (4 runs) | 0.062 – 1.187 ok; 0.500 – 0.516 unavailable | 0.094 – 1.141 ok; 0.500 – 0.594 unavailable |
| Green runs under load (19 runs) | 0.000 – 0.281 | 0.000 – 0.203 |

`refresh_holder` checkouts that found the lock taken (wait plus one `pg_try_advisory_lock`) took
0.000 – 0.938 s in the red runs.

## Run set A — 24 busy loops

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:10:36 | `create_with_blockers` | on-time | a | red: refresh ended before all waited | a/2: 0.500 a/6: 0.516 | -, - | 0:0.281 2:0.500x 4:0.109 6:0.516x 8:1.187 | 1:1.141 3:0.359 5:0.516x 7:0.500x 9:0.594x |
| 2 | 16:11:53 | `create_with_blockers` | one-late | b | red: refresh ended before all waited | b/7: 0.516 | -, - | 1:0.266 3:0.297 5:0.422 7:0.516x 9:0.500 | 0:0.250 2:0.218 4:0.328 6:0.218 8:0.297 |
| 3 | 16:12:42 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.062 2:0.031 4:0.078 6:0.093 8:0.141 | 1:0.141 3:0.094 5:0.156 7:0.063 9:0.094 |
| 4 | 16:13:07 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.016 2:0.047 4:0.094 6:0.000 8:0.047 | 1:0.016 3:0.109 5:0.047 7:0.063 9:0.047 |
| 5 | 16:13:28 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.016 2:0.125 4:0.047 6:0.094 8:0.141 | 1:0.078 3:0.078 5:0.031 7:0.078 9:0.032 |
| 6 | 16:13:52 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.032 2:0.046 4:0.031 6:0.125 8:0.046 | 1:0.078 3:0.000 5:0.032 7:0.016 9:0.016 |
| 7 | 16:14:09 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.032 2:0.047 4:0.032 6:0.015 8:0.063 | 1:0.015 3:0.063 5:0.078 7:0.015 9:0.031 |
| 8 | 16:14:25 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.047 2:0.031 4:0.047 6:0.031 8:0.094 | 1:0.063 3:0.110 5:0.062 7:0.063 9:0.062 |
| 9 | 16:14:44 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.078 4:0.032 6:0.046 8:0.141 | 1:0.063 3:0.110 5:0.047 7:0.078 9:0.063 |
| 10 | 16:15:02 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.063 2:0.016 4:0.078 6:0.172 8:0.062 | 1:0.078 3:0.031 5:0.015 7:0.047 9:0.047 |
| 11 | 16:15:28 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.031 4:0.063 6:0.094 8:0.078 | 1:0.047 3:0.078 5:0.031 7:0.047 9:0.047 |
| 12 | 16:15:43 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.015 2:0.047 4:0.031 6:0.016 8:0.032 | 1:0.063 3:0.031 5:0.016 7:0.063 9:0.031 |

Records of the two reds:

Run 1 (on-time), carrier red: `refresh ended before all waited`; instants in s from the run's first checkout.

| Process | held_at | checked_out | Tag | Phase | Status | Checkouts: step, outcome, start, duration |
|---|---|---|---|---|---|---|
| a | null | 1 | 0 | waited | 200 | find, ok, 0.047, 0.281; refresh_holder, lock taken, 0.328, 0.125 |
| a | null | 1 | 2 | arrived | 503 | find, unavailable, 0.078, 0.500 |
| a | null | 1 | 4 | held | 200 | find, ok, 0.000, 0.109; refresh_holder, holder, 0.109, 0.110 |
| a | null | 1 | 6 | arrived | 503 | find, unavailable, 0.453, 0.516 |
| a | null | 1 | 8 | waiting | - | find, ok, 0.141, 1.187; refresh_holder, lock taken, 1.328, 0.063 |
| b | null | 1 | 1 | waited | 200 | find, ok, 0.156, 1.141; refresh_holder, lock taken, 1.297, 0.062 |
| b | null | 1 | 3 | waiting | - | find, ok, 0.000, 0.359; refresh_holder, lock taken, 0.359, 0.938 |
| b | null | 1 | 5 | arrived | 503 | find, unavailable, 0.156, 0.516 |
| b | null | 1 | 7 | arrived | 503 | find, unavailable, 0.500, 0.500 |
| b | null | 1 | 9 | arrived | 503 | find, unavailable, 0.172, 0.594 |

Run 2 (one-late), carrier red: `refresh ended before all waited`; instants in s from the run's first checkout.

| Process | held_at | checked_out | Tag | Phase | Status | Checkouts: step, outcome, start, duration |
|---|---|---|---|---|---|---|
| a | null | 2 | 0 | waiting | - | find, ok, 0.156, 0.250; refresh_holder, lock taken, 0.406, 0.110 |
| a | null | 2 | 2 | waiting | - | find, ok, 0.063, 0.218; refresh_holder, lock taken, 0.281, 0.125 |
| a | null | 2 | 4 | waiting | - | find, ok, 0.188, 0.328; refresh_holder, lock taken, 0.516, 0.094 |
| a | null | 2 | 6 | waited | 200 | find, ok, 0.813, 0.218; refresh_holder, lock taken, 1.031, 0.141 |
| a | null | 2 | 8 | waiting | - | find, ok, 0.844, 0.297; refresh_holder, lock taken, 1.141, 0.156 |
| b | null | 2 | 1 | held | 200 | find, ok, 0.000, 0.266; refresh_holder, holder, 0.266, 0.109 |
| b | null | 2 | 3 | waiting | - | find, ok, 0.328, 0.297; refresh_holder, lock taken, 0.625, 0.078 |
| b | null | 2 | 5 | waiting | - | find, ok, 0.375, 0.422; refresh_holder, lock taken, 0.797, 0.156 |
| b | null | 2 | 7 | arrived | 503 | find, unavailable, 0.625, 0.516 |
| b | null | 2 | 9 | waiting | - | find, ok, 0.844, 0.500; refresh_holder, lock taken, 1.344, 0.141 |

## Run set B — 32 busy loops

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:40:59 | `create_with_blockers` | on-time | a | red: refresh ended before all waited | a/4: 0.500 | -, - | 0:0.172 2:0.281 4:0.500x 6:0.312 8:0.359 | 1:0.234 3:0.172 5:0.313 7:0.094 9:0.469 |
| 2 | 16:42:06 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.187 2:0.234 4:0.281 6:0.140 8:0.219 | 1:0.203 3:0.110 5:0.140 7:0.125 9:0.078 |
| 3 | 16:42:28 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.094 4:0.016 6:0.031 8:0.031 | 1:0.078 3:0.110 5:0.047 7:0.032 9:0.047 |
| 4 | 16:42:56 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.156 2:0.015 4:0.078 6:0.016 8:0.078 | 1:0.109 3:0.063 5:0.047 7:0.078 9:0.078 |
| 5 | 16:43:12 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.046 2:0.093 4:0.016 6:0.063 8:0.125 | 1:0.047 3:0.094 5:0.078 7:0.078 9:0.015 |
| 6 | 16:43:27 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.047 2:0.016 4:0.016 6:0.016 8:0.031 | 1:0.063 3:0.031 5:0.094 7:0.015 9:0.031 |
| 7 | 16:43:44 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.062 2:0.062 4:0.016 6:0.031 8:0.047 | 1:0.032 3:0.032 5:0.078 7:0.016 9:0.032 |
| 8 | 16:44:04 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.032 2:0.031 4:0.016 6:0.141 8:0.047 | 1:0.078 3:0.032 5:0.110 7:0.016 9:0.032 |
| 9 | 16:44:34 | `create_with_blockers` | on-time | a | green | none | -, - | 0:0.047 2:0.078 4:0.062 6:0.140 8:0.141 | 1:0.125 3:0.078 5:0.125 7:0.078 9:0.093 |
| 10 | 16:44:51 | `create_with_blockers` | one-late | a | green | none | -, - | 0:0.047 2:0.016 4:0.046 6:0.016 8:0.094 | 1:0.016 3:0.047 5:0.031 7:0.094 9:0.047 |

Record of the red:

Run 1 (on-time), carrier red: `refresh ended before all waited`; instants in s from the run's first checkout.

| Process | held_at | checked_out | Tag | Phase | Status | Checkouts: step, outcome, start, duration |
|---|---|---|---|---|---|---|
| a | null | 0 | 0 | held | 200 | find, ok, 0.000, 0.172; refresh_holder, holder, 0.172, 0.063 |
| a | null | 0 | 2 | waited | 200 | find, ok, 0.110, 0.281; refresh_holder, lock taken, 0.391, 0.047 |
| a | null | 0 | 4 | arrived | 503 | find, unavailable, 0.188, 0.500 |
| a | null | 0 | 6 | waited | 200 | find, ok, 0.688, 0.312; refresh_holder, lock taken, 1.000, 0.047 |
| a | null | 0 | 8 | waited | 200 | find, ok, 0.188, 0.359; refresh_holder, lock taken, 0.547, 0.250 |
| b | null | 0 | 1 | waited | 200 | find, ok, 0.063, 0.234; refresh_holder, lock taken, 0.297, 0.078 |
| b | null | 0 | 3 | waited | 200 | find, ok, 0.266, 0.172; refresh_holder, lock taken, 0.438, 0.109 |
| b | null | 0 | 5 | waited | 200 | find, ok, 0.656, 0.313; refresh_holder, lock taken, 0.969, 0.047 |
| b | null | 0 | 7 | waited | 200 | find, ok, 0.328, 0.094; refresh_holder, lock taken, 0.422, 0.125 |
| b | null | 0 | 9 | waited | 200 | find, ok, 0.328, 0.469; refresh_holder, lock taken, 0.797, 0.125 |

## The undelayed red of the interleaved contrast (delay 0)

Run 9 of the interleaved contrast in [`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md).
It ran on the delay factory with `EKO140_DELAY_SECONDS=0` (`applied` 0 on both processes), with no
load added. Its undelayed checkouts lasted 0.03 – 0.52 s. The neighbouring delay-0 runs lasted
0.00 – 0.06 s, so this run caught a host latency spike.

Run 9 (on-time), carrier red: `refresh ended before all waited`; instants in s from the run's first checkout.

| Process | held_at | checked_out | Tag | Phase | Status | Checkouts: step, outcome, start, duration |
|---|---|---|---|---|---|---|
| a | null | 2 | 0 | held | 200 | find, ok, 0.000, 0.062; refresh_holder, holder, 0.062, 0.079 |
| a | null | 2 | 2 | waiting | - | find, ok, 0.047, 0.281; refresh_holder, lock taken, 0.328, 0.203 |
| a | null | 2 | 4 | waiting | - | find, ok, 0.141, 0.515; refresh_holder, lock taken, 0.656, 0.141 |
| a | null | 2 | 6 | waiting | - | find, ok, 0.219, 0.390; refresh_holder, lock taken, 0.609, 0.000 |
| a | null | 2 | 8 | arrived | 503 | find, unavailable, 0.312, 0.516 |
| b | null | 2 | 1 | waiting | - | find, ok, 0.016, 0.406; refresh_holder, lock taken, 0.422, 0.172 |
| b | null | 2 | 3 | waiting | - | find, ok, 0.359, 0.250; refresh_holder, lock taken, 0.609, 0.032 |
| b | null | 2 | 5 | waiting | - | find, ok, 0.422, 0.187; refresh_holder, lock taken, 0.609, 0.032 |
| b | null | 2 | 7 | waited | - | find, ok, 0.594, 0.172; refresh_holder, lock taken, 0.766, 0.140 |
| b | null | 2 | 9 | waited | - | find, ok, 0.500, 0.266; refresh_holder, lock taken, 0.766, 0.140 |

