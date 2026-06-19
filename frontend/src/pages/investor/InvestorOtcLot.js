import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  ArrowLeft, MapPin, Building2, ShoppingCart, ShieldCheck, TrendingUp, Coins,
  PieChart, CalendarClock, BadgeCheck, ChevronDown, ChevronUp, Lock,
} from 'lucide-react';

const USD = (n) => (n === null || n === undefined || isNaN(n))
  ? '$0' : '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;
const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '—');

const CAT = {
  real_estate: { uk: 'Житлова нерухомість', en: 'Residential' },
  commercial: { uk: 'Комерційна нерухомість', en: 'Commercial' },
  land: { uk: 'Земельна ділянка', en: 'Land' },
  construction: { uk: 'Будівництво', en: 'Construction' },
};

/** OTC lot detail — the "store page" for a SHARE in a real asset. */
export default function InvestorOtcLot() {
  const { id } = useParams();
  const nav = useNavigate();
  const { bi } = useLang();
  const [listing, setListing] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [showTech, setShowTech] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await lumen.get(`/investor/otc/listings/${id}`);
      setListing(r.data.listing);
      setHistory(r.data.listing?.payout_history || []);
    } catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const buy = async () => {
    setBusy(true); setNotice('');
    try { await lumen.post(`/investor/otc/listings/${id}/buy`, {}); setNotice(bi('Угоду створено! Перейдіть у «Мої угоди» для оплати.', 'Deal created! Go to "My deals" to pay.')); await load(); }
    catch (e) { setNotice(lumenError(e)); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="p-10 max-w-5xl"><div className="h-72 rounded-2xl bg-muted/40 animate-pulse" /></div>;
  if (error || !listing) return (
    <div className="p-10 max-w-3xl">
      <button onClick={() => nav('/investor/otc')} className="text-sm text-token-muted flex items-center gap-1 mb-4"><ArrowLeft className="w-4 h-4" /> {bi('До ринку', 'Back to market')}</button>
      <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700">{error || bi('Лот не знайдено', 'Lot not found')}</div>
    </div>
  );

  const a = listing.asset || {};
  const m = listing.metrics || {};
  const cat = CAT[a.category];
  const maxH = Math.max(1, ...history.map((h) => h.amount));

  return (
    <div className="p-6 md:p-10 max-w-5xl" data-testid="otc-lot">
      <button onClick={() => nav('/investor/otc')} data-testid="lot-back" className="text-sm text-token-muted flex items-center gap-1 mb-4 hover:text-foreground">
        <ArrowLeft className="w-4 h-4" /> {bi('До ринку', 'Back to market')}
      </button>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* left: media + info */}
        <div className="lg:col-span-2 space-y-5">
          <div className="rounded-2xl overflow-hidden border border-border bg-card">
            <div className="relative h-64 bg-muted">
              {a.cover_url
                ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" />
                : <div className="w-full h-full bg-gradient-to-br from-emerald-100 to-sky-100 flex items-center justify-center"><Building2 className="w-12 h-12 text-emerald-600/60" /></div>}
              <div className="absolute top-3 left-3 flex gap-2">
                {cat && <span className="px-2.5 py-1 rounded-full bg-white/90 text-xs font-medium text-slate-700">{bi(cat.uk, cat.en)}</span>}
                {a.target_yield != null && <span className="px-2.5 py-1 rounded-full bg-emerald-600 text-white text-xs font-semibold">{PCT(a.target_yield)} {bi('річних', 'p.a.')}</span>}
              </div>
              {listing.nft?.frozen && <span className="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-amber-500 text-white text-xs flex items-center gap-1"><Lock className="w-3 h-3" /> {bi('заморожено', 'frozen')}</span>}
            </div>
            <div className="p-5">
              <h1 className="text-2xl font-bold tracking-tight">{a.title || listing.pool_id}</h1>
              {a.location && <p className="mt-1 text-token-muted flex items-center gap-1.5"><MapPin className="w-4 h-4" /> {a.location}</p>}
              {a.description && <p className="mt-3 text-sm text-token-muted leading-relaxed">{a.description}</p>}
            </div>
          </div>

          {/* economics */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <h2 className="font-semibold mb-4 flex items-center gap-2"><PieChart className="w-4 h-4 text-emerald-600" /> {bi('Економіка частки', 'Share economics')}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Eco icon={PieChart} label={bi('Ваша частка', 'Your share')} value={PCT(m.share_percent)} />
              <Eco icon={TrendingUp} label={bi('Дохідність активу', 'Asset yield')} value={PCT(m.annual_yield)} accent="emerald" />
              <Eco icon={Coins} label={bi('Дивіденди / рік', 'Dividends / yr')} value={USD(m.dividends_12m)} accent="emerald" />
              <Eco icon={BadgeCheck} label={bi('ROI за ціною', 'ROI at ask')} value={PCT(m.roi_at_ask)} accent="emerald" />
              <Eco icon={CalendarClock} label={bi('Окупність', 'Payback')} value={m.payback_years ? `${m.payback_years} ${bi('р.', 'yr')}` : '—'} />
              <Eco icon={Coins} label={bi('Дохід / місяць', 'Income / mo')} value={USD(m.monthly_income)} />
            </div>
          </div>

          {/* payout history */}
          <div className="rounded-2xl border border-border bg-card p-5">
            <h2 className="font-semibold mb-1 flex items-center gap-2"><CalendarClock className="w-4 h-4 text-sky-600" /> {bi('Історія виплат (12 міс)', 'Payout history (12 mo)')}</h2>
            <p className="text-xs text-token-muted mb-4">{bi('Прогноз на основі дохідності активу та частки.', 'Projection based on the asset yield and the share.')}</p>
            <div className="flex items-end gap-1.5 h-28" data-testid="lot-payout-chart">
              {history.map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
                  <div className="w-full rounded-t bg-emerald-500/80 group-hover:bg-emerald-600 transition-all" style={{ height: `${(h.amount / maxH) * 100}%` }} title={`${h.month}: ${USD(h.amount)}`} />
                  <span className="text-[8px] text-token-muted rotate-0">{h.month.slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* right: buy box */}
        <div className="lg:col-span-1">
          <div className="sticky top-20 rounded-2xl border border-border bg-card p-5" data-testid="lot-buybox">
            <p className="text-xs uppercase tracking-widest text-token-muted">{bi('Ціна частки', 'Share price')}</p>
            <p className="text-3xl font-bold tabular-nums mt-1">{USD(listing.price_usd)}</p>
            {m.appreciation_pct != null && (
              <p className={`text-sm mt-1 font-medium ${m.appreciation_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                {m.appreciation_pct >= 0 ? '+' : ''}{PCT(m.appreciation_pct)} {bi('до вкладеного', 'vs invested')}
              </p>
            )}

            <div className="mt-4 space-y-2 text-sm border-t border-border pt-4">
              <Row k={bi('Частка в активі', 'Stake in asset')} v={PCT(m.share_percent)} />
              <Row k={bi('Дивіденди / рік', 'Dividends / yr')} v={USD(m.dividends_12m)} accent />
              <Row k={bi('ROI', 'ROI')} v={PCT(m.roi_at_ask)} accent />
              <Row k={bi('Окупність', 'Payback')} v={m.payback_years ? `${m.payback_years} ${bi('р.', 'yr')}` : '—'} />
            </div>

            <div className="mt-4 flex items-center gap-2 text-xs text-token-muted bg-muted/40 rounded-lg p-2.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
              {bi('LUMEN виступає гарантом угоди (escrow). Право власності переходить після оплати.',
                  'LUMEN is the deal guarantor (escrow). Ownership transfers after payment.')}
            </div>

            {notice && <div className="mt-3 p-2.5 rounded-lg bg-muted/50 border border-border text-xs" data-testid="lot-notice">{notice}</div>}

            {listing.is_mine ? (
              <div className="mt-4 text-center text-sm text-token-muted py-2 border border-dashed border-border rounded-xl">{bi('Це ваш лот', 'This is your listing')}</div>
            ) : listing.status !== 'active' ? (
              <div className="mt-4 text-center text-sm text-amber-700 py-2 border border-amber-200 bg-amber-50 rounded-xl">{bi('Лот недоступний', 'Lot unavailable')}</div>
            ) : (
              <button data-testid="lot-buy" onClick={buy} disabled={busy || listing.nft?.frozen}
                className="mt-4 w-full px-4 py-3 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 disabled:opacity-40 flex items-center justify-center gap-2">
                <ShoppingCart className="w-5 h-5" /> {busy ? bi('Створення…', 'Creating…') : bi('Купити частку', 'Buy share')}
              </button>
            )}

            {/* seller + technical (NFT) details */}
            <div className="mt-4 pt-4 border-t border-border">
              <div className="flex items-center gap-2 text-sm">
                <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center"><BadgeCheck className="w-4 h-4 text-emerald-600" /></div>
                <span className="text-token-muted">{bi('Продавець:', 'Seller:')}</span>
                <span className="font-medium">{bi('Перевірений інвестор', 'Verified investor')}</span>
              </div>
              <button onClick={() => setShowTech((v) => !v)} data-testid="lot-tech-toggle" className="mt-3 w-full flex items-center justify-between text-[11px] text-token-muted hover:text-foreground">
                <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> {bi('Документ власності', 'Ownership document')}</span>
                {showTech ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
              {showTech && (
                <div className="mt-2 rounded-lg bg-muted/40 p-3 text-[11px] space-y-1 font-mono" data-testid="lot-tech">
                  <div className="flex justify-between"><span className="text-token-muted">{bi('Сертифікат', 'Certificate')}</span><span>{listing.nft?.token_id ? `#${listing.nft.token_id}` : '—'}</span></div>
                  <div className="flex justify-between"><span className="text-token-muted">{bi('Юніти', 'Units')}</span><span>{listing.units}</span></div>
                  <div className="flex justify-between"><span className="text-token-muted">{bi('Стандарт', 'Standard')}</span><span>ERC-721</span></div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const Eco = ({ icon: Icon, label, value, accent }) => (
  <div className="rounded-xl bg-muted/40 p-3">
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-token-muted">{Icon && <Icon className="w-3.5 h-3.5" />}{label}</div>
    <p className={`mt-1 text-lg font-bold tabular-nums ${accent === 'emerald' ? 'text-emerald-600' : ''}`}>{value}</p>
  </div>
);
const Row = ({ k, v, accent }) => (
  <div className="flex items-center justify-between">
    <span className="text-token-muted">{k}</span>
    <span className={`font-semibold tabular-nums ${accent ? 'text-emerald-600' : ''}`}>{v}</span>
  </div>
);
