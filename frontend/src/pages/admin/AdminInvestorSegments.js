import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { Layers3, Loader2, RotateCcw } from 'lucide-react';

const PRIMARY = '#2E5D4F';
const SEG_COLOR = {
  retail: 'bg-slate-100 text-slate-700',
  qualified: 'bg-sky-100 text-sky-700',
  strategic: 'bg-violet-100 text-violet-700',
  institutional: 'bg-emerald-100 text-emerald-700',
};

export default function AdminInvestorSegments() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState('');

  const load = useCallback(async () => {
    try { const r = await lumen.get('/admin/capital/segments'); setData(r.data); }
    catch (_e) { /* noop */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setSeg = async (uid, segment) => {
    setSavingId(uid);
    try { await lumen.put(`/admin/investors/${uid}/segment`, { segment, override: true }); await load(); }
    catch (_e) {} finally { setSavingId(''); }
  };
  const resetAuto = async (uid) => {
    setSavingId(uid);
    try { await lumen.put(`/admin/investors/${uid}/segment/auto`); await load(); }
    catch (_e) {} finally { setSavingId(''); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const segs = data?.segments || [];
  const labels = data?.segment_labels || {};
  const counts = data?.counts || {};

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="admin-investor-segments">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Capital Formation OS · Phase E</div>
        <h1 className="text-2xl font-bold">Сегменти інвесторів</h1>
        <p className="text-sm text-muted-foreground mt-1">Авто-сегмент за обсягом інвестицій або ручне призначення.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {segs.map((s) => (
          <div key={s} className="rounded-xl border border-border p-4">
            <div className={`inline-flex text-[11px] px-2 py-0.5 rounded-full font-semibold ${SEG_COLOR[s]}`}>{labels[s] || s}</div>
            <div className="text-2xl font-bold mt-2">{counts[s] || 0}</div>
          </div>
        ))}
      </div>

      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><Layers3 className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Інвестори</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="segments-table">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                <th className="text-left py-2">Інвестор</th><th className="text-right">Інвестовано</th>
                <th className="text-center">Джерело</th><th className="text-left pl-4">Сегмент</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((it) => (
                <tr key={it.user_id} className="border-b border-border/50">
                  <td className="py-2">
                    <div className="font-medium">{it.name || it.email}</div>
                    <div className="text-[11px] text-muted-foreground">{it.email}</div>
                  </td>
                  <td className="text-right font-semibold">{formatUAH(it.invested_uah)}</td>
                  <td className="text-center">
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${it.source === 'override' ? 'bg-amber-100 text-amber-700' : 'bg-muted text-muted-foreground'}`}>{it.source === 'override' ? 'ручний' : 'авто'}</span>
                  </td>
                  <td className="pl-4">
                    <select value={it.segment} disabled={savingId === it.user_id} onChange={(e) => setSeg(it.user_id, e.target.value)}
                      data-testid={`segment-select-${it.user_id}`}
                      className="h-9 rounded-lg border border-border bg-background px-2 text-sm">
                      {segs.map((s) => <option key={s} value={s}>{labels[s] || s}</option>)}
                    </select>
                  </td>
                  <td className="text-right">
                    {it.source === 'override' && (
                      <button onClick={() => resetAuto(it.user_id)} title="Скинути на авто" className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"><RotateCcw className="w-3.5 h-3.5" /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
