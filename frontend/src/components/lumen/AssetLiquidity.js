import { useEffect, useState, useCallback, useMemo } from 'react';
import { lumen, formatUAH, formatUSD, usdFromUah, lumenError } from '@/lib/lumenApi';
import {
  Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import {
  TrendingUp, TrendingDown, Activity, ArrowDownUp, Scale, Gauge, Star,
  ArrowUpRight, ArrowDownRight, Minus, LogIn, Loader2, ShieldCheck, Layers,
  Users, BarChart3, Wallet, Megaphone, Repeat, Info, Sparkles,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';
const UP = '#10b981';
const DOWN = '#ef4444';

/* ─────────────────────────── helpers ─────────────────────────── */

const fmtUnits = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });
const fmtPrice = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : formatUSD(usdFromUah(n), { decimals: 2 });
const fmtPct = (n, withSign = true) => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const v = Number(n);
  const s = withSign && v > 0 ? '+' : '';
  return `${s}${v.toFixed(1).replace('.', ',')}%`;
};

function PremiumPill({ pct, size = 'sm' }) {
  if (pct === null || pct === undefined) return null;
  const up = pct > 0.05, down = pct < -0.05;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const cls = up ? 'bg-emerald-100 text-emerald-700'
    : down ? 'bg-rose-100 text-rose-700' : 'bg-muted text-muted-foreground';
  const pad = size === 'lg' ? 'text-sm px-2.5 py-1' : 'text-xs px-2 py-0.5';
  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-semibold ${cls} ${pad}`}>
      <Icon className="w-3.5 h-3.5" />{fmtPct(pct)}
    </span>
  );
}

const SENTIMENT_TONE = {
  bullish: { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: TrendingUp },
  bearish: { cls: 'bg-rose-100 text-rose-700 border-rose-200', icon: TrendingDown },
  neutral: { cls: 'bg-muted text-muted-foreground border-border', icon: Minus },
};

/* ─────────────────────────── data hook ─────────────────────────── */

export function useLiquidity(assetId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!assetId) return;
    try {
      const r = await lumen.get(`/assets/${assetId}/liquidity-bundle`);
      setData(r.data);
    } catch (_e) {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => { setLoading(true); load(); }, [load]);
  return { data, loading, reload: load };
}

/* compact score badges for cards/headers */
export function MarketPriceBadge({ assetId }) {
  const [mp, setMp] = useState(null);
  useEffect(() => {
    let on = true;
    lumen.get(`/assets/${assetId}/market-price`).then((r) => on && setMp(r.data)).catch(() => {});
    return () => { on = false; };
  }, [assetId]);
  if (!mp) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">Ринок</span>
      <span className="font-semibold">{fmtPrice(mp.indicative_price_uah)}</span>
      <PremiumPill pct={mp.premium_discount_pct} />
    </span>
  );
}

/* ═══════════════════════ price chart ═══════════════════════ */

function PriceChart({ history, base }) {
  const series = useMemo(() => {
    const pts = (history?.daily || []).map((d) => ({
      date: d.date?.slice(5),
      price: d.vwap_uah,
    }));
    return pts;
  }, [history]);

  if (!series.length) {
    return (
      <div className="h-44 flex items-center justify-center text-sm text-muted-foreground">
        Ще немає історії угод для побудови графіка
      </div>
    );
  }
  const first = series[0]?.price ?? base;
  const last = series[series.length - 1]?.price ?? base;
  const up = last >= first;
  const color = up ? UP : DOWN;
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={series} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="liqGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
               axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis domain={['dataMin', 'dataMax']} tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
               axisLine={false} tickLine={false} width={52}
               tickFormatter={(v) => `${Math.round(v)}`} />
        <Tooltip
          formatter={(v) => [fmtPrice(v), 'VWAP']}
          contentStyle={{ borderRadius: 12, border: '1px solid hsl(var(--border))',
                          background: 'hsl(var(--background))', fontSize: 12 }}
        />
        <Area type="monotone" dataKey="price" stroke={color} strokeWidth={2}
              fill="url(#liqGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/* ═══════════════════════ order book ═══════════════════════ */

function OrderBook({ ob }) {
  const maxUnits = Math.max(
    1,
    ...(ob.asks || []).map((l) => l.units_uah),
    ...(ob.bids || []).map((l) => l.units_uah),
  );
  const Row = ({ level, side }) => {
    const pct = Math.min(100, (level.units_uah / maxUnits) * 100);
    const barCls = side === 'bid' ? 'bg-emerald-500/15' : 'bg-rose-500/15';
    const priceCls = side === 'bid' ? 'text-emerald-600' : 'text-rose-600';
    return (
      <div className="relative grid grid-cols-3 items-center text-sm py-1.5 px-2">
        <div className={`absolute inset-y-0 ${side === 'bid' ? 'right-0' : 'left-0'} ${barCls} rounded`}
             style={{ width: `${pct}%` }} />
        <span className={`relative font-semibold ${priceCls}`}>{fmtPrice(level.price_uah)}</span>
        <span className="relative text-right tabular-nums">{fmtUnits(level.units)}</span>
        <span className="relative text-right tabular-nums text-muted-foreground">{formatUAH(level.units_uah)}</span>
      </div>
    );
  };
  return (
    <div>
      <div className="grid grid-cols-3 text-[11px] uppercase tracking-wide text-muted-foreground px-2 pb-1 border-b border-border">
        <span>Ціна / unit</span><span className="text-right">Units</span><span className="text-right">Обсяг</span>
      </div>
      {/* ASK (descending so best ask sits next to spread) */}
      <div className="divide-y divide-border/50">
        {(ob.asks || []).slice().reverse().map((l, i) => <Row key={`a${i}`} level={l} side="ask" />)}
        {!(ob.asks || []).length && <div className="text-xs text-muted-foreground py-2 px-2">Немає пропозицій на продаж</div>}
      </div>
      {/* spread */}
      <div className="flex items-center justify-center gap-2 py-2 my-1 bg-muted/50 rounded text-xs">
        <span className="text-muted-foreground">Спред</span>
        <span className="font-semibold">{ob.spread_pct != null ? fmtPct(ob.spread_pct, false) : '—'}</span>
      </div>
      <div className="divide-y divide-border/50">
        {(ob.bids || []).map((l, i) => <Row key={`b${i}`} level={l} side="bid" />)}
        {!(ob.bids || []).length && <div className="text-xs text-muted-foreground py-2 px-2">Немає заявок на купівлю</div>}
      </div>
    </div>
  );
}

/* ═══════════════════════ exit simulator ═══════════════════════ */

function ExitSimulator({ assetId, myPosition, base, canTrade }) {
  const [units, setUnits] = useState('');
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const run = async () => {
    setErr(''); setRes(null);
    const u = Number(units);
    if (!u || u <= 0) { setErr('Вкажіть кількість units'); return; }
    const units_uah = u * (base || 1);
    setBusy(true);
    try {
      const r = await lumen.post('/investor/liquidity/exit-simulate', { asset_id: assetId, units_uah });
      setRes(r.data);
    } catch (e) {
      setErr(lumenError(e, 'Не вдалося прорахувати'));
    } finally {
      setBusy(false);
    }
  };

  if (!canTrade) {
    return <LoginPrompt text="Увійдіть, щоб змоделювати вихід зі своєї позиції." />;
  }

  const availUnits = myPosition?.available_units ?? 0;
  return (
    <div className="space-y-3" data-testid="exit-simulator">
      <div className="flex items-center gap-2 text-sm">
        <Scale className="w-4 h-4" style={{ color: PRIMARY }} />
        <span className="font-medium">Симулятор виходу</span>
      </div>
      <p className="text-xs text-muted-foreground">
        Скільки units я зможу продати зараз і що отримаю — без розміщення заявки.
        Доступно: <span className="font-medium text-foreground">{fmtUnits(availUnits)} units</span>
      </p>
      <div className="flex gap-2">
        <input
          type="number" value={units} onChange={(e) => setUnits(e.target.value)}
          placeholder="напр. 1000" data-testid="exit-sim-input"
          className="flex-1 h-10 rounded-lg border border-border bg-background px-3 text-sm" />
        <button onClick={run} disabled={busy} data-testid="exit-sim-run"
          className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-2"
          style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Gauge className="w-4 h-4" />}
          Прорахувати
        </button>
      </div>
      {err && <p className="text-xs text-rose-600">{err}</p>}
      {res && (
        <div className="rounded-xl border border-border p-3 space-y-2 text-sm" data-testid="exit-sim-result">
          {res.exceeds_holdings && (
            <p className="text-xs text-amber-600">Запит перевищує доступні units — рахуємо по максимуму ({fmtUnits(res.available_units)}).</p>
          )}
          <div className="flex justify-between"><span className="text-muted-foreground">Можна продати зараз</span>
            <span className="font-semibold">{fmtUnits(res.immediate_fillable_units)} units</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Середня ціна</span>
            <span className="font-semibold">{fmtPrice(res.avg_price_uah)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Виручка</span>
            <span className="font-semibold">{formatUAH(res.gross_proceeds_uah)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Комісія ({fmtPct(res.fee_pct * 100, false)})</span>
            <span className="text-rose-600">−{formatUAH(res.fee_uah)}</span></div>
          <div className="flex justify-between border-t border-border pt-2"><span className="font-medium">Чистими на гаманець</span>
            <span className="font-bold" style={{ color: PRIMARY }}>{formatUAH(res.net_proceeds_uah)}</span></div>
          {res.shortfall_units > 0 && (
            <p className="text-xs text-amber-600 pt-1">
              {fmtUnits(res.shortfall_units)} units зараз без попиту — їх можна виставити лотом по
              індикативній ціні {fmtPrice(res.indicative_price_uah)}.
            </p>
          )}
          {res.fully_fillable && (
            <p className="text-xs text-emerald-600 pt-1">Повністю покривається поточним попитом ✓</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════ place order ═══════════════════════ */

function PlaceOrder({ assetId, base, mp, myPosition, canTrade, onDone }) {
  const [side, setSide] = useState('buy');
  const [units, setUnits] = useState('');
  const [price, setPrice] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    // default limit to best ask (buy) / best bid (sell) else indicative
    if (!mp) return;
    const def = side === 'buy'
      ? (mp.best_ask ?? mp.indicative_price ?? 1)
      : (mp.best_bid ?? mp.indicative_price ?? 1);
    setPrice(String((def * (base || 1)).toFixed(2)));
  }, [side, mp, base]);

  if (!canTrade) {
    return <LoginPrompt text="Увійдіть, щоб розмістити заявку на купівлю чи продаж." />;
  }

  const submit = async () => {
    setErr(''); setMsg(null);
    const u = Number(units), p = Number(price);
    if (!u || u <= 0) { setErr('Вкажіть кількість units'); return; }
    if (!p || p <= 0) { setErr('Вкажіть ціну'); return; }
    const limit_price = p / (base || 1);   // back to par multiplier
    const units_uah = u * (base || 1);
    setBusy(true);
    try {
      const r = await lumen.post('/investor/liquidity/orders', {
        asset_id: assetId, side, units_uah, limit_price,
      });
      const d = r.data;
      const trades = d.trades || [];
      if (trades.length) {
        const filled = trades.reduce((s, t) => s + (t.units_uah || 0), 0);
        setMsg(`Виконано угод: ${trades.length} на ${fmtUnits(filled / (base || 1))} units`);
      } else if (side === 'buy') {
        setMsg('Заявку розміщено у книзі — очікує зустрічної пропозиції.');
      } else {
        setMsg('Лот виставлено на продаж.');
      }
      setUnits('');
      onDone && onDone();
    } catch (e) {
      setErr(lumenError(e, 'Не вдалося розмістити заявку'));
    } finally {
      setBusy(false);
    }
  };

  const estTotal = (Number(units) || 0) * (Number(price) || 0);
  return (
    <div className="space-y-3" data-testid="place-order">
      <div className="grid grid-cols-2 gap-1 p-1 bg-muted rounded-lg">
        {['buy', 'sell'].map((s) => (
          <button key={s} onClick={() => setSide(s)} data-testid={`order-side-${s}`}
            className={`h-9 rounded-md text-sm font-medium transition ${side === s
              ? (s === 'buy' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white')
              : 'text-muted-foreground'}`}>
            {s === 'buy' ? 'Купити' : 'Продати'}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Units</label>
          <input type="number" value={units} onChange={(e) => setUnits(e.target.value)}
            data-testid="order-units"
            className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Ліміт-ціна / unit</label>
          <input type="number" value={price} onChange={(e) => setPrice(e.target.value)}
            data-testid="order-price"
            className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
        </div>
      </div>
      {side === 'sell' && myPosition && (
        <p className="text-xs text-muted-foreground">Доступно для продажу: {fmtUnits(myPosition.available_units)} units</p>
      )}
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">Орієнтовна сума</span>
        <span className="font-semibold">{formatUAH(estTotal)}</span>
      </div>
      <button onClick={submit} disabled={busy} data-testid="order-submit"
        className={`w-full h-11 rounded-lg text-sm font-semibold text-white inline-flex items-center justify-center gap-2 ${side === 'buy' ? 'bg-emerald-600' : 'bg-rose-600'}`}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowDownUp className="w-4 h-4" />}
        {side === 'buy' ? 'Розмістити купівлю' : 'Виставити продаж'}
      </button>
      {msg && <p className="text-xs text-emerald-600">{msg}</p>}
      {err && <p className="text-xs text-rose-600">{err}</p>}
    </div>
  );
}

/* ═══════════════════════ misc ═══════════════════════ */

function LoginPrompt({ text }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-4 text-center">
      <LogIn className="w-5 h-5 mx-auto mb-2 text-muted-foreground" />
      <p className="text-sm text-muted-foreground mb-3">{text}</p>
      <a href="/auth" className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg text-sm font-medium text-white" style={{ background: PRIMARY }}>
        Увійти
      </a>
    </div>
  );
}

function Metric({ icon: Icon, label, value, sub }) {
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        <Icon className="w-3.5 h-3.5" />{label}
      </div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function SentimentPanel({ s }) {
  if (!s) return null;
  const tone = SENTIMENT_TONE[s.band] || SENTIMENT_TONE.neutral;
  const Icon = tone.icon;
  return (
    <div className="rounded-xl border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="w-4 h-4" style={{ color: PRIMARY }} />Ринковий настрій
        </div>
        <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border ${tone.cls}`}>
          <Icon className="w-3.5 h-3.5" />{s.label}
        </span>
      </div>
      {/* gauge bar -100..100 */}
      <div className="relative h-2 rounded-full bg-gradient-to-r from-rose-300 via-muted to-emerald-300 mb-1">
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-foreground border-2 border-background shadow"
             style={{ left: `calc(${(s.score + 100) / 2}% - 6px)` }} />
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground mb-3">
        <span>−100</span><span className="font-semibold text-foreground">{s.score}</span><span>+100</span>
      </div>
      <div className="space-y-1.5">
        {(s.components || []).map((c) => (
          <div key={c.key} className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{c.label}</span>
            <span className={c.available ? 'font-medium' : 'text-muted-foreground/50'}>
              {c.available ? c.score : '—'} <span className="text-muted-foreground/60">·{Math.round(c.weight * 100)}%</span>
            </span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground mt-3 flex items-start gap-1">
        <Info className="w-3 h-3 mt-0.5 shrink-0" />
        Агрегується з настрою власників, попиту вторинки, активності спільноти та голосувань.
      </p>
    </div>
  );
}

const ACTIVITY_META = {
  trade: { icon: Repeat, label: 'Угода', verb: 'Продано' },
  listing: { icon: ArrowUpRight, label: 'Лот', verb: 'Виставлено' },
  bid: { icon: ArrowDownRight, label: 'Попит', verb: 'Заявка на' },
  payout: { icon: Wallet, label: 'Виплата', verb: 'Виплата' },
};

function ActivityFeed({ items }) {
  if (!items?.length) {
    return <p className="text-sm text-muted-foreground py-4 text-center">Поки немає активності</p>;
  }
  return (
    <div className="space-y-2" data-testid="liquidity-activity">
      {items.map((it, i) => {
        const meta = ACTIVITY_META[it.type] || ACTIVITY_META.trade;
        const Icon = meta.icon;
        return (
          <div key={i} className="flex items-center gap-3 text-sm py-1.5 border-b border-border/50 last:border-0">
            <span className="w-7 h-7 rounded-full bg-muted flex items-center justify-center shrink-0">
              <Icon className="w-3.5 h-3.5 text-muted-foreground" />
            </span>
            <div className="flex-1 min-w-0">
              <span className="text-foreground">
                {meta.verb} <span className="font-semibold">{fmtUnits(it.units)} units</span>
                {' по '}<span className="font-semibold">{fmtPrice(it.price_uah)}</span>
              </span>
              {it.premium_pct != null && it.type !== 'payout' && (
                <span className="ml-2"><PremiumPill pct={it.premium_pct} /></span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ═══════════════════════ main component ═══════════════════════ */

export default function AssetLiquidity({ assetId, user }) {
  const { data, loading, reload } = useLiquidity(assetId);
  const [watching, setWatching] = useState(false);
  const [watchBusy, setWatchBusy] = useState(false);

  useEffect(() => { if (data) setWatching(!!data.watching); }, [data]);

  const canTrade = !!user;

  const toggleWatch = async () => {
    if (!canTrade) { window.location.href = '/auth'; return; }
    setWatchBusy(true);
    try {
      if (watching) {
        await lumen.delete(`/investor/watchlist/${assetId}`);
        setWatching(false);
      } else {
        await lumen.post(`/investor/watchlist/${assetId}`);
        setWatching(true);
      }
    } catch (_e) { /* noop */ }
    finally { setWatchBusy(false); }
  };

  if (loading) {
    return <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Дані ліквідності недоступні.</p>;
  }

  const { order_book: ob, market_price: mp, price_discovery: pd, price_history: ph,
          metrics: m, sentiment: sent, activity } = data;
  const base = mp.base_unit_price_uah;

  return (
    <div className="space-y-6" data-testid="asset-liquidity">
      {/* ── price header ── */}
      <div className="rounded-2xl border border-border p-5 bg-gradient-to-br from-muted/40 to-transparent">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Ринкова ціна (індикативна)</div>
            <div className="flex items-center gap-3">
              <span className="text-3xl font-bold tabular-nums">{fmtPrice(mp.indicative_price_uah)}</span>
              <PremiumPill pct={mp.premium_discount_pct} size="lg" />
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              за 1 unit · NAV {fmtPrice(pd.nav_per_unit_uah)} · {pd.label}
            </div>
          </div>
          <button onClick={toggleWatch} disabled={watchBusy} data-testid="watch-toggle"
            className={`inline-flex items-center gap-2 h-9 px-3 rounded-lg text-sm font-medium border transition ${watching
              ? 'bg-amber-50 border-amber-300 text-amber-700' : 'border-border hover:border-[#2E5D4F]'}`}>
            <Star className={`w-4 h-4 ${watching ? 'fill-amber-400 text-amber-500' : ''}`} />
            {watching ? 'У списку стеження' : 'Стежити'}
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          <div><div className="text-[11px] text-muted-foreground">Last Trade</div>
            <div className="font-semibold">{mp.last_trade ? fmtPrice(mp.last_trade.price_uah) : '—'}</div></div>
          <div><div className="text-[11px] text-muted-foreground">Best Bid</div>
            <div className="font-semibold text-emerald-600">{mp.best_bid_uah ? fmtPrice(mp.best_bid_uah) : '—'}</div></div>
          <div><div className="text-[11px] text-muted-foreground">Best Ask</div>
            <div className="font-semibold text-rose-600">{mp.best_ask_uah ? fmtPrice(mp.best_ask_uah) : '—'}</div></div>
          <div><div className="text-[11px] text-muted-foreground">Спред</div>
            <div className="font-semibold">{mp.spread_pct != null ? fmtPct(mp.spread_pct, false) : '—'}</div></div>
        </div>
      </div>

      {/* ── chart ── */}
      <div className="rounded-2xl border border-border p-5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            <BarChart3 className="w-4 h-4" style={{ color: PRIMARY }} />Динаміка ціни
          </div>
          <span className="text-xs text-muted-foreground">VWAP · останні 90 днів · {ph.count} угод</span>
        </div>
        <PriceChart history={ph} base={base} />
      </div>

      {/* ── price discovery + metrics ── */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border p-5" data-testid="price-discovery">
          <div className="flex items-center gap-2 text-sm font-medium mb-3">
            <Scale className="w-4 h-4" style={{ color: PRIMARY }} />Price Discovery
          </div>
          <div className="flex items-end gap-6 mb-4">
            <div>
              <div className="text-[11px] text-muted-foreground">NAV / unit</div>
              <div className="text-2xl font-bold">{fmtPrice(pd.nav_per_unit_uah)}</div>
              <div className="text-[11px] text-muted-foreground">балансова</div>
            </div>
            <div className="text-2xl text-muted-foreground pb-3">→</div>
            <div>
              <div className="text-[11px] text-muted-foreground">Ринкова / unit</div>
              <div className="text-2xl font-bold" style={{ color: PRIMARY }}>{fmtPrice(pd.market_price_uah)}</div>
              <div className="text-[11px] text-muted-foreground">за угодами/книгою</div>
            </div>
            <div className="ml-auto pb-2"><PremiumPill pct={pd.premium_discount_pct} size="lg" /></div>
          </div>
          <p className="text-sm text-muted-foreground">{pd.label}.
            <span className="ml-1">Достовірність: {pd.confidence === 'high' ? 'висока'
              : pd.confidence === 'medium' ? 'середня' : 'низька'} ({pd.trades_count} угод)</span></p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Metric icon={Users} label="Власників" value={fmtUnits(m.holders)} />
          <Metric icon={Activity} label="Угод 30д" value={fmtUnits(m.trades_30d)} sub={formatUAH(m.volume_30d_uah)} />
          <Metric icon={Layers} label="Виставлено" value={`${fmtUnits(m.units_listed)} u`} sub={formatUAH(m.units_listed_uah)} />
          <Metric icon={TrendingUp} label="Попит" value={`${fmtUnits(m.demand_units)} u`} sub={formatUAH(m.demand_uah)} />
        </div>
      </div>

      {m.market_maker_active && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 flex items-center gap-2 text-sm text-emerald-800">
          <ShieldCheck className="w-4 h-4" />Маркет-мейкер активний — підтримує ліквідність по цьому активу.
        </div>
      )}

      {/* ── order book + trade panels ── */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 text-sm font-medium mb-3">
            <ArrowDownUp className="w-4 h-4" style={{ color: PRIMARY }} />Книга заявок
          </div>
          <OrderBook ob={ob} />
        </div>
        <div className="space-y-4">
          <div className="rounded-2xl border border-border p-5">
            <PlaceOrder assetId={assetId} base={base} mp={mp}
              myPosition={data.my_position} canTrade={canTrade} onDone={reload} />
          </div>
          <div className="rounded-2xl border border-border p-5">
            <ExitSimulator assetId={assetId} myPosition={data.my_position}
              base={base} canTrade={canTrade} />
          </div>
        </div>
      </div>

      {/* ── sentiment + activity ── */}
      <div className="grid lg:grid-cols-2 gap-4">
        <SentimentPanel s={sent} />
        <div className="rounded-2xl border border-border p-5">
          <div className="flex items-center gap-2 text-sm font-medium mb-3">
            <Activity className="w-4 h-4" style={{ color: PRIMARY }} />Ринкова активність
          </div>
          <ActivityFeed items={activity} />
        </div>
      </div>
    </div>
  );
}
