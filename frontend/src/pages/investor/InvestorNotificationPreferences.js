import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import {
  Bell, Mail, Smartphone, RotateCcw, Loader2, ShieldCheck, FileSignature,
  CreditCard, Coins, ArrowUpFromLine, Building2, MessageCircleQuestion, Save,
} from 'lucide-react';

const CHANNEL_ICONS = {
  kyc:          ShieldCheck,
  contract:     FileSignature,
  payment:      CreditCard,
  payout:       Coins,
  withdrawal:   ArrowUpFromLine,
  asset_update: Building2,
  qa_reply:     MessageCircleQuestion,
};

const TRANSPORT_ICONS = {
  in_app: Bell,
  email:  Mail,
  push:   Smartphone,
};

export default function InvestorNotificationPreferences() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/investor/notification-preferences');
      setData(r.data);
      setDraft(JSON.parse(JSON.stringify(r.data.channels)));
      setDirty(false);
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити')); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (channel, transport) => {
    setDraft(d => {
      const next = JSON.parse(JSON.stringify(d || {}));
      next[channel] = { ...(next[channel] || {}), [transport]: !next[channel]?.[transport] };
      return next;
    });
    setDirty(true);
    setSuccess('');
  };

  const save = async () => {
    setSaving(true); setError(''); setSuccess('');
    try {
      const channels = {};
      Object.entries(draft || {}).forEach(([ch, t]) => {
        channels[ch] = { in_app: !!t.in_app, email: !!t.email, push: !!t.push };
      });
      const r = await lumen.patch('/investor/notification-preferences', { channels });
      setData(r.data);
      setDraft(JSON.parse(JSON.stringify(r.data.channels)));
      setDirty(false);
      setSuccess('Збережено');
    } catch (e) { setError(lumenError(e)); }
    finally { setSaving(false); }
  };

  const reset = async () => {
    if (!window.confirm('Скинути всі налаштування сповіщень до типових?')) return;
    setSaving(true);
    try {
      const r = await lumen.post('/investor/notification-preferences/reset');
      setData(r.data);
      setDraft(JSON.parse(JSON.stringify(r.data.channels)));
      setDirty(false);
      setSuccess('Скинуто до типових');
    } catch (e) { setError(lumenError(e)); }
    finally { setSaving(false); }
  };

  if (loading) {
    return (
      <div className="p-4 md:p-10 space-y-3" data-testid="prefs-loading">
        {[1,2,3,4,5].map(i => <div key={i} className="h-16 rounded-2xl bg-muted/40 animate-pulse" />)}
      </div>
    );
  }

  if (!data || !draft) return null;

  const labels = data.labels || {};
  const transports = data.transport_labels || {};
  const channels = data.available_channels || [];

  return (
    <div className="p-4 md:p-10 max-w-3xl mx-auto" data-testid="investor-notification-prefs">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Sprint 12 · Push Infrastructure</p>
        <h1 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight">Налаштування сповіщень</h1>
        <p className="mt-1 text-token-muted text-sm">
          Оберіть, як ви хочете отримувати важливі події. Email і Push працюватимуть після підключення live-каналів.
        </p>
      </header>

      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}
      {success && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm">{success}</div>}

      <div className="space-y-2">
        {channels.map((ch) => {
          const Icon = CHANNEL_ICONS[ch] || Bell;
          const row = draft[ch] || {};
          return (
            <div key={ch} className="rounded-2xl border border-border bg-card p-4" data-testid={`channel-${ch}`}>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center">
                  <Icon className="w-4 h-4" />
                </div>
                <h3 className="font-semibold text-sm">{labels[ch] || ch}</h3>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {['in_app', 'email', 'push'].map(t => {
                  const TIcon = TRANSPORT_ICONS[t];
                  const active = !!row[t];
                  return (
                    <button
                      key={t}
                      onClick={() => toggle(ch, t)}
                      className={`p-2 rounded-xl border text-xs flex flex-col items-center gap-1 transition ${
                        active
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-border bg-muted/30 text-muted-foreground'
                      }`}
                      data-testid={`toggle-${ch}-${t}`}
                    >
                      <TIcon className="w-4 h-4" />
                      <span className="font-medium">{transports[t] || t}</span>
                      <span className={`text-[10px] font-bold ${active ? 'text-primary' : 'text-muted-foreground/50'}`}>
                        {active ? 'ON' : 'OFF'}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 sticky bottom-4 flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-2 sm:justify-end">
        <button
          onClick={reset}
          disabled={saving}
          className="px-4 py-2.5 rounded-xl text-sm border border-border bg-card hover:bg-muted/40 disabled:opacity-50 flex items-center justify-center gap-2"
          data-testid="btn-reset-prefs"
        >
          <RotateCcw className="w-4 h-4" /> Скинути
        </button>
        <button
          onClick={save}
          disabled={saving || !dirty}
          className="px-4 py-2.5 rounded-xl text-sm bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
          data-testid="btn-save-prefs"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {dirty ? 'Зберегти зміни' : 'Збережено'}
        </button>
      </div>

      <div className="mt-6 p-3 rounded-xl bg-muted/30 text-xs text-token-muted">
        <p className="font-semibold mb-1">Які події входять у канали:</p>
        <ul className="space-y-0.5 ml-3 list-disc">
          <li><strong>Верифікація</strong> — подача / схвалення / відхилення KYC</li>
          <li><strong>Договори</strong> — підготовка / підписання / скасування</li>
          <li><strong>Платежі</strong> — запит / підтвердження / відхилення</li>
          <li><strong>Виплати</strong> — нарахування періодичного доходу</li>
          <li><strong>Виведення</strong> — зміни статусу запитів на вивід</li>
          <li><strong>Новини об'єктів</strong> — оновлення проекту / етапи будівництва</li>
          <li><strong>Q&A</strong> — відповіді на запитання</li>
        </ul>
      </div>
    </div>
  );
}
