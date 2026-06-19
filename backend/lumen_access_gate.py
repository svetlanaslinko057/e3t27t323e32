"""
LUMEN IR0.1 — Default-Deny Access Gate
========================================

A single HTTP edge that classifies EVERY incoming request into one of three
trust tiers, BEFORE the per-route guard (require_admin / require_user /
lr2_perm) does its finer authorization on top.

Three tiers
-----------
    public    → anyone (storefront, marketplace, auth flows, webhooks, health)
    investor  → valid client session OR staff
    staff     → valid staff token only — **DEFAULT**

Default-deny posture
--------------------
Anything **not explicitly allowlisted** below is staff-only. A newly added
route with no guard is therefore inaccessible to anonymous callers — which
directly closes the "developer forgot to add @require_admin" class of bugs.

Two operating modes (controlled via ``LUMEN_ACCESS_GATE_MODE`` env)
-------------------------------------------------------------------
    ``strict``     — deny violations with HTTP 401/403 (production)
    ``permissive`` — log violations to ``lumen_security_violations`` but
                     LET REQUESTS THROUGH (Controlled Beta / staging)
    ``off``        — middleware short-circuits; the gate is invisible

Every violation (denied OR logged-only) writes one row to the dedicated
collection ``lumen_security_violations`` — separate from ``lumen_audit_log``
because security events significantly outnumber business audits.

Public surface
--------------
- ``LumenAccessGateMiddleware``      ASGI middleware (mount in server.py)
- ``classify_path(method, path)``    pure classifier → ``"public" | "investor" | "staff"``
- ``is_query_token_allowed(path)``   ?token=… is permitted only here
- ``get_violation_stats()``          read-only view for /api/admin/security/violations
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Pattern

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("lumen.access_gate")

# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------
GATE_MODE_STRICT = "strict"
GATE_MODE_PERMISSIVE = "permissive"
GATE_MODE_OFF = "off"

_VALID_MODES = {GATE_MODE_STRICT, GATE_MODE_PERMISSIVE, GATE_MODE_OFF}


def resolve_mode() -> str:
    raw = (os.environ.get("LUMEN_ACCESS_GATE_MODE") or "permissive").strip().lower()
    return raw if raw in _VALID_MODES else GATE_MODE_PERMISSIVE


# ---------------------------------------------------------------------------
# Allowlists — derived from the real route inventory (grep'd 2026-06-15)
# ---------------------------------------------------------------------------
def _compile(patterns: List[str]) -> List[Pattern]:
    return [re.compile(p) for p in patterns]


# ── PUBLIC: anyone (no authentication required) ─────────────────────────────
# Storefront, marketplace, fund-marketing pages, health, auth ENTRY points,
# webhooks (the webhook's own signature replaces session auth).
_PUBLIC: List[Pattern] = _compile([
    # root + crawler / static
    r"^/$",
    r"^/favicon\.ico$",
    r"^/robots\.txt$",
    r"^/sitemap(\.xml)?$",
    r"^/api/?$",
    r"^/api/static(/.*)?$",
    r"^/api/uploads/.*$",
    # SEO surface — sitemaps, runtime SEO config, robots, all PUBLIC.
    # (See lumen_seo.py for handlers; admin /api/admin/seo/* stays staff-only.)
    r"^/api/seo/(sitemap\.xml|sitemap-index\.xml|robots\.txt|runtime-config)$",
    # Public contract view-token surface — investor opens / signs / downloads
    # a contract from a one-time signed link WITHOUT logging in.
    # (See lumen_contracts.py — admin-side /api/admin/contracts/{id}/view-link stays staff-only.)
    r"^/api/contracts/view/[A-Za-z0-9_\-]+$",
    r"^/api/contracts/view/[A-Za-z0-9_\-]+/(sign|download)$",
    # health
    r"^/api/healthz$",
    r"^/api/readyz$",
    r"^/api/system/health$",
    r"^/api/system/status$",
    r"^/api/system/info$",
    # auth ENTRY points (must be callable without a token)
    r"^/api/auth/login$",
    r"^/api/auth/register$",
    r"^/api/auth/logout$",
    r"^/api/auth/me$",
    r"^/api/auth/refresh$",
    r"^/api/auth/google(/.*)?$",
    r"^/api/auth/otp/(request|verify)$",
    r"^/api/auth/email-otp/(request|verify)$",
    r"^/api/auth/google-client-id$",
    r"^/api/auth/password-policy$",
    # CSP reporter (no auth — browser sends from any origin)
    r"^/api/security/csp-report$",
    # MARKETPLACE — public storefront of assets / funds / cases
    r"^/api/public(/.*)?$",
    r"^/api/marketplace(/.*)?$",
    r"^/api/assets/public(/.*)?$",
    r"^/api/assets/?$",                # GET list (filtered to published)
    r"^/api/assets/[^/]+/?$",          # GET single asset card
    r"^/api/assets/[^/]+/(summary|preview|stats)$",
    r"^/api/projects/?$",
    r"^/api/projects/[^/]+/?$",
    r"^/api/operators/public(/.*)?$",
    r"^/api/global/(stats|aum|kpis|trust)$",
    r"^/api/economics/public(/.*)?$",
    r"^/api/pricing/public(/.*)?$",
    # Lead-capture (lendpage форма "оставить заявку")
    r"^/api/leads/public$",
    r"^/api/leads/intent$",
    # Cookie / consent endpoints
    r"^/api/consent/.*$",
    # Webhook entry points (signature-verified inside the handler)
    r"^/api/webhook/.*$",
    r"^/api/webhooks/.*$",
    # Bootstrap / config-for-anonymous landing
    r"^/api/bootstrap/public$",
    r"^/api/config/public$",
    r"^/api/runtime/public$",
    # Service-worker / PWA manifest
    r"^/manifest\.json$",
    r"^/asset-manifest\.json$",
    # CORS preflight is handled below (OPTIONS short-circuit)
])

# ── INVESTOR: valid client session OR staff session ─────────────────────────
# Cabinet endpoints. Read-only "me" surfaces + investor operations.
_INVESTOR: List[Pattern] = _compile([
    # current user / profile
    r"^/api/me(/.*)?$",
    r"^/api/account(/.*)?$",
    r"^/api/onboarding(/.*)?$",
    r"^/api/notifications(/.*)?$",
    # investor cabinet
    r"^/api/investor/.*$",
    r"^/api/client/.*$",
    # money in / out — investor side
    r"^/api/funding/.*$",
    r"^/api/funding-accounts(/.*)?$",   # GET own accounts; create requests
    r"^/api/payments/.*$",
    r"^/api/payouts-v2/.*$",
    r"^/api/payment-proofs/.*$",
    r"^/api/withdrawals/.*$",
    # compliance docs the investor uploads/owns
    r"^/api/kyc/(my|status|upload|submit|documents)(/.*)?$",
    # certificates / contracts the investor holds
    r"^/api/certificates/my(/.*)?$",
    r"^/api/contracts/my(/.*)?$",
    # observability — clients post their own client-side errors
    r"^/api/observability/client-error$",
    # validation flows the investor initiates
    r"^/api/validation/.*$",
    # in-app chat (investor↔manager)
    r"^/api/chat/.*$",
    # operator marketplace reads (investor-facing parts)
    r"^/api/operators/?$",
    r"^/api/operators/[^/]+$",
])

# Routes that must use Authorization: Bearer header (no ?token= query allowed).
# Lumen does not currently expose <audio> / <video> tags that need it, so the
# allowlist is intentionally EMPTY — query tokens are universally disabled.
_QUERY_TOKEN_ALLOWED: Optional[Pattern] = None


# ---------------------------------------------------------------------------
# Pure classifier (no I/O, trivially unit-testable)
# ---------------------------------------------------------------------------
TIER_PUBLIC = "public"
TIER_INVESTOR = "investor"
TIER_STAFF = "staff"


def classify_path(method: str, path: str) -> str:
    """Return one of ``"public" | "investor" | "staff"`` for a given route.

    Pure function — call site does NOT need an open request or DB.
    """
    # OPTIONS (CORS preflight) is always public — the browser sends it before
    # attaching credentials.
    if method.upper() == "OPTIONS":
        return TIER_PUBLIC
    # Strip query string and trailing slash (idempotent for routes registered
    # both with and without slash).
    p = (path or "/").split("?", 1)[0]
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/")
    for pat in _PUBLIC:
        if pat.match(p):
            return TIER_PUBLIC
    for pat in _INVESTOR:
        if pat.match(p):
            return TIER_INVESTOR
    return TIER_STAFF


def is_query_token_allowed(path: str) -> bool:
    if _QUERY_TOKEN_ALLOWED is None:
        return False
    return bool(_QUERY_TOKEN_ALLOWED.match(path))


# ---------------------------------------------------------------------------
# Session resolution (low-level, side-effect-free except for the DB read)
# ---------------------------------------------------------------------------
@dataclass
class _Caller:
    has_session: bool
    user_id: Optional[str]
    role: Optional[str]
    email: Optional[str]


async def _resolve_caller(request: Request, db) -> _Caller:
    """Best-effort session resolution — never raises.

    Mirrors ``lumen_api.get_current_user`` but does NOT throw 401: it just
    returns an empty caller when there is no valid session. Authorization
    decisions belong to the gate, not to this helper.
    """
    token = (
        request.cookies.get("session_token")
        or request.cookies.get("auth_session_token")
    )
    if not token:
        # Bearer header fallback (mobile / API clients)
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(None, 1)[1].strip()
    if not token:
        return _Caller(False, None, None, None)
    try:
        sess = (
            await db.user_sessions.find_one({"session_token": token})
            or await db.sessions.find_one({"token": token})
            or await db.auth_sessions.find_one({"token": token})
        )
    except Exception as exc:  # pragma: no cover — DB hiccup; treat as no-session
        logger.debug("access_gate session lookup failed: %s", exc)
        return _Caller(False, None, None, None)
    if not sess:
        return _Caller(False, None, None, None)
    user_id = sess.get("user_id") or sess.get("uid")
    user = None
    if user_id:
        try:
            user = (
                await db.users.find_one({"user_id": user_id}, {"_id": 0})
                or await db.users.find_one({"id": user_id}, {"_id": 0})
            )
        except Exception:
            user = None
    if not user:
        return _Caller(True, user_id, None, None)
    return _Caller(
        True,
        user.get("user_id") or user.get("id"),
        (user.get("role") or "").lower() or None,
        user.get("email"),
    )


def _is_staff_role(role: Optional[str]) -> bool:
    return (role or "") in {"admin", "operator", "manager", "team_lead", "owner", "master_admin"}


def _is_investor_role(role: Optional[str]) -> bool:
    return (role or "") in {"client", "investor", "lp", "gp"}


# ---------------------------------------------------------------------------
# Violation sink (separate collection — owner directive)
# ---------------------------------------------------------------------------
async def _record_violation(
    db,
    *,
    path: str,
    method: str,
    tier: str,
    reason: str,
    mode: str,
    blocked: bool,
    actor_id: Optional[str],
    actor_role: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    """Insert one row into ``lumen_security_violations``. Never raises."""
    try:
        await db.lumen_security_violations.insert_one({
            "at": datetime.now(timezone.utc),
            "category": "access_denied",
            "path": path,
            "method": method,
            "tier_required": tier,
            "reason": reason,
            "gate_mode": mode,
            "blocked": blocked,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "ip": ip,
            "user_agent": (user_agent or "")[:240],
        })
    except Exception as exc:  # pragma: no cover
        logger.debug("violation insert failed: %s", exc)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# In-process violation counters (cheap snapshot for admin dashboard)
# ---------------------------------------------------------------------------
_VIOLATION_STATS: Dict[str, int] = {
    "total": 0,
    "blocked": 0,
    "permissive_passes": 0,
}
_VIOLATION_RECENT: List[Dict[str, Any]] = []


def _bump_stats(blocked: bool, sample: Dict[str, Any]) -> None:
    _VIOLATION_STATS["total"] += 1
    if blocked:
        _VIOLATION_STATS["blocked"] += 1
    else:
        _VIOLATION_STATS["permissive_passes"] += 1
    # ring buffer
    _VIOLATION_RECENT.append(sample)
    if len(_VIOLATION_RECENT) > 100:
        _VIOLATION_RECENT.pop(0)


def get_violation_stats() -> Dict[str, Any]:
    return {
        "mode": resolve_mode(),
        "stats": dict(_VIOLATION_STATS),
        "recent": list(_VIOLATION_RECENT[-50:]),
    }


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class LumenAccessGateMiddleware(BaseHTTPMiddleware):
    """Default-deny edge for the entire FastAPI surface.

    Mounted in ``server.py`` after CORS, BEFORE the per-route guards run.

    Behaviour matrix (gate_mode × verdict):
      strict + violation     → 401 (no session) / 403 (wrong tier)
      permissive + violation → log to lumen_security_violations, pass through
      off                    → no-op pass through (still records nothing)
    """

    def __init__(self, app: ASGIApp, db_getter) -> None:
        super().__init__(app)
        # Resolver fn returning the live Mongo db handle. We accept a function
        # (not a handle) so the middleware can be wired BEFORE _main_startup
        # has assigned the global db.
        self._db_getter = db_getter

    async def dispatch(self, request: Request, call_next):
        mode = resolve_mode()
        if mode == GATE_MODE_OFF:
            return await call_next(request)

        path = request.url.path or "/"
        method = request.method.upper()
        tier = classify_path(method, path)

        # ── Public — no session check, no DB hit ──
        if tier == TIER_PUBLIC:
            return await call_next(request)

        # ── Query-token guard ──
        if "token=" in (request.url.query or "") and not is_query_token_allowed(path):
            db = self._safe_db()
            sample = {
                "at": datetime.now(timezone.utc).isoformat(),
                "path": path,
                "method": method,
                "tier": tier,
                "reason": "query_token_forbidden",
                "mode": mode,
            }
            _bump_stats(mode == GATE_MODE_STRICT, sample)
            if db is not None:
                await _record_violation(
                    db,
                    path=path, method=method, tier=tier,
                    reason="query_token_forbidden",
                    mode=mode, blocked=(mode == GATE_MODE_STRICT),
                    actor_id=None, actor_role=None,
                    ip=_client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
            if mode == GATE_MODE_STRICT:
                return JSONResponse(
                    {"ok": False, "code": "query_token_forbidden",
                     "message": "Query-string tokens are not allowed."},
                    status_code=400,
                )

        # ── Resolve caller (DB read) ──
        db = self._safe_db()
        if db is None:
            # DB not yet initialised at boot — fail open (no-session) but
            # only for /api/healthz-class which is already public. For
            # everything else, treat as anonymous.
            caller = _Caller(False, None, None, None)
        else:
            caller = await _resolve_caller(request, db)

        # ── Tier check ──
        ok = False
        reason = ""
        if tier == TIER_INVESTOR:
            if caller.has_session and (
                _is_investor_role(caller.role) or _is_staff_role(caller.role)
            ):
                ok = True
            elif caller.has_session:
                reason = "wrong_role"
            else:
                reason = "no_session"
        elif tier == TIER_STAFF:
            if caller.has_session and _is_staff_role(caller.role):
                ok = True
            elif caller.has_session:
                reason = "wrong_role"
            else:
                reason = "no_session"

        if ok:
            # attach caller hint to request state for downstream handlers
            request.state.lumen_caller = caller
            return await call_next(request)

        # ── Violation path ──
        blocked = (mode == GATE_MODE_STRICT)
        sample = {
            "at": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "method": method,
            "tier": tier,
            "reason": reason,
            "actor_id": caller.user_id,
            "actor_role": caller.role,
            "mode": mode,
            "blocked": blocked,
        }
        _bump_stats(blocked, sample)
        if db is not None:
            await _record_violation(
                db,
                path=path, method=method, tier=tier,
                reason=reason or "default_deny",
                mode=mode, blocked=blocked,
                actor_id=caller.user_id, actor_role=caller.role,
                ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )

        if not blocked:
            # permissive — let it pass; per-route guard will still 401/403
            # downstream, but the gate observed the violation already.
            return await call_next(request)

        # strict — block now
        status = 401 if reason == "no_session" else 403
        return JSONResponse(
            {
                "ok": False,
                "code": "access_denied",
                "message": "Доступ заборонено." if reason == "wrong_role"
                           else "Потрібна авторизація.",
                "tier_required": tier,
            },
            status_code=status,
        )

    # ── helpers ──
    def _safe_db(self):
        try:
            return self._db_getter()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Admin-side query API (mounted from server.py)
# ---------------------------------------------------------------------------
def register_access_gate_routes(api_router, db, require_admin_dep) -> None:
    """Mount a small admin surface for inspecting gate state.

    GET /api/admin/security/access-gate/status
        — current mode + in-process counters + last 50 violations
    GET /api/admin/security/violations?limit=200&since=ISO
        — durable history from `lumen_security_violations`
    """
    from fastapi import Depends, Query
    from datetime import datetime as _dt

    @api_router.get("/admin/security/access-gate/status")
    async def access_gate_status(_user: dict = Depends(require_admin_dep)):
        return {"ok": True, **get_violation_stats()}

    @api_router.get("/admin/security/violations")
    async def access_gate_violations(
        limit: int = Query(default=200, ge=1, le=1000),
        since: Optional[str] = None,
        path_prefix: Optional[str] = None,
        actor_id: Optional[str] = None,
        _user: dict = Depends(require_admin_dep),
    ):
        q: Dict[str, Any] = {}
        if since:
            try:
                q["at"] = {"$gte": _dt.fromisoformat(since.replace("Z", "+00:00"))}
            except Exception:
                pass
        if path_prefix:
            q["path"] = {"$regex": f"^{re.escape(path_prefix)}"}
        if actor_id:
            q["actor_id"] = actor_id
        rows: List[Dict[str, Any]] = []
        async for r in db.lumen_security_violations.find(q, {"_id": 0}).sort("at", -1).limit(limit):
            if isinstance(r.get("at"), _dt):
                r["at"] = r["at"].isoformat()
            rows.append(r)
        return {"ok": True, "count": len(rows), "items": rows}


# ---------------------------------------------------------------------------
# Index ensure (called once at startup)
# ---------------------------------------------------------------------------
async def ensure_indexes(db) -> None:
    try:
        await db.lumen_security_violations.create_index([("at", -1)])
        await db.lumen_security_violations.create_index([("path", 1), ("at", -1)])
        await db.lumen_security_violations.create_index([("actor_id", 1), ("at", -1)])
        # TTL — auto-prune after 180 days
        await db.lumen_security_violations.create_index(
            [("at", 1)], expireAfterSeconds=60 * 60 * 24 * 180
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("lumen_security_violations index ensure failed: %s", exc)


__all__ = [
    "LumenAccessGateMiddleware",
    "classify_path",
    "is_query_token_allowed",
    "resolve_mode",
    "get_violation_stats",
    "register_access_gate_routes",
    "ensure_indexes",
    "GATE_MODE_STRICT",
    "GATE_MODE_PERMISSIVE",
    "GATE_MODE_OFF",
    "TIER_PUBLIC",
    "TIER_INVESTOR",
    "TIER_STAFF",
]
