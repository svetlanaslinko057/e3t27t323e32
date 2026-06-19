"""
LUMEN — Manager OS · M3 — Lead SLA Engine.

Deterministic, no-LLM service that answers the question that becomes critical
at the 1-year horizon: *which manager actually responds, and how fast?*

SLA fields stored ON the lead document (``lumen_leads``):
  * sla_due_at        — created_at + response window (hours)
  * first_response_at — first staff interaction after creation
  * first_response_min— minutes between created_at and first_response_at
  * last_response_at  — most recent staff interaction
  * sla_status        — pending | responded | breached
  * sla_breach_at     — when a pending lead crossed its due time unanswered

Response window resolution order:
  1. the OWNER's ``lumen_managers.sla_response_hours`` (if owner set)
  2. global setting ``lumen_settings.lead_sla_hours``
  3. env ``LUMEN_LEAD_SLA_HOURS``
  4. hard default = 24h

First-response is stamped by IR write paths (note / task / meeting / stage /
manual communication). The background scan flips still-pending overdue leads
to ``breached`` exactly once and raises a ``sla_breach`` staff notification.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from lumen_api import db

logger = logging.getLogger("lumen.sla")

LEADS = "lumen_leads"
MANAGERS = "lumen_managers"
SETTINGS = "lumen_settings"

HARD_DEFAULT_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value) -> Optional[datetime]:
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


async def _global_hours() -> int:
    try:
        doc = await db[SETTINGS].find_one({"key": "lead_sla_hours"})
        if doc and doc.get("value"):
            return int(doc["value"])
    except Exception:
        pass
    try:
        env = os.environ.get("LUMEN_LEAD_SLA_HOURS")
        if env:
            return int(env)
    except Exception:
        pass
    return HARD_DEFAULT_HOURS


async def _owner_hours(owner_id: Optional[str]) -> Optional[int]:
    if not owner_id:
        return None
    try:
        m = await db[MANAGERS].find_one({"user_id": owner_id}, {"sla_response_hours": 1})
        h = (m or {}).get("sla_response_hours")
        return int(h) if h else None
    except Exception:
        return None


async def resolve_hours(owner_id: Optional[str]) -> int:
    return (await _owner_hours(owner_id)) or (await _global_hours())


async def init_lead_sla(created_at_iso: str, owner_id: Optional[str] = None) -> dict:
    """Return the SLA fields to set on a freshly created lead."""
    created = _parse_dt(created_at_iso) or _now()
    hours = await resolve_hours(owner_id)
    due = created + timedelta(hours=hours)
    return {
        "sla_due_at": _iso(due),
        "sla_hours": hours,
        "first_response_at": None,
        "first_response_min": None,
        "last_response_at": None,
        "sla_status": "pending",
        "sla_breach_at": None,
    }


async def mark_first_response(lead_id: str, actor: Optional[dict] = None) -> None:
    """Stamp first/last response on a staff interaction. Idempotent for first."""
    try:
        lead = await db[LEADS].find_one(
            {"lead_id": lead_id},
            {"created_at": 1, "sla_due_at": 1, "first_response_at": 1, "sla_status": 1},
        )
        if not lead:
            return
        now = _now()
        updates = {"last_response_at": _iso(now)}
        if not lead.get("first_response_at"):
            created = _parse_dt(lead.get("created_at")) or now
            mins = max(0, round((now - created).total_seconds() / 60.0, 1))
            due = _parse_dt(lead.get("sla_due_at"))
            # responded in time, unless it had already been flipped to breached
            if lead.get("sla_status") == "breached":
                status = "breached"
            elif due and now > due:
                status = "breached"
            else:
                status = "responded"
            updates.update({
                "first_response_at": _iso(now),
                "first_response_min": mins,
                "sla_status": status,
            })
        await db[LEADS].update_one({"lead_id": lead_id}, {"$set": updates})
    except Exception as e:
        logger.warning("mark_first_response failed lead=%s err=%s", lead_id, e)


def live_state(lead: dict) -> dict:
    """Compute a display-only SLA state (does not write). Used by enrich."""
    status = lead.get("sla_status") or "pending"
    due = _parse_dt(lead.get("sla_due_at"))
    now = _now()
    at_risk = False
    overdue = False
    minutes_left = None
    if status == "pending" and due:
        delta_min = (due - now).total_seconds() / 60.0
        minutes_left = round(delta_min, 0)
        if delta_min < 0:
            overdue = True
        elif delta_min <= 120:  # within 2h of breach
            at_risk = True
    return {
        "status": status,
        "due_at": lead.get("sla_due_at"),
        "first_response_at": lead.get("first_response_at"),
        "first_response_min": lead.get("first_response_min"),
        "last_response_at": lead.get("last_response_at"),
        "breach_at": lead.get("sla_breach_at"),
        "at_risk": at_risk,
        "overdue": overdue,
        "minutes_left": minutes_left,
    }


async def scan_overdue() -> dict:
    """Flip still-pending overdue leads to ``breached`` (once) + notify owner.

    Idempotent: only leads with sla_status == 'pending' AND due < now are
    touched, and they leave the 'pending' set immediately so the next scan
    won't re-fire.
    """
    stats = {"breached": 0, "scanned": 0}
    now = _now()
    try:
        cur = db[LEADS].find({"sla_status": "pending"})
        async for lead in cur:
            stats["scanned"] += 1
            due = _parse_dt(lead.get("sla_due_at"))
            if not due or now <= due:
                continue
            lead_id = lead.get("lead_id")
            await db[LEADS].update_one(
                {"lead_id": lead_id},
                {"$set": {"sla_status": "breached", "sla_breach_at": _iso(now)}},
            )
            stats["breached"] += 1
            # notify owner (+ admins fallback handled by notifier)
            try:
                from lumen_staff_notifications import notify_sla_breach
                await notify_sla_breach(lead)
            except Exception:
                pass
    except Exception as e:
        logger.warning("scan_overdue failed: %s", e)
    if stats["breached"]:
        logger.info("[sla] scan: %s", stats)
    return stats


async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[LEADS].create_index("sla_status")
        await d[LEADS].create_index("sla_due_at")
    except Exception as e:
        logger.warning("ensure_indexes(sla) warn: %s", e)


async def backfill_missing() -> dict:
    """Add SLA fields to legacy leads that predate the engine. Idempotent."""
    n = 0
    try:
        async for lead in db[LEADS].find({"sla_status": {"$exists": False}}):
            fields = await init_lead_sla(lead.get("created_at"), lead.get("owner_id"))
            # legacy leads with prior activity are considered already-responded
            # so we don't retroactively breach them on first scan
            if lead.get("last_interaction_at"):
                fields["sla_status"] = "responded"
                fields["first_response_at"] = lead.get("last_interaction_at")
                fields["last_response_at"] = lead.get("last_interaction_at")
            await db[LEADS].update_one({"lead_id": lead.get("lead_id")}, {"$set": fields})
            n += 1
    except Exception as e:
        logger.warning("backfill_missing(sla) failed: %s", e)
    if n:
        logger.info("[sla] backfilled %d legacy leads", n)
    return {"backfilled": n}
