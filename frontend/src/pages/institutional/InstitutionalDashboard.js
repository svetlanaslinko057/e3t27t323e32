import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { KpiCard } from '@/lib/operatorUi';
import InstitutionalGate from './InstitutionalGate';
import { Loader2, Landmark, Users2, ShieldCheck, AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function InstitutionalDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [gated, setGated] = useState(false);

  useEffect(() => {
    lumen.get('/institutional/dashboard')
      .then((r) => setData(r.data))
      .catch((e) => { if (e?.response?.status === 403) setGated(true); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (gated) return <InstitutionalGate />;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Не вдалося завантажити.</div>;

  const { portfolio: p, funds, syndicates, compliance: c } = data;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="institutional-dashboard">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional Ownership OS · Phase G</div>
        <h1 className="text-2xl font-bold">Інституційний огляд</h1>
        <p className="text-sm text-muted-foreground mt-1">Сегмент: <b className="text-foreground">{data.segment_label}</b></p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Вартість портфеля" value={formatUAH(p.total_value_uah)} accent="#2E5D4F" />
        <KpiCard label="Активів" value={p.assets_count} />
        <KpiCard label="SPV" value={p.spv_count} />
        <KpiCard label="Фондів (мої SPV)" value={p.funds.length} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-3"><h2 className="font-semibold flex items-center gap-2"><Landmark className="w-4 h-4 text-[#2E5D4F]" /> Доступні фонди</h2><Link to="/institutional/funds" className="text-xs text-[#2E5D4F] hover:underline">Усі →</Link></div>
          <div className="space-y-2">
            {funds.map((f) => (
              <Link key={f.id} to={`/institutional/funds/${f.id}`} className="block rounded-xl border border-border p-3 hover:bg-muted/50">
                <div className="flex items-center justify-between"><span className="text-sm font-medium">{f.name}</span><span className="text-sm font-semibold">{formatUAH(f.nav_uah)}</span></div>
                <div className="text-[11px] text-muted-foreground">{f.kind_label} · {f.assets_count} активів · ціль {formatUAH(f.target_size_uah)}</div>
              </Link>
            ))}
            {funds.length === 0 && <p className="text-sm text-muted-foreground">Фондів немає.</p>}
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-3"><h2 className="font-semibold flex items-center gap-2"><Users2 className="w-4 h-4 text-[#2E5D4F]" /> Синдикати</h2><Link to="/institutional/syndicates" className="text-xs text-[#2E5D4F] hover:underline">Усі →</Link></div>
          <div className="space-y-2">
            {syndicates.map((s) => (
              <Link key={s.id} to="/institutional/syndicates" className="block rounded-xl border border-border p-3 hover:bg-muted/50">
                <div className="flex items-center justify-between"><span className="text-sm font-medium">{s.title}</span><span className="text-xs">{s.progress_pct}%</span></div>
                <div className="h-1.5 rounded-full bg-muted mt-2 overflow-hidden"><div className="h-full bg-[#2E5D4F]" style={{ width: `${Math.min(100, s.progress_pct)}%` }} /></div>
              </Link>
            ))}
            {syndicates.length === 0 && <p className="text-sm text-muted-foreground">Синдикатів немає.</p>}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-[#2E5D4F]" /> Комплаєнс-статус</h2>
        <div className="flex flex-wrap gap-6 text-sm">
          <div><div className="text-[11px] uppercase text-muted-foreground">Сегмент</div><div className="font-semibold">{c.segment_label}</div></div>
          <div><div className="text-[11px] uppercase text-muted-foreground">Ліміт чека</div><div className="font-semibold">{c.max_ticket_uah == null ? 'Без ліміту' : formatUAH(c.max_ticket_uah)}</div></div>
          <div><div className="text-[11px] uppercase text-muted-foreground">UBO</div><div className="font-semibold flex items-center gap-1">{c.ubo_declared ? <span className="text-emerald-600">Задекларовано</span> : <span className="text-amber-600 inline-flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" />Потрібно</span>}</div></div>
        </div>
        {c.requires_ubo && !c.ubo_declared && <Link to="/institutional/ubo" className="inline-block mt-3 text-xs text-[#2E5D4F] hover:underline">Задекларувати бенефіціара →</Link>}
      </div>

      {p.holdings.length > 0 && (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-5 py-3 border-b border-border font-semibold">Мій портфель за SPV</div>
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground"><tr><th className="text-left font-medium px-4 py-2">Актив</th><th className="text-left font-medium px-4 py-2">SPV</th><th className="text-right font-medium px-4 py-2">Частка</th><th className="text-right font-medium px-4 py-2">Вартість</th></tr></thead>
            <tbody>
              {p.holdings.map((h) => (
                <tr key={h.asset_id} className="border-t border-border"><td className="px-4 py-2 font-medium">{h.asset_title}</td><td className="px-4 py-2 text-muted-foreground">{h.spv_name}</td><td className="px-4 py-2 text-right">{formatPercent(h.ownership_percent)}</td><td className="px-4 py-2 text-right">{formatUAH(h.value_uah)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
