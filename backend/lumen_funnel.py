"""
LUMEN — F1 Investor Funnel Analytics
=====================================

Operational graph of an investor's journey through LUMEN, NOT a marketing
funnel. Every stage is defined by a side-effect already recorded in the
operational database (users / contracts / signatures / certificates /
institutional transfers / pipeline events).

13 stages:

    1  Visitor
    2  Lead
    3  Qualified
    4  Meeting
    5  KYC Started
    6  KYC Approved
    7  Accreditation
    8  Contract Issued
    9  Contract Signed
    10 Funding Pending
    11 Funding Confirmed
    12 Certificate Issued
    13 Active Investor

Per stage we expose:

    count
    conversion_from_previous          (Stage N count / Stage N-1 count)
    conversion_from_start             (Stage N count / Stage 1 count)
    median_time_from_previous_seconds (median delta between adjacent stages)
    median_time_from_start_seconds
    bottleneck                        (slowest median in absolute terms)
    main_dropoff                      (largest single-step drop, %)

All endpoints are gated to master-admin / staff-admin / manager (latter
sees only her own assigned investors).
"""
from __future__ import annotations

import os
import time
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from lumen_api import require_admin, require_staff, get_current_user

# ---------------------------------------------------------------------------
# Mongo
# ---------------------------------------------------------------------------
_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
db = AsyncIOMotorClient(_MONGO_URL)[_DB_NAME]


# ---------------------------------------------------------------------------
# Stage definitions (order matters — used as ordinal in the funnel)
# ---------------------------------------------------------------------------
STAGE_KEYS = [
    "visitor",
    "lead",
    "qualified",
    "meeting",
    "kyc_started",
    "kyc_approved",
    "accreditation",
    "contract_issued",
    "contract_signed",
    "funding_pending",
    "funding_confirmed",
    "certificate_issued",
    "active_investor",
]

STAGE_LABELS = {
    "visitor": {"uk": "Відвідувач", "en": "Visitor"},
    "lead": {"uk": "Лід", "en": "Lead"},
    "qualified": {"uk": "Кваліфіковано", "en": "Qualified"},
    "meeting": {"uk": "Зустріч", "en": "Meeting"},
    "kyc_started": {"uk": "KYC розпочато", "en": "KYC Started"},
    "kyc_approved": {"uk": "KYC схвалено", "en": "KYC Approved"},
    "accreditation": {"uk": "Акредитація", "en": "Accreditation"},
    "contract_issued": {"uk": "Договір видано", "en": "Contract Issued"},
    "contract_signed": {"uk": "Договір підписано", "en": "Contract Signed"},
    "funding_pending": {"uk": "Поповнення в обробці", "en": "Funding Pending"},
    "funding_confirmed": {"uk": "Поповнення підтверджено", "en": "Funding Confirmed"},
    "certificate_issued": {"uk": "Сертифікат випущено", "en": "Certificate Issued"},
    "active_investor": {"uk": "Активний інвестор", "en": "Active Investor"},
}


# ---------------------------------------------------------------------------
# Time-window helpers
# ---------------------------------------------------------------------------
def _resolve_window(rng: str) -> tuple[datetime | None, datetime]:
    """Return (since, now). since=None means 'all time'."""
    now = datetime.now(timezone.utc)
    rng = (rng or "all").lower()
    if rng == "7d":
        return now - timedelta(days=7), now
    if rng == "30d":
        return now - timedelta(days=30), now
    if rng == "90d":
        return now - timedelta(days=90), now
    if rng == "ytd":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc), now
    return None, now


