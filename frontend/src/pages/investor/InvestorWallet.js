import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatDateUk, lumenError, usdFromUah } from '@/lib/lumenApi';
import {
  Wallet, ArrowDownToLine, ArrowUpFromLine, Clock, Loader2, X,
  CheckCircle2, AlertCircle, Banknote, History, Plus, Ban, TrendingUp,
} from 'lucide-react';

/** Sprint 7 — Investor Wallet & Withdrawals */

const WD_BADGE = {
  requested:    { label: 'Створено',     cls: 'bg-sky-100 text-sky-800' },
  under_review: { label: 'На розгляді',  cls: 'bg-amber-100 text-amber-800' },
  approved:     { label: 'Схвалено',     cls: 'bg-indigo-100 text-indigo-800' },
  processing:   { label: 'Виконується',  cls: 'bg-violet-100 text-violet-800' },
  paid:         { label: 'Виплачено',    cls: 'bg-emerald-100 text-emerald-800' },
  rejected:     { label: 'Відхилено',    cls: 'bg-red-100 text-red-700' },
  cancelled:    { label: 'Скасовано',    cls: 'bg-muted text-muted-foreground' },
};

const CANCELLABLE = ['requested', 'under_review'];

export default function InvestorWallet() {
  const [wallet, setWallet] = useState(null);
  const [meta, setMeta] = useState({ min_withdrawal_uah: 1000, currencies: ['USDT', 'USD'] });
  const [withdrawals, setWithdrawals] = useState([]);
  const [txns, setTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [w, wd, tx] = await Promise.all([
        lumen.get('/investor/wallet'),
        lumen.get('/investor/withdrawals'),
        lumen.get('/investor/wallet/transactions?limit=50'),
      ]);
      setWallet(w.data?.wallet || null);
      setMeta({
        min_withdrawal_uah: w.data?.min_withdrawal_uah ?? 1000,
        // USD-denominated UI: never offer UAH as a withdrawal currency.
        currencies: (w.data?.currencies || []).filter((c) => c !== 'UAH').length
          ? (w.data?.currencies || []).filter((c) => c !== 'UAH')
          : ['USDT', 'USD'],
      });
      setWithdrawals(wd.data?.items || []);
      setTxns(tx.data?.items || []);
      setError('');
    } catch (e) {
      setError(lumenError(e, 'Не вдалось завантажити гаманець'));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const flashOk = (msg) => { setFlash(msg); setError(''); setTimeout(() => setFlash(''), 4000); };

  const cancel = async (id) => {
    if (!window.confirm('Скасувати заявку на вивід? Кошти повернуться на баланс.')) return;
    try {
      await lumen.post(`/investor/withdrawals/${id}/cancel`, {});
      flashOk('Заявку скасовано, кошти повернуто.');
      load();
    } catch (e) { setError(lumenError(e, 'Не вдалось скасувати заявку')); }
  };

  const avail = Number(wallet?.available_balance || 0);

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="investor-wallet">
      <header className="mb-8 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Фінанси</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Гаманець</h1>
          <p className="mt-1 text-muted-foreground">
            Баланс формується з реєстру (ledger): дивіденди та повернення мінус виведені кошти.
          </p>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Link
            to="/investor/payments"
            data-testid="btn-topup-wallet"
            className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 px-4 sm:px-5 h-11 rounded-full border border-border bg-card hover:bg-muted/40 text-sm font-medium">
            <ArrowDownToLine className="w-4 h-4" /> Поповнити
          </Link>
          <button
            onClick={() => { setShowForm(true); setError(''); }}
            disabled={avail < meta.min_withdrawal_uah}
            data-testid="btn-request-withdrawal"
            className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 px-4 sm:px-5 h-11 rounded-full bg-[#2E5D4F] text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed">
            <ArrowUpFromLine className="w-4 h-4" /> Вивести
          </button>
        </div>
      </header>

      {flash && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {flash}</div>}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      {/* Balance cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        <BalanceCard label="Доступно до виводу" value={formatUAH(wallet?.available_balance)}
          accent="emerald" icon={Wallet} testid="wallet-available" big />
        <BalanceCard label="У резерві (заявки)" value={formatUAH(wallet?.pending_balance)}
          accent="amber" icon={Clock} testid="wallet-pending" />
        <BalanceCard label="Усього надійшло" value={formatUAH(wallet?.total_in)}
          accent="sky" icon={ArrowDownToLine} testid="wallet-total-in" />
        <BalanceCard label="Усього виведено" value={formatUAH(wallet?.total_out)}
          accent="neutral" icon={ArrowUpFromLine} testid="wallet-total-out" />
      </div>

      {loading && !wallet ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Withdrawals */}
          <section data-testid="withdrawals-section">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><Banknote className="w-4 h-4" /> Заявки на вивід</h2>
            {withdrawals.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-8 text-center" data-testid="withdrawals-empty">
                <ArrowUpFromLine className="w-8 h-8 mx-auto text-muted-foreground/60 mb-2" />
                <p className="text-sm text-muted-foreground">Заявок на вивід ще немає.</p>
              </div>
            ) : (
              <div className="space-y-2" data-testid="withdrawals-list">
                {withdrawals.map((w) => {
                  const b = WD_BADGE[w.status] || { label: w.status_label, cls: 'bg-muted' };
                  return (
                    <div key={w.id} data-testid={`withdrawal-${w.id}`}
                      className="rounded-2xl border border-border bg-card p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-lg font-bold tabular-nums">{w.currency === 'UAH' ? formatUAH(w.amount) : `${Number(w.amount).toLocaleString('en-US')} ${w.currency}`}</p>
                          <p className="text-xs text-muted-foreground truncate">{w.bank_name} · {w.iban}</p>
                        </div>
                        <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <p className="text-xs text-muted-foreground">{formatDateUk(w.created_at)}</p>
                        {CANCELLABLE.includes(w.status) && (
                          <button onClick={() => cancel(w.id)} data-testid={`cancel-${w.id}`}
                            className="inline-flex items-center gap-1 text-xs text-red-600 hover:text-red-700 font-medium">
                            <Ban className="w-3.5 h-3.5" /> Скасувати
                          </button>
                        )}
                      </div>
                      {w.status === 'rejected' && w.admin_comment && (
                        <p className="mt-2 text-xs text-red-600">⚠ {w.admin_comment}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Transactions history */}
          <section data-testid="transactions-section">
            <h2 className="font-semibold mb-3 flex items-center gap-2"><History className="w-4 h-4" /> Історія руху коштів</h2>
            {txns.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-8 text-center">
                <p className="text-sm text-muted-foreground">Операцій ще немає.</p>
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-card divide-y divide-border" data-testid="transactions-list">
                {txns.map((t) => {
                  const isIn = t.direction === 'in';
                  return (
                    <div key={t.id} className="flex items-center justify-between gap-3 p-3" data-testid={`txn-${t.id}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center ${isIn ? 'bg-emerald-100' : 'bg-red-100'}`}>
                          {isIn ? <ArrowDownToLine className="w-4 h-4 text-emerald-700" /> : <ArrowUpFromLine className="w-4 h-4 text-red-600" />}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{t.reason_label}</p>
                          <p className="text-xs text-muted-foreground">{formatDateUk(t.created_at)}</p>
                        </div>
                      </div>
                      <span className={`font-mono font-semibold tabular-nums text-sm shrink-0 ${isIn ? 'text-emerald-700' : 'text-red-600'}`}>
                        {isIn ? '+' : '−'} {formatUAH(t.amount_uah)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}

      {showForm && (
        <WithdrawalFormModal
          available={avail}
          minAmount={meta.min_withdrawal_uah}
          currencies={meta.currencies}
          onClose={() => setShowForm(false)}
          onCreated={() => { setShowForm(false); flashOk('Заявку на вивід створено. Кошти зарезервовано.'); load(); }}
        />
      )}
    </div>
  );
}

const BalanceCard = ({ label, value, accent = 'neutral', icon: Icon, testid, big }) => {
  const accentMap = {
    emerald: 'border-emerald-200 bg-emerald-50/50',
    amber:   'border-amber-200 bg-amber-50/40',
    sky:     'border-sky-200 bg-sky-50/40',
    neutral: 'border-border bg-card',
  };
  return (
    <div data-testid={testid} className={`rounded-2xl border p-4 ${accentMap[accent]} ${big ? 'sm:col-span-2 lg:col-span-1' : ''}`}>
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon className="w-4 h-4" />}
        <p className="text-[11px] uppercase tracking-widest">{label}</p>
      </div>
      <p className={`mt-2 font-bold tabular-nums ${big ? 'text-3xl' : 'text-2xl'}`}>{value}</p>
    </div>
  );
};

function WithdrawalFormModal({ available, minAmount, currencies, onClose, onCreated }) {
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('USDT');
  const [iban, setIban] = useState('');
  const [bankName, setBankName] = useState('');
  const [beneficiary, setBeneficiary] = useState('');
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    setError('');
    const amt = Number(amount);
    if (!amt || amt <= 0) { setError('Вкажіть коректну суму'); return; }
    if (currency === 'UAH' && amt > available + 0.01) {
      setError(`Недостатньо коштів. Доступно: ${formatUAH(available)}`); return;
    }
    if (!iban.trim() || !bankName.trim() || !beneficiary.trim()) {
      setError('Заповніть IBAN, банк і отримувача'); return;
    }
    setActing(true);
    try {
      await lumen.post('/investor/withdrawals', {
        amount: amt, currency,
        iban: iban.trim(), bank_name: bankName.trim(), beneficiary_name: beneficiary.trim(),
      });
      onCreated();
    } catch (e) { setError(lumenError(e, 'Не вдалось створити заявку')); }
    finally { setActing(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="withdrawal-form-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md h-full bg-background border-l border-border shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">Заявка на вивід</h2>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg" data-testid="form-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <div className="rounded-xl bg-emerald-50/60 border border-emerald-200 p-3 flex items-center gap-2 text-sm">
            <TrendingUp className="w-4 h-4 text-emerald-700" />
            <span>Доступно до виводу: <strong>{formatUAH(available)}</strong></span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <label className="block col-span-2">
              <span className="text-xs uppercase tracking-widest text-muted-foreground">Сума</span>
              <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
                data-testid="input-amount" min={0} step="0.01"
                placeholder={`мін. $${Math.round(usdFromUah(minAmount))}`}
                className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm" />
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-widest text-muted-foreground">Валюта</span>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)}
                data-testid="input-currency"
                className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm">
                {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>

          <label className="block">
            <span className="text-xs uppercase tracking-widest text-muted-foreground">IBAN</span>
            <input value={iban} onChange={(e) => setIban(e.target.value)}
              data-testid="input-iban" placeholder="UA21 3223 1300 0002 6007 2335 6600 1"
              className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm font-mono" />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-muted-foreground">Банк</span>
            <input value={bankName} onChange={(e) => setBankName(e.target.value)}
              data-testid="input-bank" placeholder="ПриватБанк"
              className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm" />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-muted-foreground">Отримувач</span>
            <input value={beneficiary} onChange={(e) => setBeneficiary(e.target.value)}
              data-testid="input-beneficiary" placeholder="Прізвище Ім'я По батькові"
              className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm" />
          </label>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button onClick={submit} disabled={acting}
            data-testid="submit-withdrawal"
            className="w-full inline-flex items-center justify-center gap-2 px-5 h-11 rounded-full bg-[#2E5D4F] text-white font-medium disabled:opacity-60">
            {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Створити заявку
          </button>
          <p className="text-xs text-muted-foreground text-center">
            Кошти буде зарезервовано до підтвердження виплати. Заявку можна скасувати, поки вона на розгляді.
          </p>
        </div>
      </div>
    </div>
  );
}
