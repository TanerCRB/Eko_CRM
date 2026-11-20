"""Polish voivodeships and counties as the GUS TERYT register (TERC) names them, from the dated
file beside this module (EKO-3-02, C-1 A; Q-4 A).

The file is read once, at import, from the package itself: no setting, no network, no other
layer. A county is keyed by its voivodeship and its name together, since ten names belong to
two voivodeships each. Names are compared exactly as the file writes them, after NFC (G-3 A).
A rule that refuses a value raises `ValueError` with a fixed message that never repeats it.
"""

import json
from dataclasses import dataclass
from datetime import date
from importlib import resources

REGISTER_FILE = "teryt_terc_2026-01-01.json"
# Longer than any name of the register (the longest is 23 characters); checked at load.
NAME_LIMIT = 64


@dataclass(frozen=True)
class County:
    terc: str
    name: str
    kind: str


@dataclass(frozen=True)
class Voivodeship:
    terc: str
    name: str
    counties: tuple[County, ...]


@dataclass(frozen=True)
class Register:
    source: str
    as_of: date
    voivodeships: tuple[Voivodeship, ...]


def _load() -> Register:
    text = resources.files("app.domain").joinpath(REGISTER_FILE).read_text(encoding="utf-8")
    document = json.loads(text)
    register = Register(
        source=document["source"],
        as_of=date.fromisoformat(document["as_of"]),
        voivodeships=tuple(
            Voivodeship(
                terc=v["terc"],
                name=v["name"],
                counties=tuple(County(c["terc"], c["name"], c["kind"]) for c in v["counties"]),
            )
            for v in document["voivodeships"]
        ),
    )
    names = [v.name for v in register.voivodeships]
    names += [c.name for v in register.voivodeships for c in v.counties]
    if any(len(name) > NAME_LIMIT for name in names):
        raise RuntimeError("a register name is longer than the name limit")
    return register


REGISTER = _load()
_COUNTIES: dict[str, frozenset[str]] = {
    v.name: frozenset(c.name for c in v.counties) for v in REGISTER.voivodeships
}


def voivodeship(name: str) -> str:
    """One of the register's 16 voivodeships, exactly."""
    if name not in _COUNTIES:
        raise ValueError("not a voivodeship of the register")
    return name


def county(voivodeship_name: str, name: str) -> str:
    """A county of the given voivodeship, exactly; `voivodeship_name` is already checked."""
    if name not in _COUNTIES[voivodeship_name]:
        raise ValueError("not a county of the chosen voivodeship")
    return name
