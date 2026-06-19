"""
PAY-V2-P3 — Autonomous Payout Worker / Execution Engine.

Turns the P1 substrate (batches, items, events, idempotency, providers) into
an actual *operating system* — items flow through the state machine
without admin intervention.

Architectural principles (locked, per user spec):

  • Lease-based ownership — NO `while True: find_one()`. Workers claim items
    atomically via `find_one_and_update` with a TTL lease.
  • Heartbeat — claimed items get `last_heartbeat` updated every cycle.
    Stale leases (heartbeat older than `lease_sec * 2`) are reclaimed by
    a separate reaper loop.
  • Per-item isolation — one failed item does NOT break the loop or the
    batch (Pr-6). Every step is wrapped.
  • Idempotent provider execution — `idempotency_key` already lives on each
    payout_item (created at batch release). Worker re-passes it on every
    retry so the rail dedupes server-side.
  • Retry with exponential backoff — transient failures (`rate_limited`,
    `provider_unavailable`, timeout) reschedule `next_attempt_at`.
  • Dead-letter — after `max_attempts` the item moves to terminal `failed`
    with kind="exhausted" event.
  • Provider timeout handling — every `create_payout` call wrapped in
    `asyncio.wait_for`. Timeout is a transient failure.
  • Stuck payout recovery — items stuck in `initiated`/`in_flight` past a
    threshold WITHOUT provider webhook are surfaced via worker_status
    (admin sees "needs attention" — does NOT auto-advance them in live mode).
  • Mock advancer — only for the `mock` rail: after `MOCK_ADVANCE_DELAY_SEC`
    a separate ticker walks mock items through in_flight → confirmed →
    settled, simulating webhook arrival. Live rails wait for real webhooks.
  • Append-only audit — every worker action emits an event into
    `payout_v2_events` (Pr-1).

State extension (additive, does NOT touch the sealed substrate state
machine in payouts_v2.py):

  Worker tracking fields on payout_items_v2:
    - claimed_by:        worker_id | None
    - claimed_at:        ISO ts | None
    - lease_until:       ISO ts | None
    - last_heartbeat:    ISO ts | None
    - attempt_count:     int (number of provider attempts)
    - next_attempt_at:   ISO ts (when retry becomes eligible)
    - last_error:        str | None (last provider error message)
    - last_error_code:   str | None (normalized code from PayoutResult)
    - dead_lettered:     bool (item moved to terminal failed by exhaustion)

The canonical state machine (queued / initiated / in_flight / confirmed /
settled / failed / returned / disputed / cancelled / reconciled) is
unchanged. Worker reads `status=queued AND next_attempt_at <= now AND
(claimed_by IS NULL OR lease_until < now)` and walks items forward.

Configuration (all via env, sane defaults):
  PAY_V2_WORKER_ENABLED            1
  PAY_V2_WORKER_INTERVAL_SEC       5
  PAY_V2_WORKER_BATCH_SIZE         10
  PAY_V2_WORKER_LEASE_SEC          60
  PAY_V2_WORKER_HEARTBEAT_SEC      20
  PAY_V2_WORKER_MAX_ATTEMPTS       5
  PAY_V2_WORKER_TIMEOUT_SEC        30
  PAY_V2_WORKER_BACKOFF_BASE_SEC   10
  PAY_V2_WORKER_BACKOFF_MAX_SEC    600
  PAY_V2_WORKER_STUCK_AFTER_SEC    900
  PAY_V2_MOCK_ADVANCE_ENABLED      1
  PAY_V2_MOCK_ADVANCE_DELAY_SEC    2
  PAY_V2_REAPER_INTERVAL_SEC       30
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import payouts_v2 as pv2
from integrations.settlement import PayoutRequest, PayoutResult, SettlementProvider
from integrations.settlement_mock import MockSettlementProvider
from integrations.settlement_stripe import StripeConnectSettlementProvider
from integrations.settlement_paypal import PayPalPayoutsSettlementProvider

logger = logging.getLogger("payouts_v2_worker")


# ──────────────────────────────────────────────────────────────────────
# Config (read at boot — env-driven, no hardcoded literals)
# ──────────────────────────────────────────────────────────────────────
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class WorkerConfig:
    def __init__(self):
        self.enabled = _env_bool("PAY_V2_WORKER_ENABLED", True)
        self.interval_sec = _env_int("PAY_V2_WORKER_INTERVAL_SEC", 5)
        self.batch_size = _env_int("PAY_V2_WORKER_BATCH_SIZE", 10)
        self.lease_sec = _env_int("PAY_V2_WORKER_LEASE_SEC", 60)
        self.heartbeat_sec = _env_int("PAY_V2_WORKER_HEARTBEAT_SEC", 20)
        self.max_attempts = _env_int("PAY_V2_WORKER_MAX_ATTEMPTS", 5)
        self.timeout_sec = _env_int("PAY_V2_WORKER_TIMEOUT_SEC", 30)
        self.backoff_base_sec = _env_int("PAY_V2_WORKER_BACKOFF_BASE_SEC", 10)
        self.backoff_max_sec = _env_int("PAY_V2_WORKER_BACKOFF_MAX_SEC", 600)
        self.stuck_after_sec = _env_int("PAY_V2_WORKER_STUCK_AFTER_SEC", 900)
        self.mock_advance_enabled = _env_bool("PAY_V2_MOCK_ADVANCE_ENABLED", True)
        self.mock_advance_delay_sec = _env_int("PAY_V2_MOCK_ADVANCE_DELAY_SEC", 2)
        self.reaper_interval_sec = _env_int("PAY_V2_REAPER_INTERVAL_SEC", 30)


CFG = WorkerConfig()


# ──────────────────────────────────────────────────────────────────────
# Provider registry — worker reads provider by rail name.
# PAY-V2-P2A:
#   - mock           → MockSettlementProvider              (always)
#   - stripe_connect → StripeConnectSettlementProvider     (active if STRIPE_API_KEY set)
#   - paypal         → PayPalPayoutsSettlementProvider     (dormant scaffold)
# Adapters are constructed at import time. They self-disable cleanly
# when their env keys are missing — `health()` reports unavailable and
# `create_payout` returns `provider_unavailable`.
# ──────────────────────────────────────────────────────────────────────
_PROVIDERS_BY_RAIL: Dict[str, SettlementProvider] = {
    "mock":           MockSettlementProvider(),
    "stripe_connect": StripeConnectSettlementProvider(),
    "paypal":         PayPalPayoutsSettlementProvider(),
}


def get_provider_for_rail(rail: str) -> SettlementProvider:
    """Return the SettlementProvider for a given rail. Falls back to mock
    if the rail isn't wired (so P3 stays demoable without P2 adapters)."""
    return _PROVIDERS_BY_RAIL.get(rail) or _PROVIDERS_BY_RAIL["mock"]


