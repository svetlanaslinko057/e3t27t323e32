import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import InstitutionalGate from './InstitutionalGate';
import { Loader2, UserCheck, Plus, ShieldAlert } from 'lucide-react';

export default function InstitutionalUbo() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [gated, setGated] = useState(false);
  const [form, setForm] = useState({ ubo_name: '', relationship: 'self', ownership_pct: 100, is_pep: false, country: 'UA' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try { const r = await lumen.get('/institutional/me/ubo'); setItems(r.data.items || []); }
    catch (e) { if (e?.response?.status === 403) setGated(true); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.ubo_name.trim()) { setErr("Вкажіть ім'я бенефіціара"); return; }
    setBusy(true); setErr('');
    try { await lumen.post('/institutional/me/ubo', { ...form, ownership_pct: Number(form.ownership_pct) }); setForm({ ubo_name: '', relationship: 'self', ownership_pct: 100, is_pep: false, country: 'UA' }); load(); }
    catch (e) { setErr(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (gated) return <InstitutionalGate />;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6" data-testid="institutional-ubo">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G5</div><h1 className="text-2xl font-bold flex items-center gap-2"><UserCheck className="w-5 h-5 text-[#2E5D4F]" /> Кінцеві бенефіціари (UBO)</h1><p className="text-sm text-muted-foreground mt-1">Декларація кінцевих бенефіціарних власників для комплаєнсу.</p></div>
      <div className="rounded-2xl border border-border bg-card p-5 space-y-2">
        <div className="grid md:grid-cols-2 gap-2">
          <input value={form.ubo_name} onChange={(e) => setForm({ ...form, ubo_name: e.target.value })} data-testid="ubo-name" placeholder="Ім'я бенефіціара" className="h-10 rounded-lg border border-border bg-background px-2 text-sm" />
          <select value={form.relationship} onChange={(e) => setForm({ ...form, relationship: e.target.value })} className="h-10 rounded-lg border border-border bg-background px-2 text-sm">
            <option value="self">Себе</option><option value="shareholder">Акціонер</option><option value="director">Директор</option><option value="trust">Траст</option>
          </select>
          <input type="number" value={form.ownership_pct} onChange={(e) => setForm({ ...form, ownership_pct: e.target.value })} placeholder="% володіння" className="h-10 rounded-lg border border-border bg-background px-2 text-sm" />
          <label className="flex items-center gap-2 text-sm px-2"><input type="checkbox" checked={form.is_pep} onChange={(e) => setForm({ ...form, is_pep: e.target.checked })} /> Публічна особа (PEP)</label>
        </div>
        {err && <p className="text-xs text-rose-600">{err}</p>}
        <button onClick={add} disabled={busy} data-testid="ubo-add" className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Додати</button>
      </div>
      <div className="space-y-2" data-testid="ubo-list">
        {items.map((u) => (
          <div key={u.id} className="flex items-center justify-between rounded-xl border border-border bg-card p-4">
            <div><div className="text-sm font-medium">{u.ubo_name}</div><div className="text-[11px] text-muted-foreground">{u.relationship} · {u.ownership_pct}% · {u.country}</div></div>
            <div className="flex items-center gap-2">{u.is_pep && <span className="text-[11px] text-amber-600 inline-flex items-center gap-1"><ShieldAlert className="w-3.5 h-3.5" />PEP</span>}<span className={`text-[11px] ${u.verified ? 'text-emerald-600' : 'text-muted-foreground'}`}>{u.verified ? 'Підтверджено' : 'На розгляді'}</span></div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Бенефіціарів ще не задекларовано.</p>}
      </div>
    </div>
  );
}
