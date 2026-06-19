"""
LUMEN 2.0 — Phase G — Institutional Ownership OS
================================================

Not "add funds". This phase builds the **formal ownership model** between

    Investor → Certificate → SPV → Operator → Asset

so that Funds, Syndicates and Family Offices attach LATER without migration.

FORBIDDEN in G (by design): tokenization, crypto, on-chain ownership, NFT
certificates, DAO governance. Those belong to Phase H (Crypto Rail).

Blocks
------
  G1  Ownership Structure Engine — derived Asset→SPV→cap-table→operator
  G2  SPV Group / Multi-SPV      — fund membership so Fund→SPV→Asset works
  G3  Fund Layer                 — container of SPVs, NAV derived
  G4  Syndicate Layer            — lead investor reserves %, others join
  G5  Beneficial Ownership (UBO) — registry from cert holders + declared chain
  G6  Institutional Reporting    — my funds / my SPVs / aggregated portfolio
  G7  Governance Framework       — weighted votes + operator conflict-of-interest
  G8  Compliance Matrix          — per-segment limits (retail→institutional)
  G9  Institutional Dashboard    — scoped cabinet for institutional investors
  G10 Trust Graph                — nodes/edges Investor→Cert→SPV→Operator→Asset(→Fund)

Everything DERIVES from real collections — no mocks.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import (db, get_current_user, require_admin, _strip_mongo,
                       _now, _iso, lr2_perm as _lr2_perm)

try:
    from lumen_payments import _round2
except Exception:  # pragma: no cover
    def _round2(v: float) -> float:
        return round(float(v or 0), 2)

logger = logging.getLogger("lumen.institutional")
router = APIRouter(prefix="/api", tags=["lumen-institutional-os"])

# ── Domain constants ─────────────────────────────────────────────────────────
FUND_KINDS = ("residential", "commercial", "logistics", "mixed", "land")
FUND_KIND_LABELS_UK = {
    "residential": "Житловий", "commercial": "Комерційний",
    "logistics": "Логістичний", "mixed": "Змішаний", "land": "Земельний",
}
FUND_STATES = ("forming", "active", "closed")
FUND_STATE_LABELS_UK = {"forming": "Формується", "active": "Активний", "closed": "Закритий"}

SYNDICATE_STATES = ("open", "filling", "funded", "closed")
SYNDICATE_STATE_LABELS_UK = {
    "open": "Відкрито", "filling": "Збір триває", "funded": "Профінансовано", "closed": "Закрито",
}

SEGMENTS = ("retail", "qualified", "strategic", "institutional")
SEGMENT_RANK = {"retail": 1, "qualified": 2, "strategic": 3, "institutional": 4}
SEGMENT_LABELS_UK = {
    "retail": "Роздрібний", "qualified": "Кваліфікований",
    "strategic": "Стратегічний", "institutional": "Інституційний",
}
# institutional cabinet available from this segment up
INSTITUTIONAL_MIN_RANK = SEGMENT_RANK["strategic"]

GOV_SCOPES = ("asset", "spv", "fund")


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


async def _active_certs(query: dict) -> list[dict]:
    out = []
    async for c in db.lumen_certificates.find({**query, "status": {"$ne": "voided"}}, {"_id": 0}):
        out.append(c)
    return out


async def _asset_value(asset_id: str, certs: Optional[list] = None) -> float:
    """Equity value of an asset = sum of active certificate values; fallback raised."""
    if certs is None:
        certs = await _active_certs({"asset_id": asset_id})
    v = sum(float(c.get("value_uah") or 0) for c in certs)
    if v <= 0:
        a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "raised": 1, "raised_amount": 1})
        if a:
            v = float(a.get("raised") or a.get("raised_amount") or 0)
    return _round2(v)


async def _spv_for_asset(asset_id: str) -> Optional[dict]:
    return await db.lumen_spvs.find_one({"asset_id": asset_id}, {"_id": 0})


async def _operator_for_asset(asset_id: str) -> Optional[dict]:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "operator_id": 1})
    if not a or not a.get("operator_id"):
        return None
    return await db.lumen_operators.find_one({"id": a["operator_id"]}, {"_id": 0})


async def _investor_segment(user_id: str) -> str:
    p = await db.lumen_investor_profiles.find_one({"user_id": user_id}, {"_id": 0, "segment": 1})
    seg = (p or {}).get("segment") or "retail"
    return seg if seg in SEGMENTS else "retail"


async def _cap_table(asset_id: str, certs: Optional[list] = None) -> list[dict]:
    """Group active certificates by investor → holder rows for an asset."""
    if certs is None:
        certs = await _active_certs({"asset_id": asset_id})
    by_inv: dict[str, dict] = {}
    for c in certs:
        iid = c.get("investor_id")
        if not iid:
            continue
        row = by_inv.setdefault(iid, {
            "investor_id": iid, "investor_name": c.get("investor_name") or "Інвестор",
            "units": 0.0, "value_uah": 0.0, "ownership_percent": 0.0, "certificates": 0,
        })
        row["units"] += float(c.get("units") or 0)
        row["value_uah"] += float(c.get("value_uah") or 0)
        row["ownership_percent"] += float(c.get("ownership_percent") or 0)
        row["certificates"] += 1
    rows = list(by_inv.values())
    for r in rows:
        r["value_uah"] = _round2(r["value_uah"])
        r["ownership_percent"] = round(r["ownership_percent"], 3)
        r["units"] = round(r["units"], 2)
    rows.sort(key=lambda x: x["value_uah"], reverse=True)
    return rows


async def _asset_brief(asset_id: str) -> dict:
    a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0}) or {}
    return {
        "id": asset_id, "title": a.get("title"), "category": a.get("category"),
        "location": a.get("location"), "cover_url": a.get("cover_url"),
        "target_yield": a.get("target_yield"), "occupancy_percent": a.get("occupancy_percent"),
        "status": a.get("status"),
    }


def _fund_public(f: dict, nav: float | None = None, holdings: list | None = None) -> dict:
    out = {
        "id": f["id"], "name": f.get("name"), "kind": f.get("kind"),
        "kind_label": FUND_KIND_LABELS_UK.get(f.get("kind"), f.get("kind")),
        "strategy": f.get("strategy"), "region": f.get("region"),
        "target_size_uah": f.get("target_size_uah"),
        "status": f.get("status", "forming"),
        "status_label": FUND_STATE_LABELS_UK.get(f.get("status", "forming")),
        "manager_operator_id": f.get("manager_operator_id"),
        "description": f.get("description"),
        "spv_ids": f.get("spv_ids") or [],
    }
    if nav is not None:
        out["nav_uah"] = nav
        if f.get("target_size_uah"):
            out["funded_pct"] = round(nav / float(f["target_size_uah"]) * 100, 1)
    if holdings is not None:
        out["holdings"] = holdings
        out["assets_count"] = len(holdings)
    return out


async def _fund_nav_and_holdings(f: dict) -> tuple[float, list[dict]]:
    """NAV = sum of underlying SPV asset equity values."""
    holdings = []
    nav = 0.0
    for spv_id in (f.get("spv_ids") or []):
        spv = await db.lumen_spvs.find_one({"id": spv_id}, {"_id": 0})
        if not spv:
            continue
        asset_id = spv.get("asset_id")
        val = await _asset_value(asset_id) if asset_id else 0.0
        nav += val
        ab = await _asset_brief(asset_id) if asset_id else {}
        holdings.append({
            "spv_id": spv_id, "spv_name": spv.get("name"),
            "asset_id": asset_id, "asset_title": ab.get("title"),
            "category": ab.get("category"), "value_uah": val,
        })
    return _round2(nav), holdings


async def _fund_or_404(fund_id: str) -> dict:
    f = await db.lumen_funds.find_one({"id": fund_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Фонд не знайдено")
    return f


async def _syndicate_state(s: dict) -> dict:
    parts = []
    raised = 0.0
    async for p in db.lumen_syndicate_participants.find({"syndicate_id": s["id"]}, {"_id": 0}):
        parts.append(_strip_mongo(p))
        raised += float(p.get("amount_uah") or 0)
    target = float(s.get("target_uah") or 0)
    out = _strip_mongo(dict(s))
    out["state_label"] = SYNDICATE_STATE_LABELS_UK.get(s.get("status", "open"))
    out["raised_uah"] = _round2(raised)
    out["progress_pct"] = round(raised / target * 100, 1) if target else 0.0
    out["participants_count"] = len(parts)
    out["participants"] = sorted(parts, key=lambda x: (x.get("role") != "lead", -float(x.get("amount_uah") or 0)))
    return out


# ════════════════════════════════════════════════════════════════════════════
# Access dependencies
# ════════════════════════════════════════════════════════════════════════════

async def require_institutional(request: Request) -> dict:
    """Investor whose segment is strategic/institutional (or admin)."""
    user = await get_current_user(request)
    if _is_admin(user):
        return {"user": user, "segment": "institutional", "admin": True}
    seg = await _investor_segment(_uid(user))
    if SEGMENT_RANK.get(seg, 1) < INSTITUTIONAL_MIN_RANK:
        raise HTTPException(status_code=403,
                            detail="Інституційний кабінет доступний кваліфікованим інвесторам (Strategic/Institutional)")
    return {"user": user, "segment": seg, "admin": False}


# ════════════════════════════════════════════════════════════════════════════
# Pydantic payloads
# ════════════════════════════════════════════════════════════════════════════

class FundIn(BaseModel):
    name: str
    kind: Optional[str] = "mixed"
    strategy: Optional[str] = None
    region: Optional[str] = None
    target_size_uah: Optional[float] = None
    manager_operator_id: Optional[str] = None
    description: Optional[str] = None


class FundPatch(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    strategy: Optional[str] = None
    region: Optional[str] = None
    target_size_uah: Optional[float] = None
    manager_operator_id: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class SpvLinkIn(BaseModel):
    spv_id: str


class SyndicateIn(BaseModel):
    title: str
    asset_id: str
    lead_investor_id: Optional[str] = None
    target_uah: float
    lead_pct: Optional[float] = 20.0
    min_ticket_uah: Optional[float] = 50000.0
    deadline: Optional[str] = None


class SyndicateJoinIn(BaseModel):
    amount_uah: float


class UboIn(BaseModel):
    investor_id: Optional[str] = None
    ubo_name: str
    relationship: Optional[str] = "self"
    ownership_pct: Optional[float] = 100.0
    is_pep: Optional[bool] = False
    country: Optional[str] = "UA"


class ProposalIn(BaseModel):
    scope: str
    scope_id: str
    title: str
    description: Optional[str] = None
    options: Optional[list] = None
    days_open: Optional[int] = 14


class VoteIn(BaseModel):
    choice: str


class MatrixPatch(BaseModel):
    max_ticket_uah: Optional[float] = None
    allowed_categories: Optional[list] = None
    requires_accreditation: Optional[bool] = None
    requires_ubo: Optional[bool] = None


# ════════════════════════════════════════════════════════════════════════════
# G1 — Ownership Structure Engine
# ════════════════════════════════════════════════════════════════════════════

async def _asset_structure(asset_id: str) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    certs = await _active_certs({"asset_id": asset_id})
    spv = await _spv_for_asset(asset_id)
    operator = await _operator_for_asset(asset_id)
    cap = await _cap_table(asset_id, certs)
    value = await _asset_value(asset_id, certs)
    fund = await db.lumen_funds.find_one({"spv_ids": spv["id"]}, {"_id": 0}) if spv else None
    return {
        "asset": await _asset_brief(asset_id),
        "spv": ({"id": spv["id"], "name": spv.get("name"),
                 "registration_number": spv.get("registration_number"),
                 "jurisdiction": spv.get("jurisdiction"), "status": spv.get("status")} if spv else None),
        "operator": ({"id": operator["id"], "name": operator.get("name"),
                      "status": operator.get("status"),
                      "verified": operator.get("status") in ("verified", "approved")} if operator else None),
        "fund": ({"id": fund["id"], "name": fund.get("name")} if fund else None),
        "equity_value_uah": value,
        "holders_count": len(cap),
        "cap_table": cap,
    }


@router.get("/admin/institutional/assets/{asset_id}/structure")
async def admin_asset_structure(asset_id: str, _=Depends(require_admin)):
    return await _asset_structure(asset_id)


@router.get("/institutional/assets/{asset_id}/structure")
async def public_asset_structure(asset_id: str):
    """Privacy-safe: hide holder names for public consumers."""
    s = await _asset_structure(asset_id)
    for row in s["cap_table"]:
        row.pop("investor_id", None)
        row["investor_name"] = "Інвестор"
    return s


# ════════════════════════════════════════════════════════════════════════════
# G3 / G2 — Fund layer + SPV grouping
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/institutional/funds")
async def admin_list_funds(_=Depends(require_admin)):
    items = []
    async for f in db.lumen_funds.find({}, {"_id": 0}).sort("created_at", 1):
        nav, holdings = await _fund_nav_and_holdings(f)
        items.append(_fund_public(f, nav, holdings))
    return {"items": items}


@router.post("/admin/institutional/funds")
async def admin_create_fund(payload: FundIn, _=Depends(require_admin),
                             _perm=Depends(_lr2_perm("fund", "write"))):
    if payload.kind and payload.kind not in FUND_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип фонду")
    doc = {
        "id": f"fund-{uuid.uuid4().hex[:12]}", "name": payload.name.strip(),
        "kind": payload.kind or "mixed", "strategy": payload.strategy,
        "region": payload.region, "target_size_uah": payload.target_size_uah,
        "manager_operator_id": payload.manager_operator_id,
        "description": payload.description, "status": "forming",
        "spv_ids": [], "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_funds.insert_one(doc)
    return _fund_public(doc, 0.0, [])


@router.get("/admin/institutional/funds/{fund_id}")
async def admin_fund_detail(fund_id: str, _=Depends(require_admin)):
    f = await _fund_or_404(fund_id)
    nav, holdings = await _fund_nav_and_holdings(f)
    # available SPVs (not yet in this fund)
    available = []
    async for spv in db.lumen_spvs.find({"id": {"$nin": f.get("spv_ids") or []}}, {"_id": 0}):
        ab = await _asset_brief(spv.get("asset_id")) if spv.get("asset_id") else {}
        available.append({"id": spv["id"], "name": spv.get("name"),
                          "asset_id": spv.get("asset_id"), "asset_title": ab.get("title")})
    return {**_fund_public(f, nav, holdings), "available_spvs": available}


@router.patch("/admin/institutional/funds/{fund_id}")
async def admin_update_fund(fund_id: str, payload: FundPatch, _=Depends(require_admin),
                             _perm=Depends(_lr2_perm("fund", "write"))):
    await _fund_or_404(fund_id)
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "kind" in upd and upd["kind"] not in FUND_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип")
    if "status" in upd and upd["status"] not in FUND_STATES:
        raise HTTPException(status_code=400, detail="Невідомий статус")
    upd["updated_at"] = _now()
    await db.lumen_funds.update_one({"id": fund_id}, {"$set": upd})
    return {"ok": True}


@router.delete("/admin/institutional/funds/{fund_id}")
async def admin_delete_fund(fund_id: str, _=Depends(require_admin),
                             _perm=Depends(_lr2_perm("fund", "delete"))):
    res = await db.lumen_funds.delete_one({"id": fund_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Фонд не знайдено")
    return {"ok": True}


@router.post("/admin/institutional/funds/{fund_id}/spvs")
async def admin_fund_add_spv(fund_id: str, payload: SpvLinkIn, _=Depends(require_admin),
                              _perm=Depends(_lr2_perm("fund", "write"))):
    await _fund_or_404(fund_id)
    spv = await db.lumen_spvs.find_one({"id": payload.spv_id}, {"_id": 0})
    if not spv:
        raise HTTPException(status_code=404, detail="SPV не знайдено")
    await db.lumen_funds.update_one({"id": fund_id},
                                    {"$addToSet": {"spv_ids": payload.spv_id}, "$set": {"updated_at": _now()}})
    return {"ok": True}


@router.delete("/admin/institutional/funds/{fund_id}/spvs/{spv_id}")
async def admin_fund_remove_spv(fund_id: str, spv_id: str, _=Depends(require_admin)):
    await db.lumen_funds.update_one({"id": fund_id},
                                    {"$pull": {"spv_ids": spv_id}, "$set": {"updated_at": _now()}})
    return {"ok": True}


@router.get("/institutional/funds")
async def public_funds():
    items = []
    async for f in db.lumen_funds.find({"status": {"$ne": "forming"}}, {"_id": 0}).sort("created_at", 1):
        nav, holdings = await _fund_nav_and_holdings(f)
        items.append(_fund_public(f, nav, holdings))
    return {"items": items}


@router.get("/institutional/funds/{fund_id}")
async def public_fund_detail(fund_id: str):
    f = await _fund_or_404(fund_id)
    nav, holdings = await _fund_nav_and_holdings(f)
    out = _fund_public(f, nav, holdings)
    if f.get("manager_operator_id"):
        op = await db.lumen_operators.find_one({"id": f["manager_operator_id"]}, {"_id": 0, "name": 1, "status": 1})
        if op:
            out["manager"] = {"id": f["manager_operator_id"], "name": op.get("name"),
                              "verified": op.get("status") in ("verified", "approved")}
    return out


# ════════════════════════════════════════════════════════════════════════════
# G4 — Syndicate layer
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/institutional/syndicates")
async def admin_list_syndicates(_=Depends(require_admin)):
    items = []
    async for s in db.lumen_syndicates.find({}, {"_id": 0}).sort("created_at", -1):
        items.append(await _syndicate_state(s))
    return {"items": items}


@router.post("/admin/institutional/syndicates")
async def admin_create_syndicate(payload: SyndicateIn, admin=Depends(require_admin),
                                  _perm=Depends(_lr2_perm("fund", "write"))):
    a = await db.lumen_assets.find_one({"id": payload.asset_id}, {"_id": 0, "title": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    lead_name = None
    if payload.lead_investor_id:
        u = await db.users.find_one({"user_id": payload.lead_investor_id}, {"_id": 0, "name": 1})
        lead_name = (u or {}).get("name")
    sid = f"synd-{uuid.uuid4().hex[:12]}"
    doc = {
        "id": sid, "title": payload.title.strip(), "asset_id": payload.asset_id,
        "asset_title": a.get("title"), "lead_investor_id": payload.lead_investor_id,
        "lead_investor_name": lead_name, "target_uah": float(payload.target_uah),
        "lead_pct": float(payload.lead_pct or 0), "min_ticket_uah": float(payload.min_ticket_uah or 0),
        "status": "open", "deadline": payload.deadline,
        "created_by": _uid(admin), "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_syndicates.insert_one(doc)
    # lead auto-reservation
    if payload.lead_investor_id and payload.lead_pct:
        await db.lumen_syndicate_participants.insert_one({
            "id": f"sp-{uuid.uuid4().hex[:12]}", "syndicate_id": sid,
            "investor_id": payload.lead_investor_id, "investor_name": lead_name or "Lead",
            "amount_uah": _round2(float(payload.target_uah) * float(payload.lead_pct) / 100),
            "role": "lead", "status": "confirmed", "created_at": _now(),
        })
    return await _syndicate_state(doc)


@router.get("/institutional/syndicates")
async def public_syndicates():
    items = []
    async for s in db.lumen_syndicates.find({"status": {"$ne": "closed"}}, {"_id": 0}).sort("created_at", -1):
        items.append(await _syndicate_state(s))
    return {"items": items}


@router.get("/institutional/syndicates/{sid}")
async def public_syndicate_detail(sid: str):
    s = await db.lumen_syndicates.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Синдикат не знайдено")
    out = await _syndicate_state(s)
    # privacy: mask participant identities for public
    for p in out["participants"]:
        p.pop("investor_id", None)
    return out


@router.post("/institutional/syndicates/{sid}/join")
async def join_syndicate(sid: str, payload: SyndicateJoinIn,
                          ctx=Depends(require_institutional),
                          _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    s = await db.lumen_syndicates.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Синдикат не знайдено")
    if s.get("status") in ("funded", "closed"):
        raise HTTPException(status_code=400, detail="Синдикат закрито для приєднання")
    amount = float(payload.amount_uah)
    if amount < float(s.get("min_ticket_uah") or 0):
        raise HTTPException(status_code=400,
                            detail=f"Мінімальний чек {fmt_uah_as_usd(s.get('min_ticket_uah') or 0)}")
    uid = _uid(ctx["user"])
    existing = await db.lumen_syndicate_participants.find_one({"syndicate_id": sid, "investor_id": uid})
    if existing:
        await db.lumen_syndicate_participants.update_one(
            {"id": existing["id"]}, {"$set": {"amount_uah": _round2(amount), "updated_at": _now()}})
    else:
        await db.lumen_syndicate_participants.insert_one({
            "id": f"sp-{uuid.uuid4().hex[:12]}", "syndicate_id": sid, "investor_id": uid,
            "investor_name": ctx["user"].get("name") or "Інвестор", "amount_uah": _round2(amount),
            "role": "participant", "status": "reserved", "created_at": _now(),
        })
    # auto-advance status
    state = await _syndicate_state(s)
    new_status = "funded" if state["raised_uah"] >= float(s.get("target_uah") or 0) else "filling"
    await db.lumen_syndicates.update_one({"id": sid}, {"$set": {"status": new_status, "updated_at": _now()}})
    return await _syndicate_state(await db.lumen_syndicates.find_one({"id": sid}, {"_id": 0}))


# ════════════════════════════════════════════════════════════════════════════
# G5 — Beneficial Ownership (UBO)
# ════════════════════════════════════════════════════════════════════════════

async def _ubo_registry() -> list[dict]:
    """For each investor holding active certs: declared UBO chain or implicit self."""
    holders: dict[str, dict] = {}
    async for c in db.lumen_certificates.find({"status": {"$ne": "voided"}}, {"_id": 0}):
        iid = c.get("investor_id")
        if not iid:
            continue
        h = holders.setdefault(iid, {"investor_id": iid, "investor_name": c.get("investor_name"),
                                     "value_uah": 0.0})
        h["value_uah"] += float(c.get("value_uah") or 0)
    rows = []
    for iid, h in holders.items():
        declared = []
        async for u in db.lumen_beneficial_owners.find({"investor_id": iid}, {"_id": 0}):
            declared.append(_strip_mongo(u))
        rows.append({
            "investor_id": iid, "investor_name": h["investor_name"],
            "value_uah": _round2(h["value_uah"]),
            "declared": declared,
            "has_ubo": len(declared) > 0,
            "pep_flag": any(d.get("is_pep") for d in declared),
        })
    rows.sort(key=lambda x: x["value_uah"], reverse=True)
    return rows


@router.get("/admin/institutional/ubo")
async def admin_ubo_registry(_=Depends(require_admin)):
    rows = await _ubo_registry()
    return {"items": rows, "total_holders": len(rows),
            "with_ubo": sum(1 for r in rows if r["has_ubo"]),
            "pep_count": sum(1 for r in rows if r["pep_flag"])}


@router.post("/admin/institutional/ubo")
async def admin_declare_ubo(payload: UboIn, _=Depends(require_admin),
                             _perm=Depends(_lr2_perm("compliance_profile", "approve"))):
    if not payload.investor_id:
        raise HTTPException(status_code=400, detail="Вкажіть investor_id")
    return await _insert_ubo(payload, payload.investor_id, verified=True)


@router.delete("/admin/institutional/ubo/{ubo_id}")
async def admin_delete_ubo(ubo_id: str, _=Depends(require_admin),
                            _perm=Depends(_lr2_perm("compliance_profile", "delete"))):
    res = await db.lumen_beneficial_owners.delete_one({"id": ubo_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    return {"ok": True}


@router.get("/institutional/me/ubo")
async def my_ubo(ctx=Depends(require_institutional)):
    uid = _uid(ctx["user"])
    items = []
    async for u in db.lumen_beneficial_owners.find({"investor_id": uid}, {"_id": 0}):
        items.append(_strip_mongo(u))
    return {"items": items}


@router.post("/institutional/me/ubo")
async def declare_my_ubo(payload: UboIn, ctx=Depends(require_institutional),
                          _perm=Depends(_lr2_perm("compliance_profile", "write"))):
    uid = _uid(ctx["user"])
    return await _insert_ubo(payload, uid, verified=False)


async def _insert_ubo(payload: UboIn, investor_id: str, verified: bool) -> dict:
    doc = {
        "id": f"ubo-{uuid.uuid4().hex[:12]}", "investor_id": investor_id,
        "ubo_name": payload.ubo_name.strip(), "relationship": payload.relationship or "self",
        "ownership_pct": float(payload.ownership_pct or 0), "is_pep": bool(payload.is_pep),
        "country": payload.country or "UA", "verified": verified, "created_at": _now(),
    }
    await db.lumen_beneficial_owners.insert_one(doc)
    return _strip_mongo(doc)


# ════════════════════════════════════════════════════════════════════════════
# G8 — Compliance Matrix
# ════════════════════════════════════════════════════════════════════════════

DEFAULT_MATRIX = {
    "retail": {"max_ticket_uah": 100000, "allowed_categories": ["real_estate"],
               "requires_accreditation": False, "requires_ubo": False},
    "qualified": {"max_ticket_uah": 500000, "allowed_categories": ["all"],
                  "requires_accreditation": False, "requires_ubo": False},
    "strategic": {"max_ticket_uah": 2000000, "allowed_categories": ["all"],
                  "requires_accreditation": True, "requires_ubo": False},
    "institutional": {"max_ticket_uah": None, "allowed_categories": ["all"],
                      "requires_accreditation": True, "requires_ubo": True},
}


async def _matrix() -> dict:
    out = {}
    async for m in db.lumen_compliance_matrix.find({}, {"_id": 0}):
        out[m["segment"]] = m
    return out


@router.get("/institutional/compliance/matrix")
async def compliance_matrix():
    m = await _matrix()
    rows = []
    for seg in SEGMENTS:
        d = m.get(seg, {**DEFAULT_MATRIX[seg], "segment": seg})
        rows.append({**d, "segment": seg, "segment_label": SEGMENT_LABELS_UK[seg]})
    return {"items": rows}


@router.patch("/admin/institutional/compliance/matrix/{segment}")
async def admin_update_matrix(segment: str, payload: MatrixPatch, _=Depends(require_admin),
                               _perm=Depends(_lr2_perm("compliance_profile", "override"))):
    if segment not in SEGMENTS:
        raise HTTPException(status_code=400, detail="Невідомий сегмент")
    upd = {k: v for k, v in payload.dict(exclude_unset=True).items()}
    upd["updated_at"] = _now()
    await db.lumen_compliance_matrix.update_one({"segment": segment}, {"$set": upd}, upsert=True)
    return {"ok": True}


@router.get("/institutional/compliance/check")
async def compliance_check(asset_id: str, amount: float, request: Request):
    user = await get_current_user(request)
    seg = await _investor_segment(_uid(user))
    m = await _matrix()
    rule = m.get(seg) or {**DEFAULT_MATRIX[seg], "segment": seg}
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "category": 1})
    cat = (asset or {}).get("category")
    reasons = []
    allowed = True
    max_ticket = rule.get("max_ticket_uah")
    if max_ticket is not None and float(amount) > float(max_ticket):
        allowed = False
        reasons.append(f"Перевищено ліміт для сегмента {SEGMENT_LABELS_UK[seg]}: {fmt_uah_as_usd(max_ticket)}")
    allowed_cats = rule.get("allowed_categories") or ["all"]
    if "all" not in allowed_cats and cat not in allowed_cats:
        allowed = False
        reasons.append("Категорія активу недоступна для вашого сегмента")
    if rule.get("requires_accreditation"):
        p = await db.lumen_investor_profiles.find_one({"user_id": _uid(user)},
                                                      {"_id": 0, "accreditation_status": 1})
        if (p or {}).get("accreditation_status") not in ("approved", "accredited", "verified"):
            reasons.append("Потрібна акредитація інвестора")
    if rule.get("requires_ubo"):
        has = await db.lumen_beneficial_owners.count_documents({"investor_id": _uid(user)})
        if not has:
            reasons.append("Потрібно задекларувати кінцевого бенефіціара (UBO)")
    return {"segment": seg, "segment_label": SEGMENT_LABELS_UK[seg],
            "allowed": allowed, "max_ticket_uah": max_ticket,
            "warnings": [r for r in reasons if "ліміт" not in r and "недоступна" not in r],
            "blockers": [r for r in reasons if "ліміт" in r or "недоступна" in r],
            "reasons": reasons}


# ════════════════════════════════════════════════════════════════════════════
# G7 — Governance Framework (with operator conflict-of-interest)
# ════════════════════════════════════════════════════════════════════════════

async def _proposal_scope_assets(scope: str, scope_id: str) -> list[str]:
    if scope == "asset":
        return [scope_id]
    if scope == "spv":
        spv = await db.lumen_spvs.find_one({"id": scope_id}, {"_id": 0, "asset_id": 1})
        return [spv["asset_id"]] if spv and spv.get("asset_id") else []
    if scope == "fund":
        f = await db.lumen_funds.find_one({"id": scope_id}, {"_id": 0, "spv_ids": 1})
        ids = []
        for sid in (f or {}).get("spv_ids", []):
            spv = await db.lumen_spvs.find_one({"id": sid}, {"_id": 0, "asset_id": 1})
            if spv and spv.get("asset_id"):
                ids.append(spv["asset_id"])
        return ids
    return []


async def _voter_weight(uid: str, asset_ids: list[str]) -> float:
    if not asset_ids:
        return 0.0
    w = 0.0
    async for o in db.lumen_ownerships.find({"investor_id": uid, "asset_id": {"$in": asset_ids}}):
        # units_int is the authoritative materialised registry weight; fall back
        # to the UAH-scaled `units` field for legacy rows.
        w += float(o.get("units_int") or o.get("units") or 0)
    return w


async def _is_operator_coi(uid: str, asset_ids: list[str]) -> bool:
    """True if this user is the operator of ANY scoped asset (conflict of interest)."""
    if not uid or not asset_ids:
        return False
    async for a in db.lumen_assets.find({"id": {"$in": asset_ids}, "operator_id": {"$ne": None}},
                                        {"_id": 0, "operator_id": 1}):
        op = await db.lumen_operators.find_one({"id": a["operator_id"]}, {"_id": 0, "user_id": 1})
        if op and op.get("user_id") == uid:
            return True
    return False


async def _proposal_view(p: dict, uid: Optional[str] = None) -> dict:
    asset_ids = await _proposal_scope_assets(p["scope"], p["scope_id"])
    tally: dict[str, float] = {}
    voters = 0
    your_vote = None
    async for v in db.lumen_gov_votes.find({"proposal_id": p["id"]}, {"_id": 0}):
        tally[v["choice"]] = tally.get(v["choice"], 0.0) + float(v.get("weight") or 0)
        voters += 1
        if uid and v.get("voter_id") == uid:
            your_vote = v.get("choice")
    total_w = sum(tally.values())
    results = [{"option": opt, "weight": round(tally.get(opt, 0.0), 2),
                "pct": round(tally.get(opt, 0.0) / total_w * 100, 1) if total_w else 0.0}
               for opt in (p.get("options") or [])]
    out = _strip_mongo(dict(p))
    out["results"] = results
    out["total_weight"] = round(total_w, 2)
    out["voters"] = voters
    out["scope_assets"] = asset_ids
    if uid:
        out["your_vote"] = your_vote
        out["coi_blocked"] = await _is_operator_coi(uid, asset_ids)
        out["your_weight"] = round(await _voter_weight(uid, asset_ids), 2)
    return out


@router.get("/governance/proposals")
async def list_proposals(request: Request):
    user = await get_current_user(request)
    uid = _uid(user)
    items = []
    async for p in db.lumen_gov_proposals.find({}, {"_id": 0}).sort("created_at", -1):
        items.append(await _proposal_view(p, uid))
    return {"items": items}


@router.get("/governance/proposals/{pid}")
async def get_proposal(pid: str, request: Request):
    user = await get_current_user(request)
    p = await db.lumen_gov_proposals.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")
    return await _proposal_view(p, _uid(user))


@router.post("/admin/institutional/governance/proposals")
async def admin_create_proposal(payload: ProposalIn, admin=Depends(require_admin),
                                 _perm=Depends(_lr2_perm("governance_proposal", "write"))):
    if payload.scope not in GOV_SCOPES:
        raise HTTPException(status_code=400, detail="Невідомий scope")
    label = payload.scope_id
    if payload.scope == "asset":
        a = await db.lumen_assets.find_one({"id": payload.scope_id}, {"_id": 0, "title": 1})
        label = (a or {}).get("title") or payload.scope_id
    elif payload.scope == "fund":
        f = await db.lumen_funds.find_one({"id": payload.scope_id}, {"_id": 0, "name": 1})
        label = (f or {}).get("name") or payload.scope_id
    doc = {
        "id": f"gp-{uuid.uuid4().hex[:12]}", "scope": payload.scope, "scope_id": payload.scope_id,
        "scope_label": label, "title": payload.title.strip(), "description": payload.description,
        "options": payload.options or ["За", "Проти", "Утримуюсь"], "status": "open",
        "opens_at": _now(), "closes_at": _now() + timedelta(days=int(payload.days_open or 14)),
        "created_by": _uid(admin), "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_gov_proposals.insert_one(doc)
    return _strip_mongo(doc)


@router.post("/admin/institutional/governance/proposals/{pid}/close")
async def admin_close_proposal(pid: str, _=Depends(require_admin),
                                _perm=Depends(_lr2_perm("governance_proposal", "approve"))):
    await db.lumen_gov_proposals.update_one({"id": pid}, {"$set": {"status": "closed", "updated_at": _now()}})
    return {"ok": True}


@router.post("/governance/proposals/{pid}/vote")
async def cast_vote(pid: str, payload: VoteIn, request: Request,
                     _perm=Depends(_lr2_perm("governance_proposal", "write"))):
    user = await get_current_user(request)
    uid = _uid(user)
    p = await db.lumen_gov_proposals.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")
    if p.get("status") != "open":
        raise HTTPException(status_code=400, detail="Голосування закрито")
    if payload.choice not in (p.get("options") or []):
        raise HTTPException(status_code=400, detail="Невідомий варіант")
    asset_ids = await _proposal_scope_assets(p["scope"], p["scope_id"])
    # G7 conflict-of-interest: operator cannot vote on its own object
    if await _is_operator_coi(uid, asset_ids):
        raise HTTPException(status_code=403,
                            detail="Конфлікт інтересів: оператор не може голосувати по власному об'єкту")
    weight = await _voter_weight(uid, asset_ids)
    if weight <= 0:
        raise HTTPException(status_code=403, detail="Голосувати можуть лише власники часток об'єкта")
    await db.lumen_gov_votes.update_one(
        {"proposal_id": pid, "voter_id": uid},
        {"$set": {"choice": payload.choice, "weight": weight,
                  "voter_name": user.get("name"), "updated_at": _now()},
         "$setOnInsert": {"id": f"gv-{uuid.uuid4().hex[:12]}", "created_at": _now()}},
        upsert=True)
    return await _proposal_view(await db.lumen_gov_proposals.find_one({"id": pid}, {"_id": 0}), uid)


# ════════════════════════════════════════════════════════════════════════════
# G6 / G9 — Institutional reporting + dashboard
# ════════════════════════════════════════════════════════════════════════════

async def _my_holdings(uid: str) -> dict:
    """Aggregate an investor's exposure across assets/SPVs (and funds)."""
    certs = await _active_certs({"investor_id": uid})
    by_asset: dict[str, dict] = {}
    total_value = 0.0
    for c in certs:
        aid = c.get("asset_id")
        row = by_asset.setdefault(aid, {"asset_id": aid, "asset_title": c.get("asset_title"),
                                        "spv_id": c.get("spv_id"), "spv_name": c.get("spv_name"),
                                        "units": 0.0, "value_uah": 0.0, "ownership_percent": 0.0})
        row["units"] += float(c.get("units") or 0)
        row["value_uah"] += float(c.get("value_uah") or 0)
        row["ownership_percent"] += float(c.get("ownership_percent") or 0)
        total_value += float(c.get("value_uah") or 0)
    holdings = list(by_asset.values())
    for h in holdings:
        h["value_uah"] = _round2(h["value_uah"])
        h["ownership_percent"] = round(h["ownership_percent"], 3)
        h["units"] = round(h["units"], 2)
    holdings.sort(key=lambda x: x["value_uah"], reverse=True)
    # which funds contain my SPVs
    my_spv_ids = {h["spv_id"] for h in holdings if h.get("spv_id")}
    funds = []
    async for f in db.lumen_funds.find({"spv_ids": {"$in": list(my_spv_ids)}}, {"_id": 0}) if my_spv_ids else _empty():
        nav, _ = await _fund_nav_and_holdings(f)
        funds.append({"id": f["id"], "name": f.get("name"), "nav_uah": nav})
    return {"holdings": holdings, "total_value_uah": _round2(total_value),
            "assets_count": len(holdings), "spv_count": len(my_spv_ids), "funds": funds}


