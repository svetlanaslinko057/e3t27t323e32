import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, TrendingUp, Wallet, Building2, Calendar, ChevronRight, ShieldAlert, FileSignature } from 'lucide-react';
import { lumen, formatUAH, formatPercent, formatDateUk } from '@/lib/lumenApi';
import { useAuth } from '@/App';
import CabinetAppPromoBanner from '@/components/cabinet/CabinetAppPromoBanner';

export default function InvestorDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    lumen.get('/investor/portfolio')
      .then((r) => alive && setData(r.data))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  if (loading) {
    return <div className="p-8" data-testid="investor-dashboard"><div className="h-6 w-40 bg-muted animate-pulse rounded" /></div>;
  }

  const summary = data?.summary || {};
  const investments = data?.investments || [];
  const upcoming = data?.upcoming_payouts || [];
  const kycPendingCount = investments.filter((i) => i.status === 'kyc_pending').length;
  const contractPendingCount = investments.filter((i) => i.status === 'contract_pending').length;
  const awaitingPaymentCount = investments.filter((i) => i.status === 'awaiting_payment').length;

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8" data-testid="investor-dashboard">
      <header>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Огляд</p>
        <h1 className="mt-2 text-3xl md:text-4xl font-bold tracking-tight">
          Вітаємо, {user?.name || 'інвесторе'}
        </h1>
        <p className="mt-1 text-muted-foreground">Ось свіжий стан вашого портфеля.</p>
      </header>

      <CabinetAppPromoBanner />

      {kycPendingCount > 0 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 flex flex-col sm:flex-row sm:items-start gap-3" data-testid="kyc-pending-banner">
          <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-amber-900">
              {kycPendingCount === 1 ? 'Інвестиція очікує верифікації' : `Інвестицій очікує верифікації: ${kycPendingCount}`}
            </p>
            <p className="text-sm text-amber-800 mt-0.5">
              Завершіть верифікацію (KYC) у профілі — підтверджені заявки активуються автоматично.
            </p>
          </div>
          <Link
            to="/investor/profile"
            className="shrink-0 inline-flex items-center gap-1.5 px-4 h-9 rounded-full bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 transition"
            data-testid="kyc-pending-banner-cta"
          >
            Пройти верифікацію <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {contractPendingCount > 0 && (
        <div className="rounded-2xl border border-[#2E5D4F]/30 bg-[#2E5D4F]/5 p-5 flex flex-col sm:flex-row sm:items-start gap-3" data-testid="contract-pending-banner">
          <FileSignature className="w-5 h-5 text-[#2E5D4F] shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-[#1A3C32] dark:text-emerald-200">
              {contractPendingCount === 1 ? 'Інвестиція очікує підписання договору' : `Інвестицій очікує підписання договору: ${contractPendingCount}`}
            </p>
            <p className="text-sm text-muted-foreground mt-0.5">
              Підпишіть договір електронно — після підписання відкриється платіж.
            </p>
          </div>
          <Link
            to="/investor/contracts"
            className="shrink-0 inline-flex items-center gap-1.5 px-4 h-9 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition"
            data-testid="contract-pending-banner-cta"
          >
            Підписати договір <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {awaitingPaymentCount > 0 && (
        <div className="rounded-2xl border border-sky-200 bg-sky-50 p-5 flex flex-col sm:flex-row sm:items-start gap-3" data-testid="awaiting-payment-banner">
          <Wallet className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold text-sky-900">
              {awaitingPaymentCount === 1 ? 'Інвестиція очікує оплату' : `Інвестицій очікує оплату: ${awaitingPaymentCount}`}
            </p>
            <p className="text-sm text-sky-800 mt-0.5">
              Перейдіть у «Мої платежі», оплатіть за наданими реквізитами та завантажте підтвердження — інвестиція активується після підтвердження комплаєнсом.
            </p>
          </div>
          <Link
            to="/investor/payments"
            className="shrink-0 inline-flex items-center gap-1.5 px-4 h-9 rounded-full bg-sky-600 text-white text-sm font-medium hover:bg-sky-700 transition"
            data-testid="awaiting-payment-banner-cta"
          >
            Перейти до оплати <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={<Wallet className="w-4 h-4" />} label="Загальний портфель" value={formatUAH(summary.total_value)} hint={summary.change_label} testid="kpi-portfolio" />
        <KpiCard icon={<TrendingUp className="w-4 h-4" />} label="Середня дохідність" value={formatPercent(summary.average_yield)} hint="річна" testid="kpi-yield" />
        <KpiCard icon={<Building2 className="w-4 h-4" />} label="Активних інвестицій" value={summary.active_count ?? 0} hint="проєктів" testid="kpi-active" />
        <KpiCard icon={<Calendar className="w-4 h-4" />} label="Виплат цього року" value={formatUAH(summary.paid_this_year)} hint="YTD" testid="kpi-paid" />
      </section>

      <section className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <h2 className="font-semibold">Активні інвестиції</h2>
            <Link to="/investor/portfolio" className="text-xs text-[#2E5D4F] hover:underline">Дивитись всі</Link>
          </div>
          {investments.length === 0 ? (
            <EmptyBlock
              title="Ще немає активних інвестицій"
              text="Оберіть актив з активних раундів і оформіть першу позицію."
              cta={<Link to="/investor/opportunities" className="text-sm font-medium text-[#2E5D4F] inline-flex items-center gap-1">Переглянути об'єкти <ArrowUpRight className="w-3.5 h-3.5" /></Link>}
            />
          ) : (
            <ul className="divide-y divide-border">
              {investments.slice(0, 5).map((inv) => (
                <li key={inv.id} className="px-5 py-4 flex items-center gap-4 hover:bg-muted/40 transition">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate flex items-center gap-2">
                      {inv.asset_title}
                      {inv.status === 'kyc_pending' && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-medium whitespace-nowrap" data-testid={`inv-kyc-pending-${inv.id}`}>Очікує KYC</span>
                      )}
                      {inv.status === 'contract_pending' && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 font-medium whitespace-nowrap" data-testid={`inv-contract-pending-${inv.id}`}>Очікує підпису</span>
                      )}
                      {inv.status === 'awaiting_payment' && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-medium whitespace-nowrap" data-testid={`inv-awaiting-payment-${inv.id}`}>Очікує оплату</span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">{inv.asset_location} · {inv.share_percent?.toFixed(2)}%</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono font-semibold">{formatUAH(inv.invested_amount)}</p>
                    <p className="text-xs text-[#2E5D4F]">+{formatPercent(inv.current_yield)}</p>
                  </div>
                  <Link to={`/investor/assets/${inv.asset_id}`} className="text-muted-foreground hover:text-foreground">
                    <ChevronRight className="w-4 h-4" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-border bg-card">
          <div className="px-5 py-4 border-b border-border">
            <h2 className="font-semibold">Найближчі виплати</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Очікуєте надходження протягом 30 днів</p>
          </div>
          {upcoming.length === 0 ? (
            <EmptyBlock title="Виплат немає" text="Виплати з'являтимуться після оформлення першої позиції." />
          ) : (
            <ul className="divide-y divide-border">
              {upcoming.map((p) => (
                <li key={p.id} className="px-5 py-4">
                  <p className="font-medium text-sm">{p.asset_title}</p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-muted-foreground">{formatDateUk(p.scheduled_at)}</span>
                    <span className="font-mono font-semibold text-sm">{formatUAH(p.amount)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold">Рекомендуємо для вас</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Швидкий перехід до актуальних розділів кабінету.
        </p>
        <div className="mt-5 grid sm:grid-cols-3 gap-3">
          <QuickCard to="/investor/opportunities" title="Активні раунди" text="Нерухомість, земля, будівництво та комерція" />
          <QuickCard to="/investor/contracts" title="Договори" text="Підписання та юридичний контур інвестицій" />
          <QuickCard to="/investor/profile" title="Профіль і KYC" text="Перевірте верифікацію та реквізити виплат" />
        </div>
      </section>
    </div>
  );
}

const KpiCard = ({ icon, label, value, hint, testid }) => (
  <div className="rounded-2xl border border-border bg-card p-5" data-testid={testid}>
    <div className="flex items-center gap-2 text-muted-foreground">{icon}<span className="text-[11px] uppercase tracking-widest">{label}</span></div>
    <p className="mt-3 text-2xl font-bold tracking-tight">{value}</p>
    {hint && <p className="mt-1 text-xs text-[#2E5D4F]">{hint}</p>}
  </div>
);

const EmptyBlock = ({ title, text, cta }) => (
  <div className="p-10 text-center">
    <p className="font-semibold">{title}</p>
    <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">{text}</p>
    {cta && <div className="mt-4">{cta}</div>}
  </div>
);

const QuickCard = ({ to, title, text }) => (
  <Link to={to} className="rounded-xl border border-border bg-background p-4 hover:border-[#2E5D4F] hover:shadow-sm transition flex flex-col">
    <span className="font-medium">{title}</span>
    <span className="text-xs text-muted-foreground mt-1">{text}</span>
  </Link>
);
