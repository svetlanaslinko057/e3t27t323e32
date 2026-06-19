import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { lumen, lumenError, formatUSD } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { SiteHeader } from '@/pages/LandingPage';
import PublicSiteFooter from '@/components/PublicSiteFooter';
import OtcBuyModal from '@/components/otc/OtcBuyModal';
import {
  ArrowLeft, MapPin, Building2, ShoppingCart, ShieldCheck, TrendingUp, Coins,
  Calendar, PieChart, History as HistoryIcon, Wallet, Banknote, CheckCircle2, Repeat,
} from 'lucide-react';

const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;
const CAT_LABEL = {
  real_estate: { uk: 'Нерухомість', en: 'Real estate' },
  commercial: { uk: 'Комерція', en: 'Commercial' },
  construction: { uk: 'Будівництво', en: 'Construction' },
  land: { uk: 'Земля', en: 'Land' },
};

export default function OtcLotPage() {
  const { id } = useParams();
  const { bi } = useLang();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [buy, setBuy] = useState(false);

  useEffect(() => {
    setLoading(true); setError('');
    lumen.get(`/public/otc/listings/${id}`)
      .then((r) => setListing(r.data?.listing || null))
      .catch((e) => setError(lumenError(e)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="otc-lot-page">
      <SiteHeader solid />
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-8">
        <Link to="/otc" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6" data-testid="otc-lot-back">
          <ArrowLeft className="w-4 h-4" /> {bi('До OTC ринку', 'Back to OTC market')}
        </Link>

        {loading ? (
          <div className="grid lg:grid-cols-3 gap-8"><div className="lg:col-span-2 h-96 rounded-2xl bg-muted/40 animate-pulse" /><div className="h-96 rounded-2xl bg-muted/40 animate-pulse" /></div>
        ) : error ? (
          <div className="p-6 rounded-xl bg-red-50 border border-red-200 text-red-700">{error}</div>
        ) : !listing ? (
          <div className="p-16 text-center text-muted-foreground">{bi('Лот не знайдено.', 'Lot not found.')}</div>
        ) : (
          <LotDetail listing={listing} bi={bi} onBuy={() => setBuy(true)} />
        )}
      </div>
      <PublicSiteFooter />
      {buy && listing && <OtcBuyModal listing={listing} onClose={() => setBuy(false)} />}
    </div>
  );
}

function LotDetail({ listing, bi, onBuy }) {
  const a = listing.asset || {};
  const m = listing.metrics || {};
  const share = m.share_percent ?? listing.ownership_percent;
  const cat = CAT_LABEL[a.category];
  const history = listing.payout_history || [];
  const maxPayout = Math.max(1, ...history.map((h) => h.amount || 0));
  const totalPaid = history.reduce((s, h) => s + (h.amount || 0), 0);

  return (
    <div className="grid lg:grid-cols-3 gap-8">
      {/* LEFT — gallery + story */}
      <div className="lg:col-span-2 space-y-6">
        <div className="rounded-2xl overflow-hidden border border-border bg-card">
          <div className="relative h-72 md:h-96 bg-muted">
            {a.cover_url
              ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" />
              : <div className="w-full h-full flex items-center justify-center text-muted-foreground"><Building2 className="w-16 h-16" /></div>}
            <div className="absolute top-4 left-4 flex gap-2">
              {cat && <span className="px-3 py-1 rounded-md bg-background/90 backdrop-blur text-[11px] font-semibold uppercase tracking-wider">{bi(cat.uk, cat.en)}</span>}
              <span className="px-3 py-1 rounded-md bg-emerald-600 text-white text-[11px] font-semibold flex items-center gap-1"><Repeat className="w-3 h-3" /> OTC</span>
            </div>
          </div>
          <div className="p-6">
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight">{a.title}</h1>
            {a.location && <p className="mt-2 text-muted-foreground flex items-center gap-1.5"><MapPin className="w-4 h-4" /> {a.location}</p>}
            {a.description && <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{a.description}</p>}
          </div>
        </div>

        {/* economics */}
        <div className="rounded-2xl border border-border bg-card p-6">
          <h2 className="font-semibold text-lg flex items-center gap-2"><PieChart className="w-5 h-5 text-[#2E5D4F]" /> {bi('Економіка частки', 'Share economics')}</h2>
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-4">
            <Fact label={bi('Частка в активі', 'Share of asset')} value={PCT(share)} icon={PieChart} />
            <Fact label={bi('Цільова дохідність', 'Target yield')} value={PCT(m.annual_yield ?? a.target_yield)} icon={TrendingUp} accent />
            <Fact label={bi('ROI за ціною', 'ROI at ask')} value={PCT(m.roi_at_ask)} icon={TrendingUp} />
            <Fact label={bi('Дивіденди / рік', 'Dividends / yr')} value={formatUSD(m.dividends_12m)} icon={Coins} accent />
            <Fact label={bi('Дохід / місяць', 'Income / month')} value={formatUSD(m.monthly_income)} icon={Coins} />
            <Fact label={bi('Окупність', 'Payback')} value={m.payback_years ? `${m.payback_years} ${bi('р.', 'y')}` : '—'} icon={Calendar} />
            <Fact label={bi('Первинна інвестиція', 'Initial invested')} value={formatUSD(m.invested_usd)} icon={Banknote} />
            <Fact label={bi('Переоцінка', 'Appreciation')} value={PCT(m.appreciation_pct)} icon={TrendingUp} />
            <Fact label={bi('Юніти', 'Units')} value={listing.units ?? '—'} icon={PieChart} />
          </div>
        </div>

        {/* payout history */}
        {history.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-6" data-testid="otc-payout-history">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-lg flex items-center gap-2"><HistoryIcon className="w-5 h-5 text-[#2E5D4F]" /> {bi('Історія виплат', 'Payout history')}</h2>
              <span className="text-sm text-muted-foreground">{bi('Всього виплачено', 'Total paid')}: <span className="font-semibold text-foreground">{formatUSD(totalPaid)}</span></span>
            </div>
            <div className="mt-5 flex items-end gap-1.5 h-32">
              {history.map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1 group" title={`${h.month}: ${formatUSD(h.amount)}`}>
                  <div className="w-full rounded-t bg-emerald-500/80 group-hover:bg-emerald-600 transition-colors" style={{ height: `${Math.max(6, (h.amount / maxPayout) * 100)}%` }} />
                  <span className="text-[9px] text-muted-foreground rotate-0">{(h.month || '').slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* RIGHT — sticky buy box */}
      <div className="lg:col-span-1">
        <div className="sticky top-20 rounded-2xl border border-border bg-card overflow-hidden">
          <div className="p-6 border-b border-border">
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{bi('Ціна частки', 'Share price')}</p>
            <p className="mt-1 text-4xl font-bold tabular-nums">{formatUSD(listing.price_usd)}</p>
            <p className="mt-1 text-sm text-muted-foreground">{bi('за', 'for')} {PCT(share)} {bi('активу', 'of the asset')}</p>
            <button onClick={onBuy} data-testid="otc-lot-buy"
              className="mt-5 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700">
              <ShoppingCart className="w-5 h-5" /> {bi('Купити частку', 'Buy share')}
            </button>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1"><Wallet className="w-3.5 h-3.5" /> {bi('Гаманець / USDT', 'Wallet / USDT')}</span>
              <span className="inline-flex items-center gap-1"><Banknote className="w-3.5 h-3.5" /> {bi('Баланс USD', 'USD balance')}</span>
            </div>
          </div>
          <div className="p-6 space-y-3 text-sm">
            <Guarantee icon={ShieldCheck} text={bi('LUMEN виступає гарантом угоди (escrow)', 'LUMEN acts as the deal guarantor (escrow)')} />
            <Guarantee icon={CheckCircle2} text={bi('Цифровий сертифікат власності після угоди', 'Digital ownership certificate after the deal')} />
            <Guarantee icon={Coins} text={bi('Дивіденди нараховуються пропорційно частці', 'Dividends accrue pro-rata to your share')} />
          </div>
          <div className="px-6 pb-6">
            <div className="rounded-xl bg-muted/30 p-3 text-[11px] text-muted-foreground">
              {bi('Купуйте як гість — після реєстрації лот автоматично з’явиться у вашому кабінеті.',
                  'Buy as a guest — after registration the lot will automatically appear in your cabinet.')}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const Fact = ({ label, value, icon: Icon, accent }) => (
  <div className="rounded-xl border border-border bg-background p-3">
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground"><Icon className="w-3.5 h-3.5" /> {label}</div>
    <p className={`mt-1 text-lg font-bold tabular-nums ${accent ? 'text-emerald-600' : ''}`}>{value}</p>
  </div>
);

const Guarantee = ({ icon: Icon, text }) => (
  <div className="flex items-start gap-2.5"><Icon className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" /><span className="text-muted-foreground">{text}</span></div>
);
