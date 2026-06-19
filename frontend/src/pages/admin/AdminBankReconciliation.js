/**
 * AdminBankReconciliation.js — Phase H1.1
 *
 * Admin Operations Console for SEPA / SWIFT institutional rails.
 *
 * UX scope:
 *   • Transfer queue (filter by status / rail / direction / currency).
 *   • Stats KPIs (total / pending / confirmed / failed / cancelled, by rail).
 *   • Per-transfer actions: confirm (with provider_ref + settled_at + note),
 *     reject (with reason), reconcile (with bank statement ref + observed
 *     amount + currency, computes delta + currency_mismatch).
 *   • Per-transfer event timeline.
 *   • Bulk export to CSV.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import {
  Landmark, RefreshCw, Loader2, X, AlertTriangle, CheckCircle2,
  Banknote, FileDown, Filter, Search, Building2, Globe2, Zap,
  ArrowDownToLine, ArrowUpFromLine, ShieldCheck, Clock,
  Copy, ListFilter,
} from 'lucide-react';

const STATUS_META = {
  draft:     { label: 'Чернетка',         cls: 'bg-muted text-muted-foreground' },
  pending:   { label: 'Очікує',           cls: 'bg-amber-100 text-amber-900' },
  initiated: { label: 'Ініційовано',      cls: 'bg-sky-100 text-sky-900' },
  sent:      { label: 'Відправлено',      cls: 'bg-indigo-100 text-indigo-900' },
  confirmed: { label: 'Підтверджено',     cls: 'bg-emerald-100 text-emerald-900' },
  failed:    { label: 'Помилка',          cls: 'bg-red-100 text-red-800' },
  returned:  { label: 'Повернено',        cls: 'bg-rose-100 text-rose-800' },
  cancelled: { label: 'Скасовано',        cls: 'bg-zinc-200 text-zinc-700' },
};

function formatMoney(amount, currency) {
  const n = Number(amount);
  if (isNaN(n)) return '—';
  try {
    return n.toLocaleString('uk-UA', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }) + ' ' + (currency || '');
  } catch (_e) { return `${n.toFixed(2)} ${currency || ''}`; }
}

export default function AdminBankReconciliation() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [flash, setFlash] = useState('');
  const [filters, setFilters] = useState({
    status: '', rail: '', direction: '', q: '',
  });
  const [active, setActive] = useState(null);
  const [actionMode, setActionMode] = useState(null);  // confirm | reject | reconcile

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status) params.set('status', filters.status);
      if (filters.rail) params.set('rail', filters.rail);
      params.set('limit', '500');
      const [list, st] = await Promise.all([
        lumen.get(`/admin/lumen/institutional/rails/transfers?${params}`),
        lumen.get('/admin/lumen/institutional/rails/stats'),
      ]);
      setItems(list.data?.items || []);
      setStats(st.data || null);
      setErr('');
    } catch (e) {
      setErr(lumenError(e, 'Не вдалось завантажити перекази'));
    } finally { setLoading(false); }
  }, [filters.status, filters.rail]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    let xs = items;
    if (filters.direction) xs = xs.filter(t => t.direction === filters.direction);
    if (filters.q) {
      const q = filters.q.toLowerCase();
      xs = xs.filter(t =>
        (t.reference || '').toLowerCase().includes(q) ||
        (t.beneficiary_name || '').toLowerCase().includes(q) ||
        (t.beneficiary_iban || '').toLowerCase().includes(q) ||
        (t.investor_id || '').toLowerCase().includes(q) ||
        (t.id || '').toLowerCase().includes(q)
      );
    }
    return xs;
  }, [items, filters.direction, filters.q]);

  const flashOk = (m) => { setFlash(m); setTimeout(() => setFlash(''), 3500); };

  const openDetail = async (transfer) => {
    try {
      const r = await lumen.get(`/lumen/institutional/rails/transfers/${transfer.id}`);
      setActive({ transfer: r.data?.transfer || transfer,
                  events: r.data?.events || [] });
      setActionMode(null);
    } catch (e) { setErr(lumenError(e, 'Не вдалось відкрити переказ')); }
  };

  const exportCsv = () => {
    if (filtered.length === 0) return;
    const hdr = ['id', 'reference', 'rail', 'direction', 'status', 'amount',
                  'currency', 'beneficiary_name', 'beneficiary_iban',
                  'beneficiary_bic', 'beneficiary_country', 'investor_id',
                  'fund_id', 'provider_ref', 'created_at', 'settled_at',
                  'failure_reason'];
    const rows = filtered.map(t => hdr.map(k => {
      const v = t[k];
      if (v === null || v === undefined) return '';
      const s = String(v).replace(/"/g, '""');
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s}"` : s;
    }).join(','));
    const csv = [hdr.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '');
    a.href = url; a.download = `lumen_rails_${ts}.csv`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-bank-recon">
      <header className="mb-8 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Phase H1 · Банківські рейки</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight flex items-center gap-2">
            <Landmark className="w-7 h-7 text-signal" />
            Bank Reconciliation
          </h1>
          <p className="mt-2 text-muted-foreground max-w-2xl">
            Черга інституційних переказів (SEPA / SWIFT). Підтверджуйте за випискою банку,
            зіставляйте з reference, помічайте дельти та валютні розбіжності.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={load}
            className="px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition flex items-center gap-1.5"
            data-testid="recon-refresh">
            <RefreshCw className="w-4 h-4" /> Оновити
          </button>
          <button onClick={exportCsv} disabled={filtered.length === 0}
            className="px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted transition flex items-center gap-1.5 disabled:opacity-50"
            data-testid="recon-export">
            <FileDown className="w-4 h-4" /> Експорт CSV ({filtered.length})
          </button>
        </div>
      </header>

      {flash && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 px-4 py-3 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {err && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5" /> {err}
        </div>
      )}

      {/* Stats KPIs */}
      {stats?.totals && (
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <KpiCard label="Всього" value={stats.totals.transfers} icon={<Banknote className="w-4 h-4" />} />
          <KpiCard label="Очікують" value={stats.totals.pending} tone="amber" icon={<Clock className="w-4 h-4" />} />
          <KpiCard label="Підтверджено" value={stats.totals.confirmed} tone="emerald" icon={<CheckCircle2 className="w-4 h-4" />} />
          <KpiCard label="Помилки" value={stats.totals.failed} tone="red" icon={<AlertTriangle className="w-4 h-4" />} />
          <KpiCard label="Скасовано" value={stats.totals.cancelled} tone="zinc" icon={<X className="w-4 h-4" />} />
        </section>
      )}

      {/* Filters */}
      <section className="rounded-2xl border border-border bg-card p-4 mb-4 flex flex-wrap items-center gap-3" data-testid="recon-filters">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
          className="px-2 py-1.5 rounded-md border border-border bg-background text-sm" data-testid="recon-filter-status">
          <option value="">Усі статуси</option>
          {Object.entries(STATUS_META).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
        </select>
        <select value={filters.rail} onChange={e => setFilters(f => ({ ...f, rail: e.target.value }))}
          className="px-2 py-1.5 rounded-md border border-border bg-background text-sm" data-testid="recon-filter-rail">
          <option value="">Усі rails</option>
          <option value="sepa">SEPA</option>
          <option value="sepa_instant">SEPA Instant</option>
          <option value="swift">SWIFT</option>
        </select>
        <select value={filters.direction} onChange={e => setFilters(f => ({ ...f, direction: e.target.value }))}
          className="px-2 py-1.5 rounded-md border border-border bg-background text-sm" data-testid="recon-filter-direction">
          <option value="">Обидва напрямки</option>
          <option value="inbound">Вхідні</option>
          <option value="outbound">Вихідні</option>
        </select>
        <div className="flex-1 min-w-[200px] flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-background">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input value={filters.q} onChange={e => setFilters(f => ({ ...f, q: e.target.value }))}
            placeholder="Пошук: reference, бенефіціар, IBAN, investor_id…"
            className="flex-1 text-sm bg-transparent outline-none"
            data-testid="recon-search" />
        </div>
        <button onClick={() => setFilters({ status: '', rail: '', direction: '', q: '' })}
          className="text-xs text-muted-foreground hover:text-foreground" data-testid="recon-clear">
          Очистити
        </button>
      </section>

      {/* Table */}
      <section className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-10 flex items-center justify-center text-muted-foreground gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Завантаження…
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-muted-foreground">
            <Banknote className="w-10 h-10 mx-auto mb-3 opacity-60" />
            Немає переказів за обраними фільтрами.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="recon-table">
              <thead className="bg-muted/40">
                <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3">Reference</th>
                  <th className="px-4 py-3">Rail</th>
                  <th className="px-4 py-3">Інвестор</th>
                  <th className="px-4 py-3">Бенефіціар</th>
                  <th className="px-4 py-3">IBAN</th>
                  <th className="px-4 py-3">Напрям</th>
                  <th className="px-4 py-3 text-right">Сума</th>
                  <th className="px-4 py-3">Статус</th>
                  <th className="px-4 py-3">Створено</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => {
                  const m = STATUS_META[t.status] || { label: t.status, cls: 'bg-muted' };
                  return (
                    <tr key={t.id} className="border-t border-border hover:bg-muted/30" data-testid={`recon-row-${t.id}`}>
                      <td className="px-4 py-3 font-mono text-xs">{t.reference}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1 text-xs font-medium">
                          {t.rail === 'sepa_instant' && <Zap className="w-3 h-3 text-amber-500" />}
                          {t.rail === 'swift' ? <Building2 className="w-3 h-3 text-sky-500" /> : t.rail === 'sepa' ? <Globe2 className="w-3 h-3 text-emerald-500" /> : null}
                          {t.rail.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{(t.investor_id || '').slice(-10)}</td>
                      <td className="px-4 py-3 text-xs">{t.beneficiary_name}</td>
                      <td className="px-4 py-3 font-mono text-[11px]">{(t.beneficiary_iban || '').slice(0, 8)}…</td>
                      <td className="px-4 py-3 text-xs">
                        {t.direction === 'inbound'
                          ? <span className="inline-flex items-center gap-1 text-emerald-700"><ArrowDownToLine className="w-3 h-3" /> in</span>
                          : <span className="inline-flex items-center gap-1 text-sky-700"><ArrowUpFromLine className="w-3 h-3" /> out</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-medium">{formatMoney(t.amount, t.currency)}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${m.cls}`}>{m.label}</span>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateUk(t.created_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => openDetail(t)}
                          className="text-signal hover:underline text-xs font-medium" data-testid={`recon-open-${t.id}`}>
                          Відкрити →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Detail + action panel */}
      {active && (
        <ReconDrawer
          transfer={active.transfer}
          events={active.events}
          actionMode={actionMode}
          setActionMode={setActionMode}
          onClose={() => { setActive(null); setActionMode(null); }}
          onActionDone={(msg) => { flashOk(msg); load(); openDetail(active.transfer); }}
        />
      )}
    </div>
  );
}

function KpiCard({ label, value, tone, icon }) {
  const map = {
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    red: 'bg-red-50 border-red-200 text-red-800',
    zinc: 'bg-zinc-50 border-zinc-200 text-zinc-700',
  };
  return (
    <div className={`rounded-xl border p-3 ${map[tone] || 'bg-card border-border text-foreground'}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider">{label}</span>
        <span className="opacity-80">{icon}</span>
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value ?? 0}</p>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/* Drawer with confirm/reject/reconcile flows                              */
/* ────────────────────────────────────────────────────────────────────── */
function ReconDrawer({ transfer, events, onClose, actionMode, setActionMode, onActionDone }) {
  const t = transfer;
  const meta = STATUS_META[t.status] || { label: t.status, cls: 'bg-muted' };
  const isTerminal = ['confirmed', 'failed', 'returned', 'cancelled'].includes(t.status);

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end" data-testid="recon-drawer">
      <div className="w-full max-w-3xl bg-card text-foreground h-full overflow-y-auto border-l border-border shadow-2xl">
        <div className="sticky top-0 bg-card/95 backdrop-blur z-10 px-6 py-4 border-b border-border flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t.rail.toUpperCase().replace('_', ' ')} переказ</p>
            <h2 className="text-lg font-semibold mt-0.5">{t.reference}</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" data-testid="recon-drawer-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`px-3 py-1 rounded-md text-sm font-medium ${meta.cls}`}>{meta.label}</span>
            <span className="text-xl font-bold">{formatMoney(t.amount, t.currency)}</span>
            <span className="text-sm text-muted-foreground">· {t.direction === 'inbound' ? 'Вхідний' : 'Вихідний'}</span>
            {t.rail === 'sepa_instant' && <span className="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-900 flex items-center gap-1"><Zap className="w-3 h-3" /> Instant</span>}
          </div>

          {/* Beneficiary card */}
          <section className="rounded-xl border border-border bg-muted/20 p-4 space-y-1.5">
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-2">Реквізити</h3>
            <Row label="Бенефіціар" value={t.beneficiary_name} />
            <Row label="IBAN" value={t.beneficiary_iban} mono />
            {t.beneficiary_bic && <Row label="BIC" value={t.beneficiary_bic} mono />}
            {t.intermediary_bic && <Row label="Intermediary BIC" value={t.intermediary_bic} mono />}
            <Row label="Investor ID" value={t.investor_id} mono />
            {t.fund_id && <Row label="Fund ID" value={t.fund_id} mono />}
            {t.purpose && <Row label="Призначення" value={t.purpose} />}
            {t.provider_ref && <Row label="Bank ref" value={t.provider_ref} mono />}
            {t.settled_at && <Row label="Settled" value={formatDateUk(t.settled_at)} />}
            {t.failure_reason && <Row label="Причина" value={t.failure_reason} accent="text-red-700" />}
          </section>

          {/* Reconciliation result */}
          {t.reconciliation && (
            <section className={`rounded-xl border p-4 ${t.reconciliation.matched ? 'border-emerald-200 bg-emerald-50/60' : 'border-rose-200 bg-rose-50/60'}`} data-testid="recon-result-block">
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-2 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" /> Реконсиляція
              </h3>
              <Row label="Matched" value={t.reconciliation.matched ? 'так' : 'ні'} accent={t.reconciliation.matched ? 'text-emerald-700' : 'text-rose-700'} />
              <Row label="Δ amount" value={`${t.reconciliation.delta_amount >= 0 ? '+' : ''}${t.reconciliation.delta_amount} ${t.currency}`} />
              {t.reconciliation.currency_mismatch && <Row label="Currency mismatch" value="⚠ так" accent="text-rose-700" />}
              <Row label="Bank statement" value={t.reconciliation.bank_statement_ref} mono />
              <Row label="Reconciled at" value={formatDateUk(t.reconciliation.reconciled_at)} />
            </section>
          )}

          {/* Action toolbar */}
          {!isTerminal && !actionMode && (
            <section className="flex flex-wrap gap-2" data-testid="recon-actions">
              <button onClick={() => setActionMode('confirm')}
                className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 flex items-center gap-1.5"
                data-testid="recon-action-confirm">
                <CheckCircle2 className="w-4 h-4" /> Підтвердити
              </button>
              <button onClick={() => setActionMode('reject')}
                className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 flex items-center gap-1.5"
                data-testid="recon-action-reject">
                <X className="w-4 h-4" /> Відхилити
              </button>
              <button onClick={() => setActionMode('reconcile')}
                className="px-4 py-2 rounded-lg border border-border text-sm font-medium hover:bg-muted flex items-center gap-1.5"
                data-testid="recon-action-reconcile">
                <ShieldCheck className="w-4 h-4" /> Зіставити
              </button>
            </section>
          )}
          {isTerminal && (
            <section className="text-sm text-muted-foreground rounded-lg bg-muted/40 px-4 py-3">
              Переказ у фінальному статусі — дії недоступні. Доступна лише пост-фактум реконсиляція:
              <button onClick={() => setActionMode('reconcile')}
                className="ml-2 px-3 py-1 rounded-md border border-border text-xs font-medium hover:bg-card"
                data-testid="recon-action-reconcile-terminal">
                <ShieldCheck className="w-3 h-3 inline" /> зіставити з випискою
              </button>
            </section>
          )}

          {actionMode === 'confirm' && (
            <ConfirmForm transfer={t} onClose={() => setActionMode(null)}
              onDone={() => onActionDone('Переказ підтверджено та проведено в реєстрі.')} />
          )}
          {actionMode === 'reject' && (
            <RejectForm transfer={t} onClose={() => setActionMode(null)}
              onDone={() => onActionDone('Переказ відхилено.')} />
          )}
          {actionMode === 'reconcile' && (
            <ReconcileForm transfer={t} onClose={() => setActionMode(null)}
              onDone={() => onActionDone('Реконсиляція збережена.')} />
          )}

          {/* Timeline */}
          <section>
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-3 flex items-center gap-1.5">
              <Clock className="w-4 h-4" /> Історія подій
            </h3>
            <ol className="space-y-3" data-testid="recon-events">
              {events.map((ev, idx) => (
                <li key={ev.id || idx} className="flex gap-3">
                  <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${STATUS_META[ev.status]?.cls?.includes('emerald') ? 'bg-emerald-500' : STATUS_META[ev.status]?.cls?.includes('red') || STATUS_META[ev.status]?.cls?.includes('rose') ? 'bg-red-500' : 'bg-signal'}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium ${STATUS_META[ev.status]?.cls || 'bg-muted'}`}>{STATUS_META[ev.status]?.label || ev.status}</span>
                      <span className="text-xs text-muted-foreground">{formatDateUk(ev.at)}</span>
                      <span className="text-xs text-muted-foreground font-mono">· {(ev.actor || '').slice(-10)}</span>
                    </div>
                    {ev.message && <p className="text-sm text-foreground mt-1">{ev.message}</p>}
                  </div>
                </li>
              ))}
              {events.length === 0 && <p className="text-sm text-muted-foreground">Подій ще немає.</p>}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

function ConfirmForm({ transfer, onClose, onDone }) {
  const [providerRef, setProviderRef] = useState('');
  const [settledAt, setSettledAt] = useState(new Date().toISOString().slice(0, 16));
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/lumen/institutional/rails/transfers/${transfer.id}/confirm`, {
        provider_ref: providerRef.trim() || null,
        settled_at: settledAt ? new Date(settledAt).toISOString() : null,
        note: note.trim() || null,
      });
      onDone();
    } catch (e) { setErr(lumenError(e, 'Не вдалось підтвердити')); }
    finally { setBusy(false); }
  };
  return (
    <ActionPanel title="Підтвердити переказ" onClose={onClose} tone="emerald" data-testid="recon-confirm-form">
      <Field label="Bank reference (з виписки)">
        <input value={providerRef} onChange={e => setProviderRef(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background font-mono text-sm"
          placeholder="BANK-STMT-2026-..." data-testid="confirm-provider-ref" />
      </Field>
      <Field label="Дата зарахування">
        <input type="datetime-local" value={settledAt}
          onChange={e => setSettledAt(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
          data-testid="confirm-settled-at" />
      </Field>
      <Field label="Нотатка (опціонально)">
        <input value={note} onChange={e => setNote(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
          placeholder="Зараховано через Bank XYZ"
          data-testid="confirm-note" />
      </Field>
      {err && <div className="text-sm text-red-700 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> {err}</div>}
      <FormButtons busy={busy} onClose={onClose} onSubmit={submit} primary="Підтвердити" tone="emerald" testid="confirm-submit" />
    </ActionPanel>
  );
}

function RejectForm({ transfer, onClose, onDone }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => {
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/lumen/institutional/rails/transfers/${transfer.id}/reject`,
        { reason: reason.trim() });
      onDone();
    } catch (e) { setErr(lumenError(e, 'Не вдалось відхилити')); }
    finally { setBusy(false); }
  };
  return (
    <ActionPanel title="Відхилити переказ" onClose={onClose} tone="red" data-testid="recon-reject-form">
      <Field label="Причина відхилення">
        <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} required minLength={2} maxLength={240}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
          placeholder="Бенефіціар не пройшов KYC / IBAN недійсний / повернено банком…"
          data-testid="reject-reason" />
      </Field>
      {err && <div className="text-sm text-red-700 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> {err}</div>}
      <FormButtons busy={busy} onClose={onClose} onSubmit={submit} primary="Відхилити" tone="red"
        disabled={reason.trim().length < 2} testid="reject-submit" />
    </ActionPanel>
  );
}

