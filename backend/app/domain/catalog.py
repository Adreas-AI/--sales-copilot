"""BookFlow product knowledge: the only product facts emails are allowed to state.

Everything a generated email says about the product must come from here, so sales
copy can't drift into claims nobody approved. Edit this file to change positioning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.enums import BusinessCategory, Objection

PRODUCT_NAME = "BookFlow"
TRIAL_DAYS = 14


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    description: str
    synonyms: tuple[str, ...]


MODULES: dict[str, Module] = {
    m.key: m
    for m in (
        Module(
            "scheduling",
            "online booking",
            "clients book 24/7 from a link or your website, against each staff member's real availability",
            (
                "scheduling",
                "booking",
                "bookings",
                "appointments",
                "appointment",
                "calendar",
                "online booking",
            ),
        ),
        Module(
            "reminders",
            "automated reminders",
            "SMS and email reminders go out automatically before every appointment",
            ("reminders", "reminder", "no-shows", "no shows", "no-show", "sms", "notifications"),
        ),
        Module(
            "payments",
            "payments & deposits",
            "deposits, card-on-file and no-show fees can be taken at the moment of booking",
            ("payments", "payment", "deposits", "deposit", "pos", "card", "invoicing", "checkout"),
        ),
        Module(
            "memberships",
            "memberships & class packs",
            "memberships, class packs and recurring billing run without manual invoicing",
            (
                "memberships",
                "membership",
                "class packs",
                "packages",
                "subscriptions",
                "recurring billing",
            ),
        ),
        Module(
            "class_booking",
            "class booking",
            "class timetables with capacity limits and automatic waitlists",
            ("classes", "class booking", "group classes", "timetable", "waitlist", "waitlists"),
        ),
        Module(
            "crm",
            "client management",
            "every client's visit history, notes, preferences and forms in one profile",
            (
                "crm",
                "client management",
                "customer management",
                "client profiles",
                "client records",
            ),
        ),
        Module(
            "marketing",
            "marketing tools",
            "win-back campaigns for lapsed clients and automatic review requests after visits",
            ("marketing", "campaigns", "reviews", "email marketing", "loyalty", "promotions"),
        ),
        Module(
            "multi_location",
            "multi-location management",
            "one account across all locations, with per-location calendars, reporting and staff permissions",
            ("multi-location", "multi location", "multiple locations", "franchise", "locations"),
        ),
    )
}

CATEGORY_LABELS: dict[str, str] = {
    BusinessCategory.GYM: "gym",
    BusinessCategory.FITNESS_STUDIO: "fitness studio",
    BusinessCategory.BEAUTY_SALON: "salon",
    BusinessCategory.BARBERSHOP: "barbershop",
    BusinessCategory.WELLNESS_STUDIO: "wellness studio",
    BusinessCategory.SPA: "spa",
    BusinessCategory.OTHER: "business",
}

# What tends to matter most to each segment, phrased as a clause that completes
# "the part most teams notice first is that ...".
CATEGORY_ANGLES: dict[str, tuple[str, ...]] = {
    BusinessCategory.GYM: (
        "members book classes and PT sessions from their phone, and full classes fill from the waitlist automatically",
        "memberships and class packs bill on their own, so the front desk stops chasing payments",
    ),
    BusinessCategory.FITNESS_STUDIO: (
        "clients book classes from their phone, and full classes fill from the waitlist automatically",
        "class packs and memberships bill on their own, so nobody has to chase payments",
    ),
    BusinessCategory.BEAUTY_SALON: (
        "clients book the right service with the right stylist, with processing and buffer time built in",
        "a deposit at booking makes last-minute no-shows much less painful",
    ),
    BusinessCategory.BARBERSHOP: (
        "each barber gets their own calendar and booking link, while walk-ins and appointments share one queue",
        "automatic reminders mean fewer empty chairs from forgotten appointments",
    ),
    BusinessCategory.WELLNESS_STUDIO: (
        "classes, 1:1 sessions and packages are booked and paid for in one place",
        "intake forms go out automatically before a client's first visit",
    ),
    BusinessCategory.SPA: (
        "treatments, rooms and therapists are scheduled together so nothing gets double-booked",
        "gift cards and packages are redeemed straight from the booking",
    ),
    BusinessCategory.OTHER: (
        "clients book online against your team's real availability, and reminders go out automatically",
    ),
}

# Approved, honest responses to common objections.
OBJECTION_RESPONSES: dict[str, tuple[str, str]] = {
    Objection.PRICE: (
        "the cost",
        "Plans start at $49 per location per month, and the 14-day trial lets you check it against what "
        "no-shows and admin time cost you today before paying anything.",
    ),
    Objection.SWITCHING_COST: (
        "the effort of switching",
        "We import your clients, services and future appointments from your current system, and "
        "onboarding includes a setup call so your team isn't doing it alone.",
    ),
    Objection.COMPETITOR: (
        "already using another tool",
        "If your current setup works, that's a fair reason to stay. Where teams usually switch is when "
        "they need deposits, memberships or several locations handled in one place.",
    ),
    Objection.TIMING: (
        "the timing",
        "There's no need to switch in a busy period. Many teams set BookFlow up alongside their current "
        "system and move over once they're comfortable.",
    ),
    Objection.STAFF_ADOPTION: (
        "getting the team on board",
        "Staff mostly use the mobile app to see their day, and we run a short training session for the "
        "whole team as part of onboarding.",
    ),
    Objection.MISSING_FEATURE: (
        "whether it covers everything you need",
        "The quickest way to be sure is to tell me which part of your workflow you're worried about, and "
        "I'll show you exactly how it works in BookFlow, or tell you plainly if it doesn't.",
    ),
    Objection.CONTRACT_LOCK_IN: (
        "being locked into a contract",
        "Plans are month-to-month, so you can cancel whenever you like.",
    ),
}

PLANS = (
    ("Starter", "$49 per location per month", "booking, reminders and client profiles"),
    ("Growth", "$99 per location per month", "adds payments, memberships and marketing tools"),
    (
        "Multi-location",
        "custom pricing",
        "for 5+ locations, with central reporting and permissions",
    ),
)


def _pattern(synonym: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(synonym) + r"(?![\w-])", re.IGNORECASE)


_SYNONYM_PATTERNS = [(m.key, _pattern(s)) for m in MODULES.values() for s in m.synonyms]


def match_modules(*texts: str | None) -> list[str]:
    """Return module keys mentioned in any of the texts, in catalog order."""
    haystack = " \n ".join(t for t in texts if t)
    found = {key for key, pattern in _SYNONYM_PATTERNS if pattern.search(haystack)}
    return [key for key in MODULES if key in found]


def product_facts_text() -> str:
    """All approved product facts as plain text (used by the email guardrails)."""
    parts = [f"{PRODUCT_NAME} trial: {TRIAL_DAYS} days."]
    parts += [f"{m.label}: {m.description}." for m in MODULES.values()]
    parts += [response for _, response in OBJECTION_RESPONSES.values()]
    parts += [f"{name}: {price}, {what}." for name, price, what in PLANS]
    return "\n".join(parts)
