import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { FileText } from 'lucide-react';

export default function AdminDocuments() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/admin/documents')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="admin-documents">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Документи</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Юридичні документи</h1>
        <p className="mt-1 text-token-muted">Договори, акти, звітність по об'єктах та раундах.</p>
      </header>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl animate-pulse" style={{ background: 'var(--token-surface-elevated)' }} />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl p-10 text-center" style={{ border: '1px solid var(--token-border)' }}><p className="font-semibold">Документів немає</p></div>
      ) : (
        <ul className="rounded-2xl overflow-hidden divide-y" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)', borderColor: 'var(--token-border)' }}>
          {items.map((d) => (
            <li key={d.id} className="px-5 py-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'var(--token-surface-elevated)' }}><FileText className="w-5 h-5" /></div>
              <div className="flex-1 min-w-0">
                <p className="font-medium">{d.title}</p>
                <p className="text-xs text-token-muted">{d.investor_name || d.investor_email} · {d.asset_title} · {formatDateUk(d.created_at)}</p>
              </div>
              {d.url && <a href={d.url} target="_blank" rel="noreferrer" className="text-sm text-[#2E5D4F] hover:underline">Відкрити</a>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
