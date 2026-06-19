/**
 * FooterExtras — single condensed footer row:
 *   [ social icons ]  ················  [ Terms · Privacy · Cookies · © 2026 ]
 *
 * No internal dividers — the caller wraps it in a single border-top to avoid
 * the "stacked lines" feel. Adapts to dark/light via `tone`.
 */
import { useState } from 'react';
import { useLegalSettings } from '@/contexts/LegalSettingsContext';
import LegalDocumentModal from '@/components/LegalDocumentModal';
import { useLang } from '@/contexts/LanguageContext';

const ICONS = {
  // 24×24 viewBox, drawn at 16×16. Same monoline rhythm as the rest of the site.
  telegram: 'M21.5 4.5 2.8 11.6c-.9.3-.9 1.5 0 1.8l4.7 1.5 1.8 5.7c.3.9 1.4 1.1 2 .4l2.6-3 4.9 3.6c.8.6 1.9.2 2.1-.8L23 5.7c.2-.9-.7-1.6-1.5-1.2z',
  tiktok:   'M14 4v8.5a3.5 3.5 0 1 1-3.5-3.5h.5V12a1 1 0 1 0 1 1V4h2.4c.2 1.7 1.5 3 3.1 3V9c-1 0-2-.3-2.5-1z',
  instagram:'M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm5 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm5.5-1.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
  youtube:  'M22 7.5c-.2-1.4-1-2.1-2.4-2.3C17.4 5 12 5 12 5s-5.4 0-7.6.2C3 5.4 2.2 6.1 2 7.5 1.8 9 1.8 12 1.8 12s0 3 .2 4.5c.2 1.4 1 2.1 2.4 2.3C6.6 19 12 19 12 19s5.4 0 7.6-.2c1.4-.2 2.2-.9 2.4-2.3.2-1.5.2-4.5.2-4.5s0-3-.2-4.5zM10 15V9l5 3-5 3z',
  facebook: 'M22 12a10 10 0 1 0-11.6 9.9v-7H8v-3h2.4V9.6c0-2.4 1.4-3.7 3.6-3.7 1 0 2 .2 2 .2v2.3H14.8c-1.2 0-1.6.7-1.6 1.5V12h2.7l-.4 3h-2.3v7A10 10 0 0 0 22 12z',
  github:   'M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-2c-2.8.6-3.4-1.2-3.4-1.2-.5-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.6 2.4 1.1 3 .9.1-.7.4-1.1.7-1.4-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 5 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.8v2.7c0 .3.2.6.7.5A10 10 0 0 0 12 2z',
};

const LABELS = {
  telegram: 'Telegram', tiktok: 'TikTok', instagram: 'Instagram',
  youtube: 'YouTube', facebook: 'Facebook', github: 'GitHub',
};

// Fixed, human-readable labels for footer pills. Admin can still edit the
// document title (used as modal heading) — footer always uses these constants
// to avoid showing seed-test garbage or overly long titles in the footer.
const LEGAL_LABELS = {
  terms:   'Terms of Use',
  privacy: 'Privacy Policy',
  cookies: 'Cookies Policy',
};

const STROKE_ICONS = new Set(['instagram', 'github']);

export default function FooterExtras({ tone = 'dark', mono }) {
  const { tByEn } = useLang();
  const { socials, legal } = useLegalSettings();
  const [openDoc, setOpenDoc] = useState(null); // 'terms' | 'privacy' | 'cookies'

  const isLight = tone === 'light';
  const txt = isLight ? '#475569' : '#94a3b8';
  const hoverTxt = isLight ? '#0f172a' : '#e2e8f0';
  const iconBg = isLight ? 'rgba(15,23,42,0.04)' : 'rgba(255,255,255,0.04)';
  const iconBd = isLight ? 'rgba(15,23,42,0.08)' : 'rgba(255,255,255,0.08)';

  const year = new Date().getFullYear();

  return (
    <>
      <div
        className="footer-extras"
        data-testid="footer-extras"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          padding: '18px 32px',
          fontFamily: mono,
          fontSize: 11.5,
          letterSpacing: '0.04em',
        }}
      >
        {/* Left: social icons */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }} data-testid="footer-socials">
          {socials.length === 0 ? (
            <span style={{ color: txt, fontSize: 11, opacity: 0.5 }}>—</span>
          ) : (
            socials.map((s) => {
              const isStroke = STROKE_ICONS.has(s.key);
              return (
                <a
                  key={s.key}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={LABELS[s.key] || s.key}
                  data-testid={`footer-social-${s.key}`}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 30, height: 30, borderRadius: 8,
                    background: iconBg, border: `1px solid ${iconBd}`,
                    color: txt, transition: 'color .15s, transform .15s, background .15s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = hoverTxt;
                    e.currentTarget.style.transform = 'translateY(-1px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = txt;
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <svg
                    width="16" height="16" viewBox="0 0 24 24"
                    fill={isStroke ? 'none' : 'currentColor'}
                    stroke={isStroke ? 'currentColor' : 'none'}
                    strokeWidth="1.6"
                    strokeLinecap="round" strokeLinejoin="round"
                  >
                    <path d={ICONS[s.key] || ICONS.telegram} />
                  </svg>
                </a>
              );
            })
          )}
        </div>

        {/* Right: legal links + copyright in the same row */}
        <div
          style={{
            display: 'flex', alignItems: 'center', flexWrap: 'wrap',
            columnGap: 20, rowGap: 8, color: txt,
            fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
            fontSize: 13, letterSpacing: 0,
          }}
          data-testid="footer-legal-links"
        >
          {legal.map((d) => (
            <button
              key={d.kind}
              type="button"
              onClick={() => setOpenDoc(d.kind)}
              data-testid={`footer-legal-${d.kind}`}
              style={{
                background: 'transparent', border: 0, padding: 0, cursor: 'pointer',
                color: txt, fontFamily: 'inherit', fontSize: 'inherit',
                letterSpacing: 'inherit', textTransform: 'none',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = hoverTxt; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = txt; }}
            >
              {LEGAL_LABELS[d.kind] || d.title}
            </button>
          ))}
          <span
            data-testid="footer-copyright"
            style={{ color: txt, opacity: 0.7, whiteSpace: 'nowrap' }}
          >
            © {year}
          </span>
        </div>
      </div>

      {openDoc ? (
        <LegalDocumentModal kind={openDoc} onClose={() => setOpenDoc(null)} tone={tone} />
      ) : null}
    </>
  );
}
