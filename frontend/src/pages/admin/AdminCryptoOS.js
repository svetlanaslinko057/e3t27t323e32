import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import {
  LayoutDashboard, Wallet, Boxes, Repeat, ArrowLeftRight, Camera,
  ShieldAlert, Radio, RefreshCw, Star, Ban, CheckCircle2,
  CircleDollarSign, Send, XCircle, AlertTriangle, Coins,
  LifeBuoy, Lock, KeyRound, Check,
} from 'lucide-react';

const USD = (n) => {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
};
const short = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '—');

/* ── status pill ──────────────────────────────────────────────────────── */
const TONE = {
  minted: 'badge-success', transferred: 'badge-info', active: 'badge-success',
  completed: 'badge-success', pending_mint: 'badge-warning', pending_wallet: 'badge-warning',
  payment_pending: 'badge-warning', payment_confirmed: 'badge-info',
  nft_transfer_pending: 'badge-warning', reserved: 'badge-info',
  holder_unlinked: 'badge-danger', unlinked: 'badge-danger', disputed: 'badge-danger',
  cancelled: 'badge-neutral', burned: 'badge-neutral', draft: 'badge-neutral',
};
const Pill = ({ s }) => (
  <span className={`status-badge ${TONE[s] || 'badge-neutral'}`} style={{ fontSize: 11 }}>{s || '—'}</span>
);

