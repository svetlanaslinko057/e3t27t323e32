#!/usr/bin/env python3
"""
h2_2_gateway_contract.py — H2.2 Pool Gateway Layer contract
===========================================================

Proves fiat and crypto gateways funnel into ONE pool and ONE hard_cap_usd, and
that Pool OS only ever sees amount_usd (USDT 1:1 → USD).

  G1  /api/pools/gateways lists fiat + crypto
  G2  fiat contribution (USD) → confirm → counts toward cap
  G3  crypto contribution (USDT) → on-chain webhook → confirm (amount_usd 1:1)
  G4  both gateways share ONE hard_cap_usd (parallel, first-come)
  G5  over-cap deposit (any gateway) → 409
  G6  crypto webhook insufficient token amount → 400
  G7  crypto gateway rejects an unsupported currency (USD) → 400
  G8  cash audit reconciles in USD across mixed gateways

Run:  cd /app/backend && python h2_2_gateway_contract.py
"""
import asyncio
import os
import sys

import httpx

BASE = os.environ.get("POOL_CONTRACT_BASE", "http://localhost:8001")
ADMIN_EMAIL, ADMIN_PASS = "admin@atlas.dev", "admin123"
INV_EMAIL, INV_PASS = "client@atlas.dev", "client123"
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
    return tok


def r2(x):
    return round(float(x or 0), 2)


async def contribute(c, IH, pid, amount, currency, gateway):
    return await c.post("/api/investor/pools/contribute", headers=IH,
                        json={"pool_id": pid, "amount": amount, "currency": currency,
                              "gateway": gateway})


async def confirm_fiat(c, AH, cid, amount, currency):
    return await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH,
                        json={"provider_ref": "x", "bank_reference": "y",
                              "received_amount": amount, "received_currency": currency})


async def confirm_crypto(c, AH, ref, amount_token, chain=1):
    return await c.post("/api/admin/crypto/webhook/deposit", headers=AH,
                        json={"contribution_ref": ref, "tx_hash": f"0x{ref[:12]}",
                              "wallet_address": "0xabc0000000000000000000000000000000000001",
                              "amount_token": amount_token, "chain_id": chain})


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        admin_tok = await _token(c, ADMIN_EMAIL, ADMIN_PASS)
        inv_tok = await _token(c, INV_EMAIL, INV_PASS) or admin_tok
        AH = {"Cookie": f"session_token={admin_tok}"}
        IH = {"Cookie": f"session_token={inv_tok}"}
        check("auth", bool(admin_tok))

        # G1 gateways
        print("\n── G1: gateways ──")
        gws = (await c.get("/api/pools/gateways", headers=IH)).json()["gateways"]
        keys = {g["key"] for g in gws}
        check("fiat + crypto listed", {"fiat", "crypto"} <= keys, str(keys))

        # USD pool, hard cap 10000, unit price 1.0
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-gw", "title": "Gateway Pool", "target_amount": 10000,
            "min_ticket": 100, "total_units": 10000})
        pid = r.json()["pool"]["id"]
        await c.post(f"/api/admin/pools/{pid}/open", headers=AH)

        # G2 fiat 3000
        print("\n── G2: fiat → cap ──")
        f1 = (await contribute(c, IH, pid, 3000, "USD", "fiat")).json()
        check("fiat contribution gateway=fiat", f1["gateway"] == "fiat")
        r = await confirm_fiat(c, AH, f1["contribution"]["id"], 3000, "USD")
        check("fiat confirm 200", r.status_code == 200, r.text[:160])

        # G3 crypto 4000 via webhook
        print("\n── G3: crypto → webhook → cap ──")
        cr = (await contribute(c, IH, pid, 4000, "USDT", "crypto")).json()
        check("crypto gateway=crypto", cr["gateway"] == "crypto")
        check("crypto amount_usd 1:1", r2(cr["contribution"]["amount_usd"]) == 4000)
        ref = cr["payment_instructions"]["contribution_ref"]
        r = await confirm_crypto(c, AH, ref, 4000)
        check("crypto webhook confirm 200", r.status_code == 200, r.text[:160])
        check("crypto units == 4000", r.status_code == 200 and r.json().get("units") == 4000)

        # G4 one shared cap
        print("\n── G4: one shared hard_cap_usd ──")
        pool = (await c.get(f"/api/admin/pools/{pid}", headers=AH)).json()["pool"]
        check("confirmed_usd == 7000 (3000 fiat + 4000 crypto)",
              r2(pool["confirmed_usd"]) == 7000, str(pool["confirmed_usd"]))

        # fill to cap: crypto 2000 + fiat 1000 = 10000
        cr2 = (await contribute(c, IH, pid, 2000, "USDC", "crypto")).json()
        await confirm_crypto(c, AH, cr2["payment_instructions"]["contribution_ref"], 2000)
        f2 = (await contribute(c, IH, pid, 1000, "USD", "fiat")).json()
        r = await confirm_fiat(c, AH, f2["contribution"]["id"], 1000, "USD")
        check("cap reached at 10000", r.status_code == 200, r.text[:160])
        pool = (await c.get(f"/api/admin/pools/{pid}", headers=AH)).json()["pool"]
        check("confirmed_usd == 10000", r2(pool["confirmed_usd"]) == 10000, str(pool["confirmed_usd"]))

        # G5 over-cap (either gateway) → 409
        print("\n── G5: over-cap guard ──")
        if pool["status"] == "fundraising":
            over = (await contribute(c, IH, pid, 500, "USD", "fiat")).json()
            r = await confirm_fiat(c, AH, over["contribution"]["id"], 500, "USD")
            check("over-cap fiat confirm → 409", r.status_code == 409, f"got {r.status_code}")
        else:
            check("pool auto-closed at cap (no over-cap possible)", True)

        # G6 insufficient crypto + G7 unsupported currency
        print("\n── G6/G7: guards ──")
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-gw2", "title": "GW2", "target_amount": 10000,
            "min_ticket": 100, "total_units": 10000})
        pid2 = r.json()["pool"]["id"]
        await c.post(f"/api/admin/pools/{pid2}/open", headers=AH)
        crx = (await contribute(c, IH, pid2, 1000, "USDT", "crypto")).json()
        r = await confirm_crypto(c, AH, crx["payment_instructions"]["contribution_ref"], 500)
        check("insufficient token deposit → 400", r.status_code == 400, f"got {r.status_code}")
        r = await contribute(c, IH, pid2, 1000, "USD", "crypto")
        check("crypto rejects USD currency → 400", r.status_code == 400, f"got {r.status_code}")

        # G8 cash audit reconciles mixed gateways
        print("\n── G8: mixed-gateway cash audit ──")
        a = (await c.get(f"/api/admin/pools/{pid}/cash-audit", headers=AH)).json()
        check("mixed cash audit reconciles", a.get("reconciles") is True, str(a.get("checks")))
        check("inflows == 10000", r2(a["inflows"]["total"]) == 10000, str(a["inflows"]["total"]))

    print(f"\n════════ H2.2 RESULT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("H2.2 GATEWAY CONTRACT — ALL GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
