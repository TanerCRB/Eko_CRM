"""K-07 / ADR-0002-C2: no test-only revision reaches the image that ships.

The shipped image is the one the repository's normal build produced for the lab. Its tree is
exactly {0001, 0002, 0003}, each on the one before; `0002` creates schema_revision_lineage;
every variant the EKO-1-11 tests use differs from it only by files added under
/app/migrations/versions/, so those tests run the shipped env.py, app/ and entry points. A
one-head check is the wrong guard here: a test revision chained onto 0003 keeps one head.
"""

import json

import pytest

from tests.runtime.lab import ENV_PY, SOURCE_ENV_PY, VARIANTS, Lab
from tests.support import db_checks as dc
from tests.support import migration_checks as mc

pytestmark = pytest.mark.runtime

LIST_VERSIONS = (
    "import os, sys; "
    "print('\\n'.join(sorted(os.listdir(sys.argv[1]))))"  # leftovers-allow: probe stdout
)
# Every regular file and symlink of the image with its content digest; the paths Docker mounts or
# writes into a running container are left out.
LISTING = """
import hashlib, json, os
SKIP_DIRS = {"/proc", "/sys", "/dev"}
SKIP_FILES = {"/etc/hostname", "/etc/hosts", "/etc/resolv.conf", "/.dockerenv"}
found = {}
for root, dirs, files in os.walk("/"):
    dirs[:] = [d for d in dirs if os.path.join(root, d) not in SKIP_DIRS]
    for name in files:
        path = os.path.join(root, name)
        if path in SKIP_FILES:
            continue
        if os.path.islink(path):
            found[path] = "link:" + os.readlink(path)
        elif os.path.isfile(path):
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            found[path] = digest.hexdigest() + ":" + oct(os.stat(path).st_mode)
print(json.dumps(found))  # leftovers-allow: the listing runs in the image; stdout is its answer
"""


def listing(lab: Lab, image: str) -> dict[str, str]:
    found: dict[str, str] = json.loads(lab.image_python(image, LISTING))
    return found


def test_adr0002_c2_shipped_revision_tree(lab: Lab) -> None:
    history = lab.image_command(lab.shipped_image, "alembic", "history")
    assert history.returncode == 0, history.stderr[-2000:]
    files = lab.image_python(lab.shipped_image, LIST_VERSIONS, "/app/migrations/versions").split()
    assert mc.shipped_tree_violations(mc.history_edges(history.stdout), files) == []


def test_adr0002_c2_shipped_revision_tree_creates_the_lineage_table(lab: Lab) -> None:
    lab.at_head()
    columns = lab.sql(
        "SELECT column_name, data_type, is_nullable, coalesce(column_default, '<none>'), "
        "coalesce(collation_name, '<default>') FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'schema_revision_lineage'"
    )
    primary_key = lab.sql(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey) "
        "WHERE i.indrelid = 'public.schema_revision_lineage'::regclass AND i.indisprimary"
    )
    assert columns == [["revision", "text", "NO", "<none>", "C"]]
    assert primary_key == [["revision"]]


def test_adr0002_c2_shipped_revision_tree_passes_alembic_check(lab: Lab) -> None:
    lab.serving_backend()
    result = lab.composition.compose("exec", "-T", "backend", "alembic", "check", check=False)
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.fixture(scope="module")
def shipped_listing(lab: Lab) -> dict[str, str]:
    return listing(lab, lab.shipped_image)


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_adr0002_c2_shipped_revision_tree_variants_only_add_revision_files(
    lab: Lab, shipped_listing: dict[str, str], name: str
) -> None:
    found = listing(lab, lab.variant(name))
    assert mc.listing_violations(shipped_listing, found) == []
    added = set(found) - set(shipped_listing)
    assert added == {f"{mc.VARIANT_DIR}{file_name}" for file_name in VARIANTS[name]}


def test_adr0002_c2_contrast_a_variant_replacing_env_py_is_found(
    lab: Lab, shipped_listing: dict[str, str]
) -> None:
    planted = SOURCE_ENV_PY.read_text(encoding="utf-8") + "# planted\n"
    image = lab.variant("planted_env", VARIANTS["next"], {ENV_PY: planted})
    violations = mc.listing_violations(shipped_listing, listing(lab, image))
    assert f"changed: {ENV_PY}" in violations


def test_adr0002_c2_contrast_a_planted_0004_keeps_one_head_but_fails_the_tree_check(
    lab: Lab,
) -> None:
    image = lab.variant("planted_0004", ("t_planted_0004.py",))
    heads = lab.image_command(image, "alembic", "heads")
    assert dc.c2_heads(heads.stdout, ["0004"]) == []
    history = lab.image_command(image, "alembic", "history")
    files = lab.image_python(image, LIST_VERSIONS, "/app/migrations/versions").split()
    assert mc.shipped_tree_violations(mc.history_edges(history.stdout), files) != []
