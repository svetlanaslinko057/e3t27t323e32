import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, Building2, Banknote, ShieldCheck, FileText, BarChart3, Sparkles,
  CheckCircle2, TrendingUp, Calendar, MapPin, Users, Lock, Layers, Quote,
  Store, LineChart, Award, Hammer, Target, Wrench, Map,
  Coins, Repeat, Wallet, Link2,
  Menu as MenuIcon, X, Globe, ChevronDown, ChevronLeft, ChevronRight, ArrowUpRight, Mail, Send, MessageCircle, Plus, Minus,
  Landmark, BadgeCheck,
} from 'lucide-react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import WalletConnectButton from '@/components/WalletConnectButton';
import PublicWalletButton from '@/components/otc/PublicWalletButton';
import SeoHead from '@/components/SeoHead';
import { useAuth } from '@/App';
import { useLang } from '@/contexts/LanguageContext';
import { useContactModal } from '@/contexts/ContactModalContext';
import { lumen, formatUAH, formatPercent, usdFromUah, UAH_PER_USD } from '@/lib/lumenApi';
import { AssetMiniScore } from '@/components/lumen/AssetIntelligence';
import MobileAppSection from '@/components/marketing/MobileAppSection';
import { StoreBadges } from '@/components/marketing/AppShowcase';
import './LandingPage.css';

/**
 * Lumen — багата посадкова сторінка інвестиційної платформи.
 *
 * Структура:
 *   • Sticky header з кнопкою CTA та live-індикатором
 *   • Hero з анімованими цифрами та live-портфелем
 *   • Live-лента "що сталось на платформі"
 *   • Великі статистичні плитки
 *   • Категорії активів (4 ринки)
 *   • "Як це працює" — 4 кроки з ілюстраціями
 *   • Калькулятор очікуваної дохідності
 *   • Активні раунди (live з API)
 *   • Lumen vs альтернативи (банк, валюта, акції)
 *   • Сегмент 2: захист інвестора (SPV, юридичні гарантії)
 *   • Команда / партнери
 *   • Соціальні докази (відгуки)
 *   • Press / медіа
 *   • Розширений FAQ
 *   • Risk disclosure
 *   • Big CTA
 *   • Footer з повним меню
 */
export default function LandingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [assets, setAssets] = useState([]);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    document.title = 'Lumen · RWA-платформа: цифрове володіння реальними активами';
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    lumen.get('/assets', { params: { limit: 6 } })
      .then((r) => setAssets(r.data?.items || []))
      .catch(() => setAssets([]));
  }, []);

  const goCabinet = () => {
    if (user) navigate(user.role === 'admin' ? '/admin/dashboard' : '/investor/dashboard');
    else navigate('/auth?mode=register');
  };

  return (
    <div className="min-h-screen bg-background text-foreground lumen-landing">
      <SeoHead path="/" emitOrganization />
      <Header scrolled={scrolled} user={user} />
      <Hero goCabinet={goCabinet} assets={assets} />
      <Ticker />
      <BigStats />
      <Categories />
      <HowItWorks />
      <Web3Layer />
      <Calculator />
      <FeaturedAssets assets={assets} />
      <Compare />
      <MarketContext />
      <ImpactLayer />
      <Protection />
      <MobileAppSection />
      <Team />
      <Testimonials />
      <Press />
      <FAQ />
      <RiskDisclosure />
      <FinalCTA goCabinet={goCabinet} />
      <Footer />
    </div>
  );
}

/* ─────────────────────────── HEADER ─────────────────────────── */

const NAV_LINKS = [
  { uk: 'Активи', en: 'Assets', cuk: 'Каталог об’єктів і відкриті раунди', cen: 'Asset catalog & open rounds', href: '#assets' },
  { uk: 'Як це працює', en: 'How it works', cuk: 'Від $1,000 до щомісячних виплат', cen: 'From $1,000 to monthly payouts', href: '#how' },
  { uk: 'Безпека та власність', en: 'Security & ownership', cuk: 'SPV-структура й цифровий сертифікат', cen: 'SPV structure & digital certificate', href: '#protect' },
  { uk: 'Вторинний OTC-ринок', en: 'Secondary OTC market', cuk: 'Торгівля частками 24/7', cen: 'Trade shares 24/7', to: '/otc' },
  { uk: 'Питання й відповіді', en: 'FAQ', cuk: 'Поширені запитання інвесторів', cen: 'Common investor questions', href: '#faq' },
  { uk: 'Мобільний застосунок', en: 'Mobile app', cuk: 'iOS та Android', cen: 'iOS & Android', to: '/app' },
];

const Header = ({ scrolled, user }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const { lang, setLang, bi } = useLang();

  return (
    <>
      <header
        className={`sticky top-0 z-40 transition-all duration-300 ${
          scrolled ? 'backdrop-blur-xl bg-background/80 border-b border-border' : 'bg-transparent'
        }`}
        data-testid="landing-header"
      >
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Left — branded MENU emblem button */}
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="lumen-menu-emblem group"
            data-testid="header-menu-btn"
            aria-label={bi('Відкрити меню', 'Open menu')}
          >
            <span className="lumen-menu-emblem-mark" aria-hidden>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
                <path d="M12 2c.6 3.7 1.7 4.8 5.4 5.4-3.7.6-4.8 1.7-5.4 5.4-.6-3.7-1.7-4.8-5.4-5.4C10.3 6.8 11.4 5.7 12 2Z" fill="currentColor"/>
                <path d="M18 13.2c.35 2.1 1 2.75 3.1 3.1-2.1.35-2.75 1-3.1 3.1-.35-2.1-1-2.75-3.1-3.1 2.1-.35 2.75-1 3.1-3.1Z" fill="currentColor" opacity="0.7"/>
              </svg>
            </span>
            <span className="hidden sm:inline lumen-menu-emblem-label">{bi('Меню', 'Menu')}</span>
          </button>

          {/* Center — logo */}
          <Link
            to="/"
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center"
            data-testid="header-logo"
          >
            <Logo height={30} />
          </Link>

          {/* Right — wallet (MetaMask) · language · theme · auth */}
          <div className="flex items-center gap-1.5 sm:gap-2">
            {user && ['investor', 'client'].includes(user.role) ? (
              <div className="hidden md:block"><WalletConnectButton compact /></div>
            ) : (
              <div className="hidden md:block"><PublicWalletButton compact /></div>
            )}
            <LangSwitch lang={lang} setLang={setLang} bi={bi} />
            <ThemeToggle />
            {user ? (
              <Link
                to={user.role === 'admin' ? '/admin/dashboard' : '/investor/dashboard'}
                className="lumen-btn-primary text-sm font-medium px-4 h-9"
                data-testid="header-cabinet"
              >
                {bi('Кабінет', 'Cabinet')}
              </Link>
            ) : (
              <Link
                to="/auth"
                className="lumen-btn-primary text-sm font-medium px-4 sm:px-5 h-9"
                data-testid="header-login"
              >
                {bi('Увійти', 'Sign in')}
              </Link>
            )}
          </div>
        </div>
      </header>

      <MenuOverlay open={menuOpen} onClose={() => setMenuOpen(false)} bi={bi} />
    </>
  );
};

/* Self-contained site header for reuse on sub-pages (OTC, etc.).
   Keeps the SAME header/logic as the landing page. */
export const SiteHeader = ({ solid = false }) => {
  const { user } = useAuth();
  const [scrolled, setScrolled] = useState(solid);
  useEffect(() => {
    if (solid) { setScrolled(true); return undefined; }
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [solid]);
  return <Header scrolled={scrolled} user={user} />;
};

/* Language switcher — UK / EN dropdown */
const LangSwitch = ({ lang, setLang, bi }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const OPTS = [
    { code: 'uk', short: 'UA', label: 'Українська' },
    { code: 'en', short: 'EN', label: 'English' },
  ];
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="lumen-lang-btn"
        data-testid="lang-switch"
        aria-label={bi('Змінити мову', 'Change language')}
      >
        <Globe className="w-4 h-4" />
        <span className="text-xs font-semibold uppercase tracking-wide">{lang === 'uk' ? 'UA' : 'EN'}</span>
        <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.25, 0.1, 0.25, 1] }}
            className="lumen-lang-menu"
            data-testid="lang-menu"
          >
            {OPTS.map((o) => (
              <button
                key={o.code}
                type="button"
                onClick={() => { setLang(o.code); setOpen(false); }}
                className={`lumen-lang-item ${lang === o.code ? 'is-active' : ''}`}
                data-testid={`lang-${o.code}`}
              >
                <span className="font-semibold">{o.short}</span>
                <span className="text-muted-foreground">{o.label}</span>
                {lang === o.code && <CheckCircle2 className="w-3.5 h-3.5 ml-auto text-[#2E5D4F]" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

/* Full-screen MENU overlay (slides in from left, Farm-Minerals style) */
const MenuOverlay = ({ open, onClose, bi }) => {
  const navigate = useNavigate();
  const { openContact } = useContactModal();

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const go = (item) => {
    onClose();
    if (item.to) { navigate(item.to); return; }
    if (item.href) {
      const el = document.querySelector(item.href);
      if (el) { setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 60); }
      else { navigate(`/${item.href}`); }
    }
  };

  const listV = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.18 } } };
  const itemV = {
    hidden: { opacity: 0, y: 26 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] } },
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Scrim — dims the page behind, page stays visible */}
          <motion.div
            className="lumen-menu-scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            onClick={onClose}
            data-testid="menu-scrim"
          />

          {/* Left drawer — slides in over part of the screen */}
          <motion.aside
            className="lumen-menu-drawer"
            data-testid="menu-overlay"
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ duration: 0.5, ease: [0.76, 0, 0.24, 1] }}
          >
            <div className="flex items-center justify-between">
              <button type="button" onClick={onClose} className="lumen-close-btn" data-testid="menu-close-btn">
                <X className="w-4 h-4" /> {bi('Закрити', 'Close')}
              </button>
              <img
                src={`${process.env.PUBLIC_URL || ''}/branding/lumen-light.v4.png`}
                alt="LUMEN"
                draggable={false}
                style={{ height: 22, width: 'auto' }}
              />
            </div>

            <motion.nav variants={listV} initial="hidden" animate="show" className="lumen-menu-nav">
              {NAV_LINKS.map((it, i) => (
                <motion.button
                  key={i}
                  variants={itemV}
                  type="button"
                  onClick={() => go(it)}
                  className="lumen-menu-link group"
                  data-testid={`menu-link-${i}`}
                >
                  <span className="lumen-menu-num">{String(i + 1).padStart(2, '0')}</span>
                  <span className="lumen-menu-link-text">
                    <span className="lumen-menu-link-title">{bi(it.uk, it.en)}</span>
                    <span className="lumen-menu-link-cap">{bi(it.cuk, it.cen)}</span>
                  </span>
                  <ArrowUpRight className="lumen-menu-link-arrow" />
                </motion.button>
              ))}
            </motion.nav>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.45, duration: 0.5 }}
              className="lumen-menu-footer"
            >
              <button
                type="button"
                onClick={() => { onClose(); openContact({ source: 'landing_menu' }); }}
                className="lumen-pill-cta"
                data-testid="menu-contact-cta"
              >
                <span className="lumen-pill-dot" /> {bi('Залишити заявку', 'Leave a request')} <span className="lumen-pill-dot" />
              </button>
              <div className="lumen-menu-contacts">
                <a href="mailto:hello@lumen.capital" className="lumen-menu-contact" data-testid="menu-email">
                  <Mail className="w-4 h-4" /> hello@lumen.capital
                </a>
                <a href="https://t.me/lumen_capital" target="_blank" rel="noreferrer" className="lumen-menu-contact" data-testid="menu-telegram">
                  <Send className="w-4 h-4" /> Telegram
                </a>
                <button
                  type="button"
                  onClick={() => { onClose(); openContact({ source: 'landing_menu_callback' }); }}
                  className="lumen-menu-contact"
                  data-testid="menu-callback"
                >
                  <MessageCircle className="w-4 h-4" /> {bi('Замовити дзвінок', 'Request a call')}
                </button>
              </div>
              <p className="lumen-menu-tag">LUMEN · {bi('Реальні активи. Цифрова власність.', 'Real assets. Digital ownership.')}</p>
            </motion.div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
};

