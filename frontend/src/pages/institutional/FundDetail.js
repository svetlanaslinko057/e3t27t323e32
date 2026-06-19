import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { VerifiedBadge } from '@/lib/operatorUi';
import { Loader2, Landmark, Building2, ArrowLeft } from 'lucide-react';
import { trackEvent } from '@/lib/activityTracker';

export default function FundDetail() {
  const { fundId } = useParams();
  const [f, setF] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { lumen.get(`/institutional/funds/${fundId}`).then((r) => { setF(r.data); try { trackEvent('fund_view', { fund_id: fundId, surface: 'institutional', title: r.data?.name }); } catch (_) {} }).catch(() => {}).finally(() => setLoading(false)); }, [fundId]);
  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (!f) return <div className="p-6 text-sm text-muted-foreground">Фонд не знайдено.</div>;
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="fund-detail">
      <Link to="/institutional/funds" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="w-4 h-4" /> Усі фонди</Link>
      <div className="rounded-2xl border border-border bg-card p-6">
        <div className="flex items-start gap-3">
          <span className="w-12 h-12 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center"><Landmark className="w-6 h-6" /></span>
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{f.name}</h1>
            <div className="text-sm text-muted-foreground">{f.kind_label} · {f.region} · {f.status_label}</div>
            {f.manager && <div className="mt-2 flex items-center gap-2 text-sm">Керуючий: <b>{f.manager.name}</b> <VerifiedBadge verified={f.manager.verified} status={f.manager.verified ? 'verified' : 'applied'} /></div>}
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-4">{f.description}</p>
        <div className="grid grid-cols-3 gap-3 mt-4">
          <Stat label="NAV (вартість)" value={formatUAH(f.nav_uah)} accent />
          <Stat label="Цільовий розмір" value={formatUAH(f.target_size_uah)} />
          <Stat label="Зібрано від цілі" value={f.funded_pct == null ? '—' : `${f.funded_pct}%`} />
        </div>
      </div>
      <div>
        <h2 className="font-semibold mb-3">Склад фонду (SPV → активи)</h2>
        <div className="space-y-2" data-testid="fund-holdings">
          {(f.holdings || []).map((h) => (
            <div key={h.spv_id} className="flex items-center justify-between rounded-xl border border-border bg-card p-4">
              <div className="flex items-center gap-3"><Building2 className="w-4 h-4 text-muted-foreground" /><div><div className="text-sm font-medium">{h.asset_title}</div><div className="text-[11px] text-muted-foreground">{h.spv_name} · {h.category}</div></div></div>
              <div className="text-sm font-semibold">{formatUAH(h.value_uah)}</div>
            </div>
          ))}
          {(f.holdings || []).length === 0 && <p className="text-sm text-muted-foreground">Фонд ще не містить SPV.</p>}
        </div>
      </div>
    </div>
  );
}
function Stat({ label, value, accent }) {
  return <div className="rounded-xl border border-border bg-card p-3"><div className="text-[11px] uppercase text-muted-foreground">{label}</div><div className={`text-lg font-bold ${accent ? 'text-[#2E5D4F]' : ''}`}>{value}</div></div>;
}
