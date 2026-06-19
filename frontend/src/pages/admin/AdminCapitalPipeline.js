import { useEffect, useState, useCallback } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError, UAH_PER_USD } from '@/lib/lumenApi';
import {
  Workflow, Plus, Loader2, X, Trash2, ArrowRight, Ban, FileText,
  Gavel, Layers, ClipboardList, ShieldCheck, CheckCircle2, XCircle,
  MinusCircle, Building2, MapPin, User, Tag, Eye, EyeOff, Lock, Upload,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';

const STAGE_COLORS = {
  lead: 'bg-slate-100 text-slate-700 border-slate-200',
  screening: 'bg-sky-100 text-sky-700 border-sky-200',
  due_diligence: 'bg-amber-100 text-amber-700 border-amber-200',
  committee: 'bg-violet-100 text-violet-700 border-violet-200',
  funding: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  live: 'bg-teal-100 text-teal-700 border-teal-200',
  operating: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  exited: 'bg-zinc-200 text-zinc-700 border-zinc-300',
  rejected: 'bg-rose-100 text-rose-700 border-rose-200',
};
const VIS_LABEL = { public: 'Публічний', investor: 'Інвестор', admin: 'Адмін' };
const VIS_ICON = { public: Eye, investor: EyeOff, admin: Lock };
const CAT_LABEL = {
  financial_model: 'Фінмодель', valuation: 'Оцінка', contracts: 'Договори',
  photos: 'Фото', reports: 'Звіти', due_diligence: 'Due Diligence', other: 'Інше',
};

function Field({ label, value, onChange, type = 'text', placeholder, testid }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        data-testid={testid}
        className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm mt-1" />
    </div>
  );
}

export default function AdminCapitalPipeline() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [operators, setOperators] = useState([]);
  const [assets, setAssets] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [d, ops, as] = await Promise.all([
        lumen.get('/admin/deals'),
        lumen.get('/admin/operators'),
        lumen.get('/assets'),
      ]);
      setData(d.data);
      setOperators(ops.data.items || []);
      const list = Array.isArray(as.data) ? as.data : (as.data.items || as.data.assets || []);
      setAssets(list);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;
  }

  const stages = (data?.stages || []).filter((s) => s !== 'rejected');
  const labels = data?.stage_labels || {};
  const counts = data?.counts || {};
  const items = data?.items || [];
  const byStage = (s) => items.filter((d) => d.stage === s);

  return (
    <div className="p-6 space-y-5" data-testid="admin-capital-pipeline">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Capital Formation OS · Phase E</div>
          <h1 className="text-2xl font-bold">Воронка сделок</h1>
          <p className="text-sm text-muted-foreground mt-1">Від ліда до виходу — повний життєвий цикл та історія рішень.</p>
        </div>
        <button onClick={() => setShowCreate(true)} data-testid="deal-create-open"
          className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
          <Plus className="w-4 h-4" /> Нова сделка
        </button>
      </div>

      {/* Kanban board */}
      <div className="overflow-x-auto pb-3">
        <div className="flex gap-3 min-w-max" data-testid="pipeline-board">
          {stages.map((s) => (
            <div key={s} className="w-[270px] flex-shrink-0">
              <div className={`rounded-t-xl border px-3 py-2 flex items-center justify-between ${STAGE_COLORS[s] || 'bg-muted'}`}>
                <span className="text-xs font-semibold">{labels[s] || s}</span>
                <span className="text-xs font-bold">{counts[s] || 0}</span>
              </div>
              <div className="rounded-b-xl border border-t-0 border-border bg-card p-2 space-y-2 min-h-[120px]">
                {byStage(s).map((d) => (
                  <button key={d.id} onClick={() => setOpenId(d.id)} data-testid={`deal-card-${d.id}`}
                    className="w-full text-left rounded-lg border border-border bg-background p-3 hover:border-foreground/30 transition">
                    <div className="font-medium text-sm leading-snug">{d.title}</div>
                    <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <MapPin className="w-3 h-3" />{d.region || '—'}
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground flex items-center gap-1.5">
                      <Tag className="w-3 h-3" />{d.asset_type || '—'}
                    </div>
                    <div className="mt-2 text-sm font-semibold" style={{ color: PRIMARY }}>{formatUAH(d.asking_price_uah)}</div>
                  </button>
                ))}
                {byStage(s).length === 0 && <p className="text-[11px] text-muted-foreground text-center py-4">Порожньо</p>}
              </div>
            </div>
          ))}
          {/* rejected column */}
          <div className="w-[270px] flex-shrink-0">
            <div className={`rounded-t-xl border px-3 py-2 flex items-center justify-between ${STAGE_COLORS.rejected}`}>
              <span className="text-xs font-semibold">{labels.rejected || 'Відхилено'}</span>
              <span className="text-xs font-bold">{counts.rejected || 0}</span>
            </div>
            <div className="rounded-b-xl border border-t-0 border-border bg-card p-2 space-y-2 min-h-[120px]">
              {byStage('rejected').map((d) => (
                <button key={d.id} onClick={() => setOpenId(d.id)} data-testid={`deal-card-${d.id}`}
                  className="w-full text-left rounded-lg border border-border bg-background p-3 hover:border-foreground/30 transition opacity-80">
                  <div className="font-medium text-sm leading-snug">{d.title}</div>
                  <div className="mt-1 text-[11px] text-rose-600 line-clamp-2">{d.rejection_reason}</div>
                </button>
              ))}
              {byStage('rejected').length === 0 && <p className="text-[11px] text-muted-foreground text-center py-4">Порожньо</p>}
            </div>
          </div>
        </div>
      </div>

      {showCreate && (
        <CreateDealModal operators={operators} assets={assets}
          onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />
      )}
      {openId && (
        <DealDrawer dealId={openId} operators={operators} assets={assets}
          onClose={() => setOpenId(null)} onChanged={load} />
      )}
    </div>
  );
}

