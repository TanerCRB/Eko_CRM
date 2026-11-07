"""K-03 (ADR-0004-C15, set contents): one set at the destination is unreadable without a private
key the test holds outside the composition. Decrypted, it holds the application dump, then the
Keycloak dump, the roles without passwords and a manifest whose time is the application snapshot's
start and whose counts are the dump's; both dumps restore.

The set is produced once per module: backup is held at H0, the lock released at a server-clock
moment, and while the (padded, so slow) application dump runs the test writes one application
row and one Keycloak user. That row must be absent from the application dump and the user present
in the Keycloak dump: the order evidence.
"""

import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from tests.runtime.backup_lab import (
    KEY,
    LATER_VARIANT,
    OBJECTS,
    UNLOCK_BIGINT,
    BackupLab,
    Double,
    SetContents,
    backup_environment,
    complete_sets,
    container_files,
    failure_fields,
    failure_lines,
    files_holding,
    open_set,
    restore_psql,
    restore_set,
    set_names,
    unique_marker,
)
from tests.runtime.backup_lab import RowWriter as Writer
from tests.runtime.conftest import Composition, new_composition, read_env, write_env
from tests.runtime.lab import docker
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

PAD_ROWS = 150_000
SERVER_UTC = "to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"
BACKUP_POINT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z")
APPLICATION_TABLES = (
    "SELECT n.nspname || '.' || c.relname FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r', 'p') "
    "AND c.relpersistence <> 't' AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
    "AND n.nspname NOT LIKE 'pg_toast%'"
)
PREVIOUS_INIT = Path(__file__).parent / "fixtures" / "previous_init_content.sh"
# An age identity: the prefix and 58 characters of the Bech32 alphabet. The bare prefix also
# occurs in the age binaries themselves, which hold no key.
AGE_IDENTITY = re.compile(rb"AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}")
PLANTED = "/var/lib/postgresql/eko-test-planted-identity"
# The restored server's counts of the same tables, by the manifest's definition.
COUNTS = (
    "SELECT coalesce(json_object_agg(t, (xpath('/row/n/text()', query_to_xml("
    "format('SELECT count(*) AS n FROM %s', t), false, true, '')))[1]::text::bigint), '{}') "
    "FROM (SELECT n.nspname || '.' || c.relname FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r', 'p') "
    "AND c.relpersistence <> 't' AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
    "AND n.nspname NOT LIKE 'pg_toast%') AS a(t)"
)


@dataclass
class Produced:
    name: str
    contents: SetContents
    markers: dict[str, str]
    released_at: datetime
    window_at: datetime
    revision: str
    tables: set[str]
    written: int


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def produced(backup_lab: BackupLab) -> Produced:
    backup_lab.at_probe_head()
    markers = {
        label: unique_marker(label) for label in ("row", "user", "row-window", "user-window")
    }
    backup_lab.plant_row(markers["row"])
    backup_lab.plant_keycloak_user(markers["user"])
    backup_lab.pad(PAD_ROWS)
    before = set_names(backup_lab.double)
    with backup_lab.advisory_lock_held() as holder:
        run = backup_lab.start_run()
        backup_lab.wait_until(
            "backup waits for the advisory lock",
            lambda: ("eko", "eko-backup-control", "Lock") in backup_lab.backup_sessions(),
        )
        [[released]] = holder.query(f"SELECT {SERVER_UTC}")
        holder.query(UNLOCK_BIGINT, k=str(KEY))
    with Writer(backup_lab.composition) as writer:
        backup_lab.wait_until(
            "the application dump runs",
            lambda: any(
                s[1] == "eko-backup-dump-application" for s in backup_lab.backup_sessions()
            ),
        )
        [[window_at]] = backup_lab.sql(f"SELECT {SERVER_UTC}")
        backup_lab.plant_row(markers["row-window"])
        backup_lab.plant_keycloak_user(markers["user-window"])
        names = {s[1] for s in backup_lab.backup_sessions()}
        assert "eko-backup-dump-application" in names, f"window missed: {names}"
        assert "eko-backup-dump-keycloak" not in names, f"window missed: {names}"
        result = run.wait()
        written = writer.written
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    [[revision]] = backup_lab.sql("SELECT version_num FROM alembic_version")
    tables = {row[0] for row in backup_lab.sql(APPLICATION_TABLES)}
    return Produced(
        name=name,
        contents=open_set(backup_lab.double, name, backup_lab.identity),
        markers=markers,
        released_at=utc(released),
        window_at=utc(window_at),
        revision=revision,
        tables=tables,
        written=written,
    )


