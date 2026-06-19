import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent, formatDateUk } from '@/lib/lumenApi';
import {
  Gauge, Activity, TrendingUp, TrendingDown, Minus, Lightbulb, Globe2,
  Hammer, LogOut, Layers3, Building2, Users, Wallet, CalendarClock,
  CheckCircle2, XCircle, ArrowRight, Droplets, BarChart3, Sparkles,
  Flag, Receipt, FileText, RefreshCw, Repeat, MapPin,
  ShieldCheck, Percent, Banknote, PiggyBank, CircleDot, Home, Coins,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';
const GOLD = '#C99B3D';

const BAND_TONE = {
  high: { text: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', ring: '#0f9d58', chip: 'bg-emerald-100 text-emerald-800' },
  medium: { text: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', ring: GOLD, chip: 'bg-amber-100 text-amber-800' },
  low: { text: 'text-rose-700', bg: 'bg-rose-50', border: 'border-rose-200', ring: '#e11d48', chip: 'bg-rose-100 text-rose-700' },
};

/* ════════════════════════════ compact badges (cards) ════════════════════════════ */

export function ConvictionBadge({ score, band, label, compact }) {
  const tone = BAND_TONE[band] || BAND_TONE.medium;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tone.chip} ${tone.border}`}
      title={`Впевненість: ${label || ''} (${score}/100)`}
      data-testid="conviction-badge"
    >
      <Gauge className="w-3 h-3" /> {score}{compact ? '' : '/100'}
    </span>
  );
}

export function LiquidityBadge({ score, band, label }) {
  const tone = BAND_TONE[band] || BAND_TONE.medium;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tone.chip} ${tone.border}`}
      title={`Ліквідність: ${label || ''} (${score}/10)`}
      data-testid="liquidity-badge"
    >
      <Droplets className="w-3 h-3" /> {score}/10
    </span>
  );
}

/** Tiny self-fetching badge pair for marketplace/opportunity cards. */
export function AssetScoreBadges({ assetId }) {
  const [c, setC] = useState(null);
  const [l, setL] = useState(null);
  useEffect(() => {
    let alive = true;
    if (!assetId) return;
    lumen.get(`/assets/${assetId}/conviction`).then((r) => alive && setC(r.data)).catch(() => {});
    lumen.get(`/assets/${assetId}/liquidity`).then((r) => alive && setL(r.data)).catch(() => {});
    return () => { alive = false; };
  }, [assetId]);
  if (!c && !l) return null;
  return (
    <div className="flex items-center gap-1.5 flex-wrap" data-testid="asset-score-badges">
      {c && <ConvictionBadge score={c.score} band={c.band} label={c.label} compact />}
      {l && <LiquidityBadge score={l.score} band={l.band} label={l.label} />}
    </div>
  );
}

/**
 * Compact "скоринг" strip for BROWSE / list cards (landing, opportunities).
 * Answers "почему именно этот актив" before the user even opens the object:
 * Risk band · Conviction score · Occupancy — pulled from the public
 * intelligence endpoint. One lightweight call per card.
 */
