"""
LUMEN Payments & Funding — Sprint 6.

Builds the financial perimeter of the platform:

    Contract Signed (KYC ✓) → Payment Request (awaiting_payment) →
    Investor uploads proof → paid → admin under_review →
    Admin confirm → confirmed → Ledger credit (investment_funding) →
    Investment.active → Ownership upsert → Raised amount + Portfolio updated

Or, on reject: status=rejected, investor can re-submit with new proof.

Entities
========
    lumen_payment_requests   — pending payments tied to investments
    lumen_payment_proofs     — uploaded receipts / pdfs / screenshots
    lumen_funding_accounts   — admin-managed bank/swift/crypto accounts
    lumen_ledger_entries     — append-only money journal (credit / debit)

Lifecycle (payment_requests)
============================
    awaiting_payment  ─(investor uploads + submits)─►  paid
                                                            ↓
                                              (admin opens) under_review
                                                            ↓
                          ┌─────────────────┬──────────────┴──────┐
                     confirm                reject            request clarification
                          ↓                    ↓                    ↓
                      confirmed           rejected            under_review (loop)
                       (terminal)        (re-submit ok)

    cancelled (terminal) — set when investment itself is cancelled.

Key rule (Sprint 6)
===================
    Ownerships, raised_amount, portfolio updates appear ONLY after a payment
    has been `confirmed`. Historical active investments are backfilled with
    payment_requests(confirmed) + ledger_entries on startup so the registry
    is complete from day one.

Money model (multi-currency)
============================
    currency       — UAH | USD | EUR (request / proof currency)
    amount         — original amount in request currency
    base_currency  — always "UAH" (platform base)
    fx_rate        — currency→UAH rate snapshot at the time of the entry
    amount_uah     — derived = amount * fx_rate (rounded to 2)

In-app notifications (no email — Sprint 7+ task)
================================================
    payment_request_created    — when awaiting_payment opens after sign
    payment_submitted          — investor submitted proof
    payment_confirmed          — admin confirmed → investment active
    payment_rejected           — admin rejected with reason
"""

from __future__ import annotations

import logging
import os
import uuid
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso
from lumen_audit import write_audit

logger = logging.getLogger("lumen.payments")


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

PAYMENT_STATUSES = [
    "awaiting_payment",  # opened, waiting for investor
    "paid",              # investor submitted proof
    "under_review",     # admin opened / asked for clarification
    "confirmed",         # admin confirmed → ledger credit + activation
    "rejected",          # admin rejected (reason required)
    "cancelled",         # investment cancelled before payment
]

PAYMENT_STATUS_LABELS = {
    "awaiting_payment": "очікує оплату",
    "paid":              "оплачено — на перевірці",
    "under_review":     "уточнення у комплаєнс",
    "confirmed":         "підтверджено",
    "rejected":          "відхилено",
    "cancelled":         "скасовано",
}

# investor may upload / re-upload proof in these statuses
_INVESTOR_SUBMITTABLE = {"awaiting_payment", "under_review", "rejected"}

# admin may act in these statuses
_ADMIN_ACTIONABLE = {"paid", "under_review"}

# terminal statuses (no further actions)
_TERMINAL_STATUSES = {"confirmed", "cancelled"}

PAYMENT_METHODS = ["bank_transfer", "swift", "crypto_future"]
PAYMENT_METHOD_LABELS = {
    "bank_transfer": "Банківський переказ",
    "swift":          "SWIFT переказ",
    "crypto_future": "Криптовалюта (буде підключено пізніше)",
}

SUPPORTED_CURRENCIES = ["UAH", "USD", "EUR"]
BASE_CURRENCY = "UAH"

LEDGER_REASONS = [
    "investment_funding",
    "payout",
    "withdrawal",
    "adjustment",
    "refund",
    # Sprint 13 — Secondary Market
    "secondary_purchase",
    "secondary_sale",
    "platform_fee",
    # D-block — UA withholding tax
    "tax_withheld",
]

LEDGER_REASON_LABELS = {
    "investment_funding": "Фінансування інвестиції",
    "payout":              "Виплата дивідендів",
    "withdrawal":          "Вивід коштів",
    "adjustment":          "Коригування реєстру",
    "refund":              "Повернення коштів",
    "secondary_purchase":  "Купівля на вторинному ринку",
    "secondary_sale":      "Продаж на вторинному ринку",
    "platform_fee":        "Комісія платформи",
}

# Default fallback FX rates (used when admin hasn't set anything explicitly).
# These are conservative starter values; admins should override per-request.
DEFAULT_FX_RATES = {"UAH": 1.0, "USD": 41.0, "EUR": 44.5}

