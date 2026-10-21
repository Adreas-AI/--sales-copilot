"""Background worker: ``python -m app.jobs.worker`` (or ``--once`` for a single tick).

Each tick: requeue jobs with expired leases, turn due follow-up tasks into jobs,
then claim and run a batch. Every step is safe to repeat, so the worker can be
killed and restarted at any point, and several can run side by side.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.jobs import queue
from app.jobs.handlers import HANDLERS
from app.services import followups

log = get_logger(__name__)


@dataclass
class TickStats:
    recovered: int = 0
    scheduled: int = 0
    claimed: int = 0
    succeeded: int = 0
    failed: int = 0


class Worker:
    def __init__(
        self,
        factory: sessionmaker[Session] | None = None,
        *,
        worker_id: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.factory = factory or get_session_factory()
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.batch_size = batch_size or settings.worker_batch_size
        self.poll_seconds = settings.worker_poll_seconds
        self._stop = threading.Event()

    def tick(self) -> TickStats:
        stats = TickStats()
        with self.factory.begin() as session:
            stats.recovered = queue.recover_expired_leases(session)
        with self.factory.begin() as session:
            stats.scheduled = followups.enqueue_due_tasks(session)
        job_ids = queue.claim(self.factory, self.worker_id, self.batch_size)
        stats.claimed = len(job_ids)
        for job_id in job_ids:
            if queue.run_claimed(self.factory, job_id, self.worker_id, HANDLERS) == "succeeded":
                stats.succeeded += 1
            else:
                stats.failed += 1
        return stats

    def drain(self, max_ticks: int = 50) -> TickStats:
        """Tick until there's nothing left to run now (used by tests and the demo)."""
        total = TickStats()
        for _ in range(max_ticks):
            stats = self.tick()
            for field in ("recovered", "scheduled", "claimed", "succeeded", "failed"):
                setattr(total, field, getattr(total, field) + getattr(stats, field))
            if stats.claimed == 0:
                break
        return total

    def stop(self, *_: object) -> None:
        log.info("Worker %s stopping after current batch", self.worker_id)
        self._stop.set()

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        log.info("Worker %s started (poll every %.1fs)", self.worker_id, self.poll_seconds)
        while not self._stop.is_set():
            try:
                stats = self.tick()
                if stats.claimed:
                    log.info("tick %s", stats)
                    continue  # more work may be waiting
            except Exception:
                log.exception("Worker tick failed; retrying after poll interval")
            self._stop.wait(self.poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Sales Copilot job worker")
    parser.add_argument("--once", action="store_true", help="drain available work and exit")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    worker = Worker()
    if args.once:
        log.info("drained: %s", worker.drain())
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
