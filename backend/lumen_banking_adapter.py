"""
LUMEN 2.0 — Phase H1.2 — Banking Adapter
========================================

Provider-agnostic interface for the actual movement of money over banking rails.

The Funding Center (H1.1) writes transfers to the DB. The banking adapter is
the layer that, in production, will talk to Wise / Banking Circle / a direct
bank. Today we only ship `ManualBankAdapter` — it standardises the contract so
that a real provider is a swap-in change, not a rewrite.

Key decisions:

* ABC contract is **finalised** in this iteration. We will not refactor it when
  the real provider lands.
* `transfer.provider` (existing field, default "manual_ops") is the routing
  key. `get_adapter_for(provider)` returns the right adapter.
* No real third-party network calls in this module. Even when `Wise` /
  `BankingCircle` adapters arrive later, they live in `payment_providers/`.
* Adapter calls are best-effort and side-effect-free. Mutating LUMEN state
  (canonical_status, ledger postings) is done by the caller, NOT the adapter.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("lumen.banking_adapter")


# ═════════════════════════════════════════════════════════════════════════
# DTOs (vendor-neutral)
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class TransferIntent:
    transfer_id: str
    rail: str               # sepa | sepa_instant | swift
    direction: str          # inbound | outbound
    amount: float
    currency: str           # ISO 4217
    reference: str
    beneficiary_name: str
    beneficiary_iban: str
    beneficiary_bic: Optional[str] = None
    purpose: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AdapterStatus:
    """What an adapter reports about a transfer it tracks."""
    transfer_id: str
    provider: str
    provider_ref: Optional[str]
    canonical_status: str   # one of CANONICAL_STATUSES from lumen_funding_center
    settled_at: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class StatementEntry:
    """One row from a bank statement."""
    posted_at: str
    amount: float
    currency: str
    reference: Optional[str]
    counterparty_name: Optional[str]
    counterparty_iban: Optional[str]
    raw: dict = field(default_factory=dict)


@dataclass
class AccountVerification:
    iban: str
    iban_ok: bool
    country: Optional[str]
    bic_ok: Optional[bool] = None
    sepa_eligible: Optional[bool] = None
    note: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════════
# Abstract Banking Adapter
# ═════════════════════════════════════════════════════════════════════════

class BankingAdapter(abc.ABC):
    """Stable contract every banking provider must implement."""

    name: str = "abstract"

    @abc.abstractmethod
    async def create_transfer(self, intent: TransferIntent) -> AdapterStatus:
        """Submit a transfer instruction to the provider.

        Returns the immediate status reported by the provider. For real
        providers this is usually `submitted` or `pending_review`; for the
        manual adapter we report `submitted` and leave reconciliation to ops.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_transfer_status(self, transfer_id: str) -> AdapterStatus:
        """Query current provider status for a transfer.

        MUST be idempotent and side-effect-free. Used by the polling helper.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_statement(self, since: Optional[datetime] = None,
                              limit: int = 200) -> list[StatementEntry]:
        """Return a vendor-neutral statement slice from the provider.

        For the manual adapter this is the list of confirmed transfers in the
        given window (we don't read a real bank statement — yet).
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def verify_account(self, iban: str,
                              bic: Optional[str] = None) -> AccountVerification:
        """Validate IBAN/BIC checksums + return SEPA eligibility."""
        raise NotImplementedError


# ═════════════════════════════════════════════════════════════════════════
# ManualBankAdapter — the only implementation shipping in this iteration
# ═════════════════════════════════════════════════════════════════════════

class ManualBankAdapter(BankingAdapter):
    """Adapter that defers all real bank work to a human operator.

    All state lives in LUMEN's own DB. This implementation simply mirrors
    canonical_status back from the transfers collection. It is used until a
    real provider is integrated.
    """

    name = "manual_ops"

    async def create_transfer(self, intent: TransferIntent) -> AdapterStatus:
        # The Funding Center already wrote the transfer to DB before calling us.
        # We do not generate a provider_ref — ops will fill it on /confirm.
        return AdapterStatus(
            transfer_id=intent.transfer_id,
            provider=self.name,
            provider_ref=None,
            canonical_status="submitted",
        )

    async def get_transfer_status(self, transfer_id: str) -> AdapterStatus:
        from lumen_api import db
        from lumen_funding_center import canonical_status as _cs
        t = await db.lumen_institutional_transfers.find_one(
            {"id": transfer_id}, {"_id": 0},
        )
        if not t:
            return AdapterStatus(transfer_id=transfer_id, provider=self.name,
                                  provider_ref=None,
                                  canonical_status="draft")
        return AdapterStatus(
            transfer_id=transfer_id,
            provider=self.name,
            provider_ref=t.get("provider_ref"),
            canonical_status=_cs(t),
            settled_at=t.get("settled_at"),
            raw={},
        )

    async def get_statement(self, since: Optional[datetime] = None,
                              limit: int = 200) -> list[StatementEntry]:
        from lumen_api import db
        q: dict = {"status": "confirmed"}
        if since:
            q["settled_at"] = {"$gte": since.isoformat()}
        out: list[StatementEntry] = []
        cursor = db.lumen_institutional_transfers.find(q, {"_id": 0}).sort(
            "settled_at", -1).limit(limit)
        async for t in cursor:
            out.append(StatementEntry(
                posted_at=t.get("settled_at") or t.get("updated_at") or "",
                amount=float(t.get("amount") or 0),
                currency=t.get("currency"),
                reference=t.get("reference"),
                counterparty_name=t.get("beneficiary_name"),
                counterparty_iban=t.get("beneficiary_iban"),
            ))
        return out

    async def verify_account(self, iban: str,
                              bic: Optional[str] = None) -> AccountVerification:
        from lumen_institutional_rails import validate_iban, validate_bic, is_sepa_eligible
        ok, country, _err = validate_iban(iban)
        bic_ok = None
        if bic:
            bic_ok, _ = validate_bic(bic)
        sepa_ok = None
        if ok:
            sepa_ok, _ = is_sepa_eligible(iban)
        return AccountVerification(
            iban=iban,
            iban_ok=ok,
            country=country,
            bic_ok=bic_ok,
            sepa_eligible=sepa_ok,
        )


# ═════════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════════

ADAPTER_REGISTRY: dict[str, BankingAdapter] = {
    "manual_ops": ManualBankAdapter(),
}


def register_adapter(provider: str, adapter: BankingAdapter) -> None:
    """Allow downstream provider modules (Wise/BC/Direct) to register at import."""
    if not isinstance(adapter, BankingAdapter):
        raise TypeError("adapter must subclass BankingAdapter")
    ADAPTER_REGISTRY[provider] = adapter
    logger.info("BANKING ADAPTER registered: %s", provider)


def get_adapter_for(provider: Optional[str]) -> BankingAdapter:
    if not provider:
        return ADAPTER_REGISTRY["manual_ops"]
    return ADAPTER_REGISTRY.get(provider) or ADAPTER_REGISTRY["manual_ops"]


__all__ = [
    "BankingAdapter", "ManualBankAdapter",
    "TransferIntent", "AdapterStatus", "StatementEntry", "AccountVerification",
    "ADAPTER_REGISTRY", "register_adapter", "get_adapter_for",
]
