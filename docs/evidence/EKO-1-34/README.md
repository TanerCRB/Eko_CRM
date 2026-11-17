# EKO-1-34 runtime evidence (#192)

Dated records for EKO-1-34 K-01 and K-04 are added to this directory once the probe has run.
This README only says what the probe records. It is not evidence by itself.

## What the probe records

The transient workflow `.github/workflows/eko134-probe.yml` runs only on pushes to the task
branch. It is deleted before merge (K-07). Its run uploads one artifact,
`eko134-probe-<run id>-<attempt>`, holding:

- `run-identity.txt`: the runner image (`ImageOS`, `ImageVersion`), `git rev-parse HEAD`, the run
  id and attempt, the kernel, and the Docker and Compose versions.
- `interfaces-before.txt` and `interfaces-after.txt`: `ip -br link`, `ip -br addr` and the Docker
  networks before and after the loop.
- `host-events.txt`: every `ip -ts monitor all` event and every Docker event for the whole loop on
  one UTC clock. Docker events carry selected fields only, and an exec event keeps only its program
  name.
- `iterations.tsv`: one row per iteration and test. Each row holds the iteration's start and end,
  pytest's exit code, the test's outcome and first error line, the bounds of the first-redirect
  window, and the number of `ip` and Docker events inside that window.
- `iteration-NN/pytest.log`, `iteration-NN/timeline.txt` and `iteration-NN/windows.txt`: the
  redacted pytest output, which includes Playwright's own `pw:api` log. The timeline merges the
  probe's marks, Playwright's lines and the host events. The windows file lists the host events
  inside each login's first-redirect window, and in the 30 seconds before it.

The **first-redirect window** starts at Playwright's first `"load" event fired` after the
`browser_login start` mark, which is when the first `page.goto` returns. It ends at the first
`navigated to "https://auth.…"` line, or at the `browser_login raised` or `browser_login returned`
mark when no such line comes first. That is the span of the `wait_for_url` call where all eight
recorded failures happened.

**Known limit of the computed window.** When the first `page.goto` itself fails, it never fires
`load`. The probe then takes a later test's `load` as the window start, and the row's start comes
after its end. Run 44169988387 it03 k06 is such a row. Its window was re-derived by hand from that
iteration's timeline.

## Records

- [`pre-fix-probe-2026-11-17.md`](pre-fix-probe-2026-11-17.md): the K-01 record of the pre-fix
  probe run 44169988387. It names the event, its source and the passing contrast.

## Hygiene (ADR-0005, K-07)

Before upload, the workflow does the following:

- redacts every secret-named value from the iterations' synthetic env files;
- redacts the authorization code, state and token parameters, session values, synthetic
  passwords and JWT-shaped strings;
- withholds header lines that carry session or authorization material, env-file `NAME=value`
  lines and `docker inspect` shapes.

The raw logs and the iterations' temporary directories are never uploaded. A record written into
this directory from the artifact must still pass `tests/doc-checks/EKO-1-34.sh`.
