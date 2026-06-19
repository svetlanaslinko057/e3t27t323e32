"""
LUMEN 2.0 — Phase G11 — Accreditation OS (Investor Profile 2.0)
================================================================

Far more than KYC. KYC answers "is this a real person?". Accreditation answers
"WHAT can this investor access, and on what basis?".

Investor lifecycle tiers (layered ON TOP of the E6 segment engine — segments
retail/qualified/strategic/institutional remain stable for capital-formation
priority; this module adds a richer, compliance-driven access tier):

    Visitor → Retail → Qualified → Accredited → Professional → Institutional

Investor Profile 2.0 blocks (nested in lumen_investor_profiles — NO migration):
    personal · financial · experience · jurisdiction · tax · accreditation

Accreditation Review state machine:
    pending → documents_requested → under_review → approved
                                              ↘ rejected
                                  approved → expired

Asset Eligibility Engine — every asset carries an access_level:
    retail_allowed · qualified_only · accredited_only · institutional_only
Eligibility combines: asset access_level + accreditation level + the G8
compliance matrix (max ticket / accreditation / UBO).

Everything DERIVES from real collections — no mocks.
"""
from __future__ import annotations

import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _strip_mongo, _now

logger = logging.getLogger("lumen.accreditation")
router = APIRouter(prefix="/api", tags=["lumen-accreditation-os"])

# ── Accreditation tiers ──────────────────────────────────────────────────────
LEVELS = ("visitor", "retail", "qualified", "accredited", "professional", "institutional")
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
LEVEL_LABELS_UK = {
    "visitor": "Відвідувач", "retail": "Роздрібний", "qualified": "Кваліфікований",
    "accredited": "Акредитований", "professional": "Професійний", "institutional": "Інституційний",
}

REVIEW_STATES = ("pending", "documents_requested", "under_review", "approved", "rejected", "expired")
REVIEW_LABELS_UK = {
    "pending": "Не подано", "documents_requested": "Запит документів",
    "under_review": "На розгляді", "approved": "Підтверджено",
    "rejected": "Відхилено", "expired": "Прострочено",
}
# legal transitions (admin-driven, except submit)
REVIEW_TRANSITIONS = {
    "pending": {"under_review", "documents_requested"},
    "documents_requested": {"under_review", "rejected"},
    "under_review": {"approved", "rejected", "documents_requested"},
    "approved": {"expired", "under_review"},
    "rejected": {"under_review"},
    "expired": {"under_review"},
}

ASSET_ACCESS_LEVELS = ("retail_allowed", "qualified_only", "accredited_only", "institutional_only")
ASSET_ACCESS_LABELS_UK = {
    "retail_allowed": "Доступно роздрібним", "qualified_only": "Лише кваліфікованим",
    "accredited_only": "Лише акредитованим", "institutional_only": "Лише інституційним",
}
# minimum accreditation level required for each asset access level
ACCESS_MIN_LEVEL = {
    "retail_allowed": "retail", "qualified_only": "qualified",
    "accredited_only": "accredited", "institutional_only": "institutional",
}

RISK_APPETITES = ("conservative", "balanced", "growth", "aggressive")
INVESTMENT_HORIZONS = ("short", "medium", "long")

# Accreditation thresholds (illustrative, UAH). Drives the SUGGESTED level the
# admin can confirm; the authoritative level is always admin-approved.
ACCREDITED_NET_WORTH = 6_000_000      # ~ €150k
ACCREDITED_INCOME = 2_000_000         # ~ €50k / yr
PROFESSIONAL_NET_WORTH = 20_000_000
PROFESSIONAL_LIQUID = 4_000_000


