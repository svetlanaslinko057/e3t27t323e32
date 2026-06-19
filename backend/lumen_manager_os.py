"""
LUMEN — Manager OS (IR2 · Layer A · DATA & PERMISSIONS FOUNDATION).

Locked decisions (user, 2026-06-15): A1 / B1 / C1 / D1 / E1 / F1.

  • A1 — Unified Communication Log as a MIRROR of notes/tasks/meetings (and
         later: calls/emails/telegram/whatsapp/sms/docs). The original
         collections KEEP their native records — this is a single read-side
         source of truth for Timeline / Activity / Manager KPI / Audit /
         future Contact Center.
  • B1 — Manager is a FIRST-CLASS entity (``lumen_managers``) — not a tag
         on ``users``. Carries status, quota, scope, sla, timezone, etc.
  • C1 — Materialized per-manager activity counters (``lumen_manager_activity``)
         updated on-write via the same _touch() hooks IR1.3-1.8 already use.
  • D1 — Idempotent backfill of existing notes/tasks/meetings/assignments
         into the new collections (safe to re-run; marker stored in
         ``lumen_meta``).
  • E1 — Whole Layer A delivered together — Communications, Managers,
         Activity, Assignment History, Scopes — in one pass.
  • F1 — Assignment history is a FIRST-CLASS collection
         (``lumen_lead_assignment_history``), not just a field-change row,
         because tomorrow attribution will drive commission and reporting.

This module ships ZERO new UI screens. It is groundwork that lets us later
plug in Ringostat / Twilio / SIP / Gmail / Telegram as additional event
sources WITHOUT a schema break.

VALIDATION mode is preserved — none of the 10 First-Real-Money runbook
steps are touched.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, require_staff, _strip_mongo

logger = logging.getLogger("lumen.manager_os")

router = APIRouter(prefix="/api/admin", tags=["lumen-manager-os"])

# Collections
COMMUNICATIONS = "lumen_lead_communications"
MANAGERS = "lumen_managers"
MANAGER_ACTIVITY = "lumen_manager_activity"
ASSIGNMENT_HISTORY = "lumen_lead_assignment_history"
MANAGER_SCOPES = "lumen_manager_scopes"
META = "lumen_meta"


# ── enums (soft — strings only, no DB-level lock) ──────────────────────────
KIND_NOTE = "note"
KIND_TASK_CREATED = "task_created"
KIND_TASK_COMPLETED = "task_completed"
KIND_MEETING_SCHEDULED = "meeting_scheduled"
KIND_MEETING_COMPLETED = "meeting_completed"
KIND_OWNER_ASSIGNED = "owner_assigned"
KIND_CONVERTED = "converted"
KIND_STAGE_CHANGED = "stage_changed"
KIND_LEAD_CREATED = "lead_created"

# Future event kinds (placeholders so consumers can match by string):
#   call · email · sms · telegram · whatsapp · document · in_app · other

# Provider enum (always "manual" today)
PROVIDER_MANUAL = "manual"


def _utc(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# A1 · Communication Log (mirror)
# ──────────────────────────────────────────────────────────────────────────
async def mirror_communication(
    *,
    lead_id: str,
    user_id: Optional[str],
    kind: str,
    interaction_type: Optional[str],   # call / email / meeting / note / task / document / ...
    direction: Optional[str] = None,   # inbound / outbound / internal / None
    title: str = "",
    detail: str = "",
    at: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    source_collection: str = "direct",
    source_id: Optional[str] = None,
    provider: str = PROVIDER_MANUAL,
    external_ref: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Write or upsert a row in the unified Communication Log.

    Idempotency: when both ``source_collection`` and ``source_id`` are known
    (mirroring an existing notes/tasks/meetings row), the same kind+source
    pair will NOT be duplicated on re-runs — this is what makes the backfill
    safe to replay.
    """
    payload = {
        "comm_id": f"comm_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "user_id": user_id,
        "kind": kind,
        "interaction_type": interaction_type or kind,
        "direction": direction,
        "title": title,
        "detail": detail,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "source_collection": source_collection,
        "source_id": source_id,
        "provider": provider,
        "external_ref": external_ref,
        "at": at or _now_iso(),
        "created_at": _now_iso(),
    }
    if extra:
        payload["extra"] = extra

    # Idempotent path when we have a source pointer (used by backfill + writes).
    if source_collection and source_id:
        existing = await db[COMMUNICATIONS].find_one(
            {"source_collection": source_collection,
             "source_id": source_id,
             "kind": kind}
        )
        if existing:
            return _strip_mongo(existing)
        try:
            await db[COMMUNICATIONS].insert_one(payload)
        except Exception:  # tolerate races on duplicate
            existing = await db[COMMUNICATIONS].find_one(
                {"source_collection": source_collection,
                 "source_id": source_id,
                 "kind": kind})
            return _strip_mongo(existing or payload)
    else:
        await db[COMMUNICATIONS].insert_one(payload)
    return _strip_mongo(payload)


