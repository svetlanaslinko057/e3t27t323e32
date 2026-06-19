"""
ops_sop.py — Operations Standard Operating Procedures (SOP) for Lumen.

Real internal compliance/operations documents that a compliance or operations
employee can follow day-to-day — not developer markdown. Stored in MongoDB
(collection ``lumen_ops_sop``) so the compliance lead can edit & version them
from the admin panel (/admin/sop).

Five SOPs:
  • kyc_review          — KYC Review SOP
  • funding_verification — Funding / Payment Verification SOP
  • withdrawal          — Withdrawal SOP
  • payout              — Payout SOP
  • secondary_dispute   — Secondary Market Dispute SOP

Each SOP doc shape:
  { key, title, category, owner, sla, version, updated_at, auto_seeded, body }

Body uses the same markdown-lite the frontend renders (#, ##, ###, **bold**,
- / 1. lists, > callouts).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SOP_VERSION = 1
COLLECTION = "lumen_ops_sop"

# Ordered list of SOP keys (drives /admin/sop ordering).
SOP_KEYS = ["kyc_review", "funding_verification", "withdrawal", "payout", "secondary_dispute",
            "funding_failure", "withdrawal_failure", "reconciliation_failure",
            "kyc_escalation", "sanctions_hit", "payout_incident"]

_EFFECTIVE = "Чинний з 1 січня 2026 року · Внутрішній документ Lumen Operations"

SOP_SEED: Dict[str, Dict[str, Any]] = {
    # ───────────────────────── KYC REVIEW ─────────────────────────
    "kyc_review": {
        "title": "KYC Review SOP",
        "category": "Комплаєнс",
        "owner": "Compliance Officer",
        "sla": "1–2 робочі дні",
        "body": f"""# KYC Review SOP — Перевірка верифікації клієнта

{_EFFECTIVE}

## 1. Мета
Забезпечити належну ідентифікацію та верифікацію кожного інвестора перед
активацією інвестицій, відповідно до Політики KYC та Політики AML.

## 2. Сфера застосування
Усі заявки зі статусом **«Подано на перевірку» (submitted)** та повторні
перевірки (re-KYC). Виконавець — працівник комплаєнс.

## 3. Ролі та відповідальність
- **Compliance Officer** — приймає рішення «Підтвердити / Відхилити».
- **Senior Compliance** — ескалація складних кейсів, PEP, EDD.
- **Operations** — комунікація з клієнтом щодо доукомплектування анкети.

## 4. SLA
- Стандартна перевірка: **1–2 робочі дні** з моменту подання.
- EDD / PEP: до **5 робочих днів**.

## 5. Покрокова процедура
1. Відкрити чергу заявок у розділі **Admin → KYC** (фільтр: «На перевірці»).
2. Звірити дані анкети: ПІБ, дата народження, громадянство, РНОКПП.
3. Перевірити документ, що посвідчує особу: строк дії, читабельність,
   відповідність ПІБ.
4. Звірити селфі з фото документа (liveness, відсутність ознак підробки).
5. Перевірити інвестора за **санкційними переліками** (РНБО, ЄС, OFAC, ООН) та
   статусом **PEP**. За збігом — ескалація до Senior Compliance (EDD).
6. Оцінити ризик-рівень (низький / середній / високий) за Політикою AML.
7. Прийняти рішення:
   - **Підтвердити** — натиснути «Підтвердити» → статус `approved`.
   - **Відхилити** — обрати причину, додати коментар → статус `rejected`.
8. Зафіксувати рішення; система записує час, виконавця та підставу в audit log.

## 6. Критерії відхилення
- Недостовірні або суперечливі дані.
- Прострочений / нечитабельний документ.
- Невідповідність селфі та документа.
- Збіг із санкційним переліком.
- Відмова надати джерело походження коштів (для EDD).

## 7. Ескалація
Кейси PEP, високого ризику, нетипові юрисдикції — передавати Senior Compliance з
поміткою «EDD» до прийняття рішення.

## 8. Записи та зберігання
Усі рішення та документи зберігаються щонайменше **5 років** після завершення
відносин. Доступ — рольовий, журналюється.

