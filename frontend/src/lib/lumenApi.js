import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API = `${BACKEND_URL}/api`;

export const lumen = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 15000,
});

/**
 * PUBLIC CURRENCY RULE — the platform is USD-denominated.
 * Everything the user SEES is in USD ($) / USDT. The backend may still store
 * legacy amounts in UAH; we convert them to USD at the display layer using a
 * single canonical rate. There must be NO ₴ / грн / UAH anywhere in the UI.
 */
export const UAH_PER_USD = 41; // canonical display FX (НБУ-aligned). Change in one place only.

/** Convert a legacy UAH-denominated amount to USD for display. */
export const usdFromUah = (uahAmount) => Number(uahAmount || 0) / UAH_PER_USD;

/** Format a USD amount as $X,XXX (no decimals for whole-dollar display). */
export const formatUSD = (amount, { decimals = 0 } = {}) => {
  if (amount === null || amount === undefined || isNaN(amount)) return '—';
  const n = Number(amount);
  return '$' + n.toLocaleString('en-US', { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
};

/**
 * Legacy money formatter. Inputs are UAH-denominated amounts from the backend;
 * we now convert to USD and render in dollars. Kept under the old name so the
 * whole codebase switches to USD display through a single change.
 */
export const formatUAH = (amount) => {
  if (amount === null || amount === undefined || isNaN(amount)) return '—';
  return formatUSD(usdFromUah(amount));
};

/** Convenience: render an already-USD amount. Alias of formatUSD. */
export const formatMoney = formatUSD;

export const formatPercent = (n) => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return `${Number(n).toFixed(1).replace('.', ',')} %`;
};

export const formatDateUk = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('uk-UA', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch (_e) { return '—'; }
};

/**
 * Extract a human-readable message from a backend error.
 * The API wraps errors in an envelope: {ok, code, message, status, details}.
 * Falls back to FastAPI's raw `detail` and finally to the provided default.
 */
export const lumenError = (e, fallback = 'Сталася помилка') => {
  const data = e?.response?.data;
  if (!data) return fallback;
  if (typeof data.message === 'string' && data.message) return data.message;
  const d = data.detail;
  if (typeof d === 'string' && d) return d;
  if (d && typeof d.message === 'string') return d.message;
  return fallback;
};

/** Structured details payload from the error envelope (e.g. {missing: [...]}). */
export const lumenErrorDetails = (e) => {
  const data = e?.response?.data;
  if (!data) return null;
  if (data.details && typeof data.details === 'object') return data.details;
  if (data.detail && typeof data.detail === 'object') return data.detail;
  return null;
};
