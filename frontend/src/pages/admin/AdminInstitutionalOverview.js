import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import { Briefcase, Loader2, RefreshCw, Landmark, ShieldCheck, Award, Users, AlertCircle, BarChart3, ScrollText, TrendingUp, Wallet } from 'lucide-react';

const PRIMARY = '#2E5D4F';
const CAT_COLORS = ['#2E5D4F', '#6F9C8A', '#B7CEC1', '#D8E4DF', '#94A3B8', '#FCD34D'];

function Card({ title, icon: I, right, children, dt }) {
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid={dt}>
      <div className="px-5 py-3 border-b border-border flex items-center justify-between gap-2">
        <h2 className="font-semibold flex items-center gap-1.5"><I className="w-4 h-4 text-[#2E5D4F]" />{title}</h2>
        {right}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Kpi({ label, value, sub, accent }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent ? 'text-[#2E5D4F]' : ''}`}>{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

export default function AdminInstitutionalOverview() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try { const r = await lumen.get('/admin/institutional/overview'); setD(r.data); }
    catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading || !d) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-5" data-testid="admin-overview">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">LR2.6 · Chairman Dashboard</div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Briefcase className="w-5 h-5 text-[#2E5D4F]" /> Institutional Overview</h1>
          <p className="text-sm text-muted-foreground mt-1">Один екран для голови фонду / institutional COO. AUM, NAV, capital flow, compliance і рішення на розгляді.</p>
        </div>
        <button onClick={load} data-testid="overview-refresh" className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">
          <RefreshCw className="w-4 h-4" />Оновити
        </button>
      </div>
      {err && <p className="text-sm text-rose-600">{err}</p>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="overview-kpis">
        <Kpi label="AUM" value={formatUAH(d.kpi.aum_uah)} sub={`${d.kpi.assets} активів · ${d.kpi.spvs} SPV`} accent />
        <Kpi label="Активних фондів" value={d.kpi.funds_active} sub={`${d.kpi.certificates_active} сертифікатів`} />
        <Kpi label="Інвесторів" value={d.kpi.investors} />
        <Kpi label="Виплачено 90д" value={formatUAH(d.kpi.distributions_90d_uah)} sub={`pending ${formatUAH(d.kpi.payouts_pending_uah)}`} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Рішення на розгляді" icon={AlertCircle} dt="pending-decisions">
          <ul className="space-y-2 text-sm">
            <li className="flex justify-between"><span>Акредитація under review</span><b>{d.pending.accreditation_review}</b></li>
            <li className="flex justify-between"><span>Governance open / voting</span><b>{d.pending.governance_open}</b></li>
            <li className="flex justify-between"><span>Secondary orders open</span><b>{d.pending.secondary_open}</b></li>
            <li className="flex justify-between"><span>Capital calls unpaid</span><b>{d.pending.drawdowns_unpaid}</b></li>
          </ul>
        </Card>
        <Card title="Compliance постура" icon={ShieldCheck} dt="compliance-posture">
          <div className="text-sm space-y-2">
            <div className="flex justify-between"><span>Середній бал</span><b>{d.compliance.average_score ?? '—'}</b></div>
            <div className="flex justify-between"><span>Інвесторів охоплено</span><b>{d.compliance.investors_covered}</b></div>
            <div className="flex justify-between"><span>Прострочено · спливає 45д</span><b className={d.compliance.expired_count ? 'text-rose-700' : ''}>{d.compliance.expired_count} / {d.compliance.expirations_soon_count}</b></div>
            <div className="flex flex-wrap gap-1 mt-2">
              {Object.entries(d.compliance.by_status || {}).map(([k, v]) => (
                <span key={k} className="text-[10px] px-2 py-0.5 rounded-full bg-muted">{k}: {v}</span>
              ))}
            </div>
          </div>
        </Card>
        <Card title="Акредитація по рівнях" icon={Award} dt="accr-posture">
          <div className="text-sm space-y-1">
            {Object.entries(d.accreditation.by_level || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between"><span className="capitalize">{k}</span><b>{v}</b></div>
            ))}
            {Object.keys(d.accreditation.by_level || {}).length === 0 && <p className="text-xs text-muted-foreground">Немає інвесторів з рівнем.</p>}
          </div>
        </Card>
      </div>

      <Card title="Фонди (LP/GP pipeline)" icon={Landmark} dt="overview-funds"
        right={<span className="text-xs text-muted-foreground">{d.funds.length}</span>}>
        {d.funds.length === 0 ? <p className="text-sm text-muted-foreground text-center py-6">Немає фондів.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40"><tr><th className="text-left px-3 py-2">Фонд</th><th className="text-right px-3 py-2">Target</th><th className="text-right px-3 py-2">Committed</th><th className="text-right px-3 py-2">Called/Paid</th><th className="text-right px-3 py-2">NAV</th><th className="text-right px-3 py-2">LP</th><th className="text-right px-3 py-2">Fill</th></tr></thead>
            <tbody>{d.funds.map((f) => (
              <tr key={f.fund_id} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{f.name}<span className="text-[10px] text-muted-foreground ml-1">· {f.kind}</span></td>
                <td className="px-3 py-2 text-right font-mono text-xs">{formatUAH(f.target_uah)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{formatUAH(f.committed_uah)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{formatUAH(f.called_uah)} / {formatUAH(f.paid_uah)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{formatUAH(f.nav_uah)}</td>
                <td className="px-3 py-2 text-right">{f.lp_count}</td>
                <td className="px-3 py-2 text-right text-xs"><span className={`px-2 py-0.5 rounded-full ${f.fill_pct >= 100 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{f.fill_pct}%</span></td>
              </tr>))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Розподіл AUM за категоріями" icon={BarChart3} dt="overview-breakdown">
          <div className="space-y-2">
            {d.ownership_breakdown.map((b, i) => (
              <div key={b.category}>
                <div className="flex justify-between text-xs"><span className="capitalize">{b.category}</span><span className="font-mono">{b.share_pct}% · {formatUAH(b.value_uah)}</span></div>
                <div className="h-2 rounded-full bg-muted overflow-hidden mt-0.5"><div className="h-full" style={{ width: `${b.share_pct}%`, background: CAT_COLORS[i % CAT_COLORS.length] }} /></div>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Остання активність" icon={ScrollText} dt="overview-activity">
          {d.activity.length === 0 ? <p className="text-xs text-muted-foreground">Порожньо.</p> : (
            <ul className="space-y-2 text-xs max-h-72 overflow-auto">
              {d.activity.map((a, i) => (
                <li key={i} className="flex items-start justify-between gap-2 border-b border-border pb-1.5">
                  <div><div className="font-medium"><span className="text-muted-foreground">{a.category}</span> · {a.action}</div>
                    <div className="text-muted-foreground">{a.summary} · {a.actor_email || '—'}</div></div>
                  <time className="text-[10px] text-muted-foreground shrink-0">{formatDateUk(a.at)}</time>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
