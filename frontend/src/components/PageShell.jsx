/**
 * PageShell — canonical page wrapper.
 *
 * Standardized header pattern + canonical Lumen padding (provided by
 * `main.app-main` at the layout level, see responsive.css §6).
 *
 * Usage:
 *
 *   <PageShell
 *     kicker="Lumen Admin · H1.3"
 *     title={<><Rocket className="w-6 h-6 text-amber-600" /> Controlled Beta · Command Center</>}
 *     subtitle="Єдина операційна панель запуску."
 *     actions={<button onClick={…}>Refresh</button>}
 *     testid="page-cc"
 *   >
 *     ...page content...
 *   </PageShell>
 *
 * Padding is intentionally NOT set here — the layout sets canonical insets.
 */
import React from 'react';

export default function PageShell({
  kicker,
  title,
  subtitle,
  actions,
  children,
  testid,
  className = '',
  headerClassName = '',
}) {
  return (
    <div className={`w-full ${className}`} data-testid={testid}>
      {(kicker || title || subtitle || actions) && (
        <header className={`mb-6 flex items-start justify-between flex-wrap gap-3 ${headerClassName}`}>
          <div className="min-w-0">
            {kicker && (
              <p className="text-xs uppercase tracking-widest text-muted-foreground">{kicker}</p>
            )}
            {title && (
              <h1 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-3">
                {title}
              </h1>
            )}
            {subtitle && (
              <p className="mt-2 text-sm text-muted-foreground max-w-3xl">{subtitle}</p>
            )}
          </div>
          {actions && (
            <div className="flex items-center gap-2 flex-wrap shrink-0">
              {actions}
            </div>
          )}
        </header>
      )}
      <div className="space-y-6">
        {children}
      </div>
    </div>
  );
}

/**
 * Section — visual group inside PageShell.
 */
export function Section({ title, kicker, icon: Icon, actions, children, className = '', testid }) {
  return (
    <section className={`space-y-3 ${className}`} data-testid={testid}>
      {(title || kicker || actions) && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            {kicker && (
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{kicker}</p>
            )}
            {title && (
              <h2 className="text-base font-semibold flex items-center gap-2">
                {Icon && <Icon className="w-4 h-4 text-amber-600 dark:text-amber-400" />}
                {title}
              </h2>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