async def _empty():
    return
    yield  # pragma: no cover


@router.get("/institutional/portfolio")
async def institutional_portfolio(ctx=Depends(require_institutional)):
    return await _my_holdings(_uid(ctx["user"]))


@router.get("/institutional/dashboard")
async def institutional_dashboard(ctx=Depends(require_institutional)):
    uid = _uid(ctx["user"])
    seg = ctx["segment"]
    my = await _my_holdings(uid)
    funds = []
    async for f in db.lumen_funds.find({"status": {"$ne": "forming"}}, {"_id": 0}).sort("created_at", 1):
        nav, holdings = await _fund_nav_and_holdings(f)
        funds.append(_fund_public(f, nav, holdings))
    synds = []
    async for s in db.lumen_syndicates.find({"status": {"$nin": ["closed"]}}, {"_id": 0}).sort("created_at", -1):
        synds.append(await _syndicate_state(s))
    ubo_count = await db.lumen_beneficial_owners.count_documents({"investor_id": uid})
    matrix = await _matrix()
    rule = matrix.get(seg) or DEFAULT_MATRIX[seg]
    return {
        "segment": seg, "segment_label": SEGMENT_LABELS_UK[seg],
        "portfolio": my, "funds": funds, "syndicates": synds,
        "compliance": {"segment": seg, "segment_label": SEGMENT_LABELS_UK[seg],
                       "max_ticket_uah": rule.get("max_ticket_uah"),
                       "requires_ubo": rule.get("requires_ubo"),
                       "ubo_declared": ubo_count > 0},
    }


