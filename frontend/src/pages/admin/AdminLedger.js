import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, lumenError } from '@/lib/lumenApi';
import { BookOpen, ArrowDownCircle, ArrowUpCircle, Filter, Loader2 } from 'lucide-react';

const REASONS = [
  { value: '',                     label: 'Всі' },
  { value: 'investment_funding',   label: 'Фінансування інвестиції' },
  { value: 'payout',               label: 'Виплата дивідендів' },
  { value: 'withdrawal',           label: 'Вивід коштів' },
  { value: 'adjustment',           label: 'Коригування' },
  { value: 'refund',               label: 'Повернення' },
];

export default function AdminLedger() {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({ credit: {}, debit: {}, total_uah_credit: 0, total_uah_debit: 0, net_uah: 0 });
  const [type, setType] = useState('');
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (type) params.set('entry_type', type);
      if (reason) params.set('reason', reason);
      const r = await lumen.get('/admin/ledger' + (params.toString() ? `?${params}` : ''));
      setItems(r.data?.items || []);
      setSummary(r.data?.summary || {});
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити реєстр')); }
    finally { setLoading(false); }
  }, [type, reason]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6 md:p-10" data-testid="admin-ledger">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Журнал</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Фінансовий реєстр (Ledger)</h1>
        <p className="mt-1 text-token-muted">Append-only журнал усіх рухів коштів. Будь-яка зміна балансу — лише через цей реєстр.</p>
      </header>

      <div className="grid sm:grid-cols-4 gap-3 mb-6">
        <SummaryCard label="Credit (USD)" value={formatUAH(summary.total_uah_credit)} icon={<ArrowDownCircle className="w-5 h-5 text-emerald-600" />} testid="sum-credit" />
        <SummaryCard label="Debit (USD)" value={formatUAH(summary.total_uah_debit)} icon={<ArrowUpCircle className="w-5 h-5 text-red-500" />} testid="sum-debit" />
        <SummaryCard label="Net (USD)" value={formatUAH(summary.net_uah)} testid="sum-net" />
        <SummaryCard label="Усього проведень" value={items.length} testid="sum-count" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4 items-center" data-testid="ledger-filters">
        <Filter className="w-4 h-4 text-muted-foreground" />
        <FilterPills value={type} onChange={setType} options={[{ value: '', label: 'Всі' }, { value: 'credit', label: 'Credit' }, { value: 'debit', label: 'Debit' }]} testidPrefix="type" />
        <span className="mx-2 text-muted-foreground">·</span>
        <FilterPills value={reason} onChange={setReason} options={REASONS} testidPrefix="reason" />
      </div>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-14 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center">
          <BookOpen className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Проведень за фільтром не знайдено</p>
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="ledger-table">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Дата</th>
                <th className="text-left px-4 py-3 font-medium">Тип</th>
                <th className="text-left px-4 py-3 font-medium">Причина</th>
                <th className="text-left px-4 py-3 font-medium">Інвестор / Актив</th>
                <th className="text-right px-4 py-3 font-medium">Сума</th>
                <th className="text-right px-4 py-3 font-medium">USD</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-t border-border" data-testid={`ledger-row-${e.id}`}>
                  <td className="px-4 py-3 text-muted-foreground">{formatDateUk(e.created_at)}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${e.entry_type === 'credit' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-700'}`}>
                      {e.entry_type === 'credit' ? 'Credit' : 'Debit'}
                    </span>
                  </td>
                  <td className="px-4 py-3">{e.reason_label}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    <p>{e.investor_id?.slice(0, 12) || '—'}</p>
                    <p>{e.asset_id || '—'}</p>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-mono">
                    {e.entry_type === 'credit' ? '+' : '−'}{Number(e.amount).toLocaleString('uk-UA')} {e.currency}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono font-semibold ${e.entry_type === 'credit' ? 'text-emerald-700' : 'text-red-700'}`}>
                    {e.entry_type === 'credit' ? '+' : '−'}{formatUAH(e.amount_uah)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const SummaryCard = ({ label, value, icon, testid }) => (
  <div data-testid={testid} className="rounded-2xl border border-border bg-card p-4">
    <div className="flex items-center gap-2 mb-1">
      {icon}
      <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
    </div>
    <p className="text-2xl font-bold tabular-nums">{value}</p>
  </div>
);

const FilterPills = ({ value, onChange, options, testidPrefix }) => (
  <>
    {options.map((o) => (
      <button key={o.value} onClick={() => onChange(o.value)}
        data-testid={`${testidPrefix}-${o.value || 'all'}`}
        className={`px-3 h-8 rounded-full text-xs font-medium border transition ${
          value === o.value ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'
        }`}>
        {o.label}
      </button>
    ))}
  </>
);
