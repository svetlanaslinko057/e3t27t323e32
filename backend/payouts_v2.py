"""
PAY-V2-P1 — Payouts v2 substrate.

This module is the canonical authority for outbound-payment state, per
`/app/docs/active-audits/PAY_V2_P0_CHARTER.md`.

Collections introduced (Mongo):
  - `payout_batches_v2`        — proposed/released/cancelled (intent layer)
  - `payout_items_v2`          — per-rail / per-developer payouts (reality layer)
  - `payout_v2_events`         — append-only event log (Pr-1, Pr-4 authority)
  - `payout_v2_idempotency`    — `(key, scope)` unique index (Pr-5)
  - `dev_payment_profiles`     — per-developer rail preferences + KYC (Pr-9)

Lifecycle
---------
  Batch:  proposed → released → closed
                  ↘ cancelled
  Item:   queued → initiated → in_flight → confirmed → settled → reconciled
                                                              ↘ failed | returned | disputed | cancelled

Principles enforced:
  Pr-1 — every state mutation appends to `payout_v2_events`
  Pr-2 — released batches immutable (corrections via compensating events)
  Pr-4 — projections are pure functions of events (re-derivable)
  Pr-5 — idempotency key required on `propose_batch` and `submit_item`
  Pr-6 — item failure does NOT cascade to batch state
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── States ────────────────────────────────────────────────────────────
BATCH_PROPOSED = "proposed"
BATCH_RELEASED = "released"
BATCH_CANCELLED = "cancelled"
BATCH_CLOSED = "closed"
BATCH_STATES = {BATCH_PROPOSED, BATCH_RELEASED, BATCH_CANCELLED, BATCH_CLOSED}

ITEM_QUEUED = "queued"
ITEM_INITIATED = "initiated"
ITEM_IN_FLIGHT = "in_flight"
ITEM_CONFIRMED = "confirmed"
ITEM_SETTLED = "settled"
ITEM_RECONCILED = "reconciled"
ITEM_FAILED = "failed"
ITEM_RETURNED = "returned"
ITEM_DISPUTED = "disputed"
ITEM_CANCELLED = "cancelled"
ITEM_TERMINAL = {ITEM_SETTLED, ITEM_RECONCILED, ITEM_FAILED, ITEM_RETURNED, ITEM_DISPUTED, ITEM_CANCELLED}
ITEM_STATES = ITEM_TERMINAL | {ITEM_QUEUED, ITEM_INITIATED, ITEM_IN_FLIGHT, ITEM_CONFIRMED}

# ── Allowed item transitions (per Pr-6, failure stays inside item) ────
_ITEM_TRANSITIONS = {
    ITEM_QUEUED:       {ITEM_INITIATED, ITEM_CANCELLED, ITEM_FAILED},
    ITEM_INITIATED:    {ITEM_IN_FLIGHT, ITEM_FAILED, ITEM_CANCELLED},
    ITEM_IN_FLIGHT:    {ITEM_CONFIRMED, ITEM_FAILED, ITEM_RETURNED},
    ITEM_CONFIRMED:    {ITEM_SETTLED, ITEM_RETURNED, ITEM_DISPUTED},
    ITEM_SETTLED:      {ITEM_RECONCILED, ITEM_RETURNED, ITEM_DISPUTED},
    ITEM_RECONCILED:   {ITEM_DISPUTED},
    ITEM_FAILED:       set(),  # terminal; new attempt creates a NEW item
    ITEM_RETURNED:     set(),
    ITEM_DISPUTED:     {ITEM_RECONCILED},  # post-dispute resolution
    ITEM_CANCELLED:    set(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ──────────────────────────────────────────────────────────────────────
# Indexes — called once at boot from server.py
# ──────────────────────────────────────────────────────────────────────
async def ensure_indexes(db) -> None:
    await db.payout_batches_v2.create_index("batch_id", unique=True)
    await db.payout_batches_v2.create_index("status")
    await db.payout_items_v2.create_index("item_id", unique=True)
    await db.payout_items_v2.create_index([("batch_id", 1)])
    await db.payout_items_v2.create_index([("developer_id", 1), ("status", 1)])
    # PAY-V2-P3 — worker claim indexes. Most-selective fields first.
    await db.payout_items_v2.create_index([("status", 1), ("next_attempt_at", 1)])
    await db.payout_items_v2.create_index([("claimed_by", 1), ("lease_until", 1)])
    await db.payout_v2_events.create_index(
        [("scope", 1), ("subject_id", 1), ("created_at", 1)]
    )
    await db.payout_v2_idempotency.create_index(
        [("scope", 1), ("key", 1)], unique=True
    )
    await db.dev_payment_profiles.create_index("developer_id", unique=True)
    logger.info("PAYOUTS_V2: indexes ensured")


# ──────────────────────────────────────────────────────────────────────
# Idempotency
# ──────────────────────────────────────────────────────────────────────
class IdempotencyHit(Exception):
    """Raised when an idempotency key was already used. `prior` carries the
    original result so callers can return it instead of erroring."""

    def __init__(self, prior: Dict[str, Any]):
        self.prior = prior
        super().__init__("idempotency_hit")


async def _claim_key(db, scope: str, key: str, result: Dict[str, Any]) -> None:
    """Best-effort idempotency claim. Raises IdempotencyHit with the prior
    result on duplicate. `scope` namespaces keys ("batch.propose" /
    "item.submit" / "webhook.{provider}.{ref}" etc.)."""
    try:
        await db.payout_v2_idempotency.insert_one(
            {"scope": scope, "key": key, "result": result, "claimed_at": _now_iso()}
        )
    except Exception:
        prior = await db.payout_v2_idempotency.find_one(
            {"scope": scope, "key": key}, {"_id": 0}
        )
        if prior:
            raise IdempotencyHit(prior.get("result") or {})
        # Race or other error — re-raise as a soft signal
        raise IdempotencyHit({"scope": scope, "key": key})


# ──────────────────────────────────────────────────────────────────────
# Events (append-only, Pr-1)
# ──────────────────────────────────────────────────────────────────────
async def emit_event(
    db,
    *,
    scope: str,
    subject_id: str,
    kind: str,
    actor: str,
    payload: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    doc = {
        "event_id": _new_id("evt"),
        "scope": scope,  # "batch" | "item" | "profile" | "reconciliation"
        "subject_id": subject_id,  # batch_id | item_id | developer_id | settlement_id
        "kind": kind,  # state name OR action name (e.g. "released", "admin_override")
        "actor": actor,  # "scheduler" | "admin:<user_id>" | "provider:<rail>" | "system"
        "payload": payload or {},
        "reason": reason,
        "created_at": _now_iso(),
    }
    await db.payout_v2_events.insert_one(doc)
    return doc


# ──────────────────────────────────────────────────────────────────────
# Batch — intent layer (Pr-2 immutable post-release)
# ──────────────────────────────────────────────────────────────────────
async def propose_batch(
    db,
    *,
    actor: str,
    idempotency_key: str,
    developer_ids: Optional[List[str]] = None,
    label: str = "scheduled",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a proposed batch from approved earnings (per developer).

    - `developer_ids=None` → all developers with approved earnings.
    - Status: PROPOSED. Admin still has to release().
    - Items are NOT yet created (created on release()).
    """
    # Idempotency claim — return prior if hit
    try:
        await _claim_key(
            db, scope="batch.propose", key=idempotency_key, result={"pending": True}
        )
    except IdempotencyHit as h:
        return h.prior

    # Read approved earnings (not already in v2 batch)
    flt: Dict[str, Any] = {
        "earning_status": "approved",
        "payout_batch_id": None,
        "frozen": False,
    }
    if developer_ids:
        flt["user_id"] = {"$in": developer_ids}

    approved = await db.task_earnings.find(flt, {"_id": 0}).to_list(5000)

    by_dev: Dict[str, List[Dict[str, Any]]] = {}
    for e in approved:
        by_dev.setdefault(e["user_id"], []).append(e)

    if not by_dev:
        batch = {
            "batch_id": _new_id("batchv2"),
            "label": label,
            "status": BATCH_PROPOSED,
            "currency": "USD",
            "totals": {"developers": 0, "earnings": 0, "amount": 0.0},
            "proposed_at": _now_iso(),
            "proposed_by": actor,
            "released_at": None,
            "released_by": None,
            "metadata": metadata or {},
            "empty": True,
        }
        await db.payout_batches_v2.insert_one(batch)
        batch.pop("_id", None)
        await emit_event(
            db, scope="batch", subject_id=batch["batch_id"], kind="proposed",
            actor=actor, payload={"empty": True, "label": label},
        )
        await db.payout_v2_idempotency.update_one(
            {"scope": "batch.propose", "key": idempotency_key},
            {"$set": {"result": batch}},
        )
        return batch

    total_amount = sum(e["final_earning"] for devs in by_dev.values() for e in devs)
    total_earnings = sum(len(v) for v in by_dev.values())

    batch_id = _new_id("batchv2")
    items_plan = []
    for dev_id, earnings in by_dev.items():
        items_plan.append({
            "developer_id": dev_id,
            "earning_ids": [e["earning_id"] for e in earnings],
            "amount": round(sum(e["final_earning"] for e in earnings), 2),
            "currency": "USD",
        })

    batch = {
        "batch_id": batch_id,
        "label": label,
        "status": BATCH_PROPOSED,
        "currency": "USD",
        "totals": {
            "developers": len(by_dev),
            "earnings": total_earnings,
            "amount": round(total_amount, 2),
        },
        "items_plan": items_plan,  # frozen plan; items materialise on release()
        "proposed_at": _now_iso(),
        "proposed_by": actor,
        "released_at": None,
        "released_by": None,
        "metadata": metadata or {},
        "empty": False,
    }
    await db.payout_batches_v2.insert_one(batch)
    batch.pop("_id", None)
    await emit_event(
        db, scope="batch", subject_id=batch_id, kind="proposed", actor=actor,
        payload={"totals": batch["totals"], "label": label},
    )
    await db.payout_v2_idempotency.update_one(
        {"scope": "batch.propose", "key": idempotency_key},
        {"$set": {"result": batch}},
    )
    return batch


