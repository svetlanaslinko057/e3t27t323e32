"""Phase 2C-B4.3-D4 acceptance — `cancel_developer_withdrawal` is now
single-CAS canonical-ledger-only.

D-4: the cancel handler atomically flips `dev_withdrawals.status →
cancelled` via `find_one_and_update` (no more find→update race window)
and emits a canonical `withdrawal_released(reason="cancelled_by_developer")`
event via `bridge_withdrawal_released`. The legacy
`dev_wallets.$inc {pending -A, available +A}` mirror write is REMOVED.

Critical invariant: the release amount is read from the row itself
(`dev_withdrawals.amount`), NEVER from caller input. Partial / over /
negative releases are accounting breaks, so the amount source must be
the same row that proved the reserve happened in the first place.

Acceptance checks (per phase contract):
  1. Cancel of `requested` → status=cancelled
  2. Canonical: ac_reserved↓, ac_dev↑
  3. Projection: pending↓, available↑
  4. Legacy `dev_wallets` UNTOUCHED by handler
  5. Double cancel → idempotent ({"already": "cancelled"}), no double release
  6. Cancel of `paid` → 409
  7. Cancel of `rejected` → 409
  8. Cancel of someone else's withdrawal → 404 (no info leak)
  9. Cancel of non-existent withdrawal → 404
 10. Static guard: no legacy `$inc` / `dev_wallets.update_one` in handler body
 11. Amount sourced from row, never from body (covered by an invariant test
     that POSTs an empty body)
"""
import asyncio
import uuid
from unittest.mock import patch  # noqa: F401 — kept for future use

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

import sys
sys.path.insert(0, "/app/backend")

import money_bridge  # noqa: E402
from domains.money import AccountKind, Money  # noqa: E402
import money_projections as _projections  # noqa: E402


BACKEND_URL = "http://localhost:8001/api"


