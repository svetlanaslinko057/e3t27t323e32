"""
LUMEN — OTC Lite  ·  H2.8
=========================

Peer-to-peer secondary transfer of NFT ownership certificates, with **LUMEN as
guarantor/escrow** (manual settlement). This is intentionally NOT an exchange:
no order book, no matching engine, no AMM. Just the business mechanic that was
missing on top of the existing ownership layer (H2.3–H2.7):

    "I want to SELL my NFT"  →  "I want to BUY"  →  Deal  →  Payment (off-platform,
    confirmed by a manager)  →  NFT transfer  →  dividend recipient changes.

Architectural rules (fixed, reuse the existing layer — do NOT duplicate it):
    * Ownership truth         = lumen_nft_certificates.current_holder_user_id
    * Holder change           = lumen_crypto_os.otc_transfer_holder() (writes the
                                same lumen_nft_transfers audit row, source=otc)
    * Dividend recipient      = CURRENT NFT holder at distribution snapshot
                                (lumen_pool_os.distribute_revenue already snapshots
                                 holders → future dividends auto-route to the buyer;
                                 past distributions stay immutable).
    * Accounting truth (money)= Pool OS (LUMEN). The chain only moves USDT+NFT.

Collections
    lumen_otc_listings        a seller's NFT offered at a price
    lumen_otc_offers          a buyer's counter-price on a listing
    lumen_otc_deals           an accepted/bought transaction in settlement
    lumen_otc_payment_proofs  buyer-submitted proof (bank ref / usdt tx hash)

Settlement methods are pluggable from day one (manual now, escrow/smart_contract
later) without a DB migration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, require_staff, get_current_user as require_user
from lumen_crypto_os import (
    NFTS,
    otc_transfer_holder,
    primary_wallet,
    freeze_nft,
    unfreeze_nft,
    NFT_MINTED,
    NFT_TRANSFERRED,
)

logger = logging.getLogger("lumen.otc")
router = APIRouter(prefix="/api", tags=["lumen-otc"])

LISTINGS = "lumen_otc_listings"
OFFERS = "lumen_otc_offers"
DEALS = "lumen_otc_deals"
PROOFS = "lumen_otc_payment_proofs"

# ── Listing lifecycle ──────────────────────────────────────────────────────
LISTING_DRAFT = "draft"
LISTING_ACTIVE = "active"
LISTING_RESERVED = "reserved"
LISTING_PAYMENT_PENDING = "payment_pending"
LISTING_PAYMENT_CONFIRMED = "payment_confirmed"
LISTING_NFT_TRANSFER_PENDING = "nft_transfer_pending"
LISTING_COMPLETED = "completed"
LISTING_CANCELLED = "cancelled"
LISTING_DISPUTED = "disputed"
# A listing occupying its NFT (cannot create another listing for the same NFT).
LISTING_OPEN_STATES = {
    LISTING_DRAFT, LISTING_ACTIVE, LISTING_RESERVED, LISTING_PAYMENT_PENDING,
    LISTING_PAYMENT_CONFIRMED, LISTING_NFT_TRANSFER_PENDING,
}

# ── Offer lifecycle ────────────────────────────────────────────────────────
OFFER_PENDING = "pending"
OFFER_ACCEPTED = "accepted"
OFFER_REJECTED = "rejected"
OFFER_EXPIRED = "expired"
OFFER_CANCELLED = "cancelled"

# ── Deal lifecycle ─────────────────────────────────────────────────────────
DEAL_PAYMENT_PENDING = "payment_pending"
DEAL_PAYMENT_CONFIRMED = "payment_confirmed"
DEAL_NFT_TRANSFER_PENDING = "nft_transfer_pending"
DEAL_COMPLETED = "completed"
DEAL_CANCELLED = "cancelled"
DEAL_DISPUTED = "disputed"
DEAL_TERMINAL = {DEAL_COMPLETED, DEAL_CANCELLED, DEAL_DISPUTED}

PAY_PENDING = "pending"
PAY_SUBMITTED = "submitted"
PAY_CONFIRMED = "confirmed"
PAY_REJECTED = "rejected"

PAYMENT_METHODS = {"bank_transfer", "usdt_manual", "internal_balance", "manual"}


# ═══════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════
def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def ser(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def r2(x: Any) -> float:
    return round(float(x or 0), 2)


def _uid(user: dict) -> str:
    return user.get("id") or user.get("user_id")


def _kyc_ok(user: dict) -> bool:
    return (user.get("kyc_status") or "").lower() == "approved"


async def _get_nft(nft_id: str) -> dict:
    nft = await db[NFTS].find_one({"id": nft_id})
    if not nft:
        raise HTTPException(404, "NFT certificate not found")
    return nft


async def _active_listing_for_nft(nft_id: str, exclude_id: Optional[str] = None) -> Optional[dict]:
    q: Dict[str, Any] = {"nft_certificate_id": nft_id, "status": {"$in": list(LISTING_OPEN_STATES)}}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return await db[LISTINGS].find_one(q)


async def _enrich_listing(listing: dict) -> dict:
    out = ser(listing)
    nft = await db[NFTS].find_one({"id": listing.get("nft_certificate_id")})
    asset_id = listing.get("asset_id") or (nft or {}).get("asset_id")
    if nft:
        out["nft"] = {
            "id": nft["id"],
            "pool_id": nft.get("pool_id"),
            "asset_id": nft.get("asset_id"),
            "token_id": nft.get("token_id"),
            "units": nft.get("units"),
            "ownership_percent": nft.get("ownership_percent"),
            "status": nft.get("status"),
            "frozen": bool(nft.get("frozen")),
            "current_holder_user_id": nft.get("current_holder_user_id"),
        }
    # Share-framing: the buyer purchases a STAKE IN AN ASSET, not "an NFT".
    if asset_id:
        a = await db["lumen_assets"].find_one({"id": asset_id})
        if a:
            out["asset"] = {
                "id": a.get("id"),
                "title": a.get("title"),
                "category": a.get("category"),
                "location": a.get("location"),
                "cover_url": a.get("cover_url"),
                "target_yield": a.get("target_yield"),
                "description": a.get("description"),
            }
            out["metrics"] = _share_metrics(nft or {}, a, out.get("price_usd"))
    return out


def _share_metrics(nft: dict, asset: dict, price) -> dict:
    """Compute the investor-facing economics of a share for OTC cards / lot page.

    Derived transparently from the asset's target yield and the seller's invested
    amount — so a buyer sees real income, ROI and payback at the asking price.
    """
    invested = float(nft.get("invested_usd") or 0)
    pct = float(nft.get("ownership_percent") or 0)
    yld = float(asset.get("target_yield") or 0)
    price = float(price or 0)
    annual_div = round(invested * yld / 100.0, 2)
    dividends_12m = annual_div
    roi_at_ask = round((dividends_12m / price) * 100.0, 1) if price else None
    payback_years = round(price / dividends_12m, 1) if dividends_12m else None
    appreciation = round((price - invested) / invested * 100.0, 1) if invested else None
    return {
        "share_percent": pct,
        "invested_usd": invested,
        "annual_yield": yld,
        "dividends_12m": dividends_12m,
        "roi_at_ask": roi_at_ask,
        "payback_years": payback_years,
        "appreciation_pct": appreciation,
        "monthly_income": round(annual_div / 12.0, 2),
    }


def _payout_schedule(metrics: dict, months: int = 12) -> list:
    """A 12-point monthly income schedule derived from the yield — used for the
    'історія виплат' chart on the lot detail page (projection, clearly derived)."""
    from datetime import timedelta
    monthly = float(metrics.get("monthly_income") or 0)
    base = now()
    out = []
    for i in range(months, 0, -1):
        d = base - timedelta(days=30 * i)
        out.append({"month": d.strftime("%Y-%m"), "amount": round(monthly, 2)})
    return out


@router.get("/investor/otc/listings/{listing_id}")
async def get_listing(listing_id: str, user=Depends(require_user)):
    """Single OTC lot — full detail page (asset, economics, payout history)."""
    listing = await db[LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    e = await _enrich_listing(listing)
    e["is_mine"] = (listing.get("seller_user_id") == _uid(user))
    e["payout_history"] = _payout_schedule(e.get("metrics") or {})
    return {"listing": e}


# ── Guards (the fixed OTC safety rules) ────────────────────────────────────
async def assert_can_create_listing(nft: dict, user: dict) -> None:
    uid = _uid(user)
    if nft.get("current_holder_user_id") != uid:
        raise HTTPException(403, "You are not the current holder of this NFT")
    if nft.get("frozen"):
        raise HTTPException(409, "NFT is frozen (under dispute or recovery) and cannot be listed")
    if nft.get("status") not in (NFT_MINTED, NFT_TRANSFERRED):
        raise HTTPException(409, f"NFT not transferable in status '{nft.get('status')}'")
    if await _active_listing_for_nft(nft["id"]):
        raise HTTPException(409, "An active listing already exists for this NFT")


async def assert_can_buy(listing: dict, buyer: dict) -> None:
    if listing.get("status") != LISTING_ACTIVE:
        raise HTTPException(409, "Listing is not available")
    if listing.get("seller_user_id") == _uid(buyer):
        raise HTTPException(409, "You cannot buy your own listing")
    if not _kyc_ok(buyer):
        raise HTTPException(403, "KYC must be approved to buy")


# ═══════════════════════════════════════════════════════════════════════════
# Listings  (investor)
# ═══════════════════════════════════════════════════════════════════════════
class CreateListingRequest(BaseModel):
    nft_certificate_id: str
    price_usd: float
    currency: str = "USD"


@router.post("/investor/otc/listings")
async def create_listing(body: CreateListingRequest, user=Depends(require_user)):
    if body.price_usd is None or body.price_usd <= 0:
        raise HTTPException(400, "price_usd must be > 0")
    nft = await _get_nft(body.nft_certificate_id)
    await assert_can_create_listing(nft, user)
    listing = {
        "id": new_id("otcl"),
        "seller_user_id": _uid(user),
        "pool_id": nft.get("pool_id"),
        "asset_id": nft.get("asset_id"),
        "nft_certificate_id": nft["id"],
        "token_id": nft.get("token_id"),
        "units": int(nft.get("units") or 0),
        "ownership_percent": nft.get("ownership_percent"),
        "price_usd": r2(body.price_usd),
        "currency": (body.currency or "USD").upper(),
        "status": LISTING_ACTIVE,
        "active_deal_id": None,
        "created_at": now(),
        "updated_at": now(),
        "expires_at": None,
    }
    await db[LISTINGS].insert_one(dict(listing))
    logger.info("OTC listing %s created by %s for NFT %s @ %.2f",
                listing["id"], listing["seller_user_id"], nft["id"], listing["price_usd"])
    return {"ok": True, "listing": await _enrich_listing(listing)}


@router.get("/investor/otc/listings")
async def market_listings(user=Depends(require_user)):
    """Public OTC market — all ACTIVE listings (incl. the caller's own, flagged)."""
    rows = await db[LISTINGS].find({"status": LISTING_ACTIVE}).sort("created_at", -1).to_list(500)
    uid = _uid(user)
    out = []
    for r in rows:
        e = await _enrich_listing(r)
        e["is_mine"] = (r.get("seller_user_id") == uid)
        out.append(e)
    return {"listings": out}


@router.get("/investor/otc/my-listings")
async def my_listings(user=Depends(require_user)):
    rows = await db[LISTINGS].find({"seller_user_id": _uid(user)}).sort("created_at", -1).to_list(500)
    return {"listings": [await _enrich_listing(r) for r in rows]}


@router.get("/investor/web3/portfolio")
async def my_share_portfolio(user=Depends(require_user)):
    """Asset-first portfolio for the 'Мої активи' screen — the investor's shares
    in REAL assets (photo, city, yield, income), NFT kept as technical detail."""
    uid = _uid(user)
    nfts = await db[NFTS].find(
        {"current_holder_user_id": uid, "active": True}).sort("created_at", -1).to_list(1000)
    items = []
    totals = {"invested": 0.0, "dividends_12m": 0.0, "count": 0}
    for n in nfts:
        a = await db["lumen_assets"].find_one({"id": n.get("asset_id")}) if n.get("asset_id") else None
        # Skip harness/test artifacts that have no real asset record behind them.
        if not a:
            continue
        invested = float(n.get("invested_usd") or 0)
        metrics = _share_metrics(n, a, invested)
        # is this share currently listed on the market?
        active_listing = await db[LISTINGS].find_one(
            {"nft_certificate_id": n["id"], "status": LISTING_ACTIVE})
        items.append({
            "nft_id": n["id"],
            "token_id": n.get("token_id"),
            "pool_id": n.get("pool_id"),
            "asset_id": n.get("asset_id"),
            "status": n.get("status"),
            "frozen": bool(n.get("frozen")),
            "current_wallet": n.get("current_wallet"),
            "ownership_percent": n.get("ownership_percent"),
            "units": n.get("units"),
            "listed": bool(active_listing),
            "listing_id": active_listing["id"] if active_listing else None,
            "asset": ({
                "id": a.get("id"), "title": a.get("title"), "category": a.get("category"),
                "location": a.get("location"), "cover_url": a.get("cover_url"),
                "target_yield": a.get("target_yield"), "description": a.get("description"),
            } if a else None),
            "metrics": metrics,
        })
        totals["invested"] += invested
        totals["dividends_12m"] += float(metrics.get("dividends_12m") or 0)
        totals["count"] += 1
    totals["roi"] = round((totals["dividends_12m"] / totals["invested"]) * 100, 1) if totals["invested"] else 0
    totals["invested"] = round(totals["invested"], 2)
    totals["dividends_12m"] = round(totals["dividends_12m"], 2)
    return {"items": items, "totals": totals}


@router.delete("/investor/otc/listings/{listing_id}")
async def cancel_listing(listing_id: str, user=Depends(require_user)):
    listing = await db[LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing["seller_user_id"] != _uid(user):
        raise HTTPException(403, "Not your listing")
    if listing["status"] not in (LISTING_DRAFT, LISTING_ACTIVE):
        raise HTTPException(409, "Listing has a deal in progress and cannot be cancelled")
    await db[LISTINGS].update_one({"id": listing_id}, {"$set": {
        "status": LISTING_CANCELLED, "updated_at": now()}})
    # expire any pending offers
    await db[OFFERS].update_many(
        {"listing_id": listing_id, "status": OFFER_PENDING},
        {"$set": {"status": OFFER_EXPIRED, "updated_at": now()}})
    return {"ok": True}


# ── Deal creation (shared by buy + accept-offer) ───────────────────────────
async def _create_deal(listing: dict, buyer_user_id: str, price: float,
                        *, offer_id: Optional[str] = None,
                        payment_method: str = "bank_transfer") -> dict:
    # Atomically claim the listing to prevent double-sell.
    claim = await db[LISTINGS].update_one(
        {"id": listing["id"], "status": LISTING_ACTIVE},
        {"$set": {"status": LISTING_RESERVED, "updated_at": now()}})
    if claim.modified_count != 1:
        raise HTTPException(409, "Listing is no longer available")
    deal = {
        "id": new_id("otcd"),
        "listing_id": listing["id"],
        "offer_id": offer_id,
        "seller_user_id": listing["seller_user_id"],
        "buyer_user_id": buyer_user_id,
        "nft_certificate_id": listing["nft_certificate_id"],
        "pool_id": listing.get("pool_id"),
        "asset_id": listing.get("asset_id"),
        "token_id": listing.get("token_id"),
        "units": listing.get("units"),
        "price_usd": r2(price),
        "currency": listing.get("currency", "USD"),
        "payment_method": payment_method if payment_method in PAYMENT_METHODS else "manual",
        "payment_reference": f"LUMEN-OTC-{uuid4().hex[:8].upper()}",
        "payment_status": PAY_PENDING,
        "nft_status": "pending",
        "status": DEAL_PAYMENT_PENDING,
        "created_at": now(),
        "updated_at": now(),
        "completed_at": None,
    }
    await db[DEALS].insert_one(dict(deal))
    await db[LISTINGS].update_one({"id": listing["id"]}, {"$set": {
        "active_deal_id": deal["id"], "updated_at": now()}})
    logger.info("OTC deal %s created (listing %s, buyer %s, price %.2f)",
                deal["id"], listing["id"], buyer_user_id, deal["price_usd"])
    return deal


class BuyRequest(BaseModel):
    payment_method: str = "bank_transfer"


@router.post("/investor/otc/listings/{listing_id}/buy")
async def buy_listing(listing_id: str, body: BuyRequest = BuyRequest(), user=Depends(require_user)):
    listing = await db[LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    await assert_can_buy(listing, user)
    deal = await _create_deal(listing, _uid(user), listing["price_usd"],
                              payment_method=body.payment_method)
    return {"ok": True, "deal": ser(deal),
            "payment_instructions": _payment_instructions(deal)}


class OfferRequest(BaseModel):
    offer_price_usd: float
    payment_method: str = "bank_transfer"


@router.post("/investor/otc/listings/{listing_id}/offer")
async def make_offer(listing_id: str, body: OfferRequest, user=Depends(require_user)):
    if body.offer_price_usd is None or body.offer_price_usd <= 0:
        raise HTTPException(400, "offer_price_usd must be > 0")
    listing = await db[LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing["status"] != LISTING_ACTIVE:
        raise HTTPException(409, "Listing is not open to offers")
    if listing["seller_user_id"] == _uid(user):
        raise HTTPException(409, "You cannot make an offer on your own listing")
    if not _kyc_ok(user):
        raise HTTPException(403, "KYC must be approved to make an offer")
    offer = {
        "id": new_id("otco"),
        "listing_id": listing_id,
        "nft_certificate_id": listing["nft_certificate_id"],
        "buyer_user_id": _uid(user),
        "seller_user_id": listing["seller_user_id"],
        "offer_price_usd": r2(body.offer_price_usd),
        "currency": listing.get("currency", "USD"),
        "payment_method": body.payment_method,
        "status": OFFER_PENDING,
        "created_at": now(),
        "updated_at": now(),
    }
    await db[OFFERS].insert_one(dict(offer))
    return {"ok": True, "offer": ser(offer)}


@router.get("/investor/otc/listings/{listing_id}/offers")
async def listing_offers(listing_id: str, user=Depends(require_user)):
    listing = await db[LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing["seller_user_id"] != _uid(user):
        raise HTTPException(403, "Only the seller can view offers")
    rows = await db[OFFERS].find({"listing_id": listing_id}).sort("created_at", -1).to_list(200)
    return {"offers": [ser(o) for o in rows]}


@router.get("/investor/otc/my-offers")
async def my_offers(user=Depends(require_user)):
    rows = await db[OFFERS].find({"buyer_user_id": _uid(user)}).sort("created_at", -1).to_list(200)
    return {"offers": [ser(o) for o in rows]}


@router.post("/investor/otc/offers/{offer_id}/accept")
async def accept_offer(offer_id: str, user=Depends(require_user)):
    offer = await db[OFFERS].find_one({"id": offer_id})
    if not offer:
        raise HTTPException(404, "Offer not found")
    if offer["seller_user_id"] != _uid(user):
        raise HTTPException(403, "Only the seller can accept this offer")
    if offer["status"] != OFFER_PENDING:
        raise HTTPException(409, "Offer is not pending")
    listing = await db[LISTINGS].find_one({"id": offer["listing_id"]})
    if not listing or listing["status"] != LISTING_ACTIVE:
        raise HTTPException(409, "Listing is no longer available")
    deal = await _create_deal(listing, offer["buyer_user_id"], offer["offer_price_usd"],
                              offer_id=offer_id,
                              payment_method=offer.get("payment_method", "bank_transfer"))
    await db[OFFERS].update_one({"id": offer_id}, {"$set": {
        "status": OFFER_ACCEPTED, "updated_at": now()}})
    # auto-expire other pending offers on the same listing
    await db[OFFERS].update_many(
        {"listing_id": offer["listing_id"], "status": OFFER_PENDING, "id": {"$ne": offer_id}},
        {"$set": {"status": OFFER_EXPIRED, "updated_at": now()}})
    return {"ok": True, "deal": ser(deal)}


@router.post("/investor/otc/offers/{offer_id}/reject")
async def reject_offer(offer_id: str, user=Depends(require_user)):
    offer = await db[OFFERS].find_one({"id": offer_id})
    if not offer:
        raise HTTPException(404, "Offer not found")
    if offer["seller_user_id"] != _uid(user):
        raise HTTPException(403, "Only the seller can reject this offer")
    if offer["status"] != OFFER_PENDING:
        raise HTTPException(409, "Offer is not pending")
    await db[OFFERS].update_one({"id": offer_id}, {"$set": {
        "status": OFFER_REJECTED, "updated_at": now()}})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Deals (investor view + payment proof + cancel)
# ═══════════════════════════════════════════════════════════════════════════
def _payment_instructions(deal: dict) -> dict:
    return {
        "reference": deal["payment_reference"],
        "amount_usd": deal["price_usd"],
        "currency": deal["currency"],
        "method": deal["payment_method"],
        "note": "Pay LUMEN using the reference above, then upload proof. "
                "A manager confirms payment before the NFT is transferred.",
    }


@router.get("/investor/otc/my-deals")
async def my_deals(user=Depends(require_user)):
    uid = _uid(user)
    rows = await db[DEALS].find(
        {"$or": [{"buyer_user_id": uid}, {"seller_user_id": uid}]}
    ).sort("created_at", -1).to_list(500)
    out = []
    for d in rows:
        e = ser(d)
        e["role"] = "buyer" if d.get("buyer_user_id") == uid else "seller"
        out.append(e)
    return {"deals": out}


class PaymentProofRequest(BaseModel):
    method: str = "bank_transfer"
    amount: float
    currency: str = "USD"
    tx_hash: Optional[str] = None
    file_id: Optional[str] = None
    comment: str = ""


@router.post("/investor/otc/deals/{deal_id}/payment-proof")
async def submit_payment_proof(deal_id: str, body: PaymentProofRequest, user=Depends(require_user)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["buyer_user_id"] != _uid(user):
        raise HTTPException(403, "Only the buyer can submit payment proof")
    if deal["status"] != DEAL_PAYMENT_PENDING:
        raise HTTPException(409, f"Deal is not awaiting payment (status={deal['status']})")
    proof = {
        "id": new_id("otcp"),
        "deal_id": deal_id,
        "buyer_user_id": _uid(user),
        "method": body.method if body.method in PAYMENT_METHODS else "manual",
        "amount": r2(body.amount),
        "currency": (body.currency or "USD").upper(),
        "tx_hash": body.tx_hash,
        "file_id": body.file_id,
        "comment": body.comment or "",
        "status": "submitted",
        "created_at": now(),
    }
    await db[PROOFS].insert_one(dict(proof))
    await db[DEALS].update_one({"id": deal_id}, {"$set": {
        "payment_status": PAY_SUBMITTED, "updated_at": now()}})
    await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
        "status": LISTING_PAYMENT_PENDING, "updated_at": now()}})
    return {"ok": True, "proof": ser(proof)}


@router.post("/investor/otc/deals/{deal_id}/cancel")
async def investor_cancel_deal(deal_id: str, user=Depends(require_user)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    uid = _uid(user)
    if uid not in (deal["buyer_user_id"], deal["seller_user_id"]):
        raise HTTPException(403, "Not your deal")
    if deal["status"] in DEAL_TERMINAL:
        raise HTTPException(409, f"Deal already {deal['status']}")
    if deal["payment_status"] == PAY_CONFIRMED:
        raise HTTPException(409, "Payment already confirmed — contact support to dispute")
    return await _cancel_deal(deal, by="investor", actor=uid)


# ═══════════════════════════════════════════════════════════════════════════
# Admin / Manager  (require_staff)
# ═══════════════════════════════════════════════════════════════════════════
async def _cancel_deal(deal: dict, *, by: str, actor: str, reason: str = "") -> dict:
    await db[DEALS].update_one({"id": deal["id"]}, {"$set": {
        "status": DEAL_CANCELLED, "cancelled_by": by, "cancelled_actor": actor,
        "cancel_reason": reason, "updated_at": now()}})
    # free the listing again (re-listable) unless it was already terminal
    await db[LISTINGS].update_one(
        {"id": deal["listing_id"], "status": {"$nin": [LISTING_COMPLETED, LISTING_CANCELLED]}},
        {"$set": {"status": LISTING_ACTIVE, "active_deal_id": None, "updated_at": now()}})
    return {"ok": True, "deal_id": deal["id"], "status": DEAL_CANCELLED}


@router.get("/admin/otc/listings")
async def admin_listings(_=Depends(require_staff)):
    rows = await db[LISTINGS].find({}).sort("created_at", -1).to_list(1000)
    return {"listings": [await _enrich_listing(r) for r in rows]}


@router.get("/admin/otc/deals")
async def admin_deals(status: Optional[str] = None, _=Depends(require_staff)):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows = await db[DEALS].find(q).sort("created_at", -1).to_list(1000)
    summary = {}
    for s in (DEAL_PAYMENT_PENDING, DEAL_PAYMENT_CONFIRMED, DEAL_NFT_TRANSFER_PENDING,
              DEAL_COMPLETED, DEAL_CANCELLED, DEAL_DISPUTED):
        summary[s] = await db[DEALS].count_documents({"status": s})
    return {"summary": summary, "deals": [ser(d) for d in rows]}


@router.get("/admin/otc/deals/{deal_id}")
async def admin_deal_detail(deal_id: str, _=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    proofs = await db[PROOFS].find({"deal_id": deal_id}).sort("created_at", -1).to_list(100)
    return {"deal": ser(deal), "payment_proofs": [ser(p) for p in proofs]}


@router.post("/admin/otc/deals/{deal_id}/confirm-payment")
async def confirm_payment(deal_id: str, staff=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["payment_status"] != PAY_SUBMITTED:
        raise HTTPException(409, f"Payment not submitted (payment_status={deal['payment_status']})")
    if deal["status"] in DEAL_TERMINAL:
        raise HTTPException(409, f"Deal already {deal['status']}")
    await db[DEALS].update_one({"id": deal_id}, {"$set": {
        "payment_status": PAY_CONFIRMED,
        "status": DEAL_NFT_TRANSFER_PENDING,
        "payment_confirmed_by": _uid(staff),
        "payment_confirmed_at": now(),
        "updated_at": now()}})
    await db[PROOFS].update_many(
        {"deal_id": deal_id, "status": "submitted"},
        {"$set": {"status": "accepted", "updated_at": now()}})
    await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
        "status": LISTING_NFT_TRANSFER_PENDING, "updated_at": now()}})
    return {"ok": True, "deal_id": deal_id, "status": DEAL_NFT_TRANSFER_PENDING}


class ConfirmTransferRequest(BaseModel):
    tx_hash: Optional[str] = None
    to_wallet: Optional[str] = None


@router.post("/admin/otc/deals/{deal_id}/confirm-nft-transfer")
async def confirm_nft_transfer(deal_id: str, body: ConfirmTransferRequest = ConfirmTransferRequest(),
                               staff=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["payment_status"] != PAY_CONFIRMED:
        raise HTTPException(409, "Payment must be confirmed before NFT transfer")
    if deal["status"] != DEAL_NFT_TRANSFER_PENDING:
        raise HTTPException(409, f"Deal not awaiting transfer (status={deal['status']})")

    # The single source of ownership truth — reuse the crypto-OS holder mover.
    result = await otc_transfer_holder(
        nft_id=deal["nft_certificate_id"],
        to_user_id=deal["buyer_user_id"],
        to_wallet=body.to_wallet,
        tx_hash=body.tx_hash or deal.get("payment_reference"),
        from_user_id=deal["seller_user_id"],
        source="otc_lumen_guarantor")

    await db[DEALS].update_one({"id": deal_id}, {"$set": {
        "nft_status": "transferred",
        "status": DEAL_COMPLETED,
        "nft_transfer_id": result["transfer_id"],
        "transfer_tx_hash": body.tx_hash,
        "transfer_confirmed_by": _uid(staff),
        "completed_at": now(),
        "updated_at": now()}})
    await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
        "status": LISTING_COMPLETED, "updated_at": now()}})
    logger.info("OTC deal %s COMPLETED — NFT %s holder → %s",
                deal_id, deal["nft_certificate_id"], deal["buyer_user_id"])
    return {"ok": True, "deal_id": deal_id, "status": DEAL_COMPLETED,
            "transfer": result}


@router.post("/admin/otc/deals/{deal_id}/cancel")
async def admin_cancel_deal(deal_id: str, staff=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["status"] in DEAL_TERMINAL:
        raise HTTPException(409, f"Deal already {deal['status']}")
    return await _cancel_deal(deal, by="staff", actor=_uid(staff))


class DisputeRequest(BaseModel):
    reason: str = ""


@router.post("/admin/otc/deals/{deal_id}/dispute")
async def dispute_deal(deal_id: str, body: DisputeRequest = DisputeRequest(),
                       staff=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["status"] == DEAL_COMPLETED:
        raise HTTPException(409, "Completed deal cannot be disputed here")
    await db[DEALS].update_one({"id": deal_id}, {"$set": {
        "status": DEAL_DISPUTED, "dispute_reason": body.reason,
        "disputed_by": _uid(staff), "disputed_at": now(), "updated_at": now()}})
    await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
        "status": LISTING_DISPUTED, "updated_at": now()}})
    # SAFETY NET — freeze the underlying NFT token so it cannot be re-listed,
    # sold or holder-transferred while the dispute is open.
    await freeze_nft(deal["nft_certificate_id"], reason="otc_dispute",
                     by=_uid(staff), ref=deal_id)
    return {"ok": True, "deal_id": deal_id, "status": DEAL_DISPUTED, "nft_frozen": True}


