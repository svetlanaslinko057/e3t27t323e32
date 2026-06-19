import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatUAH, formatUSD, usdFromUah, lumenError } from '@/lib/lumenApi';
import {
  Activity, Star, ArrowDownUp, TrendingUp, TrendingDown, Minus, Loader2,
  ArrowUpRight, ArrowDownRight, Repeat, Wallet, ListOrderedIcon, X, Gauge,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';

const fmtUnits = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });
const fmtPrice = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : formatUSD(usdFromUah(n), { decimals: 2 });
const fmtPct = (n, sign = true) => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const v = Number(n); const s = sign && v > 0 ? '+' : '';
  return `${s}${v.toFixed(1).replace('.', ',')}%`;
};

function Pill({ pct }) {
  if (pct === null || pct === undefined) return null;
  const up = pct > 0.05, down = pct < -0.05;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const cls = up ? 'bg-emerald-100 text-emerald-700'
    : down ? 'bg-rose-100 text-rose-700' : 'bg-muted text-muted-foreground';
  return <span className={`inline-flex items-center gap-0.5 text-xs px-2 py-0.5 rounded-full font-semibold ${cls}`}><Icon className="w-3 h-3" />{fmtPct(pct)}</span>;
}

const ORDER_STATUS = {
  open: { label: 'Активна', cls: 'bg-sky-100 text-sky-700' },
  partial: { label: 'Частково', cls: 'bg-amber-100 text-amber-700' },
  filled: { label: 'Виконана', cls: 'bg-emerald-100 text-emerald-700' },
  cancelled: { label: 'Скасована', cls: 'bg-muted text-muted-foreground' },
  expired: { label: 'Прострочена', cls: 'bg-muted text-muted-foreground' },
};

const ACT = {
  trade: { icon: Repeat, verb: 'Продано' },
  listing: { icon: ArrowUpRight, verb: 'Виставлено' },
  bid: { icon: ArrowDownRight, verb: 'Заявка на' },
  payout: { icon: Wallet, verb: 'Виплата' },
};

