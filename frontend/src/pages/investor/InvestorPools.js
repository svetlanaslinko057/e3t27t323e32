import React, { useEffect, useState, useCallback } from 'react';
import { useLang } from '@/contexts/LanguageContext';
import { lumen, lumenError, formatDateUk, usdFromUah } from '@/lib/lumenApi';
import {
  Building2, Coins, Boxes, Award, Wallet, Loader2, CheckCircle2, Copy,
  TrendingUp, ArrowDownToLine, X, Banknote, Users, Target, Clock,
} from 'lucide-react';

const PRIMARY = 'var(--token-primary)';

const fmtMoney = (n, ccy = 'USD') => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const sym = ccy === 'USD' ? '$' : '';
  return sym + Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 2 }) + (sym ? '' : ' ' + ccy);
};
const poolUsd = (pool, usdField, legacyField) =>
  pool[usdField] !== undefined && pool[usdField] !== null ? pool[usdField] : pool[legacyField];

const STATUS_LABEL = {
  draft: ['Чернетка', 'Draft'], fundraising: ['Збір коштів', 'Fundraising'],
  funded: ['Зібрано', 'Funded'], release_pending: ['Очікує виплати', 'Release pending'],
  released_to_seller: ['Передано продавцю', 'Released'], operating: ['Працює', 'Operating'],
  closed: ['Закрито', 'Closed'], cancelled: ['Скасовано', 'Cancelled'],
  requested: ['Запит', 'Requested'], approved: ['Підтверджено', 'Approved'],
  paid: ['Виплачено', 'Paid'], reconciled: ['Звірено', 'Reconciled'],
  pending_payment: ['Очікує оплату', 'Pending payment'], confirmed: ['Підтверджено', 'Confirmed'],
};

function Badge({ status, bi }) {
  const lbl = STATUS_LABEL[status] ? bi(STATUS_LABEL[status][0], STATUS_LABEL[status][1]) : status;
  const green = ['funded', 'operating', 'confirmed', 'paid', 'reconciled', 'released_to_seller'].includes(status);
  const amber = ['fundraising', 'requested', 'approved', 'pending_payment', 'release_pending'].includes(status);
  const cls = green ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
    : amber ? 'bg-amber-100 text-amber-700 border-amber-200'
      : 'bg-slate-100 text-slate-600 border-slate-200';
  return <span className={`text-[11px] px-2 py-0.5 rounded-full border ${cls}`}>{lbl}</span>;
}

