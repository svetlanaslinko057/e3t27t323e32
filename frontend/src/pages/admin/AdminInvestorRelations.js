/**
 * AdminInvestorRelations — IR Center (Phase IR1).
 *
 * Investor-accompaniment layer for LUMEN (NOT a generic CRM). First slice:
 *   • IR1.1 Lead Management  — leads in lumen_leads (legacy `leads` untouched)
 *   • IR1.2 Pipeline         — hybrid: early stages manual, late stages derived
 *   • IR1.7 Ownership        — owner_id + owner_type=manager (admin-only in Beta)
 *
 * Stage moves use the drawer (no drag-drop). Late stages (KYC / Accredited /
 * Funding / Funded / Active) are AUTO-DERIVED from real platform facts and are
 * therefore read-only here.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import ActivityTimeline from '@/components/lumen/ActivityTimeline';
import {
  Users, UserPlus, Search, LayoutGrid, List as ListIcon, X, Loader2,
  ShieldCheck, Award, Banknote, FileCheck2, RefreshCw, Link2, History,
  ChevronRight, CircleDollarSign, Target, Activity,
  MessageSquare, CheckSquare, CalendarClock, GitBranch, Plus, Trash2,
  Clock, Phone, Video, MapPin, Circle, CheckCircle2, AlertTriangle, Radio,
} from 'lucide-react';

const HEALTH_META = {
  green: { label: 'Green', color: '#2F855A', bg: '#E6F4EA', bd: '#B7E1C3' },
  yellow: { label: 'Yellow', color: '#B7791F', bg: '#FEF5E7', bd: '#F4D8A8' },
  red: { label: 'Red', color: '#C53030', bg: '#FDECEC', bd: '#F5C2C2' },
};

function HealthDot({ health, size = 'sm' }) {
  const h = HEALTH_META[health?.color] || HEALTH_META.yellow;
  const dim = size === 'sm' ? 'w-2.5 h-2.5' : 'w-3 h-3';
  return <span className={`inline-block rounded-full ${dim}`} style={{ backgroundColor: h.color }} title={(health?.reasons || []).join(' · ')} />;
}

function HealthBadge({ health }) {
  if (!health) return null;
  const h = HEALTH_META[health.color] || HEALTH_META.yellow;
  return (
    <div className="rounded-lg border p-2.5" style={{ backgroundColor: h.bg, borderColor: h.bd }} data-testid="ir-health-badge">
      <div className="flex items-center gap-2">
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: h.color }} />
        <span className="text-sm font-bold" style={{ color: h.color }} data-testid={`ir-health-${health.color}`}>{h.label}</span>
        {health.last_interaction_days != null && (
          <span className="text-[11px] ml-auto" style={{ color: h.color }}>
            остання взаємодія: {health.last_interaction_days}д
          </span>
        )}
      </div>
      <ul className="mt-1.5 space-y-0.5">
        {(health.reasons || []).map((r, i) => (
          <li key={i} className="text-[11px] flex items-center gap-1.5" style={{ color: h.color }}>
            <Circle className="w-1.5 h-1.5 fill-current" /> {r}
          </li>
        ))}
      </ul>
    </div>
  );
}

const EARLY_STAGES = ['lead', 'qualified', 'meeting'];
const STAGE_LABEL = {
  lead: 'Lead', qualified: 'Qualified', meeting: 'Meeting',
  kyc: 'KYC', accredited: 'Accredited', funding_pending: 'Funding Pending',
  funded: 'Funded', active: 'Active Investor',
};
const STAGE_COLOR = {
  lead: '#8A8A8A', qualified: '#5B7C99', meeting: '#6B5B95',
  kyc: '#B7791F', accredited: '#2C7A7B', funding_pending: '#C05621',
  funded: '#2F855A', active: '#2E5D4F',
};

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

function StageBadge({ stage }) {
  const color = STAGE_COLOR[stage] || '#8A8A8A';
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold text-white"
      style={{ backgroundColor: color }}
      data-testid={`ir-stage-badge-${stage}`}
    >
      {STAGE_LABEL[stage] || stage}
    </span>
  );
}

function FactBadge({ icon: Icon, label, value, testid }) {
  const ok = ['approved', 'verified', 'active', 'confirmed', 'accredited'].includes(String(value).toLowerCase());
  const pending = ['pending', 'under_review', 'in_review', 'submitted'].includes(String(value).toLowerCase());
  const tone = ok ? { bg: '#E6F4EA', fg: '#2F855A', bd: '#B7E1C3' }
    : pending ? { bg: '#FEF5E7', fg: '#B7791F', bd: '#F4D8A8' }
    : { bg: '#F3F3F1', fg: '#8A8A8A', bd: '#E2E2DD' };
  return (
    <div
      className="flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs"
      style={{ backgroundColor: tone.bg, color: tone.fg, borderColor: tone.bd }}
      data-testid={testid}
    >
      <Icon className="w-4 h-4 shrink-0" />
      <div className="flex flex-col leading-tight">
        <span className="font-semibold">{label}</span>
        <span className="opacity-80">{value === 'none' ? '—' : value}</span>
      </div>
    </div>
  );
}

export default function AdminInvestorRelations() {
  const [view, setView] = useState('pipeline');
  const [pipeline, setPipeline] = useState(null);
  const [leads, setLeads] = useState([]);
  const [overview, setOverview] = useState(null);
  const [managers, setManagers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const [selected, setSelected] = useState(null);   // lead detail in drawer
  const [drawerBusy, setDrawerBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [pl, ov, mg] = await Promise.all([
        lumen.get('/admin/ir/pipeline'),
        lumen.get('/admin/ir/overview'),
        lumen.get('/admin/ir/managers'),
      ]);
      setPipeline(pl.data);
      setOverview(ov.data);
      setManagers(mg.data.managers || []);
      const all = (pl.data.columns || []).flatMap((c) => c.leads);
      setLeads(all);
    } catch (e) {
      setError(lumenError(e, 'Не вдалося завантажити Investor Relations'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openLead = useCallback(async (leadId) => {
    setDrawerBusy(true);
    try {
      const r = await lumen.get(`/admin/ir/leads/${leadId}`);
      setSelected(r.data);
    } catch (e) {
      setError(lumenError(e));
    } finally {
      setDrawerBusy(false);
    }
  }, []);

  const refreshSelected = useCallback(async (leadId) => {
    const r = await lumen.get(`/admin/ir/leads/${leadId}`);
    setSelected(r.data);
    load();
  }, [load]);

  const filteredLeads = useMemo(() => {
    if (!search.trim()) return leads;
    const q = search.toLowerCase();
    return leads.filter((l) =>
      (l.email || '').toLowerCase().includes(q) ||
      (l.full_name || '').toLowerCase().includes(q) ||
      (l.phone || '').toLowerCase().includes(q));
  }, [leads, search]);

  return (
    <div className="p-6 max-w-[1500px] mx-auto" data-testid="ir-page">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-foreground text-background">
              <Target className="w-5 h-5" />
            </span>
            <div>
              <h1 className="text-2xl font-bold text-foreground leading-tight">Investor Relations</h1>
              <p className="text-sm text-muted-foreground">IR Center · супровід інвесторів · лід → активний інвестор</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card hover:bg-muted/40 text-sm" data-testid="ir-refresh">
            <RefreshCw className="w-4 h-4" /> Оновити
          </button>
          <button onClick={() => setShowCreate(true)} className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90" data-testid="ir-new-lead-btn">
            <UserPlus className="w-4 h-4" /> Новий лід
          </button>
        </div>
      </div>

      {/* KPI strip */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <Kpi label="Всього лідів" value={overview.total} icon={Users} testid="ir-kpi-total" />
          <Kpi label="Без власника" value={overview.unassigned} icon={UserPlus} testid="ir-kpi-unassigned" />
          <Kpi label="Конвертовано" value={overview.converted} icon={Link2} testid="ir-kpi-converted" />
          <Kpi label="Активні інвестори" value={overview.active_investors} icon={CircleDollarSign} testid="ir-kpi-active" />
          <Kpi label="Конверсія" value={`${overview.conversion_rate}%`} icon={Target} testid="ir-kpi-conversion" />
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Пошук: email, ім'я, телефон…"
            className="pl-9 pr-3 py-2 w-72 max-w-full rounded-lg border border-border bg-background text-sm text-foreground"
            data-testid="ir-search"
          />
        </div>
        <div className="inline-flex items-center gap-1 p-1 rounded-lg border border-border bg-card">
          <ToggleBtn active={view === 'pipeline'} onClick={() => setView('pipeline')} icon={LayoutGrid} label="Pipeline" testid="ir-view-pipeline" />
          <ToggleBtn active={view === 'list'} onClick={() => setView('list')} icon={ListIcon} label="Список" testid="ir-view-list" />
        </div>
      </div>

      {error && <div className="p-3 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-sm mb-4" data-testid="ir-error">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-muted-foreground"><Loader2 className="w-6 h-6 animate-spin" /></div>
      ) : view === 'pipeline' ? (
        <KanbanBoard pipeline={pipeline} search={search} onOpen={openLead} />
      ) : (
        <LeadsTable leads={filteredLeads} onOpen={openLead} />
      )}

      {/* Drawer */}
      {(selected || drawerBusy) && (
        <LeadDrawer
          lead={selected}
          busy={drawerBusy}
          managers={managers}
          onClose={() => setSelected(null)}
          onChanged={() => selected && refreshSelected(selected.lead_id)}
          setError={setError}
        />
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateLeadModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
          setError={setError}
        />
      )}
    </div>
  );
}

