"""
H1.1 Funding Center — POC end-to-end smoke
==========================================

Validates the full operational loop in one shot:

1. login as admin (we'll use admin for both investor + admin actions in this POC
   since admin can also act as investor)
2. list bank-accounts (must include SEPA EUR)
3. submit SEPA inbound 50000 EUR → expect canonical_status=submitted
4. upload PDF proof → expect canonical_status=pending_review
5. list proofs (must be 1, must have working download URL)
6. admin reconcile (50000 EUR observed, matched=true)
7. admin match → expect canonical_status=matched
8. admin confirm → expect canonical_status=confirmed + ledger posting
9. investor history → confirmed entry present with R3 schema
10. admin /exceptions → no flags for our happy-path transfer
11. admin /ledger → contains our transfer

Failure of ANY step terminates the script with non-zero exit code.
"""
from __future__ import annotations

import io
import os
import sys
import time
import uuid

import requests

BASE = os.environ.get("LUMEN_API_BASE", "http://localhost:8001/api")
ADMIN_EMAIL = os.environ.get("LUMEN_ADMIN_EMAIL", "admin@atlas.dev")
ADMIN_PWD = os.environ.get("LUMEN_ADMIN_PWD", "admin123")


def hr(title: str) -> None:
    print("\n" + "═" * 72)
    print(f" {title}")
    print("═" * 72)


def fail(step: str, resp) -> None:
    print(f"❌ FAIL @ {step}")
    print(f"   status_code: {getattr(resp, 'status_code', '?')}")
    try:
        print(f"   body: {resp.json()}")
    except Exception:
        print(f"   body: {getattr(resp, 'text', resp)[:400]}")
    sys.exit(1)


