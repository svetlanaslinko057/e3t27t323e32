"""
Lumen investment platform router.

Adds the new investor / admin investment endpoints on top of the existing
EVA-X backend without rewriting the legacy routers. Storage is MongoDB
collections in the same database; if collections are empty we seed a
deterministic Ukrainian-language demo set so the freshly built frontend is
not empty for testers and the first preview audience.

Endpoints
=========
Public
    GET    /api/assets?status=open&category=...
    GET    /api/assets/{asset_id}

Investor (auth required, role: client/investor/admin)
    GET    /api/investor/portfolio
    GET    /api/investor/investments
    GET    /api/investor/payouts
    GET    /api/investor/documents
    GET    /api/investor/notifications
    POST   /api/investor/notifications/read-all
    POST   /api/investor/intent

Admin (auth required, role: admin)
    GET    /api/admin/overview
    GET    /api/admin/investors
    GET    /api/admin/assets
    POST   /api/admin/assets
    PATCH  /api/admin/assets/{asset_id}
    DELETE /api/admin/assets/{asset_id}
    GET    /api/admin/rounds
    GET    /api/admin/payments
    GET    /api/admin/documents
    GET    /api/admin/reports

The router intentionally relies on cookie-based auth via the existing
`session_token` cookie issued by the EVA-X auth layer. We resolve the
session lazily so the module stays decoupled from the legacy server
imports.
"""

from __future__ import annotations

import os
import uuid
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


# ----------------------------------------------------------------------------
# DB bootstrap (independent of legacy server module)
# ----------------------------------------------------------------------------

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "evax_devos")

_client: AsyncIOMotorClient = AsyncIOMotorClient(_MONGO_URL)
db: AsyncIOMotorDatabase = _client[_DB_NAME]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return None


