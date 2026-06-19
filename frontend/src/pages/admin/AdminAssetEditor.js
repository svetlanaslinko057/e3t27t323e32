import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { lumen, formatUSD, usdFromUah, UAH_PER_USD } from '@/lib/lumenApi';
import { computeEconomics } from '@/lib/lumenEconomics';
import { ArrowLeft, Save, Trash2, Layers } from 'lucide-react';

const EMPTY = {
  title: '',
  category: 'real_estate',
  location: '',
  description: '',
  cover_url: '',
  status: 'draft',
  target_yield: 15,
  horizon_months: 24,
  min_ticket: 50000,
  round_target: 1000000,
  round_deadline: '',
  // Економіка — як частки (0–1). 0.55 = 55% доходу з оренди тощо.
  // Якщо лишити 0, бекенд підставить категорійні дефолти.
  rental_share: 0.55,
  opex_rate: 0.12,
  tax_rate: 0.195,
  platform_fee: 0.02,
  spv_label: '',
};

const CATEGORIES = [
  { value: 'real_estate', label: 'Нерухомість' },
  { value: 'land', label: 'Земля' },
  { value: 'construction', label: 'Будівництво' },
  { value: 'commercial', label: 'Комерція' },
];
const STATUSES = [
  { value: 'draft', label: 'Чернетка' },
  { value: 'open', label: 'Відкрито для участі' },
  { value: 'closed', label: 'Раунд закрито' },
  { value: 'paused', label: 'На паузі' },
];

export default function AdminAssetEditor() {
  const { assetId } = useParams();
  const navigate = useNavigate();
  const isNew = !assetId;
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!isNew);

  useEffect(() => {
    if (isNew) return;
    lumen.get(`/assets/${assetId}`)
      .then((r) => setForm({ ...EMPTY, ...r.data }))
      .catch(() => navigate('/admin/assets'))
      .finally(() => setLoading(false));
  }, [assetId, isNew, navigate]);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        target_yield: Number(form.target_yield),
        horizon_months: Number(form.horizon_months),
        min_ticket: Number(form.min_ticket),
        round_target: Number(form.round_target),
        // Економіка: зберігаємо як числа з плаваючою комою (частки 0–1).
        rental_share: clamp01(Number(form.rental_share)),
        opex_rate:    clamp01(Number(form.opex_rate)),
        tax_rate:     clamp01(Number(form.tax_rate)),
        platform_fee: clamp01(Number(form.platform_fee)),
        spv_label:    (form.spv_label || '').trim(),
      };
      if (isNew) {
        const r = await lumen.post('/admin/assets', payload);
        navigate(`/admin/assets/${r.data.id}`);
      } else {
        await lumen.patch(`/admin/assets/${assetId}`, payload);
      }
    } catch (e) {
      alert(e?.response?.data?.detail || 'Не вдалося зберегти');
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!window.confirm('Видалити актив? Цю дію не можна відмінити.')) return;
    try {
      await lumen.delete(`/admin/assets/${assetId}`);
      navigate('/admin/assets');
    } catch (e) { alert(e?.response?.data?.detail || 'Помилка видалення'); }
  };

  if (loading) return <div className="p-10"><div className="h-8 w-64 animate-pulse rounded" style={{ background: 'var(--token-border)' }} /></div>;

  return (
    <div className="p-6 md:p-10 max-w-3xl mx-auto" data-testid="admin-asset-editor">
      <Link to="/admin/assets" className="inline-flex items-center gap-2 text-sm text-token-muted hover:text-token-primary mb-6"><ArrowLeft className="w-4 h-4" /> Назад</Link>
      <h1 className="text-3xl font-bold tracking-tight">{isNew ? 'Новий актив' : 'Редагування активу'}</h1>
      <p className="mt-1 text-token-muted text-sm">Заповніть ключові параметри. Повний блок медіа та юридичні документи додаєте у вкладці після створення.</p>

      {!isNew && (
        <Link
          to={`/admin/assets/${assetId}/content`}
          className="mt-4 inline-flex items-center gap-2 px-5 h-10 rounded-full text-sm font-medium transition hover:opacity-90"
          style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)', color: 'var(--token-primary)' }}
          data-testid="asset-content-link"
        >
          <Layers className="w-4 h-4" /> Контент і довіра: галерея · відео · команда · ризики · оновлення · звіти · документи · Q&A · SPV
        </Link>
      )}

      <section className="mt-8 space-y-4">
        <Field label="Назва об'єкта" value={form.title} onChange={(v) => set('title', v)} testid="asset-title" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select label="Категорія" value={form.category} onChange={(v) => set('category', v)} options={CATEGORIES} testid="asset-category" />
          <Select label="Статус" value={form.status} onChange={(v) => set('status', v)} options={STATUSES} testid="asset-status" />
        </div>
        <Field label="Локація" value={form.location} onChange={(v) => set('location', v)} placeholder="Напр. Київ, Поділ" testid="asset-location" />
        <Field label="Посилання на фото (обкладинка)" value={form.cover_url} onChange={(v) => set('cover_url', v)} placeholder="https://…" />
        <Textarea label="Опис" value={form.description} onChange={(v) => set('description', v)} testid="asset-description" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Цільова дохідність, % річних" type="number" value={form.target_yield} onChange={(v) => set('target_yield', v)} />
          <Field label="Горизонт, місяців" type="number" value={form.horizon_months} onChange={(v) => set('horizon_months', v)} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Мінімум входу, $ (USD)" type="number" value={form.min_ticket ? Math.round(usdFromUah(form.min_ticket)) : ''} onChange={(v) => set('min_ticket', Math.round(Number(v) * UAH_PER_USD))} />
          <Field label="Цільова сума раунду, $ (USD)" type="number" value={form.round_target ? Math.round(usdFromUah(form.round_target)) : ''} onChange={(v) => set('round_target', Math.round(Number(v) * UAH_PER_USD))} />
        </div>
        <Field label="Дедлайн раунду (ДД/ММ/РРРР або ISO)" value={form.round_deadline} onChange={(v) => set('round_deadline', v)} placeholder="2025-12-31" />
      </section>

      {/* ─── Економіка SPV ──────────────────────────────────────────────── */}
      <section className="mt-10 space-y-4">
        <header>
          <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F]">Економіка SPV</p>
          <h2 className="text-xl font-bold mt-1">Як рахується дохідність інвестора</h2>
          <p className="text-xs text-token-muted mt-1">
            Усі частки задаються як числа від 0 до 1 (напр., 0.55 = 55%). Якщо лишити порожнім — бекенд підставить категорійні дефолти.
          </p>
        </header>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Частка доходу з оренди (0–1)" type="number" value={form.rental_share} onChange={(v) => set('rental_share', v)} placeholder="0.55" testid="asset-rental-share" />
          <Field label="Операційні витрати від оренди (0–1)" type="number" value={form.opex_rate} onChange={(v) => set('opex_rate', v)} placeholder="0.12" testid="asset-opex-rate" />
          <Field label="Ставка податку (0–1)" type="number" value={form.tax_rate} onChange={(v) => set('tax_rate', v)} placeholder="0.195" testid="asset-tax-rate" />
          <Field label="Комісія платформи Lumen (0–1)" type="number" value={form.platform_fee} onChange={(v) => set('platform_fee', v)} placeholder="0.02" testid="asset-platform-fee" />
        </div>
        <Field
          label="Назва SPV (юрособи активу)"
          value={form.spv_label}
          onChange={(v) => set('spv_label', v)}
          placeholder="ТОВ «Lumen-Asset SPV»"
          testid="asset-spv-label"
        />

        {/* Лайв-прев'ю чистого денного доходу на типовий тікет */}
        <EconomicsPreview form={form} />
      </section>

      <div className="mt-8 flex items-center gap-3 flex-wrap">
        <button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 px-6 h-10 rounded-full font-medium text-sm disabled:opacity-50" style={{ background: 'var(--token-primary)', color: 'var(--token-on-primary)' }} data-testid="asset-save">
          <Save className="w-4 h-4" /> {saving ? 'Зберігаємо…' : 'Зберегти'}
        </button>
        {!isNew && (
          <button onClick={remove} className="inline-flex items-center gap-1.5 px-5 h-10 rounded-full text-sm text-red-500" style={{ border: '1px solid var(--token-border)' }}>
            <Trash2 className="w-4 h-4" /> Видалити
          </button>
        )}
      </div>
    </div>
  );
}

