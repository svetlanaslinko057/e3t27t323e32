"""
LUMEN KYC + Investor Profile — Sprint 3.

The investor stops being a bare `user` and becomes a full investment profile:
identity, tax data, residency, IBAN, KYC evidence and an admin moderation
queue. Strictly NO e-sign / contracts / payments / wallet / payouts / crypto /
secondary market (Sprints 4+).

Endpoints
=========
Investor
    GET    /api/investor/profile                    — get-or-create my profile
    PATCH  /api/investor/profile                    — update profile fields
    POST   /api/investor/kyc/documents              — upload evidence (multipart)
    GET    /api/investor/kyc/documents              — list my documents
    DELETE /api/investor/kyc/documents/{doc_id}     — remove (draft stages only)
    POST   /api/investor/kyc/submit                 — submit profile for review
    GET    /api/kyc/documents/{doc_id}/file         — download (owner or admin)

Admin (compliance)
    GET    /api/admin/kyc?status=...                — review queue
    GET    /api/admin/kyc/{investor_id}             — investor card (profile+docs)
    POST   /api/admin/kyc/{investor_id}/approve     — approve (note optional)
    POST   /api/admin/kyc/{investor_id}/reject      — reject (reason REQUIRED)

KYC lifecycle
=============
    not_started → draft → submitted → under_review → approved
                                  ↘ rejected → (edit → draft → submitted …)
                                                approved → expired (future)

Investment Core integration (soft mode, per product decision):
    intent approve while KYC not approved  → investment `kyc_pending`
    admin approves KYC                     → all `kyc_pending` investments of
                                             the investor activate automatically
                                             (ownership + funding recompute).
File storage: local disk (mock object storage) under uploads/kyc/<investor>/.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, _iso, lr2_perm as _lr2_perm
from lumen_investment_core import activate_ready_investments, _notify
from lumen_audit import write_audit


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

KYC_STATUSES = [
    "not_started", "draft", "submitted", "under_review",
    "approved", "rejected", "expired",
]

KYC_STATUS_LABELS = {
    "not_started":  "не розпочато",
    "draft":        "чернетка",
    "submitted":    "подано на перевірку",
    "under_review": "на розгляді",
    "approved":     "підтверджено",
    "rejected":     "відхилено",
    "expired":      "прострочено",
}

DOC_TYPES = ["passport", "tax_id", "iban_proof", "selfie", "source_of_funds", "other"]

DOC_TYPE_LABELS = {
    "passport":        "паспорт / ID-картка",
    "tax_id":          "РНОКПП (ІПН)",
    "iban_proof":      "підтвердження IBAN",
    "selfie":          "селфі з документом",
    "source_of_funds": "джерело коштів",
    "other":           "інший документ",
}

RISK_PROFILES = ["conservative", "balanced", "aggressive", "unknown"]

# Investor may self-declare accreditation; `verified` is admin-only.
INVESTOR_ALLOWED_ACCREDITATION = ["none", "self_declared"]

# Profile fields the investor may PATCH directly
_PATCHABLE_FIELDS = {
    "full_name", "date_of_birth", "phone", "country", "residency_country",
    "tax_id", "iban", "bank_name", "bank_country", "risk_profile",
    "accreditation_status",
}

# Statuses in which the investor may still edit / delete evidence
_EDITABLE_KYC_STATUSES = {"not_started", "draft", "rejected"}

_ACTIONABLE_KYC_STATUSES = {"submitted", "under_review"}

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "kyc")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_or_create_profile(user_id: str) -> dict:
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id})
    if prof:
        return prof
    now = _now()
    # Legacy mirror: users.kyc_status was seeded as "approved" for the demo
    # investor — keep that state so existing demo flows stay intact.
    user = await db.users.find_one({"user_id": user_id}) or {}
    legacy = user.get("kyc_status")
    kyc_status = "approved" if legacy == "approved" else "not_started"
    prof = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "full_name": user.get("name"),
        "date_of_birth": None,
        "phone": user.get("phone"),
        "country": None,
        "residency_country": None,
        "tax_id": None,
        "iban": None,
        "bank_name": None,
        "bank_country": None,
        "risk_profile": "unknown",
        "accreditation_status": "none",
        "kyc_status": kyc_status,
        "kyc_reviewed_at": None,
        "kyc_reviewer_id": None,
        "kyc_notes": None,
        "document_refs": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_investor_profiles.insert_one(prof)
    return prof


async def _mirror_user_kyc(user_id: str, kyc_status: str) -> None:
    """Keep the legacy users.kyc_status mirror in sync (header badges etc.)."""
    await db.users.update_one({"user_id": user_id}, {"$set": {"kyc_status": kyc_status}})


def _profile_out(prof: dict) -> dict:
    prof = _strip_mongo(dict(prof))
    prof["kyc_status_label"] = KYC_STATUS_LABELS.get(prof.get("kyc_status"), prof.get("kyc_status"))
    return prof


def _doc_out(doc: dict) -> dict:
    doc = _strip_mongo(dict(doc))
    doc.pop("storage_path", None)  # never leak server paths
    doc["doc_type_label"] = DOC_TYPE_LABELS.get(doc.get("doc_type"), doc.get("doc_type"))
    doc["file_url"] = f"/api/kyc/documents/{doc['id']}/file"
    return doc


def _kyc_completeness(prof: dict, doc_types: set[str]) -> list[str]:
    """Returns the list of missing requirements for submission."""
    missing = []
    if not (prof.get("full_name") or "").strip():
        missing.append("full_name")
    if not (prof.get("date_of_birth") or "").strip():
        missing.append("date_of_birth")
    if not (prof.get("country") or prof.get("residency_country")):
        missing.append("country")
    if not (prof.get("tax_id") or "").strip():
        missing.append("tax_id")
    if not (prof.get("iban") or "").strip():
        missing.append("iban")
    if "passport" not in doc_types:
        missing.append("document:passport")
    if "tax_id" not in doc_types:
        missing.append("document:tax_id")
    return missing


# ──────────────────────────────────────────────────────────────────────────────
# Source of Funds — risk-tiered requirement (by intended subscription amount, EUR)
# ──────────────────────────────────────────────────────────────────────────────
#   < SOF_RECOMMENDED_EUR        optional
#   SOF_RECOMMENDED..REQUIRED    recommended (not blocking)
#   SOF_REQUIRED..ENHANCED       required (SoF document mandatory)
#   >= SOF_ENHANCED_EUR          required + enhanced review (document + manual review)
SOF_RECOMMENDED_EUR = float(os.environ.get("LUMEN_SOF_RECOMMENDED_EUR", "1000"))
SOF_REQUIRED_EUR = float(os.environ.get("LUMEN_SOF_REQUIRED_EUR", "10000"))
SOF_ENHANCED_EUR = float(os.environ.get("LUMEN_SOF_ENHANCED_EUR", "100000"))


def sof_requirement(amount_eur: Optional[float]) -> dict:
    """Pure tier function. Returns {level, doc_required, enhanced, threshold}."""
    a = float(amount_eur or 0)
    if a >= SOF_ENHANCED_EUR:
        return {"level": "required_enhanced", "doc_required": True, "enhanced": True,
                "threshold": SOF_ENHANCED_EUR}
    if a >= SOF_REQUIRED_EUR:
        return {"level": "required", "doc_required": True, "enhanced": False,
                "threshold": SOF_REQUIRED_EUR}
    if a >= SOF_RECOMMENDED_EUR:
        return {"level": "recommended", "doc_required": False, "enhanced": False,
                "threshold": SOF_RECOMMENDED_EUR}
    return {"level": "optional", "doc_required": False, "enhanced": False,
            "threshold": 0.0}


async def _has_source_of_funds(investor_id: str) -> bool:
    """SoF is satisfied by an uploaded source_of_funds document OR a profile-level
    declaration (used for seeded/demo investors)."""
    doc = await db.lumen_kyc_documents.find_one(
        {"investor_id": investor_id, "doc_type": "source_of_funds"})
    if doc:
        return True
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id})
    return bool(prof and prof.get("source_of_funds_declared"))


async def assert_source_of_funds(user: dict, amount_eur: Optional[float]) -> dict:
    """Enforce the tiered SoF policy at a money-commitment point. Raises 403 when
    a Source-of-Funds document is mandatory for the amount tier and is missing.
    Non-investor roles (admin/staff/manager/operator) are exempt — the gate is for
    investor capital. Returns the resolved requirement (for response metadata)."""
    req = sof_requirement(amount_eur)
    role = (user.get("role") or "").lower()
    if role and role not in ("client", "investor"):
        return req  # exempt non-investor actors
    if req["doc_required"]:
        iid = user.get("id") or user.get("user_id")
        if not await _has_source_of_funds(iid):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "source_of_funds_required",
                    "level": req["level"],
                    "threshold_eur": req["threshold"],
                    "message": "Для цієї суми потрібно підтвердити джерело коштів "
                               "(Source of Funds). / A Source-of-Funds document is "
                               "required for this amount.",
                },
            )
    return req



# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["lumen-kyc"])


@router.on_event("startup")
async def _sprint3_bootstrap():
    """Idempotent: every investor-role user gets a profile row so the admin
    queue and the investor cabinet never see a missing-profile state."""
    try:
        os.makedirs(_UPLOAD_ROOT, exist_ok=True)
        async for u in db.users.find({"role": {"$in": ["client", "investor"]}}, {"user_id": 1}):
            if u.get("user_id"):
                await _get_or_create_profile(u["user_id"])
        # Demo/seed investors are considered to have a Source-of-Funds declaration
        # on file (kept truthful for demo flows; real investors must upload one per
        # the tiered SoF policy). Idempotent.
        await db.lumen_investor_profiles.update_many(
            {"kyc_status": "approved", "source_of_funds_declared": {"$exists": False}},
            {"$set": {"source_of_funds_declared": True,
                      "source_of_funds_note": "demo-seed declaration"}},
        )
    except Exception:  # pragma: no cover
        import logging
        logging.getLogger("lumen.kyc").exception("Sprint 3 bootstrap failed")


# ---- Investor profile ---------------------------------------------------------

@router.get("/investor/profile")
async def get_my_profile(user=Depends(get_current_user)):
    prof = await _get_or_create_profile(user["id"])
    out = _profile_out(prof)
    docs = []
    async for d in db.lumen_kyc_documents.find({"investor_id": user["id"]}).sort("created_at", -1):
        docs.append(_doc_out(d))
    out["documents"] = docs
    out["missing_for_submit"] = _kyc_completeness(prof, {d["doc_type"] for d in docs})
    out["can_edit"] = prof.get("kyc_status") in _EDITABLE_KYC_STATUSES
    out["email"] = user.get("email")
    return out


class ProfilePatch(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    residency_country: Optional[str] = None
    tax_id: Optional[str] = None
    iban: Optional[str] = None
    bank_name: Optional[str] = None
    bank_country: Optional[str] = None
    risk_profile: Optional[str] = None
    accreditation_status: Optional[str] = None


@router.patch("/investor/profile")
async def patch_my_profile(payload: ProfilePatch, user=Depends(get_current_user)):
    prof = await _get_or_create_profile(user["id"])
    status = prof.get("kyc_status") or "not_started"
    patch: dict[str, Any] = {}
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k not in _PATCHABLE_FIELDS or v is None:
            continue
        if k == "risk_profile" and v not in RISK_PROFILES:
            raise HTTPException(status_code=400, detail=f"Невідомий risk_profile: {v}")
        if k == "accreditation_status" and v not in INVESTOR_ALLOWED_ACCREDITATION:
            raise HTTPException(
                status_code=400,
                detail="Статус акредитації 'verified' встановлює лише комплаєнс",
            )
        patch[k] = v.strip() if isinstance(v, str) else v
    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    if status in ("submitted", "under_review"):
        raise HTTPException(
            status_code=409,
            detail="Анкета на перевірці — редагування заблоковано до рішення комплаєнс",
        )
    # editing moves not_started → draft; rejected → draft (re-application)
    if status in ("not_started", "rejected"):
        patch["kyc_status"] = "draft"
        patch["kyc_notes"] = None if status == "rejected" else prof.get("kyc_notes")
        await _mirror_user_kyc(user["id"], "draft")
    patch["updated_at"] = _now()
    await db.lumen_investor_profiles.update_one({"user_id": user["id"]}, {"$set": patch})
    prof = await db.lumen_investor_profiles.find_one({"user_id": user["id"]})
    # Tier-B compliance: re-screen when identity-bearing fields change.
    if any(k in patch for k in ("full_name", "residency_country", "country", "date_of_birth")):
        try:
            import lumen_compliance_screening as _csc
            await _csc.screen_on_profile_change(
                user["id"], name=prof.get("full_name"),
                dob=prof.get("date_of_birth"),
                country=prof.get("residency_country") or prof.get("country"))
        except Exception:
            import logging as _l
            _l.getLogger("lumen.kyc").warning("compliance re-screen failed", exc_info=True)
    return _profile_out(prof)


# ---- KYC documents ------------------------------------------------------------

@router.post("/investor/kyc/documents")
async def upload_kyc_document(doc_type: str = Form(...), file: UploadFile = File(...),
                              user=Depends(get_current_user),
                              _perm=Depends(_lr2_perm("compliance_profile", "write"))):
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Невідомий тип документа: {doc_type}")
    prof = await _get_or_create_profile(user["id"])
    if prof.get("kyc_status") not in _EDITABLE_KYC_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Документи можна змінювати лише до подання анкети або після відхилення",
        )
    content = await file.read()
    # IR0.2 — server-authoritative upload validation (magic-byte sniff +
    # filename sanitise + per-category size/ext policy). Replaces the
    # previous size/empty-only check.
    try:
        from lumen_upload_security import validate_upload as _ir0_validate
        safe = _ir0_validate(content, file.filename, category="kyc")
    except Exception as _us_e:
        # validate_upload raises UploadSecurityError(HTTPException) with a
        # structured detail — propagate as-is. Other failures degrade to a
        # generic 400 rather than the legacy size-only check.
        from fastapi import HTTPException as _HE
        if isinstance(_us_e, _HE):
            raise
        raise _HE(status_code=400, detail="Неможливо обробити файл")

    doc_id = str(uuid.uuid4())
    # Use the SERVER-DETERMINED extension, never the client-declared one.
    ext = f".{safe.ext}" if safe.ext else ""
    investor_dir = os.path.join(_UPLOAD_ROOT, user["id"])
    os.makedirs(investor_dir, exist_ok=True)
    storage_path = os.path.join(investor_dir, f"{doc_id}{ext}")
    with open(storage_path, "wb") as fh:
        fh.write(content)

    now = _now()
    doc = {
        "id": doc_id,
        "investor_id": user["id"],
        "doc_type": doc_type,
        "filename": safe.filename,            # sanitised
        "content_type": safe.mime,            # server-determined
        "size_bytes": safe.size,
        "storage_path": storage_path,
        "created_at": now,
        "updated_at": now,
    }
    await db.lumen_kyc_documents.insert_one(doc)
    # first evidence moves not_started → draft
    if prof.get("kyc_status") == "not_started":
        await db.lumen_investor_profiles.update_one(
            {"user_id": user["id"]},
            {"$set": {"kyc_status": "draft", "updated_at": now}},
        )
        await _mirror_user_kyc(user["id"], "draft")
    return _doc_out(doc)


@router.get("/investor/kyc/documents")
async def list_kyc_documents(user=Depends(get_current_user)):
    items = []
    async for d in db.lumen_kyc_documents.find({"investor_id": user["id"]}).sort("created_at", -1):
        items.append(_doc_out(d))
    return {"items": items, "total": len(items)}


@router.delete("/investor/kyc/documents/{doc_id}")
async def delete_kyc_document(doc_id: str, user=Depends(get_current_user),
                               _perm=Depends(_lr2_perm("compliance_profile", "delete"))):
    doc = await db.lumen_kyc_documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    if doc.get("investor_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Немає доступу")
    prof = await _get_or_create_profile(user["id"])
    if prof.get("kyc_status") not in _EDITABLE_KYC_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Видалення недоступне: анкета вже на перевірці або підтверджена",
        )
    try:
        if doc.get("storage_path") and os.path.exists(doc["storage_path"]):
            os.remove(doc["storage_path"])
    except OSError:
        pass
    await db.lumen_kyc_documents.delete_one({"id": doc_id})
    return {"ok": True}


@router.get("/kyc/documents/{doc_id}/file")
async def download_kyc_document(doc_id: str, user=Depends(get_current_user)):
    doc = await db.lumen_kyc_documents.find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    if doc.get("investor_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Немає доступу")
    path = doc.get("storage_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Файл недоступний")
    return FileResponse(path, media_type=doc.get("content_type") or "application/octet-stream",
                        filename=doc.get("filename") or "document")


# ---- Submission ----------------------------------------------------------------

@router.post("/investor/kyc/submit")
async def submit_kyc(user=Depends(get_current_user),
                      _ev=Depends(__import__("email_verification").require_verified_email),
                      _perm=Depends(_lr2_perm("compliance_profile", "write"))):
    prof = await _get_or_create_profile(user["id"])
    status = prof.get("kyc_status") or "not_started"
    if status == "approved":
        raise HTTPException(status_code=409, detail="Верифікацію вже підтверджено")
    if status in ("submitted", "under_review"):
        raise HTTPException(status_code=409, detail="Анкета вже на перевірці")
    doc_types = set()
    async for d in db.lumen_kyc_documents.find({"investor_id": user["id"]}, {"doc_type": 1}):
        doc_types.add(d.get("doc_type"))
    missing = _kyc_completeness(prof, doc_types)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"message": "Анкета неповна", "missing": missing},
        )
    now = _now()
    await db.lumen_investor_profiles.update_one(
        {"user_id": user["id"]},
        {"$set": {"kyc_status": "submitted", "kyc_notes": None,
                  "submitted_at": now, "updated_at": now}},
    )
    await _mirror_user_kyc(user["id"], "submitted")
    # Tier-B compliance: run sanctions + PEP screening on submit. Resilient —
    # never blocks submission; opens a compliance case for review on a hit.
    try:
        import lumen_compliance_screening as _csc
        await _csc.screen_on_kyc_submit(user["id"])
    except Exception:
        import logging as _l
        _l.getLogger("lumen.kyc").warning("compliance screen on kyc submit failed", exc_info=True)
    await _notify(
        user["id"],
        "Анкету подано на перевірку",
        "Комплаєнс перевірить ваші дані протягом 1-2 робочих днів. "
        "Ми повідомимо вас про результат.",
    )
    return {"ok": True, "kyc_status": "submitted"}


# ---- Admin moderation -----------------------------------------------------------

@router.get("/admin/kyc")
async def admin_kyc_queue(status: Optional[str] = None, _=Depends(require_admin)):
    q: dict[str, Any] = {}
    if status:
        if status not in KYC_STATUSES:
            raise HTTPException(status_code=400, detail=f"Невідомий статус: {status}")
        q["kyc_status"] = status
    else:
        q["kyc_status"] = {"$in": ["submitted", "under_review"]}
    items = []
    async for prof in db.lumen_investor_profiles.find(q).sort("updated_at", -1).limit(500):
        out = _profile_out(prof)
        u = await db.users.find_one({"user_id": prof["user_id"]}) or {}
        out["email"] = u.get("email")
        out["name"] = u.get("name")
        out["documents_count"] = await db.lumen_kyc_documents.count_documents(
            {"investor_id": prof["user_id"]}
        )
        items.append(out)
    counts = {}
    for s in KYC_STATUSES:
        counts[s] = await db.lumen_investor_profiles.count_documents({"kyc_status": s})
    return {"items": items, "total": len(items), "counts": counts}


@router.get("/admin/kyc/{investor_id}")
async def admin_kyc_card(investor_id: str, _=Depends(require_admin)):
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id})
    if not prof:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    out = _profile_out(prof)
    u = await db.users.find_one({"user_id": investor_id}) or {}
    out["email"] = u.get("email")
    out["name"] = u.get("name")
    docs = []
    async for d in db.lumen_kyc_documents.find({"investor_id": investor_id}).sort("created_at", -1):
        docs.append(_doc_out(d))
    out["documents"] = docs
    # investment context for the compliance officer
    out["kyc_pending_investments"] = await db.lumen_investments.count_documents(
        {"investor_id": investor_id, "status": "kyc_pending"}
    )
    out["active_investments"] = await db.lumen_investments.count_documents(
        {"investor_id": investor_id, "status": "active"}
    )
    return out


class KycDecision(BaseModel):
    note: Optional[str] = None


class KycRejectDecision(BaseModel):
    reason: str


@router.post("/admin/kyc/{investor_id}/approve")
async def admin_kyc_approve(investor_id: str, payload: KycDecision = None,
                            request: Request = None,
                            admin=Depends(require_admin),
                            _perm=Depends(_lr2_perm("compliance_profile", "approve"))):
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id})
    if not prof:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    if prof.get("kyc_status") not in _ACTIONABLE_KYC_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Анкета не на перевірці (статус: {prof.get('kyc_status')})",
        )
    now = _now()
    old_status = prof.get("kyc_status")
    await db.lumen_investor_profiles.update_one(
        {"user_id": investor_id},
        {"$set": {
            "kyc_status": "approved",
            "kyc_reviewed_at": now,
            "kyc_reviewer_id": admin["id"],
            "kyc_notes": (payload.note if payload else None),
            "updated_at": now,
        }},
    )
    # IR0.3 — field-level history: KYC status transition.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="kyc", entity_id=investor_id,
            field="kyc_status", old_value=old_status, new_value="approved",
            actor=admin, source="api",
            reason=(payload.note if payload else None),
        )
    except Exception:
        pass
    await _mirror_user_kyc(investor_id, "approved")

    # Sprint 6 chain: activation requires KYC approved + contract signed +
    # admin payment confirmation. activate_ready_investments only handles the
    # kyc_pending → contract_pending transition now. For SIGNED contracts we
    # open a payment_request (awaiting_payment) via lumen_payments.
    res = await activate_ready_investments(investor_id, actor_id=admin["id"])
    awaiting_sign = res["moved_to_contract"]
    from lumen_payments import open_payment_requests_for_investor
    pay_res = await open_payment_requests_for_investor(investor_id, actor_id=admin["id"])
    awaiting_payment = int(pay_res.get("opened", 0))

    body = "Ваш профіль інвестора верифіковано."
    if awaiting_payment:
        body += (f" Очікують оплати: {awaiting_payment} — перейдіть у "
                 "розділ «Мої платежі», щоб завершити фінансування.")
    if awaiting_sign:
        body += (f" Інвестицій очікує підписання договору: {awaiting_sign} — "
                 "підпишіть їх у розділі «Договори».")
    await _notify(investor_id, "Верифікацію підтверджено", body)
    await write_audit(
        action="kyc.approve", category="kyc",
        target_type="lumen_investor_profiles", target_id=investor_id,
        actor=admin, request=request,
        summary=f"KYC approved for investor {investor_id}",
        meta={"note": (payload.note if payload else None),
              "payment_requests_opened": awaiting_payment,
              "contracts_awaiting_sign": awaiting_sign},
    )
    return {"investor_id": investor_id, "kyc_status": "approved",
            # backward-compat: `activated_investments` == opened payment_requests
            # under Sprint 6 (activation now happens on admin payment confirm).
            "activated_investments": awaiting_payment,
            "payment_requests_opened": awaiting_payment,
            "contracts_awaiting_sign": awaiting_sign}


@router.post("/admin/kyc/{investor_id}/reject")
async def admin_kyc_reject(investor_id: str, payload: KycRejectDecision,
                           request: Request = None,
                           admin=Depends(require_admin),
                           _perm=Depends(_lr2_perm("compliance_profile", "approve"))):
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Причина відхилення обов'язкова")
    prof = await db.lumen_investor_profiles.find_one({"user_id": investor_id})
    if not prof:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    if prof.get("kyc_status") not in _ACTIONABLE_KYC_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Анкета не на перевірці (статус: {prof.get('kyc_status')})",
        )
    now = _now()
    old_status = prof.get("kyc_status")
    await db.lumen_investor_profiles.update_one(
        {"user_id": investor_id},
        {"$set": {
            "kyc_status": "rejected",
            "kyc_reviewed_at": now,
            "kyc_reviewer_id": admin["id"],
            "kyc_notes": reason,
            "updated_at": now,
        }},
    )
    # IR0.3 — field-level history: KYC rejection.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="kyc", entity_id=investor_id,
            field="kyc_status", old_value=old_status, new_value="rejected",
            actor=admin, source="api", reason=reason,
        )
    except Exception:
        pass
    await _mirror_user_kyc(investor_id, "rejected")
    await _notify(
        investor_id,
        "Верифікацію відхилено",
        f"Причина: {reason}. Виправте дані в профілі та подайте анкету повторно.",
    )
    await write_audit(
        action="kyc.reject", category="kyc",
        target_type="lumen_investor_profiles", target_id=investor_id,
        actor=admin, request=request,
        summary=f"KYC rejected for investor {investor_id}: {reason}",
        meta={"reason": reason},
    )
    return {"investor_id": investor_id, "kyc_status": "rejected", "reason": reason}
