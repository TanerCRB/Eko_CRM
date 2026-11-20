"""EKO-3-02 K-03, static half (C-1 A, Q-4 A): the dated register file the backend validates
voivodeships and counties with names its source (GUS, TERYT, TERC) and its date, and holds the 16
voivodeships and 380 counties (314 land counties, 66 cities with county rights), each county
under exactly one voivodeship.

Whether the file matches GUS's register as of that date is not decided here: that is the human's
spot-check at gate 2 against the source file named inside it.
"""

import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from app.domain import regions
from tests.support import repo_checks as rc
from tests.support.repo import REPO_ROOT

DOMAIN = REPO_ROOT / "backend" / "app" / "domain"
DATED_NAME = re.compile(r"teryt_terc_(\d{4}-\d{2}-\d{2})\.json")
LAND_COUNTY = "powiat"
CITY_KINDS = {"miasto na prawach powiatu", "miasto stołeczne, na prawach powiatu"}


def register_file() -> Path:
    """The one dated file in the domain package, which must be the one the domain loads."""
    [found] = [p for p in DOMAIN.iterdir() if DATED_NAME.fullmatch(p.name)]
    assert found.name == regions.REGISTER_FILE
    return found


def document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(register_file().read_text(encoding="utf-8"))
    return loaded


def test_k03_the_file_names_its_source_and_its_date() -> None:
    doc = document()
    assert "GUS" in doc["source"] and "TERYT" in doc["source"] and "TERC" in doc["source"]
    assert doc["source_url"].startswith("https://eteryt.stat.gov.pl/")
    match = DATED_NAME.fullmatch(register_file().name)
    assert match is not None
    assert doc["as_of"] == match.group(1)
    assert date.fromisoformat(doc["as_of"]) == regions.REGISTER.as_of
    assert re.fullmatch(r"[0-9a-f]{64}", doc["source_file_sha256"])


def test_k03_sixteen_voivodeships_and_380_counties_each_under_one() -> None:
    voivodeships = document()["voivodeships"]
    assert len(voivodeships) == 16
    assert len({v["name"] for v in voivodeships}) == 16
    assert len({v["terc"] for v in voivodeships}) == 16
    counties = [(v["terc"], c) for v in voivodeships for c in v["counties"]]
    assert len(counties) == 380
    kinds = Counter(c["kind"] for _, c in counties)
    assert kinds[LAND_COUNTY] == 314
    assert sum(kinds[k] for k in CITY_KINDS) == 66
    assert set(kinds) == {LAND_COUNTY, *CITY_KINDS}
    # Each county's TERC code is unique and starts with its own voivodeship's code.
    assert len({c["terc"] for _, c in counties}) == 380
    assert all(c["terc"][:2] == woj and len(c["terc"]) == 4 for woj, c in counties)
    # Names are unique within a voivodeship, so (voivodeship, county) is a key.
    for voivodeship in voivodeships:
        names = [c["name"] for c in voivodeship["counties"]]
        assert len(names) == len(set(names)), voivodeship["name"]


def test_k03_the_domain_holds_exactly_the_file() -> None:
    voivodeships = document()["voivodeships"]
    assert [v.name for v in regions.REGISTER.voivodeships] == [v["name"] for v in voivodeships]
    for loaded, written in zip(regions.REGISTER.voivodeships, voivodeships, strict=True):
        assert [c.name for c in loaded.counties] == [c["name"] for c in written["counties"]]


def test_k03_twin_county_names_sit_under_two_voivodeships() -> None:
    under: dict[str, list[str]] = {}
    for voivodeship in document()["voivodeships"]:
        for county in voivodeship["counties"]:
            under.setdefault(county["name"], []).append(voivodeship["name"])
    twins = {name: sorted(names) for name, names in under.items() if len(names) > 1}
    assert twins["bielski"] == ["podlaskie", "śląskie"]
    assert {"brzeski", "grodziski", "ostrowski", "średzki", "świdnicki", "tomaszowski"} <= set(
        twins
    )


def test_k03_every_name_is_nfc_and_the_file_holds_no_personal_data_shape() -> None:
    text = register_file().read_text(encoding="utf-8")
    assert unicodedata.normalize("NFC", text) == text
    assert rc.personal_data({register_file().name: text.splitlines()}) == []
