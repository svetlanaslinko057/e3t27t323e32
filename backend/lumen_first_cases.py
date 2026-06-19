"""
LUMEN — First Real Cases Journal.

Operational supplement to the ``first_funding`` Beta-1 milestone.

This is NOT a new module — it is observability over what already exists.
Idempotent scanner over existing collections (no new write paths, no
hooks into other modules). It captures the FIRST non-seed instance of
each Investor → KYC → Contract → Funding → Certificate → Payout
milestone, persists the snapshot once detected, and computes
time-between-milestones so we can read REAL operational latency the
moment a real investor lands.

Locked by user (2026-06-15) as the only operational journal during the
VALIDATION window. Replaces the need to reverse-engineer
"where did the first real investor actually slow down?" weeks later.

Status: under-the-hood. Single admin read route. No UI.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Callable

from fastapi import APIRouter, Depends

from lumen_api import db, require_admin, _strip_mongo

logger = logging.getLogger("lumen.first_cases")

router = APIRouter(prefix="/api/admin", tags=["lumen-first-cases"])

COLLECTION = "lumen_first_cases"

# Seed-account detection — mirrors lumen_beta_command_center.SEED_EMAIL_DOMAINS
# plus everything currently used in LUMEN seed scripts.
SEED_EMAIL_DOMAINS = (
    "@atlas.dev", "@devos.io",
    "@lumen.dev", "@lumen.test", "@lumen.local",
    "@example.com", "@test.com", "@test.local",
)
SEED_NAME_FRAGMENTS = (
    "test", "demo", "seed", "synthetic", "lumen demo",
    "демо", "тест",  # cyrillic demo/test
    # Names of pre-seeded mock investor profiles — explicitly excluded.
    "acme client", "helios family office", "stratos partners",
    "platform admin", "atlas admin", "qa tester", "podil operator",
    "olena kovalenko", "олена коваленко",
    "ihor petrenko", "ігор петренко",
    "maria shevchenko", "марія шевченко",
    "john developer", "multi-role user",
)
# Seed user_id prefixes used by LUMEN demo seed scripts.
SEED_USER_ID_PREFIXES = (
    "user_mktdemo_", "user_liqdemo_", "user_seed_", "user_demo_", "user_test_",
)


# Cases tracked in this journal, in the operational order of the cycle.
CASE_ORDER = [
    "first_real_investor",      # non-seed user with role/roles ∈ {investor, client}
    "first_real_kyc",           # non-seed investor profile with kyc_status='approved'
    "first_real_contract",      # non-seed contract with status='signed' / signed_at present
    "first_real_funding",       # non-seed institutional transfer with canonical_status='confirmed'
    "first_real_certificate",   # non-seed certificate issued (status≠voided)
    "first_real_payout",        # non-seed payout with status ∈ {paid, credited}
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[Any]) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, datetime):
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    return str(dt)


def _parse_dt(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        s = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_seed_email(email: Optional[str]) -> bool:
    if not email:
        return True  # No real email = treat as seed/anonymous mock data
    e = email.lower()
    return any(e.endswith(d) for d in SEED_EMAIL_DOMAINS)


def _is_seed_name(name: Optional[str]) -> bool:
    if not name:
        return False
    n = name.lower()
    return any(frag in n for frag in SEED_NAME_FRAGMENTS)


async def _is_seed_user(user_id: Optional[str]) -> bool:
    """User is considered seed/mock if user_id matches a known seed prefix,
    email is in seed domains, missing, or full_name matches a known seed
    fragment, or the user record carries an explicit seed marker."""
    if not user_id:
        return True
    # Cheap path: user_id prefix says it all (used by demo seed scripts).
    if any(user_id.startswith(p) for p in SEED_USER_ID_PREFIXES):
        return True
    user = await db.users.find_one(
        {"$or": [{"user_id": user_id}, {"id": user_id}]},
        {"_id": 0, "email": 1, "name": 1, "full_name": 1, "tags": 1, "is_seed": 1},
    )
    if not user:
        return True
    if user.get("is_seed"):
        return True
    if _is_seed_email(user.get("email")):
        return True
    if _is_seed_name(user.get("name") or user.get("full_name")):
        return True
    tags = user.get("tags") or []
    if any(t in ("seed", "demo", "test", "synthetic") for t in tags):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# Detectors — each returns (entity_id, user_id, label, at, extra_dict) or None.
# Detectors walk earliest → latest and stop at the first non-seed candidate.
# ─────────────────────────────────────────────────────────────────────────
async def _detect_first_real_investor() -> Optional[dict]:
    async for u in db.users.find(
        {"$or": [{"role": {"$in": ["investor", "client"]}},
                 {"roles": {"$in": ["investor", "client"]}}]},
    ).sort("created_at", 1):
        u = _strip_mongo(u)
        uid = u.get("user_id") or u.get("id")
        if any(uid and uid.startswith(p) for p in SEED_USER_ID_PREFIXES):
            continue
        if _is_seed_email(u.get("email")):
            continue
        if _is_seed_name(u.get("name") or u.get("full_name")):
            continue
        if u.get("is_seed"):
            continue
        tags = u.get("tags") or []
        if any(t in ("seed", "demo", "test", "synthetic") for t in tags):
            continue
        return {
            "entity_id": uid,
            "user_id": uid,
            "label": u.get("name") or u.get("full_name") or u.get("email") or uid,
            "at": _iso(u.get("created_at")),
            "extra": {"email": u.get("email")},
        }
    return None


async def _detect_first_real_kyc() -> Optional[dict]:
    async for p in db.lumen_investor_profiles.find(
        {"kyc_status": "approved"},
    ).sort([("kyc_reviewed_at", 1), ("updated_at", 1), ("created_at", 1)]):
        p = _strip_mongo(p)
        if await _is_seed_user(p.get("user_id")):
            continue
        return {
            "entity_id": p.get("id"),
            "user_id": p.get("user_id"),
            "label": p.get("full_name") or p.get("user_id"),
            "at": _iso(p.get("kyc_reviewed_at") or p.get("updated_at") or p.get("created_at")),
            "extra": {"accreditation": p.get("accreditation_status"),
                      "country": p.get("country")},
        }
    return None


async def _detect_first_real_contract() -> Optional[dict]:
    async for c in db.contracts.find(
        {"$or": [{"status": "signed"}, {"signed_at": {"$ne": None}}]},
    ).sort([("signed_at", 1), ("created_at", 1)]):
        c = _strip_mongo(c)
        if await _is_seed_user(c.get("investor_id")):
            continue
        return {
            "entity_id": c.get("id"),
            "user_id": c.get("investor_id"),
            "label": c.get("number") or c.get("title") or c.get("id"),
            "at": _iso(c.get("signed_at") or c.get("created_at")),
            "extra": {"asset_id": c.get("asset_id"),
                      "template_kind": c.get("template_kind")},
        }
    return None


async def _detect_first_real_funding() -> Optional[dict]:
    # canonical funding flow — matches Beta Command Center's _detect_first_funding
    coll = "lumen_institutional_transfers"
    async for t in db[coll].find(
        {"$or": [{"canonical_status": "confirmed"}, {"status": "confirmed"}]},
    ).sort([("settled_at", 1), ("created_at", 1)]):
        t = _strip_mongo(t)
        if await _is_seed_user(t.get("investor_id") or t.get("user_id")):
            continue
        return {
            "entity_id": t.get("id"),
            "user_id": t.get("investor_id") or t.get("user_id"),
            "label": t.get("reference") or t.get("id"),
            "at": _iso(t.get("settled_at") or t.get("updated_at") or t.get("created_at")),
            "extra": {"amount": t.get("amount"),
                      "currency": t.get("currency"),
                      "reference": t.get("reference")},
        }
    return None


async def _detect_first_real_certificate() -> Optional[dict]:
    async for cert in db.lumen_certificates.find(
        {"status": {"$nin": ["voided"]}},
    ).sort([("issue_date", 1), ("created_at", 1)]):
        cert = _strip_mongo(cert)
        if await _is_seed_user(cert.get("investor_id")):
            continue
        if _is_seed_name(cert.get("investor_name")):
            continue
        return {
            "entity_id": cert.get("id"),
            "user_id": cert.get("investor_id"),
            "label": cert.get("certificate_number") or cert.get("id"),
            "at": _iso(cert.get("issue_date") or cert.get("created_at")),
            "extra": {"asset_id": cert.get("asset_id"),
                      "units": cert.get("units"),
                      "value_uah": cert.get("value_uah")},
        }
    return None


async def _detect_first_real_payout() -> Optional[dict]:
    # Prefer the v2 records collection (richer schema), then fall back.
    for coll in ("lumen_payout_records", "lumen_payouts", "payouts"):
        try:
            async for p in db[coll].find(
                {"status": {"$in": ["paid", "credited"]}},
            ).sort([("paid_date", 1), ("paid_at", 1), ("created_at", 1)]):
                p = _strip_mongo(p)
                uid = p.get("investor_id") or p.get("user_id")
                if await _is_seed_user(uid):
                    continue
                return {
                    "entity_id": p.get("id"),
                    "user_id": uid,
                    "label": p.get("batch_id") or p.get("id"),
                    "at": _iso(p.get("paid_date") or p.get("paid_at") or p.get("created_at")),
                    "extra": {"amount": p.get("amount"),
                              "currency": p.get("currency"),
                              "source_collection": coll},
                }
        except Exception:
            continue
    return None


_DETECTORS: dict[str, Callable] = {
    "first_real_investor":    _detect_first_real_investor,
    "first_real_kyc":         _detect_first_real_kyc,
    "first_real_contract":    _detect_first_real_contract,
    "first_real_funding":     _detect_first_real_funding,
    "first_real_certificate": _detect_first_real_certificate,
    "first_real_payout":      _detect_first_real_payout,
}


# ─────────────────────────────────────────────────────────────────────────
# Scanner — idempotent
# ─────────────────────────────────────────────────────────────────────────
async def scan_first_cases() -> dict:
    """Idempotently snapshot the first non-seed instance of each milestone.

    Each row is written only ONCE (when the case_key fires for the first time);
    later scans never overwrite it — the "first" by definition cannot change.
    Empty cases re-evaluate each scan (no row written when still empty).
    """
    out = {"scanned_at": _iso(_now()), "cases": {}}
    for case_key in CASE_ORDER:
        existing = await db[COLLECTION].find_one({"case_key": case_key})
        if existing:
            existing = _strip_mongo(existing)
            out["cases"][case_key] = {**existing, "state": "captured"}
            continue
        try:
            res = await _DETECTORS[case_key]()
        except Exception as e:
            logger.warning("first_cases scan failed for %s: %s", case_key, e)
            res = None
        if not res:
            out["cases"][case_key] = {"case_key": case_key, "state": "pending"}
            continue
        doc = {
            "case_key": case_key,
            "entity_id": res.get("entity_id"),
            "user_id": res.get("user_id"),
            "label": res.get("label"),
            "at": res.get("at"),
            "extra": res.get("extra") or {},
            "captured_at": _iso(_now()),
            "state": "captured",
        }
        try:
            await db[COLLECTION].insert_one(doc)
        except Exception:
            # race: another scan got there first → re-read
            pass
        doc = _strip_mongo(await db[COLLECTION].find_one({"case_key": case_key}) or doc)
        out["cases"][case_key] = doc

    out["cycle"] = _compute_cycle(out["cases"])
    return out


def _seconds_between(a_iso: Optional[str], b_iso: Optional[str]) -> Optional[float]:
    a, b = _parse_dt(a_iso), _parse_dt(b_iso)
    if not a or not b:
        return None
    return (b - a).total_seconds()


def _humanize(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    if seconds < 0:
        seconds = -seconds
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _compute_cycle(cases: dict) -> dict:
    """Compute time-between-milestones — the real operational answer to
    'where do real investors slow down?'. Returns None for any leg whose
    endpoint has not fired yet."""
    legs = [
        ("investor_to_kyc",        "first_real_investor",    "first_real_kyc"),
        ("kyc_to_contract",        "first_real_kyc",         "first_real_contract"),
        ("contract_to_funding",    "first_real_contract",    "first_real_funding"),
        ("funding_to_certificate", "first_real_funding",     "first_real_certificate"),
        ("certificate_to_payout",  "first_real_certificate", "first_real_payout"),
        ("total_cycle",            "first_real_investor",    "first_real_payout"),
    ]
    out = {}
    for leg, frm, to in legs:
        a = (cases.get(frm) or {}).get("at")
        b = (cases.get(to) or {}).get("at")
        secs = _seconds_between(a, b)
        out[leg] = {"seconds": secs, "human": _humanize(secs)}

    captured = sum(1 for k in CASE_ORDER if (cases.get(k) or {}).get("state") == "captured")
    out["captured"] = captured
    out["total"] = len(CASE_ORDER)
    out["pending"] = [k for k in CASE_ORDER if (cases.get(k) or {}).get("state") == "pending"]
    out["complete"] = captured == len(CASE_ORDER)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Routes (admin read-only)
# ─────────────────────────────────────────────────────────────────────────
@router.get("/first-cases")
async def get_first_cases(admin=Depends(require_admin)):
    """Operational journal of the first real (non-seed) lifecycle.

    Returns each case with state ∈ {captured, pending}, the captured snapshot,
    and computed time-between-milestones once consecutive cases are captured.
    """
    return await scan_first_cases()


@router.post("/first-cases/rescan")
async def rescan_first_cases(admin=Depends(require_admin)):
    """Force a rescan. Captured cases are never overwritten (first is final).
    This route is for surfacing newly fired cases between scheduled scans.
    """
    return await scan_first_cases()


# ─────────────────────────────────────────────────────────────────────────
# Index bootstrap + background loop
# ─────────────────────────────────────────────────────────────────────────
async def ensure_indexes(database=None) -> None:
    d = database if database is not None else db
    try:
        await d[COLLECTION].create_index("case_key", unique=True)
        await d[COLLECTION].create_index("captured_at")
    except Exception as e:
        logger.warning("first_cases ensure_indexes warn: %s", e)


SCAN_INTERVAL_SECONDS = 300  # 5 minutes


async def _background_loop():
    while True:
        try:
            await scan_first_cases()
        except Exception as e:
            logger.warning("first_cases background scan failed: %s", e)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


_background_task: Optional[asyncio.Task] = None


def start_background_scan() -> None:
    """Spawn the 5-min recompute loop. Idempotent."""
    global _background_task
    if _background_task and not _background_task.done():
        return
    try:
        _background_task = asyncio.create_task(_background_loop())
        logger.info("first_cases background scan started (every %ds)", SCAN_INTERVAL_SECONDS)
    except Exception as e:
        logger.warning("first_cases background scan failed to start: %s", e)