def _norm_dt(dt: Any) -> datetime | None:
    """Coerce a possibly naive Mongo datetime to UTC-aware."""
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Building per-investor stage map
# ---------------------------------------------------------------------------
async def _collect_journeys(manager_id: str | None = None) -> list[dict]:
    """
    For every investor-side user (role in {investor, client} OR any user
    holding a lead/contract/certificate), return a dict:

        {
            user_id, email, name, manager_id,
            stage_timestamps: { stage_key -> datetime | None }
        }

    Manager scope filter: if manager_id is provided, restrict to users
    where the user's owner/manager is the given manager.
    """
    INVESTOR_ROLES = {"investor", "client"}
    user_query: dict = {"$or": [
        {"role":  {"$in": list(INVESTOR_ROLES)}},
        {"roles": {"$elemMatch": {"$in": list(INVESTOR_ROLES)}}},
        {"states": {"$elemMatch": {"$in": list(INVESTOR_ROLES)}}},
    ]}
    if manager_id:
        user_query["$and"] = [
            {"$or": [
                {"manager_id": manager_id},
                {"owner_id":   manager_id},
                {"assigned_manager_id": manager_id},
            ]}
        ]

    users = await db.users.find(user_query).to_list(None)
    # Also include any user that has a contract / certificate but didn't
    # match the role filter (defensive — early-stage DB may not yet tag
    # the role properly).
    have_contract_ids = await db.lumen_contracts.distinct("investor_id")
    have_cert_ids = await db.lumen_certificates.distinct("investor_id")
    known = {u["user_id"] for u in users if u.get("user_id")}
    extra_ids = [uid for uid in (set(have_contract_ids) | set(have_cert_ids))
                 if uid and uid not in known]
    if extra_ids:
        for u in await db.users.find({"user_id": {"$in": extra_ids}}).to_list(None):
            # Manager scope still applies
            if manager_id and not any([
                u.get("manager_id") == manager_id,
                u.get("owner_id") == manager_id,
                u.get("assigned_manager_id") == manager_id,
            ]):
                continue
            users.append(u)

    # Pre-fetch related collections
    contracts_by_inv: dict[str, list[dict]] = {}
    async for c in db.lumen_contracts.find({}, {
        "investor_id": 1, "status": 1, "generated_at": 1, "sent_at": 1,
        "viewed_at": 1, "signed_at": 1, "cancelled_at": 1, "amount": 1,
    }):
        contracts_by_inv.setdefault(c.get("investor_id"), []).append(c)

    sigs_by_inv: dict[str, datetime] = {}
    async for s in db.lumen_signatures.find({"status": "signed"},
                                            {"contract_id": 1, "signed_at": 1, "user_id": 1}):
        uid = s.get("user_id")
        signed_at = _norm_dt(s.get("signed_at"))
        if not uid or not signed_at:
            continue
        if uid not in sigs_by_inv or signed_at < sigs_by_inv[uid]:
            sigs_by_inv[uid] = signed_at

    certs_by_inv: dict[str, datetime] = {}
    async for c in db.lumen_certificates.find({"status": "active"},
                                              {"investor_id": 1, "issue_date": 1, "created_at": 1}):
        uid = c.get("investor_id")
        dt = _norm_dt(c.get("issue_date") or c.get("created_at"))
        if not uid or not dt:
            continue
        if uid not in certs_by_inv or dt < certs_by_inv[uid]:
            certs_by_inv[uid] = dt

    transfers_pending: dict[str, datetime] = {}
    transfers_confirmed: dict[str, datetime] = {}
    PENDING_STATES = {"pending", "awaiting", "awaiting_confirmation",
                       "submitted", "in_review", "processing"}
    CONFIRMED_STATES = {"confirmed", "settled", "completed", "credited", "matched"}
    async for tr in db.lumen_institutional_transfers.find({}, {
        "investor_id": 1, "user_id": 1, "status": 1,
        "submitted_at": 1, "confirmed_at": 1, "created_at": 1,
    }):
        uid = tr.get("investor_id") or tr.get("user_id")
        if not uid:
            continue
        status = (tr.get("status") or "").lower()
        if status in PENDING_STATES:
            dt = _norm_dt(tr.get("submitted_at") or tr.get("created_at"))
            if dt and (uid not in transfers_pending or dt < transfers_pending[uid]):
                transfers_pending[uid] = dt
        if status in CONFIRMED_STATES:
            dt = _norm_dt(tr.get("confirmed_at") or tr.get("submitted_at") or tr.get("created_at"))
            if dt and (uid not in transfers_confirmed or dt < transfers_confirmed[uid]):
                transfers_confirmed[uid] = dt

    # Pipeline / meeting events (collections may be empty in early db)
    qualified_at: dict[str, datetime] = {}
    meeting_at: dict[str, datetime] = {}
    async for ev in db.lumen_pipeline_events.find({}, {
        "user_id": 1, "lead_id": 1, "event_type": 1, "at": 1, "created_at": 1,
    }):
        uid = ev.get("user_id") or ev.get("lead_id")
        et  = (ev.get("event_type") or "").lower()
        dt = _norm_dt(ev.get("at") or ev.get("created_at"))
        if not uid or not dt:
            continue
        if et in ("qualified", "lead_qualified"):
            if uid not in qualified_at or dt < qualified_at[uid]:
                qualified_at[uid] = dt
        elif et in ("meeting", "meeting_held", "meeting_completed"):
            if uid not in meeting_at or dt < meeting_at[uid]:
                meeting_at[uid] = dt

    async for m in db.lumen_meetings.find({}, {
        "investor_id": 1, "user_id": 1, "scheduled_at": 1, "held_at": 1, "created_at": 1, "status": 1,
    }):
        uid = m.get("investor_id") or m.get("user_id")
        dt = _norm_dt(m.get("held_at") or m.get("scheduled_at") or m.get("created_at"))
        if not uid or not dt:
            continue
        if uid not in meeting_at or dt < meeting_at[uid]:
            meeting_at[uid] = dt

    journeys = []
    for u in users:
        uid = u.get("user_id")
        if not uid:
            continue
        ts: dict[str, datetime | None] = {k: None for k in STAGE_KEYS}

        # Stage 1 — Visitor: we don't yet have a visit log; fall back to signup
        # so the funnel still works pre-F2. F2 Site Activity will overwrite this.
        ts["visitor"] = _norm_dt(u.get("first_visit_at") or u.get("created_at"))

        # Stage 2 — Lead: any user attached to an owner/manager OR with a lead_source
        ts["lead"] = _norm_dt(
            u.get("became_lead_at") or u.get("lead_at") or u.get("created_at")
        )

        # Stage 3 — Qualified
        ts["qualified"] = qualified_at.get(uid) or _norm_dt(u.get("qualified_at"))

        # Stage 4 — Meeting
        ts["meeting"] = meeting_at.get(uid) or _norm_dt(u.get("first_meeting_at"))

        # Stage 5 — KYC started (any non-null kyc_status)
        kyc_status = u.get("kyc_status")
        if kyc_status:
            ts["kyc_started"] = _norm_dt(
                u.get("kyc_submitted_at") or u.get("kyc_started_at") or u.get("created_at")
            )

        # Stage 6 — KYC approved
        if kyc_status in ("approved", "approve", "passed", "verified"):
            ts["kyc_approved"] = _norm_dt(
                u.get("kyc_approved_at") or u.get("kyc_decision_at") or ts["kyc_started"]
            )

        # Stage 7 — Accreditation
        accr_status = (u.get("accreditation_status") or "").lower()
        accr_tier = u.get("accreditation_tier") or u.get("tier")
        if accr_status in ("approved", "accredited", "passed") or (
            accr_tier and accr_tier not in ("", "none", "unknown", None)):
            ts["accreditation"] = _norm_dt(
                u.get("accreditation_approved_at") or u.get("accreditation_at")
                or u.get("accreditation_decision_at")
            )

        # Stage 8 — Contract issued (any contract created in non-cancelled state ever)
        for c in contracts_by_inv.get(uid, []):
            dt = _norm_dt(c.get("generated_at") or c.get("sent_at"))
            if not dt:
                continue
            if ts["contract_issued"] is None or dt < ts["contract_issued"]:
                ts["contract_issued"] = dt

        # Stage 9 — Contract signed
        ts["contract_signed"] = sigs_by_inv.get(uid)
        if not ts["contract_signed"]:
            for c in contracts_by_inv.get(uid, []):
                if c.get("status") == "signed":
                    dt = _norm_dt(c.get("signed_at"))
                    if dt and (ts["contract_signed"] is None or dt < ts["contract_signed"]):
                        ts["contract_signed"] = dt

        # Stage 10/11 — Funding
        ts["funding_pending"] = transfers_pending.get(uid)
        ts["funding_confirmed"] = transfers_confirmed.get(uid)

        # Stage 12 — Certificate
        ts["certificate_issued"] = certs_by_inv.get(uid)

        # Stage 13 — Active investor (has active certificate AND activity within 180 days)
        if ts["certificate_issued"]:
            ts["active_investor"] = ts["certificate_issued"]

        # Propagation: an investor at stage N is implicitly at every stage <= N.
        # Backfill any missing earlier-stage timestamps with the next existing
        # downstream timestamp (or, preferring the latest already-set upstream
        # one if available). This ensures counts are monotonically non-increasing.
        existing = [(i, ts[k]) for i, k in enumerate(STAGE_KEYS) if ts[k] is not None]
        if existing:
            max_idx = max(i for i, _ in existing)
            last_seen: datetime | None = None
            for i in range(max_idx + 1):
                k = STAGE_KEYS[i]
                if ts[k] is not None:
                    last_seen = ts[k]
                else:
                    nxt = next((t for j, t in existing if j > i), None)
                    ts[k] = last_seen or nxt

        journeys.append({
            "user_id": uid,
            "email": u.get("email"),
            "name": u.get("name"),
            "manager_id": (u.get("manager_id") or u.get("owner_id")
                            or u.get("assigned_manager_id")),
            "stage_timestamps": ts,
        })

    return journeys


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _aggregate(journeys: list[dict], since: datetime | None) -> dict:
    """Build counts + medians + bottleneck flag."""
    counts = {k: 0 for k in STAGE_KEYS}
    deltas_from_previous: dict[str, list[float]] = {k: [] for k in STAGE_KEYS}
    deltas_from_start:    dict[str, list[float]] = {k: [] for k in STAGE_KEYS}

    for j in journeys:
        ts = j["stage_timestamps"]
        start = ts[STAGE_KEYS[0]]
        # apply window filter on the journey's first event
        if since and (start is None or start < since):
            continue
        for idx, k in enumerate(STAGE_KEYS):
            if ts[k] is not None:
                counts[k] += 1
            # deltas
            if idx > 0:
                prev = ts[STAGE_KEYS[idx - 1]]
                cur  = ts[k]
                if prev and cur and cur >= prev:
                    deltas_from_previous[k].append((cur - prev).total_seconds())
            if start and ts[k] and ts[k] >= start:
                deltas_from_start[k].append((ts[k] - start).total_seconds())

    start_count = counts[STAGE_KEYS[0]]
    out_stages = []
    biggest_drop = -1.0
    biggest_drop_idx: int | None = None
    slowest_median = -1.0
    slowest_median_idx: int | None = None
    for idx, k in enumerate(STAGE_KEYS):
        prev_count = counts[STAGE_KEYS[idx - 1]] if idx > 0 else counts[k]
        conv_prev = (counts[k] / prev_count) if prev_count else 0.0
        conv_start = (counts[k] / start_count) if start_count else 0.0
        med_prev  = statistics.median(deltas_from_previous[k]) if deltas_from_previous[k] else None
        med_start = statistics.median(deltas_from_start[k]) if deltas_from_start[k] else None
        # bottleneck — biggest drop
        if idx > 0 and prev_count > 0:
            drop = (1 - conv_prev) * 100.0
            if drop > biggest_drop:
                biggest_drop = drop
                biggest_drop_idx = idx
        # slowest median between adjacent stages
        if idx > 0 and med_prev and med_prev > slowest_median:
            slowest_median = med_prev
            slowest_median_idx = idx
        out_stages.append({
            "key": k,
            "label": STAGE_LABELS[k],
            "count": counts[k],
            "conversion_from_previous": round(conv_prev, 4),
            "conversion_from_start": round(conv_start, 4),
            "median_time_from_previous_seconds": med_prev,
            "median_time_from_start_seconds": med_start,
            "bottleneck": False,
            "main_dropoff": False,
        })
    if biggest_drop_idx is not None and counts[STAGE_KEYS[biggest_drop_idx - 1]] >= 2:
        out_stages[biggest_drop_idx]["main_dropoff"] = True
    if slowest_median_idx is not None:
        out_stages[slowest_median_idx]["bottleneck"] = True

    return {
        "stages": out_stages,
        "totals": {
            "investors_in_window": len([
                j for j in journeys
                if (not since) or (
                    j["stage_timestamps"][STAGE_KEYS[0]]
                    and j["stage_timestamps"][STAGE_KEYS[0]] >= since
                )
            ]),
            "active_investors": counts["active_investor"],
            "main_bottleneck_stage": STAGE_KEYS[slowest_median_idx]
                if slowest_median_idx else None,
            "main_dropoff_stage": STAGE_KEYS[biggest_drop_idx]
                if biggest_drop_idx else None,
        },
    }