function CreateDealModal({ operators, assets, onClose, onCreated }) {
  const [f, setF] = useState({ title: '', source: 'inbound', owner_name: '', region: '', asset_type: 'real_estate', asking_price_uah: '', team_valuation_uah: '', operator_id: '', linked_asset_id: '', description: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    if (!f.title.trim()) { setErr('Вкажіть назву'); return; }
    setBusy(true); setErr('');
    try {
      await lumen.post('/admin/deals', {
        ...f,
        asking_price_uah: (Number(f.asking_price_uah) || 0) * UAH_PER_USD,
        team_valuation_uah: (Number(f.team_valuation_uah) || 0) * UAH_PER_USD,
        operator_id: f.operator_id || null,
        linked_asset_id: f.linked_asset_id || null,
      });
      onCreated();
    } catch (e) { setErr(lumenError(e, 'Не вдалося створити')); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-card rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()} data-testid="deal-create-modal">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">Нова сделка</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <div className="md:col-span-2"><Field label="Назва" value={f.title} onChange={(v) => setF({ ...f, title: v })} testid="deal-title" placeholder="Бізнес-центр…" /></div>
          <Field label="Джерело" value={f.source} onChange={(v) => setF({ ...f, source: v })} placeholder="inbound / broker / operator" />
          <Field label="Власник" value={f.owner_name} onChange={(v) => setF({ ...f, owner_name: v })} />
          <Field label="Регіон" value={f.region} onChange={(v) => setF({ ...f, region: v })} />
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Тип</label>
            <select value={f.asset_type} onChange={(e) => setF({ ...f, asset_type: e.target.value })}
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              {['real_estate', 'commercial', 'land', 'construction'].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <Field label="Запитувана ціна, $" type="number" value={f.asking_price_uah} onChange={(v) => setF({ ...f, asking_price_uah: v })} testid="deal-asking" />
          <Field label="Оцінка команди, $" type="number" value={f.team_valuation_uah} onChange={(v) => setF({ ...f, team_valuation_uah: v })} />
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Оператор</label>
            <select value={f.operator_id} onChange={(e) => setF({ ...f, operator_id: e.target.value })}
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              <option value="">—</option>
              {operators.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Пов'язаний актив</label>
            <select value={f.linked_asset_id} onChange={(e) => setF({ ...f, linked_asset_id: e.target.value })}
              className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              <option value="">—</option>
              {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Опис</label>
            <textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} rows={3}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm mt-1" />
          </div>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="h-10 px-4 rounded-lg text-sm border border-border">Скасувати</button>
          <button onClick={submit} disabled={busy} data-testid="deal-create-submit"
            className="h-10 px-5 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Створити
          </button>
        </div>
      </div>
    </div>
  );
}

function DealDrawer({ dealId, operators, assets, onClose, onChanged }) {
  const [deal, setDeal] = useState(null);
  const [tab, setTab] = useState('overview');
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try { const r = await lumen.get(`/admin/deals/${dealId}`); setDeal(r.data); }
    catch (_e) { /* noop */ } finally { setLoading(false); }
  }, [dealId]);
  useEffect(() => { reload(); }, [reload]);

  const TABS = [
    ['overview', 'Огляд', ClipboardList],
    ['committee', 'Комітет', Gavel],
    ['dataroom', 'Data Room', FileText],
    ['raise', 'Збір та розподіл', Layers],
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex justify-end" onClick={onClose}>
      <div className="bg-background w-full max-w-2xl h-full overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="deal-drawer">
        {loading || !deal ? (
          <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>
        ) : (
          <>
            <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-start justify-between z-10">
              <div>
                <div className={`inline-flex items-center text-[11px] px-2 py-0.5 rounded-full border ${STAGE_COLORS[deal.stage]}`}>{deal.stage_label}</div>
                <h2 className="text-lg font-bold mt-1.5">{deal.title}</h2>
                <p className="text-xs text-muted-foreground">{deal.owner_name} · {deal.region}</p>
              </div>
              <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>

            <div className="flex border-b border-border px-3 bg-card overflow-x-auto">
              {TABS.map(([k, l, Icon]) => (
                <button key={k} onClick={() => setTab(k)} data-testid={`deal-tab-${k}`}
                  className={`px-3 py-2.5 text-sm font-medium inline-flex items-center gap-1.5 border-b-2 whitespace-nowrap ${tab === k ? 'border-current' : 'border-transparent text-muted-foreground'}`}
                  style={tab === k ? { color: PRIMARY } : {}}>
                  <Icon className="w-4 h-4" />{l}
                </button>
              ))}
            </div>

            <div className="p-5">
              {tab === 'overview' && <OverviewTab deal={deal} reload={reload} onChanged={onChanged} onClose={onClose} />}
              {tab === 'committee' && <CommitteeTab dealId={dealId} reload={reload} onChanged={onChanged} />}
              {tab === 'dataroom' && <DataRoomTab dealId={dealId} />}
              {tab === 'raise' && <RaiseTab deal={deal} assets={assets} reload={reload} />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function OverviewTab({ deal, reload, onChanged, onClose }) {
  const [toStage, setToStage] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const stages = ['lead', 'screening', 'due_diligence', 'committee', 'funding', 'live', 'operating', 'exited'];

  const move = async () => {
    if (!toStage) return;
    setBusy(true);
    try { await lumen.post(`/admin/deals/${deal.id}/transition`, { to_stage: toStage, note }); setToStage(''); setNote(''); reload(); onChanged?.(); }
    catch (_e) { /* noop */ } finally { setBusy(false); }
  };
  const reject = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    try { await lumen.post(`/admin/deals/${deal.id}/reject`, { reason }); reload(); onChanged?.(); }
    catch (_e) { /* noop */ } finally { setBusy(false); }
  };
  const del = async () => {
    if (!window.confirm('Видалити сделку?')) return;
    try { await lumen.delete(`/admin/deals/${deal.id}`); onChanged?.(); onClose?.(); } catch (_e) { /* noop */ }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        {[['Джерело', deal.source], ['Тип', deal.asset_type], ['Запитувана ціна', formatUAH(deal.asking_price_uah)], ['Оцінка команди', formatUAH(deal.team_valuation_uah)], ['Оператор', deal.operator_name || '—'], ['Пов\'язаний актив', deal.linked_asset_title || '—']].map(([l, v]) => (
          <div key={l} className="rounded-lg border border-border p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</div>
            <div className="text-sm font-medium mt-0.5">{v}</div>
          </div>
        ))}
      </div>
      {deal.description && <p className="text-sm text-muted-foreground">{deal.description}</p>}
      {deal.rejection_reason && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          <strong>Причина відхилення:</strong> {deal.rejection_reason}
        </div>
      )}

      {deal.stage !== 'rejected' && (
        <div className="rounded-xl border border-border p-4 space-y-3">
          <div className="text-sm font-semibold flex items-center gap-1.5"><ArrowRight className="w-4 h-4" /> Перемістити стадію</div>
          <div className="flex gap-2">
            <select value={toStage} onChange={(e) => setToStage(e.target.value)} data-testid="transition-select"
              className="flex-1 h-10 rounded-lg border border-border bg-background px-2 text-sm">
              <option value="">Оберіть стадію…</option>
              {stages.filter((s) => s !== deal.stage).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={move} disabled={busy || !toStage} data-testid="transition-btn"
              className="h-10 px-4 rounded-lg text-sm font-medium text-white" style={{ background: PRIMARY }}>Перемістити</button>
          </div>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Коментар (необов'язково)"
            className="w-full h-9 rounded-lg border border-border bg-background px-3 text-sm" />
        </div>
      )}

      {deal.stage !== 'rejected' && (
        <div className="rounded-xl border border-rose-200 p-4 space-y-2">
          <div className="text-sm font-semibold text-rose-700 flex items-center gap-1.5"><Ban className="w-4 h-4" /> Відхилити сделку</div>
          <div className="flex gap-2">
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина відхилення" data-testid="reject-reason"
              className="flex-1 h-10 rounded-lg border border-border bg-background px-3 text-sm" />
            <button onClick={reject} disabled={busy || !reason.trim()} data-testid="reject-btn"
              className="h-10 px-4 rounded-lg text-sm font-medium text-white bg-rose-600">Відхилити</button>
          </div>
        </div>
      )}

      <div>
        <div className="text-sm font-semibold mb-2">Історія</div>
        <div className="space-y-2">
          {(deal.events || []).map((e) => (
            <div key={e.id} className="flex items-start gap-2 text-sm">
              <span className="mt-1 w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
              <div>
                <span className="font-medium">{e.kind}</span>
                {e.detail?.to && <span className="text-muted-foreground"> → {e.detail.to}</span>}
                {e.detail?.reason && <span className="text-rose-600"> · {e.detail.reason}</span>}
                <div className="text-[11px] text-muted-foreground">{e.actor_name || 'system'} · {formatDateUk(e.created_at)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <button onClick={del} className="text-xs text-rose-600 inline-flex items-center gap-1"><Trash2 className="w-3.5 h-3.5" /> Видалити сделку</button>
    </div>
  );
}

function CommitteeTab({ dealId, reload, onChanged }) {
  const [c, setC] = useState(null);
  const [memo, setMemo] = useState({ opportunity: '', market: '', financials: '', exit: '', recommendation: '' });
  const [risk, setRisk] = useState({ summary: '', rating: 'medium' });
  const [fin, setFin] = useState({ summary: '', rating: 'fair' });
  const [busy, setBusy] = useState(false);

  const loadC = useCallback(async () => {
    const r = await lumen.get(`/admin/deals/${dealId}/committee`);
    setC(r.data);
    setMemo({ opportunity: '', market: '', financials: '', exit: '', recommendation: '', ...(r.data.memo || {}) });
    if (r.data.risk_review?.summary) setRisk({ summary: r.data.risk_review.summary, rating: r.data.risk_review.rating || 'medium' });
    if (r.data.financial_review?.summary) setFin({ summary: r.data.financial_review.summary, rating: r.data.financial_review.rating || 'fair' });
  }, [dealId]);
  useEffect(() => { loadC(); }, [loadC]);

  const saveMemo = async () => { setBusy(true); try { await lumen.put(`/admin/deals/${dealId}/memo`, { fields: memo }); await loadC(); } finally { setBusy(false); } };
  const saveRisk = async () => { setBusy(true); try { await lumen.put(`/admin/deals/${dealId}/risk-review`, risk); await loadC(); } finally { setBusy(false); } };
  const saveFin = async () => { setBusy(true); try { await lumen.put(`/admin/deals/${dealId}/financial-review`, fin); await loadC(); } finally { setBusy(false); } };
  const vote = async (v) => { try { await lumen.post(`/admin/deals/${dealId}/vote`, { vote: v }); await loadC(); } catch (_e) {} };
  const decide = async (d) => { try { await lumen.post(`/admin/deals/${dealId}/decision`, { decision: d }); await loadC(); reload(); onChanged?.(); } catch (_e) {} };

  if (!c) return <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-5">
      {/* Memo */}
      <section className="rounded-xl border border-border p-4 space-y-2">
        <div className="text-sm font-semibold flex items-center gap-1.5"><ClipboardList className="w-4 h-4" /> Investment Memo</div>
        {[['opportunity', 'Можливість'], ['market', 'Ринок'], ['financials', 'Фінанси'], ['exit', 'Стратегія виходу'], ['recommendation', 'Рекомендація']].map(([k, l]) => (
          <div key={k}>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</label>
            <textarea value={memo[k]} onChange={(e) => setMemo({ ...memo, [k]: e.target.value })} rows={2} data-testid={`memo-${k}`}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm mt-1" />
          </div>
        ))}
        <button onClick={saveMemo} disabled={busy} data-testid="memo-save"
          className="h-9 px-4 rounded-lg text-sm font-medium text-white" style={{ background: PRIMARY }}>Зберегти memo</button>
      </section>

      {/* Reviews */}
      <div className="grid md:grid-cols-2 gap-3">
        <section className="rounded-xl border border-border p-4 space-y-2">
          <div className="text-sm font-semibold flex items-center gap-1.5"><ShieldCheck className="w-4 h-4" /> Risk Review</div>
          <textarea value={risk.summary} onChange={(e) => setRisk({ ...risk, summary: e.target.value })} rows={3}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
          <select value={risk.rating} onChange={(e) => setRisk({ ...risk, rating: e.target.value })}
            className="w-full h-9 rounded-lg border border-border bg-background px-2 text-sm">
            {['low', 'medium', 'high'].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button onClick={saveRisk} disabled={busy} className="h-9 px-4 rounded-lg text-sm border border-border w-full">Зберегти</button>
        </section>
        <section className="rounded-xl border border-border p-4 space-y-2">
          <div className="text-sm font-semibold flex items-center gap-1.5"><Layers className="w-4 h-4" /> Financial Review</div>
          <textarea value={fin.summary} onChange={(e) => setFin({ ...fin, summary: e.target.value })} rows={3}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
          <select value={fin.rating} onChange={(e) => setFin({ ...fin, rating: e.target.value })}
            className="w-full h-9 rounded-lg border border-border bg-background px-2 text-sm">
            {['weak', 'fair', 'strong'].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button onClick={saveFin} disabled={busy} className="h-9 px-4 rounded-lg text-sm border border-border w-full">Зберегти</button>
        </section>
      </div>

      {/* Votes */}
      <section className="rounded-xl border border-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold flex items-center gap-1.5"><Gavel className="w-4 h-4" /> Голосування комітету</div>
          <div className="text-xs text-muted-foreground">
            <span className="text-emerald-600 font-semibold">{c.tally.approve} за</span> · <span className="text-rose-600 font-semibold">{c.tally.reject} проти</span> · {c.tally.abstain} утрим.
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => vote('approve')} data-testid="vote-approve" className="flex-1 h-10 rounded-lg border border-emerald-300 text-emerald-700 text-sm inline-flex items-center justify-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> За</button>
          <button onClick={() => vote('reject')} data-testid="vote-reject" className="flex-1 h-10 rounded-lg border border-rose-300 text-rose-700 text-sm inline-flex items-center justify-center gap-1.5"><XCircle className="w-4 h-4" /> Проти</button>
          <button onClick={() => vote('abstain')} className="flex-1 h-10 rounded-lg border border-border text-muted-foreground text-sm inline-flex items-center justify-center gap-1.5"><MinusCircle className="w-4 h-4" /> Утримуюсь</button>
        </div>
        {c.votes.length > 0 && (
          <div className="space-y-1">
            {c.votes.map((v, i) => (
              <div key={i} className="text-xs flex items-center justify-between border-b border-border/50 py-1">
                <span>{v.voter_name}</span>
                <span className={v.vote === 'approve' ? 'text-emerald-600' : v.vote === 'reject' ? 'text-rose-600' : 'text-muted-foreground'}>{v.vote}</span>
              </div>
            ))}
          </div>
        )}
        {c.recommended && <p className="text-xs text-muted-foreground">Рекомендація голосування: <strong>{c.recommended}</strong></p>}
        {c.decision ? (
          <div className={`rounded-lg p-3 text-sm font-medium ${c.decision === 'approved' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
            Рішення: {c.decision === 'approved' ? 'Схвалено' : 'Відхилено'} · {formatDateUk(c.decided_at)}
          </div>
        ) : (
          <div className="flex gap-2 pt-1">
            <button onClick={() => decide('approved')} data-testid="decision-approve" className="flex-1 h-10 rounded-lg text-sm font-medium text-white bg-emerald-600">Схвалити (→ Збір)</button>
            <button onClick={() => decide('rejected')} data-testid="decision-reject" className="flex-1 h-10 rounded-lg text-sm font-medium text-white bg-rose-600">Відхилити</button>
          </div>
        )}
      </section>
    </div>
  );
}

function DataRoomTab({ dealId }) {
  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState({ categories: [], visibility: [] });
  const [f, setF] = useState({ category: 'reports', title: '', url: '', visibility: 'investor' });
  const [busy, setBusy] = useState(false);

  const loadDR = useCallback(async () => {
    const r = await lumen.get('/admin/dataroom', { params: { deal_id: dealId } });
    setItems(r.data.items || []); setMeta({ categories: r.data.categories || [], visibility: r.data.visibility || [] });
  }, [dealId]);
  useEffect(() => { loadDR(); }, [loadDR]);

  const add = async () => {
    if (!f.title.trim()) return;
    setBusy(true);
    try { await lumen.post('/admin/dataroom', { ...f, deal_id: dealId }); setF({ ...f, title: '', url: '' }); loadDR(); }
    catch (_e) {} finally { setBusy(false); }
  };
  const del = async (id) => { try { await lumen.delete(`/admin/dataroom/${id}`); loadDR(); } catch (_e) {} };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-dashed border-border p-4 grid grid-cols-2 gap-2 items-end">
        <div className="col-span-2"><Field label="Назва документа" value={f.title} onChange={(v) => setF({ ...f, title: v })} testid="dr-title" /></div>
        <div className="col-span-2"><Field label="Посилання (URL)" value={f.url} onChange={(v) => setF({ ...f, url: v })} placeholder="https://…" /></div>
        <div>
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Категорія</label>
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
            {meta.categories.map((c) => <option key={c} value={c}>{CAT_LABEL[c] || c}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Доступ</label>
          <select value={f.visibility} onChange={(e) => setF({ ...f, visibility: e.target.value })} data-testid="dr-visibility" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
            {meta.visibility.map((v) => <option key={v} value={v}>{VIS_LABEL[v] || v}</option>)}
          </select>
        </div>
        <button onClick={add} disabled={busy} data-testid="dr-add" className="col-span-2 h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
          <Upload className="w-4 h-4" /> Додати документ
        </button>
      </div>
      <div className="space-y-2">
        {items.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Документів ще немає.</p>}
        {items.map((it) => {
          const Icon = VIS_ICON[it.visibility] || Eye;
          return (
            <div key={it.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <FileText className="w-4 h-4 text-muted-foreground" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{it.title}</div>
                <div className="text-[11px] text-muted-foreground">{CAT_LABEL[it.category] || it.category}</div>
              </div>
              <span className="text-[11px] inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted text-muted-foreground"><Icon className="w-3 h-3" />{VIS_LABEL[it.visibility]}</span>
              <button onClick={() => del(it.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RaiseTab({ deal, assets, reload }) {
  const assetId = deal.linked_asset_id;
  const [bundle, setBundle] = useState(null);
  const [allocs, setAllocs] = useState([]);
  const [policy, setPolicy] = useState('pro_rata');
  const [capacity, setCapacity] = useState('');
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState('');

  const loadRaise = useCallback(async () => {
    if (!assetId) return;
    const [b, a] = await Promise.all([
      lumen.get(`/admin/assets/${assetId}/raise`),
      lumen.get(`/admin/assets/${assetId}/allocations`),
    ]);
    setBundle(b.data); setAllocs(a.data.items || []);
  }, [assetId]);
  useEffect(() => { loadRaise(); }, [loadRaise]);

  const linkAsset = async () => {
    if (!link) return;
    try { await lumen.patch(`/admin/deals/${deal.id}`, { linked_asset_id: link }); reload(); } catch (_e) {}
  };
  const allocate = async () => {
    setBusy(true);
    try {
      await lumen.post(`/admin/assets/${assetId}/allocate`, { policy, capacity_uah: capacity ? Number(capacity) * UAH_PER_USD : null });
      setCapacity(''); loadRaise();
    } catch (_e) {} finally { setBusy(false); }
  };

  if (!assetId) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">Прив'яжіть актив, щоб керувати збором капіталу та розподілом.</p>
        <div className="flex gap-2">
          <select value={link} onChange={(e) => setLink(e.target.value)} className="flex-1 h-10 rounded-lg border border-border bg-background px-2 text-sm">
            <option value="">Оберіть актив…</option>
            {assets.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
          </select>
          <button onClick={linkAsset} disabled={!link} className="h-10 px-4 rounded-lg text-sm font-medium text-white" style={{ background: PRIMARY }}>Прив'язати</button>
        </div>
      </div>
    );
  }
  if (!bundle) return <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />;

  const pct = Math.min(100, bundle.demand_pct);
  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="font-medium">{bundle.asset_title}</span>
          <span className="text-muted-foreground">{formatUAH(bundle.total_demand_uah)} / {formatUAH(bundle.target_uah)}</span>
        </div>
        <div className="h-3 rounded-full bg-muted overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: bundle.oversubscribed ? '#d97706' : PRIMARY }} />
        </div>
        <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Попит: {bundle.demand_pct}%</span>
          {bundle.oversubscribed && <span className="text-amber-600 font-semibold">Переоформлено +{bundle.oversubscription_pct}%</span>}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[['Залучено', bundle.raised_uah], ['Hard commit', bundle.hard_uah], ['Резервації', bundle.reservation_uah], ['Soft commit', bundle.soft_uah], ['Зобов\'язань', bundle.commitments_count], ['В черзі', bundle.waitlist_count]].map(([l, v], i) => (
          <div key={l} className="rounded-lg border border-border p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</div>
            <div className="text-sm font-semibold mt-0.5">{i < 4 ? formatUAH(v) : v}</div>
          </div>
        ))}
      </div>

      {/* Commitments */}
      <section>
        <div className="text-sm font-semibold mb-2">Зобов'язання інвесторів</div>
        <div className="space-y-1.5">
          {(bundle.commitments || []).map((c) => (
            <div key={c.id} className="flex items-center justify-between text-sm border border-border rounded-lg p-2.5">
              <div>
                <span className="font-medium">{c.investor_name}</span>
                <span className="text-[11px] text-muted-foreground ml-2">{c.kind} · {c.segment}</span>
              </div>
              <div className="text-right">
                <div className="font-semibold">{formatUAH(c.amount_uah)}</div>
                {c.allocated_uah > 0 && <div className="text-[11px] text-emerald-600">розподілено {formatUAH(c.allocated_uah)}</div>}
              </div>
            </div>
          ))}
          {(bundle.commitments || []).length === 0 && <p className="text-sm text-muted-foreground">Немає зобов'язань.</p>}
        </div>
      </section>

      {/* Allocation runner */}
      <section className="rounded-xl border border-border p-4 space-y-3">
        <div className="text-sm font-semibold flex items-center gap-1.5"><Layers className="w-4 h-4" /> Двигун розподілу</div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Політика</label>
            <select value={policy} onChange={(e) => setPolicy(e.target.value)} data-testid="alloc-policy" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              <option value="pro_rata">Пропорційно (pro-rata)</option>
              <option value="first_come">Хто перший (first-come)</option>
              <option value="priority">За пріоритетом сегмента</option>
            </select>
          </div>
          <Field label="Ємність, $ (порожньо = залишок)" type="number" value={capacity} onChange={setCapacity} testid="alloc-capacity" />
        </div>
        <button onClick={allocate} disabled={busy} data-testid="alloc-run"
          className="h-10 px-4 rounded-lg text-sm font-medium text-white w-full inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />} Запустити розподіл
        </button>
      </section>

      {/* Allocation history */}
      {allocs.length > 0 && (
        <section>
          <div className="text-sm font-semibold mb-2">Історія розподілів</div>
          {allocs.map((a) => (
            <div key={a.id} className="rounded-lg border border-border p-3 mb-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">v{a.version} · {a.policy}</span>
                <span className="text-muted-foreground text-xs">{formatDateUk(a.created_at)}</span>
              </div>
              <div className="text-[11px] text-muted-foreground mt-1">Ємність {formatUAH(a.capacity_uah)} · попит {formatUAH(a.total_demand_uah)} · переоформлено +{a.oversubscription_pct}%</div>
              <div className="mt-2 space-y-1">
                {a.results.map((r, i) => (
                  <div key={i} className="text-xs flex items-center justify-between">
                    <span>{r.investor_name} <span className="text-muted-foreground">({r.segment})</span></span>
                    <span>{formatUAH(r.allocated_uah)}{r.waitlisted_uah > 0 && <span className="text-amber-600"> · черга {formatUAH(r.waitlisted_uah)}</span>}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