# ════════════════════════════════════════════════════════════════════════════
# G10 — Trust Graph
# ════════════════════════════════════════════════════════════════════════════

async def _trust_graph(asset_ids: list[str], mask: bool = False) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(nid, ntype, label, meta=None):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": label, **(meta or {})}

    for aid in asset_ids:
        a = await db.lumen_assets.find_one({"id": aid}, {"_id": 0})
        if not a:
            continue
        add_node(f"asset:{aid}", "asset", a.get("title"), {"category": a.get("category")})
        # operator
        if a.get("operator_id"):
            op = await db.lumen_operators.find_one({"id": a["operator_id"]}, {"_id": 0, "name": 1, "status": 1})
            if op:
                onid = f"operator:{a['operator_id']}"
                add_node(onid, "operator", op.get("name"),
                         {"verified": op.get("status") in ("verified", "approved")})
                edges.append({"from": onid, "to": f"asset:{aid}", "rel": "manages"})
        # spv
        spv = await _spv_for_asset(aid)
        if spv:
            snid = f"spv:{spv['id']}"
            add_node(snid, "spv", spv.get("name"), {"jurisdiction": spv.get("jurisdiction")})
            edges.append({"from": snid, "to": f"asset:{aid}", "rel": "owns"})
            # fund containing spv
            fund = await db.lumen_funds.find_one({"spv_ids": spv["id"]}, {"_id": 0, "id": 1, "name": 1})
            if fund:
                fnid = f"fund:{fund['id']}"
                add_node(fnid, "fund", fund.get("name"))
                edges.append({"from": fnid, "to": snid, "rel": "holds"})
            # investors via certificates
            async for c in db.lumen_certificates.find({"asset_id": aid, "status": {"$ne": "voided"}}, {"_id": 0}):
                iid = c.get("investor_id")
                inid = f"investor:{iid}"
                label = "Інвестор" if mask else (c.get("investor_name") or "Інвестор")
                add_node(inid, "investor", label)
                cnid = f"cert:{c.get('id')}"
                add_node(cnid, "certificate", c.get("certificate_number"),
                         {"ownership_percent": c.get("ownership_percent")})
                edges.append({"from": inid, "to": cnid, "rel": "holds"})
                edges.append({"from": cnid, "to": snid, "rel": "in_spv"})
    return {"nodes": list(nodes.values()), "edges": edges,
            "counts": {"nodes": len(nodes), "edges": len(edges)}}


