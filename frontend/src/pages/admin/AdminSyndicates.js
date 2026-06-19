import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatUAH } from '@/lib/lumenApi';
import { Loader2, Plus, Crown } from 'lucide-react';

export default function AdminSyndicates() {
  const [items, setItems] = useState([]);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ title: '', asset_id: '', target_uah: '', lead_pct: 20, min_ticket_uah: 50000 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([lumen.get('/admin/institutional/syndicates'), lumen.get('/admin/assets')]);
      setItems(s.data.items || []);
      const list = a.data.items || []; setAssets(list);
      setForm((f) => ({ ...f, asset_id: f.asset_id || (list[0]?.id || '') }));
    } catch (_e) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.title.trim() || !form.asset_id || !form.target_uah) { setErr('Заповніть назву, актив та ціль'); return; }
    setBusy(true); setErr('');
    try { await lumen.post('/admin/institutional/syndicates', { ...form, target_uah: Number(form.target_uah), lead_pct: Number(form.lead_pct), min_ticket_uah: Number(form.min_ticket_uah) }); setForm((f) => ({ ...f, title: '', target_uah: '' })); load(); }
    catch (e) { setErr(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="admin-syndicates">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G4</div><h1 className="text-2xl font-bold">Синдикати</h1><p className="text-sm text-muted-foreground mt-1">Lead-інвестор резервує частку, решта приєднується.</p></div>
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Новий синдикат</h2></div>
        <div className="grid md:grid-cols-5 gap-2 items-end">
          <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Назва</label><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="synd-title" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
          <div><label className="text-[11px] uppercase text-muted-foreground">Актив</label><select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">{assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}</select></div>
          <div><label className="text-[11px] uppercase text-muted-foreground">Ціль, ₾</label><input type="number" value={form.target_uah} onChange={(e) => setForm({ ...form, target_uah: e.target.value })} data-testid="synd-target" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
          <button onClick={create} disabled={busy} data-testid="synd-create" className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: '#2E5D4F' }}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Створити</button>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
      </section>
      <div className="space-y-3" data-testid="admin-syndicates-list">
        {items.map((s) => (
          <div key={s.id} className="rounded-2xl border border-border bg-card p-5">
            <div className="flex items-start justify-between"><div><div className="font-semibold">{s.title}</div><div className="text-[11px] text-muted-foreground">{s.asset_title} · {s.state_label}</div></div><div className="text-right"><div className="text-sm font-bold">{formatUAH(s.raised_uah)} / {formatUAH(s.target_uah)}</div><div className="text-[11px] text-muted-foreground">{s.progress_pct}%</div></div></div>
            <div className="h-2 rounded-full bg-muted mt-3 overflow-hidden"><div className="h-full bg-[#2E5D4F]" style={{ width: `${Math.min(100, s.progress_pct)}%` }} /></div>
            <div className="mt-3 space-y-1">{s.participants.map((p) => (<div key={p.id} className="flex items-center justify-between text-xs"><span className="inline-flex items-center gap-1">{p.role === 'lead' && <Crown className="w-3 h-3 text-amber-500" />}{p.investor_name}</span><span>{formatUAH(p.amount_uah)} · {p.status}</span></div>))}</div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Синдикатів ще немає.</p>}
      </div>
    </div>
  );
}