def _run(coro_factory):
    """Fresh event loop per test so the MoneyService singleton (reset
    in _make_db) rebinds cleanly."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


async def _make_db():
    money_bridge._money_service = None
    money_bridge._money_repo = None
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_database"]
    await money_bridge.init_money_service(db)
    return client, db


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def _seed_dev_balance(svc, dev_id: str, cents: int) -> None:
    """Land cents on `ac_dev:<dev>` via an escrow hold+release pair."""
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


async def _developer_session() -> httpx.AsyncClient:
    """Open a fresh demo developer session bound by Bearer token."""
    boot = httpx.AsyncClient(timeout=15)
    try:
        r = await boot.post(f"{BACKEND_URL}/auth/demo", json={"role": "developer"})
        assert r.status_code == 200, r.text
        token = r.cookies.get("session_token")
        body = r.json()
        actual_dev_id = body["user_id"]
    finally:
        await boot.aclose()
    client = httpx.AsyncClient(
        timeout=15,
        headers={"Authorization": f"Bearer {token}"},
    )
    client._dev_id = actual_dev_id  # type: ignore[attr-defined]
    return client


async def _create_withdrawal(sess: httpx.AsyncClient, amount: float) -> str:
    """Create a withdrawal via the live D-2 handler and return the
    withdrawal_id. Asserts 200 so a setup failure shows as a setup
    error rather than a misleading test failure."""
    r = await sess.post(f"{BACKEND_URL}/developer/withdraw", json={"amount": amount})
    assert r.status_code == 200, f"setup: request failed: {r.text}"
    return r.json()["withdrawal_id"]


# ── 1. Happy path — cancel a requested withdrawal ────────────────────────

def test_cancel_requested_withdrawal_releases_reservation_canonically():
    """Acceptance #1, #2, #3, #4 — the cornerstone happy path.

    Reserve via the live D-2 path, then cancel via D-4 and prove:
      • status flipped to cancelled (HTTP 200)
      • ac_reserved drained back to 0
      • ac_dev restored to the original balance
      • projection pending = 0, available = restored
      • legacy `dev_wallets` UNTOUCHED — both axes identical before/after
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)  # $100

                wid = await _create_withdrawal(sess, 25.0)

                # Sanity: after request the canonical reserve is live.
                ac_dev = await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
                assert ac_dev.cents == 7500, ac_dev
                assert ac_res.cents == 2500, ac_res

                # Snapshot legacy *before* cancel.
                before = await db.dev_wallets.find_one({"user_id": dev}) or {}
                avail_before = float(before.get("available_balance", 0) or 0)
                pending_before = float(before.get("pending_withdrawal", 0) or 0)

                # Fire the D-4 cancel.
                r = await sess.post(f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel")
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["status"] == "cancelled"
                assert body["withdrawal_id"] == wid
                assert "already" not in body, "first-time cancel must NOT be idempotent-flagged"

                # Canonical: reservation released.
                ac_dev = await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
                assert ac_dev.cents == 10000, ac_dev
                assert ac_res.cents == 0, ac_res

                # Projection drained.
                proj = await _projections.build_dev_wallet_projection(db, dev)
                assert proj["pending_withdrawal_cents"] == 0, proj
                assert proj["available_balance_cents"] == 10000, proj

                # Legacy UNTOUCHED by D-4.
                after = await db.dev_wallets.find_one({"user_id": dev}) or {}
                avail_after = float(after.get("available_balance", 0) or 0)
                pending_after = float(after.get("pending_withdrawal", 0) or 0)
                assert avail_after == avail_before, (
                    f"D-4 violated: legacy available mutated "
                    f"{avail_before} -> {avail_after}"
                )
                assert pending_after == pending_before, (
                    f"D-4 violated: legacy pending mutated "
                    f"{pending_before} -> {pending_after}"
                )

                # Status row reflects the cancellation.
                row = await db.dev_withdrawals.find_one(
                    {"withdrawal_id": wid}, {"_id": 0}
                )
                assert row["status"] == "cancelled"
                assert row["cancelled_by"] == "developer"
                assert row.get("cancelled_at")
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 2. Idempotent re-cancel — no double release ──────────────────────────

def test_double_cancel_is_idempotent_and_does_not_double_release():
    """Acceptance #5.

    A second `cancel` on an already-cancelled row must:
      • return HTTP 200 with `{"already": "cancelled"}`
      • NOT emit a second `withdrawal_released` event for this withdrawal_id
      • leave the ledger balanced (no double release would push ac_dev
        above the original balance)
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)
                wid = await _create_withdrawal(sess, 30.0)

                # First cancel — real release.
                r1 = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel"
                )
                assert r1.status_code == 200, r1.text
                assert r1.json()["status"] == "cancelled"
                assert "already" not in r1.json()

                # Second cancel — idempotent.
                r2 = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel"
                )
                assert r2.status_code == 200, r2.text
                assert r2.json()["status"] == "cancelled"
                assert r2.json().get("already") == "cancelled", r2.json()

                # No double release: ac_dev still at original $100,
                # ac_reserved still 0.
                ac_dev = await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
                assert ac_dev.cents == 10000, ac_dev
                assert ac_res.cents == 0, ac_res

                # Ledger: exactly ONE pair of release events tagged
                # cancelled_by_developer for this withdrawal_id.
                events = await db.money_ledger_events.find({
                    "kind": "withdrawal_released",
                    "metadata.withdrawal_id": wid,
                    "metadata.reason": "cancelled_by_developer",
                }, {"_id": 0}).to_list(None)
                assert len(events) == 2, (
                    f"expected exactly 2 entries (debit+credit) for the single "
                    f"cancel release, got {len(events)}: {events}"
                )
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 3. Cancel of paid withdrawal → 409 ───────────────────────────────────

def test_cancel_of_paid_withdrawal_is_refused():
    """Acceptance #6.

    A withdrawal in `paid` state has already drained `ac_reserved → ac_ext`.
    Cancelling it would either double-spend (release ac_reserved that is
    already 0 → `money_reserved_insufficient`) or strand the payout
    record. The CAS predicate `status ∈ {requested, approved}` blocks
    this; we return 409 explaining the current state.
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)
                wid = await _create_withdrawal(sess, 20.0)

                # Force the row into `paid` directly (simulating admin
                # mark-paid having completed). We only flip the legacy
                # status here — the canonical ledger drain on paid is
                # B4.1's responsibility and not under test in D-4.
                await db.dev_withdrawals.update_one(
                    {"withdrawal_id": wid},
                    {"$set": {"status": "paid"}},
                )

                r = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel"
                )
                assert r.status_code == 409, r.text
                body = r.json()
                detail = body.get("message") or body.get("detail") or ""
                assert "paid" in detail.lower(), detail

                # Status not changed by the failed cancel.
                row = await db.dev_withdrawals.find_one(
                    {"withdrawal_id": wid}, {"_id": 0}
                )
                assert row["status"] == "paid"
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 4. Cancel of rejected withdrawal → 409 ───────────────────────────────

