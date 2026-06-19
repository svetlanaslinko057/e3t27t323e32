import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { Loader2, Vote, Plus, Lock } from 'lucide-react';

export default function AdminGovernance() {
  const [items, setItems] = useState([]);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ scope: 'asset', scope_id: '', title: '', description: '', days_open: 14 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([lumen.get('/governance/proposals'), lumen.get('/admin/assets')]);
      setItems(p.data.items || []);
      const list = a.data.items || []; setAssets(list);
      setForm((f) => ({ ...f, scope_id: f.scope_id || (list[0]?.id || '') }));
    } catch (_e) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.title.trim() || !form.scope_id) { setErr("Заповніть назву та об'єкт"); return; }
    setBusy(true); setErr('');
    try { await lumen.post('/admin/institutional/governance/proposals', { ...form, days_open: Number(form.days_open) }); setForm((f) => ({ ...f, title: '', description: '' })); load(); }
    catch (e) { setErr(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };
  const close = async (pid) => { await lumen.post(`/admin/institutional/governance/proposals/${pid}/close`); load(); };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="admin-governance">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G7</div><h1 className="text-2xl font-bold flex items-center gap-2"><Vote className="w-5 h-5 text-[#2E5D4F]" /> Governance</h1><p className="text-sm text-muted-foreground mt-1">Голоси зважені за частками. Оператор не може голосувати по власному об'єкту.</p></div>
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Нова пропозиція</h2></div>
        <div className="grid md:grid-cols-4 gap-2 items-end">
          <div><label className="text-[11px] uppercase text-muted-foreground">Scope</label><select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1"><option value="asset">Актив</option></select></div>
          <div><label className="text-[11px] uppercase text-muted-foreground">Об'єкт</label><select value={form.scope_id} onChange={(e) => setForm({ ...form, scope_id: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">{assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}</select></div>
          <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Питання</label><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="proposal-title" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
        <button onClick={create} disabled={busy} data-testid="proposal-create" className="mt-3 h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Створити</button>
      </section>
      <div className="space-y-3" data-testid="proposals-list">
        {items.map((p) => (
          <div key={p.id} className="rounded-2xl border border-border bg-card p-5">
            <div className="flex items-start justify-between"><div><div className="font-semibold">{p.title}</div><div className="text-[11px] text-muted-foreground">{p.scope_label} · {p.voters} голосів · до {formatDateUk(p.closes_at)}</div></div>{p.status === 'open' ? <button onClick={() => close(p.id)} data-testid={`proposal-close-${p.id}`} className="text-xs text-rose-600 hover:underline inline-flex items-center gap-1"><Lock className="w-3 h-3" />Закрити</button> : <span className="text-[11px] text-muted-foreground">Закрито</span>}</div>
            <div className="mt-3 space-y-1.5">{p.results.map((r) => (<div key={r.option}><div className="flex justify-between text-xs mb-0.5"><span>{r.option}</span><span>{r.pct}%</span></div><div className="h-1.5 rounded-full bg-muted overflow-hidden"><div className="h-full bg-[#2E5D4F]" style={{ width: `${r.pct}%` }} /></div></div>))}</div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Пропозицій ще немає.</p>}
      </div>
    </div>
  );
}
