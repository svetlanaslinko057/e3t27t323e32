/**
 * AnimatedHeading — premium reveal for heading text blocks.
 *
 * Splits the heading into words; each word slides in from bottom-left
 * with a subtle blur lift and staggered cascade. Triggers when the block
 * enters the viewport (IntersectionObserver), or immediately when
 * `immediate` is true (used for the hero block above the fold).
 *
 * Used by:
 *   - Landing hero  (h1, "Software, actually shipped.")
 *   - SectionHeader (h2, every section title across the landing page)
 *
 * Design intent (from product owner):
 *   "Глубокая анимация заглавных блоков. Появление слева-направо
 *    и снизу-вверх, по возрастающей. Только заглавный текст. Карточки
 *    не трогаем."
 */
import { useEffect, useRef, useState } from 'react';
import { useLang } from '@/contexts/LanguageContext';

const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)'; // soft quint ease-out
const WORD_STAGGER_MS = 90;
const WORD_DURATION_MS = 900;
const KICKER_LEAD_MS = 80;   // kicker comes in slightly before the title
const SUB_TRAIL_MS = 200;    // sub paragraph comes in after the last word

function splitWords(text) {
  // Preserve explicit <br/> by splitting on \n, then by spaces. We keep
  // the original whitespace by appending non-breaking spaces between
  // words so layout never collapses.
  return String(text)
    .split('\n')
    .map((line) => line.split(/\s+/).filter(Boolean));
}

export default function AnimatedHeading({
  kicker,
  title,
  sub,
  as = 'h2',
  immediate = false,
  titleStyle,
  kickerStyle,
  subStyle,
  testId,
}) {
  const { tByEn } = useLang();
  // Auto-translate any string props through the reverse EN→key index. JSX
  // (e.g., the hero's <Fragment> kicker with dot + label) passes through
  // unchanged since tByEn ignores non-strings.
  kicker = tByEn(kicker);
  title = tByEn(title);
  sub = tByEn(sub);
  const ref = useRef(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (immediate) {
      // Trigger AFTER first paint so the CSS transition has an initial
      // (hidden) frame to transition from. Two rAFs to dodge layout-flush
      // races on Safari.
      const id1 = requestAnimationFrame(() => {
        const id2 = requestAnimationFrame(() => setActive(true));
        // store for cleanup
        ref.current && (ref.current.__rAF2 = id2);
      });
      return () => {
        cancelAnimationFrame(id1);
        if (ref.current?.__rAF2) cancelAnimationFrame(ref.current.__rAF2);
      };
    }
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setActive(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setActive(true);
            io.disconnect();
          }
        });
      },
      { threshold: 0.18, rootMargin: '0px 0px -10% 0px' }
    );
    io.observe(node);
    return () => io.disconnect();
  }, [immediate]);

  const lines = splitWords(title || '');
  let wordIdx = 0;
  const totalWords = lines.reduce((n, l) => n + l.length, 0);
  const titleDoneAt = totalWords * WORD_STAGGER_MS + WORD_DURATION_MS;

  const HTag = as;

  return (
    <div ref={ref} data-testid={testId} style={{ position: 'relative' }}>
      {kicker && (
        <div
          style={{
            ...(kickerStyle || {}),
            opacity: active ? 1 : 0,
            transform: active ? 'translateY(0)' : 'translateY(12px)',
            transition: `opacity 600ms ${EASE} ${KICKER_LEAD_MS}ms, transform 600ms ${EASE} ${KICKER_LEAD_MS}ms`,
            willChange: 'opacity, transform',
          }}
        >
          {kicker}
        </div>
      )}

      <HTag
        style={{
          ...(titleStyle || {}),
          // Important: keep heading wrapping identical to non-animated
          // version. Words use inline-block so transforms work without
          // breaking line wraps.
        }}
      >
        {lines.map((words, lineIdx) => (
          <span key={`l-${lineIdx}`} style={{ display: 'block' }}>
            {words.map((w, i) => {
              const idx = wordIdx++;
              const delay = idx * WORD_STAGGER_MS;
              return (
                <span
                  key={`w-${lineIdx}-${i}`}
                  // Each word is its own animation cell; outer span clips
                  // the upward translate so the entry feels grounded
                  // (mask-like reveal) without needing overflow:hidden
                  // on the full heading (which would clip descenders).
                  style={{
                    display: 'inline-block',
                    overflow: 'hidden',
                    verticalAlign: 'bottom',
                    paddingBottom: '0.08em', // breathing room for g/y/p descenders
                  }}
                >
                  <span
                    style={{
                      display: 'inline-block',
                      opacity: active ? 1 : 0,
                      transform: active
                        ? 'translate3d(0,0,0)'
                        : 'translate3d(-18px, 48px, 0)',
                      filter: active ? 'blur(0px)' : 'blur(8px)',
                      transition: [
                        `opacity ${WORD_DURATION_MS}ms ${EASE} ${delay}ms`,
                        `transform ${WORD_DURATION_MS}ms ${EASE} ${delay}ms`,
                        `filter ${WORD_DURATION_MS}ms ${EASE} ${delay}ms`,
                      ].join(', '),
                      willChange: 'opacity, transform, filter',
                    }}
                  >
                    {w}
                  </span>
                  {/* Preserve the space that would have followed this word */}
                  {i < words.length - 1 && '\u00A0'}
                </span>
              );
            })}
          </span>
        ))}
      </HTag>

      {sub && (
        <p
          style={{
            ...(subStyle || {}),
            opacity: active ? 1 : 0,
            transform: active ? 'translateY(0)' : 'translateY(16px)',
            transition: `opacity 700ms ${EASE} ${titleDoneAt + SUB_TRAIL_MS}ms, transform 700ms ${EASE} ${titleDoneAt + SUB_TRAIL_MS}ms`,
            willChange: 'opacity, transform',
          }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}
