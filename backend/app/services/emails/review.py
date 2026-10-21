"""Human review of drafts: edit, approve, reject, send."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.security import make_unsubscribe_token
from app.db.models import EmailDraft
from app.domain.enums import ActivityKind, Direction, DraftStatus, PipelineStage
from app.services.activities import record_activity
from app.services.contact_policy import check_email_contact
from app.services.emails import guardrails
from app.services.emails.context import build_context
from app.services.emails.transport import get_transport
from app.services.errors import ContactNotAllowedError, InvalidStateError, NotFoundError


def get_draft(session: Session, draft_id: uuid.UUID, *, for_update: bool = False) -> EmailDraft:
    stmt = select(EmailDraft).where(EmailDraft.id == draft_id)
    if for_update:
        stmt = stmt.with_for_update()
    draft = session.scalar(stmt)
    if draft is None:
        raise NotFoundError("Draft not found")
    return draft


def _require(draft: EmailDraft, *allowed: DraftStatus) -> None:
    if draft.status not in allowed:
        raise InvalidStateError(
            f"Draft is {draft.status}; expected {' or '.join(allowed)}",
            details={"status": draft.status},
        )


def edit_draft(
    session: Session, draft_id: uuid.UUID, *, subject: str | None, body: str | None, editor: str
) -> EmailDraft:
    draft = get_draft(session, draft_id, for_update=True)
    _require(draft, DraftStatus.PENDING_REVIEW, DraftStatus.APPROVED)
    if subject is not None:
        draft.subject = subject.strip()
    if body is not None:
        draft.body = body.strip()
    # An edit invalidates a previous approval.
    draft.status = DraftStatus.PENDING_REVIEW
    draft.reviewed_by = None
    draft.reviewed_at = None
    ctx = build_context(session, draft.lead, draft.kind, instructions=draft.instructions)
    draft.guardrail_warnings = [
        str(i) for i in guardrails.check(draft.subject, draft.body, facts_text=ctx.facts_text())
    ]
    draft.review_note = f"Edited by {editor}"
    return draft


def approve_draft(
    session: Session, draft_id: uuid.UUID, *, reviewer: str, note: str | None = None
) -> EmailDraft:
    draft = get_draft(session, draft_id, for_update=True)
    _require(draft, DraftStatus.PENDING_REVIEW)
    errors = [w for w in draft.guardrail_warnings if w.startswith("error:")]
    if errors:
        raise InvalidStateError("Fix guardrail errors before approving", details={"errors": errors})
    draft.status = DraftStatus.APPROVED
    draft.reviewed_by = reviewer
    draft.reviewed_at = clock.utcnow()
    draft.review_note = note
    return draft


def reject_draft(
    session: Session, draft_id: uuid.UUID, *, reviewer: str, note: str | None = None
) -> EmailDraft:
    draft = get_draft(session, draft_id, for_update=True)
    _require(draft, DraftStatus.PENDING_REVIEW, DraftStatus.APPROVED)
    draft.status = DraftStatus.REJECTED
    draft.reviewed_by = reviewer
    draft.reviewed_at = clock.utcnow()
    draft.review_note = note
    return draft


def unsubscribe_url(email: str) -> str:
    s = get_settings()
    token = make_unsubscribe_token(s.unsubscribe_secret, email)
    return f"{s.public_base_url.rstrip('/')}/unsubscribe?token={token}"


def send_draft(session: Session, draft_id: uuid.UUID, *, sender: str) -> EmailDraft:
    """Send an approved draft. Contact policy is checked again right before sending."""
    draft = get_draft(session, draft_id, for_update=True)
    _require(draft, DraftStatus.APPROVED)
    lead = draft.lead
    decision = check_email_contact(session, lead, draft.kind)
    if not decision.allowed:
        draft.status = DraftStatus.CANCELLED
        draft.review_note = "Cancelled at send time: " + ", ".join(decision.reasons)
        session.flush()
        raise ContactNotAllowedError(decision.reasons)

    link = unsubscribe_url(lead.email)
    body = f"{draft.body}\n\n--\nDon't want to hear from us? Unsubscribe: {link}"
    message_id = get_transport().send(
        to=lead.email,
        subject=draft.subject,
        body=body,
        headers={
            "List-Unsubscribe": f"<{link}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    now = clock.utcnow()
    draft.status = DraftStatus.SENT
    draft.sent_at = now
    draft.transport_message_id = message_id
    lead.last_outbound_at = now
    if lead.stage == PipelineStage.NEW:
        lead.stage = PipelineStage.CONTACTED
    record_activity(
        session,
        lead,
        ActivityKind.OUTBOUND_EMAIL,
        direction=Direction.OUTBOUND,
        actor=sender,
        subject=draft.subject,
        body=draft.body,
        occurred_at=now,
        external_message_id=message_id,
        meta={"draft_id": str(draft.id), "kind": draft.kind, "approved_by": draft.reviewed_by},
    )
    return draft
