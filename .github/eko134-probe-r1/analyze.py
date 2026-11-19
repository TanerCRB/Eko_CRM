"""EKO-1-34 probe r1, transient: redact one pytest invocation and judge it.

Run on the runner with `python3 -I`, once per invocation, by `.github/workflows/eko134-probe-r1.yml`
on the throwaway branch EKO-1-34-probe-r1 (never part of the PR).

  analyze.py k02      LABEL LOG JUNIT RC BASETEMP OUT
  analyze.py full     LABEL LOG JUNIT RC BASETEMP OUT
  analyze.py mutation LABEL LOG JUNIT RC BASETEMP OUT TEST KILLS

KILLS: `||` separates alternatives, any one of which is enough; within an alternative, `|`
separates kills that must all appear. A kill starting with `re:` is a regular expression searched
line by line (multiline) in the failure text; any other kill is a substring.

It writes the redacted log to OUT/LABEL/pytest.log and appends rows to these files in OUT:
- results.tsv: every test and its outcome;
- hold-values.tsv: the K-02 hold lines;
- continuous.tsv: the continuous test's settle outcome;
- other-failures.txt: failures outside the K-02 module (full mode);
- problems.txt: one line per problem. The job is red when this file is not empty.

Redaction uses the same rules as the EKO-1-34 probe: secret-named values of the invocation's
synthetic env files, authorization and token parameters, session values, synthetic passwords,
JWT shapes and typed values are redacted. Header, env-file and inspect lines are withheld.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODULE = "tests.runtime.test_eko134_k02_network_change_during_login"
K02_TESTS = (
    "test_eko134_k02_new_veth_during_login_redirect_fails_at_the_pre_fix_harness",
    "test_eko134_k02_new_veth_before_login_passes_at_the_fixed_harness",
    "test_eko134_k02_contrast_without_the_interference_passes_at_the_pre_fix_harness",
    "test_eko134_k02_continuous_interference_fails_the_wait_by_name_within_its_bound",
)
PRE_FIX, _, _, CONTINUOUS = K02_TESTS

mode, label, log_path, junit_path, rc, basetemp, out = sys.argv[1:8]
extra = sys.argv[8:]
out_dir = Path(out)
(out_dir / label).mkdir(parents=True, exist_ok=True)

SECRET_NAME = re.compile(r"(PASSWORD|SECRET|KEY|CREDENTIAL|TOKEN)")
values: set[str] = set()
env_names: set[str] = set()
for env in Path(basetemp).rglob("*.env"):
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        name, sep, value = line.partition("=")
        if not sep:
            continue
        env_names.add(name)
        if SECRET_NAME.search(name) and len(value) >= 6:
            values.add(value)
RULES = [
    # S-01: any parameter whose name ends in `code` or `state` (`session_code`, `session_state`),
    # and Keycloak's `client_data`, `tab_id` and `execution`; the name is kept, the value goes.
    (re.compile(r"(?i)\b(\w*code|\w*state|nonce|code_challenge|code_verifier|client_data|tab_id"
                r"|execution|id_token_hint|id_token|access_token|refresh_token|token)"
                r"=[^&\s\"'#<>]*"),
     r"\1=<redacted>"),
    (re.compile(r"(?i)\b(__Host-[\w-]+|__Secure-[\w-]+|KEYCLOAK_[\w-]+"
                r"|AUTH_SESSION_ID[\w-]*|KC_RESTART|KC_AUTH_SESSION_HASH)=[^;\s\"']*"),
     r"\1=<redacted>"),
    (re.compile(r"synthetic-[A-Za-z0-9_-]+"), "synthetic-<redacted>"),
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]*"), "<jwt-redacted>"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1 <redacted>"),
    (re.compile(r'\b(fill|type|pressSequentially)\("(?:[^"\\]|\\.)*"\)'), r"\1(<redacted>)"),
    (re.compile(r'\bvalue=(\\?)"[^"\\]*\1"'), r'value="<redacted>"'),
]
DROP = re.compile(r"(?i)^\s*(set-)?cookie\s*:|^\s*authorization\s*:|\"Env\"\s*:"
                  r"|\"NetworkSettings\"|^\s*[A-Z][A-Z0-9_]*=")
ENV_LINE = (re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(env_names)) + r")=")
            if env_names else None)
WITHHELD = "<line withheld by the probe's redaction>"


def clean(line: str) -> str:
    if DROP.search(line) or (ENV_LINE is not None and ENV_LINE.search(line)):
        return WITHHELD
    for value in values:
        line = line.replace(value, "<redacted>")
    for pattern, replacement in RULES:
        line = pattern.sub(replacement, line)
    return line


def append(name: str, rows: list[str]) -> None:
    if rows:
        with (out_dir / name).open("a", encoding="utf-8") as handle:
            handle.write("".join(row + "\n" for row in rows))


problems: list[str] = []
raw_log = Path(log_path)
log = [clean(part) for line in (raw_log.read_text(encoding="utf-8", errors="replace").splitlines()
                                if raw_log.is_file() else [])
       for part in line.split("\\n")]
(out_dir / label / "pytest.log").write_text("\n".join(log) + "\n", encoding="utf-8")

# Outcomes from junit, keyed by (module, test).
outcomes: dict[tuple[str, str], tuple[str, str, str]] = {}
junit = Path(junit_path)
if junit.is_file():
    for case in ET.parse(junit).getroot().iter("testcase"):
        key = (case.get("classname", ""), case.get("name", ""))
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is not None:
            text = (bad.get("message") or "") + "\n" + (bad.text or "")
            first = (bad.get("message") or "").splitlines()
            outcomes[key] = (bad.tag, clean(first[0] if first else ""), clean(text))
        elif case.find("skipped") is not None:
            outcomes[key] = ("skipped", "", "")
        else:
            outcomes[key] = ("passed", "", "")
else:
    problems.append(f"{label}: no junit file")
append("results.tsv", [f"{label}\t{module}\t{name}\t{outcome}\t{first}"
                       for (module, name), (outcome, first, _) in sorted(outcomes.items())])

# Live-log lines, attributed to the test whose node id the verbose run printed last.
NODE = re.compile(r"(tests/runtime/[\w/]+\.py)::(test_\w+)")
HOLD = re.compile(
    r"hold: settled at first request (\S+), members \[(.*?)\]; interference (\S+) started "
    r"(\S+) s after it; first failure (.+?) \(of the first request: (\S+)\) (\S+) s after it, "
    r"settled (\S+), members \[(.*?)\]")
SETTLE_RAISED = re.compile(r"eko134-probe settle raised (\w+) after ([\d.]+) s: (.*)$")
# The report sections after the run (`-rA` PASSES, FAILURES, the summaries) repeat captured
# logs under other headers. Only the live log is read, so no line is counted twice.
REPORT_SECTION = re.compile(r"^=+ (PASSES|FAILURES|ERRORS|warnings summary|short test summary)")
current = ""
holds: dict[str, list[tuple[str, ...]]] = {}
raised: dict[str, list[tuple[str, ...]]] = {}
for line in log:
    if REPORT_SECTION.match(line):
        break
    node = NODE.search(line)
    if node and "INFO" not in line:
        current = node.group(2)
    found = HOLD.search(line)
    if found:
        holds.setdefault(current, []).append(found.groups())
    found = SETTLE_RAISED.search(line)
    if found:
        raised.setdefault(current, []).append(found.groups())
append("hold-values.tsv", [f"{label}\t{test}\t" + "\t".join(groups)
                           for test, rows in holds.items() for groups in rows])
append("continuous.tsv", [f"{label}\t{test}\t" + "\t".join(groups)
                          for test, rows in raised.items() for groups in rows])


def judge_k02() -> None:
    for name in K02_TESTS:
        outcome = outcomes.get((MODULE, name), ("missing", "", ""))[0]
        if outcome != "passed":
            problems.append(f"{label}: {name} {outcome}")
    if not holds.get(PRE_FIX):
        problems.append(f"{label}: no hold line logged for the pre-fix-harness test")
    continuous = [row for row in raised.get(CONTINUOUS, []) if row[0] == "HostNetworkNotSettled"]
    if len(continuous) != 1:
        problems.append(f"{label}: {len(continuous)} HostNetworkNotSettled settle lines for the"
                        " continuous test, expected 1")


if mode == "k02":
    judge_k02()
    if rc != "0":
        problems.append(f"{label}: pytest exited {rc}")
elif mode == "full":
    judge_k02()
    # Reported by name, kept apart from the K-02 verdict.
    append("other-failures.txt", [f"{label}\t{module}::{name}\t{outcome}\t{first}"
                                  for (module, name), (outcome, first, _) in sorted(outcomes.items())
                                  if module != MODULE and outcome in ("failure", "error")])
elif mode == "mutation":
    test, spec = extra[0], "|".join(extra[1:])
    outcome, first, text = outcomes.get((MODULE, test), ("missing", "", ""))
    append("mutation.tsv", [f"{label}\t{test}\t{rc}\t{outcome}\t{first}"])
    if rc != "1":
        problems.append(f"{label}: pytest exited {rc}, expected 1 (a test failure)")
    if outcome != "failure":
        problems.append(f"{label}: {test} {outcome}, expected failure")
    def holds(kill: str) -> bool:
        if kill.startswith("re:"):
            return re.search(kill[3:], text, re.MULTILINE) is not None
        return kill in text

    alternatives = [[k for k in alt.split("|") if k] for alt in spec.split("||")]
    matched = [alt for alt in alternatives if alt and all(holds(k) for k in alt)]
    append("mutation-kill.txt", [
        f"{label}\texpected {spec!r}\t"
        + (f"matched {'|'.join(matched[0])!r}" if matched else "no match")
    ])
    if not matched:
        problems.append(f"{label}: the red does not hold the expected kill {spec!r}")
else:
    problems.append(f"unknown mode {mode}")

append("problems.txt", problems)
print("\n".join(problems) or f"{label}: no problem found")  # leftovers-allow: verdict for the job log
