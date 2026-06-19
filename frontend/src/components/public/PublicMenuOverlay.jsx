import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { X, ArrowUpRight, Mail, Send, Phone } from 'lucide-react';
import { PUBLIC_NAV, LUMEN_CONTACTS } from '@/components/public/publicNav';
import { useContactModal } from '@/contexts/ContactModalContext';

/**
 * Full-screen overlay menu (left dark-green drawer, Far-Minerals / ECO style).
 * Every item routes to a dedicated page — no anchor scroll.
 */
export const PublicMenuOverlay = ({ open, onClose }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { openContact } = useContactModal();
  const reduce = useReducedMotion();

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const go = (to) => { onClose(); if (to !== location.pathname) navigate(to); };

  const listV = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.16 } } };
  const itemV = reduce
    ? { hidden: { opacity: 0 }, show: { opacity: 1 } }
    : { hidden: { opacity: 0, y: 22, filter: 'blur(5px)' }, show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] } } };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="lumen-menu-scrim"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            onClick={onClose}
            data-testid="public-menu-scrim"
          />
          <motion.aside
            className="lumen-menu-drawer"
            data-testid="public-menu-overlay"
            initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }}
            transition={{ duration: 0.52, ease: [0.76, 0, 0.24, 1] }}
          >
            <div className="lumen-menu-top">
              <button type="button" onClick={onClose} className="lumen-close-btn group" data-testid="public-menu-close">
                <span className="lumen-close-icon"><X className="w-4 h-4" /></span>
                <span className="lumen-close-word">Закрити</span>
              </button>
              <img
                src={`${process.env.PUBLIC_URL || ''}/branding/lumen-light.v4.png`}
                alt="LUMEN" draggable={false} style={{ height: 24, width: 'auto' }}
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
              />
            </div>

            <motion.p
              className="lumen-menu-eyebrow"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.22, duration: 0.5 }}
            >
              Навігація
            </motion.p>

            <motion.nav variants={listV} initial="hidden" animate="show" className="lumen-menu-nav">
              {PUBLIC_NAV.map((it, i) => {
                const active = it.to === '/' ? location.pathname === '/' : location.pathname.startsWith(it.to);
                return (
                  <motion.button
                    key={it.to}
                    variants={itemV}
                    type="button"
                    onClick={() => go(it.to)}
                    className={`lumen-menu-link group ${active ? 'is-active' : ''}`}
                    data-testid={`public-menu-link-${it.slug}`}
                  >
                    <span className="lumen-menu-num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="lumen-menu-link-text">
                      <span className="lumen-menu-link-title">{it.label}</span>
                      <span className="lumen-menu-link-cap">{it.meta}</span>
                    </span>
                    <ArrowUpRight className="lumen-menu-link-arrow" />
                  </motion.button>
                );
              })}
            </motion.nav>

            <motion.div
              initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.5 }} className="lumen-menu-footer"
            >
              <button
                type="button"
                onClick={() => { onClose(); openContact({ source: 'public_menu', title: 'Залишити заявку' }); }}
                className="lumen-pill-cta" data-testid="public-menu-cta"
              >
                <span className="lumen-pill-dot" /> Залишити заявку <span className="lumen-pill-dot" />
              </button>
              <div className="lumen-menu-contacts">
                <a href={LUMEN_CONTACTS.phoneHref} className="lumen-menu-contact"><Phone className="w-4 h-4" /> {LUMEN_CONTACTS.phone}</a>
                <a href={LUMEN_CONTACTS.emailHref} className="lumen-menu-contact"><Mail className="w-4 h-4" /> {LUMEN_CONTACTS.email}</a>
                <a href={LUMEN_CONTACTS.telegram} target="_blank" rel="noreferrer" className="lumen-menu-contact"><Send className="w-4 h-4" /> Telegram</a>
              </div>
              <p className="lumen-menu-tag">LUMEN · Реальні активи. Цифрова власність.</p>
            </motion.div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};

export default PublicMenuOverlay;
