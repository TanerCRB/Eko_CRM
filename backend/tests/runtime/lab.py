"""EKO-1-11 migration lab: one composition with postgres and backend; migrate runs on demand.

The lab's backend image is the one the repository's normal build produced (`up --build`), so it
is the shipped image and the previous-release stand-in (C-4). Test-only revisions
(`tests/runtime/revisions/`) reach a migrate run only through a variant image built `FROM` that
image which adds revision files and nothing else (ADR-0004 addendum 2026-10-29). A planted
variant that also replaces a file is a contrast; no claim is proven on it.

Direct sessions are psql processes in the postgres container over its local socket, so their
`client_addr` is NULL and a migrate run's sessions are told apart by its container's address.
"""

import ipaddress
import json
import queue
import re
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tests.runtime.conftest import Composition
from tests.support.repo import REPO_ROOT

REVISIONS = Path(__file__).parent / "revisions"
SHIPPED_HEAD = "0002"
SHIPPED_TREE = ("0001", "0002")
# pg_dump writes a random \restrict key into every dump unless one is given.
DUMP_RESTRICT_KEY = "ekotestdump"
HEALTH_URL = "http://backend:8000/api/health"

# Name -> revision files added to the shipped image's migrations/versions/.
VARIANTS: dict[str, tuple[str, ...]] = {
    "next": ("t_next.py",),
    "sibling_a": ("t_sibling_a.py",),
    "sibling_b": ("t_sibling_b.py",),
    "slow_once": ("t_slow_once.py",),
    "slow": ("t_slow.py",),
    "c14_failing": ("t_c14_first.py", "t_c14_second_failing.py"),
    "c14_passing": ("t_c14_first.py", "t_c14_second_passing.py"),
    "c26_alter": ("t_c26_alter.py",),
    "sleep_35": ("t_sleep_35.py",),
    "sleep_25": ("t_sleep_25.py",),
}

ENV_PY = "/app/migrations/env.py"
SOURCE_ENV_PY = REPO_ROOT / "backend" / "migrations" / "env.py"

RESET_SQL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.relname);
  END LOOP;
  FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'S' LOOP
    EXECUTE format('DROP SEQUENCE IF EXISTS public.%I CASCADE', r.relname);
  END LOOP;
END $$;
"""

TABLES_PRESENT = (
    "SELECT to_regclass('public.alembic_version') IS NOT NULL, "
    "to_regclass('public.schema_revision_lineage') IS NOT NULL"
)

HEALTH_ONCE = """
import sys, urllib.error, urllib.request
try:
    status = urllib.request.urlopen(sys.argv[1], timeout=3).status
    print(status)  # leftovers-allow: probe runs in a container; stdout is its answer
except urllib.error.HTTPError as exc:
    print(exc.code)  # leftovers-allow: probe runs in a container; stdout is its answer
except OSError as exc:
    print(type(exc).__name__)  # leftovers-allow: probe runs in a container; stdout is its answer
"""

HEALTH_WATCH = """
import sys, time, urllib.error, urllib.request
end = time.monotonic() + float(sys.argv[2])
while time.monotonic() < end:
    try:
        status = str(urllib.request.urlopen(sys.argv[1], timeout=2).status)
    except urllib.error.HTTPError as exc:
        status = str(exc.code)
    except OSError as exc:
        status = type(exc).__name__
    print(status, flush=True)  # leftovers-allow: probe runs in a container; stdout is its answer
    time.sleep(0.25)
