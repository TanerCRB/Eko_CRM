# EKO-1-34 runtime evidence (#192)

This directory holds the dated records of EKO-1-34's instrumented CI runs. This README is an
index. It is not evidence by itself.

## Records

| Record | Run | Criteria | Tree |
|---|---|---|---|
| [`pre-fix-probe-2026-11-17.md`](pre-fix-probe-2026-11-17.md) | 44169988387 | K-01, and the K-04 contrast | pre-fix |
| [`fixed-tree-probe-2026-11-18.md`](fixed-tree-probe-2026-11-18.md) | 44261867387 | K-02, K-04 | fixed |
| [`fix-round-1-probe-2026-11-18.md`](fix-round-1-probe-2026-11-18.md) | 44387692426 | K-02 after the R-01 fix: isolation, full job, mutations (corrected 2026-11-19 for R-03) | fixed, fix round 1 (throwaway branch `EKO-1-34-probe-r1`) |
| [`fix-round-1-probe-r2-2026-11-19.md`](fix-round-1-probe-r2-2026-11-19.md) | 44480047835 | K-02 guard mutations o1, o2 and link, and K-02(a) again | fixed, fix round 1 (throwaway branch `EKO-1-34-probe-r1`) |

- The pre-fix record names the event, its source and the cause site, and gives the passing
  contrast.
- The fixed-tree record gives the K-02 reproducer's five repetitions and the K-04 loop of 20
  iterations, compared with the pre-fix run on the same runner image.

## The probe (transient, absent at the PR head)

Two transient files produced these records:

- the workflow `.github/workflows/eko134-probe.yml`, written under boundary exception
  EKO-1-34/boundary-1;
- the logging-only timing plugin `backend/tests/support/eko134_probe_timing.py`, with its unit test
  `backend/tests/unit/test_eko134_probe_timing.py`.

They existed only in the branch commits from `58ab4aabea51acaea6c98bde59f5a1ad968b354a` through
`5685e327ce6cd28d52a45eb4bb2143cf5c26bbcd`, and they are deleted at the PR head (K-07). The
workflow is the place to read what each run did; it is in those commits.

Each run uploaded one artifact, `eko134-probe-<run id>-<attempt>`. It holds:

- `run-identity.txt`: the runner image, `git rev-parse HEAD`, and the run id and attempt;
- `host-events.txt`: the `ip -ts monitor all` and Docker events on one UTC clock;
- per invocation:
  - the redacted pytest output with Playwright's `pw:api` log;
  - a timeline merging the probe's marks, Playwright's lines and the host events;
  - the host events inside each login's first-redirect window;
- `iterations.tsv`: one row per test;
- `invocations.tsv` (the fixed-tree run only): one row per invocation;
- `verdict.txt` (the fixed-tree run only).

The **first-redirect window** starts at Playwright's first `"load" event fired` after the
`browser_login start` mark. It ends at the first navigation to the auth host, or at the
`browser_login raised` or `returned` mark.

The pre-fix run's analysis did not stop the `load` search at the login's end. When the first
`page.goto` failed, it fired no `load`, and the window was computed wrongly. Run 44169988387 it03
k06 is such a row; its window was re-derived by hand. The fixed-tree run's analysis bounds the
search by the login's end, and starts the window at `browser_login start` when there is no
`load`.

## Hygiene (ADR-0005, K-07)

Before upload, the probe did the following:

- redacted every secret-named value from the synthetic env files;
- redacted the authorization code, state and token parameters, session values, synthetic
  passwords, typed values and JWT-shaped strings;
- withheld header lines that carry session or authorization material, env-file `NAME=value`
  lines and `docker inspect` shapes.

The raw logs and the temporary directories were never uploaded. Every record here quotes only
short excerpts, with ports and address suffixes elided. Every record must pass
`tests/doc-checks/EKO-1-34.sh`.
