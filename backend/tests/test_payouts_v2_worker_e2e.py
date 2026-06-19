"""PAY-V2-P3 end-to-end smoke: seed approved earnings → propose → release
→ drain_once_for_test (a few cycles) → assert all items reach `settled`.

Run:
    python3 /app/backend/tests/test_payouts_v2_worker_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MOCK_SETTLEMENT_FAIL", "0")
os.environ.setdefault("PAY_V2_MOCK_ADVANCE_DELAY_SEC", "0")  # immediate advance for test
os.environ.setdefault("PAY_V2_WORKER_MAX_ATTEMPTS", "5")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import payouts_v2 as pv2  # noqa: E402
import payouts_v2_worker as pv2w  # noqa: E402


SUITE_TAG = f"p3-e2e-{uuid.uuid4().hex[:6]}"
NUM_DEVS = 6
AMOUNT_EACH = 250.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_approved_earnings(db) -> list[str]:
    """Insert NUM_DEVS approved earnings tagged with SUITE_TAG."""
    docs = []
    for i in range(NUM_DEVS):
        docs.append({
            "earning_id": f"earn_{SUITE_TAG}_{i}",
            "user_id": f"dev_{SUITE_TAG}_{i}",
            "task_id": f"task_{SUITE_TAG}_{i}",
            "final_earning": AMOUNT_EACH,
            "currency": "USD",
            "earning_status": "approved",
            "payout_batch_id": None,
            "frozen": False,
            "created_at": _now_iso(),
            "_suite": SUITE_TAG,
        })
    await db.task_earnings.insert_many(docs)
    return [d["earning_id"] for d in docs]


async def _cleanup(db) -> None:
    """Remove suite docs to keep the database clean between runs."""
    await db.task_earnings.delete_many({"_suite": SUITE_TAG})
    items = await db.payout_items_v2.find(
        {"developer_id": {"$regex": f"^dev_{SUITE_TAG}_"}}, {"item_id": 1, "_id": 0}
    ).to_list(1000)
    item_ids = [i["item_id"] for i in items]
    if item_ids:
        await db.payout_items_v2.delete_many({"item_id": {"$in": item_ids}})
        await db.payout_v2_events.delete_many(
            {"scope": "item", "subject_id": {"$in": item_ids}}
        )
    # batches created during the test (label="manual" with suite tag)
    batches = await db.payout_batches_v2.find(
        {"metadata._suite": SUITE_TAG}, {"batch_id": 1, "_id": 0}
    ).to_list(1000)
    batch_ids = [b["batch_id"] for b in batches]
    if batch_ids:
        await db.payout_batches_v2.delete_many({"batch_id": {"$in": batch_ids}})
        await db.payout_v2_events.delete_many(
            {"scope": "batch", "subject_id": {"$in": batch_ids}}
        )
    await db.payout_v2_idempotency.delete_many(
        {"key": {"$regex": f"^{SUITE_TAG}"}}
    )


async def run() -> int:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    await pv2.ensure_indexes(db)
    print(f"[setup] suite={SUITE_TAG} devs={NUM_DEVS} amount_each=${AMOUNT_EACH}")

    # 1. Seed approved earnings
    earning_ids = await _seed_approved_earnings(db)
    print(f"[seed] inserted {len(earning_ids)} approved earnings")

    # 2. Propose batch
    batch = await pv2.propose_batch(
        db,
        actor="test:p3",
        idempotency_key=f"{SUITE_TAG}:propose",
        developer_ids=[f"dev_{SUITE_TAG}_{i}" for i in range(NUM_DEVS)],
        label="manual",
        metadata={"_suite": SUITE_TAG},
    )
    assert not batch.get("empty"), "batch should not be empty"
    print(
        f"[propose] batch_id={batch['batch_id']} devs={batch['totals']['developers']} "
        f"amount=${batch['totals']['amount']}"
    )

    # Tag earnings so they don't get re-proposed by other tests
    await db.task_earnings.update_many(
        {"earning_id": {"$in": earning_ids}},
        {"$set": {"payout_batch_id": batch["batch_id"]}},
    )

    # 3. Release batch — creates queued items
    batch = await pv2.release_batch(db, batch_id=batch["batch_id"], actor="test:p3")
    item_count = batch.get("item_count", 0)
    assert item_count == NUM_DEVS, f"expected {NUM_DEVS} items, got {item_count}"
    print(f"[release] batch released, items_created={item_count}")

    # 4. Drive worker manually (multiple cycles — first cycle initiates,
    #    subsequent cycles advance the mock chain to settled).
    deadline = asyncio.get_event_loop().time() + 30  # 30s hard cap
    settled = 0
    cycles = 0
    while asyncio.get_event_loop().time() < deadline:
        cycles += 1
        result = await pv2w.drain_once_for_test(db)
        drained = result["drained"]["processed"]
        advanced = result["advanced"]["advanced"]
        print(
            f"[cycle {cycles}] drained={drained} advanced={advanced} "
            f"reaped={result['reaped'].get('reclaimed', 0)}"
        )
        # Count settled items in this batch
        settled = await db.payout_items_v2.count_documents({
            "batch_id": batch["batch_id"],
            "status": pv2.ITEM_SETTLED,
        })
        if settled == NUM_DEVS:
            break
        await asyncio.sleep(0.2)  # let mock advancer's delay elapse

    # 5. Assert all items reached settled
    by_status: dict[str, int] = {}
    async for it in db.payout_items_v2.find(
        {"batch_id": batch["batch_id"]}, {"status": 1, "_id": 0}
    ):
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1

    print(f"[final] cycles={cycles} settled={settled}/{NUM_DEVS} status_counts={by_status}")

    ok = settled == NUM_DEVS and by_status.get(pv2.ITEM_SETTLED, 0) == NUM_DEVS
    if not ok:
        print("[FAIL] not all items reached settled")
        await _cleanup(db)
        return 1

    # 6. Worker status snapshot — operational visibility
    snapshot = await pv2w.worker_status_snapshot(db)
    print(
        f"[snapshot] worker_id={snapshot['worker_id']} ready={snapshot['queue_health']['ready']} "
        f"in_flight_owned={snapshot['queue_health']['in_flight_owned']} "
        f"stale={snapshot['queue_health']['stale_leases']} "
        f"stuck={snapshot['queue_health']['stuck']} "
        f"exhausted={snapshot['queue_health']['exhausted']}"
    )

    # 7. Verify events emitted (worker_claimed + provider_called + initiated
    #    + in_flight + confirmed + settled) per item
    sample_item = await db.payout_items_v2.find_one({"batch_id": batch["batch_id"]}, {"_id": 0})
    events = await db.payout_v2_events.find(
        {"scope": "item", "subject_id": sample_item["item_id"]}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    event_kinds = [e["kind"] for e in events]
    print(f"[events] sample item events: {event_kinds}")
    required_kinds = {"queued", "worker_claimed", "provider_called", "initiated",
                      "in_flight", "confirmed", "settled"}
    missing = required_kinds - set(event_kinds)
    if missing:
        print(f"[FAIL] missing event kinds for sample item: {missing}")
        await _cleanup(db)
        return 1

    # 8. Test admin_force_retry on a separate retry-eligible item
    #    (simulate provider failure via MOCK_SETTLEMENT_FAIL=1 for a moment)
    # We exercise admin_force_retry path with a synthetic queued item that
    # has next_attempt_at far in the future.
    future_iso = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat()
    test_item_id = f"item_force_retry_{SUITE_TAG}"
    await db.payout_items_v2.insert_one({
        "item_id": test_item_id,
        "batch_id": batch["batch_id"],
        "developer_id": f"dev_{SUITE_TAG}_force",
        "amount": 100.0,
        "currency": "USD",
        "rail": "mock",
        "rail_account": {},
        "earning_ids": [],
        "status": pv2.ITEM_QUEUED,
        "status_history": [{"status": pv2.ITEM_QUEUED, "at": future_iso, "actor": "test"}],
        "provider_ref": None,
        "fees_provider": 0.0,
        "fees_fx": 0.0,
        "idempotency_key": f"item:{test_item_id}",
        "kyc_status": "soft",
        "created_at": future_iso,
        "initiated_at": None,
        "settled_at": None,
        "reconciled_at": None,
        "last_error": None,
        "attempt_count": 0,
        "next_attempt_at": "9999-12-31T23:59:59+00:00",  # never eligible
        "claimed_by": None, "lease_until": None,
    })
    after = await pv2w.admin_force_retry(db, item_id=test_item_id, actor="test:admin")
    assert after["next_attempt_at"] <= datetime.now(timezone.utc).isoformat(), \
        "force_retry should reset next_attempt_at to now"
    print(f"[admin_force_retry] OK — next_attempt_at reset to {after['next_attempt_at']}")

    # 9. Test admin_force_dead_letter on the same item
    after = await pv2w.admin_force_dead_letter(
        db, item_id=test_item_id, actor="test:admin", reason="test_terminate",
    )
    assert after["status"] == pv2.ITEM_FAILED, "force_dead_letter should land in failed"
    print(f"[admin_force_dead_letter] OK — status=failed dead_lettered={after.get('dead_lettered')}")

    # Cleanup
    await db.payout_items_v2.delete_one({"item_id": test_item_id})
    await db.payout_v2_events.delete_many({"subject_id": test_item_id})
    await _cleanup(db)

    print("\n✅ PAY-V2-P3 end-to-end PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
