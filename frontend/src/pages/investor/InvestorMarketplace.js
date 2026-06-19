import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  ShoppingBag, Tag, Wallet, Loader2, Plus, X, Building2,
  TrendingUp, AlertCircle, ArrowLeftRight, History, Check, Ban, RefreshCw,
} from 'lucide-react';

const STATUS_BADGE = {
  active:           { label: 'Активний',     cls: 'bg-emerald-100 text-emerald-800' },
  partially_filled: { label: 'Частково вик',cls: 'bg-sky-100 text-sky-800' },
  filled:           { label: 'Викуплений',   cls: 'bg-indigo-100 text-indigo-800' },
  cancelled:        { label: 'Скасовано',   cls: 'bg-muted text-muted-foreground' },
  expired:          { label: 'Сплив',         cls: 'bg-muted text-muted-foreground' },
  settled:          { label: 'Закритий',     cls: 'bg-emerald-100 text-emerald-800' },
  pending:          { label: 'В обробці',     cls: 'bg-amber-100 text-amber-800' },
  failed:           { label: 'Помилка',       cls: 'bg-red-100 text-red-700' },
  accepted:         { label: 'Прийнято',     cls: 'bg-emerald-100 text-emerald-800' },
  rejected:         { label: 'Відхилено',   cls: 'bg-red-100 text-red-700' },
};
const badgeFor = (s) => STATUS_BADGE[s] || { label: s, cls: 'bg-muted text-muted-foreground' };

