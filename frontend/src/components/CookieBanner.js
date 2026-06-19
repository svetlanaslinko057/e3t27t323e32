/**
 * CookieBanner — compact, friendly first-visit consent card.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  🍪  Cookies                                                [×]  │
 *   │  Small intro line + "Cookies Policy" link.                       │
 *   │  [ Customize ]            [ Reject ]   [ Accept all ]            │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 *   Bottom-right floating card (max 420px). Slides up on first visit.
 *   "Customize" expands to category toggles inline.
 *
 * Theme: light/dark via `tone` prop. Re-open via window event
 *   `cookie-banner:open`. Persists choice in `cookie_consent_v1`.
 */
import { useEffect, useState, useCallback } from 'react';
import { useLegalSettings } from '@/contexts/LegalSettingsContext';
import LegalDocumentModal from '@/components/LegalDocumentModal';
import { useLang } from '../contexts/LanguageContext';
import { api } from '@/lib/api';

const STORAGE_KEY = 'cookie_consent_v1';

function loadStoredChoice() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch { return null; }
}

function persistChoice(payload) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...payload, at: new Date().toISOString() }));
  } catch { /* ignore */ }
}

export default function CookieBanner({ tone = 'dark', inApp = false }) {
  const { tByEn } = useLang();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [cookiesOpen, setCookiesOpen] = useState(false);
  const [categories, setCategories] = useState({
    essential: true, // always on
    functional: true,
    analytics: false,
    marketing: false,
  });
  const { legal } = useLegalSettings();
  const hasCookiesDoc = legal.some((d) => d.kind === 'cookies');

  // Initial check + window event subscription for "re-open from Footer".
  useEffect(() => {
    if (!loadStoredChoice()) setOpen(true);
    const reopen = () => { setOpen(true); setExpanded(true); };
    window.addEventListener('cookie-banner:open', reopen);
    return () => window.removeEventListener('cookie-banner:open', reopen);
  }, []);

  const submit = useCallback(async (choice, extraCategories) => {
    const cats = extraCategories || Object.entries(categories)
      .filter(([k, v]) => k !== 'essential' && v)
      .map(([k]) => k);
    persistChoice({ choice, categories: cats });
    setOpen(false);
    setExpanded(false);
    try {
      await api.post('/cookie-consent', { choice, categories: cats });
    } catch { /* non-blocking */ }
  }, [categories]);

  if (!open) return null;

  const isLight = tone === 'light';
  // Tokens — solid, opaque tints + subtle borders.
  const bg         = isLight ? '#ffffff' : '#0f141d';
  const bd         = isLight ? '#e2e8f0' : 'rgba(255,255,255,0.10)';
  const tx         = isLight ? '#0f172a' : '#e2e8f0';
  const sub        = isLight ? '#64748b' : '#94a3b8';
  const primaryBg  = isLight ? '#0f172a' : '#f8fafc';
  const primaryTx  = isLight ? '#ffffff' : '#0b0f17';
  const ghostBd    = isLight ? '#cbd5e1' : 'rgba(255,255,255,0.18)';
  const ghostHover = isLight ? '#0f172a' : '#ffffff';
  const chipBg     = isLight ? 'rgba(15,23,42,0.04)' : 'rgba(255,255,255,0.04)';
  const shadow     = isLight
    ? '0 18px 40px rgba(15,23,42,0.16), 0 4px 10px rgba(15,23,42,0.06)'
    : '0 20px 50px rgba(0,0,0,0.55), 0 4px 10px rgba(0,0,0,0.30)';

  return (
    <>
      <div
        data-testid="cookie-banner"
        role="dialog"
        className={inApp ? 'cookie-banner--inapp' : ''}
        aria-label={tByEn('Cookie consent')}
        style={{
          position: 'fixed',
          left: 20,
          bottom: 20,
          right: 'auto',
          zIndex: 9998,
          width: 'min(420px, calc(100vw - 32px))',
          background: bg,
          color: tx,
          border: `1px solid ${bd}`,
          borderRadius: 14,
          boxShadow: shadow,
          padding: '16px 18px',
          fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
          animation: 'cookie-banner-enter .28s ease-out both',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>🍪</span>
          <strong style={{ fontSize: 14, letterSpacing: '0.01em', flex: 1 }}>
            {tByEn('Cookies')}
          </strong>
          <button
            type="button"
            onClick={() => submit('essential', [])}
            aria-label={tByEn('Dismiss with essential cookies only')}
            data-testid="cookie-banner-dismiss"
            style={{
              background: 'transparent', border: 0, padding: 4, cursor: 'pointer',
              color: sub, lineHeight: 1, borderRadius: 6,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = ghostHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = sub; }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Intro */}
        <div style={{ color: sub, fontSize: 12.5, lineHeight: 1.5 }}>
          {tByEn('We use cookies to keep you signed in and improve the product. Essentials are always on.')}
          {hasCookiesDoc ? (
            <>
              {' '}
              <button
                type="button"
                onClick={() => setCookiesOpen(true)}
                data-testid="cookie-banner-policy-link"
                style={{
                  background: 'transparent', border: 0, padding: 0, color: tx,
                  textDecoration: 'underline', cursor: 'pointer', font: 'inherit',
                }}
              >
                {tByEn('Cookies Policy')}
              </button>
            </>
          ) : null}
        </div>

        {/* Actions */}
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 8, marginTop: 14,
            justifyContent: 'space-between', flexWrap: 'wrap',
          }}
        >
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            data-testid="cookie-banner-customize"
            style={{
              background: 'transparent', color: sub, border: 0, padding: '6px 0',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', textDecoration: 'underline',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = ghostHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = sub; }}
          >
            {expanded ? tByEn('Hide options') : tByEn('Customize')}
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              onClick={() => submit('rejected', [])}
              data-testid="cookie-banner-essential"
              style={{
                background: 'transparent', color: tx, border: `1px solid ${ghostBd}`,
                borderRadius: 10, padding: '8px 12px', cursor: 'pointer',
                fontSize: 12.5, fontWeight: 600,
              }}
            >
              {tByEn('Reject')}
            </button>
            <button
              type="button"
              onClick={() => submit('all', ['functional', 'analytics', 'marketing'])}
              data-testid="cookie-banner-accept-all"
              style={{
                background: primaryBg, color: primaryTx, border: '1px solid transparent',
                borderRadius: 10, padding: '8px 16px', cursor: 'pointer',
                fontSize: 12.5, fontWeight: 700,
              }}
            >
              {tByEn('Accept all')}
            </button>
          </div>
        </div>

        {/* Expanded categories */}
        {expanded ? (
          <div
            data-testid="cookie-banner-expanded"
            style={{
              marginTop: 14, paddingTop: 14, borderTop: `1px solid ${bd}`,
              display: 'grid', gridTemplateColumns: '1fr', gap: 8,
            }}
          >
            {[
              { key: 'essential',  label: tByEn('Essential'),  desc: tByEn('Authentication & security.'),          locked: true },
              { key: 'functional', label: tByEn('Functional'), desc: tByEn('Remember theme & language.') },
              { key: 'analytics',  label: tByEn('Analytics'),  desc: tByEn('Anonymous product improvement.') },
              { key: 'marketing',  label: tByEn('Marketing'),  desc: tByEn('Personalised offers.') },
            ].map((c) => {
              const checked = !!categories[c.key] || c.locked;
              return (
                <label
                  key={c.key}
                  data-testid={`cookie-banner-cat-${c.key}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    cursor: c.locked ? 'default' : 'pointer',
                    padding: '8px 10px', border: `1px solid ${bd}`, borderRadius: 10,
                    background: chipBg, opacity: c.locked ? 0.85 : 1,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={c.locked}
                    onChange={(e) => setCategories((prev) => ({ ...prev, [c.key]: e.target.checked }))}
                    style={{ accentColor: primaryBg, width: 14, height: 14 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700 }}>
                      {c.label}
                      {c.locked ? (
                        <span style={{ color: sub, fontWeight: 500, marginLeft: 6 }}>· {tByEn('always on')}</span>
                      ) : null}
                    </div>
                    <div style={{ color: sub, fontSize: 11.5, marginTop: 1 }}>{c.desc}</div>
                  </div>
                </label>
              );
            })}
            <button
              type="button"
              onClick={() => submit('custom')}
              data-testid="cookie-banner-save"
              style={{
                marginTop: 4,
                background: primaryBg, color: primaryTx, border: '1px solid transparent',
                borderRadius: 10, padding: '9px 16px', cursor: 'pointer',
                fontSize: 12.5, fontWeight: 700,
              }}
            >
              {tByEn('Save my choice')}
            </button>
          </div>
        ) : null}
      </div>

      <style>{`
        @keyframes cookie-banner-enter {
          from { opacity: 0; transform: translateY(12px) scale(.985); }
          to   { opacity: 1; transform: translateY(0)   scale(1); }
        }
        /* Inside investor/admin cabinets the bottom-left of the viewport is
           occupied by the sidebar logout/profile control. On desktop (sidebar
           visible) push the banner past the sidebar so it never overlaps it. */
        @media (min-width: 768px) {
          [data-testid="cookie-banner"].cookie-banner--inapp {
            left: 324px !important;
            width: min(400px, calc(100vw - 360px)) !important;
          }
        }
        @media (max-width: 520px) {
          [data-testid="cookie-banner"] { right: 12px !important; left: 12px !important; width: auto !important; }
        }
      `}</style>

      {cookiesOpen ? (
        <LegalDocumentModal kind="cookies" onClose={() => setCookiesOpen(false)} tone={tone} />
      ) : null}
    </>
  );
}
