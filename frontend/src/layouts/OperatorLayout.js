import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { useEffect, useState } from 'react';
import { lumen } from '@/lib/lumenApi';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useLang } from '@/contexts/LanguageContext';
import Logo from '@/components/Logo';
import SidebarGroup from '@/components/SidebarGroup';
import { VerifiedBadge } from '@/lib/operatorUi';
import { LayoutDashboard, Building2, FileText, Users, HandCoins, Activity, LogOut, ArrowLeft, ShieldCheck, Wallet } from 'lucide-react';

const OperatorLayout = () => {
  const { user, logout } = useAuth();
  const { bi } = useLang();
  const navigate = useNavigate();
  const [me, setMe] = useState(null);

  useEffect(() => {
    let alive = true;
    lumen.get('/operator/me').then((r) => { if (alive) setMe(r.data); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const handleLogout = async () => { await logout(); navigate('/'); };

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground flex" data-testid="operator-layout">
      <aside className="w-[244px] border-r border-border flex flex-col sticky top-0 h-screen bg-card">
        <div className="px-4 pt-6 pb-4">
          <div className="flex items-center"><Logo height={32} className="max-w-full" /></div>
          <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">Кабінет оператора</p>
          {me && (
            <div className="mt-2">
              <VerifiedBadge verified={me.verified} status={me.status} statusLabel={me.status_label} />
            </div>
          )}
          <Link to="/" data-testid="back-to-site" className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground transition">
            <ArrowLeft className="w-3.5 h-3.5" /> На сайт
          </Link>
        </div>

        <nav className="flex-1 p-3 space-y-0 overflow-y-auto" data-testid="operator-sidebar-nav">
          <SidebarGroup id="op_overview" label="Огляд" icon={LayoutDashboard} defaultOpen
            matchPaths={['/operator/dashboard']} testid="op-group-overview">
            <NavItem to="/operator/dashboard" icon={<LayoutDashboard className="w-[18px] h-[18px]" />} label="Огляд" testid="nav-op-dashboard" />
          </SidebarGroup>
          <SidebarGroup id="op_work" label="Робота" icon={Building2} defaultOpen
            matchPaths={['/operator/assets', '/operator/reports', '/operator/sla', '/operator/investors']} testid="op-group-work">
            <NavItem to="/operator/assets" icon={<Building2 className="w-[18px] h-[18px]" />} label="Мої об'єкти" testid="nav-op-assets" />
            <NavItem to="/operator/reports" icon={<FileText className="w-[18px] h-[18px]" />} label="Звіти" testid="nav-op-reports" />
            <NavItem to="/operator/sla" icon={<Activity className="w-[18px] h-[18px]" />} label="SLA звітності" testid="nav-op-sla" />
            <NavItem to="/operator/investors" icon={<Users className="w-[18px] h-[18px]" />} label="Інвестори" testid="nav-op-investors" />
          </SidebarGroup>
          <SidebarGroup id="op_finance" label="Фінанси" icon={Wallet}
            matchPaths={['/operator/fees']} testid="op-group-finance">
            <NavItem to="/operator/fees" icon={<HandCoins className="w-[18px] h-[18px]" />} label="Винагорода" testid="nav-op-fees" />
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
            <div className="w-9 h-9 rounded-lg bg-[#2E5D4F]/10 flex items-center justify-center font-semibold text-sm border border-border text-[#2E5D4F]">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{me?.name || user?.name || 'Оператор'}</p>
              <p className="text-[11px] text-muted-foreground truncate">{user?.email}</p>
            </div>
            <button onClick={handleLogout} className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-foreground" data-testid="operator-logout-btn" title="Вийти">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="app-main flex-1 min-h-0 overflow-y-auto bg-background">
        <Outlet />
      </main>
    </div>
  );
};

const NavItem = ({ to, icon, label, testid }) => (
  <NavLink to={to} data-testid={testid} className={({ isActive }) =>
    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
      isActive ? 'bg-[#2E5D4F]/10 text-foreground border border-[#2E5D4F]/30' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
    }`}>
    {icon}<span className="flex-1">{label}</span>
  </NavLink>
);

export default OperatorLayout;
