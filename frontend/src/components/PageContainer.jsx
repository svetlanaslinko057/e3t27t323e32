/**
 * PageContainer — canonical wrapper for every cabinet page.
 *
 * Enforces the Lumen content inset:
 *   mobile  (<768px)    : 16px sides, 24px top/bottom
 *   tablet  (768-1279px): 24px sides, 28px top/bottom
 *   desktop (≥1280px)   : 50px sides, 36px top/bottom
 *
 * Use it as the outermost element on every page (admin / investor / operator).
 * It also constrains the max width on ultra-wide displays so content keeps a
 * pleasant reading rhythm.
 *
 *   <PageContainer>
 *     <PageHeader title="..." />
 *     ...
 *   </PageContainer>
 *
 * The container is intentionally CSS-only and works even if a page is wrapped
 * inside `main.app-main` (its zero-padding override removes double inset).
 */
import * as React from 'react';

const cn = (...c) => c.filter(Boolean).join(' ');

export default function PageContainer({
  children,
  className,
  maxWidth = '1440px',
  testid,
  fullBleed = false,
}) {
  if (fullBleed) {
    return (
      <div data-testid={testid} className={cn('w-full', className)}>
        {children}
      </div>
    );
  }
  return (
    <div
      data-testid={testid}
      className={cn(
        'lumen-page',
        // horizontal: 16 / 24 / 50
        'px-4 md:px-6 xl:px-[50px]',
        // vertical: 24 / 28 / 36
        'py-6 md:py-7 xl:py-9',
        // max width (centered on huge screens)
        'mx-auto w-full',
        className,
      )}
      style={{ maxWidth }}
    >
      {children}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions, className }) {
  return (
    <header
      className={cn(
        'flex items-end justify-between gap-4 flex-wrap mb-6 md:mb-8',
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground font-semibold">
            {eyebrow}
          </p>
        )}
        {title && (
          <h1 className="mt-2 text-2xl md:text-[28px] font-bold tracking-tight text-foreground">
            {title}
          </h1>
        )}
        {description && (
          <p className="mt-1.5 text-sm text-muted-foreground max-w-2xl">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