def marker_bytes(produced: Produced, *labels: str) -> list[bytes]:
    return [produced.markers[label].encode("utf-8") for label in labels]


# Point 1 and its contrast: unreadable bytes, and a scanner that sees the markers --------------


def test_k03_1_the_bytes_at_the_destination_hold_no_marker(
    backup_lab: BackupLab, produced: Produced
) -> None:
    stored = [(o, backup_lab.double.read(f"{produced.name}.{o}")) for o in OBJECTS]
    stored.append(("complete", backup_lab.double.read(f"{produced.name}.complete")))
    assert files_holding(iter(stored), marker_bytes(produced, *produced.markers)) == []


def test_k03_1_contrast_the_scanner_finds_the_markers_in_the_decrypted_dumps(
    produced: Produced,
) -> None:
    decrypted = [("application", produced.contents.application)]
    decrypted.append(("keycloak", produced.contents.keycloak))
    assert files_holding(iter(decrypted), marker_bytes(produced, "row")) == ["application"]
    assert files_holding(iter(decrypted), marker_bytes(produced, "user")) == ["keycloak"]


# Point 2 and its contrast: the configured key decrypts, another does not --------------------


def test_k03_2_the_set_decrypts_with_the_test_key(
    backup_lab: BackupLab, produced: Produced
) -> None:
    assert complete_sets(backup_lab.double) >= {produced.name}
    for suffix in OBJECTS:
        header = backup_lab.double.read(f"{produced.name}.{suffix}")[:200]
        assert header.startswith(b"age-encryption.org/v1\n-> X25519 ")
        assert header.count(b"\n-> X25519 ") == 1, "exactly one X25519 recipient"
        assert b"\n-> scrypt " not in header, "no passphrase recipient"


def test_k03_2_contrast_a_second_key_does_not_decrypt(
    backup_lab: BackupLab, produced: Produced
) -> None:
    other, _ = backup_lab.double.new_identity()
    for suffix in OBJECTS:
        assert backup_lab.double.decrypt(f"{produced.name}.{suffix}", other).returncode != 0


# Point 3: order evidence ---------------------------------------------------------------------


def test_k03_3_application_snapshot_before_the_keycloak_dump(produced: Produced) -> None:
    assert marker_bytes(produced, "row")[0] in produced.contents.application
    assert marker_bytes(produced, "row-window")[0] not in produced.contents.application
    assert marker_bytes(produced, "user-window")[0] in produced.contents.keycloak


# Point 4: roles without passwords ------------------------------------------------------------


def test_k03_4_roles_without_passwords(backup_lab: BackupLab, produced: Produced) -> None:
    roles = produced.contents.roles.decode("utf-8")
    for role in ("eko_app", "eko_keycloak", "eko_backup"):
        assert f"CREATE ROLE {role};" in roles
    assert "PASSWORD" not in roles.upper()
    assert "SCRAM-SHA-256$" not in roles
    passwords = [v for k, v in backup_lab.composition.env.items() if "PASSWORD" in k]
    assert passwords and not [p for p in passwords if p in roles]


# Point 5: the manifest ------------------------------------------------------------------------


def test_k03_5_manifest_revision_images_and_counts(
    backup_lab: BackupLab, produced: Produced
) -> None:
    manifest = produced.contents.manifest
    composition = backup_lab.composition
    assert manifest["format"] == "eko-backup-manifest/1"
    assert manifest["set"] == produced.name
    assert manifest["alembic_revision"] == produced.revision == "t_backup_probe"
    assert manifest["images"] == {
        "backend": composition.inspect("backend")["Config"]["Image"],
        "keycloak": composition.inspect("keycloak")["Config"]["Image"],
        "postgres": composition.inspect("postgres")["Config"]["Image"],
    }
    assert set(manifest["row_counts"]) == produced.tables
    assert manifest["row_counts"]["public.eko_test_backup_empty"] == 0
    assert manifest["row_counts"]["public.alembic_version"] == 1


