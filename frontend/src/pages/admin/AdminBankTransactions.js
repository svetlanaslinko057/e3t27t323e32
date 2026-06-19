import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError, API } from '@/lib/lumenApi';
import {
  Landmark, Loader2, RefreshCw, AlertCircle, CheckCircle2, XCircle,
  Upload, Plus, Link2, Ban, Search,
} from 'lucide-react';

const STATUS_LABELS = {
  unmatched:  'Не зіставлено',
  matched:    'Співставлено',
  reconciled: 'Проведено',
  rejected:   'Відхилено',
};

const statusBadge = (s) => {
  const map = {
    unmatched:  { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.30)', text: 'rgb(180,83,9)' },
    matched:    { bg: 'rgba(59,130,246,0.10)', border: 'rgba(59,130,246,0.30)', text: 'rgb(29,78,216)' },
    reconciled: { bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.30)', text: 'rgb(5,150,105)' },
    rejected:   { bg: 'rgba(239,68,68,0.10)', border: 'rgba(239,68,68,0.30)', text: 'rgb(185,28,28)' },
  };
  return map[s] || map.unmatched;
};

export default function AdminBankTransactions() {
  const [data, setData] = useState({ items: [], counts: {} });
  const [filter, setFilter] = useState('');
  const [providerFilter, setProviderFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [importing, setImporting] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualForm, setManualForm] = useState({
    provider: 'manual', amount: '', currency: 'UAH',
    payer_name: '', payer_email: '', payer_iban: '',
    purpose: '', reference: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter) params.set('status', filter);
      if (providerFilter) params.set('provider', providerFilter);
      const r = await lumen.get('/admin/bank-transactions' + (params.toString() ? `?${params}` : ''));
      setData(r.data || { items: [], counts: {} });
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити')); }
    finally { setLoading(false); }
  }, [filter, providerFilter]);

  useEffect(() => { load(); }, [load]);

  const reject = async (id) => {
    const reason = window.prompt('Причина відхилення:');
    if (!reason) return;
    setBusy(id);
    try {
      await lumen.post(`/admin/bank-transactions/${id}/reject`, { reason });
      await load();
    } catch (e) { setError(lumenError(e)); }
    finally { setBusy(''); }
  };

  const rematch = async (id) => {
    setBusy(id);
    try {
      await lumen.post(`/admin/bank-transactions/${id}/rematch`);
      await load();
    } catch (e) { setError(lumenError(e)); }
    finally { setBusy(''); }
  };

  const manualMatch = async (id) => {
    const prId = window.prompt('Payment Request ID:');
    if (!prId) return;
    setBusy(id);
    try {
      await lumen.post(`/admin/bank-transactions/${id}/match/${prId}`);
      await load();
    } catch (e) { setError(lumenError(e)); }
    finally { setBusy(''); }
  };

  const submitManual = async (e) => {
    e.preventDefault();
    setBusy('manual');
    try {
      const payload = { ...manualForm, amount: parseFloat(manualForm.amount) };
      await lumen.post('/admin/banking/manual', payload);
      setManualOpen(false);
      setManualForm({ provider: 'manual', amount: '', currency: 'UAH', payer_name: '', payer_email: '', payer_iban: '', purpose: '', reference: '' });
      await load();
    } catch (err) { setError(lumenError(err)); }
    finally { setBusy(''); }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await lumen.post('/admin/banking/import', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      alert(`Імпортовано: ${r.data.ingested}, пропущено: ${r.data.skipped}`);
      await load();
    } catch (err) { setError(lumenError(err)); }
    finally { setImporting(false); e.target.value = ''; }
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-bank-transactions">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 11 · Banking</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Банківські транзакції</h1>
          <p className="mt-1 text-token-muted text-sm">Автоматичне та ручне зіставлення банківських надходжень з payment_request → ledger.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => setManualOpen(v => !v)} className="px-3 py-1.5 rounded-full text-sm bg-primary text-primary-foreground hover:opacity-90 flex items-center gap-2" data-testid="btn-manual-tx">
            <Plus className="w-3.5 h-3.5" /> Ручний запис
          </button>
          <label className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2 cursor-pointer">
            {importing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            CSV імпорт
            <input type="file" accept=".csv,.txt" onChange={onUpload} className="hidden" data-testid="input-csv-import" />
          </label>
          <button onClick={load} className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2" data-testid="btn-refresh-bank-tx">
            <RefreshCw className="w-3.5 h-3.5" /> Оновити
          </button>
        </div>
      </header>

      {manualOpen && (
        <form onSubmit={submitManual} className="mb-4 p-4 rounded-2xl border border-border bg-card grid md:grid-cols-3 gap-3" data-testid="manual-tx-form">
          <select value={manualForm.provider} onChange={e => setManualForm(s => ({...s, provider: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm">
            <option value="manual">manual</option>
            <option value="swift">swift</option>
            <option value="monobank">monobank</option>
            <option value="liqpay">liqpay</option>
          </select>
          <input required type="number" step="0.01" placeholder="Amount" value={manualForm.amount} onChange={e => setManualForm(s => ({...s, amount: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm" />
          <select value={manualForm.currency} onChange={e => setManualForm(s => ({...s, currency: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm">
            <option>UAH</option><option>USD</option><option>EUR</option>
          </select>
          <input placeholder="Payer name" value={manualForm.payer_name} onChange={e => setManualForm(s => ({...s, payer_name: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm" />
          <input placeholder="Payer email" value={manualForm.payer_email} onChange={e => setManualForm(s => ({...s, payer_email: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm" />
          <input placeholder="Payer IBAN" value={manualForm.payer_iban} onChange={e => setManualForm(s => ({...s, payer_iban: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm" />
          <input placeholder="Purpose" value={manualForm.purpose} onChange={e => setManualForm(s => ({...s, purpose: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm md:col-span-2" />
          <input placeholder="Reference (LUMEN-PR-...)" value={manualForm.reference} onChange={e => setManualForm(s => ({...s, reference: e.target.value}))} className="px-2 py-1.5 rounded-md border border-border bg-app text-sm" />
          <div className="md:col-span-3 flex justify-end gap-2">
            <button type="button" onClick={() => setManualOpen(false)} className="px-3 py-1.5 rounded-md text-sm bg-muted hover:bg-muted/70">Скасувати</button>
            <button type="submit" disabled={busy==='manual'} className="px-3 py-1.5 rounded-md text-sm bg-primary text-primary-foreground disabled:opacity-50">{busy==='manual'?'Створюємо...':'Створити'}</button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        {Object.entries(STATUS_LABELS).map(([k, v]) => {
          const c = statusBadge(k);
          return (
            <button key={k} onClick={() => setFilter(filter === k ? '' : k)} className="rounded-xl border bg-card p-3 text-left hover:bg-muted/30"
              style={{ borderColor: filter === k ? c.text : 'var(--token-border)' }} data-testid={`filter-${k}`}>
              <div className="text-[11px] uppercase tracking-wider text-token-muted">{v}</div>
              <div className="text-xl font-bold mt-1" style={{ color: c.text }}>{data.counts?.[k] ?? 0}</div>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2 mb-4 text-sm">
        <Search className="w-4 h-4 text-token-muted" />
        <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} className="px-2 py-1 rounded-md border border-border bg-app" data-testid="filter-provider">
          <option value="">Всі провайдери</option>
          <option value="monobank">Monobank</option>
          <option value="liqpay">LiqPay</option>
          <option value="swift">SWIFT</option>
          <option value="manual">Manual</option>
        </select>
      </div>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />)}</div>
      ) : data.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="bank-tx-empty">
          <Landmark className="w-10 h-10 mx-auto text-token-muted/60 mb-3" />
          <p className="font-semibold">Банківських транзакцій немає</p>
          <p className="text-token-muted text-sm mt-1">Після підключення Monobank/LiqPay вебхуків дані будуть приходити сюди автоматично.</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="bank-tx-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2">Час</th>
                <th className="text-left px-3 py-2">Провайдер</th>
                <th className="text-left px-3 py-2">Платник</th>
                <th className="text-right px-3 py-2">Сума</th>
                <th className="text-left px-3 py-2">Ref</th>
                <th className="text-left px-3 py-2">Статус</th>
                <th className="text-right px-3 py-2">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {data.items.map((r) => {
                const c = statusBadge(r.status);
                return (
                  <tr key={r.id} className="hover:bg-muted/20" data-testid={`bank-tx-${r.id}`}>
                    <td className="px-3 py-2 text-token-muted text-[12px] whitespace-nowrap">{formatDateUk(r.created_at)}</td>
                    <td className="px-3 py-2 font-mono text-[12px]">{r.provider}</td>
                    <td className="px-3 py-2 text-[12px]">
                      <div className="font-medium truncate max-w-[180px]">{r.payer_name || r.payer_email || '—'}</div>
                      <div className="text-token-muted text-[10px] truncate max-w-[180px]">{r.payer_iban || r.purpose || ''}</div>
                    </td>
                    <td className="px-3 py-2 text-right font-semibold whitespace-nowrap">{formatUAH(r.amount_uah)}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{r.reference || '—'}</td>
                    <td className="px-3 py-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold" style={{ background: c.bg, color: c.text, border: `1px solid ${c.border}` }}>
                        {STATUS_LABELS[r.status]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {r.status === 'unmatched' && (
                          <>
                            <button onClick={() => rematch(r.id)} disabled={busy === r.id} className="p-1.5 rounded hover:bg-blue-50" title="Повторити auto-match" data-testid={`btn-rematch-${r.id}`}>
                              {busy === r.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 text-blue-600" />}
                            </button>
                            <button onClick={() => manualMatch(r.id)} disabled={busy === r.id} className="p-1.5 rounded hover:bg-emerald-50" title="Ручне зіставлення" data-testid={`btn-match-${r.id}`}>
                              <Link2 className="w-3.5 h-3.5 text-emerald-600" />
                            </button>
                            <button onClick={() => reject(r.id)} disabled={busy === r.id} className="p-1.5 rounded hover:bg-red-50" title="Відхилити" data-testid={`btn-reject-${r.id}`}>
                              <Ban className="w-3.5 h-3.5 text-red-600" />
                            </button>
                          </>
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
    </div>
  );
}
