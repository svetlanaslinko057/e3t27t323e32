"""
LUMEN Sprint 10 — Data Consistency Audit (Block 9)

Validates the financial invariants of the platform. ALL CHECKS ARE READ-ONLY.
Reports breakages — never auto-repairs (auto-repair would mask a bug).

Invariants
----------
  I1.  Σ ownerships per asset == ownerships derived from active investments
  I2.  asset.raised_amount == Σ investments(asset).amount_uah  where status=active
  I3.  wallet.settled_balance == Σ ledger credits - Σ ledger debits
         (filtered by WALLET_LEDGER_REASONS)
  I4.  Σ payouts (credited)   == Σ ledger credit entries reason='payout'
  I5.  Σ withdrawals (paid)   == Σ ledger debit  entries reason='withdrawal'
  I6.  no negative wallets (settled_balance >= 0)
  I7.  no investor with active investments and missing approved KYC
         (compliance regression check)
  I8.  no orphan ledger entries (investor_id resolves to existing user)
  I9.  no double-credited payout records (same investor + period_key + plan)
  I10. no withdrawal paid without matching ledger debit

Each check returns:
  {
    code: 'I1', name: '...', status: 'ok' | 'warning' | 'broken',
    breaches: int, sample: [up to 5 example offending docs], details: '...'
  }

Admin API
---------
  GET  /api/admin/consistency/check        — run all + return report
  GET  /api/admin/consistency/check/{code} — run single check
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from lumen_api import db, require_admin, _now

logger = logging.getLogger("lumen.consistency")

# tolerances (UAH — floating point safety net)
EPS = 0.50

WALLET_CREDIT_REASONS = {"payout", "refund", "adjustment", "secondary_sale"}
WALLET_DEBIT_REASONS = {"withdrawal", "adjustment", "secondary_purchase"}
WALLET_REASONS = WALLET_CREDIT_REASONS | WALLET_DEBIT_REASONS


def _result(code, name, *, status, breaches=0, sample=None, details=""):
    return {
        "code": code,
        "name": name,
        "status": status,           # ok | warning | broken
        "breaches": breaches,
        "sample": sample or [],
        "details": details,
    }


# ----------------------------------------------------------------------------
# Individual invariants
# ----------------------------------------------------------------------------

async def _check_I1_ownership_sum() -> dict:
    sample = []
    breaches = 0
    async for asset in db.lumen_assets.find({}, {"id": 1, "title": 1}):
        aid = asset.get("id")
        own_sum = 0.0
        async for o in db.lumen_ownerships.find({"asset_id": aid}):
            own_sum += float(o.get("amount_uah") or o.get("amount") or 0)
        inv_sum = 0.0
        async for inv in db.lumen_investments.find(
                {"asset_id": aid, "status": "active"}):
            inv_sum += float(
                inv.get("amount_uah") or inv.get("amount")
                or inv.get("invested_amount") or 0
            )
        if abs(own_sum - inv_sum) > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "asset_id": aid,
                    "title": asset.get("title"),
                    "ownership_sum_uah": round(own_sum, 2),
                    "investments_sum_uah": round(inv_sum, 2),
                    "delta_uah": round(own_sum - inv_sum, 2),
                })
    return _result(
        "I1",
        "Σ ownerships per asset = Σ active investments",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches,
        sample=sample,
        details="Each asset's ownership ledger must match its active investments.",
    )


async def _check_I2_raised_amount() -> dict:
    sample = []
    breaches = 0
    async for asset in db.lumen_assets.find({}, {"id": 1, "title": 1, "raised_amount": 1}):
        aid = asset.get("id")
        raised = float(asset.get("raised_amount") or 0)
        confirmed = 0.0
        async for inv in db.lumen_investments.find(
                {"asset_id": aid, "status": "active"}):
            confirmed += float(
                inv.get("amount_uah") or inv.get("amount")
                or inv.get("invested_amount") or 0
            )
        if abs(raised - confirmed) > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "asset_id": aid,
                    "title": asset.get("title"),
                    "raised_amount": round(raised, 2),
                    "confirmed_funding": round(confirmed, 2),
                    "delta_uah": round(raised - confirmed, 2),
                })
    return _result(
        "I2",
        "asset.raised_amount = Σ active investment amount",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches,
        sample=sample,
        details="raised_amount denormalisation must match its source of truth.",
    )


async def _check_I3_wallet_truth() -> dict:
    sample = []
    breaches = 0
    async for w in db.lumen_wallets.find({}):
        iid = w.get("investor_id")
        settled = float(w.get("settled_balance") or 0)
        inflow = 0.0
        outflow = 0.0
        async for e in db.lumen_ledger_entries.find({
            "investor_id": iid,
            "reason": {"$in": list(WALLET_REASONS)},
        }):
            amt = float(e.get("amount_uah") or 0)
            if e.get("entry_type") == "credit":
                inflow += amt
            else:
                outflow += amt
        truth = inflow - outflow
        if abs(truth - settled) > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "investor_id": iid,
                    "wallet_settled": round(settled, 2),
                    "ledger_truth": round(truth, 2),
                    "delta_uah": round(settled - truth, 2),
                })
    return _result(
        "I3",
        "wallet.settled_balance = ledger truth",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches,
        sample=sample,
        details="Materialised wallets must equal the ledger's calculated truth.",
    )


async def _check_I4_payouts_ledger() -> dict:
    paid_records = 0.0
    async for r in db.lumen_payout_records.find({"status": "credited"}):
        paid_records += float(r.get("amount_uah") or 0)
    ledger_credit = 0.0
    async for e in db.lumen_ledger_entries.find({
        "reason": "payout", "entry_type": "credit"
    }):
        ledger_credit += float(e.get("amount_uah") or 0)
    delta = paid_records - ledger_credit
    status = "ok" if abs(delta) <= EPS else "broken"
    return _result(
        "I4",
        "Σ credited payouts = Σ ledger payout credits",
        status=status,
        breaches=0 if status == "ok" else 1,
        sample=[] if status == "ok" else [{
            "payout_records_credited": round(paid_records, 2),
            "ledger_payout_credits": round(ledger_credit, 2),
            "delta_uah": round(delta, 2),
        }],
        details="Every credited payout record must have a matching ledger credit.",
    )


async def _check_I5_withdrawals_ledger() -> dict:
    paid_w = 0.0
    async for w in db.lumen_withdrawal_requests.find({"status": "paid"}):
        paid_w += float(w.get("amount_uah") or 0)
    ledger_debit = 0.0
    async for e in db.lumen_ledger_entries.find({
        "reason": "withdrawal", "entry_type": "debit"
    }):
        ledger_debit += float(e.get("amount_uah") or 0)
    delta = paid_w - ledger_debit
    status = "ok" if abs(delta) <= EPS else "broken"
    return _result(
        "I5",
        "Σ paid withdrawals = Σ ledger withdrawal debits",
        status=status,
        breaches=0 if status == "ok" else 1,
        sample=[] if status == "ok" else [{
            "withdrawals_paid": round(paid_w, 2),
            "ledger_withdrawal_debits": round(ledger_debit, 2),
            "delta_uah": round(delta, 2),
        }],
        details="Every PAID withdrawal must have a matching ledger debit.",
    )


async def _check_I6_no_negative_wallets() -> dict:
    sample = []
    breaches = 0
    async for w in db.lumen_wallets.find({}):
        if float(w.get("settled_balance") or 0) < -EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "investor_id": w.get("investor_id"),
                    "settled_balance": w.get("settled_balance"),
                })
    return _result(
        "I6",
        "No negative wallets",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="Settled wallet balance must never go below zero.",
    )


async def _check_I7_active_inv_needs_kyc() -> dict:
    sample = []
    breaches = 0
    investor_ids = await db.lumen_investments.distinct("investor_id", {"status": "active"})
    for iid in investor_ids:
        prof = await db.lumen_investor_profiles.find_one({"user_id": iid})
        kyc_status = (prof or {}).get("kyc_status")
        if kyc_status != "approved":
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "investor_id": iid,
                    "kyc_status": kyc_status or "missing",
                })
    return _result(
        "I7",
        "Every active investor has approved KYC",
        status="ok" if breaches == 0 else "warning",
        breaches=breaches, sample=sample,
        details="Compliance regression — active investments require approved KYC.",
    )


async def _check_I8_no_orphan_ledger() -> dict:
    sample = []
    breaches = 0
    investor_ids = set()
    async for u in db.users.find({}, {"user_id": 1}):
        if u.get("user_id"):
            investor_ids.add(u["user_id"])
    # Sprint 13: platform-revenue is an intentional virtual account
    from lumen_secondary import PLATFORM_REVENUE_ACCOUNT
    investor_ids.add(PLATFORM_REVENUE_ACCOUNT)
    async for e in db.lumen_ledger_entries.find({}, {"id": 1, "investor_id": 1}):
        if e.get("investor_id") not in investor_ids:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "ledger_entry": e.get("id"),
                    "missing_investor_id": e.get("investor_id"),
                })
    return _result(
        "I8",
        "No orphan ledger entries",
        status="ok" if breaches == 0 else "warning",
        breaches=breaches, sample=sample,
        details="Every ledger row's investor_id must resolve to an existing user (or platform-revenue virtual account).",
    )


async def _check_I9_no_double_payout() -> dict:
    sample = []
    breaches = 0
    pipeline = [
        # Only periodic payout records (period_key is set). Records with
        # period_key=None are one-off ad-hoc credits and cannot be "duplicate".
        {"$match": {"status": "credited",
                    "period_key": {"$ne": None, "$exists": True}}},
        {"$group": {
            "_id": {
                "investor_id": "$investor_id",
                "plan_id": "$plan_id",
                "period_key": "$period_key",
            },
            "count": {"$sum": 1},
            "total_uah": {"$sum": "$amount_uah"},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 5},
    ]
    async for row in db.lumen_payout_records.aggregate(pipeline):
        breaches += 1
        sample.append({
            "investor_id": row["_id"].get("investor_id"),
            "plan_id": row["_id"].get("plan_id"),
            "period_key": row["_id"].get("period_key"),
            "duplicate_count": row["count"],
            "total_amount_uah": round(row.get("total_uah") or 0, 2),
        })
    return _result(
        "I9",
        "No double-credited payouts (investor+plan+period unique)",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="A single payout period must not be credited twice to the same investor.",
    )


async def _check_I10_paid_withdrawal_has_debit() -> dict:
    sample = []
    breaches = 0
    async for w in db.lumen_withdrawal_requests.find({"status": "paid"}):
        wid = w.get("id")
        # match by meta.withdrawal_id, ref_id or amount tolerance per investor
        matched = await db.lumen_ledger_entries.find_one({
            "investor_id": w.get("investor_id"),
            "reason": "withdrawal",
            "entry_type": "debit",
            "$or": [
                {"ref_id": wid},
                {"meta.withdrawal_id": wid},
            ],
        })
        if not matched:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "withdrawal_id": wid,
                    "investor_id": w.get("investor_id"),
                    "amount_uah": w.get("amount_uah"),
                })
    return _result(
        "I10",
        "Every PAID withdrawal has a matching ledger debit",
        status="ok" if breaches == 0 else "warning",
        breaches=breaches, sample=sample,
        details="Cross-reference between withdrawal lifecycle and the ledger.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 13 — Secondary Market invariants (I11–I13)
# Transfers in `lumen_share_transfers` rebalance ownership BETWEEN investors
# but do NOT change total ownership per asset (which still equals primary).
# ─────────────────────────────────────────────────────────────────────────────

async def _check_I11_transfer_matches_trade() -> dict:
    """Every settled trade must have a matching share_transfer row."""
    sample = []
    breaches = 0
    async for t in db.lumen_secondary_trades.find({"status": "settled"}):
        st = await db.lumen_share_transfers.find_one({"trade_id": t.get("id")})
        if not st:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "trade_id": t.get("id"),
                    "units_uah": t.get("units_uah"),
                })
            continue
        if abs(float(st.get("amount_uah") or 0) - float(t.get("units_uah") or 0)) > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "trade_id": t.get("id"),
                    "trade_units_uah": t.get("units_uah"),
                    "transfer_amount_uah": st.get("amount_uah"),
                })
    return _result(
        "I11",
        "Every settled trade has a share_transfer with matching units",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="Settled trades must move ownership through share_transfers.",
    )


async def _check_I12_trade_ledger_conservation() -> dict:
    """For each settled trade: buyer_debit = gross, seller_credit = net,
    platform_fee_credit = fee. Money in = Money out."""
    sample = []
    breaches = 0
    async for t in db.lumen_secondary_trades.find({"status": "settled"}):
        tid = t.get("id")
        gross = float(t.get("gross_uah") or 0)
        fee = float(t.get("fee_uah") or 0)
        net = float(t.get("seller_net_uah") or (gross - fee))
        # ledger entries are tagged by note containing "trade <tid>"
        buyer_debit = 0.0
        async for e in db.lumen_ledger_entries.find({
            "investor_id": t.get("buyer_id"),
            "reason": "secondary_purchase",
            "entry_type": "debit",
            "notes": {"$regex": tid},
        }):
            buyer_debit += float(e.get("amount_uah") or 0)
        seller_credit = 0.0
        async for e in db.lumen_ledger_entries.find({
            "investor_id": t.get("seller_id"),
            "reason": "secondary_sale",
            "entry_type": "credit",
            "notes": {"$regex": tid},
        }):
            seller_credit += float(e.get("amount_uah") or 0)
        fee_credit = 0.0
        if fee > 0:
            async for e in db.lumen_ledger_entries.find({
                "reason": "platform_fee", "entry_type": "credit",
                "notes": {"$regex": tid},
            }):
                fee_credit += float(e.get("amount_uah") or 0)
        delta_buyer = abs(buyer_debit - gross)
        delta_seller = abs(seller_credit - net)
        delta_fee = abs(fee_credit - fee)
        if delta_buyer > EPS or delta_seller > EPS or delta_fee > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "trade_id": tid,
                    "expected": {"buyer_debit": gross, "seller_credit": net, "fee_credit": fee},
                    "actual":   {"buyer_debit": round(buyer_debit, 2),
                                 "seller_credit": round(seller_credit, 2),
                                 "fee_credit": round(fee_credit, 2)},
                })
    return _result(
        "I12",
        "Every settled trade: buyer_debit = gross AND seller_credit = net AND fee_credit = fee",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="Per-trade ledger conservation across buyer / seller / platform-revenue.",
    )


async def _check_I13_per_investor_ownership() -> dict:
    """ownership(investor, asset) ==
       Σ primary investments - Σ outbound transfers + Σ inbound transfers.
       Per-investor breach is broken (regression); we sample at most 5."""
    breaches = 0
    sample = []
    async for o in db.lumen_ownerships.find({}):
        iid = o.get("investor_id"); aid = o.get("asset_id")
        if not iid or not aid: continue
        recorded = float(o.get("amount_uah") or o.get("amount") or 0)
        primary = 0.0
        async for inv in db.lumen_investments.find(
                {"investor_id": iid, "asset_id": aid, "status": "active"}):
            primary += float(inv.get("amount_uah") or inv.get("amount")
                             or inv.get("invested_amount") or 0)
        inflow = 0.0
        async for st in db.lumen_share_transfers.find(
                {"to_investor_id": iid, "asset_id": aid}):
            inflow += float(st.get("amount_uah") or 0)
        outflow = 0.0
        async for st in db.lumen_share_transfers.find(
                {"from_investor_id": iid, "asset_id": aid}):
            outflow += float(st.get("amount_uah") or 0)
        expected = primary + inflow - outflow
        if abs(recorded - expected) > EPS:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "investor_id": iid, "asset_id": aid,
                    "recorded": round(recorded, 2),
                    "expected": round(expected, 2),
                    "delta": round(recorded - expected, 2),
                })
    return _result(
        "I13",
        "ownership(investor, asset) = primary + inbound transfers - outbound transfers",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="Per-investor ownership formula including Sprint 13 share transfers.",
    )


CHECKS = {
    "I1":  _check_I1_ownership_sum,
    "I2":  _check_I2_raised_amount,
    "I3":  _check_I3_wallet_truth,
    "I4":  _check_I4_payouts_ledger,
    "I5":  _check_I5_withdrawals_ledger,
    "I6":  _check_I6_no_negative_wallets,
    "I7":  _check_I7_active_inv_needs_kyc,
    "I8":  _check_I8_no_orphan_ledger,
    "I9":  _check_I9_no_double_payout,
    "I10": _check_I10_paid_withdrawal_has_debit,
    "I11": _check_I11_transfer_matches_trade,
    "I12": _check_I12_trade_ledger_conservation,
    "I13": _check_I13_per_investor_ownership,
}


async def run_all_checks() -> dict:
    results = []
    for code, fn in CHECKS.items():
        try:
            r = await fn()
        except Exception as exc:
            logger.exception("consistency check %s failed", code)
            r = _result(code, code, status="warning", breaches=0,
                        details=f"check_failed: {exc!s}")
        results.append(r)
    broken = sum(1 for r in results if r["status"] == "broken")
    warnings = sum(1 for r in results if r["status"] == "warning")
    overall = "ok"
    if broken > 0:
        overall = "broken"
    elif warnings > 0:
        overall = "warning"
    return {
        "overall": overall,
        "broken": broken,
        "warnings": warnings,
        "checks": results,
        "checked_at": _now().isoformat(),
    }


# ----------------------------------------------------------------------------
# Router — admin
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-consistency"])


@router.get("/admin/consistency/check")
async def admin_consistency_check(_=Depends(require_admin)):
    return await run_all_checks()


@router.get("/admin/consistency/check/{code}")
async def admin_consistency_single(code: str, _=Depends(require_admin)):
    fn = CHECKS.get(code.upper())
    if not fn:
        raise HTTPException(status_code=404, detail=f"Unknown check: {code}")
    return await fn()


__all__ = ["router", "run_all_checks", "CHECKS"]
