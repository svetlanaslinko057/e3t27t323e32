import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError, API } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle, Loader2, KeyRound,
  FileText, GitBranch, FlaskConical, Settings2, RefreshCw,
  Lock, Lock as LockIcon, Radio, Siren, ToggleRight, ShieldAlert,
  Play, BellOff,
  ListChecks, Download, ChevronDown, ChevronRight, Rocket, MinusCircle,
  CircleDashed,
} from 'lucide-react';

/* Brand colour is sourced from the active theme token — never hardcoded. */
const PRIMARY = 'var(--token-primary)';

function grade2color(grade) {
  return { A: 'bg-emerald-100 text-emerald-700 border-emerald-200',
           B: 'bg-sky-100 text-sky-700 border-sky-200',
           C: 'bg-amber-100 text-amber-700 border-amber-200',
           D: 'bg-orange-100 text-orange-700 border-orange-200',
           F: 'bg-rose-100 text-rose-700 border-rose-200' }[grade] || 'bg-slate-100';
}

function Score({ s }) {
  const { bi } = useLang();
  if (!s) return null;
  return (
    <div className="rounded-2xl border border-border bg-card p-5" data-testid="lr2-score">
      <div className="flex items-center gap-4">
        <div className={`w-20 h-20 rounded-full border-4 flex items-center justify-center text-2xl font-bold ${grade2color(s.grade)}`}>
          {s.grade}
        </div>
        <div>
          <div className="text-3xl font-bold">{s.total}<span className="text-base font-medium text-muted-foreground">/{s.max}</span></div>
          <div className="text-sm text-muted-foreground">{bi('Бал готовності до запуску', 'Launch readiness score')}</div>
        </div>
      </div>
      <div className="mt-4 space-y-1.5">
        {s.parts.map((p) => {
          const wp = (p.score / p.max) * 100;
          return (
            <div key={p.key} className="flex items-center gap-2 text-xs">
              <span className="w-24 text-muted-foreground capitalize">{p.key}</span>
              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full" style={{ width: `${wp}%`, background: PRIMARY }} />
              </div>
              <span className="font-mono text-[11px] tabular-nums">{p.score}/{p.max}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Pass({ ok }) {
  const { bi } = useLang();
  return ok
    ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="w-4 h-4" />{bi('ПРОЙДЕНО', 'PASS')}</span>
    : <span className="inline-flex items-center gap-1 text-rose-700"><XCircle className="w-4 h-4" />{bi('ЗБІЙ', 'FAIL')}</span>;
}

function Severity({ s }) {
  const m = { critical: 'bg-rose-100 text-rose-700',
              high: 'bg-rose-100 text-rose-700',
              medium: 'bg-amber-100 text-amber-700',
              low: 'bg-sky-100 text-sky-700',
              warning: 'bg-amber-100 text-amber-700',
              error: 'bg-rose-100 text-rose-700' };
  return <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full ${m[s] || 'bg-slate-100 text-slate-700'}`}>{s}</span>;
}

export default function AdminLaunchReadiness() {
  const { bi } = useLang();
  const [tab, setTab] = useState('checklist');
  const [snap, setSnap] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [perm, setPerm] = useState(null);
  const [inv, setInv] = useState(null);
  const [rep, setRep] = useState(null);
  const [cof, setCof] = useState(null);
  const [demo, setDemo] = useState(null);
  const [enforce, setEnforce] = useState(null);
  const [scans, setScans] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [denials, setDenials] = useState(null);
  const [prodStatus, setProdStatus] = useState(null);
  const [sec, setSec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await lumen.get('/admin/launch-readiness/snapshot');
      setSnap(r.data);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  const loadChecklist = useCallback(async () => {
    try {
      const r = await lumen.get('/admin/launch-readiness/checklist');
      setChecklist(r.data);
    } catch (e) { setErr(lumenError(e)); }
  }, []);
  useEffect(() => { load(); loadChecklist(); }, [load, loadChecklist]);

  const lazyLoad = async (key, force = false) => {
    try {
      if (key === 'checklist' && (!checklist || force)) await loadChecklist();
      if (key === 'permissions' && (!perm || force)) setPerm((await lumen.get('/admin/launch-readiness/permissions')).data);
      if (key === 'invariants' && (!inv || force)) setInv((await lumen.get('/admin/launch-readiness/invariants')).data);
      if (key === 'reporting' && (!rep || force)) setRep((await lumen.get('/admin/launch-readiness/reporting-integrity')).data);
      if (key === 'conflicts' && (!cof || force)) setCof((await lumen.get('/admin/launch-readiness/conflicts')).data);
      if (key === 'demo' && (!demo || force)) setDemo((await lumen.get('/admin/launch-readiness/demo-data')).data);
      if (key === 'enforce' && (!enforce || force)) setEnforce((await lumen.get('/admin/launch-readiness/enforcement-coverage')).data);
      if (key === 'scanner' && (!scans || force)) {
        const [s, a, dn] = await Promise.all([
          lumen.get('/admin/launch-readiness/scans?limit=20'),
          lumen.get('/admin/launch-readiness/alerts?limit=50'),
          lumen.get('/admin/launch-readiness/denials?limit=20'),
        ]);
        setScans(s.data); setAlerts(a.data); setDenials(dn.data);
      }
      if (key === 'production' && (!prodStatus || force)) setProdStatus((await lumen.get('/admin/launch-readiness/production-switch')).data);
      if (key === 'security' && (!sec || force)) setSec((await lumen.get('/admin/launch-readiness/security-review')).data);
    } catch (e) { setErr(lumenError(e)); }
  };

  const onTab = (v) => { setTab(v); setErr(''); lazyLoad(v); };

  const tabs = [
    ['checklist', bi('Чек-лист запуску v1.0', 'Launch Checklist v1.0'), ListChecks],
    ['overview', bi('Огляд', 'Overview'), ShieldCheck],
    ['permissions', bi('2.1 Доступи', '2.1 Permissions'), KeyRound],
    ['invariants', bi('2.2 Інваріанти', '2.2 Invariants'), FlaskConical],
    ['reporting', bi('2.3 Звітність', '2.3 Reporting'), FileText],
    ['demo', bi('2.4 Демо-дані', '2.4 Demo Data'), Settings2],
    ['conflicts', bi('2.5 Конфлікти', '2.5 Conflicts'), GitBranch],
    ['enforce', bi('2.7 Enforcement', '2.7 Enforcement'), ShieldAlert],
    ['scanner', bi('2.8 Сканер', '2.8 Scanner'), Radio],
    ['production', bi('2.9 Production', '2.9 Production'), ToggleRight],
    ['security', bi('2.10 Безпека', '2.10 Security'), Lock],
  ];

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-5" data-testid="admin-launch-readiness">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{bi('Готовність системи', 'System Readiness')}</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-5 h-5" style={{ color: PRIMARY }} /> {bi('Консоль інституційного гартування', 'Institutional Hardening Console')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{bi('Контроль перед запуском: матриця доступів, інваріанти капіталу, цілісність звітності, конфлікти інтересів, карантин демо-даних, рушій enforcement, фоновий сканер, перемикач production, security-огляд.', 'Pre-launch controls: permissions matrix, capital invariants, reporting integrity, conflicts of interest, demo-data quarantine, enforcement engine, background scanner, production switch, security review.')}</p>
        </div>
        <button onClick={load} data-testid="lr2-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}
        </button>
      </div>

      {err && <p className="text-sm text-rose-600" data-testid="lr2-error">{err}</p>}

      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-1 rounded-full border ${snap?.is_production ? 'bg-rose-100 text-rose-700 border-rose-200' : 'bg-sky-100 text-sky-700 border-sky-200'}`}>
          <LockIcon className="w-3 h-3 inline mr-1" />ENV: {snap?.env || '—'}
        </span>
        <span className="text-xs text-muted-foreground">{bi('запущено', 'ran at')}: {snap?.ran_at ? formatDateUk(snap.ran_at) : '—'}</span>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto" data-testid="lr2-tabs">
        {tabs.map(([v, l, I]) => {
          const active = tab === v;
          return (
            <button key={v} onClick={() => onTab(v)} data-testid={`lr2-tab-${v}`}
              className="px-3 py-2 text-xs sm:text-sm font-medium border-b-2 -mb-px inline-flex items-center gap-1.5 whitespace-nowrap transition-colors"
              style={{
                borderColor: active ? PRIMARY : 'transparent',
                color: active ? PRIMARY : 'var(--token-muted)',
              }}>
              <I className="w-4 h-4" />{l}
            </button>
          );
        })}
      </div>

      {tab === 'overview' && snap && (
        <div className="grid md:grid-cols-2 gap-4">
          <Score s={snap.score} />
          <div className="rounded-2xl border border-border bg-card p-5 space-y-3">
            <h2 className="font-semibold flex items-center gap-1.5"><AlertTriangle className="w-4 h-4 text-amber-600" />{bi('Зведення', 'Summary')}</h2>
            <Row label={bi('Порушення доступів', 'Permission violations')} value={snap.permissions?.counts?.violations} ok={(snap.permissions?.counts?.violations ?? 0) === 0} />
            <Row label={bi('Інваріантів провалено', 'Invariants failed')} value={snap.invariants?.counts?.failed} ok={(snap.invariants?.counts?.failed ?? 0) === 0} />
            <Row label={bi('Проблем зі звітністю', 'Reporting issues')} value={snap.reporting?.counts?.issues} ok={(snap.reporting?.counts?.issues ?? 0) === 0} />
            <Row label={bi('Конфліктів інтересів', 'Conflicts of interest')} value={snap.conflicts?.counts?.total} ok={(snap.conflicts?.counts?.total ?? 0) === 0} />
            <Row label={bi('Демо-рядків усього', 'Demo rows total')} value={Object.values(snap.demo?.counts || {}).reduce((a, b) => a + b, 0)} ok={false} note={bi('обмежено середовищем', 'env-gated')} />
          </div>
        </div>
      )}

      {tab === 'checklist' && <LaunchChecklistView data={checklist} reload={loadChecklist} bi={bi} />}
      {tab === 'permissions' && <PermView data={perm} />}
      {tab === 'invariants' && <InvariantsView data={inv} />}
      {tab === 'reporting' && <ReportingView data={rep} />}
      {tab === 'conflicts' && <ConflictsView data={cof} />}
      {tab === 'demo' && <DemoView data={demo} onAction={load} />}
      {tab === 'enforce' && <EnforcementView data={enforce} />}
      {tab === 'scanner' && <ScannerView scans={scans} alerts={alerts} denials={denials} reload={() => lazyLoad('scanner', true)} />}
      {tab === 'production' && <ProductionView data={prodStatus} reload={() => lazyLoad('production', true)} />}
      {tab === 'security' && <SecurityView data={sec} />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Production Launch Readiness v1.0 — 130-item checklist (auto-eval + override)
   ═══════════════════════════════════════════════════════════════════════ */

const SEV_META = {
  blocker:  { uk: 'БЛОКЕР', en: 'BLOCKER',  cls: 'bg-rose-100 text-rose-700 border-rose-200' },
  critical: { uk: 'критич.', en: 'critical', cls: 'bg-orange-100 text-orange-700 border-orange-200' },
  major:    { uk: 'важл.',  en: 'major',    cls: 'bg-amber-100 text-amber-700 border-amber-200' },
  minor:    { uk: 'мінор.', en: 'minor',    cls: 'bg-slate-100 text-slate-600 border-slate-200' },
};

function StatusIcon({ status }) {
  if (status === 'completed') return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
  if (status === 'not_applicable') return <MinusCircle className="w-4 h-4 text-slate-400" />;
  return <CircleDashed className="w-4 h-4 text-amber-500" />;
}

function ChecklistItem({ it, reload, bi }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState(it.notes || '');
  const sev = SEV_META[it.severity] || SEV_META.minor;

  const act = async (status) => {
    setBusy(true);
    try {
      await lumen.post(`/admin/launch-readiness/checklist/${it.id}/override`, { status, notes });
      await reload();
    } catch (e) { /* surfaced by parent error */ }
    finally { setBusy(false); }
  };
  const clearOv = async () => {
    setBusy(true);
    try {
      await lumen.delete(`/admin/launch-readiness/checklist/${it.id}/override`);
      setNotes('');
      await reload();
    } catch (e) { /* ignore */ }
    finally { setBusy(false); }
  };

  return (
    <div className="rounded-xl border border-border bg-card" data-testid={`lr-item-${it.id}`}>
      <button onClick={() => setOpen((o) => !o)}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-muted/40 transition-colors">
        <StatusIcon status={it.status} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium leading-snug">{bi(it.label_uk, it.label_en)}</div>
          <div className="mt-1 flex items-center gap-1.5 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sev.cls}`}>{bi(sev.uk, sev.en)}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-border text-muted-foreground uppercase">{it.owner}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-border text-muted-foreground">
              {it.auto_supported ? bi('авто', 'auto') : bi('ручне', 'manual')}
            </span>
            {it.source === 'override' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-sky-200 bg-sky-50 text-sky-700">{bi('перевизначено', 'override')}</span>
            )}
            {it.auto_supported && it.auto_evidence && (
              <span className="text-[10px] text-muted-foreground truncate max-w-[280px]" title={it.auto_evidence}>· {it.auto_evidence}</span>
            )}
          </div>
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-muted-foreground mt-0.5" /> : <ChevronRight className="w-4 h-4 text-muted-foreground mt-0.5" />}
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-border/60 space-y-2.5">
          {it.evidence_uk && (
            <p className="text-xs text-muted-foreground">{bi('Як перевірити: ', 'How to verify: ')}{bi(it.evidence_uk, it.evidence_en)}</p>
          )}
          {it.auto_supported && (
            <p className="text-xs">
              <span className="text-muted-foreground">{bi('Автодетект: ', 'Auto-detect: ')}</span>
              <span className={it.auto_done ? 'text-emerald-700' : 'text-amber-700'}>
                {it.auto_evidence || (it.auto_done ? bi('пройдено', 'passed') : bi('очікує', 'pending'))}
              </span>
            </p>
          )}
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
            data-testid={`lr-notes-${it.id}`}
            placeholder={bi('Доказ / коментар (напр. посилання, дата, відповідальний)', 'Evidence / note (e.g. link, date, owner)')}
            className="w-full text-xs rounded-lg border border-border bg-background p-2 h-16 resize-none" />
          <div className="flex items-center gap-1.5 flex-wrap">
            <button disabled={busy} onClick={() => act('completed')} data-testid={`lr-complete-${it.id}`}
              className="h-7 px-2.5 rounded-md text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 inline-flex items-center gap-1 disabled:opacity-50">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}{bi('Готово', 'Complete')}
            </button>
            <button disabled={busy} onClick={() => act('not_applicable')}
              className="h-7 px-2.5 rounded-md text-xs font-medium border border-border hover:bg-muted inline-flex items-center gap-1 disabled:opacity-50">
              <MinusCircle className="w-3 h-3" />{bi('Не застосовно', 'N/A')}
            </button>
            <button disabled={busy} onClick={() => act('pending')}
              className="h-7 px-2.5 rounded-md text-xs font-medium border border-border hover:bg-muted inline-flex items-center gap-1 disabled:opacity-50">
              <CircleDashed className="w-3 h-3" />{bi('Очікує', 'Pending')}
            </button>
            {it.source === 'override' && (
              <button disabled={busy} onClick={clearOv} data-testid={`lr-clear-${it.id}`}
                className="h-7 px-2.5 rounded-md text-xs font-medium border border-border text-muted-foreground hover:bg-muted inline-flex items-center gap-1 disabled:opacity-50">
                <RefreshCw className="w-3 h-3" />{bi('Скинути до авто', 'Reset to auto')}
              </button>
            )}
          </div>
          {it.overridden_by && (
            <p className="text-[10px] text-muted-foreground">{bi('Перевизначив: ', 'Overridden by: ')}{it.overridden_by}{it.overridden_at ? ` · ${formatDateUk(it.overridden_at)}` : ''}</p>
          )}
        </div>
      )}
    </div>
  );
}

function DomainSection({ d, reload, bi }) {
  const [open, setOpen] = useState(d.blockers_open.length > 0 || d.pending > 0);
  const pct = d.total ? Math.round((d.green / d.total) * 100) : 0;
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid={`lr-domain-${d.id}`}>
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 p-4 hover:bg-muted/40 transition-colors text-left">
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold">{bi(d.label_uk, d.label_en)}</div>
          <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden max-w-md">
            <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct === 100 ? 'var(--token-success, #16a34a)' : PRIMARY }} />
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-bold">{d.green}<span className="text-muted-foreground font-medium">/{d.total}</span></div>
          {d.blockers_open.length > 0 && (
            <div className="text-[10px] text-rose-600 font-medium">{d.blockers_open.length} {bi('блокерів', 'blockers')}</div>
          )}
        </div>
      </button>
      {open && (
        <div className="p-3 pt-0 space-y-2">
          {d.items.map((it) => <ChecklistItem key={it.id} it={it} reload={reload} bi={bi} />)}
        </div>
      )}
    </div>
  );
}