def _strip_mongo(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = _iso(v)
    return doc


CATEGORY_LABELS = {
    "real_estate": "нерухомість",
    "land": "земля",
    "construction": "будівництво",
    "commercial": "комерція",
}
STATUS_LABELS = {
    "open": "відкрито",
    "draft": "чернетка",
    "closed": "закрито",
    "paused": "на паузі",
}
PAYOUT_KIND_LABELS = {
    "investment": "внесок",
    "dividend": "дивіденд",
    "exit": "вихід",
    "refund": "повернення",
}
PAYOUT_STATUS_LABELS = {
    "paid": "виплачено",
    "pending": "в очікуванні",
    "scheduled": "заплановано",
    "failed": "помилка",
}


# ----------------------------------------------------------------------------
# Auth dep (cookie-based; reads `session_token` and resolves user)
# ----------------------------------------------------------------------------

async def get_current_user(request: Request) -> dict:
    # Web clients send the session in a cookie; mobile (Expo) clients send it as
    # `Authorization: Bearer <session_token>`. Accept both.
    token = request.cookies.get("session_token") or request.cookies.get("auth_session_token")
    if not token:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизовано")
    # Legacy session storage. Different collections used at different points
    # in the EVA-X history; we probe all of them for compatibility.
    sess = (
        await db.user_sessions.find_one({"session_token": token})
        or await db.sessions.find_one({"token": token})
        or await db.auth_sessions.find_one({"token": token})
    )
    if not sess:
        raise HTTPException(status_code=401, detail="Сесія недійсна")
    user_id = sess.get("user_id") or sess.get("uid")
    user = None
    if user_id:
        user = (
            await db.users.find_one({"user_id": user_id})
            or await db.users.find_one({"id": user_id})
        )
    if not user:
        raise HTTPException(status_code=401, detail="Користувача не знайдено")
    user = _strip_mongo(user)
    # Normalise id field so callers can rely on it
    if "id" not in user and "user_id" in user:
        user["id"] = user["user_id"]
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Тільки для адміністратора")
    return user


# Unified staff gate — admin OR manager (manager = merged manager+operator role).
# Used by the Investor-Relations / Manager-OS cabinet so a manager login can
# operate the same surface as an admin. The access gate already treats
# manager/operator as STAFF, so this is the per-route authorization layer.
_STAFF_ROLES = {"admin", "manager", "operator", "team_lead", "owner", "master_admin"}


async def require_staff(user: dict = Depends(get_current_user)) -> dict:
    role = (user.get("role") or "").lower()
    roles = {str(r).lower() for r in (user.get("roles") or [])}
    if role in _STAFF_ROLES or (roles & _STAFF_ROLES):
        return user
    raise HTTPException(status_code=403, detail="Доступ лише для персоналу")


# ── LR2.7 Permission Engine bridge ──
# Centralised helper so any module can import a permission gate without taking
# a hard dependency on lumen_lr2_extended (which itself imports from this
# module — would create a cycle). Resolves the real `require_permission`
# lazily at request-time.
def lr2_perm(resource: str, action: str):
    """Returns a FastAPI dependency that gates a route on (resource, action).

    Falls back to require_admin when the LR2 extended module is unavailable,
    so routes don't break in environments where LR2 isn't mounted.
    """
    try:
        from lumen_lr2_extended import require_permission as _rp  # noqa: WPS433
        return _rp(resource, action)
    except Exception:
        return require_admin


# ----------------------------------------------------------------------------
# Seed (idempotent)
# ----------------------------------------------------------------------------

_DEMO_ASSETS = [
    {
        "id": "asset-podilskyi",
        "title": 'ЖК «Подільський»',
        "category": "real_estate",
        "location": "Київ, Поділ",
        "cover_url": "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "Дев'ятиповерховий житловий комплекс комфорт-класу в історичному районі Подолу.\n"
            "84 квартири, паркінг, комерційні приміщення на першому поверсі. "
            "Девелопер з 12-річним досвідом, об'єкт вже на стадії 4-го поверху."
        ),
        "status": "open",
        "target_yield": 18.5,
        "horizon_months": 24,
        "min_ticket": 75000,
        "round_target": 4_800_000,
        "raised": 2_976_000,
        "round_deadline": (_now() + timedelta(days=45)).isoformat(),
        "spv_label": "ТОВ «Подільський Інвест»",
        "investors_count": 38,
        "featured": True,
    },
    {
        "id": "asset-stoyanka-land",
        "title": "Земельна ділянка «Стоянка»",
        "category": "land",
        "location": "Бориспільський район, Київська обл.",
        "cover_url": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "2,4 га ділянки під житлову забудову біля майбутньої розв'язки. "
            "Цільове призначення — комерційна та змішана. Зростання вартості за 18 місяців "
            "за моделлю — від 35%."
        ),
        "status": "open",
        "target_yield": 22.0,
        "horizon_months": 18,
        "min_ticket": 150000,
        "round_target": 3_200_000,
        "raised": 992_000,
        "round_deadline": (_now() + timedelta(days=60)).isoformat(),
        "spv_label": "ТОВ «Стоянка Лендс»",
        "investors_count": 14,
        "featured": True,
    },
    {
        "id": "asset-lavr-tc",
        "title": 'ТЦ «Лавр»',
        "category": "commercial",
        "location": "Львів, Шевченківський район",
        "cover_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "Діючий торговий центр площею 6 200 м². Заповнення орендарями — 92%. "
            "Якірні орендарі: продуктовий ритейл, аптека, побутова техніка. "
            "Дохід з оренди розподіляється щомісяця."
        ),
        "status": "open",
        "target_yield": 14.7,
        "horizon_months": 36,
        "min_ticket": 100000,
        "round_target": 6_500_000,
        "raised": 5_720_000,
        "round_deadline": (_now() + timedelta(days=20)).isoformat(),
        "spv_label": "ТОВ «Лавр Капітал»",
        "investors_count": 62,
        "featured": True,
    },
    {
        "id": "asset-rivne-warehouse",
        "title": "Логістичний хаб «Рівне-Захід»",
        "category": "construction",
        "location": "Рівне, об'їзна траса",
        "cover_url": "https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "Будівництво складського комплексу класу B+ загальною площею 9 800 м². "
            "Контракт з трьома логістичними операторами на 5 років після введення в експлуатацію."
        ),
        "status": "open",
        "target_yield": 19.2,
        "horizon_months": 30,
        "min_ticket": 200000,
        "round_target": 8_400_000,
        "raised": 1_680_000,
        "round_deadline": (_now() + timedelta(days=75)).isoformat(),
        "spv_label": "ТОВ «Захід Логістика»",
        "investors_count": 9,
        "featured": False,
    },
    {
        "id": "asset-odessa-apartments",
        "title": "Прибутковий будинок «Французький»",
        "category": "real_estate",
        "location": "Одеса, Французький бульвар",
        "cover_url": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "Купівля 12 квартир у новобудові з подальшою здачею в довгострокову оренду. "
            "Розподіл доходу щомісяця, ліквідний вторинний ринок."
        ),
        "status": "open",
        "target_yield": 13.4,
        "horizon_months": 48,
        "min_ticket": 65000,
        "round_target": 2_900_000,
        "raised": 0,
        "round_deadline": (_now() + timedelta(days=90)).isoformat(),
        "spv_label": "ТОВ «Французький Капітал»",
        "investors_count": 0,
        "featured": False,
    },
    {
        "id": "asset-vyshneve-cottage",
        "title": "Котеджне містечко «Вишневе»",
        "category": "construction",
        "location": "Київська обл., с. Гатне",
        "cover_url": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1200&q=80",
        "description": (
            "26 котеджів площею 110-160 м² з ділянками 5-7 соток. "
            "Готовність зовнішніх мереж 100%, початок будівництва — 1 кв. 2026 р."
        ),
        "status": "draft",
        "target_yield": 21.5,
        "horizon_months": 28,
        "min_ticket": 180000,
        "round_target": 5_400_000,
        "raised": 0,
        "round_deadline": (_now() + timedelta(days=120)).isoformat(),
        "spv_label": "ТОВ «Вишневе Девелопмент»",
        "investors_count": 0,
        "featured": False,
    },
]


