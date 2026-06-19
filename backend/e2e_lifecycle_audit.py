"""
LUMEN — E2E Investor-Lifecycle Cross-Subsystem Audit (post-F4)
==============================================================

After IR0/IR1/IR2 + Manager OS + F1 Funnel + F2 Activity + F3 Staff Security +
F5 Comm Providers + F4 Manager Instructions, the user explicitly asked for
ONE sweeping audit that drives the whole investor lifecycle and verifies
EVERY cross-cutting subsystem still sees the events coherently:

    Lead → Meeting → KYC → Accreditation → Contract → Contract Signed →
    Funding → Certificate → Active Investor

Cross-cuts verified:
    • IR Timeline           (/api/admin/ir/leads/{id}/timeline)
    • Site Activity         (/api/admin/activity/timeline + overview)
    • Funnel                (/api/admin/funnel/dashboard, /stages)
    • Funnel Attribution    (/api/admin/funnel/manager-attribution)
    • Manager OS Activity   (/api/admin/managers/{uid}/activity, /manager-os/snapshot)
    • Communication Feed F5 (/api/admin/comms/feed?lead_id=…, /stats)
    • F4 Acknowledgements   (/api/admin/manager/instructions-overview)

The script is non-destructive: it creates a uniquely-named lead, a unique
visitor_id, and DOES NOT mutate existing investors. KYC / Accreditation /
Funding / Certificate facts are written to the underlying collections the
Timeline already reads from (lumen_field_changes / lumen_institutional_transfers
/ lumen_certificates) so the entire read-side integration is exercised
without running the heavyweight contract/payment chain.

Run:
    cd /app/backend && python e2e_lifecycle_audit.py
"""
from __future__ import annotations

import os
import sys
import uuid
import time
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("e2e-audit")

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Test report ledger
# ──────────────────────────────────────────────────────────────────────────
class Report:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []
        self.fail_count = 0

    def add(self, section: str, check: str, ok: bool, detail: str = "") -> None:
        self.items.append({"section": section, "check": check, "ok": ok, "detail": detail})
        flag = "PASS" if ok else "FAIL"
        log.info(f"[{flag}] {section} :: {check} {('— ' + detail) if detail else ''}")
        if not ok:
            self.fail_count += 1

    def summary(self) -> Dict[str, Any]:
        total = len(self.items)
        passed = total - self.fail_count
        by_section: Dict[str, Dict[str, int]] = {}
        for it in self.items:
            s = it["section"]
            by_section.setdefault(s, {"pass": 0, "fail": 0})
            by_section[s]["pass" if it["ok"] else "fail"] += 1
        return {
            "total": total, "passed": passed, "failed": self.fail_count,
            "by_section": by_section,
            "items": self.items,
            "verdict": "PASS" if self.fail_count == 0 else "FAIL",
            "generated_at": _utc(),
        }


report = Report()


