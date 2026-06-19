import { useCallback, useEffect, useState } from 'react';
import { lumen, lumenError, formatUAH, usdFromUah, UAH_PER_USD } from '@/lib/lumenApi';
import {
  ShieldCheck, Loader2, Send, TrendingUp, Briefcase, Globe2, Receipt,
  CheckCircle2, AlertCircle, Award, Info,
} from 'lucide-react';

const LEVEL_BADGE = {
  visitor: 'bg-muted text-muted-foreground', retail: 'bg-slate-100 text-slate-700',
  qualified: 'bg-sky-100 text-sky-800', accredited: 'bg-violet-100 text-violet-800',
  professional: 'bg-amber-100 text-amber-900', institutional: 'bg-emerald-100 text-emerald-800',
};
const STATUS_BADGE = {
  pending: 'bg-muted text-muted-foreground', documents_requested: 'bg-amber-100 text-amber-800',
  under_review: 'bg-sky-100 text-sky-800', approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-700', expired: 'bg-red-100 text-red-700',
};
const RISK = [['conservative', 'Консервативний'], ['balanced', 'Збалансований'], ['growth', 'Зростання'], ['aggressive', 'Агресивний']];
const HORIZON = [['short', 'Короткий (<2р)'], ['medium', 'Середній (2–5р)'], ['long', 'Довгий (5р+)']];
const EXP = [['none', 'Немає'], ['beginner', 'Початковий'], ['moderate', 'Помірний'], ['extensive', 'Значний']];
const ASSET_CLASSES = [['real_estate', 'Нерухомість'], ['private_equity', 'Private Equity'], ['funds', 'Фонди'], ['stocks', 'Акції'], ['bonds', 'Облігації']];

