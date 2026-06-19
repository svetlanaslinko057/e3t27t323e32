"""
LUMEN Sprint 11 — Acquiring Providers (Part 1 + 2 + 3)

Providers
---------
  monobank   — Monobank Acquiring (UA physical persons)
  liqpay     — LiqPay (backup channel, also UA)
  swift      — manual SWIFT wire (instructions + admin reconciliation)

Each provider:
  status()                — returns LIVE / MOCK / DISABLED + config
  create_checkout(pr)     — returns {payment_url, instructions, reference}

Mode resolution
---------------
  MONOBANK_API_KEY set    → LIVE
  LIQPAY_PUBLIC + PRIVATE → LIVE
  SWIFT_BANK_NAME etc.    → always available (manual instructions)
  No env keys             → MOCK (returns a placeholder URL + emits an
                            instant mock webhook in the background that
                            auto-confirms the payment, so the preview
                            environment shows the full flow end-to-end).

Investor endpoints
------------------
  GET  /api/banking/providers
  POST /api/investor/payments/{pr_id}/checkout      — returns provider hosted URL
  POST /api/investor/payments/{pr_id}/swift-ref     — ensures a reference is
                                                       issued for SWIFT flow
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import db, get_current_user, _now, _strip_mongo, _iso
from lumen_audit import write_audit
from lumen_bank_reconciliation import (
    new_reference, ingest_transaction, REFERENCE_PREFIX,
)

logger = logging.getLogger("lumen.banking.providers")

BACKEND_URL = (os.environ.get("BACKEND_URL") or "").rstrip("/")


# ----------------------------------------------------------------------------
# Provider status helpers
# ----------------------------------------------------------------------------

def monobank_status() -> dict:
    key = os.environ.get("MONOBANK_API_KEY")
    return {
        "provider": "monobank",
        "label": "Monobank Еквайринг",
        "mode": "live" if key else "mock",
        "configured": bool(key),
        "supports": ["UAH"],
        "audience": "Україна — фізичні особи",
    }


def liqpay_status() -> dict:
    pub = os.environ.get("LIQPAY_PUBLIC_KEY")
    pri = os.environ.get("LIQPAY_PRIVATE_KEY")
    return {
        "provider": "liqpay",
        "label": "LiqPay",
        "mode": "live" if (pub and pri) else "mock",
        "configured": bool(pub and pri),
        "supports": ["UAH", "USD", "EUR"],
        "audience": "Резервний канал",
    }


def swift_status() -> dict:
    return {
        "provider": "swift",
        "label": "SWIFT — міжнародний переказ",
        "mode": "live",  # SWIFT is always available; reconciliation is manual
        "configured": True,
        "supports": ["USD", "EUR"],
        "audience": "Інвестори поза Україною",
        "instructions": {
            "bank_name":     os.environ.get("SWIFT_BANK_NAME", "OTP Bank Ukraine"),
            "swift_code":    os.environ.get("SWIFT_BIC", "OTPBUAUK"),
            "iban_usd":      os.environ.get("SWIFT_IBAN_USD", "UA00 0000 0000 0000 0000 0000 001"),
            "iban_eur":      os.environ.get("SWIFT_IBAN_EUR", "UA00 0000 0000 0000 0000 0000 002"),
            "beneficiary":   os.environ.get("SWIFT_BENEFICIARY", "LUMEN INVESTMENT FUND LLC"),
            "address":       os.environ.get("SWIFT_ADDRESS", "Kyiv, Ukraine"),
            "correspondent": os.environ.get("SWIFT_CORRESPONDENT", ""),
        },
    }


def providers_status() -> dict:
    return {"providers": [monobank_status(), liqpay_status(), swift_status()]}


# ----------------------------------------------------------------------------
# Checkout creation
# ----------------------------------------------------------------------------

async def _ensure_reference(pr: dict) -> str:
    ref = pr.get("reference")
    if ref:
        return ref
    ref = new_reference()
    await db.lumen_payment_requests.update_one({"id": pr["id"]}, {"$set": {"reference": ref}})
    pr["reference"] = ref
    return ref


async def _mock_settle_after_delay(pr_id: str, provider: str, delay_s: float = 6.0) -> None:
    """Background task: simulates the bank webhook landing."""
    await asyncio.sleep(delay_s)
    try:
        pr = await db.lumen_payment_requests.find_one({"id": pr_id})
        if not pr or pr.get("status") in ("confirmed", "rejected", "cancelled"):
            return
        await ingest_transaction(
            provider=provider,
            provider_ref=f"mock-{uuid.uuid4().hex[:10]}",
            amount=float(pr.get("amount") or 0),
            currency=pr.get("currency") or "UAH",
            payer_name="Mock Provider Settlement",
            purpose=f"Mock settlement for {pr.get('reference')}",
            reference=pr.get("reference"),
            raw_payload={"mock": True, "payment_request_id": pr_id, "provider": provider},
        )
        logger.info("MOCK SETTLE: provider=%s pr=%s reference=%s",
                    provider, pr_id, pr.get("reference"))
    except Exception:
        logger.exception("mock settle failed for pr=%s", pr_id)


async def create_monobank_checkout(pr: dict, request: Request) -> dict:
    ref = await _ensure_reference(pr)
    status = monobank_status()
    if status["mode"] == "live":
        # LIVE path — real call to Monobank Acquiring API
        import httpx
        key = os.environ["MONOBANK_API_KEY"]
        webhook = f"{BACKEND_URL}/api/banking/webhooks/monobank" if BACKEND_URL else None
        body = {
            "amount": int(float(pr.get("amount") or 0) * 100),
            "ccy": 980,
            "merchantPaymInfo": {
                "reference": ref,
                "destination": pr.get("purpose") or f"Платіж за договором {ref}",
            },
        }
        if webhook:
            body["webHookUrl"] = webhook
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.monobank.ua/api/merchant/invoice/create",
                    json=body,
                    headers={"X-Token": key},
                )
                resp.raise_for_status()
                data = resp.json()
            return {
                "provider": "monobank",
                "mode": "live",
                "payment_url": data.get("pageUrl"),
                "invoice_id": data.get("invoiceId"),
                "reference": ref,
                "instructions": None,
            }
        except Exception as exc:  # pragma: no cover
            logger.exception("Monobank live checkout failed")
            raise HTTPException(status_code=502, detail=f"Monobank checkout failed: {exc}")
    # MOCK
    asyncio.create_task(_mock_settle_after_delay(pr["id"], "monobank"))
    mock_url = f"{BACKEND_URL or ''}/mock-checkout?provider=monobank&ref={ref}&pr={pr['id']}"
    return {
        "provider": "monobank",
        "mode": "mock",
        "payment_url": mock_url,
        "reference": ref,
        "instructions": "MOCK MODE: оплата буде автоматично підтверджена через кілька секунд.",
    }


async def create_liqpay_checkout(pr: dict, request: Request) -> dict:
    ref = await _ensure_reference(pr)
    status = liqpay_status()
    if status["mode"] == "live":
        import base64, hashlib, json
        pub = os.environ["LIQPAY_PUBLIC_KEY"]
        pri = os.environ["LIQPAY_PRIVATE_KEY"]
        body = {
            "version": 3,
            "public_key": pub,
            "action": "pay",
            "amount": float(pr.get("amount") or 0),
            "currency": pr.get("currency") or "UAH",
            "description": f"Інвестиція LUMEN • {ref}",
            "order_id": ref,
            "server_url": f"{BACKEND_URL}/api/banking/webhooks/liqpay" if BACKEND_URL else None,
        }
        data = base64.b64encode(json.dumps(body).encode()).decode()
        signature = base64.b64encode(
            hashlib.sha1((pri + data + pri).encode()).digest()).decode()
        payment_url = (
            f"https://www.liqpay.ua/api/3/checkout?data={data}&signature={signature}"
        )
        return {
            "provider": "liqpay",
            "mode": "live",
            "payment_url": payment_url,
            "reference": ref,
            "instructions": None,
        }
    # MOCK
    asyncio.create_task(_mock_settle_after_delay(pr["id"], "liqpay"))
    mock_url = f"{BACKEND_URL or ''}/mock-checkout?provider=liqpay&ref={ref}&pr={pr['id']}"
    return {
        "provider": "liqpay",
        "mode": "mock",
        "payment_url": mock_url,
        "reference": ref,
        "instructions": "MOCK MODE: оплата буде автоматично підтверджена через кілька секунд.",
    }


async def create_swift_instructions(pr: dict, request: Request) -> dict:
    ref = await _ensure_reference(pr)
    s = swift_status()
    instr = dict(s["instructions"])
    instr["reference"] = ref
    instr["amount"] = float(pr.get("amount") or 0)
    instr["currency"] = pr.get("currency") or "USD"
    return {
        "provider": "swift",
        "mode": "live",
        "payment_url": None,
        "reference": ref,
        "instructions": instr,
        "note": "Вкажіть reference як призначення платежу — переказ буде зіставлено автоматично.",
    }


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-banking"])


@router.get("/banking/providers")
async def public_providers():
    return providers_status()


class CheckoutPayload(BaseModel):
    provider: str  # 'monobank' | 'liqpay' | 'swift'


@router.post("/investor/payments/{pr_id}/checkout")
async def investor_create_checkout(pr_id: str, payload: CheckoutPayload,
                                    request: Request,
                                    user=Depends(get_current_user)):
    pr = await db.lumen_payment_requests.find_one({"id": pr_id})
    if not pr:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if pr.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    if pr.get("status") not in ("awaiting_payment", "paid", "under_review"):
        raise HTTPException(status_code=409,
                            detail=f"Платіж в статусі {pr.get('status')} — checkout недоступний")
    if payload.provider == "monobank":
        out = await create_monobank_checkout(pr, request)
    elif payload.provider == "liqpay":
        out = await create_liqpay_checkout(pr, request)
    elif payload.provider == "swift":
        out = await create_swift_instructions(pr, request)
    else:
        raise HTTPException(status_code=400, detail="Невідомий провайдер")
    await write_audit(
        action="banking.checkout_create", category="payment",
        target_type="lumen_payment_requests", target_id=pr_id,
        actor=user, request=request,
        summary=f"Checkout created via {payload.provider} for {pr_id} (mode={out['mode']})",
        meta={"reference": out.get("reference")},
    )
    return out


__all__ = ["router", "providers_status", "monobank_status",
           "liqpay_status", "swift_status"]
