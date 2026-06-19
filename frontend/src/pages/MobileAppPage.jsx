/**
 * LUMEN — dedicated Mobile App marketing page (/app).
 * Full showcase: hero, advantages, screen-by-screen, security, install, FAQ, final CTA.
 */
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import {
  ArrowLeft, ArrowRight, ShieldCheck, Lock, Fingerprint, BellRing, QrCode, Check, Sparkles,
} from 'lucide-react';
import Logo from '@/components/Logo';
import ThemeToggle from '@/components/ThemeToggle';
import { useLang } from '@/contexts/LanguageContext';
import {
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
} from '@/components/ui/accordion';
import {
  DeviceFrame, ScreenDashboard, ScreenAsset, ScreenInvest, ScreenIncome, ScreenOtc,
  StoreBadges, AppQR, InstallDialog, Reveal, ADVANTAGES, APP_SCREENS, GREEN, GOLD, INK,
} from '@/components/marketing/AppShowcase';

const SECURITY = [
  { icon: Fingerprint, uk: 'Біометричний вхід', en: 'Biometric login', dUk: 'Face ID та Touch ID для миттєвого й захищеного доступу.', dEn: 'Face ID and Touch ID for instant, secure access.' },
  { icon: Lock, uk: 'Двофакторна автентифікація', en: 'Two-factor auth', dUk: 'Додатковий рівень захисту для входу та транзакцій.', dEn: 'An extra layer for sign-in and transactions.' },
  { icon: ShieldCheck, uk: 'Шифровані сесії', en: 'Encrypted sessions', dUk: 'Дані передаються захищеним каналом, токени — на пристрої.', dEn: 'Data over a secure channel, tokens kept on-device.' },
  { icon: BellRing, uk: 'Контроль активності', en: 'Activity control', dUk: 'Сповіщення про входи та дії з вашим рахунком.', dEn: 'Alerts for logins and account activity.' },
];

const FAQ = [
  { q_uk: 'Коли додаток буде доступний?', q_en: 'When will the app be available?', a_uk: 'Додаток виходить для iOS та Android. Скануйте QR або залиште пристрій під рукою — встановлення займе менше хвилини.', a_en: 'The app ships for iOS and Android. Scan the QR — installation takes under a minute.' },
  { q_uk: 'Чи безпечно інвестувати з додатку?', q_en: 'Is investing in the app secure?', a_uk: 'Так. Біометрія, двофакторна автентифікація та шифровані сесії захищають кожен вхід і транзакцію.', a_en: 'Yes. Biometrics, two-factor auth and encrypted sessions protect every login and transaction.' },
  { q_uk: 'Чи можна торгувати на OTC-ринку?', q_en: 'Can I trade on the OTC market?', a_uk: 'Так, вторинний ринок часток працює прямо в додатку — купуйте та продавайте частки 24/7.', a_en: 'Yes, the secondary market runs right in the app — buy and sell shares 24/7.' },
  { q_uk: 'Чи буде реферальна програма?', q_en: 'Will there be a referral program?', a_uk: 'Так, реферальна програма з’явиться в додатку найближчим часом.', a_en: 'Yes, a referral program is coming to the app soon.' },
];

