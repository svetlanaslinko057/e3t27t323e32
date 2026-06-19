"""
LUMEN Investment Core — Sprint 2.

Implements the four engines on top of the Sprint 1 domain (schemas + indexes +
repositories), strictly WITHOUT payments / KYC / contracts / wallets /
withdrawals / payouts / crypto (those are Sprints 3-7).

Engines
=======
1. Investor Intent Engine
       POST   /api/investor/intents                 — submit intent
       GET    /api/investor/intents                 — list my intents
       GET    /api/admin/intents?status=...         — admin list
       POST   /api/admin/intents/{id}/approve       — approve → investment + ownership
       POST   /api/admin/intents/{id}/reject        — reject with reason

2. Investment Engine
       Investment is created ONLY through intent approval (no direct create
       endpoint by design — Sprint 2 scope). Lifecycle statuses are recorded
       in an append-only `history` array on each investment document.
       GET    /api/investor/investments/{id}        — investment detail + history

3. Ownership Engine
       On approve the chain  intent → investment → ownership  runs atomically
       (best-effort sequential writes; Mongo standalone has no multi-doc tx).
       Ownership registry: one document per (investor, asset), units
       accumulate, ownership_percent recomputed from the asset target.
       GET    /api/investor/ownerships              — my ownership registry

4. Asset Funding Progress
       asset.raised_amount (+ legacy mirror `raised`) and investors_count are
       recomputed automatically on every approved investment. Round
       raised_amount is updated when the intent references a round.

Units model (Sprint 2): 1 unit == 1 UAH of confirmed investment.
ownership_percent = investor_active_amount / asset.target_amount * 100.

Collections: canonical Sprint 1 set — lumen_investor_intents,
lumen_investments, lumen_ownerships (+ lumen_assets, lumen_investment_rounds).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Reuse auth + db wiring from the lumen router (cookie session auth)
from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso, lr2_perm as _lr2_perm
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer


# ──────────────────────────────────────────────────────────────────────────────
# Labels (UA)
# ──────────────────────────────────────────────────────────────────────────────

INTENT_STATUS_LABELS = {
    "submitted":    "подано",
    "under_review": "на розгляді",
    "approved":     "підтверджено",
    "rejected":     "відхилено",
    "expired":      "прострочено",
    "converted":    "конвертовано",
    "cancelled":    "скасовано",
}

INVESTMENT_STATUS_LABELS = {
    "pending_payment":  "очікує оплату",
    "kyc_pending":      "очікує верифікації (KYC)",
    "contract_pending": "очікує підписання договору",
    "awaiting_payment": "очікує оплату",
    "active":           "активна",
    "matured":          "завершена",
    "refunded":         "повернена",
    "cancelled":        "скасована",
}

# Intent statuses an admin can still act on
_ACTIONABLE_INTENT_STATUSES = {"submitted", "under_review"}


def _intent_with_labels(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = INTENT_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    return _strip_mongo(doc)


def _investment_with_labels(doc: dict) -> dict:
    doc = dict(doc)
    doc["status_label"] = INVESTMENT_STATUS_LABELS.get(doc.get("status"), doc.get("status"))
    if isinstance(doc.get("history"), list):
        doc["history"] = [
            {**h, "at": _iso(h.get("at"))} for h in doc["history"]
        ]
    return _strip_mongo(doc)


# ──────────────────────────────────────────────────────────────────────────────
# Engine internals
# ──────────────────────────────────────────────────────────────────────────────

def _asset_target(asset: dict) -> float:
    """Canonical raise target with legacy fallback."""
    return float(asset.get("target_amount") or asset.get("round_target") or 0)


async def _recompute_asset_funding(asset_id: str) -> dict:
    """Asset Funding Progress engine.

    Recomputes raised_amount + investors_count from ACTIVE investments and
    writes both canonical and legacy mirror keys used by the web frontend.
    """
    raised = 0.0
    investor_ids: set[str] = set()
    async for inv in db.lumen_investments.find(
        {"asset_id": asset_id, "status": "active"},
        {"amount": 1, "invested_amount": 1, "investor_id": 1},
    ):
        raised += float(inv.get("amount") or inv.get("invested_amount") or 0)
        if inv.get("investor_id"):
            investor_ids.add(inv["investor_id"])
    await db.lumen_assets.update_one(
        {"id": asset_id},
        {"$set": {
            "raised_amount": raised,
            "raised": raised,                 # legacy mirror (web reads `raised`)
            "investors_count": len(investor_ids),
            "updated_at": _now(),
        }},
    )
    return {"raised_amount": raised, "investors_count": len(investor_ids)}


async def _upsert_ownership(investor_id: str, asset_id: str,
                            investment_id: str) -> dict:
    """Ownership Engine.

    Recomputes the (investor, asset) ownership row from ALL active
    investments — idempotent and self-healing (re-running it after any
    investment change produces the same registry state).
    """
    total_amount = 0.0
    async for inv in db.lumen_investments.find(
        {"asset_id": asset_id, "investor_id": investor_id, "status": "active"},
        {"amount": 1, "invested_amount": 1},
    ):
        total_amount += float(inv.get("amount") or inv.get("invested_amount") or 0)

    asset = await db.lumen_assets.find_one({"id": asset_id}) or {}
    target = _asset_target(asset)
    percent = round(total_amount / target * 100, 4) if target else 0.0
    units = total_amount  # 1 unit == 1 UAH (Sprint 2 model)

    existing = await db.lumen_ownerships.find_one(
        {"investor_id": investor_id, "asset_id": asset_id}
    )
    now = _now()
    if existing:
        await db.lumen_ownerships.update_one(
            {"id": existing["id"]},
            {"$set": {
                "units": units,
                "ownership_percent": percent,
                "investment_id": investment_id,
                "updated_at": now,
            }},
        )
        own_id = existing["id"]
    else:
        own_id = str(uuid.uuid4())
        await db.lumen_ownerships.insert_one({
            "id": own_id,
            "investor_id": investor_id,
            "asset_id": asset_id,
            "investment_id": investment_id,
            "units": units,
            "ownership_percent": percent,
            "created_at": now,
            "updated_at": now,
        })
    return {"id": own_id, "units": units, "ownership_percent": percent}


async def _update_round_progress(round_id: Optional[str]) -> None:
    if not round_id:
        return
    raised = 0.0
    async for inv in db.lumen_investments.find(
        {"round_id": round_id, "status": "active"}, {"amount": 1}
    ):
        raised += float(inv.get("amount") or 0)
    await db.lumen_investment_rounds.update_one(
        {"id": round_id},
        {"$set": {"raised_amount": raised, "updated_at": _now()}},
    )


async def _notify(investor_id: str, title: str, body: str,
                  channel: str = "asset_update") -> None:
    """Sprint 12: channel-aware. Honors lumen_notification_preferences when
    available; falls back to default-on. Unknown channels are always allowed."""
    try:
        from lumen_notification_prefs import is_allowed
        if not await is_allowed(investor_id, channel, "in_app"):
            return
    except Exception:
        pass
    await db.lumen_notifications.insert_one({
        "id": f"n-{uuid.uuid4().hex[:10]}",
        "investor_id": investor_id,
        "title": title,
        "body": body,
        "channel": channel,
        "read": False,
        "created_at": _now(),
    })


async def _investor_kyc_approved(investor_id: str) -> bool:
    """Sprint 3: KYC gate. Canonical source is lumen_investor_profiles with a
    legacy fallback to users.kyc_status (pre-Sprint-3 mirror)."""
    prof = await db.lumen_investor_profiles.find_one(
        {"user_id": investor_id}, {"kyc_status": 1}
    )
    if prof:
        return prof.get("kyc_status") == "approved"
    user = await db.users.find_one({"user_id": investor_id}, {"kyc_status": 1}) or {}
    return user.get("kyc_status") == "approved"


async def _contract_signed(investment: dict) -> bool:
    """Sprint 4: legal gate. The investment's contract must be signed."""
    contract_id = investment.get("contract_id")
    if not contract_id:
        return False
    c = await db.lumen_contracts.find_one({"id": contract_id}, {"status": 1})
    return bool(c and c.get("status") == "signed")


