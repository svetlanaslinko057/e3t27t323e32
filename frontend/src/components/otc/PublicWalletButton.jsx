import { useState, useRef, useEffect } from 'react';
import { usePublicWallet } from '@/contexts/PublicWalletContext';
import { useLang } from '@/contexts/LanguageContext';
import { Wallet, Check, Copy, LogOut, ChevronDown } from 'lucide-react';

/**
 * Guest-capable wallet button for the public header. Connects MetaMask / Rabby
 * in-browser (no backend account needed) so a visitor can buy on the OTC market.
 */
export default function PublicWalletButton({ compact = false }) {
  const w = usePublicWallet();
  const { bi } = useLang();
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const fn = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  const doConnect = async () => {
    setNotice('');
    const r = await w.connect();
    if (!r.ok) {
      setNotice(r.error === 'NO_WALLET'
        ? bi('Гаманець не знайдено. Встановіть MetaMask або Rabby.', 'No wallet found. Install MetaMask or Rabby.')
        : (r.error === 'REJECTED' ? bi('Підключення відхилено.', 'Connection rejected.') : bi('Помилка підключення.', 'Connection error.')));
      setOpen(true);
    }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(w.account || ''); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* noop */ }
  };

  if (!w.connected) {
    return (
      <div className="relative" ref={ref}>
        <button
          data-testid="public-wallet-connect"
          onClick={doConnect}
          disabled={w.connecting}
          className={`inline-flex items-center gap-2 rounded-full font-medium transition disabled:opacity-50 border bg-emerald-600 text-white hover:bg-emerald-700 border-emerald-700/30 ${compact ? 'px-3 py-2 text-sm' : 'px-3.5 py-2 text-[13px]'}`}
        >
          <Wallet className="w-4 h-4" />
          {!compact && <span>{w.connecting ? bi('Підключення…', 'Connecting…') : bi('Підключити гаманець', 'Connect wallet')}</span>}
        </button>
        {notice && (
          <div className="absolute right-0 mt-2 w-64 z-50 rounded-xl border border-border bg-card p-3 text-xs shadow-lg" data-testid="public-wallet-notice">
            {notice}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        data-testid="public-wallet-badge"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-full px-2.5 py-1.5 text-[13px] font-medium bg-card border border-border hover:bg-muted/60 transition"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="font-mono">{w.short}</span>
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 z-50 rounded-2xl border border-border bg-card shadow-xl overflow-hidden" data-testid="public-wallet-dropdown">
          <div className="p-3 border-b border-border flex items-center gap-2">
            <Wallet className="w-4 h-4 text-emerald-600" />
            <span className="font-mono text-sm flex-1">{w.short}</span>
            <button onClick={copy} className="p-1 rounded hover:bg-muted" title={bi('Копіювати', 'Copy')}>
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
            </button>
          </div>
          <div className="p-2">
            <button onClick={() => { w.disconnect(); setOpen(false); }} data-testid="public-wallet-disconnect"
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted/60 text-left">
              <LogOut className="w-4 h-4 text-muted-foreground" /> {bi('Відключити гаманець', 'Disconnect wallet')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
