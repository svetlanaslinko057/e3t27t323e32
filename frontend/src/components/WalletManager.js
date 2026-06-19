import { useState } from 'react';
import { useWallet } from '@/contexts/WalletContext';
import { useLang } from '@/contexts/LanguageContext';
import {
  Wallet, Star, Trash2, Plus, ShieldCheck, Check, Copy, AlertTriangle,
} from 'lucide-react';

const short = (a) => (a ? `${a.slice(0, 8)}…${a.slice(-6)}` : '');

/** Connected-wallets manager for the investor profile (Гаманці section). */
export default function WalletManager() {
  const w = useWallet();
  const { bi } = useLang();
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState('');

  if (!w.eligible) return null;

  const connect = async () => {
    setNotice('');
    const r = await w.connect();
    setNotice(r.ok
      ? bi('Гаманець підключено ✓', 'Wallet connected ✓')
      : (r.error === 'NO_WALLET'
        ? bi('Встановіть Rabby або MetaMask.', 'Install Rabby or MetaMask.')
        : (r.error === 'REJECTED' ? bi('Підпис відхилено.', 'Signature rejected.') : r.error)));
  };
  const makePrimary = async (id) => { setBusy(id); await w.setPrimary(id); setBusy(''); };
  const remove = async (id) => { setBusy(id); await w.removeWallet(id); setBusy(''); };
  const copy = async (addr) => { try { await navigator.clipboard.writeText(addr); setCopied(addr); setTimeout(() => setCopied(''), 1500); } catch (_e) { /* noop */ } };

  const wallets = w.wallets || [];

  return (
    <section className="rounded-2xl border border-border bg-card p-6 mb-6" data-testid="profile-wallets">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h2 className="text-lg font-semibold flex items-center gap-2"><Wallet className="w-5 h-5 text-emerald-600" /> {bi('Гаманці', 'Wallets')}</h2>
        <button onClick={connect} disabled={w.busy} data-testid="profile-wallet-connect"
          className="px-3 py-1.5 rounded-full text-sm bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> {w.busy ? bi('Підключення…', 'Connecting…') : bi('Підключити', 'Connect')}
        </button>
      </div>
      <p className="text-sm text-token-muted mb-4">
        {bi('Гаманець підтверджує право власності, отримує цифрові сертифікати та потрібен для OTC-ринку. Можна привʼязати кілька — один основний.',
            'A wallet proves ownership, receives digital certificates and is needed for the OTC market. You can link several — one primary.')}
      </p>

      {!w.hasInjected && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {bi('У браузері не виявлено гаманця. Встановіть розширення Rabby або MetaMask.', 'No wallet detected in the browser. Install the Rabby or MetaMask extension.')}
        </div>
      )}

      {!wallets.length ? (
        <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-token-muted" data-testid="profile-wallets-empty">
          {bi('Гаманець ще не підключено.', 'No wallet connected yet.')}
        </div>
      ) : (
        <div className="space-y-2" data-testid="profile-wallets-list">
          {wallets.map((wal) => (
            <div key={wal.id} data-testid={`wallet-item-${wal.id}`} className="flex items-center gap-3 rounded-xl border border-border bg-background p-3">
              <div className="w-9 h-9 rounded-lg bg-emerald-100 dark:bg-emerald-950/40 flex items-center justify-center shrink-0">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm truncate">{short(wal.address)}</span>
                  <button onClick={() => copy(wal.address)} className="p-1 rounded hover:bg-muted">
                    {copied === wal.address ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-token-muted" />}
                  </button>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-token-muted capitalize">{wal.chain || 'ethereum'}</span>
                  {wal.primary && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 flex items-center gap-1"><Star className="w-3 h-3" /> {bi('Основний', 'Primary')}</span>}
                  {wal.verified && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{bi('Підтверджено', 'Verified')}</span>}
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                {!wal.primary && (
                  <button onClick={() => makePrimary(wal.id)} disabled={busy === wal.id} data-testid={`wallet-primary-${wal.id}`}
                    className="px-2 py-1 rounded-lg border border-border text-[11px] hover:bg-muted/60 flex items-center gap-1"><Star className="w-3 h-3" /> {bi('Основний', 'Primary')}</button>
                )}
                {!wal.primary && (
                  <button onClick={() => remove(wal.id)} disabled={busy === wal.id} data-testid={`wallet-remove-${wal.id}`}
                    className="px-2 py-1 rounded-lg border border-rose-200 text-rose-600 text-[11px] hover:bg-rose-50 flex items-center gap-1"><Trash2 className="w-3 h-3" /></button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {notice && <p className="mt-3 text-sm text-token-muted" data-testid="profile-wallet-notice">{notice}</p>}
    </section>
  );
}
