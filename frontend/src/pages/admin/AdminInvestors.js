import { useEffect, useState } from 'react';
import { lumen, formatDateUk } from '@/lib/lumenApi';
import { Search, ShieldCheck } from 'lucide-react';

export default function AdminInvestors() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');

  useEffect(() => {
    lumen.get('/admin/investors')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = items.filter((u) => !q || u.name?.toLowerCase().includes(q.toLowerCase()) || u.email?.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="p-6 md:p-10 max-w-6xl mx-auto" data-testid="admin-investors">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Інвестори</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">База інвесторів</h1>
        <p className="mt-1 text-token-muted">Усі зареєстровані учасники платформи та їхній KYC-статус.</p>
      </header>

      <div className="relative mb-6">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-token-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Пошук за іменем або email…" className="w-full pl-9 pr-4 h-11 rounded-xl focus:outline-none" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }} data-testid="investors-search" />
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3, 4].map((i) => <div key={i} className="h-14 rounded-xl animate-pulse" style={{ background: 'var(--token-surface-elevated)' }} />)}</div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl p-10 text-center" style={{ border: '1px solid var(--token-border)' }}><p className="font-semibold">Нічого не знайдено</p></div>
      ) : (
        <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted" style={{ background: 'var(--token-surface-elevated)' }}>
              <tr>
                <th className="text-left px-5 py-3 font-medium">Ім'я</th>
                <th className="text-left px-5 py-3 font-medium">Email</th>
                <th className="text-left px-5 py-3 font-medium">KYC</th>
                <th className="text-left px-5 py-3 font-medium">Роль</th>
                <th className="text-right px-5 py-3 font-medium">Реєстрація</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} style={{ borderTop: '1px solid var(--token-border)' }}>
                  <td className="px-5 py-3 font-medium">{u.name || '—'}</td>
                  <td className="px-5 py-3 text-token-muted">{u.email}</td>
                  <td className="px-5 py-3">
                    <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--token-surface-elevated)' }}>
                      <ShieldCheck className="w-3 h-3" /> {u.kyc_status || 'not_started'}
                    </span>
                  </td>
                  <td className="px-5 py-3 capitalize text-token-muted">{u.role}</td>
                  <td className="px-5 py-3 text-right text-token-muted">{formatDateUk(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
