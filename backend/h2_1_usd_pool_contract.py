#!/usr/bin/env python3
"""
h2_1_usd_pool_contract.py — H2.1 USD Base Currency contract harness
===================================================================

Proves the USD-core migration end-to-end against the live API:

  C1  Pool created with base_currency = USD, hard_cap_usd set
  C2  UAH contribution → USD snapshot (amount_usd = original / rate)
  C3  EUR contribution → USD snapshot
  C4  USD contribution → USD (1:1)
  C5  USDT contribution → USD (1:1 stablecoin)
  C6  units computed from USD only (amount_usd / unit_price_usd)
  C7  unified hard_cap_usd guard (over-cap confirm → 409)
  C8  Statement-A cash audit reconciles in USD; inflows == Σ amount_usd
  C9  revenue + distribution run in USD
  C10 legacy EUR demo pool migrated → USD (cash audit still reconciles)

Run:  cd /app/backend && python h2_1_usd_pool_contract.py
Exit 0 = all pass.
"""
import asyncio
import os
import sys

import httpx

BASE = os.environ.get("POOL_CONTRACT_BASE", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("LR_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PASS = os.environ.get("LR_ADMIN_PASS", "admin123")
INV_EMAIL = os.environ.get("POOL_INV_EMAIL", "client@atlas.dev")
INV_PASS = os.environ.get("POOL_INV_PASS", "client123")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


async def _token(c, email, password):
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        return None
    tok = r.cookies.get("session_token")
    if not tok:
        for sc in r.headers.get_list("set-cookie"):
            if sc.startswith("session_token="):
                tok = sc.split("=", 1)[1].split(";", 1)[0]
                break
    return tok


def r2(x):
    return round(float(x or 0), 2)


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        admin_tok = await _token(c, ADMIN_EMAIL, ADMIN_PASS)
        check("auth admin", bool(admin_tok))
        inv_tok = await _token(c, INV_EMAIL, INV_PASS) or admin_tok
        AH = {"Cookie": f"session_token={admin_tok}"}
        IH = {"Cookie": f"session_token={inv_tok}"}

        # Effective FX rates (currency units per USD)
        rates = (await c.get("/api/admin/pool-fx/rates", headers=AH)).json()["effective"]
        uah_rate = rates["UAH"]["rate_per_usd"]
        eur_rate = rates["EUR"]["rate_per_usd"]
        print(f"  [info] FX: UAH {uah_rate}/USD · EUR {eur_rate}/USD")

        # ── C1: create USD pool (unit price 1.0 USD) ──
        print("\n── C1: USD pool ──")
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-usd-core", "title": "USD Core Pool",
            "target_amount": 100000, "min_ticket": 100, "total_units": 100000})
        check("create pool 200", r.status_code == 200, r.text[:200])
        pool = r.json()["pool"]
        pid = pool["id"]
        check("base_currency == USD", pool.get("base_currency") == "USD", str(pool.get("base_currency")))
        check("hard_cap_usd == 100000", r2(pool.get("hard_cap_usd")) == 100000, str(pool.get("hard_cap_usd")))
        check("unit_price_usd == 1.0", abs(float(pool.get("unit_price_usd")) - 1.0) < 1e-9, str(pool.get("unit_price_usd")))
        await c.post(f"/api/admin/pools/{pid}/open", headers=AH)

        # ── C2–C5: multi-currency contributions → USD (via gateways) ──
        print("\n── C2–C5: gateways → USD ──")
        cases = [
            ("UAH", 100000, r2(100000 / uah_rate), "fiat"),
            ("EUR", 1000, r2(1000 / eur_rate), "fiat"),
            ("USD", 3000, 3000.0, "fiat"),
            ("USDT", 5000, 5000.0, "crypto"),
        ]
        contribs = []
        for ccy, orig, exp_usd, gw in cases:
            r = await c.post("/api/investor/pools/contribute", headers=IH,
                             json={"pool_id": pid, "amount": orig, "currency": ccy, "gateway": gw})
            ok = r.status_code == 200
            check(f"{ccy} contribute 200", ok, r.text[:200])
            if ok:
                body = r.json()
                amt_usd = r2(body["contribution"]["amount_usd"])
                check(f"{ccy} {orig} → {exp_usd} USD", abs(amt_usd - exp_usd) <= 0.02,
                      f"got {amt_usd} expected {exp_usd}")
                check(f"{ccy} original preserved",
                      body["contribution"]["original_currency"] == ccy
                      and r2(body["contribution"]["original_amount"]) == r2(orig))
                contribs.append((body["contribution"]["id"], ccy, orig, amt_usd, gw))

        # ── confirm all (fiat: received in original currency; crypto: webhook) + C6 units ──
        print("\n── confirm + C6 units from USD ──")
        total_usd = 0.0
        for cid, ccy, orig, amt_usd, gw in contribs:
            if gw == "crypto":
                r = await c.post("/api/admin/crypto/webhook/deposit", headers=AH,
                                 json={"contribution_ref": cid, "tx_hash": f"0x{cid[:10]}",
                                       "wallet_address": "0xabc0000000000000000000000000000000000009",
                                       "amount_token": orig, "chain_id": 1})
            else:
                r = await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH,
                                 json={"provider_ref": f"p-{cid}", "bank_reference": f"b-{cid}",
                                       "received_amount": orig, "received_currency": ccy})
            check(f"confirm {ccy} 200", r.status_code == 200, r.text[:200])
            if r.status_code == 200:
                units = r.json()["units"]
                check(f"{ccy} units == round(USD)", units == int(round(amt_usd)),
                      f"units={units} usd={amt_usd}")
                total_usd += amt_usd

        r = await c.get(f"/api/admin/pools/{pid}", headers=AH)
        pool = r.json()["pool"]
        check("confirmed_usd == Σ contributions",
              abs(r2(pool.get("confirmed_usd")) - r2(total_usd)) <= 0.05,
              f"{pool.get('confirmed_usd')} vs {r2(total_usd)}")

        # ── C8: cash audit USD reconciles ──
        print("\n── C8: cash audit USD ──")
        a = (await c.get(f"/api/admin/pools/{pid}/cash-audit", headers=AH)).json()
        check("cash audit reconciles", a.get("reconciles") is True, str(a.get("checks")))
        check("inflows == Σ amount_usd", abs(r2(a["inflows"]["total"]) - r2(total_usd)) <= 0.05,
              f"{a['inflows']['total']} vs {r2(total_usd)}")

        # ── C9: revenue + distribution in USD ──
        print("\n── C9: revenue + distribution USD ──")
        await c.post(f"/api/admin/pools/{pid}/mark-operating", headers=AH)
        r = await c.post("/api/admin/revenue-events", headers=AH,
                         json={"pool_id": pid, "gross_amount": 1000, "expenses_amount": 100,
                               "description": "USD rent"})
        check("revenue 200", r.status_code == 200, r.text[:200])
        ev = r.json()["revenue_event"]
        check("net_distributable_usd == 900", r2(ev.get("net_distributable_usd")) == 900,
              str(ev.get("net_distributable_usd")))
        r = await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)
        check("distribute 200 (900 USD)", r.status_code == 200
              and r2(r.json().get("distributed_amount")) == 900, r.text[:160])

        # ── C7: hard_cap_usd guard ──
        print("\n── C7: hard_cap_usd guard ──")
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-cap", "title": "Cap Pool", "target_amount": 5000,
            "min_ticket": 100, "total_units": 5000})
        cap_pid = r.json()["pool"]["id"]
        await c.post(f"/api/admin/pools/{cap_pid}/open", headers=AH)
        c1 = (await c.post("/api/investor/pools/contribute", headers=IH,
              json={"pool_id": cap_pid, "amount": 3000, "currency": "USD"})).json()["contribution"]["id"]
        c2 = (await c.post("/api/investor/pools/contribute", headers=IH,
              json={"pool_id": cap_pid, "amount": 3000, "currency": "USD"})).json()["contribution"]["id"]
        r = await c.post(f"/api/admin/pool-contributions/{c1}/confirm", headers=AH,
                         json={"provider_ref": "x", "bank_reference": "y",
                               "received_amount": 3000, "received_currency": "USD"})
        check("first 3000 confirm 200", r.status_code == 200, r.text[:160])
        r = await c.post(f"/api/admin/pool-contributions/{c2}/confirm", headers=AH,
                         json={"provider_ref": "x", "bank_reference": "y",
                               "received_amount": 3000, "received_currency": "USD"})
        check("over-cap confirm → 409", r.status_code == 409, f"got {r.status_code}")

        # ── C10: legacy EUR pool migrated → USD ──
        print("\n── C10: legacy EUR migration → USD ──")
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-legacy-eur", "title": "Legacy EUR Pool", "currency": "EUR",
            "target_amount": 10000, "min_ticket": 100, "total_units": 10000})
        eur_pid = r.json()["pool"]["id"]
        await c.post(f"/api/admin/pools/{eur_pid}/open", headers=AH)
        ec = (await c.post("/api/investor/pools/contribute", headers=IH,
              json={"pool_id": eur_pid, "amount": 2000, "currency": "EUR"})).json()["contribution"]["id"]
        await c.post(f"/api/admin/pool-contributions/{ec}/confirm", headers=AH,
                     json={"provider_ref": "x", "bank_reference": "y",
                           "received_amount": 2000, "received_currency": "EUR"})
        # run migration in-process against the live DB
        from motor.motor_asyncio import AsyncIOMotorClient
        from migrate_pools_to_usd import migrate
        mdb = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        rep = await migrate(mdb, "EUR")
        check("migration converted docs", rep["total_docs"] >= 2, str(rep["collections"]))
        r = await c.get(f"/api/admin/pools/{eur_pid}", headers=AH)
        mp = r.json()["pool"]
        check("legacy pool now USD", mp.get("currency") == "USD" and mp.get("base_currency") == "USD",
              str(mp.get("currency")))
        expected_usd = r2(2000 / eur_rate)
        check("legacy confirmed scaled to USD",
              abs(r2(mp.get("confirmed_usd")) - expected_usd) <= 0.5,
              f"{mp.get('confirmed_usd')} vs ~{expected_usd}")
        a2 = (await c.get(f"/api/admin/pools/{eur_pid}/cash-audit", headers=AH)).json()
        check("migrated pool cash audit reconciles", a2.get("reconciles") is True, str(a2.get("checks")))

    print(f"\n════════ H2.1 RESULT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("H2.1 USD POOL CONTRACT — ALL GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
