import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatUAH, formatPercent, formatDateUk } from '@/lib/lumenApi';
import {
  KpiCard, ReputationRing, StatusPill, VerifiedBadge, SeverityIcon,
  VERIFICATION_LABELS, VERIFICATION_TONE, gradeTone,
} from '@/lib/operatorUi';
import {
  Users2, Plus, Loader2, Trash2, Building2, MapPin, Briefcase, X, ShieldCheck,
  FileText, Workflow, Activity, HandCoins, Link2, MessageSquareWarning, RefreshCw, Save,
} from 'lucide-react';

const PRIMARY = '#2E5D4F';
const KIND_LABEL = { internal: 'Внутрішній', external: 'Зовнішній', partner: 'Партнер' };

export default function AdminOperators() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: '', kind: 'external', region: '', specialization: '', contact: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    try { const r = await lumen.get('/admin/operators'); setItems(r.data.items || []); }
    catch (_e) { /* noop */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name.trim()) { setErr('Вкажіть назву'); return; }
    setBusy(true); setErr('');
    try { await lumen.post('/admin/operators', form); setForm({ name: '', kind: 'external', region: '', specialization: '', contact: '' }); load(); }
    catch (e) { setErr(lumenError(e, 'Не вдалося створити')); } finally { setBusy(false); }
  };
  const remove = async (id) => { if (!window.confirm('Видалити оператора?')) return; try { await lumen.delete(`/admin/operators/${id}`); load(); } catch (_e) {} };

  const runScan = async (kind) => {
    try { await lumen.post(`/admin/operators/${kind}/scan`); } catch (_e) {}
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-operators">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Operator OS · Phase F</div>
          <h1 className="text-2xl font-bold">Оператори</h1>
          <p className="text-sm text-muted-foreground mt-1">Оператори — першокласні суб'єкти LUMEN. Профіль, верифікація, KPI, SLA, репутація, deal flow та винагорода.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => runScan('sla')} data-testid="scan-sla" className="h-9 px-3 rounded-lg text-xs font-medium border border-border inline-flex items-center gap-1.5 hover:bg-muted"><Activity className="w-3.5 h-3.5" /> SLA-скан</button>
          <button onClick={() => runScan('governance')} data-testid="scan-governance" className="h-9 px-3 rounded-lg text-xs font-medium border border-border inline-flex items-center gap-1.5 hover:bg-muted"><MessageSquareWarning className="w-3.5 h-3.5" /> Governance-скан</button>
        </div>
      </div>

      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 mb-4"><Plus className="w-4 h-4" style={{ color: PRIMARY }} /><h2 className="font-semibold">Новий оператор</h2></div>
        <div className="grid md:grid-cols-6 gap-2 items-end">
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Назва</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="op-name" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Тип</label>
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
              {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Регіон</label>
            <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Спеціалізація</label>
            <input value={form.specialization} onChange={(e) => setForm({ ...form, specialization: e.target.value })} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
          </div>
          <button onClick={create} disabled={busy} data-testid="op-create" className="h-10 rounded-lg text-sm font-medium text-white inline-flex items-center justify-center gap-1.5" style={{ background: PRIMARY }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Додати
          </button>
        </div>
        {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}
      </section>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="operators-list">
        {items.map((op) => (
          <div key={op.id} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="w-9 h-9 rounded-lg flex items-center justify-center bg-[#2E5D4F]/10 text-[#2E5D4F]"><Building2 className="w-4 h-4" /></span>
                <div>
                  <button onClick={() => setOpenId(op.id)} data-testid={`op-open-${op.id}`} className="font-semibold text-sm text-left hover:underline">{op.name}</button>
                  <div className="text-[11px] text-muted-foreground">{KIND_LABEL[op.kind] || op.kind}</div>
                </div>
              </div>
              <button onClick={() => remove(op.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
            </div>
            <div className="mt-3 space-y-1 text-xs text-muted-foreground">
              {op.region && <div className="flex items-center gap-1.5"><MapPin className="w-3 h-3" />{op.region}</div>}
              {op.specialization && <div className="flex items-center gap-1.5"><Briefcase className="w-3 h-3" />{op.specialization}</div>}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <VerifiedBadge verified={['verified', 'approved'].includes(op.status)} status={op.status} statusLabel={VERIFICATION_LABELS[op.status]} />
              <button onClick={() => setOpenId(op.id)} className="text-xs font-medium text-[#2E5D4F] hover:underline">Керувати →</button>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">Операторів ще немає.</p>}
      </div>

      {openId && <OperatorDrawer opId={openId} onClose={() => setOpenId(null)} onChanged={load} />}
    </div>
  );
}

const TABS = [
  ['overview', 'Огляд'],
  ['verification', 'Верифікація'],
  ['assets', 'Активи'],
  ['documents', 'Документи'],
  ['fees', 'Винагорода'],
  ['user', 'Доступ'],
];

function OperatorDrawer({ opId, onClose, onChanged }) {
  const [tab, setTab] = useState('overview');
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const r = await lumen.get(`/admin/operators/${opId}/overview`); setD(r.data); }
    catch (_e) { /* noop */ } finally { setLoading(false); }
  }, [opId]);
  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged?.(); };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex justify-end" onClick={onClose}>
      <div className="bg-background w-full max-w-2xl h-full overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="operator-drawer">
        {loading || !d ? (
          <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>
        ) : (
          <>
            <div className="sticky top-0 bg-background border-b border-border px-6 py-4 z-10">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-bold flex items-center gap-2">{d.operator.name}
                    <VerifiedBadge verified={d.operator.verified} status={d.operator.status} statusLabel={d.operator.status_label} />
                  </h2>
                  <div className="text-sm text-muted-foreground">{d.operator.kind_label} · {d.operator.region || '—'} · {d.operator.specialization || '—'}</div>
                </div>
                <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
              </div>
              <div className="flex gap-1 mt-3 overflow-x-auto">
                {TABS.map(([k, l]) => (
                  <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${tab === k ? 'bg-[#2E5D4F] text-white' : 'text-muted-foreground hover:bg-muted'}`}>{l}</button>
                ))}
              </div>
            </div>

            <div className="p-6">
              {tab === 'overview' && <OverviewTab d={d} />}
              {tab === 'verification' && <VerificationTab d={d} opId={opId} onChanged={refresh} />}
              {tab === 'assets' && <AssetsTab d={d} opId={opId} onChanged={refresh} />}
              {tab === 'documents' && <DocumentsTab d={d} opId={opId} onChanged={refresh} />}
              {tab === 'fees' && <FeesTab d={d} opId={opId} onChanged={refresh} />}
              {tab === 'user' && <UserTab d={d} opId={opId} onChanged={refresh} />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function OverviewTab({ d }) {
  const { kpi, reputation: rep, sla, governance: gov, dealflow: df } = d;
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4 rounded-2xl border border-border bg-card p-4">
        <ReputationRing score={rep.score} grade={rep.grade} />
        <div className="flex-1">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Репутація (факт-based)</div>
          <div className="text-sm font-semibold">Рейтинг {rep.grade} · {rep.score}/100</div>
          <div className="grid grid-cols-5 gap-1 mt-2 text-center">
            {Object.entries(rep.breakdown || {}).map(([k, v]) => (
              <div key={k} className="rounded bg-muted/50 py-1"><div className="text-xs font-semibold">{Math.round(v)}</div><div className="text-[9px] text-muted-foreground">{k.slice(0, 6)}</div></div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <KpiCard label="AUM" value={formatUAH(kpi.aum_uah)} accent="#2E5D4F" />
        <KpiCard label="Об'єктів" value={kpi.assets_count} />
        <KpiCard label="Інвесторів" value={kpi.investors_count} />
        <KpiCard label="Дохідність" value={formatPercent(kpi.avg_yield_pct)} />
        <KpiCard label="Заповненість" value={kpi.occupancy_pct == null ? '—' : formatPercent(kpi.occupancy_pct)} />
        <KpiCard label="Своєчасн. виплат" value={kpi.payout_timeliness_pct == null ? '—' : formatPercent(kpi.payout_timeliness_pct)} />
        <KpiCard label="Reporting" value={`${kpi.reporting_score}/100`} />
        <KpiCard label="Liquidity" value={`${kpi.liquidity_score}/10`} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="flex items-center justify-between mb-2"><h3 className="font-semibold text-sm flex items-center gap-1.5"><Activity className="w-4 h-4 text-[#2E5D4F]" /> SLA</h3><StatusPill status={sla.overall} label={sla.overall_label} /></div>
          <div className="space-y-1.5">
            {sla.items.map((i) => (
              <div key={i.asset_id} className="flex items-center justify-between text-xs"><span className="truncate text-muted-foreground">{i.asset_title}</span><StatusPill status={i.status} label={i.status_label} /></div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4">
          <h3 className="font-semibold text-sm flex items-center gap-1.5 mb-2"><Workflow className="w-4 h-4 text-[#2E5D4F]" /> Deal Flow</h3>
          <div className="space-y-1.5 text-xs">
            {[['Привед. сделок', df.sourced], ['Due Diligence', df.in_dd], ['Комітет', df.committee], ['Фінансування', df.funding], ['Активні', df.live], ['Відхилено', df.rejected]].map(([l, v]) => (
              <div key={l} className="flex items-center justify-between"><span className="text-muted-foreground">{l}</span><span className="font-semibold">{v}</span></div>
            ))}
            <div className="flex items-center justify-between pt-1.5 border-t border-border"><span className="text-muted-foreground">Успішність</span><span className="font-semibold">{formatPercent(df.funding_success_pct)}</span></div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-semibold text-sm">Governance (настрій спільноти)</h3>{gov.alert && <StatusPill status="warning" label="Нижче порогу" />}</div>
        <div className="text-xs text-muted-foreground">Позитивних: <b className="text-foreground">{gov.positive_pct == null ? '—' : `${gov.positive_pct}%`}</b> · поріг {gov.threshold}% · вибірка {gov.samples}</div>
      </div>

      <div>
        <h3 className="font-semibold text-sm mb-2">Журнал подій</h3>
        <div className="space-y-1.5 max-h-56 overflow-y-auto">
          {(d.events || []).map((e) => (
            <div key={e.id} className="flex items-start gap-2 text-xs border border-border rounded-lg p-2"><SeverityIcon severity={e.severity} /><div className="flex-1"><div>{e.message}</div><div className="text-[10px] text-muted-foreground">{formatDateUk(e.created_at)}</div></div></div>
          ))}
          {(d.events || []).length === 0 && <p className="text-xs text-muted-foreground">Подій немає.</p>}
        </div>
      </div>
    </div>
  );
}

function VerificationTab({ d, opId, onChanged }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(null);
  const states = d.verification_states || ['draft', 'applied', 'verified', 'approved', 'restricted', 'suspended'];
  const cur = d.operator.status;

  const transition = async (to) => {
    setBusy(to);
    try { await lumen.post(`/admin/operators/${opId}/verification`, { to_status: to, note: note || null }); setNote(''); onChanged(); }
    catch (_e) {} finally { setBusy(null); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Поточний статус</div>
        <div className="mt-1"><VerifiedBadge verified={d.operator.verified} status={cur} statusLabel={d.operator.status_label} /></div>
      </div>
      <div>
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Нотатка (опц.)</label>
        <input value={note} onChange={(e) => setNote(e.target.value)} data-testid="verif-note" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" placeholder="Причина зміни статусу" />
      </div>
      <div>
        <div className="text-sm font-medium mb-2">Перевести у статус:</div>
        <div className="flex flex-wrap gap-2">
          {states.map((s) => (
            <button key={s} disabled={s === cur || busy} onClick={() => transition(s)} data-testid={`verif-to-${s}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${s === cur ? 'opacity-40 cursor-default border-border' : `${VERIFICATION_TONE[s]} hover:opacity-80`}`}>
              {busy === s ? <Loader2 className="w-3 h-3 animate-spin inline" /> : (VERIFICATION_LABELS[s] || s)}
            </button>
          ))}
        </div>
      </div>
      <div>
        <h3 className="font-semibold text-sm mb-2">Історія верифікації</h3>
        <div className="space-y-1.5">
          {(d.events || []).filter((e) => e.kind === 'verification').map((e) => (
            <div key={e.id} className="text-xs border border-border rounded-lg p-2"><div>{e.message}</div><div className="text-[10px] text-muted-foreground">{formatDateUk(e.created_at)}</div></div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AssetsTab({ d, opId, onChanged }) {
  const [allAssets, setAllAssets] = useState([]);
  const [pick, setPick] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { lumen.get('/admin/assets').then((r) => setAllAssets(r.data.items || [])).catch(() => {}); }, []);
  const managedIds = new Set((d.assets || []).map((a) => a.id));
  const available = allAssets.filter((a) => !managedIds.has(a.id));

  const assign = async () => {
    if (!pick) return;
    setBusy(true);
    try { await lumen.post(`/admin/operators/${opId}/assets`, { asset_id: pick }); setPick(''); onChanged(); }
    catch (_e) {} finally { setBusy(false); }
  };
  const unassign = async (assetId) => {
    try { await lumen.delete(`/admin/operators/${opId}/assets/${assetId}`); onChanged(); } catch (_e) {}
  };

  return (
    <div className="space-y-5">
      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Призначити об'єкт</label>
          <select value={pick} onChange={(e) => setPick(e.target.value)} data-testid="assign-asset-select" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1">
            <option value="">— оберіть об'єкт —</option>
            {available.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
          </select>
        </div>
        <button onClick={assign} disabled={!pick || busy} data-testid="assign-asset-btn" className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Призначити
        </button>
      </div>

      <div>
        <h3 className="font-semibold text-sm mb-2">Об'єкти під управлінням ({(d.assets || []).length})</h3>
        <div className="space-y-2" data-testid="managed-assets">
          {(d.assets || []).map((a) => (
            <div key={a.id} className="flex items-center justify-between rounded-xl border border-border p-3">
              <div className="flex items-center gap-2"><Building2 className="w-4 h-4 text-muted-foreground" /><div><div className="text-sm font-medium">{a.title}</div><div className="text-[11px] text-muted-foreground">{a.category} · {formatUAH(a.raised)} / {formatUAH(a.round_target)}</div></div></div>
              <button onClick={() => unassign(a.id)} className="text-xs text-rose-600 hover:underline">Зняти</button>
            </div>
          ))}
          {(d.assets || []).length === 0 && <p className="text-sm text-muted-foreground">Об'єктів не призначено.</p>}
        </div>
      </div>
    </div>
  );
}

function DocumentsTab({ d, opId, onChanged }) {
  const [form, setForm] = useState({ title: '', kind: 'license', url: '' });
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!form.title.trim()) return;
    setBusy(true);
    try { await lumen.post(`/admin/operators/${opId}/documents`, form); setForm({ title: '', kind: 'license', url: '' }); onChanged(); }
    catch (_e) {} finally { setBusy(false); }
  };
  const del = async (docId) => { try { await lumen.delete(`/admin/operators/${opId}/documents/${docId}`); onChanged(); } catch (_e) {} };

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-border bg-card p-4 space-y-2">
        <div className="text-sm font-medium">Додати документ</div>
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="doc-title" placeholder="Назва документа" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
        <div className="flex gap-2">
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="h-10 rounded-lg border border-border bg-background px-2 text-sm">
            {['license', 'registration', 'insurance', 'financials', 'other'].map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="URL (опц.)" className="flex-1 h-10 rounded-lg border border-border bg-background px-2 text-sm" />
          <button onClick={add} disabled={busy} data-testid="doc-add" className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}</button>
        </div>
      </div>
      <div className="space-y-2" data-testid="docs-list">
        {(d.documents || []).map((doc) => (
          <div key={doc.id} className="flex items-center justify-between rounded-xl border border-border p-3">
            <div className="flex items-center gap-2"><FileText className="w-4 h-4 text-muted-foreground" /><div><div className="text-sm font-medium">{doc.title}</div><div className="text-[11px] text-muted-foreground">{doc.kind} · {formatDateUk(doc.created_at)}</div></div></div>
            <button onClick={() => del(doc.id)} className="text-muted-foreground hover:text-rose-600"><Trash2 className="w-4 h-4" /></button>
          </div>
        ))}
        {(d.documents || []).length === 0 && <p className="text-sm text-muted-foreground">Документів немає.</p>}
      </div>
    </div>
  );
}

function FeesTab({ d, opId, onChanged }) {
  const f0 = d.fees || {};
  const [f, setF] = useState({
    management_fee_pct: f0.management_fee_pct ?? 0,
    success_fee_pct: f0.success_fee_pct ?? 0,
    performance_fee_pct: f0.performance_fee_pct ?? 0,
    notes: f0.notes || '',
  });
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);

  const save = async () => {
    setBusy(true); setOk(false);
    try {
      await lumen.patch(`/admin/operators/${opId}/fees`, {
        management_fee_pct: Number(f.management_fee_pct),
        success_fee_pct: Number(f.success_fee_pct),
        performance_fee_pct: Number(f.performance_fee_pct),
        notes: f.notes,
      });
      setOk(true); onChanged();
    } catch (_e) {} finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      {[['management_fee_pct', 'Management fee, %'], ['success_fee_pct', 'Success fee, %'], ['performance_fee_pct', 'Performance fee, %']].map(([k, l]) => (
        <div key={k}>
          <label className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</label>
          <input type="number" step="0.1" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`fee-${k}`} className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm mt-1" />
        </div>
      ))}
      <div>
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Нотатки</label>
        <textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} rows={2} className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm mt-1" />
      </div>
      <div className="rounded-xl border border-[#2E5D4F]/30 bg-[#2E5D4F]/[0.05] p-3 text-sm flex items-center justify-between">
        <span className="text-muted-foreground">Орієнтовна mgmt fee / рік</span>
        <span className="font-semibold">{formatUAH(d.fees?.estimated_annual_management_fee_uah)}</span>
      </div>
      <button onClick={save} disabled={busy} data-testid="fees-save" className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Зберегти {ok && <span className="text-xs">✓</span>}
      </button>
    </div>
  );
}

function UserTab({ d, opId, onChanged }) {
  const [form, setForm] = useState({ email: '', name: '', password: '' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const link = async () => {
    if (!form.email.trim()) { setMsg('Вкажіть email'); return; }
    setBusy(true); setMsg('');
    try { const r = await lumen.post(`/admin/operators/${opId}/link-user`, form); setMsg(`Прив'язано: ${r.data.email}`); onChanged(); }
    catch (e) { setMsg(lumenError(e, 'Помилка')); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border bg-card p-4">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Прив'язаний користувач</div>
        {d.linked_user
          ? <div className="mt-1 text-sm font-medium flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-emerald-600" />{d.linked_user.name} · {d.linked_user.email}</div>
          : <div className="mt-1 text-sm text-muted-foreground">Не прив'язано. Створіть або прив'яжіть користувача з роллю operator.</div>}
      </div>
      <div className="space-y-2">
        <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="link-email" placeholder="email оператора" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ім'я (опц.)" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
        <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Пароль (опц., якщо новий)" className="w-full h-10 rounded-lg border border-border bg-background px-2 text-sm" />
        <button onClick={link} disabled={busy} data-testid="link-user-btn" className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-1.5" style={{ background: PRIMARY }}>
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Прив'язати / створити
        </button>
        {msg && <p className="text-xs text-muted-foreground">{msg}</p>}
      </div>
    </div>
  );
}
