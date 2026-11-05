"""EKO-1-15 K-02, manifest half (QA): the manifest of a set taken with the release composition
names the digests that were pushed, not only "the references the composition gave".

The developer's runtime test takes its expected value from the producer's own output, so a
producer that writes the wrong digest into the composition still passes it (QA mutation M3,
2026-11-05). Here the expected references are built independently of the producer: the project
registry name for `backend`, and the repository composition's own tag for `postgres` and
`keycloak`, each followed by the digest the push is said to have returned.
"""

import pytest
import yaml

from tests.runtime.backup_lab import BackupLab, open_set, set_names
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT

pytestmark = pytest.mark.runtime

TAG = "v1.2.0"
PUSHED = {
    name: "sha256:" + (f"qa{name}".encode().hex() * 64)[:64]
    for name in ("backend", "frontend", "proxy", "backup", "postgres", "keycloak")
}
NAMES = ("backend", "keycloak", "postgres")


def expected_references() -> dict[str, str]:
    """What the manifest must name, derived without the producer."""
    services = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]
    return {
        "backend": f"ghcr.io/tanercrb/eko-crm/backend:{TAG}@{PUSHED['backend']}",
        "keycloak": f"{services['keycloak']['image']}@{PUSHED['keycloak']}",
        "postgres": f"{services['postgres']['image']}@{PUSHED['postgres']}",
    }


def test_eko115_k02_qa_manifest_names_the_pushed_digests(backup_lab: BackupLab) -> None:
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    release = yaml.safe_load(rc.render(compose, TAG, PUSHED))
    environment = release["services"]["backup"]["environment"]
    given = {name: str(environment[f"BACKUP_MANIFEST_{name.upper()}_IMAGE"]) for name in NAMES}

    backup_lab.at_probe_head()
    before = set_names(backup_lab.double)
    env = {f"BACKUP_MANIFEST_{name.upper()}_IMAGE": ref for name, ref in given.items()}
    result = backup_lab.run(env=env)
    assert result.code == 0, result.stderr
    [name] = set_names(backup_lab.double) - before
    manifest = open_set(backup_lab.double, name, backup_lab.identity).manifest
    assert manifest["images"] == expected_references()


def test_eko115_k02_qa_contrast_expected_references_differ_per_push() -> None:
    """The expectation is not a constant: each image carries its own pushed digest, and the
    three digests differ, so a swap between them cannot match."""
    expected = expected_references()
    digests = [ref.rsplit("@", 1)[1] for ref in expected.values()]
    assert digests == [PUSHED[name] for name in expected]
    assert len(set(digests)) == len(digests)
