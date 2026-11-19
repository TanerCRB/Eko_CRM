# EKO-1-34 fix round 1: probe-r2 record (2026-11-19)

This record covers the second instrumented run on the throwaway branch, made because QA reported
three guards as untested. It ran QA's three Linux-only mutations (o1, o2, link) and repeated
mutation K-02(a) with a corrected kill matcher. The values come from the run's job artifacts and
the jobs' set-up logs. Nothing here comes from a local machine, and nothing here claims production
behaviour.

## Run

| Field | Value |
|---|---|
| Workflow run | 44480047835, attempt 1 (`eko134-probe-r1`) |
| Branch | `EKO-1-34-probe-r1` |
| Head (`git rev-parse HEAD` in every job's `run-identity.txt`, and `gh run view`) | `e7261cc5b53cd8d840b0878d114a113d302f1902` |
| Backend | `git diff --quiet 64a37b398190dc5f3b9820de998eba03000fc13c e7261cc5b53cd8d840b0878d114a113d302f1902 -- backend` exits 0: no change under `backend/`. Each job then applied one patch. |
| Runner image | `ubuntu-26.04` in every job. The version differed between jobs (set-up logs), so the runners were not uniform. |
| Docker | 29.4.2 in every job |

Runner image version and kernel per job:

| Job | Image version | Kernel |
|---|---|---|
| k02-a | `20261111.82.6` | `7.0.0-1016-aws` |
| k02-o1 | `20261111.196.1` | `7.0.0-1019-azure` |
| k02-o2 | `20261111.196.1` | `7.0.0-1019-azure` |
| k02-link | `20261116.202.1` | `7.0.0-1020-azure` |

**The probe branch is a throwaway.**
- `EKO-1-34-probe-r1` carries the transient probe workflow, its support files and the mutation
  patches.
- It was written under the conditions of boundary exception EKO-1-34/boundary-1, as the human
  approved for this branch.
- It is not part of the PR, and none of its files is on the task branch.

## Run conclusion: red, for one reason only

| Job | Conclusion |
|---|---|
| Mutation k02-a | success |
| Mutation k02-o1 | success |
| Mutation k02-link | success |
| Mutation k02-o2 | **failure** |
| Verdict | **failure**, because k02-o2 failed |

The k02-o2 job is red because the test failed at a different line than the one predicted. The
mutation itself was killed; see the o2 section. **No re-run was made.**

## Mutations: one per job, only the named test

| Mutation | Change | Test | Observed red (the line pytest marks, and its error) | Kill matched | Result |
|---|---|---|---|---|---|
| K-02(a) | interference removed: `HeldLogin(interference, page)` | pre-fix harness | `> with pytest.raises(PlaywrightError) as raised:` / `Failed: DID NOT RAISE Error` | `DID NOT RAISE Error` | killed, and the match confirmed it. This closes the matcher defect of run 44387692426. |
| o1 | in `HeldLogin._run`, the interference moved before the wait for the first request | pre-fix harness | `> assert held.failed_at is not None and held.in_flight_at < held.interfered_at < held.failed_at` / `assert (252.198968849 is not None and 250.835377519 < 250.819322125)` | the anchored ordering assertion | killed |
| o2 | veth created before the login: `veth = interference.new_veth("prefix")`, then `HeldLogin(interference, page, lambda: veth)` | pre-fix harness | `> assert held.settled_at_flight is True, "the bridge was already changing before the login"` / `AssertionError: the bridge was already changing before the login` | **no match** | killed, by an earlier guard than predicted |
| link | the link down/up removed from `hold_in_detection`; the `dad_transmits` write kept | continuous interference | `> with pytest.raises(host.HostNetworkNotSettled) as raised:` / `Failed: DID NOT RAISE HostNetworkNotSettled` | `DID NOT RAISE HostNetworkNotSettled` | killed |

**o1, read from the assertion's own values.**
- `in_flight_at` = 250.835377519 s and `interfered_at` = 250.819322125 s, on the monotonic clock.
- The interference started 0.016 s before the first request went out. The hold line reads
  `started -0.016 s after it`.
- So the ordering guard catches a reordered interference.

**link.** With `dad_transmits` written but the link not taken down and up, address detection is
not restarted. The address settled, and the settle returned within its bound.

## The o2 deviation

The prediction was a red on `assert held.veth is not None and held.veth not in
held.members_at_flight`, or `DID NOT RAISE Error`. The test went red one line earlier, on
`assert held.settled_at_flight is True`.

The hold log shows why:
- `settled at first request False`;
- the interference veth `veth03e178c` already among the 6 bridge members at the first request;
- first failure `net::ERR_NETWORK_CHANGED`, of the first request, 1.222 s after it.

The veth created before the login had not yet left address detection when the request went out.
So the bridge was not settled, and the earlier guard fired.
- The logged interference offset of 0.000 s is when the mutated lambda returned the
  already-created veth. It is not when that veth was created.

What follows:
- **The mutation was killed,** by the `settled_at_flight` guard rather than the
  `members_at_flight` assertion. The predicted kill string did not match.
- **This run did not exercise the `members_at_flight` assertion.** That assertion would catch only
  a veth created early that had already settled before the first request. In that case
  `settled_at_flight` would be True and the next assertion would decide. No run here created that
  case.
- **The run's verdict is red for this reason only.**
- **No re-run was made.**

## Widened redaction (S-01)

For this run, the probe's analyzer redacts the value of any parameter whose name ends in `code` or
`state` (`session_code`, `session_state` and similar), and of `client_data`, `tab_id` and
`execution`. The name is kept.

A grep over all four uploaded job artifacts found these counts (no values are recorded):

| Pattern | Occurrences | Unredacted |
|---|---|---|
| `session_code=` | 0 | 0 |
| `session_state=` | 0 | 0 |
| `client_data=` | 0 | 0 |
| `tab_id=` | 0 | 0 |
| `execution=` | 0 | 0 |
| `code=` / `state=` | 0 | 0 |
| any `<redacted>` marker | 0 | — |
| cookie header lines, `synthetic-` values, JWT shapes | 0 | — |

The four mutation logs held no authorization-flow URL at all: these jobs ran without Playwright's
debug log. So the widened rules found nothing to redact here. This run does not show that they
work on live data. That rests on the analyzer's synthetic fixtures, which were run locally before
the push.

## What this record does not prove

- **A green run.** The run is red on record, because o2 went red at a different line than
  predicted.
- **The `members_at_flight` assertion.** It was not exercised, so it is still not shown to catch
  anything on its own.
- **One runner image.** The four jobs ran on three different image versions and two cloud kernels,
  not on one image.
- **The widened redaction on real authorization traffic.** None was present.
- **Correctness of the unmutated tree.** Isolation, the full job and mutations b, b′, c and dad are
  recorded in [`fix-round-1-probe-2026-11-18.md`](fix-round-1-probe-2026-11-18.md) (run
  44387692426), not here.
- **Production, Docker Desktop, or the product's frontend-replacement behaviour.**
