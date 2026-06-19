"""
shared/money.py — PUBLIC CURRENCY RULE (display layer).

LUMEN is a USD/USDT product. Everything a user SEES is in dollars.
Internally the financial engine (ledger, pool OS, cash audits, FX) may keep
UAH-denominated values — that is fine and must NOT change (it would break the
financial invariants / DR drill / cash audits). We only convert at the DISPLAY
layer, using a single canonical rate that mirrors the frontend
(`frontend/src/lib/lumenApi.js` → UAH_PER_USD = 41).

There must be NO ₴ / грн / UAH in any user-facing string. Use these helpers.
"""
from __future__ import annotations

# Canonical display FX — keep in sync with frontend UAH_PER_USD.
UAH_PER_USD: float = 41.0


def usd_from_uah(uah_amount) -> float:
    """Convert a legacy UAH-denominated amount to USD for display."""
    try:
        return float(uah_amount or 0) / UAH_PER_USD
    except (TypeError, ValueError):
        return 0.0


def fmt_usd(amount, decimals: int = 0) -> str:
    """Format an amount that is ALREADY in USD as '$1,234'."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0.0
    return "$" + f"{n:,.{decimals}f}"


def fmt_uah_as_usd(uah_amount, decimals: int = 0) -> str:
    """Format a UAH-denominated amount as a USD display string '$1,234'."""
    return fmt_usd(usd_from_uah(uah_amount), decimals=decimals)


def fmt_usdt(amount, decimals: int = 0) -> str:
    """Format an already-USD amount as 'X,XXX USDT' (no leading $)."""
    try:
        n = float(amount or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"{n:,.{decimals}f} USDT"


def fmt_uah_as_usdt(uah_amount, decimals: int = 0) -> str:
    """Format a UAH-denominated amount as a USDT display string 'X,XXX USDT'."""
    return fmt_usdt(usd_from_uah(uah_amount), decimals=decimals)
