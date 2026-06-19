import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

/**
 * Editorial FAQ list — reference-style numbered rows ("1/", "2/" …) with a large
 * bold question, an animated "+" toggle (rotates to "×" when open) and thin
 * gradient divider lines. LUMEN palette (deep green text + gold accents on cream).
 *
 * Props:
 *   items: [{ q: string, a: string }]
 *   testId: optional container data-testid
 */
export default function FaqList({ items = [], testId = 'faq-list' }) {
  const [open, setOpen] = useState(-1);

  return (
    <div className="lpub-faq" data-testid={testId}>
      {items.map((item, i) => {
        const isOpen = open === i;
        const num = `${i + 1}/`;
        return (
          <div key={i} className={`lpub-faq__row ${isOpen ? 'is-open' : ''}`}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? -1 : i)}
              className="lpub-faq__q"
              aria-expanded={isOpen}
              data-testid={`faq-trigger-${i}`}
            >
              <span className="lpub-faq__num">{num}</span>
              <span className="lpub-faq__qtext">{item.q}</span>
              <span className={`lpub-faq__sign ${isOpen ? 'is-open' : ''}`} aria-hidden>
                <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
                  <path d="M13 5v16M5 13h16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </span>
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  key="content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.32, ease: [0.25, 0.1, 0.25, 1] }}
                  className="lpub-faq__a-wrap"
                  data-testid={`faq-content-${i}`}
                >
                  <p className="lpub-faq__a">{item.a}</p>
                </motion.div>
              )}
            </AnimatePresence>

            <span className="lpub-faq__line" aria-hidden />
          </div>
        );
      })}
    </div>
  );
}
