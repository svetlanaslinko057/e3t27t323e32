"""
PAY-V2-P1 — `/api/payouts-v2/*` router + hybrid-cadence scheduler.

Endpoints (admin-only unless marked):
  GET    /api/payouts-v2/admin/queue            — operational queue (Pr-7)
  GET    /api/payouts-v2/admin/batches/{id}     — batch detail + items + events
  GET    /api/payouts-v2/admin/items/{id}       — item detail + status history
  POST   /api/payouts-v2/admin/batches/propose  — manual propose (override path)
  POST   /api/payouts-v2/admin/batches/{id}/release — release a proposed batch
  POST   /api/payouts-v2/admin/batches/{id}/cancel  — cancel a proposed batch
  POST   /api/payouts-v2/admin/items/{id}/transition — manual transition (admin override)

  GET    /api/payouts-v2/developer/payment-profile
  PUT    /api/payouts-v2/developer/payment-profile
  GET    /api/payouts-v2/developer/items        — own items only

Scheduler:
  `run_scheduler_once(db, actor='scheduler')` — proposes a batch from all
  current approved earnings. Called from server boot loop on the
  configured cadence (e.g. every Friday 5pm UTC). For now wired as a
  900s (15 min) demo loop, gated by env `PAY_V2_SCHEDULER_INTERVAL_SEC`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from integrations.base import AvailabilityMode
from integrations.settlement_mock import MockSettlementProvider

import payouts_v2 as pv2
import payouts_v2_worker as pv2w

logger = logging.getLogger(__name__)


# Singleton settlement provider (Mock by default).
# Live adapters (Stripe Connect / PayPal Payouts) plug in here in PAY-V2-P2.
_PROVIDER = MockSettlementProvider()


def register_payouts_v2_routes(api_router: APIRouter, db, get_current_user, require_role=None):
    """Mount /api/payouts-v2/* on the given api_router."""

    def _require_admin(user):
        if str(getattr(user, "role", "")) != "admin":
            raise HTTPException(status_code=403, detail="Admin only")

    # ── Admin: queue (Pr-7 — queue-first UX) ───────────────────────────
    @api_router.get("/payouts-v2/admin/queue")
    async def queue(
        status: Optional[str] = Query(default=None),
        rail: Optional[str] = Query(default=None),
        user=Depends(get_current_user),
    ):
        _require_admin(user)
        return await pv2.build_queue_view(db, status=status, rail=rail)

    @api_router.get("/payouts-v2/admin/batches/{batch_id}")
    async def admin_get_batch(batch_id: str, user=Depends(get_current_user)):
        _require_admin(user)
        try:
            return await pv2.get_batch_with_items(db, batch_id=batch_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @api_router.get("/payouts-v2/admin/items/{item_id}")
    async def admin_get_item(item_id: str, user=Depends(get_current_user)):
        _require_admin(user)
        try:
            return await pv2.get_item_with_history(db, item_id=item_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @api_router.post("/payouts-v2/admin/batches/propose")
    async def admin_propose_batch(
        body: Dict[str, Any] = Body(default_factory=dict),
        user=Depends(get_current_user),
    ):
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        idem = body.get("idempotency_key") or f"manual:{uuid.uuid4().hex}"
        developer_ids = body.get("developer_ids")
        label = body.get("label") or "manual"
        try:
            return await pv2.propose_batch(
                db,
                actor=actor,
                idempotency_key=idem,
                developer_ids=developer_ids,
                label=label,
                metadata=body.get("metadata"),
            )
        except pv2.IdempotencyHit as h:
            return h.prior

    @api_router.post("/payouts-v2/admin/batches/{batch_id}/release")
    async def admin_release_batch(
        batch_id: str,
        body: Dict[str, Any] = Body(default_factory=dict),
        user=Depends(get_current_user),
    ):
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        override = bool(body.get("override"))
        try:
            return await pv2.release_batch(db, batch_id=batch_id, actor=actor, override=override)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @api_router.post("/payouts-v2/admin/batches/{batch_id}/cancel")
    async def admin_cancel_batch(
        batch_id: str,
        body: Dict[str, Any] = Body(default_factory=dict),
        user=Depends(get_current_user),
    ):
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        reason = body.get("reason", "")
        try:
            return await pv2.cancel_batch(db, batch_id=batch_id, actor=actor, reason=reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @api_router.post("/payouts-v2/admin/items/{item_id}/transition")
    async def admin_transition_item(
        item_id: str,
        body: Dict[str, Any] = Body(...),
        user=Depends(get_current_user),
    ):
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        to_status = body.get("to_status")
        if not to_status:
            raise HTTPException(status_code=400, detail="to_status required")
        try:
            return await pv2.transition_item(
                db, item_id=item_id, to_status=to_status, actor=actor,
                payload=body.get("payload"), reason=body.get("reason"),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # ── Developer: payment profile self-service (Pr-9 soft KYC) ────────
    @api_router.get("/payouts-v2/developer/payment-profile")
    async def dev_get_profile(user=Depends(get_current_user)):
        return await pv2.get_payment_profile(db, developer_id=user.user_id)

    @api_router.put("/payouts-v2/developer/payment-profile")
    async def dev_put_profile(
        body: Dict[str, Any] = Body(...),
        user=Depends(get_current_user),
    ):
        actor = f"dev:{user.user_id}"
        # Developer can only edit their own payout-related fields. KYC status
        # is admin-only here (set to "soft" by default in upsert).
        body.pop("kyc_status", None)
        body.pop("kyc_notes", None)
        return await pv2.upsert_payment_profile(
            db, developer_id=user.user_id, actor=actor, patch=body
        )

    @api_router.get("/payouts-v2/developer/items")
    async def dev_list_items(
        status: Optional[str] = Query(default=None),
        user=Depends(get_current_user),
    ):
        flt = {"developer_id": user.user_id}
        if status:
            flt["status"] = status
        items = await db.payout_items_v2.find(flt, {"_id": 0}).sort("created_at", -1).to_list(200)
        return {"items": items, "total": len(items)}

    # ── PAY-V2-P2A — Webhook ingestion ─────────────────────────────────
    # Single endpoint per provider. Idempotent (provider_event_id stored
    # in `payout_v2_idempotency`). Verifies signature, normalizes event
    # via the adapter, then transitions the item.
    @api_router.post("/payouts-v2/webhooks/stripe")
    async def stripe_webhook(request: Request):
        from fastapi import Request as _Req  # noqa: F401  (silence linter)
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        adapter = pv2w.get_provider_for_rail("stripe_connect")
        event = await adapter.verify_webhook(body, headers)
        if not event.valid:
            # 400 forces Stripe to retry — that's correct for transient
            # signature problems. Real impostor traffic logs and 400s.
            raise HTTPException(status_code=400, detail=f"invalid: {event.event_type}")

        # Idempotent: same provider event id → no-op.
        try:
            import json as _json
            raw = event.raw or _json.loads(body.decode("utf-8"))
        except Exception:
            raw = {}
        provider_event_id = (raw.get("id") if isinstance(raw, dict) else None) \
                            or f"stripe:{event.provider_ref or 'unknown'}"

        seen = await db.payout_v2_idempotency.find_one(
            {"scope": "webhook", "key": provider_event_id}, {"_id": 0},
        )
        if seen:
            return {"received": True, "duplicate": True, "kind": event.event_type}

        # Persist idempotency BEFORE acting, so even a crash mid-handler
        # doesn't double-process.
        await db.payout_v2_idempotency.insert_one({
            "scope": "webhook",
            "key": provider_event_id,
            "provider": "stripe",
            "event_type": event.event_type,
            "created_at": pv2._now_iso(),
        })

        # Handle KYC milestone separately — no item to transition.
        if event.event_type == "account_updated":
            acct = (raw.get("data") or {}).get("object") or {}
            acct_id = acct.get("id")
            if acct_id and acct.get("charges_enabled") and \
               acct.get("payouts_enabled") and acct.get("details_submitted"):
                await db.dev_payment_profiles.update_one(
                    {"rail_config.stripe_account_id": acct_id},
                    {"$set": {
                        "kyc_status": "verified",
                        "kyc_notes": "stripe.account.updated → capabilities granted",
                        "updated_at": pv2._now_iso(),
                    }},
                )
                logger.info("Stripe KYC verified for account %s", acct_id)
            return {"received": True, "kind": "account_updated"}

        # Item-level event: transition via the canonical state machine.
        if event.item_id and event.status in {
            "initiated", "in_flight", "confirmed", "settled",
            "failed", "returned", "cancelled", "disputed",
        }:
            try:
                await pv2.transition_item(
                    db, item_id=event.item_id, to_status=event.status,
                    actor="webhook:stripe",
                    payload={
                        "provider_event_id": provider_event_id,
                        "provider_ref": event.provider_ref,
                        "amount": event.amount, "currency": event.currency,
                        "error": event.error, "error_code": event.error_code,
                    },
                    reason=f"stripe webhook: {event.event_type}",
                )
            except ValueError as e:
                # Illegal transition (e.g. already settled, can't re-fail).
                # Audit but don't 500 — Stripe will stop retrying on 2xx.
                logger.info(
                    "Stripe webhook %s for item %s ignored: %s",
                    event.event_type, event.item_id, e,
                )
        return {"received": True, "kind": event.event_type}

    @api_router.post("/payouts-v2/webhooks/paypal")
    async def paypal_webhook(request: Request):
        """PayPal webhook scaffold — returns 501 until P2B."""
        adapter = pv2w.get_provider_for_rail("paypal")
        health = adapter.health()
        if not health.available:
            raise HTTPException(
                status_code=501,
                detail={
                    "ok": False, "code": "paypal_dormant",
                    "message": health.reason or "PayPal adapter dormant — see P2B",
                },
            )
        # When P2B ships: identical structure to the Stripe handler.
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        event = await adapter.verify_webhook(body, headers)
        return {"received": event.valid, "kind": event.event_type}

    # ── PAY-V2-P2A — Stripe Connect Express developer onboarding ──────
    @api_router.post("/payouts-v2/developer/stripe/onboarding")
    async def stripe_onboarding_link(
        body: Dict[str, Any] = Body(default_factory=dict),
        user=Depends(get_current_user),
    ):
        """Create (if needed) a Stripe Express account for the developer
        and return a hosted onboarding link. Idempotent — calling twice
        reuses the existing connected account ID."""
        adapter = pv2w.get_provider_for_rail("stripe_connect")
        if not adapter.health().available:
            raise HTTPException(
                status_code=503,
                detail={"ok": False, "code": "stripe_dormant",
                        "message": "Stripe adapter not configured"},
            )
        return_url  = body.get("return_url")  or "https://app.example.com/developer/payout-profile?stripe=return"
        refresh_url = body.get("refresh_url") or "https://app.example.com/developer/payout-profile?stripe=refresh"
        country     = body.get("country") or "US"

        prof = await pv2.get_payment_profile(db, developer_id=user.user_id)
        stripe_account_id = (prof.get("rail_config") or {}).get("stripe_account_id")
        if not stripe_account_id:
            try:
                acct = await adapter.create_express_account(
                    email=getattr(user, "email", None) or f"{user.user_id}@unknown.local",
                    developer_id=user.user_id,
                    country=country,
                )
                stripe_account_id = acct["id"]
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail={"ok": False, "code": "stripe_account_create_failed",
                            "message": str(e)},
                )
            # Persist the connected account id into the developer's profile.
            await pv2.upsert_payment_profile(
                db, developer_id=user.user_id, actor=f"developer:{user.user_id}",
                patch={"rail_config": {
                    **(prof.get("rail_config") or {}),
                    "stripe_account_id": stripe_account_id,
                }},
            )
        try:
            link = await adapter.create_onboarding_link(
                account_id=stripe_account_id,
                refresh_url=refresh_url,
                return_url=return_url,
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={"ok": False, "code": "stripe_link_failed",
                        "message": str(e)},
            )
        return {
            "stripe_account_id": stripe_account_id,
            "url": link["url"],
            "expires_at": link.get("expires_at"),
        }
    @api_router.get("/payouts-v2/_provider/state")
    async def provider_state(user=Depends(get_current_user)):
        _require_admin(user)
        st = await _PROVIDER.state()
        return {
            "provider": _PROVIDER.name,
            "mode": st.mode.value if hasattr(st.mode, "value") else str(st.mode),
            "reason": st.reason,
            "details": st.details,
        }

    # ── PAY-V2-P3 — Worker / execution engine endpoints ────────────────
    @api_router.get("/payouts-v2/admin/worker/status")
    async def worker_status(user=Depends(get_current_user)):
        """Operational health of the payout worker — queue depth, claim
        ownership, stale leases, stuck items, exhausted items, top failing.
        Pr-7 queue-first UX: this is the admin landing read."""
        _require_admin(user)
        return await pv2w.worker_status_snapshot(db)

    @api_router.post("/payouts-v2/admin/worker/drain-once")
    async def worker_drain_once(user=Depends(get_current_user)):
        """One-shot drain + advance + reap. Used for testing / curl smoke
        without waiting on the background loops. Admin-only."""
        _require_admin(user)
        return await pv2w.drain_once_for_test(db)

    @api_router.post("/payouts-v2/admin/items/{item_id}/force-retry")
    async def admin_item_force_retry(item_id: str, user=Depends(get_current_user)):
        """Move a queued item back into the immediate claim pool (resets
        next_attempt_at). Does NOT reset attempt_count — guards against
        infinite loops on a poison item."""
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        try:
            return await pv2w.admin_force_retry(db, item_id=item_id, actor=actor)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @api_router.post("/payouts-v2/admin/items/{item_id}/dead-letter")
    async def admin_item_dead_letter(
        item_id: str,
        body: Dict[str, Any] = Body(default_factory=dict),
        user=Depends(get_current_user),
    ):
        """Force an item to terminal failed/exhausted state. Used when
        admin decides further retries are pointless."""
        _require_admin(user)
        actor = f"admin:{user.user_id}"
        reason = body.get("reason", "admin_dead_letter")
        try:
            return await pv2w.admin_force_dead_letter(
                db, item_id=item_id, actor=actor, reason=reason,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────
# Hybrid-cadence scheduler (Pr-8)
# ──────────────────────────────────────────────────────────────────────
async def run_scheduler_once(db, *, actor: str = "scheduler") -> Dict[str, Any]:
    """One scheduler cycle. Proposes a batch from current approved earnings."""
    key = f"sched:{int(asyncio.get_event_loop().time()):d}:{uuid.uuid4().hex[:8]}"
    batch = await pv2.propose_batch(
        db, actor=actor, idempotency_key=key, label="scheduled-cycle",
    )
    return {"batch_id": batch.get("batch_id"), "empty": batch.get("empty"), "totals": batch.get("totals")}


async def scheduler_loop(db) -> None:
    """Background loop, called once at boot from server.py."""
    interval = int(os.getenv("PAY_V2_SCHEDULER_INTERVAL_SEC", "900") or 900)
    if interval <= 0:
        logger.info("PAY-V2 scheduler disabled (interval<=0)")
        return
    await pv2.ensure_indexes(db)
    logger.info("PAY-V2 scheduler started (interval %ds)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            result = await run_scheduler_once(db, actor="scheduler")
            logger.info("PAY-V2 scheduler cycle: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("PAY-V2 scheduler cycle failed (will retry)")
