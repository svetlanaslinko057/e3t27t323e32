import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { lumen, formatDateUk, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  Wallet, ShieldCheck, Gift, RefreshCw, Star, Trash2, Building2, MapPin,
  Repeat, Boxes, TrendingUp, ArrowRight, ChevronDown, ChevronUp, Lock,
  AlertTriangle, CheckCircle2, Tag, Coins,
} from 'lucide-react';

const USD = (n) => (n === null || n === undefined || isNaN(n))
  ? '—' : '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;
const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '—');

const TONE = {
  minted: 'badge-success', transferred: 'badge-info', active: 'badge-success',
  completed: 'badge-success', credited: 'badge-success', pending_mint: 'badge-warning',
  pending_wallet: 'badge-warning', reserved: 'badge-info',
  holder_unlinked: 'badge-danger', disputed: 'badge-danger', cancelled: 'badge-neutral',
};
const Pill = ({ s, label }) => <span className={`status-badge ${TONE[s] || 'badge-neutral'}`} style={{ fontSize: 11 }}>{label || s || '—'}</span>;

const CAT_LABEL = {
  real_estate: { uk: 'Житло', en: 'Residential' },
  commercial: { uk: 'Комерція', en: 'Commercial' },
  land: { uk: 'Земля', en: 'Land' },
  construction: { uk: 'Будівництво', en: 'Construction' },
};

/* ── injected wallet (MetaMask / Rabby) sign-in ───────────────────────── */
async function connectInjectedWallet() {
  const eth = typeof window !== 'undefined' ? window.ethereum : null;
  if (!eth) {
    const e = new Error('NO_WALLET');
    e.code = 'NO_WALLET';
    throw e;
  }
  const accounts = await eth.request({ method: 'eth_requestAccounts' });
  const address = accounts && accounts[0];
  if (!address) throw new Error('Не вдалося отримати адресу гаманця');
  const ch = await lumen.post('/investor/web3/wallet/challenge', { chain: 'ethereum', address });
  const message = ch.data.message;
  const signature = await eth.request({ method: 'personal_sign', params: [message, address] });
  await lumen.post('/investor/web3/wallet/verify', { chain: 'ethereum', address, signature });
  return address;
}

/**
 * "Гаманець та власність" — wallet + ownership certificates + claims.
 *
 * Web3 is NOT a separate world here. The investor's real product lives in the
 * main cabinet (Активи / OTC ринок / Доходи). This screen is only the wallet,
 * the digital ownership certificates, and unlocking payouts.
 */
export default function InvestorCryptoCenter() {
  const { bi } = useLang();
  const [tab, setTab] = useState('wallets');
  const [claimable, setClaimable] = useState(null);

  const loadClaimable = useCallback(async () => {
    try { const r = await lumen.get('/investor/web3/claimable'); setClaimable(r.data); }
    catch { /* ignore */ }
  }, []);
  useEffect(() => { loadClaimable(); }, [loadClaimable]);

  const TABS = [
    { id: 'wallets', icon: Wallet, label: bi('Гаманці', 'Wallets') },
    { id: 'nfts', icon: ShieldCheck, label: bi('Сертифікати власності', 'Ownership certificates') },
    { id: 'claim', icon: Gift, label: bi('Виплати', 'Payouts') },
  ];
  const claimBadge = claimable && (claimable.claimable_count > 0 || (claimable.pending_wallet_nfts || []).length > 0);

  return (
    <div className="p-6 md:p-10 max-w-7xl" data-testid="investor-crypto-center">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">{bi('Web3-гаманець', 'Web3 wallet')}</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">{bi('Гаманець та власність', 'Wallet & ownership')}</h1>
        <p className="mt-1 text-token-muted text-sm">
          {bi('Підключений гаманець, цифрові сертифікати вашої власності та розблокування виплат — в одному місці.',
              'Connected wallet, digital ownership certificates and payout unlocking — in one place.')}
        </p>
      </header>

      {/* Product shortcuts — Web3 lives INSIDE the product, not beside it */}
      <div className="grid sm:grid-cols-3 gap-3 mb-7" data-testid="crypto-shortcuts">
        <ShortcutCard to="/investor/my-assets" icon={Boxes} title={bi('Мої активи', 'My assets')}
          sub={bi('Ваші частки в реальних обʼєктах', 'Your shares in real objects')} bi={bi} testid="shortcut-assets" />
        <ShortcutCard to="/investor/otc" icon={Repeat} title={bi('OTC ринок', 'OTC market')}
          sub={bi('Купити або продати частку', 'Buy or sell a share')} bi={bi} testid="shortcut-otc" accent />
        <ShortcutCard to="/investor/income" icon={TrendingUp} title={bi('Доходи', 'Income')}
          sub={bi('Дивіденди та виплати', 'Dividends & payouts')} bi={bi} testid="shortcut-income" />
      </div>

      <div className="flex flex-wrap gap-2 mb-6" data-testid="crypto-center-tabs">
        {TABS.map((t) => {
          const Icon = t.icon; const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`ctab-${t.id}`}
              className={`px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 border transition relative ${
                active ? 'nav-item-active border-transparent' : 'bg-card border-border hover:bg-muted/50 text-token-primary'}`}>
              <Icon className="w-4 h-4" /> {t.label}
              {t.id === 'claim' && claimBadge && <span className="ml-1 w-2 h-2 rounded-full bg-rose-500" />}
            </button>
          );
        })}
      </div>

      {tab === 'wallets' && <WalletsTab bi={bi} onChange={loadClaimable} />}
      {tab === 'nfts' && <CertificatesTab bi={bi} />}
      {tab === 'claim' && <ClaimTab bi={bi} claimable={claimable} reload={loadClaimable} />}
    </div>
  );
}

