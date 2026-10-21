"""Signed webhooks from integrations (form tools, booking widgets, the mail provider).

Requests carry ``X-BookFlow-Timestamp`` and ``X-BookFlow-Signature: sha256=<hmac>``
computed over ``"{timestamp}." + raw_body`` with ``WEBHOOK_SECRET``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Request, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core import clock
from app.core.config import get_settings
from app.core.security import verify_webhook
from app.db.models import Lead
from app.domain.enums import LeadSource
from app.schemas.leads import IntakeOut, LeadCreate, LeadOut, WebhookLeadIn
from app.schemas.workflow import InboundEmailWebhookIn, InboundResultOut
from app.services import leads
from app.services.conversations import record_inbound_reply

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _verified_body(request: Request, timestamp: str | None, signature: str | None) -> bytes:
    settings = get_settings()
    body = await request.body()
    if not verify_webhook(
        settings.webhook_secret,
        timestamp=timestamp,
        signature=signature,
        body=body,
        now=clock.utcnow(),
        tolerance_seconds=settings.webhook_tolerance_seconds,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    return body


def _parse(model, body: bytes):
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors(include_url=False)
        ) from exc


@router.post("/leads/{integration}", response_model=IntakeOut)
async def lead_webhook(
    request: Request,
    session: SessionDep,
    integration: Annotated[str, Path(pattern=r"^[a-z0-9_-]{1,50}$")],
    x_bookflow_timestamp: Annotated[str | None, Header()] = None,
    x_bookflow_signature: Annotated[str | None, Header()] = None,
) -> IntakeOut:
    """Idempotent on (integration, external_id): retried deliveries are no-ops."""
    body = await _verified_body(request, x_bookflow_timestamp, x_bookflow_signature)
    data: WebhookLeadIn = _parse(WebhookLeadIn, body)
    payload = LeadCreate(
        **data.model_dump(exclude={"external_id", "source_type"}),
        source=LeadSource.WEBHOOK,
        source_detail=f"{integration}:{data.source_type}" if data.source_type else integration,
        external_id=f"{integration}:{data.external_id}",
    )
    result = leads.intake_lead(session, payload)
    session.commit()
    return IntakeOut(
        lead=LeadOut.model_validate(result.lead),
        created=result.created,
        duplicate_of=result.duplicate_of,
    )


@router.post("/inbound-email", response_model=InboundResultOut)
async def inbound_email_webhook(
    request: Request,
    session: SessionDep,
    x_bookflow_timestamp: Annotated[str | None, Header()] = None,
    x_bookflow_signature: Annotated[str | None, Header()] = None,
) -> InboundResultOut:
    """A prospect replied (forwarded by the mail provider). Stops follow-ups for that lead."""
    body = await _verified_body(request, x_bookflow_timestamp, x_bookflow_signature)
    data: InboundEmailWebhookIn = _parse(InboundEmailWebhookIn, body)
    lead = session.scalar(select(Lead).where(Lead.email == data.from_email.lower()))
    if lead is None:
        return InboundResultOut(lead_id=None, matched=False)
    result = record_inbound_reply(
        session,
        lead,
        subject=data.subject,
        body=data.body,
        external_message_id=data.message_id,
        received_at=data.received_at,
    )
    session.commit()
    return InboundResultOut(
        lead_id=lead.id,
        matched=True,
        duplicate=result.duplicate,
        unsubscribed=result.unsubscribed,
        sequence_stopped=result.sequence_stopped,
    )
