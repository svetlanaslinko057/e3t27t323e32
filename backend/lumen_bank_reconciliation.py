"""
LUMEN Sprint 11 — Bank Reconciliation Backbone (Part 4 + 6)

Introduces the missing link between real bank money and our ledger:

    bank_transaction → payment_request → ledger_entry

Collections
-----------
  lumen_bank_transactions
      One row per inbound bank movement we received — either via a
      provider webhook (Monobank/LiqPay), a manual import (CSV bank
      statement) or a SWIFT confirmation. Append-only.

      {
        id:             'btx-<uuid12>',
        provider:       'monobank' | 'liqpay' | 'swift' | 'manual',
        provider_ref:   external transaction id / webhook id,
        amount:         float (original currency),
        currency:       'UAH' | 'USD' | 'EUR',
        amount_uah:     float (fx-converted snapshot),
        fx_rate:        float,
        payer_name:     str | None,
        payer_iban:     str | None,
        purpose:        str | None    # raw bank statement text
        reference:      str | None    # our LUMEN-PR-<short> code if extracted
        posted_at:      datetime
        status:         'unmatched' | 'matched' | 'reconciled' | 'rejected'
        match_score:    float | None  # 0..1 confidence
        payment_request_id: str | None
        ledger_entry_id:    str | None
        matched_by:     'auto' | actor_id | None
        matched_at:     datetime | None
        rejection_reason: str | None
        raw_payload:    dict          # full provider blob
        created_at:     datetime
      }

Auto-match heuristics (deterministic, top-down)
-----------------------------------------------
  H1.  exact `reference` match: bank_transaction.reference == payment_request.reference
  H2.  amount_uah match within tolerance ±⁁0.50 AND payer email or IBAN matches
        investor profile
  H3.  amount_uah match AND single open payment_request for that investor
        within last 14 days
  H4.  amount_uah match AND single open payment_request platform-wide for that
        amount within 24h (last-resort)

  On match: payment_request.status → confirmed (calls existing
  `confirm_payment_request` so the rest of the chain — ledger / investment.active
  / ownership / asset funding — runs as normal).

Reference codes
---------------
  format: `LUMEN-PR-<8 hex>` issued by `lumen_payments` when a new
  payment_request opens. Stored in payment_request.reference. Shown to
  the investor as the "Призначення платежу" line so the bank stamps it.

Ingest API
----------
  POST /api/banking/webhooks/monobank   (open, signature-validated when LIVE)
  POST /api/banking/webhooks/liqpay     (open, signature-validated when LIVE)
  POST /api/admin/banking/import        (manual CSV upload)
  POST /api/admin/banking/manual        (admin records one wire transfer)

Admin API
---------
  GET  /api/admin/bank-transactions               (paginated, filtered)
  GET  /api/admin/bank-transactions/{id}
  POST /api/admin/bank-transactions/{id}/match/{payment_request_id}
  POST /api/admin/bank-transactions/{id}/reject
  POST /api/admin/bank-transactions/{id}/rematch  (force re-run auto-match)
"""
from __future__ import annotations

import csv
import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile, Query
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, _strip_mongo, _now, _iso
from lumen_audit import write_audit
from lumen_payments import (
    confirm_payment_request,
    _fx_rate_for,
    BASE_CURRENCY,
)

logger = logging.getLogger("lumen.banking.recon")

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

BANK_TX_STATUSES = ("unmatched", "matched", "reconciled", "rejected")
MATCH_TOLERANCE_UAH = 0.50
MATCH_WINDOW_DAYS = 14

REFERENCE_PREFIX = "LUMEN-PR-"


def new_reference() -> str:
    """Generate a fresh payment-request reference code."""
    return f"{REFERENCE_PREFIX}{secrets.token_hex(4).upper()}"


# ----------------------------------------------------------------------------
# Indexes / startup
# ----------------------------------------------------------------------------

async def ensure_indexes() -> None:
    try:
        await db.lumen_bank_transactions.create_index([("created_at", -1)])
        await db.lumen_bank_transactions.create_index([("status", 1), ("created_at", -1)])
        await db.lumen_bank_transactions.create_index(
            [("provider", 1), ("provider_ref", 1)], unique=False)
        await db.lumen_bank_transactions.create_index([("payment_request_id", 1)])
        # Backfill: every payment_request gets a reference if missing.
        async for r in db.lumen_payment_requests.find(
                {"reference": {"$exists": False}}):
            await db.lumen_payment_requests.update_one(
                {"_id": r["_id"]},
                {"$set": {"reference": new_reference()}},
            )
    except Exception:  # pragma: no cover
        logger.exception("banking indexes / backfill failed")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _strip_btx(d: dict) -> dict:
    if not d:
        return d
    d = _strip_mongo(dict(d))
    for k in ("posted_at", "created_at", "matched_at"):
        if d.get(k):
            d[k] = _iso(d[k])
    return d