# Local storage for uploaded proofs (kept inside the pod — same pattern as
# Sprint 3 KYC documents and Sprint 5 asset_content uploads).
UPLOADS_ROOT = Path(os.environ.get("LUMEN_UPLOADS_ROOT", "/app/backend/uploads"))
PROOFS_DIR = UPLOADS_ROOT / "payment_proofs"
PROOFS_DIR.mkdir(parents=True, exist_ok=True)
MAX_PROOF_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_PROOF_MIME = {
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "application/pdf",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fx_rate_for(currency: str) -> float:
    currency = (currency or BASE_CURRENCY).upper()
    if currency == BASE_CURRENCY:
        return 1.0
    # D3 — live FX snapshot (НБУ); falls back to defaults when offline.
    try:
        import lumen_fx
        return float(lumen_fx.cached_rate(currency))
    except Exception:
        return float(DEFAULT_FX_RATES.get(currency, 1.0))


def _round2(x: float) -> float:
    return round(float(x or 0), 2)


def _payment_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = PAYMENT_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    doc["method_label"] = PAYMENT_METHOD_LABELS.get(doc.get("payment_method"),
                                                    doc.get("payment_method"))
    for k in ("created_at", "updated_at", "submitted_at", "confirmed_at",
              "rejected_at", "cancelled_at"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    if isinstance(doc.get("history"), list):
        doc["history"] = [
            {**h, "at": _iso(h.get("at"))} for h in doc["history"]
        ]
    return _strip_mongo(doc)


def _proof_out(doc: dict) -> dict:
    doc = dict(doc)
    if doc.get("uploaded_at"):
        doc["uploaded_at"] = _iso(doc["uploaded_at"])
    return _strip_mongo(doc)


def _funding_out(doc: dict) -> dict:
    doc = dict(doc)
    if doc.get("created_at"):
        doc["created_at"] = _iso(doc["created_at"])
    if doc.get("updated_at"):
        doc["updated_at"] = _iso(doc["updated_at"])
    return _strip_mongo(doc)


def _ledger_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["reason_label"] = LEDGER_REASON_LABELS.get(doc.get("reason"), doc.get("reason"))
    if doc.get("created_at"):
        doc["created_at"] = _iso(doc["created_at"])
    return _strip_mongo(doc)


async def _notify(investor_id: str, title: str, body: str,
                  event: Optional[str] = None) -> None:
    """In-app notification (no email)."""
    await db.lumen_notifications.insert_one({
        "id": f"n-{uuid.uuid4().hex[:10]}",
        "investor_id": investor_id,
        "title": title,
        "body": body,
        "event": event,
        "read": False,
        "created_at": _now(),
    })


# ──────────────────────────────────────────────────────────────────────────────
# Core: create / confirm / reject payment_request
# ──────────────────────────────────────────────────────────────────────────────

async def create_payment_request_for_investment(investment: dict,
                                                actor_id: str = "system",
                                                ) -> Optional[dict]:
    """Create awaiting_payment request for a fully gated investment.

    Pre-conditions (Sprint 6):
        - investment.status in {kyc_pending, contract_pending, awaiting_payment}
        - KYC approved
        - contract signed
        - no open request for this investment

    Side-effects:
        - new lumen_payment_requests document (status=awaiting_payment)
        - investment.status → awaiting_payment + history entry
        - in-app notification (payment_request_created)
    """
    inv_id = investment["id"]
    # idempotency — if a non-terminal request already exists, return it.
    existing = await db.lumen_payment_requests.find_one(
        {"investment_id": inv_id,
         "status": {"$nin": ["confirmed", "cancelled", "rejected"]}}
    )
    if existing:
        return existing

    amount = float(investment.get("amount") or investment.get("invested_amount") or 0)
    if amount <= 0:
        return None

    currency = (investment.get("currency") or BASE_CURRENCY).upper()
    fx_rate = _fx_rate_for(currency)
    amount_uah = _round2(amount * fx_rate)
    now = _now()

    asset = await db.lumen_assets.find_one(
        {"id": investment.get("asset_id")},
        {"title": 1, "location": 1}
    ) or {}
    user = await db.users.find_one(
        {"user_id": investment.get("investor_id")},
        {"email": 1, "name": 1}
    ) or {}

    req = {
        "id": f"pr-{uuid.uuid4().hex[:12]}",
        "investor_id": investment.get("investor_id"),
        "investor_email": user.get("email"),
        "investor_name": user.get("name"),
        "investment_id": inv_id,
        "asset_id": investment.get("asset_id"),
        "asset_title": asset.get("title"),
        "asset_location": asset.get("location"),
        "round_id": investment.get("round_id"),
        "contract_id": investment.get("contract_id"),
        "amount": _round2(amount),
        "currency": currency,
        "base_currency": BASE_CURRENCY,
        "fx_rate": fx_rate,
        "amount_uah": amount_uah,
        "status": "awaiting_payment",
        "payment_method": "bank_transfer",
        "funding_account_id": None,
        "proof_ids": [],
        "admin_note": None,
        "reject_reason": None,
        "history": [
            {"status": "awaiting_payment", "at": now, "by": actor_id,
             "comment": "Договір підписано, KYC підтверджено — відкрито очікування оплати"},
        ],
        "created_at": now,
        "updated_at": now,
        "submitted_at": None,
        "confirmed_at": None,
        "rejected_at": None,
        "cancelled_at": None,
    }
    await db.lumen_payment_requests.insert_one(req)

    # Move investment to awaiting_payment
    await db.lumen_investments.update_one(
        {"id": inv_id},
        {"$set": {"status": "awaiting_payment", "updated_at": now,
                  "payment_request_id": req["id"]},
         "$push": {"history": {
             "status": "awaiting_payment", "at": now, "by": actor_id,
             "comment": "Очікування оплати інвестором",
         }}},
    )

    await _notify(
        investment.get("investor_id"),
        "Очікуємо оплату",
        f"Договір підписано. Перейдіть у «Мої платежі» та оплатіть "
        f"{amount:,.0f} {currency} за «{asset.get('title')}» — після підтвердження "
        "ваша інвестиція стане активною.".replace(",", " "),
        event="payment_request_created",
    )

    return req


async def confirm_payment_request(req_id: str, actor_id: str,
                                  note: Optional[str] = None) -> dict:
    """Admin confirms a paid request → activates investment + ledger entry."""
    req = await db.lumen_payment_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if req["status"] not in _ADMIN_ACTIONABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Платіж не можна підтвердити (статус: "
                   f"{PAYMENT_STATUS_LABELS.get(req['status'], req['status'])})"
        )

    inv = await db.lumen_investments.find_one({"id": req["investment_id"]})
    if not inv:
        raise HTTPException(status_code=404, detail="Інвестицію не знайдено")

    now = _now()

    # 1. Update payment request → confirmed
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "confirmed",
            "confirmed_at": now,
            "updated_at": now,
            "admin_note": note,
            "confirmed_by": actor_id,
        }, "$push": {"history": {
            "status": "confirmed", "at": now, "by": actor_id,
            "comment": note or "Платіж підтверджено комплаєнсом",
        }}},
    )

    # 2. Ledger credit (investment_funding)
    ledger_id = await _ledger_append(
        entry_type="credit",
        reason="investment_funding",
        investor_id=req["investor_id"],
        asset_id=req.get("asset_id"),
        investment_id=req["investment_id"],
        payment_request_id=req_id,
        amount=req["amount"],
        currency=req["currency"],
        fx_rate=req["fx_rate"],
        amount_uah=req["amount_uah"],
        actor_id=actor_id,
        notes=note or "Оплата інвестиції підтверджена",
    )

    # 3. Activate investment + ownership + funding (Sprint 2 engines)
    from lumen_investment_core import (_upsert_ownership, _recompute_asset_funding,
                                       _update_round_progress)
    await db.lumen_investments.update_one(
        {"id": inv["id"]},
        {"$set": {"status": "active", "invested_at": now, "updated_at": now,
                  "payment_confirmed_at": now},
         "$push": {"history": {
             "status": "active", "at": now, "by": actor_id,
             "comment": "Платіж підтверджено — інвестицію активовано",
         }}},
    )
    if inv.get("asset_id"):
        await _upsert_ownership(req["investor_id"], inv["asset_id"], inv["id"])
        await _recompute_asset_funding(inv["asset_id"])
    if inv.get("round_id"):
        await _update_round_progress(inv["round_id"])

    await _notify(
        req["investor_id"],
        "Платіж підтверджено — інвестицію активовано",
        f"Оплату {req['amount']:,.0f} {req['currency']} за «{req.get('asset_title')}» "
        "підтверджено. Інвестиція активна, частка зафіксована у портфелі.".replace(",", " "),
        event="payment_confirmed",
    )

    updated = await db.lumen_payment_requests.find_one({"id": req_id})
    return {
        "payment_request": _payment_out(updated),
        "ledger_entry_id": ledger_id,
        "investment_status": "active",
    }