class ResolveDisputeRequest(BaseModel):
    # release_to_buyer = complete the transfer to the buyer (payment was good)
    # refund_seller_keeps = void the deal, NFT stays with seller
    outcome: str = "refund_seller_keeps"
    note: str = ""


@router.post("/admin/otc/deals/{deal_id}/resolve-dispute")
async def resolve_dispute(deal_id: str, body: ResolveDisputeRequest = ResolveDisputeRequest(),
                          staff=Depends(require_staff)):
    deal = await db[DEALS].find_one({"id": deal_id})
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal["status"] != DEAL_DISPUTED:
        raise HTTPException(409, f"Deal is not disputed (status={deal['status']})")
    actor = _uid(staff)
    nft_id = deal["nft_certificate_id"]

    if body.outcome == "release_to_buyer":
        # Force the ownership transfer to the buyer, then unfreeze + complete.
        await unfreeze_nft(nft_id, by=actor, note=f"dispute_resolved:{body.note}")
        result = await otc_transfer_holder(
            nft_id=nft_id, to_user_id=deal["buyer_user_id"],
            tx_hash=deal.get("payment_reference"),
            from_user_id=deal["seller_user_id"], source="dispute_resolution")
        await db[DEALS].update_one({"id": deal_id}, {"$set": {
            "status": DEAL_COMPLETED, "nft_status": "transferred",
            "nft_transfer_id": result["transfer_id"], "dispute_outcome": body.outcome,
            "dispute_resolved_by": actor, "dispute_resolved_at": now(),
            "completed_at": now(), "updated_at": now()}})
        await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
            "status": LISTING_COMPLETED, "updated_at": now()}})
        return {"ok": True, "deal_id": deal_id, "outcome": body.outcome,
                "status": DEAL_COMPLETED, "nft_frozen": False}

    # refund_seller_keeps (default): void the deal, NFT returns to the seller.
    await unfreeze_nft(nft_id, by=actor, note=f"dispute_resolved:{body.note}")
    await db[DEALS].update_one({"id": deal_id}, {"$set": {
        "status": DEAL_CANCELLED, "cancelled_by": "staff", "cancelled_actor": actor,
        "cancel_reason": f"dispute_resolved:{body.note or 'seller_keeps'}",
        "dispute_outcome": body.outcome, "dispute_resolved_by": actor,
        "dispute_resolved_at": now(), "updated_at": now()}})
    await db[LISTINGS].update_one({"id": deal["listing_id"]}, {"$set": {
        "status": LISTING_CANCELLED, "active_deal_id": None, "updated_at": now()}})
    return {"ok": True, "deal_id": deal_id, "outcome": body.outcome,
            "status": DEAL_CANCELLED, "nft_frozen": False}


