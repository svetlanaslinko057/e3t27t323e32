/**
 * AdminCommandCenter — H1.3 Controlled Beta single operational panel.
 *
 * User choices (locked):
 *   1c — all 9 sources + Beta-1 Checklist
 *   2b — polling 30s + manual Refresh (no WebSocket)
 *   3c — checklist auto-detect + manual override
 *   4b — critical + warning alerts only
 *   5a — admin-only access
 *
 * Layout (top-down):
 *   1. Launch Status banner (CONTROLLED BETA · Readiness · Security · Critical · Warnings · Beta-1 N/7)
 *   2. Progress bar [■■■□□□□] N / 7
 *   3. 3×3 grid of widgets:
 *        Treasury Pulse · LR2 Score · Open Alerts (Critical+Warning)
 *        Pending KYC · Pending Compliance · Pending Funding
 *        Pending Reconciliation · Pending Capital Calls · Pending Distributions
 *   4. Beta-1 Checklist (7 milestones with override controls)
 *   5. Alerts feed (critical + warning only)
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { lumen, lumenError, usdFromUah } from '@/lib/lumenApi';
import {
  Activity, AlertTriangle, AlertCircle, CheckCircle2, RefreshCw, Loader2,
  Banknote, ShieldCheck, Users, FileWarning, Repeat, Coins, CircleDollarSign,
  Award, ClipboardCheck, Clock, Pencil, XCircle, MinusCircle,
} from 'lucide-react';
import { useFundingLang, useFundingT } from '@/i18n/funding';

const POLL_INTERVAL_MS = 30_000;

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString(undefined, {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch (_e) { return iso; }
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_e) { return iso; }
}

function fmtMoney(value, currency = 'EUR') {
  if (value == null) return '—';
  try {
    return new Intl.NumberFormat('uk-UA', {
      style: 'currency', currency, maximumFractionDigits: 0,
    }).format(value);
  } catch (_e) { return `${value}`; }
}

function humaniseSec(sec) {
  if (sec == null) return '—';
  if (sec < 60) return `${Math.round(sec * 10) / 10}s`;
  if (sec < 3600) return `${Math.round(sec / 6) / 10}min`;
  return `${Math.round(sec / 360) / 10}h`;
}

function percent(v) {
  if (v == null) return '—';
  return `${Math.round((v || 0) * 1000) / 10}%`;
}

export default function AdminCommandCenter() {
  const { lang } = useFundingLang();
  const t = useFundingT(lang);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [alertFilter, setAlertFilter] = useState('all');
  const intervalRef = useRef(null);

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const r = await lumen.get('/admin/beta/command-center');
      setData(r.data);
      setLastUpdated(new Date());
      setErr('');
    } catch (e) {
      setErr(lumenError(e, t('beta.error.load')));
    } finally {
      if (manual) setRefreshing(false);
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
    intervalRef.current = setInterval(() => load(false), POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  const ls = data?.launch_status;
  const checklist = data?.beta1_checklist;
  const completedPct = ls
    ? Math.round((ls.beta1_progress_completed / ls.beta1_progress_total) * 100)
    : 0;

  const filteredAlerts = (data?.open_alerts || []).filter((a) => (
    alertFilter === 'all' ? true : a.severity === alertFilter
  ));

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-command-center">
      {/* Header */}
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">{t('command_center.eyebrow')}</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-3">
            <Activity className="w-7 h-7 text-[#2E5D4F] dark:text-[#4FA98C]" />
            {t('beta.title')}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-3xl">{t('beta.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5">
            <Clock className="w-3 h-3" />
            {t('beta.last_updated')}: <span className="font-mono text-foreground" data-testid="cc-last-updated">{fmtTime(lastUpdated)}</span>
          </div>
          <span className="text-[10px] uppercase tracking-wider px-2 py-1 rounded-md bg-muted/40 text-muted-foreground">
            {t('beta.polling')}
          </span>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted/40 text-sm disabled:opacity-50"
            data-testid="cc-refresh"
          >
            {refreshing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {t('beta.refresh')}
          </button>
        </div>
      </header>

      {loading && !data && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}
        </div>
      )}
      {err && (
        <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200 border border-rose-200 dark:border-rose-900 mb-4" data-testid="cc-error">
          {err}
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {/* ─── 1. Launch Status banner ─── */}
          <LaunchStatusBanner ls={ls} pct={completedPct} t={t} />

          {/* ─── 2. 9 sources grid ─── */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <TreasuryWidget treasury={data.treasury_pulse} t={t} />
            <Lr2Widget lr2={data.lr2} scanner={ls?.scanner_running} t={t} />
            <AlertsWidget alerts={data.open_alerts} t={t} />

            <KycWidget data={data.pending_kyc} t={t} />
            <ComplianceWidget data={data.pending_compliance} t={t} />
            <FundingWidget data={data.pending_funding} t={t} />

            <ReconWidget data={data.pending_reconciliation} t={t} />
            <CapitalCallsWidget data={data.pending_capital_calls} t={t} />
            <DistributionsWidget data={data.pending_distributions} t={t} />
          </div>

          {/* ─── 3. Beta-1 Checklist ─── */}
          <BetaChecklistSection
            checklist={checklist}
            lang={lang}
            t={t}
            onAfterChange={() => load(true)}
          />

          {/* ─── 4. Alerts feed ─── */}
          <AlertsSection
            alerts={data.open_alerts}
            filter={alertFilter}
            setFilter={setAlertFilter}
            filtered={filteredAlerts}
            t={t}
          />
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Sub-components
   ───────────────────────────────────────────────────────────────────────── */

function LaunchStatusBanner({ ls, pct, t }) {
  if (!ls) return null;
  const readinessTone = ls.readiness_score >= 95 ? 'emerald'
    : ls.readiness_score >= 85 ? 'indigo' : ls.readiness_score >= 70 ? 'amber' : 'rose';
  const securityTone = ls.security_score >= 95 ? 'emerald'
    : ls.security_score >= 85 ? 'indigo' : ls.security_score >= 70 ? 'amber' : 'rose';
  const critTone = ls.open_critical_alerts_count === 0 ? 'emerald' : 'rose';
  const warnTone = ls.open_warnings_count === 0 ? 'emerald' : 'amber';
  return (
    <section
      className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-muted/30 via-card to-card p-6 md:p-8"
      data-testid="cc-launch-status"
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#2E5D4F] text-white text-[11px] font-semibold tracking-wider uppercase shadow-sm">
            <Activity className="w-3.5 h-3.5" />
            {t('beta.phase.label')}
          </span>
          <p className="text-xs text-muted-foreground">{t('beta.subtitle').split('.')[0]}.</p>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 md:grid-cols-5 gap-3">
        <Metric tone={readinessTone} label={t('beta.launch.readiness')}
          value={`${ls.readiness_score} / ${ls.readiness_max}`}
          sub={ls.readiness_grade ? `Grade ${ls.readiness_grade}` : null}
          testid="ls-readiness" />
        <Metric tone={securityTone} label={t('beta.launch.security')}
          value={`${ls.security_score} / ${ls.security_max}`}
          testid="ls-security" />
        <Metric tone={critTone} label={t('beta.launch.critical')}
          value={ls.open_critical_alerts_count}
          icon={AlertCircle}
          testid="ls-critical" />
        <Metric tone={warnTone} label={t('beta.launch.warnings')}
          value={ls.open_warnings_count}
          icon={AlertTriangle}
          testid="ls-warnings" />
        <Metric tone="indigo" label={t('beta.launch.beta1')}
          value={`${ls.beta1_progress_completed} / ${ls.beta1_progress_total}`}
          sub={`${pct}%`}
          icon={ClipboardCheck}
          testid="ls-beta1" />
      </div>

      <div className="mt-4">
        <ProgressBar completed={ls.beta1_progress_completed} total={ls.beta1_progress_total} t={t} />
      </div>
    </section>
  );
}

function ProgressBar({ completed, total, t }) {
  const pct = total ? Math.round((completed / total) * 100) : 0;
  const blocks = Array.from({ length: total }, (_, i) => i < completed);
  return (
    <div data-testid="cc-progress-bar">
      <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
        <span className="font-mono">
          {blocks.map((on, i) => (
            <span key={i} className={on ? 'text-amber-600 dark:text-amber-400' : 'opacity-30'}>
              {on ? '■' : '□'}
            </span>
          ))}
        </span>
        <span><strong className="text-foreground">{completed}</strong> / {total} {t('beta.launch.milestones')}</span>
      </div>
      <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const TONE = {
  default: 'bg-muted/30 text-foreground',
  emerald: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200 border-emerald-200 dark:border-emerald-900/60',
  indigo:  'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-800 dark:text-indigo-200 border-indigo-200 dark:border-indigo-900/60',
  rose:    'bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200 border-rose-200 dark:border-rose-900/60',
  amber:   'bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200 border-amber-200 dark:border-amber-900/60',
};

function Metric({ label, value, sub, tone = 'default', icon: Icon, testid }) {
  return (
    <div className={`rounded-xl border p-3 ${TONE[tone]}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider opacity-80">
        {Icon && <Icon className="w-3 h-3" />}
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tracking-tight">{value ?? '—'}</div>
      {sub && <div className="text-[11px] mt-0.5 opacity-80">{sub}</div>}
    </div>
  );
}

function Widget({ title, icon: Icon, accent, children, testid }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold">
          {Icon && <Icon className={`w-4 h-4 ${accent || 'text-foreground'}`} />}
          {title}
        </div>
      </div>
      {children}
    </div>
  );
}

function TreasuryWidget({ treasury, t }) {
  if (!treasury) return <Widget title={t('beta.section.treasury')} icon={Banknote} accent="text-amber-600" testid="w-treasury"><Empty t={t} /></Widget>;
  return (
    <Widget title={t('beta.section.treasury')} icon={Banknote} accent="text-amber-600 dark:text-amber-400" testid="w-treasury">
      <div className="grid grid-cols-2 gap-2 text-sm">
        <Cell label={t('treasury.kpi.pending_review')} value={treasury.pending_review_count} />
        <Cell label={t('treasury.kpi.matched')} value={treasury.matched_count} />
        <Cell label={t('treasury.kpi.confirmed')} value={treasury.confirmed_count} tone="emerald" />
        <Cell label={t('treasury.kpi.rejected')} value={treasury.rejected_count} tone={treasury.rejected_count ? 'rose' : 'default'} />
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm pt-2 border-t border-border">
        <Cell label={t('treasury.kpi.today_volume')} value={fmtMoney(treasury.today_volume_total)} />
        <Cell label={t('treasury.kpi.volume_30d')} value={fmtMoney(treasury.volume_30d_total)} />
        <Cell label={t('treasury.kpi.time_to_confirm')} value={humaniseSec(treasury.time_to_confirm_avg_seconds)} />
        <Cell label={t('treasury.kpi.exception_rate')} value={percent(treasury.exception_rate)}
              tone={treasury.exception_rate > 0.1 ? 'rose' : 'default'} />
      </div>
    </Widget>
  );
}

function Lr2Widget({ lr2, scanner, t }) {
  const tone = (lr2?.score || 0) >= 95 ? 'emerald'
    : (lr2?.score || 0) >= 85 ? 'indigo' : (lr2?.score || 0) >= 70 ? 'amber' : 'rose';
  return (
    <Widget title={t('beta.section.lr2')} icon={ShieldCheck} accent="text-indigo-600 dark:text-indigo-400" testid="w-lr2">
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-bold tracking-tight" data-testid="w-lr2-score">{lr2?.score ?? '—'}</span>
        <span className="text-sm text-muted-foreground">/ {lr2?.max ?? 100}</span>
        <span className={`ml-auto text-xs font-bold px-2 py-0.5 rounded-full ${TONE[tone]}`}>{t('beta.kpi.lr2_grade')}: {lr2?.grade || '—'}</span>
      </div>
      <div className="space-y-1">
        {(lr2?.parts || []).map((p) => (
          <div key={p.key} className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span className="capitalize">{p.key}</span>
            <span className="font-mono">{p.score}/{p.max}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between pt-2 border-t border-border text-xs">
        <span className="text-muted-foreground">{t('beta.kpi.scanner')}</span>
        {scanner
          ? <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold"><CheckCircle2 className="w-3 h-3" /> {t('beta.scanner.on')}</span>
          : <span className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400 font-semibold"><XCircle className="w-3 h-3" /> {t('beta.scanner.off')}</span>}
      </div>
    </Widget>
  );
}

function AlertsWidget({ alerts, t }) {
  const crit = (alerts || []).filter((a) => a.severity === 'critical').length;
  const warn = (alerts || []).filter((a) => a.severity === 'warning').length;
  return (
    <Widget title={t('beta.section.alerts')} icon={AlertTriangle} accent={crit ? 'text-rose-600' : warn ? 'text-amber-600' : 'text-emerald-600'} testid="w-alerts">
      <div className="grid grid-cols-2 gap-2">
        <BigCell tone={crit ? 'rose' : 'emerald'} label={t('beta.alerts.severity.critical')} value={crit} icon={AlertCircle} testid="w-alerts-critical" />
        <BigCell tone={warn ? 'amber' : 'emerald'} label={t('beta.alerts.severity.warning')} value={warn} icon={AlertTriangle} testid="w-alerts-warning" />
      </div>
      <div className="pt-2 border-t border-border max-h-32 overflow-y-auto space-y-1">
        {(alerts || []).slice(0, 4).map((a, i) => (
          <div key={`${a.kind}-${i}`} className="flex items-start gap-2 text-[11px]">
            <SeverityDot sev={a.severity} />
            <div className="min-w-0 flex-1">
              <div className="font-medium truncate">{a.message}</div>
              <div className="text-muted-foreground text-[10px]">{a.kind}</div>
            </div>
          </div>
        ))}
        {(!alerts || alerts.length === 0) && (
          <div className="text-xs text-muted-foreground">{t('beta.alerts.empty')}</div>
        )}
      </div>
    </Widget>
  );
}

function KycWidget({ data, t }) {
  return (
    <Widget title={t('beta.section.kyc')} icon={Users} accent="text-indigo-600 dark:text-indigo-400" testid="w-kyc">
      <div className="grid grid-cols-2 gap-2">
        <BigCell tone="default" label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-kyc-total" />
        <BigCell tone={data?.stale_24h ? 'amber' : 'default'} label={t('beta.kpi.stale')} value={data?.stale_24h ?? 0} testid="w-kyc-stale" />
      </div>
    </Widget>
  );
}

function ComplianceWidget({ data, t }) {
  return (
    <Widget title={t('beta.section.compliance')} icon={ShieldCheck} accent="text-emerald-600 dark:text-emerald-400" testid="w-compliance">
      <div className="grid grid-cols-2 gap-2">
        <BigCell tone="default" label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-compliance-total" />
        <BigCell tone={data?.expired ? 'rose' : 'default'} label={t('beta.kpi.expired')} value={data?.expired ?? 0} testid="w-compliance-expired" />
        <BigCell tone={data?.expiring_soon ? 'amber' : 'default'} label={t('beta.kpi.expiring')} value={data?.expiring_soon ?? 0} testid="w-compliance-expiring" />
        <BigCell tone={data?.stale_24h ? 'amber' : 'default'} label={t('beta.kpi.stale')} value={data?.stale_24h ?? 0} testid="w-compliance-stale" />
      </div>
    </Widget>
  );
}

function FundingWidget({ data, t }) {
  return (
    <Widget title={t('beta.section.funding')} icon={Banknote} accent="text-amber-600 dark:text-amber-400" testid="w-funding">
      <BigCell tone={data?.total ? 'amber' : 'default'} label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-funding-total" />
      <div className="space-y-1 pt-2 border-t border-border max-h-32 overflow-y-auto">
        {(data?.samples || []).slice(0, 4).map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="font-mono truncate">{s.reference || s.id}</span>
            <span className="text-muted-foreground">{fmtMoney(s.amount, s.currency || 'EUR')}</span>
          </div>
        ))}
        {(!data?.samples || data.samples.length === 0) && (
          <div className="text-xs text-muted-foreground">{t('common.no_data')}</div>
        )}
      </div>
    </Widget>
  );
}

function ReconWidget({ data, t }) {
  const byFlag = data?.by_flag || {};
  return (
    <Widget title={t('beta.section.recon')} icon={FileWarning} accent="text-rose-600 dark:text-rose-400" testid="w-recon">
      <BigCell tone={data?.total ? 'amber' : 'default'} label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-recon-total" />
      <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border text-[11px]">
        <Cell label="missing_ref" value={byFlag.missing_reference || 0} tone={byFlag.missing_reference ? 'rose' : 'default'} />
        <Cell label="curr. mismatch" value={byFlag.currency_mismatch || 0} tone={byFlag.currency_mismatch ? 'rose' : 'default'} />
        <Cell label="amount mismatch" value={byFlag.amount_mismatch || 0} tone={byFlag.amount_mismatch ? 'rose' : 'default'} />
        <Cell label="unmatched" value={byFlag.unmatched || 0} tone={byFlag.unmatched ? 'amber' : 'default'} />
      </div>
    </Widget>
  );
}

function CapitalCallsWidget({ data, t }) {
  return (
    <Widget title={t('beta.section.capital_calls')} icon={CircleDollarSign} accent="text-indigo-600 dark:text-indigo-400" testid="w-capital-calls">
      <div className="grid grid-cols-1 gap-2">
        <BigCell tone={data?.total ? 'amber' : 'default'} label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-cc-total" />
        <Cell label={t('beta.kpi.value')} value={data?.unpaid_value_uah ? fmtMoney(usdFromUah(data.unpaid_value_uah), 'USD') : '—'} />
      </div>
    </Widget>
  );
}

function DistributionsWidget({ data, t }) {
  return (
    <Widget title={t('beta.section.distributions')} icon={Coins} accent="text-emerald-600 dark:text-emerald-400" testid="w-distributions">
      <div className="grid grid-cols-1 gap-2">
        <BigCell tone={data?.total ? 'amber' : 'default'} label={t('beta.kpi.pending')} value={data?.total ?? 0} testid="w-dist-total" />
        <Cell label={t('beta.kpi.value')} value={data?.pending_value_uah ? fmtMoney(usdFromUah(data.pending_value_uah), 'USD') : '—'} />
      </div>
    </Widget>
  );
}

/* ─── Beta-1 Checklist ─── */

function BetaChecklistSection({ checklist, lang, t, onAfterChange }) {
  if (!checklist) return null;
  return (
    <section className="rounded-xl border border-border bg-card p-5" data-testid="cc-checklist">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <h2 className="text-base font-semibold">{t('beta.section.checklist')}</h2>
          <span className="text-xs text-muted-foreground">
            ({checklist.completed} / {checklist.total})
          </span>
        </div>
      </div>
      <div className="space-y-2">
        {(checklist.items || []).map((it) => (
          <MilestoneRow
            key={it.milestone_id}
            item={it}
            label={lang === 'en' ? it.label_en : it.label_uk}
            t={t}
            onAfterChange={onAfterChange}
          />
        ))}
      </div>
    </section>
  );
}

function MilestoneRow({ item, label, t, onAfterChange }) {
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState(item.notes || '');
  const [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState(item.status === 'not_applicable' ? 'not_applicable' : 'completed');

  const submit = async (status) => {
    setBusy(true);
    try {
      await lumen.post(`/admin/beta/checklist/${item.milestone_id}/override`, {
        status, notes: notes || null,
      });
      setEditing(false);
      if (onAfterChange) await onAfterChange();
    } finally { setBusy(false); }
  };

  const clearOverride = async () => {
    setBusy(true);
    try {
      await lumen.delete(`/admin/beta/checklist/${item.milestone_id}/override`);
      setEditing(false);
      setNotes('');
      if (onAfterChange) await onAfterChange();
    } finally { setBusy(false); }
  };

  const isCompleted = item.status === 'completed';
  const isNA = item.status === 'not_applicable';
  const isOverridden = !!item.overridden_by;

  return (
    <div className="border border-border rounded-lg p-3 hover:bg-muted/20 transition-colors" data-testid={`milestone-${item.milestone_id}`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          {isCompleted
            ? <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            : isNA
            ? <MinusCircle className="w-5 h-5 text-muted-foreground" />
            : <div className="w-5 h-5 rounded-full border-2 border-muted-foreground/40" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{label}</span>
            <span className="font-mono text-[10px] text-muted-foreground">{item.milestone_id}</span>
            {isOverridden && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/40 text-indigo-800 dark:text-indigo-200 font-semibold">
                OVERRIDE
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
            <span><span className="opacity-70">{t('common.status')}:</span> <strong className="text-foreground">{t(`beta.checklist.status.${item.status}`)}</strong></span>
            {item.detected_at && (
              <span><span className="opacity-70">{t('beta.checklist.detected_at')}:</span> <span className="font-mono">{fmtDateTime(item.detected_at)}</span></span>
            )}
            {item.detected_label && (
              <span><span className="opacity-70">{t('beta.checklist.entity')}:</span> <span className="font-mono">{item.detected_label}</span></span>
            )}
            {isOverridden && (
              <span><span className="opacity-70">{t('beta.checklist.overridden_by')}:</span> <strong>{item.overridden_by}</strong> · {fmtDateTime(item.overridden_at)}</span>
            )}
          </div>
          {item.notes && !editing && (
            <div className="mt-1 text-xs italic text-muted-foreground">&ldquo;{item.notes}&rdquo;</div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="p-1.5 rounded hover:bg-muted/40 text-muted-foreground"
              title={t('beta.checklist.override')}
              data-testid={`override-btn-${item.milestone_id}`}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          )}
          {isOverridden && !editing && (
            <button
              onClick={clearOverride}
              disabled={busy}
              className="p-1.5 rounded hover:bg-muted/40 text-rose-600 dark:text-rose-400 disabled:opacity-50"
              title={t('beta.checklist.clear')}
              data-testid={`clear-btn-${item.milestone_id}`}
            >
              <XCircle className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {editing && (
        <div className="mt-3 pl-8 space-y-2" data-testid={`override-form-${item.milestone_id}`}>
          <div className="flex flex-wrap gap-2">
            {[
              { v: 'completed',      label: t('beta.checklist.action.mark_done') },
              { v: 'pending',        label: t('beta.checklist.action.mark_pending') },
              { v: 'not_applicable', label: t('beta.checklist.action.mark_na') },
            ].map((opt) => (
              <button
                key={opt.v}
                type="button"
                onClick={() => setChosen(opt.v)}
                className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                  chosen === opt.v
                    ? 'bg-foreground text-background border-foreground'
                    : 'border-border hover:bg-muted/40'
                }`}
                data-testid={`override-status-${item.milestone_id}-${opt.v}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={t('beta.checklist.notes.placeholder')}
            rows={2}
            className="w-full text-xs px-2 py-1.5 rounded border border-border bg-background"
            data-testid={`override-notes-${item.milestone_id}`}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => submit(chosen)}
              disabled={busy}
              className="inline-flex items-center gap-1 px-3 py-1 rounded-md bg-foreground text-background text-xs font-semibold hover:opacity-90 disabled:opacity-40"
              data-testid={`override-save-${item.milestone_id}`}
            >
              {busy && <Loader2 className="w-3 h-3 animate-spin" />}
              {t('beta.checklist.override')}
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={busy}
              className="px-3 py-1 rounded-md border border-border text-xs hover:bg-muted/40 disabled:opacity-50"
              data-testid={`override-cancel-${item.milestone_id}`}
            >
              {t('common.cancel') || 'Cancel'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Alerts feed ─── */

function AlertsSection({ alerts, filter, setFilter, filtered, t }) {
  const crit = (alerts || []).filter((a) => a.severity === 'critical').length;
  const warn = (alerts || []).filter((a) => a.severity === 'warning').length;
  return (
    <section className="rounded-xl border border-border bg-card p-5" data-testid="cc-alerts-feed">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <h2 className="text-base font-semibold">{t('beta.section.alerts')}</h2>
          <span className="text-xs text-muted-foreground">({(alerts || []).length})</span>
        </div>
        <div className="inline-flex items-center gap-1 p-1 rounded-lg border border-border bg-background text-xs" data-testid="cc-alerts-filter">
          {[
            { v: 'all',      label: `${t('beta.alerts.all')} (${(alerts || []).length})` },
            { v: 'critical', label: `${t('beta.alerts.severity.critical')} (${crit})` },
            { v: 'warning',  label: `${t('beta.alerts.severity.warning')} (${warn})` },
          ].map((opt) => (
            <button
              key={opt.v}
              onClick={() => setFilter(opt.v)}
              className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                filter === opt.v ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
              }`}
              data-testid={`cc-alerts-filter-${opt.v}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground" data-testid="cc-alerts-empty">
          <CheckCircle2 className="w-6 h-6 mx-auto mb-2 text-emerald-500" />
          {t('beta.alerts.empty')}
        </div>
      ) : (
        <ul className="space-y-2">
          {filtered.map((a, i) => (
            <li
              key={`${a.kind}-${i}`}
              className={`flex items-start gap-3 p-3 rounded-lg border ${TONE[a.severity === 'critical' ? 'rose' : 'amber']}`}
              data-testid={`cc-alert-row`}
            >
              <SeverityDot sev={a.severity} big />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold uppercase tracking-wider">
                    {a.severity === 'critical' ? t('beta.alerts.severity.critical') : t('beta.alerts.severity.warning')}
                  </span>
                  <span className="font-mono text-[10px] opacity-70">{a.kind}</span>
                </div>
                <div className="mt-1 text-sm font-medium">{a.message}</div>
                <div className="text-[11px] opacity-70 mt-0.5 font-mono">{fmtDateTime(a.raised_at)}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ─── Small atoms ─── */

function Cell({ label, value, tone = 'default' }) {
  return (
    <div className={`rounded-md px-2 py-1.5 text-xs ${TONE[tone]}`}>
      <div className="text-[9px] uppercase tracking-wider opacity-75">{label}</div>
      <div className="font-semibold tabular-nums">{value ?? '—'}</div>
    </div>
  );
}

function BigCell({ label, value, tone = 'default', icon: Icon, testid }) {
  return (
    <div className={`rounded-lg border p-2.5 ${TONE[tone]}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider opacity-80">
        {Icon && <Icon className="w-3 h-3" />}
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value ?? '—'}</div>
    </div>
  );
}

function SeverityDot({ sev, big }) {
  const cls = sev === 'critical' ? 'bg-rose-500' : 'bg-amber-500';
  const size = big ? 'w-2.5 h-2.5' : 'w-2 h-2';
  return <span className={`mt-1.5 inline-block rounded-full ${cls} ${size}`} />;
}

function Empty({ t }) {
  return <div className="text-xs text-muted-foreground">{t('common.no_data')}</div>;
}
