"""
Sprint 7 — Wallet + Withdrawals.

Дає інвестору:
  - баланс (порахований із ledger_entries, НЕ окрема «магічна сума»);
  - історію руху коштів;
  - можливість запросити вивід коштів на банківські реквізити.

Колекції:
  lumen_wallets               — матеріалізована проєкція балансу (investor_id+currency)
  lumen_withdrawal_requests   — заявки на вивід (lifecycle + history)

Ledger:
  Будь-який РЕАЛІЗОВАНИЙ вивід пишеться ТІЛЬКИ через lumen_ledger_entries
  (reason="withdrawal", entry_type="debit") — і лише на статусі `paid`.

Розрахунок балансу (база — UAH):
  total_in  = Σ credit (reason ∈ {payout, refund, adjustment})            [+ realized]
  total_out = Σ debit  (reason ∈ {withdrawal, adjustment})                 [paid виводи]
  settled   = total_in − total_out
  pending   = Σ amount_uah заявок у статусах {requested, under_review,
                                              approved, processing}        [резерв]
  available = settled − pending

  * `investment_funding` (внесок у актив) НЕ впливає на кеш-гаманець —
    це капітал, розгорнутий в актив, відображається у портфелі.

Lifecycle заявки на вивід:
  requested → under_review → approved → processing → paid        (термінальний)
            ↘ rejected (коментар обов'язковий)                    (термінальний)
  requested / under_review → cancelled (інвестором)              (термінальний)

  При заявці  : резерв (pending↑, available↓), БЕЗ ledger.
  При paid    : final debit у ledger, pending↓ → realized total_out↑ (available незмінний).
  При reject  : резерв повертається (pending↓, available↑), БЕЗ ledger.

НЕ робимо у цьому спринті: автоплатежі / payout engine / crypto / банківський API.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso
from lumen_audit import write_audit
from lumen_payments import (
    _ledger_append,
    _round2,
    _fx_rate_for,
    BASE_CURRENCY,
    SUPPORTED_CURRENCIES,
    LEDGER_REASON_LABELS,
    _notify,
)

logger = logging.getLogger("lumen.wallet")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

WITHDRAWAL_STATUSES = [
    "requested",     # створено інвестором (резерв)
    "under_review",  # на розгляді комплаєнсу (резерв)
    "approved",      # схвалено до виплати (резерв)
    "processing",    # у роботі казначейства (резерв)
    "paid",          # виплачено → ledger debit (термінальний)
    "rejected",      # відхилено, резерв повернуто (термінальний)
    "cancelled",     # скасовано інвестором (термінальний)
]

WITHDRAWAL_STATUS_LABELS = {
    "requested":    "створено",
    "under_review": "на розгляді",
    "approved":     "схвалено",
    "processing":   "виконується",
    "paid":         "виплачено",
    "rejected":     "відхилено",
    "cancelled":    "скасовано",
}

# Заявки в цих статусах резервують кошти (входять у pending_balance).
RESERVED_STATUSES = {"requested", "under_review", "approved", "processing"}
TERMINAL_STATUSES = {"paid", "rejected", "cancelled"}

# Дозволені переходи для адміна.
_ADMIN_TRANSITIONS: dict[str, set] = {
    "requested":    {"under_review", "approved", "rejected"},
    "under_review": {"approved", "rejected"},
    "approved":     {"processing", "paid", "rejected"},
    "processing":   {"paid", "rejected"},
}

# Інвестор може скасувати лише поки заявка не пішла у роботу.
_INVESTOR_CANCELLABLE = {"requested", "under_review"}

# Які reasons ledger впливають на кеш-гаманець (БЕЗ investment_funding).
WALLET_CREDIT_REASONS = {"payout", "refund", "adjustment", "secondary_sale"}
WALLET_DEBIT_REASONS = {"withdrawal", "adjustment", "secondary_purchase"}
WALLET_LEDGER_REASONS = WALLET_CREDIT_REASONS | WALLET_DEBIT_REASONS

MIN_WITHDRAWAL_UAH = 1000.0


# ──────────────────────────────────────────────────────────────────────────────
# Output serializers
# ──────────────────────────────────────────────────────────────────────────────

def _wallet_out(doc: dict) -> dict:
    doc = dict(doc)
    for k in ("created_at", "updated_at"):
        if doc.get(k):
            doc[k] = _iso(doc[k])
    return _strip_mongo(doc)


def _withdrawal_out(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = WITHDRAWAL_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    for k in ("created_at", "updated_at", "paid_at", "rejected_at", "cancelled_at"):
        if doc.get(k) is not None:
            doc[k] = _iso(doc[k])
    if isinstance(doc.get("history"), list):
        doc["history"] = [{**h, "at": _iso(h.get("at"))} for h in doc["history"]]
    return _strip_mongo(doc)


def _txn_out(doc: dict) -> dict:
    """Ledger entry as a wallet transaction line."""
    doc = dict(doc)
    doc["reason_label"] = LEDGER_REASON_LABELS.get(doc.get("reason"), doc.get("reason"))
    doc["direction"] = "in" if doc.get("entry_type") == "credit" else "out"
    if doc.get("created_at"):
        doc["created_at"] = _iso(doc["created_at"])
    return _strip_mongo(doc)


# ──────────────────────────────────────────────────────────────────────────────
# Balance computation (single source of truth = ledger + reserved requests)
# ──────────────────────────────────────────────────────────────────────────────

async def _compute_balances(investor_id: str) -> dict:
    inflow = 0.0
    outflow = 0.0
    async for e in db.lumen_ledger_entries.find({
        "investor_id": investor_id,
        "reason": {"$in": list(WALLET_LEDGER_REASONS)},
    }):
        amt = float(e.get("amount_uah") or 0)
        if e.get("entry_type") == "credit":
            inflow += amt
        else:
            outflow += amt

    pending = 0.0
    async for w in db.lumen_withdrawal_requests.find({
        "investor_id": investor_id,
        "status": {"$in": list(RESERVED_STATUSES)},
    }):
        pending += float(w.get("amount_uah") or 0)

    settled = _round2(inflow - outflow)
    pending = _round2(pending)
    available = _round2(settled - pending)
    return {
        "total_in": _round2(inflow),
        "total_out": _round2(outflow),
        "settled_balance": settled,
        "pending_balance": pending,
        "available_balance": available,
    }


async def recompute_wallet(investor_id: str, currency: str = BASE_CURRENCY) -> dict:
    """Recompute and upsert the materialized wallet projection."""
    bal = await _compute_balances(investor_id)
    now = _now()
    set_doc = {
        "investor_id": investor_id,
        "currency": currency,
        "available_balance": bal["available_balance"],
        "pending_balance": bal["pending_balance"],
        "settled_balance": bal["settled_balance"],
        "total_in": bal["total_in"],
        "total_out": bal["total_out"],
        "updated_at": now,
    }
    await db.lumen_wallets.update_one(
        {"investor_id": investor_id, "currency": currency},
        {"$set": set_doc,
         "$setOnInsert": {"id": f"w-{uuid.uuid4().hex[:12]}", "created_at": now}},
        upsert=True,
    )
    w = await db.lumen_wallets.find_one({"investor_id": investor_id, "currency": currency})
    return _wallet_out(w)


async def get_wallet(investor_id: str, currency: str = BASE_CURRENCY) -> dict:
    """Always returns a fresh wallet (recomputed from ledger truth)."""
    return await recompute_wallet(investor_id, currency)


# ──────────────────────────────────────────────────────────────────────────────
# Withdrawal lifecycle
# ──────────────────────────────────────────────────────────────────────────────

async def create_withdrawal(
    investor_id: str, *, amount: float, currency: str,
    iban: str, bank_name: str, beneficiary_name: str,
    user: Optional[dict] = None,
) -> dict:
    currency = (currency or BASE_CURRENCY).upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Валюта не підтримується: {currency}")
    iban = (iban or "").strip()
    bank_name = (bank_name or "").strip()
    beneficiary_name = (beneficiary_name or "").strip()
    if not iban or not bank_name or not beneficiary_name:
        raise HTTPException(status_code=400,
                            detail="IBAN, банк і отримувач — обов'язкові поля")
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некоректна сума")
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Сума має бути більшою за 0")

    fx = _fx_rate_for(currency)
    amount_uah = _round2(amt * fx)
    if amount_uah < MIN_WITHDRAWAL_UAH:
        raise HTTPException(
            status_code=400,
            detail=f"Мінімальна сума виводу — {fmt_uah_as_usd(MIN_WITHDRAWAL_UAH)}")

    bal = await _compute_balances(investor_id)
    if amount_uah > bal["available_balance"] + 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Недостатньо коштів. Доступно: "
                   f"{fmt_uah_as_usd(bal['available_balance'])}")

    if user is None:
        user = await db.users.find_one({"user_id": investor_id}) or {}

    now = _now()
    doc = {
        "id": f"wd-{uuid.uuid4().hex[:12]}",
        "investor_id": investor_id,
        "investor_name": user.get("name") or user.get("full_name"),
        "investor_email": user.get("email"),
        "amount": _round2(amt),
        "currency": currency,
        "fx_rate": float(fx),
        "amount_uah": amount_uah,
        "iban": iban,
        "bank_name": bank_name,
        "beneficiary_name": beneficiary_name,
        "status": "requested",
        "admin_comment": None,
        "ledger_entry_id": None,
        "history": [{
            "status": "requested", "at": now, "by": investor_id,
            "comment": "Заявку на вивід створено",
        }],
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_withdrawal_requests.insert_one(dict(doc))
    await recompute_wallet(investor_id)
    await _notify(
        investor_id,
        "Заявку на вивід прийнято",
        f"Заявку на вивід {amt:,.0f} {currency} створено та поставлено в чергу "
        "на розгляд. Кошти зарезервовано.".replace(",", " "),
        event="withdrawal_requested",
    )
    return _withdrawal_out(doc)


async def cancel_withdrawal(investor_id: str, req_id: str) -> dict:
    w = await db.lumen_withdrawal_requests.find_one({"id": req_id})
    if not w:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    if w.get("investor_id") != investor_id:
        raise HTTPException(status_code=403, detail="Це не ваша заявка")
    if w["status"] not in _INVESTOR_CANCELLABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Заявку не можна скасувати (статус: "
                   f"{WITHDRAWAL_STATUS_LABELS.get(w['status'], w['status'])})")
    now = _now()
    await db.lumen_withdrawal_requests.update_one(
        {"id": req_id},
        {"$set": {"status": "cancelled", "cancelled_at": now, "updated_at": now},
         "$push": {"history": {"status": "cancelled", "at": now, "by": investor_id,
                               "comment": "Скасовано інвестором"}}},
    )
    await recompute_wallet(investor_id)
    updated = await db.lumen_withdrawal_requests.find_one({"id": req_id})
    return _withdrawal_out(updated)


async def admin_set_status(req_id: str, target: str, actor_id: str,
                           comment: Optional[str] = None) -> dict:
    if target not in WITHDRAWAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Невідомий статус: {target}")
    w = await db.lumen_withdrawal_requests.find_one({"id": req_id})
    if not w:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    cur = w["status"]
    if cur in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Заявка вже завершена (статус: "
                   f"{WITHDRAWAL_STATUS_LABELS.get(cur, cur)})")
    allowed = _ADMIN_TRANSITIONS.get(cur, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Неможливий перехід {WITHDRAWAL_STATUS_LABELS.get(cur, cur)} → "
                   f"{WITHDRAWAL_STATUS_LABELS.get(target, target)}")
    if target == "rejected" and not (comment or "").strip():
        raise HTTPException(status_code=400,
                            detail="Коментар обов'язковий при відхиленні")

    now = _now()
    set_fields: dict[str, Any] = {"status": target, "updated_at": now}
    if comment is not None and comment.strip():
        set_fields["admin_comment"] = comment.strip()
    if target == "rejected":
        set_fields["rejected_at"] = now
    if target == "paid":
        set_fields["paid_at"] = now

    ledger_id = None
    if target == "paid":
        # Реалізований вивід → final debit у ledger (єдина точка списання).
        ledger_id = await _ledger_append(
            entry_type="debit",
            reason="withdrawal",
            investor_id=w["investor_id"],
            asset_id=None,
            investment_id=None,
            payment_request_id=None,
            amount=w["amount"],
            currency=w["currency"],
            fx_rate=w["fx_rate"],
            amount_uah=w["amount_uah"],
            actor_id=actor_id,
            notes=f"Вивід коштів — заявка {w['id']}",
        )
        # Прив'язуємо заявку до ledger-проводки (для аудиту).
        await db.lumen_ledger_entries.update_one(
            {"id": ledger_id}, {"$set": {"withdrawal_request_id": w["id"]}})
        set_fields["ledger_entry_id"] = ledger_id

    hist_comment = (comment or "").strip() or (
        f"Статус → {WITHDRAWAL_STATUS_LABELS.get(target, target)}")
    await db.lumen_withdrawal_requests.update_one(
        {"id": req_id},
        {"$set": set_fields,
         "$push": {"history": {"status": target, "at": now, "by": actor_id,
                               "comment": hist_comment}}},
    )
    await recompute_wallet(w["investor_id"])

    # Сповіщення інвестору
    _notif_map = {
        "under_review": ("Вивід на розгляді", "Вашу заявку на вивід взято на розгляд комплаєнсом."),
        "approved":     ("Вивід схвалено", "Вашу заявку на вивід схвалено до виплати."),
        "processing":   ("Вивід виконується", "Виплату за вашою заявкою передано у роботу казначейства."),
        "paid":         ("Кошти виплачено", f"Виплату {w['amount']:,.0f} {w['currency']} за вашою заявкою виконано.".replace(",", " ")),
        "rejected":     ("Вивід відхилено", f"Вашу заявку на вивід відхилено. Причина: {(comment or '').strip()}. Кошти повернуто на баланс."),
    }
    if target in _notif_map:
        title, body = _notif_map[target]
        await _notify(w["investor_id"], title, body, event=f"withdrawal_{target}")

    updated = await db.lumen_withdrawal_requests.find_one({"id": req_id})
    out = _withdrawal_out(updated)
    if ledger_id:
        out["ledger_entry_id"] = ledger_id
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap: indexes + demo dividends seed (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_wallet_indexes() -> None:
    await db.lumen_wallets.create_index(
        [("investor_id", 1), ("currency", 1)], unique=True, name="wallet_investor_currency")
    await db.lumen_wallets.create_index("id", unique=True, sparse=True)
    await db.lumen_withdrawal_requests.create_index("id", unique=True)
    await db.lumen_withdrawal_requests.create_index(
        [("investor_id", 1), ("created_at", -1)])
    await db.lumen_withdrawal_requests.create_index("status")


async def seed_demo_dividends() -> dict:
    """Нараховує демо-дивіденди (payout credit) інвесторам з активними
    інвестиціями, щоб гаманець мав реальний баланс для виводу.

    Ідемпотентно: пропускає інвестора, у якого вже є будь-який payout-запис.
    Не є payout engine — це разовий сид історичних дивідендів.
    """
    investors: dict[str, list] = {}
    async for inv in db.lumen_investments.find({"status": "active"}):
        iid = inv.get("investor_id")
        if not iid:
            continue
        investors.setdefault(iid, []).append(inv)

    created = 0
    touched = 0
    for iid, invs in investors.items():
        already = await db.lumen_ledger_entries.find_one(
            {"investor_id": iid, "reason": "payout"})
        if already:
            continue
        for inv in invs:
            principal = float(inv.get("amount") or 0)
            if principal <= 0:
                continue
            div = _round2(principal * 0.10)  # 10% нарахованих дивідендів (демо)
            if div <= 0:
                continue
            await _ledger_append(
                entry_type="credit",
                reason="payout",
                investor_id=iid,
                asset_id=inv.get("asset_id"),
                investment_id=inv.get("id"),
                payment_request_id=None,
                amount=div,
                currency=BASE_CURRENCY,
                fx_rate=1.0,
                amount_uah=div,
                actor_id="system",
                notes="Нарахування дивідендів (демо-сид Sprint 7)",
            )
            created += 1
        await recompute_wallet(iid)
        touched += 1
    return {"investors_credited": touched, "dividend_entries": created}


async def bootstrap_wallets() -> dict:
    await ensure_wallet_indexes()
    res = await seed_demo_dividends()
    # Гарантуємо, що в кожного інвестора з активністю є wallet-проєкція.
    seen = set()
    async for e in db.lumen_ledger_entries.find({}, {"investor_id": 1}):
        iid = e.get("investor_id")
        if iid and iid not in seen:
            seen.add(iid)
            await recompute_wallet(iid)
    res["wallets_recomputed"] = len(seen)
    return res


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-wallet"])


# ---- Investor ----------------------------------------------------------------

@router.get("/investor/wallet")
async def my_wallet(user=Depends(get_current_user)):
    wallet = await get_wallet(user["id"])
    counts = {}
    for s in WITHDRAWAL_STATUSES:
        counts[s] = await db.lumen_withdrawal_requests.count_documents(
            {"investor_id": user["id"], "status": s})
    return {"wallet": wallet, "withdrawal_counts": counts,
            "min_withdrawal_uah": MIN_WITHDRAWAL_UAH,
            "currencies": SUPPORTED_CURRENCIES}


@router.get("/investor/wallet/transactions")
async def my_wallet_transactions(limit: int = 100, user=Depends(get_current_user)):
    """Повна історія руху коштів інвестора (усі ledger-проводки)."""
    items = []
    async for e in (db.lumen_ledger_entries
                    .find({"investor_id": user["id"]})
                    .sort("created_at", -1)
                    .limit(min(max(1, limit), 500))):
        items.append(_txn_out(e))
    return {"items": items, "total": len(items)}


@router.get("/investor/withdrawals")
async def my_withdrawals(status: Optional[str] = None, user=Depends(get_current_user)):
    q: dict[str, Any] = {"investor_id": user["id"]}
    if status:
        if status not in WITHDRAWAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["status"] = status
    items = []
    async for w in (db.lumen_withdrawal_requests.find(q)
                    .sort("created_at", -1).limit(500)):
        items.append(_withdrawal_out(w))
    return {"items": items, "total": len(items)}


class WithdrawalCreatePayload(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = BASE_CURRENCY
    iban: str
    bank_name: str
    beneficiary_name: str


@router.post("/investor/withdrawals")
async def create_my_withdrawal(payload: WithdrawalCreatePayload,
                               user=Depends(get_current_user),
                               _ev=Depends(__import__("email_verification").require_verified_email)):
    return await create_withdrawal(
        user["id"],
        amount=payload.amount,
        currency=payload.currency,
        iban=payload.iban,
        bank_name=payload.bank_name,
        beneficiary_name=payload.beneficiary_name,
        user=user,
    )


@router.post("/investor/withdrawals/{req_id}/cancel")
async def cancel_my_withdrawal(req_id: str, user=Depends(get_current_user)):
    return await cancel_withdrawal(user["id"], req_id)


# ---- Admin -------------------------------------------------------------------

@router.get("/admin/withdrawals")
async def admin_list_withdrawals(status: Optional[str] = None,
                                 _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        if status not in WITHDRAWAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["status"] = status
    items = []
    async for w in (db.lumen_withdrawal_requests.find(q)
                    .sort("created_at", -1).limit(1000)):
        items.append(_withdrawal_out(w))
    counts = {}
    for s in WITHDRAWAL_STATUSES:
        counts[s] = await db.lumen_withdrawal_requests.count_documents({"status": s})
    counts["all"] = await db.lumen_withdrawal_requests.count_documents({})
    # сума, що очікує виплати (резерв у роботі)
    pending_uah = 0.0
    async for w in db.lumen_withdrawal_requests.find(
            {"status": {"$in": list(RESERVED_STATUSES)}}):
        pending_uah += float(w.get("amount_uah") or 0)
    return {"items": items, "total": len(items), "counts": counts,
            "pending_uah": _round2(pending_uah)}


@router.get("/admin/withdrawals/{req_id}")
async def admin_withdrawal_detail(req_id: str, _=Depends(require_admin)):
    w = await db.lumen_withdrawal_requests.find_one({"id": req_id})
    if not w:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    out = _withdrawal_out(w)
    # гаманець інвестора + його ledger-історія
    wallet = await get_wallet(w["investor_id"])
    ledger = []
    async for e in (db.lumen_ledger_entries
                    .find({"investor_id": w["investor_id"]})
                    .sort("created_at", -1).limit(50)):
        ledger.append(_txn_out(e))
    return {"withdrawal": out, "wallet": wallet, "ledger_entries": ledger}


class AdminWithdrawalActionPayload(BaseModel):
    comment: Optional[str] = None


async def _audit_w(action: str, req_id: str, admin: dict, request: Request,
                   status: str, comment: Optional[str]) -> None:
    await write_audit(
        action=action, category="withdrawal",
        target_type="lumen_withdrawal_requests", target_id=req_id,
        actor=admin, request=request,
        summary=f"Withdrawal {req_id} -> {status}",
        meta={"comment": comment, "new_status": status},
    )


@router.post("/admin/withdrawals/{req_id}/review")
async def admin_review_withdrawal(req_id: str,
                                  payload: AdminWithdrawalActionPayload = None,
                                  request: Request = None,
                                  admin=Depends(require_admin)):
    res = await admin_set_status(req_id, "under_review", admin["id"],
                                 comment=(payload.comment if payload else None))
    await _audit_w("withdrawal.review", req_id, admin, request,
                   "under_review", (payload.comment if payload else None))
    return res


@router.post("/admin/withdrawals/{req_id}/approve")
async def admin_approve_withdrawal(req_id: str,
                                   payload: AdminWithdrawalActionPayload = None,
                                   request: Request = None,
                                   admin=Depends(require_admin)):
    res = await admin_set_status(req_id, "approved", admin["id"],
                                 comment=(payload.comment if payload else None))
    await _audit_w("withdrawal.approve", req_id, admin, request,
                   "approved", (payload.comment if payload else None))
    return res


@router.post("/admin/withdrawals/{req_id}/processing")
async def admin_processing_withdrawal(req_id: str,
                                      payload: AdminWithdrawalActionPayload = None,
                                      request: Request = None,
                                      admin=Depends(require_admin)):
    res = await admin_set_status(req_id, "processing", admin["id"],
                                 comment=(payload.comment if payload else None))
    await _audit_w("withdrawal.processing", req_id, admin, request,
                   "processing", (payload.comment if payload else None))
    return res


@router.post("/admin/withdrawals/{req_id}/paid")
async def admin_paid_withdrawal(req_id: str,
                                payload: AdminWithdrawalActionPayload = None,
                                request: Request = None,
                                admin=Depends(require_admin)):
    res = await admin_set_status(req_id, "paid", admin["id"],
                                 comment=(payload.comment if payload else None))
    await _audit_w("withdrawal.mark_paid", req_id, admin, request,
                   "paid", (payload.comment if payload else None))
    return res


@router.post("/admin/withdrawals/{req_id}/reject")
async def admin_reject_withdrawal(req_id: str,
                                  payload: AdminWithdrawalActionPayload,
                                  request: Request = None,
                                  admin=Depends(require_admin)):
    comment = (payload.comment or "").strip()
    res = await admin_set_status(req_id, "rejected", admin["id"], comment=comment)
    await _audit_w("withdrawal.reject", req_id, admin, request, "rejected", comment)
    return res


__all__ = ["router", "bootstrap_wallets", "ensure_wallet_indexes",
           "seed_demo_dividends", "get_wallet", "recompute_wallet"]
