"""
LUMEN — Secondary Market Stress / Concurrency Contract Harness (E1)
===================================================================

12th harness. The single largest *technical* risk before opening the secondary
market: settlement races. This harness fires many concurrent buy-now
settlements at ONE listing with deliberately over-subscribed demand and asserts
the core money invariants hold.

It tests the real engine in-process: it seeds a listing + buyers, then calls
``lumen_secondary._settle_trade`` for every trade simultaneously via
``asyncio.gather`` (true concurrency on one event loop), exactly as the FastAPI
worker would under load.

  E1.1  NO OVERSELL — settled units ≤ listing units; filled_units_uah ≤ units_uah.
  E1.2  NO DOUBLE TRANSFER — exactly one share_transfer per settled trade.
  E1.3  LEDGER BALANCED — Σ(credits) − Σ(debits) over the trade ledger == 0.
  E1.4  CONSISTENT FILL — filled_units_uah == settled_count × unit_size; status
        becomes 'filled' when fully subscribed.
  E1.5  LOSERS REJECTED CLEANLY — over-demand trades end 'failed' (not settled,
        no transfer, no ledger side-effects).

Run:  cd /app/backend && python secondary_stress_contract.py
"""
from __future__ import annotations

import os
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("secondary-stress")

# In-process import of the real engine.
import lumen_secondary as sec
from lumen_api import db

