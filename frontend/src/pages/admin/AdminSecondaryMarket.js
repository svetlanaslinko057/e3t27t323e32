import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import { TrendingUp, DollarSign, ShoppingBag, Tag, History, RefreshCw } from 'lucide-react';

export default function AdminSecondaryMarket() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/admin/secondary/overview'); setData(r.data); }
    catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="p-6 md:p-10 space-y-3">{[1,2,3].map(i=><div key={i} className="h-24 rounded-2xl bg-muted/40 animate-pulse" />)}</div>;
  if (!data) return null;

  return (
    <div className="p-6 md:p-10 max-w-6xl" data-testid="admin-secondary">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 13 · Secondary Market</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Вторинний ринок</h1>
          <p className="mt-1 text-token-muted text-sm">Оверсайт лістингів, оферів і угод. Комісія платформи {(data.platform_fee_pct*100).toFixed(2)}%.</p>
        </div>
        <button onClick={load} className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2" data-testid="btn-refresh-secondary">
          <RefreshCw className="w-3.5 h-3.5" /> Оновити
        </button>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        <KPI label="Дохід платформи" value={formatUAH(data.platform_revenue_uah)} icon={DollarSign} accent="emerald" />
        <KPI label="Оборот (settled)" value={formatUAH(data.settled_volume_uah)} icon={TrendingUp} accent="sky" />
        <KPI label="Закрито угод" value={data.counts.trades.settled} icon={History} accent="neutral" />
      </div>

      <div className="grid sm:grid-cols-3 gap-3 mb-6">
        <CountCard title="Лістинги" icon={Tag} counts={data.counts.listings} />
        <CountCard title="Офери" icon={ShoppingBag} counts={data.counts.bids} />
        <CountCard title="Угоди" icon={History} counts={data.counts.trades} />
      </div>

      <h2 className="text-sm font-semibold mb-3">Останні угоди</h2>
      {!data.recent_trades?.length ? (
        <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-token-muted">Угод поки немає</div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr><th className="text-left px-3 py-2">Час</th><th className="text-left px-3 py-2">Об'єкт</th><th className="text-right px-3 py-2">Сума</th><th className="text-right px-3 py-2">Комісія</th><th className="text-left px-3 py-2">Trade</th></tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {data.recent_trades.map(t => (
                <tr key={t.id} data-testid={`recent-trade-${t.id}`} className="hover:bg-muted/20">
                  <td className="px-3 py-2 text-token-muted text-[12px] whitespace-nowrap">{formatDateUk(t.settled_at || t.created_at)}</td>
                  <td className="px-3 py-2 text-[12px] truncate max-w-[240px]">{t.asset_title}</td>
                  <td className="px-3 py-2 text-right font-semibold tabular-nums whitespace-nowrap">{formatUAH(t.gross_uah)}</td>
                  <td className="px-3 py-2 text-right text-token-muted tabular-nums whitespace-nowrap">{formatUAH(t.fee_uah)}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{t.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const KPI = ({ label, value, icon: Icon, accent='neutral' }) => {
  const map = { emerald: 'border-emerald-200 bg-emerald-50/60', sky: 'border-sky-200 bg-sky-50/60', neutral: 'border-border bg-card' };
  return (
    <div className={`p-4 rounded-2xl border ${map[accent]}`}>
      <div className="flex items-center gap-2 text-token-muted text-[11px] uppercase tracking-widest">{Icon && <Icon className="w-4 h-4" />}{label}</div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
};

const CountCard = ({ title, icon: Icon, counts }) => (
  <div className="p-4 rounded-2xl border border-border bg-card">
    <div className="flex items-center gap-2 text-sm font-semibold mb-2"><Icon className="w-4 h-4" /> {title}</div>
    <div className="space-y-1 text-xs">
      {Object.entries(counts).map(([k, v]) => (
        <div key={k} className="flex items-center justify-between"><span className="text-token-muted">{k}</span><span className="font-mono font-semibold">{v}</span></div>
      ))}
    </div>
  </div>
);
