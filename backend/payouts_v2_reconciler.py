"""
PAY-V2-P4 — Reconciliation Observer (PASSIVE).

Architectural contract (locked by 2026-05-24 spec):

    provider truth
        → reconciliation line
        → divergence events
        → admin / operator visibility
        → explicit resolution

This observer NEVER mutates `payout_items_v2.state` directly. It only writes:
  • `payout_reconciliation_runs`  — one row per run (audit)
  • `payout_divergence_events`    — one row per detected discrepancy
And the admin endpoints in `payouts_v2_api.py` give operators the visibility
+ explicit resolution surface.

Divergence taxonomy (closed set):
  • provider_settled_local_pending
  • provider_failed_local_inflight
  • amount_mismatch
  • currency_mismatch
  • missing_provider_object
  • duplicate_provider_transfer
  • stale_local_state

Severity:
  • info       — informational, no operator action expected
  • warning    — review next business day
  • critical   — pause + investigate now

Modes:
  • passive (default)  — never mutates payout state; just records divergence
  • active             — operator-opt-in path that auto-acks tiny rounding
                         (deferred — NOT shipped in v1, returns 501)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("payouts_v2_reconciler")


# ── Closed set of divergence types ───────────────────────────────────────
DIVERGENCE_TYPES = {
    "provider_settled_local_pending": "warning",
    "provider_failed_local_inflight": "critical",
    "amount_mismatch": "critical",
    "currency_mismatch": "critical",
    "missing_provider_object": "warning",
    "duplicate_provider_transfer": "critical",
    "stale_local_state": "info",
}


@dataclass
class ProviderTruth:
    """What the provider says about a given item, by provider_ref."""

    provider_ref: str
    status: Optional[str]               # provider's authoritative status
    amount: Optional[float]
    currency: Optional[str]
    settled_at: Optional[str]
    found: bool                         # False = missing_provider_object


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _money_close(a: float, b: float, eps: float = 0.01) -> bool:
    try:
        return abs(float(a) - float(b)) <= eps
    except Exception:
        return False


# ── Mock truth source (used until Stripe live is wired) ──────────────────
# In MOCK mode, our local state IS the truth — no real provider exists.
# To make the observer machinery testable BEFORE live, an env knob can
# inject one synthetic divergence per run.
RECONCILE_INJECT_DIVERGENCE = os.getenv("RECONCILE_INJECT_DIVERGENCE", "").lower() in ("1", "true", "yes")
RECONCILE_INJECT_KIND = os.getenv("RECONCILE_INJECT_KIND", "amount_mismatch")


async def _fetch_provider_truth_mock(db, item: Dict[str, Any]) -> ProviderTruth:
    """Mock truth: mirror local state. Optionally inject a synthetic divergence."""
    pref = item.get("provider_ref")
    if not pref:
        return ProviderTruth(
            provider_ref="",
            status=None, amount=None, currency=None, settled_at=None,
            found=False,
        )

    # Inject a synthetic discrepancy for the FIRST settled item we encounter
    # (admin-driven, deterministic-enough for E2E tests).
    if RECONCILE_INJECT_DIVERGENCE and item.get("state") in ("settled", "confirmed"):
        kind = RECONCILE_INJECT_KIND
        if kind == "amount_mismatch":
            return ProviderTruth(
                provider_ref=pref,
                status=item.get("state"),
                amount=float(item.get("amount", 0)) + 1.23,  # synthetic drift
                currency=item.get("currency", "USD"),
                settled_at=_now_iso(),
                found=True,
            )
        if kind == "provider_failed_local_inflight":
            return ProviderTruth(
                provider_ref=pref, status="failed",
                amount=item.get("amount"), currency=item.get("currency", "USD"),
                settled_at=_now_iso(), found=True,
            )
        if kind == "missing_provider_object":
            return ProviderTruth(
                provider_ref=pref, status=None,
                amount=None, currency=None, settled_at=None, found=False,
            )

    return ProviderTruth(
        provider_ref=pref,
        status=item.get("state"),
        amount=float(item.get("amount") or 0),
        currency=item.get("currency", "USD"),
        settled_at=item.get("settled_at") or item.get("updated_at"),
        found=True,
    )


# ── Divergence detection ─────────────────────────────────────────────────
# Pure function. Inputs: (local payout_item dict, provider truth).
# Output: list of (divergence_type, severity, note) tuples — usually 0 or 1.
def detect_divergences(item: Dict[str, Any], truth: ProviderTruth) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    local_state = (item.get("state") or "").lower()
    local_amount = float(item.get("amount") or 0)
    local_currency = (item.get("currency") or "USD").upper()

    if not truth.found:
        # Provider doesn't recognise this provider_ref → critical iff we
        # believe it's already submitted; otherwise just informational.
        sev = "critical" if local_state in ("initiated", "in_flight", "confirmed", "settled") \
            else "info"
        out.append(("missing_provider_object", sev,
                    f"local_state={local_state} but provider has no record"))
        return out

    # provider says settled but we still show pending-ish
    if truth.status == "settled" and local_state in ("queued", "initiated", "in_flight", "confirmed"):
        out.append(("provider_settled_local_pending",
                    DIVERGENCE_TYPES["provider_settled_local_pending"],
                    f"provider=settled local={local_state}"))

    # provider says failed but we still show in flight
    if truth.status in ("failed", "returned") and local_state in ("initiated", "in_flight", "confirmed", "settled"):
        out.append(("provider_failed_local_inflight",
                    DIVERGENCE_TYPES["provider_failed_local_inflight"],
                    f"provider={truth.status} local={local_state}"))

    # amount drift
    if truth.amount is not None and not _money_close(truth.amount, local_amount):
        out.append(("amount_mismatch",
                    DIVERGENCE_TYPES["amount_mismatch"],
                    f"provider={truth.amount:.2f} local={local_amount:.2f}"))

    # currency mismatch
    if truth.currency and truth.currency.upper() != local_currency:
        out.append(("currency_mismatch",
                    DIVERGENCE_TYPES["currency_mismatch"],
                    f"provider={truth.currency} local={local_currency}"))

    # stale local state — settled > 7d ago but still not reconciled
    try:
        if local_state == "settled" and item.get("settled_at"):
            settled_dt = datetime.fromisoformat(item["settled_at"].replace("Z", "+00:00"))
            age_d = (datetime.now(timezone.utc) - settled_dt).days
            if age_d > 7 and item.get("reconciled") is not True:
                out.append(("stale_local_state",
                            DIVERGENCE_TYPES["stale_local_state"],
                            f"settled {age_d}d ago, never reconciled"))
    except Exception:
        pass

    return out


# ── Core run ─────────────────────────────────────────────────────────────
async def run_reconciliation(
    db,
    *,
    mode: str = "passive",
    window_minutes: int = 60 * 24,
    actor: str = "scheduler",
) -> Dict[str, Any]:
    """Run one reconciliation pass.

    mode:
      "passive" — observe-only (default, only mode shipped in v1)
      "active"  — operator-opt-in auto-resolve (NOT shipped; raises)

    Returns a summary dict + persists a row to `payout_reconciliation_runs`.
    """
    if mode == "active":
        raise NotImplementedError(
            "Active reconciliation is operator-opt-in only and not enabled in v1. "
            "Use passive mode + explicit divergence resolution."
        )

    run_id = _new_id("recon")
    started_at = _now_iso()
    t0 = time.time()

    # Query items in states that could have provider truth to compare against.
    # We scan a rolling window keyed by claimed_at OR updated_at (best-effort).
    cutoff = datetime.now(timezone.utc).timestamp() - window_minutes * 60
    q = {
        "state": {"$in": ["initiated", "in_flight", "confirmed", "settled", "failed", "returned"]},
        "provider_ref": {"$exists": True, "$ne": None},
    }

    scanned = 0
    discrepancies = 0
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    items_with_divergence: List[str] = []

    cur = db.payout_items_v2.find(q, {"_id": 0}).sort("updated_at", -1).limit(500)
    async for item in cur:
        # filter by recency in Python so we don't depend on a specific date field
        ts_field = item.get("settled_at") or item.get("updated_at") or item.get("created_at")
        if ts_field:
            try:
                ts = datetime.fromisoformat(ts_field.replace("Z", "+00:00")).timestamp()
                if ts < cutoff:
                    continue
            except Exception:
                pass

        scanned += 1
        truth = await _fetch_provider_truth_mock(db, item)
        found = detect_divergences(item, truth)
        if not found:
            continue
        items_with_divergence.append(item.get("item_id"))
        for kind, severity, note in found:
            discrepancies += 1
            by_type[kind] = by_type.get(kind, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            await db.payout_divergence_events.insert_one({
                "divergence_id": _new_id("div"),
                "run_id": run_id,
                "item_id": item.get("item_id"),
                "batch_id": item.get("batch_id"),
                "provider_ref": item.get("provider_ref"),
                "divergence_type": kind,
                "severity": severity,
                "note": note,
                "local_snapshot": {
                    "state": item.get("state"),
                    "amount": item.get("amount"),
                    "currency": item.get("currency", "USD"),
                    "settled_at": item.get("settled_at"),
                },
                "provider_snapshot": {
                    "status": truth.status,
                    "amount": truth.amount,
                    "currency": truth.currency,
                    "settled_at": truth.settled_at,
                    "found": truth.found,
                },
                "state": "open",
                "created_at": _now_iso(),
                "resolved_at": None,
                "resolved_by": None,
                "resolution": None,
                "resolution_note": None,
            })

    duration_ms = int((time.time() - t0) * 1000)
    finished_at = _now_iso()

    run_doc = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "mode": mode,
        "actor": actor,
        "window_minutes": window_minutes,
        "scanned": scanned,
        "discrepancies": discrepancies,
        "by_type": by_type,
        "by_severity": by_severity,
        "items_with_divergence": items_with_divergence,
        "injected": RECONCILE_INJECT_DIVERGENCE,
    }
    # Insert a copy so the _id Mongo writes back doesn't leak into the return value.
    await db.payout_reconciliation_runs.insert_one(dict(run_doc))

    # ── Threshold alert (P4 Observability bridge) ────────────────────────
    # When a run produces ≥ RECONCILE_ALERT_CRITICAL_THRESHOLD new critical
    # divergences, escalate via observability.capture_alert. No DB write —
    # divergences are already persisted in payout_divergence_events.
    # No-op if SENTRY_DSN unset; safe to call unconditionally.
    try:
        threshold = int(os.getenv("RECONCILE_ALERT_CRITICAL_THRESHOLD", "1") or 1)
    except Exception:
        threshold = 1
    crit_new = int(by_severity.get("critical", 0) or 0)
    if threshold > 0 and crit_new >= threshold:
        try:
            import observability  # local import — observability.py lives next to us
            observability.capture_alert(
                subsystem="reconciliation",
                message=(
                    f"Reconciliation produced {crit_new} critical divergence(s) "
                    f"(threshold={threshold}, run={run_id})"
                ),
                level="error" if crit_new >= max(threshold * 2, 3) else "warning",
                tags={
                    "run_id": run_id,
                    "mode": mode,
                    "actor": actor,
                },
                extra={
                    "scanned": scanned,
                    "discrepancies": discrepancies,
                    "by_severity": by_severity,
                    "by_type": by_type,
                    "window_minutes": window_minutes,
                    "duration_ms": duration_ms,
                },
            )
            logger.warning(
                "RECONCILE ALERT: run=%s critical=%d ≥ threshold=%d (Sentry captured)",
                run_id, crit_new, threshold,
            )
        except Exception:
            logger.exception("RECONCILE ALERT: capture failed (continuing)")

    logger.info(
        "RECONCILE run=%s scanned=%d discrepancies=%d by_severity=%s duration_ms=%d",
        run_id, scanned, discrepancies, by_severity, duration_ms,
    )
    return run_doc


# ── Background loop ──────────────────────────────────────────────────────
async def reconciliation_loop(db, interval_sec: Optional[int] = None) -> None:
    """Long-running background loop. Disable by setting interval_sec=0
    (or env RECONCILE_INTERVAL_SEC=0)."""
    if interval_sec is None:
        try:
            interval_sec = int(os.getenv("RECONCILE_INTERVAL_SEC", "1800") or 1800)
        except Exception:
            interval_sec = 1800

    if not interval_sec or interval_sec <= 0:
        logger.info("RECONCILE LOOP: disabled (interval=0)")
        return

    # Initial defer so we don't hammer the DB during boot bootstrap.
    await asyncio.sleep(min(60, interval_sec))
    logger.info("RECONCILE LOOP: started (interval %ds)", interval_sec)

    while True:
        try:
            await run_reconciliation(db, mode="passive", actor="loop")
        except Exception:
            logger.exception("RECONCILE LOOP: tick failed (continuing)")
            try:
                import observability
                observability.capture_worker_exception("reconciliation_loop", _last_exc())
            except Exception:
                pass
        await asyncio.sleep(interval_sec)


def _last_exc() -> BaseException:  # tiny helper to satisfy Sentry tag signature
    import sys
    et, ev, _ = sys.exc_info()
    return ev or RuntimeError("unknown")


# ── Read API helpers used by the HTTP layer ──────────────────────────────
async def list_runs(db, *, limit: int = 50) -> List[Dict[str, Any]]:
    cur = db.payout_reconciliation_runs.find({}, {"_id": 0}).sort(
        "started_at", -1
    ).limit(max(1, min(int(limit), 200)))
    return [r async for r in cur]


async def list_divergences(
    db, *, state: Optional[str] = None,
    severity: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if state:
        q["state"] = state
    if severity:
        q["severity"] = severity
    if item_id:
        q["item_id"] = item_id
    cur = db.payout_divergence_events.find(q, {"_id": 0}).sort(
        "created_at", -1
    ).limit(max(1, min(int(limit), 500)))
    return [d async for d in cur]


async def resolve_divergence(
    db, *, divergence_id: str, resolution: str, note: str, actor_user_id: str,
) -> bool:
    """Operator explicit resolution. NEVER mutates payout_items_v2.
    `resolution` ∈ {accepted, rejected, manual_fixed, retained_under_law}.
    Returns True if a row was updated.
    """
    if resolution not in ("accepted", "rejected", "manual_fixed", "retained_under_law"):
        raise ValueError("invalid resolution code")
    upd = await db.payout_divergence_events.update_one(
        {"divergence_id": divergence_id, "state": "open"},
        {"$set": {
            "state": "resolved",
            "resolved_at": _now_iso(),
            "resolved_by": actor_user_id,
            "resolution": resolution,
            "resolution_note": note,
        }},
    )
    return bool(upd.matched_count)


async def summary(db) -> Dict[str, Any]:
    """Health tile for admin operational UI."""
    last_run = await db.payout_reconciliation_runs.find_one(
        {}, {"_id": 0}, sort=[("started_at", -1)],
    )
    open_total = await db.payout_divergence_events.count_documents({"state": "open"})
    open_critical = await db.payout_divergence_events.count_documents({
        "state": "open", "severity": "critical",
    })
    open_warning = await db.payout_divergence_events.count_documents({
        "state": "open", "severity": "warning",
    })
    open_info = await db.payout_divergence_events.count_documents({
        "state": "open", "severity": "info",
    })
    return {
        "last_run": last_run,
        "open_total": open_total,
        "open_critical": open_critical,
        "open_warning": open_warning,
        "open_info": open_info,
        "mode": "passive",
    }