def main() -> None:
    s = requests.Session()

    hr("1. Login (admin acts as investor + admin)")
    r = s.post(f"{BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    if r.status_code != 200:
        fail("login", r)
    # session cookie is Secure-flagged; for localhost HTTP we need to
    # downgrade it so requests will send it on subsequent calls.
    for c in s.cookies:
        c.secure = False
    print(f"✅ logged in as {r.json().get('email')} (role={r.json().get('role')})")

    hr("2. List bank-accounts — SEPA EUR must be present")
    r = s.get(f"{BASE}/lumen/institutional/rails/bank-accounts")
    if r.status_code != 200:
        fail("bank-accounts", r)
    accounts = r.json().get("items") or []
    sepa = next((a for a in accounts if a.get("currency") == "EUR"
                 and a.get("method") == "sepa"), None)
    if not sepa:
        print("Items:", accounts)
        fail("bank-accounts: no SEPA EUR account", r)
    print(f"✅ SEPA EUR account found: IBAN={sepa['iban']}, bank={sepa['bank_name']}")

    hr("3. Submit SEPA inbound 50000 EUR")
    ref = f"POC-{uuid.uuid4().hex[:10].upper()}"
    r = s.post(f"{BASE}/lumen/institutional/rails/sepa/transfers",
                json={
                    "direction": "inbound",
                    "amount": 50000,
                    "currency": "EUR",
                    "beneficiary_iban": "DE89370400440532013000",
                    "beneficiary_name": "Lumen Capital SE",
                    "reference": ref,
                    "purpose": "POC test",
                })
    if r.status_code != 200:
        fail("submit SEPA", r)
    tx = r.json()
    tid = tx["id"]
    print(f"✅ transfer created: id={tid}, reference={tx['reference']}, "
          f"canonical_status={tx.get('canonical_status')}")
    if tx.get("canonical_status") != "submitted":
        fail("canonical_status != submitted after create", r)

    hr("4. Upload PDF proof → expect canonical_status=pending_review")
    # Minimal valid PDF
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n"
    )
    files = {"file": ("proof.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r = s.post(f"{BASE}/lumen/institutional/rails/transfers/{tid}/proof",
                files=files, data={"note": "POC bank statement"})
    if r.status_code != 200:
        fail("proof upload", r)
    body = r.json()
    print(f"✅ proof uploaded: proof_id={body['proof']['id']}, "
          f"canonical_status={body.get('canonical_status')}")
    if body.get("canonical_status") != "pending_review":
        fail("canonical_status != pending_review after proof", r)

    hr("5. List proofs (expect 1)")
    r = s.get(f"{BASE}/lumen/institutional/rails/transfers/{tid}/proofs")
    if r.status_code != 200 or r.json().get("total") != 1:
        fail("list proofs", r)
    proof = r.json()["items"][0]
    print(f"✅ proof listed: size={proof['size_bytes']} bytes, "
          f"url={proof['url_internal']}")
    # Try download
    r = s.get(f"{BASE}/lumen/institutional/rails/proofs/{proof['id']}/download")
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        fail("download proof", r)
    print(f"✅ proof downloaded: {len(r.content)} bytes, PDF header OK")

    hr("6. Admin reconcile (50000 EUR observed → matched=true)")
    r = s.post(
        f"{BASE}/admin/lumen/institutional/rails/transfers/{tid}/reconcile",
        json={
            "bank_statement_ref": f"BANK-STMT-{ref}",
            "amount_observed": 50000.00,
            "currency_observed": "EUR",
        },
    )
    if r.status_code != 200:
        fail("reconcile", r)
    recon = r.json().get("reconciliation") or {}
    if not recon.get("matched"):
        fail("reconciliation.matched != true", r)
    print(f"✅ reconcile OK: matched={recon['matched']}, "
          f"delta_amount={recon['delta_amount']}")

    hr("7. Admin match → expect canonical_status=matched")
    r = s.post(
        f"{BASE}/admin/lumen/institutional/rails/transfers/{tid}/match",
        json={"note": "POC bank match"},
    )
    if r.status_code != 200:
        fail("match", r)
    if r.json().get("canonical_status") != "matched":
        fail("canonical_status != matched after /match", r)
    print(f"✅ matched: canonical_status={r.json()['canonical_status']}")

    hr("8. Admin confirm → expect canonical_status=confirmed + ledger posted")
    r = s.post(
        f"{BASE}/admin/lumen/institutional/rails/transfers/{tid}/confirm",
        json={"provider_ref": f"BANK-PROV-{ref}", "note": "POC confirm"},
    )
    if r.status_code != 200:
        fail("confirm", r)
    t2 = r.json().get("transfer") or {}
    if t2.get("canonical_status") != "confirmed":
        fail("canonical_status != confirmed after /confirm", r)
    print(f"✅ confirmed: canonical_status={t2['canonical_status']}")

    hr("9. Investor history (R3) — confirmed entry present, schema check")
    r = s.get(f"{BASE}/lumen/institutional/rails/history?limit=10")
    if r.status_code != 200:
        fail("history", r)
    rows = r.json().get("items") or []
    my_row = next((x for x in rows if x.get("reference") == ref), None)
    if not my_row:
        fail("history: transfer not found in history", r)
    expected_keys = {"date", "reference", "method", "amount", "currency", "status"}
    if not expected_keys.issubset(my_row.keys()):
        print("Got keys:", list(my_row.keys()))
        fail("history: schema R3 violated", r)
    if my_row["status"] != "confirmed":
        fail("history: status != confirmed", r)
    if my_row["method"] not in ("SEPA", "SEPA Instant"):
        fail("history: method not SEPA-shaped", r)
    print(f"✅ history row R3-OK: {my_row}")

    hr("10. Admin /exceptions — happy-path transfer must NOT appear")
    r = s.get(f"{BASE}/admin/lumen/institutional/rails/exceptions?limit=200")
    if r.status_code != 200:
        fail("exceptions", r)
    flagged = [x for x in r.json().get("items") or []
               if x.get("transfer_id") == tid]
    if flagged:
        print("flagged:", flagged)
        fail("exceptions: happy-path transfer was flagged unexpectedly", r)
    print(f"✅ exceptions clean for our transfer "
          f"(total exceptions in system: {r.json().get('total')})")

    hr("11. Admin /ledger — contains our transfer's ledger entry")
    r = s.get(f"{BASE}/admin/lumen/institutional/rails/ledger?limit=50")
    if r.status_code != 200:
        fail("ledger", r)
    entries = r.json().get("items") or []
    mine = [e for e in entries if e.get("transfer_id") == tid]
    if not mine:
        fail("ledger: our transfer not in ledger view", r)
    print(f"✅ ledger entry: {mine[0]['id']} amount={mine[0]['amount']} {mine[0]['currency']}")

    hr("12. Negative paths — verify business rules still enforced")
    # currency mismatch
    r = s.post(f"{BASE}/lumen/institutional/rails/sepa/transfers",
                json={"direction": "inbound", "amount": 50000, "currency": "USD",
                       "beneficiary_iban": "DE89370400440532013000",
                       "beneficiary_name": "Lumen Capital SE",
                       "reference": f"BAD-USD-{uuid.uuid4().hex[:6]}"})
    if r.status_code != 400 or "EUR" not in r.text:
        fail("negative: SEPA+USD should be 400 (currency mismatch)", r)
    print("✅ SEPA+USD → 400 (currency mismatch UA)")

    # below minimum
    r = s.post(f"{BASE}/lumen/institutional/rails/sepa/transfers",
                json={"direction": "inbound", "amount": 50, "currency": "EUR",
                       "beneficiary_iban": "DE89370400440532013000",
                       "beneficiary_name": "Lumen Capital SE",
                       "reference": f"BAD-MIN-{uuid.uuid4().hex[:6]}"})
    if r.status_code != 400 or "1000" not in r.text:
        fail("negative: SEPA<1000 EUR should be 400", r)
    print("✅ SEPA<1000 EUR → 400 (below-min UA)")

    # duplicate reference
    r = s.post(f"{BASE}/lumen/institutional/rails/sepa/transfers",
                json={"direction": "inbound", "amount": 50000, "currency": "EUR",
                       "beneficiary_iban": "DE89370400440532013000",
                       "beneficiary_name": "Lumen Capital SE",
                       "reference": ref})
    if r.status_code != 409:
        fail("negative: duplicate reference should be 409", r)
    print(f"✅ duplicate reference → 409 conflict")

    hr("ALL POC STEPS PASSED ✅")
    print(f"  transfer_id : {tid}")
    print(f"  reference   : {ref}")
    print(f"  final state : confirmed + 1 proof + 1 ledger entry")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
