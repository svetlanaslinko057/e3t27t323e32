import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent, formatDateUk, lumenError } from '@/lib/lumenApi';
import { NavLink } from 'react-router-dom';
import {
  TrendingUp, Coins, Clock, Wallet, Building2, ArrowDownToLine,
  AlertCircle, CalendarClock, History,
} from 'lucide-react';

/** Sprint 8 — Investor Income / Earnings */

const REC_BADGE = {
  planned:   { label: 'Заплановано', cls: 'bg-muted text-muted-foreground' },
  generated: { label: 'Сформовано',  cls: 'bg-sky-100 text-sky-800' },
  approved:  { label: 'Схвалено',    cls: 'bg-indigo-100 text-indigo-800' },
  credited:  { label: 'Нараховано',  cls: 'bg-emerald-100 text-emerald-800' },
  cancelled: { label: 'Скасовано',   cls: 'bg-red-100 text-red-700' },
};

export default function InvestorIncome() {
  const [data, setData] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [inc, pr] = await Promise.all([
        lumen.get('/investor/income'),
        lumen.get('/investor/income/payouts?limit=50'),
      ]);
      setData(inc.data || null);
      setPayouts(pr.data?.items || []);
      setError('');
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити доходи')); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = data?.summary || {};

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="investor-income">
      <header className="mb-8 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Результат інвестицій</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Доходи</h1>
          <p className="mt-1 text-muted-foreground">
            Нараховані дивіденди та орендний дохід за вашими активами. Нараховані кошти зараховуються на гаманець.
          </p>
        </div>
        <NavLink to="/investor/wallet" data-testid="link-wallet"
          className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] text-sm">
          <Wallet className="w-4 h-4" /> До гаманця
        </NavLink>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      {/* Summary cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <SummaryCard label="Нараховано всього" value={formatUAH(s.accrued_total)} icon={Coins} accent="emerald" testid="income-accrued" big />
        <SummaryCard label="Виплачено (на гаманець)" value={formatUAH(s.paid_total)} icon={ArrowDownToLine} accent="sky" testid="income-paid" />
        <SummaryCard label="Очікується" value={formatUAH(s.expected_total)} icon={Clock} accent="amber" testid="income-expected" />
        <SummaryCard label="Сер. дохідність" value={formatPercent(s.yield_percent)} icon={TrendingUp} accent="neutral" testid="income-yield" />
      </div>

      {loading && !data ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Per-asset yield */}
          <section data-testid="income-by-asset">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Building2 className="w-4 h-4" /> Дохідність за активами</h2>
            {(data?.by_asset || []).length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-8 text-center">
                <p className="text-sm text-muted-foreground">Поки немає активів з доходом.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {data.by_asset.map((a) => (
                  <div key={a.asset_id} data-testid={`income-asset-${a.asset_id}`}
                    className="rounded-2xl border border-border bg-card p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold truncate">{a.asset_title}</p>
                        <p className="text-xs text-muted-foreground">Інвестовано {formatUAH(a.invested)}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-lg font-bold text-emerald-700 tabular-nums">{formatUAH(a.paid)}</p>
                        <p className="text-xs text-muted-foreground">дохідність {formatPercent(a.yield_percent)}</p>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                      <div><p className="text-muted-foreground">Очікується</p><p className="font-medium tabular-nums">{formatUAH(a.expected)}</p></div>
                      <div className="flex flex-col"><span className="text-muted-foreground flex items-center gap-1"><History className="w-3 h-3" /> Остання</span><span className="font-medium">{a.last_payout ? formatDateUk(a.last_payout) : '—'}</span></div>
                      <div className="flex flex-col"><span className="text-muted-foreground flex items-center gap-1"><CalendarClock className="w-3 h-3" /> Наступна</span><span className="font-medium">{a.next_payout ? formatDateUk(a.next_payout) : '—'}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Payout history */}
          <section data-testid="income-payouts">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Coins className="w-4 h-4" /> Історія нарахувань</h2>
            {payouts.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-8 text-center" data-testid="income-payouts-empty">
                <p className="text-sm text-muted-foreground">Нарахувань ще немає.</p>
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-card divide-y divide-border" data-testid="income-payouts-list">
                {payouts.map((p) => {
                  const b = REC_BADGE[p.status] || { label: p.status_label, cls: 'bg-muted' };
                  return (
                    <div key={p.id} className="flex items-center justify-between gap-3 p-3" data-testid={`payout-${p.id}`}>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{p.asset_title}</p>
                        <p className="text-xs text-muted-foreground">{p.type_label} · {p.period_label}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-mono font-semibold tabular-nums text-emerald-700">{formatUAH(p.amount_uah)}</p>
                        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

const SummaryCard = ({ label, value, icon: Icon, accent = 'neutral', testid, big }) => {
  const map = {
    emerald: 'border-emerald-200 bg-emerald-50/50',
    sky:     'border-sky-200 bg-sky-50/40',
    amber:   'border-amber-200 bg-amber-50/40',
    neutral: 'border-border bg-card',
  };
  return (
    <div data-testid={testid} className={`rounded-2xl border p-4 ${map[accent]} ${big ? 'sm:col-span-2 lg:col-span-1' : ''}`}>
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon className="w-4 h-4" />}
        <p className="text-[11px] uppercase tracking-widest">{label}</p>
      </div>
      <p className={`mt-2 font-bold tabular-nums ${big ? 'text-3xl' : 'text-2xl'}`}>{value}</p>
    </div>
  );
};