async def _resolve_investor_by_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    u = await db.users.find_one({"email": email.lower().strip()})
    return (u or {}).get("user_id")


async def _resolve_investor_by_iban(iban: Optional[str]) -> Optional[str]:
    if not iban:
        return None
    norm = iban.replace(" ", "").upper()
    prof = await db.lumen_investor_profiles.find_one({"iban": norm})
    return (prof or {}).get("user_id")


async def _find_payment_by_reference(ref: Optional[str]) -> Optional[dict]:
    if not ref:
        return None
    return await db.lumen_payment_requests.find_one({"reference": ref})


async def _open_requests_for_investor(investor_id: str, *, amount_uah: float,
                                       since: datetime) -> list[dict]:
    items: list[dict] = []
    async for r in db.lumen_payment_requests.find({
        "investor_id": investor_id,
        "status": {"$in": ["awaiting_payment", "paid", "under_review"]},
        "created_at": {"$gte": since},
    }):
        if abs(float(r.get("amount_uah") or 0) - amount_uah) <= MATCH_TOLERANCE_UAH:
            items.append(r)
    return items


async def _platform_open_request_by_amount(amount_uah: float,
                                             since: datetime) -> Optional[dict]:
    candidates: list[dict] = []
    async for r in db.lumen_payment_requests.find({
        "status": {"$in": ["awaiting_payment", "paid", "under_review"]},
        "created_at": {"$gte": since},
    }):
        if abs(float(r.get("amount_uah") or 0) - amount_uah) <= MATCH_TOLERANCE_UAH:
            candidates.append(r)
    if len(candidates) == 1:
        return candidates[0]
    return None


# ----------------------------------------------------------------------------
# Match engine
# ----------------------------------------------------------------------------

async def attempt_match(btx: dict, *, actor: Optional[dict] = None,
                          request: Optional[Request] = None) -> dict:
    """Run all heuristics top-down. On first match: confirm payment_request.
    Returns updated btx dict."""
    if btx.get("status") in ("reconciled", "rejected"):
        return btx

    amount_uah = float(btx.get("amount_uah") or 0)
    if amount_uah <= 0:
        return btx

    # H1 — reference
    pr = await _find_payment_by_reference(btx.get("reference"))
    score = 1.0 if pr else None

    # H2 — email/iban + amount
    if not pr:
        iid = (await _resolve_investor_by_email(btx.get("payer_email"))
               or await _resolve_investor_by_iban(btx.get("payer_iban")))
        if iid:
            since = _now() - timedelta(days=MATCH_WINDOW_DAYS)
            cand = await _open_requests_for_investor(iid, amount_uah=amount_uah,
                                                     since=since)
            if len(cand) == 1:
                pr = cand[0]; score = 0.9
            elif len(cand) >= 2:
                # ambiguous — leave for manual
                pr = None

    # H3 — single open request for investor (any amount tolerance only matches)
    # subsumed by H2 above; explicit fallthrough.

    # H4 — last resort: unique amount platform-wide in 24h
    if not pr:
        since = _now() - timedelta(hours=24)
        cand2 = await _platform_open_request_by_amount(amount_uah, since=since)
        if cand2:
            pr = cand2; score = 0.6

    if not pr:
        # No match — keep unmatched.
        return btx

    # Run the canonical confirm path — it handles ledger + investment + ownership.
    actor_id = (actor or {}).get("id") or "auto-recon"
    try:
        await confirm_payment_request(pr["id"], actor_id, note="bank reconciliation auto-match")
    except Exception as exc:
        logger.exception("confirm during reconciliation failed: %s", exc)
        return btx

    # Link the bank transaction → payment_request → fresh ledger entry.
    ledger_entry = await db.lumen_ledger_entries.find_one(
        {"payment_request_id": pr["id"]}, sort=[("created_at", -1)])
    upd = {
        "status": "reconciled",
        "match_score": score,
        "payment_request_id": pr["id"],
        "ledger_entry_id": (ledger_entry or {}).get("id"),
        "matched_by": "auto" if actor is None else actor_id,
        "matched_at": _now(),
    }
    await db.lumen_bank_transactions.update_one({"id": btx["id"]}, {"$set": upd})
    btx.update(upd)

    await write_audit(
        action="bank.reconcile", category="payment",
        target_type="lumen_bank_transactions", target_id=btx["id"],
        actor=actor, request=request,
        summary=f"Bank transaction {btx['id']} matched to payment_request {pr['id']}",
        meta={"score": score, "amount_uah": amount_uah,
              "provider": btx.get("provider"), "investor_id": pr.get("investor_id")},
    )
    return btx