async def reject_payment_request(req_id: str, actor_id: str, reason: str) -> dict:
    if not reason or not reason.strip():
        raise HTTPException(status_code=400, detail="Причина відхилення обов'язкова")
    req = await db.lumen_payment_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if req["status"] not in _ADMIN_ACTIONABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Платіж не можна відхилити (статус: "
                   f"{PAYMENT_STATUS_LABELS.get(req['status'], req['status'])})"
        )

    now = _now()
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "rejected",
            "rejected_at": now,
            "updated_at": now,
            "reject_reason": reason.strip(),
            "rejected_by": actor_id,
        }, "$push": {"history": {
            "status": "rejected", "at": now, "by": actor_id,
            "comment": reason.strip(),
        }}},
    )
    await _notify(
        req["investor_id"],
        "Платіж відхилено — потрібно повторити",
        f"Оплату {req['amount']:,.0f} {req['currency']} за «{req.get('asset_title')}» "
        f"не підтверджено. Причина: {reason.strip()}. Перевірте платіж і "
        "завантажте підтвердження ще раз у розділі «Мої платежі».".replace(",", " "),
        event="payment_rejected",
    )

    updated = await db.lumen_payment_requests.find_one({"id": req_id})
    return _payment_out(updated)


async def request_clarification(req_id: str, actor_id: str, note: str) -> dict:
    if not note or not note.strip():
        raise HTTPException(status_code=400, detail="Текст уточнення обов'язковий")
    req = await db.lumen_payment_requests.find_one({"id": req_id})
    if not req:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if req["status"] not in _ADMIN_ACTIONABLE:
        raise HTTPException(
            status_code=409,
            detail="Уточнення можна запитати лише для платежу на перевірці",
        )

    now = _now()
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$set": {
            "status": "under_review",
            "updated_at": now,
            "admin_note": note.strip(),
        }, "$push": {"history": {
            "status": "under_review", "at": now, "by": actor_id,
            "comment": f"Запит уточнення: {note.strip()}",
        }}},
    )
    await _notify(
        req["investor_id"],
        "Потрібне уточнення по платежу",
        f"Комплаєнс просить уточнити деталі платежу по «{req.get('asset_title')}». "
        f"Коментар: {note.strip()}. Відкрийте «Мої платежі» та надайте необхідну "
        "інформацію або новий скрин квитанції.",
        event="payment_under_review",
    )

    updated = await db.lumen_payment_requests.find_one({"id": req_id})
    return _payment_out(updated)


# ──────────────────────────────────────────────────────────────────────────────
# Ledger
# ──────────────────────────────────────────────────────────────────────────────

