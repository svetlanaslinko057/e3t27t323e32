"""
LUMEN — Email Verification
==========================

Closes Tier-A1 stopper: the entire downstream pipeline (KYC, accreditation,
funding, ownership registry, certificates, payouts, withdrawals) keys on
``users.email`` as the identifier. Until ownership of that email is
proven, the identity layer is structurally weak. This module proves it.

Contract enforced by ``email_verification_contract.py`` (16 assertions).

What this module owns:
  • Token store ``lumen_email_verifications`` with TTL 24 h
  • ``GET  /api/auth/verify-email/{token}``     — consume + flip user
  • ``POST /api/auth/resend-verification``      — rate-limited (≥60 s)
  • ``POST /api/auth/change-email``             — resets verified=false
  • ``GET  /api/auth/me/email-verified-status`` — frontend gate decision
  • ``require_verified_email`` FastAPI dependency
  • Hook ``on_register_user_created()`` — called from /auth/register
  • Audit rows ``category=auth.email.{verified,resent,changed}``
  • ``send_verification_email()`` — Resend in real mode, console-log in mock

Mock-mode (no ``RESEND_API_KEY``): the email body is written to
``/app/backend/email_outbox/`` and printed to the backend log. Tests
fetch tokens via the DB. Production-mode: dispatch via Resend.

Seeded users (admin/staff/demo at boot) are backfilled to
``email_verified=true`` so existing demo accounts don't get locked out.
"""
from __future__ import annotations

import os
import json
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from lumen_api import db, get_current_user

logger = logging.getLogger("lumen.email_verification")
router = APIRouter(prefix="/api", tags=["lumen-email-verification"])

# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────
VERIFICATIONS = "lumen_email_verifications"
AUDIT = "lumen_staff_login_audit"

TOKEN_TTL = timedelta(hours=24)
RESEND_COOLDOWN = timedelta(seconds=60)

CANONICAL_VERIFIED_EMAILS = {
    "admin@devos.io", "admin@atlas.dev",
    "client@atlas.dev", "family@atlas.dev",
    "manager@atlas.dev", "tester@atlas.dev",
    "operator@atlas.dev", "multi@atlas.dev",
    "john@atlas.dev",
    # quick-access developer aliases (seeded by dev_quick_access.py)
    "alice.kim@atlas.dev", "marco.rossi@atlas.dev",
    "priya.shah@atlas.dev", "luka.horvat@atlas.dev",
    "sara.chen@atlas.dev", "diego.silva@atlas.dev",
}

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@lumen.platform")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "")
MOCK_MODE = not bool(RESEND_API_KEY)

