"""EKO-4-01 K-04, the image half of ADR-0002-C8 (gate 1, A-7 A): inside the backend image the
repository's normal build produced, with no network, `ZoneInfo("Europe/Warsaw")` loads and the
application's own range function resolves the 25-hour day 2026-10-25 to the same half-open range
as in the test process. The unit half is `tests/unit/test_eko401_k04_warsaw_ranges.py`.
"""

import json
from datetime import date

import pytest

from app.domain import warsaw
from tests.runtime.lab import Lab

pytestmark = pytest.mark.runtime

SCRIPT = """
import json
from datetime import date
from zoneinfo import ZoneInfo

from app.domain import warsaw

zone = ZoneInfo("Europe/Warsaw")
found = warsaw.period_of(date(2026, 10, 25), date(2026, 10, 25))
print(json.dumps({  # leftovers-allow: probe runs in the image; stdout is its answer
    "zone": str(zone),
    "starts": found.starts.isoformat(),
    "ends": found.ends.isoformat(),
    "hours": (found.ends - found.starts).total_seconds() / 3600,
}))
"""


def test_k04_the_image_loads_the_warsaw_zone_and_resolves_the_25_hour_day(lab: Lab) -> None:
    printed = json.loads(lab.image_python(lab.shipped_image, SCRIPT).strip().splitlines()[-1])
    here = warsaw.period_of(date(2026, 10, 25), date(2026, 10, 25))
    assert printed == {
        "zone": "Europe/Warsaw",
        "starts": here.starts.isoformat(),
        "ends": here.ends.isoformat(),
        "hours": 25.0,
    }


def test_k04_contrast_a_zone_the_image_does_not_hold_is_refused_there(lab: Lab) -> None:
    script = (
        "from zoneinfo import ZoneInfo, ZoneInfoNotFoundError\n"
        "try:\n    ZoneInfo('Europe/Nowhere-eko401')\nexcept ZoneInfoNotFoundError:\n"
        "    print('refused')\n"  # leftovers-allow: probe runs in the image; stdout is its answer
    )
    assert lab.image_python(lab.shipped_image, script).strip() == "refused"
