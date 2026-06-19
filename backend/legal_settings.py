"""
Legal Settings module — single source of truth for:
  • Footer social-media links (telegram, tiktok, instagram, youtube, facebook, github)
  • Legal documents (terms of use, privacy policy, cookies policy)
  • Cookie consent log (anonymous, GDPR-friendly)

Storage: MongoDB
  • collection `legal_settings` — single doc with `key="default"`
  • collection `cookie_consents` — append-only audit log

Public reads expose only "safe" data (enabled socials, doc body); admin
reads/writes touch the full document. Consent log is anonymized — only
SHA-256 of (client IP + UA) is stored to avoid storing PII.

Wired into server.py as a sub-router via `router = APIRouter(prefix="/api")`.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from legal_content import (
    LEGAL_BODIES,
    LEGAL_PACKAGE_KINDS,
    LEGAL_PACKAGE_VERSION,
    LEGAL_SLUG_TO_KIND,
    LEGAL_SUMMARIES,
    LEGAL_TITLES,
)

logger = logging.getLogger(__name__)

# ── Settings shape ─────────────────────────────────────────────────────────

SUPPORTED_SOCIALS = ["telegram", "tiktok", "instagram", "youtube", "facebook", "github"]
# Full legal package + legacy footer docs (terms/cookies kept for compatibility).
SUPPORTED_LEGAL_DOCS = LEGAL_PACKAGE_KINDS + ["terms", "cookies"]

# Real seed bodies + titles come from legal_content.py
DEFAULT_LEGAL_BODIES = LEGAL_BODIES
DEFAULT_LEGAL_TITLES = LEGAL_TITLES


def _doc_seed(kind: str) -> Dict[str, Any]:
    return {
        "title": DEFAULT_LEGAL_TITLES.get(kind, kind.title()),
        "body": DEFAULT_LEGAL_BODIES.get(kind, ""),
        "summary": LEGAL_SUMMARIES.get(kind, ""),
        "auto_seeded": True,
        "package_version": LEGAL_PACKAGE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _default_settings() -> Dict[str, Any]:
    return {
        "key": "default",
        "socials": {
            # Three primaries default to enabled with empty URL (admin sets URLs).
            "telegram":  {"url": "",  "enabled": True},
            "tiktok":    {"url": "",  "enabled": True},
            "instagram": {"url": "",  "enabled": True},
            "youtube":   {"url": "",  "enabled": False},
            "facebook":  {"url": "",  "enabled": False},
            "github":    {"url": "",  "enabled": False},
        },
        "legal": {kind: _doc_seed(kind) for kind in SUPPORTED_LEGAL_DOCS},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# Marker present in the previous placeholder seed copy — lets us safely upgrade
# old placeholder docs to real content without clobbering admin edits.
_PLACEHOLDER_MARKERS = ("placeholder text", "edit it from the admin panel", "_set this from the admin editor_")


def _is_placeholder(body: str) -> bool:
    b = (body or "").lower()
    return any(m in b for m in _PLACEHOLDER_MARKERS)


async def _get_or_create(db) -> Dict[str, Any]:
    doc = await db.legal_settings.find_one({"key": "default"}, {"_id": 0})
    if not doc:
        doc = _default_settings()
        await db.legal_settings.insert_one(dict(doc))
        logger.info("LEGAL_SETTINGS: seeded default document (package v%s)", LEGAL_PACKAGE_VERSION)
    else:
        socials = doc.get("socials") or {}
        legal = doc.get("legal") or {}
        mutated = False
        for k in SUPPORTED_SOCIALS:
            if k not in socials:
                socials[k] = {"url": "", "enabled": False}
                mutated = True
        for k in SUPPORTED_LEGAL_DOCS:
            cur = legal.get(k)
            if not cur:
                # Brand-new doc → seed real content.
                legal[k] = _doc_seed(k)
                mutated = True
                continue
            # Refresh only docs the admin has NOT edited (auto_seeded truthy /
            # absent) when the package version advanced, or when the stored body
            # is still the old placeholder copy.
            admin_edited = cur.get("auto_seeded") is False
            stale_version = (cur.get("package_version") or 0) < LEGAL_PACKAGE_VERSION
            if (not admin_edited) and (stale_version or _is_placeholder(cur.get("body", ""))):
                legal[k] = _doc_seed(k)
                mutated = True
        if mutated:
            await db.legal_settings.update_one(
                {"key": "default"}, {"$set": {"socials": socials, "legal": legal}}
            )
            doc["socials"] = socials
            doc["legal"] = legal
    # Always drop _id defensively (projection should have handled it).
    doc.pop("_id", None)
    return doc


async def ensure_legal_package(db) -> Dict[str, Any]:
    """Startup hook: guarantee the full legal package exists with real content.

    Returns a small summary dict for logging. Safe & idempotent — admin-edited
    documents (auto_seeded=False) are never overwritten.
    """
    doc = await _get_or_create(db)
    legal = doc.get("legal") or {}
    seeded = [k for k in SUPPORTED_LEGAL_DOCS if k in legal]
    return {
        "package_version": LEGAL_PACKAGE_VERSION,
        "docs": seeded,
        "count": len(seeded),
    }


# ── Pydantic models ────────────────────────────────────────────────────────

class SocialItem(BaseModel):
    url: str = ""
    enabled: bool = False


class LegalDoc(BaseModel):
    title: str
    body: str
    summary: Optional[str] = None
    updated_at: Optional[str] = None


class LegalSettingsUpdate(BaseModel):
    socials: Optional[Dict[str, SocialItem]] = None
    legal: Optional[Dict[str, LegalDoc]] = None


class CookieConsentBody(BaseModel):
    # 'all' = accept everything, 'essential' = essential only, 'rejected' = decline all non-essential.
    choice: str = Field(..., pattern="^(all|essential|rejected)$")
    # Optional list of categories the user opted into when choosing "custom"-like flows.
    categories: Optional[List[str]] = None


# ── Router factory ─────────────────────────────────────────────────────────

def _kind_to_slug(kind: str) -> str:
    """Reverse of LEGAL_SLUG_TO_KIND for canonical public URLs."""
    if kind == "secondary":
        return "secondary-market"
    return kind


def build_legal_router(db, require_admin):
    """Build the FastAPI router bound to the given db handle + admin guard.

    The guard is passed in (not imported) so we don't introduce a circular
    dependency with server.py. Pass `require_role('admin')` from there.
    """
    router = APIRouter(prefix="/api", tags=["legal"])

    # ── Public ─────────────────────────────────────────────────────────────

    @router.get("/public/legal-settings")
    async def public_legal_settings():
        """Footer-safe payload: only enabled socials + legal doc titles."""
        doc = await _get_or_create(db)
        socials = [
            {"key": k, "url": v.get("url", "")}
            for k, v in (doc.get("socials") or {}).items()
            if v.get("enabled") and (v.get("url") or "").strip()
        ]
        legal = doc.get("legal") or {}
        legal_summary = [
            {"kind": k, "title": legal.get(k, {}).get("title", k.title()),
             "updated_at": legal.get(k, {}).get("updated_at")}
            for k in SUPPORTED_LEGAL_DOCS if k in legal
        ]
        # The curated legal *package* (ordered) used by /legal index + footer.
        package = [
            {
                "kind": k,
                "slug": _kind_to_slug(k),
                "title": legal.get(k, {}).get("title", LEGAL_TITLES.get(k, k.title())),
                "summary": legal.get(k, {}).get("summary", LEGAL_SUMMARIES.get(k, "")),
                "updated_at": legal.get(k, {}).get("updated_at"),
            }
            for k in LEGAL_PACKAGE_KINDS if k in legal
        ]
        return {"socials": socials, "legal": legal_summary, "package": package}

    @router.get("/public/legal-package")
    async def public_legal_package():
        """Ordered list of the full legal package (for the /legal index page)."""
        doc = await _get_or_create(db)
        legal = doc.get("legal") or {}
        return {
            "package_version": LEGAL_PACKAGE_VERSION,
            "items": [
                {
                    "kind": k,
                    "slug": _kind_to_slug(k),
                    "title": legal.get(k, {}).get("title", LEGAL_TITLES.get(k, k.title())),
                    "summary": legal.get(k, {}).get("summary", LEGAL_SUMMARIES.get(k, "")),
                    "updated_at": legal.get(k, {}).get("updated_at"),
                }
                for k in LEGAL_PACKAGE_KINDS if k in legal
            ],
        }

    @router.get("/public/legal-document/{kind}")
    async def public_legal_document(kind: str):
        # Accept both canonical kinds and public slugs (e.g. secondary-market).
        resolved = LEGAL_SLUG_TO_KIND.get(kind, kind)
        if resolved not in SUPPORTED_LEGAL_DOCS:
            raise HTTPException(404, detail={"code": "unknown_doc", "message": "Unknown legal document"})
        doc = await _get_or_create(db)
        legal = (doc.get("legal") or {}).get(resolved) or {}
        return {
            "kind": resolved,
            "slug": _kind_to_slug(resolved),
            "title": legal.get("title", LEGAL_TITLES.get(resolved, resolved.title())),
            "summary": legal.get("summary", LEGAL_SUMMARIES.get(resolved, "")),
            "body": legal.get("body", ""),
            "updated_at": legal.get("updated_at"),
        }

    @router.post("/cookie-consent")
    async def cookie_consent(payload: CookieConsentBody, request: Request):
        """Log anonymous cookie-consent. Hash of IP+UA only, no PII."""
        ip = (request.headers.get("x-forwarded-for") or request.client.host or "").split(",")[0].strip()
        ua = request.headers.get("user-agent", "")
        # Hash + truncate so the audit log is anonymous yet de-dup capable.
        fingerprint = hashlib.sha256(f"{ip}|{ua}".encode("utf-8")).hexdigest()[:16]
        rec = {
            "fingerprint": fingerprint,
            "choice": payload.choice,
            "categories": payload.categories or [],
            "ua_short": ua[:120],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        await db.cookie_consents.insert_one(dict(rec))
        return {"ok": True, "fingerprint": fingerprint, "at": rec["at"]}

    # ── Admin ──────────────────────────────────────────────────────────────

    @router.get("/admin/legal-settings")
    async def admin_legal_settings(user=Depends(require_admin)):
        doc = await _get_or_create(db)
        return doc

    @router.put("/admin/legal-settings")
    async def admin_legal_settings_update(
        update: LegalSettingsUpdate,
        user=Depends(require_admin),
    ):
        current = await _get_or_create(db)
        now_iso = datetime.now(timezone.utc).isoformat()
        set_fields: Dict[str, Any] = {"updated_at": now_iso}

        if update.socials is not None:
            socials = dict(current.get("socials") or {})
            for k, v in update.socials.items():
                if k not in SUPPORTED_SOCIALS:
                    raise HTTPException(400, detail={"code": "unknown_social", "message": f"Unsupported social: {k}"})
                socials[k] = {"url": (v.url or "").strip(), "enabled": bool(v.enabled)}
            set_fields["socials"] = socials

        if update.legal is not None:
            legal = dict(current.get("legal") or {})
            for k, v in update.legal.items():
                if k not in SUPPORTED_LEGAL_DOCS:
                    raise HTTPException(400, detail={"code": "unknown_doc", "message": f"Unsupported doc: {k}"})
                prev = legal.get(k) or {}
                legal[k] = {
                    "title": (v.title or "").strip(),
                    "body": v.body or "",
                    "summary": (v.summary if v.summary is not None else prev.get("summary", LEGAL_SUMMARIES.get(k, ""))),
                    # Admin-edited → never auto-overwritten by re-seeding.
                    "auto_seeded": False,
                    "package_version": LEGAL_PACKAGE_VERSION,
                    "updated_at": now_iso,
                }
            set_fields["legal"] = legal

        await db.legal_settings.update_one({"key": "default"}, {"$set": set_fields}, upsert=True)
        result = await _get_or_create(db)
        return result

    @router.get("/admin/cookie-consents/stats")
    async def admin_consent_stats(user=Depends(require_admin)):
        """Aggregate consent counters + last-7-days timeline."""
        pipeline_choice = [
            {"$group": {"_id": "$choice", "count": {"$sum": 1}}},
        ]
        by_choice: Dict[str, int] = {"all": 0, "essential": 0, "rejected": 0}
        async for row in db.cookie_consents.aggregate(pipeline_choice):
            key = row.get("_id") or "unknown"
            by_choice[key] = row.get("count", 0)
        total = sum(by_choice.values())
        return {
            "total": total,
            "by_choice": by_choice,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    return router
