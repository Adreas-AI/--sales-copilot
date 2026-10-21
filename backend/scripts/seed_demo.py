"""Populate the database with a realistic two-week history of BookFlow leads.

    python -m scripts.seed_demo            # against DATABASE_URL
    python -m scripts.seed_demo --reset    # drop and recreate all tables first (dev only)

Events are replayed in time order with the clock moved back, and the real worker
runs between them, so sequences, drafts and overdue items are all genuine.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.models import EmailDraft, Lead
from app.db.session import get_engine, get_session_factory
from app.domain.enums import DraftStatus
from app.jobs.worker import Worker
from app.schemas.leads import LeadCreate, LeadUpdate
from app.services import leads
from app.services.conversations import record_inbound_reply
from app.services.emails import review

REP = "dana.okafor"

LEADS: list[dict] = [
    {
        "business_name": "Iron Temple Fitness",
        "contact_name": "Sam Rivera",
        "email": "sam@irontemple.example",
        "business_category": "gym",
        "locations_count": 3,
        "company_size": "21-50",
        "product_interest": ["memberships", "class booking"],
        "message": "We run 3 gyms and our current booking software can't handle waitlists. "
        "Looking to switch before our contract ends next month. What does pricing look like?",
        "source": "demo_request",
    },
    {
        "business_name": "Glow Beauty Studio",
        "contact_name": "Ana Petrova",
        "email": "ana@glowbeauty.example",
        "business_category": "beauty_salon",
        "locations_count": 1,
        "company_size": "6-20",
        "product_interest": ["online booking", "deposits"],
        "message": "Last-minute no-shows are killing us. Can clients pay a deposit when they book?",
        "source": "website_form",
    },
    {
        "business_name": "Fade Factory Barbers",
        "contact_name": "Marcus Lee",
        "email": "marcus@fadefactory.example",
        "business_category": "barbershop",
        "locations_count": 2,
        "company_size": "6-20",
        "product_interest": ["scheduling", "reminders"],
        "message": "Started the trial. Want each barber to have their own booking link.",
        "source": "free_trial",
    },
    {
        "business_name": "Stillwater Yoga",
        "contact_name": "Priya Nair",
        "email": "priya@stillwateryoga.example",
        "business_category": "wellness_studio",
        "locations_count": 1,
        "company_size": "1-5",
        "product_interest": ["classes", "memberships"],
        "message": "Small studio, mostly classes and 10-class packs. "
        "Is there a way to sell packs online?",
        "source": "demo_request",
        "consent_marketing": True,
    },
    {
        "business_name": "Peak Performance Clubs",
        "contact_name": "Jordan Blake",
        "email": "jordan@peakclubs.example",
        "business_category": "gym",
        "locations_count": 12,
        "company_size": "200+",
        "product_interest": ["multi-location", "memberships", "payments"],
        "message": "We're consolidating 12 clubs onto one platform this quarter. Need central "
        "reporting and per-location permissions. Can we get a demo next week?",
        "source": "demo_request",
    },
    {
        "business_name": "Serenity Day Spa",
        "contact_name": "Helen Brooks",
        "email": "helen@serenityspa.example",
        "business_category": "spa",
        "locations_count": None,
        "company_size": None,
        "product_interest": [],
        "message": "Interested, please send info.",
        "source": "website_form",
        "preferred_channel": "phone",
        "phone": "+1 555 0142",
    },
    {
        "business_name": "Bright Pixel Marketing",
        "contact_name": "Tom Wade",
        "email": "tom@brightpixel.example",
        "business_category": "other",
        "locations_count": None,
        "company_size": None,
        "product_interest": [],
        "message": "We are an SEO agency offering an SEO package to software companies like yours.",
        "source": "website_form",
    },
    {
        "business_name": "CoreFit Studio",
        "contact_name": "Lena Fischer",
        "email": "lena@corefit.example",
        "business_category": "fitness_studio",
        "locations_count": 1,
        "company_size": "6-20",
        "product_interest": ["class booking"],
        "message": "Looking at options for our studio, no rush.",
        "source": "webhook",
        "source_detail": "typeform",
    },
]


@dataclass
class Event:
    hours_ago: float
    label: str
    action: Callable[[Session], None]


def _lead(session: Session, email: str) -> Lead:
    lead = session.scalar(select(Lead).where(Lead.email == email))
    assert lead is not None, email
    return lead


def intake(data: dict) -> Callable[[Session], None]:
    def run(session: Session) -> None:
        payload = dict(data)
        marketing = payload.pop("consent_marketing", False)
        payload["consent"] = {
            "email": True,
            "marketing": marketing,
            "source_text": "website form v3",
        }
        leads.intake_lead(session, LeadCreate(**payload))

    return run


def send_open(email: str) -> Callable[[Session], None]:
    def run(session: Session) -> None:
        lead = _lead(session, email)
        for draft in session.scalars(
            select(EmailDraft).where(
                EmailDraft.lead_id == lead.id, EmailDraft.status == DraftStatus.PENDING_REVIEW
            )
        ):
            review.approve_draft(session, draft.id, reviewer=REP)
            review.send_draft(session, draft.id, sender=REP)

    return run


def reply(email: str, body: str) -> Callable[[Session], None]:
    def run(session: Session) -> None:
        record_inbound_reply(session, _lead(session, email), subject="Re: BookFlow", body=body)

    return run


def stage(email: str, value: str) -> Callable[[Session], None]:
    def run(session: Session) -> None:
        leads.update_lead(session, _lead(session, email), LeadUpdate(stage=value), actor=REP)

    return run


def timeline() -> list[Event]:
    by_email = {d["email"]: d for d in LEADS}

    def at(days: float, hours: float = 0) -> float:
        return days * 24 + hours

    return [
        Event(at(13), "Iron Temple demo request", intake(by_email["sam@irontemple.example"])),
        Event(at(12, 22), "Rep sends Iron Temple reply", send_open("sam@irontemple.example")),
        Event(at(10, 20), "Rep sends Iron Temple follow-up", send_open("sam@irontemple.example")),
        Event(at(11), "Glow contact form", intake(by_email["ana@glowbeauty.example"])),
        Event(at(10, 21), "Rep replies to Glow", send_open("ana@glowbeauty.example")),
        Event(
            at(9),
            "Glow replies with an objection",
            reply(
                "ana@glowbeauty.example",
                "Thanks Maya. Deposits sound great but honestly it seems expensive for one salon, "
                "and we already use Square for payments.",
            ),
        ),
        Event(at(6), "Fade Factory trial", intake(by_email["marcus@fadefactory.example"])),
        Event(at(5, 22), "Rep sends trial welcome", send_open("marcus@fadefactory.example")),
        Event(at(4), "Stillwater demo request", intake(by_email["priya@stillwateryoga.example"])),
        Event(at(3), "Peak Performance demo", intake(by_email["jordan@peakclubs.example"])),
        Event(at(2, 23), "Rep sends Peak demo invite", send_open("jordan@peakclubs.example")),
        Event(
            at(2),
            "Peak books a demo",
            reply(
                "jordan@peakclubs.example",
                "Tuesday 10am works. I'll bring our ops director.",
            ),
        ),
        Event(
            at(1, 23),
            "Peak stage -> demo scheduled",
            stage("jordan@peakclubs.example", "demo_scheduled"),
        ),
        Event(at(2), "Serenity Spa form", intake(by_email["helen@serenityspa.example"])),
        Event(at(1), "Agency pitch arrives", intake(by_email["tom@brightpixel.example"])),
        Event(at(0, 6), "CoreFit via Typeform", intake(by_email["lena@corefit.example"])),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging("WARNING", settings.log_json)
    if args.reset:
        if settings.environment == "production":
            raise SystemExit("Refusing to reset a production database")
        Base.metadata.drop_all(get_engine())
        Base.metadata.create_all(get_engine())

    factory = get_session_factory()
    with factory() as session:
        if session.scalar(select(Lead.id).limit(1)) is not None and not args.reset:
            raise SystemExit("Database already has leads; use --reset to start over")

    worker = Worker(factory, worker_id="seed")
    real_now = clock.utcnow()
    try:
        for event in sorted(timeline(), key=lambda e: -e.hours_ago):
            clock.set_now(real_now - timedelta(hours=event.hours_ago))
            worker.drain()  # let anything due by now happen first
            with factory.begin() as session:
                event.action(session)
            worker.drain()
            print(f"{clock.utcnow():%b %d %H:%M}  {event.label}")
    finally:
        clock.set_now(None)
    worker.drain()
    print("Seeded. Open the dashboard to review drafts and follow-ups.")


if __name__ == "__main__":
    main()
