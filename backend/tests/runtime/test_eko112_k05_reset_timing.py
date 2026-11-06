"""EKO-1-12 K-05: local timing series in both orders; no automatic human judgement."""

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.runtime.conftest import Started
from tests.runtime.keycloak_client import RealmClient
from tests.runtime.test_eko112_k04_reset_and_log_privacy import (
    ensure_account,
    messages,
    reset_response,
)
from tests.support import eko112_fixtures as fixtures

pytestmark = pytest.mark.runtime
BASELINE = "2dcb057f818fd9a1e4142fbf0c71276f542f6ffa"


def test_k05_reset_timing_record_is_complete_without_deciding_distinguishability(
    keycloak_running: Started,
) -> None:
    composition = keycloak_running.composition
    administrator = RealmClient(composition, "eko")
    public = RealmClient(composition, "eko", listener="auth")
    try:
        token = administrator.browser_token(
            fixtures.ACCOUNTS["administrator"],
            composition.env[fixtures.PASSWORD_VARIABLES["administrator"]],
            client_id="eko-backend",
            client_secret=composition.env["OIDC_CLIENT_SECRET"],
        )["access_token"]
        ensure_account(
            administrator,
            token,
            fixtures.ACCOUNTS["timing"],
            fixtures.ADDRESSES["timing"],
            secrets.token_urlsafe(32),
            True,
        )
        series: dict[str, list[float]] = {"known": [], "unknown": []}
        statuses: dict[str, set[int]] = {"known": set(), "unknown": set()}
        texts: dict[str, set[str]] = {"known": set(), "unknown": set()}
        mail_counts: dict[str, list[int]] = {"known": [], "unknown": []}
        for order in (("known", "unknown"), ("unknown", "known")):
            for _ in range(2):
                for kind in order:
                    address = fixtures.ADDRESSES[kind]
                    before = len(messages(keycloak_running))
                    status, text, elapsed = reset_response(public, address)
                    after = len(messages(keycloak_running))
                    assert elapsed > 0
                    series[kind].append(round(elapsed * 1000, 3))
                    statuses[kind].add(status)
                    texts[kind].add(text)
                    mail_counts[kind].append(after - before)
        assert statuses["known"] == statuses["unknown"]
        assert texts["known"] == texts["unknown"]
        assert mail_counts["known"] == [1, 1, 1, 1]
        assert mail_counts["unknown"] == [0, 0, 0, 0]
        output = os.environ.get("EKO112_TIMING_RECORD")
        if output:
            record = {
                "title": "EKO-1-12 reset-timing record",
                "date": datetime.now(UTC).date().isoformat(),
                "baseline_sha": BASELINE,
                "environment": "local development composition and mail catcher only",
                "known_address": fixtures.ADDRESSES["timing"],
                "unknown_address": fixtures.ADDRESSES["unknown"],
                "known_ms": series["known"],
                "unknown_ms": series["unknown"],
                "known_mail_messages_per_request": mail_counts["known"],
                "unknown_mail_messages_per_request": mail_counts["unknown"],
                "human_distinguishability_finding": "UNDECIDABLE — returned to the human",
            }
            Path(output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    finally:
        administrator.close()
        public.close()
