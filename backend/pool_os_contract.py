#!/usr/bin/env python3
"""
pool_os_contract.py — Contract harness for LUMEN Capital Pool OS
================================================================

Exercises the full asset-pool lifecycle against the live API and asserts the
hard invariants (I1–I7):

  create pool → open → 3 contributions → confirm all → pool funded + units
  → certificates issued → release to seller → revenue event → pro-rata distribute
  → investor balances → withdrawal request → approve → pay → reconcile
  + oversell / error-path guards + /admin/pools/{id}/invariants all green.

Run:  python3 backend/pool_os_contract.py
Exit 0 = all pass.
"""
import asyncio
import os
import sys

import httpx

BASE = os.environ.get("POOL_CONTRACT_BASE", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("LR_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PASS = os.environ.get("LR_ADMIN_PASS", "admin123")
# A non-admin investor seed (client@atlas.dev exists per seed_lumen_users)
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


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        admin_tok = await _token(c, ADMIN_EMAIL, ADMIN_PASS)
        check("auth admin login", bool(admin_tok))
        inv_tok = await _token(c, INV_EMAIL, INV_PASS)
        if not inv_tok:
            # fall back to admin acting as investor (endpoints allow any authed user)
            print("  [info] investor seed login failed; using admin as investor")
            inv_tok = admin_tok
        AH = {"Cookie": f"session_token={admin_tok}"}
        IH = {"Cookie": f"session_token={inv_tok}"}

        print("\n── Auth gate ──")
        r = await c.get("/api/admin/pools")
        check("401 without auth", r.status_code == 401, f"got {r.status_code}")

        print("\n── Create + open pool ──")
        r = await c.post("/api/admin/pools", headers=AH, json={
            "asset_id": "asset-contract-pool", "title": "Contract Test Pool",
            "currency": "EUR", "target_amount": 100000, "min_ticket": 1000,
            "total_units": 100000})
        check("create pool 200", r.status_code == 200, r.text[:200])
        pool = r.json()["pool"]
        check("unit_price = 1.0", abs(pool["unit_price"] - 1.0) < 1e-9, str(pool["unit_price"]))
        pid = pool["id"]
        r = await c.post(f"/api/admin/pools/{pid}/open", headers=AH)
        check("open pool 200", r.status_code == 200)

        print("\n── Contributions (investor) ──")
        amounts = [10000, 20000, 30000, 40000]
        cids = []
        for amt in amounts:
            r = await c.post("/api/investor/pools/contribute", headers=IH,
                             json={"pool_id": pid, "amount": amt, "currency": "EUR"})
            check(f"contribute {amt} 200", r.status_code == 200, r.text[:160])
            if r.status_code == 200:
                body = r.json()
                cids.append(body["contribution"]["id"])
                check(f"contribute {amt} has reference",
                      bool(body["payment_instructions"]["reference"]))
        # extra contribution for the amount-mismatch guard (created while fundraising)
        r = await c.post("/api/investor/pools/contribute", headers=IH,
                         json={"pool_id": pid, "amount": 5000, "currency": "EUR"})
        mm_cid = r.json()["contribution"]["id"]
        # min ticket guard
        r = await c.post("/api/investor/pools/contribute", headers=IH,
                         json={"pool_id": pid, "amount": 500, "currency": "EUR"})
        check("min-ticket rejected 400", r.status_code == 400, f"got {r.status_code}")

        print("\n── Confirm contributions (reconciliation) ──")
        for cid, amt in zip(cids, amounts):
            r = await c.post(f"/api/admin/pool-contributions/{cid}/confirm", headers=AH,
                             json={"provider_ref": f"prov-{cid}", "bank_reference": f"ref-{cid}",
                                   "received_amount": amt, "received_currency": "EUR"})
            check(f"confirm {amt} 200", r.status_code == 200, r.text[:160])
        # double-confirm guard
        r = await c.post(f"/api/admin/pool-contributions/{cids[0]}/confirm", headers=AH,
                         json={"provider_ref": "x", "bank_reference": "y",
                               "received_amount": amounts[0], "received_currency": "EUR"})
        check("double-confirm rejected 409", r.status_code == 409, f"got {r.status_code}")
        # amount-mismatch guard (amount check precedes oversell check)
        r = await c.post(f"/api/admin/pool-contributions/{mm_cid}/confirm", headers=AH,
                         json={"provider_ref": "x", "bank_reference": "y",
                               "received_amount": 4999, "received_currency": "EUR"})
        check("amount-mismatch rejected 400", r.status_code == 400, f"got {r.status_code}")
        await c.post(f"/api/admin/pool-contributions/{mm_cid}/refund", headers=AH)

        print("\n── Pool state after funding ──")
        r = await c.get(f"/api/admin/pools/{pid}", headers=AH)
        pool = r.json()["pool"]
        check("confirmed_amount == 100000", pool["confirmed_amount"] == 100000, str(pool["confirmed_amount"]))
        check("issued_units == 100000", pool["issued_units"] == 100000, str(pool["issued_units"]))
        check("status == funded", pool["status"] == "funded", pool["status"])

        print("\n── Invariants endpoint ──")
        r = await c.get(f"/api/admin/pools/{pid}/invariants", headers=AH)
        inv = r.json()
        check("all invariants green", inv["all_passed"], str(inv["counts"]))

        print("\n── Certificates issued on funding ──")
        r = await c.get("/api/investor/pool-certificates", headers=IH)
        certs = [x for x in r.json()["items"] if x["pool_id"] == pid]
        check("certificate issued for investor", len(certs) >= 1, str(len(certs)))

        print("\n── Release to seller ──")
        r = await c.post(f"/api/admin/pools/{pid}/release-to-seller", headers=AH,
                         json={"amount": 100000, "seller_name": "Seller Ltd",
                               "seller_iban": "UA000000", "reason": "Asset purchase"})
        check("release 200", r.status_code == 200, r.text[:160])
        check("status released_to_seller", r.json()["pool"]["status"] == "released_to_seller")
        check("available_cash == 0", r.json()["pool"]["available_cash"] == 0,
              str(r.json()["pool"]["available_cash"]))
        # over-release guard
        r = await c.post(f"/api/admin/pools/{pid}/release-to-seller", headers=AH,
                         json={"amount": 1, "seller_name": "x", "reason": "y"})
        check("over-release rejected 409", r.status_code == 409, f"got {r.status_code}")

        print("\n── Revenue event + pro-rata distribution ──")
        await c.post(f"/api/admin/pools/{pid}/mark-operating", headers=AH)
        # balance before (slate-independent: investor balance is cumulative across pools)
        r = await c.get("/api/investor/pool-balances", headers=IH)
        before = next((b for b in r.json()["items"] if b["currency"] == "EUR"), None)
        credited_before = before["credited"] if before else 0
        r = await c.post("/api/admin/revenue-events", headers=AH,
                         json={"pool_id": pid, "gross_amount": 10000,
                               "expenses_amount": 1000, "reserve_amount": 1000,
                               "description": "Rent"})
        check("revenue event 200", r.status_code == 200, r.text[:160])
        ev = r.json()["revenue_event"]
        check("net_distributable == 8000", ev["net_distributable"] == 8000, str(ev["net_distributable"]))
        r = await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)
        check("distribute 200", r.status_code == 200, r.text[:160])
        check("distributed_amount == 8000", r.json()["distributed_amount"] == 8000, str(r.json().get("distributed_amount")))
        # double distribute guard
        r = await c.post(f"/api/admin/revenue-events/{ev['id']}/distribute", headers=AH)
        check("double-distribute rejected 409", r.status_code == 409, f"got {r.status_code}")

        print("\n── Investor balance (pro-rata, single investor → full 8000 of THIS pool) ──")
        r = await c.get("/api/investor/pool-balances", headers=IH)
        eur = next((b for b in r.json()["items"] if b["currency"] == "EUR"), None)
        check("credited delta == 8000", eur and round(eur["credited"] - credited_before, 2) == 8000, str(eur))
        avail_now = eur["available"] if eur else 0

        print("\n── Withdrawal cycle ──")
        r = await c.post("/api/investor/pool-withdrawals", headers=IH,
                         json={"currency": "EUR", "amount": 3000, "destination_iban": "UA111"})
        check("withdrawal request 200", r.status_code == 200, r.text[:160])
        wid = r.json()["withdrawal"]["id"]
        # over-withdraw guard: request more than remaining available
        r = await c.post("/api/investor/pool-withdrawals", headers=IH,
                         json={"currency": "EUR", "amount": round(avail_now - 3000 + 1000, 2)})
        check("over-withdraw rejected 409", r.status_code == 409, f"got {r.status_code}")
        r = await c.post(f"/api/admin/pool-withdrawals/{wid}/approve", headers=AH)
        check("approve 200", r.status_code == 200)
        r = await c.post(f"/api/admin/pool-withdrawals/{wid}/pay", headers=AH,
                         json={"bank_reference": "PAYOUT-1"})
        check("pay 200", r.status_code == 200)
        r = await c.post(f"/api/admin/pool-withdrawals/{wid}/reconcile", headers=AH)
        check("reconcile 200", r.status_code == 200)
        check("withdrawal reconciled", r.json()["withdrawal"]["status"] == "reconciled")

        print("\n── Final invariants ──")
        r = await c.get(f"/api/admin/pools/{pid}/invariants", headers=AH)
        check("final invariants green", r.json()["all_passed"], str(r.json()["counts"]))

        print("\n── Cash conservation audit (Statement A) ──")
        r = await c.get(f"/api/admin/pools/{pid}/cash-audit", headers=AH)
        a = r.json()
        check("cash-audit 200", r.status_code == 200, r.text[:160])
        check("Statement A reconciles", a.get("reconciles") is True, str(a.get("checks")))
        # IN = contributions(100000) + revenue(10000) = 110000
        check("inflows total == 110000", a["inflows"]["total"] == 110000, str(a["inflows"]))
        # OUT = releases(100000) + expenses(1000) + distributions(8000) = 109000
        check("outflows total == 109000", a["outflows"]["total"] == 109000, str(a["outflows"]))
        # remaining cash = reserve earmarked (1000)
        check("cash_balance == 1000 (reserve)", a["cash_balance"] == 1000, str(a["cash_balance"]))
        check("reserves_earmarked == 1000", a["reserves_earmarked"] == 1000, str(a["reserves_earmarked"]))
        check("movement journal populated", len(a.get("movements", [])) >= 4, str(len(a.get("movements", []))))
        mtypes = {m["type"] for m in a.get("movements", [])}
        check("journal has INFLOW+REVENUE+OUTFLOW+DISTRIBUTION",
              {"INFLOW", "REVENUE", "OUTFLOW", "DISTRIBUTION"}.issubset(mtypes), str(mtypes))

        print("\n── Investor-balance audit (Statement B) ──")
        r = await c.get("/api/admin/pool-cash-audit", headers=AH)
        b = r.json()
        check("Statement B reconciles", b.get("reconciles") is True, str(b.get("checks")))
        check("distributions = paid + outstanding",
              abs(b["distributions_credited"] - (b["withdrawals_paid"] + b["outstanding_balances"])) < 0.01,
              str(b))

    print(f"\n════════ RESULT: {len(PASS)} passed, {len(FAIL)} failed ════════")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("POOL OS CONTRACT — ALL GREEN ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
