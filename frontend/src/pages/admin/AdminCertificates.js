/**
 * AdminCertificates — LUMEN 2.0 / Phase A2.
 * Certificate registry for operators: filter by status/asset/investor, inspect
 * the event audit, force re-issue / void, view A2 invariants, open PDF.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Award, RefreshCw, ShieldCheck, ShieldAlert, Download, ArrowLeft,
  Ban, RefreshCcw, Activity, Search, CheckCircle2, XCircle, Clock,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const STATUS_META = {
  active:   { label: 'Активний',  cls: 'text-emerald-600 bg-emerald-500/10' },
  voided:   { label: 'Анульовано', cls: 'text-rose-600 bg-rose-500/10' },
  replaced: { label: 'Замінено',  cls: 'text-amber-600 bg-amber-500/10' },
  expired:  { label: 'Прострочено', cls: 'text-token-muted bg-app-elevated' },
  draft:    { label: 'Чернетка',  cls: 'text-token-muted bg-app-elevated' },
};

const EVENT_LABEL = {
  issued: 'Випущено', voided: 'Анульовано', reissued: 'Перевипущено',
  transferred: 'Передано', verified: 'Перевірено', downloaded: 'Завантажено',
};

const FILTERS = [
  { key: '', label: 'Усі' },
  { key: 'active', label: 'Активні' },
  { key: 'replaced', label: 'Замінені' },
  { key: 'voided', label: 'Анульовані' },
];

function Badge({ status }) {
  const m = STATUS_META[status] || STATUS_META.draft;
  return <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-lg ${m.cls}`}>{m.label}</span>;
}

export default function AdminCertificates() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [invariants, setInvariants] = useState(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, inv] = await Promise.all([
        api.get('/admin/certificates', { params: status ? { status } : {} }),
        api.get('/admin/certificates/invariants/check'),
      ]);
      setData(d);
      setInvariants(inv);
    } catch {
      toast.error('Не вдалось завантажити сертифікати');
    } finally { setLoading(false); }
  }, [toast, status]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (c) => {
    setSelected(c);
    try {
      const r = await api.get(`/admin/certificates/${c.id}`);
      setEvents(r.events || []);
      setSelected(r.certificate);
    } catch { setEvents([]); }
  };

  const openPdf = (c) => window.open(`${api.baseURL}/admin/certificates/${c.id}/pdf`, '_blank');

  const voidCert = async (c) => {
    setBusy(true);
    try {
      await api.post(`/admin/certificates/${c.id}/void`, { reason: 'admin void' });
      toast.success('Сертифікат анульовано');
      setSelected(null); await load();
    } catch (e) { toast.error('Не вдалось анулювати'); }
    finally { setBusy(false); }
  };

  const reissueCert = async (c) => {
    setBusy(true);
    try {
      await api.post(`/admin/certificates/${c.id}/reissue`);
      toast.success('Сертифікат перевипущено');
      setSelected(null); await load();
    } catch { toast.error('Не вдалось перевипустити'); }
    finally { setBusy(false); }
  };

  const reconcile = async () => {
    setBusy(true);
    try {
      const r = await api.post('/admin/certificates/reconcile');
      toast.success(`Звірка: випущено ${r.issued}, перевипущено ${r.reissued}, анульовано ${r.voided}`);
      await load();
    } catch { toast.error('Помилка звірки'); }
    finally { setBusy(false); }
  };

  const counts = data?.counts || {};
  const items = (data?.items || []).filter((c) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (c.certificate_number || '').toLowerCase().includes(s)
      || (c.asset_title || '').toLowerCase().includes(s)
      || (c.investor_name || '').toLowerCase().includes(s)
      || (c.verify_code || '').toLowerCase().includes(s);
  });
  const allOk = invariants?.all_ok;

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="admin-certificates">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Award className="w-4 h-4" /> Certificate Registry · A2</div>
          <h1 className="text-h1 mb-1 mt-1">Сертифікати</h1>
          <p className="text-small-token max-w-2xl">
            Реєстр інвестиційних сертифікатів поверх unit-registry. Сертифікати
            автоматично перевипускаються (burn &amp; re-issue) при вторинних угодах.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {invariants && (
            <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl ${allOk ? 'text-emerald-600 bg-emerald-500/10' : 'text-rose-600 bg-rose-500/10'}`}
              data-testid="certs-invariants-pill">
              {allOk ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
              {allOk ? 'Інваріанти OK' : 'Є порушення'}
            </span>
          )}
          <button onClick={reconcile} disabled={busy}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
            data-testid="certs-reconcile">
            <RefreshCcw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} /> Звірити
          </button>
        </div>
      </div>

      {/* Counts */}
      <div className="grid grid-cols-3 md:grid-cols-5 gap-3 mb-6" data-testid="certs-counts">
        {[['active', 'Активні'], ['replaced', 'Замінені'], ['voided', 'Анульовані'], ['expired', 'Прострочені'], ['draft', 'Чернетки']].map(([k, label]) => (
          <div key={k} className="rounded-xl border border-app bg-app-surface p-4">
            <div className="text-2xl font-bold text-token-primary tabular-nums">{counts[k] ?? 0}</div>
            <div className="text-[11px] uppercase tracking-wider text-token-muted">{label}</div>
          </div>
        ))}
      </div>

      {/* Filters + search */}
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setStatus(f.key)}
              data-testid={`certs-filter-${f.key || 'all'}`}
              className={`px-3 py-1.5 rounded-lg text-sm font-semibold transition ${status === f.key ? 'bg-[#2E5D4F] text-white' : 'border border-app text-token-secondary hover:text-token-primary'}`}>
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-token-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Пошук № / актив / інвестор / код"
            data-testid="certs-search"
            className="pl-9 pr-3 py-2 rounded-xl border border-app bg-app-surface text-sm text-token-primary w-72 outline-none focus:border-app-strong" />
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-12 rounded-xl bg-app-elevated animate-pulse" />)}</div>
      ) : (
        <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="certs-table">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-token-muted border-b border-app">
                  <th className="px-5 py-3 font-bold">Сертифікат</th>
                  <th className="px-5 py-3 font-bold">Інвестор</th>
                  <th className="px-5 py-3 font-bold">Актив</th>
                  <th className="px-5 py-3 font-bold text-right">Одиниці</th>
                  <th className="px-5 py-3 font-bold text-right">Частка</th>
                  <th className="px-5 py-3 font-bold">Статус</th>
                  <th className="px-5 py-3 font-bold text-right">Дії</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-b border-app/60 last:border-0 hover:bg-app-elevated/50 cursor-pointer"
                    onClick={() => openDetail(c)} data-testid={`cert-row-${c.id}`}>
                    <td className="px-5 py-3 font-semibold text-token-primary tabular-nums">{c.certificate_number}</td>
                    <td className="px-5 py-3 text-token-secondary truncate max-w-[160px]">{c.investor_name}</td>
                    <td className="px-5 py-3 text-token-secondary truncate max-w-[180px]">{c.asset_title}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-token-primary">{nfmt(c.units)}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-token-secondary">{Number(c.ownership_percent).toFixed(2)}%</td>
                    <td className="px-5 py-3"><Badge status={c.status} /></td>
                    <td className="px-5 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => openPdf(c)} className="text-token-muted hover:text-[#2E5D4F] p-1" title="PDF"><Download className="w-4 h-4" /></button>
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr><td colSpan={7} className="px-5 py-10 text-center text-token-muted">Сертифікатів не знайдено.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end" data-testid="cert-detail-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={() => setSelected(null)} />
          <div className="relative w-full max-w-lg bg-app-surface h-full overflow-y-auto shadow-xl">
            <div className="px-5 py-4 border-b border-app flex items-center gap-3 sticky top-0 bg-app-surface z-10">
              <button onClick={() => setSelected(null)} className="text-token-muted hover:text-token-primary"><ArrowLeft className="w-5 h-5" /></button>
              <div className="min-w-0 flex-1">
                <div className="text-token-kicker">Сертифікат</div>
                <h3 className="font-semibold text-token-primary truncate">{selected.certificate_number}</h3>
              </div>
              <Badge status={selected.status} />
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><div className="text-token-muted text-[11px] uppercase">Інвестор</div><div className="font-medium text-token-primary">{selected.investor_name}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Актив</div><div className="font-medium text-token-primary">{selected.asset_title}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">SPV</div><div className="font-medium text-token-primary">{selected.spv_name}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Код перевірки</div><div className="font-medium text-token-primary">{selected.verify_code}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Одиниці</div><div className="font-medium text-token-primary tabular-nums">{nfmt(selected.units)}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Частка</div><div className="font-medium text-token-primary tabular-nums">{Number(selected.ownership_percent).toFixed(4)}%</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Вартість</div><div className="font-medium text-token-primary tabular-nums">{formatUAH(selected.value_uah)}</div></div>
                <div><div className="text-token-muted text-[11px] uppercase">Випущено</div><div className="font-medium text-token-primary">{formatDateUk(selected.issue_date)}</div></div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={() => openPdf(selected)}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-app text-xs font-semibold text-token-secondary hover:text-token-primary transition">
                  <Download className="w-3.5 h-3.5" /> PDF
                </button>
                {selected.status === 'active' && (
                  <>
                    <button onClick={() => reissueCert(selected)} disabled={busy}
                      data-testid="cert-reissue"
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-amber-500/40 text-xs font-semibold text-amber-600 hover:bg-amber-500/10 transition disabled:opacity-50">
                      <RefreshCcw className="w-3.5 h-3.5" /> Перевипустити
                    </button>
                    <button onClick={() => voidCert(selected)} disabled={busy}
                      data-testid="cert-void"
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-rose-500/40 text-xs font-semibold text-rose-600 hover:bg-rose-500/10 transition disabled:opacity-50">
                      <Ban className="w-3.5 h-3.5" /> Анулювати
                    </button>
                  </>
                )}
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2"><Activity className="w-4 h-4 text-token-muted" /><h4 className="font-semibold text-token-primary text-sm">Аудит подій</h4></div>
                {events.length === 0 ? (
                  <div className="text-sm text-token-muted">Подій немає.</div>
                ) : (
                  <ul className="divide-y divide-app/60 border border-app rounded-xl overflow-hidden">
                    {events.map((e) => (
                      <li key={e.id} className="px-4 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-token-primary">{EVENT_LABEL[e.event_type] || e.event_type}</span>
                          <span className="text-[11px] text-token-muted">{formatDateUk(e.created_at)}</span>
                        </div>
                        {e.note && <div className="text-[12px] text-token-muted mt-0.5">{e.note}</div>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
