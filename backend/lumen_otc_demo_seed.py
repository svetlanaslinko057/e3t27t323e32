"""
LUMEN — OTC Market demo seed (idempotent)
==========================================

Populates the share-framed OTC secondary market with realistic lots so the
``InvestorOtcMarket`` / lot detail pages render rich product cards (object photo,
city, ROI, dividends, payback, ask price) instead of an empty market or a raw
``pool_xxx / 100% / $6500`` table.

It creates:
  * a dedicated demo seller account (so listings are buyable by everyone else),
  * a handful of MINTED NFT ownership certificates tied to the REAL seeded
    assets (``lumen_assets``) — each carries ``asset_id``, ``invested_usd``,
    ``ownership_percent`` and ``units`` so ``lumen_otc._share_metrics`` can derive
    the investor-facing economics, and
  * one ACTIVE OTC listing per certificate.

Safe to run on every boot — guarded by a ``demo_seed`` marker so it only seeds
once. Skipped in production (``LUMEN_ENV=production``) by the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger("lumen.otc.seed")

NFTS = "lumen_nft_certificates"
LISTINGS = "lumen_otc_listings"
ASSETS = "lumen_assets"
USERS = "users"

SELLER_ID = "user_otc_demo_seller"
SELLER_WALLET = "0x7a25c0f4b2ed9c3a1f6b8e0d2c4a9b7e5d3f1a02"
CONTRACT = "0x" + "1d" * 20

# (asset_id, units, ownership_percent, invested_usd, ask_price_usd)
_LOTS = [
    ("asset-podilskyi",         5000, 5.0,  6500.0,  7200.0),
    ("asset-lavr-tc",           3000, 3.0,  9000.0,  9800.0),
    ("asset-rivne-warehouse",   4000, 4.0,  7500.0,  8400.0),
    ("asset-stoyanka-land",     6000, 6.0, 12000.0, 14500.0),
    ("asset-odessa-apartments", 2500, 2.5,  5000.0,  5400.0),
    ("asset-vyshneve-cottage",  4500, 4.5, 10000.0, 11800.0),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


async def seed_otc_market_demo(db) -> dict:
    """Idempotently seed the OTC secondary market with rich demo lots.

    On every boot it also self-heals the showcase: any demo lot that was
    reserved/sold during a previous demo buy is re-activated and its certificate
    is restored to the demo seller, so the market always presents a full set of
    buyable lots. (Demo lots only — real user listings are never touched.)"""
    if await db[LISTINGS].find_one({"demo_seed": True}):
        await db[LISTINGS].update_many(
            {"demo_seed": True, "status": {"$ne": "active"}},
            {"$set": {"status": "active", "active_deal_id": None, "updated_at": _now()}})
        await db[NFTS].update_many(
            {"demo_seed": True},
            {"$set": {"current_holder_user_id": SELLER_ID, "status": "minted", "frozen": False}})
        await db["lumen_otc_deals"].delete_many({"pool_id": {"$regex": "^pool-asset-"}})
        return {"seeded": False, "reason": "already_seeded", "reactivated": True}

    # 1) Ensure a dedicated demo seller (a DIFFERENT identity from the test
    #    investor, so every other investor sees the lots as buyable).
    if not await db[USERS].find_one({"user_id": SELLER_ID}):
        await db[USERS].insert_one({
            "user_id": SELLER_ID,
            "id": SELLER_ID,
            "email": "otc.seller@lumen.demo",
            "name": "LUMEN OTC (демо-продавець)",
            "role": "investor",
            "roles": ["investor"],
            "states": ["investor"],
            "kyc_status": "approved",
            "email_verified": True,
            "created_at": _now(),
            "source": "otc_demo_seed",
        })

    listings = 0
    nfts = 0
    for i, (asset_id, units, pct, invested, ask) in enumerate(_LOTS):
        asset = await db[ASSETS].find_one({"id": asset_id})
        if not asset:
            continue
        nft_id = _nid("nftcert")
        nft = {
            "id": nft_id,
            "pool_id": f"pool-{asset_id}",
            "asset_id": asset_id,
            "allocation_id": _nid("alloc"),
            "certificate_id": None,
            "original_investor_id": SELLER_ID,
            "current_holder_user_id": SELLER_ID,
            "current_wallet": SELLER_WALLET,
            "chain": "ethereum",
            "contract_address": CONTRACT,
            "token_id": 4200 + i,
            "units": units,
            "ownership_percent": pct,
            "invested_usd": invested,
            "status": "minted",
            "frozen": False,
            "active": True,
            "demo_seed": True,
            "created_at": _now(),
            "updated_at": _now(),
            "minted_at": _now(),
        }
        await db[NFTS].insert_one(dict(nft))
        nfts += 1

        listing = {
            "id": _nid("otcl"),
            "seller_user_id": SELLER_ID,
            "pool_id": nft["pool_id"],
            "asset_id": asset_id,
            "nft_certificate_id": nft_id,
            "token_id": nft["token_id"],
            "units": units,
            "ownership_percent": pct,
            "price_usd": float(ask),
            "currency": "USD",
            "status": "active",
            "active_deal_id": None,
            "demo_seed": True,
            "created_at": _now(),
            "updated_at": _now(),
            "expires_at": None,
        }
        await db[LISTINGS].insert_one(dict(listing))
        listings += 1

    logger.info("OTC market demo seed: %d listings / %d certificates", listings, nfts)
    return {"seeded": True, "listings": listings, "nfts": nfts, "seller_id": SELLER_ID}
