"""
LUMEN · SEO Surface — Phase S1.1
=================================

Ported from BiBiCars-EU `app/routers/seo.py` and adapted for LUMEN's domain
(real-estate investment, not car marketplace).

Why
---
The LUMEN landing has been invisible to Google: no sitemap, no robots, no
JSON-LD, no per-route SEO meta. Every paid investor click earns zero
organic compound. This module fixes the discoverability hole BEFORE
P3 (First Real Investor) so the very first organic + paid traffic of the
beta starts compounding.

What's exposed
--------------
PUBLIC (no auth, served past the access gate)
  GET /api/seo/sitemap.xml
        Fresh sitemap built from published assets + (optional) blog posts.
        In-memory 10-min cache keyed on the origin so the bot can hammer
        it without hitting Mongo.
  GET /api/seo/sitemap-index.xml
        Sitemap index pointing at the dynamic + (optional) static sitemap.
  GET /api/seo/robots.txt
        Robots policy. Always points crawlers at /api/seo/sitemap.xml.
  GET /api/seo/runtime-config
        JSON blob the React shell injects into <head> for SEO meta,
        canonical, OG defaults, JSON-LD type, and feature flags.

ADMIN (staff-only, behind the gate as usual)
  GET   /api/admin/seo/settings        — fetch persisted SEO globals
  PATCH /api/admin/seo/settings        — update title template / OG / JSON-LD
  POST  /api/admin/seo/cache/invalidate — drop the 10-min sitemap cache

Persisted shape (single document in `lumen_seo_settings`, id=`global`)
---------------------------------------------------------------------
{
  id: "global",
  origin: "https://lumen.invest",          # public canonical origin
  title_template: "%s · LUMEN",
  default_title: "LUMEN — Реальні активи. Прозорі інвестиції.",
  default_description: "...",
  default_og_image: "https://lumen.invest/og-default.jpg",
  default_locale: "uk_UA",
  alt_locales: ["en_US"],
  jsonld_org_name: "LUMEN",
  jsonld_org_url: "https://lumen.invest",
  jsonld_org_logo: "https://lumen.invest/logo.png",
  jsonld_org_sameAs: ["https://t.me/lumen_invest", ...],
  twitter_handle: "@lumen_invest",
  enable_blog_in_sitemap: false,
  robots_extras: "",                       # extra lines appended to robots.txt
  updated_at: "...",
  updated_by: "user_xxx",
  version: 3,                              # bumped on every PATCH
}
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from lumen_api import db, require_admin, _now, _iso

logger = logging.getLogger("lumen.seo")

router = APIRouter(tags=["lumen-seo"])

# ───────────────────────────────────────────────────────────────────────────
# Constants & defaults
# ───────────────────────────────────────────────────────────────────────────

_SETTINGS_ID = "global"
_CACHE_TTL_SECONDS = 600  # 10 min — matches BiBi
_CACHE: dict[str, Any] = {"sitemap": None, "sitemap_at": None,
                          "sitemap_index": None, "sitemap_index_at": None}

# Static, public-facing app routes that should always be in the sitemap.
# Path → (changefreq, priority).
_STATIC_ROUTES: list[tuple[str, str, float]] = [
    ("/",                "daily",   1.0),
    ("/marketplace",     "daily",   0.9),
    ("/fund",            "weekly",  0.8),
    ("/pricing",         "monthly", 0.6),
    ("/about",           "monthly", 0.6),
    ("/legal/terms",     "yearly",  0.3),
    ("/legal/privacy",   "yearly",  0.3),
    ("/legal/cookies",   "yearly",  0.3),
    ("/legal/risk",      "yearly",  0.3),
    ("/blog",            "weekly",  0.5),
]

_DEFAULT_SETTINGS: dict[str, Any] = {
    "id": _SETTINGS_ID,
    "origin": "",                # filled at request time from Host if blank
    "title_template": "%s · LUMEN",
    "default_title": "LUMEN — Реальні активи. Прозорі інвестиції.",
    "default_description": (
        "LUMEN — платформа колективних інвестицій у нерухомість. Прозорі "
        "договори, регулярні виплати, повна звітність по кожному активу."
    ),
    "default_og_image": "",
    "default_locale": "uk_UA",
    "alt_locales": ["en_US"],
    "jsonld_org_name": "LUMEN",
    "jsonld_org_url": "",
    "jsonld_org_logo": "",
    "jsonld_org_sameAs": [],
    "twitter_handle": "",
    "enable_blog_in_sitemap": False,
    "robots_extras": "",
    "version": 1,
}


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _origin_from_request(request: Request) -> str:
    """Resolve the canonical origin to embed in URLs.

    Preference order: env SEO_PUBLIC_ORIGIN > settings.origin > Host header.
    Always returns without a trailing slash.
    """
    env = (os.environ.get("SEO_PUBLIC_ORIGIN") or os.environ.get("PUBLIC_BASE_URL") or "").strip()
    if env:
        return env.rstrip("/")
    host = request.headers.get("host", "").strip()
    if host:
        scheme = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip() or "https"
        return f"{scheme}://{host}".rstrip("/")
    return ""


async def _load_settings() -> dict[str, Any]:
    doc = await db.lumen_seo_settings.find_one({"id": _SETTINGS_ID})
    if not doc:
        # Auto-seed on first read so admin UI has something to edit.
        doc = dict(_DEFAULT_SETTINGS)
        doc["updated_at"] = _now()
        await db.lumen_seo_settings.insert_one(dict(doc))
        logger.info("SEO settings auto-seeded with defaults")
    # Strip the Mongo _id but keep ours.
    doc.pop("_id", None)
    # Coerce updated_at to ISO for outbound transport.
    ua = doc.get("updated_at")
    if isinstance(ua, datetime):
        doc["updated_at"] = ua.isoformat()
    return doc


def _invalidate_cache() -> None:
    _CACHE.update({"sitemap": None, "sitemap_at": None,
                   "sitemap_index": None, "sitemap_index_at": None})


def _cache_is_warm(key: str) -> bool:
    val = _CACHE.get(key)
    at = _CACHE.get(f"{key}_at")
    if val is None or at is None:
        return False
    age = (datetime.now(timezone.utc) - at).total_seconds()
    return age < _CACHE_TTL_SECONDS


# ───────────────────────────────────────────────────────────────────────────
# Sitemap renderers
# ───────────────────────────────────────────────────────────────────────────

async def _build_sitemap_xml(origin: str, enable_blog: bool) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls: list[str] = []

    def _u(path: str, lastmod: str, changefreq: str, priority: float) -> str:
        return (
            "  <url>\n"
            f"    <loc>{xml_escape(origin + path)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority:.1f}</priority>\n"
            "  </url>"
        )

    # 1. Static routes — always emitted.
    for path, freq, prio in _STATIC_ROUTES:
        urls.append(_u(path, today, freq, prio))

    # 2. Published assets (real-estate listings).
    try:
        async for a in db.lumen_assets.find(
            {"status": "published"},
            {"_id": 0, "id": 1, "slug": 1, "title": 1, "updated_at": 1},
        ).limit(2000):
            slug = a.get("slug") or a.get("id")
            ua = a.get("updated_at")
            if isinstance(ua, datetime):
                lastmod = ua.strftime("%Y-%m-%d")
            elif isinstance(ua, str) and len(ua) >= 10:
                lastmod = ua[:10]
            else:
                lastmod = today
            urls.append(_u(f"/marketplace/{slug}", lastmod, "weekly", 0.8))
    except Exception as e:
        logger.warning(f"sitemap: asset loop failed: {e}")

    # 3. Operators (public profile pages).
    try:
        async for op in db.lumen_operators.find(
            {"status": {"$in": ["active", "published"]}},
            {"_id": 0, "id": 1, "slug": 1, "updated_at": 1},
        ).limit(500):
            slug = op.get("slug") or op.get("id")
            urls.append(_u(f"/operator/{slug}", today, "monthly", 0.5))
    except Exception:
        pass

    # 4. Funds (collective real-estate funds).
    try:
        async for f in db.lumen_funds.find(
            {"status": "published"},
            {"_id": 0, "id": 1, "slug": 1},
        ).limit(200):
            slug = f.get("slug") or f.get("id")
            urls.append(_u(f"/fund/{slug}", today, "weekly", 0.7))
    except Exception:
        pass

    # 5. Blog (only if enabled in settings).
    if enable_blog:
        try:
            async for p in db.lumen_blog_posts.find(
                {"published": True},
                {"_id": 0, "slug": 1, "published_at": 1, "updated_at": 1},
            ).limit(500):
                slug = p.get("slug")
                if not slug:
                    continue
                ua = p.get("updated_at") or p.get("published_at")
                if isinstance(ua, datetime):
                    lastmod = ua.strftime("%Y-%m-%d")
                elif isinstance(ua, str) and len(ua) >= 10:
                    lastmod = ua[:10]
                else:
                    lastmod = today
                urls.append(_u(f"/blog/{slug}", lastmod, "monthly", 0.6))
        except Exception:
            pass

    body = "\n".join(urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        '</urlset>\n'
    )


def _build_sitemap_index_xml(origin: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <sitemap>\n'
        f'    <loc>{xml_escape(origin)}/api/seo/sitemap.xml</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        f'  </sitemap>\n'
        '</sitemapindex>\n'
    )


# ───────────────────────────────────────────────────────────────────────────
# Public endpoints
# ───────────────────────────────────────────────────────────────────────────

@router.get("/api/seo/sitemap.xml")
async def public_sitemap(request: Request) -> Response:
    origin = _origin_from_request(request)
    if _cache_is_warm("sitemap"):
        xml = _CACHE["sitemap"]
    else:
        s = await _load_settings()
        xml = await _build_sitemap_xml(origin, bool(s.get("enable_blog_in_sitemap")))
        _CACHE["sitemap"] = xml
        _CACHE["sitemap_at"] = datetime.now(timezone.utc)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={_CACHE_TTL_SECONDS}"},
    )


@router.get("/api/seo/sitemap-index.xml")
async def public_sitemap_index(request: Request) -> Response:
    origin = _origin_from_request(request)
    if _cache_is_warm("sitemap_index"):
        xml = _CACHE["sitemap_index"]
    else:
        xml = _build_sitemap_index_xml(origin)
        _CACHE["sitemap_index"] = xml
        _CACHE["sitemap_index_at"] = datetime.now(timezone.utc)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": f"public, max-age={_CACHE_TTL_SECONDS}"},
    )


@router.get("/api/seo/robots.txt")
async def public_robots(request: Request) -> Response:
    origin = _origin_from_request(request)
    s = await _load_settings()
    extras = (s.get("robots_extras") or "").rstrip() + ("\n" if s.get("robots_extras") else "")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin/\n"
        "Disallow: /investor/\n"
        "Disallow: /manager/\n"
        "Disallow: /c/view/\n"
        f"{extras}"
        f"Sitemap: {origin}/api/seo/sitemap.xml\n"
        f"Sitemap: {origin}/api/seo/sitemap-index.xml\n"
    )
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/api/seo/runtime-config")
async def public_runtime_config(request: Request) -> dict[str, Any]:
    """JSON blob the React shell consumes for per-route SEO meta.

    Surface chosen to match what the frontend SeoHead component expects:
      origin, title_template, default_title, default_description,
      default_og_image, default_locale, alt_locales,
      jsonld_org (name/url/logo/sameAs), twitter_handle.
    """
    s = await _load_settings()
    origin = s.get("origin") or _origin_from_request(request)
    return {
        "origin": origin,
        "title_template": s.get("title_template") or _DEFAULT_SETTINGS["title_template"],
        "default_title": s.get("default_title") or _DEFAULT_SETTINGS["default_title"],
        "default_description": s.get("default_description") or _DEFAULT_SETTINGS["default_description"],
        "default_og_image": s.get("default_og_image") or "",
        "default_locale": s.get("default_locale") or "uk_UA",
        "alt_locales": s.get("alt_locales") or ["en_US"],
        "jsonld_org": {
            "name":   s.get("jsonld_org_name") or "LUMEN",
            "url":    s.get("jsonld_org_url")  or origin,
            "logo":   s.get("jsonld_org_logo") or "",
            "sameAs": s.get("jsonld_org_sameAs") or [],
        },
        "twitter_handle": s.get("twitter_handle") or "",
        "sitemap_url":  f"{origin}/api/seo/sitemap.xml",
        "version":      int(s.get("version") or 1),
        "fetched_at":   _iso(_now()),
    }


# ───────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ───────────────────────────────────────────────────────────────────────────

class _SettingsPatch(BaseModel):
    origin: Optional[str] = None
    title_template: Optional[str] = None
    default_title: Optional[str] = None
    default_description: Optional[str] = None
    default_og_image: Optional[str] = None
    default_locale: Optional[str] = None
    alt_locales: Optional[list[str]] = None
    jsonld_org_name: Optional[str] = None
    jsonld_org_url: Optional[str] = None
    jsonld_org_logo: Optional[str] = None
    jsonld_org_sameAs: Optional[list[str]] = None
    twitter_handle: Optional[str] = None
    enable_blog_in_sitemap: Optional[bool] = None
    robots_extras: Optional[str] = None


@router.get("/api/admin/seo/settings")
async def admin_get_settings(_=Depends(require_admin)):
    return await _load_settings()


@router.patch("/api/admin/seo/settings")
async def admin_patch_settings(payload: _SettingsPatch, admin=Depends(require_admin)):
    patch: dict[str, Any] = {}
    for k, v in payload.dict(exclude_none=True).items():
        # Light validation
        if k == "origin" and v:
            v = v.strip().rstrip("/")
        if k == "title_template" and v and "%s" not in v:
            raise HTTPException(
                status_code=400,
                detail="title_template must contain '%s' placeholder for the page title",
            )
        patch[k] = v

    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    now = _now()
    # Ensure doc exists, then bump version on each save.
    await _load_settings()
    patch["updated_at"] = now
    patch["updated_by"] = admin.get("id") or admin.get("user_id")
    await db.lumen_seo_settings.update_one(
        {"id": _SETTINGS_ID},
        {"$set": patch, "$inc": {"version": 1}},
    )
    _invalidate_cache()
    logger.info(
        f"SEO settings patched by {admin.get('email')}: {list(patch.keys())}"
    )
    return await _load_settings()


@router.post("/api/admin/seo/cache/invalidate")
async def admin_invalidate_cache(_=Depends(require_admin)):
    _invalidate_cache()
    return {"ok": True, "invalidated_at": _iso(_now())}
