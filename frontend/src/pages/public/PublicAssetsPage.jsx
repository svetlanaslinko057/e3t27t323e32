import { useEffect, useMemo, useRef, useState } from 'react';
import { lumen } from '@/lib/lumenApi';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';
import PublicAssetCard from '@/components/public/PublicAssetCard';
import { Loader2, SearchX, Search, X, MapPin, Building2, ChevronDown, Plus } from 'lucide-react';

const FALLBACK_ASSETS = [
  { id: 'fa1', title: 'ЖК «Подільський»', category: 'real_estate', location: 'Поділ, Київ', target_yield: 18.5, min_ticket: 65000, progress_percent: 62, cover_url: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa2', title: 'Земельна ділянка «Стоянка»', category: 'land', location: 'Бориспільський р-н', target_yield: 22.0, min_ticket: 70000, progress_percent: 31, cover_url: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa3', title: 'ТЦ «Лавр»', category: 'commercial', location: 'Львів, Шевченківський', target_yield: 14.7, min_ticket: 90000, progress_percent: 88, cover_url: 'https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=900&q=80' },
];

const FILTERS = [
  { key: 'all', label: 'Усі' },
  { key: 'real_estate', label: 'Нерухомість' },
  { key: 'construction', label: 'Будівництво' },
  { key: 'commercial', label: 'Комерція' },
  { key: 'land', label: 'Земля' },
  { key: 'business', label: 'Бізнес' },
];

const SORTS = [
  { key: 'featured', label: 'Рекомендовані' },
  { key: 'yield_desc', label: 'Дохідність: висока → низька' },
  { key: 'yield_asc', label: 'Дохідність: низька → висока' },
  { key: 'ticket_asc', label: 'Вхід: дешевше спочатку' },
  { key: 'ticket_desc', label: 'Вхід: дорожче спочатку' },
  { key: 'progress_desc', label: 'Прогрес раунду' },
  { key: 'newest', label: 'Найновіші' },
];

const PAGE_SIZE = 6;
const MIN_QUERY = 2;

const progressOf = (a) => {
  if (typeof a.progress_percent === 'number') return a.progress_percent;
  const t = Number(a.round_target || a.target_amount || 0);
  const r = Number(a.raised || a.raised_amount || 0);
  return t > 0 ? Math.min(100, Math.round((r / t) * 100)) : 0;
};
const ts = (a) => {
  const d = a.created_at || a.updated_at;
  const n = d ? new Date(d).getTime() : 0;
  return Number.isFinite(n) ? n : 0;
};

