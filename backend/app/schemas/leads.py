from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.enums import (
    BusinessCategory,
    CompanySize,
    ContactChannel,
    LeadSource,
    Objection,
    PipelineStage,
)


class ConsentIn(BaseModel):
    email: bool = Field(description="Agreed to be contacted by email about this inquiry")
    marketing: bool = Field(False, description="Agreed to receive marketing emails")
    source_text: str | None = Field(
        None, max_length=200, description="Wording/version of the consent checkbox shown"
    )


class LeadBase(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(None, max_length=50)
    website: str | None = Field(None, max_length=300)
    business_category: BusinessCategory
    locations_count: int | None = Field(None, ge=1, le=10_000)
    company_size: CompanySize | None = None
    product_interest: list[str] = Field(default_factory=list, max_length=15)
    message: str | None = Field(None, max_length=5000)
    preferred_channel: ContactChannel = ContactChannel.EMAIL
    consent: ConsentIn

    @field_validator("product_interest")
    @classmethod
    def _short_items(cls, value: list[str]) -> list[str]:
        if any(len(v) > 60 for v in value):
            raise ValueError("product_interest items must be 60 characters or fewer")
        return value


class LeadCreate(LeadBase):
    """Full intake payload (manual entry, internal use)."""

    source: LeadSource = LeadSource.MANUAL
    source_detail: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=200)
    owner: str | None = Field(None, max_length=100)


class PublicFormIn(LeadBase):
    """What the public website forms post. Source is set by the endpoint."""

    # Honeypot: real visitors never see or fill this field.
    company_fax: str | None = Field(None, max_length=200)


class WebhookLeadIn(LeadBase):
    external_id: str = Field(min_length=1, max_length=200)
    source_type: LeadSource | None = Field(
        None, description="Original source if the integration knows it (e.g. demo_request)"
    )


class LeadUpdate(BaseModel):
    stage: PipelineStage | None = None
    owner: str | None = Field(None, max_length=100)
    objections: list[Objection] | None = None
    consent_email: bool | None = None
    consent_marketing: bool | None = None
    preferred_channel: ContactChannel | None = None
    do_not_contact: bool | None = None
    needs_review: bool | None = None
    locations_count: int | None = Field(None, ge=1, le=10_000)
    company_size: CompanySize | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str
    contact_name: str
    email: str
    phone: str | None
    website: str | None
    business_category: str
    locations_count: int | None
    company_size: str | None
    product_interest: list[str]
    message: str | None
    source: str
    source_detail: str | None
    stage: str
    owner: str | None
    objections: list[str]
    consent_email: bool
    consent_marketing: bool
    consent_captured_at: datetime | None
    consent_source: str | None
    preferred_channel: str
    do_not_contact: bool
    unsubscribed_at: datetime | None
    score: int | None
    temperature: str | None
    qualified_at: datetime | None
    needs_review: bool
    review_reason: str | None
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IntakeOut(BaseModel):
    lead: LeadOut
    created: bool
    duplicate_of: str | None = None


class PublicIntakeOut(BaseModel):
    """Public forms learn nothing about our CRM beyond 'received'."""

    status: str = "received"


class LeadPage(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    direction: str
    subject: str | None
    body: str | None
    actor: str | None
    meta: dict
    occurred_at: datetime


class ActivityCreate(BaseModel):
    kind: str = Field(pattern="^(note|call|inbound_email)$")
    subject: str | None = Field(None, max_length=300)
    body: str = Field(min_length=1, max_length=10_000)
    actor: str = Field("rep", max_length=100)