async def _ledger_append(*, entry_type: str, reason: str, investor_id: str,
                         asset_id: Optional[str], investment_id: Optional[str],
                         payment_request_id: Optional[str], amount: float,
                         currency: str, fx_rate: float, amount_uah: float,
                         actor_id: str, notes: Optional[str] = None) -> str:
    """Append-only journal write. Never updates an existing entry."""
    if entry_type not in {"credit", "debit"}:
        raise ValueError(f"Invalid ledger entry_type: {entry_type}")
    if reason not in LEDGER_REASONS:
        raise ValueError(f"Invalid ledger reason: {reason}")
    if amount is None or float(amount) <= 0:
        raise ValueError("Ledger amount must be > 0")

    doc = {
        "id": f"le-{uuid.uuid4().hex[:14]}",
        "entry_type": entry_type,
        "reason": reason,
        "investor_id": investor_id,
        "asset_id": asset_id,
        "investment_id": investment_id,
        "payment_request_id": payment_request_id,
        "amount": _round2(amount),
        "currency": currency,
        "base_currency": BASE_CURRENCY,
        "fx_rate": float(fx_rate),
        "amount_uah": _round2(amount_uah),
        "notes": notes,
        "created_by": actor_id,
        "created_at": _now(),
    }
    await db.lumen_ledger_entries.insert_one(doc)
    return doc["id"]


# ──────────────────────────────────────────────────────────────────────────────
# Backfill — historical active investments → payment_requests(confirmed) + ledger
# ──────────────────────────────────────────────────────────────────────────────

async def backfill_historical_payments() -> dict:
    """Idempotent: for every active investment without a payment_request,
    create payment_request(status=confirmed) and a matching ledger credit.
    Run once on startup. Seed integrity preserved (raised_amount unchanged)."""
    created_pr = 0
    created_le = 0
    skipped = 0
    seen_inv_ids = set()
    async for inv in db.lumen_investments.find({"status": "active"}):
        inv_id = inv["id"]
        seen_inv_ids.add(inv_id)
        existing = await db.lumen_payment_requests.find_one(
            {"investment_id": inv_id})
        if existing:
            skipped += 1
            continue

        amount = float(inv.get("amount") or inv.get("invested_amount") or 0)
        if amount <= 0:
            skipped += 1
            continue
        currency = (inv.get("currency") or BASE_CURRENCY).upper()
        fx_rate = _fx_rate_for(currency)
        amount_uah = _round2(amount * fx_rate)
        now = inv.get("invested_at") or inv.get("created_at") or _now()

        asset = await db.lumen_assets.find_one(
            {"id": inv.get("asset_id")}, {"title": 1, "location": 1}) or {}
        user = await db.users.find_one(
            {"user_id": inv.get("investor_id")}, {"email": 1, "name": 1}) or {}

        pr_id = f"pr-bf-{uuid.uuid4().hex[:10]}"
        await db.lumen_payment_requests.insert_one({
            "id": pr_id,
            "investor_id": inv.get("investor_id"),
            "investor_email": user.get("email"),
            "investor_name": user.get("name"),
            "investment_id": inv_id,
            "asset_id": inv.get("asset_id"),
            "asset_title": asset.get("title"),
            "asset_location": asset.get("location"),
            "round_id": inv.get("round_id"),
            "contract_id": inv.get("contract_id"),
            "amount": _round2(amount),
            "currency": currency,
            "base_currency": BASE_CURRENCY,
            "fx_rate": fx_rate,
            "amount_uah": amount_uah,
            "status": "confirmed",
            "payment_method": "bank_transfer",
            "funding_account_id": None,
            "proof_ids": [],
            "admin_note": "Historical backfill (Sprint 6 migration)",
            "history": [
                {"status": "confirmed", "at": now, "by": "system-backfill",
                 "comment": "Backfill from historical active investment"},
            ],
            "is_backfilled": True,
            "created_at": now,
            "updated_at": now,
            "submitted_at": now,
            "confirmed_at": now,
            "rejected_at": None,
            "cancelled_at": None,
        })
        created_pr += 1

        await _ledger_append(
            entry_type="credit",
            reason="investment_funding",
            investor_id=inv.get("investor_id"),
            asset_id=inv.get("asset_id"),
            investment_id=inv_id,
            payment_request_id=pr_id,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            amount_uah=amount_uah,
            actor_id="system-backfill",
            notes="Historical funding (backfill)",
        )
        created_le += 1
        await db.lumen_investments.update_one(
            {"id": inv_id},
            {"$set": {"payment_request_id": pr_id,
                      "payment_confirmed_at": now}},
        )

    logger.info("[Sprint 6] Backfill: %d payment_requests, %d ledger_entries "
                "(skipped %d)", created_pr, created_le, skipped)

    # Sprint 6 invariant: raised_amount must equal sum of confirmed payments
    # (i.e. sum of active investments). Normalize every asset to the ledger
    # truth — drops any phantom legacy "raised" value not backed by investments.
    from lumen_investment_core import _recompute_asset_funding
    normalized = 0
    async for a in db.lumen_assets.find({}, {"id": 1, "raised_amount": 1}):
        before = float(a.get("raised_amount") or 0)
        after = (await _recompute_asset_funding(a["id"]))["raised_amount"]
        if abs(before - after) > 0.01:
            normalized += 1
            logger.info("[Sprint 6] Normalized asset %s: raised %.2f → %.2f",
                        a["id"], before, after)
    if normalized:
        logger.info("[Sprint 6] Normalized %d asset(s) to ledger truth",
                    normalized)
    return {"created_payment_requests": created_pr,
            "created_ledger_entries": created_le,
            "skipped": skipped,
            "normalized_assets": normalized}


