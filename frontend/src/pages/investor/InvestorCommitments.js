import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError, UAH_PER_USD } from '@/lib/lumenApi';
import { HandCoins, Loader2, Plus, X, Clock, Ban, CheckCircle2, TrendingUp, Hourglass } from 'lucide-react';

const PRIMARY = '#2E5D4F';
const KIND_LABEL = { soft: 'М’яке (інтерес)', hard: 'Тверде', reservation: 'Резервація' };
const STATUS_LABEL = { pending: 'Очікує', confirmed: 'Підтверджено', allocated: 'Розподілено', converted: 'Інвестовано', cancelled: 'Скасовано' };
const SEG_LABEL = { retail: 'Роздрібний', qualified: 'Кваліфікований', strategic: 'Стратегічний', institutional: 'Інституційний' };

export default function InvestorCommitments() {
  const [commitments, setCommitments] = useState([]);
  const [waitlist, setWaitlist] = useState([]);
  const [assets, setAssets] = useState([]);
  const [segment, setSegment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // {asset, mode:'commit'|'waitlist'}

  const load = useCallback(async () => {
    try {
      const [c, w, a, s] = await Promise.all([
        lumen.get('/investor/commitments'),
        lumen.get('/investor/waitlist'),
        lumen.get('/assets'),
        lumen.get('/investor/segment'),
      ]);
      setCommitments(c.data.items || []);
      setWaitlist(w.data.items || []);
      const list = Array.isArray(a.data) ? a.data : (a.data.items || a.data.assets || []);
      setAssets(list);
      setSegment(s.data);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const cancel = async (id) => { try { await lumen.post(`/investor/commitments/${id}/cancel`); load(); } catch (_e) {} };
  const leaveWaitlist = async (assetId) => { try { await lumen.delete(`/investor/waitlist/${assetId}`); load(); } catch (_e) {} };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="investor-commitments">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Capital Formation · Phase E</div>
          <h1 className="text-2xl font-bold">Мої зобов'язання</h1>
        </div>
        {segment && (
          <div className="rounded-xl border border-border px-4 py-2">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Ваш сегмент</div>
            <div className="font-semibold" style={{ color: PRIMARY }}>{segment.segment_label || SEG_LABEL[segment.segment]}</div>
          </div>
        )}
      </div>

      {/* My commitments */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><HandCoins className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Зобов'язання</h2></div>
        {commitments.length === 0 ? (
          <p className="text-sm text-muted-foreground">У вас ще немає зобов'язань. Оберіть об'єкт нижче.</p>
        ) : (
          <div className="space-y-2" data-testid="my-commitments">
            {commitments.map((c) => (
              <div key={c.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{c.asset_title}</div>
                  <div className="text-[11px] text-muted-foreground">{KIND_LABEL[c.kind]} · {formatDateUk(c.created_at)}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold">{formatUAH(c.amount_uah)}</div>
                  {c.allocated_uah > 0 && <div className="text-[11px] text-emerald-600">розподілено {formatUAH(c.allocated_uah)}</div>}
                </div>
                <span className={`text-[11px] px-2 py-0.5 rounded-full ${c.status === 'cancelled' ? 'bg-muted text-muted-foreground' : c.status === 'allocated' ? 'bg-emerald-100 text-emerald-700' : 'bg-sky-100 text-sky-700'}`}>{STATUS_LABEL[c.status] || c.status}</span>
                {!['cancelled', 'converted'].includes(c.status) && (
                  <button onClick={() => cancel(c.id)} className="text-muted-foreground hover:text-rose-600" title="Скасувати"><Ban className="w-4 h-4" /></button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* My waitlist */}
      {waitlist.length > 0 && (
        <section className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-4"><Hourglass className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Лист очікування</h2></div>
          <div className="space-y-2" data-testid="my-waitlist">
            {waitlist.map((w) => (
              <div key={w.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
                <span className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center text-sm font-bold">{w.position || '—'}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{w.asset_title}</div>
                  <div className="text-[11px] text-muted-foreground">{w.status === 'notified' ? 'Звільнилось місце — оформіть зобов’язання' : 'У черзі'}</div>
                </div>
                <div className="font-semibold">{formatUAH(w.amount_uah)}</div>
                <button onClick={() => leaveWaitlist(w.asset_id)} className="text-muted-foreground hover:text-rose-600"><X className="w-4 h-4" /></button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Open assets to commit */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><TrendingUp className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Відкриті раунди</h2></div>
        <div className="grid md:grid-cols-2 gap-3" data-testid="open-assets">
          {assets.filter((a) => a.status === 'open').map((a) => (
            <AssetRaiseCard key={a.id} asset={a} onCommit={() => setModal({ asset: a, mode: 'commit' })} onWaitlist={() => setModal({ asset: a, mode: 'waitlist' })} />
          ))}
        </div>
      </section>

      {modal && <CommitModal modal={modal} onClose={() => setModal(null)} onDone={() => { setModal(null); load(); }} />}
    </div>
  );
}

function AssetRaiseCard({ asset, onCommit, onWaitlist }) {
  const [b, setB] = useState(null);
  useEffect(() => {
    let alive = true;
    lumen.get(`/assets/${asset.id}/raise-progress`).then((r) => { if (alive) setB(r.data); }).catch(() => {});
    return () => { alive = false; };
  }, [asset.id]);
  const pct = b ? Math.min(100, b.demand_pct) : 0;
  return (
    <div className="rounded-xl border border-border p-4">
      <div className="font-medium text-sm">{asset.title}</div>
      <div className="text-[11px] text-muted-foreground mb-2">{asset.category}</div>
      {b && (
        <>
          <div className="h-2.5 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${pct}%`, background: b.oversubscribed ? '#d97706' : PRIMARY }} />
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{formatUAH(b.total_demand_uah)} / {formatUAH(b.target_uah)}</span>
            <span>{b.demand_pct}%</span>
          </div>
        </>
      )}
      <div className="mt-3 flex gap-2">
        {b && b.oversubscribed ? (
          <button onClick={onWaitlist} data-testid={`waitlist-btn-${asset.id}`} className="flex-1 h-9 rounded-lg text-sm font-medium border border-amber-300 text-amber-700 inline-flex items-center justify-center gap-1.5"><Clock className="w-4 h-4" /> У чергу</button>
        ) : (
          <button onClick={onCommit} data-testid={`commit-btn-${asset.id}`} className="flex-1 h-9 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}><Plus className="w-4 h-4" /> Зобов'язатись</button>
        )}
      </div>
    </div>
  );
}

function CommitModal({ modal, onClose, onDone }) {
  const { asset, mode } = modal;
  const [amount, setAmount] = useState('');
  const [kind, setKind] = useState('hard');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) { setErr('Вкажіть суму'); return; }
    setBusy(true); setErr('');
    // User enters USD; backend ledger stores the base (UAH) amount.
    const amountBase = Math.round(amt * UAH_PER_USD);
    try {
      if (mode === 'waitlist') await lumen.post(`/investor/waitlist/${asset.id}`, { amount_uah: amountBase });
      else await lumen.post('/investor/commitments', { asset_id: asset.id, amount_uah: amountBase, kind });
      onDone();
    } catch (e) { setErr(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-card rounded-2xl border border-border w-full max-w-md p-6" onClick={(e) => e.stopPropagation()} data-testid="commit-modal">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">{mode === 'waitlist' ? 'Стати в чергу' : 'Нове зобов’язання'}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>
        <p className="text-sm text-muted-foreground mb-3">{asset.title}</p>
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Сума, USD</label>
        <div className="relative mt-1 mb-3">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
          <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="commit-amount" className="w-full h-10 rounded-lg border border-border bg-background pl-7 pr-3 text-sm" />
        </div>
        {mode === 'commit' && (
          <>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Тип зобов'язання</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)} data-testid="commit-kind" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1 mb-3">
              {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </>
        )}
        {err && <p className="text-xs text-rose-600 mb-2">{err}</p>}
        <button onClick={submit} disabled={busy} data-testid="commit-submit" className="w-full h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Підтвердити
        </button>
      </div>
    </div>
  );
}