# Point 6: the backup point --------------------------------------------------------------------


def test_k03_6_backup_point_is_the_snapshot_start_on_the_server_clock(produced: Produced) -> None:
    point = produced.contents.manifest["backup_point"]
    assert BACKUP_POINT.fullmatch(point), point
    assert produced.released_at <= utc(point) < produced.window_at
    assert produced.name.startswith("eko-" + point.replace("-", "").replace(":", ""))


# Point 7: restore, counts and markers ---------------------------------------------------------


def test_k03_7_both_dumps_restore_with_counts_and_markers(
    backup_lab: BackupLab, produced: Produced
) -> None:
    assert produced.written > 0, "no application row was written during the run"
    with backup_lab.empty_server() as server:
        restore_set(server, produced.contents)
        [[restored]] = restore_psql(server, "eko", COUNTS)
        assert json.loads(restored) == produced.contents.manifest["row_counts"]
        [[locale]] = restore_psql(
            server, "eko", "SELECT datlocprovider::text || ' ' || datlocale FROM pg_database "
            "WHERE datname = 'eko'",
        )  # fmt: skip
        assert locale == "i pl-PL"
        [[found]] = restore_psql(
            server, "eko", "SELECT count(*) FROM eko_test_backup_probe "
            "WHERE value = convert_from(decode(:'h', 'hex'), 'UTF8')",
            h=produced.markers["row"].encode("utf-8").hex(),
        )  # fmt: skip
        assert found == "1"
        [[found]] = restore_psql(
            server, "keycloak", "SELECT count(*) FROM user_entity "
            "WHERE first_name = convert_from(decode(:'h', 'hex'), 'UTF8')",
            h=produced.markers["user"].encode("utf-8").hex(),
        )  # fmt: skip
        assert found == "1"


# Point 8 and its contrast: a table of a later revision, with no grant -------------------------


def test_k03_8_a_later_revisions_table_is_in_the_next_set_with_no_grant(
    backup_lab: BackupLab,
) -> None:
    revision = REPO_ROOT / "backend" / "tests" / "runtime" / "revisions" / "t_backup_later.py"
    statements = [
        line for line in revision.read_text(encoding="utf-8").splitlines() if "op." in line
    ]
    assert statements and not [line for line in statements if "GRANT" in line.upper()]
    backup_lab.at_probe_head()
    code, logs = backup_lab.lab.run_migrate(backup_lab.lab.variant("backup_later", LATER_VARIANT))
    assert code == 0, logs
    before = set_names(backup_lab.double)
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    contents = open_set(backup_lab.double, name, backup_lab.identity)
    assert contents.manifest["row_counts"]["public.eko_test_backup_later"] == 1
    assert b"later-row" in contents.application


def test_k03_8_contrast_without_read_privilege_on_the_later_table_the_run_fails(
    backup_lab: BackupLab,
) -> None:
    backup_lab.at_probe_head()
    code, logs = backup_lab.lab.run_migrate(backup_lab.lab.variant("backup_later", LATER_VARIANT))
    assert code == 0, logs
    # With explicit grants (B-01 A) the later table's privilege is revoked directly (A-03).
    backup_lab.sql("REVOKE SELECT ON eko_test_backup_later FROM eko_backup")
    try:
        result = backup_lab.run()
    finally:
        backup_lab.sql("GRANT SELECT ON eko_test_backup_later TO eko_backup")
    assert result.code != 0
    [line] = failure_lines(result.stderr)
    assert failure_fields(line)["reason"] == "dump-application", line


# Point 9: Keycloak's own tables -----------------------------------------------------------------


