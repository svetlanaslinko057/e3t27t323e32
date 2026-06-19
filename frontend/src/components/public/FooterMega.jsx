import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Phone, Mail, Send, ArrowRight, ArrowUpRight, ArrowUp, Loader2, Check, MessageCircle, Share2 } from 'lucide-react';
import { lumen } from '@/lib/lumenApi';
import { LUMEN_CONTACTS } from '@/components/public/publicNav';
import { useContactModal } from '@/contexts/ContactModalContext';

const SECTION_LINKS = [
  { label: 'Принцип роботи та безпека', to: '/how' },
  { label: 'Активи у відкритих раундах', to: '/assets' },
  { label: 'Калькулятор дохідності', to: '/calculator' },
  { label: 'Вторинний OTC-ринок', to: '/otc' },
  { label: 'Мобільний застосунок', to: '/app' },
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
      setState('done'); setEmail(''); setMsg('Дякуємо! Ви підписані.');
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
          {state === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : state === 'done' ? <Check className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />}
        </button>
      </div>
      {msg && <p className={`lpub-foot__news-msg ${state === 'error' ? 'is-error' : 'is-ok'}`} data-testid="footer-newsletter-msg">{msg}</p>}
    </form>
  );
}

/**
 * Giant, airy footer — prominent foreground LUMEN wordmark (solid + outline,
 * DM-Auto style), trimmed columns, kicker labels and a "Нагору" control.
 */
export const FooterMega = () => {
  const { openContact } = useContactModal();
  const base = process.env.PUBLIC_URL || '';
  const year = new Date().getFullYear();
  const toTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  return (
    <footer className="lpub-foot" data-testid="footer-mega">
      <div className="lpub-foot__inner mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="lpub-foot__top">
          {/* Brand */}
          <div className="lpub-foot__brandcol">
            <span className="lpub-foot__kicker">— LUMEN</span>
            <img src={`${base}/branding/lumen-light.v4.png`} alt="LUMEN" className="lpub-foot__logo" draggable={false}
              onError={(e) => { e.currentTarget.style.display = 'none'; }} />
            <p className="lpub-foot__tag">Інвестиції в реальні активи від&nbsp;$1,000. Прозорі SPV-структури та цифрова власність.</p>
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

          {/* Trimmed columns */}
          <div className="lpub-foot__grid">
            <div className="lpub-foot__col">
              <span className="lpub-foot__kicker">— Розділи</span>
              <ul>{SECTION_LINKS.map((l) => (
                <li key={l.to}><Link to={l.to}>{l.label}<ArrowUpRight className="h-3.5 w-3.5" /></Link></li>
              ))}</ul>
            </div>
            <div className="lpub-foot__col">
              <span className="lpub-foot__kicker">— Контакти</span>
              <ul className="lpub-foot__contacts">
                <li><Phone className="h-4 w-4" /><a href={LUMEN_CONTACTS.phoneHref}>{LUMEN_CONTACTS.phone}</a></li>
                <li><Mail className="h-4 w-4" /><a href={LUMEN_CONTACTS.emailHref}>{LUMEN_CONTACTS.email}</a></li>
                <li><Send className="h-4 w-4" /><a href={LUMEN_CONTACTS.telegram} target="_blank" rel="noreferrer">@lumen_capital</a></li>
              </ul>
              <Link to="/contacts" className="lpub-foot__clientlink">Усі контакти <ArrowUpRight className="h-3.5 w-3.5" /></Link>
            </div>
            <div className="lpub-foot__col lpub-foot__col--news">
              <span className="lpub-foot__kicker">— Розсилка</span>
              <p className="lpub-foot__news-desc">Нові активи й відкриті раунди — раз на місяць.</p>
              <Newsletter />
            </div>
          </div>
        </div>

        {/* mid bar */}
        <div className="lpub-foot__mid">
          <span className="lpub-foot__mid-kicker"><i className="lpub-foot__greendot" /> Реальні активи · Цифрова власність</span>
          <button type="button" onClick={toTop} className="lpub-foot__totop" data-testid="footer-to-top">
            Нагору <span className="lpub-foot__totop-ico"><ArrowUp className="h-4 w-4" /></span>
          </button>
        </div>

        {/* prominent wordmark — REAL current LUMEN logo (same as header) */}
        <div className="lpub-foot__mega">
          <span className="lpub-foot__mega-badge">EST. 2024</span>
          <img src={`${base}/branding/lumen-light.v4.png`} alt="LUMEN" className="lpub-foot__megaimg" draggable={false}
            onError={(e) => { e.currentTarget.style.display = 'none'; }} />
        </div>

        <p className="lpub-foot__centertag"><span /> Інвестуйте в те, що існує насправді <span /></p>

        <div className="lpub-foot__bottom">
          <span className="lpub-foot__copy">© {year} LUMEN Capital Ukraine</span>
          <div className="lpub-foot__bottomlinks">
            <Link to="/legal/privacy">Конфіденційність</Link>
            <Link to="/legal/offer">Оферта</Link>
            <Link to="/legal">Документи</Link>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default FooterMega;