async def ingest_transaction(*, provider: str, provider_ref: str | None,
                              amount: float, currency: str,
                              payer_name: Optional[str] = None,
                              payer_email: Optional[str] = None,
                              payer_iban: Optional[str] = None,
                              purpose: Optional[str] = None,
                              reference: Optional[str] = None,
                              posted_at: Optional[datetime] = None,
                              raw_payload: Optional[dict] = None,
                              actor: Optional[dict] = None,
                              request: Optional[Request] = None) -> dict:
    """Single entry point for every bank transaction source. Idempotent on
    (provider, provider_ref) when provider_ref is given."""
    if provider_ref:
        existing = await db.lumen_bank_transactions.find_one(
            {"provider": provider, "provider_ref": provider_ref})
        if existing:
            return _strip_btx(existing)

    # Try to pull a reference code from purpose text if not given
    ref = reference
    if not ref and purpose:
        import re
        m = re.search(r"LUMEN-PR-[A-F0-9]{8}", purpose.upper())
        if m:
            ref = m.group(0)

    fx = _fx_rate_for(currency) or 1.0
    amount_uah = round(amount * fx, 2)
    btx = {
        "id": f"btx-{uuid.uuid4().hex[:12]}",
        "provider": provider,
        "provider_ref": provider_ref,
        "amount": float(amount),
        "currency": currency,
        "amount_uah": amount_uah,
        "fx_rate": fx,
        "payer_name": payer_name,
        "payer_email": (payer_email or "").lower().strip() or None,
        "payer_iban": (payer_iban or "").replace(" ", "").upper() or None,
        "purpose": purpose,
        "reference": ref,
        "posted_at": posted_at or _now(),
        "status": "unmatched",
        "match_score": None,
        "payment_request_id": None,
        "ledger_entry_id": None,
        "matched_by": None,
        "matched_at": None,
        "rejection_reason": None,
        "raw_payload": raw_payload or {},
        "created_at": _now(),
    }
    await db.lumen_bank_transactions.insert_one(dict(btx))
    await write_audit(
        action="bank.ingest", category="payment",
        target_type="lumen_bank_transactions", target_id=btx["id"],
        actor=actor, request=request,
        summary=f"Bank transaction ingested: {provider} {provider_ref or ''} "
                f"{amount} {currency}",
        meta={"amount_uah": amount_uah, "provider": provider},
    )
    btx = await attempt_match(btx, actor=actor, request=request)
    return _strip_btx(btx)


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen-banking"])


@router.on_event("startup")
async def _banking_recon_startup():
    await ensure_indexes()


# ---- Webhook receivers (open — verified by signature when LIVE) -------------

@router.post("/banking/webhooks/monobank")
async def monobank_webhook(payload: dict = Body(...), request: Request = None):
    # Monobank Acquiring sends a notification on settlement. Schema:
    # https://api.monobank.ua/docs/acquiring.html
    try:
        data = payload.get("data") or payload
        amount_kopecks = data.get("amount") or 0
        amount = float(amount_kopecks) / 100.0
        currency_code = data.get("ccy") or 980  # UAH
        currency = {980: "UAH", 840: "USD", 978: "EUR"}.get(int(currency_code), "UAH")
        provider_ref = data.get("invoiceId") or data.get("reference") or data.get("id")
        purpose = data.get("destination") or data.get("reference") or ""
        posted_iso = data.get("modifiedDate") or data.get("createdDate")
        posted_at = None
        if posted_iso:
            try:
                posted_at = datetime.fromisoformat(posted_iso.replace("Z", "+00:00"))
            except Exception:
                pass
        btx = await ingest_transaction(
            provider="monobank",
            provider_ref=str(provider_ref) if provider_ref else None,
            amount=amount, currency=currency,
            purpose=purpose,
            posted_at=posted_at,
            raw_payload=payload,
            request=request,
        )
        return {"ok": True, "bank_transaction_id": btx.get("id"), "status": btx.get("status")}
    except Exception as exc:
        logger.exception("monobank webhook ingest failed")
        return {"ok": False, "error": str(exc)}


