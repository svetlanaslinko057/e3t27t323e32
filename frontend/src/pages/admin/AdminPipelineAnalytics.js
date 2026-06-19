import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { BarChart3, Loader2, TrendingUp, Gauge, XCircle, Activity, CheckCircle2, Clock } from 'lucide-react';

const PRIMARY = '#2E5D4F';

export default function AdminPipelineAnalytics() {
  const [an, setAn] = useState(null);
  const [vel, setVel] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [a, v] = await Promise.all([
        lumen.get('/admin/pipeline/analytics'),
        lumen.get('/admin/capital/velocity'),
      ]);
      setAn(a.data); setVel(v.data);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const labels = an?.stage_labels || {};
  const counts = an?.counts || {};
  const maxCount = Math.max(1, ...Object.values(counts));
  const funnelStages = ['lead', 'screening', 'due_diligence', 'committee', 'funding', 'live', 'operating', 'exited'];

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-pipeline-analytics">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Capital Formation OS · Phase E</div>
        <h1 className="text-2xl font-bold">Аналітика воронки</h1>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ['Усього сделок', an?.total_deals, Activity],
          ['Активні', an?.active, TrendingUp],
          ['Запущені', an?.live, CheckCircle2],
          ['Відхилені', an?.rejected, XCircle],
        ].map(([l, v, Icon]) => (
          <div key={l} className="rounded-xl border border-border p-4">
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground"><Icon className="w-3.5 h-3.5" />{l}</div>
            <div className="text-2xl font-bold mt-1">{v ?? 0}</div>
          </div>
        ))}
      </div>

      {/* Conversion + Velocity */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-3"><Gauge className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Конверсія воронки</h2></div>
          <div className="text-4xl font-bold" style={{ color: PRIMARY }}>{an?.conversion_pct ?? 0}%</div>
          <p className="text-sm text-muted-foreground mt-1">лідів, що досягли стадії «Активний» або «Вихід».</p>
        </div>
        <div className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-3"><Clock className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Швидкість капіталу (E7)</h2></div>
          <div className="grid grid-cols-3 gap-2">
            {[['Сер. днів', vel?.avg_days_to_close], ['Найшвидше', vel?.fastest_days], ['Найповільніше', vel?.slowest_days]].map(([l, v]) => (
              <div key={l}>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</div>
                <div className="text-xl font-bold">{v != null ? v : '—'}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">Днів на закриття раунду. Закритих раундів: {vel?.closed_rounds ?? 0}.</p>
        </div>
      </div>

      {/* Funnel */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><BarChart3 className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Воронка за стадіями</h2></div>
        <div className="space-y-2" data-testid="funnel-bars">
          {funnelStages.map((s) => (
            <div key={s} className="flex items-center gap-3">
              <div className="w-32 text-sm text-muted-foreground shrink-0">{labels[s] || s}</div>
              <div className="flex-1 h-7 rounded-lg bg-muted overflow-hidden">
                <div className="h-full rounded-lg flex items-center px-2 text-xs font-semibold text-white" style={{ width: `${Math.max(6, (counts[s] || 0) / maxCount * 100)}%`, background: PRIMARY }}>{counts[s] || 0}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Rejection reasons */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><XCircle className="w-4 h-4 text-rose-600" /><h2 className="font-semibold">Причини відхилень</h2></div>
        {(an?.rejection_reasons || []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Відхилених сделок ще немає.</p>
        ) : (
          <div className="space-y-2" data-testid="rejection-reasons">
            {an.rejection_reasons.map((r, i) => (
              <div key={i} className="flex items-center justify-between text-sm border-b border-border/50 pb-2">
                <span className="text-muted-foreground">{r.reason}</span>
                <span className="font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-xs">{r.count}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Time in stage */}
      {an?.avg_time_in_stage_days && Object.keys(an.avg_time_in_stage_days).length > 0 && (
        <section className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-4"><Clock className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Середній час у стадії (днів)</h2></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(an.avg_time_in_stage_days).map(([s, d]) => (
              <div key={s} className="rounded-lg border border-border p-3">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{labels[s] || s}</div>
                <div className="text-lg font-bold">{d}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Velocity per asset */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><TrendingUp className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Раунди по об'єктах</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                <th className="text-left py-2">Об'єкт</th><th className="text-left">Раунд</th><th className="text-left">Статус</th>
                <th className="text-right">Ціль</th><th className="text-right">Залучено</th><th className="text-right">Днів</th>
              </tr>
            </thead>
            <tbody>
              {(vel?.per_asset || []).map((r, i) => (
                <tr key={i} className="border-b border-border/50">
                  <td className="py-2">{r.asset_title || r.asset_id}</td>
                  <td>{r.round_name || '—'}</td>
                  <td>{r.status || '—'}</td>
                  <td className="text-right">{formatUAH(r.target_uah)}</td>
                  <td className="text-right">{formatUAH(r.raised_uah)}</td>
                  <td className="text-right">{r.days_to_close != null ? r.days_to_close : (r.days_elapsed != null ? `${r.days_elapsed} (в роботі)` : '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
