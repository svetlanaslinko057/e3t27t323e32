/**
 * Ledger view: read-only list of money_ledger entries that originated from
 * institutional rails (source = lumen_institutional_rails).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, RefreshCw, BookOpen } from 'lucide-react';
import { formatAmount, formatDateTime } from '@/pages/funding/_shared';

export default function LedgerSection({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/lumen/institutional/rails/ledger?limit=300');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load ledger')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="admin-ledger-section">
      <div className="flex items-center justify-end">
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="ledger-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && items.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('admin.ledger.empty')}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('admin.ledger.col.posted')}</th>
                <th className="px-4 py-2.5">{t('admin.ledger.col.kind')}</th>
                <th className="px-4 py-2.5">{t('admin.ledger.col.reference')}</th>
                <th className="px-4 py-2.5">{t('admin.ledger.col.transfer')}</th>
                <th className="px-4 py-2.5 text-right">{t('common.amount')}</th>
                <th className="px-4 py-2.5">{t('common.currency')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-t border-border" data-testid={`ledger-row-${e.id}`}>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{formatDateTime(e.posted_at)}</td>
                  <td className="px-4 py-3 inline-flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="font-medium">{e.kind || 'rail'}</span>
                    <span className="text-xs text-muted-foreground">{e.rail} · {e.direction}</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{e.reference}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{e.transfer_id}</td>
                  <td className="px-4 py-3 font-mono text-right">{formatAmount(e.amount)}</td>
                  <td className="px-4 py-3">{e.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
