from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Job
from app.db.session import get_session_factory
from app.jobs import queue
from app.jobs.worker import Worker

pytestmark = pytest.mark.integration


def test_enqueue_with_idempotency_key_returns_existing(session: Session) -> None:
    with session.begin():
        a = queue.enqueue(session, "noop", {"n": 1}, idempotency_key="k1")
        b = queue.enqueue(session, "noop", {"n": 2}, idempotency_key="k1")
        c = queue.enqueue(session, "noop", {"n": 3})
    assert a.id == b.id != c.id
    assert len(session.scalars(select(Job)).all()) == 2


def test_failed_job_retries_with_backoff_then_dies(session: Session) -> None:
    factory = get_session_factory()
    calls = []

    def boom(_s, payload):
        calls.append(payload)
        raise RuntimeError("downstream unavailable")

    with session.begin():
        job = queue.enqueue(session, "boom", {}, max_attempts=3)

    for attempt in range(1, 4):
        [job_id] = queue.claim(factory, "w1", 10)
        status = queue.run_claimed(factory, job_id, "w1", {"boom": boom})
        session.expire_all()
        j = session.get(Job, job.id)
        assert j.attempts == attempt
        if attempt < 3:
            assert status == "queued"
            assert j.run_at == clock.utcnow() + queue.backoff(attempt)
            assert queue.claim(factory, "w1", 10) == []  # not yet due
            clock.advance(queue.backoff(attempt))
        else:
            assert status == "dead"
    assert "downstream unavailable" in j.last_error
    assert len(calls) == 3

    queue.retry(session, job.id)
    session.commit()
    assert session.get(Job, job.id).status == "queued"


def test_handler_effects_roll_back_on_failure(session: Session) -> None:
    factory = get_session_factory()

    def half_done(s, _payload):
        queue.enqueue(s, "side_effect", {}, idempotency_key="side")
        raise ValueError("crash after partial work")

    with session.begin():
        queue.enqueue(session, "half", {})
    [job_id] = queue.claim(factory, "w1", 10)
    queue.run_claimed(factory, job_id, "w1", {"half": half_done})
    session.expire_all()
    assert session.scalar(select(Job).where(Job.idempotency_key == "side")) is None


def test_expired_lease_is_recovered_after_worker_crash(session: Session) -> None:
    factory = get_session_factory()
    ran = []
    with session.begin():
        job = queue.enqueue(session, "work", {})
    [job_id] = queue.claim(factory, "crashed-worker", 10)  # claimed, never finished

    clock.advance(timedelta(minutes=4))
    with factory.begin() as s:
        assert queue.recover_expired_leases(s) == 0  # lease (5 min) still valid
    clock.advance(timedelta(minutes=2))
    with factory.begin() as s:
        assert queue.recover_expired_leases(s) == 1

    # the crashed worker comes back and tries to finish: it no longer owns the job
    assert (
        queue.run_claimed(factory, job_id, "crashed-worker", {"work": lambda s, p: ran.append(1)})
        == "lost"
    )

    w = Worker(factory, worker_id="fresh-worker")
    from app.jobs import handlers

    handlers.HANDLERS["work"] = lambda s, p: ran.append(2)
    try:
        assert w.drain().succeeded == 1
    finally:
        del handlers.HANDLERS["work"]
    assert ran == [2]
    session.expire_all()
    j = session.get(Job, job.id)
    assert (j.status, j.attempts) == ("succeeded", 2)


def test_unknown_job_kind_fails_cleanly(session: Session) -> None:
    factory = get_session_factory()
    with session.begin():
        queue.enqueue(session, "does_not_exist", {}, max_attempts=1)
    [job_id] = queue.claim(factory, "w1", 10)
    assert queue.run_claimed(factory, job_id, "w1", {}) == "dead"
