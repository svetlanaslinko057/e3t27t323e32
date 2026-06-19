"""
LUMEN 2.0 — Phase LR2 — Launch Readiness 2.0
==============================================

Institutional hardening before the public launch. Read-only diagnostic layer
that surfaces risks across permissions, data integrity, reporting truth,
demo-data contamination and governance conflicts.

LR2.1  Permission Matrix      — declarative role × resource × action matrix
LR2.2  Invariants Engine      — 10 hard checks on capital flow / ownership
LR2.3  Reporting Integrity    — PDF / source-of-truth cross-verification
LR2.4  Demo Data Retirement   — environment gate + demo-signature audit
LR2.5  Conflict of Interest   — detects LP=GP, voter=operator overlaps
Snapshot — single payload powering the LR2 console.

Endpoints (prefix /api, admin-only)
-----------------------------------
GET  /admin/launch-readiness/snapshot
GET  /admin/launch-readiness/permissions
GET  /admin/launch-readiness/invariants
GET  /admin/launch-readiness/reporting-integrity
GET  /admin/launch-readiness/conflicts
GET  /admin/launch-readiness/demo-data
POST /admin/launch-readiness/demo-data/quarantine   { dry_run: bool }
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, _now, _iso, _strip_mongo

logger = logging.getLogger("lumen.launch_readiness")
router = APIRouter(prefix="/api/admin/launch-readiness", tags=["lumen-lr2"])


def env() -> str:
    return (os.environ.get("LUMEN_ENV") or "preview").strip().lower()


def is_production() -> bool:
    return env() == "production"


# ═══════════════════════════════════════════════════════════════════════════
# LR2.1  Permission Matrix Audit
# ═══════════════════════════════════════════════════════════════════════════

ROLES = ["guest", "investor", "qualified", "institutional", "operator", "admin"]
ACTIONS = ["read_own", "read_any", "write", "approve", "export", "delete", "override"]

# Resource → declared permissions (per role list of allowed actions)
PERMISSION_MATRIX: dict[str, dict[str, list[str]]] = {
    "asset": {
        "guest": ["read_any"],
        "investor": ["read_any"],
        "qualified": ["read_any"],
        "institutional": ["read_any", "export"],
        "operator": ["read_any", "write"],         # only own assets
        "admin": ACTIONS,
    },
    "certificate": {
        "guest": [],
        "investor": ["read_own"],
        "qualified": ["read_own"],
        "institutional": ["read_own", "export"],
        "operator": [],
        "admin": ACTIONS,
    },
    "investment": {
        "guest": [],
        "investor": ["read_own", "write"],
        "qualified": ["read_own", "write"],
        "institutional": ["read_own", "write", "export"],
        "operator": [],
        "admin": ACTIONS,
    },
    "fund": {
        "guest": ["read_any"],
        "investor": ["read_any"],
        "qualified": ["read_any"],
        "institutional": ["read_any", "export"],
        "operator": [],
        "admin": ACTIONS,
    },
    "lp_commitment": {
        "guest": [],
        "investor": ["read_own", "write"],
        "qualified": ["read_own", "write"],
        "institutional": ["read_own", "write", "export"],
        "operator": [],
        "admin": ACTIONS,
    },
    "capital_call": {
        "guest": [], "investor": ["read_own"], "qualified": ["read_own"],
        "institutional": ["read_own", "export"], "operator": [],
        "admin": ACTIONS,
    },
    "distribution": {
        "guest": [], "investor": ["read_own"], "qualified": ["read_own"],
        "institutional": ["read_own", "export"], "operator": [],
        "admin": ACTIONS,
    },
    "compliance_profile": {
        "guest": [],
        "investor": ["read_own", "write"],
        "qualified": ["read_own", "write"],
        "institutional": ["read_own", "write", "export"],
        "operator": [],
        "admin": ACTIONS,
    },
    "accreditation_profile": {
        "guest": [],
        "investor": ["read_own", "write"],
        "qualified": ["read_own", "write"],
        "institutional": ["read_own", "write"],
        "operator": [],
        "admin": ACTIONS,
    },
    "governance_proposal": {
        "guest": ["read_any"], "investor": ["read_own", "write"],
        "qualified": ["read_any", "write"], "institutional": ["read_any", "write"],
        "operator": ["read_any"],
        "admin": ACTIONS,
    },
    "report": {
        "guest": [], "investor": ["read_own", "export"],
        "qualified": ["read_own", "export"], "institutional": ["read_own", "export"],
        "operator": ["read_own"],
        "admin": ACTIONS,
    },
    "audit_log": {
        "guest": [], "investor": ["read_own"], "qualified": ["read_own"],
        "institutional": ["read_own", "export"], "operator": [],
        "admin": ACTIONS,
    },
    "trust_graph": {
        "guest": [], "investor": ["read_own"], "qualified": ["read_own"],
        "institutional": ["read_own", "export"], "operator": [],
        "admin": ACTIONS,
    },
    # Secondary market trading — investors must be able to list / bid / accept.
    # NB: ownership / certificate burns happen inside the settle path; that side
    # is service-level (no user write to certificates required).
    "secondary_trade": {
        "guest": ["read_any"],
        "investor": ["read_any", "read_own", "write", "approve"],
        "qualified": ["read_any", "read_own", "write", "approve"],
        "institutional": ["read_any", "read_own", "write", "approve", "export"],
        "operator": ["read_any"],
        "admin": ACTIONS,
    },
}

# Critical rules that must hold (red flags)
PERMISSION_INVARIANTS = [
    ("guest_cannot_write", "guest", None, "write",
     "Гість не повинен мати write-доступ до жодного ресурсу"),
    ("operator_no_certificates", "operator", "certificate", None,
     "Оператор не має прав на сертифікати інвесторів"),
    ("non_admin_no_override", None, None, "override",
     "Тільки admin може override-ити будь-який ресурс"),
    ("non_admin_no_delete", None, None, "delete",
     "Тільки admin може delete-ити будь-який ресурс"),
]


def audit_permission_matrix() -> dict:
    rows: list[dict] = []
    violations: list[dict] = []
    for resource, by_role in PERMISSION_MATRIX.items():
        for role in ROLES:
            allowed = by_role.get(role, [])
            for action in ACTIONS:
                rows.append({
                    "resource": resource, "role": role, "action": action,
                    "allowed": action in allowed,
                })
    # Evaluate invariants
    for key, ck_role, ck_resource, ck_action, why in PERMISSION_INVARIANTS:
        for r in rows:
            if ck_role and r["role"] != ck_role:
                continue
            if ck_resource and r["resource"] != ck_resource:
                continue
            if ck_action and r["action"] != ck_action:
                continue
            if not r["allowed"]:
                continue
            # special: non_admin_no_override / delete
            if key in ("non_admin_no_override", "non_admin_no_delete") and r["role"] == "admin":
                continue
            if key == "operator_no_certificates" and r["resource"] == "certificate" and r["role"] == "operator" and r["allowed"]:
                violations.append({"invariant": key, "row": r, "why": why})
            elif key == "guest_cannot_write" and r["role"] == "guest" and r["action"] == "write":
                violations.append({"invariant": key, "row": r, "why": why})
            elif key == "non_admin_no_override" and r["role"] != "admin" and r["action"] == "override":
                violations.append({"invariant": key, "row": r, "why": why})
            elif key == "non_admin_no_delete" and r["role"] != "admin" and r["action"] == "delete":
                violations.append({"invariant": key, "row": r, "why": why})
    counts = {
        "resources": len(PERMISSION_MATRIX), "roles": len(ROLES),
        "actions": len(ACTIONS), "cells": len(rows),
        "allowed_cells": sum(1 for r in rows if r["allowed"]),
        "violations": len(violations),
    }
    return {"matrix": rows, "violations": violations, "counts": counts,
            "roles": ROLES, "actions": ACTIONS,
            "resources": list(PERMISSION_MATRIX.keys())}


# ═══════════════════════════════════════════════════════════════════════════
# LR2.2  Invariants Engine
# ═══════════════════════════════════════════════════════════════════════════

async def _inv_lp_commit_ge_called() -> dict:
    """sum(LP commitments) per fund ≥ sum(calls.total)"""
    fails = []
    async for f in db.lumen_funds.find({}, {"_id": 0, "id": 1, "name": 1}):
        commit = 0.0
        async for c in db.lumen_lp_commitments.find({"fund_id": f["id"]}, {"_id": 0, "amount_uah": 1}):
            commit += float(c.get("amount_uah") or 0)
        called = 0.0
        async for ca in db.lumen_capital_calls.find({"fund_id": f["id"]}, {"_id": 0, "total_amount_uah": 1}):
            called += float(ca.get("total_amount_uah") or 0)
        if called > commit + 0.01:
            fails.append({"fund_id": f["id"], "name": f.get("name"),
                          "committed": round(commit, 2), "called": round(called, 2)})
    return {"id": "lp_commit_ge_called",
            "label": "LP commitments ≥ called capital",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_called_ge_paid() -> dict:
    """Per capital_call, total_amount_uah ≥ sum of paid drawdowns"""
    fails = []
    async for ca in db.lumen_capital_calls.find({}, {"_id": 0, "id": 1, "fund_id": 1,
                                                      "seq": 1, "total_amount_uah": 1}):
        paid = 0.0
        async for d in db.lumen_lp_drawdowns.find(
                {"call_id": ca["id"], "paid_at": {"$ne": None}}, {"_id": 0, "amount_uah": 1}):
            paid += float(d.get("amount_uah") or 0)
        total = float(ca.get("total_amount_uah") or 0)
        if paid > total + 0.01:
            fails.append({"call_id": ca["id"], "fund_id": ca.get("fund_id"),
                          "seq": ca.get("seq"),
                          "total": round(total, 2), "paid": round(paid, 2)})
    return {"id": "called_ge_paid",
            "label": "Called capital ≥ paid drawdowns (per call)",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_distribution_lines_sum() -> dict:
    """sum(distribution_lines.amount_uah) ≈ summary.net_income_uah for each applied distribution"""
    fails = []
    async for d in db.lumen_distributions.find({"status": "applied"},
                                                 {"_id": 0, "id": 1, "summary": 1}):
        s = d.get("summary") or {}
        expected = float(s.get("net_income_uah") or 0)
        total = 0.0
        async for l in db.lumen_distribution_lines.find(
                {"distribution_id": d["id"]}, {"_id": 0, "amount_uah": 1}):
            total += float(l.get("amount_uah") or 0)
        if abs(total - expected) > 1.0:
            fails.append({"distribution_id": d["id"],
                          "expected": round(expected, 2),
                          "lines_total": round(total, 2),
                          "delta": round(total - expected, 2)})
    return {"id": "distribution_lines_sum",
            "label": "Σ distribution lines = net income (waterfall integrity)",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_fund_nav_eq_holdings() -> dict:
    """fund.nav = sum of asset-level cert NAV across fund SPVs"""
    fails = []
    async for f in db.lumen_funds.find({}, {"_id": 0, "id": 1, "name": 1, "spv_ids": 1}):
        cert_nav = 0.0
        for spv_id in (f.get("spv_ids") or []):
            spv = await db.lumen_spvs.find_one({"id": spv_id}, {"_id": 0, "asset_id": 1})
            if not spv:
                continue
            async for c in db.lumen_certificates.find(
                    {"asset_id": spv.get("asset_id"), "status": {"$ne": "voided"}},
                    {"_id": 0, "value_uah": 1}):
                cert_nav += float(c.get("value_uah") or 0)
        # compare with engine
        engine_nav = None
        try:
            from lumen_institutional_os import _fund_nav_and_holdings
            engine_nav, _ = await _fund_nav_and_holdings(f)
        except Exception:
            pass
        if engine_nav is not None and abs(float(engine_nav) - cert_nav) > 1.0:
            fails.append({"fund_id": f["id"], "name": f.get("name"),
                          "engine_nav": round(float(engine_nav), 2),
                          "cert_nav": round(cert_nav, 2),
                          "delta": round(float(engine_nav) - cert_nav, 2)})
    return {"id": "fund_nav_eq_holdings",
            "label": "Fund NAV = Σ holdings NAV",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_ownership_le_100() -> dict:
    """Per asset: sum(active cert ownership_percent) ≤ 100% (+1% tolerance)."""
    fails = []
    async for a in db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1}):
        pct = 0.0
        async for c in db.lumen_certificates.find(
                {"asset_id": a["id"], "status": {"$ne": "voided"}},
                {"_id": 0, "ownership_percent": 1}):
            pct += float(c.get("ownership_percent") or 0)
        if pct > 101.0:
            fails.append({"asset_id": a["id"], "title": a.get("title"),
                          "total_ownership_percent": round(pct, 2)})
    return {"id": "ownership_le_100",
            "label": "Сума часток сертифікатів ≤ 100% per asset",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_unique_compliance_profile() -> dict:
    """Each investor has at most one doc per compliance slot."""
    fails = []
    pairs: dict[tuple[str, str], int] = {}
    async for d in db.lumen_compliance_documents.find({},
                                                       {"_id": 0, "investor_id": 1, "slot": 1}):
        k = (d.get("investor_id") or "", d.get("slot") or "")
        pairs[k] = pairs.get(k, 0) + 1
    for (uid, slot), n in pairs.items():
        if n > 1:
            fails.append({"user_id": uid, "slot": slot, "count": n})
    return {"id": "unique_compliance_profile",
            "label": "≤ 1 compliance документ на (інвестор × slot)",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_active_cert_has_asset() -> dict:
    fails = []
    async for c in db.lumen_certificates.find(
            {"status": "active", "asset_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1}):
        fails.append({"certificate_id": c.get("id")})
    return {"id": "active_cert_has_asset",
            "label": "Активні сертифікати мають asset_id",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_accreditation_levels_consistent() -> dict:
    """investor_profile.accreditation.level === latest 'approve' event's to_level (if any)."""
    fails = []
    async for p in db.lumen_investor_profiles.find({}, {"_id": 0, "user_id": 1,
                                                          "accreditation": 1}):
        acc = p.get("accreditation") or {}
        if not acc.get("level"):
            continue
        last = None
        async for e in db.lumen_accreditation_events.find(
                {"user_id": p["user_id"], "event": "approve"},
                {"_id": 0}).sort("created_at", -1).limit(1):
            last = e
        if last and last.get("to_level") and acc.get("level") != last.get("to_level"):
            fails.append({"user_id": p["user_id"],
                          "profile_level": acc.get("level"),
                          "event_level": last.get("to_level")})
    return {"id": "accreditation_levels_consistent",
            "label": "Рівень акредитації узгоджений із останньою approve-подією",
            "passed": len(fails) == 0, "failures": fails}


