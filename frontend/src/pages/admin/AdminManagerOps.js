import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { Users2, Loader2, RefreshCw, Repeat, ArrowRight, Search, X, Timer, AlertTriangle } from 'lucide-react';

/**
 * AdminManagerOps — Manager OS control center for admins (M6 + M7).
 *  · Per-manager KPI snapshot (load, conversion, SLA, tasks)
 *  · Reassignment Center: move a lead to another manager (reason + audit)
 *  · Recent reassignment history
 */
export default function AdminManagerOps() {
  const { bi } = useLang();
  const [snapshots, setSnapshots] = useState([]);
  const [history, setHistory] = useState([]);
  const [managers, setManagers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [showReassign, setShowReassign] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [s, h, m] = await Promise.all([
        lumen.get('/admin/manager-os/snapshot'),
        lumen.get('/admin/ir/reassignments?limit=50'),
        lumen.get('/admin/ir/managers'),
      ]);
      setSnapshots(s.data?.snapshots || []);
      setHistory(h.data?.reassignments || []);
      setManagers(m.data?.managers || []);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-manager-ops">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted">{bi('Адміністрування', 'Administration')}</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Users2 className="w-5 h-5" style={{ color: 'var(--token-primary)' }} />{bi('Manager OS · Контроль команди', 'Manager OS · Team Control')}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowReassign(true)} data-testid="open-reassign" className="h-9 px-3 rounded-lg text-sm text-white inline-flex items-center gap-1.5" style={{ background: 'var(--token-primary)' }}><Repeat className="w-4 h-4" /> {bi('Перепризначити', 'Reassign')}</button>
          <button onClick={load} data-testid="mops-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}</button>
        </div>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="mops-error">{err}</p>}

      <div className="rounded-2xl border border-border bg-card overflow-x-auto" data-testid="mops-snapshot">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Навантаження та KPI менеджерів', 'Manager load & KPIs')}</div>
        {loading ? (
          <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>
        ) : snapshots.length === 0 ? (
          <p className="p-6 text-sm text-token-muted text-center">{bi('Немає даних.', 'No data.')}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Менеджер', 'Manager')}</th>
                <th className="text-right px-4 py-2.5">{bi('Ліди', 'Leads')}</th>
                <th className="text-right px-4 py-2.5">{bi('Конв.', 'Conv.')}</th>
                <th className="text-right px-4 py-2.5">{bi('Сер.відп', 'Avg resp')}</th>
                <th className="text-right px-4 py-2.5">SLA ⚠</th>
                <th className="text-right px-4 py-2.5">{bi('Задачі', 'Tasks')}</th>
                <th className="text-left px-4 py-2.5">Scope</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.user_id} className="border-t border-border" data-testid="mops-snapshot-row">
                  <td className="px-4 py-2.5"><div className="font-medium">{s.name || '—'}</div><div className="text-[11px] text-token-muted">{s.email}</div></td>
                  <td className="px-4 py-2.5 text-right font-mono">{s.leads_total ?? 0}</td>
                  <td className="px-4 py-2.5 text-right font-mono">{s.conversion_rate ?? 0}%</td>
                  <td className="px-4 py-2.5 text-right font-mono">{s.avg_response_min != null ? `${s.avg_response_min}m` : '—'}</td>
                  <td className="px-4 py-2.5 text-right font-mono">{s.sla_breached > 0 ? <span className="text-rose-600 font-bold">{s.sla_breached}</span> : (s.sla_breached ?? 0)}</td>
                  <td className="px-4 py-2.5 text-right font-mono">{s.open_tasks ?? 0}<span className="text-token-muted">/{s.overdue_tasks ?? 0}</span></td>
                  <td className="px-4 py-2.5"><span className="text-[11px] px-2 py-0.5 rounded-full bg-muted">{s.scope || 'owned'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-x-auto" data-testid="mops-history">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Історія перепризначень', 'Reassignment history')}</div>
        {history.length === 0 ? (
          <p className="p-6 text-sm text-token-muted text-center">{bi('Немає перепризначень.', 'No reassignments.')}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Лід', 'Lead')}</th>
                <th className="text-left px-4 py-2.5">{bi('Перехід', 'Transfer')}</th>
                <th className="text-left px-4 py-2.5">{bi('Причина', 'Reason')}</th>
                <th className="text-left px-4 py-2.5">{bi('Коли', 'When')}</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={i} className="border-t border-border" data-testid="mops-history-row">
                  <td className="px-4 py-2.5 font-medium">{h.lead_name || h.lead_id}</td>
                  <td className="px-4 py-2.5"><span className="inline-flex items-center gap-1.5 text-xs">{h.from_user_name || bi('—', '—')} <ArrowRight className="w-3 h-3 text-token-muted" /> <span className="font-medium">{h.to_user_name || bi('Не призн.', 'Unassigned')}</span></span></td>
                  <td className="px-4 py-2.5 text-token-muted">{h.reason || '—'}</td>
                  <td className="px-4 py-2.5 text-token-muted">{h.at ? formatDateUk(h.at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showReassign && <ReassignModal managers={managers} onClose={() => setShowReassign(false)} onDone={() => { setShowReassign(false); load(); }} bi={bi} />}
    </div>
  );
}

function ReassignModal({ managers, onClose, onDone, bi }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [to, setTo] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const search = async () => {
    setErr('');
    try {
      const r = await lumen.get(`/admin/ir/leads?limit=50${q ? `&q=${encodeURIComponent(q)}` : ''}`);
      setResults(r.data?.leads || []);
    } catch (e) { setErr(lumenError(e)); }
  };
  useEffect(() => { search(); /* eslint-disable-next-line */ }, []);

  const submit = async () => {
    if (!selected || !to) { setErr(bi('Оберіть лід і менеджера', 'Pick a lead and manager')); return; }
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/ir/leads/${selected.lead_id}/reassign`, { to_owner_id: to, reason: reason || 'admin reassignment' });
      onDone();
    } catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4" data-testid="reassign-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-card rounded-2xl border border-border p-5 space-y-3">
        <div className="flex items-center justify-between"><h3 className="font-bold text-lg">{bi('Перепризначення ліда', 'Reassign lead')}</h3><button onClick={onClose}><X className="w-5 h-5 text-token-muted" /></button></div>
        {err && <p className="text-sm text-rose-600">{err}</p>}
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-token-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} placeholder={bi('Пошук ліда…', 'Search lead…')} data-testid="reassign-search" className="w-full h-10 pl-9 pr-3 rounded-lg border border-border bg-background text-sm" />
        </div>
        <div className="max-h-40 overflow-y-auto rounded-lg border border-border divide-y divide-border">
          {results.map((l) => (
            <button key={l.lead_id} onClick={() => setSelected(l)} data-testid="reassign-lead-option" className={`w-full text-left px-3 py-2 text-sm hover:bg-muted/50 ${selected?.lead_id === l.lead_id ? 'bg-muted' : ''}`}>
              <span className="font-medium">{l.full_name || l.email}</span> <span className="text-[11px] text-token-muted">· {l.owner_name || bi('не призн.', 'unassigned')}</span>
            </button>
          ))}
          {results.length === 0 && <p className="px-3 py-3 text-sm text-token-muted">{bi('Нічого не знайдено', 'Nothing found')}</p>}
        </div>
        <select value={to} onChange={(e) => setTo(e.target.value)} data-testid="reassign-to" className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm">
          <option value="">{bi('Новий власник…', 'New owner…')}</option>
          {managers.map((m) => <option key={m.user_id} value={m.user_id}>{m.name} ({m.email})</option>)}
        </select>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={bi('Причина', 'Reason')} data-testid="reassign-modal-reason" className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm" />
        <button disabled={busy} onClick={submit} data-testid="reassign-modal-submit" className="w-full h-10 rounded-lg text-white text-sm font-medium disabled:opacity-50" style={{ background: 'var(--token-primary)' }}>{busy ? '…' : bi('Перепризначити', 'Reassign')}</button>
      </div>
    </div>
  );
}
