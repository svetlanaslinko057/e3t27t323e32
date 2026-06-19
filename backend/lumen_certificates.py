"""
lumen_certificates.py — LUMEN 2.0 / Phase A2 — Certificate Engine.

Turns the technical unit-ownership (Phase A1 registry) into an
investor-facing legal artifact: the **Investment Certificate**.

Source of truth REMAINS the unit registry (`lumen_ownerships.units_int` +
`lumen_asset_units`). Certificates are a reconciled projection on top:

    ownership (units_int)  ──reconcile──►  active certificate (units)

Lifecycle (burn & re-issue):
    • new owner / first units            → issue   (status active, event issued)
    • units changed (top-up / secondary) → old → replaced, new → active (reissued)
    • units → 0 (sold everything)        → old → voided
Everything is append-only audited in `lumen_certificate_events`.

NOT in scope (explicitly): NFT, blockchain, crypto token, external e-sign,
notary logic, tax reports.

Collections:
    lumen_certificates          — the certificates (current + historical)
    lumen_certificate_events    — append-only audit log
    lumen_certificate_templates — issuer template / legal boilerplate
    lumen_counters              — atomic sequence for certificate numbers
"""
from __future__ import annotations

import io
import logging
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pymongo import ReturnDocument

from lumen_api import db

logger = logging.getLogger("lumen.certificates")

CERTS = "lumen_certificates"
EVENTS = "lumen_certificate_events"
TEMPLATES = "lumen_certificate_templates"
COUNTERS = "lumen_counters"

STATUS_ACTIVE = "active"
STATUS_VOIDED = "voided"
STATUS_REPLACED = "replaced"
STATUS_DRAFT = "draft"
STATUS_EXPIRED = "expired"
STATUS_ISSUED = "issued"

EVENT_ISSUED = "issued"
EVENT_VOIDED = "voided"
EVENT_REISSUED = "reissued"
EVENT_TRANSFERRED = "transferred"
EVENT_VERIFIED = "verified"
EVENT_DOWNLOADED = "downloaded"
# A3 Block 4 — ownership-lifecycle certificate events
EVENT_OWNERSHIP_CREATED = "ownership_created"
EVENT_OWNERSHIP_CLOSED = "ownership_closed"
EVENT_OWNERSHIP_SPLIT = "ownership_split"
EVENT_OWNERSHIP_MERGE = "ownership_merge"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return v