async def _ensure_seed():
    count = await db.lumen_assets.count_documents({})
    if count == 0:
        for a in _DEMO_ASSETS:
            doc = dict(a)
            doc["created_at"] = _now()
            doc["updated_at"] = _now()
            await db.lumen_assets.insert_one(doc)
    # demo investments + payouts (only when first run)
    invs = await db.lumen_investments.count_documents({})
    if invs == 0:
        sample_user = await db.users.find_one({"role": {"$in": ["client", "investor"]}}) \
            or await db.users.find_one({"email": "client@atlas.dev"})
        if sample_user:
            uid = sample_user.get("user_id") or sample_user.get("id")
            now = _now()
            # ensure user looks like an investor
            await db.users.update_one(
                {"user_id": uid} if sample_user.get("user_id") else {"id": uid},
                {"$set": {"role": "investor", "kyc_status": sample_user.get("kyc_status") or "approved"}},
            )
            seed_investments = [
                {"asset_id": "asset-podilskyi", "amount": 250000, "share": 5.2, "yield": 19.1, "days_ago": 90},
                {"asset_id": "asset-lavr-tc",   "amount": 400000, "share": 6.2, "yield": 14.7, "days_ago": 180},
                {"asset_id": "asset-stoyanka-land", "amount": 200000, "share": 6.3, "yield": 21.4, "days_ago": 45},
            ]
            for s in seed_investments:
                asset = await db.lumen_assets.find_one({"id": s["asset_id"]})
                if not asset:
                    continue
                inv_id = f"inv-{uuid.uuid4().hex[:10]}"
                await db.lumen_investments.insert_one({
                    "id": inv_id,
                    "investor_id": uid,
                    "asset_id": s["asset_id"],
                    "asset_title": asset["title"],
                    "asset_location": asset["location"],
                    "round_label": "Раунд I",
                    "invested_amount": s["amount"],
                    "share_percent": s["share"],
                    "current_yield": s["yield"],
                    "invested_at": now - timedelta(days=s["days_ago"]),
                    "status": "active",
                })
                # initial investment payout (out)
                await db.lumen_payouts.insert_one({
                    "id": f"po-{uuid.uuid4().hex[:10]}",
                    "investor_id": uid,
                    "investment_id": inv_id,
                    "asset_id": s["asset_id"],
                    "asset_title": asset["title"],
                    "title": f"Внесок · {asset['title']}",
                    "kind": "investment",
                    "direction": "out",
                    "amount": s["amount"],
                    "status": "paid",
                    "created_at": now - timedelta(days=s["days_ago"]),
                })
                # 2 dividend payouts in the past
                for i in range(1, 3):
                    await db.lumen_payouts.insert_one({
                        "id": f"po-{uuid.uuid4().hex[:10]}",
                        "investor_id": uid,
                        "investment_id": inv_id,
                        "asset_id": s["asset_id"],
                        "asset_title": asset["title"],
                        "title": f"Дивіденд · {asset['title']}",
                        "kind": "dividend",
                        "direction": "in",
                        "amount": round(s["amount"] * s["yield"] / 100 / 12, 0),
                        "status": "paid",
                        "created_at": now - timedelta(days=max(1, s["days_ago"] - i * 30)),
                    })
                # 1 upcoming
                await db.lumen_payouts.insert_one({
                    "id": f"po-{uuid.uuid4().hex[:10]}",
                    "investor_id": uid,
                    "investment_id": inv_id,
                    "asset_id": s["asset_id"],
                    "asset_title": asset["title"],
                    "title": f"Дивіденд · {asset['title']}",
                    "kind": "dividend",
                    "direction": "in",
                    "amount": round(s["amount"] * s["yield"] / 100 / 12, 0),
                    "status": "scheduled",
                    "scheduled_at": now + timedelta(days=12),
                    "created_at": now,
                })
            # one signed document
            await db.lumen_documents.insert_one({
                "id": f"doc-{uuid.uuid4().hex[:10]}",
                "investor_id": uid,
                "asset_id": "asset-podilskyi",
                "asset_title": "ЖК «Подільський»",
                "title": "Договір участі №ЛП-0241",
                "kind": "contract",
                "url": "#",
                "created_at": now - timedelta(days=90),
            })
            # welcome notification
            await db.lumen_notifications.insert_one({
                "id": f"n-{uuid.uuid4().hex[:10]}",
                "investor_id": uid,
                "title": "Ласкаво просимо до Lumen",
                "body": "Ваш кабінет готовий. Перегляньте відкриті раунди, щоб зробити перші інвестиції.",
                "read": False,
                "created_at": now,
            })


def _category_with_labels(a: dict) -> dict:
    a = dict(a)
    a["category_label"] = CATEGORY_LABELS.get(a.get("category"), a.get("category"))
    a["status_label"] = STATUS_LABELS.get(a.get("status"), a.get("status"))
    if a.get("round_target"):
        raised = a.get("raised") or 0
        a["progress_percent"] = min(100, int(round((raised / a["round_target"]) * 100))) if a["round_target"] else 0
    else:
        a["progress_percent"] = 0
    a["horizon_label"] = f"{a.get('horizon_months', 12)} міс."
    # ─── Lumen economics defaults ───────────────────────────────────────────
    # Кожен актив може зберігати власну економічну модель. Якщо ні — повертаємо
    # розумні значення за замовчуванням, щоб мобільний/веб-клієнт не падали.
    cat = a.get("category")
    cat_defaults = _ECONOMICS_DEFAULTS.get(cat, _ECONOMICS_DEFAULTS["_global"])
    a["rental_share"]  = float(a.get("rental_share")  or cat_defaults["rental_share"])
    a["opex_rate"]     = float(a.get("opex_rate")     or cat_defaults["opex_rate"])
    a["tax_rate"]      = float(a.get("tax_rate")      or cat_defaults["tax_rate"])
    a["platform_fee"]  = float(a.get("platform_fee")  or cat_defaults["platform_fee"])
    return _strip_mongo(a)


