/**
 * LUMEN — Mobile App showcase primitives.
 *
 * Brand-consistent, CSS/SVG-based device mockups + screens, store badges,
 * QR (deep-links to /app), advantages data and an install dialog.
 * Palette is the existing LUMEN identity (green / gold / cream / ink).
 */
import { useMemo } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Zap, BellRing, Repeat, Fingerprint, Award, LineChart,
  TrendingUp, ChevronRight, Check, Wallet, Building2, ArrowUpRight,
} from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger,
} from '@/components/ui/dialog';

export const GREEN = '#2E5D4F';
export const GOLD = '#C99B3D';
export const INK = '#121211';
export const CREAM = '#FBF7F0';

// Placeholder store links — swap with real URLs once published.
export const APP_STORE_URL = '#';
export const GOOGLE_PLAY_URL = '#';
export const installUrl = () =>
  (typeof window !== 'undefined' ? `${window.location.origin}/app` : 'https://lumen.invest/app');

/* ───────────────────────── motion helper ───────────────────────── */
export const Reveal = ({ children, delay = 0, className = '' }) => {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 14 }}
      whileInView={reduce ? {} : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
};

/* ───────────────────────── device frame ───────────────────────── */
export const DeviceFrame = ({ children, width = 268, className = '', style = {} }) => (
  <div
    className={`relative shrink-0 ${className}`}
    style={{ width, ...style }}
    aria-hidden="true"
  >
    <div
      className="relative rounded-[2.6rem] p-[10px] shadow-2xl"
      style={{
        background: 'linear-gradient(155deg, #1c1c1a 0%, #2b2b28 60%, #161614 100%)',
        boxShadow: '0 30px 60px -20px rgba(18,18,17,0.45), 0 0 0 1px rgba(18,18,17,0.6)',
      }}
    >
      {/* screen */}
      <div className="relative overflow-hidden rounded-[2rem] bg-white" style={{ aspectRatio: '9 / 19.5' }}>
        {/* notch */}
        <div className="absolute left-1/2 top-2 z-20 h-[22px] w-[96px] -translate-x-1/2 rounded-full bg-[#161614]" />
        {/* reflection */}
        <div
          className="pointer-events-none absolute inset-0 z-10"
          style={{ background: 'linear-gradient(120deg, rgba(255,255,255,0.45), transparent 42%)', opacity: 0.14 }}
        />
        <div className="absolute inset-0 z-0 flex flex-col">{children}</div>
      </div>
    </div>
  </div>
);

const StatusBar = () => (
  <div className="flex items-center justify-between px-5 pt-3 pb-1 text-[10px] font-semibold" style={{ color: INK }}>
    <span>9:41</span>
    <div className="flex items-center gap-1 opacity-70">
      <span className="inline-block h-2.5 w-3.5 rounded-[2px] border" style={{ borderColor: INK }} />
      <span>100%</span>
    </div>
  </div>
);

const ScreenShell = ({ title, children }) => (
  <div className="flex h-full flex-col" style={{ background: CREAM }}>
    <StatusBar />
    <div className="flex items-center justify-between px-5 pb-2 pt-1">
      <span className="text-[13px] font-bold tracking-tight" style={{ color: GREEN }}>LUMEN</span>
      <span className="text-[11px] font-semibold" style={{ color: INK }}>{title}</span>
    </div>
    <div className="flex-1 overflow-hidden px-3.5 pb-3">{children}</div>
  </div>
);

const Pill = ({ children, bg = GOLD, color = '#fff' }) => (
  <span className="rounded-full px-2 py-0.5 text-[9px] font-bold" style={{ background: bg, color }}>{children}</span>
);

/* ───────────────────────── mock screens ───────────────────────── */
export const ScreenDashboard = () => (
  <ScreenShell title="Портфель">
    <div className="rounded-2xl p-3.5 text-white" style={{ background: `linear-gradient(135deg, ${GREEN}, #25493e)` }}>
      <p className="text-[9px] uppercase tracking-wider opacity-80">Загальний баланс</p>
      <p className="mt-0.5 text-[22px] font-extrabold leading-none">$12,480</p>
      <div className="mt-2 flex items-center gap-1 text-[10px]">
        <TrendingUp className="h-3 w-3" style={{ color: GOLD }} />
        <span style={{ color: GOLD }}>+18.2%</span>
        <span className="opacity-70">річних</span>
      </div>
    </div>
    <p className="mb-1.5 mt-3 text-[10px] font-bold" style={{ color: INK }}>Мої інвестиції</p>
    {[['ЖК «Подільський»', '13.4%', '$4,200'], ['Хаб «Рівне-Захід»', '19.2%', '$5,180'], ['Котедж «Вишневе»', '21.5%', '$3,100']].map((r, i) => (
      <div key={i} className="mb-1.5 flex items-center justify-between rounded-xl bg-white px-3 py-2" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
        <div>
          <p className="text-[10px] font-semibold" style={{ color: INK }}>{r[0]}</p>
          <p className="text-[9px]" style={{ color: GREEN }}>{r[1]} річних</p>
        </div>
        <span className="text-[11px] font-bold" style={{ color: INK }}>{r[2]}</span>
      </div>
    ))}
    <div className="mt-2 flex gap-2">
      <div className="flex-1 rounded-xl py-2 text-center text-[10px] font-bold text-white" style={{ background: GREEN }}>Інвестувати</div>
      <div className="flex-1 rounded-xl py-2 text-center text-[10px] font-bold" style={{ background: '#fff', color: GREEN, border: `1px solid ${GREEN}` }}>OTC ринок</div>
    </div>
  </ScreenShell>
);