# Worker identity (host-stable, instance-unique)
WORKER_ID = f"worker_{uuid.uuid4().hex[:10]}"


# Normalized transient error codes (eligible for retry)
TRANSIENT_ERROR_CODES = {
    "rate_limited", "provider_unavailable", "timeout", "network_error",
}

# Normalized terminal error codes (NO retry — admin intervention)
TERMINAL_ERROR_CODES = {
    "invalid_destination", "kyc_required", "blocked", "insufficient_funds",
}


# ──────────────────────────────────────────────────────────────────────
# Time helpers
# ──────────────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _compute_backoff_sec(attempt: int) -> int:
    """Exponential backoff with full jitter, capped at backoff_max_sec.

    attempt=1 → base * 2^0 = base
    attempt=2 → base * 2^1 = 2*base
    attempt=3 → base * 2^2 = 4*base
    ...
    Then jittered uniformly in [0, calculated] to spread thundering herd.
    """
    base = max(1, CFG.backoff_base_sec)
    raw = base * (2 ** max(0, attempt - 1))
    capped = min(raw, CFG.backoff_max_sec)
    # Full jitter (AWS-recommended): random in [base, capped]
    lo = base
    hi = max(lo, capped)
    return random.randint(lo, hi)


# ──────────────────────────────────────────────────────────────────────
# Atomic item claim — lease semantics.
# ──────────────────────────────────────────────────────────────────────
async def _claim_one_item(db) -> Optional[Dict[str, Any]]:
    """Atomically claim ONE queued item that is eligible to be worked on.

    Eligibility:
      • status == queued
      • next_attempt_at is null OR <= now
      • not currently claimed by a live lease (claimed_by null OR lease expired)

    Uses Mongo's `find_one_and_update` for atomicity — no two workers can
    claim the same item even under high concurrency.
    """
    now_iso = _now_iso()
    lease_until = _iso(_now() + timedelta(seconds=CFG.lease_sec))
    filt = {
        "status": pv2.ITEM_QUEUED,
        "$and": [
            {"$or": [
                {"next_attempt_at": {"$exists": False}},
                {"next_attempt_at": None},
                {"next_attempt_at": {"$lte": now_iso}},
            ]},
            {"$or": [
                {"claimed_by": {"$exists": False}},
                {"claimed_by": None},
                {"lease_until": {"$lt": now_iso}},
            ]},
        ],
    }
    update = {
        "$set": {
            "claimed_by": WORKER_ID,
            "claimed_at": now_iso,
            "lease_until": lease_until,
            "last_heartbeat": now_iso,
        },
        "$inc": {"claim_count": 1},
    }
    # sort by created_at ascending — fair FIFO
    item = await db.payout_items_v2.find_one_and_update(
        filt, update, sort=[("created_at", 1)], return_document=True,
        projection={"_id": 0},
    )
    return item