export default function PublicAssetsPage() {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [rawQuery, setRawQuery] = useState('');
  const [sort, setSort] = useState('featured');
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [showSug, setShowSug] = useState(false);
  const [activeSug, setActiveSug] = useState(-1);
  const searchRef = useRef(null);

  const query = rawQuery.trim();
  const queryActive = query.length >= MIN_QUERY;

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

  // close suggestions on outside click
  useEffect(() => {
    const onDoc = (e) => { if (searchRef.current && !searchRef.current.contains(e.target)) setShowSug(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // reset pagination whenever the result set changes
  useEffect(() => { setVisible(PAGE_SIZE); }, [filter, query, sort]);

  // live suggestions (titles + locations) for the current input
  const suggestions = useMemo(() => {
    if (!queryActive) return [];
    const q = query.toLowerCase();
    const seen = new Set();
    const out = [];
    for (const a of assets) {
      if (a.title && a.title.toLowerCase().includes(q) && !seen.has(a.title.toLowerCase())) {
        seen.add(a.title.toLowerCase());
        out.push({ kind: 'asset', text: a.title, sub: a.location, id: a.id });
      }
    }
    for (const a of assets) {
      const loc = a.location || '';
      const key = `loc:${loc.toLowerCase()}`;
      if (loc && loc.toLowerCase().includes(q) && !seen.has(key)) {
        seen.add(key);
        out.push({ kind: 'location', text: loc });
      }
    }
    return out.slice(0, 6);
  }, [assets, query, queryActive]);

  const filtered = useMemo(() => {
    const list = assets.filter((a) => {
      const okCat = filter === 'all' || a.category === filter;
      const okQ = !queryActive || `${a.title} ${a.location || ''}`.toLowerCase().includes(query.toLowerCase());
      return okCat && okQ;
    });
    const s = [...list];
    switch (sort) {
      case 'yield_desc': s.sort((a, b) => (b.target_yield || 0) - (a.target_yield || 0)); break;
      case 'yield_asc': s.sort((a, b) => (a.target_yield || 0) - (b.target_yield || 0)); break;
      case 'ticket_asc': s.sort((a, b) => (a.min_ticket || 0) - (b.min_ticket || 0)); break;
      case 'ticket_desc': s.sort((a, b) => (b.min_ticket || 0) - (a.min_ticket || 0)); break;
      case 'progress_desc': s.sort((a, b) => progressOf(b) - progressOf(a)); break;
      case 'newest': s.sort((a, b) => ts(b) - ts(a)); break;
      default: s.sort((a, b) => (Number(b.featured || 0) - Number(a.featured || 0)) || (b.target_yield || 0) - (a.target_yield || 0));
    }
    return s;
  }, [assets, filter, query, queryActive, sort]);

  const shown = filtered.slice(0, visible);
  const hasMore = filtered.length > visible;

  const pickSuggestion = (sug) => {
    setRawQuery(sug.text);
    setShowSug(false);
    setActiveSug(-1);
  };

  const onKeyDown = (e) => {
    if (!showSug || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveSug((i) => Math.min(i + 1, suggestions.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveSug((i) => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter' && activeSug >= 0) { e.preventDefault(); pickSuggestion(suggestions[activeSug]); }
    else if (e.key === 'Escape') { setShowSug(false); }
  };

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
          {/* Controls */}
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
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

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                {/* Search with suggestions */}
                <div ref={searchRef} className="relative w-full sm:w-80">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-token-muted" />
                  <input
                    type="text"
                    value={rawQuery}
                    onChange={(e) => { setRawQuery(e.target.value); setShowSug(true); setActiveSug(-1); }}
                    onFocus={() => setShowSug(true)}
                    onKeyDown={onKeyDown}
                    placeholder="Пошук за назвою або локацією"
                    aria-label="Пошук активів"
                    className="h-11 w-full rounded-xl border border-border bg-white pl-10 pr-9 text-sm focus:border-[#2E5D4F] focus:outline-none"
                    data-testid="assets-search-input"
                  />
                  {rawQuery && (
                    <button
                      type="button"
                      onClick={() => { setRawQuery(''); setShowSug(false); searchRef.current?.querySelector('input')?.focus(); }}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-token-muted hover:text-foreground"
                      aria-label="Очистити пошук"
                      data-testid="assets-search-clear"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}

                  {/* hint / suggestions dropdown */}
                  {showSug && rawQuery.length > 0 && rawQuery.trim().length < MIN_QUERY && (
                    <div className="absolute z-30 mt-2 w-full rounded-xl border border-border bg-white px-4 py-3 text-xs text-token-muted shadow-lg" data-testid="assets-search-hint">
                      Введіть щонайменше {MIN_QUERY} символи для пошуку
                    </div>
                  )}
                  {showSug && queryActive && suggestions.length > 0 && (
                    <ul className="absolute z-30 mt-2 w-full overflow-hidden rounded-xl border border-border bg-white py-1 shadow-xl" role="listbox" data-testid="assets-search-suggestions">
                      {suggestions.map((s, i) => (
                        <li key={`${s.kind}-${s.text}-${i}`}>
                          <button
                            type="button"
                            onMouseEnter={() => setActiveSug(i)}
                            onClick={() => pickSuggestion(s)}
                            className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition ${activeSug === i ? 'bg-[#2E5D4F]/8' : 'hover:bg-[#F7F5EF]'}`}
                            role="option"
                            aria-selected={activeSug === i}
                            data-testid={`assets-suggestion-${i}`}
                          >
                            <span className={`flex h-7 w-7 flex-none items-center justify-center rounded-lg ${s.kind === 'asset' ? 'bg-[#2E5D4F]/10 text-[#2E5D4F]' : 'bg-[#C9A961]/15 text-[#9c7d33]'}`}>
                              {s.kind === 'asset' ? <Building2 className="h-3.5 w-3.5" /> : <MapPin className="h-3.5 w-3.5" />}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-medium text-foreground">{s.text}</span>
                              {s.sub && <span className="block truncate text-xs text-token-muted">{s.sub}</span>}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {showSug && queryActive && suggestions.length === 0 && (
                    <div className="absolute z-30 mt-2 w-full rounded-xl border border-border bg-white px-4 py-3 text-xs text-token-muted shadow-lg">
                      Нічого не знайдено за «{query}»
                    </div>
                  )}
                </div>

                {/* Sort */}
                <div className="relative w-full sm:w-64">
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                    aria-label="Сортування"
                    className="h-11 w-full appearance-none rounded-xl border border-border bg-white pl-4 pr-10 text-sm font-medium text-foreground focus:border-[#2E5D4F] focus:outline-none"
                    data-testid="assets-sort-select"
                  >
                    {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-token-muted" />
                </div>
              </div>
            </div>

            {/* Result meta */}
            {!loading && (
              <p className="text-sm text-token-muted" data-testid="assets-result-count">
                {filtered.length === 0 ? 'Активів не знайдено' : (
                  <>Знайдено <b className="text-foreground">{filtered.length}</b> {pluralAssets(filtered.length)}
                    {(queryActive || filter !== 'all') && (
                      <button type="button" onClick={() => { setRawQuery(''); setFilter('all'); }} className="ml-2 text-[#2E5D4F] underline-offset-2 hover:underline">
                        скинути фільтри
                      </button>
                    )}
                  </>
                )}
              </p>
            )}
          </div>

          {/* Grid */}
          {loading ? (
            <div className="flex justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-[#2E5D4F]" /></div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-24 text-token-muted" data-testid="assets-empty">
              <SearchX className="h-10 w-10" />
              <p>За вашим запитом активів не знайдено.</p>
            </div>
          ) : (
            <>
              <div className="mt-8 grid gap-6 sm:grid-cols-2 xl:grid-cols-3" data-testid="assets-grid">
                {shown.map((a, i) => (
                  <Reveal key={a.id} delay={(i % 3) * 0.05}>
                    <PublicAssetCard asset={a} />
                  </Reveal>
                ))}
              </div>

              {hasMore && (
                <div className="mt-12 flex flex-col items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setVisible((v) => v + PAGE_SIZE)}
                    className="lpub-btn-gold"
                    data-testid="assets-show-more"
                  >
                    <Plus className="h-4 w-4" /> Показати більше
                  </button>
                  <span className="text-xs text-token-muted" data-testid="assets-shown-count">
                    Показано {shown.length} з {filtered.length}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </>
  );
}

function pluralAssets(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'актив';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'активи';
  return 'активів';
}
