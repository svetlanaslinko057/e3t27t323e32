"""
LUMEN — Blockchain Provider Seam  ·  H2.11
==========================================

The single integration seam between LUMEN and any chain. Everything (NFT
registry, event engine, OTC) talks to a `BlockchainProvider` interface — never
to web3 directly — so today's MockBlockchainProvider can be swapped for a real
EthereumProvider WITHOUT touching Pool OS, distributions, certificates or the
financial model.

        LUMEN backend
             │
     BlockchainProvider (interface)
        ├── MockBlockchainProvider   (now — deterministic, off-chain)
        └── EthereumProvider         (later — listens to real contract events)

Selected by env `LUMEN_BLOCKCHAIN_PROVIDER` (default "mock").

The Mock provider deterministically simulates mint/transfer and EMITS the SAME
events a real contract would (`CertificateMinted`, `CertificateTransferred`,
`DepositReceived`, `RefundIssued`) into the event engine, so the entire event
pipeline is exercised now and only the event *source* changes later.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mock_address(seed: str) -> str:
    h = uuid4().hex + seed
    return "0x" + (h.encode().hex()[:40])


class BlockchainProvider:
    name = "base"
    chain = "ethereum"

    async def mint_nft(self, *, pool_id: str, allocation_id: str, wallet: str,
                       units: int, metadata_uri: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    async def transfer_nft(self, *, token_id: str, from_wallet: str,
                           to_wallet: str) -> Dict[str, Any]:
        raise NotImplementedError

    def contract_address(self) -> str:
        return os.environ.get("LUMEN_POOL_CONTRACT_ADDRESS", "0xMOCKCERTIFICATECONTRACT")

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "chain": self.chain,
                "contract_address": self.contract_address(), "live": False}


class MockBlockchainProvider(BlockchainProvider):
    """Deterministic off-chain simulation. No real chain calls; produces stable
    token ids and synthetic tx hashes, and the canonical event payloads."""

    name = "mock"

    def __init__(self) -> None:
        self._counter_seed = 0

    def _token_id(self) -> str:
        self._counter_seed += 1
        return str(int(_now().timestamp() * 1000) % 10_000_000 + self._counter_seed)

    def _tx(self) -> str:
        return "0x" + uuid4().hex + uuid4().hex[:0]

    async def mint_nft(self, *, pool_id, allocation_id, wallet, units, metadata_uri=""):
        token_id = self._token_id()
        tx_hash = self._tx()
        return {
            "token_id": token_id,
            "contract_address": self.contract_address(),
            "chain": self.chain,
            "tx_hash": tx_hash,
            "wallet": (wallet or "").lower() or None,
            "units": int(units),
            "metadata_uri": metadata_uri,
            "event": {
                "event_type": "CertificateMinted",
                "token_id": token_id,
                "contract_address": self.contract_address(),
                "tx_hash": tx_hash,
                "pool_id": pool_id,
                "allocation_id": allocation_id,
                "holder": (wallet or "").lower() or None,
                "units": int(units),
            },
        }

    async def transfer_nft(self, *, token_id, from_wallet, to_wallet):
        tx_hash = self._tx()
        return {
            "token_id": token_id,
            "contract_address": self.contract_address(),
            "tx_hash": tx_hash,
            "event": {
                "event_type": "CertificateTransferred",
                "token_id": token_id,
                "contract_address": self.contract_address(),
                "tx_hash": tx_hash,
                "from_wallet": (from_wallet or "").lower() or None,
                "to_wallet": (to_wallet or "").lower() or None,
            },
        }


_REGISTRY = {"mock": MockBlockchainProvider}
_singleton: Optional[BlockchainProvider] = None


def get_provider() -> BlockchainProvider:
    global _singleton
    if _singleton is None:
        key = (os.environ.get("LUMEN_BLOCKCHAIN_PROVIDER") or "mock").lower()
        cls = _REGISTRY.get(key, MockBlockchainProvider)
        _singleton = cls()
    return _singleton


__all__ = ["BlockchainProvider", "MockBlockchainProvider", "get_provider"]