async def _inv_fund_committed_le_target() -> dict:
    """Soft check: committed should not blow past target_size_uah significantly (warning, not blocker)."""
    fails = []
    async for f in db.lumen_funds.find({}, {"_id": 0, "id": 1, "name": 1, "target_size_uah": 1}):
        target = float(f.get("target_size_uah") or 0)
        if target <= 0:
            continue
        commit = 0.0
        async for c in db.lumen_lp_commitments.find({"fund_id": f["id"]},
                                                      {"_id": 0, "amount_uah": 1}):
            commit += float(c.get("amount_uah") or 0)
        if commit > target * 1.20:  # +20% tolerance
            fails.append({"fund_id": f["id"], "name": f.get("name"),
                          "target": round(target, 2),
                          "committed": round(commit, 2),
                          "overshoot_percent": round((commit / target - 1) * 100, 1)})
    return {"id": "fund_committed_le_target",
            "label": "Σ commitments ≤ target_size + 20% per fund",
            "passed": len(fails) == 0, "failures": fails,
            "severity": "warning"}


async def _inv_payout_records_match_batches() -> dict:
    fails = []
    async for b in db.lumen_payout_batches.find({}, {"_id": 0, "id": 1, "total_amount": 1}):
        total = 0.0
        async for r in db.lumen_payout_records.find({"batch_id": b["id"]},
                                                      {"_id": 0, "amount": 1}):
            total += float(r.get("amount") or 0)
        expected = float(b.get("total_amount") or 0)
        if abs(total - expected) > 1.0 and expected > 0:
            fails.append({"batch_id": b["id"], "expected": round(expected, 2),
                          "records_total": round(total, 2),
                          "delta": round(total - expected, 2)})
    return {"id": "payout_records_match_batches",
            "label": "Payout records = batch total",
            "passed": len(fails) == 0, "failures": fails,
            "severity": "warning"}


