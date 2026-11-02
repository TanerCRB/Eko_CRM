"""EKO-1-14 backup lab: postgres, keycloak and migrate on demand, plus the destination double.

The double (destination_double/) is a container of the test harness only. It is attached to the
composition's network while the lab runs and is never part of compose.yaml (ADR-0004-C1, G-2 A).
Its keys and the age key pair are generated for every lab; the composition receives only the
recipient, the double's host key and the backup account's credential (synthetic, test-only).

Runs are one-off containers of the `backup` service, started with the command the schedule file
names (K-01) or the on-demand command documented in backup/README.md (K-05); no runner here
writes its own command line.
"""

import base64
import hashlib
import io
import json
import os
import re
import secrets
import shlex
import subprocess
import tarfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.runtime.conftest import UP_TIMEOUT_SECONDS, Composition, new_composition, read_env
from tests.runtime.conftest import write_env as write_env_file
from tests.runtime.lab import Lab, PsqlSession, docker
from tests.support import migration_checks as mc
from tests.support.repo import REPO_ROOT

DOUBLE_CONTEXT = Path(__file__).parent / "destination_double"
# A run of the lab is seconds; the variable shortens the wait where a run is known to hang.
RUN_TIMEOUT_SECONDS = float(os.environ.get("EKO_BACKUP_RUN_TIMEOUT", "600"))
README = REPO_ROOT / "backup" / "README.md"
SCHEDULE = REPO_ROOT / "backup" / "schedule"
INCOMING = "/incoming"
OBJECTS = ("application.dump.age", "keycloak.dump.age", "roles.sql.age", "manifest.json.age")
SET_NAME = re.compile(r"eko-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{16}")
KEY = mc.lock_key((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
# A Keycloak table that Keycloak reads only while it starts (Liquibase's lock); hold point H1.
H1_TABLE = "databasechangeloglock"
BACKUP_VARIABLES = (
    "BACKUP_DESTINATION",
    "BACKUP_DESTINATION_HOST_KEY",
    "BACKUP_DESTINATION_CREDENTIAL",
    "BACKUP_ENCRYPTION_PUBLIC_KEY",
)
LOCK_BIGINT = "SELECT pg_advisory_lock(CAST(:'k' AS bigint))"
UNLOCK_BIGINT = "SELECT pg_advisory_unlock(CAST(:'k' AS bigint))"
DIACRITICS = "Zażółć gęślą jaźń ŁÓDŹ"
PROBE_VARIANT = ("t_backup_probe.py",)
LATER_VARIANT = ("t_backup_probe.py", "t_backup_later.py")


# The documented interface: backup/schedule and backup/README.md -------------------------------


def schedule_entries(text: str) -> list[list[str]]:
    lines = [line.split() for line in text.splitlines()]
    return [fields for fields in lines if fields and not fields[0].startswith("#")]


def schedule_command() -> list[str]:
    """The run command of the schedule file's one entry (time, zone, command)."""
    [entry] = schedule_entries(SCHEDULE.read_text(encoding="utf-8"))
    return entry[2:]


def documented(block: str) -> str:
    """The fenced block that follows `<!-- <block> -->` in backup/README.md."""
    text = README.read_text(encoding="utf-8")
    match = re.search(rf"<!-- {re.escape(block)} -->\s*```[a-z]*\n(.*?)\n```", text, re.DOTALL)
    assert match is not None, f"backup/README.md documents no {block}"
    return match.group(1).strip()


def failure_pattern() -> re.Pattern[str]:
    return re.compile(documented("failure-line-pattern"))


def on_demand_arguments() -> list[str]:
    """The documented on-demand command, without its leading `docker compose`."""
    words = shlex.split(documented("on-demand-command"))
    assert words[:2] == ["docker", "compose"], words
    return words[2:]


def failure_lines(output: str) -> list[str]:
    pattern = failure_pattern()
    return [line for line in output.splitlines() if pattern.fullmatch(line)]


def failure_fields(line: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in line.split()[3:])


# The destination double ---------------------------------------------------------------------


@dataclass
class Double:
    container: str
    alias: str
    host_key: str
    credential: str

    def run(
        self, *command: str, stdin: bytes | None = None, check: bool = True, timeout: int = 300
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ["docker", "exec", "-i", "-u", "0", self.container, *command],
            input=stdin,
            capture_output=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"double: {command[:2]} exited {result.returncode}: {result.stderr!r}"
            )
        return result

    def sh(self, script: str, stdin: bytes | None = None, check: bool = True) -> str:
        return self.run("sh", "-c", script, stdin=stdin, check=check).stdout.decode()

    def objects(self, directory: str = INCOMING) -> dict[str, int]:
        listing = self.sh(f"find {directory} -maxdepth 1 -type f -printf '%f %s\\n'")
        pairs = (line.rsplit(" ", 1) for line in listing.splitlines() if line)
        return {name: int(size) for name, size in pairs}

    def read(self, name: str, directory: str = INCOMING) -> bytes:
        return self.run("cat", f"{directory}/{name}").stdout

    def sha256(self, name: str, directory: str = INCOMING) -> str:
        """Computed in the double, so a large object is not copied out to be hashed."""
        digest = self.run("sha256sum", f"{directory}/{name}").stdout.decode().split()[0]
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest
        return digest

    def new_directory(self) -> str:
        """An empty incoming directory, as the account's own (write and search only)."""
        directory = f"/incoming-{uuid.uuid4().hex[:8]}"
        self.sh(f"mkdir {directory} && chown eko-backup {directory} && chmod 0300 {directory}")
        return directory

    def records(self) -> list[dict[str, Any]]:
        text = self.run("cat", "/var/log/eko-double/access.jsonl").stdout.decode()
        return [json.loads(line) for line in text.splitlines() if line]

    def set_mode(self, mode: str) -> None:
        self.sh(f"echo {shlex.quote(mode)} > /etc/eko-double/mode")

    def new_identity(self) -> tuple[str, str]:
        """A fresh age key pair, generated here, outside the composition: (file, recipient)."""
        path = f"/keys/age-{uuid.uuid4().hex[:8]}"
        self.run("age-keygen", "-o", path)
        public = self.run("age-keygen", "-y", path).stdout.decode().strip()
        assert public.startswith("age1"), public
        return path, public

    def decrypt(self, name: str, identity: str) -> subprocess.CompletedProcess[bytes]:
        return self.run("age", "-d", "-i", identity, f"{INCOMING}/{name}", check=False)

    def sftp(self, account: str, batch: str) -> subprocess.CompletedProcess[bytes]:
        """An SFTP batch with one of the double's own credentials, to the double itself."""
        return self.run(
            "sftp", "-b", "-", "-i", f"/keys/{account}", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR", f"{account}@127.0.0.1",
            stdin=batch.encode(), check=False,
        )  # fmt: skip


def set_names(double: Double, directory: str = INCOMING) -> set[str]:
    return {m.group(0) for name in double.objects(directory) if (m := SET_NAME.match(name))}


def completeness_problems(double: Double, name: str, directory: str = INCOMING) -> list[str]:
    """The completeness rule (ADR-0004 addendum 2026-10-30), checked without the private key."""
    objects = double.objects(directory)
    record_name = f"{name}.complete"
    if record_name not in objects:
        return [f"{name}: no completion record"]
    try:
        record = double.read(record_name, directory).decode()
        lines = [line.split(" ") for line in record.splitlines()]
        listed = {fields[0]: (int(fields[1]), fields[2]) for fields in lines}
        assert all(len(fields) == 3 for fields in lines)
    except (ValueError, IndexError, AssertionError, UnicodeDecodeError):
        return [f"{name}: the completion record does not parse"]
    problems = []
    if set(listed) != {f"{name}.{suffix}" for suffix in OBJECTS} or len(lines) != len(OBJECTS):
        problems.append(f"{name}: the record lists {sorted(listed)}")
    for object_name, (size, digest) in listed.items():
        if objects.get(object_name) != size:
            problems.append(f"{object_name}: size {objects.get(object_name)}, recorded {size}")
        elif double.sha256(object_name, directory) != digest:
            problems.append(f"{object_name}: digest differs from the record")
    return problems


def complete_sets(double: Double, directory: str = INCOMING) -> set[str]:
    names = set_names(double, directory)
    return {name for name in names if not completeness_problems(double, name, directory)}


@dataclass
class SetContents:
    name: str
    application: bytes
    keycloak: bytes
    roles: bytes
    manifest: dict[str, Any]


def open_set(double: Double, name: str, identity: str) -> SetContents:
    parts = {}
    for suffix in OBJECTS:
        result = double.decrypt(f"{name}.{suffix}", identity)
        assert result.returncode == 0, f"{name}.{suffix}: {result.stderr!r}"
        parts[suffix] = result.stdout
    return SetContents(
        name=name,
        application=parts["application.dump.age"],
        keycloak=parts["keycloak.dump.age"],
        roles=parts["roles.sql.age"],
        manifest=json.loads(parts["manifest.json.age"].decode("utf-8")),
    )


# Runs ---------------------------------------------------------------------------------------


@dataclass
class RunResult:
    code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


# Every process of a container, as "<pid> <command line>", read from /proc (no procps in it).
PROCESSES = (
    r'for d in /proc/[0-9]*; do printf "%s %s\n" "${d#/proc/}" '
    r'"$(tr "\0" " " < "$d/cmdline")"; done 2>/dev/null'
)
# The run directory backup makes for its agent socket and known_hosts file, in its container.
RUN_DIRS = "/tmp/eko-backup."  # noqa: S108 - a path inside the backup container, never opened here


def processes(container: str) -> list[tuple[int, str]]:
    out = docker("exec", "-u", "0", container, "sh", "-c", PROCESSES).stdout
    listed = (line.split(" ", 1) for line in out.splitlines() if line.strip())
    return [(int(pid), command.strip()) for pid, command in (p for p in listed if len(p) == 2)]


def run_leftovers(container: str) -> list[str]:
    """What a finished run must not leave in a long-running container: an ssh-agent (it holds
    the destination credential), a psql or dump tool, or a run directory under /tmp."""
    left = [
        command
        for _, command in processes(container)
        if re.search(r"\b(ssh-agent|psql|pg_dump|pg_dumpall|age|curl|sftp)\b", command)
        or "eko-backup run" in command
    ]
    listing = docker(
        "exec", "-u", "0", container, "sh", "-c", f"ls -d {RUN_DIRS}* 2>/dev/null; true"
    )
    return left + listing.stdout.split()


class ExecRun:
    """`eko-backup run` started with `docker compose exec` in the long-running scheduler
    container, as an operator might, so what the run leaves behind stays observable."""

    def __init__(self, composition: Composition, env: dict[str, str] | None = None) -> None:
        options = [
            item for name, value in (env or {}).items() for item in ("-e", f"{name}={value}")
        ]
        self._process = subprocess.Popen(
            [*composition.base_args(), "exec", "-T", *options, "backup", *schedule_command()],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def running(self) -> bool:
        return self._process.poll() is None

    def wait(self, timeout: float | None = None) -> RunResult:
        stdout, stderr = self._process.communicate(timeout=timeout or RUN_TIMEOUT_SECONDS)
        return RunResult(self._process.returncode, stdout, stderr)


class BackupRun:
    """One one-off container of the `backup` service, started in the background."""

    def __init__(self, composition: Composition, arguments: list[str]) -> None:
        self.container_name = arguments[arguments.index("--name") + 1]
        self._process = subprocess.Popen(
            [*composition.base_args(), *arguments],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.started_at = time.monotonic()

    def running(self) -> bool:
        return self._process.poll() is None

    def wait(self, timeout: float | None = None) -> RunResult:
        try:
            stdout, stderr = self._process.communicate(timeout=timeout or RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as expired:
            docker("rm", "-f", self.container_name, check=False)
            self._process.kill()
            stdout, stderr = self._process.communicate(timeout=60)
            message = f"backup run still running after its timeout: {stderr[-2000:]}"
            raise AssertionError(message) from expired
        return RunResult(self._process.returncode, stdout, stderr)

    def exited_at_once(self) -> tuple[RunResult, float]:
        result = self.wait()
        return result, time.monotonic()


@dataclass
class BackupLab:
    lab: Lab
    double: Double
    identity: str
    recipient: str
    monitor: PsqlSession
    keycloak_monitor: PsqlSession
    images: dict[str, str] = field(default_factory=dict)

    @property
    def composition(self) -> Composition:
        return self.lab.composition

    def run_arguments(
        self,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        name: str | None = None,
        remove: bool = True,
        volumes: tuple[str, ...] = (),
    ) -> list[str]:
        """`run` arguments; `command` None means the schedule file's command (K-01's entry)."""
        options = ["run", "--no-deps", "-T", "--name", name or f"bkp-{uuid.uuid4().hex[:10]}"]
        if remove:
            options.append("--rm")
        for variable, value in (env or {}).items():
            options += ["-e", f"{variable}={value}"]
        for volume in volumes:
            options += ["-v", volume]
        return [*options, "backup", *(schedule_command() if command is None else command)]

    def start_run(self, **kwargs: Any) -> BackupRun:
        return BackupRun(self.composition, self.run_arguments(**kwargs))

    def run(self, **kwargs: Any) -> RunResult:
        return self.start_run(**kwargs).wait()

    def backup_image(self) -> str:
        """The shipped `backup` image the composition built."""
        # Compose names a built image <project>-<service>; `config --images` lists dependencies too.
        image = f"{self.composition.project}-backup"
        docker("image", "inspect", image)
        return image

    def with_backup_image(self, image: str) -> Composition:
        """The composition with `backup` running another image: for planted contrasts only."""
        override = self.lab.workdir / f"backup-{uuid.uuid4().hex[:8]}.yaml"
        override.write_text(
            f"services:\n  backup:\n    image: {image}\n    pull_policy: never\n", encoding="utf-8"
        )
        return Composition(self.composition.project, self.composition.env_file, [override])

    def scheduler(self) -> str:
        """The `backup` service's own long-running container (its scheduler); its name."""
        self.composition.compose("up", "-d", "--no-deps", "backup")
        # The service container by its Compose name; one-off run containers share the service.
        return f"{self.composition.project}-backup-1"

    def stop_scheduler(self) -> None:
        self.composition.compose("rm", "-s", "-f", "backup", check=False)

    def scheduler_running(self) -> bool:
        # The service's own container only: `compose ps` also lists one-off `run` containers, so
        # a test failing while its run still ran errored at teardown as "scheduler still running".
        listed = docker(
            "ps", "-q",
            "--filter", f"label=com.docker.compose.project={self.composition.project}",
            "--filter", "label=com.docker.compose.service=backup",
            "--filter", "label=com.docker.compose.oneoff=False",
        )  # fmt: skip
        return bool(listed.stdout.split())

    def interrupt_exec_run(self, container: str) -> None:
        """SIGTERM to the `eko-backup run` wrapper of an exec'd run, as `docker stop` sends it."""
        targets = [
            pid for pid, command in processes(container) if command.endswith("eko-backup run")
        ]
        assert len(targets) == 1, processes(container)
        docker("exec", "-u", "0", container, "kill", "-TERM", str(targets[0]))

    def on_demand(self, env: dict[str, str] | None = None) -> BackupRun:
        """The command documented in backup/README.md, as written, with `-T` for no terminal."""
        words = on_demand_arguments()
        assert words[0] == "run", words
        extra = ["-T", "--name", f"bkp-{uuid.uuid4().hex[:10]}"]
        for variable, value in (env or {}).items():
            extra += ["-e", f"{variable}={value}"]
        return BackupRun(self.composition, [words[0], *extra, *words[1:]])

    # Database state -----------------------------------------------------------------------

    def sql(self, statement: str, **variables: str) -> list[list[str]]:
        return self.monitor.query(statement, **variables)

    def keycloak_sql(self, statement: str, **variables: str) -> list[list[str]]:
        return self.keycloak_monitor.query(statement, **variables)

    def at_probe_head(self) -> None:
        self.lab.reset()
        code, logs = self.lab.run_migrate(self.lab.variant("backup_probe", PROBE_VARIANT))
        assert code == 0, logs

    def plant_row(self, value: str) -> None:
        """Markers travel as hex: no value with diacritics is spliced into a statement."""
        self.sql(
            "INSERT INTO eko_test_backup_probe (value) "
            "VALUES (convert_from(decode(:'h', 'hex'), 'UTF8'))",
            h=value.encode("utf-8").hex(),
        )

    def plant_keycloak_user(self, value: str) -> str:
        """A Keycloak user of the master realm whose first name is `value`."""
        user_id = str(uuid.uuid4())
        self.keycloak_sql(
            "INSERT INTO user_entity (id, username, first_name, realm_id, email_constraint, "
            "enabled, email_verified, not_before, created_timestamp) "
            "SELECT :'id', lower(convert_from(decode(:'h', 'hex'), 'UTF8')), "
            "convert_from(decode(:'h', 'hex'), 'UTF8'), id, :'id', "
            "true, false, 0, 0 FROM realm WHERE name = 'master'",
            id=user_id,
            h=value.encode("utf-8").hex(),
        )
        return user_id

    def pad(self, rows: int) -> None:
        """Rows that make the application dump take seconds; random, so they do not compress."""
        self.sql(
            "INSERT INTO eko_test_backup_probe (value) SELECT string_agg(md5(random()::text), '') "
            "FROM generate_series(1, CAST(:'n' AS integer)) AS r(i), "
            "generate_series(1, 16) AS c(j) GROUP BY i",
            n=str(rows),
        )

    def backup_sessions(self) -> list[tuple[str, str, str]]:
        """(database, application name, wait event type) of every eko_backup session."""
        rows = self.sql(
            "SELECT coalesce(datname, ''), coalesce(application_name, ''), "
            "coalesce(wait_event_type, '') FROM pg_stat_activity WHERE usename = 'eko_backup'"
        )
        return [(r[0], r[1], r[2]) for r in rows]

    def dump_sessions(self) -> list[tuple[str, str, str]]:
        return [s for s in self.backup_sessions() if s[1].startswith("eko-backup-dump-")]

    def connections_logged(self) -> int:
        """Connections of eko_backup the server has authorised so far (log_connections)."""
        logs = self.composition.compose("logs", "--no-color", "postgres", check=False)
        text = logs.stdout + logs.stderr
        return len(re.findall(r"connection authorized: user=eko_backup\b", text))

    def wait_until(
        self, condition: str, predicate: Callable[[], bool], timeout: float = 60
    ) -> None:
        self.lab.wait_until(condition, predicate, timeout)

    @contextmanager
    def advisory_lock_held(
        self, statement: str = LOCK_BIGINT, **keys: str
    ) -> Iterator[PsqlSession]:
        """H0: a test session holding the advisory lock and no other lock."""
        holder = PsqlSession(self.composition, name="eko-test-h0")
        try:
            holder.query(statement, **(keys or {"k": str(KEY)}))
            yield holder
        finally:
            holder.close()

    @contextmanager
    def keycloak_table_held(self) -> Iterator[PsqlSession]:
        """H1: a test session holding ACCESS EXCLUSIVE on a Keycloak table unused after start."""
        holder = PsqlSession(self.composition, name="eko-test-h1", database="keycloak")
        try:
            holder.query("BEGIN")
            holder.query(f"LOCK TABLE {H1_TABLE} IN ACCESS EXCLUSIVE MODE")
            yield holder
        finally:
            holder.close()

    def waiting_at_h1(self) -> bool:
        return any(
            s == ("keycloak", "eko-backup-dump-keycloak", "Lock") for s in self.backup_sessions()
        )

    # Restore, outside the composition -----------------------------------------------------

    @contextmanager
    def empty_server(self) -> Iterator[str]:
        """An empty server from the pinned postgres image, on no network."""
        password = "synthetic-" + secrets.token_hex(12)
        container = docker(
            "run", "-d", "--network", "none", "-e", f"POSTGRES_PASSWORD={password}",
            "postgres:18.6-trixie",
        ).stdout.strip()  # fmt: skip
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                ready = docker("exec", container, "pg_isready", "-h", "127.0.0.1", check=False)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            yield container
        finally:
            docker("rm", "-f", container, check=False)


def restore_psql(container: str, database: str, sql: str, **variables: str) -> list[list[str]]:
    """A query on the restored server; values reach it as psql variables, never spliced."""
    lines = []
    for name, value in variables.items():
        assert re.fullmatch(r"[A-Za-z0-9_.:-]+", value), value
        lines.append(f"\\set {name} {value}")
    script = "\n".join([*lines, sql.strip().rstrip(";") + ";"]) + "\n"
    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database, "-AtXq",
         "-F", "\t", "-v", "ON_ERROR_STOP=1", "-f", "-"],
        input=script.encode(), capture_output=True, timeout=300,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-2000:]
    lines = result.stdout.decode().splitlines()
    return [line.split("\t") for line in lines if line]


def restore_set(container: str, contents: SetContents) -> None:
    """The roles, then both dumps with stop-on-error, each creating its database."""
    roles = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "postgres", "-X",
         "-f", "-"],
        input=contents.roles, capture_output=True, timeout=300,
    )  # fmt: skip
    errors = [line for line in roles.stderr.decode().splitlines() if "ERROR" in line]
    # The bootstrap superuser exists in every server; pg_dumpall writes its CREATE ROLE anyway.
    assert all('role "postgres" already exists' in line for line in errors), errors
    for dump in (contents.application, contents.keycloak):
        restored = subprocess.run(
            ["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "--create",
             "--exit-on-error", "-d", "postgres"],
            input=dump, capture_output=True, timeout=600,
        )  # fmt: skip
        assert restored.returncode == 0, restored.stderr.decode(errors="replace")[-2000:]


# Scanning for parts of a set at rest ---------------------------------------------------------


def tar_members(stream: bytes) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(fileobj=io.BytesIO(stream), mode="r|*") as archive:
        for member in archive:
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is not None:
                    yield member.name, extracted.read()


def container_files(container: str) -> Iterator[tuple[str, bytes]]:
    """Every regular file of a container (running or stopped), tmpfs and /dev/shm included when
    it runs, and of every volume mounted into it."""
    state = json.loads(docker("inspect", "-f", "{{json .State}}", container).stdout)
    if state["Running"]:
        archive = subprocess.run(
            ["docker", "exec", "-u", "0", container, "tar", "-C", "/", "-cf", "-",
             "--exclude=./proc", "--exclude=./sys", "--exclude=./dev/pts", "."],
            capture_output=True, timeout=600,
        ).stdout  # fmt: skip
        yield from tar_members(archive)
        return
    exported = subprocess.run(["docker", "export", container], capture_output=True, timeout=600)
    yield from tar_members(exported.stdout)
    mounts = json.loads(docker("inspect", "-f", "{{json .Mounts}}", container).stdout)
    for mount in mounts:
        if mount.get("Type") == "volume":
            yield from volume_files(mount["Name"])


def volume_files(volume: str) -> Iterator[tuple[str, bytes]]:
    archive = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-u", "0", "-v", f"{volume}:/v:ro",
         "--entrypoint", "tar", "postgres:18.6-trixie", "-C", "/v", "-cf", "-", "."],
        capture_output=True, timeout=600,
    ).stdout  # fmt: skip
    for name, data in tar_members(archive):
        yield f"{volume}:{name}", data


