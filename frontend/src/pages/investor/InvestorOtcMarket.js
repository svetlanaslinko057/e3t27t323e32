import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { useWallet } from '@/contexts/WalletContext';
import {
  Repeat, ShoppingCart, Tag, HandCoins, ScrollText, History as HistoryIcon,
  RefreshCw, MapPin, Building2, XCircle, Upload, Lock, TrendingUp, Wallet, Plus,
  Bookmark, CheckCircle2,
} from 'lucide-react';

const USD = (n) => (n === null || n === undefined || isNaN(n))
  ? '$0' : '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;

const TONE = {
  active: 'badge-success', completed: 'badge-success', payment_pending: 'badge-warning',
  payment_confirmed: 'badge-info', nft_transfer_pending: 'badge-info', pending: 'badge-warning',
  reserved: 'badge-info', cancelled: 'badge-neutral', disputed: 'badge-danger',
  accepted: 'badge-success', rejected: 'badge-neutral', expired: 'badge-neutral',
};
const Pill = ({ s }) => <span className={`status-badge ${TONE[s] || 'badge-neutral'}`} style={{ fontSize: 11 }}>{s || '—'}</span>;

/**
 * Full OTC Market — the secondary market for ASSET SHARES.
 * Everywhere the user buys/sells a "частка в активі", never "an NFT".
 */
export default function InvestorOtcMarket() {
  const { bi } = useLang();
  const initialTab = (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab')) || 'market';
  const [tab, setTab] = useState(['market', 'reservations', 'sell', 'listings', 'offers', 'deals', 'history'].includes(initialTab) ? initialTab : 'market');
  const TABS = [
    { id: 'market', icon: ShoppingCart, label: bi('Ринок', 'Market') },
    { id: 'reservations', icon: Bookmark, label: bi('Мої покупки з ринку', 'My market buys') },
    { id: 'sell', icon: Tag, label: bi('Продати частку', 'Sell a share') },
    { id: 'listings', icon: ScrollText, label: bi('Мої продажі', 'My listings') },
    { id: 'offers', icon: HandCoins, label: bi('Мої пропозиції', 'My offers') },
    { id: 'deals', icon: Repeat, label: bi('Мої угоди', 'My deals') },
    { id: 'history', icon: HistoryIcon, label: bi('Історія', 'History') },
  ];
  return (
    <div className="p-6 md:p-10 max-w-7xl" data-testid="investor-otc-market">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">{bi('Вторинний ринок', 'Secondary market')}</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">{bi('OTC ринок часток', 'OTC share market')}</h1>
        <p className="mt-1 text-token-muted text-sm">
          {bi('Купуйте та продавайте частки в реальних активах. LUMEN виступає гарантом угоди.',
              'Buy and sell shares in real assets. LUMEN acts as the deal guarantor.')}
        </p>
      </header>

      <div className="flex flex-wrap gap-2 mb-6" data-testid="otc-tabs">
        {TABS.map((t) => {
          const Icon = t.icon; const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`otc-tab-${t.id}`}
              className={`px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 border transition ${
                active ? 'nav-item-active border-transparent' : 'bg-card border-border hover:bg-muted/50 text-token-primary'}`}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'market' && <Market bi={bi} />}
      {tab === 'reservations' && <Reservations bi={bi} />}
      {tab === 'sell' && <Sell bi={bi} onListed={() => setTab('listings')} />}
      {tab === 'listings' && <MyListings bi={bi} />}
      {tab === 'offers' && <MyOffers bi={bi} />}
      {tab === 'deals' && <MyDeals bi={bi} terminal={false} />}
      {tab === 'history' && <MyDeals bi={bi} terminal={true} />}
    </div>
  );
}

function useApi(url) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const r = await lumen.get(url); setData(r.data); }
    catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, [url]);
  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}

const Loading = () => <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1, 2, 3].map((i) => <div key={i} className="h-56 rounded-2xl bg-muted/40 animate-pulse" />)}</div>;
const ErrBox = ({ msg }) => msg ? <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{msg}</div> : null;
const Empty = ({ msg }) => <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-token-muted">{msg}</div>;
const Refresh = ({ onClick }) => (
  <button onClick={onClick} data-testid="otc-refresh" className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2">
    <RefreshCw className="w-3.5 h-3.5" /> Оновити
  </button>
);

