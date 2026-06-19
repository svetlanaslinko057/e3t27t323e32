import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { lumen, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import { useWallet } from '@/contexts/WalletContext';
import {
  Building2, TrendingUp, PieChart, Coins, MapPin, ChevronDown, ChevronUp,
  ShieldCheck, Repeat, RefreshCw, Lock, Wallet, ArrowUpRight, Layers, LifeBuoy,
} from 'lucide-react';

const USD = (n) => (n === null || n === undefined || isNaN(n))
  ? '$0' : '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const PCT = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : `${Number(n).toFixed(1)}%`;
const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '—');

const STATUS_TONE = {
  operating: 'badge-success', fundraising: 'badge-info', closed: 'badge-neutral',
  funded: 'badge-success', draft: 'badge-neutral',
};

/**
 * Asset Ownership Center — "Мої активи".
 *
 * PRODUCT RULE: the investor owns a SHARE IN A REAL ASSET. The NFT is the
 * internal technical implementation of that ownership and is hidden behind a
 * "технічні деталі" disclosure — 99% of users never need to see it.
 */
export default function InvestorAssets() {
  const { bi } = useLang();
  const w = useWallet();
  const [items, setItems] = useState(null);
  const [totals, setTotals] = useState({ invested: 0, dividends_12m: 0, roi: 0, count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await lumen.get('/investor/web3/portfolio');
      setItems(r.data?.items || []);
      setTotals(r.data?.totals || { invested: 0, dividends_12m: 0, roi: 0, count: 0 });
    } catch (e) { setError(lumenError(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6 md:p-10 max-w-7xl" data-testid="investor-assets">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">{bi('Власність', 'Ownership')}</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">{bi('Мої активи', 'My assets')}</h1>
          <p className="mt-1 text-token-muted text-sm">
            {bi('Ваші частки в реальних об’єктах — інвестиції, дохід і дохідність по кожному активу.',
                'Your shares in real assets — investment, income and yield per object.')}
          </p>
        </div>
        <button onClick={load} data-testid="assets-refresh" className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2">
          <RefreshCw className="w-3.5 h-3.5" /> {bi('Оновити', 'Refresh')}
        </button>
      </header>

      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPI icon={Coins} accent="emerald" label={bi('Інвестовано', 'Invested')} value={USD(totals.invested)} />
        <KPI icon={TrendingUp} accent="sky" label={bi('Дивіденди / рік', 'Dividends / yr')} value={USD(totals.dividends_12m)} />
        <KPI icon={PieChart} accent="amber" label={bi('Сукупний ROI', 'Cumulative ROI')} value={PCT(totals.roi)} />
        <KPI icon={Building2} accent="violet" label={bi('Активних об’єктів', 'Active objects')} value={totals.count} />
      </div>

      {/* wallet nudge — NFT ownership needs a wallet, but framed gently */}
      {!w.connected && (
        <div className="mb-6 rounded-2xl border border-sky-200 bg-sky-50/60 dark:bg-sky-950/20 p-4 flex flex-wrap items-center gap-3" data-testid="assets-wallet-nudge">
          <Wallet className="w-5 h-5 text-sky-600" />
          <div className="flex-1 min-w-[200px]">
            <p className="text-sm font-medium">{bi('Підключіть гаманець для повного контролю', 'Connect a wallet for full control')}</p>
            <p className="text-xs text-token-muted">{bi('Підтвердження права власності та OTC-продаж частки потребують підключеного гаманця.', 'Proving ownership on-chain and selling a share via OTC require a connected wallet.')}</p>
          </div>
        </div>
      )}

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[1, 2, 3].map((i) => <div key={i} className="h-72 rounded-2xl bg-muted/40 animate-pulse" />)}</div>
      ) : !(items || []).length ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center">
          <Layers className="w-10 h-10 text-token-muted mx-auto mb-3" />
          <p className="font-semibold">{bi('У вас ще немає часток', 'You have no shares yet')}</p>
          <p className="text-sm text-token-muted mt-1">{bi('Оберіть об’єкт і станьте співвласником реального активу.', 'Pick an object and become a co-owner of a real asset.')}</p>
          <Link to="/investor/opportunities" className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700">
            <Building2 className="w-4 h-4" /> {bi('Переглянути об’єкти', 'Browse objects')}
          </Link>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="assets-grid">
          {items.map((it) => (
            <AssetCard key={it.nft_id} it={it} bi={bi} />
          ))}
        </div>
      )}

      <RecoveryPanel bi={bi} />
    </div>
  );
}

