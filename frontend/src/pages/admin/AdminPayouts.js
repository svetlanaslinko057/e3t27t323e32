import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatPercent, formatDateUk, lumenError, UAH_PER_USD } from '@/lib/lumenApi';
import {
  Coins, Plus, Loader2, X, CheckCircle2, AlertCircle, Calculator,
  PlayCircle, Send, Ban, Layers, FileSpreadsheet, Pause, Play, BookOpen,
} from 'lucide-react';

/** Sprint 8 — Admin Payout Engine (Plans + Batches) */

const TYPE_LABELS = {
  rental_income: 'Орендний дохід', profit_share: 'Розподіл прибутку',
  exit_distribution: 'Виплата при виході', manual: 'Ручне нарахування',
};
const FREQ_LABELS = {
  one_time: 'Разово', monthly: 'Щомісячно', quarterly: 'Щоквартально', annual: 'Щорічно',
};
const BATCH_BADGE = {
  generated: { label: 'Сформовано', cls: 'bg-sky-100 text-sky-800' },
  approved:  { label: 'Схвалено',   cls: 'bg-indigo-100 text-indigo-800' },
  credited:  { label: 'Нараховано', cls: 'bg-emerald-100 text-emerald-800' },
  cancelled: { label: 'Скасовано',  cls: 'bg-red-100 text-red-700' },
};
const PLAN_BADGE = {
  active: { label: 'Активний', cls: 'bg-emerald-100 text-emerald-800' },
  paused: { label: 'Призупинено', cls: 'bg-amber-100 text-amber-800' },
  ended:  { label: 'Завершено', cls: 'bg-muted text-muted-foreground' },
};

