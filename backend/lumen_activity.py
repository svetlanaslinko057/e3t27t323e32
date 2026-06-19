"""
LUMEN — F2 Site Activity Layer (Lumen Activity Layer)
=====================================================

The missing top-of-funnel telemetry. Turns the blind SEO → Visitor → Lead →
Meeting → KYC → ... → Active Investor chain into a real, queryable activity
graph — NOT a generic Google-Analytics counter.

Six sub-systems (all shipped as one cycle):

    F2.1  Event Store        — `lumen_activity_events` (raw, TTL 24 months)
    F2.2  Visitor Identity   — `lumen_activity_identities` (visitor↔lead↔user↔profile)
    F2.3  Activity Timeline  — per-identity unified feed (all linked ids)
    F2.4  Abandonment        — abandoned_stage + days_idle
    F2.5  Live Activity       — who is on the site right now (polling 30s)
    F2.6  Attribution        — top pages, leads-by-page, funding-by-asset, manager conv
    F2.6a Retention/TTL      — raw 24mo TTL + `lumen_activity_daily` rollup (no TTL)

Identity model (F2.2 / 3a retroactive stitching):

    visitor_id  (anonymous, set by the browser, localStorage)
        ↓
    lead_id     (POST /api/leads/intake)
        ↓
    user_id     (registration / login)
        ↓
    investor_profile_id

`/api/activity/identify` stitches these together AND back-fills every prior
anonymous event so the investor card shows one uninterrupted lifetime feed.

`/api/activity/track` is auth-free and fire-and-forget (the visitor surface is
pre-login; forcing auth would bias the measurement). It still attaches a
`user_id` opportunistically when a `session_token` cookie is present.
"""
from __future__ import annotations

import os
import time
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("lumen.activity")

# ---------------------------------------------------------------------------
# Mongo (own client; same MONGO_URL/DB_NAME as the rest of the platform)
# ---------------------------------------------------------------------------
_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
db = AsyncIOMotorClient(_MONGO_URL)[_DB_NAME]

EVENTS = "lumen_activity_events"
IDENTITIES = "lumen_activity_identities"
DAILY = "lumen_activity_daily"

RAW_TTL_DAYS = int(os.environ.get("LUMEN_ACTIVITY_TTL_DAYS", "730"))  # 24 months
LIVE_WINDOW_MIN = int(os.environ.get("LUMEN_ACTIVITY_LIVE_MIN", "5"))
ABANDON_IDLE_DAYS = int(os.environ.get("LUMEN_ACTIVITY_ABANDON_DAYS", "3"))

# ---------------------------------------------------------------------------
# Event taxonomy + funnel-stage mapping
# ---------------------------------------------------------------------------
# ordinal → canonical stage key (aligned with lumen_funnel STAGE_KEYS where it
# matters; collapsed for abandonment readability)
STAGE_ORDER = [
    "visitor",
    "lead",
    "meeting",
    "kyc_started",
    "kyc_completed",
    "contract_opened",
    "contract_signed",
    "funding_started",
    "funding_confirmed",
    "certificate",
    "active_investor",
]
STAGE_INDEX = {k: i for i, k in enumerate(STAGE_ORDER)}

STAGE_LABELS = {
    "visitor": {"uk": "Відвідувач", "en": "Visitor"},
    "lead": {"uk": "Лід", "en": "Lead"},
    "meeting": {"uk": "Зустріч", "en": "Meeting"},
    "kyc_started": {"uk": "KYC розпочато", "en": "KYC Started"},
    "kyc_completed": {"uk": "KYC завершено", "en": "KYC Completed"},
    "contract_opened": {"uk": "Договір відкрито", "en": "Contract Opened"},
    "contract_signed": {"uk": "Договір підписано", "en": "Contract Signed"},
    "funding_started": {"uk": "Поповнення розпочато", "en": "Funding Started"},
    "funding_confirmed": {"uk": "Поповнення підтверджено", "en": "Funding Confirmed"},
    "certificate": {"uk": "Сертифікат", "en": "Certificate"},
    "active_investor": {"uk": "Активний інвестор", "en": "Active Investor"},
}

# event name → stage it implies (for abandonment / furthest-stage detection)
EVENT_STAGE = {
    "page_view": "visitor",
    "session_start": "visitor",
    "session_end": "visitor",
    "cta_click": "visitor",
    "asset_view": "visitor",
    "fund_view": "visitor",
    "lead_created": "lead",
    "meeting_scheduled": "meeting",
    "kyc_started": "kyc_started",
    "kyc_completed": "kyc_completed",
    "contract_opened": "contract_opened",
    "contract_signed": "contract_signed",
    "funding_started": "funding_started",
    "funding_confirmed": "funding_confirmed",
    "certificate_viewed": "certificate",
    "certificate_downloaded": "certificate",
}

KNOWN_EVENTS = set(EVENT_STAGE.keys())