const Field = ({ label, value, onChange, placeholder, type = 'text', testid }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-widest text-token-muted">{label}</span>
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid} className="mt-1 w-full h-11 px-4 rounded-xl focus:outline-none" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)', color: 'var(--token-primary)' }} />
  </label>
);
const Textarea = ({ label, value, onChange, testid }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-widest text-token-muted">{label}</span>
    <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={4} data-testid={testid} className="mt-1 w-full px-4 py-3 rounded-xl focus:outline-none" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)', color: 'var(--token-primary)' }} />
  </label>
);
const Select = ({ label, value, onChange, options, testid }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-widest text-token-muted">{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} className="mt-1 w-full h-11 px-4 rounded-xl focus:outline-none" style={{ border: '1px solid var(--token-border)', background: 'var(--token-surface)', color: 'var(--token-primary)' }}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </label>
);

function clamp01(n) {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/**
 * Лайв-прев'ю: показує, скільки інвестор отримає чистими від мінімального тікета
 * при поточних параметрах. Допомагає адміну побачити, чи правильно вибрані частки.
 */
function EconomicsPreview({ form }) {
  const econ = computeEconomics({
    ticket: Number(form.min_ticket) || 100000,
    horizonMonths: Number(form.horizon_months) || 12,
    grossYieldPercent: Number(form.target_yield) || 0,
    rentalShare: Number(form.rental_share),
    opexRate: Number(form.opex_rate),
    taxRate: Number(form.tax_rate),
    platformFee: Number(form.platform_fee),
  });
  return (
    <div className="rounded-xl border p-4 mt-2" style={{ borderColor: 'var(--token-border)', background: 'rgba(46,93,79,0.04)' }} data-testid="economics-preview">
      <p className="text-[10px] uppercase tracking-widest text-[#2E5D4F] font-semibold">Прев'ю розрахунку</p>
      <p className="text-xs text-token-muted mt-1">
        На тікет {formatUSD(usdFromUah(econ.ticket))} за {econ.horizon_years} р.
      </p>
      <div className="grid grid-cols-3 gap-3 mt-3 text-sm">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-token-muted">Чиста IRR</p>
          <p className="font-bold text-[#2E5D4F]">{econ.totals.net_irr_percent.toFixed(1)} %</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-token-muted">Net/рік</p>
          <p className="font-bold">{formatUSD(usdFromUah(econ.annual.rental_net))}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-token-muted">Сумарно</p>
          <p className="font-bold">{formatUSD(usdFromUah(econ.totals.total_net))}</p>
        </div>
      </div>
    </div>
  );
}