def project_volumes(composition: Composition) -> list[str]:
    listed = docker(
        "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={composition.project}"
    ).stdout.split()
    return sorted(listed)


def files_holding(files: Iterator[tuple[str, bytes]], needles: list[bytes]) -> list[str]:
    return sorted({name for name, data in files for needle in needles if needle in data})


def files_with_digest(files: Iterator[tuple[str, bytes]], digests: set[str]) -> list[str]:
    return sorted({name for name, data in files if hashlib.sha256(data).hexdigest() in digests})


# The lab itself -----------------------------------------------------------------------------


def unique_marker(label: str) -> str:
    return f"marker-{label}-{secrets.token_hex(5)}-{DIACRITICS}"


class SessionSampler:
    """Samples eko_backup's sessions every 20 ms; the maximum is a record, not the proof."""

    def __init__(self, composition: Composition) -> None:
        self._session = PsqlSession(composition, name="eko-test-sampler")
        self._stop = threading.Event()
        self.maximum = 0
        self.samples = 0
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self._stop.is_set():
            [[count]] = self._session.query(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = 'eko_backup'"
            )
            self.maximum = max(self.maximum, int(count))
            self.samples += 1
            time.sleep(0.02)

    def __enter__(self) -> "SessionSampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=30)
        self._session.close()