def test_cancel_of_rejected_withdrawal_is_refused():
    """Acceptance #7. Same logic as `paid` — the row is terminal,
    `ac_reserved` was already drained by D-1, cancel must refuse."""
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)
                wid = await _create_withdrawal(sess, 20.0)
                await db.dev_withdrawals.update_one(
                    {"withdrawal_id": wid},
                    {"$set": {"status": "rejected"}},
                )

                r = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel"
                )
                assert r.status_code == 409, r.text
                detail = r.json().get("message") or r.json().get("detail") or ""
                assert "rejected" in detail.lower(), detail
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 5. Cancel of someone else's withdrawal → 404 (no info leak) ──────────

def test_cancel_of_other_users_withdrawal_returns_404():
    """Acceptance #8. The CAS includes `user_id` so an attacker holding
    only the withdrawal_id can't cancel another dev's reserve. The
    response is 404 (not 403) so the existence of the row isn't leaked."""
    async def _go():
        client_db, db = await _make_db()
        try:
            # Owner session creates the withdrawal.
            owner_sess = await _developer_session()
            owner = owner_sess._dev_id  # type: ignore[attr-defined]
            attacker_sess = await _developer_session()
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, owner, 10000)
                wid = await _create_withdrawal(owner_sess, 25.0)

                # Attacker tries to cancel owner's withdrawal.
                r = await attacker_sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel"
                )
                assert r.status_code == 404, r.text

                # Owner's withdrawal still pending — attacker's call had
                # zero side effects.
                row = await db.dev_withdrawals.find_one(
                    {"withdrawal_id": wid}, {"_id": 0}
                )
                assert row["status"] == "requested"

                # Reserve still on canonical.
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, owner)
                assert ac_res.cents == 2500, ac_res
            finally:
                await owner_sess.aclose()
                await attacker_sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 6. Cancel of non-existent withdrawal → 404 ───────────────────────────

def test_cancel_of_nonexistent_withdrawal_returns_404():
    """Acceptance #9."""
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            try:
                r = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/wd_does_not_exist/cancel"
                )
                assert r.status_code == 404, r.text
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 7. Static guard — no legacy mutation in handler body ─────────────────

def test_cancel_handler_has_no_legacy_dev_wallets_mutation():
    """Acceptance #10 — AST-based regression guard.

    The handler body (excluding the docstring) must NOT contain:
      • `db.dev_wallets.update_one` calls
      • `$inc` on `pending_withdrawal` or `available_balance`
    AND must contain:
      • a canonical `bridge_withdrawal_released` call
      • the `cancelled_by_developer` reason tag
      • a `find_one_and_update` (the new atomic CAS)
    """
    import ast
    src = open("/app/backend/server.py").read()
    tree = ast.parse(src)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == "cancel_developer_withdrawal":
                target = node
                break
    assert target is not None, "cancel_developer_withdrawal not found"

    body_nodes = list(target.body)
    if (
        body_nodes
        and isinstance(body_nodes[0], ast.Expr)
        and isinstance(body_nodes[0].value, ast.Constant)
        and isinstance(body_nodes[0].value.value, str)
    ):
        body_nodes = body_nodes[1:]
    body_src = "\n".join(ast.unparse(n) for n in body_nodes)

    forbidden = [
        '"pending_withdrawal":',
        '"available_balance":',
        "dev_wallets.update_one",
    ]
    for fragment in forbidden:
        assert fragment not in body_src, (
            f"D-4 regression: `{fragment}` resurrected in "
            f"cancel_developer_withdrawal body"
        )

    required = [
        "bridge_withdrawal_released",
        "cancelled_by_developer",
        "find_one_and_update",
    ]
    for fragment in required:
        assert fragment in body_src, (
            f"cancel_developer_withdrawal lost required `{fragment}` "
            f"(D-4 / atomic CAS contract)"
        )


# ── 8. Amount-from-row invariant ─────────────────────────────────────────