# human labels for timeline rendering
EVENT_LABELS = {
    "page_view": {"uk": "Перегляд сторінки", "en": "Page view"},
    "session_start": {"uk": "Початок сесії", "en": "Session start"},
    "session_end": {"uk": "Кінець сесії", "en": "Session end"},
    "cta_click": {"uk": "Клік на CTA", "en": "CTA clicked"},
    "asset_view": {"uk": "Перегляд об'єкта", "en": "Asset viewed"},
    "fund_view": {"uk": "Перегляд фонду", "en": "Fund viewed"},
    "lead_created": {"uk": "Лід створений", "en": "Lead created"},
    "meeting_scheduled": {"uk": "Зустріч заплановано", "en": "Meeting scheduled"},
    "kyc_started": {"uk": "KYC розпочато", "en": "KYC started"},
    "kyc_completed": {"uk": "KYC завершено", "en": "KYC completed"},
    "contract_opened": {"uk": "Договір відкрито", "en": "Contract opened"},
    "contract_signed": {"uk": "Договір підписано", "en": "Contract signed"},
    "funding_started": {"uk": "Поповнення розпочато", "en": "Funding started"},
    "funding_confirmed": {"uk": "Поповнення підтверджено", "en": "Funding confirmed"},
    "certificate_viewed": {"uk": "Сертифікат переглянуто", "en": "Certificate viewed"},
    "certificate_downloaded": {"uk": "Сертифікат завантажено", "en": "Certificate downloaded"},
}

_MAX_PROPS_BYTES = 4_000
_MAX_BATCH = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_dt(dt: Any) -> Optional[datetime]:
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Any) -> Optional[str]:
    d = _norm_dt(dt)
    return d.isoformat() if d else None


def _clean_str(s: Any, n: int = 128) -> Optional[str]:
    if s is None:
        return None
    return str(s).strip()[:n] or None