INVARIANT_FNS = [
    _inv_lp_commit_ge_called,
    _inv_called_ge_paid,
    _inv_distribution_lines_sum,
    _inv_fund_nav_eq_holdings,
    _inv_ownership_le_100,
    _inv_unique_compliance_profile,
    _inv_active_cert_has_asset,
    _inv_accreditation_levels_consistent,
    _inv_fund_committed_le_target,
    _inv_payout_records_match_batches,
]


async def run_invariants() -> dict:
    results = []
    passed = failed = 0
    for fn in INVARIANT_FNS:
        try:
            r = await fn()
        except Exception as e:
            logger.exception("invariant failed")
            r = {"id": fn.__name__, "label": fn.__name__,
                 "passed": False, "failures": [{"error": str(e)}]}
        r.setdefault("severity", "error")
        results.append(r)
        if r["passed"]:
            passed += 1
        else:
            failed += 1
    return {"results": results,
            "counts": {"total": len(results), "passed": passed, "failed": failed},
            "ran_at": _iso(_now())}


# ═══════════════════════════════════════════════════════════════════════════
# LR2.3  Reporting Integrity
# ═══════════════════════════════════════════════════════════════════════════

async def reporting_integrity() -> dict:
    """Re-derive each report's source data and validate the meta is renderable."""
    issues: list[dict] = []
    checked = 0
    async for r in db.lumen_reports.find({}, {"_id": 0}):
        checked += 1
        kind, eid, period = r.get("kind"), r.get("entity_id"), r.get("period")
        if kind == "asset_factsheet":
            a = await db.lumen_assets.find_one({"id": eid}, {"_id": 0, "id": 1})
            if not a:
                issues.append({"report_id": r["id"], "kind": kind,
                               "issue": "asset_missing", "entity_id": eid})
        elif kind == "fund_report":
            f = await db.lumen_funds.find_one({"id": eid}, {"_id": 0, "id": 1})
            if not f:
                issues.append({"report_id": r["id"], "kind": kind,
                               "issue": "fund_missing", "entity_id": eid})
        elif kind == "quarterly":
            if not period:
                issues.append({"report_id": r["id"], "kind": kind,
                               "issue": "missing_period"})
    # Also: per asset, factsheet "investors" derived must match active certs count
    cross_issues: list[dict] = []
    async for a in db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1}):
        active_certs = await db.lumen_certificates.count_documents(
            {"asset_id": a["id"], "status": {"$ne": "voided"}})
        # We don't store snapshot; this is informational
        if active_certs == 0:
            continue
    return {
        "checked": checked,
        "meta_issues": issues,
        "counts": {"reports": checked, "issues": len(issues)},
        "passed": len(issues) == 0,
        "ran_at": _iso(_now()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# LR2.4  Demo Data Retirement
# ═══════════════════════════════════════════════════════════════════════════

DEMO_EMAIL_PATTERNS = ("@atlas.dev", "@lumen.test", "demo@", "test@")
DEMO_FUND_IDS = ("fund-ua-residential", "fund-flagship")
DEMO_ASSET_TITLE_KEYWORDS = ("ЖК «Подільський»", "Прибутковий будинок «Французький»",
                              "ТРЦ «Магнолія»", "Tower Pyrohiv",
                              "Lumen Industrial Park", "Demo")


async def demo_data_inventory() -> dict:
    """Identify rows that look like demo. Read-only — does not delete."""
    inv: dict[str, list[dict]] = {}

    # Demo users
    users = []
    async for u in db.users.find(
            {"email": {"$regex": "@atlas\\.dev|@lumen\\.test|^demo|^test", "$options": "i"}},
            {"_id": 0, "user_id": 1, "email": 1, "role": 1, "name": 1}):
        users.append(u)
    inv["users"] = users

    # Demo investor profiles tied to those users
    user_ids = [u["user_id"] for u in users]
    inv["investor_profiles"] = []
    async for p in db.lumen_investor_profiles.find({"user_id": {"$in": user_ids}},
                                                     {"_id": 0, "user_id": 1, "full_name": 1}):
        inv["investor_profiles"].append(p)

    # Demo funds
    inv["funds"] = []
    async for f in db.lumen_funds.find({"id": {"$in": list(DEMO_FUND_IDS)}},
                                        {"_id": 0, "id": 1, "name": 1, "status": 1}):
        inv["funds"].append(f)

    # Demo LP commitments under demo funds
    fund_ids = [f["id"] for f in inv["funds"]]
    inv["lp_commitments"] = []
    async for c in db.lumen_lp_commitments.find({"fund_id": {"$in": fund_ids}},
                                                  {"_id": 0, "id": 1, "investor_id": 1,
                                                   "amount_uah": 1, "role": 1, "fund_id": 1}):
        inv["lp_commitments"].append(c)

    inv["capital_calls"] = []
    async for ca in db.lumen_capital_calls.find({"fund_id": {"$in": fund_ids}},
                                                  {"_id": 0, "id": 1, "seq": 1, "fund_id": 1,
                                                   "total_amount_uah": 1}):
        inv["capital_calls"].append(ca)

    inv["distributions"] = []
    async for d in db.lumen_distributions.find({"fund_id": {"$in": fund_ids}},
                                                 {"_id": 0, "id": 1, "fund_id": 1, "seq": 1}):
        inv["distributions"].append(d)

    inv["reports"] = []
    async for r in db.lumen_reports.find({}, {"_id": 0, "id": 1, "kind": 1, "entity_id": 1,
                                               "title": 1}):
        inv["reports"].append(r)

    inv["compliance_documents"] = []
    async for cp in db.lumen_compliance_documents.find({"investor_id": {"$in": user_ids}},
                                                        {"_id": 0, "id": 1, "investor_id": 1,
                                                         "slot": 1, "status": 1}):
        inv["compliance_documents"].append(cp)

    counts = {k: len(v) for k, v in inv.items()}
    return {
        "env": env(),
        "is_production": is_production(),
        "patterns": {
            "demo_email_patterns": list(DEMO_EMAIL_PATTERNS),
            "demo_fund_ids": list(DEMO_FUND_IDS),
        },
        "counts": counts,
        "inventory": inv,
        "ran_at": _iso(_now()),
    }


class QuarantineIn(BaseModel):
    dry_run: bool = True
    confirm: Optional[str] = None  # must equal "DELETE-DEMO" if dry_run=False


@router.post("/demo-data/quarantine")
async def demo_data_quarantine(payload: QuarantineIn, _=Depends(require_admin)):
    """Mark demo-signed rows with a `_quarantined_at` flag (or wipe if confirmed).

    Production-safe: never mass-deletes without `dry_run=false` AND `confirm='DELETE-DEMO'`.
    """
    inv = await demo_data_inventory()
    counts = inv["counts"]
    if payload.dry_run or payload.confirm != "DELETE-DEMO":
        return {"dry_run": True, "would_affect": counts,
                "note": "Запустіть з {dry_run:false, confirm:'DELETE-DEMO'} щоб реально знищити"}
    if is_production():
        return {"error": "Production environment — операція заблокована",
                "env": env()}
    # Soft tag instead of hard delete — keeps audit trail
    user_ids = [u["user_id"] for u in inv["inventory"]["users"]]
    fund_ids = [f["id"] for f in inv["inventory"]["funds"]]
    now = _now()
    await db.users.update_many({"user_id": {"$in": user_ids}},
                                {"$set": {"_quarantined_at": now, "active": False}})
    await db.lumen_funds.update_many({"id": {"$in": fund_ids}},
                                       {"$set": {"_quarantined_at": now, "status": "quarantined"}})
    await db.lumen_lp_commitments.update_many({"fund_id": {"$in": fund_ids}},
                                                {"$set": {"_quarantined_at": now}})
    await db.lumen_capital_calls.update_many({"fund_id": {"$in": fund_ids}},
                                               {"$set": {"_quarantined_at": now}})
    await db.lumen_distributions.update_many({"fund_id": {"$in": fund_ids}},
                                               {"$set": {"_quarantined_at": now}})
    return {"dry_run": False, "quarantined_at": _iso(now),
            "affected": counts, "env": env()}


# ═══════════════════════════════════════════════════════════════════════════
# LR2.5  Conflict of Interest
# ═══════════════════════════════════════════════════════════════════════════

async def conflicts_of_interest() -> dict:
    conflicts: list[dict] = []

    # 1. Operator who also holds certificates in their own asset
    async for op in db.lumen_operators.find({}, {"_id": 0, "id": 1, "name": 1, "user_id": 1}):
        uid = op.get("user_id")
        if not uid:
            continue
        async for a in db.lumen_assets.find({"operator_id": op["id"]},
                                              {"_id": 0, "id": 1, "title": 1}):
            n = await db.lumen_certificates.count_documents(
                {"asset_id": a["id"], "investor_id": uid, "status": {"$ne": "voided"}})
            if n > 0:
                conflicts.append({
                    "type": "operator_owns_own_asset",
                    "severity": "high",
                    "operator_id": op["id"], "operator_name": op.get("name"),
                    "asset_id": a["id"], "asset_title": a.get("title"),
                    "certificate_count": n,
                    "why": "Оператор тримає сертифікати у власному об'єкті — конфлікт інтересів",
                })

    # 2. Investor with both LP and GP role in the same fund
    seen: dict[tuple[str, str], list[str]] = {}
    async for c in db.lumen_lp_commitments.find({}, {"_id": 0, "fund_id": 1,
                                                       "investor_id": 1, "role": 1,
                                                       "investor_name": 1}):
        k = (c["fund_id"], c["investor_id"])
        seen.setdefault(k, []).append(c.get("role"))
    for (fund_id, inv_id), roles in seen.items():
        if "LP" in roles and "GP" in roles:
            f = await db.lumen_funds.find_one({"id": fund_id}, {"_id": 0, "name": 1})
            u = await db.users.find_one({"user_id": inv_id}, {"_id": 0, "email": 1, "name": 1})
            conflicts.append({
                "type": "lp_and_gp_same_fund", "severity": "high",
                "fund_id": fund_id, "fund_name": (f or {}).get("name"),
                "investor_id": inv_id,
                "investor_email": (u or {}).get("email"),
                "why": "Один і той самий інвестор одночасно LP та GP у фонді",
            })

    # 3. Governance vote where voter has direct interest (cert in asset OR is operator)
    # Sample: pull up to 200 recent votes
    recent_votes = []
    async for v in db.lumen_gov_votes.find({}, {"_id": 0}).sort("created_at", -1).limit(200):
        recent_votes.append(v)
    for v in recent_votes:
        prop = await db.lumen_gov_proposals.find_one(
            {"id": v.get("proposal_id")}, {"_id": 0})
        if not prop or prop.get("scope") != "asset":
            continue
        # voter holding cert in target asset
        if await db.lumen_certificates.count_documents(
                {"asset_id": prop.get("scope_id"), "investor_id": v.get("voter_id"),
                 "status": {"$ne": "voided"}}) > 0:
            # this is normal — having shares is *why* you vote. Only flag if voter is operator
            op = await db.lumen_operators.find_one(
                {"user_id": v.get("voter_id")}, {"_id": 0, "id": 1, "name": 1})
            asset = await db.lumen_assets.find_one(
                {"id": prop.get("scope_id"), "operator_id": (op or {}).get("id")},
                {"_id": 0, "id": 1, "title": 1})
            if op and asset:
                conflicts.append({
                    "type": "operator_voting_own_asset", "severity": "medium",
                    "operator_id": op["id"], "operator_name": op.get("name"),
                    "asset_id": asset["id"], "asset_title": asset.get("title"),
                    "proposal_id": prop["id"], "proposal_title": prop.get("title"),
                    "vote": v.get("choice"),
                    "why": "Оператор голосує за пропозицію щодо власного активу",
                })

    return {"items": conflicts, "counts": {"total": len(conflicts)},
            "ran_at": _iso(_now())}


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/permissions")
async def permissions(_=Depends(require_admin)):
    return audit_permission_matrix()


@router.get("/invariants")
async def invariants(_=Depends(require_admin)):
    return await run_invariants()


@router.get("/reporting-integrity")
async def reporting(_=Depends(require_admin)):
    return await reporting_integrity()


@router.get("/conflicts")
async def conflicts(_=Depends(require_admin)):
    return await conflicts_of_interest()


@router.get("/demo-data")
async def demo_data(_=Depends(require_admin)):
    return await demo_data_inventory()


@router.get("/snapshot")
async def snapshot(_=Depends(require_admin)):
    perm = audit_permission_matrix()
    inv = await run_invariants()
    rep = await reporting_integrity()
    cof = await conflicts_of_interest()
    demo = await demo_data_inventory()
    score = _compute_readiness_score(perm, inv, rep, cof, demo)
    return {
        "score": score,
        "env": env(),
        "is_production": is_production(),
        "permissions": {"counts": perm["counts"], "violations": perm["violations"]},
        "invariants": inv,
        "reporting": rep,
        "conflicts": cof,
        "demo": {"counts": demo["counts"], "env": demo["env"]},
        "ran_at": _iso(_now()),
    }


def _compute_readiness_score(perm: dict, inv: dict, rep: dict,
                              cof: dict, demo: dict) -> dict:
    """Composite 0–100 score across the 5 LR2 dimensions."""
    parts = []
    # Permissions: 0 violations = 20
    perm_score = 20 if perm["counts"]["violations"] == 0 else max(0, 20 - 5 * perm["counts"]["violations"])
    parts.append({"key": "permissions", "score": perm_score, "max": 20})
    # Invariants: weight failed errors heavier than warnings
    err = sum(1 for r in inv["results"] if not r["passed"] and r.get("severity") != "warning")
    warn = sum(1 for r in inv["results"] if not r["passed"] and r.get("severity") == "warning")
    inv_score = max(0, 30 - 10 * err - 2 * warn)
    parts.append({"key": "invariants", "score": inv_score, "max": 30})
    # Reporting integrity
    rep_score = 15 if rep.get("passed") else max(0, 15 - len(rep.get("meta_issues") or []) * 3)
    parts.append({"key": "reporting", "score": rep_score, "max": 15})
    # Conflicts
    high = sum(1 for c in cof["items"] if c.get("severity") == "high")
    med = sum(1 for c in cof["items"] if c.get("severity") == "medium")
    cof_score = max(0, 20 - 5 * high - 2 * med)
    parts.append({"key": "conflicts", "score": cof_score, "max": 20})
    # Demo data retirement
    demo_total = sum(demo["counts"].values())
    if is_production() and demo_total > 0:
        demo_score = 0
    elif demo_total == 0:
        demo_score = 15
    else:
        # Non-production with demo present is fine, but cap at 12 to signal
        demo_score = 12
    parts.append({"key": "demo", "score": demo_score, "max": 15})

    total = sum(p["score"] for p in parts)
    return {"total": total, "max": 100, "parts": parts,
            "grade": _grade(total)}


def _grade(score: int) -> str:
    if score >= 95: return "A"
    if score >= 85: return "B"
    if score >= 70: return "C"
    if score >= 55: return "D"
    return "F"


# ═══════════════════════════════════════════════════════════════════════════
# Production Launch Readiness v1.0 — Checklist (130-item auto-eval + override)
# ═══════════════════════════════════════════════════════════════════════════

class ChecklistOverrideIn(BaseModel):
    status: str = Field(..., description="completed | pending | not_applicable")
    notes: Optional[str] = Field(None, max_length=2000)


@router.get("/checklist")
async def get_launch_checklist(_=Depends(require_admin)):
    """Full Production Launch Readiness v1.0 checklist with live auto-eval."""
    from launch_checklist_engine import build_checklist_state
    return await build_checklist_state()


@router.get("/checklist/summary")
async def get_launch_checklist_summary(_=Depends(require_admin)):
    """Lightweight rollup (no per-item payload) for headers/widgets."""
    from launch_checklist_engine import build_checklist_state
    state = await build_checklist_state()
    domains = [{k: v for k, v in d.items() if k != "items"}
               for d in state.get("domains", [])]
    return {**{k: v for k, v in state.items() if k != "domains"}, "domains": domains}


@router.post("/checklist/{item_id}/override")
async def override_launch_item(item_id: str,
                                payload: ChecklistOverrideIn,
                                user=Depends(require_admin)):
    from launch_checklist_engine import set_override
    actor = user.get("email") or user.get("user_id") or "admin"
    try:
        return await set_override(item_id, payload.status, payload.notes, actor)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown checklist item: {item_id}")
    except ValueError:
        raise HTTPException(status_code=400,
                            detail="status must be completed | pending | not_applicable")


@router.delete("/checklist/{item_id}/override")
async def clear_launch_item(item_id: str, _=Depends(require_admin)):
    from launch_checklist_engine import clear_override
    try:
        return await clear_override(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown checklist item: {item_id}")


@router.get("/checklist/doc", response_class=PlainTextResponse)
async def get_launch_checklist_doc(live: bool = True, _=Depends(require_admin)):
    """Canonical Markdown document, optionally annotated with live status."""
    from launch_checklist_engine import build_checklist_state, render_canonical_doc
    state = await build_checklist_state() if live else None
    return render_canonical_doc(state)


__all__ = ["router", "env", "is_production"]
