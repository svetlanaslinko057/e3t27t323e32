import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Phone, Mail, Send, Copy, Check, Loader2, ArrowRight, MapPin, Clock } from 'lucide-react';
import { lumen } from '@/lib/lumenApi';
import PageHero from '@/components/public/PageHero';
import Reveal from '@/components/public/Reveal';
import SectionLabel from '@/components/public/SectionLabel';
import { LUMEN_CONTACTS } from '@/components/public/publicNav';
import {
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
} from '@/components/ui/accordion';

const CHANNELS = [
  { id: 'phone', icon: Phone, label: 'Телефон', value: LUMEN_CONTACTS.phone, copy: '+380443334455', href: LUMEN_CONTACTS.phoneHref, sub: 'Щодня · 9:00–18:00' },
  { id: 'email', icon: Mail, label: 'Email', value: LUMEN_CONTACTS.email, copy: LUMEN_CONTACTS.email, href: LUMEN_CONTACTS.emailHref, sub: 'Відповідь у робочий час — до 30 хвилин' },
  { id: 'telegram', icon: Send, label: 'Telegram', value: '@lumen_capital', copy: '@lumen_capital', href: LUMEN_CONTACTS.telegram, sub: 'Швидка підтримка у месенджері' },
];

const FAQ = [
  { q: 'З якої суми можна почати інвестувати?', a: 'Мінімальна сума участі — від $1,000. Для окремих активів поріг входу може відрізнятися — точну суму вказано на сторінці кожного об’єкта.' },
  { q: 'Як підтверджується моє право власності?', a: 'Після інвестиції ви отримуєте цифровий сертифікат власності на частку в SPV, яке володіє активом. Усі операції фіксуються у прозорому реєстрі.' },
  { q: 'Як і коли відбуваються виплати?', a: 'Орендний або операційний дохід розподіляється щомісяця пропорційно до вашої частки. Виплати відображаються у вашому кабінеті та додатку.' },
  { q: 'Чи можу я продати частку раніше терміну?', a: 'Так. На вторинному OTC-ринку LUMEN ви можете продати частку іншому інвестору до завершення циклу — торгівля доступна 24/7.' },
  { q: 'У якій валюті ведуться розрахунки?', a: 'Відображення та розрахунки ведуться у USD / USDT. Це захищає ваш капітал від курсових коливань.' },
  { q: 'Чи потрібна верифікація (KYC)?', a: 'Так, для інвестування потрібно пройти верифікацію. Це вимога законодавства та захист від шахрайства — процес займає кілька хвилин.' },
];

function ChannelCard({ ch }) {
  const [copied, setCopied] = useState(false);
  const doCopy = async () => {
    try { await navigator.clipboard.writeText(ch.copy); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch {}
  };
  const Icon = ch.icon;
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-border bg-white p-5">
      <div className="flex h-12 w-12 flex-none items-center justify-center rounded-xl bg-[#2E5D4F]/10 text-[#2E5D4F]"><Icon className="h-5 w-5" /></div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-[0.14em] text-token-muted">{ch.label}</p>
        <a href={ch.href} target={ch.id === 'telegram' ? '_blank' : undefined} rel="noreferrer" className="block truncate text-lg font-semibold text-foreground hover:text-[#2E5D4F]">{ch.value}</a>
        <p className="truncate text-xs text-token-muted">{ch.sub}</p>
      </div>
      <button type="button" onClick={doCopy} className="flex h-9 w-9 flex-none items-center justify-center rounded-lg border border-border text-token-muted transition hover:border-[#2E5D4F] hover:text-[#2E5D4F]" data-testid={`contacts-copy-${ch.id}-button`} aria-label="Копіювати">
        {copied ? <Check className="h-4 w-4 text-[#2E5D4F]" /> : <Copy className="h-4 w-4" />}
      </button>
    </div>
  );
}