function ProgressBar({ pct }) {
  return (
    <div className="h-2 rounded-full bg-muted overflow-hidden">
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%`, background: PRIMARY }} />
    </div>
  );
}

/* ── Contribute modal ─────────────────────────────────────────────────── */
const CONTRIB_CCY = ['USDT', 'USD', 'EUR'];
function ContributeModal({ pool, onClose, onDone, bi }) {
  const [amount, setAmount] = useState(pool.min_ticket || 1000);
  const [ccy, setCcy] = useState('USD');
  const [rates, setRates] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    lumen.get('/pool-fx/effective').then((r) => setRates(r.data.effective)).catch(() => {});
  }, []);

  const rate = rates?.[ccy]?.rate_per_usd;
  const usdEquiv = ccy === 'USD' || ccy === 'USDT' || ccy === 'USDC'
    ? Number(amount)
    : (rate ? Number(amount) / rate : null);

  const submit = async () => {
    setBusy(true); setErr('');
    try {
      const r = await lumen.post('/investor/pools/contribute', {
        pool_id: pool.id, amount: Number(amount), currency: ccy,
      });
      setResult(r.data);
      onDone && onDone();
    } catch (e) { setErr(lumenError(e)); }
    finally { setBusy(false); }
  };

  const copyRef = () => {
    if (result?.payment_instructions?.reference) {
      navigator.clipboard?.writeText(result.payment_instructions.reference);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" data-testid="pool-contribute-modal">
      <div className="bg-card border border-border rounded-2xl w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="font-semibold">{bi('Внести в пул', 'Contribute to pool')}</div>
          <button onClick={onClose} data-testid="pool-modal-close" className="p-1 rounded hover:bg-muted"><X className="w-4 h-4" /></button>
        </div>

        {!result ? (
          <div className="p-4 space-y-3">
            <div className="text-sm font-medium">{pool.title}</div>
            <div className="text-xs text-muted-foreground">
              {bi('Мінімальний вхід', 'Minimum ticket')}: <b>{fmtMoney(pool.min_ticket, 'USD')}</b> ·
              {' '}{bi('Ціна частки', 'Unit price')}: {fmtMoney(poolUsd(pool, 'unit_price_usd', 'unit_price'), 'USD')}
            </div>
            <label className="block text-xs text-muted-foreground">{bi('Сума та валюта внеску', 'Contribution amount & currency')}</label>
            <div className="flex items-center gap-2">
              <input type="number" min={0} value={amount}
                onChange={(e) => setAmount(e.target.value)} data-testid="pool-amount-input"
                className="flex-1 h-10 rounded-lg border border-border bg-background px-3 text-sm" />
              <select value={ccy} onChange={(e) => setCcy(e.target.value)} data-testid="pool-currency-select"
                className="h-10 rounded-lg border border-border bg-background px-2 text-sm font-medium">
                {CONTRIB_CCY.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="rounded-lg bg-muted/40 px-3 py-2 text-xs space-y-0.5" data-testid="pool-usd-preview">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{bi('Еквівалент у USD', 'USD equivalent')}</span>
                <b>{usdEquiv != null ? fmtMoney(Math.round(usdEquiv * 100) / 100, 'USD') : '—'}</b>
              </div>
              {ccy !== 'USD' && ccy !== 'USDT' && (
                <div className="flex justify-between text-muted-foreground">
                  <span>{bi('Курс', 'Rate')}</span>
                  <span>{rate ? `${rate.toFixed(4)} ${ccy}/USD · ${rates?.[ccy]?.source}` : '—'}</span>
                </div>
              )}
              <div className="flex justify-between text-muted-foreground">
                <span>≈ {bi('часток', 'units')}</span>
                <span>{usdEquiv != null ? Math.floor(usdEquiv / (poolUsd(pool, 'unit_price_usd', 'unit_price') || 1)).toLocaleString('uk-UA') : '—'}</span>
              </div>
            </div>
            {err && <div className="text-xs text-rose-600">{err}</div>}
            <button onClick={submit} disabled={busy} data-testid="pool-contribute-submit"
              className="w-full h-10 rounded-lg text-white font-medium inline-flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: PRIMARY }}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Coins className="w-4 h-4" />}
              {bi('Створити внесок', 'Create contribution')}
            </button>
          </div>
        ) : (
          <div className="p-4 space-y-3" data-testid="pool-payment-instructions">
            <div className="flex items-center gap-2 text-emerald-700 text-sm font-medium">
              <CheckCircle2 className="w-5 h-5" />{bi('Внесок створено', 'Contribution created')}
            </div>
            <p className="text-xs text-muted-foreground">
              {bi('Зробіть банківський переказ із цим призначенням платежу. Після підтвердження ви отримаєте частки.',
                'Make a bank transfer with this reference. You will receive units once confirmed.')}
            </p>
            <div className="rounded-xl border border-border bg-muted/40 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{bi('Призначення платежу', 'Payment reference')}</span>
                <button onClick={copyRef} className="text-xs inline-flex items-center gap-1 text-sky-600 hover:underline">
                  <Copy className="w-3 h-3" />{copied ? bi('Скопійовано', 'Copied') : bi('Копіювати', 'Copy')}
                </button>
              </div>
              <div className="font-mono text-base font-semibold tracking-wide">{result.payment_instructions.reference}</div>
              <div className="text-xs text-muted-foreground">
                {bi('Сума', 'Amount')}: <b>{Number(result.payment_instructions.amount).toLocaleString('uk-UA')} {result.payment_instructions.currency}</b>
                {' '}≈ <b>{fmtMoney(result.payment_instructions.amount_usd, 'USD')}</b>
              </div>
              {result.fx && result.fx.fx_source !== 'native' && (
                <div className="text-[11px] text-muted-foreground">
                  {bi('Зафіксований курс', 'Locked rate')}: {Number(result.fx.fx_rate_to_usd).toFixed(4)} {result.fx.original_currency}/USD · {result.fx.fx_source}
                </div>
              )}
            </div>
            <button onClick={onClose} data-testid="pool-instructions-done"
              className="w-full h-10 rounded-lg border border-border font-medium hover:bg-muted">
              {bi('Готово', 'Done')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Pool card ────────────────────────────────────────────────────────── */
function PoolCard({ pool, onContribute, bi }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 flex flex-col" data-testid={`pool-card-${pool.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'color-mix(in srgb, var(--token-primary) 14%, transparent)' }}>
            <Building2 className="w-5 h-5" style={{ color: PRIMARY }} />
          </div>
          <div className="min-w-0">
            <div className="font-semibold truncate">{pool.title}</div>
            <div className="text-[11px] text-muted-foreground truncate">{pool.asset_id}</div>
          </div>
        </div>
        <Badge status={pool.status} bi={bi} />
      </div>

      <div className="mt-4 space-y-1.5">
        <div className="flex items-end justify-between">
          <span className="text-lg font-bold">{fmtMoney(poolUsd(pool, 'confirmed_usd', 'confirmed_amount'), 'USD')}</span>
          <span className="text-xs text-muted-foreground">/ {fmtMoney(poolUsd(pool, 'hard_cap_usd', 'target_amount'), 'USD')}</span>
        </div>
        <ProgressBar pct={pool.progress_percent || 0} />
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{(pool.progress_percent || 0).toFixed(1)}% {bi('зібрано', 'raised')}</span>
          <span>{bi('Залишок', 'Remaining')}: {fmtMoney(pool.remaining_amount, 'USD')}</span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-muted/40 py-2">
          <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1"><Users className="w-3 h-3" />{bi('Інвестори', 'Investors')}</div>
          <div className="text-sm font-semibold">{pool.investor_count ?? 0}</div>
        </div>
        <div className="rounded-lg bg-muted/40 py-2">
          <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1"><Target className="w-3 h-3" />{bi('Мін. вхід', 'Min')}</div>
          <div className="text-sm font-semibold">{fmtMoney(pool.min_ticket, 'USD')}</div>
        </div>
        <div className="rounded-lg bg-muted/40 py-2">
          <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-1"><Boxes className="w-3 h-3" />{bi('Частки', 'Units')}</div>
          <div className="text-sm font-semibold">{(pool.total_units || 0).toLocaleString('uk-UA')}</div>
        </div>
      </div>

      <button
        disabled={pool.status !== 'fundraising'}
        onClick={() => onContribute(pool)}
        data-testid={`pool-contribute-${pool.id}`}
        className="mt-4 h-10 rounded-lg text-white font-medium inline-flex items-center justify-center gap-2 disabled:opacity-40"
        style={{ background: PRIMARY }}>
        <Coins className="w-4 h-4" />
        {pool.status === 'fundraising' ? bi('Внести в пул', 'Contribute') : bi('Збір закрито', 'Closed')}
      </button>
    </div>
  );
}

