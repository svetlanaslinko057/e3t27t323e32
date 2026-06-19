"""
LUMEN — Manager OS · M5 — Staff Login Audit + Active Sessions.

For an investment platform the staff login trail matters more than it looks —
especially with remote managers. We record every staff auth event and expose
a read surface for admins (everyone) and managers (themselves only).

Collection ``lumen_staff_login_audit`` rows:
  { id, user_id, email, name, role, event, ip, user_agent, at }
  event ∈ { login_ok, login_fail, logout }

Active sessions are derived live from ``user_sessions`` (the canonical session
store) joined with ``users`` — we do NOT duplicate session state.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query

from lumen_api import db, require_staff, _strip_mongo
from lumen_staff_acl import is_privileged, staff_uid

logger = logging.getLogger("lumen.staff_audit")

router = APIRouter(prefix="/api/admin/staff", tags=["lumen-staff-audit"])

AUDIT = "lumen_staff_login_audit"
STAFF_ROLES = {"admin", "manager", "operator", "team_lead", "owner", "master_admin"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _is_staff_user(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    return role in STAFF_ROLES or bool(roles & STAFF_ROLES)


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


async def record_login_event(
    event: str,
    *,
    user: Optional[dict] = None,
    email: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    """Best-effort audit write. Records staff events; for login_fail we still
    log the attempt and resolve the role if the email maps to a known user."""
    try:
        u = user
        if u is None and email:
            u = (await db.users.find_one({"email": email.strip().lower()}) or None)
            if u:
                u = _strip_mongo(u)
        # Only audit staff accounts (skip investor/client noise), but always
        # audit failures so brute-force on staff emails is visible.
        if u is not None and event != "login_fail" and not _is_staff_user(u):
            return
        row = {
            "id": f"slog_{uuid.uuid4().hex[:12]}",
            "user_id": (u or {}).get("user_id") or (u or {}).get("id"),
            "email": (u or {}).get("email") or (email or "").strip().lower() or None,
            "name": (u or {}).get("name") or (u or {}).get("full_name"),
            "role": (u or {}).get("role"),
            "event": event,
            "ip": _client_ip(request),
            "user_agent": (request.headers.get("user-agent") if request else None),
            "at": _iso(),
        }
        await db[AUDIT].insert_one(row)
    except Exception as e:
        logger.warning("record_login_event failed event=%s err=%s", event, e)


@router.get("/login-audit")
async def login_audit(
    user=Depends(require_staff),
    days: int = Query(30, le=180),
    event: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
):
    since = _iso(_now() - timedelta(days=days))
    q: dict = {"at": {"$gte": since}}
    if event:
        q["event"] = event
    # Managers see only their own trail; admins/privileged see everyone.
    if not is_privileged(user):
        q["user_id"] = staff_uid(user)
    cur = db[AUDIT].find(q).sort("at", -1).limit(limit)
    rows = [_strip_mongo(r) async for r in cur]
    return {"events": rows, "count": len(rows), "days": days}


@router.get("/active-sessions")
async def active_sessions(user=Depends(require_staff)):
    """Live active staff sessions derived from user_sessions + users."""
    now = _now()
    out = []
    privileged = is_privileged(user)
    me = staff_uid(user)
    try:
        cur = db.user_sessions.find({}).sort("created_at", -1).limit(500)
        async for s in cur:
            s = _strip_mongo(s)
            uid = s.get("user_id")
            if not uid:
                continue
            if not privileged and uid != me:
                continue
            u = (await db.users.find_one({"user_id": uid})
                 or await db.users.find_one({"id": uid}))
            if not u:
                continue
            u = _strip_mongo(u)
            if not _is_staff_user(u):
                continue
            # expiry check
            exp = s.get("expires_at")
            active = True
            if exp:
                try:
                    ed = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                    if ed.tzinfo is None:
                        ed = ed.replace(tzinfo=timezone.utc)
                    active = ed > now
                except Exception:
                    active = True
            if not active:
                continue
            out.append({
                "session_id": s.get("session_id"),
                "user_id": uid,
                "name": u.get("name") or u.get("full_name"),
                "email": u.get("email"),
                "role": u.get("role"),
                "created_at": s.get("created_at"),
                "expires_at": exp,
            })
    except Exception as e:
        logger.warning("active_sessions failed: %s", e)
    return {"sessions": out, "count": len(out)}


async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[AUDIT].create_index("id", unique=True)
        await d[AUDIT].create_index([("at", -1)])
        await d[AUDIT].create_index([("user_id", 1), ("at", -1)])
        await d[AUDIT].create_index([("event", 1), ("at", -1)])
    except Exception as e:
        logger.warning("ensure_indexes(staff_audit) warn: %s", e)
