"""
LUMEN Asset Content Platform — Sprint 5.

The trust layer around assets. Investors decide with their eyes: before the
payment rail matters, the platform must give them something to study.

Adds per-asset:

    • gallery (multiple photos)          — stored on the asset document
    • videos (YouTube/Vimeo/self-hosted) — stored on the asset document
    • team / risks / exit_strategy       — stored on the asset document
    • updates  (lumen_asset_updates)     — the asset's internal blog
    • reports  (lumen_asset_reports)     — monthly / quarterly / annual
    • documents (lumen_asset_documents)  — valuation, audit, lease, model…
    • Q&A      (lumen_asset_questions)   — investor asks, admin answers,
                                           answered are public
    • SPV      (lumen_spvs)              — legal wrapper entity
                                           (Asset → SPV → Investors)

Files live on local disk (mock object storage) under uploads/asset_content/.

Endpoints (all under /api):

  Public / investor:
    GET  /assets/{id}/updates                  published updates (pinned first)
    GET  /assets/{id}/reports                  published reports
    GET  /assets/{id}/reports/{rid}/download
    GET  /assets/{id}/documents                metadata (investors-only marked)
    GET  /assets/{id}/documents/{did}/download (auth gate for `investors`)
    GET  /assets/{id}/questions                answered (+ own pending if auth)
    POST /investor/assets/{id}/questions       ask a question (auth)
    GET  /assets/{id}/spv                      public SPV card

  Admin:
    PATCH /admin/assets/{id}/content           gallery/videos/team/risks/exit
    GET/POST   /admin/assets/{id}/updates      PATCH/DELETE /admin/asset-updates/{uid}
    GET/POST   /admin/assets/{id}/reports      PATCH/DELETE /admin/asset-reports/{rid}
    GET/POST   /admin/assets/{id}/documents    DELETE /admin/asset-documents/{did}
    GET  /admin/questions                      queue + counts (filter by status/asset)
    POST /admin/questions/{qid}/answer         publish an answer
    POST /admin/questions/{qid}/hide           hide from public
    POST /admin/questions/{qid}/restore        pending again
    GET/POST   /admin/spvs                     PATCH/DELETE /admin/spvs/{id}
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from lumen_api import db, get_current_user, require_admin, _now, _iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["lumen-asset-content"])

_UPLOAD_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "uploads", "asset_content")
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
_ALLOWED_DOC_CT = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg", "image/webp",
}

UPDATE_KINDS = {"milestone", "news", "general"}
UPDATE_KIND_LABELS = {"milestone": "Віха проєкту", "news": "Новина", "general": "Оновлення"}
REPORT_TYPES = {"monthly", "quarterly", "annual"}
REPORT_TYPE_LABELS = {"monthly": "Місячний", "quarterly": "Квартальний", "annual": "Річний"}
DOC_TYPES = {"valuation", "audit", "lease_agreement", "financial_model", "permit", "legal", "other"}
DOC_TYPE_LABELS = {
    "valuation": "Звіт про оцінку",
    "audit": "Аудит",
    "lease_agreement": "Договір оренди",
    "financial_model": "Фінансова модель",
    "permit": "Дозвільна документація",
    "legal": "Юридичні документи",
    "other": "Інше",
}
QUESTION_STATUSES = {"pending", "answered", "hidden"}
SPV_STATUSES = {"forming", "active", "dissolved"}
SPV_STATUS_LABELS = {"forming": "реєструється", "active": "активна", "dissolved": "ліквідована"}
RISK_SEVERITIES = {"low", "medium", "high"}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _optional_user(request: Request) -> Optional[dict]:
    """Like get_current_user but returns None for anonymous visitors."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def _get_asset_or_404(asset_id: str) -> dict:
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return asset


def _clean_str(v: Any, max_len: int = 2000) -> str:
    return str(v or "").strip()[:max_len]


_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{6,20})")
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d{6,12})")


def _video_meta(url: str, title: str = "") -> dict:
    """Detect provider and build an embeddable URL."""
    url = _clean_str(url, 500)
    m = _YT_RE.search(url)
    if m:
        return {"url": url, "title": _clean_str(title, 200), "provider": "youtube",
                "embed_url": f"https://www.youtube.com/embed/{m.group(1)}"}
    m = _VIMEO_RE.search(url)
    if m:
        return {"url": url, "title": _clean_str(title, 200), "provider": "vimeo",
                "embed_url": f"https://player.vimeo.com/video/{m.group(1)}"}
    return {"url": url, "title": _clean_str(title, 200), "provider": "file",
            "embed_url": url}


def _update_out(u: dict) -> dict:
    return {
        "id": u["id"], "asset_id": u["asset_id"],
        "kind": u.get("kind", "general"),
        "kind_label": UPDATE_KIND_LABELS.get(u.get("kind", "general"), "Оновлення"),
        "title": u.get("title", ""), "body": u.get("body", ""),
        "pinned": bool(u.get("pinned")), "published": bool(u.get("published", True)),
        "published_at": _iso(u.get("published_at") or u.get("created_at")),
        "created_at": _iso(u.get("created_at")),
    }


def _report_out(r: dict) -> dict:
    return {
        "id": r["id"], "asset_id": r["asset_id"],
        "report_type": r.get("report_type", "quarterly"),
        "report_type_label": REPORT_TYPE_LABELS.get(r.get("report_type", "quarterly"), ""),
        "period_label": r.get("period_label", ""),
        "title": r.get("title", ""), "summary": r.get("summary", ""),
        "has_file": bool(r.get("storage_path")),
        "filename": r.get("filename"),
        "size_bytes": r.get("size_bytes", 0),
        "published": bool(r.get("published", True)),
        "download_url": (f"/api/assets/{r['asset_id']}/reports/{r['id']}/download"
                         if r.get("storage_path") else None),
        "created_at": _iso(r.get("created_at")),
    }


