import { useCallback, useEffect, useState } from 'react';
import { lumen, formatUAH, formatDateUk, API, lumenError } from '@/lib/lumenApi';
import {
  FileSignature, FileText, Download, Loader2, CheckCircle2, AlertCircle,
  XCircle, ScrollText, Plus, Save, Link2, Copy, Trash2,
} from 'lucide-react';

const STATUS_BADGE = {
  draft:     { label: 'Чернетка',        cls: 'bg-muted text-muted-foreground' },
  generated: { label: 'Згенеровано',     cls: 'bg-muted text-muted-foreground' },
  sent:      { label: 'Надіслано',       cls: 'bg-amber-100 text-amber-800' },
  viewed:    { label: 'Переглянуто',     cls: 'bg-sky-100 text-sky-800' },
  signed:    { label: 'Підписано',       cls: 'bg-emerald-100 text-emerald-800' },
  expired:   { label: 'Прострочено',     cls: 'bg-red-100 text-red-700' },
  cancelled: { label: 'Скасовано',       cls: 'bg-red-100 text-red-700' },
};

const FILTERS = [
  { value: '',          label: 'Всі' },
  { value: 'sent',      label: 'Надіслані' },
  { value: 'viewed',    label: 'Переглянуті' },
  { value: 'signed',    label: 'Підписані' },
  { value: 'cancelled', label: 'Скасовані' },
  { value: 'expired',   label: 'Прострочені' },
];

const KIND_OPTIONS = [
  { value: 'investment_agreement', label: 'Договір інвестування' },
  { value: 'spv_participation',    label: 'Договір участі в SPV' },
  { value: 'co_investment',        label: 'Договір спільного інвестування' },
];

export default function AdminContracts() {
  const [tab, setTab] = useState('contracts');

  return (
    <div className="p-6 md:p-10" data-testid="admin-contracts">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-widest text-token-muted">Юридичний контур</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Договори</h1>
      </header>

      <div className="flex gap-2 mb-6" data-testid="contracts-tabs">
        <TabBtn active={tab === 'contracts'} onClick={() => setTab('contracts')} testid="tab-contracts">
          <FileSignature className="w-4 h-4" /> Реєстр договорів
        </TabBtn>
        <TabBtn active={tab === 'templates'} onClick={() => setTab('templates')} testid="tab-templates">
          <ScrollText className="w-4 h-4" /> Шаблони
        </TabBtn>
      </div>

      {tab === 'contracts' ? <ContractsRegistry /> : <TemplatesManager />}
    </div>
  );
}

const TabBtn = ({ active, onClick, children, testid }) => (
  <button
    onClick={onClick}
    data-testid={testid}
    className={`inline-flex items-center gap-2 px-4 h-10 rounded-full text-sm font-medium border transition ${
      active ? 'bg-foreground text-background border-foreground'
             : 'border-border hover:border-[#2E5D4F]'
    }`}
  >
    {children}
  </button>
);

/* ────────────────────────── Contracts registry ────────────────────────── */

