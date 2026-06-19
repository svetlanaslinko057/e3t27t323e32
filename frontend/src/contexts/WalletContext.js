import { createContext, useContext, useCallback, useEffect, useState, useRef } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useAuth } from '@/App';

/**
 * Site-wide Web3 Wallet layer.
 *
 * One source of truth for the connected wallet across the WHOLE app (header
 * badge, profile, crypto center, OTC). Wraps the existing, proven backend:
 *   /investor/web3/wallet/challenge + /verify   (EIP-191 sign-to-link)
 *   /investor/web3/wallets                       (list)
 *   /investor/web3/wallet/primary                (set primary)
 *   /investor/web3/summary                       (counts for the badge)
 *
 * IMPORTANT product rule: the wallet is NOT a login. It is attached to an
 * already-authenticated account (Investor identity) — Investor → Wallets(1..N).
 */
const WalletContext = createContext(null);
export const useWallet = () => useContext(WalletContext) || {};

const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '');

function getInjected() {
  return typeof window !== 'undefined' ? window.ethereum : null;
}

export function WalletProvider({ children }) {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  // Only investor-type identities have a web3 surface. Admin/manager skip it.
  const eligible = !!user && ['investor', 'client'].includes(user.role);

  const refresh = useCallback(async () => {
    if (!eligible) { setSummary(null); setWallets([]); return; }
    try {
      const [s, w] = await Promise.all([
        lumen.get('/investor/web3/summary'),
        lumen.get('/investor/web3/wallets'),
      ]);
      setSummary(s.data);
      setWallets(w.data?.wallets || []);
    } catch (_e) { /* silent — chrome must never break on this */ }
  }, [eligible]);

  useEffect(() => { refresh(); }, [refresh]);

  // light polling so badge counts stay fresh after on-platform actions
  useEffect(() => {
    if (!eligible) return;
    pollRef.current = setInterval(refresh, 45000);
    return () => clearInterval(pollRef.current);
  }, [eligible, refresh]);

  const hasInjected = !!getInjected();

  const connect = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const eth = getInjected();
      if (!eth) { const e = new Error('NO_WALLET'); e.code = 'NO_WALLET'; throw e; }
      const accounts = await eth.request({ method: 'eth_requestAccounts' });
      const address = accounts && accounts[0];
      if (!address) throw new Error('No address returned by wallet');
      const ch = await lumen.post('/investor/web3/wallet/challenge', { chain: 'ethereum', address });
      const message = ch.data.message;
      const signature = await eth.request({ method: 'personal_sign', params: [message, address] });
      await lumen.post('/investor/web3/wallet/verify', { chain: 'ethereum', address, signature });
      await refresh();
      return { ok: true, address };
    } catch (e) {
      const msg = e.code === 'NO_WALLET'
        ? 'NO_WALLET'
        : (e?.code === 4001 ? 'REJECTED' : (lumenError(e) || String(e.message || e)));
      setError(msg);
      return { ok: false, error: msg };
    } finally { setBusy(false); }
  }, [refresh]);

  const setPrimary = useCallback(async (wallet_id) => {
    try { await lumen.post('/investor/web3/wallet/primary', { wallet_id }); await refresh(); return true; }
    catch (e) { setError(lumenError(e)); return false; }
  }, [refresh]);

  const removeWallet = useCallback(async (wallet_id) => {
    try { await lumen.delete(`/investor/web3/wallet/${wallet_id}`); await refresh(); return true; }
    catch (e) { setError(lumenError(e)); return false; }
  }, [refresh]);

  const primary = summary?.primary_wallet || null;

  const value = {
    eligible,
    hasInjected,
    summary,
    wallets,
    busy,
    error,
    connected: !!summary?.has_wallet,
    primary,
    primaryAddress: primary?.address || null,
    primaryShort: primary ? short(primary.address) : '',
    nftCount: summary?.nft_count || 0,
    otcCount: summary?.otc_active_listings || 0,
    walletCount: summary?.wallet_count || 0,
    claimableTotal: summary?.claimable_total_usd || 0,
    needsAttention: !!summary?.needs_attention,
    connect,
    setPrimary,
    removeWallet,
    refresh,
    short,
  };

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

export default WalletContext;
