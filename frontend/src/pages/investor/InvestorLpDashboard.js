import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk } from '@/lib/lumenApi';
import { Landmark, Loader2, ArrowLeft, TrendingUp, Coins, Wallet, ChevronRight } from 'lucide-react';

const PRIMARY = '#2E5D4F';

function Kpi({ label, value, sub }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-bold">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function InvestorLpDashboard() {
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openFund, setOpenFund] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/investor/lp/funds'); setList(r.data); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const open = async (fundId) => {
    setOpenFund(fundId); setDetailLoading(true); setDetail(null);
    try { const r = await lumen.get(`/investor/lp/funds/${fundId}`); setDetail(r.data); }
    finally { setDetailLoading(false); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const items = list?.items || [];

  if (openFund && detail) {
    const f = detail.fund;
    return (
      <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="lp-detail">
        <button onClick={() => { setOpenFund(null); setDetail(null); }} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-4 h-4" /> Назад до фондів
        </button>
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">LP/GP · G13</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Landmark className="w-5 h-5 text-[#2E5D4F]" />{f?.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">Ваша роль: <b className="text-foreground">{detail.role}</b></p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="lp-kpis">
          <Kpi label="Зобов'язання" value={formatUAH(detail.amount_uah)} />
          <Kpi label="Сплачено" value={formatUAH(detail.paid_uah)} sub={`викликано ${formatUAH(detail.called_uah)}`} />
          <Kpi label="Невикликано" value={formatUAH(detail.uncalled_uah)} />
          <Kpi label="Виплачено вам" value={formatUAH(detail.distributions_uah)} sub={detail.multiple != null ? `multiple ${detail.multiple}x` : '—'} />
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h2 className="font-semibold mb-3 flex items-center gap-1.5"><TrendingUp className="w-4 h-4 text-[#2E5D4F]" />Стан фонду</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div><div className="text-[11px] uppercase text-muted-foreground">NAV фонду</div><div className="font-semibold">{formatUAH(f?.nav_uah)}</div></div>
            <div><div className="text-[11px] uppercase text-muted-foreground">Загальні зобов'язання</div><div className="font-semibold">{formatUAH(f?.committed_uah)}</div></div>
            <div><div className="text-[11px] uppercase text-muted-foreground">LP / GP</div><div className="font-semibold">{f?.lp_count} / {f?.gp_count}</div></div>
            <div><div className="text-[11px] uppercase text-muted-foreground">Виплачено LP</div><div className="font-semibold">{formatUAH(f?.distributions_uah)}</div></div>
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-5 py-3 border-b border-border font-semibold flex items-center gap-1.5"><Coins className="w-4 h-4 text-[#2E5D4F]" />Capital Calls (мої рядки)</div>
          {(detail.drawdowns || []).length === 0 ? <p className="px-5 py-6 text-sm text-muted-foreground">Ще не було викликів капіталу.</p> : (
            <table className="w-full text-sm" data-testid="lp-drawdowns">
              <thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">Дата</th><th className="text-right px-4 py-2">Сума</th><th className="text-right px-4 py-2">Статус</th></tr></thead>
              <tbody>{(detail.drawdowns || []).map((d) => (<tr key={d.id} className="border-t border-border"><td className="px-4 py-2">{formatDateUk(d.created_at)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(d.amount_uah)}</td><td className="px-4 py-2 text-right"><span className={`text-[11px] px-2 py-0.5 rounded-full ${d.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{d.status === 'paid' ? 'Сплачено' : 'Очікує'}</span></td></tr>))}</tbody>
            </table>
          )}
        </div>
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-5 py-3 border-b border-border font-semibold flex items-center gap-1.5"><Wallet className="w-4 h-4 text-[#2E5D4F]" />Виплати мені</div>
          {(detail.distributions || []).length === 0 ? <p className="px-5 py-6 text-sm text-muted-foreground">Виплат ще не було.</p> : (
            <table className="w-full text-sm" data-testid="lp-distributions">
              <thead className="bg-muted/40"><tr><th className="text-left px-4 py-2">Дата</th><th className="text-right px-4 py-2">RoC</th><th className="text-right px-4 py-2">Pref</th><th className="text-right px-4 py-2">Residual / Carry</th><th className="text-right px-4 py-2">Всього</th></tr></thead>
              <tbody>{(detail.distributions || []).map((l) => (<tr key={l.id} className="border-t border-border"><td className="px-4 py-2">{formatDateUk(l.distribution?.created_at)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.return_of_capital_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.preferred_return_uah)}</td><td className="px-4 py-2 text-right font-mono">{formatUAH(l.role === 'GP' ? l.carry_uah : l.residual_uah)}</td><td className="px-4 py-2 text-right font-mono font-semibold">{formatUAH(l.amount_uah)}</td></tr>))}</tbody>
            </table>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5" data-testid="investor-lp">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">LP/GP · G13</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Landmark className="w-5 h-5 text-[#2E5D4F]" /> Фонди (LP кабінет)</h1>
        <p className="text-sm text-muted-foreground mt-1">Ваші зобов'язання в фондах, capital calls і виплати.</p>
      </div>
      {items.length === 0 ? (
        <div className="rounded-2xl border border-border p-10 text-center text-sm text-muted-foreground">
          <Landmark className="w-8 h-8 mx-auto mb-3 opacity-40" />У вас немає зобов'язань у фондах. Зв'яжіться з менеджером.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3" data-testid="lp-fund-list">
          {items.map((c) => {
            const pct = c.amount_uah > 0 ? Math.round(c.paid_uah / c.amount_uah * 100) : 0;
            return (
              <button key={c.id} onClick={() => open(c.fund_id)} data-testid={`lp-fund-${c.fund_id}`}
                className="text-left rounded-2xl border border-border bg-card p-5 hover:border-[#2E5D4F]/60 transition">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{c.fund?.kind} · {c.role}</div>
                    <h3 className="font-semibold mt-1">{c.fund?.name}</h3>
                  </div>
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="mt-4 h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full" style={{ width: `${pct}%`, background: PRIMARY }} />
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Сплачено {formatUAH(c.paid_uah)}</span>
                  <span>{formatUAH(c.amount_uah)}</span>
                </div>
                <div className="mt-3 grid grid-cols-3 text-center text-xs">
                  <div><div className="font-semibold text-sm">{formatUAH(c.uncalled_uah)}</div><div className="text-[10px] text-muted-foreground">Невикликано</div></div>
                  <div><div className="font-semibold text-sm">{formatUAH(c.distributions_uah)}</div><div className="text-[10px] text-muted-foreground">Виплати</div></div>
                  <div><div className="font-semibold text-sm">{c.fund?.status}</div><div className="text-[10px] text-muted-foreground">Статус</div></div>
                </div>
              </button>
            );
          })}
        </div>
      )}
      {openFund && detailLoading && <div className="py-12 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>}
    </div>
  );
}
