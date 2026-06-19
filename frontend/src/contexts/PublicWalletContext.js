import { createContext, useContext, useCallback, useEffect, useState } from 'react';

/**
 * PUBLIC (guest-capable) Web3 wallet layer.
 *
 * Unlike `WalletContext` (which links a wallet to an *authenticated* investor
 * via the backend sign-to-link flow), this layer just connects an injected
 * wallet (MetaMask / Rabby) in the browser so an ANONYMOUS visitor can buy a
 * share on the public OTC market. The chosen address is remembered locally and
 * handed to `POST /public/otc/reserve`. No backend account is required until
 * the user later logs in and claims the reservation.
 */
const Ctx = createContext(null);
export const usePublicWallet = () => useContext(Ctx) || {};

const LS_KEY = 'lumen_guest_wallet';
const shortAddr = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '');

function injected() {
  return typeof window !== 'undefined' ? window.ethereum : null;
}

export function PublicWalletProvider({ children }) {
  const [account, setAccount] = useState(() => {
    try { return localStorage.getItem(LS_KEY) || null; } catch { return null; }
  });
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');

  const hasProvider = !!injected();

  const persist = (a) => {
    try { a ? localStorage.setItem(LS_KEY, a) : localStorage.removeItem(LS_KEY); } catch { /* noop */ }
  };

  const connect = useCallback(async () => {
    setError(''); setConnecting(true);
    try {
      const eth = injected();
      if (!eth) { setError('NO_WALLET'); return { ok: false, error: 'NO_WALLET' }; }
      const accounts = await eth.request({ method: 'eth_requestAccounts' });
      const a = accounts && accounts[0];
      if (!a) { setError('NO_ADDRESS'); return { ok: false, error: 'NO_ADDRESS' }; }
      setAccount(a); persist(a);
      return { ok: true, address: a };
    } catch (e) {
      const msg = e?.code === 4001 ? 'REJECTED' : (e?.message || 'ERROR');
      setError(msg);
      return { ok: false, error: msg };
    } finally {
      setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(() => { setAccount(null); persist(null); }, []);

  useEffect(() => {
    const eth = injected();
    if (!eth || !eth.on) return;
    const onAccounts = (accounts) => {
      const a = (accounts && accounts[0]) || null;
      setAccount(a); persist(a);
    };
    eth.on('accountsChanged', onAccounts);
    return () => { try { eth.removeListener('accountsChanged', onAccounts); } catch { /* noop */ } };
  }, []);

  const value = {
    account,
    short: shortAddr(account),
    connected: !!account,
    connecting,
    error,
    hasProvider,
    connect,
    disconnect,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export default Ctx;
