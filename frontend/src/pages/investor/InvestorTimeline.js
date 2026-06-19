import { useEffect, useState } from 'react';
import { lumen, formatDateUk, formatUAH } from '@/lib/lumenApi';
import { Activity, Loader2, Award, FileSignature, Coins, Repeat, Vote, ShieldCheck } from 'lucide-react';

const KIND_META = {
  certificate: { icon: Award, color: 'text-emerald-600 bg-emerald-50' },
  investment: { icon: Coins, color: 'text-sky-600 bg-sky-50' },
  payout: { icon: Coins, color: 'text-amber-600 bg-amber-50' },
  secondary_trade: { icon: Repeat, color: 'text-violet-600 bg-violet-50' },
  governance: { icon: Vote, color: 'text-indigo-600 bg-indigo-50' },
  compliance: { icon: ShieldCheck, color: 'text-slate-600 bg-slate-100' },
  contract: { icon: FileSignature, color: 'text-slate-600 bg-slate-100' },
  system: { icon: Activity, color: 'text-slate-500 bg-slate-100' },
};

export default function InvestorTimeline() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/investor/timeline').then((r) => setData(r.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const items = data?.items || [];

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-5" data-testid="investor-timeline">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Audit · G14</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="w-5 h-5 text-[#2E5D4F]" /> Моя історія</h1>
        <p className="text-sm text-muted-foreground mt-1">Сертифікати, інвестиції, виплати, комплаєнс і голосування — в одній стрічці.</p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-border p-10 text-center text-sm text-muted-foreground">
          <Activity className="w-8 h-8 mx-auto mb-3 opacity-40" />Подій ще немає.
        </div>
      ) : (
        <ol className="relative border-l border-border ml-3" data-testid="timeline-list">
          {items.map((e, i) => {
            const meta = KIND_META[e.kind] || KIND_META.system;
            const Icon = meta.icon;
            return (
              <li key={i} className="mb-6 ml-5">
                <span className={`absolute -left-3 flex items-center justify-center w-6 h-6 rounded-full ${meta.color}`}>
                  <Icon className="w-3.5 h-3.5" />
                </span>
                <div className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-sm">{e.event_label || e.event}</h3>
                    <time className="text-[11px] text-muted-foreground">{formatDateUk(e.at)}</time>
                  </div>
                  {e.summary && <p className="text-sm text-muted-foreground mt-1">{e.summary}</p>}
                  {e.amount_uah ? <p className="mt-1 text-sm font-semibold text-[#2E5D4F]">{formatUAH(e.amount_uah)}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
