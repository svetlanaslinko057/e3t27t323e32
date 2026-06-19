/**
 * FundingPulse — compact KPI widget for /admin/dashboard.
 * Pulls from /api/admin/treasury/pulse.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { lumen } from '@/lib/lumenApi';
import { Activity, Clock, AlertTriangle, CheckCircle2, RefreshCw, ArrowRight } from 'lucide-react';
import { useFundingT } from '@/i18n/funding';
import { formatAmount } from '@/pages/funding/_shared';

function humaniseSec(sec, t) {
  if (sec == null) return '—';
  if (sec < 60) return `${Math.round(sec * 10) / 10}${t('treasury.unit.sec')}`;
  if (sec < 3600) return `${Math.round(sec / 6) / 10}${t('treasury.unit.min')}`;
  return `${Math.round(sec / 360) / 10}${t('treasury.unit.h')}`;
}

export default function FundingPulse() {
  const t = useFundingT();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/treasury/pulse');
      setData(r.data || null);
      setErr('');
    } catch (e) {
      setErr('Failed to load');
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <section className="p-5 rounded-2xl border border-border bg-card" data-testid="funding-pulse-widget">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-muted-foreground" />
            <h3 className="font-semibold tracking-tight">{t('treasury.pulse.title')}</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{t('treasury.pulse.lead')}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="p-1.5 rounded-md hover:bg-muted text-muted-foreground" data-testid="pulse-refresh">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <Link to="/admin/treasury" className="inline-flex items-center gap-1 text-xs font-semibold text-foreground hover:underline" data-testid="pulse-open-full">
            {t('treasury.open_full')} <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </header>

      {loading && !data && <div className="mt-4 text-sm text-muted-foreground">{t('common.loading')}</div>}
      {err && <div className="mt-4 text-sm text-rose-700 dark:text-rose-300">{err}</div>}

      {data && (
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label={t('treasury.kpi.pending_review')} value={data.pending_review_count} testid="pulse-pending" />
          <Tile label={t('treasury.kpi.matched')} value={data.matched_count} testid="pulse-matched" />
          <Tile label={t('treasury.kpi.confirmed')} value={data.confirmed_count} testid="pulse-confirmed" tone="emerald" icon={CheckCircle2} />
          <Tile label={t('treasury.kpi.rejected')} value={data.rejected_count} testid="pulse-rejected" tone="rose" />
          <Tile label={t('treasury.kpi.today_volume')} value={formatAmount(data.today_volume_total, 'EUR')} wide testid="pulse-today-vol" />
          <Tile label={t('treasury.kpi.time_to_confirm')} value={humaniseSec(data.time_to_confirm_avg_seconds, t)} testid="pulse-ttc" icon={Clock} />
          <Tile label={t('treasury.kpi.exception_rate')} value={`${Math.round((data.exception_rate || 0) * 1000) / 10}%`} testid="pulse-exc" tone={data.exception_rate > 0.1 ? 'rose' : 'default'} icon={AlertTriangle} />
        </div>
      )}
    </section>
  );
}

const TONE = {
  default: { bg: 'bg-muted/30', fg: 'text-foreground' },
  emerald: { bg: 'bg-emerald-50 dark:bg-emerald-950/40', fg: 'text-emerald-800 dark:text-emerald-200' },
  rose:    { bg: 'bg-rose-50 dark:bg-rose-950/40',       fg: 'text-rose-800 dark:text-rose-200' },
};

function Tile({ label, value, wide, tone = 'default', icon: Icon, testid }) {
  const tn = TONE[tone] || TONE.default;
  return (
    <div className={`p-3 rounded-xl ${tn.bg} ${wide ? 'col-span-2' : ''}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        {Icon && <Icon className="w-3 h-3" />}
        {label}
      </div>
      <div className={`mt-1 text-xl font-semibold tracking-tight ${tn.fg}`}>{value ?? '—'}</div>
    </div>
  );
}
