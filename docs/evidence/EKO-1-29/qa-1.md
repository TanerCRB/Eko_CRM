# EKO-1-29 — QA round 1: independent one-mechanism mutations and the live plant contrast — 2026-11-13

Date: 2026-11-13
Checkpoint (base for every patch below): `5b40a1534171448a16c6489c5d889dee2db17bf8` (branch
`EKO-1-29-secret-scan-raw-teeth`, worktree `../Eko_CRM-EKO-1-29`; the guard-file content under
test is `ffd4020`, later rows are bookkeeping only — `git show HEAD:<guard path>` matched the
worktree file and every `git checkout --` restore returned to it).
Carrier: `backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py` (the static
predicate `find_literal_secret_assignment_lines` — no docker, no runtime; production files were
never touched). Every value in this record is synthetic; no real secret exists here.
Method: each mutant was built by exactly one textual replacement in the pristine git-extracted
copy (`assert count==1` + `ast.parse`), swapped into the carrier path, run with
`uv run pytest tests/static/test_eko112_k06_synthetic_and_secret_free.py -q` from `backend/`,
then reverted with `git checkout -- <path>` and the `242 passed` green re-confirmed.
Baseline before any mutation: `242 passed in 1.64s`.

## Mutation runs (one mechanism removed per run; dev-side trail re-executed independently)

| # | Removed mechanism | Claimed | Observed (whole carrier) | Red items | Reverted-confirmed |
|---|---|---|---|---|---|
| M1 (C-1) | zero-width enumeration wrapper: the raw loop reduced to one leftmost `RAW_SECRET_ASSIGNMENT.search` | 3 | `3 failed, 239 passed in 3.52s` | the 3 raw `test_eko129_c1_a_held_leftmost_candidate_does_not_swallow_later_assignments` ids (`token=token, SECRET=literal`, the `client_secret="hunter2",` kwarg, the double-kwarg variant); the 2 diff-form swallow ids, both swallow-HOLD contrasts and all 25 R-01 mid-line items survive | yes — `242 passed in 1.43s` |
| M2 (C-2) | the after-separator alternative of `DIFF_LINE_MARKER` | 15 | `15 failed, 227 passed in 2.60s` | `test_eko129_c2_diff_form_assignments_after_line_separators_fire` for the 3 tails `+ KEY=lit`, `+KEY="foo`, `+ KEY=x` × 5 separators; the `+ token=token, SECRET=lit` tail (5 items) survives via the raw slot context, exactly as the dev-3 record predicted | yes — `242 passed in 1.47s` |
| M3 (R-05a) | quoted first values and the comma terminator in `_ASSIGNMENT_SLOT` | 6 | `6 failed, 236 passed in 2.03s` | 3 `test_eko129_r05a_quoted_first_slot_opens_the_assignment_context` + the 3 raw swallow ids (the comma slot is what reaches the hidden assignment) | yes — `242 passed in 2.60s` |
| M4 (C-4) | the `=`-attached and name-attached alternatives of the `-e`/`--env`/`env` flag context | 4 | `4 failed, 238 passed in 2.46s` | all 4 `test_eko129_c4_attached_environment_flag_assignments_fire` ids; the spaced `-e CLIENT_SECRET=x` mid-line items survive | yes — `242 passed in 3.72s` |
| M5 (C-2 other face) | the `(?!\+)` header guard from the line-start/separator marker | 5 | `5 failed, 237 passed in 3.19s` | the 5 `test_eko129_c2_contrast_diff_marker_holds_after_separators_hold[+++ b/x KEY=x-<sep>]` ids | yes — `242 passed in 1.94s` |
| M6 (R-04) | the defensive `rstrip("\r")` in the line cut | 1 | `1 failed, 241 passed in 2.47s` | `test_eko129_r04_empty_quote_before_carriage_return_is_an_observable_literal` | yes — `242 passed in 2.94s` |
| M7 (C-3) | the census constant: 17 → 14 comma-lines asserted | 1 | `1 failed, 241 passed in 2.42s` | `test_eko129_c3_keycloak_bootstrap_self_reference_census_holds` — assertion-value mutation, brittle by design (pins the true tree count) | yes — `242 passed in 2.00s` |
| M8 (R-03) | the `=`/keyword membership prefilter deleted | 0 (behaviour-inert by design) | `242 passed in 2.20s` — zero reds | none; timing probe below stands in as its evidence | yes — `242 passed in 1.87s` |