@router.get("/admin/institutional/trust-graph")
async def admin_trust_graph(asset_id: Optional[str] = None, _=Depends(require_admin)):
    if asset_id:
        ids = [asset_id]
    else:
        ids = [a["id"] async for a in db.lumen_assets.find({}, {"_id": 0, "id": 1})]
    return await _trust_graph(ids, mask=False)


@router.get("/institutional/assets/{asset_id}/trust-graph")
async def public_trust_graph(asset_id: str):
    return await _trust_graph([asset_id], mask=True)


# ════════════════════════════════════════════════════════════════════════════
# Indexes + idempotent demo seed
# ════════════════════════════════════════════════════════════════════════════

async def ensure_institutional_indexes() -> None:
    try:
        await db.lumen_funds.create_index([("status", 1)])
        await db.lumen_funds.create_index([("spv_ids", 1)])
        await db.lumen_syndicates.create_index([("status", 1)])
        await db.lumen_syndicate_participants.create_index([("syndicate_id", 1)])
        await db.lumen_beneficial_owners.create_index([("investor_id", 1)])
        await db.lumen_gov_proposals.create_index([("status", 1)])
        await db.lumen_gov_votes.create_index([("proposal_id", 1), ("voter_id", 1)], unique=True)
        await db.lumen_compliance_matrix.create_index([("segment", 1)], unique=True)
    except Exception:
        logger.exception("institutional indexes failed")


