"""
ops_center.py — Admin Operations Center aggregator for Lumen.

Read-only aggregator over EXISTING processes (no new entities). Surfaces the
operational backlog the team must act on, in one place:

  • Pending KYC        — lumen_investor_profiles where kyc_status in
                         [submitted, under_review]
  • Pending Payments   — lumen_payment_requests where status in
                         [paid, under_review]
  • Pending Withdrawals— lumen_withdrawal_requests where status in
                         [requested, approved, processing]
  • Pending Payouts    — lumen_payout_batches where status == generated
  • Pending Disputes   — secondary-market disputes are handled manually via the
                         Dispute SOP (no data entity) → count 0 + manual note

Endpoint: GET /api/admin/operations/summary
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

logger = logging.getLogger(__name__)

KYC_PENDING = ["submitted", "under_review"]
PAYMENT_PENDING = ["paid", "under_review"]
WITHDRAWAL_PENDING = ["requested", "approved", "processing"]
PAYOUT_PENDING = ["generated"]


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat() if v.tzinfo else v.replace(tzinfo=timezone.utc).isoformat()
    return v


def build_ops_center_router(db, require_admin):
    router = APIRouter(prefix="/api/admin/operations", tags=["ops-center"])

    async def _recent(collection: str, query: Dict[str, Any], fields: List[str], limit: int = 5):
        out: List[Dict[str, Any]] = []
        try:
            cur = db[collection].find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
            async for d in cur:
                out.append({f: _iso(d.get(f)) for f in fields})
        except Exception as e:  # pragma: no cover
            logger.warning("ops_center recent(%s) failed: %s", collection, e)
        return out

    @router.get("/summary")
    async def operations_summary(user=Depends(require_admin)):
        now = datetime.now(timezone.utc).isoformat()

        async def _count(collection: str, query: Dict[str, Any]) -> int:
            try:
                return await db[collection].count_documents(query)
            except Exception as e:  # pragma: no cover
                logger.warning("ops_center count(%s) failed: %s", collection, e)
                return 0

        kyc_q = {"kyc_status": {"$in": KYC_PENDING}}
        pay_q = {"status": {"$in": PAYMENT_PENDING}}
        wd_q = {"status": {"$in": WITHDRAWAL_PENDING}}
        po_q = {"status": {"$in": PAYOUT_PENDING}}

        kyc_count = await _count("lumen_investor_profiles", kyc_q)
        pay_count = await _count("lumen_payment_requests", pay_q)
        wd_count = await _count("lumen_withdrawal_requests", wd_q)
        po_count = await _count("lumen_payout_batches", po_q)

        cards = [
            {
                "key": "kyc",
                "title": "KYC на перевірці",
                "count": kyc_count,
                "link": "/admin/kyc",
                "cta": "Перейти до KYC",
                "statuses": KYC_PENDING,
                "recent": await _recent(
                    "lumen_investor_profiles", kyc_q,
                    ["user_id", "full_name", "kyc_status", "updated_at"],
                ),
            },
            {
                "key": "payments",
                "title": "Платежі на перевірці",
                "count": pay_count,
                "link": "/admin/payments",
                "cta": "Перейти до платежів",
                "statuses": PAYMENT_PENDING,
                "recent": await _recent(
                    "lumen_payment_requests", pay_q,
                    ["id", "investor_id", "amount", "currency", "status", "updated_at"],
                ),
            },
            {
                "key": "withdrawals",
                "title": "Виводи в опрацюванні",
                "count": wd_count,
                "link": "/admin/withdrawals",
                "cta": "Перейти до виводів",
                "statuses": WITHDRAWAL_PENDING,
                "recent": await _recent(
                    "lumen_withdrawal_requests", wd_q,
                    ["id", "investor_id", "amount", "status", "updated_at"],
                ),
            },
            {
                "key": "payouts",
                "title": "Виплати доходу до схвалення",
                "count": po_count,
                "link": "/admin/payouts",
                "cta": "Перейти до виплат",
                "statuses": PAYOUT_PENDING,
                "recent": await _recent(
                    "lumen_payout_batches", po_q,
                    ["id", "asset_id", "status", "total_amount", "updated_at"],
                ),
            },
            {
                "key": "disputes",
                "title": "Спори вторинного ринку",
                "count": 0,
                "link": "/admin/secondary-market",
                "cta": "Вторинний ринок",
                "statuses": [],
                "manual": True,
                "note": "Спори опрацьовуються вручну згідно з Secondary Market Dispute SOP.",
                "recent": [],
            },
        ]

        total_pending = kyc_count + pay_count + wd_count + po_count
        return {
            "computed_at": now,
            "total_pending": total_pending,
            "cards": cards,
        }

    return router
