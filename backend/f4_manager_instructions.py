"""
LUMEN — F4 Manager Instructions (operational documentation)
===========================================================

The single place that answers "how do we operate":
  • how to lead an investor          (onboarding)
  • how to run KYC                    (kyc)
  • how to handle objections          (objections)
  • how to prepare documents          (documents)
  • how to hand off a lead            (handoff)

Distinct from `ops_sop.py` (fixed-key, admin-only compliance SOPs). F4 is the
team-facing manual: admins author rich-text (markdown) instructions, managers
READ them, every edit is versioned, and managers ACKNOWLEDGE the current
version — so an admin can see who has / hasn't read each procedure.

Collections:
  lumen_manager_instructions          — current doc (title, category, body, status, version)
  lumen_manager_instruction_versions  — full edit history (one row per version)
  lumen_manager_instruction_acks      — per (instruction, version, user) acknowledgement

A new version invalidates prior acks (managers must re-acknowledge) — this is
what keeps "everyone read the latest objection-handling script" true.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from lumen_api import db, require_admin, require_staff, _strip_mongo

logger = logging.getLogger("lumen.manager_instructions")

router = APIRouter(prefix="/api", tags=["lumen-manager-instructions"])

DOCS = "lumen_manager_instructions"
VERSIONS = "lumen_manager_instruction_versions"
ACKS = "lumen_manager_instruction_acks"

STAFF_ROLES = {"admin", "manager", "operator", "team_lead", "owner", "master_admin"}

CATEGORIES = [
    {"key": "onboarding", "uk": "Як вести інвестора", "en": "Leading an investor"},
    {"key": "kyc", "uk": "KYC та верифікація", "en": "KYC & verification"},
    {"key": "objections", "uk": "Робота з запереченнями", "en": "Handling objections"},
    {"key": "documents", "uk": "Оформлення документів", "en": "Document preparation"},
    {"key": "handoff", "uk": "Передача лідів", "en": "Lead handoff"},
    {"key": "general", "uk": "Загальне", "en": "General"},
]
CATEGORY_KEYS = {c["key"] for c in CATEGORIES}

ST_DRAFT = "draft"
ST_PUBLISHED = "published"
ST_ARCHIVED = "archived"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(u: dict) -> Optional[str]:
    return u.get("user_id") or u.get("id")


def _name(u: dict) -> Optional[str]:
    return u.get("name") or u.get("full_name") or u.get("email")


def _is_admin(u: dict) -> bool:
    role = (u.get("role") or "").lower()
    roles = {str(r).lower() for r in (u.get("roles") or [])}
    return role in {"admin", "owner", "master_admin"} or bool(
        {"admin", "owner", "master_admin"} & roles)


# ===========================================================================
# Models
# ===========================================================================
class InstructionIn(BaseModel):
    title: str
    category: str = "general"
    body: str = ""
    tags: List[str] = Field(default_factory=list)
    pinned: bool = False
    status: str = ST_DRAFT


class InstructionUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[List[str]] = None
    pinned: Optional[bool] = None
    change_note: Optional[str] = None


class AckIn(BaseModel):
    version: Optional[int] = None


# ===========================================================================
# Helpers
# ===========================================================================
async def _snapshot_version(doc: dict, editor: dict, note: Optional[str]):
    await db[VERSIONS].insert_one({
        "version_id": f"iv_{uuid.uuid4().hex[:12]}",
        "instruction_id": doc["instruction_id"],
        "version": doc["version"],
        "title": doc["title"],
        "category": doc["category"],
        "body": doc["body"],
        "edited_by": _uid(editor),
        "edited_by_name": _name(editor),
        "change_note": (note or "").strip()[:300] or None,
        "at": _now(),
    })


async def _ack_count(instruction_id: str, version: int) -> int:
    return await db[ACKS].count_documents(
        {"instruction_id": instruction_id, "version": version})


async def _has_acked(instruction_id: str, version: int, user_id: str) -> bool:
    if not user_id:
        return False
    return bool(await db[ACKS].find_one(
        {"instruction_id": instruction_id, "version": version, "user_id": user_id}))


async def _active_manager_count() -> int:
    try:
        n = await db.users.count_documents(
            {"$or": [{"role": {"$in": ["manager", "admin", "team_lead"]}},
                     {"roles": {"$in": ["manager", "admin", "team_lead"]}}]})
        return max(n, 1)
    except Exception:
        return 1


# ===========================================================================
# Read (managers + admin)
# ===========================================================================
@router.get("/manager/instructions/categories")
async def categories(_staff=Depends(require_staff)):
    counts: Dict[str, int] = {}
    async for d in db[DOCS].find({"status": ST_PUBLISHED}, {"category": 1}):
        c = d.get("category") or "general"
        counts[c] = counts.get(c, 0) + 1
    return {"categories": [{**c, "count": counts.get(c["key"], 0)} for c in CATEGORIES]}


@router.get("/manager/instructions")
async def list_instructions(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    user=Depends(require_staff),
):
    admin = _is_admin(user)
    query: Dict[str, Any] = {}
    if admin:
        if status:
            query["status"] = status
    else:
        query["status"] = ST_PUBLISHED  # managers see only published
    if category:
        query["category"] = category
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"body": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    uid = _uid(user)
    rows = []
    async for d in db[DOCS].find(query).sort([("pinned", -1), ("updated_at", -1)]):
        d = _strip_mongo(d)
        acked = await _has_acked(d["instruction_id"], d.get("version", 1), uid)
        item = {
            "instruction_id": d["instruction_id"],
            "title": d["title"],
            "category": d["category"],
            "tags": d.get("tags", []),
            "pinned": d.get("pinned", False),
            "status": d.get("status"),
            "version": d.get("version", 1),
            "updated_at": d.get("updated_at"),
            "updated_by_name": d.get("updated_by_name"),
            "acknowledged": acked,
        }
        if admin:
            item["ack_count"] = await _ack_count(d["instruction_id"], d.get("version", 1))
        rows.append(item)
    # pending acks for this user (published, not yet acknowledged current version)
    pending = sum(1 for r in rows if r["status"] == ST_PUBLISHED and not r["acknowledged"])
    return {"instructions": rows, "count": len(rows), "pending_acks": pending}


@router.get("/manager/instructions/{instruction_id}")
async def get_instruction(instruction_id: str, user=Depends(require_staff)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    d = _strip_mongo(d)
    if not _is_admin(user) and d.get("status") != ST_PUBLISHED:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    uid = _uid(user)
    d["acknowledged"] = await _has_acked(instruction_id, d.get("version", 1), uid)
    d["ack_count"] = await _ack_count(instruction_id, d.get("version", 1))
    return d


@router.post("/manager/instructions/{instruction_id}/ack")
async def acknowledge(instruction_id: str, body: AckIn, user=Depends(require_staff)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    if d.get("status") != ST_PUBLISHED:
        raise HTTPException(status_code=409, detail="Можна підтвердити лише опубліковану інструкцію")
    version = d.get("version", 1)
    uid = _uid(user)
    existing = await db[ACKS].find_one(
        {"instruction_id": instruction_id, "version": version, "user_id": uid})
    if not existing:
        await db[ACKS].insert_one({
            "ack_id": f"ack_{uuid.uuid4().hex[:12]}",
            "instruction_id": instruction_id,
            "version": version,
            "user_id": uid,
            "name": _name(user),
            "at": _now(),
        })
    return {"ok": True, "instruction_id": instruction_id, "version": version,
            "ack_count": await _ack_count(instruction_id, version)}


# ===========================================================================
# Authoring (admin)
# ===========================================================================
@router.post("/admin/manager/instructions")
async def create_instruction(body: InstructionIn, admin=Depends(require_admin)):
    cat = body.category if body.category in CATEGORY_KEYS else "general"
    status = body.status if body.status in (ST_DRAFT, ST_PUBLISHED) else ST_DRAFT
    doc = {
        "instruction_id": f"mi_{uuid.uuid4().hex[:12]}",
        "title": body.title.strip()[:200] or "Без назви",
        "category": cat,
        "body": body.body or "",
        "tags": [t.strip()[:40] for t in (body.tags or []) if t.strip()][:12],
        "pinned": bool(body.pinned),
        "status": status,
        "version": 1,
        "created_at": _now(),
        "created_by": _uid(admin),
        "created_by_name": _name(admin),
        "updated_at": _now(),
        "updated_by": _uid(admin),
        "updated_by_name": _name(admin),
        "published_at": _now() if status == ST_PUBLISHED else None,
    }
    await db[DOCS].insert_one(doc)
    await _snapshot_version(doc, admin, "Створено")
    return _strip_mongo(await db[DOCS].find_one({"instruction_id": doc["instruction_id"]}))


@router.put("/admin/manager/instructions/{instruction_id}")
async def update_instruction(instruction_id: str, body: InstructionUpdate, admin=Depends(require_admin)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    # Determine if content materially changed → bump version + reset acks
    content_changed = False
    patch: Dict[str, Any] = {"updated_at": _now(), "updated_by": _uid(admin),
                             "updated_by_name": _name(admin)}
    if body.title is not None and body.title.strip() != d.get("title"):
        patch["title"] = body.title.strip()[:200]; content_changed = True
    if body.category is not None and body.category in CATEGORY_KEYS and body.category != d.get("category"):
        patch["category"] = body.category
    if body.body is not None and body.body != d.get("body"):
        patch["body"] = body.body; content_changed = True
    if body.tags is not None:
        patch["tags"] = [t.strip()[:40] for t in body.tags if t.strip()][:12]
    if body.pinned is not None:
        patch["pinned"] = bool(body.pinned)

    if content_changed:
        new_version = d.get("version", 1) + 1
        patch["version"] = new_version
        # snapshot the NEW state as the new version
        snap = {**d, **patch, "version": new_version}
        await _snapshot_version(snap, admin, body.change_note)
        # new version invalidates prior acks implicitly (acks are version-scoped)
    await db[DOCS].update_one({"instruction_id": instruction_id}, {"$set": patch})
    return _strip_mongo(await db[DOCS].find_one({"instruction_id": instruction_id}))


@router.post("/admin/manager/instructions/{instruction_id}/publish")
async def publish_instruction(instruction_id: str, admin=Depends(require_admin)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    new_status = ST_DRAFT if d.get("status") == ST_PUBLISHED else ST_PUBLISHED
    patch = {"status": new_status, "updated_at": _now(),
             "updated_by": _uid(admin), "updated_by_name": _name(admin)}
    if new_status == ST_PUBLISHED:
        patch["published_at"] = _now()
    await db[DOCS].update_one({"instruction_id": instruction_id}, {"$set": patch})
    return {"ok": True, "status": new_status}


@router.post("/admin/manager/instructions/{instruction_id}/archive")
async def archive_instruction(instruction_id: str, admin=Depends(require_admin)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    await db[DOCS].update_one({"instruction_id": instruction_id},
                              {"$set": {"status": ST_ARCHIVED, "updated_at": _now()}})
    return {"ok": True, "status": ST_ARCHIVED}


@router.get("/admin/manager/instructions/{instruction_id}/versions")
async def instruction_versions(instruction_id: str, _admin=Depends(require_admin)):
    rows = []
    async for v in db[VERSIONS].find({"instruction_id": instruction_id}).sort("version", -1):
        rows.append(_strip_mongo(v))
    return {"versions": rows, "count": len(rows)}


@router.get("/admin/manager/instructions/{instruction_id}/acks")
async def instruction_acks(instruction_id: str, _admin=Depends(require_admin)):
    d = await db[DOCS].find_one({"instruction_id": instruction_id})
    if not d:
        raise HTTPException(status_code=404, detail="Інструкцію не знайдено")
    version = d.get("version", 1)
    acked = []
    acked_ids = set()
    async for a in db[ACKS].find({"instruction_id": instruction_id, "version": version}).sort("at", -1):
        a = _strip_mongo(a)
        acked.append({"user_id": a.get("user_id"), "name": a.get("name"), "at": a.get("at")})
        acked_ids.add(a.get("user_id"))
    # who hasn't acknowledged (managers/admins)
    pending = []
    async for u in db.users.find(
        {"$or": [{"role": {"$in": ["manager", "admin", "team_lead"]}},
                 {"roles": {"$in": ["manager", "admin", "team_lead"]}}]},
        {"user_id": 1, "name": 1, "email": 1}):
        if u.get("user_id") not in acked_ids:
            pending.append({"user_id": u.get("user_id"), "name": u.get("name") or u.get("email")})
    return {"version": version, "acknowledged": acked, "pending": pending,
            "ack_count": len(acked), "pending_count": len(pending)}


@router.get("/admin/manager/instructions-overview")
async def overview(_admin=Depends(require_admin)):
    total = await db[DOCS].count_documents({})
    published = await db[DOCS].count_documents({"status": ST_PUBLISHED})
    drafts = await db[DOCS].count_documents({"status": ST_DRAFT})
    managers = await _active_manager_count()
    # coverage: avg ack ratio over published docs
    ratios = []
    by_cat: Dict[str, int] = {}
    async for d in db[DOCS].find({"status": ST_PUBLISHED}, {"instruction_id": 1, "version": 1, "category": 1}):
        c = await _ack_count(d["instruction_id"], d.get("version", 1))
        ratios.append(min(c / managers, 1.0))
        cat = d.get("category") or "general"
        by_cat[cat] = by_cat.get(cat, 0) + 1
    coverage = round(sum(ratios) / len(ratios), 3) if ratios else 0.0
    return {"total": total, "published": published, "drafts": drafts,
            "active_managers": managers, "avg_ack_coverage": coverage,
            "by_category": by_cat}


# ===========================================================================
# Seed starter instructions + indexes
# ===========================================================================
_SEED: List[dict] = [
    {"key": "seed_onboarding", "category": "onboarding", "title": "Як вести інвестора: від ліда до активного",
     "body": """# Як вести інвестора

