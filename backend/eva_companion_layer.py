"""
EVA COMPANION — мобільний/веб-маскот-робот, який супроводжує гостя по сайту.

Архітектура аналогічна banner_layer:
  • Singleton config (`system_config.eva_companion`) — один активний конфіг на платформу.
  • Admineditable через /api/admin/eva-companion (admin_only).
  • Публічний GET /api/public/eva-companion — повертає поточну версію
    (фронт кешує і polled-refresh-ить раз на 60s).
  • Public POST /api/public/eva-companion/intent — фіксує наміри гостя
    ("see_estimator", "open_callback", "dismissed_session", "register_click"),
    щоб адмін бачив реальну воронку маскота і міг A/B-тестити копію.

Лід-капчер callback переюзає існуючий /api/public/contact-leads з
banner_layer (source="eva-companion"). Це гарантує єдине джерело правди по лідам.
"""
from fastapi import APIRouter, Depends, Body, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


# ============== CONFIG MODEL ==============

class EvaTone(BaseModel):
    """Базова стилістика — підв'язана до design system EVA-X."""
    accent: str = "#D4A574"          # каркас + glow робота
    bg: str = "rgba(20,20,22,0.94)"  # тон корпусу хмарки
    text: str = "#FAFAF7"
    mood: str = "curious"            # curious | helpful | celebratory


class EvaCTA(BaseModel):
    """Одна дія в розкритій хмарці робота."""
    id: str = Field(default_factory=lambda: f"cta_{uuid.uuid4().hex[:6]}")
    label: str = ""
    icon: str = "sparkles"           # sparkles | calculator | message | rocket
    kind: str = "scroll"             # scroll | route | callback | register | external
    target: str = ""                 # для scroll: anchor; route: path; external: url


class EvaCompanionConfig(BaseModel):
    enabled: bool = True

    # Якщо False — маскот ніколи не з'являється для авторизованих юзерів.
    show_to_guests: bool = True
    show_to_logged_in: bool = False

    # Поведінка
    appear_after_ms: int = 6000       # затримка появи після завантаження
    idle_pulse_every_ms: int = 14000  # періодичний "вдих" робота
    auto_open_after_ms: int = 0       # 0 = ніколи; інакше — авто-розкриття хмарки
    dismiss_session_hours: int = 12   # після X гість бачить його знову

    # Контент — мультимовний (UA/EN), фронт сам бере по поточній мові
    greeting_en: str = "Hi, I'm EVA. Want me to estimate your project?"
    greeting_uk: str = "Привіт, я EVA. Розрахувати твій проєкт?"
    subline_en: str = "Real software, shipped. Not tasks."
    subline_uk: str = "Готовий продукт, не задачі."

    # До 4 CTA — фронт показує перші 3 (mobile 2)
    ctas: List[EvaCTA] = Field(default_factory=lambda: [
        EvaCTA(label="Estimate project",  icon="calculator", kind="scroll", target="estimator"),
        EvaCTA(label="Request callback",  icon="message",    kind="callback", target=""),
        EvaCTA(label="Start now",         icon="rocket",     kind="register", target=""),
    ])

    # Стилістика
    tone: EvaTone = Field(default_factory=EvaTone)

    # Платформи
    show_on_web: bool = True
    show_in_expo: bool = False

    # Технічна
    version: int = 1
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


def _default_config() -> Dict[str, Any]:
    return EvaCompanionConfig().model_dump()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============== ROUTER ==============

def build_router(db, get_current_user, require_role):
    router = APIRouter()
    admin_only = require_role("admin")
    cfg_coll = db.system_config
    events = db.eva_companion_events

    async def _read_cfg() -> Dict[str, Any]:
        doc = await cfg_coll.find_one({"key": "eva_companion"}, {"_id": 0})
        if not doc:
            return _default_config()
        cfg = doc.get("value") or {}
        # merge with defaults — щоб старі версії автоматично отримували нові поля
        merged = _default_config()
        merged.update(cfg)
        merged["version"] = doc.get("version", 1)
        merged["updated_at"] = doc.get("updated_at")
        merged["updated_by"] = doc.get("updated_by")
        return merged

    # ----- PUBLIC -----

    @router.get("/public/eva-companion")
    async def public_config(platform: str = Query("web")):
        cfg = await _read_cfg()
        if not cfg.get("enabled"):
            return {"companion": None}
        flag = "show_on_web" if platform == "web" else "show_in_expo"
        if not cfg.get(flag, True):
            return {"companion": None}
        # public payload — без службових полів
        cfg.pop("updated_by", None)
        return {"companion": cfg}

    @router.post("/public/eva-companion/intent")
    async def public_intent(
        action: str = Body(..., embed=True),
        meta: Dict[str, Any] = Body(default_factory=dict, embed=True),
        session_id: str = Body(default="", embed=True),
    ):
        valid = {
            "appeared", "expanded", "dismissed_session",
            "cta_estimator", "cta_callback", "cta_register",
            "cta_external", "cta_route", "lead_submitted",
        }
        if action not in valid:
            action = "unknown"
        await events.insert_one({
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "action": action,
            "session_id": session_id[:64],
            "meta": meta or {},
            "ts": _now_iso(),
        })
        return {"ok": True}

    # ----- ADMIN -----

    @router.get("/admin/eva-companion")
    async def admin_get(_admin=Depends(admin_only)):
        cfg = await _read_cfg()
        # 24h funnel
        since = datetime.now(timezone.utc).replace(microsecond=0).isoformat()[:10]
        pipeline = [
            {"$match": {"ts": {"$gte": f"{since}T00:00:00+00:00"}}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        ]
        funnel = {row["_id"]: row["count"] async for row in events.aggregate(pipeline)}
        return {"config": cfg, "funnel_today": funnel}

    @router.put("/admin/eva-companion")
    async def admin_put(spec: EvaCompanionConfig, admin=Depends(admin_only)):
        now = _now_iso()
        data = spec.model_dump()
        # bump version + author trail
        prev = await cfg_coll.find_one({"key": "eva_companion"}, {"_id": 0})
        new_version = (prev or {}).get("version", 0) + 1
        await cfg_coll.update_one(
            {"key": "eva_companion"},
            {"$set": {
                "value": data,
                "version": new_version,
                "updated_at": now,
                "updated_by": (admin or {}).get("email") if isinstance(admin, dict) else None,
            }},
            upsert=True,
        )
        return {"ok": True, "version": new_version, "updated_at": now}

    @router.post("/admin/eva-companion/reset")
    async def admin_reset(_admin=Depends(admin_only)):
        defaults = _default_config()
        await cfg_coll.update_one(
            {"key": "eva_companion"},
            {"$set": {"value": defaults, "version": 1, "updated_at": _now_iso()}},
            upsert=True,
        )
        return {"ok": True}

    @router.get("/admin/eva-companion/events")
    async def admin_events(limit: int = Query(200, ge=1, le=1000), _admin=Depends(admin_only)):
        items = await events.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
        return {"events": items, "total": len(items)}

    return router
