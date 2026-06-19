"""
P2 — FIRST REAL MONEY REHEARSAL  (no real payment — dry run only)

End-to-end rehearsal of the FULL pipeline a first real investor would touch.
The point of this script is NOT to fix bugs — it's to MEASURE where the
operator/admin tupit and where the UX breaks.  Each step is stopwatched and
labelled PASS / FRICTION / BLOCKER.

Pipeline rehearsed (in order):
    Lead → Investor (convert)
    KYC docs → KYC submit → admin approve
    Accreditation submit → admin transition
    Contract list/view → sign
    Funding request (SEPA)
    Proof upload
    Reconciliation (admin)
    Match → Confirm (admin)
    Certificate (auto-issue / read)
    Treasury (admin KPIs / pulse)
    Beta Command Center (launch-status milestones)

Run:  cd /app/backend && python test_first_real_money_rehearsal.py
"""
from __future__ import annotations

import asyncio
import io
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import bcrypt
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE = "http://localhost:8001"
_db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

ADMIN_EMAIL, ADMIN_PW = "admin@atlas.dev", "admin123"
INVESTOR_EMAIL = f"rehearsal+{uuid.uuid4().hex[:6]}@atlas.dev"
INVESTOR_PW = "rehearsal123"

# Tracking
RESULTS: list[dict[str, Any]] = []
FRICTIONS: list[str] = []
BLOCKERS: list[str] = []


def step(name: str, status: str, t_ms: float, detail: str = ""):
    badge = {"PASS": "[PASS]", "FRICT": "[FRICT]", "BLOCK": "[BLOCK]"}.get(status, status)
    line = f"  {badge}  ({t_ms:>6.0f}ms)  {name}"
    if detail:
        line += f"  — {detail[:160]}"
    print(line)
    RESULTS.append({"step": name, "status": status, "t_ms": t_ms, "detail": detail})
    if status == "FRICT":
        FRICTIONS.append(f"{name}: {detail}")
    if status == "BLOCK":
        BLOCKERS.append(f"{name}: {detail}")


async def stopwatch(fn, *a, **kw):
    t0 = time.monotonic()
    try:
        r = await fn(*a, **kw)
        return r, (time.monotonic() - t0) * 1000
    except Exception as e:
        return e, (time.monotonic() - t0) * 1000


async def login(client: httpx.AsyncClient, email: str, pw: str) -> bool:
    r = await client.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        return False
    token = r.cookies.get("session_token")
    if not token:
        import re
        m = re.search(r"session_token=([^;]+)", r.headers.get("set-cookie", ""))
        token = m.group(1) if m else None
    client.headers["Cookie"] = f"session_token={token}"
    return True


