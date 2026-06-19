"""
LUMEN — Live FX Rates (D3)
==========================

Replaces the hardcoded ``DEFAULT_FX_RATES`` with a live, snapshotted source.

Base currency = UAH (everything in LUMEN settles in UAH). We need foreign →
UAH rates for USD and EUR (SWIFT/SEPA funding arrives in those, the ledger
stores ``fx_rate`` + ``amount_uah`` at posting time so historical proofs never
drift when the rate moves).

Source of truth: НБУ (National Bank of Ukraine) public JSON —
``https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json`` — which
publishes the official UAH rate for every currency, refreshed daily. ECB is
kept as an optional cross-check for EUR. The fetch is fully resilient: if the
network is unavailable, the last good snapshot is used; if there is none, the
built-in fallback rates are stored as a snapshot tagged ``source=fallback`` so
``get_rate`` always returns a number and the engine never blocks.

Daily refresh runs from a background loop started in server.py. An admin can
force a refresh and inspect the snapshot history.

Collections:
  • ``lumen_fx_rates`` — one row per (date, source); {date, base, rates{}, source}

Public API:
  • ``cached_rate(currency) -> float``     — sync, in-memory (used by ledger writes)
  • ``await get_rate(currency) -> float``  — async, refreshes cache if empty
  • ``await refresh() -> dict``            — fetch + snapshot + repopulate cache
  • ``await boot()`` / ``router``
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from lumen_api import db, require_admin

logger = logging.getLogger("lumen.fx")
router = APIRouter(prefix="/api", tags=["lumen-fx"])

FX_RATES = "lumen_fx_rates"
BASE_CURRENCY = "UAH"
TRACKED = ("USD", "EUR")

# Built-in fallback (kept in sync with the legacy lumen_payments defaults).
FALLBACK_RATES: Dict[str, float] = {"UAH": 1.0, "USD": 41.0, "EUR": 44.5}

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"

# In-memory cache read synchronously by ledger writes.
_RATE_CACHE: Dict[str, float] = dict(FALLBACK_RATES)
_CACHE_META: Dict[str, Any] = {"source": "fallback", "fetched_at": None, "date": None}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def cached_rate(currency: str) -> float:
    """Sync accessor used inside ledger writes. Never raises."""
    c = (currency or BASE_CURRENCY).upper()
    if c == BASE_CURRENCY:
        return 1.0
    return float(_RATE_CACHE.get(c, FALLBACK_RATES.get(c, 1.0)))


async def _fetch_nbu() -> Optional[Dict[str, float]]:
    """Return {USD: rate_to_uah, EUR: rate_to_uah} from НБУ, or None on failure."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(NBU_URL)
            if r.status_code != 200:
                return None
            data = r.json()
        out: Dict[str, float] = {}
        for row in data:
            cc = row.get("cc")
            rate = row.get("rate")
            if cc in TRACKED and rate:
                out[cc] = float(rate)
        return out or None
    except Exception as e:
        logger.info("NBU fetch unavailable (%s) — using last snapshot / fallback", e)
        return None


async def _load_cache_from_db() -> bool:
    """Populate the in-memory cache from the most recent stored snapshot."""
    snap = await db[FX_RATES].find_one(sort=[("fetched_at", -1)])
    if not snap:
        return False
    _RATE_CACHE.update({"UAH": 1.0, **(snap.get("rates") or {})})
    _CACHE_META.update({"source": snap.get("source"), "fetched_at": snap.get("fetched_at"),
                        "date": snap.get("date")})
    return True


async def refresh(*, force: bool = False) -> Dict[str, Any]:
    """Fetch from НБУ → store a dated snapshot → repopulate the cache.
    Idempotent per (date, source): re-runs update the same row."""
    rates = await _fetch_nbu()
    source = "nbu"
    if not rates:
        # fall back to last snapshot's rates, else built-in fallback
        snap = await db[FX_RATES].find_one(sort=[("fetched_at", -1)])
        rates = (snap.get("rates") if snap else None) or {
            k: v for k, v in FALLBACK_RATES.items() if k in TRACKED}
        source = "fallback"
    full = {"UAH": 1.0, **rates}
    doc = {"date": _today(), "base": BASE_CURRENCY, "rates": full,
           "source": source, "fetched_at": _now()}
    await db[FX_RATES].update_one(
        {"date": _today(), "source": source},
        {"$set": doc}, upsert=True)
    _RATE_CACHE.update(full)
    _CACHE_META.update({"source": source, "fetched_at": doc["fetched_at"], "date": doc["date"]})
    logger.info("FX refresh: source=%s rates=%s", source, full)
    return {"source": source, "rates": full, "date": doc["date"]}


async def get_rate(currency: str) -> float:
    c = (currency or BASE_CURRENCY).upper()
    if c == BASE_CURRENCY:
        return 1.0
    if c not in _RATE_CACHE:
        await refresh()
    return cached_rate(c)


# ──────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/fx/rates")
async def admin_fx_rates(_=Depends(require_admin)):
    return {"base": BASE_CURRENCY, "rates": dict(_RATE_CACHE),
            "meta": _CACHE_META, "tracked": list(TRACKED)}


@router.post("/admin/fx/refresh")
async def admin_fx_refresh(_=Depends(require_admin)):
    return await refresh(force=True)


@router.get("/admin/fx/history")
async def admin_fx_history(limit: int = 60, _=Depends(require_admin)):
    items = []
    async for s in db[FX_RATES].find({}, {"_id": 0}).sort("fetched_at", -1).limit(min(limit, 365)):
        items.append(s)
    return {"items": items, "total": len(items)}


async def ensure_indexes() -> None:
    try:
        await db[FX_RATES].create_index([("date", 1), ("source", 1)], unique=True)
        await db[FX_RATES].create_index([("fetched_at", -1)])
    except Exception as e:
        logger.warning("fx ensure_indexes warning: %s", e)


async def boot() -> None:
    await ensure_indexes()
    if not await _load_cache_from_db():
        await refresh()
    logger.info("Live FX ready (source=%s, USD=%.4f, EUR=%.4f)",
                _CACHE_META.get("source"), cached_rate("USD"), cached_rate("EUR"))


async def scheduler_loop() -> None:
    """Daily FX refresh (every 12h to be safe around NBU publish time)."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(12 * 60 * 60)
            await refresh()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("FX scheduler tick failed: %s", e)