function ContractsRegistry() {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async (f = filter) => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/contracts' + (f ? `?status=${f}` : ''));
      setItems(r.data?.items || []);
      setCounts(r.data?.counts || {});
    } catch (_e) {
      setError('Не вдалось завантажити реєстр договорів');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    setDetailLoading(true);
    setError('');
    setCancelReason('');
    try {
      const r = await lumen.get(`/admin/contracts/${id}`);
      setSelected(r.data);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось відкрити договір'));
    } finally {
      setDetailLoading(false);
    }
  };

  const cancel = async () => {
    if (!selected || !cancelReason.trim()) return;
    setActing(true);
    setError('');
    try {
      await lumen.post(`/admin/contracts/${selected.id}/cancel`, { reason: cancelReason.trim() });
      setFlash('Договір скасовано, пов\'язану інвестицію зупинено');
      setTimeout(() => setFlash(''), 4000);
      await openDetail(selected.id);
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось скасувати договір'));
    } finally {
      setActing(false);
    }
  };

  const cancellable = selected && ['draft', 'generated', 'sent', 'viewed', 'expired'].includes(selected.status);
  const viewLinkAvailable = selected && !['cancelled', 'expired'].includes(selected.status);
  const hasActiveViewLink = !!(selected && selected.view_token && selected.view_token_expires_at && new Date(selected.view_token_expires_at) > new Date());
  const publicSiteOrigin = (typeof window !== 'undefined' ? window.location.origin : '');

  const issueViewLink = async () => {
    if (!selected) return;
    setActing(true);
    setError('');
    try {
      const r = await lumen.post(`/admin/contracts/${selected.id}/view-link`, { expires_in_days: 30 });
      setFlash(`Публічну ссилку згенеровано: ${r.data?.view_url || ''}`);
      setTimeout(() => setFlash(''), 6000);
      await openDetail(selected.id);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось згенерувати посилання'));
    } finally {
      setActing(false);
    }
  };

  const revokeViewLink = async () => {
    if (!selected) return;
    if (!window.confirm('Відкликати публічну ссилку? Інвестор не зможе підписати по ній.')) return;
    setActing(true);
    setError('');
    try {
      await lumen.delete(`/admin/contracts/${selected.id}/view-link`);
      setFlash('Публічну ссилку відкликано');
      setTimeout(() => setFlash(''), 4000);
      await openDetail(selected.id);
    } catch (e) {
      setError(lumenError(e, 'Не вдалось відкликати посилання'));
    } finally {
      setActing(false);
    }
  };

  const copyPublicLink = () => {
    if (!selected?.view_token) return;
    const url = `${publicSiteOrigin}/c/view/${selected.view_token}`;
    try {
      navigator.clipboard.writeText(url);
      setFlash('Ссилку скопійовано в буфер');
      setTimeout(() => setFlash(''), 3000);
    } catch (_e) {
      window.prompt('Скопіюйте ссилку вручну:', url);
    }
  };

  return (
    <div>
      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="admin-contracts-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="admin-contracts-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-6" data-testid="contracts-filters">
        {FILTERS.map((f) => {
          const count = f.value === ''
            ? Object.values(counts).reduce((a, b) => a + (b || 0), 0)
            : (counts[f.value] || 0);
          return (
            <button
              key={f.value || 'all'}
              onClick={() => { setFilter(f.value); setSelected(null); }}
              className={`px-4 h-9 rounded-full text-sm font-medium border transition ${
                filter === f.value ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'
              }`}
              data-testid={`contracts-filter-${f.value || 'all'}`}
            >
              {f.label}{count > 0 && <span className="ml-1.5 opacity-70">{count}</span>}
            </button>
          );
        })}
      </div>

      <div className="grid xl:grid-cols-5 gap-6">
        <div className="xl:col-span-3">
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            {loading ? (
              <div className="p-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            ) : items.length === 0 ? (
              <div className="p-8 text-center text-sm text-muted-foreground" data-testid="admin-contracts-empty">
                <FileText className="w-6 h-6 mx-auto mb-2 opacity-40" /> Договорів не знайдено
              </div>
            ) : (
              <table className="w-full text-sm" data-testid="admin-contracts-table">
                <thead className="bg-muted/40 text-xs uppercase tracking-widest text-muted-foreground">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">№ / Інвестор</th>
                    <th className="text-left px-4 py-3 font-medium">Актив</th>
                    <th className="text-right px-4 py-3 font-medium">Сума</th>
                    <th className="text-left px-4 py-3 font-medium">Статус</th>
                    <th className="text-right px-4 py-3 font-medium">Дата</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((c) => {
                    const b = STATUS_BADGE[c.status] || STATUS_BADGE.generated;
                    return (
                      <tr
                        key={c.id}
                        onClick={() => openDetail(c.id)}
                        className={`cursor-pointer hover:bg-muted/40 transition ${selected?.id === c.id ? 'bg-muted/60' : ''}`}
                        data-testid={`admin-contract-row-${c.id}`}
                      >
                        <td className="px-4 py-3">
                          <p className="font-medium">{c.number}</p>
                          <p className="text-xs text-muted-foreground">{c.investor_email || c.investor_name}</p>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{c.asset_title}</td>
                        <td className="px-4 py-3 text-right font-mono">{formatUAH(c.amount)}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${b.cls}`}>{b.label}</span>
                        </td>
                        <td className="px-4 py-3 text-right text-muted-foreground whitespace-nowrap">{formatDateUk(c.generated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="xl:col-span-2">
          {detailLoading ? (
            <div className="rounded-2xl border border-border bg-card p-10 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : !selected ? (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="admin-contract-detail-empty">
              <FileSignature className="w-6 h-6 mx-auto mb-2 opacity-40" />
              Оберіть договір з реєстру
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card p-6" data-testid="admin-contract-detail">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="font-bold">{selected.number}</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">{selected.template_kind_label}</p>
                </div>
                {(() => {
                  const b = STATUS_BADGE[selected.status] || STATUS_BADGE.generated;
                  return <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${b.cls}`} data-testid="admin-contract-detail-status">{b.label}</span>;
                })()}
              </div>

              <dl className="space-y-2.5 text-sm mb-5">
                <Row label="Інвестор" value={`${selected.investor_name || '—'} (${selected.investor_email || '—'})`} />
                <Row label="Актив" value={selected.asset_title} />
                <Row label="Сума" value={formatUAH(selected.amount)} />
                <Row label="Статус інвестиції" value={selected.investment_status || '—'} />
                <Row label="Згенеровано" value={formatDateUk(selected.generated_at)} />
                {selected.signed_at && <Row label="Підписано" value={formatDateUk(selected.signed_at)} />}
                {selected.cancel_reason && <Row label="Причина скасування" value={selected.cancel_reason} />}
              </dl>

              <a
                href={`${API}/contracts/${selected.id}/pdf`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-4 h-9 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm transition mb-5"
                data-testid="admin-contract-pdf"
              >
                <Download className="w-3.5 h-3.5" /> Завантажити PDF
              </a>

              <h3 className="font-semibold text-sm mb-2">Підписи ({(selected.signatures || []).length})</h3>
              {(selected.signatures || []).length === 0 ? (
                <p className="text-sm text-muted-foreground mb-5">Підписів ще немає</p>
              ) : (
                <ul className="divide-y divide-border mb-5" data-testid="admin-contract-signatures">
                  {selected.signatures.map((s) => (
                    <li key={s.id} className="py-2.5 text-sm">
                      <p className="font-medium">{formatDateUk(s.signed_at)} · {s.status}</p>
                      <p className="text-xs text-muted-foreground font-mono truncate">IP: {s.ip || '—'}</p>
                      <p className="text-[11px] text-muted-foreground truncate">{s.user_agent || '—'}</p>
                    </li>
                  ))}
                </ul>
              )}

              {/* Phase S1.2 — Public view-token link (sign without login) */}
              {viewLinkAvailable && (
                <div className="border-t border-border pt-4 pb-4 mb-1" data-testid="admin-contract-view-link-block">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-sm flex items-center gap-1.5">
                      <Link2 className="w-4 h-4" /> Публічне посилання для підпису
                    </h3>
                    {hasActiveViewLink && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                        <CheckCircle2 className="w-3 h-3" /> Активне
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mb-3 leading-relaxed">
                    Одноразова ссилка для підпису договору без входу до кабінету. Зручно для перших інвесторів,
                    які ще не пройшли акредитацію. Термін дії — 30 днів, IP та email фіксуються в аудиті.
                  </p>
                  {hasActiveViewLink ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/40 border border-border font-mono text-[11px] break-all">
                        {publicSiteOrigin}/c/view/{selected.view_token}
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Дійсне до {formatDateUk(selected.view_token_expires_at)}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={copyPublicLink}
                          disabled={acting}
                          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm transition"
                          data-testid="admin-contract-copy-view-link"
                        >
                          <Copy className="w-3.5 h-3.5" /> Скопіювати
                        </button>
                        <button
                          onClick={issueViewLink}
                          disabled={acting}
                          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full border border-border hover:border-[#2E5D4F] hover:text-[#2E5D4F] text-sm transition disabled:opacity-40"
                          data-testid="admin-contract-rotate-view-link"
                        >
                          {acting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Link2 className="w-3.5 h-3.5" />}
                          Оновити токен
                        </button>
                        <button
                          onClick={revokeViewLink}
                          disabled={acting}
                          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full border border-red-200 text-red-600 hover:bg-red-50 text-sm transition disabled:opacity-40"
                          data-testid="admin-contract-revoke-view-link"
                        >
                          <Trash2 className="w-3.5 h-3.5" /> Відкликати
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={issueViewLink}
                      disabled={acting}
                      className="inline-flex items-center gap-2 px-4 h-10 rounded-full bg-foreground text-background text-sm font-medium hover:bg-[#2E5D4F] transition disabled:opacity-40"
                      data-testid="admin-contract-issue-view-link"
                    >
                      {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />}
                      Згенерувати публічне посилання
                    </button>
                  )}
                </div>
              )}

              {cancellable ? (
                <div className="border-t border-border pt-4 space-y-3">
                  <label className="block">
                    <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Причина скасування (обов'язкова)</span>
                    <textarea
                      value={cancelReason}
                      onChange={(e) => setCancelReason(e.target.value)}
                      rows={2}
                      className="mt-1 w-full px-3 py-2 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                      data-testid="admin-contract-cancel-reason"
                    />
                  </label>
                  <button
                    onClick={cancel}
                    disabled={acting || !cancelReason.trim()}
                    className="inline-flex items-center gap-2 px-5 h-10 rounded-full border border-red-300 text-red-600 text-sm font-medium hover:bg-red-50 transition disabled:opacity-40"
                    data-testid="admin-contract-cancel-btn"
                  >
                    {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                    Скасувати договір
                  </button>
                  <p className="text-[11px] text-muted-foreground">Пов'язана інвестиція буде зупинена. Підписані договори скасувати неможливо.</p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground border-t border-border pt-4">
                  {selected.status === 'signed'
                    ? 'Підписаний договір скасувати неможливо.'
                    : 'Дії для цього статусу недоступні.'}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const Row = ({ label, value }) => (
  <div>
    <dt className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</dt>
    <dd className="mt-0.5">{value || '—'}</dd>
  </div>
);

/* ─────────────────────────── Templates manager ─────────────────────────── */

function TemplatesManager() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // template being edited
  const [isNew, setIsNew] = useState(false);
  const [form, setForm] = useState({ name: '', kind: 'investment_agreement', body_text: '', active: true });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [flash, setFlash] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await lumen.get('/admin/contract-templates');
      setItems(r.data?.items || []);
    } catch (_e) {
      setError('Не вдалось завантажити шаблони');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pick = (t) => {
    setSelected(t);
    setIsNew(false);
    setError('');
    setForm({ name: t.name || '', kind: t.kind, body_text: t.body_text || '', active: t.active !== false });
  };

  const startNew = () => {
    setSelected(null);
    setIsNew(true);
    setError('');
    setForm({ name: '', kind: 'investment_agreement', body_text: '# ДОГОВІР № {{contract_number}}\nм. Київ — {{date}}\n\n## 1. Предмет договору\n…', active: true });
  };

  const save = async () => {
    if (!form.name.trim() || !form.body_text.trim()) {
      setError('Назва та текст шаблону обов\'язкові');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (isNew) {
        const r = await lumen.post('/admin/contract-templates', form);
        setFlash('Шаблон створено');
        setIsNew(false);
        setSelected(r.data);
      } else if (selected) {
        const r = await lumen.patch(`/admin/contract-templates/${selected.id}`, form);
        setFlash(`Збережено (версія ${r.data?.version})`);
        setSelected(r.data);
      }
      setTimeout(() => setFlash(''), 4000);
      await load();
    } catch (e) {
      setError(lumenError(e, 'Не вдалось зберегти шаблон'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="templates-manager">
      {flash && (
        <div className="mb-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="templates-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="templates-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <button
            onClick={startNew}
            className="mb-3 inline-flex items-center gap-2 px-4 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition"
            data-testid="template-new-btn"
          >
            <Plus className="w-4 h-4" /> Новий шаблон
          </button>
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            {loading ? (
              <div className="p-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
            ) : (
              <ul className="divide-y divide-border" data-testid="templates-list">
                {items.map((t) => (
                  <li key={t.id}>
                    <button
                      onClick={() => pick(t)}
                      className={`w-full text-left px-4 py-3 hover:bg-muted/50 transition ${selected?.id === t.id ? 'bg-muted/60' : ''}`}
                      data-testid={`template-item-${t.kind}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-medium text-sm truncate">{t.name}</p>
                        <span className={`text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap ${t.active !== false ? 'bg-emerald-100 text-emerald-800' : 'bg-muted text-muted-foreground'}`}>
                          {t.active !== false ? 'активний' : 'вимкнено'}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{t.kind_label} · v{t.version}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="lg:col-span-3">
          {!selected && !isNew ? (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground" data-testid="template-editor-empty">
              <ScrollText className="w-6 h-6 mx-auto mb-2 opacity-40" />
              Оберіть шаблон або створіть новий
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card p-6 space-y-4" data-testid="template-editor">
              <div className="grid sm:grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Назва</span>
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="mt-1 w-full h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                    data-testid="template-name-input"
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] uppercase tracking-widest text-muted-foreground">Тип</span>
                  <select
                    value={form.kind}
                    onChange={(e) => setForm({ ...form, kind: e.target.value })}
                    className="mt-1 w-full h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm"
                    data-testid="template-kind-select"
                  >
                    {KIND_OPTIONS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                  </select>
                </label>
              </div>

              <label className="block">
                <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                  Текст договору (плейсхолдери: {'{{investor_name}}, {{amount}}, {{asset_title}}, {{ownership_percent}}, {{contract_number}}, {{date}}'} …)
                </span>
                <textarea
                  value={form.body_text}
                  onChange={(e) => setForm({ ...form, body_text: e.target.value })}
                  rows={16}
                  className="mt-1 w-full px-3 py-2 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm font-mono"
                  data-testid="template-body-input"
                />
              </label>

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer select-none text-sm">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                    className="w-4 h-4 accent-[#2E5D4F]"
                    data-testid="template-active-checkbox"
                  />
                  Шаблон активний
                </label>
                <button
                  onClick={save}
                  disabled={saving}
                  className="inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
                  data-testid="template-save-btn"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {isNew ? 'Створити шаблон' : 'Зберегти (нова версія)'}
                </button>
              </div>
              {!isNew && selected && (
                <p className="text-[11px] text-muted-foreground">
                  Поточна версія: v{selected.version}. Зміна тексту автоматично підвищує версію. Вже згенеровані договори не змінюються.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