def _uid(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    return user.get("id") or user.get("user_id")


def _is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    return user.get("role") == "admin" or "admin" in (user.get("roles") or [])


async def _profile(user_id: str) -> dict:
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id})
    if prof:
        return prof
    u = await db.users.find_one({"$or": [{"user_id": user_id}, {"id": user_id}]}) or {}
    now = _now()
    prof = {
        "id": f"prof-{user_id[-12:]}", "user_id": user_id,
        "full_name": u.get("name"), "kyc_status": u.get("kyc_status") or "not_started",
        "accreditation_status": "none", "created_at": now, "updated_at": now,
    }
    await db.lumen_investor_profiles.insert_one(prof)
    return prof


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _suggested_level(prof: dict) -> str:
    """Derive a suggested accreditation tier from the financial profile.
    Admin confirms the authoritative level; this is guidance only."""
    fin = prof.get("financial") or {}
    nw = _f(fin.get("net_worth_uah"))
    income = _f(fin.get("annual_income_uah"))
    liquid = _f(fin.get("liquid_assets_uah"))
    if nw >= PROFESSIONAL_NET_WORTH and liquid >= PROFESSIONAL_LIQUID:
        return "professional"
    if nw >= ACCREDITED_NET_WORTH or income >= ACCREDITED_INCOME:
        return "accredited"
    if nw > 0 or income > 0:
        return "qualified"
    return "retail"


def _profile2_complete(prof: dict) -> list[str]:
    missing = []
    fin = prof.get("financial") or {}
    exp = prof.get("experience") or {}
    jur = prof.get("jurisdiction") or {}
    if not _f(fin.get("annual_income_uah")):
        missing.append("financial.annual_income_uah")
    if not _f(fin.get("net_worth_uah")):
        missing.append("financial.net_worth_uah")
    if not (fin.get("risk_appetite")):
        missing.append("financial.risk_appetite")
    if exp.get("years_investing") in (None, ""):
        missing.append("experience.years_investing")
    if not (jur.get("residency_country") or prof.get("residency_country")):
        missing.append("jurisdiction.residency_country")
    return missing


def _accreditation_view(prof: dict) -> dict:
    acc = prof.get("accreditation") or {}
    level = acc.get("level") or "retail"
    status = acc.get("review_status") or "pending"
    return {
        "level": level, "level_label": LEVEL_LABELS_UK.get(level, level),
        "level_rank": LEVEL_RANK.get(level, 1),
        "review_status": status, "review_status_label": REVIEW_LABELS_UK.get(status, status),
        "submitted_at": acc.get("submitted_at"), "reviewed_at": acc.get("reviewed_at"),
        "reviewer_id": acc.get("reviewer_id"), "basis": acc.get("basis"),
        "expires_at": acc.get("expires_at"), "notes": acc.get("notes"),
        "suggested_level": _suggested_level(prof),
    }


def _profile2_view(prof: dict) -> dict:
    return {
        "user_id": prof.get("user_id"),
        "full_name": prof.get("full_name"),
        "personal": prof.get("personal") or {
            "full_name": prof.get("full_name"), "phone": prof.get("phone"),
            "date_of_birth": prof.get("date_of_birth")},
        "financial": prof.get("financial") or {},
        "experience": prof.get("experience") or {},
        "jurisdiction": prof.get("jurisdiction") or {
            "residency_country": prof.get("residency_country"),
            "citizenship": prof.get("country")},
        "tax": prof.get("tax") or {"tax_id": prof.get("tax_id")},
        "accreditation": _accreditation_view(prof),
        "segment": prof.get("segment") or "retail",
        "kyc_status": prof.get("kyc_status") or "not_started",
        "missing_for_submit": _profile2_complete(prof),
    }


async def _effective_level(user_id: str, prof: Optional[dict] = None) -> str:
    """The authoritative access tier: admin-approved accreditation level if the
    review is approved & not expired; otherwise falls back to retail (or the
    investor's E6 segment if higher and institutional)."""
    if prof is None:
        prof = await _profile(user_id)
    acc = prof.get("accreditation") or {}
    if acc.get("review_status") == "approved":
        lvl = acc.get("level") or "retail"
        return lvl if lvl in LEVEL_RANK else "retail"
    # not approved → fall back to a conservative mapping of E6 segment
    seg = prof.get("segment") or "retail"
    seg_to_level = {"retail": "retail", "qualified": "qualified",
                    "strategic": "qualified", "institutional": "institutional"}
    return seg_to_level.get(seg, "retail")


