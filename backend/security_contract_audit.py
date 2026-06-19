"""
LUMEN — Security Contract Audit
================================

Fourth harness. Lifecycle / Infra / Communication audits prove the system
**works**; this one proves it **refuses**.

Security in LUMEN is spread across:
    • IR endpoints (require_staff / require_admin)
    • F3 staff sessions (cookie session_token, revoke endpoints)
    • Access Gate (rate limiting + blocks)
    • 2FA (verify, challenges, trusted devices)
    • Session Layer (httpOnly cookies, Secure+SameSite=none)
    • Public Contract View Tokens (signed, expiring)
    • F4 instructions (admin author / manager read)
    • F5 communication core (staff for /comms/send + ingest)
    • F2 site activity (auth-free track + identify, admin-only analytics)

This audit certifies the **negative contract**: every endpoint that
SHOULDN'T let you in, doesn't. Critical before opening F6 Gmail (OAuth
callback + signed webhook = external attack surface).

Run:
    cd /app/backend && python security_contract_audit.py

Non-destructive: only logs in as existing seed users, exercises forbidden
calls, asserts they're rejected.
"""
from __future__ import annotations

import os
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("AUDIT_BASE_URL", "http://localhost:8001")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sec-audit")
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]

# Seeded credentials (see server.py demo seed)
CREDS = {
    "admin":     ("admin@devos.io",   "admin123"),
    "admin2":    ("admin@atlas.dev",  "admin123"),
    "manager":   ("manager@atlas.dev", "manager123"),
    "developer": ("john@atlas.dev",    "dev123"),
    "client":    ("client@atlas.dev",  "client123"),
    "tester":    ("tester@atlas.dev",  "tester123"),
}

REJECT = {401, 403, 404}   # acceptable "denied" responses


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Report:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []
        self.fail_count = 0
        self.warn_count = 0

    def add(self, section: str, check: str, ok: bool, detail: str = "",
            severity: str = "fail") -> None:
        self.items.append({"section": section, "check": check, "ok": ok,
                           "detail": detail,
                           "severity": "info" if ok else severity})
        flag = "PASS" if ok else ("WARN" if severity == "warn" else "FAIL")
        log.info(f"[{flag}] {section} :: {check} {('— ' + detail) if detail else ''}")
        if not ok:
            if severity == "warn":
                self.warn_count += 1
            else:
                self.fail_count += 1

    def summary(self) -> Dict[str, Any]:
        total = len(self.items)
        passed = total - self.fail_count - self.warn_count
        by_section: Dict[str, Dict[str, int]] = {}
        for it in self.items:
            s = it["section"]
            by_section.setdefault(s, {"pass": 0, "fail": 0, "warn": 0})
            if it["ok"]:
                by_section[s]["pass"] += 1
            elif it["severity"] == "warn":
                by_section[s]["warn"] += 1
            else:
                by_section[s]["fail"] += 1
        return {
            "total": total, "passed": passed,
            "failed": self.fail_count, "warned": self.warn_count,
            "by_section": by_section, "items": self.items,
            "verdict": "PASS" if self.fail_count == 0 else "FAIL",
            "generated_at": _utc(),
        }


report = Report()


# ──────────────────────────────────────────────────────────────────────────
# Auth helpers — each role gets its own httpx client with pinned cookie
# ──────────────────────────────────────────────────────────────────────────
async def login_as(role: str) -> Optional[httpx.AsyncClient]:
    email, pwd = CREDS[role]
    client = httpx.AsyncClient(timeout=15, follow_redirects=False)
    r = await client.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": pwd})
    if r.status_code != 200:
        await client.aclose()
        return None
    sc = r.headers.get("set-cookie") or ""
    token = None
    for part in sc.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                token = kv.split("=", 1)[1].strip()
                break
        if token:
            break
    if token:
        client.headers["Cookie"] = f"session_token={token}"
        client._lumen_token = token  # type: ignore[attr-defined]
    return client


# Role-keyed client cache to avoid tripping login rate limit (which the
# audit itself verifies in the last section).
_ROLE_CLIENTS: Dict[str, Optional[httpx.AsyncClient]] = {}


