import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Search, FileSignature, Wallet, Repeat, ShieldCheck, Building2, Scale, FileCheck2,
  Landmark, Lock, ArrowRight, CheckCircle2,
} from 'lucide-react';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';

const STEPS = [
  { icon: Search, t: 'Обираєте актив і суму', d: 'Переглядаєте каталог об’єктів із відкритими раундами, прогнозом дохідності та умовами. Інвестуєте від $1,000.' },
  { icon: FileSignature, t: 'Отримуєте цифровий сертифікат', d: 'Після оплати ви отримуєте цифровий сертифікат власності на частку в SPV, яке володіє активом.' },
  { icon: Wallet, t: 'Щомісячні виплати', d: 'Орендний або операційний дохід розподіляється пропорційно до вашої частки — у USD / USDT.' },
  { icon: Repeat, t: 'Вихід через OTC', d: 'Продаєте частку на вторинному OTC-ринку будь-коли або чекаєте завершення циклу та повернення капіталу.' },
];

const SECURITY = [
  { icon: Building2, t: 'Окреме SPV на кожен актив', d: 'Кожен об’єкт структуровано через окрему юридичну особу (SPV). Ваша частка — це частка в компанії, яка володіє реальним активом.' },
  { icon: Landmark, t: 'Ескроу та розрахунки', d: 'Кошти раунду акумулюються на виділеному рахунку та спрямовуються на актив лише після виконання умов.' },
  { icon: Scale, t: 'Юридичні документи', d: 'Публічна оферта, договір інвестування та корпоративні документи SPV фіксують ваші права та частку доходу.' },
  { icon: FileCheck2, t: 'Цифровий сертифікат і реєстр', d: 'Право власності підтверджено цифровим сертифікатом із перевіркою та прозорим реєстром операцій.' },
];

const GUARANTEES = [
  'Прозора структура володіння без прихованих посередників',
  'Розділення коштів платформи та інвесторів',
  'Щомісячна звітність по кожному активу',
  'Ліквідність через вторинний OTC-ринок 24/7',
];

export default function PublicHowPage() {
  useEffect(() => { document.title = 'LUMEN · Принцип роботи та безпека'; }, []);

  return (
    <>
      <PageHero
        breadcrumb={[{ label: 'Головна', to: '/' }, { label: 'Принцип роботи та безпека' }]}
        title="Як працює LUMEN"
        lead="Від вибору активу до виплат і виходу — прозоро, поетапно та з юридичною фіксацією ваших прав на частку в реальному активі."
        primary={{ label: 'Переглянути активи', to: '/assets' }}
        secondary={{ label: 'Калькулятор дохідності', to: '/calculator' }}
        watermark="PROCESS"
      />

      {/* 4 STEPS */}
      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <Reveal><SectionLabel>4 кроки</SectionLabel></Reveal>
          <Reveal delay={0.05}><h2 className="lpub-h2 mt-4 max-w-2xl">Шлях інвестора — від вибору до виходу</h2></Reveal>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <Reveal key={i} delay={i * 0.08}>
                <div className="relative h-full rounded-2xl border border-border bg-white p-6">
                  <span className="font-mono text-xs font-bold tracking-widest text-[#2E5D4F]/50">{String(i + 1).padStart(2, '0')}</span>
                  <div className="mt-3 flex h-12 w-12 items-center justify-center rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F]"><s.icon className="h-6 w-6" /></div>
                  <h3 className="mt-4 font-semibold text-lg" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>{s.t}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-token-muted">{s.d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* SECURITY EDITORIAL */}
      <section className="lpub-section lpub-section--dark">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-start">
            <div>
              <Reveal><SectionLabel tone="light">Безпека та власність</SectionLabel></Reveal>
              <Reveal delay={0.05}>
                <h2 className="lpub-h2 mt-4 text-white">Ваша частка — це реальне право, а не обіцянка</h2>
              </Reveal>
              <Reveal delay={0.1}>
                <p className="lpub-lead mt-5">
                  LUMEN будує прозору юридичну та фінансову структуру навколо кожного активу. Мета — щоб інвестор розумів, чим саме він володіє, де зберігаються кошти та як розподіляється дохід.
                </p>
              </Reveal>
              <Reveal delay={0.15}>
                <ul className="mt-7 space-y-3">
                  {GUARANTEES.map((g, i) => (
                    <li key={i} className="flex items-start gap-3 text-white/85">
                      <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-[#C9A961]" /> <span className="text-sm leading-relaxed">{g}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              {SECURITY.map((s, i) => (
                <Reveal key={i} delay={i * 0.08}>
                  <div className="h-full rounded-2xl border border-white/12 bg-white/[0.04] p-6">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#C9A961]/15 text-[#E5C98A]"><s.icon className="h-6 w-6" /></div>
                    <h3 className="mt-4 font-semibold text-white text-lg" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>{s.t}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-white/65">{s.d}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 text-center">
          <Reveal>
            <div className="flex justify-center"><Lock className="h-8 w-8 text-[#2E5D4F]" /></div>
            <h2 className="lpub-h2 mt-5">Готові почати з першої частки?</h2>
            <p className="lpub-lead mt-4 mx-auto max-w-xl">Перегляньте відкриті раунди або отримайте консультацію менеджера щодо структури та безпеки.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link to="/assets" className="lumen-btn-primary h-12 px-7 text-sm font-semibold">Переглянути активи <ArrowRight className="h-4 w-4" /></Link>
              <Link to="/contacts" className="inline-flex h-12 items-center gap-2 rounded-xl border border-[#2E5D4F] px-6 text-sm font-semibold text-[#2E5D4F] transition hover:bg-[#2E5D4F] hover:text-white">Задати запитання</Link>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