export default function LiquidityCenter() {
  const [watchlist, setWatchlist] = useState([]);
  const [orders, setOrders] = useState([]);
  const [activity, setActivity] = useState([]);
  const [feed, setFeed] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [w, o, a, f] = await Promise.all([
        lumen.get('/investor/watchlist'),
        lumen.get('/investor/liquidity/orders'),
        lumen.get('/liquidity/activity?limit=20'),
        lumen.get('/investor/watchlist/feed'),
      ]);
      setWatchlist(w.data.items || []);
      setOrders(o.data.items || []);
      setActivity(a.data.items || []);
      setFeed(f.data.items || []);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const cancelOrder = async (id) => {
    try { await lumen.post(`/investor/liquidity/orders/${id}/cancel`); load(); }
    catch (_e) { /* noop */ }
  };

  const unwatch = async (aid) => {
    try { await lumen.delete(`/investor/watchlist/${aid}`); load(); }
    catch (_e) { /* noop */ }
  };

  if (loading) {
    return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  }

  const openOrders = orders.filter((o) => ['open', 'partial'].includes(o.status));

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="liquidity-center">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Liquidity OS</div>
        <h1 className="text-2xl font-bold">Центр ліквідності</h1>
        <p className="text-muted-foreground text-sm mt-1">Стеження за активами, ваші заявки та живий ринок часток.</p>
      </div>

      {/* watchlist */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <Star className="w-4 h-4" style={{ color: PRIMARY }} />
          <h2 className="font-semibold">Список стеження</h2>
          <span className="text-xs text-muted-foreground">({watchlist.length})</span>
        </div>
        {watchlist.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Ви ще не стежите за об'єктами. Відкрийте об'єкт → вкладка «Ліквідність» → «Стежити».
          </p>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="watchlist-grid">
            {watchlist.map((w) => (
              <div key={w.asset_id} className="rounded-xl border border-border overflow-hidden group">
                {w.cover_url && (
                  <div className="h-20 bg-cover bg-center" style={{ backgroundImage: `url(${w.cover_url})` }} />
                )}
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/investor/assets/${w.asset_id}`} className="font-medium text-sm hover:underline line-clamp-1">{w.asset_title}</Link>
                    <button onClick={() => unwatch(w.asset_id)} className="text-muted-foreground hover:text-rose-600 shrink-0">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="font-semibold">{fmtPrice(w.indicative_price_uah)}</span>
                    <Pill pct={w.premium_discount_pct} />
                  </div>
                  <div className="flex justify-between text-[11px] text-muted-foreground mt-1">
                    <span>Bid {w.best_bid ? fmtPrice(w.best_bid * (w.indicative_price_uah / (w.best_ask || w.best_bid || 1))) : '—'}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* my orders */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <ArrowDownUp className="w-4 h-4" style={{ color: PRIMARY }} />
          <h2 className="font-semibold">Мої заявки</h2>
          <span className="text-xs text-muted-foreground">({openOrders.length} активних)</span>
        </div>
        {orders.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">Заявок ще немає.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="my-orders-table">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="text-left py-2">Об'єкт</th>
                  <th className="text-left">Тип</th>
                  <th className="text-right">Units</th>
                  <th className="text-right">Ліміт</th>
                  <th className="text-center">Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const st = ORDER_STATUS[o.status] || ORDER_STATUS.open;
                  return (
                    <tr key={o.id} className="border-b border-border/50">
                      <td className="py-2"><Link to={`/investor/assets/${o.asset_id}`} className="hover:underline">{o.asset_title || o.asset_id}</Link></td>
                      <td><span className="text-emerald-700 font-medium">Купівля</span></td>
                      <td className="text-right tabular-nums">{formatUAH(o.units_uah)}</td>
                      <td className="text-right tabular-nums">×{Number(o.limit_price).toFixed(2)}</td>
                      <td className="text-center"><span className={`text-xs px-2 py-0.5 rounded-full ${st.cls}`}>{st.label}</span></td>
                      <td className="text-right">
                        {['open', 'partial'].includes(o.status) && (
                          <button onClick={() => cancelOrder(o.id)} className="text-xs text-rose-600 hover:underline">Скасувати</button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* global activity */}
        <section className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4" style={{ color: PRIMARY }} />
            <h2 className="font-semibold">Ринкова активність</h2>
          </div>
          <div className="space-y-2" data-testid="global-activity">
            {activity.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">Поки тихо.</p>}
            {activity.map((it, i) => {
              const meta = ACT[it.type] || ACT.trade; const Icon = meta.icon;
              return (
                <Link to={`/investor/assets/${it.asset_id}`} key={i}
                  className="flex items-center gap-3 text-sm py-1.5 border-b border-border/50 last:border-0 hover:bg-muted/40 rounded px-1 -mx-1">
                  <span className="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0"><Icon className="w-3.5 h-3.5 text-muted-foreground" /></span>
                  <div className="flex-1 min-w-0">
                    <div className="line-clamp-1">{it.asset_title}</div>
                    <div className="text-xs text-muted-foreground">{meta.verb} {fmtUnits(it.units)} units · {fmtPrice(it.price_uah)}</div>
                  </div>
                  {it.premium_pct != null && it.type !== 'payout' && <Pill pct={it.premium_pct} />}
                </Link>
              );
            })}
          </div>
        </section>

        {/* watchlist feed */}
        <section className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 mb-4">
            <Star className="w-4 h-4" style={{ color: PRIMARY }} />
            <h2 className="font-semibold">Стрічка обраного</h2>
          </div>
          <div className="space-y-2" data-testid="watchlist-feed">
            {feed.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">Додайте об'єкти у стеження, щоб бачити події.</p>}
            {feed.map((it, i) => {
              const meta = ACT[it.type] || ACT.trade; const Icon = meta.icon;
              return (
                <div key={i} className="flex items-center gap-3 text-sm py-1.5 border-b border-border/50 last:border-0">
                  <span className="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0"><Icon className="w-3.5 h-3.5 text-muted-foreground" /></span>
                  <div className="flex-1 min-w-0">
                    <div className="line-clamp-1">{it.asset_title}</div>
                    <div className="text-xs text-muted-foreground">
                      {it.type === 'payout'
                        ? `Виплата ${formatUAH(it.amount_uah)}`
                        : `${meta.verb} ${fmtUnits(it.units)} units · ${fmtPrice(it.price_uah)}`}
                    </div>
                  </div>
                  {it.premium_pct != null && it.type !== 'payout' && <Pill pct={it.premium_pct} />}
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
