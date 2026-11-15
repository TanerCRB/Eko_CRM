"""Sets the synthetic settings `create_app()` needs since EKO-2-01 (ADR-0005 synthetic rule).

Tests that build the application in-process, or in a child process inheriting this environment,
set only the database variables they need; the authentication settings (`AuthSettings`) are
required too, with no default for a secret (ADR-0004). These are set only where unset, and a test
that judges them sets or removes them itself. The names are the backend's own: none is a
variable the composition interpolates, so no runtime composition reads them.
"""

import os

from tests.support.synthetic_auth import SYNTHETIC_AUTH_SETTINGS

for _name, _value in SYNTHETIC_AUTH_SETTINGS.items():
    os.environ.setdefault(_name, _value)
