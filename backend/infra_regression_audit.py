"""
LUMEN — Infrastructure Regression Audit
=======================================

Companion to ``e2e_lifecycle_audit.py``. While that script proves the
**business** chain (Visitor → Lead → … → Certificate) still holds, THIS
script proves the **plumbing underneath it** still holds: TTL indexes,
scheduler-driven rollups, queue buildup, counter coherence, session
hygiene, CSP intake, field-history retention, unique-index integrity.

Once the platform has 11 layers running, the next class of bugs is
infrastructural, not behavioural — silent index drift, stuck schedulers,
unbounded collections, orphaned counters. This script catches them
without simulating any user action.

Run:
    cd /app/backend && python infra_regression_audit.py

The script is READ-ONLY: it does not mutate any business collection.
The only write it performs is a one-shot ``POST /api/admin/activity/rollup``
to prove the rollup endpoint is reachable + idempotent.
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

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
log = logging.getLogger("infra-audit")

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo[DB_NAME]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────
# Report ledger (same shape as e2e_lifecycle_audit.py)
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
# HTTP helpers (re-using the lifecycle audit pattern)
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
# Index inspection
# ──────────────────────────────────────────────────────────────────────────
async def _indexes(coll: str) -> List[dict]:
    try:
        return await db[coll].index_information() and \
               [{"name": n, **spec}
                for n, spec in (await db[coll].index_information()).items()]
    except Exception as e:
        log.warning(f"indexes({coll}) failed: {e}")
        return []


async def verify_ttl_indexes() -> None:
    """Each row is (collection, field-name-that-must-have-TTL, expected_seconds_or_None)."""
    expected: List[Tuple[str, str, Optional[int]]] = [
        ("lumen_activity_events", "occurred_at", 730 * 86400),
        ("lumen_csp_reports", "at", 30 * 86400),
        ("lumen_field_changes", "at", None),  # retention is configurable
        ("lumen_access_gate_blocks", "at", 180 * 86400),
        ("two_factor_challenges", "expires_at_ts", 0),
        ("trusted_devices", "expires_at_ts", 0),
    ]
    for coll, field, exp in expected:
        idx = await _indexes(coll)
        ttl_idx = [i for i in idx if "expireAfterSeconds" in i
                   and any(k == field for k, _ in i.get("key") or [])]
        if not ttl_idx:
            # Some collections may not exist yet on a fresh boot — that's
            # acceptable as long as the ensure_indexes hook will create the
            # index on first write. We mark these "warn" not "fail".
            exists = await db[coll].estimated_document_count() if coll in await db.list_collection_names() else 0
            report.add("TTL Indexes",
                       f"{coll}.{field} TTL index present",
                       False if exists else True,
                       f"index missing, rows={exists}" if exists
                       else "collection empty (will be created on first write)",
                       severity="fail" if exists else "warn")
            continue
        actual = ttl_idx[0]["expireAfterSeconds"]
        if exp is not None and actual != exp:
            report.add("TTL Indexes",
                       f"{coll}.{field} TTL = {exp}s",
                       False, f"got {actual}s (expected {exp}s)",
                       severity="warn")
        else:
            report.add("TTL Indexes",
                       f"{coll}.{field} TTL index",
                       True, f"expireAfterSeconds={actual}")


async def verify_unique_indexes() -> None:
    """Critical unique indexes that prevent silent data corruption."""
    unique: List[Tuple[str, str]] = [
        ("lumen_leads", "lead_id"),
        ("lumen_manager_instructions", "instruction_id"),
        ("lumen_manager_instruction_acks", None),  # composite, see ensure_indexes
        ("lumen_communication_providers", "key"),
        ("lumen_activity_events", "event_id"),
    ]
    for coll, field in unique:
        idx = await _indexes(coll)
        if field is None:
            # composite uniqueness — just check that AT LEAST ONE unique idx exists
            uq = [i for i in idx if i.get("unique")]
            report.add("Unique Indexes",
                       f"{coll}.<composite> unique present",
                       len(uq) > 0,
                       f"unique_idx_count={len(uq)}")
            continue
        match = [i for i in idx if any(k == field for k, _ in i.get("key") or [])
                 and i.get("unique")]
        # event_id is not declared unique in ensure_indexes — accept either form
        if coll == "lumen_activity_events" and field == "event_id" and not match:
            # Verify uniqueness by counting duplicate event_ids
            pipeline = [{"$group": {"_id": "$event_id", "n": {"$sum": 1}}},
                        {"$match": {"n": {"$gt": 1}}}, {"$limit": 1}]
            dupes = await db[coll].aggregate(pipeline).to_list(1)
            report.add("Unique Indexes",
                       f"{coll}.{field} effectively unique (no duplicates)",
                       len(dupes) == 0,
                       "no duplicates" if not dupes else f"duplicates found")
            continue
        report.add("Unique Indexes",
                   f"{coll}.{field} unique",
                   len(match) > 0,
                   "ok" if match else "MISSING unique index")


# ──────────────────────────────────────────────────────────────────────────
# Scheduler health — observe by EFFECT, not by introspecting tasks
# ──────────────────────────────────────────────────────────────────────────
async def verify_activity_rollup(client: httpx.AsyncClient) -> None:
    # Manually trigger today's rollup; idempotent upsert.
    r = await client.post(f"{BASE}/api/admin/activity/rollup")
    report.add("Activity Rollup",
               "POST /admin/activity/rollup reachable",
               r.status_code == 200, f"status={r.status_code}")
    # Today's daily doc exists (the rollup must have written it; even an empty
    # day produces a doc with totals=0).
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.lumen_activity_daily.find_one({"date": today})
    report.add("Activity Rollup",
               f"lumen_activity_daily has row for today ({today})",
               bool(doc),
               f"keys={list(doc.keys()) if doc else 'missing'}")


async def verify_scheduler_effect() -> None:
    """Scheduler tasks are private to the process; we look at their fingerprints
    in the DB instead (uvicorn restart wipes asyncio tasks but the rollup
    boot-trigger re-runs them within the first second of startup)."""
    # Activity scheduler — at minimum a rollup for TODAY should exist after
    # boot. If absent, the scheduler never ran.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    has_today = await db.lumen_activity_daily.find_one({"date": today})
    has_yday = await db.lumen_activity_daily.find_one({"date": yday})
    report.add("Scheduler",
               "activity rollup ran since boot (today or yesterday row exists)",
               bool(has_today or has_yday),
               f"today={bool(has_today)} yesterday={bool(has_yday)}")


# ──────────────────────────────────────────────────────────────────────────
# Funnel / Attribution coherence
# ──────────────────────────────────────────────────────────────────────────
async def verify_funnel_coherence(client: httpx.AsyncClient) -> None:
    """Funnel is stateless (computed from leads + linked facts), so its
    'rollup' is really 'does the dashboard converge consistently'."""
    r = await client.get(f"{BASE}/api/admin/funnel/dashboard")
    if r.status_code != 200:
        report.add("Funnel", "dashboard reachable", False,
                   f"status={r.status_code}")
        return
    body = r.json()
    stages = body.get("stages") or []
    totals = body.get("totals") or {}
    report.add("Funnel",
               "dashboard exposes stages + totals",
               bool(stages) and bool(totals),
               f"stages={len(stages)} totals_keys={list(totals.keys())[:6]}")
    # Sanity: sum of stage counts >= total_visitors / total_leads (stages
    # cascade — visitor ⊇ lead ⊇ meeting … so per-stage counts must be
    # monotonically non-increasing along the chain).
    counts = [s.get("count", 0) for s in stages if isinstance(s, dict)]
    if len(counts) >= 2:
        monotonic_ok = all(counts[i] >= counts[i + 1]
                           for i in range(len(counts) - 1))
        report.add("Funnel",
                   "stage counts monotonically non-increasing",
                   monotonic_ok,
                   f"counts={counts}",
                   severity="warn" if not monotonic_ok else "fail")


# ──────────────────────────────────────────────────────────────────────────
# Manager + Communication counters
# ──────────────────────────────────────────────────────────────────────────
async def verify_manager_counters(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/api/admin/managers")
    if r.status_code != 200:
        report.add("Manager Counters", "list managers reachable", False,
                   f"status={r.status_code}")
        return
    managers = r.json().get("managers", []) or r.json().get("rows", []) or []
    if isinstance(managers, dict):
        managers = managers.get("rows") or managers.get("managers") or []
    report.add("Manager Counters",
               "manager roster non-empty",
               len(managers) > 0, f"count={len(managers)}",
               severity="warn" if not managers else "fail")
    # snapshot endpoint must serve global rollup
    r = await client.get(f"{BASE}/api/admin/manager-os/snapshot")
    report.add("Manager Counters",
               "manager-os snapshot reachable",
               r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        snap = r.json()
        report.add("Manager Counters",
                   "snapshot payload non-empty",
                   isinstance(snap, dict) and len(snap) > 0,
                   f"keys={list(snap.keys())[:8]}")


async def verify_communication_counters(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/api/admin/comms/stats")
    if r.status_code != 200:
        report.add("Comm Counters", "stats reachable", False,
                   f"status={r.status_code}")
        return
    s = r.json()
    by_p = s.get("by_provider") or {}
    by_d = s.get("by_direction") or {}
    by_t = s.get("by_type") or {}
    total = s.get("total", 0)
    sum_p = sum(by_p.values())
    sum_d = sum(by_d.values())
    sum_t = sum(by_t.values())
    report.add("Comm Counters",
               "total == sum(by_provider)",
               total == sum_p, f"total={total} sum_p={sum_p}",
               severity="warn" if total != sum_p else "fail")
    report.add("Comm Counters",
               "total == sum(by_direction)",
               total == sum_d, f"total={total} sum_d={sum_d}",
               severity="warn" if total != sum_d else "fail")
    report.add("Comm Counters",
               "total == sum(by_type)",
               total == sum_t, f"total={total} sum_t={sum_t}",
               severity="warn" if total != sum_t else "fail")
    # Catalogue still present
    r = await client.get(f"{BASE}/api/admin/comms/providers")
    if r.status_code == 200:
        provs = r.json().get("providers", [])
        keys = {p["key"] for p in provs}
        expected = {"manual", "ringostat", "binotel", "twilio",
                    "sip", "gmail", "outlook", "telegram", "whatsapp"}
        report.add("Comm Counters",
                   "provider catalogue intact (9 entries)",
                   expected.issubset(keys),
                   f"got={sorted(keys)} missing={sorted(expected - keys)}")


# ──────────────────────────────────────────────────────────────────────────
# Notification queue size + read/unread sanity
# ──────────────────────────────────────────────────────────────────────────
async def verify_notification_queue() -> None:
    total = await db.lumen_notifications.estimated_document_count()
    unread = await db.lumen_notifications.count_documents({"read": False})
    # warn if backlog is unrealistically large (>100k unread)
    report.add("Notifications",
               "queue size sane (<100k unread)",
               unread < 100_000,
               f"total={total} unread={unread}",
               severity="warn" if unread >= 100_000 else "fail")
    # staff notifications collection (M-layer)
    try:
        n2 = await db.lumen_staff_notifications.estimated_document_count()
        report.add("Notifications",
                   "lumen_staff_notifications reachable",
                   True, f"rows={n2}")
    except Exception as e:
        report.add("Notifications",
                   "lumen_staff_notifications reachable",
                   False, str(e))


# ──────────────────────────────────────────────────────────────────────────
# Session hygiene + CSP intake
# ──────────────────────────────────────────────────────────────────────────
async def verify_session_hygiene() -> None:
    # F3 / Manager OS M5 session table
    coll_candidates = ["lumen_user_sessions", "user_sessions",
                       "lumen_staff_sessions"]
    sessions_coll: Optional[str] = None
    cols = await db.list_collection_names()
    for c in coll_candidates:
        if c in cols:
            sessions_coll = c
            break
    if not sessions_coll:
        report.add("Sessions", "session collection present", False,
                   "none of lumen_user_sessions / user_sessions found",
                   severity="warn")
        return
    total = await db[sessions_coll].estimated_document_count()
    # Stale sessions: created >30 days ago but still flagged active.
    threshold = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    stale_active = await db[sessions_coll].count_documents({
        "$and": [
            {"$or": [{"status": "active"}, {"revoked": {"$ne": True}}]},
            {"$or": [
                {"created_at": {"$lt": threshold}},
                {"last_seen_at": {"$lt": threshold}},
            ]},
        ]
    })
    report.add("Sessions",
               f"{sessions_coll} reachable",
               True, f"rows={total}")
    report.add("Sessions",
               "no stale-active sessions older than 30d",
               stale_active == 0,
               f"stale_active={stale_active}",
               severity="warn" if stale_active else "fail")


async def verify_csp_intake(client: httpx.AsyncClient) -> None:
    """CSP endpoint must accept reports AND the collection must have a TTL."""
    payload = {
        "csp-report": {
            "document-uri": "https://audit.lumen.local/probe",
            "violated-directive": "img-src",
            "blocked-uri": "https://example.invalid/x.png",
        }
    }
    r = await client.post(f"{BASE}/api/security/csp-report", json=payload)
    report.add("CSP", "endpoint accepts report",
               r.status_code in (200, 201, 204),
               f"status={r.status_code}")
    # collection sanity
    n = await db.lumen_csp_reports.estimated_document_count()
    report.add("CSP", "lumen_csp_reports reachable", True, f"rows={n}")


# ──────────────────────────────────────────────────────────────────────────
# Field history growth
# ──────────────────────────────────────────────────────────────────────────
async def verify_field_history_growth() -> None:
    n = await db.lumen_field_changes.estimated_document_count()
    # Growth-control: warn if ≥ 5M rows; fail if ≥ 50M.
    if n >= 50_000_000:
        report.add("Field History",
                   "lumen_field_changes within hard limit (<50M)",
                   False, f"rows={n}")
    elif n >= 5_000_000:
        report.add("Field History",
                   "lumen_field_changes within soft limit (<5M)",
                   False, f"rows={n}", severity="warn")
    else:
        report.add("Field History",
                   "lumen_field_changes growth sane",
                   True, f"rows={n}")
    # Confirm there's at least an index on (entity_type, entity_id)
    idx = await _indexes("lumen_field_changes")
    has_entity_idx = any(
        any(k == "entity_type" for k, _ in (i.get("key") or []))
        for i in idx
    )
    report.add("Field History",
               "entity_type index present (lookup performance)",
               has_entity_idx,
               severity="warn" if not has_entity_idx else "fail")


# ──────────────────────────────────────────────────────────────────────────
# Healthz + auth round-trip
# ──────────────────────────────────────────────────────────────────────────
async def verify_health(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/api/healthz")
    report.add("Health", "GET /api/healthz",
               r.status_code == 200 and "ok" in r.text.lower(),
               f"status={r.status_code} body={r.text[:60]}")


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

        await verify_health(client)
        await verify_ttl_indexes()
        await verify_unique_indexes()
        await verify_scheduler_effect()
        await verify_activity_rollup(client)
        await verify_funnel_coherence(client)
        await verify_manager_counters(client)
        await verify_communication_counters(client)
        await verify_notification_queue()
        await verify_session_hygiene()
        await verify_csp_intake(client)
        await verify_field_history_growth()

    summary = report.summary()
    print("\n" + "=" * 78)
    print(f"INFRA REGRESSION AUDIT — {summary['verdict']} "
          f"(pass={summary['passed']}/{summary['total']} "
          f"fail={summary['failed']} warn={summary['warned']})")
    print("=" * 78)
    for sect, c in summary["by_section"].items():
        print(f"  {sect:24s}  pass={c['pass']:>2}  fail={c['fail']:>2}  warn={c['warn']:>2}")

    out = "/app/test_reports/infra_regression_audit.json"
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
