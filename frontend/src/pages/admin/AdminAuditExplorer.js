import { useState } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { Search, Loader2, ScrollText, ChevronRight, FileText, Building2, Award, Users, Landmark, Network } from 'lucide-react';

const TYPE_META = {
  certificate: { icon: Award, color: 'text-emerald-700 bg-emerald-100' },
  asset: { icon: Building2, color: 'text-sky-700 bg-sky-100' },
  spv: { icon: Building2, color: 'text-violet-700 bg-violet-100' },
  fund: { icon: Landmark, color: 'text-amber-700 bg-amber-100' },
  operator: { icon: Users, color: 'text-indigo-700 bg-indigo-100' },
  investor_profile: { icon: Users, color: 'text-slate-700 bg-slate-100' },
  investment: { icon: FileText, color: 'text-emerald-600 bg-emerald-50' },
  user: { icon: Users, color: 'text-rose-700 bg-rose-100' },
};

export default function AdminAuditExplorer() {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');

  const search = async (e) => {
    e?.preventDefault?.();
    if (!q || q.length < 2) { setErr('Мінімум 2 символи'); return; }
    setBusy(true); setErr(''); setData(null);
    try { const r = await lumen.get('/admin/audit/explorer', { params: { q: q.trim() } }); setData(r.data); }
    catch (e2) { setErr(lumenError(e2)); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-5" data-testid="admin-audit-explorer">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Audit OS · G14</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Network className="w-5 h-5 text-[#2E5D4F]" /> Audit Explorer</h1>
        <p className="text-sm text-muted-foreground mt-1">Універсальний пошук по ID, email або номеру сертифіката — вся історія, пов'язані записи та timeline.</p>
      </div>

      <form onSubmit={search} className="flex items-center gap-2" data-testid="explorer-form">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="explorer-input"
            placeholder="Номер сертифіката, email, user_id, asset_id, fund_id…"
            className="w-full h-11 rounded-xl border border-border bg-background pl-9 pr-3 text-sm" />
        </div>
        <button type="submit" disabled={busy} data-testid="explorer-search"
          className="h-11 px-5 rounded-xl text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Пошук
        </button>
      </form>
      {err && <p className="text-sm text-red-600">{err}</p>}

      {data && (
        <>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <span>Знайдено: <b className="text-foreground">{data.counts?.matches}</b></span>
            <span>Audit записів: <b className="text-foreground">{data.counts?.audit}</b></span>
          </div>
          {data.matches?.length > 0 ? (
            <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="explorer-matches">
              {data.matches.map((m, i) => {
                const meta = TYPE_META[m.entity_type] || TYPE_META.investor_profile;
                const Icon = meta.icon;
                return (
                  <div key={i} className="px-4 py-3 flex items-center gap-3">
                    <span className={`w-9 h-9 rounded-lg flex items-center justify-center ${meta.color}`}><Icon className="w-4 h-4" /></span>
                    <div className="flex-1">
                      <div className="font-medium text-sm">{m.label}</div>
                      <div className="text-[11px] text-muted-foreground">{m.entity_type} · {m.id} · {m.summary}</div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                );
              })}
            </div>
          ) : <p className="text-sm text-muted-foreground">Сутностей не знайдено.</p>}

          {data.certificate_graph && (
            <div className="rounded-2xl border border-border bg-card p-5" data-testid="explorer-cert-graph">
              <h2 className="font-semibold mb-3 flex items-center gap-2"><Network className="w-4 h-4 text-[#2E5D4F]" />Граф власності сертифіката</h2>
              <ol className="space-y-2 text-sm">
                {data.certificate_graph.nodes.map((n) => (
                  <li key={n.id} className="flex items-center gap-3">
                    <span className="text-[10px] uppercase text-muted-foreground w-24">{n.type}</span>
                    <span className="flex-1">{n.label}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {data.certificate_timeline && data.certificate_timeline.length > 0 && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="explorer-cert-timeline">
              <div className="px-5 py-3 border-b border-border font-semibold flex items-center gap-1.5"><ScrollText className="w-4 h-4 text-[#2E5D4F]" />Timeline сертифіката</div>
              <ul className="divide-y divide-border">
                {data.certificate_timeline.map((e, i) => (
                  <li key={i} className="px-5 py-3 flex items-start justify-between gap-2">
                    <div><div className="text-sm font-medium">{e.event_label || e.event}</div><div className="text-[12px] text-muted-foreground">{e.summary}</div></div>
                    <time className="text-[11px] text-muted-foreground">{formatDateUk(e.at)}</time>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.audit?.length > 0 && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="explorer-audit">
              <div className="px-5 py-3 border-b border-border font-semibold flex items-center gap-1.5"><ScrollText className="w-4 h-4 text-[#2E5D4F]" />Audit записи</div>
              <ul className="divide-y divide-border">
                {data.audit.map((a) => (
                  <li key={a.id} className="px-5 py-2.5 flex items-start justify-between gap-2 text-sm">
                    <div><div><b>{a.category}</b> · {a.action}</div><div className="text-muted-foreground text-[12px]">{a.summary}</div></div>
                    <time className="text-[11px] text-muted-foreground">{formatDateUk(a.at)}</time>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
