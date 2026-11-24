# EKO-1-40 K-03 / G-1: send-schedule fixes tried under the K-01 delay (2026-11-22)

Local evidence from one Windows host (`DESKTOP-B7OHL9E`, same host and tree as
[`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md)). None of these schedules is in
the tree: each ran from the temporary harness ([README](README.md#the-harness)), which replaces
`send_tagged` for one run (`monkeypatch`). The carrier's settle, blockers, hold and assertions
stayed as they are at `b099acc`. The harness also checked `[200] * 10` and
`refresh_at_block == [None]` on a run that passed the settle.

## The two schedules (both allowed by G-A A if green)

- **F1, gated:** request 0 (process a) is sent alone. Once its refresh reaches the identity stub,
  the holder is on a. Then process b's five requests are sent at once, and the holder process's
  four other requests are sent one at a time, each one only after the previous one is observed
  past `arrived` (in `waiting`) or has answered.
- **F2, pipelined:** as F1, but the next request on the holder's process is sent as soon as the
  previous one's `find` has ended.

Both put the holder on process a, so neither alone covers K-03's edge "holder on b".

## Result

| Schedule | Delay on the holder's process | Runs | Green | Red | 503 in a red | Why red |
|---|---|---|---|---|---|---|
| F1 gated | 0.05 s | 4 | 4 | 0 | – | – |
| F1 gated | 0.1 s | 4 | 4 | 0 | – | – |
| F1 gated | 0.2 s (the K-01 delay) | 4 | 0 | 4 | none | `refresh ended before all waited`: the fourth request of the holder's process was still in its `refresh_holder` checkout when the 2.0-s refresh was answered |
| F2 pipelined | 0.1 s | 3 | 3 | 0 | – | – |
| F2 pipelined | 0.2 s (the K-01 delay) | 3 | 0 | 3 | none | the same, with one `find` up to 0.594 s, close to the bound |

The carrier body at `b099acc` shows S in 6 of 6 runs at 0.1 s and in every run at 0.2 s
([`k01-controlled-delay-2026-11-22.md`](k01-controlled-delay-2026-11-22.md)). So a gated schedule
moves the delay the carrier survives from below 0.1 s to between 0.1 and 0.2 s. It does not
remove the dependency on checkout latency.

## Why no send schedule removes it

These hold for any send order that keeps where each request goes (`(a, b) * 5`) and the guarded
items of K-05:

1. Four of the ten requests share the holder's process with the holder. That process has one free
   connection (pool 2, overflow 0; the holder keeps the other one for its whole refresh).
2. Each of the four needs two checkouts that the application does not retry, `find` and then
   `refresh_holder`, and each is bounded by the 0.5-s `POOL_TIMEOUT_SECONDS`. The four
   `refresh_holder` checkouts must come after the holder took the lock, or one of them would be
   the holder.
3. Once a request waits, its probe takes the same connection every
   `PROBE_INTERVAL_SECONDS` = 0.1 s plus its own checkout time (`app/auth/sessions.py:275-291`).
4. Everything must happen before the guarded 2.0-s refresh is answered. The carrier also needs
   nine requests waiting and its blocker in place by then.

With each checkout keeping the connection for D more, there are two cases:

- Sending the four together queues at least four non-retried checkouts behind one another, so
  the last one waits about 3·D or more. That exceeds 0.5 s from D ≈ 0.17 s.
- Spreading them out costs at least 8·D of connection time, plus the probes, inside the 2.0-s
  window. F1 and F2 ran out of that window at D = 0.2 s.

So a test-only schedule works only below roughly D = 0.15 – 0.2 s on this host. The real records
of the reds show checkouts (waiting included) of up to 1.187 s for `find` and 0.938 s for
`refresh_holder`. These include the wait for a connection, so they are not the hold of one
checkout, but they are of the order of the D at which the schedules stop working, or above it
([`real-loaded-reds-2026-11-22.md`](real-loaded-reds-2026-11-22.md)). Removing the dependency
would take one of these: a longer refresh delay, a larger pool, a different bound, or a `find`
that retries. Each is a guarded item (K-05) or an application change (K-06, Out of scope), so
**G-1 applies**: no test-only change removes the dependency without loosening a bound.

## Runs

F1, gated:

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:09:47 | `create_delayed_on_holder/gated` | on-time | a | red: refresh ended before all waited | none | 0.2/11, 0.2/0 | 0:0.015 2:0.235 4:0.203 6:0.359 8:0.375 | 1:0.016 3:0.046 5:0.000 7:0.000 9:0.016 |
| 2 | 17:10:00 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.000 2:0.282 4:0.125 6:0.094 8:0.172 | 1:0.016 3:0.047 5:0.032 7:0.047 9:0.000 |
| 3 | 17:10:12 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.05/27, 0.05/0 | 0:0.000 2:0.063 4:0.078 6:0.062 8:0.140 | 1:0.015 3:0.015 5:0.046 7:0.031 9:0.015 |
| 4 | 17:10:25 | `create_delayed_on_holder/gated` | on-time | a | red: refresh ended before all waited | none | 0.2/11, 0.2/0 | 0:0.000 2:0.203 4:0.219 6:0.343 8:0.390 | 1:0.047 3:0.016 5:0.031 7:0.000 9:0.000 |
| 5 | 17:10:39 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.015 2:0.110 4:0.110 6:0.172 8:0.218 | 1:0.031 3:0.016 5:0.016 7:0.016 9:0.032 |
| 6 | 17:10:52 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.05/28, 0.05/0 | 0:0.016 2:0.062 4:0.047 6:0.047 8:0.110 | 1:0.031 3:0.031 5:0.000 7:0.016 9:0.016 |
| 7 | 17:11:05 | `create_delayed_on_holder/gated` | on-time | a | red: refresh ended before all waited | none | 0.2/11, 0.2/0 | 0:0.016 2:0.219 4:0.203 6:0.375 8:0.360 | 1:0.031 3:0.047 5:0.047 7:0.015 9:0.015 |
| 8 | 17:11:19 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.1/20, 0.1/0 | 0:0.000 2:0.109 4:0.266 6:0.110 8:0.156 | 1:0.047 3:0.016 5:0.000 7:0.016 9:0.016 |
| 9 | 17:11:32 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.05/28, 0.05/0 | 0:0.000 2:0.062 4:0.047 6:0.094 8:0.110 | 1:0.031 3:0.000 5:0.016 7:0.016 9:0.016 |
| 10 | 17:11:46 | `create_delayed_on_holder/gated` | on-time | a | red: refresh ended before all waited | none | 0.2/10, 0.2/0 | 0:0.015 2:0.219 4:0.203 6:0.360 8:0.359 | 1:0.016 3:0.016 5:0.016 7:0.016 9:0.031 |
| 11 | 17:11:59 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.000 2:0.125 4:0.093 6:0.141 8:0.281 | 1:0.047 3:0.000 5:0.031 7:0.015 9:0.000 |
| 12 | 17:12:12 | `create_delayed_on_holder/gated` | on-time | a | green | none | 0.05/28, 0.05/0 | 0:0.000 2:0.063 4:0.079 6:0.125 8:0.078 | 1:0.063 3:0.016 5:0.032 7:0.032 9:0.016 |

F2, pipelined:

| # | UTC | Factory | Case | Holder | Outcome | S (process/tag: find s) | Delay s / applied (holder, other) | `find` durations, holder process (s) | `find` durations, other process (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:13:48 | `create_delayed_on_holder/pipelined` | on-time | a | red: refresh ended before all waited | none | 0.2/11, 0.2/0 | 0:0.000 2:0.562 4:0.359 6:0.578 8:0.234 | 1:0.015 3:0.015 5:0.015 7:0.000 9:0.047 |
| 2 | 17:14:01 | `create_delayed_on_holder/pipelined` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.000 2:0.110 4:0.187 6:0.297 8:0.375 | 1:0.031 3:0.016 5:0.016 7:0.032 9:0.016 |
| 3 | 17:14:14 | `create_delayed_on_holder/pipelined` | on-time | a | red: refresh ended before all waited | none | 0.2/12, 0.2/0 | 0:0.000 2:0.343 4:0.219 6:0.578 8:0.594 | 1:0.015 3:0.062 5:0.047 7:0.015 9:0.015 |
| 4 | 17:14:27 | `create_delayed_on_holder/pipelined` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.015 2:0.110 4:0.156 6:0.281 8:0.343 | 1:0.031 3:0.016 5:0.016 7:0.016 9:0.016 |
| 5 | 17:14:40 | `create_delayed_on_holder/pipelined` | on-time | a | red: refresh ended before all waited | none | 0.2/11, 0.2/0 | 0:0.000 2:0.219 4:0.359 6:0.578 8:0.593 | 1:0.000 3:0.032 5:0.047 7:0.015 9:0.015 |
| 6 | 17:14:53 | `create_delayed_on_holder/pipelined` | on-time | a | green | none | 0.1/21, 0.1/0 | 0:0.000 2:0.125 4:0.375 6:0.250 8:0.156 | 1:0.031 3:0.016 5:0.016 7:0.016 9:0.047 |
