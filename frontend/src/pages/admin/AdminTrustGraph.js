import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import TrustGraph from '@/components/lumen/TrustGraph';
import { VerifiedBadge } from '@/lib/operatorUi';
import { Loader2, Share2, Building2 } from 'lucide-react';

export default function AdminTrustGraph() {
  const [assets, setAssets] = useState([]);
  const [sel, setSel] = useState('');
  const [structure, setStructure] = useState(null);
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    lumen.get('/admin/assets').then((r) => {
      const list = r.data.items || []; setAssets(list);
      if (list[0]) setSel(list[0].id);
    }).catch(() => {});
  }, []);

  const load = useCallback(async (aid) => {
    if (!aid) return;
    setLoading(true);
    try {
      const [s, g] = await Promise.all([
        lumen.get(`/admin/institutional/assets/${aid}/structure`),
        lumen.get(`/admin/institutional/trust-graph?asset_id=${aid}`),
      ]);
      setStructure(s.data); setGraph(g.data);
    } catch (_e) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { if (sel) load(sel); }, [sel, load]);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-trust-graph">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G1 + G10</div><h1 className="text-2xl font-bold flex items-center gap-2"><Share2 className="w-5 h-5 text-[#2E5D4F]" /> Структура власності і Trust Graph</h1><p className="text-sm text-muted-foreground mt-1">Інвестор → Сертифікат → SPV → Оператор → Актив (→ Фонд).</p></div>
      <select value={sel} onChange={(e) => setSel(e.target.value)} data-testid="tg-asset-select" className="h-10 rounded-lg border border-border bg-background px-2 text-sm">{assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}</select>
      {loading && <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}
      {!loading && structure && (
        <>
          <div className="grid md:grid-cols-4 gap-3">
            <Box label="Актив" value={structure.asset?.title} icon={<Building2 className="w-4 h-4" />} />
            <Box label="SPV" value={structure.spv?.name} sub={structure.spv?.registration_number} />
            <Box label="Оператор" value={structure.operator?.name} badge={structure.operator?.verified} />
            <Box label="Фонд" value={structure.fund?.name || '—'} />
          </div>
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            <div className="px-5 py-3 border-b border-border font-semibold flex items-center justify-between"><span>Cap table</span><span className="text-sm text-muted-foreground">Equity {formatUAH(structure.equity_value_uah)} · {structure.holders_count} власників</span></div>
            <table className="w-full text-sm"><thead className="bg-muted/50 text-muted-foreground"><tr><th className="text-left font-medium px-4 py-2">Власник</th><th className="text-right font-medium px-4 py-2">Частка</th><th className="text-right font-medium px-4 py-2">Вартість</th></tr></thead>
              <tbody>{structure.cap_table.map((r, i) => (<tr key={i} className="border-t border-border"><td className="px-4 py-2">{r.investor_name}</td><td className="px-4 py-2 text-right">{formatPercent(r.ownership_percent)}</td><td className="px-4 py-2 text-right">{formatUAH(r.value_uah)}</td></tr>))}</tbody>
            </table>
          </div>
          <div><h2 className="font-semibold mb-2">Trust Graph ({graph?.counts?.nodes} вузлів, {graph?.counts?.edges} зв'язків)</h2>{graph && <div className="text-foreground"><TrustGraph data={graph} /></div>}</div>
        </>
      )}
    </div>
  );
}
function Box({ label, value, sub, icon, badge }) { return <div className="rounded-2xl border border-border bg-card p-4"><div className="text-[11px] uppercase text-muted-foreground flex items-center gap-1.5">{icon}{label}</div><div className="font-semibold mt-1 flex items-center gap-2">{value || '—'}{badge && <VerifiedBadge verified status="verified" />}</div>{sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}</div>; }
