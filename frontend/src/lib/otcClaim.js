/**
 * OTC guest-purchase "claim ticket" persistence.
 *
 * When a visitor reserves an OTC lot as a guest, the backend returns a
 * `claim_token`. We stash it locally so that — after the visitor registers or
 * logs in — the app can automatically CLAIM the reservation and the bought lot
 * shows up in their cabinet (see `OtcClaimOnAuth` in App.js).
 */
const KEY = 'lumen_otc_claim';

export function saveClaim(token, listing) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      token,
      listing: listing ? {
        id: listing.id,
        title: listing.asset?.title || null,
        price_usd: listing.price_usd ?? null,
        cover_url: listing.asset?.cover_url || null,
      } : null,
      ts: Date.now(),
    }));
  } catch { /* noop */ }
}

export function getClaim() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}

export function clearClaim() {
  try { localStorage.removeItem(KEY); } catch { /* noop */ }
}
