from __future__ import annotations

import smtplib
import uuid
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailTransport(Protocol):
    def send(self, *, to: str, subject: str, body: str, headers: dict[str, str]) -> str:
        """Deliver the message and return a provider message id."""
        ...


class LogTransport:
    """Development transport: records the message in the log instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send(self, *, to: str, subject: str, body: str, headers: dict[str, str]) -> str:
        message_id = f"<{uuid.uuid4()}@log.bookflow.local>"
        self.sent.append({"to": to, "subject": subject, "body": body, "headers": headers})
        log.info("EMAIL (log transport) to=%s subject=%r id=%s", to, subject, message_id)
        return message_id


class SmtpTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, to: str, subject: str, body: str, headers: dict[str, str]) -> str:
        s = self.settings
        msg = EmailMessage()
        msg["From"] = f"{s.sender_name} <{s.sender_email}>"
        msg["To"] = to
        msg["Subject"] = subject
        message_id = f"<{uuid.uuid4()}@{s.sender_email.rsplit('@', 1)[-1]}>"
        msg["Message-ID"] = message_id
        for key, value in headers.items():
            msg[key] = value
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
        return message_id


_transport: EmailTransport | None = None


def set_transport(transport: EmailTransport | None) -> None:
    global _transport
    _transport = transport


def get_transport() -> EmailTransport:
    global _transport
    if _transport is None:
        settings = get_settings()
        _transport = (
            SmtpTransport(settings) if settings.email_transport == "smtp" else LogTransport()
        )
    return _transport
