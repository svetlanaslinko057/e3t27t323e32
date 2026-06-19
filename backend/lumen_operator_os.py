"""
LUMEN 2.0 — Phase F — Operator OS
=================================

The architectural pivot. Before Phase F, LUMEN was an *asset platform*
(asset → investor → ownership). After Phase F the **operator** becomes the
primary subject: operators source assets, run them, work with tenants and
report — while LUMEN becomes the registry, payment rail, certificate rail,
marketplace and **control system**.

This is what makes LUMEN scale without LUMEN's own participation: it stops
being an investment site and becomes infrastructure for dozens of operators
and hundreds of assets.

Blocks
------
  F1  Operator Profile      — rich profile (team, years, website, docs, status)
  F2  Verification Engine   — Draft→Applied→Verified→Approved (+Restricted/Suspended)
  F3  Operator KPI          — AUM, assets, investors, yield, vacancy, payout
                              timeliness, reporting score, liquidity score (DERIVED)
  F4  SLA Engine            — report not filed: 30d Warning / 60d Critical / 90d Escalation
  F5  Operator Reputation   — fact-based composite 0-100 + grade AAA/AA/A/BBB/BB
  F6  Governance Hooks      — Community sentiment (Phase C) below threshold → warning
  F7  Operator Leaderboard  — public ranking by facts (trust, not gamification)
  F8  Operator Deal Flow    — deals sourced → DD → funded → live → exited (Phase E link)
  F9  Revenue Sharing       — management / success / performance fee schedule (foundation)
  F10 Operator Portal       — NEW role `operator` with a strictly scoped cabinet

Everything DERIVES from real collections — no mocks.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import bcrypt
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin, _strip_mongo,
                       _now, _iso)

try:
    from lumen_payments import _round2, BASE_CURRENCY
except Exception:  # pragma: no cover
    BASE_CURRENCY = "UAH"

    def _round2(v: float) -> float:
        return round(float(v or 0), 2)

logger = logging.getLogger("lumen.operator")
router = APIRouter(prefix="/api", tags=["lumen-operator-os"])

# ── Domain constants ─────────────────────────────────────────────────────────
VERIFICATION_STATES = ("draft", "applied", "verified", "approved", "restricted", "suspended")
VERIFICATION_LABELS_UK = {
    "draft": "Чернетка", "applied": "Подано заявку", "verified": "Перевірено",
    "approved": "Затверджено", "restricted": "Обмежено", "suspended": "Призупинено",
}
TRUSTED_STATES = ("verified", "approved")  # → investor-visible "Verified Operator"

OPERATOR_KINDS = ("internal", "external", "partner")
KIND_LABELS_UK = {"internal": "Внутрішній", "external": "Зовнішній", "partner": "Партнер"}

# SLA thresholds (days since last published report)
SLA_WARNING_DAYS = 30
SLA_CRITICAL_DAYS = 60
SLA_ESCALATION_DAYS = 90
SLA_SEVERITY = {"ok": 0, "warning": 1, "critical": 2, "escalation": 3}
SLA_LABELS_UK = {"ok": "В нормі", "warning": "Попередження", "critical": "Критично", "escalation": "Ескалація"}

PAYOUT_GRACE_DAYS = 3
SENTIMENT_WARN_THRESHOLD = 40.0  # positive % below this → governance warning

REPUTATION_GRADES = [
    (90, "AAA"), (80, "AA"), (70, "A"), (60, "BBB"), (50, "BB"), (0, "B"),
]


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _uid(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    return user.get("user_id") or user.get("id")


def _is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return "admin" in (user.get("roles") or []) or "admin" in (user.get("states") or [])


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _as_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _days_since(v: Any) -> Optional[float]:
    d = _as_dt(v)
    if not d:
        return None
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400.0


async def _operator_or_404(op_id: str) -> dict:
    op = await db.lumen_operators.find_one({"id": op_id}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="Оператора не знайдено")
    return op


async def _managed_assets(op_id: str) -> list[dict]:
    out = []
    async for a in db.lumen_assets.find({"operator_id": op_id}, {"_id": 0}):
        out.append(a)
    return out


def _op_public(op: dict, kpi: dict | None = None, rep: dict | None = None) -> dict:
    """Privacy-safe operator card for investors/public."""
    out = {
        "id": op["id"], "name": op.get("name"), "kind": op.get("kind"),
        "kind_label": KIND_LABELS_UK.get(op.get("kind"), op.get("kind")),
        "region": op.get("region"), "specialization": op.get("specialization"),
        "website": op.get("website"), "description": op.get("description"),
        "years_active": op.get("years_active"), "team_size": op.get("team_size"),
        "logo_url": op.get("logo_url"),
        "status": op.get("status", "draft"),
        "status_label": VERIFICATION_LABELS_UK.get(op.get("status", "draft")),
        "verified": op.get("status") in TRUSTED_STATES,
    }
    if kpi is not None:
        out["kpi"] = kpi
    if rep is not None:
        out["reputation"] = rep
    return out


# ── KPI (F3) ─────────────────────────────────────────────────────────────────

async def _operator_kpi(op_id: str) -> dict:
    assets = await _managed_assets(op_id)
    asset_ids = [a["id"] for a in assets]
    n_assets = len(assets)

    aum = 0.0
    investors: set[str] = set()
    if asset_ids:
        async for o in db.lumen_ownerships.find({"asset_id": {"$in": asset_ids}}):
            aum += float(o.get("amount_uah") or o.get("amount") or 0)
            if o.get("investor_id"):
                investors.add(o["investor_id"])
    if aum == 0:
        aum = sum(float(a.get("raised") or a.get("raised_amount") or 0) for a in assets)

    yields = [float(a.get("target_yield")) for a in assets if a.get("target_yield") is not None]
    avg_yield = round(sum(yields) / len(yields), 2) if yields else 0.0
    occs = [float(a.get("occupancy_percent")) for a in assets if a.get("occupancy_percent") is not None]
    occupancy = round(sum(occs) / len(occs), 1) if occs else None
    vacancy = round(100 - occupancy, 1) if occupancy is not None else None

    # payout timeliness
    on_time = 0
    total_paid = 0
    if asset_ids:
        async for p in db.lumen_payout_records.find({"asset_id": {"$in": asset_ids}}):
            st = (p.get("status") or "").lower()
            if st not in ("paid", "credited", "settled", "completed"):
                continue
            planned = _as_dt(p.get("planned_date"))
            paid = _as_dt(p.get("paid_date"))
            if not paid:
                continue
            total_paid += 1
            if not planned or paid <= planned + timedelta(days=PAYOUT_GRACE_DAYS):
                on_time += 1
    payout_timeliness = round(on_time / total_paid * 100, 1) if total_paid else None

    # reporting score (recency per asset)
    rep_scores = []
    for a in assets:
        last = await db.lumen_asset_reports.find_one(
            {"asset_id": a["id"], "published": True}, {"_id": 0, "created_at": 1},
            sort=[("created_at", -1)])
        d = _days_since((last or {}).get("created_at")) if last else None
        if d is None:
            rep_scores.append(0)
        elif d <= 30:
            rep_scores.append(100)
        elif d <= 60:
            rep_scores.append(70)
        elif d <= 90:
            rep_scores.append(40)
        else:
            rep_scores.append(15)
    reporting_score = round(sum(rep_scores) / len(rep_scores)) if rep_scores else 0

    # liquidity score (secondary trades activity, 0-10)
    trades_90d = 0
    if asset_ids:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        async for t in db.lumen_secondary_trades.find({"asset_id": {"$in": asset_ids}}):
            td = _as_dt(t.get("created_at"))
            if td is None or td >= cutoff:
                trades_90d += 1
    open_orders = 0
    if asset_ids:
        open_orders = await db.lumen_liquidity_orders.count_documents(
            {"asset_id": {"$in": asset_ids}, "status": {"$in": ["open", "active", "pending"]}})
    liquidity_score = min(10.0, round(trades_90d * 1.5 + open_orders * 0.5, 1))

    return {
        "assets_count": n_assets,
        "aum_uah": _round2(aum),
        "investors_count": len(investors),
        "avg_yield_pct": avg_yield,
        "occupancy_pct": occupancy,
        "vacancy_pct": vacancy,
        "payout_timeliness_pct": payout_timeliness,
        "reporting_score": reporting_score,
        "liquidity_score": liquidity_score,
        "trades_90d": trades_90d,
    }


# ── SLA (F4) ───────────────────────────────────────────────────────────────

def _sla_status_for_age(days: Optional[float]) -> str:
    if days is None:
        return "escalation"  # never reported
    if days <= SLA_WARNING_DAYS:
        return "ok"
    if days <= SLA_CRITICAL_DAYS:
        return "warning"
    if days <= SLA_ESCALATION_DAYS:
        return "critical"
    return "escalation"


async def _operator_sla(op_id: str) -> dict:
    assets = await _managed_assets(op_id)
    items = []
    worst = "ok"
    for a in assets:
        last = await db.lumen_asset_reports.find_one(
            {"asset_id": a["id"], "published": True}, {"_id": 0, "created_at": 1, "title": 1},
            sort=[("created_at", -1)])
        days = _days_since((last or {}).get("created_at")) if last else None
        status = _sla_status_for_age(days)
        if SLA_SEVERITY[status] > SLA_SEVERITY[worst]:
            worst = status
        items.append({
            "asset_id": a["id"], "asset_title": a.get("title"),
            "last_report_at": _iso((last or {}).get("created_at")) if last else None,
            "days_since_report": round(days, 1) if days is not None else None,
            "status": status, "status_label": SLA_LABELS_UK[status],
        })
    counts = {"ok": 0, "warning": 0, "critical": 0, "escalation": 0}
    for it in items:
        counts[it["status"]] += 1
    return {"overall": worst, "overall_label": SLA_LABELS_UK[worst],
            "counts": counts, "items": items}


# ── Governance (F6) ──────────────────────────────────────────────────────────

def _mood_polarity(mood: Any) -> int:
    m = str(mood or "").lower()
    if m in ("bullish", "positive", "up", "good", "happy", "1", "+1"):
        return 1
    if m in ("bearish", "negative", "down", "bad", "angry", "-1"):
        return -1
    try:
        f = float(mood)
        return 1 if f > 0 else (-1 if f < 0 else 0)
    except Exception:
        return 0


async def _operator_governance(op_id: str) -> dict:
    assets = await _managed_assets(op_id)
    asset_ids = [a["id"] for a in assets]
    pos = neg = total = 0.0
    per_asset = {}
    if asset_ids:
        async for s in db.lumen_community_sentiment.find({"asset_id": {"$in": asset_ids}}):
            w = float(s.get("units_weight") or 1)
            pol = _mood_polarity(s.get("mood"))
            total += w
            if pol > 0:
                pos += w
            elif pol < 0:
                neg += w
            pa = per_asset.setdefault(s["asset_id"], {"pos": 0.0, "neg": 0.0, "total": 0.0})
            pa["total"] += w
            if pol > 0:
                pa["pos"] += w
            elif pol < 0:
                pa["neg"] += w
    positive_pct = round(pos / total * 100, 1) if total else None
    alert = positive_pct is not None and positive_pct < SENTIMENT_WARN_THRESHOLD
    flagged = []
    for aid, pa in per_asset.items():
        p = round(pa["pos"] / pa["total"] * 100, 1) if pa["total"] else None
        if p is not None and p < SENTIMENT_WARN_THRESHOLD:
            a = next((x for x in assets if x["id"] == aid), {})
            flagged.append({"asset_id": aid, "asset_title": a.get("title"), "positive_pct": p})
    return {"positive_pct": positive_pct, "alert": alert,
            "threshold": SENTIMENT_WARN_THRESHOLD, "flagged_assets": flagged,
            "samples": int(total)}


# ── Reputation (F5) ──────────────────────────────────────────────────────────

def _grade(score: float) -> str:
    for threshold, g in REPUTATION_GRADES:
        if score >= threshold:
            return g
    return "B"


async def _operator_reputation(op_id: str, kpi: dict | None = None,
                                gov: dict | None = None) -> dict:
    kpi = kpi if kpi is not None else await _operator_kpi(op_id)
    gov = gov if gov is not None else await _operator_governance(op_id)

    payout = kpi.get("payout_timeliness_pct")
    reporting = kpi.get("reporting_score") or 0
    occupancy = kpi.get("occupancy_pct")
    liquidity = (kpi.get("liquidity_score") or 0) * 10
    sentiment = gov.get("positive_pct")

    components = [
        ("payout_timeliness", payout if payout is not None else 60, 0.30),
        ("reporting", reporting, 0.25),
        ("occupancy", occupancy if occupancy is not None else 70, 0.20),
        ("liquidity", liquidity, 0.15),
        ("sentiment", sentiment if sentiment is not None else 60, 0.10),
    ]
    score = round(sum(min(100, max(0, v)) * w for _, v, w in components), 1)
    breakdown = {k: round(min(100, max(0, v)), 1) for k, v, _ in components}
    return {"score": score, "grade": _grade(score), "breakdown": breakdown}


# ── Deal Flow (F8) ───────────────────────────────────────────────────────────

async def _operator_dealflow(op_id: str) -> dict:
    sourced = in_dd = committee = funding = live = exited = rejected = 0
    rejection_reasons: dict[str, int] = {}
    async for d in db.lumen_deals.find({"operator_id": op_id}, {"_id": 0}):
        sourced += 1
        s = d.get("stage")
        if s == "due_diligence":
            in_dd += 1
        elif s == "committee":
            committee += 1
        elif s == "funding":
            funding += 1
        elif s in ("live", "operating"):
            live += 1
        elif s == "exited":
            exited += 1
        elif s == "rejected":
            rejected += 1
            r = (d.get("rejection_reason") or "Без причини").strip()
            rejection_reasons[r] = rejection_reasons.get(r, 0) + 1
    funded_or_better = funding + live + exited
    success_rate = round(funded_or_better / sourced * 100, 1) if sourced else 0
    return {
        "sourced": sourced, "in_dd": in_dd, "committee": committee,
        "funding": funding, "live": live, "exited": exited, "rejected": rejected,
        "funding_success_pct": success_rate,
        "rejection_reasons": sorted(
            [{"reason": k, "count": v} for k, v in rejection_reasons.items()],
            key=lambda x: x["count"], reverse=True),
    }


# ── Revenue sharing (F9) ─────────────────────────────────────────────────────

def _fees_preview(op: dict, kpi: dict) -> dict:
    fees = op.get("fees") or {}
    mgmt = float(fees.get("management_fee_pct") or 0)
    aum = kpi.get("aum_uah") or 0
    return {
        "management_fee_pct": mgmt,
        "success_fee_pct": float(fees.get("success_fee_pct") or 0),
        "performance_fee_pct": float(fees.get("performance_fee_pct") or 0),
        "notes": fees.get("notes"),
        "estimated_annual_management_fee_uah": _round2(aum * mgmt / 100),
    }


async def _operator_event(op_id: str, kind: str, severity: str, message: str,
                          actor: Optional[dict] = None) -> None:
    await db.lumen_operator_events.insert_one({
        "id": f"oe-{uuid.uuid4().hex[:12]}",
        "operator_id": op_id, "kind": kind, "severity": severity,
        "message": message, "actor_id": _uid(actor),
        "created_at": _now(),
    })


# ── Operator role resolution (F10) ───────────────────────────────────────────

async def require_operator(request: Request) -> dict:
    """Returns {'user': user, 'operator': operator} or raises 403."""
    user = await get_current_user(request)
    uid = _uid(user)
    op = await db.lumen_operators.find_one({"user_id": uid}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=403, detail="Обліковий запис не пов'язаний з оператором")
    return {"user": user, "operator": op}


# ════════════════════════════════════════════════════════════════════════════
# Pydantic payloads
# ════════════════════════════════════════════════════════════════════════════

class ProfilePatch(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    region: Optional[str] = None
    specialization: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    years_active: Optional[int] = None
    team_size: Optional[int] = None
    logo_url: Optional[str] = None
    contact: Optional[str] = None


class VerificationIn(BaseModel):
    to_status: str
    note: Optional[str] = None


class FeesIn(BaseModel):
    management_fee_pct: Optional[float] = None
    success_fee_pct: Optional[float] = None
    performance_fee_pct: Optional[float] = None
    notes: Optional[str] = None


class DocumentIn(BaseModel):
    title: str
    kind: Optional[str] = "other"
    url: Optional[str] = None


class AssignAssetIn(BaseModel):
    asset_id: str


class LinkUserIn(BaseModel):
    email: str
    name: Optional[str] = None
    password: Optional[str] = None


class ReportIn(BaseModel):
    title: str
    period_label: Optional[str] = None
    summary: Optional[str] = None
    report_type: Optional[str] = "operational"


# ════════════════════════════════════════════════════════════════════════════
# F1/F2/F3/F4/F5/F8/F9 — Admin operator OS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/operators/{op_id}/overview")
async def admin_operator_overview(op_id: str, _=Depends(require_admin)):
    op = await _operator_or_404(op_id)
    kpi = await _operator_kpi(op_id)
    gov = await _operator_governance(op_id)
    rep = await _operator_reputation(op_id, kpi, gov)
    sla = await _operator_sla(op_id)
    dealflow = await _operator_dealflow(op_id)
    assets = await _managed_assets(op_id)
    docs = []
    async for d in db.lumen_operator_documents.find({"operator_id": op_id}, {"_id": 0}).sort("created_at", -1):
        docs.append(_strip_mongo(d))
    events = []
    async for e in db.lumen_operator_events.find({"operator_id": op_id}, {"_id": 0}).sort("created_at", -1).limit(50):
        events.append(_strip_mongo(e))
    linked_user = None
    if op.get("user_id"):
        u = await db.users.find_one({"user_id": op["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        linked_user = u
    return {
        "operator": _op_public(op, kpi, rep),
        "raw": _strip_mongo(op),
        "kpi": kpi, "reputation": rep, "sla": sla, "governance": gov,
        "dealflow": dealflow,
        "fees": _fees_preview(op, kpi),
        "assets": [{"id": a["id"], "title": a.get("title"), "category": a.get("category"),
                    "status": a.get("status"), "occupancy_percent": a.get("occupancy_percent"),
                    "raised": a.get("raised"), "round_target": a.get("round_target")} for a in assets],
        "documents": docs, "events": events, "linked_user": linked_user,
        "verification_states": list(VERIFICATION_STATES),
        "verification_labels": VERIFICATION_LABELS_UK,
    }


@router.get("/admin/operators/{op_id}/kpi")
async def admin_operator_kpi(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    return await _operator_kpi(op_id)


@router.get("/admin/operators/{op_id}/sla")
async def admin_operator_sla(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    return await _operator_sla(op_id)


@router.get("/admin/operators/{op_id}/reputation")
async def admin_operator_reputation(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    return await _operator_reputation(op_id)


@router.get("/admin/operators/{op_id}/dealflow")
async def admin_operator_dealflow(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    return await _operator_dealflow(op_id)


@router.get("/admin/operators/{op_id}/governance")
async def admin_operator_governance(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    return await _operator_governance(op_id)


@router.patch("/admin/operators/{op_id}/profile")
async def admin_update_profile(op_id: str, payload: ProfilePatch, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "kind" in upd and upd["kind"] not in OPERATOR_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип")
    upd["updated_at"] = _now()
    await db.lumen_operators.update_one({"id": op_id}, {"$set": upd})
    return {"ok": True}


@router.post("/admin/operators/{op_id}/verification")
async def admin_verification(op_id: str, payload: VerificationIn, admin=Depends(require_admin)):
    op = await _operator_or_404(op_id)
    if payload.to_status not in VERIFICATION_STATES:
        raise HTTPException(status_code=400, detail="Невідомий статус")
    prev = op.get("status", "draft")
    await db.lumen_operators.update_one(
        {"id": op_id}, {"$set": {"status": payload.to_status, "updated_at": _now()}})
    await _operator_event(
        op_id, "verification", "info",
        f"Статус: {VERIFICATION_LABELS_UK.get(prev)} → {VERIFICATION_LABELS_UK.get(payload.to_status)}"
        + (f". {payload.note}" if payload.note else ""), admin)
    return {"ok": True, "status": payload.to_status}


@router.patch("/admin/operators/{op_id}/fees")
async def admin_update_fees(op_id: str, payload: FeesIn, _=Depends(require_admin)):
    op = await _operator_or_404(op_id)
    fees = op.get("fees") or {}
    for k, v in payload.dict(exclude_unset=True).items():
        if v is not None:
            fees[k] = v
    await db.lumen_operators.update_one(
        {"id": op_id}, {"$set": {"fees": fees, "updated_at": _now()}})
    return {"ok": True, "fees": fees}


@router.get("/admin/operators/{op_id}/events")
async def admin_operator_events(op_id: str, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    items = []
    async for e in db.lumen_operator_events.find({"operator_id": op_id}, {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(e))
    return {"items": items}


# Documents
@router.post("/admin/operators/{op_id}/documents")
async def add_operator_doc(op_id: str, payload: DocumentIn, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    doc = {
        "id": f"od-{uuid.uuid4().hex[:12]}", "operator_id": op_id,
        "title": payload.title.strip(), "kind": payload.kind or "other",
        "url": payload.url, "status": "uploaded", "created_at": _now(),
    }
    await db.lumen_operator_documents.insert_one(doc)
    return _strip_mongo(doc)


@router.delete("/admin/operators/{op_id}/documents/{doc_id}")
async def del_operator_doc(op_id: str, doc_id: str, _=Depends(require_admin)):
    res = await db.lumen_operator_documents.delete_one({"id": doc_id, "operator_id": op_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    return {"ok": True}


# Asset assignment
@router.post("/admin/operators/{op_id}/assets")
async def assign_asset(op_id: str, payload: AssignAssetIn, admin=Depends(require_admin)):
    await _operator_or_404(op_id)
    a = await db.lumen_assets.find_one({"id": payload.asset_id}, {"_id": 0, "title": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    await db.lumen_assets.update_one(
        {"id": payload.asset_id}, {"$set": {"operator_id": op_id, "updated_at": _now()}})
    await _operator_event(op_id, "asset_assigned", "info",
                          f"Призначено об'єкт: {a.get('title')}", admin)
    return {"ok": True}


@router.delete("/admin/operators/{op_id}/assets/{asset_id}")
async def unassign_asset(op_id: str, asset_id: str, _=Depends(require_admin)):
    await db.lumen_assets.update_one(
        {"id": asset_id, "operator_id": op_id}, {"$set": {"operator_id": None, "updated_at": _now()}})
    return {"ok": True}


# Link / create operator user
@router.post("/admin/operators/{op_id}/link-user")
async def link_user(op_id: str, payload: LinkUserIn, _=Depends(require_admin)):
    await _operator_or_404(op_id)
    email = payload.email.strip().lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        uid = user.get("user_id") or user.get("id")
        # promote to operator role
        roles = list(set((user.get("roles") or []) + ["operator"]))
        states = list(set((user.get("states") or []) + ["operator"]))
        await db.users.update_one({"user_id": uid},
                                  {"$set": {"role": "operator", "roles": roles, "states": states}})
    else:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        pw = payload.password or "operator123"
        await db.users.insert_one({
            "user_id": uid, "email": email,
            "name": payload.name or email.split("@")[0],
            "password_hash": _hash_pw(pw),
            "role": "operator", "roles": ["operator"], "states": ["operator"],
            "created_at": _now(), "updated_at": _now(),
        })
    await db.lumen_operators.update_one({"id": op_id}, {"$set": {"user_id": uid, "updated_at": _now()}})
    return {"ok": True, "user_id": uid, "email": email}


# Scans (F4 / F6) — on-demand; also run at startup bootstrap
@router.post("/admin/operators/sla/scan")
async def scan_sla(_=Depends(require_admin)):
    res = await run_sla_scan()
    return res


@router.post("/admin/operators/governance/scan")
async def scan_governance(_=Depends(require_admin)):
    res = await run_governance_scan()
    return res


async def run_sla_scan() -> dict:
    """Emit SLA events for operators breaching reporting thresholds."""
    flagged = 0
    async for op in db.lumen_operators.find({}, {"_id": 0, "id": 1, "name": 1}):
        sla = await _operator_sla(op["id"])
        if sla["overall"] in ("warning", "critical", "escalation"):
            # de-dupe: only one open SLA event per day per operator+severity
            since = _now() - timedelta(hours=20)
            existing = await db.lumen_operator_events.find_one({
                "operator_id": op["id"], "kind": "sla",
                "severity": sla["overall"], "created_at": {"$gte": since}})
            if not existing:
                await _operator_event(
                    op["id"], "sla", sla["overall"],
                    f"SLA звітності: {SLA_LABELS_UK[sla['overall']]} "
                    f"({sla['counts']['critical'] + sla['counts']['escalation']} критичних об'єктів)")
                flagged += 1
    return {"flagged": flagged}


async def run_governance_scan() -> dict:
    flagged = 0
    async for op in db.lumen_operators.find({}, {"_id": 0, "id": 1}):
        gov = await _operator_governance(op["id"])
        if gov.get("alert"):
            since = _now() - timedelta(hours=20)
            existing = await db.lumen_operator_events.find_one({
                "operator_id": op["id"], "kind": "governance", "created_at": {"$gte": since}})
            if not existing:
                await _operator_event(
                    op["id"], "governance", "warning",
                    f"Настрій спільноти {gov['positive_pct']}% позитивних — нижче порогу {SENTIMENT_WARN_THRESHOLD}%")
                flagged += 1
    return {"flagged": flagged}


# ════════════════════════════════════════════════════════════════════════════
# F7 — Public Leaderboard + public operator card
# ════════════════════════════════════════════════════════════════════════════

@router.get("/operators/leaderboard")
async def leaderboard():
    rows = []
    async for op in db.lumen_operators.find({}, {"_id": 0}):
        if op.get("status") == "suspended":
            continue
        kpi = await _operator_kpi(op["id"])
        gov = await _operator_governance(op["id"])
        rep = await _operator_reputation(op["id"], kpi, gov)
        card = _op_public(op, kpi, rep)
        rows.append(card)
    rows.sort(key=lambda r: (r.get("reputation") or {}).get("score", 0), reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"items": rows}


@router.get("/operators/{op_id}/public")
async def operator_public(op_id: str):
    op = await _operator_or_404(op_id)
    kpi = await _operator_kpi(op_id)
    rep = await _operator_reputation(op_id, kpi)
    dealflow = await _operator_dealflow(op_id)
    card = _op_public(op, kpi, rep)
    card["dealflow"] = {"sourced": dealflow["sourced"], "live": dealflow["live"]}
    card["managed_assets"] = [
        {"id": a["id"], "title": a.get("title"), "category": a.get("category")}
        for a in await _managed_assets(op_id)]
    return card


@router.get("/assets/{asset_id}/operator-card")
async def asset_operator_card(asset_id: str):
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "id": 1, "operator_id": 1})
    if a is None:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    op_id = a.get("operator_id")
    if not op_id:
        return {"operator": None}
    op = await db.lumen_operators.find_one({"id": op_id}, {"_id": 0})
    if not op:
        return {"operator": None}
    kpi = await _operator_kpi(op_id)
    rep = await _operator_reputation(op_id, kpi)
    return {"operator": _op_public(op, kpi, rep)}


# ════════════════════════════════════════════════════════════════════════════
# F10 — Operator Portal (role: operator) — strictly scoped
# ════════════════════════════════════════════════════════════════════════════

@router.get("/operator/me")
async def operator_me(ctx=Depends(require_operator)):
    op = ctx["operator"]
    kpi = await _operator_kpi(op["id"])
    rep = await _operator_reputation(op["id"], kpi)
    out = _op_public(op, kpi, rep)
    out["fees"] = _fees_preview(op, kpi)
    return out


@router.get("/operator/dashboard")
async def operator_dashboard(ctx=Depends(require_operator)):
    op = ctx["operator"]
    kpi = await _operator_kpi(op["id"])
    gov = await _operator_governance(op["id"])
    rep = await _operator_reputation(op["id"], kpi, gov)
    sla = await _operator_sla(op["id"])
    dealflow = await _operator_dealflow(op["id"])
    alerts = []
    async for e in db.lumen_operator_events.find(
            {"operator_id": op["id"], "severity": {"$in": ["warning", "critical", "escalation"]}},
            {"_id": 0}).sort("created_at", -1).limit(10):
        alerts.append(_strip_mongo(e))
    return {
        "operator": _op_public(op),
        "kpi": kpi, "reputation": rep, "sla": sla, "governance": gov,
        "dealflow": dealflow, "fees": _fees_preview(op, kpi), "alerts": alerts,
    }


@router.get("/operator/assets")
async def operator_assets(ctx=Depends(require_operator)):
    op = ctx["operator"]
    items = []
    for a in await _managed_assets(op["id"]):
        last = await db.lumen_asset_reports.find_one(
            {"asset_id": a["id"], "published": True}, {"_id": 0, "created_at": 1},
            sort=[("created_at", -1)])
        days = _days_since((last or {}).get("created_at")) if last else None
        n_inv = len(await db.lumen_ownerships.distinct("investor_id", {"asset_id": a["id"]}))
        items.append({
            "id": a["id"], "title": a.get("title"), "category": a.get("category"),
            "status": a.get("status"), "location": a.get("location"),
            "occupancy_percent": a.get("occupancy_percent"),
            "target_yield": a.get("target_yield"),
            "round_target": a.get("round_target"), "raised": a.get("raised"),
            "cover_url": a.get("cover_url"), "investors_count": n_inv,
            "last_report_days": round(days, 1) if days is not None else None,
            "sla_status": _sla_status_for_age(days),
        })
    return {"items": items}


@router.get("/operator/reports")
async def operator_reports(ctx=Depends(require_operator)):
    op = ctx["operator"]
    asset_ids = [a["id"] for a in await _managed_assets(op["id"])]
    items = []
    if asset_ids:
        titles = {a["id"]: a.get("title") async for a in db.lumen_assets.find(
            {"id": {"$in": asset_ids}}, {"_id": 0, "id": 1, "title": 1})}
        async for r in db.lumen_asset_reports.find(
                {"asset_id": {"$in": asset_ids}}, {"_id": 0}).sort("created_at", -1):
            out = _strip_mongo(r)
            out["asset_title"] = titles.get(r.get("asset_id"))
            items.append(out)
    return {"items": items}


@router.post("/operator/assets/{asset_id}/reports")
async def operator_submit_report(asset_id: str, payload: ReportIn, ctx=Depends(require_operator)):
    op = ctx["operator"]
    a = await db.lumen_assets.find_one({"id": asset_id, "operator_id": op["id"]}, {"_id": 0, "title": 1})
    if not a:
        raise HTTPException(status_code=403, detail="Це не ваш об'єкт")
    doc = {
        "id": f"rep-{uuid.uuid4().hex[:12]}", "asset_id": asset_id,
        "title": payload.title.strip(),
        "period_label": payload.period_label,
        "summary": payload.summary,
        "report_type": payload.report_type or "operational",
        "published": True, "created_by": _uid(ctx["user"]),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_asset_reports.insert_one(doc)
    await _operator_event(op["id"], "report", "info",
                          f"Подано звіт «{payload.title}» для {a.get('title')}", ctx["user"])
    return {"ok": True, "report": _strip_mongo(doc)}


@router.get("/operator/investors")
async def operator_investors(ctx=Depends(require_operator)):
    op = ctx["operator"]
    asset_ids = [a["id"] for a in await _managed_assets(op["id"])]
    agg: dict[str, dict] = {}
    if asset_ids:
        async for o in db.lumen_ownerships.find({"asset_id": {"$in": asset_ids}}):
            iid = o.get("investor_id")
            if not iid:
                continue
            row = agg.setdefault(iid, {"investor_id": iid, "amount_uah": 0.0,
                                       "units": 0.0, "assets": set()})
            row["amount_uah"] += float(o.get("amount_uah") or 0)
            row["units"] += float(o.get("units") or 0)
            row["assets"].add(o.get("asset_id"))
    items = []
    for iid, row in agg.items():
        u = await db.users.find_one({"user_id": iid}, {"_id": 0, "name": 1})
        items.append({
            "investor_id": iid, "name": (u or {}).get("name") or "Інвестор",
            "amount_uah": _round2(row["amount_uah"]), "units": round(row["units"], 2),
            "assets_count": len(row["assets"]),
        })
    items.sort(key=lambda x: x["amount_uah"], reverse=True)
    return {"items": items, "total_investors": len(items),
            "total_capital_uah": _round2(sum(i["amount_uah"] for i in items))}


@router.get("/operator/sla")
async def operator_sla(ctx=Depends(require_operator)):
    return await _operator_sla(ctx["operator"]["id"])


@router.get("/operator/kpi")
async def operator_kpi(ctx=Depends(require_operator)):
    return await _operator_kpi(ctx["operator"]["id"])


@router.get("/operator/dealflow")
async def operator_dealflow(ctx=Depends(require_operator)):
    return await _operator_dealflow(ctx["operator"]["id"])


@router.get("/operator/fees")
async def operator_fees(ctx=Depends(require_operator)):
    op = ctx["operator"]
    kpi = await _operator_kpi(op["id"])
    return _fees_preview(op, kpi)


# ════════════════════════════════════════════════════════════════════════════
# Indexes + idempotent demo seed
# ════════════════════════════════════════════════════════════════════════════

async def ensure_operator_indexes() -> None:
    try:
        await db.lumen_operators.create_index([("user_id", 1)])
        await db.lumen_operators.create_index([("status", 1)])
        await db.lumen_operator_documents.create_index([("operator_id", 1)])
        await db.lumen_operator_events.create_index([("operator_id", 1), ("created_at", -1)])
        await db.lumen_assets.create_index([("operator_id", 1)])
    except Exception:
        logger.exception("operator indexes failed")


async def seed_operator_os_demo() -> dict:
    """Idempotent. Enrich operators, assign real assets, create operator user."""
    await ensure_operator_indexes()
    stats = {"profiles": 0, "assigned": 0, "operator_user": 0, "documents": 0}

    ops = []
    async for op in db.lumen_operators.find({}, {"_id": 0}).sort("created_at", 1):
        ops.append(op)
    if not ops:
        return stats

    by_name = {o.get("name"): o for o in ops}
    lumen_cap = by_name.get("LUMEN Capital") or ops[0]
    podil = by_name.get("Podil Development Partners") or (ops[1] if len(ops) > 1 else ops[0])
    west = by_name.get("West Logistics Operator") or (ops[2] if len(ops) > 2 else ops[0])

    # F1/F2/F9 — enrich profiles only if not yet enriched (no 'status' field)
    enrich = {
        lumen_cap["id"]: {
            "status": "approved", "years_active": 6, "team_size": 24,
            "website": "https://lumen.capital", "logo_url": None,
            "description": "Внутрішній операційний підрозділ LUMEN. Керує флагманськими об'єктами.",
            "fees": {"management_fee_pct": 1.5, "success_fee_pct": 8, "performance_fee_pct": 15,
                     "notes": "Внутрішній тариф"},
        },
        podil["id"]: {
            "status": "verified", "years_active": 9, "team_size": 12,
            "website": "https://podil.dev",
            "description": "Девелопер житлової та комерційної нерухомості на Подолі. 9 років на ринку.",
            "fees": {"management_fee_pct": 2.0, "success_fee_pct": 10, "performance_fee_pct": 20,
                     "notes": "Стандартний партнерський тариф"},
        },
        west["id"]: {
            "status": "applied", "years_active": 4, "team_size": 7,
            "website": "https://westlog.ua",
            "description": "Оператор складської логістики у Західному регіоні.",
            "fees": {"management_fee_pct": 2.5, "success_fee_pct": 12, "performance_fee_pct": 20},
        },
    }
    for op in ops:
        if op.get("status"):
            continue
        patch = enrich.get(op["id"])
        if patch:
            patch["updated_at"] = _now()
            await db.lumen_operators.update_one({"id": op["id"]}, {"$set": patch})
            stats["profiles"] += 1

    # F1 documents (idempotent)
    if await db.lumen_operator_documents.count_documents({}) == 0:
        for op_id, docs in {
            podil["id"]: [("Витяг з ЄДР", "registration"), ("Ліцензія девелопера", "license"),
                          ("Аудит фінзвітності 2024", "audit")],
            lumen_cap["id"]: [("Статут LUMEN Capital", "registration")],
        }.items():
            for title, kind in docs:
                await db.lumen_operator_documents.insert_one({
                    "id": f"od-{uuid.uuid4().hex[:12]}", "operator_id": op_id,
                    "title": title, "kind": kind, "url": None, "status": "verified",
                    "created_at": _now()})
                stats["documents"] += 1

    # F3/F4 — assign real assets to operators (only if not yet assigned)
    assignment = {
        "asset-podilskyi": podil["id"],
        "asset-stoyanka-land": podil["id"],
        "asset-odessa-apartments": podil["id"],
        "asset-lavr-tc": lumen_cap["id"],
        "asset-vyshneve-cottage": lumen_cap["id"],
        "asset-rivne-warehouse": west["id"],
    }
    for asset_id, op_id in assignment.items():
        a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "id": 1, "operator_id": 1})
        if a is not None and not a.get("operator_id"):
            await db.lumen_assets.update_one(
                {"id": asset_id}, {"$set": {"operator_id": op_id, "updated_at": _now()}})
            stats["assigned"] += 1

    # F10 — operator user linked to Podil (manages assets with reports + payouts)
    existing_user = await db.users.find_one({"email": "operator@atlas.dev"}, {"_id": 0, "user_id": 1})
    if not existing_user:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": uid, "email": "operator@atlas.dev", "name": "Podil Operator",
            "password_hash": _hash_pw("operator123"),
            "role": "operator", "roles": ["operator"], "states": ["operator"],
            "created_at": _now(), "updated_at": _now(),
        })
        await db.lumen_operators.update_one({"id": podil["id"]}, {"$set": {"user_id": uid}})
        stats["operator_user"] = 1
    elif not podil.get("user_id"):
        uid = existing_user.get("user_id")
        await db.lumen_operators.update_one({"id": podil["id"]}, {"$set": {"user_id": uid}})

    # ── MERGED ROLE — manager = manager + operator (single unified cabinet) ──
    # One login operates BOTH the Investor-Relations surface (require_staff) and
    # the Operator portal (linkage-based require_operator). We point the richest
    # operator (Podil) at this account so its Assets/Reports/SLA/Fees show data.
    mgr = await db.users.find_one({"email": "manager@atlas.dev"}, {"_id": 0, "user_id": 1})
    if not mgr:
        mgr_uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": mgr_uid, "email": "manager@atlas.dev", "name": "Lumen Manager",
            "password_hash": _hash_pw("manager123"),
            "role": "manager", "roles": ["manager", "operator"], "states": ["manager", "operator"],
            "created_at": _now(), "updated_at": _now(),
        })
        stats["manager_user"] = 1
    else:
        mgr_uid = mgr.get("user_id")
        await db.users.update_one(
            {"email": "manager@atlas.dev"},
            {"$set": {"role": "manager", "roles": ["manager", "operator"],
                      "states": ["manager", "operator"],
                      "password_hash": _hash_pw("manager123"), "updated_at": _now()},
             "$unset": {"totp_secret": "", "two_factor_enabled": ""}})
    # Link the merged manager to the Podil operator (single source of operator data).
    await db.lumen_operators.update_one({"id": podil["id"]}, {"$set": {"user_id": mgr_uid}})

    # ── DEMO ACCESS — admin + investor demo accounts (power the /auth demo chips
    #    and /api/auth/quick session creation). Idempotent: upsert role on each boot.
    for demo_email, demo_name, demo_role, demo_roles, demo_pw in [
        ("admin@atlas.dev", "Lumen Admin", "admin", ["admin"], "admin123"),
        ("client@atlas.dev", "Demo Investor", "client", ["client"], "client123"),
    ]:
        existing = await db.users.find_one({"email": demo_email}, {"_id": 0, "user_id": 1})
        if not existing:
            await db.users.insert_one({
                "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": demo_email, "name": demo_name,
                "password_hash": _hash_pw(demo_pw),
                "role": demo_role, "roles": demo_roles, "states": demo_roles,
                "created_at": _now(), "updated_at": _now(),
            })
            stats[f"demo_{demo_role}_user"] = 1
        else:
            await db.users.update_one(
                {"email": demo_email},
                {"$set": {"role": demo_role, "roles": demo_roles, "states": demo_roles,
                          "name": demo_name, "password_hash": _hash_pw(demo_pw), "updated_at": _now()}})

    # initial SLA + governance pass so events exist on a fresh DB
    try:
        await run_sla_scan()
        await run_governance_scan()
    except Exception:
        logger.exception("operator initial scans failed")

    return stats
