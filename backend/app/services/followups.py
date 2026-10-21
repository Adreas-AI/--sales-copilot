"""Follow-up engine.

A lead that came in on Day 0 gets a *sequence*: a fixed set of tasks due on the
configured days (default: drafts on Day 2 and Day 5, manual review on Day 10).
Tasks are rows, so the plan survives restarts and is visible in the dashboard.

Stopping is enforced twice:
* event-driven: a reply, unsubscribe, suppression or stage change stops the
  sequence immediately and cancels its open drafts;
* at execution: every task re-checks the stop conditions before doing anything,
  so a missed event can never produce an unwanted email.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import EmailDraft, FollowUpSequence, FollowUpTask, Lead
from app.domain.enums import (
    OPEN_DRAFT_STATUSES,
    SEQUENCE_STOP_STAGES,
    ActivityKind,
    ContactChannel,
    Direction,
    DraftStatus,
    EmailKind,
    SequenceStatus,
    StopReason,
    TaskAction,
    TaskStatus,
)
from app.jobs import queue
from app.llm.client import LLMClient
from app.services.activities import record_activity
from app.services.contact_policy import check_email_contact
from app.services.emails.generator import generate_draft

PROCESS_TASK_JOB = "process_followup_task"


def current_cadence() -> dict:
    s = get_settings()
    return {"step_days": list(s.followup_step_days), "manual_review_day": s.manual_review_day}


def active_sequence(session: Session, lead: Lead) -> FollowUpSequence | None:
    return session.scalar(
        select(FollowUpSequence).where(
            FollowUpSequence.lead_id == lead.id, FollowUpSequence.status == SequenceStatus.ACTIVE
        )
    )


def flag_for_review(session: Session, lead: Lead, reason: str) -> None:
    lead.needs_review = True
    lead.review_reason = reason[:300]
    record_activity(
        session, lead, ActivityKind.MANUAL_REVIEW, direction=Direction.INTERNAL, body=reason
    )


def start_sequence(
    session: Session, lead: Lead, *, anchor_at: datetime | None = None, actor: str = "system"
) -> FollowUpSequence | None:
    """Create the sequence and its tasks. Idempotent: returns the active one if present."""
    existing = active_sequence(session, lead)
    if existing is not None:
        return existing
    if lead.preferred_channel == ContactChannel.PHONE:
        flag_for_review(session, lead, "Prefers phone contact; no automated email follow-ups")
        return None
    if not check_email_contact(session, lead).allowed:
        return None

    now = clock.utcnow()
    anchor = anchor_at or now
    cadence = current_cadence()
    sequence = FollowUpSequence(
        lead=lead, status=SequenceStatus.ACTIVE, anchor_at=anchor, started_at=now, cadence=cadence
    )
    session.add(sequence)
    steps = [(day, TaskAction.FOLLOWUP_DRAFT) for day in cadence["step_days"]]
    steps.append((cadence["manual_review_day"], TaskAction.MANUAL_REVIEW))
    for index, (day, action) in enumerate(steps, start=1):
        session.add(
            FollowUpTask(
                sequence=sequence,
                lead=lead,
                step=index,
                day=day,
                action=action,
                due_at=anchor + timedelta(days=day),
                status=TaskStatus.SCHEDULED,
            )
        )
    days = ", ".join(f"Day {d}" for d in cadence["step_days"])
    record_activity(
        session,
        lead,
        ActivityKind.SEQUENCE,
        actor=actor,
        body=f"Follow-up sequence started: drafts on {days}; manual review on Day "
        f"{cadence['manual_review_day']}.",
    )
    session.flush()
    return sequence


def cancel_open_drafts(
    session: Session, lead: Lead, *, reason: str, sequence_id: uuid.UUID | None = None
) -> int:
    stmt = select(EmailDraft).where(
        EmailDraft.lead_id == lead.id, EmailDraft.status.in_(OPEN_DRAFT_STATUSES)
    )
    if sequence_id is not None:
        stmt = stmt.where(EmailDraft.sequence_id == sequence_id)
    drafts = list(session.scalars(stmt))
    for draft in drafts:
        draft.status = DraftStatus.CANCELLED
        draft.review_note = f"Auto-cancelled: {reason}"
    return len(drafts)


def stop_sequence(
    session: Session, sequence: FollowUpSequence, reason: StopReason | str, *, actor: str = "system"
) -> None:
    if sequence.status != SequenceStatus.ACTIVE:
        return
    now = clock.utcnow()
    sequence.status = SequenceStatus.STOPPED
    sequence.stop_reason = str(reason)
    sequence.stopped_at = now
    for task in sequence.tasks:
        if task.status == TaskStatus.SCHEDULED:
            task.status = TaskStatus.CANCELLED
            task.outcome = f"Sequence stopped: {reason}"
            task.completed_at = now
    cancelled = cancel_open_drafts(
        session, sequence.lead, reason=f"sequence stopped ({reason})", sequence_id=sequence.id
    )
    note = f" {cancelled} open follow-up draft(s) cancelled." if cancelled else ""
    record_activity(
        session,
        sequence.lead,
        ActivityKind.SEQUENCE,
        actor=actor,
        body=f"Follow-up sequence stopped: {str(reason).replace('_', ' ')}.{note}",
        meta={"sequence_id": str(sequence.id), "reason": str(reason)},
    )


def stop_active_sequence(
    session: Session, lead: Lead, reason: StopReason | str, *, actor: str = "system"
) -> FollowUpSequence | None:
    sequence = active_sequence(session, lead)
    if sequence is not None:
        stop_sequence(session, sequence, reason, actor=actor)
    return sequence


def stop_reason_for(session: Session, lead: Lead, sequence: FollowUpSequence) -> str | None:
    """Why this sequence must not continue, or ``None`` if it may."""
    if lead.last_inbound_at is not None and lead.last_inbound_at > sequence.started_at:
        return StopReason.PROSPECT_REPLIED
    if lead.unsubscribed_at is not None or lead.do_not_contact:
        return StopReason.UNSUBSCRIBED
    decision = check_email_contact(session, lead)
    if not decision.allowed:
        if any(r.startswith("suppressed") for r in decision.reasons):
            return StopReason.SUPPRESSED
        return StopReason.CONSENT_WITHDRAWN
    if lead.stage in SEQUENCE_STOP_STAGES:
        return f"{StopReason.STAGE_CHANGED}:{lead.stage}"
    return None


def enqueue_due_tasks(session: Session, *, limit: int = 500) -> int:
    """Turn due tasks into jobs. Safe to call any number of times."""
    due_ids = list(
        session.scalars(
            select(FollowUpTask.id)
            .where(
                FollowUpTask.status == TaskStatus.SCHEDULED, FollowUpTask.due_at <= clock.utcnow()
            )
            .order_by(FollowUpTask.due_at)
            .limit(limit)
        )
    )
    for task_id in due_ids:
        queue.enqueue(
            session,
            PROCESS_TASK_JOB,
            {"task_id": str(task_id)},
            idempotency_key=f"followup-task:{task_id}",
        )
    return len(due_ids)


@dataclass
class TaskResult:
    status: str
    outcome: str
    draft_id: uuid.UUID | None = None


def _finish(task: FollowUpTask, status: TaskStatus, outcome: str) -> TaskResult:
    task.status = status
    task.outcome = outcome[:300]
    task.completed_at = clock.utcnow()
    return TaskResult(status, outcome, task.draft_id)


def process_task(session: Session, task_id: uuid.UUID, *, llm: LLMClient | None) -> TaskResult:
    """Execute one follow-up task. Idempotent: only a ``scheduled`` task does anything."""
    task = session.scalar(select(FollowUpTask).where(FollowUpTask.id == task_id).with_for_update())
    if task is None:
        return TaskResult("missing", "Task not found")
    if task.status != TaskStatus.SCHEDULED:
        return TaskResult(task.status, f"Already {task.status}; nothing to do", task.draft_id)

    sequence, lead = task.sequence, task.lead
    if sequence.status != SequenceStatus.ACTIVE:
        return _finish(task, TaskStatus.CANCELLED, f"Sequence is {sequence.status}")

    if reason := stop_reason_for(session, lead, sequence):
        stop_sequence(session, sequence, reason)
        return TaskResult(TaskStatus.CANCELLED, f"Sequence stopped: {reason}")

    sequence.current_step = task.step

    if task.action == TaskAction.MANUAL_REVIEW:
        flag_for_review(
            session, lead, f"No reply {task.day} days after the inquiry; needs a personal decision"
        )
        sequence.status = SequenceStatus.COMPLETED
        sequence.stopped_at = clock.utcnow()
        return _finish(task, TaskStatus.COMPLETED, "Lead flagged for manual review")

    # Avoid stacking drafts: if an earlier email is still waiting for a human,
    # writing another follow-up on top of it would be noise.
    open_draft = session.scalar(
        select(EmailDraft.id).where(
            EmailDraft.lead_id == lead.id, EmailDraft.status.in_(OPEN_DRAFT_STATUSES)
        )
    )
    if open_draft is not None:
        task.draft_id = open_draft
        return _finish(
            task, TaskStatus.SKIPPED, "Previous draft is still awaiting review or sending"
        )

    total_draft_steps = len(sequence.cadence.get("step_days", []))
    draft = generate_draft(
        session,
        lead,
        EmailKind.FOLLOW_UP,
        llm=llm,
        step=task.step,
        total_steps=total_draft_steps,
        sequence_id=sequence.id,
    )
    task.draft_id = draft.id
    return _finish(task, TaskStatus.COMPLETED, f"Follow-up draft {task.step} prepared for review")


@dataclass
class OverdueReport:
    tasks: list[FollowUpTask]
    drafts: list[EmailDraft]


def overdue(session: Session, *, task_grace: timedelta = timedelta(hours=1)) -> OverdueReport:
    """Tasks the worker hasn't processed in time, and drafts waiting too long for a human."""
    now = clock.utcnow()
    sla = timedelta(hours=get_settings().draft_review_sla_hours)
    tasks = list(
        session.scalars(
            select(FollowUpTask)
            .where(
                FollowUpTask.status == TaskStatus.SCHEDULED, FollowUpTask.due_at < now - task_grace
            )
            .order_by(FollowUpTask.due_at)
        )
    )
    drafts = list(
        session.scalars(
            select(EmailDraft)
            .where(EmailDraft.status.in_(OPEN_DRAFT_STATUSES), EmailDraft.created_at < now - sla)
            .order_by(EmailDraft.created_at)
        )
    )
    return OverdueReport(tasks, drafts)
