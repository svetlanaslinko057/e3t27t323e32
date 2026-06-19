/**
 * Currency display — USD / USDT ONLY.
 * Internal backend amounts are stored in UAH base; the app NEVER shows UAH.
 * Mirrors the web rule: UAH_PER_USD = 41.
 */
export const UAH_PER_USD = 41;

export const usdFromUah = (uah?: number | null): number =>
  Math.round(((Number(uah) || 0) / UAH_PER_USD) * 100) / 100;

export const formatUSD = (uahAmount?: number | null, opts: { decimals?: number } = {}): string => {
  const usd = usdFromUah(uahAmount);
  const decimals = opts.decimals ?? 0;
  return (
    '$' +
    usd.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
  );
};

/** For values already in USD (not UAH base). */
export const usd = (value?: number | null, decimals = 0): string =>
  '$' + (Number(value) || 0).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export const formatPercent = (v?: number | null, decimals = 1): string =>
  `${(Number(v) || 0).toFixed(decimals)}%`;

export const formatDate = (iso?: string | null): string => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('uk-UA', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return '—';
  }
};
