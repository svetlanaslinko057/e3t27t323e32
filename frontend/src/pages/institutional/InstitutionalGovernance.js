import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { Loader2, Vote, ShieldAlert, CheckCircle2, Lock, Scale } from 'lucide-react';

/**
 * G7 — Governance (investor voting surface).
 * Votes are weighted by ownership units. The operator of an object CANNOT vote
 * on its own object (conflict of interest) — enforced server-side and surfaced here.
 */
export default function InstitutionalGovernance() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState({});

  const load = useCallback(async () => {
    try { const r = await lumen.get('/governance/proposals'); setItems(r.data.items || []); }
    catch (_e) { /* public list */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const vote = async (pid, choice) => {
    setBusy(`${pid}:${choice}`); setMsg((m) => ({ ...m, [pid]: '' }));
    try {
      await lumen.post(`/governance/proposals/${pid}/vote`, { choice });
      setMsg((m) => ({ ...m, [pid]: 'Голос зараховано ✓' }));
      load();
    } catch (e) {
      setMsg((m) => ({ ...m, [pid]: lumenError(e, 'Не вдалося проголосувати') }));
    } finally { setBusy(null); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="institutional-governance">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Institutional OS · G7</div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Vote className="w-5 h-5 text-[#2E5D4F]" /> Governance</h1>
        <p className="text-sm text-muted-foreground mt-1">Голоси зважені за вашою часткою власності. Голосувати можуть лише власники часток об'єкта.</p>
      </div>

      <div className="space-y-4" data-testid="gov-proposals-list">
        {items.map((p) => {
          const isOpen = p.status === 'open';
          const coi = !!p.coi_blocked;
          const weight = Number(p.your_weight || 0);
          const canVote = isOpen && !coi && weight > 0;
          return (
            <div key={p.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`gov-proposal-${p.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{p.title}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {p.scope_label} · {p.voters} голосів · {isOpen ? `до ${formatDateUk(p.closes_at)}` : 'закрито'}
                  </div>
                </div>
                <span className={`text-[11px] px-2 py-1 rounded-full font-medium ${isOpen ? 'bg-[#2E5D4F]/10 text-[#2E5D4F]' : 'bg-muted text-muted-foreground'}`}>
                  {isOpen ? 'Відкрито' : 'Закрито'}
                </span>
              </div>

              {p.description && <p className="text-sm text-muted-foreground mt-2">{p.description}</p>}

              {/* results */}
              <div className="mt-4 space-y-2">
                {(p.results || []).map((r) => {
                  const chosen = p.your_vote === r.option;
                  return (
                    <div key={r.option}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className={chosen ? 'font-semibold text-[#2E5D4F]' : ''}>
                          {r.option}{chosen ? ' · ваш голос' : ''}
                        </span>
                        <span>{r.pct}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div className="h-full" style={{ width: `${r.pct}%`, background: chosen ? '#2E5D4F' : '#9CB7AC' }} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* voting controls / state messaging */}
              <div className="mt-4 pt-3 border-t border-border">
                {coi ? (
                  <div className="flex items-center gap-2 text-sm text-amber-600" data-testid={`gov-coi-${p.id}`}>
                    <ShieldAlert className="w-4 h-4" />
                    Конфлікт інтересів: ви оператор цього об'єкта і не можете голосувати.
                  </div>
                ) : !isOpen ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground"><Lock className="w-4 h-4" /> Голосування завершено.</div>
                ) : weight <= 0 ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground"><Scale className="w-4 h-4" /> Голосувати можуть лише власники часток цього об'єкта.</div>
                ) : (
                  <div>
                    <div className="text-[11px] text-muted-foreground mb-2">Вага вашого голосу: <b className="text-foreground">{weight.toLocaleString('uk-UA')}</b> одиниць</div>
                    <div className="flex flex-wrap gap-2">
                      {(p.options || []).map((opt) => (
                        <button
                          key={opt}
                          onClick={() => vote(p.id, opt)}
                          disabled={!canVote || busy === `${p.id}:${opt}`}
                          data-testid={`gov-vote-${p.id}-${opt}`}
                          className={`h-9 px-4 rounded-lg text-sm font-medium border transition inline-flex items-center gap-1.5 ${
                            p.your_vote === opt ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border hover:bg-muted'
                          }`}
                        >
                          {busy === `${p.id}:${opt}` ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {msg[p.id] && (
                  <p className={`text-xs mt-2 inline-flex items-center gap-1 ${/✓/.test(msg[p.id]) ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {/✓/.test(msg[p.id]) && <CheckCircle2 className="w-3.5 h-3.5" />}{msg[p.id]}
                  </p>
                )}
              </div>
            </div>
          );
        })}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Активних пропозицій немає.</p>}
      </div>
    </div>
  );
}
