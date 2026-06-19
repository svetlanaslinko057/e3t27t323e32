"""
LUMEN — F5 Communication Provider Layer (abstraction, NOT telephony)
====================================================================

The structural layer the whole comms stack was waiting for. It is NOT a
phone/email integration — it is the abstraction that lets Ringostat / Binotel /
Twilio / SIP / Gmail / Outlook / Telegram / WhatsApp plug in later **without
touching IR, Manager OS, Timeline, Activity or Attribution.**

Design (locked in plan.md):
  • Registry collection      `lumen_communication_providers`
  • Thin adapter contract     CommAdapter (manual functional · others stubbed)
  • Single ingestion core     record_communication() → rides the EXISTING
                              `lumen_lead_communications` via mirror_communication()
                              with provider="ringostat" etc — NO schema change.

Every channel — manual today, Ringostat/Gmail/Twilio tomorrow — funnels through
ONE in/out interface:
    outbound:  POST /api/comms/send     → adapter.send()    → record_communication()
    inbound:   POST /api/comms/ingest   → resolve contact   → record_communication()

`sync_status` lifecycle on each row: logged · queued · sent · delivered ·
received · failed · not_connected.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, require_staff, _strip_mongo
from lumen_manager_os import mirror_communication, bump_activity, COMMUNICATIONS

logger = logging.getLogger("lumen.comm_providers")

router = APIRouter(prefix="/api", tags=["lumen-comm-providers"])

PROVIDERS = "lumen_communication_providers"
LEADS = "lumen_leads"

# provider_type buckets
T_MANUAL = "manual"
T_VOICE = "voice"
T_EMAIL = "email"
T_MESSAGING = "messaging"

# status
S_ACTIVE = "active"
S_NOT_CONNECTED = "not_connected"
S_DISABLED = "disabled"

# direction
D_IN = "inbound"
D_OUT = "outbound"
D_BOTH = "both"

INTERACTION_TYPES = {"call", "email", "telegram", "whatsapp", "sms", "meeting",
                     "document", "in_app", "note", "other"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Provider catalogue (seed) — manual active, the rest dormant by design
# ──────────────────────────────────────────────────────────────────────────
PROVIDER_CATALOGUE: List[dict] = [
    {"key": "manual", "name": "Ручне логування", "name_en": "Manual logging",
     "provider_type": T_MANUAL, "direction": D_BOTH, "status": S_ACTIVE,
     "capabilities": ["call", "email", "telegram", "whatsapp", "sms", "meeting", "document", "note"],
     "is_default": True, "future": False},
    {"key": "ringostat", "name": "Ringostat", "name_en": "Ringostat",
     "provider_type": T_VOICE, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["call", "call_recording", "missed_call"], "future": True},
    {"key": "binotel", "name": "Binotel", "name_en": "Binotel",
     "provider_type": T_VOICE, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["call", "call_recording"], "future": True},
    {"key": "twilio", "name": "Twilio", "name_en": "Twilio",
     "provider_type": T_MESSAGING, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["sms", "call", "whatsapp"], "future": True},
    {"key": "sip", "name": "SIP / АТС", "name_en": "SIP / PBX",
     "provider_type": T_VOICE, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["call"], "future": True},
    {"key": "gmail", "name": "Gmail", "name_en": "Gmail",
     "provider_type": T_EMAIL, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["email", "email_thread"], "future": True},
    {"key": "outlook", "name": "Outlook", "name_en": "Outlook",
     "provider_type": T_EMAIL, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["email", "email_thread"], "future": True},
    {"key": "telegram", "name": "Telegram", "name_en": "Telegram",
     "provider_type": T_MESSAGING, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["telegram"], "future": True},
    {"key": "whatsapp", "name": "WhatsApp", "name_en": "WhatsApp",
     "provider_type": T_MESSAGING, "direction": D_BOTH, "status": S_NOT_CONNECTED,
     "capabilities": ["whatsapp"], "future": True},
]
CATALOGUE_BY_KEY = {p["key"]: p for p in PROVIDER_CATALOGUE}


# ──────────────────────────────────────────────────────────────────────────
# Adapter contract (thin). Manual is functional; the rest are dormant stubs
# that a future F6/F7/F8 replaces with a real send()/normalize_inbound().
# ──────────────────────────────────────────────────────────────────────────
class CommAdapter:
    key: str = "base"
    provider_type: str = T_MANUAL
    connected: bool = False

    async def send(self, *, interaction_type: str, direction: str, **kw) -> dict:
        """Return {status, sync_status, external_ref}. Never raises."""
        raise NotImplementedError

    def normalize_inbound(self, payload: dict) -> dict:
        """Map a provider webhook payload to the canonical comm shape."""
        return payload


class ManualAdapter(CommAdapter):
    key = "manual"
    provider_type = T_MANUAL
    connected = True

    async def send(self, *, interaction_type: str, direction: str, **kw) -> dict:
        # "Manual" = the human already performed it; we just record the fact.
        return {"status": "ok", "sync_status": "logged",
                "external_ref": kw.get("external_ref")}


class StubAdapter(CommAdapter):
    """Dormant provider. Records intent with sync_status so it is visible in the
    feed, but does not transmit (no real integration yet — by design)."""
    def __init__(self, key: str, provider_type: str):
        self.key = key
        self.provider_type = provider_type
        self.connected = False

    async def send(self, *, interaction_type: str, direction: str, **kw) -> dict:
        return {"status": "not_connected", "sync_status": S_NOT_CONNECTED,
                "external_ref": kw.get("external_ref")}


_ADAPTERS: Dict[str, CommAdapter] = {"manual": ManualAdapter()}
for _p in PROVIDER_CATALOGUE:
    if _p["key"] != "manual":
        _ADAPTERS[_p["key"]] = StubAdapter(_p["key"], _p["provider_type"])


def get_adapter(key: str) -> CommAdapter:
    return _ADAPTERS.get(key, _ADAPTERS["manual"])


def register_adapter(adapter: CommAdapter) -> None:
    """Hook for F6/F7/F8 — drop in a real adapter for an existing provider key."""
    _ADAPTERS[adapter.key] = adapter


# ──────────────────────────────────────────────────────────────────────────
# Single ingestion core — every channel writes through here
# ──────────────────────────────────────────────────────────────────────────
async def record_communication(
    *,
    provider: str,
    interaction_type: str,
    direction: str,
    lead_id: Optional[str] = None,
    user_id: Optional[str] = None,
    title: str = "",
    detail: str = "",
    external_ref: Optional[str] = None,
    thread_ref: Optional[str] = None,
    contact: Optional[str] = None,
    sync_status: str = "logged",
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    at: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Provider-agnostic write. Rides `lumen_lead_communications` via the SAME
    mirror_communication() helper used by notes/tasks/meetings (no schema
    change) and stamps the F5 dimensions: provider / provider_type / sync_status
    / contact / thread_ref."""
    cat = CATALOGUE_BY_KEY.get(provider, CATALOGUE_BY_KEY["manual"])
    provider_type = cat["provider_type"]
    itype = (interaction_type or "other").lower().strip()
    if itype not in INTERACTION_TYPES:
        itype = "other"
    direction = (direction or D_OUT).lower()
    if direction not in (D_IN, D_OUT, "internal"):
        direction = D_OUT

    src_id = external_ref or f"f5_{uuid.uuid4().hex[:12]}"
    f5_extra = {
        "provider_type": provider_type,
        "sync_status": sync_status,
        "thread_ref": thread_ref,
        "contact": contact,
    }
    if extra:
        f5_extra.update(extra)

    row = await mirror_communication(
        lead_id=lead_id or "",
        user_id=user_id,
        kind=itype,
        interaction_type=itype,
        direction=direction,
        title=title or itype.capitalize(),
        detail=(detail or "")[:1000],
        at=at or _now(),
        actor_id=actor_id,
        actor_name=actor_name,
        source_collection=f"f5:{provider}",
        source_id=src_id,
        provider=provider,
        external_ref=external_ref,
        extra=f5_extra,
    )
    # keep manager activity counters coherent (same as M8 manual log)
    if actor_id:
        try:
            if itype == "call":
                await bump_activity(actor_id, "calls_count")
            await bump_activity(
                actor_id,
                "communications_inbound" if direction == D_IN else "communications_outbound",
            )
        except Exception:
            pass
    return row