# ════════════════════════════════════════════════════════════════════════════
# Payloads
# ════════════════════════════════════════════════════════════════════════════

class FinancialBlock(BaseModel):
    annual_income_uah: Optional[float] = None
    net_worth_uah: Optional[float] = None
    liquid_assets_uah: Optional[float] = None
    investment_horizon: Optional[str] = None
    risk_appetite: Optional[str] = None


class ExperienceBlock(BaseModel):
    years_investing: Optional[int] = None
    asset_classes: Optional[list] = None
    real_estate_experience: Optional[str] = None
    private_markets_experience: Optional[str] = None


class JurisdictionBlock(BaseModel):
    residency_country: Optional[str] = None
    citizenship: Optional[str] = None
    is_us_person: Optional[bool] = None
    is_pep: Optional[bool] = None


class TaxBlock(BaseModel):
    tax_id: Optional[str] = None
    tax_residence: Optional[str] = None
    tax_form: Optional[str] = None  # w8 / w9 / none


class Profile2Patch(BaseModel):
    personal: Optional[dict] = None
    financial: Optional[FinancialBlock] = None
    experience: Optional[ExperienceBlock] = None
    jurisdiction: Optional[JurisdictionBlock] = None
    tax: Optional[TaxBlock] = None


class TransitionIn(BaseModel):
    to_status: str
    level: Optional[str] = None
    note: Optional[str] = None
    basis: Optional[str] = None
    expires_in_days: Optional[int] = 365


class AssetAccessIn(BaseModel):
    access_level: str


# ════════════════════════════════════════════════════════════════════════════
# Investor — Profile 2.0 + accreditation
# ════════════════════════════════════════════════════════════════════════════

@router.get("/investor/accreditation")
async def my_accreditation(user=Depends(get_current_user)):
    prof = await _profile(_uid(user))
    out = _profile2_view(prof)
    out["email"] = user.get("email")
    out["effective_level"] = await _effective_level(_uid(user), prof)
    return out


@router.patch("/investor/accreditation/profile")
async def patch_profile2(payload: Profile2Patch, user=Depends(get_current_user)):
    prof = await _profile(_uid(user))
    acc = prof.get("accreditation") or {}
    if acc.get("review_status") in ("under_review",):
        raise HTTPException(status_code=409, detail="Анкета на розгляді — редагування заблоковано")
    patch: dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    for block in ("personal", "financial", "experience", "jurisdiction", "tax"):
        if block in data and data[block] is not None:
            existing = prof.get(block) or {}
            incoming = {k: v for k, v in (data[block] or {}).items() if v is not None}
            patch[block] = {**existing, **incoming}
    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    patch["updated_at"] = _now()
    await db.lumen_investor_profiles.update_one({"user_id": _uid(user)}, {"$set": patch})
    prof = await db.lumen_investor_profiles.find_one({"user_id": _uid(user)})
    return _profile2_view(prof)


@router.post("/investor/accreditation/submit")
async def submit_accreditation(user=Depends(get_current_user)):
    uid = _uid(user)
    prof = await _profile(uid)
    missing = _profile2_complete(prof)
    if missing:
        raise HTTPException(status_code=400,
                            detail="Заповніть профіль перед поданням: " + ", ".join(missing))
    acc = prof.get("accreditation") or {}
    if acc.get("review_status") == "under_review":
        raise HTTPException(status_code=409, detail="Анкету вже подано на розгляд")
    new_acc = {**acc, "review_status": "under_review", "submitted_at": _now(),
               "suggested_level": _suggested_level(prof)}
    await db.lumen_investor_profiles.update_one(
        {"user_id": uid}, {"$set": {"accreditation": new_acc, "updated_at": _now()}})
    await _event(uid, "submitted", actor=uid,
                 note="Інвестор подав анкету акредитації", to_status="under_review")
    prof = await db.lumen_investor_profiles.find_one({"user_id": uid})
    return _profile2_view(prof)


@router.get("/investor/eligibility")
async def my_eligibility(asset_id: str, amount: Optional[float] = None,
                         user=Depends(get_current_user)):
    return await _eligibility(_uid(user), asset_id, amount)