async def get_role_client(role: str) -> Optional[httpx.AsyncClient]:
    if role not in _ROLE_CLIENTS:
        _ROLE_CLIENTS[role] = await login_as(role)
        # tiny gap so the limiter window doesn't burn in a tight loop
        await asyncio.sleep(0.05)
    return _ROLE_CLIENTS[role]


async def close_role_clients() -> None:
    for c in _ROLE_CLIENTS.values():
        if c:
            try:
                await c.aclose()
            except Exception:
                pass


def anon_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15, follow_redirects=False)


# ──────────────────────────────────────────────────────────────────────────
# Section 1 — Unauthenticated reject
# ──────────────────────────────────────────────────────────────────────────
ANON_REJECT_GETS = [
    "/api/admin/ir/leads",
    "/api/admin/ir/pipeline",
    "/api/admin/ir/overview",
    "/api/admin/managers",
    "/api/admin/manager-os/snapshot",
    "/api/admin/funnel/dashboard",
    "/api/admin/comms/feed",
    "/api/admin/comms/stats",
    "/api/admin/comms/providers",
    "/api/admin/activity/live",
    "/api/admin/activity/overview",
    "/api/admin/manager/instructions-overview",
    "/api/admin/staff/sessions/list",
    "/api/admin/staff/sessions/online",
    "/api/manager/instructions",
]