async def _heartbeat_item(db, *, item_id: str) -> None:
    """Extend the lease for a claimed item. Called periodically while we
    work on it. If the item was reclaimed by another worker (claimed_by
    changed), the update affects 0 docs — the caller should bail."""
    now_iso = _now_iso()
    lease_until = _iso(_now() + timedelta(seconds=CFG.lease_sec))
    await db.payout_items_v2.update_one(
        {"item_id": item_id, "claimed_by": WORKER_ID},
        {"$set": {"last_heartbeat": now_iso, "lease_until": lease_until}},
    )


async def _release_item_lease(db, *, item_id: str, reason: str = "released") -> None:
    """Drop the worker's claim on an item — used on backoff, terminal
    states, or graceful exit. Emits an event for traceability."""
    await db.payout_items_v2.update_one(
        {"item_id": item_id, "claimed_by": WORKER_ID},
        {"$set": {"claimed_by": None, "lease_until": None}},
    )
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="worker_released",
        actor=f"worker:{WORKER_ID}", payload={"reason": reason},
    )


async def _schedule_retry(
    db, *, item_id: str, attempt: int, error: str, error_code: Optional[str]
) -> int:
    """Mark item for retry with exponential backoff.
    Returns the backoff seconds applied (for logging/events)."""
    backoff = _compute_backoff_sec(attempt)
    next_at = _iso(_now() + timedelta(seconds=backoff))
    await db.payout_items_v2.update_one(
        {"item_id": item_id},
        {
            "$set": {
                "next_attempt_at": next_at,
                "last_error": error,
                "last_error_code": error_code,
                "claimed_by": None,
                "lease_until": None,
            },
            "$inc": {"attempt_count": 1},
        },
    )
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="retry_scheduled",
        actor=f"worker:{WORKER_ID}",
        payload={
            "attempt": attempt,
            "next_attempt_at": next_at,
            "backoff_sec": backoff,
            "error": error,
            "error_code": error_code,
        },
        reason=error,
    )
    return backoff


