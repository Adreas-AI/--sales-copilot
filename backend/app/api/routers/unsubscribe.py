"""Public unsubscribe link (GET shows a confirmation page, POST is RFC 8058 one-click)."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.security import read_unsubscribe_token
from app.services.conversations import unsubscribe_email

router = APIRouter(tags=["public unsubscribe"])

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BookFlow</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;
color:#1f2937}}button{{padding:.6rem 1.2rem;border-radius:.4rem;border:0;background:#4f46e5;
color:#fff;font-size:1rem;cursor:pointer}}</style></head><body>{content}</body></html>"""


def _email_or_400(token: str) -> str:
    email = read_unsubscribe_token(get_settings().unsubscribe_secret, token)
    if email is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid unsubscribe link")
    return email


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(token: str = Query(max_length=1000)) -> HTMLResponse:
    # GET only confirms, so link scanners in mail clients can't unsubscribe people.
    email = _email_or_400(token)
    content = (
        f"<h1>Unsubscribe</h1><p>Stop all emails from BookFlow to <b>{escape(email)}</b>?</p>"
        # No action attribute: the form posts back to this URL, token included.
        '<form method="post"><button>Unsubscribe</button></form>'
    )
    return HTMLResponse(PAGE.format(content=content))


@router.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(session: SessionDep, token: str = Query(max_length=1000)) -> HTMLResponse:
    email = _email_or_400(token)
    unsubscribe_email(session, email, source="unsubscribe_link")
    session.commit()
    return HTMLResponse(
        PAGE.format(content="<h1>You're unsubscribed</h1><p>You won't receive further emails.</p>")
    )
