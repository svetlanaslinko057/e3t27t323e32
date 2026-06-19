"""
PAY-V2-P1 — MockSettlementProvider.

Deterministic local rail. Useful for:
  - dev / preview environments without real Stripe/PayPal credentials
  - integration tests (seed_money_demo end-to-end seal check)
  - failure-mode rehearsal — set MOCK_SETTLEMENT_FAIL=1 in env to force failures

NEVER touches a network. Returns synthetic `provider_ref` and immediately
reports `initiated`. The scheduler/worker (P3) will drive the rest of the
state machine via direct calls to `transition_item`.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

from .settlement import (
    PayoutRequest, PayoutResult, ReconciliationLine, ReconciliationResult,
    SettlementEvent, SettlementProvider,
)
from .base import AvailabilityMode, CapabilityState


class MockSettlementProvider(SettlementProvider):
    name = "mock-settlement"

    def __init__(self):
        # Allow tests to force a failure deterministically
        self._force_fail = bool(int(os.getenv("MOCK_SETTLEMENT_FAIL", "0") or 0))

    def health(self) -> CapabilityState:
        """Honest current availability (sync; no network)."""
        from .base import Capability
        return CapabilityState(
            capability=Capability.SETTLEMENT,
            provider_name=self.name,
            mode=AvailabilityMode.MOCK,
            available=True,
            reason="MockSettlementProvider — no provider keys configured (Stripe/PayPal env empty).",
            details={"force_fail": self._force_fail},
        )

    async def state(self) -> CapabilityState:
        return self.health()

    async def create_payout(self, req: PayoutRequest) -> PayoutResult:
        if self._force_fail:
            return PayoutResult(
                success=False,
                provider_ref=None,
                status="failed",
                error="forced failure (MOCK_SETTLEMENT_FAIL=1)",
                error_code="provider_unavailable",
            )
        ref = f"mockpay_{uuid.uuid4().hex[:16]}"
        return PayoutResult(
            success=True,
            provider_ref=ref,
            status="initiated",
            fees_provider=0.0,
            estimated_settlement_at=None,
            raw={"echo": {"item_id": req.item_id, "amount": req.amount, "rail": req.rail}},
        )

    async def verify_webhook(self, body: bytes, headers: dict) -> SettlementEvent:
        # Mock never sends real webhooks — return an invalid envelope
        return SettlementEvent(
            valid=False, item_id=None, provider_ref=None,
            status="failed", event_type=None,
            error="mock provider does not emit webhooks",
        )

    async def reconcile(self, lines):
        # No-op for mock: every line matches by construction
        return ReconciliationResult(matched=len(lines), unmatched=0, discrepancies=[])