# ──────────────────────────────────────────────────────────────────────────────
# Funding accounts seed (idempotent — first run only)
# ──────────────────────────────────────────────────────────────────────────────

async def seed_funding_accounts() -> int:
    """Seed 3 starter funding accounts so investors see real instructions."""
    existing = await db.lumen_funding_accounts.count_documents({})
    if existing > 0:
        return 0
    now = _now()
    seed = [
        {
            "id": f"fa-{uuid.uuid4().hex[:10]}",
            "name": "Основний рахунок Lumen (USD)",
            "type": "bank_transfer",
            "bank_name": "АТ «УкрСиббанк»",
            "iban": "UA213223130000026007000000001",
            "beneficiary": "ТОВ «Lumen Capital»",
            "edrpou": "44512387",
            "currency": "UAH",
            "swift_code": None,
            "purpose_template": "Поповнення інвестиційного рахунку, договір №{contract_number}",
            "active": True,
            "default": True,
            "notes": "Призначення платежу обов'язково має містити номер договору.",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": f"fa-{uuid.uuid4().hex[:10]}",
            "name": "SWIFT-рахунок Lumen (USD)",
            "type": "swift",
            "bank_name": "Citibank N.A. (correspondent)",
            "iban": "UA503223130000026000000000002",
            "beneficiary": "Lumen Capital LLC",
            "edrpou": "44512387",
            "currency": "USD",
            "swift_code": "CITIUS33",
            "purpose_template": "Investment funding, contract №{contract_number}",
            "active": True,
            "default": False,
            "notes": "Комісія банку-кореспондента стягується з відправника (OUR).",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": f"fa-{uuid.uuid4().hex[:10]}",
            "name": "Crypto-рахунок (підключення пізніше)",
            "type": "crypto_future",
            "bank_name": None,
            "iban": None,
            "beneficiary": "Lumen Capital",
            "edrpou": None,
            "currency": "USDT",
            "swift_code": None,
            "purpose_template": "Буде підключено у Sprint 7+",
            "active": False,
            "default": False,
            "notes": "Канал поки що неактивний. Сповістимо інвесторів окремо.",
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.lumen_funding_accounts.insert_many(seed)
    logger.info("[Sprint 6] Seeded %d funding_accounts", len(seed))
    return len(seed)


# ──────────────────────────────────────────────────────────────────────────────
# Investor lifecycle hook (called from contract.sign)
# ──────────────────────────────────────────────────────────────────────────────

async def open_payment_requests_for_investor(investor_id: str,
                                             actor_id: str = "system") -> dict:
    """For each investment that just became eligible (KYC ok + contract signed),
    create a payment_request and move investment.status → awaiting_payment.

    Called from:
        - contract sign hook (after the legal gate is passed)
        - KYC approval hook (so old contract_pending investments open up)
    """
    opened = 0
    from lumen_investment_core import _investor_kyc_approved, _contract_signed
    kyc_ok = await _investor_kyc_approved(investor_id)
    if not kyc_ok:
        return {"opened": 0, "skipped_kyc": True}

    async for inv in db.lumen_investments.find(
        {"investor_id": investor_id,
         "status": {"$in": ["kyc_pending", "contract_pending"]}}
    ):
        signed = await _contract_signed(inv)
        if not signed:
            continue
        # Promote from contract_pending → awaiting_payment via create_payment_request
        req = await create_payment_request_for_investment(inv, actor_id=actor_id)
        if req:
            opened += 1
    return {"opened": opened}


# ──────────────────────────────────────────────────────────────────────────────
# Router — Investor endpoints
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-payments"])


@router.get("/investor/payments")
async def list_my_payments(status: Optional[str] = None,
                           user=Depends(get_current_user)):
    q: dict[str, Any] = {"investor_id": user["id"]}
    if status:
        if status not in PAYMENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["status"] = status
    items = []
    async for r in db.lumen_payment_requests.find(q).sort("created_at", -1).limit(500):
        items.append(_payment_out(r))

    counts = {}
    for s in PAYMENT_STATUSES:
        counts[s] = await db.lumen_payment_requests.count_documents(
            {"investor_id": user["id"], "status": s})
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/investor/payments/{req_id}")
async def get_my_payment(req_id: str, user=Depends(get_current_user)):
    r = await db.lumen_payment_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if r.get("investor_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Немає доступу")
    out = _payment_out(r)
    # Attach proofs
    proofs = []
    async for p in db.lumen_payment_proofs.find({"payment_request_id": req_id}):
        proofs.append(_proof_out(p))
    out["proofs"] = proofs
    # Attach funding accounts (active, matching currency)
    accounts = []
    async for fa in db.lumen_funding_accounts.find(
            {"active": True, "currency": r["currency"]}):
        accounts.append(_funding_out(fa))
    if not accounts:
        async for fa in db.lumen_funding_accounts.find({"active": True}):
            accounts.append(_funding_out(fa))
    out["funding_accounts"] = accounts
    return out


@router.post("/investor/payments/{req_id}/proof")
async def upload_proof(req_id: str, file: UploadFile = File(...),
                       user=Depends(get_current_user)):
    r = await db.lumen_payment_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if r.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    if r["status"] not in _INVESTOR_SUBMITTABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Завантаження неможливе (статус: "
                   f"{PAYMENT_STATUS_LABELS.get(r['status'], r['status'])})"
        )

    contents = await file.read()
    if len(contents) > MAX_PROOF_SIZE:
        raise HTTPException(status_code=413, detail="Файл більше 10 МБ")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Порожній файл")
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if mime not in ALLOWED_PROOF_MIME:
        raise HTTPException(
            status_code=400,
            detail="Підтримуються лише PNG, JPG, WEBP, PDF",
        )

    proof_id = f"pp-{uuid.uuid4().hex[:14]}"
    ext = mimetypes.guess_extension(mime) or ".bin"
    safe_filename = f"{proof_id}{ext}"
    path = PROOFS_DIR / safe_filename
    with open(path, "wb") as fh:
        fh.write(contents)

    now = _now()
    doc = {
        "id": proof_id,
        "payment_request_id": req_id,
        "investor_id": user["id"],
        "filename": file.filename or safe_filename,
        "storage_filename": safe_filename,
        "mime_type": mime,
        "size": len(contents),
        "file_path": str(path),
        "uploaded_at": now,
    }
    await db.lumen_payment_proofs.insert_one(doc)
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$push": {"proof_ids": proof_id},
         "$set": {"updated_at": now}},
    )
    return {"proof": _proof_out(doc)}