@router.post("/banking/webhooks/liqpay")
async def liqpay_webhook(payload: dict = Body(...), request: Request = None):
    # LiqPay POSTs base64(data) + signature. We accept either decoded or raw.
    try:
        data = payload.get("data_decoded") or payload
        amount = float(data.get("amount") or 0)
        currency = data.get("currency") or "UAH"
        provider_ref = data.get("transaction_id") or data.get("order_id")
        purpose = data.get("description") or ""
        btx = await ingest_transaction(
            provider="liqpay",
            provider_ref=str(provider_ref) if provider_ref else None,
            amount=amount, currency=currency,
            payer_email=data.get("sender_email"),
            purpose=purpose,
            raw_payload=payload,
            request=request,
        )
        return {"ok": True, "bank_transaction_id": btx.get("id"), "status": btx.get("status")}
    except Exception as exc:
        logger.exception("liqpay webhook ingest failed")
        return {"ok": False, "error": str(exc)}


# ---- Admin: manual + CSV import --------------------------------------------

class ManualBankTransactionPayload(BaseModel):
    provider: str = "manual"  # manual | swift
    provider_ref: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "UAH"
    payer_name: Optional[str] = None
    payer_email: Optional[str] = None
    payer_iban: Optional[str] = None
    purpose: Optional[str] = None
    reference: Optional[str] = None


