import { useEffect, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { Activity, Loader2, RefreshCw, Phone, CalendarDays, StickyNote, CheckSquare, Timer, AlertTriangle, Target, TrendingUp } from 'lucide-react';

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 text-token-muted text-xs uppercase tracking-wider">
        <Icon className="w-4 h-4" style={{ color: accent || 'var(--token-primary)' }} />{label}
      </div>
      <div className="mt-2 text-3xl font-bold">{value}</div>
    </div>
  );
}

/**
 * ManagerActivity — "My Performance" (M7). Personal KPI snapshot of the
 * logged-in manager from /admin/manager-os/my-snapshot (scoped server-side).
 */
export default function ManagerActivity() {
  const { bi } = useLang();
  const [snap, setSnap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const r = await lumen.get('/admin/manager-os/my-snapshot');
      setSnap(r.data);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const a = snap?.activity || {};

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="manager-activity">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted">{bi('Кабінет менеджера', 'Manager cabinet')}</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="w-5 h-5" style={{ color: 'var(--token-primary)' }} />{bi('Моя ефективність', 'My Performance')}</h1>
          <p className="text-sm text-token-muted mt-1">{snap?.manager?.name} {snap?.manager?.scope ? `· scope: ${snap.manager.scope}` : ''}</p>
        </div>
        <button onClick={load} data-testid="mgr-activity-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
        </button>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="mgr-activity-error">{err}</p>}

      {loading ? (
        <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat icon={Target} label={bi('Мої ліди', 'My leads')} value={snap?.leads_total ?? 0} />
            <Stat icon={TrendingUp} label={bi('Конверсія', 'Conversion')} value={`${snap?.conversion_rate ?? 0}%`} accent="#2C7A7B" />
            <Stat icon={Timer} label={bi('Сер. відповідь', 'Avg response')} value={snap?.avg_response_min != null ? `${snap.avg_response_min} ${bi('хв', 'min')}` : '—'} />
            <Stat icon={AlertTriangle} label={bi('SLA порушено', 'SLA breached')} value={snap?.sla_breached ?? 0} accent="#E11D48" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat icon={Phone} label={bi('Дзвінки', 'Calls')} value={a.calls_count ?? 0} />
            <Stat icon={CalendarDays} label={bi('Зустрічі', 'Meetings')} value={a.meetings_count ?? 0} />
            <Stat icon={StickyNote} label={bi('Нотатки', 'Notes')} value={a.notes_count ?? 0} />
            <Stat icon={CheckSquare} label={bi('Задачі (відкр/простр)', 'Tasks (open/overdue)')} value={`${snap?.open_tasks ?? 0}/${snap?.overdue_tasks ?? 0}`} accent="#B7791F" />
          </div>
          <p className="text-[11px] text-token-muted">{bi('Лічильники та SLA оновлюються в реальному часі (Manager OS).', 'Counters and SLA update in real time (Manager OS).')}</p>
        </>
      )}
    </div>
  );
}
