/**
 * Admin Queue: list of pending/submitted/pending_review/matched transfers.
 * Action buttons: Reconcile (opens modal), Match, Confirm, Reject.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw, CheckCircle2, X, Eye, Filter, Send } from 'lucide-react';
import { StatusPill, formatAmount, formatDateTime, methodLabelFromTransfer } from '@/pages/funding/_shared';
import ReconcileDialog from './ReconcileDialog';

function canonicalOf(t) {
  return t.canonical_status
    || ({ pending: 'submitted', initiated: 'pending_review', sent: 'pending_review',
          failed: 'rejected', returned: 'rejected', cancelled: 'rejected',
          confirmed: 'confirmed', draft: 'draft' }[t.status] || 'submitted');
}

export default function QueueSection({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [filter, setFilter] = useState('open');   // open | all
  const [reconcileFor, setReconcileFor] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/lumen/institutional/rails/transfers?limit=300');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load queue')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const showItems = items.filter((x) => {
    if (filter === 'all') return true;
    const cs = canonicalOf(x);
    return cs === 'submitted' || cs === 'pending_review' || cs === 'matched';
  });

  const doAction = async (id, action, body = {}) => {
    setBusyId(id);
    try {
      await lumen.post(`/admin/lumen/institutional/rails/transfers/${id}/${action}`, body);
      await load();
    } catch (e) {
      alert(lumenError(e, `${action} failed`));
    } finally { setBusyId(null); }
  };

  return (
    <div className="space-y-4" data-testid="admin-queue-section">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="inline-flex items-center gap-1.5 p-1 rounded-lg border border-border bg-card text-xs">
          <span className="px-2 text-muted-foreground flex items-center gap-1"><Filter className="w-3 h-3" /></span>
          {['open', 'all'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-md font-medium ${filter === f ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'}`}
              data-testid={`queue-filter-${f}`}
            >{f === 'open' ? 'Open' : 'All'}</button>
          ))}
        </div>
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="queue-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && showItems.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('admin.queue.empty')}
        </div>
      )}

      {showItems.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('transfers.col.method')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.amount')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.reference')}</th>
                <th className="px-4 py-2.5">{t('admin.queue.col.investor')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.status')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.created')}</th>
                <th className="px-4 py-2.5 text-right">{t('transfers.col.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {showItems.map((x) => {
                const cs = canonicalOf(x);
                const recon = x.reconciliation || null;
                return (
                  <tr key={x.id} className="border-t border-border" data-testid={`admin-queue-row-${x.id}`}>
                    <td className="px-4 py-3 font-medium">{methodLabelFromTransfer(x.rail)}</td>
                    <td className="px-4 py-3 font-mono">{formatAmount(x.amount, x.currency)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{x.reference}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{x.investor_id}</td>
                    <td className="px-4 py-3"><StatusPill status={cs} t={t} /></td>
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatDateTime(x.created_at)}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => setReconcileFor(x)}
                          disabled={busyId === x.id}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs hover:bg-muted disabled:opacity-50"
                          data-testid={`admin-action-reconcile-${x.id}`}
                        >
                          <Eye className="w-3.5 h-3.5" /> {t('admin.queue.action.reconcile')}
                        </button>
                        {recon?.matched && cs === 'pending_review' && (
                          <button
                            onClick={() => doAction(x.id, 'match', { note: 'Marked via Funding Ops' })}
                            disabled={busyId === x.id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-indigo-50 dark:bg-indigo-950/40 text-indigo-800 dark:text-indigo-200 hover:opacity-80 disabled:opacity-50"
                            data-testid={`admin-action-match-${x.id}`}
                          >
                            {t('admin.queue.action.match')}
                          </button>
                        )}
                        {(cs === 'matched' || cs === 'pending_review' || cs === 'submitted') && (
                          <button
                            onClick={() => doAction(x.id, 'confirm', { note: 'Confirmed via Funding Ops' })}
                            disabled={busyId === x.id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200 hover:opacity-80 disabled:opacity-50"
                            data-testid={`admin-action-confirm-${x.id}`}
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" /> {t('admin.queue.action.confirm')}
                          </button>
                        )}
                        {cs !== 'confirmed' && cs !== 'rejected' && (
                          <button
                            onClick={() => {
                              const reason = window.prompt(t('admin.reject.field.reason'));
                              if (!reason) return;
                              doAction(x.id, 'reject', { reason });
                            }}
                            disabled={busyId === x.id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/40 disabled:opacity-50"
                            data-testid={`admin-action-reject-${x.id}`}
                          >
                            <X className="w-3.5 h-3.5" /> {t('admin.queue.action.reject')}
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

      {reconcileFor && (
        <ReconcileDialog
          transfer={reconcileFor}
          t={t}
          onClose={() => setReconcileFor(null)}
          onDone={() => { setReconcileFor(null); load(); }}
        />
      )}
    </div>
  );
}
