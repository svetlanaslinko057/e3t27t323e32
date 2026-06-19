"""
LUMEN — Communication Regression Audit
======================================

Third harness, sibling to ``e2e_lifecycle_audit.py`` (business chain) and
``infra_regression_audit.py`` (plumbing). This one freezes the
**Communication contour contract** before any real adapter ships.

After F6 Gmail / F7 Ringostat / F8 Twilio, real-channel traffic will hit
this stack hard — so every invariant the IR / Manager OS / Funnel /
Activity layers rely on must be verifiable in isolation.

What this audit certifies (≈22 invariants across 9 sections):
  • OUTBOUND     — `/comms/send` writes through the single ingestion core,
                   manual → sync_status=`logged`.
  • DORMANT      — sending via a not-yet-connected provider records the
                   row with sync_status=`not_connected` (no transmission,
                   but FULL audit trail preserved).
  • INBOUND      — `/comms/ingest` writes with direction=inbound,
                   sync_status=`received`.
  • CONTACT RES. — email → lead linking; phone → lead linking; unknown
                   contact still records (matched_contact=false).
  • THREAD LINK  — two inbound rows with the same `thread_ref` group
                   together via a direct mongo query (proves the column
                   F6/F7 webhooks will key off is being persisted).
  • PROVIDER ST. — activation guard 409 (cannot activate dormant without
                   adapter); disable/enable; provider test endpoint
                   reports `connected` correctly.
  • DEDUP        — two `/comms/send` calls with the same `external_ref`
                   collapse to ONE row in `lumen_lead_communications`
                   (mirror_communication idempotency on
                   `source_collection + source_id + kind`).
  • COUNTERS     — `bump_activity` updates `communications_outbound` and
                   `calls_count` on the staff actor's manager-activity doc.
  • FEED HYGIENE — feed filtering by provider / direction / interaction_type
                   / q produces internally-consistent slices; sync_status
                   on every row ∈ {logged, queued, sent, delivered,
                   received, failed, not_connected}.

Run:
    cd /app/backend && python comm_regression_audit.py

Non-destructive: creates one synthetic lead, runs all comms against it,
cleans up afterwards.
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
ADMIN_EMAIL = os.environ.get("AUDIT_ADMIN_EMAIL", "admin@devos.io")
ADMIN_PASS = os.environ.get("AUDIT_ADMIN_PASS", "admin123")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comm-audit")

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]

VALID_SYNC = {"logged", "queued", "sent", "delivered",
              "received", "failed", "not_connected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Report ledger
# ──────────────────────────────────────────────────────────────────────────
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
            (self.warn_count if severity == "warn" else self.fail_count)
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
            "generated_at": _now(),
        }


report = Report()


# ──────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────
async def login_admin(client: httpx.AsyncClient) -> Dict[str, Any]:
    r = await client.post(f"{BASE}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
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
        client.headers["Cookie"] = f"session_token={token}"
    return r.json()


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────
async def create_audit_lead(client: httpx.AsyncClient) -> Dict[str, Any]:
    email = f"comm.audit.{uuid.uuid4().hex[:8]}@audit.example.com"
    phone = f"+38050{int(datetime.now().timestamp()) % 10000000:07d}"
    r = await client.post(f"{BASE}/api/admin/ir/leads", json={
        "email": email, "full_name": "Comm Audit Lead",
        "phone": phone, "source": "audit_comm",
        "note": "Comm regression audit — safe to remove.",
    })
    r.raise_for_status()
    lead = r.json()
    # owner = pick first manager-capable user
    mgr = await db.users.find_one(
        {"$or": [{"role": {"$in": ["manager", "team_lead"]}},
                 {"roles": {"$in": ["manager", "team_lead"]}}]})
    owner_id = (mgr or {}).get("user_id") if mgr else None
    if owner_id:
        await client.post(f"{BASE}/api/admin/ir/leads/{lead['lead_id']}/owner",
                          json={"owner_id": owner_id, "reason": "comm-audit"})
    return {"lead_id": lead["lead_id"], "email": email, "phone": phone,
            "owner_id": owner_id}


# ──────────────────────────────────────────────────────────────────────────
# Section 1 — Outbound (manual + dormant)
# ──────────────────────────────────────────────────────────────────────────
async def verify_outbound(client: httpx.AsyncClient, ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 1 / outbound")
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "manual", "interaction_type": "email", "direction": "outbound",
        "lead_id": ctx["lead_id"], "subject": "Welcome", "body": "Hi.",
    })
    payload = r.json() if r.status_code == 200 else {}
    report.add("Outbound", "manual outbound succeeds",
               r.status_code == 200 and payload.get("ok"), f"status={r.status_code}")
    report.add("Outbound", "manual outbound sync_status=logged",
               payload.get("sync_status") == "logged",
               f"sync={payload.get('sync_status')}")

    # NOTE: gmail (F6) + outlook (F7) are now wired — use ringostat (F8)
    # as the dormant probe.
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "ringostat", "interaction_type": "call", "direction": "outbound",
        "lead_id": ctx["lead_id"], "subject": "Probe ringostat", "body": "test",
    })
    payload = r.json() if r.status_code == 200 else {}
    report.add("Outbound", "dormant provider responds 200 (records intent)",
               r.status_code == 200, f"status={r.status_code}")
    report.add("Outbound", "dormant provider sync_status=not_connected",
               payload.get("sync_status") == "not_connected",
               f"sync={payload.get('sync_status')}")
    report.add("Outbound", "dormant provider ok=false (no transmission)",
               payload.get("ok") is False, f"ok={payload.get('ok')}")


# ──────────────────────────────────────────────────────────────────────────
# Section 2 — Inbound + contact resolution
# ──────────────────────────────────────────────────────────────────────────
async def verify_inbound_and_resolution(client: httpx.AsyncClient,
                                        ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 2 / inbound + contact resolution")
    # by email
    r = await client.post(f"{BASE}/api/comms/ingest", json={
        "provider": "gmail", "interaction_type": "email", "direction": "inbound",
        "contact": ctx["email"], "title": "Re: Welcome",
        "body": "Sounds good.", "external_ref": f"audit_em_{uuid.uuid4().hex[:8]}",
    })
    p = r.json() if r.status_code == 200 else {}
    report.add("Inbound", "ingest by email resolves lead_id",
               r.status_code == 200 and p.get("lead_id") == ctx["lead_id"]
               and p.get("matched_contact") is True,
               f"matched={p.get('matched_contact')} lead_id={p.get('lead_id')}")
    report.add("Inbound", "ingest by email sync_status=received",
               (p.get("comm") or {}).get("extra", {}).get("sync_status") == "received"
               or _row_sync(p) == "received",
               f"sync={_row_sync(p)}")

    # by phone
    r = await client.post(f"{BASE}/api/comms/ingest", json={
        "provider": "twilio", "interaction_type": "call", "direction": "inbound",
        "contact": ctx["phone"], "title": "Incoming call",
        "external_ref": f"audit_ph_{uuid.uuid4().hex[:8]}",
    })
    p = r.json() if r.status_code == 200 else {}
    report.add("Inbound", "ingest by phone resolves lead_id",
               r.status_code == 200 and p.get("lead_id") == ctx["lead_id"]
               and p.get("matched_contact") is True,
               f"matched={p.get('matched_contact')} lead_id={p.get('lead_id')}")

    # unknown contact — still recorded, but matched=false
    r = await client.post(f"{BASE}/api/comms/ingest", json={
        "provider": "gmail", "interaction_type": "email", "direction": "inbound",
        "contact": f"unknown.{uuid.uuid4().hex[:8]}@audit.example.com",
        "title": "Random outsider", "body": "huh",
        "external_ref": f"audit_unk_{uuid.uuid4().hex[:8]}",
    })
    p = r.json() if r.status_code == 200 else {}
    report.add("Inbound",
               "unknown contact still records (matched=false, lead_id=null)",
               r.status_code == 200 and p.get("matched_contact") is False
               and p.get("lead_id") is None,
               f"matched={p.get('matched_contact')} lead_id={p.get('lead_id')}")


def _row_sync(p: Dict[str, Any]) -> Optional[str]:
    return ((p.get("comm") or {}).get("extra") or {}).get("sync_status")


# ──────────────────────────────────────────────────────────────────────────
# Section 3 — Thread linking
# ──────────────────────────────────────────────────────────────────────────
async def verify_thread_linking(client: httpx.AsyncClient,
                                ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 3 / thread linking")
    thread_ref = f"thread_audit_{uuid.uuid4().hex[:10]}"
    for i in range(2):
        r = await client.post(f"{BASE}/api/comms/ingest", json={
            "provider": "gmail", "interaction_type": "email",
            "direction": "inbound",
            "contact": ctx["email"],
            "title": f"Thread reply #{i}",
            "thread_ref": thread_ref,
            "external_ref": f"audit_th{i}_{uuid.uuid4().hex[:8]}",
        })
        report.add("Thread Linking", f"ingest #{i} OK",
                   r.status_code == 200, f"status={r.status_code}")
    # 1. Direct mongo — the field is persisted
    n = await db.lumen_lead_communications.count_documents(
        {"extra.thread_ref": thread_ref})
    report.add("Thread Linking",
               "thread_ref persists & groups two rows (mongo)",
               n == 2, f"rows_with_thread_ref={n}")

    # 2. API exposure — the feed row dict now carries thread_ref (F6 prereq)
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}&limit=200")
    items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    threaded = [i for i in items if i.get("thread_ref") == thread_ref]
    report.add("Thread Linking",
               "feed row exposes thread_ref to API",
               len(threaded) == 2,
               f"feed_rows_with_thread_ref={len(threaded)}")

    # 3. ?thread_ref= query filter on the feed
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?thread_ref={thread_ref}&limit=200")
    items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    report.add("Thread Linking",
               "feed filter ?thread_ref= returns exactly the thread rows",
               len(items) == 2 and all(
                   i.get("thread_ref") == thread_ref for i in items),
               f"filtered={len(items)}")

    # 4. /threads/{ref} grouping primitive (what F6 Gmail UI will key off)
    r = await client.get(f"{BASE}/api/admin/comms/threads/{thread_ref}")
    body = r.json() if r.status_code == 200 else {}
    msgs = body.get("messages", [])
    sorted_ok = all(msgs[i]["at"] <= msgs[i + 1]["at"]
                    for i in range(len(msgs) - 1))
    report.add("Thread Linking",
               "/admin/comms/threads/{ref} returns oldest→newest messages",
               r.status_code == 200 and body.get("count") == 2 and sorted_ok,
               f"count={body.get('count')} sorted_asc={sorted_ok}")
    report.add("Thread Linking",
               "thread view exposes providers + lead_ids aggregates",
               isinstance(body.get("providers"), list)
               and isinstance(body.get("lead_ids"), list)
               and "gmail" in body["providers"]
               and ctx["lead_id"] in body["lead_ids"],
               f"providers={body.get('providers')} leads={body.get('lead_ids')}")

    ctx["thread_ref"] = thread_ref


# ──────────────────────────────────────────────────────────────────────────
# Section 4 — Provider status transitions
# ──────────────────────────────────────────────────────────────────────────
async def verify_provider_transitions(client: httpx.AsyncClient) -> None:
    log.info("≡ Section 4 / provider status transitions")
    # catalogue intact
    r = await client.get(f"{BASE}/api/admin/comms/providers")
    body = r.json() if r.status_code == 200 else {}
    keys = {p["key"] for p in body.get("providers", [])}
    expected = {"manual", "ringostat", "binotel", "twilio",
                "sip", "gmail", "outlook", "telegram", "whatsapp"}
    report.add("Provider Status",
               "catalogue intact (9 providers)",
               expected.issubset(keys),
               f"got={sorted(keys)} missing={sorted(expected - keys)}")

    # Activation guard: PATCH ringostat status=active → 409 (no adapter)
    # (gmail moved to F6-wired, outlook to F7-wired; ringostat stays dormant
    # until F8.)
    r = await client.patch(f"{BASE}/api/admin/comms/providers/ringostat",
                           json={"status": "active"})
    report.add("Provider Status",
               "activation guard 409 on dormant provider without adapter",
               r.status_code == 409, f"status={r.status_code}")

    # Disable manual → /comms/send manual should 409
    r = await client.patch(f"{BASE}/api/admin/comms/providers/manual",
                           json={"status": "disabled"})
    report.add("Provider Status",
               "manual can be disabled",
               r.status_code == 200, f"status={r.status_code}")
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "manual", "interaction_type": "note",
        "direction": "outbound", "body": "should fail",
    })
    report.add("Provider Status",
               "send through disabled provider rejected (409)",
               r.status_code == 409, f"status={r.status_code}")

    # Re-enable manual
    r = await client.patch(f"{BASE}/api/admin/comms/providers/manual",
                           json={"status": "active"})
    report.add("Provider Status",
               "manual can be re-enabled",
               r.status_code == 200, f"status={r.status_code}")

    # Test endpoint contracts
    r = await client.post(f"{BASE}/api/admin/comms/providers/manual/test")
    body = r.json() if r.status_code == 200 else {}
    report.add("Provider Status",
               "manual /test reports connected=true",
               body.get("connected") is True, f"resp={body.get('result')}")
    r = await client.post(f"{BASE}/api/admin/comms/providers/ringostat/test")
    body = r.json() if r.status_code == 200 else {}
    report.add("Provider Status",
               "ringostat /test reports connected=false (no adapter yet)",
               body.get("connected") is False, f"resp={body.get('result')}")


# ──────────────────────────────────────────────────────────────────────────
# Section 5 — Duplicate suppression (idempotency)
# ──────────────────────────────────────────────────────────────────────────
async def verify_dedup(client: httpx.AsyncClient,
                       ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 5 / duplicate suppression")
    ext_ref = f"audit_dedup_{uuid.uuid4().hex[:10]}"
    # POST twice with the SAME external_ref + same kind → mirror_communication
    # idempotency on (source_collection, source_id, kind) should collapse.
    for i in range(2):
        r = await client.post(f"{BASE}/api/comms/send", json={
            "provider": "manual", "interaction_type": "email",
            "direction": "outbound",
            "lead_id": ctx["lead_id"],
            "subject": "Idempotent probe",
            "body": "x", "external_ref": ext_ref,
        })
        report.add("Dedup", f"send #{i} OK",
                   r.status_code == 200, f"status={r.status_code}")
    n = await db.lumen_lead_communications.count_documents(
        {"source_id": ext_ref})
    report.add("Dedup",
               "duplicate external_ref collapses to a single row",
               n == 1, f"rows_with_ext_ref={n}")

    # Inbound idempotency — same external_ref + provider should also dedup
    ext_ref_in = f"audit_dedup_in_{uuid.uuid4().hex[:10]}"
    for i in range(2):
        r = await client.post(f"{BASE}/api/comms/ingest", json={
            "provider": "gmail", "interaction_type": "email",
            "direction": "inbound", "contact": ctx["email"],
            "title": "Idempotent inbound",
            "external_ref": ext_ref_in,
        })
        report.add("Dedup", f"ingest #{i} OK",
                   r.status_code == 200, f"status={r.status_code}")
    n = await db.lumen_lead_communications.count_documents(
        {"source_id": ext_ref_in})
    report.add("Dedup",
               "inbound dedup also collapses on same external_ref",
               n == 1, f"rows_with_ext_ref={n}")


# ──────────────────────────────────────────────────────────────────────────
# Section 6 — sync_status lifecycle whitelist
# ──────────────────────────────────────────────────────────────────────────
async def verify_sync_status_lifecycle(client: httpx.AsyncClient,
                                       ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 6 / sync_status lifecycle")
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}&limit=200")
    items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    syncs = {(i.get("sync_status") or "").lower() for i in items}
    bad = [s for s in syncs if s and s not in VALID_SYNC]
    report.add("sync_status",
               "every row has a whitelisted sync_status",
               not bad, f"observed={sorted(syncs)} bad={bad}")
    # At least: logged (manual), not_connected (gmail outbound), received (inbound)
    expected_obs = {"logged", "not_connected", "received"}
    report.add("sync_status",
               "observed {logged, not_connected, received} in this run",
               expected_obs.issubset(syncs),
               f"missing={sorted(expected_obs - syncs)}")


# ──────────────────────────────────────────────────────────────────────────
# Section 7 — Manager counters + attribution coherence
# ──────────────────────────────────────────────────────────────────────────
async def verify_counters_and_attribution(client: httpx.AsyncClient,
                                          ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 7 / manager counters + attribution")
    owner_id = ctx.get("owner_id")
    if not owner_id:
        report.add("Counters", "lead owner present", False,
                   "no manager-capable user found")
        return

    # Snapshot counters BEFORE the bump
    before = await db.lumen_manager_activity.find_one({"user_id": owner_id}) or {}
    out_before = before.get("communications_outbound", 0)
    calls_before = before.get("calls_count", 0)

    # Send an outbound call FROM the admin acting as the staff actor.
    # NOTE: send() uses the LOGGED-IN user (admin) as actor, not the lead owner.
    # So we verify against the admin's manager_activity counters (which IS
    # also bumped because admin is staff and bump_activity is by actor).
    admin_user_id = (await db.users.find_one({"email": ADMIN_EMAIL}) or {}).get("user_id")

    a_before = await db.lumen_manager_activity.find_one(
        {"user_id": admin_user_id}) or {}
    a_out_before = a_before.get("communications_outbound", 0)
    a_calls_before = a_before.get("calls_count", 0)

    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "manual", "interaction_type": "call",
        "direction": "outbound", "lead_id": ctx["lead_id"],
        "subject": "Counter probe call", "body": "x",
    })
    report.add("Counters", "probe call send OK",
               r.status_code == 200, f"status={r.status_code}")
    await asyncio.sleep(0.4)

    a_after = await db.lumen_manager_activity.find_one(
        {"user_id": admin_user_id}) or {}
    a_out_after = a_after.get("communications_outbound", 0)
    a_calls_after = a_after.get("calls_count", 0)

    report.add("Counters",
               "communications_outbound bumped on send",
               a_out_after >= a_out_before + 1,
               f"{a_out_before} → {a_out_after}")
    report.add("Counters",
               "calls_count bumped when interaction_type=call",
               a_calls_after >= a_calls_before + 1,
               f"{a_calls_before} → {a_calls_after}")

    # inbound bump test
    r = await client.post(f"{BASE}/api/comms/ingest", json={
        "provider": "gmail", "interaction_type": "email",
        "direction": "inbound", "contact": ctx["email"],
        "title": "inbound counter probe",
        "external_ref": f"audit_cn_{uuid.uuid4().hex[:8]}",
    })
    await asyncio.sleep(0.4)
    a_after2 = await db.lumen_manager_activity.find_one(
        {"user_id": admin_user_id}) or {}
    report.add("Counters",
               "communications_inbound bumped on ingest",
               a_after2.get("communications_inbound", 0) >=
               (a_after.get("communications_inbound", 0) + 1),
               f"{a_after.get('communications_inbound', 0)} → "
               f"{a_after2.get('communications_inbound', 0)}")

    # Attribution coherence: the rows we just produced ARE attached to a
    # lead that has an owner → IR Timeline must list them, and the lead's
    # owner remains stable through it.
    r = await client.get(
        f"{BASE}/api/admin/ir/leads/{ctx['lead_id']}")
    if r.status_code == 200:
        lead = r.json()
        report.add("Attribution",
                   "lead owner_id stable after comm storm",
                   lead.get("owner_id") == owner_id,
                   f"owner_id={lead.get('owner_id')}")


# ──────────────────────────────────────────────────────────────────────────
# Section 8 — Feed filter hygiene
# ──────────────────────────────────────────────────────────────────────────
async def verify_feed_filters(client: httpx.AsyncClient,
                              ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 8 / feed filter hygiene")
    # all rows for this lead
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}&limit=200")
    all_items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    n_all = len(all_items)

    # filter by provider
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}"
        f"&provider=gmail&limit=200")
    gmail_items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    report.add("Feed Filters",
               "provider filter returns subset",
               len(gmail_items) <= n_all
               and all(i["provider"] == "gmail" for i in gmail_items),
               f"all={n_all} gmail={len(gmail_items)}")

    # filter by direction=inbound
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}"
        f"&direction=inbound&limit=200")
    in_items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    report.add("Feed Filters",
               "direction=inbound filter holds",
               all(i["direction"] == "inbound" for i in in_items),
               f"inbound_rows={len(in_items)}")

    # filter by interaction_type=email
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}"
        f"&interaction_type=email&limit=200")
    em_items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    report.add("Feed Filters",
               "interaction_type=email filter holds",
               all(i["interaction_type"] == "email" for i in em_items),
               f"email_rows={len(em_items)}")

    # q text search
    r = await client.get(
        f"{BASE}/api/admin/comms/feed?lead_id={ctx['lead_id']}"
        f"&q=Welcome&limit=200")
    q_items = (r.json() or {}).get("items", []) if r.status_code == 200 else []
    report.add("Feed Filters",
               "q text search returns ≥1 hit on seeded subject",
               len(q_items) >= 1, f"q_rows={len(q_items)}")


# ──────────────────────────────────────────────────────────────────────────
# Section 9 — Input whitelisting (interaction_type / direction)
# ──────────────────────────────────────────────────────────────────────────
async def verify_input_coercion(client: httpx.AsyncClient,
                                ctx: Dict[str, Any]) -> None:
    log.info("≡ Section 9 / input coercion")
    ext_ref = f"audit_coerce_{uuid.uuid4().hex[:10]}"
    r = await client.post(f"{BASE}/api/comms/send", json={
        "provider": "manual",
        "interaction_type": "NUKE_LAUNCH",   # not in whitelist
        "direction": "diagonal",             # not in whitelist
        "lead_id": ctx["lead_id"],
        "subject": "Coercion probe", "body": "x",
        "external_ref": ext_ref,
    })
    report.add("Input Coercion", "weird inputs do NOT 500",
               r.status_code == 200, f"status={r.status_code}")
    row = await db.lumen_lead_communications.find_one({"source_id": ext_ref})
    report.add("Input Coercion",
               "unknown interaction_type coerced to 'other'",
               (row or {}).get("interaction_type") == "other",
               f"got={(row or {}).get('interaction_type')}")
    report.add("Input Coercion",
               "invalid direction coerced to 'outbound'",
               (row or {}).get("direction") == "outbound",
               f"got={(row or {}).get('direction')}")


# ──────────────────────────────────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────────────────────────────────
async def cleanup(ctx: Dict[str, Any]) -> None:
    try:
        await db.lumen_leads.delete_one({"lead_id": ctx.get("lead_id")})
        await db.lumen_lead_communications.delete_many(
            {"lead_id": ctx.get("lead_id")})
        # unknown-contact + probe rows that have no lead_id binding
        await db.lumen_lead_communications.delete_many({
            "$or": [
                {"source_id": {"$regex": "^audit_"}},
                {"title": {"$regex": "Random outsider|Idempotent|Thread reply"
                                     "|Coercion probe|Counter probe"
                                     "|Probe gmail|Audit"}},
            ]
        })
        # ensure manual provider is back to active in case test left it disabled
        await db.lumen_communication_providers.update_one(
            {"key": "manual"}, {"$set": {"status": "active"}})
    except Exception as e:
        log.warning(f"cleanup warn: {e}")


# ──────────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────────
async def main() -> int:
    log.info(f"BASE={BASE} DB={DB_NAME}")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            await login_admin(client)
            report.add("Auth", "admin login", True, ADMIN_EMAIL)
        except Exception as e:
            report.add("Auth", "admin login", False, str(e))
            print(json.dumps(report.summary(), ensure_ascii=False, indent=2))
            return 1

        ctx = await create_audit_lead(client)
        report.add("Fixture", "audit lead created",
                   bool(ctx.get("lead_id")),
                   f"lead_id={ctx.get('lead_id')} owner={ctx.get('owner_id')}")

        try:
            await verify_outbound(client, ctx)
            await verify_inbound_and_resolution(client, ctx)
            await verify_thread_linking(client, ctx)
            await verify_provider_transitions(client)
            await verify_dedup(client, ctx)
            await verify_sync_status_lifecycle(client, ctx)
            await verify_counters_and_attribution(client, ctx)
            await verify_feed_filters(client, ctx)
            await verify_input_coercion(client, ctx)
        finally:
            await cleanup(ctx)

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"COMMUNICATION REGRESSION AUDIT — {summary['verdict']} "
          f"(pass={summary['passed']}/{summary['total']} "
          f"fail={summary['failed']} warn={summary['warned']})")
    print("=" * 78)
    for sect, c in summary["by_section"].items():
        print(f"  {sect:24s}  pass={c['pass']:>2}  fail={c['fail']:>2}  warn={c['warn']:>2}")

    out = "/app/test_reports/comm_regression_audit.json"
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
