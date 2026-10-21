"""A small, restart-safe job queue on top of the ``jobs`` table.

* **Idempotent enqueue**: a job with an ``idempotency_key`` is inserted with
  ``ON CONFLICT DO NOTHING``, so enqueueing the same logical work twice is harmless.
* **Safe concurrent claiming**: workers claim with ``SELECT ... FOR UPDATE SKIP LOCKED``
  (PostgreSQL), so two workers never take the same job.
* **Leases**: a claimed job carries ``locked_until``. If a worker dies mid-job, the
  lease expires and the job is put back in the queue.
* **Atomic completion**: a handler's writes and the job's ``succeeded`` status
  commit in one transaction. A crash before commit leaves no partial effects.
* **Retries** with exponential backoff, then ``dead`` after ``max_attempts``.
"""

from __future__ import annotations

import traceback
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Job
from app.domain.enums import JobStatus

log = get_logger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]

MAX_BACKOFF = timedelta(hours=1)


def backoff(attempts: int) -> timedelta:
    return min(timedelta(seconds=30 * 2 ** max(0, attempts - 1)), MAX_BACKOFF)


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    run_at=None,
    max_attempts: int | None = None,
) -> Job:
    values = {
        "id": uuid.uuid4(),
        "kind": kind,
        "payload": payload,
        "status": JobStatus.QUEUED,
        "idempotency_key": idempotency_key,
        "run_at": run_at or clock.utcnow(),
        "attempts": 0,
        "max_attempts": max_attempts or get_settings().job_max_attempts,
        "created_at": clock.utcnow(),
    }
    if idempotency_key is None:
        job = Job(**values)
        session.add(job)
        session.flush()
        return job

    session.flush()  # make pending ORM objects visible to the raw insert below
    dialect = session.get_bind().dialect.name
    insert = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}.get(dialect)
    if insert is None:  # pragma: no cover - other backends: best-effort check-then-insert
        existing = session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing
        job = Job(**values)
        session.add(job)
        session.flush()
        return job
    session.execute(
        insert(Job).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    job = session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
    assert job is not None
    return job


def recover_expired_leases(session: Session) -> int:
    """Requeue jobs whose worker vanished (lease expired while ``running``)."""
    now = clock.utcnow()
    expired = list(
        session.scalars(
            select(Job)
            .where(Job.status == JobStatus.RUNNING, Job.locked_until < now)
            .with_for_update(skip_locked=True)
        )
    )
    for job in expired:
        job.locked_by = None
        job.locked_until = None
        job.last_error = f"Lease expired at attempt {job.attempts}; worker presumed dead"
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD
            job.finished_at = now
        else:
            job.status = JobStatus.QUEUED
            job.run_at = now
    if expired:
        log.warning("Recovered %d job(s) with expired leases", len(expired))
    return len(expired)


def claim(factory: sessionmaker[Session], worker_id: str, limit: int) -> list[uuid.UUID]:
    lease = timedelta(seconds=get_settings().job_lease_seconds)
    with factory.begin() as session:
        now = clock.utcnow()
        jobs = list(
            session.scalars(
                select(Job)
                .where(Job.status == JobStatus.QUEUED, Job.run_at <= now)
                .order_by(Job.run_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.status = JobStatus.RUNNING
            job.locked_by = worker_id
            job.locked_until = now + lease
            job.attempts += 1
            job.started_at = now
        return [job.id for job in jobs]


def run_claimed(
    factory: sessionmaker[Session],
    job_id: uuid.UUID,
    worker_id: str,
    handlers: dict[str, Handler],
) -> str:
    """Run one claimed job; returns its resulting status."""
    with factory() as session:
        job = session.get(Job, job_id)
        if job is None or job.status != JobStatus.RUNNING or job.locked_by != worker_id:
            return "lost"
        handler = handlers.get(job.kind)
        try:
            if handler is None:
                raise LookupError(f"No handler registered for job kind {job.kind!r}")
            handler(session, dict(job.payload))
            # Only finish if we still hold the lease (no other worker took over).
            result = session.execute(
                update(Job)
                .where(
                    Job.id == job_id, Job.locked_by == worker_id, Job.status == JobStatus.RUNNING
                )
                .values(
                    status=JobStatus.SUCCEEDED,
                    finished_at=clock.utcnow(),
                    locked_by=None,
                    locked_until=None,
                    last_error=None,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return "lost"
            session.commit()
            return JobStatus.SUCCEEDED
        except Exception as exc:
            session.rollback()
            error = "".join(traceback.format_exception_only(exc)).strip()[:2000]
            log.exception("Job %s (%s) failed", job_id, job.kind if job else "?")

    with factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.last_error = error
        job.locked_by = None
        job.locked_until = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.DEAD
            job.finished_at = clock.utcnow()
        else:
            job.status = JobStatus.QUEUED
            job.run_at = clock.utcnow() + backoff(job.attempts)
        return job.status


def retry(session: Session, job_id: uuid.UUID) -> Job | None:
    job = session.get(Job, job_id)
    if job is None or job.status != JobStatus.DEAD:
        return job
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.run_at = clock.utcnow()
    job.finished_at = None
    return job
