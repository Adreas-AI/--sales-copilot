"""HMAC helpers for webhook signatures and unsubscribe links."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from datetime import datetime

SIGNATURE_PREFIX = "sha256="


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """Signature over ``"{timestamp}." + body``; binding the timestamp prevents replays."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return SIGNATURE_PREFIX + mac.hexdigest()


def verify_webhook(
    secret: str,
    *,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: datetime,
    tolerance_seconds: int,
) -> bool:
    if not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(now.timestamp() - sent_at) > tolerance_seconds:
        return False
    return hmac.compare_digest(sign_webhook(secret, timestamp, body), signature)


def _email_mac(secret: str, email: str) -> str:
    return hmac.new(secret.encode(), email.encode(), hashlib.sha256).hexdigest()[:32]


def make_unsubscribe_token(secret: str, email: str) -> str:
    email = email.strip().lower()
    encoded = base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
    return f"{encoded}.{_email_mac(secret, email)}"


def read_unsubscribe_token(secret: str, token: str) -> str | None:
    """Return the email the token was issued for, or ``None`` if it is not authentic."""
    encoded, _, mac = token.partition(".")
    if not encoded or not mac:
        return None
    try:
        email = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(_email_mac(secret, email), mac):
        return None
    return email
