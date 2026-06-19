"""
Idempotent demo seeder for the Web3 SHARE MARKETPLACE.

Goal: make the OTC market and "Мої активи" sell REAL OBJECTS (ЖК «Подільський»,
ТЦ «Лавр», …) with photos / city / yield / dividends — instead of `pool_xxx`.

It mints share-NFT certificates on the 6 real seeded assets, assigns realistic
fractional ownership + invested amounts, and creates OTC listings sold by demo
co-investors so the demo investor can BROWSE and BUY real assets.

Run:  python seed_web3_market.py            (safe to re-run — deterministic ids)
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta

# load .env so DB_NAME/MONGO_URL match the running server
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import lumen_crypto_os as cos

db = cos.db
NFTS = cos.NFTS
LISTINGS = "lumen_otc_listings"
CONTRACT = "0xmockcertificatecontract"


def now():
    return datetime.now(timezone.utc)


def addr(seed: str) -> str:
    import hashlib
    return "0x" + hashlib.sha1(seed.encode()).hexdigest()[:40]


# (asset_id, holder_email, ownership_percent, invested_usd, ask_price_usd, list_it)
PLAN = [
    # demo investor's own holdings (appear in "Мої активи", he can sell them)
    ("asset-podilskyi",        "client@atlas.dev", 6.0, 6000,  7400,  False),
    ("asset-lavr-tc",          "client@atlas.dev", 8.0, 12000, 13900, False),
    # co-investors' listings on the open market (demo investor can BUY)
    ("asset-stoyanka-land",    "olena.k@lumen.test",  5.0, 5000,  6200,  True),
    ("asset-rivne-warehouse",  "ihor.p@lumen.test",   10.0, 9000,  11500, True),
    ("asset-odessa-apartments","family@atlas.dev",    7.0, 14000, 16800, True),
    ("asset-vyshneve-cottage", "olena.k@lumen.test",  12.0, 8000,  10400, True),
]


async def get_user(email: str) -> dict:
    u = await db["users"].find_one({"email": email})
    if not u:
        raise SystemExit(f"User not found: {email}")
    return u


async def ensure_pool(asset: dict) -> str:
    """Ensure a lightweight pool exists for this real asset."""
    pool_id = "pool_demo_" + asset["id"].replace("asset-", "").replace("-", "")[:18]
    existing = await db["lumen_pools"].find_one({"id": pool_id})
    if existing:
        return pool_id
    await db["lumen_pools"].insert_one({
        "id": pool_id,
        "asset_id": asset["id"],
        "title": asset.get("title"),
        "status": "operating",
        "currency": "USD", "base_currency": "USD",
        "unit_price": 1.0, "unit_price_usd": 1.0,
        "total_units": 1_000_000, "issued_units": 1_000_000,
        "target_amount_usd": 1_000_000, "raised_usd": 1_000_000,
        "platform_fee_bps": 0, "reserve_bps": 0,
        "created_at": now(), "updated_at": now(), "opened_at": now(),
        "summary": asset.get("description") or asset.get("title"),
        "demo_seeded": True,
    })
    return pool_id


async def seed():
    created = {"nfts": 0, "listings": 0, "pools": 0}
    # token id counter base
    base_token = 9_000_000
    for idx, (asset_id, email, pct, invested, ask, list_it) in enumerate(PLAN):
        asset = await db["lumen_assets"].find_one({"id": asset_id})
        if not asset:
            print(f"  ! asset missing: {asset_id} — skip")
            continue
        holder = await get_user(email)
        uid = holder["user_id"]
        pool_id = await ensure_pool(asset)

        nft_id = f"nftcert_demo_{asset_id.replace('asset-','').replace('-','')[:16]}"
        wallet = addr(email)
        units = int(pct * 10000)  # 1% = 10000 units
        token_id = str(base_token + idx)

        existing_nft = await db[NFTS].find_one({"id": nft_id})
        nft_doc = {
            "id": nft_id,
            "certificate_id": nft_id,
            "pool_id": pool_id,
            "asset_id": asset_id,
            "token_id": token_id,
            "contract_address": CONTRACT,
            "chain": "ethereum",
            "units": units,
            "ownership_percent": pct,
            "invested_usd": invested,
            "unit_price": round(invested / units, 6) if units else 1.0,
            "status": "transferred",
            "active": True,
            "original_investor_id": uid,
            "current_holder_user_id": uid,
            "current_wallet": wallet,
            "minted_at": now() - timedelta(days=400),
            "created_at": now() - timedelta(days=400),
            "updated_at": now(),
            "demo_seeded": True,
        }
        if existing_nft:
            await db[NFTS].update_one({"id": nft_id}, {"$set": nft_doc})
        else:
            await db[NFTS].insert_one(nft_doc); created["nfts"] += 1

        # ensure the holder has a verified primary wallet so it looks real
        if not await db[cos.WALLETS].find_one({"user_id": uid, "address": wallet}):
            await db[cos.WALLETS].insert_one({
                "id": f"w_demo_{uid[-8:]}", "user_id": uid, "chain": "ethereum",
                "address": wallet, "verified": True, "disabled": False, "primary": True,
                "source": "demo", "created_at": now(), "verified_at": now(), "updated_at": now()})

        if list_it:
            listing_id = f"otcl_demo_{asset_id.replace('asset-','').replace('-','')[:16]}"
            # drop any active deal references so it shows on the market
            listing_doc = {
                "id": listing_id,
                "seller_user_id": uid,
                "pool_id": pool_id,
                "asset_id": asset_id,
                "nft_certificate_id": nft_id,
                "token_id": token_id,
                "units": units,
                "ownership_percent": pct,
                "price_usd": ask,
                "currency": "USD",
                "status": "active",
                "active_deal_id": None,
                "created_at": now() - timedelta(days=idx + 1),
                "updated_at": now(),
                "expires_at": now() + timedelta(days=60),
                "demo_seeded": True,
            }
            if await db[LISTINGS].find_one({"id": listing_id}):
                await db[LISTINGS].update_one({"id": listing_id}, {"$set": listing_doc})
            else:
                await db[LISTINGS].insert_one(listing_doc); created["listings"] += 1

    print(f"Seed done: {created}")
    total_listings = await db[LISTINGS].count_documents({"status": "active"})
    print(f"Active listings now: {total_listings}")


if __name__ == "__main__":
    asyncio.run(seed())