async def _dead_letter(
    db, *, item_id: str, attempt: int, error: str, error_code: Optional[str]
) -> None:
    """Move item to terminal `failed` (exhausted). Emits BOTH the normal
    item state transition (`failed`) AND an `exhausted` kind event for
    the operational queue to surface."""
    await db.payout_items_v2.update_one(
        {"item_id": item_id},
        {"$set": {
            "dead_lettered": True,
            "claimed_by": None,
            "lease_until": None,
            "next_attempt_at": None,
            # Persist attempt_count = the attempt # that exhausted. The
            # _schedule_retry path uses $inc; the exhaustion path is a
            # direct set so the DB matches the result dict (attempts=N).
            "attempt_count": attempt,
            "last_error": error,
            "last_error_code": error_code,
        }},
    )
    try:
        await pv2.transition_item(
            db, item_id=item_id, to_status=pv2.ITEM_FAILED,
            actor=f"worker:{WORKER_ID}",
            payload={"error": error, "error_code": error_code, "attempts": attempt},
            reason=f"exhausted after {attempt} attempts: {error}",
        )
    except ValueError:
        # Item already in a terminal state — log and move on.
        logger.exception("dead_letter: cannot transition item %s to failed", item_id)
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="exhausted",
        actor=f"worker:{WORKER_ID}",
        payload={"attempts": attempt, "error": error, "error_code": error_code},
        reason="max_attempts_reached",
    )


# ──────────────────────────────────────────────────────────────────────
# Provider invocation (with timeout, idempotency, normalized errors)
# ──────────────────────────────────────────────────────────────────────
async def _call_provider(item: Dict[str, Any]) -> PayoutResult:
    """Build the vendor-neutral PayoutRequest from a payout_item and call
    the provider for its rail. All errors normalized to a PayoutResult —
    the worker never raises out of this function."""
    rail = item.get("rail") or "mock"
    provider = get_provider_for_rail(rail)
    req = PayoutRequest(
        item_id=item["item_id"],
        idempotency_key=item.get("idempotency_key") or f"item:{item['item_id']}",
        developer_id=item["developer_id"],
        amount=float(item["amount"]),
        currency=item.get("currency") or "USD",
        rail=rail,
        rail_account=item.get("rail_account") or {},
        description=f"Payout item {item['item_id']} for {item['developer_id']}",
        metadata={"batch_id": item.get("batch_id")},
    )
    try:
        # asyncio.wait_for so a hanging provider never blocks the worker.
        return await asyncio.wait_for(
            provider.create_payout(req), timeout=CFG.timeout_sec,
        )
    except asyncio.TimeoutError:
        return PayoutResult(
            success=False, provider_ref=None, status="failed",
            error=f"provider timeout after {CFG.timeout_sec}s",
            error_code="timeout",
        )
    except Exception as e:  # noqa: BLE001 — normalize ALL provider errors
        logger.exception(
            "provider %s raised on item %s", provider.name, item["item_id"]
        )
        return PayoutResult(
            success=False, provider_ref=None, status="failed",
            error=str(e) or "provider exception",
            error_code="provider_unavailable",
        )


def _classify_failure(error_code: Optional[str]) -> str:
    """Return 'transient' | 'terminal' | 'unknown' for the error_code."""
    if not error_code:
        return "unknown"
    if error_code in TRANSIENT_ERROR_CODES:
        return "transient"
    if error_code in TERMINAL_ERROR_CODES:
        return "terminal"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────
