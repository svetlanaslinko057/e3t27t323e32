"""
LUMEN — Asset Intelligence demo enrichment (idempotent)
========================================================

Gives the 6 seeded demo assets a real *operating history* so the Asset
Intelligence layer (Conviction/Liquidity score, snapshot, cash-flow, rounds,
"why we invested") presents each object as a PROVEN investment product rather
than an empty, low-confidence record.

For every asset it sets:
  * occupancy_percent, term_months, status
  * a fundraising rounds timeline (closed / open)
  * an operating cash-flow snapshot (invested / rent received / paid to
    investors / reserve), in UAH
  * 3–5 crisp "Чому ми інвестували" highlights
  * an investment thesis (opportunity / market / execution / exit) if missing
and seeds the supporting FACTS the deterministic scorer reads:
  * lumen_payout_records (credited dividends)  → payout consistency + yield history
  * lumen_asset_reports   (quarterly reports)  → transparency cadence

Idempotent (marker `intel_seeded`), skipped in production by the caller.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

logger = logging.getLogger("lumen.asset_intel.seed")

ASSETS = "lumen_assets"
REPORTS = "lumen_asset_reports"
PAYOUTS = "lumen_payout_records"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _nid(p: str) -> str:
    return f"{p}_{uuid4().hex[:12]}"


# Per-asset operating profile. Amounts are in UAH (₴) to match the asset detail
# page currency. `paid`/`total` = credited vs scheduled dividend periods.
_PROFILES = {
    "asset-podilskyi": {
        "occupancy": 93, "term": 24, "status": "open",
        "paid": 6, "total": 24,
        "cf": {"invested": 2_500_000, "rent": 612_000, "paid_out": 430_000, "reserve": 200_000},
        "rounds": [("I", "closed", 100), ("II", "closed", 100), ("III", "open", 52)],
        "highlights": [
            "Поділ — історичний центр Києва з дефіцитом нового житла бізнес-класу",
            "Орендна заповнюваність 93%, попит перевищує пропозицію в 2,3 раза",
            "Поруч нова станція метро та школа — драйвери зростання ціни",
            "Прогнозований ріст вартості об'єкта +18% за 24 місяці",
            "SPV вже оформлена, будинок зданий в експлуатацію",
        ],
    },
    "asset-lavr-tc": {
        "occupancy": 96, "term": 48, "status": "active",
        "paid": 12, "total": 12,
        "cf": {"invested": 3_800_000, "rent": 1_140_000, "paid_out": 920_000, "reserve": 260_000},
        "rounds": [("I", "closed", 100), ("II", "closed", 100)],
        "highlights": [
            "ТЦ у Шевченківському районі Львова з трафіком 1,2 млн відвідувачів/рік",
            "96% площ законтрактовано якірними орендарями на 3–5 років",
            "12 із 12 дивідендів виплачено без жодної затримки",
            "Довгострокові договори оренди з індексацією до інфляції",
        ],
    },
    "asset-rivne-warehouse": {
        "occupancy": 88, "term": 36, "status": "open",
        "paid": 5, "total": 36,
        "cf": {"invested": 1_900_000, "rent": 372_000, "paid_out": 280_000, "reserve": 150_000},
        "rounds": [("I", "closed", 100), ("II", "open", 64)],
        "highlights": [
            "Логістичний хаб на об'їзній трасі Рівного — вузол на коридорі ЄС",
            "Дефіцит класу-A складів у регіоні після релокації бізнесу із сходу",
            "Попередні договори оренди на 88% площ ще до завершення будівництва",
            "Прогнозована дохідність 19,2% річних на повному завантаженні",
        ],
    },
    "asset-stoyanka-land": {
        "occupancy": None, "term": 30, "status": "active",
        "paid": 3, "total": 6,
        "cf": {"invested": 4_100_000, "rent": 0, "paid_out": 520_000, "reserve": 300_000},
        "rounds": [("I", "closed", 100)],
        "highlights": [
            "Ділянка 2,4 га під забудову на трасі Київ–Чоп, 18 км від столиці",
            "Зміна цільового призначення під комерцію вже погоджена",
            "Земля поруч подорожчала на 40% за 2 роки через новий вузол",
            "Дохід формується від переоцінки, а не оренди — захист від простою",
        ],
    },
    "asset-odessa-apartments": {
        "occupancy": 95, "term": 60, "status": "active",
        "paid": 12, "total": 12,
        "cf": {"invested": 2_200_000, "rent": 528_000, "paid_out": 430_000, "reserve": 160_000},
        "rounds": [("I", "closed", 100), ("II", "closed", 100)],
        "highlights": [
            "Прибутковий будинок на Французькому бульварі — преміум-локація Одеси",
            "95% квартир в оренді, середній строк проживання орендаря 14 міс.",
            "12 із 12 дивідендів виплачено, стабільний грошовий потік",
            "Захищена курортна локація з попитом у будь-який сезон",
        ],
    },
    "asset-vyshneve-cottage": {
        "occupancy": 74, "term": 30, "status": "open",
        "paid": 2, "total": 30,
        "cf": {"invested": 1_500_000, "rent": 124_000, "paid_out": 86_000, "reserve": 120_000},
        "rounds": [("I", "closed", 100), ("II", "open", 38)],
        "highlights": [
            "Котеджне містечко на 26 будинків у с. Гатне, 12 км від Києва",
            "Готовність зовнішніх мереж 100%, попит на заміське житло зростає",
            "Прогнозований ріст ціни +21,5% на етапі добудови",
            "Покупці в черзі на 40% котеджів за попередніми договорами",
        ],
    },
}

_THESIS = {
    "asset-lavr-tc": {
        "opportunity": "Власник ТЦ продає частку для рефінансування боргу — дисконт 12% до ринкової оцінки об'єкта з підтвердженим грошовим потоком.",
        "market": "Орендні ставки на якісну торгову нерухомість у центрі Львова зросли на 11% за рік; вакантність у сегменті < 5%.",
        "execution": "Об'єкт працює, 96% площ законтрактовано на 3–5 років з індексацією. Керуюча компанія обслуговує ще 3 об'єкти Lumen.",
        "exit": "Базовий сценарій — продаж пакету REIT-фонду на 48-му місяці. Альтернатива — рефінансування і подовження володіння.",
    },
    "asset-rivne-warehouse": {
        "opportunity": "Девелопер залучає капітал на завершальний етап будівництва складу класу-A із вже підписаними попередніми договорами оренди.",
        "market": "Після релокації бізнесу на захід попит на сучасні склади в Рівному кратно перевищує пропозицію.",
        "execution": "88% площ законтрактовано до здачі. Підрядник із досвідом 11 років, фінансування етапів прив'язане до віх.",
        "exit": "Продаж логістичному оператору або institutional buyer після виходу на повне завантаження (36 міс.).",
    },
    "asset-stoyanka-land": {
        "opportunity": "Земельний банк на трасі Київ–Чоп із вже погодженою зміною цільового призначення під комерційну забудову.",
        "market": "Земля вздовж нового транспортного вузла подорожчала на 40% за два роки; девелопери активно скуповують ділянки.",
        "execution": "Документи оформлені, SPV володіє ділянкою без обтяжень. Дохід — від переоцінки та подальшого продажу.",
        "exit": "Продаж ділянки девелоперу на 30-му місяці або внесення в спільний проєкт забудови.",
    },
    "asset-odessa-apartments": {
        "opportunity": "Прибутковий будинок преміум-класу з повним заповненням і підтвердженою історією 12 виплат поспіль.",
        "market": "Французький бульвар — топ-локація Одеси; орендні ставки стабільні попри сезонність завдяки бізнес-попиту.",
        "execution": "95% квартир в оренді, професійне управління, низька ротація орендарів.",
        "exit": "Продаж об'єкта приватному інвестору або подовження володіння з реінвестуванням оренди.",
    },
    "asset-vyshneve-cottage": {
        "opportunity": "Котеджне містечко на етапі добудови з дисконтом до фінальної ціни та чергою попередніх покупців.",
        "market": "Попит на заміське житло біля Києва зростає; пропозиція якісних котеджних містечок обмежена.",
        "execution": "Зовнішні мережі готові на 100%, забудовник із досвідом, продажі стартували до завершення.",
        "exit": "Продаж готових котеджів кінцевим покупцям; вихід інвестора з фіксацією приросту ціни.",
    },
}


async def seed_asset_intelligence_demo(db) -> dict:
    enriched = 0
    for asset_id, p in _PROFILES.items():
        a = await db[ASSETS].find_one({"id": asset_id})
        if not a:
            continue
        if a.get("intel_seeded"):
            continue

        cf = p["cf"]
        rounds = [{"label": f"Раунд {lbl}", "status": st, "progress": pr}
                  for (lbl, st, pr) in p["rounds"]]
        update = {
            "intel_seeded": True,
            "term_months": p["term"],
            "status": p["status"],
            "dividends_paid_count": p["paid"],
            "dividends_total_count": p["total"],
            "operating_cashflow": {
                "invested": cf["invested"],
                "rent_received": cf["rent"],
                "paid_to_investors": cf["paid_out"],
                "reserve": cf["reserve"],
            },
            "rounds": rounds,
            "intel_highlights": p["highlights"],
        }
        if p["occupancy"] is not None:
            update["occupancy_percent"] = p["occupancy"]
        if asset_id in _THESIS and not (a.get("thesis") or {}).get("opportunity"):
            update["thesis"] = _THESIS[asset_id]

        await db[ASSETS].update_one({"id": asset_id}, {"$set": update})

        # ── Supporting FACTS for the deterministic scorer ──────────────────
        # quarterly reports (transparency cadence → 4 in last 12m)
        if await db[REPORTS].count_documents({"asset_id": asset_id, "intel_seed": True}) == 0:
            base = _now()
            for q in range(4):
                d = base - timedelta(days=90 * q + 5)
                await db[REPORTS].insert_one({
                    "id": _nid("rep"),
                    "asset_id": asset_id,
                    "intel_seed": True,
                    "period_label": f"Q{4 - q}",
                    "title": f"Квартальний звіт Q{4 - q}",
                    "summary": "Орендні надходження, завантаження та виплати — у межах плану.",
                    "created_at": d,
                })

        # credited dividend records (payout consistency + yield history)
        if p["paid"] > 0 and await db[PAYOUTS].count_documents({"asset_id": asset_id, "intel_seed": True}) == 0:
            per = round(cf["paid_out"] / p["paid"]) if p["paid"] else 0
            base = _now()
            for k in range(p["paid"]):
                d = base - timedelta(days=30 * (k + 1))
                await db[PAYOUTS].insert_one({
                    "id": _nid("pay"),
                    "asset_id": asset_id,
                    "intel_seed": True,
                    "status": "credited",
                    "amount_uah": per,
                    "paid_date": d,
                    "created_at": d,
                })
        enriched += 1

    logger.info("Asset Intelligence demo enrichment: %d assets", enriched)
    return {"enriched": enriched}
