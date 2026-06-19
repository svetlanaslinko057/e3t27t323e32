import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, API, lumenError } from '@/lib/lumenApi';
import {
  CreditCard, FileText, Loader2, CheckCircle2, AlertCircle, Clock,
  X, Download, MessageCircle, Filter, BookOpen, Landmark,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';

/** Sprint 6 — Admin Finance Queue */

const PAYMENT_STATUS_BADGE = {
  awaiting_payment: { label: 'Очікує оплату',    cls: 'bg-amber-100 text-amber-800' },
  paid:              { label: 'На перевірці',      cls: 'bg-sky-100 text-sky-800' },
  under_review:     { label: 'Уточнення',          cls: 'bg-orange-100 text-orange-800' },
  confirmed:         { label: 'Підтверджено',     cls: 'bg-emerald-100 text-emerald-800' },
  rejected:          { label: 'Відхилено',        cls: 'bg-red-100 text-red-700' },
  cancelled:         { label: 'Скасовано',        cls: 'bg-muted text-muted-foreground' },
};

const FILTERS = [
  { value: '',                 label: 'Всі' },
  { value: 'paid',             label: 'На перевірці' },
  { value: 'under_review',     label: 'Уточнення' },
  { value: 'awaiting_payment', label: 'Очікують оплати' },
  { value: 'confirmed',         label: 'Підтверджені' },
  { value: 'rejected',          label: 'Відхилені' },
];

export default function AdminPayments() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('paid');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/payments' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити чергу')); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await lumen.get(`/admin/payments/${id}`);
      setSelected(r.data);
    } catch (e) { setError(lumenError(e, 'Не вдалось відкрити платіж')); }
  };

  const refreshAfterAction = async (message) => {
    setFlash(message); setError('');
    await load();
    setSelected(null);
    setTimeout(() => setFlash(''), 4000);
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-payments">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Фінансовий контур</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Платежі інвесторів</h1>
          <p className="mt-1 text-token-muted">Перевіряйте, підтверджуйте або повертайте платежі. Ownership активу створюється лише після <em>confirmed</em>.</p>
        </div>
        <div className="flex gap-2">
          <NavLink to="/admin/funding-accounts" data-testid="link-funding-accounts"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] text-sm">
            <Landmark className="w-4 h-4" /> Реквізити
          </NavLink>
          <NavLink to="/admin/ledger" data-testid="link-ledger"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] text-sm">
            <BookOpen className="w-4 h-4" /> Реєстр (Ledger)
          </NavLink>
        </div>
      </header>

      {flash && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {flash}</div>}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      <div className="flex flex-wrap gap-2 mb-4" data-testid="admin-payments-filters">
        {FILTERS.map((f) => (
          <button key={f.value} onClick={() => setFilter(f.value)}
            data-testid={`filter-${f.value || 'all'}`}
            className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-xs font-medium border transition ${
              filter === f.value ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'}`}>
            {f.label}
            {counts[f.value] !== undefined && <span className="px-1.5 rounded bg-muted text-foreground">{counts[f.value]}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3, 4].map((i) => <div key={i} className="h-14 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="admin-payments-empty">
          <CreditCard className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Платежів у цій категорії немає</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="admin-payments-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Інвестор</th>
                <th className="text-left px-4 py-3 font-medium">Актив</th>
                <th className="text-right px-4 py-3 font-medium">Сума</th>
                <th className="text-left px-4 py-3 font-medium">Дата</th>
                <th className="text-left px-4 py-3 font-medium">Підтв.</th>
                <th className="text-right px-4 py-3 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const meta = PAYMENT_STATUS_BADGE[p.status] || { label: p.status_label, cls: 'bg-muted' };
                return (
                  <tr key={p.id}
                    onClick={() => openDetail(p.id)}
                    data-testid={`payment-row-${p.id}`}
                    className="border-t border-border cursor-pointer hover:bg-muted/30 transition">
                    <td className="px-4 py-3">
                      <p className="font-medium">{p.investor_name || '—'}</p>
                      <p className="text-xs text-muted-foreground">{p.investor_email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium truncate max-w-[260px]">{p.asset_title}</p>
                      <p className="text-xs text-muted-foreground">{p.asset_location}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <p className="font-mono font-semibold">{Number(p.amount).toLocaleString('uk-UA')} {p.currency}</p>
                      {p.currency !== 'UAH' && <p className="text-xs text-muted-foreground">≈ {formatUAH(p.amount_uah)}</p>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateUk(p.submitted_at || p.created_at)}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 text-xs">
                        <FileText className="w-3 h-3" /> {(p.proof_ids || []).length}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <AdminPaymentDrawer
          payment={selected}
          onClose={() => setSelected(null)}
          onConfirmed={() => refreshAfterAction('Платіж підтверджено — інвестицію активовано, частку додано в реєстр.')}
          onRejected={() => refreshAfterAction('Платіж відхилено — інвестор отримав сповіщення.')}
          onClarified={() => refreshAfterAction('Запит на уточнення надіслано інвестору.')}
        />
      )}
    </div>
  );
}

function AdminPaymentDrawer({ payment, onClose, onConfirmed, onRejected, onClarified }) {
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const meta = PAYMENT_STATUS_BADGE[payment.status] || { label: payment.status_label, cls: 'bg-muted' };
  const canAct = payment.status === 'paid' || payment.status === 'under_review';

  const doConfirm = async () => {
    if (!window.confirm(`Підтвердити оплату ${Number(payment.amount).toLocaleString('uk-UA')} ${payment.currency}? Це створить ledger-проведення та активує інвестицію.`)) return;
    setActing(true); setError('');
    try {
      await lumen.post(`/admin/payments/${payment.id}/confirm`, { note: note || null });
      onConfirmed();
    } catch (e) { setError(lumenError(e, 'Не вдалось підтвердити')); }
    finally { setActing(false); }
  };
  const doReject = async () => {
    if (!reason.trim()) { setError('Вкажіть причину відхилення'); return; }
    setActing(true); setError('');
    try {
      await lumen.post(`/admin/payments/${payment.id}/reject`, { reason: reason.trim() });
      onRejected();
    } catch (e) { setError(lumenError(e, 'Не вдалось відхилити')); }
    finally { setActing(false); }
  };
  const doClarification = async () => {
    if (!note.trim()) { setError('Вкажіть текст уточнення'); return; }
    setActing(true); setError('');
    try {
      await lumen.post(`/admin/payments/${payment.id}/clarification`, { note: note.trim() });
      onClarified();
    } catch (e) { setError(lumenError(e, 'Не вдалось надіслати уточнення')); }
    finally { setActing(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="admin-payment-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full bg-background border-l border-border shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-token-muted">Платіж #{payment.id.slice(-8)}</p>
            <h2 className="text-xl font-bold mt-0.5">{payment.investor_name || payment.investor_email}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg" data-testid="drawer-close"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-6 space-y-6">
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-token-muted">Сума</p>
              <p className="text-3xl font-bold tabular-nums mt-1">{Number(payment.amount).toLocaleString('uk-UA')} {payment.currency}</p>
              {payment.currency !== 'UAH' && <p className="text-xs text-muted-foreground mt-0.5">≈ {formatUAH(payment.amount_uah)} · курс {payment.fx_rate}</p>}
            </div>
            <span className={`text-sm font-medium px-3 py-1 rounded-full ${meta.cls}`}>{meta.label}</span>
          </div>

          <section className="rounded-2xl border border-border bg-card p-4 text-sm space-y-1" data-testid="payment-info">
            <Row label="Інвестор" value={`${payment.investor_name || ''} · ${payment.investor_email}`} />
            <Row label="Актив" value={payment.asset_title} />
            <Row label="Метод" value={payment.method_label || payment.payment_method} />
            <Row label="Відкрито" value={formatDateUk(payment.created_at)} />
            {payment.submitted_at && <Row label="Подано на перевірку" value={formatDateUk(payment.submitted_at)} />}
            {payment.contract_id && <Row label="Договір" value={payment.contract_id.slice(0, 8)} />}
          </section>

          {payment.investment && (
            <section className="rounded-xl border border-border bg-muted/40 p-3 text-sm">
              <p className="text-xs text-muted-foreground mb-1">Поточний статус інвестиції</p>
              <p className="font-medium">{payment.investment.status_label}</p>
            </section>
          )}

          {/* Proofs */}
          <section>
            <h3 className="font-semibold mb-3">Підтвердження інвестора ({(payment.proofs || []).length})</h3>
            {(payment.proofs || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Інвестор ще не завантажив підтвердження.</p>
            ) : (
              <div className="space-y-2">
                {payment.proofs.map((p) => (
                  <a key={p.id} href={`${API}/payment-proofs/${p.id}/file`} target="_blank" rel="noopener noreferrer"
                    data-testid={`admin-proof-${p.id}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-border p-3 bg-card hover:border-[#2E5D4F]">
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText className="w-4 h-4 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{p.filename}</p>
                        <p className="text-xs text-muted-foreground">{(p.size / 1024).toFixed(0)} КБ · {formatDateUk(p.uploaded_at)}</p>
                      </div>
                    </div>
                    <Download className="w-4 h-4 text-muted-foreground shrink-0" />
                  </a>
                ))}
              </div>
            )}
          </section>

          {/* Ledger entries */}
          {(payment.ledger_entries || []).length > 0 && (
            <section data-testid="payment-ledger">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><BookOpen className="w-4 h-4" /> Реєстр</h3>
              {payment.ledger_entries.map((le) => (
                <div key={le.id} className="flex items-center justify-between p-3 rounded-xl border border-border bg-card text-sm mb-2">
                  <div>
                    <p className="font-medium">{le.reason_label}</p>
                    <p className="text-xs text-muted-foreground">{le.entry_type === 'credit' ? '+' : '−'} {Number(le.amount).toLocaleString('uk-UA')} {le.currency} · {formatDateUk(le.created_at)}</p>
                  </div>
                  <span className="font-mono font-semibold tabular-nums text-emerald-700">+ {formatUAH(le.amount_uah)}</span>
                </div>
              ))}
            </section>
          )}

          {error && <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

          {/* Admin actions */}
          {canAct ? (
            <section className="rounded-2xl border border-[#2E5D4F]/30 bg-emerald-50/30 p-4 space-y-4" data-testid="admin-actions">
              <p className="font-semibold">Рішення комплаєнсу</p>

              <div>
                <label className="block text-xs uppercase tracking-widest text-muted-foreground mb-1">Внутрішній коментар / уточнення</label>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                  data-testid="admin-note-input"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  placeholder="Наприклад: «Уточніть дату переказу»" />
              </div>

              <div>
                <label className="block text-xs uppercase tracking-widest text-muted-foreground mb-1">Причина відхилення (обов'язково для reject)</label>
                <input value={reason} onChange={(e) => setReason(e.target.value)}
                  data-testid="admin-reason-input"
                  className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm"
                  placeholder="Наприклад: «Сума не відповідає договору»" />
              </div>

              <div className="flex flex-wrap gap-2">
                <button onClick={doConfirm} disabled={acting}
                  data-testid="btn-confirm"
                  className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-emerald-600 text-white font-medium disabled:opacity-60">
                  {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Підтвердити
                </button>
                <button onClick={doClarification} disabled={acting || !note.trim()}
                  data-testid="btn-clarification"
                  className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-orange-300 text-orange-700 font-medium disabled:opacity-60">
                  <MessageCircle className="w-4 h-4" /> Запитати уточнення
                </button>
                <button onClick={doReject} disabled={acting || !reason.trim()}
                  data-testid="btn-reject"
                  className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-red-300 text-red-700 font-medium disabled:opacity-60">
                  <X className="w-4 h-4" /> Відхилити
                </button>
              </div>
            </section>
          ) : (
            <p className="text-sm text-muted-foreground">У цьому статусі дії неможливі.</p>
          )}

          {/* History */}
          <section>
            <h3 className="font-semibold mb-3">Історія</h3>
            <ol className="space-y-2">
              {(payment.history || []).slice().reverse().map((h, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-2 h-2 rounded-full bg-[#2E5D4F] mt-1.5" />
                  <div><p>{h.comment}</p><p className="text-xs text-muted-foreground">{formatDateUk(h.at)} · {h.status}</p></div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

const Row = ({ label, value }) => (
  <div className="flex justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span className="text-right truncate max-w-[60%]">{value || '—'}</span>
  </div>
);
