/**
 * LUMEN — Mobile App landing section (id="mobile-app").
 * Injected into the marketing landing. Device stack with subtle parallax,
 * advantages preview, install CTAs + QR. Bilingual via bi().
 */
import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useScroll, useTransform, useReducedMotion } from 'framer-motion';
import { Smartphone, QrCode, ArrowRight, Check } from 'lucide-react';
import { useLang } from '@/contexts/LanguageContext';
import {
  DeviceFrame, ScreenDashboard, ScreenIncome, StoreBadges, AppQR, InstallDialog,
  Reveal, ADVANTAGES, GREEN, GOLD,
} from '@/components/marketing/AppShowcase';

const MobileAppSection = () => {
  const { bi } = useLang();
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const yBack = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [40, -40]);
  const yFront = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [-20, 20]);

  return (
    <section id="mobile-app" ref={ref} className="relative overflow-hidden border-t border-border" data-testid="mobile-app-section">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'linear-gradient(180deg, rgba(46,93,79,0.05) 0%, rgba(251,247,240,0) 55%)' }}
      />
      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:gap-8 lg:px-8 lg:py-28">
        {/* copy */}
        <div>
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-token-muted">
              <Smartphone className="h-3.5 w-3.5" style={{ color: GREEN }} /> {bi('Додаток · iOS та Android', 'App · iOS & Android')}
            </span>
          </Reveal>
          <Reveal delay={0.05}>
            <h2 className="lumen-h2 mt-5">
              {bi('Інвестуйте ', 'Invest ')}
              <span className="lumen-gradient-text">{bi('зі смартфона', 'from your phone')}</span>
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="lumen-section-sub mt-4 max-w-xl">
              {bi(
                'Весь LUMEN у кишені: обирайте активи, інвестуйте в USD/USDT, отримуйте дивіденди й торгуйте частками на OTC-ринку — будь-де та будь-коли.',
                'All of LUMEN in your pocket: pick assets, invest in USD/USDT, receive dividends and trade shares on the OTC market — anywhere, anytime.',
              )}
            </p>
          </Reveal>

          <Reveal delay={0.15}>
            <ul className="mt-6 grid gap-2.5 sm:grid-cols-2">
              {ADVANTAGES.slice(0, 4).map((a) => (
                <li key={a.uk} className="flex items-center gap-2 text-sm text-token-secondary">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full" style={{ background: 'rgba(46,93,79,0.1)' }}>
                    <Check className="h-3 w-3" style={{ color: GREEN }} />
                  </span>
                  {bi(a.uk, a.en)}
                </li>
              ))}
            </ul>
          </Reveal>

          <Reveal delay={0.2}>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <StoreBadges />
            </div>
          </Reveal>

          <Reveal delay={0.25}>
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Link to="/app" className="lumen-btn-primary-lg group" data-testid="mobile-app-section-cta">
                {bi('Дізнатися більше', 'Learn more')} <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <InstallDialog
                trigger={
                  <button className="lumen-btn-ghost-lg" data-testid="mobile-app-qr-open-dialog">
                    <QrCode className="h-4 w-4" /> {bi('Сканувати QR', 'Scan QR')}
                  </button>
                }
              />
              <div className="hidden items-center gap-3 rounded-2xl border border-border bg-card p-2.5 sm:flex">
                <AppQR size={64} />
                <span className="max-w-[120px] text-xs leading-snug text-token-muted">{bi('Наведіть камеру, щоб встановити', 'Point your camera to install')}</span>
              </div>
            </div>
          </Reveal>
        </div>

        {/* device stack */}
        <div className="relative flex min-h-[460px] items-center justify-center lg:justify-end">
          <motion.div style={{ y: yBack }} className="absolute right-6 top-4 hidden rotate-6 opacity-90 sm:block lg:right-16">
            <DeviceFrame width={232}><ScreenIncome /></DeviceFrame>
          </motion.div>
          <motion.div style={{ y: yFront }} className="relative -rotate-3">
            <DeviceFrame width={268}><ScreenDashboard /></DeviceFrame>
          </motion.div>
          <div className="pointer-events-none absolute -bottom-6 left-1/2 h-24 w-3/4 -translate-x-1/2 rounded-full" style={{ background: `radial-gradient(ellipse, ${GOLD}22, transparent 70%)` }} />
        </div>
      </div>
    </section>
  );
};

export default MobileAppSection;