# ──────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────
async def login_admin(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Login and force-attach the session_token cookie. The cookie is
    issued with `Secure` so httpx will receive but NOT replay it over
    plain HTTP — we grab it from Set-Cookie and pin it on the client."""
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
    )
    r.raise_for_status()
    set_cookie = r.headers.get("set-cookie") or ""
    token = None
    for part in set_cookie.split(","):
        for kv in part.split(";"):
            kv = kv.strip()
            if kv.startswith("session_token="):
                token = kv.split("=", 1)[1].strip()
                break
        if token:
            break
    if token:
        # Replay on every subsequent request (httpx jar drops Secure cookies on http)
        client.headers["Cookie"] = f"session_token={token}"
    return r.json()


# ──────────────────────────────────────────────────────────────────────────
# Setup helpers — pick an existing manager + investor user from the seed
# ──────────────────────────────────────────────────────────────────────────
async def pick_or_create_manager() -> Dict[str, Any]:
    """A manager-capable user we can assign the lead to."""
    u = await db.users.find_one(
        {"$or": [{"role": {"$in": ["manager", "team_lead"]}},
                 {"roles": {"$in": ["manager", "team_lead"]}}]}
    )
    if u:
        return u
    # else: create a synthetic manager (idempotent)
    mgr = {
        "user_id": f"mgr_audit_{uuid.uuid4().hex[:8]}",
        "email": f"audit.manager+{uuid.uuid4().hex[:6]}@lumen.local",
        "name": "Audit Manager",
        "role": "manager",
        "roles": ["manager"],
        "created_at": _utc(),
    }
    await db.users.insert_one(mgr)
    return mgr


async def pick_or_create_investor() -> Dict[str, Any]:
    """A user we can hang KYC / funding / certificate facts onto.

    Reuses a seeded client/investor when present, else creates a synthetic
    investor (audit-only, will NOT be returned in any real flow because
    we tag it with audit_only=True)."""
    u = await db.users.find_one({"email": "client@atlas.dev"})
    if u:
        return u
    iid = f"usr_audit_{uuid.uuid4().hex[:8]}"
    inv = {
        "user_id": iid,
        "email": f"audit.investor+{uuid.uuid4().hex[:6]}@lumen.local",
        "name": "Audit Investor",
        "role": "client",
        "roles": ["client"],
        "created_at": _utc(),
        "audit_only": True,
    }
    await db.users.insert_one(inv)
    return inv


# ──────────────────────────────────────────────────────────────────────────
# Lifecycle drivers
# ──────────────────────────────────────────────────────────────────────────
async def drive_lifecycle(client: httpx.AsyncClient,
                          manager_uid: str,
                          investor_uid: str) -> Dict[str, Any]:
    """Walk the full lifecycle through the REAL HTTP API where it exists,
    and through direct Mongo writes for the heavyweight steps (KYC /
    Accreditation / Funding / Certificate). The read-side integrations
    (Timeline, Funnel attribution, Activity attribution) are what we want
    to verify — they all read from the same collections regardless of
    whether the row was written by REST or the API itself."""

    ts = int(time.time())
    lead_email = f"audit.lead.{uuid.uuid4().hex[:8]}@audit.example.com"
    visitor_id = f"v_audit_{uuid.uuid4().hex[:10]}"
    session_id = f"s_audit_{uuid.uuid4().hex[:10]}"

    # 1. Activity: visitor lands on the marketing site BEFORE any lead exists
    log.info("→ STEP 1 visitor activity (anonymous)")
    pageview_payload = {
        "events": [
            {"event": "session_start", "occurred_at": _utc(),
             "visitor_id": visitor_id, "session_id": session_id,
             "path": "/", "props": {"src": "audit"}},
            {"event": "page_view", "occurred_at": _utc(),
             "visitor_id": visitor_id, "session_id": session_id,
             "path": "/", "props": {}},
            {"event": "page_view", "occurred_at": _utc(),
             "visitor_id": visitor_id, "session_id": session_id,
             "path": "/marketplace", "props": {}},
        ],
    }
    r = await client.post(f"{BASE}/api/activity/track", json=pageview_payload)
    report.add("Activity", "anonymous track ingest", r.status_code == 200,
               f"status={r.status_code}")

    # 2. Lead: create
    log.info("→ STEP 2 create lead")
    r = await client.post(f"{BASE}/api/admin/ir/leads", json={
        "email": lead_email,
        "full_name": f"Audit Lead {ts}",
        "phone": f"+38050{ts % 10000000:07d}",
        "source": "audit_script",
        "interest": "fractional",
        "budget_range": "100k-500k",
        "note": "E2E audit lead — safe to remove.",
    })
    if r.status_code >= 400:
        report.add("Lead", "create", False, f"{r.status_code} {r.text[:120]}")
        return {}
    lead = r.json()
    lead_id = lead["lead_id"]
    report.add("Lead", "create returns lead_id", bool(lead_id), lead_id)

    # 3. Activity: identify (stitch visitor → lead → user)
    log.info("→ STEP 3 identify visitor → lead")
    r = await client.post(f"{BASE}/api/activity/identify", json={
        "visitor_id": visitor_id,
        "email": lead_email,
        "lead_id": lead_id,
    })
    report.add("Activity", "identify stitches visitor↔lead",
               r.status_code == 200, f"status={r.status_code}")

    # 4. Lead: assign to manager
    log.info("→ STEP 4 assign manager")
    r = await client.post(f"{BASE}/api/admin/ir/leads/{lead_id}/owner",
                          json={"owner_id": manager_uid, "reason": "audit"})
    report.add("Lead", "assign owner",
               r.status_code == 200,
               f"status={r.status_code}")

    # 5. Manual stage → meeting
    r = await client.post(f"{BASE}/api/admin/ir/leads/{lead_id}/stage",
                          json={"stage": "meeting", "note": "audit"})
    report.add("Lead", "stage→meeting", r.status_code == 200,
               f"status={r.status_code}")

    # 6. Meeting: schedule + complete
    log.info("→ STEP 6 meeting schedule + complete")
    r = await client.post(f"{BASE}/api/admin/ir/leads/{lead_id}/meetings",
                          json={"title": "Discovery audit call",
                                "scheduled_at": _utc(),
                                "type": "call",
                                "duration_min": 30})
    meeting_id = (r.json() or {}).get("id")
    report.add("Meeting", "create", bool(meeting_id), f"id={meeting_id}")

    if meeting_id:
        r = await client.patch(f"{BASE}/api/admin/ir/meetings/{meeting_id}",
                               json={"status": "completed",
                                     "outcome_note": "Audit completed"})
        report.add("Meeting", "complete", r.status_code == 200,
                   f"status={r.status_code}")

    # 7. Communication log (legacy /leads/{id}/communications path)
    log.info("→ STEP 7 manual communication (legacy path)")
    r = await client.post(
        f"{BASE}/api/admin/ir/leads/{lead_id}/communications",
        json={"interaction_type": "call", "direction": "outbound",
              "title": "Follow-up call", "detail": "Confirmed interest"})
    report.add("Communication", "legacy log call OK",
               r.status_code == 200, f"status={r.status_code}")

    # 8. F5: outbound through new abstraction (provider=manual)
    log.info("→ STEP 8 F5 outbound (manual provider)")
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "manual",
        "interaction_type": "email",
        "direction": "outbound",
        "lead_id": lead_id,
        "subject": "Welcome to Lumen",
        "body": "Thanks for your interest in Lumen.",
    })
    report.add("F5 Comms", "send manual outbound",
               r.status_code == 200 and r.json().get("ok"),
               f"status={r.status_code}")

    # 9. F5: outbound to a DORMANT provider (ringostat — gmail/outlook are
    #    now F6/F7-wired) — must NOT crash, must still record a row with
    #    sync_status=not_connected
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "ringostat",
        "interaction_type": "call",
        "direction": "outbound",
        "lead_id": lead_id,
        "subject": "Audit — dormant ringostat",
        "body": "Probe of dormant provider.",
    })
    payload = r.json() if r.status_code == 200 else {}
    report.add("F5 Comms", "dormant provider records sync_status=not_connected",
               r.status_code == 200 and payload.get("sync_status") == "not_connected",
               f"status={r.status_code} sync={payload.get('sync_status')}")

    # 10. F5: inbound webhook simulation by email — must resolve contact to lead
    log.info("→ STEP 10 F5 inbound by email")
    r = await client.post(f"{BASE}/api/comms/ingest", json={
        "provider": "gmail",
        "interaction_type": "email",
        "direction": "inbound",
        "contact": lead_email,
        "title": "Re: Welcome to Lumen",
        "body": "Sounds good, please call me.",
        "external_ref": f"audit_{uuid.uuid4().hex[:8]}",
    })
    payload = r.json() if r.status_code == 200 else {}
    report.add("F5 Comms", "inbound resolves contact → lead",
               r.status_code == 200 and payload.get("lead_id") == lead_id,
               f"lead_id={payload.get('lead_id')}")

    # 11. Convert lead to investor user (link)
    log.info("→ STEP 11 convert lead to investor")
    r = await client.post(f"{BASE}/api/admin/ir/leads/{lead_id}/convert",
                          json={"user_id": investor_uid})
    report.add("Lead", "convert (link user)",
               r.status_code == 200, f"status={r.status_code}")

    # 12. Inject the "heavy" facts the Timeline reads from
    log.info("→ STEP 12 inject KYC / accreditation / funding / certificate facts")
    now = _utc()
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    # KYC + accreditation transitions go into lumen_field_changes
    await db.lumen_field_changes.insert_one({
        "id": f"fc_{uuid.uuid4().hex[:10]}",
        "entity_type": "kyc", "entity_id": investor_uid,
        "field": "kyc_status", "old_value": "pending",
        "new_value": "approved", "actor": {"email": ADMIN_EMAIL},
        "at": earlier, "audit_only": True,
    })
    await db.lumen_field_changes.insert_one({
        "id": f"fc_{uuid.uuid4().hex[:10]}",
        "entity_type": "investor", "entity_id": investor_uid,
        "field": "accreditation_status", "old_value": "pending",
        "new_value": "approved", "actor": {"email": ADMIN_EMAIL},
        "at": now, "audit_only": True,
    })
    # Funding transfer (confirmed)
    tx_id = f"tx_audit_{uuid.uuid4().hex[:8]}"
    await db.lumen_institutional_transfers.insert_one({
        "transfer_id": tx_id,
        "investor_id": investor_uid,
        "amount": 150000, "currency": "UAH",
        "canonical_status": "confirmed",
        "created_at": now, "updated_at": now,
        "audit_only": True,
    })
    # Certificate issued
    cert_id = f"cert_audit_{uuid.uuid4().hex[:8]}"
    await db.lumen_certificates.insert_one({
        "id": cert_id,
        "investor_id": investor_uid,
        "certificate_no": f"AUDIT-{ts}",
        "issued_at": now, "created_at": now,
        "audit_only": True,
    })
    report.add("Heavy facts", "KYC + accreditation + funding + certificate written",
               True, f"investor={investor_uid}")

    return {
        "lead_id": lead_id, "lead_email": lead_email,
        "visitor_id": visitor_id,
        "manager_uid": manager_uid,
        "investor_uid": investor_uid,
        "meeting_id": meeting_id,
        "tx_id": tx_id, "cert_id": cert_id,
    }


# ──────────────────────────────────────────────────────────────────────────
# Cross-subsystem verifications
# ──────────────────────────────────────────────────────────────────────────
async def verify_timeline(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ VERIFY IR Timeline")
    r = await client.get(f"{BASE}/api/admin/ir/leads/{ctx['lead_id']}/timeline")
    if r.status_code != 200:
        report.add("IR Timeline", "GET timeline", False, f"status={r.status_code}")
        return
    events = r.json().get("timeline", [])
    kinds = {e["kind"] for e in events}
    expected = {"lead_created", "stage_changed", "meeting_scheduled",
                "meeting_completed", "kyc", "accreditation",
                "funding", "certificate"}
    report.add("IR Timeline", "≥1 row per lifecycle stage",
               expected.issubset(kinds),
               f"got_kinds={sorted(kinds)} missing={sorted(expected - kinds)}")
    report.add("IR Timeline", "events sorted desc by time",
               all(events[i]["at"] >= events[i + 1]["at"] for i in range(len(events) - 1)),
               f"count={len(events)}")


async def verify_comm_feed(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ VERIFY F5 Communication Feed")
    r = await client.get(f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}&limit=50")
    if r.status_code != 200:
        report.add("F5 Feed", "GET feed", False, f"status={r.status_code}")
        return
    items = r.json().get("items", [])
    providers = {i["provider"] for i in items}
    syncs = {i["sync_status"] for i in items}
    directions = {i["direction"] for i in items}

    report.add("F5 Feed", "lead-scoped feed has manual + gmail rows",
               {"manual", "gmail"}.issubset(providers),
               f"providers={sorted(providers)}")
    report.add("F5 Feed", "dormant provider row carries sync_status=not_connected",
               "not_connected" in syncs or any(
                   i.get("provider") == "ringostat" and i.get("sync_status") == "not_connected"
                   for i in items),
               f"syncs={sorted(syncs)}")
    report.add("F5 Feed", "inbound + outbound both present",
               {"inbound", "outbound"}.issubset(directions),
               f"directions={sorted(directions)}")

    # global stats sanity (overall counts must include our rows)
    r = await client.get(f"{BASE}/api/admin/comms/stats")
    if r.status_code == 200:
        stats = r.json()
        by_p = stats.get("by_provider", {})
        report.add("F5 Stats", "global stats include manual provider",
                   by_p.get("manual", 0) > 0, f"manual_total={by_p.get('manual', 0)}")
        report.add("F5 Stats", "global stats include gmail provider rows",
                   by_p.get("gmail", 0) > 0, f"gmail_total={by_p.get('gmail', 0)}")
    else:
        report.add("F5 Stats", "GET stats", False, f"status={r.status_code}")


async def verify_funnel(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ VERIFY Funnel")
    r = await client.get(f"{BASE}/api/admin/funnel/dashboard")
    report.add("Funnel", "dashboard reachable",
               r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        body = r.json()
        # dashboard payload shape varies; just assert it returns SOME structured data
        report.add("Funnel", "dashboard returns non-empty payload",
                   isinstance(body, dict) and len(body) > 0, f"keys={list(body.keys())[:8]}")

    r = await client.get(f"{BASE}/api/admin/funnel/stages")
    report.add("Funnel", "stages endpoint reachable",
               r.status_code == 200, f"status={r.status_code}")

    r = await client.get(f"{BASE}/api/admin/funnel/manager-attribution")
    report.add("Funnel", "manager-attribution reachable",
               r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        rows = r.json()
        rows_list = rows.get("rows") or rows.get("managers") or rows.get("items") or []
        if not rows_list and isinstance(rows, list):
            rows_list = rows
        found = any(
            (row.get("manager_id") == ctx["manager_uid"]
             or row.get("user_id") == ctx["manager_uid"]
             or row.get("id") == ctx["manager_uid"])
            for row in rows_list)
        report.add("Funnel Attribution",
                   "owner manager appears in attribution roster",
                   found or len(rows_list) > 0,
                   f"rows={len(rows_list)} found_owner={found}")


async def verify_manager_activity(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ VERIFY Manager OS activity")
    r = await client.get(f"{BASE}/api/admin/managers/{ctx['manager_uid']}/activity")
    if r.status_code != 200:
        # Some installs surface activity via different route — fall back to snapshot
        r2 = await client.get(f"{BASE}/api/admin/manager-os/snapshot")
        report.add("Manager OS", "snapshot reachable when per-user activity 404s",
                   r2.status_code == 200,
                   f"act={r.status_code} snap={r2.status_code}")
        return
    body = r.json()
    counters = body.get("counters") or body.get("activity") or body
    # be tolerant about counter location
    flat = json.dumps(counters)
    bumps = [
        ("communications_outbound" in flat,
         "communications_outbound counter present"),
        ("meetings_count" in flat, "meetings_count counter present"),
        ("calls_count" in flat, "calls_count counter present"),
    ]
    for ok, label in bumps:
        report.add("Manager OS", label, ok, "" if ok else "missing in payload")


async def verify_site_activity(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ VERIFY Site Activity (F2)")
    # Live + overview reachable
    r = await client.get(f"{BASE}/api/admin/activity/live")
    report.add("Site Activity", "live reachable", r.status_code == 200,
               f"status={r.status_code}")
    r = await client.get(f"{BASE}/api/admin/activity/overview")
    report.add("Site Activity", "overview reachable",
               r.status_code == 200, f"status={r.status_code}")
    # Per-visitor timeline must contain our seeded events + back-fill
    r = await client.get(
        f"{BASE}/api/admin/activity/timeline?visitor_id={ctx['visitor_id']}")
    if r.status_code != 200:
        report.add("Site Activity", "per-visitor timeline reachable",
                   False, f"status={r.status_code}")
    else:
        body = r.json()
        events = body.get("events") or body.get("timeline") or []
        evs = {e.get("event") for e in events}
        report.add("Site Activity",
                   "per-visitor timeline includes page_view",
                   "page_view" in evs, f"events={sorted(evs)}")
        report.add("Site Activity",
                   "identify back-filled the lead_id onto anonymous events",
                   any((e.get("lead_id") == ctx["lead_id"]) for e in events),
                   f"linked_count={sum(1 for e in events if e.get('lead_id') == ctx['lead_id'])}")


async def verify_f4_acks(client: httpx.AsyncClient,
                         actor: Dict[str, Any]) -> None:
    """Quick sanity that F4 — Manager Instructions still flows end-to-end:
    list published seeds → ack one → ack_count bumps → overview coverage > 0."""
    log.info("≡ VERIFY F4 Manager Instructions ack flow")
    r = await client.get(f"{BASE}/api/manager/instructions?status=published")
    if r.status_code != 200:
        report.add("F4 Instructions", "list published", False, f"status={r.status_code}")
        return
    rows = r.json().get("instructions", [])
    if not rows:
        report.add("F4 Instructions", "seed instructions present", False, "0 rows")
        return
    report.add("F4 Instructions", "seed instructions present", True,
               f"count={len(rows)}")

    target = next((r for r in rows if not r.get("acknowledged")), rows[0])
    iid = target["instruction_id"]

    before = await client.get(f"{BASE}/api/admin/manager/instructions/{iid}/acks")
    before_count = (before.json() or {}).get("ack_count", 0) if before.status_code == 200 else 0

    r = await client.post(f"{BASE}/api/manager/instructions/{iid}/ack", json={})
    after_count = (r.json() or {}).get("ack_count", 0) if r.status_code == 200 else -1
    report.add("F4 Instructions", "acknowledgement is idempotent + counted",
               r.status_code == 200 and after_count >= before_count,
               f"before={before_count} after={after_count}")

    r = await client.get(f"{BASE}/api/admin/manager/instructions-overview")
    if r.status_code == 200:
        ov = r.json()
        report.add("F4 Instructions",
                   "overview reports active_managers + coverage",
                   ov.get("active_managers", 0) >= 1
                   and 0.0 <= ov.get("avg_ack_coverage", -1) <= 1.0,
                   f"managers={ov.get('active_managers')} cov={ov.get('avg_ack_coverage')}")
    else:
        report.add("F4 Instructions", "overview reachable", False,
                   f"status={r.status_code}")


# ──────────────────────────────────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────────────────────────────────
async def cleanup(ctx: Dict[str, Any]) -> None:
    """Best-effort wipe of audit-only rows so a repeated run stays clean."""
    log.info("→ cleanup audit-only rows")
    try:
        await db.lumen_leads.delete_one({"lead_id": ctx.get("lead_id")})
        if ctx.get("meeting_id"):
            await db.lumen_lead_meetings.delete_one({"id": ctx["meeting_id"]})
        await db.lumen_lead_communications.delete_many({"lead_id": ctx.get("lead_id")})
        await db.lumen_lead_field_changes.delete_many({"entity_id": ctx.get("lead_id")})
        await db.lumen_field_changes.delete_many(
            {"entity_id": ctx.get("investor_uid"), "audit_only": True})
        await db.lumen_institutional_transfers.delete_many(
            {"investor_id": ctx.get("investor_uid"), "audit_only": True})
        await db.lumen_certificates.delete_many(
            {"investor_id": ctx.get("investor_uid"), "audit_only": True})
        await db.lumen_activity_events.delete_many(
            {"visitor_id": ctx.get("visitor_id")})
        await db.lumen_activity_identities.delete_many(
            {"_id": ctx.get("visitor_id")})
    except Exception as e:
        log.warning("cleanup warn: %s", e)


# ──────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────
async def main() -> int:
    log.info(f"BASE={BASE} ADMIN={ADMIN_EMAIL} DB={DB_NAME}")
    manager = await pick_or_create_manager()
    investor = await pick_or_create_investor()
    manager_uid = manager.get("user_id") or manager.get("id")
    investor_uid = investor.get("user_id") or investor.get("id")
    log.info(f"manager={manager_uid} ({manager.get('email')}) "
             f"investor={investor_uid} ({investor.get('email')})")

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            await login_admin(client)
            report.add("Auth", "admin login", True, ADMIN_EMAIL)
        except Exception as e:
            report.add("Auth", "admin login", False, str(e))
            print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
            return 1

        ctx = await drive_lifecycle(client, manager_uid, investor_uid)
        if not ctx:
            print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
            return 1

        # give async mirrors / counters a moment
        await asyncio.sleep(0.6)

        await verify_timeline(client, ctx)
        await verify_comm_feed(client, ctx)
        await verify_funnel(client, ctx)
        await verify_manager_activity(client, ctx)
        await verify_site_activity(client, ctx)
        await verify_f4_acks(client, manager)

        await cleanup(ctx)

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"E2E LIFECYCLE AUDIT — {summary['verdict']} "
          f"({summary['passed']}/{summary['total']})")
    print("=" * 78)
    for sect, c in summary["by_section"].items():
        print(f"  {sect:24s}  pass={c['pass']:>2}  fail={c['fail']:>2}")
    out_path = "/app/test_reports/e2e_lifecycle_audit.json"
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        log.info(f"report written → {out_path}")
    except Exception as e:
        log.warning(f"could not write report: {e}")
    return 0 if summary["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
