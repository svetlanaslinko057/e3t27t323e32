/**
 * Active transfers tab: list non-terminal transfers with detail panel.
 */
import { useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw, X, Eye, Trash2, FileUp } from 'lucide-react';
import { StatusPill, formatAmount, formatDateTime, methodLabelFromTransfer, useMyTransfers, CANONICAL_STATUSES } from './_shared';
import ProofUploader from './ProofUploader';

function canonicalOf(t) {
  return t.canonical_status
    || ({ pending: 'submitted', initiated: 'pending_review', sent: 'pending_review',
          failed: 'rejected', returned: 'rejected', cancelled: 'rejected',
          confirmed: 'confirmed', draft: 'draft' }[t.status] || 'submitted');
}

export default function TransfersTab({ t }) {
  const { items, loading, err, reload } = useMyTransfers();
  const [detail, setDetail] = useState(null);

  const active = (items || []).filter((x) => {
    const cs = canonicalOf(x);
    return cs !== 'confirmed' && cs !== 'rejected';
  });

  const cancel = useCallback(async (id) => {
    if (!window.confirm(t('transfers.cancel.confirm'))) return;
    try {
      await lumen.post(`/lumen/institutional/rails/transfers/${id}/cancel`);
      reload();
      setDetail(null);
    } catch (e) {
      alert(lumenError(e, 'Cancel failed'));
    }
  }, [reload, t]);

  return (
    <div className="space-y-4" data-testid="transfers-tab">
      <div className="flex items-center justify-between">
        <header>
          <h2 className="text-2xl font-bold tracking-tight">{t('transfers.title')}</h2>
        </header>
        <button onClick={reload} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="transfers-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>
      )}
      {err && (
        <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200 border border-rose-200 dark:border-rose-900">{err}</div>
      )}

      {!loading && active.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('transfers.empty')}
        </div>
      )}

      {active.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('transfers.col.method')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.amount')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.reference')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.status')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.created')}</th>
                <th className="px-4 py-2.5 text-right">{t('transfers.col.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {active.map((x) => {
                const cs = canonicalOf(x);
                return (
                  <tr key={x.id} className="border-t border-border" data-testid={`transfer-row-${x.id}`}>
                    <td className="px-4 py-3 font-medium">{methodLabelFromTransfer(x.rail)}</td>
                    <td className="px-4 py-3 font-mono">{formatAmount(x.amount, x.currency)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{x.reference}</td>
                    <td className="px-4 py-3"><StatusPill status={cs} t={t} /></td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateTime(x.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => setDetail(x)}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs hover:bg-muted"
                          data-testid={`transfer-detail-${x.id}`}
                        >
                          <Eye className="w-3.5 h-3.5" /> {t('transfers.action.detail')}
                        </button>
                        {['submitted', 'draft'].includes(cs) && (
                          <button
                            onClick={() => cancel(x.id)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                            data-testid={`transfer-cancel-${x.id}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" /> {t('transfers.action.cancel')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <DetailDrawer transfer={detail} t={t} onClose={() => setDetail(null)} onChanged={reload} />
      )}
    </div>
  );
}

function DetailDrawer({ transfer, t, onClose, onChanged }) {
  const cs = canonicalOf(transfer);
  const [proofs, setProofs] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const loadProofs = useCallback(async () => {
    try {
      const r = await lumen.get(`/lumen/institutional/rails/transfers/${transfer.id}/proofs`);
      setProofs(r.data?.items || []);
      setLoaded(true);
    } catch (_e) { setLoaded(true); }
  }, [transfer.id]);

  // Load proofs on open
  useState(() => { loadProofs(); });
  // Re-load on uploaded
  const onUploaded = useCallback(() => { loadProofs(); if (onChanged) onChanged(); }, [loadProofs, onChanged]);

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/40" onClick={onClose} data-testid="transfer-detail-drawer">
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-xl bg-background border-l border-border overflow-y-auto p-6 space-y-5">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">{methodLabelFromTransfer(transfer.rail)} · {transfer.direction}</div>
            <h3 className="text-2xl font-bold tracking-tight mt-1">{formatAmount(transfer.amount, transfer.currency)}</h3>
            <div className="mt-2"><StatusPill status={cs} t={t} /></div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted" data-testid="transfer-detail-close"><X className="w-4 h-4" /></button>
        </div>

        <div className="space-y-2 text-sm">
          <div className="flex justify-between gap-2"><span className="text-muted-foreground">Reference</span><span className="font-mono">{transfer.reference}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted-foreground">IBAN</span><span className="font-mono text-xs">{transfer.beneficiary_iban}</span></div>
          {transfer.beneficiary_bic && <div className="flex justify-between gap-2"><span className="text-muted-foreground">BIC</span><span className="font-mono">{transfer.beneficiary_bic}</span></div>}
          <div className="flex justify-between gap-2"><span className="text-muted-foreground">{t('beneficiary.field.beneficiary')}</span><span>{transfer.beneficiary_name}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted-foreground">{t('common.date')}</span><span>{formatDateTime(transfer.created_at)}</span></div>
        </div>

        {['submitted', 'pending_review', 'matched'].includes(cs) && (
          <div className="p-4 rounded-xl border border-border bg-muted/30 space-y-3">
            <div className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-2"><FileUp className="w-3.5 h-3.5" /> {t('deposit.upload_proof')}</div>
            <ProofUploader transferId={transfer.id} t={t} onUploaded={onUploaded} />
          </div>
        )}

        {loaded && proofs.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">{t('documents.title')}</div>
            <ul className="space-y-2">
              {proofs.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-card border border-border">
                  <div className="text-sm font-medium truncate">{p.filename_original}</div>
                  <a
                    href={`${(process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '')}${p.url_internal}`}
                    target="_blank" rel="noopener noreferrer"
                    className="text-xs px-2 py-1 rounded-md border border-border hover:bg-muted"
                    data-testid={`proof-download-${p.id}`}
                  >
                    {t('common.download')}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export { canonicalOf };
export { CANONICAL_STATUSES };