export const ScreenAsset = () => (
  <ScreenShell title="Актив">
    <div className="relative h-24 overflow-hidden rounded-2xl" style={{ background: `linear-gradient(140deg, ${GREEN}, #3f7a66)` }}>
      <div className="absolute left-2 top-2"><Pill bg="rgba(255,255,255,0.18)">Нерухомість</Pill></div>
      <div className="absolute right-2 top-2"><Pill>13.4% річних</Pill></div>
      <Building2 className="absolute -bottom-3 right-3 h-16 w-16 text-white/15" />
    </div>
    <p className="mt-2 text-[12px] font-bold leading-tight" style={{ color: INK }}>Прибутковий будинок «Французький»</p>
    <p className="text-[9px]" style={{ color: 'rgba(18,18,17,0.55)' }}>Одеса · Французький бульвар</p>
    <div className="mt-2 grid grid-cols-3 gap-1.5">
      {[['Дохідність', '13.4%'], ['Термін', '24 міс'], ['Зібрано', '78%']].map((s, i) => (
        <div key={i} className="rounded-lg bg-white p-1.5 text-center" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
          <p className="text-[8px]" style={{ color: 'rgba(18,18,17,0.5)' }}>{s[0]}</p>
          <p className="text-[10px] font-bold" style={{ color: INK }}>{s[1]}</p>
        </div>
      ))}
    </div>
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full" style={{ background: 'rgba(18,18,17,0.08)' }}>
      <div className="h-full rounded-full" style={{ width: '78%', background: GOLD }} />
    </div>
    <div className="mt-3 rounded-xl py-2.5 text-center text-[11px] font-bold text-white" style={{ background: GREEN }}>Інвестувати · від $1,585</div>
  </ScreenShell>
);

export const ScreenInvest = () => (
  <ScreenShell title="Інвестування">
    <p className="text-[9px] uppercase tracking-wider" style={{ color: 'rgba(18,18,17,0.5)' }}>Сума інвестиції</p>
    <p className="text-[26px] font-extrabold leading-none" style={{ color: INK }}>$1,000</p>
    <div className="mt-2 flex gap-1.5">
      <div className="flex-1 rounded-lg py-1.5 text-center text-[10px] font-bold text-white" style={{ background: GREEN }}>USDT</div>
      <div className="flex-1 rounded-lg py-1.5 text-center text-[10px] font-semibold" style={{ background: '#fff', color: INK, border: '1px solid rgba(18,18,17,0.12)' }}>USD</div>
    </div>
    <div className="mt-3 space-y-1.5 rounded-xl bg-white p-3" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
      {[['Ваша частка', '0.62%'], ['Прогноз доходу / рік', '$134'], ['Комісія платформи', '$0']].map((r, i) => (
        <div key={i} className="flex items-center justify-between text-[10px]">
          <span style={{ color: 'rgba(18,18,17,0.6)' }}>{r[0]}</span>
          <span className="font-bold" style={{ color: INK }}>{r[1]}</span>
        </div>
      ))}
    </div>
    <div className="mt-2 flex items-center gap-1.5 text-[9px]" style={{ color: GREEN }}>
      <Check className="h-3 w-3" /> Цифровий сертифікат власності
    </div>
    <div className="mt-3 rounded-xl py-2.5 text-center text-[11px] font-bold text-white" style={{ background: GREEN }}>Підтвердити інвестицію</div>
  </ScreenShell>
);

