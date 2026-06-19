import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import StaffNotificationBell from '@/components/StaffNotificationBell';
import Logo from '@/components/Logo';
import SidebarGroup from '@/components/SidebarGroup';
import {
  LayoutDashboard, Users, Workflow, Activity, LogOut, ArrowLeft, Target,
  Building2, FileText, HandCoins, Wallet, Users2, BarChart3, BookOpen,
} from 'lucide-react';

/**
 * ManagerLayout — unified Manager cabinet (manager + operator merged).
 * Two grouped surfaces:
 *   • Інвестори — Investor-Relations / Manager-OS (leads, pipeline, activity)
 *   • Об'єкти   — Operator OS (assets, reports, SLA, fees) — strictly scoped
 * Same chrome/tokens as Admin & Investor cabinets, bilingual (UK / EN).
 */
const ManagerLayout = () => {
  const { user, logout } = useAuth();
  const { bi } = useLang();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <div className="h-screen overflow-hidden bg-app text-token-primary flex" data-testid="manager-layout">
      <aside
        className="app-sidebar w-[244px] flex flex-col sticky top-0 h-screen bg-app-surface app-safe-top"
        style={{ borderRight: '1px solid var(--token-border)' }}
      >
        <div className="px-4 pt-6 pb-4">
          <div className="flex items-center">
            <Logo height={32} className="max-w-full" />
          </div>
          <p className="text-[11px] text-token-muted mt-3 leading-relaxed inline-flex items-center gap-1.5">
            <Target className="w-3.5 h-3.5" /> {bi('Кабінет менеджера', 'Manager cabinet')}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <StaffNotificationBell />
          </div>
          <Link to="/" data-testid="mgr-back-to-site" className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-token-muted hover:text-token-primary transition">
            <ArrowLeft className="w-3.5 h-3.5" /> {bi('На сайт', 'Back to site')}
          </Link>
        </div>

        <nav className="flex-1 p-3 space-y-0 overflow-y-auto" data-testid="manager-sidebar-nav">
          <SidebarGroup
            id="mgr_ir"
            label={bi('Інвестори', 'Investors')}
            icon={Users}
            defaultOpen
            matchPaths={['/manager/dashboard', '/manager/leads', '/manager/pipeline', '/manager/activity', '/manager/funnel', '/manager/instructions']}
            testid="mgr-group-ir"
          >
            <NavItem to="/manager/dashboard" icon={<LayoutDashboard className="w-[18px] h-[18px]" />} label={bi('Огляд', 'Overview')} testid="mgr-nav-dashboard" />
            <NavItem to="/manager/leads" icon={<Users className="w-[18px] h-[18px]" />} label={bi('Мої ліди', 'My Leads')} testid="mgr-nav-leads" />
            <NavItem to="/manager/pipeline" icon={<Workflow className="w-[18px] h-[18px]" />} label={bi('Воронка', 'Pipeline')} testid="mgr-nav-pipeline" />
            <NavItem to="/manager/activity" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('Моя ефективність', 'My Performance')} testid="mgr-nav-activity" />
            <NavItem to="/manager/funnel" icon={<BarChart3 className="w-[18px] h-[18px]" />} label={bi('Воронка інвестора', 'Investor Funnel')} testid="mgr-nav-funnel" />
            <NavItem to="/manager/instructions" icon={<BookOpen className="w-[18px] h-[18px]" />} label={bi('Інструкції', 'Instructions')} testid="mgr-nav-instructions" />
          </SidebarGroup>

          <SidebarGroup
            id="mgr_operator"
            label={bi("Об'єкти", 'Assets')}
            icon={Building2}
            defaultOpen
            matchPaths={['/manager/assets', '/manager/reports', '/manager/sla', '/manager/fees', '/manager/asset-investors']}
            testid="mgr-group-operator"
          >
            <NavItem to="/manager/assets" icon={<Building2 className="w-[18px] h-[18px]" />} label={bi("Мої об'єкти", 'My Assets')} testid="mgr-nav-assets" />
            <NavItem to="/manager/reports" icon={<FileText className="w-[18px] h-[18px]" />} label={bi('Звіти', 'Reports')} testid="mgr-nav-reports" />
            <NavItem to="/manager/sla" icon={<Activity className="w-[18px] h-[18px]" />} label={bi('SLA звітності', 'Reporting SLA')} testid="mgr-nav-sla" />
            <NavItem to="/manager/asset-investors" icon={<Users2 className="w-[18px] h-[18px]" />} label={bi('Інвестори об’єктів', 'Asset Investors')} testid="mgr-nav-asset-investors" />
            <NavItem to="/manager/fees" icon={<HandCoins className="w-[18px] h-[18px]" />} label={bi('Винагорода', 'Fees')} testid="mgr-nav-fees" />
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
              style={{ background: 'var(--token-success-tint)', color: 'var(--token-primary)', border: '1px solid var(--token-success-border)' }}
            >
              {user?.name?.[0]?.toUpperCase() || 'M'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate text-token-primary">{user?.name || bi('Менеджер', 'Manager')}</p>
              <p className="text-[11px] text-token-muted capitalize">{user?.role || 'manager'}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 rounded-lg transition-colors text-token-muted hover:text-token-primary"
              data-testid="manager-logout-btn"
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

const NavItem = ({ to, icon, label, testid }) => (
  <NavLink
    to={to}
    data-testid={testid}
    className={({ isActive }) =>
      `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${isActive ? 'nav-item-active' : 'nav-item-idle'}`
    }
  >
    {icon}
    <span className="flex-1">{label}</span>
  </NavLink>
);

export default ManagerLayout;
