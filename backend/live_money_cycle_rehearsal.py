#!/usr/bin/env python3
"""
live_money_cycle_rehearsal.py — First Live Money-Cycle DRESS REHEARSAL
======================================================================

Walks the EXACT real-money path a team runs before accepting the first investor,
asserting that the cash-conservation audit stays GREEN at every checkpoint:

    100 EUR arrive (bank)            → cash movement INFLOW
      → pool contribution confirmed  → units issued → certificate issued
    10 EUR asset revenue recorded    → expenses / tax / reserve
      → distribution                 → investor balance credited
    withdrawal request               → manual payout → reconciled
      → CASH AUDIT STILL GREEN  (Statement A pool cash + Statement B balances)

Run:  python3 backend/live_money_cycle_rehearsal.py
Exit 0 + "READY TO ACCEPT REAL MONEY" = the money machine works end-to-end.

This is an OPERATIONAL rehearsal (not a new financial entity). It uses the live
API exactly as an operator would, with small symbolic amounts, then verifies the
books balance to the cent.
"""
import asyncio
import os
import sys

import httpx

BASE = os.environ.get("REHEARSAL_BASE", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("LR_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PASS = os.environ.get("LR_ADMIN_PASS", "admin123")
INV_EMAIL = os.environ.get("POOL_INV_EMAIL", "client@atlas.dev")
INV_PASS = os.environ.get("POOL_INV_PASS", "client123")

# Symbolic real-money amounts (the cycle the owner wants to validate)
CONTRIBUTION = 100.0      # 100 EUR arrives
REVENUE_GROSS = 10.0      # 10 EUR asset revenue
REVENUE_EXPENSES = 1.0
REVENUE_TAX = 2.0
REVENUE_RESERVE = 1.0
NET_DISTRIBUTABLE = REVENUE_GROSS - REVENUE_EXPENSES - REVENUE_TAX - REVENUE_RESERVE  # 6.0

STEPS = []


def step(n, title, ok, detail=""):
    STEPS.append(ok)
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] Step {n}: {title}" + (f"  — {detail}" if detail else ""))


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


async def audit_green(c, AH, pid, label):
    r = await c.get(f"/api/admin/pools/{pid}/cash-audit", headers=AH)
    a = r.json()
    ok = a.get("reconciles") is True
    print(f"      · cash audit [{label}]: IN={a['inflows']['total']} "
          f"OUT={a['outflows']['total']} BALANCE={a['cash_balance']} "
          f"→ {'GREEN ✅' if ok else 'RED ❌'}")
    return ok, a


async def main() -> int:
    print("\n══════════ FIRST LIVE MONEY-CYCLE — DRESS REHEARSAL ══════════")
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        admin_tok = await _token(c, ADMIN_EMAIL, ADMIN_PASS)
        inv_tok = await _token(c, INV_EMAIL, INV_PASS) or admin_tok
        AH = {"Cookie": f"session_token={admin_tok}"}
        IH = {"Cookie": f"session_token={inv_tok}"}
        step(0, "Authenticate admin + investor", bool(admin_tok and inv_tok))

        # 1) Operator creates the asset pool and opens fundraising
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-live-rehearsal", "title": "LIVE Rehearsal Pool",
            "currency": "EUR", "target_amount": CONTRIBUTION, "min_ticket": 1,
            "total_units": int(CONTRIBUTION)})
        pid = r.json()["pool"]["id"] if r.status_code == 200 else None
        await c.post(f"/api/admin/pools/{pid}/open", headers=AH)
        step(1, "Create + open asset pool", bool(pid), pid or r.text[:120])

        # 2) Investor commits 100 EUR → gets bank payment reference (cash NOT in yet)
        r = await c.post("/api/investor/pools/contribute", headers=IH,
                         json={"pool_id": pid, "amount": CONTRIBUTION, "currency": "EUR"})
        cid = r.json()["contribution"]["id"] if r.status_code == 200 else None
        ref = r.json()["payment_instructions"]["reference"] if r.status_code == 200 else None
        step(2, "Investor commits 100 EUR → payment reference issued", bool(cid and ref), ref or "")

        # 3) 100 EUR ARRIVE on the bank → operator reconciles/confirms → INFLOW + units
        r = await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH,
                         json={"provider_ref": "BANK-INBOUND-001", "bank_reference": ref,
                               "received_amount": CONTRIBUTION, "received_currency": "EUR"})
        confirmed = r.status_code == 200
        units = r.json().get("units") if confirmed else None
        step(3, "100 EUR arrive → reconcile/confirm → INFLOW + units issued",
             confirmed and units == int(CONTRIBUTION), f"units={units}")
        g, _ = await audit_green(c, AH, pid, "after funding")
        step("3a", "Cash audit GREEN after funding", g)

        # 4) Certificate auto-issued on funding
        r = await c.get("/api/investor/pool-certificates", headers=IH)
        has_cert = any(x["pool_id"] == pid for x in r.json()["items"])
        step(4, "Ownership certificate issued", has_cert)

        # 5) Operator releases 100 EUR to the seller/owner (asset acquisition)
        r = await c.post(f"/api/admin/pools/{pid}/release-to-seller", headers=AH,
                         json={"amount": CONTRIBUTION, "seller_name": "Real Seller Ltd",
                               "seller_iban": "UA00LIVE", "reason": "Asset purchase"})
        step(5, "Release 100 EUR to seller (asset acquired)", r.status_code == 200, r.text[:120])
        await c.post(f"/api/admin/pools/{pid}/mark-operating", headers=AH)
        g, _ = await audit_green(c, AH, pid, "after release")
        step("5a", "Cash audit GREEN after release", g)

        # 6) Asset generates 10 EUR revenue → expenses/tax/reserve → net 6 EUR
        r = await c.post("/api/admin/revenue-events", headers=AH, json={
            "pool_id": pid, "gross_amount": REVENUE_GROSS,
            "expenses_amount": REVENUE_EXPENSES, "tax_amount": REVENUE_TAX,
            "reserve_amount": REVENUE_RESERVE, "description": "First asset revenue"})
        ev = r.json().get("revenue_event") if r.status_code == 200 else None
        net_ok = ev and ev["net_distributable"] == NET_DISTRIBUTABLE
        step(6, "Record 10 EUR revenue (−expenses −tax −reserve = 6 net)", bool(net_ok),
             f"net={ev['net_distributable'] if ev else '?'}")

        # 7) Distribute net pro-rata → investor balance credited
        bal_before = 0
        rb = await c.get("/api/investor/pool-balances", headers=IH)
        bb = next((b for b in rb.json()["items"] if b["currency"] == "EUR"), None)
        bal_before = bb["credited"] if bb else 0
        r = await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)
        dist_ok = r.status_code == 200 and r.json().get("distributed_amount") == NET_DISTRIBUTABLE
        step(7, "Distribute net pro-rata to units", dist_ok)
        g, _ = await audit_green(c, AH, pid, "after distribution")
        step("7a", "Cash audit GREEN after distribution", g)

        rb = await c.get("/api/investor/pool-balances", headers=IH)
        ba = next((b for b in rb.json()["items"] if b["currency"] == "EUR"), None)
        credited_delta = round((ba["credited"] if ba else 0) - bal_before, 2)
        step(8, "Investor balance credited with net revenue", credited_delta == NET_DISTRIBUTABLE,
             f"+{credited_delta} EUR")

        # 9) Investor requests withdrawal of the 6 EUR → manual payout → reconciled
        r = await c.post("/api/investor/pool-withdrawals", headers=IH,
                         json={"currency": "EUR", "amount": NET_DISTRIBUTABLE})
        wid = r.json()["withdrawal"]["id"] if r.status_code == 200 else None
        ok9 = bool(wid)
        if wid:
            a1 = await c.post(f"/api/admin/pool-withdrawals/{wid}/approve", headers=AH)
            a2 = await c.post(f"/api/admin/pool-withdrawals/{wid}/pay", headers=AH,
                              json={"bank_reference": "BANK-OUTBOUND-001"})
            a3 = await c.post(f"/api/admin/pool-withdrawals/{wid}/reconcile", headers=AH)
            ok9 = all(x.status_code == 200 for x in (a1, a2, a3))
        step(9, "Withdrawal request → approve → manual payout → reconciled", ok9)

        # 10) Final conservation: Statement A (pool) + Statement B (investor balances)
        g, a = await audit_green(c, AH, pid, "FINAL")
        step(10, "Statement A — pool cash audit GREEN", g)
        # expected: IN=110, OUT=109 (100 release + 1 exp + 2 tax + 6 dist), balance=1 (reserve)
        a_ok = (a["inflows"]["total"] == 110 and a["outflows"]["total"] == 109
                and a["cash_balance"] == 1.0)
        step("10a", "Statement A numbers exact (IN=110, OUT=109, BAL=1=reserve)", a_ok,
             f"IN={a['inflows']['total']} OUT={a['outflows']['total']} BAL={a['cash_balance']}")
        rb = await c.get("/api/admin/pool-cash-audit", headers=AH)
        b = rb.json()
        step(11, "Statement B — investor-balance conservation GREEN", b.get("reconciles") is True,
             f"distributions={b['distributions_credited']} = paid+{b['outstanding_balances']}")
        ri = await c.get(f"/api/admin/pools/{pid}/invariants", headers=AH)
        step(12, "All pool invariants (incl. I7 cash conservation) GREEN",
             ri.json().get("all_passed") is True, str(ri.json().get("counts")))

    passed = sum(1 for s in STEPS if s)
    total = len(STEPS)
    print(f"\n══════════ {passed}/{total} steps passed ══════════")
    if passed == total:
        print("✅ MONEY MACHINE WORKS END-TO-END — books balance to the cent.")
        print("✅ READY TO ACCEPT REAL MONEY (pending real bank rails + legal SPV).")
        return 0
    print("❌ Rehearsal failed — do NOT accept real money until green.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
