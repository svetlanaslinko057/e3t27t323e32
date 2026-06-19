"""
LUMEN Sprint 10 — System Health (umbrella)

Single admin endpoint that the frontend renders in Admin → System Health.
Aggregates every Sprint 10 surface so ops can read it in one place.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from lumen_api import require_admin, _now, _iso
from lumen_audit import AUDIT_COLLECTION
from lumen_consistency import run_all_checks
from lumen_ops import (
    measure_db_latency, queue_health, storage_usage, payout_failures,
    storage_audit, disaster_recovery_check, _list_backups,
)
from lumen_permissions import run_endpoint_security_audit
from lumen_error_tracking import status as error_tracking_status
from lumen_settlement_audit import run_settlement_checks


router = APIRouter(prefix="/api", tags=["lumen-system-health"])


def _summary(status: str, label: str, detail: str = "") -> dict:
    return {"status": status, "label": label, "detail": detail}


@router.get("/admin/system-health")
async def admin_system_health(request: Request, _=Depends(require_admin)):
    # Run all subsystems in parallel-ish fashion (motor handles concurrency)
    consistency = await run_all_checks()
    db_lat = await measure_db_latency()
    queues = await queue_health()
    storage = await storage_usage()
    failures = await payout_failures(24)
    file_audit = await storage_audit()
    dr = await disaster_recovery_check()
    sec = await run_endpoint_security_audit(request)
    backups = _list_backups()
    err_tracking = error_tracking_status()

    # Audit recent activity
    from lumen_api import db
    last_audit = await db[AUDIT_COLLECTION].find_one(sort=[("at", -1)])
    audit_total = await db[AUDIT_COLLECTION].count_documents({})

    cards: list[dict] = []

    cards.append({
        "key": "consistency",
        "title": "Data Consistency",
        "summary": _summary(
            consistency["overall"],
            f"{consistency['broken']} broken, {consistency['warnings']} warnings",
            details="Financial invariants check",
        ) if False else _summary(
            consistency["overall"],
            f"{consistency['broken']} broken, {consistency['warnings']} warnings",
        ),
        "data": consistency,
    })
    cards.append({
        "key": "db",
        "title": "Database",
        "summary": _summary(
            "ok" if db_lat.get("healthy") else "broken",
            f"{db_lat.get('latency_ms', '?')} ms",
        ),
        "data": db_lat,
    })
    cards.append({
        "key": "queues",
        "title": "Queues",
        "summary": _summary(
            "ok" if queues.get("healthy") else "warning",
            "all queues within threshold" if queues.get("healthy")
            else "one or more queues over threshold",
        ),
        "data": queues,
    })
    cards.append({
        "key": "storage",
        "title": "Storage",
        "summary": _summary(
            "ok" if storage.get("healthy") else "warning",
            f"disk used {storage.get('disk', {}).get('used_pct', '?')}%",
        ),
        "data": storage,
    })
    cards.append({
        "key": "file_audit",
        "title": "File Audit (orphans / missing)",
        "summary": _summary(
            "ok" if file_audit.get("healthy") else "warning",
            "no critical findings" if file_audit.get("healthy") else "orphans or missing files",
        ),
        "data": file_audit,
    })
    cards.append({
        "key": "failures",
        "title": "Failed Jobs (24h)",
        "summary": _summary(
            "ok" if failures.get("healthy") else "warning",
            f"failed batches: {failures['failed_payout_batches']}, rejected w/d: {failures['rejected_withdrawals']}",
        ),
        "data": failures,
    })
    cards.append({
        "key": "security",
        "title": "Security (route guards)",
        "summary": _summary(
            "ok" if sec["broken"] == 0 else "broken",
            f"{sec['checked']} routes checked, {sec['broken']} broken",
        ),
        "data": sec,
    })
    cards.append({
        "key": "dr",
        "title": "Disaster Recovery",
        "summary": _summary(
            "ok" if dr.get("healthy") else "warning",
            f"{dr.get('scenario_count', 0)} active scenarios",
        ),
        "data": dr,
    })
    cards.append({
        "key": "backups",
        "title": "Backups",
        "summary": _summary(
            "ok" if backups else "warning",
            f"{len(backups)} backup(s) retained" if backups else "no backups yet",
        ),
        "data": {"items": backups[:5], "total": len(backups)},
    })
    cards.append({
        "key": "audit",
        "title": "Audit Trail",
        "summary": _summary(
            "ok" if audit_total > 0 else "warning",
            f"{audit_total} events recorded",
        ),
        "data": {
            "total": audit_total,
            "last_at": _iso(last_audit.get("at")) if last_audit else None,
            "last_action": (last_audit or {}).get("action"),
        },
    })
    cards.append({
        "key": "error_tracking",
        "title": "Error Tracking",
        "summary": _summary(
            "ok" if err_tracking["initialised"]
            else ("warning" if (err_tracking["sentry_configured"]
                                or err_tracking["rollbar_configured"]) else "ok"),
            (err_tracking["provider"] or "disabled (no DSN)"),
        ),
        "data": err_tracking,
    })

    # ---- Sprint 11: Settlement (bank = ledger) ----
    settlement = await run_settlement_checks()
    cards.append({
        "key": "settlement",
        "title": "Settlement Audit (Sprint 11)",
        "summary": _summary(
            settlement["overall"],
            f"{settlement['broken']} broken, {settlement['warnings']} warnings",
        ),
        "data": settlement,
    })

    overall = "ok"
    if any(c["summary"]["status"] == "broken" for c in cards):
        overall = "broken"
    elif any(c["summary"]["status"] == "warning" for c in cards):
        overall = "warning"

    return {
        "overall": overall,
        "checked_at": _iso(_now()),
        "cards": cards,
    }


__all__ = ["router"]