ASSET = "asset-e1-stress"
SELLER = "e1-seller"
LISTING_UNITS = 100000.0     # available
UNIT_SIZE = 5000.0           # per buyer
N_BUYERS = 40                # demand = 200000 → only 20 can win
EXPECTED_WINNERS = int(LISTING_UNITS // UNIT_SIZE)  # 20


class Report:
    def __init__(self):
        self.items, self.fail = [], 0

    def add(self, req, check, status, detail=""):
        self.items.append({"req": req, "check": check, "status": status, "detail": detail})
        log.info(f"[{status.upper()}] {req} :: {check} {('— ' + detail) if detail else ''}")
        if status == "fail":
            self.fail += 1

    def summary(self):
        return {"total": len(self.items),
                "passed": sum(1 for i in self.items if i["status"] == "pass"),
                "failed": self.fail,
                "verdict": "PASS" if self.fail == 0 else "FAIL",
                "items": self.items, "generated_at": datetime.now(timezone.utc).isoformat()}


report = Report()


def _now():
    return datetime.now(timezone.utc)


async def cleanup():
    await db.lumen_secondary_trades.delete_many({"asset_id": ASSET})
    await db.lumen_share_transfers.delete_many({"asset_id": ASSET})
    await db.lumen_secondary_listings.delete_many({"asset_id": ASSET})
    await db.lumen_ownerships.delete_many({"asset_id": ASSET})
    await db.lumen_ledger_entries.delete_many({"asset_id": ASSET})
    await db.lumen_wallets.delete_many({"investor_id": {"$regex": "^e1-buyer-"}})
    await db.lumen_wallets.delete_many({"investor_id": SELLER})


async def seed():
    await cleanup()
    # seller base ownership so compute_ownership_uah has something to draw from
    await db.lumen_ownerships.insert_one({
        "id": f"own-{uuid.uuid4().hex[:10]}", "investor_id": SELLER,
        "asset_id": ASSET, "amount_uah": LISTING_UNITS, "amount": LISTING_UNITS,
        "units": LISTING_UNITS, "status": "active", "created_at": _now(), "updated_at": _now()})
    listing_id = f"lst-{uuid.uuid4().hex[:10]}"
    await db.lumen_secondary_listings.insert_one({
        "id": listing_id, "asset_id": ASSET, "seller_id": SELLER,
        "units_uah": LISTING_UNITS, "filled_units_uah": 0.0,
        "price_per_unit": 1.0, "status": "active",
        "created_at": _now(), "updated_at": _now()})
    trades = []
    for i in range(N_BUYERS):
        buyer = f"e1-buyer-{i:03d}"
        # fund buyer wallet directly (affordability check reads settled_balance)
        await db.lumen_wallets.update_one(
            {"investor_id": buyer},
            {"$set": {"investor_id": buyer, "currency": "UAH",
                      "settled_balance": UNIT_SIZE * 2, "available_balance": UNIT_SIZE * 2,
                      "updated_at": _now()}}, upsert=True)
        tid = f"trd-{uuid.uuid4().hex[:10]}"
        trade = {"id": tid, "listing_id": listing_id, "asset_id": ASSET,
                 "buyer_id": buyer, "seller_id": SELLER,
                 "units_uah": UNIT_SIZE, "gross_uah": UNIT_SIZE, "fee_uah": 0.0,
                 "status": "pending", "created_at": _now()}
        await db.lumen_secondary_trades.insert_one(dict(trade))
        trades.append(trade)
    return listing_id, trades


async def _settle_one(trade):
    try:
        await sec._settle_trade(trade, actor={"id": "e1-stress"})
        return ("ok", trade["id"])
    except Exception as e:
        # expected for losers (409 oversell / 402 funds)
        code = getattr(e, "status_code", None)
        return ("fail", code)


async def run():
    listing_id, trades = await seed()
    log.info(f"Seeded listing {listing_id}: {LISTING_UNITS} units, {N_BUYERS} buyers "
             f"× {UNIT_SIZE} = {N_BUYERS*UNIT_SIZE} demand; expecting {EXPECTED_WINNERS} winners")

    # FIRE ALL SETTLEMENTS CONCURRENTLY
    results = await asyncio.gather(*[_settle_one(t) for t in trades])
    ok_count = sum(1 for r in results if r[0] == "ok")

    listing = await db.lumen_secondary_listings.find_one({"id": listing_id})
    settled = await db.lumen_secondary_trades.count_documents({"asset_id": ASSET, "status": "settled"})
    failed = await db.lumen_secondary_trades.count_documents({"asset_id": ASSET, "status": "failed"})
    transfers = await db.lumen_share_transfers.count_documents({"asset_id": ASSET})
    filled = float(listing.get("filled_units_uah") or 0)

    # E1.1 — NO OVERSELL
    settled_units = settled * UNIT_SIZE
    no_oversell = settled_units <= LISTING_UNITS + 0.5 and filled <= LISTING_UNITS + 0.5
    report.add("E1.1", "NO OVERSELL (settled units ≤ available; filled ≤ units)",
               "pass" if no_oversell else "fail",
               f"settled={settled} units={settled_units} filled={filled} cap={LISTING_UNITS}")

    # E1.2 — NO DOUBLE TRANSFER (one transfer per settled trade)
    per_trade = await db.lumen_share_transfers.aggregate([
        {"$match": {"asset_id": ASSET}},
        {"$group": {"_id": "$trade_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}]).to_list(100)
    report.add("E1.2", "NO DOUBLE TRANSFER (exactly 1 transfer per settled trade)",
               "pass" if (transfers == settled and not per_trade) else "fail",
               f"transfers={transfers} settled={settled} dupes={len(per_trade)}")

    # E1.3 — LEDGER BALANCED
    credit = 0.0
    debit = 0.0
    async for e in db.lumen_ledger_entries.find(
            {"asset_id": ASSET, "reason": {"$in": ["secondary_purchase", "secondary_sale", "platform_fee"]}}):
        amt = float(e.get("amount_uah") or 0)
        if e.get("entry_type") == "credit":
            credit += amt
        else:
            debit += amt
    balance = round(credit - debit, 2)
    report.add("E1.3", "LEDGER BALANCED (Σcredits − Σdebits == 0)",
               "pass" if abs(balance) < 0.5 else "fail",
               f"credits={round(credit,2)} debits={round(debit,2)} net={balance}")

    # E1.4 — CONSISTENT FILL
    consistent = abs(filled - settled_units) < 0.5
    status_ok = listing.get("status") == ("filled" if settled_units >= LISTING_UNITS - 0.5 else "partially_filled")
    report.add("E1.4", "CONSISTENT FILL (filled == settled×size; status correct)",
               "pass" if (consistent and status_ok) else "fail",
               f"filled={filled} expected={settled_units} status={listing.get('status')}")

    # E1.5 — LOSERS REJECTED CLEANLY
    losers_ok = (settled + failed == N_BUYERS) and (settled == EXPECTED_WINNERS)
    report.add("E1.5", "LOSERS REJECTED CLEANLY (settled+failed == total; winners == capacity)",
               "pass" if losers_ok else "fail",
               f"settled={settled} failed={failed} total={N_BUYERS} expected_winners={EXPECTED_WINNERS}")

    await cleanup()


async def main():
    try:
        await run()
    except Exception as e:
        report.add("Harness", "execution", "fail", str(e))
        await cleanup()
    s = report.summary()
    print("\n" + "=" * 74)
    print(f"SECONDARY MARKET STRESS CONTRACT — {s['verdict']} "
          f"(pass={s['passed']} fail={s['failed']} / total={s['total']})")
    print("=" * 74)
    try:
        os.makedirs("/app/test_reports", exist_ok=True)
        with open("/app/test_reports/secondary_stress_contract.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"write report failed: {e}")
    return 0 if s["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
