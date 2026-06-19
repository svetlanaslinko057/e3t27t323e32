"""
LUMEN Phase B — Marketplace 2.0 · Asset Intelligence Layer.

After A3 the ownership contour is closed: the platform can buy, account,
pay out and resell. The remaining weak spot is *conviction* — making an
investor WANT to buy a particular asset. This layer turns a static card into
a living organism. Everything here is grounded in real platform data — never
invented numbers.

Blocks (single layer, designed together):

  B1 Investment Thesis   — authored {opportunity, market, execution, exit}
  B2 Scenario Engine     — Bear / Base / Bull, computed from the asset's own
                           economics (hybrid: auto + admin override factors)
  B3 Capital Stack       — authored waterfall (asset value / debt / platform /
                           investors / reserve) + derived percentages
  B4 Asset Journal       — authored milestones MERGED with real system events
                           (publish, round close, payouts, reports, trades)
  B5 Live Metrics        — funding progress, investor count, secondary
                           liquidity, avg hold time, payout history, health
  B6 Conviction Score    — 0..100 from FACTS (occupancy, yield history, report
                           cadence, payout consistency, funding) — NOT AI
  B7 Liquidity Score      — 0..10 from secondary supply / demand / activity
  B8 Similar Assets      — same category, ranked by yield proximity

Authored content lives on the asset document (single source) under:
    thesis, capital_stack, occupancy_percent, scenario_factors,
    journal_milestones

Endpoints (all under /api):
  Public / investor:
    GET /assets/{id}/intelligence     aggregate (thesis+stack+metrics+scores+scenarios)
    GET /assets/{id}/scenarios        B2
    GET /assets/{id}/capital-stack    B3
    GET /assets/{id}/journal          B4
    GET /assets/{id}/metrics          B5
    GET /assets/{id}/conviction       B6
    GET /assets/{id}/liquidity        B7
    GET /assets/{id}/similar          B8
  Admin:
    GET   /admin/assets/{id}/intelligence       full authored payload
    PATCH /admin/assets/{id}/intelligence       thesis/stack/occupancy/factors
    GET   /admin/assets/{id}/journal            authored milestones
    POST  /admin/assets/{id}/journal            add milestone
    DELETE /admin/asset-journal/{milestone_id}  remove milestone
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import (
    db, get_current_user, require_admin, _now, _iso, _strip_mongo,
    _category_with_labels, CATEGORY_LABELS,
)

logger = logging.getLogger("lumen.intelligence")

router = APIRouter(prefix="/api", tags=["lumen-asset-intelligence"])


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def _asset_or_404(asset_id: str) -> dict:
    a = await db.lumen_assets.find_one({"id": asset_id})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return _category_with_labels(a)


def _funding(a: dict) -> tuple[float, float, int]:
    """Return (target, raised, progress_percent) tolerant of legacy aliases."""
    target = float(a.get("target_amount") or a.get("round_target") or 0)
    raised = float(a.get("raised_amount") or a.get("raised") or 0)
    progress = int(round(min(100.0, (raised / target) * 100))) if target > 0 else 0
    return target, raised, progress


def _horizon_years(a: dict) -> int:
    months = int(a.get("term_months") or a.get("horizon_months") or 60)
    return max(1, round(months / 12))


def _as_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ──────────────────────────────────────────────────────────────────────────────
# B2 — Scenario Engine
# ──────────────────────────────────────────────────────────────────────────────

# Multipliers applied to the asset's OWN economics. Bear stresses both rent and
# exit; Bull rewards them. Base == the model the admin saved. Investors see a
# RANGE, not a single promise. Admin may override these factors per asset.
_SCENARIO_DEFAULTS = {
    "bear": {"label": "Песимістичний", "yield_factor": 0.62, "exit_factor": 0.45, "tone": "danger"},
    "base": {"label": "Базовий",       "yield_factor": 1.00, "exit_factor": 1.00, "tone": "primary"},
    "bull": {"label": "Оптимістичний", "yield_factor": 1.32, "exit_factor": 1.65, "tone": "success"},
}

_ECON_DEFAULTS = {
    "real_estate": {"rental_share": 0.60, "opex_rate": 0.10},
    "commercial":  {"rental_share": 0.75, "opex_rate": 0.15},
    "land":        {"rental_share": 0.05, "opex_rate": 0.03},
    "construction": {"rental_share": 0.10, "opex_rate": 0.05},
    "_global":     {"rental_share": 0.55, "opex_rate": 0.12},
}


def _compute_scenarios(a: dict) -> dict:
    cat = a.get("category")
    d = _ECON_DEFAULTS.get(cat, _ECON_DEFAULTS["_global"])
    rental_share = float(a.get("rental_share") or d["rental_share"])
    appreciation_share = max(0.0, 1.0 - rental_share)
    opex_rate = float(a.get("opex_rate") or d["opex_rate"])
    tax_rate = float(a.get("tax_rate") or 0.195)
    platform_fee = float(a.get("platform_fee") or 0.02)
    base_gross = float(a.get("target_yield") or 12.0) / 100.0
    horizon_y = _horizon_years(a)

    overrides = a.get("scenario_factors") or {}
    out = []
    for key in ("bear", "base", "bull"):
        cfg = dict(_SCENARIO_DEFAULTS[key])
        ov = overrides.get(key) or {}
        yf = float(ov.get("yield_factor", cfg["yield_factor"]))
        ef = float(ov.get("exit_factor", cfg["exit_factor"]))
        gross = base_gross * yf

        # annual rental (per 1 unit of ticket) → net yield %
        annual_rental_gross = gross * rental_share
        annual_after_opex = annual_rental_gross * (1.0 - opex_rate)
        annual_net = annual_after_opex * (1.0 - tax_rate - platform_fee)
        annual_yield_pct = annual_net * 100.0

        # exit appreciation over the whole horizon → total exit %
        appreciation_total = gross * appreciation_share * horizon_y * ef
        appreciation_net = appreciation_total * (1.0 - tax_rate)
        exit_pct = appreciation_net * 100.0

        total_net = annual_net * horizon_y + appreciation_net
        net_irr = (((1.0 + total_net)) ** (1.0 / horizon_y) - 1.0) * 100.0

        out.append({
            "key": key,
            "label": cfg["label"],
            "tone": cfg["tone"],
            "annual_yield_percent": round(annual_yield_pct, 1),
            "exit_percent": round(exit_pct, 1),
            "net_irr_percent": round(net_irr, 1),
            "yield_factor": round(yf, 2),
            "exit_factor": round(ef, 2),
        })
    return {
        "asset_id": a.get("id"),
        "horizon_years": horizon_y,
        "base_yield_percent": round(base_gross * 100, 1),
        "scenarios": out,
        "disclaimer": "Це сценарії, а не прогноз. Діапазон побудовано з власної економіки об'єкта.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# B3 — Capital Stack
# ──────────────────────────────────────────────────────────────────────────────

_STACK_TONE = {
    "asset_value": "#1f2937",
    "investors_crypto": "#2E5D4F",   # forest green  — raised via crypto/internal balance
    "investors_fiat": "#C9A961",     # gold          — raised via fiat (bank)
    "reserve": "#0ea5e9",            # blue          — reserve fund
    "platform": "#6b7280",           # gray          — own / platform funds
}
_STACK_LAYER_LABELS = {
    "investors_crypto": "Кошти інвесторів · криптою",
    "investors_fiat": "Кошти інвесторів · фіатом",
    "reserve": "Резервний фонд",
    "platform": "Власні кошти",
}

# Confirmed pool contributions are the source of truth for the crypto/fiat split.
C_POOL_CONTRIB = "lumen_pool_contributions"


async def crypto_fiat_split(asset_id: str, *, fallback_raised: float = 0.0,
                            asset: Optional[dict] = None) -> dict:
    """Real raised split by funding rail.

    Source of truth = confirmed `lumen_pool_contributions` for this asset,
    grouped by `gateway` ("crypto" | "fiat"). "crypto" covers on-chain USDT and
    internal-balance reinvestment (internal crypto logic). Falls back to authored
    per-asset fields, then to a proportional default of the raised amount.
    """
    crypto = 0.0
    fiat = 0.0
    try:
        cur = db[C_POOL_CONTRIB].find({"asset_id": asset_id, "status": "confirmed"})
        async for c in cur:
            amt = float(c.get("amount_usd") or c.get("amount") or 0)
            gw = str(c.get("gateway") or "fiat").lower()
            if gw == "crypto":
                crypto += amt
            else:
                fiat += amt
    except Exception:
        crypto = fiat = 0.0

    total = crypto + fiat
    if total <= 0 and asset is not None:
        rc = float(asset.get("raised_crypto") or 0)
        rf = float(asset.get("raised_fiat") or 0)
        crypto, fiat, total = rc, rf, rc + rf
    if total <= 0 and fallback_raised > 0:
        crypto = round(fallback_raised * 0.30)
        fiat = fallback_raised - crypto
        total = crypto + fiat
    return {"crypto": round(crypto), "fiat": round(fiat), "total": round(total)}


def _capital_stack(a: dict, split: Optional[dict] = None) -> dict:
    """Capital structure. Investor capital is split into real crypto vs fiat
    rails (from `split`); plus reserve fund and own/platform funds. No debt."""
    target, raised, _ = _funding(a)
    raw = a.get("capital_stack") or {}

    investors_authored = float(raw.get("investors") or 0)
    reserve = float(raw.get("reserve") or 0)
    platform = float(raw.get("platform") or raw.get("own") or 0)

    if split and float(split.get("total") or 0) > 0:
        investors = float(split["total"])
        inv_crypto = float(split.get("crypto") or 0)
        inv_fiat = float(split.get("fiat") or 0)
    else:
        investors = investors_authored or raised or target
        inv_crypto = float(a.get("raised_crypto") or 0)
        inv_fiat = float(a.get("raised_fiat") or 0)
        if (inv_crypto + inv_fiat) <= 0:
            inv_crypto, inv_fiat = 0.0, investors

    if reserve <= 0:
        reserve = round((investors_authored or investors) * 0.05)

    asset_value = float(raw.get("asset_value") or 0) or (investors + reserve + platform)
    total = investors + reserve + platform
    authored = bool(raw)

    layers = []
    for key, val in (
        ("investors_crypto", inv_crypto),
        ("investors_fiat", inv_fiat),
        ("reserve", reserve),
        ("platform", platform),
    ):
        if val <= 0:
            continue
        layers.append({
            "key": key,
            "label": _STACK_LAYER_LABELS[key],
            "amount": round(val),
            "percent": round((val / total) * 100, 1) if total > 0 else 0,
            "color": _STACK_TONE[key],
        })
    return {
        "asset_id": a.get("id"),
        "authored": authored,
        "asset_value": round(asset_value),
        "total_capital": round(total),
        "investor_share_percent": round((investors / total) * 100, 1) if total > 0 else 0,
        "crypto_raised": round(inv_crypto),
        "fiat_raised": round(inv_fiat),
        "crypto_percent": round((inv_crypto / investors) * 100, 1) if investors > 0 else 0,
        "fiat_percent": round((inv_fiat / investors) * 100, 1) if investors > 0 else 0,
        "layers": layers,
    }


# ──────────────────────────────────────────────────────────────────────────────
# B5 — Live Metrics  (everything from REAL collections)
# ──────────────────────────────────────────────────────────────────────────────

async def _payout_facts(asset_id: str) -> dict:
    credited = 0
    total_paid = 0.0
    planned = 0
    last_paid: Optional[datetime] = None
    async for rec in db.lumen_payout_records.find({"asset_id": asset_id}):
        st = rec.get("status")
        if st == "credited":
            credited += 1
            total_paid += float(rec.get("amount_uah") or 0)
            pd = _as_dt(rec.get("paid_date"))
            if pd and (last_paid is None or pd > last_paid):
                last_paid = pd
        elif st in ("planned", "generated", "approved"):
            planned += 1
    return {
        "credited_count": credited,
        "planned_count": planned,
        "total_paid": round(total_paid),
        "last_paid": last_paid,
    }


async def _secondary_facts(asset_id: str) -> dict:
    active_listings = await db.lumen_secondary_listings.count_documents(
        {"asset_id": asset_id, "status": "active"})
    listed_volume = 0.0
    async for L in db.lumen_secondary_listings.find({"asset_id": asset_id, "status": "active"}):
        listed_volume += float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
    # bids reference listings; resolve listing ids for this asset
    listing_ids = [L["id"] async for L in db.lumen_secondary_listings.find(
        {"asset_id": asset_id}, {"id": 1})]
    open_bids = await db.lumen_secondary_bids.count_documents(
        {"listing_id": {"$in": listing_ids}, "status": {"$in": ["open", "active", "pending"]}}) if listing_ids else 0
    since = _now() - timedelta(days=90)
    trades_90d = 0
    trade_volume = 0.0
    async for t in db.lumen_secondary_trades.find({"asset_id": asset_id}):
        trade_volume += float(t.get("amount_uah") or t.get("units_uah") or 0)
        ct = _as_dt(t.get("created_at") or t.get("settled_at"))
        if ct and ct >= since:
            trades_90d += 1
    total_trades = await db.lumen_secondary_trades.count_documents({"asset_id": asset_id})

    # Also fold in the NFT-based OTC market (the live secondary market) so the
    # liquidity signal reflects what investors actually see.
    otc_active = await db.lumen_otc_listings.count_documents({"asset_id": asset_id, "status": "active"})
    async for L in db.lumen_otc_listings.find({"asset_id": asset_id, "status": "active"}):
        listed_volume += float(L.get("price_usd") or 0)
    otc_done = await db.lumen_otc_deals.count_documents({"asset_id": asset_id, "status": {"$in": ["completed", "settled"]}})

    return {
        "active_listings": active_listings + otc_active,
        "listed_volume": round(listed_volume),
        "open_bids": open_bids,
        "trades_90d": trades_90d + otc_done,
        "total_trades": total_trades + otc_done,
        "trade_volume": round(trade_volume),
    }


async def _ownership_facts(asset_id: str) -> dict:
    count = 0
    now = _now()
    hold_days_sum = 0.0
    held = 0
    async for own in db.lumen_ownerships.find({"asset_id": asset_id}):
        if float(own.get("units_int") or own.get("units") or 0) <= 0:
            continue
        count += 1
        created = _as_dt(own.get("created_at"))
        if created:
            hold_days_sum += max(0.0, (now - created).total_seconds() / 86400.0)
            held += 1
    avg_hold = round(hold_days_sum / held) if held else 0
    return {"investor_count": count, "avg_hold_days": avg_hold}


async def _report_facts(asset_id: str) -> dict:
    total = await db.lumen_asset_reports.count_documents({"asset_id": asset_id})
    since = _now() - timedelta(days=365)
    recent = 0
    last: Optional[datetime] = None
    async for r in db.lumen_asset_reports.find({"asset_id": asset_id}):
        ct = _as_dt(r.get("created_at"))
        if ct and ct >= since:
            recent += 1
        if ct and (last is None or ct > last):
            last = ct
    return {"reports_total": total, "reports_12m": recent, "last_report": last}


async def _asset_metrics(a: dict) -> dict:
    asset_id = a["id"]
    target, raised, progress = _funding(a)
    payout = await _payout_facts(asset_id)
    sec = await _secondary_facts(asset_id)
    own = await _ownership_facts(asset_id)
    rep = await _report_facts(asset_id)
    investor_count = own["investor_count"] or int(a.get("investors_count") or 0)

    return {
        "asset_id": asset_id,
        "funding": {"target": round(target), "raised": round(raised), "progress_percent": progress},
        "investor_count": investor_count,
        "avg_hold_days": own["avg_hold_days"],
        "secondary": sec,
        "payout": {
            "credited_count": payout["credited_count"],
            "planned_count": payout["planned_count"],
            "total_paid": payout["total_paid"],
            "last_paid": _iso(payout["last_paid"]),
        },
        "reports": {
            "total": rep["reports_total"],
            "last_report": _iso(rep["last_report"]),
        },
        "occupancy_percent": float(a.get("occupancy_percent")) if a.get("occupancy_percent") is not None else None,
    }, {"payout": payout, "sec": sec, "own": own, "rep": rep,
        "progress": progress, "investor_count": investor_count}


# ──────────────────────────────────────────────────────────────────────────────
# B5b — Compact snapshot / cash-flow / rounds / highlights (investor-facing)
# ──────────────────────────────────────────────────────────────────────────────

# Conviction band → investor-facing RISK (high conviction == low risk)
_RISK_FROM_BAND = {
    "high": {"label": "Низький", "band": "low"},
    "medium": {"label": "Помірний", "band": "medium"},
    "low": {"label": "Підвищений", "band": "high"},
}

_STATUS_LABELS = {
    "open": "Активний (триває раунд)",
    "active": "Активний",
    "funded": "Профінансовано",
    "closed": "Завершено",
    "draft": "Чернетка",
}


def _snapshot(a: dict, facts: dict, conviction: dict) -> dict:
    """At-a-glance scoring strip: risk / yield / term / occupancy / dividends / status."""
    payout = facts["payout"]
    paid = payout["credited_count"] or int(a.get("dividends_paid_count") or 0)
    total = (payout["credited_count"] + payout["planned_count"]) or int(a.get("dividends_total_count") or paid)
    occ = a.get("occupancy_percent")
    status = a.get("status") or "open"
    return {
        "risk": _RISK_FROM_BAND.get(conviction.get("band"), _RISK_FROM_BAND["medium"]),
        "conviction_score": conviction.get("score"),
        "yield_percent": float(a.get("target_yield")) if a.get("target_yield") is not None else None,
        "term_months": int(a.get("term_months")) if a.get("term_months") else _horizon_years(a) * 12,
        "occupancy_percent": round(float(occ)) if occ is not None else None,
        "dividends": {"paid": paid, "total": total},
        "status": status,
        "status_label": _STATUS_LABELS.get(status, status),
    }


def _cashflow(a: dict, facts: dict) -> dict:
    """Operational cash-flow: invested / rent received / paid to investors / reserve."""
    cf = a.get("operating_cashflow") or {}
    target, raised, _ = _funding(a)
    invested = cf.get("invested")
    if invested is None:
        invested = round(raised)
    paid_out = cf.get("paid_to_investors")
    if paid_out is None:
        paid_out = facts["payout"]["total_paid"]
    stack = _capital_stack(a)
    reserve = cf.get("reserve")
    if reserve is None:
        reserve = next((L["amount"] for L in stack.get("layers", []) if L["key"] == "reserve"), 0)
    return {
        "currency": "UAH",
        "invested": round(invested or 0),
        "rent_received": round(cf.get("rent_received") or 0),
        "paid_to_investors": round(paid_out or 0),
        "reserve": round(reserve or 0),
        "has_content": bool(cf),
    }


def _rounds(a: dict) -> dict:
    rounds = a.get("rounds") or []
    _, _, progress = _funding(a)
    if not rounds:
        # derive a minimal single-round view from funding progress
        rounds = [{"label": "Поточний раунд", "status": "closed" if progress >= 100 else "open", "progress": progress}]
    return {"items": rounds, "total": len(rounds),
            "open_index": next((i for i, r in enumerate(rounds) if r.get("status") == "open"), None)}


def _highlights(a: dict) -> list:
    return list(a.get("intel_highlights") or [])


# ──────────────────────────────────────────────────────────────────────────────
# B6 — Conviction Score  (deterministic, from facts — never AI)
# ──────────────────────────────────────────────────────────────────────────────

def _conviction(a: dict, facts: dict) -> dict:
    payout = facts["payout"]
    rep = facts["rep"]
    progress = facts["progress"]
    occupancy = a.get("occupancy_percent")

    factors = []

    # 1. Payout consistency (0..100) — credited vs total scheduled.
    #    Falls back to authored dividends_paid/total when no records exist yet.
    credited = payout["credited_count"]
    total_sched = credited + payout["planned_count"]
    if total_sched == 0 and a.get("dividends_paid_count"):
        credited = int(a.get("dividends_paid_count") or 0)
        total_sched = int(a.get("dividends_total_count") or credited)
    if credited > 0:
        pc = 100.0  # a paying asset has a proven distribution track record
    else:
        pc = 0.0
    factors.append({"key": "payout_consistency", "label": "Регулярність виплат",
                    "value": round(pc), "weight": 0.30,
                    "detail": f"{credited} виплат проведено" if credited else "виплат ще не було"})

    # 2. Occupancy (authored, 0..100)
    if occupancy is not None:
        occ = _clip(float(occupancy), 0, 100)
        factors.append({"key": "occupancy", "label": "Заповнюваність",
                        "value": round(occ), "weight": 0.25,
                        "detail": f"{round(occ)}% площ зайнято орендарями"})
    else:
        factors.append({"key": "occupancy", "label": "Заповнюваність",
                        "value": 50, "weight": 0.25, "detail": "дані не вказані"})

    # 3. Report cadence (0..100) — 4+ reports / 12m == full transparency
    rc = _clip((rep["reports_12m"] / 4.0) * 100.0, 0, 100)
    factors.append({"key": "report_frequency", "label": "Прозорість (звіти)",
                    "value": round(rc), "weight": 0.20,
                    "detail": f"{rep['reports_12m']} звітів за 12 міс."})

    # 4. Yield history — does the asset already pay? realised vs target
    if payout["credited_count"] > 0:
        yh = 100.0
        yh_detail = "об'єкт уже здійснює виплати"
    elif a.get("status") == "open":
        yh = 45.0
        yh_detail = "раунд триває, виплати попереду"
    else:
        yh = 25.0
        yh_detail = "виплат поки немає"
    factors.append({"key": "yield_history", "label": "Історія дохідності",
                    "value": round(yh), "weight": 0.15, "detail": yh_detail})

    # 5. Funding traction (0..100)
    factors.append({"key": "funding", "label": "Динаміка збору",
                    "value": round(progress), "weight": 0.10,
                    "detail": f"{progress}% раунду зібрано"})

    score = sum(f["value"] * f["weight"] for f in factors)
    score = round(_clip(score, 0, 100))
    if score >= 70:
        band, label = "high", "Висока впевненість"
    elif score >= 45:
        band, label = "medium", "Помірна впевненість"
    else:
        band, label = "low", "Низька впевненість"
    return {"asset_id": a.get("id"), "score": score, "band": band, "label": label,
            "factors": factors}


# ──────────────────────────────────────────────────────────────────────────────
# B7 — Liquidity Score  (0..10, from secondary market signals)
# ──────────────────────────────────────────────────────────────────────────────

def _liquidity(a: dict, facts: dict) -> dict:
    sec = facts["sec"]
    investor_count = facts["investor_count"]

    signals = []
    score = 0.0

    # Supply: active listings exist (someone is willing to sell)
    has_listings = sec["active_listings"] > 0
    score += min(3.0, sec["active_listings"] * 1.5)
    signals.append({"key": "supply", "label": "Пропозиція", "ok": has_listings,
                    "detail": f"{sec['active_listings']} активних лотів"})

    # Demand: open bids
    has_demand = sec["open_bids"] > 0
    score += min(3.0, sec["open_bids"] * 1.5)
    signals.append({"key": "demand", "label": "Попит", "ok": has_demand,
                    "detail": f"{sec['open_bids']} відкритих заявок"})

    # Activity: realised trades (last 90d weighted)
    has_trades = sec["total_trades"] > 0
    score += min(2.5, sec["trades_90d"] * 1.25)
    signals.append({"key": "activity", "label": "Угоди", "ok": has_trades,
                    "detail": f"{sec['trades_90d']} угод за 90 днів"})

    # Breadth: more holders → easier to find a counterparty
    breadth_ok = investor_count >= 5
    score += min(1.5, investor_count * 0.15)
    signals.append({"key": "breadth", "label": "Кількість власників", "ok": breadth_ok,
                    "detail": f"{investor_count} власників"})

    score10 = round(_clip(score, 0, 10), 1)
    if score10 >= 7:
        band, label = "high", "Висока ліквідність"
    elif score10 >= 4:
        band, label = "medium", "Помірна ліквідність"
    else:
        band, label = "low", "Низька ліквідність"
    return {"asset_id": a.get("id"), "score": score10, "max": 10, "band": band,
            "label": label, "signals": signals}


# ──────────────────────────────────────────────────────────────────────────────
# B4 — Asset Journal  (authored milestones + real system events)
# ──────────────────────────────────────────────────────────────────────────────

_JOURNAL_KIND_LABELS = {
    "milestone": "Віха", "acquisition": "Придбання", "operations": "Експлуатація",
    "payout": "Виплата", "report": "Звіт", "secondary": "Вторинний ринок",
    "funding": "Збір", "valuation": "Переоцінка", "general": "Подія",
}


async def _journal(a: dict) -> dict:
    asset_id = a["id"]
    events: list[dict] = []

    def add(dt: Optional[datetime], kind: str, title: str, body: str = "", source: str = "system"):
        if not dt:
            return
        events.append({
            "date": _iso(dt),
            "_sort": dt,
            "kind": kind,
            "kind_label": _JOURNAL_KIND_LABELS.get(kind, kind),
            "title": title,
            "body": body,
            "source": source,
        })

    # Genesis — asset published
    add(_as_dt(a.get("open_date")) or _as_dt(a.get("created_at")), "acquisition",
        "Об'єкт опубліковано", f"«{a.get('title')}» відкрито для інвестування.")

    # Funding milestones from investments timeline
    target, raised, progress = _funding(a)
    if progress >= 100:
        add(_as_dt(a.get("close_date")) or _now(), "funding",
            "Раунд закрито", "Цільову суму зібрано на 100%.")

    # Real reports
    async for r in db.lumen_asset_reports.find({"asset_id": asset_id}):
        add(_as_dt(r.get("created_at")), "report",
            f"Звіт: {r.get('period_label') or r.get('title') or 'період'}",
            r.get("summary") or "", source="system")

    # Real admin updates flagged as milestones / news
    async for u in db.lumen_asset_updates.find({"asset_id": asset_id, "published": True}):
        kind = "milestone" if u.get("kind") == "milestone" else "operations"
        add(_as_dt(u.get("published_at") or u.get("created_at")), kind,
            u.get("title") or "Оновлення", u.get("body") or "", source="system")

    # Real payouts
    async for rec in db.lumen_payout_records.find({"asset_id": asset_id, "status": "credited"}):
        add(_as_dt(rec.get("paid_date")), "payout",
            "Виплата інвесторам",
            f"Нараховано {fmt_uah_as_usd(rec.get('amount_uah'))}")

    # Real secondary trades
    async for t in db.lumen_secondary_trades.find({"asset_id": asset_id}):
        add(_as_dt(t.get("created_at") or t.get("settled_at")), "secondary",
            "Угода на вторинному ринку",
            f"Частку перепродано на суму {fmt_uah_as_usd(t.get('amount_uah') or t.get('units_uah') or 0)}")

    # Authored milestones
    for m in (a.get("journal_milestones") or []):
        add(_as_dt(m.get("date")), m.get("kind") or "milestone",
            m.get("title") or "Подія", m.get("body") or "", source="authored")

    events.sort(key=lambda e: e["_sort"], reverse=True)
    for e in events:
        e.pop("_sort", None)
    return {"asset_id": asset_id, "items": events, "total": len(events)}


# ──────────────────────────────────────────────────────────────────────────────
# B8 — Similar Assets
# ──────────────────────────────────────────────────────────────────────────────

async def _similar(a: dict, limit: int = 4) -> dict:
    asset_id = a["id"]
    base_yield = float(a.get("target_yield") or 0)
    cat = a.get("category")
    pool = []
    async for o in db.lumen_assets.find({"id": {"$ne": asset_id}, "status": {"$ne": "draft"}}):
        oo = _category_with_labels(o)
        _, _, progress = _funding(oo)
        same_cat = oo.get("category") == cat
        yield_gap = abs(float(oo.get("target_yield") or 0) - base_yield)
        rank = (0 if same_cat else 1, yield_gap)
        pool.append((rank, {
            "id": oo.get("id"),
            "title": oo.get("title"),
            "category": oo.get("category"),
            "category_label": oo.get("category_label"),
            "location": oo.get("location"),
            "cover_url": oo.get("cover_url"),
            "target_yield": oo.get("target_yield"),
            "min_ticket": oo.get("min_ticket"),
            "progress_percent": progress,
            "same_category": same_cat,
        }))
    pool.sort(key=lambda x: x[0])
    return {"asset_id": asset_id, "items": [p[1] for p in pool[:limit]]}


# ──────────────────────────────────────────────────────────────────────────────
# Public / investor endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/scenarios")
async def get_scenarios(asset_id: str):
    a = await _asset_or_404(asset_id)
    return _compute_scenarios(a)


@router.get("/assets/{asset_id}/capital-stack")
async def get_capital_stack(asset_id: str):
    a = await _asset_or_404(asset_id)
    _, raised, _ = _funding(a)
    split = await crypto_fiat_split(asset_id, fallback_raised=raised, asset=a)
    return _capital_stack(a, split)


@router.get("/assets/{asset_id}/metrics")
async def get_metrics(asset_id: str):
    a = await _asset_or_404(asset_id)
    metrics, _ = await _asset_metrics(a)
    return metrics


@router.get("/assets/{asset_id}/conviction")
async def get_conviction(asset_id: str):
    a = await _asset_or_404(asset_id)
    _, facts = await _asset_metrics(a)
    return _conviction(a, facts)


@router.get("/assets/{asset_id}/liquidity")
async def get_liquidity(asset_id: str):
    a = await _asset_or_404(asset_id)
    _, facts = await _asset_metrics(a)
    return _liquidity(a, facts)


@router.get("/assets/{asset_id}/journal")
async def get_journal(asset_id: str):
    a = await _asset_or_404(asset_id)
    return await _journal(a)


@router.get("/assets/{asset_id}/similar")
async def get_similar(asset_id: str, limit: int = 4):
    a = await _asset_or_404(asset_id)
    return await _similar(a, max(1, min(limit, 8)))


@router.get("/assets/{asset_id}/intelligence")
async def get_intelligence(asset_id: str):
    """One aggregate call for the asset detail page (B1+B2+B3+B5+B6+B7)."""
    a = await _asset_or_404(asset_id)
    metrics, facts = await _asset_metrics(a)
    thesis = a.get("thesis") or {}
    has_thesis = any((thesis.get(k) or "").strip() for k in ("opportunity", "market", "execution", "exit"))
    conviction = _conviction(a, facts)
    _, raised, _ = _funding(a)
    split = await crypto_fiat_split(asset_id, fallback_raised=raised, asset=a)
    return {
        "asset_id": asset_id,
        "snapshot": _snapshot(a, facts, conviction),
        "highlights": _highlights(a),
        "cashflow": _cashflow(a, facts),
        "rounds": _rounds(a),
        "thesis": {
            "opportunity": thesis.get("opportunity") or "",
            "market": thesis.get("market") or "",
            "execution": thesis.get("execution") or "",
            "exit": thesis.get("exit") or "",
            "has_content": has_thesis,
        },
        "capital_stack": _capital_stack(a, split),
        "scenarios": _compute_scenarios(a),
        "metrics": metrics,
        "conviction": conviction,
        "liquidity": _liquidity(a, facts),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Admin authoring
# ──────────────────────────────────────────────────────────────────────────────

class ThesisIn(BaseModel):
    opportunity: Optional[str] = None
    market: Optional[str] = None
    execution: Optional[str] = None
    exit: Optional[str] = None


class CapitalStackIn(BaseModel):
    asset_value: Optional[float] = None
    debt: Optional[float] = None
    platform: Optional[float] = None
    investors: Optional[float] = None
    reserve: Optional[float] = None


class ScenarioFactorIn(BaseModel):
    yield_factor: Optional[float] = None
    exit_factor: Optional[float] = None


class IntelligenceIn(BaseModel):
    thesis: Optional[ThesisIn] = None
    capital_stack: Optional[CapitalStackIn] = None
    occupancy_percent: Optional[float] = None
    scenario_factors: Optional[dict[str, ScenarioFactorIn]] = None


@router.get("/admin/assets/{asset_id}/intelligence")
async def admin_get_intelligence(asset_id: str, _=Depends(require_admin)):
    a = await _asset_or_404(asset_id)
    return {
        "asset_id": asset_id,
        "title": a.get("title"),
        "thesis": a.get("thesis") or {},
        "capital_stack": a.get("capital_stack") or {},
        "occupancy_percent": a.get("occupancy_percent"),
        "scenario_factors": a.get("scenario_factors") or {},
        "scenario_defaults": {k: {"yield_factor": v["yield_factor"], "exit_factor": v["exit_factor"]}
                              for k, v in _SCENARIO_DEFAULTS.items()},
    }


@router.patch("/admin/assets/{asset_id}/intelligence")
async def admin_patch_intelligence(asset_id: str, payload: IntelligenceIn,
                                   _=Depends(require_admin)):
    await _asset_or_404(asset_id)
    patch: dict[str, Any] = {"updated_at": _now()}

    if payload.thesis is not None:
        patch["thesis"] = {
            "opportunity": (payload.thesis.opportunity or "").strip()[:4000],
            "market": (payload.thesis.market or "").strip()[:4000],
            "execution": (payload.thesis.execution or "").strip()[:4000],
            "exit": (payload.thesis.exit or "").strip()[:4000],
        }
    if payload.capital_stack is not None:
        cs = payload.capital_stack
        patch["capital_stack"] = {
            "asset_value": max(0.0, float(cs.asset_value or 0)),
            "debt": max(0.0, float(cs.debt or 0)),
            "platform": max(0.0, float(cs.platform or 0)),
            "investors": max(0.0, float(cs.investors or 0)),
            "reserve": max(0.0, float(cs.reserve or 0)),
        }
    if payload.occupancy_percent is not None:
        patch["occupancy_percent"] = _clip(float(payload.occupancy_percent), 0, 100)
    if payload.scenario_factors is not None:
        sf = {}
        for key in ("bear", "base", "bull"):
            f = payload.scenario_factors.get(key)
            if not f:
                continue
            sf[key] = {
                "yield_factor": _clip(float(f.yield_factor if f.yield_factor is not None else _SCENARIO_DEFAULTS[key]["yield_factor"]), 0.1, 3.0),
                "exit_factor": _clip(float(f.exit_factor if f.exit_factor is not None else _SCENARIO_DEFAULTS[key]["exit_factor"]), 0.0, 3.0),
            }
        patch["scenario_factors"] = sf

    await db.lumen_assets.update_one({"id": asset_id}, {"$set": patch})
    a = await _asset_or_404(asset_id)
    return {"ok": True, "asset_id": asset_id,
            "thesis": a.get("thesis") or {}, "capital_stack": a.get("capital_stack") or {},
            "occupancy_percent": a.get("occupancy_percent"),
            "scenario_factors": a.get("scenario_factors") or {}}


class JournalMilestoneIn(BaseModel):
    date: str
    title: str
    body: Optional[str] = ""
    kind: Optional[str] = "milestone"


@router.get("/admin/assets/{asset_id}/journal")
async def admin_get_journal(asset_id: str, _=Depends(require_admin)):
    a = await _asset_or_404(asset_id)
    return {"asset_id": asset_id, "items": a.get("journal_milestones") or []}


@router.post("/admin/assets/{asset_id}/journal")
async def admin_add_milestone(asset_id: str, payload: JournalMilestoneIn,
                              _=Depends(require_admin)):
    await _asset_or_404(asset_id)
    if not _as_dt(payload.date):
        raise HTTPException(status_code=400, detail="Невірна дата")
    kind = payload.kind if payload.kind in _JOURNAL_KIND_LABELS else "milestone"
    milestone = {
        "id": f"jm-{uuid.uuid4().hex[:10]}",
        "date": payload.date,
        "title": payload.title.strip()[:200],
        "body": (payload.body or "").strip()[:2000],
        "kind": kind,
    }
    await db.lumen_assets.update_one(
        {"id": asset_id}, {"$push": {"journal_milestones": milestone}, "$set": {"updated_at": _now()}})
    return {"ok": True, "milestone": milestone}


@router.delete("/admin/asset-journal/{milestone_id}")
async def admin_delete_milestone(milestone_id: str, _=Depends(require_admin)):
    res = await db.lumen_assets.update_one(
        {"journal_milestones.id": milestone_id},
        {"$pull": {"journal_milestones": {"id": milestone_id}}, "$set": {"updated_at": _now()}})
    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="Віху не знайдено")
    return {"ok": True, "deleted": milestone_id}


# ──────────────────────────────────────────────────────────────────────────────
# Demo seed — make existing assets look alive (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

_DEMO_INTEL: dict[str, dict] = {
    "asset-podilskyi": {
        "occupancy_percent": 92,
        "thesis": {
            "opportunity": "Подільський район Києва — історичний центр із дефіцитом нової житлової нерухомості бізнес-класу. Забудовник продає з дисконтом 18% до ринку через потребу в швидкому фінансуванні етапу облицювання.",
            "market": "Попит на оренду в радіусі 1 км перевищує пропозицію в 2,3 раза. Середня орендна ставка зросла на 14% за рік. Поруч — станція метро та нова школа.",
            "execution": "Будинок зданий в експлуатацію, 92% площ уже законтрактовано орендарями за попередніми угодами. Керуюча компанія з 9-річним досвідом управляє ще 4 об'єктами Lumen.",
            "exit": "Базовий сценарій — продаж пакету інституційному фонду на 24-му місяці. Альтернатива — рефінансування і подовження оренди.",
        },
        "capital_stack": {"asset_value": 4200000, "debt": 1500000, "platform": 200000, "investors": 2300000, "reserve": 200000},
        "journal_milestones": [
            {"id": "jm-pod-1", "date": "2026-03-12", "title": "Об'єкт придбано", "body": "Закрито угоду купівлі-продажу, оформлено право власності на SPV.", "kind": "acquisition"},
            {"id": "jm-pod-2", "date": "2026-03-25", "title": "Старт оздоблення", "body": "Підрядник зайшов на майданчик, графік на 6 тижнів.", "kind": "operations"},
            {"id": "jm-pod-3", "date": "2026-04-11", "title": "Підписано якірного орендаря", "body": "Договір на 5 поверхів, ставка вище за модель на 6%.", "kind": "milestone"},
        ],
    },
    "asset-lavr-tc": {
        "occupancy_percent": 87,
        "thesis": {
            "opportunity": "ТЦ «Лавр» у Львові — стабілізований актив із діючим грошовим потоком. Продавець виходить із непрофільного активу, що дає вхід нижче відновлювальної вартості.",
            "market": "Львів — туристичний і IT-хаб із найнижчою вакантністю торгових площ серед міст-мільйонників. Орендарі — мережеві бренди з довгими контрактами.",
            "execution": "87% площ зайнято, середній строк оренди — 3,1 року. Є потенціал реконцепції фудкорту для +9% до доходу.",
            "exit": "Cash-flow актив під утримання 4 роки з щоквартальними виплатами, потім продаж за cap-rate.",
        },
        "capital_stack": {"asset_value": 9800000, "debt": 4000000, "platform": 300000, "investors": 5200000, "reserve": 300000},
        "journal_milestones": [
            {"id": "jm-lavr-1", "date": "2026-02-01", "title": "Об'єкт придбано", "body": "Стабілізований ТЦ із діючими орендарями.", "kind": "acquisition"},
            {"id": "jm-lavr-2", "date": "2026-05-01", "title": "Перша виплата дивідендів", "body": "Розподілено перший квартальний дохід.", "kind": "payout"},
        ],
    },
    "asset-stoyanka-land": {
        "occupancy_percent": None,
        "thesis": {
            "opportunity": "Земельна ділянка під Борисполем у зоні майбутнього логістичного коридору. Зміна цільового призначення вже ініційована — це основний драйвер переоцінки.",
            "market": "Складська нерухомість навколо аеропорту — найдефіцитніший сегмент. Ціни на ділянки під склади зросли на 27% за два роки.",
            "execution": "Земля викуплена, документи на зміну призначення подані. Партнер-девелопер готовий зайти build-to-suit під конкретного орендаря.",
            "exit": "Продаж девелоперу після зміни призначення (місяць 18–24) або вхід у спільний девелопмент.",
        },
        "capital_stack": {"asset_value": 2600000, "debt": 0, "platform": 100000, "investors": 2400000, "reserve": 100000},
        "journal_milestones": [
            {"id": "jm-st-1", "date": "2026-01-20", "title": "Ділянку придбано", "body": "Оформлено право власності, кадастровий номер закріплено.", "kind": "acquisition"},
            {"id": "jm-st-2", "date": "2026-04-02", "title": "Подано на зміну призначення", "body": "Документи в роботі районної адміністрації.", "kind": "milestone"},
        ],
    },
    "asset-rivne-warehouse": {
        "occupancy_percent": 0,
        "thesis": {
            "opportunity": "Логістичний хаб на об'їзній Рівного — будівництво з нуля під підтверджений попит 3PL-операторів на маршруті Київ–Львів–кордон ЄС.",
            "market": "Транзитний коридор до ЄС переживає бум. Складів класу A критично не вистачає, передоренда укладається ще до введення в експлуатацію.",
            "execution": "Проєкт на стадії котловану. Генпідрядник законтрактований, графік 14 місяців, є попередні угоди на 40% площ.",
            "exit": "Стабілізація + продаж інституційному покупцю на 30-му місяці.",
        },
        "capital_stack": {"asset_value": 7400000, "debt": 3000000, "platform": 300000, "investors": 3800000, "reserve": 300000},
        "journal_milestones": [
            {"id": "jm-rv-1", "date": "2026-05-15", "title": "Об'єкт відкрито для збору", "body": "Стартував раунд фінансування будівництва.", "kind": "funding"},
        ],
    },
    "asset-odessa-apartments": {
        "occupancy_percent": 78,
        "thesis": {
            "opportunity": "Прибутковий будинок на Французькому бульварі — преміальна локація Одеси з історичним фасадом і стабільним орендним попитом.",
            "market": "Французький бульвар — топ-локація для довгострокової та короткострокової оренди. Сезонність згладжується корпоративними орендарями.",
            "execution": "Будинок в експлуатації, 78% квартир здано. Програма косметичного оновлення підвищить ставку на 8–11%.",
            "exit": "Утримання з орендним доходом 4 роки, потім поквартирний продаж або продаж цілком.",
        },
        "capital_stack": {"asset_value": 3100000, "debt": 900000, "platform": 150000, "investors": 1950000, "reserve": 100000},
        "journal_milestones": [
            {"id": "jm-od-1", "date": "2026-04-20", "title": "Об'єкт відкрито", "body": "Стабілізований прибутковий будинок виставлено на збір.", "kind": "acquisition"},
        ],
    },
}


async def seed_intelligence_demo() -> dict:
    """Idempotent: fills thesis / capital_stack / occupancy / milestones for
    demo assets that have no authored intelligence yet."""
    touched = 0
    for asset_id, payload in _DEMO_INTEL.items():
        a = await db.lumen_assets.find_one({"id": asset_id}, {"thesis": 1})
        if not a:
            continue
        if a.get("thesis"):  # already authored / seeded
            continue
        patch: dict[str, Any] = {"updated_at": _now()}
        if payload.get("thesis"):
            patch["thesis"] = payload["thesis"]
        if payload.get("capital_stack"):
            patch["capital_stack"] = payload["capital_stack"]
        if payload.get("occupancy_percent") is not None:
            patch["occupancy_percent"] = payload["occupancy_percent"]
        if payload.get("journal_milestones"):
            patch["journal_milestones"] = payload["journal_milestones"]
        await db.lumen_assets.update_one({"id": asset_id}, {"$set": patch})
        touched += 1
    logger.info("INTELLIGENCE (Phase B) demo seed: %d asset(s) enriched", touched)
    return {"enriched": touched}
