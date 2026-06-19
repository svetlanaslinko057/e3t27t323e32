"""
LUMEN — Capital Pool OS
=======================

The missing business entity between **Funding** and **Ownership**: an
asset-specific capital pool that behaves like a "банка" (jar) per object / SPV /
round. Off-chain ledger — no smart contract. Money physically sits on the
company/SPV bank account; LUMEN keeps the internal registry of shares (units).

Flow
----
    Investor → Pool Contribution (gets IBAN + reference)
            → bank transfer → Admin/reconciliation confirms
            → Units issued + Allocation + Pool ledger
            → Pool funded → Certificates issued → Release to seller/owner
            → Asset operating → Revenue event (gross − expenses − reserve)
            → Pro-rata distribution by units → Investor pool balance
            → Withdrawal request → Admin payout → Reconciled

Hard invariants (also checked by `pool_os_contract.py` and the
`GET /admin/pools/{id}/invariants` endpoint):

  I1  Σ confirmed_contributions.amount      = pool.confirmed_amount
  I2  Σ allocation.units                    = pool.issued_units
  I3  pool.available_cash = confirmed_amount − released_to_seller − refunded
  I4  Σ distribution.gross_amount (event)   = event.net_distributable  (rounding → largest holder)
  I5  investor_distribution = units / issued_units × net_distributable
  I6  issued_units ≤ total_units            (oversell protection)
  I7  pool_balance.available = Σ credited_distributions − Σ (paid + reserved withdrawals)

This module is intentionally **self-contained & multi-currency** (EUR-native);
it does NOT touch the legacy UAH wallet/dividend invariants. The two balance
systems can be unified later if desired.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _now, _iso, _strip_mongo
from lumen_pool_cash import (
    CashType, record_movement, build_pool_cash_audit,
    build_investor_balance_audit, list_pool_movements,
)

logger = logging.getLogger("lumen.pool_os")
router = APIRouter(prefix="/api", tags=["Lumen Pool OS"])

# Any authenticated user can act as an investor.
require_user = get_current_user

# ── Collections ────────────────────────────────────────────────────────────
C_POOLS = "lumen_pools"
C_CONTRIB = "lumen_pool_contributions"
C_LEDGER = "lumen_pool_ledger"
C_ALLOC = "lumen_pool_allocations"
C_RELEASE = "lumen_pool_releases"
C_CERT = "lumen_pool_certificates"
C_REVENUE = "lumen_revenue_events"
C_DIST = "lumen_revenue_distributions"
C_BALANCE = "lumen_pool_balances"
C_WITHDRAW = "lumen_pool_withdrawals"


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class PoolStatus(str, Enum):
    draft = "draft"
    fundraising = "fundraising"
    funded = "funded"
    release_pending = "release_pending"
    released_to_seller = "released_to_seller"
    operating = "operating"
    closed = "closed"
    cancelled = "cancelled"


class ContributionStatus(str, Enum):
    pending_payment = "pending_payment"
    matched = "matched"
    confirmed = "confirmed"
    cancelled = "cancelled"
    refunded = "refunded"


class PoolLedgerKind(str, Enum):
    contribution_confirmed = "contribution_confirmed"
    seller_release = "seller_release"
    platform_fee = "platform_fee"
    reserve_set_aside = "reserve_set_aside"
    refund = "refund"
    revenue_received = "revenue_received"
    expense_paid = "expense_paid"
    distribution_generated = "distribution_generated"


class RevenueStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    distributed = "distributed"
    cancelled = "cancelled"


class WithdrawalStatus(str, Enum):
    requested = "requested"
    approved = "approved"
    paid = "paid"
    reconciled = "reconciled"
    rejected = "rejected"
    cancelled = "cancelled"


WITHDRAWAL_RESERVED = {"requested", "approved"}
WITHDRAWAL_SETTLED = {"paid", "reconciled"}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def r2(x: Any) -> float:
    return round(float(x or 0), 2)


def contribution_reference(pool_id: str) -> str:
    return f"LUMEN-{pool_id[-6:].upper()}-{uuid4().hex[:6].upper()}"


_DATE_FIELDS = ("created_at", "updated_at", "opened_at", "confirmed_at",
                "distributed_at", "issued_at", "received_at", "approved_at",
                "paid_at", "reconciled_at", "released_at", "fx_locked_at")


def ser(doc: Optional[dict]) -> Optional[dict]:
    """JSON-safe public projection (datetime → iso, strip _id)."""
    if doc is None:
        return None
    doc = _strip_mongo(dict(doc))
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = _iso(v)
    return doc


def investor_id_of(user: dict) -> str:
    return user.get("id") or user.get("user_id")


async def append_pool_ledger(pool_id: str, kind: str, amount: float,
                              currency: str, debit: str, credit: str,
                              ref_id: Optional[str] = None,
                              meta: Optional[dict] = None) -> dict:
    entry = {
        "id": new_id("pledger"),
        "pool_id": pool_id,
        "kind": kind,
        "amount": r2(amount),
        "currency": currency,
        "debit": debit,
        "credit": credit,
        "ref_id": ref_id,
        "meta": meta or {},
        "created_at": now(),
    }
    await db[C_LEDGER].insert_one(dict(entry))
    return entry


async def _sum(coll: str, match: dict, field: str) -> float:
    cur = db[coll].aggregate([
        {"$match": match},
        {"$group": {"_id": None, "v": {"$sum": f"${field}"}}},
    ])
    rows = await cur.to_list(1)
    return float(rows[0]["v"]) if rows else 0.0


async def recompute_pool(pool_id: str) -> dict:
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")

    confirmed_amount = await _sum(C_CONTRIB, {"pool_id": pool_id, "status": "confirmed"}, "amount")
    issued_units = await _sum(C_CONTRIB, {"pool_id": pool_id, "status": "confirmed"}, "units")
    released = await _sum(C_LEDGER, {"pool_id": pool_id, "kind": "seller_release"}, "amount")
    # Refunds only count when they actually left the pool (confirmed → refunded),
    # which is exactly when a `refund` ledger entry was written.
    refunded = await _sum(C_LEDGER, {"pool_id": pool_id, "kind": "refund"}, "amount")

    available_cash = r2(confirmed_amount - released - refunded)
    status = pool["status"]
    if status == "fundraising" and confirmed_amount >= pool["target_amount"]:
        status = "funded"

    await db[C_POOLS].update_one(
        {"id": pool_id},
        {"$set": {
            "confirmed_amount": r2(confirmed_amount),
            "issued_units": int(round(issued_units)),
            "released_amount": r2(released),
            "refunded_amount": r2(refunded),
            "available_cash": available_cash,
            # USD-core aliases (H2.1): for USD pools these equal the base amounts.
            "confirmed_usd": r2(confirmed_amount),
            "raised_usd": r2(confirmed_amount),
            "available_cash_usd": available_cash,
            "hard_cap_usd": r2(pool.get("target_amount")),
            "target_amount_usd": r2(pool.get("target_amount")),
            "unit_price_usd": round(float(pool.get("unit_price") or 0), 8),
            "status": status,
            "updated_at": now(),
        }})

    pool = await db[C_POOLS].find_one({"id": pool_id})
    if pool["status"] == "funded":
        await issue_pool_certificates(pool)
        # H2.4 — mirror an NFT ownership certificate per allocation (holder = investor).
        try:
            from lumen_crypto_os import mirror_nfts_for_pool
            await mirror_nfts_for_pool(pool)
        except Exception as _e:
            logger.warning("NFT mirror failed for pool %s: %s", pool_id, _e)
    return pool


async def issue_pool_certificates(pool: dict) -> int:
    """Idempotently issue a unit certificate per investor when a pool is funded."""
    pool_id = pool["id"]
    issued = 0
    allocations = await db[C_ALLOC].find({"pool_id": pool_id, "units": {"$gt": 0}}).to_list(100000)
    issued_units = int(pool.get("issued_units") or 0) or 1
    for a in allocations:
        exists = await db[C_CERT].find_one({"pool_id": pool_id, "investor_id": a["investor_id"]})
        if exists:
            continue
        units = int(a["units"])
        cert = {
            "id": new_id("pcert"),
            "serial": f"PC-{pool_id[-6:].upper()}-{uuid4().hex[:8].upper()}",
            "pool_id": pool_id,
            "asset_id": pool.get("asset_id"),
            "investor_id": a["investor_id"],
            "units": units,
            "ownership_percent": round(units / issued_units * 100, 6),
            "unit_price": pool.get("unit_price"),
            "currency": pool.get("currency"),
            "amount": r2(a.get("amount")),
            "status": "issued",
            "issued_at": now(),
            "created_at": now(),
        }
        await db[C_CERT].insert_one(dict(cert))
        issued += 1
    if issued:
        logger.info("Pool %s: issued %d certificates", pool_id, issued)
    return issued


async def recompute_pool_balance(investor_id: str, currency: str) -> dict:
    credited = await _sum(C_DIST, {"investor_id": investor_id, "currency": currency,
                                   "status": "credited"}, "gross_amount")
    settled = await _sum(C_WITHDRAW, {"investor_id": investor_id, "currency": currency,
                                      "status": {"$in": list(WITHDRAWAL_SETTLED)}}, "amount")
    reserved = await _sum(C_WITHDRAW, {"investor_id": investor_id, "currency": currency,
                                       "status": {"$in": list(WITHDRAWAL_RESERVED)}}, "amount")
    available = r2(credited - settled - reserved)
    doc = {
        "investor_id": investor_id, "currency": currency,
        "credited": r2(credited), "withdrawn": r2(settled),
        "reserved": r2(reserved), "available": available,
        "updated_at": now(),
    }
    await db[C_BALANCE].update_one(
        {"investor_id": investor_id, "currency": currency},
        {"$set": doc, "$setOnInsert": {"id": new_id("pbal"), "created_at": now()}},
        upsert=True)
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# DTOs
# ═══════════════════════════════════════════════════════════════════════════

class CreatePoolRequest(BaseModel):
    asset_id: str
    spv_id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    currency: str = "USD"            # base/settlement currency (H2.1: USD)
    target_amount: float = Field(gt=0)   # denominated in `currency` (USD)
    min_ticket: float = 1000
    total_units: int = Field(default=1_000_000, gt=0)
    platform_fee_bps: int = 0
    reserve_bps: int = 0
    deadline: Optional[datetime] = None


class CreateContributionRequest(BaseModel):
    pool_id: str
    amount: float = Field(gt=0)            # ORIGINAL amount in `currency`
    currency: Optional[str] = None         # original currency; default = pool base
    gateway: Optional[str] = "fiat"        # "fiat" | "crypto" (H2.2)
    wallet_address: Optional[str] = None   # crypto: investor wallet (optional)


class ConfirmContributionRequest(BaseModel):
    provider_ref: str
    bank_reference: str
    received_amount: float = Field(gt=0)
    received_currency: str
    received_at: Optional[datetime] = None


class ReleaseToSellerRequest(BaseModel):
    amount: float = Field(gt=0)
    seller_name: str
    seller_iban: Optional[str] = None
    reason: str = "Asset acquisition payment"


class CreateRevenueEventRequest(BaseModel):
    pool_id: str
    gross_amount: float = Field(gt=0)
    expenses_amount: float = 0
    reserve_amount: float = 0
    tax_amount: float = 0
    original_currency: Optional[str] = None   # default = pool base (USD)
    description: str = "Revenue event"


class WithdrawRequest(BaseModel):
    currency: str = "EUR"
    amount: float = Field(gt=0)
    destination_iban: Optional[str] = None


class PayWithdrawalRequest(BaseModel):
    bank_reference: str
    paid_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════════════
# Admin — pools
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/admin/pools")
async def create_pool(body: CreatePoolRequest, admin=Depends(require_admin)):
    unit_price = body.target_amount / body.total_units
    base_ccy = (body.currency or "USD").upper()
    pool = {
        "id": new_id("pool"),
        "asset_id": body.asset_id,
        "spv_id": body.spv_id,
        "title": body.title,
        "summary": body.summary,
        "currency": base_ccy,
        "base_currency": base_ccy,
        "target_amount": r2(body.target_amount),
        "confirmed_amount": 0.0,
        "available_cash": 0.0,
        "released_amount": 0.0,
        "refunded_amount": 0.0,
        # ── USD-core alias fields (H2.1) — for USD pools these equal base amounts
        "hard_cap_usd": r2(body.target_amount),
        "target_amount_usd": r2(body.target_amount),
        "confirmed_usd": 0.0,
        "raised_usd": 0.0,
        "available_cash_usd": 0.0,
        "unit_price_usd": round(unit_price, 8),
        "min_ticket": r2(body.min_ticket),
        "total_units": int(body.total_units),
        "issued_units": 0,
        "unit_price": round(unit_price, 8),
        "platform_fee_bps": int(body.platform_fee_bps),
        "reserve_bps": int(body.reserve_bps),
        "deadline": body.deadline,
        "status": PoolStatus.draft.value,
        "created_by": investor_id_of(admin),
        "created_at": now(),
        "updated_at": now(),
    }
    await db[C_POOLS].insert_one(dict(pool))
    return {"ok": True, "pool": ser(pool)}


@router.post("/admin/pools/{pool_id}/open")
async def open_pool(pool_id: str, admin=Depends(require_admin)):
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    if pool["status"] != "draft":
        raise HTTPException(409, "Only a draft pool can be opened")
    await db[C_POOLS].update_one({"id": pool_id},
        {"$set": {"status": "fundraising", "opened_at": now(), "updated_at": now()}})
    return {"ok": True, "pool": ser(await db[C_POOLS].find_one({"id": pool_id}))}


@router.post("/admin/pools/{pool_id}/mark-operating")
async def mark_operating(pool_id: str, admin=Depends(require_admin)):
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    if pool["status"] not in ("released_to_seller", "funded"):
        raise HTTPException(409, "Pool must be released_to_seller/funded to start operating")
    await db[C_POOLS].update_one({"id": pool_id},
        {"$set": {"status": "operating", "updated_at": now()}})
    return {"ok": True, "pool": ser(await db[C_POOLS].find_one({"id": pool_id}))}


@router.post("/admin/pools/{pool_id}/release-to-seller")
async def release_to_seller(pool_id: str, body: ReleaseToSellerRequest,
                            admin=Depends(require_admin)):
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    if pool["status"] not in ("funded", "release_pending", "released_to_seller", "operating"):
        raise HTTPException(409, "Pool is not ready for release")
    if r2(body.amount) > r2(pool.get("available_cash")):
        raise HTTPException(409, "Insufficient pool cash")
    release = {
        "id": new_id("release"),
        "pool_id": pool_id,
        "amount": r2(body.amount),
        "currency": pool["currency"],
        "seller_name": body.seller_name,
        "seller_iban": body.seller_iban,
        "reason": body.reason,
        "status": "pending_bank_transfer",
        "created_by": investor_id_of(admin),
        "created_at": now(),
    }
    await db[C_RELEASE].insert_one(dict(release))
    await append_pool_ledger(pool_id, PoolLedgerKind.seller_release.value,
                             body.amount, pool["currency"],
                             debit="pool_cash", credit="seller_payable",
                             ref_id=release["id"],
                             meta={"seller_name": body.seller_name})
    await record_movement(db, mtype=CashType.OUTFLOW, amount=body.amount,
                          currency=pool["currency"], pool_id=pool_id,
                          source_kind="seller_release", ref_id=release["id"],
                          description=f"Release to seller: {body.seller_name}")
    await db[C_POOLS].update_one({"id": pool_id},
        {"$set": {"status": "released_to_seller", "released_at": now(), "updated_at": now()}})
    pool = await recompute_pool(pool_id)
    return {"ok": True, "release": ser(release), "pool": ser(pool)}


@router.get("/admin/pools")
async def list_pools(admin=Depends(require_admin)):
    pools = await db[C_POOLS].find({}).sort("created_at", -1).to_list(500)
    return {"items": [ser(p) for p in pools]}


@router.get("/admin/pools/{pool_id}")
async def get_pool_admin(pool_id: str, admin=Depends(require_admin)):
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    contributions = await db[C_CONTRIB].find({"pool_id": pool_id}).sort("created_at", -1).to_list(10000)
    allocations = await db[C_ALLOC].find({"pool_id": pool_id}).to_list(10000)
    ledger = await db[C_LEDGER].find({"pool_id": pool_id}).sort("created_at", -1).to_list(500)
    releases = await db[C_RELEASE].find({"pool_id": pool_id}).sort("created_at", -1).to_list(200)
    revenue = await db[C_REVENUE].find({"pool_id": pool_id}).sort("created_at", -1).to_list(200)
    return {
        "pool": ser(pool),
        "contributions": [ser(x) for x in contributions],
        "allocations": [ser(x) for x in allocations],
        "ledger": [ser(x) for x in ledger],
        "releases": [ser(x) for x in releases],
        "revenue_events": [ser(x) for x in revenue],
    }


@router.get("/admin/pools/{pool_id}/invariants")
async def pool_invariants(pool_id: str, admin=Depends(require_admin)):
    return await check_pool_invariants(pool_id)


@router.get("/admin/pools/{pool_id}/cash-audit")
async def pool_cash_audit(pool_id: str, admin=Depends(require_admin)):
    """Statement A — per-pool cash conservation (IN = OUT + balance) + movement journal."""
    audit = await build_pool_cash_audit(db, pool_id)
    if audit.get("error"):
        raise HTTPException(404, "Pool not found")
    audit["movements"] = await list_pool_movements(db, pool_id)
    return audit


@router.get("/admin/pool-cash-audit")
async def global_balance_audit(admin=Depends(require_admin)):
    """Statement B — platform-wide investor-balance conservation."""
    return await build_investor_balance_audit(db)


# ═══════════════════════════════════════════════════════════════════════════
# Admin — contribution reconciliation
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/admin/pool-contributions/{contribution_id}/confirm")
async def confirm_contribution(contribution_id: str,
                               body: ConfirmContributionRequest,
                               admin=Depends(require_admin)):
    contribution = await db[C_CONTRIB].find_one({"id": contribution_id})
    if not contribution:
        raise HTTPException(404, "Contribution not found")
    if contribution["status"] != "pending_payment":
        raise HTTPException(409, "Contribution is not pending payment")
    pool = await db[C_POOLS].find_one({"id": contribution["pool_id"]})
    if not pool:
        raise HTTPException(404, "Pool not found")
    base_ccy = (pool.get("base_currency") or pool.get("currency") or "USD").upper()
    orig_ccy = (contribution.get("original_currency") or base_ccy).upper()
    amount_base = r2(contribution["amount"])           # pool base (USD)
    amount_usd = r2(contribution.get("amount_usd") or amount_base)

    # Reconciliation: the bank confirms the actual received amount, either in the
    # investor's original currency or in the pool base currency.
    rc = (body.received_currency or "").upper()
    if rc == orig_ccy:
        if r2(body.received_amount) != r2(contribution.get("original_amount", amount_base)):
            raise HTTPException(400, "Received amount mismatch")
    elif rc == base_ccy:
        if r2(body.received_amount) != amount_base:
            raise HTTPException(400, "Received amount mismatch")
    else:
        raise HTTPException(400, "Received currency mismatch")

    # ── Unified hard-cap guard (USD/base) — all gateways bleed into one cap ──
    if r2(pool.get("confirmed_amount")) + amount_base > r2(pool.get("target_amount")) + 0.01:
        raise HTTPException(409, "Pool hard cap exceeded")

    units = int(round(amount_base / pool["unit_price"]))
    if pool["issued_units"] + units > pool["total_units"]:
        raise HTTPException(409, "Pool oversubscribed (units exceed total_units)")

    # Idempotent state transition guarded on status
    result = await db[C_CONTRIB].update_one(
        {"id": contribution_id, "status": "pending_payment"},
        {"$set": {
            "status": "confirmed",
            "units": units,
            "provider_ref": body.provider_ref,
            "bank_reference": body.bank_reference,
            "confirmed_by": investor_id_of(admin),
            "confirmed_at": body.received_at or now(),
            "updated_at": now(),
        }})
    if result.modified_count != 1:
        raise HTTPException(409, "Contribution already processed")

    await append_pool_ledger(pool["id"], PoolLedgerKind.contribution_confirmed.value,
                             amount_base, base_ccy,
                             debit="bank_cash", credit="pool_cash",
                             ref_id=contribution_id,
                             meta={"investor_id": contribution["investor_id"], "units": units,
                                   "amount_usd": amount_usd,
                                   "original_amount": contribution.get("original_amount"),
                                   "original_currency": orig_ccy})
    await record_movement(db, mtype=CashType.INFLOW, amount=amount_base,
                          currency=base_ccy, pool_id=pool["id"],
                          investor_id=contribution["investor_id"],
                          source_kind="contribution", ref_id=contribution_id,
                          description="Investor contribution confirmed")

    await db[C_ALLOC].update_one(
        {"pool_id": pool["id"], "investor_id": contribution["investor_id"]},
        {"$inc": {"amount": amount_base, "units": units},
         "$set": {"asset_id": pool["asset_id"], "currency": base_ccy, "updated_at": now()},
         "$setOnInsert": {"id": new_id("alloc"), "created_at": now()}},
        upsert=True)

    updated_pool = await recompute_pool(pool["id"])
    return {"ok": True, "units": units, "pool": ser(updated_pool)}


@router.post("/admin/pool-contributions/{contribution_id}/refund")
async def refund_contribution(contribution_id: str, admin=Depends(require_admin)):
    contribution = await db[C_CONTRIB].find_one({"id": contribution_id})
    if not contribution:
        raise HTTPException(404, "Contribution not found")
    if contribution["status"] not in ("pending_payment", "confirmed"):
        raise HTTPException(409, "Only pending/confirmed contributions can be refunded")
    pool = await db[C_POOLS].find_one({"id": contribution["pool_id"]})
    was_confirmed = contribution["status"] == "confirmed"
    await db[C_CONTRIB].update_one({"id": contribution_id},
        {"$set": {"status": "refunded", "refunded_at": now(), "updated_at": now()}})
    if was_confirmed and pool:
        units = int(contribution.get("units") or 0)
        await db[C_ALLOC].update_one(
            {"pool_id": pool["id"], "investor_id": contribution["investor_id"]},
            {"$inc": {"amount": -float(contribution["amount"]), "units": -units},
             "$set": {"updated_at": now()}})
        await append_pool_ledger(pool["id"], PoolLedgerKind.refund.value,
                                 contribution["amount"], pool["currency"],
                                 debit="pool_cash", credit="bank_cash",
                                 ref_id=contribution_id,
                                 meta={"investor_id": contribution["investor_id"]})
        await record_movement(db, mtype=CashType.OUTFLOW, amount=contribution["amount"],
                              currency=pool["currency"], pool_id=pool["id"],
                              investor_id=contribution["investor_id"],
                              source_kind="refund", ref_id=contribution_id,
                              description="Contribution refunded")
        await recompute_pool(pool["id"])
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# Admin — revenue pool
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/admin/revenue-events")
async def create_revenue_event(body: CreateRevenueEventRequest,
                               admin=Depends(require_admin)):
    from lumen_pool_fx import convert_to_usd
    pool = await db[C_POOLS].find_one({"id": body.pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    if int(pool.get("issued_units") or 0) <= 0:
        raise HTTPException(409, "No issued units")

    base_ccy = (pool.get("base_currency") or pool.get("currency") or "USD").upper()
    orig_ccy = (body.original_currency or base_ccy).upper()

    # Convert each leg original → pool base (USD). Identity when orig == base.
    async def to_base(x: float) -> tuple[float, float]:
        if orig_ccy == base_ccy:
            return r2(x), r2(x)
        if base_ccy != "USD":
            raise HTTPException(400, "Cross-currency revenue only supported for USD-base pools")
        fx = await convert_to_usd(x, orig_ccy)
        return fx["amount_usd"], fx["amount_usd"]

    gross_b, gross_usd = await to_base(body.gross_amount)
    exp_b, exp_usd = await to_base(body.expenses_amount)
    res_b, res_usd = await to_base(body.reserve_amount)
    tax_b, tax_usd = await to_base(body.tax_amount)
    net = gross_b - exp_b - res_b - tax_b
    if net <= 0:
        raise HTTPException(400, "Net distributable amount must be positive")

    fx_snapshot = await convert_to_usd(1.0, orig_ccy) if orig_ccy != base_ccy else None
    event = {
        "id": new_id("revenue"),
        "pool_id": pool["id"],
        "asset_id": pool["asset_id"],
        "gross_amount": r2(gross_b),
        "expenses_amount": r2(exp_b),
        "reserve_amount": r2(res_b),
        "tax_amount": r2(tax_b),
        "net_distributable": r2(net),
        "currency": base_ccy,
        # ── USD-core fields (H2.1) ──
        "gross_usd": r2(gross_usd),
        "expenses_usd": r2(exp_usd),
        "reserve_usd": r2(res_usd),
        "tax_usd": r2(tax_usd),
        "net_distributable_usd": r2(gross_usd - exp_usd - res_usd - tax_usd),
        "original_currency": orig_ccy,
        "original_gross_amount": r2(body.gross_amount),
        "fx_rate_to_usd": (fx_snapshot["fx_rate_to_usd"] if fx_snapshot else 1.0),
        "fx_source": (fx_snapshot["fx_source"] if fx_snapshot else "native"),
        "description": body.description,
        "status": RevenueStatus.draft.value,
        "created_by": investor_id_of(admin),
        "created_at": now(),
    }
    await db[C_REVENUE].insert_one(dict(event))
    await append_pool_ledger(pool["id"], PoolLedgerKind.revenue_received.value,
                             gross_b, base_ccy,
                             debit="bank_cash", credit="revenue_pool",
                             ref_id=event["id"])
    # Cash movement journal: REVENUE in, plus EXPENSE/TAX out and RESERVE earmark
    await record_movement(db, mtype=CashType.REVENUE, amount=gross_b,
                          currency=base_ccy, pool_id=pool["id"],
                          source_kind="revenue", ref_id=event["id"],
                          description=body.description)
    if exp_b:
        await record_movement(db, mtype=CashType.OUTFLOW, amount=exp_b,
                              currency=base_ccy, pool_id=pool["id"],
                              source_kind="expense", ref_id=event["id"],
                              description="Operating expenses")
    if tax_b:
        await record_movement(db, mtype=CashType.TAX, amount=tax_b,
                              currency=base_ccy, pool_id=pool["id"],
                              source_kind="tax", ref_id=event["id"],
                              description="Tax withheld on revenue")
    if res_b:
        await record_movement(db, mtype=CashType.RESERVE, amount=res_b,
                              currency=base_ccy, pool_id=pool["id"],
                              source_kind="reserve", ref_id=event["id"],
                              description="Reserve earmarked")
    return {"ok": True, "revenue_event": ser(event)}


@router.post("/admin/revenue-events/{event_id}/distribute")
async def distribute_revenue(event_id: str, admin=Depends(require_admin)):
    event = await db[C_REVENUE].find_one({"id": event_id})
    if not event:
        raise HTTPException(404, "Revenue event not found")
    if event["status"] != "draft":
        raise HTTPException(409, "Revenue event already processed")
    pool = await db[C_POOLS].find_one({"id": event["pool_id"]})
    if not pool:
        raise HTTPException(404, "Pool not found")

    # ── Dividend recipient source = CURRENT NFT holder at snapshot date (H2.7).
    # Backward-compatible: untransferred NFTs keep holder = original investor, so
    # results are identical to allocation-based distribution. Legacy pools without
    # NFTs fall back to allocations.
    from lumen_crypto_os import take_holder_snapshot
    snapshot = await take_holder_snapshot(pool["id"], event["id"])
    if snapshot:
        holders = [{"user_id": s["holder_user_id"], "wallet": s["holder_wallet"],
                    "token_id": s["token_id"], "units": int(s["units"])}
                   for s in snapshot if int(s["units"]) > 0]
        source = "nft_holder_snapshot"
    else:
        allocations = await db[C_ALLOC].find(
            {"pool_id": pool["id"], "units": {"$gt": 0}}).to_list(100000)
        holders = [{"user_id": a["investor_id"], "wallet": None, "token_id": None,
                    "units": int(a["units"])} for a in allocations]
        source = "allocation"
    if not holders:
        raise HTTPException(409, "No allocations to distribute to")

    # Guard: claim the event (idempotency) before writing distribution rows
    claim = await db[C_REVENUE].update_one(
        {"id": event_id, "status": "draft"},
        {"$set": {"status": "distributing", "updated_at": now()}})
    if claim.modified_count != 1:
        raise HTTPException(409, "Revenue event already processed")

    total_units = sum(h["units"] for h in holders)
    net = r2(event["net_distributable"])
    raw = []
    distributed = 0.0
    for h in holders:
        amount = r2(net * (h["units"] / total_units))
        distributed += amount
        raw.append([h, amount])
    diff = r2(net - distributed)
    if diff != 0 and raw:
        largest_i = max(range(len(raw)), key=lambda i: raw[i][0]["units"])
        raw[largest_i][1] = r2(raw[largest_i][1] + diff)

    rows = []
    credited_users = set()
    blocked_total = 0.0
    for holder, amount in raw:
        # Payout safety: NFT held by a wallet not linked to a LUMEN user → parked,
        # NOT lost, until the holder links their wallet.
        blocked = holder["user_id"] is None
        if blocked:
            blocked_total = r2(blocked_total + amount)
        rows.append({
            "id": new_id("dist"),
            "revenue_event_id": event["id"],
            "pool_id": pool["id"],
            "asset_id": pool["asset_id"],
            "investor_id": holder["user_id"],         # None when blocked
            "recipient_user_id": holder["user_id"],
            "holder_wallet": holder["wallet"],
            "token_id": holder["token_id"],
            "units": holder["units"],
            "gross_amount": amount,
            "currency": pool["currency"],
            "status": "claimable_pending_wallet_link" if blocked else "credited",
            "source": source,
            "created_at": now(),
        })
        if not blocked:
            credited_users.add(holder["user_id"])
    if rows:
        await db[C_DIST].insert_many([dict(r) for r in rows])

    await append_pool_ledger(pool["id"], PoolLedgerKind.distribution_generated.value,
                             net, pool["currency"],
                             debit="revenue_pool", credit="investor_balances",
                             ref_id=event["id"], meta={"rows": len(rows), "source": source,
                                                       "blocked_usd": blocked_total})
    await record_movement(db, mtype=CashType.DISTRIBUTION, amount=net,
                          currency=pool["currency"], pool_id=pool["id"],
                          source_kind="distribution", ref_id=event["id"],
                          description=f"Distribution to {len(rows)} holder(s) [{source}]")

    # Materialize per-investor pool balances (credited recipients only)
    for uid in credited_users:
        await recompute_pool_balance(uid, pool["currency"])

    await db[C_REVENUE].update_one({"id": event["id"]},
        {"$set": {"status": "distributed", "distributed_at": now(),
                  "distributed_by": investor_id_of(admin), "updated_at": now()}})
    return {"ok": True, "event_id": event["id"], "distributed_amount": net,
            "rows": len(rows), "source": source,
            "blocked_amount": blocked_total, "blocked_pending_wallet_link": blocked_total > 0}


# ═══════════════════════════════════════════════════════════════════════════
# Admin — withdrawals (payout)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/admin/pool-withdrawals")
async def list_withdrawals(status: Optional[str] = None, admin=Depends(require_admin)):
    q = {"status": status} if status else {}
    items = await db[C_WITHDRAW].find(q).sort("created_at", -1).to_list(1000)
    return {"items": [ser(x) for x in items]}


@router.post("/admin/pool-withdrawals/{wid}/approve")
async def approve_withdrawal(wid: str, admin=Depends(require_admin)):
    w = await db[C_WITHDRAW].find_one({"id": wid})
    if not w:
        raise HTTPException(404, "Withdrawal not found")
    if w["status"] != "requested":
        raise HTTPException(409, "Only requested withdrawals can be approved")
    await db[C_WITHDRAW].update_one({"id": wid},
        {"$set": {"status": "approved", "approved_by": investor_id_of(admin),
                  "approved_at": now(), "updated_at": now()}})
    await recompute_pool_balance(w["investor_id"], w["currency"])
    return {"ok": True, "withdrawal": ser(await db[C_WITHDRAW].find_one({"id": wid}))}


@router.post("/admin/pool-withdrawals/{wid}/pay")
async def pay_withdrawal(wid: str, body: PayWithdrawalRequest, admin=Depends(require_admin)):
    w = await db[C_WITHDRAW].find_one({"id": wid})
    if not w:
        raise HTTPException(404, "Withdrawal not found")
    if w["status"] != "approved":
        raise HTTPException(409, "Only approved withdrawals can be paid")
    await db[C_WITHDRAW].update_one({"id": wid},
        {"$set": {"status": "paid", "bank_reference": body.bank_reference,
                  "paid_by": investor_id_of(admin), "paid_at": body.paid_at or now(),
                  "updated_at": now()}})
    await record_movement(db, mtype=CashType.WITHDRAWAL, amount=w["amount"],
                          currency=w["currency"], investor_id=w["investor_id"],
                          source_kind="withdrawal", ref_id=wid,
                          description="Investor withdrawal paid to bank")
    await recompute_pool_balance(w["investor_id"], w["currency"])
    return {"ok": True, "withdrawal": ser(await db[C_WITHDRAW].find_one({"id": wid}))}


@router.post("/admin/pool-withdrawals/{wid}/reconcile")
async def reconcile_withdrawal(wid: str, admin=Depends(require_admin)):
    w = await db[C_WITHDRAW].find_one({"id": wid})
    if not w:
        raise HTTPException(404, "Withdrawal not found")
    if w["status"] != "paid":
        raise HTTPException(409, "Only paid withdrawals can be reconciled")
    await db[C_WITHDRAW].update_one({"id": wid},
        {"$set": {"status": "reconciled", "reconciled_at": now(), "updated_at": now()}})
    return {"ok": True, "withdrawal": ser(await db[C_WITHDRAW].find_one({"id": wid}))}


# ═══════════════════════════════════════════════════════════════════════════
# Investor — browse, contribute, positions, balance, withdraw
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/pools/gateways")
async def pool_gateways(user=Depends(require_user)):
    """Available contribution gateways (fiat / crypto) — uniform USD view."""
    from lumen_pool_gateways import list_gateways
    return {"gateways": list_gateways()}


@router.get("/investor/pools")
async def browse_pools(user=Depends(require_user)):
    pools = await db[C_POOLS].find(
        {"status": {"$in": ["fundraising", "funded", "operating", "released_to_seller"]}}
    ).sort("created_at", -1).to_list(200)
    out = []
    for p in pools:
        d = ser(p)
        tgt = float(p.get("target_amount") or 0) or 1
        d["progress_percent"] = round(float(p.get("confirmed_amount") or 0) / tgt * 100, 2)
        d["remaining_amount"] = r2(float(p.get("target_amount") or 0) - float(p.get("confirmed_amount") or 0))
        d["investor_count"] = await db[C_ALLOC].count_documents({"pool_id": p["id"], "units": {"$gt": 0}})
        out.append(d)
    return {"items": out}


@router.get("/investor/pools/my")
async def my_positions(user=Depends(require_user)):
    iid = investor_id_of(user)
    allocations = await db[C_ALLOC].find({"investor_id": iid, "units": {"$gt": 0}}).to_list(1000)
    pool_ids = list({a["pool_id"] for a in allocations})
    pools = await db[C_POOLS].find({"id": {"$in": pool_ids}}).to_list(1000)
    pmap = {p["id"]: p for p in pools}
    items = []
    for a in allocations:
        pool = pmap.get(a["pool_id"])
        if not pool:
            continue
        issued = int(pool.get("issued_units") or 0)
        percent = round(int(a["units"]) / issued * 100, 6) if issued else 0
        items.append({
            "pool_id": a["pool_id"],
            "asset_id": a.get("asset_id"),
            "title": pool.get("title"),
            "amount": r2(a.get("amount")),
            "currency": a.get("currency"),
            "units": int(a["units"]),
            "ownership_percent": percent,
            "pool_status": pool.get("status"),
        })
    return {"items": items}


@router.get("/investor/pools/{pool_id}")
async def get_pool_public(pool_id: str, user=Depends(require_user)):
    p = await db[C_POOLS].find_one({"id": pool_id})
    if not p:
        raise HTTPException(404, "Pool not found")
    d = ser(p)
    tgt = float(p.get("target_amount") or 0) or 1
    d["progress_percent"] = round(float(p.get("confirmed_amount") or 0) / tgt * 100, 2)
    d["remaining_amount"] = r2(float(p.get("target_amount") or 0) - float(p.get("confirmed_amount") or 0))
    d["investor_count"] = await db[C_ALLOC].count_documents({"pool_id": pool_id, "units": {"$gt": 0}})
    my = await db[C_ALLOC].find_one({"pool_id": pool_id, "investor_id": investor_id_of(user)})
    d["my_position"] = ser(my) if my else None
    return {"pool": d}


@router.post("/investor/pools/contribute")
async def create_contribution(body: CreateContributionRequest, user=Depends(require_user)):
    from lumen_pool_fx import convert_to_usd
    from lumen_pool_gateways import get_gateway
    pool = await db[C_POOLS].find_one({"id": body.pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    if pool["status"] != "fundraising":
        raise HTTPException(409, "Pool is not fundraising")

    base_ccy = (pool.get("base_currency") or pool.get("currency") or "USD").upper()
    gw = get_gateway(body.gateway)
    # Gateway picks the default currency: crypto → USDT, fiat → pool base.
    orig_ccy = (body.currency or (gw.currencies[0] if gw.kind == "crypto" else base_ccy)).upper()
    if not gw.supports_currency(orig_ccy):
        raise HTTPException(400, f"Gateway '{gw.key}' does not support {orig_ccy}")

    # FX snapshot: original → USD (locked at contribution time). Stablecoins = 1:1.
    fx = await convert_to_usd(body.amount, orig_ccy)
    amount_usd = fx["amount_usd"]
    # Canonical pool-base amount used by all existing money math.
    if orig_ccy == base_ccy:
        amount_base = r2(body.amount)
    elif base_ccy == "USD":
        amount_base = amount_usd
    else:
        raise HTTPException(400, f"Cross-currency contributions are only supported "
                                 f"for USD-base pools (pool base={base_ccy})")

    if amount_base < pool["min_ticket"]:
        raise HTTPException(400, f"Minimum ticket is {pool['min_ticket']} {base_ccy}")

    # Tiered Source-of-Funds gate — evaluated on the USD-equivalent value.
    from lumen_kyc import assert_source_of_funds
    sof = await assert_source_of_funds(user, amount_usd)

    reference = contribution_reference(pool["id"])
    contribution = {
        "id": new_id("contrib"),
        "pool_id": pool["id"],
        "asset_id": pool["asset_id"],
        "investor_id": investor_id_of(user),
        "investor_email": user.get("email"),
        "amount": amount_base,                 # in pool base currency (USD)
        "currency": base_ccy,
        # ── USD-core snapshot (H2.1) ──
        "original_amount": r2(body.amount),
        "original_currency": orig_ccy,
        "fx_rate_to_usd": fx["fx_rate_to_usd"],
        "fx_source": fx["fx_source"],
        "fx_locked_at": fx["fx_locked_at"],
        "amount_usd": amount_usd,
        # ── Gateway (H2.2) ──
        "gateway": gw.key,
        "wallet_address": (body.wallet_address or "").lower() or None,
        "units": 0,
        "reference": reference,
        "status": ContributionStatus.pending_payment.value,
        "created_at": now(),
        "updated_at": now(),
    }
    await db[C_CONTRIB].insert_one(dict(contribution))
    instructions = await gw.create_instructions(pool, contribution)
    return {
        "ok": True,
        "contribution": ser(contribution),
        "sof_policy": sof,
        "gateway": gw.key,
        "fx": {"original_amount": r2(body.amount), "original_currency": orig_ccy,
               "amount_usd": amount_usd, "fx_rate_to_usd": fx["fx_rate_to_usd"],
               "fx_source": fx["fx_source"]},
        "payment_instructions": instructions,
    }


class CryptoDepositEvent(BaseModel):
    contribution_ref: str                  # = contribution id
    tx_hash: str
    wallet_address: str
    amount_token: float
    chain_id: int = 1
    token_address: Optional[str] = None


@router.post("/admin/crypto/webhook/deposit")
async def crypto_deposit_webhook(body: CryptoDepositEvent, admin=Depends(require_admin)):
    """On-chain deposit confirmation for a crypto-gateway contribution. In
    production this is driven by a chain indexer; here it is admin/indexer-gated.
    It records the tx and routes into the SAME Pool-OS confirm core (USD)."""
    contribution = await db[C_CONTRIB].find_one(
        {"id": body.contribution_ref, "gateway": "crypto"})
    if not contribution:
        raise HTTPException(404, "Crypto contribution not found")
    if contribution["status"] != "pending_payment":
        raise HTTPException(409, "Contribution already processed")
    token_ccy = (contribution.get("original_currency") or "USDT").upper()
    if r2(body.amount_token) < r2(contribution.get("original_amount")):
        raise HTTPException(400, "Insufficient token amount deposited")
    await db[C_CONTRIB].update_one({"id": contribution["id"]}, {"$set": {
        "tx_hash": body.tx_hash, "wallet_address": (body.wallet_address or "").lower(),
        "chain_id": body.chain_id, "token_address": body.token_address,
        "updated_at": now(),
    }})
    # Reconcile in the original (token) currency → unified Pool-OS confirm core.
    confirm_body = ConfirmContributionRequest(
        received_amount=r2(contribution.get("original_amount")),
        received_currency=token_ccy,
        provider_ref=body.tx_hash,
        bank_reference=(body.wallet_address or "")[:42])
    return await confirm_contribution(contribution["id"], confirm_body, admin)


@router.get("/investor/pool-balances")
async def my_balances(user=Depends(require_user)):
    iid = investor_id_of(user)
    # Recompute known currencies from distributions
    currencies = await db[C_DIST].distinct("currency", {"investor_id": iid})
    out = []
    for ccy in currencies:
        out.append(ser(await recompute_pool_balance(iid, ccy)))
    return {"items": out}


@router.get("/investor/pool-certificates")
async def my_certificates(user=Depends(require_user)):
    iid = investor_id_of(user)
    certs = await db[C_CERT].find({"investor_id": iid}).sort("issued_at", -1).to_list(1000)
    return {"items": [ser(c) for c in certs]}


@router.post("/investor/pool-withdrawals")
async def request_withdrawal(body: WithdrawRequest, user=Depends(require_user)):
    iid = investor_id_of(user)
    bal = await recompute_pool_balance(iid, body.currency)
    if r2(body.amount) > bal["available"]:
        raise HTTPException(409, f"Insufficient available balance ({bal['available']} {body.currency})")
    w = {
        "id": new_id("pwd"),
        "investor_id": iid,
        "investor_email": user.get("email"),
        "currency": body.currency,
        "amount": r2(body.amount),
        "destination_iban": body.destination_iban,
        "status": WithdrawalStatus.requested.value,
        "created_at": now(),
        "updated_at": now(),
    }
    await db[C_WITHDRAW].insert_one(dict(w))
    await recompute_pool_balance(iid, body.currency)
    return {"ok": True, "withdrawal": ser(w)}


@router.get("/investor/pool-withdrawals")
async def my_withdrawals(user=Depends(require_user)):
    iid = investor_id_of(user)
    items = await db[C_WITHDRAW].find({"investor_id": iid}).sort("created_at", -1).to_list(500)
    return {"items": [ser(x) for x in items]}


# ═══════════════════════════════════════════════════════════════════════════
# Invariants (used by contract harness + admin endpoint)
# ═══════════════════════════════════════════════════════════════════════════

async def check_pool_invariants(pool_id: str) -> dict:
    pool = await db[C_POOLS].find_one({"id": pool_id})
    if not pool:
        raise HTTPException(404, "Pool not found")
    checks = []

    def add(name, ok, detail=None):
        checks.append({"id": name, "passed": bool(ok), "detail": detail})

    confirmed = await _sum(C_CONTRIB, {"pool_id": pool_id, "status": "confirmed"}, "amount")
    add("I1_confirmed_sum", abs(confirmed - float(pool.get("confirmed_amount") or 0)) < 0.01,
        {"sum": r2(confirmed), "pool": pool.get("confirmed_amount")})

    alloc_units = await _sum(C_ALLOC, {"pool_id": pool_id}, "units")
    add("I2_units_sum", int(round(alloc_units)) == int(pool.get("issued_units") or 0),
        {"alloc_units": int(round(alloc_units)), "issued": pool.get("issued_units")})

    released = await _sum(C_LEDGER, {"pool_id": pool_id, "kind": "seller_release"}, "amount")
    refunded = await _sum(C_LEDGER, {"pool_id": pool_id, "kind": "refund"}, "amount")
    expected_cash = r2(confirmed - released - refunded)
    add("I3_available_cash", abs(expected_cash - float(pool.get("available_cash") or 0)) < 0.01,
        {"expected": expected_cash, "pool": pool.get("available_cash")})

    add("I6_units_le_total", int(pool.get("issued_units") or 0) <= int(pool.get("total_units") or 0),
        {"issued": pool.get("issued_units"), "total": pool.get("total_units")})

    # I7: pool cash conservation (IN = OUT + balance, balance ≥ 0)
    cash_audit = await build_pool_cash_audit(db, pool_id)
    add("I7_cash_conservation", bool(cash_audit.get("reconciles")),
        {"in": cash_audit.get("inflows", {}).get("total"),
         "out": cash_audit.get("outflows", {}).get("total"),
         "balance": cash_audit.get("cash_balance")})

    # I4: each distributed revenue event sums to net_distributable
    i4_ok = True
    async for ev in db[C_REVENUE].find({"pool_id": pool_id, "status": "distributed"}):
        s = await _sum(C_DIST, {"revenue_event_id": ev["id"]}, "gross_amount")
        if abs(s - float(ev.get("net_distributable") or 0)) > 0.01:
            i4_ok = False
    add("I4_distribution_sum", i4_ok)

    passed = sum(1 for c in checks if c["passed"])
    return {"pool_id": pool_id, "checks": checks,
            "counts": {"total": len(checks), "passed": passed,
                       "failed": len(checks) - passed},
            "all_passed": passed == len(checks)}


__all__ = ["router", "check_pool_invariants", "recompute_pool"]
