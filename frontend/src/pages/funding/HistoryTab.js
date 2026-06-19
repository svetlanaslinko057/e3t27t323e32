/**
 * History tab (R3): pure bank-statement view.
 * Columns EXACTLY: Date / Reference / Method / Amount / Currency / Status.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw } from 'lucide-react';
import { StatusPill, formatAmount, formatDateTime } from './_shared';

export default function HistoryTab({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/lumen/institutional/rails/history?limit=500');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load history')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="history-tab">
      <div className="flex items-center justify-between">
        <header>
          <h2 className="text-2xl font-bold tracking-tight">{t('history.title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('history.subtitle')}</p>
        </header>
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="history-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && items.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('history.empty')}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('history.col.date')}</th>
                <th className="px-4 py-2.5">{t('history.col.reference')}</th>
                <th className="px-4 py-2.5">{t('history.col.method')}</th>
                <th className="px-4 py-2.5 text-right">{t('history.col.amount')}</th>
                <th className="px-4 py-2.5">{t('history.col.currency')}</th>
                <th className="px-4 py-2.5">{t('history.col.status')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((x) => (
                <tr key={x._id_internal || x.reference} className="border-t border-border" data-testid={`history-row-${x.reference}`}>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatDateTime(x.date)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{x.reference}</td>
                  <td className="px-4 py-3 font-medium">{x.method}</td>
                  <td className="px-4 py-3 font-mono text-right">{formatAmount(x.amount)}</td>
                  <td className="px-4 py-3">{x.currency}</td>
                  <td className="px-4 py-3"><StatusPill status={x.status} t={t} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
