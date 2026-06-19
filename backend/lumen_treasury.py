"""
LUMEN 2.0 — Phase H1.1.1 — Treasury Dashboard
==============================================

Real-time operational view of the Funding Center for the finance team. All
KPIs come from authoritative sources only (Treasury-R1):

* `lumen_institutional_transfers`
* `money_ledger`
* the `reconciliation` block on each transfer

No derived mocks, no synthetic data.

Also exposes the H1.2 webhook + polling control surface:

* `POST /api/lumen/banking/webhook/{provider}` — idempotent webhook ingress
* `POST /api/admin/treasury/sync` — manual trigger of `sync_pending_transfers`
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin,
                       _strip_mongo, _now, _iso, lr2_perm as _lr2_perm)
from lumen_funding_center import (
    canonical_status as _cs,
    CS_CONFIRMED, CS_MATCHED, CS_PENDING_REVIEW, CS_REJECTED, CS_SUBMITTED,
    TERMINAL_CANONICAL,
)
from lumen_banking_adapter import get_adapter_for

logger = logging.getLogger("lumen.treasury")

TRANSFERS = "lumen_institutional_transfers"
LEDGER = "money_ledger"
WEBHOOK_EVENTS = "lumen_banking_webhook_events"


# ═════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        s = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


async def _sum_volume(query: dict) -> tuple[int, float]:
    """Returns (count, total_amount) for transfers matching query."""
    pipeline = [
        {"$match": query},
        {"$group": {"_id": None, "n": {"$sum": 1},
                     "v": {"$sum": "$amount"}}},
    ]
    async for row in db[TRANSFERS].aggregate(pipeline):
        return int(row.get("n") or 0), float(row.get("v") or 0.0)
    return 0, 0.0


# ═════════════════════════════════════════════════════════════════════════
# KPI computation (Treasury-R1)
# ═════════════════════════════════════════════════════════════════════════

async def compute_kpis(window_days: int = 30) -> dict:
    """Compute all Treasury KPIs from authoritative sources only.

    Treasury-R1: data comes from lumen_institutional_transfers + money_ledger.
    Treasury-R2: time-to-confirm uses created_at (== submitted_at) → confirmed_at.
    """
    now = _utcnow()
    window_start = now - timedelta(days=window_days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Status counts (canonical_status preferred; legacy mapped at query level)
    counts: dict[str, int] = {}
    for cs in (CS_SUBMITTED, CS_PENDING_REVIEW, CS_MATCHED, CS_CONFIRMED, CS_REJECTED):
        counts[cs] = await db[TRANSFERS].count_documents({"canonical_status": cs})
    # Backfill counts also using legacy status mapping for older rows
    legacy_extra = {
        CS_SUBMITTED: await db[TRANSFERS].count_documents(
            {"canonical_status": {"$exists": False}, "status": "pending"}),
        CS_PENDING_REVIEW: await db[TRANSFERS].count_documents(
            {"canonical_status": {"$exists": False},
             "status": {"$in": ["initiated", "sent"]}}),
        CS_CONFIRMED: await db[TRANSFERS].count_documents(
            {"canonical_status": {"$exists": False}, "status": "confirmed"}),
        CS_REJECTED: await db[TRANSFERS].count_documents(
            {"canonical_status": {"$exists": False},
             "status": {"$in": ["failed", "returned", "cancelled"]}}),
    }
    for k, v in legacy_extra.items():
        counts[k] = counts.get(k, 0) + v

    # Volumes (use settled_at for confirmed, fallback to created_at)
    today_n, today_v = await _sum_volume({
        "$or": [{"settled_at": {"$gte": _iso(today_start)}},
                 {"created_at": {"$gte": today_start}}],
    })
    win_n, win_v = await _sum_volume({"created_at": {"$gte": window_start}})
    sepa_n, sepa_v = await _sum_volume({
        "created_at": {"$gte": window_start},
        "rail": {"$in": ["sepa", "sepa_instant"]},
    })
    swift_n, swift_v = await _sum_volume({
        "created_at": {"$gte": window_start},
        "rail": "swift",
    })

    # Time-to-Confirm (Treasury-R2): avg seconds from created_at → settled_at
    durations: list[float] = []
    async for t in db[TRANSFERS].find(
        {"$or": [{"canonical_status": CS_CONFIRMED},
                  {"status": "confirmed"}],
         "settled_at": {"$exists": True, "$ne": None}},
        {"_id": 0, "created_at": 1, "settled_at": 1},
    ).limit(500):
        a = _parse_dt(t.get("created_at"))
        b = _parse_dt(t.get("settled_at"))
        if a and b and b >= a:
            durations.append((b - a).total_seconds())
    ttc_avg = round(sum(durations) / len(durations), 1) if durations else None

    # Exception rate (% of window transfers with any flag)
    flagged = 0
    total_in_window = 0
    async for t in db[TRANSFERS].find(
        {"created_at": {"$gte": window_start}},
        {"_id": 0, "reconciliation": 1, "canonical_status": 1, "status": 1, "reference": 1},
    ):
        total_in_window += 1
        recon = t.get("reconciliation") or {}
        is_flagged = False
        if recon:
            if recon.get("currency_mismatch"):
                is_flagged = True
            if abs(float(recon.get("delta_amount") or 0)) >= 0.01:
                is_flagged = True
            if recon.get("matched") is False:
                is_flagged = True
        if not (t.get("reference") or "").strip():
            is_flagged = True
        cs = t.get("canonical_status") or (
            "rejected" if t.get("status") in ("failed", "returned", "cancelled")
            else "")
        if cs == CS_REJECTED:
            is_flagged = True
        if is_flagged:
            flagged += 1
    exception_rate = (round(flagged / total_in_window, 4)
                       if total_in_window else 0.0)

    return {
        "window_days": window_days,
        "as_of": _iso(now),
        # Status counts
        "pending_review_count": counts.get(CS_PENDING_REVIEW, 0),
        "matched_count": counts.get(CS_MATCHED, 0),
        "confirmed_count": counts.get(CS_CONFIRMED, 0),
        "rejected_count": counts.get(CS_REJECTED, 0),
        "submitted_count": counts.get(CS_SUBMITTED, 0),
        # Volumes
        "today_volume_total": round(today_v, 2),
        "today_volume_count": today_n,
        "volume_30d_total": round(win_v, 2),
        "volume_30d_count": win_n,
        "sepa_volume_30d": round(sepa_v, 2),
        "sepa_volume_30d_count": sepa_n,
        "swift_volume_30d": round(swift_v, 2),
        "swift_volume_30d_count": swift_n,
        # Ops health
        "time_to_confirm_avg_seconds": ttc_avg,
        "exception_rate": exception_rate,
        "exception_count": flagged,
        "window_total_count": total_in_window,
    }


# ═════════════════════════════════════════════════════════════════════════
# Polling helper (H1.2 — webhook+polling 4c)
# ═════════════════════════════════════════════════════════════════════════

async def sync_pending_transfers() -> dict:
    """Iterate non-terminal transfers and ask each transfer's adapter for the
    current status. Returns a scan summary.

    The Manual adapter is a no-op here (status already lives in our DB), but
    once a real provider lands this is where webhook gaps get filled in.
    """
    scanned = 0
    updated = 0
    cursor = db[TRANSFERS].find(
        {"$and": [
            {"$or": [
                {"canonical_status": {"$nin": list(TERMINAL_CANONICAL)}},
                {"canonical_status": {"$exists": False}},
            ]},
            {"$or": [
                {"status": {"$nin": ["confirmed", "failed", "returned", "cancelled"]}},
                {"status": {"$exists": False}},
            ]},
        ]},
        {"_id": 0, "id": 1, "provider": 1, "canonical_status": 1, "status": 1},
    )
    async for t in cursor:
        scanned += 1
        adapter = get_adapter_for(t.get("provider") or "manual_ops")
        try:
            st = await adapter.get_transfer_status(t["id"])
        except Exception as e:  # pragma: no cover
            logger.warning("adapter status failed for %s: %s", t["id"], e)
            continue
        # Manual adapter just mirrors DB — no DB update needed.
        # Real adapters would update canonical_status here if it differs.
        current = t.get("canonical_status") or _cs(t)
        if st.canonical_status and st.canonical_status != current and st.canonical_status in {
            "submitted", "pending_review", "matched", "confirmed", "rejected",
        }:
            await db[TRANSFERS].update_one(
                {"id": t["id"]},
                {"$set": {"canonical_status": st.canonical_status,
                           "updated_at": _now()}},
            )
            updated += 1
    return {"scanned": scanned, "updated": updated, "ran_at": _iso(_utcnow())}


async def ensure_treasury_indexes() -> None:
    try:
        await db[WEBHOOK_EVENTS].create_index("external_event_id", unique=True)
        await db[WEBHOOK_EVENTS].create_index("received_at")
        logger.info("TREASURY: indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("TREASURY: index ensure failed: %s", e)


# ═════════════════════════════════════════════════════════════════════════
# Router
# ═════════════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api", tags=["lumen-treasury"])


@router.get("/admin/treasury/kpis")
async def admin_treasury_kpis(_=Depends(require_admin), window: int = 30):
    if window < 1 or window > 365:
        window = 30
    return await compute_kpis(window_days=window)


@router.get("/admin/treasury/pulse")
async def admin_treasury_pulse(_=Depends(require_admin)):
    full = await compute_kpis(window_days=30)
    return {
        "as_of": full["as_of"],
        "pending_review_count": full["pending_review_count"],
        "matched_count": full["matched_count"],
        "confirmed_count": full["confirmed_count"],
        "rejected_count": full["rejected_count"],
        "today_volume_total": full["today_volume_total"],
        "time_to_confirm_avg_seconds": full["time_to_confirm_avg_seconds"],
        "exception_rate": full["exception_rate"],
    }


class WebhookEventIn(BaseModel):
    external_event_id: str = Field(..., min_length=2, max_length=200)
    transfer_id: Optional[str] = None
    status: Optional[str] = None        # provider-native; not necessarily canonical
    settled_at: Optional[str] = None
    provider_ref: Optional[str] = None
    raw: Optional[dict] = None


@router.post("/lumen/banking/webhook/{provider}")
async def banking_webhook(provider: str, payload: WebhookEventIn,
                            request: Request):
    """Webhook ingress — idempotent by `external_event_id`.

    Real providers will sign requests; we will plug HMAC verification per
    provider via the adapter (Wise/BC have well-known schemes). The manual
    provider has no signature — it is accepted as-is for ops simulations.
    """
    # Dedup
    existing = await db[WEBHOOK_EVENTS].find_one(
        {"external_event_id": payload.external_event_id},
        {"_id": 0, "id": 1},
    )
    if existing:
        return {"ok": True, "dedup": True, "event_id": existing["id"]}

    # Resolve adapter (today: only manual_ops, but contract is stable)
    _adapter = get_adapter_for(provider)

    event_doc = {
        "id": f"wh-{uuid.uuid4().hex[:14]}",
        "provider": provider,
        "external_event_id": payload.external_event_id,
        "transfer_id": payload.transfer_id,
        "received_at": _now(),
        "request_id": request.headers.get("x-request-id"),
        "payload": payload.model_dump(),
    }
    await db[WEBHOOK_EVENTS].insert_one(event_doc)

    # Manual provider: webhook is informational. Real providers would map
    # status → canonical and update the transfer here.
    return {"ok": True, "event_id": event_doc["id"], "provider": provider,
            "adapter": _adapter.name}


@router.post("/admin/treasury/sync")
async def admin_treasury_sync(
    admin=Depends(require_admin),
    _perm=Depends(_lr2_perm("distribution", "approve")),
):
    result = await sync_pending_transfers()
    return {"ok": True, **result}


@router.get("/admin/treasury/adapters")
async def admin_treasury_adapters(_=Depends(require_admin)):
    from lumen_banking_adapter import ADAPTER_REGISTRY
    return {
        "adapters": [
            {"provider": k, "name": getattr(v, "name", k),
             "class": v.__class__.__name__}
            for k, v in ADAPTER_REGISTRY.items()
        ],
        "default": "manual_ops",
    }


__all__ = [
    "router",
    "compute_kpis",
    "sync_pending_transfers",
    "ensure_treasury_indexes",
]