# Item lifecycle — one full pass on a claimed item.
# ──────────────────────────────────────────────────────────────────────
async def _process_claimed_item(db, item: Dict[str, Any]) -> Dict[str, Any]:
    """Walk a freshly-claimed queued item one step forward.

    Returns a small status dict for the loop's reporting.
    """
    item_id = item["item_id"]
    attempt_count = int(item.get("attempt_count", 0)) + 1  # this attempt #
    rail = item.get("rail") or "mock"

    # Emit "worker_claimed" first — operational visibility.
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="worker_claimed",
        actor=f"worker:{WORKER_ID}",
        payload={
            "worker_id": WORKER_ID,
            "attempt": attempt_count,
            "lease_until": item.get("lease_until"),
            "rail": rail,
        },
    )
    # Mid-step heartbeat (cheap; just keeps the lease fresh while we call
    # the provider).
    await _heartbeat_item(db, item_id=item_id)

    # Provider call (with timeout + normalized errors)
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="provider_called",
        actor=f"worker:{WORKER_ID}",
        payload={"provider": get_provider_for_rail(rail).name, "rail": rail,
                 "attempt": attempt_count},
    )
    result = await _call_provider(item)

    # ── Happy path ─────────────────────────────────────────────────
    if result.success:
        try:
            await pv2.transition_item(
                db, item_id=item_id, to_status=pv2.ITEM_INITIATED,
                actor=f"worker:{WORKER_ID}",
                payload={
                    "provider_ref": result.provider_ref,
                    "fees_provider": result.fees_provider,
                    "attempt": attempt_count,
                },
                reason="provider_accepted",
            )
        except ValueError:
            # Concurrent transition — log + bail without breaking the loop.
            logger.exception("transition queued→initiated failed for %s", item_id)
        # Release the lease — item is now in `initiated`, no longer in the
        # claim pool. Mock advancer / webhook drives the rest.
        await db.payout_items_v2.update_one(
            {"item_id": item_id, "claimed_by": WORKER_ID},
            {"$set": {
                "claimed_by": None, "lease_until": None,
                "attempt_count": attempt_count,
                "last_error": None, "last_error_code": None,
            }},
        )
        return {"item_id": item_id, "result": "initiated",
                "provider_ref": result.provider_ref}

    # ── Failure path ───────────────────────────────────────────────
    classification = _classify_failure(result.error_code)
    error_msg = result.error or "unknown provider error"
    error_code = result.error_code

    # If we already hit max attempts on this attempt, dead-letter regardless
    # of classification (a terminal error always dead-letters immediately
    # anyway — this just covers transient that ran out of retries).
    if attempt_count >= CFG.max_attempts or classification == "terminal":
        await _dead_letter(
            db, item_id=item_id, attempt=attempt_count,
            error=error_msg, error_code=error_code,
        )
        return {"item_id": item_id, "result": "exhausted",
                "attempts": attempt_count, "error_code": error_code}

    # Transient or unknown → reschedule with backoff.
    backoff = await _schedule_retry(
        db, item_id=item_id, attempt=attempt_count,
        error=error_msg, error_code=error_code,
    )
    return {"item_id": item_id, "result": "retry_scheduled",
            "attempts": attempt_count, "backoff_sec": backoff,
            "error_code": error_code}


# ──────────────────────────────────────────────────────────────────────
# Worker loop — drains the queue, batched per cycle.
# ──────────────────────────────────────────────────────────────────────
async def _drain_once(db) -> Dict[str, Any]:
    """One worker cycle. Claim up to `batch_size` items, walk each one
    step. Per-item isolation: ONE bad item never crashes the loop."""
    processed: List[Dict[str, Any]] = []
    for _ in range(CFG.batch_size):
        try:
            claimed = await _claim_one_item(db)
        except Exception:
            logger.exception("worker.claim error")
            break
        if claimed is None:
            break
        try:
            res = await _process_claimed_item(db, claimed)
            processed.append(res)
        except Exception as e:  # noqa: BLE001 — never break the loop
            logger.exception("worker.process error for item %s", claimed.get("item_id"))
            # Best-effort release the lease so another worker can retry it
            try:
                await _release_item_lease(
                    db, item_id=claimed["item_id"],
                    reason=f"worker_exception:{type(e).__name__}",
                )
            except Exception:
                pass
            processed.append({
                "item_id": claimed.get("item_id"), "result": "worker_error",
                "error": str(e),
            })
    return {
        "worker_id": WORKER_ID, "processed": len(processed),
        "items": processed, "at": _now_iso(),
    }


