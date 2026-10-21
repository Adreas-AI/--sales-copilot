from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    make_unsubscribe_token,
    read_unsubscribe_token,
    sign_webhook,
    verify_webhook,
)

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def test_webhook_signature_roundtrip() -> None:
    ts = str(int(NOW.timestamp()))
    sig = sign_webhook("s3cret", ts, b'{"a":1}')
    ok = dict(timestamp=ts, signature=sig, body=b'{"a":1}', now=NOW, tolerance_seconds=300)
    assert verify_webhook("s3cret", **ok)
    assert not verify_webhook("other", **ok)
    assert not verify_webhook("s3cret", **{**ok, "body": b'{"a":2}'})
    assert not verify_webhook("s3cret", **{**ok, "signature": None})


def test_webhook_rejects_stale_timestamps() -> None:
    ts = str(int((NOW - timedelta(minutes=10)).timestamp()))
    sig = sign_webhook("s3cret", ts, b"{}")
    assert not verify_webhook(
        "s3cret", timestamp=ts, signature=sig, body=b"{}", now=NOW, tolerance_seconds=300
    )


def test_unsubscribe_token_roundtrip_and_tamper() -> None:
    token = make_unsubscribe_token("k", "Sam@Example.com")
    assert read_unsubscribe_token("k", token) == "sam@example.com"
    assert read_unsubscribe_token("other-key", token) is None
    encoded, mac = token.split(".")
    forged = make_unsubscribe_token("k", "victim@example.com").split(".")[0] + "." + mac
    assert read_unsubscribe_token("k", forged) is None
    assert read_unsubscribe_token("k", "garbage") is None


def test_cadence_parses_csv_and_validates() -> None:
    s = Settings(followup_step_days="1,3,7", manual_review_day=14, followup_temperatures="hot")
    assert s.followup_step_days == [1, 3, 7]
    assert s.followup_temperatures == ["hot"]
    with pytest.raises(ValidationError):
        Settings(followup_step_days="5,2")
    with pytest.raises(ValidationError):
        Settings(followup_step_days="2,5", manual_review_day=5)
    with pytest.raises(ValidationError):
        Settings(hot_threshold=30, warm_threshold=40)
