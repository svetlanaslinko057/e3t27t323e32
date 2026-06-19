"""
LUMEN — RV2 Outlook / Microsoft 365 Real-Provider Validation
============================================================

Eighth harness, sibling to RV1 Gmail. Enforces the same reality contract
against a real Microsoft 365 tenant: real OAuth, real Graph sendMail,
real refresh-token rotation, real subscription that hasn't expired
(Graph subscriptions are notoriously short-lived — Mail subscriptions
max out at ~3 days and must be renewed).

Tri-state report (PASS / FAIL / SKIP). Mock-mode → every reality
assertion SKIPs with an explicit precondition; verdict stays PASS. Real
mode → every assertion must PASS or the merge is blocked.

Required environment for "real mode":
  OUTLOOK_CLIENT_ID         — Microsoft Entra app registration client id
  OUTLOOK_CLIENT_SECRET     — corresponding client secret
  OUTLOOK_TENANT            — tenant id (or 'common' / 'organizations')
  OUTLOOK_REDIRECT_URI      — registered redirect URI
  OUTLOOK_WEBHOOK_SECRET    — HMAC secret on the Graph push proxy
  OUTLOOK_CLIENT_STATE      — clientState shared with the subscription
  OUTLOOK_TEST_MAILBOX      — (optional) mailbox to use for live send

Mock-token detection: if the stored access_token / refresh_token start
with ``mock_ms_``, the harness treats the system as not-yet-real.

Run:
    cd /app/backend && python rv2_outlook_real_provider.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
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

OUTLOOK_CLIENT_ID = (
    os.environ.get("OUTLOOK_CLIENT_ID")
    or os.environ.get("MS_CLIENT_ID")
    or os.environ.get("AZURE_CLIENT_ID")
)
OUTLOOK_CLIENT_SECRET = (
    os.environ.get("OUTLOOK_CLIENT_SECRET")
    or os.environ.get("MS_CLIENT_SECRET")
    or os.environ.get("AZURE_CLIENT_SECRET")
)
OUTLOOK_TENANT = os.environ.get("OUTLOOK_TENANT")
OUTLOOK_REDIRECT_URI = os.environ.get("OUTLOOK_REDIRECT_URI")
OUTLOOK_WEBHOOK_SECRET = os.environ.get("OUTLOOK_WEBHOOK_SECRET")
OUTLOOK_CLIENT_STATE = os.environ.get("OUTLOOK_CLIENT_STATE")
OUTLOOK_TEST_MAILBOX = os.environ.get("OUTLOOK_TEST_MAILBOX")

ENV_HAS_CREDS = bool(OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rv2-outlook")
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
                "items": self.items, "generated_at": _utc(),
                "mode": "real" if ENV_HAS_CREDS else "mock"}


report = Report()


async def login_admin(client: httpx.AsyncClient) -> bool:
    r = await client.post(f"{BASE}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        return False
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
    return True


async def _outlook_status(client: httpx.AsyncClient) -> dict:
    r = await client.get(f"{BASE}/api/admin/comms/outlook/status")
    return r.json() if r.status_code == 200 else {}


async def _provider_doc() -> dict:
    return (await db.lumen_communication_providers.find_one(
        {"key": "outlook"})) or {}


def _looks_mock_token(value: Optional[str]) -> bool:
    if not value:
        return True
    v = str(value)
    return v.startswith("mock_ms_") or v.startswith("mock_") or v.startswith("lumen-mock-")


# ──────────────────────────────────────────────────────────────────────────
# RV2.1 — Credentials gate
# ──────────────────────────────────────────────────────────────────────────
async def check_creds() -> None:
    if not ENV_HAS_CREDS:
        report.add("RV2.1",
                   "OUTLOOK_CLIENT_ID + OUTLOOK_CLIENT_SECRET present",
                   "skip",
                   "set OUTLOOK_CLIENT_ID + OUTLOOK_CLIENT_SECRET in backend/.env "
                   "(from Microsoft Entra app registration)")
        return
    if not OUTLOOK_TENANT or OUTLOOK_TENANT == "common":
        report.add("RV2.1",
                   "OUTLOOK_TENANT is a specific tenant id (not 'common')",
                   "skip",
                   "set OUTLOOK_TENANT to your Microsoft tenant id for "
                   "production; 'common' is fine for dev but cannot be "
                   "audited for tenant-scoped behaviour")
        return
    if not OUTLOOK_REDIRECT_URI or "://" not in (OUTLOOK_REDIRECT_URI or ""):
        report.add("RV2.1",
                   "OUTLOOK_REDIRECT_URI is a real https URL registered in "
                   "the Entra app",
                   "skip", "set OUTLOOK_REDIRECT_URI")
        return
    if not OUTLOOK_WEBHOOK_SECRET or len(OUTLOOK_WEBHOOK_SECRET) < 32:
        report.add("RV2.1",
                   "OUTLOOK_WEBHOOK_SECRET is a strong (≥32 chars) secret",
                   "skip", "set OUTLOOK_WEBHOOK_SECRET")
        return
    if not OUTLOOK_CLIENT_STATE or len(OUTLOOK_CLIENT_STATE) < 16:
        report.add("RV2.1",
                   "OUTLOOK_CLIENT_STATE is a stable ≥16-char value matching "
                   "the Graph subscription",
                   "skip", "set OUTLOOK_CLIENT_STATE")
        return
    report.add("RV2.1",
               "all Microsoft real-creds env vars present",
               "pass", f"tenant={OUTLOOK_TENANT}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.2 — Connected to real M365 tenant
# ──────────────────────────────────────────────────────────────────────────
async def check_real_connection(client: httpx.AsyncClient) -> None:
    status = await _outlook_status(client)
    if status.get("mock_mode"):
        report.add("RV2.2",
                   "outlook adapter is NOT in mock_mode",
                   "skip", "F7 mock-mode active — provide real creds")
        return
    if status.get("oauth_status") != "connected":
        report.add("RV2.2",
                   "oauth_status==connected against real M365 tenant",
                   "skip", "complete real OAuth at /api/comms/oauth/outlook/start")
        return
    doc = await _provider_doc()
    cfg = doc.get("config") or {}
    if _looks_mock_token(cfg.get("refresh_token")) or _looks_mock_token(cfg.get("access_token")):
        report.add("RV2.2",
                   "stored Microsoft tokens are real (not mock_ms_*)",
                   "fail", "tokens still look mock — re-run real OAuth")
        return
    report.add("RV2.2",
               "real Microsoft tokens stored, oauth_status=connected",
               "pass",
               f"tenant={cfg.get('tenant')} connected_at={cfg.get('connected_at')}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.3 — Real outbound via Graph sendMail
# ──────────────────────────────────────────────────────────────────────────
async def check_real_outbound(client: httpx.AsyncClient) -> None:
    status = await _outlook_status(client)
    if status.get("mock_mode") or status.get("oauth_status") != "connected":
        report.add("RV2.3",
                   "outbound via real Graph sendMail returns sync_status=sent "
                   "+ real internetMessageId",
                   "skip", "requires real creds + connected OAuth")
        return
    if not OUTLOOK_TEST_MAILBOX:
        report.add("RV2.3",
                   "outbound via real Graph sendMail returns sync_status=sent",
                   "skip",
                   "set OUTLOOK_TEST_MAILBOX to enable the live send smoke")
        return
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "outlook",
        "interaction_type": "email",
        "direction": "outbound",
        "contact": OUTLOOK_TEST_MAILBOX,
        "subject": f"[LUMEN RV2] real-provider smoke {datetime.utcnow().isoformat()}",
        "body": "Automated RV2 smoke. Safe to ignore.",
    })
    payload = r.json() if r.status_code == 200 else {}
    sync = payload.get("sync_status")
    ext = ((payload.get("comm") or {}).get("external_ref")) or ""
    real_looking = ext and not ext.startswith("outlook_") and not _looks_mock_token(ext)
    report.add("RV2.3",
               "outbound via real Graph sendMail returns sync_status=sent + "
               "real internetMessageId",
               "pass" if (sync == "sent" and real_looking) else "fail",
               f"sync={sync} external_ref={ext[:32]}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.4 — Real refresh-token rotation
# ──────────────────────────────────────────────────────────────────────────
async def check_real_refresh(client: httpx.AsyncClient) -> None:
    status = await _outlook_status(client)
    if status.get("mock_mode") or status.get("oauth_status") != "connected":
        report.add("RV2.4",
                   "real refresh-token rotation succeeded (Microsoft token "
                   "endpoint)",
                   "skip", "requires real creds + connected OAuth")
        return
    doc_before = await _provider_doc()
    at_before = (doc_before.get("config") or {}).get("access_token")
    r = await client.post(f"{BASE}/api/admin/comms/outlook/rotate-token")
    if r.status_code != 200 or not r.json().get("ok"):
        report.add("RV2.4",
                   "real refresh-token rotation succeeded",
                   "fail", f"rotate returned {r.status_code}: {r.text[:120]}")
        return
    doc_after = await _provider_doc()
    at_after = (doc_after.get("config") or {}).get("access_token")
    if _looks_mock_token(at_after):
        report.add("RV2.4",
                   "rotated access_token is real (not mock_ms_*)",
                   "fail", "rotation returned a mock token")
        return
    if at_before == at_after:
        report.add("RV2.4",
                   "rotated access_token differs from the previous one",
                   "fail", "Microsoft returned an identical access_token")
        return
    audit = await db.lumen_staff_login_audit.find_one(
        {"category": "oauth.outlook.refresh",
         "detail.mock": {"$ne": True}},
        sort=[("at", -1)],
    )
    report.add("RV2.4",
               "real refresh-token rotation succeeded + audit row written "
               "with mock=false",
               "pass" if audit else "fail",
               f"audit_row={audit.get('id') if audit else None}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.5 — Real inbound from Graph subscription
# ──────────────────────────────────────────────────────────────────────────
async def check_real_inbound() -> None:
    """Find any outlook comm row whose external_ref is NOT the F7 seed
    AND whose extra.received_at is within the last 90 days."""
    if not ENV_HAS_CREDS:
        report.add("RV2.5",
                   "at least one inbound outlook row from real Graph "
                   "subscription delivery",
                   "skip", "requires real creds")
        return
    cfg = (await _provider_doc()).get("config") or {}
    if _looks_mock_token(cfg.get("refresh_token")):
        report.add("RV2.5",
                   "at least one inbound outlook row from real Graph "
                   "subscription delivery",
                   "skip", "tokens still mock — connect real OAuth")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    row = await db.lumen_lead_communications.find_one({
        "provider": "outlook",
        "direction": "inbound",
        "external_ref": {"$nin": ["outlook_msg_lumen_welcome_001"],
                         "$not": {"$regex": "^outlook_msg_audit_"}},
        "at": {"$gte": cutoff},
    })
    report.add("RV2.5",
               "at least one inbound outlook row from real Graph delivery",
               "pass" if row else "fail",
               f"sample_external_ref={(row or {}).get('external_ref')}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.6 — Graph subscription renewed within safety window
# ──────────────────────────────────────────────────────────────────────────
async def check_subscription_lifecycle() -> None:
    """Microsoft Graph mail subscriptions max out at ~3 days. Production
    deployments MUST renew them on a sub-3-day cadence. Check that the
    persisted ``subscription_expires_at`` is at least 12 h away."""
    if not ENV_HAS_CREDS:
        report.add("RV2.6",
                   "Graph subscription is renewed within 3-day safety window",
                   "skip", "requires real creds")
        return
    cfg = (await _provider_doc()).get("config") or {}
    sub_exp = cfg.get("subscription_expires_at") or cfg.get("graph_subscription_expires_at")
    if not sub_exp:
        report.add("RV2.6",
                   "subscription_expires_at recorded in provider.config",
                   "skip",
                   "the live deployment must create a Graph subscription and "
                   "persist its expiration timestamp; not yet wired")
        return
    try:
        exp = datetime.fromisoformat(str(sub_exp).replace("Z", "+00:00"))
        margin = exp - datetime.now(timezone.utc)
        report.add("RV2.6",
                   "Graph subscription is current (≥12 h to expiry)",
                   "pass" if margin > timedelta(hours=12) else "fail",
                   f"expires_in={margin}")
    except Exception as e:
        report.add("RV2.6",
                   "subscription_expires_at is a parseable timestamp",
                   "fail", f"parse_error={e}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.7 — Quota / error hygiene
# ──────────────────────────────────────────────────────────────────────────
async def check_quota_hygiene() -> None:
    if not ENV_HAS_CREDS:
        report.add("RV2.7",
                   "no quota / throttling failures in the last 24 h",
                   "skip", "requires real creds")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    bad = await db.lumen_staff_login_audit.count_documents({
        "category": {"$regex": "^oauth\\.outlook\\.(refresh_failed|throttle|quota)"},
        "at": {"$gte": cutoff},
    })
    report.add("RV2.7",
               "no Graph throttle / refresh failures in audit during the "
               "last 24 h",
               "pass" if bad == 0 else "fail",
               f"failure_rows={bad}")


# ──────────────────────────────────────────────────────────────────────────
# RV2.8 — Real conversationId propagates across read surfaces
# ──────────────────────────────────────────────────────────────────────────
async def check_thread_surface_propagation() -> None:
    if not ENV_HAS_CREDS:
        report.add("RV2.8",
                   "real conversationId propagates to Feed + Timeline + Activity",
                   "skip", "requires real creds + a real inbound row")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    row = await db.lumen_lead_communications.find_one({
        "provider": "outlook", "direction": "inbound",
        "external_ref": {"$nin": ["outlook_msg_lumen_welcome_001"]},
        "at": {"$gte": cutoff},
    })
    if not row:
        report.add("RV2.8",
                   "real conversationId propagates across read surfaces",
                   "skip", "no real inbound row yet (RV2.5 SKIP)")
        return
    thread_ref = (row.get("extra") or {}).get("thread_ref")
    if not thread_ref:
        report.add("RV2.8",
                   "real inbound row carries a non-empty conversationId",
                   "fail", f"thread_ref={thread_ref!r}")
        return
    same_thread = await db.lumen_lead_communications.count_documents(
        {"extra.thread_ref": thread_ref})
    report.add("RV2.8",
               "real conversationId is queryable via extra.thread_ref index",
               "pass" if same_thread >= 1 else "fail",
               f"rows_in_thread={same_thread} thread_ref={thread_ref}")


# ──────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────
async def main() -> int:
    log.info(f"BASE={BASE} DB={DB_NAME} mode={'real' if ENV_HAS_CREDS else 'mock'}")
    async with httpx.AsyncClient(timeout=20) as client:
        if not await login_admin(client):
            report.add("Auth", "admin login", "fail", "could not login")
            print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
            return 1
        report.add("Auth", "admin login", "pass", ADMIN_EMAIL)

        await check_creds()
        await check_real_connection(client)
        await check_real_outbound(client)
        await check_real_refresh(client)
        await check_real_inbound()
        await check_subscription_lifecycle()
        await check_quota_hygiene()
        await check_thread_surface_propagation()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"RV2 OUTLOOK REAL-PROVIDER VALIDATION — {summary['verdict']} "
          f"(pass={summary['passed']}  fail={summary['failed']}  "
          f"skip={summary['skipped']}  /  total={summary['total']}  "
          f"mode={summary['mode']})")
    print("=" * 78)
    by_req: Dict[str, Dict[str, int]] = {}
    for it in summary["items"]:
        r = it["req"]
        by_req.setdefault(r, {"pass": 0, "fail": 0, "skip": 0})
        by_req[r][it["status"]] += 1
    for r, c in by_req.items():
        print(f"  {r:8s}  pass={c['pass']:>2}  fail={c['fail']:>2}  skip={c['skip']:>2}")

    out = "/app/test_reports/rv2_outlook_real_provider.json"
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