# ──────────────────────────────────────────────────────────────────────
# Stale-lease reaper — recovers items abandoned by crashed workers.
# ──────────────────────────────────────────────────────────────────────
async def _reap_stale_leases(db) -> Dict[str, Any]:
    """Find items whose lease expired (worker likely died) and release
    them back into the claim pool. Emits `lease_expired` events for audit.
    Items in non-claim-pool states (initiated/in_flight/etc.) get their
    stale lease cleared but stay where they are."""
    now_iso = _now_iso()
    # Read first so we can emit per-item events (find+update doesn't give
    # back the affected docs cleanly across motor versions).
    stale = await db.payout_items_v2.find(
        {
            "claimed_by": {"$ne": None},
            "lease_until": {"$ne": None, "$lt": now_iso},
        },
        {"_id": 0, "item_id": 1, "claimed_by": 1, "claimed_at": 1, "status": 1},
    ).to_list(200)
    if not stale:
        return {"reclaimed": 0}

    item_ids = [s["item_id"] for s in stale]
    await db.payout_items_v2.update_many(
        {"item_id": {"$in": item_ids}},
        {
            "$set": {"claimed_by": None, "lease_until": None},
            "$inc": {"reclaim_count": 1},
        },
    )
    for s in stale:
        await pv2.emit_event(
            db, scope="item", subject_id=s["item_id"], kind="lease_expired",
            actor=f"reaper:{WORKER_ID}",
            payload={
                "previous_worker": s.get("claimed_by"),
                "claimed_at": s.get("claimed_at"),
                "status_at_reclaim": s.get("status"),
            },
            reason="lease_expired",
        )
    logger.info("PAY-V2 reaper: reclaimed %d stale leases", len(stale))
    return {"reclaimed": len(stale), "items": item_ids}


# ──────────────────────────────────────────────────────────────────────
# Mock-rail advancer — simulates async webhook arrival for the mock
# provider. Walks items: initiated → in_flight → confirmed → settled.
# Live rails (Stripe / PayPal) wait for real webhooks — no advancer.
# ──────────────────────────────────────────────────────────────────────
_MOCK_ADVANCE_CHAIN = [
    (pv2.ITEM_INITIATED, pv2.ITEM_IN_FLIGHT),
    (pv2.ITEM_IN_FLIGHT, pv2.ITEM_CONFIRMED),
    (pv2.ITEM_CONFIRMED, pv2.ITEM_SETTLED),
]


async def _advance_mock_items_once(db) -> Dict[str, Any]:
    """Advance one step for all mock-rail items past the delay threshold."""
    if not CFG.mock_advance_enabled:
        return {"advanced": 0, "disabled": True}

    cutoff = _iso(_now() - timedelta(seconds=CFG.mock_advance_delay_sec))
    advanced: List[Dict[str, Any]] = []
    for src, dst in _MOCK_ADVANCE_CHAIN:
        # Item must be in `src` state on the mock rail, and the last status
        # change must be at least mock_advance_delay_sec old (so we don't
        # advance an item we just initiated in the same cycle).
        candidates = await db.payout_items_v2.find(
            {
                "rail": "mock",
                "status": src,
                # initiated_at / settled_at used as fallback timestamps
                "$or": [
                    {"status_history.0": {"$exists": False}},
                    {"status_history": {"$elemMatch": {"status": src, "at": {"$lte": cutoff}}}},
                ],
            },
            {"_id": 0, "item_id": 1, "amount": 1, "rail": 1, "status": 1, "provider_ref": 1},
        ).limit(100).to_list(100)
        for it in candidates:
            try:
                payload: Dict[str, Any] = {"source": "mock_advancer"}
                if dst == pv2.ITEM_SETTLED:
                    payload["fees_provider"] = 0.0
                    payload["fees_fx"] = 0.0
                await pv2.transition_item(
                    db, item_id=it["item_id"], to_status=dst,
                    actor=f"mock_advancer:{WORKER_ID}",
                    payload=payload, reason="mock_webhook_simulated",
                )
                advanced.append({"item_id": it["item_id"], "from": src, "to": dst})
            except ValueError:
                # Concurrent transition — skip.
                continue
    if advanced:
        logger.info("PAY-V2 mock advancer: advanced %d items", len(advanced))
    return {"advanced": len(advanced), "transitions": advanced[:50]}


# ──────────────────────────────────────────────────────────────────────
# Background loops (started from server.py at app boot)
# ──────────────────────────────────────────────────────────────────────
async def worker_loop(db) -> None:
    """Long-running worker drain loop. One per process; lease semantics
    let multiple processes safely run this concurrently in the future."""
    if not CFG.enabled:
        logger.info("PAY-V2 worker disabled (PAY_V2_WORKER_ENABLED=0)")
        return
    logger.info(
        "PAY-V2 worker started: id=%s interval=%ds batch=%d lease=%ds max_attempts=%d",
        WORKER_ID, CFG.interval_sec, CFG.batch_size, CFG.lease_sec,
        CFG.max_attempts,
    )
    while True:
        try:
            await _drain_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker_loop iteration failed (will retry)")
        try:
            await asyncio.sleep(CFG.interval_sec)
        except asyncio.CancelledError:
            raise


