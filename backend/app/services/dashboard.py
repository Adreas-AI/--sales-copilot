from __future__ import annotations

import statistics
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import Activity, EmailDraft, FollowUpSequence, FollowUpTask, Job, Lead
from app.domain.enums import (
    ActivityKind,
    DraftStatus,
    SequenceStatus,
    TaskStatus,
)
from app.schemas.workflow import SummaryOut
from app.services import followups
from app.services.leads import unanswered_leads


def _count(session: Session, stmt) -> int:
    return session.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _grouped(session: Session, column) -> dict[str, int]:
    rows = session.execute(select(column, func.count()).group_by(column)).all()
    return {str(k): v for k, v in rows if k is not None}


def median_first_response_hours(session: Session, *, days: int = 30) -> float | None:
    since = clock.utcnow() - timedelta(days=days)
    first_out = (
        select(Activity.lead_id, func.min(Activity.occurred_at).label("first_at"))
        .where(Activity.kind == ActivityKind.OUTBOUND_EMAIL)
        .group_by(Activity.lead_id)
        .subquery()
    )
    rows = session.execute(
        select(Lead.created_at, first_out.c.first_at)
        .join(first_out, first_out.c.lead_id == Lead.id)
        .where(Lead.created_at >= since)
    ).all()
    # func.min keeps the column type, so both values come back as aware UTC datetimes.
    hours = [(first - created).total_seconds() / 3600 for created, first in rows]
    return round(statistics.median(hours), 1) if hours else None


def summary(session: Session) -> SummaryOut:
    now = clock.utcnow()
    return SummaryOut(
        total_leads=_count(session, select(Lead.id)),
        new_last_7_days=_count(
            session, select(Lead.id).where(Lead.created_at >= now - timedelta(days=7))
        ),
        by_temperature=_grouped(session, Lead.temperature),
        by_stage=_grouped(session, Lead.stage),
        drafts_pending_review=_count(
            session, select(EmailDraft.id).where(EmailDraft.status == DraftStatus.PENDING_REVIEW)
        ),
        drafts_approved_unsent=_count(
            session, select(EmailDraft.id).where(EmailDraft.status == DraftStatus.APPROVED)
        ),
        active_sequences=_count(
            session,
            select(FollowUpSequence.id).where(FollowUpSequence.status == SequenceStatus.ACTIVE),
        ),
        followups_due_24h=_count(
            session,
            select(FollowUpTask.id).where(
                FollowUpTask.status == TaskStatus.SCHEDULED,
                FollowUpTask.due_at <= now + timedelta(hours=24),
            ),
        ),
        overdue_drafts=len(followups.overdue(session).drafts),
        needs_review=_count(session, select(Lead.id).where(Lead.needs_review.is_(True))),
        unanswered=len(unanswered_leads(session)),
        median_first_response_hours=median_first_response_hours(session),
        jobs=_grouped(session, Job.status),
        ai_enabled=get_settings().ai_configured,
    )
