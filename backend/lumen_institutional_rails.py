"""
LUMEN 2.0 — Phase H1 — Institutional Banking Rails (SEPA + SWIFT)
==================================================================

For institutional LPs and family-office tickets that move money over the
real banking system rather than through retail card processors.

Design principles (consistent with the rest of LUMEN):

* Vendor-neutral DTOs.  Provider integration (Banking Circle / Wise / direct
  bank) is the next layer below — Phase H1 ships the **instruction +
  reconciliation engine** that any provider can plug into.
* Authority-of-record is `money_ledger`.  Rail status events emit ledger
  postings on `confirmed` / `returned` / `failed`.
* Idempotent — every transfer has a client-provided `reference` (Lumen UEID)
  that is unique within (institution × rail × direction).
* LR2.7 gated — all write endpoints go through the permission engine so
  `compliance_profile`, `lp_commitment`, `distribution`, `fund` roles
  determine who can do what.
* Audit — every state change writes to `lumen_audit_log` and to the
  per-transfer `events[]` array.

Collections:
    lumen_institutional_transfers      — header (one row per transfer)
    lumen_institutional_transfer_events — append-only state log

Lifecycle:
    draft   ─submit→ pending  ─admin confirm/init→ initiated
                                      │
                                      ├──→ sent
                                      ├──→ confirmed   (terminal — settled)
                                      ├──→ failed      (terminal)
                                      ├──→ returned    (terminal)
                                      └──→ cancelled   (terminal)

Endpoints (prefix /api):
    POST   /lumen/institutional/rails/sepa/transfers
    POST   /lumen/institutional/rails/swift/transfers
    GET    /lumen/institutional/rails/transfers
    GET    /lumen/institutional/rails/transfers/{transfer_id}
    POST   /lumen/institutional/rails/transfers/{transfer_id}/cancel
    GET    /admin/lumen/institutional/rails/transfers
    POST   /admin/lumen/institutional/rails/transfers/{transfer_id}/confirm
    POST   /admin/lumen/institutional/rails/transfers/{transfer_id}/reject
    POST   /admin/lumen/institutional/rails/transfers/{transfer_id}/reconcile
    GET    /admin/lumen/institutional/rails/stats
    GET    /lumen/institutional/rails/iban/validate
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from lumen_api import (db, get_current_user, require_admin,
                       _strip_mongo, _now, _iso, lr2_perm as _lr2_perm)

logger = logging.getLogger("lumen.institutional_rails")

# ════════════════════════════════════════════════════════════════════════════
# Collections + constants
# ════════════════════════════════════════════════════════════════════════════
TRANSFERS = "lumen_institutional_transfers"
EVENTS = "lumen_institutional_transfer_events"

RAIL_SEPA = "sepa"
RAIL_SEPA_INSTANT = "sepa_instant"
RAIL_SWIFT = "swift"
RAILS = (RAIL_SEPA, RAIL_SEPA_INSTANT, RAIL_SWIFT)

DIR_INBOUND = "inbound"     # money INTO Lumen / fund
DIR_OUTBOUND = "outbound"   # money OUT to investor

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending"
STATUS_INITIATED = "initiated"
STATUS_SENT = "sent"
STATUS_CONFIRMED = "confirmed"
STATUS_FAILED = "failed"
STATUS_RETURNED = "returned"
STATUS_CANCELLED = "cancelled"
STATUSES = (STATUS_DRAFT, STATUS_PENDING, STATUS_INITIATED, STATUS_SENT,
            STATUS_CONFIRMED, STATUS_FAILED, STATUS_RETURNED, STATUS_CANCELLED)

TERMINAL = {STATUS_CONFIRMED, STATUS_FAILED, STATUS_RETURNED, STATUS_CANCELLED}

CHARGES_OUR = "OUR"   # sender pays all charges
CHARGES_SHA = "SHA"   # shared
CHARGES_BEN = "BEN"   # beneficiary pays

# SEPA Direct Debit is EUR-only and only across SEPA zone (33 countries).
SEPA_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IS", "IE", "IT", "LV", "LI", "LT", "LU", "MT", "MC", "NL", "NO",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE", "CH", "GB", "SM", "VA", "AD",
}
SEPA_CURRENCY = "EUR"

# Default minimums by rail to discourage retail usage of an institutional rail
MIN_AMOUNT_EUR = float(os.environ.get("LUMEN_RAILS_MIN_SEPA_EUR", "1000"))
MIN_AMOUNT_USD = float(os.environ.get("LUMEN_RAILS_MIN_SWIFT_USD", "10000"))

# ════════════════════════════════════════════════════════════════════════════
# IBAN / BIC validation (ISO 13616 + ISO 9362)
# ════════════════════════════════════════════════════════════════════════════
_IBAN_RX = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}$")
_BIC_RX = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def normalize_iban(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").upper())


def normalize_bic(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").upper())


def _iban_mod97(iban: str) -> bool:
    """ISO 13616 IBAN check-digit verification."""
    rearranged = iban[4:] + iban[:4]
    # Letters → digits: A=10, B=11, ..., Z=35
    converted = "".join(
        ch if ch.isdigit() else str(ord(ch) - 55) for ch in rearranged
    )
    try:
        return int(converted) % 97 == 1
    except Exception:
        return False


def validate_iban(raw: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Returns (ok, country_code, error)."""
    iban = normalize_iban(raw)
    if not iban:
        return False, None, "IBAN порожній"
    if not (15 <= len(iban) <= 34):
        return False, None, f"Невірна довжина IBAN ({len(iban)} символів)"
    if not _IBAN_RX.match(iban):
        return False, None, "IBAN містить недопустимі символи"
    if not _iban_mod97(iban):
        return False, iban[:2], "Контрольна сума IBAN не сходиться (mod-97)"
    return True, iban[:2], None