export const ScreenIncome = () => (
  <ScreenShell title="Дохід">
    <div className="rounded-2xl bg-white p-3" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
      <p className="text-[9px] uppercase tracking-wider" style={{ color: 'rgba(18,18,17,0.5)' }}>Виплачено за весь час</p>
      <p className="text-[22px] font-extrabold leading-none" style={{ color: GREEN }}>$1,585</p>
    </div>
    <p className="mb-1.5 mt-3 text-[10px] font-bold" style={{ color: INK }}>Дивіденди</p>
    {[['10 чер', 'ЖК «Подільський»', '+$142'], ['10 трав', 'Хаб «Рівне-Захід»', '+$168'], ['10 кві', 'Котедж «Вишневе»', '+$96'], ['10 бер', 'ЖК «Подільський»', '+$142']].map((r, i) => (
      <div key={i} className="mb-1.5 flex items-center justify-between rounded-xl bg-white px-3 py-2" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full" style={{ background: 'rgba(46,93,79,0.1)' }}>
            <ArrowUpRight className="h-3 w-3" style={{ color: GREEN }} />
          </span>
          <div>
            <p className="text-[10px] font-semibold" style={{ color: INK }}>{r[1]}</p>
            <p className="text-[8px]" style={{ color: 'rgba(18,18,17,0.5)' }}>{r[0]}</p>
          </div>
        </div>
        <span className="text-[11px] font-bold" style={{ color: GREEN }}>{r[2]}</span>
      </div>
    ))}
  </ScreenShell>
);

export const ScreenOtc = () => (
  <ScreenShell title="OTC ринок">
    <div className="mb-2 flex items-center gap-1.5 rounded-xl px-3 py-2 text-[9px] text-white" style={{ background: `linear-gradient(135deg, ${GREEN}, #25493e)` }}>
      <Repeat className="h-3 w-3" style={{ color: GOLD }} /> Вторинний ринок часток 24/7
    </div>
    {[['ЖК «Подільський»', '$6,500', '2.5%'], ['Хаб «Рівне-Захід»', '$4,878', '1.8%'], ['Котедж «Вишневе»', '$3,100', '3.0%'], ['ТЦ «Лавр»', '$5,240', '1.2%']].map((r, i) => (
      <div key={i} className="mb-1.5 flex items-center justify-between rounded-xl bg-white px-3 py-2" style={{ border: '1px solid rgba(18,18,17,0.07)' }}>
        <div>
          <p className="text-[10px] font-semibold" style={{ color: INK }}>{r[0]}</p>
          <p className="text-[8px]" style={{ color: 'rgba(18,18,17,0.5)' }}>частка {r[2]}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold" style={{ color: INK }}>{r[1]}</span>
          <span className="rounded-lg px-2 py-1 text-[9px] font-bold text-white" style={{ background: GREEN }}>Купити</span>
        </div>
      </div>
    ))}
  </ScreenShell>
);

export const APP_SCREENS = [
  { key: 'dashboard', el: <ScreenDashboard />, uk: 'Портфель', en: 'Portfolio', subUk: 'Баланс, активи та дохід — на одному екрані.', subEn: 'Balance, assets & income on one screen.' },
  { key: 'asset', el: <ScreenAsset />, uk: 'Картка активу', en: 'Asset detail', subUk: 'Дохідність, термін, документи та інвестування.', subEn: 'Yield, term, documents and investing.' },
  { key: 'invest', el: <ScreenInvest />, uk: 'Інвестування', en: 'Invest flow', subUk: 'Сума, USD/USDT та миттєве підтвердження.', subEn: 'Amount, USD/USDT and instant confirm.' },
  { key: 'income', el: <ScreenIncome />, uk: 'Дохід', en: 'Income', subUk: 'Історія дивідендів і статус виплат.', subEn: 'Dividend history and payout status.' },
  { key: 'otc', el: <ScreenOtc />, uk: 'OTC ринок', en: 'OTC market', subUk: 'Купуйте та продавайте частки в один тап.', subEn: 'Buy and sell shares in one tap.' },
];

/* ───────────────────────── advantages ───────────────────────── */
export const ADVANTAGES = [
  { icon: Zap, uk: 'Миттєве інвестування', en: 'Instant investing', dUk: 'Оберіть актив і купіть частку за хвилину — прямо зі смартфона.', dEn: 'Pick an asset and buy a share in a minute — right from your phone.' },
  { icon: BellRing, uk: 'Сповіщення про дивіденди', en: 'Dividend alerts', dUk: 'Push одразу, щойно нараховано виплату по вашому активу.', dEn: 'Push the moment a payout hits your asset.' },
  { icon: Repeat, uk: 'OTC торгівля на ходу', en: 'OTC trading on the go', dUk: 'Вторинний ринок часток 24/7 — вихід з інвестиції в кишені.', dEn: 'A 24/7 secondary market — exit in your pocket.' },
  { icon: Fingerprint, uk: 'Face / Touch ID + 2FA', en: 'Biometric + 2FA', dUk: 'Біометрія та двофакторний захист на рівні пристрою.', dEn: 'Biometrics and device-level two-factor security.' },
  { icon: Award, uk: 'Сертифікат власності', en: 'Ownership certificate', dUk: 'Цифровий сертифікат на частку — завжди під рукою.', dEn: 'Your digital ownership certificate, always at hand.' },
  { icon: LineChart, uk: 'Портфель у реальному часі', en: 'Real-time portfolio', dUk: 'Дохідність, баланс і ціни в USD/USDT онлайн.', dEn: 'Yield, balance and USD/USDT prices, live.' },
];