async def _eligibility(user_id: str, asset_id: str, amount: Optional[float]) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    access = asset.get("access_level") or "retail_allowed"
    required = ACCESS_MIN_LEVEL.get(access, "retail")
    prof = await _profile(user_id)
    level = await _effective_level(user_id, prof)
    blockers: list[str] = []
    warnings: list[str] = []

    if LEVEL_RANK.get(level, 0) < LEVEL_RANK.get(required, 0):
        blockers.append(
            f"Потрібен рівень «{LEVEL_LABELS_UK[required]}», ваш — «{LEVEL_LABELS_UK.get(level, level)}»")

    # G8 compliance matrix integration (max ticket / accreditation / UBO)
    try:
        from lumen_institutional_os import _matrix, DEFAULT_MATRIX, _investor_segment as _g8_seg
        seg = await _g8_seg(user_id)
        m = await _matrix()
        rule = m.get(seg) or DEFAULT_MATRIX.get(seg, {})
        max_ticket = rule.get("max_ticket_uah")
        if amount is not None and max_ticket is not None and float(amount) > float(max_ticket):
            blockers.append(f"Сума перевищує ліміт сегмента: {fmt_uah_as_usd(max_ticket)}")
        if rule.get("requires_accreditation") and prof.get("accreditation", {}).get("review_status") != "approved":
            warnings.append("Для цього сегмента потрібна підтверджена акредитація")
        if rule.get("requires_ubo"):
            has_ubo = await db.lumen_beneficial_owners.count_documents({"investor_id": user_id})
            if not has_ubo:
                warnings.append("Потрібно задекларувати кінцевого бенефіціара (UBO)")
    except Exception:
        logger.exception("eligibility G8 integration failed")

    return {
        "asset_id": asset_id, "asset_title": asset.get("title"),
        "access_level": access, "access_level_label": ASSET_ACCESS_LABELS_UK.get(access, access),
        "required_level": required, "required_level_label": LEVEL_LABELS_UK.get(required),
        "your_level": level, "your_level_label": LEVEL_LABELS_UK.get(level, level),
        "eligible": len(blockers) == 0,
        "blockers": blockers, "warnings": warnings,
    }


# ════════════════════════════════════════════════════════════════════════════
# Admin — accreditation review queue + transitions + asset access
# ════════════════════════════════════════════════════════════════════════════

@router.get("/admin/accreditation/queue")
async def admin_queue(status: Optional[str] = None, _=Depends(require_admin)):
    q: dict = {}
    if status and status in REVIEW_STATES:
        q["accreditation.review_status"] = status
    items = []
    async for p in db.lumen_investor_profiles.find(q, {"_id": 0}).sort("updated_at", -1):
        acc = _accreditation_view(p)
        items.append({
            "user_id": p.get("user_id"), "full_name": p.get("full_name"),
            "segment": p.get("segment") or "retail", "kyc_status": p.get("kyc_status"),
            "accreditation": acc, "missing": _profile2_complete(p),
        })
    # counts by state
    counts = {s: 0 for s in REVIEW_STATES}
    for it in items:
        counts[it["accreditation"]["review_status"]] = counts.get(it["accreditation"]["review_status"], 0) + 1
    return {"items": items, "counts": counts}


@router.get("/admin/accreditation/{user_id}")
async def admin_accreditation_card(user_id: str, _=Depends(require_admin)):
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not prof:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    out = _profile2_view(prof)
    events = []
    async for e in db.lumen_accreditation_events.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1):
        events.append(_strip_mongo(e))
    out["events"] = events
    out["effective_level"] = await _effective_level(user_id, prof)
    return out


