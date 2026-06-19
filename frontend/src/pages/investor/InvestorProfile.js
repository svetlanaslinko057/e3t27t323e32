import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/App';
import { lumen, lumenError, lumenErrorDetails } from '@/lib/lumenApi';
import { trackEvent } from '@/lib/activityTracker';
import { Link } from 'react-router-dom';
import WalletManager from '@/components/WalletManager';
import {
  ShieldCheck, AlertCircle, CheckCircle2, UploadCloud, Trash2,
  FileText, Loader2, Send,
} from 'lucide-react';

const KYC_BADGE = {
  not_started:  { label: 'Не розпочато',        cls: 'bg-muted text-muted-foreground' },
  draft:        { label: 'Чернетка',             cls: 'bg-amber-100 text-amber-800' },
  submitted:    { label: 'Подано на перевірку',  cls: 'bg-sky-100 text-sky-800' },
  under_review: { label: 'На розгляді',          cls: 'bg-sky-100 text-sky-800' },
  approved:     { label: 'Підтверджено',         cls: 'bg-emerald-100 text-emerald-800' },
  rejected:     { label: 'Відхилено',            cls: 'bg-red-100 text-red-700' },
  expired:      { label: 'Прострочено',          cls: 'bg-red-100 text-red-700' },
};

const DOC_TYPES = [
  { value: 'passport',        label: 'Паспорт / ID-картка' },
  { value: 'tax_id',          label: 'РНОКПП (ІПН)' },
  { value: 'iban_proof',      label: 'Підтвердження IBAN' },
  { value: 'selfie',          label: 'Селфі з документом' },
  { value: 'source_of_funds', label: 'Джерело коштів' },
  { value: 'other',           label: 'Інший документ' },
];

const RISK_OPTIONS = [
  { value: 'unknown',      label: 'Не визначено' },
  { value: 'conservative', label: 'Консервативний' },
  { value: 'balanced',     label: 'Збалансований' },
  { value: 'aggressive',   label: 'Агресивний' },
];

const MISSING_LABELS = {
  full_name: 'ПІБ',
  date_of_birth: 'дата народження',
  country: 'країна',
  tax_id: 'РНОКПП',
  iban: 'IBAN',
  'document:passport': 'документ: паспорт',
  'document:tax_id': 'документ: РНОКПП',
};

