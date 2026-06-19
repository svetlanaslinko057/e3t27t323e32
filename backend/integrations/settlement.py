"""
PAY-V2-P1 — SettlementProvider abstraction.

Outbound payment contract (pay developers OUT). Mirror of `PaymentProvider`
(which is inbound — charge clients).

Principles enforced (per `PAY_V2_P0_CHARTER.md`):
  - Pr-3 Provider abstraction — Stripe/PayPal/Wise/crypto behind one ABC.
  - Pr-5 Idempotency — `idempotency_key` REQUIRED on `create_payout`.
  - Pr-1 Authority — provider response is settlement signal only; canonical
    state lives in `money_ledger` + `payout_v2_*_events`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional

from .base import Capability, Provider


# ──────────────────────────────────────────────────────────────────────
# Vendor-neutral request / result types
# ──────────────────────────────────────────────────────────────────────
@dataclass
class PayoutRequest:
    """Vendor-neutral input for `create_payout`."""

    item_id: str
    """Our internal payout_item.item_id — surfaced back in webhook."""
    idempotency_key: str
    """REQUIRED. Provider must reject duplicates inside the active window."""

    developer_id: str
    amount: float
    """Always positive. v2 launch constrains currency to 'USD' (Pr-10)."""
    currency: str = "USD"

    rail: str = "stripe_connect"
    """`stripe_connect` | `paypal` | `wise` | `bank_transfer` | `crypto` | `mock`."""

    rail_account: dict = field(default_factory=dict)
    """Rail-specific destination — bank account, PayPal email, wallet address.
    Vendor adapter unpacks; operational code never reads this."""

    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class PayoutResult:
    """Identical shape across all SettlementProvider implementations."""

    success: bool
    provider_ref: Optional[str]
    """Opaque vendor-side ID we'll receive back in the webhook."""
    status: str = "initiated"
    """`initiated` | `in_flight` | `failed` — initial state from provider."""
    error: Optional[str] = None
    error_code: Optional[str] = None
    """Normalized error code (`insufficient_funds`, `invalid_destination`,
    `kyc_required`, `rate_limited`, `provider_unavailable`, `unknown`)."""
    estimated_settlement_at: Optional[str] = None
    """ISO-8601 — provider's best estimate of when funds clear. Optional."""
    fees_provider: float = 0.0
    """USD fee deducted at submission. May be 0 at this stage (settled later)."""
    raw: dict = field(default_factory=dict)
    """Debug-only — operational code MUST NEVER read this."""


@dataclass
class SettlementEvent:
    """Normalized outbound-payment webhook event."""

    valid: bool
    item_id: Optional[str]
    """Our payout_item.item_id (echoed back from PayoutRequest)."""
    provider_ref: Optional[str]
    status: str
    """`initiated` | `in_flight` | `confirmed` | `settled` | `failed` |
    `returned` | `disputed` | `cancelled`."""
    event_type: Optional[str] = None
    """Normalized event name. e.g. `payout_initiated` | `payout_settled` |
    `payout_failed` | `payout_returned`. Vendor-specific names are mapped
    here by the live adapter — business logic MUST NOT switch on raw
    vendor strings."""
    amount: Optional[float] = None
    currency: Optional[str] = None
    fees_provider: Optional[float] = None
    fees_fx: Optional[float] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    occurred_at: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class ReconciliationLine:
    """One row from a provider's settlement report."""

    provider_ref: str
    amount: float
    currency: str
    settled_at: str
    fees_provider: float = 0.0
    fees_fx: float = 0.0


@dataclass
class ReconciliationResult:
    matched: int
    unmatched: int
    discrepancies: list = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# SettlementProvider ABC
# ──────────────────────────────────────────────────────────────────────
class SettlementProvider(Provider, abc.ABC):
    """Outbound payment rail (pay developer OUT)."""

    capability = Capability.SETTLEMENT  # registered in base.py below

    @abc.abstractmethod
    async def create_payout(self, req: PayoutRequest) -> PayoutResult:
        """Submit one payout to the rail. Must be idempotent on
        `req.idempotency_key`. If a payout with the same key was already
        accepted, return its prior result rather than raising."""
        ...

    @abc.abstractmethod
    async def verify_webhook(self, body: bytes, headers: dict) -> SettlementEvent:
        """Verify provider signature and normalize the event."""
        ...

    @abc.abstractmethod
    async def reconcile(
        self, lines: list[ReconciliationLine]
    ) -> ReconciliationResult:
        """Match provider settlement report lines to our internal payout_items
        by `provider_ref`. ADDITIVE-ONLY (per Pr-4) — emits events, never
        mutates historical batch/item documents in place."""
        ...
