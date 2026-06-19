/**
 * Reconcile dialog: admin enters bank statement reference + observed amount/currency.
 * Backend computes matched / delta_amount / currency_mismatch and stores reconciliation.
 */
import { useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { X, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { formatAmount, methodLabelFromTransfer } from '@/pages/funding/_shared';

export default function ReconcileDialog({ transfer, t, onClose, onDone }) {
  const [bankRef, setBankRef] = useState(`BANK-${transfer.reference || ''}`);
  const [amount, setAmount] = useState(String(transfer.amount || ''));
  const [currency, setCurrency] = useState(transfer.currency || 'EUR');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState(null);

  const run = async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await lumen.post(
        `/admin/lumen/institutional/rails/transfers/${transfer.id}/reconcile`,
        {
          bank_statement_ref: bankRef,
          amount_observed: Number(amount),
          currency_observed: currency,
        },
      );
      setResult(r.data?.reconciliation || null);
    } catch (e) {
      setErr(lumenError(e, 'Reconcile failed'));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} data-testid="reconcile-dialog">
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-lg bg-background border border-border rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold">{t('admin.reconcile.title')}</h3>
            <p className="text-xs text-muted-foreground mt-1">
              {methodLabelFromTransfer(transfer.rail)} · {formatAmount(transfer.amount, transfer.currency)} · <span className="font-mono">{transfer.reference}</span>
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted" data-testid="reconcile-close"><X className="w-4 h-4" /></button>
        </div>

        <div className="space-y-3">
          <Field label={t('admin.reconcile.field.bank_ref')} value={bankRef} onChange={setBankRef} testid="reconcile-bank-ref" />
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('admin.reconcile.field.amount_observed')} value={amount} onChange={setAmount} testid="reconcile-amount" type="number" />
            <Field label={t('admin.reconcile.field.currency_observed')} value={currency} onChange={(v) => setCurrency(v.toUpperCase())} testid="reconcile-currency" />
          </div>
        </div>

        {err && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">
            <AlertTriangle className="w-4 h-4" /> {err}
          </div>
        )}
        {result && (
          <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
            result.matched
              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200'
              : 'bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200'
          }`}>
            <CheckCircle2 className="w-4 h-4 mt-0.5" />
            <div>
              <div className="font-semibold">
                {result.matched ? t('admin.reconcile.matched.ok') : t('admin.reconcile.matched.bad')}
              </div>
              <div className="text-xs mt-1">
                {t('admin.reconcile.delta')}: {result.delta_amount}
                {result.currency_mismatch ? ` · ${t('admin.flag.currency_mismatch')}` : ''}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm border border-border bg-card hover:bg-muted">{t('common.close')}</button>
          <button
            onClick={run}
            disabled={busy || !bankRef || !amount}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-semibold bg-foreground text-background hover:opacity-90 disabled:opacity-40"
            data-testid="reconcile-run-btn"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {t('admin.reconcile.btn.run')}
          </button>
          {result && (
            <button
              onClick={onDone}
              className="px-3 py-1.5 rounded-lg text-sm font-semibold border border-border bg-card hover:bg-muted"
              data-testid="reconcile-done-btn"
            >
              {t('common.close')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, testid, type = 'text' }) {
  return (
    <div className="space-y-1">
      <label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
        data-testid={testid}
      />
    </div>
  );
}