## 9. Контроль якості
Щомісячний вибірковий перегляд 10% підтверджених заявок керівником комплаєнс.
""",
    },

    # ───────────────────────── FUNDING VERIFICATION ─────────────────────────
    "funding_verification": {
        "title": "Funding Verification SOP",
        "category": "Фінанси",
        "owner": "Finance / Treasury",
        "sla": "1 робочий день",
        "body": f"""# Funding Verification SOP — Підтвердження надходження коштів

{_EFFECTIVE}

## 1. Мета
Достовірно підтверджувати оплату внесків інвесторів перед формуванням частки
(ownership) та проведенням запису в реєстрі (ledger).

## 2. Сфера застосування
Платіжні заявки (payment requests) зі статусом **`paid`** (інвестор завантажив
підтвердження) та **`under_review`** (взято в роботу).

## 3. Ролі
- **Finance Officer** — звірка та рішення «Підтвердити / Відхилити».
- **Treasury** — звірка з банківською випискою.
- **Operations** — запит уточнень у інвестора (clarification).

## 4. SLA
**1 робочий день** з моменту подання інвестором підтвердження.

## 5. Передумови
- KYC інвестора — **approved**.
- Договір участі — **підписаний**.
- Платіжна заявка має призначення платежу та реквізити SPV.

## 6. Покрокова процедура
1. Відкрити **Admin → Платежі**, фільтр «На перевірці».
2. Відкрити заявку, перевірити вкладене підтвердження (PDF/JPG/PNG).
3. Звірити: суму, валюту, призначення платежу, реквізити одержувача (SPV),
   ПІБ платника = інвестор.
4. Звірити надходження з **банківською випискою** (Admin → Банк-транзакції).
5. Прийняти рішення:
   - **Підтвердити** → статус `confirmed`: система формує ownership, оновлює
     raised_amount активу та створює ledger-запис `credit / investment_funding`.
   - **Уточнення** → статус `under_review`: додати коментар, що саме потрібно.
   - **Відхилити** → статус `rejected`: зазначити причину (резерв не формується).
6. Переконатися, що сума ledger дорівнює сумі підтвердженого платежу (контроль Σ).

## 7. Контроль цілісності
- Жоден рух коштів не проводиться поза реєстром (ledger = джерело істини).
- Подвійне підтвердження однієї заявки заблоковано (ідемпотентність → 409).

## 8. Червоні прапорці (ескалація до комплаєнс)
- Платник ≠ інвестор (оплата третьою особою).
- Невідповідність суми / валюти / призначення.
- Розбивка великого внеску на дрібні платежі.

## 9. Записи
Підтвердження та рішення зберігаються; усі дії журналюються в audit log.
""",
    },

    # ───────────────────────── WITHDRAWAL ─────────────────────────
    "withdrawal": {
        "title": "Withdrawal SOP",
        "category": "Фінанси",
        "owner": "Finance / Treasury",
        "sla": "1–3 робочі дні",
        "body": f"""# Withdrawal SOP — Опрацювання заявок на вивід коштів

{_EFFECTIVE}

## 1. Мета
Опрацьовувати заявки інвесторів на вивід коштів безпечно, з контролем балансу
та дотриманням AML, без розривів у реєстрі.

## 2. Сфера застосування
Заявки на вивід (withdrawal requests) у статусах **`requested` → `approved` →
`processing` → `paid`** (або `rejected`).

## 3. Ролі
- **Finance Officer** — перевірка та схвалення.
- **Treasury** — фактична виплата на реквізити.
- **Compliance** — перевірка AML для великих/нетипових сум.

## 4. SLA
**1–3 робочі дні** залежно від суми та банківських строків.

## 5. Передумови
- KYC — **approved**; реквізити для виплат (IBAN) збігаються з даними KYC.
- Доступний баланс гаманця ≥ сума виводу (резерв уже утримано системою при
  створенні заявки).

## 6. Покрокова процедура
1. Відкрити **Admin → Виводи**, фільтр «Створено» (requested).
2. Перевірити доступний баланс та коректність резерву.
3. Звірити IBAN/банк зі збереженими в KYC реквізитами.
4. Для сум вище порогового значення — узгодити з **Compliance** (AML).
5. **Схвалити** заявку → статус `approved`.
6. Передати в **Treasury**: провести банківський платіж → статус `processing`.
7. Після фактичного зарахування — позначити **`paid`**: система проводить
   ledger-запис `debit / withdrawal` (термінальний статус).
