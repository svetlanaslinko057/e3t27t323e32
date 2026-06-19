/**
 * Documents tab: list of all proofs uploaded by the investor across transfers.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Loader2, FileText, RefreshCw, Download } from 'lucide-react';
import { formatBytes, formatDateTime } from './_shared';

export default function DocumentsTab({ t }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/lumen/institutional/rails/proofs?limit=200');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) { setErr(lumenError(e, 'Failed to load documents')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const base = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');

  return (
    <div className="space-y-4" data-testid="documents-tab">
      <div className="flex items-center justify-between">
        <header>
          <h2 className="text-2xl font-bold tracking-tight">{t('documents.title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('documents.subtitle')}</p>
        </header>
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="documents-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {loading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> {t('common.loading')}</div>}
      {err && <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 text-sm text-rose-800 dark:text-rose-200">{err}</div>}

      {!loading && items.length === 0 && (
        <div className="p-8 rounded-xl border border-border bg-muted/30 text-center text-sm text-muted-foreground">
          {t('documents.empty')}
        </div>
      )}

      {items.length > 0 && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40">
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">{t('documents.col.file')}</th>
                <th className="px-4 py-2.5">{t('documents.col.transfer')}</th>
                <th className="px-4 py-2.5">{t('documents.col.size')}</th>
                <th className="px-4 py-2.5">{t('documents.col.uploaded')}</th>
                <th className="px-4 py-2.5 text-right">{t('documents.col.download')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-t border-border" data-testid={`document-row-${p.id}`}>
                  <td className="px-4 py-3 font-medium flex items-center gap-2">
                    <FileText className="w-4 h-4 text-muted-foreground" /> {p.filename_original}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{p.transfer_id}</td>
                  <td className="px-4 py-3">{formatBytes(p.size_bytes)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(p.uploaded_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <a
                      href={`${base}${p.url_internal}`}
                      target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs hover:bg-muted"
                      data-testid={`document-download-${p.id}`}
                    >
                      <Download className="w-3.5 h-3.5" /> {t('common.download')}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