# ──────────────────────────────────────────────────────────────────────────
# Contact resolution (email / phone → lead / user)
# ──────────────────────────────────────────────────────────────────────────
async def _resolve_contact(contact: Optional[str]) -> dict:
    out = {"lead_id": None, "user_id": None, "matched": False}
    if not contact:
        return out
    c = contact.strip().lower()
    is_email = "@" in c
    try:
        if is_email:
            lead = await db[LEADS].find_one({"email": c})
            user = await db.users.find_one({"email": c})
        else:
            digits = "".join(ch for ch in c if ch.isdigit())
            lead = await db[LEADS].find_one({"phone": {"$regex": digits[-9:]}}) if digits else None
            user = await db.users.find_one({"phone": {"$regex": digits[-9:]}}) if digits else None
        if lead:
            out["lead_id"] = lead.get("lead_id")
            out["user_id"] = out["user_id"] or lead.get("user_id")
            out["matched"] = True
        if user:
            out["user_id"] = user.get("user_id")
            out["matched"] = True
    except Exception as e:
        logger.warning("contact resolve failed: %s", e)
    return out


# ===========================================================================
# Registry endpoints
# ===========================================================================
@router.get("/admin/comms/providers")
async def list_providers(_staff=Depends(require_staff)):
    rows = []
    async for p in db[PROVIDERS].find({}).sort("provider_type", 1):
        p = _strip_mongo(p)
        p["connected"] = get_adapter(p["key"]).connected
        rows.append(p)
    # group summary
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r.get("status")] = by_status.get(r.get("status"), 0) + 1
    return {"providers": rows, "by_status": by_status, "generated_at": _now()}