/* ── Main page ────────────────────────────────────────────────────────── */
export default function InvestorPools() {
  const { bi } = useLang();
  const [tab, setTab] = useState('browse');
  const [pools, setPools] = useState(null);
  const [positions, setPositions] = useState(null);
  const [balances, setBalances] = useState(null);
  const [withdrawals, setWithdrawals] = useState(null);
  const [certs, setCerts] = useState(null);
  const [contribPool, setContribPool] = useState(null);
  const [err, setErr] = useState('');
  const [wdAmount, setWdAmount] = useState('');
  const [wdCcy, setWdCcy] = useState('USD');
  const [wdBusy, setWdBusy] = useState(false);

  const loadAll = useCallback(async () => {
    const calls = [
      ['pools', '/investor/pools'],
      ['positions', '/investor/pools/my'],
      ['balances', '/investor/pool-balances'],
      ['withdrawals', '/investor/pool-withdrawals'],
      ['certs', '/investor/pool-certificates'],
    ];
    const setters = { pools: setPools, positions: setPositions, balances: setBalances, withdrawals: setWithdrawals, certs: setCerts };
    const results = await Promise.allSettled(calls.map(([, url]) => lumen.get(url)));
    let firstErr = '';
    results.forEach((res, i) => {
      const key = calls[i][0];
      if (res.status === 'fulfilled') setters[key](res.value.data.items || []);
      else { setters[key]([]); if (!firstErr) firstErr = lumenError(res.reason); }
    });
    setErr(firstErr);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const requestWithdrawal = async () => {
    setWdBusy(true); setErr('');
    try {
      await lumen.post('/investor/pool-withdrawals', { currency: wdCcy, amount: Number(wdAmount) });
      setWdAmount('');
      await loadAll();
    } catch (e) { setErr(lumenError(e)); }
    finally { setWdBusy(false); }
  };

  const tabs = [
    ['browse', bi('Пули обʼєктів', 'Pools'), Building2],
    ['positions', bi('Мої частки', 'My positions'), Boxes],
    ['balance', bi('Баланс і виплати', 'Balance & payouts'), Wallet],
    ['certificates', bi('Сертифікати', 'Certificates'), Award],
  ];

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto" data-testid="investor-pools-page">
      <div>
        <h1 className="text-2xl font-bold">{bi('Інвестиційні пули', 'Capital Pools')}</h1>
        <p className="text-sm text-muted-foreground">{bi('Увійдіть у пул конкретного обʼєкта та отримайте частки (units) пропорційно внеску.', 'Join an asset pool and receive units pro-rata to your contribution.')}</p>
      </div>

      <div className="flex gap-1.5 flex-wrap border-b border-border pb-2">
        {tabs.map(([key, label, Icon]) => (
          <button key={key} onClick={() => setTab(key)} data-testid={`pool-tab-${key}`}
            className={`h-9 px-3 rounded-lg text-sm font-medium inline-flex items-center gap-1.5 ${tab === key ? 'text-white' : 'text-muted-foreground hover:bg-muted'}`}
            style={tab === key ? { background: PRIMARY } : {}}>
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>

      {err && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-2">{err}</div>}

      {/* Browse */}
      {tab === 'browse' && (
        pools === null ? <Loading bi={bi} /> :
          pools.length === 0 ? <Empty bi={bi} text={bi('Поки немає активних пулів', 'No active pools yet')} /> :
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {pools.map((p) => <PoolCard key={p.id} pool={p} onContribute={setContribPool} bi={bi} />)}
            </div>
      )}

      {/* Positions */}
      {tab === 'positions' && (
        positions === null ? <Loading bi={bi} /> :
          positions.length === 0 ? <Empty bi={bi} text={bi('У вас ще немає часток', 'You have no units yet')} /> :
            <div className="rounded-2xl border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-xs">
                  <tr>
                    <th className="text-left p-3">{bi('Обʼєкт', 'Asset')}</th>
                    <th className="text-right p-3">{bi('Внесок', 'Contribution')}</th>
                    <th className="text-right p-3">{bi('Частки', 'Units')}</th>
                    <th className="text-right p-3">{bi('Частка', 'Ownership')}</th>
                    <th className="text-right p-3">{bi('Статус', 'Status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.pool_id} className="border-t border-border" data-testid={`pos-${p.pool_id}`}>
                      <td className="p-3 font-medium">{p.title}</td>
                      <td className="p-3 text-right">{fmtMoney(p.amount, p.currency)}</td>
                      <td className="p-3 text-right">{(p.units || 0).toLocaleString('uk-UA')}</td>
                      <td className="p-3 text-right font-semibold">{(p.ownership_percent || 0).toFixed(4)}%</td>
                      <td className="p-3 text-right"><Badge status={p.pool_status} bi={bi} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
      )}

      {/* Balance & withdrawals */}
      {tab === 'balance' && (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {(balances || []).length === 0 && <Empty bi={bi} text={bi('Дохід ще не нараховано', 'No income credited yet')} />}
            {(balances || []).map((b) => (
              <div key={b.currency} className="rounded-2xl border border-border bg-card p-5" data-testid={`balance-${b.currency}`}>
                <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{bi('Доступний баланс', 'Available balance')}</div>
                <div className="text-3xl font-bold mt-1" style={{ color: PRIMARY }}>{fmtMoney(b.available, b.currency)}</div>
                <div className="mt-2 text-xs text-muted-foreground space-y-0.5">
                  <div className="flex justify-between"><span>{bi('Нараховано', 'Credited')}</span><span>{fmtMoney(b.credited, b.currency)}</span></div>
                  <div className="flex justify-between"><span>{bi('Зарезервовано', 'Reserved')}</span><span>{fmtMoney(b.reserved, b.currency)}</span></div>
                  <div className="flex justify-between"><span>{bi('Виведено', 'Withdrawn')}</span><span>{fmtMoney(b.withdrawn, b.currency)}</span></div>
                </div>
              </div>
            ))}
          </div>

          {/* Request withdrawal */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="font-semibold flex items-center gap-2 mb-3"><ArrowDownToLine className="w-4 h-4" />{bi('Запит на виведення', 'Request withdrawal')}</div>
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">{bi('Сума', 'Amount')}</label>
                <input type="number" value={wdAmount} onChange={(e) => setWdAmount(e.target.value)} data-testid="wd-amount"
                  className="h-10 w-40 rounded-lg border border-border bg-background px-3 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">{bi('Валюта', 'Currency')}</label>
                <select value={wdCcy} onChange={(e) => setWdCcy(e.target.value)} className="h-10 rounded-lg border border-border bg-background px-3 text-sm">
                  {(balances && balances.length ? balances.map((b) => b.currency) : ['USD']).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <button onClick={requestWithdrawal} disabled={wdBusy || !wdAmount} data-testid="wd-submit"
                className="h-10 px-4 rounded-lg text-white font-medium inline-flex items-center gap-2 disabled:opacity-50" style={{ background: PRIMARY }}>
                {wdBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}{bi('Запросити', 'Request')}
              </button>
            </div>
          </div>

          {/* Withdrawal history */}
          {(withdrawals || []).length > 0 && (
            <div className="rounded-2xl border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-xs">
                  <tr><th className="text-left p-3">{bi('Дата', 'Date')}</th><th className="text-right p-3">{bi('Сума', 'Amount')}</th><th className="text-right p-3">{bi('Статус', 'Status')}</th></tr>
                </thead>
                <tbody>
                  {withdrawals.map((w) => (
                    <tr key={w.id} className="border-t border-border" data-testid={`wd-${w.id}`}>
                      <td className="p-3">{formatDateUk(w.created_at)}</td>
                      <td className="p-3 text-right">{fmtMoney(w.amount, w.currency)}</td>
                      <td className="p-3 text-right"><Badge status={w.status} bi={bi} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Certificates */}
      {tab === 'certificates' && (
        certs === null ? <Loading bi={bi} /> :
          certs.length === 0 ? <Empty bi={bi} text={bi('Сертифікати зʼявляться після закриття пулу', 'Certificates appear once a pool is funded')} /> :
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {certs.map((c) => (
                <div key={c.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`cert-${c.id}`}>
                  <div className="flex items-center justify-between">
                    <Award className="w-6 h-6" style={{ color: PRIMARY }} />
                    <Badge status={c.status} bi={bi} />
                  </div>
                  <div className="mt-3 font-mono text-xs text-muted-foreground">{c.serial}</div>
                  <div className="mt-1 text-sm font-semibold">{c.asset_id}</div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div><div className="text-[10px] text-muted-foreground">{bi('Частки', 'Units')}</div><div className="font-semibold">{(c.units || 0).toLocaleString('uk-UA')}</div></div>
                    <div><div className="text-[10px] text-muted-foreground">{bi('Частка', 'Ownership')}</div><div className="font-semibold">{(c.ownership_percent || 0).toFixed(4)}%</div></div>
                  </div>
                  <div className="mt-2 text-[11px] text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" />{formatDateUk(c.issued_at)}</div>
                </div>
              ))}
            </div>
      )}

      {contribPool && (
        <ContributeModal pool={contribPool} bi={bi}
          onClose={() => { setContribPool(null); loadAll(); }}
          onDone={loadAll} />
      )}
    </div>
  );
}

function Loading({ bi }) {
  return <div className="flex items-center gap-2 text-sm text-muted-foreground p-8"><Loader2 className="w-4 h-4 animate-spin" />{bi('Завантаження…', 'Loading…')}</div>;
}
function Empty({ text }) {
  return <div className="text-sm text-muted-foreground border border-dashed border-border rounded-2xl p-10 text-center">{text}</div>;
}
