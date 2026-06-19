"""
LUMEN — Crypto OS  ·  H2.3 / H2.4 / H2.6 / H2.7
===============================================

The crypto-ownership layer AROUND the (off-chain) smart contract. Pool OS stays
the accounting source of truth; this layer adds:

  H2.3 Wallet Registry      lumen_web3_wallets   (sign-message verified wallets)
  H2.4 NFT Registry         lumen_nft_certificates (ownership mirror per allocation)
  H2.6 Event Engine         lumen_blockchain_events (receive/dedupe/process/audit)
  H2.7 Transfer Processor   lumen_nft_transfers + holder snapshots

ARCHITECTURAL RULE (fixed):
    Pool OS            = accounting source of truth (money)
    NFT holder         = ownership-transfer source (who owns the right NOW)
    Dividend recipient = current NFT holder at snapshot date

Backward compatibility: every allocation auto-mints exactly ONE NFT whose
`current_holder_user_id` starts as the original investor — so an untransferred
holding distributes EXACTLY as before. Transfers re-route FUTURE dividends only.

Payout safety: if an NFT is held by a wallet NOT linked to a LUMEN user, the
dividend is NOT lost — it is parked as `claimable_pending_wallet_link`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, get_current_user as require_user
from lumen_blockchain_provider import get_provider

logger = logging.getLogger("lumen.crypto_os")
router = APIRouter(prefix="/api", tags=["lumen-crypto-os"])

WALLETS = "lumen_web3_wallets"
NFTS = "lumen_nft_certificates"
EVENTS = "lumen_blockchain_events"
TRANSFERS = "lumen_nft_transfers"
SNAPSHOTS = "lumen_nft_holder_snapshots"
RECOVERIES = "lumen_wallet_recoveries"

CHAINS = {"ethereum", "polygon", "arbitrum", "base"}

# NFT lifecycle statuses
NFT_PENDING_WALLET = "pending_wallet"   # owner known (LUMEN user), no wallet linked yet
NFT_PENDING_MINT = "pending_mint"       # wallet linked, awaiting on-chain mint
NFT_MINTED = "minted"                   # minted on-chain
NFT_TRANSFERRED = "transferred"         # transferred to another linked LUMEN user
NFT_HOLDER_UNLINKED = "holder_unlinked"  # held by wallet not linked to any LUMEN user
NFT_BURNED = "burned"


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _iso(d: Any) -> Any:
    return d.isoformat() if isinstance(d, datetime) else d


def ser(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def r2(x: Any) -> float:
    return round(float(x or 0), 2)


# ═══════════════════════════════════════════════════════════════════════════
# H2.3 — Wallet Registry
# ═══════════════════════════════════════════════════════════════════════════
def _challenge_message(address: str, nonce: str) -> str:
    return (f"LUMEN wallet verification\nAddress: {address.lower()}\n"
            f"Nonce: {nonce}\nSign this message to link your wallet to LUMEN.")


async def wallet_owner(address: str) -> Optional[str]:
    """Return the LUMEN user_id that has VERIFIED this wallet, else None."""
    w = await db[WALLETS].find_one({"address": (address or "").lower(), "verified": True})
    return w.get("user_id") if w else None


async def primary_wallet(user_id: str) -> Optional[dict]:
    return await db[WALLETS].find_one({"user_id": user_id, "verified": True, "primary": True}) \
        or await db[WALLETS].find_one({"user_id": user_id, "verified": True})


class WalletChallengeRequest(BaseModel):
    chain: str = "ethereum"
    address: str


class WalletVerifyRequest(BaseModel):
    chain: str = "ethereum"
    address: str
    signature: str


@router.post("/investor/web3/wallet/challenge")
async def wallet_challenge(body: WalletChallengeRequest, user=Depends(require_user)):
    chain = body.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(400, f"Unsupported chain (allowed: {sorted(CHAINS)})")
    address = body.address.lower()
    if not (address.startswith("0x") and len(address) == 42):
        raise HTTPException(400, "Invalid EVM address")
    nonce = uuid4().hex
    await db[WALLETS].update_one(
        {"user_id": user["id"], "chain": chain, "address": address},
        {"$set": {"nonce": nonce, "updated_at": now()},
         "$setOnInsert": {"id": new_id("wallet"), "verified": False,
                          "primary": False, "created_at": now()}},
        upsert=True)
    return {"ok": True, "message": _challenge_message(address, nonce), "nonce": nonce}


@router.post("/investor/web3/wallet/verify")
async def wallet_verify(body: WalletVerifyRequest, user=Depends(require_user)):
    address = body.address.lower()
    rec = await db[WALLETS].find_one(
        {"user_id": user["id"], "chain": body.chain.lower(), "address": address})
    if not rec or not rec.get("nonce"):
        raise HTTPException(409, "No pending challenge for this wallet")
    msg = _challenge_message(address, rec["nonce"])
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
        recovered = Account.recover_message(encode_defunct(text=msg), signature=body.signature)
    except Exception as e:
        raise HTTPException(400, f"Signature verification failed: {e}")
    if recovered.lower() != address:
        raise HTTPException(400, "Signature does not match the wallet address")
    # Ensure this wallet is not verified by another user
    other = await db[WALLETS].find_one(
        {"address": address, "verified": True, "user_id": {"$ne": user["id"]}})
    if other:
        raise HTTPException(409, "Wallet already linked to another LUMEN account")
    has_primary = await db[WALLETS].find_one({"user_id": user["id"], "verified": True, "primary": True})
    await db[WALLETS].update_one(
        {"id": rec["id"]},
        {"$set": {"verified": True, "verified_at": now(), "nonce": None,
                  "primary": not bool(has_primary), "updated_at": now()}})
    # Backfill: any of this user's NFTs awaiting a wallet can now mint.
    await _backfill_pending_wallet_nfts(user["id"], address)
    return {"ok": True, "address": address, "primary": not bool(has_primary)}


@router.get("/investor/web3/wallets")
async def list_my_wallets(user=Depends(require_user)):
    rows = await db[WALLETS].find({"user_id": user["id"]}).sort("created_at", 1).to_list(100)
    return {"wallets": [ser({k: v for k, v in w.items() if k != "nonce"}) for w in rows]}


class SetPrimaryRequest(BaseModel):
    wallet_id: str


@router.post("/investor/web3/wallet/primary")
async def set_primary_wallet(body: SetPrimaryRequest, user=Depends(require_user)):
    w = await db[WALLETS].find_one({"id": body.wallet_id, "user_id": user["id"], "verified": True})
    if not w:
        raise HTTPException(404, "Verified wallet not found")
    await db[WALLETS].update_many({"user_id": user["id"]}, {"$set": {"primary": False}})
    await db[WALLETS].update_one({"id": w["id"]}, {"$set": {"primary": True, "updated_at": now()}})
    return {"ok": True}


@router.get("/admin/web3/wallets")
async def admin_list_wallets(_=Depends(require_admin)):
    rows = await db[WALLETS].find({}).sort("created_at", -1).to_list(1000)
    return {"wallets": [ser({k: v for k, v in w.items() if k != "nonce"}) for w in rows]}


# ═══════════════════════════════════════════════════════════════════════════
# H2.4 — NFT Registry (ownership mirror)
# ═══════════════════════════════════════════════════════════════════════════
async def mirror_nfts_for_pool(pool: dict) -> int:
    """Idempotently create ONE NFT certificate per allocation (units>0). Holder
    starts as the original investor. If the investor has a verified wallet, the
    NFT is minted (mock) immediately; otherwise it waits as pending_wallet."""
    pool_id = pool["id"]
    issued_units = int(pool.get("issued_units") or 0) or 1
    allocations = await db["lumen_pool_allocations"].find(
        {"pool_id": pool_id, "units": {"$gt": 0}}).to_list(100000)
    created = 0
    for a in allocations:
        exists = await db[NFTS].find_one({"pool_id": pool_id, "allocation_id": a["id"]})
        if exists:
            continue
        cert = await db["lumen_pool_certificates"].find_one(
            {"pool_id": pool_id, "investor_id": a["investor_id"]})
        units = int(a["units"])
        wallet = await primary_wallet(a["investor_id"])
        doc = {
            "id": new_id("nftcert"),
            "pool_id": pool_id,
            "asset_id": pool.get("asset_id"),
            "allocation_id": a["id"],
            "certificate_id": cert.get("id") if cert else None,
            "original_investor_id": a["investor_id"],
            "current_holder_user_id": a["investor_id"],   # backward-compat default
            "current_wallet": (wallet.get("address") if wallet else None),
            "chain": (wallet.get("chain") if wallet else os.environ.get("LUMEN_POOL_CHAIN", "ethereum")),
            "contract_address": None,
            "token_id": None,
            "units": units,
            "ownership_percent": round(units / issued_units * 100, 6),
            "status": NFT_PENDING_WALLET if not wallet else NFT_PENDING_MINT,
            "active": True,
            "created_at": now(),
            "updated_at": now(),
        }
        await db[NFTS].insert_one(dict(doc))
        created += 1
        if wallet:
            await _mint_nft(doc["id"])
    if created:
        logger.info("Pool %s: mirrored %d NFT certificate(s)", pool_id, created)
    return created


async def _mint_nft(nft_id: str) -> None:
    nft = await db[NFTS].find_one({"id": nft_id})
    if not nft or nft["status"] not in (NFT_PENDING_MINT, NFT_PENDING_WALLET):
        return
    if not nft.get("current_wallet"):
        return
    provider = get_provider()
    res = await provider.mint_nft(
        pool_id=nft["pool_id"], allocation_id=nft["allocation_id"],
        wallet=nft["current_wallet"], units=nft["units"],
        metadata_uri=f"lumen://pool/{nft['pool_id']}/cert/{nft.get('certificate_id')}")
    await db[NFTS].update_one({"id": nft_id}, {"$set": {
        "token_id": res["token_id"], "contract_address": (res["contract_address"] or "").lower(),
        "chain": res["chain"], "status": NFT_MINTED, "minted_at": now(),
        "mint_tx": res["tx_hash"], "updated_at": now()}})
    await ingest_event(res["event"], source="mock_mint")


async def _backfill_pending_wallet_nfts(user_id: str, address: str) -> None:
    """When a user links a wallet:
      1) mint any of their `pending_wallet` NFTs, and
      2) re-link any `holder_unlinked` NFTs that this exact wallet holds back to
         the user (so future dividends route to them), then release any blocked
         (claimable_pending_wallet_link) distributions for those NFTs.
    """
    addr = address.lower()
    rows = await db[NFTS].find(
        {"current_holder_user_id": user_id, "status": NFT_PENDING_WALLET}).to_list(10000)
    for n in rows:
        await db[NFTS].update_one({"id": n["id"]}, {"$set": {
            "current_wallet": addr, "status": NFT_PENDING_MINT, "updated_at": now()}})
        await _mint_nft(n["id"])

    relinked = await db[NFTS].find(
        {"current_wallet": addr, "status": NFT_HOLDER_UNLINKED}).to_list(10000)
    for n in relinked:
        await db[NFTS].update_one({"id": n["id"]}, {"$set": {
            "current_holder_user_id": user_id, "status": NFT_TRANSFERRED, "updated_at": now()}})
        await db[TRANSFERS].insert_one({
            "id": new_id("nfttr"), "pool_id": n.get("pool_id"), "token_id": n.get("token_id"),
            "contract_address": n.get("contract_address"), "from_wallet": addr, "to_wallet": addr,
            "from_user_id": None, "to_user_id": user_id, "tx_hash": None,
            "source": "wallet_relink", "status": "processed", "created_at": now()})
    if relinked:
        await _release_blocked_for_user(user_id)


async def _release_blocked_for_user(user_id: str) -> dict:
    """Release distributions parked as claimable_pending_wallet_link for NFTs that
    are now held by `user_id`. Money-safe: only flips status + recipient and
    recomputes balances (the net was already accounted at distribution time)."""
    held = await db[NFTS].find({"current_holder_user_id": user_id}).to_list(100000)
    token_ids = [n["token_id"] for n in held if n.get("token_id")]
    if not token_ids:
        return {"released": 0, "total": 0.0}
    blocked = await db[DISTS].find(
        {"status": "claimable_pending_wallet_link", "token_id": {"$in": token_ids}}).to_list(100000)
    total = 0.0
    ccys = set()
    for d in blocked:
        await db[DISTS].update_one({"id": d["id"]}, {"$set": {
            "status": "credited", "investor_id": user_id, "recipient_user_id": user_id,
            "released_at": now()}})
        total += float(d.get("gross_amount") or 0)
        ccys.add(d.get("currency") or "USD")
    for c in ccys:
        try:
            from lumen_pool_os import recompute_pool_balance
            await recompute_pool_balance(user_id, c)
        except Exception as e:  # pragma: no cover
            logger.warning("recompute_pool_balance failed for %s/%s: %s", user_id, c, e)
    if blocked:
        logger.info("Released %d blocked payout(s) for %s (total %.2f)", len(blocked), user_id, total)
    return {"released": len(blocked), "total": round(total, 2)}


@router.get("/investor/nft-certificates")
async def my_nft_certificates(user=Depends(require_user)):
    owned = await db[NFTS].find({"current_holder_user_id": user["id"], "active": True}) \
        .sort("created_at", -1).to_list(1000)
    pending_link = await db[NFTS].find(
        {"current_wallet": {"$ne": None}, "current_holder_user_id": None}).to_list(200)

    # Share-framing: attach the REAL asset behind each ownership certificate so
    # the UI can speak "частка в активі" (photo, city, yield) instead of "NFT".
    async def _enrich(n: dict) -> dict:
        out = ser(n)
        a = None
        if n.get("asset_id"):
            a = await db["lumen_assets"].find_one({"id": n["asset_id"]})
        if a:
            out["asset"] = {
                "id": a.get("id"),
                "title": a.get("title"),
                "category": a.get("category"),
                "location": a.get("location"),
                "cover_url": a.get("cover_url"),
                "target_yield": a.get("target_yield"),
            }
        return out

    return {"nfts": [await _enrich(n) for n in owned],
            "pending_wallet_link": [ser(n) for n in pending_link]}


@router.delete("/investor/web3/wallet/{wallet_id}")
async def delete_my_wallet(wallet_id: str, user=Depends(require_user)):
    w = await db[WALLETS].find_one({"id": wallet_id, "user_id": user["id"]})
    if not w:
        raise HTTPException(404, "Wallet not found")
    addr = (w.get("address") or "").lower()
    holds = await db[NFTS].count_documents(
        {"current_wallet": addr, "current_holder_user_id": user["id"],
         "status": {"$in": [NFT_MINTED, NFT_TRANSFERRED]}})
    if holds:
        raise HTTPException(409, "Wallet holds active NFT certificates — transfer them before removing")
    await db[WALLETS].delete_one({"id": wallet_id})
    # If we removed the primary, promote the oldest remaining verified wallet.
    if w.get("primary"):
        nxt = await db[WALLETS].find_one(
            {"user_id": user["id"], "verified": True}, sort=[("created_at", 1)])
        if nxt:
            await db[WALLETS].update_one({"id": nxt["id"]}, {"$set": {"primary": True, "updated_at": now()}})
    return {"ok": True, "deleted": wallet_id}


# ── H2.10 — Investor NFT income + Claim Center ─────────────────────────────
@router.get("/investor/nft-income")
async def my_nft_income(user=Depends(require_user)):
    """Pool-OS dividend income attributed to the investor as the CURRENT NFT
    holder (snapshot-based), plus what is blocked pending a wallet link."""
    uid = user["id"]
    rows = await db[DISTS].find({"recipient_user_id": uid}).sort("created_at", -1).to_list(5000)
    addrs = [(w.get("address") or "").lower() for w in await db[WALLETS]
             .find({"user_id": uid, "verified": True}).to_list(100)]
    blocked = []
    if addrs:
        blocked = await db[DISTS].find(
            {"status": "claimable_pending_wallet_link",
             "holder_wallet": {"$in": addrs}}).sort("created_at", -1).to_list(2000)

    accrued = round(sum(float(r.get("gross_amount") or 0)
                        for r in rows if r.get("status") == "credited"), 2)
    blocked_total = round(sum(float(b.get("gross_amount") or 0) for b in blocked), 2)

    # paid / available come from pool balances (credited − withdrawn − reserved)
    paid_total = 0.0
    available_total = 0.0
    try:
        from lumen_pool_os import recompute_pool_balance
        ccys = await db[DISTS].distinct("currency", {"recipient_user_id": uid, "status": "credited"})
        for c in ccys:
            bal = await recompute_pool_balance(uid, c)
            paid_total += float(bal.get("withdrawn") or 0)
            available_total += float(bal.get("available") or 0)
    except Exception as e:  # pragma: no cover
        logger.warning("income balance compute failed: %s", e)

    def row(d, status_override=None):
        return {
            "id": d.get("id"), "pool_id": d.get("pool_id"), "asset_id": d.get("asset_id"),
            "revenue_event_id": d.get("revenue_event_id"), "token_id": d.get("token_id"),
            "units": d.get("units"), "amount_usd": round(float(d.get("gross_amount") or 0), 2),
            "currency": d.get("currency"), "status": status_override or d.get("status"),
            "snapshot_at": _iso(d.get("created_at")),
        }

    return {
        "summary": {
            "accrued": accrued,
            "paid": round(paid_total, 2),
            "available": round(available_total, 2),
            "blocked": blocked_total,
        },
        "distributions": [row(r) for r in rows],
        "blocked_distributions": [row(b) for b in blocked],
    }


@router.get("/investor/web3/claimable")
async def my_claimable(user=Depends(require_user)):
    """Claim Center: what the investor can unlock by linking the holding wallet."""
    uid = user["id"]
    pending_wallet_nfts = await db[NFTS].find(
        {"current_holder_user_id": uid, "status": NFT_PENDING_WALLET}).to_list(1000)
    addrs = [(w.get("address") or "").lower() for w in await db[WALLETS]
             .find({"user_id": uid, "verified": True}).to_list(100)]
    blocked = []
    if addrs:
        blocked = await db[DISTS].find(
            {"status": "claimable_pending_wallet_link",
             "holder_wallet": {"$in": addrs}}).to_list(2000)
    total = round(sum(float(b.get("gross_amount") or 0) for b in blocked), 2)

    # Share-framing: resolve the REAL asset title behind each pool so the UI can
    # speak "частка в активі" instead of leaking an internal pool_id.
    _asset_ids = {x.get("asset_id") for x in (list(pending_wallet_nfts) + list(blocked)) if x.get("asset_id")}
    _titles: dict = {}
    if _asset_ids:
        async for a in db["lumen_assets"].find({"id": {"$in": list(_asset_ids)}}, {"id": 1, "title": 1}):
            _titles[a["id"]] = a.get("title")

    def _pn(n: dict) -> dict:
        out = ser(n)
        out["asset_title"] = _titles.get(n.get("asset_id"))
        return out

    return {
        "has_verified_wallet": bool(addrs),
        "pending_wallet_nfts": [_pn(n) for n in pending_wallet_nfts],
        "blocked_distributions": [
            {"id": b.get("id"), "pool_id": b.get("pool_id"), "token_id": b.get("token_id"),
             "asset_title": _titles.get(b.get("asset_id")),
             "amount_usd": round(float(b.get("gross_amount") or 0), 2),
             "currency": b.get("currency"), "wallet": b.get("holder_wallet")}
            for b in blocked],
        "claimable_total_usd": total,
        "claimable_count": len(blocked),
    }


@router.post("/investor/web3/claim")
async def claim_blocked(user=Depends(require_user)):
    """Release blocked dividends for NFTs the investor now holds (after linking
    the wallet that controls them)."""
    res = await _release_blocked_for_user(user["id"])
    return {"ok": True, "released_count": res["released"], "released_total_usd": res["total"]}


@router.get("/investor/web3/summary")
async def my_web3_summary(user=Depends(require_user)):
    """Lightweight aggregate for the SITE-WIDE wallet layer (header badge).
    One call returns everything the chrome needs: primary wallet, wallet count,
    active NFT certificates held, active OTC listings, and claimable totals."""
    uid = user["id"]
    pw = await primary_wallet(uid)
    wallet_count = await db[WALLETS].count_documents({"user_id": uid, "verified": True})
    nft_count = await db[NFTS].count_documents(
        {"current_holder_user_id": uid, "active": True,
         "status": {"$in": [NFT_MINTED, NFT_TRANSFERRED, NFT_PENDING_MINT, NFT_PENDING_WALLET]}})
    otc_active = await db["lumen_otc_listings"].count_documents(
        {"seller_user_id": uid, "status": "active"})
    # claimable (blocked pending wallet link) — reuse the same query as Claim Center
    addrs = [(w.get("address") or "").lower() for w in await db[WALLETS]
             .find({"user_id": uid, "verified": True}).to_list(100)]
    claimable_total = 0.0
    if addrs:
        blocked = await db[DISTS].find(
            {"status": "claimable_pending_wallet_link",
             "holder_wallet": {"$in": addrs}}).to_list(2000)
        claimable_total = round(sum(float(b.get("gross_amount") or 0) for b in blocked), 2)
    pending_link = await db[NFTS].count_documents(
        {"current_holder_user_id": uid, "status": NFT_PENDING_WALLET})
    return {
        "has_wallet": bool(pw),
        "primary_wallet": (
            {"address": pw.get("address"), "chain": pw.get("chain"),
             "verified": pw.get("verified", False)} if pw else None),
        "wallet_count": wallet_count,
        "nft_count": nft_count,
        "otc_active_listings": otc_active,
        "claimable_total_usd": claimable_total,
        "pending_wallet_links": pending_link,
        "needs_attention": bool(claimable_total > 0 or pending_link > 0),
    }


@router.get("/admin/nft-registry")
async def admin_nft_registry(_=Depends(require_admin)):
    async def cnt(q):
        return await db[NFTS].count_documents(q)
    rows = await db[NFTS].find({}).sort("created_at", -1).to_list(2000)
    return {
        "summary": {
            "total": await cnt({}),
            "minted": await cnt({"status": NFT_MINTED}),
            "pending_wallet": await cnt({"status": NFT_PENDING_WALLET}),
            "pending_mint": await cnt({"status": NFT_PENDING_MINT}),
            "transferred": await cnt({"status": NFT_TRANSFERRED}),
            "holder_unlinked": await cnt({"status": NFT_HOLDER_UNLINKED}),
        },
        "nfts": [ser(n) for n in rows],
    }


# ═══════════════════════════════════════════════════════════════════════════
# H2.6 — Blockchain Event Engine (receive / dedupe / process / audit)
# ═══════════════════════════════════════════════════════════════════════════
EVENT_HANDLERS = {}


def _dedupe_key(ev: dict) -> str:
    return (f"{ev.get('event_type')}|{(ev.get('contract_address') or '').lower()}|"
            f"{ev.get('tx_hash')}|{ev.get('token_id')}|{ev.get('log_index', 0)}")


async def ingest_event(ev: dict, source: str = "indexer") -> dict:
    """Receive → dedupe → persist → process → audit. Idempotent by dedupe_key."""
    key = _dedupe_key(ev)
    existing = await db[EVENTS].find_one({"dedupe_key": key})
    if existing:
        return {"ok": True, "deduped": True, "event_id": existing["id"],
                "status": existing.get("status")}
    doc = {
        "id": new_id("bcev"),
        "event_type": ev.get("event_type"),
        "chain": ev.get("chain", os.environ.get("LUMEN_POOL_CHAIN", "ethereum")),
        "contract_address": (ev.get("contract_address") or "").lower() or None,
        "tx_hash": ev.get("tx_hash"),
        "log_index": ev.get("log_index", 0),
        "payload": ev,
        "dedupe_key": key,
        "source": source,
        "status": "received",
        "received_at": now(),
    }
    await db[EVENTS].insert_one(dict(doc))
    try:
        handler = EVENT_HANDLERS.get(ev.get("event_type"))
        result = await handler(ev) if handler else {"ignored": True}
        await db[EVENTS].update_one({"id": doc["id"]}, {"$set": {
            "status": "processed", "processed_at": now(), "result": result}})
        return {"ok": True, "deduped": False, "event_id": doc["id"], "result": result}
    except Exception as e:  # pragma: no cover
        await db[EVENTS].update_one({"id": doc["id"]}, {"$set": {
            "status": "failed", "error": str(e), "processed_at": now()}})
        logger.warning("event %s processing failed: %s", doc["id"], e)
        return {"ok": False, "event_id": doc["id"], "error": str(e)}


def event_handler(event_type: str):
    def deco(fn):
        EVENT_HANDLERS[event_type] = fn
        return fn
    return deco


@event_handler("CertificateMinted")
async def _on_minted(ev: dict) -> dict:
    nft = await db[NFTS].find_one({"token_id": ev.get("token_id"),
                                   "contract_address": (ev.get("contract_address") or "").lower()})
    return {"nft_id": nft["id"] if nft else None, "noted": True}


@event_handler("CertificateTransferred")
async def _on_transferred(ev: dict) -> dict:
    return await process_nft_transfer(
        token_id=ev.get("token_id"),
        contract_address=(ev.get("contract_address") or "").lower(),
        from_wallet=(ev.get("from_wallet") or "").lower() or None,
        to_wallet=(ev.get("to_wallet") or "").lower() or None,
        tx_hash=ev.get("tx_hash"))


class IngestEventRequest(BaseModel):
    event_type: str
    token_id: Optional[str] = None
    contract_address: Optional[str] = None
    tx_hash: Optional[str] = None
    from_wallet: Optional[str] = None
    to_wallet: Optional[str] = None
    log_index: int = 0
    extra: Dict[str, Any] = Field(default_factory=dict)


@router.post("/admin/blockchain/events")
async def admin_ingest_event(body: IngestEventRequest, _=Depends(require_admin)):
    ev = {k: v for k, v in body.dict().items() if k != "extra"}
    ev.update(body.extra or {})
    return await ingest_event(ev, source="admin")


@router.get("/admin/blockchain/events")
async def admin_list_events(_=Depends(require_admin)):
    rows = await db[EVENTS].find({}).sort("received_at", -1).to_list(500)
    return {"events": [ser(e) for e in rows]}


# ═══════════════════════════════════════════════════════════════════════════
# H2.7 — NFT Transfer Processor (ownership-transfer source)
# ═══════════════════════════════════════════════════════════════════════════
async def process_nft_transfer(*, token_id: str, contract_address: str,
                               from_wallet: Optional[str], to_wallet: Optional[str],
                               tx_hash: Optional[str]) -> dict:
    nft = await db[NFTS].find_one({"token_id": token_id, "contract_address": contract_address})
    if not nft:
        raise HTTPException(404, "NFT not found for transfer")
    from_user = nft.get("current_holder_user_id")
    to_user = await wallet_owner(to_wallet) if to_wallet else None
    new_status = NFT_TRANSFERRED if to_user else NFT_HOLDER_UNLINKED
    await db[NFTS].update_one({"id": nft["id"]}, {"$set": {
        "current_wallet": to_wallet,
        "current_holder_user_id": to_user,        # None => payouts blocked
        "status": new_status,
        "updated_at": now(),
    }})
    transfer = {
        "id": new_id("nfttr"),
        "pool_id": nft["pool_id"],
        "token_id": token_id,
        "contract_address": contract_address,
        "from_wallet": from_wallet,
        "to_wallet": to_wallet,
        "from_user_id": from_user,
        "to_user_id": to_user,
        "tx_hash": tx_hash,
        "status": "processed",
        "created_at": now(),
    }
    await db[TRANSFERS].insert_one(dict(transfer))
    logger.info("NFT %s transferred %s -> %s (user %s -> %s)",
                token_id, from_wallet, to_wallet, from_user, to_user)
    return {"nft_id": nft["id"], "to_user_id": to_user, "status": new_status}


async def otc_transfer_holder(*, nft_id: str, to_user_id: str,
                              to_wallet: Optional[str] = None,
                              tx_hash: Optional[str] = None,
                              from_user_id: Optional[str] = None,
                              source: str = "otc_lumen_guarantor") -> dict:
    """Manager-confirmed (off-chain / OTC) ownership transfer.

    Unlike `process_nft_transfer` (driven by an on-chain Transfer event keyed on
    token_id+wallet), this re-points the NFT holder to an explicit LUMEN user_id
    — the model where LUMEN acts as escrow/guarantor for an OTC deal. It writes
    the SAME `lumen_nft_transfers` audit row so the transfer history is uniform,
    and leaves the NFT status `transferred` so future dividend snapshots route to
    the new holder while past distributions stay immutable.
    """
    nft = await db[NFTS].find_one({"id": nft_id})
    if not nft:
        raise HTTPException(404, "NFT not found for OTC transfer")
    if nft.get("frozen") and source != "dispute_resolution":
        raise HTTPException(
            409, "NFT is frozen (under dispute) — resolve the dispute before transferring")
    old_user = nft.get("current_holder_user_id")
    old_wallet = nft.get("current_wallet")
    # Prefer the buyer's verified primary wallet when not explicitly supplied.
    to_wallet_l = (to_wallet or "").lower() or None
    if to_wallet_l is None and to_user_id:
        pw = await primary_wallet(to_user_id)
        to_wallet_l = (pw.get("address") if pw else None)
    await db[NFTS].update_one({"id": nft_id}, {"$set": {
        "current_holder_user_id": to_user_id,
        "current_wallet": to_wallet_l,
        "status": NFT_TRANSFERRED,
        "last_transfer_tx": tx_hash,
        "updated_at": now(),
    }})
    transfer = {
        "id": new_id("nfttr"),
        "pool_id": nft["pool_id"],
        "token_id": nft.get("token_id"),
        "contract_address": nft.get("contract_address"),
        "from_wallet": old_wallet,
        "to_wallet": to_wallet_l,
        "from_user_id": from_user_id or old_user,
        "to_user_id": to_user_id,
        "tx_hash": tx_hash,
        "source": source,
        "status": "processed",
        "created_at": now(),
    }
    await db[TRANSFERS].insert_one(dict(transfer))
    logger.info("OTC NFT %s holder %s -> %s (source=%s)",
                nft_id, old_user, to_user_id, source)
    return {"nft_id": nft_id, "from_user_id": old_user,
            "to_user_id": to_user_id, "to_wallet": to_wallet_l,
            "transfer_id": transfer["id"]}


@router.get("/admin/nft-registry/transfers")
async def admin_list_transfers(_=Depends(require_admin)):
    rows = await db[TRANSFERS].find({}).sort("created_at", -1).to_list(500)
    return {"transfers": [ser(t) for t in rows]}


# ── NFT Freeze (safety net: dispute / recovery lock the token) ─────────────
async def freeze_nft(nft_id: str, *, reason: str, by: str, ref: str = "") -> dict:
    """Lock an NFT certificate so it cannot be listed, sold or holder-transferred.
    Used when an OTC deal is disputed or a wallet-recovery is pending."""
    nft = await db[NFTS].find_one({"id": nft_id})
    if not nft:
        return {"ok": False, "error": "nft_not_found"}
    await db[NFTS].update_one({"id": nft_id}, {"$set": {
        "frozen": True, "frozen_reason": reason, "frozen_by": by,
        "frozen_ref": ref, "frozen_at": now(), "updated_at": now()}})
    logger.info("NFT %s FROZEN (reason=%s by=%s ref=%s)", nft_id, reason, by, ref)
    return {"ok": True, "nft_id": nft_id, "frozen": True}


async def unfreeze_nft(nft_id: str, *, by: str, note: str = "") -> dict:
    nft = await db[NFTS].find_one({"id": nft_id})
    if not nft:
        return {"ok": False, "error": "nft_not_found"}
    await db[NFTS].update_one({"id": nft_id}, {"$set": {
        "frozen": False, "unfrozen_by": by, "unfrozen_note": note,
        "unfrozen_at": now(), "updated_at": now()},
        "$unset": {"frozen_reason": "", "frozen_ref": ""}})
    logger.info("NFT %s UNFROZEN (by=%s)", nft_id, by)
    return {"ok": True, "nft_id": nft_id, "frozen": False}


# ── Holder snapshot (used by distribution-by-NFT-holder) ──────────────────
async def take_holder_snapshot(pool_id: str, ref_id: str) -> List[dict]:
    """Snapshot current NFT holders for a pool. Returns rows used to distribute.
    Falls back to allocations only if NO NFTs exist (legacy pools)."""
    nfts = await db[NFTS].find({"pool_id": pool_id, "active": True}).to_list(100000)
    snap_at = now()
    rows = []
    if nfts:
        for n in nfts:
            rows.append({
                "id": new_id("snap"),
                "pool_id": pool_id,
                "ref_id": ref_id,
                "snapshot_at": snap_at,
                "token_id": n.get("token_id"),
                "contract_address": n.get("contract_address"),
                "allocation_id": n.get("allocation_id"),
                "holder_wallet": n.get("current_wallet"),
                "holder_user_id": n.get("current_holder_user_id"),
                "units": int(n.get("units") or 0),
            })
        if rows:
            await db[SNAPSHOTS].insert_many([dict(r) for r in rows])
    return rows


@router.get("/admin/nft-registry/snapshots")
async def admin_list_snapshots(_=Depends(require_admin)):
    rows = await db[SNAPSHOTS].find({}).sort("snapshot_at", -1).to_list(1000)
    return {"snapshots": [ser(s) for s in rows]}


async def check_nft_invariants(pool_id: str) -> dict:
    """NFT ownership invariants for a pool (the fixed hybrid-RWA rules)."""
    pool = await db["lumen_pools"].find_one({"id": pool_id})
    nfts = await db[NFTS].find({"pool_id": pool_id, "active": True}).to_list(100000)
    allocs = await db["lumen_pool_allocations"].find(
        {"pool_id": pool_id, "units": {"$gt": 0}}).to_list(100000)
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    issued = int((pool or {}).get("issued_units") or 0)
    nft_units = sum(int(n.get("units") or 0) for n in nfts)
    add("sum_nft_units_eq_issued_units", nft_units == issued, f"{nft_units} vs {issued}")
    add("one_active_nft_per_allocation", len(nfts) == len(allocs), f"{len(nfts)} nfts / {len(allocs)} allocs")
    blocked = [n for n in nfts if n.get("current_holder_user_id") is None]
    add("unlinked_holders_flagged", all(n.get("status") == NFT_HOLDER_UNLINKED for n in blocked),
        f"{len(blocked)} unlinked")
    # blocked NFTs must not have credited distributions
    bad = 0
    for n in blocked:
        cnt = await db["lumen_revenue_distributions"].count_documents(
            {"token_id": n.get("token_id"), "status": "credited"})
        bad += cnt
    add("unlinked_wallets_no_credited_payout", bad == 0, f"{bad} credited to unlinked")
    passed = sum(1 for c in checks if c["passed"])
    return {"pool_id": pool_id, "all_passed": passed == len(checks),
            "counts": {"passed": passed, "total": len(checks)}, "checks": checks}


@router.get("/admin/nft-registry/invariants/{pool_id}")
async def admin_nft_invariants(pool_id: str, _=Depends(require_admin)):
    return await check_nft_invariants(pool_id)


# ═══════════════════════════════════════════════════════════════════════════
# H2.9 — Admin Crypto OS  (operational center for managers)
# ═══════════════════════════════════════════════════════════════════════════
DISTS = "lumen_revenue_distributions"
OTC_LISTINGS = "lumen_otc_listings"
OTC_DEALS = "lumen_otc_deals"

_OTC_DEAL_OPEN = ["payment_pending", "payment_confirmed", "nft_transfer_pending"]


@router.get("/admin/web3/overview")
async def admin_web3_overview(_=Depends(require_admin)):
    """Single operational dashboard for the Crypto OS — all the counters a
    manager needs the moment real OTC trades start."""
    async def w(q):
        return await db[WALLETS].count_documents(q)

    async def n(q):
        return await db[NFTS].count_documents(q)

    async def d(q):
        return await db[OTC_DEALS].count_documents(q)

    blocked_rows = await db[DISTS].find(
        {"status": "claimable_pending_wallet_link"}).to_list(100000)
    blocked_total = round(sum(float(r.get("gross_amount") or 0) for r in blocked_rows), 2)

    return {
        "wallets": {
            "connected": await w({"verified": True, "disabled": {"$ne": True}}),
            "disabled": await w({"disabled": True}),
            "total": await w({}),
        },
        "nfts": {
            "minted": await n({"status": NFT_MINTED}),
            "pending_mint": await n({"status": NFT_PENDING_MINT}),
            "pending_wallet": await n({"status": NFT_PENDING_WALLET}),
            "transferred": await n({"status": NFT_TRANSFERRED}),
            "unlinked": await n({"status": NFT_HOLDER_UNLINKED}),
            "burned": await n({"status": NFT_BURNED}),
            "total": await n({}),
        },
        "otc": {
            "listings_active": await db[OTC_LISTINGS].count_documents({"status": "active"}),
            "deals_open": await d({"status": {"$in": _OTC_DEAL_OPEN}}),
            "awaiting_payment": await d({"status": "payment_pending"}),
            "pending_transfer": await d({"status": "nft_transfer_pending"}),
            "completed": await d({"status": "completed"}),
            "disputed": await d({"status": "disputed"}),
        },
        "blocked_payouts": {
            "count": len(blocked_rows),
            "total_usd": blocked_total,
        },
        "events_total": await db[EVENTS].count_documents({}),
    }


@router.get("/admin/web3/blocked-payouts")
async def admin_blocked_payouts(_=Depends(require_admin)):
    """Distributions parked because the NFT holder's wallet isn't linked to a
    LUMEN user. The money is NOT lost — it waits for the holder to link a wallet."""
    rows = await db[DISTS].find(
        {"status": "claimable_pending_wallet_link"}).sort("created_at", -1).to_list(2000)
    out = []
    for r in rows:
        nft = None
        if r.get("token_id"):
            nft = await db[NFTS].find_one({"token_id": r.get("token_id")})
        out.append({
            "id": r.get("id"),
            "pool_id": r.get("pool_id"),
            "asset_id": r.get("asset_id"),
            "token_id": r.get("token_id"),
            "current_wallet": (nft or {}).get("current_wallet") or r.get("holder_wallet"),
            "current_holder_user_id": (nft or {}).get("current_holder_user_id"),
            "amount_usd": round(float(r.get("gross_amount") or 0), 2),
            "currency": r.get("currency"),
            "reason": "wallet_not_linked",
            "created_at": _iso(r.get("created_at")),
        })
    total = round(sum(o["amount_usd"] for o in out), 2)
    return {"blocked_payouts": out, "count": len(out), "total_usd": total}


class AdminWalletActionRequest(BaseModel):
    wallet_id: str


@router.post("/admin/web3/wallet/disable")
async def admin_disable_wallet(body: AdminWalletActionRequest, _=Depends(require_admin)):
    w = await db[WALLETS].find_one({"id": body.wallet_id})
    if not w:
        raise HTTPException(404, "Wallet not found")
    await db[WALLETS].update_one({"id": body.wallet_id}, {"$set": {
        "disabled": True, "verified": False, "primary": False, "updated_at": now()}})
    return {"ok": True, "wallet_id": body.wallet_id, "disabled": True}


@router.post("/admin/web3/wallet/enable")
async def admin_enable_wallet(body: AdminWalletActionRequest, _=Depends(require_admin)):
    w = await db[WALLETS].find_one({"id": body.wallet_id})
    if not w:
        raise HTTPException(404, "Wallet not found")
    await db[WALLETS].update_one({"id": body.wallet_id}, {"$set": {
        "disabled": False, "verified": True, "updated_at": now()}})
    return {"ok": True, "wallet_id": body.wallet_id, "disabled": False}


@router.post("/admin/web3/wallet/make-primary")
async def admin_make_primary(body: AdminWalletActionRequest, _=Depends(require_admin)):
    w = await db[WALLETS].find_one({"id": body.wallet_id})
    if not w:
        raise HTTPException(404, "Wallet not found")
    await db[WALLETS].update_many({"user_id": w["user_id"]}, {"$set": {"primary": False}})
    await db[WALLETS].update_one({"id": body.wallet_id}, {"$set": {
        "primary": True, "updated_at": now()}})
    return {"ok": True, "wallet_id": body.wallet_id, "primary": True}

# ═══════════════════════════════════════════════════════════════════════════
# H2.12 — Wallet Recovery (safety net: lost / changed wallet)
# ═══════════════════════════════════════════════════════════════════════════
# Flow:  Investor → (KYC verified) → Recovery request → manager review →
#        old wallets revoked → new wallet verified (admin-attested) →
#        NFTs reassigned to the new wallet → append-only audit record.
#
# This is the piece that "kills projects" if missing: a real-asset investor who
# loses a seed phrase or changes phone must NOT lose their NFT ownership, their
# dividends or their ability to use OTC.
REC_PENDING = "pending"
REC_APPROVED = "approved"
REC_REJECTED = "rejected"
REC_OPEN = {REC_PENDING}


async def _user_doc(user_id: str) -> dict:
    return await db["users"].find_one({"user_id": user_id}) or {}


def _kyc_approved(u: dict) -> bool:
    return (u.get("kyc_status") or "").lower() == "approved"


class RecoveryRequestBody(BaseModel):
    reason: str = Field(default="lost_wallet")
    lost_address: Optional[str] = None
    new_address: Optional[str] = None
    note: str = ""


@router.post("/investor/web3/recovery/request")
async def request_wallet_recovery(body: RecoveryRequestBody, user=Depends(require_user)):
    """Investor reports a lost/changed wallet. We FREEZE their NFTs immediately so
    nobody can move ownership while the recovery is being reviewed."""
    uid = user["id"]
    existing = await db[RECOVERIES].find_one({"user_id": uid, "status": {"$in": list(REC_OPEN)}})
    if existing:
        raise HTTPException(409, "You already have a pending recovery request")
    rec = {
        "id": new_id("wrec"),
        "user_id": uid,
        "user_email": user.get("email"),
        "reason": body.reason,
        "lost_address": (body.lost_address or "").lower() or None,
        "new_address": (body.new_address or "").lower() or None,
        "note": body.note,
        "status": REC_PENDING,
        "frozen_nft_ids": [],
        "created_at": now(),
        "updated_at": now(),
    }
    # Freeze all of the investor's active NFTs while the request is open.
    held = await db[NFTS].find({"current_holder_user_id": uid, "active": True}).to_list(100000)
    frozen_ids = []
    for n in held:
        await freeze_nft(n["id"], reason="wallet_recovery", by=uid, ref=rec["id"])
        frozen_ids.append(n["id"])
    rec["frozen_nft_ids"] = frozen_ids
    await db[RECOVERIES].insert_one(dict(rec))
    logger.info("Wallet recovery %s requested by %s (froze %d NFT)",
                rec["id"], uid, len(frozen_ids))
    return {"ok": True, "recovery": ser(rec), "frozen_nfts": len(frozen_ids)}


@router.get("/investor/web3/recovery/my")
async def my_recovery_requests(user=Depends(require_user)):
    rows = await db[RECOVERIES].find({"user_id": user["id"]}).sort("created_at", -1).to_list(100)
    return {"recoveries": [ser(r) for r in rows]}


@router.get("/admin/web3/recoveries")
async def admin_list_recoveries(status: Optional[str] = None, _=Depends(require_admin)):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows = await db[RECOVERIES].find(q).sort("created_at", -1).to_list(1000)
    out = []
    for r in rows:
        u = await _user_doc(r["user_id"])
        e = ser(r)
        e["kyc_status"] = u.get("kyc_status")
        e["kyc_ok"] = _kyc_approved(u)
        e["user_name"] = u.get("name")
        out.append(e)
    summary = {s: await db[RECOVERIES].count_documents({"status": s})
               for s in (REC_PENDING, REC_APPROVED, REC_REJECTED)}
    return {"summary": summary, "recoveries": out}


class ApproveRecoveryBody(BaseModel):
    new_address: str
    chain: str = "ethereum"
    note: str = ""


@router.post("/admin/web3/recovery/{recovery_id}/approve")
async def approve_wallet_recovery(recovery_id: str, body: ApproveRecoveryBody,
                                  staff=Depends(require_admin)):
    rec = await db[RECOVERIES].find_one({"id": recovery_id})
    if not rec:
        raise HTTPException(404, "Recovery request not found")
    if rec["status"] != REC_PENDING:
        raise HTTPException(409, f"Recovery already {rec['status']}")
    uid = rec["user_id"]
    u = await _user_doc(uid)
    if not _kyc_approved(u):
        raise HTTPException(403, "KYC must be approved before a wallet recovery can be executed")
    new_addr = (body.new_address or "").lower()
    if not new_addr.startswith("0x") or len(new_addr) < 10:
        raise HTTPException(400, "new_address is not a valid wallet address")
    # The new wallet must not belong to a DIFFERENT verified user.
    clash = await db[WALLETS].find_one(
        {"address": new_addr, "verified": True, "user_id": {"$ne": uid}})
    if clash:
        raise HTTPException(409, "Target wallet is already verified by another user")

    actor = staff.get("id") or staff.get("user_id")

    # 1) Revoke ALL old wallets of this user.
    old = await db[WALLETS].find({"user_id": uid}).to_list(200)
    old_addrs = [(w.get("address") or "").lower() for w in old]
    await db[WALLETS].update_many({"user_id": uid}, {"$set": {
        "verified": False, "disabled": True, "primary": False,
        "revoked_by_recovery": recovery_id, "updated_at": now()}})

    # 2) Register + verify the new wallet (admin-attested, since the user lost
    #    access to the old one — identity is proven by KYC on file).
    existing_new = await db[WALLETS].find_one({"user_id": uid, "address": new_addr})
    if existing_new:
        await db[WALLETS].update_one({"id": existing_new["id"]}, {"$set": {
            "verified": True, "disabled": False, "primary": True,
            "chain": body.chain.lower(), "source": "recovery",
            "verified_at": now(), "updated_at": now()},
            "$unset": {"revoked_by_recovery": ""}})
        new_wallet_id = existing_new["id"]
    else:
        new_wallet_id = new_id("w")
        await db[WALLETS].insert_one({
            "id": new_wallet_id, "user_id": uid, "chain": body.chain.lower(),
            "address": new_addr, "verified": True, "disabled": False, "primary": True,
            "source": "recovery", "recovery_id": recovery_id,
            "created_at": now(), "verified_at": now(), "updated_at": now()})

    # 3) Reassign every NFT the user holds to the new wallet + unfreeze.
    held = await db[NFTS].find({"current_holder_user_id": uid, "active": True}).to_list(100000)
    reassigned = 0
    for n in held:
        await db[NFTS].update_one({"id": n["id"]}, {"$set": {
            "current_wallet": new_addr, "updated_at": now()},
            "$unset": {"frozen": "", "frozen_reason": "", "frozen_ref": ""}})
        await db[TRANSFERS].insert_one({
            "id": new_id("nfttr"), "pool_id": n.get("pool_id"), "token_id": n.get("token_id"),
            "contract_address": n.get("contract_address"),
            "from_wallet": n.get("current_wallet"), "to_wallet": new_addr,
            "from_user_id": uid, "to_user_id": uid, "tx_hash": None,
            "source": "wallet_recovery", "recovery_id": recovery_id,
            "status": "processed", "created_at": now()})
        reassigned += 1

    # 4) Append-only audit record.
    audit = {
        "id": new_id("wraud"), "recovery_id": recovery_id, "user_id": uid,
        "action": "recovery_approved", "actor": actor,
        "old_addresses": old_addrs, "new_address": new_addr,
        "nfts_reassigned": reassigned, "note": body.note, "at": now(),
    }
    await db["lumen_wallet_recovery_audit"].insert_one(dict(audit))

    await db[RECOVERIES].update_one({"id": recovery_id}, {"$set": {
        "status": REC_APPROVED, "new_address": new_addr, "new_wallet_id": new_wallet_id,
        "old_addresses": old_addrs, "nfts_reassigned": reassigned,
        "approved_by": actor, "approved_at": now(), "updated_at": now()}})
    logger.info("Wallet recovery %s APPROVED — user %s → %s (reassigned %d NFT)",
                recovery_id, uid, new_addr, reassigned)

    # 5) Release any payouts that were blocked pending a wallet link.
    try:
        await _release_blocked_for_user(uid)
    except Exception as e:  # pragma: no cover
        logger.warning("recovery release_blocked failed: %s", e)

    return {"ok": True, "recovery_id": recovery_id, "status": REC_APPROVED,
            "new_wallet_id": new_wallet_id, "old_addresses": old_addrs,
            "nfts_reassigned": reassigned}


class RejectRecoveryBody(BaseModel):
    reason: str = ""


@router.post("/admin/web3/recovery/{recovery_id}/reject")
async def reject_wallet_recovery(recovery_id: str, body: RejectRecoveryBody = RejectRecoveryBody(),
                                 staff=Depends(require_admin)):
    rec = await db[RECOVERIES].find_one({"id": recovery_id})
    if not rec:
        raise HTTPException(404, "Recovery request not found")
    if rec["status"] != REC_PENDING:
        raise HTTPException(409, f"Recovery already {rec['status']}")
    actor = staff.get("id") or staff.get("user_id")
    # Unfreeze the NFTs we froze on request.
    for nid in rec.get("frozen_nft_ids", []):
        await unfreeze_nft(nid, by=actor, note=f"recovery_rejected:{recovery_id}")
    await db[RECOVERIES].update_one({"id": recovery_id}, {"$set": {
        "status": REC_REJECTED, "reject_reason": body.reason,
        "rejected_by": actor, "rejected_at": now(), "updated_at": now()}})
    await db["lumen_wallet_recovery_audit"].insert_one({
        "id": new_id("wraud"), "recovery_id": recovery_id, "user_id": rec["user_id"],
        "action": "recovery_rejected", "actor": actor, "note": body.reason, "at": now()})
    return {"ok": True, "recovery_id": recovery_id, "status": REC_REJECTED}




async def ensure_indexes() -> None:
    try:
        await db[WALLETS].create_index("id", unique=True)
        await db[WALLETS].create_index([("address", 1), ("verified", 1)])
        await db[WALLETS].create_index([("user_id", 1)])
        await db[NFTS].create_index("id", unique=True)
        await db[NFTS].create_index([("pool_id", 1), ("allocation_id", 1)])
        await db[NFTS].create_index([("current_holder_user_id", 1), ("active", 1)])
        await db[NFTS].create_index([("token_id", 1), ("contract_address", 1)])
        await db[EVENTS].create_index("dedupe_key", unique=True)
        await db[TRANSFERS].create_index("id", unique=True)
        await db[SNAPSHOTS].create_index([("pool_id", 1), ("ref_id", 1)])
        await db[RECOVERIES].create_index("id", unique=True)
        await db[RECOVERIES].create_index([("user_id", 1), ("status", 1)])
    except Exception as e:  # pragma: no cover
        logger.warning("crypto_os index ensure failed: %s", e)


async def boot() -> None:
    await ensure_indexes()
    logger.info("Crypto OS (wallets/NFT/events) ready · provider=%s",
                get_provider().name)


__all__ = ["router", "boot", "mirror_nfts_for_pool", "take_holder_snapshot",
           "process_nft_transfer", "otc_transfer_holder", "ingest_event",
           "wallet_owner", "primary_wallet", "freeze_nft", "unfreeze_nft",
           "NFTS", "WALLETS", "TRANSFERS",
           "NFT_MINTED", "NFT_TRANSFERRED", "NFT_HOLDER_UNLINKED"]