# ═══════════════════════════════════════════════════════════════════════════
# boot / indexes
# ═══════════════════════════════════════════════════════════════════════════
async def ensure_indexes() -> None:
    try:
        await db[LISTINGS].create_index("id", unique=True)
        await db[LISTINGS].create_index([("status", 1)])
        await db[LISTINGS].create_index([("seller_user_id", 1)])
        await db[LISTINGS].create_index([("nft_certificate_id", 1)])
        await db[OFFERS].create_index("id", unique=True)
        await db[OFFERS].create_index([("listing_id", 1), ("status", 1)])
        await db[OFFERS].create_index([("buyer_user_id", 1)])
        await db[DEALS].create_index("id", unique=True)
        await db[DEALS].create_index([("status", 1)])
        await db[DEALS].create_index([("buyer_user_id", 1)])
        await db[DEALS].create_index([("seller_user_id", 1)])
        await db[DEALS].create_index([("listing_id", 1)])
        await db[PROOFS].create_index("id", unique=True)
        await db[PROOFS].create_index([("deal_id", 1)])
    except Exception as e:  # pragma: no cover
        logger.warning("otc index ensure failed: %s", e)


async def boot() -> None:
    await ensure_indexes()
    logger.info("OTC Lite (H2.8) ready · LUMEN-as-guarantor manual settlement")


__all__ = ["router", "boot"]
