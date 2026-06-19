/**
 * Admin · Compliance Screening (Tier B) — Sanctions + PEP + Risk + AML
 * Review queue · case decisions · ad-hoc screening · watchlist · AML journal.
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk, UAH_PER_USD } from '@/lib/lumenApi';
import {
  Loader2, ShieldAlert, Search, Gavel, ListChecks, ScrollText,
  AlertTriangle, RefreshCw, CheckCircle2, ArrowUpCircle, Ban,
} from 'lucide-react';

const RISK_STYLE = {
  LOW: { bg: '#ECFDF5', fg: '#047857', label: 'LOW' },
  MEDIUM: { bg: '#FFFBEB', fg: '#B45309', label: 'MEDIUM' },
  HIGH: { bg: '#FFF1F2', fg: '#BE123C', label: 'HIGH' },
  CRITICAL: { bg: '#450A0A', fg: '#FECACA', label: 'CRITICAL' },
};
const STATUS_STYLE = {
  open: { bg: '#FFFBEB', fg: '#B45309' },
  in_review: { bg: '#EFF6FF', fg: '#1D4ED8' },
  escalated: { bg: '#FFF1F2', fg: '#BE123C' },
  cleared: { bg: '#ECFDF5', fg: '#047857' },
  blocked: { bg: '#450A0A', fg: '#FECACA' },
};

const RiskBadge = ({ band }) => {
  const s = RISK_STYLE[band] || RISK_STYLE.LOW;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold tracking-wide"
      style={{ background: s.bg, color: s.fg }}>{s.label}</span>
  );
};
const StatusBadge = ({ status }) => {
  const s = STATUS_STYLE[status] || STATUS_STYLE.open;
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold capitalize"
      style={{ background: s.bg, color: s.fg }}>{(status || '').replace('_', ' ')}</span>
  );
};

const KPI = ({ label, value, accent }) => (
  <div className="rounded-2xl border border-border bg-card p-4">
    <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</div>
    <div className="text-2xl font-bold mt-1" style={accent ? { color: accent } : {}}>{value}</div>
  </div>
);

export default function AdminComplianceScreening() {
  const [tab, setTab] = useState('queue');
  const [dash, setDash] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [deciding, setDeciding] = useState(false);
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');

  // screen tool
  const [scrName, setScrName] = useState('');
  const [scrCountry, setScrCountry] = useState('');
  const [scrAmount, setScrAmount] = useState('');
  const [scrPep, setScrPep] = useState(false);
  const [scrResult, setScrResult] = useState(null);
  const [scrLoading, setScrLoading] = useState(false);

  // watchlist + aml
  const [watchlist, setWatchlist] = useState([]);
  const [aml, setAml] = useState([]);
  const [wlRefresh, setWlRefresh] = useState(null);
  const [wlBusy, setWlBusy] = useState(false);

  const loadWatchlist = useCallback(() => {
    lumen.get('/admin/compliance/watchlist', { params: { limit: 300 } }).then((r) => setWatchlist(r.data.items || [])).catch(() => {});
    lumen.get('/admin/compliance/watchlist/refresh-status').then((r) => setWlRefresh(r.data)).catch(() => {});
  }, []);

  const refreshWatchlist = async () => {
    setWlBusy(true); setErr('');
    try { await lumen.post('/admin/compliance/watchlist/refresh'); loadWatchlist(); }
    catch (e) { setErr(lumenError(e)); } finally { setWlBusy(false); }
  };

  const loadDash = useCallback(() => {
    lumen.get('/admin/compliance/dashboard').then((r) => setDash(r.data)).catch(() => {});
  }, []);

  const loadCases = useCallback(() => {
    setLoading(true);
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (riskFilter) params.risk = riskFilter;
    lumen.get('/admin/compliance/cases', { params })
      .then((r) => setCases(r.data.items || []))
      .catch((e) => setErr(lumenError(e)))
      .finally(() => setLoading(false));
  }, [statusFilter, riskFilter]);

  useEffect(() => { loadDash(); }, [loadDash]);
  useEffect(() => { if (tab === 'queue') loadCases(); }, [tab, loadCases]);
  useEffect(() => {
    if (tab === 'watchlist') loadWatchlist();
    if (tab === 'aml') lumen.get('/admin/compliance/aml-audit', { params: { limit: 300 } }).then((r) => setAml(r.data.items || [])).catch(() => {});
  }, [tab, loadWatchlist]);

  const openCase = (c) => {
    setSelected(c); setDetail(null); setReason('');
    lumen.get(`/admin/compliance/cases/${c.id}`).then((r) => setDetail(r.data)).catch(() => {});
  };

  const decide = async (decision) => {
    if (!selected) return;
    if (!reason.trim()) { setErr('Вкажіть причину рішення / Provide a reason'); return; }
    setDeciding(true); setErr('');
    try {
      await lumen.post(`/admin/compliance/cases/${selected.id}/decision`, { decision, reason });
      setSelected(null); setDetail(null); loadCases(); loadDash();
    } catch (e) { setErr(lumenError(e)); } finally { setDeciding(false); }
  };

  const runScreen = async () => {
    if (!scrName.trim()) return;
    setScrLoading(true); setScrResult(null);
    try {
      const r = await lumen.post('/admin/compliance/screen', {
        name: scrName, country: scrCountry || null,
        amount_uah: scrAmount ? Number(scrAmount) * UAH_PER_USD : null, is_pep: scrPep,
      });
      setScrResult(r.data);
    } catch (e) { setErr(lumenError(e)); } finally { setScrLoading(false); }
  };

  const TabBtn = ({ id, icon, label }) => (
    <button onClick={() => setTab(id)} data-testid={`compliance-tab-${id}`}
      className={`inline-flex items-center gap-1.5 px-3 h-9 rounded-lg text-sm font-medium transition ${tab === id ? 'text-white' : 'text-muted-foreground hover:text-foreground'}`}
      style={tab === id ? { background: '#2E5D4F' } : {}}>
      {icon}{label}
    </button>
  );

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-compliance-screening">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Compliance · Tier B</div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-[#2E5D4F]" /> Санкції · PEP · Ризик · AML
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Скринінг проти OFAC / EU / UK / РНБО та PEP-списків, оцінка ризику й незмінний AML-журнал.
          </p>
        </div>
        <button onClick={() => { loadDash(); loadCases(); }} data-testid="compliance-refresh"
          className="h-9 px-3 rounded-lg border border-border text-sm inline-flex items-center gap-1.5 hover:bg-muted">
          <RefreshCw className="w-4 h-4" /> Оновити
        </button>
      </div>

      {/* KPIs */}
      {dash && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPI label="Watchlist" value={dash.watchlist_total} />
          <KPI label="Відкриті кейси" value={dash.open_cases} accent="#B45309" />
          <KPI label="CRITICAL" value={dash.open_cases_by_risk?.CRITICAL ?? 0} accent="#BE123C" />
          <KPI label="Скринінгів" value={dash.screenings_total} />
          <KPI label="AML подій" value={dash.aml_events_total} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        <TabBtn id="queue" icon={<ListChecks className="w-4 h-4" />} label="Черга перевірки" />
        <TabBtn id="screen" icon={<Search className="w-4 h-4" />} label="Скринінг" />
        <TabBtn id="watchlist" icon={<ShieldAlert className="w-4 h-4" />} label="Watchlist" />
        <TabBtn id="aml" icon={<ScrollText className="w-4 h-4" />} label="AML-журнал" />
      </div>

      {err && <div className="rounded-lg bg-rose-50 text-rose-700 text-sm px-3 py-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{err}</div>}

      {/* QUEUE */}
      {tab === 'queue' && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="filter-status"
              className="h-9 rounded-lg border border-border bg-background px-2 text-sm">
              <option value="">Всі статуси</option>
              {['open', 'in_review', 'escalated', 'cleared', 'blocked'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)} data-testid="filter-risk"
              className="h-9 rounded-lg border border-border bg-background px-2 text-sm">
              <option value="">Всі ризики</option>
              {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
          ) : cases.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Немає кейсів</div>
          ) : (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-[11px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="text-left px-4 py-2">Інвестор</th>
                    <th className="text-left px-4 py-2">Тип</th>
                    <th className="text-left px-4 py-2">Ризик</th>
                    <th className="text-left px-4 py-2">Статус</th>
                    <th className="text-left px-4 py-2">Відкрито</th>
                    <th className="px-4 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id} className="border-t border-border" data-testid={`case-row-${c.id}`}>
                      <td className="px-4 py-2 font-medium">{c.investor_name || c.investor_id}</td>
                      <td className="px-4 py-2 capitalize">{c.case_type}</td>
                      <td className="px-4 py-2"><RiskBadge band={c.risk_band} /></td>
                      <td className="px-4 py-2"><StatusBadge status={c.status} /></td>
                      <td className="px-4 py-2 text-muted-foreground">{formatDateUk(c.opened_at_iso || c.opened_at)}</td>
                      <td className="px-4 py-2 text-right">
                        <button onClick={() => openCase(c)} data-testid={`case-open-${c.id}`}
                          className="text-[#2E5D4F] font-medium hover:underline">Відкрити</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* SCREEN TOOL */}
      {tab === 'screen' && (
        <div className="grid md:grid-cols-2 gap-5">
          <div className="rounded-2xl border border-border bg-card p-5 space-y-3">
            <div className="font-semibold">Ручний скринінг</div>
            <input value={scrName} onChange={(e) => setScrName(e.target.value)} placeholder="Повне ім'я / Full name" data-testid="screen-name"
              className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
            <div className="flex gap-2">
              <input value={scrCountry} onChange={(e) => setScrCountry(e.target.value)} placeholder="Країна (ISO2, напр. UA)" data-testid="screen-country"
                className="w-1/2 h-10 rounded-lg border border-border bg-background px-3 text-sm" />
              <input value={scrAmount} onChange={(e) => setScrAmount(e.target.value)} placeholder="Сума, $" type="number" data-testid="screen-amount"
                className="w-1/2 h-10 rounded-lg border border-border bg-background px-3 text-sm" />
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={scrPep} onChange={(e) => setScrPep(e.target.checked)} /> Декларований PEP</label>
            <button onClick={runScreen} disabled={scrLoading || !scrName.trim()} data-testid="screen-run"
              className="h-10 px-4 rounded-lg text-sm font-medium text-white inline-flex items-center gap-2 disabled:opacity-50" style={{ background: '#2E5D4F' }}>
              {scrLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Перевірити
            </button>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5" data-testid="screen-result">
            {!scrResult ? (
              <div className="text-sm text-muted-foreground">Результат скринінгу з'явиться тут.</div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold capitalize">{(scrResult.decision || '').replace('_', ' ')}</span>
                  <RiskBadge band={scrResult.risk_band} />
                  {scrResult.pep_hit && <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-semibold">PEP</span>}
                </div>
                <div className="text-xs text-muted-foreground">Причини ризику: {(scrResult.risk_reasons || []).join(', ') || '—'}</div>
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Збіги ({(scrResult.matches || []).length})</div>
                <div className="space-y-1.5 max-h-72 overflow-auto">
                  {(scrResult.matches || []).map((m, i) => (
                    <div key={i} className="flex items-center justify-between text-sm border-b border-border/60 py-1">
                      <span>{m.full_name} <span className="text-[11px] text-muted-foreground uppercase">· {m.source} · {m.list_type}</span></span>
                      <span className="font-mono text-xs">{(m.score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                  {(scrResult.matches || []).length === 0 && <div className="text-sm text-emerald-700">Збігів не знайдено</div>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* WATCHLIST */}
      {tab === 'watchlist' && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
            <div className="text-sm">
              <div className="font-medium">Перелік спостереження (OFAC / EU / UK / РНБО / PEP)</div>
              <div className="text-xs text-muted-foreground">
                {wlRefresh ? (
                  <>Автозавантажено: <b>{wlRefresh.auto_fetched_count}</b> · Seed/ручні: <b>{wlRefresh.seed_manual_count}</b>
                  {wlRefresh.last_refresh?.at_iso && <> · Оновлено: {formatDateUk(wlRefresh.last_refresh.at_iso)} ({wlRefresh.last_refresh.status})</>}</>
                ) : '...'}
              </div>
            </div>
            <button onClick={refreshWatchlist} disabled={wlBusy} data-testid="watchlist-refresh"
              className="h-9 px-3 rounded-lg text-sm text-white inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: '#2E5D4F' }}>
              {wlBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Оновити з OFAC
            </button>
          </div>
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr><th className="text-left px-4 py-2">Ім'я</th><th className="text-left px-4 py-2">Джерело</th><th className="text-left px-4 py-2">Тип</th><th className="text-left px-4 py-2">Країна</th><th className="text-left px-4 py-2">Програма</th></tr>
            </thead>
            <tbody>
              {watchlist.map((w) => (
                <tr key={w.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium">{w.full_name}</td>
                  <td className="px-4 py-2 uppercase">{w.source}</td>
                  <td className="px-4 py-2">{w.list_type}</td>
                  <td className="px-4 py-2">{w.country || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{w.program || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </div>
      )}

      {/* AML JOURNAL */}
      {tab === 'aml' && (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-4 py-2 text-[11px] text-muted-foreground bg-muted/40">Незмінний журнал (append-only). Хто · що · коли · чому.</div>
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr><th className="text-left px-4 py-2">Коли</th><th className="text-left px-4 py-2">Дія</th><th className="text-left px-4 py-2">Суб'єкт</th><th className="text-left px-4 py-2">Актор</th><th className="text-left px-4 py-2">Причина</th></tr>
            </thead>
            <tbody>
              {aml.map((a) => (
                <tr key={a.id} className="border-t border-border">
                  <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">{formatDateUk(a.at_iso || a.at)}</td>
                  <td className="px-4 py-2 font-mono text-xs">{a.action}</td>
                  <td className="px-4 py-2 text-xs">{a.subject_type}:{(a.subject_id || '').slice(0, 14)}</td>
                  <td className="px-4 py-2 text-xs">{(a.actor || '—').slice(0, 16)}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{a.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* CASE DRAWER */}
      {selected && (
        <div className="fixed inset-0 bg-black/40 z-50 flex justify-end" onClick={() => setSelected(null)}>
          <div className="w-full max-w-lg bg-background h-full overflow-auto p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="case-drawer">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Кейс комплаєнсу</h2>
              <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground">✕</button>
            </div>
            <div className="flex items-center gap-2">
              <RiskBadge band={selected.risk_band} /><StatusBadge status={selected.status} />
              <span className="text-sm capitalize text-muted-foreground">{selected.case_type}</span>
            </div>
            <div className="text-sm"><span className="text-muted-foreground">Інвестор:</span> <b>{selected.investor_name || selected.investor_id}</b></div>
            {!detail ? (
              <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            ) : (
              <>
                {detail.screening_result && (
                  <div className="rounded-xl border border-border p-3 space-y-2">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Результат скринінгу</div>
                    <div className="text-sm">Рішення: <b className="capitalize">{(detail.screening_result.decision || '').replace('_', ' ')}</b></div>
                    <div className="text-xs text-muted-foreground">Причини: {(detail.screening_result.risk_reasons || []).join(', ') || '—'}</div>
                    <div className="space-y-1">
                      {(detail.screening_result.matches || []).slice(0, 8).map((m, i) => (
                        <div key={i} className="flex justify-between text-xs border-b border-border/50 py-0.5">
                          <span>{m.full_name} <span className="uppercase text-muted-foreground">· {m.source}/{m.list_type}</span></span>
                          <span className="font-mono">{(m.score * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="rounded-xl border border-border p-3">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">AML-журнал суб'єкта</div>
                  <div className="space-y-1 max-h-40 overflow-auto">
                    {(detail.aml_audit || []).map((a) => (
                      <div key={a.id} className="text-xs text-muted-foreground"><span className="font-mono">{a.action}</span> — {a.reason} · {formatDateUk(a.at_iso || a.at)}</div>
                    ))}
                  </div>
                </div>
              </>
            )}
            <div className="space-y-2 pt-2 border-t border-border">
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Рішення комплаєнсу</div>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина рішення (обов'язково)" data-testid="decision-reason"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" rows={2} />
              <div className="flex gap-2">
                <button onClick={() => decide('clear')} disabled={deciding} data-testid="decision-clear"
                  className="flex-1 h-10 rounded-lg text-sm font-medium inline-flex items-center justify-center gap-1.5 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50">
                  <CheckCircle2 className="w-4 h-4" /> Очистити
                </button>
                <button onClick={() => decide('escalate')} disabled={deciding} data-testid="decision-escalate"
                  className="flex-1 h-10 rounded-lg text-sm font-medium inline-flex items-center justify-center gap-1.5 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50">
                  <ArrowUpCircle className="w-4 h-4" /> Ескалація
                </button>
                <button onClick={() => decide('block')} disabled={deciding} data-testid="decision-block"
                  className="flex-1 h-10 rounded-lg text-sm font-medium inline-flex items-center justify-center gap-1.5 text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50">
                  {deciding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />} Блок
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