async def seed_institutional_os_demo() -> dict:
    await ensure_institutional_indexes()
    stats = {"matrix": 0, "funds": 0, "syndicates": 0, "proposals": 0, "ubo": 0}

    # G8 — seed compliance matrix (idempotent)
    for seg in SEGMENTS:
        existing = await db.lumen_compliance_matrix.find_one({"segment": seg})
        if not existing:
            await db.lumen_compliance_matrix.insert_one({
                "segment": seg, **DEFAULT_MATRIX[seg], "created_at": _now(), "updated_at": _now()})
            stats["matrix"] += 1

    # G3 — seed funds grouping existing SPVs (idempotent by name)
    spvs = []
    async for s in db.lumen_spvs.find({}, {"_id": 0, "id": 1, "asset_id": 1}).sort("created_at", 1):
        spvs.append(s)
    podil_op = await db.lumen_operators.find_one({"name": "Podil Development Partners"}, {"_id": 0, "id": 1})
    lumen_op = await db.lumen_operators.find_one({"name": "LUMEN Capital"}, {"_id": 0, "id": 1})

    if await db.lumen_funds.count_documents({}) == 0 and spvs:
        # residential fund = first 2 SPVs; flagship fund = next 2
        residential = [s["id"] for s in spvs[:2]]
        flagship = [s["id"] for s in spvs[2:4]]
        await db.lumen_funds.insert_one({
            "id": "fund-ua-residential", "name": "Ukraine Residential Fund I",
            "kind": "residential", "strategy": "Дохідна житлова нерухомість у великих містах",
            "region": "Україна", "target_size_uah": 50_000_000,
            "manager_operator_id": (podil_op or {}).get("id"),
            "description": "Контейнер житлових SPV. Інвестор купує частку фонду, а не окремий об'єкт.",
            "status": "active", "spv_ids": residential, "created_at": _now(), "updated_at": _now()})
        await db.lumen_funds.insert_one({
            "id": "fund-flagship", "name": "LUMEN Flagship Fund",
            "kind": "mixed", "strategy": "Флагманські об'єкти під управлінням LUMEN Capital",
            "region": "Україна", "target_size_uah": 80_000_000,
            "manager_operator_id": (lumen_op or {}).get("id"),
            "description": "Змішаний фонд флагманських активів.",
            "status": "active", "spv_ids": flagship, "created_at": _now(), "updated_at": _now()})
        stats["funds"] = 2

    # G4 — seed one open syndicate on an existing asset
    if await db.lumen_syndicates.count_documents({}) == 0:
        a = await db.lumen_assets.find_one({"id": "asset-vyshneve-cottage"}, {"_id": 0, "id": 1, "title": 1}) \
            or await db.lumen_assets.find_one({}, {"_id": 0, "id": 1, "title": 1})
        if a:
            lead = await db.users.find_one({"email": "client@atlas.dev"}, {"_id": 0, "user_id": 1, "name": 1})
            sid = "synd-vyshneve"
            await db.lumen_syndicates.insert_one({
                "id": sid, "title": f"Синдикат: {a.get('title')}", "asset_id": a["id"],
                "asset_title": a.get("title"), "lead_investor_id": (lead or {}).get("user_id"),
                "lead_investor_name": (lead or {}).get("name"), "target_uah": 3_000_000,
                "lead_pct": 25.0, "min_ticket_uah": 100000, "status": "filling",
                "deadline": None, "created_at": _now(), "updated_at": _now()})
            if lead:
                await db.lumen_syndicate_participants.insert_one({
                    "id": f"sp-{uuid.uuid4().hex[:12]}", "syndicate_id": sid,
                    "investor_id": lead["user_id"], "investor_name": lead.get("name"),
                    "amount_uah": 750000, "role": "lead", "status": "confirmed", "created_at": _now()})
            stats["syndicates"] = 1

    # G7 — seed one open governance proposal on an asset
    if await db.lumen_gov_proposals.count_documents({}) == 0:
        a = await db.lumen_assets.find_one({"id": "asset-podilskyi"}, {"_id": 0, "id": 1, "title": 1}) \
            or await db.lumen_assets.find_one({}, {"_id": 0, "id": 1, "title": 1})
        if a:
            await db.lumen_gov_proposals.insert_one({
                "id": "gp-podil-reserve", "scope": "asset", "scope_id": a["id"],
                "scope_label": a.get("title"),
                "title": "Реінвестувати 30% доходу в капітальний ремонт?",
                "description": "Пропозиція спрямувати частину доходу на ремонт фасаду та ліфтів.",
                "options": ["За", "Проти", "Утримуюсь"], "status": "open",
                "opens_at": _now(), "closes_at": _now() + timedelta(days=21),
                "created_by": "system", "created_at": _now(), "updated_at": _now()})
            stats["proposals"] = 1

    # G5 — seed a UBO declaration for the demo client (idempotent)
    client = await db.users.find_one({"email": "client@atlas.dev"}, {"_id": 0, "user_id": 1, "name": 1})
    if client and await db.lumen_beneficial_owners.count_documents({"investor_id": client["user_id"]}) == 0:
        await db.lumen_beneficial_owners.insert_one({
            "id": f"ubo-{uuid.uuid4().hex[:12]}", "investor_id": client["user_id"],
            "ubo_name": client.get("name") or "Acme Client", "relationship": "self",
            "ownership_pct": 100.0, "is_pep": False, "country": "UA",
            "verified": True, "created_at": _now()})
        stats["ubo"] = 1

    # G9 — seed a demo institutional investor (Family Office) so the cabinet is demoable
    try:
        import bcrypt as _bcrypt
        fam = await db.users.find_one({"email": "family@atlas.dev"}, {"_id": 0, "user_id": 1})
        if not fam:
            fam_uid = f"user_{uuid.uuid4().hex[:12]}"
            pw = _bcrypt.hashpw("family123".encode(), _bcrypt.gensalt()).decode()
            await db.users.insert_one({
                "user_id": fam_uid, "email": "family@atlas.dev", "name": "Helios Family Office",
                "password_hash": pw, "role": "client", "roles": ["client"],
                "active_role": "client", "states": [], "kyc_status": "approved",
                "source": "phase_g_seed", "created_at": _now(),
            })
            await db.lumen_investor_profiles.insert_one({
                "id": f"prof-{uuid.uuid4().hex[:12]}", "user_id": fam_uid,
                "full_name": "Helios Family Office", "country": "UA", "residency_country": "UA",
                "accreditation_status": "approved", "kyc_status": "approved",
                "segment": "institutional", "segment_override": True,
                "created_at": _now(), "updated_at": _now(),
            })
            await db.lumen_beneficial_owners.insert_one({
                "id": f"ubo-{uuid.uuid4().hex[:12]}", "investor_id": fam_uid,
                "ubo_name": "Andriy Helios", "relationship": "shareholder",
                "ownership_pct": 100.0, "is_pep": False, "country": "UA",
                "verified": True, "created_at": _now()})
            stats["institutional_user"] = 1
    except Exception:
        logger.exception("institutional demo user seed failed")

    return stats


