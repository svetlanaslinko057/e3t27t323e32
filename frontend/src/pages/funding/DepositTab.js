/**
 * Deposit wizard: amount + currency + method → reference + bank details + proof.
 */
import { useEffect, useMemo, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { trackEvent } from '@/lib/activityTracker';
import { Building2, Send, CheckCircle2, AlertTriangle, Loader2, Landmark, Zap, Globe2 } from 'lucide-react';
import { CopyButton, formatAmount, formatIban, useBankAccounts } from './_shared';
import ProofUploader from './ProofUploader';
import LumenSelect from '@/components/ui/LumenSelect';

const METHODS = [
  { id: 'sepa',         icon: Landmark, currencies: ['EUR'], min: 1000 },
  { id: 'sepa_instant', icon: Zap,      currencies: ['EUR'], min: 1000 },
  { id: 'swift',        icon: Globe2,   currencies: ['USD','EUR','GBP','CHF','JPY','CAD','AUD','NOK','SEK','DKK'], min: 10000 },
];

export default function DepositTab({ t, onCreated }) {
  const { accounts } = useBankAccounts();
  const [method, setMethod] = useState('sepa');
  const [amount, setAmount] = useState('1000');
  const [currency, setCurrency] = useState('EUR');
  const [iban, setIban] = useState('');
  const [bic, setBic] = useState('');
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [charges, setCharges] = useState('SHA');
  const [ibanInfo, setIbanInfo] = useState(null);   // {ok, country, sepa_eligible}
  const [bicInfo, setBicInfo] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState('');
  const [created, setCreated] = useState(null);     // {transfer, beneficiary}

  const m = METHODS.find((x) => x.id === method) || METHODS[0];
  const beneficiary = useMemo(() => {
    if (method === 'swift') return accounts.find((a) => a.method === 'swift');
    if (method === 'sepa' || method === 'sepa_instant')
      return accounts.find((a) => a.method === 'sepa');
    return accounts.find((a) => a.currency === currency);
  }, [accounts, method, currency]);

  useEffect(() => {
    // Force currency to match method constraints
    if (!m.currencies.includes(currency)) {
      setCurrency(m.currencies[0]);
    }
  }, [method]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Live IBAN validation (debounced minimal)
  useEffect(() => {
    let active = true;
    if (!iban || iban.replace(/\s+/g, '').length < 8) { setIbanInfo(null); return; }
    const id = setTimeout(async () => {
      try {
        const r = await lumen.get(
          `/lumen/institutional/rails/iban/validate?iban=${encodeURIComponent(iban)}`,
        );
        if (active) setIbanInfo(r.data);
      } catch (_e) { if (active) setIbanInfo({ ok: false }); }
    }, 400);
    return () => { active = false; clearTimeout(id); };
  }, [iban]);

  // Live BIC validation for SWIFT
  useEffect(() => {
    let active = true;
    if (method !== 'swift' || !bic || bic.length < 4) { setBicInfo(null); return; }
    const id = setTimeout(async () => {
      try {
        const r = await lumen.get(
          `/lumen/institutional/rails/bic/validate?bic=${encodeURIComponent(bic)}`,
        );
        if (active) setBicInfo(r.data);
      } catch (_e) { if (active) setBicInfo({ ok: false }); }
    }, 400);
    return () => { active = false; clearTimeout(id); };
  }, [bic, method]);

  const canSubmit = (
    !!iban && ibanInfo?.ok && (method !== 'swift' || (bic && bicInfo?.ok))
    && Number(amount) >= m.min && currency && name.trim().length >= 2
  );

  const onSubmit = async () => {
    setErr(''); setSubmitting(true);
    try {
      const path = method === 'swift'
        ? '/lumen/institutional/rails/swift/transfers'
        : '/lumen/institutional/rails/sepa/transfers';
      const body = {
        direction: 'inbound',
        amount: Number(amount),
        currency,
        beneficiary_iban: iban.replace(/\s+/g, ''),
        beneficiary_name: name.trim(),
        purpose: purpose || undefined,
      };
      if (method === 'sepa_instant') body.instant = true;
      if (method === 'swift') {
        body.beneficiary_bic = bic.replace(/\s+/g, '').toUpperCase();
        body.charges = charges;
      }
      const r = await lumen.post(path, body);
      try { trackEvent('funding_started', { surface: 'investor', method, amount: body.amount }); } catch (_) {}
      setCreated({ transfer: r.data, beneficiary });
      if (onCreated) onCreated(r.data);
    } catch (e) {
      setErr(lumenError(e, 'Failed to create transfer'));
    } finally {
      setSubmitting(false);
    }
  };

  // Success view ────────────────────────────────────────────────────────────
  if (created) {
    const tx = created.transfer;
    const ben = created.beneficiary;
    return (
      <div className="max-w-3xl space-y-6" data-testid="deposit-created">
        <div className="flex items-start gap-3 p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900">
          <CheckCircle2 className="w-5 h-5 text-emerald-700 dark:text-emerald-300 mt-0.5" />
          <div>
            <h3 className="font-semibold text-emerald-900 dark:text-emerald-100">{t('deposit.created.title')}</h3>
            <p className="text-sm text-emerald-800 dark:text-emerald-200 mt-1">{t('deposit.created.lead')}</p>
          </div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-card space-y-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider">{t('deposit.field.amount')} · {t('deposit.field.currency')}</div>
          <div className="text-3xl font-semibold tracking-tight">{formatAmount(tx.amount, tx.currency)}</div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-card space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Reference</div>
            <CopyButton value={tx.reference} t={t} />
          </div>
          <div className="font-mono text-lg tracking-tight">{tx.reference}</div>
          <p className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed">
            {t('deposit.warning.reference')}
          </p>
        </div>

        {ben && (
          <div className="p-5 rounded-xl border border-border bg-card space-y-3">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">{t('beneficiary.title')}</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <Field label={t('beneficiary.field.beneficiary')} value={ben.beneficiary} t={t} />
              <Field label={t('beneficiary.field.bank')} value={ben.bank_name} t={t} />
              <Field label={t('beneficiary.field.iban')} value={formatIban(ben.iban)} t={t} mono />
              <Field label={t('beneficiary.field.bic')} value={ben.swift_code} t={t} mono />
              {ben.edrpou && <Field label={t('beneficiary.field.edrpou')} value={ben.edrpou} t={t} mono />}
              <Field label={t('beneficiary.field.currency')} value={ben.currency} t={t} />
            </div>
          </div>
        )}

        <div className="p-5 rounded-xl border border-border bg-card space-y-3">
          <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Send className="w-3.5 h-3.5" /> {t('deposit.upload_proof')}
          </div>
          <p className="text-sm text-muted-foreground">{t('deposit.upload_proof_lead')}</p>
          <ProofUploader transferId={tx.id} t={t} />
        </div>

        <div>
          <button
            type="button"
            onClick={() => setCreated(null)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-border bg-card hover:bg-muted"
            data-testid="deposit-new-btn"
          >
            {t('deposit.title')}
          </button>
        </div>
      </div>
    );
  }

  // Wizard ──────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl space-y-6" data-testid="deposit-tab">
      <header>
        <h2 className="text-2xl font-bold tracking-tight">{t('deposit.title')}</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{t('deposit.lead')}</p>
      </header>

      {/* Method picker */}
      <section className="space-y-2">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">{t('deposit.step.method')}</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {METHODS.map((mm) => {
            const Icon = mm.icon;
            const active = method === mm.id;
            return (
              <button
                key={mm.id}
                type="button"
                onClick={() => setMethod(mm.id)}
                className={`flex flex-col items-start gap-2 p-4 rounded-xl border text-left transition-all ${
                  active ? 'border-signal bg-signal/5' : 'border-border bg-card hover:bg-muted'
                }`}
                data-testid={`deposit-method-${mm.id}`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-semibold">{t(`deposit.method.${mm.id}`)}</span>
                <span className="text-xs text-muted-foreground">{t(`deposit.method.${mm.id}.desc`)}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Amount + currency */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 space-y-2">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">{t('deposit.field.amount')}</label>
          <input
            type="number"
            min={m.min}
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-lg font-semibold"
            data-testid="deposit-amount"
          />
          {Number(amount) < m.min && (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              {t('deposit.below_min', null, { min: m.min, currency })}
            </p>
          )}
        </div>
        <div className="space-y-2">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">{t('deposit.field.currency')}</label>
          <LumenSelect
            value={currency}
            onValueChange={setCurrency}
            options={m.currencies.map((c) => ({ value: c, label: c }))}
            testid="deposit-currency"
          />
        </div>
      </section>

      {/* Sender bank */}
      <section className="space-y-3 p-5 rounded-xl border border-border bg-card">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">{t('deposit.step.beneficiary')}</div>
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">{t('deposit.field.beneficiary_name')}</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Holdings BV"
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
            data-testid="deposit-name"
          />
        </div>
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">{t('deposit.field.iban')}</label>
          <input
            type="text"
            value={iban}
            onChange={(e) => setIban(e.target.value.toUpperCase())}
            placeholder="DE89 3704 0044 0532 0130 00"
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono"
            data-testid="deposit-iban"
          />
          <div className="text-xs">
            {ibanInfo?.ok && (
              <span className="text-emerald-700 dark:text-emerald-300">✓ {t('deposit.field.iban.ok')} · {ibanInfo.country}{ibanInfo.sepa_eligible ? ` · ${t('deposit.field.iban.sepa_ok')}` : ''}</span>
            )}
            {ibanInfo && !ibanInfo.ok && (
              <span className="text-rose-700 dark:text-rose-300">✗ {t('deposit.field.iban.bad')} — {ibanInfo.error || ''}</span>
            )}
          </div>
        </div>
        {method === 'swift' && (
          <>
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">{t('deposit.field.bic')}</label>
              <input
                type="text"
                value={bic}
                onChange={(e) => setBic(e.target.value.toUpperCase())}
                placeholder="BARCGB22XXX"
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono"
                data-testid="deposit-bic"
              />
              <div className="text-xs">
                {bicInfo?.ok && <span className="text-emerald-700 dark:text-emerald-300">✓ BIC OK</span>}
                {bicInfo && !bicInfo.ok && <span className="text-rose-700 dark:text-rose-300">✗ {bicInfo.error || 'BIC invalid'}</span>}
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">{t('deposit.field.charges')}</label>
              <LumenSelect
                value={charges}
                onValueChange={setCharges}
                options={[
                  { value: 'OUR', label: t('deposit.charges.OUR') },
                  { value: 'SHA', label: t('deposit.charges.SHA') },
                  { value: 'BEN', label: t('deposit.charges.BEN') },
                ]}
                testid="deposit-charges"
              />
            </div>
          </>
        )}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">{t('deposit.field.purpose')} <span className="text-muted-foreground">({t('common.optional')})</span></label>
          <input
            type="text"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
            data-testid="deposit-purpose"
          />
        </div>
      </section>

      {beneficiary && (
        <section className="p-4 rounded-xl bg-muted/30 border border-border">
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5" /> {t('beneficiary.title')}
          </div>
          <div className="text-sm font-medium">{beneficiary.beneficiary} · {beneficiary.bank_name}</div>
          <div className="text-xs text-muted-foreground mt-1 font-mono">{formatIban(beneficiary.iban)} {beneficiary.swift_code && `· ${beneficiary.swift_code}`}</div>
        </section>
      )}

      {err && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200 border border-rose-200 dark:border-rose-900">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}

      <button
        type="button"
        disabled={!canSubmit || submitting}
        onClick={onSubmit}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-foreground text-background text-sm font-semibold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
        data-testid="deposit-submit-btn"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        {submitting ? t('deposit.btn.creating') : t('deposit.btn.create')}
      </button>
    </div>
  );
}

function Field({ label, value, t, mono }) {
  return (
    <div className="space-y-1">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`flex items-center justify-between gap-2 ${mono ? 'font-mono' : ''}`}>
        <span className="break-all">{value || '—'}</span>
        {value && <CopyButton value={value} t={t} />}
      </div>
    </div>
  );
}
