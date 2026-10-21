"""Everything an email is allowed to know, gathered in one place.

Both the template writer and the AI writer read only from ``EmailContext``, and the
guardrails check the output against ``facts_text()``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Activity, Lead
from app.domain import catalog
from app.domain.enums import ActivityKind, EmailKind

CONVERSATION_KINDS = (
    ActivityKind.INQUIRY,
    ActivityKind.INBOUND_EMAIL,
    ActivityKind.OUTBOUND_EMAIL,
)
MAX_MESSAGES = 6
MAX_MESSAGE_CHARS = 800


@dataclass
class Message:
    direction: str
    subject: str | None
    body: str
    at: datetime


@dataclass
class EmailContext:
    kind: EmailKind
    step: int | None
    total_steps: int | None
    first_name: str | None
    business_name: str
    category: str
    category_label: str
    locations_count: int | None
    source: str
    stage: str
    modules: list[str]
    objections: list[str]
    conversation: list[Message]
    last_outbound_subject: str | None
    sender_name: str
    sender_title: str
    instructions: str | None = None
    angles: list[str] = field(default_factory=list)

    @property
    def greeting_name(self) -> str:
        return self.first_name or "there"

    @property
    def module_labels(self) -> list[str]:
        return [catalog.MODULES[k].label for k in self.modules]

    def facts_text(self) -> str:
        lines = [
            self.business_name,
            self.category_label,
            f"locations: {self.locations_count}" if self.locations_count else "",
            *[m.body for m in self.conversation],
            self.instructions or "",
            catalog.product_facts_text(),
        ]
        return "\n".join(line for line in lines if line)

    def snapshot(self) -> dict:
        data = asdict(self)
        data["conversation"] = [{**asdict(m), "at": m.at.isoformat()} for m in self.conversation]
        return data


def build_context(
    session: Session,
    lead: Lead,
    kind: EmailKind,
    *,
    step: int | None = None,
    total_steps: int | None = None,
    instructions: str | None = None,
) -> EmailContext:
    settings = get_settings()
    rows = list(
        session.scalars(
            select(Activity)
            .where(Activity.lead_id == lead.id, Activity.kind.in_(CONVERSATION_KINDS))
            .order_by(Activity.occurred_at.desc())
            .limit(MAX_MESSAGES)
        )
    )
    rows.reverse()
    conversation = [
        Message(
            direction=a.direction,
            subject=a.subject,
            body=(a.body or "")[:MAX_MESSAGE_CHARS],
            at=a.occurred_at,
        )
        for a in rows
        if a.body
    ]
    last_outbound = next(
        (a.subject for a in reversed(rows) if a.kind == ActivityKind.OUTBOUND_EMAIL), None
    )
    angles = list(catalog.CATEGORY_ANGLES.get(lead.business_category, ()))
    if not angles:
        angles = list(catalog.CATEGORY_ANGLES["other"])
    return EmailContext(
        kind=kind,
        step=step,
        total_steps=total_steps,
        first_name=lead.first_name,
        business_name=lead.business_name,
        category=lead.business_category,
        category_label=catalog.CATEGORY_LABELS.get(lead.business_category, "business"),
        locations_count=lead.locations_count,
        source=lead.source,
        stage=lead.stage,
        modules=catalog.match_modules(", ".join(lead.product_interest or []), lead.message),
        objections=list(lead.objections or []),
        conversation=conversation,
        last_outbound_subject=last_outbound,
        sender_name=settings.sender_name,
        sender_title=settings.sender_title,
        instructions=instructions,
        angles=angles,
    )