class RowWriter:
    """Inserts one application row every 20 ms until stopped (writes during a dump)."""

    def __init__(self, composition: Composition) -> None:
        self._session = PsqlSession(composition, name="eko-test-writer")
        self._stop = threading.Event()
        self.written = 0
        self._thread = threading.Thread(target=self._write, daemon=True)

    def _write(self) -> None:
        while not self._stop.is_set():
            self._session.query("INSERT INTO eko_test_backup_probe (value) VALUES ('writer-row')")
            self.written += 1
            time.sleep(0.02)

    def __enter__(self) -> "RowWriter":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=30)
        self._session.close()


def start_double(project: str) -> Double:
    tag = f"localhost/eko-crm/backup-double:{project}"
    docker("build", "-q", "-t", tag, str(DOUBLE_CONTEXT), timeout=900)
    container = docker("run", "-d", "--name", f"{project}-double", tag).stdout.strip()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        probe = docker("exec", container, "test", "-s", "/keys/root.pub", check=False)
        if probe.returncode == 0:
            break
        time.sleep(0.5)
    host_key = docker("exec", container, "cat", "/etc/ssh/ssh_host_ed25519_key.pub").stdout
    key_file = subprocess.run(
        ["docker", "exec", container, "cat", "/keys/eko-backup"], capture_output=True, check=True
    ).stdout
    alias = f"dest-{secrets.token_hex(4)}"
    return Double(container, alias, host_key.strip(), base64.b64encode(key_file).decode())


