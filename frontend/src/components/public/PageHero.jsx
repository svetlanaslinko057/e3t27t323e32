import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, ChevronRight } from 'lucide-react';

/**
 * Shared dark hero for every public sub-page.
 * breadcrumb (ГОЛОВНА • X) + oversized display title + lead + optional CTAs.
 */
export const PageHero = ({
  breadcrumb = [],
  title,
  highlight,
  lead,
  primary,
  secondary,
  watermark = 'LUMEN',
  children,
}) => {
  const reduce = useReducedMotion();
  const ease = [0.16, 1, 0.3, 1];
  return (
    <section className="lpub-hero" data-testid="page-hero">
      <span className="lpub-hero__watermark" aria-hidden>{watermark}</span>
      <div className="lpub-hero__grain" aria-hidden />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative">
        {breadcrumb.length > 0 && (
          <motion.nav
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease }}
            className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-white/55"
            data-testid="page-hero-breadcrumb"
          >
            {breadcrumb.map((b, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {b.to ? (
                  <Link to={b.to} className="hover:text-white transition-colors">{b.label}</Link>
                ) : (
                  <span className="text-white/85">{b.label}</span>
                )}
                {i < breadcrumb.length - 1 && <ChevronRight className="h-3 w-3 text-white/30" />}
              </span>
            ))}
          </motion.nav>
        )}

        <motion.h1
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.06, ease }}
          className="lpub-hero__title"
          data-testid="page-hero-title"
        >
          {title}{highlight && <><br /><span className="lumen-gradient-text">{highlight}</span></>}
        </motion.h1>

        {lead && (
          <motion.p
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.16, ease }}
            className="mt-6 max-w-2xl text-base md:text-lg leading-relaxed text-white/75"
          >
            {lead}
          </motion.p>
        )}

        {(primary || secondary) && (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.26, ease }}
            className="mt-9 flex flex-wrap items-center gap-3"
          >
            {primary && (
              <Link to={primary.to} className="lpub-btn-gold" data-testid="page-hero-primary-cta">
                {primary.label} <ArrowRight className="h-4 w-4" />
              </Link>
            )}
            {secondary && (
              <Link to={secondary.to} className="lpub-btn-ghost-light" data-testid="page-hero-secondary-cta">
                {secondary.label}
              </Link>
            )}
          </motion.div>
        )}

        {children}
      </div>
    </section>
  );
};

export default PageHero;