def _document_out(d: dict, *, authed: bool) -> dict:
    locked = d.get("visibility") == "investors" and not authed
    return {
        "id": d["id"], "asset_id": d["asset_id"],
        "doc_type": d.get("doc_type", "other"),
        "doc_type_label": DOC_TYPE_LABELS.get(d.get("doc_type", "other"), "Інше"),
        "title": d.get("title", ""), "filename": d.get("filename", ""),
        "size_bytes": d.get("size_bytes", 0),
        "visibility": d.get("visibility", "public"),
        "locked": locked,
        "download_url": (None if locked
                         else f"/api/assets/{d['asset_id']}/documents/{d['id']}/download"),
        "created_at": _iso(d.get("created_at")),
    }


def _question_out(q: dict, *, own: bool = False) -> dict:
    return {
        "id": q["id"], "asset_id": q["asset_id"],
        "investor_name": q.get("investor_name") or "Інвестор",
        "question": q.get("question", ""),
        "answer": q.get("answer"),
        "status": q.get("status", "pending"),
        "is_own": own,
        "answered_at": _iso(q.get("answered_at")),
        "created_at": _iso(q.get("created_at")),
    }


def _spv_out(s: dict) -> dict:
    return {
        "id": s["id"], "name": s.get("name", ""),
        "registration_number": s.get("registration_number"),
        "jurisdiction": s.get("jurisdiction", "UA"),
        "asset_id": s.get("asset_id"),
        "status": s.get("status", "forming"),
        "status_label": SPV_STATUS_LABELS.get(s.get("status", "forming"), ""),
        "notes": s.get("notes"),
        "created_at": _iso(s.get("created_at")),
    }


async def _save_upload(subdir: str, file: UploadFile) -> tuple[str, str, int]:
    """Persist an upload; returns (storage_path, filename, size).

    IR0.2 — Server-authoritative validation. Uses lumen_upload_security to
    sniff magic bytes, sanitise filename, and enforce per-category limits.
    Category derived from subdir (asset|misc).
    """
    content = await file.read()
    # Derive category from the subdir hint (gallery/photo/team -> asset,
    # otherwise default to misc which accepts office docs + images).
    cat = "asset" if any(k in (subdir or "") for k in ("gallery", "photo", "team", "video")) else "misc"
    try:
        from lumen_upload_security import validate_upload as _ir0_validate
        safe = _ir0_validate(content, file.filename, category=cat)
    except Exception as _us_e:
        from fastapi import HTTPException as _HE
        if isinstance(_us_e, _HE):
            raise
        raise _HE(status_code=400, detail="Неможливо обробити файл")
    folder = os.path.join(_UPLOAD_ROOT, subdir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex[:10]}_{safe.filename}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path, safe.filename, safe.size