# Категорія-залежні дефолти економіки. Чим «комерційніший» актив — тим вища
# частка з оренди і тим вищі експлуатаційні. Землю / девелопмент майже
# повністю формує переоцінка.
_ECONOMICS_DEFAULTS: dict[str, dict[str, float]] = {
    "_global":      {"rental_share": 0.55, "opex_rate": 0.12, "tax_rate": 0.195, "platform_fee": 0.02},
    "residential":  {"rental_share": 0.60, "opex_rate": 0.10, "tax_rate": 0.195, "platform_fee": 0.02},
    "commercial":   {"rental_share": 0.75, "opex_rate": 0.15, "tax_rate": 0.195, "platform_fee": 0.02},
    "logistics":    {"rental_share": 0.80, "opex_rate": 0.10, "tax_rate": 0.195, "platform_fee": 0.02},
    "land":         {"rental_share": 0.05, "opex_rate": 0.03, "tax_rate": 0.195, "platform_fee": 0.02},
    "development":  {"rental_share": 0.10, "opex_rate": 0.05, "tax_rate": 0.195, "platform_fee": 0.025},
}


def _payout_with_labels(p: dict) -> dict:
    p = dict(p)
    p["kind_label"] = PAYOUT_KIND_LABELS.get(p.get("kind"), p.get("kind"))
    p["status_label"] = PAYOUT_STATUS_LABELS.get(p.get("status"), p.get("status"))
    return _strip_mongo(p)


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["lumen"])


@router.on_event("startup")
async def _startup():
    try:
        await _ensure_seed()
    except Exception:
        # never block boot
        pass


# ---- Public asset catalogue -------------------------------------------------

@router.get("/assets")
async def list_assets(status: str | None = None, category: str | None = None,
                      featured: bool | None = None, limit: int = 50):
    await _ensure_seed()
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if category:
        q["category"] = category
    if featured is not None:
        q["featured"] = featured
    cur = db.lumen_assets.find(q).sort("created_at", -1).limit(max(1, min(limit, 100)))
    items = [_category_with_labels(a) async for a in cur]
    return {"items": items, "total": len(items)}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    a = await db.lumen_assets.find_one({"id": asset_id})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    return _category_with_labels(a)


# ───────────────────────────────────────────────────────────────────────────
# Версія економічної моделі. Будь-яка зміна формули, дефолтів або частки —
# піднімайте цей номер. Клієнтські бібліотеки порівнюють його з власною
# `LUMEN_ECONOMICS_VERSION` і голосно скаржаться у логах, якщо вони розійшлись.
# ───────────────────────────────────────────────────────────────────────────
ECONOMICS_VERSION = "1.0.0"


@router.get("/economics/spec")
async def economics_spec():
    """JSON-специфікація економічної моделі Lumen.

    Дозволяє:
      • клієнтським тестам (web + mobile) валідувати паритет розрахунку
      • UI-debug сторінкам показувати, які саме дефолти/сценарії зараз активні
      • CI-перевіркам видавати фейл, якщо хтось правив формулу лише на одному боці

    Структура:
      version        — semver моделі (треба піднімати на будь-якій зміні)
      defaults       — категорійні дефолти (rental_share, opex_rate, ...)
      scenarios      — UX-список «Що якби» (UI клієнтів синхронізує сюди)
      golden_samples — масив input/expected пар. Клієнт обраховує те саме
                       й порівнює з expected з допустимою похибкою 0.01 USD / 0.01 %.
    """
    # Сценарії — синхрон із web та mobile (lumenEconomics).
    scenarios = [
        {"key": "native",      "label": "Як є"},
        {"key": "residential", "label": "Житло",       "rental_share": 0.60, "opex_rate": 0.10},
        {"key": "commercial",  "label": "Комерція",    "rental_share": 0.75, "opex_rate": 0.15},
        {"key": "logistics",   "label": "Логістика",   "rental_share": 0.80, "opex_rate": 0.10},
        {"key": "land",        "label": "Земля",       "rental_share": 0.05, "opex_rate": 0.03},
        {"key": "development", "label": "Девелопмент", "rental_share": 0.10, "opex_rate": 0.05},
    ]

    # «Золоті» тестові кейси — навмисно охоплюють крайні значення:
    # звичайний житловий, чиста земля, девелопмент, край за тікетом.
    golden_inputs = [
        {"ticket": 100_000, "horizon_months": 48, "gross_yield_percent": 13.4,
         "rental_share": 0.55, "opex_rate": 0.12, "tax_rate": 0.195, "platform_fee": 0.02},
        {"ticket": 1_000_000, "horizon_months": 24, "gross_yield_percent": 18.5,
         "rental_share": 0.05, "opex_rate": 0.03, "tax_rate": 0.195, "platform_fee": 0.02},
        {"ticket": 50_000, "horizon_months": 36, "gross_yield_percent": 15.0,
         "rental_share": 0.10, "opex_rate": 0.05, "tax_rate": 0.195, "platform_fee": 0.025},
        {"ticket": 1, "horizon_months": 12, "gross_yield_percent": 12.0,
         "rental_share": 0.55, "opex_rate": 0.12, "tax_rate": 0.195, "platform_fee": 0.02},
    ]

    golden = []
    for inp in golden_inputs:
        e = _compute_economics_from_inputs(inp)
        golden.append({
            "input": inp,
            "expected": {
                "net_irr_percent": e["totals"]["net_irr_percent"],
                "total_net":       e["totals"]["total_net"],
                "annual_rental_net": e["annual"]["rental_net"],
                "appreciation_net": e["exit"]["appreciation_net"],
            },
        })

    return {
        "version": ECONOMICS_VERSION,
        "defaults": _ECONOMICS_DEFAULTS,
        "scenarios": scenarios,
        "golden_samples": golden,
        "tolerance": {"currency_uah": 1, "percent": 0.01},
        "formula": {
            "annual_rental_gross": "ticket * gross_yield * rental_share",
            "annual_opex":         "annual_rental_gross * opex_rate",
            "annual_after_opex":   "annual_rental_gross - annual_opex",
            "annual_tax":          "annual_after_opex * tax_rate",
            "annual_platform_fee": "annual_after_opex * platform_fee",
            "annual_net":          "annual_after_opex - annual_tax - annual_platform_fee",
            "appreciation_total":  "ticket * gross_yield * (1 - rental_share) * horizon_years",
            "exit_tax":            "appreciation_total * tax_rate",
            "appreciation_net":    "appreciation_total - exit_tax",
            "total_net":           "annual_net * horizon_years + appreciation_net",
            "net_irr":             "((ticket + total_net) / ticket) ** (1 / horizon_years) - 1",
        },
    }


