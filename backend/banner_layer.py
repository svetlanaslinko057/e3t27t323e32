"""
MARKETING — Promo Banner + Contact Leads.

Mounted via: fastapi_app.include_router(banner_layer.build_router(db, get_current_user, require_role), prefix="/api")

Two surfaces:
  • Promo banner — configured in admin, shown on web (and optionally Expo).
    Single active banner at a time (activating one deactivates the rest).
    Supports date-window + live countdown, two placements (top_bar / hero_card / both),
    CTA modes (custom url / register / open contact modal), accent colour, type.
  • Contact leads — submissions from the site-wide "leave a request" modal.

All content fields are free-text (any language). Admin UI is bilingual UK/EN
(handled on the frontend); the stored banner content is language-agnostic.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid
from datetime import datetime, timezone


# ========== MODELS ==========

BANNER_TYPES = ("discount", "special", "announcement", "app")
PLACEMENTS = ("top_bar", "hero_card", "both")
CTA_MODES = ("url", "register", "contact")
PLATFORMS = ("web", "expo")


class BannerSpec(BaseModel):
    enabled: bool = False
    type: str = Field(default="special")
    placement: str = Field(default="both")

    title: str = ""
    subtitle: str = ""
    features: List[str] = Field(default_factory=list)

    price: str = ""
    old_price: str = ""
    currency: str = "$"

    starts_at: Optional[str] = None   # ISO string or null
    ends_at: Optional[str] = None     # ISO string or null
    show_countdown: bool = True

    cta_text: str = ""
    cta_mode: str = Field(default="contact")
    cta_url: str = ""

    accent: str = "#D4A574"           # accent colour (hex)
    badge: str = ""                   # small kicker label, e.g. "LIMITED"

    show_on_web: bool = True
    show_in_expo: bool = False


class ContactLeadSpec(BaseModel):
    name: str = ""
    contact: str = ""                 # email / phone / telegram — free text
    message: str = ""
    source: str = "site"              # where it came from (banner / footer / cta…)
    banner_id: Optional[str] = None
    locale: Optional[str] = None


def _now():
    return datetime.now(timezone.utc)


def _parse_iso(v):
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _validate(spec: BannerSpec):
    if spec.type not in BANNER_TYPES:
        raise HTTPException(400, f"Invalid type. Allowed: {BANNER_TYPES}")
    if spec.placement not in PLACEMENTS:
        raise HTTPException(400, f"Invalid placement. Allowed: {PLACEMENTS}")
    if spec.cta_mode not in CTA_MODES:
        raise HTTPException(400, f"Invalid cta_mode. Allowed: {CTA_MODES}")


# ========== ROUTER FACTORY ==========

def build_router(db, get_current_user, require_role):
    router = APIRouter()
    admin_only = require_role("admin")

    banners = db.promo_banners
    leads = db.contact_leads

    # ---------- ADMIN: banners ----------

    @router.get("/admin/banners")
    async def list_banners(_admin=Depends(admin_only)):
        items = await banners.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
        return {"banners": items}

    @router.post("/admin/banners")
    async def create_banner(spec: BannerSpec, _admin=Depends(admin_only)):
        _validate(spec)
        now = _now().isoformat()
        doc = spec.model_dump()
        doc["id"] = f"banner_{uuid.uuid4().hex[:12]}"
        doc["created_at"] = now
        doc["updated_at"] = now
        # Single active banner — turning this on deactivates the others.
        if doc["enabled"]:
            await banners.update_many({"enabled": True}, {"$set": {"enabled": False, "updated_at": now}})
        await banners.insert_one(doc)
        return _clean(doc)

    @router.put("/admin/banners/{banner_id}")
    async def update_banner(banner_id: str, spec: BannerSpec, _admin=Depends(admin_only)):
        _validate(spec)
        existing = await banners.find_one({"id": banner_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Banner not found")
        now = _now().isoformat()
        doc = spec.model_dump()
        doc["updated_at"] = now
        if doc["enabled"]:
            await banners.update_many(
                {"enabled": True, "id": {"$ne": banner_id}},
                {"$set": {"enabled": False, "updated_at": now}},
            )
        await banners.update_one({"id": banner_id}, {"$set": doc})
        updated = await banners.find_one({"id": banner_id}, {"_id": 0})
        return updated

    @router.post("/admin/banners/{banner_id}/toggle")
    async def toggle_banner(banner_id: str, _admin=Depends(admin_only)):
        existing = await banners.find_one({"id": banner_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Banner not found")
        now = _now().isoformat()
        new_state = not existing.get("enabled", False)
        if new_state:
            await banners.update_many({"enabled": True}, {"$set": {"enabled": False, "updated_at": now}})
        await banners.update_one({"id": banner_id}, {"$set": {"enabled": new_state, "updated_at": now}})
        return {"id": banner_id, "enabled": new_state}

    @router.delete("/admin/banners/{banner_id}")
    async def delete_banner(banner_id: str, _admin=Depends(admin_only)):
        res = await banners.delete_one({"id": banner_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "Banner not found")
        return {"deleted": True, "id": banner_id}

    # ---------- PUBLIC: active banner ----------

    @router.get("/public/banner")
    async def public_active_banner(platform: str = Query("web")):
        if platform not in PLATFORMS:
            platform = "web"
        flag = "show_on_web" if platform == "web" else "show_in_expo"
        candidates = await banners.find(
            {"enabled": True, flag: True}, {"_id": 0}
        ).sort("updated_at", -1).to_list(20)
        now = _now()
        for b in candidates:
            sa = _parse_iso(b.get("starts_at"))
            ea = _parse_iso(b.get("ends_at"))
            if sa and now < sa:
                continue
            if ea and now > ea:
                continue
            return {"banner": b}
        return {"banner": None}

    # ---------- PUBLIC: contact lead submit ----------

    @router.post("/public/contact-leads")
    async def submit_contact_lead(spec: ContactLeadSpec):
        if not (spec.contact or "").strip() and not (spec.name or "").strip():
            raise HTTPException(400, "Name or contact is required")
        now = _now().isoformat()
        doc = spec.model_dump()
        doc["id"] = f"lead_{uuid.uuid4().hex[:12]}"
        doc["status"] = "new"
        doc["created_at"] = now
        await leads.insert_one(doc)
        return {"ok": True, "id": doc["id"]}

    # ---------- ADMIN: contact leads ----------

    @router.get("/admin/contact-leads")
    async def list_contact_leads(_admin=Depends(admin_only)):
        items = await leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
        new_count = sum(1 for x in items if x.get("status") == "new")
        return {"leads": items, "total": len(items), "new": new_count}

    @router.patch("/admin/contact-leads/{lead_id}")
    async def update_contact_lead(lead_id: str, status: str = Body(..., embed=True), _admin=Depends(admin_only)):
        if status not in ("new", "handled", "archived"):
            raise HTTPException(400, "Invalid status")
        res = await leads.update_one({"id": lead_id}, {"$set": {"status": status}})
        if res.matched_count == 0:
            raise HTTPException(404, "Lead not found")
        return {"id": lead_id, "status": status}

    return router