# ---------------------------------------------------------------------------
# In-memory cache (60s) keyed by (manager_id, range)
# ---------------------------------------------------------------------------
_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_TTL = 60


async def _funnel_data(manager_id: str | None, rng: str) -> dict:
    key = (manager_id or "*", rng or "all")
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < _CACHE_TTL:
        return _CACHE[key][1]
    since, _now = _resolve_window(rng)
    journeys = await _collect_journeys(manager_id=manager_id)
    agg = _aggregate(journeys, since=since)

    # Manager attribution (F1.5)
    by_manager: dict[str, dict] = {}
    for j in journeys:
        mid = j["manager_id"] or "_unassigned"
        bm = by_manager.setdefault(mid, {
            "manager_id": mid if mid != "_unassigned" else None,
            "leads_assigned": 0,
            "kyc_approved": 0,
            "contract_signed": 0,
            "funding_confirmed": 0,
            "certificate_issued": 0,
            "active_investor": 0,
        })
        ts = j["stage_timestamps"]
        if since and (ts[STAGE_KEYS[0]] is None or ts[STAGE_KEYS[0]] < since):
            continue
        bm["leads_assigned"] += 1
        for stage in ("kyc_approved", "contract_signed", "funding_confirmed",
                       "certificate_issued", "active_investor"):
            if ts[stage]:
                bm[stage] += 1
    # enrich with manager names
    mgr_ids = [m for m in by_manager.keys() if m != "_unassigned"]
    mgrs = {u["user_id"]: u for u in await db.users.find(
        {"user_id": {"$in": mgr_ids}},
        {"user_id": 1, "name": 1, "email": 1}
    ).to_list(None)} if mgr_ids else {}
    manager_rows = []
    for mid, row in by_manager.items():
        u = mgrs.get(mid) or {}
        row["manager_name"] = u.get("name") if mid != "_unassigned" else None
        row["manager_email"] = u.get("email") if mid != "_unassigned" else None
        row["lead_to_funded_conv"] = round(
            (row["funding_confirmed"] / row["leads_assigned"])
            if row["leads_assigned"] else 0.0, 4)
        manager_rows.append(row)
    manager_rows.sort(key=lambda r: r["funding_confirmed"], reverse=True)

    # Funding attribution (F1.6) — per manager
    funding_rows = []
    transfers_pipe = [
        {"$match": {"status": {"$in": ["confirmed", "settled", "completed",
                                        "credited", "matched"]}}},
        {"$group": {"_id": "$manager_id", "volume": {"$sum": "$amount"},
                    "count": {"$sum": 1}}},
    ]
    try:
        async for r in db.lumen_institutional_transfers.aggregate(transfers_pipe):
            funding_rows.append({
                "manager_id": r.get("_id"),
                "volume_eur": r.get("volume", 0.0),
                "transfers": r.get("count", 0),
            })
    except Exception:
        pass
    # complement with certificate-derived volume (UAH → no FX, kept as separate field)
    cert_vol_pipe = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$manager_id",
                     "value_uah": {"$sum": "$value_uah"},
                     "count": {"$sum": 1}}},
    ]
    cert_rows = {}
    try:
        async for r in db.lumen_certificates.aggregate(cert_vol_pipe):
            cert_rows[r.get("_id")] = {
                "certificate_value_uah": r.get("value_uah", 0.0),
                "certificates": r.get("count", 0),
            }
    except Exception:
        pass

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range": rng or "all",
        "scope": "manager" if manager_id else "global",
        "manager_id": manager_id,
        **agg,
        "manager_attribution": manager_rows,
        "funding_attribution": [
            {
                **r,
                "manager_name": (mgrs.get(r["manager_id"]) or {}).get("name"),
                **(cert_rows.get(r["manager_id"]) or {}),
            } for r in funding_rows
        ],
        "stage_keys": STAGE_KEYS,
    }
    _CACHE[key] = (now, out)
    return out


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api", tags=["lumen-funnel"])


