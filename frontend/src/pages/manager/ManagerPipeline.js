import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import LeadDrawer from '@/components/ir/LeadDrawer';
import { Workflow, Loader2, RefreshCw } from 'lucide-react';

const PRIO = { A: 'bg-rose-100 text-rose-700', B: 'bg-amber-100 text-amber-700', C: 'bg-sky-100 text-sky-700', D: 'bg-slate-100 text-slate-600' };

export default function ManagerPipeline() {
  const { bi } = useLang();
  const [cols, setCols] = useState([]);
  const [managers, setManagers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [activeLead, setActiveLead] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [r, m] = await Promise.all([
        lumen.get('/admin/ir/pipeline'),
        lumen.get('/admin/ir/managers'),
      ]);
      setCols(r.data?.columns || []);
      setManagers(m.data?.managers || []);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-5" data-testid="manager-pipeline">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted">{bi('Кабінет менеджера', 'Manager cabinet')}</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Workflow className="w-5 h-5" style={{ color: 'var(--token-primary)' }} />{bi('Воронка інвесторів', 'Investor pipeline')}</h1>
          <p className="text-sm text-token-muted mt-1">{bi('Ранні етапи — ручні, пізні — автоматично. Натисніть на лід, щоб відкрити.', 'Early stages manual, late auto. Click a lead to open.')}</p>
        </div>
        <button onClick={load} data-testid="mgr-pipeline-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
        </button>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="mgr-pipeline-error">{err}</p>}

      {loading ? (
        <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2" data-testid="mgr-pipeline-board">
          {cols.map((c) => (
            <div key={c.stage} className="w-60 shrink-0 rounded-2xl border border-border bg-card" data-testid={`mgr-col-${c.stage}`}>
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: c.color || 'var(--token-primary)' }} />
                  <span className="text-sm font-semibold">{c.label}</span>
                </div>
                <span className="text-xs font-mono text-token-muted">{c.count}</span>
              </div>
              <div className="px-3 py-2">
                <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${c.kind === 'derived' ? 'bg-sky-100 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>
                  {c.kind === 'derived' ? bi('авто', 'auto') : bi('ручний', 'manual')}
                </span>
                {(c.leads || []).length === 0 ? (
                  <p className="text-xs text-token-muted py-4 text-center">{bi('Порожньо', 'Empty')}</p>
                ) : (
                  <ul className="mt-2 space-y-1.5">
                    {(c.leads || []).map((l) => (
                      <li key={l.lead_id} onClick={() => setActiveLead(l.lead_id)} className="rounded-lg border border-border px-2.5 py-2 text-xs cursor-pointer hover:bg-muted/50 flex items-center justify-between gap-2" data-testid="mgr-pipeline-card">
                        <span className="font-medium truncate">{l.full_name || l.email || '—'}</span>
                        {l.priority?.bucket && <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${PRIO[l.priority.bucket]}`}>{l.priority.bucket}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeLead && (
        <LeadDrawer leadId={activeLead} managers={managers} onClose={() => setActiveLead(null)} onChanged={load} />
      )}
    </div>
  );
}