def _remove_file(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Admin: embedded asset content (gallery / videos / team / risks / exit)
# ──────────────────────────────────────────────────────────────────────────────

class AssetContentPatch(BaseModel):
    gallery: Optional[list] = None        # [{url, caption?}]
    videos: Optional[list] = None         # [{url, title?}]
    team: Optional[list] = None           # [{name, role?, photo_url?, bio?}]
    risks: Optional[list] = None          # [{title, description?, severity?}]
    exit_strategy: Optional[str] = None


@router.patch("/admin/assets/{asset_id}/content")
async def admin_patch_asset_content(asset_id: str, payload: AssetContentPatch,
                                    _=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    patch: dict = {}

    if payload.gallery is not None:
        gallery = []
        for item in payload.gallery[:20]:
            url = _clean_str((item or {}).get("url"), 500)
            if not url.startswith(("http://", "https://")):
                continue
            gallery.append({"url": url, "caption": _clean_str((item or {}).get("caption"), 200)})
        patch["gallery"] = gallery

    if payload.videos is not None:
        videos = []
        for item in payload.videos[:10]:
            url = _clean_str((item or {}).get("url"), 500)
            if not url.startswith(("http://", "https://")):
                continue
            videos.append(_video_meta(url, (item or {}).get("title", "")))
        patch["videos"] = videos

    if payload.team is not None:
        team = []
        for item in payload.team[:12]:
            name = _clean_str((item or {}).get("name"), 120)
            if not name:
                continue
            team.append({
                "name": name,
                "role": _clean_str((item or {}).get("role"), 120),
                "photo_url": _clean_str((item or {}).get("photo_url"), 500),
                "bio": _clean_str((item or {}).get("bio"), 600),
            })
        patch["team"] = team

    if payload.risks is not None:
        risks = []
        for item in payload.risks[:12]:
            title = _clean_str((item or {}).get("title"), 200)
            if not title:
                continue
            severity = (item or {}).get("severity", "medium")
            risks.append({
                "title": title,
                "description": _clean_str((item or {}).get("description"), 800),
                "severity": severity if severity in RISK_SEVERITIES else "medium",
            })
        patch["risks"] = risks

    if payload.exit_strategy is not None:
        patch["exit_strategy"] = _clean_str(payload.exit_strategy, 3000)

    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    patch["updated_at"] = _now()
    await db.lumen_assets.update_one({"id": asset_id}, {"$set": patch})
    asset = await db.lumen_assets.find_one({"id": asset_id}, {"_id": 0})
    return {k: asset.get(k) for k in
            ("id", "gallery", "videos", "team", "risks", "exit_strategy")}


# ──────────────────────────────────────────────────────────────────────────────
# Updates — the asset's internal blog
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/updates")
async def asset_updates(asset_id: str):
    await _get_asset_or_404(asset_id)
    items = [
        _update_out(u) async for u in
        db.lumen_asset_updates.find({"asset_id": asset_id, "published": True})
        .sort([("pinned", -1), ("created_at", -1)]).limit(100)
    ]
    return {"items": items, "total": len(items)}


class UpdatePayload(BaseModel):
    title: str = ""
    body: str = ""
    kind: str = "general"
    pinned: bool = False
    published: bool = True


@router.get("/admin/assets/{asset_id}/updates")
async def admin_asset_updates(asset_id: str, _=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    items = [
        _update_out(u) async for u in
        db.lumen_asset_updates.find({"asset_id": asset_id})
        .sort([("pinned", -1), ("created_at", -1)]).limit(200)
    ]
    return {"items": items, "total": len(items)}


@router.post("/admin/assets/{asset_id}/updates")
async def admin_create_update(asset_id: str, payload: UpdatePayload,
                              admin=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    title = _clean_str(payload.title, 200)
    body = _clean_str(payload.body, 5000)
    if not title or not body:
        raise HTTPException(status_code=400, detail="Вкажіть заголовок і текст оновлення")
    if payload.kind not in UPDATE_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип оновлення")
    doc = {
        "id": str(uuid.uuid4()), "asset_id": asset_id,
        "kind": payload.kind, "title": title, "body": body,
        "pinned": bool(payload.pinned), "published": bool(payload.published),
        "created_by": admin.get("user_id") or admin.get("id"),
        "published_at": _now() if payload.published else None,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_asset_updates.insert_one(doc)
    return _update_out(doc)


@router.patch("/admin/asset-updates/{update_id}")
async def admin_patch_update(update_id: str, payload: UpdatePayload,
                             _=Depends(require_admin)):
    u = await db.lumen_asset_updates.find_one({"id": update_id})
    if not u:
        raise HTTPException(status_code=404, detail="Оновлення не знайдено")
    if payload.kind not in UPDATE_KINDS:
        raise HTTPException(status_code=400, detail="Невідомий тип оновлення")
    title = _clean_str(payload.title, 200)
    body = _clean_str(payload.body, 5000)
    if not title or not body:
        raise HTTPException(status_code=400, detail="Вкажіть заголовок і текст оновлення")
    patch = {
        "title": title, "body": body, "kind": payload.kind,
        "pinned": bool(payload.pinned), "published": bool(payload.published),
        "updated_at": _now(),
    }
    if payload.published and not u.get("published_at"):
        patch["published_at"] = _now()
    await db.lumen_asset_updates.update_one({"id": update_id}, {"$set": patch})
    return _update_out(await db.lumen_asset_updates.find_one({"id": update_id}))


@router.delete("/admin/asset-updates/{update_id}")
async def admin_delete_update(update_id: str, _=Depends(require_admin)):
    res = await db.lumen_asset_updates.delete_one({"id": update_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Оновлення не знайдено")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Reports — monthly / quarterly / annual
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/reports")
async def asset_reports(asset_id: str):
    await _get_asset_or_404(asset_id)
    items = [
        _report_out(r) async for r in
        db.lumen_asset_reports.find({"asset_id": asset_id, "published": True})
        .sort("created_at", -1).limit(100)
    ]
    return {"items": items, "total": len(items)}


@router.get("/assets/{asset_id}/reports/{report_id}/download")
async def download_report(asset_id: str, report_id: str):
    r = await db.lumen_asset_reports.find_one(
        {"id": report_id, "asset_id": asset_id, "published": True})
    if not r or not r.get("storage_path") or not os.path.exists(r["storage_path"]):
        raise HTTPException(status_code=404, detail="Файл звіту не знайдено")
    return FileResponse(r["storage_path"], filename=r.get("filename") or "report.pdf",
                        media_type=r.get("content_type") or "application/octet-stream")


@router.get("/admin/assets/{asset_id}/reports")
async def admin_asset_reports(asset_id: str, _=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    items = [
        _report_out(r) async for r in
        db.lumen_asset_reports.find({"asset_id": asset_id})
        .sort("created_at", -1).limit(200)
    ]
    return {"items": items, "total": len(items)}


@router.post("/admin/assets/{asset_id}/reports")
async def admin_create_report(asset_id: str,
                              title: str = Form(...),
                              report_type: str = Form("quarterly"),
                              period_label: str = Form(""),
                              summary: str = Form(""),
                              published: bool = Form(True),
                              file: Optional[UploadFile] = File(None),
                              admin=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    title = _clean_str(title, 200)
    if not title:
        raise HTTPException(status_code=400, detail="Вкажіть назву звіту")
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Тип звіту: monthly / quarterly / annual")
    storage_path = filename = content_type = None
    size = 0
    if file is not None and (file.filename or "").strip():
        storage_path, filename, size = await _save_upload(f"reports/{asset_id}", file)
        content_type = (file.content_type or "").split(";")[0] or None
    doc = {
        "id": str(uuid.uuid4()), "asset_id": asset_id,
        "report_type": report_type, "period_label": _clean_str(period_label, 60),
        "title": title, "summary": _clean_str(summary, 3000),
        "filename": filename, "content_type": content_type,
        "size_bytes": size, "storage_path": storage_path,
        "published": bool(published),
        "created_by": admin.get("user_id") or admin.get("id"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_asset_reports.insert_one(doc)
    return _report_out(doc)


class ReportPatch(BaseModel):
    title: Optional[str] = None
    report_type: Optional[str] = None
    period_label: Optional[str] = None
    summary: Optional[str] = None
    published: Optional[bool] = None


@router.patch("/admin/asset-reports/{report_id}")
async def admin_patch_report(report_id: str, payload: ReportPatch,
                             _=Depends(require_admin)):
    r = await db.lumen_asset_reports.find_one({"id": report_id})
    if not r:
        raise HTTPException(status_code=404, detail="Звіт не знайдено")
    patch: dict = {}
    if payload.title is not None:
        t = _clean_str(payload.title, 200)
        if not t:
            raise HTTPException(status_code=400, detail="Назва не може бути порожньою")
        patch["title"] = t
    if payload.report_type is not None:
        if payload.report_type not in REPORT_TYPES:
            raise HTTPException(status_code=400, detail="Невідомий тип звіту")
        patch["report_type"] = payload.report_type
    if payload.period_label is not None:
        patch["period_label"] = _clean_str(payload.period_label, 60)
    if payload.summary is not None:
        patch["summary"] = _clean_str(payload.summary, 3000)
    if payload.published is not None:
        patch["published"] = bool(payload.published)
    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    patch["updated_at"] = _now()
    await db.lumen_asset_reports.update_one({"id": report_id}, {"$set": patch})
    return _report_out(await db.lumen_asset_reports.find_one({"id": report_id}))


@router.delete("/admin/asset-reports/{report_id}")
async def admin_delete_report(report_id: str, _=Depends(require_admin)):
    r = await db.lumen_asset_reports.find_one({"id": report_id})
    if not r:
        raise HTTPException(status_code=404, detail="Звіт не знайдено")
    _remove_file(r.get("storage_path"))
    await db.lumen_asset_reports.delete_one({"id": report_id})
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Documents — due diligence pack
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/documents")
async def asset_documents(asset_id: str, request: Request):
    await _get_asset_or_404(asset_id)
    user = await _optional_user(request)
    items = [
        _document_out(d, authed=user is not None) async for d in
        db.lumen_asset_documents.find({"asset_id": asset_id})
        .sort("created_at", -1).limit(100)
    ]
    return {"items": items, "total": len(items)}


@router.get("/assets/{asset_id}/documents/{doc_id}/download")
async def download_document(asset_id: str, doc_id: str, request: Request):
    d = await db.lumen_asset_documents.find_one({"id": doc_id, "asset_id": asset_id})
    if not d or not d.get("storage_path") or not os.path.exists(d["storage_path"]):
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    if d.get("visibility") == "investors":
        user = await _optional_user(request)
        if user is None:
            raise HTTPException(status_code=401,
                                detail="Документ доступний лише авторизованим інвесторам")
    return FileResponse(d["storage_path"], filename=d.get("filename") or "document.pdf",
                        media_type=d.get("content_type") or "application/octet-stream")


@router.get("/admin/assets/{asset_id}/documents")
async def admin_asset_documents(asset_id: str, _=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    items = [
        _document_out(d, authed=True) async for d in
        db.lumen_asset_documents.find({"asset_id": asset_id})
        .sort("created_at", -1).limit(200)
    ]
    return {"items": items, "total": len(items)}


@router.post("/admin/assets/{asset_id}/documents")
async def admin_upload_document(asset_id: str,
                                title: str = Form(...),
                                doc_type: str = Form("other"),
                                visibility: str = Form("public"),
                                file: UploadFile = File(...),
                                admin=Depends(require_admin)):
    await _get_asset_or_404(asset_id)
    title = _clean_str(title, 200)
    if not title:
        raise HTTPException(status_code=400, detail="Вкажіть назву документа")
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Невідомий тип документа")
    if visibility not in ("public", "investors"):
        raise HTTPException(status_code=400, detail="visibility: public або investors")
    storage_path, filename, size = await _save_upload(f"documents/{asset_id}", file)
    doc = {
        "id": str(uuid.uuid4()), "asset_id": asset_id,
        "doc_type": doc_type, "title": title,
        "filename": filename,
        "content_type": (file.content_type or "").split(";")[0] or None,
        "size_bytes": size, "storage_path": storage_path,
        "visibility": visibility,
        "created_by": admin.get("user_id") or admin.get("id"),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_asset_documents.insert_one(doc)
    return _document_out(doc, authed=True)


@router.delete("/admin/asset-documents/{doc_id}")
async def admin_delete_document(doc_id: str, _=Depends(require_admin)):
    d = await db.lumen_asset_documents.find_one({"id": doc_id})
    if not d:
        raise HTTPException(status_code=404, detail="Документ не знайдено")
    _remove_file(d.get("storage_path"))
    await db.lumen_asset_documents.delete_one({"id": doc_id})
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Q&A — investor asks, admin answers, everyone reads
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/questions")
async def asset_questions(asset_id: str, request: Request):
    await _get_asset_or_404(asset_id)
    user = await _optional_user(request)
    uid = (user or {}).get("user_id") or (user or {}).get("id")
    query: dict = {"asset_id": asset_id, "status": "answered"}
    if uid:
        query = {"asset_id": asset_id, "$or": [
            {"status": "answered"},
            {"investor_id": uid, "status": "pending"},
        ]}
    items = [
        _question_out(q, own=bool(uid) and q.get("investor_id") == uid)
        async for q in db.lumen_asset_questions.find(query)
        .sort("created_at", -1).limit(100)
    ]
    return {"items": items, "total": len(items)}


class QuestionPayload(BaseModel):
    question: str = ""


@router.post("/investor/assets/{asset_id}/questions")
async def investor_ask_question(asset_id: str, payload: QuestionPayload,
                                user=Depends(get_current_user)):
    await _get_asset_or_404(asset_id)
    question = _clean_str(payload.question, 1000)
    if len(question) < 10:
        raise HTTPException(status_code=400,
                            detail="Питання надто коротке (мінімум 10 символів)")
    uid = user.get("user_id") or user.get("id")
    pending = await db.lumen_asset_questions.count_documents(
        {"asset_id": asset_id, "investor_id": uid, "status": "pending"})
    if pending >= 5:
        raise HTTPException(status_code=429,
                            detail="Забагато питань без відповіді — зачекайте на відповідь оператора")
    doc = {
        "id": str(uuid.uuid4()), "asset_id": asset_id,
        "investor_id": uid, "investor_name": user.get("name"),
        "question": question, "answer": None,
        "answered_by": None, "answered_at": None,
        "status": "pending",
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_asset_questions.insert_one(doc)
    return _question_out(doc, own=True)


@router.get("/admin/questions")
async def admin_questions(status: Optional[str] = None,
                          asset_id: Optional[str] = None,
                          _=Depends(require_admin)):
    if status and status not in QUESTION_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status: {', '.join(sorted(QUESTION_STATUSES))}")
    query: dict = {}
    if status:
        query["status"] = status
    if asset_id:
        query["asset_id"] = asset_id
    counts = {s: await db.lumen_asset_questions.count_documents(
        {**({"asset_id": asset_id} if asset_id else {}), "status": s})
        for s in QUESTION_STATUSES}
    asset_titles = {a["id"]: a.get("title", "") async for a in
                    db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1})}
    items = []
    async for q in db.lumen_asset_questions.find(query).sort("created_at", -1).limit(200):
        out = _question_out(q)
        out["asset_title"] = asset_titles.get(q["asset_id"], q["asset_id"])
        items.append(out)
    return {"items": items, "total": len(items), "counts": counts}


class AnswerPayload(BaseModel):
    answer: str = ""


@router.post("/admin/questions/{question_id}/answer")
async def admin_answer_question(question_id: str, payload: AnswerPayload,
                                admin=Depends(require_admin)):
    q = await db.lumen_asset_questions.find_one({"id": question_id})
    if not q:
        raise HTTPException(status_code=404, detail="Питання не знайдено")
    answer = _clean_str(payload.answer, 3000)
    if len(answer) < 2:
        raise HTTPException(status_code=400, detail="Відповідь не може бути порожньою")
    await db.lumen_asset_questions.update_one({"id": question_id}, {"$set": {
        "answer": answer, "status": "answered",
        "answered_by": admin.get("user_id") or admin.get("id"),
        "answered_at": _now(), "updated_at": _now(),
    }})
    # notify the investor (best-effort)
    try:
        asset = await db.lumen_assets.find_one({"id": q["asset_id"]})
        await db.lumen_notifications.insert_one({
            "id": str(uuid.uuid4()), "investor_id": q["investor_id"],
            "title": "Відповідь на ваше питання",
            "body": f"Оператор відповів на ваше питання щодо «{(asset or {}).get('title', '')}».",
            "kind": "qa", "read": False, "created_at": _now(),
        })
    except Exception:  # pragma: no cover
        pass
    return _question_out(await db.lumen_asset_questions.find_one({"id": question_id}))


@router.post("/admin/questions/{question_id}/hide")
async def admin_hide_question(question_id: str, _=Depends(require_admin)):
    q = await db.lumen_asset_questions.find_one({"id": question_id})
    if not q:
        raise HTTPException(status_code=404, detail="Питання не знайдено")
    await db.lumen_asset_questions.update_one(
        {"id": question_id}, {"$set": {"status": "hidden", "updated_at": _now()}})
    return {"ok": True, "status": "hidden"}


@router.post("/admin/questions/{question_id}/restore")
async def admin_restore_question(question_id: str, _=Depends(require_admin)):
    q = await db.lumen_asset_questions.find_one({"id": question_id})
    if not q:
        raise HTTPException(status_code=404, detail="Питання не знайдено")
    status = "answered" if q.get("answer") else "pending"
    await db.lumen_asset_questions.update_one(
        {"id": question_id}, {"$set": {"status": status, "updated_at": _now()}})
    return {"ok": True, "status": status}


# ──────────────────────────────────────────────────────────────────────────────
# SPV — the legal wrapper (Asset → SPV → Investors)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/assets/{asset_id}/spv")
async def asset_spv(asset_id: str):
    await _get_asset_or_404(asset_id)
    s = await db.lumen_spvs.find_one({"asset_id": asset_id})
    return {"spv": _spv_out(s) if s else None}


class SpvPayload(BaseModel):
    name: Optional[str] = None
    registration_number: Optional[str] = None
    jurisdiction: Optional[str] = None
    asset_id: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/admin/spvs")
async def admin_spvs(_=Depends(require_admin)):
    asset_titles = {a["id"]: a.get("title", "") async for a in
                    db.lumen_assets.find({}, {"_id": 0, "id": 1, "title": 1})}
    counts = {s: await db.lumen_spvs.count_documents({"status": s}) for s in SPV_STATUSES}
    items = []
    async for s in db.lumen_spvs.find({}).sort("created_at", -1).limit(200):
        out = _spv_out(s)
        out["asset_title"] = asset_titles.get(s.get("asset_id"), None)
        items.append(out)
    return {"items": items, "total": len(items), "counts": counts}


@router.post("/admin/spvs")
async def admin_create_spv(payload: SpvPayload, _=Depends(require_admin)):
    name = _clean_str(payload.name, 200)
    if not name:
        raise HTTPException(status_code=400, detail="Вкажіть назву SPV")
    status = payload.status or "forming"
    if status not in SPV_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status: {', '.join(sorted(SPV_STATUSES))}")
    if payload.asset_id:
        await _get_asset_or_404(payload.asset_id)
        existing = await db.lumen_spvs.find_one({"asset_id": payload.asset_id})
        if existing:
            raise HTTPException(status_code=409,
                                detail="Для цього активу вже існує SPV")
    doc = {
        "id": str(uuid.uuid4()), "name": name,
        "registration_number": _clean_str(payload.registration_number, 40) or None,
        "jurisdiction": _clean_str(payload.jurisdiction, 10) or "UA",
        "asset_id": payload.asset_id or None,
        "status": status, "notes": _clean_str(payload.notes, 1000) or None,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.lumen_spvs.insert_one(doc)
    return _spv_out(doc)


@router.patch("/admin/spvs/{spv_id}")
async def admin_patch_spv(spv_id: str, payload: SpvPayload, _=Depends(require_admin)):
    s = await db.lumen_spvs.find_one({"id": spv_id})
    if not s:
        raise HTTPException(status_code=404, detail="SPV не знайдено")
    patch: dict = {}
    if payload.name is not None:
        name = _clean_str(payload.name, 200)
        if not name:
            raise HTTPException(status_code=400, detail="Назва не може бути порожньою")
        patch["name"] = name
    if payload.registration_number is not None:
        patch["registration_number"] = _clean_str(payload.registration_number, 40) or None
    if payload.jurisdiction is not None:
        patch["jurisdiction"] = _clean_str(payload.jurisdiction, 10) or "UA"
    if payload.status is not None:
        if payload.status not in SPV_STATUSES:
            raise HTTPException(status_code=400,
                                detail=f"status: {', '.join(sorted(SPV_STATUSES))}")
        patch["status"] = payload.status
    if payload.asset_id is not None:
        if payload.asset_id:
            await _get_asset_or_404(payload.asset_id)
            other = await db.lumen_spvs.find_one(
                {"asset_id": payload.asset_id, "id": {"$ne": spv_id}})
            if other:
                raise HTTPException(status_code=409,
                                    detail="Для цього активу вже існує SPV")
        patch["asset_id"] = payload.asset_id or None
    if payload.notes is not None:
        patch["notes"] = _clean_str(payload.notes, 1000) or None
    if not patch:
        raise HTTPException(status_code=400, detail="Немає полів для оновлення")
    patch["updated_at"] = _now()
    await db.lumen_spvs.update_one({"id": spv_id}, {"$set": patch})
    return _spv_out(await db.lumen_spvs.find_one({"id": spv_id}))


@router.delete("/admin/spvs/{spv_id}")
async def admin_delete_spv(spv_id: str, _=Depends(require_admin)):
    res = await db.lumen_spvs.delete_one({"id": spv_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="SPV не знайдено")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# Seed — demo trust-layer content (idempotent, per-collection guards)
# ──────────────────────────────────────────────────────────────────────────────

_GALLERY_SEED = {
    "asset-podilskyi": [
        {"url": "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80", "caption": "Фасад комплексу"},
        {"url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1200&q=80", "caption": "Внутрішній двір"},
        {"url": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1200&q=80", "caption": "Шоурум квартири"},
        {"url": "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=80", "caption": "Хід будівництва"},
    ],
    "asset-stoyanka-land": [
        {"url": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80", "caption": "Панорама ділянки"},
        {"url": "https://images.unsplash.com/photo-1500076656116-558758c991c1?auto=format&fit=crop&w=1200&q=80", "caption": "Під'їзна дорога"},
        {"url": "https://images.unsplash.com/photo-1473448912268-2022ce9509d8?auto=format&fit=crop&w=1200&q=80", "caption": "Межі землевідводу"},
    ],
    "asset-lavr-tc": [
        {"url": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80", "caption": "Атріум центру"},
        {"url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1200&q=80", "caption": "Торгова галерея"},
        {"url": "https://images.unsplash.com/photo-1555529669-e69e7aa0ba9a?auto=format&fit=crop&w=1200&q=80", "caption": "Орендні приміщення"},
    ],
}

_VIDEOS_SEED = {
    "asset-podilskyi": [
        {"url": "https://www.youtube.com/watch?v=R3HrU_lKjnk", "title": "Відеоогляд об'єкта з дрона"},
    ],
    "asset-lavr-tc": [
        {"url": "https://www.youtube.com/watch?v=Q3mLPyiVriw", "title": "Презентація торгового центру"},
    ],
}

_TEAM_SEED = {
    "asset-podilskyi": [
        {"name": "Андрій Коваленко", "role": "Керівник проєкту", "photo_url": "", "bio": "12 років у девелопменті житла, 6 зданих комплексів у Києві."},
        {"name": "Ольга Романюк", "role": "Фінансова директорка SPV", "photo_url": "", "bio": "Ex-Big4, аудит і фінансове моделювання нерухомості."},
        {"name": "Сергій Литвин", "role": "Технічний нагляд", "photo_url": "", "bio": "Інженер-будівельник, контроль якості та графіка робіт."},
    ],
    "asset-lavr-tc": [
        {"name": "Марія Гончар", "role": "Керуюча активом", "photo_url": "", "bio": "Управління комерційною нерухомістю 9 років, заповнюваність портфеля 96%."},
        {"name": "Дмитро Білоус", "role": "Брокер оренди", "photo_url": "", "bio": "Договірна робота з якірними орендарями."},
    ],
}

_RISKS_SEED = {
    "asset-podilskyi": [
        {"title": "Затримка введення в експлуатацію", "description": "Зсуває початок орендних виплат. Мітигація: штрафні санкції у договорі з генпідрядником.", "severity": "medium"},
        {"title": "Зниження орендних ставок у локації", "description": "Впливає на щомісячний дохід. Мітигація: диверсифікація форматів квартир.", "severity": "medium"},
        {"title": "Валютні та інфляційні коливання", "description": "Частково компенсуються індексацією оренди та переоцінкою активу.", "severity": "low"},
        {"title": "Подовження горизонту виходу", "description": "Продаж активу може зайняти на 6–12 міс. довше за рішенням SPV.", "severity": "low"},
    ],
    "asset-lavr-tc": [
        {"title": "Ротація якірного орендаря", "description": "Вихід якоря знижує трафік. Мітигація: довгострокові договори з пенальті.", "severity": "high"},
        {"title": "Зростання операційних витрат", "description": "Енергоносії та обслуговування. Мітигація: енергоаудит, фіксація тарифів.", "severity": "medium"},
    ],
}

_EXIT_SEED = {
    "asset-podilskyi": (
        "Базовий сценарій: продаж квартир після введення в експлуатацію (міс. 18–24) "
        "з розподілом виручки пропорційно часткам. Альтернатива: рефінансування під "
        "орендний потік і вихід через продаж SPV стратегічному інвестору. "
        "Рішення про вихід ухвалюється зборами учасників SPV."
    ),
    "asset-lavr-tc": (
        "Утримання 36 міс. з щоквартальними виплатами орендного доходу, далі — продаж "
        "об'єкта професійному управителю або REIT-фонду. Очікуваний множник на капітал "
        "1.4–1.6x з урахуванням переоцінки."
    ),
}

_SPV_SEED_STATUS = {"asset-podilskyi": "active", "asset-lavr-tc": "active",
                    "asset-stoyanka-land": "active"}


async def _seed_asset_content() -> None:
    """Idempotent demo seed for the trust layer."""
    # 1) embedded fields — only when the asset has no gallery yet
    async for asset in db.lumen_assets.find({}):
        aid = asset["id"]
        patch: dict = {}
        if "gallery" not in asset:
            gallery = _GALLERY_SEED.get(aid) or (
                [{"url": asset["cover_url"], "caption": asset.get("title", "")}]
                if asset.get("cover_url") else [])
            patch["gallery"] = gallery
        if "videos" not in asset:
            patch["videos"] = [_video_meta(v["url"], v["title"])
                               for v in _VIDEOS_SEED.get(aid, [])]
        if "team" not in asset:
            patch["team"] = _TEAM_SEED.get(aid, [])
        if "risks" not in asset:
            patch["risks"] = _RISKS_SEED.get(aid, [])
        if "exit_strategy" not in asset:
            patch["exit_strategy"] = _EXIT_SEED.get(aid, "")
        if patch:
            await db.lumen_assets.update_one({"id": aid}, {"$set": patch})

    # 2) SPV registry — derive from spv_label
    if await db.lumen_spvs.count_documents({}) == 0:
        edrpou = 44810000
        async for asset in db.lumen_assets.find({}):
            label = asset.get("spv_label")
            if not label:
                continue
            edrpou += 137
            await db.lumen_spvs.insert_one({
                "id": str(uuid.uuid4()), "name": label,
                "registration_number": str(edrpou),
                "jurisdiction": "UA", "asset_id": asset["id"],
                "status": _SPV_SEED_STATUS.get(asset["id"], "forming"),
                "notes": "Окремий рахунок SPV; кошти інвесторів відокремлені від платформи.",
                "created_at": _now(), "updated_at": _now(),
            })

    # 3) updates
    if await db.lumen_asset_updates.count_documents({}) == 0:
        seed_updates = [
            ("asset-podilskyi", "milestone", "Завершено 4-й поверх", True,
             "Монолітні роботи 4-го поверху завершено з випередженням графіка на 9 днів. "
             "Розпочато мурування зовнішніх стін 1–2 поверхів."),
            ("asset-podilskyi", "news", "Підписано договір з оператором паркінгу", False,
             "Підземний паркінг на 46 місць передано в управління оператору з фіксованим "
             "орендним платежем — це додає ~1.2% до річної дохідності SPV."),
            ("asset-podilskyi", "general", "Фотозвіт за місяць опубліковано", False,
             "У галереї об'єкта додано свіжі фото будмайданчика та шоуруму."),
            ("asset-lavr-tc", "milestone", "Підписано якірного орендаря", True,
             "Укладено 5-річний договір оренди з національною продуктовою мережею на 1 850 м². "
             "Заповнюваність центру зросла до 92%."),
            ("asset-stoyanka-land", "news", "Отримано витяг з містобудівних умов", False,
             "Отримано вихідні дані для проєктування. Наступний крок — концепція забудови."),
        ]
        for aid, kind, title, pinned, body in seed_updates:
            if not await db.lumen_assets.find_one({"id": aid}):
                continue
            await db.lumen_asset_updates.insert_one({
                "id": str(uuid.uuid4()), "asset_id": aid, "kind": kind,
                "title": title, "body": body, "pinned": pinned,
                "published": True, "created_by": None,
                "published_at": _now(), "created_at": _now(), "updated_at": _now(),
            })

    # 4) reports + documents (small generated PDFs)
    if await db.lumen_asset_reports.count_documents({}) == 0 \
            or await db.lumen_asset_documents.count_documents({}) == 0:
        try:
            pdf_q1 = _make_seed_pdf(
                "Квартальний звіт SPV — Q1 2026",
                ["Об'єкт: ЖК «Подільський», Київ",
                 "Готовність: 4/9 поверхів, графік +9 днів",
                 "Касовий залишок SPV: $10,056",
                 "Виконання бюджету будівництва: 97.4%",
                 "Прогноз введення в експлуатацію: без змін"])
            pdf_val = _make_seed_pdf(
                "Звіт про незалежну оцінку",
                ["Об'єкт: ЖК «Подільський», Київ, Поділ",
                 "Оцінювач: ТОВ «Експерт-Оцінка» (сертифікат ФДМУ)",
                 "Ринкова вартість завершеного об'єкта: $2.35M",
                 "Метод: дохідний + порівняльний"])
            pdf_fin = _make_seed_pdf(
                "Фінансова модель проєкту (витяг)",
                ["Цільова IRR інвестора: 18.5% річних",
                 "Частка орендного доходу: 55%",
                 "OPEX: 12%, податки: 19.5%, комісія платформи: 2%",
                 "Горизонт: 24 місяці"])
            pdf_permit = _make_seed_pdf(
                "Дозвіл на виконання будівельних робіт",
                ["Номер: ІУ 013260418866",
                 "Замовник: ТОВ «Подільський Інвест»",
                 "Видано: ДІАМ, чинний"])
        except Exception as e:  # pragma: no cover
            logger.error("Sprint5 seed PDF generation failed: %s", e)
            pdf_q1 = pdf_val = pdf_fin = pdf_permit = None

        if await db.lumen_asset_reports.count_documents({}) == 0 and pdf_q1:
            await db.lumen_asset_reports.insert_one({
                "id": str(uuid.uuid4()), "asset_id": "asset-podilskyi",
                "report_type": "quarterly", "period_label": "Q1 2026",
                "title": "Квартальний звіт SPV — Q1 2026",
                "summary": "Будівництво за графіком (+9 днів випередження), бюджет виконано на 97.4%. "
                           "Касовий залишок SPV — $10,056.",
                "filename": "lumen_podilskyi_Q1_2026.pdf",
                "content_type": "application/pdf",
                "size_bytes": os.path.getsize(pdf_q1), "storage_path": pdf_q1,
                "published": True, "created_by": None,
                "created_at": _now(), "updated_at": _now(),
            })

        if await db.lumen_asset_documents.count_documents({}) == 0 and pdf_val:
            docs_seed = [
                ("valuation", "Звіт про незалежну оцінку", "public", pdf_val,
                 "lumen_podilskyi_valuation.pdf"),
                ("financial_model", "Фінансова модель проєкту", "investors", pdf_fin,
                 "lumen_podilskyi_finmodel.pdf"),
                ("permit", "Дозвіл на будівельні роботи", "public", pdf_permit,
                 "lumen_podilskyi_permit.pdf"),
            ]
            for doc_type, title, visibility, path, fname in docs_seed:
                if not path:
                    continue
                await db.lumen_asset_documents.insert_one({
                    "id": str(uuid.uuid4()), "asset_id": "asset-podilskyi",
                    "doc_type": doc_type, "title": title,
                    "filename": fname, "content_type": "application/pdf",
                    "size_bytes": os.path.getsize(path), "storage_path": path,
                    "visibility": visibility, "created_by": None,
                    "created_at": _now(), "updated_at": _now(),
                })

    # 5) Q&A — a couple of answered questions from the demo investor
    if await db.lumen_asset_questions.count_documents({}) == 0:
        demo = await db.users.find_one({"email": "client@atlas.dev"})
        if demo:
            uid = demo.get("user_id") or demo.get("id")
            qa_seed = [
                ("Що буде, якщо забудовник затримає здачу будинку?",
                 "У договорі з генпідрядником передбачені штрафні санкції за зрив графіка. "
                 "Крім того, виплати інвесторам прив'язані до фактичного орендного потоку, "
                 "а резервний фонд SPV покриває до 3 місяців затримки."),
                ("Чи можу я продати свою частку до завершення горизонту?",
                 "Так, після запуску вторинного ринку (у розробці) частку можна буде запропонувати "
                 "іншим інвесторам платформи. До того моменту можлива переуступка за погодженням SPV."),
            ]
            for question, answer in qa_seed:
                await db.lumen_asset_questions.insert_one({
                    "id": str(uuid.uuid4()), "asset_id": "asset-podilskyi",
                    "investor_id": uid, "investor_name": demo.get("name"),
                    "question": question, "answer": answer,
                    "answered_by": None, "answered_at": _now(),
                    "status": "answered",
                    "created_at": _now(), "updated_at": _now(),
                })


def _make_seed_pdf(title: str, lines: list[str]) -> str:
    """Generate a tiny branded PDF into the uploads dir; returns the path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    folder = os.path.join(_UPLOAD_ROOT, "seed")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, re.sub(r"[^\w]+", "_", title)[:60] + ".pdf")
    if os.path.exists(path):
        return path

    font = "Helvetica"
    for fpath in ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(fpath):
            try:
                pdfmetrics.registerFont(TTFont("LumenSeed", fpath))
                font = "LumenSeed"
                break
            except Exception:
                pass

    c = _canvas.Canvas(path, pagesize=A4)
    w, h = A4
    c.setFont(font, 16)
    c.drawString(50, h - 70, title)
    c.setFont(font, 10)
    c.drawString(50, h - 90, "LUMEN — платформа колективних інвестицій (демо-документ)")
    y = h - 130
    c.setFont(font, 11)
    for line in lines:
        c.drawString(50, y, f"•  {line}")
        y -= 22
    c.setFont(font, 8)
    c.drawString(50, 40, "Згенеровано автоматично для демонстрації. Не є офіційним документом.")
    c.save()
    return path


@router.on_event("startup")
async def _sprint5_startup():
    try:
        await _seed_asset_content()
        logger.info("[Sprint 5] Asset content seed ensured")
    except Exception as e:  # pragma: no cover
        logger.error("[Sprint 5] seed failed: %s", e)
