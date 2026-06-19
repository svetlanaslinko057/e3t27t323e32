import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { FileText, Download, Loader2, Plus, Building2, BarChart3, Landmark, Trash2 } from 'lucide-react';

const KIND_META = {
  asset_factsheet: { icon: Building2, label: 'Факт-лист активу' },
  quarterly: { icon: BarChart3, label: 'Квартальний звіт' },
  fund_report: { icon: Landmark, label: 'Звіт фонду' },
};

export default function AdminReportBuilder() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState('asset_factsheet');
  const [assets, setAssets] = useState([]);
  const [funds, setFunds] = useState([]);
  const [entityId, setEntityId] = useState('');
  const [period, setPeriod] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a, f] = await Promise.all([
        lumen.get('/admin/report-builder/list'),
        lumen.get('/admin/assets'),
        lumen.get('/admin/institutional/funds'),
      ]);
      setItems(r.data.items || []);
      setAssets(a.data.items || a.data || []);
      setFunds(f.data.items || []);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const body = { kind };
      if (kind === 'asset_factsheet' || kind === 'fund_report') body.entity_id = entityId || null;
      if (kind === 'quarterly') body.period = period || undefined;
      const r = await lumen.post('/admin/report-builder/generate', body);
      setMsg(`✓ Згенеровано: ${r.data.title}`);
      load();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  const dl = (rid) => window.open(`${lumen.defaults.baseURL}/reports/${rid}/pdf`, '_blank');

  const del = async (rid) => {
    if (!window.confirm('Видалити звіт?')) return;
    try { await lumen.delete(`/admin/report-builder/${rid}`); load(); } catch (_e) {}
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5" data-testid="admin-report-builder">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reporting OS · G12</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileText className="w-5 h-5 text-[#2E5D4F]" /> Report Builder</h1>
        <p className="text-sm text-muted-foreground mt-1">Факт-листи активів, квартальні та фондові звіти. PDF генерується на льоту з реальних колекцій.</p>
      </div>

      <section className="rounded-2xl border border-border bg-card p-5" data-testid="report-builder-form">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Новий звіт</h2></div>
        <div className="grid md:grid-cols-4 gap-3 items-end">
          <div><label className="text-[11px] uppercase text-muted-foreground">Тип звіту</label>
            <select value={kind} onChange={(e) => { setKind(e.target.value); setEntityId(''); }} data-testid="rb-kind"
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              <option value="asset_factsheet">Факт-лист активу</option>
              <option value="quarterly">Квартальний звіт</option>
              <option value="fund_report">Звіт фонду</option>
            </select>
          </div>
          {kind === 'asset_factsheet' && (
            <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Актив</label>
              <select value={entityId} onChange={(e) => setEntityId(e.target.value)} data-testid="rb-asset"
                className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
                <option value="">— виберіть актив —</option>
                {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
              </select>
            </div>
          )}
          {kind === 'fund_report' && (
            <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Фонд</label>
              <select value={entityId} onChange={(e) => setEntityId(e.target.value)} data-testid="rb-fund"
                className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
                <option value="">— виберіть фонд —</option>
                {funds.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
          )}
          {kind === 'quarterly' && (
            <div className="md:col-span-2"><label className="text-[11px] uppercase text-muted-foreground">Період (напр. 2026Q2)</label>
              <input value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="rb-period" placeholder="Авто: поточний квартал"
                className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
            </div>
          )}
          <button onClick={generate} disabled={busy} data-testid="rb-generate"
            className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: '#2E5D4F' }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Згенерувати
          </button>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
        {msg && <p className="text-xs text-emerald-600 mt-2">{msg}</p>}
      </section>

      <section className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="report-list">
        <div className="px-5 py-3 border-b border-border font-semibold flex items-center justify-between">
          <span>Бібліотека звітів</span>
          <span className="text-xs text-muted-foreground">{items.length} всього</span>
        </div>
        {loading ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
          : items.length === 0 ? <div className="py-12 text-center text-sm text-muted-foreground">Звітів ще немає. Створіть перший вище.</div>
            : <table className="w-full text-sm"><thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">Назва</th><th className="text-left px-4 py-2">Тип</th><th className="text-left px-4 py-2">Період</th><th className="text-left px-4 py-2">Створено</th><th className="text-right px-4 py-2">Дії</th></tr></thead>
              <tbody>{items.map((r) => { const meta = KIND_META[r.kind] || {}; const Icon = meta.icon || FileText; return (
                <tr key={r.id} className="border-t border-border" data-testid={`rb-row-${r.id}`}>
                  <td className="px-4 py-2"><div className="flex items-center gap-2"><Icon className="w-4 h-4 text-muted-foreground" /><span className="font-medium">{r.title}</span></div></td>
                  <td className="px-4 py-2 text-muted-foreground">{meta.label}</td>
                  <td className="px-4 py-2 text-muted-foreground">{r.period || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{formatDateUk(r.created_at)}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button onClick={() => dl(r.id)} data-testid={`rb-pdf-${r.id}`} className="text-[#2E5D4F] hover:underline inline-flex items-center gap-1"><Download className="w-3.5 h-3.5" />PDF</button>
                      <button onClick={() => del(r.id)} className="text-rose-600 hover:underline inline-flex items-center gap-1"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>); })}
              </tbody></table>}
      </section>
    </div>
  );
}