OUTBOX_DIR = Path("/app/backend/email_outbox")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _mint_token() -> str:
    # 32-byte url-safe token → 43 chars, ≈256 bits entropy
    return "ev_" + secrets.token_urlsafe(32)


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# Email dispatch
# ──────────────────────────────────────────────────────────────────────────
async def send_verification_email(*, to: str, token: str, name: Optional[str] = None) -> None:
    verify_url = (
        f"{PUBLIC_BASE.rstrip('/')}/verify-email?token={token}"
        if PUBLIC_BASE else f"/verify-email?token={token}"
    )
    subject = "[LUMEN] Підтвердіть email / Confirm email"
    body_text = (
        f"Привіт{', ' + name if name else ''}!\n\n"
        f"Щоб завершити реєстрацію в LUMEN, підтвердіть свою електронну "
        f"пошту, перейшовши за посиланням нижче (діє 24 години):\n\n"
        f"{verify_url}\n\n"
        f"Якщо ви не реєструвалися — просто проігноруйте цей лист.\n\n"
        f"— LUMEN Team\n\n"
        f"---\n"
        f"Hi{', ' + name if name else ''}!\n\n"
        f"Click the link below within 24 hours to confirm your email and "
        f"finish your LUMEN registration:\n\n"
        f"{verify_url}\n\n"
        f"If you didn't sign up, ignore this email.\n\n"
        f"— LUMEN Team\n"
    )
    if MOCK_MODE:
        try:
            OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
            fname = OUTBOX_DIR / f"verify_{token[:16]}_{int(_now().timestamp())}.txt"
            fname.write_text(
                f"To: {to}\nFrom: {EMAIL_FROM}\nSubject: {subject}\n\n{body_text}",
                encoding="utf-8",
            )
            logger.info("📧 [MOCK email] verify link for %s → %s (also written to %s)",
                        to, verify_url, fname)
        except Exception as e:
            logger.warning("mock outbox write failed: %s", e)
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                         "Content-Type": "application/json"},
                json={"from": EMAIL_FROM, "to": [to], "subject": subject,
                      "text": body_text},
            )
            if r.status_code >= 400:
                logger.warning("Resend dispatch failed: %s %s",
                               r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Resend dispatch exception: %s", e)


# ──────────────────────────────────────────────────────────────────────────
# Token lifecycle
# ──────────────────────────────────────────────────────────────────────────
async def mint_verification_token(*, user_id: str, email: str,
                                  request: Optional[Request] = None) -> str:
    """Mint a new token + invalidate any prior unconsumed token for the
    same email. Returns the new token."""
    await db[VERIFICATIONS].update_many(
        {"email": email, "consumed": False},
        {"$set": {"consumed": True,
                  "consumed_at": _now(),
                  "consumed_reason": "superseded"}},
    )
    token = _mint_token()
    await db[VERIFICATIONS].insert_one({
        "id": f"emv_{uuid.uuid4().hex[:12]}",
        "token": token,
        "user_id": user_id,
        "email": email,
        "created_at": _now(),
        "expires_at": _now() + TOKEN_TTL,
        "consumed": False,
        "consumed_at": None,
        "created_ip": _client_ip(request),
    })
    return token


async def _audit(category: str, *, user_id: Optional[str], email: Optional[str],
                 detail: dict, request: Optional[Request] = None) -> None:
    try:
        await db[AUDIT].insert_one({
            "id": f"emv_{uuid.uuid4().hex[:12]}",
            "user_id": user_id, "email": email,
            "event": category, "category": category,
            "detail": detail,
            "ip": _client_ip(request),
            "user_agent": (request.headers.get("user-agent") if request else None),
            "at": _iso(),
        })
    except Exception as e:
        logger.warning("audit insert failed (%s): %s", category, e)


# ──────────────────────────────────────────────────────────────────────────
# Hook called from /auth/register
# ──────────────────────────────────────────────────────────────────────────
async def on_register_user_created(*, user_id: str, email: str,
                                   name: Optional[str] = None,
                                   request: Optional[Request] = None) -> None:
    """Called right after the user doc is inserted by /auth/register.

    Sets email_verified=false on the user, mints the first token, and
    dispatches the verification email. Idempotent if called twice for
    the same user."""
    email = email.strip().lower()
    if email in CANONICAL_VERIFIED_EMAILS:
        # Demo/seed accounts are pre-verified — see backfill in ensure_indexes().
        await db.users.update_one({"user_id": user_id},
                                  {"$set": {"email_verified": True}})
        return
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"email_verified": False,
                  "email_verified_at": None}},
    )
    token = await mint_verification_token(user_id=user_id, email=email,
                                          request=request)
    await send_verification_email(to=email, token=token, name=name)
    await _audit("auth.email.sent",
                 user_id=user_id, email=email,
                 detail={"mock": MOCK_MODE}, request=request)


