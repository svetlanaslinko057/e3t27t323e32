"""
Sprint 8 — Payout Engine — End-to-end POC.

Validates the full income chain:
    Asset → Payout Plan → generate(Batch) → approve → credit →
    Ledger(credit, reason=payout) → Wallet.available_balance↑ → Withdrawal

Checks:
    1. Admin creates a payout plan for an asset.
    2. recalculate() previews ownership-pro-rata distribution (sums to expected).
    3. generate() creates a batch (status=generated) + payout_records.
    4. approve() → batch+records approved. credit() → batch credited, ledger
       credit entries created, wallet.available_balance increases by total.
    5. Investor /investor/income reflects paid/expected; /investor/income/payouts
       lists records.
    6. The newly credited income is WITHDRAWABLE (wallet → withdrawal request).
    7. cancel() of a non-credited batch cancels its records (no ledger).
    8. Invalid lifecycle transitions blocked (credit before approve → 409;
       action on credited batch → 409).
    9. Asset payout-summary returns last/next/total.
   10. Regression: S6 ledger, S7 wallet, S2 portfolio still respond.

Run: cd /app/backend && python tests/test_sprint8_payouts.py
"""
import os
import sys
import requests

BASE = os.environ.get("LUMEN_API_BASE", "http://localhost:8001")
TIMEOUT = 30
ADMIN = ("admin@atlas.dev", "admin123")
INVESTOR = ("client@atlas.dev", "client123")
FAILS = []


def _check(cond, msg):
    print(f"  {'✓' if cond else '✗'} {msg}")
    if not cond:
        FAILS.append(msg)


def _login(s, email, pw):
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=TIMEOUT)
    assert r.status_code == 200, f"login {email}: {r.text}"
    tok = s.cookies.get("session_token")
    if tok:
        s.headers["Cookie"] = f"session_token={tok}"
    return r.json()


def section(t):
    print(f"\n━━━ {t} ━━━")


def _wallet(s):
    return s.get(f"{BASE}/api/investor/wallet", timeout=TIMEOUT).json()["wallet"]


