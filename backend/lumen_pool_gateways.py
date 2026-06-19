"""
LUMEN — Pool Gateway Layer  ·  H2.2
===================================

A uniform abstraction over *how money arrives* into a pool. Pool OS stays the
single source of truth and only ever sees **amount_usd** — it must not care
whether $1000 arrived as a SEPA wire, a card, or 1000 USDT on Ethereum.

        Pool OS (source of truth)
               │
     ┌─────────┴─────────┐
  Fiat Gateway      Crypto Gateway
  (bank/SEPA/        (USDT/USDC on
   SWIFT/Stripe)      ETH/Polygon/…)
     └─────────┬─────────┘
          Contribution  →  amount_usd  →  one hard_cap_usd

Both gateways funnel into the SAME `confirm_contribution` core (hard-cap guard,
units, ledger, movement, allocation, certificate) — already USD-native.

This layer deliberately contains NO business logic (no dividends / revenue /
ownership / AML). The on-chain contract is a *payment + NFT mirror*, specified
separately in docs/CONTRACT_INTERFACE_SPEC.md — NOT implemented in Solidity here.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class PoolGateway:
    """Abstract gateway. `create_instructions` returns what the investor needs to
    pay; reconciliation/confirmation always routes back into Pool OS confirm."""

    key: str = "base"
    label: str = "Base"
    kind: str = "fiat"           # "fiat" | "crypto"
    currencies: List[str] = []

    def supports_currency(self, ccy: str) -> bool:
        return (ccy or "").upper() in self.currencies

    async def create_instructions(self, pool: Dict[str, Any],
                                  contribution: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        return {"key": self.key, "kind": self.kind, "currencies": self.currencies}


class FiatBankGateway(PoolGateway):
    key = "fiat"
    label = "Bank transfer (SEPA / SWIFT / local)"
    kind = "fiat"
    currencies = ["USD", "UAH", "EUR"]

    async def create_instructions(self, pool, contribution):
        return {
            "gateway": self.key,
            "method": "bank_transfer",
            "reference": contribution["reference"],
            "iban": os.environ.get("LUMEN_POOL_IBAN", "<configure LUMEN_POOL_IBAN>"),
            "beneficiary": os.environ.get("LUMEN_POOL_BENEFICIARY", pool.get("title")),
            "amount": contribution.get("original_amount"),
            "currency": contribution.get("original_currency"),
            "amount_usd": contribution.get("amount_usd"),
            "message": "Зробіть банківський переказ із цим призначенням платежу / "
                       "Make a bank transfer using this payment reference",
        }


class CryptoGateway(PoolGateway):
    key = "crypto"
    label = "Crypto (USDT / USDC)"
    kind = "crypto"
    currencies = ["USDT", "USDC"]

    async def create_instructions(self, pool, contribution):
        chain_id = int(os.environ.get("LUMEN_POOL_CHAIN_ID", "1"))
        return {
            "gateway": self.key,
            "method": "crypto_deposit",
            "chain_id": chain_id,
            "token": contribution.get("original_currency"),
            "token_address": os.environ.get(
                f"LUMEN_TOKEN_{(contribution.get('original_currency') or '').upper()}",
                "<configure token address>"),
            # The escrow contract address (deployed later from the Interface Spec).
            "contract_address": os.environ.get("LUMEN_POOL_CONTRACT_ADDRESS",
                                               "<pending escrow deployment>"),
            # On-chain reference linking the deposit back to this contribution.
            "contribution_ref": contribution["id"],
            "amount_token": contribution.get("original_amount"),
            "amount_usd": contribution.get("amount_usd"),
            "min_deposit_usd": pool.get("min_ticket"),
            "message": "Надішліть USDT/USDC на адресу контракту escrow з цим reference / "
                       "Send USDT/USDC to the escrow contract with this reference",
        }


_REGISTRY: Dict[str, PoolGateway] = {
    FiatBankGateway.key: FiatBankGateway(),
    CryptoGateway.key: CryptoGateway(),
}


def get_gateway(key: Optional[str]) -> PoolGateway:
    return _REGISTRY.get((key or "fiat").lower(), _REGISTRY["fiat"])


def list_gateways() -> List[Dict[str, Any]]:
    return [g.health() | {"label": g.label} for g in _REGISTRY.values()]


def pool_os_view(gateway: str, amount_usd: float) -> Dict[str, Any]:
    """The ONLY thing Pool OS should consume from a gateway."""
    return {"gateway": gateway, "amount_usd": round(float(amount_usd or 0), 2)}


__all__ = ["PoolGateway", "FiatBankGateway", "CryptoGateway",
           "get_gateway", "list_gateways", "pool_os_view"]
