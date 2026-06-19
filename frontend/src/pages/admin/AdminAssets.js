import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { Plus, Building2 } from 'lucide-react';

export default function AdminAssets() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    lumen.get('/admin/assets')
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-assets">
      <header className="mb-8 flex items-end justify-between gap-3 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Активи</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Каталог активів</h1>
          <p className="mt-1 text-token-muted">Об'єкти, виведені на платформу для колективної участі.</p>
        </div>
        <Link to="/admin/assets/new" className="inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-sm font-medium" style={{ background: 'var(--token-primary)', color: 'var(--token-on-primary)' }}>
          <Plus className="w-4 h-4" /> Новий актив
        </Link>
      </header>

      {loading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">{[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-72 rounded-2xl animate-pulse" style={{ background: 'var(--token-surface-elevated)' }} />)}</div>
      ) : items.length === 0 ? (
        <EmptyAssets />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {items.map((a) => (
            <Link key={a.id} to={`/admin/assets/${a.id}`} className="rounded-2xl overflow-hidden hover:shadow-lg transition flex flex-col" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }} data-testid={`admin-asset-${a.id}`}>
              <div className="aspect-[16/10]" style={a.cover_url ? { backgroundImage: `url(${a.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : { background: 'var(--token-surface-elevated)' }}>
                {!a.cover_url && <div className="w-full h-full flex items-center justify-center text-token-muted"><Building2 className="w-10 h-10" /></div>}
              </div>
              <div className="p-5 flex-1 flex flex-col">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] uppercase tracking-widest text-token-muted">{a.category_label || a.category}</span>
                  <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${a.status === 'open' ? 'bg-[#2E5D4F]/15 text-[#2E5D4F]' : ''}`} style={a.status !== 'open' ? { background: 'var(--token-surface-elevated)' } : undefined}>{a.status}</span>
                </div>
                <h3 className="font-semibold leading-snug">{a.title}</h3>
                <p className="text-xs text-token-muted mt-1">{a.location}</p>
                <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <div><p className="text-token-muted">Ціль</p><p className="font-mono">{formatUAH(a.round_target)}</p></div>
                  <div><p className="text-token-muted">Дохідність</p><p className="font-mono text-[#2E5D4F]">{formatPercent(a.target_yield)}</p></div>
                </div>
                <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--token-border)' }}>
                  <div className="h-full bg-[#2E5D4F]" style={{ width: `${a.progress_percent || 0}%` }} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const EmptyAssets = () => (
  <div className="rounded-2xl p-16 text-center" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
    <Building2 className="w-12 h-12 mx-auto text-token-muted" />
    <p className="mt-4 font-semibold">Ще немає жодного активу</p>
    <p className="mt-2 text-sm text-token-muted max-w-md mx-auto">Створіть перший актив — картку об'єкта з описом, фотографіями, моделлю доходності та мінімальним внеском.</p>
    <Link to="/admin/assets/new" className="inline-flex items-center gap-1.5 mt-5 px-5 h-10 rounded-full text-sm font-medium" style={{ background: 'var(--token-primary)', color: 'var(--token-on-primary)' }}>
      <Plus className="w-4 h-4" /> Створити актив
    </Link>
  </div>
);
