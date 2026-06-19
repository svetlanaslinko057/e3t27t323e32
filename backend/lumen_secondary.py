"""
LUMEN Sprint 13 — Secondary Market

Investors who already own units of an asset can list those units for sale to
other investors. Trading happens entirely INSIDE the platform:
  • settlement runs through the existing Ownership Registry — no parallel
    accounting of shares;
  • money moves through the existing Ledger — no parallel wallet;
  • the only NEW append-only artefact is `lumen_share_transfers` which
    records who handed shares to whom, when, and which trade triggered it.

Architecture
------------

  Ownership(investor, asset) =
      Σ primary investments (investor, asset, status=active)
      + Σ inbound  share_transfers
      - Σ outbound share_transfers

  Listing  → Bid (optional) → Trade → Settlement → 3 ledger entries
                                                  + 1 share_transfer
                                                  + buyer ownership ↑
                                                  + seller ownership ↓

Money conservation per trade (gross = units * price):
    buyer  debit  gross
    seller credit gross - fee          (reason=secondary_sale)
    plat.  credit fee                  (reason=platform_fee, investor=PLATFORM)
    ─── total = 0 ✓

Forbidden in this sprint (the user was explicit):
  ❌ auctions
  ❌ margin trading
  ❌ tokenization
  ❌ full order book
  ❌ partial credit on trades
  ❌ P2P crypto
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso, lr2_perm as _lr2_perm
from lumen_audit import write_audit
from lumen_payments import _ledger_append, _round2, BASE_CURRENCY
from lumen_wallet import recompute_wallet
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer

logger = logging.getLogger("lumen.secondary")

# ----------------------------------------------------------------------------
# Configuration (envable)
# ----------------------------------------------------------------------------

PLATFORM_FEE_PCT = float(os.environ.get("SECONDARY_FEE_PCT", "0.01"))   # 1%
LISTING_TTL_DAYS = int(os.environ.get("SECONDARY_LISTING_TTL_DAYS", "30"))
MIN_LISTING_UAH  = float(os.environ.get("SECONDARY_MIN_UAH", "100"))
PLATFORM_REVENUE_ACCOUNT = "platform-revenue"  # virtual investor id used in ledger

LISTING_STATUSES = ("draft", "active", "partially_filled", "filled",
                    "cancelled", "expired")
BID_STATUSES     = ("active", "accepted", "rejected", "cancelled", "expired")
TRADE_STATUSES   = ("pending", "settled", "failed", "cancelled")


# ----------------------------------------------------------------------------
# Indexes
# ----------------------------------------------------------------------------

async def ensure_indexes() -> None:
    try:
        await db.lumen_secondary_listings.create_index([("status", 1), ("created_at", -1)])
        await db.lumen_secondary_listings.create_index([("seller_id", 1)])
        await db.lumen_secondary_listings.create_index([("asset_id", 1)])
        await db.lumen_secondary_bids.create_index([("listing_id", 1)])
        await db.lumen_secondary_bids.create_index([("buyer_id", 1)])
        await db.lumen_secondary_trades.create_index([("seller_id", 1)])
        await db.lumen_secondary_trades.create_index([("buyer_id", 1)])
        await db.lumen_share_transfers.create_index([("asset_id", 1)])
        await db.lumen_share_transfers.create_index([("from_investor_id", 1)])
        await db.lumen_share_transfers.create_index([("to_investor_id", 1)])
    except Exception:
        logger.exception("secondary indexes failed")


# ----------------------------------------------------------------------------
# Ownership maths
# ----------------------------------------------------------------------------

async def compute_ownership_uah(investor_id: str, asset_id: str) -> float:
    """Truth: primary investments + inbound transfers − outbound transfers."""
    primary = 0.0
    async for inv in db.lumen_investments.find({
        "investor_id": investor_id, "asset_id": asset_id, "status": "active",
    }):
        primary += float(inv.get("amount_uah") or inv.get("amount")
                         or inv.get("invested_amount") or 0)
    inflow = 0.0
    async for t in db.lumen_share_transfers.find({
        "to_investor_id": investor_id, "asset_id": asset_id,
    }):
        inflow += float(t.get("amount_uah") or 0)
    outflow = 0.0
    async for t in db.lumen_share_transfers.find({
        "from_investor_id": investor_id, "asset_id": asset_id,
    }):
        outflow += float(t.get("amount_uah") or 0)
    return _round2(primary + inflow - outflow)


async def listed_units_uah(investor_id: str, asset_id: str) -> float:
    """How many UAH already locked in active/partial listings."""
    total = 0.0
    async for L in db.lumen_secondary_listings.find({
        "seller_id": investor_id, "asset_id": asset_id,
        "status": {"$in": ["active", "partially_filled", "draft"]},
    }):
        remaining = float(L.get("units_uah") or 0) - float(L.get("filled_units_uah") or 0)
        total += max(0.0, remaining)
    return _round2(total)


async def holdings_summary(investor_id: str) -> list[dict]:
    """Per-asset breakdown for the seller portfolio."""
    asset_ids = set()
    async for inv in db.lumen_investments.find(
            {"investor_id": investor_id, "status": "active"}, {"asset_id": 1}):
        asset_ids.add(inv["asset_id"])
    async for t in db.lumen_share_transfers.find(
            {"$or": [{"from_investor_id": investor_id},
                     {"to_investor_id": investor_id}]}, {"asset_id": 1}):
        asset_ids.add(t["asset_id"])
    out: list[dict] = []
    for aid in asset_ids:
        owned = await compute_ownership_uah(investor_id, aid)
        if owned <= 0:
            continue
        locked = await listed_units_uah(investor_id, aid)
        asset = await db.lumen_assets.find_one(
            {"id": aid}, {"title": 1, "category": 1, "yield_pct": 1})
        out.append({
            "asset_id": aid,
            "asset_title": (asset or {}).get("title"),
            "category": (asset or {}).get("category"),
            "yield_pct": (asset or {}).get("yield_pct"),
            "owned_uah": owned,
            "listed_uah": locked,
            "available_uah": _round2(owned - locked),
        })
    out.sort(key=lambda x: -x["available_uah"])
    return out


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _now_plus_days(n: int) -> datetime:
    return _now() + timedelta(days=n)


def _strip_listing(d: dict) -> dict:
    if not d: return d
    d = _strip_mongo(dict(d))
    for k in ("created_at", "updated_at", "expires_at", "filled_at",
              "cancelled_at"):
        if d.get(k):
            d[k] = _iso(d[k])
    return d


def _strip_trade(d: dict) -> dict:
    if not d: return d
    d = _strip_mongo(dict(d))
    for k in ("created_at", "settled_at", "cancelled_at"):
        if d.get(k):
            d[k] = _iso(d[k])
    return d


async def _wallet_settled_balance(investor_id: str) -> float:
    w = await db.lumen_wallets.find_one({"investor_id": investor_id})
    return float((w or {}).get("settled_balance") or 0)


# ----------------------------------------------------------------------------
# Settlement (the core of Sprint 13)
# ----------------------------------------------------------------------------

async def _settle_trade(trade: dict, *, actor: dict,
                          request: Optional[Request] = None) -> dict:
    """Atomic-ish settlement: ledger + transfer + listing close + wallets.

    We use mongo's insertion idempotency + status guards rather than a real
    transaction. The order is chosen so a mid-failure leaves the platform in
    a recoverable state and Sprint 10 consistency invariants surface any
    breach loudly.
    """
    tid = trade["id"]
    listing = await db.lumen_secondary_listings.find_one({"id": trade["listing_id"]})
    if not listing:
        raise HTTPException(status_code=404, detail="Listing зник")
    if listing["status"] not in ("active", "partially_filled"):
        raise HTTPException(status_code=409, detail=f"Listing у статусі {listing['status']}")

    units_uah   = _round2(trade["units_uah"])
    gross_uah   = _round2(trade["gross_uah"])
    fee_uah     = _round2(trade["fee_uah"])
    seller_net  = _round2(gross_uah - fee_uah)
    asset_id    = trade["asset_id"]
    buyer_id    = trade["buyer_id"]
    seller_id   = trade["seller_id"]

    # Verify buyer can still afford
    avail = await _wallet_settled_balance(buyer_id)
    if avail + 0.5 < gross_uah:
        await db.lumen_secondary_trades.update_one(
            {"id": tid},
            {"$set": {"status": "failed", "failure_reason": "Недостатньо коштів на гаманці",
                      "cancelled_at": _now()}},
        )
        raise HTTPException(status_code=402,
                            detail=f"Недостатньо коштів: потрібно {gross_uah:.2f}, доступно {avail:.2f}")

    # ── E1 fix — ATOMIC UNIT RESERVATION (oversell guard) ──
    # Concurrent buy-now requests previously each passed a stale `remaining`
    # check and then settled via a read-modify-write fill update → oversell.
    # We now reserve units with a single conditional $inc that only succeeds
    # if it cannot push filled_units_uah past units_uah. Losers get 409 and
    # never touch the ledger/ownership.
    from pymongo import ReturnDocument as _ReturnDoc
    reserved = await db.lumen_secondary_listings.find_one_and_update(
        {"id": listing["id"],
         "status": {"$in": ("active", "partially_filled")},
         "$expr": {"$lte": [
             {"$add": [{"$ifNull": ["$filled_units_uah", 0]}, units_uah]},
             {"$add": ["$units_uah", 0.5]}]}},
        {"$inc": {"filled_units_uah": units_uah}},
        return_document=_ReturnDoc.AFTER,
    )
    if not reserved:
        await db.lumen_secondary_trades.update_one(
            {"id": tid},
            {"$set": {"status": "failed",
                      "failure_reason": "Недостатньо вільних одиниць у лістингу (oversell guard)",
                      "cancelled_at": _now()}},
        )
        raise HTTPException(status_code=409,
                            detail="Недостатньо вільних одиниць у лістингу")

    # 1. Ledger entries (append-only; never undone)
    buyer_le = await _ledger_append(
        entry_type="debit", reason="secondary_purchase",
        investor_id=buyer_id, asset_id=asset_id, investment_id=None,
        payment_request_id=None, amount=gross_uah, currency=BASE_CURRENCY,
        fx_rate=1.0, amount_uah=gross_uah, actor_id=actor.get("id", "system"),
        notes=f"secondary trade {tid}",
    )
    seller_le = await _ledger_append(
        entry_type="credit", reason="secondary_sale",
        investor_id=seller_id, asset_id=asset_id, investment_id=None,
        payment_request_id=None, amount=seller_net, currency=BASE_CURRENCY,
        fx_rate=1.0, amount_uah=seller_net, actor_id=actor.get("id", "system"),
        notes=f"secondary trade {tid}",
    )
    fee_le = None
    if fee_uah > 0:
        fee_le = await _ledger_append(
            entry_type="credit", reason="platform_fee",
            investor_id=PLATFORM_REVENUE_ACCOUNT, asset_id=asset_id,
            investment_id=None, payment_request_id=None,
            amount=fee_uah, currency=BASE_CURRENCY, fx_rate=1.0,
            amount_uah=fee_uah, actor_id=actor.get("id", "system"),
            notes=f"platform fee for trade {tid}",
        )

    # 2. Append share_transfer (authoritative ownership change)
    transfer = {
        "id": f"st-{uuid.uuid4().hex[:12]}",
        "trade_id": tid,
        "asset_id": asset_id,
        "from_investor_id": seller_id,
        "to_investor_id":   buyer_id,
        "amount_uah":       units_uah,
        "settled_at":       _now(),
    }
    await db.lumen_share_transfers.insert_one(transfer)

    # 3. Update ownership rows
    new_seller_owned = await compute_ownership_uah(seller_id, asset_id)
    new_buyer_owned  = await compute_ownership_uah(buyer_id, asset_id)
    await db.lumen_ownerships.update_one(
        {"investor_id": seller_id, "asset_id": asset_id},
        {"$set": {"amount_uah": new_seller_owned, "amount": new_seller_owned,
                  "updated_at": _now()},
         "$setOnInsert": {"id": f"own-{uuid.uuid4().hex[:12]}",
                          "created_at": _now()}},
        upsert=True,
    )
    await db.lumen_ownerships.update_one(
        {"investor_id": buyer_id, "asset_id": asset_id},
        {"$set": {"amount_uah": new_buyer_owned, "amount": new_buyer_owned,
                  "updated_at": _now()},
         "$setOnInsert": {"id": f"own-{uuid.uuid4().hex[:12]}",
                          "created_at": _now()}},
        upsert=True,
    )

    # 4. Wallet recompute
    try:
        await recompute_wallet(buyer_id, BASE_CURRENCY)
        await recompute_wallet(seller_id, BASE_CURRENCY)
    except Exception:
        logger.exception("wallet recompute failed during settlement")

    # 5. Listing fill-tracking — units already reserved atomically above.
    #    The status transition is made monotonic + guarded so concurrent
    #    settlements can never downgrade a 'filled' listing back to
    #    'partially_filled' (last-writer race). Both updates key off the
    #    authoritative current filled_units_uah via $expr.
    await db.lumen_secondary_listings.update_one(
        {"id": listing["id"],
         "$expr": {"$gte": [{"$ifNull": ["$filled_units_uah", 0]},
                            {"$subtract": ["$units_uah", 0.5]}]}},
        {"$set": {"status": "filled", "filled_at": _now(), "updated_at": _now()}},
    )
    await db.lumen_secondary_listings.update_one(
        {"id": listing["id"], "status": "active",
         "$expr": {"$lt": [{"$ifNull": ["$filled_units_uah", 0]},
                           {"$subtract": ["$units_uah", 0.5]}]}},
        {"$set": {"status": "partially_filled", "updated_at": _now()}},
    )

    # 6. Mark trade settled
    await db.lumen_secondary_trades.update_one(
        {"id": tid},
        {"$set": {"status": "settled", "settled_at": _now(),
                  "ledger_entries": [le for le in [buyer_le, seller_le, fee_le] if le],
                  "transfer_id": transfer["id"],
                  "seller_net_uah": seller_net}},
    )

    # 6b. LUMEN 2.0 / A1 — sync integer Unit Registry + ownership events
    try:
        import lumen_unit_registry as _ur
        await _ur.on_trade_settled(asset_id, seller_id, buyer_id, units_uah, tid)
    except Exception:
        logger.exception("unit-registry hook failed during settlement (trade %s)", tid)

    # 6c. LUMEN 2.0 / A2 — burn & re-issue certificates (after registry sync)
    try:
        import lumen_certificates as _cert
        await _cert.on_trade_settled(asset_id, seller_id, buyer_id, tid)
    except Exception:
        logger.exception("certificate hook failed during settlement (trade %s)", tid)

    # 6d. LUMEN 2.0 / A3 — re-bind ownership ↔ certificate after burn & re-issue
    try:
        import lumen_ownership_lifecycle as _lc
        await _lc.bind_all()
    except Exception:
        logger.exception("lifecycle binding hook failed during settlement (trade %s)", tid)

    # 7. Audit
    await write_audit(
        action="secondary.trade_settled", category="payment",
        target_type="lumen_secondary_trades", target_id=tid,
        actor=actor, request=request,
        summary=(f"Trade {tid} settled: {fmt_uah_as_usd(units_uah, decimals=2)} @ price={trade['price_per_unit']}"
                 f" between {seller_id} → {buyer_id}, fee={fmt_uah_as_usd(fee_uah, decimals=2)}"),
        meta={"asset_id": asset_id, "gross_uah": gross_uah,
              "seller_net_uah": seller_net, "fee_uah": fee_uah,
              "buyer_le": buyer_le, "seller_le": seller_le, "fee_le": fee_le},
    )

    return await db.lumen_secondary_trades.find_one({"id": tid})


# ----------------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------------

class CreateListingPayload(BaseModel):
    asset_id: str
    units_uah: float = Field(..., gt=0)
    price_per_unit: float = Field(1.0, gt=0)  # 1.0 = par, 1.05 = premium 5%, 0.95 = discount
    expires_in_days: int = Field(LISTING_TTL_DAYS, ge=1, le=180)


class CreateBidPayload(BaseModel):
    listing_id: str
    units_uah: float = Field(..., gt=0)
    price_per_unit: Optional[float] = None  # if None ⇒ buy-now at listing price


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-secondary"])


@router.on_event("startup")
async def _secondary_startup():
    await ensure_indexes()


# ---- Investor: portfolio holdings + listings catalogue ---------------------

@router.get("/investor/secondary/holdings")
async def my_holdings(user=Depends(get_current_user)):
    return {
        "items": await holdings_summary(user["id"]),
        "platform_fee_pct": PLATFORM_FEE_PCT,
        "min_listing_uah": MIN_LISTING_UAH,
    }


@router.get("/secondary/listings")
async def public_listings(asset_id: Optional[str] = None,
                            limit: int = Query(100, ge=1, le=500)):
    q: dict[str, Any] = {"status": {"$in": ["active", "partially_filled"]}}
    if asset_id: q["asset_id"] = asset_id
    items: list[dict] = []
    async for L in db.lumen_secondary_listings.find(q).sort("created_at", -1).limit(limit):
        out = _strip_listing(L)
        a = await db.lumen_assets.find_one(
            {"id": L["asset_id"]},
            {"title": 1, "category": 1, "yield_pct": 1, "cover_url": 1})
        if a:
            out["asset"] = _strip_mongo(a)
        # Hide seller_id from public listing; expose only seller_label
        out["seller_label"] = f"Інвестор #{(L['seller_id'] or '')[-6:]}"
        out.pop("seller_id", None)
        items.append(out)
    return {"items": items, "platform_fee_pct": PLATFORM_FEE_PCT}


@router.get("/secondary/listings/{listing_id}")
async def listing_detail(listing_id: str):
    L = await db.lumen_secondary_listings.find_one({"id": listing_id})
    if not L:
        raise HTTPException(status_code=404, detail="Не знайдено")
    out = _strip_listing(L)
    a = await db.lumen_assets.find_one({"id": L["asset_id"]})
    if a:
        out["asset"] = _strip_mongo(a)
    bids: list[dict] = []
    async for b in db.lumen_secondary_bids.find({"listing_id": listing_id}).sort("created_at", -1):
        bids.append(_strip_listing(b))
    out["bids"] = bids
    out["seller_label"] = f"Інвестор #{(L['seller_id'] or '')[-6:]}"
    out["platform_fee_pct"] = PLATFORM_FEE_PCT
    return out


# ---- Investor: create / cancel listing -------------------------------------

@router.post("/investor/secondary/listings")
async def create_listing(payload: CreateListingPayload, request: Request,
                           user=Depends(get_current_user),
                           _perm=Depends(_lr2_perm("secondary_trade", "write"))):
    if payload.units_uah < MIN_LISTING_UAH:
        raise HTTPException(status_code=400,
                            detail=f"Мінімум для виставлення: {fmt_uah_as_usd(MIN_LISTING_UAH)}")
    avail = await compute_ownership_uah(user["id"], payload.asset_id)
    locked = await listed_units_uah(user["id"], payload.asset_id)
    free = avail - locked
    if free + 0.5 < payload.units_uah:
        raise HTTPException(status_code=400,
                            detail=f"Доступно для продажу: {fmt_uah_as_usd(free, decimals=2)}")
    if payload.price_per_unit <= 0 or payload.price_per_unit > 5:
        raise HTTPException(status_code=400, detail="Ціна за одиницю поза допустимими межами")
    L = {
        "id": f"sl-{uuid.uuid4().hex[:12]}",
        "seller_id": user["id"],
        "asset_id": payload.asset_id,
        "units_uah": _round2(payload.units_uah),
        "price_per_unit": float(payload.price_per_unit),
        "filled_units_uah": 0.0,
        "currency": BASE_CURRENCY,
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
        "expires_at": _now_plus_days(payload.expires_in_days),
    }
    await db.lumen_secondary_listings.insert_one(L)
    await write_audit(
        action="secondary.listing_create", category="asset",
        target_type="lumen_secondary_listings", target_id=L["id"],
        actor=user, request=request,
        summary=f"Listing created: {fmt_uah_as_usd(L['units_uah'], decimals=2)} of {payload.asset_id} @ {payload.price_per_unit}",
        meta={"asset_id": payload.asset_id, "units_uah": L["units_uah"],
              "price_per_unit": L["price_per_unit"]},
    )
    return _strip_listing(L)


@router.post("/investor/secondary/listings/{listing_id}/cancel")
async def cancel_listing(listing_id: str, request: Request,
                          user=Depends(get_current_user),
                          _perm=Depends(_lr2_perm("secondary_trade", "write"))):
    L = await db.lumen_secondary_listings.find_one({"id": listing_id})
    if not L:
        raise HTTPException(status_code=404, detail="Не знайдено")
    if L["seller_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Тільки автор може скасувати")
    if L["status"] in ("filled", "cancelled", "expired"):
        raise HTTPException(status_code=409, detail=f"Лістинг у статусі {L['status']}")
    await db.lumen_secondary_listings.update_one(
        {"id": listing_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now(),
                  "updated_at": _now()}},
    )
    await write_audit(
        action="secondary.listing_cancel", category="asset",
        target_type="lumen_secondary_listings", target_id=listing_id,
        actor=user, request=request,
        summary=f"Listing {listing_id} cancelled",
    )
    return {"ok": True}


# ---- Investor: buy-now or make-offer ---------------------------------------

@router.post("/investor/secondary/bids")
async def create_bid_or_buy(payload: CreateBidPayload, request: Request,
                              user=Depends(get_current_user),
                              _perm=Depends(_lr2_perm("secondary_trade", "write"))):
    L = await db.lumen_secondary_listings.find_one({"id": payload.listing_id})
    if not L:
        raise HTTPException(status_code=404, detail="Listing не знайдено")
    if L["status"] not in ("active", "partially_filled"):
        raise HTTPException(status_code=409, detail=f"Listing у статусі {L['status']}")
    if L["seller_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Не можна купити власний лістинг")
    remaining = _round2(float(L["units_uah"]) - float(L.get("filled_units_uah") or 0))
    if payload.units_uah > remaining + 0.5:
        raise HTTPException(status_code=400,
                            detail=f"Доступно для купівлі: {fmt_uah_as_usd(remaining, decimals=2)}")

    price = payload.price_per_unit if payload.price_per_unit is not None else float(L["price_per_unit"])
    if price <= 0 or price > 5:
        raise HTTPException(status_code=400, detail="Ціна поза межами")

    is_buy_now = (payload.price_per_unit is None
                  or abs(price - float(L["price_per_unit"])) < 0.0001)

    if is_buy_now:
        # Direct trade
        gross = _round2(payload.units_uah * price)
        fee = _round2(gross * PLATFORM_FEE_PCT)
        # affordability pre-check
        avail = await _wallet_settled_balance(user["id"])
        if avail + 0.5 < gross:
            raise HTTPException(
                status_code=402,
                detail=(f"Недостатньо коштів на гаманці: потрібно "
                        f"{fmt_uah_as_usd(gross, decimals=2)}, доступно {fmt_uah_as_usd(avail, decimals=2)}"),
            )
        trade = {
            "id": f"tr-{uuid.uuid4().hex[:12]}",
            "listing_id": L["id"],
            "bid_id": None,
            "seller_id": L["seller_id"],
            "buyer_id": user["id"],
            "asset_id": L["asset_id"],
            "units_uah": _round2(payload.units_uah),
            "price_per_unit": price,
            "gross_uah": gross,
            "fee_uah": fee,
            "seller_net_uah": _round2(gross - fee),
            "currency": BASE_CURRENCY,
            "status": "pending",
            "created_at": _now(),
        }
        await db.lumen_secondary_trades.insert_one(trade)
        await write_audit(
            action="secondary.buy_now", category="payment",
            target_type="lumen_secondary_trades", target_id=trade["id"],
            actor=user, request=request,
            summary=f"Buy-now trade created: {fmt_uah_as_usd(gross, decimals=2)} on listing {L['id']}",
        )
        settled = await _settle_trade(trade, actor=user, request=request)
        return {"trade": _strip_trade(settled), "mode": "buy_now"}

    # Otherwise: place an offer bid for seller to accept/reject
    if price >= float(L["price_per_unit"]):
        raise HTTPException(status_code=400,
                            detail="Оффер має бути нижчим за ціну лістингу")
    bid = {
        "id": f"sb-{uuid.uuid4().hex[:12]}",
        "listing_id": L["id"],
        "buyer_id": user["id"],
        "units_uah": _round2(payload.units_uah),
        "price_per_unit": price,
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.lumen_secondary_bids.insert_one(bid)
    await write_audit(
        action="secondary.bid_create", category="asset",
        target_type="lumen_secondary_bids", target_id=bid["id"],
        actor=user, request=request,
        summary=f"Bid placed: {fmt_uah_as_usd(bid['units_uah'], decimals=2)} @ {price} on listing {L['id']}",
    )
    return {"bid": _strip_listing(bid), "mode": "offer"}


@router.post("/investor/secondary/bids/{bid_id}/cancel")
async def cancel_bid(bid_id: str, request: Request, user=Depends(get_current_user),
                      _perm=Depends(_lr2_perm("secondary_trade", "write"))):
    b = await db.lumen_secondary_bids.find_one({"id": bid_id})
    if not b:
        raise HTTPException(status_code=404, detail="Не знайдено")
    if b["buyer_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Лише автор може скасувати")
    if b["status"] != "active":
        raise HTTPException(status_code=409, detail=f"Bid у статусі {b['status']}")
    await db.lumen_secondary_bids.update_one(
        {"id": bid_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}},
    )
    await write_audit(
        action="secondary.bid_cancel", category="asset",
        target_type="lumen_secondary_bids", target_id=bid_id,
        actor=user, request=request,
        summary=f"Bid {bid_id} cancelled by buyer",
    )
    return {"ok": True}


@router.post("/investor/secondary/bids/{bid_id}/accept")
async def accept_bid(bid_id: str, request: Request,
                      user=Depends(get_current_user),
                      _perm=Depends(_lr2_perm("secondary_trade", "approve"))):
    b = await db.lumen_secondary_bids.find_one({"id": bid_id})
    if not b:
        raise HTTPException(status_code=404, detail="Не знайдено")
    L = await db.lumen_secondary_listings.find_one({"id": b["listing_id"]})
    if not L or L["seller_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Лише продавець може прийняти")
    if b["status"] != "active":
        raise HTTPException(status_code=409, detail=f"Bid у статусі {b['status']}")
    if L["status"] not in ("active", "partially_filled"):
        raise HTTPException(status_code=409, detail=f"Listing у статусі {L['status']}")
    remaining = _round2(float(L["units_uah"]) - float(L.get("filled_units_uah") or 0))
    units = min(_round2(b["units_uah"]), remaining)
    if units < MIN_LISTING_UAH and units < remaining:
        units = remaining  # finish off micro-leftovers
    price = float(b["price_per_unit"])
    gross = _round2(units * price)
    fee = _round2(gross * PLATFORM_FEE_PCT)
    trade = {
        "id": f"tr-{uuid.uuid4().hex[:12]}",
        "listing_id": L["id"], "bid_id": b["id"],
        "seller_id": L["seller_id"], "buyer_id": b["buyer_id"],
        "asset_id": L["asset_id"],
        "units_uah": units, "price_per_unit": price,
        "gross_uah": gross, "fee_uah": fee,
        "seller_net_uah": _round2(gross - fee),
        "currency": BASE_CURRENCY,
        "status": "pending", "created_at": _now(),
    }
    await db.lumen_secondary_trades.insert_one(trade)
    await db.lumen_secondary_bids.update_one(
        {"id": bid_id}, {"$set": {"status": "accepted", "updated_at": _now()}},
    )
    await write_audit(
        action="secondary.bid_accept", category="payment",
        target_type="lumen_secondary_bids", target_id=bid_id,
        actor=user, request=request,
        summary=f"Bid {bid_id} accepted, trade {trade['id']} created ({fmt_uah_as_usd(gross, decimals=2)})",
    )
    settled = await _settle_trade(trade, actor=user, request=request)
    return {"trade": _strip_trade(settled)}


@router.post("/investor/secondary/bids/{bid_id}/reject")
async def reject_bid(bid_id: str, request: Request,
                      user=Depends(get_current_user),
                      _perm=Depends(_lr2_perm("secondary_trade", "write"))):
    b = await db.lumen_secondary_bids.find_one({"id": bid_id})
    if not b:
        raise HTTPException(status_code=404, detail="Не знайдено")
    L = await db.lumen_secondary_listings.find_one({"id": b["listing_id"]})
    if not L or L["seller_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Лише продавець може відхилити")
    await db.lumen_secondary_bids.update_one(
        {"id": bid_id},
        {"$set": {"status": "rejected", "updated_at": _now()}},
    )
    await write_audit(
        action="secondary.bid_reject", category="asset",
        target_type="lumen_secondary_bids", target_id=bid_id,
        actor=user, request=request,
        summary=f"Bid {bid_id} rejected by seller",
    )
    return {"ok": True}


# ---- Investor: my listings / bids / trades ---------------------------------

@router.get("/investor/secondary/my-listings")
async def my_listings(user=Depends(get_current_user)):
    items: list[dict] = []
    async for L in db.lumen_secondary_listings.find(
            {"seller_id": user["id"]}).sort("created_at", -1):
        out = _strip_listing(L)
        a = await db.lumen_assets.find_one({"id": L["asset_id"]}, {"title": 1})
        if a: out["asset_title"] = a.get("title")
        bid_count = await db.lumen_secondary_bids.count_documents(
            {"listing_id": L["id"], "status": "active"})
        out["active_bids"] = bid_count
        items.append(out)
    return {"items": items}


@router.get("/investor/secondary/my-bids")
async def my_bids(user=Depends(get_current_user)):
    items: list[dict] = []
    async for b in db.lumen_secondary_bids.find(
            {"buyer_id": user["id"]}).sort("created_at", -1):
        out = _strip_listing(b)
        L = await db.lumen_secondary_listings.find_one(
            {"id": b["listing_id"]}, {"asset_id": 1, "price_per_unit": 1})
        out["listing_asset_id"] = (L or {}).get("asset_id")
        out["listing_price_per_unit"] = (L or {}).get("price_per_unit")
        items.append(out)
    return {"items": items}


@router.get("/investor/secondary/my-trades")
async def my_trades(user=Depends(get_current_user)):
    items: list[dict] = []
    async for t in db.lumen_secondary_trades.find(
            {"$or": [{"buyer_id": user["id"]}, {"seller_id": user["id"]}]}
        ).sort("created_at", -1):
        out = _strip_trade(t)
        out["role"] = "buyer" if t["buyer_id"] == user["id"] else "seller"
        a = await db.lumen_assets.find_one({"id": t["asset_id"]}, {"title": 1})
        if a: out["asset_title"] = a.get("title")
        items.append(out)
    return {"items": items}


# ---- Admin: oversight + platform revenue -----------------------------------

@router.get("/admin/secondary/overview")
async def admin_overview(_=Depends(require_admin)):
    counts = {"listings": {}, "bids": {}, "trades": {}}
    for s in LISTING_STATUSES:
        counts["listings"][s] = await db.lumen_secondary_listings.count_documents({"status": s})
    for s in BID_STATUSES:
        counts["bids"][s] = await db.lumen_secondary_bids.count_documents({"status": s})
    for s in TRADE_STATUSES:
        counts["trades"][s] = await db.lumen_secondary_trades.count_documents({"status": s})

    # Platform revenue (Σ fee_uah ledger credits to PLATFORM_REVENUE_ACCOUNT)
    revenue = 0.0
    async for e in db.lumen_ledger_entries.find({
        "investor_id": PLATFORM_REVENUE_ACCOUNT, "reason": "platform_fee",
        "entry_type": "credit",
    }):
        revenue += float(e.get("amount_uah") or 0)

    settled_volume = 0.0
    async for t in db.lumen_secondary_trades.find({"status": "settled"}):
        settled_volume += float(t.get("gross_uah") or 0)

    recent: list[dict] = []
    async for t in db.lumen_secondary_trades.find({"status": "settled"}
        ).sort("settled_at", -1).limit(10):
        out = _strip_trade(t)
        a = await db.lumen_assets.find_one({"id": t["asset_id"]}, {"title": 1})
        if a: out["asset_title"] = a.get("title")
        recent.append(out)

    return {
        "counts": counts,
        "platform_fee_pct": PLATFORM_FEE_PCT,
        "platform_revenue_uah": _round2(revenue),
        "settled_volume_uah": _round2(settled_volume),
        "recent_trades": recent,
    }


@router.get("/admin/secondary/listings")
async def admin_list_listings(status: Optional[str] = None,
                                _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status: q["status"] = status
    items = []
    async for L in db.lumen_secondary_listings.find(q).sort("created_at", -1).limit(200):
        out = _strip_listing(L)
        a = await db.lumen_assets.find_one({"id": L["asset_id"]}, {"title": 1})
        if a: out["asset_title"] = a.get("title")
        items.append(out)
    return {"items": items}


@router.get("/admin/secondary/trades")
async def admin_list_trades(_=Depends(require_admin)):
    items = []
    async for t in db.lumen_secondary_trades.find({}).sort("created_at", -1).limit(200):
        out = _strip_trade(t)
        a = await db.lumen_assets.find_one({"id": t["asset_id"]}, {"title": 1})
        if a: out["asset_title"] = a.get("title")
        items.append(out)
    return {"items": items}


# ----------------------------------------------------------------------------
# Demo seed (idempotent) — 1-2 active listings for the marketplace витрина/UI
# ----------------------------------------------------------------------------
#
# We must NOT create a parallel share registry. So instead of inventing units
# for a fresh seller, we move part of an existing owner's holding to a dedicated
# demo seller through the SAME share_transfer mechanism settlement uses (no
# money, no trade — a one-off registry rebalance). All consistency invariants
# stay green:
#   I1  Σ ownership rows per asset == Σ active investments        (unchanged)
#   I13 ownership(investor) == primary − outbound + inbound       (recomputed)
#   I2  raised_amount == Σ active investments                     (untouched)
# The demo seller is a SEPARATE investor so the primary demo login
# (client@atlas.dev) can browse AND buy these listings.

DEMO_SELLER_EMAIL = "marketplace.demo@lumen.test"


async def _sync_ownership_row(investor_id: str, asset_id: str) -> float:
    owned = await compute_ownership_uah(investor_id, asset_id)
    await db.lumen_ownerships.update_one(
        {"investor_id": investor_id, "asset_id": asset_id},
        {"$set": {"amount_uah": owned, "amount": owned, "units": owned,
                  "updated_at": _now()},
         "$setOnInsert": {"id": f"own-{uuid.uuid4().hex[:12]}",
                          "created_at": _now()}},
        upsert=True,
    )
    return owned


async def seed_secondary_demo() -> dict:
    """Create 1-2 active demo listings if the secondary market is empty."""
    existing = await db.lumen_secondary_listings.count_documents(
        {"status": {"$in": ["active", "partially_filled"]}})
    if existing > 0:
        return {"skipped": "active listings already exist", "active": existing}

    # Source owner with real holdings (the primary demo investor).
    src = (await db.users.find_one({"email": "client@atlas.dev"})
           or await db.lumen_ownerships.find_one({}))
    if not src:
        return {"skipped": "no source owner found"}
    src_id = src.get("user_id") or src.get("investor_id")
    if not src_id:
        return {"skipped": "source owner has no id"}

    # Ensure a dedicated demo seller investor.
    seller = await db.users.find_one({"email": DEMO_SELLER_EMAIL})
    if seller:
        seller_id = seller.get("user_id") or seller.get("id")
    else:
        seller_id = f"user_mktdemo_{uuid.uuid4().hex[:10]}"
        await db.users.insert_one({
            "user_id": seller_id, "id": seller_id, "email": DEMO_SELLER_EMAIL,
            "name": "Демо-продавець", "role": "client", "roles": ["client"],
            "active_role": "client", "states": ["client"],
            "password_hash": None, "created_at": _iso(_now()),
        })

    plan = [
        {"asset_id": "asset-lavr-tc",   "move": 200000, "list": 120000,
         "price": 1.03, "days": 30},
        {"asset_id": "asset-podilskyi", "move": 150000, "list": 90000,
         "price": 0.97, "days": 30},
    ]
    created = 0
    for p in plan:
        src_owned = await compute_ownership_uah(src_id, p["asset_id"])
        if src_owned + 0.5 < p["move"]:
            continue  # source doesn't own enough — skip this one
        # 1) registry rebalance src → demo seller (seed transfer)
        await db.lumen_share_transfers.insert_one({
            "id": f"st-seed-{uuid.uuid4().hex[:10]}",
            "trade_id": None, "is_seed": True,
            "asset_id": p["asset_id"],
            "from_investor_id": src_id, "to_investor_id": seller_id,
            "amount_uah": float(p["move"]), "settled_at": _now(),
        })
        # 2) recompute both ownership rows to keep I1/I13 green
        await _sync_ownership_row(src_id, p["asset_id"])
        await _sync_ownership_row(seller_id, p["asset_id"])
        # 3) demo seller lists part of the acquired holding
        await db.lumen_secondary_listings.insert_one({
            "id": f"sl-demo-{uuid.uuid4().hex[:10]}",
            "seller_id": seller_id, "asset_id": p["asset_id"],
            "units_uah": float(p["list"]), "price_per_unit": float(p["price"]),
            "filled_units_uah": 0.0, "currency": BASE_CURRENCY,
            "status": "active", "is_seed": True,
            "created_at": _now(), "updated_at": _now(),
            "expires_at": _now_plus_days(p["days"]),
        })
        created += 1

    return {"created_listings": created, "demo_seller_id": seller_id}


__all__ = [
    "router",
    "compute_ownership_uah", "listed_units_uah", "holdings_summary",
    "PLATFORM_FEE_PCT", "PLATFORM_REVENUE_ACCOUNT", "MIN_LISTING_UAH",
    "seed_secondary_demo",
]
