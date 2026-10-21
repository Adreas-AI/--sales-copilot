from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import clock
from app.db.base import Base
from app.domain.enums import (
    ContactChannel,
    DraftStatus,
    JobStatus,
    PipelineStage,
    SequenceStatus,
    TaskStatus,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=clock.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=clock.utcnow, onupdate=clock.utcnow)


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    business_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(300))
    business_category: Mapped[str] = mapped_column(String(32))
    locations_count: Mapped[int | None] = mapped_column(Integer)
    company_size: Mapped[str | None] = mapped_column(String(16))
    product_interest: Mapped[list[str]] = mapped_column(default=list)
    message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(String(32), index=True)
    source_detail: Mapped[str | None] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(200))

    stage: Mapped[str] = mapped_column(String(32), default=PipelineStage.NEW, index=True)
    owner: Mapped[str | None] = mapped_column(String(100))
    objections: Mapped[list[str]] = mapped_column(default=list)

    # Consent & communication preferences
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_captured_at: Mapped[datetime | None]
    consent_source: Mapped[str | None] = mapped_column(String(200))
    preferred_channel: Mapped[str] = mapped_column(String(16), default=ContactChannel.EMAIL)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    unsubscribed_at: Mapped[datetime | None]

    # Denormalised from the latest qualification for fast filtering
    score: Mapped[int | None] = mapped_column(Integer)
    temperature: Mapped[str | None] = mapped_column(String(8), index=True)
    qualified_at: Mapped[datetime | None]

    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(300))

    last_inbound_at: Mapped[datetime | None]
    last_outbound_at: Mapped[datetime | None]

    activities: Mapped[list[Activity]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Activity.occurred_at"
    )
    qualifications: Mapped[list[Qualification]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Qualification.created_at"
    )
    drafts: Mapped[list[EmailDraft]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="EmailDraft.created_at"
    )
    sequences: Mapped[list[FollowUpSequence]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="FollowUpSequence.started_at"
    )

    @property
    def first_name(self) -> str | None:
        parts = self.contact_name.split()
        return parts[0] if parts else None

    @property
    def email_domain(self) -> str:
        return self.email.rsplit("@", 1)[-1]


class Activity(Base):
    """One entry in a lead's timeline: messages, notes, system events."""

    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(100))
    # Message-ID of inbound/outbound email, used to ignore duplicate deliveries.
    external_message_id: Mapped[str | None] = mapped_column(String(300), unique=True)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    occurred_at: Mapped[datetime] = mapped_column(default=clock.utcnow)

    lead: Mapped[Lead] = relationship(back_populates="activities")

    __table_args__ = (Index("ix_activities_lead_occurred", "lead_id", "occurred_at"),)


class Qualification(Base):
    __tablename__ = "qualifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    temperature: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)
    rule_score: Mapped[int] = mapped_column(Integer)
    ai_adjustment: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))  # "rules" or "rules+ai"
    model: Mapped[str | None] = mapped_column(String(100))
    factors: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    signals: Mapped[list[str]] = mapped_column(default=list)
    missing_information: Mapped[list[str]] = mapped_column(default=list)
    detected_objections: Mapped[list[str]] = mapped_column(default=list)
    ai_evidence: Mapped[list[str]] = mapped_column(default=list)
    reasoning: Mapped[str] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(default=clock.utcnow)

    lead: Mapped[Lead] = relationship(back_populates="qualifications")


class EmailDraft(TimestampMixin, Base):
    __tablename__ = "email_drafts"
    # One draft per follow-up step: the database itself refuses duplicates.
    __table_args__ = (
        UniqueConstraint("sequence_id", "followup_step"),
        Index("ix_email_drafts_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=DraftStatus.PENDING_REVIEW)
    generated_by: Mapped[str] = mapped_column(String(16))  # "template" or "ai"
    model: Mapped[str | None] = mapped_column(String(100))
    guardrail_warnings: Mapped[list[str]] = mapped_column(default=list)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(default=dict)
    instructions: Mapped[str | None] = mapped_column(Text)

    sequence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("followup_sequences.id", ondelete="SET NULL")
    )
    followup_step: Mapped[int | None] = mapped_column(Integer)

    created_by: Mapped[str] = mapped_column(String(100), default="system")
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None]
    transport_message_id: Mapped[str | None] = mapped_column(String(300))

    lead: Mapped[Lead] = relationship(back_populates="drafts")


class FollowUpSequence(Base):
    __tablename__ = "followup_sequences"
    __table_args__ = (
        # At most one active sequence per lead, enforced by the database.
        Index(
            "uq_followup_sequences_one_active",
            "lead_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=SequenceStatus.ACTIVE)
    # Day 0 of the cadence (normally when the lead came in).
    anchor_at: Mapped[datetime]
    # When the sequence was actually created; replies after this stop it.
    started_at: Mapped[datetime] = mapped_column(default=clock.utcnow)
    # Snapshot of the cadence in force at start, so config changes don't
    # reshuffle sequences that are already running.
    cadence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(64))
    stopped_at: Mapped[datetime | None]

    lead: Mapped[Lead] = relationship(back_populates="sequences")
    tasks: Mapped[list[FollowUpTask]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan", order_by="FollowUpTask.step"
    )


class FollowUpTask(Base):
    __tablename__ = "followup_tasks"
    __table_args__ = (
        UniqueConstraint("sequence_id", "step"),
        Index("ix_followup_tasks_status_due", "status", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("followup_sequences.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    due_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.SCHEDULED)
    outcome: Mapped[str | None] = mapped_column(String(300))
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_drafts.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=clock.utcnow)

    sequence: Mapped[FollowUpSequence] = relationship(back_populates="tasks")
    lead: Mapped[Lead] = relationship()


class SuppressionEntry(Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("kind", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16))  # "email" or "domain"
    value: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=clock.utcnow)


class Job(Base):
    """A unit of background work. The table *is* the queue."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_at", "status", "run_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    # Enqueueing the same logical work twice returns the existing job.
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    run_at: Mapped[datetime] = mapped_column(default=clock.utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=clock.utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
