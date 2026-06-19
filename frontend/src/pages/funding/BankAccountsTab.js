/**
 * Bank Accounts tab: read-only beneficiary cards for Lumen.
 */
import { Loader2, Building2, Star } from 'lucide-react';
import { CopyButton, formatIban, useBankAccounts } from './_shared';

export default function BankAccountsTab({ t }) {
  const { accounts, loading, err } = useBankAccounts();

  return (
    <div className="space-y-4" data-testid="bank-accounts-tab">
      <header>
        <h2 className="text-2xl font-bold tracking-tight">{t('beneficiary.title')}</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{t('beneficiary.subtitle')}</p>
      </header>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {accounts.filter((a) => a.iban).map((a) => (
          <article key={a.id} className="p-5 rounded-xl border border-border bg-card space-y-3" data-testid={`bank-account-card-${a.id}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-muted-foreground" />
                <div>
                  <h3 className="font-semibold">{a.label}</h3>
                  <div className="text-xs text-muted-foreground">{a.bank_name}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {a.default && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200">
                    <Star className="w-3 h-3" /> {t('beneficiary.default')}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-muted text-muted-foreground">{a.currency}</span>
              </div>
            </div>
            <dl className="space-y-2 text-sm">
              <Row label={t('beneficiary.field.beneficiary')} value={a.beneficiary} t={t} />
              <Row label={t('beneficiary.field.iban')} value={formatIban(a.iban)} t={t} mono />
              {a.swift_code && <Row label={t('beneficiary.field.bic')} value={a.swift_code} t={t} mono />}
              {a.edrpou && <Row label={t('beneficiary.field.edrpou')} value={a.edrpou} t={t} mono />}
              {a.purpose_template && <Row label={t('beneficiary.field.purpose_template')} value={a.purpose_template} t={t} />}
            </dl>
            {a.notes && (
              <p className="text-xs text-muted-foreground pt-2 border-t border-border">{a.notes}</p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value, t, mono }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-xs uppercase tracking-wider text-muted-foreground pt-0.5">{label}</dt>
      <dd className={`flex items-center gap-2 text-right ${mono ? 'font-mono' : ''} flex-1 justify-end break-all`}>
        <span>{value}</span>
        <CopyButton value={value} t={t} />
      </dd>
    </div>
  );
}
