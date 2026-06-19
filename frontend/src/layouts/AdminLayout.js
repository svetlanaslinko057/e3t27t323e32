import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';
import { ConnectionStatusBadge } from '@/components/ConnectionStatus';
import NotificationBell from '@/components/NotificationBell';
import StaffNotificationBell from '@/components/StaffNotificationBell';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import Logo from '@/components/Logo';
import MobileNav from '@/components/MobileNav';
import SidebarGroup from '@/components/SidebarGroup';
import {
  LayoutDashboard,
  Users,
  ShieldCheck,
  Building2,
  CircleDollarSign,
  CreditCard,
  FileText,
  FileSignature,
  Inbox,
  BarChart3,
  Settings,
  LogOut,
  MessageCircleQuestion,
  Landmark,
  BookOpen,
  ArrowUpFromLine,
  Coins,
  Gauge,
  HeartPulse,
  ScrollText,
  Banknote,
  FileDown,
  Repeat,
  ArrowLeft,
  Activity,
  BookOpenCheck,
  Boxes,
  Award,
  Workflow,
  Users2,
  Layers3,
  UserCheck,
  Scale,
  Vote,
  Share2,
  Briefcase,
  Rocket,
  Wallet,
  Cog,
  Target,
  Globe,
  Radio,
  MessagesSquare,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';

/**
 * Lumen Admin Panel — investment fund operations console.
 * Sidebar is grouped into collapsible sections, ordered by daily relevance.
 * All labels are bilingual (Українська / English) via the `bi()` helper.
 */
const AdminLayout = () => {
  const { user, logout } = useAuth();
  const { bi } = useLang();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <div className="h-screen overflow-hidden bg-app text-token-primary flex" data-testid="admin-layout">
      <MobileNav role="admin" />
      <aside
        className="app-sidebar w-[244px] flex flex-col sticky top-0 h-screen bg-app-surface app-safe-top"
        style={{ borderRight: '1px solid var(--token-border)' }}
      >
        <div className="px-4 pt-6 pb-4">
          <div className="flex items-center">
            <Logo height={32} className="max-w-full" />
          </div>
          <p className="text-[11px] text-token-muted mt-3 leading-relaxed">{bi('Панель фонду', 'Fund console')}</p>
          <div className="mt-2 flex items-center gap-2">
            <ConnectionStatusBadge />
            <NotificationBell />
            <StaffNotificationBell />
          </div>
          <Link to="/" data-testid="back-to-site" className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-token-muted hover:text-token-primary transition">
            <ArrowLeft className="w-3.5 h-3.5" /> {bi('На сайт', 'Back to site')}
          </Link>
        </div>

        <nav className="flex-1 p-3 space-y-0 overflow-y-auto" data-testid="admin-sidebar-nav">
          {/* 1. Launch — Beta + Readiness (top of mind) */}
          <SidebarGroup
            id="admin_launch"
            label={bi('Операції', 'Operations')}
            icon={Activity}
            defaultOpen
            matchPaths={['/admin/command-center', '/admin/launch-readiness', '/admin/institutional-overview', '/admin/system-health']}
            testid="admin-group-launch"
          >
            <NavItem to="/admin/command-center" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('Командний центр', 'Operations Center')} testid="nav-command-center" />
            <NavItem to="/admin/launch-readiness" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label={bi('Готовність системи', 'System Readiness')} testid="nav-launch-readiness" />
            <NavItem to="/admin/institutional-overview" icon={<Briefcase className="w-[18px] h-[18px]" />} label={bi('Огляд для голови', 'Chairman Overview')} testid="nav-chairman" />
            <NavItem to="/admin/system-health" icon={<HeartPulse className="w-[18px] h-[18px]" />} label={bi('Стан системи', 'System Health')} testid="nav-system-health" />
          </SidebarGroup>

          {/* 2. Overview — Operational dashboards */}
          <SidebarGroup
            id="admin_overview"
            label={bi('Огляд', 'Overview')}
            icon={LayoutDashboard}
            defaultOpen
            matchPaths={['/admin/dashboard', '/admin/operations', '/admin/fund', '/admin/audit-log', '/admin/audit-explorer']}
            testid="admin-group-overview"
          >
            <NavItem to="/admin/dashboard" icon={<LayoutDashboard className="w-[18px] h-[18px]" />} label={bi('Огляд', 'Overview')} testid="nav-dashboard" />
            <NavItem to="/admin/operations" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('Центр операцій', 'Operations Center')} testid="nav-operations" />
            <NavItem to="/admin/fund" icon={<Gauge className="w-[18px] h-[18px]" />} label={bi('Аналітика фонду', 'Fund Analytics')} testid="nav-fund" />
            <NavItem to="/admin/audit-explorer" icon={<ScrollText className="w-[18px] h-[18px]" />} label={bi('Аудит-експлорер', 'Audit Explorer')} testid="nav-audit-explorer" />
            <NavItem to="/admin/audit-log" icon={<ScrollText className="w-[18px] h-[18px]" />} label={bi('Журнал аудиту', 'Audit Log')} testid="nav-audit-log" />
          </SidebarGroup>

          {/* 3. Investors — People, KYC, Compliance */}
          <SidebarGroup
            id="admin_people"
            label={bi('Інвестори', 'Investors')}
            icon={Users}
            matchPaths={['/admin/investors', '/admin/intents', '/admin/kyc', '/admin/accreditation', '/admin/compliance', '/admin/compliance-screening', '/admin/ubo', '/admin/investor-segments', '/admin/funnel', '/admin/site-activity']}
            testid="admin-group-people"
          >
            <NavItem to="/admin/investors" icon={<Users className="w-[18px] h-[18px]" />} label={bi('Інвестори', 'Investors')} testid="nav-investors" />
            <NavItem to="/admin/funnel" icon={<BarChart3 className="w-[18px] h-[18px]" />} label={bi('Воронка інвестора', 'Investor Funnel')} testid="nav-funnel" />
            <NavItem to="/admin/site-activity" icon={<Radio className="w-[18px] h-[18px]" />} label={bi('Активність сайту', 'Site Activity')} testid="nav-site-activity" />
            <NavItem to="/admin/investor-relations" icon={<Target className="w-[18px] h-[18px]" />} label={bi("Зв'язки з інвесторами", 'Investor Relations')} testid="nav-investor-relations" />
            <NavItem to="/manager/dashboard" icon={<Briefcase className="w-[18px] h-[18px]" />} label={bi('Кабінет менеджера', 'Manager Cabinet')} testid="nav-manager-cabinet" />
            <NavItem to="/admin/manager-ops" icon={<Users2 className="w-[18px] h-[18px]" />} label={bi('Manager OS · Контроль', 'Manager OS · Control')} testid="nav-manager-ops" />
            <NavItem to="/admin/intents" icon={<Inbox className="w-[18px] h-[18px]" />} label={bi('Заявки', 'Intents')} testid="nav-intents" />
            <NavItem to="/admin/kyc" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label="KYC" testid="nav-kyc" />
            <NavItem to="/admin/accreditation" icon={<Award className="w-[18px] h-[18px]" />} label={bi('Акредитація', 'Accreditation')} testid="nav-accreditation" />
            <NavItem to="/admin/compliance" icon={<Scale className="w-[18px] h-[18px]" />} label={bi('Комплаєнс', 'Compliance')} testid="nav-compliance" />
            <NavItem to="/admin/compliance-screening" icon={<ShieldAlert className="w-[18px] h-[18px]" />} label={bi('Санкції · PEP · AML', 'Sanctions · PEP · AML')} testid="nav-compliance-screening" />
            <NavItem to="/admin/ubo" icon={<UserCheck className="w-[18px] h-[18px]" />} label="UBO" testid="nav-ubo" />
            <NavItem to="/admin/investor-segments" icon={<Layers3 className="w-[18px] h-[18px]" />} label={bi('Сегменти', 'Segments')} testid="nav-investor-segments" />
          </SidebarGroup>

          {/* 4. Assets — Assets / Certificates / Rounds */}
          <SidebarGroup
            id="admin_assets"
            label={bi('Активи', 'Assets')}
            icon={Building2}
            matchPaths={['/admin/assets', '/admin/registry', '/admin/certificates', '/admin/rounds', '/admin/operators', '/admin/pipeline', '/admin/pipeline-analytics', '/admin/questions', '/admin/pools']}
            testid="admin-group-assets"
          >
            <NavItem to="/admin/pools" icon={<Layers3 className="w-[18px] h-[18px]" />} label={bi('Інвестиційні пули', 'Capital Pools')} testid="nav-pools" />
            <NavItem to="/admin/assets" icon={<Building2 className="w-[18px] h-[18px]" />} label={bi('Активи', 'Assets')} testid="nav-assets" />
            <NavItem to="/admin/registry" icon={<Boxes className="w-[18px] h-[18px]" />} label={bi('Реєстр одиниць', 'Unit Registry')} testid="nav-registry" />
            <NavItem to="/admin/certificates" icon={<Award className="w-[18px] h-[18px]" />} label={bi('Сертифікати', 'Certificates')} testid="nav-certificates" />
            <NavItem to="/admin/rounds" icon={<CircleDollarSign className="w-[18px] h-[18px]" />} label={bi('Раунди', 'Rounds')} testid="nav-rounds" />
            <NavItem to="/admin/operators" icon={<Users2 className="w-[18px] h-[18px]" />} label={bi('Оператори', 'Operators')} testid="nav-operators" />
            <NavItem to="/admin/pipeline" icon={<Workflow className="w-[18px] h-[18px]" />} label={bi('Воронка угод', 'Deal Pipeline')} testid="nav-pipeline" />
            <NavItem to="/admin/pipeline-analytics" icon={<BarChart3 className="w-[18px] h-[18px]" />} label={bi('Аналітика воронки', 'Pipeline Analytics')} testid="nav-pipeline-analytics" />
            <NavItem to="/admin/questions" icon={<MessageCircleQuestion className="w-[18px] h-[18px]" />} label={bi('Питання (Q&A)', 'Questions (Q&A)')} testid="nav-questions" />
          </SidebarGroup>

          {/* 5. Finance — Money rails / Treasury / Payouts */}
          <SidebarGroup
            id="admin_finance"
            label={bi('Фінанси', 'Finance')}
            icon={Wallet}
            matchPaths={['/admin/treasury', '/admin/rails', '/admin/bank-reconciliation', '/admin/bank-transactions', '/admin/funding-accounts', '/admin/payments', '/admin/withdrawals', '/admin/payouts', '/admin/finance-engine', '/admin/payout-export', '/admin/ledger']}
            testid="admin-group-finance"
          >
            <NavItem to="/admin/treasury" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('Казначейство', 'Treasury')} testid="nav-treasury" />
            <NavItem to="/admin/rails" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('Фандинг-операції', 'Funding Operations')} testid="nav-funding-ops" />
            <NavItem to="/admin/bank-reconciliation" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label="SEPA / SWIFT" testid="nav-bank-reconciliation" />
            <NavItem to="/admin/bank-transactions" icon={<Banknote className="w-[18px] h-[18px]" />} label={bi('Банк-транзакції', 'Bank Transactions')} testid="nav-bank-transactions" />
            <NavItem to="/admin/funding-accounts" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('Реквізити', 'Funding Accounts')} testid="nav-funding-accounts" />
            <NavItem to="/admin/payments" icon={<CreditCard className="w-[18px] h-[18px]" />} label={bi('Платежі', 'Payments')} testid="nav-payments" />
            <NavItem to="/admin/withdrawals" icon={<ArrowUpFromLine className="w-[18px] h-[18px]" />} label={bi('Виводи', 'Withdrawals')} testid="nav-withdrawals" />
            <NavItem to="/admin/payouts" icon={<Coins className="w-[18px] h-[18px]" />} label={bi('Виплати доходу', 'Income Payouts')} testid="nav-payouts" />
            <NavItem to="/admin/finance-engine" icon={<TrendingUp className="w-[18px] h-[18px]" />} label={bi('Курси · Податки · Дивіденди', 'FX · Tax · Dividends')} testid="nav-finance-engine" />
            <NavItem to="/admin/payout-export" icon={<FileDown className="w-[18px] h-[18px]" />} label={bi('Експорт виплат', 'Payout Export')} testid="nav-payout-export" />
            <NavItem to="/admin/ledger" icon={<BookOpen className="w-[18px] h-[18px]" />} label={bi('Реєстр проводок', 'Ledger')} testid="nav-ledger" />
          </SidebarGroup>

          {/* 6. Market — Secondary market & Liquidity */}
          <SidebarGroup
            id="admin_markets"
            label={bi('Ринок', 'Market')}
            icon={Repeat}
            matchPaths={['/admin/secondary-market', '/admin/web3', '/admin/market-makers', '/admin/contracts']}
            testid="admin-group-markets"
          >
            <NavItem to="/admin/secondary-market" icon={<Repeat className="w-[18px] h-[18px]" />} label={bi('Вторинний ринок', 'Secondary Market')} testid="nav-secondary-market" />
            <NavItem to="/admin/web3" icon={<Coins className="w-[18px] h-[18px]" />} label={bi('Crypto OS · Web3', 'Crypto OS · Web3')} testid="nav-crypto-os" />
            <NavItem to="/admin/market-makers" icon={<Gauge className="w-[18px] h-[18px]" />} label={bi('Ліквідність', 'Liquidity')} testid="nav-market-makers" />
            <NavItem to="/admin/contracts" icon={<FileSignature className="w-[18px] h-[18px]" />} label={bi('Договори', 'Contracts')} testid="nav-contracts" />
          </SidebarGroup>

          {/* 7. Institutional — Funds / Governance / Reports */}
          <SidebarGroup
            id="admin_inst"
            label={bi('Інституційне', 'Institutional')}
            icon={Landmark}
            matchPaths={['/admin/funds', '/admin/syndicates', '/admin/governance', '/admin/trust-graph', '/admin/fund-lpgp', '/admin/report-builder', '/admin/reports', '/admin/documents']}
            testid="admin-group-institutional"
          >
            <NavItem to="/admin/funds" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('Фонди', 'Funds')} testid="nav-inst-funds" />
            <NavItem to="/admin/syndicates" icon={<Users2 className="w-[18px] h-[18px]" />} label={bi('Синдикати', 'Syndicates')} testid="nav-inst-syndicates" />
            <NavItem to="/admin/governance" icon={<Vote className="w-[18px] h-[18px]" />} label={bi('Корпоративне управління', 'Governance')} testid="nav-inst-governance" />
            <NavItem to="/admin/trust-graph" icon={<Share2 className="w-[18px] h-[18px]" />} label={bi('Граф довіри', 'Trust Graph')} testid="nav-inst-trust-graph" />
            <NavItem to="/admin/fund-lpgp" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('LP/GP та Waterfall', 'LP/GP & Waterfall')} testid="nav-inst-lpgp" />
            <NavItem to="/admin/report-builder" icon={<FileText className="w-[18px] h-[18px]" />} label={bi('Конструктор звітів', 'Report Builder')} testid="nav-inst-reports" />
            <NavItem to="/admin/reports" icon={<BarChart3 className="w-[18px] h-[18px]" />} label={bi('Звіти', 'Reports')} testid="nav-reports" />
            <NavItem to="/admin/documents" icon={<FileText className="w-[18px] h-[18px]" />} label={bi('Документи', 'Documents')} testid="nav-documents" />
          </SidebarGroup>

          {/* 8. System — Settings / SOP */}
          <SidebarGroup
            id="admin_system"
            label={bi('Система', 'System')}
            icon={Cog}
            matchPaths={['/admin/sop', '/admin/settings', '/admin/staff-security', '/admin/comm-channels', '/admin/seo-settings']}
            testid="admin-group-system"
          >
            <NavItem to="/admin/sop" icon={<BookOpenCheck className="w-[18px] h-[18px]" />} label={bi('Регламенти (SOP)', 'Procedures (SOP)')} testid="nav-sop" />
            <NavItem to="/admin/staff-security" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label={bi('Безпека персоналу', 'Staff Security')} testid="nav-staff-security" />
            <NavItem to="/admin/comm-channels" icon={<MessagesSquare className="w-[18px] h-[18px]" />} label={bi('Канали зв’язку', 'Communication Channels')} testid="nav-comm-channels" />
            <NavItem to="/admin/manager-instructions" icon={<BookOpen className="w-[18px] h-[18px]" />} label={bi('Інструкції менеджера', 'Manager Instructions')} testid="nav-manager-instructions" />
            <NavItem to="/admin/seo-settings" icon={<Globe className="w-[18px] h-[18px]" />} label={bi('SEO · Sitemap / Robots', 'SEO · Sitemap / Robots')} testid="nav-seo-settings" />
            <NavItem to="/admin/settings" icon={<Settings className="w-[18px] h-[18px]" />} label={bi('Налаштування', 'Settings')} testid="nav-settings" />
          </SidebarGroup>
        </nav>

        <div className="p-3" style={{ borderTop: '1px solid var(--token-border)' }}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-token-muted font-semibold">{bi('Мова', 'Language')}</span>
            <LanguageSwitcher />
          </div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-token-muted font-semibold">{bi('Тема', 'Theme')}</span>
            <ThemeToggle />
          </div>
          <div
            className="flex items-center gap-3 p-3 rounded-xl"
            style={{ background: 'var(--token-surface-elevated)', border: '1px solid var(--token-border)' }}
          >
            <div
              className="w-9 h-9 rounded-lg flex items-center justify-center font-semibold text-sm"
              style={{
                background: 'var(--token-success-tint)',
                color: 'var(--token-primary)',
                border: '1px solid var(--token-success-border)',
              }}
            >
              {user?.name?.[0]?.toUpperCase() || 'A'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate text-token-primary">{user?.name || bi('Адмін', 'Admin')}</p>
              <p className="text-[11px] text-token-muted capitalize">{user?.role || 'admin'}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 rounded-lg transition-colors text-token-muted hover:text-token-primary"
              style={{ background: 'transparent' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--token-border)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              data-testid="admin-logout-btn"
              title={bi('Вийти', 'Sign out')}
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="app-main flex-1 min-h-0 overflow-y-auto bg-app">
        <Outlet />
      </main>
    </div>
  );
};

const NavItem = ({ to, icon, label, badge, testid }) => (
  <NavLink
    to={to}
    data-testid={testid}
    className={({ isActive }) =>
      `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
        isActive ? 'nav-item-active' : 'nav-item-idle'
      }`
    }
  >
    {icon}
    <span className="flex-1">{label}</span>
    {badge && <span className="status-badge badge-danger">{badge}</span>}
  </NavLink>
);

export default AdminLayout;
