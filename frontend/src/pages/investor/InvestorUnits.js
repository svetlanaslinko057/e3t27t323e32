/**
 * InvestorUnits — LUMEN 2.0 / Phase A1.
 * "Мої частки" — the investor's integer unit holdings across all assets.
 * Shows total units + total value and a per-asset breakdown (units, % of asset,
 * unit price, current value), with a drill-down to the ownership-event history.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Boxes, Layers, Wallet, TrendingUp, ArrowLeft, Activity,
  ArrowDownRight, ArrowUpRight, Sparkles, MapPin, RefreshCw,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const EVENT_META = {
  issue:        { label: 'Купівля (первинна)', icon: Sparkles,       cls: 'text-emerald-500 bg-emerald-500/10' },
  transfer_in:  { label: 'Купівля на ринку',   icon: ArrowDownRight, cls: 'text-sky-500 bg-sky-500/10' },
  transfer_out: { label: 'Продаж на ринку',    icon: ArrowUpRight,   cls: 'text-amber-500 bg-amber-500/10' },
  void:         { label: 'Анулювання',         icon: Activity,       cls: 'text-rose-500 bg-rose-500/10' },
  adjust:       { label: 'Коригування',        icon: Activity,       cls: 'text-violet-500 bg-violet-500/10' },
};

export default function InvestorUnits() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openAsset, setOpenAsset] = useState(null);   // {asset_id, asset_title}
  const [events, setEvents] = useState([]);
  const [evLoading, setEvLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get('/investor/units');
      setData(d);
    } catch {
      toast.error('Не вдалось завантажити частки');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const showHistory = async (h) => {
    setOpenAsset(h);
    setEvLoading(true);
    try {
      const r = await api.get(`/investor/units/${h.asset_id}/events`);
      setEvents(r.items || []);
    } catch {
      setEvents([]);
    } finally {
      setEvLoading(false);
    }
  };

  const holdings = data?.holdings || [];

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="investor-units">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Boxes className="w-4 h-4" /> Ownership · одиниці</div>
          <h1 className="text-h1 mb-1 mt-1">Мої частки</h1>
          <p className="text-small-token max-w-2xl">
            Ваше володіння у вигляді одиниць (units). Кожен актив поділено на фіксовану
            кількість одиниць — ви володієте їх частиною пропорційно до інвестицій.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
          data-testid="units-refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8" data-testid="units-summary">
        <div className="rounded-2xl border border-app bg-app-surface p-5">
          <div className="w-10 h-10 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center"><Boxes className="w-5 h-5" /></div>
          <div className="mt-3 text-3xl font-bold text-token-primary tabular-nums leading-none" data-testid="units-total">
            {loading ? '…' : nfmt(data?.total_units)}
          </div>
          <div className="mt-1.5 text-[11px] uppercase tracking-wider font-bold text-token-muted">Усього одиниць</div>
        </div>
        <div className="rounded-2xl border border-app bg-app-surface p-5">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center"><Wallet className="w-5 h-5" /></div>
          <div className="mt-3 text-3xl font-bold text-token-primary tabular-nums leading-none" data-testid="units-value">
            {loading ? '…' : formatUAH(data?.total_value_uah)}
          </div>
          <div className="mt-1.5 text-[11px] uppercase tracking-wider font-bold text-token-muted">Поточна вартість</div>
        </div>
        <div className="rounded-2xl border border-app bg-app-surface p-5">
          <div className="w-10 h-10 rounded-xl bg-sky-500/10 text-sky-500 flex items-center justify-center"><Layers className="w-5 h-5" /></div>
          <div className="mt-3 text-3xl font-bold text-token-primary tabular-nums leading-none" data-testid="units-assets">
            {loading ? '…' : nfmt(data?.assets_count)}
          </div>
          <div className="mt-1.5 text-[11px] uppercase tracking-wider font-bold text-token-muted">Активів у портфелі</div>
        </div>
      </div>

      {/* Holdings */}
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-4 h-4 text-token-muted" />
        <h2 className="text-lg font-semibold text-token-primary">Володіння за активами</h2>
      </div>

      {loading ? (
        <div className="space-y-3">{[...Array(3)].map((_, i) => <div key={i} className="h-24 rounded-2xl bg-app-elevated animate-pulse" />)}</div>
      ) : holdings.length === 0 ? (
        <div className="rounded-2xl border border-app bg-app-surface p-10 text-center">
          <Boxes className="w-10 h-10 mx-auto text-token-muted mb-3" />
          <p className="text-token-secondary font-medium">У вас поки немає часток</p>
          <p className="text-sm text-token-muted mt-1">Інвестуйте в об'єкт, щоб отримати одиниці володіння.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="units-holdings">
          {holdings.map((h) => (
            <div key={h.asset_id} className="rounded-2xl border border-app bg-app-surface overflow-hidden flex flex-col sm:flex-row" data-testid={`holding-${h.asset_id}`}>
              {h.cover_url ? (
                <div className="sm:w-44 h-32 sm:h-auto shrink-0 bg-app-elevated">
                  <img src={h.cover_url} alt={h.asset_title} className="w-full h-full object-cover" />
                </div>
              ) : null}
              <div className="flex-1 p-5 flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-token-primary truncate">{h.asset_title}</h3>
                  <div className="flex items-center gap-1 text-[12px] text-token-muted mt-0.5">
                    <MapPin className="w-3.5 h-3.5" /> <span className="truncate">{h.location || '—'}</span>
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-token-muted mt-1">{h.category}</div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <div className="text-xl font-bold text-token-primary tabular-nums">{nfmt(h.units)}</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">одиниць</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xl font-bold text-[#2E5D4F] tabular-nums">{Number(h.percent).toFixed(2)}%</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">частка</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xl font-bold text-token-primary tabular-nums">{formatUAH(h.value_uah)}</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">вартість</div>
                  </div>
                  <button onClick={() => showHistory(h)}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-app text-xs font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition"
                    data-testid={`holding-history-${h.asset_id}`}>
                    <Activity className="w-3.5 h-3.5" /> Історія
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* History drawer */}
      {openAsset && (
        <div className="fixed inset-0 z-50 flex justify-end" data-testid="units-history-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpenAsset(null)} />
          <div className="relative w-full max-w-md bg-app-surface h-full overflow-y-auto shadow-xl">
            <div className="px-5 py-4 border-b border-app flex items-center gap-3 sticky top-0 bg-app-surface">
              <button onClick={() => setOpenAsset(null)} className="text-token-muted hover:text-token-primary"><ArrowLeft className="w-5 h-5" /></button>
              <div className="min-w-0">
                <div className="text-token-kicker">Історія одиниць</div>
                <h3 className="font-semibold text-token-primary truncate">{openAsset.asset_title}</h3>
              </div>
            </div>
            {evLoading ? (
              <div className="p-5 space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-14 rounded-xl bg-app-elevated animate-pulse" />)}</div>
            ) : events.length === 0 ? (
              <div className="p-10 text-center text-sm text-token-muted">Подій ще немає.</div>
            ) : (
              <ul className="divide-y divide-app/60">
                {events.map((e) => {
                  const meta = EVENT_META[e.event_type] || EVENT_META.adjust;
                  const Icon = meta.icon;
                  return (
                    <li key={e.id} className="px-5 py-3 flex items-start gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${meta.cls}`}><Icon className="w-4 h-4" /></div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-token-primary">{meta.label}</span>
                          <span className={`text-sm font-semibold tabular-nums ${e.delta_units >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {e.delta_units >= 0 ? '+' : ''}{nfmt(e.delta_units)}
                          </span>
                        </div>
                        <div className="text-[11px] text-token-muted">
                          Баланс: {nfmt(e.balance_after)} од. · {formatDateUk(e.created_at)}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
