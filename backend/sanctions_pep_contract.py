"""
LUMEN — Sanctions + PEP + Risk + AML Contract Harness
=====================================================

Tenth harness — locks ТЗ Level-B (Compliance). Same tri-state shape as
email_verification_contract / F6 / F7 / RV1 / RV2.

The 9 hard requirements:

  S1. Consolidated watchlist seeded with entries from OFAC + EU + UK +
      Ukraine(NSDC) + PEP (each source > 0).
  S2. A known sanctioned name screens to a CONFIRMED match → risk CRITICAL.
  S3. A clean random name → no match (decision=clear) → risk LOW/MEDIUM.
  S4. KYC submit triggers screening → a screening_result is written AND a
      compliance case is opened for a hit/high-risk subject.
  S5. A PEP-listed subject → pep_hit=true → risk band ≥ HIGH.
  S6. Risk scoring honours jurisdiction (high-risk country bump) AND
      transaction size (large tx bumps the band).
  S7. Funding intent for a sanction-blocked investor → 403 compliance_block.
  S8. AML audit trail is append-only (who/what/when/why) AND an admin case
      decision writes an AML audit row.
  S9. Admin review queue + decision endpoint (clear/escalate/block) work, and
      the watchlist is queryable.

Run:
    cd /app/backend && python sanctions_pep_contract.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("AUDIT_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ.get("AUDIT_ADMIN_EMAIL", "admin@devos.io")
ADMIN_PASS = os.environ.get("AUDIT_ADMIN_PASS", "admin123")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sanctions-pep-contract")
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Report:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []
        self.fail_count = 0
        self.skip_count = 0

    def add(self, req: str, check: str, status: str, detail: str = "") -> None:
        self.items.append({"req": req, "check": check, "status": status, "detail": detail})
        flag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
        log.info(f"[{flag}] {req} :: {check} {('— ' + detail) if detail else ''}")
        if status == "fail":
            self.fail_count += 1
        elif status == "skip":
            self.skip_count += 1

    def summary(self) -> Dict[str, Any]:
        total = len(self.items)
        passed = sum(1 for i in self.items if i["status"] == "pass")
        verdict = "PASS" if self.fail_count == 0 else "FAIL"
        return {"total": total, "passed": passed, "failed": self.fail_count,
                "skipped": self.skip_count, "verdict": verdict,
                "items": self.items, "generated_at": _utc()}


report = Report()


async def _admin_session(client: httpx.AsyncClient) -> bool:
    r = await client.post(f"{BASE}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        return False
    sc = r.headers.get("set-cookie") or ""
    for part in sc.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                client.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
    return True


def _rand_email() -> str:
    return f"spep_probe_{uuid.uuid4().hex[:10]}@audit-probe.example"


async def _make_verified_investor(name: str, country: str = "UA") -> Dict[str, Any]:
    """Register + verify (DB flip) an investor; return a logged-in client + ids."""
    email = _rand_email()
    async with httpx.AsyncClient(timeout=15) as reg:
        r = await reg.post(f"{BASE}/api/auth/register",
                           json={"email": email, "password": "ProbeP@ss12345",
                                 "name": name, "role": "client"})
    u = await db.users.find_one({"email": email})
    if not u:
        return {}
    # bypass email gate for the test
    await db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    client = httpx.AsyncClient(timeout=15)
    rl = await client.post(f"{BASE}/api/auth/login",
                           json={"email": email, "password": "ProbeP@ss12345"})
    sc = rl.headers.get("set-cookie") or ""
    for part in sc.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                client.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
    # Ensure the profile row exists (API assigns its `id`), then set fields
    # WITHOUT upsert so we never create an id:null duplicate.
    await client.get(f"{BASE}/api/investor/profile")
    await db.lumen_investor_profiles.update_one(
        {"user_id": u["user_id"]},
        {"$set": {"full_name": name, "residency_country": country,
                  "country": country, "date_of_birth": "1970-01-01",
                  "kyc_status": "draft"}})
    return {"client": client, "email": email, "user_id": u["user_id"]}


# ── S1 — consolidated list seeded ──────────────────────────────────────────
async def check_s1(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/api/admin/compliance/watchlist")
    if r.status_code != 200:
        report.add("S1", "watchlist endpoint healthy", "fail", f"status={r.status_code}")
        return
    by_source = r.json().get("by_source", {})
    for src in ("ofac", "eu", "uk", "ua_nsdc", "pep"):
        report.add("S1", f"watchlist has {src} entries",
                   "pass" if by_source.get(src, 0) > 0 else "fail",
                   f"count={by_source.get(src, 0)}")


# ── S2 — known sanctioned name → confirmed → CRITICAL ──────────────────────
async def check_s2(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{BASE}/api/admin/compliance/screen",
                          json={"name": "Stanislav Sanctiontest Blockov", "country": "RU"})
    if r.status_code != 200:
        report.add("S2", "manual screen endpoint healthy", "fail", f"status={r.status_code}")
        return
    body = r.json()
    report.add("S2", "known sanctioned name → confirmed_match",
               "pass" if body.get("decision") == "confirmed_match" else "fail",
               f"decision={body.get('decision')} top={body.get('top_score')}")
    report.add("S2", "confirmed sanction → risk band CRITICAL",
               "pass" if body.get("risk_band") == "CRITICAL" else "fail",
               f"risk={body.get('risk_band')}")


# ── S3 — clean name → clear → LOW/MEDIUM ───────────────────────────────────
async def check_s3(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{BASE}/api/admin/compliance/screen",
                          json={"name": "Olha Tymchenko Bezdoganna", "country": "UA"})
    body = r.json() if r.status_code == 200 else {}
    report.add("S3", "clean name → decision=clear",
               "pass" if body.get("decision") == "clear" else "fail",
               f"decision={body.get('decision')} matches={len(body.get('matches', []))}")
    report.add("S3", "clean UA name → risk LOW/MEDIUM",
               "pass" if body.get("risk_band") in ("LOW", "MEDIUM") else "fail",
               f"risk={body.get('risk_band')}")


# ── S4 — KYC submit triggers screening + opens a case ──────────────────────
async def check_s4() -> Optional[str]:
    ctx = await _make_verified_investor("Stanislav Sanctiontest Blockov", country="RU")
    if not ctx:
        report.add("S4", "KYC submit triggers screening", "skip", "investor setup failed")
        return None
    client = ctx["client"]
    uid = ctx["user_id"]
    try:
        # Complete the KYC so submit() succeeds and the screening hook fires:
        # all required profile fields + the two required document rows.
        await db.lumen_investor_profiles.update_one(
            {"user_id": uid},
            {"$set": {"full_name": "Stanislav Sanctiontest Blockov",
                      "date_of_birth": "1970-01-01", "country": "RU",
                      "residency_country": "RU", "tax_id": "1234567890",
                      "iban": "UA213223130000026007233566001",
                      "kyc_status": "draft"}})
        for dt in ("passport", "tax_id"):
            await db.lumen_kyc_documents.insert_one({
                "id": str(uuid.uuid4()), "investor_id": uid, "doc_type": dt,
                "filename": f"{dt}.pdf", "content_type": "application/pdf",
                "size_bytes": 1024, "storage_path": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)})
        r = await client.post(f"{BASE}/api/investor/kyc/submit", json={})
        # screening must have written a result for this subject
        res = await db.lumen_screening_results.find_one(
            {"subject_id": uid, "triggered_by": "kyc_submit"})
        report.add("S4", "kyc_submit wrote a screening_result",
                   "pass" if res else "fail",
                   f"submit_status={r.status_code} result_id={(res or {}).get('id')}")
        case = await db.lumen_compliance_cases.find_one({"investor_id": uid})
        report.add("S4", "sanction hit at KYC opens a compliance case",
                   "pass" if case else "fail", f"case_id={(case or {}).get('id')}")
        return uid
    finally:
        await client.aclose()


# ── S5 — PEP subject → pep_hit + risk ≥ HIGH ───────────────────────────────
async def check_s5(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{BASE}/api/admin/compliance/screen",
                          json={"name": "Petro Peptest Politov", "country": "UA"})
    body = r.json() if r.status_code == 200 else {}
    report.add("S5", "PEP-listed name → pep_hit=true",
               "pass" if body.get("pep_hit") is True else "fail",
               f"pep_hit={body.get('pep_hit')}")
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    report.add("S5", "PEP subject → risk band ≥ HIGH",
               "pass" if order.get(body.get("risk_band"), 0) >= 2 else "fail",
               f"risk={body.get('risk_band')}")


# ── S6 — risk scoring: jurisdiction + transaction size ─────────────────────
async def check_s6(client: httpx.AsyncClient) -> None:
    # clean name in a high-risk jurisdiction → ≥ HIGH
    r1 = await client.post(f"{BASE}/api/admin/compliance/screen",
                           json={"name": "Olha Tymchenko Bezdoganna", "country": "IR"})
    b1 = r1.json() if r1.status_code == 200 else {}
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    report.add("S6", "high-risk jurisdiction bumps band to ≥ HIGH",
               "pass" if order.get(b1.get("risk_band"), 0) >= 2 else "fail",
               f"country=IR risk={b1.get('risk_band')}")
    # clean low-risk name with a very large transaction → bumped above LOW
    r2 = await client.post(f"{BASE}/api/admin/compliance/screen",
                           json={"name": "Olha Tymchenko Bezdoganna", "country": "UA",
                                 "amount_uah": 5000000})
    b2 = r2.json() if r2.status_code == 200 else {}
    report.add("S6", "very-large transaction bumps risk above LOW",
               "pass" if order.get(b2.get("risk_band"), 0) >= 1 else "fail",
               f"amount=5M risk={b2.get('risk_band')} reasons={b2.get('risk_reasons')}")


# ── S7 — funding intent blocked for sanctioned investor ────────────────────
async def check_s7() -> None:
    ctx = await _make_verified_investor("Stanislav Sanctiontest Blockov", country="RU")
    if not ctx:
        report.add("S7", "funding intent blocked for sanctioned investor", "skip",
                   "investor setup failed")
        return
    client = ctx["client"]
    try:
        # force a screening (kyc submit) so the block is established
        await client.post(f"{BASE}/api/investor/kyc/submit", json={})
        r = await client.post(f"{BASE}/api/investor/intents",
                              json={"asset_id": "asset-podilskyi", "amount": 100000})
        ok = r.status_code == 403
        detail = ""
        try:
            detail = json.dumps(r.json())[:160]
        except Exception:
            detail = r.text[:160]
        report.add("S7", "POST /investor/intents → 403 compliance_block for sanctioned investor",
                   "pass" if ok else "fail", f"status={r.status_code} {detail}")
    finally:
        await client.aclose()


# ── S8 — AML audit append-only + decision writes a row ─────────────────────
async def check_s8(client: httpx.AsyncClient) -> None:
    # there must be AML rows from earlier screenings
    r = await client.get(f"{BASE}/api/admin/compliance/aml-audit?limit=50")
    body = r.json() if r.status_code == 200 else {}
    items = body.get("items", [])
    has_fields = bool(items) and all(
        all(k in items[0] for k in ("actor", "action", "at", "reason"))
        for _ in [0])
    report.add("S8", "AML journal exposes who/what/when/why",
               "pass" if items and has_fields else "fail",
               f"n={len(items)} keys={list(items[0].keys()) if items else []}")
    # append-only: no update route exists; verify count only grows after a decision
    before = await db.lumen_aml_audit.count_documents({})
    # find any open case and decide it
    rc = await client.get(f"{BASE}/api/admin/compliance/cases?status=blocked")
    cases = rc.json().get("items", []) if rc.status_code == 200 else []
    if not cases:
        rc2 = await client.get(f"{BASE}/api/admin/compliance/cases?status=open")
        cases = rc2.json().get("items", []) if rc2.status_code == 200 else []
    if cases:
        cid = cases[0]["id"]
        rd = await client.post(f"{BASE}/api/admin/compliance/cases/{cid}/decision",
                               json={"decision": "escalate", "reason": "contract probe"})
        after = await db.lumen_aml_audit.count_documents({})
        report.add("S8", "admin case decision appends an AML audit row",
                   "pass" if (rd.status_code == 200 and after > before) else "fail",
                   f"status={rd.status_code} before={before} after={after}")
    else:
        report.add("S8", "admin case decision appends an AML audit row", "fail",
                   "no case available to decide")


# ── S9 — review queue + decision + watchlist queryable ─────────────────────
async def check_s9(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/api/admin/compliance/dashboard")
    body = r.json() if r.status_code == 200 else {}
    report.add("S9", "compliance dashboard returns case + watchlist rollups",
               "pass" if r.status_code == 200 and "cases_by_status" in body else "fail",
               f"status={r.status_code} open_cases={body.get('open_cases')}")
    rq = await client.get(f"{BASE}/api/admin/compliance/cases")
    report.add("S9", "review queue (cases list) queryable",
               "pass" if rq.status_code == 200 and "items" in rq.json() else "fail",
               f"status={rq.status_code} n={len(rq.json().get('items', []))}")
    # clear decision closes a case
    cases = rq.json().get("items", []) if rq.status_code == 200 else []
    open_cases = [c for c in cases if c.get("status") in ("open", "in_review", "escalated")]
    if open_cases:
        cid = open_cases[0]["id"]
        rd = await client.post(f"{BASE}/api/admin/compliance/cases/{cid}/decision",
                               json={"decision": "clear", "reason": "contract probe clear"})
        ok = rd.status_code == 200 and rd.json().get("case", {}).get("status") == "cleared"
        report.add("S9", "decision clear → case status=cleared",
                   "pass" if ok else "fail", f"status={rd.status_code}")
    else:
        report.add("S9", "decision clear → case status=cleared", "skip", "no open case")


async def _cleanup() -> None:
    try:
        await db.users.delete_many({"email": {"$regex": "^spep_probe_"}})
    except Exception:
        pass


async def main() -> int:
    log.info(f"BASE={BASE} DB={DB_NAME}")
    async with httpx.AsyncClient(timeout=30) as client:
        if not await _admin_session(client):
            report.add("Auth", "admin login", "fail", "could not login")
            print(json.dumps(report.summary(), indent=2))
            return 2
        report.add("Auth", "admin login", "pass", ADMIN_EMAIL)

        await check_s1(client)
        await check_s2(client)
        await check_s3(client)
        await check_s4()
        await check_s5(client)
        await check_s6(client)
        await check_s7()
        await check_s8(client)
        await check_s9(client)

    await _cleanup()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"SANCTIONS + PEP + RISK + AML CONTRACT — {summary['verdict']} "
          f"(pass={summary['passed']}  fail={summary['failed']}  "
          f"skip={summary['skipped']}  /  total={summary['total']})")
    print("=" * 78)
    by_req: Dict[str, Dict[str, int]] = {}
    for it in summary["items"]:
        rq = it["req"]
        by_req.setdefault(rq, {"pass": 0, "fail": 0, "skip": 0})
        by_req[rq][it["status"]] += 1
    for rq, c in by_req.items():
        print(f"  {rq:6s}  pass={c['pass']:>2}  fail={c['fail']:>2}  skip={c['skip']:>2}")

    out = "/app/test_reports/sanctions_pep_contract.json"
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log.info(f"report → {out}")
    except Exception as e:
        log.warning(f"write report failed: {e}")
    return 0 if summary["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
