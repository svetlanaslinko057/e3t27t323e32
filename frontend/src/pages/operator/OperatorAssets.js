import { useEffect, useState } from 'react';
import { lumen, formatPercent } from '@/lib/lumenApi';
import { StatusPill } from '@/lib/operatorUi';
import { Loader2, Building2, Users, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function OperatorAssets() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/operator/assets').then((r) => setItems(r.data.items || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="operator-assets">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS</div>
        <h1 className="text-2xl font-bold">Мої об'єкти</h1>
        <p className="text-sm text-muted-foreground mt-1">Активи під вашим управлінням. SLA рахується від дати останнього звіту.</p>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="operator-assets-list">
        {items.map((a) => (
          <div key={a.id} className="rounded-2xl border border-border bg-card overflow-hidden">
            {a.cover_url
              ? <img src={a.cover_url} alt={a.title} className="h-32 w-full object-cover" />
              : <div className="h-32 w-full bg-muted flex items-center justify-center"><Building2 className="w-8 h-8 text-muted-foreground" /></div>}
            <div className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div><div className="font-semibold text-sm">{a.title}</div><div className="text-[11px] text-muted-foreground">{a.location || a.category || '—'}</div></div>
                <StatusPill status={a.sla_status} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div><div className="text-sm font-semibold">{formatPercent(a.occupancy_percent)}</div><div className="text-[10px] text-muted-foreground">заповн.</div></div>
                <div><div className="text-sm font-semibold">{formatPercent(a.target_yield)}</div><div className="text-[10px] text-muted-foreground">дохідн.</div></div>
                <div className="flex flex-col items-center"><div className="text-sm font-semibold flex items-center gap-1"><Users className="w-3 h-3" />{a.investors_count}</div><div className="text-[10px] text-muted-foreground">інвест.</div></div>
              </div>
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Ост. звіт: {a.last_report_days == null ? 'ніколи' : `${a.last_report_days} дн. тому`}</span>
                <Link to="/operator/reports" className="inline-flex items-center gap-1 text-[#2E5D4F] font-medium hover:underline"><FileText className="w-3 h-3" /> Звітувати</Link>
              </div>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Вам ще не призначено жодного об'єкта.</p>}
      </div>
    </div>
  );
}
