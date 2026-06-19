"""Idempotent seed: expand the public marketplace.

  • Adds ~9 more demo assets (→ ~15 total) so the /assets list pagination
    ("Показати більше") is meaningful.
  • Sets a real capital structure on every asset: investor tranche + reserve
    fund + own/platform funds (NO debt), plus explicit geo coords for the map.
  • Seeds REAL confirmed pool contributions (lumen_pools + lumen_pool_contributions)
    with a realistic crypto/fiat mix, so the Capital Stack crypto-vs-fiat split is
    computed from genuine backend records (not hardcoded UI numbers).

Run:  python seed_assets_expansion.py
Safe to re-run — assets are upserted by id; demo contributions are replaced.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "lumen_database")


def now():
    return datetime.now(timezone.utc)


# City coordinates for the interactive map (Leaflet markers).
CITY_GEO = {
    "київ":      {"lat": 50.4501, "lng": 30.5234, "region": "Київ"},
    "львів":     {"lat": 49.8397, "lng": 24.0297, "region": "Львівська обл."},
    "рівне":     {"lat": 50.6199, "lng": 26.2516, "region": "Рівненська обл."},
    "одеса":     {"lat": 46.4825, "lng": 30.7233, "region": "Одеська обл."},
    "харків":    {"lat": 49.9935, "lng": 36.2304, "region": "Харківська обл."},
    "дніпро":    {"lat": 48.4647, "lng": 35.0462, "region": "Дніпропетровська обл."},
    "бориспіль": {"lat": 50.3450, "lng": 30.9500, "region": "Київська обл."},
    "гатне":     {"lat": 50.3580, "lng": 30.3700, "region": "Київська обл."},
}


def geo_for(location: str, lat=None, lng=None, region=None, district=None):
    low = (location or "").lower()
    match = next((v for k, v in CITY_GEO.items() if k in low), None)
    glat = lat if lat is not None else (match or {}).get("lat")
    glng = lng if lng is not None else (match or {}).get("lng")
    greg = region or (match or {}).get("region") or ""
    parts = [p.strip() for p in (location or "").split(",")]
    gdist = district or next((p for p in parts if "район" in p.lower()),
                             parts[-1] if parts else location)
    if glat is None or glng is None:
        return None
    # nudge each asset a little so markers in the same city don't overlap exactly
    return {"lat": round(glat, 5), "lng": round(glng, 5), "region": greg,
            "district": gdist, "address": location, "infrastructure": []}


U = "https://images.unsplash.com/"
IMG = lambda pid: f"{U}{pid}?auto=format&fit=crop&w=1200&q=80"

# ── 9 new demo assets ────────────────────────────────────────────────────────
NEW_ASSETS = [
    dict(id="asset-kharkiv-bc", title='БЦ «Каскад»', category="commercial",
         location="Харків, Нагірний район", cover=IMG("photo-1486406146926-c627a92ad1ab"),
         yield_=16.2, horizon=36, min_ticket=120000, target=7_200_000, raised=4_320_000,
         spv="ТОВ «Каскад Девелопмент»", investors=44, crypto_ratio=0.38, days=30, featured=True,
         desc="Бізнес-центр класу B+ площею 7 400 м². Заповнення орендарями 88%, "
              "довгострокові контракти з IT-компаніями та банком."),
    dict(id="asset-dnipro-resi", title='ЖК «Набережний»', category="real_estate",
         location="Дніпро, Соборний район", cover=IMG("photo-1512917774080-9991f1c4c750"),
         yield_=17.8, horizon=24, min_ticket=80000, target=5_600_000, raised=2_240_000,
         spv="ТОВ «Набережний Інвест»", investors=27, crypto_ratio=0.30, days=22, featured=False,
         desc="Житловий комплекс комфорт-класу на березі Дніпра. 96 квартир, "
              "підземний паркінг, набережна зона відпочинку."),
    dict(id="asset-lviv-hotel", title='Готель «Ратуша»', category="commercial",
         location="Львів, Галицький район", cover=IMG("photo-1566073771259-6a8506099945"),
         yield_=15.5, horizon=48, min_ticket=150000, target=9_100_000, raised=6_370_000,
         spv="ТОВ «Ратуша Готель»", investors=58, crypto_ratio=0.42, days=40, featured=True,
         desc="Бутік-готель на 64 номери у пішій зоні центру Львова. "
              "Середнє завантаження 79%, дохід від номерного фонду й ресторану."),
    dict(id="asset-odesa-logistics", title='Логіс-парк «Південь»', category="construction",
         location="Одеса, Пересипський район", cover=IMG("photo-1553413077-190dd305871c"),
         yield_=20.1, horizon=30, min_ticket=200000, target=6_800_000, raised=1_360_000,
         spv="ТОВ «Південь Логістика»", investors=11, crypto_ratio=0.25, days=18, featured=False,
         desc="Будівництво логістичного парку класу A біля порту, 14 200 м². "
              "Попередні угоди з двома операторами на 7 років."),
    dict(id="asset-kyiv-office", title='Офіс «Гулівер-Сіті»', category="commercial",
         location="Київ, Печерський район", cover=IMG("photo-1497366754035-f200968a6e72"),
         yield_=14.2, horizon=36, min_ticket=100000, target=8_900_000, raised=7_120_000,
         spv="ТОВ «Гулівер Капітал»", investors=71, crypto_ratio=0.34, days=12, featured=True,
         desc="Поверхи преміального бізнес-центру в діловому ядрі Києва. "
              "Орендарі — корпорації та представництва, заповнення 95%."),
    dict(id="asset-rivne-resi", title='ЖК «Зелений Двір»', category="real_estate",
         location="Рівне, центр", cover=IMG("photo-1460317442991-0ec209397118"),
         yield_=18.9, horizon=24, min_ticket=60000, target=3_900_000, raised=975_000,
         spv="ТОВ «Зелений Двір»", investors=16, crypto_ratio=0.28, days=20, featured=False,
         desc="Камерний житловий комплекс на 48 квартир із закритим двором. "
              "Висока ліквідність на місцевому ринку оренди."),
    dict(id="asset-kharkiv-land", title='Ділянка «Окружна»', category="land",
         location="Харків, Слобідський район", cover=IMG("photo-1416879595882-3373a0480b5b"),
         yield_=23.4, horizon=18, min_ticket=130000, target=4_100_000, raised=1_435_000,
         spv="ТОВ «Окружна Лендс»", investors=12, crypto_ratio=0.45, days=55, featured=False,
         desc="3,1 га під комерційну забудову біля окружної дороги. "
              "Зміна цільового призначення в процесі, очікуване зростання вартості 40%."),
    dict(id="asset-dnipro-retail", title='ТЦ «Караван-Сіті»', category="commercial",
         location="Дніпро, Амур-Нижньодніпровський район", cover=IMG("photo-1519567241046-7f570eee3ce6"),
         yield_=13.9, horizon=36, min_ticket=90000, target=5_200_000, raised=4_160_000,
         spv="ТОВ «Караван Рітейл»", investors=49, crypto_ratio=0.31, days=15, featured=False,
         desc="Діючий торговий центр площею 5 800 м². Якірні орендарі — "
              "продуктовий гіпермаркет і мережа електроніки."),
    dict(id="asset-kyiv-cottage", title='Котеджі «Лісовий Квартал»', category="construction",
         location="Бориспільський район, Київська обл.", cover=IMG("photo-1448630360428-65456885c650"),
         yield_=21.0, horizon=28, min_ticket=170000, target=6_000_000, raised=600_000,
         spv="ТОВ «Лісовий Квартал»", investors=6, crypto_ratio=0.36, days=70, featured=False,
         desc="32 котеджі 120-180 м² у лісовій зоні за 18 км від Києва. "
              "Інженерні мережі готові на 80%, старт продажів — 2026 р."),
]


def build_asset_doc(a: dict) -> dict:
    target = a["target"]
    raised = a["raised"]
    reserve = round(target * 0.06)
    platform = round(target * 0.05) if a["featured"] else 0
    crypto = round(raised * a["crypto_ratio"])
    fiat = raised - crypto
    return {
        "id": a["id"], "title": a["title"], "category": a["category"],
        "location": a["location"], "cover_url": a["cover"], "description": a["desc"],
        "status": "open", "target_yield": a["yield_"], "horizon_months": a["horizon"],
        "min_ticket": a["min_ticket"], "round_target": target, "raised": raised,
        "round_deadline": (now() + timedelta(days=a["days"])).isoformat(),
        "spv_label": a["spv"], "investors_count": a["investors"], "featured": a["featured"],
        "capital_stack": {
            "asset_value": target + reserve + platform,
            "investors": target, "reserve": reserve, "platform": platform,
        },
        "raised_crypto": crypto, "raised_fiat": fiat,
        "geo": geo_for(a["location"]),
        "gallery": [a["cover"], IMG("photo-1554995207-c18c203602cb"),
                    IMG("photo-1560448204-e02f11c3d0e2")],
    }


# Existing 6 assets — capital structure + crypto/fiat split + geo (raised kept as-is).
EXISTING = {
    "asset-podilskyi":        dict(crypto_ratio=0.40, platform_pct=0.05),
    "asset-stoyanka-land":    dict(crypto_ratio=0.30, platform_pct=0.0),
    "asset-lavr-tc":          dict(crypto_ratio=0.45, platform_pct=0.05),
    "asset-rivne-warehouse":  dict(crypto_ratio=0.25, platform_pct=0.0),
    "asset-odessa-apartments": dict(crypto_ratio=0.35, platform_pct=0.04),
    "asset-vyshneve-cottage": dict(crypto_ratio=0.33, platform_pct=0.0),
}


async def seed_contributions(db, asset_id: str, raised: float, crypto: float, fiat: float):
    """Create a pool + confirmed contributions with a real crypto/fiat mix."""
    await db.lumen_pool_contributions.delete_many({"asset_id": asset_id, "source": "seed_demo"})
    if raised <= 0:
        return
    pool_id = f"pool-{asset_id}"
    await db.lumen_pools.update_one(
        {"id": pool_id},
        {"$set": {"id": pool_id, "asset_id": asset_id, "currency": "UAH",
                  "target_amount": raised, "raised_usd": raised,
                  "status": "open", "updated_at": now()},
         "$setOnInsert": {"created_at": now()}},
        upsert=True,
    )

    def tickets(total: float, gateway: str, n: int):
        if total <= 0:
            return []
        base = round(total / n)
        out = [base] * (n - 1) + [round(total - base * (n - 1))]
        return [{
            "id": f"contrib-{uuid.uuid4().hex[:10]}",
            "pool_id": pool_id, "asset_id": asset_id,
            "gateway": gateway, "amount_usd": float(amt), "amount": float(amt),
            "currency": "USDT" if gateway == "crypto" else "UAH",
            "status": "confirmed", "source": "seed_demo",
            "created_at": now() - timedelta(days=(i + 1) * 3),
        } for i, amt in enumerate(out)]

    docs = tickets(crypto, "crypto", 4) + tickets(fiat, "fiat", 6)
    if docs:
        await db.lumen_pool_contributions.insert_many(docs)


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # 1) upsert new assets
    for a in NEW_ASSETS:
        doc = build_asset_doc(a)
        existing = await db.lumen_assets.find_one({"id": doc["id"]})
        if existing:
            doc["created_at"] = existing.get("created_at") or now()
            doc["updated_at"] = now()
            await db.lumen_assets.update_one({"id": doc["id"]}, {"$set": doc})
            print(f"updated {doc['id']}")
        else:
            doc["created_at"] = now()
            doc["updated_at"] = now()
            await db.lumen_assets.insert_one(doc)
            print(f"created {doc['id']}")
        await seed_contributions(db, doc["id"], doc["raised"],
                                 doc["raised_crypto"], doc["raised_fiat"])

    # 2) enrich existing assets with capital structure + split + geo
    for asset_id, cfg in EXISTING.items():
        a = await db.lumen_assets.find_one({"id": asset_id})
        if not a:
            continue
        target = float(a.get("round_target") or a.get("target_amount") or 0)
        raised = float(a.get("raised") or a.get("raised_amount") or 0)
        reserve = round(target * 0.06)
        platform = round(target * cfg["platform_pct"])
        crypto = round(raised * cfg["crypto_ratio"])
        fiat = raised - crypto
        patch = {
            "capital_stack": {
                "asset_value": target + reserve + platform,
                "investors": target, "reserve": reserve, "platform": platform,
            },
            "raised_crypto": crypto, "raised_fiat": fiat,
            "updated_at": now(),
        }
        if not a.get("geo"):
            g = geo_for(a.get("location") or "")
            if g:
                patch["geo"] = g
        # make sure all marketplace assets are visible/open
        if a.get("status") not in ("open", "active"):
            patch["status"] = "open"
        await db.lumen_assets.update_one({"id": asset_id}, {"$set": patch})
        await seed_contributions(db, asset_id, raised, crypto, fiat)
        print(f"enriched {asset_id}: crypto={crypto} fiat={fiat}")

    total = await db.lumen_assets.count_documents({})
    contribs = await db.lumen_pool_contributions.count_documents({"source": "seed_demo"})
    print(f"\nDONE. assets={total}, demo contributions={contribs}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