/* ── rich share-framed card used in Market & My listings ────────────────── */
const CAT_LABEL = {
  real_estate: { uk: 'Житло', en: 'Residential' },
  commercial: { uk: 'Комерція', en: 'Commercial' },
  land: { uk: 'Земля', en: 'Land' },
  construction: { uk: 'Будівництво', en: 'Construction' },
};
function ShareCard({ listing, bi, lang, children, footer }) {
  const a = listing.asset || {};
  const m = listing.metrics || {};
  const op = m.share_percent ?? listing.ownership_percent ?? listing.nft?.ownership_percent;
  const frozen = listing.nft?.frozen;
  const cat = CAT_LABEL[a.category];
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col hover:shadow-lg transition-shadow" data-testid={`share-card-${listing.id}`}>
      <div className="relative h-40 bg-muted">
        {a.cover_url
          ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" loading="lazy" />
          : <div className="w-full h-full bg-gradient-to-br from-emerald-100 to-sky-100 dark:from-emerald-950/40 dark:to-sky-950/40 flex items-center justify-center"><Building2 className="w-9 h-9 text-emerald-600/60" /></div>}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3">
          <h3 className="text-white font-semibold leading-tight text-[15px] drop-shadow">{a.title || listing.pool_id}</h3>
          {a.location && <p className="text-white/85 text-[11px] flex items-center gap-1 mt-0.5"><MapPin className="w-3 h-3" /> {a.location}</p>}
        </div>
        <div className="absolute top-2 left-2 flex gap-1.5">
          {cat && <span className="px-2 py-0.5 rounded-full bg-white/90 text-[10px] font-medium text-slate-700">{bi(cat.uk, cat.en)}</span>}
          {a.target_yield != null && <span className="px-2 py-0.5 rounded-full bg-emerald-600 text-white text-[10px] font-semibold">{PCT(a.target_yield)} {bi('річних', 'p.a.')}</span>}
        </div>
        {frozen && <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-medium flex items-center gap-1"><Lock className="w-3 h-3" /> {bi('заморожено', 'frozen')}</span>}
      </div>

      <div className="p-4 flex-1">
        <div className="grid grid-cols-3 gap-2 text-center">
          <Metric label={bi('Частка', 'Share')} value={PCT(op)} />
          <Metric label={bi('Дивіденди / рік', 'Dividends / yr')} value={USD(m.dividends_12m)} accent="emerald" />
          <Metric label={bi('Окупність', 'Payback')} value={m.payback_years ? `${m.payback_years} ${bi('р.', 'y')}` : '—'} />
        </div>
        {children}
      </div>
      {footer && <div className="px-4 py-3 border-t border-border bg-muted/20">{footer}</div>}
    </div>
  );
}
const Metric = ({ label, value, accent }) => (
  <div>
    <p className="text-[10px] uppercase tracking-wide text-token-muted leading-tight">{label}</p>
    <p className={`font-bold tabular-nums text-[15px] mt-0.5 ${accent === 'emerald' ? 'text-emerald-600' : ''}`}>{value}</p>
  </div>
);

