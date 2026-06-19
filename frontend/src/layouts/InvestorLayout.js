import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { ConnectionStatusBadge } from '@/components/ConnectionStatus';
import NotificationBell from '@/components/NotificationBell';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useLang } from '@/contexts/LanguageContext';
import Logo from '@/components/Logo';
import MobileNav from '@/components/MobileNav';
import SidebarGroup from '@/components/SidebarGroup';
import WalletConnectButton from '@/components/WalletConnectButton';
import { LayoutDashboard, Briefcase, Building2, Wallet, FileText, FileSignature, User, Bell, LogOut, PiggyBank, TrendingUp, PieChart, Repeat, ArrowLeft, Boxes, Award, Route as RouteIcon, Gauge, HandCoins, Trophy, Landmark, ShieldCheck, Activity, Coins, Layers } from 'lucide-react';

const InvestorLayout = () => {
  const { user, logout } = useAuth();
  const { bi } = useLang();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground flex" data-testid="investor-layout">
      <MobileNav role="investor" />
      <aside className="app-sidebar w-[244px] border-r border-border flex flex-col sticky top-0 h-screen bg-card app-safe-top">
        <div className="px-4 pt-6 pb-4">
          <div className="flex items-center">
            <Logo height={32} className="max-w-full" />
          </div>
          <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
            {bi('Кабінет інвестора', 'Investor Cabinet')}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <ConnectionStatusBadge />
            <NotificationBell />
          </div>
          <Link to="/" data-testid="back-to-site" className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground transition">
            <ArrowLeft className="w-3.5 h-3.5" /> На сайт
          </Link>
        </div>

        <nav className="flex-1 p-3 space-y-0 overflow-y-auto" data-testid="investor-sidebar-nav">
          {/* Overview — single entry */}
          <NavItem to="/investor/dashboard" icon={<LayoutDashboard className="w-[18px] h-[18px]" />} label={bi('Огляд', 'Overview')} testid="nav-dashboard" />

          {/* 1. My Investments */}
          <SidebarGroup
            id="inv_investments"
            label={bi('Мої інвестиції', 'My Investments')}
            icon={Briefcase}
            defaultOpen
            matchPaths={['/investor/portfolio', '/investor/opportunities', '/investor/units', '/investor/analytics']}
            testid="inv-group-investments"
          >
            <NavItem to="/investor/portfolio" icon={<Briefcase className="w-[18px] h-[18px]" />} label={bi('Портфель', 'Portfolio')} testid="nav-portfolio" />
            <NavItem to="/investor/opportunities" icon={<Building2 className="w-[18px] h-[18px]" />} label={bi('Активи', 'Assets')} testid="nav-opportunities" />
            <NavItem to="/investor/units" icon={<Boxes className="w-[18px] h-[18px]" />} label={bi('Мої частки', 'My Shares')} testid="nav-units" />
            <NavItem to="/investor/analytics" icon={<PieChart className="w-[18px] h-[18px]" />} label={bi('Аналітика', 'Analytics')} testid="nav-analytics" />
          </SidebarGroup>

          {/* 2. Income */}
          <SidebarGroup
            id="inv_income"
            label={bi('Дохід', 'Income')}
            icon={TrendingUp}
            defaultOpen
            matchPaths={['/investor/income', '/investor/payments']}
            testid="inv-group-income"
          >
            <NavItem to="/investor/income" icon={<TrendingUp className="w-[18px] h-[18px]" />} label={bi('Дохід та дивіденди', 'Income & Dividends')} testid="nav-income" />
            <NavItem to="/investor/payments" icon={<Coins className="w-[18px] h-[18px]" />} label={bi('Виплати', 'Payouts')} testid="nav-payments" />
          </SidebarGroup>

          {/* 3. Market */}
          <SidebarGroup
            id="inv_market"
            label={bi('Ринок', 'Market')}
            icon={Repeat}
            defaultOpen
            matchPaths={['/investor/otc', '/investor/marketplace', '/investor/my-assets']}
            testid="inv-group-market"
          >
            <NavItem to="/investor/otc" icon={<Repeat className="w-[18px] h-[18px]" />} label={bi('Вторинний ринок', 'Secondary Market')} testid="nav-otc-market" />
            <NavItem to="/investor/my-assets" icon={<Boxes className="w-[18px] h-[18px]" />} label={bi('Мої лоти на продаж', 'My Listings')} testid="nav-my-assets" />
          </SidebarGroup>

          {/* 4. Wallet */}
          <SidebarGroup
            id="inv_wallet"
            label={bi('Гаманець', 'Wallet')}
            icon={Wallet}
            matchPaths={['/investor/wallet', '/investor/funding', '/investor/crypto']}
            testid="inv-group-wallet"
          >
            <NavItem to="/investor/wallet" icon={<PiggyBank className="w-[18px] h-[18px]" />} label={bi('Баланс', 'Balance')} testid="nav-wallet" />
            <NavItem to="/investor/funding" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('Поповнення', 'Add Funds')} testid="nav-funding" />
            <NavItem to="/investor/crypto" icon={<Coins className="w-[18px] h-[18px]" />} label={bi('Web3-гаманець', 'Web3 Wallet')} testid="nav-crypto-center" />
          </SidebarGroup>

          {/* 5. Documents */}
          <SidebarGroup
            id="inv_docs"
            label={bi('Документи', 'Documents')}
            icon={FileText}
            matchPaths={['/investor/documents', '/investor/certificates', '/investor/contracts', '/investor/reports']}
            testid="inv-group-docs"
          >
            <NavItem to="/investor/certificates" icon={<Award className="w-[18px] h-[18px]" />} label={bi('Сертифікати власності', 'Ownership Certificates')} testid="nav-certificates" />
            <NavItem to="/investor/contracts" icon={<FileSignature className="w-[18px] h-[18px]" />} label={bi('Договори', 'Contracts')} testid="nav-contracts" />
            <NavItem to="/investor/documents" icon={<FileText className="w-[18px] h-[18px]" />} label={bi('Документи', 'Documents')} testid="nav-documents" />
            <NavItem to="/investor/reports" icon={<FileText className="w-[18px] h-[18px]" />} label={bi('Звіти (PDF)', 'Reports (PDF)')} testid="nav-reports" />
          </SidebarGroup>

          {/* More — advanced / internal surfaces */}
          <SidebarGroup
            id="inv_more"
            label={bi('Ще', 'More')}
            icon={Layers}
            matchPaths={['/investor/pools', '/investor/commitments', '/investor/lp-funds', '/investor/liquidity', '/investor/journey', '/investor/timeline', '/institutional/dashboard', '/operators/leaderboard', '/investor/notifications', '/investor/notification-preferences']}
            testid="inv-group-more"
          >
            <NavItem to="/investor/pools" icon={<Layers className="w-[18px] h-[18px]" />} label={bi('Інвестиційні пули', 'Investment Pools')} testid="nav-pools" />
            <NavItem to="/investor/commitments" icon={<HandCoins className="w-[18px] h-[18px]" />} label={bi("Зобов'язання", 'Commitments')} testid="nav-commitments" />
            <NavItem to="/investor/lp-funds" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('LP кабінет (фонди)', 'LP (Funds)')} testid="nav-lp-funds" />
            <NavItem to="/investor/liquidity" icon={<Gauge className="w-[18px] h-[18px]" />} label={bi('Центр ліквідності', 'Liquidity')} testid="nav-liquidity" />
            <NavItem to="/investor/journey" icon={<RouteIcon className="w-[18px] h-[18px]" />} label={bi('Шлях інвестицій', 'Journey')} testid="nav-journey" />
            <NavItem to="/investor/timeline" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('Історія', 'Timeline')} testid="nav-timeline" />
            <NavItem to="/institutional/dashboard" icon={<Landmark className="w-[18px] h-[18px]" />} label={bi('Інституційний кабінет', 'Institutional')} testid="nav-institutional" />
            <NavItem to="/operators/leaderboard" icon={<Trophy className="w-[18px] h-[18px]" />} label={bi('Рейтинг операторів', 'Operators')} testid="nav-operators-leaderboard" />
            <NavItem to="/investor/notifications" icon={<Bell className="w-[18px] h-[18px]" />} label={bi('Сповіщення', 'Notifications')} testid="nav-notifications" />
            <NavItem to="/investor/notification-preferences" icon={<Bell className="w-[18px] h-[18px]" />} label={bi('Налаштування сповіщень', 'Notification Settings')} testid="nav-notif-prefs" />
          </SidebarGroup>

          {/* Profile */}
          <SidebarGroup
            id="inv_profile"
            label={bi('Профіль', 'Profile')}
            icon={User}
            matchPaths={['/investor/profile', '/investor/accreditation', '/investor/compliance']}
            testid="inv-group-profile"
          >
            <NavItem to="/investor/profile" icon={<User className="w-[18px] h-[18px]" />} label={bi('Профіль', 'Profile')} testid="nav-profile" />
            <NavItem to="/investor/accreditation" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label={bi('Акредитація', 'Accreditation')} testid="nav-accreditation" />
            <NavItem to="/investor/compliance" icon={<ShieldCheck className="w-[18px] h-[18px]" />} label={bi('Комплаєнс', 'Compliance')} testid="nav-compliance" />
          </SidebarGroup>
        </nav>

        <div className="p-3 border-t border-border">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">{bi('Мова', 'Language')}</span>
            <LanguageSwitcher />
          </div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">{bi('Тема', 'Theme')}</span>
            <ThemeToggle />
          </div>
          <div className="flex items-center gap-3 p-3 rounded-xl bg-muted border border-border">
            <div className="w-9 h-9 rounded-lg bg-signal/10 flex items-center justify-center font-semibold text-sm border border-border">
              {user?.name?.[0]?.toUpperCase() || 'I'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name || 'Інвестор'}</p>
              <p className="text-[11px] text-muted-foreground truncate">{user?.email}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground"
              data-testid="logout-btn"
              title="Вийти"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="app-main flex-1 min-h-0 overflow-y-auto bg-background">
        <div className="sticky top-0 z-30 hidden md:flex items-center justify-end gap-3 px-6 lg:px-10 h-14 border-b border-border bg-background/85 backdrop-blur-md" data-testid="investor-topbar">
          <span className="mr-auto text-[12px] text-muted-foreground hidden lg:block">{bi('Web3-гаманець, цифрова власність та OTC ринок — завжди під рукою', 'Web3 wallet, digital ownership & OTC market — always at hand')}</span>
          <WalletConnectButton />
        </div>
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
        isActive
          ? 'bg-signal/10 text-foreground border border-signal/30'
          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
      }`
    }
  >
    {icon}
    <span className="flex-1">{label}</span>
    {badge && <span className="px-2 py-0.5 text-xs bg-signal/15 text-signal rounded-full">{badge}</span>}
  </NavLink>
);

export default InvestorLayout;