export default function InvestorMarketplace() {
  const [tab, setTab] = useState('browse');
  return (
    <div className="p-4 md:p-10 max-w-6xl mx-auto" data-testid="investor-marketplace">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 13 · Secondary Market</p>
        <h1 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight">Вторинний ринок</h1>
        <p className="mt-1 text-token-muted text-sm">Купуйте та продавайте частки інвесторів безпосередньо в середині LUMEN.</p>
        <p className="mt-2 text-xs text-token-muted" data-testid="marketplace-terms-link">
          Операції регулюються{' '}
          <Link to="/legal/secondary-market" target="_blank" className="text-[#2E5D4F] hover:underline font-medium">
            Умовами вторинного ринку
          </Link>. Комісія платформи утримується з продавця під час угоди.
        </p>
      </header>

      <nav className="flex flex-wrap gap-1 mb-6 p-1 bg-muted/40 rounded-xl">
        {[
          { key: 'browse',  label: 'Огляд', icon: ShoppingBag },
          { key: 'holdings',label: 'Мої частки', icon: Building2 },
          { key: 'listings',label: 'Мої лістинги', icon: Tag },
          { key: 'bids',    label: 'Мої офери', icon: ArrowLeftRight },
          { key: 'trades',  label: 'Угоди', icon: History },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`flex-1 sm:flex-none px-3 py-2 rounded-lg text-xs sm:text-sm flex items-center justify-center gap-1.5 transition ${tab===t.key ? 'bg-card shadow-sm text-foreground font-semibold':'text-token-muted'}`}
              data-testid={`tab-${t.key}`}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </nav>

      {tab === 'browse'   && <BrowseTab />}
      {tab === 'holdings' && <HoldingsTab />}
      {tab === 'listings' && <ListingsTab />}
      {tab === 'bids'     && <BidsTab />}
      {tab === 'trades'   && <TradesTab />}
    </div>
  );
}

// =================== BROWSE TAB ===================
function BrowseTab() {
  const [items, setItems] = useState([]);
  const [feePct, setFeePct] = useState(0.01);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [selected, setSelected] = useState(null);
  const [units, setUnits] = useState('');
  const [offerPrice, setOfferPrice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/secondary/listings');
      setItems(r.data?.items || []);
      setFeePct(r.data?.platform_fee_pct || 0.01);
    } catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async (mode) => {
    if (!selected) return;
    setBusy(selected.id); setError('');
    try {
      const body = { listing_id: selected.id, units_uah: parseFloat(units) };
      if (mode === 'offer') body.price_per_unit = parseFloat(offerPrice);
      const r = await lumen.post('/investor/secondary/bids', body);
      alert(mode === 'buy_now'
        ? `Угоду закрито! Отримано ${formatUAH(r.data?.trade?.units_uah || 0)} частки.`
        : `Офер надіслано продавцю.`);
      setSelected(null); setUnits(''); setOfferPrice('');
      await load();
    } catch (e) { setError(lumenError(e)); }
    finally { setBusy(''); }
  };

  if (loading) return <SkeletonList />;
  if (!items.length) return <EmptyState icon={ShoppingBag} text="Наразі немає активних лістингів" />;

  return (
    <>
      {error && <ErrorBox>{error}</ErrorBox>}
      <div className="grid sm:grid-cols-2 gap-3">
        {items.map(L => {
          const remaining = (L.units_uah || 0) - (L.filled_units_uah || 0);
          const b = badgeFor(L.status);
          return (
            <div key={L.id} className="rounded-2xl border border-border bg-card p-4 hover:bg-muted/20 transition" data-testid={`listing-${L.id}`}>
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{L.asset?.title || L.asset_id}</p>
                  <p className="text-xs text-token-muted">{L.seller_label}</p>
                </div>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs mb-3">
                <div><p className="text-token-muted">Доступно</p><p className="font-bold tabular-nums">{formatUAH(remaining)}</p></div>
                <div><p className="text-token-muted">Ціна</p><p className="font-bold tabular-nums">{(L.price_per_unit || 1).toFixed(3)}×</p></div>
                <div><p className="text-token-muted">До</p><p className="font-medium">{formatDateUk(L.expires_at)}</p></div>
              </div>
              <button onClick={() => { setSelected(L); setUnits(String(Math.min(remaining, 10000))); setOfferPrice(String(L.price_per_unit)); }}
                className="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90"
                data-testid={`btn-open-${L.id}`}>
                Купити або зробити офер
              </button>
            </div>
          );
        })}
      </div>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-2" onClick={() => setSelected(null)}>
          <div className="bg-card rounded-t-2xl sm:rounded-2xl w-full max-w-md p-5" onClick={e => e.stopPropagation()} data-testid="buy-modal">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold">{selected.asset?.title}</h3>
              <button onClick={() => setSelected(null)} className="p-1 hover:bg-muted rounded"><X className="w-4 h-4" /></button>
            </div>
            <div className="text-xs text-token-muted mb-3">
              Доступно: <strong>{formatUAH((selected.units_uah || 0) - (selected.filled_units_uah || 0))}</strong> · Ціна за одиницю: <strong>{(selected.price_per_unit || 1).toFixed(3)}</strong>
            </div>
            <label className="block text-xs text-token-muted mb-1">Обсяг частки (USDT-номінал)</label>
            <input type="number" step="0.01" value={units} onChange={e => setUnits(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm mb-3" data-testid="input-units" />
            <div className="text-[11px] text-token-muted mb-3">
              До сплати: <strong className="tabular-nums">{formatUAH(parseFloat(units || '0') * (selected.price_per_unit || 1))}</strong>
              {feePct > 0 && <span> (комісія платформи {(feePct*100).toFixed(2)}%)</span>}
            </div>
            <button onClick={() => submit('buy_now')} disabled={busy === selected.id || !units}
              className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground font-medium mb-2 disabled:opacity-50"
              data-testid="btn-buy-now">
              {busy === selected.id ? <Loader2 className="w-4 h-4 animate-spin inline" /> : `Купити зараз`}
            </button>
            <details className="mt-2">
              <summary className="text-xs text-token-muted cursor-pointer">Або зробити офер з нижчою ціною</summary>
              <div className="mt-2 space-y-2">
                <input type="number" step="0.001" placeholder="Ціна за одиницю" value={offerPrice}
                  onChange={e => setOfferPrice(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm" data-testid="input-offer-price" />
                <button onClick={() => submit('offer')} disabled={busy === selected.id || !offerPrice}
                  className="w-full py-2 rounded-lg border border-border bg-card text-sm hover:bg-muted/30 disabled:opacity-50"
                  data-testid="btn-make-offer">
                  Запропонувати ціну
                </button>
              </div>
            </details>
          </div>
        </div>
      )}
    </>
  );
}

// =================== HOLDINGS TAB ===================
function HoldingsTab() {
  const [data, setData] = useState({ items: [], min_listing_uah: 100 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ units_uah: '', price_per_unit: '1.0', expires_in_days: 30 });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/investor/secondary/holdings');
      setData(r.data || { items: [] });
    } catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await lumen.post('/investor/secondary/listings', {
        asset_id: selected.asset_id,
        units_uah: parseFloat(form.units_uah),
        price_per_unit: parseFloat(form.price_per_unit),
        expires_in_days: parseInt(form.expires_in_days),
      });
      setSelected(null);
      setForm({ units_uah: '', price_per_unit: '1.0', expires_in_days: 30 });
      await load();
    } catch (err) { setError(lumenError(err)); }
    finally { setBusy(false); }
  };

  if (loading) return <SkeletonList />;
  if (!data.items.length) return <EmptyState icon={Building2} text="У вас поки немає часток для продажу" />;

  return (
    <>
      {error && <ErrorBox>{error}</ErrorBox>}
      <div className="space-y-2">
        {data.items.map(h => (
          <div key={h.asset_id} className="p-4 rounded-2xl border border-border bg-card" data-testid={`holding-${h.asset_id}`}>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="min-w-0">
                <p className="font-semibold truncate">{h.asset_title}</p>
                <p className="text-xs text-token-muted">{h.category}</p>
              </div>
              <button onClick={() => { setSelected(h); setForm({ units_uah: '', price_per_unit: '1.0', expires_in_days: 30 }); }}
                disabled={h.available_uah < (data.min_listing_uah || 100)}
                className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium disabled:opacity-50"
                data-testid={`btn-list-${h.asset_id}`}>
                <Plus className="w-3 h-3 inline mr-1" /> Виставити на продаж
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><p className="text-token-muted">Володіння</p><p className="font-bold tabular-nums">{formatUAH(h.owned_uah)}</p></div>
              <div><p className="text-token-muted">Виставлено</p><p className="font-medium tabular-nums">{formatUAH(h.listed_uah)}</p></div>
              <div><p className="text-token-muted">Доступно</p><p className="font-bold tabular-nums text-emerald-700">{formatUAH(h.available_uah)}</p></div>
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-2" onClick={() => setSelected(null)}>
          <form onSubmit={submit} className="bg-card rounded-t-2xl sm:rounded-2xl w-full max-w-md p-5" onClick={e => e.stopPropagation()} data-testid="list-form">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold">Виставити частку на продаж</h3>
              <button type="button" onClick={() => setSelected(null)} className="p-1 hover:bg-muted rounded"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-token-muted mb-3">{selected.asset_title}<br />Доступно: <strong>{formatUAH(selected.available_uah)}</strong></p>
            <label className="block text-xs text-token-muted mb-1">Обсяг частки (USDT-номінал)</label>
            <input required type="number" min={data.min_listing_uah} max={selected.available_uah} step="0.01" value={form.units_uah} onChange={e => setForm(s => ({...s, units_uah: e.target.value}))} className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm mb-3" data-testid="input-list-units" />
            <label className="block text-xs text-token-muted mb-1">Ціна за одиницю (1.0 = номінал)</label>
            <input required type="number" min="0.5" max="3" step="0.001" value={form.price_per_unit} onChange={e => setForm(s => ({...s, price_per_unit: e.target.value}))} className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm mb-3" data-testid="input-list-price" />
            <label className="block text-xs text-token-muted mb-1">Діє днів</label>
            <input required type="number" min="1" max="180" value={form.expires_in_days} onChange={e => setForm(s => ({...s, expires_in_days: e.target.value}))} className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm mb-4" data-testid="input-list-expires" />
            <button type="submit" disabled={busy} className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground font-medium disabled:opacity-50" data-testid="btn-submit-list">
              {busy ? <Loader2 className="w-4 h-4 animate-spin inline" /> : 'Опублікувати'}
            </button>
          </form>
        </div>
      )}
    </>
  );
}

// =================== LISTINGS TAB ===================
function ListingsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/investor/secondary/my-listings'); setItems(r.data?.items || []); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const cancel = async (id) => {
    if (!window.confirm('Скасувати лістинг?')) return;
    setBusy(id);
    try { await lumen.post(`/investor/secondary/listings/${id}/cancel`); await load(); }
    finally { setBusy(''); }
  };
  if (loading) return <SkeletonList />;
  if (!items.length) return <EmptyState icon={Tag} text="Ви ще не створили жодного лістингу" />;
  return (
    <div className="space-y-2">
      {items.map(L => {
        const b = badgeFor(L.status);
        const remaining = (L.units_uah || 0) - (L.filled_units_uah || 0);
        return (
          <div key={L.id} className="p-4 rounded-2xl border border-border bg-card" data-testid={`my-listing-${L.id}`}>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="min-w-0">
                <p className="font-semibold truncate">{L.asset_title}</p>
                <p className="text-xs text-token-muted">Створено {formatDateUk(L.created_at)} · до {formatDateUk(L.expires_at)}</p>
              </div>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
            </div>
            <div className="grid grid-cols-4 gap-2 text-xs mb-3">
              <div><p className="text-token-muted">Сума</p><p className="font-bold tabular-nums">{formatUAH(L.units_uah)}</p></div>
              <div><p className="text-token-muted">Викуплено</p><p className="font-medium tabular-nums">{formatUAH(L.filled_units_uah)}</p></div>
              <div><p className="text-token-muted">Лишилось</p><p className="font-medium tabular-nums">{formatUAH(remaining)}</p></div>
              <div><p className="text-token-muted">Оферів</p><p className="font-medium">{L.active_bids}</p></div>
            </div>
            {['active', 'partially_filled', 'draft'].includes(L.status) && (
              <button onClick={() => cancel(L.id)} disabled={busy === L.id}
                className="text-xs px-3 py-1.5 rounded-lg border border-red-200 text-red-700 hover:bg-red-50 disabled:opacity-50" data-testid={`btn-cancel-${L.id}`}>
                <Ban className="w-3 h-3 inline mr-1" /> Скасувати
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

// =================== BIDS TAB ===================
function BidsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/investor/secondary/my-bids'); setItems(r.data?.items || []); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const cancel = async (id) => {
    setBusy(id);
    try { await lumen.post(`/investor/secondary/bids/${id}/cancel`); await load(); }
    finally { setBusy(''); }
  };
  if (loading) return <SkeletonList />;
  if (!items.length) return <EmptyState icon={ArrowLeftRight} text="Ви ще не робили жодних оферів" />;
  return (
    <div className="space-y-2">
      {items.map(b => {
        const badge = badgeFor(b.status);
        return (
          <div key={b.id} className="p-3 rounded-2xl border border-border bg-card flex items-center justify-between gap-3" data-testid={`my-bid-${b.id}`}>
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{formatUAH(b.units_uah)} @ {(b.price_per_unit||1).toFixed(3)}×</p>
              <p className="text-xs text-token-muted">{formatDateUk(b.created_at)}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span>
              {b.status === 'active' && (
                <button onClick={() => cancel(b.id)} disabled={busy === b.id} className="text-[10px] px-2 py-0.5 rounded border border-red-200 text-red-700" data-testid={`btn-cancel-bid-${b.id}`}>Скасувати</button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// =================== TRADES TAB ===================
function TradesTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    lumen.get('/investor/secondary/my-trades').then(r => setItems(r.data?.items || [])).finally(() => setLoading(false));
  }, []);
  if (loading) return <SkeletonList />;
  if (!items.length) return <EmptyState icon={History} text="Ще не було жодних угод" />;
  return (
    <div className="space-y-2">
      {items.map(t => {
        const badge = badgeFor(t.status);
        return (
          <div key={t.id} className="p-4 rounded-2xl border border-border bg-card" data-testid={`my-trade-${t.id}`}>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="min-w-0">
                <p className="font-semibold truncate">{t.asset_title}</p>
                <p className="text-xs text-token-muted">{t.role === 'buyer' ? 'Покупка' : 'Продаж'} · {formatDateUk(t.created_at)}</p>
              </div>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><p className="text-token-muted">Частка</p><p className="font-bold tabular-nums">{formatUAH(t.units_uah)}</p></div>
              <div><p className="text-token-muted">Сума</p><p className="font-bold tabular-nums">{formatUAH(t.gross_uah)}</p></div>
              <div><p className="text-token-muted">{t.role==='seller'?'Отримано':'Комісія'}</p><p className="font-medium tabular-nums">{formatUAH(t.role==='seller'?t.seller_net_uah:t.fee_uah)}</p></div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const SkeletonList = () => <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="h-24 rounded-2xl bg-muted/40 animate-pulse" />)}</div>;
const EmptyState = ({ icon: Icon, text }) => (
  <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="marketplace-empty">
    <Icon className="w-10 h-10 mx-auto text-token-muted/60 mb-3" />
    <p className="text-sm text-token-muted">{text}</p>
  </div>
);
const ErrorBox = ({ children }) => <div className="mb-3 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{children}</div>;