# ════════════════════════════════════════════════════════════════════════════
# Demo holdings seed — populate the REAL ownership chain so every Phase G
# surface (cap tables, trust graph, governance weights, fund NAV, portfolios)
# has fact-based data. Drives the production engines (unit registry + cert
# reconcile) — NOT hand-faked numbers. Idempotent: skips once certificates exist.
# ════════════════════════════════════════════════════════════════════════════

DEMO_HOLDERS = [
    # email, name, segment, password (existing accounts keep their password)
    {"email": "family@atlas.dev", "name": "Helios Family Office", "segment": "institutional"},
    {"email": "olena.k@lumen.test", "name": "Олена Коваленко", "segment": "qualified", "password": "demo123"},
    {"email": "ihor.p@lumen.test", "name": "Ігор Петренко", "segment": "strategic", "password": "demo123"},
    {"email": "maria.s@lumen.test", "name": "Марія Шевченко", "segment": "retail", "password": "demo123"},
]

# (asset_id, holder_email, amount_uah) — multiple holders per asset → real cap tables
DEMO_ALLOCATION = [
    ("asset-podilskyi", "family@atlas.dev", 1_500_000),
    ("asset-podilskyi", "olena.k@lumen.test", 600_000),
    ("asset-podilskyi", "maria.s@lumen.test", 150_000),
    ("asset-odessa-apartments", "family@atlas.dev", 900_000),
    ("asset-odessa-apartments", "ihor.p@lumen.test", 1_200_000),
    ("asset-lavr-tc", "olena.k@lumen.test", 450_000),
    ("asset-lavr-tc", "maria.s@lumen.test", 90_000),
    ("asset-rivne-warehouse", "ihor.p@lumen.test", 700_000),
    ("asset-stoyanka-land", "ihor.p@lumen.test", 300_000),
]


