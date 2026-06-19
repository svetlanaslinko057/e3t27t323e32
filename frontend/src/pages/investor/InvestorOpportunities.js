import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { Building2 } from 'lucide-react';
import { AssetScoreBadges } from '@/components/lumen/AssetIntelligence';

const CATEGORIES = [
  { key: 'all', label: 'Усі' },
  { key: 'real_estate', label: 'Нерухомість' },
  { key: 'land', label: 'Земля' },
  { key: 'construction', label: 'Будівництво' },
  { key: 'commercial', label: 'Комерція' },
];

export default function InvestorOpportunities() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    lumen.get('/assets', { params: { status: 'open' } })
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () => (filter === 'all' ? items : items.filter((a) => a.category === filter)),
    [items, filter]
  );

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="investor-opportunities">
      {/* legacy alias marker so /investor/assets references resolve */}
      <span data-testid="investor-assets" className="sr-only" aria-hidden="true" />
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Об'єкти</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Активні раунди для участі</h1>
        <p className="mt-1 text-muted-foreground">Оберіть об'єкт, перегляньте модель доходності і оформіть договір участі.</p>
      </header>

      <div className="flex flex-wrap gap-2 mb-6" data-testid="opportunities-filters">
        {CATEGORIES.map((c) => (
          <button
            key={c.key}
            onClick={() => setFilter(c.key)}
            className={`px-4 h-9 rounded-full text-sm font-medium border transition ${
              filter === c.key
                ? 'bg-foreground text-background border-foreground'
                : 'bg-card border-border text-muted-foreground hover:text-foreground'
            }`}
            data-testid={`filter-${c.key}`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-80 rounded-2xl bg-muted/40 animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <p className="font-semibold">На цьому фільтрі об'єктів немає</p>
          <p className="text-sm text-muted-foreground mt-2">Перемкніться між категоріями або перевірте вибір пізніше.</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((a) => <AssetCard key={a.id} asset={a} />)}
        </div>
      )}
    </div>
  );
}

const AssetCard = ({ asset }) => (
  <Link
    to={`/investor/assets/${asset.id}`}
    className="group rounded-2xl border border-border bg-card overflow-hidden hover:shadow-lg transition flex flex-col"
    data-testid={`asset-${asset.id}`}
  >
    <div
      className="aspect-[16/10] bg-muted relative"
      style={asset.cover_url ? { backgroundImage: `url(${asset.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
    >
      {!asset.cover_url && <div className="absolute inset-0 flex items-center justify-center text-muted-foreground"><Building2 className="w-12 h-12" /></div>}
      <span className="absolute top-3 left-3 px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-background/90 border border-border">
        {asset.category_label || asset.category}
      </span>
      {asset.status === 'open' && (
        <span className="absolute top-3 right-3 px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-[#2E5D4F] text-white">відкрито</span>
      )}
    </div>
    <div className="p-5 flex-1 flex flex-col">
      <h3 className="font-semibold text-lg leading-snug">{asset.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{asset.location}</p>
      <div className="mt-2"><AssetScoreBadges assetId={asset.id} /></div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Цільова дохідність</p>
          <p className="font-semibold text-[#2E5D4F]">{formatPercent(asset.target_yield)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Мінімум</p>
          <p className="font-semibold">{formatUAH(asset.min_ticket)}</p>
        </div>
      </div>
      <div className="mt-4 pt-4 border-t border-border">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
          <span>Прогрес раунду</span>
          <span className="font-mono">{asset.progress_percent || 0}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
          <div className="h-full bg-[#2E5D4F] transition-all" style={{ width: `${asset.progress_percent || 0}%` }} />
        </div>
      </div>
    </div>
  </Link>
);