function LaunchChecklistView({ data, reload, bi }) {
  if (!data) {
    return <div className="flex items-center gap-2 text-sm text-muted-foreground p-8"><Loader2 className="w-4 h-4 animate-spin" />{bi('Завантаження чек-листа…', 'Loading checklist…')}</div>;
  }
  const t = data.totals;
  const green = t.completed + t.not_applicable;
  const docUrl = `${API}/admin/launch-readiness/checklist/doc`;

  return (
    <div className="space-y-4" data-testid="lr-checklist">
      {/* Hero: readiness + go-live */}
      <div className="grid md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{bi('Готовність до запуску', 'Launch readiness')}</div>
          <div className="mt-1 flex items-end gap-2">
            <div className="text-4xl font-bold" style={{ color: PRIMARY }}>{data.readiness_pct}%</div>
            <div className="text-sm text-muted-foreground mb-1">{green}/{t.total} {bi('зелених', 'green')}</div>
          </div>
          <div className="mt-3 h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${data.readiness_pct}%`, background: PRIMARY }} />
          </div>
        </div>

        <div className={`rounded-2xl border p-5 ${data.go_live_ready ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50'}`} data-testid="lr-golive">
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground flex items-center gap-1"><Rocket className="w-3.5 h-3.5" />{bi('Готовність go-live', 'Go-live status')}</div>
          <div className={`mt-2 text-2xl font-bold ${data.go_live_ready ? 'text-emerald-700' : 'text-rose-700'}`}>
            {data.go_live_ready ? bi('ГОТОВО', 'READY') : bi('НЕ ГОТОВО', 'NOT READY')}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {bi('Блокери: ', 'Blockers: ')}<span className="font-semibold">{data.blockers.green}/{data.blockers.total}</span> {bi('зелених', 'green')}
            {data.blockers.open.length > 0 && <span className="text-rose-600"> · {data.blockers.open.length} {bi('відкрито', 'open')}</span>}
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-5 flex flex-col justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{bi('Статуси', 'Item statuses')}</div>
            <div className="mt-2 flex items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1"><CheckCircle2 className="w-4 h-4 text-emerald-600" />{t.completed}</span>
              <span className="inline-flex items-center gap-1"><CircleDashed className="w-4 h-4 text-amber-500" />{t.pending}</span>
              <span className="inline-flex items-center gap-1"><MinusCircle className="w-4 h-4 text-slate-400" />{t.not_applicable}</span>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <a href={docUrl} target="_blank" rel="noreferrer" data-testid="lr-download-doc"
              className="h-8 px-3 rounded-lg text-xs font-medium border border-border hover:bg-muted inline-flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" />{bi('Документ v1.0', 'Document v1.0')}
            </a>
            <button onClick={reload} data-testid="lr-checklist-refresh"
              className="h-8 px-3 rounded-lg text-xs font-medium border border-border hover:bg-muted inline-flex items-center gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" />{bi('Оновити', 'Refresh')}
            </button>
          </div>
        </div>
      </div>

      {/* Open blockers callout */}
      {data.blockers.open.length > 0 && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4" data-testid="lr-open-blockers">
          <div className="text-sm font-semibold text-rose-700 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" />{bi('Відкриті блокери go-live', 'Open go-live blockers')} ({data.blockers.open.length})</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.blockers.open.map((id) => (
              <span key={id} className="text-[11px] font-mono px-2 py-0.5 rounded border border-rose-200 bg-white text-rose-700">{id}</span>
            ))}
          </div>
        </div>
      )}

      {/* Domains */}
      <div className="space-y-3">
        {data.domains.map((d) => <DomainSection key={d.id} d={d} reload={reload} bi={bi} />)}
      </div>

      <p className="text-[11px] text-muted-foreground pt-1">
        {bi('Джерело істини: ', 'Source of truth: ')}<code>backend/launch_checklist_seed.py</code> · v{data.version} · {bi('згенеровано', 'generated')} {data.generated_at ? formatDateUk(data.generated_at) : '—'}
      </p>
    </div>
  );
}


