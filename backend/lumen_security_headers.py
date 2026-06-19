"""
LUMEN IR0.5 — Security Headers Middleware + CSP Report-Only
=============================================================

Adds a safe baseline of HTTP security headers to every response, and ships a
**Content-Security-Policy in Report-Only mode** so we can observe violations
before enforcing.

Design decisions
----------------
* A small, audited set of static headers is enforced on EVERY response (HTML
  or JSON or static asset — the headers are universal):
      X-Content-Type-Options:   nosniff
      X-Frame-Options:          SAMEORIGIN
      Referrer-Policy:          strict-origin-when-cross-origin
      X-Permitted-Cross-Domain-Policies: none
      Permissions-Policy:       camera=(), microphone=(), geolocation=(),
                                usb=(), payment=()

* CSP is shipped in **Report-Only** form for HTML responses only — so the
  React app, Stripe / Google sign-in, PDF preview, etc. keep working while
  the policy is being tuned. Violations are POSTed to /api/security/csp-report
  and stored in ``lumen_csp_reports`` (TTL 30 days).

* **HSTS is intentionally NOT set** here — it is enabled only after the
  production cut-over to HTTPS so a misconfigured preview cannot brick the
  domain for a year via the browser HSTS cache.

* Private API responses (any path beyond /api/public/* and /api/marketplace/*)
  also receive ``Cache-Control: no-store`` so authenticated payloads are
  never cached by shared proxies.

Public surface
--------------
* ``LumenSecurityHeadersMiddleware``    — ASGI middleware (mount in server.py)
* ``CSP_REPORT_PATH``                    — "/api/security/csp-report"
* ``register_csp_routes(api_router, db)``— mounts the report sink
* ``ensure_indexes(db)``                 — ensures CSP report indexes/TTL
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("lumen.security_headers")

CSP_REPORT_PATH = "/api/security/csp-report"
CSP_COLLECTION = "lumen_csp_reports"

# Always-on, non-breaking headers.
STATIC_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=(), payment=()",
}

# CSP target policy — shipped Report-Only (HTML only). Origins the Lumen
# storefront and cabinet legitimately use (Google sign-in, Stripe-in-future,
# preview/prod domain) are allowlisted. 'unsafe-inline' is permitted for
# STYLES only — scripts NEVER get unsafe-inline so violations are reported
# exactly enough times to noncify them later.
_CSP_REPORT_ONLY = "; ".join([
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "script-src 'self' https://accounts.google.com https://apis.google.com "
    "https://www.googletagmanager.com",
    "connect-src 'self' https://accounts.google.com https://www.google-analytics.com",
    "frame-src 'self' https://accounts.google.com",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    f"report-uri {CSP_REPORT_PATH}",
])

# Private endpoints — anything NOT below these prefixes gets `Cache-Control: no-store`
_CACHEABLE_PREFIXES = (
    "/api/public/", "/api/marketplace/", "/api/assets/public/",
    "/api/global/", "/api/projects/", "/api/economics/public/",
    "/api/pricing/public/", "/api/static/", "/api/uploads/",
    "/api/healthz", "/api/readyz", "/api/system/health",
    "/api/system/status", "/api/system/info",
)


def _is_html(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return ct.startswith("text/html") or ct.startswith("application/xhtml")


def _is_cacheable(path: str) -> bool:
    return any(path.startswith(p) for p in _CACHEABLE_PREFIXES) or path == "/"


class LumenSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach Lumen's security header baseline to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            for k, v in STATIC_HEADERS.items():
                # Only set if route didn't already set it (let handlers override).
                response.headers.setdefault(k, v)
            # CSP-RO — HTML responses only (don't apply to API JSON / static).
            if _is_html(response.headers.get("content-type", "")):
                response.headers.setdefault("Content-Security-Policy-Report-Only", _CSP_REPORT_ONLY)
            # no-store for private payloads
            if not _is_cacheable(request.url.path or "/"):
                response.headers.setdefault("Cache-Control", "no-store")
        except Exception as exc:  # pragma: no cover — never break the response
            logger.debug("header attach failed: %s", exc)
        return response


def register_csp_routes(api_router, db) -> None:
    """Mount the CSP report sink at ``CSP_REPORT_PATH``.

    Public route — the browser POSTs from any origin without credentials.
    The access gate allowlist already includes this path.
    """
    from fastapi import Request

    @api_router.post("/security/csp-report")
    async def csp_report(request: Request):
        try:
            raw = await request.body()
            payload: Dict[str, Any] = {}
            try:
                import json as _json
                payload = _json.loads(raw.decode("utf-8", "ignore") or "{}")
            except Exception:
                payload = {"raw": (raw[:2048] or b"").decode("utf-8", "ignore")}
            doc = {
                "at": datetime.now(timezone.utc),
                "ua": (request.headers.get("user-agent") or "")[:240],
                "ip": (request.headers.get("x-forwarded-for")
                       or (request.client.host if request.client else None)),
                "report": payload,
            }
            await db[CSP_COLLECTION].insert_one(doc)
        except Exception as exc:  # pragma: no cover
            logger.debug("csp report insert failed: %s", exc)
        # The browser only cares about a 2xx; we deliberately return 204.
        from starlette.responses import Response
        return Response(status_code=204)


async def ensure_indexes(db) -> None:
    try:
        await db[CSP_COLLECTION].create_index([("at", -1)])
        # TTL — prune after 30 days
        await db[CSP_COLLECTION].create_index(
            [("at", 1)], expireAfterSeconds=60 * 60 * 24 * 30,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("CSP report index ensure failed: %s", exc)


__all__ = [
    "LumenSecurityHeadersMiddleware",
    "register_csp_routes",
    "ensure_indexes",
    "CSP_REPORT_PATH",
    "CSP_COLLECTION",
    "STATIC_HEADERS",
]