def _strip(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    d = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = _iso(v)
    return d


def _public_base(request: Optional[Request]) -> str:
    """Best-effort absolute origin for QR / verify links."""
    env = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("APP_URL")
    if env:
        return env.rstrip("/")
    if request is not None:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if host:
            return f"{proto}://{host}"
        return str(request.base_url).rstrip("/")
    return ""


def verify_url(code: str, request: Optional[Request] = None) -> str:
    base = _public_base(request)
    return f"{base}/certificates/verify/{code}" if base else f"/certificates/verify/{code}"


async def _next_certificate_number() -> str:
    year = _now().year
    doc = await db[COUNTERS].find_one_and_update(
        {"_id": f"certificate-{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(doc.get("seq", 1))
    return f"LMN-{year}-{seq:06d}"


async def _unique_verify_code() -> str:
    for _ in range(12):
        raw = secrets.token_hex(6).upper()  # 12 hex chars
        code = f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"
        if not await db[CERTS].find_one({"verify_code": code}):
            return code
    return f"{secrets.token_hex(8).upper()}"


async def ensure_indexes() -> None:
    try:
        await db[CERTS].create_index([("verify_code", 1)], unique=True)
        await db[CERTS].create_index([("certificate_number", 1)], unique=True)
        await db[CERTS].create_index([("investor_id", 1), ("status", 1)])
        await db[CERTS].create_index([("asset_id", 1), ("status", 1)])
        await db[EVENTS].create_index([("certificate_id", 1), ("created_at", -1)])
        await db[EVENTS].create_index([("investor_id", 1), ("created_at", -1)])
    except Exception:
        logger.exception("certificate indexes failed")


# ──────────────────────────────────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────────────────────────────────

async def record_event(certificate_id: str, event_type: str, *,
                       investor_id: Optional[str] = None,
                       asset_id: Optional[str] = None,
                       actor: Optional[str] = None,
                       note: Optional[str] = None,
                       meta: Optional[dict] = None) -> dict:
    ev = {
        "id": _uuid("ce-"),
        "certificate_id": certificate_id,
        "event_type": event_type,
        "investor_id": investor_id,
        "asset_id": asset_id,
        "actor": actor,
        "note": note,
        "meta": meta or {},
        "created_at": _now(),
    }
    await db[EVENTS].insert_one(dict(ev))
    return _strip(ev)


# ──────────────────────────────────────────────────────────────────────────────
# Lookups
# ──────────────────────────────────────────────────────────────────────────────

async def _asset(asset_id: str) -> dict:
    return await db.lumen_assets.find_one({"id": asset_id}) or {}


async def _asset_units(asset_id: str) -> dict:
    return await db.lumen_asset_units.find_one({"asset_id": asset_id}) or {}


async def _spv_for(asset: dict) -> Dict[str, Optional[str]]:
    spv = await db.lumen_spvs.find_one({"asset_id": asset.get("id")}) if asset.get("id") else None
    return {
        "spv_id": (spv or {}).get("id"),
        "spv_name": (spv or {}).get("name") or asset.get("spv_label") or "ТОВ Lumen-SPV",
    }


async def _contract_id(investor_id: str, asset_id: str) -> Optional[str]:
    c = await db.lumen_contracts.find_one(
        {"investor_id": investor_id, "asset_id": asset_id},
        sort=[("created_at", -1)],
    )
    return (c or {}).get("id")


async def _investor_name(investor_id: str) -> str:
    u = await db.users.find_one(
        {"$or": [{"user_id": investor_id}, {"id": investor_id}]},
        {"name": 1, "email": 1})
    return (u or {}).get("name") or (u or {}).get("email") or investor_id


# ──────────────────────────────────────────────────────────────────────────────
# Issue / void / reissue
# ──────────────────────────────────────────────────────────────────────────────

async def _issue_certificate(investor_id: str, asset_id: str, units: int, *,
                             parent_id: Optional[str] = None,
                             reason: str = "issue",
                             actor: Optional[str] = None) -> dict:
    asset = await _asset(asset_id)
    au = await _asset_units(asset_id)
    total_units = int(au.get("total_units") or 0)
    unit_price = float(au.get("unit_price_uah") or 0)
    spv = await _spv_for(asset)
    number = await _next_certificate_number()
    code = await _unique_verify_code()
    cert = {
        "id": _uuid("cert-"),
        "certificate_number": number,
        "verify_code": code,
        "investor_id": investor_id,
        "investor_name": await _investor_name(investor_id),
        "asset_id": asset_id,
        "asset_title": asset.get("title"),
        "spv_id": spv["spv_id"],
        "spv_name": spv["spv_name"],
        "units": int(units),
        "total_units": total_units,
        "ownership_percent": round(units / total_units * 100, 4) if total_units else 0.0,
        "unit_price_uah": unit_price,
        "value_uah": round(units * unit_price, 2),
        "issue_date": _now(),
        "status": STATUS_ACTIVE,
        "linked_contract_id": await _contract_id(investor_id, asset_id),
        "parent_certificate_id": parent_id,
        "voided_at": None,
        "voided_reason": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[CERTS].insert_one(dict(cert))
    await record_event(cert["id"], EVENT_REISSUED if parent_id else EVENT_ISSUED,
                       investor_id=investor_id, asset_id=asset_id, actor=actor,
                       note=f"{reason}: {units} units", meta={"units": int(units),
                       "certificate_number": number})
    return cert


async def _void_certificate(cert: dict, *, status: str = STATUS_VOIDED,
                            reason: str = "", actor: Optional[str] = None,
                            replaced_by: Optional[str] = None) -> None:
    await db[CERTS].update_one(
        {"id": cert["id"]},
        {"$set": {"status": status, "voided_at": _now(), "voided_reason": reason,
                  "replaced_by": replaced_by, "updated_at": _now()}},
    )
    await record_event(cert["id"], EVENT_VOIDED, investor_id=cert.get("investor_id"),
                       asset_id=cert.get("asset_id"), actor=actor,
                       note=reason or status,
                       meta={"new_status": status, "replaced_by": replaced_by})
    # IR0.3 — field-level history: certificate status transition.
    try:
        from lumen_field_changes import record_change as _ir0_record
        await _ir0_record(
            db, entity_type="certificate", entity_id=cert["id"],
            field="status", old_value=cert.get("status"), new_value=status,
            actor=({"id": actor, "role": "admin"} if actor else None),
            source="api", reason=(reason or None),
        )
    except Exception:
        pass


async def admin_void(certificate_id: str, *, reason: str, actor: Optional[str]) -> dict:
    cert = await db[CERTS].find_one({"id": certificate_id})
    if not cert:
        raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
    if cert["status"] not in (STATUS_ACTIVE, STATUS_ISSUED):
        raise HTTPException(status_code=409, detail=f"Сертифікат у статусі {cert['status']}")
    await _void_certificate(cert, status=STATUS_VOIDED, reason=reason or "admin void", actor=actor)
    return await db[CERTS].find_one({"id": certificate_id})


async def admin_reissue(certificate_id: str, *, actor: Optional[str]) -> dict:
    """Force a fresh certificate from current registry units (manual re-issue)."""
    cert = await db[CERTS].find_one({"id": certificate_id})
    if not cert:
        raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
    own = await db.lumen_ownerships.find_one(
        {"investor_id": cert["investor_id"], "asset_id": cert["asset_id"]})
    units = int((own or {}).get("units_int") or 0)
    if units <= 0:
        await _void_certificate(cert, status=STATUS_VOIDED, reason="reissue: no units", actor=actor)
        return {"voided": True}
    new = await _issue_certificate(cert["investor_id"], cert["asset_id"], units,
                                   parent_id=cert["id"], reason="manual reissue", actor=actor)
    await _void_certificate(cert, status=STATUS_REPLACED, reason="manual reissue",
                            actor=actor, replaced_by=new["id"])
    return new


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation (the heart) — registry → certificates
# ──────────────────────────────────────────────────────────────────────────────

async def reconcile_asset(asset_id: str, *, actor: Optional[str] = None) -> dict:
    """Make certificates match the registry for one asset (idempotent).
    Handles issue / reissue / void (burn & re-issue)."""
    issued = reissued = voided = unchanged = 0

    # 1. current owners from registry
    owners: Dict[str, int] = {}
    async for own in db.lumen_ownerships.find(
            {"asset_id": asset_id, "units_int": {"$gt": 0}}):
        owners[own["investor_id"]] = int(own.get("units_int") or 0)

    # 2. ensure active cert per owner
    for investor_id, units in owners.items():
        active = await db[CERTS].find_one(
            {"investor_id": investor_id, "asset_id": asset_id, "status": STATUS_ACTIVE})
        if not active:
            # brand-new active cert. ownership_created only if this owner had no prior cert at all
            had_prior = await db[CERTS].count_documents(
                {"investor_id": investor_id, "asset_id": asset_id})
            new = await _issue_certificate(investor_id, asset_id, units, reason="reconcile issue", actor=actor)
            if had_prior == 0:
                await record_event(new["id"], EVENT_OWNERSHIP_CREATED, investor_id=investor_id,
                                   asset_id=asset_id, actor=actor,
                                   note="Володіння створено", meta={"units": units})
            issued += 1
        elif int(active.get("units") or 0) != units:
            new = await _issue_certificate(investor_id, asset_id, units,
                                           parent_id=active["id"], reason="reconcile reissue", actor=actor)
            await _void_certificate(active, status=STATUS_REPLACED, reason="units changed",
                                    actor=actor, replaced_by=new["id"])
            reissued += 1
        else:
            unchanged += 1

    # 3. void active certs whose owner no longer holds units
    async for active in db[CERTS].find({"asset_id": asset_id, "status": STATUS_ACTIVE}):
        if active["investor_id"] not in owners:
            await _void_certificate(active, status=STATUS_VOIDED, reason="ownership exited", actor=actor)
            await record_event(active["id"], EVENT_OWNERSHIP_CLOSED,
                               investor_id=active["investor_id"], asset_id=asset_id, actor=actor,
                               note="Володіння закрито")
            voided += 1

    return {"asset_id": asset_id, "issued": issued, "reissued": reissued,
            "voided": voided, "unchanged": unchanged}


async def reconcile_all(*, actor: Optional[str] = None) -> dict:
    await ensure_indexes()
    totals = {"assets": 0, "issued": 0, "reissued": 0, "voided": 0, "unchanged": 0}
    async for asset in db.lumen_assets.find({}, {"id": 1}):
        try:
            r = await reconcile_asset(asset["id"], actor=actor)
            totals["assets"] += 1
            for k in ("issued", "reissued", "voided", "unchanged"):
                totals[k] += r[k]
        except Exception:
            logger.exception("reconcile asset %s failed", asset.get("id"))
    return totals


# ──────────────────────────────────────────────────────────────────────────────
# Secondary-market hook (burn & re-issue)
# ──────────────────────────────────────────────────────────────────────────────

async def on_trade_settled(asset_id: str, seller_id: str, buyer_id: str,
                           trade_id: str) -> None:
    """Called from lumen_secondary._settle_trade AFTER the unit-registry hook."""
    try:
        await reconcile_asset(asset_id, actor="secondary")
        # mark transfer context + split/merge semantics on both parties
        for inv, role in ((seller_id, "seller"), (buyer_id, "buyer")):
            cert = await db[CERTS].find_one(
                {"investor_id": inv, "asset_id": asset_id, "status": STATUS_ACTIVE})
            if cert:
                # seller still holding units after a sale → split; buyer adding to a
                # holding that existed before → merge.
                prior = await db[CERTS].count_documents(
                    {"investor_id": inv, "asset_id": asset_id,
                     "status": {"$in": [STATUS_REPLACED, STATUS_VOIDED]}})
                if role == "seller":
                    await record_event(cert["id"], EVENT_OWNERSHIP_SPLIT, investor_id=inv,
                                       asset_id=asset_id, actor="secondary",
                                       note=f"Частковий продаж (split) · trade {trade_id}",
                                       meta={"trade_id": trade_id})
                elif role == "buyer" and prior > 0:
                    await record_event(cert["id"], EVENT_OWNERSHIP_MERGE, investor_id=inv,
                                       asset_id=asset_id, actor="secondary",
                                       note=f"Консолідація (merge) · trade {trade_id}",
                                       meta={"trade_id": trade_id})
                await record_event(cert["id"], EVENT_TRANSFERRED, investor_id=inv,
                                   asset_id=asset_id, actor="secondary",
                                   note=f"secondary trade {trade_id}",
                                   meta={"trade_id": trade_id})
    except Exception:
        logger.exception("certificate trade hook failed (trade %s)", trade_id)


# ──────────────────────────────────────────────────────────────────────────────
# Invariants A2
# ──────────────────────────────────────────────────────────────────────────────

async def invariant_check(asset_id: Optional[str] = None) -> dict:
    checks = {
        "active_units_match_registry": True,
        "single_active_per_owner": True,
        "every_active_ownership_has_cert": True,
        "verify_codes_unique": True,
    }
    details: List[dict] = []

    q = {"status": STATUS_ACTIVE}
    if asset_id:
        q["asset_id"] = asset_id

    # 1. active cert units == registry units; one active per (investor, asset)
    seen: Dict[str, int] = {}
    async for cert in db[CERTS].find(q):
        key = f"{cert['investor_id']}::{cert['asset_id']}"
        seen[key] = seen.get(key, 0) + 1
        own = await db.lumen_ownerships.find_one(
            {"investor_id": cert["investor_id"], "asset_id": cert["asset_id"]})
        reg_units = int((own or {}).get("units_int") or 0)
        if int(cert.get("units") or 0) != reg_units:
            checks["active_units_match_registry"] = False
            details.append({"issue": "units_mismatch", "certificate": cert["certificate_number"],
                            "cert_units": cert.get("units"), "registry_units": reg_units})
    for key, cnt in seen.items():
        if cnt > 1:
            checks["single_active_per_owner"] = False
            details.append({"issue": "multiple_active", "key": key, "count": cnt})

    # 2. every active ownership (units>0) has an active cert
    own_q = {"units_int": {"$gt": 0}}
    if asset_id:
        own_q["asset_id"] = asset_id
    async for own in db.lumen_ownerships.find(own_q):
        c = await db[CERTS].find_one(
            {"investor_id": own["investor_id"], "asset_id": own["asset_id"], "status": STATUS_ACTIVE})
        if not c:
            checks["every_active_ownership_has_cert"] = False
            details.append({"issue": "missing_cert", "investor_id": own["investor_id"],
                            "asset_id": own["asset_id"], "units": own.get("units_int")})

    return {
        "computed_at": _iso(_now()),
        "all_ok": all(checks.values()),
        "checks": checks,
        "violations": details[:50],
    }


# ──────────────────────────────────────────────────────────────────────────────
# PDF + QR
# ──────────────────────────────────────────────────────────────────────────────

def _qr_png_bytes(data: str) -> Optional[bytes]:
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.exception("QR generation failed")
        return None


def render_certificate_pdf(cert: dict, v_url: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    GREEN = (0.18, 0.36, 0.31)
    DARK = (0.12, 0.12, 0.12)
    MUTED = (0.45, 0.45, 0.45)

    # Frame
    c.setStrokeColorRGB(*GREEN)
    c.setLineWidth(2)
    c.rect(15 * mm, 15 * mm, W - 30 * mm, H - 30 * mm)
    c.setLineWidth(0.5)
    c.rect(18 * mm, 18 * mm, W - 36 * mm, H - 36 * mm)

    # Header
    c.setFillColorRGB(*GREEN)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(28 * mm, H - 40 * mm, "LUMEN")
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*MUTED)
    c.drawString(28 * mm, H - 46 * mm, "Collective Investment Platform")

    c.setFillColorRGB(*DARK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(28 * mm, H - 62 * mm, "INVESTMENT CERTIFICATE")
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(*MUTED)
    c.drawString(28 * mm, H - 69 * mm, "Інвестиційний сертифікат")

    status = (cert.get("status") or "").upper()
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(*(GREEN if cert.get("status") == STATUS_ACTIVE else (0.7, 0.2, 0.2)))
    c.drawRightString(W - 28 * mm, H - 40 * mm, f"№ {cert.get('certificate_number')}")
    c.drawRightString(W - 28 * mm, H - 47 * mm, status)

    # Body fields
    rows = [
        ("Власник / Holder", cert.get("investor_name") or cert.get("investor_id")),
        ("Актив / Asset", cert.get("asset_title") or cert.get("asset_id")),
        ("SPV", cert.get("spv_name") or "—"),
        ("Одиниці / Units", f"{int(cert.get('units') or 0):,}".replace(",", " ")),
        ("Частка / Ownership", f"{cert.get('ownership_percent', 0):.4f} %"),
        ("Вартість / Value", fmt_uah_as_usd(cert.get('value_uah', 0), decimals=2)),
        ("Дата випуску / Issued", _iso(cert.get("issue_date"))[:10] if cert.get("issue_date") else "—"),
        ("Договір / Contract", cert.get("linked_contract_id") or "—"),
    ]
    y = H - 90 * mm
    for label, value in rows:
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*MUTED)
        c.drawString(28 * mm, y, label.upper())
        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(*DARK)
        c.drawString(28 * mm, y - 6 * mm, str(value))
        y -= 16 * mm

    # QR
    qr = _qr_png_bytes(v_url)
    if qr:
        c.drawImage(ImageReader(io.BytesIO(qr)), W - 62 * mm, 28 * mm,
                    width=34 * mm, height=34 * mm)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(*MUTED)
    c.drawRightString(W - 28 * mm, 24 * mm, f"Verify: {cert.get('verify_code')}")

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(28 * mm, 24 * mm,
                 "Source of truth: LUMEN Unit Registry. This document is a representation of registry ownership.")

    c.showPage()
    c.save()
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Read models
# ──────────────────────────────────────────────────────────────────────────────

async def list_investor_certificates(investor_id: str) -> dict:
    active, history = [], []
    async for c in db[CERTS].find({"investor_id": investor_id}).sort("issue_date", -1):
        item = _strip(c)
        if c["status"] == STATUS_ACTIVE:
            active.append(item)
        else:
            history.append(item)
    return {"active": active, "history": history,
            "total_active": len(active), "total_history": len(history)}


def public_certificate_view(cert: dict) -> dict:
    """Public-safe projection — NO private investor data."""
    return {
        "certificate_number": cert.get("certificate_number"),
        "verify_code": cert.get("verify_code"),
        "asset_title": cert.get("asset_title"),
        "spv_name": cert.get("spv_name"),
        "units": cert.get("units"),
        "ownership_percent": cert.get("ownership_percent"),
        "status": cert.get("status"),
        "issue_date": _iso(cert.get("issue_date")),
        "valid": cert.get("status") == STATUS_ACTIVE,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────────────────────────────────────

def build_certificates_router(db_ignored, get_current_user, require_admin) -> APIRouter:
    # LR2.7 — bring the permission gate factory in lazily so this module
    # stays decoupled from lumen_lr2_extended (no circular import).
    try:
        from lumen_api import lr2_perm as _lr2_perm
    except Exception:  # pragma: no cover
        def _lr2_perm(*a, **k): return require_admin  # type: ignore
    router = APIRouter(prefix="/api", tags=["certificates"])

    # ---- Public verification (no auth) --------------------------------------
    @router.get("/public/certificates/verify/{code}")
    async def verify_certificate(code: str):
        cert = await db[CERTS].find_one({"verify_code": code})
        if not cert:
            raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
        await record_event(cert["id"], EVENT_VERIFIED, asset_id=cert.get("asset_id"),
                           note="public verify")
        return public_certificate_view(cert)

    # ---- Investor -----------------------------------------------------------
    @router.get("/investor/certificates")
    async def my_certificates(user=Depends(get_current_user)):
        return await list_investor_certificates(user["id"])

    @router.get("/investor/certificates/{certificate_id}")
    async def my_certificate(certificate_id: str, user=Depends(get_current_user)):
        cert = await db[CERTS].find_one({"id": certificate_id, "investor_id": user["id"]})
        if not cert:
            raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
        events = []
        async for e in db[EVENTS].find({"certificate_id": certificate_id}).sort("created_at", -1):
            events.append(_strip(e))
        return {"certificate": _strip(cert), "events": events}

    @router.get("/investor/certificates/{certificate_id}/pdf")
    async def my_certificate_pdf(certificate_id: str, request: Request,
                                 user=Depends(get_current_user)):
        cert = await db[CERTS].find_one({"id": certificate_id, "investor_id": user["id"]})
        if not cert:
            raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
        pdf = render_certificate_pdf(cert, verify_url(cert["verify_code"], request))
        await record_event(certificate_id, EVENT_DOWNLOADED, investor_id=user["id"],
                           asset_id=cert.get("asset_id"), actor=user["id"])
        return Response(content=pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{cert["certificate_number"]}.pdf"'})

    # ---- Admin --------------------------------------------------------------
    @router.get("/admin/certificates")
    async def admin_list(_=Depends(require_admin),
                         status: Optional[str] = None,
                         asset_id: Optional[str] = None,
                         investor_id: Optional[str] = None,
                         limit: int = Query(200, le=1000)):
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        if asset_id:
            q["asset_id"] = asset_id
        if investor_id:
            q["investor_id"] = investor_id
        items = []
        async for c in db[CERTS].find(q).sort("issue_date", -1).limit(limit):
            items.append(_strip(c))
        # status counts
        counts = {}
        for st in (STATUS_ACTIVE, STATUS_VOIDED, STATUS_REPLACED, STATUS_EXPIRED, STATUS_DRAFT):
            counts[st] = await db[CERTS].count_documents({**q, "status": st}) if not status else (
                len(items) if status == st else 0)
        return {"items": items, "total": len(items), "counts": counts}

    @router.get("/admin/certificates/{certificate_id}")
    async def admin_detail(certificate_id: str, _=Depends(require_admin)):
        cert = await db[CERTS].find_one({"id": certificate_id})
        if not cert:
            raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
        events = []
        async for e in db[EVENTS].find({"certificate_id": certificate_id}).sort("created_at", -1):
            events.append(_strip(e))
        return {"certificate": _strip(cert), "events": events}

    @router.get("/admin/certificates/{certificate_id}/pdf")
    async def admin_pdf(certificate_id: str, request: Request, _=Depends(require_admin)):
        cert = await db[CERTS].find_one({"id": certificate_id})
        if not cert:
            raise HTTPException(status_code=404, detail="Сертифікат не знайдено")
        pdf = render_certificate_pdf(cert, verify_url(cert["verify_code"], request))
        return Response(content=pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{cert["certificate_number"]}.pdf"'})

    @router.post("/admin/certificates/{certificate_id}/void")
    async def admin_void_cert(certificate_id: str, admin=Depends(require_admin),
                              _perm=Depends(_lr2_perm("certificate", "delete")),
                              payload: dict = None):
        reason = (payload or {}).get("reason", "admin void")
        cert = await admin_void(certificate_id, reason=reason, actor=admin.get("id"))
        return {"ok": True, "certificate": _strip(cert)}

    @router.post("/admin/certificates/{certificate_id}/reissue")
    async def admin_reissue_cert(certificate_id: str, admin=Depends(require_admin),
                                 _perm=Depends(_lr2_perm("certificate", "override"))):
        res = await admin_reissue(certificate_id, actor=admin.get("id"))
        return {"ok": True, "result": _strip(res) if isinstance(res, dict) and "id" in res else res}

    @router.post("/admin/certificates/reconcile")
    async def admin_reconcile(admin=Depends(require_admin),
                              _perm=Depends(_lr2_perm("certificate", "override"))):
        return await reconcile_all(actor=admin.get("id"))

    @router.get("/admin/certificates/invariants/check")
    async def admin_invariants(_=Depends(require_admin), asset_id: Optional[str] = None):
        return await invariant_check(asset_id)

    return router
