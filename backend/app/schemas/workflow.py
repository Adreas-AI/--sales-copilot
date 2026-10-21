from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import EmailKind, SuppressionKind, SuppressionReason
from app.schemas.leads import LeadOut


class QualificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    score: int
    temperature: str
    confidence: float
    rule_score: int
    ai_adjustment: int | None
    method: str
    model: str | None
    factors: list[dict]
    signals: list[str]
    missing_information: list[str]
    detected_objections: list[str]
    ai_evidence: list[str]
    reasoning: str
    warnings: list[str]
    created_at: datetime


class DraftCreate(BaseModel):
    kind: EmailKind
    use_ai: bool = True
    instructions: str | None = Field(
        None,
        max_length=1000,
        description="Optional guidance from the rep, e.g. 'mention Saturday hours'",
    )
    created_by: str = Field("rep", max_length=100)


class DraftUpdate(BaseModel):
    subject: str | None = Field(None, min_length=1, max_length=300)
    body: str | None = Field(None, min_length=1, max_length=10_000)
    editor: str = Field("rep", max_length=100)


class ReviewAction(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    note: str | None = Field(None, max_length=1000)


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    kind: str
    subject: str
    body: str
    status: str
    generated_by: str
    model: str | None
    guardrail_warnings: list[str]
    instructions: str | None
    sequence_id: uuid.UUID | None
    followup_step: int | None
    created_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DraftWithLead(DraftOut):
    lead: LeadOut


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_id: uuid.UUID
    lead_id: uuid.UUID
    step: int
    day: int
    action: str
    due_at: datetime
    status: str
    outcome: str | None
    draft_id: uuid.UUID | None
    completed_at: datetime | None


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    status: str
    anchor_at: datetime
    started_at: datetime
    cadence: dict
    current_step: int
    stop_reason: str | None
    stopped_at: datetime | None
    tasks: list[TaskOut]


class LeadDetail(BaseModel):
    lead: LeadOut
    latest_qualification: QualificationOut | None
    sequences: list[SequenceOut]
    drafts: list[DraftOut]


class InboundReplyIn(BaseModel):
    subject: str | None = Field(None, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    message_id: str | None = Field(None, max_length=300)
    received_at: datetime | None = None


class InboundEmailWebhookIn(InboundReplyIn):
    from_email: EmailStr


class InboundResultOut(BaseModel):
    lead_id: uuid.UUID | None
    matched: bool
    duplicate: bool = False
    unsubscribed: bool = False
    sequence_stopped: bool = False


class CadenceOut(BaseModel):
    step_days: list[int]
    manual_review_day: int
    temperatures: list[str]
    draft_review_sla_hours: int


class OverdueOut(BaseModel):
    tasks: list[TaskOut]
    drafts: list[DraftOut]


class SuppressionIn(BaseModel):
    kind: SuppressionKind = SuppressionKind.EMAIL
    value: str = Field(min_length=3, max_length=320)
    reason: SuppressionReason = SuppressionReason.MANUAL
    note: str | None = Field(None, max_length=1000)


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    value: str
    reason: str
    source: str | None
    note: str | None
    created_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    payload: dict
    status: str
    idempotency_key: str | None
    run_at: datetime
    attempts: int
    max_attempts: int
    locked_by: str | None
    last_error: str | None
    created_at: datetime
    finished_at: datetime | None


class SummaryOut(BaseModel):
    total_leads: int
    new_last_7_days: int
    by_temperature: dict[str, int]
    by_stage: dict[str, int]
    drafts_pending_review: int
    drafts_approved_unsent: int
    active_sequences: int
    followups_due_24h: int
    overdue_drafts: int
    needs_review: int
    unanswered: int
    median_first_response_hours: float | None
    jobs: dict[str, int]
    ai_enabled: bool
