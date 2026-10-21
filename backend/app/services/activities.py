from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Activity, Lead
from app.domain.enums import ActivityKind, Direction


def record_activity(
    session: Session,
    lead: Lead,
    kind: ActivityKind,
    *,
    direction: Direction = Direction.INTERNAL,
    subject: str | None = None,
    body: str | None = None,
    actor: str | None = "system",
    occurred_at: datetime | None = None,
    external_message_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Activity:
    activity = Activity(
        lead=lead,
        kind=kind,
        direction=direction,
        subject=subject,
        body=body,
        actor=actor,
        occurred_at=occurred_at or clock.utcnow(),
        external_message_id=external_message_id,
        meta=meta or {},
    )
    session.add(activity)
    return activity
