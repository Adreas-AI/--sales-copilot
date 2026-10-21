from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Activity, Lead, Qualification
from app.domain.enums import ActivityKind, Direction
from app.llm.client import LLMClient, LLMError
from app.services.activities import record_activity
from app.services.qualification import ai, rules

log = get_logger(__name__)

PROSPECT_TEXT_KINDS = (ActivityKind.INQUIRY, ActivityKind.INBOUND_EMAIL)


def build_facts(session: Session, lead: Lead) -> rules.LeadFacts:
    texts = list(
        session.scalars(
            select(Activity.body)
            .where(
                Activity.lead_id == lead.id,
                Activity.kind.in_(PROSPECT_TEXT_KINDS),
                Activity.body.is_not(None),
            )
            .order_by(Activity.occurred_at)
        )
    )
    if lead.message and lead.message not in texts:
        texts.insert(0, lead.message)
    replies = session.scalar(
        select(func.count())
        .select_from(Activity)
        .where(Activity.lead_id == lead.id, Activity.kind == ActivityKind.INBOUND_EMAIL)
    )
    return rules.LeadFacts(
        business_category=lead.business_category,
        locations_count=lead.locations_count,
        company_size=lead.company_size,
        product_interest=list(lead.product_interest or []),
        message=lead.message,
        source=lead.source,
        email_domain=lead.email_domain,
        stage=lead.stage,
        inbound_replies=replies or 0,
        prospect_texts=texts,
    )


def _rules_confidence(completeness: float) -> float:
    # A lead that told us nothing can still be scored, but we say we're unsure.
    return round(0.4 + 0.5 * completeness, 2)


def _reasoning(result: rules.RuleResult, review: ai.AIReview | None) -> str:
    parts = [f"Rule score {result.score}/100."]
    strongest = sorted(result.factors, key=lambda f: f.points / f.max_points, reverse=True)[:2]
    parts.append(
        "Strongest signals: "
        + "; ".join(f"{f.label.lower()} ({f.evidence})" for f in strongest)
        + "."
    )
    if result.penalties:
        parts.append("Penalties: " + "; ".join(p.evidence for p in result.penalties) + ".")
    if result.missing_information:
        parts.append(
            "Not provided: "
            + ", ".join(m.replace("_", " ") for m in result.missing_information)
            + "."
        )
    if review is not None:
        sign = "+" if review.adjustment >= 0 else ""
        parts.append(f"AI review ({sign}{review.adjustment}): {review.reasoning}")
    return " ".join(parts)


def qualify_lead(
    session: Session, lead: Lead, *, llm: LLMClient | None, actor: str = "system"
) -> Qualification:
    settings = get_settings()
    facts = build_facts(session, lead)
    result = rules.evaluate(facts)

    review: ai.AIReview | None = None
    warnings: list[str] = []
    if llm is not None:
        try:
            review = ai.review(llm, facts, result, max_adjustment=settings.ai_max_adjustment)
            warnings.extend(review.warnings)
        except LLMError as exc:
            log.warning("AI qualification unavailable for lead %s: %s", lead.id, exc)
            warnings.append(f"AI review unavailable, rules only: {exc}")

    adjustment = review.adjustment if review else 0
    score = max(0, min(100, result.score + adjustment))
    temperature = rules.classify(
        score, hot_threshold=settings.hot_threshold, warm_threshold=settings.warm_threshold
    )
    confidence = _rules_confidence(result.completeness)
    if review is not None:
        confidence = (confidence + review.confidence) / 2
        if abs(adjustment) >= settings.ai_max_adjustment * 2 / 3:
            confidence -= 0.1  # rules and AI disagree noticeably
    confidence = round(max(0.05, min(0.99, confidence)), 2)

    # Objections the AI names are kept only when it could quote the prospect.
    ai_objections = review.objections if review and review.evidence else []

    qualification = Qualification(
        lead=lead,
        score=score,
        temperature=temperature,
        confidence=confidence,
        rule_score=result.score,
        ai_adjustment=review.adjustment if review else None,
        method="rules+ai" if review else "rules",
        model=review.model if review else None,
        factors=[f.as_dict() for f in result.factors + result.penalties],
        signals=result.signals,
        missing_information=result.missing_information,
        detected_objections=ai_objections,
        ai_evidence=review.evidence if review else [],
        reasoning=_reasoning(result, review),
        warnings=warnings,
    )
    session.add(qualification)

    lead.score = score
    lead.temperature = temperature
    lead.qualified_at = clock.utcnow()
    if ai_objections:
        lead.objections = sorted(set(lead.objections or []) | set(ai_objections))

    record_activity(
        session,
        lead,
        ActivityKind.QUALIFIED,
        direction=Direction.INTERNAL,
        actor=actor,
        body=f"Scored {score}/100 ({temperature}, confidence {confidence:.0%}).",
        meta={"method": qualification.method, "rule_score": result.score},
    )
    session.flush()
    return qualification
