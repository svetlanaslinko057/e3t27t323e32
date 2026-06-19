"""
LUMEN 2.0 — Phase G15 — Compliance Vault
========================================

A SINGLE unified compliance layer per investor. Compliance data is otherwise
scattered (KYC here, UBO there, contracts elsewhere). The Vault aggregates
everything an institution needs to onboard:

    KYC · Accreditation · AML · Source of Funds (SOF) · UBO · Certificates ·
    Contracts · Tax forms (W-8/W-9) · Risk acknowledgements · Voting consents

Derived from real collections (lumen_investor_profiles, lumen_beneficial_owners,
lumen_contracts, lumen_certificates) + attestation "slots" stored in
lumen_compliance_documents. Produces a Compliance Score (0–100) with reasons and
an Expiration Engine that surfaces items that are expiring or expired.

NO migration, NO mocks (demo data is an idempotent seed).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now, lr2_perm as _lr2_perm

logger = logging.getLogger("lumen.compliance_vault")
router = APIRouter(prefix="/api", tags=["lumen-compliance-vault"])

# Attestation slots the investor can declare / upload
SLOTS = ("sof", "tax_form", "risk_acknowledgement", "voting_consent", "aml_questionnaire")
SLOT_LABELS_UK = {
    "sof": "Джерело коштів (SOF)", "tax_form": "Податкова форма (W-8/W-9)",
    "risk_acknowledgement": "Підтвердження ризиків", "voting_consent": "Згода на голосування",
    "aml_questionnaire": "AML-анкета",
}
SLOT_STATUSES = ("missing", "provided", "verified", "rejected", "expired")

# item key → (label, category, weight, required)
ITEM_SPEC = {
    "kyc":                 ("KYC / Ідентифікація", "identity", 25, True),
    "accreditation":       ("Акредитація", "accreditation", 20, True),
    "sof":                 ("Джерело коштів (SOF)", "aml", 15, True),
    "aml_questionnaire":   ("AML-анкета", "aml", 10, True),
    "tax_form":            ("Податкова форма", "tax", 10, True),
    "ubo":                 ("Кінцевий бенефіціар (UBO)", "ownership", 10, False),
    "risk_acknowledgement":("Підтвердження ризиків", "consent", 5, True),
    "voting_consent":      ("Згода на голосування", "consent", 5, False),
}
STATUS_FRACTION = {"approved": 1.0, "verified": 1.0, "provided": 0.5,
                   "under_review": 0.5, "pending": 0.5, "self_declared": 0.5,
                   "missing": 0.0, "rejected": 0.0, "expired": 0.0, "not_started": 0.0}
STATUS_LABELS_UK = {
    "approved": "Підтверджено", "verified": "Перевірено", "provided": "Надано",
    "under_review": "На розгляді", "pending": "Очікує", "self_declared": "Самодекларація",
    "missing": "Відсутнє", "rejected": "Відхилено", "expired": "Прострочено", "not_started": "Не розпочато",
}
EXPIRY_WARN_DAYS = 45


def _uid(user) -> str:
    return user.get("id") or user.get("user_id")


def _as_dt(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _expired(expires_at) -> bool:
    dt = _as_dt(expires_at)
    return bool(dt and dt < datetime.now(timezone.utc))


def _days_left(expires_at) -> Optional[int]:
    dt = _as_dt(expires_at)
    if not dt:
        return None
    return (dt - datetime.now(timezone.utc)).days


async def _slot_map(user_id: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    async for d in db.lumen_compliance_documents.find({"investor_id": user_id}, {"_id": 0}):
        out[d.get("slot")] = d
    return out


async def _build_vault(user_id: str) -> dict:
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id}, {"_id": 0}) or {}
    slots = await _slot_map(user_id)
    items: list[dict] = []

    def add(key: str, status: str, *, evidence: str = "", expires_at=None, detail: str = ""):
        label, category, weight, required = ITEM_SPEC[key]
        st = "expired" if (expires_at and _expired(expires_at)) else status
        items.append({
            "key": key, "label": label, "category": category, "weight": weight,
            "required": required, "status": st, "status_label": STATUS_LABELS_UK.get(st, st),
            "evidence": evidence, "detail": detail,
            "expires_at": expires_at, "days_left": _days_left(expires_at),
            "fraction": STATUS_FRACTION.get(st, 0.0),
        })

    # 1) KYC (from profile)
    add("kyc", prof.get("kyc_status") or "not_started", evidence="lumen_investor_profiles")
    # 2) Accreditation (G11)
    acc = prof.get("accreditation") or {}
    add("accreditation", acc.get("review_status") or "pending",
        evidence="accreditation_os", expires_at=acc.get("expires_at"),
        detail=acc.get("level") or "")
    # 3-? attestation slots
    for slot_key in ("sof", "aml_questionnaire", "tax_form", "risk_acknowledgement", "voting_consent"):
        s = slots.get(slot_key)
        if s:
            add(slot_key, s.get("status") or "provided",
                evidence=s.get("reference") or "attested", expires_at=s.get("expires_at"),
                detail=s.get("note") or "")
        else:
            # tax_form can be satisfied by profile.tax.tax_form
            if slot_key == "tax_form" and (prof.get("tax") or {}).get("tax_form") in ("w8", "w9"):
                add("tax_form", "provided", evidence="profile.tax", detail=(prof["tax"]["tax_form"]))
            else:
                add(slot_key, "missing")
    # UBO (from beneficial owners)
    ubo_count = await db.lumen_beneficial_owners.count_documents({"investor_id": user_id})
    add("ubo", "verified" if ubo_count else "missing",
        evidence=f"{ubo_count} UBO" if ubo_count else "")

    # Score
    score = 0.0
    reasons: list[str] = []
    for it in items:
        score += it["weight"] * it["fraction"]
        if it["required"] and it["fraction"] < 1.0:
            reasons.append(f"{it['label']}: {it['status_label']}")
    score = round(score)

    # Expirations
    expirations = []
    for it in items:
        dl = it.get("days_left")
        if dl is not None and (dl < 0 or dl <= EXPIRY_WARN_DAYS):
            expirations.append({"key": it["key"], "label": it["label"],
                                "days_left": dl, "expired": dl < 0, "expires_at": it["expires_at"]})

    # informational counts
    contracts_signed = await db.lumen_contracts.count_documents({"investor_id": user_id, "status": "signed"})
    certs = await db.lumen_certificates.count_documents({"investor_id": user_id, "status": {"$ne": "voided"}})

    blocked = any(it["required"] and it["fraction"] < 1.0 for it in items)
    return {
        "user_id": user_id, "full_name": prof.get("full_name"),
        "score": score, "score_band": ("ready" if score >= 90 else "partial" if score >= 60 else "incomplete"),
        "reasons": reasons, "items": items, "expirations": expirations,
        "institutional_ready": not blocked,
        "contracts_signed": contracts_signed, "certificates": certs,
        "ubo_count": ubo_count,
        "segment": prof.get("segment") or "retail",
    }


# ════════════════════════════════════════════════════════════════════════════
# Investor
# ════════════════════════════════════════════════════════════════════════════

@router.get("/investor/compliance")
async def my_compliance(user=Depends(get_current_user)):
    out = await _build_vault(_uid(user))
    out["email"] = user.get("email")
    out["slot_catalog"] = [{"slot": s, "label": SLOT_LABELS_UK[s]} for s in SLOTS]
    return out


class AttestIn(BaseModel):
    slot: str
    note: Optional[str] = None
    reference: Optional[str] = None
    valid_months: Optional[int] = 12


@router.post("/investor/compliance/attest")
async def attest_slot(payload: AttestIn, user=Depends(get_current_user),
                       _perm=Depends(_lr2_perm("compliance_profile", "write"))):
    if payload.slot not in SLOTS:
        raise HTTPException(status_code=400, detail="Невідомий тип документа")
    uid = _uid(user)
    now = _now()
    expires_at = now + timedelta(days=30 * int(payload.valid_months or 12)) if payload.valid_months else None
    doc = {
        "investor_id": uid, "slot": payload.slot, "status": "provided",
        "note": payload.note, "reference": payload.reference or "self-attested",
        "expires_at": expires_at, "updated_at": now,
    }
    await db.lumen_compliance_documents.update_one(
        {"investor_id": uid, "slot": payload.slot},
        {"$set": doc, "$setOnInsert": {"id": f"cdoc-{uuid.uuid4().hex[:12]}", "created_at": now}},
        upsert=True)
    await _audit(uid, "compliance.attest", f"Надано {SLOT_LABELS_UK[payload.slot]}", actor=uid)
    return await _build_vault(uid)


# ════════════════════════════════════════════════════════════════════════════
# Admin
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/compliance/registry")
async def admin_registry(filter: Optional[str] = None, _=Depends(require_admin)):
    items = []
    async for p in db.lumen_investor_profiles.find({}, {"_id": 0, "user_id": 1}):
        v = await _build_vault(p["user_id"])
        items.append({
            "user_id": v["user_id"], "full_name": v["full_name"], "segment": v["segment"],
            "score": v["score"], "score_band": v["score_band"],
            "institutional_ready": v["institutional_ready"],
            "gaps": len(v["reasons"]), "expiring": len(v["expirations"]),
        })
    if filter == "blocked":
        items = [i for i in items if not i["institutional_ready"]]
    elif filter == "expiring":
        items = [i for i in items if i["expiring"] > 0]
    elif filter == "ready":
        items = [i for i in items if i["institutional_ready"]]
    items.sort(key=lambda x: x["score"])
    avg = round(sum(i["score"] for i in items) / len(items)) if items else 0
    return {"items": items, "count": len(items), "avg_score": avg,
            "ready": sum(1 for i in items if i["institutional_ready"])}


@router.get("/admin/compliance/expirations")
async def admin_expirations(_=Depends(require_admin)):
    out = []
    async for p in db.lumen_investor_profiles.find({}, {"_id": 0, "user_id": 1, "full_name": 1}):
        v = await _build_vault(p["user_id"])
        for e in v["expirations"]:
            out.append({**e, "user_id": p["user_id"], "full_name": p.get("full_name")})
    out.sort(key=lambda x: (x["days_left"] if x["days_left"] is not None else 9999))
    return {"items": out, "count": len(out), "expired": sum(1 for e in out if e["expired"])}


@router.get("/admin/compliance/{user_id}")
async def admin_vault(user_id: str, _=Depends(require_admin)):
    return await _build_vault(user_id)


class VerifyIn(BaseModel):
    slot: str
    status: str  # verified | rejected


@router.post("/admin/compliance/{user_id}/verify")
async def admin_verify(user_id: str, payload: VerifyIn, admin=Depends(require_admin),
                        _perm=Depends(_lr2_perm("compliance_profile", "approve"))):
    if payload.slot not in SLOTS:
        raise HTTPException(status_code=400, detail="Невідомий тип документа")
    if payload.status not in ("verified", "rejected"):
        raise HTTPException(status_code=400, detail="Статус має бути verified або rejected")
    res = await db.lumen_compliance_documents.update_one(
        {"investor_id": user_id, "slot": payload.slot},
        {"$set": {"status": payload.status, "verified_by": _uid(admin), "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Документ не знайдено — інвестор ще не надав його")
    await _audit(user_id, "compliance.verify",
                 f"{SLOT_LABELS_UK[payload.slot]} → {payload.status}", actor=_uid(admin))
    return await _build_vault(user_id)


# ════════════════════════════════════════════════════════════════════════════
# Helpers + seed
# ════════════════════════════════════════════════════════════════════════════

async def _audit(user_id: str, action: str, summary: str, actor: Optional[str]) -> None:
    try:
        from lumen_audit import write_audit
        await write_audit(action=action, category="compliance", target_type="investor",
                          target_id=user_id, summary=summary)
    except Exception:
        pass


async def ensure_compliance_indexes() -> None:
    try:
        await db.lumen_compliance_documents.create_index(
            [("investor_id", 1), ("slot", 1)], unique=True)
    except Exception:
        logger.exception("compliance indexes failed")


async def seed_compliance_demo() -> dict:
    """Idempotent: attest realistic compliance slots for demo investors, leaving
    intentional gaps (e.g. maria missing SOF) so the score + reasons are visible."""
    await ensure_compliance_indexes()
    stats = {"slots_seeded": 0}
    now = _now()
    plan = {
        # full institutional onboarding
        "family@atlas.dev": [("sof", 24), ("aml_questionnaire", 24), ("tax_form", 24),
                             ("risk_acknowledgement", 24), ("voting_consent", 24)],
        "ihor.p@lumen.test": [("sof", 12), ("aml_questionnaire", 12), ("tax_form", 12),
                             ("risk_acknowledgement", 12)],
        # accredited but one item EXPIRED (SOF) to demo the expiration engine
        "olena.k@lumen.test": [("sof", -1), ("aml_questionnaire", 12), ("risk_acknowledgement", 12)],
        # retail, intentionally missing SOF + tax → low score
        "maria.s@lumen.test": [("risk_acknowledgement", 6)],
    }
    for email, slots in plan.items():
        u = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
        if not u:
            continue
        uid = u["user_id"]
        for slot, months in slots:
            exists = await db.lumen_compliance_documents.find_one({"investor_id": uid, "slot": slot})
            if exists:
                continue
            expires_at = now + timedelta(days=30 * months)  # negative months → already expired
            await db.lumen_compliance_documents.insert_one({
                "id": f"cdoc-{uuid.uuid4().hex[:12]}", "investor_id": uid, "slot": slot,
                "status": "verified", "reference": "seed_demo",
                "note": None, "expires_at": expires_at,
                "created_at": now, "updated_at": now,
            })
            stats["slots_seeded"] += 1
    return stats
