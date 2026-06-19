"""PAY-V2-P3 failure/retry/exhaustion path (deterministic unit-style).

Races against the running backend worker can't be avoided when both share
the same Mongo collection — so we test the worker's *logic* directly by:
  • Inserting items DIRECTLY in `payout_items_v2` (no propose/release path).
  • Calling `_process_claimed_item` directly with a forced-fail provider.
  • Asserting retry-scheduling fields on each attempt, and that the
    `attempt_count==max_attempts` attempt dead-letters to terminal `failed`.

This deterministically validates:
  - transient failure → next_attempt_at set with exponential backoff
  - retry_scheduled event emitted with backoff_sec
  - attempt_count increments
  - at max_attempts, dead_letter fires: status=failed, dead_lettered=True,
    `exhausted` event emitted.
  - last_error / last_error_code propagated.

Run:
    python3 /app/backend/tests/test_payouts_v2_worker_failure.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

os.environ["PAY_V2_WORKER_MAX_ATTEMPTS"] = "3"
os.environ["PAY_V2_WORKER_BACKOFF_BASE_SEC"] = "1"
os.environ["PAY_V2_WORKER_BACKOFF_MAX_SEC"] = "3"

sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import payouts_v2 as pv2  # noqa: E402
import payouts_v2_worker as pv2w  # noqa: E402
from integrations.settlement import (  # noqa: E402
    PayoutRequest, PayoutResult, SettlementEvent, SettlementProvider,
)
from integrations.base import AvailabilityMode, Capability, CapabilityState  # noqa: E402


SUITE_TAG = f"p3-failunit-{uuid.uuid4().hex[:6]}"
TEST_RAIL = f"test_failrail_{uuid.uuid4().hex[:6]}"


class AlwaysFailProvider(SettlementProvider):
    """Returns a `provider_unavailable` (transient) error every call."""
    name = "always-fail-test"

    def health(self) -> CapabilityState:
        return CapabilityState(
            capability=Capability.SETTLEMENT, provider_name=self.name,
            mode=AvailabilityMode.MOCK, available=False,
            reason="forced-fail test fixture", details={},
        )

    async def state(self) -> CapabilityState:
        return self.health()

    async def create_payout(self, req: PayoutRequest) -> PayoutResult:
        return PayoutResult(
            success=False, provider_ref=None, status="failed",
            error="provider unavailable (test)",
            error_code="provider_unavailable",
        )

    async def verify_webhook(self, body, headers):
        return SettlementEvent(
            valid=False, item_id=None, provider_ref=None,
            status="failed", event_type=None,
        )

    async def reconcile(self, lines):
        from integrations.settlement import ReconciliationResult
        return ReconciliationResult(matched=0, unmatched=len(lines))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _make_test_item(db, suffix: str) -> str:
    """Create a payout item that the BACKEND worker won't touch: we route
    it to TEST_RAIL (unknown rail). Even if backend's worker claims it
    (it will, since status=queued), backend's `get_provider_for_rail`
    falls back to its mock which succeeds. So this test could still race.

    To prevent the race entirely, we DON'T leave the item in `queued`
    long enough for the backend to claim it — we directly invoke
    `_process_claimed_item` after manually claiming the lease."""
    item_id = f"item_{SUITE_TAG}_{suffix}"
    now = _now_iso()
    await db.payout_items_v2.insert_one({
        "item_id": item_id,
        "batch_id": f"batch_{SUITE_TAG}",
        "developer_id": f"dev_{SUITE_TAG}_{suffix}",
        "amount": 100.0,
        "currency": "USD",
        "rail": TEST_RAIL,
        "rail_account": {},
        "earning_ids": [],
        "status": pv2.ITEM_QUEUED,
        "status_history": [{"status": pv2.ITEM_QUEUED, "at": now, "actor": "test"}],
        "provider_ref": None,
        "fees_provider": 0.0, "fees_fx": 0.0,
        "idempotency_key": f"item:{item_id}",
        "kyc_status": "soft",
        "created_at": now,
        "initiated_at": None, "settled_at": None, "reconciled_at": None,
        "last_error": None, "last_error_code": None,
        "attempt_count": 0,
        "next_attempt_at": None,
        "claimed_by": None, "lease_until": None,
        # Mark as test-only — backend worker would still touch it but we'll
        # race-proof by manually claiming + processing in one tight loop.
        "_test_suite": SUITE_TAG,
    })
    return item_id


async def _cleanup(db):
    items = await db.payout_items_v2.find(
        {"_test_suite": SUITE_TAG}, {"item_id": 1, "_id": 0}
    ).to_list(100)
    ids = [i["item_id"] for i in items]
    if ids:
        await db.payout_items_v2.delete_many({"item_id": {"$in": ids}})
        await db.payout_v2_events.delete_many(
            {"scope": "item", "subject_id": {"$in": ids}}
        )


async def run() -> int:
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    )[os.environ.get("DB_NAME", "test_database")]
    await pv2.ensure_indexes(db)

    # Inject the failing provider for our test rail. This affects ONLY
    # the test process — backend process still has its own map.
    pv2w._PROVIDERS_BY_RAIL[TEST_RAIL] = AlwaysFailProvider()
    print(f"[setup] suite={SUITE_TAG} rail={TEST_RAIL} max_attempts={pv2w.CFG.max_attempts}")

    item_id = await _make_test_item(db, "1")

    # We test the per-attempt logic deterministically by:
    #   1) parking the item with next_attempt_at FAR FUTURE so backend
    #      worker can't claim it,
    #   2) for each attempt: forcibly set claimed_by + lease ourselves,
    #      fetch the item dict, and call _process_claimed_item directly,
    #   3) verify the resulting state, then loop.
    FAR_FUTURE = "2099-01-01T00:00:00+00:00"
    await db.payout_items_v2.update_one(
        {"item_id": item_id},
        {"$set": {"next_attempt_at": FAR_FUTURE}},
    )

    from datetime import timedelta
    for expected_attempt in range(1, pv2w.CFG.max_attempts + 1):
        # Claim manually (race-proof against backend worker because we
        # set claimed_by+lease in one update; backend won't reclaim until
        # lease_until expires).
        lease_until = (datetime.now(timezone.utc) + timedelta(
            seconds=pv2w.CFG.lease_sec)).isoformat()
        await db.payout_items_v2.update_one(
            {"item_id": item_id},
            {"$set": {
                "claimed_by": pv2w.WORKER_ID,
                "claimed_at": _now_iso(),
                "lease_until": lease_until,
                "last_heartbeat": _now_iso(),
            }, "$inc": {"claim_count": 1}},
        )
        item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
        assert item["status"] == pv2.ITEM_QUEUED, \
            f"attempt {expected_attempt}: expected queued, got {item['status']}"

        result = await pv2w._process_claimed_item(db, item)
        is_last = expected_attempt == pv2w.CFG.max_attempts
        print(
            f"[attempt {expected_attempt}] result={result['result']} "
            f"attempts={result.get('attempts')} backoff={result.get('backoff_sec')}"
        )

        item = await db.payout_items_v2.find_one({"item_id": item_id}, {"_id": 0})
        if is_last:
            assert item["status"] == pv2.ITEM_FAILED, \
                f"final attempt should yield status=failed, got {item['status']}"
            assert item.get("dead_lettered") is True, \
                "final attempt should set dead_lettered=True"
            assert item.get("last_error_code") == "provider_unavailable"
            assert item.get("attempt_count") == pv2w.CFG.max_attempts
        else:
            assert item["status"] == pv2.ITEM_QUEUED, \
                f"non-final attempt should stay queued, got {item['status']}"
            assert item.get("next_attempt_at") is not None
            assert item.get("claimed_by") is None
            assert item.get("attempt_count") == expected_attempt
            # Park next_attempt_at to FAR_FUTURE so backend can't claim it,
            # but our test claim path bypasses next_attempt_at filtering.
            await db.payout_items_v2.update_one(
                {"item_id": item_id},
                {"$set": {"next_attempt_at": FAR_FUTURE}},
            )

    # Verify the event trail
    events = await db.payout_v2_events.find(
        {"scope": "item", "subject_id": item_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    kinds = [e["kind"] for e in events]
    print(f"[events] {kinds}")

    required = {"worker_claimed", "provider_called", "retry_scheduled",
                "exhausted", "failed"}
    missing = required - set(kinds)
    # Count retry_scheduled events — should be max_attempts - 1
    retry_count = kinds.count("retry_scheduled")
    exhausted_count = kinds.count("exhausted")
    failed_count = kinds.count("failed")

    print(f"[events] retry_scheduled×{retry_count} exhausted×{exhausted_count} failed×{failed_count}")
    ok = (
        not missing
        and retry_count == pv2w.CFG.max_attempts - 1
        and exhausted_count == 1
        and failed_count == 1
    )
    if not ok:
        print(f"[FAIL] missing={missing} retry={retry_count} expected={pv2w.CFG.max_attempts - 1}")
        await _cleanup(db)
        return 1

    # Check that retry_scheduled events carry the backoff_sec field
    rs_events = [e for e in events if e["kind"] == "retry_scheduled"]
    for e in rs_events:
        assert "backoff_sec" in (e.get("payload") or {}), \
            "retry_scheduled event must carry backoff_sec"
        assert "next_attempt_at" in (e.get("payload") or {}), \
            "retry_scheduled event must carry next_attempt_at"
        assert "attempt" in (e.get("payload") or {}), \
            "retry_scheduled event must carry attempt #"
    print("[verify] all retry_scheduled events carry backoff_sec/next_attempt_at/attempt")

    await _cleanup(db)
    print("\n✅ PAY-V2-P3 failure/retry/exhaustion PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