class ProviderUpsert(BaseModel):
    key: str
    name: Optional[str] = None
    provider_type: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    capabilities: Optional[List[str]] = None
    config: Optional[dict] = None


@router.post("/admin/comms/providers")
async def upsert_provider(body: ProviderUpsert, admin=Depends(require_admin)):
    key = body.key.strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    existing = await db[PROVIDERS].find_one({"key": key})
    cat = CATALOGUE_BY_KEY.get(key, {})
    doc = {
        "key": key,
        "name": body.name or (existing or {}).get("name") or cat.get("name") or key,
        "provider_type": body.provider_type or (existing or {}).get("provider_type") or cat.get("provider_type") or T_MANUAL,
        "direction": body.direction or (existing or {}).get("direction") or cat.get("direction") or D_BOTH,
        "status": body.status or (existing or {}).get("status") or cat.get("status") or S_NOT_CONNECTED,
        "capabilities": body.capabilities or (existing or {}).get("capabilities") or cat.get("capabilities") or [],
        "config": {**((existing or {}).get("config") or {}), **(body.config or {})},
        "updated_at": _now(),
        "updated_by": admin.get("user_id"),
    }
    if not existing:
        doc["provider_id"] = f"cp_{uuid.uuid4().hex[:10]}"
        doc["created_at"] = _now()
        await db[PROVIDERS].insert_one(doc)
    else:
        await db[PROVIDERS].update_one({"key": key}, {"$set": doc})
    return _strip_mongo(await db[PROVIDERS].find_one({"key": key}))


class ProviderPatch(BaseModel):
    status: Optional[str] = None
    direction: Optional[str] = None
    config: Optional[dict] = None
    name: Optional[str] = None


