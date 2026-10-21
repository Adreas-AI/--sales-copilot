"""Deterministic email copy. Used when AI is off, and as the fallback when AI output
fails the guardrails. Written to read like a person, not a campaign.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain import catalog
from app.domain.enums import EmailKind, LeadSource
from app.services.emails.context import EmailContext


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _signoff(ctx: EmailContext) -> str:
    return f"Best,\n{ctx.sender_name}\n{ctx.sender_title}, {catalog.PRODUCT_NAME}"


def _topic(ctx: EmailContext) -> str:
    if ctx.module_labels:
        return _join(ctx.module_labels[:2]) + f" for {ctx.business_name}"
    return f"BookFlow for {ctx.business_name}"


def _multi_location_line(ctx: EmailContext) -> str:
    if ctx.locations_count and ctx.locations_count > 1:
        return (
            f"With {ctx.locations_count} locations, you'd also run every calendar and report "
            "from one account, with staff permissions per location."
        )
    return ""


def _paragraphs(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


def initial_response(ctx: EmailContext) -> tuple[str, str]:
    if ctx.source == LeadSource.FREE_TRIAL:
        body = _paragraphs(
            f"Hi {ctx.greeting_name},",
            f"Thanks for starting a BookFlow trial for {ctx.business_name}. You have "
            f"{catalog.TRIAL_DAYS} days on the full product.",
            "The quickest way to see whether it fits: add your main services, connect one "
            "staff calendar, then make a test booking from your phone.",
            "If you'd rather not do that alone, I can set it up with you on a short call and "
            "import your client list while we're at it.",
            _signoff(ctx),
        )
        return f"Your BookFlow trial for {ctx.business_name}", body

    interest = ""
    if ctx.module_labels:
        interest = f", and specifically about {_join(ctx.module_labels[:3])}"
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        f"Thanks for getting in touch about BookFlow{interest}.",
        f"For a {ctx.category_label} like yours, the part most teams notice first is that "
        f"{ctx.angles[0]}. " + _multi_location_line(ctx),
        "Would a 20-minute call this week help? I can show you how it would work at "
        f"{ctx.business_name} and answer any questions about setup.",
        _signoff(ctx),
    )
    return f"BookFlow for {ctx.business_name}", body


def demo_invitation(ctx: EmailContext) -> tuple[str, str]:
    if ctx.module_labels:
        focus = _join(ctx.module_labels[:3])
    else:
        focus = f"how booking, reminders and payments would work for your {ctx.category_label}"
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        f"Thanks for requesting a demo. I'll keep it to about 25 minutes and focus on {focus}.",
        _multi_location_line(ctx),
        "Could you reply with two or three times that work this week or next? If someone "
        f"else at {ctx.business_name} will be part of the decision, they're welcome to join.",
        _signoff(ctx),
    )
    return f"Your BookFlow demo for {ctx.business_name}", body


def follow_up(ctx: EmailContext) -> tuple[str, str]:
    subject = (
        f"Re: {ctx.last_outbound_subject}"
        if ctx.last_outbound_subject and not ctx.last_outbound_subject.startswith("Re:")
        else ctx.last_outbound_subject or f"BookFlow for {ctx.business_name}"
    )
    is_last = ctx.step is not None and ctx.total_steps is not None and ctx.step >= ctx.total_steps
    if is_last:
        body = _paragraphs(
            f"Hi {ctx.greeting_name},",
            "I haven't heard back, so I'll assume now isn't the right moment and won't keep "
            "filling your inbox.",
            f"If {_topic(ctx)} comes back onto your list, reply to this email and I'll pick it "
            "up from there.",
            _signoff(ctx),
        )
    else:
        body = _paragraphs(
            f"Hi {ctx.greeting_name},",
            f"Following up on my last note about {_topic(ctx)}. If a call is easier, reply "
            "with a time that suits you and I'll send an invite.",
            "And if the timing isn't right, just say so. That's completely fine.",
            _signoff(ctx),
        )
    return subject, body


def post_demo_followup(ctx: EmailContext) -> tuple[str, str]:
    keys = ctx.modules[:3] or ["scheduling", "reminders", "crm"]
    recap = "\n".join(
        f"- {catalog.MODULES[k].description[0].upper()}{catalog.MODULES[k].description[1:]}"
        for k in keys
    )
    objection = ""
    if ctx.objections and ctx.objections[0] in catalog.OBJECTION_RESPONSES:
        phrase, response = catalog.OBJECTION_RESPONSES[ctx.objections[0]]
        objection = f"You mentioned {phrase}. {response}"
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        "Thanks for your time on the demo. A quick recap of what we covered:",
        recap,
        objection,
        f"Would it help if I set up a trial account with your services already loaded, so "
        f"the team at {ctx.business_name} can try it this week?",
        _signoff(ctx),
    )
    return "Following up on your BookFlow demo", body


def trial_activation_reminder(ctx: EmailContext) -> tuple[str, str]:
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        f"Checking in on your BookFlow trial for {ctx.business_name}. If you haven't had a "
        "chance to set it up yet, three steps get you to a real test:",
        "1. Add your main services\n2. Connect one staff calendar\n3. Make a test booking from your phone",
        "That takes about 15 minutes. I'm also happy to do it with you on a call, or import "
        "your existing client list for you.",
        _signoff(ctx),
    )
    return "Getting your BookFlow trial set up", body


def objection_handling(ctx: EmailContext) -> tuple[str, str]:
    known = [o for o in ctx.objections if o in catalog.OBJECTION_RESPONSES][:2]
    if not known:
        known = ["missing_feature"]
    phrases = [catalog.OBJECTION_RESPONSES[o][0] for o in known]
    responses = [catalog.OBJECTION_RESPONSES[o][1] for o in known]
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        f"Thanks for being upfront about {_join(phrases)}.",
        *responses,
        "If it's useful, I can walk through exactly how this would look for "
        f"{ctx.business_name} on a short call.",
        _signoff(ctx),
    )
    subject = (
        f"Re: {ctx.last_outbound_subject}"
        if ctx.last_outbound_subject
        else "Your questions about BookFlow"
    )
    return subject, body


def re_engagement(ctx: EmailContext) -> tuple[str, str]:
    angle = ctx.angles[-1]
    body = _paragraphs(
        f"Hi {ctx.greeting_name},",
        f"It's been a while since we spoke about {_topic(ctx)}.",
        f"One thing I didn't mention before: {angle}.",
        "If it's worth another look, I'm happy to set up a short call. If not, no need to reply.",
        _signoff(ctx),
    )
    return f"BookFlow for {ctx.business_name}", body


WRITERS: dict[EmailKind, Callable[[EmailContext], tuple[str, str]]] = {
    EmailKind.INITIAL_RESPONSE: initial_response,
    EmailKind.DEMO_INVITATION: demo_invitation,
    EmailKind.FOLLOW_UP: follow_up,
    EmailKind.POST_DEMO_FOLLOWUP: post_demo_followup,
    EmailKind.TRIAL_ACTIVATION_REMINDER: trial_activation_reminder,
    EmailKind.OBJECTION_HANDLING: objection_handling,
    EmailKind.RE_ENGAGEMENT: re_engagement,
}


def render(ctx: EmailContext) -> tuple[str, str]:
    return WRITERS[ctx.kind](ctx)
