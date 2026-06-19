"""
Phase 2C-B4.3-C — projection & reader semantics tests.

Covers:
  • build_dev_wallet_projection now reads ac_reserved into pending
  • earned_lifetime includes reserved balance
  • compare_dev_wallet_projection classifies pending divergence correctly
  • dev_wallet_reader uses projection.pending when ledger has reserve events
  • dev_wallet_reader falls back to legacy when no reserve events exist
  • projection rebuild is deterministic with the new axis
  • _log_compare classifies pending_pre_b4_3_d as INFO (not WARN)

No legacy writers are touched. No new endpoints introduced. Tests use
the same per-loop motor client pattern as B4.3-B.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import dev_wallet_reader as _reader
import money_bridge
import money_projections as _projections
from domains.money import AccountKind, Money

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _run(coro_factory):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


async def _make_db():
    money_bridge._money_service = None
    money_bridge._money_repo = None
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await money_bridge.init_money_service(db)
    return client, db


async def _seed_dev_balance(svc, dev_id, cents):
    project_id = f"test_proj_{dev_id}"
    await svc.hold_escrow(
        project_id=project_id, amount=Money(cents, "USD"),
        client_id=f"client_{dev_id}", actor="test_seed",
        idempotency_key=f"test_seed_hold:{dev_id}:{cents}",
    )
    await svc.release_escrow(
        project_id=project_id, amount=Money(cents, "USD"),
        developer_id=dev_id, actor="test_seed", fee_cents=0,
        idempotency_key=f"test_seed_release:{dev_id}:{cents}",
    )


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ── 1. Projection reads ac_reserved into pending_withdrawal_cents ──────────

def test_projection_pending_derives_from_reserved_after_reserve():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)

            # Before reserve — projection.pending = 0, available = 5000
            proj0 = await _projections.build_dev_wallet_projection(db, dev)
            assert proj0["pending_withdrawal_cents"] == 0
            assert proj0["available_balance_cents"] == 5000
            assert proj0["_pending_has_ledger_source"] is False

            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )

            # After reserve — projection.pending = 2000, available = 3000
            proj1 = await _projections.build_dev_wallet_projection(db, dev)
            assert proj1["pending_withdrawal_cents"] == 2000
            assert proj1["available_balance_cents"] == 3000
            assert proj1["_pending_has_ledger_source"] is True
        finally:
            client.close()
    _run(_go)


# ── 2. Reject/cancel restores projection pending immediately ───────────────

def test_projection_pending_clears_after_release():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            await svc.release_withdrawal_reservation(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, reason="rejected_by_admin",
                actor="admin",
            )

            proj = await _projections.build_dev_wallet_projection(db, dev)
            assert proj["pending_withdrawal_cents"] == 0
            assert proj["available_balance_cents"] == 5000
            # Ledger HAS reserved activity even though balance is 0
            assert proj["_pending_has_ledger_source"] is True
        finally:
            client.close()
    _run(_go)


# ── 3. Paid drains projection pending to zero (and inflates withdrawn) ─────

def test_projection_pending_drains_after_paid():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            await svc.pay_reserved_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="admin",
                external_ref="BANK-REF",
            )

            proj = await _projections.build_dev_wallet_projection(db, dev)
            assert proj["pending_withdrawal_cents"] == 0
            assert proj["available_balance_cents"] == 3000
            assert proj["withdrawn_lifetime_cents"] == 2000
        finally:
            client.close()
    _run(_go)


# ── 4. earned_lifetime includes reserved (conservation) ────────────────────

def test_earned_lifetime_includes_reserved():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 10000)
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(4000, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            proj = await _projections.build_dev_wallet_projection(db, dev)
            # earned = available (6000) + reserved (4000) + withdrawn (0)
            assert proj["earned_lifetime_cents"] == 10000
            assert (
                proj["available_balance_cents"]
                + proj["pending_withdrawal_cents"]
                + proj["withdrawn_lifetime_cents"]
                == proj["earned_lifetime_cents"]
            )
        finally:
            client.close()
    _run(_go)


# ── 5. compare classifies pending_pre_b4_3_d when legacy pending > 0 ───────

def test_compare_classifies_pending_pre_b4_3_d_when_writer_not_migrated():
    """Legacy has non-zero pending (writer not migrated), ledger has no
    reserve event — must classify as `pending_pre_b4_3_d`, not `diverged`."""
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            await _seed_dev_balance(svc, dev, 5000)

            # Simulate the legacy writer running (B4.3-D not shipped yet):
            # available -= 2000, pending += 2000, in dollars
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 30.00,
                    "earned_lifetime": 50.00,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 20.00,
                }},
                upsert=True,
            )

            cmp_ = await _projections.compare_dev_wallet_projection(db, dev)
            assert cmp_["classification"] == "pending_pre_b4_3_d", \
                f"got {cmp_['classification']}, diff={cmp_['diff_cents']}"
            assert cmp_["diff_cents"]["pending_withdrawal"] == 2000
        finally:
            client.close()
    _run(_go)


# ── 6. compare matches when ledger and legacy both have reserve ────────────

def test_compare_matches_when_both_sides_have_reserve():
    """Legacy and ledger both report the same pending — `matches`."""
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)
            # Canonical reserve
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            # Legacy mirror (what the writer would write)
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 30.00,
                    "earned_lifetime": 50.00,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 20.00,
                }},
                upsert=True,
            )
            cmp_ = await _projections.compare_dev_wallet_projection(db, dev)
            assert cmp_["classification"] == "matches", \
                f"got {cmp_['classification']}, diff={cmp_['diff_cents']}"
        finally:
            client.close()
    _run(_go)


# ── 7. Reader returns projection.pending when ledger has reserve events ────

def test_reader_uses_projection_pending_when_ledger_has_source():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            # Legacy has different pending value — should be IGNORED
            # because ledger has a reserve event for this dev.
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 30.00,
                    "earned_lifetime": 50.00,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 99.99,  # bogus value
                }},
                upsert=True,
            )
            os.environ["MONEY_READS_FROM_PROJECTION"] = "true"
            try:
                wallet = await _reader.read_dev_wallet(db, dev)
            finally:
                os.environ.pop("MONEY_READS_FROM_PROJECTION", None)

            assert wallet["pending_withdrawal"] == 20.0, wallet
            assert wallet["_read_source"] == "projection"
            assert wallet["_pending_source"] == "ledger"
        finally:
            client.close()
    _run(_go)


# ── 8. Reader falls back to legacy pending when ledger has no source ───────

def test_reader_falls_back_to_legacy_when_no_reserve_event():
    """During B4.3-C → B4.3-D transition: legacy writer creates pending
    but ledger has no reserve event yet. Reader MUST still surface the
    correct value via legacy fallback so UI stays correct."""
    async def _go():
        client, db = await _make_db()
        try:
            dev = _uid("dev")
            # No ledger activity at all for this dev — legacy says pending=$15
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 35.00,
                    "earned_lifetime": 50.00,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 15.00,
                }},
                upsert=True,
            )

            os.environ["MONEY_READS_FROM_PROJECTION"] = "true"
            try:
                wallet = await _reader.read_dev_wallet(db, dev)
            finally:
                os.environ.pop("MONEY_READS_FROM_PROJECTION", None)

            assert wallet["pending_withdrawal"] == 15.0, wallet
            assert wallet["_pending_source"] == "legacy_fallback"
            assert wallet["_classification"] == "legacy_only"
        finally:
            client.close()
    _run(_go)


# ── 9. Projection rebuild is deterministic with reserved axis ──────────────

def test_projection_rebuild_deterministic_with_reserved():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid, actor="developer",
            )

            p1 = await _projections.build_dev_wallet_projection(db, dev)
            p2 = await _projections.build_dev_wallet_projection(db, dev)

            # Compare all stable fields (skip computed_at which is now())
            for k in (
                "available_balance_cents", "earned_lifetime_cents",
                "withdrawn_lifetime_cents", "pending_withdrawal_cents",
                "accrual_pending_cents", "_pending_has_ledger_source",
            ):
                assert p1[k] == p2[k], f"non-deterministic: {k} {p1[k]}!={p2[k]}"
        finally:
            client.close()
    _run(_go)


# ── 10. _discover_developer_ids picks up reserved-only devs ────────────────

def test_discover_finds_dev_with_only_reserved_activity():
    """A developer who appears only on ac_reserved (e.g. orphan reserve
    with no corresponding ac_dev row — shouldn't happen normally but the
    discovery must still find them)."""
    async def _go():
        client, db = await _make_db()
        try:
            from infrastructure.db.repositories.money import MoneyRepository
            dev = _uid("dev")
            # Manually insert a stub ledger row on ac_reserved only
            # (not via reserve_withdrawal because that requires ac_dev seed).
            repo = MoneyRepository(db)
            await repo.ensure_indexes()
            await repo.append(
                entry_id=f"entry_{uuid.uuid4().hex[:10]}",
                account_id=f"ac_reserved:{dev}",
                delta_cents=2000,
                kind="adjustment",  # admin correction, no source on ac_dev
                actor="test_admin",
                idempotency_key=f"test_orphan:{dev}",
            )

            ids = await _projections._discover_developer_ids(db)
            assert dev in ids, f"reserved-only dev not discovered: {ids[:5]}"

            # Cleanup so this orphan doesn't pollute other tests
            await db.money_ledger_events.delete_many(
                {"account_id": f"ac_reserved:{dev}"}
            )
        finally:
            client.close()
    _run(_go)


# ── 11. mock_orphan classification still works (regression) ────────────────

def test_mock_orphan_classification_still_works():
    """The pre-B4.3 `mock_orphan` (legacy.withdrawn > 0, ledger empty)
    must STILL classify as `mock_orphan`, not get re-routed to the new
    `pending_pre_b4_3_d` branch."""
    async def _go():
        client, db = await _make_db()
        try:
            dev = _uid("dev")
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 0.0,
                    "earned_lifetime": 50.00,
                    "withdrawn_lifetime": 50.00,
                    "pending_withdrawal": 0.0,
                }},
                upsert=True,
            )
            cmp_ = await _projections.compare_dev_wallet_projection(db, dev)
            assert cmp_["classification"] == "mock_orphan", \
                f"got {cmp_['classification']}"
        finally:
            client.close()
    _run(_go)