/* ── 1. Market ──────────────────────────────────────────────────────────── */
function Market({ bi }) {
  const { lang } = useLang();
  const { data, loading, error, reload } = useApi('/investor/otc/listings');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const buy = async (l) => {
    setBusy(l.id); setNotice('');
    try { await lumen.post(`/investor/otc/listings/${l.id}/buy`, {}); setNotice(bi('Угоду створено. Перейдіть у «Мої угоди» для оплати.', 'Deal created. Go to "My deals" to pay.')); await reload(); }
    catch (e) { setNotice(lumenError(e)); }
    finally { setBusy(''); }
  };
  if (loading) return <Loading />;
  const rows = data?.listings || [];
  return (
    <div>
      <ErrBox msg={error} />
      {notice && <div className="mb-4 p-3 rounded-xl bg-muted/50 border border-border text-sm" data-testid="market-notice">{notice}</div>}
      <div className="flex justify-between items-center mb-3">
        <p className="text-sm text-token-muted">{rows.length} {bi('лотів у продажу', 'lots on sale')}</p>
        <Refresh onClick={reload} />
      </div>
      {!rows.length ? <Empty msg={bi('На ринку зараз немає часток у продажу.', 'No shares for sale on the market right now.')} /> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="market-grid">
          {rows.map((l) => (
            <ShareCard key={l.id} listing={l} bi={bi} lang={lang}
              footer={
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-[10px] uppercase text-token-muted">{bi('Ціна частки', 'Share price')}</p>
                    <p className="text-xl font-bold tabular-nums">{USD(l.price_usd)}</p>
                    {l.metrics?.roi_at_ask != null && <p className="text-[11px] text-emerald-600 font-medium">ROI {PCT(l.metrics.roi_at_ask)}</p>}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {l.is_mine
                      ? <span className="text-xs text-token-muted px-3 py-2 text-center">{bi('Ваш лот', 'Your listing')}</span>
                      : <button data-testid={`market-buy-${l.id}`} disabled={busy === l.id || l.nft?.frozen} onClick={() => buy(l)}
                          className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-40 flex items-center gap-2 justify-center">
                          <ShoppingCart className="w-4 h-4" /> {bi('Купити частку', 'Buy share')}
                        </button>}
                    <Link to={`/investor/otc/${l.id}`} data-testid={`market-detail-${l.id}`} className="text-[11px] text-center text-token-muted hover:text-foreground underline underline-offset-2">{bi('Деталі лоту →', 'Lot details →')}</Link>
                  </div>
                </div>
              } />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 1b. Reservations (lots bought from the public OTC market, then claimed) ── */
function Reservations({ bi }) {
  const { data, loading, error, reload } = useApi('/investor/otc/reservations');
  if (loading) return <Loading />;
  const rows = data?.reservations || [];
  const STATUS = {
    reserved: bi('зарезервовано', 'reserved'),
    claimed: bi('очікує фіналізації', 'awaiting settlement'),
    cancelled: bi('скасовано', 'cancelled'),
  };
  return (
    <div data-testid="otc-reservations">
      <ErrBox msg={error} />
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-token-muted">{bi('Частки, які ви придбали на публічному OTC-ринку.', 'Shares you bought on the public OTC market.')}</p>
        <Refresh onClick={reload} />
      </div>
      {!rows.length ? (
        <Empty msg={bi('Ви ще не купували часток на OTC-ринку.', 'You have not bought any OTC shares yet.')} />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="reservations-grid">
          {rows.map((r) => {
            const a = r.asset_snapshot || {};
            return (
              <div key={r.id} data-testid={`reservation-${r.id}`} className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col">
                <div className="relative h-36 bg-muted">
                  {a.cover_url
                    ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" loading="lazy" />
                    : <div className="w-full h-full flex items-center justify-center text-emerald-600/50"><Building2 className="w-9 h-9" /></div>}
                  <span className="absolute top-2 right-2 status-badge badge-info" style={{ fontSize: 11 }}>{STATUS[r.status] || r.status}</span>
                </div>
                <div className="p-4 flex-1">
                  <h3 className="font-semibold leading-tight">{a.title || bi('Частка в активі', 'Asset share')}</h3>
                  {a.location && <p className="mt-0.5 text-[11px] text-token-muted flex items-center gap-1"><MapPin className="w-3 h-3" /> {a.location}</p>}
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div><p className="text-[10px] uppercase text-token-muted">{bi('Ціна', 'Price')}</p><p className="font-bold tabular-nums">{USD(r.price_usd)}</p></div>
                    <div><p className="text-[10px] uppercase text-token-muted">{bi('Оплата', 'Payment')}</p><p className="font-medium capitalize">{r.payment_method === 'wallet' ? bi('Гаманець', 'Wallet') : bi('Баланс', 'Balance')}</p></div>
                  </div>
                  <p className="mt-3 text-[11px] text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" /> {bi('Менеджер LUMEN звʼяжеться для фіналізації угоди.', 'A LUMEN manager will reach out to finalise the deal.')}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


/* ── 2. Sell a share (pick from my assets) ──────────────────────────────── */
function Sell({ bi, onListed }) {
  const { data, loading, error, reload } = useApi('/investor/nft-certificates');
  const [priceFor, setPriceFor] = useState(null);
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const w = useWallet();

  const list = async (nft) => {
    if (!price || Number(price) <= 0) { setNotice(bi('Вкажіть ціну продажу', 'Enter a sale price')); return; }
    setBusy(true); setNotice('');
    try {
      await lumen.post('/investor/otc/listings', { nft_certificate_id: nft.id, price_usd: Number(price) });
      setPriceFor(null); setPrice('');
      setNotice(bi('Частку виставлено на OTC ринок ✓', 'Share listed on the OTC market ✓'));
      await reload(); w.refresh && w.refresh();
      onListed && onListed();
    } catch (e) { setNotice(lumenError(e)); }
    finally { setBusy(false); }
  };
  if (loading) return <Loading />;
  const sellable = (data?.nfts || []).filter((n) => ['minted', 'transferred'].includes(n.status) && !n.frozen);
  const frozen = (data?.nfts || []).filter((n) => n.frozen);
  return (
    <div data-testid="otc-sell">
      <ErrBox msg={error} />
      {notice && <div className="mb-4 p-3 rounded-xl bg-muted/50 border border-border text-sm" data-testid="sell-notice">{notice}</div>}
      {!sellable.length && !frozen.length ? (
        <Empty msg={bi('У вас немає часток, доступних для продажу.', 'You have no shares available to sell.')} />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sellable.map((n) => (
            <div key={n.id} data-testid={`sellable-${n.id}`} className="rounded-2xl border border-border bg-card p-4">
              <h3 className="font-semibold">{n.asset?.title || bi('Частка в активі', 'Asset share')}</h3>
              {n.asset?.location && <p className="text-[11px] text-token-muted flex items-center gap-1 mt-0.5"><MapPin className="w-3 h-3" /> {n.asset.location}</p>}
              <div className="mt-2 text-sm space-y-1">
                <div className="flex justify-between"><span className="text-token-muted text-xs">{bi('Частка', 'Share')}</span><span className="font-medium">{PCT(n.ownership_percent)}</span></div>
                <div className="flex justify-between"><span className="text-token-muted text-xs">{bi('Юніти', 'Units')}</span><span className="font-medium">{n.units}</span></div>
              </div>
              {priceFor === n.id ? (
                <div className="mt-3 flex gap-2">
                  <input data-testid={`sell-price-${n.id}`} value={price} onChange={(e) => setPrice(e.target.value)} type="number" placeholder="USD"
                    className="flex-1 px-2 py-1.5 rounded-lg border border-border bg-app text-sm" />
                  <button data-testid={`sell-confirm-${n.id}`} disabled={busy} onClick={() => list(n)} className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs">{bi('Виставити', 'List')}</button>
                  <button onClick={() => { setPriceFor(null); setPrice(''); }} className="px-2 py-1.5 rounded-lg border border-border text-xs">✕</button>
                </div>
              ) : (
                <button data-testid={`sell-start-${n.id}`} onClick={() => setPriceFor(n.id)} className="mt-3 w-full px-3 py-2 rounded-xl bg-card border border-border text-sm hover:bg-muted/60 flex items-center justify-center gap-2">
                  <Tag className="w-4 h-4" /> {bi('Виставити на продаж', 'List for sale')}
                </button>
              )}
            </div>
          ))}
          {frozen.map((n) => (
            <div key={n.id} className="rounded-2xl border border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 p-4">
              <h3 className="font-semibold">{n.asset?.title || bi('Частка в активі', 'Asset share')}</h3>
              <p className="mt-3 text-xs text-amber-700 flex items-center gap-1.5"><Lock className="w-3.5 h-3.5" /> {bi('Заморожено — недоступно для продажу', 'Frozen — not available to sell')}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 3. My listings ─────────────────────────────────────────────────────── */
function MyListings({ bi }) {
  const { data, loading, error, reload } = useApi('/investor/otc/my-listings');
  const cancel = async (id) => { try { await lumen.delete(`/investor/otc/listings/${id}`); await reload(); } catch (e) { alert(lumenError(e)); } };
  if (loading) return <Loading />;
  const rows = data?.listings || [];
  return (
    <div>
      <ErrBox msg={error} />
      <div className="flex justify-end mb-3"><Refresh onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Ви ще нічого не продаєте.', 'You are not selling anything yet.')} /> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="my-listings-grid">
          {rows.map((l) => (
            <ShareCard key={l.id} listing={l} bi={bi}
              footer={
                <div className="flex items-center justify-between gap-2">
                  <div><p className="text-[10px] uppercase text-token-muted">{bi('Ціна', 'Price')}</p><p className="text-lg font-bold tabular-nums">{USD(l.price_usd)}</p></div>
                  <div className="flex items-center gap-2">
                    <Pill s={l.status} />
                    {['draft', 'active'].includes(l.status) && (
                      <button data-testid={`cancel-listing-${l.id}`} onClick={() => cancel(l.id)} className="px-2.5 py-1.5 rounded-lg border border-rose-200 text-rose-700 text-xs hover:bg-rose-50 flex items-center gap-1"><XCircle className="w-3.5 h-3.5" /> {bi('Зняти', 'Cancel')}</button>
                    )}
                  </div>
                </div>
              } />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 4. My offers ───────────────────────────────────────────────────────── */
function MyOffers({ bi }) {
  const { data, loading, error, reload } = useApi('/investor/otc/my-offers');
  if (loading) return <Loading />;
  const rows = data?.offers || [];
  return (
    <div>
      <ErrBox msg={error} />
      <div className="flex justify-end mb-3"><Refresh onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Ви ще не робили пропозицій.', 'You have not made any offers yet.')} /> : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="my-offers-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr><th className="px-3 py-2 text-left">{bi('Об’єкт', 'Object')}</th><th className="px-3 py-2 text-right">{bi('Пропозиція', 'Offer')}</th><th className="px-3 py-2 text-left">{bi('Статус', 'Status')}</th><th className="px-3 py-2 text-left">{bi('Дата', 'Date')}</th></tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {rows.map((o) => (
                <tr key={o.id} data-testid={`offer-row-${o.id}`} className="hover:bg-muted/20">
                  <td className="px-3 py-2">{o.asset?.title || o.pool_id || o.nft_certificate_id?.slice(0, 10)}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">{USD(o.offer_price_usd)}</td>
                  <td className="px-3 py-2"><Pill s={o.status} /></td>
                  <td className="px-3 py-2 text-[11px] text-token-muted">{formatDateUk(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── 5/6. My deals + History ────────────────────────────────────────────── */
function MyDeals({ bi, terminal }) {
  const { data, loading, error, reload } = useApi('/investor/otc/my-deals');
  const [busy, setBusy] = useState('');
  const pay = async (d) => {
    setBusy(d.id);
    try { await lumen.post(`/investor/otc/deals/${d.id}/payment-proof`, { method: 'bank_transfer', amount: d.price_usd, currency: d.currency || 'USD', comment: 'paid' }); await reload(); }
    catch (e) { alert(lumenError(e)); } finally { setBusy(''); }
  };
  const cancel = async (id) => { setBusy(id); try { await lumen.post(`/investor/otc/deals/${id}/cancel`); await reload(); } catch (e) { alert(lumenError(e)); } finally { setBusy(''); } };
  if (loading) return <Loading />;
  const all = data?.deals || [];
  const TERM = ['completed', 'cancelled', 'disputed'];
  const rows = all.filter((d) => terminal ? TERM.includes(d.status) : !TERM.includes(d.status));
  return (
    <div>
      <ErrBox msg={error} />
      <div className="flex justify-end mb-3"><Refresh onClick={reload} /></div>
      {!rows.length ? <Empty msg={terminal ? bi('Історія угод порожня.', 'Deal history is empty.') : bi('Активних угод немає.', 'No active deals.')} /> : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid={terminal ? 'history-table' : 'deals-table'}>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="px-3 py-2 text-left">{bi('Роль', 'Role')}</th>
                <th className="px-3 py-2 text-left">{bi('Об’єкт', 'Object')}</th>
                <th className="px-3 py-2 text-right">{bi('Сума', 'Amount')}</th>
                <th className="px-3 py-2 text-left">{bi('Оплата', 'Payment')}</th>
                <th className="px-3 py-2 text-left">{bi('Статус', 'Status')}</th>
                {!terminal && <th className="px-3 py-2 text-left">{bi('Дії', 'Actions')}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {rows.map((d) => (
                <tr key={d.id} data-testid={`deal-row-${d.id}`} className="hover:bg-muted/20">
                  <td className="px-3 py-2"><span className="status-badge badge-neutral" style={{ fontSize: 10 }}>{d.role === 'buyer' ? bi('покупець', 'buyer') : bi('продавець', 'seller')}</span></td>
                  <td className="px-3 py-2">{d.asset?.title || d.pool_id || '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">{USD(d.price_usd)}</td>
                  <td className="px-3 py-2"><Pill s={d.payment_status} /></td>
                  <td className="px-3 py-2"><Pill s={d.status} /></td>
                  {!terminal && (
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1.5">
                        {d.role === 'buyer' && d.status === 'payment_pending' && d.payment_status === 'pending' && (
                          <button data-testid={`deal-pay-${d.id}`} disabled={busy === d.id} onClick={() => pay(d)} className="px-2 py-1 rounded-lg border border-emerald-200 text-emerald-700 text-[11px] hover:bg-emerald-50 flex items-center gap-1"><Upload className="w-3 h-3" /> {bi('Підтвердити оплату', 'Submit payment')}</button>
                        )}
                        {!['completed', 'cancelled', 'disputed'].includes(d.status) && d.payment_status !== 'confirmed' && (
                          <button data-testid={`deal-cancel-${d.id}`} disabled={busy === d.id} onClick={() => cancel(d.id)} className="px-2 py-1 rounded-lg border border-rose-200 text-rose-700 text-[11px] hover:bg-rose-50 flex items-center gap-1"><XCircle className="w-3 h-3" /> {bi('Скасувати', 'Cancel')}</button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
