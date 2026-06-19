import { useEffect, useMemo, useState } from 'react';
import { lumen } from '@/lib/lumenApi';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';
import PublicAssetCard from '@/components/public/PublicAssetCard';
import { Loader2, SearchX } from 'lucide-react';

const FALLBACK_ASSETS = [
  { id: 'fa1', title: 'ЖК «Подільський»', category: 'real_estate', location: 'Поділ, Київ', target_yield: 18.5, min_ticket: 65000, progress_percent: 62, cover_url: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa2', title: 'Земельна ділянка «Стоянка»', category: 'land', location: 'Бориспільський р-н', target_yield: 22.0, min_ticket: 70000, progress_percent: 31, cover_url: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa3', title: 'ТЦ «Лавр»', category: 'commercial', location: 'Львів, Шевченківський', target_yield: 14.7, min_ticket: 90000, progress_percent: 88, cover_url: 'https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa4', title: 'Логістичний хаб «Рівне-Захід»', category: 'construction', location: 'Рівне, об’їзна', target_yield: 19.2, min_ticket: 200000, progress_percent: 20, cover_url: 'https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa5', title: 'Будинок «Французький»', category: 'real_estate', location: 'Одеса', target_yield: 13.4, min_ticket: 65000, progress_percent: 5, cover_url: 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa6', title: 'Котеджне містечко «Вишневе»', category: 'construction', location: 'с. Гатне', target_yield: 21.5, min_ticket: 180000, progress_percent: 12, cover_url: 'https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=900&q=80' },
];

const FILTERS = [
  { key: 'all', label: 'Усі' },
  { key: 'real_estate', label: 'Нерухомість' },
  { key: 'construction', label: 'Будівництво' },
  { key: 'commercial', label: 'Комерція' },
  { key: 'land', label: 'Земля' },
  { key: 'business', label: 'Бізнес' },
];

export default function PublicAssetsPage() {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    document.title = 'LUMEN · Активи та відкриті раунди';
    let active = true;
    lumen.get('/assets', { params: { limit: 60 } })
      .then((r) => {
        if (!active) return;
        const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        setAssets(items.length ? items : FALLBACK_ASSETS);
      })
      .catch(() => { if (active) setAssets(FALLBACK_ASSETS); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      const okCat = filter === 'all' || a.category === filter;
      const okQ = !query || `${a.title} ${a.location || ''}`.toLowerCase().includes(query.toLowerCase());
      return okCat && okQ;
    });
  }, [assets, filter, query]);

  return (
    <>
      <PageHero
        breadcrumb={[{ label: 'Головна', to: '/' }, { label: 'Активи' }]}
        title="Активи у відкритих раундах"
        lead="Обирайте об’єкти з прозорими параметрами, прогнозом дохідності та реальним прогресом раунду. Інвестуйте від $1,000."
        watermark="ASSETS"
      />

      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Filters */}
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-wrap gap-2" data-testid="assets-filter-category-tabs">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFilter(f.key)}
                  className={`h-9 rounded-full px-4 text-sm font-medium transition ${filter === f.key ? 'bg-[#2E5D4F] text-white' : 'border border-border bg-white text-token-muted hover:border-[#2E5D4F] hover:text-[#2E5D4F]'}`}
                  data-testid={`assets-filter-${f.key}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Пошук за назвою або локацією"
              className="h-10 w-full rounded-xl border border-border bg-white px-4 text-sm md:w-72"
              data-testid="assets-search-input"
            />
          </div>

          {/* Grid */}
          {loading ? (
            <div className="flex justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-[#2E5D4F]" /></div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-24 text-token-muted">
              <SearchX className="h-10 w-10" />
              <p>За вашим запитом активів не знайдено.</p>
            </div>
          ) : (
            <div className="mt-10 grid gap-6 sm:grid-cols-2 xl:grid-cols-3" data-testid="assets-grid">
              {filtered.map((a, i) => (
                <Reveal key={a.id} delay={(i % 3) * 0.06}>
                  <PublicAssetCard asset={a} />
                </Reveal>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
