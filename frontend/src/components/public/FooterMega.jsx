import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Phone, Mail, MapPin, Clock, Send, ArrowRight, ArrowUpRight, Loader2, Check, MessageCircle, Share2 } from 'lucide-react';
import { lumen } from '@/lib/lumenApi';
import { PUBLIC_NAV, LUMEN_CONTACTS } from '@/components/public/publicNav';
import { useContactModal } from '@/contexts/ContactModalContext';

const COMPANY_LINKS = [
  { label: 'Принцип роботи та безпека', to: '/how' },
  { label: 'Активи у відкритих раундах', to: '/assets' },
  { label: 'Калькулятор дохідності', to: '/calculator' },
  { label: 'OTC-ринок', to: '/otc' },
  { label: 'Мобільний застосунок', to: '/app' },
];

const LEGAL_LINKS = [
  { label: 'Публічна оферта', to: '/legal/offer' },
  { label: 'Конфіденційність', to: '/legal/privacy' },
  { label: 'AML-політика', to: '/legal/aml' },
  { label: 'Розкриття ризиків', to: '/legal/risk' },
  { label: 'Усі документи', to: '/legal' },
];

function Newsletter() {
  const [email, setEmail] = useState('');
  const [state, setState] = useState('idle');
  const [msg, setMsg] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (state === 'loading') return;
    const value = email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) { setState('error'); setMsg('Вкажіть коректний email'); return; }
    setState('loading'); setMsg('');
    try {
      await lumen.post('/public/newsletter/subscribe', { email: value, source: 'footer' });
      setState('done'); setEmail(''); setMsg('Дякуємо! Ви підписані на розсилку.');
    } catch (err) {
      setState('error'); setMsg('Не вдалося підписатися. Спробуйте пізніше.');
    }
  };

  return (
    <form className="lpub-foot__news" onSubmit={submit} data-testid="footer-newsletter-form">
      <div className="lpub-foot__news-row">
        <input
          type="email" className="lpub-foot__news-input" placeholder="Ваш email"
          value={email} onChange={(e) => { setEmail(e.target.value); if (state !== 'idle') setState('idle'); }}
          aria-label="Email для розсилки" data-testid="footer-newsletter-input"
        />
        <button type="submit" className="lpub-foot__news-btn" disabled={state === 'loading'} aria-label="Підписатися" data-testid="footer-newsletter-submit-button">
          {state === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : state === 'done' ? <Check className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
      {msg && <p className={`lpub-foot__news-msg ${state === 'error' ? 'is-error' : 'is-ok'}`} data-testid="footer-newsletter-msg">{msg}</p>}
    </form>
  );
}

/**
 * Giant multi-column footer with a huge background wordmark (ECO / DM-Auto style),
 * adapted to LUMEN palette. Present on every public page.
 */
export const FooterMega = () => {
  const { openContact } = useContactModal();
  const year = new Date().getFullYear();
  return (
    <footer className="lpub-foot" data-testid="footer-mega">
      <div className="lpub-foot__inner mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="lpub-foot__top">
          {/* Brand */}
          <div className="lpub-foot__brandcol">
            <div className="lpub-foot__brand">LUMEN<i>.</i></div>
            <p className="lpub-foot__tag">
              RWA-платформа цифрового володіння реальними активами. Інвестиції від $1,000, прозорі SPV-структури, цифрові сертифікати власності та вторинний ринок.
            </p>
            <div className="lpub-foot__cta">
              <Link to="/assets" className="lpub-foot__btn lpub-foot__btn--primary" data-testid="footer-cta">Переглянути активи <ArrowRight className="h-4 w-4" /></Link>
              <button type="button" onClick={() => openContact({ source: 'footer', title: 'Залишити заявку' })} className="lpub-foot__btn lpub-foot__btn--ghost">Залишити заявку</button>
            </div>
            <div className="lpub-foot__socials">
              <a href={LUMEN_CONTACTS.telegram} target="_blank" rel="noreferrer" aria-label="Telegram" className="lpub-foot__social"><Send className="h-4 w-4" /></a>
              <a href={LUMEN_CONTACTS.emailHref} aria-label="Email" className="lpub-foot__social"><Mail className="h-4 w-4" /></a>
              <a href="#" aria-label="Спільнота" className="lpub-foot__social"><MessageCircle className="h-4 w-4" /></a>
              <a href="#" aria-label="Поділитися" className="lpub-foot__social"><Share2 className="h-4 w-4" /></a>
            </div>
          </div>

          {/* Link columns */}
          <div className="lpub-foot__grid">
            <div className="lpub-foot__col">
              <h4>Сайт</h4>
              <ul>{PUBLIC_NAV.map((l) => <li key={l.to}><Link to={l.to}>{l.label}</Link></li>)}</ul>
            </div>
            <div className="lpub-foot__col">
              <h4>Продукти</h4>
              <ul>{COMPANY_LINKS.map((l) => <li key={l.label}><Link to={l.to}>{l.label}</Link></li>)}</ul>
            </div>
            <div className="lpub-foot__col">
              <h4>Документи</h4>
              <ul>{LEGAL_LINKS.map((l) => <li key={l.label}><Link to={l.to}>{l.label}</Link></li>)}</ul>
            </div>
            <div className="lpub-foot__col lpub-foot__col--contacts">
              <h4>Контакти</h4>
              <ul className="lpub-foot__contacts">
                <li><Phone className="h-4 w-4" /><a href={LUMEN_CONTACTS.phoneHref}>{LUMEN_CONTACTS.phone}</a></li>
                <li><Mail className="h-4 w-4" /><a href={LUMEN_CONTACTS.emailHref}>{LUMEN_CONTACTS.email}</a></li>
                <li><MapPin className="h-4 w-4" /><span>{LUMEN_CONTACTS.address}</span></li>
                <li><Clock className="h-4 w-4" /><span>{LUMEN_CONTACTS.hours}</span></li>
              </ul>
              <Link to="/contacts" className="lpub-foot__clientlink">Усі контакти <ArrowUpRight className="h-3.5 w-3.5" /></Link>
            </div>
            <div className="lpub-foot__col lpub-foot__col--news">
              <h4>Розсилка</h4>
              <p className="lpub-foot__news-desc">Нові активи, відкриті раунди та звіти по виплатах — раз на місяць.</p>
              <Newsletter />
            </div>
          </div>
        </div>

        <div className="lpub-foot__wordmark" aria-hidden>LUMEN<span>.</span></div>

        <div className="lpub-foot__bottom">
          <span className="lpub-foot__copy">© {year} LUMEN Capital Ukraine · Усі права захищено</span>
          <div className="lpub-foot__badges"><span>SPV-структура</span><i /><span>Цифровий сертифікат</span><i /><span>USD / USDT</span></div>
          <div className="lpub-foot__bottomlinks">
            <Link to="/legal/privacy">Конфіденційність</Link>
            <Link to="/legal/offer">Оферта</Link>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default FooterMega;
