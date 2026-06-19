"""
LUMEN Sprint 10.1 — Data Reconciliation

Purpose: close the I2 invariant on legacy seed data so that

    asset.raised_amount == Σ active investments

for every asset BEFORE Sprint 11 (Banking & Settlement) connects real money.

Behavior:
  • For each lumen_assets document, recompute raised_amount from active
    investments via the canonical `_recompute_asset_funding()` helper.
  • For ownerships: ensure each (investor, asset) row matches sum of active
    investments. Stale rows (no matching investment) are zeroed.
  • Idempotent. Safe to run at any time.

Run modes:
  • startup bootstrap (`reconcile_at_startup` env flag) — auto-fix at boot
  • admin endpoint   — POST /api/admin/reconcile/run  (manual trigger)
  • dry-run endpoint — GET  /api/admin/reconcile/preview

Every reconcile run writes one audit row (category=system, action=reconcile).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request

from lumen_api import db, require_admin, _now, _iso, _strip_mongo
from lumen_audit import write_audit
from lumen_investment_core import _recompute_asset_funding

logger = logging.getLogger("lumen.reconciliation")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

async def _preview_assets() -> list[dict]:
    out = []
    async for asset in db.lumen_assets.find({}, {"id": 1, "title": 1,
                                                  "raised_amount": 1, "raised": 1}):
        aid = asset.get("id")
        confirmed = 0.0
        async for inv in db.lumen_investments.find(
            {"asset_id": aid, "status": "active"},
            {"amount": 1, "invested_amount": 1},
        ):
            confirmed += float(inv.get("amount") or inv.get("invested_amount") or 0)
        before = float(asset.get("raised_amount") or 0)
        if abs(before - confirmed) > 0.5:
            out.append({
                "asset_id": aid,
                "title": asset.get("title"),
                "raised_amount_before": round(before, 2),
                "confirmed_funding": round(confirmed, 2),
                "delta_uah": round(before - confirmed, 2),
            })
    return out


async def _preview_ownerships() -> list[dict]:
    """Find ownership rows whose amount diverges from sum of active investments."""
    out = []
    seen_pairs: set[tuple[str, str]] = set()
    async for own in db.lumen_ownerships.find({}):
        iid = own.get("investor_id")
        aid = own.get("asset_id")
        if not iid or not aid:
            continue
        seen_pairs.add((iid, aid))
        confirmed = 0.0
        async for inv in db.lumen_investments.find(
            {"investor_id": iid, "asset_id": aid, "status": "active"},
            {"amount": 1, "invested_amount": 1},
        ):
            confirmed += float(inv.get("amount") or inv.get("invested_amount") or 0)
        before = float(own.get("amount_uah") or own.get("amount") or 0)
        if abs(before - confirmed) > 0.5:
            out.append({
                "investor_id": iid, "asset_id": aid,
                "ownership_before": round(before, 2),
                "confirmed_funding": round(confirmed, 2),
                "delta_uah": round(before - confirmed, 2),
            })
    return out


async def reconcile_assets() -> dict:
    """Recompute raised_amount + investors_count for every asset."""
    touched = 0
    fixed = []
    async for asset in db.lumen_assets.find({}, {"id": 1, "title": 1, "raised_amount": 1}):
        aid = asset.get("id")
        before = float(asset.get("raised_amount") or 0)
        res = await _recompute_asset_funding(aid)
        after = float(res.get("raised_amount") or 0)
        if abs(before - after) > 0.5:
            fixed.append({
                "asset_id": aid,
                "title": asset.get("title"),
                "raised_amount_before": round(before, 2),
                "raised_amount_after": round(after, 2),
            })
        touched += 1
    return {"assets_touched": touched, "assets_fixed": fixed}


async def reconcile_ownerships() -> dict:
    """Sync ownership rows with the canonical formula:

        ownership = Σ primary - Σ outbound transfers + Σ inbound transfers

    This is transfer-aware (Sprint 13) so secondary-market buyers don't get
    their ownership reset to zero."""
    touched = 0
    fixed = []
    async for own in db.lumen_ownerships.find({}):
        iid = own.get("investor_id"); aid = own.get("asset_id")
        if not iid or not aid:
            continue
        primary = 0.0
        async for inv in db.lumen_investments.find(
            {"investor_id": iid, "asset_id": aid, "status": "active"},
            {"amount": 1, "invested_amount": 1, "amount_uah": 1},
        ):
            primary += float(inv.get("amount_uah") or inv.get("amount")
                             or inv.get("invested_amount") or 0)
        inflow = 0.0
        async for st in db.lumen_share_transfers.find(
            {"to_investor_id": iid, "asset_id": aid}, {"amount_uah": 1},
        ):
            inflow += float(st.get("amount_uah") or 0)
        outflow = 0.0
        async for st in db.lumen_share_transfers.find(
            {"from_investor_id": iid, "asset_id": aid}, {"amount_uah": 1},
        ):
            outflow += float(st.get("amount_uah") or 0)
        confirmed = primary + inflow - outflow
        before = float(own.get("amount_uah") or own.get("amount") or 0)
        if abs(before - confirmed) > 0.5:
            await db.lumen_ownerships.update_one(
                {"_id": own["_id"]},
                {"$set": {
                    "amount_uah": round(confirmed, 2),
                    "amount": round(confirmed, 2),
                    "updated_at": _now(),
                    "reconciled_at": _now(),
                }},
            )
            fixed.append({
                "investor_id": iid, "asset_id": aid,
                "ownership_before": round(before, 2),
                "ownership_after": round(confirmed, 2),
            })
        touched += 1
    return {"ownerships_touched": touched, "ownerships_fixed": fixed}


async def run_reconciliation(*, actor: dict | None = None,
                             request: Request | None = None) -> dict:
    a = await reconcile_assets()
    o = await reconcile_ownerships()
    summary = {
        "ran_at": _iso(_now()),
        "assets": a,
        "ownerships": o,
        "totals": {
            "assets_fixed": len(a["assets_fixed"]),
            "ownerships_fixed": len(o["ownerships_fixed"]),
        },
    }
    try:
        await write_audit(
            action="reconcile.run", category="system",
            target_type="lumen_assets", target_id=None,
            actor=actor, request=request,
            summary=(f"Reconciliation: {summary['totals']['assets_fixed']} asset(s) "
                     f"fixed, {summary['totals']['ownerships_fixed']} ownership(s) fixed"),
            meta=summary["totals"],
        )
    except Exception:
        logger.exception("audit write failed")
    return summary


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-reconciliation"])


@router.on_event("startup")
async def _reconcile_startup():
    if os.environ.get("LUMEN_RECONCILE_ON_BOOT", "1") == "1":
        try:
            res = await run_reconciliation()
            logger.info("LUMEN reconcile @ startup: assets_fixed=%s ownerships_fixed=%s",
                        res["totals"]["assets_fixed"], res["totals"]["ownerships_fixed"])
        except Exception:
            logger.exception("startup reconciliation failed")


@router.get("/admin/reconcile/preview")
async def admin_reconcile_preview(_=Depends(require_admin)):
    return {
        "assets_to_fix": await _preview_assets(),
        "ownerships_to_fix": await _preview_ownerships(),
    }


@router.post("/admin/reconcile/run")
async def admin_reconcile_run(request: Request, admin=Depends(require_admin)):
    return await run_reconciliation(actor=admin, request=request)


__all__ = ["router", "run_reconciliation", "reconcile_assets",
           "reconcile_ownerships"]
