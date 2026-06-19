import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatUAH, formatDateUk } from '@/lib/lumenApi';
import {
  ShieldCheck, Loader2, Users, CheckCircle2, XCircle, FileSearch,
  Award, Building2, ChevronRight, Save,
} from 'lucide-react';

const STATUS_BADGE = {
  pending: 'bg-muted text-muted-foreground', documents_requested: 'bg-amber-100 text-amber-800',
  under_review: 'bg-sky-100 text-sky-800', approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-700', expired: 'bg-red-100 text-red-700',
};
const LEVELS = ['retail', 'qualified', 'accredited', 'professional', 'institutional'];
const FILTERS = [
  { value: '', label: 'Усі' }, { value: 'under_review', label: 'На розгляді' },
  { value: 'documents_requested', label: 'Запит документів' }, { value: 'approved', label: 'Підтверджені' },
  { value: 'pending', label: 'Не подані' }, { value: 'rejected', label: 'Відхилені' },
];

export default function AdminAccreditation() {
  const [tab, setTab] = useState('queue');
  const [filter, setFilter] = useState('');
  const [data, setData] = useState({ items: [], counts: {} });
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(null);
  const [card, setCard] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [level, setLevel] = useState('qualified');
  const [note, setNote] = useState('');
  // asset access
  const [assets, setAssets] = useState({ items: [], levels: [] });

  const loadQueue = useCallback(async () => {
    setLoading(true);
    try { const r = await lumen.get('/admin/accreditation/queue', { params: filter ? { status: filter } : {} }); setData(r.data); }
    catch (e) { setMsg(lumenError(e)); } finally { setLoading(false); }
  }, [filter]);

  const loadAssets = useCallback(async () => {
    try { const r = await lumen.get('/admin/accreditation/assets/access'); setAssets(r.data); } catch (_e) {}
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);
  useEffect(() => { if (tab === 'assets') loadAssets(); }, [tab, loadAssets]);

  const openCard = async (uid) => {
    setSel(uid); setCard(null); setMsg('');
    try { const r = await lumen.get(`/admin/accreditation/${uid}`); setCard(r.data); setLevel(r.data.accreditation?.level || 'qualified'); }
    catch (e) { setMsg(lumenError(e)); }
  };

  const transition = async (to_status, withLevel) => {
    if (!sel) return;
    setBusy(true); setMsg('');
    try {
      const body = { to_status, note };
      if (to_status === 'approved') body.level = withLevel || level;
      await lumen.post(`/admin/accreditation/${sel}/transition`, body);
      setMsg('Оновлено ✓'); setNote('');
      await openCard(sel); await loadQueue();
    } catch (e) { setMsg(lumenError(e)); } finally { setBusy(false); }
  };

  const setAccess = async (assetId, access_level) => {
    try { await lumen.patch(`/admin/accreditation/assets/${assetId}/access`, { access_level }); loadAssets(); } catch (_e) {}
  };

  return (
    <div className="p-6 space-y-5" data-testid="admin-accreditation">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-6 h-6 text-[#2E5D4F]" /> Accreditation OS</h1>
        <p className="text-sm text-muted-foreground">G11 — перевірка акредитації інвесторів і рівні доступу до об'єктів.</p>
      </div>

      <div className="flex gap-2 border-b border-border">
        {[['queue', 'Черга акредитації'], ['assets', 'Доступ до об\'єктів']].map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`acc-tab-${v}`}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === v ? 'border-[#2E5D4F] text-[#2E5D4F]' : 'border-transparent text-muted-foreground'}`}>{l}</button>
        ))}
      </div>

      {tab === 'queue' && (
        <>
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button key={f.value} onClick={() => setFilter(f.value)} data-testid={`acc-filter-${f.value || 'all'}`}
                className={`h-8 px-3 rounded-full text-xs border ${filter === f.value ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border hover:bg-muted'}`}>
                {f.label}{data.counts?.[f.value] != null && f.value ? ` (${data.counts[f.value]})` : ''}
              </button>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            {/* list */}
            <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="acc-queue-list">
              {loading ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
                : data.items.length === 0 ? <div className="py-16 text-center text-sm text-muted-foreground"><Users className="w-8 h-8 mx-auto mb-2 opacity-40" />Немає інвесторів у цьому фільтрі</div>
                  : data.items.map((it) => (
                    <button key={it.user_id} onClick={() => openCard(it.user_id)} data-testid={`acc-row-${it.user_id}`}
                      className={`w-full text-left px-4 py-3 hover:bg-muted/50 flex items-center justify-between gap-3 ${sel === it.user_id ? 'bg-muted/60' : ''}`}>
                      <div>
                        <div className="font-medium text-sm">{it.full_name || it.user_id}</div>
                        <div className="text-[11px] text-muted-foreground">сегмент: {it.segment} · KYC: {it.kyc_status}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full ${STATUS_BADGE[it.accreditation.review_status]}`}>{it.accreditation.review_status_label}</span>
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                      </div>
                    </button>
                  ))}
            </div>

            {/* card */}
            <div className="rounded-2xl border border-border bg-card p-5" data-testid="acc-card">
              {!sel ? <div className="py-16 text-center text-sm text-muted-foreground"><FileSearch className="w-8 h-8 mx-auto mb-2 opacity-40" />Оберіть інвестора зі списку</div>
                : !card ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
                  : (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="font-semibold">{card.full_name || card.user_id}</div>
                        <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${STATUS_BADGE[card.accreditation.review_status]}`}>{card.accreditation.review_status_label}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div><div className="text-[11px] text-muted-foreground">Рівень</div><div className="font-medium flex items-center gap-1"><Award className="w-3.5 h-3.5" />{card.accreditation.level_label}</div></div>
                        <div><div className="text-[11px] text-muted-foreground">Рекомендований</div><div className="font-medium">{card.accreditation.suggested_level}</div></div>
                        <div><div className="text-[11px] text-muted-foreground">Річний дохід</div><div>{formatUAH(card.financial?.annual_income_uah || 0)}</div></div>
                        <div><div className="text-[11px] text-muted-foreground">Чисті активи</div><div>{formatUAH(card.financial?.net_worth_uah || 0)}</div></div>
                        <div><div className="text-[11px] text-muted-foreground">Ліквідні активи</div><div>{formatUAH(card.financial?.liquid_assets_uah || 0)}</div></div>
                        <div><div className="text-[11px] text-muted-foreground">Досвід</div><div>{card.experience?.years_investing ?? '—'} р.</div></div>
                      </div>
                      {card.missing_for_submit?.length > 0 && <div className="text-xs text-amber-700">Незаповнено: {card.missing_for_submit.map((m) => m.split('.').pop()).join(', ')}</div>}

                      <div className="pt-3 border-t border-border space-y-3">
                        <div className="flex gap-2 items-end">
                          <div className="flex-1">
                            <label className="block text-[11px] text-muted-foreground mb-1">Рівень при підтвердженні</label>
                            <select value={level} onChange={(e) => setLevel(e.target.value)} data-testid="acc-level-select" className="w-full h-9 px-2 rounded-lg border border-border bg-background text-sm">
                              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                            </select>
                          </div>
                        </div>
                        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Коментар (необов'язково)" className="w-full h-9 px-3 rounded-lg border border-border bg-background text-sm" data-testid="acc-note" />
                        <div className="flex flex-wrap gap-2">
                          <button onClick={() => transition('under_review')} disabled={busy} className="h-9 px-3 rounded-lg text-xs border border-border hover:bg-muted">На розгляд</button>
                          <button onClick={() => transition('documents_requested')} disabled={busy} className="h-9 px-3 rounded-lg text-xs border border-border hover:bg-muted">Запит документів</button>
                          <button onClick={() => transition('approved')} disabled={busy} data-testid="acc-approve" className="h-9 px-4 rounded-lg text-xs bg-[#2E5D4F] text-white inline-flex items-center gap-1.5 hover:opacity-90"><CheckCircle2 className="w-3.5 h-3.5" />Підтвердити</button>
                          <button onClick={() => transition('rejected')} disabled={busy} data-testid="acc-reject" className="h-9 px-4 rounded-lg text-xs bg-red-600 text-white inline-flex items-center gap-1.5 hover:opacity-90"><XCircle className="w-3.5 h-3.5" />Відхилити</button>
                        </div>
                        {msg && <p className={`text-xs ${/✓/.test(msg) ? 'text-emerald-600' : 'text-red-600'}`}>{msg}</p>}
                      </div>

                      {card.events?.length > 0 && (
                        <div className="pt-3 border-t border-border">
                          <div className="text-[11px] text-muted-foreground mb-2">Історія</div>
                          <div className="space-y-1.5 max-h-40 overflow-auto">
                            {card.events.map((e) => (
                              <div key={e.id} className="text-xs flex justify-between gap-2">
                                <span>{e.kind} {e.to_status ? `→ ${e.to_status}` : ''} {e.level ? `(${e.level})` : ''}</span>
                                <span className="text-muted-foreground">{formatDateUk(e.created_at)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
            </div>
          </div>
        </>
      )}

      {tab === 'assets' && (
        <div className="rounded-2xl border border-border bg-card divide-y divide-border overflow-hidden" data-testid="acc-asset-access">
          {assets.items.length === 0 ? <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
            : assets.items.map((a) => (
              <div key={a.id} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2"><Building2 className="w-4 h-4 text-muted-foreground" /><div><div className="font-medium text-sm">{a.title}</div><div className="text-[11px] text-muted-foreground">{a.status}</div></div></div>
                <select value={a.access_level} onChange={(e) => setAccess(a.id, e.target.value)} data-testid={`access-${a.id}`} className="h-9 px-2 rounded-lg border border-border bg-background text-sm">
                  {assets.levels.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
