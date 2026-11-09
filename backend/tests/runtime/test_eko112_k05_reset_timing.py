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
    recipient_messages,
    reset_response,
    wait_for_recipient_message,
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
        # The known-address class is backed by the `timing` account this test creates (the
        # eko112-known account belongs to K-04 and may not exist standalone-cold); the
        # unknown-address class is `ADDRESSES["unknown"]`, absent even case-insensitively.
        addresses = {
            "known": fixtures.ADDRESSES["timing"],
            "unknown": fixtures.ADDRESSES["unknown"],
        }
        series: dict[str, list[float]] = {"known": [], "unknown": []}
        statuses: dict[str, set[int]] = {"known": set(), "unknown": set()}
        texts: dict[str, set[str]] = {"known": set(), "unknown": set()}
        mail_counts: dict[str, list[int]] = {"known": [], "unknown": []}
        for order in (("known", "unknown"), ("unknown", "known")):
            for _ in range(2):
                for kind in order:
                    address = addresses[kind]
                    # R-03: bounded poll for the recipient's own message, not a single global
                    # snapshot — the reset mail is queued asynchronously and the response
                    # returns before delivery. Measuring the delta after a settled wait is
                    # what makes the count robust on a cold queue.
                    before = len(recipient_messages(keycloak_running, address))
                    status, text, elapsed = reset_response(public, address)
                    assert elapsed > 0
                    if kind == "known":
                        after = wait_for_recipient_message(keycloak_running, address, before)
                    else:
                        after = len(recipient_messages(keycloak_running, address))
                    series[kind].append(round(elapsed * 1000, 3))
                    statuses[kind].add(status)
                    texts[kind].add(text)
                    mail_counts[kind].append(after - before)
        assert statuses["known"] == statuses["unknown"]
        assert texts["known"] == texts["unknown"]
        assert mail_counts["known"] == [1, 1, 1, 1], (
            "each known-address request must deliver exactly one message (bounded poll)"
        )
        assert mail_counts["unknown"] == [0, 0, 0, 0], (
            "no unknown-address request may deliver a message"
        )
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
