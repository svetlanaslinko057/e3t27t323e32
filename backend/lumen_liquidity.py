"""
LUMEN 2.0 — Phase D — Liquidity OS
==================================

Not "just an order book". A full liquidity experience layer that turns the
proven Secondary Market settlement engine (Sprint 13) into a living market.

Everything DERIVES from real collections — no mocks:
  • ASK side  = active `lumen_secondary_listings`            (Sprint 13)
  • BID side  = resting `lumen_liquidity_orders` (NEW)        (real limit buys)
  • trades    = `lumen_secondary_trades` (settled)            (price history)
  • ownership = `lumen_ownerships` + `lumen_share_transfers`  (registry truth)

Settlement is NEVER re-implemented — buy/sell orders that cross are executed
through `lumen_secondary._settle_trade`, so the Unit Registry (A1), Certificates
(A2), Lifecycle (A3) and all consistency invariants stay green.

Modules
-------
  D1  Order Book          — BID/ASK depth, best bid/ask, spread, limit orders
  D2  Indicative Price    — last trade · best bid · best ask · indicative (mid)
  D3  Liquidity Center     — holders · listed · demand · spread · trades/vol 30d
  D4  Exit Simulator       — "if I sell N units now → proceeds Y, fee Z" (no order)
  D5  Market Activity Feed — anonymised ("Продано 2 500 units по $2.54 +4.3%")
  D6  Watchlists           — follow assets → trades/listings/price/payout events
  D7  Market Makers        — `lumen_liquidity_providers` (fund/operator/spv)
  D8  Price Discovery      — NAV vs Market Price → premium / discount
  +   market_sentiment     — composite from C5 mood · C4 voting · activity · demand

Forbidden (per product owner): crypto, tokenization, blockchain, margin,
leverage, derivatives, short selling.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin, _strip_mongo,
                       _now, _iso)
from lumen_payments import _round2, BASE_CURRENCY

import lumen_secondary as _sec          # settlement + ownership maths (reused)

logger = logging.getLogger("lumen.liquidity")

router = APIRouter(prefix="/api", tags=["lumen-liquidity"])

PLATFORM_FEE_PCT = _sec.PLATFORM_FEE_PCT
DEFAULT_BASE_UNIT_PRICE = 100.0          # fallback par price if registry missing

ORDER_STATUSES = ("open", "partial", "filled", "cancelled", "expired")
MM_KINDS = ("fund", "operator", "spv", "external")

DEMO_BUYER_EMAIL = "liquidity.demo@lumen.test"


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
    return "admin" in (user.get("roles") or [])


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


async def _base_unit_price(asset_id: str) -> float:
    """Par / NAV price of one registry unit (UAH)."""
    au = await db.lumen_asset_units.find_one({"asset_id": asset_id})
    if au and float(au.get("unit_price_uah") or 0) > 0:
        return float(au["unit_price_uah"])
    a = await db.lumen_assets.find_one(
        {"id": asset_id}, {"round_target": 1, "target_amount": 1, "target": 1})
    target = float((a or {}).get("round_target") or (a or {}).get("target_amount")
                   or (a or {}).get("target") or 0)
    if target > 0:
        return _round2(target / 100000.0)
    return DEFAULT_BASE_UNIT_PRICE


def _units_from_uah(units_uah: float, base: float) -> int:
    return int(round(units_uah / base)) if base else 0


async def _holders_count(asset_id: str) -> int:
    n = 0
    async for o in db.lumen_ownerships.find({"asset_id": asset_id}):
        if float(o.get("units_int") or o.get("units") or o.get("amount_uah") or 0) > 0:
            n += 1
    return n


async def _last_trade(asset_id: str) -> Optional[dict]:
    return await db.lumen_secondary_trades.find_one(
        {"asset_id": asset_id, "status": "settled"},
        sort=[("settled_at", -1)],
    )


async def _price_marks(asset_id: str,
                       since: Optional[datetime] = None) -> list[dict]:
    """Unified price marks = real settled trades + demo/historical price points.

    Real settled trades come from `lumen_secondary_trades` (status=settled).
    Demo/historical marks live in `lumen_liquidity_price_points` — a SEPARATE
    collection so we never inject fake "settled" trades (which would break
    consistency invariants I11/I12 that require share_transfers + ledger per
    settled trade). Both feed the chart / discovery / market-price.
    """
    marks: list[dict] = []
    async for t in db.lumen_secondary_trades.find(
            {"asset_id": asset_id, "status": "settled"}):
        at = _as_dt(t.get("settled_at") or t.get("created_at"))
        if since and (not at or at < since):
            continue
        marks.append({
            "price": float(t.get("price_per_unit") or 1.0),
            "units_uah": float(t.get("units_uah") or 0),
            "gross_uah": float(t.get("gross_uah") or t.get("units_uah") or 0),
            "at": at, "real": True,
        })
    async for p in db.lumen_liquidity_price_points.find({"asset_id": asset_id}):
        at = _as_dt(p.get("at"))
        if since and (not at or at < since):
            continue
        marks.append({
            "price": float(p.get("price") or 1.0),
            "units_uah": float(p.get("units_uah") or 0),
            "gross_uah": float(p.get("gross_uah") or p.get("units_uah") or 0),
            "at": at, "real": False,
        })
    marks.sort(key=lambda m: m["at"] or _now())
    return marks


async def _last_mark(asset_id: str) -> Optional[dict]:
    marks = await _price_marks(asset_id)
    return marks[-1] if marks else None


def _strip_order(d: dict) -> dict:
    if not d:
        return d
    d = _strip_mongo(dict(d))
    for k in ("created_at", "updated_at", "cancelled_at", "expires_at"):
        if d.get(k):
            d[k] = _iso(d[k])
    return d


# ════════════════════════════════════════════════════════════════════════════
# D1 — Order Book (BID/ASK depth)
# ════════════════════════════════════════════════════════════════════════════

async def _active_listings(asset_id: str) -> list[dict]:
    out = []
    async for L in db.lumen_secondary_listings.find(
            {"asset_id": asset_id,
             "status": {"$in": ["active", "partially_filled"]}}):
        rem = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        if rem > 0.5:
            out.append(L)
    return out


async def _open_buy_orders(asset_id: str) -> list[dict]:
    out = []
    async for o in db.lumen_liquidity_orders.find(
            {"asset_id": asset_id, "side": "buy",
             "status": {"$in": ["open", "partial"]}}):
        rem = float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        if rem > 0.5:
            out.append(o)
    return out


async def _order_book(asset_id: str, depth: int = 12) -> dict:
    base = await _base_unit_price(asset_id)

    asks: dict[float, float] = {}
    for L in await _active_listings(asset_id):
        rem = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        p = round(float(L.get("price_per_unit") or 1.0), 4)
        asks[p] = asks.get(p, 0.0) + rem

    bids: dict[float, float] = {}
    for o in await _open_buy_orders(asset_id):
        rem = float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        p = round(float(o.get("limit_price") or 1.0), 4)
        bids[p] = bids.get(p, 0.0) + rem

    def _level(p: float, u: float) -> dict:
        return {"price": p, "price_uah": _round2(p * base),
                "units_uah": _round2(u), "units": _units_from_uah(u, base)}

    ask_levels = [_level(p, u) for p, u in sorted(asks.items())][:depth]
    bid_levels = [_level(p, u) for p, u in sorted(bids.items(), reverse=True)][:depth]

    best_ask = ask_levels[0]["price"] if ask_levels else None
    best_bid = bid_levels[0]["price"] if bid_levels else None
    spread = _round2(best_ask - best_bid) if (best_ask and best_bid) else None
    spread_pct = (round((best_ask - best_bid) / best_bid * 100, 2)
                  if (best_ask and best_bid and best_bid > 0) else None)

    return {
        "asset_id": asset_id,
        "base_unit_price_uah": base,
        "asks": ask_levels,
        "bids": bid_levels,
        "best_ask": best_ask,
        "best_ask_uah": _round2(best_ask * base) if best_ask else None,
        "best_bid": best_bid,
        "best_bid_uah": _round2(best_bid * base) if best_bid else None,
        "spread": spread,
        "spread_pct": spread_pct,
        "ask_units_total": _round2(sum(asks.values())),
        "bid_units_total": _round2(sum(bids.values())),
    }


# ════════════════════════════════════════════════════════════════════════════
# D2 — Indicative Market Price
# ════════════════════════════════════════════════════════════════════════════

async def _market_price(asset_id: str) -> dict:
    base = await _base_unit_price(asset_id)
    ob = await _order_book(asset_id)
    lt = await _last_mark(asset_id)

    last_price = float(lt["price"]) if lt else None
    bb, ba = ob["best_bid"], ob["best_ask"]

    if bb is not None and ba is not None:
        indicative = round((bb + ba) / 2, 4)
        basis = "mid"
    elif last_price is not None:
        indicative = round(last_price, 4)
        basis = "last_trade"
    elif bb is not None:
        indicative = bb
        basis = "best_bid"
    elif ba is not None:
        indicative = ba
        basis = "best_ask"
    else:
        indicative = 1.0
        basis = "par"

    last_block = None
    if lt:
        lp = float(lt["price"])
        last_block = {
            "price": round(lp, 4),
            "price_uah": _round2(lp * base),
            "units_uah": _round2(float(lt.get("units_uah") or 0)),
            "units": _units_from_uah(float(lt.get("units_uah") or 0), base),
            "premium_pct": round((lp - 1.0) * 100, 1),
            "at": _iso(lt.get("at")),
        }

    return {
        "asset_id": asset_id,
        "base_unit_price_uah": base,
        "par_multiplier": 1.0,
        "last_trade": last_block,
        "best_bid": bb,
        "best_bid_uah": ob["best_bid_uah"],
        "best_ask": ba,
        "best_ask_uah": ob["best_ask_uah"],
        "spread": ob["spread"],
        "spread_pct": ob["spread_pct"],
        "indicative_price": indicative,
        "indicative_price_uah": _round2(indicative * base),
        "indicative_basis": basis,
        "premium_discount_pct": round((indicative - 1.0) * 100, 2),
    }


# ════════════════════════════════════════════════════════════════════════════
# Price history (feeds chart + D8)
# ════════════════════════════════════════════════════════════════════════════

async def _price_history(asset_id: str, days: int = 90) -> dict:
    base = await _base_unit_price(asset_id)
    since = _now() - timedelta(days=days)
    marks = await _price_marks(asset_id, since=since)
    points: list[dict] = []
    for m in marks:
        p = float(m["price"])
        vol = float(m.get("gross_uah") or m.get("units_uah") or 0)
        points.append({
            "at": _iso(m["at"]),
            "price": round(p, 4),
            "price_uah": _round2(p * base),
            "volume_uah": _round2(vol),
            "premium_pct": round((p - 1.0) * 100, 1),
        })

    # daily VWAP aggregation
    daily: dict[str, dict] = {}
    for pt in points:
        day = (pt["at"] or "")[:10]
        d = daily.setdefault(day, {"date": day, "pv": 0.0, "v": 0.0, "n": 0,
                                   "high": pt["price"], "low": pt["price"]})
        d["pv"] += pt["price"] * pt["volume_uah"]
        d["v"] += pt["volume_uah"]
        d["n"] += 1
        d["high"] = max(d["high"], pt["price"])
        d["low"] = min(d["low"], pt["price"])
    daily_out = []
    for day in sorted(daily):
        d = daily[day]
        vwap = round(d["pv"] / d["v"], 4) if d["v"] else 1.0
        daily_out.append({"date": day, "vwap": vwap, "vwap_uah": _round2(vwap * base),
                          "volume_uah": _round2(d["v"]), "trades": d["n"],
                          "high": round(d["high"], 4), "low": round(d["low"], 4)})

    return {"asset_id": asset_id, "base_unit_price_uah": base,
            "points": points, "daily": daily_out, "count": len(points)}


# ════════════════════════════════════════════════════════════════════════════
# D8 — Price Discovery (NAV vs Market)
# ════════════════════════════════════════════════════════════════════════════

async def _price_discovery(asset_id: str) -> dict:
    base = await _base_unit_price(asset_id)
    mp = await _market_price(asset_id)
    total_trades = len(await _price_marks(asset_id))

    prem = mp["premium_discount_pct"]
    if prem > 1.0:
        band, label = "premium", "Торгується з премією до NAV"
    elif prem < -1.0:
        band, label = "discount", "Торгується з дисконтом до NAV"
    else:
        band, label = "fair", "Близько до справедливої вартості (NAV)"

    if total_trades >= 8:
        confidence = "high"
    elif total_trades >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "asset_id": asset_id,
        "nav_per_unit_uah": base,
        "market_price_uah": mp["indicative_price_uah"],
        "market_multiplier": mp["indicative_price"],
        "premium_discount_pct": prem,
        "band": band,
        "label": label,
        "basis": mp["indicative_basis"],
        "confidence": confidence,
        "trades_count": total_trades,
    }


# ════════════════════════════════════════════════════════════════════════════
# D3 — Liquidity Center metrics
# ════════════════════════════════════════════════════════════════════════════

async def _liquidity_metrics(asset_id: str) -> dict:
    base = await _base_unit_price(asset_id)
    holders = await _holders_count(asset_id)

    listed_uah = sum(
        float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        for L in await _active_listings(asset_id))
    demand_uah = sum(
        float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        for o in await _open_buy_orders(asset_id))

    ob = await _order_book(asset_id)

    since30 = _now() - timedelta(days=30)
    marks30 = await _price_marks(asset_id, since=since30)
    trades_30d = len(marks30)
    volume_30d = sum(float(m.get("gross_uah") or m.get("units_uah") or 0) for m in marks30)

    mm = await db.lumen_liquidity_providers.count_documents(
        {"asset_id": asset_id, "active": True})

    # Reuse B7 liquidity score (single source of truth) — best effort.
    score = None
    try:
        import lumen_asset_intelligence as _ai
        a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
        if a:
            _m, facts = await _ai._asset_metrics(a)
            score = _ai._liquidity(a, facts)
    except Exception:
        logger.exception("liquidity score reuse failed")

    return {
        "asset_id": asset_id,
        "base_unit_price_uah": base,
        "holders": holders,
        "units_listed_uah": _round2(listed_uah),
        "units_listed": _units_from_uah(listed_uah, base),
        "demand_uah": _round2(demand_uah),
        "demand_units": _units_from_uah(demand_uah, base),
        "best_bid": ob["best_bid"],
        "best_ask": ob["best_ask"],
        "spread_pct": ob["spread_pct"],
        "trades_30d": trades_30d,
        "volume_30d_uah": _round2(volume_30d),
        "market_maker_active": mm > 0,
        "score": score,
    }


# ════════════════════════════════════════════════════════════════════════════
# D4 — Exit Simulator
# ════════════════════════════════════════════════════════════════════════════

async def _exit_simulate(asset_id: str, units_uah: float,
                         investor_id: str) -> dict:
    base = await _base_unit_price(asset_id)
    owned = await _sec.compute_ownership_uah(investor_id, asset_id)
    listed = await _sec.listed_units_uah(investor_id, asset_id)
    available = _round2(max(0.0, owned - listed))

    requested = _round2(units_uah)
    want = min(requested, available)

    # Walk the BID book — highest price first, exclude own resting orders.
    orders = await _open_buy_orders(asset_id)
    orders = [o for o in orders if (o.get("investor_id") != investor_id)]
    orders.sort(key=lambda o: -float(o.get("limit_price") or 0))

    remaining = want
    gross = 0.0
    filled_uah = 0.0
    levels: list[dict] = []
    for o in orders:
        if remaining <= 0.5:
            break
        o_rem = float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        take = min(remaining, o_rem)
        if take <= 0.5:
            continue
        price = float(o.get("limit_price") or 1.0)
        gross += take * price
        filled_uah += take
        remaining -= take
        levels.append({
            "price": round(price, 4),
            "price_uah": _round2(price * base),
            "units_uah": _round2(take),
            "units": _units_from_uah(take, base),
            "proceeds_uah": _round2(take * price),
        })

    fee = _round2(gross * PLATFORM_FEE_PCT)
    net = _round2(gross - fee)
    avg_price = round(gross / filled_uah, 4) if filled_uah > 0.5 else None
    shortfall = _round2(max(0.0, want - filled_uah))

    mp = await _market_price(asset_id)

    return {
        "asset_id": asset_id,
        "base_unit_price_uah": base,
        "requested_units_uah": requested,
        "requested_units": _units_from_uah(requested, base),
        "available_units_uah": available,
        "available_units": _units_from_uah(available, base),
        "immediate_fillable_uah": _round2(filled_uah),
        "immediate_fillable_units": _units_from_uah(filled_uah, base),
        "avg_price": avg_price,
        "avg_price_uah": _round2(avg_price * base) if avg_price else None,
        "gross_proceeds_uah": _round2(gross),
        "fee_pct": PLATFORM_FEE_PCT,
        "fee_uah": fee,
        "net_proceeds_uah": net,
        "shortfall_units_uah": shortfall,
        "shortfall_units": _units_from_uah(shortfall, base),
        "fully_fillable": shortfall <= 0.5 and want > 0.5,
        "exceeds_holdings": requested > available + 0.5,
        "indicative_price": mp["indicative_price"],
        "indicative_price_uah": mp["indicative_price_uah"],
        "levels": levels,
    }


# ════════════════════════════════════════════════════════════════════════════
# D5 — Market Activity Feed (anonymised)
# ════════════════════════════════════════════════════════════════════════════

async def _activity_feed(asset_id: Optional[str] = None, limit: int = 25) -> list[dict]:
    items: list[dict] = []
    base_cache: dict[str, float] = {}

    async def _base(aid: str) -> float:
        if aid not in base_cache:
            base_cache[aid] = await _base_unit_price(aid)
        return base_cache[aid]

    title_cache: dict[str, Optional[str]] = {}

    async def _title(aid: str) -> Optional[str]:
        if aid not in title_cache:
            a = await db.lumen_assets.find_one({"id": aid}, {"title": 1})
            title_cache[aid] = (a or {}).get("title")
        return title_cache[aid]

    tq: dict[str, Any] = {"status": "settled"}
    if asset_id:
        tq["asset_id"] = asset_id
    async for t in db.lumen_secondary_trades.find(tq).sort("settled_at", -1).limit(limit):
        aid = t["asset_id"]
        base = await _base(aid)
        p = float(t.get("price_per_unit") or 1.0)
        u_uah = float(t.get("units_uah") or 0)
        units = _units_from_uah(u_uah, base)
        prem = round((p - 1.0) * 100, 1)
        items.append({
            "type": "trade",
            "asset_id": aid,
            "asset_title": await _title(aid),
            "units": units,
            "units_uah": _round2(u_uah),
            "price": round(p, 4),
            "price_uah": _round2(p * base),
            "premium_pct": prem,
            "at": _iso(t.get("settled_at") or t.get("created_at")),
        })

    # historical / demo price marks (anonymised past trades)
    pq: dict[str, Any] = {}
    if asset_id:
        pq["asset_id"] = asset_id
    async for pt in db.lumen_liquidity_price_points.find(pq).sort("at", -1).limit(limit):
        aid = pt["asset_id"]
        base = await _base(aid)
        p = float(pt.get("price") or 1.0)
        u_uah = float(pt.get("units_uah") or 0)
        items.append({
            "type": "trade",
            "asset_id": aid,
            "asset_title": await _title(aid),
            "units": _units_from_uah(u_uah, base),
            "units_uah": _round2(u_uah),
            "price": round(p, 4),
            "price_uah": _round2(p * base),
            "premium_pct": round((p - 1.0) * 100, 1),
            "at": _iso(pt.get("at")),
        })

    lq: dict[str, Any] = {"status": {"$in": ["active", "partially_filled"]}}
    if asset_id:
        lq["asset_id"] = asset_id
    async for L in db.lumen_secondary_listings.find(lq).sort("created_at", -1).limit(limit):
        aid = L["asset_id"]
        base = await _base(aid)
        p = float(L.get("price_per_unit") or 1.0)
        rem = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        items.append({
            "type": "listing",
            "asset_id": aid,
            "asset_title": await _title(aid),
            "units": _units_from_uah(rem, base),
            "units_uah": _round2(rem),
            "price": round(p, 4),
            "price_uah": _round2(p * base),
            "premium_pct": round((p - 1.0) * 100, 1),
            "at": _iso(L.get("created_at")),
        })

    oq: dict[str, Any] = {"side": "buy", "status": {"$in": ["open", "partial"]}}
    if asset_id:
        oq["asset_id"] = asset_id
    async for o in db.lumen_liquidity_orders.find(oq).sort("created_at", -1).limit(limit):
        aid = o["asset_id"]
        base = await _base(aid)
        p = float(o.get("limit_price") or 1.0)
        rem = float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        items.append({
            "type": "bid",
            "asset_id": aid,
            "asset_title": await _title(aid),
            "units": _units_from_uah(rem, base),
            "units_uah": _round2(rem),
            "price": round(p, 4),
            "price_uah": _round2(p * base),
            "premium_pct": round((p - 1.0) * 100, 1),
            "at": _iso(o.get("created_at")),
        })

    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return items[:limit]


# ════════════════════════════════════════════════════════════════════════════
# market_sentiment — composite (C5 mood · C4 voting · activity · demand)
# ════════════════════════════════════════════════════════════════════════════

async def _market_sentiment(asset_id: str) -> dict:
    components: list[dict] = []

    # 1) Community mood (C5) — unit-weighted positive vs negative → −100..+100
    mood_score = 0.0
    mood_available = False
    try:
        import lumen_community as _comm
        s = await _comm._sentiment(asset_id)
        if s.get("available"):
            mood_available = True
            mood_score = float(s.get("positive", 0)) - float(s.get("negative", 0))
    except Exception:
        logger.exception("community sentiment read failed")
    components.append({"key": "mood", "label": "Настрій власників (C5)",
                       "weight": 0.40, "score": round(mood_score),
                       "available": mood_available})

    # 2) Secondary demand — demand vs supply imbalance → −100..+100
    metrics = await _liquidity_metrics(asset_id)
    demand = metrics["demand_uah"]
    supply = metrics["units_listed_uah"]
    if (demand + supply) > 0:
        demand_score = (demand - supply) / (demand + supply) * 100.0
        demand_available = True
    else:
        demand_score = 0.0
        demand_available = False
    components.append({"key": "demand", "label": "Попит vs пропозиція",
                       "weight": 0.35, "score": round(demand_score),
                       "available": demand_available})

    # 3) Community activity (30d posts + comments) — engagement → 0..+100
    activity_score = 0.0
    activity_available = False
    try:
        since30 = _now() - timedelta(days=30)
        posts = await db.lumen_community_posts.count_documents(
            {"asset_id": asset_id, "created_at": {"$gte": since30}})
        comments = await db.lumen_community_comments.count_documents(
            {"asset_id": asset_id, "created_at": {"$gte": since30}})
        engagement = posts + comments
        if engagement > 0:
            activity_available = True
            activity_score = min(100.0, engagement * 12.0)
    except Exception:
        logger.exception("community activity read failed")
    components.append({"key": "activity", "label": "Активність спільноти (30д)",
                       "weight": 0.15, "score": round(activity_score),
                       "available": activity_available})

    # 4) Voting participation (C4) — turnout → 0..+100
    voting_score = 0.0
    voting_available = False
    try:
        polls = await db.lumen_community_polls.count_documents({"asset_id": asset_id})
        ballots = await db.lumen_community_ballots.count_documents({"asset_id": asset_id})
        if polls > 0:
            voting_available = True
            voting_score = min(100.0, (ballots / max(1, polls)) * 20.0)
    except Exception:
        logger.exception("community voting read failed")
    components.append({"key": "voting", "label": "Участь у голосуваннях (C4)",
                       "weight": 0.10, "score": round(voting_score),
                       "available": voting_available})

    # Composite — reweight over the components that actually have data.
    avail = [c for c in components if c["available"]]
    if avail:
        wsum = sum(c["weight"] for c in avail)
        composite = sum(c["score"] * (c["weight"] / wsum) for c in avail)
    else:
        composite = 0.0
    composite = max(-100.0, min(100.0, composite))

    if composite >= 25:
        band, label = "bullish", "Оптимістичний"
    elif composite <= -25:
        band, label = "bearish", "Песимістичний"
    else:
        band, label = "neutral", "Нейтральний"

    return {
        "asset_id": asset_id,
        "score": round(composite),
        "band": band,
        "label": label,
        "available": bool(avail),
        "components": components,
    }


# ════════════════════════════════════════════════════════════════════════════
# D1 — Live limit-order matching (reuses _settle_trade)
# ════════════════════════════════════════════════════════════════════════════

async def _match_buy_order(order: dict, actor: dict,
                           request: Optional[Request]) -> list[dict]:
    """Cross a resting buy order against active listings (cheapest ASK first)."""
    asset_id = order["asset_id"]
    buyer_id = order["investor_id"]
    limit_price = float(order["limit_price"])

    listings = await _active_listings(asset_id)
    listings = [L for L in listings
                if float(L.get("price_per_unit") or 1.0) <= limit_price + 1e-6
                and L.get("seller_id") != buyer_id]
    listings.sort(key=lambda L: (float(L.get("price_per_unit") or 0),
                                 _as_dt(L.get("created_at")) or _now()))

    remaining = float(order["units_uah"]) - float(order.get("filled_units_uah") or 0)
    trades: list[dict] = []

    for L in listings:
        if remaining <= 0.5:
            break
        l_rem = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        take = min(remaining, l_rem)
        if take <= 0.5:
            continue
        price = float(L.get("price_per_unit") or 1.0)
        gross = _round2(take * price)
        fee = _round2(gross * PLATFORM_FEE_PCT)
        trade = {
            "id": f"tr-{uuid.uuid4().hex[:12]}",
            "listing_id": L["id"], "bid_id": None, "order_id": order["id"],
            "seller_id": L["seller_id"], "buyer_id": buyer_id,
            "asset_id": asset_id, "units_uah": _round2(take),
            "price_per_unit": price, "gross_uah": gross, "fee_uah": fee,
            "seller_net_uah": _round2(gross - fee), "currency": BASE_CURRENCY,
            "status": "pending", "created_at": _now(), "source": "liquidity_order",
        }
        await db.lumen_secondary_trades.insert_one(trade)
        try:
            settled = await _sec._settle_trade(trade, actor=actor, request=request)
            trades.append(_sec._strip_trade(settled))
            remaining -= take
        except HTTPException as e:
            # e.g. insufficient wallet funds — stop matching, leave order resting
            logger.info("buy-order match halted (%s): %s", order["id"],
                        getattr(e, "detail", e))
            break
        except Exception:
            logger.exception("buy-order settlement failed for %s", order["id"])
            break

    filled = _round2(float(order.get("filled_units_uah") or 0)
                     + (float(order["units_uah"]) - float(order.get("filled_units_uah") or 0) - remaining))
    if filled + 0.5 >= float(order["units_uah"]):
        status = "filled"
    elif filled > 0.5:
        status = "partial"
    else:
        status = "open"
    await db.lumen_liquidity_orders.update_one(
        {"id": order["id"]},
        {"$set": {"filled_units_uah": filled, "status": status, "updated_at": _now()}},
    )
    return trades


async def _match_listing_against_orders(listing: dict, actor: dict,
                                        request: Optional[Request]) -> list[dict]:
    """When a new sell listing crosses resting buy orders (highest BID first)."""
    asset_id = listing["asset_id"]
    seller_id = listing["seller_id"]
    listing_price = float(listing.get("price_per_unit") or 1.0)

    orders = await _open_buy_orders(asset_id)
    orders = [o for o in orders
              if float(o.get("limit_price") or 0) >= listing_price - 1e-6
              and o.get("investor_id") != seller_id]
    orders.sort(key=lambda o: -float(o.get("limit_price") or 0))

    listing_rem = float(listing.get("units_uah") or 0) - float(listing.get("filled_units_uah") or 0)
    trades: list[dict] = []

    for o in orders:
        if listing_rem <= 0.5:
            break
        o_rem = float(o.get("units_uah") or 0) - float(o.get("filled_units_uah") or 0)
        take = min(listing_rem, o_rem)
        if take <= 0.5:
            continue
        price = listing_price  # taker is the seller → trade at the resting ask price
        gross = _round2(take * price)
        fee = _round2(gross * PLATFORM_FEE_PCT)
        trade = {
            "id": f"tr-{uuid.uuid4().hex[:12]}",
            "listing_id": listing["id"], "bid_id": None, "order_id": o["id"],
            "seller_id": seller_id, "buyer_id": o["investor_id"],
            "asset_id": asset_id, "units_uah": _round2(take),
            "price_per_unit": price, "gross_uah": gross, "fee_uah": fee,
            "seller_net_uah": _round2(gross - fee), "currency": BASE_CURRENCY,
            "status": "pending", "created_at": _now(), "source": "liquidity_cross",
        }
        await db.lumen_secondary_trades.insert_one(trade)
        try:
            settled = await _sec._settle_trade(trade, actor=actor, request=request)
            trades.append(_sec._strip_trade(settled))
            listing_rem -= take
            new_o_filled = _round2(float(o.get("filled_units_uah") or 0) + take)
            o_status = "filled" if new_o_filled + 0.5 >= float(o["units_uah"]) else "partial"
            await db.lumen_liquidity_orders.update_one(
                {"id": o["id"]},
                {"$set": {"filled_units_uah": new_o_filled, "status": o_status,
                          "updated_at": _now()}},
            )
        except HTTPException as e:
            logger.info("listing cross skipped order %s: %s", o["id"],
                        getattr(e, "detail", e))
            continue
        except Exception:
            logger.exception("listing cross settlement failed")
            continue

    return trades


# ════════════════════════════════════════════════════════════════════════════
# Pydantic
# ════════════════════════════════════════════════════════════════════════════

class PlaceOrderIn(BaseModel):
    asset_id: str
    side: str = Field("buy", pattern="^(buy|sell)$")
    units_uah: float = Field(..., gt=0)
    limit_price: float = Field(1.0, gt=0, le=5)
    expires_in_days: int = Field(30, ge=1, le=180)


class ExitSimIn(BaseModel):
    asset_id: str
    units_uah: float = Field(..., gt=0)


class MarketMakerIn(BaseModel):
    asset_id: str
    name: str
    kind: str = Field("fund", pattern="^(fund|operator|spv|external)$")
    committed_uah: float = Field(0.0, ge=0)
    target_spread_pct: float = Field(2.0, ge=0, le=50)
    active: bool = True


# ════════════════════════════════════════════════════════════════════════════
# Public / investor read endpoints (D1/D2/D3/D5/D8 + sentiment)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/assets/{asset_id}/orderbook")
async def get_orderbook(asset_id: str, depth: int = Query(12, ge=1, le=50)):
    await _asset_or_404(asset_id)
    return await _order_book(asset_id, depth)


@router.get("/assets/{asset_id}/market-price")
async def get_market_price(asset_id: str):
    await _asset_or_404(asset_id)
    return await _market_price(asset_id)


@router.get("/assets/{asset_id}/price-history")
async def get_price_history(asset_id: str, days: int = Query(90, ge=1, le=365)):
    await _asset_or_404(asset_id)
    return await _price_history(asset_id, days)


@router.get("/assets/{asset_id}/price-discovery")
async def get_price_discovery(asset_id: str):
    await _asset_or_404(asset_id)
    return await _price_discovery(asset_id)


@router.get("/assets/{asset_id}/liquidity-center")
async def get_liquidity_center(asset_id: str):
    await _asset_or_404(asset_id)
    metrics = await _liquidity_metrics(asset_id)
    providers = []
    async for p in db.lumen_liquidity_providers.find(
            {"asset_id": asset_id, "active": True}):
        providers.append(_strip_order(p))
    return {"metrics": metrics, "market_makers": providers,
            "platform_fee_pct": PLATFORM_FEE_PCT}


@router.get("/assets/{asset_id}/market-sentiment")
async def get_market_sentiment(asset_id: str):
    await _asset_or_404(asset_id)
    return await _market_sentiment(asset_id)


@router.get("/liquidity/activity")
async def get_activity(asset_id: Optional[str] = None,
                       limit: int = Query(25, ge=1, le=100)):
    return {"items": await _activity_feed(asset_id, limit)}


@router.get("/assets/{asset_id}/liquidity-bundle")
async def get_asset_liquidity_bundle(asset_id: str, request: Request):
    """One call powering the asset-detail Liquidity tab."""
    await _asset_or_404(asset_id)
    user = await _optional_user(request)
    uid = _uid(user)
    bundle = {
        "order_book": await _order_book(asset_id),
        "market_price": await _market_price(asset_id),
        "price_discovery": await _price_discovery(asset_id),
        "price_history": await _price_history(asset_id, 90),
        "metrics": await _liquidity_metrics(asset_id),
        "sentiment": await _market_sentiment(asset_id),
        "activity": await _activity_feed(asset_id, 12),
        "platform_fee_pct": PLATFORM_FEE_PCT,
    }
    if uid:
        bundle["watching"] = await db.lumen_watchlists.count_documents(
            {"user_id": uid, "asset_id": asset_id}) > 0
        owned = await _sec.compute_ownership_uah(uid, asset_id)
        listed = await _sec.listed_units_uah(uid, asset_id)
        base = await _base_unit_price(asset_id)
        bundle["my_position"] = {
            "owned_uah": _round2(owned),
            "available_uah": _round2(max(0.0, owned - listed)),
            "owned_units": _units_from_uah(owned, base),
            "available_units": _units_from_uah(max(0.0, owned - listed), base),
        }
    return bundle


# ════════════════════════════════════════════════════════════════════════════
# D4 — Exit Simulator (auth)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/investor/liquidity/exit-simulate")
async def exit_simulate(payload: ExitSimIn, user=Depends(get_current_user)):
    await _asset_or_404(payload.asset_id)
    return await _exit_simulate(payload.asset_id, payload.units_uah, _uid(user))


# ════════════════════════════════════════════════════════════════════════════
# D1 — Orders (auth)
# ════════════════════════════════════════════════════════════════════════════

@router.post("/investor/liquidity/orders")
async def place_order(payload: PlaceOrderIn, request: Request,
                      user=Depends(get_current_user)):
    uid = _uid(user)
    await _asset_or_404(payload.asset_id)

    if payload.side == "sell":
        # Reuse Sprint-13 ownership guard, create a listing, then cross orders.
        available = await _sec.compute_ownership_uah(uid, payload.asset_id)
        locked = await _sec.listed_units_uah(uid, payload.asset_id)
        free = available - locked
        if payload.units_uah < _sec.MIN_LISTING_UAH:
            raise HTTPException(status_code=400,
                                detail=f"Мінімум для продажу: {fmt_uah_as_usd(_sec.MIN_LISTING_UAH)}")
        if free + 0.5 < payload.units_uah:
            raise HTTPException(status_code=400,
                                detail=f"Доступно для продажу: {fmt_uah_as_usd(free, decimals=2)}")
        listing = {
            "id": f"sl-{uuid.uuid4().hex[:12]}",
            "seller_id": uid, "asset_id": payload.asset_id,
            "units_uah": _round2(payload.units_uah),
            "price_per_unit": float(payload.limit_price),
            "filled_units_uah": 0.0, "currency": BASE_CURRENCY,
            "status": "active", "created_at": _now(), "updated_at": _now(),
            "expires_at": _now() + timedelta(days=payload.expires_in_days),
            "source": "liquidity_order",
        }
        await db.lumen_secondary_listings.insert_one(listing)
        trades = await _match_listing_against_orders(listing, actor=user, request=request)
        L = await db.lumen_secondary_listings.find_one({"id": listing["id"]})
        return {"side": "sell", "listing": _sec._strip_listing(L), "trades": trades}

    # BUY — rest the order, then cross against listings.
    order = {
        "id": f"lo-{uuid.uuid4().hex[:12]}",
        "asset_id": payload.asset_id, "side": "buy", "investor_id": uid,
        "units_uah": _round2(payload.units_uah),
        "limit_price": float(payload.limit_price),
        "filled_units_uah": 0.0, "status": "open",
        "currency": BASE_CURRENCY, "created_at": _now(), "updated_at": _now(),
        "expires_at": _now() + timedelta(days=payload.expires_in_days),
    }
    await db.lumen_liquidity_orders.insert_one(order)
    trades = await _match_buy_order(order, actor=user, request=request)
    o = await db.lumen_liquidity_orders.find_one({"id": order["id"]})
    return {"side": "buy", "order": _strip_order(o), "trades": trades}


@router.get("/investor/liquidity/orders")
async def my_orders(user=Depends(get_current_user)):
    uid = _uid(user)
    items = []
    async for o in db.lumen_liquidity_orders.find(
            {"investor_id": uid}).sort("created_at", -1):
        out = _strip_order(o)
        a = await db.lumen_assets.find_one({"id": o["asset_id"]}, {"title": 1})
        if a:
            out["asset_title"] = a.get("title")
        items.append(out)
    return {"items": items}


@router.post("/investor/liquidity/orders/{order_id}/cancel")
async def cancel_order(order_id: str, user=Depends(get_current_user)):
    o = await db.lumen_liquidity_orders.find_one({"id": order_id})
    if not o:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    if o.get("investor_id") != _uid(user):
        raise HTTPException(status_code=403, detail="Лише автор може скасувати")
    if o.get("status") in ("filled", "cancelled", "expired"):
        raise HTTPException(status_code=409, detail=f"Заявка у статусі {o.get('status')}")
    await db.lumen_liquidity_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "updated_at": _now()}},
    )
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════
# D6 — Watchlists (auth)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/investor/watchlist")
async def get_watchlist(user=Depends(get_current_user)):
    uid = _uid(user)
    items = []
    async for w in db.lumen_watchlists.find({"user_id": uid}).sort("created_at", -1):
        aid = w["asset_id"]
        a = await db.lumen_assets.find_one(
            {"id": aid}, {"title": 1, "category": 1, "cover_url": 1})
        if not a:
            continue
        mp = await _market_price(aid)
        items.append({
            "asset_id": aid,
            "asset_title": a.get("title"),
            "category": a.get("category"),
            "cover_url": a.get("cover_url"),
            "indicative_price_uah": mp["indicative_price_uah"],
            "premium_discount_pct": mp["premium_discount_pct"],
            "best_bid": mp["best_bid"], "best_ask": mp["best_ask"],
            "added_at": _iso(w.get("created_at")),
        })
    return {"items": items}


@router.post("/investor/watchlist/{asset_id}")
async def add_watchlist(asset_id: str, user=Depends(get_current_user)):
    await _asset_or_404(asset_id)
    uid = _uid(user)
    existing = await db.lumen_watchlists.find_one({"user_id": uid, "asset_id": asset_id})
    if existing:
        return {"ok": True, "watching": True}
    await db.lumen_watchlists.insert_one({
        "id": f"wl-{uuid.uuid4().hex[:12]}",
        "user_id": uid, "asset_id": asset_id, "created_at": _now(),
    })
    return {"ok": True, "watching": True}


@router.delete("/investor/watchlist/{asset_id}")
async def remove_watchlist(asset_id: str, user=Depends(get_current_user)):
    await db.lumen_watchlists.delete_many({"user_id": _uid(user), "asset_id": asset_id})
    return {"ok": True, "watching": False}


@router.get("/investor/watchlist/feed")
async def watchlist_feed(user=Depends(get_current_user),
                         limit: int = Query(40, ge=1, le=100)):
    uid = _uid(user)
    asset_ids = [w["asset_id"] async for w in db.lumen_watchlists.find({"user_id": uid})]
    if not asset_ids:
        return {"items": [], "asset_ids": []}

    title_cache: dict[str, Optional[str]] = {}

    async def _title(aid: str) -> Optional[str]:
        if aid not in title_cache:
            a = await db.lumen_assets.find_one({"id": aid}, {"title": 1})
            title_cache[aid] = (a or {}).get("title")
        return title_cache[aid]

    items: list[dict] = []

    # trades + listings (anonymised activity)
    for aid in asset_ids:
        for ev in await _activity_feed(aid, 8):
            items.append(ev)

    # payouts on watched assets
    async for rec in db.lumen_payout_records.find(
            {"asset_id": {"$in": asset_ids}}).sort("paid_date", -1).limit(limit):
        items.append({
            "type": "payout",
            "asset_id": rec.get("asset_id"),
            "asset_title": await _title(rec.get("asset_id")),
            "amount_uah": _round2(float(rec.get("amount_uah") or 0)),
            "status": rec.get("status"),
            "at": _iso(rec.get("paid_date") or rec.get("created_at")),
        })

    items.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"items": items[:limit], "asset_ids": asset_ids}


# ════════════════════════════════════════════════════════════════════════════
# D7 — Market Makers (admin)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/liquidity/market-makers")
async def admin_list_market_makers(asset_id: Optional[str] = None,
                                   _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    async for p in db.lumen_liquidity_providers.find(q).sort("created_at", -1):
        out = _strip_order(p)
        a = await db.lumen_assets.find_one({"id": p["asset_id"]}, {"title": 1})
        if a:
            out["asset_title"] = a.get("title")
        items.append(out)
    return {"items": items, "kinds": list(MM_KINDS)}


@router.post("/admin/liquidity/market-makers")
async def admin_create_market_maker(payload: MarketMakerIn,
                                    _=Depends(require_admin)):
    await _asset_or_404(payload.asset_id)
    doc = {
        "id": f"mm-{uuid.uuid4().hex[:12]}",
        "asset_id": payload.asset_id, "name": payload.name.strip(),
        "kind": payload.kind, "committed_uah": _round2(payload.committed_uah),
        "target_spread_pct": float(payload.target_spread_pct),
        "active": bool(payload.active),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_liquidity_providers.insert_one(doc)
    return _strip_order(doc)


@router.patch("/admin/liquidity/market-makers/{mm_id}")
async def admin_update_market_maker(mm_id: str, payload: dict = Body(...),
                                    _=Depends(require_admin)):
    upd = {k: payload[k] for k in
           ("name", "kind", "committed_uah", "target_spread_pct", "active")
           if k in payload}
    if not upd:
        raise HTTPException(status_code=400, detail="Немає змін")
    upd["updated_at"] = _now()
    r = await db.lumen_liquidity_providers.update_one({"id": mm_id}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Не знайдено")
    return {"ok": True}


@router.delete("/admin/liquidity/market-makers/{mm_id}")
async def admin_delete_market_maker(mm_id: str, _=Depends(require_admin)):
    await db.lumen_liquidity_providers.delete_one({"id": mm_id})
    return {"ok": True}


@router.get("/admin/liquidity/overview")
async def admin_liquidity_overview(_=Depends(require_admin)):
    open_orders = await db.lumen_liquidity_orders.count_documents(
        {"status": {"$in": ["open", "partial"]}})
    active_listings = await db.lumen_secondary_listings.count_documents(
        {"status": {"$in": ["active", "partially_filled"]}})
    settled_trades = await db.lumen_secondary_trades.count_documents({"status": "settled"})
    watchers = await db.lumen_watchlists.count_documents({})
    market_makers = await db.lumen_liquidity_providers.count_documents({"active": True})

    # Per-asset snapshot
    assets = []
    async for a in db.lumen_assets.find({}, {"id": 1, "title": 1}):
        mp = await _market_price(a["id"])
        m = await _liquidity_metrics(a["id"])
        assets.append({
            "asset_id": a["id"], "asset_title": a.get("title"),
            "indicative_price_uah": mp["indicative_price_uah"],
            "premium_discount_pct": mp["premium_discount_pct"],
            "best_bid": mp["best_bid"], "best_ask": mp["best_ask"],
            "spread_pct": m["spread_pct"], "holders": m["holders"],
            "trades_30d": m["trades_30d"], "volume_30d_uah": m["volume_30d_uah"],
            "demand_uah": m["demand_uah"], "units_listed_uah": m["units_listed_uah"],
        })
    assets.sort(key=lambda x: -(x["volume_30d_uah"] or 0))

    return {
        "open_orders": open_orders, "active_listings": active_listings,
        "settled_trades": settled_trades, "watchers": watchers,
        "market_makers": market_makers, "assets": assets,
    }


# ════════════════════════════════════════════════════════════════════════════
# Indexes + idempotent demo seed
# ════════════════════════════════════════════════════════════════════════════

async def ensure_liquidity_indexes() -> None:
    try:
        await db.lumen_liquidity_orders.create_index([("asset_id", 1), ("status", 1)])
        await db.lumen_liquidity_orders.create_index([("investor_id", 1)])
        await db.lumen_watchlists.create_index([("user_id", 1), ("asset_id", 1)], unique=True)
        await db.lumen_liquidity_providers.create_index([("asset_id", 1), ("active", 1)])
    except Exception:
        logger.exception("liquidity indexes failed")


async def _ensure_demo_buyer() -> str:
    u = await db.users.find_one({"email": DEMO_BUYER_EMAIL})
    if u:
        return u.get("user_id") or u.get("id")
    uid = f"user_liqdemo_{uuid.uuid4().hex[:10]}"
    await db.users.insert_one({
        "user_id": uid, "id": uid, "email": DEMO_BUYER_EMAIL,
        "name": "Демо-покупець", "role": "client", "roles": ["client"],
        "active_role": "client", "states": ["client"],
        "password_hash": None, "created_at": _iso(_now()),
    })
    return uid


async def seed_liquidity_demo() -> dict:
    """Idempotent demo so the Liquidity OS is alive on a fresh DB.

    • resting BUY orders below best ASK  → BID depth + demand + exit sim
    • historical settled trades          → price history + discovery (NO
      share-transfer side-effects: invariants check ownership vs
      investments+transfers, never vs trades, so price-history seed is safe)
    • a market-maker per flagship asset
    • the primary demo investor watches a couple of assets
    """
    await ensure_liquidity_indexes()
    stats = {"orders": 0, "trades": 0, "market_makers": 0, "watchlist": 0}

    buyer_id = await _ensure_demo_buyer()

    # ── resting BUY orders (BID side) ───────────────────────────────────────
    if await db.lumen_liquidity_orders.count_documents({}) == 0:
        plan = [
            {"asset_id": "asset-podilskyi", "units_uah": 60000, "price": 0.95},
            {"asset_id": "asset-podilskyi", "units_uah": 30000, "price": 0.93},
            {"asset_id": "asset-lavr-tc", "units_uah": 50000, "price": 1.00},
            {"asset_id": "asset-lavr-tc", "units_uah": 25000, "price": 0.98},
        ]
        for p in plan:
            if not await db.lumen_assets.find_one({"id": p["asset_id"]}):
                continue
            await db.lumen_liquidity_orders.insert_one({
                "id": f"lo-seed-{uuid.uuid4().hex[:10]}",
                "asset_id": p["asset_id"], "side": "buy",
                "investor_id": buyer_id, "units_uah": float(p["units_uah"]),
                "limit_price": float(p["price"]), "filled_units_uah": 0.0,
                "status": "open", "currency": BASE_CURRENCY, "is_seed": True,
                "created_at": _now(), "updated_at": _now(),
                "expires_at": _now() + timedelta(days=30),
            })
            stats["orders"] += 1

    # ── historical price points (chart + discovery) ─────────────────────────
    # Stored in a DEDICATED collection — NOT as fake settled trades — so the
    # consistency invariants I11/I12 (settled trade ⇒ share_transfer + ledger)
    # stay green. These are indicative historical marks for the price chart.
    if await db.lumen_liquidity_price_points.count_documents({}) == 0:
        walks = {
            "asset-podilskyi": [0.95, 0.96, 0.94, 0.97, 0.98, 0.96, 0.99, 0.97],
            "asset-lavr-tc":   [1.01, 1.02, 1.00, 1.03, 1.02, 1.04, 1.03, 1.05],
        }
        for aid, prices in walks.items():
            if not await db.lumen_assets.find_one({"id": aid}):
                continue
            n = len(prices)
            for i, pr in enumerate(prices):
                units_uah = 8000.0 + (i % 3) * 2500.0
                days_ago = (n - i) * 9
                ts = _now() - timedelta(days=days_ago)
                await db.lumen_liquidity_price_points.insert_one({
                    "id": f"pp-seed-{uuid.uuid4().hex[:10]}",
                    "asset_id": aid, "price": pr,
                    "units_uah": units_uah, "gross_uah": _round2(units_uah * pr),
                    "is_seed": True, "at": ts, "created_at": ts,
                })
                stats["trades"] += 1

    # ── market makers ───────────────────────────────────────────────────────
    if await db.lumen_liquidity_providers.count_documents({}) == 0:
        for aid, name in (("asset-podilskyi", "Lumen Liquidity Fund"),
                          ("asset-lavr-tc", "Lumen Liquidity Fund")):
            if not await db.lumen_assets.find_one({"id": aid}):
                continue
            await db.lumen_liquidity_providers.insert_one({
                "id": f"mm-seed-{uuid.uuid4().hex[:10]}",
                "asset_id": aid, "name": name, "kind": "fund",
                "committed_uah": 500000.0, "target_spread_pct": 2.0,
                "active": True, "is_seed": True,
                "created_at": _now(), "updated_at": _now(),
            })
            stats["market_makers"] += 1

    # ── primary demo investor watchlist ─────────────────────────────────────
    client = await db.users.find_one({"email": "client@atlas.dev"})
    if client:
        cid = client.get("user_id") or client.get("id")
        for aid in ("asset-lavr-tc", "asset-podilskyi"):
            if not await db.lumen_assets.find_one({"id": aid}):
                continue
            if not await db.lumen_watchlists.find_one({"user_id": cid, "asset_id": aid}):
                await db.lumen_watchlists.insert_one({
                    "id": f"wl-seed-{uuid.uuid4().hex[:10]}",
                    "user_id": cid, "asset_id": aid, "is_seed": True,
                    "created_at": _now(),
                })
                stats["watchlist"] += 1

    return stats


@router.on_event("startup")
async def _liquidity_startup():
    await ensure_liquidity_indexes()


__all__ = [
    "router", "ensure_liquidity_indexes", "seed_liquidity_demo",
    "_order_book", "_market_price", "_price_discovery", "_market_sentiment",
    "_exit_simulate", "_liquidity_metrics", "PLATFORM_FEE_PCT",
]