def validate_bic(raw: str) -> tuple[bool, Optional[str]]:
    bic = normalize_bic(raw)
    if not bic:
        return False, "BIC порожній"
    if len(bic) not in (8, 11):
        return False, f"BIC має бути 8 або 11 символів (отримано {len(bic)})"
    if not _BIC_RX.match(bic):
        return False, "BIC не відповідає ISO 9362"
    return True, None


def is_sepa_eligible(iban: str) -> tuple[bool, Optional[str]]:
    ok, cc, err = validate_iban(iban)
    if not ok:
        return False, err
    if cc not in SEPA_COUNTRIES:
        return False, f"Країна '{cc}' не входить в SEPA-зону"
    return True, None


# ════════════════════════════════════════════════════════════════════════════
# Pydantic payloads
# ════════════════════════════════════════════════════════════════════════════

class _RailsBase(BaseModel):
    direction: str = Field(..., description="inbound | outbound")
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    beneficiary_name: str = Field(..., min_length=2, max_length=140)
    beneficiary_iban: str = Field(..., min_length=15, max_length=34)
    reference: Optional[str] = Field(None, max_length=140,
                                       description="Lumen UEID — unique idempotency key")
    purpose: Optional[str] = Field(None, max_length=240)
    fund_id: Optional[str] = None
    commitment_id: Optional[str] = None
    investor_id: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("direction")
    @classmethod
    def _v_dir(cls, v):
        if v not in (DIR_INBOUND, DIR_OUTBOUND):
            raise ValueError("direction must be 'inbound' or 'outbound'")
        return v

    @field_validator("currency")
    @classmethod
    def _v_cur(cls, v):
        return v.upper()


class SepaTransferIn(_RailsBase):
    instant: bool = Field(False, description="True for SEPA-Instant (SCT-Inst). False = standard SCT.")


class SwiftTransferIn(_RailsBase):
    beneficiary_bic: str = Field(..., min_length=8, max_length=11)
    intermediary_bic: Optional[str] = Field(None, min_length=8, max_length=11)
    charges: str = Field("SHA", description="OUR | SHA | BEN")

    @field_validator("charges")
    @classmethod
    def _v_charges(cls, v):
        v = (v or "SHA").upper()
        if v not in (CHARGES_OUR, CHARGES_SHA, CHARGES_BEN):
            raise ValueError("charges must be OUR/SHA/BEN")
        return v