@router.delete("/investor/payments/{req_id}/proof/{proof_id}")
async def delete_proof(req_id: str, proof_id: str,
                       user=Depends(get_current_user)):
    r = await db.lumen_payment_requests.find_one({"id": req_id})
    if not r or r.get("investor_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if r["status"] not in _INVESTOR_SUBMITTABLE:
        raise HTTPException(
            status_code=409,
            detail="Видалити підтвердження можна лише до перевірки комплаєнсом",
        )
    p = await db.lumen_payment_proofs.find_one({"id": proof_id})
    if not p or p.get("payment_request_id") != req_id:
        raise HTTPException(status_code=404, detail="Підтвердження не знайдено")
    try:
        Path(p["file_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    await db.lumen_payment_proofs.delete_one({"id": proof_id})
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$pull": {"proof_ids": proof_id},
         "$set": {"updated_at": _now()}},
    )
    return {"ok": True, "deleted": proof_id}


class SubmitPayload(BaseModel):
    payment_method: Optional[str] = None
    funding_account_id: Optional[str] = None
    note: Optional[str] = None


@router.post("/investor/payments/{req_id}/submit")
async def submit_payment(req_id: str, payload: SubmitPayload = None,
                         user=Depends(get_current_user)):
    """Investor marks the payment as paid (uploaded proofs + ready for review)."""
    r = await db.lumen_payment_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    if r.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    if r["status"] not in {"awaiting_payment", "under_review", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail=f"Платіж не можна подати (статус: "
                   f"{PAYMENT_STATUS_LABELS.get(r['status'], r['status'])})"
        )
    if not r.get("proof_ids"):
        raise HTTPException(
            status_code=400,
            detail="Завантажте хоча б одне підтвердження оплати",
        )

    now = _now()
    update_set = {
        "status": "paid",
        "submitted_at": now,
        "updated_at": now,
    }
    if payload:
        if payload.payment_method:
            if payload.payment_method not in PAYMENT_METHODS:
                raise HTTPException(status_code=400, detail="Невідомий метод оплати")
            update_set["payment_method"] = payload.payment_method
        if payload.funding_account_id:
            update_set["funding_account_id"] = payload.funding_account_id
        if payload.note:
            update_set["investor_note"] = payload.note.strip()
    await db.lumen_payment_requests.update_one(
        {"id": req_id},
        {"$set": update_set,
         "$push": {"history": {
             "status": "paid", "at": now, "by": user["id"],
             "comment": "Інвестор подав підтвердження оплати",
         }}},
    )
    await _notify(
        user["id"],
        "Платіж подано на перевірку",
        f"Підтвердження по «{r.get('asset_title')}» надіслано комплаєнсу. "
        "Зазвичай перевірка займає 1 робочий день.",
        event="payment_submitted",
    )

    # Inform all admins via in-app notification
    async for admin in db.users.find({"role": "admin"}, {"user_id": 1}):
        await db.lumen_notifications.insert_one({
            "id": f"n-{uuid.uuid4().hex[:10]}",
            "investor_id": admin.get("user_id"),
            "title": "Новий платіж на перевірку",
            "body": f"Інвестор {r.get('investor_email') or r.get('investor_name')} "
                    f"подав оплату {r['amount']:,.0f} {r['currency']} "
                    f"за «{r.get('asset_title')}».".replace(",", " "),
            "event": "payment_submitted",
            "read": False,
            "created_at": now,
        })

    updated = await db.lumen_payment_requests.find_one({"id": req_id})
    return _payment_out(updated)


# ──────────────────────────────────────────────────────────────────────────────
# Router — proof file access (owner / admin)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/payment-proofs/{proof_id}/file")
async def download_proof(proof_id: str, user=Depends(get_current_user)):
    p = await db.lumen_payment_proofs.find_one({"id": proof_id})
    if not p:
        raise HTTPException(status_code=404, detail="Файл не знайдено")
    if p.get("investor_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Немає доступу")
    path = Path(p["file_path"])
    if not path.exists():
        raise HTTPException(status_code=410, detail="Файл вже не доступний")
    return FileResponse(str(path), media_type=p.get("mime_type"),
                        filename=p.get("filename"))


# ──────────────────────────────────────────────────────────────────────────────
# Router — Admin payment queue
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/payments")
async def admin_payments(status: Optional[str] = None,
                         asset_id: Optional[str] = None,
                         investor_id: Optional[str] = None,
                         _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        if status not in PAYMENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["status"] = status
    if asset_id:
        q["asset_id"] = asset_id
    if investor_id:
        q["investor_id"] = investor_id
    items = []
    async for r in db.lumen_payment_requests.find(q).sort("created_at", -1).limit(500):
        items.append(_payment_out(r))
    counts = {}
    for s in PAYMENT_STATUSES:
        counts[s] = await db.lumen_payment_requests.count_documents({"status": s})
    counts["total"] = await db.lumen_payment_requests.count_documents({})
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/admin/payments/{req_id}")
async def admin_payment_detail(req_id: str, _=Depends(require_admin)):
    r = await db.lumen_payment_requests.find_one({"id": req_id})
    if not r:
        raise HTTPException(status_code=404, detail="Платіж не знайдено")
    out = _payment_out(r)
    proofs = []
    async for p in db.lumen_payment_proofs.find({"payment_request_id": req_id}):
        proofs.append(_proof_out(p))
    out["proofs"] = proofs
    # related ledger entries
    le = []
    async for entry in db.lumen_ledger_entries.find(
            {"payment_request_id": req_id}).sort("created_at", 1):
        le.append(_ledger_out(entry))
    out["ledger_entries"] = le
    # related investment
    inv = await db.lumen_investments.find_one({"id": r.get("investment_id")}) or {}
    if inv:
        from lumen_investment_core import _investment_with_labels
        out["investment"] = _investment_with_labels(inv)
    return out


class AdminActionPayload(BaseModel):
    note: Optional[str] = None
    reason: Optional[str] = None


@router.post("/admin/payments/{req_id}/confirm")
async def admin_confirm_payment(req_id: str, payload: AdminActionPayload = None,
                                request: Request = None,
                                admin=Depends(require_admin)):
    result = await confirm_payment_request(req_id, admin["id"],
                                           note=(payload.note if payload else None))
    await write_audit(
        action="payment.confirm", category="payment",
        target_type="lumen_payment_requests", target_id=req_id,
        actor=admin, request=request,
        summary=f"Payment confirmed: {req_id}",
        meta={"note": (payload.note if payload else None),
              "investor_id": (result or {}).get("investor_id"),
              "amount_uah": (result or {}).get("amount_uah")},
    )
    return result


@router.post("/admin/payments/{req_id}/reject")
async def admin_reject_payment(req_id: str, payload: AdminActionPayload,
                               request: Request = None,
                               admin=Depends(require_admin)):
    reason = (payload.reason or "").strip()
    result = await reject_payment_request(req_id, admin["id"], reason=reason)
    await write_audit(
        action="payment.reject", category="payment",
        target_type="lumen_payment_requests", target_id=req_id,
        actor=admin, request=request,
        summary=f"Payment rejected: {req_id} ({reason})",
        meta={"reason": reason},
    )
    return result


@router.post("/admin/payments/{req_id}/clarification")
async def admin_request_clarification(req_id: str, payload: AdminActionPayload,
                                      request: Request = None,
                                      admin=Depends(require_admin)):
    note = (payload.note or "").strip()
    result = await request_clarification(req_id, admin["id"], note=note)
    await write_audit(
        action="payment.clarification_requested", category="payment",
        target_type="lumen_payment_requests", target_id=req_id,
        actor=admin, request=request,
        summary=f"Payment clarification requested: {req_id}",
        meta={"note": note},
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Router — Funding accounts (admin CRUD + public read)
# ──────────────────────────────────────────────────────────────────────────────

class FundingAccountPayload(BaseModel):
    name: str
    type: str = "bank_transfer"
    bank_name: Optional[str] = None
    iban: Optional[str] = None
    swift_code: Optional[str] = None
    beneficiary: Optional[str] = None
    edrpou: Optional[str] = None
    currency: str = "UAH"
    purpose_template: Optional[str] = None
    active: bool = True
    default: bool = False
    notes: Optional[str] = None


@router.get("/admin/funding-accounts")
async def admin_list_funding_accounts(_=Depends(require_admin)):
    items = []
    async for fa in db.lumen_funding_accounts.find().sort("created_at", 1):
        items.append(_funding_out(fa))
    return {"items": items, "total": len(items)}


@router.post("/admin/funding-accounts")
async def admin_create_funding_account(payload: FundingAccountPayload,
                                       admin=Depends(require_admin)):
    if payload.type not in ("bank_transfer", "swift", "crypto_future"):
        raise HTTPException(status_code=400, detail="Невідомий тип рахунку")
    now = _now()
    doc = payload.model_dump()
    doc["id"] = f"fa-{uuid.uuid4().hex[:10]}"
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["created_by"] = admin["id"]
    if doc.get("default"):
        # ensure only one default per currency
        await db.lumen_funding_accounts.update_many(
            {"currency": doc["currency"], "default": True},
            {"$set": {"default": False}}
        )
    await db.lumen_funding_accounts.insert_one(doc)
    return _funding_out(doc)


@router.patch("/admin/funding-accounts/{fa_id}")
async def admin_update_funding_account(fa_id: str,
                                       payload: FundingAccountPayload,
                                       admin=Depends(require_admin)):
    fa = await db.lumen_funding_accounts.find_one({"id": fa_id})
    if not fa:
        raise HTTPException(status_code=404, detail="Рахунок не знайдено")
    update = payload.model_dump()
    update["updated_at"] = _now()
    update["updated_by"] = admin["id"]
    if update.get("default"):
        await db.lumen_funding_accounts.update_many(
            {"currency": update["currency"], "default": True, "id": {"$ne": fa_id}},
            {"$set": {"default": False}}
        )
    await db.lumen_funding_accounts.update_one({"id": fa_id}, {"$set": update})
    fa2 = await db.lumen_funding_accounts.find_one({"id": fa_id})
    # IR0.3 — field-level change history (IBAN / BIC / holder are
    # regulator-sensitive; we ALWAYS want a who-when-what record for them).
    try:
        from lumen_field_changes import record_diff as _ir0_record_diff
        await _ir0_record_diff(
            db,
            entity_type="funding_account",
            entity_id=fa_id,
            before=fa or {},
            after=fa2 or {},
            actor=admin,
            source="api",
            reason="admin_update_funding_account",
        )
    except Exception:
        pass
    return _funding_out(fa2)


@router.delete("/admin/funding-accounts/{fa_id}")
async def admin_delete_funding_account(fa_id: str, admin=Depends(require_admin)):
    fa = await db.lumen_funding_accounts.find_one({"id": fa_id})
    if not fa:
        raise HTTPException(status_code=404, detail="Рахунок не знайдено")
    # soft delete (active=False) — never hard delete to preserve referential history
    await db.lumen_funding_accounts.update_one(
        {"id": fa_id},
        {"$set": {"active": False, "default": False, "updated_at": _now(),
                  "deleted_by": admin["id"], "deleted_at": _now()}}
    )
    # IR0.3 — explicit "deactivated" event
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="funding_account", entity_id=fa_id,
            field="status", old_value="active", new_value="deactivated",
            actor=admin, source="api", reason="admin_delete_funding_account",
        )
    except Exception:
        pass
    return {"ok": True, "id": fa_id, "active": False}


@router.get("/funding-accounts/public")
async def public_funding_accounts():
    """Public-safe view: investors see only active accounts with masked IBAN."""
    items = []
    async for fa in db.lumen_funding_accounts.find({"active": True}).sort("default", -1):
        items.append(_funding_out(fa))
    return {"items": items, "total": len(items)}


# ──────────────────────────────────────────────────────────────────────────────
# Router — Ledger (admin)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/admin/ledger")
async def admin_ledger(entry_type: Optional[str] = None,
                       reason: Optional[str] = None,
                       investor_id: Optional[str] = None,
                       asset_id: Optional[str] = None,
                       limit: int = 200,
                       _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if entry_type:
        if entry_type not in ("credit", "debit"):
            raise HTTPException(status_code=400, detail="entry_type: credit|debit")
        q["entry_type"] = entry_type
    if reason:
        if reason not in LEDGER_REASONS:
            raise HTTPException(status_code=400, detail=f"reason ∈ {LEDGER_REASONS}")
        q["reason"] = reason
    if investor_id:
        q["investor_id"] = investor_id
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    async for e in db.lumen_ledger_entries.find(q).sort("created_at", -1).limit(min(limit, 1000)):
        items.append(_ledger_out(e))
    # summary aggregates by currency
    summary = {"credit": {}, "debit": {}, "total_uah_credit": 0.0,
               "total_uah_debit": 0.0}
    async for e in db.lumen_ledger_entries.find(q):
        bucket = summary[e["entry_type"]]
        cur = e["currency"]
        bucket[cur] = _round2(bucket.get(cur, 0.0) + float(e["amount"]))
        if e["entry_type"] == "credit":
            summary["total_uah_credit"] = _round2(
                summary["total_uah_credit"] + float(e["amount_uah"]))
        else:
            summary["total_uah_debit"] = _round2(
                summary["total_uah_debit"] + float(e["amount_uah"]))
    summary["net_uah"] = _round2(summary["total_uah_credit"]
                                  - summary["total_uah_debit"])
    return {"items": items, "total": len(items), "summary": summary}


# ──────────────────────────────────────────────────────────────────────────────
# Router — Investor in-app notifications (read endpoint)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/investor/notifications")
async def list_investor_notifications(limit: int = 50,
                                       user=Depends(get_current_user)):
    items = []
    async for n in db.lumen_notifications.find(
            {"investor_id": user["id"]}
        ).sort("created_at", -1).limit(min(limit, 200)):
        n2 = dict(n)
        if n2.get("created_at"):
            n2["created_at"] = _iso(n2["created_at"])
        items.append(_strip_mongo(n2))
    unread = await db.lumen_notifications.count_documents(
        {"investor_id": user["id"], "read": False})
    return {"items": items, "total": len(items), "unread": unread}


class NotifMarkPayload(BaseModel):
    ids: Optional[List[str]] = None
    all: bool = False


@router.post("/investor/notifications/mark-read")
async def mark_notifications_read(payload: NotifMarkPayload,
                                  user=Depends(get_current_user)):
    q: dict[str, Any] = {"investor_id": user["id"], "read": False}
    if payload.all:
        pass
    elif payload.ids:
        q["id"] = {"$in": payload.ids}
    else:
        raise HTTPException(status_code=400, detail="Вкажіть ids або all=true")
    res = await db.lumen_notifications.update_many(q, {"$set": {"read": True}})
    return {"updated": res.modified_count}


__all__ = [
    "router",
    "backfill_historical_payments",
    "seed_funding_accounts",
    "create_payment_request_for_investment",
    "open_payment_requests_for_investor",
    "confirm_payment_request",
    "reject_payment_request",
    "request_clarification",
    "PAYMENT_STATUSES",
    "LEDGER_REASONS",
]