export default function PublicContactsPage() {
  const [form, setForm] = useState({ name: '', phone: '', topic: '', message: '' });
  const [state, setState] = useState('idle');
  const [msg, setMsg] = useState('');

  useEffect(() => { document.title = 'LUMEN · Контакти'; }, []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (state === 'loading') return;
    if (!form.name.trim() || !form.phone.trim()) { setState('error'); setMsg('Вкажіть ім’я та телефон'); return; }
    setState('loading'); setMsg('');
    try {
      await lumen.post('/public/contact', { ...form, source: 'contacts_page' });
      setState('done'); setMsg('Дякуємо! Менеджер зв’яжеться з вами найближчим часом.');
      setForm({ name: '', phone: '', topic: '', message: '' });
    } catch (err) {
      setState('error'); setMsg('Не вдалося надіслати. Спробуйте ще раз або зателефонуйте.');
    }
  };

  return (
    <>
      <PageHero
        breadcrumb={[{ label: 'Головна', to: '/' }, { label: 'Контакти' }]}
        title="Контакти"
        lead="Поставте запитання менеджеру або залиште заявку — відповімо у робочий час впродовж 30 хвилин."
      >
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.5 }}
          className="mt-8 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 py-2 text-sm text-white/80">
          <span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#7BD389] opacity-60" /><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#7BD389]" /></span>
          Менеджер на лінії · Київ
        </motion.div>
      </PageHero>

      <section className="lpub-section lpub-section--cream">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
            {/* Channels */}
            <div>
              <Reveal><SectionLabel>Прямі канали</SectionLabel></Reveal>
              <div className="mt-6 space-y-4">
                {CHANNELS.map((ch, i) => <Reveal key={ch.id} delay={i * 0.06}><ChannelCard ch={ch} /></Reveal>)}
              </div>
              <Reveal delay={0.2}>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-3 rounded-2xl border border-border bg-white p-5"><MapPin className="h-5 w-5 text-[#2E5D4F]" /><span className="text-sm text-token-muted">{LUMEN_CONTACTS.address}</span></div>
                  <div className="flex items-center gap-3 rounded-2xl border border-border bg-white p-5"><Clock className="h-5 w-5 text-[#2E5D4F]" /><span className="text-sm text-token-muted">{LUMEN_CONTACTS.hours}</span></div>
                </div>
              </Reveal>
            </div>

            {/* Quick request form */}
            <Reveal delay={0.1}>
              <div className="rounded-2xl bg-[#062614] p-6 sm:p-8 text-white">
                <SectionLabel tone="light">Швидка заявка</SectionLabel>
                <h2 className="mt-4 text-2xl font-semibold" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Отримайте консультацію</h2>
                <p className="mt-2 text-sm text-white/65">Залиште контакти — ми розкажемо про активи, структуру та умови без зобов’язань.</p>
                <form className="mt-6 space-y-4" onSubmit={submit} data-testid="contacts-request-form">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <input className="lpub-cform" placeholder="Ім’я" value={form.name} onChange={set('name')} data-testid="contacts-name-input" />
                    <input className="lpub-cform" placeholder="Телефон" value={form.phone} onChange={set('phone')} data-testid="contacts-phone-input" />
                  </div>
                  <input className="lpub-cform" placeholder="Тема (напр. інвестиції в нерухомість)" value={form.topic} onChange={set('topic')} data-testid="contacts-topic-input" />
                  <textarea className="lpub-cform min-h-[110px] resize-y" placeholder="Повідомлення (необов’язково)" value={form.message} onChange={set('message')} data-testid="contacts-message-input" />
                  <button type="submit" disabled={state === 'loading'} className="lpub-btn-gold w-full justify-center" data-testid="contacts-submit-button">
                    {state === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Замовити дзвінок <ArrowRight className="h-4 w-4" /></>}
                  </button>
                  {msg && <p className={`text-sm ${state === 'error' ? 'text-red-300' : 'text-[#E5C98A]'}`} data-testid="contacts-form-msg">{msg}</p>}
                </form>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="lpub-section lpub-section--cream pt-0">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <Reveal><SectionLabel>Питання й відповіді</SectionLabel></Reveal>
          <Reveal delay={0.05}><h2 className="lpub-h2 mt-4">Поширені запитання інвесторів</h2></Reveal>
          <Reveal delay={0.1}>
            <Accordion type="single" collapsible className="mt-8" data-testid="contacts-faq">
              {FAQ.map((f, i) => (
                <AccordionItem key={i} value={`q${i}`} className="border-b border-border">
                  <AccordionTrigger className="text-left text-base font-semibold hover:no-underline" data-testid={`faq-trigger-${i}`}>{f.q}</AccordionTrigger>
                  <AccordionContent className="text-sm leading-relaxed text-token-muted">{f.a}</AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </Reveal>
        </div>
      </section>
    </>
  );
}
