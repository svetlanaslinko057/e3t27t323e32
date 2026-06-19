"""
Phase 2C-B4.3-B — withdrawal reservation lifecycle tests.

Covers the new MoneyService methods and bridges introduced in B4.3-B
(no legacy writers touched yet — that's D-1..D-4):
  • reserve_withdrawal       (ac_dev → ac_reserved)
  • release_withdrawal_reservation (ac_reserved → ac_dev)
  • pay_reserved_withdrawal  (ac_reserved → ac_ext)
  • bridge_payout_processed dispatches by legacy_kind
  • Hard guard on negative ac_reserved
  • Idempotency on all three methods

These tests run against the live MongoDB instance configured via
MONGO_URL/DB_NAME. Each test uses a unique developer_id to isolate
state — no shared fixtures, no global cleanup pressure.
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

import money_bridge
from domains.money import (
    AccountKind,
    Money,
    WithdrawalPaid,
    WithdrawalReleased,
    WithdrawalReserved,
    account_id,
)
from shared.errors import PolicyDenied

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _run(coro_factory):
    """Per-test isolated loop. `coro_factory` is a 0-arg async callable
    so the motor client + MoneyService are constructed INSIDE the new
    loop (otherwise Motor binds Futures to the wrong loop)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


async def _make_db():
    """Construct a fresh motor client on the CURRENT loop and reset the
    MoneyService singleton so it re-initialises on this loop too."""
    # Reset the bridge singleton — its _ledger holds a coll bound to the
    # prior loop. Fresh init re-binds to the current loop.
    money_bridge._money_service = None
    money_bridge._money_repo = None
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await money_bridge.init_money_service(db)
    return client, db


async def _bal(svc, kind, dev_id):
    """Helper — read balance from MoneyService."""
    m = await svc.balance_for(kind, dev_id)
    return m.cents


async def _seed_dev_balance(svc, dev_id, cents):
    """Credit `ac_dev:<dev_id>` with `cents` via an escrow_release seed."""
    project_id = f"test_proj_{dev_id}"
    await svc.hold_escrow(
        project_id=project_id,
        amount=Money(cents, "USD"),
        client_id=f"client_{dev_id}",
        actor="test_seed",
        idempotency_key=f"test_seed_hold:{dev_id}:{cents}",
    )
    await svc.release_escrow(
        project_id=project_id,
        amount=Money(cents, "USD"),
        developer_id=dev_id,
        actor="test_seed",
        fee_cents=0,
        idempotency_key=f"test_seed_release:{dev_id}:{cents}",
    )


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ── 1. Reserve: ac_dev decreases, ac_reserved increases ────────────────────

def test_reserve_withdrawal_moves_dev_to_reserved():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")

            await _seed_dev_balance(svc, dev, 5000)  # $50 in ac_dev

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 5000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0

            await svc.reserve_withdrawal(
                developer_id=dev,
                amount=Money(2000, "USD"),  # $20
                withdrawal_id=wid,
                actor="developer",
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 3000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 2000
        finally:
            client.close()

    _run(_go)


# ── 2. Release: ac_reserved decreases, ac_dev increases ────────────────────

def test_release_withdrawal_restores_dev_balance():
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
                developer_id=dev,
                amount=Money(2000, "USD"),
                withdrawal_id=wid,
                reason="cancelled_by_developer",
                actor="developer",
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 5000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0
        finally:
            client.close()

    _run(_go)


# ── 3. Paid: ac_reserved decreases, ac_ext increases ───────────────────────

def test_pay_reserved_drains_to_external():
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

            ext_before = await _bal(svc, AccountKind.EXTERNAL, dev)
            await svc.pay_reserved_withdrawal(
                developer_id=dev,
                amount=Money(2000, "USD"),
                withdrawal_id=wid,
                actor="admin",
                external_ref="BANK-REF-1",
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 3000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0
            assert await _bal(svc, AccountKind.EXTERNAL, dev) == ext_before + 2000
        finally:
            client.close()

    _run(_go)


# ── 4. Hard guard: negative ac_reserved blocked ────────────────────────────

def test_release_without_prior_reserve_fails_hard():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")

            with pytest.raises(PolicyDenied) as exc:
                await svc.release_withdrawal_reservation(
                    developer_id=dev,
                    amount=Money(2000, "USD"),
                    withdrawal_id=wid,
                    reason="unprovoked",
                    actor="test",
                )
            assert exc.value.code == "money_reserved_insufficient"
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0
        finally:
            client.close()

    _run(_go)


def test_pay_without_prior_reserve_fails_hard():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")

            await _seed_dev_balance(svc, dev, 5000)

            with pytest.raises(PolicyDenied) as exc:
                await svc.pay_reserved_withdrawal(
                    developer_id=dev,
                    amount=Money(2000, "USD"),
                    withdrawal_id=wid,
                    actor="admin",
                )
            assert exc.value.code == "money_reserved_insufficient"
            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 5000
        finally:
            client.close()

    _run(_go)


# ── 5. Idempotency: repeated calls collapse to one event ───────────────────

def test_reserve_is_idempotent():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)

            for _ in range(3):
                await svc.reserve_withdrawal(
                    developer_id=dev, amount=Money(2000, "USD"),
                    withdrawal_id=wid, actor="developer",
                )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 3000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 2000

            n = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_reserved",
                 "metadata.withdrawal_id": wid}
            )
            assert n == 2, f"reserve emitted {n} ledger rows, expected 2"
        finally:
            client.close()

    _run(_go)


