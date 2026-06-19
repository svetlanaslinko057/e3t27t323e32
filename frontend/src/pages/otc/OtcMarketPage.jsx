import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { lumen, lumenError, formatUSD } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { SiteHeader } from '@/pages/LandingPage';
import PublicSiteFooter from '@/components/PublicSiteFooter';
import OtcBuyModal from '@/components/otc/OtcBuyModal';
import {
  Repeat, ShoppingCart, MapPin, Building2, ShieldCheck, TrendingUp, Search,
  RefreshCw, ArrowRight, BadgeCheck, Layers,
} from 'lucide-react';

const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;

const CATS = [
  { id: 'all', uk: 'Усі', en: 'All' },
  { id: 'real_estate', uk: 'Нерухомість', en: 'Real estate' },
  { id: 'commercial', uk: 'Комерція', en: 'Commercial' },
  { id: 'construction', uk: 'Будівництво', en: 'Construction' },
  { id: 'land', uk: 'Земля', en: 'Land' },
];
const CAT_LABEL = {
  real_estate: { uk: 'Нерухомість', en: 'Real estate' },
  commercial: { uk: 'Комерція', en: 'Commercial' },
  construction: { uk: 'Будівництво', en: 'Construction' },
  land: { uk: 'Земля', en: 'Land' },
};

export default function OtcMarketPage() {
  const { bi } = useLang();
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [cat, setCat] = useState('all');
  const [q, setQ] = useState('');
  const [buy, setBuy] = useState(null);

  const load = () => {
    setLoading(true); setError('');
    lumen.get('/public/otc/listings')
      .then((r) => setListings(r.data?.listings || []))
      .catch((e) => setError(lumenError(e)))
      .finally(() => setLoading(false));
  };
  useEffect(() => { document.title = 'LUMEN · OTC ринок часток'; load(); }, []);

  const filtered = useMemo(() => listings.filter((l) => {
    const okCat = cat === 'all' || l.asset?.category === cat;
    const okQ = !q || (l.asset?.title || '').toLowerCase().includes(q.toLowerCase()) || (l.asset?.location || '').toLowerCase().includes(q.toLowerCase());
    return okCat && okQ;
  }), [listings, cat, q]);

  const totalVolume = listings.reduce((s, l) => s + (l.price_usd || 0), 0);

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="otc-market-page">
      <SiteHeader solid />

      {/* hero strip */}
      <section className="border-b border-border bg-gradient-to-br from-[#2E5D4F] to-[#25493e] text-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-xs uppercase tracking-widest">
            <Repeat className="w-3.5 h-3.5" /> {bi('Вторинний ринок 24/7', 'Secondary market 24/7')}
          </div>
          <h1 className="mt-4 text-4xl md:text-5xl font-bold tracking-tight">{bi('OTC ринок часток', 'OTC share market')}</h1>
          <p className="mt-3 max-w-2xl text-white/80 text-lg">
            {bi('Купуйте частки в реальних активах, які інвестори перепродають на вторинному ринку. Ціна, дохідність та історія — прозоро. Оплата гаманцем або з балансу.',
                'Buy shares in real assets that investors resell on the secondary market. Price, yield and history — fully transparent. Pay with a wallet or from balance.')}
          </p>
          <div className="mt-6 flex flex-wrap gap-8">
            <HeroStat value={listings.length} label={bi('лотів у продажу', 'lots on sale')} />
            <HeroStat value={formatUSD(totalVolume)} label={bi('загальний обсяг', 'total volume')} />
            <HeroStat value={<span className="inline-flex items-center gap-1"><ShieldCheck className="w-5 h-5" /> Escrow</span>} label={bi('гарантія угоди', 'deal guarantee')} />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
        {/* filters */}
        <div className="flex flex-col md:flex-row md:items-center gap-3 mb-6">
          <div className="flex flex-wrap gap-2">
            {CATS.map((c) => (
              <button key={c.id} onClick={() => setCat(c.id)} data-testid={`otc-filter-${c.id}`}
                className={`px-3.5 py-2 rounded-full text-sm font-medium border transition ${cat === c.id ? 'bg-[#2E5D4F] text-white border-transparent' : 'bg-card border-border hover:bg-muted/50 text-muted-foreground'}`}>
                {bi(c.uk, c.en)}
              </button>
            ))}
          </div>
          <div className="md:ml-auto flex items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="otc-search" placeholder={bi('Пошук активу…', 'Search asset…')}
                className="pl-9 pr-3 py-2 rounded-full border border-border bg-card text-sm w-56" />
            </div>
            <button onClick={load} data-testid="otc-refresh" className="px-3 py-2 rounded-full border border-border bg-card hover:bg-muted/50 text-sm flex items-center gap-2">
              <RefreshCw className="w-3.5 h-3.5" /> {bi('Оновити', 'Refresh')}
            </button>
          </div>
        </div>

        {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

        {loading ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">{[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-80 rounded-2xl bg-muted/40 animate-pulse" />)}</div>
        ) : !filtered.length ? (
          <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
            <Layers className="w-10 h-10 mx-auto mb-3 opacity-40" />
            {bi('Немає лотів за обраним фільтром.', 'No lots match the selected filter.')}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="otc-market-grid">
            {filtered.map((l) => <LotCard key={l.id} listing={l} bi={bi} onBuy={() => setBuy(l)} />)}
          </div>
        )}
      </section>

      <PublicSiteFooter />
      {buy && <OtcBuyModal listing={buy} onClose={() => setBuy(null)} />}
    </div>
  );
}