def test_k03_9_keycloak_tables_are_in_the_keycloak_dump(
    backup_lab: BackupLab, produced: Produced
) -> None:
    rows = backup_lab.keycloak_sql("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    tables = {row[0] for row in rows}
    assert {"user_entity", "realm", "client"} <= tables
    listed = subprocess.run(
        [*backup_lab.composition.base_args(), "exec", "-T", "postgres", "pg_restore", "-l"],
        cwd=REPO_ROOT, input=produced.contents.keycloak, capture_output=True, timeout=300,
    )  # fmt: skip
    assert listed.returncode == 0, listed.stderr
    dumped = set(re.findall(r" TABLE public (\S+) ", listed.stdout.decode()))
    assert tables <= dumped


# B-01 (fix round 1): a run that drops --no-role-passwords cannot read pg_authid, so it fails
# instead of putting verifiers in a set. A planted contrast: the shipped script, one flag removed.


def test_b01_a_roles_dump_with_passwords_fails_with_42501(
    backup_lab: BackupLab, tmp_path: Path
) -> None:
    backup_lab.at_probe_head()
    base = backup_lab.backup_image()
    script = (REPO_ROOT / "backup" / "eko-backup").read_text(encoding="utf-8")
    assert script.count(" --no-role-passwords") == 1
    (tmp_path / "eko-backup").write_text(
        script.replace(" --no-role-passwords", ""), encoding="utf-8", newline="\n"
    )
    (tmp_path / "Dockerfile").write_text(
        f"FROM {base}\nCOPY --chmod=0755 eko-backup /usr/local/bin/eko-backup\n",
        encoding="utf-8",
    )
    tag = f"localhost/eko-crm/backup-planted:{tmp_path.name.lower()}"
    docker("build", "-q", "-t", tag, str(tmp_path), timeout=600)
    backup_lab.images[tag] = tag
    planted = backup_lab.with_backup_image(tag)
    before = set_names(backup_lab.double)
    result = planted.compose(
        "run", "--rm", "--no-deps", "-T", "backup", "eko-backup", "run", check=False, timeout=900
    )
    assert result.returncode != 0
    [line] = failure_lines(result.stderr)
    fields = failure_fields(line)
    assert (fields["reason"], fields.get("sqlstate")) == ("dump-roles", "42501"), line
    assert not (set_names(backup_lab.double) - before) & complete_sets(backup_lab.double)


# Static and image check: no age identity in the image, the container or an environment file ---


def packaged_age_files(files: list[tuple[str, bytes]]) -> dict[str, str]:
    """Path -> MD5 of the age package's own files, from dpkg's record in the same filesystem."""
    for name, data in files:
        if name.lstrip("./") == "var/lib/dpkg/info/age.md5sums":
            pairs = (line.split(maxsplit=1) for line in data.decode().splitlines() if line)
            return {path: digest for digest, path in pairs}
    return {}


def scan_for_identity(files: list[tuple[str, bytes]]) -> list[str]:
    """Files holding an age identity. The age binaries carry the format's published test
    identity; they pass only while their bytes are exactly the package's (dpkg's MD5)."""
    packaged = packaged_age_files(files)
    found = set()
    for name, data in files:
        path = name.lstrip("./")
        digest = hashlib.md5(data, usedforsecurity=False).hexdigest()
        if AGE_IDENTITY.search(data) and packaged.get(path) != digest:
            found.add(name)
    return sorted(found)


def test_k03_no_age_identity_in_the_image_the_container_or_the_environment_file(
    backup_lab: BackupLab,
) -> None:
    composition = backup_lab.composition
    composition.compose("up", "-d", "--no-deps", "backup")
    container = composition.container_id("backup")
    image = composition.inspect("backup")["Config"]["Image"]
    created = docker("create", image).stdout.strip()
    try:
        assert scan_for_identity(list(container_files(created))) == []
    finally:
        docker("rm", "-f", created, check=False)
    assert scan_for_identity(list(container_files(container))) == []
    assert not AGE_IDENTITY.search(composition.env_file.read_bytes())


def test_k03_contrast_a_planted_identity_is_found(backup_lab: BackupLab) -> None:
    composition = backup_lab.composition
    composition.compose("up", "-d", "--no-deps", "backup")
    container = composition.container_id("backup")
    identity = backup_lab.double.run("cat", backup_lab.identity).stdout
    subprocess.run(
        ["docker", "exec", "-i", container, "sh", "-c", f"cat > {PLANTED}"],
        input=identity, check=True, capture_output=True,
    )  # fmt: skip
    try:
        assert scan_for_identity(list(container_files(container))) != []
    finally:
        docker(
            "exec",
            container,
            "rm",
            "-f",
            PLANTED,
            check=False,
        )


# Existing volume (DoD item 13): the previous init content, then the documented operator step ---


def operator_step(database: str) -> str:
    """The documented existing-volume statements for one database (backup/README.md)."""
    from tests.runtime.backup_lab import documented

    return documented(f"existing-volume-step-{database}")


def run_operator_step(composition: Composition) -> None:
    for database in ("eko", "keycloak"):
        composition.compose(
            "exec", "-T", "postgres", "psql", "-X", "-U", "postgres", "-d", database,
            "-v", "ON_ERROR_STOP=1", stdin=operator_step(database) + "\n",
        )  # fmt: skip


def verifier_readable(composition: Composition) -> bool:
    probe = composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-U", "eko_backup", "-d", "eko",
        "-c", "SELECT count(*) FROM pg_authid", check=False,
    )  # fmt: skip
    return probe.returncode == 0


