"""Follow-ups, suppression list, jobs and the dashboard summary."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.db.models import FollowUpTask, Job, SuppressionEntry
from app.domain.enums import JobStatus, TaskStatus
from app.jobs import queue
from app.schemas.workflow import (
    CadenceOut,
    DraftOut,
    JobOut,
    OverdueOut,
    SummaryOut,
    SuppressionIn,
    SuppressionOut,
    TaskOut,
)
from app.services import dashboard, followups
from app.services.suppression import add_suppression

router = APIRouter(tags=["operations"])


@router.get("/followups/cadence", response_model=CadenceOut)
def cadence() -> CadenceOut:
    s = get_settings()
    return CadenceOut(
        step_days=s.followup_step_days,
        manual_review_day=s.manual_review_day,
        temperatures=s.followup_temperatures,
        draft_review_sla_hours=s.draft_review_sla_hours,
    )


@router.get("/followups/tasks", response_model=list[TaskOut])
def list_tasks(
    session: SessionDep,
    status_: TaskStatus | None = Query(TaskStatus.SCHEDULED, alias="status"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[TaskOut]:
    stmt = select(FollowUpTask)
    if status_:
        stmt = stmt.where(FollowUpTask.status == status_)
    rows = session.scalars(stmt.order_by(FollowUpTask.due_at).limit(limit))
    return [TaskOut.model_validate(t) for t in rows]


@router.get("/followups/overdue", response_model=OverdueOut)
def overdue(session: SessionDep) -> OverdueOut:
    report = followups.overdue(session)
    return OverdueOut(
        tasks=[TaskOut.model_validate(t) for t in report.tasks],
        drafts=[DraftOut.model_validate(d) for d in report.drafts],
    )


@router.get("/suppressions", response_model=list[SuppressionOut])
def list_suppressions(session: SessionDep) -> list[SuppressionOut]:
    rows = session.scalars(select(SuppressionEntry).order_by(SuppressionEntry.created_at.desc()))
    return [SuppressionOut.model_validate(s) for s in rows]


@router.post("/suppressions", response_model=SuppressionOut, status_code=201)
def create_suppression(data: SuppressionIn, session: SessionDep) -> SuppressionOut:
    entry = add_suppression(
        session,
        kind=data.kind,
        value=data.value,
        reason=data.reason,
        source="dashboard",
        note=data.note,
    )
    session.commit()
    return SuppressionOut.model_validate(entry)


@router.delete("/suppressions/{entry_id}", status_code=204)
def delete_suppression(entry_id: uuid.UUID, session: SessionDep) -> None:
    entry = session.get(SuppressionEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suppression not found")
    if entry.reason in ("unsubscribe", "complaint"):
        # Opt-outs come from the recipient; only they can reverse them.
        raise HTTPException(status.HTTP_409_CONFLICT, "Opt-outs cannot be removed by staff")
    session.delete(entry)
    session.commit()


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    session: SessionDep,
    status_: JobStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
) -> list[JobOut]:
    stmt = select(Job)
    if status_:
        stmt = stmt.where(Job.status == status_)
    rows = session.scalars(stmt.order_by(Job.created_at.desc()).limit(limit))
    return [JobOut.model_validate(j) for j in rows]


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, session: SessionDep) -> JobOut:
    job = queue.retry(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    session.commit()
    return JobOut.model_validate(job)


@router.get("/dashboard/summary", response_model=SummaryOut)
def summary(session: SessionDep) -> SummaryOut:
    return dashboard.summary(session)
