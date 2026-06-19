import { useEffect, useState } from 'react';
import { lumen } from '@/lib/lumenApi';
import { Settings as SettingsIcon, Globe, CreditCard, Building2, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function AdminSettings() {
  const [legal, setLegal] = useState(null);

  useEffect(() => {
    lumen.get('/admin/legal-settings')
      .then((r) => setLegal(r.data))
      .catch(() => setLegal(null));
  }, []);

  return (
    <div className="p-6 md:p-10 max-w-3xl mx-auto" data-testid="admin-settings">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-token-muted">Налаштування</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Налаштування платформи</h1>
      </header>

      <div className="space-y-4">
        <Card icon={<Building2 className="w-5 h-5" />} title="Реквізити фонду" text={legal?.company_name || 'Не вказано'} hint="Юридична особа, яка оперує платформою" />
        <Card icon={<CreditCard className="w-5 h-5" />} title="Платіжні методи" text="Структура провайдерів настроюється окремо у .env" hint="WayForPay · Stripe · USDT" />
        <Card icon={<ShieldCheck className="w-5 h-5" />} title="KYC провайдер" text="Настроюється на наступному етапі" hint="Мінімальний KYC доступний вже зараз" />
        <Card icon={<Globe className="w-5 h-5" />} title="Мови платформи" text="Українська (активна)" hint="English додастся після закріплення української копії" />
        <Card icon={<SettingsIcon className="w-5 h-5" />} title="Обліковий запис адміна" text="Керування профілем" hint={<Link to="/account/2fa/setup" className="text-[#2E5D4F] hover:underline">Налаштувати 2FA</Link>} />
      </div>
    </div>
  );
}

const Card = ({ icon, title, text, hint }) => (
  <div className="rounded-2xl p-5 flex items-start gap-4" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)' }}>
    <div className="w-10 h-10 rounded-xl flex items-center justify-center text-[#2E5D4F]" style={{ background: 'var(--token-success-tint)' }}>{icon}</div>
    <div className="flex-1">
      <p className="font-medium">{title}</p>
      <p className="text-sm text-token-muted mt-0.5">{text}</p>
      {hint && <div className="text-xs text-token-muted mt-2">{hint}</div>}
    </div>
  </div>
);
