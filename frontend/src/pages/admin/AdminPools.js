import React, { useEffect, useState, useCallback } from 'react';
import { useLang } from '@/contexts/LanguageContext';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import {
  Layers, Plus, Loader2, CheckCircle2, Banknote, TrendingUp, ShieldCheck,
  X, Play, Send, ArrowLeft, Coins, Building2, RefreshCw, AlertTriangle, Wallet,
} from 'lucide-react';

const PRIMARY = 'var(--token-primary)';
const fmtMoney = (n, ccy = 'USD') => (n === null || n === undefined || isNaN(n)) ? '—'
  : (ccy === 'USD' ? '$' + Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 2 })
    : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 2 }) + ' ' + ccy);

const ST = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  fundraising: 'bg-amber-100 text-amber-700 border-amber-200',
  funded: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  released_to_seller: 'bg-sky-100 text-sky-700 border-sky-200',
  operating: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  pending_payment: 'bg-amber-100 text-amber-700 border-amber-200',
  confirmed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  refunded: 'bg-rose-100 text-rose-700 border-rose-200',
  requested: 'bg-amber-100 text-amber-700 border-amber-200',
  approved: 'bg-sky-100 text-sky-700 border-sky-200',
  paid: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  reconciled: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};
const Badge = ({ s }) => <span className={`text-[11px] px-2 py-0.5 rounded-full border ${ST[s] || ST.draft}`}>{s}</span>;

