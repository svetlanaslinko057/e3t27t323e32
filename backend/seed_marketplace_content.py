"""
Seed realistic Sprint-5 content + geo for the public Marketplace Depth cards.

Idempotent: only fills what is missing. This is DEMO content living in the real
collections (lumen_asset_updates / _reports / _documents / _questions) and an
asset `geo` block — admins can edit or replace it from the cabinet at any time.

Run:  python seed_marketplace_content.py
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


GEO = {
    "asset-podilskyi": {
        "lat": 50.4664, "lng": 30.5168, "region": "Київ", "district": "Подільський район",
        "infrastructure": ["Метро «Контрактова площа» — 400 м", "Набережна Дніпра",
                            "Бізнес-центри Подолу", "Київський фунікулер"],
    },
    "asset-stoyanka-land": {
        "lat": 50.3450, "lng": 30.9500, "region": "Київська обл.", "district": "Бориспільський район",
        "infrastructure": ["Аеропорт «Бориспіль» — 8 км", "Траса М-03 Київ–Харків",
                            "Логістичні термінали", "Під'їзні дороги з покриттям"],
    },
    "asset-lavr-tc": {
        "lat": 49.8525, "lng": 24.0300, "region": "Львівська обл.", "district": "Шевченківський район",
        "infrastructure": ["Історичний центр — 1.5 км", "Громадський транспорт",
                            "Школи та університети", "Щільна житлова забудова"],
    },
    "asset-rivne-warehouse": {
        "lat": 50.6199, "lng": 26.2200, "region": "Рівненська обл.", "district": "Об'їзна траса",
        "infrastructure": ["Траса М-06 Київ–Чоп", "Митний термінал",
                            "Залізнична гілка", "Промислова зона"],
    },
    "asset-odessa-apartments": {
        "lat": 46.4350, "lng": 30.7600, "region": "Одеська обл.", "district": "Приморський район",
        "infrastructure": ["Французький бульвар", "Море — 600 м",
                            "Парк Шевченка", "Центр міста — 10 хв"],
    },
    "asset-vyshneve-cottage": {
        "lat": 50.3580, "lng": 30.3700, "region": "Київська обл.", "district": "Києво-Святошинський район",
        "infrastructure": ["Об'їзна Києва — 3 км", "Лісопаркова зона",
                            "Школа та дитсадок", "Центральні комунікації"],
    },
}

PLANS = {
    "asset-podilskyi": [
        {"url": "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=80", "caption": "Планування типового поверху"},
        {"url": "https://images.unsplash.com/photo-1487958449943-2429e8be8625?auto=format&fit=crop&w=1200&q=80", "caption": "Схема забудови ділянки"},
    ],
    "asset-lavr-tc": [
        {"url": "https://images.unsplash.com/photo-1487958449943-2429e8be8625?auto=format&fit=crop&w=1200&q=80", "caption": "Планування торгових площ"},
    ],
    "asset-odessa-apartments": [
        {"url": "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=80", "caption": "Планування квартир"},
    ],
}


def updates_for(a: dict) -> list[dict]:
    t = a.get("title", "об'єкт")
    return [
        {"kind": "milestone", "title": "Завершено етап оцінки об'єкта",
         "body": f"Незалежний оцінювач підтвердив ринкову вартість «{t}». Готуємо документи раунду.",
         "days": 24, "pinned": True},
        {"kind": "milestone", "title": "Підписано договір управління активом",
         "body": "SPV уклала договір з керуючою компанією. Розпочато операційну фазу проєкту.",
         "days": 12, "pinned": False},
        {"kind": "news", "title": "Раунд інвестування активний",
         "body": "Інвестори вже долучаються до проєкту. Слідкуйте за заповненням раунду у картці.",
         "days": 3, "pinned": False},
    ]


def reports_for(a: dict) -> list[dict]:
    return [
        {"report_type": "quarterly", "period_label": "I квартал 2026",
         "title": "Квартальний звіт про стан об'єкта",
         "summary": "Операційні показники у межах плану. Заповнюваність та грошовий потік стабільні."},
        {"report_type": "annual", "period_label": "2025",
         "title": "Річний звіт SPV",
         "summary": "Підсумки року: дохідність відповідає цільовій, резерв на капремонт сформовано."},
    ]


def documents_for(a: dict) -> list[dict]:
    return [
        {"doc_type": "valuation", "title": "Звіт про незалежну оцінку", "visibility": "public"},
        {"doc_type": "lease_agreement", "title": "Витяг з договорів оренди", "visibility": "public"},
        {"doc_type": "financial_model", "title": "Фінансова модель проєкту", "visibility": "investors"},
    ]


def questions_for(a: dict) -> list[dict]:
    return [
        {"author": "Андрій К.", "question": "Як часто виплачується дохід інвесторам?",
         "answer": "Виплати здійснюються щоквартально на гаманець інвестора після закриття раунду."},
        {"author": "Olena M.", "question": "Що відбувається з моєю часткою при виході з проєкту?",
         "answer": "Частку можна продати на вторинному ринку Lumen іншому інвестору в будь-який момент."},
        {"author": "Ігор П.", "question": "Чи застрахований об'єкт?",
         "answer": "Так, об'єкт застраховано від основних майнових ризиків; поліс зберігається у SPV."},
    ]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    stats = {"geo": 0, "plans": 0, "updates": 0, "reports": 0, "documents": 0, "questions": 0}

    async for a in db.lumen_assets.find({}):
        aid = a["id"]

        # geo
        if not a.get("geo") and aid in GEO:
            await db.lumen_assets.update_one({"id": aid}, {"$set": {"geo": GEO[aid]}})
            stats["geo"] += 1

        # plans (floor plans extend the gallery section)
        if not a.get("plans") and aid in PLANS:
            await db.lumen_assets.update_one({"id": aid}, {"$set": {"plans": PLANS[aid]}})
            stats["plans"] += 1

        # updates
        if await db.lumen_asset_updates.count_documents({"asset_id": aid}) == 0:
            for u in updates_for(a):
                await db.lumen_asset_updates.insert_one({
                    "id": _id("upd"), "asset_id": aid, "kind": u["kind"],
                    "title": u["title"], "body": u["body"], "pinned": u["pinned"],
                    "published": True, "published_at": _ago(u["days"]), "created_at": _ago(u["days"]),
                })
                stats["updates"] += 1

        # reports
        if await db.lumen_asset_reports.count_documents({"asset_id": aid}) == 0:
            for i, r in enumerate(reports_for(a)):
                await db.lumen_asset_reports.insert_one({
                    "id": _id("rep"), "asset_id": aid, "report_type": r["report_type"],
                    "period_label": r["period_label"], "title": r["title"], "summary": r["summary"],
                    "storage_path": None, "filename": None, "size_bytes": 0,
                    "published": True, "created_at": _ago(30 + i * 30),
                })
                stats["reports"] += 1

        # documents
        if await db.lumen_asset_documents.count_documents({"asset_id": aid}) == 0:
            for d in documents_for(a):
                await db.lumen_asset_documents.insert_one({
                    "id": _id("doc"), "asset_id": aid, "doc_type": d["doc_type"],
                    "title": d["title"], "filename": f"{d['doc_type']}.pdf", "size_bytes": 0,
                    "visibility": d["visibility"], "storage_path": None, "created_at": _ago(20),
                })
                stats["documents"] += 1

        # questions (answered)
        if await db.lumen_asset_questions.count_documents({"asset_id": aid}) == 0:
            for i, q in enumerate(questions_for(a)):
                await db.lumen_asset_questions.insert_one({
                    "id": _id("qa"), "asset_id": aid, "investor_id": None,
                    "investor_name": q["author"], "question": q["question"], "answer": q["answer"],
                    "status": "answered", "answered_at": _ago(5 + i), "created_at": _ago(8 + i),
                })
                stats["questions"] += 1

    print("seed_marketplace_content done:", stats)


if __name__ == "__main__":
    asyncio.run(main())
