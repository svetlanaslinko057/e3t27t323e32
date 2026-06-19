"""
LUMEN — Manager OS · M4 — Staff (in-app) Notifications.

A lightweight, staff-facing notification feed that is SEPARATE from the
investor-facing ``lumen_notifications`` and the DevOS dev ``notifications``
collection. Surfaces to managers/admins in a dedicated bell.

Kinds (extensible strings):
  * new_lead_assigned   — a lead was assigned/reassigned to you
  * task_due_today      — you have an open task due today
  * task_overdue        — you have an open task past its due date
  * meeting_in_1_hour   — a meeting you own starts within the next hour
  * sla_breach          — a lead you own breached its first-response SLA

Delivery is in-app only for now (no email) — by design. The reminder scan is
idempotent per (user, kind, ref, day) so it never spams.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query

from lumen_api import db, require_staff, _strip_mongo

logger = logging.getLogger("lumen.staff_notify")

router = APIRouter(prefix="/api/staff", tags=["lumen-staff-notifications"])

NOTIFS = "lumen_staff_notifications"
LEADS = "lumen_leads"
TASKS = "lumen_lead_tasks"
MEETINGS = "lumen_lead_meetings"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _uid(user: dict) -> Optional[str]:
    return user.get("user_id") or user.get("id")


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def notify_staff(
    user_id: Optional[str],
    kind: str,
    title: str,
    body: str = "",
    *,
    link: Optional[str] = None,
    lead_id: Optional[str] = None,
    meta: Optional[dict] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[dict]:
    """Create one staff notification. No-op when user_id is None.

    When ``dedupe_key`` is set, a notification with the same
    (user_id, dedupe_key) created in the last 20h is NOT duplicated — this is
    what keeps the daily reminder scans from spamming.
    """
    if not user_id:
        return None
    try:
        if dedupe_key:
            since = _iso(_now() - timedelta(hours=20))
            existing = await db[NOTIFS].find_one({
                "user_id": user_id,
                "dedupe_key": dedupe_key,
                "created_at": {"$gte": since},
            })
            if existing:
                return _strip_mongo(existing)
        doc = {
            "id": f"snotif_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "kind": kind,
            "title": title,
            "body": body,
            "link": link,
            "lead_id": lead_id,
            "meta": meta or {},
            "dedupe_key": dedupe_key,
            "read": False,
            "created_at": _iso(),
        }
        await db[NOTIFS].insert_one(doc)
        return _strip_mongo(doc)
    except Exception as e:
        logger.warning("notify_staff failed user=%s kind=%s err=%s", user_id, kind, e)
        return None


async def _admin_user_ids() -> List[str]:
    ids = []
    try:
        async for u in db.users.find(
            {"$or": [{"role": "admin"}, {"roles": "admin"}]},
            {"user_id": 1, "id": 1},
        ):
            ids.append(u.get("user_id") or u.get("id"))
    except Exception:
        pass
    return [i for i in ids if i]


async def notify_new_lead_assigned(lead: dict, to_user_id: str, *, actor_name: str = ""):
    if not to_user_id:
        return
    name = lead.get("full_name") or lead.get("email") or lead.get("lead_id")
    await notify_staff(
        to_user_id,
        "new_lead_assigned",
        "Новий лід призначено",
        f"Вам призначено лід: {name}" + (f" · {actor_name}" if actor_name else ""),
        link="/manager/leads",
        lead_id=lead.get("lead_id"),
    )


async def notify_sla_breach(lead: dict):
    owner_id = lead.get("owner_id")
    name = lead.get("full_name") or lead.get("email") or lead.get("lead_id")
    title = "Порушено SLA першої відповіді"
    body = f"Лід {name} не отримав відповіді вчасно."
    dk = f"sla_breach:{lead.get('lead_id')}"
    if owner_id:
        await notify_staff(owner_id, "sla_breach", title, body,
                           link="/manager/leads", lead_id=lead.get("lead_id"),
                           dedupe_key=dk)
    else:
        # unassigned breach → alert all admins
        for aid in await _admin_user_ids():
            await notify_staff(aid, "sla_breach", title,
                               f"Непризначений лід {name} порушив SLA.",
                               link="/admin/investor-relations",
                               lead_id=lead.get("lead_id"),
                               dedupe_key=dk)


# ---------------------------------------------------------------------------
# Reminder scan (idempotent per day)
# ---------------------------------------------------------------------------
async def scan_reminders() -> dict:
    stats = {"task_due_today": 0, "task_overdue": 0, "meeting_soon": 0}
    now = _now()
    today = now.date()
    try:
        # Open tasks with a due date + an assignee.
        async for t in db[TASKS].find({"status": "open", "assignee_id": {"$ne": None}}):
            due = _parse_dt(t.get("due_date"))
            if not due:
                continue
            assignee = t.get("assignee_id")
            title = t.get("title") or "Задача"
            if due < now and due.date() < today:
                await notify_staff(
                    assignee, "task_overdue", "Прострочена задача",
                    f"Задача «{title}» прострочена.",
                    link="/manager/leads", lead_id=t.get("lead_id"),
                    dedupe_key=f"task_overdue:{t.get('id')}:{today.isoformat()}",
                )
                stats["task_overdue"] += 1
            elif due.date() == today:
                await notify_staff(
                    assignee, "task_due_today", "Задача на сьогодні",
                    f"Сьогодні дедлайн задачі «{title}».",
                    link="/manager/leads", lead_id=t.get("lead_id"),
                    dedupe_key=f"task_due:{t.get('id')}:{today.isoformat()}",
                )
                stats["task_due_today"] += 1

        # Meetings starting within the next 60 minutes.
        soon = now + timedelta(minutes=60)
        async for m in db[MEETINGS].find({"status": "scheduled"}):
            sched = _parse_dt(m.get("scheduled_at"))
            if not sched:
                continue
            if now <= sched <= soon:
                # owner of the lead, fallback to nobody
                lead = await db[LEADS].find_one({"lead_id": m.get("lead_id")}, {"owner_id": 1})
                owner = (lead or {}).get("owner_id")
                if owner:
                    await notify_staff(
                        owner, "meeting_in_1_hour", "Зустріч скоро",
                        f"Зустріч «{m.get('title','')}» почнеться протягом години.",
                        link="/manager/leads", lead_id=m.get("lead_id"),
                        dedupe_key=f"meeting_soon:{m.get('id')}",
                    )
                    stats["meeting_soon"] += 1
    except Exception as e:
        logger.warning("scan_reminders failed: %s", e)
    return stats


# ---------------------------------------------------------------------------
# HTTP surface (each staff user sees ONLY their own notifications)
# ---------------------------------------------------------------------------
@router.get("/notifications")
async def list_notifications(
    user=Depends(require_staff),
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
):
    q = {"user_id": _uid(user)}
    if unread_only:
        q["read"] = False
    cur = db[NOTIFS].find(q).sort("created_at", -1).limit(limit)
    rows = [_strip_mongo(r) async for r in cur]
    return {"notifications": rows, "count": len(rows)}


@router.get("/notifications/unread-count")
async def unread_count(user=Depends(require_staff)):
    n = await db[NOTIFS].count_documents({"user_id": _uid(user), "read": False})
    return {"count": n}


@router.post("/notifications/read-all")
async def read_all(user=Depends(require_staff)):
    await db[NOTIFS].update_many(
        {"user_id": _uid(user), "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/{notif_id}/read")
async def read_one(notif_id: str, user=Depends(require_staff)):
    r = await db[NOTIFS].update_one(
        {"id": notif_id, "user_id": _uid(user)}, {"$set": {"read": True}})
    if not r.matched_count:
        raise HTTPException(404, detail="Сповіщення не знайдено")
    return {"ok": True}


async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[NOTIFS].create_index("id", unique=True)
        await d[NOTIFS].create_index([("user_id", 1), ("read", 1), ("created_at", -1)])
        await d[NOTIFS].create_index([("user_id", 1), ("dedupe_key", 1)])
    except Exception as e:
        logger.warning("ensure_indexes(staff_notifications) warn: %s", e)
