/**
 * Exceptions: transfers flagged by backend (currency/amount mismatch,
 * missing reference, rejected, reconciliation without match).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw, AlertTriangle } from 'lucide-react';
import { StatusPill, formatAmount, formatDateTime } from '@/pages/funding/_shared';

export default function ExceptionsSection({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/lumen/institutional/rails/exceptions?limit=200');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load exceptions')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="admin-exceptions-section">
      <div className="flex items-center justify-end">
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="exceptions-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && items.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-emerald-50 dark:bg-emerald-950/40 text-center text-sm text-emerald-800 dark:text-emerald-200">
          {t('admin.exceptions.empty')}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('transfers.col.reference')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.method')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.amount')}</th>
                <th className="px-4 py-2.5">{t('admin.exceptions.col.flags')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.status')}</th>
                <th className="px-4 py-2.5">{t('transfers.col.created')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.transfer_id} className="border-t border-border" data-testid={`exception-row-${x.transfer_id}`}>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{x.reference}</td>
                  <td className="px-4 py-3 font-medium">{String(x.rail || '').toUpperCase()}</td>
                  <td className="px-4 py-3 font-mono">{formatAmount(x.amount, x.currency)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(x.flags || []).map((f) => (
                        <span key={f} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200">
                          <AlertTriangle className="w-2.5 h-2.5" />
                          {t(`admin.flag.${f}`, null) || f}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3"><StatusPill status={x.canonical_status} t={t} /></td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatDateTime(x.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