def _compute_economics_from_inputs(p: dict) -> dict:
    """Чиста функція, ідентична за формулою з asset_economics().
    Виокремлено саме для /economics/spec golden samples, щоб не дублювати код."""
    ticket = max(float(p.get("ticket", 0) or 0), 1.0)
    horizon_months = int(p.get("horizon_months", 60))
    horizon_y = max(1, round(horizon_months / 12))
    gross_yield = float(p.get("gross_yield_percent", 12)) / 100.0
    rental_share = max(0.0, min(1.0, float(p.get("rental_share", 0.55))))
    appreciation_share = max(0.0, 1.0 - rental_share)
    opex_rate    = max(0.0, min(1.0, float(p.get("opex_rate", 0.12))))
    tax_rate     = max(0.0, min(1.0, float(p.get("tax_rate", 0.195))))
    platform_fee = max(0.0, min(1.0, float(p.get("platform_fee", 0.02))))

    annual_rental_gross = ticket * gross_yield * rental_share
    annual_opex = annual_rental_gross * opex_rate
    annual_after_opex = annual_rental_gross - annual_opex
    annual_tax = annual_after_opex * tax_rate
    annual_platform = annual_after_opex * platform_fee
    annual_net = annual_after_opex - annual_tax - annual_platform

    appreciation_total = ticket * gross_yield * appreciation_share * horizon_y
    exit_tax = appreciation_total * tax_rate
    appreciation_net = appreciation_total - exit_tax
    total_net = annual_net * horizon_y + appreciation_net
    net_irr = (((ticket + total_net) / ticket) ** (1.0 / horizon_y)) - 1.0 if ticket > 0 else 0.0

    return {
        "annual":  {"rental_net": round(annual_net)},
        "exit":    {"appreciation_net": round(appreciation_net)},
        "totals":  {
            "total_net": round(total_net),
            "net_irr_percent": round(net_irr * 100, 2),
        },
    }


@router.get("/assets/{asset_id}/economics")
async def asset_economics(asset_id: str, ticket: float | None = None):
    """Серверний розрахунок повної економіки активу для введеної суми.

    Повертає однакову структуру для web та mobile, щоб не дублювати формули
    клієнтсько-серверно. Усі частки (`rental_share`, `opex_rate`, `tax_rate`,
    `platform_fee`) беруться з документа активу або з категорії-дефолтів.
    """
    a = await db.lumen_assets.find_one({"id": asset_id})
    if not a:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    aa = _category_with_labels(a)

    ticket = float(max(ticket or aa.get("min_ticket") or 100000.0, 1.0))
    horizon_months = int(aa.get("horizon_months") or 60)
    horizon_y = max(1, round(horizon_months / 12))
    gross_yield = float(aa.get("target_yield") or 12.0) / 100.0
    rental_share = float(aa.get("rental_share") or 0.55)
    appreciation_share = max(0.0, 1.0 - rental_share)
    opex_rate = float(aa.get("opex_rate") or 0.12)
    tax_rate = float(aa.get("tax_rate") or 0.195)
    platform_fee = float(aa.get("platform_fee") or 0.02)

    annual_rental_gross = ticket * gross_yield * rental_share
    annual_opex = annual_rental_gross * opex_rate
    annual_rental_net = annual_rental_gross - annual_opex
    annual_tax = annual_rental_net * tax_rate
    annual_platform = annual_rental_net * platform_fee
    annual_net = annual_rental_net - annual_tax - annual_platform

    appreciation_total = ticket * gross_yield * appreciation_share * horizon_y
    exit_tax = appreciation_total * tax_rate
    total_net = annual_net * horizon_y + appreciation_total - exit_tax
    if ticket > 0:
        net_irr = (((ticket + total_net) / ticket) ** (1.0 / horizon_y)) - 1.0
    else:
        net_irr = 0.0

    cashflow = []
    for y in range(1, horizon_y + 1):
        exit_part = (appreciation_total - exit_tax) if y == horizon_y else 0.0
        cashflow.append({
            "year": y,
            "rental_net": round(annual_net),
            "exit": round(exit_part),
            "total": round(annual_net + exit_part),
        })

    return {
        "ticket": round(ticket),
        "horizon_years": horizon_y,
        "horizon_months": horizon_months,
        "shares": {
            "rental": round(rental_share, 4),
            "appreciation": round(appreciation_share, 4),
        },
        "rates": {
            "gross_yield": round(gross_yield, 4),
            "opex_rate": round(opex_rate, 4),
            "tax_rate": round(tax_rate, 4),
            "platform_fee": round(platform_fee, 4),
        },
        "annual": {
            "rental_gross": round(annual_rental_gross),
            "opex": round(annual_opex),
            "tax": round(annual_tax),
            "platform_fee": round(annual_platform),
            "rental_net": round(annual_net),
        },
        "exit": {
            "appreciation_total": round(appreciation_total),
            "exit_tax": round(exit_tax),
            "appreciation_net": round(appreciation_total - exit_tax),
        },
        "totals": {
            "total_net": round(total_net),
            "net_irr_percent": round(net_irr * 100, 2),
            "gross_yield_percent": round(gross_yield * 100, 2),
        },
        "cashflow": cashflow,
        "spv": {
            "label": aa.get("spv_label") or "ТОВ Lumen-SPV",
            "category": aa.get("category_label") or aa.get("category"),
            "location": aa.get("location"),
        },
    }


