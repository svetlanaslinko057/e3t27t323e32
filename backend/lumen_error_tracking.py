"""
LUMEN Sprint 10 — Error Tracking (Block 6)

Prepares Sentry / Rollbar integration but does NOT enable it by default.
Flip on by setting `SENTRY_DSN` (or `ROLLBAR_TOKEN`) in the backend env and
restarting. While inactive we still expose admin visibility into the
configured provider so ops can confirm what's live.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends

from lumen_api import require_admin

logger = logging.getLogger("lumen.error_tracking")

_initialised = False
_provider: str | None = None
_init_error: str | None = None


def init_error_tracking() -> dict:
    """Initialise Sentry or Rollbar if a DSN/token is provided. Idempotent."""
    global _initialised, _provider, _init_error
    if _initialised:
        return status()
    dsn = os.environ.get("SENTRY_DSN") or ""
    rollbar_token = os.environ.get("ROLLBAR_TOKEN") or ""
    try:
        if dsn:
            try:
                import sentry_sdk  # type: ignore
                from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
                sentry_sdk.init(
                    dsn=dsn,
                    environment=os.environ.get("ENV", "preview"),
                    integrations=[FastApiIntegration()],
                    traces_sample_rate=0.0,
                )
                _provider = "sentry"
                _initialised = True
                logger.info("ERROR-TRACKING: Sentry initialised")
            except ImportError:
                _init_error = "sentry_sdk not installed — add to requirements.txt to enable"
                logger.warning(_init_error)
        elif rollbar_token:
            try:
                import rollbar  # type: ignore
                rollbar.init(rollbar_token, environment=os.environ.get("ENV", "preview"))
                _provider = "rollbar"
                _initialised = True
                logger.info("ERROR-TRACKING: Rollbar initialised")
            except ImportError:
                _init_error = "rollbar not installed — add to requirements.txt to enable"
                logger.warning(_init_error)
        else:
            _provider = None
            logger.info("ERROR-TRACKING: no DSN/token — disabled")
    except Exception as exc:  # pragma: no cover
        _init_error = str(exc)
        logger.exception("ERROR-TRACKING init failed")
    return status()


def status() -> dict:
    return {
        "initialised": _initialised,
        "provider": _provider,
        "sentry_configured": bool(os.environ.get("SENTRY_DSN")),
        "rollbar_configured": bool(os.environ.get("ROLLBAR_TOKEN")),
        "error": _init_error,
    }


def capture_exception(exc: BaseException, **context: Any) -> None:
    """Send an exception to the active provider. No-op if disabled."""
    if not _initialised:
        return
    try:
        if _provider == "sentry":
            import sentry_sdk  # type: ignore
            with sentry_sdk.push_scope() as scope:
                for k, v in context.items():
                    scope.set_extra(k, v)
                sentry_sdk.capture_exception(exc)
        elif _provider == "rollbar":
            import rollbar  # type: ignore
            rollbar.report_exc_info(extra_data=context)
    except Exception:  # pragma: no cover
        logger.exception("ERROR-TRACKING capture failed")


router = APIRouter(prefix="/api", tags=["lumen-error-tracking"])


@router.get("/admin/error-tracking/status")
async def admin_error_tracking_status(_=Depends(require_admin)):
    return status()


__all__ = ["router", "init_error_tracking", "status", "capture_exception"]
