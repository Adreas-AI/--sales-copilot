from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import Lead
from app.domain.enums import (
    SEQUENCE_STOP_STAGES,
    ActivityKind,
    Direction,
    LeadSource,
    PipelineStage,
    StopReason,
)
from app.jobs import queue
from app.schemas.leads import LeadCreate, LeadUpdate
from app.services import followups
from app.services.activities import record_activity
from app.services.errors import NotFoundError

QUALIFY_JOB = "qualify_lead"


@dataclass
class IntakeResult:
    lead: Lead
    created: bool
    duplicate_of: str | None = None  # "external_id" | "email"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_lead(session: Session, lead_id: uuid.UUID) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError("Lead not found")
    return lead


def _clean_interests(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        v = v.strip().lower()
        if v and v not in seen:
            seen.append(v)
    return seen


def _merge_into(existing: Lead, data: LeadCreate) -> list[str]:
    """Fill gaps on an existing lead from a new submission. Never overwrites known values."""
    filled = []
    for field in ("phone", "website", "locations_count", "company_size"):
        new = getattr(data, field)
        if getattr(existing, field) in (None, "") and new not in (None, ""):
            setattr(existing, field, new)
            filled.append(field)
    if existing.business_category == "other" and data.business_category != "other":
        existing.business_category = data.business_category
        filled.append("business_category")
    interests = _clean_interests(list(existing.product_interest or []) + data.product_interest)
    if interests != list(existing.product_interest or []):
        existing.product_interest = interests
        filled.append("product_interest")
    # Consent can be granted by a new submission; withdrawing it goes through
    # unsubscribe / preferences, never by omission on a form.
    now = clock.utcnow()
    if data.consent.email and not existing.consent_email and existing.unsubscribed_at is None:
        existing.consent_email = True
        existing.consent_captured_at = now
        existing.consent_source = data.consent.source_text
        filled.append("consent_email")
    if (
        data.consent.marketing
        and not existing.consent_marketing
        and existing.unsubscribed_at is None
    ):
        existing.consent_marketing = True
        filled.append("consent_marketing")
    return filled


def intake_lead(session: Session, data: LeadCreate, *, actor: str = "system") -> IntakeResult:
    now = clock.utcnow()
    if data.external_id:
        replay = session.scalar(
            select(Lead).where(Lead.source == data.source, Lead.external_id == data.external_id)
        )
        if replay is not None:
            return IntakeResult(replay, created=False, duplicate_of="external_id")

    email = normalize_email(data.email)
    existing = session.scalar(select(Lead).where(Lead.email == email))
    if existing is not None:
        filled = _merge_into(existing, data)
        activity = record_activity(
            session,
            existing,
            ActivityKind.INQUIRY,
            direction=Direction.INBOUND,
            actor="prospect",
            subject=f"Repeat inquiry via {data.source.replace('_', ' ')}",
            body=data.message,
            occurred_at=now,
            meta={"source": data.source, "filled_fields": filled},
        )
        existing.last_inbound_at = now
        followups.stop_active_sequence(session, existing, StopReason.PROSPECT_REPLIED)
        session.flush()
        queue.enqueue(
            session,
            QUALIFY_JOB,
            {"lead_id": str(existing.id), "reason": "repeat_inquiry"},
            idempotency_key=f"qualify:{existing.id}:inquiry:{activity.id}",
        )
        return IntakeResult(existing, created=False, duplicate_of="email")

    lead = Lead(
        business_name=data.business_name.strip(),
        contact_name=data.contact_name.strip(),
        email=email,
        phone=data.phone,
        website=data.website,
        business_category=data.business_category,
        locations_count=data.locations_count,
        company_size=data.company_size,
        product_interest=_clean_interests(data.product_interest),
        message=(data.message or "").strip() or None,
        source=data.source,
        source_detail=data.source_detail,
        external_id=data.external_id,
        owner=data.owner,
        stage=PipelineStage.TRIAL if data.source == LeadSource.FREE_TRIAL else PipelineStage.NEW,
        consent_email=data.consent.email,
        consent_marketing=data.consent.marketing,
        consent_captured_at=now if (data.consent.email or data.consent.marketing) else None,
        consent_source=data.consent.source_text,
        preferred_channel=data.preferred_channel,
        last_inbound_at=now,
        created_at=now,
    )
    session.add(lead)
    session.flush()
    record_activity(
        session,
        lead,
        ActivityKind.INQUIRY,
        direction=Direction.INBOUND,
        actor="prospect" if data.source != LeadSource.MANUAL else actor,
        subject=f"New {data.source.replace('_', ' ')}",
        body=lead.message,
        occurred_at=now,
        meta={"source": data.source, "source_detail": data.source_detail},
    )
    queue.enqueue(
        session,
        QUALIFY_JOB,
        {"lead_id": str(lead.id), "reason": "intake"},
        idempotency_key=f"qualify:{lead.id}:intake",
    )
    return IntakeResult(lead, created=True)


def update_lead(session: Session, lead: Lead, data: LeadUpdate, *, actor: str) -> Lead:
    changes = data.model_dump(exclude_unset=True)
    if "stage" in changes and changes["stage"] != lead.stage:
        old = lead.stage
        lead.stage = changes.pop("stage")
        record_activity(
            session,
            lead,
            ActivityKind.STAGE_CHANGE,
            actor=actor,
            body=f"Stage changed from {old} to {lead.stage}",
            meta={"from": old, "to": lead.stage},
        )
        if lead.stage in SEQUENCE_STOP_STAGES:
            followups.stop_active_sequence(
                session, lead, f"{StopReason.STAGE_CHANGED}:{lead.stage}", actor=actor
            )
    else:
        changes.pop("stage", None)

    if changes.get("consent_email") is False and lead.consent_email:
        followups.stop_active_sequence(session, lead, StopReason.CONSENT_WITHDRAWN, actor=actor)
        followups.cancel_open_drafts(session, lead, reason="email consent withdrawn")
    if changes.get("do_not_contact") is True and not lead.do_not_contact:
        followups.stop_active_sequence(session, lead, StopReason.UNSUBSCRIBED, actor=actor)
        followups.cancel_open_drafts(session, lead, reason="marked do-not-contact")
    if changes.get("consent_email") is True and not lead.consent_email:
        lead.consent_captured_at = clock.utcnow()
    if changes.get("needs_review") is False:
        lead.review_reason = None
    if "objections" in changes:
        changes["objections"] = sorted(set(changes["objections"]))
    for key, value in changes.items():
        setattr(lead, key, value)
    return lead


def list_leads(
    session: Session,
    *,
    temperature: str | None = None,
    stage: str | None = None,
    source: str | None = None,
    needs_review: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Lead], int]:
    stmt = select(Lead)
    if temperature:
        stmt = stmt.where(Lead.temperature == temperature)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if source:
        stmt = stmt.where(Lead.source == source)
    if needs_review is not None:
        stmt = stmt.where(Lead.needs_review.is_(needs_review))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Lead.business_name).like(like),
                func.lower(Lead.contact_name).like(like),
                Lead.email.like(like),
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total


def unanswered_leads(session: Session) -> list[Lead]:
    """Prospects who wrote to us (inquiry or reply) and haven't heard back yet."""
    cutoff = clock.utcnow() - timedelta(hours=get_settings().unanswered_after_hours)
    return list(
        session.scalars(
            select(Lead)
            .where(
                Lead.last_inbound_at.is_not(None),
                Lead.last_inbound_at < cutoff,
                or_(Lead.last_outbound_at.is_(None), Lead.last_outbound_at < Lead.last_inbound_at),
                Lead.do_not_contact.is_(False),
                Lead.unsubscribed_at.is_(None),
                Lead.stage.not_in([PipelineStage.WON, PipelineStage.LOST]),
            )
            .order_by(Lead.last_inbound_at)
        )
    )