function Kpi({ label, value, icon: Icon, testid }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid={testid}>
      <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1.5"><Icon className="w-4 h-4" />{label}</div>
      <div className="text-2xl font-bold text-foreground">{value}</div>
    </div>
  );
}

function ToggleBtn({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition ${active ? 'bg-foreground text-background font-semibold' : 'text-muted-foreground hover:bg-muted/40'}`}
      data-testid={testid}
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

function KanbanBoard({ pipeline, search, onOpen }) {
  if (!pipeline) return null;
  const q = search.trim().toLowerCase();
  return (
    <div className="flex gap-4 overflow-x-auto pb-4" data-testid="ir-kanban">
      {pipeline.columns.map((col) => {
        const items = q
          ? col.leads.filter((l) => (l.email || '').toLowerCase().includes(q) || (l.full_name || '').toLowerCase().includes(q))
          : col.leads;
        return (
          <div key={col.stage} className="w-72 shrink-0" data-testid={`ir-column-${col.stage}`}>
            <div className="flex items-center justify-between mb-2 px-1">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: col.color }} />
                <span className="font-semibold text-sm text-foreground">{col.label}</span>
                {col.kind === 'derived' && <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">auto</span>}
              </div>
              <span className="text-xs text-muted-foreground font-medium" data-testid={`ir-column-count-${col.stage}`}>{items.length}</span>
            </div>
            <div className="space-y-2 min-h-[80px] rounded-xl bg-muted/20 p-2">
              {items.length === 0 && <div className="text-center text-xs text-muted-foreground py-4">—</div>}
              {items.map((l) => (
                <button
                  key={l.lead_id}
                  onClick={() => onOpen(l.lead_id)}
                  className="w-full text-left rounded-lg border border-border bg-card p-3 hover:shadow-sm hover:border-foreground/30 transition"
                  data-testid={`ir-lead-card-${l.lead_id}`}
                >
                  <div className="font-medium text-sm text-foreground truncate flex items-center gap-1.5">
                    <HealthDot health={l.health} />
                    <span className="truncate">{l.full_name || l.email}</span>
                  </div>
                  <div className="text-xs text-muted-foreground truncate">{l.email}</div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-[11px] text-muted-foreground truncate">{l.owner_name ? `👤 ${l.owner_name}` : 'без власника'}</span>
                    {l.budget_range && <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">{l.budget_range}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LeadsTable({ leads, onOpen }) {
  if (!leads.length) return <div className="text-center text-muted-foreground py-16">Лідів поки немає</div>;
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden" data-testid="ir-list-table">
      <table className="w-full text-sm">
        <thead className="bg-muted/30 text-muted-foreground text-xs uppercase tracking-wider">
          <tr>
            <th className="text-left px-4 py-3 font-semibold">Лід</th>
            <th className="text-left px-4 py-3 font-semibold">Стадія</th>
            <th className="text-left px-4 py-3 font-semibold">Власник</th>
            <th className="text-left px-4 py-3 font-semibold">Бюджет</th>
            <th className="text-left px-4 py-3 font-semibold">Створено</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {leads.map((l) => (
            <tr key={l.lead_id} className="border-t border-border hover:bg-muted/20 cursor-pointer" onClick={() => onOpen(l.lead_id)} data-testid={`ir-list-row-${l.lead_id}`}>
              <td className="px-4 py-3">
                <div className="font-medium text-foreground flex items-center gap-1.5"><HealthDot health={l.health} /> {l.full_name || '—'}</div>
                <div className="text-xs text-muted-foreground">{l.email}</div>
              </td>
              <td className="px-4 py-3"><StageBadge stage={l.effective_stage} /></td>
              <td className="px-4 py-3 text-foreground">{l.owner_name || <span className="text-muted-foreground">—</span>}</td>
              <td className="px-4 py-3 text-muted-foreground">{l.budget_range || '—'}</td>
              <td className="px-4 py-3 text-muted-foreground text-xs">{fmtDate(l.created_at)}</td>
              <td className="px-4 py-3 text-right"><ChevronRight className="w-4 h-4 text-muted-foreground inline" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DRAWER_TABS = [
  { key: 'overview', label: 'Overview', icon: Target, testid: 'ir-tab-overview' },
  { key: 'notes', label: 'Notes', icon: MessageSquare, testid: 'ir-tab-notes' },
  { key: 'tasks', label: 'Tasks', icon: CheckSquare, testid: 'ir-tab-tasks' },
  { key: 'meetings', label: 'Meetings', icon: CalendarClock, testid: 'ir-tab-meetings' },
  { key: 'timeline', label: 'Timeline', icon: GitBranch, testid: 'ir-tab-timeline' },
  { key: 'site_activity', label: 'Активність', icon: Radio, testid: 'ir-tab-site-activity' },
  { key: 'health', label: 'Health', icon: Activity, testid: 'ir-tab-health' },
];

function LeadDrawer({ lead, busy, managers, onClose, onChanged, setError }) {
  const [tab, setTab] = useState('overview');
  const [ownerSel, setOwnerSel] = useState('');
  const [savingOwner, setSavingOwner] = useState(false);
  const [savingStage, setSavingStage] = useState('');
  const [convertId, setConvertId] = useState('');

  useEffect(() => { setOwnerSel(lead?.owner_id || ''); }, [lead?.lead_id, lead?.owner_id]);
  useEffect(() => { setTab('overview'); }, [lead?.lead_id]);

  const assignOwner = async () => {
    setSavingOwner(true);
    try {
      await lumen.post(`/admin/ir/leads/${lead.lead_id}/owner`, { owner_id: ownerSel || null });
      await onChanged();
    } catch (e) { setError(lumenError(e)); } finally { setSavingOwner(false); }
  };

  const setStage = async (stage) => {
    setSavingStage(stage);
    try {
      await lumen.post(`/admin/ir/leads/${lead.lead_id}/stage`, { stage });
      await onChanged();
    } catch (e) { setError(lumenError(e)); } finally { setSavingStage(''); }
  };

  const convert = async () => {
    if (!convertId.trim()) return;
    try {
      await lumen.post(`/admin/ir/leads/${lead.lead_id}/convert`, { user_id: convertId.trim() });
      setConvertId('');
      await onChanged();
    } catch (e) { setError(lumenError(e)); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="ir-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-background h-full shadow-2xl overflow-y-auto border-l border-border">
        <div className="sticky top-0 bg-background border-b border-border z-10">
          <div className="px-5 py-4 flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              {lead?.health && <HealthDot health={lead.health} size="md" />}
              <h2 className="font-bold text-foreground truncate">{lead?.full_name || lead?.email || 'Картка ліда'}</h2>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted/40" data-testid="ir-drawer-close"><X className="w-5 h-5 text-muted-foreground" /></button>
          </div>
          {!busy && lead && (
            <div className="flex items-center gap-1 px-3 pb-2 overflow-x-auto">
              {DRAWER_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition ${tab === t.key ? 'bg-foreground text-background font-semibold' : 'text-muted-foreground hover:bg-muted/40'}`}
                  data-testid={t.testid}
                >
                  <t.icon className="w-3.5 h-3.5" /> {t.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {busy || !lead ? (
          <div className="flex items-center justify-center py-24"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : tab === 'overview' ? (
          <div className="p-5 space-y-5">
            <div>
              <div className="text-sm text-muted-foreground">{lead.email}</div>
              {lead.phone && <div className="text-sm text-muted-foreground">{lead.phone}</div>}
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                <StageBadge stage={lead.effective_stage} />
                {lead.source && <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted/60 text-muted-foreground">{lead.source}</span>}
                {lead.budget_range && <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted/60 text-muted-foreground">{lead.budget_range}</span>}
              </div>
            </div>

            {/* Investor Health (IR1.8) */}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Investor Health</div>
              <HealthBadge health={lead.health} />
            </div>

            {/* Auto-derived facts */}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Факти (авто з реальних даних)</div>
              <div className="grid grid-cols-2 gap-2">
                <FactBadge icon={ShieldCheck} label="KYC" value={lead.facts?.kyc} testid="ir-badge-kyc" />
                <FactBadge icon={Award} label="Акредитація" value={lead.facts?.accreditation} testid="ir-badge-accreditation" />
                <FactBadge icon={Banknote} label="Funding" value={lead.facts?.funding} testid="ir-badge-funding" />
                <FactBadge icon={FileCheck2} label="Сертифікат" value={lead.facts?.certificate} testid="ir-badge-certificate" />
              </div>
            </div>

            {/* Manual early stages */}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Стадія (ранні — вручну)</div>
              <div className="flex flex-wrap gap-2">
                {EARLY_STAGES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setStage(s)}
                    disabled={savingStage === s}
                    className={`px-3 py-1.5 rounded-lg text-sm border transition ${lead.manual_stage === s ? 'bg-foreground text-background border-foreground font-semibold' : 'border-border bg-card hover:bg-muted/40 text-foreground'}`}
                    data-testid={`ir-stage-btn-${s}`}
                  >
                    {savingStage === s ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : STAGE_LABEL[s]}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">Пізні стадії (KYC → Active) визначаються автоматично за фактами.</p>
            </div>

            {/* Ownership */}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Власник (Manager)</div>
              <div className="flex items-center gap-2">
                <select value={ownerSel} onChange={(e) => setOwnerSel(e.target.value)} className="flex-1 px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground" data-testid="ir-owner-select">
                  <option value="">— без власника —</option>
                  {managers.map((m) => (<option key={m.user_id} value={m.user_id}>{m.name} ({m.role})</option>))}
                </select>
                <button onClick={assignOwner} disabled={savingOwner} className="px-3 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-50" data-testid="ir-assign-owner-btn">
                  {savingOwner ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Призначити'}
                </button>
              </div>
            </div>

            {/* Conversion / link */}
            {!lead.user_id ? (
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Зв'язати з користувачем</div>
                <div className="flex items-center gap-2">
                  <input value={convertId} onChange={(e) => setConvertId(e.target.value)} placeholder="user_id" className="flex-1 px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-convert-input" />
                  <button onClick={convert} className="px-3 py-2 rounded-lg border border-border bg-card hover:bg-muted/40 text-sm inline-flex items-center gap-1.5" data-testid="ir-convert-btn"><Link2 className="w-4 h-4" /> Linkувати</button>
                </div>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground flex items-center gap-1.5"><Link2 className="w-3.5 h-3.5" /> Linked: <code className="bg-muted/50 px-1.5 py-0.5 rounded">{lead.user_id}</code></div>
            )}

            {/* Field history */}
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5"><History className="w-3.5 h-3.5" /> Історія змін</div>
              <div className="space-y-2" data-testid="ir-history">
                {(lead.history || []).length === 0 && <div className="text-xs text-muted-foreground">Немає записів</div>}
                {(lead.history || []).map((h, i) => (
                  <div key={i} className="text-xs border border-border rounded-lg p-2.5 bg-card">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">{h.field}</span>
                      <span className="text-muted-foreground">{fmtDate(h.at || h.changed_at || h.created_at)}</span>
                    </div>
                    <div className="text-muted-foreground mt-0.5">
                      <span className="line-through opacity-70">{String(h.old_value ?? '—')}</span>
                      <span className="mx-1">→</span>
                      <span className="text-foreground">{String(h.new_value ?? '—')}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : tab === 'notes' ? (
          <NotesPanel leadId={lead.lead_id} setError={setError} onChanged={onChanged} />
        ) : tab === 'tasks' ? (
          <TasksPanel leadId={lead.lead_id} managers={managers} setError={setError} onChanged={onChanged} />
        ) : tab === 'meetings' ? (
          <MeetingsPanel leadId={lead.lead_id} setError={setError} onChanged={onChanged} />
        ) : tab === 'health' ? (
          <HealthPanel leadId={lead.lead_id} lead={lead} setError={setError} />
        ) : tab === 'site_activity' ? (
          <div className="p-5" data-testid="ir-site-activity-panel">
            <ActivityTimeline leadId={lead.lead_id} userId={lead.user_id || undefined} limit={300} />
          </div>
        ) : (
          <TimelinePanel leadId={lead.lead_id} setError={setError} />
        )}
      </div>
    </div>
  );
}

// ── IR1.3 Notes panel ──
function NotesPanel({ leadId, setError, onChanged }) {
  const [notes, setNotes] = useState([]);
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get(`/admin/ir/leads/${leadId}/notes`); setNotes(r.data.notes || []); }
    catch (e) { setError(lumenError(e)); } finally { setLoading(false); }
  }, [leadId, setError]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!body.trim()) return;
    setSaving(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/notes`, { body }); setBody(''); await load(); onChanged && onChanged(); }
    catch (e) { setError(lumenError(e)); } finally { setSaving(false); }
  };
  const del = async (id) => { try { await lumen.delete(`/admin/ir/notes/${id}`); await load(); } catch (e) { setError(lumenError(e)); } };

  return (
    <div className="p-5 space-y-4" data-testid="ir-notes-panel">
      <div className="space-y-2">
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="Додати нотатку…" className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none" data-testid="ir-note-input" />
        <button onClick={add} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-50" data-testid="ir-note-add">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Додати нотатку
        </button>
      </div>
      <div className="space-y-2" data-testid="ir-notes-list">
        {loading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /> :
          notes.length === 0 ? <div className="text-sm text-muted-foreground text-center py-6">Нотаток поки немає</div> :
          notes.map((n) => (
            <div key={n.id} className="rounded-lg border border-border bg-card p-3 group" data-testid="ir-note-item">
              <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                <span>{n.author_name}</span>
                <div className="flex items-center gap-2"><span>{fmtDate(n.created_at)}</span>
                  <button onClick={() => del(n.id)} className="opacity-0 group-hover:opacity-100 hover:text-rose-600"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
              <div className="text-sm text-foreground whitespace-pre-wrap">{n.body}</div>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── IR1.4 Tasks panel ──
function TasksPanel({ leadId, managers, setError, onChanged }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ title: '', assignee_id: '', due_date: '', priority: 'normal', task_type: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get(`/admin/ir/leads/${leadId}/tasks`); setTasks(r.data.tasks || []); }
    catch (e) { setError(lumenError(e)); } finally { setLoading(false); }
  }, [leadId, setError]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await lumen.post(`/admin/ir/leads/${leadId}/tasks`, {
        ...form, due_date: form.due_date || null, assignee_id: form.assignee_id || null, task_type: form.task_type || null,
      });
      setForm({ title: '', assignee_id: '', due_date: '', priority: 'normal', task_type: '' });
      await load(); onChanged && onChanged();
    } catch (e) { setError(lumenError(e)); } finally { setSaving(false); }
  };
  const toggle = async (t) => {
    try { await lumen.patch(`/admin/ir/tasks/${t.id}`, { status: t.status === 'done' ? 'open' : 'done' }); await load(); onChanged && onChanged(); }
    catch (e) { setError(lumenError(e)); }
  };

  const PRIO = { high: '#C53030', normal: '#5B7C99', low: '#8A8A8A' };
  return (
    <div className="p-5 space-y-4" data-testid="ir-tasks-panel">
      <div className="rounded-lg border border-border bg-card p-3 space-y-2">
        <input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Назва задачі" className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-task-title" />
        <div className="grid grid-cols-2 gap-2">
          <select value={form.assignee_id} onChange={(e) => setForm((f) => ({ ...f, assignee_id: e.target.value }))} className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-task-assignee">
            <option value="">— виконавець —</option>
            {managers.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
          </select>
          <input type="datetime-local" value={form.due_date} onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-task-due" />
          <select value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))} className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-task-priority">
            <option value="low">low</option><option value="normal">normal</option><option value="high">high</option>
          </select>
          <input value={form.task_type} onChange={(e) => setForm((f) => ({ ...f, task_type: e.target.value }))} placeholder="тип (call/email…)" className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-task-type" />
        </div>
        <button onClick={add} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-50" data-testid="ir-task-add">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Додати задачу
        </button>
      </div>
      <div className="space-y-2" data-testid="ir-tasks-list">
        {loading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /> :
          tasks.length === 0 ? <div className="text-sm text-muted-foreground text-center py-6">Задач поки немає</div> :
          tasks.map((t) => {
            const overdue = t.status === 'open' && t.due_date && new Date(t.due_date) < new Date();
            return (
              <div key={t.id} className="rounded-lg border border-border bg-card p-3 flex items-start gap-2.5" data-testid="ir-task-item">
                <button onClick={() => toggle(t)} className="mt-0.5" data-testid={`ir-task-complete-${t.id}`}>
                  {t.status === 'done' ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <Circle className="w-5 h-5 text-muted-foreground" />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-medium ${t.status === 'done' ? 'line-through text-muted-foreground' : 'text-foreground'}`}>{t.title}</div>
                  <div className="flex items-center gap-2 mt-1 flex-wrap text-[11px]">
                    <span className="px-1.5 py-0.5 rounded text-white" style={{ backgroundColor: PRIO[t.priority] || '#5B7C99' }}>{t.priority}</span>
                    {t.task_type && <span className="px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground">{t.task_type}</span>}
                    {t.assignee_name && <span className="text-muted-foreground">👤 {t.assignee_name}</span>}
                    {t.due_date && <span className={overdue ? 'text-rose-600 font-semibold inline-flex items-center gap-1' : 'text-muted-foreground'}>{overdue && <AlertTriangle className="w-3 h-3" />}<Clock className="w-3 h-3 inline" /> {fmtDate(t.due_date)}</span>}
                  </div>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ── IR1.5 Meetings panel ──
function MeetingsPanel({ leadId, setError, onChanged }) {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ title: '', scheduled_at: '', type: 'call', duration_min: 30 });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get(`/admin/ir/leads/${leadId}/meetings`); setMeetings(r.data.meetings || []); }
    catch (e) { setError(lumenError(e)); } finally { setLoading(false); }
  }, [leadId, setError]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.title.trim() || !form.scheduled_at) return;
    setSaving(true);
    try { await lumen.post(`/admin/ir/leads/${leadId}/meetings`, { ...form, duration_min: Number(form.duration_min) || 30 }); setForm({ title: '', scheduled_at: '', type: 'call', duration_min: 30 }); await load(); onChanged && onChanged(); }
    catch (e) { setError(lumenError(e)); } finally { setSaving(false); }
  };
  const complete = async (m) => { try { await lumen.patch(`/admin/ir/meetings/${m.id}`, { status: 'completed' }); await load(); onChanged && onChanged(); } catch (e) { setError(lumenError(e)); } };

  const TYPE_ICON = { call: Phone, video: Video, in_person: MapPin };
  const STATUS_TONE = { scheduled: '#5B7C99', completed: '#2F855A', cancelled: '#8A8A8A' };
  return (
    <div className="p-5 space-y-4" data-testid="ir-meetings-panel">
      <div className="rounded-lg border border-border bg-card p-3 space-y-2">
        <input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Назва зустрічі" className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-meeting-title" />
        <div className="grid grid-cols-2 gap-2">
          <input type="datetime-local" value={form.scheduled_at} onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))} className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-meeting-datetime" />
          <select value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} className="px-2 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-meeting-type">
            <option value="call">call</option><option value="video">video</option><option value="in_person">in_person</option>
          </select>
        </div>
        <button onClick={add} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-50" data-testid="ir-meeting-add">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Запланувати
        </button>
      </div>
      <div className="space-y-2" data-testid="ir-meetings-list">
        {loading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /> :
          meetings.length === 0 ? <div className="text-sm text-muted-foreground text-center py-6">Зустрічей поки немає</div> :
          meetings.map((m) => {
            const Icon = TYPE_ICON[m.type] || Phone;
            return (
              <div key={m.id} className="rounded-lg border border-border bg-card p-3" data-testid="ir-meeting-item">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground"><Icon className="w-4 h-4 text-muted-foreground" /> {m.title}</div>
                  <span className="text-[11px] px-2 py-0.5 rounded-full text-white" style={{ backgroundColor: STATUS_TONE[m.status] || '#5B7C99' }}>{m.status}</span>
                </div>
                <div className="text-xs text-muted-foreground mt-1 flex items-center gap-2"><Clock className="w-3 h-3" /> {fmtDate(m.scheduled_at)} · {m.duration_min}хв</div>
                {m.outcome_note && <div className="text-xs text-foreground mt-1.5 bg-muted/30 rounded p-2">{m.outcome_note}</div>}
                {m.status === 'scheduled' && (
                  <button onClick={() => complete(m)} className="mt-2 text-xs px-2.5 py-1 rounded-lg border border-border hover:bg-muted/40" data-testid={`ir-meeting-complete-${m.id}`}>Відмітити проведеною</button>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ── IR1.6 Timeline panel ──
const TL_META = {
  lead_created: { icon: UserPlus, color: '#5B7C99' },
  stage_changed: { icon: GitBranch, color: '#6B5B95' },
  owner_assigned: { icon: Users, color: '#5B7C99' },
  converted: { icon: Link2, color: '#2C7A7B' },
  note: { icon: MessageSquare, color: '#8A8A8A' },
  task_created: { icon: CheckSquare, color: '#5B7C99' },
  task_completed: { icon: CheckCircle2, color: '#2F855A' },
  meeting_scheduled: { icon: CalendarClock, color: '#6B5B95' },
  meeting_completed: { icon: CheckCircle2, color: '#2F855A' },
  funding: { icon: Banknote, color: '#2F855A' },
  certificate: { icon: FileCheck2, color: '#2E5D4F' },
  kyc: { icon: ShieldCheck, color: '#B7791F' },
  accreditation: { icon: Award, color: '#2C7A7B' },
};
function TimelinePanel({ leadId, setError }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      setLoading(true);
      try { const r = await lumen.get(`/admin/ir/leads/${leadId}/timeline`); setEvents(r.data.timeline || []); }
      catch (e) { setError(lumenError(e)); } finally { setLoading(false); }
    })();
  }, [leadId, setError]);

  return (
    <div className="p-5" data-testid="ir-timeline">
      {loading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /> :
        events.length === 0 ? <div className="text-sm text-muted-foreground text-center py-6">Подій поки немає</div> : (
          <div className="relative pl-6">
            <div className="absolute left-2 top-1 bottom-1 w-px bg-border" />
            <div className="space-y-4">
              {events.map((e, i) => {
                const meta = TL_META[e.kind] || { icon: Circle, color: '#8A8A8A' };
                const Icon = meta.icon;
                return (
                  <div key={i} className="relative" data-testid="ir-timeline-item">
                    <span className="absolute -left-[1.35rem] top-0.5 w-4 h-4 rounded-full flex items-center justify-center" style={{ backgroundColor: meta.color }}>
                      <Icon className="w-2.5 h-2.5 text-white" />
                    </span>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-foreground">{e.title}</span>
                      <span className="text-[11px] text-muted-foreground">{fmtDate(e.at)}</span>
                    </div>
                    {e.detail && <div className="text-xs text-muted-foreground mt-0.5">{e.detail}</div>}
                    {e.actor && <div className="text-[10px] text-muted-foreground/70 mt-0.5">{e.actor}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
    </div>
  );
}

// ── IR1.8 Health panel (dedicated tab) ──
function HealthPanel({ leadId, lead, setError }) {
  const [health, setHealth] = useState(lead?.health || null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get(`/admin/ir/leads/${leadId}/health`); setHealth(r.data); }
    catch (e) { setError(lumenError(e)); } finally { setLoading(false); }
  }, [leadId, setError]);
  useEffect(() => { refresh(); }, [refresh]);

  const h = health || {};
  const meta = HEALTH_META[h.color] || HEALTH_META.yellow;
  const facts = lead?.facts || {};

  return (
    <div className="p-5 space-y-4" data-testid="ir-health-panel">
      <div className="flex items-center justify-between relative z-10">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Investor Health</div>
        <button type="button" onClick={refresh} disabled={loading} data-testid="ir-health-refresh" className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted/40 disabled:opacity-50 relative z-10">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Оновити
        </button>
      </div>

      {/* Big health card */}
      <div className="rounded-xl border p-4" style={{ backgroundColor: meta.bg, borderColor: meta.bd }}>
        <div className="flex items-center gap-3">
          <span className="w-4 h-4 rounded-full" style={{ backgroundColor: meta.color }} />
          <span className="text-lg font-extrabold" style={{ color: meta.color }} data-testid={`ir-health-status-${h.color}`}>{meta.label}</span>
          {h.last_interaction_days != null && (
            <span className="ml-auto text-xs px-2 py-0.5 rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.5)', color: meta.color }}>
              остання взаємодія: {h.last_interaction_days}д тому
            </span>
          )}
        </div>
        <ul className="mt-3 space-y-1">
          {(h.reasons || []).map((r, i) => (
            <li key={i} className="text-xs flex items-center gap-1.5" style={{ color: meta.color }}>
              <Circle className="w-2 h-2 fill-current" /> {r}
            </li>
          ))}
        </ul>
      </div>

      {/* Computed signals breakdown */}
      <div>
        <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Сигнали</div>
        <div className="space-y-1.5 text-sm">
          <SignalRow label="KYC" value={facts.kyc} okSet={['approved','verified','passed','completed']} pendingSet={['pending','under_review','in_review','submitted','in_progress']} />
          <SignalRow label="Акредитація" value={facts.accreditation} okSet={['approved','accredited','verified']} pendingSet={['pending','under_review','in_review']} />
          <SignalRow label="Funding" value={facts.funding} okSet={['confirmed']} pendingSet={['pending']} />
          <SignalRow label="Активний сертифікат" value={facts.certificate} okSet={['active']} pendingSet={[]} />
          <SignalRow label="Відкриті задачі" value={String(h.open_tasks ?? 0)} okSet={['0']} pendingSet={[]} dangerWhen={(h.open_tasks ?? 0) > 0} />
          <SignalRow label="Прострочена задача" value={h.overdue_task ? 'так' : 'ні'} okSet={['ні']} pendingSet={[]} dangerWhen={!!h.overdue_task} />
          <SignalRow label="Остання взаємодія" value={h.last_interaction_days != null ? `${h.last_interaction_days}д тому` : '—'} okSet={[]} pendingSet={[]}
                     dangerWhen={h.last_interaction_days != null && h.last_interaction_days > 60}
                     warnWhen={h.last_interaction_days != null && h.last_interaction_days >= 30 && h.last_interaction_days <= 60} />
        </div>
      </div>

      {/* Rules legend */}
      <div className="rounded-lg border border-border bg-muted/20 p-3 text-[11px] leading-relaxed text-muted-foreground">
        <div className="font-semibold text-foreground mb-1">Як рахується Health (4a)</div>
        <div><b style={{ color: '#C53030' }}>Red</b> — KYC не завершено, або &gt; 60 днів без взаємодії, або є прострочена задача.</div>
        <div><b style={{ color: '#B7791F' }}>Yellow</b> — KYC pending, funding pending, є відкрита задача, або 30–60 днів без взаємодії.</div>
        <div><b style={{ color: '#2F855A' }}>Green</b> — KYC ✓ І активний сертифікат І &lt; 30 днів взаємодії І немає відкритих питань.</div>
      </div>
    </div>
  );
}

function SignalRow({ label, value, okSet, pendingSet, dangerWhen, warnWhen }) {
  const v = String(value || '').toLowerCase();
  let tone = '#8A8A8A', bg = '#F3F3F1', bd = '#E2E2DD';
  if (dangerWhen) { tone = '#C53030'; bg = '#FDECEC'; bd = '#F5C2C2'; }
  else if (warnWhen) { tone = '#B7791F'; bg = '#FEF5E7'; bd = '#F4D8A8'; }
  else if (okSet.includes(v)) { tone = '#2F855A'; bg = '#E6F4EA'; bd = '#B7E1C3'; }
  else if (pendingSet.includes(v)) { tone = '#B7791F'; bg = '#FEF5E7'; bd = '#F4D8A8'; }
  return (
    <div className="flex items-center justify-between rounded-lg border px-3 py-2" style={{ backgroundColor: bg, borderColor: bd }}>
      <span className="text-xs font-medium" style={{ color: tone }}>{label}</span>
      <span className="text-xs font-semibold" style={{ color: tone }}>{value || '—'}</span>
    </div>
  );
}




function CreateLeadModal({ onClose, onCreated, setError }) {
  const [form, setForm] = useState({ email: '', full_name: '', phone: '', source: 'manual', interest: '', budget_range: '' });
  const [saving, setSaving] = useState(false);
  const upd = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    if (!form.email.trim()) { setError("Email обов'язковий"); return; }
    setSaving(true);
    try {
      await lumen.post('/admin/ir/leads', form);
      onCreated();
    } catch (e) { setError(lumenError(e, 'Не вдалося створити ліда')); } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="ir-create-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-background rounded-2xl border border-border shadow-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-foreground">Новий лід</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted/40"><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>
        <div className="space-y-3">
          <Field label="Email *"><input value={form.email} onChange={upd('email')} type="email" className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-email" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Ім'я"><input value={form.full_name} onChange={upd('full_name')} className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-name" /></Field>
            <Field label="Телефон"><input value={form.phone} onChange={upd('phone')} className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-phone" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Джерело"><input value={form.source} onChange={upd('source')} className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-source" /></Field>
            <Field label="Бюджет"><input value={form.budget_range} onChange={upd('budget_range')} placeholder="50k-100k" className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-budget" /></Field>
          </div>
          <Field label="Інтерес"><input value={form.interest} onChange={upd('interest')} className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm" data-testid="ir-create-interest" /></Field>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-border bg-card hover:bg-muted/40 text-sm">Скасувати</button>
          <button onClick={submit} disabled={saving} className="px-4 py-2 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1.5" data-testid="ir-create-submit">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />} Створити
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="text-xs text-muted-foreground mb-1 block">{label}</span>
      {children}
    </label>
  );
}
