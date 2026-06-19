import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError, API } from '@/lib/lumenApi';
import { Download, FileSpreadsheet, FileCode2, FileText, Loader2, RefreshCw, Check } from 'lucide-react';

const FORMATS = [
  { value: 'csv',  label: 'CSV',  icon: <FileText className="w-4 h-4" /> },
  { value: 'xlsx', label: 'XLS',  icon: <FileSpreadsheet className="w-4 h-4" /> },
  { value: 'sepa', label: 'SEPA', icon: <FileCode2 className="w-4 h-4" /> },
  { value: 'swift',label: 'SWIFT MT103', icon: <FileText className="w-4 h-4" /> },
];

export default function AdminPayoutExport() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/payout-export/batches');
      setItems(r.data?.items || []);
    } catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const download = (batchId, fmt) => {
    window.open(`${API}/admin/payout-export/${batchId}/${fmt}`, '_blank');
  };

  const markExported = async (batchId) => {
    setBusy(batchId);
    try {
      await lumen.post(`/admin/payout-export/${batchId}/mark`);
      await load();
    } catch (e) { setError(lumenError(e)); }
    finally { setBusy(''); }
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-payout-export">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 11 · Banking</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Експорт виплат</h1>
          <p className="mt-1 text-token-muted text-sm">Формування файлів для фінвідділу: CSV / XLS / SEPA pain.001 / SWIFT MT103.</p>
        </div>
        <button onClick={load} className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2" data-testid="btn-refresh-export">
          <RefreshCw className="w-3.5 h-3.5" /> Оновити
        </button>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-24 rounded-xl bg-muted/40 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="export-empty">
          <Download className="w-10 h-10 mx-auto text-token-muted/60 mb-3" />
          <p className="font-semibold">Немає пакетів виплат для експорту</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map(b => (
            <div key={b.id} className="p-4 rounded-2xl border border-border bg-card" data-testid={`batch-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-sm font-semibold truncate">{b.id}</div>
                  <div className="text-xs text-token-muted mt-1">
                    Status: <span className="font-semibold">{b.status}</span> · Записів: {b.records} · {formatDateUk(b.created_at)}
                  </div>
                  {b.title && <div className="text-sm mt-1">{b.title}</div>}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {FORMATS.map(f => (
                    <button key={f.value} onClick={() => download(b.id, f.value)} className="px-3 py-1.5 text-xs rounded-md border border-border bg-app hover:bg-muted/50 flex items-center gap-1.5" data-testid={`btn-export-${b.id}-${f.value}`}>
                      {f.icon} {f.label}
                    </button>
                  ))}
                  <button onClick={() => markExported(b.id)} disabled={busy === b.id} className="px-3 py-1.5 text-xs rounded-md bg-primary text-primary-foreground disabled:opacity-50 flex items-center gap-1.5" data-testid={`btn-mark-${b.id}`}>
                    {busy === b.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                    Позначити експортованим
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
