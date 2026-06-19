import { Link } from 'react-router-dom';
import Logo from '@/components/Logo';
import { useLang } from '@/contexts/LanguageContext';

export default function PublicSiteFooter() {
  const { bi } = useLang();
  return (
    <footer className="border-t border-border bg-card" data-testid="public-site-footer">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="flex items-center gap-3">
            <Logo height={28} />
            <span className="text-sm text-muted-foreground max-w-xs">
              {bi('Реальні активи. Прозорі інвестиції. Усі розрахунки — в USD / USDT.',
                  'Real assets. Transparent investments. All figures in USD / USDT.')}
            </span>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
            <Link to="/#assets" className="hover:text-foreground">{bi('Активи', 'Assets')}</Link>
            <Link to="/otc" className="hover:text-foreground">{bi('OTC ринок', 'OTC market')}</Link>
            <Link to="/#how" className="hover:text-foreground">{bi('Як це працює', 'How it works')}</Link>
            <Link to="/legal" className="hover:text-foreground">{bi('Документи', 'Legal')}</Link>
            <Link to="/app" className="hover:text-foreground">{bi('Додаток', 'App')}</Link>
          </nav>
        </div>
        <p className="mt-8 text-xs text-muted-foreground/70">© {new Date().getFullYear()} LUMEN. {bi('Усі права захищено.', 'All rights reserved.')}</p>
      </div>
    </footer>
  );
}