@router.post("/admin/accreditation/{user_id}/transition")
async def admin_transition(user_id: str, payload: TransitionIn, admin=Depends(require_admin)):
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id})
    if not prof:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    acc = prof.get("accreditation") or {}
    cur = acc.get("review_status") or "pending"
    to = payload.to_status
    if to not in REVIEW_STATES:
        raise HTTPException(status_code=400, detail="Невідомий статус")
    allowed = REVIEW_TRANSITIONS.get(cur, set())
    if to != cur and to not in allowed:
        raise HTTPException(status_code=409,
                            detail=f"Перехід {cur} → {to} не дозволено")
    new_acc = dict(acc)
    new_acc["review_status"] = to
    if to == "approved":
        lvl = payload.level or acc.get("level") or _suggested_level(prof)
        if lvl not in LEVEL_RANK:
            raise HTTPException(status_code=400, detail="Невідомий рівень акредитації")
        new_acc["level"] = lvl
        new_acc["reviewed_at"] = _now()
        new_acc["reviewer_id"] = _uid(admin)
        new_acc["basis"] = payload.basis or "admin_review"
        if payload.expires_in_days:
            from datetime import timedelta
            new_acc["expires_at"] = _now() + timedelta(days=int(payload.expires_in_days))
        # mirror to legacy field used elsewhere
        await db.lumen_investor_profiles.update_one(
            {"user_id": user_id}, {"$set": {"accreditation_status": "verified"}})
    if payload.note:
        new_acc["notes"] = payload.note
    await db.lumen_investor_profiles.update_one(
        {"user_id": user_id}, {"$set": {"accreditation": new_acc, "updated_at": _now()}})
    # IR0.3 — field-level history: investor accreditation status transition.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="investor", entity_id=user_id,
            field="accreditation_status", old_value=cur, new_value=to,
            actor=admin, source="api", reason=(payload.note or None),
        )
    except Exception:
        pass
    await _event(user_id, "transition", actor=_uid(admin),
                 note=payload.note or "", to_status=to, level=new_acc.get("level"))
    prof = await db.lumen_investor_profiles.find_one({"user_id": user_id}, {"_id": 0})
    return await admin_accreditation_card(user_id, admin)


@router.get("/admin/accreditation/assets/access")
async def admin_asset_access(_=Depends(require_admin)):
    items = []
    async for a in db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1, "category": 1,
                                             "access_level": 1, "status": 1}):
        lvl = a.get("access_level") or "retail_allowed"
        items.append({"id": a["id"], "title": a.get("title"), "category": a.get("category"),
                      "status": a.get("status"), "access_level": lvl,
                      "access_level_label": ASSET_ACCESS_LABELS_UK.get(lvl, lvl)})
    return {"items": items, "levels": [{"value": v, "label": ASSET_ACCESS_LABELS_UK[v]}
                                       for v in ASSET_ACCESS_LEVELS]}


