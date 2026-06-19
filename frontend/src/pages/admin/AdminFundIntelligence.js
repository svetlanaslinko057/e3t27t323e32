import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent, lumenError } from '@/lib/lumenApi';
import {
  Gauge, Wallet, Users, TrendingUp, Banknote, ArrowDownToLine, ArrowUpFromLine,
  Clock, CircleDollarSign, HeartPulse, AlertCircle, ShieldCheck, AlertTriangle,
  ShieldAlert, Loader2, Coins,
} from 'lucide-react';

/** Sprint 9 — Admin Fund Intelligence Dashboard.
 *  Усі показники рахуються наживо з реєстрів (ledger/ownerships/payouts/...). */

const HEALTH = {
  healthy:  { label: 'Здорові',     cls: 'bg-emerald-100 text-emerald-800', bar: 'bg-emerald-500', Icon: ShieldCheck },
  warning:  { label: 'Увага',       cls: 'bg-amber-100 text-amber-800',     bar: 'bg-amber-500',   Icon: AlertTriangle },
  critical: { label: 'Критичні',    cls: 'bg-red-100 text-red-700',         bar: 'bg-red-500',     Icon: ShieldAlert },
};

export default function AdminFundIntelligence() {
  const [fi, setFi] = useState(null);
  const [health, setHealth] = useState([]);
  const [thresholds, setThresholds] = useState(null);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, h] = await Promise.all([
        lumen.get('/admin/fund/intelligence'),
        lumen.get('/admin/fund/health'),
      ]);
      setFi(a.data || null);
      setHealth(h.data?.items || []);
      setThresholds(h.data?.thresholds || null);
      setError('');
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити аналітику фонду')); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const dist = fi?.asset_health_distribution || { healthy: 0, warning: 0, critical: 0 };
  const distTotal = (dist.healthy || 0) + (dist.warning || 0) + (dist.critical || 0);
  const shownHealth = filter ? health.filter((h) => h.status === filter) : health;

  return (
    <div className="p-6 md:p-10" data-testid="admin-fund">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Управління фондом</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-2">
          <Gauge className="w-7 h-7 text-[#2E5D4F]" /> Аналітика фонду
        </h1>
        <p className="mt-1 text-token-muted">Fund Intelligence — стан капіталу під управлінням. Усі метрики рахуються наживо з реєстру (ledger — джерело істини).</p>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      {loading && !fi ? (
        <div className="grid sm:grid-cols-3 lg:grid-cols-4 gap-3">{[1,2,3,4,5,6,7,8].map(i => <div key={i} className="h-24 rounded-2xl bg-muted animate-pulse" />)}</div>
      ) : (
        <>
          {/* KPI grid */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4" data-testid="fund-kpis">
            <Kpi label="AUM (під управлінням)" value={formatUAH(fi.aum)} Icon={Wallet} accent="teal" big testid="kpi-aum" />
            <Kpi label="Активні інвестори" value={fi.active_investors} Icon={Users} testid="kpi-investors" />
            <Kpi label="Залучено капіталу" value={formatUAH(fi.capital_raised)} Icon={Banknote} accent="emerald" testid="kpi-raised" />
            <Kpi label="Виплачено доходу" value={formatUAH(fi.capital_paid_out)} Icon={Coins} accent="emerald" testid="kpi-paid-out" />
            <Kpi label="Очікує фінансування" value={formatUAH(fi.pending_funding)} Icon={Clock} accent="amber" testid="kpi-pending-funding" />
            <Kpi label="Очікують виводи" value={formatUAH(fi.pending_withdrawals)} Icon={ArrowUpFromLine} accent="amber" testid="kpi-pending-withdrawals" />
            <Kpi label={`Найближчі виплати${fi.upcoming_payouts_count ? ` · ${fi.upcoming_payouts_count}` : ''}`} value={formatUAH(fi.upcoming_payouts)} Icon={ArrowDownToLine} testid="kpi-upcoming" />
            <Kpi label="Чиста грошова позиція" value={formatUAH(fi.net_cash_position)} Icon={CircleDollarSign} accent="teal" big testid="kpi-net-cash" />
            <Kpi label="Середня дохідність" value={formatPercent(fi.average_yield)} Icon={TrendingUp} testid="kpi-avg-yield" />
            <Kpi label="Виведено (всього)" value={formatUAH(fi.withdrawals_paid)} Icon={ArrowUpFromLine} testid="kpi-withdrawn" />
          </div>

          {/* Asset Health distribution */}
          <section className="mb-6" data-testid="fund-health-distribution">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><HeartPulse className="w-4 h-4" /> Здоров’я активів</h2>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="grid sm:grid-cols-3 gap-3 mb-4">
                {['healthy', 'warning', 'critical'].map((k) => {
                  const meta = HEALTH[k]; const Icon = meta.Icon;
                  return (
                    <button key={k} onClick={() => setFilter(filter === k ? '' : k)} data-testid={`health-card-${k}`}
                      className={`text-left rounded-xl border p-4 transition ${filter === k ? 'border-[#2E5D4F] ring-1 ring-[#2E5D4F]/30' : 'border-border hover:border-[#2E5D4F]/40'}`}>
                      <div className="flex items-center gap-2 text-muted-foreground"><Icon className="w-4 h-4" /><span className="text-[11px] uppercase tracking-widest">{meta.label}</span></div>
                      <p className="text-2xl font-bold tabular-nums mt-1">{dist[k] || 0}</p>
                    </button>
                  );
                })}
              </div>
              {/* Stacked bar */}
              <div className="h-3 rounded-full bg-muted overflow-hidden flex">
                {['healthy', 'warning', 'critical'].map((k) => (
                  (dist[k] > 0) ? <div key={k} className={`${HEALTH[k].bar} h-full`} style={{ width: `${(dist[k] / (distTotal || 1)) * 100}%` }} title={`${HEALTH[k].label}: ${dist[k]}`} /> : null
                ))}
              </div>
            </div>
          </section>

          {/* Asset Health table */}
          <section data-testid="fund-health-table">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <h2 className="font-semibold flex items-center gap-2"><HeartPulse className="w-4 h-4" /> Моніторинг активів</h2>
              {filter && <button onClick={() => setFilter('')} className="text-xs text-muted-foreground underline" data-testid="health-clear-filter">Скинути фільтр</button>}
            </div>
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-border">
                      <th className="px-4 py-3 font-medium">Актив</th>
                      <th className="px-4 py-3 font-medium">Стан</th>
                      <th className="px-4 py-3 font-medium">Сигнали</th>
                      <th className="px-4 py-3 font-medium text-right">Прострочення</th>
                      <th className="px-4 py-3 font-medium text-right">Днів без звіту</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shownHealth.length === 0 ? (
                      <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Немає активів за цим фільтром.</td></tr>
                    ) : shownHealth.map((h) => {
                      const meta = HEALTH[h.status] || HEALTH.healthy;
                      return (
                        <tr key={h.asset_id} className="border-b border-border last:border-0" data-testid={`health-row-${h.asset_id}`}>
                          <td className="px-4 py-3 font-medium">{h.asset_title}</td>
                          <td className="px-4 py-3"><span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span></td>
                          <td className="px-4 py-3">
                            {(!h.signals || h.signals.length === 0) ? <span className="text-muted-foreground text-xs">Без зауважень</span> : (
                              <ul className="space-y-0.5">
                                {h.signals.map((s, i) => (
                                  <li key={i} className="text-xs flex items-center gap-1.5">
                                    <span className={`w-1.5 h-1.5 rounded-full ${s.severity === 'critical' ? 'bg-red-500' : 'bg-amber-500'}`} />{s.message}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right tabular-nums">{h.days_overdue ? `${h.days_overdue} дн.` : '—'}</td>
                          <td className="px-4 py-3 text-right tabular-nums">{h.days_since_report != null ? `${h.days_since_report} дн.` : '—'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            {thresholds && (
              <p className="text-[11px] text-muted-foreground mt-2">
                Пороги: прострочення &gt;{thresholds.overdue_warn_days} дн. → увага, &gt;{thresholds.overdue_crit_days} дн. → критично ·
                звіти &gt;{thresholds.report_warn_days} дн. → увага, &gt;{thresholds.report_crit_days} дн. → критично.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

const Kpi = ({ label, value, Icon, accent = 'neutral', big, testid }) => {
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
    </div>
  );
};
