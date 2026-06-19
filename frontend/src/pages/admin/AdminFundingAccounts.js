import { useCallback, useEffect, useState } from 'react';
import { lumen, formatDateUk, lumenError } from '@/lib/lumenApi';
import {
  Landmark, Plus, Loader2, CheckCircle2, AlertCircle, X, Pencil, Save, Trash2,
} from 'lucide-react';

const TYPES = [
  { value: 'bank_transfer', label: 'Банк' },
  { value: 'swift',         label: 'SWIFT' },
  { value: 'crypto_future', label: 'Crypto (пізніше)' },
];
const CURRENCIES = ['UAH', 'USD', 'EUR', 'USDT'];

const EMPTY = {
  name: '', type: 'bank_transfer', bank_name: '', iban: '', swift_code: '',
  beneficiary: '', edrpou: '', currency: 'UAH', purpose_template: '',
  active: true, default: false, notes: '',
};

export default function AdminFundingAccounts() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/funding-accounts');
      setItems(r.data?.items || []);
    } catch (e) { setError(lumenError(e, 'Не вдалось завантажити рахунки')); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (data, id) => {
    setError(''); setFlash('');
    try {
      if (id) {
        await lumen.patch(`/admin/funding-accounts/${id}`, data);
        setFlash('Рахунок оновлено');
      } else {
        await lumen.post('/admin/funding-accounts', data);
        setFlash('Рахунок створено');
      }
      setEditing(null);
      await load();
      setTimeout(() => setFlash(''), 3000);
    } catch (e) { setError(lumenError(e, 'Не вдалось зберегти')); }
  };

  const remove = async (id) => {
    if (!window.confirm('Архівувати цей рахунок? (Інвестори більше не побачать)')) return;
    try {
      await lumen.delete(`/admin/funding-accounts/${id}`);
      setFlash('Рахунок архівовано');
      await load();
      setTimeout(() => setFlash(''), 3000);
    } catch (e) { setError(lumenError(e, 'Не вдалось архівувати')); }
  };

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="admin-funding-accounts">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-token-muted">Реквізити</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Рахунки для прийому платежів</h1>
          <p className="mt-1 text-token-muted">Інвестори бачать тільки активні рахунки потрібної валюти.</p>
        </div>
        <button onClick={() => setEditing({ ...EMPTY })}
          data-testid="btn-new-account"
          className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-[#2E5D4F] text-white text-sm">
          <Plus className="w-4 h-4" /> Новий рахунок
        </button>
      </header>

      {flash && <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> {flash}</div>}
      {error && <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {error}</div>}

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center">
          <Landmark className="w-10 h-10 mx-auto text-muted-foreground/60 mb-3" />
          <p className="font-semibold">Рахунків поки немає</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="funding-accounts-list">
          {items.map((a) => (
            <div key={a.id} data-testid={`fa-${a.id}`}
              className={`rounded-2xl border p-5 ${a.active ? 'border-border bg-card' : 'border-dashed border-border bg-muted/30 opacity-70'}`}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold">{a.name}</p>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted">{a.currency}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{TYPES.find((t) => t.value === a.type)?.label || a.type}</span>
                    {a.default && <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">Default</span>}
                    {!a.active && <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">Архів</span>}
                  </div>
                  {a.bank_name && <p className="text-sm text-muted-foreground mt-1">{a.bank_name}</p>}
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => setEditing({ ...EMPTY, ...a })} className="p-2 hover:bg-muted rounded-lg" data-testid={`btn-edit-${a.id}`}><Pencil className="w-4 h-4" /></button>
                  {a.active && <button onClick={() => remove(a.id)} className="p-2 hover:bg-red-50 text-muted-foreground hover:text-red-600 rounded-lg" data-testid={`btn-remove-${a.id}`}><Trash2 className="w-4 h-4" /></button>}
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
                {a.iban && <Row label="IBAN" value={a.iban} mono />}
                {a.swift_code && <Row label="SWIFT" value={a.swift_code} mono />}
                {a.beneficiary && <Row label="Отримувач" value={a.beneficiary} />}
                {a.edrpou && <Row label="ЄДРПОУ" value={a.edrpou} mono />}
              </div>
              {a.notes && <p className="text-xs text-muted-foreground mt-3">{a.notes}</p>}
            </div>
          ))}
        </div>
      )}

      {editing && (
        <EditDrawer initial={editing} onClose={() => setEditing(null)}
          onSave={(data) => save(data, editing.id)} />
      )}
    </div>
  );
}

const Row = ({ label, value, mono }) => (
  <div className="flex justify-between gap-3 py-0.5">
    <span className="text-muted-foreground text-xs uppercase tracking-widest">{label}</span>
    <span className={`text-right truncate ${mono ? 'font-mono' : ''}`}>{value || '—'}</span>
  </div>
);

function EditDrawer({ initial, onClose, onSave }) {
  const [d, setD] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k, v) => setD((p) => ({ ...p, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!d.name.trim()) { setError('Назва обов\'язкова'); return; }
    setSaving(true); setError('');
    try { await onSave(d); }
    catch (e2) { setError('Помилка збереження'); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="fa-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-xl h-full bg-background border-l border-border shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">{initial.id ? 'Редагувати рахунок' : 'Новий рахунок'}</h2>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-lg"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <Field label="Назва (бачить інвестор)" required>
            <input value={d.name} onChange={(e) => set('name', e.target.value)} data-testid="fa-name"
              className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
          </Field>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Тип">
              <select value={d.type} onChange={(e) => set('type', e.target.value)} data-testid="fa-type"
                className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm">
                {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </Field>
            <Field label="Валюта">
              <select value={d.currency} onChange={(e) => set('currency', e.target.value)} data-testid="fa-currency"
                className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm">
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Банк"><input value={d.bank_name || ''} onChange={(e) => set('bank_name', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" /></Field>
          <Field label="IBAN"><input value={d.iban || ''} onChange={(e) => set('iban', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm font-mono" /></Field>
          <Field label="SWIFT"><input value={d.swift_code || ''} onChange={(e) => set('swift_code', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm font-mono" /></Field>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Отримувач"><input value={d.beneficiary || ''} onChange={(e) => set('beneficiary', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" /></Field>
            <Field label="ЄДРПОУ"><input value={d.edrpou || ''} onChange={(e) => set('edrpou', e.target.value)} className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm font-mono" /></Field>
          </div>
          <Field label="Шаблон призначення платежу">
            <input value={d.purpose_template || ''} onChange={(e) => set('purpose_template', e.target.value)}
              placeholder="Поповнення рахунку, договір №{contract_number}"
              className="w-full h-10 rounded-lg border border-border bg-background px-3 text-sm" />
          </Field>
          <Field label="Внутрішні нотатки (інвестор не бачить)">
            <textarea value={d.notes || ''} onChange={(e) => set('notes', e.target.value)} rows={2}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
          </Field>
          <div className="flex gap-4">
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={d.active} onChange={(e) => set('active', e.target.checked)} /> Активний</label>
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={d.default} onChange={(e) => set('default', e.target.checked)} /> За замовчуванням для валюти</label>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={saving} data-testid="fa-save"
              className="inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white font-medium disabled:opacity-60">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Зберегти
            </button>
            <button type="button" onClick={onClose} className="px-5 h-10 rounded-full border border-border">Скасувати</button>
          </div>
        </form>
      </div>
    </div>
  );
}

const Field = ({ label, required, children }) => (
  <label className="block">
    <span className="text-xs uppercase tracking-widest text-muted-foreground">{label}{required && <span className="text-red-500 ml-1">*</span>}</span>
    <div className="mt-1">{children}</div>
  </label>
);
