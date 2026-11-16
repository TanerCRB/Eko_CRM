# EKO-1-31 — QA CI plant-and-remove cycle (K-05) — 2026-11-15

Synthetic values only. Task: Issue #162 / EKO-1-31, criterion K-05 (Judged by: Human at gate 2 — this record supplies the artifacts; the provenance call is the human's). Branch `EKO-1-31-ci-traceback-secret-echo`, PR [#175](https://github.com/TanerCRB/Eko_CRM/pull/175). Precedent form: `docs/evidence/EKO-1-29/plant-red-2026-11-12.md`; retrieval method: `gh run view --job <id> --log` (documented at `docs/evidence/EKO-1-12/fix-round-3-ubuntu-hardening.md:21`).

## Cycle

| Step | Commit | Head at CI | Run | Backend static job | Result |
|---|---|---|---|---|---|
| Plant (transient) | `88ddce4` — adds `clients[0]` `{"clientId": "qa131-ci-plant", "secret": "QA131-CI-PLANT-9f2e6a1b-synthetic"}` to `identity/eko-realm.json` | `13b802e` (plant + mypy fix) | [43736848440](https://github.com/TanerCRB/Eko_CRM/actions/runs/43736848440) | job [132881230030](https://github.com/TanerCRB/Eko_CRM/actions/runs/43736848440/job/132881230030) | **RED as designed** — 2m27s |
| Remove plant | `f083902` — reverts `identity/eko-realm.json` to base | (no run scheduled for `f083902` — see Anomalies) | — | — | — |
| Merge + final green | `84d845a` (merge of main incl. EKO-1-32; plant absent) | `84d845a` | [43760898105](https://github.com/TanerCRB/Eko_CRM/actions/runs/43760898105) | job 132955251879 | **GREEN** — backend pass 2m49s; frontend/layer/process-ci/changes pass; runtime jobs skipping (paths outside triggers) |

## The red run's captured log — mechanical checks

Full job log fetched (`gh run view --job 132881230030 --log`): **2,689 lines** (complete job log, not an excerpt; kept off-repo at `.task/ci-red-plant-run2.log` — the absence claim below was checked over this complete file; re-retrievable from the run id at any time while Actions retains it, 90 days).

| Check | Command (over the full fetched log) | Result |
|---|---|---|
| Plant value absent | `grep -c "QA131-CI-PLANT-9f2e6a1b-synthetic"` | **0** |
| Plant prefix absent | `grep -c "QA131-CI-PLANT"` | 0 |
| Field path present | `grep -n "clients\[0\].secret"` | present — the failure line: `E AssertionError: clients[0].secret` (log line 2655) |
| Wrong node reddened | `grep "FAILED tests/static/test_eko112_k06..."` | `test_k06_every_export_secret_is_absent_or_an_environment_placeholder - AssertionError: clients[0].secret` (log line 2671) |
| Echo channels dead under CI render | visual inspection of the traceback section around the failure | only `realm = <object>`-free caller source + the path message; no `isinstance('<value>')`/`fullmatch('<value>')` breakdown, no realm-dict argument block |

## Recorded collateral (which node turned red — all of them)

Two nodes reddened under the plant, not one: beyond the k06 realm node above, `test_eko112_k01_realm_export.py::test_k01_every_client_has_direct_access_disabled` also failed (`assert False`, log lines 1159/2669) — the plant client omitted `directAccessGrantsEnabled`, and k01 requires each client to carry it explicitly. Both failures are consequences of the same committed plant; neither echoes the value (the `0` counts above cover the complete log including both failures' tracebacks). No other node flipped.

## Discrimination note (the pre-fix contrast)

The same plant against the PRE-fix reporting behavior is demonstrated locally by the executed mutations, not by a second CI cycle: QA's M1 (base echo form) re-renders the plant in BOTH channels in the child report captured with the CI-equivalent `-v` render path (`test_eko131_k01_failing_realm_report_names_the_path_and_holds_no_plant` red with `realm = {'clients': [{'secret': 'QA131-REPORTING-PLANT-4c81'}]}` + breakdown echoes, patches in the PR description, Base `e9c6453`). A CI-side pre-fix contrast would require pushing the plant onto an unfixed tree — same red log with the value in it; the committed-guard mutation covers the render mechanism; the human may treat "run the plant on base once" as an optional extra at gate 2.

## Anomalies (honest record)

- Run scheduling gap: pushes `f083902` (plant removal) and the earlier `88ddce4` PR-event pair showed GitHub queueing duplicates/cancellations on this account (repo-wide Actions list busy with EKO-1-32/main runs at the same minutes); `f083902` received **no** workflow run at all, and `gh pr checks` reported "no checks" transiently. The green on `84d845a` is the first post-removal CI verdict and it passes with the plant absent from the tree (verified at commit level: `git show 84d845a:identity/eko-realm.json` contains no `qa131-ci-plant`; local check `plant gone: true` at removal time).
- Local Windows env: pytest-subprocess harnesses need `TMP/TEMP/TMPDIR` pinned to a quiet native dir (see task journal; env-only, CI on ubuntu unaffected).

## Verdict inputs this record supplies for the human (K-05)

1. The real CI static job turned red on the committed synthetic plant (`88ddce4`, run 43736848440).
2. The complete captured log names the offending field path (`clients[0].secret`) and the failed node id, and contains the planted value 0 times — checked mechanically over all 2,689 lines.
3. With the plant removed, the pipeline is green again (run 43760898105 at `84d845a`).
4. Provenance (that these are the genuine Actions logs of these commits) is the human-side call per the criterion text; run ids above are independently re-fetchable.