@router.patch("/admin/accreditation/assets/{asset_id}/access")
async def admin_set_asset_access(asset_id: str, payload: AssetAccessIn, _=Depends(require_admin)):
    if payload.access_level not in ASSET_ACCESS_LEVELS:
        raise HTTPException(status_code=400, detail="Невідомий рівень доступу")
    res = await db.lumen_assets.update_one(
        {"id": asset_id}, {"$set": {"access_level": payload.access_level, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return {"ok": True, "asset_id": asset_id, "access_level": payload.access_level}


# ════════════════════════════════════════════════════════════════════════════
# Events + indexes + idempotent demo seed
# ════════════════════════════════════════════════════════════════════════════

async def _event(user_id: str, kind: str, *, actor: Optional[str], note: str = "",
                 to_status: Optional[str] = None, level: Optional[str] = None) -> None:
    import uuid as _uuid
    doc = {
        "id": f"acev-{_uuid.uuid4().hex[:12]}", "user_id": user_id, "kind": kind,
        "to_status": to_status, "level": level, "actor": actor, "note": note,
        "created_at": _now(),
    }
    try:
        await db.lumen_accreditation_events.insert_one(doc)
    except Exception:
        logger.exception("accreditation event insert failed")
    # also write to the global audit log if available
    try:
        from lumen_audit import write_audit
        await write_audit(action=f"accreditation.{kind}", category="compliance",
                          target_type="investor", target_id=user_id,
                          summary=note or f"accreditation {kind} → {to_status}",
                          diff={"to_status": to_status, "level": level})
    except Exception:
        pass


async def ensure_accreditation_indexes() -> None:
    try:
        await db.lumen_accreditation_events.create_index([("user_id", 1), ("created_at", -1)])
        await db.lumen_investor_profiles.create_index([("accreditation.review_status", 1)])
    except Exception:
        logger.exception("accreditation indexes failed")


async def seed_accreditation_demo() -> dict:
    """Idempotent: enrich existing demo investors with Profile 2.0 + accreditation,
    and tag a couple of assets with elevated access levels for demonstration."""
    await ensure_accreditation_indexes()
    stats = {"profiles_enriched": 0, "assets_tagged": 0}

    plan = {
        "family@atlas.dev": {
            "level": "institutional", "status": "approved",
            "financial": {"annual_income_uah": 12_000_000, "net_worth_uah": 250_000_000,
                          "liquid_assets_uah": 60_000_000, "investment_horizon": "long",
                          "risk_appetite": "growth"},
            "experience": {"years_investing": 18, "asset_classes": ["real_estate", "private_equity", "funds"],
                           "real_estate_experience": "extensive", "private_markets_experience": "extensive"},
        },
        "ihor.p@lumen.test": {
            "level": "professional", "status": "approved",
            "financial": {"annual_income_uah": 3_500_000, "net_worth_uah": 28_000_000,
                          "liquid_assets_uah": 6_000_000, "investment_horizon": "long",
                          "risk_appetite": "aggressive"},
            "experience": {"years_investing": 11, "asset_classes": ["real_estate", "stocks"],
                           "real_estate_experience": "moderate", "private_markets_experience": "moderate"},
        },
        "olena.k@lumen.test": {
            "level": "accredited", "status": "approved",
            "financial": {"annual_income_uah": 2_200_000, "net_worth_uah": 7_500_000,
                          "liquid_assets_uah": 2_000_000, "investment_horizon": "medium",
                          "risk_appetite": "balanced"},
            "experience": {"years_investing": 6, "asset_classes": ["real_estate"],
                           "real_estate_experience": "moderate", "private_markets_experience": "beginner"},
        },
        "maria.s@lumen.test": {
            "level": "retail", "status": "under_review",
            "financial": {"annual_income_uah": 600_000, "net_worth_uah": 900_000,
                          "liquid_assets_uah": 300_000, "investment_horizon": "short",
                          "risk_appetite": "conservative"},
            "experience": {"years_investing": 1, "asset_classes": ["real_estate"],
                           "real_estate_experience": "beginner", "private_markets_experience": "none"},
        },
    }

    from datetime import timedelta
    for email, spec in plan.items():
        u = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
        if not u:
            continue
        uid = u["user_id"]
        prof = await _profile(uid)
        acc = prof.get("accreditation") or {}
        if acc.get("review_status"):
            continue  # already enriched
        new_acc = {
            "level": spec["level"], "review_status": spec["status"],
            "submitted_at": _now(),
        }
        if spec["status"] == "approved":
            new_acc["reviewed_at"] = _now()
            new_acc["reviewer_id"] = "system"
            new_acc["basis"] = "seed_demo"
            new_acc["expires_at"] = _now() + timedelta(days=365)
        await db.lumen_investor_profiles.update_one(
            {"user_id": uid},
            {"$set": {"financial": spec["financial"], "experience": spec["experience"],
                      "jurisdiction": {"residency_country": "UA", "citizenship": "UA",
                                       "is_us_person": False, "is_pep": False},
                      "accreditation": new_acc,
                      "accreditation_status": "verified" if spec["status"] == "approved" else "self_declared",
                      "updated_at": _now()}})
        stats["profiles_enriched"] += 1

    # tag assets with elevated access for demonstration (idempotent)
    access_plan = {
        "asset-lavr-tc": "qualified_only",
        "asset-odessa-apartments": "accredited_only",
        "asset-stoyanka-land": "institutional_only",
    }
    for asset_id, lvl in access_plan.items():
        a = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0, "access_level": 1})
        if a is not None and not a.get("access_level"):
            await db.lumen_assets.update_one({"id": asset_id}, {"$set": {"access_level": lvl}})
            stats["assets_tagged"] += 1

    return stats
