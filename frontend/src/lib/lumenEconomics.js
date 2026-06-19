/**
 * Lumen — спільна бібліотека економічних розрахунків (Web).
 *
 * Це клієнтський дзеркало серверного `/api/assets/{id}/economics`. Ми завжди
 * віддаємо перевагу серверним даним, але якщо потрібен швидкий лайв-прев'ю
 * або «що якби» сценарій, ці функції повертають той самий формат у JS.
 *
 * Аналог: `/app/expo/src/lumen-economics.ts`
 *
 * Зміна формули ОДНОЧАСНО має застосовуватись у:
 *   • backend `lumen_api.py` (`asset_economics`)
 *   • web `frontend/src/lib/lumenEconomics.js`
 *   • mobile `expo/src/lumen-economics.ts`
 */

/** Версія економічної моделі — має дорівнювати серверній `ECONOMICS_VERSION`.
 *  Якщо CI-перевірка `/api/economics/spec` поверне інший version — це сигнал
 *  оновити цей файл у синхроні з бекендом. */
export const LUMEN_ECONOMICS_VERSION = '1.0.0';

/** Категорійні дефолти економічної моделі — повторюють серверні. */
export const ECONOMICS_DEFAULTS = {
  _global:     { rental_share: 0.55, opex_rate: 0.12, tax_rate: 0.195, platform_fee: 0.02 },
  residential: { rental_share: 0.60, opex_rate: 0.10, tax_rate: 0.195, platform_fee: 0.02 },
  real_estate: { rental_share: 0.60, opex_rate: 0.10, tax_rate: 0.195, platform_fee: 0.02 },
  commercial:  { rental_share: 0.75, opex_rate: 0.15, tax_rate: 0.195, platform_fee: 0.02 },
  logistics:   { rental_share: 0.80, opex_rate: 0.10, tax_rate: 0.195, platform_fee: 0.02 },
  construction:{ rental_share: 0.55, opex_rate: 0.12, tax_rate: 0.195, platform_fee: 0.02 },
  land:        { rental_share: 0.05, opex_rate: 0.03, tax_rate: 0.195, platform_fee: 0.02 },
  development: { rental_share: 0.10, opex_rate: 0.05, tax_rate: 0.195, platform_fee: 0.025 },
};

/** Сценарії «Що якби» для UX — однакові на web і mobile. */
export const ECONOMICS_SCENARIOS = [
  { key: 'native',      label: 'Як є' },
  { key: 'residential', label: 'Житло',      rental_share: 0.60, opex_rate: 0.10 },
  { key: 'commercial',  label: 'Комерція',   rental_share: 0.75, opex_rate: 0.15 },
  { key: 'logistics',   label: 'Логістика',  rental_share: 0.80, opex_rate: 0.10 },
  { key: 'land',        label: 'Земля',      rental_share: 0.05, opex_rate: 0.03 },
  { key: 'development', label: 'Девелопмент',rental_share: 0.10, opex_rate: 0.05 },
];

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, Number.isFinite(n) ? n : 0));
const clamp01 = (n) => clamp(n, 0, 1);
const round  = (n) => Math.round(n);

/**
 * Повна економічна модель для активу на введену суму.
 *
 * @param {object} input
 * @param {number} input.ticket            — інвестована сума, ₴
 * @param {number} input.horizonMonths     — горизонт, місяців
 * @param {number} input.grossYieldPercent — брутто-дохідність у %
 * @param {number} input.rentalShare       — частка доходу з оренди (0–1)
 * @param {number} input.opexRate          — opex від орендного валового (0–1)
 * @param {number} input.taxRate           — ставка податку (0–1)
 * @param {number} input.platformFee       — комісія платформи (0–1)
 * @returns серверносуміжна структура (shares, rates, annual, exit, totals, cashflow)
 */
export function computeEconomics({
  ticket,
  horizonMonths = 60,
  grossYieldPercent = 12,
  rentalShare = 0.55,
  opexRate = 0.12,
  taxRate = 0.195,
  platformFee = 0.02,
}) {
  const t = Math.max(Number(ticket) || 0, 1);
  const horizonY = Math.max(1, Math.round((Number(horizonMonths) || 12) / 12));
  const gross = (Number(grossYieldPercent) || 0) / 100;
  const rshare = clamp01(rentalShare);
  const ashare = Math.max(0, 1 - rshare);
  const opex = clamp01(opexRate);
  const tax = clamp01(taxRate);
  const fee = clamp01(platformFee);

  const annualRentalGross = t * gross * rshare;
  const annualOpex = annualRentalGross * opex;
  const annualRentalAfterOpex = annualRentalGross - annualOpex;
  const annualTax = annualRentalAfterOpex * tax;
  const annualPlatform = annualRentalAfterOpex * fee;
  const annualNet = annualRentalAfterOpex - annualTax - annualPlatform;

  const appreciationTotal = t * gross * ashare * horizonY;
  const exitTax = appreciationTotal * tax;
  const appreciationNet = appreciationTotal - exitTax;

  const totalNet = annualNet * horizonY + appreciationNet;
  const netIrr = t > 0 ? Math.pow((t + totalNet) / t, 1 / horizonY) - 1 : 0;

  const cashflow = [];
  for (let y = 1; y <= horizonY; y++) {
    const exitPart = y === horizonY ? appreciationNet : 0;
    cashflow.push({
      year: y,
      rental_net: round(annualNet),
      exit: round(exitPart),
      total: round(annualNet + exitPart),
    });
  }

  return {
    ticket: round(t),
    horizon_years: horizonY,
    horizon_months: Number(horizonMonths) || horizonY * 12,
    shares: { rental: rshare, appreciation: ashare },
    rates: {
      gross_yield: gross,
      opex_rate: opex,
      tax_rate: tax,
      platform_fee: fee,
    },
    annual: {
      rental_gross: round(annualRentalGross),
      opex: round(annualOpex),
      tax: round(annualTax),
      platform_fee: round(annualPlatform),
      rental_net: round(annualNet),
    },
    exit: {
      appreciation_total: round(appreciationTotal),
      exit_tax: round(exitTax),
      appreciation_net: round(appreciationNet),
    },
    totals: {
      total_net: round(totalNet),
      net_irr_percent: Math.round(netIrr * 100 * 100) / 100,
      gross_yield_percent: Math.round(gross * 10000) / 100,
    },
    cashflow,
  };
}

/**
 * Застосувати сценарій «Що якби» поверх серверних даних.
 * Якщо сценарій 'native' — повертаємо серверні дані без змін.
 */
export function applyScenario(serverEcon, scenarioKey) {
  if (!serverEcon || !scenarioKey || scenarioKey === 'native') return serverEcon;
  const sc = ECONOMICS_SCENARIOS.find((s) => s.key === scenarioKey);
  if (!sc || sc.rental_share == null) return serverEcon;
  return computeEconomics({
    ticket: serverEcon.ticket,
    horizonMonths: serverEcon.horizon_months,
    grossYieldPercent: serverEcon.totals.gross_yield_percent,
    rentalShare: sc.rental_share,
    opexRate: sc.opex_rate,
    taxRate: serverEcon.rates.tax_rate,
    platformFee: serverEcon.rates.platform_fee,
  });
}
