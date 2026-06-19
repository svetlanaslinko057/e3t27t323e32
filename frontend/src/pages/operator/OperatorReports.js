import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { Loader2, FileText, Plus, Send, CheckCircle2 } from 'lucide-react';

export default function OperatorReports() {
  const [reports, setReports] = useState([]);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ asset_id: '', title: '', period_label: '', summary: '', report_type: 'operational' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');

  const load = useCallback(async () => {
    try {
      const [r, a] = await Promise.all([lumen.get('/operator/reports'), lumen.get('/operator/assets')]);
      setReports(r.data.items || []);
      const list = a.data.items || [];
      setAssets(list);
      setForm((f) => ({ ...f, asset_id: f.asset_id || (list[0]?.id || '') }));
    } catch (_e) { /* noop */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!form.asset_id) { setErr('Оберіть об\u0027єкт'); return; }
    if (!form.title.trim()) { setErr('Вкажіть заголовок звіту'); return; }
    setBusy(true); setErr(''); setOk('');
    try {
      await lumen.post(`/operator/assets/${form.asset_id}/reports`, {
        title: form.title.trim(), period_label: form.period_label || null,
        summary: form.summary || null, report_type: form.report_type,
      });
      setOk('Звіт опубліковано — SLA оновлено.');
      setForm((f) => ({ ...f, title: '', period_label: '', summary: '' }));
      load();
    } catch (e) { setErr(lumenError(e, 'Не вдалося опублікувати звіт')); } finally { setBusy(false); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="operator-reports">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS</div>
        <h1 className="text-2xl font-bold">Звіти</h1>
        <p className="text-sm text-muted-foreground mt-1">Подання звіту скидає лічильник SLA по об'єкту.</p>
      </div>

      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Новий звіт</h2></div>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Об'єкт</label>
            <select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })} data-testid="report-asset" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Період</label>
            <input value={form.period_label} onChange={(e) => setForm({ ...form, period_label: e.target.value })} placeholder="листопад 2026" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
          </div>
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Заголовок</label>
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="report-title" placeholder="Місячний звіт по об'єкту" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
          </div>
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Короткий опис</label>
            <textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} rows={3} className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm mt-1" />
          </div>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
        {ok && <p className="text-xs text-emerald-600 mt-2 inline-flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />{ok}</p>}
        <button onClick={submit} disabled={busy} data-testid="report-submit" className="mt-4 h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Опублікувати звіт
        </button>
      </section>

      <section>
        <h2 className="font-semibold mb-3">Історія звітів ({reports.length})</h2>
        <div className="space-y-2" data-testid="operator-reports-list">
          {reports.map((r) => (
            <div key={r.id} className="rounded-xl border border-border bg-card p-4 flex items-start gap-3">
              <FileText className="w-4 h-4 text-[#2E5D4F] mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-medium">{r.title}</div>
                <div className="text-[11px] text-muted-foreground">{r.asset_title} · {r.period_label || r.report_type} · {formatDateUk(r.created_at)}</div>
                {r.summary && <div className="text-xs text-muted-foreground mt-1">{r.summary}</div>}
              </div>
            </div>
          ))}
          {reports.length === 0 && <p className="text-sm text-muted-foreground">Звітів ще немає.</p>}
        </div>
      </section>
    </div>
  );
}
