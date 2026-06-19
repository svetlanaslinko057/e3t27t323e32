import { useEffect, useRef, useState } from 'react';
import { X, Send, ArrowRight, Building2, Calculator as CalcIcon, MessageCircle, UserPlus, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { lumen, formatUAH, formatPercent } from '@/lib/lumenApi';
import { useAuth } from '@/App';
import './EvaCompanion.css';

/**
 * Lumen Concierge — friendly investor-side helper.
 *
 *   ┌─ floating action button (FAB) → opens panel
 *   └─ panel with multiple flows:
 *      • greeting (avatar + 4 quick actions)
 *      • register (collect email + name → /api/auth/register)
 *      • calculate (sum, %, years → projected income)
 *      • browse (fetch /api/assets and surface top 3 open rounds)
 *      • ask (free-text + email → /api/public/contact-leads)
 *
 * Visual identity: bot-investor with laptop, sage-green palette.
 * Drawn inline as SVG (no external dependencies), animates idle.
 */
export default function EvaCompanion() {
  const navigate = useNavigate();
  const { user, checkAuth } = useAuth();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState('home');
  const [visible, setVisible] = useState(false);
  const seenRef = useRef(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 3500);
    return () => clearTimeout(t);
  }, []);

  const close = () => {
    setOpen(false);
    seenRef.current = true;
    setTimeout(() => setView('home'), 250);
  };

  const goToCabinet = () => {
    if (user) navigate('/investor/dashboard');
    else navigate('/auth?mode=register');
    close();
  };

  if (!visible) return null;

  return (
    <div className="lumen-bot-root" data-testid="lumen-concierge">
      {open ? (
        <div className="lumen-bot-panel" role="dialog" aria-label="Lumen Concierge">
          <PanelHeader
            view={view}
            onBack={view === 'home' ? null : () => setView('home')}
            onClose={close}
          />
          <div className="lumen-bot-body">
            {view === 'home' && <HomeView setView={setView} user={user} goToCabinet={goToCabinet} />}
            {view === 'register' && <RegisterView onDone={async () => { await checkAuth(); setView('done'); }} />}
            {view === 'calculate' && <CalculateView />}
            {view === 'browse' && <BrowseView />}
            {view === 'ask' && <AskView onDone={() => setView('done')} />}
            {view === 'done' && <DoneView onClose={close} navigate={navigate} setView={setView} />}
          </div>
        </div>
      ) : (
        <button
          className="lumen-bot-fab"
          onClick={() => setOpen(true)}
          aria-label="Відкрити Lumen Concierge"
          data-testid="lumen-concierge-open"
        >
          <BotAvatar size={24} />
          <span>Питання?</span>
        </button>
      )}
    </div>
  );
}

/* ─────────── Header ─────────── */

const PanelHeader = ({ view, onBack, onClose }) => {
  const titles = {
    home: 'Lumen Concierge',
    register: 'Створення кабінету',
    calculate: 'Калькулятор',
    browse: 'Активні раунди',
    ask: 'Питання консьєржу',
    done: 'Готово',
  };
  return (
    <div className="lumen-bot-head">
      <div className="flex items-center gap-2.5">
        {onBack ? (
          <button onClick={onBack} className="lumen-bot-back" aria-label="Назад">←</button>
        ) : (
          <BotAvatar size={28} idle />
        )}
        <div>
          <strong className="block leading-tight">{titles[view] || titles.home}</strong>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">онлайн</span>
        </div>
      </div>
      <button onClick={onClose} aria-label="Закрити" className="lumen-bot-close"><X className="w-4 h-4" /></button>
    </div>
  );
};

/* ─────────── HOME ─────────── */

