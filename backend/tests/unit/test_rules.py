from __future__ import annotations

from app.domain.enums import Temperature
from app.services.qualification import rules
from app.services.qualification.signals import detect_objections, wants_unsubscribe


def facts(**overrides) -> rules.LeadFacts:
    base = dict(
        business_category="gym",
        locations_count=3,
        company_size="21-50",
        product_interest=["memberships", "class booking"],
        message="We want to switch before our contract ends next month. What is the pricing?",
        source="demo_request",
        email_domain="irontemple.example",
        stage="new",
    )
    base.update(overrides)
    base.setdefault("prospect_texts", [base["message"]] if base["message"] else [])
    return rules.LeadFacts(**base)


def factor(result: rules.RuleResult, key: str) -> rules.Factor:
    return next(f for f in result.factors + result.penalties if f.key == key)


def test_strong_demo_request_is_hot() -> None:
    result = rules.evaluate(facts())
    assert result.score >= 70
    assert rules.classify(result.score, hot_threshold=70, warm_threshold=40) == Temperature.HOT
    assert factor(result, "category_fit").points == 20
    assert factor(result, "business_size").points == 16  # max(3 locations=14, 21-50 staff=16)
    assert factor(result, "urgency").points == 10
    assert "switching_provider" in result.signals
    assert result.missing_information == []


def test_vague_contact_form_is_cold_and_reports_missing_fields() -> None:
    result = rules.evaluate(
        facts(
            business_category="other",
            locations_count=None,
            company_size=None,
            product_interest=[],
            message="hi",
            source="website_form",
        )
    )
    assert result.score < 40
    assert set(result.missing_information) == {
        "business_category",
        "locations_count",
        "company_size",
        "product_interest",
        "inquiry_message",
    }
    assert result.completeness == 0.0
    assert factor(result, "business_size").evidence == "Size not provided"


def test_non_buyer_and_personal_email_are_penalised() -> None:
    result = rules.evaluate(
        facts(
            message="We are an SEO agency offering an SEO package for gyms.",
            email_domain="gmail.com",
        )
    )
    keys = {p.key for p in result.penalties}
    assert keys == {"non_buyer", "personal_email"}
    assert "possible_non_buyer" in result.signals
    assert result.score < 40


def test_size_uses_locations_when_staff_unknown() -> None:
    result = rules.evaluate(facts(company_size=None, locations_count=12))
    assert factor(result, "business_size").points == 20
    assert "12 locations" in factor(result, "business_size").evidence


def test_engagement_counts_replies_and_stage() -> None:
    result = rules.evaluate(facts(inbound_replies=1, stage="demo_scheduled"))
    assert factor(result, "engagement").points == 10


def test_score_is_clamped_to_0_100() -> None:
    result = rules.evaluate(
        facts(
            business_category="other",
            locations_count=None,
            company_size=None,
            product_interest=[],
            message="Applying for the job opening, my CV attached",
            source="manual",
            email_domain="gmail.com",
        )
    )
    assert result.score == 0


def test_classify_boundaries() -> None:
    assert rules.classify(70, hot_threshold=70, warm_threshold=40) == Temperature.HOT
    assert rules.classify(69, hot_threshold=70, warm_threshold=40) == Temperature.WARM
    assert rules.classify(40, hot_threshold=70, warm_threshold=40) == Temperature.WARM
    assert rules.classify(39, hot_threshold=70, warm_threshold=40) == Temperature.COLD


def test_signal_helpers() -> None:
    assert wants_unsubscribe("Please remove me from your list")
    assert wants_unsubscribe("UNSUBSCRIBE")
    assert not wants_unsubscribe("Can we talk next week?")
    found = detect_objections("Looks good but it's too expensive and we already use Fresha")
    assert {o.value for o in found} == {"price", "competitor"}
