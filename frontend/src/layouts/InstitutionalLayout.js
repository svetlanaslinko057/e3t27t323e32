import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import ThemeToggle from '@/components/ThemeToggle';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import { useLang } from '@/contexts/LanguageContext';
import Logo from '@/components/Logo';
import { LayoutDashboard, Landmark, Users2, Scale, UserCheck, Share2, LogOut, ArrowLeft, Building2, Vote, Banknote } from 'lucide-react';

const InstitutionalLayout = () => {
  const { user, logout } = useAuth();
  const { bi } = useLang();
  const navigate = useNavigate();
  const handleLogout = async () => { await logout(); navigate('/'); };

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground flex" data-testid="institutional-layout">
      <aside className="w-[244px] border-r border-border flex flex-col sticky top-0 h-screen bg-card">
        <div className="px-4 pt-6 pb-4">
          <Link to="/"><Logo height={32} className="max-w-full" /></Link>
          <p className="text-[11px] text-muted-foreground mt-3">Інституційний кабінет</p>
          <Link to="/investor/dashboard" data-testid="back-to-investor" className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground transition">
            <ArrowLeft className="w-3.5 h-3.5" /> Кабінет інвестора
          </Link>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto" data-testid="institutional-sidebar">
          <NavItem to="/institutional/dashboard" icon={<LayoutDashboard className="w-[18px] h-[18px]" />} label="Огляд" testid="nav-inst-dashboard" />
          <NavItem to="/institutional/funds" icon={<Landmark className="w-[18px] h-[18px]" />} label="Фонди" testid="nav-inst-funds" />
          <NavItem to="/institutional/syndicates" icon={<Users2 className="w-[18px] h-[18px]" />} label="Синдикати" testid="nav-inst-syndicates" />
          <NavItem to="/institutional/structure" icon={<Share2 className="w-[18px] h-[18px]" />} label="Структура власності" testid="nav-inst-structure" />
          <NavItem to="/institutional/governance" icon={<Vote className="w-[18px] h-[18px]" />} label="Governance" testid="nav-inst-governance" />
          <NavItem to="/institutional/compliance" icon={<Scale className="w-[18px] h-[18px]" />} label="Комплаєнс" testid="nav-inst-compliance" />
          <NavItem to="/institutional/ubo" icon={<UserCheck className="w-[18px] h-[18px]" />} label="Бенефіціари (UBO)" testid="nav-inst-ubo" />
          <NavItem to="/investor/rails" icon={<Banknote className="w-[18px] h-[18px]" />} label="SEPA / SWIFT" testid="nav-inst-rails" />
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
            <div className="w-9 h-9 rounded-lg bg-[#2E5D4F]/10 flex items-center justify-center text-[#2E5D4F] border border-border"><Building2 className="w-4 h-4" /></div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name || 'Інвестор'}</p>
              <p className="text-[11px] text-muted-foreground truncate">{user?.email}</p>
            </div>
            <button onClick={handleLogout} className="p-2 hover:bg-muted rounded-lg text-muted-foreground hover:text-foreground" data-testid="inst-logout-btn"><LogOut className="w-4 h-4" /></button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-h-0 overflow-y-auto bg-background"><Outlet /></main>
    </div>
  );
};

const NavItem = ({ to, icon, label, testid }) => (
  <NavLink to={to} data-testid={testid} className={({ isActive }) =>
    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
      isActive ? 'bg-[#2E5D4F]/10 text-foreground border border-[#2E5D4F]/30' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
    }`}>{icon}<span className="flex-1">{label}</span></NavLink>
);

export default InstitutionalLayout;
