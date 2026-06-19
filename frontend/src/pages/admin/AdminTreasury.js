/**
 * AdminTreasury — H1.1.1 full treasury operations page.
 * Pulls from /api/admin/treasury/kpis + /api/admin/treasury/adapters.
 * Includes manual sync trigger.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import {
  Activity, Clock, AlertTriangle, CheckCircle2, RefreshCw, Loader2,
  Banknote, Landmark, Globe2, Hourglass, BookOpen, Layers, Send,
} from 'lucide-react';
import { useFundingLang, useFundingT } from '@/i18n/funding';
import { formatAmount } from '@/pages/funding/_shared';

function humaniseSec(sec, t) {
  if (sec == null) return '—';
  if (sec < 60) return `${Math.round(sec * 10) / 10}${t('treasury.unit.sec')}`;
  if (sec < 3600) return `${Math.round(sec / 6) / 10}${t('treasury.unit.min')}`;
  return `${Math.round(sec / 360) / 10}${t('treasury.unit.h')}`;
}

function percent(v) {
  if (v == null) return '—';
  return `${Math.round((v || 0) * 1000) / 10}%`;
}

export default function AdminTreasury() {
  const { lang } = useFundingLang();
  const t = useFundingT(lang);
  const [kpis, setKpis] = useState(null);
  const [adapters, setAdapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, b] = await Promise.all([
        lumen.get('/admin/treasury/kpis?window=30'),
        lumen.get('/admin/treasury/adapters'),
      ]);
      setKpis(a.data);
      setAdapters(b.data?.adapters || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const runSync = async () => {
    setSyncing(true); setSyncResult(null);
    try {
      const r = await lumen.post('/admin/treasury/sync');
      setSyncResult({ scanned: r.data?.scanned ?? 0, updated: r.data?.updated ?? 0 });
      await load();
    } catch (e) {
      setSyncResult({ error: lumenError(e, 'sync failed') });
    } finally { setSyncing(false); }
  };

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-treasury">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Lumen Admin</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">{t('treasury.title')}</h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{t('treasury.subtitle')}</p>
          {kpis?.as_of && (
            <p className="mt-2 text-[11px] text-muted-foreground">as_of: <span className="font-mono">{kpis.as_of}</span> · {t('treasury.window.30d')}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="treasury-refresh">
            <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
          </button>
        </div>
      </header>

      {loading && !kpis && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>
      )}
      {err && (
        <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200 border border-rose-200 dark:border-rose-900">{err}</div>
      )}

      {kpis && (
        <div className="space-y-6">
          {/* Status counts */}
          <Section title={t('treasury.section.counts')} icon={Layers}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Tile label={t('treasury.kpi.pending_review')} value={kpis.pending_review_count} testid="kpi-pending" />
              <Tile label={t('treasury.kpi.matched')} value={kpis.matched_count} testid="kpi-matched" tone="indigo" />
              <Tile label={t('treasury.kpi.confirmed')} value={kpis.confirmed_count} testid="kpi-confirmed" tone="emerald" icon={CheckCircle2} />
              <Tile label={t('treasury.kpi.rejected')} value={kpis.rejected_count} testid="kpi-rejected" tone="rose" />
            </div>
          </Section>

          {/* Volumes */}
          <Section title={t('treasury.section.volume')} icon={Banknote}>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <Tile label={t('treasury.kpi.today_volume')} value={formatAmount(kpis.today_volume_total, 'EUR')} testid="kpi-today-vol" wide />
              <Tile label={t('treasury.kpi.volume_30d')} value={formatAmount(kpis.volume_30d_total, 'EUR')} testid="kpi-30d-vol" wide />
              <Tile label={t('treasury.kpi.sepa_volume')} value={formatAmount(kpis.sepa_volume_30d, 'EUR')} testid="kpi-sepa-vol" icon={Landmark} />
              <Tile label={t('treasury.kpi.swift_volume')} value={formatAmount(kpis.swift_volume_30d, 'USD')} testid="kpi-swift-vol" icon={Globe2} />
            </div>
          </Section>

          {/* Ops health */}
          <Section title={t('treasury.section.ops')} icon={Activity}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <BigTile
                label={t('treasury.kpi.time_to_confirm')}
                sub={t('treasury.kpi.time_to_confirm.sub')}
                value={humaniseSec(kpis.time_to_confirm_avg_seconds, t)}
                icon={Hourglass}
                tone="emerald"
                testid="kpi-ttc"
              />
              <BigTile
                label={t('treasury.kpi.exception_rate')}
                sub={t('treasury.kpi.exception_rate.sub')}
                value={percent(kpis.exception_rate)}
                meta={`${kpis.exception_count} / ${kpis.window_total_count}`}
                icon={AlertTriangle}
                tone={kpis.exception_rate > 0.1 ? 'rose' : 'default'}
                testid="kpi-exc"
              />
            </div>
          </Section>

          {/* Adapters + Sync */}
          <Section title={t('treasury.section.adapters')} icon={Send}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <div className="p-4 rounded-xl border border-border bg-card" data-testid="adapters-card">
                <ul className="space-y-2">
                  {adapters.map((a) => (
                    <li key={a.provider} className="flex items-center justify-between gap-3 text-sm">
                      <div>
                        <div className="font-semibold">{a.provider}</div>
                        <div className="text-xs text-muted-foreground">{a.class}</div>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200">
                        {t('treasury.adapter.default')}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="p-4 rounded-xl border border-border bg-card" data-testid="sync-card">
                <div className="text-sm font-semibold">{t('treasury.sync.title')}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t('treasury.sync.lead')}</p>
                <button
                  onClick={runSync}
                  disabled={syncing}
                  className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-40"
                  data-testid="treasury-sync-btn"
                >
                  {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  {syncing ? t('treasury.sync.running') : t('treasury.sync.btn')}
                </button>
                {syncResult && !syncResult.error && (
                  <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">
                    {t('treasury.sync.ok', null, { scanned: syncResult.scanned, updated: syncResult.updated })}
                  </p>
                )}
                {syncResult?.error && (
                  <p className="mt-2 text-xs text-rose-700 dark:text-rose-300">{syncResult.error}</p>
                )}
              </div>
            </div>
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-3 text-xs uppercase tracking-wider text-muted-foreground">
        {Icon && <Icon className="w-3.5 h-3.5" />}
        {title}
      </div>
      {children}
    </section>
  );
}

const TONE = {
  default: { bg: 'bg-muted/30', fg: 'text-foreground' },
  emerald: { bg: 'bg-emerald-50 dark:bg-emerald-950/40', fg: 'text-emerald-800 dark:text-emerald-200' },
  indigo:  { bg: 'bg-indigo-50 dark:bg-indigo-950/40',   fg: 'text-indigo-800 dark:text-indigo-200' },
  rose:    { bg: 'bg-rose-50 dark:bg-rose-950/40',       fg: 'text-rose-800 dark:text-rose-200' },
  amber:   { bg: 'bg-amber-50 dark:bg-amber-950/40',     fg: 'text-amber-800 dark:text-amber-200' },
};

function Tile({ label, value, wide, tone = 'default', icon: Icon, testid }) {
  const tn = TONE[tone] || TONE.default;
  return (
    <div className={`p-4 rounded-xl ${tn.bg} ${wide ? 'md:col-span-1' : ''}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        {Icon && <Icon className="w-3 h-3" />}
        {label}
      </div>
      <div className={`mt-1.5 text-2xl font-bold tracking-tight ${tn.fg}`}>{value ?? '—'}</div>
    </div>
  );
}

function BigTile({ label, sub, value, meta, tone = 'default', icon: Icon, testid }) {
  const tn = TONE[tone] || TONE.default;
  return (
    <div className={`p-5 rounded-xl ${tn.bg}`} data-testid={testid}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
        {Icon && <Icon className="w-3.5 h-3.5" />}
        {label}
      </div>
      <div className={`mt-2 text-3xl font-bold tracking-tight ${tn.fg}`}>{value ?? '—'}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}{meta ? <span className="ml-2 font-mono">{meta}</span> : null}</div>
    </div>
  );
}