# ---- Investor cabinet -------------------------------------------------------

@router.get("/investor/portfolio")
async def investor_portfolio(user=Depends(get_current_user)):
    """Portfolio Engine (Sprint 2).

    Assembled from the REAL domain registry — ownerships + investments +
    assets — not from seeded display fields. Response shape stays compatible
    with the web investor dashboard.
    """
    uid = user["id"]

    # 1. Ownership registry — source of truth for "who owns what"
    ownerships: dict[str, dict] = {}
    async for own in db.lumen_ownerships.find({"investor_id": uid}):
        ownerships[own["asset_id"]] = _strip_mongo(dict(own))

    # 2. Active investments joined with live asset data
    invs_cur = db.lumen_investments.find({"investor_id": uid}).sort("invested_at", -1)
    investments = []
    total = 0.0
    weighted_yield_num = 0.0
    asset_cache: dict[str, dict] = {}
    async for it in invs_cur:
        it = _strip_mongo(dict(it))
        asset_id = it.get("asset_id")
        if asset_id and asset_id not in asset_cache:
            asset_cache[asset_id] = await db.lumen_assets.find_one({"id": asset_id}) or {}
        asset = asset_cache.get(asset_id, {})
        amount = float(it.get("amount") or it.get("invested_amount") or 0)
        a_yield = float(asset.get("target_yield") or it.get("current_yield") or 0)
        own = ownerships.get(asset_id) or {}
        # live enrichment from the assets registry (no stale denormalised data)
        it["asset_title"] = asset.get("title") or it.get("asset_title")
        it["asset_location"] = asset.get("location") or it.get("asset_location")
        it["current_yield"] = a_yield
        it["invested_amount"] = amount            # legacy key for web
        it["amount"] = amount
        it["share_percent"] = float(own.get("ownership_percent")
                                    or it.get("ownership_percent")
                                    or it.get("share_percent") or 0)
        it["units"] = float(own.get("units") or it.get("units") or amount)
        if it.get("status") == "active":
            total += amount
            weighted_yield_num += amount * a_yield
        investments.append(it)

    active = [i for i in investments if i.get("status") == "active"]
    avg_yield = round(weighted_yield_num / total, 2) if total else 0.0

    # 3. YTD paid (payout engine arrives in Sprint 7; until then the ledger
    #    only contains historical paid records)
    start_year = datetime(_now().year, 1, 1, tzinfo=timezone.utc)
    ytd = 0.0
    async for p in db.lumen_payouts.find({
        "investor_id": uid, "direction": "in", "status": "paid",
        "created_at": {"$gte": start_year},
    }):
        ytd += float(p.get("amount") or 0)

    # upcoming
    upcoming = []
    cur = db.lumen_payouts.find({
        "investor_id": uid, "status": {"$in": ["scheduled", "pending"]}, "direction": "in",
    }).sort("scheduled_at", 1).limit(5)
    async for p in cur:
        upcoming.append(_payout_with_labels(p))

    return {
        "summary": {
            "total_value": round(total + ytd, 0),
            "change_label": f"+{round(ytd / total * 100, 1)}% за рік" if total else None,
            "average_yield": avg_yield,
            "active_count": len(active),
            "paid_this_year": ytd,
        },
        "investments": investments,
        "ownerships": list(ownerships.values()),
        "upcoming_payouts": upcoming,
    }


@router.get("/investor/investments")
async def investor_investments(user=Depends(get_current_user)):
    items = []
    async for it in db.lumen_investments.find({"investor_id": user["id"]}).sort("invested_at", -1):
        items.append(_strip_mongo(it))
    return {"items": items, "total": len(items)}


@router.get("/investor/payouts")
async def investor_payouts(user=Depends(get_current_user)):
    items = []
    cur = db.lumen_payouts.find({"investor_id": user["id"]}).sort("created_at", -1)
    async for p in cur:
        items.append(_payout_with_labels(p))
    return {"items": items, "total": len(items)}