const HomeView = ({ setView, user, goToCabinet }) => (
  <>
    <div className="lumen-bot-bubble">
      <p>Доброго дня. Я допоможу вам почати з Lumen за пару хвилин.</p>
      <p className="mt-2 text-muted-foreground text-[13px]">Оберіть, чим почати:</p>
    </div>
    <div className="lumen-bot-actions">
      {user ? (
        <Action icon={<ArrowRight className="w-4 h-4" />} label="Перейти у мій кабінет" onClick={goToCabinet} primary testid="bot-action-cabinet" />
      ) : (
        <Action icon={<UserPlus className="w-4 h-4" />} label="Створити кабінет інвестора" onClick={() => setView('register')} primary testid="bot-action-register" />
      )}
      <Action icon={<CalcIcon className="w-4 h-4" />} label="Розрахувати очікуваний дохід" onClick={() => setView('calculate')} testid="bot-action-calc" />
      <Action icon={<Building2 className="w-4 h-4" />} label="Показати активні раунди" onClick={() => setView('browse')} testid="bot-action-browse" />
      <Action icon={<MessageCircle className="w-4 h-4" />} label="Задати питання" onClick={() => setView('ask')} testid="bot-action-ask" />
    </div>
  </>
);

/* ─────────── REGISTER ─────────── */

