import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, API, lumenError } from '@/lib/lumenApi';
import {
  ShieldCheck, AlertCircle, CheckCircle2, XCircle, FileText,
  Loader2, ExternalLink, Users,
} from 'lucide-react';

const STATUS_BADGE = {
  not_started:  { label: 'Не розпочато',  cls: 'bg-muted text-muted-foreground' },
  draft:        { label: 'Чернетка',       cls: 'bg-amber-100 text-amber-800' },
  submitted:    { label: 'Подано',         cls: 'bg-sky-100 text-sky-800' },
  under_review: { label: 'На розгляді',    cls: 'bg-sky-100 text-sky-800' },
  approved:     { label: 'Підтверджено',   cls: 'bg-emerald-100 text-emerald-800' },
  rejected:     { label: 'Відхилено',      cls: 'bg-red-100 text-red-700' },
  expired:      { label: 'Прострочено',    cls: 'bg-red-100 text-red-700' },
};

const FILTERS = [
  { value: '',             label: 'Черга' },
  { value: 'submitted',    label: 'Подані' },
  { value: 'under_review', label: 'На розгляді' },
  { value: 'approved',     label: 'Підтверджені' },
  { value: 'rejected',     label: 'Відхилені' },
  { value: 'draft',        label: 'Чернетки' },
];