def backup_environment(double: Double, recipient: str) -> dict[str, str]:
    """The four values the lab writes into the composition's environment file (test-only)."""
    values = (
        f"sftp://eko-backup@{double.alias}:22{INCOMING}",
        double.host_key,
        double.credential,
        recipient,
    )
    return dict(zip(BACKUP_VARIABLES, values, strict=True))


def backup_lab_session(tmp_path_factory: pytest.TempPathFactory) -> Iterator[BackupLab]:
    composition = new_composition(tmp_path_factory, "bkp")
    double: Double | None = None
    monitors: list[PsqlSession] = []
    started: BackupLab | None = None
    lab: Lab | None = None
    try:
        double = start_double(composition.project)
        identity, recipient = double.new_identity()
        values = read_env(composition.env_file)
        values.update(backup_environment(double, recipient))
        write_env_file(composition.env_file, values)
        up = composition.compose(
            "up", "--build", "--wait", "--wait-timeout", str(UP_TIMEOUT_SECONDS),
            "backend", "keycloak",
            check=False, timeout=UP_TIMEOUT_SECONDS + 300,
        )  # fmt: skip
        if up.returncode != 0:
            logs = composition.compose("logs", "--tail", "40", check=False).stdout
            raise AssertionError(f"up exited {up.returncode}\n{up.stderr[-3000:]}\n{logs[-6000:]}")
        composition.compose("build", "backup", timeout=900)
        docker(
            "network", "connect", "--alias", double.alias, f"{composition.project}_default",
            double.container,
        )  # fmt: skip
        monitor = PsqlSession(composition, name="eko-test-monitor")
        monitors.append(monitor)
        keycloak_monitor = PsqlSession(composition, name="eko-test-kc-monitor", database="keycloak")
        monitors.append(keycloak_monitor)
        monitor.query("ALTER SYSTEM SET log_connections = 'on'")
        monitor.query("SELECT pg_reload_conf()")
        shipped = composition.inspect("backend")["Config"]["Image"]
        workdir = tmp_path_factory.mktemp("bkp-work")
        lab = Lab(composition, workdir, shipped, "", monitor)
        started = BackupLab(lab, double, identity, recipient, monitor, keycloak_monitor)
        yield started
    finally:
        for session in monitors:
            session.close()
        if lab is not None:
            for tag in lab.images.values():
                docker("rmi", "-f", tag, check=False)
        # The planted schedule images of K-05's contrasts, and this lab's double image (QA,
        # EKO-1-14: both outlived every session before).
        if started is not None:
            for tag in started.images.values():
                docker("rmi", "-f", tag, check=False)
        if double is not None:
            docker("rm", "-f", double.container, check=False)
        docker("rmi", "-f", f"localhost/eko-crm/backup-double:{composition.project}", check=False)
        composition.down()