# ──────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────
@router.get("/auth/verify-email/{token}")
async def verify_email(token: str, request: Request):
    doc = await db[VERIFICATIONS].find_one({"token": token})
    if not doc:
        raise HTTPException(status_code=400, detail="invalid_token")
    if doc.get("consumed"):
        # 410 Gone — token already used (consumed-once contract)
        raise HTTPException(status_code=410, detail="token_already_used")
    expires_at = doc.get("expires_at")
    if isinstance(expires_at, datetime):
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if exp < _now():
            raise HTTPException(status_code=400, detail="token_expired")

    await db[VERIFICATIONS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"consumed": True, "consumed_at": _now(),
                  "consumed_reason": "verified"}},
    )
    await db.users.update_one(
        {"user_id": doc["user_id"]},
        {"$set": {"email_verified": True, "email_verified_at": _iso()}},
    )
    await _audit("auth.email.verified",
                 user_id=doc["user_id"], email=doc["email"],
                 detail={"token_id": doc.get("id")}, request=request)
    return {"ok": True, "email": doc["email"], "verified": True}


class ResendIn(BaseModel):
    email: Optional[EmailStr] = None  # optional override; defaults to current user


@router.post("/auth/resend-verification")
async def resend_verification(payload: ResendIn, request: Request,
                              user=Depends(get_current_user)):
    target_email = (payload.email or user.get("email") or "").strip().lower()
    if not target_email:
        raise HTTPException(status_code=400, detail="email_required")
    # Only the authenticated user can resend their own verification.
    if target_email != (user.get("email") or "").lower():
        raise HTTPException(status_code=403, detail="forbidden")
    # If user is already verified — no-op 200
    udoc = await db.users.find_one({"user_id": user.get("user_id")})
    if (udoc or {}).get("email_verified") is True:
        return {"ok": True, "already_verified": True}
    # Cooldown: only against the previous EXPLICIT resend, not against the
    # register-hook bootstrap token. We track last_resend_at on the user.
    last_resend = (udoc or {}).get("last_resend_at")
    if last_resend:
        try:
            lr = (last_resend if isinstance(last_resend, datetime)
                  else datetime.fromisoformat(str(last_resend).replace("Z", "+00:00")))
            lr = lr if lr.tzinfo else lr.replace(tzinfo=timezone.utc)
            if _now() - lr < RESEND_COOLDOWN:
                raise HTTPException(
                    status_code=429,
                    detail=f"cooldown_active_{int(RESEND_COOLDOWN.total_seconds())}s",
                )
        except HTTPException:
            raise
        except Exception:
            pass
    token = await mint_verification_token(user_id=user.get("user_id"),
                                          email=target_email, request=request)
    await db.users.update_one(
        {"user_id": user.get("user_id")},
        {"$set": {"last_resend_at": _now()}},
    )
    await send_verification_email(to=target_email, token=token,
                                  name=user.get("name"))
    await _audit("auth.email.resent",
                 user_id=user.get("user_id"), email=target_email,
                 detail={"mock": MOCK_MODE}, request=request)
    return {"ok": True, "cooldown_seconds": int(RESEND_COOLDOWN.total_seconds())}


class ChangeEmailIn(BaseModel):
    new_email: EmailStr


@router.post("/auth/change-email")
async def change_email(payload: ChangeEmailIn, request: Request,
                       user=Depends(get_current_user)):
    new_email = payload.new_email.strip().lower()
    if not new_email or "@" not in new_email:
        raise HTTPException(status_code=400, detail="email_invalid")
    if new_email == (user.get("email") or "").lower():
        raise HTTPException(status_code=400, detail="email_unchanged")
    taken = await db.users.find_one({"email": new_email,
                                     "user_id": {"$ne": user.get("user_id")}})
    if taken:
        raise HTTPException(status_code=409, detail="email_taken")
    old_email = (user.get("email") or "").lower()
    await db.users.update_one(
        {"user_id": user.get("user_id")},
        {"$set": {"email": new_email,
                  "email_verified": False,
                  "email_verified_at": None,
                  "email_changed_at": _iso(),
                  "email_previous": old_email}},
    )
    # Invalidate all prior tokens for the OLD email + mint a fresh one for the new
    await db[VERIFICATIONS].update_many(
        {"email": old_email, "consumed": False},
        {"$set": {"consumed": True, "consumed_at": _now(),
                  "consumed_reason": "email_changed"}},
    )
    token = await mint_verification_token(user_id=user.get("user_id"),
                                          email=new_email, request=request)
    await send_verification_email(to=new_email, token=token, name=user.get("name"))
    await _audit("auth.email.changed",
                 user_id=user.get("user_id"), email=new_email,
                 detail={"old": old_email, "mock": MOCK_MODE}, request=request)
    return {"ok": True, "email": new_email, "email_verified": False}