@router.patch("/admin/comms/providers/{key}")
async def patch_provider(key: str, body: ProviderPatch, admin=Depends(require_admin)):
    existing = await db[PROVIDERS].find_one({"key": key})
    if not existing:
        raise HTTPException(status_code=404, detail="Провайдера не знайдено")
    patch: Dict[str, Any] = {"updated_at": _now(), "updated_by": admin.get("user_id")}
    if body.status is not None:
        if body.status not in (S_ACTIVE, S_NOT_CONNECTED, S_DISABLED):
            raise HTTPException(status_code=400, detail="invalid status")
        # F6 contract (R9): OAuth-backed providers — when the provider doc
        # carries ``config.oauth_status``, that field is the canonical
        # truth (set by the OAuth callback). Otherwise fall back to the
        # in-process adapter.connected flag (manual=ok, stubs=409).
        cfg = (existing.get("config") or {})
        oauth_field = cfg.get("oauth_status")
        if body.status == S_ACTIVE:
            if oauth_field is not None:
                if oauth_field != "connected":
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "OAuth не завершено. Підключіть провайдера "
                            "через /api/comms/oauth/{key}/start перш ніж активувати."
                        ),
                    )
            elif not get_adapter(key).connected:
                raise HTTPException(
                    status_code=409,
                    detail="Провайдер не під'єднано (адаптер відсутній). Інтеграція з'явиться у F6–F8.",
                )
        patch["status"] = body.status
    if body.direction is not None:
        patch["direction"] = body.direction
    if body.name is not None:
        patch["name"] = body.name
    if body.config is not None:
        patch["config"] = {**(existing.get("config") or {}), **body.config}
    await db[PROVIDERS].update_one({"key": key}, {"$set": patch})
    return _strip_mongo(await db[PROVIDERS].find_one({"key": key}))


@router.post("/admin/comms/providers/{key}/test")
async def test_provider(key: str, _admin=Depends(require_admin)):
    existing = await db[PROVIDERS].find_one({"key": key})
    if not existing:
        raise HTTPException(status_code=404, detail="Провайдера не знайдено")
    adapter = get_adapter(key)
    ok = adapter.connected
    await db[PROVIDERS].update_one({"key": key}, {"$set": {"last_test_at": _now()}})
    return {
        "key": key,
        "connected": ok,
        "result": "ok" if ok else "not_connected",
        "message": ("Адаптер активний (ручне логування)" if ok
                    else "Адаптер ще не під'єднано — інтеграція у F6–F8"),
        "tested_at": _now(),
    }


# ===========================================================================
# Unified feed + stats
# ===========================================================================
@router.get("/admin/comms/feed")
async def feed(
    provider: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    interaction_type: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    thread_ref: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _staff=Depends(require_staff),
):
    query: Dict[str, Any] = {}
    if provider:
        query["provider"] = provider
    if direction:
        query["direction"] = direction
    if interaction_type:
        query["interaction_type"] = interaction_type
    if lead_id:
        query["lead_id"] = lead_id
    if thread_ref:
        query["extra.thread_ref"] = thread_ref
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"detail": {"$regex": q, "$options": "i"}},
        ]
    rows = []
    async for r in db[COMMUNICATIONS].find(query).sort("at", -1).limit(limit):
        r = _strip_mongo(r)
        extra = r.get("extra") or {}
        rows.append({
            "comm_id": r.get("comm_id"),
            "lead_id": r.get("lead_id"),
            "user_id": r.get("user_id"),
            "provider": r.get("provider") or "manual",
            "provider_type": extra.get("provider_type"),
            "interaction_type": r.get("interaction_type"),
            "direction": r.get("direction"),
            "title": r.get("title"),
            "detail": r.get("detail"),
            "contact": extra.get("contact"),
            "external_ref": r.get("external_ref"),
            "thread_ref": extra.get("thread_ref"),
            "sync_status": extra.get("sync_status") or "logged",
            "actor_name": r.get("actor_name"),
            "at": r.get("at"),
        })
    return {"items": rows, "count": len(rows), "generated_at": _now()}