async def activate_ready_investments(investor_id: str,
                                     actor_id: str = "system") -> dict:
    """Sprint 6 activation gate — investments NO LONGER become `active` here.

    Lifecycle now is:

        kyc_pending      + KYC ok                → contract_pending
        contract_pending + contract signed       → awaiting_payment (via
                                                   lumen_payments.create_payment_request_for_investment)
        awaiting_payment + admin confirms        → active (in lumen_payments.confirm_payment_request)

    This function only handles the kyc_pending → contract_pending transition.
    The contract_pending → awaiting_payment transition is delegated to
    `lumen_payments.open_payment_requests_for_investor` (called by the
    contract.sign hook and the KYC approval hook).

    Returns {"activated": 0, "moved_to_contract": m} for backward compatibility.
    Ownership / funding are NOT recomputed here (Sprint 6: only on confirmed payment).
    """
    kyc_ok = await _investor_kyc_approved(investor_id)
    moved = 0
    now = _now()
    if not kyc_ok:
        return {"activated": 0, "moved_to_contract": 0}

    async for inv in db.lumen_investments.find(
        {"investor_id": investor_id, "status": "kyc_pending"}
    ):
        await db.lumen_investments.update_one(
            {"id": inv["id"]},
            {"$set": {"status": "contract_pending", "updated_at": now},
             "$push": {"history": {
                 "status": "contract_pending", "at": now, "by": actor_id,
                 "comment": "KYC підтверджено — очікує підписання договору",
             }}},
        )
        moved += 1
    return {"activated": 0, "moved_to_contract": moved}