async def _ensure_demo_holder(spec: dict) -> Optional[str]:
    """Ensure a demo investor user + investor profile exist. Returns user_id."""
    import bcrypt as _bcrypt
    u = await db.users.find_one({"email": spec["email"]}, {"_id": 0, "user_id": 1})
    if u:
        uid = u["user_id"]
    else:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        pw = _bcrypt.hashpw(str(spec.get("password") or "demo123").encode(), _bcrypt.gensalt()).decode()
        await db.users.insert_one({
            "user_id": uid, "email": spec["email"], "name": spec["name"],
            "password_hash": pw, "role": "client", "roles": ["client"],
            "active_role": "client", "states": [], "kyc_status": "approved",
            "source": "phase_g_holdings_seed", "created_at": _now(),
        })
    prof = await db.lumen_investor_profiles.find_one({"user_id": uid}, {"_id": 0, "id": 1})
    if not prof:
        await db.lumen_investor_profiles.insert_one({
            "id": f"prof-{uuid.uuid4().hex[:12]}", "user_id": uid,
            "full_name": spec["name"], "country": "UA", "residency_country": "UA",
            "accreditation_status": "approved", "kyc_status": "approved",
            "segment": spec["segment"], "segment_override": True,
            "created_at": _now(), "updated_at": _now(),
        })
    else:
        # keep segment in sync for the demo
        await db.lumen_investor_profiles.update_one(
            {"user_id": uid},
            {"$set": {"segment": spec["segment"], "accreditation_status": "approved",
                      "kyc_status": "approved", "updated_at": _now()}})
    return uid