async def verify_anonymous_reject() -> None:
    log.info("≡ Section 1 / unauthenticated reject")
    async with anon_client() as c:
        for path in ANON_REJECT_GETS:
            r = await c.get(f"{BASE}{path}")
            report.add("Anonymous reject",
                       f"GET {path}",
                       r.status_code in REJECT,
                       f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 2 — Privilege escalation (non-admin / non-staff)
# ──────────────────────────────────────────────────────────────────────────
ADMIN_ONLY_PROBES = [
    ("GET",  "/api/admin/managers"),
    ("POST", "/api/admin/comms/providers", {"key": "gmail"}),
    ("POST", "/api/admin/manager/instructions",
     {"title": "evil", "body": "x", "category": "general", "status": "draft"}),
    ("POST", "/api/admin/activity/rollup"),
    ("GET",  "/api/admin/staff/sessions/suspicious"),
]


async def _probe(client: httpx.AsyncClient, method: str, path: str,
                 body: Optional[dict] = None) -> int:
    if method == "GET":
        r = await client.get(f"{BASE}{path}")
    elif method == "POST":
        r = await client.post(f"{BASE}{path}", json=body or {})
    elif method == "PATCH":
        r = await client.patch(f"{BASE}{path}", json=body or {})
    elif method == "DELETE":
        r = await client.delete(f"{BASE}{path}")
    else:
        return 0
    return r.status_code


async def verify_privilege_escalation() -> None:
    log.info("≡ Section 2 / privilege escalation (client / developer / tester)")
    for role in ("client", "developer", "tester"):
        client = await get_role_client(role)
        if not client:
            report.add("Privilege Escalation", f"{role} login OK", False,
                       "could not login")
            continue
        for probe in ADMIN_ONLY_PROBES:
            m, p = probe[0], probe[1]
            body = probe[2] if len(probe) > 2 else None
            code = await _probe(client, m, p, body)
            report.add("Privilege Escalation",
                       f"{role} {m} {p}",
                       code in REJECT,
                       f"status={code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 3 — Staff vs Admin separation
# ──────────────────────────────────────────────────────────────────────────
# manager can hit require_staff endpoints but NOT require_admin ones.
async def verify_staff_vs_admin() -> None:
    log.info("≡ Section 3 / staff vs admin separation")
    client = await get_role_client("manager")
    if not client:
        report.add("Staff/Admin", "manager login", False, "login failed")
        return
    # SHOULD pass — staff scope
    for p in ["/api/admin/ir/leads",
              "/api/admin/comms/feed",
              "/api/admin/comms/stats",
              "/api/manager/instructions"]:
        r = await client.get(f"{BASE}{p}")
        report.add("Staff/Admin",
                   f"manager CAN GET {p}",
                   r.status_code == 200,
                   f"status={r.status_code}")

    # SHOULD reject — admin-only
    for probe in [
        ("POST", "/api/admin/manager/instructions",
         {"title": "x", "body": "x", "category": "general", "status": "draft"}),
        ("PATCH", "/api/admin/comms/providers/gmail",
         {"status": "disabled"}),
        ("POST", "/api/admin/activity/rollup"),
    ]:
        code = await _probe(client, probe[0], probe[1],
                            probe[2] if len(probe) > 2 else None)
        report.add("Staff/Admin",
                   f"manager CANNOT {probe[0]} {probe[1]}",
                   code in REJECT,
                   f"status={code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 4 — Session revocation enforcement
# ──────────────────────────────────────────────────────────────────────────
async def verify_session_revocation() -> None:
    log.info("≡ Section 4 / session revocation")
    # Admin logs in twice — first cookie used to revoke the second cookie.
    admin1 = await login_as("admin")
    admin2 = await login_as("admin")
    if not admin1 or not admin2:
        report.add("Revocation", "admin double-login", False, "login failed")
        if admin1:
            await admin1.aclose()
        if admin2:
            await admin2.aclose()
        return
    try:
        token2 = admin2._lumen_token  # type: ignore[attr-defined]
        # Confirm admin2 works first
        r = await admin2.get(f"{BASE}/api/admin/ir/leads")
        report.add("Revocation", "fresh admin session works",
                   r.status_code == 200, f"status={r.status_code}")
        # Find admin2's session row in mongo to revoke by session_id
        sess = None
        for coll in ["user_sessions", "lumen_user_sessions",
                     "lumen_staff_sessions"]:
            try:
                sess = await db[coll].find_one({"session_token": token2})
                if sess:
                    break
            except Exception:
                pass
        if not sess:
            report.add("Revocation",
                       "find session row in DB by session_token",
                       False, f"token={token2[:12]}…")
            return
        sid = sess.get("session_id") or sess.get("id")
        if not sid:
            report.add("Revocation",
                       "session row carries session_id",
                       False, "no session_id field")
            return
        # Admin1 revokes admin2's session via F3 endpoint
        r = await admin1.post(
            f"{BASE}/api/admin/staff/sessions/{sid}/revoke",
            json={"reason": "security-audit-probe"})
        report.add("Revocation", "POST revoke succeeds",
                   r.status_code == 200, f"status={r.status_code}")
        # Now admin2 must be locked out
        r = await admin2.get(f"{BASE}/api/admin/ir/leads")
        report.add("Revocation",
                   "revoked session is rejected on next call",
                   r.status_code in REJECT,
                   f"status={r.status_code}")
    finally:
        if admin1:
            await admin1.aclose()
        if admin2:
            await admin2.aclose()


# ──────────────────────────────────────────────────────────────────────────
# Section 5 — Public Contract View Tokens
# ──────────────────────────────────────────────────────────────────────────
async def verify_contract_tokens() -> None:
    log.info("≡ Section 5 / public contract view tokens")
    async with anon_client() as c:
        # Random bogus token
        r = await c.get(f"{BASE}/api/contracts/view/{'x' * 24}")
        report.add("Contract Tokens",
                   "bogus token → 404/410/403",
                   r.status_code in {403, 404, 410},
                   f"status={r.status_code}")
        # Empty / clearly malicious token
        r = await c.get(f"{BASE}/api/contracts/view/__invalid__")
        report.add("Contract Tokens",
                   "malformed token → not 200",
                   r.status_code != 200, f"status={r.status_code}")
        # Sign endpoint must reject without a real token
        r = await c.post(f"{BASE}/api/contracts/view/x{'a'*16}/sign",
                         json={"otp": "000000"})
        report.add("Contract Tokens",
                   "sign endpoint on bogus token rejects",
                   r.status_code in {400, 401, 403, 404, 410, 422},
                   f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 6 — CSP report endpoint is public BUT cannot read back
# ──────────────────────────────────────────────────────────────────────────
async def verify_csp_endpoints() -> None:
    log.info("≡ Section 6 / CSP intake")
    async with anon_client() as c:
        # POST is public by design (browsers send unauthenticated)
        r = await c.post(f"{BASE}/api/security/csp-report",
                         json={"csp-report": {"document-uri": "https://x/y",
                                              "violated-directive": "img-src",
                                              "blocked-uri": "https://z"}})
        report.add("CSP", "anon POST accepted",
                   r.status_code in {200, 201, 204}, f"status={r.status_code}")
        # Anon cannot LIST reports (no public list endpoint expected)
        for p in ["/api/security/csp-reports",
                  "/api/admin/security/csp-reports"]:
            r = await c.get(f"{BASE}{p}")
            # ok = either not_found (no endpoint) or properly gated
            report.add("CSP",
                       f"anon GET {p} NOT 200",
                       r.status_code != 200, f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 7 — Communication ownership leaks
# ──────────────────────────────────────────────────────────────────────────
async def verify_comms_scope() -> None:
    log.info("≡ Section 7 / communication scope")
    # Anonymous cannot send / ingest / read feed
    async with anon_client() as c:
        for path, method, body in [
            ("/api/comms/send", "POST",
             {"provider": "manual", "interaction_type": "note",
              "direction": "outbound", "body": "leak"}),
            ("/api/comms/ingest", "POST",
             {"provider": "gmail", "interaction_type": "email",
              "direction": "inbound", "contact": "x@example.com"}),
            ("/api/admin/comms/feed", "GET", None),
        ]:
            code = await _probe(c, method, path, body)
            report.add("Comm Scope",
                       f"anon {method} {path} rejected",
                       code in REJECT, f"status={code}")

    # client / developer / tester (non-staff) cannot either
    for role in ("client", "developer", "tester"):
        client = await get_role_client(role)
        if not client:
            continue
        for path, method, body in [
            ("/api/comms/send", "POST",
             {"provider": "manual", "interaction_type": "note",
              "direction": "outbound", "body": "leak"}),
            ("/api/admin/comms/feed", "GET", None),
            ("/api/admin/comms/providers", "GET", None),
        ]:
            code = await _probe(client, method, path, body)
            report.add("Comm Scope",
                       f"{role} {method} {path} rejected",
                       code in REJECT, f"status={code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 8 — Activity admin endpoints scope
# ──────────────────────────────────────────────────────────────────────────
async def verify_activity_scope() -> None:
    log.info("≡ Section 8 / activity admin endpoints scope")
    # Public ingest endpoints stay public (by F2 design — fire-and-forget)
    async with anon_client() as c:
        r = await c.post(f"{BASE}/api/activity/track", json={
            "events": [{"event": "page_view", "visitor_id": f"sec_audit_{uuid.uuid4().hex[:8]}",
                        "path": "/", "props": {}}],
        })
        report.add("Activity Scope",
                   "anon /activity/track stays public (by design)",
                   r.status_code == 200, f"status={r.status_code}")
        r = await c.post(f"{BASE}/api/activity/identify", json={
            "visitor_id": f"sec_audit_{uuid.uuid4().hex[:8]}",
        })
        report.add("Activity Scope",
                   "anon /activity/identify stays public (by design)",
                   r.status_code == 200, f"status={r.status_code}")
        # But admin-only analytics must be gated
        for p in ["/api/admin/activity/overview",
                  "/api/admin/activity/live",
                  "/api/admin/activity/abandonment",
                  "/api/admin/activity/attribution"]:
            r = await c.get(f"{BASE}{p}")
            report.add("Activity Scope",
                       f"anon GET {p} rejected",
                       r.status_code in REJECT, f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 9 — F4 Instructions scope
# ──────────────────────────────────────────────────────────────────────────
async def verify_f4_scope() -> None:
    log.info("≡ Section 9 / F4 instructions scope")
    # Non-staff cannot read manager-side
    for role in ("client", "developer", "tester"):
        client = await get_role_client(role)
        if not client:
            continue
        r = await client.get(f"{BASE}/api/manager/instructions")
        report.add("F4 Scope",
                   f"{role} GET /manager/instructions rejected",
                   r.status_code in REJECT, f"status={r.status_code}")

    # Manager can read, but cannot CREATE
    client = await get_role_client("manager")
    if client:
        r = await client.get(f"{BASE}/api/manager/instructions")
        report.add("F4 Scope",
                   "manager GET /manager/instructions allowed",
                   r.status_code == 200, f"status={r.status_code}")
        r = await client.post(f"{BASE}/api/admin/manager/instructions",
                              json={"title": "manager-injected",
                                    "body": "x", "category": "general",
                                    "status": "draft"})
        report.add("F4 Scope",
                   "manager POST /admin/manager/instructions rejected",
                   r.status_code in REJECT, f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Section 10 — Manager scope on IR (visibility)
# ──────────────────────────────────────────────────────────────────────────
async def verify_manager_ir_scope() -> None:
    """Per PRD: 'Manager cabinet reuses ADMIN-gated IR endpoints → a pure
    manager-role user gets 401' was a known follow-on. We assert the CURRENT
    contract: manager role gets a 200 from /admin/ir/leads (the existing
    behaviour shows scoped leads — but the contract is that it does not 500
    and does not leak rows that belong to other admins outside the manager's
    scope filter). We sanity-check the call succeeds & returns a list."""
    log.info("≡ Section 10 / manager IR visibility")
    client = await get_role_client("manager")
    if not client:
        report.add("Manager IR", "manager login", False, "login failed")
        return
    r = await client.get(f"{BASE}/api/admin/ir/leads")
    report.add("Manager IR",
               "manager can list IR leads (scoped)",
               r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        payload = r.json()
        leads = payload.get("leads", [])
        # If any lead is returned, every visible lead must either have no
        # owner or have owner_id == this manager's user_id. Pure admin's
        # private leads must not leak.
        mgr_id = None
        me = await client.get(f"{BASE}/api/auth/me")
        if me.status_code == 200:
            mgr_id = (me.json() or {}).get("user_id")
        leaked = [l for l in leads
                  if l.get("owner_id")
                  and mgr_id and l.get("owner_id") != mgr_id]
        report.add("Manager IR",
                   "no foreign-owner leads leak into manager scope",
                   len(leaked) == 0,
                   f"visible={len(leads)} foreign={len(leaked)}")


# ──────────────────────────────────────────────────────────────────────────
# Section 11 — Auth brute-force defence (rate limit / X-RateLimit headers)
# ──────────────────────────────────────────────────────────────────────────
async def verify_auth_rate_limit() -> None:
    """Login endpoint should expose rate-limit headers AND start 429-ing
    when burst-spammed."""
    log.info("≡ Section 11 / auth rate limit")
    async with anon_client() as c:
        # Single login carries X-RateLimit-* headers (proves middleware is on)
        r = await c.post(f"{BASE}/api/auth/login",
                         json={"email": "ghost@nowhere",
                               "password": "x" * 10})
        has_headers = any(h.lower().startswith("x-ratelimit-")
                          for h in r.headers.keys())
        report.add("Rate Limit",
                   "login response carries X-RateLimit-* headers",
                   has_headers, f"keys={[h for h in r.headers if 'rate' in h.lower()]}")

    # Burst: try a clearly-wrong password 15 times → some MUST be 429
    async with anon_client() as c:
        codes: List[int] = []
        for _ in range(15):
            r = await c.post(f"{BASE}/api/auth/login",
                             json={"email": "ghost@nowhere",
                                   "password": "x" * 12})
            codes.append(r.status_code)
        any_429 = any(s == 429 for s in codes)
        report.add("Rate Limit",
                   "auth burst hits 429 (brute-force throttle)",
                   any_429, f"codes_observed={sorted(set(codes))}")


# ──────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────
async def main() -> int:
    log.info(f"BASE={BASE} DB={DB_NAME}")
    await verify_anonymous_reject()
    # Cache role clients up-front so every subsequent section reuses
    # the same login (otherwise the audit's own bursts trip the limiter
    # the audit also verifies).
    for role in ("admin", "manager", "client", "developer", "tester"):
        await get_role_client(role)
        await asyncio.sleep(0.05)

    await verify_privilege_escalation()
    await verify_staff_vs_admin()
    await verify_session_revocation()
    await verify_contract_tokens()
    await verify_csp_endpoints()
    await verify_comms_scope()
    await verify_activity_scope()
    await verify_f4_scope()
    await verify_manager_ir_scope()
    # Run the brute-force burst LAST so it doesn't lock other sections out.
    # Give the limiter window a moment to drain from earlier logins.
    await asyncio.sleep(15)
    await verify_auth_rate_limit()
    await close_role_clients()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"SECURITY CONTRACT AUDIT — {summary['verdict']} "
          f"(pass={summary['passed']}/{summary['total']} "
          f"fail={summary['failed']} warn={summary['warned']})")
    print("=" * 78)
    for sect, c in summary["by_section"].items():
        print(f"  {sect:24s}  pass={c['pass']:>2}  fail={c['fail']:>2}  warn={c['warn']:>2}")

    out = "/app/test_reports/security_contract_audit.json"
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