async def ensure_investor() -> str:
    """Create a fresh real-investor user (not seed)."""
    u = await _db.users.find_one({"email": INVESTOR_EMAIL})
    if u:
        return u.get("user_id") or u.get("id")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    await _db.users.insert_one({
        "user_id": uid, "id": uid,
        "email": INVESTOR_EMAIL, "name": "Rehearsal Investor",
        "role": "investor", "roles": ["investor"],
        "level": "junior", "skills": [], "source": "rehearsal",
        "password_hash": bcrypt.hashpw(INVESTOR_PW.encode(), bcrypt.gensalt()).decode(),
        "picture": None, "rating": 5.0, "completed_tasks": 0,
        "active_load": 0, "states": [], "active_context": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid


# ──────────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "=" * 78)
    print(" P2 — FIRST REAL MONEY REHEARSAL  (dry run, no real payment)")
    print("=" * 78 + "\n")

    investor_uid = await ensure_investor()
    print(f"  investor_uid = {investor_uid}")
    print(f"  investor_email = {INVESTOR_EMAIL}\n")

    admin = httpx.AsyncClient(timeout=30)
    inv = httpx.AsyncClient(timeout=30)

    # ── 0. Auth ────────────────────────────────────────────────────────────
    print("STAGE 0 · Authentication")
    t0 = time.monotonic()
    ok = await login(admin, ADMIN_EMAIL, ADMIN_PW)
    step("admin login", "PASS" if ok else "BLOCK",
         (time.monotonic() - t0) * 1000)
    if not ok:
        print("FATAL: admin login failed"); return

    t0 = time.monotonic()
    ok = await login(inv, INVESTOR_EMAIL, INVESTOR_PW)
    step("investor login", "PASS" if ok else "BLOCK",
         (time.monotonic() - t0) * 1000)
    if not ok:
        print("FATAL: investor login failed"); return

    # ── 1. IR Center: create lead → assign owner → notes/task/meeting → convert
    print("\nSTAGE 1 · IR Center (Manager work before money)")
    t0 = time.monotonic()
    r = await admin.post(f"{BASE}/api/admin/ir/leads", json={
        "email": INVESTOR_EMAIL,
        "full_name": "Rehearsal Investor",
        "phone": "+380501234567",
        "source": "rehearsal",
        "interest": "Real estate · Podilskyi",
        "budget_range": "100k-500k",
        "note": "First-real-money rehearsal lead",
    })
    elapsed = (time.monotonic() - t0) * 1000
    if r.status_code == 200:
        lead = r.json()
        lead_id = lead.get("lead_id")
        step("create lead", "PASS", elapsed,
             f"lead_id={lead_id}, user_id auto-linked={bool(lead.get('user_id'))}")
    elif r.status_code == 409:
        step("create lead (already exists)", "PASS", elapsed, "409 idempotent")
        # fetch existing
        r2 = await admin.get(f"{BASE}/api/admin/ir/leads", params={"q": INVESTOR_EMAIL})
        leads = (r2.json().get("leads") or [])
        lead_id = leads[0]["lead_id"] if leads else None
    else:
        step("create lead", "BLOCK", elapsed, f"HTTP {r.status_code} {r.text[:120]}")
        lead_id = None

    if lead_id:
        # Find a manager to assign
        t0 = time.monotonic()
        r = await admin.get(f"{BASE}/api/admin/ir/managers")
        elapsed = (time.monotonic() - t0) * 1000
        mgrs = (r.json().get("items") or r.json().get("managers") or []) if r.status_code == 200 else []
        if mgrs:
            mgr = mgrs[0]
            mgr_id = mgr.get("user_id") or mgr.get("manager_id") or mgr.get("id")
            step("list managers", "PASS", elapsed, f"{len(mgrs)} managers · first={mgr_id}")
        else:
            step("list managers", "FRICT", elapsed,
                 "no managers seeded — admin would have to create one manually before assigning")
            mgr_id = None

        if mgr_id:
            t0 = time.monotonic()
            r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/owner",
                                  json={"user_id": mgr_id})
            elapsed = (time.monotonic() - t0) * 1000
            step("assign owner (manager)",
                 "PASS" if r.status_code == 200 else "FRICT",
                 elapsed, f"HTTP {r.status_code}")

        # Add a note
        t0 = time.monotonic()
        r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/notes",
                              json={"body": "First call — interested in 500k UAH tranche"})
        elapsed = (time.monotonic() - t0) * 1000
        step("add note", "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code}")

        # Add a task
        t0 = time.monotonic()
        r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/tasks", json={
            "title": "Schedule KYC consultation",
            "task_type": "follow_up",
            "priority": "high",
            "due_date": "2026-06-22T10:00:00Z",
        })
        elapsed = (time.monotonic() - t0) * 1000
        step("add task", "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code}")

        # Schedule a meeting
        t0 = time.monotonic()
        r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/meetings", json={
            "title": "KYC Onboarding Call",
            "scheduled_at": "2026-06-22T10:00:00Z",
            "type": "video",
            "duration_min": 30,
        })
        elapsed = (time.monotonic() - t0) * 1000
        step("schedule meeting", "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code}")

        # Move stage manually → qualified
        t0 = time.monotonic()
        r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/stage",
                              json={"stage": "qualified"})
        elapsed = (time.monotonic() - t0) * 1000
        step("manual stage → qualified",
             "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code}")

        # Convert lead → real user
        t0 = time.monotonic()
        r = await admin.post(f"{BASE}/api/admin/ir/leads/{lead_id}/convert",
                              json={"user_id": investor_uid})
        elapsed = (time.monotonic() - t0) * 1000
        step("convert lead → user_id",
             "PASS" if r.status_code == 200 else "BLOCK",
             elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # ── 2. KYC ─────────────────────────────────────────────────────────────
    print("\nSTAGE 2 · KYC")
    # Upload all required documents — passport + tax_id (per _kyc_completeness)
    for doc_type, content in [
        ("passport", b"%PDF-1.4\nmock passport content\n%%EOF\n"),
        ("tax_id", b"%PDF-1.4\nmock tax_id content\n%%EOF\n"),
    ]:
        t0 = time.monotonic()
        files = {"file": (f"{doc_type}.pdf", content, "application/pdf")}
        data = {"doc_type": doc_type}
        r = await inv.post(f"{BASE}/api/investor/kyc/documents", data=data, files=files)
        elapsed = (time.monotonic() - t0) * 1000
        step(f"upload KYC document ({doc_type})",
             "PASS" if r.status_code in (200, 201) else "FRICT",
             elapsed, f"HTTP {r.status_code}")

    # Patch profile (full_name/dob/country/tax_id/iban) — required by KYC submit
    t0 = time.monotonic()
    r = await inv.patch(f"{BASE}/api/investor/profile", json={
        "full_name": "Rehearsal Investor",
        "date_of_birth": "1990-01-01",
        "country": "UA",
        "residency_country": "UA",
        "phone": "+380501234567",
        "tax_id": "1234567890",
        "iban": "UA213223130000026007233566001",
        "bank_name": "PrivatBank",
        "bank_country": "UA",
    })
    elapsed = (time.monotonic() - t0) * 1000
    step("patch investor profile", "PASS" if r.status_code == 200 else "FRICT",
         elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # Submit KYC
    t0 = time.monotonic()
    r = await inv.post(f"{BASE}/api/investor/kyc/submit", json={})
    elapsed = (time.monotonic() - t0) * 1000
    step("submit KYC", "PASS" if r.status_code == 200 else "FRICT",
         elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # Admin approves
    t0 = time.monotonic()
    r = await admin.post(f"{BASE}/api/admin/kyc/{investor_uid}/approve", json={
        "note": "Rehearsal approval",
    })
    elapsed = (time.monotonic() - t0) * 1000
    step("admin approve KYC", "PASS" if r.status_code == 200 else "BLOCK",
         elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # ── 3. Accreditation ───────────────────────────────────────────────────
    print("\nSTAGE 3 · Accreditation")
    t0 = time.monotonic()
    r = await inv.patch(f"{BASE}/api/investor/accreditation/profile", json={
        "financial": {
            "annual_income_uah": 600000,
            "net_worth_uah": 1500000,
            "liquid_assets_uah": 500000,
            "investment_horizon": "long",
            "risk_appetite": "moderate",
        },
        "experience": {
            "years_investing": 3,
            "asset_classes": ["real_estate"],
            "real_estate_experience": "intermediate",
        },
        "jurisdiction": {
            "residency_country": "UA",
            "citizenship": "UA",
            "is_us_person": False,
            "is_pep": False,
        },
        "tax": {
            "tax_id": "1234567890",
            "tax_residence": "UA",
            "tax_form": "none",
        },
    })
    elapsed = (time.monotonic() - t0) * 1000
    step("patch accreditation profile",
         "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code} {r.text[:120]}")

    t0 = time.monotonic()
    r = await inv.post(f"{BASE}/api/investor/accreditation/submit", json={})
    elapsed = (time.monotonic() - t0) * 1000
    step("submit accreditation",
         "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code} {r.text[:120]}")

    t0 = time.monotonic()
    r = await admin.post(f"{BASE}/api/admin/accreditation/{investor_uid}/transition", json={
        "to_status": "approved",
        "level": "qualified",
        "note": "Rehearsal approval",
        "basis": "rehearsal",
        "expires_in_days": 365,
    })
    elapsed = (time.monotonic() - t0) * 1000
    step("admin transition → qualified",
         "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code} {r.text[:120]}")

    # ── 4. Contract ────────────────────────────────────────────────────────
    print("\nSTAGE 4 · Contract")
    t0 = time.monotonic()
    r = await inv.get(f"{BASE}/api/investor/contracts")
    elapsed = (time.monotonic() - t0) * 1000
    contracts = (r.json().get("items") or r.json().get("contracts") or []) if r.status_code == 200 else []
    if r.status_code == 200:
        step("list my contracts", "PASS", elapsed, f"{len(contracts)} contract(s)")
    else:
        step("list my contracts", "FRICT", elapsed, f"HTTP {r.status_code}")
    if not contracts:
        step("contract availability (after KYC+accred)", "FRICT", 0,
             "No contract auto-generated — investor would need explicit funding intent first")

    # ── 5. Funding request (SEPA) ──────────────────────────────────────────
    print("\nSTAGE 5 · Funding request (SEPA)")
    ref = f"REHEARSAL-{int(time.time())}"
    t0 = time.monotonic()
    r = await inv.post(f"{BASE}/api/lumen/institutional/rails/sepa/transfers", json={
        "direction": "inbound",
        "amount": 5000,
        "currency": "EUR",
        "beneficiary_name": "Lumen Capital SE",
        "beneficiary_iban": "DE89370400440532013000",
        "reference": ref,
    })
    elapsed = (time.monotonic() - t0) * 1000
    transfer_id = None
    if r.status_code == 200:
        transfer = r.json()
        transfer_id = transfer.get("id")
        step("create SEPA transfer (investor)", "PASS", elapsed,
             f"transfer_id={transfer_id} ref={ref}")
    else:
        step("create SEPA transfer (investor)", "BLOCK", elapsed,
             f"HTTP {r.status_code} {r.text[:200]}")

    # ── 6. Proof upload ────────────────────────────────────────────────────
    print("\nSTAGE 6 · Proof upload")
    if transfer_id:
        t0 = time.monotonic()
        files = {"file": ("payment_proof.pdf",
                          b"%PDF-1.4\nmock payment confirmation\n%%EOF\n",
                          "application/pdf")}
        data = {"note": "Initial 5000 EUR transfer proof"}
        r = await inv.post(
            f"{BASE}/api/lumen/institutional/rails/transfers/{transfer_id}/proof",
            data=data, files=files,
        )
        elapsed = (time.monotonic() - t0) * 1000
        step("attach proof PDF", "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # ── 7. Reconciliation ─────────────────────────────────────────────────
    print("\nSTAGE 7 · Reconciliation (admin)")
    if transfer_id:
        t0 = time.monotonic()
        r = await admin.post(
            f"{BASE}/api/admin/lumen/institutional/rails/transfers/{transfer_id}/reconcile",
            json={
                "bank_statement_ref": f"STMT-{ref}",
                "amount_observed": 5000,
                "currency_observed": "EUR",
            },
        )
        elapsed = (time.monotonic() - t0) * 1000
        recon = (r.json().get("reconciliation") or {}) if r.status_code == 200 else {}
        ok = r.status_code == 200 and recon.get("matched") is True
        step("reconcile (matched)", "PASS" if ok else "FRICT", elapsed,
             f"HTTP {r.status_code} matched={recon.get('matched')} "
             f"delta={recon.get('delta_amount')}")

    # ── 8. Match → Confirm ────────────────────────────────────────────────
    print("\nSTAGE 8 · Match → Confirm (admin)")
    if transfer_id:
        t0 = time.monotonic()
        r = await admin.post(
            f"{BASE}/api/admin/lumen/institutional/rails/transfers/{transfer_id}/match",
            json={"note": "Rehearsal · auto-match"},
        )
        elapsed = (time.monotonic() - t0) * 1000
        step("admin /match", "PASS" if r.status_code == 200 else "FRICT",
             elapsed, f"HTTP {r.status_code} {r.text[:120]}")

        t0 = time.monotonic()
        r = await admin.post(
            f"{BASE}/api/admin/lumen/institutional/rails/transfers/{transfer_id}/confirm",
            json={"provider_ref": f"BANK-{ref}"},
        )
        elapsed = (time.monotonic() - t0) * 1000
        step("admin /confirm → ledger", "PASS" if r.status_code == 200 else "BLOCK",
             elapsed, f"HTTP {r.status_code} {r.text[:120]}")

    # ── 9. Certificate ────────────────────────────────────────────────────
    print("\nSTAGE 9 · Certificate (auto-issue check)")
    t0 = time.monotonic()
    r = await inv.get(f"{BASE}/api/investor/certificates")
    elapsed = (time.monotonic() - t0) * 1000
    certs = (r.json().get("items") or r.json().get("certificates") or []) if r.status_code == 200 else []
    if r.status_code == 200:
        if certs:
            step("certificate auto-issued", "PASS", elapsed,
                 f"{len(certs)} certificate(s) found")
        else:
            step("certificate auto-issued", "FRICT", elapsed,
                 "Funding confirmed but no certificate issued — manual admin step likely required")
    else:
        step("certificate list", "FRICT", elapsed, f"HTTP {r.status_code}")

    # Admin: try to admin-list certificates
    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/certificates", params={"q": investor_uid})
    elapsed = (time.monotonic() - t0) * 1000
    step("admin certificates list",
         "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code}")

    # ── 10. Treasury ──────────────────────────────────────────────────────
    print("\nSTAGE 10 · Treasury Dashboard")
    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/treasury/kpis")
    elapsed = (time.monotonic() - t0) * 1000
    step("treasury KPIs", "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code}")
    if r.status_code == 200:
        k = r.json() or {}
        print(f"      → KPIs preview: "
              f"AUM={k.get('aum_uah', k.get('aum'))}  "
              f"transfers_confirmed={k.get('transfers_confirmed', k.get('transfers'))}")

    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/treasury/pulse")
    elapsed = (time.monotonic() - t0) * 1000
    step("treasury pulse", "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code}")

    # ── 11. Beta Command Center (correct prefix: /api/admin/beta) ────────
    print("\nSTAGE 11 · Beta Command Center")
    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/beta/launch-status")
    elapsed = (time.monotonic() - t0) * 1000
    step("launch-status", "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code}")
    if r.status_code == 200:
        ls = r.json() or {}
        cc = ls.get("command_center") or ls
        print(f"      → first_real_money: {cc.get('first_real_money', cc.get('FIRST_REAL_MONEY', 'n/a'))}")
        print(f"      → first_real_investor: {cc.get('first_real_investor', cc.get('FIRST_REAL_INVESTOR', 'n/a'))}")

    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/beta/command-center")
    elapsed = (time.monotonic() - t0) * 1000
    step("command-center", "PASS" if r.status_code == 200 else "FRICT", elapsed,
         f"HTTP {r.status_code}")

    t0 = time.monotonic()
    r = await admin.get(f"{BASE}/api/admin/beta/checklist")
    elapsed = (time.monotonic() - t0) * 1000
    if r.status_code == 200:
        cl = r.json() or {}
        milestones = cl.get("milestones") or cl.get("items") or []
        done = sum(1 for m in milestones if m.get("status") in ("done", "passed", "ok", True))
        step("beta checklist", "PASS", elapsed,
             f"{done}/{len(milestones)} milestones done")
    else:
        step("beta checklist", "FRICT", elapsed, f"HTTP {r.status_code}")

    # ── Summary ────────────────────────────────────────────────────────────
    await admin.aclose(); await inv.aclose()

    print("\n" + "=" * 78)
    print(" REHEARSAL SUMMARY")
    print("=" * 78)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    fricts = sum(1 for r in RESULTS if r["status"] == "FRICT")
    blocks = sum(1 for r in RESULTS if r["status"] == "BLOCK")
    total_ms = sum(r["t_ms"] for r in RESULTS)

    print(f"\n  Steps:       {passed}/{total} PASS · {fricts} FRICTION · {blocks} BLOCKER")
    print(f"  Total time:  {total_ms / 1000:.2f}s  (excluding human-think-time)")

    # Slowest steps
    slowest = sorted(RESULTS, key=lambda r: r["t_ms"], reverse=True)[:5]
    print("\n  Top 5 slowest API calls (operator-felt latency):")
    for r in slowest:
        print(f"    {r['t_ms']:>7.0f}ms  ·  {r['step']}")

    if FRICTIONS:
        print("\n  FRICTION POINTS (manager/admin tupit here):")
        for f in FRICTIONS:
            print(f"    • {f}")

    if BLOCKERS:
        print("\n  BLOCKERS (must fix before real money):")
        for b in BLOCKERS:
            print(f"    • {b}")
    else:
        print("\n  ★ No hard blockers — pipeline is FUNCTIONALLY ready end-to-end.")

    print()


if __name__ == "__main__":
    asyncio.run(main())
