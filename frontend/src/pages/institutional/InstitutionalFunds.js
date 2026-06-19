import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { Loader2, Landmark } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function InstitutionalFunds() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { lumen.get('/institutional/funds').then((r) => setItems(r.data.items || [])).catch(() => {}).finally(() => setLoading(false)); }, []);
  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="institutional-funds">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS</div><h1 className="text-2xl font-bold">Фонди</h1><p className="text-sm text-muted-foreground mt-1">Фонд — контейнер SPV. Інвестор отримує частку фонду, а не окремий об'єкт.</p></div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="funds-list">
        {items.map((f) => (
          <Link key={f.id} to={`/institutional/funds/${f.id}`} className="rounded-2xl border border-border bg-card p-5 hover:shadow-md transition">
            <div className="flex items-center gap-2 mb-2"><span className="w-9 h-9 rounded-lg bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center"><Landmark className="w-4 h-4" /></span><div><div className="font-semibold">{f.name}</div><div className="text-[11px] text-muted-foreground">{f.kind_label} · {f.region}</div></div></div>
            <p className="text-xs text-muted-foreground line-clamp-2">{f.strategy}</p>
            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              <div><div className="text-sm font-bold">{formatUAH(f.nav_uah)}</div><div className="text-[10px] text-muted-foreground">NAV</div></div>
              <div><div className="text-sm font-bold">{f.assets_count}</div><div className="text-[10px] text-muted-foreground">активів</div></div>
              <div><div className="text-sm font-bold">{f.funded_pct == null ? '—' : `${f.funded_pct}%`}</div><div className="text-[10px] text-muted-foreground">від цілі</div></div>
            </div>
          </Link>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Активних фондів немає.</p>}
      </div>
    </div>
  );
}
