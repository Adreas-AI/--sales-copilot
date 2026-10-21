"""Job handlers. Each one is idempotent: running it twice has the same effect as once."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EmailDraft, Lead
from app.domain.enums import ContactChannel
from app.jobs import queue
from app.llm import provider
from app.services import followups
from app.services.contact_policy import check_email_contact
from app.services.emails.generator import generate_draft, initial_kind_for
from app.services.qualification.engine import qualify_lead
from app.services.qualification.signals import NON_BUYER

PREPARE_OUTREACH_JOB = "prepare_initial_outreach"


def _lead(session: Session, payload: dict[str, Any]) -> Lead | None:
    return session.get(Lead, uuid.UUID(payload["lead_id"]))


def handle_qualify_lead(session: Session, payload: dict[str, Any]) -> None:
    lead = _lead(session, payload)
    if lead is None:
        return
    qualify_lead(session, lead, llm=provider.get_llm())
    if payload.get("reason") == "intake":
        queue.enqueue(
            session,
            PREPARE_OUTREACH_JOB,
            {"lead_id": str(lead.id)},
            idempotency_key=f"initial-outreach:{lead.id}",
        )


def handle_prepare_initial_outreach(session: Session, payload: dict[str, Any]) -> None:
    """Day 0: draft the first response and schedule the follow-up sequence."""
    lead = _lead(session, payload)
    if lead is None:
        return

    if lead.preferred_channel == ContactChannel.PHONE:
        followups.flag_for_review(session, lead, "Prefers phone contact; call them back")
        return
    decision = check_email_contact(session, lead)
    if not decision.allowed:
        followups.flag_for_review(
            session, lead, "Cannot email automatically: " + ", ".join(decision.reasons)
        )
        return
    if lead.message and NON_BUYER.search(lead.message):
        followups.flag_for_review(
            session, lead, "Looks like a vendor, job seeker or student; check before replying"
        )
        return

    already_drafted = session.scalar(select(exists().where(EmailDraft.lead_id == lead.id)))
    if not already_drafted:
        generate_draft(session, lead, initial_kind_for(lead), llm=provider.get_llm())

    if lead.temperature in get_settings().followup_temperatures:
        followups.start_sequence(session, lead, anchor_at=lead.created_at)


def handle_process_followup_task(session: Session, payload: dict[str, Any]) -> None:
    followups.process_task(session, uuid.UUID(payload["task_id"]), llm=provider.get_llm())


HANDLERS: dict[str, queue.Handler] = {
    "qualify_lead": handle_qualify_lead,
    PREPARE_OUTREACH_JOB: handle_prepare_initial_outreach,
    followups.PROCESS_TASK_JOB: handle_process_followup_task,
}