async def release_batch(
    db,
    *,
    batch_id: str,
    actor: str,
    override: bool = False,
) -> Dict[str, Any]:
    """Transition PROPOSED → RELEASED. Materialises payout_items.

    `override=True` records an `admin_override` event (Pr-8).
    """
    batch = await db.payout_batches_v2.find_one({"batch_id": batch_id}, {"_id": 0})
    if not batch:
        raise ValueError(f"batch {batch_id} not found")
    if batch["status"] != BATCH_PROPOSED:
        raise ValueError(f"batch {batch_id} not proposed (status={batch['status']})")

    items_plan = batch.get("items_plan") or []

    # Fetch payment profiles for rail routing (default: mock if missing)
    profiles = {}
    if items_plan:
        dev_ids = [it["developer_id"] for it in items_plan]
        async for p in db.dev_payment_profiles.find(
            {"developer_id": {"$in": dev_ids}}, {"_id": 0}
        ):
            profiles[p["developer_id"]] = p

    items_created: List[Dict[str, Any]] = []
    now = _now_iso()
    for plan in items_plan:
        prof = profiles.get(plan["developer_id"]) or {}
        rail = prof.get("preferred_rail") or "mock"
        item = {
            "item_id": _new_id("item"),
            "batch_id": batch_id,
            "developer_id": plan["developer_id"],
            "amount": plan["amount"],
            "currency": plan["currency"],
            "rail": rail,
            "rail_account": prof.get("rail_config") or {},
            "earning_ids": plan["earning_ids"],
            "status": ITEM_QUEUED,
            "status_history": [
                {"status": ITEM_QUEUED, "at": now, "actor": actor, "reason": "batch_released"}
            ],
            "provider_ref": None,
            "fees_provider": 0.0,
            "fees_fx": 0.0,
            "idempotency_key": f"item:{_new_id('idem')}",
            "kyc_status": prof.get("kyc_status") or "soft",
            "created_at": now,
            "initiated_at": None,
            "settled_at": None,
            "reconciled_at": None,
            "last_error": None,
            "retry_count": 0,
        }
        items_created.append(item)
        await emit_event(
            db, scope="item", subject_id=item["item_id"], kind=ITEM_QUEUED,
            actor=actor, payload={"batch_id": batch_id, "rail": rail},
        )

    if items_created:
        await db.payout_items_v2.insert_many(items_created)

    await db.payout_batches_v2.update_one(
        {"batch_id": batch_id},
        {"$set": {
            "status": BATCH_RELEASED,
            "released_at": now,
            "released_by": actor,
            "item_count": len(items_created),
        }},
    )

    await emit_event(
        db, scope="batch", subject_id=batch_id,
        kind="admin_override" if override else "released",
        actor=actor, payload={"items": len(items_created)},
    )
    logger.info("PAYOUTS_V2: batch %s released (items=%d, override=%s)", batch_id, len(items_created), override)

    return await db.payout_batches_v2.find_one({"batch_id": batch_id}, {"_id": 0})


