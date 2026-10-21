from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.llm import provider
from app.llm.client import LLMClient

SessionDep = Annotated[Session, Depends(get_session)]


def get_llm() -> LLMClient | None:
    return provider.get_llm()


LLMDep = Annotated[LLMClient | None, Depends(get_llm)]


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_key
    if not expected:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")