const ShortcutCard = ({ to, icon: Icon, title, sub, accent, testid }) => (
  <Link to={to} data-testid={testid}
    className={`group rounded-2xl border p-4 flex items-center gap-3 transition hover:shadow-md ${
      accent ? 'border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20' : 'border-border bg-card hover:bg-muted/40'}`}>
    <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${accent ? 'bg-emerald-600 text-white' : 'bg-muted text-foreground'}`}>
      <Icon className="w-5 h-5" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="font-semibold text-sm">{title}</p>
      <p className="text-[11px] text-token-muted truncate">{sub}</p>
    </div>
    <ArrowRight className="w-4 h-4 text-token-muted group-hover:translate-x-0.5 transition" />
  </Link>
);

/* ── shared ───────────────────────────────────────────────────────────── */
function useApi(url, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const r = await lumen.get(url); setData(r.data); }
    catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, ...deps]);
  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}
const Loading = () => <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-20 rounded-2xl bg-muted/40 animate-pulse" />)}</div>;
const ErrBox = ({ msg }) => msg ? <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{msg}</div> : null;
const Empty = ({ msg, cta }) => (
  <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-token-muted">
    <p>{msg}</p>
    {cta}
  </div>
);
const RefreshBtn = ({ onClick }) => (
  <button onClick={onClick} data-testid="btn-refresh" className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2">
    <RefreshCw className="w-3.5 h-3.5" /> Оновити
  </button>
);

/* ── 1. Wallets ───────────────────────────────────────────────────────── */
function WalletsTab({ bi, onChange }) {
  const { data, loading, error, reload } = useApi('/investor/web3/wallets');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const connect = async () => {
    setBusy(true); setNotice('');
    try {
      const addr = await connectInjectedWallet();
      setNotice(bi(`Гаманець ${short(addr)} підтверджено ✓`, `Wallet ${short(addr)} verified ✓`));
      await reload(); onChange && onChange();
    } catch (e) {
      if (e.code === 'NO_WALLET') {
        setNotice(bi('Гаманець не знайдено. Встановіть розширення Rabby або MetaMask у браузері.',
                     'No wallet detected. Install the Rabby or MetaMask browser extension.'));
      } else if (e?.code === 4001) {
        setNotice(bi('Підпис відхилено користувачем.', 'Signature rejected by user.'));
      } else {
        setNotice(lumenError(e) || String(e.message || e));
      }
    } finally { setBusy(false); }
  };

  const setPrimary = async (wallet_id) => { try { await lumen.post('/investor/web3/wallet/primary', { wallet_id }); await reload(); onChange && onChange(); } catch (e) { alert(lumenError(e)); } };
  const remove = async (wallet_id) => { try { await lumen.delete(`/investor/web3/wallet/${wallet_id}`); await reload(); onChange && onChange(); } catch (e) { alert(lumenError(e)); } };

  if (loading) return <Loading />;
  const rows = data?.wallets || [];
  return (
    <div data-testid="wallets-tab">
      <ErrBox msg={error} />
      <div className="rounded-2xl border border-border bg-card p-5 mb-5">
        <h3 className="font-semibold mb-1">{bi('Підключити гаманець', 'Connect wallet')}</h3>
        <p className="text-sm text-token-muted mb-4">{bi('Підпишіть повідомлення для підтвердження володіння. Підпис не авторизує жодної транзакції. Інвестувати можна й без гаманця — через банк.', 'Sign a message to prove ownership. The signature does not authorize any transaction. You can also invest without a wallet — via bank.')}</p>
        <div className="flex flex-wrap gap-2">
          <button onClick={connect} disabled={busy} data-testid="btn-connect-rabby"
            className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-2">
            <Wallet className="w-4 h-4" /> Rabby <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded">{bi('рекомендовано', 'recommended')}</span>
          </button>
          <button onClick={connect} disabled={busy} data-testid="btn-connect-metamask"
            className="px-4 py-2 rounded-xl bg-card border border-border text-sm font-medium hover:bg-muted/50 disabled:opacity-50 flex items-center gap-2">
            <Wallet className="w-4 h-4" /> MetaMask
          </button>
          <button disabled title={bi('Скоро', 'Coming soon')} data-testid="btn-connect-walletconnect"
            className="px-4 py-2 rounded-xl bg-card border border-border text-sm font-medium opacity-50 cursor-not-allowed flex items-center gap-2">
            <Wallet className="w-4 h-4" /> WalletConnect <span className="text-[10px]">({bi('скоро', 'soon')})</span>
          </button>
        </div>
        {notice && <div data-testid="wallet-notice" className="mt-3 text-sm p-2 rounded-lg bg-muted/50 border border-border">{notice}</div>}
      </div>

      <div className="flex justify-end mb-3"><RefreshBtn onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Гаманців ще немає — підключіть перший вище.', 'No wallets yet — connect one above.')} /> : (
        <div className="grid sm:grid-cols-2 gap-3" data-testid="wallets-list">
          {rows.map((w) => (
            <div key={w.id} data-testid={`wallet-card-${w.id}`} className="rounded-2xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm" title={w.address}>{short(w.address)}</span>
                  {w.primary && <span className="status-badge badge-warning" style={{ fontSize: 10 }}><Star className="w-3 h-3 inline -mt-0.5" /> {bi('основний', 'primary')}</span>}
                </div>
                <Pill s={w.disabled ? 'cancelled' : (w.verified ? 'active' : 'pending_wallet')} />
              </div>
              <div className="mt-2 text-[11px] text-token-muted flex flex-wrap gap-x-4 gap-y-1">
                <span className="capitalize">{w.chain}</span>
                {w.verified_at && <span>{bi('Підтверджено', 'Verified')}: {formatDateUk(w.verified_at)}</span>}
              </div>
              <div className="mt-3 flex gap-2">
                {!w.primary && w.verified && (
                  <button data-testid={`btn-make-primary-${w.id}`} onClick={() => setPrimary(w.id)}
                    className="px-2.5 py-1 rounded-lg border border-border text-xs hover:bg-muted/50 flex items-center gap-1"><Star className="w-3 h-3" /> {bi('Зробити основним', 'Make primary')}</button>
                )}
                <button data-testid={`btn-delete-wallet-${w.id}`} onClick={() => remove(w.id)}
                  className="px-2.5 py-1 rounded-lg border border-rose-200 text-rose-700 text-xs hover:bg-rose-50 flex items-center gap-1"><Trash2 className="w-3 h-3" /> {bi('Видалити', 'Remove')}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 2. Ownership certificates (share-framed; NFT kept as technical detail) ─ */
function CertificatesTab({ bi }) {
  const { data, loading, error, reload } = useApi('/investor/nft-certificates');
  const [showTech, setShowTech] = useState({});
  if (loading) return <Loading />;
  const nfts = data?.nfts || [];
  return (
    <div data-testid="nfts-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-3"><RefreshBtn onClick={reload} /></div>
      {!nfts.length ? (
        <Empty
          msg={bi('У вас ще немає сертифікатів власності.', 'You have no ownership certificates yet.')}
          cta={<Link to="/investor/opportunities" data-testid="cert-empty-cta" className="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700">{bi('Обрати обʼєкт', 'Choose an object')} <ArrowRight className="w-4 h-4" /></Link>}
        />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="nfts-list">
          {nfts.map((n) => {
            const a = n.asset || {};
            const cat = CAT_LABEL[a.category];
            const open = !!showTech[n.id];
            return (
              <div key={n.id} data-testid={`nft-card-${n.id}`} className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col">
                <div className="relative h-32 bg-muted">
                  {a.cover_url
                    ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" loading="lazy" />
                    : <div className="w-full h-full bg-gradient-to-br from-emerald-100 to-sky-100 dark:from-emerald-950/40 dark:to-sky-950/40 flex items-center justify-center"><Building2 className="w-8 h-8 text-emerald-600/60" /></div>}
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2.5">
                    <h3 className="text-white font-semibold text-sm leading-tight drop-shadow">{a.title || bi('Частка в активі', 'Asset share')}</h3>
                    {a.location && <p className="text-white/85 text-[10px] flex items-center gap-1 mt-0.5"><MapPin className="w-3 h-3" /> {a.location}</p>}
                  </div>
                  <div className="absolute top-2 left-2 flex gap-1.5">
                    {cat && <span className="px-2 py-0.5 rounded-full bg-white/90 text-[10px] font-medium text-slate-700">{bi(cat.uk, cat.en)}</span>}
                  </div>
                  {n.frozen && <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-amber-500 text-white text-[10px] flex items-center gap-1"><Lock className="w-3 h-3" /> {bi('заморожено', 'frozen')}</span>}
                </div>
                <div className="p-4 flex-1">
                  <div className="grid grid-cols-2 gap-2 text-center">
                    <div className="rounded-lg bg-muted/40 p-2">
                      <p className="text-[10px] uppercase tracking-wide text-token-muted">{bi('Ваша частка', 'Your share')}</p>
                      <p className="font-bold text-[15px] mt-0.5">{PCT(n.ownership_percent)}</p>
                    </div>
                    <div className="rounded-lg bg-muted/40 p-2">
                      <p className="text-[10px] uppercase tracking-wide text-token-muted">{bi('Дохідність', 'Yield')}</p>
                      <p className="font-bold text-[15px] mt-0.5 text-emerald-600">{PCT(a.target_yield)}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <Pill s={n.status} label={n.status === 'minted' || n.status === 'transferred' ? bi('Підтверджено', 'Confirmed') : undefined} />
                    {['minted', 'transferred'].includes(n.status) && !n.frozen && (
                      <Link to="/investor/otc?tab=sell" data-testid={`btn-sell-${n.id}`}
                        className="px-2.5 py-1.5 rounded-lg bg-card border border-border text-xs hover:bg-muted/60 flex items-center gap-1"><Tag className="w-3 h-3" /> {bi('Продати частку', 'Sell share')}</Link>
                    )}
                  </div>
                  <button onClick={() => setShowTech((s) => ({ ...s, [n.id]: !open }))} data-testid={`tech-toggle-${n.id}`}
                    className="mt-3 w-full flex items-center justify-between text-[11px] text-token-muted hover:text-foreground">
                    <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> {bi('Технічні дані (сертифікат)', 'Technical details (certificate)')}</span>
                    {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                  {open && (
                    <div className="mt-2 rounded-lg bg-muted/40 p-3 text-[11px] space-y-1 font-mono" data-testid={`tech-${n.id}`}>
                      <div className="flex justify-between"><span className="text-token-muted">{bi('Сертифікат', 'Certificate')}</span><span>{n.token_id ? `#${n.token_id}` : '—'}</span></div>
                      <div className="flex justify-between"><span className="text-token-muted">{bi('Юніти', 'Units')}</span><span>{n.units}</span></div>
                      <div className="flex justify-between"><span className="text-token-muted">{bi('Гаманець', 'Wallet')}</span><span>{short(n.current_wallet)}</span></div>
                      <div className="flex justify-between"><span className="text-token-muted">{bi('Стандарт', 'Standard')}</span><span>ERC-721</span></div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── 3. Claim Center (payouts) ────────────────────────────────────────── */
function ClaimTab({ bi, claimable, reload }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const connect = async () => {
    setBusy(true); setNotice('');
    try { await connectInjectedWallet(); await reload(); setNotice(bi('Гаманець підключено. Виплати розблоковуються автоматично.', 'Wallet connected. Payouts are released automatically.')); }
    catch (e) { setNotice(e.code === 'NO_WALLET' ? bi('Гаманець не знайдено. Встановіть Rabby або MetaMask.', 'No wallet detected. Install Rabby or MetaMask.') : (lumenError(e) || String(e.message || e))); }
    finally { setBusy(false); }
  };
  const claim = async () => {
    setBusy(true); setNotice('');
    try { const r = await lumen.post('/investor/web3/claim'); setNotice(bi(`Розблоковано виплат: ${r.data.released_count} на суму ${USD(r.data.released_total_usd)}`, `Released ${r.data.released_count} payout(s) totalling ${USD(r.data.released_total_usd)}`)); await reload(); }
    catch (e) { setNotice(lumenError(e)); }
    finally { setBusy(false); }
  };

  if (!claimable) return <Loading />;
  const blocked = claimable.blocked_distributions || [];
  const pendingNfts = claimable.pending_wallet_nfts || [];
  const nothing = blocked.length === 0 && pendingNfts.length === 0;

  return (
    <div data-testid="claim-tab">
      {notice && <div data-testid="claim-notice" className="mb-4 text-sm p-3 rounded-xl bg-muted/50 border border-border">{notice}</div>}

      {nothing ? (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-8 text-center">
          <ShieldCheck className="w-10 h-10 text-emerald-600 mx-auto mb-3" />
          <p className="font-semibold">{bi('Усе чисто 🎉', 'All clear 🎉')}</p>
          <p className="text-sm text-token-muted mt-1">{bi('Заблокованих виплат немає, усі сертифікати привʼязані до гаманця.', 'No blocked payouts; all certificates are linked to a wallet.')}</p>
        </div>
      ) : (
        <>
          {claimable.claimable_total_usd > 0 && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5 mb-4" data-testid="claim-banner">
              <div className="flex items-center gap-2 text-amber-800 font-semibold"><Gift className="w-5 h-5" /> {bi('У вас є виплати до отримання', 'You have payouts to claim')}</div>
              <p className="text-2xl font-bold mt-2 tabular-nums">{USD(claimable.claimable_total_usd)}</p>
              <p className="text-sm text-token-muted mt-1">{bi('Накопичені дивіденди по вашій частці. Натисніть, щоб зарахувати на баланс.', 'Accrued dividends on your share. Click to credit them to your balance.')}</p>
              <button data-testid="btn-claim" disabled={busy} onClick={claim}
                className="mt-3 px-4 py-2 rounded-xl bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50 flex items-center gap-2">
                <Gift className="w-4 h-4" /> {bi('Отримати виплати', 'Claim payouts')}
              </button>
            </div>
          )}

          {!claimable.has_verified_wallet && (
            <div className="rounded-2xl border border-sky-200 bg-sky-50/60 p-5 mb-4">
              <div className="flex items-center gap-2 text-sky-800 font-semibold"><Wallet className="w-5 h-5" /> {bi('Підключіть гаманець', 'Connect your wallet')}</div>
              <p className="text-sm text-token-muted mt-1">{bi('Щоб розблокувати виплати по вашій частці, підключіть гаманець, який нею володіє.', 'To unlock share payouts, connect the wallet that holds it.')}</p>
              <button data-testid="btn-claim-connect" disabled={busy} onClick={connect}
                className="mt-3 px-4 py-2 rounded-xl bg-sky-600 text-white text-sm font-medium hover:bg-sky-700 disabled:opacity-50 flex items-center gap-2">
                <Wallet className="w-4 h-4" /> {bi('Підключити гаманець', 'Connect wallet')}
              </button>
            </div>
          )}

          {pendingNfts.length > 0 && (
            <div className="rounded-2xl border border-border bg-card p-4 mb-4" data-testid="pending-nft-list">
              <h4 className="font-semibold text-sm mb-2">{bi('Сертифікати очікують привʼязки гаманця', 'Certificates awaiting wallet link')}</h4>
              {pendingNfts.map((n) => (
                <div key={n.id} className="flex items-center justify-between py-1.5 border-b border-border/40 last:border-0 text-sm">
                  <span className="text-xs font-medium">{n.asset_title || n.asset?.title || bi('Частка в активі', 'Asset share')}</span>
                  <span>{n.units} · {n.ownership_percent}%</span>
                  <Pill s={n.status} />
                </div>
              ))}
            </div>
          )}

          {blocked.length > 0 && (
            <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid="claim-blocked-table">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
                  <tr><th className="px-3 py-2 text-left">{bi('Обʼєкт', 'Object')}</th><th className="px-3 py-2 text-left">{bi('Сертифікат', 'Certificate')}</th><th className="px-3 py-2 text-left">{bi('Гаманець', 'Wallet')}</th><th className="px-3 py-2 text-right">{bi('Сума', 'Amount')}</th></tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {blocked.map((b) => (
                    <tr key={b.id} data-testid={`claim-row-${b.id}`} className="hover:bg-muted/20">
                      <td className="px-3 py-2 text-[12px]">{b.asset_title || b.pool_id}</td>
                      <td className="px-3 py-2 font-mono text-[11px]">{b.token_id || '—'}</td>
                      <td className="px-3 py-2 font-mono text-[11px]">{short(b.wallet)}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-semibold text-amber-700">{USD(b.amount_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
