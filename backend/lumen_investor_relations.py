"""
LUMEN — Investor Relations OS (IR Center).

Phase IR1 — first slice: IR1.1 Lead Management + IR1.2 Pipeline + IR1.7 Ownership.

This is NOT a generic CRM. It is the investor-accompaniment layer for LUMEN.
Locked product decisions (user, 2026-06-15):

  • 1c — leads live in their OWN collection ``lumen_leads`` (the legacy generic
         ``leads`` collection is NOT touched). On conversion a lead is linked to
         a real user / investor profile (``user_id`` + ``investor_profile_id``).
  • 2a — HYBRID pipeline: early stages are set MANUALLY by a manager
         (lead → qualified → meeting); late stages are AUTO-DERIVED from real
         platform facts (KYC, accreditation, funding transfers, certificates) —
         never hand-set, so "funded" can only appear when real funding exists.
  • 3c — ownership today is admin/staff, but the model already carries
         ``owner_id`` + ``owner_type = "manager"`` so scoped manager access can
         be switched on later WITHOUT a migration.
  • 4a — admin-only during Controlled Beta. Routes live under ``/api/admin/ir/*``
         and are therefore classified ``staff`` by the IR0.1 Default-Deny gate.

Field-level changes (owner / stage / conversion) are written to the IR0.3
``lumen_field_changes`` history under entity_type ``lead``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, EmailStr, Field

from lumen_api import db, require_admin, require_staff, _strip_mongo, _now

router = APIRouter(prefix="/api/admin/ir", tags=["lumen-investor-relations"])

LEADS = "lumen_leads"
NOTES = "lumen_lead_notes"
TASKS = "lumen_lead_tasks"
MEETINGS = "lumen_lead_meetings"

# ──────────────────────────────────────────────────────────────────────────
# Pipeline model
# ──────────────────────────────────────────────────────────────────────────
EARLY_STAGES = ["lead", "qualified", "meeting"]
LATE_STAGES = ["kyc", "accredited", "funding_pending", "funded", "active"]
ALL_STAGES = EARLY_STAGES + LATE_STAGES
STAGE_RANK = {s: i for i, s in enumerate(ALL_STAGES)}

STAGE_META = {
    "lead":            {"label": "Lead",            "kind": "manual", "color": "#8A8A8A"},
    "qualified":       {"label": "Qualified",       "kind": "manual", "color": "#5B7C99"},
    "meeting":         {"label": "Meeting",         "kind": "manual", "color": "#6B5B95"},
    "kyc":             {"label": "KYC",             "kind": "derived", "color": "#B7791F"},
    "accredited":      {"label": "Accredited",      "kind": "derived", "color": "#2C7A7B"},
    "funding_pending": {"label": "Funding Pending", "kind": "derived", "color": "#C05621"},
    "funded":          {"label": "Funded",          "kind": "derived", "color": "#2F855A"},
    "active":          {"label": "Active Investor", "kind": "derived", "color": "#2E5D4F"},
}

FUNDING_CONFIRMED = "confirmed"
FUNDING_PENDING = {"submitted", "pending_review", "matched"}


def _utc(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _parse_dt(value) -> Optional[datetime]:
    """Best-effort parse of an ISO string / datetime into an aware datetime."""
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


def _days_since(value) -> Optional[float]:
    d = _parse_dt(value)
    if not d:
        return None
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400.0


async def _touch(lead_id: str):
    """Bump last_interaction_at — called from any real interaction event."""
    try:
        await db[LEADS].update_one(
            {"lead_id": lead_id},
            {"$set": {"last_interaction_at": _utc(), "updated_at": _utc()}},
        )
    except Exception:
        pass


# ── IR2 Layer A · safe hooks (no-op if module unavailable) ────────────────
async def _mgros_mirror(**kwargs):
    try:
        from lumen_manager_os import mirror_communication
        await mirror_communication(**kwargs)
    except Exception:
        pass


async def _mgros_bump(user_id, field, inc=1):
    try:
        from lumen_manager_os import bump_activity
        await bump_activity(user_id, field, inc=inc)
    except Exception:
        pass


async def _mgros_record_assignment(**kwargs):
    try:
        from lumen_manager_os import record_assignment
        await record_assignment(**kwargs)
    except Exception:
        pass


# ── M1 · Staff ACL / Ownership Scope (safe wrappers) ──────────────────────
async def _scope_filter(user: dict) -> dict:
    """Mongo filter limiting leads to what this staff user may see."""
    try:
        from lumen_staff_acl import lead_scope_filter
        return await lead_scope_filter(user)
    except Exception:
        return {}


async def _assert_lead_visible(user: dict, lead: dict) -> None:
    try:
        from lumen_staff_acl import assert_can_see_lead
        await assert_can_see_lead(user, lead)
    except HTTPException:
        raise
    except Exception:
        pass


# ── M3 · SLA hooks (safe) ─────────────────────────────────────────────────
async def _sla_init(created_at: str, owner_id: Optional[str] = None) -> dict:
    try:
        from lumen_sla import init_lead_sla
        return await init_lead_sla(created_at, owner_id)
    except Exception:
        return {}


async def _sla_touch(lead_id: str, actor: Optional[dict] = None) -> None:
    try:
        from lumen_sla import mark_first_response
        await mark_first_response(lead_id, actor)
    except Exception:
        pass


def _sla_live(lead: dict) -> Optional[dict]:
    try:
        from lumen_sla import live_state
        return live_state(lead)
    except Exception:
        return None


# ── M4 · Staff notifications (safe) ───────────────────────────────────────
async def _notify_new_owner(lead: dict, to_user_id: str, actor_name: str = "") -> None:
    try:
        from lumen_staff_notifications import notify_new_lead_assigned
        await notify_new_lead_assigned(lead, to_user_id, actor_name=actor_name)
    except Exception:
        pass


# ── Lead priority engine (deterministic A/B/C/D — "who to call first") ────
def _compute_priority(lead: dict) -> dict:
    """Explainable priority on top of health + SLA + stage signals.

    Buckets: A (>=80) hot · B (60-79) active · C (40-59) watch · D (<40) cold.
    """
    score = 40
    reasons: List[str] = []
    health = (lead.get("health") or {}).get("color")
    if health == "red":
        score += 30
        reasons.append("червоний health")
    elif health == "yellow":
        score += 12
        reasons.append("жовтий health")

    sla = lead.get("sla") or {}
    if sla.get("overdue") or sla.get("status") == "breached":
        score += 25
        reasons.append("прострочено SLA")
    elif sla.get("at_risk"):
        score += 15
        reasons.append("SLA під ризиком")

    stage = lead.get("effective_stage")
    if stage in ("qualified", "meeting"):
        score += 12
        reasons.append("активна стадія")
    elif stage == "funding_pending":
        score += 18
        reasons.append("очікує funding")

    h = lead.get("health") or {}
    if h.get("open_tasks"):
        score += 6
        reasons.append("є відкриті задачі")
    if not lead.get("owner_id"):
        score += 8
        reasons.append("без власника")

    score = max(0, min(100, score))
    if score >= 80:
        bucket, label = "A", "Гарячий"
    elif score >= 60:
        bucket, label = "B", "Активний"
    elif score >= 40:
        bucket, label = "C", "Спостереження"
    else:
        bucket, label = "D", "Холодний"
    return {"score": score, "bucket": bucket, "label": label, "reasons": reasons[:4]}


async def _lead_owner_id(lead_id: str) -> Optional[str]:
    try:
        l = await db[LEADS].find_one({"lead_id": lead_id}, {"owner_id": 1})
        return (l or {}).get("owner_id")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# Field-history helper (IR0.3)
# ──────────────────────────────────────────────────────────────────────────
async def _record(entity_id: str, field: str, old, new, actor: dict, reason: str = ""):
    try:
        from lumen_field_changes import record_change
        await record_change(
            db, entity_type="lead", entity_id=entity_id,
            field=field, old_value=old, new_value=new,
            actor=actor, source="api", reason=(reason or None),
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────
# Auto-derive late pipeline stage from REAL platform facts
# ──────────────────────────────────────────────────────────────────────────
async def _derive_facts(user_id: Optional[str]) -> dict:
    """Return per-domain badges + the highest LATE stage reached, from real data.

    Everything is read from canonical collections — nothing synthetic. When the
    lead is not yet linked to a user, every fact is ``none`` and no late stage
    is reached.
    """
    facts = {
        "kyc": "none",
        "accreditation": "none",
        "funding": "none",
        "certificate": "none",
        "derived_stage": None,
    }
    if not user_id:
        return facts

    # KYC + accreditation come from the investor profile (fallback to users).
    profile = await db.lumen_investor_profiles.find_one({"user_id": user_id}) or {}
    user = await db.users.find_one({"user_id": user_id}) or await db.users.find_one({"id": user_id}) or {}

    kyc_status = (profile.get("kyc_status") or user.get("kyc_status") or "none")
    facts["kyc"] = kyc_status
    acc = (profile.get("accreditation") or {})
    acc_status = acc.get("review_status") or acc.get("status") or "none"
    facts["accreditation"] = acc_status

    # Funding — canonical institutional transfers.
    funding_state = "none"
    confirmed = await db.lumen_institutional_transfers.count_documents(
        {"investor_id": user_id, "canonical_status": FUNDING_CONFIRMED})
    if confirmed:
        funding_state = "confirmed"
    else:
        pending = await db.lumen_institutional_transfers.count_documents(
            {"investor_id": user_id, "canonical_status": {"$in": list(FUNDING_PENDING)}})
        if pending:
            funding_state = "pending"
    facts["funding"] = funding_state

    # Certificate — an active certificate means a live investment.
    active_cert = await db.lumen_certificates.count_documents(
        {"investor_id": user_id, "status": "active"})
    facts["certificate"] = "active" if active_cert else "none"

    # Highest late stage reached (max-reached wins).
    reached: Optional[str] = None
    if str(kyc_status).lower() in {"approved", "verified", "passed", "completed"}:
        reached = "kyc"
    if str(acc_status).lower() in {"approved", "accredited", "verified"}:
        reached = "accredited"
    if funding_state == "pending":
        reached = "funding_pending"
    if funding_state == "confirmed":
        reached = "funded"
    if facts["certificate"] == "active":
        reached = "active"
    facts["derived_stage"] = reached
    return facts


async def _effective(lead: dict) -> dict:
    """Compute effective stage = max(manual stage, derived late stage)."""
    manual = lead.get("manual_stage") or "lead"
    facts = await _derive_facts(lead.get("user_id"))
    derived = facts.get("derived_stage")
    manual_rank = STAGE_RANK.get(manual, 0)
    derived_rank = STAGE_RANK.get(derived, -1) if derived else -1
    if derived_rank >= manual_rank:
        effective = derived or manual
    else:
        effective = manual
    return {"effective_stage": effective, "facts": facts}


async def _last_interaction(lead: dict, facts_funding_ts=None, facts_cert_ts=None) -> Optional[str]:
    """Effective last interaction = max(stored, latest funding, latest cert, created)."""
    candidates = [
        _parse_dt(lead.get("last_interaction_at")),
        _parse_dt(lead.get("created_at")),
        _parse_dt(facts_funding_ts),
        _parse_dt(facts_cert_ts),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return None
    return max(candidates).isoformat()


async def _compute_health(lead: dict, facts: dict) -> dict:
    """Fact-based Green / Yellow / Red (IR1.8). No AI, no scoring magic.

    Locked rules (user, 2026-06-15):
      RED    = KYC not completed OR last interaction > 60d OR overdue task
      YELLOW = KYC pending OR funding pending OR open task OR interaction 30–60d
      GREEN  = KYC approved AND active certificate AND interaction < 30d AND no open issues
    Green is EARNED, never the default.
    """
    lead_id = lead.get("lead_id")
    kyc = str(facts.get("kyc", "none")).lower()
    kyc_completed = kyc in {"approved", "verified", "passed", "completed"}
    kyc_pending = kyc in {"pending", "under_review", "in_review", "submitted", "in_progress"}
    kyc_missing = not kyc_completed and not kyc_pending  # none / rejected / failed
    funding_pending = facts.get("funding") == "pending"
    cert_active = facts.get("certificate") == "active"

    open_tasks = 0
    overdue = False
    try:
        open_tasks = await db[TASKS].count_documents({"lead_id": lead_id, "status": "open"})
        if open_tasks:
            now = datetime.now(timezone.utc)
            async for t in db[TASKS].find({"lead_id": lead_id, "status": "open", "due_date": {"$ne": None}}):
                dd = _parse_dt(t.get("due_date"))
                if dd and dd < now:
                    overdue = True
                    break
    except Exception:
        pass

    # latest funding / certificate timestamps for last-interaction enrichment
    fund_ts = cert_ts = None
    uid = lead.get("user_id")
    if uid:
        try:
            ft = await db.lumen_institutional_transfers.find_one(
                {"investor_id": uid}, sort=[("updated_at", -1)])
            fund_ts = (ft or {}).get("updated_at") or (ft or {}).get("created_at")
            ct = await db.lumen_certificates.find_one(
                {"investor_id": uid}, sort=[("created_at", -1)])
            cert_ts = (ct or {}).get("issued_at") or (ct or {}).get("created_at")
        except Exception:
            pass
    last_iso = await _last_interaction(lead, fund_ts, cert_ts)
    last_days = _days_since(last_iso)

    red, yellow = [], []
    if kyc_missing:
        red.append("KYC не завершено")
    if last_days is not None and last_days > 60:
        red.append("Немає взаємодії > 60 днів")
    if overdue:
        red.append("Є прострочена задача")

    if kyc_pending:
        yellow.append("KYC в процесі")
    if funding_pending:
        yellow.append("Funding очікує")
    if open_tasks > 0:
        yellow.append("Є відкриті задачі")
    if last_days is not None and 30 <= last_days <= 60:
        yellow.append("Взаємодія 30–60 днів тому")

    green = (kyc_completed and cert_active and last_days is not None
             and last_days < 30 and open_tasks == 0 and not funding_pending)

    if red:
        color, reasons = "red", red
    elif green:
        color, reasons = "green", ["KYC ок · активний сертифікат · свіжа взаємодія"]
    else:
        color, reasons = "yellow", (yellow or ["Неповний green-стан"])

    return {
        "color": color,
        "reasons": reasons,
        "open_tasks": open_tasks,
        "overdue_task": overdue,
        "last_interaction_at": last_iso,
        "last_interaction_days": round(last_days, 1) if last_days is not None else None,
    }


async def _enrich(lead: dict, with_health: bool = True) -> dict:
    lead = _strip_mongo(dict(lead))
    eff = await _effective(lead)
    lead["effective_stage"] = eff["effective_stage"]
    lead["effective_stage_label"] = STAGE_META.get(eff["effective_stage"], {}).get("label", eff["effective_stage"])
    lead["facts"] = eff["facts"]
    if with_health:
        lead["health"] = await _compute_health(lead, eff["facts"])
    # M3 · SLA live state + M-priority (deterministic, depends on health/sla)
    lead["sla"] = _sla_live(lead)
    lead["priority"] = _compute_priority(lead)
    return lead


# ──────────────────────────────────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────────────────────────────────
class LeadCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = "manual"
    interest: Optional[str] = None
    budget_range: Optional[str] = None
    note: Optional[str] = None


class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    interest: Optional[str] = None
    budget_range: Optional[str] = None


class StageChange(BaseModel):
    stage: str
    note: Optional[str] = None


class OwnerAssign(BaseModel):
    owner_id: Optional[str] = None  # None → unassign
    reason: Optional[str] = None


class ReassignOne(BaseModel):
    to_owner_id: Optional[str] = None  # None → unassign
    reason: Optional[str] = None


class ReassignBulk(BaseModel):
    lead_ids: List[str]
    to_owner_id: Optional[str] = None
    reason: Optional[str] = None


class LeadConvert(BaseModel):
    user_id: str


class NoteCreate(BaseModel):
    body: str


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = "normal"   # low | normal | high
    task_type: Optional[str] = None      # free field (call/email/follow_up/document…)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    task_type: Optional[str] = None
    status: Optional[str] = None          # open | done


class MeetingCreate(BaseModel):
    title: str
    scheduled_at: str
    type: Optional[str] = "call"          # call | video | in_person
    duration_min: Optional[int] = 30
    outcome_note: Optional[str] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    scheduled_at: Optional[str] = None
    type: Optional[str] = None
    duration_min: Optional[int] = None
    outcome_note: Optional[str] = None
    status: Optional[str] = None          # scheduled | completed | cancelled


# ──────────────────────────────────────────────────────────────────────────
# Owner (manager) candidates — admin + manager users
# ──────────────────────────────────────────────────────────────────────────
@router.get("/managers")
async def list_managers(admin=Depends(require_staff)):
    """Staff users eligible to own leads (Admin/Manager). 2-level model only."""
    cur = db.users.find({
        "$or": [
            {"role": {"$in": ["admin", "manager"]}},
            {"roles": {"$in": ["admin", "manager"]}},
        ]
    })
    out = []
    async for u in cur:
        u = _strip_mongo(u)
        out.append({
            "user_id": u.get("user_id") or u.get("id"),
            "name": u.get("name") or u.get("full_name") or u.get("email"),
            "email": u.get("email"),
            "role": u.get("role") or (u.get("roles") or ["—"])[0],
        })
    return {"managers": out}


# ──────────────────────────────────────────────────────────────────────────
# Leads CRUD
# ──────────────────────────────────────────────────────────────────────────
@router.post("/leads")
async def create_lead(payload: LeadCreate, admin=Depends(require_staff)):
    email = payload.email.lower().strip()
    existing = await db[LEADS].find_one({"email": email})
    if existing:
        raise HTTPException(409, detail="Лід з таким email вже існує")
    # Try to link to an existing user immediately (soft link, not conversion).
    linked = await db.users.find_one({"email": email})
    user_id = (linked or {}).get("user_id") or (linked or {}).get("id")
    profile_id = None
    if user_id:
        prof = await db.lumen_investor_profiles.find_one({"user_id": user_id})
        profile_id = (prof or {}).get("id") or (prof or {}).get("profile_id")

    lead_id = f"lead_{uuid.uuid4().hex[:12]}"
    now = _utc()
    doc = {
        "lead_id": lead_id,
        "email": email,
        "full_name": payload.full_name,
        "phone": payload.phone,
        "source": payload.source or "manual",
        "interest": payload.interest,
        "budget_range": payload.budget_range,
        "note": payload.note,
        "manual_stage": "lead",
        "status": "open",
        "user_id": user_id,
        "investor_profile_id": profile_id,
        "owner_id": None,
        "owner_type": None,
        "owner_name": None,
        "owner_email": None,
        "created_at": now,
        "updated_at": now,
        "converted_at": _utc() if user_id else None,
    }
    # M3 · seed SLA fields (first-response clock starts now)
    doc.update(await _sla_init(now, None))
    await db[LEADS].insert_one(doc)
    await _record(lead_id, "stage", None, "lead",
                  actor=admin, reason="lead created")
    return await _enrich(doc)


@router.get("/leads")
async def list_leads(
    admin=Depends(require_staff),
    stage: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
):
    query: dict = await _scope_filter(admin)
    if owner_id:
        query["owner_id"] = owner_id
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"full_name": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    cur = db[LEADS].find(query).sort("created_at", -1).limit(limit)
    leads = [await _enrich(d) async for d in cur]
    if stage:
        leads = [l for l in leads if l["effective_stage"] == stage]
    return {"leads": leads, "total": len(leads)}


@router.get("/pipeline")
async def pipeline(admin=Depends(require_staff)):
    """Kanban board: every stage column with its leads + counts."""
    cur = db[LEADS].find(await _scope_filter(admin)).sort("created_at", -1)
    enriched = [await _enrich(d) async for d in cur]
    columns = []
    for s in ALL_STAGES:
        items = [l for l in enriched if l["effective_stage"] == s]
        meta = STAGE_META[s]
        columns.append({
            "stage": s,
            "label": meta["label"],
            "kind": meta["kind"],
            "color": meta["color"],
            "count": len(items),
            "leads": items,
        })
    return {
        "columns": columns,
        "total": len(enriched),
        "early_stages": EARLY_STAGES,
        "late_stages": LATE_STAGES,
    }


@router.get("/overview")
async def overview(admin=Depends(require_staff)):
    cur = db[LEADS].find(await _scope_filter(admin))
    enriched = [await _enrich(d) async for d in cur]
    by_stage = {s: 0 for s in ALL_STAGES}
    for l in enriched:
        by_stage[l["effective_stage"]] = by_stage.get(l["effective_stage"], 0) + 1
    unassigned = sum(1 for l in enriched if not l.get("owner_id"))
    converted = sum(1 for l in enriched if l.get("user_id"))
    active = by_stage.get("active", 0)
    total = len(enriched)
    # M3 · SLA + priority rollups for the dashboard
    sla_breached = sum(1 for l in enriched if (l.get("sla") or {}).get("status") == "breached")
    sla_at_risk = sum(1 for l in enriched if (l.get("sla") or {}).get("at_risk"))
    rt = [l.get("sla", {}).get("first_response_min") for l in enriched
          if l.get("sla") and l["sla"].get("first_response_min") is not None]
    avg_response_min = round(sum(rt) / len(rt), 1) if rt else None
    hot = sum(1 for l in enriched if (l.get("priority") or {}).get("bucket") == "A")
    health_counts = {"red": 0, "yellow": 0, "green": 0}
    for l in enriched:
        c = (l.get("health") or {}).get("color")
        if c in health_counts:
            health_counts[c] += 1
    return {
        "total": total,
        "by_stage": by_stage,
        "unassigned": unassigned,
        "converted": converted,
        "active_investors": active,
        "conversion_rate": round((converted / total) * 100, 1) if total else 0.0,
        "sla_breached": sla_breached,
        "sla_at_risk": sla_at_risk,
        "avg_response_min": avg_response_min,
        "hot_leads": hot,
        "health_counts": health_counts,
    }


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, admin=Depends(require_staff)):
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    enriched = await _enrich(lead)
    # Attach field history (IR0.3).
    history = []
    try:
        cur = db.lumen_field_changes.find(
            {"entity_type": "lead", "entity_id": lead_id}).sort("at", -1).limit(100)
        async for h in cur:
            history.append(_strip_mongo(h))
    except Exception:
        history = []
    enriched["history"] = history
    return enriched


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, admin=Depends(require_staff)):
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if updates:
        updates["updated_at"] = _utc()
        await db[LEADS].update_one({"lead_id": lead_id}, {"$set": updates})
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    return await _enrich(lead)


@router.post("/leads/{lead_id}/stage")
async def change_stage(lead_id: str, payload: StageChange, admin=Depends(require_staff)):
    """Manual transition — EARLY stages only. Late stages are auto-derived."""
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    target = payload.stage
    if target not in EARLY_STAGES:
        raise HTTPException(
            400,
            detail=(f"Стадію '{target}' не можна виставити вручну. "
                    f"Пізні стадії ({', '.join(LATE_STAGES)}) визначаються "
                    f"автоматично за фактами (KYC / акредитація / funding / сертифікат)."),
        )
    prev = lead.get("manual_stage")
    await db[LEADS].update_one(
        {"lead_id": lead_id},
        {"$set": {"manual_stage": target, "updated_at": _utc()}},
    )
    await _record(lead_id, "stage", prev, target, actor=admin, reason=(payload.note or ""))
    await _sla_touch(lead_id, admin)
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    return await _enrich(lead)


async def _do_assign(lead: dict, owner_id: Optional[str], admin: dict, reason: str):
    """Core ownership transition — shared by /owner and /reassign.

    Validates the target manager, is idempotent on no-change, writes field
    history + first-class assignment history, bumps counters and notifies the
    new owner. Returns the freshly enriched lead.
    """
    lead_id = lead.get("lead_id")
    prev_owner = lead.get("owner_id")
    # Idempotent: assigning to the same owner is a no-op.
    if (owner_id or None) == (prev_owner or None):
        return await _enrich(await db[LEADS].find_one({"lead_id": lead_id}))

    if owner_id:
        owner = (await db.users.find_one({"user_id": owner_id})
                 or await db.users.find_one({"id": owner_id}))
        if not owner:
            raise HTTPException(404, detail="Менеджера не знайдено")
        owner = _strip_mongo(owner)
        is_staff = (owner.get("role") in {"admin", "manager"}
                    or bool(set(owner.get("roles", [])) & {"admin", "manager"}))
        if not is_staff:
            raise HTTPException(400, detail="Власником може бути лише Admin або Manager")
        set_doc = {
            "owner_id": owner_id,
            "owner_type": "manager",
            "owner_name": owner.get("name") or owner.get("full_name") or owner.get("email"),
            "owner_email": owner.get("email"),
            "updated_at": _utc(),
        }
    else:
        set_doc = {
            "owner_id": None, "owner_type": None,
            "owner_name": None, "owner_email": None, "updated_at": _utc(),
        }

    await db[LEADS].update_one({"lead_id": lead_id}, {"$set": set_doc})
    await _record(lead_id, "owner_id", prev_owner, owner_id, actor=admin, reason=reason)
    await _mgros_record_assignment(
        lead_id=lead_id,
        from_user_id=prev_owner,
        from_user_name=lead.get("owner_name"),
        to_user_id=owner_id,
        to_user_name=set_doc.get("owner_name"),
        actor=admin,
        reason=reason or "owner_assignment",
    )
    if owner_id:
        fresh = await db[LEADS].find_one({"lead_id": lead_id})
        await _notify_new_owner(_strip_mongo(dict(fresh)), owner_id, _actor_name(admin))
    return await _enrich(await db[LEADS].find_one({"lead_id": lead_id}))


@router.post("/leads/{lead_id}/owner")
async def assign_owner(lead_id: str, payload: OwnerAssign, admin=Depends(require_staff)):
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    return await _do_assign(lead, payload.owner_id, admin, payload.reason or "owner_assignment")


# ── M6 · Reassignment Center ──────────────────────────────────────────────
@router.post("/leads/{lead_id}/reassign")
async def reassign_lead(lead_id: str, payload: "ReassignOne", admin=Depends(require_staff)):
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    return await _do_assign(lead, payload.to_owner_id, admin, payload.reason or "reassignment")


@router.post("/reassign")
async def reassign_bulk(payload: "ReassignBulk", admin=Depends(require_staff)):
    """Bulk reassignment with predictable partial-failure semantics."""
    results = []
    for lid in payload.lead_ids:
        try:
            lead = await db[LEADS].find_one({"lead_id": lid})
            if not lead:
                results.append({"lead_id": lid, "ok": False, "error": "not_found"})
                continue
            await _assert_lead_visible(admin, lead)
            await _do_assign(lead, payload.to_owner_id, admin, payload.reason or "bulk_reassignment")
            results.append({"lead_id": lid, "ok": True})
        except HTTPException as he:
            results.append({"lead_id": lid, "ok": False, "error": he.detail})
        except Exception as e:
            results.append({"lead_id": lid, "ok": False, "error": str(e)})
    ok = sum(1 for r in results if r["ok"])
    return {"results": results, "ok_count": ok, "total": len(results)}


@router.get("/reassignments")
async def list_reassignments(admin=Depends(require_staff), limit: int = Query(100, le=500)):
    """Recent ownership transitions (assignment history). Scoped for managers."""
    from lumen_staff_acl import is_privileged, staff_uid
    q: dict = {}
    if not is_privileged(admin):
        # a scoped manager only sees transitions to/from themselves
        uid = staff_uid(admin)
        q = {"$or": [{"to_user_id": uid}, {"from_user_id": uid}]}
    cur = db["lumen_lead_assignment_history"].find(q).sort("at", -1).limit(limit)
    rows = [_strip_mongo(r) async for r in cur]
    # enrich with lead name
    for r in rows:
        ld = await db[LEADS].find_one({"lead_id": r.get("lead_id")},
                                      {"full_name": 1, "email": 1})
        r["lead_name"] = (ld or {}).get("full_name") or (ld or {}).get("email")
    return {"reassignments": rows, "count": len(rows)}


@router.post("/leads/{lead_id}/convert")
async def convert_lead(lead_id: str, payload: LeadConvert, admin=Depends(require_staff)):
    """Link a lead to a real user / investor profile (does not create accounts)."""
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    await _assert_lead_visible(admin, lead)
    user = (await db.users.find_one({"user_id": payload.user_id})
            or await db.users.find_one({"id": payload.user_id}))
    if not user:
        raise HTTPException(404, detail="Користувача не знайдено")
    user = _strip_mongo(user)
    uid = user.get("user_id") or user.get("id")
    prof = await db.lumen_investor_profiles.find_one({"user_id": uid})
    prev = lead.get("user_id")
    await db[LEADS].update_one(
        {"lead_id": lead_id},
        {"$set": {
            "user_id": uid,
            "investor_profile_id": (prof or {}).get("id") or (prof or {}).get("profile_id"),
            "status": "converted",
            "converted_at": _utc(),
            "updated_at": _utc(),
        }},
    )
    await _record(lead_id, "user_id", prev, uid, actor=admin, reason="lead converted/linked")
    # IR2 · C1 bump leads_converted for the current owner (if any)
    owner_id = lead.get("owner_id")
    if owner_id and not prev:  # first time becoming linked
        await _mgros_bump(owner_id, "leads_converted")
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    return await _enrich(lead)


def _actor_name(admin: dict) -> str:
    return admin.get("name") or admin.get("full_name") or admin.get("email") or "—"


async def _require_lead(lead_id: str, actor: Optional[dict] = None) -> dict:
    lead = await db[LEADS].find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(404, detail="Лід не знайдено")
    if actor is not None:
        await _assert_lead_visible(actor, lead)
    return lead


# ── IR1.3 — Notes ──────────────────────────────────────────────────────────
@router.get("/leads/{lead_id}/notes")
async def list_notes(lead_id: str, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    cur = db[NOTES].find({"lead_id": lead_id}).sort("created_at", -1)
    return {"notes": [_strip_mongo(n) async for n in cur]}


@router.post("/leads/{lead_id}/notes")
async def create_note(lead_id: str, payload: NoteCreate, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(400, detail="Порожня нотатка")
    note = {
        "id": f"note_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "body": body,
        "author_id": admin.get("id") or admin.get("user_id"),
        "author_name": _actor_name(admin),
        "created_at": _utc(),
    }
    await db[NOTES].insert_one(note)
    await _touch(lead_id)
    await _sla_touch(lead_id, admin)
    # IR2 · A1 mirror + C1 activity bump
    await _mgros_mirror(
        lead_id=lead_id,
        user_id=None,
        kind="note",
        interaction_type="note",
        direction="internal",
        title="Нотатка",
        detail=body[:240],
        at=note["created_at"],
        actor_id=note["author_id"],
        actor_name=note["author_name"],
        source_collection=NOTES,
        source_id=note["id"],
    )
    await _mgros_bump(note["author_id"], "notes_count")
    return _strip_mongo(note)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, admin=Depends(require_staff)):
    note = await db[NOTES].find_one({"id": note_id})
    if not note:
        raise HTTPException(404, detail="Нотатку не знайдено")
    await _require_lead(note.get("lead_id"), admin)
    await db[NOTES].delete_one({"id": note_id})
    return {"ok": True}


# ── IR1.4 — Tasks ──────────────────────────────────────────────────────────
@router.get("/leads/{lead_id}/tasks")
async def list_tasks(lead_id: str, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    cur = db[TASKS].find({"lead_id": lead_id}).sort("created_at", -1)
    return {"tasks": [_strip_mongo(t) async for t in cur]}


@router.post("/leads/{lead_id}/tasks")
async def create_task(lead_id: str, payload: TaskCreate, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    if not (payload.title or "").strip():
        raise HTTPException(400, detail="Назва задачі обов'язкова")
    assignee_name = None
    if payload.assignee_id:
        u = (await db.users.find_one({"user_id": payload.assignee_id})
             or await db.users.find_one({"id": payload.assignee_id}))
        if u:
            u = _strip_mongo(u)
            assignee_name = u.get("name") or u.get("full_name") or u.get("email")
    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "title": payload.title.strip(),
        "description": payload.description,
        "assignee_id": payload.assignee_id,
        "assignee_name": assignee_name,
        "due_date": payload.due_date,
        "priority": payload.priority or "normal",
        "task_type": payload.task_type,   # free field, no enum lock
        "status": "open",
        "created_by": _actor_name(admin),
        "created_at": _utc(),
        "updated_at": _utc(),
        "completed_at": None,
    }
    await db[TASKS].insert_one(task)
    # IR2 · A1 mirror (task_created)
    await _mgros_mirror(
        lead_id=lead_id,
        user_id=None,
        kind="task_created",
        interaction_type=payload.task_type or "task",
        direction=None,
        title=f"Задача: {task['title']}",
        detail=(task.get("description") or "")[:240],
        at=task["created_at"],
        actor_id=admin.get("user_id") or admin.get("id"),
        actor_name=_actor_name(admin),
        source_collection=TASKS,
        source_id=task["id"],
        extra={"assignee_id": payload.assignee_id, "priority": task["priority"]},
    )
    await _sla_touch(lead_id, admin)
    return _strip_mongo(task)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, admin=Depends(require_staff)):
    task = await db[TASKS].find_one({"id": task_id})
    if not task:
        raise HTTPException(404, detail="Задачу не знайдено")
    await _require_lead(task.get("lead_id"), admin)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    completing = updates.get("status") == "done" and task.get("status") != "done"
    if updates.get("assignee_id"):
        u = (await db.users.find_one({"user_id": updates["assignee_id"]})
             or await db.users.find_one({"id": updates["assignee_id"]}))
        if u:
            u = _strip_mongo(u)
            updates["assignee_name"] = u.get("name") or u.get("full_name") or u.get("email")
    if completing:
        updates["completed_at"] = _utc()
    updates["updated_at"] = _utc()
    await db[TASKS].update_one({"id": task_id}, {"$set": updates})
    if completing:
        await _touch(task["lead_id"])
        # IR2 · A1 mirror + C1 activity (tasks_completed by the assignee, fallback admin)
        completer = task.get("assignee_id") or admin.get("user_id") or admin.get("id")
        await _mgros_mirror(
            lead_id=task["lead_id"],
            user_id=None,
            kind="task_completed",
            interaction_type=task.get("task_type") or "task",
            title=f"Задача виконана: {task.get('title','')}",
            detail="",
            at=updates["completed_at"],
            actor_id=completer,
            actor_name=task.get("assignee_name") or _actor_name(admin),
            source_collection=TASKS,
            source_id=task_id,
        )
        await _mgros_bump(completer, "tasks_completed")
    return _strip_mongo(await db[TASKS].find_one({"id": task_id}))


# ── IR1.5 — Meetings ───────────────────────────────────────────────────────
@router.get("/leads/{lead_id}/meetings")
async def list_meetings(lead_id: str, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    cur = db[MEETINGS].find({"lead_id": lead_id}).sort("scheduled_at", -1)
    return {"meetings": [_strip_mongo(m) async for m in cur]}


@router.post("/leads/{lead_id}/meetings")
async def create_meeting(lead_id: str, payload: MeetingCreate, admin=Depends(require_staff)):
    await _require_lead(lead_id, admin)
    if not (payload.title or "").strip():
        raise HTTPException(400, detail="Назва зустрічі обов'язкова")
    meeting = {
        "id": f"meet_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "title": payload.title.strip(),
        "scheduled_at": payload.scheduled_at,
        "type": payload.type or "call",
        "duration_min": payload.duration_min or 30,
        "outcome_note": payload.outcome_note,
        "status": "scheduled",
        # calendar integration placeholders (no integration yet — 3b)
        "external_calendar_provider": None,
        "external_event_id": None,
        "calendar_sync_status": None,
        "created_by": _actor_name(admin),
        "created_at": _utc(),
        "updated_at": _utc(),
    }
    await db[MEETINGS].insert_one(meeting)
    await _touch(lead_id)
    await _sla_touch(lead_id, admin)
    # IR2 · A1 mirror (meeting_scheduled)
    await _mgros_mirror(
        lead_id=lead_id,
        user_id=None,
        kind="meeting_scheduled",
        interaction_type="meeting",
        direction="outbound",
        title=f"Зустріч: {meeting['title']}",
        detail=f"{meeting.get('type','')} · {meeting.get('duration_min','')}хв",
        at=meeting["created_at"],
        actor_id=admin.get("user_id") or admin.get("id"),
        actor_name=_actor_name(admin),
        source_collection=MEETINGS,
        source_id=meeting["id"],
    )
    return _strip_mongo(meeting)


@router.patch("/meetings/{meeting_id}")
async def update_meeting(meeting_id: str, payload: MeetingUpdate, admin=Depends(require_staff)):
    m = await db[MEETINGS].find_one({"id": meeting_id})
    if not m:
        raise HTTPException(404, detail="Зустріч не знайдено")
    await _require_lead(m.get("lead_id"), admin)
    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    completing = updates.get("status") == "completed" and m.get("status") != "completed"
    updates["updated_at"] = _utc()
    await db[MEETINGS].update_one({"id": meeting_id}, {"$set": updates})
    if completing:
        await _touch(m["lead_id"])
        # IR2 · A1 mirror + C1 bump (meetings_count)
        completer = admin.get("user_id") or admin.get("id")
        await _mgros_mirror(
            lead_id=m["lead_id"],
            user_id=None,
            kind="meeting_completed",
            interaction_type="meeting",
            direction="outbound",
            title=f"Зустріч проведено: {m.get('title','')}",
            detail=(updates.get("outcome_note") or m.get("outcome_note") or "")[:240],
            at=updates["updated_at"],
            actor_id=completer,
            actor_name=_actor_name(admin),
            source_collection=MEETINGS,
            source_id=meeting_id,
        )
        await _mgros_bump(completer, "meetings_count")
    return _strip_mongo(await db[MEETINGS].find_one({"id": meeting_id}))


# ── IR1.8 — Investor Health ────────────────────────────────────────────────
@router.get("/leads/{lead_id}/health")
async def lead_health(lead_id: str, admin=Depends(require_staff)):
    lead = await _require_lead(lead_id, admin)
    facts = (await _effective(lead))["facts"]
    return await _compute_health(_strip_mongo(lead), facts)


# ── M8 — Manual communication log (call / email / telegram / whatsapp / …) ──
COMM_TYPES = {"call", "email", "telegram", "whatsapp", "sms", "meeting",
              "document", "in_app", "other"}


class CommunicationLog(BaseModel):
    interaction_type: str = Field(..., description="call/email/telegram/whatsapp/sms/document/in_app/other")
    direction: Optional[str] = "outbound"   # inbound | outbound | internal
    title: Optional[str] = None
    detail: Optional[str] = None


@router.post("/leads/{lead_id}/communications")
async def log_communication(lead_id: str, payload: CommunicationLog, admin=Depends(require_staff)):
    """Manually log a real-world communication into the unified log (M8).

    Records into ``lumen_lead_communications`` via the same mirror helper used
    by notes/tasks/meetings — so future Ringostat/Twilio/Gmail events ride the
    SAME table without schema change. Bumps inbound/outbound + call counters
    and counts as an SLA first-response.
    """
    await _require_lead(lead_id, admin)
    itype = (payload.interaction_type or "other").lower().strip()
    if itype not in COMM_TYPES:
        itype = "other"
    direction = (payload.direction or "outbound").lower()
    if direction not in ("inbound", "outbound", "internal"):
        direction = "outbound"
    actor_id = admin.get("user_id") or admin.get("id")
    title = payload.title or {
        "call": "Дзвінок", "email": "Email", "telegram": "Telegram",
        "whatsapp": "WhatsApp", "sms": "SMS", "document": "Документ",
        "in_app": "У застосунку", "meeting": "Зустріч", "other": "Комунікація",
    }.get(itype, "Комунікація")
    import uuid as _uuid
    src_id = f"manual_{_uuid.uuid4().hex[:12]}"
    await _mgros_mirror(
        lead_id=lead_id,
        user_id=None,
        kind=itype,
        interaction_type=itype,
        direction=direction,
        title=title,
        detail=(payload.detail or "")[:500],
        at=_utc(),
        actor_id=actor_id,
        actor_name=_actor_name(admin),
        source_collection="manual",
        source_id=src_id,
    )
    # counters: calls + inbound/outbound
    if itype == "call":
        await _mgros_bump(actor_id, "calls_count")
    await _mgros_bump(actor_id, "communications_inbound" if direction == "inbound"
                      else "communications_outbound")
    await _touch(lead_id)
    await _sla_touch(lead_id, admin)
    return {"ok": True, "interaction_type": itype, "direction": direction}


# ── IR1.6 — Unified Timeline ───────────────────────────────────────────────
@router.get("/leads/{lead_id}/timeline")
async def lead_timeline(lead_id: str, admin=Depends(require_staff)):
    """One continuous feed: lead events + linked-investor real facts.

    Sources: lead field-history, notes, tasks, meetings, and — via the linked
    user_id — KYC / accreditation changes, funding transfers, certificates.
    This keeps a single uninterrupted chain Lead → Meeting → KYC → Accreditation
    → Funding → Certificate for the manager (1c).
    """
    lead = await _require_lead(lead_id, admin)
    uid = lead.get("user_id")
    events: List[dict] = []

    def add(kind, title, at, detail="", actor=""):
        if not at:
            return
        events.append({"kind": kind, "title": title, "detail": detail,
                       "at": at, "actor": actor})

    # 1. Lead field-history (created / stage / owner / convert)
    try:
        async for h in db.lumen_field_changes.find(
                {"entity_type": "lead", "entity_id": lead_id}):
            h = _strip_mongo(h)
            f, old, new = h.get("field"), h.get("old_value"), h.get("new_value")
            at = h.get("at") or h.get("changed_at") or h.get("created_at")
            actor = (h.get("actor") or {}).get("email") if isinstance(h.get("actor"), dict) else ""
            if f == "stage" and not old:
                add("lead_created", "Лід створений", at, actor=actor)
            elif f == "stage":
                add("stage_changed", "Зміна стадії", at, f"{old} → {new}", actor)
            elif f == "owner_id":
                add("owner_assigned", "Призначено власника", at, str(new or "—"), actor)
            elif f == "user_id":
                add("converted", "Конвертовано / прив'язано", at, str(new or "—"), actor)
    except Exception:
        pass

    # 2. Notes
    async for n in db[NOTES].find({"lead_id": lead_id}):
        n = _strip_mongo(n)
        add("note", "Нотатка додана", n.get("created_at"),
            (n.get("body") or "")[:120], n.get("author_name", ""))

    # 3. Tasks
    async for t in db[TASKS].find({"lead_id": lead_id}):
        t = _strip_mongo(t)
        add("task_created", "Задача створена", t.get("created_at"),
            t.get("title", ""), t.get("created_by", ""))
        if t.get("status") == "done":
            add("task_completed", "Задача виконана", t.get("completed_at"), t.get("title", ""))

    # 4. Meetings
    async for m in db[MEETINGS].find({"lead_id": lead_id}):
        m = _strip_mongo(m)
        add("meeting_scheduled", "Зустріч заплановано",
            m.get("created_at") or m.get("scheduled_at"),
            f"{m.get('title','')} · {m.get('type','')}", m.get("created_by", ""))
        if m.get("status") == "completed":
            add("meeting_completed", "Зустріч проведено", m.get("updated_at"),
                (m.get("outcome_note") or m.get("title") or "")[:120])

    # 5. Linked investor real facts (continuity across conversion — 1c)
    if uid:
        try:
            async for tx in db.lumen_institutional_transfers.find({"investor_id": uid}):
                tx = _strip_mongo(tx)
                st = tx.get("canonical_status", "—")
                label = "Funding отримано" if st == "confirmed" else f"Funding: {st}"
                add("funding", label, tx.get("updated_at") or tx.get("created_at"),
                    f"{tx.get('amount', '')} {tx.get('currency', '')}".strip())
        except Exception:
            pass
        try:
            async for c in db.lumen_certificates.find({"investor_id": uid}):
                c = _strip_mongo(c)
                add("certificate", "Сертифікат випущено",
                    c.get("issued_at") or c.get("created_at"),
                    c.get("certificate_no") or c.get("id", ""))
        except Exception:
            pass
        try:
            async for h in db.lumen_field_changes.find(
                    {"entity_type": {"$in": ["investor", "kyc"]}, "entity_id": uid}):
                h = _strip_mongo(h)
                f, old, new = h.get("field"), h.get("old_value"), h.get("new_value")
                at = h.get("at") or h.get("changed_at") or h.get("created_at")
                if f in ("kyc_status",):
                    add("kyc", "KYC оновлено", at, f"{old} → {new}")
                elif f in ("accreditation_status",):
                    add("accreditation", "Акредитація оновлена", at, f"{old} → {new}")
        except Exception:
            pass

    events.sort(key=lambda e: e["at"], reverse=True)
    return {"timeline": events, "count": len(events)}


# ──────────────────────────────────────────────────────────────────────────
# Index bootstrap
# ──────────────────────────────────────────────────────────────────────────
async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[LEADS].create_index("lead_id", unique=True)
        await d[LEADS].create_index("email")
        await d[LEADS].create_index("owner_id")
        await d[LEADS].create_index("user_id")
        await d[LEADS].create_index("manual_stage")
        await d[LEADS].create_index([("created_at", -1)])
        await d[NOTES].create_index([("lead_id", 1), ("created_at", -1)])
        await d[TASKS].create_index([("lead_id", 1), ("status", 1)])
        await d[TASKS].create_index("id", unique=True)
        await d[TASKS].create_index("assignee_id")
        await d[MEETINGS].create_index([("lead_id", 1), ("scheduled_at", -1)])
        await d[MEETINGS].create_index("id", unique=True)
        await d[NOTES].create_index("id", unique=True)
    except Exception:
        pass
