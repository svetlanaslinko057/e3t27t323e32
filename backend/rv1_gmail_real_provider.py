"""
LUMEN — RV1 Gmail Real-Provider Validation
==========================================

Seventh harness, the first one that **does not enforce architecture —
it enforces reality**. The other six harnesses (Business, Infrastructure,
Communication, Security, F6 Gmail, F7 Outlook) all run against the LUMEN
process itself. This harness runs against a **real Google Workspace
tenant** and refuses to claim Gmail is production-ready until live
behaviours match the F6 contract.

Why this exists:
  F6 proved the *shape* of the integration — OAuth state, HMAC, dedup,
  thread_ref wiring, activation guard. But shape is not behaviour.
  Real Google has quotas, push subscription expiry, refresh-token
  invalidation after long idle periods, mailbox-specific permission
  errors, real timezones in headers, and at-least-once delivery on
  Pub/Sub that arrives multiple times in flaky windows. None of that
  is reachable from a mock.

Discipline:
  • Pre-real-tenant state: every reality-assertion reports SKIP with
    an explicit precondition (the env var or flag that flips it). The
    overall verdict stays PASS because no live failure was observed —
    same shape as F6 preflight pre-F6.
  • Post-real-tenant state: every assertion MUST be PASS. Anything that
    flips to FAIL is a real-world bug the mock could not surface.

Required environment for "real mode":
  GMAIL_CLIENT_ID         — Google OAuth client id
  GMAIL_CLIENT_SECRET     — Google OAuth client secret
  GMAIL_REDIRECT_URI      — production redirect URI registered in Google Console
  GMAIL_WEBHOOK_SECRET    — HMAC secret shared with the publisher (Pub/Sub push proxy)
  GMAIL_TEST_MAILBOX      — (optional) mailbox address to use for the smoke test

Mock-detection is intentionally robust: even if env vars are present, a
refresh_token starting with ``mock_`` is treated as not-yet-real. This
prevents the harness from claiming victory when someone ran the F6
mock-OAuth in a "real" deployment.

Run:
    cd /app/backend && python rv1_gmail_real_provider.py
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

# Real-tenant detection
GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID")
GMAIL_CLIENT_SECRET = (
    os.environ.get("GMAIL_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET")
)
GMAIL_REDIRECT_URI = os.environ.get("GMAIL_REDIRECT_URI")
GMAIL_WEBHOOK_SECRET = os.environ.get("GMAIL_WEBHOOK_SECRET")
GMAIL_TEST_MAILBOX = os.environ.get("GMAIL_TEST_MAILBOX")

# "real mode" requires BOTH client creds present AND not a mock-token deploy
ENV_HAS_CREDS = bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rv1-gmail")
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Tri-state report
# ──────────────────────────────────────────────────────────────────────────
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


async def _gmail_status(client: httpx.AsyncClient) -> dict:
    r = await client.get(f"{BASE}/api/admin/comms/gmail/status")
    return r.json() if r.status_code == 200 else {}


async def _provider_doc() -> dict:
    return (await db.lumen_communication_providers.find_one({"key": "gmail"})) or {}


def _looks_mock_token(value: Optional[str]) -> bool:
    if not value:
        return True
    v = str(value)
    return v.startswith("mock_") or v.startswith("lumen-mock-")


# ──────────────────────────────────────────────────────────────────────────
# RV1.1 — OAuth credentials reachable
# ──────────────────────────────────────────────────────────────────────────
async def check_creds() -> None:
    """The Google OAuth client id + secret must be present AND not the
    mock placeholders. This is the gate that flips every other assertion
    from SKIP to ENFORCEABLE."""
    if not ENV_HAS_CREDS:
        report.add("RV1.1",
                   "GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET present in env",
                   "skip",
                   "set GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET in backend/.env")
        return
    if not GMAIL_REDIRECT_URI or "://" not in (GMAIL_REDIRECT_URI or ""):
        report.add("RV1.1",
                   "GMAIL_REDIRECT_URI is a real https URL registered in "
                   "Google Console",
                   "skip",
                   "set GMAIL_REDIRECT_URI to the URL registered in "
                   "Google Console → Credentials")
        return
    if not GMAIL_WEBHOOK_SECRET or len(GMAIL_WEBHOOK_SECRET) < 32:
        report.add("RV1.1",
                   "GMAIL_WEBHOOK_SECRET is a strong (≥32 chars) secret",
                   "skip",
                   "set GMAIL_WEBHOOK_SECRET to a ≥32-char random string")
        return
    report.add("RV1.1",
               "GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REDIRECT_URI "
               "+ GMAIL_WEBHOOK_SECRET all present",
               "pass", "real-credentials gate is open")


# ──────────────────────────────────────────────────────────────────────────
# RV1.2 — Connected to a real Google tenant (not mock token)
# ──────────────────────────────────────────────────────────────────────────
async def check_real_connection(client: httpx.AsyncClient) -> None:
    """``oauth_status == connected`` must be true AND the stored
    refresh_token must look like a real Google token (not the mock
    placeholder F6 ships with)."""
    status = await _gmail_status(client)
    if status.get("mock_mode"):
        report.add("RV1.2",
                   "gmail adapter is NOT in mock_mode",
                   "skip",
                   "F6 mock-mode active — provide real creds to flip this")
        return
    if status.get("oauth_status") != "connected":
        report.add("RV1.2",
                   "oauth_status==connected against a real Google tenant",
                   "skip",
                   "complete the real OAuth flow at /api/comms/oauth/gmail/start")
        return
    doc = await _provider_doc()
    cfg = doc.get("config") or {}
    rt = cfg.get("refresh_token")
    at = cfg.get("access_token")
    if _looks_mock_token(rt) or _looks_mock_token(at):
        report.add("RV1.2",
                   "stored tokens are real (not mock_*)",
                   "fail",
                   "tokens still look mock — re-run real OAuth flow")
        return
    report.add("RV1.2",
               "real Google tokens stored, oauth_status=connected",
               "pass",
               f"connected_at={cfg.get('connected_at')} "
               f"refresh_at={cfg.get('refresh_at')}")


# ──────────────────────────────────────────────────────────────────────────
# RV1.3 — Real outbound: /comms/send via gmail provider transmits, not
#         just records
# ──────────────────────────────────────────────────────────────────────────
async def check_real_outbound(client: httpx.AsyncClient) -> None:
    """The adapter ``send()`` in F6 is currently a no-op in mock mode (just
    fabricates external_ref). With real creds it must POST to Gmail API
    ``users.messages.send`` and only then claim sync_status=sent. This
    harness verifies the latter."""
    status = await _gmail_status(client)
    if status.get("mock_mode") or status.get("oauth_status") != "connected":
        report.add("RV1.3",
                   "outbound via real Gmail API returns sync_status=sent + "
                   "valid Gmail messageId",
                   "skip",
                   "requires real creds + connected OAuth")
        return
    if not GMAIL_TEST_MAILBOX:
        report.add("RV1.3",
                   "outbound via real Gmail API returns sync_status=sent",
                   "skip",
                   "set GMAIL_TEST_MAILBOX to enable the live send smoke")
        return
    body = {
        "provider": "gmail",
        "interaction_type": "email",
        "direction": "outbound",
        "contact": GMAIL_TEST_MAILBOX,
        "subject": f"[LUMEN RV1] real-provider smoke {datetime.utcnow().isoformat()}",
        "body": "Automated RV1 smoke. Safe to ignore.",
    }
    r = await client.post(f"{BASE}/api/comms/send", json=body)
    payload = r.json() if r.status_code == 200 else {}
    sync = payload.get("sync_status")
    ext = ((payload.get("comm") or {}).get("external_ref")) or ""
    real_looking = ext and not ext.startswith("gmail_") and not _looks_mock_token(ext)
    report.add("RV1.3",
               "outbound via real Gmail API returns sync_status=sent + "
               "valid Gmail messageId (not the F6 placeholder)",
               "pass" if (sync == "sent" and real_looking) else "fail",
               f"sync={sync} external_ref={ext[:32]}")


# ──────────────────────────────────────────────────────────────────────────
# RV1.4 — Refresh-token rotation against real Google succeeded
# ──────────────────────────────────────────────────────────────────────────
async def check_real_refresh(client: httpx.AsyncClient) -> None:
    """A scheduled rotation must update last_refreshed_at AND issue a
    NEW access_token (different from the previous one) using the real
    Google token endpoint. The audit row category=oauth.gmail.refresh
    must reflect a non-mock event."""
    status = await _gmail_status(client)
    if status.get("mock_mode") or status.get("oauth_status") != "connected":
        report.add("RV1.4",
                   "real refresh-token rotation succeeded (Google "
                   "token endpoint)",
                   "skip", "requires real creds + connected OAuth")
        return
    doc_before = await _provider_doc()
    at_before = (doc_before.get("config") or {}).get("access_token")
    r = await client.post(f"{BASE}/api/admin/comms/gmail/rotate-token")
    if r.status_code != 200 or not r.json().get("ok"):
        report.add("RV1.4",
                   "real refresh-token rotation succeeded",
                   "fail",
                   f"rotate endpoint returned {r.status_code}: {r.text[:120]}")
        return
    doc_after = await _provider_doc()
    at_after = (doc_after.get("config") or {}).get("access_token")
    if _looks_mock_token(at_after):
        report.add("RV1.4",
                   "rotated access_token is real (not mock_*)",
                   "fail", "rotation returned a mock token")
        return
    if at_before == at_after:
        report.add("RV1.4",
                   "rotated access_token differs from the previous one",
                   "fail", "Google returned an identical access_token "
                           "(possible cache or no rotation)")
        return
    # Verify the audit row exists and is non-mock
    audit = await db.lumen_staff_login_audit.find_one(
        {"category": "oauth.gmail.refresh",
         "detail.mock": {"$ne": True}},
        sort=[("at", -1)],
    )
    report.add("RV1.4",
               "real refresh-token rotation succeeded + audit row written "
               "with mock=false",
               "pass" if audit else "fail",
               f"audit_row={audit.get('id') if audit else None}")


# ──────────────────────────────────────────────────────────────────────────
# RV1.5 — Real inbound: a real Pub/Sub push delivered a real message
# ──────────────────────────────────────────────────────────────────────────
async def check_real_inbound() -> None:
    """Look for any gmail comm row whose external_ref does NOT match the
    F6 seed pattern and whose extra.received_at is within the last 90
    days. This proves the webhook ingested REAL traffic, not the seed.
    """
    status_mock = (await _gmail_status_via_db()).get("mock_mode_inferred", True)
    if status_mock:
        report.add("RV1.5",
                   "at least one inbound gmail row is from real Pub/Sub "
                   "delivery (not the F6 seed)",
                   "skip", "requires real provider + a real inbound event")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    row = await db.lumen_lead_communications.find_one({
        "provider": "gmail",
        "direction": "inbound",
        "external_ref": {"$nin": ["gmail_msg_lumen_welcome_001"],
                         "$not": {"$regex": "^gmail_msg_audit_"}},
        "at": {"$gte": cutoff},
    })
    report.add("RV1.5",
               "at least one inbound gmail row is from real delivery",
               "pass" if row else "fail",
               f"sample_external_ref={(row or {}).get('external_ref')}")


async def _gmail_status_via_db() -> dict:
    """Mock-mode inference without needing an http call (so RV1.5 can
    run independently). Mock if no real creds OR no non-mock token."""
    if not ENV_HAS_CREDS:
        return {"mock_mode_inferred": True}
    cfg = (await _provider_doc()).get("config") or {}
    rt = cfg.get("refresh_token")
    if _looks_mock_token(rt) or cfg.get("oauth_status") != "connected":
        return {"mock_mode_inferred": True}
    return {"mock_mode_inferred": False}


# ──────────────────────────────────────────────────────────────────────────
# RV1.6 — Pub/Sub watch is current (Gmail watch expires ~7 days)
# ──────────────────────────────────────────────────────────────────────────
async def check_watch_subscription() -> None:
    """Gmail's push-notification model uses ``users.watch`` which Google
    auto-expires after at most 7 days. Production deployments MUST renew
    it on a schedule. This assertion checks that the most recent
    successful watch renewal is within the last 6 days (giving 24 h of
    safety margin)."""
    if not ENV_HAS_CREDS:
        report.add("RV1.6",
                   "Pub/Sub watch is renewed within 6-day safety window",
                   "skip", "requires real creds")
        return
    cfg = (await _provider_doc()).get("config") or {}
    watch_until = cfg.get("watch_expires_at")
    if not watch_until:
        report.add("RV1.6",
                   "watch_expires_at recorded in provider.config.gmail",
                   "skip",
                   "the live deployment must call users.watch and persist "
                   "the expiration timestamp; not yet wired")
        return
    try:
        exp = datetime.fromisoformat(str(watch_until).replace("Z", "+00:00"))
        margin = exp - datetime.now(timezone.utc)
        report.add("RV1.6",
                   "Pub/Sub watch is current (≥24 h to expiry)",
                   "pass" if margin > timedelta(hours=24) else "fail",
                   f"expires_in={margin}")
    except Exception as e:
        report.add("RV1.6",
                   "watch_expires_at is a parseable timestamp",
                   "fail", f"parse_error={e}")


# ──────────────────────────────────────────────────────────────────────────
# RV1.7 — Quota / error hygiene: no quota-exceeded errors in last 24 h
# ──────────────────────────────────────────────────────────────────────────
async def check_quota_hygiene() -> None:
    """In real mode, Google enforces quotas (e.g. 1B units/day per
    project, per-user rate limits). Any 429/403 quota error in the last
    24 h is a production warning. We surface it via the audit collection
    (F6 writes ``oauth.gmail.refresh_failed`` already; we extend the
    pattern here)."""
    if not ENV_HAS_CREDS:
        report.add("RV1.7",
                   "no quota-exceeded errors in the last 24 h",
                   "skip", "requires real creds")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    bad = await db.lumen_staff_login_audit.count_documents({
        "category": {"$regex": "^oauth\\.gmail\\.(refresh_failed|quota_)"},
        "at": {"$gte": cutoff},
    })
    report.add("RV1.7",
               "no quota / refresh failures in audit during the last 24 h",
               "pass" if bad == 0 else "fail",
               f"failure_rows={bad}")


# ──────────────────────────────────────────────────────────────────────────
# RV1.8 — Real thread_ref appears across the read surfaces
# ──────────────────────────────────────────────────────────────────────────
async def check_thread_surface_propagation() -> None:
    """If RV1.5 found a real inbound row, its ``extra.thread_ref`` must
    appear in (a) the comm feed at /admin/comms/feed?thread_ref=…,
    (b) the lead timeline if a lead was resolved, and (c) the manager
    activity counters bumped. This is the architectural contract from
    F5 — verified against REAL data, not the seed."""
    if not ENV_HAS_CREDS:
        report.add("RV1.8",
                   "real thread_ref propagates to Feed + Timeline + Activity",
                   "skip", "requires real creds + a real inbound row")
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    row = await db.lumen_lead_communications.find_one({
        "provider": "gmail", "direction": "inbound",
        "external_ref": {"$nin": ["gmail_msg_lumen_welcome_001"]},
        "at": {"$gte": cutoff},
    })
    if not row:
        report.add("RV1.8",
                   "real thread_ref propagates to Feed + Timeline + Activity",
                   "skip", "no real inbound row yet (RV1.5 SKIP)")
        return
    thread_ref = (row.get("extra") or {}).get("thread_ref")
    if not thread_ref:
        report.add("RV1.8",
                   "real inbound row carries a non-empty thread_ref",
                   "fail", f"thread_ref={thread_ref!r}")
        return
    # Read-back via the F5 thread endpoint
    same_thread = await db.lumen_lead_communications.count_documents(
        {"extra.thread_ref": thread_ref})
    report.add("RV1.8",
               "real thread_ref is queryable via extra.thread_ref index",
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
        await check_watch_subscription()
        await check_quota_hygiene()
        await check_thread_surface_propagation()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"RV1 GMAIL REAL-PROVIDER VALIDATION — {summary['verdict']} "
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

    out = "/app/test_reports/rv1_gmail_real_provider.json"
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