8. У разі відмови — **`rejected`**: резерв повертається на баланс, зазначити
   причину.

## 7. Контроль
- Сума debit у реєстрі = сума фактичної виплати.
- Заборонено виплату на реквізити, відмінні від KYC, без повторної верифікації.

## 8. Червоні прапорці
- Зміна реквізитів безпосередньо перед виводом.
- Швидкий цикл внесок → вивід без інвестиційної активності.
- Запит виводу на третю особу.

## 9. Записи
Усі статуси та підстави фіксуються в історії заявки та audit log.
""",
    },

    # ───────────────────────── PAYOUT ─────────────────────────
    "payout": {
        "title": "Payout SOP",
        "category": "Фінанси",
        "owner": "Finance / Operations",
        "sla": "За графіком активу",
        "body": f"""# Payout SOP — Нарахування та виплата доходу інвесторам

{_EFFECTIVE}

## 1. Мета
Коректно нараховувати та виплачувати дохід (оренда / переоцінка / дивіденд)
інвесторам пропорційно їхнім часткам, з утриманням податків.

## 2. Сфера застосування
Плани виплат (payout plans), нарахування (records) та пакети (batches) у статусах
**`generated` → `approved` → `credited`** (або `cancelled`).

## 3. Ролі
- **Operations** — формування плану та пакета нарахувань.
- **Finance Officer** — перевірка та схвалення пакета.
- **Treasury** — зарахування на гаманці інвесторів.

## 4. SLA
Згідно з графіком активу (щомісяця для рентних, за віхами/на виході для інших).

## 5. Покрокова процедура
1. Перевірити фактичні надходження по активу (оренда / результат виходу).
2. Сформувати/звірити **план виплат** (тип, частота, період, база розподілу).
3. Згенерувати **пакет нарахувань** (batch) — система рахує суми по кожному
   ownership пропорційно частці → статус `generated`.
4. Перевірити: Σ нарахувань = сумі до розподілу; утримання податків (ПДФО 18% +
   ВЗ 1,5%) розраховано коректно.
5. **Схвалити** пакет → статус `approved` (Admin → Виплати доходу).
6. **Провести** зарахування → статус `credited`: ledger-записи `credit / payout`
   на гаманці інвесторів.
7. За потреби сформувати **експорт виплат** для бухгалтерії / банку.

## 6. Контроль цілісності
- Жодна виплата поза реєстром; Σ credit = розподілена сума − утримані податки.
- Подвійне проведення пакета заблоковано переходами станів.

## 7. Скасування
До проведення (`generated`/`approved`) пакет можна **скасувати** (`cancelled`)
із зазначенням причини. Після `credited` — лише коригувальним записом.

## 8. Записи
План, пакет, нарахування та податкові утримання зберігаються для звітності й
аудиту.
""",
    },

    # ───────────────────────── SECONDARY DISPUTE ─────────────────────────
    "secondary_dispute": {
        "title": "Secondary Market Dispute SOP",
        "category": "Комплаєнс / Підтримка",
        "owner": "Support + Compliance",
        "sla": "До 5 робочих днів",
        "body": f"""# Secondary Market Dispute SOP — Вирішення спорів вторинного ринку

{_EFFECTIVE}

## 1. Мета
Справедливо та прозоро розглядати спори щодо угод вторинного ринку (лістинги,
оферти, розрахунки, передача часток) на підставі записів реєстру.

## 2. Сфера застосування
Звернення інвесторів щодо: неправильного обсягу/ціни, помилкової угоди, спірного
списання/зарахування, технічних збоїв під час розрахунку.

## 3. Ролі
- **Support** — приймає звернення, фіксує кейс, збирає докази.
- **Compliance** — ухвалює рішення по суті спору.
- **Finance** — виконує коригувальні ledger-записи за рішенням.

## 4. SLA
Первинна відповідь — **1 робочий день**; рішення — **до 5 робочих днів**.

## 5. Принцип істини
Єдине джерело істини — **реєстр (ledger)** та записи передачі часток
(share_transfer). Інваріант: загальна кількість одиниць по активу незмінна.

## 6. Покрокова процедура
1. Зареєструвати звернення: ID угоди/лістингу, суть претензії, скріншоти.
2. Підняти записи: trade, listing/bid, ledger-проведення (gross / fee / sale),
   рядки ownership продавця та покупця **до і після** угоди.
