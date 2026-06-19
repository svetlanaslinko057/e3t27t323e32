import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowRight, CheckCircle2, TrendingUp, Wallet, PiggyBank, Info, Building2,
} from 'lucide-react';
import { lumen, formatUAH, formatPercent, usdFromUah, UAH_PER_USD } from '@/lib/lumenApi';
import SectionLabel from '@/components/public/SectionLabel';
import Reveal from '@/components/public/Reveal';

/* ───────────────────────── ECONOMIC MODEL ─────────────────────────
 *
 * Реальна модель колективної інвестиції в конкретний об'єкт.
 * Кожен актив має фіксовану економіку (round_target, target_yield,
 * horizon_months, min_ticket, category). Модель потоку залежить від
 * категорії: rental частка + переоцінка частки при виході.
 *
 *   share_pct      = invest / round_target
 *   gross_rental   = invest * (target_yield * rental_share)
 *   monthly_cash   = gross_rental / 12
 *   total_gross    = invest * (1 + irr)^years
 *   appreciation   = total_gross − invest − rental_total
 *   pdfo+vz        = profit_gross * 19.5%  (укр. податок з дивідендів)
 *   irr_eff        = (total_net / invest)^(1/years) − 1
 */

const RENTAL_SHARE_BY_CATEGORY = {
  real_estate: 0.6,
  commercial: 0.6,
  restoration: 0.5,
  construction: 0,
  land: 0,
};

const FALLBACK_ASSETS = [
  { id: 'fa1', title: 'ЖК «Подільський»', category: 'real_estate', category_label: 'нерухомість', location: 'Поділ, Київ', target_yield: 18.5, horizon_months: 24, round_target: 4200000, min_ticket: 75000, status: 'open' },
  { id: 'fa2', title: 'Земельна ділянка «Стоянка»', category: 'land', category_label: 'земля', location: 'Бориспільський р-н', target_yield: 22.0, horizon_months: 36, round_target: 6100000, min_ticket: 150000, status: 'open' },
  { id: 'fa3', title: 'ТЦ «Лавр»', category: 'commercial', category_label: 'комерція', location: 'Львів', target_yield: 14.7, horizon_months: 24, round_target: 5300000, min_ticket: 100000, status: 'open' },
  { id: 'fa4', title: 'Котеджне містечко «Вишневе»', category: 'construction', category_label: 'будівництво', location: 'с. Гатне', target_yield: 21.5, horizon_months: 28, round_target: 5400000, min_ticket: 180000, status: 'open' },
];

export const computeProjection = (asset, amount) => {
  const cat = asset.category;
  const irr = (asset.target_yield || 15) / 100;
  const horizonM = asset.horizon_months || 24;
  const years = horizonM / 12;
  const rentalShare = RENTAL_SHARE_BY_CATEGORY[cat] ?? 0.4;
  const capShare = 1 - rentalShare;
  const sharePct = asset.round_target ? amount / asset.round_target : 0;

  const annualCash = amount * (irr * rentalShare);
  const monthlyCash = annualCash / 12;

  const totalGross = amount * Math.pow(1 + irr, years);
  const rentalTotal = annualCash * years;
  const appreciation = totalGross - amount - rentalTotal;

  const profitGross = totalGross - amount;
  const taxRate = 0.195; // 18% ПДФО + 1.5% військового збору
  const tax = profitGross * taxRate;
  const profitNet = profitGross - tax;
  const totalNet = amount + profitNet;
  const irrEffective = years > 0 ? Math.pow(totalNet / amount, 1 / years) - 1 : 0;

  const scenario = (delta) => {
    const irrScn = irr * (1 + delta);
    const totalScn = amount * Math.pow(1 + irrScn, years);
    return totalScn - amount;
  };

  return {
    sharePct, monthlyCash, annualCash, rentalTotal, appreciation, totalGross,
    profitGross, tax, profitNet, totalNet, irrEffective, years, rentalShare,
    capShare, horizonM,
    conservative: scenario(-0.20),
    base: profitGross,
    optimistic: scenario(0.15),
  };
};

/* ───────────────────────────── COMPONENT ───────────────────────────── */