function ReconcileForm({ transfer, onClose, onDone }) {
  const [bankRef, setBankRef] = useState('');
  const [amount, setAmount] = useState(transfer.amount);
  const [currency, setCurrency] = useState(transfer.currency);
  const [settledAt, setSettledAt] = useState(new Date().toISOString().slice(0, 16));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const delta = Number(amount) - Number(transfer.amount);
  const currencyMismatch = currency.toUpperCase() !== transfer.currency.toUpperCase();
  const submit = async () => {
    setBusy(true); setErr('');
    try {
      await lumen.post(`/admin/lumen/institutional/rails/transfers/${transfer.id}/reconcile`, {
        bank_statement_ref: bankRef.trim(),
        amount_observed: Number(amount),
        currency_observed: currency.toUpperCase(),
        settled_at: settledAt ? new Date(settledAt).toISOString() : null,
      });
      onDone();
    } catch (e) { setErr(lumenError(e, 'Не вдалось зіставити')); }
    finally { setBusy(false); }
  };
  return (
    <ActionPanel title="Зіставити з випискою банку" onClose={onClose} tone="signal" data-testid="recon-reconcile-form">
      <Field label="Bank statement reference">
        <input value={bankRef} onChange={e => setBankRef(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background font-mono text-sm"
          placeholder="STMT-2026-Q2-..." required data-testid="recon-bank-ref" />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <Field label="Спостережувана сума">
            <input type="number" step="0.01" value={amount} onChange={e => setAmount(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm tabular-nums"
              required data-testid="recon-observed-amount" />
          </Field>
        </div>
        <Field label="Валюта">
          <input value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())} maxLength={3}
            className={`w-full px-3 py-2 rounded-lg border bg-background text-sm font-mono ${currencyMismatch ? 'border-rose-300' : 'border-border'}`}
            required data-testid="recon-observed-currency" />
        </Field>
      </div>
      <Field label="Дата зарахування">
        <input type="datetime-local" value={settledAt} onChange={e => setSettledAt(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
          data-testid="recon-observed-settled" />
      </Field>
      <div className={`rounded-lg px-3 py-2 text-sm flex items-center gap-2 ${Math.abs(delta) < 0.01 && !currencyMismatch ? 'bg-emerald-50 text-emerald-900' : 'bg-amber-50 text-amber-900'}`} data-testid="recon-delta-preview">
        {Math.abs(delta) < 0.01 && !currencyMismatch ? (
          <><CheckCircle2 className="w-4 h-4" /> Очікується matched (Δ = 0).</>
        ) : (
          <><AlertTriangle className="w-4 h-4" /> Δ = {delta >= 0 ? '+' : ''}{delta.toFixed(2)} {transfer.currency}{currencyMismatch ? `, валюта: ${currency} ≠ ${transfer.currency}` : ''}.</>
        )}
      </div>
      {err && <div className="text-sm text-red-700 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> {err}</div>}
      <FormButtons busy={busy} onClose={onClose} onSubmit={submit} primary="Зіставити" tone="signal"
        disabled={!bankRef.trim() || !amount} testid="recon-submit" />
    </ActionPanel>
  );
}

function ActionPanel({ title, onClose, children, tone = 'signal', ...rest }) {
  const toneCls = {
    emerald: 'border-emerald-200 bg-emerald-50/40',
    red: 'border-red-200 bg-red-50/40',
    signal: 'border-border bg-muted/30',
  }[tone] || 'border-border bg-muted/30';
  return (
    <section className={`rounded-xl border p-4 space-y-3 ${toneCls}`} {...rest}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">{title}</h4>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xs">Скасувати</button>
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wider text-muted-foreground mb-1">{label}</span>
      {children}
    </label>
  );
}

function FormButtons({ busy, onClose, onSubmit, primary, tone, disabled, testid }) {
  const toneCls = {
    emerald: 'bg-emerald-600 hover:bg-emerald-700',
    red: 'bg-red-600 hover:bg-red-700',
    signal: 'bg-signal hover:opacity-90',
  }[tone] || 'bg-signal hover:opacity-90';
  return (
    <div className="flex items-center justify-end gap-2 pt-2">
      <button type="button" onClick={onClose} disabled={busy}
        className="px-3 py-2 rounded-lg border border-border text-sm hover:bg-muted">
        Скасувати
      </button>
      <button type="button" onClick={onSubmit} disabled={busy || disabled}
        className={`px-4 py-2 rounded-lg text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50 ${toneCls}`}
        data-testid={testid}>
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
        {primary}
      </button>
    </div>
  );
}

function Row({ label, value, mono, accent }) {
  return (
    <div className="flex items-start gap-3 text-sm">
      <span className="w-36 text-xs uppercase tracking-wider text-muted-foreground flex-shrink-0">{label}</span>
      <span className={`flex-1 min-w-0 break-words ${mono ? 'font-mono text-sm' : ''} ${accent || ''}`}>{value}</span>
    </div>
  );
}