export default function AdminCryptoOS() {
  const { bi } = useLang();
  const [tab, setTab] = useState('overview');

  const TABS = [
    { id: 'overview', icon: LayoutDashboard, label: bi('Огляд', 'Overview') },
    { id: 'wallets', icon: Wallet, label: bi('Реєстр гаманців', 'Wallet Registry') },
    { id: 'nfts', icon: Boxes, label: bi('Реєстр NFT', 'NFT Registry') },
    { id: 'otc', icon: Repeat, label: bi('OTC угоди', 'OTC Deals') },
    { id: 'recoveries', icon: LifeBuoy, label: bi('Відновлення', 'Recoveries') },
    { id: 'transfers', icon: ArrowLeftRight, label: bi('Черга трансферів', 'Transfer Queue') },
    { id: 'snapshots', icon: Camera, label: bi('Снапшоти', 'Snapshots') },
    { id: 'blocked', icon: ShieldAlert, label: bi('Заблоковані виплати', 'Blocked Payouts') },
    { id: 'events', icon: Radio, label: bi('Події блокчейну', 'Blockchain Events') },
  ];

  return (
    <div className="p-6 md:p-10 max-w-7xl" data-testid="admin-crypto-os">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">H2.9 · Crypto OS</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">{bi('Admin Crypto OS', 'Admin Crypto OS')}</h1>
        <p className="mt-1 text-token-muted text-sm">
          {bi('Операційний центр: гаманці, NFT-власність, OTC-сделки, трансфери та виплати.',
              'Operational center: wallets, NFT ownership, OTC deals, transfers and payouts.')}
        </p>
      </header>

      <div className="flex flex-wrap gap-2 mb-6" data-testid="crypto-tabs">
        {TABS.map((t) => {
          const Icon = t.icon; const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}
              className={`px-3 py-2 rounded-xl text-sm font-medium flex items-center gap-2 border transition ${
                active ? 'nav-item-active border-transparent' : 'bg-card border-border hover:bg-muted/50 text-token-primary'}`}>
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'overview' && <OverviewTab bi={bi} />}
      {tab === 'wallets' && <WalletsTab bi={bi} />}
      {tab === 'nfts' && <NftsTab bi={bi} />}
      {tab === 'otc' && <OtcTab bi={bi} />}
      {tab === 'recoveries' && <RecoveriesTab bi={bi} />}
      {tab === 'transfers' && <TransfersTab bi={bi} />}
      {tab === 'snapshots' && <SnapshotsTab bi={bi} />}
      {tab === 'blocked' && <BlockedTab bi={bi} />}
      {tab === 'events' && <EventsTab bi={bi} />}
    </div>
  );
}

/* ── shared data hook ─────────────────────────────────────────────────── */
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

const Loading = () => (
  <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-20 rounded-2xl bg-muted/40 animate-pulse" />)}</div>
);
const ErrBox = ({ msg }) => msg ? <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{msg}</div> : null;
const Empty = ({ msg }) => <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-token-muted">{msg}</div>;
const RefreshBtn = ({ onClick }) => (
  <button onClick={onClick} className="px-3 py-1.5 rounded-full text-sm bg-card border border-border hover:bg-muted/50 flex items-center gap-2" data-testid="btn-refresh">
    <RefreshCw className="w-3.5 h-3.5" /> Оновити
  </button>
);
const TableWrap = ({ headers, children, testid }) => (
  <div className="rounded-2xl overflow-hidden border border-border bg-card" data-testid={testid}>
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-widest text-token-muted bg-muted/40">
          <tr>{headers.map((h, i) => <th key={i} className={`px-3 py-2 ${h.r ? 'text-right' : 'text-left'}`}>{h.t}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-border/40">{children}</tbody>
      </table>
    </div>
  </div>
);

/* ── 1. Overview ──────────────────────────────────────────────────────── */
function OverviewTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/web3/overview');
  if (loading) return <Loading />;
  return (
    <div data-testid="overview-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-4"><RefreshBtn onClick={reload} /></div>
      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <KPI icon={Wallet} accent="sky" label={bi('Підключені гаманці', 'Connected wallets')} value={data.wallets.connected} />
            <KPI icon={Boxes} accent="emerald" label={bi('Заміновані NFT', 'Minted NFTs')} value={data.nfts.minted} />
            <KPI icon={Boxes} accent="amber" label={bi('Очікують mint', 'Pending mint')} value={data.nfts.pending_mint + data.nfts.pending_wallet} />
            <KPI icon={ShieldAlert} accent="rose" label={bi('Відвʼязані', 'Unlinked')} value={data.nfts.unlinked} />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KPI icon={Repeat} accent="sky" label={bi('OTC активні', 'OTC active')} value={data.otc.deals_open} />
            <KPI icon={Send} accent="amber" label={bi('Очікують transfer', 'Pending transfers')} value={data.otc.pending_transfer} />
            <KPI icon={AlertTriangle} accent="rose" label={bi('OTC спори', 'OTC disputed')} value={data.otc.disputed} />
            <KPI icon={Coins} accent="rose" label={bi('Заблоковані виплати', 'Blocked payouts')} value={USD(data.blocked_payouts.total_usd)} sub={`${data.blocked_payouts.count} шт`} />
          </div>
        </>
      )}
    </div>
  );
}
const KPI = ({ label, value, icon: Icon, accent = 'neutral', sub }) => {
  const map = {
    emerald: 'border-emerald-200 bg-emerald-50/60', sky: 'border-sky-200 bg-sky-50/60',
    amber: 'border-amber-200 bg-amber-50/60', rose: 'border-rose-200 bg-rose-50/60', neutral: 'border-border bg-card',
  };
  return (
    <div className={`p-4 rounded-2xl border ${map[accent]}`}>
      <div className="flex items-center gap-2 text-token-muted text-[11px] uppercase tracking-widest">{Icon && <Icon className="w-4 h-4" />}{label}</div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-token-muted mt-0.5">{sub}</p>}
    </div>
  );
};