/* ───────────────────────── QR ───────────────────────── */
export const AppQR = ({ size = 104, className = '' }) => {
  const url = useMemo(() => installUrl(), []);
  return (
    <div className={`rounded-xl bg-white p-2 ${className}`} style={{ border: `1px solid rgba(201,155,61,0.35)` }} aria-label="QR-код для встановлення додатку">
      <QRCodeSVG value={url} size={size} fgColor={INK} bgColor="#ffffff" level="M" />
    </div>
  );
};

/* ───────────────────────── store badges ───────────────────────── */
const BadgeShell = ({ href, testid, top, bottom, icon }) => (
  <a
    href={href}
    target={href === '#' ? undefined : '_blank'}
    rel="noreferrer"
    data-testid={testid}
    className="inline-flex items-center gap-2.5 rounded-xl px-3.5 py-2 text-white transition-transform duration-200 hover:-translate-y-0.5"
    style={{ background: INK, boxShadow: '0 6px 18px -8px rgba(18,18,17,0.5)' }}
  >
    {icon}
    <span className="text-left leading-tight">
      <span className="block text-[9px] uppercase tracking-wide opacity-80">{top}</span>
      <span className="block text-[14px] font-semibold">{bottom}</span>
    </span>
  </a>
);

export const StoreBadges = ({ className = '' }) => (
  <div className={`flex flex-wrap items-center gap-3 ${className}`}>
    <BadgeShell
      href={APP_STORE_URL}
      testid="mobile-app-store-badge-appstore"
      top="Завантажити в"
      bottom="App Store"
      icon={<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d="M16.365 1.43c.06 1.02-.34 2.02-1 2.77-.66.77-1.74 1.36-2.78 1.28-.07-1 .39-2.04 1.02-2.74.7-.78 1.86-1.36 2.76-1.31zM20.5 17.18c-.5 1.16-.74 1.68-1.39 2.71-.9 1.44-2.18 3.23-3.76 3.24-1.4.02-1.76-.92-3.66-.91-1.9.01-2.29.93-3.69.91-1.58-.01-2.79-1.62-3.69-3.05-2.53-4.02-2.8-8.73-1.24-11.24 1.11-1.79 2.86-2.84 4.5-2.84 1.68 0 2.73.92 4.12.92 1.34 0 2.16-.92 4.1-.92 1.46 0 3.01.8 4.12 2.17-3.62 1.98-3.03 7.15.19 8.27z" /></svg>}
    />
    <BadgeShell
      href={GOOGLE_PLAY_URL}
      testid="mobile-app-store-badge-googleplay"
      top="Завантажити в"
      bottom="Google Play"
      icon={<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M3.6 2.1c-.3.3-.5.7-.5 1.2v17.4c0 .5.2.9.5 1.2l9.3-9.9L3.6 2.1z" fill="#34A853" /><path d="M16.5 8.4 5 1.7c-.4-.2-.8-.2-1.1 0l9.2 9.8 3.4-3.1z" fill="#EA4335" /><path d="m20.4 10.6-2.6-1.5-3.6 3.3 3.6 3.3 2.6-1.5c.9-.5.9-1.7 0-2.2 0-.7 0-1.4 0-1.4z" fill="#FBBC04" /><path d="m4 22.3 11.4-6.6-3.4-3.1L4 22.3z" fill="#4285F4" /></svg>}
    />
  </div>
);

/* ───────────────────────── install dialog ───────────────────────── */
export const InstallDialog = ({ trigger }) => (
  <Dialog>
    <DialogTrigger asChild>{trigger}</DialogTrigger>
    <DialogContent className="sm:max-w-sm" data-testid="mobile-app-install-dialog">
      <DialogHeader>
        <DialogTitle>Встановіть додаток LUMEN</DialogTitle>
        <DialogDescription>Скануйте QR-код камерою телефона, щоб відкрити сторінку встановлення для iOS та Android.</DialogDescription>
      </DialogHeader>
      <div className="flex flex-col items-center gap-4 py-2">
        <AppQR size={172} />
        <StoreBadges className="justify-center" />
        <p className="flex items-center gap-1.5 text-xs text-token-muted">
          <Wallet className="h-3.5 w-3.5" /> Інвестуйте, отримуйте дохід та торгуйте на OTC зі смартфона
        </p>
      </div>
    </DialogContent>
  </Dialog>
);

export { ChevronRight };
