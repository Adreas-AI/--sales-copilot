from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import sign_webhook
from app.db.models import Activity, Job, Lead
from tests.conftest import lead_payload

pytestmark = pytest.mark.integration


def signed(body: dict, secret: str = "test-webhook-secret") -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(body).encode()
    ts = str(int(clock.utcnow().timestamp()))
    return raw, {
        "X-BookFlow-Timestamp": ts,
        "X-BookFlow-Signature": sign_webhook(secret, ts, raw),
        "Content-Type": "application/json",
    }


def test_manual_lead_is_created_and_qualification_queued(
    client: TestClient, session: Session
) -> None:
    res = client.post("/api/v1/leads", json=lead_payload(source="manual", owner="dana"))
    assert res.status_code == 201
    body = res.json()
    assert body["created"] is True
    lead = body["lead"]
    assert lead["email"] == "sam@irontemple.example"
    assert lead["consent_email"] is True and lead["consent_source"] == "demo form v3"
    assert lead["stage"] == "new"

    job = session.scalar(select(Job))
    assert job.kind == "qualify_lead" and job.idempotency_key == f"qualify:{lead['id']}:intake"

    detail = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert detail["lead"]["business_name"] == "Iron Temple Fitness"
    timeline = client.get(f"/api/v1/leads/{lead['id']}/timeline").json()
    assert timeline[0]["kind"] == "inquiry"


@pytest.mark.parametrize(
    ("form", "source", "stage"),
    [
        ("contact", "website_form", "new"),
        ("demo", "demo_request", "new"),
        ("trial", "free_trial", "trial"),
    ],
)
def test_public_forms_set_source(
    client: TestClient, session: Session, form: str, source: str, stage: str
) -> None:
    res = client.post(f"/api/v1/intake/forms/{form}", json=lead_payload())
    assert res.status_code == 202
    assert res.json() == {"status": "received"}  # nothing about our CRM leaks out
    lead = session.scalar(select(Lead))
    assert (lead.source, lead.stage, lead.source_detail) == (source, stage, f"website:{form}")


def test_honeypot_submissions_are_dropped(client: TestClient, session: Session) -> None:
    res = client.post("/api/v1/intake/forms/demo", json=lead_payload(company_fax="555-0100"))
    assert res.status_code == 202
    assert session.scalar(select(func.count()).select_from(Lead)) == 0


def test_validation_errors(client: TestClient) -> None:
    assert client.post("/api/v1/leads", json=lead_payload(email="not-an-email")).status_code == 422
    assert (
        client.post("/api/v1/leads", json=lead_payload(business_category="bakery")).status_code
        == 422
    )
    assert client.post("/api/v1/leads", json=lead_payload(locations_count=0)).status_code == 422
    no_consent = lead_payload()
    del no_consent["consent"]
    assert client.post("/api/v1/leads", json=no_consent).status_code == 422


def test_duplicate_email_merges_instead_of_duplicating(
    client: TestClient, session: Session
) -> None:
    first = client.post(
        "/api/v1/leads", json=lead_payload(locations_count=None, product_interest=["booking"])
    ).json()
    second = client.post(
        "/api/v1/intake/forms/demo",
        json=lead_payload(
            email="SAM@irontemple.example", locations_count=4, message="Following up on my form"
        ),
    )
    assert second.status_code == 202
    assert session.scalar(select(func.count()).select_from(Lead)) == 1
    lead = session.get(Lead, __import__("uuid").UUID(first["lead"]["id"]))
    session.refresh(lead)
    assert lead.locations_count == 4  # gap filled
    assert lead.product_interest == ["booking", "memberships", "class booking"]
    inquiries = session.scalar(
        select(func.count()).select_from(Activity).where(Activity.kind == "inquiry")
    )
    assert inquiries == 2


def test_webhook_requires_valid_signature(client: TestClient) -> None:
    body = {**lead_payload(), "external_id": "evt_1"}
    raw, headers = signed(body, secret="wrong")
    assert (
        client.post("/api/v1/webhooks/leads/typeform", content=raw, headers=headers).status_code
        == 401
    )
    assert client.post("/api/v1/webhooks/leads/typeform", json=body).status_code == 401


def test_webhook_is_idempotent_on_external_id(client: TestClient, session: Session) -> None:
    body = {**lead_payload(), "external_id": "evt_1", "source_type": "demo_request"}
    raw, headers = signed(body)
    first = client.post("/api/v1/webhooks/leads/typeform", content=raw, headers=headers)
    retry = client.post("/api/v1/webhooks/leads/typeform", content=raw, headers=headers)
    assert first.status_code == retry.status_code == 200
    assert first.json()["created"] is True
    assert retry.json() == {**retry.json(), "created": False, "duplicate_of": "external_id"}
    lead = session.scalar(select(Lead))
    assert (lead.source, lead.source_detail, lead.external_id) == (
        "webhook",
        "typeform:demo_request",
        "typeform:evt_1",
    )
    assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_api_key_protects_internal_endpoints(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("API_KEY", "k-123")
    get_settings.cache_clear()
    assert client.get("/api/v1/leads").status_code == 401
    assert client.get("/api/v1/leads", headers={"X-API-Key": "k-123"}).status_code == 200
    # public intake stays open
    assert client.post("/api/v1/intake/forms/demo", json=lead_payload()).status_code == 202


def test_list_filters_and_search(client: TestClient) -> None:
    client.post("/api/v1/leads", json=lead_payload())
    client.post(
        "/api/v1/leads",
        json=lead_payload(
            email="ana@glowstudio.example",
            business_name="Glow Studio",
            business_category="beauty_salon",
        ),
    )
    page = client.get("/api/v1/leads", params={"q": "glow"}).json()
    assert page["total"] == 1 and page["items"][0]["business_name"] == "Glow Studio"
    assert client.get("/api/v1/leads", params={"limit": 1}).json()["total"] == 2