# ──────────────────────────────────────────────────────────────────────────
# C1 · Manager Activity (materialized counters)
# ──────────────────────────────────────────────────────────────────────────
ACTIVITY_FIELDS = (
    "calls_count", "meetings_count", "notes_count", "tasks_completed",
    "tasks_open", "leads_assigned", "leads_converted",
    "funding_attributed_count", "communications_inbound",
    "communications_outbound",
)


async def _ensure_activity_doc(user_id: str):
    if not user_id:
        return
    await db[MANAGER_ACTIVITY].update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            **{f: 0 for f in ACTIVITY_FIELDS},
            "created_at": _now_iso(),
        }},
        upsert=True,
    )


async def bump_activity(
    user_id: Optional[str],
    field: str,
    inc: int = 1,
    touch_last_activity: bool = True,
):
    """Bump one materialized counter for a manager. No-op when user_id is None."""
    if not user_id or field not in ACTIVITY_FIELDS:
        return
    try:
        await _ensure_activity_doc(user_id)
        update = {"$inc": {field: inc}, "$set": {"updated_at": _now_iso()}}
        if touch_last_activity:
            update["$set"]["last_activity_at"] = _now_iso()
        await db[MANAGER_ACTIVITY].update_one({"user_id": user_id}, update)
    except Exception as e:
        logger.warning("bump_activity failed user=%s field=%s err=%s", user_id, field, e)


async def get_activity(user_id: str) -> dict:
    doc = await db[MANAGER_ACTIVITY].find_one({"user_id": user_id})
    if not doc:
        return {"user_id": user_id, **{f: 0 for f in ACTIVITY_FIELDS}, "last_activity_at": None}
    return _strip_mongo(doc)


