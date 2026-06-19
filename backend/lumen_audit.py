"""
LUMEN Sprint 10 — Audit Trail (Block 3)

Central immutable journal for every sensitive operation. Replaces the
scattered logging / db.events sinks with a single source of truth that
compliance / finance can review and export.

Collection: `lumen_audit_log`

Document shape
--------------
{
    id          : "al-<uuid12>",
    at          : ISO timestamp (UTC),
    actor_id    : user_id who performed action (None for system),
    actor_role  : 'admin' | 'investor' | 'system',
    actor_email : snapshot of email at time of action,
    actor_ip    : remote IP if available,
    action      : machine-readable code  (e.g. 'kyc.approve')
    category    : 'kyc' | 'contract' | 'payment' | 'payout' | 'withdrawal'
                 | 'asset' | 'spv' | 'auth' | 'system',
    target_type : entity collection name  (e.g. 'lumen_investor_profiles')
    target_id   : entity id
    summary     : human readable line (uk),
    diff        : optional dict {field: {before, after}},
    meta        : arbitrary structured context (amounts, reasons, etc.),
    request_id  : x-request-id if present (cross-correlation),
}

Writes are append-only. We never UPDATE or DELETE audit rows from code
(only mongodump cleanup is permitted manually).

Admin API (compliance / finance read-only)
------------------------------------------
    GET  /api/admin/audit/log           — paginated query
    GET  /api/admin/audit/categories    — known categories + counts
    GET  /api/admin/audit/export.csv    — CSV export for off-site retention
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from lumen_api import db, require_admin, _strip_mongo, _now, _iso

logger = logging.getLogger("lumen.audit")

AUDIT_COLLECTION = "lumen_audit_log"

KNOWN_CATEGORIES = (
    "kyc", "contract", "payment", "payout", "withdrawal",
    "asset", "spv", "auth", "system",
)

# ----------------------------------------------------------------------------
# Indexes
# ----------------------------------------------------------------------------

async def ensure_audit_indexes() -> None:
    try:
        await db[AUDIT_COLLECTION].create_index([("at", -1)])
        await db[AUDIT_COLLECTION].create_index([("category", 1), ("at", -1)])
        await db[AUDIT_COLLECTION].create_index([("actor_id", 1), ("at", -1)])
        await db[AUDIT_COLLECTION].create_index([("target_type", 1), ("target_id", 1)])
        await db[AUDIT_COLLECTION].create_index([("action", 1)])
    except Exception:  # pragma: no cover
        logger.exception("AUDIT: index ensure failed")


# ----------------------------------------------------------------------------
# Core writer
# ----------------------------------------------------------------------------

async def write_audit(
    *,
    action: str,
    category: str,
    target_type: str,
    target_id: Optional[str],
    actor: Optional[dict] = None,
    summary: str = "",
    diff: Optional[dict] = None,
    meta: Optional[dict] = None,
    request: Optional[Request] = None,
) -> dict:
    """Append a single audit row. Never raises — audit MUST NOT break flow."""
    try:
        actor = actor or {}
        doc = {
            "id": f"al-{uuid.uuid4().hex[:12]}",
            "at": _now(),
            "actor_id": actor.get("id") or actor.get("user_id"),
            "actor_role": actor.get("role") or ("system" if not actor else "unknown"),
            "actor_email": actor.get("email"),
            "actor_ip": _resolve_ip(request),
            "action": action,
            "category": category if category in KNOWN_CATEGORIES else "system",
            "target_type": target_type,
            "target_id": target_id,
            "summary": summary,
            "diff": diff or {},
            "meta": meta or {},
            "request_id": (request.headers.get("x-request-id") if request else None),
        }
        await db[AUDIT_COLLECTION].insert_one(doc)
        return doc
    except Exception:  # pragma: no cover
        logger.exception("AUDIT write failed: action=%s", action)
        return {}


def _resolve_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else None
    except Exception:
        return None


def _row_out(doc: dict) -> dict:
    out = _strip_mongo(dict(doc))
    out["at"] = _iso(out.get("at"))
    return out


# ----------------------------------------------------------------------------
# Router — admin viewer
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-audit"])


@router.on_event("startup")
async def _audit_startup():
    await ensure_audit_indexes()
    logger.info("AUDIT: indexes ensured (collection=%s)", AUDIT_COLLECTION)


@router.get("/admin/audit/log")
async def admin_audit_log(
    category: Optional[str] = None,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    target_id: Optional[str] = None,
    since_hours: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _=Depends(require_admin),
):
    q: dict[str, Any] = {}
    if category:
        if category not in KNOWN_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Unknown category: {category}")
        q["category"] = category
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    if target_id:
        q["target_id"] = target_id
    if since_hours and since_hours > 0:
        q["at"] = {"$gte": _now() - timedelta(hours=int(since_hours))}

    total = await db[AUDIT_COLLECTION].count_documents(q)
    items = []
    async for r in (db[AUDIT_COLLECTION]
                    .find(q).sort("at", -1).skip(skip).limit(limit)):
        items.append(_row_out(r))
    return {"items": items, "total": total, "limit": limit, "skip": skip}


@router.get("/admin/audit/categories")
async def admin_audit_categories(_=Depends(require_admin)):
    out = []
    for c in KNOWN_CATEGORIES:
        cnt = await db[AUDIT_COLLECTION].count_documents({"category": c})
        out.append({"category": c, "count": cnt})
    total = await db[AUDIT_COLLECTION].count_documents({})
    last = await db[AUDIT_COLLECTION].find_one(sort=[("at", -1)])
    last_at = _iso(last.get("at")) if last else None
    return {"categories": out, "total": total, "last_at": last_at}


@router.get("/admin/audit/export.csv")
async def admin_audit_export_csv(
    category: Optional[str] = None,
    since_hours: Optional[int] = 24 * 7,
    _=Depends(require_admin),
):
    q: dict[str, Any] = {}
    if category:
        q["category"] = category
    if since_hours and since_hours > 0:
        q["at"] = {"$gte": _now() - timedelta(hours=int(since_hours))}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "at", "category", "action", "actor_id", "actor_role", "actor_email",
        "actor_ip", "target_type", "target_id", "summary", "request_id",
    ])
    async for r in db[AUDIT_COLLECTION].find(q).sort("at", -1).limit(50000):
        writer.writerow([
            _iso(r.get("at")), r.get("category"), r.get("action"),
            r.get("actor_id"), r.get("actor_role"), r.get("actor_email"),
            r.get("actor_ip"), r.get("target_type"), r.get("target_id"),
            r.get("summary"), r.get("request_id"),
        ])
    data = buf.getvalue().encode("utf-8")
    return Response(
        content=data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="lumen-audit-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")}.csv"',
        },
    )


__all__ = ["router", "write_audit", "ensure_audit_indexes",
           "AUDIT_COLLECTION", "KNOWN_CATEGORIES"]
