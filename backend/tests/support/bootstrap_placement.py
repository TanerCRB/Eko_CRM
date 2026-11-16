"""EKO-2-01 (option A, 2026-11-15): give the Keycloak bootstrap a placement naming a fixture image.

When its environment carries the checked-image pairs, `scripts/keycloak-bootstrap.sh` composes
the same placement override as the runtime harness (EKO-1-26 QA F-1) and passes explicit `-f`
files, so a `COMPOSE_FILE` given to it is not read. A runtime contrast that has to start Keycloak
from a fixture image in build mode and in release mode alike therefore gives the bootstrap a
placement: each project image as the composition's containers already run it, with keycloak
replaced by the fixture.

This writes the variable for a child process only. It never reads the session's own value, so
the result does not depend on the mode the session runs in.
"""

PLACEMENT_VARIABLE = "EKO_CHECKED_IMAGES"
# The image families the bootstrap requires besides keycloak; migrate and worker run backend's.
RUNNING_FAMILIES = ("backend", "frontend", "proxy", "backup")


def bootstrap_placement(running: dict[str, str], keycloak_image: str) -> dict[str, str]:
    """Environment overrides for the bootstrap. `running` maps each of RUNNING_FAMILIES to the
    image its container runs; every family keeps that image, and keycloak gets `keycloak_image`."""
    images = {family: running[family] for family in RUNNING_FAMILIES}
    images["keycloak"] = keycloak_image
    return {PLACEMENT_VARIABLE: " ".join(f"{name}={image}" for name, image in images.items())}