class ConfirmIn(BaseModel):
    provider_ref: Optional[str] = Field(None,
        description="External payment/ref ID from the bank statement.")
    settled_at: Optional[str] = None
    note: Optional[str] = None


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=240)


class ReconcileIn(BaseModel):
    bank_statement_ref: str = Field(..., min_length=2, max_length=240)
    amount_observed: float = Field(..., gt=0)
    currency_observed: str = Field(..., min_length=3, max_length=3)
    settled_at: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════════
def _uid(user) -> str:
    if not user:
        return "anonymous"
    return user.get("user_id") or user.get("id") or "unknown"


def _new_ref(rail: str) -> str:
    return f"LUMEN-{rail.upper()}-{uuid.uuid4().hex[:14].upper()}"


def _new_id() -> str:
    return f"itx-{uuid.uuid4().hex[:14]}"


def _strip(doc):
    return _strip_mongo(doc) if doc else doc


async def _event(transfer_id: str, *, status: str, actor: str,
                 message: Optional[str] = None,
                 meta: Optional[dict] = None) -> dict:
    ev = {
        "id": f"itxev-{uuid.uuid4().hex[:14]}",
        "transfer_id": transfer_id,
        "status": status,
        "actor": actor,
        "message": message,
        "meta": meta or {},
        "at": _now(),
    }
    await db[EVENTS].insert_one(ev)
    return _strip(ev)


async def _audit(action: str, *, actor, target_id: str,
                  request: Optional[Request], summary: str,
                  meta: Optional[dict] = None) -> None:
    try:
        from lumen_audit import write_audit
        await write_audit(action=action, category="payment",
                           target_type=TRANSFERS, target_id=target_id,
                           actor=actor, request=request,
                           summary=summary, meta=meta or {})
    except Exception:
        # Soft — audit log must never crash a money flow
        logger.debug("audit write failed for %s", action, exc_info=True)


async def _is_terminal(transfer_id: str) -> bool:
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0, "status": 1})
    return bool(t) and t.get("status") in TERMINAL


