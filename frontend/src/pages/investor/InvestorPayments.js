import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, API, lumenError } from '@/lib/lumenApi';
import {
  Wallet, Upload, Loader2, CheckCircle2, AlertCircle, Clock, FileText,
  X, Copy, Download, ArrowRight, ShieldCheck,
} from 'lucide-react';

/** Sprint 6 — Investor «Мої платежі» (My Funding) */

const PAYMENT_STATUS_BADGE = {
  awaiting_payment: { label: 'Очікує оплату',    cls: 'bg-amber-100 text-amber-800',  icon: Clock },
  paid:              { label: 'На перевірці',      cls: 'bg-sky-100 text-sky-800',       icon: Upload },
  under_review:     { label: 'Уточнення',          cls: 'bg-orange-100 text-orange-800', icon: AlertCircle },
  confirmed:         { label: 'Підтверджено',     cls: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  rejected:          { label: 'Відхилено',        cls: 'bg-red-100 text-red-700',        icon: X },
  cancelled:         { label: 'Скасовано',        cls: 'bg-muted text-muted-foreground',  icon: X },
};

const FILTERS = [
  { value: '',                 label: 'Всі' },
  { value: 'awaiting_payment', label: 'Очікують оплати' },
  { value: 'paid',             label: 'На перевірці' },
  { value: 'under_review',     label: 'Уточнення' },
  { value: 'confirmed',         label: 'Підтверджено' },
  { value: 'rejected',          label: 'Відхилено' },
];

export default function InvestorPayments() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/investor/payments' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
      setError('');
    } catch (e) {
      setError(lumenError(e, 'Не вдалось завантажити платежі'));
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await lumen.get(`/investor/payments/${id}`);
      setSelected(r.data);
    } catch (e) { setError(lumenError(e, 'Не вдалось відкрити деталі платежу')); }
  };

  const totals = {
    awaiting: counts.awaiting_payment || 0,
    inReview: (counts.paid || 0) + (counts.under_review || 0),
    confirmed: counts.confirmed || 0,
    confirmedAmount: items
      .filter((p) => p.status === 'confirmed')
      .reduce((s, p) => s + (Number(p.amount_uah) || 0), 0),
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="investor-payments">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Фінансування</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Мої платежі</h1>
        <p className="mt-1 text-muted-foreground">
          Оплачуйте підписані інвестиції та відстежуйте підтвердження комплаєнсом. Ownership активу з’являється лише після підтвердженої оплати.
        </p>
      </header>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      <div className="grid sm:grid-cols-4 gap-3 mb-6">
        <StatCard label="Очікують оплати" value={totals.awaiting} accent="amber" testid="stat-awaiting" />
        <StatCard label="На перевірці" value={totals.inReview} accent="sky" testid="stat-review" />
        <StatCard label="Підтверджених" value={totals.confirmed} accent="emerald" testid="stat-confirmed" />
        <StatCard label="Оплачено всього" value={formatUAH(totals.confirmedAmount)} accent="neutral" testid="stat-amount" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4" data-testid="payments-filters">
        {FILTERS.map((f) => (
          <button key={f.value}
            onClick={() => setFilter(f.value)}
            data-testid={`filter-${f.value || 'all'}`}
            className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-xs font-medium border transition ${
              filter === f.value ? 'bg-foreground text-background border-foreground'
                                 : 'border-border hover:border-[#2E5D4F]'
            }`}>
            {f.label}
            {counts[f.value] !== undefined && (
              <span className={`px-1.5 rounded ${filter === f.value ? 'bg-background/20' : 'bg-muted'}`}>{counts[f.value]}</span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-20 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3" data-testid="payments-list">
          {items.map((p) => <PaymentCard key={p.id} payment={p} onOpen={() => openDetail(p.id)} />)}
        </div>
      )}

      {selected && (
        <PaymentDetailDrawer
          payment={selected}
          onClose={() => setSelected(null)}
          onChanged={() => { setSelected(null); load(); }}
        />
      )}
    </div>
  );
}

const StatCard = ({ label, value, accent = 'neutral', testid }) => {
  const accentMap = {
    amber:    'border-amber-200 bg-amber-50/40',
    sky:      'border-sky-200 bg-sky-50/40',
    emerald:  'border-emerald-200 bg-emerald-50/40',
    neutral:  'border-border bg-card',
  };
  return (
    <div data-testid={testid} className={`rounded-2xl border p-4 ${accentMap[accent]}`}>
      <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
};

const EmptyState = () => (
  <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="payments-empty">
    <Wallet className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
    <p className="font-semibold">Платежів поки немає</p>
    <p className="text-sm text-muted-foreground mt-1">
      Платіж відкриється автоматично після підписання договору та підтвердження верифікації (KYC).
    </p>
  </div>
);

const PaymentCard = ({ payment, onOpen }) => {
  const meta = PAYMENT_STATUS_BADGE[payment.status] || { label: payment.status_label, cls: 'bg-muted', icon: Clock };
  const Icon = meta.icon;
  return (
    <div
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen(); }}
      data-testid={`payment-card-${payment.id}`}
      className="w-full text-left rounded-2xl border border-border bg-card p-4 hover:border-[#2E5D4F] hover:shadow-sm transition cursor-pointer">
      <div className="flex items-start gap-3">
        <div className="shrink-0 w-10 h-10 rounded-xl bg-muted flex items-center justify-center">
          <Icon className="w-5 h-5 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <p className="font-semibold truncate">{payment.asset_title || '—'}</p>
            <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
          </div>
          <div className="flex items-baseline gap-3 mt-1">
            <p className="text-lg font-bold tabular-nums">{Number(payment.amount).toLocaleString('uk-UA')} {payment.currency}</p>
            {payment.currency !== 'UAH' && (
              <span className="text-xs text-muted-foreground">≈ {formatUAH(payment.amount_uah)}</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
            <span>Відкрито: {formatDateUk(payment.created_at)}</span>
            {payment.proof_ids?.length > 0 && (
              <span className="inline-flex items-center gap-1"><FileText className="w-3 h-3" /> {payment.proof_ids.length} файл(и)</span>
            )}
            {payment.status === 'rejected' && payment.reject_reason && (
              <span className="text-red-600 truncate max-w-[280px]">⚠ {payment.reject_reason}</span>
            )}
          </div>
        </div>
        <ArrowRight className="w-4 h-4 text-muted-foreground/60 shrink-0 mt-3" />
      </div>
    </div>
  );
};

/* ─────────────────────────── Detail drawer ──────────────────────── */

function PaymentDetailDrawer({ payment, onClose, onChanged }) {
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');
  const [method, setMethod] = useState(payment.payment_method || 'bank_transfer');
  const [fundingAccountId, setFundingAccountId] = useState(payment.funding_account_id || (payment.funding_accounts?.[0]?.id || ''));
  const [note, setNote] = useState('');
  const [data, setData] = useState(payment);

  const reload = useCallback(async () => {
    try {
      const r = await lumen.get(`/investor/payments/${data.id}`);
      setData(r.data);
    } catch (_e) {}
  }, [data.id]);

  const uploadProof = async (file) => {
    if (!file) return;
    setActing(true); setError(''); setFlash('');
    try {
      const fd = new FormData(); fd.append('file', file);
      await lumen.post(`/investor/payments/${data.id}/proof`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setFlash('Файл завантажено');
      await reload();
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити файл')); }
    finally { setActing(false); }
  };

  const deleteProof = async (proofId) => {
    if (!window.confirm('Видалити підтвердження?')) return;
    setActing(true); setError(''); setFlash('');
    try {
      await lumen.delete(`/investor/payments/${data.id}/proof/${proofId}`);
      setFlash('Файл видалено');
      await reload();
    } catch (e) { setError(lumenError(e, 'Не вдалось видалити файл')); }
    finally { setActing(false); }
  };

  const submit = async () => {
    setActing(true); setError(''); setFlash('');
    try {
      await lumen.post(`/investor/payments/${data.id}/submit`, {
        payment_method: method,
        funding_account_id: fundingAccountId || null,
        note: note || null,
      });
      setFlash('Платіж надіслано на перевірку');
      await reload();
      setTimeout(onChanged, 800);
    } catch (e) { setError(lumenError(e, 'Не вдалось подати платіж')); }
    finally { setActing(false); }
  };

  const meta = PAYMENT_STATUS_BADGE[data.status] || { label: data.status_label, cls: 'bg-muted', icon: Clock };
  const canEdit = ['awaiting_payment', 'under_review', 'rejected'].includes(data.status);
  const account = data.funding_accounts?.find((a) => a.id === fundingAccountId) || data.funding_accounts?.[0];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="payment-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full bg-background border-l border-border shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Платіж #{data.id.slice(-6)}</p>
            <h2 className="text-xl font-bold mt-0.5">{data.asset_title}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg" data-testid="drawer-close"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-6 space-y-6">
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">До оплати</p>
              <p className="text-3xl font-bold tabular-nums mt-1">{Number(data.amount).toLocaleString('uk-UA')} {data.currency}</p>
              {data.currency !== 'UAH' && <p className="text-xs text-muted-foreground mt-0.5">≈ {formatUAH(data.amount_uah)} · курс {data.fx_rate}</p>}
            </div>
            <span className={`text-sm font-medium px-3 py-1 rounded-full ${meta.cls}`}>{meta.label}</span>
          </div>

          {data.status === 'rejected' && data.reject_reason && (
            <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
              <p className="font-semibold mb-1">Платіж відхилено комплаєнсом</p>
              <p>{data.reject_reason}</p>
              <p className="text-xs text-red-600/80 mt-2">Перевірте платіж і завантажте підтвердження ще раз.</p>
            </div>
          )}
          {data.status === 'under_review' && data.admin_note && (
            <div className="rounded-xl bg-orange-50 border border-orange-200 p-4 text-sm text-orange-800">
              <p className="font-semibold mb-1">Уточнення від комплаєнсу</p>
              <p>{data.admin_note}</p>
            </div>
          )}
          {data.status === 'confirmed' && (
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 mt-0.5" />
              <div>
                <p className="font-semibold">Платіж підтверджено</p>
                <p>Інвестиція активна, частка зафіксована у портфелі.</p>
              </div>
            </div>
          )}

          {/* Sprint 11 — Acquiring providers */}
          {canEdit && <AcquiringPanel paymentRequestId={data.id} reference={data.reference} amount={data.amount} currency={data.currency} onSettled={reload} />}

          {/* Funding instructions */}
          {canEdit && data.funding_accounts?.length > 0 && (
            <section data-testid="funding-instructions">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Реквізити для оплати</h3>
              {data.funding_accounts.length > 1 && (
                <div className="mb-3 flex gap-2 flex-wrap">
                  {data.funding_accounts.map((a) => (
                    <button key={a.id} onClick={() => setFundingAccountId(a.id)}
                      data-testid={`account-${a.id}`}
                      className={`text-xs px-3 h-8 rounded-full border ${fundingAccountId === a.id ? 'bg-foreground text-background border-foreground' : 'border-border'}`}>
                      {a.name}
                    </button>
                  ))}
                </div>
              )}
              {account && (
                <div className="rounded-xl border border-border bg-muted/40 p-4 space-y-2 text-sm">
                  <CopyRow label="Назва рахунку" value={account.name} />
                  {account.bank_name && <CopyRow label="Банк" value={account.bank_name} />}
                  {account.iban && <CopyRow label="IBAN" value={account.iban} mono />}
                  {account.swift_code && <CopyRow label="SWIFT" value={account.swift_code} mono />}
                  {account.beneficiary && <CopyRow label="Отримувач" value={account.beneficiary} />}
                  {account.edrpou && <CopyRow label="ЄДРПОУ" value={account.edrpou} mono />}
                  {account.purpose_template && <CopyRow label="Призначення" value={account.purpose_template.replace('{contract_number}', `(№ договору)`)} />}
                  {account.notes && <p className="text-xs text-muted-foreground pt-1">{account.notes}</p>}
                </div>
              )}
            </section>
          )}

          {/* Proofs */}
          <section>
            <h3 className="font-semibold mb-3 flex items-center gap-2"><FileText className="w-4 h-4" /> Підтвердження оплати ({(data.proofs || []).length})</h3>
            {(data.proofs || []).length === 0 && canEdit && (
              <p className="text-sm text-muted-foreground mb-2">Завантажте квитанцію PDF або скриншот переказу.</p>
            )}
            <div className="space-y-2">
              {(data.proofs || []).map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 rounded-xl border border-border p-3 bg-card"
                  data-testid={`proof-${p.id}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{p.filename}</p>
                      <p className="text-xs text-muted-foreground">{(p.size / 1024).toFixed(0)} КБ · {formatDateUk(p.uploaded_at)}</p>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <a href={`${API}/payment-proofs/${p.id}/file`} target="_blank" rel="noopener noreferrer"
                       className="p-2 hover:bg-muted rounded-lg text-muted-foreground hover:text-foreground" title="Відкрити">
                      <Download className="w-4 h-4" />
                    </a>
                    {canEdit && (
                      <button onClick={() => deleteProof(p.id)} disabled={acting}
                        className="p-2 hover:bg-red-50 rounded-lg text-muted-foreground hover:text-red-600" title="Видалити">
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {canEdit && (
              <label className="mt-3 inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] cursor-pointer text-sm" data-testid="upload-proof-btn">
                <Upload className="w-4 h-4" /> Завантажити підтвердження
                <input type="file" accept="image/png,image/jpeg,image/webp,application/pdf"
                       hidden onChange={(e) => uploadProof(e.target.files?.[0])} disabled={acting} />
              </label>
            )}
          </section>

          {/* Submit form */}
          {canEdit && (data.proofs || []).length > 0 && (
            <section className="rounded-2xl border border-[#2E5D4F]/30 bg-emerald-50/40 p-4" data-testid="submit-section">
              <p className="font-semibold mb-2">Подати платіж на перевірку</p>
              <div className="grid sm:grid-cols-2 gap-3 mb-3">
                <label className="block">
                  <span className="text-xs uppercase tracking-widest text-muted-foreground">Метод</span>
                  <select value={method} onChange={(e) => setMethod(e.target.value)}
                          className="mt-1 w-full h-10 rounded-lg border border-border bg-background px-3 text-sm">
                    <option value="bank_transfer">Банківський переказ</option>
                    <option value="swift">SWIFT переказ</option>
                  </select>
                </label>
                <label className="block sm:col-span-2">
                  <span className="text-xs uppercase tracking-widest text-muted-foreground">Коментар (необов’язковий)</span>
                  <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Дата переказу, особливості…"
                         className="mt-1 w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
                </label>
              </div>
              {error && <p className="text-sm text-red-600 mb-2">{error}</p>}
              {flash && <p className="text-sm text-emerald-700 mb-2">{flash}</p>}
              <button onClick={submit} disabled={acting}
                data-testid="submit-payment-btn"
                className="inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white font-medium disabled:opacity-60">
                {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                Надіслати на перевірку
              </button>
            </section>
          )}

          {!canEdit && (error || flash) && (
            <div className="text-sm">
              {error && <p className="text-red-600">{error}</p>}
              {flash && <p className="text-emerald-700">{flash}</p>}
            </div>
          )}

          {/* History */}
          <section>
            <h3 className="font-semibold mb-3">Історія</h3>
            <ol className="space-y-2">
              {(data.history || []).slice().reverse().map((h, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-2 h-2 rounded-full bg-[#2E5D4F] mt-1.5" />
                  <div>
                    <p>{h.comment}</p>
                    <p className="text-xs text-muted-foreground">{formatDateUk(h.at)} · {h.status}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

const CopyRow = ({ label, value, mono }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className={`truncate ${mono ? 'font-mono text-sm' : 'text-sm'}`}>{value}</p>
      </div>
      <button onClick={copy} className="shrink-0 p-1.5 hover:bg-background rounded-lg text-muted-foreground" title="Копіювати">
        <Copy className="w-3.5 h-3.5" />
      </button>
      {copied && <span className="text-xs text-emerald-600">скопійовано</span>}
    </div>
  );
};


// ============ Sprint 11 — Acquiring providers panel ============
const AcquiringPanel = ({ paymentRequestId, reference, amount, currency, onSettled }) => {
  const [providers, setProviders] = useState([]);
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    lumen.get('/banking/providers')
      .then(r => setProviders(r.data?.providers || []))
      .catch(() => setProviders([]));
  }, []);

  const checkout = async (provider) => {
    setBusy(provider); setError(''); setResult(null);
    try {
      const r = await lumen.post(`/investor/payments/${paymentRequestId}/checkout`, { provider });
      setResult(r.data);
      if (r.data?.payment_url && provider !== 'swift') {
        window.open(r.data.payment_url, '_blank', 'noopener');
      }
      if (r.data?.mode === 'mock') {
        // poll for settlement
        let tries = 0;
        const poll = setInterval(async () => {
          tries++;
          try {
            const fresh = await lumen.get(`/investor/payments/${paymentRequestId}`);
            if (fresh.data?.status === 'confirmed') {
              clearInterval(poll);
              onSettled && onSettled();
            }
          } catch (_) {}
          if (tries > 15) clearInterval(poll);
        }, 1500);
      }
    } catch (e) {
      setError(e?.response?.data?.message || e?.response?.data?.detail || 'Помилка');
    } finally {
      setBusy('');
    }
  };

  if (!providers.length) return null;

  return (
    <section data-testid="acquiring-panel">
      <h3 className="font-semibold mb-3 flex items-center gap-2">
        <span>Швидка оплата</span>
        {reference && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">ref: {reference}</span>
        )}
      </h3>
      <div className="grid sm:grid-cols-3 gap-2">
        {providers.map(p => (
          <button
            key={p.provider}
            onClick={() => checkout(p.provider)}
            disabled={busy === p.provider}
            className="text-left p-3 rounded-xl border border-border bg-card hover:bg-muted/30 disabled:opacity-60"
            data-testid={`acquire-${p.provider}`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{p.label}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${p.mode === 'live' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                {p.mode}
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground mt-1">{p.audience}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">{p.supports.join(' · ')}</div>
          </button>
        ))}
      </div>
      {error && <div className="mt-2 p-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">{error}</div>}
      {result && (
        <div className="mt-3 p-3 rounded-xl border border-border bg-muted/40 text-xs">
          {result.payment_url && result.provider !== 'swift' && (
            <p>
              <strong>{result.provider}</strong> ({result.mode}):{' '}
              <a href={result.payment_url} target="_blank" rel="noreferrer" className="text-blue-600 underline break-all">{result.payment_url}</a>
            </p>
          )}
          {result.provider === 'swift' && result.instructions && (
            <div className="space-y-1">
              <p className="font-semibold mb-1">SWIFT-інструкції:</p>
              <p><span className="text-muted-foreground">Bank:</span> {result.instructions.bank_name} ({result.instructions.swift_code})</p>
              <p><span className="text-muted-foreground">IBAN USD:</span> <span className="font-mono">{result.instructions.iban_usd}</span></p>
              <p><span className="text-muted-foreground">IBAN EUR:</span> <span className="font-mono">{result.instructions.iban_eur}</span></p>
              <p><span className="text-muted-foreground">Beneficiary:</span> {result.instructions.beneficiary}</p>
              <p><span className="text-muted-foreground">Reference (призначення):</span> <span className="font-mono font-bold">{result.reference}</span></p>
            </div>
          )}
          {result.instructions && result.provider !== 'swift' && (
            <p className="text-muted-foreground mt-1">{result.instructions}</p>
          )}
        </div>
      )}
    </section>
  );
};