function Row({ label, value, ok, note }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span>{label}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-xs">{value ?? 0}</span>
        {note ? <span className="text-[10px] text-muted-foreground">{note}</span>
          : (ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <AlertTriangle className="w-4 h-4 text-amber-600" />)}
      </span>
    </div>
  );
}

function Stat({ label, value, bad, compact }) {
  return (
    <div className={`rounded-${compact ? 'lg' : 'xl'} border border-border bg-card p-${compact ? 2 : 3}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-0.5 ${compact ? 'text-sm' : 'text-lg'} font-bold ${bad ? 'text-rose-700' : ''}`}>{value}</div>
    </div>
  );
}

function Spinner() { return <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" /></div>; }

function PermView({ data }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  return (
    <div className="space-y-4" data-testid="lr2-permissions">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <Stat label={bi('Ресурсів', 'Resources')} value={data.counts.resources} />
        <Stat label={bi('Ролей', 'Roles')} value={data.counts.roles} />
        <Stat label={bi('Осередків матриці', 'Matrix cells')} value={data.counts.allowed_cells + '/' + data.counts.cells} />
        <Stat label={bi('Порушень', 'Violations')} value={data.counts.violations} bad={data.counts.violations > 0} />
      </div>
      {data.violations?.length > 0 && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-4 text-sm" data-testid="perm-violations">
          <div className="font-semibold text-rose-700 mb-2">{bi('Порушення', 'Violations')}</div>
          <ul className="space-y-1">{data.violations.map((v, i) => <li key={i} className="text-rose-800">{v.invariant}: {JSON.stringify(v.row)} — {v.why}</li>)}</ul>
        </div>
      )}
      <div className="rounded-2xl border border-border bg-card overflow-x-auto" data-testid="perm-matrix">
        <table className="w-full text-xs">
          <thead className="bg-muted/40">
            <tr>
              <th className="text-left px-3 py-2">{bi('Ресурс', 'Resource')}</th><th className="text-left px-3 py-2">{bi('Роль', 'Role')}</th>
              {data.actions.map((a) => <th key={a} className="px-2 py-2">{a}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.resources.map((res) => data.roles.map((role) => {
              const cells = data.matrix.filter((m) => m.resource === res && m.role === role);
              return (
                <tr key={`${res}-${role}`} className="border-t border-border">
                  <td className="px-3 py-1.5 font-medium">{res}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{role}</td>
                  {data.actions.map((a) => { const c = cells.find((m) => m.action === a);
                    return <td key={a} className="text-center px-2 py-1.5">{c?.allowed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 inline" /> : <span className="text-muted-foreground">·</span>}</td>;
                  })}
                </tr>
              );
            }))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function InvariantsView({ data }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  return (
    <div className="space-y-3" data-testid="lr2-invariants">
      <div className="flex items-center gap-3 text-sm">
        <span>{bi('Всього', 'Total')}: <b>{data.counts.total}</b></span>
        <span className="text-emerald-700">{bi('ПРОЙДЕНО', 'PASS')}: <b>{data.counts.passed}</b></span>
        <span className="text-rose-700">{bi('ЗБІЙ', 'FAIL')}: <b>{data.counts.failed}</b></span>
      </div>
      <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden">
        {data.results.map((r) => (
          <div key={r.id} className="px-5 py-3" data-testid={`inv-${r.id}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium">{r.label}</div>
              <div className="flex items-center gap-2"><Severity s={r.severity} /><Pass ok={r.passed} /></div>
            </div>
            {(r.failures || []).length > 0 && (
              <ul className="mt-2 text-xs text-rose-700 list-disc list-inside">
                {r.failures.map((f, i) => <li key={i}><code className="text-[11px]">{JSON.stringify(f)}</code></li>)}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportingView({ data }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  return (
    <div className="space-y-3" data-testid="lr2-reporting">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        <Stat label={bi('Звітів перевірено', 'Reports checked')} value={data.counts.reports} />
        <Stat label={bi('Проблем', 'Issues')} value={data.counts.issues} bad={data.counts.issues > 0} />
        <Stat label={bi('Статус', 'Status')} value={data.passed ? bi('ПРОЙДЕНО', 'PASS') : bi('ЗБІЙ', 'FAIL')} bad={!data.passed} />
      </div>
      {(data.meta_issues || []).length > 0 && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-4 text-sm">
          <div className="font-semibold text-rose-700 mb-2">{bi('Проблеми', 'Issues')}</div>
          <ul className="space-y-1">{data.meta_issues.map((i, k) => <li key={k} className="text-rose-800"><code>{JSON.stringify(i)}</code></li>)}</ul>
        </div>
      )}
    </div>
  );
}

function ConflictsView({ data }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  return (
    <div className="space-y-3" data-testid="lr2-conflicts">
      <div className="text-sm">{bi('Всього конфліктів', 'Conflicts total')}: <b>{data.counts.total}</b></div>
      {data.items.length === 0 ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-6 text-center text-sm text-emerald-800">
          <CheckCircle2 className="w-6 h-6 mx-auto mb-2" />{bi('Конфліктів інтересів не виявлено.', 'No conflicts of interest detected.')}
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card divide-y divide-border">
          {data.items.map((c, i) => (
            <div key={i} className="px-5 py-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{c.type}</div>
                <Severity s={c.severity} />
              </div>
              <div className="text-xs text-muted-foreground mt-1">{c.why}</div>
              <pre className="text-[10px] text-muted-foreground mt-1 whitespace-pre-wrap">{JSON.stringify(c, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DemoView({ data, onAction }) {
  const { bi } = useLang();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  if (!data) return <Spinner />;
  const quarantine = async (confirm) => {
    setBusy(true); setErr(''); setMsg('');
    try {
      const r = await lumen.post('/admin/launch-readiness/demo-data/quarantine',
        confirm ? { dry_run: false, confirm: 'DELETE-DEMO' } : { dry_run: true });
      setMsg(JSON.stringify(r.data, null, 2));
      if (confirm) onAction?.();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="lr2-demo">
      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-semibold flex items-center gap-1.5"><FlaskConical className="w-4 h-4" style={{ color: PRIMARY }} />{bi('Демо-дані', 'Demo data')}</div>
            <div className="text-xs text-muted-foreground">ENV: {data.env} · patterns: {data.patterns?.demo_email_patterns?.join(', ')}</div>
          </div>
          {data.is_production && <span className="text-xs px-2 py-1 rounded-full bg-rose-100 text-rose-700"><Lock className="w-3 h-3 inline mr-1" />{bi('Production — заблоковано', 'Production — locked')}</span>}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        {Object.entries(data.counts).map(([k, v]) => <Stat key={k} label={k} value={v} bad={v > 0} compact />)}
      </div>
      <div className="rounded-2xl border border-amber-200 bg-amber-50/30 p-4 space-y-2">
        <div className="text-sm font-medium">{bi('Карантин', 'Quarantine')}</div>
        <p className="text-xs text-muted-foreground">{bi('Помічає демо-рядки флагом', 'Flags demo rows with')} <code>_quarantined_at</code> {bi('і вимикає їх (без фізичного видалення). Структурна вирубка. У production заблоковано.', 'and disables them (no physical delete). Structural cut-off. Locked in production.')}</p>
        <div className="flex gap-2">
          <button onClick={() => quarantine(false)} disabled={busy} data-testid="demo-dryrun"
            className="h-9 px-3 rounded-lg text-sm border border-border bg-background hover:bg-muted">{bi('Пробний запуск', 'Dry-run')}</button>
          <button onClick={() => { if (window.confirm(bi('Карантинувати всі демо-дані?', 'Quarantine all demo data?'))) quarantine(true); }}
            disabled={busy || data.is_production} data-testid="demo-quarantine"
            className="h-9 px-3 rounded-lg text-sm text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-40">{bi('Карантинувати', 'Quarantine')}</button>
        </div>
        {err && <p className="text-xs text-rose-600">{err}</p>}
        {msg && <pre className="text-[10px] bg-muted/30 rounded p-2 whitespace-pre-wrap max-h-48 overflow-auto">{msg}</pre>}
      </div>
    </div>
  );
}

// ── LR2.7 ENFORCEMENT VIEW ────────────────────────────────────────────────
function EnforcementView({ data }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  const c = data.counts;
  const coveragePct = c.total ? Math.round((c.auth_gated / c.total) * 100) : 0;
  return (
    <div className="space-y-4" data-testid="lr2-enforce">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
        <Stat label={bi('Всього маршрутів', 'Total routes')} value={c.total} />
        <Stat label="Auth-gated" value={c.auth_gated} />
        <Stat label="Admin-gated" value={c.admin_gated} />
        <Stat label="LR2-gated" value={c.lr2_gated} />
        <Stat label={bi('Публічні', 'Public')} value={c.public} bad={c.public > 0} />
      </div>

      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="text-sm font-medium mb-1.5">{bi('Покриття auth', 'Auth coverage')}: {coveragePct}%</div>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div className="h-full" style={{ width: `${coveragePct}%`, background: PRIMARY }} />
        </div>
        <div className="text-[11px] text-muted-foreground mt-1.5">
          {bi("Публічні маршрути не обов'язково діра — лендінг, шлюзи здоров'я, OAuth callbacks мають бути публічними. Дивіться список нижче.", 'Public routes are not necessarily a hole — landing, health gates and OAuth callbacks must be public. See the list below.')}
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="enforce-registry">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Активний реєстр доступів LR2', 'Active LR2 permission registry')}</div>
        {data.registry.length === 0 ? <p className="p-5 text-xs text-muted-foreground">{bi('Жодних require_permission() поки не зареєстровано.', 'No require_permission() registered yet.')}</p> : (
          <table className="w-full text-xs">
            <thead className="bg-muted/40"><tr>
              <th className="text-left px-3 py-2">Resource</th><th className="text-left px-3 py-2">Action</th>
              <th className="text-right px-3 py-2">{bi('Звернень', 'Hits')}</th><th className="text-right px-3 py-2">{bi('Відмов', 'Denials')}</th>
              <th className="text-left px-3 py-2">{bi('Останнє', 'Last used')}</th>
            </tr></thead>
            <tbody>{data.registry.map((r, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{r.resource}</td>
                <td className="px-3 py-2">{r.action}</td>
                <td className="px-3 py-2 text-right font-mono">{r.hits}</td>
                <td className={`px-3 py-2 text-right font-mono ${r.denials > 0 ? 'text-rose-700' : ''}`}>{r.denials}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.last_used_at ? formatDateUk(r.last_used_at) : '—'}</td>
              </tr>))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Покриття за ресурсами', 'Coverage per resource')}</div>
        <table className="w-full text-xs">
          <thead className="bg-muted/40"><tr>
            <th className="text-left px-3 py-2">Resource</th>
            <th className="text-right px-3 py-2">{bi('Всього', 'Total')}</th>
            <th className="text-right px-3 py-2">LR2-gated</th>
            <th className="text-right px-3 py-2">Admin-gated</th>
            <th className="text-right px-3 py-2">{bi('Публічні', 'Public')}</th>
          </tr></thead>
          <tbody>{Object.entries(data.per_resource).map(([k, v]) => (
            <tr key={k} className="border-t border-border">
              <td className="px-3 py-2 font-medium">{k}</td>
              <td className="px-3 py-2 text-right font-mono">{v.total}</td>
              <td className={`px-3 py-2 text-right font-mono ${v.lr2_gated > 0 ? 'text-emerald-700 font-semibold' : ''}`}>{v.lr2_gated}</td>
              <td className="px-3 py-2 text-right font-mono">{v.admin_gated}</td>
              <td className={`px-3 py-2 text-right font-mono ${v.public > 0 ? 'text-amber-700' : 'text-muted-foreground'}`}>{v.public}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

// ── LR2.8 SCANNER VIEW ─────────────────────────────────────────────────────
function ScannerView({ scans, alerts, denials, reload }) {
  const { bi } = useLang();
  const [busy, setBusy] = useState(false);
  if (!scans || !alerts) return <Spinner />;
  const runNow = async () => {
    setBusy(true);
    try { await lumen.post('/admin/launch-readiness/scans/run'); await reload(); }
    finally { setBusy(false); }
  };
  const ack = async (id) => {
    try { await lumen.post(`/admin/launch-readiness/alerts/${id}/ack`, { note: 'acked from console' }); await reload(); } catch (e) {}
  };
  const openAlerts = alerts.items.filter((a) => a.status === 'open');
  return (
    <div className="space-y-4" data-testid="lr2-scanner">
      <div className="rounded-2xl border border-border bg-card p-4 flex items-center justify-between">
        <div className="text-sm">
          <div className="font-semibold flex items-center gap-1.5"><Radio className="w-4 h-4" style={{ color: PRIMARY }} />{bi('Фоновий сканер', 'Background scanner')}</div>
          <div className="text-xs text-muted-foreground">{bi('інтервал', 'interval')}: {scans.interval_seconds}s · {bi('останні', 'last')} {scans.count} {bi('сканів', 'scans')}</div>
        </div>
        <button onClick={runNow} disabled={busy} data-testid="lr2-scan-now"
          className="h-9 px-3 rounded-lg text-sm text-white hover:opacity-90 inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} {bi('Запустити скан', 'Run scan')}
        </button>
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between">
          <span className="font-semibold text-sm flex items-center gap-1.5"><Siren className="w-4 h-4 text-rose-600" />{bi('Критичні алерти', 'Critical alerts')}</span>
          <span className="text-xs">{openAlerts.length} {bi('відкритих', 'open')} · {alerts.count} {bi('усього', 'total')}</span>
        </div>
        {alerts.items.length === 0 ? <p className="p-5 text-xs text-muted-foreground">{bi('Алертів немає.', 'No alerts.')}</p> : (
          <ul className="divide-y divide-border max-h-72 overflow-auto">
            {alerts.items.map((a) => (
              <li key={a.id} className="px-5 py-3 flex items-start gap-3" data-testid={`alert-${a.kind}`}>
                <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full mt-0.5 ${a.status === 'open' ? 'bg-rose-100 text-rose-700' : a.status === 'acked' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>{a.status}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium flex items-center gap-2"><Severity s={a.severity} />{a.title}</div>
                  <div className="text-xs text-muted-foreground truncate">{a.message}</div>
                  <div className="text-[10px] text-muted-foreground mt-1">{bi('відкрито', 'opened')}: {formatDateUk(a.opened_at)} · {bi('востаннє', 'last seen')}: {formatDateUk(a.last_seen_at)}{a.acked_at ? ` · ${bi('підтв.', 'acked by')} ${a.acked_by} ${formatDateUk(a.acked_at)}` : ''}</div>
                </div>
                {a.status === 'open' && (
                  <button onClick={() => ack(a.id)} data-testid={`ack-${a.id}`} className="h-7 px-2 rounded text-[11px] border border-border hover:bg-muted inline-flex items-center gap-1"><BellOff className="w-3 h-3" />{bi('Підтвердити', 'Ack')}</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Історія сканів', 'Scan history')} ({bi('останні', 'last')} {scans.items.length})</div>
        {scans.items.length === 0 ? <p className="p-5 text-xs text-muted-foreground">{bi('Сканів ще не було. Натисніть «Запустити скан», або зачекайте на фоновий запуск.', 'No scans yet. Press “Run scan”, or wait for the background run.')}</p> : (
          <table className="w-full text-xs">
            <thead className="bg-muted/40"><tr>
              <th className="text-left px-3 py-2">{bi('Час', 'Time')}</th><th className="text-left px-3 py-2">{bi('Причина', 'Reason')}</th>
              <th className="text-right px-3 py-2">{bi('Бал', 'Score')}</th><th className="text-right px-3 py-2">Inv F</th>
              <th className="text-right px-3 py-2">Perm V</th><th className="text-right px-3 py-2">{bi('Конфлікти', 'Conflicts')}</th>
              <th className="text-right px-3 py-2">Demo</th>
            </tr></thead>
            <tbody>{scans.items.map((s) => (
              <tr key={s.id} className="border-t border-border">
                <td className="px-3 py-2">{formatDateUk(s.at)}</td>
                <td className="px-3 py-2 text-muted-foreground">{s.reason}</td>
                <td className="px-3 py-2 text-right font-mono">{s.score?.total}/{s.score?.max} <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${grade2color(s.score?.grade)}`}>{s.score?.grade}</span></td>
                <td className={`px-3 py-2 text-right font-mono ${s.summary?.invariant_failed > 0 ? 'text-rose-700' : ''}`}>{s.summary?.invariant_failed}</td>
                <td className={`px-3 py-2 text-right font-mono ${s.summary?.permission_violations > 0 ? 'text-rose-700' : ''}`}>{s.summary?.permission_violations}</td>
                <td className={`px-3 py-2 text-right font-mono ${s.summary?.conflicts > 0 ? 'text-rose-700' : ''}`}>{s.summary?.conflicts}</td>
                <td className="px-3 py-2 text-right font-mono text-muted-foreground">{s.summary?.demo_rows}</td>
              </tr>))}
            </tbody>
          </table>
        )}
      </div>

      {denials && denials.items.length > 0 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/30 overflow-hidden">
          <div className="px-5 py-3 border-b border-amber-200 font-semibold text-sm">{bi('Відмови в доступі', 'Permission denials')} ({bi('останні', 'last')} {denials.items.length})</div>
          <ul className="divide-y divide-amber-200 max-h-48 overflow-auto">
            {denials.items.map((d) => (
              <li key={d.id} className="px-5 py-2 text-xs">
                <span className="font-mono text-[11px] text-amber-900">{d.email} ({d.effective_role})</span> → <code>{d.resource}/{d.action}</code> · {formatDateUk(d.at)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── LR2.9 PRODUCTION SWITCH VIEW ──────────────────────────────────────────
function ProductionView({ data, reload }) {
  const { bi } = useLang();
  if (!data) return <Spinner />;
  return (
    <div className="space-y-4" data-testid="lr2-production">
      <div className={`rounded-2xl border p-5 ${data.is_production ? 'border-rose-200 bg-rose-50/40' : 'border-sky-200 bg-sky-50/40'}`}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">LUMEN_ENV</div>
            <h3 className="text-2xl font-bold">{data.env.toUpperCase()}</h3>
            <p className="text-xs text-muted-foreground mt-1">{bi('Перемикач рівня коду — інших налаштувань не потрібно. Перевизначте змінну середовища', 'Code-level switch — no other settings needed. Override the environment variable')} <code>LUMEN_ENV</code> {bi('і перезапустіть backend.', 'and restart the backend.')}</p>
          </div>
          <ToggleRight className={`w-12 h-12 ${data.is_production ? 'text-rose-600' : 'text-sky-600'}`} />
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="font-semibold text-sm mb-3">{bi('Контролі', 'Controls')}</h3>
          <ul className="space-y-2 text-sm">
            {Object.entries(data.controls).map(([k, v]) => (
              <li key={k} className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">{k}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${typeof v === 'boolean' ? (v ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600') : 'bg-slate-100 text-slate-600'}`}>{String(v)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="font-semibold text-sm mb-3">{bi('Наявні демо-дані', 'Demo data present')}</h3>
          <ul className="space-y-1 text-xs">
            {Object.entries(data.demo_present).map(([k, v]) => (
              <li key={k} className="flex justify-between"><span className="text-muted-foreground">{k}</span><b className={v > 0 ? 'text-amber-700' : 'text-muted-foreground'}>{v}</b></li>
            ))}
          </ul>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-3 border-b border-border font-semibold text-sm">{bi('Чек-лист production', 'Production checklist')}</div>
        <ul className="divide-y divide-border">
          {data.checklist.map((c) => (
            <li key={c.id} className="px-5 py-3 flex items-start gap-3">
              {c.ok ? <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" /> : <XCircle className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{c.title}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{c.details}</div>
              </div>
              {c.required_for_launch && <span className="text-[10px] uppercase px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">{bi('обовʼязково', 'required')}</span>}
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-2xl border border-amber-200 bg-amber-50/30 p-4 text-xs space-y-1.5">
        <div className="font-semibold text-amber-900">{bi('Як виставити production', 'How to set production')}</div>
        <ol className="list-decimal list-inside space-y-0.5 text-amber-800">
          <li>{bi('Прибрати демо-дані:', 'Remove demo data:')} <code>POST /admin/launch-readiness/demo-data/quarantine</code> {bi('з', 'with')} <code>confirm:"DELETE-DEMO"</code></li>
          <li>{bi('Створити справжнього адміна через CLI або захищений seed', 'Create a real admin via CLI or a protected seed')}</li>
          <li>{bi('Виставити', 'Set')} <code>LUMEN_ENV=production</code> {bi('та', 'and')} <code>CORS_ORIGINS=https://lumen.your-domain</code></li>
          <li>{bi('Виставити', 'Set')} <code>LUMEN_RATE_LIMIT_ENABLED=true</code></li>
          <li>{bi('Перезапустити backend. Quick-access користувачі більше не сідаються, демо-seed повністю вимкнено.', 'Restart the backend. Quick-access users are no longer seeded, demo seed is fully disabled.')}</li>
        </ol>
      </div>
    </div>
  );
}

// ── LR2.10 SECURITY VIEW ──────────────────────────────────────────────────
function SecurityView({ data }) {
  const { bi } = useLang();
  const [rl, setRl] = useState(null);
  useEffect(() => { lumen.get('/admin/launch-readiness/rate-limit/stats').then(r => setRl(r.data)).catch(() => {}); }, []);
  if (!data) return <Spinner />;
  const c = data.counts;
  return (
    <div className="space-y-4" data-testid="lr2-security">
      <div className="rounded-2xl border border-border bg-card p-5 flex items-center gap-5">
        <div className={`w-16 h-16 rounded-full border-4 flex items-center justify-center text-xl font-bold ${data.score >= 90 ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : data.score >= 70 ? 'bg-amber-100 text-amber-700 border-amber-200' : 'bg-rose-100 text-rose-700 border-rose-200'}`}>
          {data.score}
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{bi('Бал безпеки', 'Security score')} · {data.score}/{data.max}</div>
          <div className="text-xs text-muted-foreground">{c.passing}/{c.total} {bi('перевірок пройдено', 'checks passing')} · critical {c.by_severity.critical} · high {c.by_severity.high} · medium {c.by_severity.medium} · low {c.by_severity.low}</div>
        </div>
      </div>
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <ul className="divide-y divide-border">
          {data.items.map((i) => (
            <li key={i.id} className="px-5 py-3 flex items-start gap-3" data-testid={`sec-${i.id}`}>
              {i.ok ? <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" /> : <XCircle className="w-5 h-5 text-rose-600 mt-0.5 shrink-0" />}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium flex items-center gap-2">{i.title} <Severity s={i.severity} /></div>
                <div className="text-xs text-muted-foreground mt-0.5">{bi('доказ', 'evidence')}: <code className="text-[11px]">{Array.isArray(i.evidence) ? i.evidence.join(', ') || '—' : String(i.evidence)}</code></div>
                {!i.ok && <div className="text-xs text-amber-700 mt-0.5">{i.hint}</div>}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {rl && (
        <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="rate-limit-panel">
          <div className="px-5 py-3 border-b border-border flex items-center justify-between">
            <span className="font-semibold text-sm flex items-center gap-1.5">
              <Lock className="w-4 h-4" style={{ color: PRIMARY }} />{bi('Rate-limit middleware', 'Rate-limit middleware')}
            </span>
            <div className="flex items-center gap-2 text-xs">
              <span className={`px-2 py-0.5 rounded-full ${rl.middleware_mounted ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>{rl.middleware_mounted ? bi('встановлено', 'mounted') : bi('не встановлено', 'not mounted')}</span>
              <span className={`px-2 py-0.5 rounded-full ${rl.enforce_enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{rl.enforce_enabled ? 'enforce' : 'observe'}</span>
              <span className="text-muted-foreground">{rl.rules_count} {bi('правил', 'rules')} · {bi('вікно', 'window')} {rl.window_seconds}s</span>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 text-sm">
            <Stat label={bi('Запитів', 'Requests')} value={rl.totals.requests} />
            <Stat label={bi('Заблоковано (enforce)', 'Blocked (enforce)')} value={rl.totals.blocked} bad={rl.totals.blocked > 0} />
            <Stat label={bi('Було б заблоковано (observe)', 'Would-block (observe)')} value={rl.totals.observed_blocks} />
            <Stat label={bi('Унікальних клієнтів', 'Unique clients')} value={rl.totals.unique_clients} />
          </div>
          {rl.metrics.length > 0 && (
            <table className="w-full text-xs">
              <thead className="bg-muted/40"><tr>
                <th className="text-left px-3 py-2">{bi('Правило', 'Rule')}</th><th className="text-left px-3 py-2">{bi('Префікс', 'Prefix')}</th>
                <th className="text-right px-3 py-2">{bi('Ліміт/хв', 'Limit/min')}</th><th className="text-right px-3 py-2">{bi('Запитів', 'Requests')}</th>
                <th className="text-right px-3 py-2">{bi('Заблок.', 'Blocked')}</th><th className="text-right px-3 py-2">{bi('Клієнтів', 'Clients')}</th>
                <th className="text-left px-3 py-2">{bi('Останнє спрацювання', 'Last triggered')}</th>
              </tr></thead>
              <tbody>{rl.metrics.map((m) => (
                <tr key={m.id} className="border-t border-border">
                  <td className="px-3 py-2 font-mono text-[11px]">{m.id}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">{m.prefix}</td>
                  <td className="px-3 py-2 text-right font-mono">{m.limit}</td>
                  <td className="px-3 py-2 text-right font-mono">{m.requests}</td>
                  <td className={`px-3 py-2 text-right font-mono ${m.blocked > 0 ? 'text-rose-700 font-semibold' : ''}`}>{m.blocked}</td>
                  <td className="px-3 py-2 text-right font-mono">{m.unique_clients}</td>
                  <td className="px-3 py-2 text-[10px] text-muted-foreground">{m.last_triggered_at ? formatDateUk(m.last_triggered_at) : '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
