"""
LUMEN — OTC Public & Guest layer
================================

Powers the public **OTC marketplace page** on the website and the
"buy-as-guest, claim-after-login" flow:

    Guest opens /otc  →  browses real-asset lots (photo, yield, share %, income,
    payout history)  →  taps "Buy"  →  connects wallet (MetaMask) OR pays with
    internal balance (requires auth)  →  a RESERVATION is created and a
    `claim_token` is handed back.

    Later the user registers / logs in  →  the cabinet automatically CLAIMS the
    reservation by its token  →  the bought lot appears in their account as a
    pending OTC purchase (manual settlement continues via the existing OTC deal
    flow handled by managers).

This layer is read-mostly + reservation bookkeeping; it never moves NFTs or
money on its own (that stays in the audited investor/manager OTC flow).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from lumen_api import db, get_current_user as require_user
import lumen_otc as otc

logger = logging.getLogger("lumen.otc.public")
router = APIRouter(prefix="/api", tags=["lumen-otc-public"])

GUEST_ORDERS = "lumen_otc_guest_orders"

GUEST_METHODS = {"wallet", "internal"}
GUEST_RESERVED = "reserved"
GUEST_CLAIMED = "claimed"
GUEST_CANCELLED = "cancelled"


def _public_view(e: dict) -> dict:
    """Strip caller-specific / internal flags for anonymous consumption."""
    e.pop("is_mine", None)
    return e


# ═══════════════════════════════════════════════════════════════════════════
# Public (no auth) — marketplace listing + detail
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/public/otc/listings")
async def public_listings():
    """All ACTIVE OTC lots for the public marketplace page (no auth)."""
    rows = await db[otc.LISTINGS].find({"status": otc.LISTING_ACTIVE}).sort("created_at", -1).to_list(500)
    out = []
    for r in rows:
        try:
            out.append(_public_view(await otc._enrich_listing(r)))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("enrich listing %s failed: %s", r.get("id"), exc)
    return {"listings": out}


@router.get("/public/otc/listings/{listing_id}")
async def public_listing_detail(listing_id: str):
    """Single OTC lot — full public detail (asset, economics, payout history)."""
    listing = await db[otc.LISTINGS].find_one({"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    e = _public_view(await otc._enrich_listing(listing))
    e["payout_history"] = otc._payout_schedule(e.get("metrics") or {})
    return {"listing": e}


# ═══════════════════════════════════════════════════════════════════════════
# Guest reservation  (no auth)  →  claim token
# ═══════════════════════════════════════════════════════════════════════════
class ReserveRequest(BaseModel):
    listing_id: str
    payment_method: str = "wallet"        # 'wallet' | 'internal'
    wallet_address: Optional[str] = None  # required when payment_method == 'wallet'
    email: Optional[str] = None
    name: Optional[str] = None


@router.post("/public/otc/reserve")
async def public_reserve(body: ReserveRequest):
    method = (body.payment_method or "wallet").lower()
    if method not in GUEST_METHODS:
        raise HTTPException(400, "payment_method must be 'wallet' or 'internal'")
    listing = await db[otc.LISTINGS].find_one({"id": body.listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.get("status") != otc.LISTING_ACTIVE:
        raise HTTPException(409, "Listing is not available")
    if method == "wallet" and not (body.wallet_address or "").strip():
        raise HTTPException(400, "wallet_address is required for wallet payment")

    enriched = await otc._enrich_listing(listing)
    order = {
        "id": otc.new_id("otcg"),
        "claim_token": otc.new_id("claim"),
        "listing_id": listing["id"],
        "asset_id": listing.get("asset_id"),
        "nft_certificate_id": listing.get("nft_certificate_id"),
        "price_usd": listing.get("price_usd"),
        "payment_method": method,
        "wallet_address": (body.wallet_address or "").strip() or None,
        "email": (body.email or "").strip().lower() or None,
        "name": (body.name or "").strip() or None,
        "status": GUEST_RESERVED,
        "user_id": None,
        "asset_snapshot": (enriched.get("asset") or {}),
        "created_at": otc.now(),
        "updated_at": otc.now(),
    }
    await db[GUEST_ORDERS].insert_one(dict(order))
    logger.info("OTC guest reservation %s for listing %s via %s", order["id"], listing["id"], method)
    return {
        "ok": True,
        "reservation_id": order["id"],
        "claim_token": order["claim_token"],
        "payment_method": method,
        "listing": _public_view(enriched),
        "next": "Зареєструйтесь або увійдіть, щоб завершити купівлю — лот зʼявиться у вашому кабінеті.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Claim  (auth)  →  attach a guest reservation to the logged-in investor
# ═══════════════════════════════════════════════════════════════════════════
class ClaimRequest(BaseModel):
    claim_token: str


@router.post("/investor/otc/claim")
async def claim_reservation(body: ClaimRequest, user=Depends(require_user)):
    uid = otc._uid(user)
    order = await db[GUEST_ORDERS].find_one({"claim_token": body.claim_token})
    if not order:
        raise HTTPException(404, "Reservation not found")
    if order.get("status") == GUEST_CLAIMED and order.get("user_id") not in (None, uid):
        raise HTTPException(409, "Reservation already claimed by another account")
    await db[GUEST_ORDERS].update_one(
        {"id": order["id"]},
        {"$set": {"user_id": uid, "status": GUEST_CLAIMED, "updated_at": otc.now()}},
    )
    order = await db[GUEST_ORDERS].find_one({"id": order["id"]})
    logger.info("OTC reservation %s claimed by %s", order["id"], uid)
    return {"ok": True, "reservation": otc.ser(order)}


@router.get("/investor/otc/reservations")
async def my_reservations(user=Depends(require_user)):
    uid = otc._uid(user)
    rows = await db[GUEST_ORDERS].find({"user_id": uid}).sort("created_at", -1).to_list(200)
    return {"reservations": [otc.ser(r) for r in rows]}