## 1. Перший контакт
- Відповідай на новий лід протягом **SLA** (див. картку ліда).
- Зафіксуй джерело та first-touch у CRM.

## 2. Кваліфікація
- Уточни мету інвестування, горизонт, суму.
- Признач зустріч (meeting) у картці ліда.

## 3. Супровід
- Веди всі комунікації через Communication Log (дзвінок / email / Telegram).
- Після кожної взаємодії онови нотатки та наступний крок.

## 4. Просування воронкою
Lead → Meeting → KYC → Accreditation → Contract → Funding → Certificate.
Не пропускай етапи — Timeline та Attribution залежать від коректних статусів.
"""},
    {"key": "seed_kyc", "category": "kyc", "title": "Процедура KYC для менеджера",
     "body": """# KYC для менеджера

1. Попроси інвестора завантажити документ, що посвідчує особу, та селфі.
2. Перевір повноту анкети перед поданням на комплаєнс.
3. Поясни строки: стандарт **1–2 робочі дні**.
4. Не приймай рішення про підтвердження — це робить комплаєнс.
5. Тримай інвестора в курсі статусу; фіксуй комунікації.
"""},
    {"key": "seed_objections", "category": "objections", "title": "Робота з типовими запереченнями",
     "body": """# Робота з запереченнями