export function AssetMiniScore({ assetId, className = '' }) {
  const [snap, setSnap] = useState(null);
  const [conv, setConv] = useState(null);
  useEffect(() => {
    let alive = true;
    if (!assetId) return;
    lumen.get(`/assets/${assetId}/intelligence`).then((r) => {
      if (!alive) return;
      setSnap(r.data?.snapshot || null);
      setConv(r.data?.conviction || null);
    }).catch(() => {});
    return () => { alive = false; };
  }, [assetId]);
  if (!snap && !conv) return null;
  const risk = snap?.risk || {};
  const rt = RISK_TONE[risk.band] || RISK_TONE.medium;
  const cTone = BAND_TONE[conv?.band] || BAND_TONE.medium;
  return (
    <div className={`flex items-center gap-1.5 flex-wrap ${className}`} data-testid="asset-mini-score">
      {risk.label && (
        <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[10px] font-semibold" title={`Ризик: ${risk.label}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${rt.dot}`} />
          <span className="text-muted-foreground font-normal">Ризик</span> <span className={rt.text}>{risk.label}</span>
        </span>
      )}
      {conv && (
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${cTone.chip} ${cTone.border}`} title={`Впевненість ${conv.score}/100`}>
          <Gauge className="w-3 h-3" /> {conv.score}<span className="font-normal opacity-70">/100</span>
        </span>
      )}
      {snap?.occupancy_percent != null && (
        <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[10px] font-semibold" title={`Заповнюваність ${snap.occupancy_percent}%`}>
          <Building2 className="w-3 h-3 text-muted-foreground" /><span className="text-muted-foreground font-normal">Заповн.</span> {snap.occupancy_percent}%
        </span>
      )}
    </div>
  );
}


/* ════════════════════════════ circular gauge ════════════════════════════ */

function Ring({ value, max = 100, color, size = 92, label, sub }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / max));
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" className="text-muted" strokeWidth="8" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={circ * (1 - pct)} style={{ transition: 'stroke-dashoffset .6s ease' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold leading-none">{label}</span>
        {sub && <span className="text-[9px] uppercase tracking-wider text-muted-foreground mt-0.5">{sub}</span>}
      </div>
    </div>
  );
}

/* ════════════════════════════ B5a — Asset Snapshot (at-a-glance scoring) ════════════════════════════ */

const RISK_TONE = {
  low: { text: 'text-emerald-700', dot: 'bg-emerald-500' },
  medium: { text: 'text-amber-700', dot: 'bg-amber-500' },
  high: { text: 'text-rose-700', dot: 'bg-rose-500' },
};

function SnapCell({ icon, label, value, valueClass, testid }) {
  return (
    <div className="flex-1 min-w-[120px] px-4 py-3" data-testid={testid}>
      <div className="flex items-center gap-1.5 text-muted-foreground">{icon}<span className="text-[10px] uppercase tracking-widest">{label}</span></div>
      <p className={`mt-1 font-bold text-[15px] leading-tight ${valueClass || ''}`}>{value}</p>
    </div>
  );
}

/** Compact "Скоринг" strip — answers the buyer's first questions at a glance. */
export function AssetSnapshot({ snapshot }) {
  if (!snapshot) return null;
  const s = snapshot;
  const risk = s.risk || {};
  const rt = RISK_TONE[risk.band] || RISK_TONE.medium;
  const term = s.term_months ? `${s.term_months} міс` : '—';
  const occ = s.occupancy_percent != null ? `${s.occupancy_percent}%` : '—';
  const div = s.dividends ? `${s.dividends.paid} з ${s.dividends.total}` : '—';
  const fullPaid = s.dividends && s.dividends.total > 0 && s.dividends.paid >= s.dividends.total;
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="asset-snapshot">
      <div className="flex flex-wrap divide-x divide-border/70 [&>*]:border-t-0">
        <SnapCell testid="snap-risk"
          icon={<ShieldCheck className="w-4 h-4" />} label="Ризик"
          value={<span className="inline-flex items-center gap-1.5"><span className={`w-2 h-2 rounded-full ${rt.dot}`} />{risk.label || '—'}</span>}
          valueClass={rt.text} />
        <SnapCell testid="snap-yield"
          icon={<Percent className="w-4 h-4" />} label="Доходність"
          value={s.yield_percent != null ? `${formatPercent(s.yield_percent)}` : '—'}
          valueClass="text-[#2E5D4F]" />
        <SnapCell testid="snap-term"
          icon={<CalendarClock className="w-4 h-4" />} label="Термін" value={term} />
        <SnapCell testid="snap-occupancy"
          icon={<Building2 className="w-4 h-4" />} label="Заповнення" value={occ} />
        <SnapCell testid="snap-dividends"
          icon={<Receipt className="w-4 h-4" />} label="Виплачено"
          value={<span className="inline-flex items-center gap-1.5">{div}{fullPaid && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />}</span>}
          valueClass={fullPaid ? 'text-emerald-700' : ''} />
        <SnapCell testid="snap-status"
          icon={<CircleDot className="w-4 h-4" />} label="Статус" value={s.status_label || '—'} />
      </div>
    </div>
  );
}

/* ════════════════════════════ B5b — Why we invested (crisp thesis bullets) ════════════════════════════ */

export function WhyWeInvested({ highlights }) {
  if (!highlights || highlights.length === 0) return null;
  return (
    <div className="rounded-2xl border border-[#2E5D4F]/25 bg-[#2E5D4F]/5 p-6" data-testid="why-we-invested">
      <header className="mb-4 flex items-center gap-2">
        <span className="w-8 h-8 rounded-lg bg-[#2E5D4F]/15 flex items-center justify-center"><Sparkles className="w-4 h-4 text-[#2E5D4F]" /></span>
        <h2 className="font-bold text-lg">Чому ми інвестували в цей актив</h2>
      </header>
      <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
        {highlights.map((h, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm" data-testid={`why-${i}`}>
            <CheckCircle2 className="w-4 h-4 text-[#2E5D4F] mt-0.5 shrink-0" />
            <span className="text-foreground/90 leading-snug">{h}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ════════════════════════════ B5c — Operating cash-flow ════════════════════════════ */

export function CashFlow({ data }) {
  if (!data || !data.has_content) return null;
  const cells = [
    { icon: <Banknote className="w-4 h-4" />, label: 'Інвестовано', value: data.invested, tone: 'text-foreground' },
    { icon: <Home className="w-4 h-4" />, label: 'Отримано оренди', value: data.rent_received, tone: 'text-foreground' },
    { icon: <Coins className="w-4 h-4" />, label: 'Виплачено інвесторам', value: data.paid_to_investors, tone: 'text-emerald-700' },
    { icon: <PiggyBank className="w-4 h-4" />, label: 'Резерв', value: data.reserve, tone: 'text-sky-700' },
  ];
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="cashflow">
      <header className="mb-4 flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-[#2E5D4F]" />
        <h2 className="font-semibold">Грошовий потік об'єкта</h2>
        <span className="text-[11px] text-muted-foreground ml-auto">з моменту запуску</span>
      </header>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="cashflow-cells">
        {cells.map((c, i) => (
          <div key={i} className="rounded-xl border border-border bg-background/50 p-3">
            <div className="flex items-center gap-1.5 text-muted-foreground">{c.icon}<span className="text-[10px] uppercase tracking-widest leading-tight">{c.label}</span></div>
            <p className={`mt-1.5 font-bold ${c.tone}`}>{formatUAH(c.value)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ════════════════════════════ B5d — Rounds timeline ════════════════════════════ */

const ROUND_STATUS = {
  closed: { label: 'закрито', cls: 'bg-emerald-100 text-emerald-800 border-emerald-200', dot: 'bg-emerald-500' },
  open: { label: 'відкрито', cls: 'bg-amber-100 text-amber-800 border-amber-200', dot: 'bg-amber-500 animate-pulse' },
  upcoming: { label: 'скоро', cls: 'bg-muted text-muted-foreground border-border', dot: 'bg-muted-foreground/50' },
};

export function RoundsTimeline({ data }) {
  if (!data || !Array.isArray(data.items) || data.items.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="rounds-timeline">
      <header className="mb-4 flex items-center gap-2">
        <Layers3 className="w-4 h-4 text-[#2E5D4F]" />
        <h2 className="font-semibold">Історія об'єкта</h2>
      </header>
      <div className="flex items-stretch gap-2 overflow-x-auto pb-1">
        {data.items.map((r, i) => {
          const st = ROUND_STATUS[r.status] || ROUND_STATUS.upcoming;
          return (
            <div key={i} className="flex items-center gap-2 shrink-0" data-testid={`round-${i}`}>
              <div className="rounded-xl border border-border bg-background/50 px-4 py-3 min-w-[140px]">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-sm">{r.label}</span>
                  <span className={`w-2 h-2 rounded-full ${st.dot}`} />
                </div>
                <span className={`mt-2 inline-block text-[10px] px-2 py-0.5 rounded-full border ${st.cls}`}>{st.label}</span>
                {typeof r.progress === 'number' && (
                  <div className="mt-2">
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-[#2E5D4F]" style={{ width: `${Math.min(100, r.progress)}%` }} />
                    </div>
                    <span className="text-[10px] text-muted-foreground">{r.progress}% зібрано</span>
                  </div>
                )}
              </div>
              {i < data.items.length - 1 && <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ════════════════════════════ B5+B6+B7 — Intelligence panel ════════════════════════════ */

export function IntelligencePanel({ metrics, conviction, liquidity }) {
  if (!metrics && !conviction && !liquidity) return null;
  const cTone = BAND_TONE[conviction?.band] || BAND_TONE.medium;
  const lTone = BAND_TONE[liquidity?.band] || BAND_TONE.medium;
  const m = metrics || {};

  const liveCells = [
    { icon: <BarChart3 className="w-4 h-4" />, label: 'Зібрано раунду', value: `${m.funding?.progress_percent ?? 0}%` },
    { icon: <Users className="w-4 h-4" />, label: 'Інвесторів', value: m.investor_count ?? 0 },
    { icon: <Wallet className="w-4 h-4" />, label: 'Виплачено', value: formatUAH(m.payout?.total_paid || 0) },
    { icon: <Repeat className="w-4 h-4" />, label: 'Лотів на вторинці', value: m.secondary?.active_listings ?? 0 },
    { icon: <CalendarClock className="w-4 h-4" />, label: 'Сер. строк володіння', value: m.avg_hold_days ? `${m.avg_hold_days} дн.` : '—' },
    { icon: <Building2 className="w-4 h-4" />, label: 'Заповнюваність', value: m.occupancy_percent != null ? `${Math.round(m.occupancy_percent)}%` : '—' },
  ];

  return (
    <div className="rounded-2xl border border-border bg-card p-6 space-y-6" data-testid="intelligence-panel">
      <header className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-[#2E5D4F]" />
        <h2 className="font-semibold">Здоров'я об'єкта</h2>
        <span className="text-[11px] text-muted-foreground ml-auto">розраховано з реальних даних платформи</span>
      </header>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Conviction */}
        {conviction && (
          <div className={`rounded-xl border ${cTone.border} ${cTone.bg} p-4`} data-testid="conviction-card">
            <div className="flex items-center gap-4">
              <Ring value={conviction.score} color={cTone.ring} label={conviction.score} sub="/100" />
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1"><Gauge className="w-3 h-3" /> Conviction Score</p>
                <p className={`text-lg font-bold ${cTone.text}`}>{conviction.label}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">впевненість на основі фактів, не AI</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {(conviction.factors || []).map((f) => (
                <div key={f.key}>
                  <div className="flex justify-between text-[11px] mb-0.5">
                    <span className="text-muted-foreground">{f.label}</span>
                    <span className="font-medium">{f.value}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${f.value}%`, backgroundColor: cTone.ring }} />
                  </div>
                  {f.detail && <p className="text-[10px] text-muted-foreground mt-0.5">{f.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Liquidity */}
        {liquidity && (
          <div className={`rounded-xl border ${lTone.border} ${lTone.bg} p-4`} data-testid="liquidity-card">
            <div className="flex items-center gap-4">
              <Ring value={liquidity.score} max={10} color={lTone.ring} label={liquidity.score} sub="/10" />
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1"><Droplets className="w-3 h-3" /> Liquidity Score</p>
                <p className={`text-lg font-bold ${lTone.text}`}>{liquidity.label}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">наскільки легко перепродати частку</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {(liquidity.signals || []).map((s) => (
                <div key={s.key} className="flex items-center gap-2 text-sm">
                  {s.ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" /> : <XCircle className="w-4 h-4 text-muted-foreground shrink-0" />}
                  <span className="text-muted-foreground">{s.label}:</span>
                  <span className="font-medium ml-auto">{s.detail}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Live metrics */}
      {metrics && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1"><Activity className="w-3 h-3" /> Живі показники</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="live-metrics">
            {liveCells.map((c, i) => (
              <div key={i} className="rounded-xl border border-border bg-background/50 p-3">
                <div className="flex items-center gap-1.5 text-muted-foreground">{c.icon}<span className="text-[10px] uppercase tracking-widest">{c.label}</span></div>
                <p className="mt-1.5 font-bold">{c.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ════════════════════════════ B1 — Investment Thesis ════════════════════════════ */

const THESIS_PARTS = [
  { key: 'opportunity', label: 'Можливість', icon: Lightbulb, q: 'Чому існує ця можливість?' },
  { key: 'market', label: 'Ринок', icon: Globe2, q: 'Чому ринок це недооцінює?' },
  { key: 'execution', label: 'Виконання', icon: Hammer, q: 'Як ми це реалізуємо?' },
  { key: 'exit', label: 'Вихід', icon: LogOut, q: 'Як інвестор поверне капітал?' },
];

export function InvestmentThesis({ thesis }) {
  if (!thesis || !thesis.has_content) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="investment-thesis">
      <header className="mb-4">
        <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Investment Thesis</p>
        <h2 className="text-xl font-bold mt-1">Чому саме цей об'єкт</h2>
      </header>
      <div className="grid sm:grid-cols-2 gap-4">
        {THESIS_PARTS.map(({ key, label, icon: Icon, q }) => {
          const body = thesis[key];
          if (!body) return null;
          return (
            <div key={key} className="rounded-xl border border-border bg-background/40 p-4" data-testid={`thesis-${key}`}>
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 rounded-lg bg-[#2E5D4F]/10 flex items-center justify-center"><Icon className="w-4 h-4 text-[#2E5D4F]" /></span>
                <div>
                  <p className="font-semibold text-sm">{label}</p>
                  <p className="text-[11px] text-muted-foreground">{q}</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{body}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ════════════════════════════ B2 — Scenario Engine ════════════════════════════ */

const SC_ICON = { bear: TrendingDown, base: Minus, bull: TrendingUp };
const SC_TONE = {
  danger: { border: 'border-rose-200', bg: 'bg-rose-50/60', accent: 'text-rose-700', dot: 'bg-rose-500' },
  primary: { border: 'border-[#2E5D4F]/30', bg: 'bg-[#2E5D4F]/5', accent: 'text-[#2E5D4F]', dot: 'bg-[#2E5D4F]' },
  success: { border: 'border-emerald-200', bg: 'bg-emerald-50/60', accent: 'text-emerald-700', dot: 'bg-emerald-500' },
};

export function ScenarioEngine({ data }) {
  if (!data || !Array.isArray(data.scenarios) || data.scenarios.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="scenario-engine">
      <header className="mb-4 flex items-end justify-between flex-wrap gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Scenario Engine</p>
          <h2 className="text-xl font-bold mt-1">Три сценарії, а не одна обіцянка</h2>
        </div>
        <span className="text-[11px] text-muted-foreground">горизонт {data.horizon_years} р.</span>
      </header>
      <div className="grid sm:grid-cols-3 gap-4">
        {data.scenarios.map((s) => {
          const Icon = SC_ICON[s.key] || Minus;
          const tone = SC_TONE[s.tone] || SC_TONE.primary;
          return (
            <div key={s.key} className={`rounded-xl border ${tone.border} ${tone.bg} p-4`} data-testid={`scenario-${s.key}`}>
              <div className="flex items-center gap-2">
                <Icon className={`w-4 h-4 ${tone.accent}`} />
                <p className={`font-semibold ${tone.accent}`}>{s.label}</p>
              </div>
              <div className="mt-3 space-y-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">Дохідність / рік</span>
                  <span className="text-lg font-bold">{formatPercent(s.annual_yield_percent)}</span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">Вихід (за весь строк)</span>
                  <span className={`text-lg font-bold ${tone.accent}`}>+{Number(s.exit_percent).toFixed(1).replace('.', ',')}%</span>
                </div>
                <div className="flex items-baseline justify-between pt-2 border-t border-border/60">
                  <span className="text-xs text-muted-foreground">Чиста IRR</span>
                  <span className="text-sm font-semibold">{formatPercent(s.net_irr_percent)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-muted-foreground mt-3">{data.disclaimer}</p>
    </div>
  );
}

/* ════════════════════════════ B3 — Capital Stack ════════════════════════════ */

export function CapitalStack({ data }) {
  if (!data || !Array.isArray(data.layers) || data.layers.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="capital-stack">
      <header className="mb-4 flex items-end justify-between flex-wrap gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Capital Stack</p>
          <h2 className="text-xl font-bold mt-1">Структура капіталу угоди</h2>
        </div>
        <span className="text-[11px] text-muted-foreground">Вартість об'єкта: <b className="text-foreground">{formatUAH(data.asset_value)}</b></span>
      </header>

      {/* waterfall bar */}
      <div className="h-6 rounded-lg overflow-hidden flex border border-border" data-testid="capital-stack-bar">
        {data.layers.map((l) => (
          <div key={l.key} title={`${l.label}: ${l.percent}%`} style={{ width: `${l.percent}%`, backgroundColor: l.color }} />
        ))}
      </div>

      <div className="mt-4 space-y-2">
        {data.layers.map((l) => (
          <div key={l.key} className="flex items-center gap-3 text-sm" data-testid={`stack-layer-${l.key}`}>
            <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: l.color }} />
            <span className="text-muted-foreground">{l.label}</span>
            <span className="ml-auto font-medium">{formatUAH(l.amount)}</span>
            <span className="text-muted-foreground w-12 text-right">{l.percent}%</span>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-sm">
        <span className="text-muted-foreground">Частка інвесторів у капіталі</span>
        <span className="font-bold text-[#2E5D4F]">{data.investor_share_percent}%</span>
      </div>

      {(data.crypto_raised > 0 || data.fiat_raised > 0) && (
        <div className="mt-4 grid grid-cols-2 gap-3" data-testid="capital-stack-rails">
          <div className="rounded-xl border border-[#2E5D4F]/25 bg-[#2E5D4F]/[0.05] p-3">
            <p className="text-[11px] uppercase tracking-wide text-[#2E5D4F]">Зібрано криптою</p>
            <p className="mt-1 font-mono text-lg font-bold text-foreground" data-testid="capital-crypto">{formatUAH(data.crypto_raised)}</p>
            <p className="text-xs text-muted-foreground">{data.crypto_percent}% від коштів інвесторів</p>
          </div>
          <div className="rounded-xl border border-[#C9A961]/40 bg-[#C9A961]/[0.08] p-3">
            <p className="text-[11px] uppercase tracking-wide text-[#9c7d33]">Зібрано фіатом</p>
            <p className="mt-1 font-mono text-lg font-bold text-foreground" data-testid="capital-fiat">{formatUAH(data.fiat_raised)}</p>
            <p className="text-xs text-muted-foreground">{data.fiat_percent}% від коштів інвесторів</p>
          </div>
        </div>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
        Розподіл «крипта / фіат» рахується з реальних підтверджених внесків пулу. Криптою враховано також реінвестування з внутрішнього балансу.
      </p>
    </div>
  );
}

/* ════════════════════════════ B4 — Asset Journal ════════════════════════════ */

const JOURNAL_ICON = {
  acquisition: Building2, operations: Hammer, payout: Receipt, report: FileText,
  secondary: Repeat, funding: BarChart3, valuation: RefreshCw, milestone: Flag, general: Flag,
};
const JOURNAL_COLOR = {
  acquisition: PRIMARY, operations: '#6b7280', payout: '#0f9d58', report: '#0ea5e9',
  secondary: GOLD, funding: PRIMARY, valuation: GOLD, milestone: PRIMARY, general: '#6b7280',
};

export function AssetJournal({ items }) {
  if (!items) return null;
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="journal-empty">
        Історія об'єкта поповнюватиметься тут — придбання, ремонт, оренда, виплати, угоди.
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="asset-journal">
      <header className="mb-5">
        <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Asset Journal</p>
        <h2 className="text-xl font-bold mt-1">Жива історія активу</h2>
      </header>
      <ol className="relative border-l border-border ml-3">
        {items.map((e, i) => {
          const Icon = JOURNAL_ICON[e.kind] || Flag;
          const color = JOURNAL_COLOR[e.kind] || PRIMARY;
          return (
            <li key={i} className="mb-6 ml-6 last:mb-0" data-testid={`journal-item-${i}`}>
              <span className="absolute -left-3 flex items-center justify-center w-6 h-6 rounded-full ring-4 ring-background" style={{ backgroundColor: `${color}1a` }}>
                <Icon className="w-3.5 h-3.5" style={{ color }} />
              </span>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: `${color}1a`, color }}>{e.kind_label}</span>
                {e.source === 'authored' && <span className="text-[9px] uppercase tracking-wider text-muted-foreground">оператор</span>}
                <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(e.date)}</span>
              </div>
              <h3 className="mt-1.5 font-semibold text-sm">{e.title}</h3>
              {e.body && <p className="mt-0.5 text-sm text-muted-foreground leading-relaxed">{e.body}</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ════════════════════════════ B8 — Similar Assets ════════════════════════════ */

export function SimilarAssets({ items, basePath = '/investor/assets' }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-6" data-testid="similar-assets">
      <header className="mb-4 flex items-center gap-2">
        <Layers3 className="w-4 h-4 text-[#2E5D4F]" />
        <h2 className="font-semibold">Схожі об'єкти</h2>
      </header>
      <div className="grid sm:grid-cols-2 gap-4">
        {items.map((a) => (
          <Link key={a.id} to={`${basePath}/${a.id}`} className="group rounded-xl border border-border bg-background/40 overflow-hidden hover:border-[#2E5D4F] transition" data-testid={`similar-${a.id}`}>
            <div className="h-28 bg-muted" style={a.cover_url ? { backgroundImage: `url(${a.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}>
              {!a.cover_url && <div className="w-full h-full flex items-center justify-center text-muted-foreground"><Building2 className="w-8 h-8" /></div>}
            </div>
            <div className="p-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F]">{a.category_label || a.category}</span>
                {a.same_category && <span className="text-[9px] text-muted-foreground">та сама категорія</span>}
              </div>
              <p className="mt-1.5 font-semibold text-sm leading-tight group-hover:text-[#2E5D4F] transition">{a.title}</p>
              {a.location && <p className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5"><MapPin className="w-3 h-3" /> {a.location}</p>}
              <div className="mt-2 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">дохідність</span>
                <span className="font-semibold text-[#2E5D4F]">{formatPercent(a.target_yield)}</span>
              </div>
              <div className="flex items-center justify-between text-xs mt-0.5">
                <span className="text-muted-foreground">мін. вхід</span>
                <span className="font-medium">{formatUAH(a.min_ticket)}</span>
              </div>
              <span className="mt-2 inline-flex items-center gap-1 text-[11px] text-[#2E5D4F] group-hover:gap-1.5 transition-all">Дивитись <ArrowRight className="w-3 h-3" /></span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

/* ════════════════════════════ data hook ════════════════════════════ */

export function useAssetIntelligence(assetId) {
  const [intel, setIntel] = useState(null);
  const [journal, setJournal] = useState(null);
  const [similar, setSimilar] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!assetId) return;
    let alive = true;
    setLoading(true);
    Promise.all([
      lumen.get(`/assets/${assetId}/intelligence`).catch(() => null),
      lumen.get(`/assets/${assetId}/journal`).catch(() => null),
      lumen.get(`/assets/${assetId}/similar`).catch(() => null),
    ]).then(([i, j, s]) => {
      if (!alive) return;
      setIntel(i?.data || null);
      setJournal(j?.data?.items || []);
      setSimilar(s?.data?.items || []);
    }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [assetId]);

  return { intel, journal, similar, loading };
}
