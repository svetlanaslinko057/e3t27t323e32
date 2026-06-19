import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { Building2, Users, BarChart3, CircleDollarSign } from 'lucide-react';

export default function AdminReports() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/admin/reports')
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto space-y-8" data-testid="admin-reports">
      <header>
        <p className="text-xs uppercase tracking-widest text-token-muted">Звіти</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Звітність фонду</h1>
        <p className="mt-1 text-token-muted">Ключові показники та розрізи по активах і інвесторах.</p>
      </header>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">{[1, 2, 3, 4].map((i) => <div key={i} className="h-24 rounded-2xl animate-pulse" style={{ background: 'var(--token-surface-elevated)' }} />)}</div>
      ) : !data ? (
        <div className="rounded-2xl p-10 text-center" style={{ border: '1px solid var(--token-border)' }}><p className="font-semibold">Даних поки немає</p></div>
      ) : (
        <>
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi icon={<CircleDollarSign className="w-4 h-4" />} label="Залучено всього" value={formatUAH(data?.kpi?.total_raised)} />
            <Kpi icon={<Users className="w-4 h-4" />} label="Активних інвесторів" value={data?.kpi?.investors_count ?? 0} />
            <Kpi icon={<Building2 className="w-4 h-4" />} label="Активів" value={data?.kpi?.assets_count ?? 0} />
            <Kpi icon={<BarChart3 className="w-4 h-4" />} label="Середня дохідність" value={formatPercent(data?.kpi?.average_yield)} />
          </section>

          <section className="rounded-2xl p-6" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
            <h2 className="font-semibold mb-4">Розподіл за категоріями</h2>
            {(data?.by_category || []).length === 0 ? (
              <p className="text-sm text-token-muted">Поки немає даних.</p>
            ) : (
              <ul className="space-y-3">
                {data.by_category.map((c) => (
                  <li key={c.category}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{c.label}</span>
                      <span className="font-mono">{formatUAH(c.amount)} · {(c.share * 100).toFixed(1)}%</span>
                    </div>
                    <div className="mt-2 h-2 rounded-full overflow-hidden" style={{ background: 'var(--token-border)' }}>
                      <div className="h-full bg-[#2E5D4F]" style={{ width: `${(c.share * 100).toFixed(1)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

const Kpi = ({ icon, label, value }) => (
  <div className="rounded-2xl p-5" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
    <div className="flex items-center gap-2 text-token-muted">{icon}<span className="text-[11px] uppercase tracking-widest">{label}</span></div>
    <p className="mt-3 text-2xl font-bold">{value}</p>
  </div>
);