async def seed_demo_holdings() -> dict:
    """Populate ownerships + certificates through the real engines (idempotent)."""
    active_certs = await db.lumen_certificates.count_documents({"status": {"$ne": "voided"}})
    if active_certs > 0:
        return {"skipped": "holdings already present", "active_certificates": active_certs}

    # 1) demo investors
    uid_by_email: dict[str, str] = {}
    for spec in DEMO_HOLDERS:
        uid = await _ensure_demo_holder(spec)
        if uid:
            uid_by_email[spec["email"]] = uid

    # 2) active investments (the canonical source the engines read from)
    affected_assets: set[str] = set()
    investments = 0
    for asset_id, email, amount in DEMO_ALLOCATION:
        asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "id": 1, "title": 1,
                                                                  "location": 1, "target_yield": 1})
        uid = uid_by_email.get(email)
        if not asset or not uid:
            continue
        # idempotent: one demo investment per (investor, asset)
        exists = await db.lumen_investments.find_one(
            {"asset_id": asset_id, "investor_id": uid, "source": "phase_g_holdings_seed"})
        if exists:
            affected_assets.add(asset_id)
            continue
        now = _now()
        await db.lumen_investments.insert_one({
            "id": f"inv-{uuid.uuid4().hex[:12]}", "asset_id": asset_id, "round_id": None,
            "investor_id": uid, "intent_id": None, "amount": float(amount), "amount_uah": float(amount),
            "invested_amount": float(amount), "units": float(amount),
            "status": "active", "payment_reference": None, "contract_id": None,
            "invested_at": now, "matured_at": None,
            "asset_title": asset.get("title"), "asset_location": asset.get("location"),
            "round_label": "Раунд I", "current_yield": float(asset.get("target_yield") or 0),
            "source": "phase_g_holdings_seed", "created_at": now, "updated_at": now,
        })
        investments += 1
        affected_assets.add(asset_id)

    # 3) drive the REAL engines: unit registry recompute → certificate reconcile
    recomputed = 0
    certs_issued = 0
    try:
        import lumen_unit_registry as _ur
        import lumen_certificates as _certs
        from lumen_investment_core import _recompute_asset_funding as _raf
        for asset_id in sorted(affected_assets):
            try:
                await _raf(asset_id)
            except Exception:
                logger.exception("funding recompute failed for %s", asset_id)
            await _ur.recompute_asset(asset_id, reason="phase_g_holdings_seed", emit_genesis=True)
            recomputed += 1
            res = await _certs.reconcile_asset(asset_id, actor="phase_g_holdings_seed")
            certs_issued += int((res or {}).get("issued", 0) or 0)
    except Exception:
        logger.exception("demo holdings engine pass failed")

    return {"investors": len(uid_by_email), "investments": investments,
            "assets_recomputed": recomputed, "certificates_issued": certs_issued}
