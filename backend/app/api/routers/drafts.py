from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.db.models import EmailDraft
from app.domain.enums import DraftStatus
from app.schemas.workflow import DraftOut, DraftUpdate, DraftWithLead, ReviewAction
from app.services.emails import review
from app.services.errors import ContactNotAllowedError

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=list[DraftWithLead])
def list_drafts(
    session: SessionDep,
    status: DraftStatus | None = DraftStatus.PENDING_REVIEW,
    limit: int = Query(100, ge=1, le=500),
) -> list[DraftWithLead]:
    stmt = select(EmailDraft).options(selectinload(EmailDraft.lead))
    if status:
        stmt = stmt.where(EmailDraft.status == status)
    rows = session.scalars(stmt.order_by(EmailDraft.created_at).limit(limit))
    return [DraftWithLead.model_validate(d) for d in rows]


@router.get("/{draft_id}", response_model=DraftWithLead)
def get_draft(draft_id: uuid.UUID, session: SessionDep) -> DraftWithLead:
    return DraftWithLead.model_validate(review.get_draft(session, draft_id))


@router.patch("/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: uuid.UUID, data: DraftUpdate, session: SessionDep) -> DraftOut:
    draft = review.edit_draft(
        session, draft_id, subject=data.subject, body=data.body, editor=data.editor
    )
    session.commit()
    return DraftOut.model_validate(draft)


@router.post("/{draft_id}/approve", response_model=DraftOut)
def approve(draft_id: uuid.UUID, data: ReviewAction, session: SessionDep) -> DraftOut:
    draft = review.approve_draft(session, draft_id, reviewer=data.reviewer, note=data.note)
    session.commit()
    return DraftOut.model_validate(draft)


@router.post("/{draft_id}/reject", response_model=DraftOut)
def reject(draft_id: uuid.UUID, data: ReviewAction, session: SessionDep) -> DraftOut:
    draft = review.reject_draft(session, draft_id, reviewer=data.reviewer, note=data.note)
    session.commit()
    return DraftOut.model_validate(draft)


@router.post("/{draft_id}/send", response_model=DraftOut)
def send(draft_id: uuid.UUID, data: ReviewAction, session: SessionDep) -> DraftOut:
    try:
        draft = review.send_draft(session, draft_id, sender=data.reviewer)
    except ContactNotAllowedError:
        session.commit()  # persist the cancellation before reporting it
        raise
    session.commit()
    return DraftOut.model_validate(draft)
