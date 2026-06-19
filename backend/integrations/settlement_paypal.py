"""
PAY-V2-P2A — PayPalPayoutsSettlementProvider (DORMANT SCAFFOLD).

Per user strategy: PayPal stays a *plug-in slot*, not an active rail.

What this file provides NOW:
  • Concrete class fulfilling `SettlementProvider` ABC contract
  • Env-aware activation (`enabled` iff `PAYPAL_CLIENT_ID`,
    `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` all present)
  • Capability registration (so `/api/integrations/capabilities` reports
    paypal=dormant in MOCK mode, not absent)
  • Webhook endpoint scaffold (returns 501 until configured)
  • Method stubs that return `provider_unavailable` when dormant

What this file does NOT do (per user direction):
  • NO live HTTP calls to PayPal
  • NO onboarding flow
  • NO sandbox setup
  • NO webhook signature verification logic

When user provisions all three env keys, this adapter activates and
worker's `_PROVIDERS_BY_RAIL["paypal"]` starts routing items to it.
At that point we add the actual httpx-based implementation in P2B.

The point of the dormant scaffold is to keep the architecture clean —
adding PayPal later does NOT require touching the worker, registry,
state machine, UI, or webhook router. ONLY this file changes.
"""

from __future__ import annotations

import logging
import os
from typing import Dict

from .base import AvailabilityMode, Capability, CapabilityState
from .settlement import (
    PayoutRequest, PayoutResult, ReconciliationLine, ReconciliationResult,
    SettlementEvent, SettlementProvider,
)

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    """Three env keys must ALL be set for PayPal to leave dormant mode."""
    return all([
        os.getenv("PAYPAL_CLIENT_ID"),
        os.getenv("PAYPAL_CLIENT_SECRET"),
        os.getenv("PAYPAL_WEBHOOK_ID"),
    ])


class PayPalPayoutsSettlementProvider(SettlementProvider):
    """PayPal Payouts rail — dormant until env keys provisioned.

    Mode auto-detect:
      • Live   — env keys present AND `PAYPAL_ENVIRONMENT=live`
      • Sandbox — env keys present AND `PAYPAL_ENVIRONMENT != live` (default)
      • Dormant — any key missing (MOCK mode reported)

    The actual live HTTP client (httpx-based) lands in P2B once the user
    supplies sandbox keys. This class shape stays unchanged then.
    """

    name = "paypal-payouts"

    def __init__(self) -> None:
        self._enabled = _is_configured()
        env = (os.getenv("PAYPAL_ENVIRONMENT") or "sandbox").strip().lower()
        self._mode = "live" if env == "live" else "sandbox"
        if self._enabled:
            logger.info(
                "PayPalPayouts adapter SCAFFOLD ENABLED (mode=%s) — "
                "ready for P2B implementation",
                self._mode,
            )
        else:
            logger.info(
                "PayPalPayouts adapter DORMANT — set PAYPAL_CLIENT_ID, "
                "PAYPAL_CLIENT_SECRET, PAYPAL_WEBHOOK_ID to enable"
            )

    # ── Capability state ──────────────────────────────────────────────
    def health(self) -> CapabilityState:
        if not self._enabled:
            return CapabilityState(
                capability=Capability.SETTLEMENT,
                provider_name=self.name,
                mode=AvailabilityMode.MOCK,
                available=False,
                reason="PAYPAL_CLIENT_ID/SECRET/WEBHOOK_ID missing — dormant scaffold",
                details={"phase": "scaffold", "mode": "dormant"},
            )
        # Even when keys present, P2A leaves PayPal dormant on purpose.
        # When P2B ships, change `available=True` + flip mode to SANDBOX/LIVE.
        return CapabilityState(
            capability=Capability.SETTLEMENT,
            provider_name=self.name,
            mode=AvailabilityMode.MOCK,
            available=False,
            reason="PayPal scaffold present; P2B (live calls) not yet shipped",
            details={"phase": "scaffold", "configured": True, "mode": self._mode},
        )

    async def state(self) -> CapabilityState:
        return self.health()

    # ── All operational methods short-circuit until P2B ──────────────
    async def create_payout(self, req: PayoutRequest) -> PayoutResult:
        return PayoutResult(
            success=False, provider_ref=None, status="failed",
            error="PayPal rail not yet implemented (P2B). Use stripe_connect or mock.",
            error_code="provider_unavailable",
        )

    async def verify_webhook(
        self, body: bytes, headers: Dict[str, str]
    ) -> SettlementEvent:
        # No verification until P2B lands the verify-webhook-signature flow.
        return SettlementEvent(
            valid=False, item_id=None, provider_ref=None,
            status="failed", event_type="paypal_dormant",
        )

    async def reconcile(
        self, lines: list[ReconciliationLine]
    ) -> ReconciliationResult:
        return ReconciliationResult(
            matched=0, unmatched=len(lines),
            discrepancies=[{"reason": "paypal_dormant_scaffold"}],
        )