const RegisterView = ({ onDone }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const valid = name && email && /\S+@\S+\.\S+/.test(email);

  const submit = async (e) => {
    e?.preventDefault();
    setLoading(true);
    setError('');
    try {
      // generate a temp password — user can set it later
      const tempPwd = `Lumen_${Math.random().toString(36).slice(2, 10)}_!a`;
      await lumen.post('/auth/register', {
        email: email.trim(),
        password: tempPwd,
        name: name.trim(),
        role: 'client',
      });
      // log in
      await lumen.post('/auth/login', { email: email.trim(), password: tempPwd });
      // optional: store phone as a profile note
      try {
        if (phone) await lumen.patch('/account/profile', { phone });
      } catch (_e) {}
      onDone?.();
    } catch (err) {
      const msg = err?.response?.data?.detail;
      setError(typeof msg === 'string' ? msg : 'Не вдалося створити кабінет. Можливо, email уже використовується.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="lumen-bot-bubble">
        <p>Без проблем. Заповніть три поля — я створю кабінет і одразу впущу вас усередину.</p>
      </div>
      <form onSubmit={submit} className="lumen-bot-form" data-testid="bot-register-form">
        <BotField label="Ваше ім'я" value={name} onChange={setName} placeholder="Іван Петренко" testid="bot-name" />
        <BotField label="Email" type="email" value={email} onChange={setEmail} placeholder="you@example.com" testid="bot-email" />
        <BotField label="Телефон (опційно)" value={phone} onChange={setPhone} placeholder="+380…" testid="bot-phone" />
        {error && <p className="lumen-bot-error">{error}</p>}
        <button type="submit" disabled={!valid || loading} className="lumen-bot-primary mt-2" data-testid="bot-register-submit">
          {loading ? 'Створюємо…' : 'Створити кабінет'} <ArrowRight className="w-3.5 h-3.5" />
        </button>
        <p className="text-[10px] text-muted-foreground mt-2 leading-relaxed">
          Безкоштовно. KYC ви проходите пізніше, перед першою інвестицією.
        </p>
      </form>
    </>
  );
};

/* ─────────── CALCULATE ─────────── */

const CalculateView = () => {
  const [amount, setAmount] = useState(300000);
  const [yieldPct, setYieldPct] = useState(18);
  const [years, setYears] = useState(3);

  const monthly = (amount * (yieldPct / 100)) / 12;
  const total = amount * Math.pow(1 + yieldPct / 100, years);
  const profit = total - amount;

  return (
    <>
      <div className="lumen-bot-bubble">
        <p>Покажу орієнтовну дохідність на ваших параметрах. Це не обіцянка, а калькулятор моделі.</p>
      </div>
      <div className="lumen-bot-form" data-testid="bot-calc">
        <BotSlider label="Сума" value={amount} onChange={setAmount} min={50000} max={3000000} step={10000} format={formatUAH} testid="bot-calc-amount" />
        <BotSlider label="Очікувана річна доходність" value={yieldPct} onChange={setYieldPct} min={10} max={26} step={0.5} format={(v) => `${v.toFixed(1).replace('.', ',')}%`} testid="bot-calc-yield" />
        <BotSlider label="Термін" value={years} onChange={setYears} min={1} max={6} step={1} format={(v) => `${v} ${v === 1 ? 'рік' : v < 5 ? 'роки' : 'років'}`} testid="bot-calc-years" />
      </div>
      <div className="lumen-bot-result" data-testid="bot-calc-result">
        <div>
          <span className="lumen-bot-result-label">Місячний потік</span>
          <span className="lumen-bot-result-value">{formatUAH(monthly)}</span>
        </div>
        <div>
          <span className="lumen-bot-result-label">Дохід за {years} р.</span>
          <span className="lumen-bot-result-value lumen-gradient-text">{formatUAH(profit)}</span>
        </div>
        <div>
          <span className="lumen-bot-result-label">На виході</span>
          <span className="lumen-bot-result-value">{formatUAH(total)}</span>
        </div>
      </div>
    </>
  );
};

/* ─────────── BROWSE ─────────── */

const BrowseView = () => {
  const [items, setItems] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    lumen.get('/assets', { params: { status: 'open', limit: 4 } })
      .then((r) => setItems(r.data?.items || []))
      .catch(() => setItems([]));
  }, []);

  return (
    <>
      <div className="lumen-bot-bubble">
        <p>Зараз відкрито декілька раундів. Ось топ за прогресом:</p>
      </div>
      {!items ? (
        <div className="lumen-bot-skel">
          {[1, 2, 3].map((i) => <div key={i} className="lumen-bot-skel-row" />)}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Зараз немає відкритих раундів. Зайдіть пізніше.</p>
      ) : (
        <div className="lumen-bot-list" data-testid="bot-browse-list">
          {items.map((a) => (
            <button key={a.id} className="lumen-bot-asset" onClick={() => { navigate('/auth?mode=register'); }}>
              <div className="lumen-bot-asset-img" style={a.cover_url ? { backgroundImage: `url(${a.cover_url})` } : undefined}>
                {!a.cover_url && <Building2 className="w-4 h-4 text-muted-foreground" />}
              </div>
              <div className="flex-1 text-left min-w-0">
                <p className="font-medium text-sm truncate">{a.title}</p>
                <p className="text-[11px] text-muted-foreground">{a.location} · {a.category_label}</p>
                <div className="flex items-center justify-between text-[11px] mt-1">
                  <span className="text-[#2E5D4F] font-semibold">{formatPercent(a.target_yield)}</span>
                  <span className="text-muted-foreground">від {formatUAH(a.min_ticket)}</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  );
};

/* ─────────── ASK ─────────── */

const AskView = ({ onDone }) => {
  const [msg, setMsg] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  const valid = msg.trim().length > 5 && /\S+@\S+\.\S+/.test(email);

  const submit = async () => {
    setLoading(true);
    try {
      await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/public/contact-leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: 'lumen_concierge_ask', message: msg, email, source: 'concierge' }),
      });
    } catch (_e) { /* still considered "submitted" — UX */ }
    setLoading(false);
    onDone?.();
  };

  return (
    <>
      <div className="lumen-bot-bubble">
        <p>Опишіть ваше питання — і email, на який вам зручно отримати відповідь.</p>
      </div>
      <div className="lumen-bot-form">
        <label className="lumen-bot-label">Ваше питання</label>
        <textarea
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          rows={3}
          placeholder="Напр. чи можна інвестувати через ФОП?"
          className="lumen-bot-textarea"
          data-testid="bot-ask-text"
        />
        <BotField label="Email для відповіді" type="email" value={email} onChange={setEmail} placeholder="you@example.com" testid="bot-ask-email" />
        <button onClick={submit} disabled={!valid || loading} className="lumen-bot-primary mt-2" data-testid="bot-ask-submit">
          {loading ? 'Надсилання…' : 'Надіслати'} <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </>
  );
};

/* ─────────── DONE ─────────── */

const DoneView = ({ onClose, navigate, setView }) => (
  <>
    <div className="lumen-bot-bubble" data-testid="bot-done">
      <p className="font-semibold">Готово.</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Ми обробили запит. Якщо це була реєстрація — кабінет уже доступний у меню.
      </p>
    </div>
    <div className="lumen-bot-actions mt-3">
      <Action icon={<ArrowRight className="w-4 h-4" />} label="Перейти у кабінет" onClick={() => { navigate('/investor/dashboard'); onClose(); }} primary />
      <Action icon={<Sparkles className="w-4 h-4" />} label="Повернутись у меню" onClick={() => setView('home')} />
    </div>
  </>
);

/* ─────────── shared ─────────── */

const Action = ({ icon, label, onClick, primary, testid }) => (
  <button
    onClick={onClick}
    className={`lumen-bot-action ${primary ? 'is-primary' : ''}`}
    data-testid={testid}
  >
    <span className="lumen-bot-action-icon">{icon}</span>
    <span className="flex-1 text-left">{label}</span>
    <ArrowRight className="w-3.5 h-3.5 opacity-50" />
  </button>
);

const BotField = ({ label, value, onChange, type = 'text', placeholder, testid }) => (
  <label className="block">
    <span className="lumen-bot-label">{label}</span>
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      data-testid={testid}
      className="lumen-bot-input"
    />
  </label>
);

const BotSlider = ({ label, value, onChange, min, max, step, format, testid }) => (
  <div>
    <div className="flex items-baseline justify-between">
      <span className="text-xs font-medium">{label}</span>
      <span className="font-mono font-semibold text-sm">{format(value)}</span>
    </div>
    <input
      type="range"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      min={min}
      max={max}
      step={step}
      data-testid={testid}
      className="lumen-bot-slider mt-2 w-full"
    />
  </div>
);

/* ─────────── BotAvatar SVG — investor robot with laptop ─────────── */

const BotAvatar = ({ size = 32, idle = false }) => (
  <span className={`lumen-bot-avatar ${idle ? 'is-idle' : ''}`} style={{ width: size, height: size }}>
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="bot-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3F7B66" />
          <stop offset="1" stopColor="#2E5D4F" />
        </linearGradient>
        <linearGradient id="bot-screen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F2DDAA" />
          <stop offset="1" stopColor="#C9A961" />
        </linearGradient>
      </defs>
      {/* head */}
      <rect x="11" y="6" width="18" height="14" rx="4" fill="url(#bot-body)" />
      <rect x="11" y="6" width="18" height="14" rx="4" stroke="#1E4A3D" strokeWidth="0.8" />
      {/* antenna */}
      <line x1="20" y1="6" x2="20" y2="2.5" stroke="#1E4A3D" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="20" cy="2" r="1.3" fill="#D4B675" />
      {/* eyes */}
      <circle cx="16.5" cy="13" r="1.6" fill="#F0EBDE" />
      <circle cx="23.5" cy="13" r="1.6" fill="#F0EBDE" />
      <circle cx="16.5" cy="13" r="0.7" fill="#1E4A3D" />
      <circle cx="23.5" cy="13" r="0.7" fill="#1E4A3D" />
      {/* mouth smile */}
      <path d="M 17 17 Q 20 18.5 23 17" stroke="#1E4A3D" strokeWidth="1" strokeLinecap="round" fill="none" />
      {/* laptop base */}
      <rect x="8" y="26" width="24" height="3" rx="0.6" fill="#1E4A3D" />
      {/* laptop screen */}
      <rect x="11" y="20" width="18" height="7" rx="1" fill="url(#bot-screen)" />
      {/* tiny chart line on screen */}
      <polyline points="13,25.5 16,23 19,24 22,21.5 27,22.5" stroke="#1E4A3D" strokeWidth="0.8" fill="none" strokeLinecap="round" />
    </svg>
  </span>
);
