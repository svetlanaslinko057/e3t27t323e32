import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { Loader2, UserCheck, ShieldAlert, Trash2 } from 'lucide-react';

export default function AdminUbo() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { try { const r = await lumen.get('/admin/institutional/ubo'); setData(r.data); } catch (_e) {} finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const del = async (id) => { await lumen.delete(`/admin/institutional/ubo/${id}`); load(); };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  const rows = data?.items || [];
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="admin-ubo">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G5</div><h1 className="text-2xl font-bold flex items-center gap-2"><UserCheck className="w-5 h-5 text-[#2E5D4F]" /> Реєстр бенефіціарів (UBO)</h1><p className="text-sm text-muted-foreground mt-1">Хто кінцевий бенефіціар за кожним власником сертифікатів.</p></div>
      <div className="grid grid-cols-3 gap-3"><Stat label="Власників" value={data?.total_holders ?? 0} /><Stat label="З UBO" value={data?.with_ubo ?? 0} /><Stat label="PEP" value={data?.pep_count ?? 0} accent={(data?.pep_count ?? 0) > 0} /></div>
      <div className="space-y-3" data-testid="ubo-registry">
        {rows.map((r) => (
          <div key={r.investor_id} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-center justify-between"><div><div className="font-medium text-sm">{r.investor_name}</div><div className="text-[11px] text-muted-foreground">Вартість {formatUAH(r.value_uah)}</div></div>{!r.has_ubo && <span className="text-[11px] text-amber-600 inline-flex items-center gap-1"><ShieldAlert className="w-3.5 h-3.5" />UBO не задекларовано</span>}</div>
            {r.declared.length > 0 && <div className="mt-2 space-y-1">{r.declared.map((u) => (<div key={u.id} className="flex items-center justify-between text-xs rounded-lg bg-muted/40 px-3 py-1.5"><span>{u.ubo_name} · {u.relationship} · {u.ownership_pct}%{u.is_pep ? ' · PEP' : ''}</span><button onClick={() => del(u.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-3.5 h-3.5" /></button></div>))}</div>}
          </div>
        ))}
        {rows.length === 0 && <p className="text-sm text-muted-foreground">Власників сертифікатів немає.</p>}
      </div>
    </div>
  );
}
function Stat({ label, value, accent }) { return <div className="rounded-2xl border border-border bg-card p-4"><div className="text-[11px] uppercase text-muted-foreground">{label}</div><div className={`text-2xl font-bold ${accent ? 'text-amber-600' : ''}`}>{value}</div></div>; }
