/**
 * ContactModal — site-wide "leave a request" lead-capture modal.
 * Theme-aware (light/dark), bilingual (uk/en) via useLang().lang.
 * Submits to POST /api/public/contact-leads. No external UI deps.
 */
import { useEffect, useState } from 'react';
import { X, Send, CheckCircle2 } from 'lucide-react';
import api from '@/lib/api';
import { useTheme } from '@/contexts/ThemeContext';
import { useLang } from '@/contexts/LanguageContext';

const COPY = {
  title:    { en: 'Leave a request', uk: 'Залишити заявку' },
  subtitle: { en: 'Drop your contact — we will reach out shortly.', uk: 'Залиште контакт — ми зв’яжемося найближчим часом.' },
  name:     { en: 'Your name', uk: 'Ваше ім’я' },
  contact:  { en: 'Email / phone / Telegram', uk: 'Email / телефон / Telegram' },
  message:  { en: 'What do you need? (optional)', uk: 'Що вам потрібно? (необов’язково)' },
  submit:   { en: 'Send request', uk: 'Надіслати заявку' },
  sending:  { en: 'Sending…', uk: 'Надсилаємо…' },
  okTitle:  { en: 'Request received', uk: 'Заявку отримано' },
  okBody:   { en: 'Thank you. We will contact you soon.', uk: 'Дякуємо. Ми скоро зв’яжемося з вами.' },
  close:    { en: 'Close', uk: 'Закрити' },
  required: { en: 'Please enter a name or a contact.', uk: 'Вкажіть ім’я або контакт.' },
  error:    { en: 'Something went wrong. Try again.', uk: 'Сталася помилка. Спробуйте ще раз.' },
};

export default function ContactModal({ open, onClose, options = {} }) {
  const { theme } = useTheme();
  const { lang } = useLang();
  const dark = theme !== 'light';
  const T = (k) => (COPY[k] ? (COPY[k][lang] || COPY[k].en) : k);

  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (open) {
      setDone(false); setErr(''); setBusy(false);
      setName(''); setContact(''); setMessage(options.prefillMessage || '');
    }
  }, [open, options.prefillMessage]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const pal = dark
    ? { panel: '#16161A', border: 'rgba(245,242,236,0.14)', text: '#F5F2EC', sub: '#A09A92', field: '#0F0F11', fieldBd: 'rgba(245,242,236,0.16)', accent: '#D4A574', ctaInk: '#1A1714', overlay: 'rgba(0,0,0,0.66)' }
    : { panel: '#FFFFFF', border: 'rgba(0,0,0,0.10)', text: '#1A1714', sub: '#5C544D', field: '#F5F2EC', fieldBd: 'rgba(0,0,0,0.14)', accent: '#A07A2E', ctaInk: '#F5F2EC', overlay: 'rgba(20,18,15,0.45)' };

  const submit = async () => {
    if (!name.trim() && !contact.trim()) { setErr(T('required')); return; }
    setBusy(true); setErr('');
    try {
      await api.post('/public/contact-leads', {
        name: name.trim(),
        contact: contact.trim(),
        message: message.trim(),
        source: options.source || 'site',
        banner_id: options.bannerId || null,
        locale: lang,
      });
      setDone(true);
    } catch (e) {
      setErr(T('error'));
    } finally {
      setBusy(false);
    }
  };

  const field = {
    width: '100%', background: pal.field, border: `1px solid ${pal.fieldBd}`,
    borderRadius: 10, padding: '12px 14px', color: pal.text, fontSize: 14,
    outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
  };
  const label = { fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: pal.sub, marginBottom: 6, fontWeight: 600 };

  return (
    <div
      data-testid="contact-modal-overlay"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, background: pal.overlay,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
        animation: 'cm-fade 160ms ease',
      }}
    >
      <style>{`
        @keyframes cm-fade { from { opacity: 0 } to { opacity: 1 } }
        @keyframes cm-rise { from { opacity: 0; transform: translateY(14px) scale(0.985) } to { opacity: 1; transform: none } }
      `}</style>
      <div
        data-testid="contact-modal"
        style={{
          width: '100%', maxWidth: 440, background: pal.panel,
          border: `1px solid ${pal.border}`, borderRadius: 18, padding: 28,
          boxShadow: '0 30px 80px rgba(0,0,0,0.35)', animation: 'cm-rise 220ms cubic-bezier(0.22,1,0.36,1)',
          position: 'relative',
        }}
      >
        <button
          onClick={onClose}
          data-testid="contact-modal-close"
          aria-label={T('close')}
          style={{ position: 'absolute', top: 16, right: 16, background: 'transparent', border: 'none', color: pal.sub, cursor: 'pointer', padding: 4 }}
        >
          <X size={20} />
        </button>

        {done ? (
          <div style={{ textAlign: 'center', padding: '16px 4px' }} data-testid="contact-modal-success">
            <div style={{ width: 56, height: 56, borderRadius: 999, background: `${pal.accent}22`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: pal.accent, marginBottom: 16 }}>
              <CheckCircle2 size={30} />
            </div>
            <h3 style={{ color: pal.text, fontSize: 20, fontWeight: 600, margin: '0 0 8px' }}>{T('okTitle')}</h3>
            <p style={{ color: pal.sub, fontSize: 14, lineHeight: 1.5, margin: '0 0 20px' }}>{T('okBody')}</p>
            <button
              onClick={onClose}
              data-testid="contact-modal-done-btn"
              style={{ background: pal.accent, color: pal.ctaInk, border: 'none', borderRadius: 10, padding: '12px 22px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
            >
              {T('close')}
            </button>
          </div>
        ) : (
          <>
            <h3 style={{ color: pal.text, fontSize: 22, fontWeight: 600, margin: '0 0 6px', letterSpacing: '-0.01em' }}>
              {options.title || T('title')}
            </h3>
            <p style={{ color: pal.sub, fontSize: 14, lineHeight: 1.5, margin: '0 0 22px' }}>
              {options.subtitle || T('subtitle')}
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <div style={label}>{T('name')}</div>
                <input data-testid="contact-name-input" style={field} value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <div style={label}>{T('contact')}</div>
                <input data-testid="contact-contact-input" style={field} value={contact} onChange={(e) => setContact(e.target.value)} autoFocus />
              </div>
              <div>
                <div style={label}>{T('message')}</div>
                <textarea data-testid="contact-message-input" style={{ ...field, minHeight: 84, resize: 'vertical' }} value={message} onChange={(e) => setMessage(e.target.value)} />
              </div>

              {err ? <div data-testid="contact-error" style={{ color: '#E5645B', fontSize: 13 }}>{err}</div> : null}

              <button
                onClick={submit}
                disabled={busy}
                data-testid="contact-submit-btn"
                style={{
                  background: pal.accent, color: pal.ctaInk, border: 'none', borderRadius: 12,
                  padding: '14px 18px', fontSize: 15, fontWeight: 600, cursor: busy ? 'wait' : 'pointer',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  opacity: busy ? 0.75 : 1,
                }}
              >
                {busy ? T('sending') : T('submit')}
                {!busy && <Send size={16} />}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
