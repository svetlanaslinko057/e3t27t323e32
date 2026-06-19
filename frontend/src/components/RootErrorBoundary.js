/**
 * WEB-P5 — RootErrorBoundary
 *
 * Catches uncaught render errors anywhere in the React tree below.
 * Surfaces a theme-aware error UI and logs the error to console.
 *
 * Wrapped beneath LanguageProvider so it can render localised copy.
 * Wrapped beneath AuthProvider so auth context is available.
 * Wrapped beneath ToastProvider so the boundary can also surface a toast.
 */
import { Component } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { LanguageContext } from '@/contexts/LanguageContext';

const STR = {
  en: {
    title: 'Something went wrong',
    body: 'The page crashed unexpectedly. The error has been logged.',
    retry: 'Reload page',
  },
  uk: {
    title: 'Щось пішло не так',
    body: 'Сторінка несподівано аварійно завершилася. Помилку зафіксовано.',
    retry: 'Перезавантажити сторінку',
  },
};

class RootErrorBoundary extends Component {
  static contextType = LanguageContext;

  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[web-p5] uncaught render error', { error, info });
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('runtime:render_error', {
          detail: { message: error?.message || String(error), stack: error?.stack || '' },
        })
      );
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const lang = (this.context && this.context.lang) || 'en';
    const s = STR[lang] || STR.en;

    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--token-bg, #FAFAF7)',
          color: 'var(--token-text-primary, #1A1A1A)',
          padding: 24,
        }}
        data-testid="root-error-boundary"
      >
        <div
          style={{
            maxWidth: 440,
            width: '100%',
            padding: 32,
            borderRadius: 20,
            border: '1px solid var(--token-border, rgba(0,0,0,0.08))',
            background: 'var(--token-surface, #FFFFFF)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 16 }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 16,
                background: 'var(--token-danger-tint, rgba(220, 38, 38, 0.08))',
                border: '1px solid var(--token-danger-border, rgba(220, 38, 38, 0.20))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AlertTriangle style={{ width: 26, height: 26, color: 'var(--token-danger, #DC2626)' }} />
            </div>
            <div>
              <h2
                style={{
                  fontSize: 20,
                  fontWeight: 600,
                  marginBottom: 6,
                  color: 'var(--token-text-primary, #1A1A1A)',
                }}
              >
                {s.title}
              </h2>
              <p style={{ fontSize: 14, color: 'var(--token-text-secondary, #4A4A4A)', lineHeight: 1.5 }}>
                {s.body}
              </p>
              {this.state.error?.message && (
                <p
                  style={{
                    marginTop: 12,
                    fontSize: 12,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    color: 'var(--token-text-tertiary, #6A6A6A)',
                    background: 'var(--token-surface-elevated, rgba(0,0,0,0.04))',
                    borderRadius: 8,
                    padding: '8px 10px',
                    wordBreak: 'break-word',
                    textAlign: 'left',
                  }}
                >
                  {this.state.error.message}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={this.handleRetry}
              style={{
                marginTop: 8,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 18px',
                borderRadius: 10,
                background: 'var(--token-primary, #2EBF6F)',
                color: '#FFFFFF',
                border: 'none',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'opacity 120ms ease',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.92'; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
              data-testid="root-error-retry"
            >
              <RotateCcw style={{ width: 16, height: 16 }} />
              {s.retry}
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default RootErrorBoundary;
