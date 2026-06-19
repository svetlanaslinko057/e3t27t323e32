/**
 * AdminOperations — Operations Center (LR-3b).
 * Read-only aggregator over existing processes: pending KYC, payments,
 * withdrawals, payouts and (manual) secondary-market disputes. Deep-links to
 * each operational queue. No new entities.
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  ShieldCheck, CreditCard, ArrowUpFromLine, Coins, Repeat,
  RefreshCw, ArrowRight, Inbox, AlertCircle, CheckCircle2, Activity,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';

const CARD_ICON = {
  kyc: ShieldCheck,
  payments: CreditCard,
  withdrawals: ArrowUpFromLine,
  payouts: Coins,
  disputes: Repeat,
};

const CARD_ACCENT = {
  kyc: 'text-sky-500 bg-sky-500/10',
  payments: 'text-emerald-500 bg-emerald-500/10',
  withdrawals: 'text-amber-500 bg-amber-500/10',
  payouts: 'text-violet-500 bg-violet-500/10',
  disputes: 'text-rose-500 bg-rose-500/10',
};

function recentLabel(card, r) {
  switch (card.key) {
    case 'kyc': return r.full_name || r.user_id || '—';
    case 'payments': return `${formatUAH(r.amount)} · ${r.status}`;
    case 'withdrawals': return `${formatUAH(r.amount)} · ${r.status}`;
    case 'payouts': return `${r.asset_id || '—'} · ${r.status}`;
    default: return r.id || '—';
  }
}

export default function AdminOperations() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get('/admin/operations/summary');
      setData(d);
    } catch {
      toast.error('Не вдалось завантажити центр операцій');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const cards = data?.cards || [];

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="admin-operations">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Activity className="w-4 h-4" /> Operations Center</div>
          <h1 className="text-h1 mb-1 mt-1">Центр операцій</h1>
          <p className="text-small-token max-w-2xl">
            Єдина черга завдань, що потребують дії команди: KYC, платежі, виводи,
            виплати доходу та спори. Натисніть на картку, щоб перейти до відповідної черги.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-token-muted font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" /> Оновлено {data.computed_at ? new Date(data.computed_at).toLocaleTimeString() : ''}
            </span>
          ) : null}
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
            data-testid="ops-refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
          </button>
        </div>
      </div>

      {/* Total banner */}
      <div className="rounded-2xl border border-app bg-app-surface p-5 mb-6 flex items-center gap-4" data-testid="ops-total">
        <div className="w-12 h-12 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center">
          <Inbox className="w-6 h-6" />
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-bold text-token-muted">Всього завдань у роботі</div>
          <div className="text-3xl font-bold text-token-primary tabular-nums" data-testid="ops-total-count">
            {loading && !data ? '…' : (data?.total_pending ?? 0)}
          </div>
        </div>
      </div>

      {loading && !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(5)].map((_, i) => <div key={i} className="h-56 rounded-2xl bg-app-elevated animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {cards.map((c) => {
            const Icon = CARD_ICON[c.key] || Inbox;
            const accent = CARD_ACCENT[c.key] || 'text-token-primary bg-app-elevated';
            return (
              <div
                key={c.key}
                data-testid={`ops-card-${c.key}`}
                className="rounded-2xl border border-app bg-app-surface overflow-hidden flex flex-col"
              >
                <div className="p-5">
                  <div className="flex items-start justify-between">
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${accent}`}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="text-right">
                      <div className="text-4xl font-bold text-token-primary tabular-nums leading-none" data-testid={`ops-count-${c.key}`}>{c.count}</div>
                    </div>
                  </div>
                  <h3 className="mt-4 font-semibold text-token-primary">{c.title}</h3>

                  {c.manual ? (
                    <p className="mt-2 text-xs text-token-muted leading-relaxed flex items-start gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {c.note}
                    </p>
                  ) : c.recent && c.recent.length ? (
                    <ul className="mt-3 space-y-1.5" data-testid={`ops-recent-${c.key}`}>
                      {c.recent.slice(0, 4).map((r, i) => (
                        <li key={i} className="flex items-center justify-between gap-2 text-xs">
                          <span className="truncate text-token-secondary">{recentLabel(c, r)}</span>
                          <span className="text-token-muted shrink-0">{formatDateUk(r.updated_at)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-xs text-token-muted">Немає завдань у черзі. Чисто ✨</p>
                  )}
                </div>
                <Link
                  to={c.link}
                  data-testid={`ops-link-${c.key}`}
                  className="mt-auto px-5 py-3.5 border-t border-app flex items-center justify-between text-sm font-semibold text-[#2E5D4F] hover:bg-app-elevated transition"
                >
                  {c.cta}
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
