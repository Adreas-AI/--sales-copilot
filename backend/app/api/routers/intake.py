"""Public endpoints the BookFlow website posts to. No API key; minimal response."""

from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter, status

from app.api.deps import SessionDep
from app.core.logging import get_logger
from app.domain.enums import LeadSource
from app.schemas.leads import LeadCreate, PublicFormIn, PublicIntakeOut
from app.services import leads

log = get_logger(__name__)

router = APIRouter(prefix="/intake", tags=["public intake"])


class FormType(StrEnum):
    CONTACT = "contact"
    DEMO = "demo"
    TRIAL = "trial"


FORM_SOURCES = {
    FormType.CONTACT: LeadSource.WEBSITE_FORM,
    FormType.DEMO: LeadSource.DEMO_REQUEST,
    FormType.TRIAL: LeadSource.FREE_TRIAL,
}


@router.post(
    "/forms/{form_type}", response_model=PublicIntakeOut, status_code=status.HTTP_202_ACCEPTED
)
def submit_form(form_type: FormType, data: PublicFormIn, session: SessionDep) -> PublicIntakeOut:
    if data.company_fax:
        log.info("Dropped %s form submission caught by honeypot", form_type)
        return PublicIntakeOut()
    payload = LeadCreate(
        **data.model_dump(exclude={"company_fax"}),
        source=FORM_SOURCES[form_type],
        source_detail=f"website:{form_type}",
    )
    leads.intake_lead(session, payload)
    session.commit()
    return PublicIntakeOut()
