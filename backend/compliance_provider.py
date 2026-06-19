"""
LUMEN — Compliance Screening Provider Seam
==========================================

The **single integration seam** for sanctions / PEP / wallet screening. Business
logic (risk scoring, cases, AML audit, funding gates) calls a `ScreeningProvider`
interface — never a concrete vendor — so the data source can be swapped:

        SeedProvider  (default, in-house OFAC-live-capable + seed lists)
            ↓  (no business-logic changes)
        ComplyAdvantage / Refinitiv World-Check / Dow Jones / Sumsub / AMLBot

Selection is by env: `LUMEN_SCREENING_PROVIDER` (default "seed"). A new vendor is
added by implementing this interface and registering it in `_REGISTRY` — nothing
in `run_screening` / KYC / funding changes.

NOTE: This is intentionally an **abstraction only**. No real vendor is integrated
here — that decision is deferred until the bank / MLRO / jurisdiction is known
(to avoid paying for the wrong provider). `health()` reports honestly that the
default provider runs on in-house data with no licensed PEP/crypto feed.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


class ScreeningProvider:
    """Abstract screening provider. Methods return a ranked list of match dicts:
    {entry_id, full_name, source, list_type, program, score, dob_match}."""

    name: str = "base"
    live_data: bool = False

    async def screen_name(self, name: str, *, dob: Optional[str] = None,
                          country: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def screen_company(self, name: str, *, country: Optional[str] = None,
                             registration_number: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def screen_wallet(self, address: str, *,
                            asset: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "live_data": self.live_data}


class SeedProvider(ScreeningProvider):
    """Default provider — delegates to the in-house fuzzy-match watchlist engine
    (OFAC live-capable + seeded EU/UK/UA/PEP). Behaviour-preserving: it simply
    wraps `lumen_compliance_screening.screen_name`."""

    name = "seed"
    live_data = False  # honest: OFAC is live-capable, but PEP/EU/UK/UA are seed

    async def screen_name(self, name: str, *, dob: Optional[str] = None,
                          country: Optional[str] = None) -> List[Dict[str, Any]]:
        from lumen_compliance_screening import screen_name as _sn
        return await _sn(name, dob=dob, country=country)

    async def screen_company(self, name: str, *, country: Optional[str] = None,
                             registration_number: Optional[str] = None) -> List[Dict[str, Any]]:
        # The in-house watchlist contains entities too; screen by name.
        from lumen_compliance_screening import screen_name as _sn
        return await _sn(name, country=country)

    async def screen_wallet(self, address: str, *,
                            asset: Optional[str] = None) -> List[Dict[str, Any]]:
        # No crypto/wallet list in the seed engine. Seam is ready for a vendor
        # (e.g. Chainalysis / TRM / AMLBot) — returns no matches today.
        return []

    def health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "live_data": self.live_data,
            "capabilities": ["name", "company"],
            "missing": ["licensed_pep_feed", "wallet_screening"],
            "notes": "in-house engine: OFAC live-capable + seed EU/UK/UA/PEP; "
                     "no licensed PEP or wallet provider connected",
        }


# Registry of available providers. Future vendors register here, e.g.:
#   _REGISTRY["complyadvantage"] = ComplyAdvantageProvider
#   _REGISTRY["sumsub"]          = SumsubProvider
_REGISTRY: Dict[str, type] = {
    "seed": SeedProvider,
}

_provider_singleton: Optional[ScreeningProvider] = None


def get_provider() -> ScreeningProvider:
    """Return the active screening provider (cached). Selected by
    `LUMEN_SCREENING_PROVIDER` env (default 'seed')."""
    global _provider_singleton
    if _provider_singleton is None:
        key = (os.environ.get("LUMEN_SCREENING_PROVIDER") or "seed").strip().lower()
        cls = _REGISTRY.get(key, SeedProvider)
        _provider_singleton = cls()
    return _provider_singleton


def provider_health() -> Dict[str, Any]:
    return get_provider().health()


__all__ = ["ScreeningProvider", "SeedProvider", "get_provider", "provider_health"]
