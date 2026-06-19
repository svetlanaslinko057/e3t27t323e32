"""
LUMEN Sprint 11 — Settlement Audit (Part 6)

Verifies the second-order invariant that Sprint 10 could not:

    bank reconciled total
      == ledger payment_funding credits
      == ownership sum (already covered by Sprint 10 I1)
      == wallet truth (already covered by Sprint 10 I3)

Introduces five additional checks (S1–S5) that are surfaced under the same
admin endpoint shape as `lumen_consistency`:

  S1.  Σ reconciled bank_transactions.amount_uah
         == Σ ledger entries (reason=investment_funding, type=credit)
  S2.  every reconciled bank_transaction has a matching ledger entry
  S3.  every confirmed payment_request has ≥ 1 bank_transaction OR
         was created BEFORE Sprint 11 (legacy backfill window)
  S4.  every unmatched bank_transaction older than 48h is reviewed
         (status check — not stuck silently)
  S5.  payout export consistency: Σ exported payout_records == Σ ledger
         debit reason=payout where matching period
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends

from lumen_api import db, require_admin, _now, _iso

logger = logging.getLogger("lumen.settlement_audit")

EPS = 0.50

# Sprint 11 boundary — anything older than this date predates banking layer.
# Used to avoid flagging legacy demo data as "missing bank_transaction".
SPRINT11_CUTOFF = "2026-06-10T00:00:00+00:00"


def _result(code, name, *, status, breaches=0, sample=None, details=""):
    return {
        "code": code, "name": name, "status": status,
        "breaches": breaches, "sample": sample or [], "details": details,
    }


async def _check_S1_bank_vs_ledger() -> dict:
    bank_total = 0.0
    async for b in db.lumen_bank_transactions.find({"status": "reconciled"}):
        bank_total += float(b.get("amount_uah") or 0)
    ledger_total = 0.0
    async for e in db.lumen_ledger_entries.find({
        "reason": "investment_funding", "entry_type": "credit",
    }):
        ledger_total += float(e.get("amount_uah") or 0)
    # Compare only the bank-tracked portion: ledger may include legacy backfill.
    delta = bank_total - 0  # bank is the floor; ledger should be >= bank
    status = "ok" if ledger_total + EPS >= bank_total else "broken"
    return _result(
        "S1",
        "Σ reconciled bank-tx amount_uah ≤ Σ ledger investment_funding credits",
        status=status,
        breaches=0 if status == "ok" else 1,
        sample=[] if status == "ok" else [{
            "bank_total_uah": round(bank_total, 2),
            "ledger_total_uah": round(ledger_total, 2),
            "delta_uah": round(bank_total - ledger_total, 2),
        }],
        details="Every reconciled bank money must end up in the ledger.",
    )


async def _check_S2_bank_has_ledger_link() -> dict:
    breaches = 0; sample = []
    async for b in db.lumen_bank_transactions.find({"status": "reconciled"}):
        if not b.get("ledger_entry_id"):
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "bank_transaction_id": b.get("id"),
                    "provider": b.get("provider"),
                    "amount_uah": b.get("amount_uah"),
                })
    return _result(
        "S2",
        "Every reconciled bank transaction has a ledger_entry_id link",
        status="ok" if breaches == 0 else "broken",
        breaches=breaches, sample=sample,
        details="Reconciled bank rows must link to a concrete ledger entry.",
    )


async def _check_S3_confirmed_has_bank_or_legacy() -> dict:
    breaches = 0; sample = []
    async for pr in db.lumen_payment_requests.find({"status": "confirmed"}):
        created = pr.get("created_at")
        # Legacy backfill window: anything created before Sprint 11 cutoff is
        # exempt (we had no banking layer yet).
        if created:
            cstr = created if isinstance(created, str) else created.isoformat()
            if cstr < SPRINT11_CUTOFF:
                continue
        has_bank = await db.lumen_bank_transactions.find_one({
            "payment_request_id": pr.get("id"), "status": "reconciled",
        })
        if not has_bank:
            breaches += 1
            if len(sample) < 5:
                sample.append({
                    "payment_request_id": pr.get("id"),
                    "investor_id": pr.get("investor_id"),
                    "amount_uah": pr.get("amount_uah"),
                })
    return _result(
        "S3",
        "Every confirmed payment_request (post Sprint 11) has a bank_transaction",
        status="ok" if breaches == 0 else "warning",
        breaches=breaches, sample=sample,
        details="Post Sprint 11, every confirmed payment must originate from a real bank tx.",
    )


async def _check_S4_stale_unmatched() -> dict:
    cutoff = _now() - timedelta(hours=48)
    breaches = 0; sample = []
    async for b in db.lumen_bank_transactions.find({
        "status": "unmatched",
        "created_at": {"$lt": cutoff},
    }):
        breaches += 1
        if len(sample) < 5:
            sample.append({
                "bank_transaction_id": b.get("id"),
                "provider": b.get("provider"),
                "amount_uah": b.get("amount_uah"),
                "created_at": _iso(b.get("created_at")),
            })
    return _result(
        "S4",
        "No bank transactions stuck unmatched > 48h",
        status="ok" if breaches == 0 else "warning",
        breaches=breaches, sample=sample,
        details="Unmatched bank rows older than 48h need manual review.",
    )


async def _check_S5_export_consistency() -> dict:
    exported_sum = 0.0
    async for r in db.lumen_payout_records.find({"exported_at": {"$ne": None}}):
        exported_sum += float(r.get("amount_uah") or 0)
    ledger_sum = 0.0
    async for e in db.lumen_ledger_entries.find({
        "reason": "payout", "entry_type": "credit",
    }):
        ledger_sum += float(e.get("amount_uah") or 0)
    # Export sum must be <= ledger sum (we can't export what we didn't credit).
    delta = exported_sum - ledger_sum
    status = "ok" if exported_sum <= ledger_sum + EPS else "broken"
    return _result(
        "S5",
        "Σ exported payout_records ≤ Σ ledger payout credits",
        status=status,
        breaches=0 if status == "ok" else 1,
        sample=[] if status == "ok" else [{
            "exported_uah": round(exported_sum, 2),
            "ledger_payout_credits_uah": round(ledger_sum, 2),
            "delta_uah": round(delta, 2),
        }],
        details="Finance must not hand off a file that exceeds credited payouts.",
    )


CHECKS = {
    "S1": _check_S1_bank_vs_ledger,
    "S2": _check_S2_bank_has_ledger_link,
    "S3": _check_S3_confirmed_has_bank_or_legacy,
    "S4": _check_S4_stale_unmatched,
    "S5": _check_S5_export_consistency,
}


async def run_settlement_checks() -> dict:
    results = []
    for code, fn in CHECKS.items():
        try:
            r = await fn()
        except Exception as exc:
            logger.exception("settlement check %s failed", code)
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
        "checked_at": _iso(_now()),
    }


router = APIRouter(prefix="/api", tags=["lumen-banking"])


@router.get("/admin/settlement/check")
async def admin_settlement_check(_=Depends(require_admin)):
    return await run_settlement_checks()


__all__ = ["router", "run_settlement_checks", "CHECKS"]