def created_later_is_readable(composition: Composition, database: str, owner: str) -> bool:
    """A table the database's owner role creates now: can eko_backup read it? (QA, fix round 1:
    the operator step's default privileges must cover tables created after the step, which the
    run right after the step never sees.)"""
    table = f"eko_test_after_step_{uuid.uuid4().hex[:8]}"
    composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-U", "postgres", "-d", database,
        "-v", "ON_ERROR_STOP=1", "-c", f"SET ROLE {owner}; CREATE TABLE {table} (id int)",
    )  # fmt: skip
    probe = composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-U", "eko_backup", "-d", database,
        "-v", "ON_ERROR_STOP=1", "-c", f"SELECT count(*) FROM {table}", check=False,  # noqa: S608 - a generated hex name
    )  # fmt: skip
    composition.compose(
        "exec", "-T", "postgres", "psql", "-X", "-U", "postgres", "-d", database,
        "-c", f"DROP TABLE {table}",
    )  # fmt: skip
    return probe.returncode == 0


def test_k03_existing_volume_needs_the_documented_operator_step(
    backup_lab: BackupLab, tmp_path_factory: pytest.TempPathFactory
) -> None:
    old = new_composition(tmp_path_factory, "bkpold")
    values = read_env(old.env_file)
    values.update(backup_environment(backup_lab.double, backup_lab.recipient))
    values["BACKEND_IMAGE_TAG"] = backup_lab.composition.env["BACKEND_IMAGE_TAG"]
    write_env(old.env_file, values)
    override = tmp_path_factory.mktemp("bkpold-override") / "previous-init.yaml"
    content = PREVIOUS_INIT.read_text(encoding="utf-8")
    indented = "".join(f"      {line}\n" for line in content.splitlines())
    override.write_text(f"configs:\n  postgres-init:\n    content: |\n{indented}", encoding="utf-8")
    previous = Composition(old.project, old.env_file, [override])
    double: Double = backup_lab.double
    connected = False
    try:
        previous.compose("up", "-d", "--wait", "postgres", timeout=600)
        old.compose("run", "--rm", "--no-deps", "migrate", timeout=600)
        old.compose("up", "-d", "--wait", "postgres", timeout=600)
        network = f"{old.project}_default"
        docker("network", "connect", "--alias", double.alias, network, double.container)
        connected = True
        command = ["run", "--rm", "--no-deps", "-T", "backup", "eko-backup", "run"]
        refused = old.compose(*command, check=False, timeout=900)
        assert refused.returncode != 0
        [line] = failure_lines(refused.stderr)
        fields = failure_fields(line)
        assert (fields["reason"], fields.get("sqlstate")) == ("dump-application", "42501"), line
        # Contrast for the check after the step: before it, a table created now is unreadable.
        assert not created_later_is_readable(old, "eko", "eko_app")
        assert not created_later_is_readable(old, "keycloak", "eko_keycloak")
        assert "REVOKE pg_read_all_data FROM eko_backup;" in operator_step("eko")
        # The step also brings a volume first initialised by this task's earlier init content
        # (membership in pg_read_all_data) to the explicit grants.
        old.compose(
            "exec", "-T", "postgres", "psql", "-X", "-U", "postgres", "-d", "eko",
            "-c", "GRANT pg_read_all_data TO eko_backup",
        )  # fmt: skip
        assert verifier_readable(old)
        run_operator_step(old)
        run_operator_step(old)
        assert not verifier_readable(old)
        assert created_later_is_readable(old, "eko", "eko_app")
        assert created_later_is_readable(old, "keycloak", "eko_keycloak")
        before = set_names(double)
        accepted = old.compose(*command, check=False, timeout=900)
        assert accepted.returncode == 0, accepted.stderr
        assert len(set_names(double) - before) == 1
    finally:
        if connected:
            docker("network", "disconnect", f"{old.project}_default", double.container, check=False)
        old.down()


