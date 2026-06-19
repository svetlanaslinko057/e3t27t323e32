import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError, API } from '@/lib/lumenApi';
import { Loader2, FileSearch, Download, Filter, RefreshCw } from 'lucide-react';

const CATEGORY_LABELS = {
  kyc: 'KYC', contract: 'Договори', payment: 'Платежі', payout: 'Виплати',
  withdrawal: 'Виводи', asset: 'Активи', spv: 'SPV', auth: 'Авторизація',
  system: 'Система',
};

export default function AdminAuditLog() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('');
  const [actorId, setActorId] = useState('');
  const [sinceHours, setSinceHours] = useState(168); // 7 days
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [logRes, catRes] = await Promise.all([
        lumen.get('/admin/audit/log', {
          params: {
            category: category || undefined,
            actor_id: actorId || undefined,
            since_hours: sinceHours || undefined,
            limit: 200,
          },
        }),
        lumen.get('/admin/audit/categories'),
      ]);
      setItems(logRes.data?.items || []);
      setTotal(logRes.data?.total || 0);
      setCategories(catRes.data?.categories || []);
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити журнал')); }
    finally { setLoading(false); }
  }, [category, actorId, sinceHours]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (sinceHours) params.set('since_hours', String(sinceHours));
    window.open(`${API}/admin/audit/export.csv?${params}`, '_blank');
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-audit-log">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 10 · Audit Trail</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Журнал аудиту</h1>
          <p className="mt-1 text-token-muted text-sm">
            Незмінний журнал чутливих операцій: KYC, договори, платежі, виплати, виводи, активи. Усього: {total}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2" data-testid="btn-refresh-audit">
            <RefreshCw className="w-3.5 h-3.5" /> Оновити
          </button>
          <button onClick={exportCsv} className="px-3 py-1.5 rounded-full text-sm bg-primary text-primary-foreground hover:opacity-90 flex items-center gap-2" data-testid="btn-export-audit-csv">
            <Download className="w-3.5 h-3.5" /> Експорт CSV
          </button>
        </div>
      </header>

      {/* Category quick stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 mb-4">
        {categories.map(c => (
          <button
            key={c.category}
            onClick={() => setCategory(category === c.category ? '' : c.category)}
            className="rounded-xl border bg-card p-3 text-left hover:bg-muted/30"
            style={{ borderColor: category === c.category ? 'var(--token-primary)' : 'var(--token-border)' }}
            data-testid={`audit-cat-${c.category}`}
          >
            <div className="text-[11px] uppercase tracking-wider text-token-muted">{CATEGORY_LABELS[c.category] || c.category}</div>
            <div className="text-xl font-bold mt-1">{c.count}</div>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 mb-4 p-3 rounded-xl bg-card border border-border">
        <Filter className="w-4 h-4 text-token-muted" />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="text-sm px-2 py-1 rounded-md border border-border bg-app" data-testid="audit-filter-category">
          <option value="">Всі категорії</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={sinceHours} onChange={(e) => setSinceHours(Number(e.target.value))} className="text-sm px-2 py-1 rounded-md border border-border bg-app" data-testid="audit-filter-window">
          <option value={1}>1 година</option>
          <option value={24}>24 години</option>
          <option value={168}>7 днів</option>
          <option value={720}>30 днів</option>
          <option value={0}>Весь час</option>
        </select>
        <input
          placeholder="actor_id"
          value={actorId}
          onChange={(e) => setActorId(e.target.value)}
          className="text-sm px-2 py-1 rounded-md border border-border bg-app w-44"
          data-testid="audit-filter-actor"
        />
        {(category || actorId || sinceHours !== 168) && (
          <button onClick={() => { setCategory(''); setActorId(''); setSinceHours(168); }} className="text-xs text-token-muted underline">
            Скинути
          </button>
        )}
      </div>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="space-y-2">{[1,2,3,4].map(i => <div key={i} className="h-16 rounded-xl bg-muted/40 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="audit-empty">
          <FileSearch className="w-10 h-10 mx-auto text-token-muted/60 mb-3" />
          <p className="font-semibold">Подій за фільтром не знайдено</p>
          <p className="text-token-muted text-sm mt-1">Журнал заповнюватиметься у міру виконання чутливих операцій.</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="audit-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Час</th>
                <th className="text-left px-3 py-2 font-medium">Категорія</th>
                <th className="text-left px-3 py-2 font-medium">Дія</th>
                <th className="text-left px-3 py-2 font-medium">Actor</th>
                <th className="text-left px-3 py-2 font-medium">Target</th>
                <th className="text-left px-3 py-2 font-medium">Опис</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {items.map((r) => (
                <tr key={r.id} className="hover:bg-muted/30" data-testid={`audit-row-${r.id}`}>
                  <td className="px-3 py-2 text-token-muted whitespace-nowrap text-[12px]">{formatDateUk(r.at)}</td>
                  <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted">{r.category}</span></td>
                  <td className="px-3 py-2 font-mono text-[12px]">{r.action}</td>
                  <td className="px-3 py-2 text-[12px]">
                    <div className="font-medium truncate max-w-[180px]">{r.actor_email || r.actor_id || '—'}</div>
                    <div className="text-token-muted text-[10px]">{r.actor_role}</div>
                  </td>
                  <td className="px-3 py-2 text-[12px]">
                    <div className="text-token-muted truncate max-w-[180px]">{r.target_type}</div>
                    <div className="font-mono text-[10px] truncate max-w-[180px]">{r.target_id || '—'}</div>
                  </td>
                  <td className="px-3 py-2 text-[12px] max-w-[420px]">
                    <div className="truncate">{r.summary || '—'}</div>
                    {r.meta && Object.keys(r.meta).length > 0 && (
                      <details className="text-token-muted">
                        <summary className="text-[10px] cursor-pointer">meta</summary>
                        <pre className="text-[10px] mt-1 p-1 bg-muted/40 rounded overflow-x-auto">{JSON.stringify(r.meta, null, 1)}</pre>
                      </details>
                    )}
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