def run():
    adm = requests.Session(); inv = requests.Session()
    a = _login(adm, *ADMIN); _login(inv, *INVESTOR)
    _check(a.get("role") == "admin", "admin logged in")

    # pick an asset where the investor has ownership but ideally no plan yet
    own = inv.get(f"{BASE}/api/investor/ownerships", timeout=TIMEOUT).json()["items"]
    _check(len(own) > 0, "investor has ownerships")
    # prefer lavr-tc (no demo plan there)
    target = next((o for o in own if o["asset_id"] == "asset-lavr-tc"), own[0])
    asset_id = target["asset_id"]
    print(f"    target asset: {asset_id} (units={target.get('units')})")

    w_before = _wallet(inv)
    avail_before = w_before["available_balance"]

    # ── 1. Create plan ──────────────────────────────────────────────────────
    section("1-2. Create plan + recalculate preview")
    EXPECTED = 40000.0
    r = adm.post(f"{BASE}/api/admin/payout-plans", json={
        "asset_id": asset_id, "type": "rental_income", "frequency": "monthly",
        "expected_amount": EXPECTED, "notes": "POC plan"}, timeout=TIMEOUT)
    _check(r.status_code == 200, f"create plan → 200 ({r.status_code}: {r.text[:120]})")
    plan = r.json(); plan_id = plan["id"]
    _check(plan["status"] == "active" and plan["type"] == "rental_income", "plan active rental_income")

    # ── 2. Recalculate (preview distribution) ───────────────────────────────
    r = adm.post(f"{BASE}/api/admin/payout-plans/{plan_id}/recalculate", json={}, timeout=TIMEOUT)
    rc = r.json()
    _check(r.status_code == 200 and rc["investor_count"] >= 1, "recalculate returns allocations")
    _check(abs(rc["total_amount"] - EXPECTED) < 0.5, f"distribution sums to expected ({rc['total_amount']} ≈ {EXPECTED})")
    inv_alloc = next((x for x in rc["allocations"] if x["investor_id"] == target["investor_id"]), None)
    _check(inv_alloc is not None and inv_alloc["amount"] > 0, "investor has a positive allocation")
    expected_inv_amount = inv_alloc["amount"] if inv_alloc else 0

    # ── 3. Generate batch ───────────────────────────────────────────────────
    section("3. Generate batch")
    r = adm.post(f"{BASE}/api/admin/payout-plans/{plan_id}/generate", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200, f"generate → 200 ({r.status_code}: {r.text[:120]})")
    batch = r.json(); batch_id = batch["id"]
    _check(batch["status"] == "generated", "batch status = generated")
    _check(batch["payout_count"] >= 1, "batch has payout records")

    # credit before approve → 409
    r = adm.post(f"{BASE}/api/admin/payout-batches/{batch_id}/credit", json={}, timeout=TIMEOUT)
    _check(r.status_code == 409, f"credit before approve blocked ({r.status_code})")

    # ── 4. Approve → Credit ─────────────────────────────────────────────────
    section("4. Approve → Credit → Ledger → Wallet")
    r = adm.post(f"{BASE}/api/admin/payout-batches/{batch_id}/approve", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "approved", "batch approved")
    r = adm.post(f"{BASE}/api/admin/payout-batches/{batch_id}/credit", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "credited", "batch credited")

    # ledger credit present
    r = adm.get(f"{BASE}/api/admin/ledger?reason=payout&entry_type=credit", timeout=TIMEOUT)
    le = r.json()["items"]
    _check(any(e.get("payout_batch_id") == batch_id for e in le), "ledger credit linked to batch")

    w_after = _wallet(inv)
    _check(abs((w_after["available_balance"] - avail_before) - expected_inv_amount) < 0.5,
           f"wallet available increased by allocation (Δ={w_after['available_balance'] - avail_before} ≈ {expected_inv_amount})")

    # action on credited (terminal) batch → 409
    r = adm.post(f"{BASE}/api/admin/payout-batches/{batch_id}/cancel", json={}, timeout=TIMEOUT)
    _check(r.status_code == 409, f"cancel credited batch blocked ({r.status_code})")

    # ── 5. Investor income reflects it ──────────────────────────────────────
    section("5. Investor income view")
    inc = inv.get(f"{BASE}/api/investor/income", timeout=TIMEOUT).json()
    _check(inc["summary"]["paid_total"] > 0, "income paid_total > 0")
    asset_row = next((x for x in inc["by_asset"] if x["asset_id"] == asset_id), None)
    _check(asset_row is not None and asset_row["paid"] >= expected_inv_amount - 0.5,
           "income by_asset reflects credited payout")
    pr = inv.get(f"{BASE}/api/investor/income/payouts", timeout=TIMEOUT).json()
    _check(pr["total"] >= 1 and any(x["status"] == "credited" for x in pr["items"]),
           "investor sees credited payout records")

    # ── 6. Credited income is withdrawable ──────────────────────────────────
    section("6. Income → Withdrawal (full chain)")
    amt = round(min(10000.0, w_after["available_balance"] / 2), 2)
    r = inv.post(f"{BASE}/api/investor/withdrawals", json={
        "amount": amt, "currency": "UAH",
        "iban": "UA213223130000026007233566001", "bank_name": "ПриватБанк",
        "beneficiary_name": "Тест Інвестор"}, timeout=TIMEOUT)
    _check(r.status_code == 200, f"withdrawal from payout income → 200 ({r.status_code})")
    if r.status_code == 200:
        wid = r.json()["id"]
        inv.post(f"{BASE}/api/investor/withdrawals/{wid}/cancel", json={}, timeout=TIMEOUT)  # cleanup

    # ── 7. Generate + cancel a batch (no ledger) ────────────────────────────
    section("7. Cancel non-credited batch")
    r = adm.post(f"{BASE}/api/admin/payout-plans/{plan_id}/generate", json={}, timeout=TIMEOUT)
    b2 = r.json()["id"]
    ledger_before = len(adm.get(f"{BASE}/api/admin/ledger?reason=payout", timeout=TIMEOUT).json()["items"])
    r = adm.post(f"{BASE}/api/admin/payout-batches/{b2}/cancel", json={"reason": "Помилка періоду"}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "cancelled", "non-credited batch cancelled")
    det = adm.get(f"{BASE}/api/admin/payout-batches/{b2}", timeout=TIMEOUT).json()
    _check(all(rec["status"] == "cancelled" for rec in det["records"]), "cancelled batch records all cancelled")
    ledger_after = len(adm.get(f"{BASE}/api/admin/ledger?reason=payout", timeout=TIMEOUT).json()["items"])
    _check(ledger_before == ledger_after, "no ledger entries from cancelled batch")

    # ── 8. Asset payout summary ─────────────────────────────────────────────
    section("8. Asset payout summary")
    r = inv.get(f"{BASE}/api/assets/{asset_id}/payout-summary", timeout=TIMEOUT)
    ps = r.json()
    _check(r.status_code == 200 and ps["total_accrued"] > 0, "asset payout-summary has total_accrued")

    # ── 9. Admin batches list + counts ──────────────────────────────────────
    section("9. Admin batches queue")
    r = adm.get(f"{BASE}/api/admin/payout-batches", timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["counts"].get("credited", 0) >= 1, "batch queue counts include credited")

    # ── 10. Regression ──────────────────────────────────────────────────────
    section("10. Regression S6/S7/S2")
    _check(adm.get(f"{BASE}/api/admin/payments", timeout=TIMEOUT).status_code == 200, "S6 /admin/payments")
    _check(inv.get(f"{BASE}/api/investor/wallet", timeout=TIMEOUT).status_code == 200, "S7 /investor/wallet")
    _check(inv.get(f"{BASE}/api/investor/portfolio", timeout=TIMEOUT).status_code == 200, "S2 /investor/portfolio")

    print()
    if FAILS:
        print(f"❌ FAILED: {len(FAILS)} check(s)")
        for f in FAILS:
            print("   -", f)
        sys.exit(1)
    print("✅ Sprint 8 — ALL CHECKS PASS")


if __name__ == "__main__":
    run()
