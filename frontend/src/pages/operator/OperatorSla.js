import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { StatusPill } from '@/lib/operatorUi';
import { Loader2, Activity } from 'lucide-react';

export default function OperatorSla() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/operator/sla').then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  const items = data?.items || [];

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="operator-sla">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="w-5 h-5 text-[#2E5D4F]" /> SLA звітності</h1>
        <p className="text-sm text-muted-foreground mt-1">Правила: 30 днів — попередження, 60 — критично, 90 — ескалація.</p>
      </div>

      {data && (
        <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4">
          <span className="text-sm text-muted-foreground">Загальний статус:</span>
          <StatusPill status={data.overall} label={data.overall_label} />
          <div className="ml-auto flex gap-4 text-xs text-muted-foreground">
            {['ok','warning','critical','escalation'].map((k) => <span key={k}>{k}: <b className="text-foreground">{data.counts[k]}</b></span>)}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr><th className="text-left font-medium px-4 py-2.5">Об'єкт</th><th className="text-left font-medium px-4 py-2.5">Останній звіт</th><th className="text-right font-medium px-4 py-2.5">Днів тому</th><th className="text-right font-medium px-4 py-2.5">Статус</th></tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.asset_id} className="border-t border-border">
                <td className="px-4 py-2.5 font-medium">{i.asset_title}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{i.last_report_at ? formatDateUk(i.last_report_at) : 'ніколи'}</td>
                <td className="px-4 py-2.5 text-right">{i.days_since_report == null ? '—' : i.days_since_report}</td>
                <td className="px-4 py-2.5 text-right"><StatusPill status={i.status} label={i.status_label} /></td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">Об'єктів немає.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
