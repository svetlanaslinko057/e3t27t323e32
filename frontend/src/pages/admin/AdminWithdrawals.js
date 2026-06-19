import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import { NavLink } from 'react-router-dom';
import {
  Banknote, Loader2, CheckCircle2, AlertCircle, X, BookOpen, Wallet,
  ArrowDownToLine, ArrowUpFromLine, ShieldCheck, PlayCircle, Send,
} from 'lucide-react';

/** Sprint 7 — Admin Withdrawals queue */

const WD_BADGE = {
  requested:    { label: 'Створено',     cls: 'bg-sky-100 text-sky-800' },
  under_review: { label: 'На розгляді',  cls: 'bg-amber-100 text-amber-800' },
  approved:     { label: 'Схвалено',     cls: 'bg-indigo-100 text-indigo-800' },
  processing:   { label: 'Виконується',  cls: 'bg-violet-100 text-violet-800' },
  paid:         { label: 'Виплачено',    cls: 'bg-emerald-100 text-emerald-800' },
  rejected:     { label: 'Відхилено',    cls: 'bg-red-100 text-red-700' },
  cancelled:    { label: 'Скасовано',    cls: 'bg-muted text-muted-foreground' },
};

const FILTERS = [
  { value: '',             label: 'Всі' },
  { value: 'requested',    label: 'Нові' },
  { value: 'under_review', label: 'На розгляді' },
  { value: 'approved',     label: 'Схвалені' },
  { value: 'processing',   label: 'Виконуються' },
  { value: 'paid',         label: 'Виплачені' },
  { value: 'rejected',     label: 'Відхилені' },
];