export default function MobileAppPage() {
  const { bi } = useLang();
  const reduce = useReducedMotion();
  useEffect(() => { document.title = 'LUMEN · ' + bi('Додаток для iOS та Android', 'App for iOS & Android'); }, [bi]);

  return (
    <div className="min-h-screen bg-background text-foreground lumen-landing">
      {/* top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex items-center" data-testid="app-page-logo"><Logo height={30} /></Link>
          <div className="flex items-center gap-2">
            <Link to="/" className="hidden items-center gap-1.5 text-sm font-medium text-token-muted transition-colors hover:text-foreground sm:inline-flex" data-testid="app-page-back">
              <ArrowLeft className="h-4 w-4" /> {bi('На сайт', 'Back to site')}
            </Link>
            <ThemeToggle />
            <InstallDialog trigger={<button className="lumen-btn-primary h-9 px-4 text-sm font-medium" data-testid="app-page-install-top"><QrCode className="h-4 w-4" /> {bi('Встановити', 'Install')}</button>} />
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(46,93,79,0.06) 0%, rgba(251,247,240,0) 50%)' }} />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:gap-8 lg:px-8 lg:py-24">
          <div>
            <Reveal>
              <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-token-muted">
                <Sparkles className="h-3.5 w-3.5" style={{ color: GOLD }} /> iOS • Android
              </span>
            </Reveal>
            <Reveal delay={0.05}>
              <h1 className="mt-5 text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl">
                {bi('Ваші інвестиції — ', 'Your investments — ')}<span className="lumen-gradient-text">{bi('у кишені', 'in your pocket')}</span>
              </h1>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="lumen-section-sub mt-5 max-w-xl">
                {bi(
                  'Реальні активи, дохід у USD/USDT, цифрові сертифікати власності та OTC-ринок — усе у застосунку LUMEN для iOS та Android.',
                  'Real-world assets, USD/USDT income, digital ownership certificates and an OTC market — all in the LUMEN app for iOS and Android.',
                )}
              </p>
            </Reveal>
            <Reveal delay={0.18}>
              <div className="mt-8"><StoreBadges /></div>
            </Reveal>
            <Reveal delay={0.24}>
              <div className="mt-6 flex items-center gap-4 rounded-2xl border border-border bg-card p-3 w-fit">
                <AppQR size={84} />
                <div className="max-w-[180px]">
                  <p className="text-sm font-semibold">{bi('Скануйте, щоб встановити', 'Scan to install')}</p>
                  <p className="text-xs text-token-muted">{bi('Наведіть камеру телефона на код', 'Point your phone camera at the code')}</p>
                </div>
              </div>
            </Reveal>
          </div>

          <div className="relative flex min-h-[480px] items-center justify-center">
            <motion.div initial={reduce ? false : { opacity: 0, y: 24 }} animate={reduce ? {} : { opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="absolute right-8 top-2 hidden rotate-6 sm:block">
              <DeviceFrame width={236}><ScreenAsset /></DeviceFrame>
            </motion.div>
            <motion.div initial={reduce ? false : { opacity: 0, y: 14 }} animate={reduce ? {} : { opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} className="relative -rotate-3">
              <DeviceFrame width={278}><ScreenDashboard /></DeviceFrame>
            </motion.div>
            <div className="pointer-events-none absolute -bottom-6 left-1/2 h-28 w-3/4 -translate-x-1/2 rounded-full" style={{ background: `radial-gradient(ellipse, ${GOLD}22, transparent 70%)` }} />
          </div>
        </div>
      </section>

      {/* ADVANTAGES */}
      <section className="border-t border-border py-20 sm:py-24" style={{ background: 'var(--token-surface, #f7f3ec)' }}>
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <Reveal><p className="text-center text-[12px] font-semibold uppercase tracking-widest text-token-muted">{bi('Чому додаток', 'Why the app')}</p></Reveal>
          <Reveal delay={0.05}><h2 className="lumen-h2 mx-auto mt-3 text-center">{bi('Все для інвестора — в одному застосунку', 'Everything an investor needs — in one app')}</h2></Reveal>
          <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {ADVANTAGES.map((a, i) => (
              <Reveal key={a.uk} delay={i * 0.04}>
                <div className="h-full rounded-2xl border border-border bg-card p-6 transition-transform duration-200 hover:-translate-y-0.5" data-testid={`app-advantage-${i}`}>
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: 'rgba(201,155,61,0.12)' }}>
                    <a.icon className="h-5 w-5" style={{ color: GOLD }} />
                  </span>
                  <h3 className="mt-4 text-base font-semibold">{bi(a.uk, a.en)}</h3>
                  <p className="mt-1.5 text-sm leading-6 text-token-muted">{bi(a.dUk, a.dEn)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* SCREENS */}
      <section className="border-t border-border py-20 sm:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <Reveal><h2 className="lumen-h2 text-center">{bi('Подивіться, як це працює', 'See how it works')}</h2></Reveal>
          <Reveal delay={0.05}><p className="lumen-section-sub mx-auto mt-3 max-w-2xl text-center">{bi('П’ять екранів — увесь шлях інвестора: від вибору активу до доходу та виходу через OTC.', 'Five screens — the whole investor journey: from picking an asset to income and an OTC exit.')}</p></Reveal>
          <div className="mt-12 flex snap-x snap-mandatory gap-6 overflow-x-auto pb-6 lg:justify-center lg:overflow-visible" data-testid="app-screens-row">
            {APP_SCREENS.map((s, i) => (
              <Reveal key={s.key} delay={i * 0.05} className="snap-center">
                <div className="flex flex-col items-center">
                  <DeviceFrame width={218}>{s.el}</DeviceFrame>
                  <p className="mt-4 text-sm font-semibold">{bi(s.uk, s.en)}</p>
                  <p className="mt-1 max-w-[200px] text-center text-xs text-token-muted">{bi(s.subUk, s.subEn)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* SECURITY */}
      <section className="border-t border-border py-20 sm:py-24" style={{ background: 'var(--token-surface, #f7f3ec)' }}>
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:gap-16 lg:px-8">
          <div>
            <Reveal><p className="text-[12px] font-semibold uppercase tracking-widest text-token-muted">{bi('Безпека', 'Security')}</p></Reveal>
            <Reveal delay={0.05}><h2 className="lumen-h2 mt-3">{bi('Захищено на рівні банку', 'Bank-grade protection')}</h2></Reveal>
            <Reveal delay={0.1}><p className="lumen-section-sub mt-4">{bi('Ваш капітал і дані під захистом біометрії, 2FA та шифрування. Кожен вхід і транзакція — під вашим контролем.', 'Your capital and data are protected by biometrics, 2FA and encryption. Every login and transaction stays under your control.')}</p></Reveal>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {SECURITY.map((s, i) => (
              <Reveal key={s.uk} delay={i * 0.05}>
                <div className="rounded-2xl border border-border bg-card p-5" data-testid={`app-security-${i}`}>
                  <s.icon className="h-5 w-5" style={{ color: GREEN }} />
                  <h3 className="mt-3 text-sm font-semibold">{bi(s.uk, s.en)}</h3>
                  <p className="mt-1 text-xs leading-5 text-token-muted">{bi(s.dUk, s.dEn)}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* INSTALL */}
      <section className="border-t border-border py-20 sm:py-24">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl border border-border bg-card p-8 sm:p-12" style={{ boxShadow: '0 24px 60px -30px rgba(18,18,17,0.35)' }}>
            <div className="grid items-center gap-10 lg:grid-cols-[1fr_auto]">
              <div>
                <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{bi('Встановіть LUMEN сьогодні', 'Get LUMEN today')}</h2>
                <p className="mt-3 max-w-xl text-token-muted">{bi('Почніть інвестувати в реальні активи від $1,000 прямо зі смартфона. iOS та Android.', 'Start investing in real-world assets from $1,000 right from your phone. iOS and Android.')}</p>
                <div className="mt-6"><StoreBadges /></div>
              </div>
              <div className="flex flex-col items-center gap-3">
                <AppQR size={140} />
                <span className="text-xs text-token-muted">{bi('Скануйте для встановлення', 'Scan to install')}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-border py-20 sm:py-24" style={{ background: 'var(--token-surface, #f7f3ec)' }}>
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <Reveal><h2 className="lumen-h2 text-center">{bi('Часті запитання', 'FAQ')}</h2></Reveal>
          <Reveal delay={0.05}>
            <Accordion type="single" collapsible className="mt-8" data-testid="app-faq">
              {FAQ.map((f, i) => (
                <AccordionItem key={i} value={`item-${i}`}>
                  <AccordionTrigger className="text-left text-sm font-semibold" data-testid={`app-faq-trigger-${i}`}>{bi(f.q_uk, f.q_en)}</AccordionTrigger>
                  <AccordionContent className="text-sm leading-6 text-token-muted">{bi(f.a_uk, f.a_en)}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Reveal>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="border-t border-border py-16">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-6 px-4 text-center sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: GREEN }}>
            <Check className="h-4 w-4" /> {bi('Реальні активи · USD / USDT · Цифрова власність', 'Real assets · USD / USDT · Digital ownership')}
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{bi('Інвестуйте розумно — зі смартфона', 'Invest smart — from your phone')}</h2>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <StoreBadges className="justify-center" />
          </div>
          <Link to="/auth?mode=register" className="lumen-btn-ghost-lg" data-testid="app-page-register">
            {bi('Або зареєструватися на сайті', 'Or sign up on the web')} <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
