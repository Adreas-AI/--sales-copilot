from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.deps import LLMDep, SessionDep
from app.db.models import Activity, Qualification
from app.domain.enums import ActivityKind, Direction, LeadSource, PipelineStage, Temperature
from app.schemas.leads import (
    ActivityCreate,
    ActivityOut,
    IntakeOut,
    LeadCreate,
    LeadOut,
    LeadPage,
    LeadUpdate,
)
from app.schemas.workflow import (
    DraftCreate,
    DraftOut,
    InboundReplyIn,
    InboundResultOut,
    LeadDetail,
    QualificationOut,
    SequenceOut,
)
from app.services import followups, leads
from app.services.activities import record_activity
from app.services.conversations import record_inbound_reply
from app.services.emails.generator import generate_draft
from app.services.errors import InvalidStateError
from app.services.qualification.engine import qualify_lead

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=IntakeOut, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, session: SessionDep, response: Response) -> IntakeOut:
    """Manual CRM entry (or any internal source). Duplicates by email are merged."""
    result = leads.intake_lead(session, data, actor=data.owner or "rep")
    session.commit()
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return IntakeOut(
        lead=LeadOut.model_validate(result.lead),
        created=result.created,
        duplicate_of=result.duplicate_of,
    )


@router.get("", response_model=LeadPage)
def list_leads(
    session: SessionDep,
    temperature: Temperature | None = None,
    stage: PipelineStage | None = None,
    source: LeadSource | None = None,
    needs_review: bool | None = None,
    q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> LeadPage:
    rows, total = leads.list_leads(
        session,
        temperature=temperature,
        stage=stage,
        source=source,
        needs_review=needs_review,
        q=q,
        limit=limit,
        offset=offset,
    )
    return LeadPage(
        items=[LeadOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/unanswered", response_model=list[LeadOut])
def unanswered(session: SessionDep) -> list[LeadOut]:
    return [LeadOut.model_validate(r) for r in leads.unanswered_leads(session)]


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: uuid.UUID, session: SessionDep) -> LeadDetail:
    lead = leads.get_lead(session, lead_id)
    latest = lead.qualifications[-1] if lead.qualifications else None
    return LeadDetail(
        lead=LeadOut.model_validate(lead),
        latest_qualification=QualificationOut.model_validate(latest) if latest else None,
        sequences=[SequenceOut.model_validate(s) for s in reversed(lead.sequences)],
        drafts=[DraftOut.model_validate(d) for d in reversed(lead.drafts)],
    )


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: uuid.UUID, data: LeadUpdate, session: SessionDep) -> LeadOut:
    lead = leads.get_lead(session, lead_id)
    leads.update_lead(session, lead, data, actor=data.owner or "rep")
    session.commit()
    return LeadOut.model_validate(lead)


@router.get("/{lead_id}/timeline", response_model=list[ActivityOut])
def timeline(lead_id: uuid.UUID, session: SessionDep) -> list[ActivityOut]:
    leads.get_lead(session, lead_id)
    rows = session.scalars(
        select(Activity).where(Activity.lead_id == lead_id).order_by(Activity.occurred_at.desc())
    )
    return [ActivityOut.model_validate(a) for a in rows]


@router.post("/{lead_id}/activities", response_model=ActivityOut, status_code=201)
def log_activity(lead_id: uuid.UUID, data: ActivityCreate, session: SessionDep) -> ActivityOut:
    """Log a note or call, or paste in a reply the prospect sent (which stops follow-ups)."""
    lead = leads.get_lead(session, lead_id)
    if data.kind == ActivityKind.INBOUND_EMAIL:
        activity = record_inbound_reply(
            session, lead, subject=data.subject, body=data.body, actor=data.actor
        ).activity
    else:
        activity = record_activity(
            session,
            lead,
            ActivityKind(data.kind),
            direction=Direction.INTERNAL,
            subject=data.subject,
            body=data.body,
            actor=data.actor,
        )
    session.commit()
    return ActivityOut.model_validate(activity)


@router.post("/{lead_id}/replies", response_model=InboundResultOut)
def record_reply(lead_id: uuid.UUID, data: InboundReplyIn, session: SessionDep) -> InboundResultOut:
    lead = leads.get_lead(session, lead_id)
    result = record_inbound_reply(
        session,
        lead,
        subject=data.subject,
        body=data.body,
        external_message_id=data.message_id,
        received_at=data.received_at,
    )
    session.commit()
    return InboundResultOut(
        lead_id=lead.id,
        matched=True,
        duplicate=result.duplicate,
        unsubscribed=result.unsubscribed,
        sequence_stopped=result.sequence_stopped,
    )


@router.post("/{lead_id}/qualify", response_model=QualificationOut)
def requalify(
    lead_id: uuid.UUID, session: SessionDep, llm: LLMDep, use_ai: bool = True
) -> QualificationOut:
    lead = leads.get_lead(session, lead_id)
    qualification = qualify_lead(session, lead, llm=llm if use_ai else None, actor="rep")
    session.commit()
    return QualificationOut.model_validate(qualification)


@router.get("/{lead_id}/qualifications", response_model=list[QualificationOut])
def qualification_history(lead_id: uuid.UUID, session: SessionDep) -> list[QualificationOut]:
    leads.get_lead(session, lead_id)
    rows = session.scalars(
        select(Qualification)
        .where(Qualification.lead_id == lead_id)
        .order_by(Qualification.created_at.desc())
    )
    return [QualificationOut.model_validate(q) for q in rows]


@router.post("/{lead_id}/drafts", response_model=DraftOut, status_code=201)
def create_draft(
    lead_id: uuid.UUID, data: DraftCreate, session: SessionDep, llm: LLMDep
) -> DraftOut:
    lead = leads.get_lead(session, lead_id)
    draft = generate_draft(
        session,
        lead,
        data.kind,
        llm=llm if data.use_ai else None,
        instructions=data.instructions,
        created_by=data.created_by,
    )
    session.commit()
    return DraftOut.model_validate(draft)


@router.post("/{lead_id}/sequence", response_model=SequenceOut, status_code=201)
def start_sequence(lead_id: uuid.UUID, session: SessionDep) -> SequenceOut:
    """Start (or restart) a follow-up sequence from today."""
    lead = leads.get_lead(session, lead_id)
    sequence = followups.start_sequence(session, lead, actor="rep")
    if sequence is None:
        session.commit()  # keep the review flag / activity explaining why
        raise InvalidStateError(
            "Sequence not started: lead prefers phone or cannot be emailed",
            details={"review_reason": lead.review_reason},
        )
    session.commit()
    return SequenceOut.model_validate(sequence)


@router.delete("/{lead_id}/sequence", response_model=SequenceOut | None)
def stop_sequence(lead_id: uuid.UUID, session: SessionDep) -> SequenceOut | None:
    lead = leads.get_lead(session, lead_id)
    sequence = followups.stop_active_sequence(session, lead, "manual", actor="rep")
    session.commit()
    return SequenceOut.model_validate(sequence) if sequence else None
