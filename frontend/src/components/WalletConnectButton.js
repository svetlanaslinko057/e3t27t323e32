import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useWallet } from '@/contexts/WalletContext';
import { useLang } from '@/contexts/LanguageContext';
import {
  Wallet, ChevronDown, Boxes, Repeat, Star, Gift, Check, Copy,
  Plus, ShieldCheck, AlertTriangle, ExternalLink,
} from 'lucide-react';

const USD = (n) => (n === null || n === undefined || isNaN(n))
  ? '$0' : '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });

/**
 * Site-wide wallet badge. Two states:
 *   - not connected → "Підключити гаманець"
 *   - connected     → 0xA71C…9F2A  + dropdown (network, NFT/OTC counts, manage)
 *
 * `compact` renders an icon-only trigger (for tight headers / public landing).
 */
export default function WalletConnectButton({ compact = false }) {
  const w = useWallet();
  const { bi } = useLang();
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  if (!w.eligible) return null;

  const doConnect = async () => {
    setNotice('');
    const r = await w.connect();
    if (!r.ok) {
      setNotice(r.error === 'NO_WALLET'
        ? bi('Гаманець не знайдено. Встановіть Rabby або MetaMask.', 'No wallet found. Install Rabby or MetaMask.')
        : (r.error === 'REJECTED' ? bi('Підпис відхилено.', 'Signature rejected.') : r.error));
      setOpen(true);
    } else {
      setNotice(bi('Гаманець підключено ✓', 'Wallet connected ✓'));
    }
  };

  const copyAddr = async () => {
    try { await navigator.clipboard.writeText(w.primaryAddress || ''); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch (_e) { /* noop */ }
  };

  // ── Not connected ──────────────────────────────────────────────────────
  if (!w.connected) {
    return (
      <div className="relative" ref={ref}>
        <button
          data-testid="wallet-connect-btn"
          onClick={doConnect}
          disabled={w.busy}
          className={`inline-flex items-center gap-2 rounded-full font-medium transition disabled:opacity-50
            ${compact ? 'px-3 py-2 text-sm' : 'px-3.5 py-2 text-[13px]'}
            bg-emerald-600 text-white hover:bg-emerald-700 border border-emerald-700/30`}
        >
          <Wallet className="w-4 h-4" />
          {!compact && <span>{w.busy ? bi('Підключення…', 'Connecting…') : bi('Підключити гаманець', 'Connect wallet')}</span>}
        </button>
        {notice && (
          <div className="absolute right-0 mt-2 w-64 z-50 rounded-xl border border-border bg-card p-3 text-xs shadow-lg" data-testid="wallet-connect-notice">
            {notice}
          </div>
        )}
      </div>
    );
  }

  // ── Connected ──────────────────────────────────────────────────────────
  const net = (w.primary?.chain || 'ethereum');
  return (
    <div className="relative" ref={ref}>
      <button
        data-testid="wallet-badge"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded-full px-2.5 py-1.5 text-[13px] font-medium
          bg-card border border-border hover:bg-muted/60 transition"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span className="font-mono">{w.primaryShort}</span>
        {w.needsAttention && <span className="w-2 h-2 rounded-full bg-amber-500" title={bi('Потребує уваги', 'Needs attention')} />}
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-72 z-50 rounded-2xl border border-border bg-card shadow-xl overflow-hidden" data-testid="wallet-dropdown">
          <div className="p-4 bg-emerald-50/60 dark:bg-emerald-950/20 border-b border-border">
            <div className="flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-widest text-emerald-700 dark:text-emerald-400 font-semibold flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" /> {bi('Гаманець підключено', 'Wallet connected')}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-card border border-border capitalize">{net}</span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Star className="w-3.5 h-3.5 text-amber-500" />
              <span className="font-mono text-sm">{w.primaryShort}</span>
              <button onClick={copyAddr} title={bi('Копіювати', 'Copy')} className="ml-auto p-1 rounded hover:bg-muted">
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-border border-b border-border">
            <Stat icon={Boxes} label={bi('Мої активи', 'My assets')} value={w.nftCount} testid="wallet-stat-nft" />
            <Stat icon={Repeat} label={bi('OTC лоти', 'OTC listings')} value={w.otcCount} testid="wallet-stat-otc" />
          </div>

          {w.claimableTotal > 0 && (
            <Link to="/investor/crypto?tab=claim" onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2.5 bg-amber-50/70 dark:bg-amber-950/20 border-b border-border text-sm hover:bg-amber-100/70">
              <Gift className="w-4 h-4 text-amber-600" />
              <span className="text-amber-800 dark:text-amber-300">{bi('До отримання', 'Claimable')}</span>
              <span className="ml-auto font-semibold tabular-nums">{USD(w.claimableTotal)}</span>
            </Link>
          )}
          {w.needsAttention && w.claimableTotal === 0 && (
            <Link to="/investor/crypto?tab=claim" onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2.5 bg-amber-50/70 dark:bg-amber-950/20 border-b border-border text-xs hover:bg-amber-100/70 text-amber-800 dark:text-amber-300">
              <AlertTriangle className="w-3.5 h-3.5" /> {bi('NFT очікують привʼязки гаманця', 'NFTs awaiting wallet link')}
            </Link>
          )}

          <div className="p-2">
            <DropLink to="/investor/crypto?tab=wallets" onClick={() => setOpen(false)} icon={Wallet}
              label={bi(`Мої гаманці (${w.walletCount})`, `My wallets (${w.walletCount})`)} testid="wallet-link-manage" />
            <DropLink to="/investor/my-assets" onClick={() => setOpen(false)} icon={Boxes}
              label={bi('Мої активи', 'My assets')} testid="wallet-link-assets" />
            <DropLink to="/investor/otc" onClick={() => setOpen(false)} icon={Repeat}
              label={bi('OTC ринок', 'OTC market')} testid="wallet-link-otc" />
            <button onClick={doConnect} disabled={w.busy}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-muted/60 text-left disabled:opacity-50" data-testid="wallet-add-another">
              <Plus className="w-4 h-4 text-muted-foreground" /> {bi('Додати ще гаманець', 'Add another wallet')}
            </button>
          </div>
          {notice && <div className="px-4 pb-3 text-xs text-muted-foreground">{notice}</div>}
        </div>
      )}
    </div>
  );
}

const Stat = ({ icon: Icon, label, value, testid }) => (
  <div className="p-3 text-center" data-testid={testid}>
    <div className="flex items-center justify-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
      <Icon className="w-3.5 h-3.5" /> {label}
    </div>
    <p className="mt-1 text-xl font-bold tabular-nums">{value}</p>
  </div>
);

const DropLink = ({ to, onClick, icon: Icon, label, testid }) => (
  <Link to={to} onClick={onClick} data-testid={testid}
    className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm hover:bg-muted/60">
    <Icon className="w-4 h-4 text-muted-foreground" />
    <span className="flex-1">{label}</span>
    <ExternalLink className="w-3 h-3 text-muted-foreground/60" />
  </Link>
);
