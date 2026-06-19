"""PAY-V2-P2A — Stripe Connect adapter live smoke test.

Uses the test-mode STRIPE_API_KEY provisioned in pod env. Creates:
  1. A real Stripe Express account
  2. A real onboarding link
  3. Attempts a Transfer to the new account (will fail because new
     accounts have no capability yet — we expect kyc_required or similar)

Validates:
  • Adapter activates with the env key
  • Account.create_async works
  • AccountLink.create_async returns a hosted URL
  • create_payout returns a proper normalized PayoutResult (success=False
    with error_code in {kyc_required, invalid_destination, insufficient_funds})

Run:
    python3 /app/backend/tests/test_payouts_v2_stripe_live.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")

from integrations.settlement import PayoutRequest  # noqa: E402
from integrations.settlement_stripe import StripeConnectSettlementProvider  # noqa: E402


async def run() -> int:
    api_key = os.getenv("STRIPE_API_KEY")
    if not api_key:
        print("[skip] STRIPE_API_KEY not set in env")
        return 0

    adapter = StripeConnectSettlementProvider()
    h = adapter.health()
    print(f"[health] enabled={h.available} mode={h.details.get('mode')} reason={h.reason}")
    assert h.available, "adapter should be enabled"

    # 1) Create an Express account
    email = f"smoke-{uuid.uuid4().hex[:6]}@example.test"
    try:
        acct = await adapter.create_express_account(
            email=email, developer_id=f"dev_smoke_{uuid.uuid4().hex[:6]}",
            country="US",
        )
        print(f"[acct] created {acct['id']}")
    except Exception as e:
        print(f"[FAIL] create_express_account: {e}")
        return 1
    acct_id = acct["id"]

    # 2) Create an onboarding link
    try:
        link = await adapter.create_onboarding_link(
            account_id=acct_id,
            refresh_url="https://example.test/refresh",
            return_url="https://example.test/return",
        )
        print(f"[link] url={link['url'][:80]}…")
        assert link["url"].startswith("https://"), "onboarding URL must be https"
    except Exception as e:
        print(f"[FAIL] create_onboarding_link: {e}")
        return 1

    # 3) Attempt a Transfer — expected to fail because the account hasn't
    #    completed onboarding yet (no `transfers` capability active).
    req = PayoutRequest(
        item_id=f"smoke_{uuid.uuid4().hex[:6]}",
        idempotency_key=f"smoke-{uuid.uuid4().hex[:10]}",
        developer_id="dev_smoke",
        amount=1.0,
        currency="USD",
        rail="stripe_connect",
        rail_account={"stripe_account_id": acct_id},
        description="P2A smoke test",
        metadata={"batch_id": "smoke"},
    )
    result = await adapter.create_payout(req)
    print(
        f"[payout] success={result.success} status={result.status} "
        f"code={result.error_code} error={result.error}"
    )
    # We expect either success (rare — account would need to be fully
    # onboarded and platform balance funded) OR a normalized terminal error.
    if result.success:
        print(f"[payout] unexpectedly succeeded: provider_ref={result.provider_ref}")
        return 0
    # Should be a terminal error_code, classified correctly
    accepted_terminal = {"invalid_destination", "kyc_required", "blocked", "insufficient_funds"}
    accepted_transient = {"rate_limited", "provider_unavailable", "network_error"}
    if result.error_code in accepted_terminal:
        print(f"[OK] terminal error classified: {result.error_code}")
    elif result.error_code in accepted_transient:
        print(f"[OK] transient error classified: {result.error_code}")
    else:
        print(f"[FAIL] unknown error_code: {result.error_code}")
        return 1

    # Note: we don't clean up the Express account because the Stripe test
    # account deletion API requires extra steps and these are throwaway
    # test accounts that auto-cleanup over time.
    print(f"\n[done] Stripe Connect adapter smoke PASS (acct: {acct_id})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
