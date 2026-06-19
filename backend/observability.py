"""
P4 — Observability nervous system (Sentry).

Init contract:
  • Reads SENTRY_DSN from env. If unset → no-op (tests + dev safe).
  • Reads SENTRY_ENVIRONMENT (default "preview") and SENTRY_RELEASE.
  • Wires FastAPI + Starlette + asyncio + logging integrations.
  • PII off by default; can be enabled with SENTRY_SEND_PII=true.

Exposed helpers:
  • init_sentry()                    — call once at process start
  • capture_worker_exception(name, exc, extra)
                                     — uniform tagging from background loops
  • is_enabled()                     — feature flag readout
  • bind_request_tags(role, user_id) — attach actor context to current scope

The frontend forwards client-side renders via POST /api/observability/client-error
(see register_observability_routes below).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_ENABLED = False


class ClientErrorIn(BaseModel):
    """Frontend-reported error payload (web + expo)."""
    kind: str = Field(default="render_error", max_length=64)
    message: str = Field(default="", max_length=2000)
    stack: Optional[str] = Field(default=None, max_length=20000)
    url: Optional[str] = Field(default=None, max_length=512)
    user_agent: Optional[str] = Field(default=None, max_length=512)
    release: Optional[str] = Field(default=None, max_length=64)
    platform: Optional[str] = Field(default=None, max_length=32)
    context: Optional[Dict[str, Any]] = None


def init_sentry() -> bool:
    """Idempotent Sentry init. Returns True if enabled."""
    global _ENABLED
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        logger.info("OBSERVABILITY: SENTRY_DSN not set — capture disabled")
        return False
    if _ENABLED:
        return True
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "preview"),
            release=os.getenv("SENTRY_RELEASE") or None,
            send_default_pii=(os.getenv("SENTRY_SEND_PII", "").lower() in ("1", "true", "yes")),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0") or 0.0),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0") or 0.0),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            attach_stacktrace=True,
            default_integrations=True,
        )
        sentry_sdk.set_tag("service", "atlas-backend")
        _ENABLED = True
        logger.info("OBSERVABILITY: Sentry initialised env=%s", os.getenv("SENTRY_ENVIRONMENT", "preview"))
        return True
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning(f"OBSERVABILITY: Sentry init failed ({e!r}) — running without")
        return False


def is_enabled() -> bool:
    return _ENABLED


def capture_worker_exception(worker_name: str, exc: BaseException, extra: Optional[Dict[str, Any]] = None) -> None:
    """Tag-rich capture for background loops (worker, reaper, advancer, etc.)."""
    if not _ENABLED:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("subsystem", "worker")
            scope.set_tag("worker", worker_name)
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def capture_alert(
    subsystem: str,
    message: str,
    *,
    level: str = "warning",
    tags: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Threshold-driven server-side alert (non-exception).

    Used by background observers (reconciler, etc.) to escalate when a
    headline counter crosses an env-defined threshold. No DB writes — the
    underlying events (e.g. payout_divergence_events) are already persisted
    by their own subsystem. This helper is purely the Sentry/PagerDuty
    side-channel and no-ops when SENTRY_DSN isn't set.
    """
    if not _ENABLED:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("subsystem", subsystem)
            scope.set_tag("alert", "true")
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, str(v))
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass


def bind_request_tags(role: Optional[str], user_id: Optional[str]) -> None:
    if not _ENABLED:
        return
    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            if user_id:
                scope.set_user({"id": user_id, "role": role or ""})
            if role:
                scope.set_tag("actor.role", role)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Client-error sink — forwards frontend renders to Sentry + Mongo audit
# -----------------------------------------------------------------------------

async def register_observability_routes(fastapi_app, db, get_current_user) -> None:
    """Mount observability routes on fastapi_app as a fresh /api router.

    Endpoints:
      POST /api/observability/client-error          — frontend error sink
      GET  /api/admin/observability/client-errors   — admin list
      GET  /api/admin/observability/health          — admin readout
    """
    from datetime import datetime, timezone

    router = APIRouter(prefix="/api")

    async def _persist(payload: Dict[str, Any]) -> None:
        try:
            await db.client_errors.insert_one(payload)
        except Exception:
            logger.exception("OBSERVABILITY: persist client_errors failed")

    @router.post("/observability/client-error")
    async def _client_error(request: Request, body: ClientErrorIn = Body(...)):
        # Allow anonymous reporting so pre-auth render errors are still captured.
        user = None
        try:
            user = await get_current_user(request)  # type: ignore[arg-type]
        except Exception:
            user = None
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "at": now,
            "kind": body.kind,
            "message": (body.message or "")[:2000],
            "stack": body.stack,
            "url": body.url,
            "user_agent": body.user_agent or request.headers.get("user-agent", ""),
            "release": body.release,
            "platform": body.platform,
            "context": body.context or {},
            "actor_user_id": getattr(user, "user_id", None),
            "actor_role": getattr(user, "role", None),
            "ip": request.client.host if request.client else None,
        }
        # don't return _id
        await _persist(record)

        if _ENABLED:
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("subsystem", "frontend")
                    scope.set_tag("kind", body.kind)
                    if body.platform:
                        scope.set_tag("platform", body.platform)
                    if body.release:
                        scope.set_tag("release.frontend", body.release)
                    if body.url:
                        scope.set_extra("url", body.url)
                    if body.context:
                        for k, v in body.context.items():
                            scope.set_extra(f"ctx.{k}", v)
                    scope.set_user({
                        "id": getattr(user, "user_id", None) or "anonymous",
                        "role": getattr(user, "role", None) or "",
                    })
                    sentry_sdk.capture_message(
                        body.message or body.kind or "frontend error",
                        level="error",
                    )
            except Exception:
                pass

        return {"ok": True}

    @router.get("/admin/observability/client-errors")
    async def _client_errors_list(
        limit: int = 50,
        kind: Optional[str] = None,
        user=Depends(get_current_user),
    ):
        # admin-only
        roles = set(getattr(user, "roles", []) or [])
        if "admin" not in roles and getattr(user, "role", "") != "admin":
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin only")
        q: Dict[str, Any] = {}
        if kind:
            q["kind"] = kind
        cur = db.client_errors.find(q, {"_id": 0}).sort("at", -1).limit(max(1, min(int(limit), 500)))
        items = [r async for r in cur]
        return {"items": items, "count": len(items)}

    @router.get("/admin/observability/health")
    async def _obs_health(user=Depends(get_current_user)):
        roles = set(getattr(user, "roles", []) or [])
        if "admin" not in roles and getattr(user, "role", "") != "admin":
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Admin only")
        total = await db.client_errors.count_documents({})
        recent = await db.client_errors.count_documents({})  # window queries can be added later
        return {
            "sentry_enabled": _ENABLED,
            "environment": os.getenv("SENTRY_ENVIRONMENT", "preview"),
            "release": os.getenv("SENTRY_RELEASE"),
            "client_errors_total": total,
            "client_errors_window": recent,
        }

    fastapi_app.include_router(router)
