from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.enums import EmailKind
from app.services.emails import guardrails, templates
from app.services.emails.context import EmailContext, Message


def ctx(kind: EmailKind, **overrides) -> EmailContext:
    base = dict(
        kind=kind,
        step=None,
        total_steps=None,
        first_name="Sam",
        business_name="Iron Temple Fitness",
        category="gym",
        category_label="gym",
        locations_count=3,
        source="demo_request",
        stage="new",
        modules=["memberships", "class_booking"],
        objections=["price", "switching_cost"],
        conversation=[
            Message(
                "inbound",
                "New demo request",
                "We need waitlists.",
                datetime(2026, 3, 2, tzinfo=UTC),
            )
        ],
        last_outbound_subject="Your BookFlow demo for Iron Temple Fitness",
        sender_name="Maya Chen",
        sender_title="Account Executive",
        angles=["members book classes from their phone", "memberships bill on their own"],
    )
    base.update(overrides)
    return EmailContext(**base)


@pytest.mark.parametrize("kind", list(EmailKind))
@pytest.mark.parametrize("first_name", ["Sam", None])
def test_every_template_passes_guardrails(kind: EmailKind, first_name: str | None) -> None:
    c = ctx(kind, first_name=first_name, step=1, total_steps=2)
    subject, body = templates.render(c)
    issues = guardrails.check(subject, body, facts_text=c.facts_text())
    assert issues == [], issues
    assert body.startswith(f"Hi {first_name or 'there'},")
    assert "Maya Chen" in body


def test_last_follow_up_closes_the_loop() -> None:
    _, body = templates.render(ctx(EmailKind.FOLLOW_UP, step=2, total_steps=2))
    assert "won't keep filling your inbox" in body


def test_trial_initial_response_mentions_trial_length() -> None:
    _, body = templates.render(ctx(EmailKind.INITIAL_RESPONSE, source="free_trial"))
    assert "14 days" in body


def test_unsupported_statistics_are_errors() -> None:
    issues = guardrails.check(
        "Cut no-shows",
        "BookFlow customers see 43% fewer no-shows and 3x revenue.",
        facts_text="BookFlow",
    )
    codes = [i.code for i in issues if i.severity == "error"]
    assert codes.count("unsupported_claim") == 2


def test_claims_from_the_catalog_are_allowed() -> None:
    c = ctx(EmailKind.OBJECTION_HANDLING)
    issues = guardrails.check(
        "Pricing", "Plans start at $49 per location.", facts_text=c.facts_text()
    )
    assert not guardrails.has_errors(issues)


def test_placeholders_and_ai_mentions_are_errors() -> None:
    issues = guardrails.check("Hi", "Hi [First Name], as an AI I think...", facts_text="")
    assert {i.code for i in issues} >= {"placeholder", "ai_self_reference"}


def test_cliches_are_warnings_not_errors() -> None:
    issues = guardrails.check(
        "Quick question", "I hope this email finds you well. Let's touch base.", facts_text=""
    )
    assert {i.code for i in issues} == {"cliche"}
    assert not guardrails.has_errors(issues)


def test_overlong_body_is_an_error() -> None:
    issues = guardrails.check("Hi", "word " * 200, facts_text="")
    assert any(i.code == "too_long" for i in issues)