def _trim_props(p: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(p, dict):
        return {}
    out: Dict[str, Any] = {}
    used = 0
    for k, v in p.items():
        try:
            ks = str(k)[:64]
            if isinstance(v, (int, float, bool)) or v is None:
                vs: Any = v
                added = len(ks) + 16
            else:
                vs = str(v)[:256]
                added = len(ks) + len(vs)
            if used + added > _MAX_PROPS_BYTES:
                break
            out[ks] = vs
            used += added
        except Exception:
            continue
    return out


def _strip(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Optional-auth resolver (best-effort; never raises)
# ---------------------------------------------------------------------------
async def _resolve_optional_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session_token") or request.cookies.get("auth_session_token")
    if not token:
        return None
    try:
        sess = (
            await db.user_sessions.find_one({"session_token": token})
            or await db.sessions.find_one({"token": token})
            or await db.auth_sessions.find_one({"token": token})
        )
        if not sess:
            return None
        uid = sess.get("user_id") or sess.get("uid")
        if not uid:
            return None
        user = await db.users.find_one({"user_id": uid}) or await db.users.find_one({"id": uid})
        return _strip(user) if user else None
    except Exception:
        return None


# ===========================================================================
# F2.2 — Identity store
# ===========================================================================
async def _upsert_identity(
    visitor_id: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    manager_id: Optional[str] = None,
    investor_profile_id: Optional[str] = None,
    at: Optional[datetime] = None,
) -> None:
    if not visitor_id:
        return
    at = at or _now()
    set_fields: Dict[str, Any] = {"last_seen_at": at, "visitor_id": visitor_id}
    if user_id:
        set_fields["user_id"] = user_id
    if lead_id:
        set_fields["lead_id"] = lead_id
    if manager_id:
        set_fields["manager_id"] = manager_id
    if investor_profile_id:
        set_fields["investor_profile_id"] = investor_profile_id

    add_to_set: Dict[str, Any] = {}
    if session_id:
        add_to_set["sessions"] = session_id

    update: Dict[str, Any] = {
        "$set": set_fields,
        "$setOnInsert": {"first_visit_at": at, "created_at": at},
        "$inc": {"event_count": 1},
    }
    if add_to_set:
        update["$addToSet"] = add_to_set
    try:
        await db[IDENTITIES].update_one({"_id": visitor_id}, update, upsert=True)
    except Exception as e:  # pragma: no cover
        logger.warning(f"ACTIVITY identity upsert failed vid={visitor_id} err={e}")


async def _resolve_linked_ids(
    *, visitor_id: Optional[str] = None,
    user_id: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> dict:
    """Given any one id, return the full linked identity bundle + all visitor_ids."""
    q: List[dict] = []
    if visitor_id:
        q.append({"_id": visitor_id})
        q.append({"visitor_id": visitor_id})
    if user_id:
        q.append({"user_id": user_id})
    if lead_id:
        q.append({"lead_id": lead_id})
    bundle = {
        "visitor_ids": set(),
        "user_id": user_id,
        "lead_id": lead_id,
        "investor_profile_id": None,
        "manager_id": None,
        "first_visit_at": None,
    }
    if not q:
        return {**bundle, "visitor_ids": list(bundle["visitor_ids"])}
    try:
        async for ident in db[IDENTITIES].find({"$or": q}):
            vid = ident.get("visitor_id") or ident.get("_id")
            if vid:
                bundle["visitor_ids"].add(vid)
            bundle["user_id"] = bundle["user_id"] or ident.get("user_id")
            bundle["lead_id"] = bundle["lead_id"] or ident.get("lead_id")
            bundle["investor_profile_id"] = bundle["investor_profile_id"] or ident.get("investor_profile_id")
            bundle["manager_id"] = bundle["manager_id"] or ident.get("manager_id")
            fv = _norm_dt(ident.get("first_visit_at"))
            if fv and (bundle["first_visit_at"] is None or fv < bundle["first_visit_at"]):
                bundle["first_visit_at"] = fv
    except Exception:
        pass
    # second pass: if we now know user_id/lead_id, gather any other visitor rows
    extra_q: List[dict] = []
    if bundle["user_id"]:
        extra_q.append({"user_id": bundle["user_id"]})
    if bundle["lead_id"]:
        extra_q.append({"lead_id": bundle["lead_id"]})
    if extra_q:
        try:
            async for ident in db[IDENTITIES].find({"$or": extra_q}):
                vid = ident.get("visitor_id") or ident.get("_id")
                if vid:
                    bundle["visitor_ids"].add(vid)
        except Exception:
            pass
    bundle["visitor_ids"] = list(bundle["visitor_ids"])
    return bundle


# ===========================================================================
# Write path
# ===========================================================================
async def _write_events(events: List[dict], user: Optional[dict], request: Request) -> int:
    now = _now()
    ua = _clean_str(request.headers.get("user-agent"), 256)
    xff = request.headers.get("x-forwarded-for")
    ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else None))
    ip = _clean_str(ip, 64)

    docs: List[dict] = []
    touched_visitors: Dict[str, dict] = {}
    for raw in events[:_MAX_BATCH]:
        if not isinstance(raw, dict):
            continue
        ev = _clean_str(raw.get("event"), 64)
        if not ev:
            continue
        visitor_id = _clean_str(raw.get("visitor_id"), 64)
        session_id = _clean_str(raw.get("session_id"), 64)
        props = _trim_props(raw.get("props"))
        # opportunistic identity from cookie
        uid = _clean_str(raw.get("user_id"), 64) or (user.get("user_id") if user else None)
        lead_id = _clean_str(raw.get("lead_id"), 64)
        manager_id = _clean_str(raw.get("manager_id"), 64)
        if user and not manager_id:
            manager_id = user.get("manager_id") or user.get("owner_id") or user.get("assigned_manager_id")

        occurred = _norm_dt(raw.get("occurred_at")) or now
        doc = {
            "event_id": f"ae_{uuid.uuid4().hex[:16]}",
            "event": ev,
            "surface": _clean_str(raw.get("surface"), 32) or "web",
            "visitor_id": visitor_id,
            "session_id": session_id,
            "user_id": uid,
            "lead_id": lead_id,
            "manager_id": manager_id,
            "path": _clean_str(raw.get("path") or props.get("path"), 256),
            "referrer": _clean_str(raw.get("referrer") or props.get("referrer"), 256),
            "asset_id": _clean_str(props.get("asset_id"), 64),
            "fund_id": _clean_str(props.get("fund_id"), 64),
            "contract_id": _clean_str(props.get("contract_id"), 64),
            "device": _clean_str(raw.get("device"), 16),
            "ua": ua,
            "ip": ip,
            "props": props,
            "occurred_at": occurred,
            "created_at": now,
            "stage": EVENT_STAGE.get(ev),
        }
        docs.append(doc)
        if visitor_id:
            t = touched_visitors.setdefault(visitor_id, {
                "session_id": session_id, "user_id": uid, "lead_id": lead_id,
                "manager_id": manager_id, "at": occurred,
            })
            # keep earliest "at" for first_visit accuracy
            if occurred < t["at"]:
                t["at"] = occurred
            t["session_id"] = t["session_id"] or session_id
            t["user_id"] = t["user_id"] or uid
            t["lead_id"] = t["lead_id"] or lead_id

    if not docs:
        return 0
    try:
        await db[EVENTS].insert_many(docs, ordered=False)
    except Exception as e:  # pragma: no cover
        logger.warning(f"ACTIVITY insert_many failed err={e}")

    for vid, t in touched_visitors.items():
        await _upsert_identity(
            vid, session_id=t["session_id"], user_id=t["user_id"],
            lead_id=t["lead_id"], manager_id=t["manager_id"], at=t["at"],
        )
        # 5a — propagate real first_visit_at to the user record (funnel Visitor stage)
        if t["user_id"]:
            try:
                await db.users.update_one(
                    {"user_id": t["user_id"], "$or": [
                        {"first_visit_at": {"$exists": False}},
                        {"first_visit_at": None},
                        {"first_visit_at": {"$gt": t["at"]}},
                    ]},
                    {"$set": {"first_visit_at": t["at"]}},
                )
            except Exception:
                pass
    return len(docs)


# ===========================================================================
# F2.2 — identify (stitch + 3a retroactive back-fill)
# ===========================================================================
async def _identify(
    *, visitor_id: str, user_id: Optional[str], lead_id: Optional[str],
    manager_id: Optional[str], investor_profile_id: Optional[str],
) -> dict:
    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id required")

    await _upsert_identity(
        visitor_id, user_id=user_id, lead_id=lead_id,
        manager_id=manager_id, investor_profile_id=investor_profile_id,
    )
    bundle = await _resolve_linked_ids(visitor_id=visitor_id, user_id=user_id, lead_id=lead_id)
    vids = list(set(bundle["visitor_ids"] + [visitor_id]))
    user_id = user_id or bundle["user_id"]
    lead_id = lead_id or bundle["lead_id"]

    # 3a — retroactively back-fill every anonymous event under these visitor_ids
    set_fields: Dict[str, Any] = {}
    if user_id:
        set_fields["user_id"] = user_id
    if lead_id:
        set_fields["lead_id"] = lead_id
    if manager_id:
        set_fields["manager_id"] = manager_id
    backfilled = 0
    if vids and set_fields:
        try:
            res = await db[EVENTS].update_many(
                {"visitor_id": {"$in": vids}}, {"$set": set_fields}
            )
            backfilled = res.modified_count
        except Exception as e:
            logger.warning(f"ACTIVITY backfill failed err={e}")
        # also link sibling identity rows
        try:
            await db[IDENTITIES].update_many(
                {"visitor_id": {"$in": vids}}, {"$set": set_fields}
            )
        except Exception:
            pass

    # 5a — set real first_visit_at on the user from earliest visitor event
    if user_id and bundle["first_visit_at"]:
        try:
            await db.users.update_one(
                {"user_id": user_id, "$or": [
                    {"first_visit_at": {"$exists": False}},
                    {"first_visit_at": None},
                    {"first_visit_at": {"$gt": bundle["first_visit_at"]}},
                ]},
                {"$set": {"first_visit_at": bundle["first_visit_at"]}},
            )
        except Exception:
            pass

    return {
        "ok": True,
        "visitor_id": visitor_id,
        "linked_visitor_ids": vids,
        "user_id": user_id,
        "lead_id": lead_id,
        "events_backfilled": backfilled,
        "first_visit_at": _iso(bundle["first_visit_at"]),
    }


# ===========================================================================
# F2.6a — Daily rollup
# ===========================================================================
async def _rollup_day(day: Optional[datetime] = None) -> dict:
    """Aggregate one UTC day into lumen_activity_daily (idempotent upsert)."""
    day = (day or _now()).astimezone(timezone.utc)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    date_key = start.strftime("%Y-%m-%d")

    match = {"occurred_at": {"$gte": start, "$lt": end}}
    by_event: Dict[str, int] = {}
    visitors = set()
    sessions = set()
    by_page: Dict[str, int] = {}
    by_asset: Dict[str, int] = {}
    leads = 0
    total = 0
    try:
        async for d in db[EVENTS].find(match, {
            "event": 1, "visitor_id": 1, "session_id": 1, "path": 1, "asset_id": 1,
        }):
            total += 1
            ev = d.get("event") or "unknown"
            by_event[ev] = by_event.get(ev, 0) + 1
            if d.get("visitor_id"):
                visitors.add(d["visitor_id"])
            if d.get("session_id"):
                sessions.add(d["session_id"])
            if d.get("path"):
                by_page[d["path"]] = by_page.get(d["path"], 0) + 1
            if d.get("asset_id"):
                by_asset[d["asset_id"]] = by_asset.get(d["asset_id"], 0) + 1
            if ev == "lead_created":
                leads += 1
    except Exception as e:
        logger.warning(f"ACTIVITY rollup scan failed err={e}")

    doc = {
        "date": date_key,
        "total_events": total,
        "unique_visitors": len(visitors),
        "unique_sessions": len(sessions),
        "leads": leads,
        "by_event": by_event,
        "by_page": dict(sorted(by_page.items(), key=lambda x: x[1], reverse=True)[:50]),
        "by_asset": dict(sorted(by_asset.items(), key=lambda x: x[1], reverse=True)[:50]),
        "rolled_at": _now(),
    }
    try:
        await db[DAILY].update_one({"date": date_key}, {"$set": doc}, upsert=True)
    except Exception as e:
        logger.warning(f"ACTIVITY rollup upsert failed err={e}")
    return doc


# ===========================================================================
# Index bootstrap
# ===========================================================================
async def ensure_indexes() -> None:
    try:
        await db[EVENTS].create_index("occurred_at", expireAfterSeconds=RAW_TTL_DAYS * 86400)
        await db[EVENTS].create_index("visitor_id")
        await db[EVENTS].create_index("user_id")
        await db[EVENTS].create_index("lead_id")
        await db[EVENTS].create_index("session_id")
        await db[EVENTS].create_index("event")
        await db[IDENTITIES].create_index("user_id")
        await db[IDENTITIES].create_index("lead_id")
        await db[IDENTITIES].create_index("last_seen_at")
        await db[DAILY].create_index("date", unique=True)
        logger.info(f"ACTIVITY indexes ensured (raw TTL={RAW_TTL_DAYS}d, no TTL on {DAILY})")
    except Exception as e:
        logger.warning(f"ACTIVITY ensure_indexes failed err={e}")


_rollup_task: Optional[asyncio.Task] = None


async def _rollup_loop():
    # initial small delay so boot isn't blocked
    await asyncio.sleep(20)
    while True:
        try:
            await _rollup_day(_now())                       # today (running total)
            await _rollup_day(_now() - timedelta(days=1))    # yesterday (final)
        except Exception as e:
            logger.warning(f"ACTIVITY rollup loop err={e}")
        await asyncio.sleep(3600)  # hourly refresh


def start_scheduler():
    global _rollup_task
    if _rollup_task is None:
        try:
            loop = asyncio.get_event_loop()
            _rollup_task = loop.create_task(_rollup_loop())
            logger.info("ACTIVITY rollup scheduler started (hourly)")
        except Exception as e:
            logger.warning(f"ACTIVITY scheduler start failed err={e}")


# ===========================================================================
# Pydantic
# ===========================================================================
class TrackEvent(BaseModel):
    event: str
    surface: Optional[str] = None
    visitor_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    lead_id: Optional[str] = None
    manager_id: Optional[str] = None
    path: Optional[str] = None
    referrer: Optional[str] = None
    device: Optional[str] = None
    occurred_at: Optional[datetime] = None
    props: Optional[Dict[str, Any]] = None


class TrackBatch(BaseModel):
    events: List[TrackEvent] = Field(default_factory=list)


class IdentifyIn(BaseModel):
    visitor_id: str
    user_id: Optional[str] = None
    lead_id: Optional[str] = None
    manager_id: Optional[str] = None
    investor_profile_id: Optional[str] = None


# ===========================================================================
# Router
# ===========================================================================
def build_router(require_admin, require_staff, get_current_user) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["lumen-activity"])

    # ---- F2.1 ingest (auth-free, fire-and-forget) ----
    @router.post("/activity/track")
    async def track(body: TrackBatch, request: Request):
        if not body.events:
            return {"ok": True, "accepted": 0}
        user = await _resolve_optional_user(request)
        events = [e.model_dump() for e in body.events]
        n = await _write_events(events, user, request)
        # F3 · keep the staff session's last_seen_at fresh for presence
        if user:
            try:
                import f3_staff_sessions as _f3
                await _f3.touch_session(
                    request.cookies.get("session_token") or request.cookies.get("auth_session_token")
                )
            except Exception:
                pass
        return {"ok": True, "accepted": n}

    # ---- F2.2 identify (auth-optional) ----
    @router.post("/activity/identify")
    async def identify(body: IdentifyIn, request: Request):
        user = await _resolve_optional_user(request)
        user_id = body.user_id or (user.get("user_id") if user else None)
        manager_id = body.manager_id
        if user and not manager_id:
            manager_id = user.get("manager_id") or user.get("owner_id") or user.get("assigned_manager_id")
        return await _identify(
            visitor_id=body.visitor_id, user_id=user_id, lead_id=body.lead_id,
            manager_id=manager_id, investor_profile_id=body.investor_profile_id,
        )

    # ---- F2.5 live activity ----
    @router.get("/admin/activity/live")
    async def live(_staff: dict = Depends(require_staff)):
        since = _now() - timedelta(minutes=LIVE_WINDOW_MIN)
        sessions: Dict[str, dict] = {}
        try:
            async for d in db[EVENTS].find(
                {"occurred_at": {"$gte": since}},
                {"session_id": 1, "visitor_id": 1, "user_id": 1, "lead_id": 1,
                 "event": 1, "path": 1, "asset_id": 1, "stage": 1, "occurred_at": 1},
            ).sort("occurred_at", 1):
                sid = d.get("session_id") or d.get("visitor_id") or d.get("event_id")
                if not sid:
                    continue
                s = sessions.setdefault(sid, {
                    "session_id": d.get("session_id"),
                    "visitor_id": d.get("visitor_id"),
                    "user_id": d.get("user_id"),
                    "lead_id": d.get("lead_id"),
                    "events": 0,
                    "first_at": _norm_dt(d.get("occurred_at")),
                })
                s["events"] += 1
                s["user_id"] = s["user_id"] or d.get("user_id")
                s["lead_id"] = s["lead_id"] or d.get("lead_id")
                s["last_event"] = d.get("event")
                s["last_path"] = d.get("path")
                s["last_asset_id"] = d.get("asset_id")
                s["stage"] = d.get("stage") or s.get("stage")
                s["last_at"] = _norm_dt(d.get("occurred_at"))
        except Exception as e:
            logger.warning(f"ACTIVITY live failed err={e}")

        # enrich user/lead names
        uids = [s["user_id"] for s in sessions.values() if s.get("user_id")]
        lids = [s["lead_id"] for s in sessions.values() if s.get("lead_id")]
        users = {u["user_id"]: u for u in await db.users.find(
            {"user_id": {"$in": uids}}, {"user_id": 1, "name": 1, "email": 1}).to_list(None)} if uids else {}
        leads = {l["lead_id"]: l for l in await db.leads.find(
            {"lead_id": {"$in": lids}}, {"lead_id": 1, "email": 1, "name": 1}).to_list(None)} if lids else {}

        rows = []
        for s in sessions.values():
            u = users.get(s.get("user_id")) or {}
            l = leads.get(s.get("lead_id")) or {}
            who = u.get("name") or u.get("email") or l.get("name") or l.get("email")
            rows.append({
                "session_id": s.get("session_id"),
                "visitor_id": s.get("visitor_id"),
                "user_id": s.get("user_id"),
                "lead_id": s.get("lead_id"),
                "identity": who or "Анонімний відвідувач",
                "is_anonymous": not (s.get("user_id") or s.get("lead_id")),
                "stage": s.get("stage"),
                "stage_label": STAGE_LABELS.get(s.get("stage") or "", {}),
                "last_event": s.get("last_event"),
                "last_event_label": EVENT_LABELS.get(s.get("last_event") or "", {}),
                "last_path": s.get("last_path"),
                "last_asset_id": s.get("last_asset_id"),
                "events": s["events"],
                "first_at": _iso(s.get("first_at")),
                "last_at": _iso(s.get("last_at")),
            })
        rows.sort(key=lambda r: r.get("last_at") or "", reverse=True)
        return {
            "online_count": len(rows),
            "anonymous_count": sum(1 for r in rows if r["is_anonymous"]),
            "identified_count": sum(1 for r in rows if not r["is_anonymous"]),
            "window_minutes": LIVE_WINDOW_MIN,
            "sessions": rows,
            "generated_at": _now().isoformat(),
        }

    # ---- F2.4 abandonment ----
    @router.get("/admin/activity/abandonment")
    async def abandonment(
        idle_days: int = Query(ABANDON_IDLE_DAYS, ge=0, le=365),
        _staff: dict = Depends(require_staff),
    ):
        # furthest stage + last activity per identified visitor
        per: Dict[str, dict] = {}
        try:
            async for d in db[EVENTS].find(
                {"$or": [{"user_id": {"$ne": None}}, {"lead_id": {"$ne": None}}]},
                {"user_id": 1, "lead_id": 1, "visitor_id": 1, "manager_id": 1,
                 "event": 1, "stage": 1, "occurred_at": 1},
            ):
                key = d.get("user_id") or d.get("lead_id")
                if not key:
                    continue
                stage = d.get("stage") or EVENT_STAGE.get(d.get("event") or "")
                idx = STAGE_INDEX.get(stage, 0)
                at = _norm_dt(d.get("occurred_at"))
                p = per.setdefault(key, {
                    "user_id": d.get("user_id"), "lead_id": d.get("lead_id"),
                    "visitor_id": d.get("visitor_id"), "manager_id": d.get("manager_id"),
                    "max_idx": -1, "last_at": None,
                })
                if idx > p["max_idx"]:
                    p["max_idx"] = idx
                    p["max_stage"] = stage
                if at and (p["last_at"] is None or at > p["last_at"]):
                    p["last_at"] = at
                p["manager_id"] = p["manager_id"] or d.get("manager_id")
        except Exception as e:
            logger.warning(f"ACTIVITY abandonment failed err={e}")

        now = _now()
        rows = []
        for p in per.values():
            stage = p.get("max_stage") or "visitor"
            # active investor = converted, not abandoned
            if STAGE_INDEX.get(stage, 0) >= STAGE_INDEX["certificate"]:
                continue
            last_at = p.get("last_at")
            if not last_at:
                continue
            days = (now - last_at).total_seconds() / 86400.0
            if days < idle_days:
                continue
            rows.append({
                "user_id": p.get("user_id"),
                "lead_id": p.get("lead_id"),
                "visitor_id": p.get("visitor_id"),
                "manager_id": p.get("manager_id"),
                "abandoned_stage": stage,
                "abandoned_stage_label": STAGE_LABELS.get(stage, {}),
                "days_idle": round(days, 1),
                "last_at": _iso(last_at),
            })

        # enrich identity names
        uids = [r["user_id"] for r in rows if r.get("user_id")]
        lids = [r["lead_id"] for r in rows if r.get("lead_id")]
        users = {u["user_id"]: u for u in await db.users.find(
            {"user_id": {"$in": uids}}, {"user_id": 1, "name": 1, "email": 1}).to_list(None)} if uids else {}
        leads = {l["lead_id"]: l for l in await db.leads.find(
            {"lead_id": {"$in": lids}}, {"lead_id": 1, "email": 1, "name": 1}).to_list(None)} if lids else {}
        for r in rows:
            u = users.get(r.get("user_id")) or {}
            l = leads.get(r.get("lead_id")) or {}
            r["identity"] = u.get("name") or u.get("email") or l.get("name") or l.get("email") or "—"
        rows.sort(key=lambda r: r["days_idle"], reverse=True)

        # bucket by stage
        by_stage: Dict[str, int] = {}
        for r in rows:
            by_stage[r["abandoned_stage"]] = by_stage.get(r["abandoned_stage"], 0) + 1
        return {
            "idle_days_threshold": idle_days,
            "abandoned_count": len(rows),
            "by_stage": by_stage,
            "rows": rows[:500],
            "generated_at": _now().isoformat(),
        }

    # ---- F2.6 attribution ----
    @router.get("/admin/activity/attribution")
    async def attribution(
        range: str = Query("30d"),
        _admin: dict = Depends(require_admin),
    ):
        since = _resolve_since(range)
        match: dict = {}
        if since:
            match["occurred_at"] = {"$gte": since}

        top_pages: Dict[str, dict] = {}
        leads_by_page: Dict[str, int] = {}
        asset_views: Dict[str, int] = {}
        cta_by_page: Dict[str, int] = {}
        # lead → its first landing path (attribution)
        lead_landing: Dict[str, str] = {}

        try:
            async for d in db[EVENTS].find(match, {
                "event": 1, "path": 1, "asset_id": 1, "visitor_id": 1,
                "lead_id": 1, "occurred_at": 1,
            }).sort("occurred_at", 1):
                ev = d.get("event")
                path = d.get("path")
                if ev == "page_view" and path:
                    tp = top_pages.setdefault(path, {"views": 0, "visitors": set()})
                    tp["views"] += 1
                    if d.get("visitor_id"):
                        tp["visitors"].add(d["visitor_id"])
                    # remember first landing path per visitor → lead attribution
                    if d.get("visitor_id") and d["visitor_id"] not in lead_landing:
                        lead_landing[d["visitor_id"]] = path
                elif ev == "cta_click" and path:
                    cta_by_page[path] = cta_by_page.get(path, 0) + 1
                elif ev == "asset_view" and d.get("asset_id"):
                    asset_views[d["asset_id"]] = asset_views.get(d["asset_id"], 0) + 1
                elif ev == "lead_created":
                    lp = lead_landing.get(d.get("visitor_id")) or path or "(direct)"
                    leads_by_page[lp] = leads_by_page.get(lp, 0) + 1
        except Exception as e:
            logger.warning(f"ACTIVITY attribution failed err={e}")

        pages_rows = sorted(
            [{"path": p, "views": v["views"], "unique_visitors": len(v["visitors"]),
              "leads": leads_by_page.get(p, 0), "ctas": cta_by_page.get(p, 0),
              "lead_conversion": round(leads_by_page.get(p, 0) / len(v["visitors"]), 4) if v["visitors"] else 0.0}
             for p, v in top_pages.items()],
            key=lambda r: r["views"], reverse=True,
        )[:50]

        # funding-by-asset (real facts from certificates/transfers)
        funding_by_asset = await _funding_by_asset(since)

        # asset views joined w/ titles
        asset_ids = list(asset_views.keys())
        asset_titles = {}
        if asset_ids:
            try:
                async for a in db.lumen_assets.find(
                    {"$or": [{"asset_id": {"$in": asset_ids}}, {"id": {"$in": asset_ids}}]},
                    {"asset_id": 1, "id": 1, "title": 1, "name": 1}):
                    aid = a.get("asset_id") or a.get("id")
                    asset_titles[aid] = a.get("title") or a.get("name")
            except Exception:
                pass
        assets_rows = sorted(
            [{"asset_id": k, "title": asset_titles.get(k), "views": v,
              "funding": funding_by_asset.get(k, {})}
             for k, v in asset_views.items()],
            key=lambda r: r["views"], reverse=True,
        )[:50]

        # manager conversion (from activity-linked managers)
        manager_rows = await _manager_conversion(since)

        return {
            "range": range,
            "top_pages": pages_rows,
            "leads_by_page": sorted(
                [{"path": p, "leads": n} for p, n in leads_by_page.items()],
                key=lambda r: r["leads"], reverse=True)[:50],
            "assets": assets_rows,
            "manager_conversion": manager_rows,
            "generated_at": _now().isoformat(),
        }

    # ---- F2.6 / top pages + overview ----
    @router.get("/admin/activity/overview")
    async def overview(range: str = Query("7d"), _staff: dict = Depends(require_staff)):
        since = _resolve_since(range)
        match = {"occurred_at": {"$gte": since}} if since else {}
        total = 0
        visitors = set()
        sessions = set()
        leads = 0
        by_event: Dict[str, int] = {}
        try:
            async for d in db[EVENTS].find(match, {
                "event": 1, "visitor_id": 1, "session_id": 1}):
                total += 1
                ev = d.get("event") or "unknown"
                by_event[ev] = by_event.get(ev, 0) + 1
                if d.get("visitor_id"):
                    visitors.add(d["visitor_id"])
                if d.get("session_id"):
                    sessions.add(d["session_id"])
                if ev == "lead_created":
                    leads += 1
        except Exception as e:
            logger.warning(f"ACTIVITY overview failed err={e}")
        # daily series from rollups
        series = []
        try:
            async for d in db[DAILY].find({}, {"_id": 0}).sort("date", -1).limit(30):
                series.append({
                    "date": d.get("date"),
                    "events": d.get("total_events", 0),
                    "visitors": d.get("unique_visitors", 0),
                    "leads": d.get("leads", 0),
                })
            series.reverse()
        except Exception:
            pass
        return {
            "range": range,
            "total_events": total,
            "unique_visitors": len(visitors),
            "unique_sessions": len(sessions),
            "leads": leads,
            "by_event": by_event,
            "daily": series,
            "generated_at": _now().isoformat(),
        }

    # ---- F2.3 timeline ----
    @router.get("/admin/activity/timeline")
    async def timeline(
        visitor_id: Optional[str] = Query(None),
        user_id: Optional[str] = Query(None),
        lead_id: Optional[str] = Query(None),
        limit: int = Query(200, ge=1, le=1000),
        _staff: dict = Depends(require_staff),
    ):
        if not (visitor_id or user_id or lead_id):
            raise HTTPException(status_code=400, detail="Provide visitor_id, user_id or lead_id")
        bundle = await _resolve_linked_ids(visitor_id=visitor_id, user_id=user_id, lead_id=lead_id)
        ors: List[dict] = []
        if bundle["visitor_ids"]:
            ors.append({"visitor_id": {"$in": bundle["visitor_ids"]}})
        if bundle["user_id"]:
            ors.append({"user_id": bundle["user_id"]})
        if bundle["lead_id"]:
            ors.append({"lead_id": bundle["lead_id"]})
        if visitor_id:
            ors.append({"visitor_id": visitor_id})
        if user_id:
            ors.append({"user_id": user_id})
        if lead_id:
            ors.append({"lead_id": lead_id})
        if not ors:
            return {"events": [], "count": 0, "identity": bundle}

        events: List[dict] = []
        try:
            async for d in db[EVENTS].find({"$or": ors}).sort("occurred_at", -1).limit(limit):
                d = _strip(d)
                events.append({
                    "event": d.get("event"),
                    "label": EVENT_LABELS.get(d.get("event") or "", {}),
                    "stage": d.get("stage"),
                    "path": d.get("path"),
                    "asset_id": d.get("asset_id"),
                    "surface": d.get("surface"),
                    "session_id": d.get("session_id"),
                    "visitor_id": d.get("visitor_id"),
                    "user_id": d.get("user_id"),
                    "lead_id": d.get("lead_id"),
                    "props": d.get("props"),
                    "at": _iso(d.get("occurred_at")),
                })
        except Exception as e:
            logger.warning(f"ACTIVITY timeline failed err={e}")
        return {
            "events": events,
            "count": len(events),
            "identity": {
                "visitor_ids": bundle["visitor_ids"],
                "user_id": bundle["user_id"],
                "lead_id": bundle["lead_id"],
                "first_visit_at": _iso(bundle["first_visit_at"]),
            },
            "generated_at": _now().isoformat(),
        }

    # ---- F2.6a manual rollup trigger ----
    @router.post("/admin/activity/rollup")
    async def trigger_rollup(_admin: dict = Depends(require_admin)):
        today = await _rollup_day(_now())
        yday = await _rollup_day(_now() - timedelta(days=1))
        return {"ok": True, "today": _strip(today), "yesterday": _strip(yday)}

    return router


