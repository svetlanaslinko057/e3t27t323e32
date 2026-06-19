"""
LUMEN — Pool FX (USD base currency layer)  ·  H2.1
==================================================

USD is the **single base/settlement currency** for Pool OS. Every contribution
(UAH / EUR / USD / USDT / USDC …) is converted to USD at a *locked snapshot*
rate and the pool accounts exclusively in USD.

Rate sourcing (priority):
  1. **admin_market** — an admin-set market rate in `lumen_pool_fx_rates`
     (the real street/market rate the desk fixes — preferred per product spec).
  2. **nbu_derived**  — derived from the existing NBU UAH feed (`lumen_fx`):
        rate(currency→per-USD) = USD/UAH ÷ currency/UAH
  3. **fallback**     — built-in constants (engine never blocks).

Rate convention: `rate` = units of `currency` per **1 USD** (e.g. UAH 41.25/USD).
Conversion: `amount_usd = amount / rate`   (stablecoins & USD → rate = 1).

Public surface
  • await convert_to_usd(amount, currency) -> {amount_usd, fx_rate_to_usd, fx_source, fx_locked_at}
  • await get_usd_rate(currency) -> (rate, source)
  • router  (admin FX table CRUD)
  • await boot()  (seed UAH/EUR/USDT/USDC/USD)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, get_current_user as require_user

logger = logging.getLogger("lumen.pool_fx")
router = APIRouter(prefix="/api", tags=["lumen-pool-fx"])

FX = "lumen_pool_fx_rates"
BASE = "USD"
STABLECOINS = {"USDT", "USDC"}
# Built-in last-resort rates (currency units per 1 USD).
FALLBACK_PER_USD: Dict[str, float] = {"USD": 1.0, "UAH": 41.0, "EUR": 0.92,
                                      "USDT": 1.0, "USDC": 1.0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return f"pfx_{uuid4().hex[:16]}"


def _r2(x: Any) -> float:
    return round(float(x or 0), 2)


async def _admin_rate(currency: str) -> Optional[float]:
    row = await db[FX].find_one(
        {"currency": currency, "is_active": True},
        sort=[("valid_from", -1)])
    if row and row.get("rate"):
        return float(row["rate"])
    return None


async def _nbu_derived_rate(currency: str) -> Optional[float]:
    """Derive `currency per USD` from the NBU UAH feed (lumen_fx)."""
    try:
        import lumen_fx
        usd_uah = await lumen_fx.get_rate("USD")   # UAH per USD
        if not usd_uah:
            return None
        if currency == "UAH":
            return float(usd_uah)                  # UAH per USD
        cur_uah = await lumen_fx.get_rate(currency)  # UAH per `currency`
        if not cur_uah:
            return None
        # currency per USD = (UAH per USD) / (UAH per currency)
        return float(usd_uah) / float(cur_uah)
    except Exception as e:  # pragma: no cover
        logger.info("nbu derive failed for %s: %s", currency, e)
        return None


async def get_usd_rate(currency: str) -> Tuple[float, str]:
    """Return (rate_currency_per_usd, source). USD & stablecoins → (1.0, ...)."""
    c = (currency or "").upper()
    if c == BASE:
        return 1.0, "native"
    if c in STABLECOINS:
        return 1.0, "stablecoin"
    admin = await _admin_rate(c)
    if admin:
        return admin, "admin_market"
    derived = await _nbu_derived_rate(c)
    if derived:
        return derived, "nbu_derived"
    return FALLBACK_PER_USD.get(c, 1.0), "fallback"


async def convert_to_usd(amount: float, currency: str) -> Dict[str, Any]:
    """Convert an original amount to USD at a locked snapshot rate."""
    c = (currency or "").upper()
    rate, source = await get_usd_rate(c)
    if c == BASE or c in STABLECOINS:
        amount_usd = _r2(amount)
    else:
        amount_usd = _r2(float(amount) / float(rate)) if rate else 0.0
    return {
        "amount_usd": amount_usd,
        "fx_rate_to_usd": round(float(rate), 8),
        "fx_source": source,
        "fx_locked_at": _now(),
        "original_amount": _r2(amount),
        "original_currency": c,
    }


# ─────────────────────────────────────────────────────────────────────────
# Admin FX table
# ─────────────────────────────────────────────────────────────────────────
class SetFxRateRequest(BaseModel):
    currency: str
    rate: float = Field(gt=0, description="units of currency per 1 USD")
    source: str = "admin_market"


@router.get("/pool-fx/effective")
async def effective_pool_fx_rates(_=Depends(require_user)):
    """Investor-facing effective USD rates (for live contribution preview)."""
    out = {}
    for c in ("USD", "UAH", "EUR", "USDT", "USDC"):
        rate, source = await get_usd_rate(c)
        out[c] = {"rate_per_usd": round(rate, 8), "source": source}
    return {"base_currency": BASE, "effective": out}


@router.get("/admin/pool-fx/rates")
async def list_pool_fx_rates(_=Depends(require_admin)):
    active = []
    async for r in db[FX].find({"is_active": True}, {"_id": 0}).sort("currency", 1):
        if isinstance(r.get("valid_from"), datetime):
            r["valid_from"] = r["valid_from"].isoformat()
        active.append(r)
    # Effective rates (admin or derived) for the common set.
    effective = {}
    for c in ("UAH", "EUR", "USD", "USDT", "USDC"):
        rate, source = await get_usd_rate(c)
        effective[c] = {"rate_per_usd": round(rate, 8), "source": source}
    return {"base_currency": BASE, "active": active, "effective": effective}


@router.post("/admin/pool-fx/rates")
async def set_pool_fx_rate(body: SetFxRateRequest, admin=Depends(require_admin)):
    cur = body.currency.upper()
    if cur == BASE:
        raise HTTPException(400, "USD is the base currency (rate is always 1)")
    await db[FX].update_many({"currency": cur, "is_active": True},
                             {"$set": {"is_active": False}})
    doc = {
        "id": _new_id(),
        "currency": cur,
        "base_currency": BASE,
        "rate": float(body.rate),
        "source": body.source or "admin_market",
        "valid_from": _now(),
        "created_by": admin.get("id") or admin.get("user_id"),
        "created_at": _now(),
        "is_active": True,
    }
    await db[FX].insert_one(dict(doc))
    doc.pop("_id", None)
    if isinstance(doc.get("valid_from"), datetime):
        doc["valid_from"] = doc["valid_from"].isoformat()
    return {"ok": True, "rate": doc}


async def ensure_indexes() -> None:
    try:
        await db[FX].create_index("id", unique=True)
        await db[FX].create_index([("currency", 1), ("is_active", 1), ("valid_from", -1)])
    except Exception as e:  # pragma: no cover
        logger.warning("pool_fx index ensure failed: %s", e)


async def boot() -> None:
    """Seed admin_market rates for the common set if none exist yet (derived from
    NBU so the desk starts from a sane market number, then can override)."""
    await ensure_indexes()
    for cur in ("UAH", "EUR"):
        exists = await db[FX].find_one({"currency": cur, "is_active": True})
        if exists:
            continue
        rate, source = await get_usd_rate(cur)
        await db[FX].insert_one({
            "id": _new_id(), "currency": cur, "base_currency": BASE,
            "rate": round(float(rate), 8), "source": f"seed_{source}",
            "valid_from": _now(), "created_by": "boot", "created_at": _now(),
            "is_active": True,
        })
    for stable in ("USDT", "USDC"):
        exists = await db[FX].find_one({"currency": stable, "is_active": True})
        if not exists:
            await db[FX].insert_one({
                "id": _new_id(), "currency": stable, "base_currency": BASE,
                "rate": 1.0, "source": "stablecoin", "valid_from": _now(),
                "created_by": "boot", "created_at": _now(), "is_active": True,
            })
    logger.info("Pool FX (USD base) ready")


__all__ = ["convert_to_usd", "get_usd_rate", "router", "boot", "FX", "BASE"]