3. Перевірити інваріант загальної кількості одиниць та баланс Σ=0 по угоді.
4. Кваліфікувати кейс:
   - **Без помилки** — пояснити інвестору механіку угоди, закрити.
   - **Технічна помилка** — підготувати коригування.
5. Узгодити рішення з Compliance; за потреби — корекція через Finance
   (коригувальний ledger-запис, без порушення інваріанту).
6. Повідомити інвесторам результат із посиланням на записи реєстру.

## 7. Заборони
- Не змінювати завершені угоди «вручну» поза реєстром.
- Не проводити корекції без письмового рішення Compliance.

## 8. Ескалація
Спори з потенційними ознаками шахрайства / зловживання — негайно до Senior
Compliance та, за потреби, до відповідального з фінмоніторингу.

## 9. Записи
Кейс, докази, рішення та коригування зберігаються та журналюються (audit log).
""",
    },

    # ═══════════════ INCIDENT RUNBOOKS (production operations) ═══════════════
    "funding_failure": {
        "title": "Runbook · Funding Failure", "category": "Інциденти",
        "owner": "Finance Ops", "sla": "Реакція 30 хв · Резолюція 1 р.д.",
        "body": f"""# Runbook — Збій зарахування коштів (Funding Failure)

{_EFFECTIVE}

## Тригери
Платіж не підтверджено; webhook провайдера не дійшов / помилковий; статус
платежу `failed`/`reversed`; невідповідність суми; платіж без відповідного intent.

## Негайні дії (перші 30 хв)
1. Зафіксувати інцидент: payment_id, intent_id, інвестор, сума, провайдер, час.
2. Перевірити статус у провайдера (Stripe/банк) та в Admin → Платежі.
3. **НЕ** активувати ownership і **НЕ** проводити ledger-кредит, доки кошти не
   підтверджені реально (paid = підтверджений переказ, а не статус).

## Діагностика
- Звірити webhook-лог і `provider_ref` з банківською випискою.
- Перевірити idempotency: чи немає подвійного зарахування.
- Перевірити reconciliation-чергу на mismatch.

## Резолюція
- Кошти надійшли, але intent не закрито → ручне підтвердження + ledger-кредит.
- Кошти не надійшли → intent у `failed`, повідомити інвестора, без проводок.
- Дубль → сторно зайвого через коригувальний запис (Σ-інваріант не порушувати).

## Ескалація
> 1 р.д. або системний збій webhook → CTO + провайдер.

## Записи
Усі дії журналюються в audit log + AML, якщо стосується підозрілої операції.
""",
    },
    "withdrawal_failure": {
        "title": "Runbook · Withdrawal Failure", "category": "Інциденти",
        "owner": "Finance Ops", "sla": "Реакція 30 хв · Резолюція 1 р.д.",
        "body": f"""# Runbook — Збій виводу коштів (Withdrawal Failure)

{_EFFECTIVE}

## Тригери
Банк відхилив переказ; невірні реквізити (IBAN/BIC); експорт-файл не прийнято;
переказ завис між `approved` та `paid`; розбіжність у звірці.

## Негайні дії
1. Зафіксувати: withdrawal_id, інвестор, сума, статус, batch/export-файл.
2. Заморозити повторну виплату по цій заявці (ризик подвійного списання).
3. Перевірити, чи **не** виставлено статус `paid` без підтвердження банку.

## Діагностика
- Звірити export (CSV/SEPA/SWIFT) із підтвердженням банку.
- Перевірити mark-exported прапор (захист від подвійної виплати).
- Перевірити баланс гаманця та ledger-дебет.

## Резолюція
- Реквізити невірні → повернути в `approved`, запросити коректні, перевипуск.
- Банк відхилив → у `approved`, повторний експорт після виправлення.
- Кошти пішли, статус не оновлено → виставити `paid` після підтвердження.

## Заборони
`paid` ставиться ЛИШЕ після підтвердженого банківського переказу.

## Ескалація
Завис > 1 р.д. або ризик подвійної виплати → CFO + банк.
""",
    },
    "reconciliation_failure": {
        "title": "Runbook · Bank Reconciliation Failure", "category": "Інциденти",
        "owner": "Finance Ops", "sla": "Резолюція 2 р.д.",
        "body": f"""# Runbook — Збій банківської звірки (Reconciliation Failure)

