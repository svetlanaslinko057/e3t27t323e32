import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH, formatUSD, usdFromUah, lumenError } from '@/lib/lumenApi';
import {
  Gauge, Plus, Trash2, Loader2, ShieldCheck, Power, TrendingUp, Activity,
  ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';

const fmtPct = (n, sign = true) => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const v = Number(n); const s = sign && v > 0 ? '+' : '';
  return `${s}${v.toFixed(1).replace('.', ',')}%`;
};
const fmtPrice = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : formatUSD(usdFromUah(n), { decimals: 2 });

const KIND_LABEL = { fund: 'Фонд', operator: 'Оператор', spv: 'SPV', external: 'Зовнішній' };

function Pill({ pct }) {
  if (pct === null || pct === undefined) return null;
  const up = pct > 0.05, down = pct < -0.05;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const cls = up ? 'bg-emerald-100 text-emerald-700'
    : down ? 'bg-rose-100 text-rose-700' : 'bg-muted text-muted-foreground';
  return <span className={`inline-flex items-center gap-0.5 text-xs px-2 py-0.5 rounded-full font-semibold ${cls}`}><Icon className="w-3 h-3" />{fmtPct(pct)}</span>;
}

export default function AdminMarketMakers() {
  const [overview, setOverview] = useState(null);
  const [makers, setMakers] = useState([]);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ asset_id: '', name: '', kind: 'fund', committed_uah: '', target_spread_pct: '2' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const [ov, mm, as] = await Promise.all([
        lumen.get('/admin/liquidity/overview'),
        lumen.get('/admin/liquidity/market-makers'),
        lumen.get('/assets'),
      ]);
      setOverview(ov.data);
      setMakers(mm.data.items || []);
      const list = Array.isArray(as.data) ? as.data : (as.data.items || as.data.assets || []);
      setAssets(list);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setErr('');
    if (!form.asset_id || !form.name) { setErr('Оберіть об\'єкт і вкажіть назву'); return; }
    setBusy(true);
    try {
      await lumen.post('/admin/liquidity/market-makers', {
        asset_id: form.asset_id, name: form.name, kind: form.kind,
        committed_uah: Number(form.committed_uah) || 0,
        target_spread_pct: Number(form.target_spread_pct) || 2,
        active: true,
      });
      setForm({ asset_id: '', name: '', kind: 'fund', committed_uah: '', target_spread_pct: '2' });
      load();
    } catch (e) { setErr(lumenError(e, 'Не вдалося створити')); }
    finally { setBusy(false); }
  };

  const toggle = async (mm) => {
    try { await lumen.patch(`/admin/liquidity/market-makers/${mm.id}`, { active: !mm.active }); load(); }
    catch (_e) { /* noop */ }
  };
  const remove = async (id) => {
    try { await lumen.delete(`/admin/liquidity/market-makers/${id}`); load(); }
    catch (_e) { /* noop */ }
  };

  if (loading) {
    return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-market-makers">
      <div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Liquidity OS · Phase D</div>
        <h1 className="text-2xl font-bold">Ліквідність і маркет-мейкери</h1>
      </div>

      {/* KPIs */}
      {overview && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            ['Активні лоти', overview.active_listings],
            ['Відкриті заявки', overview.open_orders],
            ['Угод (settled)', overview.settled_trades],
            ['Стежать', overview.watchers],
            ['Маркет-мейкери', overview.market_makers],
          ].map(([l, v]) => (
            <div key={l} className="rounded-xl border border-border p-4">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</div>
              <div className="text-2xl font-bold">{v}</div>
            </div>
          ))}
        </div>
      )}

      {/* per-asset snapshot */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><TrendingUp className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Зведення по об'єктах</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="liquidity-overview-table">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-muted-foreground border-b border-border">
                <th className="text-left py-2">Об'єкт</th>
                <th className="text-right">Ринкова</th>
                <th className="text-center">Прем/Диск</th>
                <th className="text-right">Спред</th>
                <th className="text-right">Власників</th>
                <th className="text-right">Угод 30д</th>
                <th className="text-right">Обсяг 30д</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.assets || []).map((a) => (
                <tr key={a.asset_id} className="border-b border-border/50">
                  <td className="py-2">{a.asset_title || a.asset_id}</td>
                  <td className="text-right font-semibold">{fmtPrice(a.indicative_price_uah)}</td>
                  <td className="text-center"><Pill pct={a.premium_discount_pct} /></td>
                  <td className="text-right">{a.spread_pct != null ? fmtPct(a.spread_pct, false) : '—'}</td>
                  <td className="text-right">{a.holders}</td>
                  <td className="text-right">{a.trades_30d}</td>
                  <td className="text-right">{formatUAH(a.volume_30d_uah)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* market makers */}
      <section className="rounded-2xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4"><ShieldCheck className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Маркет-мейкери</h2></div>

        {/* create form */}
        <div className="rounded-xl border border-dashed border-border p-4 mb-4 grid md:grid-cols-6 gap-2 items-end" data-testid="mm-create-form">
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Об'єкт</label>
            <select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })}
              data-testid="mm-asset" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm">
              <option value="">Оберіть…</option>
              {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Назва</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              data-testid="mm-name" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Тип</label>
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm">
              {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Спред %</label>
            <input type="number" value={form.target_spread_pct} onChange={(e) => setForm({ ...form, target_spread_pct: e.target.value })}
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
          </div>
          <button onClick={create} disabled={busy} data-testid="mm-create-btn"
            className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}Додати
          </button>
        </div>
        {err && <p className="text-xs text-rose-600 mb-2">{err}</p>}

        {makers.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">Маркет-мейкерів ще немає.</p>
        ) : (
          <div className="space-y-2" data-testid="mm-list">
            {makers.map((mm) => (
              <div key={mm.id} className="flex items-center gap-3 rounded-xl border border-border p-3">
                <span className={`w-9 h-9 rounded-lg flex items-center justify-center ${mm.active ? 'bg-emerald-100 text-emerald-700' : 'bg-muted text-muted-foreground'}`}>
                  <ShieldCheck className="w-4 h-4" />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{mm.name} <span className="text-xs text-muted-foreground">· {KIND_LABEL[mm.kind] || mm.kind}</span></div>
                  <div className="text-xs text-muted-foreground">{mm.asset_title || mm.asset_id} · резерв {formatUAH(mm.committed_uah)} · цільовий спред {fmtPct(mm.target_spread_pct, false)}</div>
                </div>
                <button onClick={() => toggle(mm)} className={`text-xs px-2.5 py-1 rounded-lg border inline-flex items-center gap-1 ${mm.active ? 'border-emerald-300 text-emerald-700' : 'border-border text-muted-foreground'}`}>
                  <Power className="w-3.5 h-3.5" />{mm.active ? 'Активний' : 'Вимкнений'}
                </button>
                <button onClick={() => remove(mm.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
