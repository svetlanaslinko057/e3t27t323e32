import { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { lumen, API, formatUAH, formatPercent, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  PieChart, TrendingUp, Wallet, Coins, Clock, Building2, MapPin, ShieldAlert,
  ArrowDownToLine, BarChart3, AlertCircle, CalendarClock, History, FileText,
  Download, CheckCircle2, Circle, Layers, Banknote,
} from 'lucide-react';

/** Sprint 9 — Investor Analytics & Fund Intelligence (investor side). */

const RISK_COLOR = {
  low:    { bar: 'bg-emerald-500', dot: 'bg-emerald-500' },
  medium: { bar: 'bg-amber-500',   dot: 'bg-amber-500' },
  high:   { bar: 'bg-red-500',     dot: 'bg-red-500' },
  unknown:{ bar: 'bg-slate-400',   dot: 'bg-slate-400' },
};
const CAT_BAR = 'bg-[#2E5D4F]';
const REGION_BAR = 'bg-[#B8893B]';

const EVENT_META = {
  investment_created:   { label: 'Інвестицію створено',   dot: 'bg-sky-500',     Icon: Building2 },
  kyc_approved:         { label: 'KYC підтверджено',      dot: 'bg-indigo-500',  Icon: ShieldAlert },
  contract_signed:      { label: 'Договір підписано',     dot: 'bg-violet-500',  Icon: FileText },
  payment_confirmed:    { label: 'Оплату підтверджено',   dot: 'bg-teal-600',    Icon: Banknote },
  payout_received:      { label: 'Отримано виплату',      dot: 'bg-emerald-600', Icon: Coins },
  withdrawal_submitted: { label: 'Заявка на вивід',       dot: 'bg-amber-600',   Icon: ArrowDownToLine },
};

export default function InvestorAnalytics() {
  const [ov, setOv] = useState(null);
  const [assets, setAssets] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [ptl, setPtl] = useState(null);
  const [stmts, setStmts] = useState(null);
  const [stmtType, setStmtType] = useState('monthly');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, a, t, p, s] = await Promise.all([
        lumen.get('/investor/analytics/overview'),
        lumen.get('/investor/analytics/assets'),
        lumen.get('/investor/analytics/timeline?limit=40'),
        lumen.get('/investor/analytics/portfolio-timeline'),
        lumen.get('/investor/statements'),
      ]);
      setOv(o.data || null);
      setAssets(a.data?.items || []);
      setTimeline(t.data?.items || []);
      setPtl(p.data || null);
      setStmts(s.data || null);
      setError('');
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити аналітику')); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pf = ov?.portfolio || {};
  const yl = ov?.yield || {};
  const al = ov?.allocation || {};

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="investor-analytics">
      <header className="mb-8 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Стан капіталу</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-2">
            <PieChart className="w-7 h-7 text-[#2E5D4F]" /> Аналітика портфеля
          </h1>
          <p className="mt-1 text-muted-foreground">Не список об’єктів, а стан вашого капіталу: вартість, дохідність, алокація та історія.</p>
        </div>
        <NavLink to="/investor/income" data-testid="link-income"
          className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] text-sm">
          <TrendingUp className="w-4 h-4" /> Доходи
        </NavLink>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      {loading && !ov ? (
        <div className="space-y-3">{[1,2,3,4].map(i => <div key={i} className="h-24 rounded-2xl bg-muted animate-pulse" />)}</div>
      ) : (
        <>
          {/* Block 1 — Portfolio Value */}
          <section className="mb-8" data-testid="analytics-portfolio">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Layers className="w-4 h-4" /> Вартість портфеля</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <Stat label="Всього інвестовано" value={formatUAH(pf.invested_total)} Icon={Banknote} accent="neutral" big testid="pf-invested" />
              <Stat label="Поточна вартість" value={formatUAH(pf.current_value)} Icon={BarChart3} accent="teal" testid="pf-current" />
              <Stat label="Отримано виплат" value={formatUAH(pf.received_total)} Icon={ArrowDownToLine} accent="emerald" testid="pf-received" />
              <Stat label="Очікується виплат" value={formatUAH(pf.expected_total)} Icon={Clock} accent="amber" testid="pf-expected" />
            </div>
          </section>

          {/* Block 2 — Yield Analytics */}
          <section className="mb-8" data-testid="analytics-yield">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Дохідність</h2>
            <div className="grid sm:grid-cols-3 gap-3">
              <Stat label="Realized (отримано)" value={formatPercent(yl.realized_yield)} Icon={Coins} accent="emerald" testid="yield-realized" />
              <Stat label="Unrealized (очікується)" value={formatPercent(yl.unrealized_yield)} Icon={Clock} accent="amber" testid="yield-unrealized" />
              <Stat label="Annualized (річна)" value={formatPercent(yl.annualized_yield)} Icon={TrendingUp} accent="teal" testid="yield-annualized"
                hint={`зважено за часом · ${formatPercent((yl.weighted_holding_years || 0) * 100).replace(' %','')} р.`} />
            </div>
          </section>

          {/* Allocation */}
          <section className="mb-8 grid lg:grid-cols-3 gap-4" data-testid="analytics-allocation">
            <AllocPanel title="Класи активів" icon={Building2} rows={al.by_category} colorFor={() => CAT_BAR} testid="alloc-category" />
            <AllocPanel title="Географія" icon={MapPin} rows={al.by_region} colorFor={() => REGION_BAR} testid="alloc-region" />
            <AllocPanel title="Ризик-категорії" icon={ShieldAlert} rows={al.by_risk} colorFor={(r) => (RISK_COLOR[r.key] || RISK_COLOR.unknown).bar} testid="alloc-risk" />
          </section>

          {/* Block 3 — Asset Performance */}
          <section className="mb-8" data-testid="analytics-assets">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><BarChart3 className="w-4 h-4" /> Ефективність активів</h2>
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-border">
                      <th className="px-4 py-3 font-medium">Актив</th>
                      <th className="px-4 py-3 font-medium text-right">Інвестовано</th>
                      <th className="px-4 py-3 font-medium text-right">Частка</th>
                      <th className="px-4 py-3 font-medium text-right">Отримано</th>
                      <th className="px-4 py-3 font-medium text-right">ROI</th>
                      <th className="px-4 py-3 font-medium text-right">Наступна виплата</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.length === 0 ? (
                      <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">Поки немає активів у портфелі.</td></tr>
                    ) : assets.map((a) => (
                      <tr key={a.asset_id} className="border-b border-border last:border-0" data-testid={`perf-${a.asset_id}`}>
                        <td className="px-4 py-3">
                          <div className="font-medium">{a.asset_title}</div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>{a.category_label}</span>·<span>{a.region}</span>
                            <span className={`inline-flex items-center gap-1`}><span className={`w-2 h-2 rounded-full ${(RISK_COLOR[a.risk_level]||RISK_COLOR.unknown).dot}`} />{a.risk_label}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">{formatUAH(a.invested)}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{formatPercent(a.share_percent)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-emerald-700">{formatUAH(a.received)}</td>
                        <td className="px-4 py-3 text-right tabular-nums font-semibold">{formatPercent(a.roi)}</td>
                        <td className="px-4 py-3 text-right text-muted-foreground">{a.next_payout ? formatDateUk(a.next_payout) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Portfolio Timeline (5-stage lifecycle) */}
          <section className="mb-8" data-testid="analytics-portfolio-timeline">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Layers className="w-4 h-4" /> Інвестиційна історія</h2>
            <div className="rounded-2xl border border-border bg-card p-5">
              <Stepper stages={ptl?.stages || []} />
            </div>
          </section>

          {/* Two-column: Investor timeline + Statements */}
          <section className="grid lg:grid-cols-2 gap-8">
            {/* Block 4 — Investor Timeline */}
            <div data-testid="analytics-timeline">
              <h2 className="font-semibold mb-3 flex items-center gap-2"><History className="w-4 h-4" /> Стрічка подій</h2>
              {timeline.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">Подій ще немає.</div>
              ) : (
                <div className="rounded-2xl border border-border bg-card p-4">
                  <ol className="relative border-l border-border ml-2">
                    {timeline.map((e, i) => {
                      const m = EVENT_META[e.type] || { label: e.title, dot: 'bg-slate-400', Icon: Circle };
                      const Icon = m.Icon;
                      return (
                        <li key={i} className="mb-5 ml-5 last:mb-0" data-testid={`tl-${e.type}`}>
                          <span className={`absolute -left-[9px] flex items-center justify-center w-4 h-4 rounded-full ${m.dot}`}>
                            <Icon className="w-2.5 h-2.5 text-white" />
                          </span>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium">{e.title}</p>
                            {e.amount ? <span className="text-sm font-semibold tabular-nums text-[#2E5D4F]">{formatUAH(e.amount)}</span> : null}
                          </div>
                          <p className="text-xs text-muted-foreground">{formatDateUk(e.date)}{e.description ? ` · ${e.description}` : ''}</p>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              )}
            </div>

            {/* Block 7 — Statements */}
            <div data-testid="analytics-statements">
              <h2 className="font-semibold mb-3 flex items-center gap-2"><FileText className="w-4 h-4" /> Виписки (PDF)</h2>
              <div className="rounded-2xl border border-border bg-card p-4">
                <div className="flex gap-1 mb-4 p-1 rounded-xl bg-muted w-fit">
                  {(stmts?.types || []).map((t) => (
                    <button key={t.key} onClick={() => setStmtType(t.key)} data-testid={`stmt-tab-${t.key}`}
                      className={`px-3 h-8 rounded-lg text-xs font-medium transition-colors ${stmtType === t.key ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                      {t.label}
                    </button>
                  ))}
                </div>
                <div className="space-y-2 max-h-[360px] overflow-y-auto">
                  {((stmts?.periods || {})[stmtType] || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-6">Періодів ще немає.</p>
                  ) : (stmts.periods[stmtType]).map((p) => (
                    <a key={p.key} href={`${API}/investor/statements/${p.type}/${p.key}/pdf`} target="_blank" rel="noreferrer"
                      data-testid={`stmt-dl-${p.type}-${p.key}`}
                      className={`flex items-center justify-between gap-3 p-3 rounded-xl border transition-colors ${p.has_activity ? 'border-border hover:border-[#2E5D4F] hover:bg-muted/40' : 'border-dashed border-border opacity-60'}`}>
                      <div>
                        <p className="text-sm font-medium">{p.label}</p>
                        <p className="text-xs text-muted-foreground">{p.has_activity ? 'Є операції за період' : 'Без операцій'}</p>
                      </div>
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#2E5D4F]"><Download className="w-4 h-4" /> PDF</span>
                    </a>
                  ))}
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

const Stat = ({ label, value, Icon, accent = 'neutral', big, hint, testid }) => {
  const map = {
    teal:    'border-[#2E5D4F]/25 bg-[#2E5D4F]/5',
    emerald: 'border-emerald-200 bg-emerald-50/50',
    amber:   'border-amber-200 bg-amber-50/40',
    neutral: 'border-border bg-card',
  };
  return (
    <div data-testid={testid} className={`rounded-2xl border p-4 ${map[accent]}`}>
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon className="w-4 h-4" />}
        <p className="text-[11px] uppercase tracking-widest">{label}</p>
      </div>
      <p className={`mt-2 font-bold tabular-nums ${big ? 'text-2xl' : 'text-xl'}`}>{value}</p>
      {hint ? <p className="text-[11px] text-muted-foreground mt-1">{hint}</p> : null}
    </div>
  );
};

const AllocPanel = ({ title, icon: Icon, rows = [], colorFor, testid }) => (
  <div className="rounded-2xl border border-border bg-card p-4" data-testid={testid}>
    <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Icon className="w-4 h-4" /> {title}</h3>
    {(!rows || rows.length === 0) ? (
      <p className="text-xs text-muted-foreground py-4 text-center">Немає даних.</p>
    ) : (
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.key}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-medium truncate">{r.label}</span>
              <span className="text-muted-foreground tabular-nums">{formatPercent(r.percent)}</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className={`h-full ${colorFor(r)} rounded-full`} style={{ width: `${Math.min(100, r.percent)}%` }} />
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5 tabular-nums">{formatUAH(r.amount)}</div>
          </div>
        ))}
      </div>
    )}
  </div>
);

const Stepper = ({ stages = [] }) => (
  <div className="flex flex-col sm:flex-row sm:items-start gap-4 sm:gap-0">
    {stages.map((s, i) => (
      <div key={s.key} className="flex-1 flex sm:flex-col items-start sm:items-center gap-3 sm:gap-2 relative">
        {i < stages.length - 1 && (
          <span className={`hidden sm:block absolute top-3 left-1/2 w-full h-0.5 ${stages[i + 1].done ? 'bg-[#2E5D4F]' : 'bg-border'}`} />
        )}
        <span className={`relative z-10 flex items-center justify-center w-6 h-6 rounded-full shrink-0 ${s.done ? 'bg-[#2E5D4F] text-white' : 'bg-muted text-muted-foreground border border-border'}`}>
          {s.done ? <CheckCircle2 className="w-4 h-4" /> : <Circle className="w-3.5 h-3.5" />}
        </span>
        <div className="sm:text-center">
          <p className={`text-sm font-medium ${s.done ? '' : 'text-muted-foreground'}`}>{s.label}</p>
          <p className="text-[11px] text-muted-foreground">{s.date ? formatDateUk(s.date) : '—'}</p>
        </div>
      </div>
    ))}
  </div>
);
