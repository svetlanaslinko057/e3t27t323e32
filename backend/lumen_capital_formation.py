"""
LUMEN 2.0 — Phase E — Capital Formation OS
==========================================

The growth engine of the platform. Phases A–D taught LUMEN to *manage*
ownership, intelligence, community and liquidity. Phase E teaches it to
*originate* — how new assets enter the system, get screened, approved,
raise capital, allocate when oversubscribed, and scale the funnel.

Everything DERIVES from real collections — no mocks. The capital-raise
progress reuses real `lumen_assets` round targets and `lumen_investments`,
so nothing here re-implements settlement.

Blocks
------
  E1  Deal Pipeline        — `deal` entity; Lead→Screening→DD→Committee→
                             Funding→Live→Operating→Exited (+Rejected) + audit trail
  E2  Investment Committee — memo · risk review · financial review · votes · decision
  E3  Data Room            — financial model / valuation / contracts / photos /
                             reports / DD, gated Public / Investor / Admin
  E4  Capital Raise Engine — soft / hard / reservation commitments + funding progress
  E5  Waitlist             — join when oversubscribed → auto-notify when capacity frees
  E6  Investor Segments    — Retail / Qualified / Strategic / Institutional
  E7  Capital Velocity     — KPI: days to close a round
  E8  Allocation Engine    — oversubscribed allocation: first_come / pro_rata / priority
  E9  Pipeline Analytics   — funnel counts · rejection reasons · time-in-stage · velocity
  E10 Operator Marketplace — operators (internal / external / partner) sourcing deals

Forbidden (per product owner): crypto, tokenization, blockchain, wallet-connect.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin, _strip_mongo,
                       _now, _iso, lr2_perm as _lr2_perm)

try:
    from lumen_payments import _round2, BASE_CURRENCY
except Exception:  # pragma: no cover - defensive
    BASE_CURRENCY = "UAH"

    def _round2(v: float) -> float:
        return round(float(v or 0), 2)

logger = logging.getLogger("lumen.capital")

router = APIRouter(prefix="/api", tags=["lumen-capital"])

# ── Domain constants ─────────────────────────────────────────────────────────
DEAL_STAGES = (
    "lead", "screening", "due_diligence", "committee",
    "funding", "live", "operating", "exited", "rejected",
)
STAGE_LABELS_UK = {
    "lead": "Лід",
    "screening": "Скринінг",
    "due_diligence": "Due Diligence",
    "committee": "Комітет",
    "funding": "Збір капіталу",
    "live": "Активний",
    "operating": "В управлінні",
    "exited": "Вихід",
    "rejected": "Відхилено",
}
# Forward flow used for funnel/velocity ordering
STAGE_ORDER = {s: i for i, s in enumerate(
    ("lead", "screening", "due_diligence", "committee",
     "funding", "live", "operating", "exited"))}

COMMITMENT_KINDS = ("soft", "hard", "reservation")
COMMITMENT_STATUSES = ("pending", "confirmed", "allocated", "converted", "cancelled")

DATAROOM_CATEGORIES = (
    "financial_model", "valuation", "contracts", "photos",
    "reports", "due_diligence", "other",
)
DATAROOM_VISIBILITY = ("public", "investor", "admin")

SEGMENTS = ("retail", "qualified", "strategic", "institutional")
SEGMENT_RANK = {"institutional": 4, "strategic": 3, "qualified": 2, "retail": 1}
SEGMENT_LABELS_UK = {
    "retail": "Роздрібний",
    "qualified": "Кваліфікований",
    "strategic": "Стратегічний",
    "institutional": "Інституційний",
}
# Auto-segment thresholds by total invested (UAH)
SEGMENT_THRESHOLDS = [
    (2_000_000, "institutional"),
    (500_000, "strategic"),
    (100_000, "qualified"),
    (0, "retail"),
]

OPERATOR_KINDS = ("internal", "external", "partner")
ALLOCATION_POLICIES = ("first_come", "pro_rata", "priority")


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _uid(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    return user.get("user_id") or user.get("id")


def _uname(user: Optional[dict]) -> str:
    if not user:
        return "—"
    return user.get("name") or user.get("email") or "—"


def _is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return "admin" in (user.get("roles") or []) or "admin" in (user.get("states") or [])


async def _optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def _asset_or_404(asset_id: str) -> dict:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return a


async def _deal_or_404(deal_id: str) -> dict:
    d = await db.lumen_deals.find_one({"id": deal_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Сделку не знайдено")
    return d


def _round_target(asset: dict) -> float:
    return float(asset.get("round_target") or asset.get("target_amount")
                 or asset.get("target") or 0)


async def _raised_real_uah(asset_id: str) -> float:
    """Confirmed primary-market capital already raised (real investments)."""
    total = 0.0
    async for inv in db.lumen_investments.find({"asset_id": asset_id}):
        st = (inv.get("status") or "").lower()
        if st in ("cancelled", "rejected", "failed", "refunded"):
            continue
        total += float(inv.get("amount") or inv.get("invested_amount") or 0)
    return _round2(total)


async def _commit_sums(asset_id: str) -> dict:
    """Sum live commitments by kind (pending/confirmed/allocated count as demand)."""
    out = {"soft": 0.0, "hard": 0.0, "reservation": 0.0}
    async for c in db.lumen_commitments.find(
            {"asset_id": asset_id,
             "status": {"$in": ["pending", "confirmed", "allocated"]}}):
        k = c.get("kind")
        if k in out:
            out[k] += float(c.get("amount_uah") or 0)
    return {k: _round2(v) for k, v in out.items()}


async def _total_invested(investor_id: str) -> float:
    total = 0.0
    async for inv in db.lumen_investments.find({"investor_id": investor_id}):
        st = (inv.get("status") or "").lower()
        if st in ("cancelled", "rejected", "failed", "refunded"):
            continue
        total += float(inv.get("amount") or inv.get("invested_amount") or 0)
    return _round2(total)


def _auto_segment(invested_uah: float) -> str:
    for threshold, seg in SEGMENT_THRESHOLDS:
        if invested_uah >= threshold:
            return seg
    return "retail"


async def _investor_segment(user_id: str) -> dict:
    """Returns {segment, source: override|auto, invested_uah}."""
    prof = await db.lumen_investor_profiles.find_one(
        {"user_id": user_id}, {"_id": 0, "segment": 1, "segment_override": 1})
    invested = await _total_invested(user_id)
    auto = _auto_segment(invested)
    override = (prof or {}).get("segment_override")
    seg = (prof or {}).get("segment")
    if override and seg in SEGMENTS:
        return {"segment": seg, "source": "override", "invested_uah": invested}
    return {"segment": auto, "source": "auto", "invested_uah": invested}


async def _notify(investor_id: str, title: str, body: str) -> None:
    try:
        await db.lumen_notifications.insert_one({
            "id": f"ntf-{uuid.uuid4().hex[:12]}",
            "investor_id": investor_id,
            "title": title, "body": body,
            "read": False, "created_at": _now(),
        })
    except Exception:
        logger.exception("notify failed for %s", investor_id)


async def _deal_event(deal_id: str, kind: str, actor: Optional[dict],
                      detail: dict | None = None) -> None:
    await db.lumen_deal_events.insert_one({
        "id": f"de-{uuid.uuid4().hex[:12]}",
        "deal_id": deal_id, "kind": kind,
        "actor_id": _uid(actor), "actor_name": _uname(actor),
        "detail": detail or {}, "created_at": _now(),
    })


# ════════════════════════════════════════════════════════════════════════════
# Pydantic payloads
# ════════════════════════════════════════════════════════════════════════════

class DealIn(BaseModel):
    title: str
    source: Optional[str] = None
    owner_name: Optional[str] = None
    region: Optional[str] = None
    asset_type: Optional[str] = None
    asking_price_uah: Optional[float] = 0
    team_valuation_uah: Optional[float] = 0
    description: Optional[str] = None
    operator_id: Optional[str] = None
    linked_asset_id: Optional[str] = None


class DealPatch(BaseModel):
    title: Optional[str] = None
    source: Optional[str] = None
    owner_name: Optional[str] = None
    region: Optional[str] = None
    asset_type: Optional[str] = None
    asking_price_uah: Optional[float] = None
    team_valuation_uah: Optional[float] = None
    description: Optional[str] = None
    operator_id: Optional[str] = None
    linked_asset_id: Optional[str] = None


class TransitionIn(BaseModel):
    to_stage: str
    note: Optional[str] = None


class RejectIn(BaseModel):
    reason: str


class ReviewIn(BaseModel):
    summary: Optional[str] = None
    rating: Optional[str] = None     # low|medium|high  (risk) or weak|fair|strong (fin)
    fields: Optional[dict] = None    # memo fields {opportunity, market, financials, exit, recommendation}


class VoteIn(BaseModel):
    vote: str                        # approve|reject|abstain
    comment: Optional[str] = None


class DecisionIn(BaseModel):
    decision: str                    # approved|rejected
    note: Optional[str] = None


class DataRoomIn(BaseModel):
    deal_id: Optional[str] = None
    asset_id: Optional[str] = None
    category: str = "other"
    title: str
    url: Optional[str] = None
    file_name: Optional[str] = None
    visibility: str = "admin"
    size: Optional[int] = None


class CommitmentIn(BaseModel):
    asset_id: str
    amount_uah: float = Field(gt=0)
    kind: str = "soft"               # soft|hard|reservation
    deal_id: Optional[str] = None


class WaitlistIn(BaseModel):
    amount_uah: float = Field(gt=0)


class SegmentIn(BaseModel):
    segment: str
    override: bool = True


class AllocateIn(BaseModel):
    policy: str = "pro_rata"
    capacity_uah: Optional[float] = None  # default = remaining of round target


class OperatorIn(BaseModel):
    name: str
    kind: str = "external"
    region: Optional[str] = None
    specialization: Optional[str] = None
    contact: Optional[str] = None
    active: bool = True


class OperatorPatch(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    region: Optional[str] = None
    specialization: Optional[str] = None
    contact: Optional[str] = None
    active: Optional[bool] = None


# ════════════════════════════════════════════════════════════════════════════
# E1 — Deal Pipeline
# ════════════════════════════════════════════════════════════════════════════

def _deal_label(d: dict) -> dict:
    d = _strip_mongo(dict(d))
    d["stage_label"] = STAGE_LABELS_UK.get(d.get("stage"), d.get("stage"))
    return d


@router.get("/admin/deals")
async def list_deals(stage: Optional[str] = None, operator_id: Optional[str] = None,
                     _=Depends(require_admin)):
    q: dict = {}
    if stage:
        q["stage"] = stage
    if operator_id:
        q["operator_id"] = operator_id
    items = []
    async for d in db.lumen_deals.find(q, {"_id": 0}).sort("created_at", -1):
        items.append(_deal_label(d))
    # group counts by stage for board headers
    counts = {s: 0 for s in DEAL_STAGES}
    async for d in db.lumen_deals.find({}, {"stage": 1}):
        s = d.get("stage")
        if s in counts:
            counts[s] += 1
    return {"items": items, "counts": counts, "stages": list(DEAL_STAGES),
            "stage_labels": STAGE_LABELS_UK}


@router.post("/admin/deals")
async def create_deal(payload: DealIn, admin=Depends(require_admin),
                       _perm=Depends(_lr2_perm("investment", "write"))):
    deal = {
        "id": f"deal-{uuid.uuid4().hex[:12]}",
        "title": payload.title.strip(),
        "source": payload.source or "manual",
        "owner_name": payload.owner_name,
        "region": payload.region,
        "asset_type": payload.asset_type,
        "asking_price_uah": _round2(payload.asking_price_uah or 0),
        "team_valuation_uah": _round2(payload.team_valuation_uah or 0),
        "description": payload.description,
        "operator_id": payload.operator_id,
        "linked_asset_id": payload.linked_asset_id,
        "stage": "lead",
        "rejection_reason": None,
        "committee": {"memo": {}, "risk_review": {}, "financial_review": {},
                      "decision": None, "decided_at": None},
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_deals.insert_one(deal)
    await _deal_event(deal["id"], "created", admin, {"stage": "lead"})
    return _deal_label(deal)


@router.get("/admin/deals/{deal_id}")
async def get_deal(deal_id: str, _=Depends(require_admin)):
    d = await _deal_or_404(deal_id)
    events = []
    async for e in db.lumen_deal_events.find({"deal_id": deal_id}, {"_id": 0}).sort("created_at", -1):
        events.append(_strip_mongo(e))
    votes = []
    async for v in db.lumen_committee_votes.find({"deal_id": deal_id}, {"_id": 0}):
        votes.append(_strip_mongo(v))
    dataroom_n = await db.lumen_data_room.count_documents({"deal_id": deal_id})
    out = _deal_label(d)
    out["events"] = events
    out["votes"] = votes
    out["dataroom_count"] = dataroom_n
    if d.get("linked_asset_id"):
        a = await db.lumen_assets.find_one({"id": d["linked_asset_id"]}, {"_id": 0, "title": 1})
        out["linked_asset_title"] = (a or {}).get("title")
    if d.get("operator_id"):
        op = await db.lumen_operators.find_one({"id": d["operator_id"]}, {"_id": 0, "name": 1})
        out["operator_name"] = (op or {}).get("name")
    return out


@router.patch("/admin/deals/{deal_id}")
async def update_deal(deal_id: str, payload: DealPatch, admin=Depends(require_admin)):
    await _deal_or_404(deal_id)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "asking_price_uah" in upd:
        upd["asking_price_uah"] = _round2(upd["asking_price_uah"])
    if "team_valuation_uah" in upd:
        upd["team_valuation_uah"] = _round2(upd["team_valuation_uah"])
    upd["updated_at"] = _now()
    await db.lumen_deals.update_one({"id": deal_id}, {"$set": upd})
    await _deal_event(deal_id, "updated", admin, {"fields": list(upd.keys())})
    return await get_deal(deal_id, _=admin)


@router.post("/admin/deals/{deal_id}/transition")
async def transition_deal(deal_id: str, payload: TransitionIn, admin=Depends(require_admin),
                           _perm=Depends(_lr2_perm("investment", "approve"))):
    d = await _deal_or_404(deal_id)
    if payload.to_stage not in DEAL_STAGES:
        raise HTTPException(status_code=400, detail="Невідома стадія")
    if payload.to_stage == "rejected":
        raise HTTPException(status_code=400, detail="Використайте /reject для відхилення")
    prev = d.get("stage")
    await db.lumen_deals.update_one(
        {"id": deal_id},
        {"$set": {"stage": payload.to_stage, "updated_at": _now()}})
    await _deal_event(deal_id, "stage_change", admin,
                      {"from": prev, "to": payload.to_stage, "note": payload.note})
    # IR0.3 — field-level history: round/deal stage transition.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="round", entity_id=deal_id,
            field="status", old_value=prev, new_value=payload.to_stage,
            actor=admin, source="api", reason=(payload.note or None),
        )
    except Exception:
        pass
    return await get_deal(deal_id, _=admin)


@router.post("/admin/deals/{deal_id}/reject")
async def reject_deal(deal_id: str, payload: RejectIn, admin=Depends(require_admin),
                       _perm=Depends(_lr2_perm("investment", "approve"))):
    d = await _deal_or_404(deal_id)
    prev = d.get("stage")
    await db.lumen_deals.update_one(
        {"id": deal_id},
        {"$set": {"stage": "rejected", "rejection_reason": payload.reason.strip(),
                  "updated_at": _now()}})
    await _deal_event(deal_id, "rejected", admin, {"from": prev, "reason": payload.reason})
    # IR0.3 — field-level history: round/deal rejected.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="round", entity_id=deal_id,
            field="status", old_value=prev, new_value="rejected",
            actor=admin, source="api", reason=(payload.reason or None),
        )
    except Exception:
        pass
    return await get_deal(deal_id, _=admin)


@router.get("/admin/deals/{deal_id}/events")
async def deal_events(deal_id: str, _=Depends(require_admin)):
    await _deal_or_404(deal_id)
    items = []
    async for e in db.lumen_deal_events.find({"deal_id": deal_id}, {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(e))
    return {"items": items}


@router.delete("/admin/deals/{deal_id}")
async def delete_deal(deal_id: str, _=Depends(require_admin)):
    await _deal_or_404(deal_id)
    await db.lumen_deals.delete_one({"id": deal_id})
    await db.lumen_deal_events.delete_many({"deal_id": deal_id})
    await db.lumen_committee_votes.delete_many({"deal_id": deal_id})
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
# E2 — Investment Committee
# ════════════════════════════════════════════════════════════════════════════

@router.put("/admin/deals/{deal_id}/memo")
async def save_memo(deal_id: str, payload: ReviewIn, admin=Depends(require_admin)):
    await _deal_or_404(deal_id)
    memo = payload.fields or {}
    await db.lumen_deals.update_one(
        {"id": deal_id}, {"$set": {"committee.memo": memo, "updated_at": _now()}})
    await _deal_event(deal_id, "memo_saved", admin, {})
    return {"ok": True, "memo": memo}


@router.put("/admin/deals/{deal_id}/risk-review")
async def save_risk_review(deal_id: str, payload: ReviewIn, admin=Depends(require_admin)):
    await _deal_or_404(deal_id)
    rr = {"summary": payload.summary, "rating": payload.rating or "medium"}
    await db.lumen_deals.update_one(
        {"id": deal_id}, {"$set": {"committee.risk_review": rr, "updated_at": _now()}})
    await _deal_event(deal_id, "risk_review_saved", admin, {"rating": rr["rating"]})
    return {"ok": True, "risk_review": rr}


@router.put("/admin/deals/{deal_id}/financial-review")
async def save_financial_review(deal_id: str, payload: ReviewIn, admin=Depends(require_admin)):
    await _deal_or_404(deal_id)
    fr = {"summary": payload.summary, "rating": payload.rating or "fair"}
    await db.lumen_deals.update_one(
        {"id": deal_id}, {"$set": {"committee.financial_review": fr, "updated_at": _now()}})
    await _deal_event(deal_id, "financial_review_saved", admin, {"rating": fr["rating"]})
    return {"ok": True, "financial_review": fr}


@router.post("/admin/deals/{deal_id}/vote")
async def cast_vote(deal_id: str, payload: VoteIn, admin=Depends(require_admin)):
    await _deal_or_404(deal_id)
    if payload.vote not in ("approve", "reject", "abstain"):
        raise HTTPException(status_code=400, detail="vote ∈ approve|reject|abstain")
    uid = _uid(admin)
    existing = await db.lumen_committee_votes.find_one({"deal_id": deal_id, "voter_id": uid})
    doc = {
        "deal_id": deal_id, "voter_id": uid, "voter_name": _uname(admin),
        "vote": payload.vote, "comment": payload.comment, "created_at": _now(),
    }
    if existing:
        await db.lumen_committee_votes.update_one(
            {"deal_id": deal_id, "voter_id": uid}, {"$set": doc})
    else:
        doc["id"] = f"cv-{uuid.uuid4().hex[:12]}"
        await db.lumen_committee_votes.insert_one(doc)
    await _deal_event(deal_id, "vote", admin, {"vote": payload.vote})
    return await committee_view(deal_id, _=admin)


@router.get("/admin/deals/{deal_id}/committee")
async def committee_view(deal_id: str, _=Depends(require_admin)):
    d = await _deal_or_404(deal_id)
    committee = d.get("committee") or {}
    votes = []
    tally = {"approve": 0, "reject": 0, "abstain": 0}
    async for v in db.lumen_committee_votes.find({"deal_id": deal_id}, {"_id": 0}).sort("created_at", 1):
        votes.append(_strip_mongo(v))
        if v.get("vote") in tally:
            tally[v["vote"]] += 1
    recommended = None
    decided = tally["approve"] + tally["reject"]
    if decided > 0:
        recommended = "approved" if tally["approve"] > tally["reject"] else (
            "rejected" if tally["reject"] > tally["approve"] else "tie")
    return {
        "deal_id": deal_id,
        "memo": committee.get("memo") or {},
        "risk_review": committee.get("risk_review") or {},
        "financial_review": committee.get("financial_review") or {},
        "votes": votes, "tally": tally, "recommended": recommended,
        "decision": committee.get("decision"),
        "decided_at": _iso(committee.get("decided_at")),
    }


@router.post("/admin/deals/{deal_id}/decision")
async def finalize_decision(deal_id: str, payload: DecisionIn, admin=Depends(require_admin),
                             _perm=Depends(_lr2_perm("investment", "approve"))):
    d = await _deal_or_404(deal_id)
    if payload.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision ∈ approved|rejected")
    set_doc = {"committee.decision": payload.decision,
               "committee.decided_at": _now(), "updated_at": _now()}
    if payload.decision == "approved":
        set_doc["stage"] = "funding"
    else:
        set_doc["stage"] = "rejected"
        set_doc["rejection_reason"] = payload.note or "Відхилено комітетом"
    await db.lumen_deals.update_one({"id": deal_id}, {"$set": set_doc})
    await _deal_event(deal_id, "decision", admin,
                      {"decision": payload.decision, "note": payload.note})
    return await get_deal(deal_id, _=admin)


# ════════════════════════════════════════════════════════════════════════════
# E3 — Data Room
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/dataroom")
async def admin_dataroom(deal_id: Optional[str] = None, asset_id: Optional[str] = None,
                         _=Depends(require_admin)):
    q: dict = {}
    if deal_id:
        q["deal_id"] = deal_id
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    async for it in db.lumen_data_room.find(q, {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(it))
    return {"items": items, "categories": list(DATAROOM_CATEGORIES),
            "visibility": list(DATAROOM_VISIBILITY)}


@router.post("/admin/dataroom")
async def add_dataroom(payload: DataRoomIn, admin=Depends(require_admin)):
    if payload.category not in DATAROOM_CATEGORIES:
        raise HTTPException(status_code=400, detail="Невідома категорія")
    if payload.visibility not in DATAROOM_VISIBILITY:
        raise HTTPException(status_code=400, detail="Невідомий рівень доступу")
    if not payload.deal_id and not payload.asset_id:
        raise HTTPException(status_code=400, detail="Вкажіть deal_id або asset_id")
    doc = {
        "id": f"dr-{uuid.uuid4().hex[:12]}",
        "deal_id": payload.deal_id, "asset_id": payload.asset_id,
        "category": payload.category, "title": payload.title.strip(),
        "url": payload.url, "file_name": payload.file_name,
        "visibility": payload.visibility, "size": payload.size,
        "uploaded_by": _uid(admin), "created_at": _now(),
    }
    await db.lumen_data_room.insert_one(doc)
    return _strip_mongo(doc)


@router.delete("/admin/dataroom/{item_id}")
async def delete_dataroom(item_id: str, _=Depends(require_admin)):
    res = await db.lumen_data_room.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    return {"ok": True}


@router.get("/assets/{asset_id}/dataroom")
async def asset_dataroom(asset_id: str, request: Request):
    """Gated read. anon → public; investor → public+investor; admin → all."""
    await _asset_or_404(asset_id)
    user = await _optional_user(request)
    if _is_admin(user):
        allowed = list(DATAROOM_VISIBILITY)
    elif user:
        allowed = ["public", "investor"]
    else:
        allowed = ["public"]
    items = []
    async for it in db.lumen_data_room.find(
            {"asset_id": asset_id, "visibility": {"$in": allowed}},
            {"_id": 0}).sort("created_at", -1):
        items.append(_strip_mongo(it))
    return {"items": items, "access_level": ("admin" if _is_admin(user)
            else "investor" if user else "public")}


# ════════════════════════════════════════════════════════════════════════════
# E4 — Capital Raise Engine + funding progress
# ════════════════════════════════════════════════════════════════════════════

async def _raise_bundle(asset_id: str) -> dict:
    a = await _asset_or_404(asset_id)
    target = _round_target(a)
    raised = await _raised_real_uah(asset_id)
    sums = await _commit_sums(asset_id)
    # committed capital = hard + reservation (binding); soft = interest only
    committed = _round2(sums["hard"] + sums["reservation"])
    total_demand = _round2(raised + committed)
    remaining = _round2(max(0.0, target - raised))
    progress_pct = _round2((raised / target * 100) if target else 0)
    demand_pct = _round2((total_demand / target * 100) if target else 0)
    oversubscription_pct = _round2(max(0.0, demand_pct - 100))
    waitlist_n = await db.lumen_waitlist.count_documents(
        {"asset_id": asset_id, "status": {"$in": ["waiting", "notified"]}})
    commit_n = await db.lumen_commitments.count_documents(
        {"asset_id": asset_id, "status": {"$in": ["pending", "confirmed", "allocated"]}})
    return {
        "asset_id": asset_id, "asset_title": a.get("title"),
        "currency": BASE_CURRENCY,
        "target_uah": target, "raised_uah": raised,
        "soft_uah": sums["soft"], "hard_uah": sums["hard"],
        "reservation_uah": sums["reservation"], "committed_uah": committed,
        "total_demand_uah": total_demand, "remaining_uah": remaining,
        "progress_pct": progress_pct, "demand_pct": demand_pct,
        "oversubscription_pct": oversubscription_pct,
        "oversubscribed": demand_pct > 100,
        "fully_funded": raised >= target > 0,
        "commitments_count": commit_n, "waitlist_count": waitlist_n,
    }


@router.post("/investor/commitments")
async def create_commitment(payload: CommitmentIn, user=Depends(get_current_user)):
    await _asset_or_404(payload.asset_id)
    if payload.kind not in COMMITMENT_KINDS:
        raise HTTPException(status_code=400, detail="kind ∈ soft|hard|reservation")
    uid = _uid(user)
    seg = await _investor_segment(uid)
    doc = {
        "id": f"cm-{uuid.uuid4().hex[:12]}",
        "asset_id": payload.asset_id, "deal_id": payload.deal_id,
        "investor_id": uid, "investor_name": _uname(user),
        "amount_uah": _round2(payload.amount_uah), "kind": payload.kind,
        "status": "pending", "segment": seg["segment"],
        "allocated_uah": 0.0,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_commitments.insert_one(doc)
    return {"ok": True, "commitment": _strip_mongo(doc),
            "raise": await _raise_bundle(payload.asset_id)}


@router.get("/investor/commitments")
async def my_commitments(user=Depends(get_current_user)):
    uid = _uid(user)
    items = []
    async for c in db.lumen_commitments.find({"investor_id": uid}, {"_id": 0}).sort("created_at", -1):
        out = _strip_mongo(c)
        a = await db.lumen_assets.find_one({"id": c["asset_id"]}, {"_id": 0, "title": 1, "category": 1})
        out["asset_title"] = (a or {}).get("title")
        out["category"] = (a or {}).get("category")
        items.append(out)
    return {"items": items}


@router.post("/investor/commitments/{commit_id}/cancel")
async def cancel_commitment(commit_id: str, user=Depends(get_current_user)):
    c = await db.lumen_commitments.find_one({"id": commit_id})
    if not c:
        raise HTTPException(status_code=404, detail="Зобов'язання не знайдено")
    if c.get("investor_id") != _uid(user) and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Лише автор може скасувати")
    if c.get("status") in ("cancelled", "converted"):
        raise HTTPException(status_code=409, detail=f"Статус: {c.get('status')}")
    await db.lumen_commitments.update_one(
        {"id": commit_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}})
    # capacity may have freed → notify waitlist
    await _promote_waitlist(c["asset_id"])
    return {"ok": True}


@router.get("/assets/{asset_id}/raise-progress")
async def public_raise_progress(asset_id: str):
    return await _raise_bundle(asset_id)


@router.get("/admin/assets/{asset_id}/raise")
async def admin_raise(asset_id: str, _=Depends(require_admin)):
    bundle = await _raise_bundle(asset_id)
    commitments = []
    async for c in db.lumen_commitments.find({"asset_id": asset_id}, {"_id": 0}).sort("created_at", 1):
        commitments.append(_strip_mongo(c))
    bundle["commitments"] = commitments
    return bundle


# ════════════════════════════════════════════════════════════════════════════
# E5 — Waitlist
# ════════════════════════════════════════════════════════════════════════════

async def _waitlist_positions(asset_id: str) -> list[dict]:
    items = []
    async for w in db.lumen_waitlist.find(
            {"asset_id": asset_id}, {"_id": 0}).sort("created_at", 1):
        items.append(_strip_mongo(w))
    # assign positions among active entries (preserve segment priority then time)
    active = [w for w in items if w.get("status") in ("waiting", "notified")]
    active.sort(key=lambda w: (-SEGMENT_RANK.get(w.get("segment", "retail"), 1),
                               w.get("created_at") or _now()))
    pos_map = {w["id"]: i + 1 for i, w in enumerate(active)}
    for w in items:
        w["position"] = pos_map.get(w["id"])
    return items


async def _promote_waitlist(asset_id: str) -> dict:
    """Notify waitlisted investors when capacity frees up."""
    bundle = await _raise_bundle(asset_id)
    remaining = bundle["remaining_uah"]
    if remaining <= 0:
        return {"notified": 0, "remaining_uah": remaining}
    notified = 0
    capacity = remaining
    entries = await _waitlist_positions(asset_id)
    waiting = [w for w in entries if w.get("status") == "waiting"]
    for w in waiting:
        if capacity <= 0:
            break
        await db.lumen_waitlist.update_one(
            {"id": w["id"]},
            {"$set": {"status": "notified", "notified_at": _now()}})
        await _notify(
            w["investor_id"],
            "Звільнилось місце в раунді",
            f"У об'єкті «{bundle['asset_title']}» звільнилось місце. "
            f"Ви можете оформити зобов'язання на суму до {fmt_uah_as_usd(w.get('amount_uah'))}.")
        notified += 1
        capacity -= float(w.get("amount_uah") or 0)
    return {"notified": notified, "remaining_uah": remaining}


@router.post("/investor/waitlist/{asset_id}")
async def join_waitlist(asset_id: str, payload: WaitlistIn, user=Depends(get_current_user)):
    await _asset_or_404(asset_id)
    uid = _uid(user)
    seg = await _investor_segment(uid)
    existing = await db.lumen_waitlist.find_one({"asset_id": asset_id, "investor_id": uid})
    if existing and existing.get("status") in ("waiting", "notified"):
        await db.lumen_waitlist.update_one(
            {"id": existing["id"]},
            {"$set": {"amount_uah": _round2(payload.amount_uah),
                      "segment": seg["segment"], "updated_at": _now()}})
        return {"ok": True, "joined": True}
    doc = {
        "id": f"wl-{uuid.uuid4().hex[:12]}",
        "asset_id": asset_id, "investor_id": uid, "investor_name": _uname(user),
        "amount_uah": _round2(payload.amount_uah), "segment": seg["segment"],
        "status": "waiting", "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_waitlist.insert_one(doc)
    return {"ok": True, "joined": True}


@router.delete("/investor/waitlist/{asset_id}")
async def leave_waitlist(asset_id: str, user=Depends(get_current_user)):
    await db.lumen_waitlist.update_many(
        {"asset_id": asset_id, "investor_id": _uid(user)},
        {"$set": {"status": "cancelled", "updated_at": _now()}})
    return {"ok": True}


@router.get("/investor/waitlist")
async def my_waitlist(user=Depends(get_current_user)):
    uid = _uid(user)
    items = []
    async for w in db.lumen_waitlist.find({"investor_id": uid}, {"_id": 0}).sort("created_at", -1):
        if w.get("status") == "cancelled":
            continue
        positions = await _waitlist_positions(w["asset_id"])
        pos = next((p["position"] for p in positions if p["id"] == w["id"]), None)
        out = _strip_mongo(w)
        out["position"] = pos
        a = await db.lumen_assets.find_one({"id": w["asset_id"]}, {"_id": 0, "title": 1})
        out["asset_title"] = (a or {}).get("title")
        items.append(out)
    return {"items": items}


@router.get("/admin/assets/{asset_id}/waitlist")
async def admin_waitlist(asset_id: str, _=Depends(require_admin)):
    items = await _waitlist_positions(asset_id)
    return {"items": [w for w in items if w.get("status") != "cancelled"]}


@router.post("/admin/assets/{asset_id}/waitlist/notify")
async def admin_notify_waitlist(asset_id: str, _=Depends(require_admin)):
    await _asset_or_404(asset_id)
    res = await _promote_waitlist(asset_id)
    return res


# ════════════════════════════════════════════════════════════════════════════
# E6 — Investor Segments
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/capital/segments")
async def list_segments(_=Depends(require_admin)):
    counts = {s: 0 for s in SEGMENTS}
    items = []
    async for u in db.users.find(
            {"$or": [{"role": "client"}, {"roles": "client"}, {"role": "investor"}]},
            {"_id": 0, "user_id": 1, "id": 1, "email": 1, "name": 1}):
        uid = u.get("user_id") or u.get("id")
        if not uid:
            continue
        seg = await _investor_segment(uid)
        counts[seg["segment"]] = counts.get(seg["segment"], 0) + 1
        items.append({
            "user_id": uid, "email": u.get("email"), "name": u.get("name"),
            "segment": seg["segment"], "source": seg["source"],
            "invested_uah": seg["invested_uah"],
            "segment_label": SEGMENT_LABELS_UK.get(seg["segment"]),
        })
    items.sort(key=lambda x: x["invested_uah"], reverse=True)
    return {"items": items, "counts": counts, "segments": list(SEGMENTS),
            "segment_labels": SEGMENT_LABELS_UK}


@router.put("/admin/investors/{user_id}/segment")
async def set_segment(user_id: str, payload: SegmentIn, _=Depends(require_admin),
                       _perm=Depends(_lr2_perm("accreditation_profile", "override"))):
    if payload.segment not in SEGMENTS:
        raise HTTPException(status_code=400, detail="Невідомий сегмент")
    await db.lumen_investor_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"segment": payload.segment, "segment_override": bool(payload.override),
                  "updated_at": _now()},
         "$setOnInsert": {"id": f"prof-{uuid.uuid4().hex[:10]}", "user_id": user_id,
                          "created_at": _now()}},
        upsert=True)
    return await _investor_segment(user_id)


@router.put("/admin/investors/{user_id}/segment/auto")
async def reset_segment_auto(user_id: str, _=Depends(require_admin)):
    await db.lumen_investor_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"segment_override": False, "updated_at": _now()}})
    return await _investor_segment(user_id)


@router.get("/investor/segment")
async def get_my_segment(user=Depends(get_current_user)):
    seg = await _investor_segment(_uid(user))
    seg["segment_label"] = SEGMENT_LABELS_UK.get(seg["segment"])
    return seg


# ════════════════════════════════════════════════════════════════════════════
# E7 — Capital Velocity  (days to close a round)
# ════════════════════════════════════════════════════════════════════════════

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


@router.get("/admin/capital/velocity")
async def capital_velocity(_=Depends(require_admin)):
    per_asset = []
    closed_days = []
    async for r in db.lumen_investment_rounds.find({}, {"_id": 0}):
        opened = _as_dt(r.get("open_at")) or _as_dt(r.get("created_at"))
        closed = _as_dt(r.get("close_at"))
        status = (r.get("status") or "").lower()
        asset_id = r.get("asset_id")
        a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "title": 1}) if asset_id else None
        row = {
            "asset_id": asset_id, "asset_title": (a or {}).get("title"),
            "round_name": r.get("round_name"), "status": status,
            "target_uah": _round2(r.get("target_amount") or 0),
            "raised_uah": _round2(r.get("raised_amount") or 0),
        }
        if opened and closed and closed >= opened and status in ("closed", "funded", "completed", "settled"):
            days = round((closed - opened).total_seconds() / 86400.0, 1)
            row["days_to_close"] = days
            closed_days.append(days)
        elif opened:
            now = _now()
            row["days_elapsed"] = round((now - opened).total_seconds() / 86400.0, 1)
        per_asset.append(row)
    avg_days = round(sum(closed_days) / len(closed_days), 1) if closed_days else None
    return {
        "per_asset": per_asset,
        "avg_days_to_close": avg_days,
        "fastest_days": min(closed_days) if closed_days else None,
        "slowest_days": max(closed_days) if closed_days else None,
        "closed_rounds": len(closed_days),
    }


# ════════════════════════════════════════════════════════════════════════════
# E8 — Allocation Engine
# ════════════════════════════════════════════════════════════════════════════

def _largest_remainder(requests: list[float], capacity: float) -> list[float]:
    """Pro-rata allocation with largest-remainder rounding so Σ == capacity."""
    total = sum(requests)
    if total <= 0 or capacity <= 0:
        return [0.0 for _ in requests]
    if total <= capacity:
        return [round(r, 2) for r in requests]
    raw = [r * capacity / total for r in requests]
    floors = [int(x) for x in raw]
    allocated = list(floors)
    remainder = int(round(capacity)) - sum(floors)
    fracs = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i]), reverse=True)
    for i in range(max(0, remainder)):
        allocated[fracs[i % len(fracs)]] += 1
    return [float(x) for x in allocated]


@router.post("/admin/assets/{asset_id}/allocate")
async def run_allocation(asset_id: str, payload: AllocateIn, admin=Depends(require_admin)):
    a = await _asset_or_404(asset_id)
    if payload.policy not in ALLOCATION_POLICIES:
        raise HTTPException(status_code=400, detail="policy ∈ first_come|pro_rata|priority")
    target = _round_target(a)
    raised = await _raised_real_uah(asset_id)
    capacity = payload.capacity_uah if payload.capacity_uah is not None else max(0.0, target - raised)
    capacity = _round2(capacity)

    # binding demand = hard + reservation commitments still in play
    commits = []
    async for c in db.lumen_commitments.find(
            {"asset_id": asset_id, "kind": {"$in": ["hard", "reservation"]},
             "status": {"$in": ["pending", "confirmed", "allocated"]}}):
        commits.append(c)

    if not commits:
        raise HTTPException(status_code=400, detail="Немає зобов'язань для розподілу")

    # order per policy
    if payload.policy == "first_come":
        commits.sort(key=lambda c: c.get("created_at") or _now())
    elif payload.policy == "priority":
        commits.sort(key=lambda c: (-SEGMENT_RANK.get(c.get("segment", "retail"), 1),
                                    c.get("created_at") or _now()))
    # pro_rata keeps insertion order; allocation is proportional

    requests = [float(c.get("amount_uah") or 0) for c in commits]
    total_demand = _round2(sum(requests))

    if payload.policy == "pro_rata":
        allocs = _largest_remainder(requests, capacity)
    else:
        # sequential fill (first_come / priority)
        allocs = []
        left = capacity
        for r in requests:
            give = min(r, max(0.0, left))
            allocs.append(_round2(give))
            left = _round2(left - give)

    version = await db.lumen_allocations.count_documents({"asset_id": asset_id}) + 1
    results = []
    for c, give in zip(commits, allocs):
        give = _round2(give)
        waitlisted = _round2(max(0.0, float(c.get("amount_uah") or 0) - give))
        await db.lumen_commitments.update_one(
            {"id": c["id"]},
            {"$set": {"allocated_uah": give, "status": "allocated", "updated_at": _now()}})
        # overflow → waitlist
        if waitlisted > 0:
            existing = await db.lumen_waitlist.find_one(
                {"asset_id": asset_id, "investor_id": c["investor_id"],
                 "status": {"$in": ["waiting", "notified"]}})
            if not existing:
                await db.lumen_waitlist.insert_one({
                    "id": f"wl-{uuid.uuid4().hex[:12]}",
                    "asset_id": asset_id, "investor_id": c["investor_id"],
                    "investor_name": c.get("investor_name"),
                    "amount_uah": waitlisted, "segment": c.get("segment", "retail"),
                    "status": "waiting", "source": "allocation_overflow",
                    "created_at": _now(), "updated_at": _now(),
                })
        results.append({
            "commitment_id": c["id"], "investor_id": c["investor_id"],
            "investor_name": c.get("investor_name"), "segment": c.get("segment"),
            "requested_uah": _round2(float(c.get("amount_uah") or 0)),
            "allocated_uah": give, "waitlisted_uah": waitlisted,
        })

    over_pct = _round2(max(0.0, (total_demand / capacity * 100 - 100))) if capacity else 0
    record = {
        "id": f"alloc-{uuid.uuid4().hex[:12]}",
        "asset_id": asset_id, "asset_title": a.get("title"),
        "policy": payload.policy, "version": version,
        "capacity_uah": capacity, "total_demand_uah": total_demand,
        "oversubscription_pct": over_pct, "results": results,
        "created_by": _uid(admin), "created_at": _now(),
    }
    await db.lumen_allocations.insert_one(record)
    return _strip_mongo(record)


@router.get("/admin/assets/{asset_id}/allocations")
async def list_allocations(asset_id: str, _=Depends(require_admin)):
    items = []
    async for r in db.lumen_allocations.find({"asset_id": asset_id}, {"_id": 0}).sort("version", -1):
        items.append(_strip_mongo(r))
    return {"items": items}


# ════════════════════════════════════════════════════════════════════════════
# E9 — Pipeline Analytics
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/pipeline/analytics")
async def pipeline_analytics(_=Depends(require_admin)):
    counts = {s: 0 for s in DEAL_STAGES}
    total = 0
    rejection_reasons: dict[str, int] = {}
    deals = []
    async for d in db.lumen_deals.find({}, {"_id": 0}):
        total += 1
        s = d.get("stage")
        if s in counts:
            counts[s] += 1
        if s == "rejected":
            reason = (d.get("rejection_reason") or "Без причини").strip()
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        deals.append(d)

    active = sum(counts[s] for s in ("lead", "screening", "due_diligence", "committee", "funding"))
    live = counts.get("live", 0) + counts.get("operating", 0)
    closed = counts.get("exited", 0)
    rejected = counts.get("rejected", 0)

    # avg time-in-stage from events (stage_change deltas)
    durations: dict[str, list[float]] = {}
    for d in deals:
        evs = []
        async for e in db.lumen_deal_events.find(
                {"deal_id": d["id"], "kind": {"$in": ["created", "stage_change", "decision", "rejected"]}},
                {"_id": 0}).sort("created_at", 1):
            evs.append(e)
        for i in range(len(evs) - 1):
            cur = evs[i]
            nxt = evs[i + 1]
            stage_from = (cur.get("detail") or {}).get("to") or (
                "lead" if cur.get("kind") == "created" else None)
            t0 = _as_dt(cur.get("created_at"))
            t1 = _as_dt(nxt.get("created_at"))
            if stage_from and t0 and t1 and t1 >= t0:
                durations.setdefault(stage_from, []).append((t1 - t0).total_seconds() / 86400.0)
    avg_time_in_stage = {k: round(sum(v) / len(v), 1) for k, v in durations.items() if v}

    conversion_pct = _round2((live + closed) / total * 100) if total else 0
    rejection_list = sorted(
        [{"reason": k, "count": v} for k, v in rejection_reasons.items()],
        key=lambda x: x["count"], reverse=True)

    return {
        "total_deals": total, "counts": counts,
        "stage_labels": STAGE_LABELS_UK,
        "active": active, "live": live, "closed": closed, "rejected": rejected,
        "conversion_pct": conversion_pct,
        "rejection_reasons": rejection_list,
        "avg_time_in_stage_days": avg_time_in_stage,
    }


# ════════════════════════════════════════════════════════════════════════════
# E10 — Operator Marketplace
# ════════════════════════════════════════════════════════════════════════════

async def _operator_stats(op_id: str) -> dict:
    deals = await db.lumen_deals.count_documents({"operator_id": op_id})
    live = await db.lumen_deals.count_documents(
        {"operator_id": op_id, "stage": {"$in": ["live", "operating"]}})
    return {"deals_sourced": deals, "deals_live": live}


@router.get("/admin/operators")
async def list_operators(_=Depends(require_admin)):
    items = []
    async for op in db.lumen_operators.find({}, {"_id": 0}).sort("created_at", -1):
        out = _strip_mongo(op)
        out.update(await _operator_stats(op["id"]))
        items.append(out)
    return {"items": items, "kinds": list(OPERATOR_KINDS)}


@router.post("/admin/operators")
async def create_operator(payload: OperatorIn, _=Depends(require_admin)):
    if payload.kind not in OPERATOR_KINDS:
        raise HTTPException(status_code=400, detail="kind ∈ internal|external|partner")
    doc = {
        "id": f"op-{uuid.uuid4().hex[:12]}",
        "name": payload.name.strip(), "kind": payload.kind,
        "region": payload.region, "specialization": payload.specialization,
        "contact": payload.contact, "active": bool(payload.active),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_operators.insert_one(doc)
    out = _strip_mongo(doc)
    out.update(await _operator_stats(doc["id"]))
    return out


@router.get("/admin/operators/{op_id}")
async def get_operator(op_id: str, _=Depends(require_admin)):
    op = await db.lumen_operators.find_one({"id": op_id}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="Оператора не знайдено")
    out = _strip_mongo(op)
    out.update(await _operator_stats(op_id))
    deals = []
    async for d in db.lumen_deals.find({"operator_id": op_id}, {"_id": 0}).sort("created_at", -1):
        deals.append(_deal_label(d))
    out["deals"] = deals
    return out


@router.patch("/admin/operators/{op_id}")
async def update_operator(op_id: str, payload: OperatorPatch, _=Depends(require_admin)):
    op = await db.lumen_operators.find_one({"id": op_id})
    if not op:
        raise HTTPException(status_code=404, detail="Оператора не знайдено")
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "kind" in upd and upd["kind"] not in OPERATOR_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип")
    upd["updated_at"] = _now()
    await db.lumen_operators.update_one({"id": op_id}, {"$set": upd})
    return {"ok": True}


@router.delete("/admin/operators/{op_id}")
async def delete_operator(op_id: str, _=Depends(require_admin)):
    res = await db.lumen_operators.delete_one({"id": op_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Оператора не знайдено")
    await db.lumen_deals.update_many({"operator_id": op_id}, {"$set": {"operator_id": None}})
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
# Indexes + idempotent demo seed
# ════════════════════════════════════════════════════════════════════════════

async def ensure_capital_indexes() -> None:
    try:
        await db.lumen_deals.create_index([("stage", 1)])
        await db.lumen_deals.create_index([("operator_id", 1)])
        await db.lumen_deal_events.create_index([("deal_id", 1), ("created_at", 1)])
        await db.lumen_committee_votes.create_index(
            [("deal_id", 1), ("voter_id", 1)], unique=True)
        await db.lumen_data_room.create_index([("asset_id", 1), ("visibility", 1)])
        await db.lumen_data_room.create_index([("deal_id", 1)])
        await db.lumen_commitments.create_index([("asset_id", 1), ("status", 1)])
        await db.lumen_commitments.create_index([("investor_id", 1)])
        await db.lumen_waitlist.create_index(
            [("asset_id", 1), ("investor_id", 1)])
        await db.lumen_waitlist.create_index([("investor_id", 1)])
        await db.lumen_allocations.create_index([("asset_id", 1), ("version", -1)])
        await db.lumen_operators.create_index([("kind", 1), ("active", 1)])
    except Exception:
        logger.exception("capital indexes failed")


async def seed_capital_demo() -> dict:
    """Idempotent demo so Capital Formation OS is alive on a fresh DB.

    Uses REAL existing assets/users — never fabricates assets.
    """
    await ensure_capital_indexes()
    stats = {"operators": 0, "deals": 0, "dataroom": 0, "commitments": 0,
             "votes": 0}

    # ── E10 operators ──
    if await db.lumen_operators.count_documents({}) == 0:
        ops = [
            {"name": "LUMEN Capital", "kind": "internal", "region": "Україна",
             "specialization": "Усі класи активів", "contact": "capital@lumen.test"},
            {"name": "Podil Development Partners", "kind": "external", "region": "Київ",
             "specialization": "Житлова нерухомість", "contact": "info@podil.dev"},
            {"name": "West Logistics Operator", "kind": "partner", "region": "Захід",
             "specialization": "Складська логістика", "contact": "ops@westlog.ua"},
        ]
        op_ids = []
        for o in ops:
            doc = {"id": f"op-{uuid.uuid4().hex[:12]}", "active": True,
                   "created_at": _now(), "updated_at": _now(), **o}
            await db.lumen_operators.insert_one(doc)
            op_ids.append(doc["id"])
            stats["operators"] += 1
    else:
        op_ids = [o["id"] async for o in db.lumen_operators.find({}, {"id": 1}).limit(3)]

    op0 = op_ids[0] if op_ids else None
    op1 = op_ids[1] if len(op_ids) > 1 else op0
    op2 = op_ids[2] if len(op_ids) > 2 else op0

    # ── E1/E2 deals at various stages ──
    if await db.lumen_deals.count_documents({}) == 0:
        seed_deals = [
            {"title": "Бізнес-центр «Поділ Тех»", "source": "operator", "owner_name": "ТОВ «Поділ Девелопмент»",
             "region": "Київ", "asset_type": "commercial", "asking_price_uah": 12_000_000,
             "team_valuation_uah": 10_800_000, "stage": "due_diligence", "operator_id": op1,
             "description": "Офісний центр класу B+ у центрі Подолу, 4 200 м²."},
            {"title": "Сонячна станція «Південь-5»", "source": "inbound", "owner_name": "ФОП Коваленко",
             "region": "Одеська обл.", "asset_type": "construction", "asking_price_uah": 7_500_000,
             "team_valuation_uah": 7_000_000, "stage": "committee", "operator_id": op2,
             "description": "СЕС 2 МВт із діючим зеленим тарифом.",
             "committee": {
                 "memo": {"opportunity": "Стабільний грошовий потік від зеленого тарифу.",
                          "market": "Дефіцит генерації на півдні.",
                          "financials": "IRR ~19%, payback 5.3 роки.",
                          "exit": "Продаж стратегу через 5 років.",
                          "recommendation": "Рекомендуємо до схвалення."},
                 "risk_review": {"summary": "Регуляторний ризик тарифу.", "rating": "medium"},
                 "financial_review": {"summary": "Модель консервативна, маржа безпеки є.", "rating": "strong"},
                 "decision": None, "decided_at": None}},
            {"title": "Паркінг «Арена Сіті»", "source": "broker", "owner_name": "Arena Holding",
             "region": "Київ", "asset_type": "commercial", "asking_price_uah": 4_200_000,
             "team_valuation_uah": 3_900_000, "stage": "screening", "operator_id": op0,
             "description": "Багаторівневий паркінг біля ТРЦ, 320 місць."},
            {"title": "Агрокомплекс «Полтава-Зерно»", "source": "inbound", "owner_name": "АФ «Полтава»",
             "region": "Полтавська обл.", "asset_type": "land", "asking_price_uah": 9_800_000,
             "team_valuation_uah": 0, "stage": "rejected", "operator_id": op0,
             "rejection_reason": "Неприйнятна структура власності землі (оренда < 7 років).",
             "description": "Елеватор + 1 200 га оренди."},
            {"title": "Земельна ділянка «Стоянка» (раунд)", "source": "internal",
             "owner_name": "LUMEN SPV", "region": "Київська обл.", "asset_type": "land",
             "asking_price_uah": 3_200_000, "team_valuation_uah": 3_200_000,
             "stage": "funding", "operator_id": op0, "linked_asset_id": "asset-stoyanka-land",
             "description": "Перехід у збір капіталу — пов'язано з активом «Стоянка». Є активні зобов'язання інвесторів."},
        ]
        for sd in seed_deals:
            committee = sd.pop("committee", None) or {
                "memo": {}, "risk_review": {}, "financial_review": {},
                "decision": None, "decided_at": None}
            doc = {
                "id": f"deal-{uuid.uuid4().hex[:12]}",
                "rejection_reason": sd.pop("rejection_reason", None),
                "linked_asset_id": sd.pop("linked_asset_id", None),
                "committee": committee,
                "created_at": _now(), "updated_at": _now(),
                **sd,
            }
            await db.lumen_deals.insert_one(doc)
            stats["deals"] += 1
            await _deal_event(doc["id"], "created", None, {"stage": doc["stage"], "seed": True})
            # seed a committee vote on the committee-stage deal
            if doc["stage"] == "committee":
                admin_u = await db.users.find_one({"email": "admin@atlas.dev"}, {"user_id": 1, "id": 1, "name": 1})
                if admin_u:
                    auid = admin_u.get("user_id") or admin_u.get("id")
                    await db.lumen_committee_votes.update_one(
                        {"deal_id": doc["id"], "voter_id": auid},
                        {"$set": {"deal_id": doc["id"], "voter_id": auid,
                                  "voter_name": admin_u.get("name") or "Admin",
                                  "vote": "approve",
                                  "comment": "Підтримую, ризики прийнятні.",
                                  "created_at": _now(),
                                  "id": f"cv-{uuid.uuid4().hex[:12]}"}},
                        upsert=True)
                    stats["votes"] += 1

    # ── E3 data room (real asset) ──
    if await db.lumen_data_room.count_documents({}) == 0:
        if await db.lumen_assets.find_one({"id": "asset-podilskyi"}):
            dr = [
                {"category": "financial_model", "title": "Фінансова модель (зведення)", "visibility": "public"},
                {"category": "valuation", "title": "Звіт про оцінку", "visibility": "investor"},
                {"category": "reports", "title": "Щомісячний звіт — листопад", "visibility": "investor"},
                {"category": "contracts", "title": "Договір SPV (повний)", "visibility": "admin"},
                {"category": "due_diligence", "title": "DD checklist (внутрішній)", "visibility": "admin"},
                {"category": "photos", "title": "Фотозвіт об'єкта", "visibility": "public"},
            ]
            for item in dr:
                await db.lumen_data_room.insert_one({
                    "id": f"dr-{uuid.uuid4().hex[:12]}",
                    "asset_id": "asset-podilskyi", "deal_id": None,
                    "url": None, "file_name": None, "size": None,
                    "uploaded_by": "seed", "created_at": _now(), **item})
                stats["dataroom"] += 1

    # ── E4 commitments (oversubscribe asset-stoyanka-land for a live demo) ──
    if await db.lumen_commitments.count_documents({}) == 0:
        client = await db.users.find_one({"email": "client@atlas.dev"}, {"user_id": 1, "id": 1, "name": 1})
        if client and await db.lumen_assets.find_one({"id": "asset-stoyanka-land"}):
            cuid = client.get("user_id") or client.get("id")
            seg = await _investor_segment(cuid)
            demo_commits = [
                {"kind": "hard", "amount_uah": 400_000},
                {"kind": "reservation", "amount_uah": 250_000},
                {"kind": "soft", "amount_uah": 150_000},
            ]
            for dc in demo_commits:
                await db.lumen_commitments.insert_one({
                    "id": f"cm-{uuid.uuid4().hex[:12]}",
                    "asset_id": "asset-stoyanka-land", "deal_id": None,
                    "investor_id": cuid, "investor_name": client.get("name") or "Client",
                    "segment": seg["segment"], "allocated_uah": 0.0,
                    "status": "pending", "created_at": _now(), "updated_at": _now(),
                    **dc})
                stats["commitments"] += 1

    return stats