@router.get("/investor/documents")
async def investor_documents(user=Depends(get_current_user)):
    items = []
    async for d in db.lumen_documents.find({"investor_id": user["id"]}).sort("created_at", -1):
        d = _strip_mongo(d)
        d["kind_label"] = {"contract": "договір", "act": "акт", "report": "звіт"}.get(d.get("kind"), d.get("kind"))
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/investor/notifications")
async def investor_notifications(user=Depends(get_current_user)):
    items = []
    async for n in db.lumen_notifications.find({"investor_id": user["id"]}).sort("created_at", -1).limit(50):
        items.append(_strip_mongo(n))
    return {"items": items, "total": len(items)}


@router.post("/investor/notifications/read-all")
async def investor_read_all(user=Depends(get_current_user)):
    await db.lumen_notifications.update_many({"investor_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


class IntentPayload(BaseModel):
    asset_id: str
    amount: float = Field(gt=0)


@router.post("/investor/intent")
async def investor_intent(payload: IntentPayload, user=Depends(get_current_user)):
    """Legacy alias — delegates to the Sprint 2 Investor Intent Engine so all
    intents land in the canonical `lumen_investor_intents` registry."""
    from lumen_investment_core import create_intent
    intent = await create_intent(user, payload.asset_id, payload.amount)
    return {"id": intent["id"], "status": intent["status"]}


# ---- Admin ------------------------------------------------------------------

@router.get("/admin/overview")
async def admin_overview(_=Depends(require_admin)):
    investors_count = await db.users.count_documents({"role": {"$in": ["client", "investor"]}})
    assets_count = await db.lumen_assets.count_documents({})
    active_rounds = await db.lumen_assets.count_documents({"status": "open"})
    # total raised across assets
    total_raised = 0.0
    async for a in db.lumen_assets.find({}, {"raised": 1}):
        total_raised += float(a.get("raised") or 0)
    # recent investors
    recent = []
    async for u in db.users.find({"role": {"$in": ["client", "investor"]}}).sort("created_at", -1).limit(8):
        recent.append({
            "id": u.get("user_id") or u.get("id"),
            "name": u.get("name"),
            "email": u.get("email"),
            "kyc_status": u.get("kyc_status") or "not_started",
        })
    # active rounds list
    rounds = []
    async for a in db.lumen_assets.find({"status": "open"}).sort("created_at", -1).limit(6):
        rounds.append({
            "id": a.get("id"),
            "asset_title": a.get("title"),
            "progress_percent": _category_with_labels(a).get("progress_percent"),
        })
    return {
        "kpi": {
            "investors_count": investors_count,
            "assets_count": assets_count,
            "active_rounds": active_rounds,
            "total_raised": total_raised,
        },
        "recent_investors": recent,
        "active_rounds": rounds,
    }


@router.get("/admin/investors")
async def admin_investors(_=Depends(require_admin)):
    items = []
    cur = db.users.find({"role": {"$in": ["client", "investor"]}}).sort("created_at", -1)
    async for u in cur:
        items.append({
            "id": u.get("user_id") or u.get("id"),
            "name": u.get("name"),
            "email": u.get("email"),
            "role": u.get("role"),
            "kyc_status": u.get("kyc_status") or "not_started",
            "created_at": _iso(u.get("created_at")),
        })
    return {"items": items, "total": len(items)}


class AssetPayload(BaseModel):
    title: str
    category: str
    location: str | None = ""
    description: str | None = ""
    cover_url: str | None = ""
    status: str = "draft"
    target_yield: float = 0
    horizon_months: int = 12
    min_ticket: float = 0
    round_target: float = 0
    round_deadline: str | None = None
    spv_label: str | None = None
    featured: bool = False


@router.get("/admin/assets")
async def admin_assets(_=Depends(require_admin)):
    items = []
    async for a in db.lumen_assets.find().sort("created_at", -1):
        items.append(_category_with_labels(a))
    return {"items": items, "total": len(items)}


@router.post("/admin/assets")
async def admin_create_asset(payload: AssetPayload, request: Request,
                             admin=Depends(require_admin)):
    doc = payload.model_dump()
    doc["id"] = f"asset-{secrets.token_hex(5)}"
    doc["raised"] = 0
    doc["investors_count"] = 0
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    await db.lumen_assets.insert_one(doc)
    try:
        from lumen_audit import write_audit
        await write_audit(
            action="asset.create", category="asset",
            target_type="lumen_assets", target_id=doc["id"],
            actor=admin, request=request,
            summary=f"Asset created: {doc.get('title')}",
            meta={"category": doc.get("category"), "status": doc.get("status")},
        )
    except Exception:
        pass
    return _category_with_labels(doc)


@router.patch("/admin/assets/{asset_id}")
async def admin_update_asset(asset_id: str, payload: AssetPayload, request: Request,
                             admin=Depends(require_admin)):
    upd = payload.model_dump()
    upd["updated_at"] = _now()
    before = await db.lumen_assets.find_one({"id": asset_id})
    res = await db.lumen_assets.update_one({"id": asset_id}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    a = await db.lumen_assets.find_one({"id": asset_id})
    try:
        from lumen_audit import write_audit
        # build minimal diff (changed fields only)
        diff = {}
        for k, v in upd.items():
            if k in ("updated_at",):
                continue
            old = (before or {}).get(k)
            if old != v:
                diff[k] = {"before": old, "after": v}
        await write_audit(
            action="asset.update", category="asset",
            target_type="lumen_assets", target_id=asset_id,
            actor=admin, request=request,
            summary=f"Asset updated: {a.get('title')}",
            diff=diff,
        )
    except Exception:
        pass
    return _category_with_labels(a)


@router.delete("/admin/assets/{asset_id}")
async def admin_delete_asset(asset_id: str, request: Request,
                             admin=Depends(require_admin)):
    before = await db.lumen_assets.find_one({"id": asset_id}, {"title": 1})
    res = await db.lumen_assets.delete_one({"id": asset_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Об'єкт не знайдено")
    try:
        from lumen_audit import write_audit
        await write_audit(
            action="asset.delete", category="asset",
            target_type="lumen_assets", target_id=asset_id,
            actor=admin, request=request,
            summary=f"Asset deleted: {(before or {}).get('title') or asset_id}",
        )
    except Exception:
        pass
    return {"ok": True}


@router.get("/admin/rounds")
async def admin_rounds(_=Depends(require_admin)):
    """Rounds registry (Sprint 2) — reads from lumen_investment_rounds with a
    fallback to asset-level data for assets without a round document."""
    items = []
    seen_assets: set[str] = set()
    async for r in db.lumen_investment_rounds.find().sort("created_at", -1):
        asset = await db.lumen_assets.find_one({"id": r.get("asset_id")}) or {}
        seen_assets.add(r.get("asset_id"))
        items.append({
            "id": r.get("id"),
            "asset_id": r.get("asset_id"),
            "asset_title": asset.get("title"),
            "round_name": r.get("round_name") or f"Раунд {r.get('round_number', 1)}",
            "status": r.get("status"),
            "raised": r.get("raised_amount") or 0,
            "target": r.get("target_amount") or 0,
            "minimum_ticket": r.get("minimum_ticket") or 0,
            "deadline": _iso(r.get("close_at")),
        })
    # legacy fallback for assets not yet covered by the rounds registry
    async for a in db.lumen_assets.find({"id": {"$nin": list(seen_assets)}}).sort("created_at", -1):
        items.append({
            "id": a.get("id"),
            "asset_id": a.get("id"),
            "asset_title": a.get("title"),
            "round_name": "Раунд I",
            "status": a.get("status"),
            "raised": a.get("raised") or 0,
            "target": a.get("round_target") or 0,
            "minimum_ticket": a.get("min_ticket") or 0,
            "deadline": _iso(a.get("round_deadline")),
        })
    return {"items": items, "total": len(items)}


@router.get("/admin/payments")
async def admin_payments(_=Depends(require_admin)):
    items = []
    user_cache: dict[str, dict] = {}
    cur = db.lumen_payouts.find().sort("created_at", -1).limit(200)
    async for p in cur:
        p = _payout_with_labels(p)
        uid = p.get("investor_id")
        if uid and uid not in user_cache:
            u = await db.users.find_one({"user_id": uid}) or await db.users.find_one({"id": uid}) or {}
            user_cache[uid] = u
        u = user_cache.get(uid, {}) if uid else {}
        p["investor_name"] = u.get("name")
        p["investor_email"] = u.get("email")
        items.append(p)
    return {"items": items, "total": len(items)}


@router.get("/admin/documents")
async def admin_documents(_=Depends(require_admin)):
    items = []
    user_cache: dict[str, dict] = {}
    async for d in db.lumen_documents.find().sort("created_at", -1):
        d = _strip_mongo(d)
        uid = d.get("investor_id")
        if uid and uid not in user_cache:
            u = await db.users.find_one({"user_id": uid}) or await db.users.find_one({"id": uid}) or {}
            user_cache[uid] = u
        u = user_cache.get(uid, {}) if uid else {}
        d["investor_name"] = u.get("name")
        d["investor_email"] = u.get("email")
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/admin/reports")
async def admin_reports(_=Depends(require_admin)):
    investors_count = await db.users.count_documents({"role": {"$in": ["client", "investor"]}})
    assets_count = await db.lumen_assets.count_documents({})
    total_raised = 0.0
    by_cat: dict[str, float] = {}
    yields = []
    async for a in db.lumen_assets.find():
        amt = float(a.get("raised") or 0)
        total_raised += amt
        by_cat[a.get("category", "other")] = by_cat.get(a.get("category", "other"), 0) + amt
        if a.get("target_yield"):
            yields.append(float(a["target_yield"]))
    avg_yield = round(sum(yields) / len(yields), 1) if yields else 0
    by_category = []
    for cat, amt in by_cat.items():
        share = (amt / total_raised) if total_raised else 0
        by_category.append({
            "category": cat,
            "label": CATEGORY_LABELS.get(cat, cat),
            "amount": amt,
            "share": share,
        })
    return {
        "kpi": {
            "total_raised": total_raised,
            "investors_count": investors_count,
            "assets_count": assets_count,
            "average_yield": avg_yield,
        },
        "by_category": by_category,
    }


@router.get("/admin/legal-settings")
async def admin_legal_settings(_=Depends(require_admin)):
    doc = await db.legal_settings.find_one({}) or {}
    return {
        "company_name": doc.get("company_name") or "Lumen Capital Ukraine",
        "address": doc.get("address") or "м. Київ, Україна",
        "contact_email": doc.get("contact_email") or "hello@lumen.com.ua",
    }
