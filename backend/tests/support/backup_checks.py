"""EKO-1-14 checks on backup's declaration in compose.yaml and on its synthetic environment.

Each check returns the violations it finds, empty when the rule holds, so every one can be shown
failing on a planted input (ADR-0004 addendum 2026-10-30, *Secret inventory*, *The manifest*).
"""

import re
from collections.abc import Mapping
from typing import Any

import yaml

SECRET_VARIABLES = ("BACKUP_DESTINATION_CREDENTIAL", "BACKUP_ENCRYPTION_PUBLIC_KEY")
VALUE_VARIABLES = ("BACKUP_DESTINATION", "BACKUP_DESTINATION_HOST_KEY")
DEVELOPMENT_DESTINATION = "sftp://eko-backup@destination.invalid:22/incoming"
MANIFEST_IMAGES = {
    "BACKUP_MANIFEST_BACKEND_IMAGE": "backend",
    "BACKUP_MANIFEST_KEYCLOAK_IMAGE": "keycloak",
    "BACKUP_MANIFEST_POSTGRES_IMAGE": "postgres",
}
SYNTHETIC_SECRET = re.compile(r"synthetic-[0-9a-f]{48}")


def backup_variable_violations(source: Mapping[str, Any]) -> list[str]:
    """The four variables are in backup's environment, each required with no default."""
    environment = source["services"]["backup"].get("environment") or {}
    problems = []
    for name in (*SECRET_VARIABLES, *VALUE_VARIABLES):
        value = environment.get(name)
        if not isinstance(value, str) or not re.fullmatch(rf"\$\{{{name}:\?[^}}]*\}}", value):
            problems.append(f"backup's {name} is {value!r}, not a required ${{{name}:?...}}")
    return problems


def _mapping(node: yaml.Node) -> dict[str, yaml.Node]:
    assert isinstance(node, yaml.MappingNode), node
    return {key.value: value for key, value in node.value}


def manifest_image_violations(compose_text: str) -> list[str]:
    """Each manifest image variable of backup is the YAML alias of its service's `image:`."""
    root = yaml.compose(compose_text)
    assert root is not None
    services = _mapping(_mapping(root)["services"])
    environment = _mapping(services["backup"]).get("environment")
    values = {} if environment is None else _mapping(environment)
    problems = []
    for variable, service in MANIFEST_IMAGES.items():
        image = _mapping(services[service]).get("image")
        if values.get(variable) is None or values.get(variable) is not image:
            problems.append(f"backup's {variable} is not a reference to {service}'s image")
    return problems


def dev_env_backup_violations(values: Mapping[str, str]) -> list[str]:
    """The development environment holds synthetic values only for the four variables."""
    problems = []
    for name in (*SECRET_VARIABLES, "BACKUP_DESTINATION_HOST_KEY"):
        if not SYNTHETIC_SECRET.fullmatch(values.get(name, "")):
            problems.append(f"{name} is not a synthetic random value")
    if values.get("BACKUP_DESTINATION") != DEVELOPMENT_DESTINATION:
        problems.append(f"BACKUP_DESTINATION is {values.get('BACKUP_DESTINATION')!r}")
    return problems
