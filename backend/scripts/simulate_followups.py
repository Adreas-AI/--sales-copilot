"""Walk one lead through Day 0 → Day 10 in a few seconds, printing what happens.

    python -m scripts.simulate_followups               # nobody replies
    python -m scripts.simulate_followups --reply-on 3  # prospect replies on day 3

Runs against an in-memory SQLite database; nothing is persisted.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core import clock
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.models import Activity, EmailDraft, Lead
from app.db.session import configure_engine, get_session_factory
from app.domain.enums import DraftStatus
from app.jobs.worker import Worker
from app.schemas.leads import LeadCreate
from app.services import leads
from app.services.conversations import record_inbound_reply
from app.services.emails import review

START = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reply-on", type=int, default=None, help="day the prospect replies")
    args = parser.parse_args()
    configure_logging("WARNING")
    Base.metadata.create_all(configure_engine("sqlite://"))
    factory = get_session_factory()
    worker = Worker(factory, worker_id="sim")
    clock.set_now(START)

    with factory.begin() as s:
        leads.intake_lead(
            s,
            LeadCreate(
                business_name="Iron Temple Fitness",
                contact_name="Sam Rivera",
                email="sam@irontemple.example",
                business_category="gym",
                locations_count=3,
                company_size="21-50",
                product_interest=["memberships", "class booking"],
                message="Our booking tool can't do waitlists. Switching before our contract "
                "ends next month. Pricing?",
                source="demo_request",
                consent={"email": True},
            ),
        )
    seen: set = set()
    for day in range(0, 12):
        clock.set_now(START + timedelta(days=day, minutes=5))
        if args.reply_on == day:
            with factory.begin() as s:
                lead = s.scalar(select(Lead))
                record_inbound_reply(s, lead, subject="Re: demo", body="Thursday works for us.")
        worker.drain()
        with factory.begin() as s:
            # The rep approves and sends whatever the copilot prepared.
            for d in s.scalars(
                select(EmailDraft).where(EmailDraft.status == DraftStatus.PENDING_REVIEW)
            ):
                review.approve_draft(s, d.id, reviewer="dana")
                review.send_draft(s, d.id, sender="dana")
        with factory() as s:
            for a in s.scalars(select(Activity).order_by(Activity.occurred_at)):
                if a.id in seen:
                    continue
                seen.add(a.id)
                text = a.subject if a.kind == "outbound_email" else (a.body or a.subject or "")
                print(f"Day {day:>2}  {a.kind:<15} {text[:90]}")
    clock.set_now(None)


if __name__ == "__main__":
    main()
