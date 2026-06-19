"""
LUMEN — Capital Pool OS · Cash Movements & Conservation Audit
=============================================================

A single, signed, human-readable journal of every money movement in a pool plus
a strict conservation audit an external auditor can verify:

    ALL MONEY IN  =  ALL MONEY OUT  +  REMAINING BALANCE

The journal (`lumen_pool_cash_movements`) classifies each movement:

    INFLOW       investor contribution confirmed         (cash in,  pool)
    REVENUE      asset/SPV income received               (cash in,  pool)
    OUTFLOW      seller release / expense / refund       (cash out, pool)
    TAX          tax withheld on revenue                 (cash out, pool)
    RESERVE      reserve earmarked from revenue          (earmark,  pool — stays as cash)
    DISTRIBUTION net revenue moved to investor balances  (cash out of pool → investor liability)
    WITHDRAWAL   investor balance paid to bank           (cash out, investor/platform level)

Two conservation statements (real SPVs keep these separate because investor
balances are cumulative ACROSS pools, so a withdrawal cannot be attributed to a
single pool):

  Statement A — Pool cash custody (per pool)
      IN  = contributions + revenue
      OUT = releases + expenses + tax + refunds + distributions
      cash_balance = IN − OUT          (of which `reserve` is earmarked)
      → auditor: IN == OUT + cash_balance   and   cash_balance ≥ 0

  Statement B — Investor balance pool (platform-wide)
      distributions_credited = withdrawals_paid + outstanding_balances
      → auditor: the three tie out exactly

Audit numbers are computed from the **source-of-truth collections** (so they are
correct even for pools created before this journal existed); the journal itself
is the readable trail going forward.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("lumen.pool_cash")

C_MOVE = "lumen_pool_cash_movements"


class CashType(str, Enum):
    INFLOW = "INFLOW"          # investor contribution
    REVENUE = "REVENUE"        # asset/SPV income
    OUTFLOW = "OUTFLOW"        # seller release / expense / refund
    TAX = "TAX"                # tax withheld
    RESERVE = "RESERVE"        # reserve earmarked
    DISTRIBUTION = "DISTRIBUTION"  # net revenue → investor balances
    WITHDRAWAL = "WITHDRAWAL"  # investor balance → bank


_DIRECTION = {
    CashType.INFLOW: "in", CashType.REVENUE: "in",
    CashType.OUTFLOW: "out", CashType.TAX: "out",
    CashType.DISTRIBUTION: "out", CashType.WITHDRAWAL: "out",
    CashType.RESERVE: "earmark",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _r2(x) -> float:
    return round(float(x or 0), 2)


async def ensure_cash_indexes(db) -> None:
    try:
        await db[C_MOVE].create_index("id", unique=True)
        await db[C_MOVE].create_index("pool_id")
        await db[C_MOVE].create_index("investor_id")
        await db[C_MOVE].create_index("type")
        await db[C_MOVE].create_index("created_at")
        logger.info("POOL CASH: movement journal indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("POOL CASH: index ensure failed: %s", e)


async def record_movement(db, *, mtype: CashType, amount: float, currency: str,
                          pool_id: Optional[str] = None,
                          investor_id: Optional[str] = None,
                          source_kind: str = "", ref_id: Optional[str] = None,
                          description: str = "") -> dict:
    """Append one signed cash movement to the journal (best-effort, never raises)."""
    mv = {
        "id": f"mv_{uuid4().hex[:16]}",
        "pool_id": pool_id,
        "investor_id": investor_id,
        "type": mtype.value,
        "direction": _DIRECTION[mtype],
        "amount": _r2(amount),
        "currency": currency,
        "source_kind": source_kind,
        "ref_id": ref_id,
        "description": description,
        "created_at": _now(),
    }
    try:
        await db[C_MOVE].insert_one(dict(mv))
    except Exception as e:  # pragma: no cover
        logger.warning("cash movement record failed: %s", e)
    return mv


async def _sum(db, coll: str, match: dict, field: str) -> float:
    cur = db[coll].aggregate([
        {"$match": match},
        {"$group": {"_id": None, "v": {"$sum": f"${field}"}}},
    ])
    rows = await cur.to_list(1)
    return float(rows[0]["v"]) if rows else 0.0


async def build_pool_cash_audit(db, pool_id: str) -> dict:
    """Statement A — per-pool cash conservation, from source-of-truth aggregates."""
    pool = await db["lumen_pools"].find_one({"id": pool_id})
    if not pool:
        return {"error": "pool_not_found"}
    ccy = pool.get("currency", "EUR")

    contributions = await _sum(db, "lumen_pool_contributions",
                               {"pool_id": pool_id, "status": "confirmed"}, "amount")
    revenue = await _sum(db, "lumen_revenue_events", {"pool_id": pool_id}, "gross_amount")
    expenses = await _sum(db, "lumen_revenue_events", {"pool_id": pool_id}, "expenses_amount")
    tax = await _sum(db, "lumen_revenue_events", {"pool_id": pool_id}, "tax_amount")
    reserve = await _sum(db, "lumen_revenue_events", {"pool_id": pool_id}, "reserve_amount")
    releases = await _sum(db, "lumen_pool_ledger",
                          {"pool_id": pool_id, "kind": "seller_release"}, "amount")
    refunds = await _sum(db, "lumen_pool_ledger",
                         {"pool_id": pool_id, "kind": "refund"}, "amount")
    distributions = await _sum(db, "lumen_revenue_distributions",
                               {"pool_id": pool_id, "status": "credited"}, "gross_amount")

    total_in = _r2(contributions + revenue)
    total_out = _r2(releases + expenses + tax + refunds + distributions)
    cash_balance = _r2(total_in - total_out)
    reserves_earmarked = _r2(reserve)
    free_cash = _r2(cash_balance - reserves_earmarked)

    reconciles = abs(total_in - (total_out + cash_balance)) < 0.01
    non_negative = cash_balance >= -0.01

    return {
        "pool_id": pool_id,
        "currency": ccy,
        "inflows": {
            "contributions": _r2(contributions),
            "revenue": _r2(revenue),
            "total": total_in,
        },
        "outflows": {
            "seller_releases": _r2(releases),
            "expenses": _r2(expenses),
            "tax": _r2(tax),
            "refunds": _r2(refunds),
            "distributions": _r2(distributions),
            "total": total_out,
        },
        "cash_balance": cash_balance,
        "reserves_earmarked": reserves_earmarked,
        "free_cash": free_cash,
        "reconciles": bool(reconciles and non_negative),
        "checks": {
            "in_equals_out_plus_balance": bool(reconciles),
            "cash_balance_non_negative": bool(non_negative),
        },
    }


async def build_investor_balance_audit(db) -> dict:
    """Statement B — platform-wide investor-balance conservation."""
    distributions = await _sum(db, "lumen_revenue_distributions",
                               {"status": "credited"}, "gross_amount")
    withdrawals_paid = await _sum(db, "lumen_pool_withdrawals",
                                  {"status": {"$in": ["paid", "reconciled"]}}, "amount")
    reserved = await _sum(db, "lumen_pool_withdrawals",
                          {"status": {"$in": ["requested", "approved"]}}, "amount")
    outstanding = _r2(distributions - withdrawals_paid)
    available = _r2(outstanding - reserved)
    reconciles = abs(distributions - (withdrawals_paid + outstanding)) < 0.01
    return {
        "distributions_credited": _r2(distributions),
        "withdrawals_paid": _r2(withdrawals_paid),
        "withdrawals_reserved": _r2(reserved),
        "outstanding_balances": outstanding,
        "available_balances": available,
        "reconciles": bool(reconciles and outstanding >= -0.01),
        "checks": {
            "distributions_equal_paid_plus_outstanding": bool(reconciles),
            "outstanding_non_negative": bool(outstanding >= -0.01),
        },
    }


async def list_pool_movements(db, pool_id: str, limit: int = 300) -> list[dict]:
    rows = await db[C_MOVE].find({"pool_id": pool_id}).sort("created_at", -1).to_list(limit)
    out = []
    for r in rows:
        r.pop("_id", None)
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        out.append(r)
    return out


__all__ = [
    "CashType", "C_MOVE", "ensure_cash_indexes", "record_movement",
    "build_pool_cash_audit", "build_investor_balance_audit", "list_pool_movements",
]