async def _ensure_unique_reference(reference: str, rail: str,
                                    direction: str) -> None:
    """Idempotency guard — refuse duplicates inside (rail × direction × ref)."""
    if not reference:
        return
    existing = await db[TRANSFERS].find_one(
        {"reference": reference, "rail": {"$in": [rail, f"{rail}_instant"]},
         "direction": direction},
        {"_id": 0, "id": 1, "status": 1},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Transfer з reference={reference} вже існує (id={existing['id']}, "
                   f"status={existing.get('status')})",
        )


async def _post_to_ledger(transfer: dict) -> None:
    """When a transfer is `confirmed`, post a matching entry to money_ledger.
    Best-effort: if money_ledger is unavailable in this env, we just log.
    """
    try:
        ledger_doc = {
            "id": f"ml-{uuid.uuid4().hex[:14]}",
            "kind": "institutional_rail",
            "rail": transfer["rail"],
            "direction": transfer["direction"],
            "amount": float(transfer["amount"]),
            "currency": transfer["currency"],
            "investor_id": transfer.get("investor_id"),
            "fund_id": transfer.get("fund_id"),
            "commitment_id": transfer.get("commitment_id"),
            "reference": transfer.get("reference"),
            "provider_ref": transfer.get("provider_ref"),
            "transfer_id": transfer["id"],
            "posted_at": _now(),
            "source": "lumen_institutional_rails",
        }
        await db.money_ledger.insert_one(ledger_doc)
        logger.info("RAILS: posted to ledger (%s %s %s %s)",
                    transfer["rail"], transfer["direction"],
                    transfer["amount"], transfer["currency"])
    except Exception as e:  # pragma: no cover
        logger.warning("RAILS: ledger post failed: %s", e)


async def ensure_rails_indexes() -> None:
    try:
        await db[TRANSFERS].create_index("id", unique=True)
        await db[TRANSFERS].create_index([("rail", 1), ("status", 1)])
        await db[TRANSFERS].create_index([("investor_id", 1), ("created_at", -1)])
        await db[TRANSFERS].create_index([("fund_id", 1), ("created_at", -1)])
        await db[TRANSFERS].create_index([("reference", 1), ("rail", 1),
                                           ("direction", 1)], unique=False)
        await db[EVENTS].create_index([("transfer_id", 1), ("at", -1)])
        logger.info("LUMEN INSTITUTIONAL RAILS: indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("RAILS: index ensure failed: %s", e)


# ════════════════════════════════════════════════════════════════════════════
# Core transfer creation
# ════════════════════════════════════════════════════════════════════════════
async def _create_transfer(rail: str, payload: _RailsBase, *,
                             user: dict, request: Request,
                             rail_specific: dict) -> dict:
    iban_ok, country, err = validate_iban(payload.beneficiary_iban)
    if not iban_ok:
        raise HTTPException(status_code=400,
                            detail=f"Некоректний IBAN: {err}")
    iban = normalize_iban(payload.beneficiary_iban)

    if rail in (RAIL_SEPA, RAIL_SEPA_INSTANT):
        if payload.currency != SEPA_CURRENCY:
            raise HTTPException(status_code=400,
                                detail=f"SEPA підтримує тільки {SEPA_CURRENCY}. "
                                       f"Для іншої валюти використовуйте SWIFT.")
        sepa_ok, sepa_err = is_sepa_eligible(iban)
        if not sepa_ok:
            raise HTTPException(status_code=400,
                                detail=f"IBAN не SEPA-сумісний: {sepa_err}")
        if payload.amount < MIN_AMOUNT_EUR:
            raise HTTPException(
                status_code=400,
                detail=f"Інституційний SEPA-rail: мінімум {MIN_AMOUNT_EUR:.0f} EUR. "
                       f"Для менших сум використайте картковий шлюз.",
            )
    elif rail == RAIL_SWIFT:
        # SWIFT validates BIC
        bic_ok, bic_err = validate_bic(rail_specific.get("beneficiary_bic") or "")
        if not bic_ok:
            raise HTTPException(status_code=400,
                                detail=f"Некоректний BIC: {bic_err}")
        if rail_specific.get("intermediary_bic"):
            ok, err = validate_bic(rail_specific["intermediary_bic"])
            if not ok:
                raise HTTPException(status_code=400,
                                    detail=f"Некоректний intermediary BIC: {err}")
        # SWIFT supports any major currency
        if payload.currency not in {"USD", "EUR", "GBP", "CHF", "JPY", "CAD",
                                      "AUD", "NOK", "SEK", "DKK"}:
            raise HTTPException(
                status_code=400,
                detail=f"SWIFT валюта '{payload.currency}' не підтримується "
                       f"у поточному relise. Дозволено: USD/EUR/GBP/CHF/JPY...",
            )
        if payload.currency == "USD" and payload.amount < MIN_AMOUNT_USD:
            raise HTTPException(
                status_code=400,
                detail=f"Інституційний SWIFT-rail: мінімум {MIN_AMOUNT_USD:.0f} USD",
            )

    reference = (payload.reference or _new_ref(rail)).strip()
    await _ensure_unique_reference(reference, rail.replace("_instant", ""),
                                    payload.direction)

    actor_id = _uid(user)
    doc = {
        "id": _new_id(),
        "rail": rail,
        "direction": payload.direction,
        "status": STATUS_PENDING,
        "canonical_status": "submitted",   # H1.1-R2 canonical state
        "amount": float(payload.amount),
        "currency": payload.currency,
        "reference": reference,
        "purpose": payload.purpose,
        "beneficiary_name": payload.beneficiary_name.strip(),
        "beneficiary_iban": iban,
        "beneficiary_country": country,
        "investor_id": payload.investor_id or actor_id,
        "fund_id": payload.fund_id,
        "commitment_id": payload.commitment_id,
        "created_by": actor_id,
        "created_at": _now(),
        "updated_at": _now(),
        "provider": "manual_ops",   # gets replaced when a banking adapter exists
        "provider_ref": None,
        "metadata": payload.metadata or {},
        **rail_specific,
    }
    await db[TRANSFERS].insert_one(doc)
    await _event(doc["id"], status=STATUS_PENDING, actor=actor_id,
                  message=f"Created via {rail} rail",
                  meta={"amount": doc["amount"], "currency": doc["currency"]})
    await _audit(
        f"institutional_rails.{rail}.submit", actor=user,
        target_id=doc["id"], request=request,
        summary=f"{rail.upper()} {payload.direction} {doc['amount']:.2f} {doc['currency']} → {iban[:8]}…",
        meta={"reference": reference},
    )
    logger.info("RAILS: created %s id=%s rail=%s dir=%s amount=%.2f %s",
                "transfer", doc["id"], rail, payload.direction,
                doc["amount"], doc["currency"])
    return _strip(doc)


# ════════════════════════════════════════════════════════════════════════════
# Router
# ════════════════════════════════════════════════════════════════════════════
router = APIRouter(prefix="/api", tags=["lumen-institutional-rails"])


# ── IBAN/BIC validators (public, useful for the UI form) ────────────────────
@router.get("/lumen/institutional/rails/iban/validate")
async def validate_iban_endpoint(iban: str):
    ok, country, err = validate_iban(iban)
    sepa_ok = False
    if ok:
        sepa_ok, _ = is_sepa_eligible(iban)
    return {"ok": ok, "country": country, "error": err,
            "sepa_eligible": sepa_ok,
            "iban_normalized": normalize_iban(iban) if ok else None}


@router.get("/lumen/institutional/rails/bic/validate")
async def validate_bic_endpoint(bic: str):
    ok, err = validate_bic(bic)
    return {"ok": ok, "error": err,
            "bic_normalized": normalize_bic(bic) if ok else None}


# ── INVESTOR: submit SEPA ───────────────────────────────────────────────────
@router.post("/lumen/institutional/rails/sepa/transfers")
async def submit_sepa_transfer(payload: SepaTransferIn, request: Request,
                                 user=Depends(get_current_user),
                                 _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    rail = RAIL_SEPA_INSTANT if payload.instant else RAIL_SEPA
    return await _create_transfer(rail, payload, user=user, request=request,
                                    rail_specific={"sepa_instant": bool(payload.instant)})


# ── INVESTOR: submit SWIFT ──────────────────────────────────────────────────
@router.post("/lumen/institutional/rails/swift/transfers")
async def submit_swift_transfer(payload: SwiftTransferIn, request: Request,
                                  user=Depends(get_current_user),
                                  _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    return await _create_transfer(
        RAIL_SWIFT, payload, user=user, request=request,
        rail_specific={
            "beneficiary_bic": normalize_bic(payload.beneficiary_bic),
            "intermediary_bic": (normalize_bic(payload.intermediary_bic)
                                    if payload.intermediary_bic else None),
            "charges": payload.charges,
        })


# ── INVESTOR: list my transfers ─────────────────────────────────────────────
@router.get("/lumen/institutional/rails/transfers")
async def list_my_transfers(user=Depends(get_current_user),
                              status: Optional[str] = None,
                              rail: Optional[str] = None,
                              limit: int = 50):
    q: dict = {"$or": [
        {"investor_id": _uid(user)}, {"created_by": _uid(user)}
    ]}
    if status:
        q["status"] = status
    if rail:
        q["rail"] = rail
    items = []
    async for t in db[TRANSFERS].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(_strip(t))
    return {"items": items, "total": len(items)}


# ── INVESTOR / ADMIN: detail ────────────────────────────────────────────────
@router.get("/lumen/institutional/rails/transfers/{transfer_id}")
async def get_transfer(transfer_id: str, user=Depends(get_current_user)):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    # Visibility: investor sees own, admin sees all
    if user.get("role") != "admin":
        if t.get("investor_id") != _uid(user) and t.get("created_by") != _uid(user):
            raise HTTPException(status_code=403, detail="forbidden")
    events = []
    async for e in db[EVENTS].find({"transfer_id": transfer_id}, {"_id": 0}).sort("at", -1):
        events.append(_strip(e))
    return {"transfer": _strip(t), "events": events}


# ── INVESTOR: cancel a pending (own) transfer ───────────────────────────────
@router.post("/lumen/institutional/rails/transfers/{transfer_id}/cancel")
async def cancel_my_transfer(transfer_id: str, request: Request,
                               user=Depends(get_current_user),
                               _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    if t.get("created_by") != _uid(user) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    if t["status"] in TERMINAL:
        raise HTTPException(status_code=409,
                            detail=f"Transfer вже у фінальному статусі ({t['status']})")
    if t["status"] not in (STATUS_DRAFT, STATUS_PENDING):
        raise HTTPException(status_code=409,
                            detail=f"Скасування можливе лише до initiated (поточний: {t['status']})")
    await db[TRANSFERS].update_one(
        {"id": transfer_id},
        {"$set": {"status": STATUS_CANCELLED,
                   "canonical_status": "rejected",
                   "updated_at": _now()}},
    )
    await _event(transfer_id, status=STATUS_CANCELLED, actor=_uid(user),
                  message="cancelled by initiator")
    await _audit("institutional_rails.cancel", actor=user,
                  target_id=transfer_id, request=request,
                  summary="Transfer cancelled by initiator")
    return {"ok": True, "status": STATUS_CANCELLED}


# ── ADMIN: list all transfers + filters ─────────────────────────────────────
@router.get("/admin/lumen/institutional/rails/transfers")
async def admin_list_transfers(_=Depends(require_admin),
                                 status: Optional[str] = None,
                                 rail: Optional[str] = None,
                                 investor_id: Optional[str] = None,
                                 fund_id: Optional[str] = None,
                                 limit: int = 200):
    q: dict = {}
    if status:
        q["status"] = status
    if rail:
        q["rail"] = rail
    if investor_id:
        q["investor_id"] = investor_id
    if fund_id:
        q["fund_id"] = fund_id
    items = []
    async for t in db[TRANSFERS].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(_strip(t))
    return {"items": items, "total": len(items)}


# ── ADMIN: confirm (mark settled) ───────────────────────────────────────────
@router.post("/admin/lumen/institutional/rails/transfers/{transfer_id}/confirm")
async def admin_confirm(transfer_id: str, payload: ConfirmIn, request: Request,
                         admin=Depends(require_admin),
                         _perm=Depends(_lr2_perm("distribution", "approve"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    if t["status"] == STATUS_CONFIRMED:
        return {"ok": True, "status": STATUS_CONFIRMED, "already": True,
                "transfer": _strip(t)}
    if t["status"] in TERMINAL:
        raise HTTPException(status_code=409,
                            detail=f"Не можна підтвердити: статус {t['status']}")
    new_set = {
        "status": STATUS_CONFIRMED,
        "canonical_status": "confirmed",
        "updated_at": _now(),
        "settled_at": payload.settled_at or _iso(_now()),
        "provider_ref": payload.provider_ref or t.get("provider_ref"),
    }
    await db[TRANSFERS].update_one({"id": transfer_id}, {"$set": new_set})
    t2 = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    await _event(transfer_id, status=STATUS_CONFIRMED, actor=_uid(admin),
                  message=payload.note or "confirmed by admin",
                  meta={"provider_ref": payload.provider_ref})
    await _audit("institutional_rails.confirm", actor=admin,
                  target_id=transfer_id, request=request,
                  summary=f"Confirmed {t['rail']} {t['direction']} "
                          f"{t['amount']:.2f} {t['currency']}",
                  meta={"provider_ref": payload.provider_ref})
    # Authority-of-record: post to money_ledger
    await _post_to_ledger(t2)
    return {"ok": True, "status": STATUS_CONFIRMED, "transfer": _strip(t2)}


# ── ADMIN: reject / fail / return ───────────────────────────────────────────
@router.post("/admin/lumen/institutional/rails/transfers/{transfer_id}/reject")
async def admin_reject(transfer_id: str, payload: RejectIn, request: Request,
                        admin=Depends(require_admin),
                        _perm=Depends(_lr2_perm("distribution", "approve"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    if t["status"] in TERMINAL:
        raise HTTPException(status_code=409,
                            detail=f"Вже у фінальному статусі ({t['status']})")
    await db[TRANSFERS].update_one({"id": transfer_id},
                                     {"$set": {"status": STATUS_FAILED,
                                               "canonical_status": "rejected",
                                               "updated_at": _now(),
                                               "failure_reason": payload.reason}})
    await _event(transfer_id, status=STATUS_FAILED, actor=_uid(admin),
                  message=payload.reason)
    await _audit("institutional_rails.reject", actor=admin,
                  target_id=transfer_id, request=request,
                  summary=f"Rejected: {payload.reason}",
                  meta={"reason": payload.reason})
    return {"ok": True, "status": STATUS_FAILED, "reason": payload.reason}


# ── ADMIN: reconcile against bank statement ─────────────────────────────────
@router.post("/admin/lumen/institutional/rails/transfers/{transfer_id}/reconcile")
async def admin_reconcile(transfer_id: str, payload: ReconcileIn, request: Request,
                           admin=Depends(require_admin),
                           _perm=Depends(_lr2_perm("distribution", "approve"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    delta_amount = round(float(payload.amount_observed) - float(t["amount"]), 2)
    currency_mismatch = (payload.currency_observed.upper() != t["currency"].upper())
    matched = (abs(delta_amount) < 0.01) and not currency_mismatch
    recon = {
        "matched": matched,
        "delta_amount": delta_amount,
        "currency_mismatch": currency_mismatch,
        "bank_statement_ref": payload.bank_statement_ref,
        "observed": {"amount": float(payload.amount_observed),
                       "currency": payload.currency_observed.upper()},
        "reconciled_at": _iso(_now()),
        "reconciled_by": _uid(admin),
    }
    await db[TRANSFERS].update_one({"id": transfer_id},
                                     {"$set": {"reconciliation": recon,
                                               "updated_at": _now()}})
    await _event(transfer_id, status=t["status"], actor=_uid(admin),
                  message=f"Reconciled vs {payload.bank_statement_ref} "
                          f"(matched={matched})",
                  meta=recon)
    await _audit("institutional_rails.reconcile", actor=admin,
                  target_id=transfer_id, request=request,
                  summary=f"Reconciled (matched={matched}, "
                          f"delta={delta_amount:+.2f} {t['currency']})",
                  meta=recon)
    return {"ok": True, "reconciliation": recon}


# ── ADMIN: aggregate stats for the admin dashboard ──────────────────────────
@router.get("/admin/lumen/institutional/rails/stats")
async def admin_rails_stats(_=Depends(require_admin)):
    pipeline = [
        {"$group": {
            "_id": {"rail": "$rail", "status": "$status",
                     "currency": "$currency",
                     "direction": "$direction"},
            "count": {"$sum": 1},
            "total": {"$sum": "$amount"},
        }},
    ]
    by_combo: list[dict] = []
    async for row in db[TRANSFERS].aggregate(pipeline):
        k = row["_id"]
        by_combo.append({
            "rail": k.get("rail"),
            "status": k.get("status"),
            "currency": k.get("currency"),
            "direction": k.get("direction"),
            "count": row["count"],
            "total_amount": round(float(row["total"] or 0), 2),
        })
    totals = {
        "transfers": await db[TRANSFERS].count_documents({}),
        "pending": await db[TRANSFERS].count_documents({"status": STATUS_PENDING}),
        "confirmed": await db[TRANSFERS].count_documents({"status": STATUS_CONFIRMED}),
        "failed": await db[TRANSFERS].count_documents({"status": STATUS_FAILED}),
        "cancelled": await db[TRANSFERS].count_documents({"status": STATUS_CANCELLED}),
    }
    return {"totals": totals, "by_combo": by_combo,
            "rails_supported": list(RAILS),
            "min_amounts": {"sepa_eur": MIN_AMOUNT_EUR, "swift_usd": MIN_AMOUNT_USD},
            "ran_at": _iso(_now())}


__all__ = [
    "router",
    "ensure_rails_indexes",
    "RAIL_SEPA",
    "RAIL_SEPA_INSTANT",
    "RAIL_SWIFT",
    "validate_iban",
    "validate_bic",
    "is_sepa_eligible",
]
