"""
WEB-P4 — Backend Authority Contract summary endpoints.

Pages must render backend JSON, not compute business state locally.
This module adds canonical aggregate endpoints that replace `.reduce`,
`.sort`, `Math.max/min` and `useMemo` derivations previously living
inside `/app/web/src/pages/`.

Mounted from `server.py` via `register_web_p4_routes(api_router, db, get_current_user)`
so the dependencies stay singly-defined in the main module.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query


# Statuses that mean money has NOT yet been collected.
# Mirrors `mock_seed.py` + `legal_contract_layer.py` taxonomy.
_PENDING_INVOICE_STATES = {"pending", "pending_payment", "draft", "failed", "overdue"}
_PAID_INVOICE_STATES = {"paid", "settled"}


def register_web_p4_routes(api_router: APIRouter, db, get_current_user):
    """Attach WEB-P4 summary endpoints to the given /api router."""

    # ────────────────────────────────────────────────────────────────
    # /api/client/billing/invoices-summary
    # Replaces ClientBillingOS.js:74-77 (`.filter` + `.reduce`).
    # NOTE: `/api/client/billing/summary` is already used for product-flow
    # next-payment, so this page-level invoice aggregation lives under a
    # distinct path.
    # ────────────────────────────────────────────────────────────────
    @api_router.get("/client/billing/invoices-summary")
    async def _client_billing_summary(user=Depends(get_current_user)):
        cursor = db.invoices.find({"client_id": user.user_id}, {"_id": 0})
        invoices: List[Dict[str, Any]] = await cursor.to_list(500)

        pending: List[Dict[str, Any]] = []
        paid: List[Dict[str, Any]] = []
        total_pending = 0.0
        total_paid = 0.0

        for inv in invoices:
            amount = float(inv.get("amount") or 0)
            status = str(inv.get("status") or "").lower()
            if status in _PAID_INVOICE_STATES:
                total_paid += amount
                paid.append({**inv, "status": "paid", "status_raw": status})
            elif status in _PENDING_INVOICE_STATES:
                total_pending += amount
                pending.append({**inv, "status": "pending", "status_raw": status})

        def _ts(row: Dict[str, Any]) -> str:
            return str(row.get("created_at") or "")

        return {
            "totals": {
                "pending": round(total_pending, 2),
                "paid": round(total_paid, 2),
                "pending_count": len(pending),
                "paid_count": len(paid),
            },
            "pending": sorted(pending, key=_ts, reverse=True),
            "paid": sorted(paid, key=_ts, reverse=True),
        }

    # ────────────────────────────────────────────────────────────────
    # /api/developer/performance/summary
    # Replaces DeveloperPerformance.js:34-46 (.filter + .reduce + Math.round)
    # ────────────────────────────────────────────────────────────────
    @api_router.get("/developer/performance/summary")
    async def _developer_performance_summary(user=Depends(get_current_user)):
        units = await db.work_units.find(
            {"developer_id": user.user_id}, {"_id": 0}
        ).to_list(1000)

        completed_recent: List[Dict[str, Any]] = []
        total_hours = 0.0
        total_completed = 0
        total_revisions = 0
        sum_completed_hours = 0.0

        for u in units:
            actual = float(u.get("actual_hours") or 0)
            total_hours += actual
            status = str(u.get("status") or "")
            if status == "completed":
                total_completed += 1
                sum_completed_hours += actual
                completed_recent.append(u)
            elif status == "revision":
                total_revisions += 1

        denom = total_completed + total_revisions
        success_rate_pct = 100 if denom == 0 else round((total_completed / denom) * 100)
        avg_hours_per_completed = (
            round(sum_completed_hours / total_completed, 1) if total_completed > 0 else 0
        )

        completed_recent_sorted = sorted(
            completed_recent,
            key=lambda r: str(r.get("completed_at") or r.get("created_at") or ""),
            reverse=True,
        )[:10]

        return {
            "totals": {
                "total_hours": round(total_hours, 1),
                "total_completed": total_completed,
                "total_revisions": total_revisions,
                "success_rate_pct": success_rate_pct,
                "avg_hours_per_completed": avg_hours_per_completed,
            },
            "completed_recent": completed_recent_sorted,
        }

    # ────────────────────────────────────────────────────────────────
    # /api/admin/users-v2/summary
    # Replaces AdminUsersPage.js:155 (useMemo counts)
    # ────────────────────────────────────────────────────────────────
    @api_router.get("/admin/users-v2/summary")
    async def _admin_users_v2_summary(
        q: str | None = Query(default=None),
        role: str | None = Query(default=None),
        user=Depends(get_current_user),
    ):
        if str(getattr(user, "role", "")) != "admin":
            raise HTTPException(status_code=403, detail="Admin only")

        flt: Dict[str, Any] = {}
        if q:
            flt["$or"] = [
                {"email": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
            ]
        if role:
            flt["role"] = role

        total = await db.users.count_documents(flt)
        blocked = await db.users.count_documents({**flt, "status": "blocked"})
        deleted = await db.users.count_documents({**flt, "is_deleted": True})

        return {
            "total": total,
            "active": max(0, total - blocked - deleted),
            "blocked": blocked,
            "deleted": deleted,
        }