**«Дорого / висока сума входу»** — поясни модель співволодіння та поріг входу.

**«Ризиковано»** — покажи структуру SPV, юридичний захист, сертифікат власності.

**«Подумаю»** — узгодь конкретний наступний крок і дату повторного контакту.

**«Не довіряю онлайн»** — запропонуй зустріч, покажи публічний договір і реєстр.
"""},
    {"key": "seed_documents", "category": "documents", "title": "Оформлення документів та договорів",
     "body": """# Оформлення документів

1. Переконайся, що KYC та accreditation завершені до генерації договору.
2. Надішли інвестору посилання на публічний перегляд договору (view token).
3. Підпис фіксується в системі; не приймай підпис поза платформою.
4. Після підписання — переходь до етапу Funding.
"""},
    {"key": "seed_handoff", "category": "handoff", "title": "Передача лідів між менеджерами",
     "body": """# Передача лідів

- Передавай лід лише через **Reassignment** — це пише Assignment History.
- Вкажи причину передачі.
- Передай контекст у нотатках: на якому етапі, домовленості, наступний крок.
- Новий власник підтверджує прийняття та продовжує супровід.
"""},
]


async def seed_instructions(actor_name="System"):
    for s in _SEED:
        existing = await db[DOCS].find_one({"seed_key": s["key"]})
        if existing:
            continue
        doc = {
            "instruction_id": f"mi_{uuid.uuid4().hex[:12]}",
            "seed_key": s["key"],
            "title": s["title"],
            "category": s["category"],
            "body": s["body"],
            "tags": [],
            "pinned": s["category"] == "onboarding",
            "status": ST_PUBLISHED,
            "version": 1,
            "created_at": _now(),
            "created_by_name": actor_name,
            "updated_at": _now(),
            "updated_by_name": actor_name,
            "published_at": _now(),
        }
        await db[DOCS].insert_one(doc)
        await db[VERSIONS].insert_one({
            "version_id": f"iv_{uuid.uuid4().hex[:12]}",
            "instruction_id": doc["instruction_id"], "version": 1,
            "title": doc["title"], "category": doc["category"], "body": doc["body"],
            "edited_by_name": actor_name, "change_note": "Створено (seed)", "at": _now(),
        })
    logger.info("F4 manager instructions seeded")


async def ensure_indexes(database=None):
    d = database if database is not None else db
    try:
        await d[DOCS].create_index("instruction_id", unique=True)
        await d[DOCS].create_index([("status", 1), ("category", 1)])
        await d[VERSIONS].create_index([("instruction_id", 1), ("version", -1)])
        await d[ACKS].create_index([("instruction_id", 1), ("version", 1), ("user_id", 1)], unique=True)
        logger.info("F4 manager-instructions indexes ensured")
    except Exception as e:
        logger.warning("F4 ensure_indexes warn: %s", e)
    await seed_instructions()