export default function AdminPayouts() {
  const [tab, setTab] = useState('plans');
  const [flash, setFlash] = useState('');
  const [error, setError] = useState('');

  const flashOk = (m) => { setFlash(m); setError(''); setTimeout(() => setFlash(''), 4000); };

  return (
    <div className="p-6 md:p-10" data-testid="admin-payouts">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Двигун доходності</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Виплати доходу</h1>
        <p className="mt-1 text-token-muted">
          Створюйте плани нарахувань, розподіляйте дохід між власниками за часткою та проводьте пакети у реєстр.
        </p>
      </header>

      {flash && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {flash}</div>}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      <div className="flex gap-2 mb-6 border-b border-border">
        {[['plans', 'Плани нарахувань', Coins], ['batches', 'Пакети виплат', Layers]].map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`}
            className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition ${
              tab === k ? 'border-[#2E5D4F] text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </div>

      {tab === 'plans'
        ? <PlansTab onError={setError} onOk={flashOk} />
        : <BatchesTab onError={setError} onOk={flashOk} />}
    </div>
  );
}

/* ───────────────────────────── Plans ───────────────────────────── */

function PlansTab({ onError, onOk }) {
  const [plans, setPlans] = useState([]);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [preview, setPreview] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, a] = await Promise.all([
        lumen.get('/admin/payout-plans'),
        lumen.get('/assets?limit=100'),
      ]);
      setPlans(p.data?.items || []);
      setAssets(a.data?.items || []);
    } catch (e) { onError(lumenError(e, 'Не вдалось завантажити плани')); }
    finally { setLoading(false); }
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  const recalc = async (id) => {
    try {
      const r = await lumen.post(`/admin/payout-plans/${id}/recalculate`, {});
      setPreview(r.data);
    } catch (e) { onError(lumenError(e, 'Не вдалось перерахувати')); }
  };

  const generate = async (id) => {
    if (!window.confirm('Згенерувати пакет виплат за цим планом?')) return;
    try {
      await lumen.post(`/admin/payout-plans/${id}/generate`, {});
      onOk('Пакет виплат сформовано. Перейдіть у «Пакети виплат» для проведення.');
      load();
    } catch (e) { onError(lumenError(e, 'Не вдалось згенерувати пакет')); }
  };

  const toggleStatus = async (p) => {
    const next = p.status === 'active' ? 'paused' : 'active';
    try {
      await lumen.patch(`/admin/payout-plans/${p.id}`, { status: next });
      onOk(next === 'active' ? 'План активовано.' : 'План призупинено.');
      load();
    } catch (e) { onError(lumenError(e, 'Не вдалось оновити план')); }
  };

  return (
    <div data-testid="plans-tab">
      <div className="flex justify-end mb-4">
        <button onClick={() => setShowCreate(true)} data-testid="btn-create-plan"
          className="inline-flex items-center gap-2 px-5 h-11 rounded-full bg-[#2E5D4F] text-white font-medium">
          <Plus className="w-4 h-4" /> Створити план
        </button>
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2].map((i) => <div key={i} className="h-20 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : plans.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="plans-empty">
          <Coins className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Планів нарахувань ще немає</p>
          <p className="text-sm text-muted-foreground mt-1">Створіть перший план, щоб почати нараховувати дохід інвесторам.</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3" data-testid="plans-list">
          {plans.map((p) => {
            const b = PLAN_BADGE[p.status] || { label: p.status_label, cls: 'bg-muted' };
            return (
              <div key={p.id} data-testid={`plan-${p.id}`} className="rounded-2xl border border-border bg-card p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{p.asset_title}</p>
                    <p className="text-xs text-muted-foreground">{p.type_label} · {p.frequency_label}</p>
                  </div>
                  <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                </div>
                <p className="mt-3 text-2xl font-bold tabular-nums">{formatUAH(p.expected_amount)}<span className="text-sm font-normal text-muted-foreground"> / період</span></p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button onClick={() => recalc(p.id)} data-testid={`recalc-${p.id}`}
                    className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full border border-border hover:border-[#2E5D4F] text-xs font-medium">
                    <Calculator className="w-3.5 h-3.5" /> Розрахувати
                  </button>
                  <button onClick={() => generate(p.id)} data-testid={`generate-${p.id}`}
                    disabled={p.status !== 'active'}
                    className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full bg-[#2E5D4F] text-white text-xs font-medium disabled:opacity-50">
                    <FileSpreadsheet className="w-3.5 h-3.5" /> Згенерувати пакет
                  </button>
                  {p.status !== 'ended' && (
                    <button onClick={() => toggleStatus(p)} data-testid={`toggle-${p.id}`}
                      className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full border border-border hover:border-amber-400 text-xs font-medium">
                      {p.status === 'active' ? <><Pause className="w-3.5 h-3.5" /> Призупинити</> : <><Play className="w-3.5 h-3.5" /> Активувати</>}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showCreate && (
        <CreatePlanModal assets={assets} onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); onOk('План нарахувань створено.'); load(); }}
          onError={onError} />
      )}
      {preview && <RecalcPreviewModal data={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function CreatePlanModal({ assets, onClose, onCreated, onError }) {
  const [assetId, setAssetId] = useState(assets[0]?.id || '');
  const [type, setType] = useState('rental_income');
  const [frequency, setFrequency] = useState('monthly');
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [acting, setActing] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    setErr('');
    if (!assetId) { setErr('Оберіть актив'); return; }
    const amt = Number(amount);
    if (!amt || amt <= 0) { setErr('Вкажіть суму'); return; }
    setActing(true);
    try {
      await lumen.post('/admin/payout-plans', {
        asset_id: assetId, type, frequency, expected_amount: amt * UAH_PER_USD, notes: notes.trim() || null,
      });
      onCreated();
    } catch (e) { setErr(lumenError(e, 'Не вдалось створити план')); }
    finally { setActing(false); }
  };

  return (
    <Drawer title="Новий план нарахувань" onClose={onClose} testid="create-plan-modal">
      <label className="block">
        <span className="text-xs uppercase tracking-widest text-muted-foreground">Актив</span>
        <select value={assetId} onChange={(e) => setAssetId(e.target.value)} data-testid="plan-asset"
          className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm">
          {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-muted-foreground">Тип</span>
          <select value={type} onChange={(e) => setType(e.target.value)} data-testid="plan-type"
            className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm">
            {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-widest text-muted-foreground">Частота</span>
          <select value={frequency} onChange={(e) => setFrequency(e.target.value)} data-testid="plan-frequency"
            className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm">
            {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      <label className="block">
        <span className="text-xs uppercase tracking-widest text-muted-foreground">Сума за період (USD)</span>
        <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="plan-amount"
          placeholder="напр. 4000" className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm" />
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-widest text-muted-foreground">Примітка</span>
        <input value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="plan-notes"
          className="mt-1 w-full h-11 rounded-lg border border-border bg-background px-3 text-sm" />
      </label>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button onClick={submit} disabled={acting} data-testid="submit-plan"
        className="w-full inline-flex items-center justify-center gap-2 px-5 h-11 rounded-full bg-[#2E5D4F] text-white font-medium disabled:opacity-60">
        {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Створити план
      </button>
    </Drawer>
  );
}

function RecalcPreviewModal({ data, onClose }) {
  return (
    <Drawer title="Попередній розподіл" onClose={onClose} testid="recalc-preview">
      <div className="rounded-xl bg-muted/40 border border-border p-3 text-sm">
        <p className="font-semibold">{data.plan.asset_title}</p>
        <p className="text-muted-foreground">{data.plan.type_label} · {formatUAH(data.plan.expected_amount)} / період</p>
      </div>
      <p className="text-xs uppercase tracking-widest text-muted-foreground">Розподіл між {data.investor_count} власниками</p>
      <div className="rounded-xl border border-border divide-y divide-border" data-testid="preview-allocations">
        {data.allocations.map((a, i) => (
          <div key={i} className="flex items-center justify-between p-3 text-sm">
            <div className="min-w-0">
              <p className="font-medium truncate">{a.investor_name || a.investor_email || a.investor_id}</p>
              <p className="text-xs text-muted-foreground">частка {formatPercent(a.share_percent)}</p>
            </div>
            <span className="font-mono font-semibold tabular-nums">{formatUAH(a.amount)}</span>
          </div>
        ))}
      </div>
      <div className="flex justify-between font-semibold pt-1">
        <span>Разом</span><span className="tabular-nums">{formatUAH(data.total_amount)}</span>
      </div>
    </Drawer>
  );
}

/* ───────────────────────────── Batches ───────────────────────────── */

function BatchesTab({ onError, onOk }) {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/payout-batches' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (e) { onError(lumenError(e, 'Не вдалось завантажити пакети')); }
    finally { setLoading(false); }
  }, [filter, onError]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try { setSelected((await lumen.get(`/admin/payout-batches/${id}`)).data); }
    catch (e) { onError(lumenError(e, 'Не вдалось відкрити пакет')); }
  };

  const afterAction = async (msg) => { onOk(msg); await load(); setSelected(null); };

  const FILTERS = [['', 'Всі'], ['generated', 'Сформовані'], ['approved', 'Схвалені'], ['credited', 'Нараховані'], ['cancelled', 'Скасовані']];

  return (
    <div data-testid="batches-tab">
      <div className="flex flex-wrap gap-2 mb-4">
        {FILTERS.map(([v, label]) => (
          <button key={v} onClick={() => setFilter(v)} data-testid={`bfilter-${v || 'all'}`}
            className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-xs font-medium border ${
              filter === v ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'}`}>
            {label}{counts[v] !== undefined && <span className="px-1.5 rounded bg-muted text-foreground">{counts[v]}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-14 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="batches-empty">
          <Layers className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Пакетів немає</p>
          <p className="text-sm text-muted-foreground mt-1">Згенеруйте пакет у вкладці «Плани нарахувань».</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="batches-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Актив</th>
                <th className="text-left px-4 py-3 font-medium">Період</th>
                <th className="text-right px-4 py-3 font-medium">Сума</th>
                <th className="text-center px-4 py-3 font-medium">Виплат</th>
                <th className="text-right px-4 py-3 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => {
                const badge = BATCH_BADGE[b.status] || { label: b.status_label, cls: 'bg-muted' };
                return (
                  <tr key={b.id} onClick={() => openDetail(b.id)} data-testid={`batch-row-${b.id}`}
                    className="border-t border-border cursor-pointer hover:bg-muted/30 transition">
                    <td className="px-4 py-3"><p className="font-medium">{b.asset_title}</p><p className="text-xs text-muted-foreground">{b.type_label}</p></td>
                    <td className="px-4 py-3">{b.period_label}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold tabular-nums">{formatUAH(b.total_amount_uah)}</td>
                    <td className="px-4 py-3 text-center">{b.payout_count}</td>
                    <td className="px-4 py-3 text-right"><span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badge.cls}`}>{badge.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && <BatchDrawer data={selected} onClose={() => setSelected(null)} onActed={afterAction} onError={onError} />}
    </div>
  );
}

function BatchDrawer({ data, onClose, onActed, onError }) {
  const b = data.batch;
  const records = data.records || [];
  const [acting, setActing] = useState(false);
  const badge = BATCH_BADGE[b.status] || { label: b.status_label, cls: 'bg-muted' };

  const act = async (action) => {
    if (action === 'credit' && !window.confirm(
      `Нарахувати ${formatUAH(b.total_amount_uah)} (${b.payout_count} виплат)? Це створить проводки у реєстрі та поповнить гаманці інвесторів.`)) return;
    if (action === 'cancel' && !window.confirm('Скасувати пакет? Усі виплати в ньому буде скасовано.')) return;
    setActing(true);
    try {
      await lumen.post(`/admin/payout-batches/${b.id}/${action}`, {});
      const msgs = { approve: 'Пакет схвалено.', credit: 'Пакет нараховано — кошти на гаманцях інвесторів.', cancel: 'Пакет скасовано.' };
      onActed(msgs[action]);
    } catch (e) { onError(lumenError(e, 'Не вдалось виконати дію')); setActing(false); }
  };

  return (
    <Drawer title={`Пакет · ${b.asset_title}`} subtitle={`${b.type_label} · ${b.period_label}`} onClose={onClose} testid="batch-drawer" wide>
      <div className="flex items-baseline justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-token-muted">Сума пакета</p>
          <p className="text-3xl font-bold tabular-nums mt-1">{formatUAH(b.total_amount_uah)}</p>
          <p className="text-xs text-muted-foreground">{b.payout_count} виплат · план. дата {formatDateUk(b.planned_date)}</p>
        </div>
        <span className={`text-sm font-medium px-3 py-1 rounded-full ${badge.cls}`}>{badge.label}</span>
      </div>

      {/* D2 — UA withholding tax breakdown (gross / ПДФО+ВЗ / net) */}
      {b.taxable && (b.total_tax_uah > 0 || b.total_gross_uah) && (
        <div className="grid grid-cols-3 gap-3" data-testid="batch-tax-breakdown">
          <div className="rounded-xl border border-border bg-muted/40 p-3">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Нараховано (gross)</p>
            <p className="text-lg font-semibold tabular-nums">{formatUAH(b.total_gross_uah)}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-amber-700">Податок (утримання)</p>
            <p className="text-lg font-semibold tabular-nums text-amber-800">−{formatUAH(b.total_tax_uah)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-emerald-700">До виплати (net)</p>
            <p className="text-lg font-semibold tabular-nums text-emerald-800">{formatUAH(b.total_net_uah)}</p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2" data-testid="batch-actions">
        {b.status === 'generated' && (
          <button onClick={() => act('approve')} disabled={acting} data-testid="batch-approve"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-indigo-600 text-white font-medium disabled:opacity-50">
            {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Схвалити
          </button>
        )}
        {b.status === 'approved' && (
          <button onClick={() => act('credit')} disabled={acting} data-testid="batch-credit"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-emerald-600 text-white font-medium disabled:opacity-50">
            {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Нарахувати (credit)
          </button>
        )}
        {(b.status === 'generated' || b.status === 'approved') && (
          <button onClick={() => act('cancel')} disabled={acting} data-testid="batch-cancel"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-red-300 text-red-700 font-medium disabled:opacity-50">
            <Ban className="w-4 h-4" /> Скасувати
          </button>
        )}
        {b.status === 'credited' && (
          <p className="text-sm text-emerald-700 flex items-center gap-1.5" data-testid="batch-credited-note"><CheckCircle2 className="w-4 h-4" /> Нараховано {formatDateUk(b.credited_at)}</p>
        )}
        {b.status === 'cancelled' && (
          <p className="text-sm text-muted-foreground" data-testid="batch-cancelled-note">Пакет скасовано.</p>
        )}
      </div>

      {/* Records */}
      <section data-testid="batch-records">
        <h3 className="font-semibold mb-2 text-sm">Виплати інвесторам ({records.length})</h3>
        <div className="rounded-xl border border-border divide-y divide-border">
          {records.map((r) => (
            <div key={r.id} className="flex items-center justify-between p-3 text-sm" data-testid={`batch-record-${r.id}`}>
              <div className="min-w-0">
                <p className="font-medium truncate">{r.investor_name || r.investor_email || r.investor_id}</p>
                <p className="text-xs text-muted-foreground">частка {formatPercent(r.share_percent)} · {r.status_label}</p>
              </div>
              <span className="font-mono font-semibold tabular-nums">{formatUAH(r.amount_uah)}</span>
            </div>
          ))}
        </div>
      </section>
    </Drawer>
  );
}

/* ───────────────────────────── Shared Drawer ───────────────────────────── */

function Drawer({ title, subtitle, children, onClose, testid, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid={testid}>
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className={`relative w-full ${wide ? 'max-w-2xl' : 'max-w-md'} h-full bg-background border-l border-border shadow-2xl overflow-y-auto`}>
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">{title}</h2>
            {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg" data-testid="drawer-close"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4">{children}</div>
      </div>
    </div>
  );
}