/* Wallet recovery — investor self-service request (executed by admin after KYC). */
function RecoveryPanel({ bi }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('lost_seed');
  const [lost, setLost] = useState('');
  const [newAddr, setNewAddr] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [mine, setMine] = useState([]);

  const loadMine = useCallback(async () => {
    try { const r = await lumen.get('/investor/web3/recovery/my'); setMine(r.data?.recoveries || []); } catch (_e) { /* noop */ }
  }, []);
  useEffect(() => { loadMine(); }, [loadMine]);

  const submit = async () => {
    setBusy(true); setMsg('');
    try {
      const r = await lumen.post('/investor/web3/recovery/request', { reason, lost_address: lost || null, new_address: newAddr || null });
      setMsg(bi(`Запит створено. Заморожено активів: ${r.data.frozen_nfts}. Менеджер опрацює після перевірки KYC.`,
                `Request created. Frozen assets: ${r.data.frozen_nfts}. A manager will process it after KYC review.`));
      setOpen(false); await loadMine();
    } catch (e) { setMsg(lumenError(e)); }
    finally { setBusy(false); }
  };

  const pending = mine.find((m) => m.status === 'pending');
  return (
    <div className="mt-8 rounded-2xl border border-border bg-card p-5" data-testid="recovery-panel">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-amber-50 dark:bg-amber-950/30 flex items-center justify-center shrink-0">
          <LifeBuoy className="w-5 h-5 text-amber-600" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold">{bi('Втратили доступ до гаманця?', 'Lost access to your wallet?')}</h3>
          <p className="text-sm text-token-muted mt-1">
            {bi('Ваші частки та дивіденди не втрачаються. Подайте запит на відновлення — після перевірки KYC менеджер перевипустить власність на ваш новий гаманець.',
                'Your shares and dividends are never lost. Submit a recovery request — after KYC verification a manager re-points ownership to your new wallet.')}
          </p>

          {pending ? (
            <div className="mt-3 rounded-xl bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200 p-3 text-sm text-amber-800 dark:text-amber-300" data-testid="recovery-pending">
              {bi('Запит на відновлення в обробці. Ваші активи тимчасово заморожені для безпеки.',
                  'Recovery request in progress. Your assets are temporarily frozen for safety.')}
            </div>
          ) : !open ? (
            <button data-testid="recovery-open" onClick={() => setOpen(true)} className="mt-3 px-4 py-2 rounded-xl bg-card border border-amber-200 text-amber-700 text-sm font-medium hover:bg-amber-50">
              {bi('Подати запит на відновлення', 'Submit a recovery request')}
            </button>
          ) : (
            <div className="mt-4 space-y-3 max-w-md" data-testid="recovery-form">
              <select value={reason} onChange={(e) => setReason(e.target.value)} data-testid="recovery-reason" className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm">
                <option value="lost_seed">{bi('Втратив seed-фразу', 'Lost seed phrase')}</option>
                <option value="changed_phone">{bi('Змінив телефон', 'Changed phone')}</option>
                <option value="new_wallet">{bi('Створив новий гаманець', 'Created a new wallet')}</option>
                <option value="compromised">{bi('Гаманець скомпрометовано', 'Wallet compromised')}</option>
              </select>
              <input value={lost} onChange={(e) => setLost(e.target.value)} data-testid="recovery-lost" placeholder={bi('Старий гаманець (необов’язково)', 'Old wallet (optional)')} className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm font-mono" />
              <input value={newAddr} onChange={(e) => setNewAddr(e.target.value)} data-testid="recovery-new" placeholder={bi('Новий гаманець (необов’язково)', 'New wallet (optional)')} className="w-full px-3 py-2 rounded-lg border border-border bg-app text-sm font-mono" />
              <div className="flex gap-2">
                <button data-testid="recovery-submit" disabled={busy} onClick={submit} className="px-4 py-2 rounded-xl bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50">
                  {busy ? bi('Надсилання…', 'Submitting…') : bi('Надіслати запит', 'Send request')}
                </button>
                <button onClick={() => setOpen(false)} className="px-4 py-2 rounded-xl border border-border text-sm">{bi('Скасувати', 'Cancel')}</button>
              </div>
            </div>
          )}
          {msg && <p className="mt-3 text-sm text-token-muted" data-testid="recovery-msg">{msg}</p>}
        </div>
      </div>
    </div>
  );
}

