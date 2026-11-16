"""EKO-1-15 K-01 (ADR-0004-C29): the release composition names every image by digest, the
`FROM` of `proxy/Dockerfile` carries a digest, and otherwise it passes the repository
composition's controls with its required variables kept and no value substituted.

The release composition is the producer's output for given digests; fixtures change one
reference of it to tag-only (derived at run time, so no unpinned reference is a tracked line).
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.static.conftest import COMPOSE
from tests.support import compose_checks as cc
from tests.support import release_composition as rc
from tests.support.repo import REPO_ROOT, render, write_synthetic_env

PROXY_DOCKERFILE = (REPO_ROOT / "proxy" / "Dockerfile").read_text(encoding="utf-8")
TAG = "v1.2.0"
# Split so the tracked-file reference scan (ADR-0002-C12) never reads a planted reference.
PG_NAME = "postgres"
PG = PG_NAME + ":18.6-trixie"


def digest(seed: str) -> str:
    return "sha256:" + (seed.encode().hex() * 64)[:64]


DIGESTS = {
    "backend": digest("backend"),
    "frontend": digest("frontend"),
    "proxy": digest("proxy"),
    "backup": digest("backup"),
    "postgres": digest("postgres"),
    "keycloak": digest("keycloak"),
}


def release_text() -> str:
    return rc.render(COMPOSE.read_text(encoding="utf-8"), TAG, DIGESTS)


def source(text: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(text)
    return loaded


def rendered(tmp_path: Path, text: str, dev_profile: bool) -> dict[str, Any]:
    target = tmp_path / "compose.release.yaml"
    target.write_text(text, encoding="utf-8")
    env = tmp_path / f"synthetic-{dev_profile}.env"
    write_synthetic_env(env, compose_file=target)
    return render(env, dev_profile=dev_profile, compose_file=target)


def tag_only(text: str, service: str) -> str:
    """The release composition with `service`'s image stripped of its digest."""
    image = str(source(text)["services"][service]["image"])
    assert "@sha256:" in image
    assert text.count(image) >= 1
    return re.sub(r"(image: (?:&\S+ )?)" + re.escape(image), r"\g<1>" + image.split("@")[0], text)


def test_eko115_k01_release_composition_passes_the_digest_rule() -> None:
    assert rc.c29_violations(source(release_text()), PROXY_DOCKERFILE) == []


def test_eko115_k01_project_images_name_the_given_digests() -> None:
    services = source(release_text())["services"]
    # EKO-1-26 route A: the custom Keycloak image is the fifth project image — it names the
    # project registry like the four before it, not a pulled third-party location.
    for name in ("backend", "frontend", "proxy", "backup", "keycloak"):
        assert services[name]["image"] == f"ghcr.io/tanercrb/eko-crm/{name}:{TAG}@{DIGESTS[name]}"
    for name in ("migrate", "worker"):
        assert services[name]["image"] == services["backend"]["image"]
    assert services["postgres"]["image"] == f"{PG}@{DIGESTS['postgres']}"


def test_eko126_k03_release_names_the_custom_image_not_the_official_repository() -> None:
    """EKO-1-26 K-03: whose digest the reference carries is a fact the digest form cannot show —
    `c29_violations` passes a reference from the official repository with any digest alike
    (finding B-01's substitution), so the rendered location itself is asserted here."""
    image = str(source(release_text())["services"]["keycloak"]["image"])
    assert image == f"{rc.PROJECT_REGISTRY}/keycloak:{TAG}@{DIGESTS['keycloak']}"
    assert "keycloak/keycloak" not in image
    assert not image.startswith("quay.io")


@pytest.mark.parametrize("service", ["backend", "postgres", "keycloak"])
def test_eko115_k01_digest_rule_fails_on_a_tag_only_reference(service: str) -> None:
    problems = rc.c29_violations(source(tag_only(release_text(), service)), PROXY_DOCKERFILE)
    assert any(p.startswith(f"{service}:") for p in problems), problems


def test_eko115_k01_digest_rule_fails_on_a_tag_only_proxy_base() -> None:
    planted = re.sub(r"(FROM \S+?)@sha256:[0-9a-f]{64}", r"\1", PROXY_DOCKERFILE)
    assert planted != PROXY_DOCKERFILE
    problems = rc.c29_violations(source(release_text()), planted)
    assert any(p.startswith("proxy/Dockerfile:") for p in problems), problems


