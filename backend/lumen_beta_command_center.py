"""
LUMEN 2.0 — Phase H1.3 — Controlled Beta Command Center
========================================================

Single admin-only operational panel for the Controlled Beta launch window.

Hard constraints (locked by user choices):
- CC-R1 (1c)  : ALL 9 sources + Beta-1 Checklist must be exposed in one payload
- CC-R2 (2b)  : polling 30s (client) + manual refresh, server returns `as_of`
- CC-R3 (3c)  : Beta-1 Checklist is auto-detected + supports manual override
- CC-R4 (4b)  : Open Alerts are limited to severities `critical` and `warning`
- CC-R5 (5a)  : admin-only (require_admin)

Aggregator payload contains:
- launch_status        (top header: phase + readiness + security + counts)
- treasury_pulse       (subset of /admin/treasury/pulse — Treasury-R1 compliant)
- lr2                  (LR2 snapshot subset: score, grade, scanner status)
- open_alerts          (critical + warning only)
- pending_kyc          (queue counts + samples)
- pending_compliance   (count of expirations/missing)
- pending_funding      (transfers in pending_review)
- pending_reconciliation (transfers with reconciliation flags)
- pending_capital_calls (lumen_lp_drawdowns unpaid)
- pending_distributions (lumen_payout_records.status == pending)
- beta1_checklist      (7 milestones with override metadata)

This module is **read-only with one exception**: the override endpoint
mutates `lumen_beta_checklist`. No new mocked data is introduced — every
metric is computed from existing collections at request time.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _now, _iso, _strip_mongo

logger = logging.getLogger("lumen.beta_command_center")

# ─────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────

CHECKLIST = "lumen_beta_checklist"
TRANSFERS = "lumen_institutional_transfers"

# 7 Beta-1 milestones (ordered for stable UI rendering)
BETA1_MILESTONES: list[dict[str, str]] = [
    {"id": "first_real_investor",     "label_uk": "Перший реальний інвестор",       "label_en": "First real investor"},
    {"id": "first_kyc_approved",      "label_uk": "Перший підтверджений KYC",        "label_en": "First KYC approved"},
    {"id": "first_certificate",       "label_uk": "Перший сертифікат",               "label_en": "First certificate issued"},
    {"id": "first_funding",           "label_uk": "Перше реальне поповнення",        "label_en": "First confirmed funding"},
    {"id": "first_payout",            "label_uk": "Перша виплата",                   "label_en": "First payout"},
    {"id": "first_quarterly_report",  "label_uk": "Перший квартальний звіт",         "label_en": "First quarterly report"},
    {"id": "first_operator",          "label_uk": "Перший оператор",                 "label_en": "First operator onboarded"},
]
BETA1_TOTAL = len(BETA1_MILESTONES)

# Thresholds for warning-level alerts
TTC_WARN_SECONDS = 3600          # > 1h time-to-confirm = warning
KYC_PENDING_HOURS = 24
COMPLIANCE_PENDING_HOURS = 24
EXCEPTION_RATE_CRITICAL = 0.10   # > 10% flagged transfers in window = critical
LR2_CRITICAL_BELOW = 90
SECURITY_CRITICAL_BELOW = 90

# Seed-account email pattern (excluded from "real" investor detection)
SEED_EMAIL_DOMAINS = ("@atlas.dev", "@devos.io")


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
        return False
    return any(email.lower().endswith(d) for d in SEED_EMAIL_DOMAINS)


# ─────────────────────────────────────────────────────────────────────────
# Beta-1 Checklist — auto-detection + override storage
# ─────────────────────────────────────────────────────────────────────────


async def ensure_beta_checklist_indexes() -> None:
    try:
        await db[CHECKLIST].create_index("milestone_id", unique=True)
        logger.info("BETA CHECKLIST: indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("BETA CHECKLIST: index ensure failed: %s", e)


async def _detect_first_real_investor() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    """First investor with kyc=approved on a non-seed email."""
    async for prof in db.lumen_investor_profiles.find(
            {"kyc_status": "approved"}, {"_id": 0}).sort("created_at", 1).limit(50):
        uid = prof.get("user_id")
        if not uid:
            continue
        user = await db.users.find_one({"user_id": uid},
                                          {"_id": 0, "email": 1, "name": 1})
        if not user or _is_seed_email(user.get("email")):
            continue
        return (uid, f"{user.get('name') or user.get('email')}",
                _parse_dt(prof.get("approved_at") or prof.get("updated_at") or prof.get("created_at")))
    return None, None, None


async def _detect_first_kyc_approved() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    """First investor whose KYC reached approved (seed accounts count too)."""
    doc = await db.lumen_investor_profiles.find_one(
        {"kyc_status": "approved"},
        {"_id": 0}, sort=[("approved_at", 1), ("updated_at", 1), ("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("user_id"), doc.get("user_id"),
            _parse_dt(doc.get("approved_at") or doc.get("updated_at") or doc.get("created_at")))


async def _detect_first_certificate() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    doc = await db.lumen_certificates.find_one(
        {"status": {"$nin": ["voided"]}}, {"_id": 0},
        sort=[("issued_at", 1), ("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("id"), doc.get("certificate_number") or doc.get("id"),
            _parse_dt(doc.get("issued_at") or doc.get("created_at")))


async def _detect_first_funding() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    doc = await db[TRANSFERS].find_one(
        {"$or": [{"canonical_status": "confirmed"}, {"status": "confirmed"}]},
        {"_id": 0},
        sort=[("settled_at", 1), ("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("id"), doc.get("reference") or doc.get("id"),
            _parse_dt(doc.get("settled_at") or doc.get("updated_at") or doc.get("created_at")))


async def _detect_first_payout() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    doc = await db.lumen_payout_records.find_one(
        {"status": {"$in": ["paid", "credited"]}}, {"_id": 0},
        sort=[("paid_date", 1), ("paid_at", 1), ("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("id"), doc.get("batch_id") or doc.get("id"),
            _parse_dt(doc.get("paid_date") or doc.get("paid_at") or doc.get("created_at")))


async def _detect_first_quarterly_report() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    doc = await db.lumen_reports.find_one(
        {"kind": "quarterly"}, {"_id": 0},
        sort=[("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("id"), doc.get("period") or doc.get("id"),
            _parse_dt(doc.get("created_at")))


async def _detect_first_operator() -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    doc = await db.lumen_operators.find_one(
        {"status": {"$in": ["verified", "approved", "active"]}}, {"_id": 0},
        sort=[("verified_at", 1), ("created_at", 1)])
    if not doc:
        return None, None, None
    return (doc.get("id"), doc.get("name") or doc.get("id"),
            _parse_dt(doc.get("verified_at") or doc.get("created_at")))


_DETECTORS = {
    "first_real_investor":    _detect_first_real_investor,
    "first_kyc_approved":     _detect_first_kyc_approved,
    "first_certificate":      _detect_first_certificate,
    "first_funding":          _detect_first_funding,
    "first_payout":           _detect_first_payout,
    "first_quarterly_report": _detect_first_quarterly_report,
    "first_operator":         _detect_first_operator,
}


async def _load_milestone(meta: dict) -> dict:
    mid = meta["id"]
    persisted = await db[CHECKLIST].find_one({"milestone_id": mid}, {"_id": 0})
    if not persisted:
        persisted = {
            "milestone_id": mid,
            "status": "pending",
            "detected_at": None,
            "detected_entity_id": None,
            "detected_label": None,
            "notes": None,
            "overridden_by": None,
            "overridden_at": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        try:
            await db[CHECKLIST].insert_one(dict(persisted))
        except Exception:
            pass

    # If admin already overrode, return as-is (overrides win).
    if persisted.get("overridden_by"):
        out = dict(persisted)
    else:
        # Auto-detect if not yet completed
        if persisted.get("status") != "completed":
            detector = _DETECTORS.get(mid)
            if detector:
                try:
                    entity_id, label, when = await detector()
                except Exception as e:  # pragma: no cover
                    logger.warning("detector failed for %s: %s", mid, e)
                    entity_id, label, when = None, None, None
                if entity_id:
                    persisted.update({
                        "status": "completed",
                        "detected_at": _iso(when or _utcnow()),
                        "detected_entity_id": entity_id,
                        "detected_label": label,
                        "updated_at": _now(),
                    })
                    await db[CHECKLIST].update_one(
                        {"milestone_id": mid},
                        {"$set": {"status": "completed",
                                   "detected_at": persisted["detected_at"],
                                   "detected_entity_id": entity_id,
                                   "detected_label": label,
                                   "updated_at": _now()}})
        out = dict(persisted)

    out["label_uk"] = meta["label_uk"]
    out["label_en"] = meta["label_en"]
    return _strip_mongo(out)


async def beta1_checklist_state() -> dict:
    """Return the full Beta-1 Checklist payload with computed progress."""
    items = []
    for meta in BETA1_MILESTONES:
        items.append(await _load_milestone(meta))
    completed = sum(1 for it in items if it.get("status") == "completed")
    return {
        "total": BETA1_TOTAL,
        "completed": completed,
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────
# Pending queues
# ─────────────────────────────────────────────────────────────────────────


async def _pending_kyc() -> dict:
    cutoff = _utcnow() - timedelta(hours=KYC_PENDING_HOURS)
    PENDING_KYC_STATUSES = ["submitted", "under_review", "pending", "in_progress"]
    total = await db.lumen_investor_profiles.count_documents(
        {"kyc_status": {"$in": PENDING_KYC_STATUSES}})
    stale = await db.lumen_investor_profiles.count_documents(
        {"kyc_status": {"$in": PENDING_KYC_STATUSES},
         "updated_at": {"$lte": cutoff}})
    samples: list[dict] = []
    async for p in db.lumen_investor_profiles.find(
            {"kyc_status": {"$in": PENDING_KYC_STATUSES}}, {"_id": 0}
            ).sort("updated_at", 1).limit(5):
        samples.append({
            "user_id": p.get("user_id"),
            "kyc_status": p.get("kyc_status"),
            "updated_at": _iso(p.get("updated_at")),
        })
    return {"total": total, "stale_24h": stale, "samples": samples}


async def _pending_compliance() -> dict:
    cutoff_24h = _utcnow() - timedelta(hours=COMPLIANCE_PENDING_HOURS)
    soon = _utcnow() + timedelta(days=45)
    missing_or_pending = await db.lumen_compliance_documents.count_documents(
        {"status": {"$in": ["missing", "pending", "submitted", "expired"]}})
    expired = await db.lumen_compliance_documents.count_documents(
        {"expires_at": {"$lt": _utcnow()}})
    expiring_soon = await db.lumen_compliance_documents.count_documents(
        {"expires_at": {"$gte": _utcnow(), "$lte": soon}})
    stale = await db.lumen_compliance_documents.count_documents(
        {"status": {"$in": ["pending", "submitted"]},
         "updated_at": {"$lte": cutoff_24h}})
    return {
        "total": missing_or_pending,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "stale_24h": stale,
    }


async def _pending_funding() -> dict:
    pending_review = await db[TRANSFERS].count_documents(
        {"$or": [{"canonical_status": "pending_review"},
                  {"canonical_status": {"$exists": False},
                   "status": {"$in": ["initiated", "sent"]}}]})
    submitted = await db[TRANSFERS].count_documents(
        {"$or": [{"canonical_status": "submitted"},
                  {"canonical_status": {"$exists": False}, "status": "pending"}]})
    samples: list[dict] = []
    async for t in db[TRANSFERS].find(
            {"$or": [{"canonical_status": "pending_review"},
                      {"canonical_status": "submitted"}]},
            {"_id": 0, "id": 1, "reference": 1, "amount": 1,
             "currency": 1, "rail": 1, "canonical_status": 1,
             "created_at": 1},
            ).sort("created_at", 1).limit(5):
        samples.append({
            "id": t.get("id"),
            "reference": t.get("reference"),
            "amount": t.get("amount"),
            "currency": t.get("currency"),
            "rail": t.get("rail"),
            "status": t.get("canonical_status"),
            "created_at": _iso(t.get("created_at")),
        })
    return {"total": pending_review + submitted,
            "pending_review": pending_review,
            "submitted": submitted,
            "samples": samples}


async def _pending_reconciliation() -> dict:
    """Transfers with reconciliation flags or missing references."""
    flagged = 0
    by_flag: dict[str, int] = {"currency_mismatch": 0,
                                 "amount_mismatch": 0,
                                 "missing_reference": 0,
                                 "unmatched": 0}
    async for t in db[TRANSFERS].find(
            {"$or": [{"canonical_status": {"$nin": ["confirmed", "rejected"]}},
                      {"canonical_status": {"$exists": False}}]},
            {"_id": 0, "reference": 1, "reconciliation": 1,
             "canonical_status": 1, "status": 1}):
        recon = t.get("reconciliation") or {}
        is_flagged = False
        if recon.get("currency_mismatch"):
            by_flag["currency_mismatch"] += 1
            is_flagged = True
        if abs(float(recon.get("delta_amount") or 0)) >= 0.01:
            by_flag["amount_mismatch"] += 1
            is_flagged = True
        if recon.get("matched") is False:
            by_flag["unmatched"] += 1
            is_flagged = True
        if not (t.get("reference") or "").strip():
            by_flag["missing_reference"] += 1
            is_flagged = True
        if is_flagged:
            flagged += 1
    return {"total": flagged, "by_flag": by_flag}


async def _pending_capital_calls() -> dict:
    unpaid = await db.lumen_lp_drawdowns.count_documents({"paid_at": None})
    unpaid_value = 0.0
    async for d in db.lumen_lp_drawdowns.find(
            {"paid_at": None}, {"_id": 0, "amount_uah": 1}):
        unpaid_value += float(d.get("amount_uah") or 0)
    return {"total": unpaid, "unpaid_value_uah": round(unpaid_value, 2)}


async def _pending_distributions() -> dict:
    pending = await db.lumen_payout_records.count_documents(
        {"status": {"$in": ["pending", "queued"]}})
    pending_value = 0.0
    async for r in db.lumen_payout_records.find(
            {"status": {"$in": ["pending", "queued"]}},
            {"_id": 0, "amount": 1}):
        pending_value += float(r.get("amount") or 0)
    return {"total": pending, "pending_value_uah": round(pending_value, 2)}


# ─────────────────────────────────────────────────────────────────────────
# Treasury Pulse + LR2 + Security score (delegated to existing modules)
# ─────────────────────────────────────────────────────────────────────────


async def _treasury_pulse() -> dict:
    try:
        from lumen_treasury import compute_kpis
        k = await compute_kpis(window_days=30)
        return {
            "as_of": k.get("as_of"),
            "pending_review_count": k.get("pending_review_count", 0),
            "matched_count": k.get("matched_count", 0),
            "confirmed_count": k.get("confirmed_count", 0),
            "rejected_count": k.get("rejected_count", 0),
            "today_volume_total": k.get("today_volume_total", 0),
            "volume_30d_total": k.get("volume_30d_total", 0),
            "time_to_confirm_avg_seconds": k.get("time_to_confirm_avg_seconds"),
            "exception_rate": k.get("exception_rate", 0),
        }
    except Exception as e:  # pragma: no cover
        logger.warning("treasury pulse failed: %s", e)
        return {"as_of": _iso(_utcnow()), "error": str(e)}


async def _lr2_snapshot() -> dict:
    """LR2 readiness snapshot (subset only)."""
    try:
        from lumen_launch_readiness import (
            audit_permission_matrix, run_invariants, reporting_integrity,
            conflicts_of_interest, demo_data_inventory,
            _compute_readiness_score, _grade,
        )
        perm = audit_permission_matrix()
        inv = await run_invariants()
        rep = await reporting_integrity()
        cof = await conflicts_of_interest()
        demo = await demo_data_inventory()
        score = _compute_readiness_score(perm, inv, rep, cof, demo)
        return {
            "score": score.get("total", 0),
            "max": score.get("max", 100),
            "grade": _grade(score.get("total", 0)),
            "parts": score.get("parts", []),
        }
    except Exception as e:  # pragma: no cover
        logger.warning("LR2 snapshot failed: %s", e)
        return {"score": 0, "max": 100, "grade": "F", "error": str(e)}


async def _security_score() -> int:
    try:
        from lumen_lr2_extended import _security_items
        items = await _security_items()
        weight = {"critical": 5, "high": 3, "medium": 1, "low": 0.5}
        total_max = sum(weight.get(i["severity"], 1) for i in items)
        earned = sum(weight.get(i["severity"], 1) for i in items if i.get("ok"))
        if not total_max:
            return 0
        return round(earned / total_max * 100)
    except Exception as e:  # pragma: no cover
        logger.warning("security score failed: %s", e)
        return 0


async def _scanner_status() -> dict:
    """Probe LR2 scanner liveness."""
    try:
        from lumen_lr2_extended import (
            _lr2_scan_task, _scan_interval_seconds,
        )
        running = bool(_lr2_scan_task and not _lr2_scan_task.done())
        return {"running": running, "interval_seconds": _scan_interval_seconds()}
    except Exception:
        return {"running": False, "interval_seconds": None}


# ─────────────────────────────────────────────────────────────────────────
# Open Alerts — critical + warning only
# ─────────────────────────────────────────────────────────────────────────


async def _open_alerts(lr2: dict, security: int, treasury: dict,
                          scanner: dict, recon: dict, kyc: dict,
                          compliance: dict) -> list[dict]:
    alerts: list[dict] = []
    now = _utcnow()

    def add(severity: str, kind: str, message: str, **extra):
        alerts.append({
            "severity": severity,
            "kind": kind,
            "message": message,
            "raised_at": _iso(now),
            **extra,
        })

    # CRITICAL — LR2 readiness regression
    if (lr2.get("score") or 0) < LR2_CRITICAL_BELOW:
        add("critical", "lr2_score_low",
            f"LR2 score {lr2.get('score')} < {LR2_CRITICAL_BELOW}",
            score=lr2.get("score"))

    # CRITICAL — Security review regression
    if security < SECURITY_CRITICAL_BELOW:
        add("critical", "security_score_low",
            f"Security score {security} < {SECURITY_CRITICAL_BELOW}",
            score=security)

    # CRITICAL — LR2 background scanner not running
    if scanner.get("running") is False:
        add("critical", "scanner_failed",
            "LR2 background scanner is not running")

    # CRITICAL — exception rate threshold
    er = float(treasury.get("exception_rate") or 0)
    if er > EXCEPTION_RATE_CRITICAL:
        add("critical", "exception_rate_high",
            f"Funding exception rate {round(er * 100, 1)}% "
            f"> {round(EXCEPTION_RATE_CRITICAL * 100)}%",
            exception_rate=er)

    # CRITICAL — open alerts from LR2 extended scanner
    async for a in db.lumen_critical_alerts.find(
            {"status": "open"}, {"_id": 0}).sort("opened_at", -1).limit(50):
        sev = (a.get("severity") or "high").lower()
        # Only show critical-from-DB at critical level; everything else as warning
        out_sev = "critical" if sev == "critical" else "warning"
        alerts.append({
            "severity": out_sev,
            "kind": a.get("kind") or "lr2_alert",
            "message": a.get("message") or a.get("kind"),
            "raised_at": _iso(a.get("opened_at") or a.get("updated_at")),
            "source": "lumen_critical_alerts",
            "id": a.get("id"),
        })

    # WARNING — reconciliation flags
    by_flag = (recon or {}).get("by_flag") or {}
    if (by_flag.get("missing_reference") or 0) > 0:
        add("warning", "missing_reference",
            f"{by_flag['missing_reference']} transfer(s) missing reference",
            count=by_flag["missing_reference"])
    if (by_flag.get("currency_mismatch") or 0) > 0:
        add("warning", "currency_mismatch",
            f"{by_flag['currency_mismatch']} transfer(s) with currency mismatch",
            count=by_flag["currency_mismatch"])
    if (by_flag.get("amount_mismatch") or 0) > 0:
        add("warning", "amount_mismatch",
            f"{by_flag['amount_mismatch']} transfer(s) with amount mismatch",
            count=by_flag["amount_mismatch"])
    if (recon.get("total") or 0) > 0:
        add("warning", "pending_reconciliation",
            f"{recon['total']} transfer(s) pending reconciliation",
            count=recon["total"])

    # WARNING — TTC > 1h
    ttc = treasury.get("time_to_confirm_avg_seconds")
    if ttc is not None and float(ttc) > TTC_WARN_SECONDS:
        add("warning", "time_to_confirm_high",
            f"Average time-to-confirm {round(float(ttc) / 60, 1)} min > 60 min",
            seconds=float(ttc))

    # WARNING — KYC pending > 24h
    if (kyc.get("stale_24h") or 0) > 0:
        add("warning", "kyc_stale",
            f"{kyc['stale_24h']} KYC profile(s) pending > 24h",
            count=kyc["stale_24h"])

    # WARNING — Compliance pending > 24h
    if (compliance.get("stale_24h") or 0) > 0:
        add("warning", "compliance_stale",
            f"{compliance['stale_24h']} compliance doc(s) pending > 24h",
            count=compliance["stale_24h"])

    return alerts


def _counts(alerts: list[dict]) -> tuple[int, int]:
    crit = sum(1 for a in alerts if a.get("severity") == "critical")
    warn = sum(1 for a in alerts if a.get("severity") == "warning")
    return crit, warn


# ─────────────────────────────────────────────────────────────────────────
# Aggregator (full command-center payload)
# ─────────────────────────────────────────────────────────────────────────


async def build_command_center() -> dict:
    """Build the full command-center payload (one round-trip)."""
    treasury = await _treasury_pulse()
    lr2 = await _lr2_snapshot()
    security = await _security_score()
    scanner = await _scanner_status()
    kyc = await _pending_kyc()
    compliance = await _pending_compliance()
    funding = await _pending_funding()
    recon = await _pending_reconciliation()
    capital_calls = await _pending_capital_calls()
    distributions = await _pending_distributions()
    checklist = await beta1_checklist_state()
    alerts = await _open_alerts(lr2, security, treasury, scanner,
                                  recon, kyc, compliance)
    crit_count, warn_count = _counts(alerts)
    launch_status = {
        "phase": "CONTROLLED_BETA",
        "readiness_score": lr2.get("score", 0),
        "readiness_max": lr2.get("max", 100),
        "readiness_grade": lr2.get("grade"),
        "security_score": security,
        "security_max": 100,
        "open_critical_alerts_count": crit_count,
        "open_warnings_count": warn_count,
        "beta1_progress_completed": checklist["completed"],
        "beta1_progress_total": checklist["total"],
        "scanner_running": bool(scanner.get("running")),
        "as_of": _iso(_utcnow()),
    }
    return {
        "as_of": _iso(_utcnow()),
        "launch_status": launch_status,
        "treasury_pulse": treasury,
        "lr2": lr2,
        "open_alerts": alerts,
        "pending_kyc": kyc,
        "pending_compliance": compliance,
        "pending_funding": funding,
        "pending_reconciliation": recon,
        "pending_capital_calls": capital_calls,
        "pending_distributions": distributions,
        "beta1_checklist": checklist,
    }


# ─────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────


router = APIRouter(prefix="/api/admin/beta", tags=["lumen-beta-command-center"])


@router.get("/launch-status")
async def launch_status(_=Depends(require_admin)):
    """Top header bundle — fastest call (no heavy pending queues besides what
    we already compute for the count). Used by the Launch Status banner that
    is the first thing admin sees after login."""
    treasury = await _treasury_pulse()
    lr2 = await _lr2_snapshot()
    security = await _security_score()
    scanner = await _scanner_status()
    kyc = await _pending_kyc()
    compliance = await _pending_compliance()
    recon = await _pending_reconciliation()
    checklist = await beta1_checklist_state()
    alerts = await _open_alerts(lr2, security, treasury, scanner,
                                  recon, kyc, compliance)
    crit_count, warn_count = _counts(alerts)
    return {
        "phase": "CONTROLLED_BETA",
        "readiness_score": lr2.get("score", 0),
        "readiness_max": lr2.get("max", 100),
        "readiness_grade": lr2.get("grade"),
        "security_score": security,
        "security_max": 100,
        "open_critical_alerts_count": crit_count,
        "open_warnings_count": warn_count,
        "beta1_progress_completed": checklist["completed"],
        "beta1_progress_total": checklist["total"],
        "scanner_running": bool(scanner.get("running")),
        "as_of": _iso(_utcnow()),
    }


@router.get("/command-center")
async def command_center(_=Depends(require_admin)):
    """Full aggregator payload (CC-R1)."""
    return await build_command_center()


@router.get("/checklist")
async def get_checklist(_=Depends(require_admin)):
    return await beta1_checklist_state()


class ChecklistOverrideIn(BaseModel):
    status: str = Field(..., description="completed | pending | not_applicable")
    notes: Optional[str] = Field(None, max_length=2000)


ALLOWED_OVERRIDE_STATUSES = {"completed", "pending", "not_applicable"}


@router.post("/checklist/{milestone_id}/override")
async def override_checklist(milestone_id: str,
                                payload: ChecklistOverrideIn,
                                user=Depends(require_admin)):
    if milestone_id not in {m["id"] for m in BETA1_MILESTONES}:
        raise HTTPException(status_code=404, detail=f"Unknown milestone: {milestone_id}")
    if payload.status not in ALLOWED_OVERRIDE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Use one of: {sorted(ALLOWED_OVERRIDE_STATUSES)}")
    now = _now()
    actor = user.get("email") or user.get("user_id") or "admin"
    set_doc = {
        "status": payload.status,
        "notes": payload.notes,
        "overridden_by": actor,
        "overridden_at": _iso(now),
        "updated_at": now,
    }
    await db[CHECKLIST].update_one(
        {"milestone_id": milestone_id},
        {"$set": set_doc, "$setOnInsert": {"milestone_id": milestone_id,
                                              "created_at": now}},
        upsert=True,
    )
    meta = next(m for m in BETA1_MILESTONES if m["id"] == milestone_id)
    return await _load_milestone(meta)


@router.delete("/checklist/{milestone_id}/override")
async def clear_override(milestone_id: str, _=Depends(require_admin)):
    """Clear the override and restore auto-detected state."""
    if milestone_id not in {m["id"] for m in BETA1_MILESTONES}:
        raise HTTPException(status_code=404, detail=f"Unknown milestone: {milestone_id}")
    await db[CHECKLIST].update_one(
        {"milestone_id": milestone_id},
        {"$set": {"overridden_by": None, "overridden_at": None,
                   "notes": None, "status": "pending",
                   "updated_at": _now()}},
    )
    meta = next(m for m in BETA1_MILESTONES if m["id"] == milestone_id)
    return await _load_milestone(meta)


@router.get("/alerts")
async def alerts(_=Depends(require_admin),
                  severity: Optional[str] = None):
    """List actionable alerts (critical + warning only, CC-R3)."""
    treasury = await _treasury_pulse()
    lr2 = await _lr2_snapshot()
    security = await _security_score()
    scanner = await _scanner_status()
    kyc = await _pending_kyc()
    compliance = await _pending_compliance()
    recon = await _pending_reconciliation()
    items = await _open_alerts(lr2, security, treasury, scanner,
                                 recon, kyc, compliance)
    if severity:
        sev = severity.lower()
        if sev not in {"critical", "warning"}:
            raise HTTPException(status_code=400,
                                  detail="severity must be 'critical' or 'warning'")
        items = [a for a in items if a.get("severity") == sev]
    crit, warn = _counts(items)
    return {
        "as_of": _iso(_utcnow()),
        "counts": {"critical": crit, "warning": warn, "total": len(items)},
        "items": items,
    }


__all__ = [
    "router",
    "build_command_center",
    "beta1_checklist_state",
    "ensure_beta_checklist_indexes",
    "BETA1_MILESTONES",
]
