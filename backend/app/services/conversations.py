"""Inbound messages and opt-outs: the events that must stop automated outreach."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Activity, Lead
from app.domain.enums import (
    ActivityKind,
    Direction,
    PipelineStage,
    StopReason,
    SuppressionKind,
    SuppressionReason,
)
from app.jobs import queue
from app.services import followups
from app.services.activities import record_activity
from app.services.qualification.signals import detect_objections, wants_unsubscribe
from app.services.suppression import add_suppression


@dataclass
class InboundResult:
    activity: Activity
    duplicate: bool
    unsubscribed: bool = False
    sequence_stopped: bool = False


def record_inbound_reply(
    session: Session,
    lead: Lead,
    *,
    subject: str | None,
    body: str,
    external_message_id: str | None = None,
    received_at: datetime | None = None,
    actor: str = "prospect",
) -> InboundResult:
    if external_message_id:
        seen = session.scalar(
            select(Activity).where(Activity.external_message_id == external_message_id)
        )
        if seen is not None:
            return InboundResult(seen, duplicate=True)

    at = received_at or clock.utcnow()
    activity = record_activity(
        session,
        lead,
        ActivityKind.INBOUND_EMAIL,
        direction=Direction.INBOUND,
        actor=actor,
        subject=subject,
        body=body,
        occurred_at=at,
        external_message_id=external_message_id,
    )
    if lead.last_inbound_at is None or at > lead.last_inbound_at:
        lead.last_inbound_at = at

    if wants_unsubscribe(body):
        unsubscribe_lead(session, lead, source="reply")
        session.flush()
        return InboundResult(activity, duplicate=False, unsubscribed=True, sequence_stopped=True)

    stopped = followups.stop_active_sequence(session, lead, StopReason.PROSPECT_REPLIED)
    # Their reply supersedes queued follow-ups; the rep answers it personally.
    followups.cancel_open_drafts(session, lead, reason="prospect replied")
    found = {o.value for o in detect_objections(body)}
    if found:
        lead.objections = sorted(set(lead.objections or []) | found)
    if lead.stage in (PipelineStage.NEW, PipelineStage.CONTACTED):
        lead.stage = PipelineStage.ENGAGED
    session.flush()
    queue.enqueue(
        session,
        "qualify_lead",
        {"lead_id": str(lead.id), "reason": "reply"},
        idempotency_key=f"qualify:{lead.id}:reply:{activity.id}",
    )
    return InboundResult(activity, duplicate=False, sequence_stopped=stopped is not None)


def unsubscribe_lead(session: Session, lead: Lead, *, source: str) -> None:
    if lead.unsubscribed_at is None:
        lead.unsubscribed_at = clock.utcnow()
        record_activity(
            session,
            lead,
            ActivityKind.UNSUBSCRIBED,
            direction=Direction.INBOUND,
            actor="prospect",
            body=f"Unsubscribed via {source}. All outreach stopped.",
        )
    lead.do_not_contact = True
    lead.consent_marketing = False
    followups.stop_active_sequence(session, lead, StopReason.UNSUBSCRIBED)
    followups.cancel_open_drafts(session, lead, reason="unsubscribed")
    add_suppression(
        session,
        kind=SuppressionKind.EMAIL,
        value=lead.email,
        reason=SuppressionReason.UNSUBSCRIBE,
        source=source,
    )


def unsubscribe_email(session: Session, email: str, *, source: str) -> Lead | None:
    """Honour an unsubscribe even for addresses we have no lead for."""
    email = email.strip().lower()
    lead = session.scalar(select(Lead).where(Lead.email == email))
    if lead is not None:
        unsubscribe_lead(session, lead, source=source)
    else:
        add_suppression(
            session,
            kind=SuppressionKind.EMAIL,
            value=email,
            reason=SuppressionReason.UNSUBSCRIBE,
            source=source,
        )
    return lead
