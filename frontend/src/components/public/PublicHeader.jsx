import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Phone } from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import PublicWalletButton from '@/components/otc/PublicWalletButton';
import WalletConnectButton from '@/components/WalletConnectButton';
import { useAuth } from '@/App';
import { useContactModal } from '@/contexts/ContactModalContext';
import { LUMEN_CONTACTS } from '@/components/public/publicNav';
import PublicMenuOverlay from '@/components/public/PublicMenuOverlay';

/**
 * Unified public site header used by ALL public pages via PublicLayout.
 * Left: MENU trigger (opens overlay). Center: logo. Right: phone + CTA + auth.
 */
export const PublicHeader = () => {
  const { user } = useAuth();
  const { openContact } = useContactModal();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const isInvestor = user && ['investor', 'client'].includes(user.role);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <>
      <header className={`lpub-header ${scrolled ? 'is-scrolled' : ''}`} data-testid="public-header">
        <div className="relative mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* LEFT — original branded MENU emblem trigger */}
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="lumen-menu-emblem group"
            data-testid="public-menu-trigger"
            aria-label="Відкрити меню"
          >
            <span className="lumen-menu-emblem-mark" aria-hidden>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
                <path d="M12 2c.6 3.7 1.7 4.8 5.4 5.4-3.7.6-4.8 1.7-5.4 5.4-.6-3.7-1.7-4.8-5.4-5.4C10.3 6.8 11.4 5.7 12 2Z" fill="currentColor"/>
                <path d="M18 13.2c.35 2.1 1 2.75 3.1 3.1-2.1.35-2.75 1-3.1 3.1-.35-2.1-1-2.75-3.1-3.1 2.1-.35 2.75-1 3.1-3.1Z" fill="currentColor" opacity="0.7"/>
              </svg>
            </span>
            <span className="hidden sm:inline lumen-menu-emblem-label">Меню</span>
          </button>

          {/* CENTER — logo */}
          <Link to="/" className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center" data-testid="public-header-logo">
            <Logo height={30} />
          </Link>

          {/* RIGHT — phone + CTA + auth */}
          <div className="flex items-center gap-1.5 sm:gap-2">
            <a href={LUMEN_CONTACTS.phoneHref} className="lpub-header__phone" data-testid="public-header-phone">
              <Phone className="h-4 w-4" /><span className="hidden xl:inline">{LUMEN_CONTACTS.phone}</span>
            </a>
            <button
              type="button"
              onClick={() => openContact({ source: 'header', title: 'Замовити дзвінок' })}
              className="lpub-header__cta hidden md:inline-flex"
              data-testid="public-header-callback"
            >
              Замовити дзвінок
            </button>
            {isInvestor
              ? <div className="hidden lg:block"><WalletConnectButton compact /></div>
              : <div className="hidden lg:block"><PublicWalletButton compact /></div>}
            <ThemeToggle />
            {user ? (
              <Link to={user.role === 'admin' ? '/admin/dashboard' : '/investor/dashboard'} className="lumen-btn-primary h-9 px-4 text-sm font-medium" data-testid="public-header-cabinet">
                Кабінет
              </Link>
            ) : (
              <Link to="/auth" className="lumen-btn-primary h-9 px-4 sm:px-5 text-sm font-medium" data-testid="public-header-login">
                Увійти
              </Link>
            )}
          </div>
        </div>
      </header>

      <PublicMenuOverlay open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
};

export default PublicHeader;