/* ── 2. Wallet Registry ───────────────────────────────────────────────── */
function WalletsTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/web3/wallets');
  const [busy, setBusy] = useState('');
  const act = async (path, wallet_id) => {
    setBusy(wallet_id);
    try { await lumen.post(path, { wallet_id }); await reload(); }
    catch (e) { alert(lumenError(e)); }
    finally { setBusy(''); }
  };
  if (loading) return <Loading />;
  const rows = data?.wallets || [];
  return (
    <div data-testid="wallets-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-4"><RefreshBtn onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Гаманців немає', 'No wallets')} /> : (
        <TableWrap testid="wallets-table" headers={[
          { t: bi('Інвестор', 'Investor') }, { t: bi('Гаманець', 'Wallet') }, { t: bi('Мережа', 'Network') },
          { t: bi('Осн.', 'Primary') }, { t: bi('Статус', 'Status') }, { t: bi('Дії', 'Actions') }]}>
          {rows.map((w) => (
            <tr key={w.id} data-testid={`wallet-row-${w.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{w.user_id}</td>
              <td className="px-3 py-2 font-mono text-[12px]" title={w.address}>{short(w.address)}</td>
              <td className="px-3 py-2 capitalize">{w.chain}</td>
              <td className="px-3 py-2">{w.primary ? <Star className="w-4 h-4 text-amber-500 fill-amber-400" /> : '—'}</td>
              <td className="px-3 py-2"><Pill s={w.disabled ? 'cancelled' : (w.verified ? 'active' : 'draft')} /></td>
              <td className="px-3 py-2">
                <div className="flex gap-1.5">
                  {!w.primary && w.verified && !w.disabled && (
                    <IconBtn testid={`btn-primary-${w.id}`} disabled={busy === w.id} onClick={() => act('/admin/web3/wallet/make-primary', w.id)} icon={Star} title={bi('Зробити основним', 'Make primary')} />
                  )}
                  {w.disabled
                    ? <IconBtn testid={`btn-enable-${w.id}`} disabled={busy === w.id} tone="emerald" onClick={() => act('/admin/web3/wallet/enable', w.id)} icon={CheckCircle2} title={bi('Увімкнути', 'Enable')} />
                    : <IconBtn testid={`btn-disable-${w.id}`} disabled={busy === w.id} tone="rose" onClick={() => act('/admin/web3/wallet/disable', w.id)} icon={Ban} title={bi('Вимкнути', 'Disable')} />}
                </div>
              </td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}
const IconBtn = ({ icon: Icon, onClick, title, tone = 'neutral', disabled, testid }) => {
  const map = { neutral: 'border-border hover:bg-muted/50', emerald: 'border-emerald-200 text-emerald-700 hover:bg-emerald-50', rose: 'border-rose-200 text-rose-700 hover:bg-rose-50' };
  return (
    <button data-testid={testid} disabled={disabled} onClick={onClick} title={title}
      className={`p-1.5 rounded-lg border text-xs bg-card transition disabled:opacity-40 ${map[tone]}`}>
      <Icon className="w-3.5 h-3.5" />
    </button>
  );
};

/* ── 3. NFT Registry ──────────────────────────────────────────────────── */
const NFT_FILTERS = ['all', 'pending_wallet', 'pending_mint', 'minted', 'transferred', 'holder_unlinked', 'burned'];
function NftsTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/nft-registry');
  const [f, setF] = useState('all');
  if (loading) return <Loading />;
  const all = data?.nfts || [];
  const rows = f === 'all' ? all : all.filter((n) => n.status === f);
  return (
    <div data-testid="nfts-tab">
      <ErrBox msg={error} />
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex flex-wrap gap-1.5">
          {NFT_FILTERS.map((s) => (
            <button key={s} data-testid={`nft-filter-${s}`} onClick={() => setF(s)}
              className={`px-2.5 py-1 rounded-full text-xs border transition ${f === s ? 'nav-item-active border-transparent' : 'bg-card border-border hover:bg-muted/50'}`}>{s}</button>
          ))}
        </div>
        <RefreshBtn onClick={reload} />
      </div>
      {!rows.length ? <Empty msg={bi('NFT не знайдено', 'No NFTs')} /> : (
        <TableWrap testid="nfts-table" headers={[
          { t: 'NFT' }, { t: 'Pool' }, { t: bi('Юніти', 'Units'), r: true }, { t: bi('Власник', 'Holder') },
          { t: bi('Гаманець', 'Wallet') }, { t: 'Token' }, { t: bi('Статус', 'Status') }]}>
          {rows.map((n) => (
            <tr key={n.id} data-testid={`nft-row-${n.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{n.id.slice(0, 14)}</td>
              <td className="px-3 py-2 text-[12px]">{n.pool_id}</td>
              <td className="px-3 py-2 text-right tabular-nums">{n.units}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{n.current_holder_user_id || '—'}</td>
              <td className="px-3 py-2 font-mono text-[11px]" title={n.current_wallet}>{short(n.current_wallet)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{n.token_id || '—'}</td>
              <td className="px-3 py-2">
                <span className="inline-flex items-center gap-1.5">
                  <Pill s={n.status} />
                  {n.frozen && <Lock className="w-3.5 h-3.5 text-amber-500" title="frozen" />}
                </span>
              </td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}

/* ── 4. OTC Deals ─────────────────────────────────────────────────────── */
function OtcTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/otc/deals');
  const [busy, setBusy] = useState('');
  const act = async (path, id) => {
    setBusy(id);
    try { await lumen.post(`/admin/otc/deals/${id}/${path}`, {}); await reload(); }
    catch (e) { alert(lumenError(e)); }
    finally { setBusy(''); }
  };
  const resolve = async (id, outcome) => {
    setBusy(id);
    try { await lumen.post(`/admin/otc/deals/${id}/resolve-dispute`, { outcome }); await reload(); }
    catch (e) { alert(lumenError(e)); }
    finally { setBusy(''); }
  };
  if (loading) return <Loading />;
  const rows = data?.deals || [];
  return (
    <div data-testid="otc-tab">
      <ErrBox msg={error} />
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        {data?.summary && (
          <div className="flex flex-wrap gap-1.5 text-xs">
            {Object.entries(data.summary).map(([k, v]) => (
              <span key={k} className="px-2.5 py-1 rounded-full bg-muted/50 border border-border">{k}: <b>{v}</b></span>
            ))}
          </div>
        )}
        <RefreshBtn onClick={reload} />
      </div>
      {!rows.length ? <Empty msg={bi('OTC-угод немає', 'No OTC deals')} /> : (
        <TableWrap testid="otc-deals-table" headers={[
          { t: 'Deal' }, { t: bi('Продавець', 'Seller') }, { t: bi('Покупець', 'Buyer') }, { t: bi('Сума', 'Amount'), r: true },
          { t: bi('Оплата', 'Payment') }, { t: bi('Статус', 'Status') }, { t: bi('Дії', 'Actions') }]}>
          {rows.map((d) => (
            <tr key={d.id} data-testid={`otc-deal-row-${d.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{d.id.slice(0, 14)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{(d.seller_user_id || '').slice(0, 12)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{(d.buyer_user_id || '').slice(0, 12)}</td>
              <td className="px-3 py-2 text-right tabular-nums font-semibold">{USD(d.price_usd)}</td>
              <td className="px-3 py-2"><Pill s={d.payment_status} /></td>
              <td className="px-3 py-2"><Pill s={d.status} /></td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1.5">
                  {d.payment_status === 'submitted' && d.status !== 'completed' && (
                    <ActBtn testid={`btn-confirm-payment-${d.id}`} disabled={busy === d.id} tone="emerald" icon={CircleDollarSign} label={bi('Оплата', 'Confirm pay')} onClick={() => act('confirm-payment', d.id)} />
                  )}
                  {d.status === 'nft_transfer_pending' && (
                    <ActBtn testid={`btn-confirm-transfer-${d.id}`} disabled={busy === d.id} tone="sky" icon={Send} label={bi('Transfer', 'Transfer')} onClick={() => act('confirm-nft-transfer', d.id)} />
                  )}
                  {!['completed', 'cancelled', 'disputed'].includes(d.status) && (
                    <>
                      <ActBtn testid={`btn-dispute-${d.id}`} disabled={busy === d.id} tone="amber" icon={AlertTriangle} label={bi('Спір', 'Dispute')} onClick={() => act('dispute', d.id)} />
                      <ActBtn testid={`btn-cancel-${d.id}`} disabled={busy === d.id} tone="rose" icon={XCircle} label={bi('Скас.', 'Cancel')} onClick={() => act('cancel', d.id)} />
                    </>
                  )}
                  {d.status === 'disputed' && (
                    <>
                      <ActBtn testid={`btn-resolve-buyer-${d.id}`} disabled={busy === d.id} tone="sky" icon={Send} label={bi('Покупцю', 'To buyer')} onClick={() => resolve(d.id, 'release_to_buyer')} />
                      <ActBtn testid={`btn-resolve-seller-${d.id}`} disabled={busy === d.id} tone="emerald" icon={Check} label={bi('Продавцю', 'Seller keeps')} onClick={() => resolve(d.id, 'refund_seller_keeps')} />
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}
const ActBtn = ({ icon: Icon, label, onClick, tone = 'neutral', disabled, testid }) => {
  const map = { neutral: 'border-border hover:bg-muted/50', emerald: 'border-emerald-200 text-emerald-700 hover:bg-emerald-50', sky: 'border-sky-200 text-sky-700 hover:bg-sky-50', amber: 'border-amber-200 text-amber-700 hover:bg-amber-50', rose: 'border-rose-200 text-rose-700 hover:bg-rose-50' };
  return (
    <button data-testid={testid} disabled={disabled} onClick={onClick}
      className={`px-2 py-1 rounded-lg border text-[11px] bg-card flex items-center gap-1 transition disabled:opacity-40 ${map[tone]}`}>
      <Icon className="w-3 h-3" /> {label}
    </button>
  );
};

/* ── 4b. Wallet Recoveries ────────────────────────────────────────────── */
function RecoveriesTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/web3/recoveries');
  const [busy, setBusy] = useState('');
  const [approveFor, setApproveFor] = useState(null);
  const [newAddr, setNewAddr] = useState('');
  const reject = async (id) => {
    setBusy(id);
    try { await lumen.post(`/admin/web3/recovery/${id}/reject`, { reason: 'rejected by reviewer' }); await reload(); }
    catch (e) { alert(lumenError(e)); } finally { setBusy(''); }
  };
  const approve = async (id) => {
    if (!newAddr || !newAddr.startsWith('0x')) { alert(bi('Введіть коректну адресу нового гаманця', 'Enter a valid new wallet address')); return; }
    setBusy(id);
    try { await lumen.post(`/admin/web3/recovery/${id}/approve`, { new_address: newAddr, chain: 'ethereum', note: 'KYC verified' }); setApproveFor(null); setNewAddr(''); await reload(); }
    catch (e) { alert(lumenError(e)); } finally { setBusy(''); }
  };
  if (loading) return <Loading />;
  const rows = data?.recoveries || [];
  const s = data?.summary || {};
  return (
    <div data-testid="recoveries-tab">
      <ErrBox msg={error} />
      <div className="rounded-2xl border border-sky-200 bg-sky-50/50 p-3 mb-4 text-xs text-sky-800 flex items-start gap-2">
        <KeyRound className="w-4 h-4 mt-0.5 shrink-0" />
        <span>{bi('Відновлення виконується ТІЛЬКИ після підтвердженого KYC. Старі гаманці відкликаються, новий верифікується, NFT переприв’язуються, створюється аудит-запис.',
                 'Recovery runs ONLY after approved KYC. Old wallets are revoked, the new one verified, NFTs reassigned, an audit record is written.')}</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex gap-1.5 text-xs">
          <span className="px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200">{bi('очікують', 'pending')}: <b>{s.pending || 0}</b></span>
          <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200">{bi('виконані', 'approved')}: <b>{s.approved || 0}</b></span>
          <span className="px-2.5 py-1 rounded-full bg-muted/50 border border-border">{bi('відхилені', 'rejected')}: <b>{s.rejected || 0}</b></span>
        </div>
        <RefreshBtn onClick={reload} />
      </div>
      {!rows.length ? <Empty msg={bi('Запитів на відновлення немає', 'No recovery requests')} /> : (
        <TableWrap testid="recoveries-table" headers={[
          { t: bi('Інвестор', 'Investor') }, { t: 'KYC' }, { t: bi('Причина', 'Reason') },
          { t: bi('Втрачений', 'Lost') }, { t: bi('Новий', 'New') }, { t: bi('Статус', 'Status') }, { t: bi('Дії', 'Actions') }]}>
          {rows.map((r) => (
            <tr key={r.id} data-testid={`recovery-row-${r.id}`} className="hover:bg-muted/20 align-top">
              <td className="px-3 py-2">
                <div className="text-[12px]">{r.user_name || r.user_email || '—'}</div>
                <div className="font-mono text-[10px] text-token-muted">{r.user_id}</div>
              </td>
              <td className="px-3 py-2">{r.kyc_ok ? <span className="status-badge badge-success" style={{ fontSize: 10 }}>approved</span> : <span className="status-badge badge-danger" style={{ fontSize: 10 }}>{r.kyc_status || 'none'}</span>}</td>
              <td className="px-3 py-2 text-[12px]">{r.reason}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{short(r.lost_address)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{short(r.new_address)}</td>
              <td className="px-3 py-2"><Pill s={r.status === 'approved' ? 'completed' : (r.status === 'rejected' ? 'cancelled' : 'payment_pending')} />{r.nfts_reassigned != null && <div className="text-[10px] text-token-muted mt-0.5">{r.nfts_reassigned} NFT</div>}</td>
              <td className="px-3 py-2">
                {r.status === 'pending' ? (
                  approveFor === r.id ? (
                    <div className="flex flex-col gap-1.5 min-w-[200px]">
                      <input data-testid={`recovery-newaddr-${r.id}`} value={newAddr} onChange={(e) => setNewAddr(e.target.value)} placeholder="0x… новий гаманець"
                        className="px-2 py-1 rounded-lg border border-border bg-app text-[11px] font-mono" />
                      <div className="flex gap-1.5">
                        <button data-testid={`recovery-approve-confirm-${r.id}`} disabled={busy === r.id || !r.kyc_ok} onClick={() => approve(r.id)}
                          className="px-2 py-1 rounded-lg border border-emerald-200 text-emerald-700 text-[11px] hover:bg-emerald-50 disabled:opacity-40 flex items-center gap-1" title={!r.kyc_ok ? bi('Потрібен KYC', 'KYC required') : ''}>
                          <CheckCircle2 className="w-3 h-3" /> {bi('Підтвердити', 'Approve')}
                        </button>
                        <button onClick={() => { setApproveFor(null); setNewAddr(''); }} className="px-2 py-1 rounded-lg border border-border text-[11px]">✕</button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-1.5">
                      <ActBtn testid={`recovery-approve-${r.id}`} disabled={busy === r.id} tone="emerald" icon={LifeBuoy} label={bi('Відновити', 'Recover')} onClick={() => setApproveFor(r.id)} />
                      <ActBtn testid={`recovery-reject-${r.id}`} disabled={busy === r.id} tone="rose" icon={XCircle} label={bi('Відхил.', 'Reject')} onClick={() => reject(r.id)} />
                    </div>
                  )
                ) : <span className="text-[11px] text-token-muted">—</span>}
              </td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}

/* ── 5. Transfer Queue ────────────────────────────────────────────────── */
function TransfersTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/nft-registry/transfers');
  if (loading) return <Loading />;
  const rows = data?.transfers || [];
  return (
    <div data-testid="transfers-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-4"><RefreshBtn onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Трансферів немає', 'No transfers')} /> : (
        <TableWrap testid="transfers-table" headers={[
          { t: bi('Час', 'Time') }, { t: 'Token' }, { t: bi('Від', 'From') }, { t: bi('До', 'To') },
          { t: bi('Джерело', 'Source') }, { t: 'Tx' }]}>
          {rows.map((t) => (
            <tr key={t.id} data-testid={`transfer-row-${t.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 text-[11px] text-token-muted whitespace-nowrap">{formatDateUk(t.created_at)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{t.token_id || '—'}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{t.from_user_id ? t.from_user_id.slice(0, 12) : short(t.from_wallet)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{t.to_user_id ? t.to_user_id.slice(0, 12) : short(t.to_wallet)}</td>
              <td className="px-3 py-2"><span className="status-badge badge-neutral" style={{ fontSize: 10 }}>{t.source || 'indexer'}</span></td>
              <td className="px-3 py-2 font-mono text-[11px] text-token-muted">{t.tx_hash || '—'}</td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}

/* ── 6. Snapshots ─────────────────────────────────────────────────────── */
function SnapshotsTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/nft-registry/snapshots');
  if (loading) return <Loading />;
  const rows = data?.snapshots || [];
  return (
    <div data-testid="snapshots-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-4"><RefreshBtn onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Снапшотів немає', 'No snapshots')} /> : (
        <TableWrap testid="snapshots-table" headers={[
          { t: bi('Дата', 'Date') }, { t: 'Pool' }, { t: 'Token' }, { t: bi('Власник', 'Holder') }, { t: bi('Юніти', 'Units'), r: true }]}>
          {rows.map((s) => (
            <tr key={s.id} data-testid={`snapshot-row-${s.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 text-[11px] text-token-muted whitespace-nowrap">{formatDateUk(s.snapshot_at)}</td>
              <td className="px-3 py-2 text-[12px]">{s.pool_id}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{s.token_id || '—'}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{s.holder_user_id || short(s.holder_wallet)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{s.units}</td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}

/* ── 7. Blocked Payouts ───────────────────────────────────────────────── */
function BlockedTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/web3/blocked-payouts');
  if (loading) return <Loading />;
  const rows = data?.blocked_payouts || [];
  return (
    <div data-testid="blocked-tab">
      <ErrBox msg={error} />
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="text-sm text-token-muted">
          {bi('Всього заблоковано', 'Total blocked')}: <b className="text-token-primary">{USD(data?.total_usd)}</b> · {data?.count || 0} {bi('записів', 'rows')}
        </div>
        <RefreshBtn onClick={reload} />
      </div>
      {!rows.length ? <Empty msg={bi('Заблокованих виплат немає 🎉', 'No blocked payouts 🎉')} /> : (
        <TableWrap testid="blocked-table" headers={[
          { t: 'NFT' }, { t: 'Pool' }, { t: bi('Гаманець', 'Wallet') }, { t: bi('Власник', 'Holder') },
          { t: bi('Сума', 'Amount'), r: true }, { t: bi('Причина', 'Reason') }]}>
          {rows.map((b) => (
            <tr key={b.id} data-testid={`blocked-row-${b.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 font-mono text-[11px]">{b.token_id || '—'}</td>
              <td className="px-3 py-2 text-[12px]">{b.pool_id}</td>
              <td className="px-3 py-2 font-mono text-[11px]" title={b.current_wallet}>{short(b.current_wallet)}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{b.current_holder_user_id || '—'}</td>
              <td className="px-3 py-2 text-right tabular-nums font-semibold text-rose-600">{USD(b.amount_usd)}</td>
              <td className="px-3 py-2"><span className="status-badge badge-danger" style={{ fontSize: 10 }}>{b.reason}</span></td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}

/* ── 8. Blockchain Events ─────────────────────────────────────────────── */
function EventsTab({ bi }) {
  const { data, loading, error, reload } = useApi('/admin/blockchain/events');
  if (loading) return <Loading />;
  const rows = data?.events || [];
  return (
    <div data-testid="events-tab">
      <ErrBox msg={error} />
      <div className="flex justify-end mb-4"><RefreshBtn onClick={reload} /></div>
      {!rows.length ? <Empty msg={bi('Подій немає', 'No events')} /> : (
        <TableWrap testid="events-table" headers={[
          { t: bi('Час', 'Time') }, { t: bi('Тип', 'Type') }, { t: bi('Мережа', 'Chain') }, { t: 'Token' }, { t: bi('Статус', 'Status') }, { t: bi('Джерело', 'Source') }]}>
          {rows.map((e) => (
            <tr key={e.id} data-testid={`event-row-${e.id}`} className="hover:bg-muted/20">
              <td className="px-3 py-2 text-[11px] text-token-muted whitespace-nowrap">{formatDateUk(e.received_at)}</td>
              <td className="px-3 py-2 text-[12px] font-medium">{e.event_type}</td>
              <td className="px-3 py-2 capitalize text-[12px]">{e.chain}</td>
              <td className="px-3 py-2 font-mono text-[11px]">{e.payload?.token_id || '—'}</td>
              <td className="px-3 py-2"><Pill s={e.status === 'processed' ? 'completed' : (e.status === 'failed' ? 'disputed' : 'reserved')} /></td>
              <td className="px-3 py-2"><span className="status-badge badge-neutral" style={{ fontSize: 10 }}>{e.source}</span></td>
            </tr>
          ))}
        </TableWrap>
      )}
    </div>
  );
}
