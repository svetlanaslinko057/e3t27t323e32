import { useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk } from '@/lib/lumenApi';

export default function AdminRounds() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/admin/rounds')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="admin-rounds">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Раунди</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Інвестиційні раунди</h1>
        <p className="mt-1 text-token-muted">Відкриті, завершені та заплановані раунди по всіх активах.</p>
      </header>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-20 rounded-xl animate-pulse" style={{ background: 'var(--token-surface-elevated)' }} />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl p-10 text-center" style={{ border: '1px solid var(--token-border)' }}><p className="font-semibold">Раундів немає</p><p className="text-sm text-token-muted mt-1">Раунди створюються автоматично при виведенні активу в статус «Відкрито».</p></div>
      ) : (
        <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted" style={{ background: 'var(--token-surface-elevated)' }}>
              <tr>
                <th className="text-left px-5 py-3 font-medium">Актив</th>
                <th className="text-left px-5 py-3 font-medium">Статус</th>
                <th className="text-right px-5 py-3 font-medium">Зібрано</th>
                <th className="text-right px-5 py-3 font-medium">Ціль</th>
                <th className="text-right px-5 py-3 font-medium">Дедлайн</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} style={{ borderTop: '1px solid var(--token-border)' }}>
                  <td className="px-5 py-3 font-medium">{r.asset_title}</td>
                  <td className="px-5 py-3 capitalize text-token-muted">{r.status}</td>
                  <td className="px-5 py-3 text-right font-mono">{formatUAH(r.raised)}</td>
                  <td className="px-5 py-3 text-right font-mono">{formatUAH(r.target)}</td>
                  <td className="px-5 py-3 text-right text-token-muted">{formatDateUk(r.deadline)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
