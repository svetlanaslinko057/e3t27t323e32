# LUMEN — Go-Live Execution Plan (Business Launch Roadmap)

> **Это не roadmap разработки. Это roadmap запуска бизнеса.**
> Код готов на ~97–99% (подтверждено: 20 контрактных харнесов зелёные, 130-item
> Launch Readiness = 54%, go_live_ready=false из-за **9 открытых блокеров**, которые
> почти все — owner / банк / юр-решения, а не программирование).
>
> Каждая фаза ниже привязана к конкретным пунктам живого чек-листа
> (`/admin/launch-readiness` → Launch Checklist v1.0). По мере закрытия — отмечайте
> пункты через override с доказательством; панель сама пересчитает go-live %.
>
> Источник истины по пунктам: `backend/launch_checklist_seed.py`.
> Связанный артефакт: `docs/PRODUCTION_LAUNCH_READINESS_v1.0.md`.

---

## Критический путь (одной строкой)

```
Юрлицо/SPV → KYB → Банковский счёт(IBAN) → Stripe Live + SEPA/SWIFT(inbound)
→ Withdrawal rail(outbound) → Юр-пакет подписан → Money-cycle dress rehearsal
→ Первый реальный инвестор → First Dividend → First Withdrawal → Bank confirmation
→ Операционный запуск (20–50 мелочей)
```

**Definition of Go-Live:** все 22 BLOCKER-пункта чек-листа зелёные (auto или override
с доказательством) **И** пройден один настоящий денежный цикл с банковским
подтверждением на обоих концах.

---

## Фаза 0 — Юридическое лицо и регуляторная позиция
**Владелец:** owner + юрист · **Тип:** не код · **Гейт:** структура оформлена и действительна

| Задача | Чек-лист ID | Доказательство |
|---|---|---|
| Юр-структура платформа + SPV оформлена | `legal_entity_structure` | выписка из реестра, устав SPV |
| Регуляторная позиция/лицензирование подтверждены юристом | `legal_regulatory_stance` 🛑 | юр-заключение |
| MLRO / комплаенс-офицер назначен | `cmp_mlro_assigned` | приказ/назначение |

**Почему первой:** без юрлица невозможны ни KYB, ни счёт, ни договоры. Это самый
длинный по срокам пункт — запускать параллельно со всем остальным.

---

## Фаза 1 — KYB и банковский счёт
**Владелец:** owner · **Тип:** не код · **Гейт:** реальный IBAN открыт, KYB пройден

| Задача | Чек-лист ID | Доказательство |
|---|---|---|
| KYB у платёжного провайдера (документы, UBO, лицензии) | `fund_kyb_completed` 🛑 | подтверждение провайдера |
| Реальный IBAN на юрлицо/SPV | `fund_real_iban` 🛑 | реквизиты счёта |
| KYB институциональных инвесторов/SPV | `cmp_kyb_investors` | процедура |

**Зависит от:** Фаза 0. **Блокирует:** все денежные рельсы.

---

## Фаза 2 — Входящие платёжные рельсы (Funding)
**Владелец:** owner + eng · **Гейт:** деньги можно ПОЛУЧИТЬ

| Задача | Чек-лист ID | Доказательство |
|---|---|---|
| Stripe Live активирован, ключи в проде, payout-счёт привязан | `fund_stripe_live` 🛑 | Stripe Dashboard = Live/Activated |
| SEPA inbound: банк принимает входящие на funding-счёт | `fund_sepa_inbound` 🛑 | тестовый входящий перевод |
| SWIFT inbound (международные инвесторы) | `fund_swift_inbound` | реквизиты корреспондента |
| Monobank Business / UAH-эквайринг (если нужен UAH) | `fund_monobank_acquiring` | договор эквайринга |
| Платёжный провайдер закреплён в конфиге (не manual_ops) | `fund_provider_selected` | конфиг прода |
| Webhook поповнения подписан секретом (env `STRIPE_WEBHOOK_SECRET`) | `fund_webhook_secret` (auto) | секрет в env прода |
| Лимиты min/max поповнения | `fund_min_max_limits` | конфиг |

**Eng-замечание:** `fund_idempotency`, `fund_currency_support` (live FX) уже auto-green —
код готов; нужны лишь реальные ключи/секрет в проде.

---

## Фаза 3 — Исходящие рельсы (Withdrawal)
**Владелец:** owner + ops · **Гейт:** деньги можно ВЫВЕСТИ

| Задача | Чек-лист ID | Доказательство |
|---|---|---|
| Хотя бы один реальный канал вывода (SEPA/SWIFT/bank-API/CSV) | `wd_channel_live` 🛑 | реальный исходящий перевод |
| SEPA payout проверен реальным переводом | `wd_sepa_payout` | банковская выписка |
| Импорт банковского CSV в реконсиляцию | `wd_bank_csv_import` | прогон импорта |
| Модель банковских комиссий учтена в выплате | `wd_bank_fee_model` | расчёт |
| Лимиты/velocity вывода | `wd_limits_velocity` | конфиг |

**Eng готово (auto/maker-checker):** `wd_approval_workflow`, `wd_aml_rescreen`,
`wd_reconciliation` — нужен только реальный банковский канал.

---

## Фаза 4 — Юридическая упаковка (подписана юристом)
**Владелец:** legal/owner · **Гейт:** документы опубликованы и согласованы

