/**
 * InvestorFunding.js — H1.1 Funding Center (investor side).
 *
 * 5 tabs: Deposit / Transfers / History / Bank Accounts / Documents.
 * Implements H1.1 constraints R1-R3 (see /app/plan.md and /app/backend/lumen_funding_center.py).
 */
import { useState } from 'react';
import { Wallet, Building2, History, Files, Send } from 'lucide-react';
import { useFundingLang, useFundingT } from '@/i18n/funding';
import DepositTab from '@/pages/funding/DepositTab';
import TransfersTab from '@/pages/funding/TransfersTab';
import HistoryTab from '@/pages/funding/HistoryTab';
import BankAccountsTab from '@/pages/funding/BankAccountsTab';
import DocumentsTab from '@/pages/funding/DocumentsTab';

const TABS = [
  { id: 'deposit',       Icon: Send,       Comp: DepositTab,      label: 'tab.deposit' },
  { id: 'transfers',     Icon: Wallet,     Comp: TransfersTab,    label: 'tab.transfers' },
  { id: 'history',       Icon: History,    Comp: HistoryTab,      label: 'tab.history' },
  { id: 'bank_accounts', Icon: Building2,  Comp: BankAccountsTab, label: 'tab.bank_accounts' },
  { id: 'documents',     Icon: Files,      Comp: DocumentsTab,    label: 'tab.documents' },
];

export default function InvestorFunding() {
  const { lang } = useFundingLang();
  const t = useFundingT(lang);
  const [active, setActive] = useState('deposit');

  const TabComp = TABS.find((x) => x.id === active)?.Comp || DepositTab;

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="investor-funding">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Lumen</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">{t('page.title')}</h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{t('page.subtitle')}</p>
        </div>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-border mb-6" data-testid="funding-tabs">
        {TABS.map((tab) => {
          const isActive = active === tab.id;
          const Icon = tab.Icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActive(tab.id)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
              data-testid={`funding-tab-${tab.id}`}
            >
              <Icon className="w-4 h-4" />
              {t(tab.label)}
            </button>
          );
        })}
      </nav>

      <TabComp t={t} />
    </div>
  );
}
