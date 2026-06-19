"""
Lumen — Public Marketplace layer (shareable cards + "Marketplace Live" feed).

Public, read-only surface that powers:
  • `GET /api/public/marketplace`         — Marketplace Live feed (cards)
  • `GET /api/public/marketplace/{id}`    — Unified shareable detail DTO

Marketplace Depth (Full Asset Page)
-----------------------------------
The detail DTO aggregates the Sprint 5–9 content that already lives in the
platform into one public card, turning it into an investment landing page:
  P1 Gallery   — photos · plans · documents · progress (ход робіт) · yield
  P2 Map       — coordinates · district · infrastructure · static map point
  P3 Q&A       — answered investor questions, inline
  P4 Listing   — secondary-market offer (owner · share · price · yield · reason)
  P5 Updates   — asset blog updates + periodic reports

Design rules (unchanged):
  • Auth NOT required to view. Actions stay role-aware on the client.
  • NO new mutating actions / flows here — this layer only READS existing
    registries (assets, asset content, secondary listings).
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from lumen_api import db, _strip_mongo, _category_with_labels, _iso  # type: ignore
from shared.money import fmt_uah_as_usd, usd_from_uah  # USD display layer

try:
    from lumen_secondary import PLATFORM_FEE_PCT, _strip_listing  # type: ignore
except Exception:  # pragma: no cover
    PLATFORM_FEE_PCT = 0.01

    def _strip_listing(d: Optional[dict]) -> Optional[dict]:  # type: ignore
        return _strip_mongo(d)

try:
    from lumen_asset_content import (  # type: ignore
        _update_out, _report_out, _document_out, _question_out,
    )
except Exception:  # pragma: no cover
    def _update_out(u): return _strip_mongo(u)
    def _report_out(r): return _strip_mongo(r)
    def _document_out(d, *, authed=False): return _strip_mongo(d)
    def _question_out(q, *, own=False): return _strip_mongo(q)

router = APIRouter(prefix="/api", tags=["lumen-marketplace"])


# ── geo fallback (used only when an asset has no explicit `geo`) ──────────────
_CITY_GEO: dict[str, dict[str, Any]] = {
    "київ":    {"lat": 50.4501, "lng": 30.5234, "region": "Київ"},
    "львів":   {"lat": 49.8397, "lng": 24.0297, "region": "Львівська обл."},
    "рівне":   {"lat": 50.6199, "lng": 26.2516, "region": "Рівненська обл."},
    "одеса":   {"lat": 46.4825, "lng": 30.7233, "region": "Одеська обл."},
    "харків":  {"lat": 49.9935, "lng": 36.2304, "region": "Харківська обл."},
    "дніпро":  {"lat": 48.4647, "lng": 35.0462, "region": "Дніпропетровська обл."},
    "бориспіль": {"lat": 50.3450, "lng": 30.9500, "region": "Київська обл."},
    "гатне":   {"lat": 50.3580, "lng": 30.3700, "region": "Київська обл."},
}


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _progress(a: dict) -> int:
    p = a.get("progress_percent")
    if p is not None:
        try:
            return max(0, min(100, int(round(float(p)))))
        except Exception:
            pass
    target = _num(a.get("round_target") or a.get("target_amount"))
    raised = _num(a.get("raised_amount") or a.get("raised"))
    if target > 0:
        return max(0, min(100, int(round(raised / target * 100))))
    return 0


def _badges(a: dict) -> list[str]:
    out: list[str] = []
    if a.get("featured"):
        out.append("Рекомендовано")
    if a.get("spv_label"):
        out.append("Окреме SPV")
    out.append("Україна")
    return out


def _static_map_url(lat: float, lng: float) -> str:
    return (
        "https://staticmap.openstreetmap.de/staticmap.php?"
        f"center={lat},{lng}&zoom=14&size=600x280&maptype=mapnik&markers={lat},{lng},red-pushpin"
    )


def _geo_for(a: dict) -> Optional[dict]:
    geo = a.get("geo") if isinstance(a.get("geo"), dict) else None
    location = a.get("location") or ""
    if not geo:
        low = location.lower()
        match = next((v for k, v in _CITY_GEO.items() if k in low), None)
        if not match:
            return None
        # district = first comma-part after the city, else the city itself
        parts = [p.strip() for p in location.split(",")]
        district = next((p for p in parts if "район" in p.lower()), parts[-1] if parts else location)
        geo = {
            "lat": match["lat"], "lng": match["lng"],
            "region": match["region"], "district": district,
            "infrastructure": [],
        }
    lat, lng = _num(geo.get("lat")), _num(geo.get("lng"))
    return {
        "lat": lat, "lng": lng,
        "region": geo.get("region") or "",
        "district": geo.get("district") or "",
        "infrastructure": geo.get("infrastructure") if isinstance(geo.get("infrastructure"), list) else [],
        "static_map_url": _static_map_url(lat, lng),
        "maps_link": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
        "address": location,
    }


def _yield_summary(a: dict) -> dict:
    ty = _num(a.get("target_yield"))
    mt = _num(a.get("min_ticket"))
    return {
        "target_yield": ty,
        "min_ticket": mt,
        "horizon_label": a.get("horizon_label") or f"{a.get('horizon_months') or 12} міс.",
        "projected_annual_income": round(mt * ty / 100.0, 2),
        "raised": _num(a.get("raised_amount") or a.get("raised")),
        "round_target": _num(a.get("round_target") or a.get("target_amount")),
        "progress_percent": _progress(a),
    }


def _split_gallery(a: dict) -> tuple[list, list]:
    """Split the raw gallery into photos vs. plans (планування) by caption."""
    photos, plans = [], []
    for g in (a.get("gallery") or []):
        if not isinstance(g, dict):
            g = {"url": g, "caption": ""}
        cap = (g.get("caption") or "").lower()
        item = {"url": g.get("url") or g.get("uri"), "caption": g.get("caption") or ""}
        if not item["url"]:
            continue
        if any(t in cap for t in ("планув", "план ", "planning", "поверх", "схема")):
            plans.append(item)
        else:
            photos.append(item)
    # explicit plans field wins/extends
    for p in (a.get("plans") or []):
        if isinstance(p, dict) and p.get("url"):
            plans.append({"url": p["url"], "caption": p.get("caption") or "Планування"})
    return photos, plans


# ── async content aggregation ────────────────────────────────────────────────
async def _content(asset_id: str) -> dict:
    updates, reports, documents, questions = [], [], [], []
    try:
        async for u in db.lumen_asset_updates.find(
            {"asset_id": asset_id, "published": True}
        ).sort("created_at", -1).limit(30):
            updates.append(_update_out(u))
    except Exception:
        pass
    try:
        async for r in db.lumen_asset_reports.find(
            {"asset_id": asset_id, "published": True}
        ).sort("created_at", -1).limit(20):
            reports.append(_report_out(r))
    except Exception:
        pass
    try:
        async for d in db.lumen_asset_documents.find(
            {"asset_id": asset_id}
        ).sort("created_at", -1).limit(30):
            documents.append(_document_out(d, authed=False))  # public view → investor docs locked
    except Exception:
        pass
    try:
        async for q in db.lumen_asset_questions.find(
            {"asset_id": asset_id, "status": "answered"}
        ).sort("created_at", -1).limit(50):
            questions.append(_question_out(q))
    except Exception:
        pass
    return {"updates": updates, "reports": reports, "documents": documents, "questions": questions}


async def _build_sections(a: dict, *, kind: str, offer: Optional[dict]) -> dict:
    asset_id = a.get("id")
    photos, plans = _split_gallery(a)
    content = await _content(asset_id)
    progress_updates = [u for u in content["updates"]
                        if u.get("kind") in ("milestone", "construction", "progress")]

    geo = _geo_for(a)
    qa_items = [{
        "question": q.get("question"),
        "answer": q.get("answer"),
        "answered_at": q.get("answered_at") or q.get("created_at"),
        "author": q.get("investor_name") or "Інвестор",
    } for q in content["questions"]]

    return {
        "gallery": {
            "photos": photos,
            "plans": plans,
            "documents": content["documents"],
            "progress": progress_updates,
            "yield": _yield_summary(a),
        },
        "map": geo,
        "qa": {"enabled": True, "count": len(qa_items), "items": qa_items},
        "updates": content["updates"],
        "reports": content["reports"],
        "bids": {"enabled": kind == "listing", "count": (offer or {}).get("bids_count", 0), "items": []},
    }


def _timeline(a: dict, *, offer: Optional[dict] = None) -> list[dict]:
    prog = _progress(a)
    status = (a.get("status") or "").lower()
    events: list[dict] = [
        {"key": "published", "label": "Об'єкт опубліковано", "date": _iso(a.get("created_at")),
         "state": "done", "note": a.get("spv_label") or "Створено SPV під об'єкт"},
        {"key": "round_open", "label": "Відкрито раунд інвестування", "date": _iso(a.get("created_at")),
         "state": "active" if prog < 100 and status not in ("closed", "funded") else "done",
         "note": f"Зібрано {prog}%"},
        {"key": "deadline", "label": "Дедлайн раунду", "date": _iso(a.get("round_deadline")),
         "state": "upcoming" if prog < 100 else "done", "note": None},
        {"key": "funded", "label": "Раунд профінансовано", "date": None,
         "state": "done" if prog >= 100 else "upcoming", "note": "Старт виплат після закриття раунду"},
    ]
    if offer:
        events.insert(0, {"key": "listed", "label": "Частку виставлено на вторинному ринку",
                          "date": _iso(offer.get("created_at")), "state": "active",
                          "note": offer.get("seller_label")})
    return events


def _listing_block(a: dict, offer: dict) -> dict:
    """P4 — secondary offer details for the public card."""
    units = offer.get("units_uah") or offer.get("units") or 0
    ppu = _num(offer.get("price_per_unit"))
    return {
        "owner_label": offer.get("seller_label"),
        "share_uah": _num(units),
        "price_per_unit": ppu,
        "total_price": round(_num(units) * ppu, 2) if ppu else None,
        "target_yield": _num(a.get("target_yield")),
        "reason": offer.get("reason") or "Ребалансування портфеля",
        "platform_fee_pct": PLATFORM_FEE_PCT,
        "status": offer.get("status"),
        "bids_count": offer.get("bids_count", 0),
    }


def _card(a: dict, *, kind: str = "asset", offer: Optional[dict] = None) -> dict:
    a = _category_with_labels(a) or a
    metric_label, metric_value = "Цільова дохідність", f"{_num(a.get('target_yield')):.1f} %"
    if kind == "listing" and offer:
        ppu = offer.get("price_per_unit")
        metric_label = "Ціна частки"
        if ppu is not None:
            metric_value = fmt_uah_as_usd(ppu, decimals=2)
    return {
        "id": (offer or {}).get("id") or a.get("id"),
        "asset_id": a.get("id"),
        "kind": kind,
        "title": a.get("title"),
        "subtitle": a.get("location") or a.get("category_label") or "",
        "category": a.get("category"),
        "category_label": a.get("category_label") or a.get("category"),
        "cover_url": a.get("cover_url"),
        "location": a.get("location"),
        "metric_label": metric_label,
        "metric_value": metric_value,
        "progress_percent": _progress(a),
        "status": a.get("status"),
        "status_label": a.get("status_label") or a.get("status"),
        "badge": "Вторинний ринок" if kind == "listing" else "Первинний раунд",
    }


async def _dto(a: dict, *, kind: str = "asset", offer: Optional[dict] = None) -> dict:
    a = _category_with_labels(a) or a
    asset_id = a.get("id")
    action: dict[str, Any] = {
        "kind": kind,
        "target_yield": _num(a.get("target_yield")),
        "min_ticket": _num(a.get("min_ticket")),
        "progress_percent": _progress(a),
        "round_target": _num(a.get("round_target") or a.get("target_amount")),
        "raised": _num(a.get("raised_amount") or a.get("raised")),
        "round_deadline": _iso(a.get("round_deadline")),
    }
    if kind == "listing" and offer:
        action.update({
            "price_per_unit": offer.get("price_per_unit"),
            "units_available": offer.get("units_uah") or offer.get("units"),
            "platform_fee_pct": PLATFORM_FEE_PCT,
            "seller_label": offer.get("seller_label"),
            "listing_status": offer.get("status"),
        })
    return {
        "id": (offer or {}).get("id") or asset_id,
        "kind": kind,
        "asset_id": asset_id,
        "hero": {
            "title": a.get("title"),
            "category": a.get("category"),
            "category_label": a.get("category_label") or a.get("category"),
            "location": a.get("location"),
            "cover_url": a.get("cover_url"),
            "status": a.get("status"),
            "status_label": a.get("status_label") or a.get("status"),
            "description": a.get("description"),
        },
        "trust": {
            "spv_label": a.get("spv_label") or "ТОВ «Lumen-Asset SPV»",
            "residency": "Україна",
            "min_ticket": _num(a.get("min_ticket")),
            "target_yield": _num(a.get("target_yield")),
            "horizon_label": a.get("horizon_label") or f"{a.get('horizon_months') or 12} міс.",
            "investors_count": a.get("investors_count") or 0,
            "badges": _badges(a),
        },
        "timeline": _timeline(a, offer=offer),
        "action": action,
        "listing": _listing_block(a, offer) if (kind == "listing" and offer) else None,
        "sections": await _build_sections(a, kind=kind, offer=offer),
        "economics_endpoint": f"/api/assets/{asset_id}/economics",
        "share": {"title": a.get("title"), "path": f"/marketplace/{(offer or {}).get('id') or asset_id}"},
    }


# ── endpoints ────────────────────────────────────────────────────────────────
@router.get("/public/marketplace")
async def public_feed(
    kind: Optional[str] = Query(None, description="asset | listing | all"),
    category: Optional[str] = None,
    limit: int = Query(60, ge=1, le=200),
):
    items: list[dict] = []
    if kind in (None, "all", "asset"):
        q: dict[str, Any] = {}
        if category:
            q["category"] = category
        async for a in db.lumen_assets.find(q).sort("created_at", -1).limit(limit):
            items.append(_card(_strip_mongo(a)))
    if kind in (None, "all", "listing"):
        try:
            async for L in db.lumen_secondary_listings.find(
                {"status": {"$in": ["active", "partially_filled"]}}
            ).sort("created_at", -1).limit(limit):
                off = _strip_listing(L) or {}
                off.setdefault("seller_label", f"Інвестор #{str(L.get('seller_id') or '')[-6:]}")
                off.pop("seller_id", None)
                a = await db.lumen_assets.find_one({"id": L.get("asset_id")})
                if a:
                    items.append(_card(_strip_mongo(a), kind="listing", offer=off))
        except Exception:
            pass
    return {"items": items, "count": len(items), "platform_fee_pct": PLATFORM_FEE_PCT}


@router.get("/public/marketplace/{item_id}")
async def public_item(item_id: str):
    a = await db.lumen_assets.find_one({"id": item_id})
    if a:
        return await _dto(_strip_mongo(a), kind="asset")

    L = await db.lumen_secondary_listings.find_one({"id": item_id})
    if L:
        a2 = await db.lumen_assets.find_one({"id": L.get("asset_id")})
        if not a2:
            raise HTTPException(status_code=404, detail="Базовий об'єкт не знайдено")
        off = _strip_listing(L) or {}
        off.setdefault("seller_label", f"Інвестор #{str(L.get('seller_id') or '')[-6:]}")
        off.pop("seller_id", None)
        try:
            off["bids_count"] = await db.lumen_secondary_bids.count_documents({"listing_id": item_id})
        except Exception:
            off["bids_count"] = 0
        return await _dto(_strip_mongo(a2), kind="listing", offer=off)

    raise HTTPException(status_code=404, detail="Картку не знайдено")
