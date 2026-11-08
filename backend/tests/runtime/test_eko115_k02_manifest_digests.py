"""EKO-1-15 K-02, manifest half (ADR-0004 addendum 2026-10-30): a backup set taken with the
release composition's references, all three in digest form, has a manifest naming exactly them,
with no change under `backup/` in EKO-1-15's own change set (PR #85's merge parents, read from git;
EKO-1-21, #109), whatever the branch running this test changes.

The references are those the producer renders for `backup`'s manifest variables (the YAML anchors
of the repository composition, resolved); the run is the lab's real `backup` against the local
destination double. Contrast: the repository composition's own references are the local tag.
"""

import pytest
import yaml

from tests.runtime.backup_lab import BackupLab, open_set, set_names
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT, git

pytestmark = pytest.mark.runtime

DIGESTS = {
    name: "sha256:" + (name.encode().hex() * 64)[:64]
    for name in ("backend", "frontend", "proxy", "backup", "postgres", "keycloak")
}
NAMES = ("backend", "keycloak", "postgres")
# PR #85 (EKO-1-15): 0e525b6^1 and 0e525b6^2.
EKO_1_15_BASE = "14e9576a1bbf17e94f3a281e2061b0c4ad4a6563"
EKO_1_15_HEAD = "0d221229917c0fea3d7b99efaa3cce578e51087f"


def eko_1_15_backup_changes(base: str = EKO_1_15_BASE, head: str = EKO_1_15_HEAD) -> list[str]:
    """Paths under `backup/` changed from `base` to `head`, with `changed_paths()`'s semantics
    (both sides of a rename, mode changes). A commit missing from the checkout raises."""
    out = git("diff", "--name-status", "-M", f"{base}^{{commit}}", f"{head}^{{commit}}", "--")
    paths = {p for line in out.splitlines() for p in line.split("\t")[1:]}
    return sorted(p for p in paths if p.startswith("backup/"))


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
    assert eko_1_15_backup_changes() == []


def test_eko115_k02_contrast_the_repository_composition_names_the_local_tag() -> None:
    given = manifest_references((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert given["backend"].startswith("localhost/eko-crm/backend:")
    assert rc.digest_violations(given["backend"]) != []
