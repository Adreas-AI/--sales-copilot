"""The Day 0 → Day 10 workflow, driven by a frozen clock and the real worker."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import EmailDraft, FollowUpSequence, FollowUpTask, Job, Lead
from app.jobs.worker import Worker
from app.services import followups
from tests.conftest import lead_payload

pytestmark = pytest.mark.integration


def new_lead(client: TestClient, worker: Worker, **overrides) -> uuid.UUID:
    client.post("/api/v1/intake/forms/demo", json=lead_payload(**overrides))
    worker.drain()
    lead = client.get("/api/v1/leads").json()["items"][0]
    return uuid.UUID(lead["id"])


def drafts(session: Session, lead_id: uuid.UUID) -> list[EmailDraft]:
    session.expire_all()
    return list(
        session.scalars(
            select(EmailDraft).where(EmailDraft.lead_id == lead_id).order_by(EmailDraft.created_at)
        )
    )


def send_all_open(client: TestClient, lead_id: uuid.UUID) -> None:
    for d in client.get(f"/api/v1/leads/{lead_id}").json()["drafts"]:
        if d["status"] == "pending_review":
            assert (
                client.post(
                    f"/api/v1/drafts/{d['id']}/approve", json={"reviewer": "dana"}
                ).status_code
                == 200
            )
            assert (
                client.post(f"/api/v1/drafts/{d['id']}/send", json={"reviewer": "dana"}).status_code
                == 200
            )


def test_day_0_qualifies_drafts_and_schedules(
    client: TestClient, worker: Worker, session: Session
) -> None:
    lead_id = new_lead(client, worker)
    detail = client.get(f"/api/v1/leads/{lead_id}").json()

    assert detail["lead"]["temperature"] == "hot"
    assert detail["latest_qualification"]["method"] == "rules"
    [draft] = detail["drafts"]
    assert draft["kind"] == "demo_invitation" and draft["status"] == "pending_review"
    assert draft["generated_by"] == "template"

    [sequence] = detail["sequences"]
    assert sequence["status"] == "active"
    plan = [(t["day"], t["action"], t["status"]) for t in sequence["tasks"]]
    assert plan == [
        (2, "followup_draft", "scheduled"),
        (5, "followup_draft", "scheduled"),
        (10, "manual_review", "scheduled"),
    ]
    assert sequence["tasks"][0]["due_at"].startswith("2026-03-04T09:00")


def test_full_unanswered_timeline(
    client: TestClient, worker: Worker, session: Session, outbox
) -> None:
    lead_id = new_lead(client, worker)
    send_all_open(client, lead_id)  # Day 0: rep approves and sends the first response
    assert len(outbox.sent) == 1
    assert "Unsubscribe:" in outbox.sent[0]["body"]
    assert outbox.sent[0]["headers"]["List-Unsubscribe"].startswith("<http")

    clock.advance(timedelta(days=1))
    worker.drain()
    assert len(drafts(session, lead_id)) == 1  # nothing due yet

    clock.advance(timedelta(days=1, minutes=1))  # Day 2
    worker.drain()
    ds = drafts(session, lead_id)
    assert [(d.kind, d.followup_step, d.status) for d in ds[1:]] == [
        ("follow_up", 1, "pending_review")
    ]
    assert ds[1].subject.startswith("Re: ")
    send_all_open(client, lead_id)

    clock.advance(timedelta(days=3))  # Day 5
    worker.drain()
    ds = drafts(session, lead_id)
    assert ds[-1].followup_step == 2
    assert "won't keep filling your inbox" in ds[-1].body
    send_all_open(client, lead_id)

    clock.advance(timedelta(days=5))  # Day 10
    worker.drain()
    lead = client.get(f"/api/v1/leads/{lead_id}").json()
    assert lead["lead"]["needs_review"] is True
    assert "No reply 10 days" in lead["lead"]["review_reason"]
    assert lead["sequences"][0]["status"] == "completed"
    assert len(outbox.sent) == 3


def test_reply_stops_sequence_and_cancels_queued_draft(
    client: TestClient, worker: Worker, session: Session
) -> None:
    lead_id = new_lead(client, worker)
    send_all_open(client, lead_id)
    clock.advance(timedelta(days=2, minutes=1))
    worker.drain()
    followup = drafts(session, lead_id)[-1]
    assert followup.status == "pending_review"

    clock.advance(timedelta(hours=3))
    res = client.post(
        f"/api/v1/leads/{lead_id}/replies",
        json={
            "body": "Thanks! Thursday works. It's a bit expensive though.",
            "message_id": "<r1@mail>",
        },
    )
    assert res.json()["sequence_stopped"] is True

    detail = client.get(f"/api/v1/leads/{lead_id}").json()
    seq = detail["sequences"][0]
    assert (seq["status"], seq["stop_reason"]) == ("stopped", "prospect_replied")
    assert {t["status"] for t in seq["tasks"][1:]} == {"cancelled"}
    assert drafts(session, lead_id)[-1].status == "cancelled"
    assert detail["lead"]["stage"] == "engaged"
    assert detail["lead"]["objections"] == ["price"]

    # duplicate delivery of the same reply is ignored
    again = client.post(
        f"/api/v1/leads/{lead_id}/replies", json={"body": "dup", "message_id": "<r1@mail>"}
    )
    assert again.json()["duplicate"] is True

    worker.drain()  # re-qualification job from the reply
    assert len(client.get(f"/api/v1/leads/{lead_id}/qualifications").json()) == 2

    clock.advance(timedelta(days=30))
    worker.drain()
    assert all(d.status != "pending_review" for d in drafts(session, lead_id))


def test_task_rechecks_stop_conditions_even_if_event_was_missed(
    client: TestClient, worker: Worker, session: Session
) -> None:
    lead_id = new_lead(client, worker)
    send_all_open(client, lead_id)
    # Simulate a reply that bypassed the API (e.g. imported directly into the DB).
    lead = session.get(Lead, lead_id)
    lead.last_inbound_at = clock.utcnow() + timedelta(hours=1)
    session.commit()

    clock.advance(timedelta(days=2, minutes=1))
    worker.drain()
    assert len(drafts(session, lead_id)) == 1
    seq = session.scalar(select(FollowUpSequence).where(FollowUpSequence.lead_id == lead_id))
    assert seq.stop_reason == "prospect_replied"


def test_unsubscribe_link_stops_everything(
    client: TestClient, worker: Worker, session: Session
) -> None:
    lead_id = new_lead(client, worker)
    from app.services.emails.review import unsubscribe_url

    url = unsubscribe_url("sam@irontemple.example")
    path = url.split("8000", 1)[1]
    page = client.get(path)
    assert page.status_code == 200 and "sam@irontemple.example" in page.text
    assert client.get(path.replace("token=", "token=x")).status_code == 400

    assert client.post(path).status_code == 200
    detail = client.get(f"/api/v1/leads/{lead_id}").json()
    assert detail["lead"]["do_not_contact"] is True
    assert detail["sequences"][0]["stop_reason"] == "unsubscribed"
    assert detail["drafts"][0]["status"] == "cancelled"
    assert (
        client.post(f"/api/v1/leads/{lead_id}/drafts", json={"kind": "follow_up"}).status_code
        == 409
    )
    sup = client.get("/api/v1/suppressions").json()
    assert sup[0]["value"] == "sam@irontemple.example" and sup[0]["reason"] == "unsubscribe"
    assert client.delete(f"/api/v1/suppressions/{sup[0]['id']}").status_code == 409


def test_reply_asking_to_stop_is_treated_as_unsubscribe(client: TestClient, worker: Worker) -> None:
    lead_id = new_lead(client, worker)
    res = client.post(f"/api/v1/leads/{lead_id}/replies", json={"body": "Please stop emailing me."})
    assert res.json()["unsubscribed"] is True
    assert client.get(f"/api/v1/leads/{lead_id}").json()["lead"]["unsubscribed_at"] is not None


def test_domain_suppression_blocks_send_at_the_last_moment(
    client: TestClient, worker: Worker
) -> None:
    lead_id = new_lead(client, worker)
    draft = client.get(f"/api/v1/leads/{lead_id}").json()["drafts"][0]
    client.post(f"/api/v1/drafts/{draft['id']}/approve", json={"reviewer": "dana"})
    # Bypass the event hook to prove the send-time check works on its own.
    from app.db.models import SuppressionEntry
    from app.db.session import get_session_factory

    with get_session_factory().begin() as s:
        s.add(SuppressionEntry(kind="domain", value="irontemple.example", reason="legal"))
    res = client.post(f"/api/v1/drafts/{draft['id']}/send", json={"reviewer": "dana"})
    assert res.status_code == 409
    assert res.json()["code"] == "contact_not_allowed"
    assert client.get(f"/api/v1/drafts/{draft['id']}").json()["status"] == "cancelled"


def test_open_draft_prevents_stacked_follow_ups(
    client: TestClient, worker: Worker, session: Session
) -> None:
    lead_id = new_lead(client, worker)  # initial draft left unreviewed
    clock.advance(timedelta(days=2, minutes=1))
    worker.drain()
    ds = drafts(session, lead_id)
    assert len(ds) == 1
    task = session.scalar(select(FollowUpTask).where(FollowUpTask.step == 1))
    assert task.status == "skipped" and "awaiting review" in task.outcome


def test_processing_is_idempotent(client: TestClient, worker: Worker, session: Session) -> None:
    lead_id = new_lead(client, worker)
    send_all_open(client, lead_id)
    clock.advance(timedelta(days=2, minutes=1))
    with session.begin():
        assert followups.enqueue_due_tasks(session) == 1
    with session.begin():
        assert followups.enqueue_due_tasks(session) == 1  # same task, same job
    assert session.scalar(select(Job).where(Job.kind == "process_followup_task")) is not None
    worker.drain()

    session.expire_all()
    task = session.scalar(select(FollowUpTask).where(FollowUpTask.step == 1))
    result = followups.process_task(session, task.id, llm=None)  # replay
    session.commit()
    assert "nothing to do" in result.outcome
    assert len([d for d in drafts(session, lead_id) if d.followup_step == 1]) == 1
    jobs = session.scalars(select(Job).where(Job.kind == "process_followup_task")).all()
    assert len(jobs) == 1


def test_phone_preference_skips_email_automation(client: TestClient, worker: Worker) -> None:
    lead_id = new_lead(client, worker, preferred_channel="phone")
    detail = client.get(f"/api/v1/leads/{lead_id}").json()
    assert detail["drafts"] == [] and detail["sequences"] == []
    assert detail["lead"]["needs_review"] is True
    assert "phone" in detail["lead"]["review_reason"]


def test_cold_lead_gets_reply_but_no_sequence(client: TestClient, worker: Worker) -> None:
    lead_id = new_lead(
        client,
        worker,
        business_category="other",
        locations_count=None,
        company_size=None,
        product_interest=[],
        message="Just browsing.",
    )
    detail = client.get(f"/api/v1/leads/{lead_id}").json()
    assert detail["lead"]["temperature"] == "cold"
    assert len(detail["drafts"]) == 1
    assert detail["sequences"] == []


def test_stage_change_stops_sequence(client: TestClient, worker: Worker) -> None:
    lead_id = new_lead(client, worker)
    client.patch(f"/api/v1/leads/{lead_id}", json={"stage": "demo_scheduled", "owner": "dana"})
    seq = client.get(f"/api/v1/leads/{lead_id}").json()["sequences"][0]
    assert seq["stop_reason"] == "stage_changed:demo_scheduled"


def test_non_buyer_is_routed_to_a_person(client: TestClient, worker: Worker) -> None:
    lead_id = new_lead(
        client, worker, message="Hi, we are an SEO agency with an SEO package for gyms."
    )
    detail = client.get(f"/api/v1/leads/{lead_id}").json()
    assert detail["drafts"] == []
    assert detail["lead"]["needs_review"] is True


def test_cadence_is_configurable(
    client: TestClient, worker: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("FOLLOWUP_STEP_DAYS", "1,3,6")
    monkeypatch.setenv("MANUAL_REVIEW_DAY", "14")
    get_settings.cache_clear()
    lead_id = new_lead(client, worker)
    tasks = client.get(f"/api/v1/leads/{lead_id}").json()["sequences"][0]["tasks"]
    assert [t["day"] for t in tasks] == [1, 3, 6, 14]
    assert client.get("/api/v1/followups/cadence").json()["step_days"] == [1, 3, 6]


def test_overdue_and_unanswered_reports(client: TestClient, worker: Worker) -> None:
    new_lead(client, worker)
    assert client.get("/api/v1/leads/unanswered").json() == []  # too fresh
    clock.advance(timedelta(hours=25))
    assert len(client.get("/api/v1/leads/unanswered").json()) == 1
    overdue = client.get("/api/v1/followups/overdue").json()
    assert len(overdue["drafts"]) == 1  # initial draft waiting > 24h
    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["overdue_drafts"] == 1 and summary["unanswered"] == 1
    assert summary["by_temperature"] == {"hot": 1}