async def activate_kyc_pending_investments(investor_id: str,
                                           actor_id: str = "system-kyc") -> int:
    """Backward-compatible wrapper (Sprint 3 API).

    Sprint 6 lifecycle:
        kyc_pending      + KYC ok                → contract_pending
        contract_pending + signed                → awaiting_payment (payment_request opened)
        (only admin confirm → active)

    Returns the number of payment_requests OPENED (was: activated investments).
    Old name preserved so lumen_kyc.py keeps working.
    """
    res = await activate_ready_investments(investor_id, actor_id=actor_id)
    from lumen_payments import open_payment_requests_for_investor
    pay = await open_payment_requests_for_investor(investor_id, actor_id=actor_id)
    return int(pay.get("opened", 0))


async def create_intent(user: dict, asset_id: str, amount: float,
                        round_id: Optional[str] = None,
                        note: Optional[str] = None) -> dict:
    """Shared intent creation (used by the canonical endpoint AND the legacy
    POST /api/investor/intent alias)."""
    # Tier-B compliance gate: a sanction-blocked investor cannot fund.
    try:
        import lumen_compliance_screening as _csc
        await _csc.screen_on_funding(user["id"], float(amount))
        await _csc.assert_not_blocked(user["id"])
    except HTTPException:
        raise
    except Exception:
        import logging as _l
        _l.getLogger("lumen.investment").warning("compliance gate check failed (soft-allow)", exc_info=True)
    asset = await db.lumen_assets.find_one({"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    if asset.get("status") != "open":
        raise HTTPException(status_code=400, detail="Раунд за цим об'єктом не відкрито")
    min_ticket = float(asset.get("min_ticket") or 0)
    if amount < min_ticket:
        raise HTTPException(status_code=400, detail=f"Мінімальна сума: {fmt_uah_as_usd(min_ticket)}")
    if round_id:
        rnd = await db.lumen_investment_rounds.find_one({"id": round_id})
        if not rnd or rnd.get("asset_id") != asset_id:
            raise HTTPException(status_code=404, detail="Раунд не знайдено")
        if rnd.get("status") not in ("open", "scheduled"):
            raise HTTPException(status_code=400, detail="Раунд закрито")
    else:
        # Attach the open round automatically when the asset has exactly one
        rnd = await db.lumen_investment_rounds.find_one(
            {"asset_id": asset_id, "status": "open"}
        )
        round_id = rnd["id"] if rnd else None

    now = _now()
    intent_id = str(uuid.uuid4())
    doc = {
        "id": intent_id,
        "asset_id": asset_id,
        "round_id": round_id,
        "investor_id": user["id"],
        # display denormalisation (kept in sync at write-time only)
        "investor_email": user.get("email"),
        "investor_name": user.get("name"),
        "asset_title": asset.get("title"),
        "amount": float(amount),
        "status": "submitted",
        "note": note,
        "admin_note": None,
        "submitted_at": now,
        "reviewed_at": None,
        "reviewer_id": None,
        "converted_investment_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_investor_intents.insert_one(doc)
    await _notify(
        user["id"],
        "Отримали ваш намір інвестувати",
        f"Заявка на {fmt_uah_as_usd(amount)} у «{asset.get('title')}» подана. "
        "Після перевірки ви отримаєте підтвердження.".replace(",", " "),
    )
    return _intent_with_labels(doc)


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-investment-core"])


# ---- Backfill / bootstrap (idempotent, runs at startup) ----------------------

@router.on_event("startup")
async def _sprint2_backfill():
    """Canonicalise legacy seed data so the engines run on real registry state.

    1. Investments: ensure canonical `amount`, `units`, `created_at`.
    2. Rounds: create «Раунд I» per asset when the registry is empty.
    3. Ownerships: rebuild from active investments when registry is empty.
    4. Assets: mirror raised -> raised_amount + funding recompute.
    """
    try:
        # 1. investments canonical fields
        async for inv in db.lumen_investments.find({"amount": {"$exists": False}}):
            amount = float(inv.get("invested_amount") or 0)
            await db.lumen_investments.update_one(
                {"id": inv["id"]},
                {"$set": {
                    "amount": amount,
                    "units": amount,
                    "created_at": inv.get("invested_at") or _now(),
                    "updated_at": _now(),
                    "history": inv.get("history") or [
                        {"status": "active", "at": inv.get("invested_at") or _now(),
                         "by": "system-backfill"}
                    ],
                }},
            )

        # 2. rounds registry
        if await db.lumen_investment_rounds.count_documents({}) == 0:
            async for asset in db.lumen_assets.find({}):
                now = _now()
                await db.lumen_investment_rounds.insert_one({
                    "id": str(uuid.uuid4()),
                    "asset_id": asset["id"],
                    "round_number": 1,
                    "round_name": "Раунд I",
                    "status": "open" if asset.get("status") == "open" else "scheduled",
                    "target_amount": _asset_target(asset),
                    "raised_amount": float(asset.get("raised") or 0),
                    "minimum_ticket": float(asset.get("min_ticket") or 0),
                    "max_ticket": None,
                    "open_at": asset.get("created_at") or now,
                    "close_at": asset.get("round_deadline"),
                    "created_at": now,
                    "updated_at": now,
                })

        # 3. ownership registry
        if await db.lumen_ownerships.count_documents({}) == 0:
            pairs: set[tuple[str, str]] = set()
            async for inv in db.lumen_investments.find({"status": "active"}):
                if inv.get("investor_id") and inv.get("asset_id"):
                    pairs.add((inv["investor_id"], inv["asset_id"]))
            for investor_id, asset_id in pairs:
                last = await db.lumen_investments.find_one(
                    {"investor_id": investor_id, "asset_id": asset_id, "status": "active"},
                    sort=[("invested_at", -1)],
                )
                await _upsert_ownership(investor_id, asset_id,
                                        (last or {}).get("id"))

        # 4. asset funding mirrors (only for assets that have investments)
        asset_ids = await db.lumen_investments.distinct("asset_id", {"status": "active"})
        for aid in asset_ids:
            await _recompute_asset_funding(aid)
        # assets without investments: just mirror legacy raised -> raised_amount
        await db.lumen_assets.update_many(
            {"raised_amount": {"$exists": False}},
            [{"$set": {"raised_amount": {"$ifNull": ["$raised", 0]}}}],
        )
    except Exception:  # pragma: no cover — never block boot
        import logging
        logging.getLogger("lumen.sprint2").exception("Sprint 2 backfill failed")


# ---- 1. Investor Intent Engine ------------------------------------------------

class IntentCreatePayload(BaseModel):
    asset_id: str
    amount: float = Field(gt=0)
    round_id: Optional[str] = None
    note: Optional[str] = None


@router.post("/investor/intents")
async def submit_intent(payload: IntentCreatePayload, user=Depends(get_current_user),
                         _ev=Depends(__import__("email_verification").require_verified_email),
                         _perm=Depends(_lr2_perm("investment", "write"))):
    return await create_intent(user, payload.asset_id, payload.amount,
                               payload.round_id, payload.note)


@router.get("/investor/intents")
async def my_intents(status: Optional[str] = None, user=Depends(get_current_user)):
    q: dict[str, Any] = {"investor_id": user["id"]}
    if status:
        q["status"] = status
    items = []
    async for it in db.lumen_investor_intents.find(q).sort("submitted_at", -1).limit(200):
        items.append(_intent_with_labels(it))
    return {"items": items, "total": len(items)}


@router.get("/admin/intents")
async def admin_intents(status: Optional[str] = None, asset_id: Optional[str] = None,
                        _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    async for it in db.lumen_investor_intents.find(q).sort("submitted_at", -1).limit(500):
        items.append(_intent_with_labels(it))
    counts: dict[str, int] = {}
    for s in INTENT_STATUS_LABELS:
        counts[s] = await db.lumen_investor_intents.count_documents({"status": s})
    return {"items": items, "total": len(items), "counts": counts}


class IntentDecisionPayload(BaseModel):
    note: Optional[str] = None


@router.post("/admin/intents/{intent_id}/approve")
async def approve_intent(intent_id: str, payload: IntentDecisionPayload = None,
                         admin=Depends(require_admin),
                         _perm=Depends(_lr2_perm("investment", "approve"))):
    """Approve chain: intent → investment (active) → ownership → funding."""
    intent = await db.lumen_investor_intents.find_one({"id": intent_id})
    if not intent:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    if intent.get("status") not in _ACTIONABLE_INTENT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Заявка вже оброблена (статус: {intent.get('status')})",
        )
    asset = await db.lumen_assets.find_one({"id": intent["asset_id"]})
    if not asset:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")

    now = _now()
    amount = float(intent["amount"])
    target = _asset_target(asset)

    # Sprint 4 legal gate (поверх Sprint 3 soft-mode KYC gate):
    #   активація інвестиції можлива ЛИШЕ коли KYC approved ТА договір підписано.
    #   KYC approved      → investment `contract_pending` (очікує підпис)
    #   KYC not approved  → investment `kyc_pending`
    # Договір генерується одразу після approve у будь-якому випадку.
    kyc_ok = await _investor_kyc_approved(intent["investor_id"])
    inv_status = "contract_pending" if kyc_ok else "kyc_pending"

    # 2. Investment Engine — create investment (payments are Sprint 5;
    #    activation now happens via the contract-sign / KYC-approve chain)
    investment_id = str(uuid.uuid4())
    ownership_percent = round(amount / target * 100, 4) if target else 0.0
    investment_doc = {
        "id": investment_id,
        "asset_id": intent["asset_id"],
        "round_id": intent.get("round_id"),
        "investor_id": intent["investor_id"],
        "intent_id": intent_id,
        "amount": amount,
        "units": amount,                       # 1 unit == 1 UAH
        "ownership_percent": ownership_percent,
        "status": inv_status,
        "payment_reference": None,
        "contract_id": None,
        "invested_at": None,
        "matured_at": None,
        "history": [
            {"status": inv_status, "at": now, "by": admin["id"],
             "comment": ("Заявку підтверджено — очікує підписання договору"
                         if kyc_ok else
                         "Заявку підтверджено — очікує верифікації інвестора (KYC)")},
        ],
        # display denormalisation for the web cabinet
        "asset_title": asset.get("title"),
        "asset_location": asset.get("location"),
        "round_label": "Раунд I",
        "invested_amount": amount,             # legacy mirror
        "share_percent": ownership_percent,    # legacy mirror
        "current_yield": float(asset.get("target_yield") or 0),
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_investments.insert_one(investment_doc)

    # Sprint 4: generate the legal contract right after approve
    from lumen_contracts import generate_contract_for_investment
    contract = await generate_contract_for_investment(investment_doc)
    if contract:
        investment_doc["contract_id"] = contract["id"]

    # 3-4. Ownership + Funding engines count ONLY active investments —
    # nothing is recomputed until both gates (KYC + contract) are passed
    ownership = None
    funding = None

    # 1. close the intent
    await db.lumen_investor_intents.update_one(
        {"id": intent_id},
        {"$set": {
            "status": "converted",
            "reviewed_at": now,
            "reviewer_id": admin["id"],
            "admin_note": (payload.note if payload else None),
            "converted_investment_id": investment_id,
            "updated_at": now,
        }},
    )

    if kyc_ok:
        await _notify(
            intent["investor_id"],
            "Заявку підтверджено — підпишіть договір",
            f"Інвестицію {fmt_uah_as_usd(amount)} у «{asset.get('title')}» зарезервовано. "
            f"Підпишіть договір {contract.get('number') if contract else ''} у розділі "
            "«Договори», щоб її активувати.".replace(",", " "),
        )
    else:
        await _notify(
            intent["investor_id"],
            "Заявку підтверджено — потрібна верифікація",
            f"Інвестицію {fmt_uah_as_usd(amount)} у «{asset.get('title')}» зарезервовано. "
            "Пройдіть верифікацію (KYC) у профілі та підпишіть договір, "
            "щоб її активувати.".replace(",", " "),
        )

    return {
        "intent_id": intent_id,
        "status": "converted",
        "investment": _investment_with_labels(investment_doc),
        "ownership": ownership,
        "asset_funding": funding,
        "kyc_required": not kyc_ok,
        "contract_required": True,
        "contract": {
            "id": contract.get("id"),
            "number": contract.get("number"),
            "status": contract.get("status"),
            "pdf_url": contract.get("pdf_url"),
        } if contract else None,
    }


@router.post("/admin/intents/{intent_id}/reject")
async def reject_intent(intent_id: str, payload: IntentDecisionPayload = None,
                        admin=Depends(require_admin),
                        _perm=Depends(_lr2_perm("investment", "approve"))):
    intent = await db.lumen_investor_intents.find_one({"id": intent_id})
    if not intent:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    if intent.get("status") not in _ACTIONABLE_INTENT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Заявка вже оброблена (статус: {intent.get('status')})",
        )
    now = _now()
    await db.lumen_investor_intents.update_one(
        {"id": intent_id},
        {"$set": {
            "status": "rejected",
            "reviewed_at": now,
            "reviewer_id": admin["id"],
            "admin_note": (payload.note if payload else None),
            "updated_at": now,
        }},
    )
    await _notify(
        intent["investor_id"],
        "Заявку відхилено",
        (payload.note if payload and payload.note
         else f"На жаль, заявку щодо «{intent.get('asset_title')}» відхилено. "
              "Зв'яжіться з нами для деталей."),
    )
    return {"intent_id": intent_id, "status": "rejected"}


# ---- 2. Investment Engine (read endpoints) ------------------------------------

@router.get("/investor/investments/{investment_id}")
async def investment_detail(investment_id: str, user=Depends(get_current_user)):
    inv = await db.lumen_investments.find_one({"id": investment_id})
    if not inv:
        raise HTTPException(status_code=404, detail="Інвестицію не знайдено")
    if inv.get("investor_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Немає доступу")
    return _investment_with_labels(inv)


# ---- 3. Ownership Engine (read endpoints) -------------------------------------

@router.get("/investor/ownerships")
async def my_ownerships(user=Depends(get_current_user)):
    items = []
    async for own in db.lumen_ownerships.find({"investor_id": user["id"]}).sort("updated_at", -1):
        own = _strip_mongo(own)
        asset = await db.lumen_assets.find_one({"id": own["asset_id"]}) or {}
        own["asset_title"] = asset.get("title")
        own["asset_location"] = asset.get("location")
        own["asset_status"] = asset.get("status")
        own["asset_target_yield"] = asset.get("target_yield")
        items.append(own)
    return {"items": items, "total": len(items)}


@router.get("/admin/ownerships")
async def admin_ownerships(asset_id: Optional[str] = None, _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if asset_id:
        q["asset_id"] = asset_id
    items = []
    user_cache: dict[str, dict] = {}
    async for own in db.lumen_ownerships.find(q).sort("updated_at", -1).limit(500):
        own = _strip_mongo(own)
        uid = own.get("investor_id")
        if uid and uid not in user_cache:
            u = await db.users.find_one({"user_id": uid}) or await db.users.find_one({"id": uid}) or {}
            user_cache[uid] = u
        u = user_cache.get(uid, {})
        own["investor_name"] = u.get("name")
        own["investor_email"] = u.get("email")
        asset = await db.lumen_assets.find_one({"id": own["asset_id"]}) or {}
        own["asset_title"] = asset.get("title")
        items.append(own)
    return {"items": items, "total": len(items)}
