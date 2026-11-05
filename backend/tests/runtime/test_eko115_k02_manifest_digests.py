"""EKO-1-15 K-02, manifest half (ADR-0004 addendum 2026-10-30): a backup set taken with the
release composition's references, all three in digest form, has a manifest naming exactly them,
with no change under `backup/`.

The references are those the producer renders for `backup`'s manifest variables (the YAML anchors
of the repository composition, resolved); the run is the lab's real `backup` against the local
destination double. Contrast: the repository composition's own references are the local tag.
"""

import pytest
import yaml

from tests.runtime.backup_lab import BackupLab, open_set, set_names
from tests.static.test_k07_changeset import changed_paths
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

DIGESTS = {
    name: "sha256:" + (name.encode().hex() * 64)[:64]
    for name in ("backend", "frontend", "proxy", "backup", "postgres", "keycloak")
}
NAMES = ("backend", "keycloak", "postgres")


def manifest_references(compose: str) -> dict[str, str]:
    environment = yaml.safe_load(compose)["services"]["backup"]["environment"]
    return {name: str(environment[f"BACKUP_MANIFEST_{name.upper()}_IMAGE"]) for name in NAMES}


def test_eko115_k02_manifest_names_the_release_digests(backup_lab: BackupLab) -> None:
    release = rc.render((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"), "v1.2.0", DIGESTS)
    given = manifest_references(release)
    services = yaml.safe_load(release)["services"]
    assert given == {name: services[name]["image"] for name in NAMES}
    assert [ref for ref in given.values() if rc.digest_violations(ref)] == []

    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    env = {f"BACKUP_MANIFEST_{name.upper()}_IMAGE": ref for name, ref in given.items()}
    result = backup_lab.run(env=env)
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    manifest = open_set(backup_lab.double, name, backup_lab.identity).manifest
    assert manifest["images"] == given
    assert [p for p in changed_paths() if p.startswith("backup/")] == []


def test_eko115_k02_contrast_the_repository_composition_names_the_local_tag() -> None:
    given = manifest_references((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert given["backend"].startswith("localhost/eko-crm/backend:")
    assert rc.digest_violations(given["backend"]) != []