/* ── Create pool modal ────────────────────────────────────────────────── */
function CreatePoolModal({ onClose, onCreated, bi }) {
  const [f, setF] = useState({ asset_id: '', title: '', currency: 'USD', target_amount: 100000, min_ticket: 1000, total_units: 100000 });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const up = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async () => {
    setBusy(true); setErr('');
    try {
      const r = await lumen.post('/admin/pools', {
        ...f, target_amount: Number(f.target_amount), min_ticket: Number(f.min_ticket), total_units: Number(f.total_units),
      });
      onCreated(r.data.pool);
    } catch (e) { setErr(lumenError(e)); } finally { setBusy(false); }
  };
  const Field = ({ k, label, type = 'text' }) => (
    <div>
      <label className="block text-xs text-muted-foreground mb-1">{label}</label>
      <input type={type} value={f[k]} onChange={(e) => up(k, e.target.value)} data-testid={`pool-field-${k}`}
        className="w-full h-9 rounded-lg border border-border bg-background px-3 text-sm" />
    </div>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="font-semibold">{bi('Новий пул', 'New pool')}</div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3">
          <div className="col-span-2"><Field k="title" label={bi('Назва пулу', 'Pool title')} /></div>
          <Field k="asset_id" label={bi('ID обʼєкта (asset_id)', 'Asset ID')} />
          <Field k="currency" label={bi('Валюта', 'Currency')} />
          <Field k="target_amount" label={bi('Ціль збору', 'Target amount')} type="number" />
          <Field k="min_ticket" label={bi('Мін. вхід', 'Min ticket')} type="number" />
          <Field k="total_units" label={bi('Всього часток', 'Total units')} type="number" />
        </div>
        {err && <div className="px-4 text-xs text-rose-600">{err}</div>}
        <div className="p-4 flex justify-end gap-2">
          <button onClick={onClose} className="h-9 px-4 rounded-lg border border-border text-sm">{bi('Скасувати', 'Cancel')}</button>
          <button onClick={submit} disabled={busy || !f.title || !f.asset_id} data-testid="pool-create-submit"
            className="h-9 px-4 rounded-lg text-white text-sm font-medium inline-flex items-center gap-2 disabled:opacity-50" style={{ background: PRIMARY }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}{bi('Створити', 'Create')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Pool detail ──────────────────────────────────────────────────────── */
function PoolDetail({ poolId, onBack, bi }) {
  const [data, setData] = useState(null);
  const [inv, setInv] = useState(null);
  const [audit, setAudit] = useState(null);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [rev, setRev] = useState({ gross_amount: 10000, expenses_amount: 1000, reserve_amount: 1000, tax_amount: 0, description: 'Дохід обʼєкта' });
  const [rel, setRel] = useState({ amount: '', seller_name: '', seller_iban: '', reason: 'Оплата за обʼєкт' });

  const load = useCallback(async () => {
    try {
      const [d, i, a] = await Promise.all([
        lumen.get(`/admin/pools/${poolId}`),
        lumen.get(`/admin/pools/${poolId}/invariants`),
        lumen.get(`/admin/pools/${poolId}/cash-audit`),
      ]);
      setData(d.data); setInv(i.data); setAudit(a.data);
    } catch (e) { setErr(lumenError(e)); }
  }, [poolId]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, key) => {
    setBusy(key); setErr('');
    try { await fn(); await load(); } catch (e) { setErr(lumenError(e)); } finally { setBusy(''); }
  };

  if (!data) return <div className="flex items-center gap-2 text-sm text-muted-foreground p-8"><Loader2 className="w-4 h-4 animate-spin" />Loading…</div>;
  const p = data.pool;

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-muted-foreground inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="w-4 h-4" />{bi('До списку', 'Back to pools')}</button>

      {/* Header */}
      <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><h2 className="text-xl font-bold">{p.title}</h2><Badge s={p.status} /></div>
            <div className="text-xs text-muted-foreground mt-0.5">{p.asset_id} · {p.id}</div>
          </div>
          <div className="flex gap-2">
            {p.status === 'draft' && <button onClick={() => act(() => lumen.post(`/admin/pools/${p.id}/open`), 'open')} disabled={busy === 'open'} data-testid="pool-open-btn" className="h-9 px-3 rounded-lg text-white text-sm font-medium inline-flex items-center gap-1.5" style={{ background: PRIMARY }}><Play className="w-4 h-4" />{bi('Відкрити збір', 'Open')}</button>}
            {p.status === 'released_to_seller' && <button onClick={() => act(() => lumen.post(`/admin/pools/${p.id}/mark-operating`), 'op')} disabled={busy === 'op'} className="h-9 px-3 rounded-lg border border-border text-sm font-medium inline-flex items-center gap-1.5"><TrendingUp className="w-4 h-4" />{bi('Перевести в роботу', 'Mark operating')}</button>}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            [bi('Ціль', 'Target'), fmtMoney(p.target_amount, p.currency)],
            [bi('Зібрано', 'Confirmed'), fmtMoney(p.confirmed_amount, p.currency)],
            [bi('Доступно в пулі', 'Available cash'), fmtMoney(p.available_cash, p.currency)],
            [bi('Випущено часток', 'Issued units'), (p.issued_units || 0).toLocaleString('uk-UA')],
            [bi('Передано продавцю', 'Released'), fmtMoney(p.released_amount, p.currency)],
          ].map(([l, v]) => (
            <div key={l} className="rounded-lg bg-muted/40 p-3"><div className="text-[10px] text-muted-foreground">{l}</div><div className="text-sm font-semibold">{v}</div></div>
          ))}
        </div>
      </div>

      {err && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-2">{err}</div>}

      {/* Invariants */}
      {inv && (
        <div className={`rounded-2xl border p-4 ${inv.all_passed ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50'}`} data-testid="pool-invariants">
          <div className="text-sm font-semibold flex items-center gap-1.5">
            {inv.all_passed ? <ShieldCheck className="w-4 h-4 text-emerald-600" /> : <AlertTriangle className="w-4 h-4 text-rose-600" />}
            {bi('Інваріанти пулу', 'Pool invariants')}: {inv.counts.passed}/{inv.counts.total}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {inv.checks.map((c) => (
              <span key={c.id} className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${c.passed ? 'border-emerald-200 bg-white text-emerald-700' : 'border-rose-200 bg-white text-rose-700'}`}>{c.passed ? '✓' : '✗'} {c.id}</span>
            ))}
          </div>
        </div>
      )}

      {/* Cash conservation audit (Statement A) */}
      {audit && !audit.error && (
        <div className="rounded-2xl border border-border bg-card p-4" data-testid="pool-cash-audit">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="font-semibold flex items-center gap-2"><Wallet className="w-4 h-4" />{bi('Аудит руху коштів', 'Cash movement audit')}</div>
            <span className={`text-[11px] px-2 py-0.5 rounded-full border ${audit.reconciles ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-rose-100 text-rose-700 border-rose-200'}`}>
              {audit.reconciles ? bi('Зведено ✓ Вхід = Вихід + Залишок', 'Reconciled ✓ In = Out + Balance') : bi('Розбіжність!', 'Mismatch!')}
            </span>
          </div>
          <div className="mt-3 grid sm:grid-cols-3 gap-3">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
              <div className="text-[10px] uppercase tracking-wide text-emerald-700 font-medium">{bi('Надходження (IN)', 'Inflows (IN)')}</div>
              <div className="text-lg font-bold text-emerald-700">{fmtMoney(audit.inflows.total, audit.currency)}</div>
              <div className="text-[11px] text-muted-foreground mt-1 space-y-0.5">
                <div className="flex justify-between"><span>{bi('Внески', 'Contributions')}</span><span>{fmtMoney(audit.inflows.contributions, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Дохід', 'Revenue')}</span><span>{fmtMoney(audit.inflows.revenue, audit.currency)}</span></div>
              </div>
            </div>
            <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3">
              <div className="text-[10px] uppercase tracking-wide text-rose-700 font-medium">{bi('Видатки (OUT)', 'Outflows (OUT)')}</div>
              <div className="text-lg font-bold text-rose-700">{fmtMoney(audit.outflows.total, audit.currency)}</div>
              <div className="text-[11px] text-muted-foreground mt-1 space-y-0.5">
                <div className="flex justify-between"><span>{bi('Продавцю', 'Releases')}</span><span>{fmtMoney(audit.outflows.seller_releases, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Витрати', 'Expenses')}</span><span>{fmtMoney(audit.outflows.expenses, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Податок', 'Tax')}</span><span>{fmtMoney(audit.outflows.tax, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Розподіл', 'Distributions')}</span><span>{fmtMoney(audit.outflows.distributions, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Повернення', 'Refunds')}</span><span>{fmtMoney(audit.outflows.refunds, audit.currency)}</span></div>
              </div>
            </div>
            <div className="rounded-xl border border-border bg-muted/40 p-3">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{bi('Залишок у пулі', 'Cash balance')}</div>
              <div className="text-lg font-bold">{fmtMoney(audit.cash_balance, audit.currency)}</div>
              <div className="text-[11px] text-muted-foreground mt-1 space-y-0.5">
                <div className="flex justify-between"><span>{bi('Зарезервовано', 'Reserve')}</span><span>{fmtMoney(audit.reserves_earmarked, audit.currency)}</span></div>
                <div className="flex justify-between"><span>{bi('Вільні кошти', 'Free cash')}</span><span>{fmtMoney(audit.free_cash, audit.currency)}</span></div>
              </div>
            </div>
          </div>
          {(audit.movements || []).length > 0 && (
            <details className="mt-3">
              <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">{bi('Журнал руху коштів', 'Movement journal')} ({audit.movements.length})</summary>
              <table className="w-full text-xs mt-2">
                <thead className="text-muted-foreground"><tr><th className="text-left p-1.5">{bi('Тип', 'Type')}</th><th className="text-left p-1.5">{bi('Опис', 'Description')}</th><th className="text-right p-1.5">{bi('Сума', 'Amount')}</th></tr></thead>
                <tbody>
                  {audit.movements.map((m) => (
                    <tr key={m.id} className="border-t border-border/60" data-testid={`mv-${m.id}`}>
                      <td className="p-1.5"><span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${m.direction === 'in' ? 'bg-emerald-100 text-emerald-700' : m.direction === 'out' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'}`}>{m.type}</span></td>
                      <td className="p-1.5 text-muted-foreground">{m.description}</td>
                      <td className={`p-1.5 text-right font-medium ${m.direction === 'in' ? 'text-emerald-700' : m.direction === 'out' ? 'text-rose-700' : ''}`}>{m.direction === 'out' ? '−' : m.direction === 'in' ? '+' : ''}{fmtMoney(m.amount, m.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
      )}

      {/* Contributions */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="p-3 font-semibold flex items-center gap-2 border-b border-border"><Coins className="w-4 h-4" />{bi('Внески (реконсиляція)', 'Contributions (reconciliation)')}</div>
        {data.contributions.length === 0 ? <div className="p-4 text-sm text-muted-foreground">{bi('Ще немає внесків', 'No contributions yet')}</div> : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-xs"><tr>
              <th className="text-left p-3">{bi('Інвестор', 'Investor')}</th><th className="text-left p-3">{bi('Призначення', 'Reference')}</th>
              <th className="text-right p-3">{bi('Сума', 'Amount')}</th><th className="text-right p-3">{bi('Частки', 'Units')}</th>
              <th className="text-right p-3">{bi('Статус', 'Status')}</th><th className="text-right p-3"></th>
            </tr></thead>
            <tbody>
              {data.contributions.map((c) => (
                <tr key={c.id} className="border-t border-border" data-testid={`contrib-${c.id}`}>
                  <td className="p-3">{c.investor_email || c.investor_id}</td>
                  <td className="p-3 font-mono text-xs">{c.reference}</td>
                  <td className="p-3 text-right">
                    {fmtMoney(c.amount_usd ?? c.amount, 'USD')}
                    {c.original_currency && c.original_currency !== 'USD' && (
                      <div className="text-[10px] text-muted-foreground">
                        {Number(c.original_amount).toLocaleString('uk-UA')} {c.original_currency}
                        {c.fx_rate_to_usd ? ` @ ${Number(c.fx_rate_to_usd).toFixed(4)}` : ''}
                      </div>
                    )}
                  </td>
                  <td className="p-3 text-right">{(c.units || 0).toLocaleString('uk-UA')}</td>
                  <td className="p-3 text-right"><Badge s={c.status} /></td>
                  <td className="p-3 text-right">
                    {c.status === 'pending_payment' && (
                      <button onClick={() => act(() => lumen.post(`/admin/pool-contributions/${c.id}/confirm`, { provider_ref: `manual-${c.id}`, bank_reference: c.reference, received_amount: c.original_amount ?? c.amount, received_currency: c.original_currency || c.currency }), `cf-${c.id}`)}
                        disabled={busy === `cf-${c.id}`} data-testid={`confirm-${c.id}`}
                        className="h-7 px-2.5 rounded-md text-xs font-medium bg-emerald-600 text-white inline-flex items-center gap-1">
                        {busy === `cf-${c.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}{bi('Підтвердити', 'Confirm')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Release to seller */}
      {['funded', 'released_to_seller', 'operating'].includes(p.status) && (
        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="font-semibold flex items-center gap-2 mb-3"><Send className="w-4 h-4" />{bi('Передати кошти продавцю / власнику', 'Release to seller / owner')}</div>
          <div className="grid sm:grid-cols-4 gap-2">
            <input placeholder={bi('Сума', 'Amount')} type="number" value={rel.amount} onChange={(e) => setRel({ ...rel, amount: e.target.value })} data-testid="release-amount" className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <input placeholder={bi('Продавець', 'Seller name')} value={rel.seller_name} onChange={(e) => setRel({ ...rel, seller_name: e.target.value })} data-testid="release-seller" className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <input placeholder="IBAN" value={rel.seller_iban} onChange={(e) => setRel({ ...rel, seller_iban: e.target.value })} className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <button onClick={() => act(() => lumen.post(`/admin/pools/${p.id}/release-to-seller`, { amount: Number(rel.amount), seller_name: rel.seller_name, seller_iban: rel.seller_iban, reason: rel.reason }), 'rel')}
              disabled={busy === 'rel' || !rel.amount || !rel.seller_name} data-testid="release-submit"
              className="h-9 rounded-lg text-white text-sm font-medium inline-flex items-center justify-center gap-1.5 disabled:opacity-50" style={{ background: PRIMARY }}>
              {busy === 'rel' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}{bi('Виплатити', 'Release')}
            </button>
          </div>
        </div>
      )}

      {/* Revenue */}
      {p.issued_units > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="font-semibold flex items-center gap-2 mb-3"><TrendingUp className="w-4 h-4" />{bi('Дохід обʼєкта → розподіл по частках', 'Revenue → pro-rata distribution')}</div>
          <div className="grid sm:grid-cols-5 gap-2 mb-2">
            <input placeholder={bi('Дохід', 'Gross')} type="number" value={rev.gross_amount} onChange={(e) => setRev({ ...rev, gross_amount: e.target.value })} data-testid="rev-gross" className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <input placeholder={bi('Витрати', 'Expenses')} type="number" value={rev.expenses_amount} onChange={(e) => setRev({ ...rev, expenses_amount: e.target.value })} className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <input placeholder={bi('Резерв', 'Reserve')} type="number" value={rev.reserve_amount} onChange={(e) => setRev({ ...rev, reserve_amount: e.target.value })} className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <input placeholder={bi('Податок', 'Tax')} type="number" value={rev.tax_amount} onChange={(e) => setRev({ ...rev, tax_amount: e.target.value })} data-testid="rev-tax" className="h-9 rounded-lg border border-border bg-background px-3 text-sm" />
            <button onClick={() => act(async () => { await lumen.post('/admin/revenue-events', { pool_id: p.id, gross_amount: Number(rev.gross_amount), expenses_amount: Number(rev.expenses_amount), reserve_amount: Number(rev.reserve_amount), tax_amount: Number(rev.tax_amount), description: rev.description }); }, 'rev')}
              disabled={busy === 'rev'} data-testid="rev-create"
              className="h-9 rounded-lg border border-border text-sm font-medium inline-flex items-center justify-center gap-1.5">
              {busy === 'rev' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}{bi('Додати дохід', 'Add revenue')}
            </button>
          </div>
          {(data.revenue_events || []).length > 0 && (
            <table className="w-full text-sm mt-2">
              <thead className="bg-muted/40 text-muted-foreground text-xs"><tr>
                <th className="text-left p-2">{bi('Опис', 'Description')}</th><th className="text-right p-2">{bi('Чистий', 'Net')}</th>
                <th className="text-right p-2">{bi('Статус', 'Status')}</th><th className="text-right p-2"></th>
              </tr></thead>
              <tbody>
                {data.revenue_events.map((ev) => (
                  <tr key={ev.id} className="border-t border-border" data-testid={`rev-${ev.id}`}>
                    <td className="p-2">{ev.description}</td>
                    <td className="p-2 text-right">{fmtMoney(ev.net_distributable, ev.currency)}</td>
                    <td className="p-2 text-right"><Badge s={ev.status} /></td>
                    <td className="p-2 text-right">
                      {ev.status === 'draft' && (
                        <button onClick={() => act(() => lumen.post(`/admin/revenue-events/${ev.id}/distribute`), `ds-${ev.id}`)} disabled={busy === `ds-${ev.id}`} data-testid={`distribute-${ev.id}`}
                          className="h-7 px-2.5 rounded-md text-xs font-medium bg-emerald-600 text-white inline-flex items-center gap-1">
                          {busy === `ds-${ev.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}{bi('Розподілити', 'Distribute')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Withdrawals queue ────────────────────────────────────────────────── */
function WithdrawalsQueue({ bi }) {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState('');
  const load = useCallback(async () => {
    try { const r = await lumen.get('/admin/pool-withdrawals'); setItems(r.data.items); } catch (_e) { setItems([]); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (fn, key) => { setBusy(key); try { await fn(); await load(); } finally { setBusy(''); } };
  if (items === null) return <div className="flex items-center gap-2 text-sm text-muted-foreground p-8"><Loader2 className="w-4 h-4 animate-spin" />Loading…</div>;
  if (items.length === 0) return <div className="text-sm text-muted-foreground border border-dashed border-border rounded-2xl p-10 text-center">{bi('Немає запитів на виведення', 'No withdrawal requests')}</div>;
  return (
    <div className="rounded-2xl border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground text-xs"><tr>
          <th className="text-left p-3">{bi('Інвестор', 'Investor')}</th><th className="text-left p-3">{bi('Дата', 'Date')}</th>
          <th className="text-right p-3">{bi('Сума', 'Amount')}</th><th className="text-right p-3">{bi('Статус', 'Status')}</th><th className="text-right p-3"></th>
        </tr></thead>
        <tbody>
          {items.map((w) => (
            <tr key={w.id} className="border-t border-border" data-testid={`adm-wd-${w.id}`}>
              <td className="p-3">{w.investor_email || w.investor_id}</td>
              <td className="p-3">{formatDateUk(w.created_at)}</td>
              <td className="p-3 text-right">{fmtMoney(w.amount, w.currency)}</td>
              <td className="p-3 text-right"><Badge s={w.status} /></td>
              <td className="p-3 text-right">
                {w.status === 'requested' && <button onClick={() => act(() => lumen.post(`/admin/pool-withdrawals/${w.id}/approve`), w.id)} disabled={busy === w.id} data-testid={`wd-approve-${w.id}`} className="h-7 px-2.5 rounded-md text-xs font-medium bg-sky-600 text-white">{bi('Підтвердити', 'Approve')}</button>}
                {w.status === 'approved' && <button onClick={() => act(() => lumen.post(`/admin/pool-withdrawals/${w.id}/pay`, { bank_reference: `PAYOUT-${w.id.slice(-6)}` }), w.id)} disabled={busy === w.id} data-testid={`wd-pay-${w.id}`} className="h-7 px-2.5 rounded-md text-xs font-medium bg-emerald-600 text-white">{bi('Виплатити', 'Pay')}</button>}
                {w.status === 'paid' && <button onClick={() => act(() => lumen.post(`/admin/pool-withdrawals/${w.id}/reconcile`), w.id)} disabled={busy === w.id} data-testid={`wd-recon-${w.id}`} className="h-7 px-2.5 rounded-md text-xs font-medium border border-border">{bi('Звірити', 'Reconcile')}</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Main ─────────────────────────────────────────────────────────────── */
export default function AdminPools() {
  const { bi } = useLang();
  const [tab, setTab] = useState('pools');
  const [pools, setPools] = useState(null);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try { const r = await lumen.get('/admin/pools'); setPools(r.data.items); } catch (e) { setErr(lumenError(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto" data-testid="admin-pools-page">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Layers className="w-6 h-6" style={{ color: PRIMARY }} />{bi('Capital Pool OS', 'Capital Pool OS')}</h1>
          <p className="text-sm text-muted-foreground">{bi('Пули обʼєктів: збір → частки → виплата продавцю → дохід → розподіл → виведення.', 'Asset pools: raise → units → release → revenue → distribute → withdrawal.')}</p>
        </div>
        {!selected && (
          <div className="flex items-center gap-2">
            <button onClick={load} className="h-9 px-3 rounded-lg border border-border text-sm inline-flex items-center gap-1.5"><RefreshCw className="w-4 h-4" />{bi('Оновити', 'Refresh')}</button>
            <button onClick={() => setCreating(true)} data-testid="pool-new-btn" className="h-9 px-3 rounded-lg text-white text-sm font-medium inline-flex items-center gap-1.5" style={{ background: PRIMARY }}><Plus className="w-4 h-4" />{bi('Новий пул', 'New pool')}</button>
          </div>
        )}
      </div>

      {!selected && (
        <div className="flex gap-1.5 border-b border-border pb-2">
          {[['pools', bi('Пули', 'Pools'), Building2], ['withdrawals', bi('Виведення', 'Withdrawals'), Wallet]].map(([k, l, Icon]) => (
            <button key={k} onClick={() => setTab(k)} data-testid={`adm-pool-tab-${k}`} className={`h-9 px-3 rounded-lg text-sm font-medium inline-flex items-center gap-1.5 ${tab === k ? 'text-white' : 'text-muted-foreground hover:bg-muted'}`} style={tab === k ? { background: PRIMARY } : {}}>
              <Icon className="w-4 h-4" />{l}
            </button>
          ))}
        </div>
      )}

      {err && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-2">{err}</div>}

      {selected ? (
        <PoolDetail poolId={selected} onBack={() => { setSelected(null); load(); }} bi={bi} />
      ) : tab === 'withdrawals' ? (
        <WithdrawalsQueue bi={bi} />
      ) : pools === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground p-8"><Loader2 className="w-4 h-4 animate-spin" />Loading…</div>
      ) : pools.length === 0 ? (
        <div className="text-sm text-muted-foreground border border-dashed border-border rounded-2xl p-10 text-center">{bi('Ще немає пулів. Створіть перший.', 'No pools yet. Create the first one.')}</div>
      ) : (
        <div className="rounded-2xl border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground text-xs"><tr>
              <th className="text-left p-3">{bi('Пул', 'Pool')}</th><th className="text-right p-3">{bi('Зібрано', 'Raised')}</th>
              <th className="text-right p-3">{bi('Частки', 'Units')}</th><th className="text-right p-3">{bi('Статус', 'Status')}</th><th className="text-right p-3"></th>
            </tr></thead>
            <tbody>
              {pools.map((p) => (
                <tr key={p.id} className="border-t border-border hover:bg-muted/30 cursor-pointer" onClick={() => setSelected(p.id)} data-testid={`adm-pool-row-${p.id}`}>
                  <td className="p-3"><div className="font-medium">{p.title}</div><div className="text-[11px] text-muted-foreground">{p.asset_id}</div></td>
                  <td className="p-3 text-right">{fmtMoney(p.confirmed_amount, p.currency)} <span className="text-muted-foreground">/ {fmtMoney(p.target_amount, p.currency)}</span></td>
                  <td className="p-3 text-right">{(p.issued_units || 0).toLocaleString('uk-UA')}</td>
                  <td className="p-3 text-right"><Badge s={p.status} /></td>
                  <td className="p-3 text-right"><button className="text-xs text-sky-600 hover:underline">{bi('Відкрити', 'Open')}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && <CreatePoolModal bi={bi} onClose={() => setCreating(false)} onCreated={(pool) => { setCreating(false); load(); setSelected(pool.id); }} />}
    </div>
  );
}
