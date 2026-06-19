import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import LeadDrawer from '@/components/ir/LeadDrawer';
import { Search, Loader2, RefreshCw, Users, Plus, X, Flame, ShieldAlert } from 'lucide-react';

const HEALTH = { green: 'bg-emerald-100 text-emerald-700', yellow: 'bg-amber-100 text-amber-700', red: 'bg-rose-100 text-rose-700' };
const SLA = { responded: 'bg-emerald-100 text-emerald-700', pending: 'bg-sky-100 text-sky-700', breached: 'bg-rose-100 text-rose-700' };
const PRIO = { A: 'bg-rose-100 text-rose-700', B: 'bg-amber-100 text-amber-700', C: 'bg-sky-100 text-sky-700', D: 'bg-slate-100 text-slate-600' };

export default function ManagerLeads() {
  const { bi } = useLang();
  const [leads, setLeads] = useState([]);
  const [managers, setManagers] = useState([]);
  const [q, setQ] = useState('');
  const [prioFilter, setPrioFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [activeLead, setActiveLead] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ email: '', full_name: '', phone: '', source: 'manual', interest: '' });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const [r, m] = await Promise.all([
        lumen.get('/admin/ir/leads?limit=300'),
        lumen.get('/admin/ir/managers'),
      ]);
      const list = (r.data?.leads || []).slice().sort((a, b) => (b.priority?.score || 0) - (a.priority?.score || 0));
      setLeads(list);
      setManagers(m.data?.managers || []);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const filtered = leads.filter((l) => {
    if (prioFilter && (l.priority?.bucket !== prioFilter)) return false;
    if (!q) return true;
    const hay = `${l.full_name || ''} ${l.email || ''} ${l.phone || ''}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  const createLead = async () => {
    if (!form.email && !form.full_name) { setErr(bi('Вкажіть email або імʼя', 'Provide email or name')); return; }
    setCreating(true); setErr('');
    try {
      await lumen.post('/admin/ir/leads', form);
      setShowCreate(false);
      setForm({ email: '', full_name: '', phone: '', source: 'manual', interest: '' });
      await load();
    } catch (e) { setErr(lumenError(e)); } finally { setCreating(false); }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5" data-testid="manager-leads">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted">{bi('Кабінет менеджера', 'Manager cabinet')}</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Users className="w-5 h-5" style={{ color: 'var(--token-primary)' }} />{bi('Мої ліди', 'My Leads')}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowCreate(true)} data-testid="mgr-lead-create-btn" className="h-9 px-3 rounded-lg text-sm text-white inline-flex items-center gap-1.5" style={{ background: 'var(--token-primary)' }}>
            <Plus className="w-4 h-4" /> {bi('Новий лід', 'New lead')}
          </button>
          <button onClick={load} data-testid="mgr-leads-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
          </button>
        </div>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="mgr-leads-error">{err}</p>}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-token-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="mgr-leads-search" placeholder={bi('Пошук…', 'Search…')} className="w-full h-10 pl-9 pr-3 rounded-lg border border-border bg-background text-sm" />
        </div>
        <div className="flex items-center gap-1">
          {['', 'A', 'B', 'C', 'D'].map((p) => (
            <button key={p || 'all'} onClick={() => setPrioFilter(p)} data-testid={`prio-filter-${p || 'all'}`}
              className={`text-xs px-2.5 py-1.5 rounded-lg border ${prioFilter === p ? 'border-[var(--token-primary)] text-token-primary font-semibold' : 'border-border text-token-muted'}`}>
              {p || bi('Усі', 'All')}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>
        ) : filtered.length === 0 ? (
          <p className="p-6 text-sm text-token-muted text-center">{bi('Лідів не знайдено.', 'No leads found.')}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-token-muted">
              <tr>
                <th className="text-left px-4 py-2.5">{bi('Пріор.', 'Prio')}</th>
                <th className="text-left px-4 py-2.5">{bi("Ім'я", 'Name')}</th>
                <th className="text-left px-4 py-2.5">{bi('Етап', 'Stage')}</th>
                <th className="text-left px-4 py-2.5">Health</th>
                <th className="text-left px-4 py-2.5">SLA</th>
                <th className="text-left px-4 py-2.5">{bi('Створено', 'Created')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => (
                <tr key={l.lead_id} onClick={() => setActiveLead(l.lead_id)} className="border-t border-border cursor-pointer hover:bg-muted/40" data-testid="mgr-lead-row">
                  <td className="px-4 py-2.5"><span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${PRIO[l.priority?.bucket] || 'bg-slate-100'}`}>{l.priority?.bucket || '—'}</span></td>
                  <td className="px-4 py-2.5"><div className="font-medium">{l.full_name || '—'}</div><div className="text-[11px] text-token-muted">{l.email}</div></td>
                  <td className="px-4 py-2.5"><span className="text-[11px] px-2 py-0.5 rounded-full bg-muted">{l.effective_stage_label}</span></td>
                  <td className="px-4 py-2.5">{l.health?.color ? <span className={`text-[11px] px-2 py-0.5 rounded-full ${HEALTH[l.health.color]}`}>{l.health.color}</span> : '—'}</td>
                  <td className="px-4 py-2.5">{l.sla?.status ? <span className={`text-[11px] px-2 py-0.5 rounded-full ${SLA[l.sla.status] || 'bg-slate-100'} ${l.sla.overdue ? 'ring-1 ring-rose-400' : ''}`}>{l.sla.status}</span> : '—'}</td>
                  <td className="px-4 py-2.5 text-token-muted">{l.created_at ? formatDateUk(l.created_at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {activeLead && (
        <LeadDrawer leadId={activeLead} managers={managers} onClose={() => setActiveLead(null)} onChanged={load} />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4" data-testid="create-lead-modal">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowCreate(false)} />
          <div className="relative w-full max-w-md bg-card rounded-2xl border border-border p-5 space-y-3">
            <div className="flex items-center justify-between"><h3 className="font-bold text-lg">{bi('Новий лід', 'New lead')}</h3><button onClick={() => setShowCreate(false)}><X className="w-5 h-5 text-token-muted" /></button></div>
            <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder={bi("Повне ім'я", 'Full name')} data-testid="create-name" className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm" />
            <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" data-testid="create-email" className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm" />
            <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder={bi('Телефон', 'Phone')} className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm" />
            <input value={form.interest} onChange={(e) => setForm({ ...form, interest: e.target.value })} placeholder={bi('Інтерес', 'Interest')} className="w-full h-10 px-3 rounded-lg border border-border bg-background text-sm" />
            <button disabled={creating} onClick={createLead} data-testid="create-submit" className="w-full h-10 rounded-lg text-white text-sm font-medium disabled:opacity-50" style={{ background: 'var(--token-primary)' }}>{creating ? bi('Створення…', 'Creating…') : bi('Створити', 'Create')}</button>
          </div>
        </div>
      )}
    </div>
  );
}
