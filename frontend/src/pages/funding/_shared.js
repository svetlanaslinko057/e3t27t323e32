/**
 * Shared utilities for Funding Center (Investor + Admin).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';

export const CANONICAL_STATUSES = [
  'draft', 'submitted', 'pending_review', 'matched', 'confirmed', 'rejected',
];

export const STATUS_TONE = {
  draft:           { bg: 'bg-zinc-100 dark:bg-zinc-800', fg: 'text-zinc-700 dark:text-zinc-200', dot: 'bg-zinc-400' },
  submitted:       { bg: 'bg-amber-50 dark:bg-amber-950/40', fg: 'text-amber-800 dark:text-amber-200', dot: 'bg-amber-500' },
  pending_review:  { bg: 'bg-sky-50 dark:bg-sky-950/40', fg: 'text-sky-800 dark:text-sky-200', dot: 'bg-sky-500' },
  matched:         { bg: 'bg-indigo-50 dark:bg-indigo-950/40', fg: 'text-indigo-800 dark:text-indigo-200', dot: 'bg-indigo-500' },
  confirmed:       { bg: 'bg-emerald-50 dark:bg-emerald-950/40', fg: 'text-emerald-800 dark:text-emerald-200', dot: 'bg-emerald-600' },
  rejected:        { bg: 'bg-rose-50 dark:bg-rose-950/40', fg: 'text-rose-800 dark:text-rose-200', dot: 'bg-rose-500' },
};

export function formatAmount(value, currency, locale = 'uk-UA') {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  try {
    return n.toLocaleString(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + (currency ? ` ${currency}` : '');
  } catch (_e) {
    return `${n.toFixed(2)}${currency ? ` ${currency}` : ''}`;
  }
}

export function formatDateTime(iso, locale = 'uk-UA') {
  if (!iso) return '—';
  try {
    const d = typeof iso === 'string' ? new Date(iso) : iso;
    return d.toLocaleString(locale, {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_e) {
    return String(iso);
  }
}

export function formatBytes(n) {
  if (!Number.isFinite(n)) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function formatIban(iban) {
  if (!iban) return '—';
  return String(iban).replace(/(.{4})/g, '$1 ').trim();
}

export function methodLabelFromTransfer(rail) {
  if (!rail) return '—';
  if (rail === 'sepa_instant' || rail === 'SEPA Instant') return 'SEPA Instant';
  return String(rail).toUpperCase();
}

/**
 * Status pill component.  Always reflects the canonical status.
 */
export function StatusPill({ status, t }) {
  const cs = String(status || 'submitted').toLowerCase();
  const tone = STATUS_TONE[cs] || STATUS_TONE.submitted;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${tone.bg} ${tone.fg}`}
      data-testid={`status-pill-${cs}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
      {t(`status.${cs}`)}
    </span>
  );
}

export function CopyButton({ value, t }) {
  const [copied, setCopied] = useState(false);
  const onClick = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(String(value || ''));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (_e) { /* noop */ }
  }, [value]);
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border border-border bg-card hover:bg-muted transition-colors"
      data-testid="funding-copy-btn"
    >
      {copied ? t('common.copied') : t('common.copy')}
    </button>
  );
}

/**
 * Loads all bank-accounts visible to the investor.
 */
export function useBankAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/lumen/institutional/rails/bank-accounts');
      setAccounts(r.data?.items || []);
      setErr('');
    } catch (e) {
      setErr(lumenError(e, 'Failed to load bank accounts'));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return { accounts, loading, err, reload: load };
}

/**
 * Loads transfers for the current investor.
 */
export function useMyTransfers() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/lumen/institutional/rails/transfers?limit=200');
      setItems(r.data?.items || []);
      setErr('');
    } catch (e) {
      setErr(lumenError(e, 'Failed to load transfers'));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return { items, loading, err, reload: load };
}