def test_eko115_k01_digest_rule_fails_on_a_shared_service_with_build() -> None:
    services = source(release_text())
    services["services"]["proxy"]["build"] = {"context": "./proxy"}
    assert rc.c29_violations(services, PROXY_DOCKERFILE) != []


@pytest.mark.parametrize(
    "reference",
    [
        PG + "@sha256:" + "a" * 63,
        PG + "@sha256:" + "a" * 65,
        PG + "@sha256:" + "A" * 64,
        PG + "@sha256:",
        PG + "@",
        PG + "@sha512:" + "a" * 128,
        PG,
    ],
)
def test_eko115_k01_edge_malformed_digest_fails(reference: str) -> None:
    assert rc.digest_violations(reference) != [], reference


@pytest.mark.parametrize(
    "reference",
    [PG + "@sha256:" + "a" * 64, PG_NAME + "@sha256:" + "0" * 64],
)
def test_eko115_k01_edge_tag_beside_digest_and_bare_digest_pass(reference: str) -> None:
    assert rc.digest_violations(reference) == []


def test_eko115_k01_mail_catcher_stays_dev_only_and_untouched() -> None:
    services = source(release_text())["services"]
    assert services["mailcatcher"]["profiles"] == ["dev"]
    assert rc.c29_violations(source(release_text()), PROXY_DOCKERFILE) == []


# The release composition otherwise passes the repository's controls ------------------------


@pytest.fixture(scope="module")
def release_renderings(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    directory = tmp_path_factory.mktemp("release")
    text = release_text()
    return {
        "dev": rendered(directory, text, True),
        "shared": rendered(directory, text, False),
    }


def test_eko115_k01_release_composition_passes_c1_to_c4_and_c28(
    release_renderings: dict[str, dict[str, Any]],
) -> None:
    dev, shared = release_renderings["dev"], release_renderings["shared"]
    problems = cc.c1_services(dev, shared)
    for profile in (dev, shared):
        problems += cc.c2_images(profile) + cc.c3_ports(profile) + cc.c4_state(profile)
        problems += cc.c28_rendered(profile)
    release = source(release_text())
    problems += cc.c3_admin_bind_declared(release) + cc.c28_source(release)
    assert problems == []


def test_eko115_k01_shared_rendering_has_no_build_and_every_image_by_digest(
    release_renderings: dict[str, dict[str, Any]],
) -> None:
    shared = release_renderings["shared"]["services"]
    assert [name for name, s in shared.items() if "build" in s] == []
    assert [n for n, s in shared.items() if rc.digest_violations(str(s["image"]))] == []


def test_eko115_k01_required_variables_stay_required(secret_inventory: set[str]) -> None:
    text = release_text()
    assert rc.variable_violations(COMPOSE.read_text(encoding="utf-8"), text) == []
    assert cc.secret_declaration_violations(source(text), secret_inventory) == []
    assert source(text)["name"] == "${COMPOSE_PROJECT_NAME:?COMPOSE_PROJECT_NAME is required}"


def test_eko115_k01_a_substituted_value_fails(secret_inventory: set[str]) -> None:
    text = release_text()
    # Built from its parts: the tracked-file secret scan (ADR-0004-C9) reads this file too.
    name = "APP_DB" + "_PASSWORD"
    required = "${" + name + ":?" + name + " is required}"
    assert required in text
    planted = text.replace(required, "planted-sentinel-value")
    assert rc.variable_violations(COMPOSE.read_text(encoding="utf-8"), planted) != []
    assert cc.secret_declaration_violations(source(planted), secret_inventory) != []


def test_eko115_k01_proxy_dockerfile_base_is_pinned_by_digest_in_the_repository() -> None:
    assert rc.dockerfile_violations("proxy/Dockerfile", PROXY_DOCKERFILE) == []


def test_eko115_k01_producer_refuses_a_malformed_digest() -> None:
    with pytest.raises(ValueError):
        rc.render(COMPOSE.read_text(encoding="utf-8"), TAG, {**DIGESTS, "backend": "sha256:x"})


def test_eko115_k01_producer_refuses_a_missing_digest() -> None:
    missing = {k: v for k, v in DIGESTS.items() if k != "keycloak"}
    with pytest.raises(ValueError):
        rc.render(COMPOSE.read_text(encoding="utf-8"), TAG, missing)