export default function AssetYieldCalculator() {
  const [allAssets, setAllAssets] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [amount, setAmount] = useState(4000); // USD
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    lumen.get('/assets', { params: { status: 'open' } })
      .then((r) => {
        if (!alive) return;
        const items = (r.data?.items || []).filter((a) => a.round_target && a.min_ticket);
        const list = items.length ? items : FALLBACK_ASSETS;
        setAllAssets(list);
        if (list[0]) {
          setSelectedId(list[0].id);
          setAmount(Math.max(Math.round(usdFromUah(list[0].min_ticket || 50000)), 1000));
        }
      })
      .catch(() => {
        if (!alive) return;
        setAllAssets(FALLBACK_ASSETS);
        setSelectedId(FALLBACK_ASSETS[0].id);
        setAmount(Math.round(usdFromUah(FALLBACK_ASSETS[0].min_ticket)));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const selected = allAssets.find((a) => a.id === selectedId) || allAssets[0];
  const minUsd = selected ? Math.round(usdFromUah(selected.min_ticket || 0)) : 0;
  const maxUsd = selected ? Math.round(usdFromUah(selected.round_target || 1e12)) : 1e12;
  const tooLow = selected && amount < minUsd;
  const tooHigh = selected && amount > maxUsd;
  const isValid = selected && !tooLow && !tooHigh && amount > 0;
  const projection = useMemo(
    () => (selected && isValid ? computeProjection(selected, amount * UAH_PER_USD) : null),
    [selected, isValid, amount],
  );

  const sliderMin = minUsd || 1000;
  const sliderMax = Math.min(maxUsd, Math.max(minUsd * 20, 100000));
  const clampedSlider = Math.min(Math.max(amount, sliderMin), sliderMax);

  return (
    <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
      {/* ── INPUTS ── */}
      <Reveal>
        <div className="rounded-2xl border border-border bg-white p-6 sm:p-8">
          <SectionLabel>Параметри</SectionLabel>

          <div className="mt-7">
            <label className="text-sm font-medium text-token-muted">Оберіть об'єкт</label>
            <AssetSelect
              value={selectedId}
              options={allAssets}
              loading={loading}
              onChange={(id) => {
                setSelectedId(id);
                const a = allAssets.find((x) => x.id === id);
                if (a) {
                  const m = Math.round(usdFromUah(a.min_ticket || 0));
                  if (amount < m) setAmount(m);
                }
              }}
            />
          </div>

          {selected && (
            <div className="mt-5 rounded-xl border border-border bg-[#F7F5EF] p-4 text-sm">
              <InfoRow label="Категорія" value={selected.category_label || selected.category} />
              <InfoRow label="Локація" value={selected.location} />
              <InfoRow label="Горизонт" value={`${selected.horizon_months || 24} міс.`} />
              <InfoRow label="Цільова IRR (валова)" value={formatPercent(selected.target_yield)} accent />
              <InfoRow label="Об'єм пулу" value={formatUAH(selected.round_target)} />
              <InfoRow label="Мінімальна частка" value={formatUAH(selected.min_ticket)} last />
            </div>
          )}

          <div className="mt-7">
            <div className="flex items-end justify-between">
              <label className="text-sm font-medium text-token-muted">Ваш внесок</label>
              <span className="font-mono text-xl font-bold text-[#2E5D4F]">${Math.round(amount).toLocaleString('en-US')}</span>
            </div>
            <div className="mt-3 relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-token-muted font-semibold">$</span>
              <input
                type="number"
                value={amount}
                min={minUsd}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="w-full h-12 pl-8 pr-16 rounded-xl border border-border bg-white focus:outline-none focus:border-[#2E5D4F] font-mono font-semibold text-lg"
                data-testid="calc-amount"
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-token-muted text-xs">USDT</span>
            </div>
            <input
              type="range"
              min={sliderMin}
              max={sliderMax}
              step={Math.max(100, Math.round((sliderMax - sliderMin) / 200))}
              value={clampedSlider}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="lpub-range mt-4 w-full"
              data-testid="calculator-invest-amount-input"
            />
            <div className="mt-1 flex justify-between text-xs text-token-muted">
              <span>${sliderMin.toLocaleString('en-US')}</span>
              <span>${sliderMax.toLocaleString('en-US')}</span>
            </div>

            {tooLow && (
              <p className="mt-2 text-xs text-red-600">Мінімальна частка цього активу — {formatUAH(selected.min_ticket)}</p>
            )}
            {tooHigh && (
              <p className="mt-2 text-xs text-red-600">Об'єм пулу — {formatUAH(selected.round_target)}. Виберіть менший внесок.</p>
            )}
          </div>
        </div>
      </Reveal>

      {/* ── PROJECTION ── */}
      <Reveal delay={0.1}>
        <div className="rounded-2xl bg-[#062614] p-6 sm:p-8 text-white" data-testid="calc-projection">
          <SectionLabel tone="light">Прогноз по об'єкту</SectionLabel>

          {!projection ? (
            <div className="mt-10 text-center text-sm text-white/55">
              {loading ? 'Завантажуємо моделі активів…' : 'Вкажіть коректну суму внеску, щоб побачити прогноз.'}
            </div>
          ) : (
            <div className="mt-7" data-testid="calculator-result">
              <div className="grid grid-cols-3 gap-3 sm:gap-4">
                <BigMetric label="Частка у пулі" value={`${(projection.sharePct * 100).toFixed(2)}%`.replace('.', ',')} />
                <BigMetric label="Чистий прибуток" value={formatUAH(projection.profitNet)} accent />
                <BigMetric label="Ефективна IRR" value={formatPercent(projection.irrEffective * 100)} />
              </div>

              <div className="mt-6 rounded-xl border border-white/12 bg-white/[0.04] p-5">
                <p className="text-xs uppercase tracking-[0.16em] text-white/50">Розкладка по виплатах</p>
                <div className="mt-3 space-y-2.5">
                  {projection.rentalShare > 0 && (
                    <>
                      <FlowLine icon={Wallet} label="Місячна виплата (оренда, ваша частка)" value={formatUAH(projection.monthlyCash)} muted />
                      <FlowLine label={`Сумарна оренда за ${projection.horizonM} міс.`} value={formatUAH(projection.rentalTotal)} />
                    </>
                  )}
                  {projection.capShare > 0 && (
                    <FlowLine icon={TrendingUp} label={`Переоцінка при виході (${Math.round(projection.capShare * 100)}%)`} value={formatUAH(projection.appreciation)} />
                  )}
                  <FlowLine label="Валовий прибуток (до податків)" value={formatUAH(projection.profitGross)} />
                  <FlowLine label="Податок на прибуток (оцінка 19.5%)" value={`−${formatUAH(projection.tax)}`} muted />
                  <div className="my-1 h-px bg-white/10" />
                  <FlowLine icon={PiggyBank} label="Чистий прибуток на руки" value={formatUAH(projection.profitNet)} accent strong />
                  <FlowLine label="Загальна сума на виході" value={formatUAH(projection.totalNet)} strong />
                </div>
              </div>

              <div className="mt-6 rounded-xl border border-white/12 bg-white/[0.04] p-5">
                <p className="text-xs uppercase tracking-[0.16em] text-white/50">Три сценарії за валовим прибутком</p>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <ScenarioPill label="Консервативний" value={projection.conservative} hint="IRR −20%" />
                  <ScenarioPill label="Базовий" value={projection.base} accent />
                  <ScenarioPill label="Оптимістичний" value={projection.optimistic} hint="IRR +15%" />
                </div>
              </div>

              <Link
                to={selected?.id?.startsWith('asset-') ? `/objects/${selected.id}` : '/assets'}
                className="lpub-btn-gold mt-7 w-full justify-center"
                data-testid="calculator-cta"
              >
                Зарезервувати частку в об'єкті <ArrowRight className="h-4 w-4" />
              </Link>
              <p className="mt-4 flex items-start gap-2 text-xs leading-relaxed text-white/45">
                <Info className="mt-0.5 h-3.5 w-3.5 flex-none" />
                Модель базується на параметрах, зафіксованих у договорі участі цього активу. Орендна частина виплачується пропорційно до фактичних надходжень; переоцінка фіксується при виході з раунду. Не є гарантією доходу.
              </p>
            </div>
          )}
        </div>
      </Reveal>
    </div>
  );
}

/* ───────────────────────────── PRIMITIVES ───────────────────────────── */

function InfoRow({ label, value, accent, last }) {
  return (
    <div className={`flex items-center justify-between gap-3 ${last ? '' : 'mb-2'}`}>
      <span className="text-xs text-token-muted">{label}</span>
      <span className={`font-medium ${accent ? 'text-[#2E5D4F]' : 'text-foreground'}`}>{value}</span>
    </div>
  );
}

function BigMetric({ label, value, accent }) {
  return (
    <div className={`rounded-xl border p-4 ${accent ? 'border-[#C9A961]/30 bg-[#C9A961]/[0.06]' : 'border-white/12 bg-white/[0.04]'}`}>
      <p className="text-[10px] uppercase tracking-[0.14em] text-white/50">{label}</p>
      <motion.p
        key={value}
        initial={{ opacity: 0.4, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className={`mt-1.5 font-mono text-xl font-bold sm:text-2xl ${accent ? 'text-[#E5C98A]' : 'text-white'}`}
      >
        {value}
      </motion.p>
    </div>
  );
}

function FlowLine({ icon: Icon, label, value, muted, accent, strong }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className={`flex items-center gap-2 text-sm ${muted ? 'text-white/45' : 'text-white/80'}`}>
        {Icon && <Icon className="h-3.5 w-3.5 flex-none text-white/40" />}
        {label}
      </span>
      <span className={`font-mono ${strong ? 'text-base font-bold' : 'font-medium'} ${accent ? 'text-[#E5C98A]' : muted ? 'text-white/45' : 'text-white'}`}>
        {value}
      </span>
    </div>
  );
}

function ScenarioPill({ label, value, hint, accent }) {
  return (
    <div className={`rounded-xl border p-3 ${accent ? 'border-[#E5C98A]/40 bg-[#E5C98A]/[0.08]' : 'border-white/12 bg-white/[0.03]'}`}>
      <p className="text-[10px] uppercase tracking-[0.12em] text-white/50">{label}</p>
      <p className={`mt-1 font-mono text-sm font-bold ${accent ? 'text-[#E5C98A]' : 'text-white'}`}>{formatUAH(value)}</p>
      {hint && <p className="mt-0.5 text-[10px] text-white/40">{hint}</p>}
    </div>
  );
}

/* Branded asset selector — replaces native <select> with a popover */
function AssetSelect({ value, onChange, options, loading }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);

  const selected = options.find((o) => o.id === value);

  return (
    <div ref={ref} className="relative mt-2" data-testid="calc-asset">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-14 w-full items-center rounded-2xl border border-border bg-white pl-4 pr-12 text-left transition hover:border-[#2E5D4F]/50"
      >
        <span className="min-w-0 flex-1">
          {selected ? (
            <>
              <span className="block truncate font-medium text-foreground">{selected.title}</span>
              <span className="block truncate text-xs text-token-muted">{selected.location} · {selected.category_label || selected.category}</span>
            </>
          ) : (
            <span className="text-token-muted">{loading ? 'Завантаження активів…' : "Оберіть об'єкт…"}</span>
          )}
        </span>
        <span className={`absolute right-4 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F] transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 5.5l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </span>
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 z-30 mt-2 max-h-80 overflow-y-auto overflow-hidden rounded-2xl border border-border bg-white py-1 shadow-2xl"
          style={{ boxShadow: '0 24px 60px -20px rgba(46,93,79,0.25), 0 6px 18px rgba(0,0,0,0.08)' }}
        >
          {options.length === 0 && (
            <li className="px-4 py-3 text-sm text-token-muted">Немає відкритих об'єктів</li>
          )}
          {options.map((o) => {
            const isSel = o.id === value;
            return (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => { onChange(o.id); setOpen(false); }}
                  className={`flex w-full items-center gap-3 px-4 py-3 text-left transition ${isSel ? 'bg-[#2E5D4F]/8' : 'hover:bg-[#F7F5EF]'}`}
                  role="option"
                  aria-selected={isSel}
                >
                  <span className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-[#2E5D4F]/8 text-[#2E5D4F]">
                    <Building2 className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">{o.title}</span>
                    <span className="block truncate text-xs text-token-muted">
                      {o.location} · {o.category_label || o.category} · IRR {formatPercent(o.target_yield)}
                    </span>
                  </span>
                  {isSel && <CheckCircle2 className="h-4 w-4 flex-none text-[#2E5D4F]" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
