import { useLang } from '@/contexts/LanguageContext';

/**
 * LanguageSwitcher — compact UK / EN segmented control.
 * Uses semantic design tokens so it sits cleanly in any cabinet chrome.
 *
 * variant:
 *   • "pill"    — bordered segmented control (sidebars / toolbars)
 *   • "ghost"   — minimal text toggle (public header)
 */
const LanguageSwitcher = ({ variant = 'pill', className = '' }) => {
  const { lang, setLang } = useLang();
  const options = [
    { id: 'uk', label: 'УКР' },
    { id: 'en', label: 'ENG' },
  ];

  if (variant === 'ghost') {
    return (
      <div className={`inline-flex items-center gap-1 text-[12px] font-medium ${className}`} data-testid="language-switcher">
        {options.map((o, i) => (
          <span key={o.id} className="inline-flex items-center">
            {i > 0 && <span className="mx-1 opacity-40">/</span>}
            <button
              type="button"
              onClick={() => setLang(o.id)}
              data-testid={`lang-${o.id}`}
              className={`transition-colors ${lang === o.id ? 'opacity-100 font-semibold' : 'opacity-55 hover:opacity-90'}`}
            >
              {o.label}
            </button>
          </span>
        ))}
      </div>
    );
  }

  return (
    <div
      className={`inline-flex items-center rounded-lg p-0.5 ${className}`}
      style={{ background: 'var(--token-surface-elevated)', border: '1px solid var(--token-border)' }}
      data-testid="language-switcher"
    >
      {options.map((o) => {
        const active = lang === o.id;
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => setLang(o.id)}
            data-testid={`lang-${o.id}`}
            className="px-2.5 py-1 rounded-md text-[11px] font-semibold tracking-wide transition-all"
            style={{
              background: active ? 'var(--token-success-tint)' : 'transparent',
              color: active ? 'var(--token-primary)' : 'var(--token-muted)',
              border: active ? '1px solid var(--token-success-border)' : '1px solid transparent',
            }}
            aria-pressed={active}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
};

export default LanguageSwitcher;