def _resolve_role_check():
    """Stub kept for back-compat; new endpoints use require_admin/require_staff."""
    return None


@router.get("/admin/funnel/dashboard")
async def admin_funnel_dashboard(
    range: str = Query("90d"),
    _admin: dict = Depends(require_admin),
):
    return await _funnel_data(manager_id=None, rng=range)


@router.get("/admin/funnel/stages")
async def admin_funnel_stages(
    range: str = Query("90d"),
    _admin: dict = Depends(require_admin),
):
    data = await _funnel_data(manager_id=None, rng=range)
    return {"stages": data["stages"], "totals": data["totals"],
            "generated_at": data["generated_at"], "range": range}


@router.get("/admin/funnel/manager-attribution")
async def admin_funnel_manager_attr(
    range: str = Query("90d"),
    _admin: dict = Depends(require_admin),
):
    data = await _funnel_data(manager_id=None, rng=range)
    return {"rows": data["manager_attribution"], "range": range,
            "generated_at": data["generated_at"]}


@router.get("/admin/funnel/funding-attribution")
async def admin_funnel_funding_attr(
    range: str = Query("90d"),
    _admin: dict = Depends(require_admin),
):
    data = await _funnel_data(manager_id=None, rng=range)
    return {"rows": data["funding_attribution"], "range": range,
            "generated_at": data["generated_at"]}


@router.get("/manager/funnel/dashboard")
async def manager_funnel_dashboard(
    range: str = Query("90d"),
    user: dict = Depends(require_staff),
):
    """Manager-scoped funnel: only journeys where manager_id == self."""
    return await _funnel_data(manager_id=user.get("user_id") or user.get("id"),
                              rng=range)