{_EFFECTIVE}

## Тригери
Незведена транзакція; mismatch сум; частковий платіж; дубль; невідомий
відправник; розбіжність реєстр ↔ банк.

## Процедура
1. Відкрити mismatch-чергу (Admin → Bank Reconciliation).
2. Класифікувати: incoming / outgoing / partial / duplicate / unknown.
3. Зіставити `provider_ref` / призначення платежу з intent / withdrawal.
4. Для частковго платежу — або дозброїти до повної суми, або повернути різницю.
5. Для дубля — коригувальний запис (без порушення Σ=0).
6. Невідомий відправник → утримати кошти, запит KYC джерела, без активації.

## Контроль
Ledger = джерело істини. Будь-яке коригування — лише записом, ніколи «вручну».

## Ескалація
Розбіжність не закрита за 2 р.д. → CFO; підозра на AML → фінмоніторинг.
""",
    },
    "kyc_escalation": {
        "title": "Runbook · KYC Escalation", "category": "Інциденти",
        "owner": "Senior Compliance", "sla": "EDD до 5 р.д.",
        "body": f"""# Runbook — Ескалація KYC / EDD

{_EFFECTIVE}

## Тригери
PEP-збіг; висока/критична оцінка ризику; нетипова юрисдикція; сумнівні
документи; відмова надати джерело коштів (SoF).

## Процедура
1. Кейс із комплаєнс-черги передати Senior Compliance з поміткою «EDD».
2. Запросити додаткові документи: SoF/SoW, структура власності (UBO).
3. Повторний скринінг (санкції + PEP) + перевірка медіа/негативу.
4. Рішення: підтвердити з підвищеним моніторингом / відхилити / заблокувати.
5. Для критичного ризику — рішення двох осіб (4-eyes).

## Блокування
До рішення EDD — funding/withdrawal для інвестора заблоковані гейтом комплаєнсу.

## Записи
Рішення, підстава, докази — в audit log + AML (незмінний журнал).
""",
    },
    "sanctions_hit": {
        "title": "Runbook · Sanctions Hit", "category": "Інциденти",
        "owner": "Compliance Officer", "sla": "Негайно",
        "body": f"""# Runbook — Збіг із санкційним переліком (Sanctions Hit)

{_EFFECTIVE}

## Тригери
Підтверджений збіг (confirmed_match) проти OFAC/ЄС/UK/РНБО під час реєстрації,
KYC, зміни профілю або funding.

## Негайні дії
1. **Заблокувати** операції інвестора (гейт комплаєнсу → 403).
2. Зафіксувати кейс: суб'єкт, перелік, програма, score, тригер.
3. **НЕ** повідомляти суб'єкта про причину (заборона tipping-off).
4. Заморозити будь-які кошти/виплати по інвестору.

## Перевірка
1. Підтвердити, що це не хибне спрацювання (звірка ПІБ/ДН/країни).
2. Якщо хибне — рішенням Compliance «Очистити» (clear) з підставою.
3. Якщо справжнє — ескалація до відповідального з фінмоніторингу.

## Звітність
За підтвердженим збігом — підготувати повідомлення регулятору згідно з
вимогами фінмоніторингу у встановлені строки.

## Записи
Усе — в незмінний AML-журнал (хто/що/коли/чому).
""",
    },
    "payout_incident": {
        "title": "Runbook · Payout / Dividend Incident", "category": "Інциденти",
        "owner": "Finance Ops", "sla": "Резолюція 1 р.д.",
        "body": f"""# Runbook — Інцидент нарахування виплат (Payout Incident)

{_EFFECTIVE}

## Тригери
Помилка планувальника; дубль пакета за період; невірний розподіл часток;
помилка утримання податку (ПДФО/ВЗ); збій кредитування гаманців.

## Процедура
1. Зафіксувати: plan_id, batch_id, період, суми gross/tax/net.
2. Якщо пакет ще `generated`/`approved` — **скасувати** (cancel), виправити план.
3. Якщо вже `credited` — лише коригувальний ledger-запис (сторно), без видалення.
4. Перевірити дубль за період (планувальник ідемпотентний — дубль = аномалія).
5. Перевірити коректність утримання: gross − (ПДФО 18% + ВЗ 1.5%) = net; звірити
   рахунок податкового зобов'язання.