export default function AdminWithdrawals() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [pendingUah, setPendingUah] = useState(0);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/withdrawals' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
      setPendingUah(r.data?.pending_uah || 0);
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити чергу виводів')); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const r = await lumen.get(`/admin/withdrawals/${id}`);
      setSelected(r.data);
    } catch (e) { setError(lumenError(e, 'Не вдалось відкрити заявку')); }
  };

  const afterAction = async (msg) => {
    setFlash(msg); setError('');
    await load();
    setSelected(null);
    setTimeout(() => setFlash(''), 4000);
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-withdrawals">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Казначейство</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Виводи коштів</h1>
          <p className="mt-1 text-token-muted">
            Опрацьовуйте заявки інвесторів. Списання в реєстр (ledger) відбувається лише на статусі <em>виплачено</em>.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-widest text-token-muted">У резерві</p>
            <p className="text-lg font-bold tabular-nums" data-testid="pending-uah">{formatUAH(pendingUah)}</p>
          </div>
          <NavLink to="/admin/ledger" data-testid="link-ledger"
            className="inline-flex items-center gap-2 px-4 h-10 rounded-full border border-border hover:border-[#2E5D4F] text-sm">
            <BookOpen className="w-4 h-4" /> Реєстр (Ledger)
          </NavLink>
        </div>
      </header>

      {flash && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {flash}</div>}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      <div className="flex flex-wrap gap-2 mb-4" data-testid="admin-withdrawals-filters">
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
        <div className="rounded-2xl border border-dashed border-border p-12 text-center" data-testid="admin-withdrawals-empty">
          <Banknote className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Заявок у цій категорії немає</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="admin-withdrawals-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Інвестор</th>
                <th className="text-left px-4 py-3 font-medium">Реквізити</th>
                <th className="text-right px-4 py-3 font-medium">Сума</th>
                <th className="text-left px-4 py-3 font-medium">Дата</th>
                <th className="text-right px-4 py-3 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => {
                const b = WD_BADGE[w.status] || { label: w.status_label, cls: 'bg-muted' };
                return (
                  <tr key={w.id} onClick={() => openDetail(w.id)}
                    data-testid={`withdrawal-row-${w.id}`}
                    className="border-t border-border cursor-pointer hover:bg-muted/30 transition">
                    <td className="px-4 py-3">
                      <p className="font-medium">{w.investor_name || '—'}</p>
                      <p className="text-xs text-muted-foreground">{w.investor_email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium">{w.bank_name}</p>
                      <p className="text-xs text-muted-foreground font-mono truncate max-w-[220px]">{w.iban}</p>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <p className="font-mono font-semibold">{Number(w.amount).toLocaleString('uk-UA')} {w.currency}</p>
                      {w.currency !== 'UAH' && <p className="text-xs text-muted-foreground">≈ {formatUAH(w.amount_uah)}</p>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateUk(w.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${b.cls}`}>{b.label}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <AdminWithdrawalDrawer
          data={selected}
          onClose={() => setSelected(null)}
          onActed={afterAction}
        />
      )}
    </div>
  );
}

function AdminWithdrawalDrawer({ data, onClose, onActed }) {
  const w = data.withdrawal;
  const wallet = data.wallet;
  const ledger = data.ledger_entries || [];
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [comment, setComment] = useState('');

  const b = WD_BADGE[w.status] || { label: w.status_label, cls: 'bg-muted' };

  // Allowed admin transitions, mirrors backend
  const transitions = {
    requested:    ['under_review', 'approved', 'rejected'],
    under_review: ['approved', 'rejected'],
    approved:     ['processing', 'paid', 'rejected'],
    processing:   ['paid', 'rejected'],
  };
  const allowed = transitions[w.status] || [];

  const act = async (action, requireComment = false) => {
    if (requireComment && !comment.trim()) { setError('Вкажіть причину відхилення'); return; }
    if (action === 'paid' && !window.confirm(
      `Підтвердити виплату ${Number(w.amount).toLocaleString('uk-UA')} ${w.currency}? Це створить списання у реєстрі (ledger).`)) return;
    setActing(true); setError('');
    try {
      await lumen.post(`/admin/withdrawals/${w.id}/${action}`, { comment: comment.trim() || null });
      const msgs = {
        review: 'Заявку взято на розгляд.',
        approve: 'Заявку схвалено.',
        processing: 'Заявку передано у роботу.',
        paid: 'Виплату підтверджено — списання додано у реєстр.',
        reject: 'Заявку відхилено — кошти повернуто інвестору.',
      };
      onActed(msgs[action] || 'Статус оновлено.');
    } catch (e) { setError(lumenError(e, 'Не вдалось виконати дію')); }
    finally { setActing(false); }
  };

  const ACTION_BTN = {
    under_review: { fn: () => act('review'),     label: 'На розгляд',  cls: 'border border-amber-300 text-amber-700', icon: ShieldCheck },
    approved:     { fn: () => act('approve'),     label: 'Схвалити',    cls: 'bg-indigo-600 text-white', icon: CheckCircle2 },
    processing:   { fn: () => act('processing'),  label: 'У роботу',    cls: 'border border-violet-300 text-violet-700', icon: PlayCircle },
    paid:         { fn: () => act('paid'),        label: 'Виплачено',   cls: 'bg-emerald-600 text-white', icon: Send },
    rejected:     { fn: () => act('reject', true),label: 'Відхилити',   cls: 'border border-red-300 text-red-700', icon: X },
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="admin-withdrawal-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full bg-background border-l border-border shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-widest text-token-muted">Заявка #{w.id.slice(-8)}</p>
            <h2 className="text-xl font-bold mt-0.5">{w.investor_name || w.investor_email}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg" data-testid="drawer-close"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-6 space-y-6">
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-token-muted">Сума до виводу</p>
              <p className="text-3xl font-bold tabular-nums mt-1">{Number(w.amount).toLocaleString('uk-UA')} {w.currency}</p>
              {w.currency !== 'UAH' && <p className="text-xs text-muted-foreground mt-0.5">≈ {formatUAH(w.amount_uah)} · курс {w.fx_rate}</p>}
            </div>
            <span className={`text-sm font-medium px-3 py-1 rounded-full ${b.cls}`}>{b.label}</span>
          </div>

          {/* Bank requisites */}
          <section className="rounded-2xl border border-border bg-card p-4 text-sm space-y-1" data-testid="withdrawal-requisites">
            <Row label="Банк" value={w.bank_name} />
            <Row label="IBAN" value={w.iban} mono />
            <Row label="Отримувач" value={w.beneficiary_name} />
            <Row label="Email" value={w.investor_email} />
            <Row label="Створено" value={formatDateUk(w.created_at)} />
            {w.ledger_entry_id && <Row label="Ledger проводка" value={w.ledger_entry_id} mono />}
          </section>

          {/* Investor wallet snapshot */}
          {wallet && (
            <section className="rounded-2xl border border-border bg-muted/40 p-4" data-testid="withdrawal-wallet">
              <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-1"><Wallet className="w-3.5 h-3.5" /> Гаманець інвестора</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div><p className="text-[10px] uppercase text-muted-foreground">Доступно</p><p className="font-semibold tabular-nums text-sm">{formatUAH(wallet.available_balance)}</p></div>
                <div><p className="text-[10px] uppercase text-muted-foreground">Резерв</p><p className="font-semibold tabular-nums text-sm">{formatUAH(wallet.pending_balance)}</p></div>
                <div><p className="text-[10px] uppercase text-muted-foreground">Виведено</p><p className="font-semibold tabular-nums text-sm">{formatUAH(wallet.total_out)}</p></div>
              </div>
            </section>
          )}

          {/* Comment */}
          {allowed.length > 0 && (
            <div data-testid="admin-comment-box">
              <label className="block text-xs uppercase tracking-widest text-muted-foreground mb-1">Коментар (обов'язковий для відхилення)</label>
              <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2}
                data-testid="admin-comment-input"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                placeholder="Внутрішня примітка або причина рішення" />
            </div>
          )}

          {error && <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

          {/* Actions */}
          {allowed.length > 0 ? (
            <section className="flex flex-wrap gap-2" data-testid="withdrawal-actions">
              {allowed.map((target) => {
                const a = ACTION_BTN[target];
                if (!a) return null;
                const Icon = a.icon;
                const isReject = target === 'rejected';
                return (
                  <button key={target} onClick={a.fn}
                    disabled={acting || (isReject && !comment.trim())}
                    data-testid={`action-${target}`}
                    className={`inline-flex items-center gap-2 px-4 h-10 rounded-full font-medium disabled:opacity-50 ${a.cls}`}>
                    {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />} {a.label}
                  </button>
                );
              })}
            </section>
          ) : (
            <p className="text-sm text-muted-foreground" data-testid="withdrawal-terminal">Заявка завершена — подальші дії неможливі.</p>
          )}

          {/* Ledger entries */}
          {ledger.length > 0 && (
            <section data-testid="withdrawal-ledger">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><BookOpen className="w-4 h-4" /> Реєстр інвестора</h3>
              <div className="space-y-2">
                {ledger.map((le) => {
                  const isIn = le.entry_type === 'credit';
                  return (
                    <div key={le.id} className="flex items-center justify-between p-3 rounded-xl border border-border bg-card text-sm">
                      <div className="flex items-center gap-2">
                        {isIn ? <ArrowDownToLine className="w-4 h-4 text-emerald-700" /> : <ArrowUpFromLine className="w-4 h-4 text-red-600" />}
                        <div>
                          <p className="font-medium">{le.reason_label}</p>
                          <p className="text-xs text-muted-foreground">{formatDateUk(le.created_at)}</p>
                        </div>
                      </div>
                      <span className={`font-mono font-semibold tabular-nums ${isIn ? 'text-emerald-700' : 'text-red-600'}`}>
                        {isIn ? '+' : '−'} {formatUAH(le.amount_uah)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* History */}
          <section>
            <h3 className="font-semibold mb-3">Історія заявки</h3>
            <ol className="space-y-2">
              {(w.history || []).slice().reverse().map((h, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="shrink-0 w-2 h-2 rounded-full bg-[#2E5D4F] mt-1.5" />
                  <div><p>{h.comment}</p><p className="text-xs text-muted-foreground">{formatDateUk(h.at)} · {WD_BADGE[h.status]?.label || h.status}</p></div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}

const Row = ({ label, value, mono }) => (
  <div className="flex justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span className={`text-right truncate max-w-[60%] ${mono ? 'font-mono text-xs' : ''}`}>{value || '—'}</span>
  </div>
);