Every claimed red count reproduced exactly; no mutation produced a collection error or an
unrelated red — each run's failures were confined to the family the criterion names.

M1 wording note: the single-mechanism removal was implemented as one leftmost `.search` (the
dev-3 K1 "swallow back"), which reproduces the claimed 3 reds. A literal `.match` (anchored at
position 0) would additionally kill the 25 R-01 mid-line items — that is wholesale breakage of
the prefix grammar, not removal of the enumeration mechanism, so it is not this mutation.

### The header guard's other face (auditor S-5) — predicate probes

Direct calls of `find_literal_secret_assignment_lines("proxy/entrypoint.sh", …)` at rest and
under M5:

| Line (synthetic) | At rest | Under M5 |
|---|---|---|
| ``+++ b/proxy/entrypoint.sh`` (real header) | hold | hold (no `=`) |
| ``+++ KEY=x`` | **hold** | FIRE |
| ``++QA129_SECRET=x`` | **hold** | FIRE |
| ``+ KEY=x`` | FIRE | FIRE |

So `(?!\+)` is load-bearing in both directions: with it, the `++`/`+++` marker prefix exempts
the following assignment as well — the documented residual S-5 describes is real and is exactly
what M5 proves; removing the guard flips those shapes to firing while the genuine `+++ b/…`
header still holds. This is a property of the named grammar boundary, already listed among the
Story's "does not prove" items (shapes outside the named plants); recorded here as confirmation,
not as a new finding.

## Live-scan plant contrast (QA duty beyond mutations)

Untracked working-tree plants under the scanned `proxy/` prefix; the live scan tests run:

| Plant | Test | Result |
|---|---|---|
| `proxy/qa129-plant.sh` — line 2 bare literal assignment, line 3 the comma-terminated self-reference kwarg followed by a prefixed literal assignment (both `QA129_`-named, synthetic) | `test_k06_tracked_additions_have_no_literal_secret_environment_assignment` | RED — `AssertionError: proxy/qa129-plant.sh: line(s) [2, 3]: literal secret environment assignment` (`1 failed in 2.93s`, with the `++`-variant file also present) |
| same run | `test_k06_task_files_contain_no_declared_real_fixture` | GREEN — by design: that test scans different prefixes (`identity/`, `docs/evidence/EKO-1-12/`, `backend/tests/`, `scripts/keycloak-`) and a different property (a declared-real-data phrase), so a `proxy/` plant cannot reach it. (The tasking predicted both live-scan tests going red; only the tracked-additions scan is reachable by a `proxy/` plant — stated as observed.) |
| same run | `test_k07_c9_no_tracked_file_assigns_a_secret` | GREEN — the `QA129_` prefixed names stay outside the compose inventory, the established dev-1/dev-3 collision-avoidance precedent |
| `proxy/qa129-plant.sh` removed, `proxy/qa129-plant2.sh` (`++`-marker variant of the same assignment) left alone | tracked-additions scan | GREEN — plant2 undetected: the live-scan confirmation of the S-5 residual above |
| both plants removed | both k06 live-scan tests | `2 passed` — green restored; `git status` showed no residue |

Line 3 going red in the live scan matters independently: it is the C-1 enumeration working on
real file content, not only on in-memory plants.

## M8 timing sanity (the prefilter's insurance)

`uv run python` direct predicate calls, best-of-3 ms, Windows host, same line both runs
(~320 k characters):

| Case | At rest (prefilter) | M8 mutant (no prefilter) |
|---|---|---|
| all-held `token=token,` ×320k (contains `=` and a keyword) | 382.8 ms, no fire | 384.8 ms, no fire |
| keyword-free 320k word line | 0.2 ms | 69.0 ms |

