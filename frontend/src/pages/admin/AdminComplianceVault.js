import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import {
  ShieldCheck, Loader2, Users, CheckCircle2, XCircle, Clock,
  AlertTriangle, ChevronRight, Gauge,
} from 'lucide-react';

const BAND = {
  ready: 'bg-emerald-100 text-emerald-800', partial: 'bg-sky-100 text-sky-800',
  incomplete: 'bg-amber-100 text-amber-800',
};
const FILTERS = [
  { value: '', label: 'Усі' }, { value: 'blocked', label: 'Заблоковані' },
  { value: 'expiring', label: 'Спливають' }, { value: 'ready', label: 'Готові' },
];

function scoreColor(s) { return s >= 90 ? '#059669' : s >= 60 ? '#0284c7' : '#d97706'; }

export default function AdminComplianceVault() {
  const [tab, setTab] = useState('registry');
  const [filter, setFilter] = useState('');
  const [reg, setReg] = useState({ items: [], avg_score: 0, ready: 0, count: 0 });
  const [exp, setExp] = useState({ items: [], count: 0, expired: 0 });
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(null);
  const [card, setCard] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const loadReg = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/admin/compliance/registry', { params: filter ? { filter } : {} }); setReg(r.data); }
    catch (e) { setMsg(lumenError(e)); } finally { setLoading(false); }
  }, [filter]);
  const loadExp = useCallback(async () => {
    try { const r = await lumen.get('/admin/compliance/expirations'); setExp(r.data); } catch (_e) {}
  }, []);

  useEffect(() => { loadReg(); }, [loadReg]);
  useEffect(() => { if (tab === 'expirations') loadExp(); }, [tab, loadExp]);

  const open = async (uid) => {
    setSel(uid); setCard(null); setMsg('');
    try { const r = await lumen.get(`/admin/compliance/${uid}`); setCard(r.data); } catch (e) { setMsg(lumenError(e)); }
  };
  const verify = async (slot, status) => {
    setBusy(true); setMsg('');
    try { const r = await lumen.post(`/admin/compliance/${sel}/verify`, { slot, status }); setCard(r.data); await loadReg(); }
    catch (e) { setMsg(lumenError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="p-6 space-y-5" data-testid="admin-compliance-vault">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-6 h-6 text-[#2E5D4F]" /> Compliance Vault</h1>
        <p className="text-sm text-muted-foreground">G15 — єдиний комплаєнс-реєстр інвесторів, скоринг і терміни дії.</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-4"><div className="text-[11px] uppercase text-muted-foreground">Середній бал</div><div className="text-2xl font-bold flex items-center gap-1"><Gauge className="w-5 h-5 text-[#2E5D4F]" />{reg.avg_score}</div></div>
        <div className="rounded-xl border border-border bg-card p-4"><div className="text-[11px] uppercase text-muted-foreground">Готові</div><div className="text-2xl font-bold text-emerald-600">{reg.ready}/{reg.count}</div></div>
        <div className="rounded-xl border border-border bg-card p-4"><div className="text-[11px] uppercase text-muted-foreground">Спливають / прострочені</div><div className="text-2xl font-bold text-amber-600">{exp.count || '—'}</div></div>
      </div>

      <div className="flex gap-2 border-b border-border">
        {[['registry', 'Реєстр'], ['expirations', 'Терміни дії']].map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`cv-tab-${v}`}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === v ? 'border-[#2E5D4F] text-[#2E5D4F]' : 'border-transparent text-muted-foreground'}`}>{l}</button>
        ))}
      </div>

      {tab === 'registry' && (
        <>
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button key={f.value} onClick={() => setFilter(f.value)} data-testid={`cv-filter-${f.value || 'all'}`}
                className={`h-8 px-3 rounded-full text-xs border ${filter === f.value ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border hover:bg-muted'}`}>{f.label}</button>
            ))}
          </div>
          <div className="grid lg:grid-cols-2 gap-5">
            <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="cv-registry-list">
              {loading ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
                : reg.items.length === 0 ? <div className="py-16 text-center text-sm text-muted-foreground"><Users className="w-8 h-8 mx-auto mb-2 opacity-40" />Немає інвесторів</div>
                  : reg.items.map((it) => (
                    <button key={it.user_id} onClick={() => open(it.user_id)} data-testid={`cv-row-${it.user_id}`}
                      className={`w-full text-left px-4 py-3 hover:bg-muted/50 flex items-center justify-between gap-3 ${sel === it.user_id ? 'bg-muted/60' : ''}`}>
                      <div className="flex items-center gap-3">
                        <div className="text-lg font-bold w-10 text-center" style={{ color: scoreColor(it.score) }}>{it.score}</div>
                        <div>
                          <div className="font-medium text-sm">{it.full_name || it.user_id}</div>
                          <div className="text-[11px] text-muted-foreground">{it.gaps} прогалин · {it.expiring} спливають</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full ${BAND[it.score_band]}`}>{it.score_band}</span>
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                      </div>
                    </button>
                  ))}
            </div>
            <div className="rounded-2xl border border-border bg-card p-5" data-testid="cv-card">
              {!sel ? <div className="py-16 text-center text-sm text-muted-foreground"><ShieldCheck className="w-8 h-8 mx-auto mb-2 opacity-40" />Оберіть інвестора</div>
                : !card ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
                  : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="font-semibold">{card.full_name || card.user_id}</div>
                        <div className="text-2xl font-bold" style={{ color: scoreColor(card.score) }}>{card.score}</div>
                      </div>
                      <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                        {card.items.map((it) => (
                          <div key={it.key} className="px-3 py-2 flex items-center justify-between gap-2 text-sm">
                            <span>{it.label}</span>
                            <div className="flex items-center gap-2">
                              <span className={it.fraction >= 1 ? 'text-emerald-600' : it.fraction > 0 ? 'text-sky-600' : 'text-muted-foreground'}>{it.status_label}</span>
                              {['sof', 'aml_questionnaire', 'tax_form', 'risk_acknowledgement', 'voting_consent'].includes(it.key) && it.status === 'provided' && (
                                <>
                                  <button onClick={() => verify(it.key, 'verified')} disabled={busy} data-testid={`cv-verify-${it.key}`} className="text-emerald-600 hover:text-emerald-700"><CheckCircle2 className="w-4 h-4" /></button>
                                  <button onClick={() => verify(it.key, 'rejected')} disabled={busy} className="text-red-600 hover:text-red-700"><XCircle className="w-4 h-4" /></button>
                                </>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      {msg && <p className={`text-xs ${/✓|verif/i.test(msg) ? 'text-emerald-600' : 'text-red-600'}`}>{msg}</p>}
                    </div>
                  )}
            </div>
          </div>
        </>
      )}

      {tab === 'expirations' && (
        <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="cv-expirations">
          {exp.items.length === 0 ? <div className="py-16 text-center text-sm text-muted-foreground"><CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-40 text-emerald-500" />Немає документів, що спливають</div>
            : exp.items.map((e, i) => (
              <div key={i} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">{e.expired ? <AlertTriangle className="w-4 h-4 text-red-600" /> : <Clock className="w-4 h-4 text-amber-600" />}
                  <div><div className="font-medium text-sm">{e.full_name}</div><div className="text-[11px] text-muted-foreground">{e.label}</div></div></div>
                <span className={`text-xs font-medium ${e.expired ? 'text-red-600' : 'text-amber-600'}`}>{e.expired ? 'Прострочено' : `${e.days_left} дн.`}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
