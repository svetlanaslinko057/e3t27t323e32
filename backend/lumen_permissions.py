"""
LUMEN Sprint 10 — Permissions Matrix + Endpoint Security Self-Test (Block 1+2)

Declares the role -> action -> endpoint mapping the platform claims to enforce.
Provides a runtime self-test that walks the live FastAPI routes and verifies
the declared matrix is actually applied (i.e. catches broken access control
regressions like a route losing its `require_admin` dependency).

Why a matrix instead of decorators?
-----------------------------------
A decorator says "this endpoint requires admin" — but it does not say *what
finance, compliance, and asset-managers should be able to do*. Lumen runs in a
mixed-role environment (Investor / Asset Manager / Compliance / Finance /
Admin). The matrix captures business rules; the live-routes scan verifies
code adheres to them.

Roles (post-Sprint 10)
----------------------
  investor       : end user investing money in assets
  asset_manager  : edits assets, manages SPVs (NOT money)
  compliance     : KYC moderation, document review (NOT money)
  finance        : payments / payouts / withdrawals (NOT KYC, NOT assets)
  admin          : everything (super-user, audited)
  system         : internal jobs (workers, schedulers)

Note: under LUMEN_ONLY the live user model uses 'admin' and 'client'/'investor'.
Until HR introduces separate user accounts for compliance/finance/asset_manager,
admin acts as their proxy. The matrix still lists the *intent* per role so the
future role-split is a config change — not a refactor.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from lumen_api import db, require_admin, _now

logger = logging.getLogger("lumen.permissions")

# ----------------------------------------------------------------------------
# Permissions Matrix (single source of truth)
# ----------------------------------------------------------------------------

ROLES = ["investor", "asset_manager", "compliance", "finance", "admin", "system"]

# action -> list of roles allowed
MATRIX: dict[str, list[str]] = {
    # ---- self-service (investor) ----
    "investor.view_own_profile":       ["investor", "compliance", "admin"],
    "investor.edit_own_profile":       ["investor"],
    "investor.upload_kyc_doc":         ["investor"],
    "investor.delete_own_kyc_doc":     ["investor"],
    "investor.download_own_doc":       ["investor", "compliance", "admin"],
    "investor.submit_kyc":             ["investor"],
    "investor.sign_contract":          ["investor"],
    "investor.view_own_contract":      ["investor", "compliance", "admin"],
    "investor.download_own_contract":  ["investor", "compliance", "admin"],
    "investor.upload_payment_proof":   ["investor"],
    "investor.delete_own_proof":       ["investor"],
    "investor.view_own_wallet":        ["investor"],
    "investor.request_withdrawal":     ["investor"],
    "investor.cancel_own_withdrawal":  ["investor"],
    "investor.view_own_statements":    ["investor", "admin"],
    "investor.download_own_statement": ["investor", "admin"],

    # ---- compliance ----
    "kyc.view_queue":          ["compliance", "admin"],
    "kyc.view_investor_card":  ["compliance", "admin"],
    "kyc.approve":             ["compliance", "admin"],
    "kyc.reject":              ["compliance", "admin"],
    "kyc.download_any_doc":    ["compliance", "admin"],

    # ---- asset manager ----
    "asset.create":            ["asset_manager", "admin"],
    "asset.update":            ["asset_manager", "admin"],
    "asset.delete":            ["admin"],
    "asset.publish":           ["asset_manager", "admin"],
    "spv.edit":                ["asset_manager", "admin"],
    "contract_template.edit":  ["asset_manager", "admin"],

    # ---- finance ----
    "payment.confirm":         ["finance", "admin"],
    "payment.reject":          ["finance", "admin"],
    "payment.list":            ["finance", "admin"],
    "funding_account.crud":    ["finance", "admin"],
    "payout_plan.crud":        ["finance", "admin"],
    "payout_batch.approve":    ["finance", "admin"],
    "payout_batch.credit":     ["finance", "admin"],
    "withdrawal.review":       ["finance", "admin"],
    "withdrawal.approve":      ["finance", "admin"],
    "withdrawal.mark_paid":    ["finance", "admin"],
    "withdrawal.reject":       ["finance", "admin"],
    "ledger.view":             ["finance", "admin"],

    # ---- analytics / overview ----
    "admin.overview":          ["finance", "compliance", "asset_manager", "admin"],
    "fund_intelligence.view":  ["finance", "admin"],

    # ---- system / hardening (Sprint 10) ----
    "audit.view":              ["compliance", "admin"],
    "consistency.run":         ["admin"],
    "system_health.view":      ["admin"],
    "backup.trigger":          ["admin"],
}

# Expected access guard per endpoint path (verifies the live routes match
# what the matrix promises). Pattern → expected guard kind.
#   'admin'     — endpoint must require admin role
#   'auth'      — endpoint must require any authenticated user
#   'public'    — endpoint may be anonymous
EXPECTED_GUARDS: list[tuple[str, str]] = [
    # admin namespaces — must be admin-locked
    ("^/api/admin/", "admin"),
    # investor namespaces — auth-only
    ("^/api/investor/", "auth"),
    # money-touching endpoints under non-admin namespaces are still auth-only
    ("^/api/kyc/documents/", "auth"),
    ("^/api/contracts/[^/]+/pdf", "auth"),
    ("^/api/payment-proofs/", "auth"),
    # public catalog
    ("^/api/assets($|/[^/]+$)", "public"),
    ("^/api/economics/", "public"),
    ("^/api/funding-accounts/public", "public"),
    ("^/api/healthz", "public"),
    ("^/api/readyz", "public"),
]


# ----------------------------------------------------------------------------
# Live route inspection
# ----------------------------------------------------------------------------

def _route_guards(route) -> set[str]:
    """Resolve the set of FastAPI dependency callables on a route to coarse
    guard names ('admin', 'auth')."""
    names: set[str] = set()
    try:
        deps = getattr(route, "dependant", None)
        stack = []
        if deps is not None:
            stack.extend(deps.dependencies or [])
        while stack:
            d = stack.pop()
            call = getattr(d, "call", None)
            n = getattr(call, "__name__", "")
            if n in {"require_admin", "require_role_admin"}:
                names.add("admin")
            elif n in {"get_current_user", "get_current_user_or_none"}:
                names.add("auth")
            stack.extend(getattr(d, "dependencies", []) or [])
    except Exception:
        logger.exception("route guard inspection failed for %s", route)
    return names


def _expected_guard_for(path: str) -> str | None:
    import re
    for pattern, kind in EXPECTED_GUARDS:
        if re.search(pattern, path):
            return kind
    return None


async def run_endpoint_security_audit(request: Request) -> dict:
    """Scan the live FastAPI app and report mismatches vs. EXPECTED_GUARDS.

    SCOPE: Sprint 10 hardening covers ONLY the LUMEN product surface
    (routes tagged with a `lumen-*` tag). Legacy EVA-X routes have their
    own guard patterns and are out of scope for this matrix.
    """
    from fastapi.routing import APIRoute
    app = request.app
    findings_broken: list[dict] = []
    findings_unknown: list[dict] = []
    checked = 0
    skipped_non_lumen = 0
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        path = r.path
        if not path.startswith("/api/"):
            continue
        tags = list(getattr(r, "tags", []) or [])
        is_lumen = any(str(t).startswith("lumen") for t in tags)
        if not is_lumen:
            skipped_non_lumen += 1
            continue
        expected = _expected_guard_for(path)
        if expected is None:
            continue
        checked += 1
        guards = _route_guards(r)
        ok = False
        if expected == "admin":
            ok = "admin" in guards
        elif expected == "auth":
            ok = "auth" in guards or "admin" in guards
        elif expected == "public":
            ok = True  # no requirement
        if not ok:
            findings_broken.append({
                "path": path,
                "methods": sorted(r.methods or []),
                "tags": tags,
                "expected": expected,
                "actual_guards": sorted(guards) or ["NONE"],
            })
    return {
        "scope": "lumen",
        "checked": checked,
        "broken": len(findings_broken),
        "sample": findings_broken[:30],
        "unknown": findings_unknown,
        "skipped_non_lumen": skipped_non_lumen,
        "checked_at": _now().isoformat(),
    }


# ----------------------------------------------------------------------------
# Permission helper (re-exported for new code)
# ----------------------------------------------------------------------------

def can(role: str, action: str) -> bool:
    return role in MATRIX.get(action, [])


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-permissions"])


@router.get("/admin/permissions/matrix")
async def admin_permissions_matrix(_=Depends(require_admin)):
    out: list[dict] = []
    for action, roles in MATRIX.items():
        out.append({"action": action, "roles": roles})
    return {"roles": ROLES, "matrix": out, "total_actions": len(MATRIX)}


@router.get("/admin/permissions/audit")
async def admin_permissions_audit(request: Request, _=Depends(require_admin)):
    return await run_endpoint_security_audit(request)


__all__ = ["router", "MATRIX", "ROLES", "EXPECTED_GUARDS",
           "can", "run_endpoint_security_audit"]
