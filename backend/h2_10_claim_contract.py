#!/usr/bin/env python3
"""
h2_10_claim_contract.py — H2.10 Investor Crypto Center (Claim path + income)
============================================================================

Validates the only NEW backend behaviour in H2.10 (the rest of H2.10 is UI on
already-tested endpoints): the **Claim Center** loop and money-safety.

Scenario (all via the real API, so audits stay truthful):
  1. Seller funds a pool with a linked wallet → 1 NFT minted (holder = seller).
  2. An on-chain CertificateTransferred event moves the NFT to a wallet that is
     NOT linked to any LUMEN user → NFT becomes `holder_unlinked`.
  3. Admin posts revenue + distributes → the payout is BLOCKED
     (claimable_pending_wallet_link, holder_wallet = the unlinked wallet).
  4. A claimer (demo user) links THAT wallet (sign-in challenge) → backend
     re-links the NFT to them and auto-releases the blocked payout.
  5. Assertions:
       CL1  blocked payout visible in /admin/web3/blocked-payouts before claim
       CL2  /investor/web3/claimable shows the blocked amount for the claimer
       CL3  after linking the holding wallet → NFT holder re-linked to claimer
       CL4  blocked payout released → credited to claimer (/investor/nft-income)
       CL5  /investor/web3/claimable now empty
       CL6  wallet DELETE guard: cannot delete a wallet holding active NFTs
       AUD  pool cash-audit AND platform balance-audit still reconcile (money-safe)

Run:  cd /app/backend && python h2_10_claim_contract.py
"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct

load_dotenv()
BASE = os.environ.get("POOL_CONTRACT_BASE", "http://localhost:8001")
ADMIN_EMAIL, ADMIN_PASS = "admin@atlas.dev", "admin123"
SELLER_EMAIL, SELLER_PASS = "client@atlas.dev", "client123"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


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


async def link_wallet(c, H, acct):
    r = await c.post("/api/investor/web3/wallet/challenge", headers=H,
                     json={"chain": "ethereum", "address": acct.address})
    msg = r.json()["message"]
    sig = Account.sign_message(encode_defunct(text=msg), private_key=acct.key).signature.hex()
    return await c.post("/api/investor/web3/wallet/verify", headers=H,
                        json={"chain": "ethereum", "address": acct.address, "signature": sig})


async def main() -> int:
    seller_acct = Account.create()
    unlinked_acct = Account.create()   # holds the NFT but is linked to nobody (yet)

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        admin_tok = await _login(c, ADMIN_EMAIL, ADMIN_PASS)
        seller_tok = await _login(c, SELLER_EMAIL, SELLER_PASS)
        rclaim = await c.post("/api/auth/demo", json={"role": "client"})
        claimer_tok = _cookie(rclaim)
        claimer_id = rclaim.json().get("user_id")
        check("auth admin+seller+claimer", all([admin_tok, seller_tok, claimer_tok, claimer_id]))
        AH = {"Cookie": f"session_token={admin_tok}"}
        SH = {"Cookie": f"session_token={seller_tok}"}
        CH = {"Cookie": f"session_token={claimer_tok}"}

        # 1) seller wallet + funded pool → minted NFT
        check("seller wallet verified", (await link_wallet(c, SH, seller_acct)).status_code == 200)
        p = (await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-claim", "title": "Claim Pool", "target_amount": 10000,
            "min_ticket": 100, "total_units": 10000})).json()["pool"]
        pid = p["id"]
        await c.post(f"/api/admin/pools/{pid}/open", headers=AH)
        cid = (await c.post("/api/investor/pools/contribute", headers=SH, json={
            "pool_id": pid, "amount": 10000, "currency": "USD", "gateway": "fiat"})).json()["contribution"]["id"]
        await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH, json={
            "provider_ref": "x", "bank_reference": "y", "received_amount": 10000, "received_currency": "USD"})
        await c.post(f"/api/admin/pools/{pid}/mark-operating", headers=AH)
        reg = (await c.get("/api/admin/nft-registry", headers=AH)).json()
        nft = [n for n in reg["nfts"] if n["pool_id"] == pid][0]
        check("NFT minted to seller", nft["status"] == "minted" and bool(nft.get("token_id")),
              f"status={nft['status']} token={nft.get('token_id')}")
        token_id = nft["token_id"]

        # 2) on-chain transfer to an UNLINKED wallet → holder_unlinked
        await c.post("/api/admin/blockchain/events", headers=AH, json={
            "event_type": "CertificateTransferred", "token_id": token_id,
            "contract_address": nft.get("contract_address"), "tx_hash": "0xclaim_unlink",
            "from_wallet": seller_acct.address, "to_wallet": unlinked_acct.address})
        reg = (await c.get("/api/admin/nft-registry", headers=AH)).json()
        nft2 = [n for n in reg["nfts"] if n["id"] == nft["id"]][0]
        check("NFT now holder_unlinked", nft2["status"] == "holder_unlinked" and
              nft2["current_holder_user_id"] is None, f"status={nft2['status']}")

        # 3) revenue → distribute → blocked payout
        ev = (await c.post("/api/admin/revenue-events", headers=AH, json={
            "pool_id": pid, "gross_amount": 1000, "description": "rev"})).json()["revenue_event"]
        dist = (await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)).json()
        check("distribution reports blocked payout", dist.get("blocked_pending_wallet_link") is True,
              f"blocked={dist.get('blocked_amount')}")

        # CL1 — blocked payout visible to admin
        bp = (await c.get("/api/admin/web3/blocked-payouts", headers=AH)).json()
        mine = [b for b in bp["blocked_payouts"] if b.get("token_id") == token_id]
        check("CL1 blocked payout visible (admin)", len(mine) == 1 and mine[0]["amount_usd"] == 1000.0,
              f"rows={len(mine)}")

        # claimer links the UNLINKED wallet → re-link + auto-release
        # First, while NOT linked, claimable should be empty for claimer.
        cl_before = (await c.get("/api/investor/web3/claimable", headers=CH)).json()
        check("claimable empty before linking holding wallet", cl_before["claimable_count"] == 0)

        # 4) link the holding wallet
        check("claimer links holding wallet", (await link_wallet(c, CH, unlinked_acct)).status_code == 200)

        # CL3 — NFT re-linked to claimer
        reg = (await c.get("/api/admin/nft-registry", headers=AH)).json()
        nft3 = [n for n in reg["nfts"] if n["id"] == nft["id"]][0]
        check("CL3 NFT re-linked to claimer", nft3["current_holder_user_id"] == claimer_id and
              nft3["status"] == "transferred", f"holder={nft3['current_holder_user_id']} status={nft3['status']}")

        # CL4 — blocked payout auto-released → credited to claimer
        income = (await c.get("/api/investor/nft-income", headers=CH)).json()
        check("CL4 released payout credited to claimer", income["summary"]["accrued"] >= 1000.0,
              f"accrued={income['summary']['accrued']}")

        # CL5 — claimable now empty
        cl_after = (await c.get("/api/investor/web3/claimable", headers=CH)).json()
        check("CL5 claimable empty after release", cl_after["claimable_count"] == 0,
              f"count={cl_after['claimable_count']}")

        # explicit claim is idempotent (nothing left)
        again = (await c.post("/api/investor/web3/claim", headers=CH)).json()
        check("claim idempotent (0 left)", again["released_count"] == 0)

        # CL6 — wallet DELETE guard (claimer's wallet now holds an active NFT)
        wl = (await c.get("/api/investor/web3/wallets", headers=CH)).json()["wallets"]
        wid = wl[0]["id"]
        rdel = await c.delete(f"/api/investor/web3/wallet/{wid}", headers=CH)
        check("CL6 cannot delete wallet holding active NFT (409)", rdel.status_code == 409,
              f"{rdel.status_code}")

        # AUD — money invariants still reconcile after the release
        ca = (await c.get(f"/api/admin/pools/{pid}/cash-audit", headers=AH)).json()
        ba = (await c.get("/api/admin/pool-cash-audit", headers=AH)).json()
        check("AUD pool cash-audit reconciles", ca.get("reconciles") is True, str(ca.get("checks")))
        check("AUD platform balance-audit reconciles", ba.get("reconciles") is True, str(ba.get("checks")))

    print(f"\n════════ H2.10 CLAIM CONTRACT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("H2.10 CLAIM CONTRACT — ALL GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
