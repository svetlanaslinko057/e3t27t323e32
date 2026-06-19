"""
LUMEN 2.0 — Phase LR2.6 — Institutional Overview (Chairman Dashboard)
======================================================================

One screen for the chairperson / institutional COO. Surfaces the *whole*
state of the platform in one aggregated payload — no scrolling between
tabs to understand AUM, NAV, fund pipeline, capital flow, compliance
posture and pending decisions.

Read-only, admin-only.

Endpoint
--------
GET /api/admin/institutional/overview
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends

from lumen_api import db, require_admin, _now, _iso

logger = logging.getLogger("lumen.institutional_overview")
router = APIRouter(prefix="/api/admin/institutional", tags=["lumen-overview"])


async def _kpi_block() -> dict:
    # AUM = sum of active certificate NAV
    aum = 0.0
    async for c in db.lumen_certificates.find({"status": {"$ne": "voided"}},
                                                {"_id": 0, "value_uah": 1}):
        aum += float(c.get("value_uah") or 0)

    # Pending payouts
    payouts_pending = 0.0
    async for r in db.lumen_payout_records.find({"status": "pending"},
                                                  {"_id": 0, "amount": 1}):
        payouts_pending += float(r.get("amount") or 0)

    # Distributions last 90 days
    cutoff = _now() - timedelta(days=90)
    paid_90 = 0.0
    async for r in db.lumen_payout_records.find(
            {"status": "paid", "paid_at": {"$gte": cutoff}}, {"_id": 0, "amount": 1}):
        paid_90 += float(r.get("amount") or 0)

    return {
        "aum_uah": round(aum, 2),
        "payouts_pending_uah": round(payouts_pending, 2),
        "distributions_90d_uah": round(paid_90, 2),
        "assets": await db.lumen_assets.count_documents({}),
        "investors": await db.lumen_investor_profiles.count_documents({}),
        "funds_active": await db.lumen_funds.count_documents({"status": {"$nin":
                                                                ["closed", "quarantined"]}}),
        "spvs": await db.lumen_spvs.count_documents({}),
        "certificates_active": await db.lumen_certificates.count_documents(
            {"status": {"$ne": "voided"}}),
    }


async def _fund_pipeline() -> list[dict]:
    out: list[dict] = []
    async for f in db.lumen_funds.find({}, {"_id": 0}):
        commit = 0.0
        async for c in db.lumen_lp_commitments.find({"fund_id": f["id"]},
                                                      {"_id": 0, "amount_uah": 1}):
            commit += float(c.get("amount_uah") or 0)
        called = 0.0
        paid = 0.0
        async for d in db.lumen_lp_drawdowns.find({"fund_id": f["id"]},
                                                    {"_id": 0, "amount_uah": 1, "paid_at": 1}):
            called += float(d.get("amount_uah") or 0)
            if d.get("paid_at"):
                paid += float(d.get("amount_uah") or 0)
        lp_count = await db.lumen_lp_commitments.count_documents(
            {"fund_id": f["id"], "role": "LP"})
        nav = 0.0
        try:
            from lumen_institutional_os import _fund_nav_and_holdings
            nav, _ = await _fund_nav_and_holdings(f)
        except Exception:
            pass
        out.append({
            "fund_id": f["id"], "name": f.get("name"),
            "kind": f.get("kind"), "status": f.get("status"),
            "target_uah": float(f.get("target_size_uah") or 0),
            "committed_uah": round(commit, 2),
            "called_uah": round(called, 2),
            "paid_uah": round(paid, 2),
            "uncalled_uah": round(commit - called, 2),
            "nav_uah": round(float(nav), 2),
            "lp_count": lp_count,
            "fill_pct": round(commit / float(f.get("target_size_uah") or 1) * 100, 1),
        })
    out.sort(key=lambda r: -r["committed_uah"])
    return out


async def _compliance_posture() -> dict:
    """Aggregate compliance health from per-slot documents (lumen_compliance_documents)."""
    by_status: dict[str, int] = {}
    expiring_soon = 0
    expired = 0
    cutoff = _now() + timedelta(days=45)
    investors: set[str] = set()
    async for d in db.lumen_compliance_documents.find({}, {"_id": 0}):
        st = d.get("status") or "missing"
        by_status[st] = by_status.get(st, 0) + 1
        investors.add(d.get("investor_id") or "")
        exp = d.get("expires_at")
        if exp:
            try:
                if exp.tzinfo is None:
                    from datetime import timezone as _tz
                    exp = exp.replace(tzinfo=_tz.utc)
            except Exception:
                continue
            if exp < _now():
                expired += 1
            elif exp <= cutoff:
                expiring_soon += 1
    # Score per investor via aggregator (best-effort, samples up to 25)
    sample_scores = []
    for inv in list(investors)[:25]:
        try:
            from lumen_compliance_vault import _compute_profile  # type: ignore
            p = await _compute_profile(inv)
            if isinstance(p.get("score"), (int, float)):
                sample_scores.append(float(p["score"]))
        except Exception:
            pass
    avg = round(sum(sample_scores) / len(sample_scores), 1) if sample_scores else None
    return {"by_status": by_status,
            "average_score": avg,
            "expirations_soon_count": expiring_soon,
            "expired_count": expired,
            "investors_covered": len(investors)}


async def _accreditation_posture() -> dict:
    """Aggregate accreditation status + level from investor profiles (Profile 2.0)."""
    by_status: dict[str, int] = {}
    by_level: dict[str, int] = {}
    async for p in db.lumen_investor_profiles.find({}, {"_id": 0,
                                                          "accreditation": 1, "segment": 1}):
        acc = p.get("accreditation") or {}
        st = acc.get("status") or "none"
        lv = acc.get("level") or (p.get("segment") or "retail")
        by_status[st] = by_status.get(st, 0) + 1
        by_level[lv] = by_level.get(lv, 0) + 1
    return {"by_status": by_status, "by_level": by_level}


async def _pending_decisions() -> dict:
    """Items awaiting admin/chairman action."""
    accr_queue = await db.lumen_investor_profiles.count_documents(
        {"accreditation.status": "under_review"})
    gov_open = await db.lumen_gov_proposals.count_documents(
        {"status": {"$in": ["open", "voting"]}})
    try:
        secondary_open = await db.lumen_secondary_orders.count_documents(
            {"status": "open"})
    except Exception:
        secondary_open = 0
    calls_unpaid = await db.lumen_lp_drawdowns.count_documents({"paid_at": None})
    return {
        "accreditation_review": accr_queue,
        "governance_open": gov_open,
        "secondary_open": secondary_open,
        "drawdowns_unpaid": calls_unpaid,
    }


async def _recent_activity() -> list[dict]:
    items: list[dict] = []
    async for a in db.lumen_audit_log.find({}, {"_id": 0}).sort("at", -1).limit(15):
        items.append({
            "at": _iso(a.get("at")),
            "category": a.get("category"),
            "action": a.get("action"),
            "actor_email": a.get("actor_email"),
            "summary": a.get("summary"),
            "target_type": a.get("target_type"),
        })
    return items


async def _ownership_breakdown() -> list[dict]:
    """AUM by asset category."""
    by_cat: dict[str, float] = {}
    async for c in db.lumen_certificates.find({"status": {"$ne": "voided"}}, {"_id": 0}):
        a = await db.lumen_assets.find_one({"id": c.get("asset_id")},
                                             {"_id": 0, "category": 1})
        cat = (a or {}).get("category") or "інше"
        by_cat[cat] = by_cat.get(cat, 0) + float(c.get("value_uah") or 0)
    rows = [{"category": k, "value_uah": round(v, 2)} for k, v in by_cat.items()]
    rows.sort(key=lambda r: -r["value_uah"])
    total = sum(r["value_uah"] for r in rows) or 1.0
    for r in rows:
        r["share_pct"] = round(r["value_uah"] / total * 100, 1)
    return rows


@router.get("/overview")
async def institutional_overview(_=Depends(require_admin)):
    """Single payload for chairman dashboard."""
    kpi = await _kpi_block()
    funds = await _fund_pipeline()
    compliance = await _compliance_posture()
    accreditation = await _accreditation_posture()
    pending = await _pending_decisions()
    activity = await _recent_activity()
    breakdown = await _ownership_breakdown()
    return {
        "ran_at": _iso(_now()),
        "kpi": kpi,
        "funds": funds,
        "compliance": compliance,
        "accreditation": accreditation,
        "pending": pending,
        "activity": activity,
        "ownership_breakdown": breakdown,
    }


__all__ = ["router"]
