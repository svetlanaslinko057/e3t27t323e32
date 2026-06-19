import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatUAH } from '@/lib/lumenApi';
import InstitutionalGate from './InstitutionalGate';
import { Loader2, Users2, Crown, CheckCircle2 } from 'lucide-react';

export default function InstitutionalSyndicates() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [gated, setGated] = useState(false);
  const [amounts, setAmounts] = useState({});
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState({});

  const load = useCallback(async () => {
    try { const r = await lumen.get('/institutional/syndicates'); setItems(r.data.items || []); }
    catch (_e) { /* public, ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const join = async (sid) => {
    const amount = Number(amounts[sid]);
    if (!amount) { setMsg((m) => ({ ...m, [sid]: 'Вкажіть суму' })); return; }
    setBusy(sid); setMsg((m) => ({ ...m, [sid]: '' }));
    try {
      await lumen.post(`/institutional/syndicates/${sid}/join`, { amount_uah: amount });
      setMsg((m) => ({ ...m, [sid]: 'Заявку на участь прийнято ✓' }));
      load();
    } catch (e) {
      if (e?.response?.status === 403 && /кваліфікованим|Strategic/i.test(e?.response?.data?.detail || '')) { setGated(true); return; }
      setMsg((m) => ({ ...m, [sid]: lumenError(e, 'Не вдалося приєднатися') }));
    } finally { setBusy(null); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  if (gated) return <InstitutionalGate message="Приєднання до синдикатів доступне кваліфікованим інвесторам (Strategic / Institutional)." />;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="institutional-syndicates">
      <div><div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS</div><h1 className="text-2xl font-bold">Синдикати</h1><p className="text-sm text-muted-foreground mt-1">Lead-інвестор резервує частку, решта приєднується.</p></div>
      <div className="space-y-4" data-testid="syndicates-list">
        {items.map((s) => (
          <div key={s.id} className="rounded-2xl border border-border bg-card p-5">
            <div className="flex items-start justify-between gap-3">
              <div><div className="font-semibold">{s.title}</div><div className="text-[11px] text-muted-foreground">{s.asset_title} · {s.state_label}</div></div>
              <div className="text-right"><div className="text-sm font-bold">{formatUAH(s.raised_uah)}</div><div className="text-[11px] text-muted-foreground">з {formatUAH(s.target_uah)}</div></div>
            </div>
            <div className="h-2 rounded-full bg-muted mt-3 overflow-hidden"><div className="h-full bg-[#2E5D4F]" style={{ width: `${Math.min(100, s.progress_pct)}%` }} /></div>
            <div className="flex items-center justify-between mt-2 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1"><Crown className="w-3 h-3 text-amber-500" /> Lead {s.lead_pct}% · {s.lead_investor_name || '—'}</span>
              <span className="inline-flex items-center gap-1"><Users2 className="w-3 h-3" /> {s.participants_count} учасн.</span>
            </div>
            {s.status !== 'funded' && s.status !== 'closed' && (
              <div className="flex gap-2 mt-4">
                <input type="number" placeholder={`мін. ${formatUAH(s.min_ticket_uah)}`} value={amounts[s.id] || ''} onChange={(e) => setAmounts((a) => ({ ...a, [s.id]: e.target.value }))} data-testid={`synd-amount-${s.id}`} className="flex-1 h-10 rounded-lg border border-border bg-background px-2 text-sm" />
                <button onClick={() => join(s.id)} disabled={busy === s.id} data-testid={`synd-join-${s.id}`} className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: '#2E5D4F' }}>{busy === s.id ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Приєднатися'}</button>
              </div>
            )}
            {msg[s.id] && <p className={`text-xs mt-2 inline-flex items-center gap-1 ${/✓/.test(msg[s.id]) ? 'text-emerald-600' : 'text-rose-600'}`}>{/✓/.test(msg[s.id]) && <CheckCircle2 className="w-3.5 h-3.5" />}{msg[s.id]}</p>}
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Відкритих синдикатів немає.</p>}
      </div>
    </div>
  );
}
