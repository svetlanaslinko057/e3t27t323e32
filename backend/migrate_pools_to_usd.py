#!/usr/bin/env python3
"""
migrate_pools_to_usd.py — H2.1 legacy → USD base-currency migration
===================================================================

Converts any legacy single-currency (e.g. EUR) Pool-OS data to the USD base.
Because the demo is effectively single-currency, every money field is scaled by
the SAME FX factor, so the cash-conservation audits stay reconciled by
construction (everything scales together).

What it converts (for docs whose `currency` == FROM_CURRENCY):
  pools · contributions · allocations · ledger · cash_movements ·
  revenue_events · distributions · withdrawals · balances

Idempotent: only touches docs still in FROM_CURRENCY. Read the resulting
verdict from stdout / return value.

Run:  cd /app/backend && python migrate_pools_to_usd.py [FROM_CURRENCY=EUR]
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _now():
    return datetime.now(timezone.utc)


def _r2(x):
    return round(float(x or 0), 2)


async def migrate(db, from_currency: str = "EUR") -> dict:
    from lumen_pool_fx import convert_to_usd
    fc = from_currency.upper()
    # full-precision factor: 1 unit FROM = (1/rate) USD
    conv = await convert_to_usd(1.0, fc)
    rate_to_usd = float(conv["fx_rate_to_usd"])  # FROM units per USD
    source = conv["fx_source"]
    if fc == "USD" or fc in {"USDT", "USDC"} or not rate_to_usd:
        factor = 1.0
    else:
        factor = 1.0 / rate_to_usd               # USD per 1 FROM unit (full precision)

    report = {"from_currency": fc, "usd_per_unit": round(factor, 8),
              "fx_rate_to_usd": rate_to_usd, "fx_source": source, "collections": {}}

    def scale(doc, fields):
        out = {}
        for f in fields:
            if doc.get(f) is not None:
                out[f] = _r2(float(doc[f]) * factor)
        return out

    # ── pools ──
    n = 0
    async for p in db["lumen_pools"].find({"currency": fc}):
        s = scale(p, ["target_amount", "confirmed_amount", "available_cash",
                      "released_amount", "refunded_amount"])
        up = round(float(p.get("unit_price") or 0) * factor, 8)
        s.update({
            "currency": "USD", "base_currency": "USD", "unit_price": up,
            "hard_cap_usd": s.get("target_amount", 0.0),
            "target_amount_usd": s.get("target_amount", 0.0),
            "confirmed_usd": s.get("confirmed_amount", 0.0),
            "raised_usd": s.get("confirmed_amount", 0.0),
            "available_cash_usd": s.get("available_cash", 0.0),
            "unit_price_usd": up,
            "migrated_from_currency": fc, "migrated_fx_rate": rate_to_usd,
            "updated_at": _now(),
        })
        await db["lumen_pools"].update_one({"id": p["id"]}, {"$set": s})
        n += 1
    report["collections"]["pools"] = n

    # ── contributions ──
    n = 0
    async for c in db["lumen_pool_contributions"].find({"currency": fc}):
        new_amt = _r2(float(c.get("amount") or 0) * factor)
        await db["lumen_pool_contributions"].update_one({"id": c["id"]}, {"$set": {
            "amount": new_amt, "currency": "USD",
            "original_amount": _r2(c.get("amount")),
            "original_currency": fc, "fx_rate_to_usd": rate_to_usd,
            "fx_source": source, "amount_usd": new_amt,
            "gateway": c.get("gateway", "fiat"), "updated_at": _now(),
        }})
        n += 1
    report["collections"]["contributions"] = n

    # ── simple pool-scoped money collections ──
    async def simple(coll, fields):
        cnt = 0
        async for d in db[coll].find({"currency": fc}):
            s = scale(d, fields)
            s["currency"] = "USD"
            s["updated_at"] = _now()
            await db[coll].update_one({"id": d["id"]}, {"$set": s})
            cnt += 1
        return cnt

    report["collections"]["allocations"] = await simple("lumen_pool_allocations", ["amount"])
    report["collections"]["ledger"] = await simple("lumen_pool_ledger", ["amount"])
    report["collections"]["cash_movements"] = await simple("lumen_pool_cash_movements", ["amount"])
    report["collections"]["withdrawals"] = await simple("lumen_pool_withdrawals", ["amount"])
    report["collections"]["distributions"] = await simple(
        "lumen_revenue_distributions", ["gross_amount"])

    # ── revenue events (add USD fields) ──
    n = 0
    async for e in db["lumen_revenue_events"].find({"currency": fc}):
        s = scale(e, ["gross_amount", "expenses_amount", "reserve_amount",
                      "tax_amount", "net_distributable"])
        s.update({
            "currency": "USD",
            "gross_usd": s.get("gross_amount", 0.0),
            "expenses_usd": s.get("expenses_amount", 0.0),
            "reserve_usd": s.get("reserve_amount", 0.0),
            "tax_usd": s.get("tax_amount", 0.0),
            "net_distributable_usd": s.get("net_distributable", 0.0),
            "original_currency": fc, "fx_rate_to_usd": rate_to_usd,
            "updated_at": _now(),
        })
        await db["lumen_revenue_events"].update_one({"id": e["id"]}, {"$set": s})
        n += 1
    report["collections"]["revenue_events"] = n

    # ── balances are DERIVED: delete stale FROM-currency rows and recompute USD
    #    from the (now-USD) distributions + withdrawals (avoids unique-index clash).
    affected = set()
    async for d in db["lumen_revenue_distributions"].find({"currency": "USD"}, {"investor_id": 1}):
        if d.get("investor_id"):
            affected.add(d["investor_id"])
    async for w in db["lumen_pool_withdrawals"].find({"currency": "USD"}, {"investor_id": 1}):
        if w.get("investor_id"):
            affected.add(w["investor_id"])
    await db["lumen_pool_balances"].delete_many({"currency": fc})
    import lumen_pool_os as _pos
    _orig_db = _pos.db
    _pos.db = db
    try:
        for iid in affected:
            await _pos.recompute_pool_balance(iid, "USD")
    finally:
        _pos.db = _orig_db
    report["collections"]["balances"] = len(affected)

    report["total_docs"] = sum(report["collections"].values())
    return report


async def _main() -> int:
    fc = (sys.argv[1] if len(sys.argv) > 1 else "EUR").upper()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    rep = await migrate(db, fc)
    print(f"USD migration ({fc} → USD): {rep['total_docs']} docs converted "
          f"@ {rep['usd_per_unit']} USD/{fc}")
    for k, v in rep["collections"].items():
        if v:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