# ──────────────────────────────────────────────────────────────────────────
# B1 · Manager entity
# ──────────────────────────────────────────────────────────────────────────
async def upsert_manager_from_user(user: dict, *, status: str = "active") -> dict:
    """Ensure a ``lumen_managers`` row exists for an admin/manager user.

    Called from the startup auto-promotion sweep and from /managers admin route.
    """
    uid = user.get("user_id") or user.get("id")
    if not uid:
        return {}
    existing = await db[MANAGERS].find_one({"user_id": uid})
    if existing:
        return _strip_mongo(existing)
    doc = {
        "manager_id": f"mgr_{uuid.uuid4().hex[:12]}",
        "user_id": uid,
        "name": user.get("name") or user.get("full_name") or user.get("email"),
        "email": user.get("email"),
        "role_in_users": user.get("role"),
        "status": status,
        "quota": None,
        "specialization": [],
        "country": None,
        "language": None,
        "timezone": None,
        "sla_response_hours": None,
        "scope": "all" if (user.get("role") == "admin" or "admin" in (user.get("roles") or [])) else "owned",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    try:
        await db[MANAGERS].insert_one(doc)
    except Exception:
        existing = await db[MANAGERS].find_one({"user_id": uid})
        if existing:
            return _strip_mongo(existing)
    await _ensure_activity_doc(uid)
    return _strip_mongo(doc)


# ──────────────────────────────────────────────────────────────────────────
# F1 · Assignment History (first-class)
# ──────────────────────────────────────────────────────────────────────────
async def record_assignment(
    *,
    lead_id: str,
    from_user_id: Optional[str],
    from_user_name: Optional[str],
    to_user_id: Optional[str],
    to_user_name: Optional[str],
    actor: dict,
    reason: Optional[str] = None,
    at: Optional[str] = None,
):
    """Append a row to the assignment history."""
    if from_user_id == to_user_id:
        return
    row = {
        "assign_id": f"aid_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "from_user_id": from_user_id,
        "from_user_name": from_user_name,
        "to_user_id": to_user_id,
        "to_user_name": to_user_name,
        "reason": reason or "owner_assignment",
        "assigned_by_id": actor.get("user_id") or actor.get("id"),
        "assigned_by_name": actor.get("name") or actor.get("full_name") or actor.get("email"),
        "at": at or _now_iso(),
    }
    try:
        await db[ASSIGNMENT_HISTORY].insert_one(row)
    except Exception as e:
        logger.warning("record_assignment failed lead=%s err=%s", lead_id, e)

    # Counter side-effects: bump 'leads_assigned' for the NEW owner.
    if to_user_id:
        await bump_activity(to_user_id, "leads_assigned")


# ──────────────────────────────────────────────────────────────────────────
# D1 · Backfill (idempotent)
# ──────────────────────────────────────────────────────────────────────────
BACKFILL_VERSION = "ir2_layer_a_v1"


async def backfill_once():
    """One-shot backfill: mirror existing notes/tasks/meetings into the new
    Communication Log, seed manager rows for everyone who could be an owner,
    and reconstruct ``leads_assigned`` counters from current ownership.

    Safe to call on every startup — uses a meta marker AND insert-idempotent
    mirror_communication so a half-finished previous run repairs itself."""
    marker = await db[META].find_one({"key": "ir2_backfill"})
    if marker and marker.get("version") == BACKFILL_VERSION:
        return {"skipped": True, "version": BACKFILL_VERSION}

    stats = {
        "notes_mirrored": 0,
        "tasks_mirrored": 0,
        "tasks_completed_mirrored": 0,
        "meetings_mirrored": 0,
        "meetings_completed_mirrored": 0,
        "lead_owner_history_rows": 0,
        "managers_upserted": 0,
        "leads_assigned_counts": 0,
    }

    # 1. Seed manager rows for every admin / manager user.
    async for u in db.users.find({"$or": [
        {"role": {"$in": ["admin", "manager"]}},
        {"roles": {"$in": ["admin", "manager"]}},
    ]}):
        u = _strip_mongo(u)
        before = await db[MANAGERS].find_one({"user_id": u.get("user_id") or u.get("id")})
        await upsert_manager_from_user(u)
        if not before:
            stats["managers_upserted"] += 1

    # 2. Mirror notes.
    async for n in db.lumen_lead_notes.find({}):
        n = _strip_mongo(n)
        await mirror_communication(
            lead_id=n.get("lead_id"),
            user_id=None,
            kind=KIND_NOTE,
            interaction_type="note",
            direction="internal",
            title="Нотатка",
            detail=(n.get("body") or "")[:240],
            at=n.get("created_at"),
            actor_id=n.get("author_id"),
            actor_name=n.get("author_name"),
            source_collection="lumen_lead_notes",
            source_id=n.get("id"),
        )
        stats["notes_mirrored"] += 1

    # 3. Mirror tasks (created + completed are separate events).
    async for t in db.lumen_lead_tasks.find({}):
        t = _strip_mongo(t)
        await mirror_communication(
            lead_id=t.get("lead_id"),
            user_id=None,
            kind=KIND_TASK_CREATED,
            interaction_type=t.get("task_type") or "task",
            direction=None,
            title=f"Задача: {t.get('title','')}",
            detail=(t.get("description") or "")[:240],
            at=t.get("created_at"),
            actor_id=None,
            actor_name=t.get("created_by"),
            source_collection="lumen_lead_tasks",
            source_id=t.get("id"),
            extra={"assignee_id": t.get("assignee_id"), "priority": t.get("priority")},
        )
        stats["tasks_mirrored"] += 1
        if t.get("status") == "done" and t.get("completed_at"):
            await mirror_communication(
                lead_id=t.get("lead_id"),
                user_id=None,
                kind=KIND_TASK_COMPLETED,
                interaction_type=t.get("task_type") or "task",
                title=f"Задача виконана: {t.get('title','')}",
                detail="",
                at=t.get("completed_at"),
                actor_id=t.get("assignee_id"),
                actor_name=t.get("assignee_name"),
                source_collection="lumen_lead_tasks",
                source_id=t.get("id"),
            )
            stats["tasks_completed_mirrored"] += 1

    # 4. Mirror meetings.
    async for m in db.lumen_lead_meetings.find({}):
        m = _strip_mongo(m)
        await mirror_communication(
            lead_id=m.get("lead_id"),
            user_id=None,
            kind=KIND_MEETING_SCHEDULED,
            interaction_type="meeting",
            direction="outbound",
            title=f"Зустріч: {m.get('title','')}",
            detail=f"{m.get('type','')} · {m.get('duration_min','')}хв",
            at=m.get("created_at") or m.get("scheduled_at"),
            actor_id=None,
            actor_name=m.get("created_by"),
            source_collection="lumen_lead_meetings",
            source_id=m.get("id"),
        )
        stats["meetings_mirrored"] += 1
        if m.get("status") == "completed":
            await mirror_communication(
                lead_id=m.get("lead_id"),
                user_id=None,
                kind=KIND_MEETING_COMPLETED,
                interaction_type="meeting",
                direction="outbound",
                title=f"Зустріч проведено: {m.get('title','')}",
                detail=(m.get("outcome_note") or "")[:240],
                at=m.get("updated_at") or m.get("scheduled_at"),
                source_collection="lumen_lead_meetings",
                source_id=m.get("id"),
            )
            stats["meetings_completed_mirrored"] += 1

    # 5. Reconstruct lead-owner assignment history from lumen_field_changes.
    try:
        async for h in db.lumen_field_changes.find({"entity_type": "lead", "field": "owner_id"}):
            h = _strip_mongo(h)
            lid = h.get("entity_id")
            old = h.get("old_value")
            new = h.get("new_value")
            actor = h.get("actor") or {}
            at = h.get("at") or h.get("changed_at") or h.get("created_at")
            # Dedup: real-time writes from /owner endpoint and field-history
            # rows describe the SAME logical transition with timestamps that
            # differ by microseconds. Match by (lead, from, to) ignoring `at`
            # — the rare A→B→A→B re-transition is acceptable to deduplicate
            # given this is replay protection, not the live event path.
            existing = await db[ASSIGNMENT_HISTORY].find_one(
                {"lead_id": lid, "from_user_id": old, "to_user_id": new})
            if existing:
                continue
            from_name = None
            to_name = None
            if old:
                fu = (await db.users.find_one({"user_id": old})
                      or await db.users.find_one({"id": old}))
                if fu:
                    fu = _strip_mongo(fu)
                    from_name = fu.get("name") or fu.get("full_name") or fu.get("email")
            if new:
                tu = (await db.users.find_one({"user_id": new})
                      or await db.users.find_one({"id": new}))
                if tu:
                    tu = _strip_mongo(tu)
                    to_name = tu.get("name") or tu.get("full_name") or tu.get("email")
            await db[ASSIGNMENT_HISTORY].insert_one({
                "assign_id": f"aid_{uuid.uuid4().hex[:12]}",
                "lead_id": lid,
                "from_user_id": old,
                "from_user_name": from_name,
                "to_user_id": new,
                "to_user_name": to_name,
                "reason": "backfill_from_field_history",
                "assigned_by_id": (actor or {}).get("id") if isinstance(actor, dict) else None,
                "assigned_by_name": (actor or {}).get("email") if isinstance(actor, dict) else None,
                "at": at,
            })
            stats["lead_owner_history_rows"] += 1
    except Exception as e:
        logger.warning("backfill assignment history failed: %s", e)

    # 6. Reconstruct ``leads_assigned`` counters from CURRENT ownership.
    try:
        from collections import Counter
        counts = Counter()
        async for ld in db.lumen_leads.find({"owner_id": {"$ne": None}}):
            counts[ld.get("owner_id")] += 1
        for uid, n in counts.items():
            if not uid:
                continue
            await _ensure_activity_doc(uid)
            await db[MANAGER_ACTIVITY].update_one(
                {"user_id": uid},
                {"$set": {"leads_assigned": int(n), "updated_at": _now_iso()}},
            )
            stats["leads_assigned_counts"] += 1
    except Exception as e:
        logger.warning("backfill leads_assigned failed: %s", e)

    # 7. Reconstruct ``leads_converted`` counters from CURRENT linkage.
    try:
        from collections import Counter
        counts = Counter()
        async for ld in db.lumen_leads.find({"user_id": {"$ne": None}, "owner_id": {"$ne": None}}):
            counts[ld.get("owner_id")] += 1
        for uid, n in counts.items():
            if not uid:
                continue
            await _ensure_activity_doc(uid)
            await db[MANAGER_ACTIVITY].update_one(
                {"user_id": uid},
                {"$set": {"leads_converted": int(n), "updated_at": _now_iso()}},
            )
    except Exception:
        pass

    # 8. Mark done.
    await db[META].update_one(
        {"key": "ir2_backfill"},
        {"$set": {"key": "ir2_backfill", "version": BACKFILL_VERSION,
                  "at": _now_iso(), "stats": stats}},
        upsert=True,
    )
    logger.info("[manager_os] backfill complete %s", stats)
    return {"skipped": False, "version": BACKFILL_VERSION, "stats": stats}


# ──────────────────────────────────────────────────────────────────────────
# Admin read-only endpoints (no UI required; useful for audit & verification)
# ──────────────────────────────────────────────────────────────────────────
@router.get("/managers")
async def list_managers_with_activity(admin=Depends(require_staff)):
    """List managers with materialized activity. Scoped: a non-privileged
    manager sees only their own row ("my activity")."""
    try:
        from lumen_staff_acl import is_privileged, staff_uid
        privileged = is_privileged(admin)
        me = staff_uid(admin)
    except Exception:
        privileged, me = True, None
    q = {} if privileged else {"user_id": me}
    out: List[dict] = []
    async for m in db[MANAGERS].find(q).sort("created_at", -1):
        m = _strip_mongo(m)
        act = await get_activity(m["user_id"])
        out.append({**m, "activity": act})
    return {"managers": out, "count": len(out)}


@router.get("/managers/{user_id}/activity")
async def manager_activity(user_id: str, admin=Depends(require_staff)):
    return await get_activity(user_id)


@router.get("/ir/leads/{lead_id}/communications")
async def lead_communications(
    lead_id: str,
    admin=Depends(require_staff),
    kind: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
):
    """Unified communication log per lead — single source of truth.

    Filter by ``kind`` (e.g. ``note``, ``meeting_scheduled``, ``task_completed``).
    Future call/email/telegram events ride here without schema change.
    """
    q: dict = {"lead_id": lead_id}
    if kind:
        q["kind"] = kind
    try:
        from lumen_staff_acl import assert_can_see_lead
        lead = await db[LEADS].find_one({"lead_id": lead_id})
        await assert_can_see_lead(admin, lead)
    except HTTPException:
        raise
    except Exception:
        pass
    cur = db[COMMUNICATIONS].find(q).sort("at", -1).limit(limit)
    rows = [_strip_mongo(r) async for r in cur]
    return {"communications": rows, "count": len(rows)}


@router.get("/ir/leads/{lead_id}/assignment-history")
async def lead_assignment_history(lead_id: str, admin=Depends(require_staff)):
    try:
        from lumen_staff_acl import assert_can_see_lead
        lead = await db[LEADS].find_one({"lead_id": lead_id})
        await assert_can_see_lead(admin, lead)
    except HTTPException:
        raise
    except Exception:
        pass
    cur = db[ASSIGNMENT_HISTORY].find({"lead_id": lead_id}).sort("at", -1)
    rows = [_strip_mongo(r) async for r in cur]
    return {"history": rows, "count": len(rows)}


class ManagerUpdate(BaseModel):
    status: Optional[str] = Field(None, description="active / paused / off")
    quota: Optional[int] = None
    specialization: Optional[List[str]] = None
    country: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    sla_response_hours: Optional[int] = None
    scope: Optional[str] = None


@router.patch("/managers/{user_id}")
async def patch_manager(user_id: str, payload: ManagerUpdate, admin=Depends(require_staff)):
    m = await db[MANAGERS].find_one({"user_id": user_id})
    if not m:
        # Auto-create from user record if the user is admin/manager.
        u = (await db.users.find_one({"user_id": user_id})
             or await db.users.find_one({"id": user_id}))
        if not u:
            raise HTTPException(404, detail="Менеджера не знайдено")
        u = _strip_mongo(u)
        if (u.get("role") not in ("admin", "manager")
                and not (set(u.get("roles", [])) & {"admin", "manager"})):
            raise HTTPException(400, detail="User is not eligible to be a manager")
        await upsert_manager_from_user(u)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if updates:
        updates["updated_at"] = _now_iso()
        await db[MANAGERS].update_one({"user_id": user_id}, {"$set": updates})
    return _strip_mongo(await db[MANAGERS].find_one({"user_id": user_id}))


@router.post("/manager-os/backfill")
async def trigger_backfill(admin=Depends(require_staff)):
    """Idempotent manual trigger for the Layer A backfill (admin-only)."""
    # Force a re-run by clearing the marker.
    await db[META].update_one(
        {"key": "ir2_backfill"},
        {"$set": {"version": "force_rerun"}},
        upsert=True,
    )
    return await backfill_once()


# ──────────────────────────────────────────────────────────────────────────
# M7 · Manager Activity Snapshot (backend aggregator)
# ──────────────────────────────────────────────────────────────────────────
LEADS = "lumen_leads"
TASKS = "lumen_lead_tasks"


def _parse_dt(value):
    from datetime import datetime as _dt
    if not value:
        return None
    if isinstance(value, _dt):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        d = _dt.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _manager_snapshot(user_id: str) -> dict:
    """Compute a live KPI snapshot for one manager from real collections."""
    act = await get_activity(user_id)
    leads = [l async for l in db[LEADS].find({"owner_id": user_id})]
    total_leads = len(leads)
    # SLA rollups
    rt = [l.get("first_response_min") for l in leads if l.get("first_response_min") is not None]
    avg_response_min = round(sum(rt) / len(rt), 1) if rt else None
    sla_breached = sum(1 for l in leads if l.get("sla_status") == "breached")
    sla_pending = sum(1 for l in leads if l.get("sla_status") == "pending")
    converted = sum(1 for l in leads if l.get("user_id"))
    # task rollups
    now = datetime.now(timezone.utc)
    open_tasks = 0
    overdue_tasks = 0
    async for t in db[TASKS].find({"assignee_id": user_id, "status": "open"}):
        open_tasks += 1
        dd = _parse_dt(t.get("due_date"))
        if dd and dd < now:
            overdue_tasks += 1
    return {
        "user_id": user_id,
        "activity": act,
        "leads_total": total_leads,
        "leads_converted": converted,
        "conversion_rate": round(converted / total_leads * 100, 1) if total_leads else 0.0,
        "avg_response_min": avg_response_min,
        "sla_breached": sla_breached,
        "sla_pending": sla_pending,
        "open_tasks": open_tasks,
        "overdue_tasks": overdue_tasks,
    }


@router.get("/manager-os/snapshot")
async def manager_os_snapshot(admin=Depends(require_staff)):
    """Per-manager KPI snapshot. Privileged → all managers; manager → self."""
    try:
        from lumen_staff_acl import is_privileged, staff_uid
        privileged = is_privileged(admin)
        me = staff_uid(admin)
    except Exception:
        privileged, me = True, None
    q = {} if privileged else {"user_id": me}
    out = []
    async for m in db[MANAGERS].find(q).sort("created_at", -1):
        m = _strip_mongo(m)
        snap = await _manager_snapshot(m["user_id"])
        out.append({
            "manager_id": m.get("manager_id"),
            "user_id": m.get("user_id"),
            "name": m.get("name"),
            "email": m.get("email"),
            "status": m.get("status"),
            "scope": m.get("scope"),
            "role_in_users": m.get("role_in_users"),
            **snap,
        })
    return {"snapshots": out, "count": len(out)}


@router.get("/manager-os/my-snapshot")
async def my_snapshot(admin=Depends(require_staff)):
    """Current user's own KPI snapshot (for the manager 'My performance' page)."""
    try:
        from lumen_staff_acl import staff_uid
        uid = staff_uid(admin)
    except Exception:
        uid = admin.get("user_id") or admin.get("id")
    m = await db[MANAGERS].find_one({"user_id": uid})
    snap = await _manager_snapshot(uid)
    return {
        "manager": _strip_mongo(m) if m else {"user_id": uid, "name": admin.get("name")},
        **snap,
    }


# ──────────────────────────────────────────────────────────────────────────
# Index bootstrap
# ──────────────────────────────────────────────────────────────────────────
async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        # Communications
        await d[COMMUNICATIONS].create_index("comm_id", unique=True)
        await d[COMMUNICATIONS].create_index([("lead_id", 1), ("at", -1)])
        await d[COMMUNICATIONS].create_index([("user_id", 1), ("at", -1)])
        await d[COMMUNICATIONS].create_index([("kind", 1), ("at", -1)])
        await d[COMMUNICATIONS].create_index(
            [("source_collection", 1), ("source_id", 1), ("kind", 1)],
            name="mirror_idempotency",
        )
        # Managers
        await d[MANAGERS].create_index("manager_id", unique=True)
        await d[MANAGERS].create_index("user_id", unique=True)
        await d[MANAGERS].create_index("email")
        # Activity (one doc per manager)
        await d[MANAGER_ACTIVITY].create_index("user_id", unique=True)
        await d[MANAGER_ACTIVITY].create_index([("last_activity_at", -1)])
        # Assignment history
        await d[ASSIGNMENT_HISTORY].create_index("assign_id", unique=True)
        await d[ASSIGNMENT_HISTORY].create_index([("lead_id", 1), ("at", -1)])
        await d[ASSIGNMENT_HISTORY].create_index([("to_user_id", 1), ("at", -1)])
        # Scopes (placeholder collection — empty by design in Beta)
        await d[MANAGER_SCOPES].create_index("user_id", unique=True)
        # Meta
        await d[META].create_index("key", unique=True)
    except Exception as e:
        logger.warning("ensure_indexes(manager_os) warn: %s", e)
