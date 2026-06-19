"""
Sprint 13 — Secondary Market: end-to-end core proof.

Proves the full lifecycle through the REAL HTTP API + the core invariant:

    Ownership → Listing → Bid/Buy → Trade → Settlement → Ledger

Invariant under test (the user was explicit):
    Σ ownership units per asset NEVER changes — only the owner changes.

Also checks money conservation (buyer −gross, seller +(gross−fee), platform +fee)
and the seller-reserve / insufficient-funds / can't-buy-own guards.

Run: python test_secondary_e2e.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE = "http://localhost:8001"
ASSET = "asset-podilskyi"
SELLER_EMAIL, SELLER_PW = "client@atlas.dev", "client123"
BUYER_EMAIL, BUYER_PW = "buyer2@atlas.dev", "buyer123"

_db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


# ── ownership maths (mirror lumen_secondary.compute_ownership_uah) ────────────
async def ownership(investor_id, asset_id):
    p = 0.0
    async for inv in _db.lumen_investments.find({"investor_id": investor_id, "asset_id": asset_id, "status": "active"}):
        p += float(inv.get("amount_uah") or inv.get("amount") or 0)
    inflow = outflow = 0.0
    async for t in _db.lumen_share_transfers.find({"to_investor_id": investor_id, "asset_id": asset_id}):
        inflow += float(t.get("amount_uah") or 0)
    async for t in _db.lumen_share_transfers.find({"from_investor_id": investor_id, "asset_id": asset_id}):
        outflow += float(t.get("amount_uah") or 0)
    return round(p + inflow - outflow, 2)


async def asset_investor_ids(asset_id):
    ids = set()
    async for inv in _db.lumen_investments.find({"asset_id": asset_id, "status": "active"}, {"investor_id": 1}):
        ids.add(inv["investor_id"])
    async for t in _db.lumen_share_transfers.find({"asset_id": asset_id}, {"from_investor_id": 1, "to_investor_id": 1}):
        ids.add(t["from_investor_id"]); ids.add(t["to_investor_id"])
    return ids


async def total_owned(asset_id):
    return round(sum([await ownership(i, asset_id) for i in await asset_investor_ids(asset_id)]), 2)


async def total_primary(asset_id):
    s = 0.0
    async for inv in _db.lumen_investments.find({"asset_id": asset_id, "status": "active"}):
        s += float(inv.get("amount_uah") or inv.get("amount") or 0)
    return round(s, 2)


async def wallet_settled(investor_id):
    w = await _db.lumen_wallets.find_one({"investor_id": investor_id})
    return float((w or {}).get("settled_balance") or 0)


async def platform_revenue():
    r = 0.0
    async for e in _db.lumen_ledger_entries.find({"investor_id": "platform-revenue", "reason": "platform_fee", "entry_type": "credit"}):
        r += float(e.get("amount_uah") or 0)
    return round(r, 2)


# ── setup: ensure buyer exists + funded ──────────────────────────────────────
async def ensure_buyer():
    from lumen_payments import _ledger_append  # type: ignore
    from lumen_wallet import recompute_wallet   # type: ignore

    u = await _db.users.find_one({"email": BUYER_EMAIL})
    if not u:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await _db.users.insert_one({
            "user_id": uid, "email": BUYER_EMAIL, "name": "Test Buyer",
            "role": "investor", "roles": ["investor"], "level": "junior",
            "skills": [], "source": "test",
            "password_hash": bcrypt.hashpw(BUYER_PW.encode(), bcrypt.gensalt()).decode(),
            "picture": None, "rating": 5.0, "completed_tasks": 0,
            "active_load": 0, "states": [], "active_context": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        uid = u.get("id") or u.get("user_id")
    # top-up wallet to 60000 via an `adjustment` credit (a real wallet reason)
    bal = await wallet_settled(uid)
    if bal < 60000:
        await _ledger_append(
            entry_type="credit", reason="adjustment", investor_id=uid, asset_id=None,
            investment_id=None, payment_request_id=None, amount=60000 - bal,
            currency="UAH", fx_rate=1.0, amount_uah=60000 - bal,
            actor_id="test-harness", notes="e2e buyer top-up",
        )
        await recompute_wallet(uid, "UAH")
    return uid


async def login(client, email, pw):
    r = await client.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    token = r.cookies.get("session_token")
    if not token:
        import re
        m = re.search(r"session_token=([^;]+)", r.headers.get("set-cookie", ""))
        token = m.group(1) if m else None
    # Secure cookie is dropped over http → pin it explicitly as a header.
    client.headers["Cookie"] = f"session_token={token}"
    return r


async def main():
    print("=== Sprint 13 Secondary Market — E2E core proof ===\n")
    buyer_id = await ensure_buyer()
    seller = await _db.users.find_one({"email": SELLER_EMAIL})
    seller_id = seller.get("id") or seller.get("user_id")
    print(f"seller={seller_id}  buyer={buyer_id}  asset={ASSET}\n")

    # baseline invariant
    base_total = await total_owned(ASSET)
    base_primary = await total_primary(ASSET)
    print(f"baseline: total_owned={base_total}  total_primary={base_primary}")
    check("INVARIANT baseline: Σowned == Σprimary", abs(base_total - base_primary) < 0.5,
          f"{base_total} vs {base_primary}")

    async with httpx.AsyncClient(timeout=30) as sc, httpx.AsyncClient(timeout=30) as bc:
        await login(sc, SELLER_EMAIL, SELLER_PW)
        await login(bc, BUYER_EMAIL, BUYER_PW)

        # ============================================================ TEST 1
        print("\n--- TEST 1: buy-now full lifecycle + invariant ---")
        pre_s_own = await ownership(seller_id, ASSET)
        pre_b_own = await ownership(buyer_id, ASSET)
        pre_s_wal = await wallet_settled(seller_id)
        pre_b_wal = await wallet_settled(buyer_id)
        pre_rev = await platform_revenue()
        UNITS, PRICE = 10000.0, 1.0
        gross = UNITS * PRICE
        fee = round(gross * 0.01, 2)

        r = await sc.post(f"{BASE}/api/investor/secondary/listings",
                          json={"asset_id": ASSET, "units_uah": UNITS, "price_per_unit": PRICE})
        check("seller can create listing", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
        listing_id = r.json().get("id") if r.status_code == 200 else None

        r2 = await bc.post(f"{BASE}/api/investor/secondary/bids",
                           json={"listing_id": listing_id, "units_uah": UNITS})
        ok = r2.status_code == 200 and r2.json().get("mode") == "buy_now"
        check("buyer buy-now settles trade", ok, f"HTTP {r2.status_code} {r2.text[:140]}")
        trade = (r2.json().get("trade") or {}) if r2.status_code == 200 else {}
        check("trade status == settled", trade.get("status") == "settled", str(trade.get("status")))

        post_total = await total_owned(ASSET)
        post_s_own = await ownership(seller_id, ASSET)
        post_b_own = await ownership(buyer_id, ASSET)
        post_s_wal = await wallet_settled(seller_id)
        post_b_wal = await wallet_settled(buyer_id)
        post_rev = await platform_revenue()

        check("★ INVARIANT: Σ ownership units per asset UNCHANGED",
              abs(post_total - base_total) < 0.5, f"{base_total} → {post_total}")
        check("seller ownership −units", abs((pre_s_own - post_s_own) - UNITS) < 0.5,
              f"{pre_s_own} → {post_s_own}")
        check("buyer ownership +units", abs((post_b_own - pre_b_own) - UNITS) < 0.5,
              f"{pre_b_own} → {post_b_own}")
        check("buyer wallet −gross", abs((pre_b_wal - post_b_wal) - gross) < 0.5,
              f"{pre_b_wal} → {post_b_wal}")
        check("seller wallet +(gross−fee)", abs((post_s_wal - pre_s_wal) - (gross - fee)) < 0.5,
              f"{pre_s_wal} → {post_s_wal}")
        check("platform revenue +fee", abs((post_rev - pre_rev) - fee) < 0.5,
              f"{pre_rev} → {post_rev}")
        d_money = (post_b_wal - pre_b_wal) + (post_s_wal - pre_s_wal) + (post_rev - pre_rev)
        check("money conservation Δbuyer+Δseller+Δplatform == 0", abs(d_money) < 0.5, f"Δ={d_money}")
        st = await _db.lumen_share_transfers.find_one({"trade_id": trade.get("id")})
        check("share_transfer recorded (seller→buyer)",
              bool(st) and st.get("from_investor_id") == seller_id and st.get("to_investor_id") == buyer_id)
        le = await _db.lumen_ledger_entries.count_documents({"notes": {"$regex": trade.get("id", "x")}})
        check("3 ledger entries for trade", le == 3, f"found {le}")

        # ============================================================ TEST 2
        print("\n--- TEST 2: offer → accept lifecycle ---")
        r = await sc.post(f"{BASE}/api/investor/secondary/listings",
                          json={"asset_id": ASSET, "units_uah": 5000.0, "price_per_unit": 1.0})
        lid2 = r.json().get("id")
        pre_total2 = await total_owned(ASSET)
        r = await bc.post(f"{BASE}/api/investor/secondary/bids",
                          json={"listing_id": lid2, "units_uah": 5000.0, "price_per_unit": 0.95})
        ok = r.status_code == 200 and r.json().get("mode") == "offer"
        check("buyer can place offer (price < listing)", ok, f"HTTP {r.status_code} {r.text[:120]}")
        bid_id = (r.json().get("bid") or {}).get("id") if ok else None
        r = await sc.post(f"{BASE}/api/investor/secondary/bids/{bid_id}/accept")
        ok = r.status_code == 200 and (r.json().get("trade") or {}).get("status") == "settled"
        check("seller accepts bid → trade settled", ok, f"HTTP {r.status_code} {r.text[:140]}")
        post_total2 = await total_owned(ASSET)
        check("★ INVARIANT after offer/accept", abs(post_total2 - pre_total2) < 0.5,
              f"{pre_total2} → {post_total2}")

        # ============================================================ TEST 3 (guards)
        print("\n--- TEST 3: guards ---")
        r = await sc.post(f"{BASE}/api/investor/secondary/listings",
                          json={"asset_id": ASSET, "units_uah": 3000.0, "price_per_unit": 1.0})
        own_listing = r.json().get("id")
        r = await sc.post(f"{BASE}/api/investor/secondary/bids",
                          json={"listing_id": own_listing, "units_uah": 1000.0})
        check("cannot buy own listing (400)", r.status_code == 400, f"HTTP {r.status_code}")

        # oversell guard: seller lists more than owned
        huge = await ownership(seller_id, ASSET) + 1_000_000
        r = await sc.post(f"{BASE}/api/investor/secondary/listings",
                          json={"asset_id": ASSET, "units_uah": huge, "price_per_unit": 1.0})
        check("cannot list more than owned (400)", r.status_code == 400, f"HTTP {r.status_code}")

        # insufficient funds: buyer tries to buy beyond wallet
        r = await sc.post(f"{BASE}/api/investor/secondary/listings",
                          json={"asset_id": ASSET, "units_uah": 50000.0, "price_per_unit": 1.0})
        big_listing = r.json().get("id")
        r = await bc.post(f"{BASE}/api/investor/secondary/bids",
                          json={"listing_id": big_listing, "units_uah": 50000.0})
        check("insufficient funds blocked (402)", r.status_code == 402, f"HTTP {r.status_code}")

        # ============================================================ TEST 4 (admin)
        print("\n--- TEST 4: admin oversight ---")
        ac = httpx.AsyncClient(timeout=30)
        await login(ac, "admin@atlas.dev", "admin123")
        r = await ac.get(f"{BASE}/api/admin/secondary/overview")
        ok = r.status_code == 200
        ov = r.json() if ok else {}
        check("admin overview 200", ok, f"HTTP {r.status_code}")
        check("admin sees settled trades >= 2", ov.get("counts", {}).get("trades", {}).get("settled", 0) >= 2,
              str(ov.get("counts", {}).get("trades")))
        check("admin platform revenue > 0", float(ov.get("platform_revenue_uah") or 0) > 0,
              f"rev={ov.get('platform_revenue_uah')}")
        await ac.aclose()

        # ============================================================ FINAL invariant
        print("\n--- FINAL: global invariant ---")
        final_total = await total_owned(ASSET)
        final_primary = await total_primary(ASSET)
        check("★ FINAL INVARIANT: Σowned == Σprimary == baseline",
              abs(final_total - base_primary) < 0.5 and abs(final_primary - base_primary) < 0.5,
              f"owned={final_total} primary={final_primary} baseline={base_primary}")

    print(f"\n===== RESULT: {len(PASS)} passed, {len(FAIL)} failed =====")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL SECONDARY-MARKET E2E CHECKS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
