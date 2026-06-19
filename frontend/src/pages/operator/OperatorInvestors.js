import { useEffect, useState } from 'react';
import { lumen, formatUAH } from '@/lib/lumenApi';
import { KpiCard } from '@/lib/operatorUi';
import { Loader2, Users } from 'lucide-react';

export default function OperatorInvestors() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/operator/investors').then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  const items = data?.items || [];

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="operator-investors">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS</div>
        <h1 className="text-2xl font-bold">Інвестори</h1>
        <p className="text-sm text-muted-foreground mt-1">Агреговані дані по інвесторах ваших об'єктів.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 max-w-md">
        <KpiCard label="Інвесторів" value={data?.total_investors ?? 0} />
        <KpiCard label="Залучено капіталу" value={formatUAH(data?.total_capital_uah)} accent="#2E5D4F" />
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr><th className="text-left font-medium px-4 py-2.5">Інвестор</th><th className="text-right font-medium px-4 py-2.5">Сума</th><th className="text-right font-medium px-4 py-2.5">Частки</th><th className="text-right font-medium px-4 py-2.5">Об'єктів</th></tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.investor_id} className="border-t border-border">
                <td className="px-4 py-2.5 font-medium flex items-center gap-2"><span className="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs">{(i.name || 'I')[0]}</span>{i.name}</td>
                <td className="px-4 py-2.5 text-right">{formatUAH(i.amount_uah)}</td>
                <td className="px-4 py-2.5 text-right">{i.units}</td>
                <td className="px-4 py-2.5 text-right">{i.assets_count}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={4} className="px-4 py-8 text-center text-muted-foreground"><Users className="w-5 h-5 mx-auto mb-2 opacity-50" />Інвесторів ще немає.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