@router.get("/admin/comms/stats")
async def stats(_staff=Depends(require_staff)):
    by_provider: Dict[str, int] = {}
    by_direction: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total = 0
    async for r in db[COMMUNICATIONS].find({}, {"provider": 1, "direction": 1, "interaction_type": 1}):
        total += 1
        p = r.get("provider") or "manual"
        by_provider[p] = by_provider.get(p, 0) + 1
        d = r.get("direction") or "outbound"
        by_direction[d] = by_direction.get(d, 0) + 1
        t = r.get("interaction_type") or "other"
        by_type[t] = by_type.get(t, 0) + 1
    return {"total": total, "by_provider": by_provider,
            "by_direction": by_direction, "by_type": by_type, "generated_at": _now()}


# ===========================================================================
# Thread read primitive — what the F6 Gmail UI will key off
# ===========================================================================
@router.get("/admin/comms/threads/{thread_ref}")
async def thread_view(thread_ref: str, _staff=Depends(require_staff)):
    """All comm rows belonging to one provider thread, oldest → newest.

    This is the read-side primitive a Gmail/Outlook thread view will use.
    F6/F7 webhooks already write ``extra.thread_ref`` through
    ``record_communication()``; this endpoint just groups them.
    """
    rows: List[dict] = []
    async for r in db[COMMUNICATIONS].find(
        {"extra.thread_ref": thread_ref}
    ).sort("at", 1):
        r = _strip_mongo(r)
        extra = r.get("extra") or {}
        rows.append({
            "comm_id": r.get("comm_id"),
            "lead_id": r.get("lead_id"),
            "provider": r.get("provider"),
            "interaction_type": r.get("interaction_type"),
            "direction": r.get("direction"),
            "title": r.get("title"),
            "detail": r.get("detail"),
            "contact": extra.get("contact"),
            "external_ref": r.get("external_ref"),
            "thread_ref": extra.get("thread_ref"),
            "sync_status": extra.get("sync_status") or "logged",
            "actor_name": r.get("actor_name"),
            "at": r.get("at"),
        })
    providers = sorted({r["provider"] for r in rows if r.get("provider")})
    lead_ids = sorted({r["lead_id"] for r in rows if r.get("lead_id")})
    return {
        "thread_ref": thread_ref,
        "messages": rows,
        "count": len(rows),
        "providers": providers,
        "lead_ids": lead_ids,
        "generated_at": _now(),
    }


# ===========================================================================
# Outbound + inbound abstraction
# ===========================================================================
class SendIn(BaseModel):
    provider: str = "manual"
    interaction_type: str = "note"
    direction: str = "outbound"
    lead_id: Optional[str] = None
    user_id: Optional[str] = None
    contact: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    external_ref: Optional[str] = None


@router.post("/comms/send")
async def send(body: SendIn, staff=Depends(require_staff)):
    """Provider-agnostic OUTBOUND. Routes to the adapter, then records the
    communication through the single ingestion core. Manual = logs; dormant
    providers return not_connected but still leave an auditable row."""
    provider = (body.provider or "manual").lower()
    cat = CATALOGUE_BY_KEY.get(provider)
    if not cat:
        raise HTTPException(status_code=404, detail="Невідомий провайдер")
    prov_doc = await db[PROVIDERS].find_one({"key": provider})
    if prov_doc and prov_doc.get("status") == S_DISABLED:
        raise HTTPException(status_code=409, detail="Провайдер вимкнено")

    # resolve contact if no explicit lead/user
    lead_id, user_id = body.lead_id, body.user_id
    if not lead_id and not user_id and body.contact:
        r = await _resolve_contact(body.contact)
        lead_id, user_id = r["lead_id"], r["user_id"]

    adapter = get_adapter(provider)
    res = await adapter.send(
        interaction_type=body.interaction_type, direction=body.direction,
        external_ref=body.external_ref, contact=body.contact, body=body.body,
    )
    row = await record_communication(
        provider=provider,
        interaction_type=body.interaction_type,
        direction=body.direction or D_OUT,
        lead_id=lead_id, user_id=user_id,
        title=body.subject or "",
        detail=body.body or "",
        external_ref=res.get("external_ref") or body.external_ref,
        contact=body.contact,
        sync_status=res.get("sync_status", "logged"),
        actor_id=staff.get("user_id"),
        actor_name=staff.get("name") or staff.get("email"),
    )
    return {"ok": res.get("status") != "not_connected", "result": res.get("status"),
            "sync_status": res.get("sync_status"), "comm": row}