The prompt's bar was the all-held line staying < 1 s without the prefilter: 385 ms, well under —
the prefilter is irrelevant there by construction (the short-circuit admits the line anyway).
The keyword-free row shows what the prefilter actually buys: a constant factor (~350× on this
probe), not the asymptotics — the `{0,64}` name bound and the lookbehind contexts of the dev-3
grammar already keep the enumeration linear. Realistic tree lines (< 500 characters) are sub-ms
either way. Behaviour-inert confirmed; the cost is defense-in-depth.

## Gates

- Guard file alone: `242 passed` (baseline and after every one of the eight reverts).
- Guard + `test_k07_changeset.py` together at rest: `284 passed` (242 + 42).
- Full static suite at rest: `uv run pytest tests/static -q` → `2033 passed in 1048.32s
  (0:17:28)`, exit 0 — exactly the expected count, no unrelated flake to attribute. (The run
  started before this record was written, so `qa-1.md` entered the scan's read set mid-run;
  the final state of this record was then proven inert independently — the guard file plus
  `test_k07_c9_no_tracked_file_assigns_a_secret` re-run with it present, `243 passed`.)
- Tree state after all mutation cycles and plant removals: `git status --porcelain` empty for
  everything this run touched; production files never modified; the only working-tree additions
  were the deleted plants (untracked, removed) and this record.

## What this record does not prove

- Same limits as the criteria list: comment-form assignments, names outside the keyword set,
  ignored files, PR history, and the grammar beyond the named shapes are not proven; the S-5
  `++`-marker exemption is a confirmed residual inside that stated limit, not new coverage.
- Mutations target the eight named mechanisms of the dev-3 round; earlier-round mechanisms
  (R-01/R-02/R-04/G-01 halves) were re-run by dev only — their one-mechanism kills here are the
  M2–M6 set plus the dev trail, not every historical fix independently.
- Local runs on one Windows host; CI on the PR is the authoritative green, and the gate-3
  register/disposition half of K-04 lands with the documentation PR (outside this run).

## Mutation patches (each against `5b40a15`, `git diff HEAD -- <guard path>` with the mutant in place)

### M1 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..48c5c03 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -124,9 +124,11 @@ def is_secret_env_assignment(line: str) -> bool:
     # dev-3 C-1: fire if ANY candidate is a non-held literal assignment; the line
     # holds only when every enumerated candidate is sanctioned (placeholder values are
     # not candidates at all — the literal value grammar never matches them).
-    for candidate in RAW_CANDIDATES.finditer(line):
-        if not _is_self_reference_kwarg_passing(candidate["name"], candidate["value"]):
-            return True
+    candidate = RAW_SECRET_ASSIGNMENT.search(line)
+    if candidate is not None and not _is_self_reference_kwarg_passing(
+        candidate["name"], candidate["value"]
+    ):
+        return True
     marker = DIFF_LINE_MARKER.search(line)
     if marker is not None:
         for candidate in ASSIGNMENT_TAIL.finditer(line, marker.end()):
```

### M2 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..0fc5632 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -91,7 +91,7 @@ RAW_CANDIDATES = re.compile(rf"(?=({RAW_SECRET_ASSIGNMENT.pattern}))", re.IGNORE
 # start or directly after a Unicode line separator: base's splitlines() cut made
 # `notes<U+2028>+ KEY=lit` its own diff line, and the newline-only cut must not lose
 # that (dev-3 G-01B). `(?!\+)` keeps the `+++ b/...` headers out of the marker.
-DIFF_LINE_MARKER = re.compile(r"(?:^|(?<=[\u2028\u2029\x0b\x0c\x85]))\+(?!\+)")
+DIFF_LINE_MARKER = re.compile(r"^\+(?!\+)")
 ASSIGNMENT_TAIL = re.compile(
     rf"(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
 )
```