/* ─────────────────────────── HERO ─────────────────────────── */

const Hero = ({ assets }) => (
  <section className="relative overflow-hidden">
    <div aria-hidden className="lumen-hero-bg" />
    <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-20 pb-24">
      <div className="grid lg:grid-cols-12 gap-10 items-center">
        <div className="lg:col-span-7">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#2E5D4F]/30 bg-[#2E5D4F]/5 text-xs uppercase tracking-widest text-[#2E5D4F] font-medium" data-testid="hero-eyebrow">
            <Sparkles className="w-3.5 h-3.5" /> Реальні активи · Цифрова власність · USD / USDT
          </div>
          <h1 className="mt-6 text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.02]">
            Інвестуйте в
            <br />
            <span className="lumen-gradient-text">реальні активи</span>
            <br />
            <span className="text-muted-foreground text-3xl md:text-4xl lg:text-5xl font-semibold">
              від&nbsp;$1,000.
            </span>
          </h1>
          <p className="mt-7 text-lg md:text-xl text-muted-foreground max-w-2xl leading-relaxed">
            Купуйте <strong className="text-foreground">частки в нерухомості та бізнес-активах</strong>, отримуйте дохід і продавайте частки на вторинному OTC-ринку. Право власності підтверджено цифровим сертифікатом. Усі розрахунки — в&nbsp;USD&nbsp;/&nbsp;USDT.
          </p>
          <div className="mt-5 inline-flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="hero-rwa-chip">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border"><ShieldCheck className="w-3.5 h-3.5 text-[#2E5D4F]" /> Цифровий сертифікат власності</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border"><Repeat className="w-3.5 h-3.5 text-[#2E5D4F]" /> Вторинний ринок 24/7</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card border border-border"><Link2 className="w-3.5 h-3.5 text-[#2E5D4F]" /> Powered by blockchain</span>
          </div>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <a href="#assets" className="lumen-btn-primary-lg group" data-testid="hero-cta-primary">
              Подивитись активи
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition" />
            </a>
            <a href="#how" className="lumen-btn-ghost-lg" data-testid="hero-cta-secondary">
              <Building2 className="w-4 h-4" /> Як це працює
            </a>
          </div>
          <div className="mt-10 grid grid-cols-3 gap-6 max-w-xl">
            <HeroStat value="22" label="активи в роботі" />
            <HeroStat value="$820K" label="залучено в раундах" />
            <HeroStat value="18.2%" label="середня дохідність" />
          </div>
        </div>

        <div className="lg:col-span-5 relative">
          <HeroAssetCards assets={assets} />
        </div>
      </div>
    </div>
  </section>
);

const HeroStat = ({ value, label }) => (
  <div>
    <p className="text-3xl font-bold tracking-tight">{value}</p>
    <p className="text-xs uppercase tracking-widest text-muted-foreground mt-1">{label}</p>
  </div>
);

const HeroAssetCards = ({ assets }) => {
  const list = (assets && assets.length ? assets : FALLBACK_ASSETS).slice(0, 3);
  return (
    <div className="space-y-3" data-testid="hero-asset-cards">
      <div className="flex items-center justify-between px-1">
        <span className="text-xs uppercase tracking-widest text-muted-foreground">Активи у відкритих раундах</span>
        <span className="px-2 py-0.5 rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F] uppercase tracking-widest text-[10px] font-semibold">live</span>
      </div>
      {list.map((a, i) => (
        <Link
          key={a.id || i}
          to={a.id && a.id.startsWith('asset-') ? `/objects/${a.id}` : '#assets'}
          className="lumen-hero-card flex items-center gap-4 p-3 transition-all hover:shadow-lg hover:-translate-y-0.5"
          data-testid="hero-asset-card"
        >
          <div
            className="w-20 h-16 rounded-[6px] bg-muted shrink-0 overflow-hidden flex items-center justify-center text-muted-foreground"
            style={a.cover_url ? { backgroundImage: `url(${a.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
          >
            {!a.cover_url && <Building2 className="w-6 h-6" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-sm leading-tight truncate">{a.title}</p>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5 truncate"><MapPin className="w-3 h-3 shrink-0" /> {a.location}</p>
            <p className="text-[11px] text-muted-foreground mt-1">від {formatUAH(a.min_ticket || 41000)}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-lg font-bold text-[#2E5D4F] leading-none">{formatPercent(a.target_yield || 18)}</p>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">річних</p>
          </div>
        </Link>
      ))}
      <div className="flex gap-2">
        <a href="#assets" className="lumen-btn-ghost flex-1 justify-center text-sm" data-testid="hero-cards-cta">
          Усі активи <ArrowRight className="w-4 h-4" />
        </a>
        <Link to="/otc" className="lumen-btn-ghost flex-1 justify-center text-sm" data-testid="hero-otc-cta">
          <Repeat className="w-4 h-4" /> OTC ринок
        </Link>
      </div>
    </div>
  );
};

const PortfolioCardPreview = ({ assets }) => (
  <div className="lumen-hero-card relative" data-testid="hero-portfolio-card">
    <div className="px-5 py-3 border-b border-border flex items-center justify-between text-xs">
      <span className="font-mono text-muted-foreground">lumen · кабінет інвестора</span>
      <span className="px-2 py-0.5 rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F] uppercase tracking-widest text-[10px] font-semibold">
        live demo
      </span>
    </div>
    <div className="p-6 space-y-5">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Загальний портфель</p>
        <p className="text-4xl font-bold mt-1">{formatUAH(2_465_000)}</p>
        <p className="text-sm text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
          <TrendingUp className="w-3.5 h-3.5" /> +17,4% за 12 місяців
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 pt-4 border-t border-border">
        <SmallStat label="Активи" value="4" />
        <SmallStat label="Раунди" value="7" />
        <SmallStat label="Виплати" value="23" />
      </div>
      <div className="pt-4 border-t border-border">
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Активні позиції</p>
        <div className="space-y-2">
          {(assets.slice(0, 3).length ? assets.slice(0, 3) : DEMO_POSITIONS).map((p, i) => (
            <div key={p.id || i} className="flex items-center justify-between text-sm">
              <span className="flex-1 truncate">{p.title}</span>
              <span className="text-[#2E5D4F] font-mono text-xs">+{formatPercent(p.target_yield || p.yield || 18)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="pt-4 border-t border-border bg-gradient-to-r from-[#2E5D4F]/8 to-transparent -mx-6 -mb-6 px-6 pb-5 rounded-b-3xl">
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">Найближча виплата</p>
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold">ЖК «Подільський» · раунд II</p>
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Calendar className="w-3 h-3" /> 12 грудня · дивіденд
            </p>
          </div>
          <span className="font-mono text-lg font-bold text-[#2E5D4F]">{formatUAH(48_200)}</span>
        </div>
      </div>
    </div>
  </div>
);

const SmallStat = ({ label, value }) => (
  <div>
    <p className="text-2xl font-bold">{value}</p>
    <p className="text-[10px] uppercase tracking-widest text-muted-foreground mt-0.5">{label}</p>
  </div>
);

const FloatingChip = ({ icon, text, tone, className = '' }) => (
  <div className={`hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold shadow-lg ${className} ${
    tone === 'success' ? 'bg-emerald-500 text-white' : 'bg-[#2E5D4F] text-white'
  }`} style={{ boxShadow: '0 8px 24px -8px rgba(0,0,0,0.3)' }}>
    {icon} {text}
  </div>
);

/* ─────────────────────────── TICKER ─────────────────────────── */

const Ticker = () => {
  const events = [
    'Інвестор оформив $6,000 у ЖК «Подільський»',
    'Дивіденд ТЦ «Лавр» виплачено · 62 інвестори',
    'Новий актив: Котеджне містечко «Вишневе» · 26 будинків',
    'Раунд закрито: Земля «Стоянка» зібрано 100%',
    'Звіт за листопад: середня дохідність 18.2%',
    'Логістичний хаб «Рівне-Захід» — 9 нових інвесторів',
  ];
  return (
    <section className="border-y border-border bg-card overflow-hidden">
      <div className="lumen-ticker flex items-center gap-12 py-4 whitespace-nowrap text-sm text-muted-foreground">
        {[...events, ...events, ...events].map((e, i) => (
          <span key={i} className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#2E5D4F]" /> {e}
          </span>
        ))}
      </div>
    </section>
  );
};

/* ─────────────────────────── BIG STATS ─────────────────────────── */

const BigStats = () => (
  <section className="py-20 border-b border-border" data-testid="big-stats">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
        <BigStat number="$820K" label="проінвестовано" hint="у відкритих раундах" />
        <BigStat number="180+" label="інвесторів" hint="у 12 країнах" />
        <BigStat number="$151K" label="виплачено дивідендів" hint="за реалізованими об'єктами" />
        <BigStat number="87" label="угод на OTC-ринку" hint="вторинний продаж часток" />
      </div>
    </div>
  </section>
);

const BigStat = ({ number, label, hint }) => (
  <div className="border-l-2 border-[#2E5D4F] pl-5">
    <p className="text-4xl md:text-5xl font-bold tracking-tight">{number}</p>
    <p className="mt-2 text-sm font-medium">{label}</p>
    <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>
  </div>
);

/* ─────────────────────────── CATEGORIES ─────────────────────────── */

const Categories = () => {
  const cats = [
    {
      Icon: Building2,
      title: 'Нерухомість',
      tagline: 'Готова оренда з місячним грошовим потоком.',
      yield: '13–19%',
      objects: 24,
      photo: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80',
      benefits: ['Орендний дохід щомісяця', 'Захист через окреме SPV', 'Швидкий вихід на OTC-ринку'],
    },
    {
      Icon: Map,
      title: 'Земля',
      tagline: 'Ділянки під забудову з потенціалом переоцінки.',
      yield: '18–30%',
      objects: 8,
      photo: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=1200&q=80',
      benefits: ['Зростання вартості ділянки', 'Низький поріг входу', 'Прозорий кадастровий статус'],
    },
    {
      Icon: Hammer,
      title: 'Будівництво',
      tagline: 'Девелоперські проєкти з фіксованими віхами.',
      yield: '19–25%',
      objects: 12,
      photo: 'https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=80',
      benefits: ['Дохід при здачі обʼєкта', 'Контроль етапів забудови', 'Найвища цільова дохідність'],
    },
    {
      Icon: Store,
      title: 'Комерція',
      tagline: 'ТЦ, логістика, склади та офіси з орендарями.',
      yield: '12–17%',
      objects: 14,
      photo: 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80',
      benefits: ['Довгострокові орендні угоди', 'Стабільний грошовий потік', 'Інституційні орендарі'],
    },
    {
      Icon: Wrench,
      title: 'Відновлення',
      tagline: 'Реконструкція обʼєктів у партнерстві з «єВідновлення».',
      yield: '20–28%',
      objects: 6,
      accent: true,
      photo: 'https://images.unsplash.com/photo-1486718448742-163732cd1544?auto=format&fit=crop&w=1200&q=80',
      benefits: ['Соціальний вплив + дохід', 'Державне співфінансування', 'Преміальна дохідність'],
    },
  ];
  const trackRef = useRef(null);
  const [active, setActive] = useState(0);

  const scrollToIndex = (i) => {
    const track = trackRef.current;
    if (!track) return;
    const clamped = Math.max(0, Math.min(cats.length - 1, i));
    const card = track.children[clamped];
    if (card) track.scrollTo({ left: card.offsetLeft - track.offsetLeft, behavior: 'smooth' });
    setActive(clamped);
  };
  const onScroll = () => {
    const track = trackRef.current;
    if (!track) return;
    let nearest = 0;
    let min = Infinity;
    Array.from(track.children).forEach((ch, i) => {
      const d = Math.abs(ch.offsetLeft - track.offsetLeft - track.scrollLeft);
      if (d < min) { min = d; nearest = i; }
    });
    setActive(nearest);
  };

  return (
    <section className="lumen-cat-section" id="categories">
      <div className="lumen-cat-inner">
        {/* Left panel — title, description, brand animation, unified controls */}
        <div className="lumen-cat-panel">
          <SectionEyebrow>чотири ринки + відновлення</SectionEyebrow>
          <h2 className="lumen-h2">Куди саме ви інвестуєте через Lumen</h2>
          <p className="lumen-section-sub !mt-3">
            Ми не змішуємо ринки в одному «фонді». Кожен актив — окремий обʼєкт із власною моделлю доходності, своїм SPV і прозорим балансом.
          </p>

          <div className="lumen-cat-brand">
            <motion.span
              className="lumen-cat-spark"
              animate={{ rotate: 360 }}
              transition={{ duration: 22, repeat: Infinity, ease: 'linear' }}
              aria-hidden
            >
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
                <path d="M12 2c.6 3.7 1.7 4.8 5.4 5.4-3.7.6-4.8 1.7-5.4 5.4-.6-3.7-1.7-4.8-5.4-5.4C10.3 6.8 11.4 5.7 12 2Z" fill="currentColor" />
                <path d="M18 13.2c.35 2.1 1 2.75 3.1 3.1-2.1.35-2.75 1-3.1 3.1-.35-2.1-1-2.75-3.1-3.1 2.1-.35 2.75-1 3.1-3.1Z" fill="currentColor" opacity="0.7" />
              </svg>
            </motion.span>
            <div>
              <p className="lumen-cat-brand-num">5 ринків · 64 обʼєкти</p>
              <p className="lumen-cat-brand-cap">Кожен — окреме SPV і прозорий баланс</p>
            </div>
          </div>
        </div>

        {/* Right — slider track + its own controls underneath */}
        <div className="lumen-cat-slider-col">
          <div ref={trackRef} onScroll={onScroll} className="lumen-cat-track" data-testid="categories-track">
          {cats.map((c, i) => {
            const Icon = c.Icon;
            return (
              <a
                key={c.title}
                href="#assets"
                data-testid={`category-card-${i}`}
                className={`lumen-cat-card group relative flex flex-col overflow-hidden rounded-2xl border bg-background transition-all duration-300 hover:-translate-y-1.5 hover:shadow-2xl ${c.accent ? 'border-[#C99B3D]/50 ring-1 ring-[#C99B3D]/20' : 'border-border'}`}
              >
                <div className="relative h-40 overflow-hidden">
                  <img
                    src={c.photo}
                    alt={c.title}
                    loading="lazy"
                    className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                    style={{ borderRadius: 0 }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-transparent" />
                  <div className="absolute left-4 top-4 flex h-10 w-10 items-center justify-center rounded-md bg-white/15 text-white backdrop-blur-md ring-1 ring-white/25">
                    <Icon className="w-5 h-5" />
                  </div>
                  {c.accent && (
                    <span className="absolute right-4 top-4 rounded-md bg-[#C99B3D] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white shadow">
                      нова лінійка
                    </span>
                  )}
                  <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between">
                    <h3 className="text-xl font-bold tracking-tight text-white drop-shadow">{c.title}</h3>
                    <div className="text-right">
                      <p className="text-[9px] uppercase tracking-widest text-white/70">дохідність</p>
                      <p className="text-lg font-extrabold leading-none text-white">{c.yield}</p>
                    </div>
                  </div>
                </div>
                <div className="flex flex-1 flex-col p-5">
                  <p className="text-sm font-medium text-foreground">{c.tagline}</p>
                  <ul className="mt-3 space-y-1.5">
                    {c.benefits.map((b) => (
                      <li key={b} className="flex items-start gap-2 text-[13px] text-muted-foreground">
                        <CheckCircle2 className={`mt-0.5 h-4 w-4 shrink-0 ${c.accent ? 'text-[#C99B3D]' : 'text-[#2E5D4F]'}`} />
                        {b}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-5 flex items-center justify-between border-t border-border pt-4">
                    <span className="text-xs font-semibold text-muted-foreground">{c.objects} обʼєктів у роботі</span>
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-[#2E5D4F] transition-transform group-hover:translate-x-0.5">
                      Дивитись <ArrowRight className="w-4 h-4" />
                    </span>
                  </div>
                </div>
              </a>
            );
          })}
          </div>

          {/* Unified controls under the slider */}
          <div className="lumen-cat-controls lumen-cat-controls--under lumen-cat-controls--right">
            <button
              type="button"
              className="lumen-slider-arrow"
              onClick={() => scrollToIndex(active - 1)}
              disabled={active === 0}
              data-testid="categories-prev"
              aria-label="Попередній"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2" data-testid="categories-dots">
              {cats.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => scrollToIndex(i)}
                  className={`lumen-slider-dot ${active === i ? 'is-active' : ''}`}
                  aria-label={`Слайд ${i + 1}`}
                />
              ))}
            </div>
            <button
              type="button"
              className="lumen-slider-arrow"
              onClick={() => scrollToIndex(active + 1)}
              disabled={active >= cats.length - 1}
              data-testid="categories-next"
              aria-label="Наступний"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

/* ─────────────────────────── HOW IT WORKS ─────────────────────────── */

const JOURNEY_STEPS = [
  { Icon: Building2, tuk: 'Обираєте актив', ten: 'Choose an asset', duk: 'Переглядаєте відкриті обʼєкти — кожен має власну економіку.', den: 'Browse open objects — each with its own economics.' },
  { Icon: Landmark, tuk: 'Інвестуєте: банк або USDT', ten: 'Invest: bank or USDT', duk: 'Оплата банком або USDT; підпис через ЕЦП.', den: 'Pay by bank or USDT; sign with a digital signature.', tag: 'BANK / USDT' },
  { Icon: BadgeCheck, tuk: 'Цифровий сертифікат', ten: 'Digital certificate', duk: 'NFT-сертифікат фіксує право власності on-chain.', den: 'An on-chain NFT certificate fixes your ownership.', tag: 'ON-CHAIN' },
  { Icon: Coins, tuk: 'Отримуєте дивіденди', ten: 'Receive dividends', duk: 'Дохід пропорційно частці — щомісяця або поквартально.', den: 'Income proportional to your share — monthly / quarterly.' },
  { Icon: Repeat, tuk: 'Продаєте частку', ten: 'Sell your share', duk: 'Вихід через вторинний OTC-ринок LUMEN будь-коли.', den: 'Exit via LUMEN\u2019s secondary OTC market anytime.' },
];

const HowItWorks = () => {
  const { bi } = useLang();
  const trackRef = useRef(null);
  const [active, setActive] = useState(0);

  const scrollToIndex = (i) => {
    const track = trackRef.current;
    if (!track) return;
    const clamped = Math.max(0, Math.min(JOURNEY_STEPS.length - 1, i));
    const card = track.children[clamped];
    if (card) track.scrollTo({ left: card.offsetLeft - track.offsetLeft, behavior: 'smooth' });
    setActive(clamped);
  };
  const onScroll = () => {
    const track = trackRef.current;
    if (!track) return;
    let nearest = 0;
    let min = Infinity;
    Array.from(track.children).forEach((ch, i) => {
      const d = Math.abs(ch.offsetLeft - track.offsetLeft - track.scrollLeft);
      if (d < min) { min = d; nearest = i; }
    });
    setActive(nearest);
  };

  return (
    <section id="how" className="lumen-journey" data-testid="investment-journey-section">
      <div className="lumen-journey__inner">
        {/* RIGHT (DOM first) — description panel */}
        <div className="lumen-journey__panel">
          <SectionEyebrow>як це працює</SectionEyebrow>
          <h2 className="lumen-h2">{bi('Шлях від реєстрації до першої виплати', 'From sign-up to your first payout')}</h2>
          <p className="lumen-section-sub !mt-3">
            {bi('Все онлайн. Прозоро, юридично коректно, у вашому темпі — від вибору обʼєкта до виплат.', 'All online. Transparent, legally sound, at your pace — from picking an object to payouts.')}
          </p>
          <span className="lumen-journey__badge" data-testid="investment-journey-badge">
            <Sparkles className="w-3.5 h-3.5 text-[#C9A961]" />
            {bi('5 кроків · від $1,000 · виплати в USD / USDT', '5 steps · from $1,000 · payouts in USD / USDT')}
          </span>

          <div className="lumen-cat-brand">
            <motion.span
              className="lumen-cat-spark"
              animate={{ rotate: 360 }}
              transition={{ duration: 22, repeat: Infinity, ease: 'linear' }}
              aria-hidden
            >
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
                <path d="M12 2c.6 3.7 1.7 4.8 5.4 5.4-3.7.6-4.8 1.7-5.4 5.4-.6-3.7-1.7-4.8-5.4-5.4C10.3 6.8 11.4 5.7 12 2Z" fill="currentColor" />
                <path d="M18 13.2c.35 2.1 1 2.75 3.1 3.1-2.1.35-2.75 1-3.1 3.1-.35-2.1-1-2.75-3.1-3.1 2.1-.35 2.75-1 3.1-3.1Z" fill="currentColor" opacity="0.7" />
              </svg>
            </motion.span>
            <div>
              <p className="lumen-cat-brand-num">{bi('Повністю онлайн', 'Fully online')}</p>
              <p className="lumen-cat-brand-cap">{bi('ЕЦП · спецрахунок · NFT-сертифікат', 'e-signature · escrow · NFT certificate')}</p>
            </div>
          </div>
        </div>

        {/* LEFT (visually) — slider track + controls underneath */}
        <div className="lumen-journey__slidercol">
          <div ref={trackRef} onScroll={onScroll} className="lumen-journey__track" data-testid="investment-journey-track">
            {JOURNEY_STEPS.map((s, i) => {
              const Icon = s.Icon;
              return (
                <motion.article
                  key={i}
                  role="listitem"
                  data-testid={`investment-journey-step-card-${i}`}
                  className="journey-card"
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 0.5, delay: i * 0.07, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="journey-card__top">
                    <span className="journey-card__num">[ <strong>{String(i + 1).padStart(2, '0')}</strong> ]</span>
                    {s.tag && <span className="journey-card__tag">{s.tag}</span>}
                  </div>
                  <span className="journey-card__iconWrap">
                    <Icon className="journey-card__icon" width={18} height={18} />
                  </span>
                  <h3 className="journey-card__title" data-testid={`investment-journey-step-title-${i}`}>{bi(s.tuk, s.ten)}</h3>
                  <p className="journey-card__desc" data-testid={`investment-journey-step-desc-${i}`}>{bi(s.duk, s.den)}</p>
                  <span className="journey-card__cue">
                    {i < JOURNEY_STEPS.length - 1 ? bi('далі', 'next') : bi('готово', 'done')}
                    <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                  <span className="journey-card__underline" />
                </motion.article>
              );
            })}
          </div>

          {/* Controls under the slider */}
          <div className="lumen-cat-controls lumen-cat-controls--under" data-testid="investment-journey-progress-dots">
            <button type="button" className="lumen-slider-arrow" onClick={() => scrollToIndex(active - 1)} disabled={active === 0} data-testid="journey-prev" aria-label="Попередній">
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2">
              {JOURNEY_STEPS.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => scrollToIndex(i)}
                  className={`lumen-slider-dot ${active === i ? 'is-active' : ''}`}
                  data-testid={`investment-journey-progress-dot-${i}`}
                  aria-label={`Крок ${i + 1}`}
                />
              ))}
            </div>
            <button type="button" className="lumen-slider-arrow" onClick={() => scrollToIndex(active + 1)} disabled={active >= JOURNEY_STEPS.length - 1} data-testid="journey-next" aria-label="Наступний">
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

/* ─────────────────────────── WEB3 / DIGITAL OWNERSHIP ─────────────────────────── */

const Web3Layer = () => (
  <section id="web3" className="py-24 border-b border-border bg-card" data-testid="landing-web3">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 lg:items-center">
        {/* left — narrative + entry options */}
        <div>
          <SectionEyebrow>цифрова власність</SectionEyebrow>
          <h2 className="lumen-h2">Реальні активи + прозорість блокчейну</h2>
          <p className="lumen-section-sub">
            LUMEN поєднує юридичне володіння через SPV із цифровим сертифікатом у блокчейні.
            Ви володієте часткою реального обʼєкта — а технологія робить це право прозорим,
            захищеним і ліквідним.
          </p>
          <div className="mt-8 space-y-3">
            <Web3Badge icon={<Wallet className="w-4 h-4" />} t="Гаманець MetaMask / Rabby" s="Підключіть будь-коли — або інвестуйте через банк без гаманця" />
            <Web3Badge icon={<Repeat className="w-4 h-4" />} t="Вторинний OTC-ринок" s="Продайте частку іншому інвестору до завершення циклу" />
            <Web3Badge icon={<Coins className="w-4 h-4" />} t="USDT та банківський переказ" s="Обирайте зручний спосіб входу в актив" />
          </div>
        </div>

        {/* right — feature panel (distinct ledger-style card) */}
        <div className="relative rounded-3xl border border-border bg-background p-2 shadow-xl">
          <div className="rounded-[1.25rem] bg-gradient-to-br from-[#2E5D4F] to-[#25493e] p-6">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-white/70">Сертифікат власності</span>
              <span className="rounded-full bg-[#C99B3D] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">On-chain</span>
            </div>
            <div className="mt-5 divide-y divide-white/10">
              {WEB3_FEATURES.map((f) => (
                <div key={f.title} className="flex gap-4 py-4 first:pt-0 last:pb-0">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/10 text-white [&>svg]:w-5 [&>svg]:h-5">
                    {f.icon}
                  </div>
                  <div>
                    <h3 className="text-[15px] font-semibold text-white">{f.title}</h3>
                    <p className="mt-1 text-[13px] leading-relaxed text-white/70">{f.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
);

const WEB3_FEATURES = [
  { icon: <ShieldCheck className="w-6 h-6" />, title: 'Прозора власність', text: 'Цифровий сертифікат підтверджує ваше право володіння часткою — незмінно й перевірювано в блокчейні.' },
  { icon: <Repeat className="w-6 h-6" />, title: 'Вторинний ринок', text: 'Не чекаєте кінця циклу: продаєте частку іншому інвестору на OTC-ринку LUMEN під гарантією платформи.' },
  { icon: <Coins className="w-6 h-6" />, title: 'USDT або банк', text: 'Інвестуйте криптовалютою чи звичайним банківським переказом — обидва шляхи ведуть до однієї власності.' },
  { icon: <Banknote className="w-6 h-6" />, title: 'Виплати дивідендів', text: 'Регулярний дохід від активу нараховується власнику сертифіката автоматично та пропорційно частці.' },
];

const Web3Badge = ({ icon, t, s }) => (
  <div className="flex items-start gap-3 rounded-2xl border border-border bg-background p-4">
    <div className="w-9 h-9 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center shrink-0">{icon}</div>
    <div>
      <p className="font-medium text-sm">{t}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{s}</p>
    </div>
  </div>
);

/* ─────────────────────────── CALCULATOR ───────────────────────────
 *
 * Реальна модель колективної інвестиції в конкретний об'єкт.
 *
 * Кожен актив має фіксовану економіку, яку задає Lumen під час
 * структурування угоди:
 *   • round_target   — обсяг пулу
 *   • target_yield   — цільова річна IRR для інвестора
 *   • horizon_months — горизонт інвестиції
 *   • min_ticket     — мінімум входу
 *   • category       — тип активу, визначає модель потоку
 *
 * Модель потоку (на основі category):
 *   • real_estate / commercial → mixed: ~60% рента + ~40% переоцінка
 *   • restoration              → mixed: ~50% рента + ~50% переоцінка
 *   • construction / land      → capital_gain: 0% рента, 100% при виході
 *
 * Розрахунок для інвестора:
 *   share_pct      = invest_amount / round_target
 *   gross_rental   = invest_amount * (target_yield * rental_share)
 *   monthly_cash   = gross_rental / 12               (для rental частки)
 *   appreciation   = invest_amount * (1 + cap_growth)^years − invest_amount
 *   total_gross    = invest_amount + (gross_rental * years) + appreciation
 *   pdfo+vz        = profit_gross * 19.5%   (укр. податок з дивідендів)
 *   irr_annualised = (total_gross / invest_amount)^(1/years) − 1
 *
 * Користувач:
 *   • обирає актив зі списку відкритих раундів
 *   • вводить суму (з валідацією min_ticket / round_target)
 *   • бачить чесну розбивку: частка в пулі, грошовий потік, переоцінка,
 *     валовий і чистий прибуток, IRR, три сценарії.
 */

const RENTAL_SHARE_BY_CATEGORY = {
  real_estate: 0.6,
  commercial:  0.6,
  restoration: 0.5,
  construction: 0,
  land: 0,
};

const computeProjection = (asset, amount) => {
  const cat = asset.category;
  const irr = (asset.target_yield || 15) / 100;
  const horizonM = asset.horizon_months || 24;
  const years = horizonM / 12;
  const rentalShare = RENTAL_SHARE_BY_CATEGORY[cat] ?? 0.4;
  const capShare = 1 - rentalShare;
  const sharePct = asset.round_target ? amount / asset.round_target : 0;

  // annual rental cash distribution proportional to IRR's rental component
  const annualCash = amount * (irr * rentalShare);
  const monthlyCash = annualCash / 12;

  // appreciation compounds at cap_rate for non-rental component
  // We solve: total = amount * (1 + irr)^years → total_gross = amount * (1+irr)^years
  // Then split: rental_total = amount * irr * rentalShare * years (linear)
  // appreciation_value = total_gross − amount − rental_total
  const totalGross = amount * Math.pow(1 + irr, years);
  const rentalTotal = annualCash * years;
  const appreciation = totalGross - amount - rentalTotal;

  const profitGross = totalGross - amount;
  const taxRate = 0.195; // 18% PDFO + 1.5% військового збору
  const tax = profitGross * taxRate;
  const profitNet = profitGross - tax;
  const totalNet = amount + profitNet;
  const irrEffective = years > 0 ? Math.pow(totalNet / amount, 1 / years) - 1 : 0;

  // three scenarios: conservative −20%, base, optimistic +15% on yield
  const scenario = (delta) => {
    const irrScn = irr * (1 + delta);
    const totalScn = amount * Math.pow(1 + irrScn, years);
    return totalScn - amount;
  };

  return {
    sharePct,
    monthlyCash,
    annualCash,
    rentalTotal,
    appreciation,
    totalGross,
    profitGross,
    tax,
    profitNet,
    totalNet,
    irrEffective,
    years,
    rentalShare,
    capShare,
    horizonM,
    conservative: scenario(-0.20),
    base: profitGross,
    optimistic: scenario(0.15),
  };
};

const Calculator = () => {
  const [allAssets, setAllAssets] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [amount, setAmount] = useState(4000); // USD

  useEffect(() => {
    lumen.get('/assets', { params: { status: 'open' } })
      .then((r) => {
        const items = r.data?.items || [];
        setAllAssets(items);
        if (items[0]) {
          setSelectedId(items[0].id);
          setAmount(Math.max(Math.round(usdFromUah(items[0].min_ticket || 50000)), 1000));
        }
      })
      .catch(() => setAllAssets(FALLBACK_ASSETS));
  }, []);

  const selected = allAssets.find((a) => a.id === selectedId) || allAssets[0];
  const minUsd = selected ? usdFromUah(selected.min_ticket || 0) : 0;
  const maxUsd = selected ? usdFromUah(selected.round_target || 1e12) : 1e12;
  const isValid = selected && amount >= minUsd && amount <= maxUsd;
  // computeProjection works in the stored (UAH) base; convert the USD ticket back
  // to base so the percentage math is identical, then display converts to USD.
  const projection = selected && isValid ? computeProjection(selected, amount * UAH_PER_USD) : null;

  return (
    <section id="calculator" className="py-24 border-b border-border bg-card">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <SectionEyebrow>модель частки в активі</SectionEyebrow>
        <h2 className="lumen-h2">Прорахуйте свою позицію в конкретному об'єкті</h2>
        <p className="lumen-section-sub">
          Ви не інвестуєте «в платформу під 18%». Ви купуєте частку у пулі, що фінансує реальний об'єкт. Дохід — це ваша частка від реальної економіки активу: оренда + переоцінка. Цифри взяті безпосередньо з моделей наших активів.
        </p>

        <div className="mt-12 grid lg:grid-cols-5 gap-6 items-start">
          {/* ── INPUTS ── */}
          <div className="lg:col-span-2 space-y-5" data-testid="calculator-inputs">
            <div>
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Оберіть об'єкт</span>
              <AssetSelect
                value={selectedId}
                onChange={(id) => {
                  setSelectedId(id);
                  const a = allAssets.find((x) => x.id === id);
                  if (a && amount < usdFromUah(a.min_ticket || 0)) setAmount(Math.round(usdFromUah(a.min_ticket)));
                }}
                options={allAssets}
              />
            </div>

            {selected && (
              <div className="rounded-2xl border border-border bg-background p-4 text-sm space-y-2">
                <Row label="Категорія" value={selected.category_label || selected.category} />
                <Row label="Локація" value={selected.location} />
                <Row label="Горизонт" value={`${selected.horizon_months || 24} міс.`} />
                <Row label="Цільова IRR (валова)" value={formatPercent(selected.target_yield)} accent />
                <Row label="Об'єм пулу" value={formatUAH(selected.round_target)} />
                <Row label="Мінімальна частка" value={formatUAH(selected.min_ticket)} />
              </div>
            )}

            <div>
              <label className="block">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Ваш внесок, USD</span>
                <div className="mt-2 relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground font-semibold">$</span>
                  <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(Number(e.target.value))}
                    className="w-full h-12 pl-8 pr-16 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] font-mono font-semibold text-lg"
                    data-testid="calc-amount"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">USDT</span>
                </div>
              </label>
              {selected && amount < minUsd && (
                <p className="mt-2 text-xs text-red-500">Мінімальна частка цього активу — {formatUAH(selected.min_ticket)}</p>
              )}
              {selected && amount > maxUsd && (
                <p className="mt-2 text-xs text-red-500">Об'єм пулу — {formatUAH(selected.round_target)}. Виберіть менший внесок.</p>
              )}
            </div>
          </div>

          {/* ── PROJECTION ── */}
          <div className="lg:col-span-3 lumen-card-elevated" data-testid="calc-projection">
            {!projection ? (
              <div className="text-center py-10 text-muted-foreground text-sm">Завантажуємо моделі активів…</div>
            ) : (
              <>
                <div className="grid sm:grid-cols-3 gap-4">
                  <BigMetric label="Ваша частка у пулі" value={`${(projection.sharePct * 100).toFixed(2)}%`.replace('.', ',')} />
                  <BigMetric label="Чистий прибуток" value={formatUAH(projection.profitNet)} accent />
                  <BigMetric label="Ефективна IRR (нетто)" value={formatPercent(projection.irrEffective * 100)} />
                </div>

                <div className="mt-6 pt-6 border-t border-border">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Розкладка по виплатах</p>
                  <div className="space-y-2.5 text-sm">
                    {projection.rentalShare > 0 && (
                      <>
                        <FlowLine label="Місячна виплата (оренда, ваша частка)" value={formatUAH(projection.monthlyCash)} muted />
                        <FlowLine label={`Сумарна оренда за ${projection.horizonM} міс.`} value={formatUAH(projection.rentalTotal)} />
                      </>
                    )}
                    {projection.capShare > 0 && (
                      <FlowLine label={`Переоцінка частки при виході (${(projection.capShare * 100).toFixed(0)}%)`} value={formatUAH(projection.appreciation)} />
                    )}
                    <FlowLine label="Валовий прибуток (до податків)" value={formatUAH(projection.profitGross)} />
                    <FlowLine label="Податок на прибуток (оцінка)" value={`−${formatUAH(projection.tax)}`} muted />
                    <FlowLine label="Чистий прибуток на руки" value={formatUAH(projection.profitNet)} accent strong />
                    <FlowLine label="Загальна сума на виході" value={formatUAH(projection.totalNet)} strong />
                  </div>
                </div>

                <div className="mt-6 pt-6 border-t border-border">
                  <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">Три сценарії за валовим прибутком</p>
                  <div className="grid grid-cols-3 gap-3">
                    <ScenarioPill label="Консервативний" value={projection.conservative} hint="IRR −20%" />
                    <ScenarioPill label="Базовий" value={projection.base} accent />
                    <ScenarioPill label="Оптимістичний" value={projection.optimistic} hint="IRR +15%" />
                  </div>
                </div>

                <Link
                  to="/auth?mode=register"
                  className="lumen-btn-primary mt-7 w-full justify-center"
                  data-testid="calculator-cta"
                >
                  Зарезервувати частку в цьому об'єкті <ArrowRight className="w-4 h-4" />
                </Link>
                <p className="mt-4 text-[11px] text-muted-foreground leading-relaxed">
                  Модель базується на параметрах, зафіксованих у договорі участі цього активу. Виплати орендної частини — пропорційно до фактичних надходжень з об'єкта. Переоцінка фіксується при виході з раунду (продажу активу або викупі оператором). Податки утримуються автоматично.
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

const Row = ({ label, value, accent }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="text-muted-foreground text-xs">{label}</span>
    <span className={`font-medium ${accent ? 'text-[#2E5D4F]' : ''}`}>{value}</span>
  </div>
);

const BigMetric = ({ label, value, accent }) => (
  <div>
    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
    <p className={`mt-2 text-2xl font-bold ${accent ? 'lumen-gradient-text' : ''}`}>{value}</p>
  </div>
);

const FlowLine = ({ label, value, muted, accent, strong }) => (
  <div className="flex items-baseline justify-between gap-3">
    <span className={`text-sm ${muted ? 'text-muted-foreground' : ''}`}>{label}</span>
    <span className={`font-mono ${strong ? 'font-bold text-base' : 'font-medium'} ${accent ? 'text-[#2E5D4F]' : ''} ${muted && !strong ? 'text-muted-foreground' : ''}`}>{value}</span>
  </div>
);

const ScenarioPill = ({ label, value, hint, accent }) => (
  <div className={`rounded-xl p-3 border ${accent ? 'border-[#2E5D4F]/40 bg-[#2E5D4F]/5' : 'border-border bg-background'}`}>
    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
    <p className={`mt-1 font-mono font-bold ${accent ? 'text-[#2E5D4F]' : ''}`}>{formatUAH(value)}</p>
    {hint && <p className="text-[10px] text-muted-foreground mt-0.5">{hint}</p>}
  </div>
);

/* Custom asset selector — replaces native <select> with branded popover */
const AssetSelect = ({ value, onChange, options }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);

  const selected = options.find((o) => o.id === value);

  return (
    <div ref={ref} className="relative mt-2" data-testid="calc-asset">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="w-full h-14 pl-4 pr-12 rounded-2xl border border-border bg-background hover:border-[#2E5D4F]/50 transition flex items-center text-left"
      >
        <span className="flex-1 min-w-0">
          {selected ? (
            <>
              <span className="block font-medium truncate">{selected.title}</span>
              <span className="block text-xs text-muted-foreground truncate">{selected.location} · {selected.category_label || selected.category}</span>
            </>
          ) : (
            <span className="text-muted-foreground">Оберіть об'єкт…</span>
          )}
        </span>
        <span
          className={`absolute right-4 top-1/2 -translate-y-1/2 flex items-center justify-center w-7 h-7 rounded-full bg-[#2E5D4F]/8 text-[#2E5D4F] transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 5.5l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute z-30 mt-2 left-0 right-0 rounded-2xl border border-border bg-card shadow-2xl overflow-hidden max-h-80 overflow-y-auto py-1"
          style={{ boxShadow: '0 24px 60px -20px rgba(46,93,79,0.25), 0 6px 18px rgba(0,0,0,0.08)' }}
        >
          {options.map((o) => {
            const isSel = o.id === value;
            return (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => { onChange(o.id); setOpen(false); }}
                  className={`w-full text-left px-4 py-3 flex items-center gap-3 transition ${isSel ? 'bg-[#2E5D4F]/8' : 'hover:bg-muted/60'}`}
                  role="option"
                  aria-selected={isSel}
                >
                  <span className={`w-2 h-2 rounded-full shrink-0 ${isSel ? 'bg-[#2E5D4F]' : 'bg-border'}`} />
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium truncate">{o.title}</span>
                    <span className="block text-xs text-muted-foreground truncate">
                      {o.location} · {o.category_label || o.category} · цільова IRR {formatPercent(o.target_yield)}
                    </span>
                  </span>
                  {isSel && (
                    <CheckCircle2 className="w-4 h-4 text-[#2E5D4F] shrink-0" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};


/* ─────────────────────────── FEATURED ASSETS ─────────────────────────── */

const FeaturedAssets = ({ assets }) => (
  <section id="assets" className="py-24 border-b border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="flex items-end justify-between gap-6 flex-wrap mb-10">
        <div>
          <SectionEyebrow>відкриті раунди</SectionEyebrow>
          <h2 className="lumen-h2">Об'єкти, які приймають інвесторів зараз</h2>
        </div>
        <Link to="/auth?mode=register" className="hidden md:inline-flex items-center gap-1 text-sm font-medium text-[#2E5D4F] hover:underline">
          Переглянути всі <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {(assets.length ? assets : FALLBACK_ASSETS).slice(0, 6).map((a) => (
          <AssetCard key={a.id || a.slug} asset={a} />
        ))}
      </div>
    </div>
  </section>
);

const AssetCard = ({ asset }) => (
  <Link
    to={asset.id?.startsWith('asset-') ? `/objects/${asset.id}` : '/auth'}
    className="group lumen-asset-card"
    data-testid={`asset-card-${asset.id || asset.slug}`}
  >
    <div
      className="aspect-[16/10] bg-muted relative overflow-hidden"
      style={asset.cover_url ? { backgroundImage: `url(${asset.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
    >
      {!asset.cover_url && (
        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
          <Building2 className="w-12 h-12" />
        </div>
      )}
      <span className="absolute top-3 left-3 px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-background/95 backdrop-blur border border-border font-semibold">
        {asset.category_label || asset.category}
      </span>
      {asset.status === 'open' && (
        <span className="absolute top-3 right-3 px-2.5 py-1 text-[10px] uppercase tracking-widest rounded-full bg-emerald-500 text-white font-semibold flex items-center gap-1">
          <span className="w-1 h-1 rounded-full bg-white animate-pulse" /> відкрито
        </span>
      )}
    </div>
    <div className="p-5">
      <h3 className="font-semibold text-lg leading-snug">{asset.title}</h3>
      <p className="mt-1 text-sm text-muted-foreground flex items-center gap-1.5"><MapPin className="w-3 h-3" /> {asset.location}</p>
      {asset.id?.startsWith('asset-') && <AssetMiniScore assetId={asset.id} className="mt-3" />}
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Дохідність</p>
          <p className="font-semibold text-[#2E5D4F] text-lg">{formatPercent(asset.target_yield)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Від</p>
          <p className="font-semibold text-lg">{formatUAH(asset.min_ticket)}</p>
        </div>
      </div>
      <div className="mt-4 pt-4 border-t border-border">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
          <span>Прогрес раунду</span>
          <span className="font-mono font-semibold">{asset.progress_percent || 0}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
          <div className="h-full bg-gradient-to-r from-[#C9A961] to-[#A98A45] transition-all" style={{ width: `${asset.progress_percent || 0}%` }} />
        </div>
      </div>
    </div>
  </Link>
);

/* ─────────────────────────── COMPARE ─────────────────────────── */

const Compare = () => {
  const rows = [
    { l: 'Очікувана річна доходність', lumen: '14-22%', bank: '13-16%', usd: '0-2%', stock: '−10..+25%' },
    { l: 'Захист капіталу', lumen: 'SPV + договір', bank: 'обмежені гарантії', usd: 'інфляція $', stock: 'жодного' },
    { l: 'Прозорість', lumen: 'щомісячний звіт', bank: 'низька', usd: '—', stock: 'квартальна' },
    { l: 'Поріг входу', lumen: 'від $1,000', bank: 'від $25', usd: 'від $1', stock: 'від ~$25' },
    { l: 'Ліквідність', lumen: 'вихід через раунд', bank: 'до 5 років', usd: 'миттєва', stock: 'миттєва' },
    { l: 'Зрозумілість', lumen: 'реальний об\'єкт', bank: 'депозит', usd: 'валюта', stock: 'ринкова спекуляція' },
  ];
  return (
    <section className="py-24 border-b border-border bg-card">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <SectionEyebrow>Lumen vs альтернативи</SectionEyebrow>
        <h2 className="lumen-h2">Куди вигідніше інвестувати $12,000 сьогодні</h2>
        <p className="lumen-section-sub">
          Об'єктивне порівняння Lumen зі звичними способами зберігати капітал у 2025-2026 роках.
        </p>
        <div className="mt-10 rounded-2xl border border-border bg-background overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/30">
                <th className="text-left px-5 py-4 font-medium text-muted-foreground">Параметр</th>
                <th className="text-left px-5 py-4 font-bold text-[#2E5D4F]">Lumen</th>
                <th className="text-left px-5 py-4 font-medium text-muted-foreground">Банк (депозит)</th>
                <th className="text-left px-5 py-4 font-medium text-muted-foreground">Долар «під подушкою»</th>
                <th className="text-left px-5 py-4 font-medium text-muted-foreground">Акції</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="px-5 py-4 font-medium">{r.l}</td>
                  <td className="px-5 py-4 font-semibold text-[#2E5D4F]">{r.lumen}</td>
                  <td className="px-5 py-4 text-muted-foreground">{r.bank}</td>
                  <td className="px-5 py-4 text-muted-foreground">{r.usd}</td>
                  <td className="px-5 py-4 text-muted-foreground">{r.stock}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

/* ─────────────────────────── MARKET CONTEXT (UA) ─────────────────────────── */

const MarketContext = () => (
  <section id="market" className="py-24 border-b border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="grid lg:grid-cols-12 gap-12 items-start">
        <div className="lg:col-span-5">
          <SectionEyebrow>український ринок 2025–2026</SectionEyebrow>
          <h2 className="lumen-h2">
            Чому інвестувати <span className="lumen-gradient-text">в українські активи</span> зараз —
            це раціонально, а не тільки емоційно
          </h2>
          <p className="lumen-section-sub">
            Ринок нерухомості України на старті нового циклу. Дефіцит житла, високий попит на оренду, програми відбудови та інституційний інтерес створюють вікно входу за заниженими цінами.
          </p>
          <div className="mt-7 p-5 rounded-2xl border border-border bg-card flex items-start gap-3">
            <MapPin className="w-5 h-5 text-[#2E5D4F] shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground leading-relaxed">
              Ми працюємо лише з українськими об'єктами та юридичними особами. Без офшорів, без перепродажу прав за межі країни.
            </p>
          </div>
        </div>

        <div className="lg:col-span-7 grid sm:grid-cols-2 gap-4">
          <MarketCard
            value="−40 %"
            label="дефіцит житла в містах"
            text="За даними галузевих оглядів, після 2022 року попит на якісне житло перевищує пропозицію на 35–45 % у Києві, Львові, Одесі та обласних центрах західної України."
          />
          <MarketCard
            value="14–22 %"
            label="дохідність орендних об'єктів"
            text="Орендні ставки в київських ЖК зросли на 18 % за два роки. Якісна нерухомість у нових проєктах виходить на стабільну рентну дохідність 14–18 % річних."
          />
          <MarketCard
            value="$36 млрд"
            label="оцінка ринку відбудови"
            text="World Bank оцінює потреби у відновленні житла та інфраструктури України у понад $500 млрд. Це — десятиліття роботи для девелопменту та будівельної галузі."
          />
          <MarketCard
            value="+27 %"
            label="зростання cash-on-cash"
            text="Інвестори, які входили в нерухомість у 2023–2024, фіксують середній річний приріст вартості активу на 22–32 % у твердій валюті після стабілізації ринку."
          />
        </div>
      </div>
    </div>
  </section>
);

const MarketCard = ({ value, label, text }) => (
  <div className="lumen-card">
    <p className="text-4xl font-bold tracking-tight lumen-gradient-text">{value}</p>
    <p className="mt-1 text-sm font-medium">{label}</p>
    <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{text}</p>
  </div>
);

/* ─────────────────────────── IMPACT LAYER ─────────────────────────── */

const ImpactLayer = () => (
  <section className="py-24 border-b border-border lumen-impact-bg">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="text-center max-w-3xl mx-auto">
        <SectionEyebrow>не лише прибуток</SectionEyebrow>
        <h2 className="lumen-h2 mx-auto">
          Інвестиція, яка <span className="lumen-gradient-text">залишається в Україні</span>
        </h2>
        <p className="lumen-section-sub mx-auto" style={{ marginLeft: 'auto', marginRight: 'auto' }}>
          Кожен інвестований долар, що проходить через Lumen, працює на конкретний об'єкт: будівництво, оренду, реконструкцію. Це не благодійність — це раціональна інвестиція з реальним грошовим потоком.
        </p>
      </div>

      <div className="mt-14 grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        <ImpactCard
          icon={<Hammer className="w-5 h-5" />}
          value="∼220"
          label="робочих місць"
          text="Один середній житловий проєкт Lumen — це робота для 200–250 людей: будівельники, постачальники, проєктувальники, інженери."
        />
        <ImpactCard
          icon={<Banknote className="w-5 h-5" />}
          value="∼18 %"
          label="у вигляді податків"
          text="Девелопмент, оренда та продаж активів генерують податки та збори, що залишаються в місцевій економіці кожного об'єкта."
        />
        <ImpactCard
          icon={<Layers className="w-5 h-5" />}
          value="реконструкція"
          label="пошкоджених об'єктів"
          text="Окрема категорія активів — викуп та відновлення пошкоджених будинків і комерції з програми «єВідновлення» та власних коштів інвесторів."
        />
        <ImpactCard
          icon={<Award className="w-5 h-5" />}
          value="100 %"
          label="українські SPV"
          text="Усі юридичні особи — резиденти України. Усі рахунки в українських банках. Жодного офшорного шару чи прихованих бенефіціарів."
        />
      </div>

      <div className="mt-12 max-w-4xl mx-auto rounded-2xl border border-border bg-card p-7">
        <div className="flex flex-col md:flex-row gap-5 md:items-center">
          <div className="w-14 h-14 rounded-2xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center shrink-0">
            <Wrench className="w-6 h-6" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-lg">Окрема лінійка: «Відновлення»</h3>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
              Активи з категорії «реконструкція» — це житлові та комерційні об'єкти, які постраждали і потребують відбудови. Lumen структурує такі угоди разом із програмою <strong className="text-foreground">«єВідновлення»</strong> та компенсаціями власникам. Доходність — поєднання ринкової оренди після ремонту та зростання вартості об'єкта.
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Перші об'єкти цієї лінійки відкриваються в I кварталі 2026 року. Залиште заявку, і ми попередимо вас першими.
            </p>
          </div>
          <Link to="/auth?mode=register" className="lumen-btn-primary self-start md:self-auto">
            Зацікавлений
          </Link>
        </div>
      </div>
    </div>
  </section>
);

const ImpactCard = ({ icon, value, label, text }) => (
  <div className="lumen-card">
    <div className="w-10 h-10 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center">{icon}</div>
    <p className="mt-5 text-2xl font-bold tracking-tight">{value}</p>
    <p className="text-xs uppercase tracking-widest text-muted-foreground mt-1">{label}</p>
    <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{text}</p>
  </div>
);

/* ─────────────────────────── PROTECTION ─────────────────────────── */

const Protection = () => (
  <section id="protect" className="py-24 border-b border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="grid lg:grid-cols-3 gap-12">
        <div>
          <SectionEyebrow>захист інвестора</SectionEyebrow>
          <h2 className="lumen-h2">5 рівнів захисту, які не залежать від «чесного слова»</h2>
          <p className="lumen-section-sub">
            Юридична, операційна та інформаційна оболонка кожної інвестиції. Працює навіть якщо команда зміниться.
          </p>
          <Link to="/auth?mode=register" className="lumen-btn-primary mt-8" data-testid="protect-cta">
            Подивитись приклад договору <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="lg:col-span-2 grid sm:grid-cols-2 gap-4">
          <Pillar
            icon={<ShieldCheck className="w-5 h-5" />}
            title="SPV під кожен актив"
            text="Окрема юридична особа-власник, яка володіє об'єктом від імені учасників. Ваша частка — це не «віра» в проєкт, а корпоративне право."
          />
          <Pillar
            icon={<FileText className="w-5 h-5" />}
            title="Договір участі з ЕЦП"
            text="Юридично-зобов'язуючий документ, який зберігається у вашому кабінеті і в реєстрі нотаріуса. Доступний 24/7."
          />
          <Pillar
            icon={<BarChart3 className="w-5 h-5" />}
            title="Щомісячні звіти"
            text="Готовність будівництва, надходження орендної плати, витрати, прогноз виплат. Без слів «у нас все добре»."
          />
          <Pillar
            icon={<Banknote className="w-5 h-5" />}
            title="Регулярні виплати"
            text="Дивіденди потоком на ваш кошелек або у внутрішній баланс кабінету. Виплати у USD / USDT."
          />
          <Pillar
            icon={<Lock className="w-5 h-5" />}
            title="Незалежний ескроу"
            text="Гроші для оплати девелоперу резервуються на ескроу-рахунку і вивільняються тільки після досягнення зафіксованих віх."
          />
          <Pillar
            icon={<Users className="w-5 h-5" />}
            title="Збори учасників"
            text="При критичних відхиленнях скликаємо віртуальні збори учасників SPV для прийняття рішень, як у класичному фонді."
          />
        </div>
      </div>
    </div>
  </section>
);

const Pillar = ({ icon, title, text }) => (
  <div className="lumen-card">
    <div className="w-11 h-11 rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F] flex items-center justify-center">
      {icon}
    </div>
    <h3 className="mt-5 font-semibold">{title}</h3>
    <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{text}</p>
  </div>
);

/* ─────────────────────────── TEAM ─────────────────────────── */

const Team = () => (
  <section id="team" className="py-24 border-b border-border bg-card">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="grid lg:grid-cols-2 gap-12 items-start">
        <div>
          <SectionEyebrow>хто за цим стоїть</SectionEyebrow>
          <h2 className="lumen-h2">Команда з досвідом у нерухомості, фінансах і праві</h2>
          <p className="lumen-section-sub">
            Lumen побудована командою з 14-річним досвідом у девелопменті, інвестиційному консалтингу та корпоративному праві в Україні.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-6">
            <Metric value="14 років" label="у нерухомості" />
            <Metric value="$30 млн+" label="реалізованих угод" />
            <Metric value="4 партнери" label="у складі команди" />
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          {TEAM.map((t) => (
            <div key={t.name} className="lumen-card">
              <div className="w-14 h-14 rounded-full bg-gradient-to-br from-[#E5C98A] to-[#A98A45] flex items-center justify-center text-white font-bold text-xl">
                {t.name[0]}
              </div>
              <h3 className="mt-4 font-semibold">{t.name}</h3>
              <p className="text-sm text-[#2E5D4F] font-medium">{t.role}</p>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{t.bio}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  </section>
);

const TEAM = [
  { name: 'Олексій Лучко', role: 'CEO, керуючий партнер', bio: '12 років у девелопменті житла. Реалізував 4 ЖК на 38 000 м² загальної площі.' },
  { name: 'Марія Заболотна', role: 'Юридичний партнер', bio: 'Корпоративне право, SPV-структури, M&A. Лекторка програми Real Estate Law.' },
  { name: 'Андрій Чуб', role: 'Інвестиційний директор', bio: 'Колишній керівник Real Estate департаменту в одному з топ-5 банків України.' },
  { name: 'Софія Грушевська', role: 'Operations', bio: 'Будує операційні процеси платформи: KYC, документообіг, виплати, звітність.' },
];

const Metric = ({ value, label }) => (
  <div>
    <p className="text-3xl font-bold tracking-tight">{value}</p>
    <p className="text-xs text-muted-foreground mt-1">{label}</p>
  </div>
);

/* ─────────────────────────── TESTIMONIALS ─────────────────────────── */

const Testimonials = () => (
  <section className="py-24 border-b border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <SectionEyebrow>думки інвесторів</SectionEyebrow>
      <h2 className="lumen-h2">Як учасники Lumen описують свій досвід</h2>
      <div className="mt-12 grid md:grid-cols-3 gap-5">
        {TESTIMONIALS.map((t, i) => (
          <div key={i} className="lumen-card relative">
            <Quote className="w-8 h-8 text-[#2E5D4F]/30 absolute top-5 right-5" />
            <p className="text-sm leading-relaxed">{t.quote}</p>
            <div className="mt-5 pt-5 border-t border-border flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#E5C98A] to-[#A98A45] flex items-center justify-center text-white font-bold">
                {t.author[0]}
              </div>
              <div>
                <p className="font-semibold text-sm">{t.author}</p>
                <p className="text-xs text-muted-foreground">{t.role}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  </section>
);

const TESTIMONIALS = [
  {
    quote: "До Lumen я тримав гроші в банку під 14% — а інфляція з'їдала майже все. Тут перший актив (ТЦ «Лавр») за 9 місяців дав 11% і ще 6% залишилось до кінця року. Звіти приходять як годинник.",
    author: 'Ярослав Кравченко',
    role: 'Інвестор, Київ · з січня 2025',
  },
  {
    quote: 'Сподобалось, що показують і будівельний майданчик, і фотозвіти, і реальні документи. Не «довіряйте нам», а покажуть. Я з другого активу ще збираюсь вкласти більше.',
    author: 'Олена Тимошенко',
    role: 'Підприємниця, Львів',
  },
  {
    quote: 'Підписав договір онлайн з ЕЦП, ще й нотаріус підтвердив. Юрист подивився структуру SPV і сказав «нормальна угода, як в європейському фонді». Перший дивіденд прийшов через 4 тижні.',
    author: 'Дмитро Бойко',
    role: 'Адвокат, Одеса',
  },
];

/* ─────────────────────────── PRESS ─────────────────────────── */

const Press = () => (
  <section className="py-16 border-b border-border bg-card">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <p className="text-center text-xs uppercase tracking-widest text-muted-foreground mb-6">Про нас пишуть</p>
      <div className="flex flex-wrap items-center justify-center gap-x-12 gap-y-4 text-muted-foreground/60">
        <span className="font-bold text-2xl tracking-tight">Forbes Ukraine</span>
        <span className="font-bold text-2xl tracking-tight">NV.ua</span>
        <span className="font-bold text-2xl tracking-tight">ЕП</span>
        <span className="font-bold text-2xl tracking-tight">Mind</span>
        <span className="font-bold text-2xl tracking-tight">delo.ua</span>
        <span className="font-bold text-2xl tracking-tight">AIN</span>
      </div>
    </div>
  </section>
);

/* ─────────────────────────── FAQ ─────────────────────────── */

const FAQ_ITEMS = [
  { q: 'Яка мінімальна сума входу?', a: 'Стартова частка — від $1,000 для більшості активів. Для преміум-об\u2019єктів (бізнес-центри, історична нерухомість) поріг входу вищий і вказаний на сторінці активу.' },
  { q: 'Коли я отримую виплати?', a: 'Для рентних активів (житло на оренду, ТЦ, склади) — щомісячно. Для будівельних — після фіксованих віх або в кінці раунду при виході з проєкту. Для землі — після перепродажу або зміни цільового призначення.' },
  { q: 'Як я виходжу з інвестиції?', a: 'Три варіанти: 1) дочекатися закриття раунду (продаж активу або викуп оператором); 2) запропонувати свою частку через внутрішній вторинний ринок Lumen; 3) попросити викуп у нас за поточною ринковою ціною (з дисконтом 5-10%).' },
  { q: 'Що буде, якщо проєкт не вийде на планову дохідність?', a: 'Прозорі звіти дозволяють побачити відхилення на ранніх етапах. При критичних — скликаємо збори учасників SPV для рішення (продаж, зміна керуючого, реструктуризація). У договорі прописана пріоритетність виплат: учасники першими отримують повернення капіталу.' },
  { q: 'Чи це легально в Україні?', a: 'Так. Кожен актив структурується через українську юридичну особу (товариство з обмеженою відповідальністю або АТ) відповідно до Закону «Про товариства з обмеженою та додатковою відповідальністю» та Закону «Про інвестиційну діяльність».' },
  { q: 'А як же ризик війни? Що, якщо об\u2019єкт постраждає?', a: 'Кожен актив має майнове страхування у партнерських українських страхових компаніях. Окремо ми проводимо ризик-скоринг локації: працюємо тільки з регіонами, де ризик прямого пошкодження мінімальний. Для активів категорії «Відновлення» — закладаємо реконструкцію в саму економіку проєкту. Інвестори бачать ризик-карту перед прийняттям рішення.' },
  { q: 'Які податки я плачу як інвестор?', a: 'Усі розрахунки та виплати — у доларі / USDT. Якщо у вашій юрисдикції з доходу утримується податок, ми утримуємо його автоматично і перераховуємо до відповідного бюджету. Ви отримуєте чисту суму.' },
  { q: 'Чи можу я інвестувати через ФОП або юр.особу?', a: 'Так. Юр.особи (включно з ФОП на загальній системі) можуть стати учасниками SPV з прозорою бухгалтерською обробкою. Зв\u2019яжіться з нами для індивідуального оформлення.' },
  { q: 'Як ви заробляєте?', a: 'Lumen бере 2% management fee при вході та 15% від профіту понад «hurdle rate» (поріг гарантованої дохідності інвестору). Це класична для фондів модель — ми заробляємо тоді, коли заробляєте ви.' },
];

const FAQ = () => {
  const [open, setOpen] = useState(0);
  return (
    <section id="faq" className="py-20 border-b border-border">
      <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <SectionEyebrow>часті питання</SectionEyebrow>
        <h2 className="lumen-h2">Що питають перед тим, як стати інвестором</h2>
        <div className="mt-10 lumen-faq-list" data-testid="faq-list">
          {FAQ_ITEMS.map((it, i) => (
            <FaqItem
              key={i}
              num={i + 1}
              q={it.q}
              a={it.a}
              open={open === i}
              onToggle={() => setOpen(open === i ? -1 : i)}
            />
          ))}
        </div>
      </div>
    </section>
  );
};

const FaqItem = ({ num, q, a, open, onToggle }) => (
  <div className={`lumen-faq-row ${open ? 'is-open' : ''}`}>
    <button type="button" onClick={onToggle} className="lumen-faq-q" data-testid={`faq-item-${num}`}>
      <span className="lumen-faq-num">{String(num).padStart(2, '0')}</span>
      <span className="lumen-faq-qtext">{q}</span>
      <span className="lumen-faq-sign">{open ? <Minus className="w-5 h-5" /> : <Plus className="w-5 h-5" />}</span>
    </button>
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
          className="lumen-faq-a-wrap"
        >
          <div className="lumen-faq-line" />
          <p className="lumen-faq-a">{a}</p>
        </motion.div>
      )}
    </AnimatePresence>
  </div>
);

/* ─────────────────────────── RISK ─────────────────────────── */

const RiskDisclosure = () => (
  <section className="py-12 border-b border-border bg-muted/20">
    <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
      <div className="flex gap-4 items-start">
        <ShieldCheck className="w-5 h-5 text-muted-foreground shrink-0 mt-1" />
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>Розкриття ризиків.</strong> Інвестиції в реальні активи завжди мають ризик часткової або повної втрати капіталу. Прогнозовані показники дохідності засновані на історичних даних та моделях ринку — фактична доходність може відрізнятись. Lumen не є банком і не пропонує депозитних продуктів. Кожен інвестор має проконсультуватись із своїм фінансовим радником перед прийняттям рішення. Інформація на сайті не є публічною пропозицією або інвестиційною порадою.
        </p>
      </div>
    </div>
  </section>
);

/* ─────────────────────────── FINAL CTA ─────────────────────────── */

const FinalCTA = ({ goCabinet }) => (
  <section className="py-24 relative overflow-hidden border-b border-border">
    <div aria-hidden className="lumen-cta-bg" />
    <div className="relative mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 text-center">
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#2E5D4F]/30 bg-[#2E5D4F]/10 text-xs uppercase tracking-widest text-[#2E5D4F] font-semibold">
        <Sparkles className="w-3.5 h-3.5" /> перший актив — без комісії платформи
      </div>
      <h2 className="mt-6 text-4xl md:text-6xl font-bold tracking-tight">
        Готові побачити свій <span className="lumen-gradient-text">перший пасивний дохід</span>?
      </h2>
      <p className="mt-5 text-lg text-muted-foreground max-w-2xl mx-auto">
        Безкоштовна реєстрація за 2 хвилини. KYC можна пройти після першого вибору об'єкту. Зворотний зв'язок від нашого консьєржа — у робочий день.
      </p>
      <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
        <button onClick={goCabinet} className="lumen-btn-primary-lg" data-testid="final-cta-primary">
          Створити кабінет інвестора <ArrowRight className="w-4 h-4" />
        </button>
        <a href="#assets" className="lumen-btn-ghost-lg">
          Подивитись об'єкти спочатку
        </a>
      </div>
    </div>
  </section>
);

/* ─────────────────────────── FOOTER ─────────────────────────── */

const Footer = () => (
  <footer className="bg-card border-t border-border">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-14">
      <div className="grid md:grid-cols-6 gap-8">
        <div className="md:col-span-2">
          <Logo height={40} />
          <p className="mt-4 text-sm text-muted-foreground max-w-md leading-relaxed">
            Lumen — RWA-платформа цифрового володіння реальними активами. Інвестиції в долар/USDT, прозорі SPV-структури, цифрові сертифікати власності та вторинний ринок.
          </p>
          <div className="mt-6 flex gap-2">
            <SocialBtn label="Telegram" />
            <SocialBtn label="Instagram" />
            <SocialBtn label="LinkedIn" />
            <SocialBtn label="YouTube" />
          </div>
          <div className="mt-6">
            <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Мобільний застосунок</p>
            <div className="mt-3"><StoreBadges /></div>
          </div>
        </div>
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Платформа</p>
          <ul className="mt-4 space-y-2 text-sm">
            <li><a href="#assets" className="hover:text-[#2E5D4F]">Активні раунди</a></li>
            <li><a href="#how" className="hover:text-[#2E5D4F]">Як це працює</a></li>
            <li><a href="#calculator" className="hover:text-[#2E5D4F]">Калькулятор</a></li>
            <li><a href="#faq" className="hover:text-[#2E5D4F]">Питання</a></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Компанія</p>
          <ul className="mt-4 space-y-2 text-sm">
            <li><a href="#team" className="hover:text-[#2E5D4F]">Команда</a></li>
            <li><a href="#" className="hover:text-[#2E5D4F]">Партнери</a></li>
            <li><a href="#" className="hover:text-[#2E5D4F]">Новини</a></li>
            <li><a href="#" className="hover:text-[#2E5D4F]">Кар'єра</a></li>
          </ul>
        </div>
        <div data-testid="footer-legal-col">
          <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Правова інформація</p>
          <ul className="mt-4 space-y-2 text-sm">
            <li><Link to="/legal/offer" className="hover:text-[#2E5D4F]" data-testid="footer-legal-offer">Публічна оферта</Link></li>
            <li><Link to="/legal/privacy" className="hover:text-[#2E5D4F]" data-testid="footer-legal-privacy">Конфіденційність</Link></li>
            <li><Link to="/legal/aml" className="hover:text-[#2E5D4F]" data-testid="footer-legal-aml">AML-політика</Link></li>
            <li><Link to="/legal/kyc" className="hover:text-[#2E5D4F]" data-testid="footer-legal-kyc">KYC-політика</Link></li>
            <li><Link to="/legal/risk" className="hover:text-[#2E5D4F]" data-testid="footer-legal-risk">Розкриття ризиків</Link></li>
            <li><Link to="/legal/secondary-market" className="hover:text-[#2E5D4F]" data-testid="footer-legal-secondary">Вторинний ринок</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">Контакти</p>
          <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
            <li>Київ, Україна</li>
            <li><a href="mailto:hello@lumen.com.ua" className="hover:text-[#2E5D4F]">hello@lumen.com.ua</a></li>
            <li><a href="tel:+380443334455" className="hover:text-[#2E5D4F]">+380 (44) 333-44-55</a></li>
          </ul>
        </div>
      </div>
      <div className="mt-10 pt-6 border-t border-border flex flex-col md:flex-row justify-between gap-4 text-xs text-muted-foreground">
        <span>© {new Date().getFullYear()} Lumen Capital Ukraine. Усі права захищено.</span>
        <div className="flex flex-wrap gap-5">
          <Link to="/legal/privacy" className="hover:text-foreground">Політика конфіденційності</Link>
          <Link to="/legal/offer" className="hover:text-foreground">Публічна оферта</Link>
          <Link to="/legal/risk" className="hover:text-foreground">Розкриття ризиків</Link>
          <Link to="/legal" className="hover:text-foreground">Усі документи</Link>
        </div>
      </div>
    </div>
  </footer>
);

const SocialBtn = ({ label }) => (
  <a
    href="#"
    aria-label={label}
    className="w-9 h-9 rounded-full border border-border bg-background flex items-center justify-center text-muted-foreground hover:text-[#2E5D4F] hover:border-[#2E5D4F] transition"
  >
    <span className="text-[10px] font-semibold">{label[0]}</span>
  </a>
);

/* ─────────────────────────── shared bits ─────────────────────────── */

const SectionEyebrow = ({ children }) => (
  <p className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-[#2E5D4F] font-semibold">
    <span className="w-6 h-px bg-[#2E5D4F]" /> {children}
  </p>
);

const FALLBACK_ASSETS = [
  { id: 'fa1', title: 'ЖК «Подільський»', category_label: 'нерухомість', location: 'Поділ, Київ', target_yield: 18.5, min_ticket: 75000, progress_percent: 62, status: 'open', cover_url: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa2', title: 'Земельна ділянка «Стоянка»', category_label: 'земля', location: 'Бориспільський р-н', target_yield: 22.0, min_ticket: 150000, progress_percent: 31, status: 'open', cover_url: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa3', title: 'ТЦ «Лавр»', category_label: 'комерція', location: 'Львів, Шевченківський', target_yield: 14.7, min_ticket: 100000, progress_percent: 88, status: 'open', cover_url: 'https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa4', title: 'Логістичний хаб «Рівне-Захід»', category_label: 'будівництво', location: 'Рівне, об\'їзна', target_yield: 19.2, min_ticket: 200000, progress_percent: 20, status: 'open', cover_url: 'https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa5', title: 'Будинок «Французький»', category_label: 'нерухомість', location: 'Одеса', target_yield: 13.4, min_ticket: 65000, progress_percent: 5, status: 'open', cover_url: 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=900&q=80' },
  { id: 'fa6', title: 'Котеджне містечко «Вишневе»', category_label: 'будівництво', location: 'с. Гатне', target_yield: 21.5, min_ticket: 180000, progress_percent: 12, status: 'open', cover_url: 'https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=900&q=80' },
];

const DEMO_POSITIONS = [
  { title: 'ЖК «Подільський»', yield: 19.1 },
  { title: 'ТЦ «Лавр»', yield: 14.7 },
  { title: 'Земля «Стоянка»', yield: 21.4 },
];
