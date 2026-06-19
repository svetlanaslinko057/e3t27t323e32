"""
Phase 2C-B4.3-D1 — admin reject withdrawal removes legacy pending writer.

Tests for the removal of `dev_wallets.$inc {pending_withdrawal, available_balance}`
in `admin_reject_withdrawal`. The legacy writer is replaced by
`bridge_withdrawal_released` which mirrors the lifecycle to the canonical
ledger.

Test setup pattern: since the developer request endpoint still uses the
legacy writer (B4.3-D2 not shipped yet), we cannot exercise the full
request→reject chain end-to-end via HTTP. Instead, we:
  1. Seed `dev_wallets` with the legacy pending state (simulating the
     pre-D2 request writer having run).
  2. Seed `dev_withdrawals` with a `requested` row.
  3. Manually call `bridge_withdrawal_reserved` to emit the canonical
     reserve event (simulating what D-2 will do).
  4. Hit the `/api/admin/withdrawals/{id}/reject` endpoint.
  5. Verify:
     • status flipped to `rejected`
     • ac_reserved → ac_dev released in ledger
     • projection.pending = 0, projection.available correctly increased
     • legacy `dev_wallets.pending_withdrawal` UNCHANGED (drift expected)
     • re-reject is idempotent (200 with `already=rejected`)
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import money_bridge
import money_projections as _projections
from domains.money import AccountKind, Money

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")
BACKEND_URL = "http://localhost:8001/api"


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


async def _admin_session() -> httpx.AsyncClient:
    """Returns an httpx client with `Authorization: Bearer <token>` set
    to the admin's session token.

    Note: the session cookie is issued with `Secure; SameSite=none` so
    httpx won't replay it on plain HTTP localhost. The `get_current_user`
    handler falls back to the `Authorization: Bearer` header which is the
    robust transport for tests. We extract the session_token from the
    login response and attach it as a Bearer header on the returned
    client."""
    boot = httpx.AsyncClient(timeout=15)
    try:
        r = await boot.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": "admin@atlas.dev", "password": "admin123"},
        )
        assert r.status_code == 200, r.text
        token = r.cookies.get("session_token")
        assert token, f"no session_token in login response: {r.cookies}"
    finally:
        await boot.aclose()
    client = httpx.AsyncClient(
        timeout=15,
        headers={"Authorization": f"Bearer {token}"},
    )
    return client


# ── 1. Happy path: admin reject releases reservation canonically ──────────

def test_admin_reject_releases_reservation_via_ledger():
    async def _go():
        client_db, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            amount_dollars = 25.0
            amount_cents = 2500

            # Step 1 — seed ac_dev with $100, simulating prior earnings.
            await _seed_dev_balance(svc, dev, 10000)

            # Step 2 — simulate D-2: emit canonical reserve via bridge.
            await money_bridge.bridge_withdrawal_reserved(
                developer_id=dev,
                amount_dollars=amount_dollars,
                withdrawal_id=wid,
                actor="developer",
            )

            # Step 3 — also create the legacy dev_withdrawals row (the
            # existing legacy writer in `request_developer_withdrawal`).
            await db.dev_withdrawals.insert_one({
                "withdrawal_id": wid,
                "user_id": dev,
                "amount": amount_dollars,
                "status": "requested",
                "created_at": "2026-05-21T22:00:00+00:00",
                "destination": "mock-bank",
            })

            # Step 4 — seed legacy dev_wallets to simulate the request
            # writer also having decremented available/incremented pending.
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 75.0,
                    "earned_lifetime": 100.0,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 25.0,
                }},
                upsert=True,
            )

            # Pre-flight: ac_reserved = $25, ac_dev = $75 ($100 - $25)
            assert (
                await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
            ).cents == amount_cents
            assert (
                await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
            ).cents == 10000 - amount_cents

            legacy_before = await db.dev_wallets.find_one({"user_id": dev}, {"_id": 0})

            # Step 5 — hit the admin reject endpoint.
            http = await _admin_session()
            try:
                r = await http.post(
                    f"{BACKEND_URL}/admin/withdrawals/{wid}/reject",
                    json={"reason": "test_reject"},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["status"] == "rejected"
            finally:
                await http.aclose()

            # Step 6 — verify dev_withdrawals row flipped
            row = await db.dev_withdrawals.find_one(
                {"withdrawal_id": wid}, {"_id": 0}
            )
            assert row["status"] == "rejected"

            # Step 7 — verify CANONICAL release happened
            assert (
                await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
            ).cents == 0
            assert (
                await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
            ).cents == 10000  # restored to full $100

            # Step 8 — verify LEGACY dev_wallets NOT mutated by handler
            legacy_after = await db.dev_wallets.find_one({"user_id": dev}, {"_id": 0})
            # Pending stays at $25, available stays at $75 — exactly the
            # values legacy had pre-reject. D-1 removed the legacy writer.
            assert legacy_after["pending_withdrawal"] == legacy_before["pending_withdrawal"]
            assert legacy_after["available_balance"] == legacy_before["available_balance"]

            # Step 9 — projection now reflects canonical truth
            proj = await _projections.build_dev_wallet_projection(db, dev)
            assert proj["pending_withdrawal_cents"] == 0
            assert proj["available_balance_cents"] == 10000
            assert proj["_pending_has_ledger_source"] is True

            # Step 10 — cleanup so future test runs don't drift
            await db.dev_withdrawals.delete_one({"withdrawal_id": wid})
            await db.dev_wallets.delete_one({"user_id": dev})
        finally:
            client_db.close()
    _run(_go)


# ── 2. Re-reject is idempotent (already-handled path) ─────────────────────

def test_admin_reject_idempotent_when_already_rejected():
    async def _go():
        client_db, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 10000)
            await money_bridge.bridge_withdrawal_reserved(
                developer_id=dev, amount_dollars=20.0,
                withdrawal_id=wid, actor="developer",
            )
            await db.dev_withdrawals.insert_one({
                "withdrawal_id": wid, "user_id": dev,
                "amount": 20.0, "status": "requested",
                "created_at": "2026-05-21T22:00:00+00:00",
            })

            http = await _admin_session()
            try:
                # First reject — winner
                r1 = await http.post(
                    f"{BACKEND_URL}/admin/withdrawals/{wid}/reject",
                    json={"reason": "first"},
                )
                assert r1.status_code == 200
                assert r1.json()["status"] == "rejected"

                # Second reject — must be no-op (already=rejected)
                r2 = await http.post(
                    f"{BACKEND_URL}/admin/withdrawals/{wid}/reject",
                    json={"reason": "second"},
                )
                assert r2.status_code == 200
                body2 = r2.json()
                assert body2.get("already") == "rejected"
            finally:
                await http.aclose()

            # Ledger has exactly ONE released event (idempotent bridge)
            n_released = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_released",
                 "metadata.withdrawal_id": wid}
            )
            assert n_released == 2, f"expected 2 ledger rows, got {n_released}"

            # And ac_reserved is at 0 (not -$20 from double-release)
            assert (
                await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
            ).cents == 0

            await db.dev_withdrawals.delete_one({"withdrawal_id": wid})
        finally:
            client_db.close()
    _run(_go)


# ── 3. Reject a withdrawal that never had a canonical reserve event ───────

def test_admin_reject_without_prior_reserve_event():
    """Pre-D1 rows that pre-date the canonical reserve event (legacy-only
    history) — admin reject still flips status, bridge swallows
    `money_reserved_insufficient` policy denial. Legacy mutation NO LONGER
    happens (the writer was removed in D1). Operator sees the row flipped;
    divergence engine surfaces the missing canonical release."""
    async def _go():
        client_db, db = await _make_db()
        try:
            dev = _uid("dev")
            wid = _uid("wd")

            await db.dev_withdrawals.insert_one({
                "withdrawal_id": wid, "user_id": dev,
                "amount": 15.0, "status": "requested",
                "created_at": "2026-05-21T22:00:00+00:00",
            })
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 85.0,
                    "earned_lifetime": 100.0,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 15.0,
                }},
                upsert=True,
            )

            http = await _admin_session()
            try:
                r = await http.post(
                    f"{BACKEND_URL}/admin/withdrawals/{wid}/reject",
                    json={"reason": "test_no_reserve"},
                )
                assert r.status_code == 200, r.text
                assert r.json()["status"] == "rejected"
            finally:
                await http.aclose()

            # Status flipped
            row = await db.dev_withdrawals.find_one(
                {"withdrawal_id": wid}, {"_id": 0}
            )
            assert row["status"] == "rejected"

            # Bridge swallowed `money_reserved_insufficient` — no ledger
            # release event was emitted because there was nothing to release.
            n_released = await db.money_ledger_events.count_documents(
                {"kind": "withdrawal_released",
                 "metadata.withdrawal_id": wid}
            )
            assert n_released == 0

            # Legacy is unchanged by D-1 (writer removed)
            legacy = await db.dev_wallets.find_one(
                {"user_id": dev}, {"_id": 0}
            )
            assert legacy["pending_withdrawal"] == 15.0
            assert legacy["available_balance"] == 85.0

            await db.dev_withdrawals.delete_one({"withdrawal_id": wid})
            await db.dev_wallets.delete_one({"user_id": dev})
        finally:
            client_db.close()
    _run(_go)


# ── 4. Architecture invariant: no $inc pending_withdrawal in reject handler

def test_admin_reject_handler_has_no_pending_inc():
    """Static check: the `admin_reject_withdrawal` handler body must NOT
    contain any `$inc.*pending_withdrawal` mutation. This is the D-1
    completion check — if a future refactor re-introduces the legacy
    writer, this test fires immediately."""
    server_py = open("/app/backend/server.py").read()

    # Find the handler body
    start_marker = '@api_router.post("/admin/withdrawals/{withdrawal_id}/reject")'
    end_marker = '@api_router.post("/billing/invoice/'
    start = server_py.index(start_marker)
    end = server_py.index(end_marker, start)
    handler_body = server_py[start:end]

    # Strip comment lines (lines whose first non-whitespace char is `#`).
    # The handler's removal block intentionally cites the legacy names in
    # comments — that's documentation of the removal, not the writer.
    active_lines = [
        ln for ln in handler_body.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    active_code = "\n".join(active_lines)

    # No `pending_withdrawal` increment/decrement allowed in active code
    assert "pending_withdrawal" not in active_code, (
        "admin_reject_withdrawal still touches pending_withdrawal — D-1 regression!"
    )
    # No `available_balance` legacy increment allowed in active code
    assert '"available_balance"' not in active_code, (
        "admin_reject_withdrawal still touches available_balance — D-1 regression!"
    )
    # And NO `$inc` operation anywhere in active code (extra strict)
    assert "$inc" not in active_code, (
        "admin_reject_withdrawal still has a $inc — D-1 regression!"
    )
    # Must call the canonical bridge
    assert "bridge_withdrawal_released" in active_code, (
        "admin_reject_withdrawal no longer calls bridge_withdrawal_released"
    )



# ── 5. Divergence classifier: post-D1 admin-reject signature ──────────────

def test_divergence_classifies_post_b4_3_d1_admin_reject_drift():
    """After D-1, legacy `dev_wallets.pending_withdrawal` is no longer
    decremented when admin rejects. The ledger correctly releases the
    reserve (ac_reserved -> ac_dev) but legacy `pending` stays elevated.

    `compare_dev_wallet_projection` must surface this signature with the
    `pending_post_b4_3_d1` classification (INFO, not WARN) so the
    divergence engine can count it but the on-call channel stays quiet.

    Signature checked:
        • _pending_has_ledger_source == True (ledger has reserve activity)
        • legacy.pending > projection.pending (legacy is "stuck")
        • diff_available / earned / withdrawn within rounding
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            svc = money_bridge.get_money_service()
            dev = _uid("dev")
            wid = _uid("wd")
            await _seed_dev_balance(svc, dev, 10000)  # ac_dev = $100

            # Simulate D-2: reserve + release via the canonical service.
            await svc.reserve_withdrawal(
                developer_id=dev, amount=Money(2500, "USD"),
                withdrawal_id=wid, actor="developer",
            )
            await svc.release_withdrawal_reservation(
                developer_id=dev, amount=Money(2500, "USD"),
                withdrawal_id=wid, reason="rejected_by_admin",
                actor="admin",
            )

            # Legacy mirror: simulate the pre-D2 request writer having
            # decremented available/incremented pending, AND the D-1
            # admin-reject path NOT having decremented pending (because
            # we just removed that writer).
            await db.dev_wallets.update_one(
                {"user_id": dev},
                {"$set": {
                    "user_id": dev,
                    "available_balance": 75.0,  # 100 - 25 (request stage)
                    "earned_lifetime": 100.0,
                    "withdrawn_lifetime": 0.0,
                    "pending_withdrawal": 25.0,  # stuck — D-1 removed the decrement
                }},
                upsert=True,
            )

            cmp = await _projections.compare_dev_wallet_projection(db, dev)
            assert cmp["classification"] == "pending_post_b4_3_d1", (
                f"got {cmp['classification']}; cmp={cmp}"
            )
            # Diff signature (sub-case B — "request+reject in flight"):
            # both `available` and `pending` diverge but their sum is zero
            # (same dollars cross-bucketed in legacy). earned/withdrawn
            # match.
            d = cmp["diff_cents"]
            assert d["pending_withdrawal"] == 2500, d
            assert d["available_balance"] == -2500, d
            assert d["available_balance"] + d["pending_withdrawal"] == 0, d
            assert abs(d["earned_lifetime"]) <= 1, d
            assert abs(d["withdrawn_lifetime"]) <= 1, d

            # Cleanup so a re-run doesn't leak stale rows into other probes
            await db.dev_wallets.delete_one({"user_id": dev})
        finally:
            client_db.close()
    _run(_go)


def test_log_compare_does_not_warn_for_post_b4_3_d1(caplog):
    """`dev_wallet_reader._log_compare` must classify `pending_post_b4_3_d1`
    as INFO. Anything that surfaces as WARN here would page the on-call
    channel — and the whole point of B4.3-D1 is that this drift is
    expected and bounded."""
    import dev_wallet_reader as _reader  # noqa: F401 — imported for the side-effect
    comparison = {
        "classification": "pending_post_b4_3_d1",
        "diff_cents": {
            "available_balance": 0,
            "earned_lifetime": 0,
            "withdrawn_lifetime": 0,
            "pending_withdrawal": 2500,
        },
    }
    with caplog.at_level("INFO", logger="dev_wallet_reader"):
        _reader._log_compare("dev_test_post_d1", comparison)

    # Should log exactly once, at INFO, with `event=dev_wallet_read.mismatch`
    records = [
        r for r in caplog.records
        if "dev_wallet_read.mismatch" in r.getMessage()
    ]
    assert len(records) == 1, f"expected 1 mismatch log, got {len(records)}"
    assert records[0].levelname == "INFO", (
        f"pending_post_b4_3_d1 must be INFO, got {records[0].levelname}"
    )
