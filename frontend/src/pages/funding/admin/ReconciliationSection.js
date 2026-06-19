/**
 * Reconciliation overview: list of transfers that have a reconciliation block,
 * with matched / delta / currency_mismatch indicators.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw } from 'lucide-react';
import { StatusPill, formatAmount, formatDateTime, methodLabelFromTransfer } from '@/pages/funding/_shared';

function canonicalOf(t) {
  return t.canonical_status || 'submitted';
}

export default function ReconciliationSection({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/lumen/institutional/rails/transfers?limit=500');
      setItems((r.data?.items || []).filter((x) => x.reconciliation));
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="admin-reconciliation-section">
      <div className="flex items-center justify-end">
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="reconciliation-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && items.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('common.no_data')}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('transfers.col.method')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.reference')}</th>
                <th className="px-4 py-2.5">{t('admin.reconcile.field.bank_ref')}</th>
                <th className="px-4 py-2.5">{t('admin.reconcile.delta')}</th>
                <th className="px-4 py-2.5">Matched</th>
                <th className="px-4 py-2.5">{t('transfers.col.status')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((x) => {
                const r = x.reconciliation;
                return (
                  <tr key={x.id} className="border-t border-border" data-testid={`reconciliation-row-${x.id}`}>
                    <td className="px-4 py-3 font-medium">{methodLabelFromTransfer(x.rail)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{x.reference}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{r.bank_statement_ref}</td>
                    <td className="px-4 py-3 font-mono">{formatAmount(r.delta_amount, x.currency)}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.matched
                          ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200'
                          : 'bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200'
                      }`}>
                        {r.matched ? t('admin.reconcile.matched.ok') : t('admin.reconcile.matched.bad')}
                      </span>
                    </td>
                    <td className="px-4 py-3"><StatusPill status={canonicalOf(x)} t={t} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