async def cancel_batch(
    db, *, batch_id: str, actor: str, reason: str = ""
) -> Dict[str, Any]:
    batch = await db.payout_batches_v2.find_one({"batch_id": batch_id}, {"_id": 0})
    if not batch:
        raise ValueError(f"batch {batch_id} not found")
    if batch["status"] != BATCH_PROPOSED:
        raise ValueError(
            f"batch {batch_id} can only be cancelled while proposed (status={batch['status']})"
        )
    await db.payout_batches_v2.update_one(
        {"batch_id": batch_id},
        {"$set": {"status": BATCH_CANCELLED, "cancelled_at": _now_iso(), "cancel_reason": reason}},
    )
    await emit_event(
        db, scope="batch", subject_id=batch_id, kind=BATCH_CANCELLED,
        actor=actor, reason=reason,
    )
    return await db.payout_batches_v2.find_one({"batch_id": batch_id}, {"_id": 0})


# ──────────────────────────────────────────────────────────────────────
# Items — reality layer (Pr-6 failure-isolated)
# ──────────────────────────────────────────────────────────────────────
async def transition_item(
    db, *, item_id: str, to_status: str, actor: str,
    payload: Optional[Dict[str, Any]] = None, reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Move an item to a new status, validating the transition. Appends to
    `status_history` and emits an event. Idempotent: re-applying the same
    transition is a noop."""
    if to_status not in ITEM_STATES:
        raise ValueError(f"unknown item status: {to_status}")
    item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
    if not item:
        raise ValueError(f"item {item_id} not found")
    cur = item["status"]
    if cur == to_status:
        return item
    allowed = _ITEM_TRANSITIONS.get(cur) or set()
    if to_status not in allowed:
        raise ValueError(
            f"item {item_id}: illegal transition {cur} → {to_status} (allowed: {sorted(allowed)})"
        )

    now = _now_iso()
    update: Dict[str, Any] = {"status": to_status}
    history_entry = {"status": to_status, "at": now, "actor": actor, "reason": reason}
    if payload:
        history_entry["payload"] = payload
    if to_status == ITEM_INITIATED:
        update["initiated_at"] = now
        if payload and "provider_ref" in payload:
            update["provider_ref"] = payload["provider_ref"]
    if to_status == ITEM_SETTLED:
        update["settled_at"] = now
        if payload:
            update["fees_provider"] = float(payload.get("fees_provider") or 0)
            update["fees_fx"] = float(payload.get("fees_fx") or 0)
    if to_status == ITEM_RECONCILED:
        update["reconciled_at"] = now
    if to_status == ITEM_FAILED:
        update["last_error"] = (payload or {}).get("error") or reason
        update["retry_count"] = int(item.get("retry_count", 0)) + 1
    await db.payout_items_v2.update_one(
        {"item_id": item_id},
        {"$set": update, "$push": {"status_history": history_entry}},
    )

    await emit_event(
        db, scope="item", subject_id=item_id, kind=to_status,
        actor=actor, payload=payload, reason=reason,
    )
    logger.info("PAYOUTS_V2: item %s %s → %s", item_id, cur, to_status)
    return await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})


# ──────────────────────────────────────────────────────────────────────
# Authoritative projection (Pr-4 — pure function of items + events)
# ──────────────────────────────────────────────────────────────────────
async def build_queue_view(
    db, *, status: Optional[str] = None, rail: Optional[str] = None
) -> Dict[str, Any]:
    """Operational queue (admin) — what needs action now (Pr-7)."""
    flt: Dict[str, Any] = {}
    if status:
        flt["status"] = status
    if rail:
        flt["rail"] = rail
    items = await db.payout_items_v2.find(flt, {"_id": 0}).sort("created_at", 1).to_list(1000)

    counts: Dict[str, int] = {s: 0 for s in ITEM_STATES}
    amount_by_status: Dict[str, float] = {s: 0.0 for s in ITEM_STATES}
    for it in items:
        s = it["status"]
        counts[s] = counts.get(s, 0) + 1
        amount_by_status[s] = round(amount_by_status.get(s, 0.0) + float(it["amount"]), 2)

    # Batches summary
    batches = await db.payout_batches_v2.find({}, {"_id": 0}).sort("proposed_at", -1).to_list(200)
    batch_counts: Dict[str, int] = {s: 0 for s in BATCH_STATES}
    for b in batches:
        batch_counts[b["status"]] = batch_counts.get(b["status"], 0) + 1

    return {
        "items": {
            "total": len(items),
            "counts_by_status": counts,
            "amount_by_status": amount_by_status,
            "list": items[:200],  # cap for UI
        },
        "batches": {
            "total": len(batches),
            "counts_by_status": batch_counts,
            "recent": batches[:50],
        },
        "as_of": _now_iso(),
    }


async def get_batch_with_items(db, *, batch_id: str) -> Dict[str, Any]:
    batch = await db.payout_batches_v2.find_one({"batch_id": batch_id}, {"_id": 0})
    if not batch:
        raise ValueError(f"batch {batch_id} not found")
    items = await db.payout_items_v2.find({"batch_id": batch_id}, {"_id": 0}).to_list(1000)
    events = await db.payout_v2_events.find(
        {"scope": "batch", "subject_id": batch_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return {"batch": batch, "items": items, "events": events}


async def get_item_with_history(db, *, item_id: str) -> Dict[str, Any]:
    item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
    if not item:
        raise ValueError(f"item {item_id} not found")
    events = await db.payout_v2_events.find(
        {"scope": "item", "subject_id": item_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    return {"item": item, "events": events}


# ──────────────────────────────────────────────────────────────────────
# Payment profile (Pr-9 soft KYC, additive)
# ──────────────────────────────────────────────────────────────────────
async def upsert_payment_profile(
    db, *, developer_id: str, actor: str, patch: Dict[str, Any]
) -> Dict[str, Any]:
    allowed = {
        "country", "preferred_rail", "rail_config",
        "kyc_status", "kyc_notes",
    }
    update = {k: v for k, v in patch.items() if k in allowed}
    update["updated_at"] = _now_iso()
    update["updated_by"] = actor

    existing = await db.dev_payment_profiles.find_one({"developer_id": developer_id}, {"_id": 0})
    if not existing:
        doc = {
            "developer_id": developer_id,
            "country": update.get("country"),
            "preferred_rail": update.get("preferred_rail") or "mock",
            "rail_config": update.get("rail_config") or {},
            "kyc_status": update.get("kyc_status") or "soft",
            "kyc_notes": update.get("kyc_notes"),
            "created_at": _now_iso(),
            "updated_at": update["updated_at"],
            "updated_by": actor,
        }
        await db.dev_payment_profiles.insert_one(doc)
        doc.pop("_id", None)
        await emit_event(db, scope="profile", subject_id=developer_id, kind="created", actor=actor)
        return doc

    await db.dev_payment_profiles.update_one({"developer_id": developer_id}, {"$set": update})
    await emit_event(
        db, scope="profile", subject_id=developer_id, kind="updated", actor=actor,
        payload={"keys": list(update.keys())},
    )
    return await db.dev_payment_profiles.find_one({"developer_id": developer_id}, {"_id": 0})


async def get_payment_profile(db, *, developer_id: str) -> Dict[str, Any]:
    p = await db.dev_payment_profiles.find_one({"developer_id": developer_id}, {"_id": 0})
    if p:
        return p
    return {
        "developer_id": developer_id,
        "country": None,
        "preferred_rail": "mock",
        "rail_config": {},
        "kyc_status": "soft",
        "kyc_notes": None,
        "ephemeral": True,
    }
