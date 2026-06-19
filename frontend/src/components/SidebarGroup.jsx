/**
 * SidebarGroup — collapsible nav section used in all 3 cabinet layouts.
 * Auto-expands when any of its children matches the active route.
 * Persists expand state per-key in localStorage.
 */
import { useEffect, useState, useMemo, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';

const LS_PREFIX = 'lumen_sidebar_group_';

export default function SidebarGroup({
  id,
  label,
  icon: Icon,
  defaultOpen = false,
  matchPaths = [],
  children,
  testid,
}) {
  const location = useLocation();
  const isActiveSection = useMemo(() => (
    Array.isArray(matchPaths) && matchPaths.some((p) => location.pathname.startsWith(p))
  ), [location.pathname, matchPaths]);

  const lsKey = `${LS_PREFIX}${id}`;
  const initiallyOpen = useRef(null);
  if (initiallyOpen.current === null) {
    let saved = null;
    try {
      const raw = typeof window !== 'undefined' ? window.localStorage.getItem(lsKey) : null;
      if (raw === '1') saved = true;
      else if (raw === '0') saved = false;
    } catch (_e) { /* noop */ }
    initiallyOpen.current = saved !== null ? saved : (isActiveSection || defaultOpen);
  }

  const [open, setOpen] = useState(initiallyOpen.current);

  // If user navigates INTO this section, auto-open
  useEffect(() => {
    if (isActiveSection) setOpen(true);
  }, [isActiveSection]);

  useEffect(() => {
    try { window.localStorage.setItem(lsKey, open ? '1' : '0'); } catch (_e) { /* noop */ }
  }, [open, lsKey]);

  return (
    <div className="mb-1" data-testid={testid}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] uppercase tracking-wider font-bold transition-colors ${
          isActiveSection
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-token-muted hover:text-token-primary'
        }`}
        aria-expanded={open}
        data-testid={testid ? `${testid}-toggle` : undefined}
      >
        {Icon && <Icon className="w-3.5 h-3.5" />}
        <span className="flex-1 text-left">{label}</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      <div
        className={`overflow-hidden transition-[max-height,opacity] duration-200 ${
          open ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="space-y-0.5 py-1">{children}</div>
      </div>
    </div>
  );
}
