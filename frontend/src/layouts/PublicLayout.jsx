import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import PublicHeader from '@/components/public/PublicHeader';
import FooterMega from '@/components/public/FooterMega';
import '@/pages/LandingPage.css';
import '@/components/public/public.css';

/**
 * Shared shell for ALL public marketing pages.
 * Sticky header + overlay menu (in PublicHeader) + page content (Outlet) + giant footer.
 * Resets scroll to top on every route change.
 */
export default function PublicLayout() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="lpub-shell lumen-landing min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main className="lpub-main"><Outlet /></main>
      <FooterMega />
    </div>
  );
}