export default function InvestorProfile() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [docType, setDocType] = useState('passport');
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await lumen.get('/investor/profile');
      const p = r?.data || r;
      setProfile(p);
      setForm({
        full_name: p.full_name || '',
        date_of_birth: p.date_of_birth || '',
        phone: p.phone || '',
        country: p.country || '',
        residency_country: p.residency_country || '',
        tax_id: p.tax_id || '',
        iban: p.iban || '',
        bank_name: p.bank_name || '',
        risk_profile: p.risk_profile || 'unknown',
        accreditation_status: p.accreditation_status || 'none',
      });
    } catch (_e) {
      setError('Не вдалось завантажити профіль');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const kycStatus = profile?.kyc_status || 'not_started';
  const badge = KYC_BADGE[kycStatus] || KYC_BADGE.not_started;
  const canEdit = profile?.can_edit !== false;
  const docs = profile?.documents || [];
  const missing = profile?.missing_for_submit || [];

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {};
      Object.entries(form).forEach(([k, v]) => { if (v !== '' && v !== null) payload[k] = v; });
      await lumen.patch('/investor/profile', payload);
      await load();
      setSaved(true);
      setTimeout(() => setSaved(false), 2400);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось зберегти'));
    } finally {
      setSaving(false);
    }
  };

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('doc_type', docType);
      fd.append('file', file);
      await lumen.post('/investor/kyc/documents', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      try { trackEvent('kyc_started', { surface: 'investor', doc_type: docType }); } catch (_) {}
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось завантажити файл'));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const removeDoc = async (id) => {
    try {
      await lumen.delete(`/investor/kyc/documents/${id}`);
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось видалити документ'));
    }
  };

  const submitKyc = async () => {
    setSubmitting(true);
    setError('');
    try {
      await lumen.post('/investor/kyc/submit');
      try { trackEvent('kyc_completed', { surface: 'investor' }); } catch (_) {}
      await load();
    } catch (e) {
      const det = lumenErrorDetails(e);
      if (det?.missing) {
        setError('Анкета неповна: ' + det.missing.map((m) => MISSING_LABELS[m] || m).join(', '));
      } else {
        setError(lumenError(e, 'Не вдалось подати анкету'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-10 flex justify-center" data-testid="investor-profile-loading">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 md:p-10 max-w-3xl mx-auto" data-testid="investor-profile">
      <header className="mb-8">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Профіль</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Профіль та верифікація</h1>
      </header>

      {error && (
        <div className="mb-6 p-4 rounded-2xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-start gap-2" data-testid="profile-error">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{String(error)}</span>
        </div>
      )}

      {/* ── KYC status ── */}
      <section className="rounded-2xl border border-border bg-card p-6 mb-6" data-testid="kyc-status-card">
        <div className="flex items-center gap-3 mb-3">
          <ShieldCheck className="w-5 h-5 text-[#2E5D4F]" />
          <h2 className="font-semibold">Верифікація (KYC)</h2>
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${badge.cls}`} data-testid="kyc-status-badge">{badge.label}</span>
        </div>
        <p className="text-xs text-muted-foreground mb-3" data-testid="kyc-legal-links">
          Перед поданням ознайомтесь із{' '}
          <Link to="/legal/kyc" target="_blank" className="text-[#2E5D4F] hover:underline">Політикою KYC</Link>{' '}
          та{' '}
          <Link to="/legal/aml" target="_blank" className="text-[#2E5D4F] hover:underline">Політикою AML</Link>.
          Ваші дані обробляються згідно з{' '}
          <Link to="/legal/privacy" target="_blank" className="text-[#2E5D4F] hover:underline">Політикою конфіденційності</Link>.
        </p>
        {kycStatus === 'rejected' && profile?.kyc_notes && (
          <div className="mb-3 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm" data-testid="kyc-reject-reason">
            <p className="font-medium mb-0.5">Причина відхилення:</p>
            <p>{profile.kyc_notes}</p>
          </div>
        )}
        {kycStatus === 'approved' ? (
          <p className="text-sm text-muted-foreground">Ваш профіль інвестора верифіковано. Інвестиції активуються одразу після підтвердження заявки.</p>
        ) : ['submitted', 'under_review'].includes(kycStatus) ? (
          <p className="text-sm text-muted-foreground">Анкета на перевірці у комплаєнс. Зазвичай це займає 1-2 робочих дні. Редагування тимчасово заблоковано.</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Заповніть дані нижче та завантажте документи, щоб інвестиції активувались автоматично після підтвердження заявок.
            </p>
            {missing.length > 0 && (
              <p className="mt-2 text-xs text-amber-700" data-testid="kyc-missing">
                Не вистачає: {missing.map((m) => MISSING_LABELS[m] || m).join(', ')}
              </p>
            )}
            <button
              onClick={submitKyc}
              disabled={submitting || missing.length > 0}
              className="mt-4 inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-40"
              data-testid="kyc-submit"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Подати на перевірку
            </button>
          </>
        )}
      </section>

      {/* ── Wallets (Web3) ── */}
      <WalletManager />

      {/* ── Personal data ── */}
      <section className="rounded-2xl border border-border bg-card p-6 mb-6" data-testid="profile-personal">
        <h2 className="font-semibold mb-4">Особисті дані</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="ПІБ (повністю)" value={form.full_name} onChange={set('full_name')} disabled={!canEdit} testid="profile-full-name" />
          <Field label="Дата народження" type="date" value={form.date_of_birth} onChange={set('date_of_birth')} disabled={!canEdit} testid="profile-dob" />
          <Field label="Email" value={profile?.email || user?.email || ''} disabled />
          <Field label="Телефон" value={form.phone} onChange={set('phone')} placeholder="+380…" disabled={!canEdit} testid="profile-phone" />
          <Field label="Громадянство (країна)" value={form.country} onChange={set('country')} placeholder="UA" disabled={!canEdit} testid="profile-country" />
          <Field label="Податкове резидентство" value={form.residency_country} onChange={set('residency_country')} placeholder="UA" disabled={!canEdit} testid="profile-residency" />
        </div>
      </section>

      {/* ── Tax & banking ── */}
      <section className="rounded-2xl border border-border bg-card p-6 mb-6" data-testid="profile-tax">
        <h2 className="font-semibold mb-4">Податкові та банківські дані</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="РНОКПП (ІПН)" value={form.tax_id} onChange={set('tax_id')} placeholder="1234567890" disabled={!canEdit} testid="profile-tax-id" />
          <Field label="IBAN для виплат" value={form.iban} onChange={set('iban')} placeholder="UA…" disabled={!canEdit} testid="profile-iban" />
          <Field label="Банк" value={form.bank_name} onChange={set('bank_name')} disabled={!canEdit} testid="profile-bank" />
          <label className="block">
            <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Ризик-профіль</span>
            <select
              value={form.risk_profile}
              onChange={(e) => set('risk_profile')(e.target.value)}
              disabled={!canEdit}
              data-testid="profile-risk"
              className="mt-1 w-full h-11 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition disabled:opacity-60"
            >
              {RISK_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={form.accreditation_status === 'self_declared'}
            onChange={(e) => set('accreditation_status')(e.target.checked ? 'self_declared' : 'none')}
            disabled={!canEdit || profile?.accreditation_status === 'verified'}
            data-testid="profile-accreditation"
            className="w-4 h-4 accent-[#2E5D4F]"
          />
          <span>Підтверджую, що розумію ризики інвестування у реальні активи</span>
        </label>
        <div className="mt-6 flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving || !canEdit}
            className="px-6 h-10 rounded-full bg-foreground text-background font-medium hover:opacity-90 transition disabled:opacity-50"
            data-testid="profile-save"
          >
            {saving ? 'Зберігаємо…' : 'Зберегти зміни'}
          </button>
          {saved && <span className="text-sm text-[#2E5D4F] flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Збережено</span>}
        </div>
      </section>

      {/* ── KYC documents ── */}
      <section className="rounded-2xl border border-border bg-card p-6 mb-6" data-testid="kyc-documents">
        <h2 className="font-semibold mb-4">Документи для верифікації</h2>
        {canEdit && (
          <div className="flex flex-col sm:flex-row gap-3 mb-5">
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              data-testid="kyc-doc-type"
              className="h-11 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition"
            >
              {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.heic"
              className="hidden"
              data-testid="kyc-file-input"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="inline-flex items-center gap-2 px-5 h-11 rounded-xl border border-dashed border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm font-medium transition disabled:opacity-50"
              data-testid="kyc-upload"
            >
              {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
              {uploading ? 'Завантажуємо…' : 'Завантажити файл'}
            </button>
          </div>
        )}
        {docs.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="kyc-docs-empty">Документів ще немає. Потрібні щонайменше паспорт та РНОКПП.</p>
        ) : (
          <ul className="divide-y divide-border" data-testid="kyc-docs-list">
            {docs.map((d) => (
              <li key={d.id} className="py-3 flex items-center gap-3">
                <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{d.doc_type_label}</p>
                  <p className="text-xs text-muted-foreground truncate">{d.filename} · {(d.size_bytes / 1024).toFixed(0)} КБ</p>
                </div>
                {canEdit && (
                  <button
                    onClick={() => removeDoc(d.id)}
                    className="p-2 rounded-lg hover:bg-red-50 text-muted-foreground hover:text-red-600 transition"
                    data-testid={`kyc-doc-delete-${d.doc_type}`}
                    title="Видалити"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Security ── */}
      <section className="rounded-2xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-3">Безпека</h2>
        <ul className="text-sm divide-y divide-border">
          <li className="py-3 flex items-center justify-between">
            <div>
              <p className="font-medium">Двофакторна автентифікація</p>
              <p className="text-xs text-muted-foreground">{user?.two_factor_enabled ? 'Увімкнено' : 'Не настроєно'}</p>
            </div>
            <Link to="/account/2fa/setup" className="text-sm text-[#2E5D4F] hover:underline">Налаштувати</Link>
          </li>
          <li className="py-3 flex items-center justify-between">
            <div>
              <p className="font-medium">Резервні коди</p>
              <p className="text-xs text-muted-foreground">Для відновлення доступу</p>
            </div>
            <Link to="/account/2fa/recovery" className="text-sm text-[#2E5D4F] hover:underline">Відкрити</Link>
          </li>
        </ul>
      </section>
    </div>
  );
}

const Field = ({ label, value, onChange, disabled, placeholder, testid, type = 'text' }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</span>
    <input
      type={type}
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onChange && onChange(e.target.value)}
      placeholder={placeholder}
      data-testid={testid}
      className="mt-1 w-full h-11 px-4 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition disabled:opacity-60"
    />
  </label>
);
