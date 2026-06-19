"""
Sprint 7 — Wallet + Withdrawals — End-to-end POC.

Covers (Definition of Done):
    1. Wallet is COMPUTED from ledger (not a magic number): available =
       Σcredit(payout/refund/adjustment) − Σdebit(withdrawal) − pending.
    2. Investor sees a positive balance (demo dividends seeded).
    3. Investor can create a withdrawal request → funds reserved
       (available↓, pending↑). NO ledger entry yet.
    4. Cannot withdraw more than available (400).
    5. Admin lifecycle: requested → under_review → approved → processing →
       paid. `paid` creates exactly ONE ledger debit (reason=withdrawal).
    6. After paid: available unchanged (was reserved), total_out↑, pending↓.
    7. Reject path returns the reserved funds (available restored, NO debit).
    8. Investor cancel returns reserved funds.
    9. Invalid transitions are rejected (409). Reject without comment → 400.
   10. Regression: Sprint 6 ledger/payments + Sprint 2 portfolio still work.

Run with:
    cd /app/backend && python tests/test_sprint7_wallet.py
"""
import os
import sys
import uuid
import requests

BASE = os.environ.get("LUMEN_API_BASE", "http://localhost:8001")
TIMEOUT = 30

ADMIN_EMAIL = "admin@atlas.dev"
ADMIN_PASS = "admin123"
INVESTOR_EMAIL = "client@atlas.dev"
INVESTOR_PASS = "client123"

FAILS = []


def _check(cond, msg):
    if cond:
        print(f"  ✓ {msg}")
    else:
        print(f"  ✗ {msg}")
        FAILS.append(msg)


def _login(s, email, password):
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": email, "password": password}, timeout=TIMEOUT)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    tok = s.cookies.get("session_token")
    if tok:
        s.headers["Cookie"] = f"session_token={tok}"
    return r.json()


def section(title):
    print()
    print(f"━━━ {title} ━━━")


