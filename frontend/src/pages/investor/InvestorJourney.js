/**
 * InvestorJourney — LUMEN 2.0 / Phase A3 — Portfolio Timeline 2.0.
 * The canonical ownership journey for each investment:
 * Заявка → KYC → Договір → Оплата → Сертифікат → Активна → Перша виплата → Виведення доходу.
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Route, FileText, ShieldCheck, FileSignature, CreditCard, Award,
  CheckCircle2, Banknote, Wallet, RefreshCw, Circle, Loader2, ChevronRight,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { formatUAH, formatDateUk } from '@/lib/lumenApi';

const nfmt = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : Number(n).toLocaleString('uk-UA', { maximumFractionDigits: 0 });

const STEP_ICON = {
  intent: FileText, kyc: ShieldCheck, contract: FileSignature, payment: CreditCard,
  certificate: Award, active: CheckCircle2, first_payout: Banknote, withdrawal: Wallet,
};

const STATE_BADGE = {
  active: 'text-emerald-600 bg-emerald-500/10',
  certificate_issued: 'text-sky-600 bg-sky-500/10',
  ownership_created: 'text-sky-600 bg-sky-500/10',
  payment_confirmed: 'text-amber-600 bg-amber-500/10',
  payment_pending: 'text-amber-600 bg-amber-500/10',
  contract_signed: 'text-violet-600 bg-violet-500/10',
  contract_pending: 'text-violet-600 bg-violet-500/10',
  kyc_approved: 'text-violet-600 bg-violet-500/10',
  kyc_pending: 'text-token-muted bg-app-elevated',
  intent_created: 'text-token-muted bg-app-elevated',
};

function StepNode({ step, last }) {
  const Icon = STEP_ICON[step.key] || Circle;
  const done = step.status === 'done';
  const current = step.status === 'current';
  const color = done ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]'
    : current ? 'bg-amber-500/15 text-amber-600 border-amber-500'
    : 'bg-app-elevated text-token-muted border-app';
  return (
    <div className="flex gap-3" data-testid={`step-${step.key}`}>
      <div className="flex flex-col items-center">
        <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center shrink-0 ${color}`}>
          {current ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
        </div>
        {!last && <div className={`w-0.5 flex-1 min-h-[20px] ${done ? 'bg-[#2E5D4F]' : 'bg-app'}`} />}
      </div>
      <div className={`pb-5 min-w-0 ${done || current ? '' : 'opacity-60'}`}>
        <div className="flex items-center gap-2">
          <span className="font-semibold text-token-primary text-sm">{step.label}</span>
          {done && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
        </div>
        {step.detail && <div className="text-[12px] text-token-secondary">{step.detail}</div>}
        {step.at && <div className="text-[11px] text-token-muted">{formatDateUk(step.at)}</div>}
      </div>
    </div>
  );
}

export default function InvestorJourney() {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get('/investor/lifecycle');
      setItems(d.items || []);
      if (d.items?.length) setOpenId((prev) => prev || d.items[0].investment_id);
    } catch {
      toast.error('Не вдалось завантажити шлях інвестицій');
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="investor-journey">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><Route className="w-4 h-4" /> Ownership Lifecycle · A3</div>
          <h1 className="text-h1 mb-1 mt-1">Шлях інвестицій</h1>
          <p className="text-small-token max-w-2xl">
            Повний канонічний шлях кожної інвестиції — від заявки до виведення доходу.
            Кожен крок підтверджено реальними подіями платформи.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
          data-testid="journey-refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">{[...Array(2)].map((_, i) => <div key={i} className="h-24 rounded-2xl bg-app-elevated animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-app bg-app-surface p-10 text-center">
          <Route className="w-10 h-10 mx-auto text-token-muted mb-3" />
          <p className="text-token-secondary font-medium">Поки немає інвестицій</p>
          <p className="text-sm text-token-muted mt-1">Створіть заявку, щоб побачити шлях володіння.</p>
        </div>
      ) : (
        <div className="space-y-4" data-testid="journey-list">
          {items.map((it) => {
            const open = openId === it.investment_id;
            return (
              <div key={it.investment_id} className="rounded-2xl border border-app bg-app-surface overflow-hidden" data-testid={`journey-${it.investment_id}`}>
                <button onClick={() => setOpenId(open ? null : it.investment_id)}
                  className="w-full flex items-center justify-between gap-4 p-5 text-left hover:bg-app-elevated/40 transition"
                  data-testid={`journey-toggle-${it.investment_id}`}>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-token-primary truncate">{it.asset_title}</h3>
                    <div className="text-[12px] text-token-muted">
                      {formatUAH(it.amount)} · {nfmt(it.units)} од. {it.certificate_number ? `· ${it.certificate_number}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-lg ${STATE_BADGE[it.canonical_state] || STATE_BADGE.intent_created}`}>
                      {it.canonical_state_label}
                    </span>
                    <div className="hidden sm:flex items-center gap-2">
                      <div className="h-1.5 w-24 rounded-full bg-app-elevated overflow-hidden">
                        <div className="h-full bg-[#2E5D4F]" style={{ width: `${(it.progress / it.total_steps) * 100}%` }} />
                      </div>
                      <span className="text-[11px] text-token-muted tabular-nums">{it.progress}/{it.total_steps}</span>
                    </div>
                    <ChevronRight className={`w-5 h-5 text-token-muted transition ${open ? 'rotate-90' : ''}`} />
                  </div>
                </button>
                {open && (
                  <div className="px-5 pb-5 pt-1 border-t border-app" data-testid={`journey-steps-${it.investment_id}`}>
                    <div className="mt-4">
                      {it.steps.map((s, idx) => (
                        <StepNode key={s.key} step={s} last={idx === it.steps.length - 1} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
