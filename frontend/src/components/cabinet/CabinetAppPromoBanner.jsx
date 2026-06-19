/**
 * LUMEN — in-cabinet "Get the app" promo banner (dismissible).
 * Shown at the top of the investor dashboard. Remembers dismissal in localStorage.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Smartphone, X, ArrowRight } from 'lucide-react';
import { useLang } from '@/contexts/LanguageContext';
import { AppQR, StoreBadges, GREEN } from '@/components/marketing/AppShowcase';

const KEY = 'lumen_app_banner_dismissed_v1';

const CabinetAppPromoBanner = () => {
  const { bi } = useLang();
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
  });
  if (hidden) return null;

  const dismiss = () => {
    try { localStorage.setItem(KEY, '1'); } catch { /* ignore */ }
    setHidden(true);
  };

  return (
    <div
      className="relative flex flex-col gap-4 overflow-hidden rounded-2xl border border-border bg-card p-4 md:flex-row md:items-center md:gap-5 md:p-5"
      data-testid="cabinet-app-promo-banner"
    >
      <div className="pointer-events-none absolute inset-0" style={{ background: 'linear-gradient(120deg, rgba(46,93,79,0.05), transparent 55%)' }} />
      <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" style={{ background: 'rgba(46,93,79,0.1)' }}>
        <Smartphone className="h-5 w-5" style={{ color: GREEN }} />
      </span>
      <div className="relative flex-1">
        <p className="text-sm font-semibold">{bi('Керуйте інвестиціями з додатку', 'Manage your investments from the app')}</p>
        <p className="mt-0.5 text-xs text-token-muted">{bi('Інвестуйте, отримуйте дивіденди та торгуйте на OTC — на iOS та Android.', 'Invest, receive dividends and trade on OTC — on iOS and Android.')}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <StoreBadges />
          <Link to="/app" className="inline-flex items-center gap-1 text-sm font-semibold transition-colors hover:opacity-80" style={{ color: GREEN }} data-testid="cabinet-app-promo-learn">
            {bi('Детальніше', 'Learn more')} <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
      <div className="relative hidden shrink-0 sm:block"><AppQR size={72} /></div>
      <button
        onClick={dismiss}
        className="absolute right-3 top-3 rounded-lg p-1.5 text-token-muted transition-colors hover:bg-muted hover:text-foreground"
        data-testid="cabinet-app-promo-dismiss-button"
        aria-label={bi('Закрити', 'Dismiss')}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
};

export default CabinetAppPromoBanner;
