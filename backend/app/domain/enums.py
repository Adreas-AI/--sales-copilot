"""Domain vocabulary. Stored as plain strings so the schema stays portable."""

from __future__ import annotations

from enum import StrEnum


class BusinessCategory(StrEnum):
    GYM = "gym"
    FITNESS_STUDIO = "fitness_studio"
    BEAUTY_SALON = "beauty_salon"
    BARBERSHOP = "barbershop"
    WELLNESS_STUDIO = "wellness_studio"
    SPA = "spa"
    OTHER = "other"


class CompanySize(StrEnum):
    S1_5 = "1-5"
    S6_20 = "6-20"
    S21_50 = "21-50"
    S51_200 = "51-200"
    S200_PLUS = "200+"


class LeadSource(StrEnum):
    WEBSITE_FORM = "website_form"
    DEMO_REQUEST = "demo_request"
    FREE_TRIAL = "free_trial"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class PipelineStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    DEMO_SCHEDULED = "demo_scheduled"
    DEMO_COMPLETED = "demo_completed"
    TRIAL = "trial"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


# Once a person is actively working the deal, automated follow-ups step aside.
SEQUENCE_STOP_STAGES = frozenset(
    {
        PipelineStage.ENGAGED,
        PipelineStage.DEMO_SCHEDULED,
        PipelineStage.DEMO_COMPLETED,
        PipelineStage.NEGOTIATION,
        PipelineStage.WON,
        PipelineStage.LOST,
    }
)


class Temperature(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class ContactChannel(StrEnum):
    EMAIL = "email"
    PHONE = "phone"


class ActivityKind(StrEnum):
    INQUIRY = "inquiry"
    INBOUND_EMAIL = "inbound_email"
    OUTBOUND_EMAIL = "outbound_email"
    NOTE = "note"
    CALL = "call"
    STAGE_CHANGE = "stage_change"
    QUALIFIED = "qualified"
    DRAFT_CREATED = "draft_created"
    SEQUENCE = "sequence"
    UNSUBSCRIBED = "unsubscribed"
    MANUAL_REVIEW = "manual_review"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class EmailKind(StrEnum):
    INITIAL_RESPONSE = "initial_response"
    DEMO_INVITATION = "demo_invitation"
    POST_DEMO_FOLLOWUP = "post_demo_followup"
    TRIAL_ACTIVATION_REMINDER = "trial_activation_reminder"
    OBJECTION_HANDLING = "objection_handling"
    RE_ENGAGEMENT = "re_engagement"
    FOLLOW_UP = "follow_up"


# Marketing-type messages need explicit marketing consent, not just consent to a reply.
MARKETING_EMAIL_KINDS = frozenset({EmailKind.RE_ENGAGEMENT})


class DraftStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    CANCELLED = "cancelled"


OPEN_DRAFT_STATUSES = frozenset({DraftStatus.PENDING_REVIEW, DraftStatus.APPROVED})


class SequenceStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"


class StopReason(StrEnum):
    PROSPECT_REPLIED = "prospect_replied"
    UNSUBSCRIBED = "unsubscribed"
    SUPPRESSED = "suppressed"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    STAGE_CHANGED = "stage_changed"
    MANUAL = "manual"


class TaskAction(StrEnum):
    FOLLOWUP_DRAFT = "followup_draft"
    MANUAL_REVIEW = "manual_review"


class TaskStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class SuppressionKind(StrEnum):
    EMAIL = "email"
    DOMAIN = "domain"


class SuppressionReason(StrEnum):
    UNSUBSCRIBE = "unsubscribe"
    BOUNCE = "bounce"
    COMPLAINT = "complaint"
    MANUAL = "manual"
    LEGAL = "legal"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEAD = "dead"


class Objection(StrEnum):
    PRICE = "price"
    SWITCHING_COST = "switching_cost"
    COMPETITOR = "competitor"
    TIMING = "timing"
    STAFF_ADOPTION = "staff_adoption"
    MISSING_FEATURE = "missing_feature"
    CONTRACT_LOCK_IN = "contract_lock_in"