@router.get("/auth/me/email-verified-status")
async def email_verified_status(user=Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user.get("user_id")}) or {}
    return {
        "email": u.get("email"),
        "verified": bool(u.get("email_verified")),
        "verified_at": u.get("email_verified_at"),
        "pending_token_exists": bool(await db[VERIFICATIONS].find_one(
            {"email": u.get("email"), "consumed": False})),
    }


# ──────────────────────────────────────────────────────────────────────────
# require_verified_email — FastAPI dependency for downstream gates
# ──────────────────────────────────────────────────────────────────────────
async def require_verified_email(user=Depends(get_current_user)) -> dict:
    """Use as ``Depends(require_verified_email)`` on KYC / funding /
    withdrawal endpoints. Returns the user dict on success; raises 403
    with structured ``email_verification_required`` code otherwise."""
    if user.get("email_verified") is True:
        return user
    # Re-read in case the session-cached user is stale (verified after login)
    fresh = await db.users.find_one({"user_id": user.get("user_id")}) or {}
    if fresh.get("email_verified") is True:
        return fresh
    raise HTTPException(
        status_code=403,
        detail={
            "code": "email_verification_required",
            "message": "Підтвердіть email перш ніж продовжити. / "
                       "Verify your email before continuing.",
            "email": fresh.get("email") or user.get("email"),
        },
    )


# ──────────────────────────────────────────────────────────────────────────
# Indexes + seed backfill
# ──────────────────────────────────────────────────────────────────────────
async def ensure_indexes() -> None:
    try:
        await db[VERIFICATIONS].create_index("token", unique=True)
        await db[VERIFICATIONS].create_index(
            "expires_at", expireAfterSeconds=0, name="email_verification_ttl")
        await db[VERIFICATIONS].create_index(
            [("email", 1), ("consumed", 1)], name="email_consumed_lookup")
        logger.info("email_verification indexes ensured")
    except Exception as e:
        logger.warning("ensure_indexes warning: %s", e)


async def backfill_seed_users() -> int:
    """One-shot: every canonical demo/staff user gets email_verified=true.
    Idempotent — re-runs are cheap."""
    n = 0
    for em in CANONICAL_VERIFIED_EMAILS:
        r = await db.users.update_one(
            {"email": em},
            {"$set": {"email_verified": True,
                      "email_verified_at": _iso(),
                      "email_verified_reason": "seed_backfill"}},
        )
        if r.modified_count:
            n += r.modified_count
    # Also: any user already created BEFORE this module was added, without
    # the field, gets a one-shot decision: if their email is in the seed
    # list, verified=true; otherwise verified=false (they will need to
    # verify on their next visit).
    seed = list(CANONICAL_VERIFIED_EMAILS)
    await db.users.update_many(
        {"email_verified": {"$exists": False}, "email": {"$in": seed}},
        {"$set": {"email_verified": True,
                  "email_verified_at": _iso(),
                  "email_verified_reason": "seed_backfill"}},
    )
    await db.users.update_many(
        {"email_verified": {"$exists": False}, "email": {"$nin": seed}},
        {"$set": {"email_verified": False,
                  "email_verified_reason": "legacy_user_unverified"}},
    )
    if n:
        logger.info("email_verified backfill: %d seed users marked verified", n)
    return n


async def boot() -> None:
    await ensure_indexes()
    await backfill_seed_users()
    logger.info("F-EmailVerification ready (mock_mode=%s, outbox=%s)",
                MOCK_MODE, OUTBOX_DIR)
