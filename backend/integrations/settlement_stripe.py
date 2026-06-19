"""
PAY-V2-P2A — StripeConnectSettlementProvider.

Active live rail. Pays developers from the platform's Stripe balance to
their connected Express accounts via Transfers (test mode by default
because the provisioned key starts with `sk_test_`).

Architectural discipline (locked by user — do NOT regress):
  • This file is the ONLY place that knows about Stripe types/exceptions.
    Operational code reads `PayoutResult.status` / `error_code` — never
    `stripe.error.*` directly.
  • Idempotency is non-negotiable: `req.idempotency_key` is passed as the
    Stripe Idempotency-Key header. Retries with the same key are safe
    (Stripe dedupes server-side for 24h).
  • Async-friendly: uses `stripe.Transfer.create_async` so the FastAPI
    event loop is never blocked.
  • Self-disable cleanly: when `STRIPE_API_KEY` is missing, the adapter
    reports unavailable via `health()` and `create_payout` returns
    `provider_unavailable` (transient, will retry — but the worker's
    retry semantics give the operator time to set the key).
  • Webhook secret optional in dev/preview: if `STRIPE_WEBHOOK_SECRET` is
    set, signatures are verified; if missing AND env hint
    `PAY_V2_ALLOW_UNSIGNED_WEBHOOKS=1` is set, payloads are accepted
    unsigned (DEV ONLY — never set this flag in production).

Stripe API version pinned to the SDK default (15.x → 2025-12-18+ default).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import stripe

from .base import AvailabilityMode, Capability, CapabilityState
from .settlement import (
    PayoutRequest, PayoutResult, ReconciliationLine, ReconciliationResult,
    SettlementEvent, SettlementProvider,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Error classification — maps Stripe exception types to OUR normalized
# error_code vocabulary. Worker uses these to decide transient vs terminal.
# ──────────────────────────────────────────────────────────────────────
def _classify_stripe_error(exc: BaseException) -> str:
    """Map any Stripe exception to one of:
      transient  → rate_limited | provider_unavailable | network_error | timeout
      terminal   → invalid_destination | kyc_required | blocked | insufficient_funds
    """
    name = exc.__class__.__name__
    # Stripe SDK 15.x error hierarchy
    if name == "RateLimitError":
        return "rate_limited"
    if name in ("APIConnectionError",):
        return "network_error"
    if name in ("APIError", "StripeError") and name != "InvalidRequestError":
        # Server-side / transient infra
        return "provider_unavailable"
    if name in ("AuthenticationError", "PermissionError"):
        return "blocked"
    if name == "InvalidRequestError":
        msg = (str(getattr(exc, "user_message", "")) or str(exc)).lower()
        if "insufficient" in msg and "funds" in msg:
            return "insufficient_funds"
        if "no such destination" in msg or "no such recipient" in msg:
            return "invalid_destination"
        if "no such" in msg:
            return "invalid_destination"
        if "verification" in msg or "kyc" in msg or "capabilities" in msg or \
           "charges_enabled" in msg or "payouts_enabled" in msg:
            return "kyc_required"
        # Stripe's `account_invalid`, `account_country_invalid` etc. all bucket
        # here — terminal: destination is wrong, retrying won't help.
        return "invalid_destination"
    if name == "CardError":
        # CardError doesn't really apply to Transfers, but for completeness
        return "invalid_destination"
    return "provider_unavailable"


# ──────────────────────────────────────────────────────────────────────
# Stripe Connect adapter
# ──────────────────────────────────────────────────────────────────────
class StripeConnectSettlementProvider(SettlementProvider):
    name = "stripe-connect"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> None:
        # Read at construction. If the env mutates, restart the process.
        self._api_key = api_key or os.getenv("STRIPE_API_KEY")
        self._webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET")
        self._enabled = bool(self._api_key)
        self._mode = "live" if (self._api_key or "").startswith("sk_live_") else "test"
        if self._enabled:
            # The Stripe SDK pulls the key from this module-global. We set
            # it per-call below via `api_key=` on each method to be explicit
            # and thread-safe.
            stripe.api_key = self._api_key
            logger.info(
                "StripeConnect adapter enabled (mode=%s, whsec=%s)",
                self._mode, "set" if self._webhook_secret else "missing",
            )
        else:
            logger.info("StripeConnect adapter DORMANT — STRIPE_API_KEY missing")

    # ── Capability state ──────────────────────────────────────────────
    def health(self) -> CapabilityState:
        if not self._enabled:
            return CapabilityState(
                capability=Capability.SETTLEMENT,
                provider_name=self.name,
                mode=AvailabilityMode.UNAVAILABLE,
                available=False,
                reason="STRIPE_API_KEY missing",
                details={"mode": self._mode, "webhook_secret": False},
            )
        # AvailabilityMode has only LIVE / MOCK / DEGRADED / UNAVAILABLE.
        # Test-mode Stripe is technically LIVE traffic to Stripe's sandbox —
        # surface mode="live" but use details to distinguish test vs prod.
        return CapabilityState(
            capability=Capability.SETTLEMENT,
            provider_name=self.name,
            mode=AvailabilityMode.LIVE,
            available=True,
            reason=None,
            details={
                "mode": self._mode,  # "test" | "live"
                "webhook_secret": bool(self._webhook_secret),
            },
        )

    async def state(self) -> CapabilityState:
        # Could add a lightweight `Balance.retrieve_async()` round-trip here,
        # but it costs an API call per worker_status refresh. Static for now.
        return self.health()

    # ── Outbound payout ───────────────────────────────────────────────
    async def create_payout(self, req: PayoutRequest) -> PayoutResult:
        if not self._enabled:
            return PayoutResult(
                success=False, provider_ref=None, status="failed",
                error="StripeConnect adapter dormant (STRIPE_API_KEY missing)",
                error_code="provider_unavailable",
            )

        # Destination resolution. Two acceptable shapes in rail_account:
        #   - {"stripe_account_id": "acct_..."}     (preferred — explicit)
        #   - {"connected_account": "acct_..."}     (fallback alias)
        dest = (
            req.rail_account.get("stripe_account_id")
            or req.rail_account.get("connected_account")
        )
        if not dest:
            return PayoutResult(
                success=False, provider_ref=None, status="failed",
                error="rail_account.stripe_account_id missing",
                error_code="invalid_destination",
            )

        amount_cents = int(round(req.amount * 100))
        if amount_cents <= 0:
            return PayoutResult(
                success=False, provider_ref=None, status="failed",
                error=f"amount must be positive, got {req.amount}",
                error_code="invalid_destination",
            )

        # Metadata pinned so we can recover item_id from webhook events.
        # ("transfer.created" gives us the destination + metadata back.)
        meta = dict(req.metadata or {})
        meta.setdefault("batch_id", str(meta.get("batch_id") or ""))
        meta["payout_item_id"] = req.item_id
        meta["developer_id"] = req.developer_id

        try:
            tr = await stripe.Transfer.create_async(
                amount=amount_cents,
                currency=(req.currency or "USD").lower(),
                destination=dest,
                description=req.description or f"Payout item {req.item_id}",
                metadata=meta,
                idempotency_key=req.idempotency_key,
                api_key=self._api_key,
            )
        except Exception as e:  # noqa: BLE001 — normalize, never raise
            code = _classify_stripe_error(e)
            logger.exception(
                "StripeConnect.create_payout failed item=%s code=%s",
                req.item_id, code,
            )
            return PayoutResult(
                success=False, provider_ref=None, status="failed",
                error=str(getattr(e, "user_message", None) or e),
                error_code=code,
            )

        return PayoutResult(
            success=True,
            provider_ref=tr["id"],
            status="initiated",
            fees_provider=0.0,
            raw={"object": "transfer", "balance_transaction": tr.get("balance_transaction")},
        )

    # ── Webhook verification + normalization ──────────────────────────
    async def verify_webhook(
        self, body: bytes, headers: Dict[str, str]
    ) -> SettlementEvent:
        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        allow_unsigned = (os.getenv("PAY_V2_ALLOW_UNSIGNED_WEBHOOKS") or "").strip() in (
            "1", "true", "yes", "on",
        )

        event_dict: Optional[Dict[str, Any]] = None
        if self._webhook_secret and sig:
            try:
                event = stripe.Webhook.construct_event(
                    payload=body, sig_header=sig, secret=self._webhook_secret,
                )
                event_dict = event if isinstance(event, dict) else dict(event)
            except Exception:
                logger.exception("Stripe webhook signature verify failed")
                return SettlementEvent(
                    valid=False, item_id=None, provider_ref=None,
                    status="failed", event_type="signature_invalid",
                )
        elif allow_unsigned:
            # DEV-ONLY path. Never set PAY_V2_ALLOW_UNSIGNED_WEBHOOKS=1 in prod.
            import json
            try:
                event_dict = json.loads(body.decode("utf-8"))
                logger.warning(
                    "Stripe webhook accepted UNSIGNED (PAY_V2_ALLOW_UNSIGNED_WEBHOOKS=1)"
                )
            except Exception:
                return SettlementEvent(
                    valid=False, item_id=None, provider_ref=None,
                    status="failed", event_type="bad_payload",
                )
        else:
            logger.warning(
                "Stripe webhook rejected — no signature header or "
                "STRIPE_WEBHOOK_SECRET missing"
            )
            return SettlementEvent(
                valid=False, item_id=None, provider_ref=None,
                status="failed", event_type="unverified",
            )

        return self._normalize_event(event_dict)

    def _normalize_event(self, ev: Dict[str, Any]) -> SettlementEvent:
        """Map a Stripe Event into our canonical SettlementEvent vocabulary.

        Vendor-specific event names are mapped HERE — business logic does
        NOT switch on raw Stripe strings (per Pr-3 provider abstraction).
        """
        et = ev.get("type") or ""
        obj = (ev.get("data") or {}).get("object") or {}
        meta = obj.get("metadata") or {}
        item_id = meta.get("payout_item_id")
        provider_ref = obj.get("id")
        amount = obj.get("amount")
        currency = obj.get("currency")
        # Stripe amounts are in cents — convert back to floats.
        if isinstance(amount, (int, float)):
            amount = float(amount) / 100.0
        if isinstance(currency, str):
            currency = currency.upper()

        # Default classification: unknown event → no-op but valid.
        status = "in_flight"
        event_type = et
        error = None
        error_code = None

        if et == "transfer.created":
            status = "initiated"
            event_type = "payout_initiated"
        elif et == "transfer.updated":
            # `amount_reversed > 0` means partial reversal in flight
            if (obj.get("amount_reversed") or 0) > 0:
                status = "returned"
                event_type = "payout_returned"
            else:
                status = "in_flight"
                event_type = "payout_in_flight"
        elif et == "transfer.reversed":
            status = "returned"
            event_type = "payout_returned"
        elif et == "transfer.failed":
            status = "failed"
            event_type = "payout_failed"
            error = obj.get("failure_message")
            error_code = obj.get("failure_code") or "provider_unavailable"
        elif et == "payout.paid":
            # Connected-account payout reached the developer's bank
            status = "settled"
            event_type = "payout_settled"
        elif et == "payout.failed":
            status = "failed"
            event_type = "payout_failed"
            error = obj.get("failure_message")
            error_code = obj.get("failure_code") or "provider_unavailable"
        elif et == "payout.canceled":
            status = "cancelled"
            event_type = "payout_cancelled"
        elif et == "account.application.deauthorized":
            # Developer revoked our Connect app — surface as failure
            status = "failed"
            event_type = "account_deauthorized"
            error_code = "blocked"
        elif et == "account.updated":
            # KYC milestone signal. Worker doesn't act on it directly;
            # the webhook router handles KYC flips separately. Return
            # valid=True so the route can dispatch.
            status = "in_flight"
            event_type = "account_updated"
        else:
            # Unknown event type — return valid but neutral, so the route
            # can decide whether to ignore or audit.
            return SettlementEvent(
                valid=True, item_id=item_id, provider_ref=provider_ref,
                status="in_flight", event_type=et,
                amount=amount, currency=currency, raw=ev,
            )

        return SettlementEvent(
            valid=True, item_id=item_id, provider_ref=provider_ref,
            status=status, event_type=event_type,
            amount=amount, currency=currency,
            error=error, error_code=error_code,
            occurred_at=None,  # Stripe `created` is unix-ts; converted in route if needed
            raw=ev,
        )

    # ── Reconciliation hook (consumed by P4 observer later) ───────────
    async def reconcile(
        self, lines: list[ReconciliationLine]
    ) -> ReconciliationResult:
        """List Transfers from Stripe and match by metadata.payout_item_id.

        Pr-4 ADDITIVE-ONLY: this returns a result. Mutating internal
        state is the caller's job (P4 observer emits divergence events).
        """
        if not self._enabled:
            return ReconciliationResult(
                matched=0, unmatched=len(lines),
                discrepancies=[{"reason": "adapter_dormant"}],
            )
        matched = 0
        unmatched = 0
        discrepancies: list = []
        for line in lines:
            try:
                tr = await stripe.Transfer.retrieve_async(
                    line.provider_ref, api_key=self._api_key,
                )
            except Exception as e:  # noqa: BLE001
                unmatched += 1
                discrepancies.append({
                    "provider_ref": line.provider_ref,
                    "reason": "lookup_failed",
                    "error": str(e),
                })
                continue
            stripe_amt = float(tr.get("amount", 0)) / 100.0
            if abs(stripe_amt - line.amount) > 0.005:
                discrepancies.append({
                    "provider_ref": line.provider_ref,
                    "reason": "amount_mismatch",
                    "local": line.amount, "remote": stripe_amt,
                })
                unmatched += 1
            elif (tr.get("amount_reversed") or 0) > 0:
                discrepancies.append({
                    "provider_ref": line.provider_ref,
                    "reason": "reversed",
                    "amount_reversed_cents": tr.get("amount_reversed"),
                })
                unmatched += 1
            else:
                matched += 1
        return ReconciliationResult(
            matched=matched, unmatched=unmatched, discrepancies=discrepancies,
        )

    # ── Helpers used by the onboarding endpoint (called from routes) ──
    async def create_express_account(
        self, *, email: str, developer_id: str, country: str = "US",
    ) -> Dict[str, Any]:
        """Create a Stripe Express connected account for a developer.
        Called only when the developer opts into Stripe payouts."""
        if not self._enabled:
            raise RuntimeError("StripeConnect adapter dormant")
        acct = await stripe.Account.create_async(
            type="express",
            country=country,
            email=email,
            capabilities={
                "transfers": {"requested": True},
            },
            metadata={"developer_id": developer_id},
            api_key=self._api_key,
        )
        return {"id": acct["id"], "object": acct.get("object")}

    async def create_onboarding_link(
        self, *, account_id: str, refresh_url: str, return_url: str,
    ) -> Dict[str, Any]:
        """Generate an AccountLink for Stripe-hosted Express onboarding."""
        if not self._enabled:
            raise RuntimeError("StripeConnect adapter dormant")
        link = await stripe.AccountLink.create_async(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
            api_key=self._api_key,
        )
        return {"url": link["url"], "expires_at": link.get("expires_at")}

    async def retrieve_account(self, account_id: str) -> Dict[str, Any]:
        if not self._enabled:
            raise RuntimeError("StripeConnect adapter dormant")
        acct = await stripe.Account.retrieve_async(account_id, api_key=self._api_key)
        return dict(acct)