"""

SAFE_VALUE = re.compile(r"[A-Za-z0-9_.:-]+")


def docker(*args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"docker {' '.join(args[:3])} exited {result.returncode}\n{result.stderr[-3000:]}"
        )
    return result


class PsqlSession:
    """One long-lived psql session in the postgres container; statements are sent one at a time.

    Every statement is followed by an `\\echo` of a fresh marker, so the arrival time of the marker
    is the time the statement finished.
    """

    def __init__(self, composition: Composition, role: str = "postgres", name: str = "") -> None:
        app_name = name or f"eko-test-{uuid.uuid4().hex[:6]}"
        args = [
            *composition.base_args(), "exec", "-T", "-e", f"PGAPPNAME={app_name}",
            "postgres", "psql", "-U", role, "-d", "eko", "-AtXq", "-F", "\t",
        ]  # fmt: skip
        self.application_name = app_name
        self._process = subprocess.Popen(
            args,
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._lines: queue.Queue[tuple[float, str]] = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put((time.monotonic(), line.rstrip("\n")))

    def send(self, sql: str, **variables: str) -> str:
        """Send one statement without waiting; returns the marker `wait` waits for."""
        assert self._process.stdin is not None
        marker = f"done-{uuid.uuid4().hex}"
        lines = []
        for name, value in variables.items():
            assert SAFE_VALUE.fullmatch(value), value
            lines.append(f"\\set {name} {value}")
        statement = sql.strip()
        # psql keeps a statement without its semicolon in the buffer and runs it with the next one.
        if not statement.endswith(";"):
            statement += ";"
        lines += [statement, f"\\echo {marker}"]
        self._process.stdin.write("\n".join(lines) + "\n")
        self._process.stdin.flush()
        return marker

    def wait(self, marker: str, timeout: float = 60) -> tuple[float, list[str]]:
        """The time the marker arrived and the lines printed before it."""
        deadline = time.monotonic() + timeout
        collected: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"psql: no answer within {timeout} s; got {collected[-5:]}")
            try:
                arrived, line = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line == marker:
                return arrived, collected
            collected.append(line)

    def query(self, sql: str, **variables: str) -> list[list[str]]:
        _, lines = self.wait(self.send(sql, **variables), 120)
        errors = [line for line in lines if "ERROR:" in line or "FATAL:" in line]
        if errors:
            raise AssertionError(f"psql: {errors}")
        return [line.split("\t") for line in lines if line]

    def close(self) -> None:
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=15)


@dataclass
class MigrateRun:
    container: str
    address: str
    exited_at: list[float] = field(default_factory=list)
    _waiter: threading.Thread | None = None

    def start_waiting(self) -> None:
        def wait() -> None:
            docker("wait", self.container, timeout=900, check=False)
            self.exited_at.append(time.monotonic())

        self._waiter = threading.Thread(target=wait, daemon=True)
        self._waiter.start()

    def wait(self, timeout: float = 180) -> int:
        """The run's exit code, once it has exited."""
        assert self._waiter is not None
        self._waiter.join(timeout)
        assert not self._waiter.is_alive(), f"migrate run still running after {timeout} s"
        state = json.loads(docker("inspect", "-f", "{{json .State}}", self.container).stdout)
        assert state["Status"] == "exited", state
        code: int = state["ExitCode"]
        return code

    def running(self) -> bool:
        return not self.exited_at

    def logs(self) -> str:
        result = docker("logs", self.container, check=False)
        return result.stdout + result.stderr

    def remove(self) -> None:
        docker("rm", "-f", self.container, check=False)


