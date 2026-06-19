"""
LUMEN — Public website lead-capture layer
==========================================

Lightweight public endpoints used by the marketing site:

  * POST /api/public/contact              — quick request / "Замовити дзвінок" form
  * POST /api/public/newsletter/subscribe — footer newsletter signup

Both are write-only (store to Mongo) and never require auth. They are
intentionally minimal: managers pick up leads from these collections via the
existing admin tooling.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from lumen_api import db

logger = logging.getLogger("lumen.public_site")
router = APIRouter(prefix="/api", tags=["lumen-public-site"])

CONTACTS_COLL = "lumen_public_contacts"
NEWSLETTER_COLL = "lumen_newsletter_subscribers"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=3, max_length=40)
    topic: Optional[str] = Field("", max_length=200)
    message: Optional[str] = Field("", max_length=2000)
    source: Optional[str] = Field("contacts_page", max_length=80)


class NewsletterRequest(BaseModel):
    email: str = Field(..., max_length=160)
    source: Optional[str] = Field("footer", max_length=80)


@router.post("/public/contact")
async def public_contact(body: ContactRequest):
    """Store a public contact / callback request (no auth)."""
    doc = {
        "id": f"lead_{uuid.uuid4().hex[:16]}",
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "topic": (body.topic or "").strip(),
        "message": (body.message or "").strip(),
        "source": (body.source or "contacts_page").strip(),
        "status": "new",
        "created_at": _now(),
    }
    try:
        await db[CONTACTS_COLL].insert_one(dict(doc))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("public_contact insert failed: %s", exc)
        # Still return ok so the visitor isn't blocked; lead is logged.
        logger.info("CONTACT LEAD (not stored): %s", doc)
    return {"ok": True, "id": doc["id"], "message": "Заявку прийнято"}


@router.post("/public/newsletter/subscribe")
async def public_newsletter_subscribe(body: NewsletterRequest):
    """Subscribe an email to the newsletter (idempotent, no auth)."""
    email = (body.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return {"ok": False, "message": "Вкажіть коректний email"}
    try:
        await db[NEWSLETTER_COLL].update_one(
            {"email": email},
            {
                "$setOnInsert": {
                    "id": f"sub_{uuid.uuid4().hex[:16]}",
                    "email": email,
                    "created_at": _now(),
                },
                "$set": {
                    "source": (body.source or "footer").strip(),
                    "active": True,
                    "updated_at": _now(),
                },
            },
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("newsletter subscribe failed: %s", exc)
    return {"ok": True, "message": "Дякуємо! Ви підписані на розсилку."}