const HeroStat = ({ value, label }) => (
  <div><p className="text-2xl font-bold">{value}</p><p className="text-xs uppercase tracking-widest text-white/60 mt-1">{label}</p></div>
);

function LotCard({ listing, bi, onBuy }) {
  const a = listing.asset || {};
  const m = listing.metrics || {};
  const share = m.share_percent ?? listing.ownership_percent;
  const cat = CAT_LABEL[a.category];
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col hover:shadow-xl hover:-translate-y-0.5 transition-all" data-testid={`otc-card-${listing.id}`}>
      <Link to={`/otc/${listing.id}`} className="block relative h-44 bg-muted overflow-hidden">
        {a.cover_url
          ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" loading="lazy" />
          : <div className="w-full h-full flex items-center justify-center text-muted-foreground"><Building2 className="w-10 h-10" /></div>}
        <div className="absolute top-3 left-3 flex gap-1.5">
          {cat && <span className="px-2.5 py-1 rounded-md bg-background/90 backdrop-blur text-[10px] font-semibold uppercase tracking-wider text-foreground">{bi(cat.uk, cat.en)}</span>}
        </div>
        {a.target_yield != null && (
          <div className="absolute top-3 right-3 px-2.5 py-1 rounded-md bg-emerald-600 text-white text-[11px] font-bold flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> {PCT(a.target_yield)} {bi('річних', 'p.a.')}
          </div>
        )}
      </Link>
      <div className="p-5 flex-1 flex flex-col">
        <Link to={`/otc/${listing.id}`} className="font-semibold leading-tight hover:text-[#2E5D4F]">{a.title}</Link>
        {a.location && <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1"><MapPin className="w-3 h-3" /> {a.location}</p>}
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <Metric label={bi('Частка', 'Share')} value={PCT(share)} />
          <Metric label={bi('Дивіденди/рік', 'Dividends/yr')} value={formatUSD(m.dividends_12m)} accent />
          <Metric label={bi('ROI', 'ROI')} value={PCT(m.roi_at_ask)} />
        </div>
        <div className="mt-auto pt-4 flex items-end justify-between border-t border-border mt-4">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{bi('Ціна частки', 'Share price')}</p>
            <p className="text-2xl font-bold tabular-nums">{formatUSD(listing.price_usd)}</p>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <button onClick={onBuy} data-testid={`otc-card-buy-${listing.id}`}
              className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 flex items-center gap-1.5">
              <ShoppingCart className="w-4 h-4" /> {bi('Купити', 'Buy')}
            </button>
            <Link to={`/otc/${listing.id}`} className="text-[11px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
              {bi('Деталі', 'Details')} <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

const Metric = ({ label, value, accent }) => (
  <div>
    <p className="text-[10px] uppercase tracking-wide text-muted-foreground leading-tight">{label}</p>
    <p className={`font-bold tabular-nums text-sm mt-0.5 ${accent ? 'text-emerald-600' : ''}`}>{value}</p>
  </div>
);
