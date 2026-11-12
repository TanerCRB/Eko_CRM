"""K-04: composition controls on both rendered profiles; each fails on a one-violation fixture.

ADR-0004-C1, C2, C3, C4, C11, the static half of C28, ADR-0003-C3 and the composition half of
ADR-0006-C13. The fixtures are compose.yaml with one case of fixtures/composition_cases.yaml.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from tests.static.conftest import COMPOSE, composition_cases
from tests.support import backup_checks as bc
from tests.support import compose_checks as cc
from tests.support.repo import REPO_ROOT

Rendered = dict[str, Any]
RenderCase = Callable[..., Rendered]
SourceCase = Callable[[str], dict[str, Any]]
BACKEND_DOCKERFILE = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")


def test_k04_every_fixture_case_is_one_change_of_the_real_file() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    for item in composition_cases():
        assert text.count(item["old"]) == 1, item["id"]


def test_k04_no_override_file_is_loaded_beside_the_composition() -> None:
    names = [p.name for p in REPO_ROOT.iterdir() if "override" in p.name and "compose" in p.name]
    assert names == []


# ADR-0004-C1 -------------------------------------------------------------------------------


def test_k04_c1_nine_services_in_dev_and_eight_shared(
    rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    assert cc.c1_services(rendered_dev, rendered_shared) == []


def test_k04_c1_fails_with_a_mail_catcher_in_the_shared_profile(render_case: RenderCase) -> None:
    case_id = "c1-mail-catcher-in-shared-profile"
    dev, shared = render_case(case_id, True), render_case(case_id, False)
    assert cc.c1_services(dev, shared) != []


# ADR-0004-C2 and ADR-0003-C3 on the composition -------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_k04_c2_every_image_is_pinned(
    profile: str, rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    assert cc.c2_images(rendered_dev if profile == "dev" else rendered_shared) == []


@pytest.mark.parametrize(
    "case_id",
    [
        "c2-postgres-bare-major",
        "c2-postgres-floating-alpine",
        "c2-mail-catcher-floating",
        "adr0003-c3-keycloak-minor-only",
    ],
)
def test_k04_c2_fails_on_an_unpinned_image(case_id: str, render_case: RenderCase) -> None:
    assert cc.c2_images(render_case(case_id, True)) != []


# ADR-0004-C3 and DoD item 12 ---------------------------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_k04_c3_only_proxy_publishes_ports(
    profile: str, rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    assert cc.c3_ports(rendered_dev if profile == "dev" else rendered_shared) == []


def test_k04_c3_admin_bind_is_a_required_variable(compose_source: dict[str, Any]) -> None:
    assert cc.c3_admin_bind_declared(compose_source) == []


@pytest.mark.parametrize(
    "case_id",
    ["c3-ports-on-postgres", "c3-host-network-on-backend", "c3-admin-listener-on-every-address"],
)
@pytest.mark.parametrize("dev_profile", [True, False])
def test_k04_c3_fails_on_a_published_port(
    case_id: str, dev_profile: bool, render_case: RenderCase
) -> None:
    assert cc.c3_ports(render_case(case_id, dev_profile)) != []


@pytest.mark.parametrize(
    "case_id", ["c3-admin-listener-on-every-address", "c3-admin-bind-with-default"]
)
def test_k04_c3_fails_when_admin_bind_is_not_required(
    case_id: str, source_case: SourceCase
) -> None:
    assert cc.c3_admin_bind_declared(source_case(case_id)) != []


# ADR-0004-C4 -------------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_k04_c4_state_only_in_the_three_named_volumes(
    profile: str, rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    # C4 as amended by the addendum of 2026-11-10: `keycloak-boot` (the boot-token carrier)
    # joins the two state volumes. A FOURTH declared volume needs two changes to render at
    # all (compose drops an unused declaration from `config`), so the "exactly these three"
    # superset half of the amendment is pinned on the source side — the unrendered set
    # assertion in tests/static/test_eko112_k01_custom_provider_image.py.
    assert cc.c4_state(rendered_dev if profile == "dev" else rendered_shared) == []


def test_k04_c4_fails_on_a_host_path_into_postgres(render_case: RenderCase) -> None:
    assert cc.c4_state(render_case("c4-host-path-into-postgres")) != []


# ADR-0004-C11 and ADR-0006-C13 (composition half) ------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_k04_c11_only_migrate_upgrades_and_others_wait_for_it(
    profile: str, rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    rendered = rendered_dev if profile == "dev" else rendered_shared
    assert cc.c11_migrations(rendered, BACKEND_DOCKERFILE) == []


@pytest.mark.parametrize(
    "case_id",
    [
        "c11-upgrade-in-backend-command",
        "c11-upgrade-in-worker-command",
        "c11-worker-service-started",
        "c11-upgrade-with-config-option",
        "c11-upgrade-split-across-entrypoint-and-command",
    ],
)
def test_k04_c11_fails_on_a_second_migrating_process(case_id: str, render_case: RenderCase) -> None:
    assert cc.c11_migrations(render_case(case_id), BACKEND_DOCKERFILE) != []


def test_k04_c11_fails_when_the_backend_image_upgrades(rendered_shared: Rendered) -> None:
    dockerfile = BACKEND_DOCKERFILE.replace(
        'CMD ["python", "-m", "app.serve"]',
        'CMD ["sh", "-c", "alembic upgrade head && python -m app.serve"]',
    )
    assert dockerfile != BACKEND_DOCKERFILE
    assert cc.c11_migrations(rendered_shared, dockerfile) != []


def test_k04_adr0006_c13_worker_runs_the_backend_image(rendered_shared: Rendered) -> None:
    assert cc.c13_worker_image(rendered_shared) == []


@pytest.mark.parametrize("case_id", ["c13-worker-on-another-image", "c13-worker-built-separately"])
def test_k04_adr0006_c13_fails_on_a_worker_with_another_image(
    case_id: str, render_case: RenderCase
) -> None:
    assert cc.c13_worker_image(render_case(case_id)) != []


# ADR-0004-C28, static half -----------------------------------------------------------------


@pytest.mark.parametrize("profile", ["dev", "shared"])
def test_k04_c28_postgres_is_the_image_with_inline_init_content(
    profile: str, rendered_dev: Rendered, rendered_shared: Rendered
) -> None:
    assert cc.c28_rendered(rendered_dev if profile == "dev" else rendered_shared) == []


def test_k04_c28_init_content_has_no_interpolation(compose_source: dict[str, Any]) -> None:
    assert cc.c28_source(compose_source) == []


@pytest.mark.parametrize("case_id", ["c28-build-on-postgres", "c28-file-source"])
def test_k04_c28_fails_on_a_built_postgres_or_a_file_source(
    case_id: str, render_case: RenderCase, source_case: SourceCase
) -> None:
    problems = cc.c28_rendered(render_case(case_id)) + cc.c28_source(source_case(case_id))
    assert problems != []


@pytest.mark.parametrize("case_id", ["c28-braced-interpolation", "c28-bare-interpolation"])
def test_k04_c28_fails_on_any_interpolation_in_the_init_content(
    case_id: str, source_case: SourceCase
) -> None:
    assert cc.c28_source(source_case(case_id)) != []


def test_k04_c28_dollar_rule_counts_only_unescaped_dollars() -> None:
    assert cc.unescaped_dollars("a $$b $${c} $$$$") == []
    assert len(cc.unescaped_dollars("$a $$b ${c} $$$d")) == 3


# ADR-0004-C9 and C10, declaration half ------------------------------------------------------


def test_k04_c10_every_secret_is_required_with_no_default(
    compose_source: dict[str, Any], secret_inventory: set[str]
) -> None:
    assert cc.secret_declaration_violations(compose_source, secret_inventory) == []


@pytest.mark.parametrize(
    "case_id", ["c9-secret-with-default", "c9-secret-with-value", "c10-secret-not-required"]
)
def test_k04_c10_fails_on_a_secret_with_a_default_or_value(
    case_id: str, source_case: SourceCase, secret_inventory: set[str]
) -> None:
    assert cc.secret_declaration_violations(source_case(case_id), secret_inventory) != []


# R-04: a second migrating process written in another form than the literal "alembic upgrade".


@pytest.mark.parametrize(
    "line",
    [
        'ENTRYPOINT ["alembic", "upgrade", "head"]',
        'CMD ["alembic", "-c", "alembic.ini", "upgrade", "head"]',
        "RUN alembic upgrade head",
        'CMD ["python", "-m", "alembic", "upgrade", "head"]',
    ],
)
def test_k04_c11_fails_on_an_image_that_migrates_in_any_form(
    line: str, rendered_shared: Rendered
) -> None:
    dockerfile = BACKEND_DOCKERFILE + line + "\n"
    assert cc.c11_migrations(rendered_shared, dockerfile) != []


def test_k04_c11_backend_sources_never_migrate() -> None:
    assert cc.backend_source_migration_violations(backend_sources()) == []


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("backend/entrypoint.sh", '#!/bin/sh\nalembic -c alembic.ini upgrade head\nexec "$@"\n'),
        ("backend/app/core/startup.py", "from alembic import command\n"),
        ("backend/app/main.py", "import alembic.command\n"),
        ("backend/app/serve.py", "command.upgrade(config, 'head')\n"),
    ],
)
def test_k04_c11_fails_on_backend_code_or_a_script_that_migrates(path: str, text: str) -> None:
    sources = {**backend_sources(), path: text}
    assert cc.backend_source_migration_violations(sources) != []


def backend_sources() -> dict[str, str]:
    """The files of the backend build context outside migrations/ and tests/."""
    root = REPO_ROOT / "backend"
    sources = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or relative.split("/")[0] in {"migrations", "tests", ".venv"}:
            continue
        if path.suffix in {".py", ".sh"} or path.name.startswith("Dockerfile"):
            sources[f"backend/{relative}"] = path.read_text(encoding="utf-8")
    return sources


# ADR-0004-C9 and C10 for backup's variables (EKO-1-14 K-06) ----------------------------------


def test_k06_c9_backup_variables_are_required_with_no_default(
    compose_source: dict[str, Any], secret_inventory: set[str]
) -> None:
    assert bc.backup_variable_violations(compose_source) == []
    assert set(bc.SECRET_VARIABLES) <= secret_inventory


@pytest.mark.parametrize("variable", [*bc.SECRET_VARIABLES, *bc.VALUE_VARIABLES])
@pytest.mark.parametrize("planted", ["${{{name}:-x}}", "synthetic-value", "${{{name}}}"])
def test_k06_c9_fails_on_a_backup_variable_with_a_default_or_value(
    compose_source: dict[str, Any], variable: str, planted: str
) -> None:
    source = copy.deepcopy(compose_source)
    source["services"]["backup"].setdefault("environment", {})[variable] = planted.format(
        name=variable
    )
    assert bc.backup_variable_violations(source) != []


# ADR-0004 addendum 2026-10-30, *The manifest*: image references by YAML reference -------------


def test_k03_manifest_images_are_references_to_the_services_images() -> None:
    assert bc.manifest_image_violations(COMPOSE.read_text(encoding="utf-8")) == []


def test_k03_manifest_image_check_fails_on_a_literal_equal_to_the_image() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    old = "BACKUP_MANIFEST_POSTGRES_IMAGE: *postgres-image"
    assert text.count(old) == 1
    planted = text.replace(old, "BACKUP_MANIFEST_POSTGRES_IMAGE: postgres:18.6-trixie")
    assert bc.manifest_image_violations(planted) != []


def test_k07_backup_dockerfile_is_from_the_postgres_image(rendered_shared: Rendered) -> None:
    dockerfile = (REPO_ROOT / "backup" / "Dockerfile").read_text(encoding="utf-8")
    bases = [line.split()[1] for line in dockerfile.splitlines() if line.startswith("FROM ")]
    assert bases == [rendered_shared["services"]["postgres"]["image"]] == ["postgres:18.6-trixie"]


def test_k06_backup_receives_no_other_services_environment_file(rendered_dev: Rendered) -> None:
    backup = rendered_dev["services"]["backup"]
    assert "env_file" not in backup
    assert not [name for name in backup.get("environment", {}) if name.startswith("APP_")]
