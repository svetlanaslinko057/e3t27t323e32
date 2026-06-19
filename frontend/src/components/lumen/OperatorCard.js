import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { VerifiedBadge, gradeTone } from '@/lib/operatorUi';
import { Building2, ShieldCheck } from 'lucide-react';

/**
 * Investor-facing operator trust card for an asset page.
 * Fetches /assets/{assetId}/operator-card and renders the verified operator
 * with reputation + key KPI. Renders nothing if the asset has no operator.
 */
export default function OperatorCard({ assetId }) {
  const [op, setOp] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!assetId) return;
    lumen.get(`/assets/${assetId}/operator-card`)
      .then((r) => setOp(r.data?.operator || null))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [assetId]);

  if (!loaded || !op) return null;

  return (
    <div className="rounded-2xl border border-border bg-card p-5" data-testid="asset-operator-card">
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck className="w-4 h-4 text-[#2E5D4F]" />
        <h3 className="font-semibold text-sm">Оператор об'єкта</h3>
      </div>
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-muted flex items-center justify-center shrink-0"><Building2 className="w-5 h-5 text-muted-foreground" /></div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{op.name}</span>
            <VerifiedBadge verified={op.verified} status={op.status} statusLabel={op.status_label} />
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">{op.kind_label} · {op.region || '—'}</div>
          <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-muted-foreground">
            <span>{op.kpi?.assets_count ?? 0} об'єктів</span>
            {op.years_active ? <span>{op.years_active} р. на ринку</span> : null}
            <span>AUM {formatUAH(op.kpi?.aum_uah)}</span>
            <span>дохідність {formatPercent(op.kpi?.avg_yield_pct)}</span>
          </div>
        </div>
        {op.reputation && (
          <div className="text-right">
            <div className="text-2xl font-bold">{Math.round(op.reputation.score)}</div>
            <div className={`text-xs font-semibold ${gradeTone(op.reputation.grade)}`}>{op.reputation.grade}</div>
          </div>
        )}
      </div>
    </div>
  );
}
