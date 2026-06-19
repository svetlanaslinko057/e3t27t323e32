/**
 * AdminRailsOps.js — H1.1 Funding Operations console (admin side).
 *
 * 4 sections: Queue / Reconciliation / Exceptions / Ledger.
 * Replaces the legacy /admin/rails redirect to /admin/bank-reconciliation.
 */
import { useState } from 'react';
import { Inbox, ShieldCheck, AlertTriangle, BookOpen } from 'lucide-react';
import { useFundingLang, useFundingT } from '@/i18n/funding';
import QueueSection from '@/pages/funding/admin/QueueSection';
import ReconciliationSection from '@/pages/funding/admin/ReconciliationSection';
import ExceptionsSection from '@/pages/funding/admin/ExceptionsSection';
import LedgerSection from '@/pages/funding/admin/LedgerSection';

const SECTIONS = [
  { id: 'queue',          Icon: Inbox,         Comp: QueueSection,          label: 'admin.section.queue' },
  { id: 'reconciliation', Icon: ShieldCheck,   Comp: ReconciliationSection, label: 'admin.section.reconciliation' },
  { id: 'exceptions',     Icon: AlertTriangle, Comp: ExceptionsSection,     label: 'admin.section.exceptions' },
  { id: 'ledger',         Icon: BookOpen,      Comp: LedgerSection,         label: 'admin.section.ledger' },
];

export default function AdminRailsOps() {
  const { lang } = useFundingLang();
  const t = useFundingT(lang);
  const [active, setActive] = useState('queue');

  const SecComp = SECTIONS.find((x) => x.id === active)?.Comp || QueueSection;

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto" data-testid="admin-rails-ops">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Lumen Admin</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">{t('admin.title')}</h1>
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{t('admin.subtitle')}</p>
        </div>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-border mb-6" data-testid="admin-funding-sections">
        {SECTIONS.map((sec) => {
          const isActive = active === sec.id;
          const Icon = sec.Icon;
          return (
            <button
              key={sec.id}
              type="button"
              onClick={() => setActive(sec.id)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
              data-testid={`admin-funding-section-${sec.id}`}
            >
              <Icon className="w-4 h-4" />
              {t(sec.label)}
            </button>
          );
        })}
      </nav>

      <SecComp t={t} />
    </div>
  );
}