# Point 7, the mechanism: counts and dump inside the one exported snapshot (QA, EKO-1-14) -------
# The restored-count check cannot see counts read in the milliseconds just before the snapshot is
# taken: no test write lands there. The server's own statement log can: for one run, the control
# session's statements in order, with eko_backup's statements logged for that run only.

# The prefix is docs/operations/log-format.md's: `%m [%p] %e %q%u@%d %h ` (S-1, Issue #54).
LOGGED = re.compile(r"\[(?P<pid>[0-9]+)\] (?:\S+ )*?LOG:  statement: (?P<text>.*)$")


def logged_statements(backup_lab: BackupLab) -> list[tuple[str, str]]:
    logs = backup_lab.composition.compose("logs", "--no-color", "postgres", check=False)
    found = (LOGGED.search(line) for line in (logs.stdout + logs.stderr).splitlines())
    return [(m["pid"], m["text"].rstrip().rstrip(";")) for m in found if m]


def statement_logged_run(backup_lab: BackupLab) -> list[tuple[str, str]]:
    """One run with eko_backup's statements logged; the statements logged during it."""
    backup_lab.at_probe_head()
    already = len(logged_statements(backup_lab))
    backup_lab.sql("ALTER ROLE eko_backup SET log_statement = 'all'")
    try:
        result = backup_lab.run()
    finally:
        backup_lab.sql("ALTER ROLE eko_backup RESET log_statement")
    assert result.code == 0, result.stderr
    return logged_statements(backup_lab)[already:]


def test_k03_7_counts_and_dump_are_read_in_the_exported_snapshot(backup_lab: BackupLab) -> None:
    run = statement_logged_run(backup_lab)
    [control] = {pid for pid, text in run if text.startswith("SELECT pg_advisory_lock(")}
    texts = [text for pid, text in run if pid == control]
    lock = next(i for i, t in enumerate(texts) if t.startswith("SELECT pg_advisory_lock("))
    begin = next(i for i, t in enumerate(texts) if t.startswith("BEGIN ISOLATION LEVEL REPEATABLE"))
    commit = next(i for i, t in enumerate(texts) if i > begin and t == "COMMIT")
    counts = [i for i, t in enumerate(texts) if "count(" in t]
    # Lock first, then the transaction, whose first statement exports the snapshot.
    assert lock < begin, texts
    assert "pg_export_snapshot()" in texts[begin + 1], texts
    # Every count of the run is read inside that transaction, after the export.
    assert counts and all(begin + 1 < i < commit for i in counts), texts
    # The application dump joins the exported snapshot; the Keycloak dump cannot.
    joined = [t for pid, t in run if pid != control and t.startswith("SET TRANSACTION SNAPSHOT")]
    assert len(joined) == 1, joined


def test_k03_7_contrast_the_statement_log_holds_nothing_outside_the_logged_run(
    backup_lab: BackupLab,
) -> None:
    """The log window is the run's own: with logging reset, a second run adds no statement."""
    first_run = statement_logged_run(backup_lab)
    assert first_run, "the parser found no statement in the logged run"
    already = len(logged_statements(backup_lab))
    result = backup_lab.run()
    assert result.code == 0, result.stderr
    assert logged_statements(backup_lab)[already:] == []