# ---------------------------------------------------------------------------
# Attribution helpers
# ---------------------------------------------------------------------------
def _resolve_since(rng: str) -> Optional[datetime]:
    now = _now()
    rng = (rng or "all").lower()
    if rng == "24h":
        return now - timedelta(hours=24)
    if rng == "7d":
        return now - timedelta(days=7)
    if rng == "30d":
        return now - timedelta(days=30)
    if rng == "90d":
        return now - timedelta(days=90)
    return None


async def _funding_by_asset(since: Optional[datetime]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    try:
        pipe: List[dict] = [{"$match": {"status": "active"}}]
        pipe.append({"$group": {"_id": "$asset_id",
                                 "value_uah": {"$sum": "$value_uah"},
                                 "count": {"$sum": 1}}})
        async for r in db.lumen_certificates.aggregate(pipe):
            if r.get("_id"):
                out[r["_id"]] = {"certificate_value_uah": r.get("value_uah", 0),
                                 "certificates": r.get("count", 0)}
    except Exception:
        pass
    return out


async def _manager_conversion(since: Optional[datetime]) -> List[dict]:
    """Leads vs converted, attributed to managers via activity events."""
    match: dict = {"manager_id": {"$ne": None}}
    if since:
        match["occurred_at"] = {"$gte": since}
    per: Dict[str, dict] = {}
    try:
        async for d in db[EVENTS].find(match, {
            "manager_id": 1, "user_id": 1, "lead_id": 1, "stage": 1, "event": 1}):
            mid = d.get("manager_id")
            if not mid:
                continue
            key = d.get("user_id") or d.get("lead_id") or d.get("visitor_id")
            m = per.setdefault(mid, {"identities": {}, "events": 0})
            m["events"] += 1
            if key:
                cur = m["identities"].get(key, 0)
                idx = STAGE_INDEX.get(d.get("stage") or EVENT_STAGE.get(d.get("event") or ""), 0)
                if idx > cur:
                    m["identities"][key] = idx
    except Exception:
        pass
    mids = list(per.keys())
    names = {}
    if mids:
        try:
            async for u in db.users.find({"user_id": {"$in": mids}},
                                         {"user_id": 1, "name": 1, "email": 1}):
                names[u["user_id"]] = u
        except Exception:
            pass
    rows = []
    for mid, m in per.items():
        total = len(m["identities"])
        funded = sum(1 for v in m["identities"].values() if v >= STAGE_INDEX["funding_confirmed"])
        u = names.get(mid) or {}
        rows.append({
            "manager_id": mid,
            "manager_name": u.get("name") or u.get("email"),
            "touched_identities": total,
            "funded": funded,
            "conversion": round(funded / total, 4) if total else 0.0,
            "events": m["events"],
        })
    rows.sort(key=lambda r: r["funded"], reverse=True)
    return rows
