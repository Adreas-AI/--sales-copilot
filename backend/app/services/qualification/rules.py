"""Deterministic lead scoring. Pure functions over ``LeadFacts``; no I/O.

Six factors add up to 100 points; penalties subtract. Every factor records the
evidence it used, and anything the lead didn't tell us is reported as missing
rather than guessed.

    category fit      20   Is this a segment BookFlow is built for?
    business size     20   Locations and staff headcount
    product fit       15   Interest in modules BookFlow actually has
    purchase intent   25   Lead source plus what they asked for
    urgency           10   Stated timelines
    engagement        10   Replies and pipeline progress
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.domain import catalog
from app.domain.enums import (
    BusinessCategory,
    CompanySize,
    LeadSource,
    PipelineStage,
    Temperature,
)
from app.services.qualification import signals

CATEGORY_POINTS: dict[str, int] = {
    BusinessCategory.GYM: 20,
    BusinessCategory.FITNESS_STUDIO: 20,
    BusinessCategory.BEAUTY_SALON: 20,
    BusinessCategory.BARBERSHOP: 20,
    BusinessCategory.WELLNESS_STUDIO: 18,
    BusinessCategory.SPA: 18,
    BusinessCategory.OTHER: 4,
}

COMPANY_SIZE_POINTS: dict[str, int] = {
    CompanySize.S1_5: 6,
    CompanySize.S6_20: 12,
    CompanySize.S21_50: 16,
    CompanySize.S51_200: 20,
    CompanySize.S200_PLUS: 20,
}

SOURCE_INTENT_POINTS: dict[str, int] = {
    LeadSource.DEMO_REQUEST: 15,
    LeadSource.FREE_TRIAL: 12,
    LeadSource.WEBSITE_FORM: 6,
    LeadSource.MANUAL: 6,
    LeadSource.WEBHOOK: 6,
}

PERSONAL_EMAIL_PENALTY = -5
NON_BUYER_PENALTY = -40
MIN_MEANINGFUL_MESSAGE = 20


@dataclass(frozen=True)
class LeadFacts:
    business_category: str
    locations_count: int | None
    company_size: str | None
    product_interest: list[str]
    message: str | None
    source: str
    email_domain: str
    stage: str
    inbound_replies: int = 0
    # Everything the prospect has written to us (inquiry + replies), newest last.
    prospect_texts: list[str] = field(default_factory=list)

    @property
    def prospect_text(self) -> str:
        return "\n".join(t for t in self.prospect_texts if t)


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    points: int
    max_points: int
    evidence: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RuleResult:
    score: int
    factors: list[Factor]
    penalties: list[Factor]
    signals: list[str]
    missing_information: list[str]
    completeness: float


def _locations_points(n: int) -> int:
    if n >= 10:
        return 20
    if n >= 4:
        return 18
    if n >= 2:
        return 14
    return 8


def score_category(facts: LeadFacts) -> Factor:
    points = CATEGORY_POINTS.get(facts.business_category, 0)
    label = catalog.CATEGORY_LABELS.get(facts.business_category, facts.business_category)
    if facts.business_category == BusinessCategory.OTHER:
        evidence = "Category 'other': outside BookFlow's core segments"
    else:
        evidence = f"Core segment: {label}"
    return Factor("category_fit", "Category fit", points, 20, evidence)


def score_size(facts: LeadFacts) -> Factor:
    candidates: list[tuple[int, str]] = []
    if facts.locations_count is not None:
        n = facts.locations_count
        candidates.append((_locations_points(n), f"{n} location{'s' if n != 1 else ''}"))
    if facts.company_size is not None and facts.company_size in COMPANY_SIZE_POINTS:
        candidates.append((COMPANY_SIZE_POINTS[facts.company_size], f"{facts.company_size} staff"))
    if not candidates:
        return Factor("business_size", "Business size", 0, 20, "Size not provided")
    points = max(p for p, _ in candidates)
    return Factor("business_size", "Business size", points, 20, ", ".join(e for _, e in candidates))


def score_product_fit(facts: LeadFacts) -> Factor:
    modules = catalog.match_modules(" , ".join(facts.product_interest), facts.message)
    if not modules:
        return Factor("product_fit", "Product fit", 0, 15, "No specific BookFlow module mentioned")
    labels = [catalog.MODULES[k].label for k in modules]
    return Factor(
        "product_fit",
        "Product fit",
        min(15, 5 * len(modules)),
        15,
        "Interested in " + ", ".join(labels),
    )


def score_intent(facts: LeadFacts) -> tuple[Factor, list[str]]:
    base = SOURCE_INTENT_POINTS.get(facts.source, 0)
    found = signals.detect_intent(facts.prospect_text)
    points = min(25, base + min(10, 5 * len(found)))
    evidence = f"Source: {facts.source.replace('_', ' ')}"
    if found:
        evidence += "; " + ", ".join(s.replace("_", " ") for s in found)
    return Factor("purchase_intent", "Purchase intent", points, 25, evidence), found


def score_urgency(facts: LeadFacts) -> Factor:
    level, phrase = signals.detect_urgency(facts.prospect_text)
    points = {"high": 10, "medium": 5}.get(level, 0)
    evidence = f'Said "{phrase}"' if phrase else "No timeline mentioned"
    return Factor("urgency", "Urgency", points, 10, evidence)


def score_engagement(facts: LeadFacts) -> Factor:
    points = min(8, 4 * facts.inbound_replies)
    notes = []
    if facts.inbound_replies:
        notes.append(f"{facts.inbound_replies} repl{'y' if facts.inbound_replies == 1 else 'ies'}")
    if facts.stage in (PipelineStage.DEMO_SCHEDULED, PipelineStage.DEMO_COMPLETED):
        points += 6
        notes.append(f"stage {facts.stage.replace('_', ' ')}")
    elif facts.stage == PipelineStage.NEGOTIATION:
        points += 8
        notes.append("in negotiation")
    return Factor(
        "engagement",
        "Engagement",
        min(10, points),
        10,
        ", ".join(notes) if notes else "No engagement yet",
    )


def missing_information(facts: LeadFacts) -> list[str]:
    missing = []
    if facts.business_category == BusinessCategory.OTHER:
        missing.append("business_category")
    if facts.locations_count is None:
        missing.append("locations_count")
    if facts.company_size is None:
        missing.append("company_size")
    if not facts.product_interest:
        missing.append("product_interest")
    if not facts.message or len(facts.message.strip()) < MIN_MEANINGFUL_MESSAGE:
        missing.append("inquiry_message")
    return missing


COMPLETENESS_FIELDS = 5


def evaluate(facts: LeadFacts) -> RuleResult:
    intent, intent_signals = score_intent(facts)
    factors = [
        score_category(facts),
        score_size(facts),
        score_product_fit(facts),
        intent,
        score_urgency(facts),
        score_engagement(facts),
    ]
    found_signals = list(intent_signals)
    penalties: list[Factor] = []

    if facts.email_domain.lower() in signals.PERSONAL_EMAIL_DOMAINS:
        penalties.append(
            Factor(
                "personal_email",
                "Personal email address",
                PERSONAL_EMAIL_PENALTY,
                0,
                f"Uses {facts.email_domain}, not a business domain",
            )
        )
        found_signals.append("personal_email_domain")

    if phrase := signals.detect_non_buyer(facts.prospect_text):
        penalties.append(
            Factor(
                "non_buyer",
                "Likely not a buyer",
                NON_BUYER_PENALTY,
                0,
                f'Message mentions "{phrase}"',
            )
        )
        found_signals.append("possible_non_buyer")

    raw = sum(f.points for f in factors) + sum(p.points for p in penalties)
    missing = missing_information(facts)
    return RuleResult(
        score=max(0, min(100, raw)),
        factors=factors,
        penalties=penalties,
        signals=found_signals,
        missing_information=missing,
        completeness=round(1 - len(missing) / COMPLETENESS_FIELDS, 2),
    )


def classify(score: int, *, hot_threshold: int, warm_threshold: int) -> Temperature:
    if score >= hot_threshold:
        return Temperature.HOT
    if score >= warm_threshold:
        return Temperature.WARM
    return Temperature.COLD
