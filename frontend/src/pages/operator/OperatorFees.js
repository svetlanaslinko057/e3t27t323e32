import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { Loader2, HandCoins, Info } from 'lucide-react';

export default function OperatorFees() {
  const [fees, setFees] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/operator/fees').then((r) => setFees(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (!fees) return <div className="p-6 text-sm text-muted-foreground">Не вдалося завантажити.</div>;

  const rows = [
    ['Management fee', formatPercent(fees.management_fee_pct), 'Щорічна комісія за управління AUM'],
    ['Success fee', formatPercent(fees.success_fee_pct), 'Комісія за успішне залучення / закриття'],
    ['Performance fee', formatPercent(fees.performance_fee_pct), 'Комісія з прибутку понад hurdle'],
  ];

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6" data-testid="operator-fees">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><HandCoins className="w-5 h-5 text-[#2E5D4F]" /> Винагорода</h1>
        <p className="text-sm text-muted-foreground mt-1">Ваша тарифна сітка. Налаштовується адміністратором LUMEN.</p>
      </div>

      <div className="rounded-2xl border border-border bg-card divide-y divide-border">
        {rows.map(([l, v, d]) => (
          <div key={l} className="flex items-center justify-between p-4">
            <div><div className="font-medium text-sm">{l}</div><div className="text-[11px] text-muted-foreground">{d}</div></div>
            <div className="text-lg font-bold">{v}</div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-[#2E5D4F]/30 bg-[#2E5D4F]/[0.05] p-4 flex items-center justify-between">
        <div className="text-sm"><div className="font-medium">Орієнтовна management fee / рік</div><div className="text-[11px] text-muted-foreground">= AUM × management fee %</div></div>
        <div className="text-xl font-bold text-[#2E5D4F]">{formatUAH(fees.estimated_annual_management_fee_uah)}</div>
      </div>

      {fees.notes && <div className="flex items-start gap-2 text-xs text-muted-foreground"><Info className="w-3.5 h-3.5 mt-0.5" />{fees.notes}</div>}
    </div>
  );
}
