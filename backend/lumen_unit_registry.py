"""
lumen_unit_registry.py — LUMEN 2.0 / Phase A1 — Unit Registry & Ownership OS.

Replaces the legacy "1 unit == 1 UAH" float model with a deterministic
INTEGER unit registry that is the source of truth for ownership, the secondary
market order book (Phase D), certificates (Phase A2) and payouts.

Core model
──────────
  Asset
    └── total_units      (fixed, default 100 000)
    └── unit_price_uah   = target_amount / total_units
  Ownership
    └── units            : integer count of units owned

The cap-table is *derived authoritatively* from the existing domain truth —
active primary investments (lumen_investments) ± secondary share-transfers
(lumen_share_transfers) — and mapped to integer units with the
**largest-remainder method** so the conservation invariant always holds:

    Σ holder.units  ==  issued_units  ≤  total_units

New collections
───────────────
  lumen_asset_units        — per-asset unit definition + materialised totals
  lumen_ownership_events   — append-only audit log of every unit movement
  lumen_ownership_snapshots— point-in-time full cap-table snapshots

This module ADDS a parallel integer registry; it does NOT mutate the legacy
float `units` / `ownership_percent` fields, so payouts (driven by
ownership_percent) and the secondary market (driven by amount_uah) keep working
unchanged. Integer `units_int` is materialised onto ownership rows for fast
reads by the Ownership Explorer / Investor Units view.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lumen_api import db

logger = logging.getLogger("lumen.unit_registry")

DEFAULT_TOTAL_UNITS = int(os.environ.get("LUMEN_DEFAULT_TOTAL_UNITS", "100000"))

ASSET_UNITS_COLL = "lumen_asset_units"
EVENTS_COLL = "lumen_ownership_events"
SNAPSHOTS_COLL = "lumen_ownership_snapshots"

EVENT_TYPES = (
    "issue",          # primary issuance (genesis)
    "transfer_in",    # secondary buy
    "transfer_out",   # secondary sell
    "void",           # holding zeroed
    "adjust",         # admin / migration reconciliation
)

# Canonical ownership-event kinds (A3 Block 3)
KIND_CREATED = "created"
KIND_INCREASED = "increased"
KIND_DECREASED = "decreased"
KIND_TRANSFERRED = "transferred"
KIND_CLOSED = "closed"


def _canonical_kind(event_type: str, delta_units: int, balance_after: int) -> str:
    """Map a low-level event to a canonical ownership-lifecycle kind."""
    if balance_after <= 0:
        return KIND_CLOSED
    if event_type == "issue":
        return KIND_CREATED
    if delta_units > 0:
        return KIND_INCREASED if balance_after != delta_units else KIND_CREATED
    if delta_units < 0:
        return KIND_DECREASED
    return KIND_TRANSFERRED


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return v


def _strip(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    d = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = _iso(v)
    return d


def _asset_target(asset: dict) -> float:
    for k in ("target_amount", "round_target", "target", "raised_amount", "raised"):
        v = asset.get(k)
        if v:
            return float(v)
    return 0.0


def _round2(x: float) -> float:
    return round(float(x or 0) + 1e-9, 2)


def largest_remainder(weights: List[float], total: int) -> List[int]:
    """Distribute `total` integer units across holders proportionally to
    `weights`, guaranteeing Σ result == total (when Σweights > 0)."""
    s = sum(weights)
    if total <= 0 or s <= 0:
        return [0 for _ in weights]
    exact = [w / s * total for w in weights]
    floors = [int(math.floor(e)) for e in exact]
    remainder = total - sum(floors)
    # rank by largest fractional part
    order = sorted(range(len(weights)), key=lambda i: (exact[i] - floors[i]), reverse=True)
    for i in range(remainder):
        floors[order[i % len(order)]] += 1
    return floors


# ──────────────────────────────────────────────────────────────────────────────
# Indexes
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_indexes() -> None:
    try:
        await db[ASSET_UNITS_COLL].create_index([("asset_id", 1)], unique=True)
        await db[EVENTS_COLL].create_index([("asset_id", 1), ("created_at", -1)])
        await db[EVENTS_COLL].create_index([("investor_id", 1), ("created_at", -1)])
        await db[SNAPSHOTS_COLL].create_index([("asset_id", 1), ("taken_at", -1)])
        # materialised integer units lookup
        await db.lumen_ownerships.create_index([("asset_id", 1)])
    except Exception:
        logger.exception("unit-registry indexes failed")


# ──────────────────────────────────────────────────────────────────────────────
# Asset units definition
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_asset_units(asset: dict) -> dict:
    """Create (idempotent) the per-asset unit definition. total_units is stable
    once set; unit_price is (re)derived from the live target_amount."""
    asset_id = asset.get("id")
    target = _asset_target(asset)
    row = await db[ASSET_UNITS_COLL].find_one({"asset_id": asset_id})
    if not row:
        total_units = DEFAULT_TOTAL_UNITS
        unit_price = _round2(target / total_units) if total_units else 0.0
        row = {
            "id": _uuid("au-"),
            "asset_id": asset_id,
            "asset_title": asset.get("title"),
            "total_units": total_units,
            "unit_price_uah": unit_price,
            "issued_units": 0,
            "available_units": total_units,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[ASSET_UNITS_COLL].insert_one(dict(row))
    else:
        total_units = int(row.get("total_units") or DEFAULT_TOTAL_UNITS)
        unit_price = _round2(target / total_units) if total_units else 0.0
        if abs(float(row.get("unit_price_uah") or 0) - unit_price) > 0.001 \
                or row.get("asset_title") != asset.get("title"):
            await db[ASSET_UNITS_COLL].update_one(
                {"asset_id": asset_id},
                {"$set": {"unit_price_uah": unit_price,
                          "asset_title": asset.get("title"),
                          "updated_at": _now()}},
            )
            row["unit_price_uah"] = unit_price
    return _strip(row)


# ──────────────────────────────────────────────────────────────────────────────
# Authoritative cap table (UAH) — from investments ± transfers
# ──────────────────────────────────────────────────────────────────────────────

async def _cap_table_uah(asset_id: str) -> Dict[str, float]:
    """The real owned-UAH per investor for an asset (post-secondary truth)."""
    holders: Dict[str, float] = defaultdict(float)
    async for inv in db.lumen_investments.find(
        {"asset_id": asset_id, "status": "active"},
        {"investor_id": 1, "amount": 1, "invested_amount": 1, "amount_uah": 1},
    ):
        amt = float(inv.get("amount_uah") or inv.get("amount")
                    or inv.get("invested_amount") or 0)
        holders[inv["investor_id"]] += amt
    async for t in db.lumen_share_transfers.find(
        {"asset_id": asset_id},
        {"from_investor_id": 1, "to_investor_id": 1, "amount_uah": 1},
    ):
        amt = float(t.get("amount_uah") or 0)
        if t.get("to_investor_id"):
            holders[t["to_investor_id"]] += amt
        if t.get("from_investor_id"):
            holders[t["from_investor_id"]] -= amt
    # drop dust / non-positive
    return {k: _round2(v) for k, v in holders.items() if _round2(v) > 0.01}


# ──────────────────────────────────────────────────────────────────────────────
# Recompute (the heart) — derive integer units & materialise
# ──────────────────────────────────────────────────────────────────────────────

async def recompute_asset(asset_id: str, *, reason: str = "recompute",
                          emit_genesis: bool = False) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    au = await ensure_asset_units(asset)
    total_units = int(au["total_units"])
    unit_price = float(au["unit_price_uah"] or 0)

    cap = await _cap_table_uah(asset_id)
    investor_ids = list(cap.keys())
    weights = [cap[i] for i in investor_ids]

    raised = _round2(sum(weights))
    # target issued = raised / price, capped at total_units
    issued_target = min(total_units, int(round(raised / unit_price))) if unit_price else 0
    units_list = largest_remainder(weights, issued_target)
    units_by_investor = dict(zip(investor_ids, units_list))

    issued = sum(units_list)
    available = total_units - issued

    # materialise units_int onto ownership rows
    for inv_id, u in units_by_investor.items():
        await db.lumen_ownerships.update_one(
            {"investor_id": inv_id, "asset_id": asset_id},
            {"$set": {"units_int": int(u),
                      "registry_percent": round(u / total_units * 100, 4) if total_units else 0.0,
                      "unit_price_uah": unit_price,
                      "units_updated_at": _now()},
             "$setOnInsert": {"id": _uuid("own-"), "investor_id": inv_id,
                              "asset_id": asset_id, "created_at": _now()}},
            upsert=True,
        )
    # zero-out holders no longer in cap table
    async for own in db.lumen_ownerships.find(
            {"asset_id": asset_id, "units_int": {"$gt": 0}}):
        if own["investor_id"] not in units_by_investor:
            await db.lumen_ownerships.update_one(
                {"id": own["id"]},
                {"$set": {"units_int": 0, "registry_percent": 0.0,
                          "units_updated_at": _now()}})

    await db[ASSET_UNITS_COLL].update_one(
        {"asset_id": asset_id},
        {"$set": {"issued_units": int(issued), "available_units": int(available),
                  "unit_price_uah": unit_price, "updated_at": _now()}},
    )

    if emit_genesis:
        existing = await db[EVENTS_COLL].count_documents({"asset_id": asset_id})
        if existing == 0:
            for inv_id, u in units_by_investor.items():
                if u > 0:
                    await record_event(asset_id, inv_id, "issue", int(u), int(u),
                                       ref_type="primary", ref_id=None,
                                       unit_price_uah=unit_price,
                                       note="Genesis issuance (A1 migration)")

    return {
        "asset_id": asset_id,
        "total_units": total_units,
        "issued_units": int(issued),
        "available_units": int(available),
        "unit_price_uah": unit_price,
        "holders": len(units_by_investor),
        "reason": reason,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Events & snapshots
# ──────────────────────────────────────────────────────────────────────────────

async def record_event(asset_id: str, investor_id: str, event_type: str,
                        delta_units: int, balance_after: int, *,
                        ref_type: Optional[str] = None, ref_id: Optional[str] = None,
                        unit_price_uah: Optional[float] = None,
                        note: Optional[str] = None,
                        kind: Optional[str] = None,
                        certificate_id: Optional[str] = None) -> dict:
    ev = {
        "id": _uuid("oe-"),
        "asset_id": asset_id,
        "investor_id": investor_id,
        "event_type": event_type,
        "kind": kind or _canonical_kind(event_type, delta_units, balance_after),
        "delta_units": int(delta_units),
        "balance_after": int(balance_after),
        "ref_type": ref_type,
        "ref_id": ref_id,
        "unit_price_uah": unit_price_uah,
        "certificate_id": certificate_id,   # A2 hook (always present for forward-compat)
        "note": note,
        "created_at": _now(),
    }
    await db[EVENTS_COLL].insert_one(dict(ev))
    return _strip(ev)


async def create_snapshot(asset_id: str, *, reason: str = "manual",
                          created_by: Optional[str] = None) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id}) or {}
    au = await db[ASSET_UNITS_COLL].find_one({"asset_id": asset_id}) or {}
    total_units = int(au.get("total_units") or DEFAULT_TOTAL_UNITS)
    holders: List[dict] = []
    issued = 0
    async for own in db.lumen_ownerships.find(
            {"asset_id": asset_id, "units_int": {"$gt": 0}}).sort("units_int", -1):
        u = int(own.get("units_int") or 0)
        issued += u
        holders.append({
            "investor_id": own["investor_id"],
            "units": u,
            "percent": round(u / total_units * 100, 4) if total_units else 0.0,
        })
    snap = {
        "id": _uuid("snap-"),
        "asset_id": asset_id,
        "asset_title": asset.get("title"),
        "total_units": total_units,
        "issued_units": issued,
        "available_units": total_units - issued,
        "unit_price_uah": float(au.get("unit_price_uah") or 0),
        "holders": holders,
        "holders_count": len(holders),
        "reason": reason,
        "created_by": created_by,
        "taken_at": _now(),
    }
    await db[SNAPSHOTS_COLL].insert_one(dict(snap))
    return _strip(snap)


# ──────────────────────────────────────────────────────────────────────────────
# Invariants
# ──────────────────────────────────────────────────────────────────────────────

async def invariant_check(asset_id: Optional[str] = None) -> dict:
    results: List[dict] = []
    q = {"asset_id": asset_id} if asset_id else {}
    async for au in db[ASSET_UNITS_COLL].find(q):
        aid = au["asset_id"]
        total_units = int(au.get("total_units") or 0)
        issued_recorded = int(au.get("issued_units") or 0)
        issued_actual = 0
        negative = 0
        async for own in db.lumen_ownerships.find({"asset_id": aid}):
            u = int(own.get("units_int") or 0)
            if u < 0:
                negative += 1
            issued_actual += max(0, u)
        checks = {
            "conservation": issued_actual + (total_units - issued_actual) == total_units,
            "issued_matches_holders": issued_recorded == issued_actual,
            "issued_within_total": issued_actual <= total_units,
            "no_negative_units": negative == 0,
        }
        results.append({
            "asset_id": aid,
            "asset_title": au.get("asset_title"),
            "total_units": total_units,
            "issued_units": issued_actual,
            "available_units": total_units - issued_actual,
            "ok": all(checks.values()),
            "checks": checks,
        })
    return {
        "computed_at": _iso(_now()),
        "assets": results,
        "all_ok": all(r["ok"] for r in results) if results else True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Migration (idempotent) — establish integer registry across all assets
# ──────────────────────────────────────────────────────────────────────────────

async def migrate_all(*, emit_genesis: bool = True) -> dict:
    await ensure_indexes()
    migrated = 0
    async for asset in db.lumen_assets.find({}):
        try:
            await recompute_asset(asset["id"], reason="A1 migration",
                                  emit_genesis=emit_genesis)
            migrated += 1
        except Exception:
            logger.exception("migrate asset %s failed", asset.get("id"))
    inv = await invariant_check()
    return {"migrated_assets": migrated, "all_invariants_ok": inv["all_ok"]}


# ──────────────────────────────────────────────────────────────────────────────
# Secondary-market hook
# ──────────────────────────────────────────────────────────────────────────────

async def on_trade_settled(asset_id: str, seller_id: str, buyer_id: str,
                           units_uah: float, trade_id: str) -> None:
    """Called from lumen_secondary._settle_trade AFTER ownership rows updated.
    Re-derives integer units for the asset and logs transfer events."""
    try:
        au = await db[ASSET_UNITS_COLL].find_one({"asset_id": asset_id})
        unit_price = float((au or {}).get("unit_price_uah") or 0)
        delta = int(round(float(units_uah) / unit_price)) if unit_price else 0
        await recompute_asset(asset_id, reason=f"secondary trade {trade_id}")
        seller_own = await db.lumen_ownerships.find_one(
            {"investor_id": seller_id, "asset_id": asset_id})
        buyer_own = await db.lumen_ownerships.find_one(
            {"investor_id": buyer_id, "asset_id": asset_id})
        await record_event(asset_id, seller_id, "transfer_out", -delta,
                           int((seller_own or {}).get("units_int") or 0),
                           ref_type="secondary_trade", ref_id=trade_id,
                           unit_price_uah=unit_price, note="Secondary sale")
        await record_event(asset_id, buyer_id, "transfer_in", delta,
                           int((buyer_own or {}).get("units_int") or 0),
                           ref_type="secondary_trade", ref_id=trade_id,
                           unit_price_uah=unit_price, note="Secondary purchase")
    except Exception:
        logger.exception("on_trade_settled registry hook failed (trade %s)", trade_id)


# ──────────────────────────────────────────────────────────────────────────────
# Read models
# ──────────────────────────────────────────────────────────────────────────────

async def _listed_units_for_asset(asset_id: str, unit_price: float) -> Dict[str, int]:
    """Units currently locked in active/partial secondary listings, per seller."""
    out: Dict[str, int] = defaultdict(int)
    if unit_price <= 0:
        return out
    async for L in db.lumen_secondary_listings.find(
        {"asset_id": asset_id, "status": {"$in": ["active", "partially_filled", "draft"]}},
        {"seller_id": 1, "units_uah": 1, "filled_units_uah": 1},
    ):
        remaining = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        if remaining > 0:
            out[L["seller_id"]] += int(round(remaining / unit_price))
    return out


async def get_asset_registry(asset_id: str) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    au = await ensure_asset_units(asset)
    total_units = int(au["total_units"])
    unit_price = float(au["unit_price_uah"] or 0)

    listed_by_seller = await _listed_units_for_asset(asset_id, unit_price)
    listed_total = sum(listed_by_seller.values())

    holders: List[dict] = []
    issued = 0
    async for own in db.lumen_ownerships.find(
            {"asset_id": asset_id, "units_int": {"$gt": 0}}).sort("units_int", -1):
        u = int(own.get("units_int") or 0)
        issued += u
        inv = await db.users.find_one(
            {"$or": [{"user_id": own["investor_id"]}, {"id": own["investor_id"]}]},
            {"name": 1, "email": 1})
        holders.append({
            "investor_id": own["investor_id"],
            "investor_name": (inv or {}).get("name") or (inv or {}).get("email") or own["investor_id"][:10],
            "units": u,
            "percent": round(u / total_units * 100, 4) if total_units else 0.0,
            "value_uah": _round2(u * unit_price),
            "listed_units": int(listed_by_seller.get(own["investor_id"], 0)),
        })

    available = total_units - issued
    events = []
    async for e in db[EVENTS_COLL].find({"asset_id": asset_id}).sort("created_at", -1).limit(20):
        events.append(_strip(e))

    return {
        "asset_id": asset_id,
        "asset_title": asset.get("title"),
        "category": asset.get("category"),
        "target_amount": _asset_target(asset),
        "total_units": total_units,
        "issued_units": issued,
        "available_units": available,
        "listed_units": listed_total,
        "locked_units": listed_total,
        "unit_price_uah": unit_price,
        "holders_count": len(holders),
        "holders": holders,
        "recent_events": events,
    }


async def get_registry_overview() -> dict:
    assets: List[dict] = []
    tot_total = tot_issued = tot_listed = 0
    async for asset in db.lumen_assets.find({}).sort("created_at", -1):
        au = await ensure_asset_units(asset)
        total_units = int(au["total_units"])
        issued = int(au.get("issued_units") or 0)
        unit_price = float(au["unit_price_uah"] or 0)
        listed_map = await _listed_units_for_asset(asset["id"], unit_price)
        listed = sum(listed_map.values())
        holders = await db.lumen_ownerships.count_documents(
            {"asset_id": asset["id"], "units_int": {"$gt": 0}})
        assets.append({
            "asset_id": asset["id"],
            "asset_title": asset.get("title"),
            "category": asset.get("category"),
            "status": asset.get("status"),
            "total_units": total_units,
            "issued_units": issued,
            "available_units": total_units - issued,
            "listed_units": listed,
            "unit_price_uah": unit_price,
            "holders_count": holders,
            "subscription_pct": round(issued / total_units * 100, 2) if total_units else 0.0,
        })
        tot_total += total_units
        tot_issued += issued
        tot_listed += listed
    return {
        "computed_at": _iso(_now()),
        "totals": {
            "assets": len(assets),
            "total_units": tot_total,
            "issued_units": tot_issued,
            "available_units": tot_total - tot_issued,
            "listed_units": tot_listed,
        },
        "assets": assets,
    }


async def get_investor_units(investor_id: str) -> dict:
    holdings: List[dict] = []
    total_value = 0.0
    async for own in db.lumen_ownerships.find(
            {"investor_id": investor_id, "units_int": {"$gt": 0}}).sort("units_int", -1):
        asset = await db.lumen_assets.find_one({"id": own["asset_id"]}) or {}
        au = await db[ASSET_UNITS_COLL].find_one({"asset_id": own["asset_id"]}) or {}
        total_units = int(au.get("total_units") or DEFAULT_TOTAL_UNITS)
        unit_price = float(au.get("unit_price_uah") or 0)
        u = int(own.get("units_int") or 0)
        value = _round2(u * unit_price)
        total_value += value
        holdings.append({
            "asset_id": own["asset_id"],
            "asset_title": asset.get("title"),
            "category": asset.get("category"),
            "location": asset.get("location"),
            "cover_url": asset.get("cover_url"),
            "units": u,
            "total_units": total_units,
            "percent": round(u / total_units * 100, 4) if total_units else 0.0,
            "unit_price_uah": unit_price,
            "value_uah": value,
        })
    return {
        "investor_id": investor_id,
        "total_units": sum(h["units"] for h in holdings),
        "total_value_uah": _round2(total_value),
        "assets_count": len(holdings),
        "holdings": holdings,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

def build_registry_router(db_ignored, get_current_user, require_admin) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["unit-registry"])

    # ---- Investor -----------------------------------------------------------
    @router.get("/investor/units")
    async def investor_units(user=Depends(get_current_user)):
        return await get_investor_units(user["id"])

    @router.get("/investor/units/{asset_id}/events")
    async def investor_unit_events(asset_id: str, user=Depends(get_current_user)):
        items = []
        async for e in db[EVENTS_COLL].find(
                {"asset_id": asset_id, "investor_id": user["id"]}
        ).sort("created_at", -1).limit(100):
            items.append(_strip(e))
        return {"items": items, "total": len(items)}

    # ---- Admin --------------------------------------------------------------
    @router.get("/admin/registry/summary")
    async def admin_registry_summary(_=Depends(require_admin)):
        return await get_registry_overview()

    @router.get("/admin/registry/asset/{asset_id}")
    async def admin_registry_asset(asset_id: str, _=Depends(require_admin)):
        return await get_asset_registry(asset_id)

    @router.get("/admin/registry/asset/{asset_id}/events")
    async def admin_registry_events(asset_id: str, _=Depends(require_admin),
                                    limit: int = Query(100, le=500)):
        items = []
        async for e in db[EVENTS_COLL].find({"asset_id": asset_id}).sort(
                "created_at", -1).limit(limit):
            items.append(_strip(e))
        return {"items": items, "total": len(items)}

    @router.get("/admin/registry/asset/{asset_id}/snapshots")
    async def admin_registry_snapshots(asset_id: str, _=Depends(require_admin)):
        items = []
        async for s in db[SNAPSHOTS_COLL].find({"asset_id": asset_id}).sort(
                "taken_at", -1).limit(50):
            items.append(_strip(s))
        return {"items": items, "total": len(items)}

    @router.post("/admin/registry/asset/{asset_id}/snapshot")
    async def admin_create_snapshot(asset_id: str, admin=Depends(require_admin)):
        snap = await create_snapshot(asset_id, reason="manual",
                                     created_by=admin.get("id"))
        return {"ok": True, "snapshot": snap}

    @router.post("/admin/registry/asset/{asset_id}/recompute")
    async def admin_recompute_asset(asset_id: str, _=Depends(require_admin)):
        res = await recompute_asset(asset_id, reason="admin manual recompute")
        return {"ok": True, "result": res}

    @router.get("/admin/registry/invariants")
    async def admin_invariants(_=Depends(require_admin),
                               asset_id: Optional[str] = None):
        return await invariant_check(asset_id)

    @router.post("/admin/registry/migrate")
    async def admin_migrate(_=Depends(require_admin)):
        return await migrate_all(emit_genesis=True)

    return router