### M3 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..36dea85 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -59,7 +59,7 @@ _LITERAL_VALUE = rf"(?P<value>{_QUOTED_LITERAL}|{_BARE_LITERAL})"
 # The value grammar keeps the placeholder and path-valued names out of every context;
 # the `{0,64}` name bound caps the per-position slot attempt (dev-2 R-03).
 _ASSIGNMENT_SLOT = (
-    r"[A-Za-z_][A-Za-z0-9_]{0,64}=(?:\"[^\"]*\"|'[^']*'|[^\"',\s]+),?[ \t]+(?:export\s+)?"
+    r"[A-Za-z_][A-Za-z0-9_]{0,64}=[^\"',\s]+[ \t]+(?:export\s+)?"
 )
 _ASSIGNMENT_PREFIX = (
     r"(?:^\s*(?:export\s+)?"
```

### M4 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..18c7aef 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -65,7 +65,7 @@ _ASSIGNMENT_PREFIX = (
     r"(?:^\s*(?:export\s+)?"
     r"|(?<=[;|&])\s*(?:export\s+)?"
     r"|(?<=[\u2028\u2029\x0b\x0c\x85])\s*(?:export\s+)?"
-    r"|(?:^|\s)(?:-{1,2}(?:env|e)|env)(?:[ \t]*=[ \t]*|[ \t]+|(?=[A-Za-z0-9_]))(?:export\s+)?"
+    r"|(?:^|\s)(?:-{1,2}(?:env|e)|env)[ \t]+(?:export\s+)?"
     rf"|{_ASSIGNMENT_SLOT})"
 )
 RAW_SECRET_ASSIGNMENT = re.compile(
```

### M5 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..9d01c4b 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -91,7 +91,7 @@ RAW_CANDIDATES = re.compile(rf"(?=({RAW_SECRET_ASSIGNMENT.pattern}))", re.IGNORE
 # start or directly after a Unicode line separator: base's splitlines() cut made
 # `notes<U+2028>+ KEY=lit` its own diff line, and the newline-only cut must not lose
 # that (dev-3 G-01B). `(?!\+)` keeps the `+++ b/...` headers out of the marker.
-DIFF_LINE_MARKER = re.compile(r"(?:^|(?<=[\u2028\u2029\x0b\x0c\x85]))\+(?!\+)")
+DIFF_LINE_MARKER = re.compile(r"(?:^|(?<=[\u2028\u2029\x0b\x0c\x85]))\+")
 ASSIGNMENT_TAIL = re.compile(
     rf"(?P<name>{_KEYWORD_TERMINATED_NAME})={_LITERAL_VALUE}", re.IGNORECASE
 )
```

### M6 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..93b909d 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -147,7 +147,7 @@ def find_literal_secret_assignment_lines(relative: str, text: str) -> list[int]:
     return [
         number
         for number, line in enumerate(
-            (raw.rstrip("\r") for raw in text.split("\n")),
+            (raw for raw in text.split("\n")),
             start=1,
         )
         if is_secret_env_assignment(line)
```

### M7 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..8100568 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -600,7 +600,7 @@ def test_eko129_c3_keycloak_bootstrap_self_reference_census_holds() -> None:
     text = read_text(relative)
     assert text is not None
     lines = text.split("\n")
-    assert sum(1 for line in lines if "token=token," in line) == 17
+    assert sum(1 for line in lines if "token=token," in line) == 14
     assert sum(1 for line in lines if "token=token" in line) == 29
     assert find_literal_secret_assignment_lines(relative, text) == []
 
```

### M8 — Base: `5b40a1534171448a16c6489c5d889dee2db17bf8`

```diff
diff --git a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
index 40fa898..24583a1 100644
--- a/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
+++ b/backend/tests/static/test_eko112_k06_synthetic_and_secret_free.py
@@ -116,11 +116,6 @@ def is_secret_env_assignment(line: str) -> bool:
     # dev-2 R-03: the mid-line diff search was quadratic on long non-matching lines (10k =
     # 8.1s measured, base 0.25ms); this linear membership prefilter guards both branches —
     # no match is possible without an `=` and a keyword on the line.
-    if "=" not in line:
-        return False
-    folded = line.casefold()
-    if not any(keyword in folded for keyword in _SECRET_KEYWORDS):
-        return False
     # dev-3 C-1: fire if ANY candidate is a non-held literal assignment; the line
     # holds only when every enumerated candidate is sanctioned (placeholder values are
     # not candidates at all — the literal value grammar never matches them).
```

