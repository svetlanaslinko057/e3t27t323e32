#!/usr/bin/env python3
"""
h2_8_otc_lite_contract.py — H2.8 OTC Lite (LUMEN-as-guarantor)
==============================================================

Proves the secondary-transfer business mechanic end-to-end against the live API,
on top of the existing ownership layer (H2.3–H2.7). LUMEN escrows/guarantees a
MANUAL settlement: buyer pays, manager confirms payment, NFT is transferred,
the dividend recipient changes — and snapshot protection keeps PAST dividends
with the seller while FUTURE dividends route to the buyer.

Checks
  G1  seller can list own NFT
  G2  seller cannot list a foreign NFT
  G3  buyer cannot buy own listing
  B1  buyer can reserve listing (buy → deal)
  B2  listing cannot be double-sold (second buy → 409)
  P1  buyer submits payment proof
  P2  manager confirms payment (→ nft_transfer_pending)
  T1  manager confirms NFT transfer (→ completed)
  T2  NFT holder changes (registry: current_holder_user_id == buyer)
  D0  PAST dividend (before transfer) credited the SELLER
  D1  FUTURE dividend (after transfer) credited the BUYER (NFT holder snapshot)
  D2  PAST dividend rows are immutable (still SELLER after transfer)
  I1  pool NFT invariants still pass (unlinked-wallet payout safety intact)
  C1  cancel path: buyer cancels → deal cancelled, listing re-activated
  X1  dispute path: manager disputes a paid deal → deal disputed

Run:  cd /app/backend && python h2_8_otc_lite_contract.py
"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
BASE = os.environ.get("POOL_CONTRACT_BASE", "http://localhost:8001")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ADMIN_EMAIL, ADMIN_PASS = "admin@atlas.dev", "admin123"
SELLER_EMAIL, SELLER_PASS = "client@atlas.dev", "client123"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


def r2(x):
    return round(float(x or 0), 2)


def _cookie(resp):
    tok = resp.cookies.get("session_token")
    if not tok:
        for sc in resp.headers.get_list("set-cookie"):
            if sc.startswith("session_token="):
                tok = sc.split("=", 1)[1].split(";", 1)[0]
    return tok


async def _login(c, email, password):
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    return _cookie(r) if r.status_code == 200 else None


async def _me(c, H):
    r = await c.get("/api/auth/me", headers=H)
    return r.json() if r.status_code == 200 else {}


async def link_wallet(c, H, acct):
    r = await c.post("/api/investor/web3/wallet/challenge", headers=H,
                     json={"chain": "ethereum", "address": acct.address})
    msg = r.json()["message"]
    sig = Account.sign_message(encode_defunct(text=msg), private_key=acct.key).signature.hex()
    r = await c.post("/api/investor/web3/wallet/verify", headers=H,
                     json={"chain": "ethereum", "address": acct.address, "signature": sig})
    if r.status_code == 200:
        wl = (await c.get("/api/investor/web3/wallets", headers=H)).json()["wallets"]
        match = [w for w in wl if (w.get("address") or "").lower() == acct.address.lower()]
        if match:
            await c.post("/api/investor/web3/wallet/primary", headers=H,
                         json={"wallet_id": match[0]["id"]})
    return r


async def fund_pool_one_nft(c, AH, SH, title):
    """Create a pool, fund it fully from the SELLER → exactly ONE minted NFT."""
    p = (await c.post("/api/admin/pools", headers=AH, json={
        "asset_id": "asset-nft", "title": title, "target_amount": 10000,
        "min_ticket": 100, "total_units": 10000})).json()["pool"]
    pid = p["id"]
    await c.post(f"/api/admin/pools/{pid}/open", headers=AH)
    cid = (await c.post("/api/investor/pools/contribute", headers=SH, json={
        "pool_id": pid, "amount": 10000, "currency": "USD", "gateway": "fiat"})).json()["contribution"]["id"]
    await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH, json={
        "provider_ref": "x", "bank_reference": "y", "received_amount": 10000, "received_currency": "USD"})
    await c.post(f"/api/admin/pools/{pid}/mark-operating", headers=AH)
    reg = (await c.get("/api/admin/nft-registry", headers=AH)).json()
    nfts = [n for n in reg["nfts"] if n["pool_id"] == pid]
    return pid, (nfts[0] if nfts else None)


async def make_revenue(c, AH, pid, gross):
    ev = (await c.post("/api/admin/revenue-events", headers=AH, json={
        "pool_id": pid, "gross_amount": gross, "description": "rev"})).json()["revenue_event"]
    await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)
    return ev["id"]


async def main() -> int:
    mc = AsyncIOMotorClient(MONGO_URL)
    db = mc[DB_NAME]
    seller_acct = Account.create()
    buyer_acct = Account.create()

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        admin_tok = await _login(c, ADMIN_EMAIL, ADMIN_PASS)
        seller_tok = await _login(c, SELLER_EMAIL, SELLER_PASS)
        # Independent buyer via demo auth (clean isolation)
        rb = await c.post("/api/auth/demo", json={"role": "client"})
        buyer = rb.json()
        buyer_id = buyer.get("user_id")
        buyer_tok = _cookie(rb)
        check("auth admin+seller+buyer", all([admin_tok, seller_tok, buyer_tok, buyer_id]),
              f"admin={bool(admin_tok)} seller={bool(seller_tok)} buyer={bool(buyer_tok)}")
        AH = {"Cookie": f"session_token={admin_tok}"}
        SH = {"Cookie": f"session_token={seller_tok}"}
        BH = {"Cookie": f"session_token={buyer_tok}"}

        # Buyer must be KYC-approved to buy/offer
        await db.users.update_one({"user_id": buyer_id}, {"$set": {"kyc_status": "approved"}})

        seller_id = (await _me(c, SH)).get("user_id") or (await _me(c, SH)).get("id")

        # Wallets (seller wallet BEFORE mark-operating so NFT mints to seller)
        print("\n── setup: wallets ──")
        check("seller wallet verified", (await link_wallet(c, SH, seller_acct)).status_code == 200)
        check("buyer wallet verified", (await link_wallet(c, BH, buyer_acct)).status_code == 200)

        # ── Pool #1: full lifecycle ──
        print("\n── N: fund pool #1 → 1 NFT to seller ──")
        pid, nft = await fund_pool_one_nft(c, AH, SH, "OTC Pool 1")
        check("seller has one minted NFT", bool(nft) and nft["status"] == "minted" and
              nft["current_holder_user_id"] == seller_id, str(nft and nft.get("status")))
        nft_id = nft["id"]

        # G2 — seller cannot list foreign NFT (buyer tries to list seller's NFT)
        print("\n── G2: foreign-NFT listing rejected ──")
        r = await c.post("/api/investor/otc/listings", headers=BH,
                         json={"nft_certificate_id": nft_id, "price_usd": 9999})
        check("foreign NFT listing rejected (403)", r.status_code == 403, f"{r.status_code} {r.text[:120]}")

        # D0 — PAST dividend BEFORE any transfer → seller credited
        print("\n── D0: past dividend → seller ──")
        ev0 = await make_revenue(c, AH, pid, 1000)
        rec0 = await db.lumen_revenue_distributions.distinct("recipient_user_id", {"revenue_event_id": ev0})
        check("past dividend credited the SELLER", rec0 == [seller_id], f"recipients={rec0} seller={seller_id}")

        # G1 — seller lists own NFT
        print("\n── G1: seller lists own NFT ──")
        r = await c.post("/api/investor/otc/listings", headers=SH,
                         json={"nft_certificate_id": nft_id, "price_usd": 12000})
        check("seller can list own NFT", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        listing = r.json()["listing"]
        lid = listing["id"]

        # G3 — buyer cannot buy own listing (seller buying own listing)
        print("\n── G3: self-buy rejected ──")
        r = await c.post(f"/api/investor/otc/listings/{lid}/buy", headers=SH, json={})
        check("self-buy rejected (409)", r.status_code == 409, f"{r.status_code} {r.text[:120]}")

        # B1 — buyer buys
        print("\n── B1/B2: buy + double-sell guard ──")
        r = await c.post(f"/api/investor/otc/listings/{lid}/buy", headers=BH, json={})
        check("buyer can reserve listing (buy)", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        deal = r.json()["deal"]
        did = deal["id"]
        # B2 — double sell guard
        r2x = await c.post(f"/api/investor/otc/listings/{lid}/buy", headers=BH, json={})
        check("listing cannot be double-sold (409)", r2x.status_code == 409, f"{r2x.status_code}")

        # P1 — buyer submits payment proof
        print("\n── P1/P2: payment proof + manager confirm ──")
        r = await c.post(f"/api/investor/otc/deals/{did}/payment-proof", headers=BH, json={
            "method": "bank_transfer", "amount": 12000, "currency": "USD", "comment": "paid"})
        check("payment proof submitted", r.status_code == 200 and r.json()["proof"]["status"] == "submitted",
              f"{r.status_code} {r.text[:120]}")

        # P2 — manager (admin/staff) confirms payment
        r = await c.post(f"/api/admin/otc/deals/{did}/confirm-payment", headers=AH)
        check("manager confirms payment → nft_transfer_pending",
              r.status_code == 200 and r.json()["status"] == "nft_transfer_pending", f"{r.status_code} {r.text[:120]}")

        # T1 — manager confirms NFT transfer
        print("\n── T1/T2: NFT transfer + holder change ──")
        r = await c.post(f"/api/admin/otc/deals/{did}/confirm-nft-transfer", headers=AH,
                         json={"tx_hash": "0xotc_transfer_1"})
        check("manager confirms NFT transfer → completed",
              r.status_code == 200 and r.json()["status"] == "completed", f"{r.status_code} {r.text[:160]}")

        # T2 — holder changed in registry
        reg = (await c.get("/api/admin/nft-registry", headers=AH)).json()
        nft2 = [n for n in reg["nfts"] if n["id"] == nft_id][0]
        check("NFT holder changed to buyer", nft2["current_holder_user_id"] == buyer_id and
              nft2["status"] == "transferred", f"holder={nft2['current_holder_user_id']} status={nft2['status']}")

        # D1 — FUTURE dividend AFTER transfer → buyer
        print("\n── D1/D2: future dividend → buyer, past stays seller ──")
        ev1 = await make_revenue(c, AH, pid, 1000)
        rec1 = await db.lumen_revenue_distributions.distinct("recipient_user_id", {"revenue_event_id": ev1})
        check("future dividend credited the BUYER", rec1 == [buyer_id], f"recipients={rec1} buyer={buyer_id}")

        # D2 — past dividend rows immutable (event0 still seller)
        rec0_after = await db.lumen_revenue_distributions.distinct("recipient_user_id", {"revenue_event_id": ev0})
        check("past dividend immutable (still seller)", rec0_after == [seller_id], f"recipients={rec0_after}")

        # I1 — NFT invariants still pass
        inv = (await c.get(f"/api/admin/nft-registry/invariants/{pid}", headers=AH)).json()
        check("pool NFT invariants all pass", inv.get("all_passed") is True, str(inv.get("counts")))

        # ── Pool #2: cancel + dispute paths ──
        print("\n── C1: cancel path ──")
        pid2, nftb = await fund_pool_one_nft(c, AH, SH, "OTC Pool 2")
        check("pool #2 NFT minted to seller", bool(nftb) and nftb["status"] == "minted")
        nftb_id = nftb["id"]
        lid2 = (await c.post("/api/investor/otc/listings", headers=SH,
                json={"nft_certificate_id": nftb_id, "price_usd": 8000})).json()["listing"]["id"]
        d2 = (await c.post(f"/api/investor/otc/listings/{lid2}/buy", headers=BH, json={})).json()["deal"]
        rc = await c.post(f"/api/investor/otc/deals/{d2['id']}/cancel", headers=BH)
        check("buyer cancels deal", rc.status_code == 200 and rc.json()["status"] == "cancelled", rc.text[:120])
        lst = await db.lumen_otc_listings.find_one({"id": lid2})
        check("listing re-activated after cancel", lst["status"] == "active", lst["status"])

        # X1 — dispute path (re-buy the now-active listing, pay, dispute)
        print("\n── X1: dispute path ──")
        d3 = (await c.post(f"/api/investor/otc/listings/{lid2}/buy", headers=BH, json={})).json()["deal"]
        await c.post(f"/api/investor/otc/deals/{d3['id']}/payment-proof", headers=BH, json={
            "method": "bank_transfer", "amount": 8000, "currency": "USD"})
        rd = await c.post(f"/api/admin/otc/deals/{d3['id']}/dispute", headers=AH, json={"reason": "mismatch"})
        check("manager disputes deal", rd.status_code == 200 and rd.json()["status"] == "disputed", rd.text[:120])

    mc.close()
    print(f"\n════════ H2.8 OTC LITE RESULT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("H2.8 OTC LITE CONTRACT — ALL GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