export default function AdminKyc() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // investor card
  const [cardLoading, setCardLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [note, setNote] = useState('');
  const [acting, setActing] = useState('');
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const loadQueue = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/kyc' + (f ? `?status=${f}` : ''));
      const data = r?.data || r;
      setItems(data.items || []);
      setCounts(data.counts || {});
    } catch (_e) {
      setError('Не вдалось завантажити чергу KYC');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const openCard = async (investorId) => {
    setCardLoading(true);
    setError('');
    setRejectReason('');
    setNote('');
    try {
      const r = await lumen.get(`/admin/kyc/${investorId}`);
      setSelected(r?.data || r);
    } catch (_e) {
      setError('Не вдалось відкрити картку інвестора');
    } finally {
      setCardLoading(false);
    }
  };

  const approve = async () => {
    if (!selected) return;
    setActing('approve');
    setError('');
    try {
      const r = await lumen.post(`/admin/kyc/${selected.user_id}/approve`, { note: note || null });
      const data = r?.data || r;
      setFlash(`Верифікацію підтверджено${data.activated_investments ? ` · активовано інвестицій: ${data.activated_investments}` : ''}`);
      setTimeout(() => setFlash(''), 4000);
      await openCard(selected.user_id);
      await loadQueue();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось підтвердити'));
    } finally {
      setActing('');
    }
  };

  const reject = async () => {
    if (!selected) return;
    if (!rejectReason.trim()) {
      setError('Вкажіть причину відхилення — це обов\'язково');
      return;
    }
    setActing('reject');
    setError('');
    try {
      await lumen.post(`/admin/kyc/${selected.user_id}/reject`, { reason: rejectReason.trim() });
      setFlash('Анкету відхилено, інвестора повідомлено');
      setTimeout(() => setFlash(''), 4000);
      await openCard(selected.user_id);
      await loadQueue();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось відхилити'));
    } finally {
      setActing('');
    }
  };

  const actionable = selected && ['submitted', 'under_review'].includes(selected.kyc_status);

  return (
    <div className="p-6 md:p-10" data-testid="admin-kyc">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Комплаєнс</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Верифікація інвесторів (KYC)</h1>
      </header>

      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="kyc-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="kyc-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      {/* filters */}
      <div className="flex flex-wrap gap-2 mb-6" data-testid="kyc-filters">
        {FILTERS.map((f) => {
          const count = f.value === ''
            ? (counts.submitted || 0) + (counts.under_review || 0)
            : (counts[f.value] || 0);
          return (
            <button
              key={f.value || 'queue'}
              onClick={() => { setFilter(f.value); setSelected(null); }}
              className={`px-4 h-9 rounded-full text-sm font-medium border transition ${
                filter === f.value
                  ? 'bg-foreground text-background border-foreground'
                  : 'border-border hover:border-[#2E5D4F]'
              }`}
              data-testid={`kyc-filter-${f.value || 'queue'}`}
            >
              {f.label}{count > 0 && <span className="ml-1.5 opacity-70">{count}</span>}
            </button>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* queue list */}
        <div className="lg:col-span-2">
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            {loading ? (
              <div className="p-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground" data-testid="kyc-queue-empty">
                <Users className="w-6 h-6 mx-auto mb-2 opacity-40" />
                Черга порожня
              </div>
            ) : (
              <ul className="divide-y divide-border" data-testid="kyc-queue-list">
                {items.map((p) => {
                  const b = STATUS_BADGE[p.kyc_status] || STATUS_BADGE.not_started;
                  return (
                    <li key={p.user_id}>
                      <button
                        onClick={() => openCard(p.user_id)}
                        className={`w-full text-left px-4 py-3 hover:bg-muted/50 transition ${selected?.user_id === p.user_id ? 'bg-muted/60' : ''}`}
                        data-testid={`kyc-queue-item-${p.user_id}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-medium text-sm truncate">{p.full_name || p.name || p.email}</p>
                          <span className={`text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap ${b.cls}`}>{b.label}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">{p.email} · документів: {p.documents_count ?? 0}</p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* investor card */}
        <div className="lg:col-span-3">
          {cardLoading ? (
            <div className="rounded-2xl border border-border bg-card p-10 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : !selected ? (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="kyc-card-empty">
              <ShieldCheck className="w-6 h-6 mx-auto mb-2 opacity-40" />
              Оберіть інвестора зі списку, щоб переглянути анкету
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card p-6" data-testid="kyc-card">
              <div className="flex items-start justify-between gap-3 mb-5">
                <div>
                  <h2 className="text-xl font-bold">{selected.full_name || selected.name || '—'}</h2>
                  <p className="text-sm text-muted-foreground">{selected.email}</p>
                </div>
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${(STATUS_BADGE[selected.kyc_status] || STATUS_BADGE.not_started).cls}`} data-testid="kyc-card-status">
                  {(STATUS_BADGE[selected.kyc_status] || STATUS_BADGE.not_started).label}
                </span>
              </div>

              {selected.kyc_status === 'rejected' && selected.kyc_notes && (
                <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm">
                  <span className="font-medium">Причина відхилення:</span> {selected.kyc_notes}
                </div>
              )}

              <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm mb-6" data-testid="kyc-card-fields">
                <Row label="Дата народження" value={selected.date_of_birth} />
                <Row label="Телефон" value={selected.phone} />
                <Row label="Громадянство" value={selected.country} />
                <Row label="Резидентство" value={selected.residency_country} />
                <Row label="РНОКПП" value={selected.tax_id} />
                <Row label="IBAN" value={selected.iban} mono />
                <Row label="Банк" value={selected.bank_name} />
                <Row label="Ризик-профіль" value={selected.risk_profile} />
                <Row label="Інвестицій очікує KYC" value={String(selected.kyc_pending_investments ?? 0)} />
                <Row label="Активних інвестицій" value={String(selected.active_investments ?? 0)} />
              </dl>

              <h3 className="font-semibold text-sm mb-2">Документи ({(selected.documents || []).length})</h3>
              {(selected.documents || []).length === 0 ? (
                <p className="text-sm text-muted-foreground mb-6">Документи не завантажені</p>
              ) : (
                <ul className="divide-y divide-border mb-6" data-testid="kyc-card-docs">
                  {selected.documents.map((d) => (
                    <li key={d.id} className="py-2.5 flex items-center gap-3">
                      <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{d.doc_type_label}</p>
                        <p className="text-xs text-muted-foreground truncate">{d.filename} · {formatDateUk(d.created_at)}</p>
                      </div>
                      <a
                        href={`${API.replace(/\/api$/, '')}${d.file_url}`}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition"
                        title="Відкрити файл"
                        data-testid={`kyc-doc-open-${d.doc_type}`}
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}

              {actionable ? (
                <div className="border-t border-border pt-5 space-y-4">
                  <label className="block">
                    <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Коментар комплаєнс (необов'язково для approve)</span>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      data-testid="kyc-note"
                      className="mt-1 w-full h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                    />
                  </label>
                  <label className="block">
                    <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Причина відхилення (обов'язкова для reject)</span>
                    <textarea
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      rows={2}
                      data-testid="kyc-reject-reason-input"
                      className="mt-1 w-full px-3 py-2 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                    />
                  </label>
                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={approve}
                      disabled={!!acting}
                      className="inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
                      data-testid="kyc-approve"
                    >
                      {acting === 'approve' ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                      Підтвердити
                    </button>
                    <button
                      onClick={reject}
                      disabled={!!acting || !rejectReason.trim()}
                      className="inline-flex items-center gap-2 px-5 h-10 rounded-full border border-red-300 text-red-600 text-sm font-medium hover:bg-red-50 transition disabled:opacity-40"
                      data-testid="kyc-reject"
                    >
                      {acting === 'reject' ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                      Відхилити
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground border-t border-border pt-4">
                  Дії доступні лише для анкет у статусі «подано» або «на розгляді».
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const Row = ({ label, value, mono }) => (
  <div>
    <dt className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</dt>
    <dd className={`mt-0.5 ${mono ? 'font-mono text-xs' : ''}`}>{value || '—'}</dd>
  </div>
);
