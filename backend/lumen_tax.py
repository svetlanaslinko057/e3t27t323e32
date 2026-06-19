"""
LUMEN — Tax Engine (D2) — Ukrainian withholding on investor income
===================================================================

Ukrainian-sourced investment income paid to resident individuals is subject to
withholding at source:

    ПДФО (personal income tax)         = 18.0 %
    Військовий збір (military levy/ВЗ) = 1.5 %
    ─────────────────────────────────────────
    total withholding                  = 19.5 %

LUMEN, as the payer (SPV/operator), is the tax agent: it withholds the tax and
remits it to the state. Therefore every income payout must record the full
breakdown and the platform must carry a **tax-liability ledger account** (money
withheld but not yet remitted).

This module owns:
  • ``get_config()`` / admin GET+PUT — rates are config (defaults 18% / 1.5%)
  • ``compute_withholding(gross, ...)`` — pure function → {gross, pdfo, vz,
    tax_total, net, effective_rate}
  • ``write_tax_liability(...)`` — append a ``tax_withheld`` ledger credit to the
    platform tax-liability account (so liability is queryable + auditable)
  • admin GET ``/admin/tax/liability`` — outstanding liability + recent rows

Non-residents: a per-investor ``tax_withholding_override`` (fraction) on the
profile takes precedence; ``tax_exempt=true`` zeroes withholding. Defaults to
the UA resident rate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, require_admin

logger = logging.getLogger("lumen.tax")
router = APIRouter(prefix="/api", tags=["lumen-tax"])

TAX_CONFIG = "lumen_tax_config"
CONFIG_ID = "ua_default"

# Statutory defaults (Ukraine).
DEFAULT_PDFO = 0.18
DEFAULT_VZ = 0.015

# Platform liability account in the ledger (money withheld, owed to the state).
TAX_LIABILITY_ACCOUNT = "platform_tax_liability"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _round2(x: float) -> float:
    return round(float(x or 0) + 1e-9, 2)


async def get_config() -> Dict[str, Any]:
    doc = await db[TAX_CONFIG].find_one({"id": CONFIG_ID})
    if not doc:
        doc = {"id": CONFIG_ID, "pdfo_rate": DEFAULT_PDFO, "vz_rate": DEFAULT_VZ,
               "enabled": True, "jurisdiction": "UA",
               "updated_at": _now()}
        await db[TAX_CONFIG].update_one({"id": CONFIG_ID}, {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    return doc


def compute_withholding(gross: float, *, pdfo_rate: float = DEFAULT_PDFO,
                        vz_rate: float = DEFAULT_VZ, enabled: bool = True,
                        override_rate: Optional[float] = None,
                        exempt: bool = False) -> Dict[str, float]:
    """Pure withholding calculation. Returns gross/pdfo/vz/tax_total/net."""
    gross = _round2(gross)
    if not enabled or exempt or gross <= 0:
        return {"gross": gross, "pdfo": 0.0, "vz": 0.0, "tax_total": 0.0,
                "net": gross, "effective_rate": 0.0}
    if override_rate is not None:
        tax_total = _round2(gross * float(override_rate))
        # represent the override entirely as pdfo for record-keeping
        return {"gross": gross, "pdfo": tax_total, "vz": 0.0,
                "tax_total": tax_total, "net": _round2(gross - tax_total),
                "effective_rate": round(float(override_rate), 4)}
    pdfo = _round2(gross * pdfo_rate)
    vz = _round2(gross * vz_rate)
    tax_total = _round2(pdfo + vz)
    return {"gross": gross, "pdfo": pdfo, "vz": vz, "tax_total": tax_total,
            "net": _round2(gross - tax_total),
            "effective_rate": round(pdfo_rate + vz_rate, 4)}


async def withholding_for_investor(investor_id: str, gross: float,
                                   *, config: Optional[dict] = None) -> Dict[str, float]:
    """Resolve per-investor overrides then compute withholding."""
    cfg = config or await get_config()
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id}) or {}
    override = prof.get("tax_withholding_override")
    exempt = bool(prof.get("tax_exempt"))
    return compute_withholding(
        gross, pdfo_rate=float(cfg.get("pdfo_rate", DEFAULT_PDFO)),
        vz_rate=float(cfg.get("vz_rate", DEFAULT_VZ)),
        enabled=bool(cfg.get("enabled", True)),
        override_rate=(float(override) if override is not None else None),
        exempt=exempt)


async def write_tax_liability(*, amount: float, asset_id: Optional[str],
                              batch_id: Optional[str], actor_id: str,
                              notes: str = "") -> Optional[str]:
    """Append a tax_withheld ledger credit to the platform liability account."""
    if _round2(amount) <= 0:
        return None
    try:
        from lumen_payments import _ledger_append
        le = await _ledger_append(
            entry_type="credit", reason="tax_withheld",
            investor_id=TAX_LIABILITY_ACCOUNT, asset_id=asset_id,
            investment_id=None, payment_request_id=None,
            amount=_round2(amount), currency="UAH", fx_rate=1.0,
            amount_uah=_round2(amount), actor_id=actor_id,
            notes=notes or f"UA withholding (ПДФО+ВЗ) batch={batch_id}")
        if batch_id:
            await db.lumen_ledger_entries.update_one(
                {"id": le}, {"$set": {"payout_batch_id": batch_id,
                                      "tax_liability": True}})
        return le
    except Exception as e:
        logger.warning("write_tax_liability failed: %s", e)
        return None


# ──────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/tax/config")
async def admin_get_tax_config(_=Depends(require_admin)):
    return await get_config()


class TaxConfigIn(BaseModel):
    pdfo_rate: Optional[float] = Field(None, ge=0, le=0.5)
    vz_rate: Optional[float] = Field(None, ge=0, le=0.5)
    enabled: Optional[bool] = None


@router.put("/admin/tax/config")
async def admin_put_tax_config(payload: TaxConfigIn, admin=Depends(require_admin)):
    cfg = await get_config()
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    upd["updated_at"] = _now()
    upd["updated_by"] = admin.get("id")
    await db[TAX_CONFIG].update_one({"id": CONFIG_ID}, {"$set": upd})
    return await get_config()


@router.get("/admin/tax/preview")
async def admin_tax_preview(gross: float, _=Depends(require_admin)):
    cfg = await get_config()
    return compute_withholding(
        gross, pdfo_rate=float(cfg["pdfo_rate"]), vz_rate=float(cfg["vz_rate"]),
        enabled=bool(cfg["enabled"]))


@router.get("/admin/tax/liability")
async def admin_tax_liability(limit: int = 100, _=Depends(require_admin)):
    total = 0.0
    rows = []
    async for e in db.lumen_ledger_entries.find(
            {"reason": "tax_withheld", "investor_id": TAX_LIABILITY_ACCOUNT}).sort("created_at", -1).limit(min(limit, 1000)):
        total += float(e.get("amount_uah") or 0)
        e.pop("_id", None)
        rows.append(e)
    return {"outstanding_liability_uah": _round2(total), "count": len(rows),
            "entries": rows, "account": TAX_LIABILITY_ACCOUNT}


async def ensure_indexes() -> None:
    try:
        await db[TAX_CONFIG].create_index("id", unique=True)
        await get_config()  # materialise defaults
    except Exception as e:
        logger.warning("tax ensure_indexes warning: %s", e)


async def boot() -> None:
    await ensure_indexes()
    cfg = await get_config()
    logger.info("Tax Engine ready (ПДФО=%.1f%% ВЗ=%.1f%% enabled=%s)",
                cfg["pdfo_rate"] * 100, cfg["vz_rate"] * 100, cfg["enabled"])