def test_release_is_idempotent():
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

            for _ in range(3):
                await svc.release_withdrawal_reservation(
                    developer_id=dev, amount=Money(2000, "USD"),
                    withdrawal_id=wid, reason="cancelled_by_developer",
                    actor="developer",
                )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 5000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0

            n = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_released",
                 "metadata.withdrawal_id": wid}
            )
            assert n == 2
        finally:
            client.close()

    _run(_go)


def test_pay_is_idempotent():
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

            for _ in range(3):
                await svc.pay_reserved_withdrawal(
                    developer_id=dev, amount=Money(2000, "USD"),
                    withdrawal_id=wid, actor="admin",
                    external_ref="REF-1",
                )

            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0
            n = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_paid",
                 "metadata.withdrawal_id": wid}
            )
            assert n == 2
        finally:
            client.close()

    _run(_go)


# ── 6. Bridge dispatch by legacy_kind ──────────────────────────────────────

def test_bridge_payout_processed_routes_withdrawal_via_reserved():
    """When legacy_kind='withdrawal', the bridge must hit the reservation
    path (ac_reserved → ac_ext), NOT the legacy direct-drain path."""
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

            dev_before = await _bal(svc, AccountKind.DEVELOPER_WALLET, dev)
            ext_before = await _bal(svc, AccountKind.EXTERNAL, dev)

            await money_bridge.bridge_payout_processed(
                developer_id=dev,
                amount_dollars=20.0,
                legacy_id=wid,
                legacy_kind="withdrawal",
                actor="admin",
                external_ref="BANK-1",
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == dev_before
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 0
            assert await _bal(svc, AccountKind.EXTERNAL, dev) == ext_before + 2000

            n = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_paid",
                 "metadata.withdrawal_id": wid}
            )
            assert n == 2
        finally:
            client.close()

    _run(_go)


def test_bridge_payout_processed_keeps_legacy_path_for_batch():
    """When legacy_kind='payout_batch', the bridge must STILL hit the
    legacy ac_dev → ac_ext path. B4.3-B does not regress non-withdrawal
    payouts."""
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            batch_id = _uid("batch")
            ext_ref = f"BATCH-REF-{batch_id}"

            await _seed_dev_balance(svc, dev, 5000)

            dev_before = await _bal(svc, AccountKind.DEVELOPER_WALLET, dev)
            ext_before = await _bal(svc, AccountKind.EXTERNAL, dev)
            reserved_before = await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev)

            await money_bridge.bridge_payout_processed(
                developer_id=dev,
                amount_dollars=20.0,
                legacy_id=batch_id,
                legacy_kind="payout_batch",
                actor="admin",
                external_ref=ext_ref,
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == dev_before - 2000
            assert await _bal(svc, AccountKind.EXTERNAL, dev) == ext_before + 2000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == reserved_before

            # Kind must be 'payout', not 'withdrawal_paid'.
            # The legacy process_payout writes 2 rows but only the debit
            # carries metadata.payout_batch_id (credit metadata uses
            # source_entry_id + external_ref). So we count the pair via
            # external_ref which is on both rows.
            n_payout = await db.money_ledger_events.count_documents(
                {"kind": "payout",
                 "metadata.external_ref": ext_ref}
            )
            assert n_payout == 2
            # Sanity: NO withdrawal_paid rows for this batch
            n_paid = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_paid",
                 "metadata.withdrawal_id": batch_id}
            )
            assert n_paid == 0
        finally:
            client.close()

    _run(_go)


def test_bridge_payout_processed_suppressed_without_reservation():
    """When legacy_kind='withdrawal' but no reservation has been emitted
    (pre-B4.3-D state), the bridge must swallow PolicyDenied and log —
    NOT raise. This preserves the existing legacy-correctness-comes-first
    invariant during the rollout window."""
    async def _go():
        client, db = await _make_db()
        try:
            dev = _uid("dev")
            wid = _uid("wd")
            result = await money_bridge.bridge_payout_processed(
                developer_id=dev,
                amount_dollars=20.0,
                legacy_id=wid,
                legacy_kind="withdrawal",
                actor="admin",
            )
            assert result is None
        finally:
            client.close()

    _run(_go)


# ── 7. End-to-end lifecycle: reserve → paid (conservation) ─────────────────

def test_full_reserve_to_paid_chain_balanced():
    """The chain ac_dev → ac_reserved → ac_ext must conserve money."""
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
            await svc.pay_reserved_withdrawal(
                developer_id=dev, amount=Money(4000, "USD"),
                withdrawal_id=wid, actor="admin",
                external_ref="BANK-REF",
            )

            dev_bal = await _bal(svc, AccountKind.DEVELOPER_WALLET, dev)
            res_bal = await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev)
            ext_bal = await _bal(svc, AccountKind.EXTERNAL, dev)

            assert dev_bal == 6000
            assert res_bal == 0
            assert ext_bal == 4000
            assert dev_bal + res_bal + ext_bal == 10000
        finally:
            client.close()

    _run(_go)


# ── 8. End-to-end: reserve → release (no leak, no orphan) ──────────────────

def test_reserve_then_release_then_reserve_again():
    async def _go():
        client, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid_a = _uid("wd")
            wid_b = _uid("wd")
            await _seed_dev_balance(svc, dev, 5000)

            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid_a, actor="developer",
            )
            await svc.release_withdrawal_reservation(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid_a, reason="cancelled_by_developer",
                actor="developer",
            )
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2000, "USD"),
                withdrawal_id=wid_b, actor="developer",
            )

            assert await _bal(svc, AccountKind.DEVELOPER_WALLET, dev) == 3000
            assert await _bal(svc, AccountKind.RESERVED_WITHDRAWAL, dev) == 2000
        finally:
            client.close()

    _run(_go)