def test_cancel_releases_exactly_row_amount_ignoring_body():
    """Critical invariant from the D-4 contract:

        "cancel must release exactly the amount originally reserved.
        Не брать amount из request body. Брать из dev_withdrawals.amount."

    Posting a malicious `amount` field in the cancel body must be
    ignored — the release MUST use the row amount. Otherwise an
    attacker could trigger partial / over / negative releases by
    crafting a body.

    We send a body with a deliberately-wrong amount and verify the
    ledger drains exactly the reserved figure ($25), not the malicious
    one ($999).
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)
                wid = await _create_withdrawal(sess, 25.0)

                # Deliberately-wrong amount in the body.
                r = await sess.post(
                    f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel",
                    json={"amount": 999.0, "currency": "BTC"},
                )
                assert r.status_code == 200, r.text

                # Ledger drained exactly $25 from ac_reserved → ac_dev.
                ac_dev = await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
                assert ac_dev.cents == 10000, (
                    f"D-4 amount invariant violated: ac_dev = {ac_dev}, "
                    f"expected 10000 (original $100)"
                )
                assert ac_res.cents == 0, ac_res

                # Audit trail: release amount is the row amount, NOT the body.
                events = await db.money_ledger_events.find({
                    "kind": "withdrawal_released",
                    "metadata.withdrawal_id": wid,
                    "metadata.reason": "cancelled_by_developer",
                }, {"_id": 0}).to_list(None)
                # The CREDIT entry to ac_dev should be +$25 (2500 cents).
                credits = [e for e in events if e["delta_cents"] > 0]
                assert len(credits) == 1, credits
                assert credits[0]["delta_cents"] == 2500, (
                    f"release credit not equal to row amount: "
                    f"{credits[0]['delta_cents']}"
                )
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)


# ── 9. Race-safety: concurrent cancels resolve to one winner ─────────────

def test_concurrent_cancels_have_exactly_one_winner():
    """Acceptance: the CAS must serialize concurrent attempts.

    Fire N parallel cancel requests against the same withdrawal_id.
    Exactly one must return without the `already` flag (the winner);
    the rest must report `already=cancelled`. The ledger must show
    exactly one release pair — no double drains, no negative reserves.
    """
    async def _go():
        client_db, db = await _make_db()
        try:
            sess = await _developer_session()
            dev = sess._dev_id  # type: ignore[attr-defined]
            try:
                svc = money_bridge.get_money_service()
                await _seed_dev_balance(svc, dev, 10000)
                wid = await _create_withdrawal(sess, 40.0)

                # Fire 5 cancels concurrently.
                responses = await asyncio.gather(*[
                    sess.post(f"{BACKEND_URL}/developer/withdrawals/{wid}/cancel")
                    for _ in range(5)
                ])
                bodies = [r.json() for r in responses]
                assert all(r.status_code == 200 for r in responses), [
                    r.text for r in responses
                ]
                # Exactly one winner (no `already` flag), rest idempotent.
                winners = [b for b in bodies if "already" not in b]
                losers = [b for b in bodies if b.get("already") == "cancelled"]
                assert len(winners) == 1, (
                    f"CAS race: expected exactly one winner, got "
                    f"{len(winners)}: {bodies}"
                )
                assert len(losers) == 4, (
                    f"CAS race: expected 4 idempotent responses, got "
                    f"{len(losers)}: {bodies}"
                )

                # Ledger: exactly one release pair, ac_dev fully restored.
                ac_dev = await svc.balance_for(AccountKind.DEVELOPER_WALLET, dev)
                ac_res = await svc.balance_for(AccountKind.RESERVED_WITHDRAWAL, dev)
                assert ac_dev.cents == 10000, ac_dev
                assert ac_res.cents == 0, ac_res

                pair = await db.money_ledger_events.find({
                    "kind": "withdrawal_released",
                    "metadata.withdrawal_id": wid,
                    "metadata.reason": "cancelled_by_developer",
                }, {"_id": 0}).to_list(None)
                assert len(pair) == 2, (
                    f"CAS race: ledger has {len(pair)} release entries, "
                    f"expected exactly 2 (single debit+credit pair)"
                )
            finally:
                await sess.aclose()
        finally:
            client_db.close()
    _run(_go)
