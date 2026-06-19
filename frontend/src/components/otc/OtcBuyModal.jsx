import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { lumen, lumenError, formatUSD } from '@/lib/lumenApi';
import { usePublicWallet } from '@/contexts/PublicWalletContext';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';
import { saveClaim } from '@/lib/otcClaim';
import {
  X, Wallet, Banknote, ShieldCheck, CheckCircle2, ArrowRight, Loader2, Building2,
} from 'lucide-react';

/**
 * OTC purchase modal.
 *  - Wallet (MetaMask): connects an injected wallet (guest-ok) and creates a
 *    reservation via POST /public/otc/reserve. The claim_token is stored so the
 *    lot is auto-attached to the account after the visitor logs in.
 *  - Internal balance (USD / USDT): requires an authenticated investor; if the
 *    visitor is a guest we route them to register/login and return here.
 */
export default function OtcBuyModal({ listing, onClose }) {
  const { bi } = useLang();
  const { user } = useAuth();
  const wallet = usePublicWallet();
  const navigate = useNavigate();
  const [method, setMethod] = useState('wallet');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(null);

  const a = listing.asset || {};
  const price = listing.price_usd;
  const sharePct = listing.metrics?.share_percent ?? listing.ownership_percent;

  const reserve = (payload) => lumen.post('/public/otc/reserve', { listing_id: listing.id, ...payload }).then((r) => r.data);

  const finishReservation = async (data) => {
    saveClaim(data.claim_token, listing);
    let claimed = false;
    if (user) { try { await lumen.post('/investor/otc/claim', { claim_token: data.claim_token }); claimed = true; } catch { /* will retry on next auth */ } }
    setDone({ claim_token: data.claim_token, claimed });
  };

  const handleWallet = async () => {
    setError(''); setBusy(true);
    try {
      let addr = wallet.account;
      if (!addr) {
        const c = await wallet.connect();
        if (!c.ok) {
          setError(c.error === 'NO_WALLET'
            ? bi('Гаманець не знайдено. Встановіть MetaMask або Rabby та спробуйте знову.', 'No wallet found. Install MetaMask or Rabby and try again.')
            : bi('Не вдалося підключити гаманець.', 'Could not connect wallet.'));
          setBusy(false); return;
        }
        addr = c.address;
      }
      const data = await reserve({ payment_method: 'wallet', wallet_address: addr, email: user?.email, name: user?.name });
      await finishReservation(data);
    } catch (e) { setError(lumenError(e)); } finally { setBusy(false); }
  };

  const handleInternal = async () => {
    if (!user) {
      navigate(`/auth?mode=register&next=${encodeURIComponent('/otc/' + listing.id)}`);
      return;
    }
    setError(''); setBusy(true);
    try {
      const data = await reserve({ payment_method: 'internal', email: user.email, name: user.name });
      await finishReservation(data);
    } catch (e) { setError(lumenError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="otc-buy-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full sm:max-w-lg bg-card border border-border rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="font-semibold text-lg">{done ? bi('Готово', 'Done') : bi('Купівля частки', 'Buy a share')}</h3>
          <button onClick={onClose} data-testid="otc-buy-close" className="p-1.5 rounded-lg hover:bg-muted"><X className="w-5 h-5" /></button>
        </div>

        {/* asset summary */}
        <div className="flex items-center gap-3 px-5 py-4 bg-muted/30">
          <div className="w-14 h-14 rounded-md overflow-hidden bg-muted shrink-0 flex items-center justify-center">
            {a.cover_url ? <img src={a.cover_url} alt={a.title} className="w-full h-full object-cover" /> : <Building2 className="w-6 h-6 text-muted-foreground" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-sm truncate">{a.title}</p>
            <p className="text-xs text-muted-foreground">{bi('Частка', 'Share')} {Number(sharePct || 0).toFixed(1)}% · {bi('Ціна', 'Price')} {formatUSD(price)}</p>
          </div>
        </div>

        {done ? (
          <div className="p-6 text-center" data-testid="otc-buy-success">
            <div className="mx-auto w-14 h-14 rounded-full bg-emerald-100 dark:bg-emerald-950/40 flex items-center justify-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-600" />
            </div>
            {done.claimed ? (
              <>
                <h4 className="mt-4 text-lg font-semibold">{bi('Лот додано у ваш кабінет', 'Lot added to your cabinet')}</h4>
                <p className="mt-1 text-sm text-muted-foreground">{bi('Менеджер LUMEN зв’яжеться для фіналізації оплати та переказу частки.', 'A LUMEN manager will reach out to finalise payment and transfer the share.')}</p>
                <button onClick={() => navigate('/investor/otc?tab=reservations')} data-testid="otc-buy-go-cabinet"
                  className="mt-5 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 text-white font-medium hover:bg-emerald-700">
                  {bi('Перейти в кабінет', 'Go to cabinet')} <ArrowRight className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <h4 className="mt-4 text-lg font-semibold">{bi('Частку заброньовано!', 'Share reserved!')}</h4>
                <p className="mt-1 text-sm text-muted-foreground">{bi('Зареєструйтесь або увійдіть — лот автоматично з’явиться у вашому кабінеті.', 'Register or sign in — the lot will automatically appear in your cabinet.')}</p>
                <div className="mt-3 px-3 py-2 rounded-lg bg-muted/50 text-[11px] font-mono text-muted-foreground break-all">{done.claim_token}</div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button onClick={() => navigate('/auth?mode=register')} data-testid="otc-buy-register" className="px-4 py-2.5 rounded-xl bg-emerald-600 text-white font-medium hover:bg-emerald-700">{bi('Зареєструватись', 'Register')}</button>
                  <button onClick={() => navigate('/auth')} className="px-4 py-2.5 rounded-xl border border-border font-medium hover:bg-muted/60">{bi('Увійти', 'Sign in')}</button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="p-5">
            <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">{bi('Спосіб оплати', 'Payment method')}</p>
            <div className="grid grid-cols-2 gap-3">
              <MethodCard active={method === 'wallet'} onClick={() => setMethod('wallet')} icon={Wallet}
                title={bi('Гаманець', 'Wallet')} sub={bi('MetaMask / USDT', 'MetaMask / USDT')} testid="otc-method-wallet" />
              <MethodCard active={method === 'internal'} onClick={() => setMethod('internal')} icon={Banknote}
                title={bi('Баланс USD', 'USD balance')} sub={bi('внутрішній рахунок', 'internal account')} testid="otc-method-internal" />
            </div>

            <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">{bi('До сплати', 'Total due')}</span>
                <span className="text-2xl font-bold tabular-nums">{formatUSD(price)}</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                {bi('LUMEN виступає гарантом угоди (escrow).', 'LUMEN acts as the deal guarantor (escrow).')}
              </p>
            </div>

            {method === 'internal' && !user && (
              <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                {bi('Для оплати з внутрішнього балансу потрібна авторизація.', 'Authorization is required to pay from the internal balance.')}
              </p>
            )}
            {error && <div className="mt-3 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="otc-buy-error">{error}</div>}

            <button
              onClick={method === 'wallet' ? handleWallet : handleInternal}
              disabled={busy}
              data-testid="otc-buy-confirm"
              className="mt-5 w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 disabled:opacity-50"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              {method === 'wallet'
                ? (wallet.connected ? bi('Підтвердити купівлю', 'Confirm purchase') : bi('Підключити гаманець і купити', 'Connect wallet & buy'))
                : (user ? bi('Оплатити з балансу', 'Pay from balance') : bi('Увійти, щоб оплатити', 'Sign in to pay'))}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const MethodCard = ({ active, onClick, icon: Icon, title, sub, testid }) => (
  <button onClick={onClick} data-testid={testid}
    className={`flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition ${active ? 'border-emerald-500 bg-emerald-50/60 dark:bg-emerald-950/20 ring-1 ring-emerald-500/30' : 'border-border hover:bg-muted/40'}`}>
    <Icon className={`w-5 h-5 ${active ? 'text-emerald-600' : 'text-muted-foreground'}`} />
    <span className="font-semibold text-sm">{title}</span>
    <span className="text-[11px] text-muted-foreground">{sub}</span>
  </button>
);