| Задача | Чек-лист ID | Статус кода |
|---|---|---|
| Investor Agreement / SPV-документы проверены юристом | `legal_investor_agreement` 🛑 | требует юриста |
| Terms of Service | `legal_tos` 🛑 | контент в пакете (auto), нужен sign-off |
| Privacy Policy | `legal_privacy` 🛑 | контент в пакете (auto) |
| AML Policy | `legal_aml_policy` 🛑 | контент в пакете (auto) |
| Risk Disclosure | `legal_risk_disclosure` 🛑 | контент в пакете (auto) |
| KYC Policy | `legal_kyc_policy` | контент в пакете (auto) |
| Dividend Policy | `legal_dividend_policy` | нужен документ |
| Secondary Market Rules | `legal_secondary_rules` | контент в пакете (auto) |

**Замечание:** тексты политик уже есть в коде (`legal_content.py`) → auto-detect зелёный
на "опубликовано". Остаётся **юридическая верификация и подписание** — закрывается
override'ом с приложенным заключением юриста.

---

## Фаза 5 — Money-Cycle Dress Rehearsal (репетиция на собственных деньгах)
**Владелец:** owner + ops + eng · **Гейт:** один полный цикл с банк-подтверждением

> Не тест. Настоящий цикл на 10–100 EUR (можно деньгами основателя).

```
Funding → Reconciliation → Ledger → Ownership → Certificate
→ Dividend → Withdrawal → Bank confirmation
```

| Контрольная точка | Чек-лист ID |
|---|---|
| Полный реальный цикл выполнен | `mc_real_cycle_executed` 🛑 |
| Поповнение → ledger | `mc_funding_to_ledger` (auto) |
| Ledger → ownership ≤100% | `mc_ledger_to_ownership` (auto) |
| Сертификат выпущен | `mc_certificate_issue` (auto) |
| Дивиденд начислен планировщиком | `mc_dividend_calc` (auto) |
| Округление без потери копеек | `mc_rounding_policy` |
| FX точность на момент проводки | `mc_fx_accuracy` (auto) |
| Банковские комиссии сведены | `mc_bank_fee_recon` |
| Налоговые проводки ПДФО+ВЗ | `mc_tax_postings` (auto) |
| Итоговая реконсиляция = 0 | `mc_reconciliation_tie` (auto) |
| Ручные шаги операторов задокументированы | `mc_operator_manual_steps` |

**Зачем:** именно здесь всплывают округления, FX, банк-комиссии, реконсиляция,
налоги и ручные процессы — то, что не ловит ни один контракт.

---

## Фаза 6 — Безопасность секретов и финальные прод-гейты
**Владелец:** eng · **Гейт:** прод включён, демо вычищено, секреты в хранилище

| Задача | Чек-лист ID |
|---|---|
| Секреты в vault/env, ротация определена | `sec_secrets_mgmt` 🛑 |
| `LUMEN_ENV=production` включает прод-гейты | `inf_prod_env_gate` 🛑 (auto) |
| Демо-аккаунты/quick-access bypass выключены | `inf_demo_purge` 🛑 (auto в prod) |
| Все прод env-переменные заданы и проверены | `inf_env_vars` |
| TLS/HTTPS принудительно | `inf_tls` |
| Внешний pentest перед запуском | `sec_pentest` |

---

## Фаза 7 — Первый реальный инвестор + операционный запуск
**Владелец:** owner + ops · **Гейт:** первый внешний инвестор прошёл цикл

После dress rehearsal: онбординг первого реального инвестора, затем «хвост» из 20–50
мелочей (уведомления, тексты, статусы, UX KYC, onboarding, коммуникации менеджеров).
Эти пункты сгруппированы в чек-листе как `ix_*`, `rep_*`, `ops_*` и закрываются по факту.

---

## Сводка: 9 текущих открытых BLOCKER'ов → фазы

| # | Блокер | Фаза | Кто |
|---|---|---|---|
| 1 | `legal_regulatory_stance` | 0 | owner+юрист |
| 2 | `fund_kyb_completed` | 1 | owner |
| 3 | `fund_real_iban` | 1 | owner |
| 4 | `fund_stripe_live` | 2 | owner |
| 5 | `fund_sepa_inbound` | 2 | owner |
| 6 | `wd_channel_live` | 3 | owner+ops |
| 7 | `legal_investor_agreement` | 4 | legal |
| 8 | `mc_real_cycle_executed` | 5 | owner+ops+eng |
| 9 | `sec_secrets_mgmt` | 6 | eng |

**Параллелизация:** Фазы 0→1→2/3 — последовательны (зависят от юрлица/счёта).
Фаза 4 (юр-пакет) и Фаза 6 (секреты/гейты) идут **параллельно** с 1–3.
Фаза 5 (dress rehearsal) требует готовности 2+3. Фаза 7 — финал.

---

## Как отслеживать прогресс
1. Открыть `/admin/launch-readiness` → вкладка **Launch Checklist v1.0**.
2. По мере закрытия пункта — раскрыть его, нажать **Готово (Complete)**, вписать
   доказательство (ссылка/дата/реквизит) → override с актором и таймстампом.
3. Когда все 🛑 BLOCKER зелёные → панель покажет **go_live_ready = true**.
4. Скачать актуальный срез: `GET /api/admin/launch-readiness/checklist/doc`.

> Документ-источник генерируется из seed. Этот Execution Plan — owner-facing
> последовательность; чек-лист — полная категорийная матрица. Используйте вместе.