async def reaper_loop(db) -> None:
    """Long-running stale-lease reaper loop."""
    if not CFG.enabled:
        return
    logger.info("PAY-V2 reaper started: interval=%ds", CFG.reaper_interval_sec)
    while True:
        try:
            await _reap_stale_leases(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reaper_loop iteration failed (will retry)")
        try:
            await asyncio.sleep(CFG.reaper_interval_sec)
        except asyncio.CancelledError:
            raise


async def mock_advancer_loop(db) -> None:
    """Long-running mock-rail advancer loop. Simulates webhooks for the
    mock provider so demos see items reach `settled` end-to-end."""
    if not CFG.enabled or not CFG.mock_advance_enabled:
        return
    logger.info(
        "PAY-V2 mock advancer started: interval=%ds delay=%ds",
        CFG.interval_sec, CFG.mock_advance_delay_sec,
    )
    while True:
        try:
            await _advance_mock_items_once(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("mock_advancer_loop iteration failed (will retry)")
        try:
            await asyncio.sleep(CFG.interval_sec)
        except asyncio.CancelledError:
            raise


# ──────────────────────────────────────────────────────────────────────
# Operational visibility helpers (used by admin endpoints in *_api.py)
# ──────────────────────────────────────────────────────────────────────
async def worker_status_snapshot(db) -> Dict[str, Any]:
    """Aggregate current worker / queue health for the admin UI.

    Pr-7 (queue-first UX): everything an operator needs in one read.
    """
    now = _now()
    now_iso = _iso(now)
    stuck_cutoff = _iso(now - timedelta(seconds=CFG.stuck_after_sec))

    # Counts by status (cheap aggregation; capped collection sizes assumed
    # small for v2 — single org, single tenant)
    pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "amount": {"$sum": "$amount"},
        }},
    ]
    rows = await db.payout_items_v2.aggregate(pipeline).to_list(None)
    counts: Dict[str, int] = {s: 0 for s in pv2.ITEM_STATES}
    amounts: Dict[str, float] = {s: 0.0 for s in pv2.ITEM_STATES}
    for r in rows:
        s = r["_id"]
        counts[s] = int(r["count"])
        amounts[s] = round(float(r["amount"] or 0), 2)

    # Currently claimed (in-flight ownership)
    in_flight_owned = await db.payout_items_v2.count_documents({
        "claimed_by": {"$ne": None},
        "lease_until": {"$gte": now_iso},
    })
    # Stale leases waiting for reaper
    stale_leases = await db.payout_items_v2.count_documents({
        "claimed_by": {"$ne": None},
        "lease_until": {"$lt": now_iso},
    })
    # Items in `queued` awaiting retry backoff
    pending_retry = await db.payout_items_v2.count_documents({
        "status": pv2.ITEM_QUEUED,
        "next_attempt_at": {"$gt": now_iso},
    })
    # Items eligible to be claimed RIGHT NOW
    ready = await db.payout_items_v2.count_documents({
        "status": pv2.ITEM_QUEUED,
        "$and": [
            {"$or": [{"next_attempt_at": None}, {"next_attempt_at": {"$lte": now_iso}}]},
            {"$or": [{"claimed_by": None}, {"lease_until": {"$lt": now_iso}}]},
        ],
    })
    # Stuck items — initiated/in_flight too long (LIVE provider hasn't called
    # us back). Always 0 in pure-mock mode because advancer drains those.
    stuck = await db.payout_items_v2.count_documents({
        "status": {"$in": [pv2.ITEM_INITIATED, pv2.ITEM_IN_FLIGHT]},
        "initiated_at": {"$lt": stuck_cutoff},
    })
    # Dead-lettered
    exhausted = await db.payout_items_v2.count_documents({
        "dead_lettered": True,
    })

    # Top failing items (last 20, sorted by attempt_count desc)
    failing = await db.payout_items_v2.find(
        {"attempt_count": {"$gt": 0}, "status": pv2.ITEM_QUEUED},
        {"_id": 0, "item_id": 1, "developer_id": 1, "rail": 1,
         "attempt_count": 1, "last_error": 1, "last_error_code": 1,
         "next_attempt_at": 1, "amount": 1, "currency": 1},
    ).sort([("attempt_count", -1)]).limit(20).to_list(20)

    return {
        "worker_id": WORKER_ID,
        "config": {
            "enabled": CFG.enabled,
            "interval_sec": CFG.interval_sec,
            "batch_size": CFG.batch_size,
            "lease_sec": CFG.lease_sec,
            "heartbeat_sec": CFG.heartbeat_sec,
            "max_attempts": CFG.max_attempts,
            "timeout_sec": CFG.timeout_sec,
            "backoff_base_sec": CFG.backoff_base_sec,
            "backoff_max_sec": CFG.backoff_max_sec,
            "stuck_after_sec": CFG.stuck_after_sec,
            "mock_advance_enabled": CFG.mock_advance_enabled,
            "mock_advance_delay_sec": CFG.mock_advance_delay_sec,
        },
        "queue_health": {
            "ready": ready,
            "pending_retry": pending_retry,
            "in_flight_owned": in_flight_owned,
            "stale_leases": stale_leases,
            "stuck": stuck,
            "exhausted": exhausted,
        },
        "counts_by_status": counts,
        "amount_by_status": amounts,
        "failing_items": failing,
        "providers": {
            rail: prov.name for rail, prov in _PROVIDERS_BY_RAIL.items()
        },
        "as_of": now_iso,
    }


