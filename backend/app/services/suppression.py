"""Suppression list: addresses and domains that must never be emailed."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Lead, SuppressionEntry
from app.domain.enums import StopReason, SuppressionKind, SuppressionReason


def normalize(kind: SuppressionKind, value: str) -> str:
    value = value.strip().lower()
    if kind == SuppressionKind.DOMAIN:
        value = value.lstrip("@")
    return value


def find_suppression(session: Session, email: str) -> SuppressionEntry | None:
    email = email.strip().lower()
    domain = email.rsplit("@", 1)[-1]
    return session.scalars(
        select(SuppressionEntry)
        .where(
            or_(
                (SuppressionEntry.kind == SuppressionKind.EMAIL)
                & (SuppressionEntry.value == email),
                (SuppressionEntry.kind == SuppressionKind.DOMAIN)
                & (SuppressionEntry.value == domain),
            )
        )
        .limit(1)
    ).first()


def add_suppression(
    session: Session,
    *,
    kind: SuppressionKind,
    value: str,
    reason: SuppressionReason,
    source: str | None = None,
    note: str | None = None,
) -> SuppressionEntry:
    """Idempotently suppress an address/domain and stop outreach to matching leads."""
    from app.services import followups  # local import: followups depends on this module

    value = normalize(kind, value)
    entry = session.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.kind == kind, SuppressionEntry.value == value
        )
    )
    if entry is None:
        entry = SuppressionEntry(kind=kind, value=value, reason=reason, source=source, note=note)
        session.add(entry)
        session.flush()

    if kind == SuppressionKind.EMAIL:
        matching = select(Lead).where(Lead.email == value)
    else:
        matching = select(Lead).where(Lead.email.like(f"%@{value}"))
    for lead in session.scalars(matching):
        followups.stop_active_sequence(session, lead, StopReason.SUPPRESSED)
        followups.cancel_open_drafts(session, lead, reason=f"suppressed ({reason})")
    return entry
