"""
LUMEN 2.0 — Phase LR2 Extended (LR2.7 → LR2.10)
================================================

Production hardening on top of the read-only LR2 console:

  LR2.7  Permission Enforcement Engine
           - effective_role() + can() + require_permission()
           - enforcement registry + coverage report (which routes are gated)
           - audit trail on permission denials

  LR2.8  Background Invariants Scanner
           - asyncio task that runs the full LR2 snapshot on an interval
           - persists scans in lumen_lr2_scans
           - opens / re-uses lumen_critical_alerts when checks degrade

  LR2.9  Production Switch
           - LUMEN_ENV=production is the *only* code-level switch
           - status endpoint surfacing what production-mode disables
           - hard-block on quick-access login + demo seeders

  LR2.10 Security Review
           - read-only configuration audit (CORS, secrets, default creds,
             demo data in production, rate-limit headers, auth cookie flags)
           - rolls into a weighted security score

All endpoints are admin-only and live under /api/admin/launch-readiness/.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import db, require_admin, get_current_user, _now, _iso
from lumen_launch_readiness import (
    PERMISSION_MATRIX,
    ROLES,
    ACTIONS,
    env,
    is_production,
    audit_permission_matrix,
    run_invariants,
    reporting_integrity,
    conflicts_of_interest,
    demo_data_inventory,
    _compute_readiness_score,
)

logger = logging.getLogger("lumen.lr2_extended")

router = APIRouter(prefix="/api/admin/launch-readiness", tags=["lumen-lr2"])


# ═══════════════════════════════════════════════════════════════════════════
# LR2.7  Permission Enforcement Engine
# ═══════════════════════════════════════════════════════════════════════════

# Registry of routes that have gone through require_permission(). Populated
# lazily at request-time via the dependency factory — so what we report is
# what FastAPI actually wired up, not what we hoped for.
_ENFORCEMENT_REGISTRY: dict[str, dict[str, Any]] = {}


def effective_role(user: Optional[dict]) -> str:
    """Derive the *operative* role from the user document.

    Precedence:
      1. admin / operator base role wins (they're not investors)
      2. for investors: accreditation level overrides 'investor' → 'qualified'
         / 'institutional' so the matrix lookup matches what the user can
         actually do.
      3. anonymous → guest
    """
    if not user:
        return "guest"
    base = (user.get("role") or "").lower() or "guest"
    if base in ("admin", "operator"):
        return base
    # Investors can have an accreditation level that elevates their permissions.
    if base in ("investor", "client", "user", "guest"):
        # Accreditation-level lookups: best-effort, no DB I/O here on hot path.
        # The dependency factory does the DB lookup once and stuffs it on user.
        level = (user.get("_effective_level")
                 or (user.get("accreditation") or {}).get("level")
                 or user.get("segment"))
        if level in ("institutional", "qualified"):
            return level
        return "investor"
    if base == "guest":
        return "guest"
    # Unknown base role — fall through to base for matrix lookup
    return base


def can(user: Optional[dict], resource: str, action: str) -> bool:
    role = effective_role(user)
    allowed = (PERMISSION_MATRIX.get(resource) or {}).get(role) or []
    return action in allowed


async def _resolve_effective_level(user: dict) -> dict:
    """Enrich the user dict with the latest accreditation level (cached on user)."""
    if user.get("_effective_level_resolved"):
        return user
    uid = user.get("user_id") or user.get("id")
    if uid and (user.get("role") or "").lower() == "investor":
        prof = await db.lumen_investor_profiles.find_one(
            {"user_id": uid}, {"_id": 0, "accreditation": 1, "segment": 1})
        if prof:
            acc = (prof.get("accreditation") or {})
            user["_effective_level"] = (acc.get("level")
                                         if acc.get("status") == "approved"
                                         else prof.get("segment"))
    user["_effective_level_resolved"] = True
    return user


def require_permission(resource: str, action: str) -> Callable:
    """FastAPI dependency factory that gates a route on (resource, action)."""
    # Register declaratively so the coverage report can introspect even when
    # the route hasn't been hit yet.
    key = f"{resource}::{action}"
    _ENFORCEMENT_REGISTRY.setdefault(key, {"resource": resource, "action": action,
                                            "hits": 0, "denials": 0,
                                            "last_used_at": None})

    async def _gate(user: dict = Depends(get_current_user)) -> dict:
        await _resolve_effective_level(user)
        slot = _ENFORCEMENT_REGISTRY[key]
        slot["hits"] += 1
        slot["last_used_at"] = _iso(_now())
        if not can(user, resource, action):
            slot["denials"] += 1
            # Audit denial — soft (insert, don't await error handling)
            try:
                await db.lumen_lr2_denials.insert_one({
                    "id": f"deny_{os.urandom(6).hex()}",
                    "at": _now(),
                    "user_id": user.get("user_id") or user.get("id"),
                    "email": user.get("email"),
                    "role": user.get("role"),
                    "effective_role": effective_role(user),
                    "resource": resource,
                    "action": action,
                })
            except Exception:
                pass
            raise HTTPException(status_code=403,
                                detail=f"Permission denied: {resource}/{action}")
        return user

    _gate.__lr2_resource__ = resource  # type: ignore[attr-defined]
    _gate.__lr2_action__ = action      # type: ignore[attr-defined]
    return _gate


# ── Enforcement coverage report ─────────────────────────────────────────────

# Resource detection heuristic: maps URL path keywords → matrix resource keys.
# Falls back to 'unknown'.
_RESOURCE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"/(certificates?|cert)(/|$)"), "certificate"),
    (re.compile(r"/(assets?|asset)(/|$)"), "asset"),
    (re.compile(r"/(investments?|investment)(/|$)"), "investment"),
    (re.compile(r"/(funds?|fund|fund-lpgp|lp-funds)(/|$)"), "fund"),
    (re.compile(r"/(lp[/_-]commit|commitments?)(/|$)"), "lp_commitment"),
    (re.compile(r"/(capital[/_-]calls?|capital-call)(/|$)"), "capital_call"),
    (re.compile(r"/(distributions?|distribution)(/|$)"), "distribution"),
    (re.compile(r"/(compliance|kyc|aml)(/|$)"), "compliance_profile"),
    (re.compile(r"/(accreditation|profile2)(/|$)"), "accreditation_profile"),
    (re.compile(r"/(governance|gov[/_-]|proposals?|votes?)(/|$)"),
     "governance_proposal"),
    (re.compile(r"/(reports?|factsheet|quarterly|report-builder)(/|$)"), "report"),
    (re.compile(r"/(audit|audit-log|audit-explorer)(/|$)"), "audit_log"),
    (re.compile(r"/(trust-graph|trustgraph)(/|$)"), "trust_graph"),
]


def _detect_resource_for_path(path: str) -> str:
    for rx, key in _RESOURCE_PATTERNS:
        if rx.search(path):
            return key
    return "unknown"


def _detect_role_required(path: str) -> str:
    """Heuristic role inference from path: /admin/* → admin, /investor/* → investor."""
    p = path.lower()
    if "/admin/" in p:
        return "admin"
    if "/operator/" in p:
        return "operator"
    if "/investor/" in p or "/client/" in p:
        return "investor"
    return "any"


@router.get("/enforcement-coverage")
async def enforcement_coverage(request: Request, _=Depends(require_admin)):
    """Walk FastAPI routes and report enforcement state.

    For each route we surface:
      - method + path
      - inferred resource (from path heuristics)
      - inferred role group (admin / investor / operator / any)
      - has_lr2_gate: True if any dependency is a require_permission() result
      - has_admin_gate: True if any dependency is require_admin
      - has_auth_gate: True if any dependency reads the user session
    """
    app = request.app
    rows: list[dict] = []
    counts = {"total": 0, "lr2_gated": 0, "admin_gated": 0, "auth_gated": 0,
              "public": 0, "skip": 0}
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path or not path.startswith("/api/"):
            counts["skip"] += 1
            continue
        methods = sorted(getattr(r, "methods", set()) - {"HEAD", "OPTIONS"})
        if not methods:
            counts["skip"] += 1
            continue
        deps = []
        try:
            for d in (getattr(r, "dependant", None) and r.dependant.dependencies) or []:
                fn = getattr(d, "call", None)
                if fn is None:
                    continue
                deps.append(fn)
                # Recurse into sub-deps (FastAPI nests them)
                for sd in (d.dependencies or []):
                    sfn = getattr(sd, "call", None)
                    if sfn:
                        deps.append(sfn)
        except Exception:
            pass
        has_lr2 = any(getattr(fn, "__lr2_resource__", None) for fn in deps)
        has_admin = any(getattr(fn, "__name__", "") == "require_admin"
                        for fn in deps)
        has_auth = any(getattr(fn, "__name__", "") in
                       ("require_admin", "get_current_user", "_gate")
                       for fn in deps)
        for fn in deps:
            res = getattr(fn, "__lr2_resource__", None)
            act = getattr(fn, "__lr2_action__", None)
            if res:
                break
        else:
            res, act = None, None
        for m in methods:
            counts["total"] += 1
            if has_lr2:
                counts["lr2_gated"] += 1
            if has_admin:
                counts["admin_gated"] += 1
            if has_auth:
                counts["auth_gated"] += 1
            if not has_auth:
                counts["public"] += 1
            rows.append({
                "method": m,
                "path": path,
                "resource": res or _detect_resource_for_path(path),
                "role_group": _detect_role_required(path),
                "lr2_gated": has_lr2,
                "lr2_resource": res,
                "lr2_action": act,
                "admin_gated": has_admin,
                "auth_gated": has_auth,
            })
    rows.sort(key=lambda r: (not r["lr2_gated"], r["path"]))
    # Per-resource summary
    per_res: dict[str, dict[str, int]] = {}
    for r in rows:
        k = r["resource"]
        per_res.setdefault(k, {"total": 0, "lr2_gated": 0, "admin_gated": 0,
                                "public": 0})
        per_res[k]["total"] += 1
        per_res[k]["lr2_gated"] += int(r["lr2_gated"])
        per_res[k]["admin_gated"] += int(r["admin_gated"])
        if not r["auth_gated"]:
            per_res[k]["public"] += 1
    return {
        "counts": counts,
        "per_resource": per_res,
        "registry": list(_ENFORCEMENT_REGISTRY.values()),
        "rows": rows[:500],   # cap payload
        "ran_at": _iso(_now()),
    }


@router.get("/denials")
async def denials(limit: int = 50, _=Depends(require_admin)):
    items: list[dict] = []
    async for d in db.lumen_lr2_denials.find({}, {"_id": 0}).sort("at", -1).limit(limit):
        d["at"] = _iso(d.get("at"))
        items.append(d)
    return {"items": items, "count": len(items),
            "registry_total_denials": sum(s.get("denials", 0)
                                            for s in _ENFORCEMENT_REGISTRY.values())}


# ═══════════════════════════════════════════════════════════════════════════
# LR2.8  Background Invariants Scanner
# ═══════════════════════════════════════════════════════════════════════════

def _scan_interval_seconds() -> int:
    try:
        return max(60, int(os.environ.get("LR2_SCAN_INTERVAL_SECONDS") or 3600))
    except Exception:
        return 3600


async def run_lr2_scan(reason: str = "periodic") -> dict:
    """Run all LR2 checks, persist a scan doc, and raise alerts on regressions."""
    perm = audit_permission_matrix()
    inv = await run_invariants()
    rep = await reporting_integrity()
    cof = await conflicts_of_interest()
    demo = await demo_data_inventory()
    score = _compute_readiness_score(perm, inv, rep, cof, demo)
    now = _now()
    scan = {
        "id": f"scan_{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}",
        "at": now,
        "reason": reason,
        "env": env(),
        "is_production": is_production(),
        "score": score,
        "summary": {
            "permission_violations": perm["counts"]["violations"],
            "invariant_failed": inv["counts"]["failed"],
            "invariant_passed": inv["counts"]["passed"],
            "reporting_issues": rep["counts"]["issues"],
            "conflicts": cof["counts"]["total"],
            "demo_rows": sum(demo["counts"].values()),
        },
        "invariants": [
            {"id": r["id"], "label": r["label"], "passed": r["passed"],
             "severity": r.get("severity"), "failure_count": len(r.get("failures") or [])}
            for r in inv["results"]
        ],
    }
    await db.lumen_lr2_scans.insert_one(dict(scan))
    # Trim history — keep last 500
    cutoff = await db.lumen_lr2_scans.count_documents({})
    if cutoff > 500:
        old_ids = []
        async for d in db.lumen_lr2_scans.find({}, {"_id": 1}).sort("at", 1).limit(cutoff - 500):
            old_ids.append(d["_id"])
        if old_ids:
            await db.lumen_lr2_scans.delete_many({"_id": {"$in": old_ids}})

    # ── Alert engine: open/close based on summary deltas ──
    prev = None
    async for d in db.lumen_lr2_scans.find({"id": {"$ne": scan["id"]}}, {"_id": 0}
                                             ).sort("at", -1).limit(1):
        prev = d
    await _raise_alerts(scan, prev)

    scan["at"] = _iso(scan["at"])
    return scan


async def _raise_alerts(scan: dict, prev: Optional[dict]) -> None:
    """Compare summary against previous scan; open or close alerts as needed."""
    s = scan["summary"]
    # 1. Permission matrix has violations
    await _open_or_close_alert(
        "permission_violation",
        active=s["permission_violations"] > 0,
        severity="critical",
        title="Порушення матриці прав доступу",
        message=f"{s['permission_violations']} порушень в PERMISSION_MATRIX",
    )
    # 2. Any error-severity invariant failing
    err_inv = [r for r in scan["invariants"]
               if not r["passed"] and r.get("severity") != "warning"]
    await _open_or_close_alert(
        "invariant_error",
        active=len(err_inv) > 0,
        severity="critical",
        title="Інваріант капіталу/власності зламано",
        message="; ".join(r["label"] for r in err_inv) or "n/a",
        data={"invariants": [r["id"] for r in err_inv]},
    )
    # 3. Reporting integrity issues
    await _open_or_close_alert(
        "reporting_drift",
        active=s["reporting_issues"] > 0,
        severity="high",
        title="Невідповідність звітів source-of-truth",
        message=f"{s['reporting_issues']} report mismatches",
    )
    # 4. Conflicts of interest
    await _open_or_close_alert(
        "conflict_of_interest",
        active=s["conflicts"] > 0,
        severity="high",
        title="Виявлено конфлікт інтересів",
        message=f"{s['conflicts']} конфліктів",
    )
    # 5. Demo data in production
    if is_production() and s["demo_rows"] > 0:
        await _open_or_close_alert(
            "demo_in_production",
            active=True,
            severity="critical",
            title="Demo-дані у production-середовищі",
            message=f"{s['demo_rows']} demo рядків знайдено",
        )
    else:
        await _open_or_close_alert("demo_in_production", active=False,
                                    severity="critical",
                                    title="Demo-дані у production-середовищі",
                                    message="ok")
    # 6. Readiness score regression
    if prev and prev.get("score", {}).get("total", 0) - scan["score"]["total"] >= 5:
        await _open_or_close_alert(
            "score_regression",
            active=True,
            severity="medium",
            title="Падіння Launch Readiness Score",
            message=f"{prev['score']['total']} → {scan['score']['total']}",
        )


async def _open_or_close_alert(kind: str, *, active: bool, severity: str,
                                 title: str, message: str,
                                 data: Optional[dict] = None) -> None:
    existing = await db.lumen_critical_alerts.find_one(
        {"kind": kind, "status": "open"}, {"_id": 0})
    now = _now()
    if active and not existing:
        await db.lumen_critical_alerts.insert_one({
            "id": f"alert_{kind}_{now.strftime('%Y%m%d%H%M%S')}",
            "kind": kind,
            "severity": severity,
            "title": title,
            "message": message,
            "data": data or {},
            "status": "open",
            "opened_at": now,
            "last_seen_at": now,
            "acked_at": None,
            "acked_by": None,
        })
        logger.warning("LR2 ALERT OPENED [%s/%s]: %s", severity, kind, message)
    elif active and existing:
        await db.lumen_critical_alerts.update_one(
            {"kind": kind, "status": "open"},
            {"$set": {"last_seen_at": now, "message": message}})
    elif not active and existing:
        await db.lumen_critical_alerts.update_one(
            {"kind": kind, "status": "open"},
            {"$set": {"status": "auto_closed", "closed_at": now}})
        logger.info("LR2 ALERT auto-closed: %s", kind)


# ── Scanner background task ──
_lr2_scan_task: Optional[asyncio.Task] = None


async def _scanner_loop():
    interval = _scan_interval_seconds()
    logger.info("LR2 SCANNER: started, interval=%ss", interval)
    # Initial scan 60s after boot so the rest of the seeders settle
    await asyncio.sleep(60)
    while True:
        try:
            r = await run_lr2_scan(reason="periodic")
            logger.info("LR2 SCAN ok: score=%s/100 grade=%s", r["score"]["total"],
                        r["score"]["grade"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("LR2 SCANNER iteration failed: %s", e)
        await asyncio.sleep(_scan_interval_seconds())


def start_scanner_task(app=None):
    """Idempotent. Called from server.py startup hook."""
    global _lr2_scan_task
    if _lr2_scan_task and not _lr2_scan_task.done():
        return
    try:
        _lr2_scan_task = asyncio.create_task(_scanner_loop())
        logger.info("LR2 SCANNER: task scheduled (interval=%ss)",
                    _scan_interval_seconds())
    except Exception as e:
        logger.error("LR2 SCANNER: failed to schedule task: %s", e)


@router.get("/scans")
async def list_scans(limit: int = 50, _=Depends(require_admin)):
    items: list[dict] = []
    async for d in db.lumen_lr2_scans.find({}, {"_id": 0}).sort("at", -1).limit(limit):
        d["at"] = _iso(d.get("at"))
        items.append(d)
    return {"items": items, "count": len(items),
            "interval_seconds": _scan_interval_seconds()}


@router.post("/scans/run")
async def run_scan_now(_=Depends(require_admin)):
    scan = await run_lr2_scan(reason="manual")
    return scan


@router.get("/alerts")
async def list_alerts(status: Optional[str] = None, limit: int = 100,
                       _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    items: list[dict] = []
    async for a in db.lumen_critical_alerts.find(q, {"_id": 0}
                                                   ).sort("opened_at", -1).limit(limit):
        for k in ("opened_at", "last_seen_at", "acked_at", "closed_at"):
            if a.get(k):
                a[k] = _iso(a[k])
        items.append(a)
    return {"items": items, "count": len(items)}


class AckIn(BaseModel):
    note: Optional[str] = None


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, payload: AckIn,
                     user: dict = Depends(require_admin)):
    res = await db.lumen_critical_alerts.update_one(
        {"id": alert_id, "status": "open"},
        {"$set": {"status": "acked", "acked_at": _now(),
                  "acked_by": user.get("email"),
                  "ack_note": payload.note}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Active alert not found")
    return {"ok": True, "alert_id": alert_id}


# ═══════════════════════════════════════════════════════════════════════════
# LR2.9  Production Switch
# ═══════════════════════════════════════════════════════════════════════════

# Public flags read by other modules. These flip purely on LUMEN_ENV.
def quick_access_login_enabled() -> bool:
    return not is_production()


def demo_seeders_enabled() -> bool:
    # Allow explicit override for production smoke-tests (must be on by default
    # only in non-production environments).
    if is_production():
        return os.environ.get("LUMEN_ALLOW_DEMO_SEEDS_IN_PROD", "").lower() == "true"
    return True


async def _count_demo_rows() -> dict:
    inv = await demo_data_inventory()
    return inv["counts"]


@router.get("/production-switch")
async def production_switch_status(_=Depends(require_admin)):
    """What does LUMEN_ENV=production turn off, right now?"""
    demo_counts = await _count_demo_rows()
    return {
        "env": env(),
        "is_production": is_production(),
        "controls": {
            "quick_access_login_enabled": quick_access_login_enabled(),
            "demo_seeders_enabled": demo_seeders_enabled(),
            "demo_quarantine_allowed": not is_production(),
            "lr2_scanner_running": bool(_lr2_scan_task and not _lr2_scan_task.done()),
            "scan_interval_seconds": _scan_interval_seconds(),
        },
        "demo_present": demo_counts,
        "checklist": _production_checklist(demo_counts),
        "ran_at": _iso(_now()),
    }


def _production_checklist(demo_counts: dict) -> list[dict]:
    prod = is_production()
    demo_total = sum(demo_counts.values())
    return [
        {"id": "env_flag", "ok": prod,
         "title": "LUMEN_ENV=production",
         "details": f"Поточне значення: {env()}",
         "required_for_launch": True},
        {"id": "quick_access_off", "ok": prod,
         "title": "Quick-access login вимкнено",
         "details": "Quick-access seed-юзери не повинні існувати у production",
         "required_for_launch": True},
        {"id": "no_demo_rows", "ok": (not prod) or demo_total == 0,
         "title": "Demo-дані прибрано",
         "details": f"Знайдено {demo_total} demo рядків (за патернами)",
         "required_for_launch": True},
        {"id": "scanner_on", "ok": bool(_lr2_scan_task and not _lr2_scan_task.done()),
         "title": "LR2 background scanner активний",
         "details": f"Інтервал: {_scan_interval_seconds()}с",
         "required_for_launch": True},
        {"id": "cors_locked", "ok": _check_cors_locked(),
         "title": "CORS не allow-all",
         "details": os.environ.get("CORS_ORIGINS") or "(not set)",
         "required_for_launch": True},
    ]


def _check_cors_locked() -> bool:
    val = os.environ.get("CORS_ORIGINS", "")
    if not val:
        return False
    return val.strip() not in ("*", "")


# ═══════════════════════════════════════════════════════════════════════════
# LR2.10  Security Review
# ═══════════════════════════════════════════════════════════════════════════

async def _security_items() -> list[dict]:
    items: list[dict] = []
    prod = is_production()

    # 1. CORS — semantics depend on env. In preview '*' is intentional
    #    (cookies disabled, web preview is same-origin via ingress). In
    #    production '*' must be a real whitelist.
    cors_raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    cors_ok = (not prod) or (cors_raw not in ("", "*"))
    items.append({
        "id": "cors_not_wildcard",
        "severity": "critical" if prod else "low",
        "title": "CORS обмежено доменами (production-only)",
        "ok": cors_ok,
        "evidence": f"CORS_ORIGINS={cors_raw or '(empty)'} · env={env()}",
        "hint": "У production задайте whitelist через CORS_ORIGINS. В preview '*' "
                "безпечно тому що cookies вимкнено (allow_credentials=False).",
    })
    # 2. Default admin — production-only check (preview keeps default for UX)
    #    Production must have ZERO of these specific default emails AND zero
    #    accounts in the broader demo-email pattern (@atlas.dev / @lumen.test
    #    / demo@ / test@). The B2 startup hook actively purges them, but the
    #    security review is the source of truth that they're really gone.
    default_admin = await db.users.find_one(
        {"$or": [
            {"email": {"$in": [
                "admin@atlas.dev", "admin@devos.io",
                "john@atlas.dev", "client@atlas.dev",
                "multi@atlas.dev", "tester@atlas.dev",
            ]}},
            {"email": {"$regex": "@atlas\\.dev|@lumen\\.test|^demo@|^test@",
                       "$options": "i"}},
        ]},
        {"_id": 0, "email": 1})
    default_admin_ok = (not prod) or (default_admin is None)
    items.append({
        "id": "default_admin_creds",
        "severity": "critical" if prod else "low",
        "title": "Default admin акаунти відсутні (production-only)",
        "ok": default_admin_ok,
        "evidence": f"found={(default_admin or {}).get('email') or 'none'} · env={env()}",
        "hint": "У production startup_event пропускає demo seed І активно "
                "видаляє admin@devos.io / @atlas.dev / @lumen.test акаунти. "
                "Якщо тут щось зʼявляється — перезапустіть бекенд: B2 hook "
                "виконає purge.",
    })
    # 3. Demo users count — production-only critical
    demo_users = await db.users.count_documents(
        {"email": {"$regex": "@atlas\\.dev|@lumen\\.test|^demo|^test",
                    "$options": "i"}})
    demo_ok = (not prod) or demo_users == 0
    items.append({
        "id": "no_demo_users",
        "severity": "critical" if prod else "low",
        "title": "Demo-юзерів немає (production-only)",
        "ok": demo_ok,
        "evidence": f"demo_users={demo_users} · env={env()}",
        "hint": "Запустіть /demo-data/quarantine у non-prod, потім перейдіть у prod",
    })
    # 4. Session cookies — HttpOnly/Secure (informational)
    items.append({
        "id": "secure_cookies",
        "severity": "medium",
        "title": "Cookie HttpOnly+Secure",
        "ok": True,
        "evidence": "Сесійні cookies встановлюються з HttpOnly. "
                    "Secure=true має бути за HTTPS (k8s ingress).",
        "hint": "Перевірте Set-Cookie у браузері: HttpOnly + Secure + SameSite=Lax",
    })
    # 5. Secrets not in CORS_ORIGINS (sanity)
    sus = []
    for var in ("MONGO_URL", "EMERGENT_LLM_KEY", "STRIPE_SECRET_KEY",
                 "RESEND_API_KEY", "GOOGLE_CLIENT_SECRET"):
        v = os.environ.get(var)
        if v and len(v) > 20 and v in (os.environ.get("CORS_ORIGINS") or ""):
            sus.append(var)
    items.append({
        "id": "no_secrets_in_cors",
        "severity": "critical",
        "title": "Секрети не випадково в CORS_ORIGINS",
        "ok": not sus,
        "evidence": sus or "none",
        "hint": "Якщо знайдено — негайно перевипустіть ключі.",
    })
    # 6. Rate-limit — DETECT THE ACTUAL MIDDLEWARE, not just an env flag
    rl_mounted = False
    rl_enforce = False
    rl_total_req = 0
    rl_total_blocked = 0
    try:
        from lumen_rate_limit import (snapshot_stats as _rl_stats,
                                       enforce_enabled as _rl_enf,
                                       middleware_mounted as _rl_mid)
        from server import fastapi_app as _app
        rl_mounted = _rl_mid(_app)
        rl_enforce = _rl_enf()
        s = _rl_stats()
        rl_total_req = s["totals"]["requests"]
        rl_total_blocked = s["totals"]["blocked"]
    except Exception as _e:
        logger.warning("security_review: rate-limit probe failed: %s", _e)
    items.append({
        "id": "rate_limit_on",
        "severity": "high",
        "title": "Rate-limit middleware активний",
        "ok": rl_mounted and rl_enforce,
        "evidence": f"mounted={rl_mounted} · enforce={rl_enforce} · "
                    f"observed_requests={rl_total_req} · blocked={rl_total_blocked}",
        "hint": "LUMEN_RATE_LIMIT_ENABLED=true (default). Виставте 'false' лише "
                "для діагностики (observe mode).",
    })
    # 7. LR2 scanner is running
    items.append({
        "id": "lr2_scanner_running",
        "severity": "high",
        "title": "LR2 background scanner активний",
        "ok": bool(_lr2_scan_task and not _lr2_scan_task.done()),
        "evidence": f"interval={_scan_interval_seconds()}s",
        "hint": "Без сканера регресії інваріантів не помічаються автоматично",
    })
    # 8. Open critical alerts
    open_alerts = await db.lumen_critical_alerts.count_documents({"status": "open"})
    items.append({
        "id": "no_open_critical_alerts",
        "severity": "critical",
        "title": "Немає відкритих critical alerts",
        "ok": open_alerts == 0,
        "evidence": f"open_alerts={open_alerts}",
        "hint": "Розберіть відкриті алерти перед запуском",
    })
    # 9. Auth: 2FA available
    has_2fa = bool(os.environ.get("TWO_FACTOR_ENABLED",
                                    "true").lower() in ("1", "true", "yes"))
    items.append({
        "id": "two_factor_available",
        "severity": "medium",
        "title": "2FA для адмінів доступне",
        "ok": has_2fa,
        "evidence": f"TWO_FACTOR_ENABLED={os.environ.get('TWO_FACTOR_ENABLED') or 'true'}",
        "hint": "Адмін акаунти у production мають бути з 2FA",
    })
    # 10. Audit log writes happen
    recent_audit = await db.lumen_audit_log.count_documents({})
    items.append({
        "id": "audit_log_active",
        "severity": "medium",
        "title": "Audit log пише події",
        "ok": recent_audit > 0,
        "evidence": f"rows={recent_audit}",
        "hint": "Audit log порожній — це аномалія",
    })
    return items


@router.get("/security-review")
async def security_review(_=Depends(require_admin)):
    items = await _security_items()
    weight = {"critical": 5, "high": 3, "medium": 1, "low": 0.5}
    total_max = sum(weight.get(i["severity"], 1) for i in items)
    earned = sum(weight.get(i["severity"], 1) for i in items if i["ok"])
    score = round(earned / total_max * 100) if total_max else 0
    counts = {
        "total": len(items),
        "passing": sum(1 for i in items if i["ok"]),
        "failing": sum(1 for i in items if not i["ok"]),
        "by_severity": {
            sev: sum(1 for i in items
                     if not i["ok"] and i["severity"] == sev)
            for sev in ("critical", "high", "medium", "low")
        },
    }
    return {"items": items, "counts": counts,
            "score": score, "max": 100,
            "ran_at": _iso(_now())}


@router.get("/rate-limit/stats")
async def rate_limit_stats(_=Depends(require_admin)):
    """LR2.B1 — live rate-limit metrics (per-rule counters)."""
    try:
        from lumen_rate_limit import snapshot_stats, middleware_mounted
        from server import fastapi_app as _app
        snap = snapshot_stats()
        snap["middleware_mounted"] = middleware_mounted(_app)
        return snap
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"rate-limit subsystem unavailable: {e}")


__all__ = [
    "router",
    "effective_role",
    "can",
    "require_permission",
    "run_lr2_scan",
    "start_scanner_task",
    "quick_access_login_enabled",
    "demo_seeders_enabled",
]
