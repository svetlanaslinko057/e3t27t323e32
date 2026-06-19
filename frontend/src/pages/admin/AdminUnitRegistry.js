/**
 * AdminUnitRegistry — LUMEN 2.0 / Phase A1.
 * Unit Registry Dashboard + Ownership Explorer.
 *
 * The integer source of truth for ownership. Lists every asset's unit ledger
 * (total / issued / locked / listed / available), drills into the per-asset
 * cap table + ownership-event stream, and exposes admin maintenance actions
 * (snapshot, recompute) plus a live invariant check.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Boxes, Database, Layers, Coins, Lock, Tag, RefreshCw, Camera,
  ArrowLeft, ShieldCheck, ShieldAlert, Users, Activity, ArrowDownRight,
  ArrowUpRight, Sparkles, PieChart, Route, X, FileText, CreditCard,
  Banknote, Award, Repeat, ListTree,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const EVENT_META = {
  issue:        { label: 'Випуск',     icon: Sparkles,       cls: 'text-emerald-500 bg-emerald-500/10' },
  transfer_in:  { label: 'Надходження', icon: ArrowDownRight, cls: 'text-sky-500 bg-sky-500/10' },
  transfer_out: { label: 'Списання',    icon: ArrowUpRight,   cls: 'text-amber-500 bg-amber-500/10' },
  void:         { label: 'Анулювання',  icon: ShieldAlert,    cls: 'text-rose-500 bg-rose-500/10' },
  adjust:       { label: 'Коригування', icon: Activity,       cls: 'text-violet-500 bg-violet-500/10' },
};

function StatTile({ icon: Icon, label, value, accent = 'text-[#2E5D4F] bg-[#2E5D4F]/10', testid }) {
  return (
    <div className="rounded-2xl border border-app bg-app-surface p-5" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${accent}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="mt-3 text-2xl font-bold text-token-primary tabular-nums leading-none">{value}</div>
      <div className="mt-1.5 text-[11px] uppercase tracking-wider font-bold text-token-muted">{label}</div>
    </div>
  );
}

function SubscriptionBar({ pct }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  return (
    <div className="h-2 rounded-full bg-app-elevated overflow-hidden w-full">
      <div className="h-full bg-[#2E5D4F] rounded-full transition-all" style={{ width: `${p}%` }} />
    </div>
  );
}

export default function AdminUnitRegistry() {
  const { toast } = useToast();
  const [overview, setOverview] = useState(null);
  const [invariants, setInvariants] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);   // asset detail
  const [detailLoading, setDetailLoading] = useState(false);
  const [trace, setTrace] = useState(null);          // ownership trace drawer
  const [traceLoading, setTraceLoading] = useState(false);

  const openTrace = useCallback(async (assetId, investorId) => {
    setTrace({ loading: true });
    setTraceLoading(true);
    try {
      const d = await api.get('/admin/ownership/trace', { params: { investor_id: investorId, asset_id: assetId } });
      setTrace(d);
    } catch {
      toast.error('Не вдалось завантажити трасування');
      setTrace(null);
    } finally { setTraceLoading(false); }
  }, [toast]);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, inv] = await Promise.all([
        api.get('/admin/registry/summary'),
        api.get('/admin/registry/invariants'),
      ]);
      setOverview(ov);
      setInvariants(inv);
    } catch {
      toast.error('Не вдалось завантажити реєстр одиниць');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const openAsset = useCallback(async (assetId) => {
    setDetailLoading(true);
    try {
      const d = await api.get(`/admin/registry/asset/${assetId}`);
      setSelected(d);
    } catch {
      toast.error('Не вдалось відкрити актив');
    } finally {
      setDetailLoading(false);
    }
  }, [toast]);

  const snapshot = async (assetId) => {
    setBusy(true);
    try {
      await api.post(`/admin/registry/asset/${assetId}/snapshot`);
      toast.success('Знімок капіталізації створено');
    } catch {
      toast.error('Помилка створення знімку');
    } finally { setBusy(false); }
  };

  const recompute = async (assetId) => {
    setBusy(true);
    try {
      await api.post(`/admin/registry/asset/${assetId}/recompute`);
      toast.success('Реєстр перераховано');
      await openAsset(assetId);
      await loadOverview();
    } catch {
      toast.error('Помилка перерахунку');
    } finally { setBusy(false); }
  };

  const invByAsset = (id) => (invariants?.assets || []).find((a) => a.asset_id === id);
  const totals = overview?.totals || {};
  const allOk = invariants?.all_ok;

  // ---- Detail (Ownership Explorer) -----------------------------------------
  if (selected) {
    const inv = invByAsset(selected.asset_id);
    return (
      <div className="px-[50px] py-8 pb-20" data-testid="registry-asset-detail">
        <button
          onClick={() => setSelected(null)}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-token-muted hover:text-token-primary transition mb-5"
          data-testid="registry-back"
        >
          <ArrowLeft className="w-4 h-4" /> До реєстру
        </button>

        <div className="flex items-start justify-between gap-6 flex-wrap mb-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-token-kicker"><Boxes className="w-4 h-4" /> Ownership Explorer</div>
            <h1 className="text-h1 mt-1 mb-1">{selected.asset_title}</h1>
            <p className="text-small-token">
              Ціна одиниці <b className="text-token-primary">{formatUAH(selected.unit_price_uah)}</b> ·
              Ціль раунду {formatUAH(selected.target_amount)} · {selected.holders_count} власників
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => snapshot(selected.asset_id)} disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
              data-testid="registry-snapshot">
              <Camera className="w-4 h-4" /> Знімок
            </button>
            <button onClick={() => recompute(selected.asset_id)} disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43] transition disabled:opacity-50"
              data-testid="registry-recompute">
              <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} /> Перерахувати
            </button>
          </div>
        </div>

        {/* Invariant badge */}
        {inv && (
          <div className={`rounded-xl border p-4 mb-6 flex items-center gap-3 ${inv.ok ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5'}`}
            data-testid="registry-invariant-badge">
            {inv.ok ? <ShieldCheck className="w-5 h-5 text-emerald-500" /> : <ShieldAlert className="w-5 h-5 text-rose-500" />}
            <div className="text-sm">
              <span className={`font-semibold ${inv.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
                {inv.ok ? 'Інваріанти збережено' : 'Порушення інваріанта'}
              </span>
              <span className="text-token-muted ml-2">
                Σ власників = {nfmt(inv.issued_units)} · доступно {nfmt(inv.available_units)} · разом {nfmt(inv.total_units)}
              </span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatTile icon={Database} label="Усього одиниць" value={nfmt(selected.total_units)} testid="detail-total" />
          <StatTile icon={Coins} label="Випущено" value={nfmt(selected.issued_units)} accent="text-emerald-500 bg-emerald-500/10" testid="detail-issued" />
          <StatTile icon={Tag} label="Виставлено на ринок" value={nfmt(selected.listed_units)} accent="text-amber-500 bg-amber-500/10" testid="detail-listed" />
          <StatTile icon={Layers} label="Доступно" value={nfmt(selected.available_units)} accent="text-sky-500 bg-sky-500/10" testid="detail-available" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Cap table */}
          <div className="lg:col-span-2 rounded-2xl border border-app bg-app-surface overflow-hidden">
            <div className="px-5 py-4 border-b border-app flex items-center gap-2">
              <Users className="w-4 h-4 text-token-muted" />
              <h3 className="font-semibold text-token-primary">Таблиця капіталізації</h3>
            </div>
            {(selected.holders || []).length === 0 ? (
              <div className="p-8 text-center text-sm text-token-muted">Поки немає власників одиниць.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="cap-table">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wider text-token-muted border-b border-app">
                      <th className="px-5 py-3 font-bold">Інвестор</th>
                      <th className="px-5 py-3 font-bold text-right">Одиниці</th>
                      <th className="px-5 py-3 font-bold text-right">Частка</th>
                      <th className="px-5 py-3 font-bold text-right">Виставлено</th>
                      <th className="px-5 py-3 font-bold text-right">Вартість</th>
                      <th className="px-5 py-3 font-bold text-right">Трасування</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.holders.map((h) => (
                      <tr key={h.investor_id} className="border-b border-app/60 last:border-0 hover:bg-app-elevated/50">
                        <td className="px-5 py-3 font-medium text-token-primary truncate max-w-[220px]">{h.investor_name}</td>
                        <td className="px-5 py-3 text-right tabular-nums font-semibold text-token-primary">{nfmt(h.units)}</td>
                        <td className="px-5 py-3 text-right tabular-nums text-token-secondary">{Number(h.percent).toFixed(2)}%</td>
                        <td className="px-5 py-3 text-right tabular-nums text-token-muted">{h.listed_units ? nfmt(h.listed_units) : '—'}</td>
                        <td className="px-5 py-3 text-right tabular-nums text-token-secondary">{formatUAH(h.value_uah)}</td>
                        <td className="px-5 py-3 text-right">
                          <button onClick={() => openTrace(selected.asset_id, h.investor_id)}
                            data-testid={`trace-${h.investor_id}`}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-app text-xs font-semibold text-token-secondary hover:text-[#2E5D4F] hover:border-app-strong transition">
                            <ListTree className="w-3.5 h-3.5" /> Trace
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Event stream */}
          <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
            <div className="px-5 py-4 border-b border-app flex items-center gap-2">
              <Activity className="w-4 h-4 text-token-muted" />
              <h3 className="font-semibold text-token-primary">Реєстр подій</h3>
            </div>
            {(selected.recent_events || []).length === 0 ? (
              <div className="p-8 text-center text-sm text-token-muted">Подій ще немає.</div>
            ) : (
              <ul className="divide-y divide-app/60" data-testid="event-stream">
                {selected.recent_events.map((e) => {
                  const meta = EVENT_META[e.event_type] || EVENT_META.adjust;
                  const Icon = meta.icon;
                  return (
                    <li key={e.id} className="px-5 py-3 flex items-start gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${meta.cls}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-token-primary">{meta.label}</span>
                          <span className={`text-sm font-semibold tabular-nums ${e.delta_units >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {e.delta_units >= 0 ? '+' : ''}{nfmt(e.delta_units)}
                          </span>
                        </div>
                        <div className="text-[11px] text-token-muted truncate">
                          {e.note || e.ref_type || '—'} · {formatDateUk(e.created_at)}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {trace && <TraceDrawer trace={trace} loading={traceLoading} onClose={() => setTrace(null)} />}
      </div>
    );
  }

  // ---- Dashboard (Registry overview) ---------------------------------------
  return (
    <div className="px-[50px] py-8 pb-20" data-testid="admin-unit-registry">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Database className="w-4 h-4" /> Unit Registry · LUMEN 2.0</div>
          <h1 className="text-h1 mb-1 mt-1">Реєстр одиниць</h1>
          <p className="text-small-token max-w-2xl">
            Цілочисельний реєстр володіння — джерело істини для часток, вторинного ринку,
            сертифікатів і виплат. Кожен актив поділено на фіксовану кількість одиниць.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {invariants && (
            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl ${allOk ? 'text-emerald-600 bg-emerald-500/10' : 'text-rose-600 bg-rose-500/10'}`}
              data-testid="registry-invariants-pill">
              {allOk ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
              {allOk ? 'Інваріанти OK' : 'Є порушення'}
            </span>
          )}
          <button onClick={loadOverview} disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
            data-testid="registry-refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
          </button>
        </div>
      </div>

      {/* Totals */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8" data-testid="registry-totals">
        <StatTile icon={Database} label="Усього одиниць" value={loading ? '…' : nfmt(totals.total_units)} testid="total-units" />
        <StatTile icon={Coins} label="Випущено" value={loading ? '…' : nfmt(totals.issued_units)} accent="text-emerald-500 bg-emerald-500/10" testid="total-issued" />
        <StatTile icon={Tag} label="На вторинному ринку" value={loading ? '…' : nfmt(totals.listed_units)} accent="text-amber-500 bg-amber-500/10" testid="total-listed" />
        <StatTile icon={Layers} label="Доступно" value={loading ? '…' : nfmt(totals.available_units)} accent="text-sky-500 bg-sky-500/10" testid="total-available" />
      </div>

      <div className="flex items-center gap-2 mb-4">
        <Boxes className="w-4 h-4 text-token-muted" />
        <h2 className="text-lg font-semibold text-token-primary">Активи</h2>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-44 rounded-2xl bg-app-elevated animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="registry-assets">
          {(overview?.assets || []).map((a) => {
            const inv = invByAsset(a.asset_id);
            return (
              <button
                key={a.asset_id}
                onClick={() => openAsset(a.asset_id)}
                disabled={detailLoading}
                className="text-left rounded-2xl border border-app bg-app-surface p-5 hover:border-app-strong hover:shadow-sm transition group"
                data-testid={`registry-asset-${a.asset_id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-token-primary truncate group-hover:text-[#2E5D4F] transition">{a.asset_title}</h3>
                    <div className="text-[11px] text-token-muted mt-0.5 uppercase tracking-wide">{a.category} · {a.status}</div>
                  </div>
                  {inv && (inv.ok
                    ? <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
                    : <ShieldAlert className="w-4 h-4 text-rose-500 shrink-0" />)}
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-lg font-bold text-token-primary tabular-nums">{nfmt(a.issued_units)}</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">Випущено</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-token-primary tabular-nums">{nfmt(a.available_units)}</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">Доступно</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-token-primary tabular-nums">{nfmt(a.holders_count)}</div>
                    <div className="text-[10px] uppercase tracking-wider text-token-muted">Власників</div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="flex items-center justify-between text-[11px] text-token-muted mb-1.5">
                    <span>Підписка {a.subscription_pct}%</span>
                    <span>{formatUAH(a.unit_price_uah)}/од.</span>
                  </div>
                  <SubscriptionBar pct={a.subscription_pct} />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ── Ownership Explorer — full trace drawer (A3 Block 6) ──────────────────────
const TRACE_STEP_ICON = {
  intent: FileText, kyc: ShieldCheck, contract: FileText, payment: CreditCard,
  certificate: Award, active: ShieldCheck, first_payout: Banknote, withdrawal: Coins,
};

function TraceSection({ icon: Icon, title, count, children }) {
  return (
    <div className="rounded-xl border border-app overflow-hidden">
      <div className="px-4 py-2.5 bg-app-elevated/50 flex items-center gap-2">
        <Icon className="w-4 h-4 text-token-muted" />
        <span className="text-sm font-semibold text-token-primary">{title}</span>
        {count !== undefined && <span className="text-[11px] text-token-muted ml-auto">{count}</span>}
      </div>
      <div className="p-3 space-y-2">{children}</div>
    </div>
  );
}

function Row({ left, right, sub }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <div className="min-w-0">
        <div className="text-token-primary truncate">{left}</div>
        {sub && <div className="text-[11px] text-token-muted truncate">{sub}</div>}
      </div>
      {right !== undefined && <div className="text-token-secondary tabular-nums shrink-0">{right}</div>}
    </div>
  );
}

function TraceDrawer({ trace, loading, onClose }) {
  const lc = trace?.lifecycle;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="ownership-trace-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-app-surface h-full overflow-y-auto shadow-xl">
        <div className="px-5 py-4 border-b border-app flex items-center gap-3 sticky top-0 bg-app-surface z-10">
          <ListTree className="w-5 h-5 text-[#2E5D4F]" />
          <div className="min-w-0 flex-1">
            <div className="text-token-kicker">Ownership Explorer · Trace</div>
            <h3 className="font-semibold text-token-primary truncate">{trace?.investor_name || '…'}</h3>
          </div>
          <button onClick={onClose} className="text-token-muted hover:text-token-primary"><X className="w-5 h-5" /></button>
        </div>

        {loading || trace?.loading ? (
          <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="h-16 rounded-xl bg-app-elevated animate-pulse" />)}</div>
        ) : (
          <div className="p-5 space-y-4">
            {/* Lifecycle */}
            {lc && (
              <TraceSection icon={Route} title="Канонічний шлях" count={`${lc.progress}/${lc.total_steps}`}>
                <div className="flex flex-wrap gap-1.5">
                  {lc.steps.map((s) => {
                    const I = TRACE_STEP_ICON[s.key] || Coins;
                    const done = s.status === 'done';
                    return (
                      <span key={s.key}
                        className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg ${done ? 'bg-[#2E5D4F]/10 text-[#2E5D4F]' : s.status === 'current' ? 'bg-amber-500/10 text-amber-600' : 'bg-app-elevated text-token-muted'}`}>
                        <I className="w-3 h-3" /> {s.label}
                      </span>
                    );
                  })}
                </div>
              </TraceSection>
            )}

            <TraceSection icon={FileText} title="Інвестиції" count={trace.investments.length}>
              {trace.investments.map((i) => (
                <Row key={i.id} left={i.asset_title || i.id} right={formatUAH(i.amount)} sub={`${i.status} · ${formatDateUk(i.created_at)}`} />
              ))}
              {trace.investments.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={CreditCard} title="Платежі" count={trace.payments.length}>
              {trace.payments.map((p) => (
                <Row key={p.id} left={p.method || 'Оплата'} right={formatUAH(p.amount_uah || p.amount)} sub={`${p.status} · ${formatDateUk(p.created_at)}`} />
              ))}
              {trace.payments.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={Coins} title="Леджер" count={trace.ledger.length}>
              {trace.ledger.slice(0, 8).map((l) => (
                <Row key={l.id} left={l.type || l.entry_type || 'запис'} right={formatUAH(l.amount_uah || l.amount)} sub={formatDateUk(l.created_at)} />
              ))}
              {trace.ledger.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={Award} title="Сертифікати" count={trace.certificates.length}>
              {trace.certificates.map((c) => (
                <Row key={c.id} left={c.certificate_number} right={`${nfmt(c.units)} од.`} sub={`${c.status} · ${formatDateUk(c.issue_date)}`} />
              ))}
              {trace.certificates.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={Banknote} title="Виплати" count={trace.payouts.length}>
              {trace.payouts.slice(0, 8).map((p) => (
                <Row key={p.id} left={p.period || 'Виплата'} right={formatUAH(p.amount_uah || p.amount)} sub={`${p.status || ''} · ${formatDateUk(p.created_at)}`} />
              ))}
              {trace.payouts.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={Repeat} title="Вторинні угоди" count={trace.secondary_trades.length}>
              {trace.secondary_trades.map((t) => (
                <Row key={t.id} left={t.buyer_id === trace.investor_id ? 'Купівля' : 'Продаж'} right={formatUAH(t.units_uah || t.amount_uah)} sub={`${t.status} · ${formatDateUk(t.created_at)}`} />
              ))}
              {trace.secondary_trades.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>

            <TraceSection icon={Activity} title="Події володіння" count={trace.ownership_events.length}>
              {trace.ownership_events.slice(0, 10).map((e) => (
                <Row key={e.id} left={e.kind || e.event_type}
                  right={`${e.delta_units >= 0 ? '+' : ''}${nfmt(e.delta_units)}`}
                  sub={formatDateUk(e.created_at)} />
              ))}
              {trace.ownership_events.length === 0 && <div className="text-sm text-token-muted">—</div>}
            </TraceSection>
          </div>
        )}
      </div>
    </div>
  );
}
