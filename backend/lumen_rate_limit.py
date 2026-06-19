"""
LUMEN — Rate Limiting Middleware (B1 production hardening).

Per-IP / per-path-prefix sliding-window rate limit.

* Always counts requests (metrics)
* By default enforces (returns 429 on exceedance)
* Honours LUMEN_RATE_LIMIT_ENABLED env: "observe" disables the block but
  keeps metrics — useful for safe rollout/diagnostics
* Exposes snapshot_stats() for the LR2 Security console
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from threading import Lock
from typing import Deque, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("lumen.ratelimit")

# (path_prefix, per_minute_limit, rule_id). First match wins so order matters.
#
# ── B1 (LR2.10 Security Hardening) — narrow, dedicated buckets for the
#    *individual* auth & high-value write surfaces. These MUST appear BEFORE
#    the coarse "/api/auth/" rule so the matcher picks the strictest cap.
RULES: list[tuple[str, int, str]] = [
    # ── B1 NARROW AUTH BUCKETS ────────────────────────────────────────────
    # Brute-force protection on login itself (per-IP).
    ("/api/auth/login", 10, "auth_login"),
    ("/api/mobile/auth/login", 10, "mobile_auth_login"),
    # Registration abuse (account farming, signup spam).
    ("/api/auth/register", 5, "auth_register"),
    ("/api/mobile/auth/register", 5, "mobile_auth_register"),
    # Password reset (email enumeration + token brute force).
    ("/api/auth/password-reset/request", 5, "auth_password_reset_request"),
    ("/api/auth/password-reset/verify", 5, "auth_password_reset_verify"),
    # 2FA gates (token brute force).
    ("/api/auth/2fa/verify", 10, "auth_2fa_verify"),
    ("/api/auth/2fa/challenge", 10, "auth_2fa_challenge"),
    # OAuth callbacks — tighter than coarse /auth/ rule
    ("/api/auth/google", 20, "auth_google"),

    # Outflow / withdrawal endpoints — extra cautious
    ("/api/investor/withdrawals", 20, "investor_withdrawals"),
    ("/api/admin/withdrawals", 60, "admin_withdrawals"),
    ("/api/withdrawals", 30, "withdrawals"),

    # Coarse auth surface (catches everything else under /api/auth/*)
    ("/api/auth/", 30, "auth"),

    # KYC
    ("/api/investor/kyc", 60, "investor_kyc"),
    ("/api/admin/kyc", 60, "admin_kyc"),
    ("/api/kyc/", 60, "kyc"),
    ("/api/lumen/kyc", 60, "lumen_kyc"),
    ("/api/lumen/compliance", 60, "lumen_compliance"),
    ("/api/lumen/documents", 60, "lumen_documents"),

    # Contracts
    ("/api/contracts/", 60, "contracts"),
    ("/api/investor/contracts", 60, "investor_contracts"),
    ("/api/admin/contracts", 60, "admin_contracts"),

    # Payments
    ("/api/payment-proofs/", 30, "payment_proofs"),
    ("/api/investor/payments", 30, "investor_payments"),
    ("/api/admin/payments", 60, "admin_payments"),
    ("/api/payments/", 30, "payments"),

    # ── B1 EXTRA: money-moving + governance + investment intent ─────────────
    # NOTE: order matters — narrower MUST be listed BEFORE the coarse one.
    ("/api/lumen/orders/place", 10, "lumen_order_place"),       # B1 narrow
    ("/api/lumen/orders/cancel", 30, "lumen_order_cancel"),     # B1 narrow
    ("/api/lumen/investments/intent", 15, "lumen_invest_intent"),  # B1 narrow
    ("/api/lumen/governance/vote", 20, "lumen_governance_vote"),    # B1 narrow
    ("/api/lumen/governance/proposals", 20, "lumen_governance_proposals"),  # B1 narrow
    ("/api/lumen/votes/cast", 20, "lumen_votes_cast"),               # B1 narrow
    # KYC document upload — tighter than coarse /kyc/
    ("/api/lumen/kyc/upload", 20, "lumen_kyc_upload"),
    ("/api/investor/kyc/upload", 20, "investor_kyc_upload"),
    ("/api/lumen/compliance/upload", 20, "lumen_compliance_upload"),

    # ── B1 Phase H1: institutional banking rails (SEPA/SWIFT) ──
    # Submitting a real bank transfer is high-value, low-frequency.
    ("/api/lumen/institutional/rails/sepa", 10, "rails_sepa"),
    ("/api/lumen/institutional/rails/swift", 10, "rails_swift"),
    ("/api/admin/lumen/institutional/rails", 60, "rails_admin"),

    # Coarse buckets (catch-alls for the rest of the surface)
    ("/api/lumen/invest", 30, "lumen_invest"),
    ("/api/lumen/investments", 30, "lumen_investments"),
    ("/api/lumen/orders", 30, "lumen_orders"),
    ("/api/lumen/marketplace", 60, "lumen_marketplace"),
    ("/api/lumen/governance", 60, "lumen_governance"),
    ("/api/lumen/proposals", 60, "lumen_proposals"),
    ("/api/lumen/votes", 60, "lumen_votes"),
    ("/api/lumen/certificates", 60, "lumen_certificates"),
    ("/api/lumen/funds", 60, "lumen_funds"),

    # Global per-IP fallback for everything else on /api/*
    ("/api/", 600, "global_api"),
]

WINDOW_SECONDS = 60

# (ip, rule_id) -> deque of timestamps
_BUCKETS: dict[tuple[str, str], Deque[float]] = {}

# Per-rule metrics: id -> {requests, blocked, observed_blocks, last_triggered_at, unique_clients}
_METRICS: dict[str, dict] = {}
_METRICS_LOCK = Lock()


def enforce_enabled() -> bool:
    """If LUMEN_RATE_LIMIT_ENABLED is explicitly set to a falsy value we go
    into 'observe' mode (count, don't block). Default = enforce. This is
    inverted from typical feature-flags because the middleware is *already*
    mounted and we want safe defaults."""
    v = (os.environ.get("LUMEN_RATE_LIMIT_ENABLED") or "true").lower()
    return v in ("1", "true", "yes", "on")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real
    return request.client.host if request.client else "unknown"


def _match_rule(path: str) -> Optional[tuple[str, int, str]]:
    for prefix, limit, rid in RULES:
        if path.startswith(prefix):
            return prefix, limit, rid
    return None


def _bump_metric(rid: str, *, prefix: str, limit: int, blocked: bool,
                 observed_only: bool, client: str) -> None:
    with _METRICS_LOCK:
        m = _METRICS.setdefault(rid, {
            "id": rid, "prefix": prefix, "limit": limit, "window": WINDOW_SECONDS,
            "requests": 0, "blocked": 0, "observed_blocks": 0,
            "last_triggered_at": None, "unique_clients": 0, "_clients": set(),
        })
        m["requests"] += 1
        m["_clients"].add(client)
        m["unique_clients"] = len(m["_clients"])
        if blocked:
            if observed_only:
                m["observed_blocks"] += 1
            else:
                m["blocked"] += 1
            m["last_triggered_at"] = time.time()


class LumenRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        rule = _match_rule(path)
        if rule is None:
            return await call_next(request)
        prefix, limit, rid = rule
        ip = _client_ip(request)
        key = (ip, rid)
        now = time.monotonic()
        bucket = _BUCKETS.setdefault(key, deque())
        while bucket and (now - bucket[0]) > WINDOW_SECONDS:
            bucket.popleft()

        enforce = enforce_enabled()
        if len(bucket) >= limit:
            retry = max(1, int(WINDOW_SECONDS - (now - bucket[0])))
            _bump_metric(rid, prefix=prefix, limit=limit, blocked=True,
                         observed_only=not enforce, client=ip)
            if enforce:
                logger.warning("RATE-LIMIT 429: ip=%s rule=%s count=%s/%s retry=%ss",
                               ip, rid, len(bucket), limit, retry)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Перевищено ліміт запитів. Зачекайте і спробуйте знову.",
                        "code": "rate_limit_exceeded",
                        "rule": rid,
                        "limit": limit,
                        "window_seconds": WINDOW_SECONDS,
                        "retry_after_seconds": retry,
                    },
                    headers={"Retry-After": str(retry),
                             "X-RateLimit-Rule": rid,
                             "X-RateLimit-Limit": str(limit),
                             "X-RateLimit-Remaining": "0",
                             "X-RateLimit-Reset": str(retry),
                             "X-RateLimit-Mode": "enforce"})
            # observe mode — pass through, just log
            logger.info("RATE-LIMIT (observe) would-block: ip=%s rule=%s %s/%s",
                        ip, rid, len(bucket), limit)
        else:
            _bump_metric(rid, prefix=prefix, limit=limit, blocked=False,
                         observed_only=not enforce, client=ip)

        bucket.append(now)
        try:
            response = await call_next(request)
            response.headers["X-RateLimit-Rule"] = rid
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(bucket)))
            response.headers["X-RateLimit-Reset"] = str(WINDOW_SECONDS)
            response.headers["X-RateLimit-Mode"] = "enforce" if enforce else "observe"
            return response
        except Exception:
            raise


def snapshot_stats() -> dict:
    """Public, JSON-safe snapshot for the LR2 Security console."""
    with _METRICS_LOCK:
        rows = []
        for rid, m in _METRICS.items():
            d = {k: v for k, v in m.items() if not k.startswith("_")}
            if m.get("last_triggered_at"):
                from datetime import datetime, timezone
                d["last_triggered_at"] = datetime.fromtimestamp(
                    m["last_triggered_at"], timezone.utc).isoformat()
            rows.append(d)
        rows.sort(key=lambda x: x["requests"], reverse=True)
    return {
        "enforce_enabled": enforce_enabled(),
        "window_seconds": WINDOW_SECONDS,
        "rules_count": len(RULES),
        "active_rules": len(rows),
        "totals": {
            "requests": sum(r["requests"] for r in rows),
            "blocked": sum(r["blocked"] for r in rows),
            "observed_blocks": sum(r["observed_blocks"] for r in rows),
            "unique_clients": sum(r["unique_clients"] for r in rows),
        },
        "metrics": rows,
        "rules": [{"id": rid, "prefix": p, "limit": l, "window": WINDOW_SECONDS}
                  for (p, l, rid) in RULES],
    }


def middleware_mounted(app) -> bool:
    """Best-effort detection that the middleware is in the stack."""
    try:
        for mw in getattr(app, "user_middleware", []):
            cls = getattr(mw, "cls", None)
            if cls and cls.__name__ == "LumenRateLimitMiddleware":
                return True
    except Exception:
        pass
    return False


__all__ = ["LumenRateLimitMiddleware", "RULES", "WINDOW_SECONDS",
           "snapshot_stats", "enforce_enabled", "middleware_mounted"]
