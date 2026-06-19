import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams, useLocation, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { runtime } from '@/runtime';
import {
  Eye, EyeOff, Loader2, ArrowLeft, ShieldCheck, Sparkles, Check, X,
  User, Briefcase, Crown, Shield, KeyRound, Smartphone, Clock, MapPin,
} from 'lucide-react';
import { GoogleLogin } from '@react-oauth/google';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import ForgotPasswordModal from '@/components/ForgotPasswordModal';
import PasswordStrengthMeter from '@/components/PasswordStrengthMeter';
import { getDeviceFingerprint, getDeviceLabel } from '@/lib/deviceFingerprint';

/**
 * Lumen — sign-in / sign-up for investors.
 *
 * - Animated showcase of real investment objects (two vertical marquee columns,
 *   data pulled live from /api/assets — admins change objects → animation updates).
 * - Quick demo access reduced to three compact icon buttons at the bottom.
 * - Gmail / Google sign-in (enabled via /api/auth/google/config).
 * - Full registration with confirm-password + live password policy checklist.
 * - Inline 2FA challenge modal (6-digit) when the account has 2FA enabled.
 */

// Fallback objects in case the assets API is empty (keeps the animation alive).
const FALLBACK_ASSETS = [
  { id: 'f1', title: 'Котеджне містечко «Вишневе»', location: 'Київська обл.', target_yield: 21.5, cover_url: 'https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1200&q=80' },
  { id: 'f2', title: 'Логістичний хаб «Бровари»', location: 'Бровари', target_yield: 16.8, cover_url: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1200&q=80' },
  { id: 'f3', title: 'Прибутковий будинок', location: 'Львів, центр', target_yield: 18.2, cover_url: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80' },
  { id: 'f4', title: 'Бізнес-центр «Поділ»', location: 'Київ', target_yield: 14.5, cover_url: 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80' },
  { id: 'f5', title: 'Ділянка під забудову', location: 'Одеса', target_yield: 27.0, cover_url: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80' },
  { id: 'f6', title: 'ТЦ «Магеллан»', location: 'Харків', target_yield: 15.3, cover_url: 'https://images.unsplash.com/photo-1519567241046-7f570eee3ce6?auto=format&fit=crop&w=1200&q=80' },
];

export default function UnifiedAuthPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, checkAuth, setUser } = useAuth();
  const [searchParams] = useSearchParams();

  const initialMode = (() => {
    const m = (searchParams.get('mode') || '').toLowerCase();
    if (m === 'signin' || m === 'register') return m;
    return 'signin';
  })();

  const [mode, setMode] = useState(initialMode);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [demoLoadingRole, setDemoLoadingRole] = useState(null);
  const [error, setError] = useState('');
  const [forgotOpen, setForgotOpen] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [demoEnabled, setDemoEnabled] = useState(true);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [assets, setAssets] = useState([]);
  const [form, setForm] = useState({ email: '', password: '', confirm: '', name: '' });
  const [twoFA, setTwoFA] = useState(null); // { challenge_token, email, method, ttl_seconds }

  const next = searchParams.get('next') || '';

  useEffect(() => {
    runtime.get('/api/auth/config')
      .then((r) => { const d = r?.data || r; if (d && typeof d.demo_auth_enabled === 'boolean') setDemoEnabled(d.demo_auth_enabled); })
      .catch(() => {});
    runtime.get('/api/auth/google/config')
      .then((r) => { const d = r?.data || r; setGoogleEnabled(!!d?.enabled); })
      .catch(() => setGoogleEnabled(false));
    runtime.get('/api/assets')
      .then((r) => {
        const d = r?.data || r;
        const list = Array.isArray(d) ? d : (d.assets || d.items || []);
        const clean = (list || []).filter((a) => a && a.cover_url).slice(0, 12);
        setAssets(clean.length ? clean : FALLBACK_ASSETS);
      })
      .catch(() => setAssets(FALLBACK_ASSETS));
  }, []);

  useEffect(() => {
    document.title = mode === 'register' ? 'Lumen · Реєстрація інвестора' : 'Lumen · Вхід у кабінет';
  }, [mode]);

  const updateField = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  const isRegister = mode === 'register';
  const passwordsMismatch = isRegister && form.confirm.length > 0 && form.password !== form.confirm;

  const destFor = (role) => {
    if (next) return next;
    return role === 'admin' ? '/admin/command-center'
      : role === 'manager' ? '/manager/dashboard'
      : role === 'operator' ? '/operator/dashboard'
      : '/investor/dashboard';
  };

  const submit = async (e) => {
    e?.preventDefault();
    setError('');
    if (isRegister) {
      if (!agreed) { setError('Щоб продовжити, прийміть Публічну оферту, Політику конфіденційності та Розкриття ризиків.'); return; }
      if (form.password !== form.confirm) { setError('Паролі не співпадають. Перевірте поле «Повторіть пароль».'); return; }
    }
    setLoading(true);
    try {
      if (isRegister) {
        await runtime.post('/api/auth/register', {
          email: form.email.trim(),
          password: form.password,
          name: form.name.trim() || form.email.split('@')[0],
          role: 'client',
        });
      }
      const u = await login(form.email.trim(), form.password);
      navigate(destFor(u?.role));
    } catch (err) {
      if (err?.requires_2fa) {
        setTwoFA({
          challenge_token: err.challenge_token,
          email: err.email,
          method: err.method,
          ttl_seconds: err.ttl_seconds,
        });
        setLoading(false);
        return;
      }
      const msg = err?.response?.data?.detail || err?.message || 'Не вдалось увійти. Перевірте дані та спробуйте ще раз.';
      setError(typeof msg === 'string' ? msg : 'Помилка авторизації');
    } finally {
      setLoading(false);
    }
  };

  const demoLogin = async (kind) => {
    setError('');
    setDemoLoadingRole(kind);
    try {
      const emailByKind = { admin: 'admin@atlas.dev', manager: 'manager@atlas.dev', investor: 'client@atlas.dev' };
      const routeByKind = { admin: '/admin/command-center', manager: '/manager/dashboard', investor: '/investor/dashboard' };
      const r = await runtime.post('/api/auth/quick', { email: emailByKind[kind] || emailByKind.investor });
      const data = r?.data || r;
      if (data?.user || data?.user_id || data?.session_token) {
        await checkAuth();
        navigate(routeByKind[kind] || routeByKind.investor);
      } else {
        setError('Демо-вхід тимчасово недоступний.');
      }
    } catch (_e) {
      setError('Демо-вхід тимчасово недоступний.');
    } finally {
      setDemoLoadingRole(null);
    }
  };

  const handleGoogle = async (credentialResponse) => {
    setLoading(true); setError('');
    try {
      const r = await runtime.post('/api/auth/google', { credential: credentialResponse.credential, role: 'client' });
      const data = r?.data || r;
      if (data) { await checkAuth(); navigate(destFor(data?.role || 'client')); }
    } catch (_e) {
      setError('Не вдалось увійти через Google. Спробуйте email + пароль.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col" data-testid="auth-page">
      <header className="px-6 lg:px-10 py-5 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2" data-testid="auth-back-home">
          <ArrowLeft className="w-4 h-4 text-muted-foreground" />
          <Logo height={36} />
        </Link>
        <ThemeToggle />
      </header>

      <div className="flex-1 grid lg:grid-cols-2 gap-0">
        {/* Left — animated showcase of real investment objects */}
        <AnimatedShowcase assets={assets} />

        {/* Right — form */}
        <main className="flex items-center justify-center px-6 py-10 lg:py-16">
          <div className="w-full max-w-md">
            <h1 className="text-3xl font-bold tracking-tight" data-testid="auth-title">
              {isRegister ? 'Створіть кабінет інвестора' : 'Увійдіть у кабінет'}
            </h1>
            <p className="mt-2 text-muted-foreground text-sm">
              {isRegister ? 'Безкоштовна реєстрація. KYC можна пройти пізніше.' : 'Раді бачити знову. Введіть свої дані.'}
            </p>

            <form onSubmit={submit} className="mt-6 space-y-3" data-testid="auth-form">
              {isRegister && (
                <Field label="Ваше ім'я" value={form.name} onChange={(v) => updateField('name', v)} placeholder="Іван Петренко" testid="name-input" />
              )}
              <Field label="Email" type="email" value={form.email} onChange={(v) => updateField('email', v)} placeholder="you@example.com" required testid="email-input" />
              <Field
                label="Пароль"
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={(v) => updateField('password', v)}
                placeholder="мінімум 8 символів"
                required
                testid="password-input"
                suffix={
                  <button type="button" onClick={() => setShowPassword((p) => !p)} className="text-muted-foreground hover:text-foreground transition" aria-label="Показати або сховати пароль">
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                }
              />

              {isRegister && (
                <>
                  <Field
                    label="Повторіть пароль"
                    type={showConfirm ? 'text' : 'password'}
                    value={form.confirm}
                    onChange={(v) => updateField('confirm', v)}
                    placeholder="введіть пароль ще раз"
                    required
                    testid="confirm-password-input"
                    error={passwordsMismatch}
                    suffix={
                      <button type="button" onClick={() => setShowConfirm((p) => !p)} className="text-muted-foreground hover:text-foreground transition" aria-label="Показати або сховати пароль">
                        {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    }
                  />
                  {form.confirm.length > 0 && (
                    <p className={`flex items-center gap-1.5 text-xs ${passwordsMismatch ? 'text-red-500' : 'text-[#2E5D4F]'}`} data-testid="confirm-match-hint">
                      {passwordsMismatch ? <X className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
                      {passwordsMismatch ? 'Паролі не співпадають' : 'Паролі співпадають'}
                    </p>
                  )}
                  <PasswordStrengthMeter password={form.password} />
                </>
              )}

              {error && (
                <div className="text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2" data-testid="auth-error">{error}</div>
              )}

              {!isRegister && (
                <div className="flex justify-end">
                  <button type="button" onClick={() => setForgotOpen(true)} className="text-xs text-[#2E5D4F] hover:underline">Забули пароль?</button>
                </div>
              )}

              {isRegister && (
                <label className="flex items-start gap-2.5 text-xs text-muted-foreground leading-relaxed cursor-pointer" data-testid="auth-consent">
                  <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5 w-4 h-4 rounded border-border accent-[#2E5D4F] shrink-0" data-testid="auth-consent-checkbox" />
                  <span>
                    Я прийняв(-ла){' '}
                    <Link to="/legal/offer" target="_blank" className="text-[#2E5D4F] hover:underline">Публічну оферту</Link>,{' '}
                    <Link to="/legal/privacy" target="_blank" className="text-[#2E5D4F] hover:underline">Політику конфіденційності</Link>{' '}
                    та <Link to="/legal/risk" target="_blank" className="text-[#2E5D4F] hover:underline">Розкриття ризиків</Link>.
                  </span>
                </label>
              )}

              <button
                type="submit"
                disabled={loading || (isRegister && (!agreed || passwordsMismatch))}
                className="w-full h-12 rounded-full bg-foreground text-background font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2"
                data-testid="auth-submit"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {isRegister ? 'Створити кабінет' : 'Увійти'}
              </button>
            </form>

            {googleEnabled && (
              <div className="mt-5" data-testid="auth-google">
                <div className="flex items-center gap-3 text-xs text-muted-foreground my-3">
                  <div className="flex-1 h-px bg-border" /><span>або</span><div className="flex-1 h-px bg-border" />
                </div>
                <div className="flex justify-center">
                  <GoogleLogin onSuccess={handleGoogle} onError={() => setError('Google вхід не вдався.')} text={isRegister ? 'signup_with' : 'signin_with'} locale="uk" width="320" />
                </div>
                <p className="mt-2 text-center text-[11px] text-muted-foreground">Швидкий вхід через Gmail — профіль можна дозаповнити пізніше.</p>
              </div>
            )}

            <p className="mt-7 text-sm text-muted-foreground text-center">
              {isRegister ? 'Вже маєте кабінет? ' : 'Новий тут? '}
              <button onClick={() => { setMode(isRegister ? 'signin' : 'register'); setError(''); }} className="text-[#2E5D4F] hover:underline font-medium" data-testid="auth-mode-toggle">
                {isRegister ? 'Увійти' : 'Створити кабінет'}
              </button>
            </p>

            {/* Compact demo access — three small icons at the bottom */}
            {demoEnabled && (
              <div className="mt-8 flex flex-col items-center gap-2.5" data-testid="auth-demo-icons">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Швидкий демо-вхід</span>
                <div className="flex items-center gap-3">
                  <DemoIcon kind="investor" Icon={User} label="Демо інвестор" loading={demoLoadingRole === 'investor'} onClick={() => demoLogin('investor')} />
                  <DemoIcon kind="manager" Icon={Briefcase} label="Демо менеджер" loading={demoLoadingRole === 'manager'} onClick={() => demoLogin('manager')} />
                  <DemoIcon kind="admin" Icon={Crown} label="Демо адмін" loading={demoLoadingRole === 'admin'} onClick={() => demoLogin('admin')} />
                </div>
              </div>
            )}

            <div className="mt-8 pt-6 border-t border-border flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="w-4 h-4 text-[#2E5D4F]" />
              <span>Захищене з'єднання. Ваші дані шифруються відповідно до GDPR і ЗУ «Про захист персональних даних».</span>
            </div>
          </div>
        </main>
      </div>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
      {twoFA && (
        <TwoFactorModal
          ctx={twoFA}
          onClose={() => setTwoFA(null)}
          onSuccess={(u) => { setUser(u); setTwoFA(null); navigate(destFor(u?.role)); }}
        />
      )}
    </div>
  );
}

/* ── Animated showcase (two vertical marquee columns of real objects) ─────── */
function AnimatedShowcase({ assets }) {
  const items = assets && assets.length ? assets : FALLBACK_ASSETS;
  const colA = items.filter((_, i) => i % 2 === 0);
  const colB = items.filter((_, i) => i % 2 === 1);
  const safeA = colA.length ? colA : items;
  const safeB = colB.length ? colB : items;

  return (
    <aside
      className="relative hidden lg:block overflow-hidden"
      style={{ background: 'linear-gradient(160deg, #0E2620 0%, #173B32 50%, #0A1B17 100%)' }}
      data-testid="auth-showcase"
    >
      {/* moving cards — two columns with different widths, equal card heights */}
      <div className="lumen-marquee absolute inset-0 grid grid-cols-[1.18fr_0.82fr] gap-4 p-6 lumen-marquee-mask opacity-95" aria-hidden>
        <MarqueeColumn items={safeA} dir="up" />
        <MarqueeColumn items={safeB} dir="down" />
      </div>

      {/* ambient gold glow */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(700px 480px at 22% 12%, rgba(229,201,138,0.12), transparent 62%)' }} />

      {/* bottom readable panel — blurs the moving cards behind the text */}
      <div className="absolute bottom-0 left-0 right-0 z-20 pointer-events-none">
        <div className="relative px-10 pb-9 pt-14">
          {/* gradient-blur scrim: fully blurred + dark near text, fading out upward */}
          <div
            className="absolute inset-0 backdrop-blur-md"
            style={{
              WebkitMaskImage: 'linear-gradient(to top, #000 62%, rgba(0,0,0,0.5) 84%, transparent 100%)',
              maskImage: 'linear-gradient(to top, #000 62%, rgba(0,0,0,0.5) 84%, transparent 100%)',
              background: 'linear-gradient(to top, rgba(6,18,15,0.94) 30%, rgba(6,18,15,0.6) 70%, transparent 100%)',
            }}
          />
          <div className="relative text-[#F4ECDA]">
            <h2 className="text-xl xl:text-2xl font-bold tracking-tight leading-snug max-w-sm">
              Інвестуйте в реальні об'єкти з прозорою структурою.
            </h2>
            <p className="mt-2.5 text-[#F4ECDA]/85 leading-relaxed max-w-sm text-[13px]">
              Кожен об'єкт оформлюється через окрему SPV-юрособу. Ваша частка — підписаний договір участі з реальними правами на потік доходу.
            </p>
            <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] max-w-sm">
              <Bullet text="SPV під кожен актив" />
              <Bullet text="Юридичні договори" />
              <Bullet text="Щомісячні виплати" />
            </ul>
            <div className="mt-5 inline-flex items-baseline gap-2 px-3.5 py-2 rounded-xl border border-white/10 bg-white/10">
              <span className="text-[10px] uppercase tracking-widest text-[#D4B675]">сер. доходність</span>
              <span className="text-lg font-bold">17,4% — 22%</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function MarqueeColumn({ items, dir }) {
  const doubled = [...items, ...items];
  return (
    <div className="relative overflow-hidden h-full">
      <div className={`flex flex-col gap-4 ${dir === 'up' ? 'lumen-col-up' : 'lumen-col-down'}`}>
        {doubled.map((a, i) => <ShowcaseCard key={`${a.id || 'a'}-${i}`} a={a} />)}
      </div>
    </div>
  );
}

const ShowcaseCard = ({ a }) => (
  <div className="rounded-2xl overflow-hidden border border-white/10 bg-white/5 shadow-xl">
    <div className="relative h-44">
      <img src={a.cover_url} alt={a.title} loading="lazy" className="w-full h-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-transparent" />
      {a.target_yield != null && (
        <span className="absolute top-2.5 right-2.5 rounded-lg bg-emerald-500 text-white text-[11px] font-bold px-2 py-0.5 shadow">
          {Number(a.target_yield).toFixed(1)}%
        </span>
      )}
      <div className="absolute bottom-2.5 left-3 right-3">
        <p className="text-white text-sm font-semibold leading-tight line-clamp-1">{a.title}</p>
        {a.location && (
          <p className="text-white/70 text-[11px] flex items-center gap-1 mt-0.5 line-clamp-1">
            <MapPin className="w-3 h-3 shrink-0" /> {a.location}
          </p>
        )}
      </div>
    </div>
  </div>
);

const Bullet = ({ text }) => (
  <li className="flex items-center gap-2">
    <Sparkles className="w-4 h-4 text-[#D4B675] shrink-0" /><span>{text}</span>
  </li>
);

const Field = ({ label, value, onChange, type = 'text', placeholder, required, testid, suffix, error }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</span>
    <div className="mt-1 relative">
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        data-testid={testid}
        className={`w-full h-12 px-4 pr-10 rounded-xl border bg-background focus:outline-none focus:ring-2 transition ${error ? 'border-red-400 focus:border-red-400 focus:ring-red-400/15' : 'border-border focus:border-[#2E5D4F] focus:ring-[#2E5D4F]/15'}`}
      />
      {suffix && <div className="absolute right-3 top-1/2 -translate-y-1/2">{suffix}</div>}
    </div>
  </label>
);

const DemoIcon = ({ kind, Icon, label, loading, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={loading}
    title={label}
    aria-label={label}
    data-testid={`demo-${kind}`}
    className="group relative flex h-11 w-11 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition hover:border-[#2E5D4F]/40 hover:text-[#2E5D4F] hover:bg-[#2E5D4F]/5 disabled:opacity-50"
  >
    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
    <span className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-[11px] font-medium text-background opacity-0 transition group-hover:opacity-100">
      {label}
    </span>
  </button>
);

/* ── Inline 2FA challenge modal (shown when login returns requires_2fa) ────── */
function TwoFactorModal({ ctx, onClose, onSuccess }) {
  const [tab, setTab] = useState('totp');
  const [code, setCode] = useState('');
  const [trust, setTrust] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(ctx.ttl_seconds || 300);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((v) => Math.max(0, v - 1)), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  const ttlLabel = secondsLeft > 0 ? `${Math.floor(secondsLeft / 60)}:${(secondsLeft % 60).toString().padStart(2, '0')}` : 'минув';

  const verify = async (e) => {
    e?.preventDefault();
    const cleaned = code.trim();
    if (!cleaned) { setError('Введіть код'); return; }
    setBusy(true); setError('');
    try {
      const r = await runtime.post('/api/auth/2fa/verify', {
        challenge_token: ctx.challenge_token,
        code: cleaned,
        device_fingerprint: getDeviceFingerprint(),
        trust_device: trust,
        device_label: getDeviceLabel(),
      });
      onSuccess(r?.data || r);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.response?.data?.message || 'Невірний код');
      setCode('');
      if (err?.response?.status === 410) setTimeout(onClose, 1500);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" data-testid="2fa-modal">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-card border border-border rounded-3xl shadow-2xl p-6">
        <div className="mx-auto w-14 h-14 rounded-full bg-[#2E5D4F]/10 border border-[#2E5D4F]/30 flex items-center justify-center">
          <Shield className="w-7 h-7 text-[#2E5D4F]" />
        </div>
        <h2 className="mt-4 text-xl font-bold text-center">Двофакторне підтвердження</h2>
        <p className="mt-1 text-center text-sm text-muted-foreground">
          Вхід у <span className="font-semibold text-foreground">{ctx.email || 'ваш акаунт'}</span>. Введіть {tab === 'totp' ? '6-значний код з додатка' : 'код відновлення'}.
        </p>

        <div className="mt-5 flex bg-muted rounded-full p-1 border border-border">
          <button type="button" data-testid="2fa-tab-totp" onClick={() => { setTab('totp'); setCode(''); setError(''); }}
            className={`flex-1 py-2 rounded-full text-sm font-semibold transition flex items-center justify-center gap-2 ${tab === 'totp' ? 'bg-[#2E5D4F]/15 text-[#2E5D4F]' : 'text-muted-foreground'}`}>
            <Smartphone className="w-3.5 h-3.5" /> Додаток
          </button>
          <button type="button" data-testid="2fa-tab-recovery" onClick={() => { setTab('recovery'); setCode(''); setError(''); }}
            className={`flex-1 py-2 rounded-full text-sm font-semibold transition flex items-center justify-center gap-2 ${tab === 'recovery' ? 'bg-[#2E5D4F]/15 text-[#2E5D4F]' : 'text-muted-foreground'}`}>
            <KeyRound className="w-3.5 h-3.5" /> Код відновлення
          </button>
        </div>

        <form onSubmit={verify} className="mt-5">
          {tab === 'totp' ? (
            <input
              data-testid="2fa-modal-input" autoFocus inputMode="numeric" pattern="[0-9]*" maxLength={6}
              value={code} onChange={(e) => { setCode(e.target.value.replace(/\D/g, '').slice(0, 6)); if (error) setError(''); }}
              placeholder="000000"
              className="w-full bg-background border border-border rounded-xl px-4 py-4 text-center text-3xl tracking-[0.5em] font-bold focus:outline-none focus:border-[#2E5D4F]"
            />
          ) : (
            <input
              data-testid="2fa-modal-recovery-input" autoFocus autoCapitalize="characters" maxLength={24}
              value={code} onChange={(e) => { setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 24)); if (error) setError(''); }}
              placeholder="ABCDE-12345"
              className="w-full bg-background border border-border rounded-xl px-4 py-4 text-center text-xl tracking-widest font-mono font-bold focus:outline-none focus:border-[#2E5D4F]"
            />
          )}

          {error && <div className="mt-3 text-sm text-red-500 text-center" data-testid="2fa-modal-error">{error}</div>}

          <label className="mt-4 flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" checked={trust} onChange={(e) => setTrust(e.target.checked)} className="mt-0.5 w-4 h-4 accent-[#2E5D4F]" />
            <span className="text-sm text-muted-foreground">
              <span className="text-foreground font-semibold">Довіряти цьому пристрою 30 днів</span><br />
              <span className="text-xs">Пропускати 2FA в цьому браузері. Можна відкликати в налаштуваннях.</span>
            </span>
          </label>

          <div className="mt-3 text-xs text-muted-foreground text-center flex items-center justify-center gap-1.5">
            <Clock className="w-3 h-3" /> Запит діє ще {ttlLabel}
          </div>

          <button type="submit" data-testid="2fa-modal-submit" disabled={busy || code.length < 4 || secondsLeft <= 0}
            className="mt-5 w-full h-12 rounded-full bg-[#2E5D4F] text-white font-semibold disabled:opacity-40 hover:opacity-90 transition flex items-center justify-center gap-2">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} Підтвердити і увійти
          </button>
          <button type="button" onClick={onClose} className="mt-2 w-full text-muted-foreground text-sm py-2 hover:text-foreground transition">
            Скасувати
          </button>
        </form>
      </div>
    </div>
  );
}