6. Перерахувати гаманці постраждалих інвесторів.

## Заборони
Нарахований пакет не редагується «вручну» — лише сторно/коригування записом.

## Ескалація
Системна помилка планувальника → CTO; податкова розбіжність → CFO.
""",
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _seed_doc(key: str) -> Dict[str, Any]:
    s = SOP_SEED[key]
    return {
        "key": key,
        "title": s["title"],
        "category": s["category"],
        "owner": s["owner"],
        "sla": s["sla"],
        "body": s["body"],
        "version": SOP_VERSION,
        "auto_seeded": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def ensure_sop_seed(db) -> Dict[str, Any]:
    """Idempotent seed/refresh. Admin-edited SOPs (auto_seeded=False) preserved."""
    await db[COLLECTION].create_index("key", unique=True)
    seeded = 0
    for key in SOP_KEYS:
        cur = await db[COLLECTION].find_one({"key": key}, {"_id": 0})
        if not cur:
            await db[COLLECTION].insert_one(_seed_doc(key))
            seeded += 1
        elif cur.get("auto_seeded") is not False and (cur.get("version") or 0) < SOP_VERSION:
            await db[COLLECTION].update_one({"key": key}, {"$set": _seed_doc(key)})
            seeded += 1
    return {"version": SOP_VERSION, "total": len(SOP_KEYS), "seeded_or_refreshed": seeded}


# ── Models ──────────────────────────────────────────────────────────────────

class SOPUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    owner: Optional[str] = None
    sla: Optional[str] = None
    body: Optional[str] = None


# ── Router factory ──────────────────────────────────────────────────────────

def build_sop_router(db, require_admin):
    router = APIRouter(prefix="/api/admin/sop", tags=["ops-sop"])

    def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
        d.pop("_id", None)
        return d

    @router.get("")
    async def list_sops(user=Depends(require_admin)):
        await ensure_sop_seed(db)
        order = {k: i for i, k in enumerate(SOP_KEYS)}
        items: List[Dict[str, Any]] = []
        async for d in db[COLLECTION].find({}, {"_id": 0}):
            items.append(d)
        items.sort(key=lambda x: order.get(x.get("key"), 999))
        # Lightweight list payload (no full body) + summary count.
        return {
            "items": [
                {
                    "key": x["key"], "title": x.get("title"), "category": x.get("category"),
                    "owner": x.get("owner"), "sla": x.get("sla"),
                    "version": x.get("version"), "updated_at": x.get("updated_at"),
                    "auto_seeded": x.get("auto_seeded", True),
                }
                for x in items
            ],
            "count": len(items),
        }

    @router.get("/{key}")
    async def get_sop(key: str, user=Depends(require_admin)):
        await ensure_sop_seed(db)
        d = await db[COLLECTION].find_one({"key": key}, {"_id": 0})
        if not d:
            raise HTTPException(404, detail={"code": "unknown_sop", "message": "SOP not found"})
        return _clean(d)

    @router.put("/{key}")
    async def update_sop(key: str, payload: SOPUpdate, user=Depends(require_admin)):
        cur = await db[COLLECTION].find_one({"key": key}, {"_id": 0})
        if not cur:
            raise HTTPException(404, detail={"code": "unknown_sop", "message": "SOP not found"})
        patch: Dict[str, Any] = {"auto_seeded": False, "updated_at": datetime.now(timezone.utc).isoformat()}
        for f in ("title", "category", "owner", "sla", "body"):
            v = getattr(payload, f)
            if v is not None:
                patch[f] = v
        await db[COLLECTION].update_one({"key": key}, {"$set": patch})
        d = await db[COLLECTION].find_one({"key": key}, {"_id": 0})
        return _clean(d)

    @router.post("/{key}/reset")
    async def reset_sop(key: str, user=Depends(require_admin)):
        if key not in SOP_SEED:
            raise HTTPException(404, detail={"code": "unknown_sop", "message": "SOP not found"})
        await db[COLLECTION].update_one({"key": key}, {"$set": _seed_doc(key)}, upsert=True)
        d = await db[COLLECTION].find_one({"key": key}, {"_id": 0})
        return _clean(d)

    return router
