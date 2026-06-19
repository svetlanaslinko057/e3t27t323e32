import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { KpiCard, ReputationRing, StatusPill, SeverityIcon, VerifiedBadge } from '@/lib/operatorUi';
import { Loader2, Percent, Activity, Workflow } from 'lucide-react';

export default function OperatorDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/operator/dashboard').then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">Не вдалося завантажити панель.</div>;

  const { operator: op, kpi, reputation: rep, sla, governance: gov, dealflow: df, fees, alerts } = data;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="operator-dashboard">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS · Phase F</div>
          <h1 className="text-2xl font-bold flex items-center gap-3">{op.name}
            <VerifiedBadge verified={op.verified} status={op.status} statusLabel={op.status_label} />
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{op.kind_label} · {op.region || '—'} · {op.specialization || '—'}</p>
        </div>
        <div className="flex items-center gap-4 rounded-2xl border border-border bg-card p-4">
          <ReputationRing score={rep.score} grade={rep.grade} />
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Репутація</div>
            <div className="text-sm font-semibold mt-0.5">Рейтинг {rep.grade}</div>
            <div className="text-[11px] text-muted-foreground mt-1">На основі фактів</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="AUM під управлінням" value={formatUAH(kpi.aum_uah)} accent="#2E5D4F" />
        <KpiCard label="Об'єктів" value={kpi.assets_count} sub="під управлінням" />
        <KpiCard label="Інвесторів" value={kpi.investors_count} />
        <KpiCard label="Середня дохідність" value={formatPercent(kpi.avg_yield_pct)} />
        <KpiCard label="Заповненість" value={kpi.occupancy_pct == null ? '—' : formatPercent(kpi.occupancy_pct)} sub={kpi.vacancy_pct == null ? undefined : `вакантність ${formatPercent(kpi.vacancy_pct)}`} />
        <KpiCard label="Своєчасність виплат" value={kpi.payout_timeliness_pct == null ? '—' : formatPercent(kpi.payout_timeliness_pct)} />
        <KpiCard label="Reporting Score" value={`${kpi.reporting_score}/100`} />
        <KpiCard label="Liquidity Score" value={`${kpi.liquidity_score}/10`} sub={`${kpi.trades_90d} угод / 90д`} />
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-3"><Activity className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">SLA звітності</h2></div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-muted-foreground">Загальний статус</span>
            <StatusPill status={sla.overall} label={sla.overall_label} />
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            {['ok','warning','critical','escalation'].map((k) => (
              <div key={k} className="rounded-lg bg-muted/50 py-2">
                <div className="text-lg font-bold">{sla.counts[k]}</div>
                <StatusPill status={k} />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-3"><Workflow className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Deal Flow</h2></div>
          <div className="space-y-2 text-sm">
            {[['Приведено сделок', df.sourced], ['Due Diligence', df.in_dd], ['Комітет', df.committee], ['Фінансування', df.funding], ['Активні', df.live]].map(([l, v]) => (
              <div key={l} className="flex items-center justify-between"><span className="text-muted-foreground">{l}</span><span className="font-semibold">{v}</span></div>
            ))}
            <div className="flex items-center justify-between pt-2 border-t border-border"><span className="text-muted-foreground">Успішність фінансування</span><span className="font-semibold">{formatPercent(df.funding_success_pct)}</span></div>
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-3"><Percent className="w-4 h-4 text-[#2E5D4F]" /><h2 className="font-semibold">Винагорода</h2></div>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between"><span className="text-muted-foreground">Management fee</span><span className="font-semibold">{formatPercent(fees.management_fee_pct)}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted-foreground">Success fee</span><span className="font-semibold">{formatPercent(fees.success_fee_pct)}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted-foreground">Performance fee</span><span className="font-semibold">{formatPercent(fees.performance_fee_pct)}</span></div>
            <div className="flex items-center justify-between pt-2 border-t border-border"><span className="text-muted-foreground">Mgmt fee / рік (орієнтовно)</span><span className="font-semibold">{formatUAH(fees.estimated_annual_management_fee_uah)}</span></div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Сповіщення та алерти</h2>
          {gov.alert && <StatusPill status="warning" label={`Настрій спільноти ${gov.positive_pct}%`} />}
        </div>
        <div className="space-y-2" data-testid="operator-alerts">
          {(alerts || []).map((a) => (
            <div key={a.id} className="flex items-start gap-2 rounded-lg border border-border p-3">
              <SeverityIcon severity={a.severity} />
              <div className="flex-1"><div className="text-sm">{a.message}</div></div>
            </div>
          ))}
          {(!alerts || alerts.length === 0) && <p className="text-sm text-muted-foreground">Алертів немає — все в нормі.</p>}
        </div>
      </div>
    </div>
  );
}
