import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Globe, ChevronDown, CheckCircle2 } from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import PublicWalletButton from '@/components/otc/PublicWalletButton';
import WalletConnectButton from '@/components/WalletConnectButton';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';
import PublicMenuOverlay from '@/components/public/PublicMenuOverlay';

/* Language switcher — restored original logic (UA / EN). */
function LangSwitch() {
  const { lang, setLang, bi } = useLang();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const OPTS = [
    { code: 'uk', short: 'UA', label: 'Українська' },
    { code: 'en', short: 'EN', label: 'English' },
  ];
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="lumen-lang-btn"
        data-testid="lang-switch"
        aria-label={bi('Змінити мову', 'Change language')}
      >
        <Globe className="w-4 h-4" />
        <span className="text-xs font-semibold uppercase tracking-wide">{lang === 'uk' ? 'UA' : 'EN'}</span>
        <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.25, 0.1, 0.25, 1] }}
            className="lumen-lang-menu"
            data-testid="lang-menu"
          >
            {OPTS.map((o) => (
              <button
                key={o.code}
                type="button"
                onClick={() => { setLang(o.code); setOpen(false); }}
                className={`lumen-lang-item ${lang === o.code ? 'is-active' : ''}`}
                data-testid={`lang-${o.code}`}
              >
                <span className="font-semibold">{o.short}</span>
                <span className="text-muted-foreground">{o.label}</span>
                {lang === o.code && <CheckCircle2 className="w-3.5 h-3.5 ml-auto text-[#2E5D4F]" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Unified public site header used by ALL public pages via PublicLayout.
 * Left: MENU emblem trigger (opens overlay). Center: logo.
 * Right (original logic): language · wallet · theme · auth.
 */
export const PublicHeader = () => {
  const { user } = useAuth();
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
          {/* LEFT — branded MENU emblem trigger */}
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

          {/* RIGHT — language · wallet · theme · auth (original logic) */}
          <div className="flex items-center gap-1.5 sm:gap-2">
            <LangSwitch />
            {isInvestor
              ? <div className="hidden md:block"><WalletConnectButton compact /></div>
              : <div className="hidden md:block"><PublicWalletButton compact /></div>}
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