const Field = ({ label, children, hint }) => (
  <div>
    <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
    {children}
    {hint && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
  </div>
);
const inputCls = 'w-full h-10 px-3 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-[#2E5D4F]/30';

export default function InvestorAccreditation() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [form, setForm] = useState({ financial: {}, experience: {}, jurisdiction: {}, tax: {} });

  const load = useCallback(async () => {
    try {
      const r = await lumen.get('/investor/accreditation');
      setData(r.data);
      const fin = r.data.financial || {};
      const toUsd = (v) => (v === '' || v == null ? '' : Math.round(usdFromUah(v)));
      setForm({
        financial: {
          ...fin,
          annual_income_uah: toUsd(fin.annual_income_uah),
          net_worth_uah: toUsd(fin.net_worth_uah),
          liquid_assets_uah: toUsd(fin.liquid_assets_uah),
        },
        experience: r.data.experience || {},
        jurisdiction: r.data.jurisdiction || {}, tax: r.data.tax || {},
      });
    } catch (e) { setErr(lumenError(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setB = (block, key, val) => setForm((f) => ({ ...f, [block]: { ...f[block], [key]: val } }));
  const num = (v) => (v === '' || v == null ? null : Number(v));
  const numUah = (v) => (v === '' || v == null ? null : Math.round(Number(v) * UAH_PER_USD));

  const save = async () => {
    setSaving(true); setMsg(''); setErr('');
    try {
      const payload = {
        financial: {
          annual_income_uah: numUah(form.financial.annual_income_uah),
          net_worth_uah: numUah(form.financial.net_worth_uah),
          liquid_assets_uah: numUah(form.financial.liquid_assets_uah),
          investment_horizon: form.financial.investment_horizon || null,
          risk_appetite: form.financial.risk_appetite || null,
        },
        experience: {
          years_investing: num(form.experience.years_investing),
          asset_classes: form.experience.asset_classes || [],
          real_estate_experience: form.experience.real_estate_experience || null,
          private_markets_experience: form.experience.private_markets_experience || null,
        },
        jurisdiction: {
          residency_country: form.jurisdiction.residency_country || null,
          citizenship: form.jurisdiction.citizenship || null,
          is_us_person: !!form.jurisdiction.is_us_person,
          is_pep: !!form.jurisdiction.is_pep,
        },
        tax: { tax_id: form.tax.tax_id || null, tax_residence: form.tax.tax_residence || null, tax_form: form.tax.tax_form || null },
      };
      await lumen.patch('/investor/accreditation/profile', payload);
      setMsg('Профіль збережено ✓'); await load();
    } catch (e) { setErr(lumenError(e)); } finally { setSaving(false); }
  };

  const submit = async () => {
    setSubmitting(true); setMsg(''); setErr('');
    try { await lumen.post('/investor/accreditation/submit'); setMsg('Анкету подано на розгляд ✓'); await load(); }
    catch (e) { setErr(lumenError(e)); } finally { setSubmitting(false); }
  };

  if (loading) return <div className="py-24 flex justify-center"><Loader2 className="w-7 h-7 animate-spin text-muted-foreground" /></div>;

  const acc = data?.accreditation || {};
  const missing = data?.missing_for_submit || [];
  const canSubmit = missing.length === 0 && !['under_review', 'approved'].includes(acc.review_status);
  const toggleClass = (c) => {
    const arr = new Set(form.experience.asset_classes || []);
    arr.has(c) ? arr.delete(c) : arr.add(c);
    setB('experience', 'asset_classes', Array.from(arr));
  };

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6" data-testid="investor-accreditation">
      {/* header / status */}
      <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Phase G11 · Accreditation OS</div>
            <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-[#2E5D4F]" /> Акредитація інвестора</h1>
            <p className="text-sm text-muted-foreground mt-1">Профіль 2.0 визначає, до яких об'єктів і фондів ви маєте доступ.</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className={`text-xs px-3 py-1 rounded-full font-semibold ${LEVEL_BADGE[acc.level] || LEVEL_BADGE.retail}`} data-testid="acc-level">
              <Award className="w-3.5 h-3.5 inline mr-1" />{acc.level_label}
            </span>
            <span className={`text-[11px] px-2.5 py-1 rounded-full font-medium ${STATUS_BADGE[acc.review_status] || STATUS_BADGE.pending}`} data-testid="acc-status">
              {acc.review_status_label}
            </span>
          </div>
        </div>
        {acc.suggested_level && acc.review_status !== 'approved' && (
          <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5" /> На основі ваших даних рекомендований рівень: <b className="text-foreground">{acc.suggested_level}</b>
          </div>
        )}
        {acc.review_status === 'approved' && acc.expires_at && (
          <div className="mt-3 text-xs text-emerald-700 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> Акредитацію підтверджено. Дійсна до {new Date(acc.expires_at).toLocaleDateString('uk-UA')}.
          </div>
        )}
      </div>

      {/* Financial */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold flex items-center gap-2 mb-4"><TrendingUp className="w-4 h-4 text-[#2E5D4F]" /> Фінансовий профіль</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Річний дохід, $"><input data-testid="acc-income" type="number" className={inputCls} value={form.financial.annual_income_uah ?? ''} onChange={(e) => setB('financial', 'annual_income_uah', e.target.value)} /></Field>
          <Field label="Чисті активи (net worth), $"><input data-testid="acc-networth" type="number" className={inputCls} value={form.financial.net_worth_uah ?? ''} onChange={(e) => setB('financial', 'net_worth_uah', e.target.value)} /></Field>
          <Field label="Ліквідні активи, $"><input type="number" className={inputCls} value={form.financial.liquid_assets_uah ?? ''} onChange={(e) => setB('financial', 'liquid_assets_uah', e.target.value)} /></Field>
          <Field label="Горизонт інвестування"><select className={inputCls} value={form.financial.investment_horizon ?? ''} onChange={(e) => setB('financial', 'investment_horizon', e.target.value)}><option value="">—</option>{HORIZON.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Ризик-апетит"><select data-testid="acc-risk" className={inputCls} value={form.financial.risk_appetite ?? ''} onChange={(e) => setB('financial', 'risk_appetite', e.target.value)}><option value="">—</option>{RISK.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        </div>
      </section>

      {/* Experience */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold flex items-center gap-2 mb-4"><Briefcase className="w-4 h-4 text-[#2E5D4F]" /> Досвід інвестування</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Років інвестую"><input data-testid="acc-years" type="number" className={inputCls} value={form.experience.years_investing ?? ''} onChange={(e) => setB('experience', 'years_investing', e.target.value)} /></Field>
          <Field label="Досвід у нерухомості"><select className={inputCls} value={form.experience.real_estate_experience ?? ''} onChange={(e) => setB('experience', 'real_estate_experience', e.target.value)}><option value="">—</option>{EXP.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Досвід у private markets"><select className={inputCls} value={form.experience.private_markets_experience ?? ''} onChange={(e) => setB('experience', 'private_markets_experience', e.target.value)}><option value="">—</option>{EXP.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        </div>
        <Field label="Класи активів" hint="Оберіть усі, з якими працювали">
          <div className="flex flex-wrap gap-2 mt-1">
            {ASSET_CLASSES.map(([v, l]) => {
              const on = (form.experience.asset_classes || []).includes(v);
              return <button type="button" key={v} onClick={() => toggleClass(v)} className={`h-8 px-3 rounded-full text-xs border ${on ? 'bg-[#2E5D4F] text-white border-[#2E5D4F]' : 'border-border hover:bg-muted'}`}>{l}</button>;
            })}
          </div>
        </Field>
      </section>

      {/* Jurisdiction + Tax */}
      <section className="rounded-2xl border border-border bg-card p-5 grid sm:grid-cols-2 gap-6">
        <div>
          <h2 className="font-semibold flex items-center gap-2 mb-4"><Globe2 className="w-4 h-4 text-[#2E5D4F]" /> Юрисдикція</h2>
          <div className="space-y-4">
            <Field label="Країна резидентства"><input className={inputCls} value={form.jurisdiction.residency_country ?? ''} onChange={(e) => setB('jurisdiction', 'residency_country', e.target.value)} placeholder="UA" /></Field>
            <Field label="Громадянство"><input className={inputCls} value={form.jurisdiction.citizenship ?? ''} onChange={(e) => setB('jurisdiction', 'citizenship', e.target.value)} placeholder="UA" /></Field>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.jurisdiction.is_us_person} onChange={(e) => setB('jurisdiction', 'is_us_person', e.target.checked)} /> US person</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!form.jurisdiction.is_pep} onChange={(e) => setB('jurisdiction', 'is_pep', e.target.checked)} /> PEP</label>
            </div>
          </div>
        </div>
        <div>
          <h2 className="font-semibold flex items-center gap-2 mb-4"><Receipt className="w-4 h-4 text-[#2E5D4F]" /> Податки</h2>
          <div className="space-y-4">
            <Field label="Податковий номер (ІПН)"><input className={inputCls} value={form.tax.tax_id ?? ''} onChange={(e) => setB('tax', 'tax_id', e.target.value)} /></Field>
            <Field label="Податкове резидентство"><input className={inputCls} value={form.tax.tax_residence ?? ''} onChange={(e) => setB('tax', 'tax_residence', e.target.value)} placeholder="UA" /></Field>
            <Field label="Податкова форма"><select className={inputCls} value={form.tax.tax_form ?? ''} onChange={(e) => setB('tax', 'tax_form', e.target.value)}><option value="">—</option><option value="none">Немає</option><option value="w8">W-8 (нерезидент US)</option><option value="w9">W-9 (US)</option></select></Field>
          </div>
        </div>
      </section>

      {/* missing + actions */}
      {missing.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 flex items-start gap-2" data-testid="acc-missing">
          <AlertCircle className="w-4 h-4 mt-0.5" />
          <div>Для подання заповніть: {missing.map((m) => m.split('.').pop()).join(', ')}</div>
        </div>
      )}
      {(msg || err) && <p className={`text-sm ${err ? 'text-red-600' : 'text-emerald-600'}`}>{err || msg}</p>}
      <div className="flex flex-wrap gap-3">
        <button onClick={save} disabled={saving} data-testid="acc-save" className="h-10 px-5 rounded-lg bg-card border border-border font-medium text-sm hover:bg-muted inline-flex items-center gap-2">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Зберегти профіль
        </button>
        <button onClick={submit} disabled={!canSubmit || submitting} data-testid="acc-submit" className="h-10 px-5 rounded-lg bg-[#2E5D4F] text-white font-medium text-sm hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-2">
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Подати на акредитацію
        </button>
      </div>
    </div>
  );
}