# ──────────────────────────────────────────────────────────────────────
# Admin actions (called from payouts_v2_api.py)
# ──────────────────────────────────────────────────────────────────────
async def admin_force_retry(db, *, item_id: str, actor: str) -> Dict[str, Any]:
    """Move an item back into the claim pool RIGHT NOW. Resets backoff,
    keeps attempt_count (so an admin can't accidentally infinite-loop a
    bad item). If the item is in a terminal state (failed/cancelled) we
    cannot resurrect it via this path — admin must propose a new batch."""
    item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
    if not item:
        raise ValueError(f"item {item_id} not found")
    if item["status"] != pv2.ITEM_QUEUED:
        raise ValueError(
            f"force_retry only valid on queued items (current status={item['status']})"
        )
    await db.payout_items_v2.update_one(
        {"item_id": item_id},
        {"$set": {
            "next_attempt_at": _now_iso(),
            "claimed_by": None,
            "lease_until": None,
        }},
    )
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="admin_force_retry",
        actor=actor, reason="manual_retry",
    )
    return await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})


async def admin_force_dead_letter(
    db, *, item_id: str, actor: str, reason: str = "admin_dead_letter"
) -> Dict[str, Any]:
    """Force an item to terminal failed/exhausted — used when admin
    decides further retries are pointless (e.g. known bad rail account
    that the rail can't validate)."""
    item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
    if not item:
        raise ValueError(f"item {item_id} not found")
    if item["status"] != pv2.ITEM_QUEUED:
        raise ValueError(
            f"dead_letter only valid on queued items (current status={item['status']})"
        )
    await _dead_letter(
        db, item_id=item_id, attempt=int(item.get("attempt_count", 0)) + 1,
        error=reason, error_code="admin_terminated",
    )
    await pv2.emit_event(
        db, scope="item", subject_id=item_id, kind="admin_force_dead_letter",
        actor=actor, reason=reason,
    )
    return await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})


# ──────────────────────────────────────────────────────────────────────
# One-shot drainer for tests / curl smoke
# ──────────────────────────────────────────────────────────────────────
async def drain_once_for_test(db) -> Dict[str, Any]:
    """One drain cycle + one mock-advance cycle + one reap. Used by tests
    so we don't have to wait for the background loops."""
    drained = await _drain_once(db)
    advanced = await _advance_mock_items_once(db)
    reaped = await _reap_stale_leases(db)
    return {"drained": drained, "advanced": advanced, "reaped": reaped}