@router.post("/admin/banking/manual")
async def admin_manual_bank_tx(payload: ManualBankTransactionPayload,
                                request: Request, admin=Depends(require_admin)):
    if payload.provider not in ("manual", "swift", "monobank", "liqpay"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    btx = await ingest_transaction(
        provider=payload.provider,
        provider_ref=payload.provider_ref or f"manual-{secrets.token_hex(4)}",
        amount=payload.amount, currency=payload.currency,
        payer_name=payload.payer_name,
        payer_email=payload.payer_email,
        payer_iban=payload.payer_iban,
        purpose=payload.purpose,
        reference=payload.reference,
        actor=admin, request=request,
    )
    return btx


@router.post("/admin/banking/import")
async def admin_csv_import(file: UploadFile = File(...),
                            request: Request = None,
                            admin=Depends(require_admin)):
    """Import a bank statement CSV. Expected columns (case-insensitive):
    posted_at, amount, currency, payer, iban, purpose, reference, provider_ref.
    Missing columns default. Returns counts."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fieldmap = {k.lower(): k for k in (reader.fieldnames or [])}
    def col(row: dict, name: str) -> Optional[str]:
        k = fieldmap.get(name.lower())
        if not k: return None
        v = row.get(k)
        return v.strip() if isinstance(v, str) else v
    ingested = []
    skipped = 0
    for row in reader:
        try:
            amount = float((col(row, "amount") or "0").replace(",", ".").replace(" ", ""))
        except ValueError:
            skipped += 1; continue
        if amount <= 0:
            skipped += 1; continue
        currency = (col(row, "currency") or "UAH").upper()
        provider_ref = col(row, "provider_ref") or col(row, "reference_id") or None
        posted_at = None
        if (raw_pa := col(row, "posted_at")):
            try:
                posted_at = datetime.fromisoformat(raw_pa)
            except ValueError:
                pass
        btx = await ingest_transaction(
            provider="manual",
            provider_ref=provider_ref,
            amount=amount, currency=currency,
            payer_name=col(row, "payer"),
            payer_iban=col(row, "iban"),
            purpose=col(row, "purpose"),
            reference=col(row, "reference"),
            posted_at=posted_at,
            raw_payload={"source": "csv", "row": row},
            actor=admin, request=request,
        )
        ingested.append(btx["id"])
    return {"ingested": len(ingested), "ids": ingested[:20], "skipped": skipped}


# ---- Admin: bank transactions viewer / actions ------------------------------

@router.get("/admin/bank-transactions")
async def admin_list_btx(status: Optional[str] = None,
                          provider: Optional[str] = None,
                          limit: int = Query(200, ge=1, le=500),
                          _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        if status not in BANK_TX_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
        q["status"] = status
    if provider:
        q["provider"] = provider
    items = []
    async for r in db.lumen_bank_transactions.find(q).sort("created_at", -1).limit(limit):
        items.append(_strip_btx(r))
    counts = {}
    for s in BANK_TX_STATUSES:
        counts[s] = await db.lumen_bank_transactions.count_documents({"status": s})
    return {"items": items, "counts": counts, "total": len(items)}


@router.get("/admin/bank-transactions/{btx_id}")
async def admin_btx_detail(btx_id: str, _=Depends(require_admin)):
    btx = await db.lumen_bank_transactions.find_one({"id": btx_id})
    if not btx:
        raise HTTPException(status_code=404, detail="Не знайдено")
    out = _strip_btx(btx)
    if out.get("payment_request_id"):
        pr = await db.lumen_payment_requests.find_one({"id": out["payment_request_id"]})
        if pr:
            out["payment_request"] = _strip_mongo(pr)
    return out


@router.post("/admin/bank-transactions/{btx_id}/match/{pr_id}")
async def admin_force_match(btx_id: str, pr_id: str, request: Request,
                              admin=Depends(require_admin)):
    btx = await db.lumen_bank_transactions.find_one({"id": btx_id})
    if not btx:
        raise HTTPException(status_code=404, detail="Не знайдено")
    if btx.get("status") in ("reconciled", "rejected"):
        raise HTTPException(status_code=409,
                            detail=f"Already {btx.get('status')}")
    pr = await db.lumen_payment_requests.find_one({"id": pr_id})
    if not pr:
        raise HTTPException(status_code=404, detail="payment_request не знайдено")
    if pr["status"] not in ("awaiting_payment", "paid", "under_review"):
        raise HTTPException(status_code=409,
                            detail=f"payment_request в статусі {pr['status']}")
    await confirm_payment_request(pr["id"], admin["id"],
                                  note=f"manual match by admin from bank tx {btx_id}")
    ledger_entry = await db.lumen_ledger_entries.find_one(
        {"payment_request_id": pr["id"]}, sort=[("created_at", -1)])
    await db.lumen_bank_transactions.update_one(
        {"id": btx_id},
        {"$set": {
            "status": "reconciled",
            "payment_request_id": pr["id"],
            "ledger_entry_id": (ledger_entry or {}).get("id"),
            "matched_by": admin["id"],
            "matched_at": _now(),
            "match_score": 1.0,
        }},
    )
    await write_audit(
        action="bank.manual_match", category="payment",
        target_type="lumen_bank_transactions", target_id=btx_id,
        actor=admin, request=request,
        summary=f"Bank transaction {btx_id} manually matched to {pr_id}",
    )
    return await admin_btx_detail(btx_id, _=admin)


class RejectBtxPayload(BaseModel):
    reason: str


@router.post("/admin/bank-transactions/{btx_id}/reject")
async def admin_reject_btx(btx_id: str, payload: RejectBtxPayload,
                            request: Request, admin=Depends(require_admin)):
    btx = await db.lumen_bank_transactions.find_one({"id": btx_id})
    if not btx:
        raise HTTPException(status_code=404, detail="Не знайдено")
    if btx.get("status") in ("reconciled", "rejected"):
        raise HTTPException(status_code=409, detail=f"Вже {btx['status']}")
    await db.lumen_bank_transactions.update_one(
        {"id": btx_id},
        {"$set": {"status": "rejected",
                  "rejection_reason": (payload.reason or "").strip(),
                  "matched_by": admin["id"], "matched_at": _now()}},
    )
    await write_audit(
        action="bank.reject", category="payment",
        target_type="lumen_bank_transactions", target_id=btx_id,
        actor=admin, request=request,
        summary=f"Bank transaction {btx_id} rejected: {payload.reason}",
        meta={"reason": payload.reason},
    )
    return {"ok": True}


@router.post("/admin/bank-transactions/{btx_id}/rematch")
async def admin_rematch_btx(btx_id: str, request: Request,
                             admin=Depends(require_admin)):
    btx = await db.lumen_bank_transactions.find_one({"id": btx_id})
    if not btx:
        raise HTTPException(status_code=404, detail="Не знайдено")
    if btx.get("status") == "reconciled":
        return _strip_btx(btx)
    if btx.get("status") == "rejected":
        await db.lumen_bank_transactions.update_one({"id": btx_id},
            {"$set": {"status": "unmatched", "rejection_reason": None}})
        btx["status"] = "unmatched"
    btx = await attempt_match(btx, actor=admin, request=request)
    return _strip_btx(btx)


__all__ = [
    "router", "ingest_transaction", "attempt_match", "ensure_indexes",
    "new_reference", "REFERENCE_PREFIX", "BANK_TX_STATUSES",
]
