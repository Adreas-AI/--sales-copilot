"""The single place that decides whether a lead may be emailed.

Checked when a draft is generated, again when a follow-up step runs, and once more
at the moment of sending, so a suppression added in between always wins.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Lead
from app.domain.enums import MARKETING_EMAIL_KINDS, EmailKind
from app.services.suppression import find_suppression


@dataclass(frozen=True)
class ContactDecision:
    allowed: bool
    reasons: tuple[str, ...]


def check_email_contact(
    session: Session, lead: Lead, kind: EmailKind | None = None
) -> ContactDecision:
    reasons: list[str] = []
    if lead.unsubscribed_at is not None:
        reasons.append("unsubscribed")
    if lead.do_not_contact:
        reasons.append("do_not_contact")
    if not lead.consent_email:
        reasons.append("no_email_consent")
    if kind in MARKETING_EMAIL_KINDS and not lead.consent_marketing:
        reasons.append("no_marketing_consent")
    entry = find_suppression(session, lead.email)
    if entry is not None:
        reasons.append(f"suppressed_{entry.kind}:{entry.reason}")
    return ContactDecision(allowed=not reasons, reasons=tuple(reasons))
