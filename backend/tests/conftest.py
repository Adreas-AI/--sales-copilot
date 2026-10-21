from __future__ import annotations

import os

# Tests never read a developer's .env or call real services.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["OPENAI_API_KEY"] = ""
os.environ["API_KEY"] = ""
os.environ["EMAIL_TRANSPORT"] = "log"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["UNSUBSCRIBE_SECRET"] = "test-unsubscribe-secret"

from collections.abc import Callable, Iterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.jobs.worker import Worker  # noqa: E402
from app.llm import provider  # noqa: E402
from app.services.emails import transport  # noqa: E402

T0 = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)  # a Monday morning


class FakeLLM:
    """Scriptable LLM: responses keyed by schema name, as dicts or callables."""

    model = "fake-llm"

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system: str, user: str, schema_name: str, schema: dict) -> dict:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        response = self.responses[schema_name]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(user)
        if isinstance(response, list):
            return response.pop(0)
        return response


@pytest.fixture(autouse=True)
def _settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def database() -> Iterator[None]:
    engine = db_session.configure_engine(os.environ["DATABASE_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_now(T0)
    yield
    clock.set_now(None)


@pytest.fixture(autouse=True)
def no_llm() -> Iterator[None]:
    provider.set_llm_override(None)
    yield
    provider.set_llm_override(None, active=False)


@pytest.fixture
def fake_llm() -> Callable[[dict[str, Any]], FakeLLM]:
    def install(responses: dict[str, Any]) -> FakeLLM:
        llm = FakeLLM(responses)
        provider.set_llm_override(llm)
        return llm

    return install


@pytest.fixture(autouse=True)
def outbox() -> Iterator[transport.LogTransport]:
    log_transport = transport.LogTransport()
    transport.set_transport(log_transport)
    yield log_transport
    transport.set_transport(None)


@pytest.fixture
def session() -> Iterator[Session]:
    with db_session.get_session_factory()() as s:
        yield s


@pytest.fixture
def client() -> TestClient:
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture
def worker() -> Worker:
    return Worker(db_session.get_session_factory(), worker_id="test-worker")


def lead_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "business_name": "Iron Temple Fitness",
        "contact_name": "Sam Rivera",
        "email": "sam@irontemple.example",
        "business_category": "gym",
        "locations_count": 3,
        "company_size": "21-50",
        "product_interest": ["memberships", "class booking"],
        "message": (
            "We run 3 gyms and our current booking software can't handle waitlists. "
            "Looking to switch before our contract ends next month. What does pricing look like?"
        ),
        "consent": {"email": True, "marketing": False, "source_text": "demo form v3"},
    }
    payload.update(overrides)
    return payload
