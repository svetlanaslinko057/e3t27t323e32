import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatUAH } from '@/lib/lumenApi';
import { Loader2, Landmark, Plus, X, Trash2 } from 'lucide-react';

const KINDS = { residential: 'Житловий', commercial: 'Комерційний', logistics: 'Логістичний', mixed: 'Змішаний', land: 'Земельний' };

export default function AdminFunds() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: '', kind: 'mixed', region: '', target_size_uah: '', strategy: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try { const r = await lumen.get('/admin/institutional/funds'); setItems(r.data.items || []); }
    catch (_e) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name.trim()) { setErr('Вкажіть назву'); return; }
    setBusy(true); setErr('');
    try { await lumen.post('/admin/institutional/funds', { ...form, target_size_uah: form.target_size_uah ? Number(form.target_size_uah) : null }); setForm({ name: '', kind: 'mixed', region: '', target_size_uah: '', strategy: '' }); load(); }
    catch (e) { setErr(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };
  const remove = async (id) => { if (!window.confirm('Видалити фонд?')) return; try { await lumen.delete(`/admin/institutional/funds/${id}`); load(); } catch (_e) {} };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-funds">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G3</div><h1 className="text-2xl font-bold">Фонди</h1><p className="text-sm text-muted-foreground mt-1">Фонд — контейнер SPV. NAV рахується з вартості базових активів.</p></div>
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Новий фонд</h2></div>
        <div className="grid md:grid-cols-5 gap-2 items-end">
          <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Назва</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="fund-name" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
          <div><label className="text-[11px] uppercase text-muted-foreground">Тип</label><select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">{Object.entries(KINDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
          <div><label className="text-[11px] uppercase text-muted-foreground">Ціль, ₾</label><input type="number" value={form.target_size_uah} onChange={(e) => setForm({ ...form, target_size_uah: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" /></div>
          <button onClick={create} disabled={busy} data-testid="fund-create" className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: '#2E5D4F' }}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Створити</button>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
      </section>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="admin-funds-list">
        {items.map((f) => (
          <div key={f.id} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-start justify-between">
              <button onClick={() => setOpenId(f.id)} data-testid={`fund-open-${f.id}`} className="flex items-center gap-2 text-left"><span className="w-9 h-9 rounded-lg bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center"><Landmark className="w-4 h-4" /></span><div><div className="font-semibold text-sm hover:underline">{f.name}</div><div className="text-[11px] text-muted-foreground">{f.kind_label} · {f.status_label}</div></div></button>
              <button onClick={() => remove(f.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-3 text-center"><div><div className="text-sm font-bold">{formatUAH(f.nav_uah)}</div><div className="text-[10px] text-muted-foreground">NAV</div></div><div><div className="text-sm font-bold">{f.spv_ids.length}</div><div className="text-[10px] text-muted-foreground">SPV</div></div><div><div className="text-sm font-bold">{f.funded_pct == null ? '—' : `${f.funded_pct}%`}</div><div className="text-[10px] text-muted-foreground">ціль</div></div></div>
            <button onClick={() => setOpenId(f.id)} className="text-xs font-medium text-[#2E5D4F] hover:underline mt-3">Керувати SPV →</button>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Фондів ще немає.</p>}
      </div>
      {openId && <FundDrawer fundId={openId} onClose={() => setOpenId(null)} onChanged={load} />}
    </div>
  );
}

function FundDrawer({ fundId, onClose, onChanged }) {
  const [d, setD] = useState(null);
  const [pick, setPick] = useState('');
  const load = useCallback(async () => { try { const r = await lumen.get(`/admin/institutional/funds/${fundId}`); setD(r.data); } catch (_e) {} }, [fundId]);
  useEffect(() => { load(); }, [load]);
  const refresh = () => { load(); onChanged?.(); };
  const addSpv = async () => { if (!pick) return; await lumen.post(`/admin/institutional/funds/${fundId}/spvs`, { spv_id: pick }); setPick(''); refresh(); };
  const removeSpv = async (sid) => { await lumen.delete(`/admin/institutional/funds/${fundId}/spvs/${sid}`); refresh(); };
  const setStatus = async (status) => { await lumen.patch(`/admin/institutional/funds/${fundId}`, { status }); refresh(); };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex justify-end" onClick={onClose}>
      <div className="bg-background w-full max-w-xl h-full overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="fund-drawer">
        {!d ? <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div> : (
          <div className="p-6 space-y-5">
            <div className="flex items-start justify-between"><div><h2 className="text-lg font-bold">{d.name}</h2><div className="text-sm text-muted-foreground">NAV {formatUAH(d.nav_uah)} · {d.assets_count} активів</div></div><button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button></div>
            <div className="flex gap-2">{['forming', 'active', 'closed'].map((s) => <button key={s} onClick={() => setStatus(s)} data-testid={`fund-status-${s}`} className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${d.status === s ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border hover:bg-muted'}`}>{s}</button>)}</div>
            <div>
              <h3 className="font-semibold text-sm mb-2">SPV у фонді</h3>
              <div className="space-y-2" data-testid="fund-spvs">{(d.holdings || []).map((h) => (<div key={h.spv_id} className="flex items-center justify-between rounded-xl border border-border p-3"><div><div className="text-sm font-medium">{h.asset_title}</div><div className="text-[11px] text-muted-foreground">{h.spv_name} · {formatUAH(h.value_uah)}</div></div><button onClick={() => removeSpv(h.spv_id)} className="text-xs text-rose-600 hover:underline">Вилучити</button></div>))}{(d.holdings || []).length === 0 && <p className="text-sm text-muted-foreground">Порожньо.</p>}</div>
            </div>
            <div className="flex gap-2 items-end">
              <div className="flex-1"><label className="text-[11px] uppercase text-muted-foreground">Додати SPV</label><select value={pick} onChange={(e) => setPick(e.target.value)} data-testid="fund-add-spv-select" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1"><option value="">— SPV —</option>{(d.available_spvs || []).map((s) => <option key={s.id} value={s.id}>{s.name} ({s.asset_title})</option>)}</select></div>
              <button onClick={addSpv} disabled={!pick} data-testid="fund-add-spv-btn" className="h-10 px-4 rounded-lg text-sm font-medium text-white" style={{ background: '#2E5D4F' }}>Додати</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
