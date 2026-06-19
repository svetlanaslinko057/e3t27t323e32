/**
 * FunnelDashboardView — F1 Investor Funnel Analytics
 * ─────────────────────────────────────────────────────────────────────────────
 * Single reusable view used by both:
 *   • /admin/funnel          (global scope)
 *   • /manager/funnel        (own-leads scope)
 *
 * 7 sections per locked F1 spec:
 *   F1.1  Stages — count + conversion bars
 *   F1.2  Conversion matrix
 *   F1.3  Bottlenecks
 *   F1.4  Duration analysis
 *   F1.5  Manager attribution      (admin only — hidden in manager scope)
 *   F1.6  Funding attribution      (admin only)
 *   F1.7  Executive summary
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useFundingT, useFundingLang } from '@/i18n/funding';
import {
  Activity, RefreshCw, Loader2, AlertTriangle, TrendingDown,
  Clock, Users, Target, BarChart3, Award,
} from 'lucide-react';

const RANGES = ['7d', '30d', '90d', 'ytd', 'all'];

function pct(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const p = Math.min(Math.max(v * 100, 0), 999);
  return `${p.toFixed(1)}%`;
}

function fmtDuration(seconds, lang) {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${Math.round(seconds)} ${lang === 'uk' ? 'с' : 's'}`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} ${lang === 'uk' ? 'хв' : 'min'}`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} ${lang === 'uk' ? 'г' : 'h'}`;
  return `${(seconds / 86400).toFixed(1)} ${lang === 'uk' ? 'дн' : 'd'}`;
}

function fmtMoney(v, currency) {
  if (!v) return '—';
  return new Intl.NumberFormat('uk-UA', {
    style: 'currency', currency: currency || 'EUR', maximumFractionDigits: 0,
  }).format(v);
}

export default function FunnelDashboardView({ scope = 'admin' }) {
  const t = useFundingT();
  const { lang } = useFundingLang();
  const [range, setRange] = useState('90d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const endpoint = scope === 'manager'
    ? '/manager/funnel/dashboard'
    : '/admin/funnel/dashboard';

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await lumen.get(endpoint, { params: { range } });
      setData(r.data);
    } catch (e) {
      setError(lumenError(e, t('funnel.empty')));
    } finally {
      setLoading(false);
    }
  }, [endpoint, range, t]);

  useEffect(() => { load(); }, [load]);

  const stages = data?.stages || [];
  const totals = data?.totals || {};
  const maxCount = useMemo(
    () => stages.reduce((m, s) => Math.max(m, s.count || 0), 0) || 1,
    [stages]
  );

  const showManagerSections = scope === 'admin';

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid={`funnel-view-${scope}`}>
      {/* ─── Header ───────────────────────────────────────────────────────── */}
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            {t('funnel.eyebrow')}
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-3">
            <Activity className="w-7 h-7 text-[#2E5D4F] dark:text-[#4FA98C]" />
            {t('funnel.title')}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-3xl">{t('funnel.subtitle')}</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex items-center rounded-full border border-border bg-card p-1 gap-0.5">
            {RANGES.map(r => (
              <button
                key={r}
                onClick={() => setRange(r)}
                data-testid={`funnel-range-${r}`}
                className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                  range === r
                    ? 'bg-[#2E5D4F] text-white shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t(`funnel.range.${r}`)}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            disabled={loading}
            data-testid="funnel-refresh"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted/40 text-sm disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            {t('funnel.refresh')}
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-5 px-4 py-3 rounded-lg border border-rose-200 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-900/60 text-sm text-rose-700 dark:text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {!data && loading && (
        <div className="py-20 flex items-center justify-center text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> {t('funnel.loading')}
        </div>
      )}

      {data && (
        <>
          {/* ─── F1.7 Executive KPIs (top) ─────────────────────────────────── */}
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8" data-testid="funnel-kpis">
            <Kpi
              icon={Users}
              label={t('funnel.kpi.investors')}
              value={totals.investors_in_window ?? 0}
              tone="neutral"
            />
            <Kpi
              icon={Award}
              label={t('funnel.kpi.active')}
              value={totals.active_investors ?? 0}
              tone="emerald"
            />
            <Kpi
              icon={Clock}
              label={t('funnel.kpi.bottleneck')}
              value={stageLabel(totals.main_bottleneck_stage, stages, lang) || t('funnel.kpi.none')}
              tone="amber"
            />
            <Kpi
              icon={TrendingDown}
              label={t('funnel.kpi.dropoff')}
              value={stageLabel(totals.main_dropoff_stage, stages, lang) || t('funnel.kpi.none')}
              tone="rose"
            />
          </section>

          {/* ─── F1.1 Stages with horizontal bars ──────────────────────────── */}
          <section className="mb-8" data-testid="funnel-stages">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> {t('funnel.section.stages')}
            </h2>
            <div className="rounded-2xl border border-border bg-card overflow-hidden divide-y divide-border">
              {stages.map((s, idx) => (
                <StageRow key={s.key} stage={s} idx={idx} maxCount={maxCount} lang={lang} t={t} />
              ))}
            </div>
          </section>

          {/* ─── F1.2 Conversion matrix & F1.4 Durations (table) ───────────── */}
          <section className="mb-8" data-testid="funnel-conversion-matrix">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
              <Target className="w-4 h-4" /> {t('funnel.section.conversion')} · {t('funnel.section.durations')}
            </h2>
            <div className="rounded-2xl border border-border bg-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 text-left">{t('funnel.col.stage')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.count')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.conv_prev')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.conv_start')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.median_prev')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.median_start')}</th>
                    <th className="px-4 py-2.5 text-right">{t('funnel.col.flags')}</th>
                  </tr>
                </thead>
                <tbody>
                  {stages.map((s) => (
                    <tr key={s.key} className="border-t border-border">
                      <td className="px-4 py-2.5 font-medium">{s.label[lang] || s.label.en}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{s.count}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{pct(s.conversion_from_previous)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{pct(s.conversion_from_start)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{fmtDuration(s.median_time_from_previous_seconds, lang)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{fmtDuration(s.median_time_from_start_seconds, lang)}</td>
                      <td className="px-4 py-2.5 text-right">
                        {s.bottleneck && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 text-[10px] uppercase tracking-wider mr-1">
                            <Clock className="w-3 h-3" /> {t('funnel.flag.bottleneck')}
                          </span>
                        )}
                        {s.main_dropoff && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-[10px] uppercase tracking-wider">
                            <TrendingDown className="w-3 h-3" /> {t('funnel.flag.dropoff')}
                          </span>
                        )}
                        {!s.bottleneck && !s.main_dropoff && <span className="text-muted-foreground">{t('funnel.flag.none')}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ─── F1.5 Manager attribution (admin only) ─────────────────────── */}
          {showManagerSections && (
            <section className="mb-8" data-testid="funnel-manager-attribution">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                <Users className="w-4 h-4" /> {t('funnel.section.manager')}
              </h2>
              <div className="rounded-2xl border border-border bg-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 text-left">{t('funnel.col.manager')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.leads')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.kyc')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.signed')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.funded')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.certs')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.active')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.lead_to_funded')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.manager_attribution || []).length === 0 ? (
                      <tr><td colSpan={8} className="px-4 py-6 text-center text-muted-foreground text-sm">{t('funnel.no_data')}</td></tr>
                    ) : (data.manager_attribution || []).map((r) => (
                      <tr key={r.manager_id || '_un'} className="border-t border-border">
                        <td className="px-4 py-2.5">
                          {r.manager_name || (
                            <span className="text-muted-foreground italic">{t('funnel.unassigned')}</span>
                          )}
                          {r.manager_email && <div className="text-[11px] text-muted-foreground font-mono">{r.manager_email}</div>}
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.leads_assigned}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.kyc_approved}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.contract_signed}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.funding_confirmed}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.certificate_issued}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.active_investor}</td>
                        <td className="px-4 py-2.5 text-right font-mono font-semibold">{pct(r.lead_to_funded_conv)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ─── F1.6 Funding attribution (admin only) ─────────────────────── */}
          {showManagerSections && (
            <section className="mb-8" data-testid="funnel-funding-attribution">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                <Award className="w-4 h-4" /> {t('funnel.section.funding')}
              </h2>
              <div className="rounded-2xl border border-border bg-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 text-left">{t('funnel.col.manager')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.volume')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.transfers')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.cert_value')}</th>
                      <th className="px-4 py-2.5 text-right">{t('funnel.col.certs')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.funding_attribution || []).length === 0 ? (
                      <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground text-sm">{t('funnel.no_data')}</td></tr>
                    ) : (data.funding_attribution || []).map((r, i) => (
                      <tr key={r.manager_id || `_un-${i}`} className="border-t border-border">
                        <td className="px-4 py-2.5">
                          {r.manager_name || (
                            <span className="text-muted-foreground italic">{t('funnel.unassigned')}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono">{fmtMoney(r.volume_eur, 'EUR')}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.transfers || 0}</td>
                        <td className="px-4 py-2.5 text-right font-mono">
                          {r.certificate_value_uah
                            ? new Intl.NumberFormat('uk-UA', { style: 'currency', currency: 'UAH', maximumFractionDigits: 0 }).format(r.certificate_value_uah)
                            : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono">{r.certificates || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ─── F1.7 Executive summary ─────────────────────────────────────── */}
          <section
            className="rounded-2xl border border-border bg-gradient-to-br from-[#F4F7F5] to-card dark:from-[#1A2520] dark:to-card p-6"
            data-testid="funnel-executive"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-2">
              {t('funnel.section.executive')}
            </h2>
            <p className="text-sm leading-relaxed">
              {t('funnel.executive.text')(
                totals.active_investors ?? 0,
                totals.investors_in_window ?? 0,
                stageLabel(totals.main_bottleneck_stage, stages, lang),
                stageLabel(totals.main_dropoff_stage, stages, lang),
              )}
            </p>
            {data.generated_at && (
              <p className="mt-3 text-[11px] text-muted-foreground font-mono">
                {data.generated_at}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function stageLabel(key, stages, lang) {
  if (!key) return null;
  const s = (stages || []).find(x => x.key === key);
  return s ? (s.label[lang] || s.label.en) : key;
}

function Kpi({ icon: Icon, label, value, tone }) {
  const tones = {
    neutral: 'border-border bg-card',
    emerald: 'border-emerald-200 bg-emerald-50 dark:bg-emerald-950/20 dark:border-emerald-900/60',
    amber: 'border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900/60',
    rose: 'border-rose-200 bg-rose-50 dark:bg-rose-950/20 dark:border-rose-900/60',
  };
  return (
    <div className={`rounded-2xl border p-4 ${tones[tone] || tones.neutral}`}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight">{value}</div>
    </div>
  );
}

function StageRow({ stage, idx, maxCount, lang, t }) {
  const widthPct = maxCount > 0 ? (stage.count / maxCount) * 100 : 0;
  return (
    <div className="px-4 py-3 flex items-center gap-3">
      <div className="w-6 text-xs text-muted-foreground font-mono">{idx + 1}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{stage.label[lang] || stage.label.en}</span>
            {stage.bottleneck && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 text-[10px] uppercase tracking-wider">
                <Clock className="w-3 h-3" /> {t('funnel.flag.bottleneck')}
              </span>
            )}
            {stage.main_dropoff && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 text-[10px] uppercase tracking-wider">
                <TrendingDown className="w-3 h-3" /> {t('funnel.flag.dropoff')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{pct(stage.conversion_from_previous)}</span>
            <span className="font-mono font-semibold text-foreground">{stage.count}</span>
          </div>
        </div>
        <div className="mt-1.5 h-2 rounded-full bg-muted/40 overflow-hidden">
          <div
            className="h-full bg-[#2E5D4F] dark:bg-[#4FA98C] transition-all"
            style={{ width: `${widthPct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
