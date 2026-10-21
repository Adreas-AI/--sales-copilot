"""Creates email drafts. Every draft starts as ``pending_review``; nothing is sent here."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import EmailDraft, Lead
from app.domain.enums import ActivityKind, Direction, DraftStatus, EmailKind
from app.llm.client import LLMClient, LLMError
from app.services.activities import record_activity
from app.services.contact_policy import check_email_contact
from app.services.emails import ai_writer, guardrails, templates
from app.services.emails.context import build_context
from app.services.errors import ContactNotAllowedError

log = get_logger(__name__)


def generate_draft(
    session: Session,
    lead: Lead,
    kind: EmailKind,
    *,
    llm: LLMClient | None,
    step: int | None = None,
    total_steps: int | None = None,
    sequence_id: uuid.UUID | None = None,
    instructions: str | None = None,
    created_by: str = "system",
) -> EmailDraft:
    decision = check_email_contact(session, lead, kind)
    if not decision.allowed:
        raise ContactNotAllowedError(decision.reasons)

    ctx = build_context(
        session, lead, kind, step=step, total_steps=total_steps, instructions=instructions
    )
    warnings: list[str] = []
    generated_by, model = "template", None
    subject = body = ""
    issues: list[guardrails.Issue] = []

    if llm is not None:
        try:
            subject, body, issues = ai_writer.write(llm, ctx)
            generated_by, model = "ai", llm.model
        except LLMError as exc:
            log.warning("AI email unavailable for lead %s, using template: %s", lead.id, exc)
            warnings.append(f"AI draft not used ({exc}); template used instead")

    if generated_by == "template":
        subject, body = templates.render(ctx)
        issues = guardrails.check(subject, body, facts_text=ctx.facts_text())

    warnings.extend(str(i) for i in issues)
    draft = EmailDraft(
        lead=lead,
        kind=kind,
        subject=subject,
        body=body,
        status=DraftStatus.PENDING_REVIEW,
        generated_by=generated_by,
        model=model,
        guardrail_warnings=warnings,
        context_snapshot={"prompt_version": ai_writer.PROMPT_VERSION, **ctx.snapshot()},
        instructions=instructions,
        sequence_id=sequence_id,
        followup_step=step if sequence_id else None,
        created_by=created_by,
    )
    session.add(draft)
    session.flush()
    record_activity(
        session,
        lead,
        ActivityKind.DRAFT_CREATED,
        direction=Direction.INTERNAL,
        actor=created_by,
        subject=subject,
        body=f"{kind.replace('_', ' ').capitalize()} draft ready for review ({generated_by}).",
        meta={"draft_id": str(draft.id), "kind": kind, "step": step},
    )
    return draft


def initial_kind_for(lead: Lead) -> EmailKind:
    return (
        EmailKind.DEMO_INVITATION if lead.source == "demo_request" else EmailKind.INITIAL_RESPONSE
    )