function AssetCard({ it, bi }) {
  const [tech, setTech] = useState(false);
  const a = it.asset || {};
  const m = it.metrics || {};
  const frozen = it.frozen;
  return (
    <div data-testid={`asset-card-${it.pool_id}`} className="rounded-2xl border border-border bg-card overflow-hidden flex flex-col hover:shadow-lg transition-shadow">
      <div className="relative h-40 bg-muted">
        {a.cover_url
          ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" loading="lazy" />
          : <div className="w-full h-full bg-gradient-to-br from-emerald-100 to-sky-100 flex items-center justify-center"><Building2 className="w-9 h-9 text-emerald-600/60" /></div>}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3">
          <h3 className="text-white font-semibold text-[15px] leading-tight drop-shadow">{a.title}</h3>
          {a.location && <p className="text-white/85 text-[11px] flex items-center gap-1 mt-0.5"><MapPin className="w-3 h-3" /> {a.location}</p>}
        </div>
        {a.target_yield != null && <span className="absolute top-2 left-2 px-2 py-0.5 rounded-full bg-emerald-600 text-white text-[10px] font-semibold">{PCT(a.target_yield)} {bi('річних', 'p.a.')}</span>}
        {it.listed && <span className="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-sky-600 text-white text-[10px] font-medium">{bi('на продажу', 'listed')}</span>}
      </div>

      <div className="p-4 flex-1">
        <div className="rounded-xl bg-emerald-50/70 dark:bg-emerald-950/20 border border-emerald-200/60 p-3 text-center mb-3">
          <p className="text-[10px] uppercase tracking-wider text-emerald-700 dark:text-emerald-400">{bi('Ваша частка', 'Your share')}</p>
          <p className="text-2xl font-bold tabular-nums">{PCT(it.ownership_percent)}</p>
        </div>
        <div className="space-y-2 text-sm">
          <Row k={bi('Інвестовано', 'Invested')} v={USD(m.invested_usd)} />
          <Row k={bi('Дивіденди / рік', 'Dividends / yr')} v={USD(m.dividends_12m)} accent="emerald" />
          <Row k={bi('Дохідність (ROI)', 'Yield (ROI)')} v={PCT(m.annual_yield)} accent="emerald" />
          <Row k={bi('Дохід / місяць', 'Income / mo')} v={USD(m.monthly_income)} />
        </div>

        <button onClick={() => setTech((v) => !v)} data-testid={`asset-tech-toggle-${it.pool_id}`}
          className="mt-4 w-full flex items-center justify-between text-[11px] text-token-muted hover:text-foreground border-t border-border/60 pt-2">
          <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" /> {bi('Документ власності', 'Ownership document')}</span>
          {tech ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
        {tech && (
          <div className="mt-2 rounded-lg bg-muted/40 p-3 text-[11px] space-y-1 font-mono" data-testid={`asset-tech-${it.pool_id}`}>
            <div className="flex justify-between"><span className="text-token-muted">{bi('Сертифікат', 'Certificate')}</span><span>{it.token_id ? `#${it.token_id}` : bi('очікує', 'pending')}</span></div>
            <div className="flex justify-between"><span className="text-token-muted">Wallet</span><span>{short(it.current_wallet)}</span></div>
            <div className="flex justify-between"><span className="text-token-muted">{bi('Стандарт', 'Standard')}</span><span>ERC-721</span></div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border bg-muted/20 flex items-center gap-2">
        {frozen ? (
          <span className="flex-1 inline-flex items-center justify-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg py-2" data-testid={`asset-frozen-${it.pool_id}`}>
            <Lock className="w-3.5 h-3.5" /> {bi('Частку заморожено', 'Share frozen')}
          </span>
        ) : it.listed ? (
          <Link to={`/investor/otc/${it.listing_id}`} className="flex-1 inline-flex items-center justify-center gap-1.5 text-sm font-medium rounded-lg py-2 bg-card border border-sky-200 text-sky-700 hover:bg-sky-50">
            <Repeat className="w-4 h-4" /> {bi('Переглянути лот', 'View listing')}
          </Link>
        ) : (
          <Link to="/investor/otc?tab=sell" data-testid={`asset-sell-${it.pool_id}`}
            className="flex-1 inline-flex items-center justify-center gap-1.5 text-sm font-medium rounded-lg py-2 bg-card border border-border hover:bg-muted/60">
            <Repeat className="w-4 h-4" /> {bi('Продати частку', 'Sell share')}
          </Link>
        )}
      </div>
    </div>
  );
}

const Row = ({ k, v, accent }) => (
  <div className="flex items-center justify-between">
    <span className="text-token-muted text-xs">{k}</span>
    <span className={`text-sm font-medium tabular-nums ${accent === 'emerald' ? 'text-emerald-600' : ''}`}>{v}</span>
  </div>
);

const KPI = ({ label, value, icon: Icon, accent = 'neutral' }) => {
  const map = {
    emerald: 'border-emerald-200 bg-emerald-50/60 dark:bg-emerald-950/20',
    sky: 'border-sky-200 bg-sky-50/60 dark:bg-sky-950/20',
    amber: 'border-amber-200 bg-amber-50/60 dark:bg-amber-950/20',
    violet: 'border-violet-200 bg-violet-50/60 dark:bg-violet-950/20',
    neutral: 'border-border bg-card',
  };
  return (
    <div className={`p-4 rounded-2xl border ${map[accent]}`}>
      <div className="flex items-center gap-2 text-token-muted text-[11px] uppercase tracking-widest">{Icon && <Icon className="w-4 h-4" />}{label}</div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
};
