from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import SessionDep, require_api_key
from app.api.routers import drafts, intake, leads, operations, unsubscribe, webhooks
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.errors import DomainError


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="AI Sales Copilot",
        version="0.1.0",
        description="Lead qualification, AI-drafted emails with human approval, and "
        "restart-safe follow-up automation for BookFlow's sales team.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code, "details": exc.details},
        )

    @app.get("/health", tags=["health"])
    def health(session: SessionDep) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ok"}

    internal = [Depends(require_api_key)]
    for module in (leads, drafts, operations):
        app.include_router(module.router, prefix="/api/v1", dependencies=internal)
    # Public (website forms, signed webhooks, unsubscribe links): no API key.
    app.include_router(intake.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(unsubscribe.router)
    return app


app = create_app()
