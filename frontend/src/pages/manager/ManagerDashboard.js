import { useEffect, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import LiveActivityWidget from '@/components/lumen/LiveActivityWidget';
import { Users, TrendingUp, UserCheck, UserX, Loader2, RefreshCw, Flame, ShieldAlert, Timer, AlertTriangle, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

function Kpi({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5" data-testid="mgr-kpi">
      <div className="flex items-center gap-2 text-token-muted text-xs uppercase tracking-wider">
        <Icon className="w-4 h-4" style={{ color: accent || 'var(--token-primary)' }} />{label}
      </div>
      <div className="mt-2 text-3xl font-bold">{value}</div>
    </div>
  );
}

export default function ManagerDashboard() {
  const { bi } = useLang();
  const [ov, setOv] = useState(null);
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = async () => {
    setLoading(true); setErr('');
    try {
      const [o, l] = await Promise.all([
        lumen.get('/admin/ir/overview'),
        lumen.get('/admin/ir/leads?limit=8'),
      ]);
      setOv(o.data);
      setLeads((l.data?.leads || []).slice().sort((a, b) => (b.priority?.score || 0) - (a.priority?.score || 0)));
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="manager-dashboard">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted">{bi('Кабінет менеджера', 'Manager cabinet')}</div>
          <h1 className="text-2xl font-bold">{bi('Огляд роботи з інвесторами', 'Investor relations overview')}</h1>
        </div>
        <button onClick={load} data-testid="mgr-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
        </button>
      </div>

      {/* Security / 2FA */}
      <div className="rounded-2xl border border-border bg-card p-4 flex items-center justify-between gap-4" data-testid="mgr-security">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#2E5D4F]/10 flex items-center justify-center"><ShieldCheck className="w-5 h-5 text-[#2E5D4F]" /></div>
          <div>
            <p className="font-medium">{bi('Двофакторна автентифікація', 'Two-factor authentication')}</p>
            <p className="text-xs text-token-muted">{bi('Додатковий захист входу в кабінет менеджера.', 'Extra protection for manager sign-in.')}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link to="/account/2fa/setup" className="text-[#2E5D4F] hover:underline" data-testid="mgr-2fa-setup">{bi('Налаштувати', 'Set up')}</Link>
          <Link to="/account/2fa/recovery" className="text-token-muted hover:text-foreground" data-testid="mgr-2fa-recovery">{bi('Коди відновлення', 'Recovery codes')}</Link>
        </div>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="mgr-error">{err}</p>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi icon={Users} label={bi('Усього лідів', 'Total leads')} value={ov?.total ?? '—'} />
        <Kpi icon={TrendingUp} label={bi('Конверсія', 'Conversion')} value={ov ? `${ov.conversion_rate || 0}%` : '—'} accent="#2C7A7B" />
        <Kpi icon={Flame} label={bi('Гарячі (A)', 'Hot (A)')} value={ov?.hot_leads ?? '—'} accent="#E11D48" />
        <Kpi icon={UserX} label={bi('Неназначені', 'Unassigned')} value={ov?.unassigned ?? '—'} accent="#B7791F" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Kpi icon={AlertTriangle} label={bi('SLA порушено', 'SLA breached')} value={ov?.sla_breached ?? '—'} accent="#E11D48" />
        <Kpi icon={ShieldAlert} label={bi('SLA під ризиком', 'SLA at risk')} value={ov?.sla_at_risk ?? '—'} accent="#B7791F" />
        <Kpi icon={Timer} label={bi('Сер. відповідь', 'Avg response')} value={ov?.avg_response_min != null ? `${ov.avg_response_min} ${bi('хв', 'min')}` : '—'} accent="#2C7A7B" />
        <Kpi icon={UserCheck} label={bi('Активні інвестори', 'Active investors')} value={ov?.active_investors ?? '—'} />
      </div>

      <div className="rounded-2xl border border-border bg-card p-5" data-testid="mgr-funnel">
        <h2 className="font-semibold mb-4">{bi('Воронка за етапами', 'Funnel by stage')}</h2>
        <div className="space-y-2">
          {Object.entries(ov?.by_stage || {}).map(([stage, count]) => {
            const max = Math.max(1, ...Object.values(ov?.by_stage || { x: 1 }));
            const pct = Math.round((count / max) * 100);
            return (
              <div key={stage} className="flex items-center gap-3 text-sm">
                <span className="w-36 shrink-0 text-token-muted capitalize">{stage}</span>
                <div className="flex-1 h-2.5 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--token-primary)' }} />
                </div>
                <span className="w-8 text-right font-mono tabular-nums">{count}</span>
              </div>
            );
          })}
          {!ov && <p className="text-sm text-token-muted">{bi('Завантаження…', 'Loading…')}</p>}
        </div>
      </div>

      <LiveActivityWidget compact />

      <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="mgr-recent-leads">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Пріоритетні ліди (кому дзвонити першим)', 'Priority leads (call first)')}</div>
        {leads.length === 0 ? (
          <p className="p-5 text-sm text-token-muted">{bi('Лідів поки немає.', 'No leads yet.')}</p>
        ) : (
          <ul className="divide-y divide-border">
            {leads.map((l) => (
              <li key={l.lead_id} className="px-5 py-3 flex items-center justify-between gap-3 text-sm">
                <span className="flex items-center gap-2 min-w-0">
                  <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded ${l.priority?.bucket === 'A' ? 'bg-rose-100 text-rose-700' : l.priority?.bucket === 'B' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>{l.priority?.bucket}</span>
                  <span className="font-medium truncate">{l.full_name || l.email || '—'}</span>
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-token-muted whitespace-nowrap">{l.effective_stage_label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
