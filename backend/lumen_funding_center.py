"""
LUMEN 2.0 — Phase H1.1 — Funding Center
========================================

Operational layer **on top of** lumen_institutional_rails (H1).

H1   = the rails engine (SEPA / SWIFT instruction + reconciliation + ledger).
H1.1 = the **investor + admin UX contour** around it. This module ADDS:

  * canonical_status normalization (R2): backend stays compatible with the
    legacy state machine, but every transfer is also tagged with a canonical
    status in `{draft, submitted, pending_review, matched, confirmed, rejected}`
    that the UI uses end-to-end.

  * proof attachments (R3-relevant): investors attach a PDF/PNG/JPG payment
    proof to a transfer. Storage is filesystem-based (mock-safe — same pattern
    as cloudinary_service) and survives backend restart. Each transfer can
    have multiple proofs.

  * bank-accounts read-only endpoint: single source of truth is the existing
    `lumen_funding_accounts` (Sprint 6) — H1.1 does NOT introduce a parallel
    bank-accounts collection. We surface SEPA / SWIFT / UAH variants in one
    shape the UI can consume.

  * /match admin endpoint — intermediate state between reconcile (which only
    measures the delta) and /confirm (which posts to ledger). Lets the admin
    visually progress: pending_review → matched → confirmed.

  * /exceptions admin endpoint — every transfer that has a reconciliation
    flagged as not-matched, currency_mismatch, or that is stuck `failed`
    surfaces here as an actionable queue item.

  * /ledger admin endpoint — money_ledger entries that originated from the
    institutional rails (source = "lumen_institutional_rails"). Pure read.

  * SEPA-EUR funding account seeded once on startup (idempotent) so that the
    Funding Center always has a SEPA beneficiary to show in the UI.

Hard constraints (R1):
  * No "rail" / "settlement" / "treasury" wording in user-facing messages
    coming out of this module. UA + EN error/status text only.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import (APIRouter, Depends, HTTPException, Request, UploadFile,
                     File, Form)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from lumen_api import (db, get_current_user, require_admin,
                       _strip_mongo, _now, _iso, lr2_perm as _lr2_perm)

logger = logging.getLogger("lumen.funding_center")

# ════════════════════════════════════════════════════════════════════════════
# Collections + constants
# ════════════════════════════════════════════════════════════════════════════
TRANSFERS = "lumen_institutional_transfers"  # owned by lumen_institutional_rails
EVENTS = "lumen_institutional_transfer_events"
PROOFS = "lumen_institutional_transfer_proofs"   # NEW (this module)
FUNDING_ACCOUNTS = "lumen_funding_accounts"      # owned by lumen_payments (read-only here)
LEDGER = "money_ledger"

PROOF_DIR = Path("/app/backend/uploads/rails_proofs")
PROOF_DIR.mkdir(parents=True, exist_ok=True)

PROOF_MAX_BYTES = int(os.environ.get("LUMEN_PROOF_MAX_BYTES", str(10 * 1024 * 1024)))   # 10 MB
PROOF_ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}
PROOF_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}

# ── Canonical statuses (R2) ─────────────────────────────────────────────────
CS_DRAFT = "draft"
CS_SUBMITTED = "submitted"
CS_PENDING_REVIEW = "pending_review"
CS_MATCHED = "matched"
CS_CONFIRMED = "confirmed"
CS_REJECTED = "rejected"
CANONICAL_STATUSES = (
    CS_DRAFT, CS_SUBMITTED, CS_PENDING_REVIEW,
    CS_MATCHED, CS_CONFIRMED, CS_REJECTED,
)

# Map legacy (lumen_institutional_rails) status → canonical status
LEGACY_TO_CANONICAL = {
    "draft": CS_DRAFT,
    "pending": CS_SUBMITTED,
    "initiated": CS_PENDING_REVIEW,
    "sent": CS_PENDING_REVIEW,
    "confirmed": CS_CONFIRMED,
    "failed": CS_REJECTED,
    "returned": CS_REJECTED,
    "cancelled": CS_REJECTED,
    # already canonical
    "submitted": CS_SUBMITTED,
    "pending_review": CS_PENDING_REVIEW,
    "matched": CS_MATCHED,
    "rejected": CS_REJECTED,
}

TERMINAL_CANONICAL = {CS_CONFIRMED, CS_REJECTED}


def canonical_status(transfer: dict) -> str:
    """Return canonical status of a transfer."""
    if not transfer:
        return CS_DRAFT
    # explicit canonical_status takes precedence
    cs = transfer.get("canonical_status")
    if cs in CANONICAL_STATUSES:
        return cs
    return LEGACY_TO_CANONICAL.get(transfer.get("status") or "", CS_SUBMITTED)


def with_canonical(transfer: dict) -> dict:
    """Annotate a transfer dict with canonical_status (idempotent)."""
    if not transfer:
        return transfer
    t = dict(transfer)
    t["canonical_status"] = canonical_status(transfer)
    return t


# ════════════════════════════════════════════════════════════════════════════
# Pydantic
# ════════════════════════════════════════════════════════════════════════════
class MatchIn(BaseModel):
    note: Optional[str] = Field(None, max_length=240)


class ConfirmedFlagIn(BaseModel):
    note: Optional[str] = Field(None, max_length=240)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════
def _uid(user) -> str:
    if not user:
        return "anonymous"
    return user.get("user_id") or user.get("id") or "unknown"


def _strip(doc):
    return _strip_mongo(doc) if doc else doc


def _new_proof_id() -> str:
    return f"itxp-{uuid.uuid4().hex[:14]}"


async def _set_canonical_status(transfer_id: str, cs: str, *,
                                  actor: str, message: str = "",
                                  meta: Optional[dict] = None) -> None:
    """Update both legacy and canonical status of a transfer."""
    # Legacy mapping for backward compat with H1 module
    canonical_to_legacy = {
        CS_DRAFT: "draft",
        CS_SUBMITTED: "pending",
        CS_PENDING_REVIEW: "initiated",
        CS_MATCHED: "initiated",      # not terminal in legacy world
        CS_CONFIRMED: "confirmed",
        CS_REJECTED: "failed",
    }
    legacy = canonical_to_legacy.get(cs, "pending")
    await db[TRANSFERS].update_one(
        {"id": transfer_id},
        {"$set": {
            "status": legacy,
            "canonical_status": cs,
            "updated_at": _now(),
        }},
    )
    # Mirror event
    await db[EVENTS].insert_one({
        "id": f"itxev-{uuid.uuid4().hex[:14]}",
        "transfer_id": transfer_id,
        "status": legacy,
        "canonical_status": cs,
        "actor": actor,
        "message": message or f"canonical_status → {cs}",
        "meta": meta or {},
        "at": _now(),
    })


def _safe_ext(filename: str) -> str:
    if not filename:
        return ""
    name = filename.lower().strip()
    for ext in PROOF_ALLOWED_EXT:
        if name.endswith(ext):
            return ext
    return ""


# ════════════════════════════════════════════════════════════════════════════
# Router
# ════════════════════════════════════════════════════════════════════════════
router = APIRouter(prefix="/api", tags=["lumen-funding-center"])


# ── PUBLIC: list of canonical statuses for the UI ───────────────────────────
@router.get("/lumen/institutional/rails/statuses")
async def list_canonical_statuses():
    return {"statuses": list(CANONICAL_STATUSES),
            "terminal": list(TERMINAL_CANONICAL)}


# ── INVESTOR/PUBLIC: Lumen beneficiary bank accounts ────────────────────────
@router.get("/lumen/institutional/rails/bank-accounts")
async def list_bank_accounts(user=Depends(get_current_user)):
    """
    Read-only list of Lumen beneficiary accounts that an investor can fund
    a transfer TO. Source of truth: lumen_funding_accounts (Sprint 6).
    Filters to active accounts only and shapes them for the Funding UI.
    """
    items: list[dict] = []
    async for fa in db[FUNDING_ACCOUNTS].find(
        {"active": True},
        {"_id": 0},
    ).sort("default", -1):
        items.append({
            "id": fa.get("id"),
            "label": fa.get("name"),
            "type": fa.get("type"),                  # bank_transfer | swift | crypto_future
            "bank_name": fa.get("bank_name"),
            "iban": fa.get("iban"),
            "swift_code": fa.get("swift_code"),
            "beneficiary": fa.get("beneficiary"),
            "edrpou": fa.get("edrpou"),
            "currency": fa.get("currency"),
            "default": bool(fa.get("default")),
            "purpose_template": fa.get("purpose_template"),
            "notes": fa.get("notes"),
            "method": "sepa" if (fa.get("currency") == "EUR" and fa.get("type") in ("bank_transfer", "sepa"))
                      else ("swift" if fa.get("type") == "swift" else fa.get("type")),
        })
    return {"items": items, "total": len(items)}


# ── INVESTOR: upload a proof for a transfer (multipart) ─────────────────────
@router.post("/lumen/institutional/rails/transfers/{transfer_id}/proof")
async def upload_proof(transfer_id: str,
                        request: Request,
                        note: Optional[str] = Form(None),
                        file: UploadFile = File(...),
                        user=Depends(get_current_user),
                        _perm=Depends(_lr2_perm("lp_commitment", "write"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено / not found")

    if user.get("role") != "admin":
        if t.get("created_by") != _uid(user) and t.get("investor_id") != _uid(user):
            raise HTTPException(status_code=403, detail="forbidden")

    cs = canonical_status(t)
    if cs in TERMINAL_CANONICAL:
        raise HTTPException(
            status_code=409,
            detail=f"Transfer вже завершено (статус {cs}) — proof attach forbidden",
        )

    # Validate file — IR0.2 server-authoritative validation replaces the
    # ext+mime check with magic-byte sniff + sanitised filename.
    raw = await file.read()
    try:
        from lumen_upload_security import validate_upload as _ir0_validate
        safe = _ir0_validate(raw, file.filename, category="funding_proof")
    except Exception as _us_e:
        from fastapi import HTTPException as _HE
        if isinstance(_us_e, _HE):
            raise
        raise _HE(status_code=400, detail="Неможливо обробити файл")
    ext = f".{safe.ext}" if safe.ext else ""
    mime = safe.mime

    proof_id = _new_proof_id()
    target_dir = PROOF_DIR / transfer_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{proof_id}{ext}"
    with target_path.open("wb") as f:
        f.write(raw)

    proof_doc = {
        "id": proof_id,
        "transfer_id": transfer_id,
        "filename_original": safe.filename,
        "filename_stored": target_path.name,
        "ext": ext,
        "mime": mime,
        "size_bytes": safe.size,
        "uploaded_by": _uid(user),
        "uploaded_at": _now(),
        "note": (note or "").strip()[:240] or None,
        "url_internal": f"/api/lumen/institutional/rails/proofs/{proof_id}/download",
    }
    await db[PROOFS].insert_one(proof_doc)

    # Transition pending → pending_review on first proof upload (only forward)
    if cs == CS_SUBMITTED:
        await _set_canonical_status(
            transfer_id, CS_PENDING_REVIEW,
            actor=_uid(user),
            message="Proof attached; awaiting bank reconciliation",
            meta={"proof_id": proof_id},
        )

    logger.info("FUNDING: proof %s uploaded for transfer %s (%d bytes)",
                proof_id, transfer_id, len(raw))
    return {"ok": True, "proof": _strip(proof_doc),
            "canonical_status": CS_PENDING_REVIEW if cs == CS_SUBMITTED else cs}


# ── INVESTOR/ADMIN: list proofs for a transfer ──────────────────────────────
@router.get("/lumen/institutional/rails/transfers/{transfer_id}/proofs")
async def list_proofs(transfer_id: str, user=Depends(get_current_user)):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    if user.get("role") != "admin":
        if t.get("investor_id") != _uid(user) and t.get("created_by") != _uid(user):
            raise HTTPException(status_code=403, detail="forbidden")
    items: list[dict] = []
    async for p in db[PROOFS].find(
        {"transfer_id": transfer_id},
        {"_id": 0},
    ).sort("uploaded_at", -1):
        items.append(_strip(p))
    return {"items": items, "total": len(items)}


# ── INVESTOR/ADMIN: list all proofs for the current user / all (admin) ──────
@router.get("/lumen/institutional/rails/proofs")
async def my_proofs(user=Depends(get_current_user), limit: int = 100):
    is_admin = user.get("role") == "admin"
    if is_admin:
        q = {}
    else:
        # All transfers owned by this user
        my_ids = []
        async for t in db[TRANSFERS].find(
            {"$or": [{"investor_id": _uid(user)}, {"created_by": _uid(user)}]},
            {"_id": 0, "id": 1},
        ):
            my_ids.append(t["id"])
        if not my_ids:
            return {"items": [], "total": 0}
        q = {"transfer_id": {"$in": my_ids}}
    items: list[dict] = []
    async for p in db[PROOFS].find(q, {"_id": 0}).sort("uploaded_at", -1).limit(limit):
        items.append(_strip(p))
    return {"items": items, "total": len(items)}


# ── INVESTOR/ADMIN: download a proof file ───────────────────────────────────
@router.get("/lumen/institutional/rails/proofs/{proof_id}/download")
async def download_proof(proof_id: str, user=Depends(get_current_user)):
    p = await db[PROOFS].find_one({"id": proof_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Proof не знайдено")
    t = await db[TRANSFERS].find_one({"id": p["transfer_id"]}, {"_id": 0})
    if user.get("role") != "admin":
        if not t or (t.get("investor_id") != _uid(user)
                     and t.get("created_by") != _uid(user)):
            raise HTTPException(status_code=403, detail="forbidden")
    path = PROOF_DIR / p["transfer_id"] / p["filename_stored"]
    if not path.exists():
        raise HTTPException(status_code=410, detail="Файл недоступний на сервері")
    return FileResponse(path, media_type=p.get("mime") or "application/octet-stream",
                         filename=p.get("filename_original") or path.name)


# ── ADMIN: mark transfer as MATCHED (post-reconcile, pre-confirm) ───────────
@router.post("/admin/lumen/institutional/rails/transfers/{transfer_id}/match")
async def admin_match(transfer_id: str, payload: MatchIn, request: Request,
                       admin=Depends(require_admin),
                       _perm=Depends(_lr2_perm("distribution", "approve"))):
    t = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transfer не знайдено")
    cs = canonical_status(t)
    if cs in TERMINAL_CANONICAL:
        raise HTTPException(
            status_code=409,
            detail=f"Transfer вже у фінальному статусі ({cs})",
        )
    recon = t.get("reconciliation") or {}
    if not recon.get("matched"):
        raise HTTPException(
            status_code=409,
            detail="Не можна позначити як matched: спочатку запустіть Reconciliation "
                   "із позитивним збігом (matched=true).",
        )
    await _set_canonical_status(
        transfer_id, CS_MATCHED,
        actor=_uid(admin),
        message=payload.note or "Marked as matched by admin",
        meta={"reconciliation_ref": recon.get("bank_statement_ref")},
    )
    t2 = await db[TRANSFERS].find_one({"id": transfer_id}, {"_id": 0})
    return {"ok": True, "canonical_status": CS_MATCHED, "transfer": with_canonical(_strip(t2))}


# ── ADMIN: exceptions queue ─────────────────────────────────────────────────
@router.get("/admin/lumen/institutional/rails/exceptions")
async def admin_exceptions(_=Depends(require_admin), limit: int = 200):
    """
    Surfaces transfers that need operational attention:
      • currency_mismatch on reconciliation
      • amount_mismatch (delta != 0) on reconciliation
      • status = failed (legacy "rejected"/"failed"/"returned"/"cancelled" → canonical "rejected")
      • duplicate_reference (we never insert them, but show 409-collisions as future flag)
      • missing_reference (transfer was created without a reference — guarded but kept for ops)
    """
    items: list[dict] = []
    async for t in db[TRANSFERS].find({}, {"_id": 0}).sort("created_at", -1).limit(limit):
        flags = []
        recon = t.get("reconciliation") or {}
        if recon:
            if recon.get("currency_mismatch"):
                flags.append("currency_mismatch")
            if abs(float(recon.get("delta_amount") or 0)) >= 0.01:
                flags.append("amount_mismatch")
            if recon.get("matched") is False and not (recon.get("currency_mismatch")
                                                       or abs(float(recon.get("delta_amount") or 0)) >= 0.01):
                flags.append("reconcile_no_match")
        if not (t.get("reference") or "").strip():
            flags.append("missing_reference")
        if canonical_status(t) == CS_REJECTED:
            flags.append("rejected")
        if flags:
            items.append({
                "transfer_id": t["id"],
                "rail": t.get("rail"),
                "direction": t.get("direction"),
                "amount": t.get("amount"),
                "currency": t.get("currency"),
                "reference": t.get("reference"),
                "investor_id": t.get("investor_id"),
                "canonical_status": canonical_status(t),
                "flags": flags,
                "reconciliation": recon or None,
                "created_at": t.get("created_at"),
            })
    return {"items": items, "total": len(items)}


# ── ADMIN: ledger entries that came from institutional rails ────────────────
@router.get("/admin/lumen/institutional/rails/ledger")
async def admin_rails_ledger(_=Depends(require_admin), limit: int = 200):
    items: list[dict] = []
    async for entry in db[LEDGER].find(
        {"source": "lumen_institutional_rails"},
        {"_id": 0},
    ).sort("posted_at", -1).limit(limit):
        items.append(_strip(entry))
    return {"items": items, "total": len(items)}


# ── INVESTOR: history (bank-statement view) (R3) ────────────────────────────
@router.get("/lumen/institutional/rails/history")
async def investor_history(user=Depends(get_current_user), limit: int = 200):
    """
    R3 — Investor "History" reads as a bank statement.
    Returns ONLY the columns required: date / reference / method / amount /
    currency / status. No internal IDs leak through.
    """
    q = {"$or": [{"investor_id": _uid(user)}, {"created_by": _uid(user)}]}
    items: list[dict] = []
    async for t in db[TRANSFERS].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        rail = t.get("rail") or ""
        method = "SEPA Instant" if rail == "sepa_instant" else rail.upper()
        items.append({
            "date": t.get("created_at"),
            "reference": t.get("reference"),
            "method": method,
            "amount": float(t.get("amount") or 0),
            "currency": t.get("currency"),
            "status": canonical_status(t),
            "_id_internal": t.get("id"),   # kept under underscore for UI navigation only
        })
    return {"items": items, "total": len(items)}


# ════════════════════════════════════════════════════════════════════════════
# Bootstrap: seed a SEPA-EUR funding account so the Funding Center UI has a
# beneficiary to render in the Deposit wizard.  Idempotent.
# ════════════════════════════════════════════════════════════════════════════
SEPA_SEED = {
    "id": "fa-sepa-eur-default",
    "name": "Lumen SEPA-рахунок (EUR)",
    "type": "sepa",
    "bank_name": "DekaBank Deutsche Girozentrale",
    "iban": "DE89370400440532013000",
    "beneficiary": "Lumen Capital SE",
    "edrpou": None,
    "currency": "EUR",
    "swift_code": "DEUTDEFFXXX",
    "purpose_template": "Lumen Investment Funding · ref {reference}",
    "active": True,
    "default": False,
    "notes": "SEPA bank transfer for institutional EUR funding. "
             "Mandatorily include the reference in payment purpose.",
}


async def ensure_funding_center_indexes() -> None:
    try:
        await db[PROOFS].create_index("id", unique=True)
        await db[PROOFS].create_index([("transfer_id", 1), ("uploaded_at", -1)])
        await db[PROOFS].create_index("uploaded_by")
        await db[TRANSFERS].create_index("canonical_status")
        logger.info("FUNDING CENTER: indexes ensured")
    except Exception as e:  # pragma: no cover
        logger.warning("FUNDING CENTER: index ensure failed: %s", e)


async def ensure_sepa_funding_account() -> None:
    try:
        existing = await db[FUNDING_ACCOUNTS].find_one({"id": SEPA_SEED["id"]})
        if existing:
            return
        # Don't create if there's already any SEPA/EUR account
        eur = await db[FUNDING_ACCOUNTS].find_one(
            {"$or": [
                {"currency": "EUR", "active": True},
                {"type": "sepa", "active": True},
            ]},
        )
        if eur:
            return
        doc = dict(SEPA_SEED)
        doc["created_at"] = _now()
        doc["updated_at"] = _now()
        await db[FUNDING_ACCOUNTS].insert_one(doc)
        logger.info("FUNDING CENTER: seeded SEPA-EUR funding account")
    except Exception as e:  # pragma: no cover
        logger.warning("FUNDING CENTER: SEPA seed failed: %s", e)


async def bootstrap_funding_center() -> None:
    await ensure_funding_center_indexes()
    await ensure_sepa_funding_account()


__all__ = [
    "router",
    "bootstrap_funding_center",
    "canonical_status",
    "with_canonical",
    "CANONICAL_STATUSES",
    "TERMINAL_CANONICAL",
    "CS_DRAFT", "CS_SUBMITTED", "CS_PENDING_REVIEW",
    "CS_MATCHED", "CS_CONFIRMED", "CS_REJECTED",
]