def _wallet(s):
    r = s.get(f"{BASE}/api/investor/wallet", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()["wallet"]


def run():
    inv = requests.Session()
    adm = requests.Session()
    _login(inv, INVESTOR_EMAIL, INVESTOR_PASS)
    a = _login(adm, ADMIN_EMAIL, ADMIN_PASS)
    _check(a.get("role") == "admin", "admin logged in")

    # ── 1. Wallet computed from ledger ──────────────────────────────────────
    section("1. Wallet computed from ledger")
    w0 = _wallet(inv)
    print(f"    wallet: avail={w0['available_balance']} pending={w0['pending_balance']} "
          f"in={w0['total_in']} out={w0['total_out']}")
    _check(w0["available_balance"] > 0, "investor has positive available balance (seeded dividends)")
    _check(abs((w0["total_in"] - w0["total_out"] - w0["pending_balance"])
               - w0["available_balance"]) < 0.01,
           "available == total_in − total_out − pending (ledger invariant)")

    # transactions history present
    r = inv.get(f"{BASE}/api/investor/wallet/transactions", timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["total"] >= 1,
           "wallet transactions history returns ledger entries")

    avail0 = w0["available_balance"]

    # ── 2. Cannot withdraw more than available ──────────────────────────────
    section("2. Insufficient funds guard")
    r = inv.post(f"{BASE}/api/investor/withdrawals", json={
        "amount": avail0 + 1_000_000, "currency": "UAH",
        "iban": "UA213223130000026007233566001", "bank_name": "ПриватБанк",
        "beneficiary_name": "Тест Інвестор"}, timeout=TIMEOUT)
    _check(r.status_code == 400, f"over-balance withdrawal rejected (got {r.status_code})")

    # ── 3. Create withdrawal → reserve ──────────────────────────────────────
    section("3. Create withdrawal → funds reserved")
    amount = round(min(10000.0, avail0 / 2.0), 2)
    r = inv.post(f"{BASE}/api/investor/withdrawals", json={
        "amount": amount, "currency": "UAH",
        "iban": "UA213223130000026007233566001", "bank_name": "ПриватБанк",
        "beneficiary_name": "Тест Інвестор"}, timeout=TIMEOUT)
    _check(r.status_code == 200, f"create withdrawal → 200 (got {r.status_code}: {r.text[:120]})")
    wd = r.json()
    req_id = wd["id"]
    _check(wd["status"] == "requested", "new withdrawal status = requested")
    _check(wd.get("ledger_entry_id") is None, "no ledger entry created at request time")

    w1 = _wallet(inv)
    _check(abs((w1["pending_balance"] - w0["pending_balance"]) - amount) < 0.01,
           f"pending_balance increased by amount (Δ={w1['pending_balance'] - w0['pending_balance']} == {amount})")
    _check(abs(w1["available_balance"] - (avail0 - amount)) < 0.01,
           f"available decreased by reserve ({w1['available_balance']} == {avail0 - amount})")

    # ── 4. Admin lifecycle → paid ───────────────────────────────────────────
    section("4. Admin lifecycle: review → approve → processing → paid")
    # invalid jump: processing before approve
    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/processing", json={}, timeout=TIMEOUT)
    _check(r.status_code == 409, f"requested → processing blocked (got {r.status_code})")

    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/review", json={"comment": "Перевірка реквізитів"}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "under_review", "→ under_review")
    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/approve", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "approved", "→ approved")
    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/processing", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "processing", "→ processing")
    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/paid", json={"comment": "Виплачено на IBAN"}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "paid", "→ paid")
    paid = r.json()
    _check(bool(paid.get("ledger_entry_id")), "paid created a ledger debit (ledger_entry_id set)")
    ledger_id = paid.get("ledger_entry_id")

    # ledger debit exists
    r = adm.get(f"{BASE}/api/admin/ledger?reason=withdrawal&entry_type=debit", timeout=TIMEOUT)
    le = r.json()
    _check(any(e["id"] == ledger_id for e in le["items"]),
           "withdrawal debit present in admin ledger")

    w2 = _wallet(inv)
    _check(abs((w1["pending_balance"] - w2["pending_balance"]) - amount) < 0.01,
           f"pending reduced by amount after paid (Δ={w1['pending_balance'] - w2['pending_balance']} == {amount})")
    _check(abs((w2["total_out"] - w1["total_out"]) - amount) < 0.01,
           f"total_out increased by paid amount (Δ={w2['total_out'] - w1['total_out']} == {amount})")
    _check(abs(w2["available_balance"] - (avail0 - amount)) < 0.01,
           f"available stable across paid (reserve became realized): {w2['available_balance']}")

    # cannot act on terminal
    r = adm.post(f"{BASE}/api/admin/withdrawals/{req_id}/approve", json={}, timeout=TIMEOUT)
    _check(r.status_code == 409, f"action on paid (terminal) blocked (got {r.status_code})")

    # ── 5. Reject path returns funds ────────────────────────────────────────
    section("5. Reject path returns reserved funds")
    availR = _wallet(inv)["available_balance"]
    amt2 = round(min(5000.0, availR / 2.0), 2)
    r = inv.post(f"{BASE}/api/investor/withdrawals", json={
        "amount": amt2, "currency": "UAH",
        "iban": "UA213223130000026007233566002", "bank_name": "Монобанк",
        "beneficiary_name": "Тест Інвестор"}, timeout=TIMEOUT)
    rid2 = r.json()["id"]
    afterReserve = _wallet(inv)["available_balance"]
    _check(abs(afterReserve - (availR - amt2)) < 0.01, "reserve applied for 2nd request")

    # reject without comment → 400
    r = adm.post(f"{BASE}/api/admin/withdrawals/{rid2}/reject", json={}, timeout=TIMEOUT)
    _check(r.status_code == 400, f"reject without comment → 400 (got {r.status_code})")
    # reject with comment
    r = adm.post(f"{BASE}/api/admin/withdrawals/{rid2}/reject",
                 json={"comment": "Невірний IBAN"}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "rejected", "rejected with comment")
    backAvail = _wallet(inv)["available_balance"]
    _check(abs(backAvail - availR) < 0.01,
           f"funds returned after reject ({backAvail} == {availR})")
    # no debit created for rejected
    r = adm.get(f"{BASE}/api/admin/ledger?reason=withdrawal&entry_type=debit", timeout=TIMEOUT)
    _check(not any(e.get("withdrawal_request_id") == rid2 for e in r.json()["items"]),
           "no ledger debit for rejected withdrawal")

    # ── 6. Investor cancel returns funds ────────────────────────────────────
    section("6. Investor cancel returns reserved funds")
    availC = _wallet(inv)["available_balance"]
    amt3 = round(min(3000.0, availC / 2.0), 2)
    r = inv.post(f"{BASE}/api/investor/withdrawals", json={
        "amount": amt3, "currency": "UAH",
        "iban": "UA213223130000026007233566003", "bank_name": "ПУМБ",
        "beneficiary_name": "Тест Інвестор"}, timeout=TIMEOUT)
    rid3 = r.json()["id"]
    r = inv.post(f"{BASE}/api/investor/withdrawals/{rid3}/cancel", json={}, timeout=TIMEOUT)
    _check(r.status_code == 200 and r.json()["status"] == "cancelled", "investor cancelled request")
    _check(abs(_wallet(inv)["available_balance"] - availC) < 0.01, "funds returned after cancel")

    # ── 7. Admin queue + detail ─────────────────────────────────────────────
    section("7. Admin withdrawals queue + detail")
    r = adm.get(f"{BASE}/api/admin/withdrawals", timeout=TIMEOUT)
    _check(r.status_code == 200, "GET /admin/withdrawals → 200")
    q = r.json()
    _check(q["counts"].get("paid", 0) >= 1, "queue counts include paid")
    r = adm.get(f"{BASE}/api/admin/withdrawals/{req_id}", timeout=TIMEOUT)
    d = r.json()
    _check(d.get("wallet") is not None and isinstance(d.get("ledger_entries"), list),
           "admin detail returns wallet + ledger entries")

    # ── 8. Regression Sprint 6 / Sprint 2 ───────────────────────────────────
    section("8. Regression S6 (ledger/payments) + S2 (portfolio)")
    r = adm.get(f"{BASE}/api/admin/payments", timeout=TIMEOUT)
    _check(r.status_code == 200, "GET /admin/payments → 200 (S6)")
    r = inv.get(f"{BASE}/api/investor/portfolio", timeout=TIMEOUT)
    _check(r.status_code == 200, "GET /investor/portfolio → 200 (S2)")

    print()
    if FAILS:
        print(f"❌ FAILED: {len(FAILS)} check(s)")
        for f in FAILS:
            print(f"   - {f}")
        sys.exit(1)
    print("✅ Sprint 7 — ALL CHECKS PASS")


if __name__ == "__main__":
    run()
