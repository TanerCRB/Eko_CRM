"""EKO-1-10 K-04: date APIs, client storage, `import.meta.env` and the tree boundary in frontend/.

ADR-0001-C13 and C14 (grep halves) as restated 2026-10-29, ADR-0005-C12 (grep half), checklist
rules 4 and 7. The frontend files are read as data (Out of scope: permanent, not rule 7).
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
import yaml

from tests.support import source_checks as sc
from tests.support import workflow_checks as wc
from tests.support.repo import REPO_ROOT

HELPER = "frontend/src/time/warsaw.ts"
COMPONENT = "frontend/src/components/Card.tsx"
CLIENT = "frontend/src/api/client.ts"
ALLOW_LIST = "frontend/env-allowlist.json"
Check = Callable[[sc.Files], list[str]]


def fails(check: Check, path: str, text: str) -> bool:
    return check({path: text}) != []


# ADR-0001-C13: nowhere in frontend/src/, the helper included ----------------------------------

DEVICE_ZONE = [
    "d.getFullYear()",
    "d.getMonth()",
    "d.getDate()",
    "d.getDay()",
    "d.getHours()",
    "d.getMinutes()",
    "d.getTimezoneOffset()",
    "d.setDate(1)",
    "d.setHours(0)",
    "d.setFullYear(2026)",
    "d.setMonth(0)",
    "d.setMinutes(0)",
    "d.setSeconds(0)",
    "d.setMilliseconds(0)",
    "d.toDateString()",
    "d.toTimeString()",
    "const s = Date();",
    "const s = Date ();",
    "// d.getHours() in a comment",
    "const a = 1;\r\nconst b = d.getHours();\r\n",
]


def test_eko110_k04_device_zone_reads_and_setters_nowhere() -> None:
    assert sc.device_zone_reads(sc.repository_sources()) == []


@pytest.mark.parametrize("text", DEVICE_ZONE)
@pytest.mark.parametrize("path", [COMPONENT, HELPER, "frontend/src/fixtures/x.ts"])
def test_eko110_k04_device_zone_fails_everywhere(path: str, text: str) -> None:
    assert fails(sc.device_zone_reads, path, text + "\n")


@pytest.mark.parametrize(
    "text",
    [
        "new Date(0)",
        "new Date(iso)",
        "Date.now()",
        "d.getUTCDate()",
        "d.setUTCHours(0)",
        "d.toLocaleDateString()",
        "const fmt = new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw' });",
        "export const label = 'Bliżej Twoich klientów';",
    ],
)
def test_eko110_k04_device_zone_contrasts_pass(text: str) -> None:
    assert sc.device_zone_reads({HELPER: text + "\n"}) == []
    assert sc.device_zone_reads({"frontend/tests/x.test.ts": "d.getHours();\n"}) == []


# ADR-0001-C14: only in frontend/src/time/warsaw.ts ----------------------------------------------

HELPER_ONLY = [
    "d.toISOString()",
    "d.getUTCDate()",
    "Date.UTC(2026, 0, 1)",
    "d.toLocaleDateString('pl-PL')",
    "(1234.5).toLocaleString('pl-PL')",
    "new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw' })",
    "Temporal.Now.instant()",
    "import { format } from 'date-fns';",
    "import dayjs from 'dayjs';",
    "import { DateTime } from 'luxon';",
    "import moment from 'moment';",
    'import moment from "moment";',
    "new Date(2026, 9, 25)",
    "d.setUTCHours(0)",
    "d.setUTCFullYear(2026)",
    "Date.now()",
    "new Date()",
    "new Date( )",
    "new Date;",
    "// Date.now() in a comment",
]


def test_eko110_k04_date_apis_only_in_helper() -> None:
    assert sc.date_apis_outside_helper(sc.repository_sources()) == []


@pytest.mark.parametrize("text", HELPER_ONLY)
@pytest.mark.parametrize(
    "path",
    [
        COMPONENT,
        CLIENT,
        "frontend/src/time/other.ts",
        "frontend/src/time/warsaw.test.ts",
        "frontend/src/time/warsawHelpers.ts",
        "frontend/src/fixtures/x.ts",
    ],
)
def test_eko110_k04_date_api_fails_outside_helper(path: str, text: str) -> None:
    assert fails(sc.date_apis_outside_helper, path, text + "\n")


@pytest.mark.parametrize("text", HELPER_ONLY)
def test_eko110_k04_date_api_passes_in_helper(text: str) -> None:
    assert sc.date_apis_outside_helper({HELPER: text + "\n"}) == []


@pytest.mark.parametrize(
    "text", ["new Date(0)", "new Date(iso)", "performance.now()", "new Intl.NumberFormat('pl-PL')"]
)
def test_eko110_k04_date_api_contrasts_pass_outside_helper(text: str) -> None:
    assert sc.date_apis_outside_helper({COMPONENT: text + "\n"}) == []


def test_eko110_k04_to_json_nowhere() -> None:
    assert sc.to_json(sc.repository_sources()) == []
    for path in (COMPONENT, HELPER, CLIENT):
        assert fails(sc.to_json, path, "const s = d.toJSON();\n"), path
    assert sc.to_json({"frontend/tests/x.test.ts": "d.toJSON();\n"}) == []


# The CI lint step (G-7 A) ----------------------------------------------------------------------


def test_eko110_k04_ci_runs_frontend_lint() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job: dict[str, Any] = workflow["jobs"]["frontend"]
    runs = [str(step.get("run", "")).strip() for step in job["steps"]]
    assert "pnpm lint" in runs
    lint = next(s for s in job["steps"] if str(s.get("run", "")).strip() == "pnpm lint")
    assert lint.get("working-directory") == "frontend"
    assert runs.index("pnpm lint") > runs.index("pnpm install --frozen-lockfile")
    assert "if" not in job and "if" not in lint
    assert wc.failures_fail_the_run({"jobs": {"frontend": job}}) == []


# ADR-0005-C12, grep half -----------------------------------------------------------------------

STORAGE = [
    "localStorage.setItem('k', v)",
    "window.localStorage.getItem('k')",
    "sessionStorage.clear()",
    "indexedDB.open('db')",
    "caches.open('v1')",
    "navigator.serviceWorker.register('/sw.js')",
]


def test_eko110_k04_no_client_storage() -> None:
    assert sc.client_storage(sc.repository_sources()) == []
    for text in STORAGE:
        for path in (COMPONENT, HELPER, "frontend/src/main.tsx"):
            assert fails(sc.client_storage, path, text + "\n"), (path, text)
    assert sc.client_storage({"frontend/tests/x.test.ts": "localStorage.setItem('k', v)\n"}) == []


# Checklist rule 4 -------------------------------------------------------------------------------


def allow_list() -> frozenset[str]:
    names = json.loads((REPO_ROOT / ALLOW_LIST).read_text(encoding="utf-8"))
    assert isinstance(names, list) and all(isinstance(n, str) for n in names), ALLOW_LIST
    return frozenset(names)


def test_eko110_k04_env_reads_builtin_or_allow_listed() -> None:
    assert sc.frontend_env_reads(sc.repository_sources(), allow_list()) == []


@pytest.mark.parametrize(
    "text",
    [
        "const t = import.meta.env.VITE_API_TOKEN;",
        "const m = import.meta.env.MODEX;",
        "const { VITE_X } = import.meta.env;",
        "const x = import.meta.env['VITE_X'];",
        'const x = import.meta.env["VITE_X"];',
        "const all = import.meta.env;",
        "const k = import.meta.env[key];",
        "// VITE_SECRET is read by the build",
        "const a = 1;\r\nconst t = import.meta.env.VITE_API_TOKEN;\r\n",
    ],
)
@pytest.mark.parametrize(
    "path", ["frontend/src/mount.tsx", "frontend/vite.config.ts", "frontend/tests/x.test.ts"]
)
def test_eko110_k04_env_read_fails(path: str, text: str) -> None:
    assert sc.frontend_env_reads({path: text + "\n"}, frozenset()) != []


@pytest.mark.parametrize(
    "text",
    [
        "const m = import.meta.env.MODE;",
        "const b = import.meta.env.BASE_URL;",
        "const p = import.meta.env.PROD;",
        "const d = import.meta.env.DEV;",
        "const s = import.meta.env.SSR;",
        "const m = import.meta.env['MODE'];",
        "tsconfigRootDir: import.meta.dirname,",
    ],
)
def test_eko110_k04_env_builtin_passes(text: str) -> None:
    assert sc.frontend_env_reads({"frontend/src/mount.tsx": text + "\n"}, frozenset()) == []


def test_eko110_k04_env_allow_list_admits_its_names_only() -> None:
    text = "const base = import.meta.env.VITE_API_BASE;\n"
    assert sc.frontend_env_reads({"frontend/src/api/client.ts": text}, frozenset()) != []
    allowed = frozenset({"VITE_API_BASE"})
    assert sc.frontend_env_reads({"frontend/src/api/client.ts": text}, allowed) == []
    other = "const t = import.meta.env.VITE_API_TOKEN;\n"
    assert sc.frontend_env_reads({"frontend/src/api/client.ts": other}, allowed) != []


def test_eko110_k04_no_env_prefix_or_define_in_vite_config() -> None:
    assert sc.vite_env_injection(sc.repository_sources()) == []
    for name in ("vite.config.ts", "vite.config.js", "vite.config.mts", "vite.config.mjs"):
        path = f"frontend/{name}"
        assert fails(sc.vite_env_injection, path, "export default { envPrefix: 'APP_' };\n"), path
        assert fails(sc.vite_env_injection, path, "export default { define: { X: '1' } };\n"), path
    real = "export default defineConfig({ build: { assetsInlineLimit: 0 } });\n"
    assert sc.vite_env_injection({"frontend/vite.config.ts": real}) == []


# Checklist rule 7 -------------------------------------------------------------------------------

CROSS_REFERENCES = [
    ("frontend/src/x.ts", 'import x from "../../backend/app/x";'),
    ("frontend/src/x.ts", "const x = require('../backend');"),
    ("frontend/src/x.ts", 'const x = await import("../../backend/x");'),
    ("frontend/vite.config.ts", 'const p = path.join(root, "..", "backend");'),
    ("frontend/tests/x.test.ts", "// see ../backend/app/main.py"),
    ("backend/app/serve.py", 'DIST = "../frontend/dist"'),
    ("backend/app/main.py", 'DIST = Path(__file__).parents[2] / "frontend" / "dist"'),
    ("backend/app/main.py", "import frontend"),
    ("backend/migrations/env.py", "SEED = '../frontend/src/i18n/pl.ts'"),
    ("backend/app/services/fixtures/x.py", 'DIST = "../frontend/dist"'),
]


def test_eko110_k04_no_reference_across_backend_and_frontend() -> None:
    assert sc.cross_tree_references(sc.repository_sources()) == []


@pytest.mark.parametrize(("path", "text"), CROSS_REFERENCES)
def test_eko110_k04_cross_reference_fails(path: str, text: str) -> None:
    assert fails(sc.cross_tree_references, path, text + "\n")


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("frontend/src/x.ts", 'import x from "@/api/backendClient";'),
        ("frontend/src/x.ts", "// the backend answers on /api/"),
        ("backend/app/main.py", '"""The frontend is served by its own image."""'),
        ("backend/tests/x.py", 'DIST = "../frontend/dist"'),
    ],
)
def test_eko110_k04_cross_reference_contrasts_pass(path: str, text: str) -> None:
    assert sc.cross_tree_references({path: text + "\n"}) == []


# R-02: "`new Date(` with two or more arguments", judged by its arguments, not by `[^)]*,`.
TWO_OR_MORE_ARGUMENTS = [
    "new Date(Number(year), month - 1, day)",
    "new Date(parseInt(y, 10), 0, 1)",
    "new Date(parts[0] /* ) */, 1)",
    "new Date(parts[0] // )\n, 1)",
    "new Date(...parts)",
    "new Date(\n  year,\n  month,\n)",
    "new Date(label(')'), 1)",
    "new Date ( { y }.y, 1 )",
]
ONE_ARGUMENT = [
    "new Date(Number(ms))",
    "new Date(parseInt(s, 10))",
    "new Date(toInstant(a, b))",
    "new Date([a, b].join(''))",
    "new Date('2026-10-25, 10:00')",
    "new Date(`${a},${b}`)",
    "new Date(iso,)",
]


@pytest.mark.parametrize("text", TWO_OR_MORE_ARGUMENTS)
def test_eko110_k04_new_date_with_two_or_more_arguments_fails(text: str) -> None:
    assert fails(sc.date_apis_outside_helper, COMPONENT, f"const d = {text};\n")
    assert sc.date_apis_outside_helper({HELPER: f"const d = {text};\n"}) == []


@pytest.mark.parametrize("text", ONE_ARGUMENT)
def test_eko110_k04_new_date_with_one_argument_passes(text: str) -> None:
    assert sc.date_apis_outside_helper({COMPONENT: f"const d = {text};\n"}) == []