@dataclass
class Lab:
    composition: Composition
    workdir: Path
    shipped_image: str
    prober: str
    monitor: PsqlSession
    images: dict[str, str] = field(default_factory=dict)

    # Database state -------------------------------------------------------------------------

    def sql(self, sql: str, **variables: str) -> list[list[str]]:
        return self.monitor.query(sql, **variables)

    def reset(self) -> None:
        """An empty application database: no table and no sequence in `public`."""
        self.sql(RESET_SQL)

    def versions(self) -> list[str] | None:
        [[has_versions, _]] = self.sql(TABLES_PRESENT)
        if has_versions != "t":
            return None
        rows = self.sql('SELECT version_num FROM alembic_version ORDER BY version_num COLLATE "C"')
        return [row[0] for row in rows]

    def lineage(self) -> set[str] | None:
        [[_, has_lineage]] = self.sql(TABLES_PRESENT)
        if has_lineage != "t":
            return None
        return {row[0] for row in self.sql("SELECT revision FROM schema_revision_lineage")}

    def comparison_dump(self) -> str:
        """The schema-only dump plus the rows of alembic_version and schema_revision_lineage."""
        schema = self.composition.compose(
            "exec", "-T", "postgres", "pg_dump", "-U", "postgres", "-d", "eko", "--schema-only",
            f"--restrict-key={DUMP_RESTRICT_KEY}",
        ).stdout  # fmt: skip
        versions = self.versions()
        lineage = self.lineage()
        rows = {
            "alembic_version": versions,
            "schema_revision_lineage": None if lineage is None else sorted(lineage),
        }
        return schema + "\n-- rows\n" + json.dumps(rows, sort_keys=True) + "\n"

    def at_head(self) -> None:
        """The shipped migrate run on an empty database."""
        self.reset()
        run = self.run_migrate()
        assert run[0] == 0, run[1]

    def at_variant_head(self, variant: str) -> None:
        self.reset()
        code, logs = self.run_migrate(self.variant(variant))
        assert code == 0, logs

    def set_versions(self, rows: list[str]) -> None:
        """Superuser edit of alembic_version, as a database no migrate wrote would hold."""
        self.sql("DELETE FROM alembic_version")
        for row in rows:
            self.sql("INSERT INTO alembic_version (version_num) VALUES (:'v')", v=row)

    def drop_lineage(self) -> None:
        self.sql("DROP TABLE IF EXISTS schema_revision_lineage")

    def at_0001(self) -> None:
        """The database as the release whose tree is {0001} left it: alembic_version only."""
        self.at_head()
        self.drop_lineage()
        self.set_versions(["0001"])

    # Images ---------------------------------------------------------------------------------

    def variant(
        self, name: str, files: tuple[str, ...] | None = None, replace: dict[str, str] | None = None
    ) -> str:
        """An image FROM the shipped image adding `files` to migrations/versions/.

        `replace` (path in the image -> content) is for planted contrasts only.
        """
        if name in self.images:
            return self.images[name]
        added = VARIANTS[name] if files is None else files
        context = self.workdir / "variants" / name
        (context / "versions").mkdir(parents=True)
        for file_name in added:
            (context / "versions" / file_name).write_bytes((REVISIONS / file_name).read_bytes())
        lines = [f"FROM {self.shipped_image}", "COPY versions/ /app/migrations/versions/"]
        for index, (target, content) in enumerate(sorted((replace or {}).items())):
            (context / f"replaced-{index}").write_text(content, encoding="utf-8")
            lines.append(f"COPY replaced-{index} {target}")
        (context / "Dockerfile").write_text("\n".join(lines) + "\n", encoding="utf-8")
        tag = f"localhost/eko-crm/backend-variant:{self.composition.project}-{name}"
        docker("build", "-q", "-t", tag, str(context), timeout=600)
        self.images[name] = tag
        return tag

    def planted_env_py(self, name: str, old: str, new: str, files: tuple[str, ...]) -> str:
        """A planted contrast: a variant whose env.py differs from the shipped one."""
        source = SOURCE_ENV_PY.read_text(encoding="utf-8")
        assert source.count(old) == 1, f"planted contrast {name}: {old!r} not found once"
        return self.variant(name, files, {ENV_PY: source.replace(old, new)})

    def image_python(self, image: str, script: str, *args: str) -> str:
        """Run a script in an image with no network, as root so every file is readable."""
        result = docker(
            "run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "python",
            image, "-c", script, *args, timeout=600,
        )  # fmt: skip
        return result.stdout

    def image_command(self, image: str, *command: str) -> subprocess.CompletedProcess[str]:
        return docker("run", "--rm", "--network", "none", image, *command, check=False)

    # Processes ------------------------------------------------------------------------------

    def _with_image(self, service: str, image: str | None) -> Composition:
        if image is None:
            return self.composition
        override = self.workdir / f"{service}-{uuid.uuid4().hex[:8]}.yaml"
        override.write_text(f"services:\n  {service}:\n    image: {image}\n", encoding="utf-8")
        return Composition(
            project=self.composition.project,
            env_file=self.composition.env_file,
            extra_files=[override],
        )

    def start_migrate(self, image: str | None = None) -> MigrateRun:
        started = self._with_image("migrate", image).compose("run", "-d", "--no-deps", "migrate")
        container = started.stdout.strip().splitlines()[-1]
        address = docker(
            "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container
        ).stdout.strip()
        ipaddress.ip_address(address)
        run = MigrateRun(container, address)
        run.start_waiting()
        return run

    def run_migrate(self, image: str | None = None, timeout: float = 180) -> tuple[int, str]:
        run = self.start_migrate(image)
        try:
            code = run.wait(timeout)
            return code, run.logs()
        finally:
            run.remove()

    def migrate_sessions(self, run: MigrateRun) -> int:
        [[count]] = self.sql(
            "SELECT count(*) FROM pg_stat_activity WHERE host(client_addr) = :'addr'",
            addr=run.address,
        )
        return int(count)

    def advisory_locks(self, run: MigrateRun) -> list[tuple[int, int, int, bool]]:
        """(classid, objid, objsubid, granted) of every advisory lock the run's sessions hold or
        wait for."""
        rows = self.sql(
            "SELECT l.classid, l.objid, l.objsubid, l.granted FROM pg_locks l "
            "JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE l.locktype = 'advisory' AND host(a.client_addr) = :'addr'",
            addr=run.address,
        )
        return [(int(r[0]), int(r[1]), int(r[2]), r[3] == "t") for r in rows]

    def relation_locks(self, run: MigrateRun) -> list[str]:
        """Relations of `public` on which the run's sessions hold or wait for a lock."""
        rows = self.sql(
            "SELECT c.relname FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "JOIN pg_class c ON c.oid = l.relation "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE l.locktype = 'relation' AND n.nspname = 'public' "
            "AND host(a.client_addr) = :'addr'",
            addr=run.address,
        )
        return sorted(r[0] for r in rows)

    def activity(self, run: MigrateRun) -> list[tuple[str, str, str]]:
        """(wait_event_type, state, query) of the run's sessions."""
        rows = self.sql(
            "SELECT coalesce(wait_event_type, ''), coalesce(state, ''), "
            "replace(replace(query, chr(10), ' '), chr(9), ' ') FROM pg_stat_activity "
            "WHERE host(client_addr) = :'addr'",
            addr=run.address,
        )
        return [(r[0], r[1], r[2]) for r in rows]

    def wait_until(
        self, condition: str, predicate: Callable[[], bool], timeout: float = 30
    ) -> float:
        """Poll `predicate()` until true; the monotonic time it first held."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return time.monotonic()
            time.sleep(0.05)
        raise AssertionError(f"not observed within {timeout} s: {condition}")

    def health(self) -> str:
        return docker("exec", self.prober, "python", "-c", HEALTH_ONCE, HEALTH_URL).stdout.strip()

    def watch_health(self, seconds: float) -> "HealthWatch":
        return HealthWatch(self.prober, seconds)

    def serving_backend(self) -> str:
        """The database at the shipped head and backend started on it, answering; its id."""
        self.at_head()
        self.composition.compose("up", "-d", "--no-deps", "--force-recreate", "backend")
        self.wait_for_health("200", 90)
        return self.composition.container_id("backend")

    def wait_for_health(self, status: str, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        last = ""
        while time.monotonic() < deadline:
            last = self.health()
            if last == status:
                return
            time.sleep(0.5)
        raise AssertionError(f"backend health {last!r}, not {status!r}, after {seconds} s")

    def start_worker(self) -> str:
        started = self.composition.compose("run", "-d", "--no-deps", "worker")
        return started.stdout.strip().splitlines()[-1]


class HealthWatch:
    """Polls backend's /api/health from the prober container every 0.25 s for a fixed time."""

    def __init__(self, prober: str, seconds: float) -> None:
        self._process = subprocess.Popen(
            ["docker", "exec", prober, "python", "-c", HEALTH_WATCH, HEALTH_URL, str(seconds)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._seconds = seconds

    def statuses(self) -> list[str]:
        out, _ = self._process.communicate(timeout=self._seconds + 60)
        return out.split()


def container_state(container: str) -> dict[str, object]:
    state: dict[str, object] = json.loads(
        docker("inspect", "-f", "{{json .State}}", container).stdout
    )
    return state


def restart_count(container: str) -> int:
    return int(docker("inspect", "-f", "{{.RestartCount}}", container).stdout.strip())


HEALTH_BODY = """
import sys, urllib.request
body = urllib.request.urlopen(sys.argv[1], timeout=3).read().decode()
print(body)  # leftovers-allow: probe runs in a container; stdout is its answer
"""


def health_body(lab: Lab) -> str:
    return docker("exec", lab.prober, "python", "-c", HEALTH_BODY, HEALTH_URL).stdout.strip()


def exit_code_once_exited(container: str, seconds: float = 60) -> int:
    """The exit code the next time the container is not running (exited, or between restarts)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = container_state(container)
        if state["Status"] in {"exited", "restarting", "dead"}:
            code = state["ExitCode"]
            assert isinstance(code, int)
            return code
        time.sleep(0.2)
    raise AssertionError(f"{container} did not exit within {seconds} s")


def configuration_values(lab: Lab) -> list[str]:
    """Values a refusal line must never name: passwords, the host (also in a URL), the role."""
    env = lab.composition.env
    passwords = [value for name, value in env.items() if "PASSWORD" in name]
    return [*passwords, "postgres", "eko_app"]


def _no_row(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions([])


def _two_rows(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions(["0001", "0002"])


def _unknown(lab: Lab) -> None:
    lab.at_head()
    lab.set_versions(["zz_never_written"])


def _lineage_emptied(lab: Lab) -> None:
    lab.at_variant_head("next")
    lab.sql("DELETE FROM schema_revision_lineage")


def _lineage_dropped(lab: Lab) -> None:
    lab.at_variant_head("next")
    lab.drop_lineage()


# K-02's refusing states (i)-(vi) and accepting states, each prepared on the lab database.
REFUSING_STATES: dict[str, Callable[[Lab], None]] = {
    "i-older-0001": Lab.at_0001,
    "ii-no-alembic-version": Lab.reset,
    "iii-no-row": _no_row,
    "iv-two-rows": _two_rows,
    "v-unknown-identifier": _unknown,
    "vi-descendant-lineage-emptied": _lineage_emptied,
    "vi-descendant-lineage-dropped": _lineage_dropped,
}
ACCEPTING_STATES: dict[str, Callable[[Lab], None]] = {
    "head-0002": Lab.at_head,
    "descendant-t_next": lambda lab: lab.at_variant_head("next"),
}
