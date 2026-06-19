import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  Inbox, Loader2, CheckCircle2, XCircle, AlertCircle, FileSignature,
} from 'lucide-react';

const STATUS_BADGE = {
  submitted:    { label: 'Подана',        cls: 'bg-amber-100 text-amber-800' },
  under_review: { label: 'На розгляді',   cls: 'bg-sky-100 text-sky-800' },
  converted:    { label: 'Підтверджена',  cls: 'bg-emerald-100 text-emerald-800' },
  rejected:     { label: 'Відхилена',     cls: 'bg-red-100 text-red-700' },
  cancelled:    { label: 'Скасована',     cls: 'bg-muted text-muted-foreground' },
};

const FILTERS = [
  { value: 'submitted', label: 'Нові' },
  { value: '',          label: 'Всі' },
  { value: 'converted', label: 'Підтверджені' },
  { value: 'rejected',  label: 'Відхилені' },
];

export default function AdminIntents() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('submitted');
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(''); // `${action}:${id}`
  const [rejectId, setRejectId] = useState(null);
  const [rejectNote, setRejectNote] = useState('');
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/intents' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (_e) {
      setError('Не вдалось завантажити заявки');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const approve = async (id) => {
    setActing(`approve:${id}`);
    setError('');
    try {
      const r = await lumen.post(`/admin/intents/${id}/approve`, {});
      const d = r.data || {};
      const num = d.contract?.number;
      setFlash(d.kyc_required
        ? `Заявку підтверджено. Договір ${num || ''} згенеровано — інвестор має пройти KYC та підписати договір.`
        : `Заявку підтверджено. Договір ${num || ''} надіслано інвестору на підпис.`);
      setTimeout(() => setFlash(''), 6000);
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось підтвердити заявку'));
    } finally {
      setActing('');
    }
  };

  const reject = async (id) => {
    setActing(`reject:${id}`);
    setError('');
    try {
      await lumen.post(`/admin/intents/${id}/reject`, { note: rejectNote.trim() || null });
      setFlash('Заявку відхилено, інвестора повідомлено');
      setTimeout(() => setFlash(''), 4000);
      setRejectId(null);
      setRejectNote('');
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось відхилити заявку'));
    } finally {
      setActing('');
    }
  };

  return (
    <div className="p-6 md:p-10" data-testid="admin-intents">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Операції</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Заявки на інвестиції</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Підтвердження заявки автоматично генерує договір — інвестиція активується після KYC та підписання.
        </p>
      </header>

      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="intents-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="intents-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-6" data-testid="intents-filters">
        {FILTERS.map((f) => {
          const count = f.value === ''
            ? Object.values(counts).reduce((a, b) => a + (b || 0), 0)
            : (counts[f.value] || 0);
          return (
            <button
              key={f.value || 'all'}
              onClick={() => setFilter(f.value)}
              className={`px-4 h-9 rounded-full text-sm font-medium border transition ${
                filter === f.value ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'
              }`}
              data-testid={`intents-filter-${f.value || 'all'}`}
            >
              {f.label}{count > 0 && <span className="ml-1.5 opacity-70">{count}</span>}
            </button>
          );
        })}
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="p-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground" data-testid="intents-empty">
            <Inbox className="w-6 h-6 mx-auto mb-2 opacity-40" />
            Заявок немає
          </div>
        ) : (
          <table className="w-full text-sm" data-testid="intents-table">
            <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
              <tr>
                <th className="text-left px-5 py-3 font-medium">Інвестор</th>
                <th className="text-left px-5 py-3 font-medium">Актив</th>
                <th className="text-right px-5 py-3 font-medium">Сума</th>
                <th className="text-left px-5 py-3 font-medium">Статус</th>
                <th className="text-right px-5 py-3 font-medium">Подана</th>
                <th className="text-right px-5 py-3 font-medium">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((it) => {
                const b = STATUS_BADGE[it.status] || { label: it.status, cls: 'bg-muted text-muted-foreground' };
                const actionable = ['submitted', 'under_review'].includes(it.status);
                return (
                  <tr key={it.id} className="hover:bg-muted/40 transition" data-testid={`intent-row-${it.id}`}>
                    <td className="px-5 py-4">
                      <p className="font-medium">{it.investor_name || '—'}</p>
                      <p className="text-xs text-muted-foreground">{it.investor_email}</p>
                    </td>
                    <td className="px-5 py-4 text-muted-foreground">{it.asset_title}</td>
                    <td className="px-5 py-4 text-right font-mono font-semibold">{formatUAH(it.amount)}</td>
                    <td className="px-5 py-4">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${b.cls}`}>{b.label}</span>
                    </td>
                    <td className="px-5 py-4 text-right text-muted-foreground whitespace-nowrap">{formatDateUk(it.submitted_at)}</td>
                    <td className="px-5 py-4">
                      {actionable ? (
                        rejectId === it.id ? (
                          <div className="flex items-center gap-2 justify-end">
                            <input
                              value={rejectNote}
                              onChange={(e) => setRejectNote(e.target.value)}
                              placeholder="Причина (необов'язково)"
                              className="h-9 px-3 w-44 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-xs"
                              data-testid={`intent-reject-note-${it.id}`}
                            />
                            <button
                              onClick={() => reject(it.id)}
                              disabled={!!acting}
                              className="inline-flex items-center gap-1 px-3 h-9 rounded-full border border-red-300 text-red-600 text-xs font-medium hover:bg-red-50 transition disabled:opacity-40"
                              data-testid={`intent-reject-confirm-${it.id}`}
                            >
                              {acting === `reject:${it.id}` ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
                              Відхилити
                            </button>
                            <button
                              onClick={() => { setRejectId(null); setRejectNote(''); }}
                              className="text-xs text-muted-foreground hover:text-foreground transition"
                            >
                              Скасувати
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 justify-end">
                            <button
                              onClick={() => approve(it.id)}
                              disabled={!!acting}
                              className="inline-flex items-center gap-1.5 px-4 h-9 rounded-full bg-[#2E5D4F] text-white text-xs font-medium hover:opacity-90 transition disabled:opacity-50"
                              data-testid={`intent-approve-${it.id}`}
                            >
                              {acting === `approve:${it.id}` ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileSignature className="w-3.5 h-3.5" />}
                              Підтвердити
                            </button>
                            <button
                              onClick={() => setRejectId(it.id)}
                              disabled={!!acting}
                              className="inline-flex items-center gap-1 px-3 h-9 rounded-full border border-border text-xs font-medium hover:border-red-300 hover:text-red-600 transition disabled:opacity-40"
                              data-testid={`intent-reject-${it.id}`}
                            >
                              <XCircle className="w-3.5 h-3.5" /> Відхилити
                            </button>
                          </div>
                        )
                      ) : (
                        <span className="block text-right text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
