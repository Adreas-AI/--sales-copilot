"""Keyword signals read from what the prospect actually wrote.

Shared by the rule engine and by inbound-reply processing. Patterns are kept
conservative: a missed signal costs a few points; a false one misleads a rep.
"""

from __future__ import annotations

import re

from app.domain.enums import Objection


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


INTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "asked_about_pricing": _rx(r"\b(pric(e|es|ing)|costs?|quote|how much|subscription fee)\b"),
    "asked_for_demo": _rx(r"\b(demo|walk ?-?through|show (me|us) how)\b"),
    "switching_provider": _rx(
        r"\b(switch(ing)?|migrat(e|ing|ion)|replac(e|ing)|moving (away )?from|"
        r"current (system|software|tool|provider))\b"
    ),
    "ready_to_start": _rx(r"\b(sign up|get started|ready to|onboard(ing)?|purchase|go live)\b"),
}

URGENCY_HIGH = _rx(
    r"\b(asap|urgent(ly)?|as soon as possible|this week|immediately|right away|next week|"
    r"(contract|subscription) (ends|expires|is up|runs out)|opening (on|in|next)|"
    r"launch(ing)? (on|in|next))\b"
)
URGENCY_MEDIUM = _rx(
    r"\b(this month|next month|soon|within (a|one|two|three|\d+) (weeks?|months?)|"
    r"before (the )?(end of|summer|winter|spring|autumn|new year)|q[1-4])\b"
)

# Senders who are not prospective customers (job seekers, vendors, students).
NON_BUYER = _rx(
    r"\b(job (application|opening)|apply(ing)? for (a|the) (job|position|role)|my (resume|cv)|"
    r"internship|student (project|research)|homework|seo (services|agency|package)|guest post|"
    r"link ?building|backlinks|we are an? (agency|vendor)|partnership proposal)\b"
)

UNSUBSCRIBE_INTENT = _rx(
    r"\b(unsubscribe|remove me|take me off|stop (emailing|contacting|messaging) me|"
    r"do not (email|contact) me|don't (email|contact) me( again)?|opt[ -]?out)\b"
)

OBJECTION_PATTERNS: dict[Objection, re.Pattern[str]] = {
    Objection.PRICE: _rx(
        r"\b(too expensive|expensive|budget|can't afford|cannot afford|cheaper|cost too much|pricey)\b"
    ),
    Objection.SWITCHING_COST: _rx(
        r"\b(hassle|effort|migrat(e|ing|ion)|move (all )?(our|my) (data|clients)|transfer (our|my))\b"
    ),
    Objection.COMPETITOR: _rx(
        r"\b(already (use|using|have)|we use|currently (use|using|on)|happy with (our|my))\b"
    ),
    Objection.TIMING: _rx(
        r"\b(not (the )?right time|too busy|busy season|later this year|maybe later)\b"
    ),
    Objection.STAFF_ADOPTION: _rx(
        r"\b(staff|team|employees|barbers|stylists|trainers) (won't|will not|wouldn't|may not|might not)"
        r"|\b(not tech[- ]savvy|learning curve)\b"
    ),
    Objection.MISSING_FEATURE: _rx(
        r"\b(does it (support|have|integrate)|is there (a|an) way|integrat(e|ion) with)\b"
    ),
    Objection.CONTRACT_LOCK_IN: _rx(
        r"\b(long[- ]term contract|lock(ed)?[- ]in|minimum (term|commitment)|annual commitment|"
        r"tied (in|into)|cancel any ?time)\b"
    ),
}

PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "yandex.com",
    }
)


def detect_intent(text: str) -> list[str]:
    return [name for name, pattern in INTENT_PATTERNS.items() if pattern.search(text)]


def detect_urgency(text: str) -> tuple[str, str | None]:
    """Return ("high"|"medium"|"none", matched phrase)."""
    if m := URGENCY_HIGH.search(text):
        return "high", m.group(0)
    if m := URGENCY_MEDIUM.search(text):
        return "medium", m.group(0)
    return "none", None


def detect_non_buyer(text: str) -> str | None:
    m = NON_BUYER.search(text)
    return m.group(0) if m else None


def detect_objections(text: str) -> set[Objection]:
    return {objection for objection, pattern in OBJECTION_PATTERNS.items() if pattern.search(text)}


def wants_unsubscribe(text: str) -> bool:
    return bool(UNSUBSCRIBE_INTENT.search(text))
