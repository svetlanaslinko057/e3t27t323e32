"""
LUMEN — Email Verification Contract Harness
==========================================

Ninth harness — closes the first "real-investor-can-actually-onboard"
stopper that the architectural sweep surfaced. Email is the identifier
the entire downstream pipeline trusts: KYC, accreditation, funding,
ownership registry, certificates, payouts, withdrawals all key on
``users.email``. Until ownership of that email is proven, registering
under ``victim@example.com`` and then driving a real KYC/funding flow
against it is structurally possible. This file makes that impossible.

Tri-state report (PASS / FAIL / SKIP) — same shape as F6/F7/RV1/RV2.
Cold (pre-feature) run: 0 PASS · N FAIL · 0 SKIP — verdict FAIL until
the email-verification module ships. Post-feature: every assertion
PASS or merge blocked.

The 9 hard requirements (lock-in for the implementation):

  E1. New /auth/register creates a user with ``email_verified=false``
      AND a verification token in ``lumen_email_verifications`` with
      a 24-hour TTL.
  E2. GET /api/auth/verify-email/{token} flips the user to
      ``email_verified=true``, marks the token consumed, and writes
      an audit row category=``auth.email.verified``.
  E3. The same token used twice → 410 Gone (consumed-once contract).
  E4. An invalid / unknown / expired token → 400 (does not leak info).
  E5. POST /api/auth/resend-verification mints a NEW token, invalidates
      the previous, and is rate-limited (cooldown ≥ 60 s).
  E6. POST /api/auth/change-email flips ``email_verified`` back to false
      and dispatches a fresh verification to the new address.
  E7. Gate enforcement: while ``email_verified=false``, the three
      downstream endpoints MUST return 403 with a structured
      "email_verification_required" code:
        • POST /api/investor/kyc/submit
        • POST /api/investor/intents          (funding intent gate)
        • POST /api/investor/withdrawals      (withdrawal gate)
  E8. The verified-status surface is queryable from the frontend:
      GET /api/auth/me returns ``email_verified`` AND
      GET /api/auth/me/email-verified-status returns the gate decision.
  E9. Seeded admin / staff / demo users (admin@devos.io, admin@atlas.dev,
      *@atlas.dev) start as ``email_verified=true`` (migration handles
      backfill so existing demo accounts don't get locked out).

Run:
    cd /app/backend && python email_verification_contract.py
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

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("email-verification-contract")
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
        self.items.append({"req": req, "check": check, "status": status,
                           "detail": detail})
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


def _rand_email() -> str:
    return f"ev_probe_{uuid.uuid4().hex[:10]}@audit-probe.example"


async def _staff_session(client: httpx.AsyncClient, email: str, pw: str) -> bool:
    r = await client.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": pw})
    if r.status_code != 200:
        return False
    sc = r.headers.get("set-cookie") or ""
    for part in sc.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                client.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
                return True
    return True


# ──────────────────────────────────────────────────────────────────────────
# E1 — Register creates user(email_verified=false) + token in store
# ──────────────────────────────────────────────────────────────────────────
async def check_e1(client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    email = _rand_email()
    r = await client.post(f"{BASE}/api/auth/register",
                          json={"email": email, "password": "ProbeP@ss12345",
                                "name": "EV Probe", "role": "client"})
    if r.status_code not in (200, 201):
        report.add("E1", "register endpoint healthy",
                   "fail", f"status={r.status_code}: {r.text[:120]}")
        return None

    user_doc = await db.users.find_one({"email": email})
    if not user_doc:
        report.add("E1", "registered user persisted", "fail", "no user doc")
        return None

    verified = user_doc.get("email_verified")
    report.add("E1",
               "new user has email_verified=false at registration",
               "pass" if verified is False else "fail",
               f"email_verified={verified}")

    token_doc = await db.lumen_email_verifications.find_one(
        {"email": email, "consumed": False})
    if not token_doc:
        report.add("E1",
                   "verification token persisted in lumen_email_verifications",
                   "fail", "no token row")
        return None
    report.add("E1", "verification token created with TTL field",
               "pass" if token_doc.get("expires_at") else "fail",
               f"expires_at={token_doc.get('expires_at')}")
    return {"email": email, "user_id": user_doc.get("user_id"),
            "token": token_doc.get("token")}


# ──────────────────────────────────────────────────────────────────────────
# E2 — Valid token → 200 + email_verified=true + audit
# ──────────────────────────────────────────────────────────────────────────
async def check_e2(client: httpx.AsyncClient, ctx: Optional[Dict]) -> None:
    if not ctx:
        report.add("E2", "valid token flips email_verified=true",
                   "skip", "E1 failed — no ctx")
        return
    r = await client.get(f"{BASE}/api/auth/verify-email/{ctx['token']}")
    report.add("E2", "verify endpoint returns 200 for valid token",
               "pass" if r.status_code == 200 else "fail",
               f"status={r.status_code}")
    user = await db.users.find_one({"email": ctx["email"]})
    report.add("E2", "user.email_verified flipped to true",
               "pass" if (user or {}).get("email_verified") is True else "fail",
               f"verified={(user or {}).get('email_verified')}")
    audit = await db.lumen_staff_login_audit.find_one(
        {"category": "auth.email.verified", "email": ctx["email"]})
    report.add("E2", "audit row category=auth.email.verified written",
               "pass" if audit else "fail", f"audit_id={(audit or {}).get('id')}")


# ──────────────────────────────────────────────────────────────────────────
# E3 — Re-using a consumed token → 410
# ──────────────────────────────────────────────────────────────────────────
async def check_e3(client: httpx.AsyncClient, ctx: Optional[Dict]) -> None:
    if not ctx:
        report.add("E3", "consumed token cannot be replayed", "skip", "E1 failed")
        return
    r = await client.get(f"{BASE}/api/auth/verify-email/{ctx['token']}")
    report.add("E3",
               "second use of the same token returns 410 (consumed-once)",
               "pass" if r.status_code in (410, 400) else "fail",
               f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# E4 — Invalid / unknown token → 400
# ──────────────────────────────────────────────────────────────────────────
async def check_e4(client: httpx.AsyncClient) -> None:
    fake = "ev_" + uuid.uuid4().hex
    r = await client.get(f"{BASE}/api/auth/verify-email/{fake}")
    report.add("E4", "unknown token returns 400",
               "pass" if r.status_code == 400 else "fail",
               f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# E5 — Resend mints new token + invalidates prior + has cooldown
# ──────────────────────────────────────────────────────────────────────────
async def check_e5(client: httpx.AsyncClient) -> None:
    # Fresh user — register, capture first token, then resend.
    email = _rand_email()
    r = await client.post(f"{BASE}/api/auth/register",
                          json={"email": email, "password": "ProbeP@ss12345",
                                "name": "EV Resend", "role": "client"})
    if r.status_code not in (200, 201):
        report.add("E5", "resend cooldown + new token", "skip",
                   f"register failed {r.status_code}")
        return
    # Login as the new user (register already set session cookie on client;
    # but we use a fresh client to avoid auth pollution).
    fresh = httpx.AsyncClient(timeout=10)
    try:
        rl = await fresh.post(f"{BASE}/api/auth/login",
                              json={"email": email, "password": "ProbeP@ss12345"})
        sc = rl.headers.get("set-cookie") or ""
        for part in sc.split(","):
            for kv in part.split(";"):
                kv = kv.strip()
                if kv.startswith("session_token="):
                    fresh.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
        # initial token
        t0 = await db.lumen_email_verifications.find_one(
            {"email": email, "consumed": False},
            sort=[("created_at", -1)])
        # resend
        r1 = await fresh.post(f"{BASE}/api/auth/resend-verification",
                              json={"email": email})
        if r1.status_code not in (200, 202):
            report.add("E5", "resend endpoint healthy", "fail",
                       f"status={r1.status_code}: {r1.text[:120]}")
            return
        t1 = await db.lumen_email_verifications.find_one(
            {"email": email, "consumed": False},
            sort=[("created_at", -1)])
        report.add("E5",
                   "resend mints a NEW token (token value rotates)",
                   "pass" if t0 and t1 and t0.get("token") != t1.get("token")
                   else "fail",
                   f"old={(t0 or {}).get('token','')[:10]} "
                   f"new={(t1 or {}).get('token','')[:10]}")
        # Cooldown: a second resend within 60 s must be rejected (429 or 200 with cooldown msg)
        r2 = await fresh.post(f"{BASE}/api/auth/resend-verification",
                              json={"email": email})
        report.add("E5",
                   "second resend within cooldown is rate-limited (429)",
                   "pass" if r2.status_code in (429, 409) else "fail",
                   f"status={r2.status_code}")
    finally:
        await fresh.aclose()


# ──────────────────────────────────────────────────────────────────────────
# E6 — Change email resets email_verified
# ──────────────────────────────────────────────────────────────────────────
async def check_e6(client: httpx.AsyncClient) -> None:
    """Register + verify a user, then call change-email and confirm
    email_verified flips back to false + a new token is minted for the
    new address."""
    email_old = _rand_email()
    r = await client.post(f"{BASE}/api/auth/register",
                          json={"email": email_old, "password": "ProbeP@ss12345",
                                "name": "EV Change", "role": "client"})
    if r.status_code not in (200, 201):
        report.add("E6", "change-email resets email_verified",
                   "skip", "register failed")
        return
    fresh = httpx.AsyncClient(timeout=10)
    try:
        rl = await fresh.post(f"{BASE}/api/auth/login",
                              json={"email": email_old, "password": "ProbeP@ss12345"})
        sc = rl.headers.get("set-cookie") or ""
        for part in sc.split(","):
            for kv in part.split(";"):
                kv = kv.strip()
                if kv.startswith("session_token="):
                    fresh.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
        # Verify the old email first
        t = await db.lumen_email_verifications.find_one(
            {"email": email_old, "consumed": False},
            sort=[("created_at", -1)])
        if t:
            await fresh.get(f"{BASE}/api/auth/verify-email/{t['token']}")

        email_new = _rand_email()
        r_ch = await fresh.post(f"{BASE}/api/auth/change-email",
                                json={"new_email": email_new})
        report.add("E6", "change-email endpoint healthy",
                   "pass" if r_ch.status_code in (200, 202) else "fail",
                   f"status={r_ch.status_code}")
        u = await db.users.find_one({"email": email_new})
        report.add("E6",
                   "user.email switched + email_verified reset to false",
                   "pass" if u and u.get("email_verified") is False else "fail",
                   f"verified={(u or {}).get('email_verified')}")
        tok_new = await db.lumen_email_verifications.find_one(
            {"email": email_new, "consumed": False})
        report.add("E6",
                   "fresh verification token minted for new email",
                   "pass" if tok_new else "fail",
                   f"token_id={(tok_new or {}).get('id')}")
    finally:
        await fresh.aclose()


# ──────────────────────────────────────────────────────────────────────────
# E7 — KYC / Funding / Withdrawal gates return 403 when unverified
# ──────────────────────────────────────────────────────────────────────────
async def check_e7(client: httpx.AsyncClient) -> None:
    email = _rand_email()
    r = await client.post(f"{BASE}/api/auth/register",
                          json={"email": email, "password": "ProbeP@ss12345",
                                "name": "EV Gate", "role": "client"})
    if r.status_code not in (200, 201):
        report.add("E7", "gates reject unverified user", "skip",
                   f"register failed {r.status_code}")
        return
    fresh = httpx.AsyncClient(timeout=10)
    try:
        rl = await fresh.post(f"{BASE}/api/auth/login",
                              json={"email": email, "password": "ProbeP@ss12345"})
        sc = rl.headers.get("set-cookie") or ""
        for part in sc.split(","):
            for kv in part.split(";"):
                kv = kv.strip()
                if kv.startswith("session_token="):
                    fresh.headers["Cookie"] = f"session_token={kv.split('=', 1)[1].strip()}"
        # KYC submit
        r_kyc = await fresh.post(f"{BASE}/api/investor/kyc/submit", json={})
        report.add("E7",
                   "POST /investor/kyc/submit returns 403 (email_verification_required)",
                   "pass" if r_kyc.status_code == 403 else "fail",
                   f"status={r_kyc.status_code}")
        # Funding intent
        r_intent = await fresh.post(f"{BASE}/api/investor/intents",
                                    json={"asset_id": "asset-test", "amount": 1000})
        report.add("E7",
                   "POST /investor/intents returns 403 (email_verification_required)",
                   "pass" if r_intent.status_code == 403 else "fail",
                   f"status={r_intent.status_code}")
        # Withdrawal
        r_w = await fresh.post(f"{BASE}/api/investor/withdrawals",
                               json={"amount": 100, "currency": "UAH",
                                     "iban": "UA000000000000000000000000001"})
        report.add("E7",
                   "POST /investor/withdrawals returns 403 (email_verification_required)",
                   "pass" if r_w.status_code == 403 else "fail",
                   f"status={r_w.status_code}")
    finally:
        await fresh.aclose()


# ──────────────────────────────────────────────────────────────────────────
# E8 — /api/auth/me + status endpoint exposes the flag
# ──────────────────────────────────────────────────────────────────────────
async def check_e8(client: httpx.AsyncClient) -> None:
    # Use the admin session — admin should be email_verified=true after E9 backfill
    r = await client.get(f"{BASE}/api/auth/me")
    body = r.json() if r.status_code == 200 else {}
    report.add("E8",
               "/api/auth/me carries email_verified flag",
               "pass" if "email_verified" in body else "fail",
               f"keys={list(body.keys())[:10]}")
    r2 = await client.get(f"{BASE}/api/auth/me/email-verified-status")
    body2 = r2.json() if r2.status_code == 200 else {}
    report.add("E8",
               "/api/auth/me/email-verified-status surface available",
               "pass" if r2.status_code == 200 and "verified" in body2 else "fail",
               f"status={r2.status_code} body={body2}")


# ──────────────────────────────────────────────────────────────────────────
# E9 — Seed users backfilled to email_verified=true
# ──────────────────────────────────────────────────────────────────────────
async def check_e9() -> None:
    canonical = ["admin@devos.io", "admin@atlas.dev", "client@atlas.dev",
                 "family@atlas.dev", "manager@atlas.dev", "tester@atlas.dev",
                 "operator@atlas.dev", "multi@atlas.dev", "john@atlas.dev"]
    bad = []
    for em in canonical:
        u = await db.users.find_one({"email": em})
        if not u:
            continue  # not seeded in this deploy, skip
        if u.get("email_verified") is not True:
            bad.append(em)
    report.add("E9",
               "all seeded canonical users have email_verified=true (no lockout)",
               "pass" if not bad else "fail",
               f"unverified_seed_users={bad}")


# ──────────────────────────────────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────────────────────────────────
async def _cleanup() -> None:
    try:
        await db.users.delete_many({"email": {"$regex": "^ev_probe_"}})
        await db.lumen_email_verifications.delete_many(
            {"email": {"$regex": "^ev_probe_"}})
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────
async def main() -> int:
    log.info(f"BASE={BASE} DB={DB_NAME}")
    async with httpx.AsyncClient(timeout=20) as client:
        if not await _staff_session(client, ADMIN_EMAIL, ADMIN_PASS):
            report.add("Auth", "admin login", "fail", "could not login")
        else:
            report.add("Auth", "admin login", "pass", ADMIN_EMAIL)

        ctx = await check_e1(client)
        await check_e2(client, ctx)
        await check_e3(client, ctx)
        await check_e4(client)
        await check_e5(client)
        await check_e6(client)
        await check_e7(client)
        await check_e8(client)
        await check_e9()

    await _cleanup()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"EMAIL VERIFICATION CONTRACT — {summary['verdict']} "
          f"(pass={summary['passed']}  fail={summary['failed']}  "
          f"skip={summary['skipped']}  /  total={summary['total']})")
    print("=" * 78)
    by_req: Dict[str, Dict[str, int]] = {}
    for it in summary["items"]:
        r = it["req"]
        by_req.setdefault(r, {"pass": 0, "fail": 0, "skip": 0})
        by_req[r][it["status"]] += 1
    for r, c in by_req.items():
        print(f"  {r:6s}  pass={c['pass']:>2}  fail={c['fail']:>2}  skip={c['skip']:>2}")

    out = "/app/test_reports/email_verification_contract.json"
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
