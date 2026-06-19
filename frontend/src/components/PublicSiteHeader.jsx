import { Link } from 'react-router-dom';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import PublicWalletButton from '@/components/otc/PublicWalletButton';
import WalletConnectButton from '@/components/WalletConnectButton';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';

/**
 * Reusable public site header (used by the standalone OTC pages and any other
 * public route). Mirrors the landing header but works on every public page and
 * always exposes the wallet-connect control.
 */
export default function PublicSiteHeader({ active }) {
  const { user } = useAuth();
  const { bi } = useLang();
  const isInvestor = user && ['investor', 'client'].includes(user.role);
  const navCls = (k) => `transition ${active === k ? 'text-foreground font-semibold' : 'hover:text-foreground'}`;

  return (
    <header className="sticky top-0 z-30 backdrop-blur-xl bg-background/85 border-b border-border" data-testid="public-site-header">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center" data-testid="public-header-logo"><Logo height={32} /></Link>
        <nav className="hidden lg:flex items-center gap-7 text-sm text-muted-foreground">
          <Link to="/#assets" className={navCls('assets')}>{bi('Активи', 'Assets')}</Link>
          <Link to="/#how" className={navCls('how')}>{bi('Як це працює', 'How it works')}</Link>
          <Link to="/otc" className={navCls('otc')} data-testid="nav-otc">{bi('OTC ринок', 'OTC market')}</Link>
          <Link to="/#protect" className={navCls('protect')}>{bi('Безпека', 'Security')}</Link>
          <Link to="/app" className={navCls('app')}>{bi('Додаток', 'App')}</Link>
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {isInvestor
            ? <div className="hidden md:block"><WalletConnectButton compact /></div>
            : <div className="hidden md:block"><PublicWalletButton compact /></div>}
          {user ? (
            <Link to={user.role === 'admin' ? '/admin/dashboard' : '/investor/dashboard'} className="lumen-btn-primary text-sm font-medium px-4 h-9" data-testid="public-header-cabinet">
              {bi('Мій кабінет', 'My cabinet')}
            </Link>
          ) : (
            <>
              <Link to="/auth" className="hidden sm:inline-flex text-sm font-medium text-muted-foreground hover:text-foreground transition px-3 h-9 items-center" data-testid="public-header-login">
                {bi('Увійти', 'Sign in')}
              </Link>
              <Link to="/auth?mode=register" className="lumen-btn-primary text-sm font-medium px-4 h-9" data-testid="public-header-register">
                {bi('Стати інвестором', 'Become investor')}
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