class IngestIn(BaseModel):
    provider: str
    interaction_type: str = "other"
    direction: str = "inbound"
    contact: Optional[str] = None
    lead_id: Optional[str] = None
    user_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    external_ref: Optional[str] = None
    thread_ref: Optional[str] = None
    at: Optional[str] = None


@router.post("/comms/ingest")
async def ingest(body: IngestIn, staff=Depends(require_staff)):
    """Provider-agnostic INBOUND. The shape future Ringostat/Gmail/Twilio
    webhooks will normalise into. Resolves the contact, then records through
    the single ingestion core."""
    provider = (body.provider or "manual").lower()
    if provider not in CATALOGUE_BY_KEY:
        raise HTTPException(status_code=404, detail="Невідомий провайдер")
    lead_id, user_id, matched = body.lead_id, body.user_id, bool(body.lead_id or body.user_id)
    if not lead_id and not user_id and body.contact:
        r = await _resolve_contact(body.contact)
        lead_id, user_id, matched = r["lead_id"], r["user_id"], r["matched"]
    row = await record_communication(
        provider=provider,
        interaction_type=body.interaction_type,
        direction=body.direction or D_IN,
        lead_id=lead_id, user_id=user_id,
        title=body.title or "",
        detail=body.body or "",
        external_ref=body.external_ref,
        thread_ref=body.thread_ref,
        contact=body.contact,
        sync_status="received",
        actor_id=staff.get("user_id"),
        actor_name=staff.get("name") or staff.get("email"),
        at=body.at,
    )
    return {"ok": True, "matched_contact": matched, "lead_id": lead_id,
            "user_id": user_id, "comm": row}


# ===========================================================================
# boot — seed catalogue + indexes
# ===========================================================================
async def seed_providers():
    for cat in PROVIDER_CATALOGUE:
        existing = await db[PROVIDERS].find_one({"key": cat["key"]})
        if existing:
            continue
        doc = {
            "provider_id": f"cp_{uuid.uuid4().hex[:10]}",
            "key": cat["key"],
            "name": cat["name"],
            "name_en": cat.get("name_en"),
            "provider_type": cat["provider_type"],
            "direction": cat["direction"],
            "status": cat["status"],
            "capabilities": cat["capabilities"],
            "is_default": cat.get("is_default", False),
            "future": cat.get("future", False),
            "config": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[PROVIDERS].insert_one(doc)
    logger.info("F5 provider catalogue seeded (%d providers)", len(PROVIDER_CATALOGUE))


async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[PROVIDERS].create_index("key", unique=True)
        await d[COMMUNICATIONS].create_index("provider")
        await d[COMMUNICATIONS].create_index([("provider", 1), ("at", -1)])
        await d[COMMUNICATIONS].create_index("direction")
        await d[COMMUNICATIONS].create_index(
            "extra.thread_ref", sparse=True,
            name="f5_thread_ref_sparse")
        logger.info("F5 comm-provider indexes ensured")
    except Exception as e:
        logger.warning("F5 ensure_indexes warn: %s", e)
    await seed_providers()
