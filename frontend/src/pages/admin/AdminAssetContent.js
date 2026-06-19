import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { lumen, formatDateUk, lumenError, usdFromUah, UAH_PER_USD } from '@/lib/lumenApi';
import {
  ArrowLeft, Save, Plus, Trash2, Loader2, CheckCircle2, AlertCircle,
  Image as ImageIcon, Users, AlertTriangle, Newspaper, FileText, Inbox,
  MessageCircleQuestion, Landmark, Pin, Upload, EyeOff, Eye, Sparkles,
  Megaphone, Vote,
} from 'lucide-react';

const TABS = [
  { key: 'media',   label: 'Медіа',          icon: ImageIcon },
  { key: 'team',    label: 'Команда',        icon: Users },
  { key: 'risks',   label: 'Ризики й вихід', icon: AlertTriangle },
  { key: 'intel',   label: 'Marketplace 2.0', icon: Sparkles },
  { key: 'community', label: 'Спільнота',    icon: Megaphone },
  { key: 'updates', label: 'Оновлення',      icon: Newspaper },
  { key: 'reports', label: 'Звіти',          icon: FileText },
  { key: 'docs',    label: 'Документи',      icon: Inbox },
  { key: 'qa',      label: 'Q&A',            icon: MessageCircleQuestion },
  { key: 'spv',     label: 'SPV',            icon: Landmark },
];

export default function AdminAssetContent() {
  const { assetId } = useParams();
  const [asset, setAsset] = useState(null);
  const [tab, setTab] = useState('media');
  const [flash, setFlash] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    lumen.get(`/assets/${assetId}`).then((r) => setAsset(r.data)).catch(() => setAsset(null));
  }, [assetId]);

  const notify = (msg) => { setFlash(msg); setTimeout(() => setFlash(''), 4000); };
  const fail = (e, fallback) => setError(lumenError(e, fallback));

  if (!asset) {
    return <div className="p-10"><div className="h-8 w-64 animate-pulse rounded" style={{ background: 'var(--token-border)' }} /></div>;
  }

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto" data-testid="admin-asset-content">
      <Link to={`/admin/assets/${assetId}`} className="inline-flex items-center gap-2 text-sm text-token-muted hover:text-token-primary mb-6">
        <ArrowLeft className="w-4 h-4" /> До редактора активу
      </Link>
      <p className="text-xs uppercase tracking-widest text-token-muted">Контент і довіра</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight">{asset.title}</h1>
      <p className="mt-1 text-token-muted text-sm">Інформаційний шар активу: галерея, відео, команда, ризики, оновлення, звіти, документи, Q&A та SPV.</p>

      <div className="mt-6 flex gap-2 flex-wrap" data-testid="content-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setError(''); }}
            className={`inline-flex items-center gap-1.5 px-3.5 h-9 rounded-full text-sm font-medium border transition ${tab === t.key ? 'bg-foreground text-background border-foreground' : 'border-border hover:border-[#2E5D4F]'}`}
            data-testid={`content-tab-${t.key}`}
          >
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {flash && (
        <div className="mt-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm flex items-center gap-2" data-testid="content-flash">
          <CheckCircle2 className="w-4 h-4" /> {flash}
        </div>
      )}
      {error && (
        <div className="mt-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-center gap-2" data-testid="content-error">
          <AlertCircle className="w-4 h-4" /> {String(error)}
        </div>
      )}

      <div className="mt-6">
        {tab === 'media' && <MediaTab asset={asset} setAsset={setAsset} notify={notify} fail={fail} />}
        {tab === 'team' && <TeamTab asset={asset} setAsset={setAsset} notify={notify} fail={fail} />}
        {tab === 'risks' && <RisksTab asset={asset} setAsset={setAsset} notify={notify} fail={fail} />}
        {tab === 'intel' && <IntelTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'community' && <CommunityTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'updates' && <UpdatesTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'reports' && <ReportsTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'docs' && <DocsTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'qa' && <QaTab assetId={assetId} notify={notify} fail={fail} />}
        {tab === 'spv' && <SpvTab assetId={assetId} notify={notify} fail={fail} />}
      </div>
    </div>
  );
}

/* ──────────────────────────── shared inputs ──────────────────────────── */

const Input = ({ value, onChange, placeholder, testid, className = '' }) => (
  <input value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid}
    className={`h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm w-full ${className}`} />
);

const SaveBtn = ({ onClick, saving, label = 'Зберегти', testid }) => (
  <button onClick={onClick} disabled={saving} data-testid={testid}
    className="inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} {label}
  </button>
);

/* ──────────────────────────── Media (gallery + videos) ──────────────────────────── */

function MediaTab({ asset, setAsset, notify, fail }) {
  const [gallery, setGallery] = useState(asset.gallery || []);
  const [videos, setVideos] = useState(asset.videos || []);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const r = await lumen.patch(`/admin/assets/${asset.id}/content`, { gallery, videos });
      setGallery(r.data.gallery || []);
      setVideos(r.data.videos || []);
      setAsset((p) => ({ ...p, gallery: r.data.gallery, videos: r.data.videos }));
      notify('Медіа збережено');
    } catch (e) { fail(e, 'Не вдалось зберегти медіа'); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-6" data-testid="media-tab">
      <section className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold mb-1">Фотогалерея</h2>
        <p className="text-xs text-muted-foreground mb-4">Декілька фото замість однієї обкладинки. Перше фото — головне.</p>
        <div className="space-y-3">
          {gallery.map((g, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="w-16 h-12 rounded-lg border border-border bg-muted shrink-0" style={g.url ? { backgroundImage: `url(${g.url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined} />
              <div className="flex-1 grid sm:grid-cols-2 gap-2">
                <Input value={g.url} onChange={(v) => setGallery(gallery.map((x, j) => j === i ? { ...x, url: v } : x))} placeholder="https://… (URL фото)" testid={`gallery-url-${i}`} />
                <Input value={g.caption} onChange={(v) => setGallery(gallery.map((x, j) => j === i ? { ...x, caption: v } : x))} placeholder="Підпис (необов'язково)" />
              </div>
              <button onClick={() => setGallery(gallery.filter((_, j) => j !== i))} className="p-2.5 text-red-500 hover:bg-red-50 rounded-lg transition" data-testid={`gallery-remove-${i}`}>
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
        <button onClick={() => setGallery([...gallery, { url: '', caption: '' }])} className="mt-3 inline-flex items-center gap-1.5 text-sm text-[#2E5D4F] hover:underline" data-testid="gallery-add">
          <Plus className="w-4 h-4" /> Додати фото
        </button>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold mb-1">Відео</h2>
        <p className="text-xs text-muted-foreground mb-4">YouTube / Vimeo посилання — плеєр вбудується автоматично.</p>
        <div className="space-y-3">
          {videos.map((v, i) => (
            <div key={i} className="flex gap-2 items-start">
              <div className="flex-1 grid sm:grid-cols-2 gap-2">
                <Input value={v.url} onChange={(val) => setVideos(videos.map((x, j) => j === i ? { ...x, url: val } : x))} placeholder="https://youtube.com/watch?v=…" testid={`video-url-${i}`} />
                <Input value={v.title} onChange={(val) => setVideos(videos.map((x, j) => j === i ? { ...x, title: val } : x))} placeholder="Назва відео" />
              </div>
              <button onClick={() => setVideos(videos.filter((_, j) => j !== i))} className="p-2.5 text-red-500 hover:bg-red-50 rounded-lg transition">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
        <button onClick={() => setVideos([...videos, { url: '', title: '' }])} className="mt-3 inline-flex items-center gap-1.5 text-sm text-[#2E5D4F] hover:underline" data-testid="video-add">
          <Plus className="w-4 h-4" /> Додати відео
        </button>
      </section>

      <SaveBtn onClick={save} saving={saving} label="Зберегти медіа" testid="media-save" />
    </div>
  );
}

/* ──────────────────────────── Team ──────────────────────────── */

function TeamTab({ asset, setAsset, notify, fail }) {
  const [team, setTeam] = useState(asset.team || []);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const r = await lumen.patch(`/admin/assets/${asset.id}/content`, { team });
      setTeam(r.data.team || []);
      setAsset((p) => ({ ...p, team: r.data.team }));
      notify('Команду збережено');
    } catch (e) { fail(e, 'Не вдалось зберегти команду'); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-4" data-testid="team-tab">
      {team.map((m, i) => (
        <div key={i} className="rounded-2xl border border-border bg-card p-4 space-y-2">
          <div className="grid sm:grid-cols-3 gap-2">
            <Input value={m.name} onChange={(v) => setTeam(team.map((x, j) => j === i ? { ...x, name: v } : x))} placeholder="Ім'я та прізвище" testid={`team-name-${i}`} />
            <Input value={m.role} onChange={(v) => setTeam(team.map((x, j) => j === i ? { ...x, role: v } : x))} placeholder="Роль (напр. Керівник проєкту)" />
            <Input value={m.photo_url} onChange={(v) => setTeam(team.map((x, j) => j === i ? { ...x, photo_url: v } : x))} placeholder="URL фото (необов'язково)" />
          </div>
          <div className="flex gap-2">
            <Input value={m.bio} onChange={(v) => setTeam(team.map((x, j) => j === i ? { ...x, bio: v } : x))} placeholder="Коротке біо / досвід" />
            <button onClick={() => setTeam(team.filter((_, j) => j !== i))} className="p-2.5 text-red-500 hover:bg-red-50 rounded-lg transition shrink-0">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
      <button onClick={() => setTeam([...team, { name: '', role: '', photo_url: '', bio: '' }])} className="inline-flex items-center gap-1.5 text-sm text-[#2E5D4F] hover:underline" data-testid="team-add">
        <Plus className="w-4 h-4" /> Додати учасника
      </button>
      <div><SaveBtn onClick={save} saving={saving} label="Зберегти команду" testid="team-save" /></div>
    </div>
  );
}

/* ──────────────────────────── Risks + exit ──────────────────────────── */

function RisksTab({ asset, setAsset, notify, fail }) {
  const [risks, setRisks] = useState(asset.risks || []);
  const [exitStrategy, setExitStrategy] = useState(asset.exit_strategy || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const r = await lumen.patch(`/admin/assets/${asset.id}/content`, { risks, exit_strategy: exitStrategy });
      setRisks(r.data.risks || []);
      setAsset((p) => ({ ...p, risks: r.data.risks, exit_strategy: r.data.exit_strategy }));
      notify('Ризики та стратегію виходу збережено');
    } catch (e) { fail(e, 'Не вдалось зберегти'); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-5" data-testid="risks-tab">
      <section className="rounded-2xl border border-border bg-card p-5 space-y-3">
        <h2 className="font-semibold">Ризики</h2>
        {risks.map((r, i) => (
          <div key={i} className="flex gap-2 items-start">
            <div className="flex-1 grid sm:grid-cols-5 gap-2">
              <Input className="sm:col-span-2" value={r.title} onChange={(v) => setRisks(risks.map((x, j) => j === i ? { ...x, title: v } : x))} placeholder="Назва ризику" testid={`risk-title-${i}`} />
              <Input className="sm:col-span-2" value={r.description} onChange={(v) => setRisks(risks.map((x, j) => j === i ? { ...x, description: v } : x))} placeholder="Опис / мітигація" />
              <select value={r.severity || 'medium'} onChange={(e) => setRisks(risks.map((x, j) => j === i ? { ...x, severity: e.target.value } : x))}
                className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm">
                <option value="low">низький</option>
                <option value="medium">середній</option>
                <option value="high">високий</option>
              </select>
            </div>
            <button onClick={() => setRisks(risks.filter((_, j) => j !== i))} className="p-2.5 text-red-500 hover:bg-red-50 rounded-lg transition shrink-0">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
        <button onClick={() => setRisks([...risks, { title: '', description: '', severity: 'medium' }])} className="inline-flex items-center gap-1.5 text-sm text-[#2E5D4F] hover:underline" data-testid="risk-add">
          <Plus className="w-4 h-4" /> Додати ризик
        </button>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5">
        <h2 className="font-semibold mb-1">Стратегія виходу</h2>
        <p className="text-xs text-muted-foreground mb-3">Як інвестор отримує гроші назад.</p>
        <textarea value={exitStrategy} onChange={(e) => setExitStrategy(e.target.value)} rows={5}
          className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm"
          data-testid="exit-strategy-input" />
      </section>

      <SaveBtn onClick={save} saving={saving} label="Зберегти" testid="risks-save" />
    </div>
  );
}

/* ──────────────────────────── Updates ──────────────────────────── */

const EMPTY_UPDATE = { title: '', body: '', kind: 'general', pinned: false, published: true };

function UpdatesTab({ assetId, notify, fail }) {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(EMPTY_UPDATE);
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() =>
    lumen.get(`/admin/assets/${assetId}/updates`).then((r) => setItems(r.data?.items || [])).catch(() => {}), [assetId]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      if (editId) {
        await lumen.patch(`/admin/asset-updates/${editId}`, form);
        notify('Оновлення збережено');
      } else {
        await lumen.post(`/admin/assets/${assetId}/updates`, form);
        notify('Оновлення опубліковано');
      }
      setForm(EMPTY_UPDATE);
      setEditId(null);
      await load();
    } catch (e) { fail(e, 'Не вдалось зберегти оновлення'); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try {
      await lumen.delete(`/admin/asset-updates/${id}`);
      notify('Оновлення видалено');
      await load();
    } catch (e) { fail(e, 'Не вдалось видалити'); }
  };

  return (
    <div className="space-y-5" data-testid="updates-admin-tab">
      <section className="rounded-2xl border border-border bg-card p-5 space-y-3">
        <h2 className="font-semibold">{editId ? 'Редагування оновлення' : 'Нове оновлення'}</h2>
        <div className="grid sm:grid-cols-3 gap-2">
          <Input className="sm:col-span-2" value={form.title} onChange={(v) => setForm({ ...form, title: v })} placeholder="Заголовок (напр. Завершено фундамент)" testid="update-title-input" />
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="update-kind-select">
            <option value="milestone">Віха проєкту</option>
            <option value="news">Новина</option>
            <option value="general">Оновлення</option>
          </select>
        </div>
        <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={4}
          placeholder="Текст оновлення…" className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="update-body-input" />
        <div className="flex items-center gap-5 text-sm">
          <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={form.pinned} onChange={(e) => setForm({ ...form, pinned: e.target.checked })} className="w-4 h-4 accent-[#2E5D4F]" /> Закріпити</label>
          <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={form.published} onChange={(e) => setForm({ ...form, published: e.target.checked })} className="w-4 h-4 accent-[#2E5D4F]" /> Опубліковано</label>
        </div>
        <div className="flex gap-2">
          <SaveBtn onClick={save} saving={saving} label={editId ? 'Зберегти зміни' : 'Опублікувати'} testid="update-save" />
          {editId && <button onClick={() => { setEditId(null); setForm(EMPTY_UPDATE); }} className="text-sm text-muted-foreground hover:text-foreground">Скасувати</button>}
        </div>
      </section>

      <ul className="space-y-3" data-testid="updates-admin-list">
        {items.map((u) => (
          <li key={u.id} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 flex-wrap">
              {u.pinned && <Pin className="w-3.5 h-3.5 text-[#C99B3D]" />}
              <p className="font-medium text-sm">{u.title}</p>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{u.kind_label}</span>
              {!u.published && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">чернетка</span>}
              <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(u.published_at)}</span>
              <button onClick={() => { setEditId(u.id); setForm({ title: u.title, body: u.body, kind: u.kind, pinned: u.pinned, published: u.published }); }}
                className="text-xs text-[#2E5D4F] hover:underline" data-testid={`update-edit-${u.id}`}>Редагувати</button>
              <button onClick={() => remove(u.id)} className="text-xs text-red-500 hover:underline" data-testid={`update-delete-${u.id}`}>Видалити</button>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed line-clamp-2">{u.body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ──────────────────────────── Reports ──────────────────────────── */

function ReportsTab({ assetId, notify, fail }) {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: '', report_type: 'quarterly', period_label: '', summary: '' });
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() =>
    lumen.get(`/admin/assets/${assetId}/reports`).then((r) => setItems(r.data?.items || [])).catch(() => {}), [assetId]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', form.title);
      fd.append('report_type', form.report_type);
      fd.append('period_label', form.period_label);
      fd.append('summary', form.summary);
      if (file) fd.append('file', file);
      await lumen.post(`/admin/assets/${assetId}/reports`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      notify('Звіт опубліковано');
      setForm({ title: '', report_type: 'quarterly', period_label: '', summary: '' });
      setFile(null);
      await load();
    } catch (e) { fail(e, 'Не вдалось створити звіт'); }
    finally { setSaving(false); }
  };

  const togglePublish = async (r) => {
    try {
      await lumen.patch(`/admin/asset-reports/${r.id}`, { published: !r.published });
      await load();
    } catch (e) { fail(e, 'Не вдалось змінити публікацію'); }
  };

  const remove = async (id) => {
    try {
      await lumen.delete(`/admin/asset-reports/${id}`);
      notify('Звіт видалено');
      await load();
    } catch (e) { fail(e, 'Не вдалось видалити'); }
  };

  return (
    <div className="space-y-5" data-testid="reports-admin-tab">
      <section className="rounded-2xl border border-border bg-card p-5 space-y-3">
        <h2 className="font-semibold">Новий звіт</h2>
        <div className="grid sm:grid-cols-3 gap-2">
          <Input value={form.title} onChange={(v) => setForm({ ...form, title: v })} placeholder="Назва (напр. Квартальний звіт Q2)" testid="report-title-input" />
          <select value={form.report_type} onChange={(e) => setForm({ ...form, report_type: e.target.value })}
            className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="report-type-select">
            <option value="monthly">Місячний</option>
            <option value="quarterly">Квартальний</option>
            <option value="annual">Річний</option>
          </select>
          <Input value={form.period_label} onChange={(v) => setForm({ ...form, period_label: v })} placeholder="Період (напр. Q2 2026)" />
        </div>
        <textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} rows={3}
          placeholder="Короткий підсумок періоду…" className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="report-summary-input" />
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <Upload className="w-4 h-4 text-[#2E5D4F]" />
          <span className="text-[#2E5D4F] hover:underline">{file ? file.name : 'Прикріпити PDF (необов\'язково)'}</span>
          <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="report-file-input" />
        </label>
        <SaveBtn onClick={save} saving={saving} label="Опублікувати звіт" testid="report-save" />
      </section>

      <ul className="space-y-3" data-testid="reports-admin-list">
        {items.map((r) => (
          <li key={r.id} className="rounded-2xl border border-border bg-card p-4 flex items-center gap-3 flex-wrap">
            <FileText className="w-4 h-4 text-[#2E5D4F]" />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm">{r.title} <span className="text-xs text-muted-foreground">· {r.report_type_label}{r.period_label ? ` · ${r.period_label}` : ''}</span></p>
              {!r.published && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">не опубліковано</span>}
            </div>
            <button onClick={() => togglePublish(r)} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1" data-testid={`report-toggle-${r.id}`}>
              {r.published ? <><EyeOff className="w-3.5 h-3.5" /> Сховати</> : <><Eye className="w-3.5 h-3.5" /> Опублікувати</>}
            </button>
            <button onClick={() => remove(r.id)} className="text-xs text-red-500 hover:underline" data-testid={`report-delete-${r.id}`}>Видалити</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ──────────────────────────── Documents ──────────────────────────── */

const DOC_TYPES = [
  { value: 'valuation', label: 'Звіт про оцінку' },
  { value: 'audit', label: 'Аудит' },
  { value: 'lease_agreement', label: 'Договір оренди' },
  { value: 'financial_model', label: 'Фінансова модель' },
  { value: 'permit', label: 'Дозвільна документація' },
  { value: 'legal', label: 'Юридичні документи' },
  { value: 'other', label: 'Інше' },
];

function DocsTab({ assetId, notify, fail }) {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: '', doc_type: 'valuation', visibility: 'public' });
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() =>
    lumen.get(`/admin/assets/${assetId}/documents`).then((r) => setItems(r.data?.items || [])).catch(() => {}), [assetId]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!file) { fail(null, 'Оберіть файл для завантаження'); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', form.title);
      fd.append('doc_type', form.doc_type);
      fd.append('visibility', form.visibility);
      fd.append('file', file);
      await lumen.post(`/admin/assets/${assetId}/documents`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      notify('Документ завантажено');
      setForm({ title: '', doc_type: 'valuation', visibility: 'public' });
      setFile(null);
      await load();
    } catch (e) { fail(e, 'Не вдалось завантажити документ'); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try {
      await lumen.delete(`/admin/asset-documents/${id}`);
      notify('Документ видалено');
      await load();
    } catch (e) { fail(e, 'Не вдалось видалити'); }
  };

  return (
    <div className="space-y-5" data-testid="docs-admin-tab">
      <section className="rounded-2xl border border-border bg-card p-5 space-y-3">
        <h2 className="font-semibold">Завантажити документ</h2>
        <div className="grid sm:grid-cols-3 gap-2">
          <Input value={form.title} onChange={(v) => setForm({ ...form, title: v })} placeholder="Назва документа" testid="doc-title-input" />
          <select value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}
            className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="doc-type-select">
            {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
          <select value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}
            className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="doc-visibility-select">
            <option value="public">Публічний</option>
            <option value="investors">Лише для інвесторів</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <Upload className="w-4 h-4 text-[#2E5D4F]" />
          <span className="text-[#2E5D4F] hover:underline">{file ? file.name : 'Обрати файл (PDF, DOC, XLS, зображення)'}</span>
          <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="doc-file-input" />
        </label>
        <SaveBtn onClick={save} saving={saving} label="Завантажити" testid="doc-save" />
      </section>

      <ul className="space-y-2.5" data-testid="docs-admin-list">
        {items.map((d) => (
          <li key={d.id} className="rounded-2xl border border-border bg-card p-4 flex items-center gap-3 flex-wrap">
            <FileText className="w-4 h-4 text-[#2E5D4F]" />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm">{d.title}</p>
              <p className="text-xs text-muted-foreground">{d.doc_type_label} · {d.visibility === 'investors' ? 'лише для інвесторів' : 'публічний'}</p>
            </div>
            {d.download_url && (
              <a href={`${process.env.REACT_APP_BACKEND_URL}${d.download_url}`} target="_blank" rel="noreferrer" className="text-xs text-[#2E5D4F] hover:underline">Відкрити</a>
            )}
            <button onClick={() => remove(d.id)} className="text-xs text-red-500 hover:underline" data-testid={`doc-delete-${d.id}`}>Видалити</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ──────────────────────────── Q&A (per asset) ──────────────────────────── */

function QaTab({ assetId, notify, fail }) {
  const [items, setItems] = useState([]);
  const [answers, setAnswers] = useState({});
  const [actingId, setActingId] = useState('');

  const load = useCallback(() =>
    lumen.get(`/admin/questions?asset_id=${assetId}`).then((r) => setItems(r.data?.items || [])).catch(() => {}), [assetId]);
  useEffect(() => { load(); }, [load]);

  const answer = async (id) => {
    setActingId(id);
    try {
      await lumen.post(`/admin/questions/${id}/answer`, { answer: answers[id] || '' });
      notify('Відповідь опубліковано');
      setAnswers((p) => ({ ...p, [id]: '' }));
      await load();
    } catch (e) { fail(e, 'Не вдалось відповісти'); }
    finally { setActingId(''); }
  };

  const hide = async (id, hidden) => {
    try {
      await lumen.post(`/admin/questions/${id}/${hidden ? 'restore' : 'hide'}`);
      await load();
    } catch (e) { fail(e, 'Не вдалось змінити видимість'); }
  };

  return (
    <div className="space-y-4" data-testid="qa-admin-tab">
      {items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">Питань по цьому активу ще немає.</div>
      )}
      {items.map((q) => (
        <div key={q.id} className="rounded-2xl border border-border bg-card p-4" data-testid={`qa-admin-item-${q.id}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-medium text-sm">{q.investor_name}</p>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${q.status === 'pending' ? 'bg-amber-100 text-amber-800' : q.status === 'answered' ? 'bg-emerald-100 text-emerald-800' : 'bg-muted text-muted-foreground'}`}>
              {q.status === 'pending' ? 'очікує' : q.status === 'answered' ? 'відповідь дано' : 'приховано'}
            </span>
            <span className="text-xs text-muted-foreground ml-auto">{formatDateUk(q.created_at)}</span>
            <button onClick={() => hide(q.id, q.status === 'hidden')} className="text-xs text-muted-foreground hover:text-foreground">
              {q.status === 'hidden' ? 'Відновити' : 'Приховати'}
            </button>
          </div>
          <p className="mt-2 text-sm">{q.question}</p>
          {q.answer && <p className="mt-2 text-sm text-muted-foreground border-l-2 border-[#2E5D4F]/40 pl-3">{q.answer}</p>}
          {q.status === 'pending' && (
            <div className="mt-3 flex gap-2">
              <Input value={answers[q.id] || ''} onChange={(v) => setAnswers((p) => ({ ...p, [q.id]: v }))} placeholder="Ваша публічна відповідь…" testid={`qa-answer-input-${q.id}`} />
              <button onClick={() => answer(q.id)} disabled={actingId === q.id || !(answers[q.id] || '').trim()}
                className="shrink-0 px-4 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-40" data-testid={`qa-answer-send-${q.id}`}>
                {actingId === q.id ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Відповісти'}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ──────────────────────────── SPV ──────────────────────────── */

function SpvTab({ assetId, notify, fail }) {
  const [spv, setSpv] = useState(null);
  const [form, setForm] = useState({ name: '', registration_number: '', jurisdiction: 'UA', status: 'forming', notes: '' });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    lumen.get(`/assets/${assetId}/spv`).then((r) => {
      const s = r.data?.spv;
      setSpv(s || null);
      if (s) setForm({ name: s.name || '', registration_number: s.registration_number || '', jurisdiction: s.jurisdiction || 'UA', status: s.status || 'forming', notes: s.notes || '' });
    }).catch(() => {}).finally(() => setLoaded(true));
  }, [assetId]);

  const save = async () => {
    setSaving(true);
    try {
      let r;
      if (spv) {
        r = await lumen.patch(`/admin/spvs/${spv.id}`, form);
      } else {
        r = await lumen.post('/admin/spvs', { ...form, asset_id: assetId });
      }
      setSpv(r.data);
      notify('SPV збережено');
    } catch (e) { fail(e, 'Не вдалось зберегти SPV'); }
    finally { setSaving(false); }
  };

  if (!loaded) return <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 space-y-3 max-w-2xl" data-testid="spv-tab">
      <h2 className="font-semibold flex items-center gap-2"><Landmark className="w-4 h-4 text-[#2E5D4F]" /> {spv ? 'Юрособа активу' : 'Створити SPV для активу'}</h2>
      <p className="text-xs text-muted-foreground">Asset → SPV → Investors. Кошти інвесторів зберігаються на окремому рахунку SPV.</p>
      <div className="grid sm:grid-cols-2 gap-2">
        <Input value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="Назва (ТОВ «…»)" testid="spv-name-input" />
        <Input value={form.registration_number} onChange={(v) => setForm({ ...form, registration_number: v })} placeholder="ЄДРПОУ" testid="spv-edrpou-input" />
        <Input value={form.jurisdiction} onChange={(v) => setForm({ ...form, jurisdiction: v })} placeholder="Юрисдикція (UA)" />
        <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
          className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" data-testid="spv-status-select">
          <option value="forming">Реєструється</option>
          <option value="active">Активна</option>
          <option value="dissolved">Ліквідована</option>
        </select>
      </div>
      <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3}
        placeholder="Нотатки (рахунок, банк, особливості структури)…"
        className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" />
      <SaveBtn onClick={save} saving={saving} label={spv ? 'Зберегти SPV' : 'Створити SPV'} testid="spv-save" />
    </div>
  );
}


/* ──────────────────────────── Marketplace 2.0 (Phase B) ──────────────────────────── */

const Area = ({ value, onChange, placeholder, rows = 3, testid }) => (
  <textarea value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} rows={rows} data-testid={testid}
    className="w-full px-4 py-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] text-sm" />
);

const NumIn = ({ value, onChange, placeholder, testid, step = '1' }) => (
  <input type="number" step={step} value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid}
    className="h-10 px-3 rounded-xl border border-border bg-background focus:outline-none focus:border-[#2E5D4F] transition text-sm w-full" />
);

const THESIS_FIELDS = [
  { key: 'opportunity', label: 'Можливість — чому існує ця можливість?' },
  { key: 'market', label: 'Ринок — чому ринок це недооцінює?' },
  { key: 'execution', label: 'Виконання — як ми це реалізуємо?' },
  { key: 'exit', label: 'Вихід — як інвестор поверне капітал?' },
];
const STACK_FIELDS = [
  { key: 'asset_value', label: 'Вартість об\u0027єкта (USD)' },
  { key: 'debt', label: 'Банківський кредит (USD)' },
  { key: 'platform', label: 'Кошти платформи (USD)' },
  { key: 'investors', label: 'Кошти інвесторів (USD)' },
  { key: 'reserve', label: 'Резервний фонд (USD)' },
];
const MILESTONE_KINDS = [
  { v: 'acquisition', l: 'Придбання' }, { v: 'operations', l: 'Експлуатація' },
  { v: 'milestone', l: 'Віха' }, { v: 'valuation', l: 'Переоцінка' },
  { v: 'funding', l: 'Збір' }, { v: 'payout', l: 'Виплата' },
];

function IntelTab({ assetId, notify, fail }) {
  const [thesis, setThesis] = useState({});
  const [stack, setStack] = useState({});
  const [occupancy, setOccupancy] = useState('');
  const [factors, setFactors] = useState({});
  const [defaults, setDefaults] = useState({});
  const [milestones, setMilestones] = useState([]);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ date: '', title: '', body: '', kind: 'milestone' });
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    Promise.all([
      lumen.get(`/admin/assets/${assetId}/intelligence`).catch(() => null),
      lumen.get(`/admin/assets/${assetId}/journal`).catch(() => null),
    ]).then(([i, j]) => {
      if (i?.data) {
        setThesis(i.data.thesis || {});
        setStack(i.data.capital_stack || {});
        setOccupancy(i.data.occupancy_percent ?? '');
        setFactors(i.data.scenario_factors || {});
        setDefaults(i.data.scenario_defaults || {});
      }
      setMilestones(j?.data?.items || []);
    }).finally(() => setLoading(false));
  }, [assetId]);

  useEffect(() => { reload(); }, [reload]);

  const save = async () => {
    setSaving(true);
    try {
      await lumen.patch(`/admin/assets/${assetId}/intelligence`, {
        thesis,
        capital_stack: Object.fromEntries(STACK_FIELDS.map((f) => [f.key, Number(stack[f.key]) || 0])),
        occupancy_percent: occupancy === '' ? null : Number(occupancy),
        scenario_factors: factors,
      });
      notify('Marketplace 2.0 збережено');
      reload();
    } catch (e) { fail(e, 'Не вдалось зберегти'); }
    finally { setSaving(false); }
  };

  const addMilestone = async () => {
    if (!form.date || !form.title) { fail(null, 'Вкажіть дату і заголовок'); return; }
    try {
      await lumen.post(`/admin/assets/${assetId}/journal`, form);
      setForm({ date: '', title: '', body: '', kind: 'milestone' });
      notify('Віху додано');
      reload();
    } catch (e) { fail(e, 'Не вдалось додати віху'); }
  };

  const delMilestone = async (id) => {
    try { await lumen.delete(`/admin/asset-journal/${id}`); notify('Віху видалено'); reload(); }
    catch (e) { fail(e, 'Не вдалось видалити'); }
  };

  const setFactor = (key, field, val) =>
    setFactors((p) => ({ ...p, [key]: { ...(p[key] || {}), [field]: val === '' ? undefined : Number(val) } }));

  if (loading) return <div className="h-40 rounded-2xl bg-muted/40 animate-pulse" />;

  return (
    <div className="space-y-8" data-testid="intel-tab">
      {/* B1 Thesis */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1">Investment Thesis (B1)</h3>
        <p className="text-xs text-token-muted mb-4">Ядро карточки — навіщо інвестувати саме сюди.</p>
        <div className="grid sm:grid-cols-2 gap-4">
          {THESIS_FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="text-xs font-medium text-token-muted">{f.label}</span>
              <div className="mt-1"><Area value={thesis[f.key]} onChange={(v) => setThesis((p) => ({ ...p, [f.key]: v }))} rows={4} testid={`thesis-${f.key}`} /></div>
            </label>
          ))}
        </div>
      </section>

      {/* B3 Capital Stack */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1">Capital Stack (B3)</h3>
        <p className="text-xs text-token-muted mb-4">Структура капіталу угоди — відображається водоспадом.</p>
        <div className="grid sm:grid-cols-3 gap-4">
          {STACK_FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="text-xs font-medium text-token-muted">{f.label}</span>
              <div className="mt-1"><NumIn value={stack[f.key] ? Math.round(usdFromUah(Number(stack[f.key]) || 0)) : ''} onChange={(v) => setStack((p) => ({ ...p, [f.key]: Math.round(Number(v) * UAH_PER_USD) }))} testid={`stack-${f.key}`} /></div>
            </label>
          ))}
        </div>
      </section>

      {/* B6 occupancy + B2 factors */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1">Здоров'я та сценарії (B2 / B6)</h3>
        <p className="text-xs text-token-muted mb-4">Заповнюваність живить Conviction Score. Множники — діапазон Scenario Engine (Base зазвичай 1.0).</p>
        <label className="block max-w-xs mb-5">
          <span className="text-xs font-medium text-token-muted">Заповнюваність, % (occupancy)</span>
          <div className="mt-1"><NumIn value={occupancy} onChange={setOccupancy} placeholder="0–100" testid="intel-occupancy" /></div>
        </label>
        <div className="grid sm:grid-cols-3 gap-4">
          {['bear', 'base', 'bull'].map((key) => (
            <div key={key} className="rounded-xl border border-border p-3">
              <p className="text-sm font-medium capitalize mb-2">{key}</p>
              <label className="block mb-2">
                <span className="text-[11px] text-token-muted">Множник дохідності (деф. {defaults[key]?.yield_factor ?? '—'})</span>
                <NumIn step="0.01" value={factors[key]?.yield_factor} onChange={(v) => setFactor(key, 'yield_factor', v)} testid={`factor-${key}-yield`} />
              </label>
              <label className="block">
                <span className="text-[11px] text-token-muted">Множник виходу (деф. {defaults[key]?.exit_factor ?? '—'})</span>
                <NumIn step="0.01" value={factors[key]?.exit_factor} onChange={(v) => setFactor(key, 'exit_factor', v)} testid={`factor-${key}-exit`} />
              </label>
            </div>
          ))}
        </div>
        <div className="mt-5"><SaveBtn onClick={save} saving={saving} label="Зберегти Marketplace 2.0" testid="intel-save" /></div>
      </section>

      {/* B4 Journal milestones */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1">Asset Journal — авторські віхи (B4)</h3>
        <p className="text-xs text-token-muted mb-4">Об'єднуються з реальними подіями системи (виплати, звіти, угоди) у живій стрічці.</p>
        <div className="grid sm:grid-cols-[140px_1fr_160px] gap-3 mb-3">
          <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="milestone-date"
            className="h-10 px-3 rounded-xl border border-border bg-background text-sm" />
          <Input value={form.title} onChange={(v) => setForm({ ...form, title: v })} placeholder="Заголовок віхи" testid="milestone-title" />
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} data-testid="milestone-kind"
            className="h-10 px-3 rounded-xl border border-border bg-background text-sm">
            {MILESTONE_KINDS.map((k) => <option key={k.v} value={k.v}>{k.l}</option>)}
          </select>
        </div>
        <Area value={form.body} onChange={(v) => setForm({ ...form, body: v })} placeholder="Опис (необов'язково)" testid="milestone-body" />
        <button onClick={addMilestone} data-testid="milestone-add"
          className="mt-3 inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 transition">
          <Plus className="w-4 h-4" /> Додати віху
        </button>

        <div className="mt-5 space-y-2" data-testid="milestone-list">
          {milestones.length === 0 ? (
            <p className="text-sm text-token-muted">Авторських віх ще немає.</p>
          ) : milestones.map((m) => (
            <div key={m.id} className="flex items-start gap-3 p-3 rounded-xl border border-border bg-background/40" data-testid={`milestone-${m.id}`}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-token-muted">{formatDateUk(m.date)}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#2E5D4F]/10 text-[#2E5D4F]">{m.kind}</span>
                </div>
                <p className="font-medium text-sm mt-1">{m.title}</p>
                {m.body && <p className="text-xs text-token-muted mt-0.5">{m.body}</p>}
              </div>
              <button onClick={() => delMilestone(m.id)} data-testid={`milestone-del-${m.id}`}
                className="shrink-0 p-2 rounded-lg border border-red-200 text-red-600 hover:bg-red-50">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ──────────────────────────── Community OS (Phase C) ──────────────────────────── */

function CommunityTab({ assetId, notify, fail }) {
  const [ann, setAnn] = useState({ title: '', body: '' });
  const [poll, setPoll] = useState({ question: '', options: ['', ''], closes_in_days: 14 });
  const [feed, setFeed] = useState([]);
  const [polls, setPolls] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    Promise.all([
      lumen.get(`/assets/${assetId}/community/feed`).catch(() => null),
      lumen.get(`/assets/${assetId}/community/polls`).catch(() => null),
    ]).then(([f, p]) => {
      setFeed(f?.data?.items || []);
      setPolls(p?.data?.items || []);
    }).finally(() => setLoading(false));
  }, [assetId]);
  useEffect(() => { reload(); }, [reload]);

  const publishAnn = async () => {
    if (!ann.title.trim()) { fail(null, 'Вкажіть заголовок'); return; }
    setBusy(true);
    try {
      const r = await lumen.post(`/admin/assets/${assetId}/community/announcements`, ann);
      notify(`Оголошення опубліковано · сповіщено ${r.data.notified} власників`);
      setAnn({ title: '', body: '' }); reload();
    } catch (e) { fail(e, 'Не вдалось опублікувати'); } finally { setBusy(false); }
  };

  const createPoll = async () => {
    const opts = poll.options.map((o) => o.trim()).filter(Boolean);
    if (!poll.question.trim() || opts.length < 2) { fail(null, 'Питання і ≥2 варіанти'); return; }
    setBusy(true);
    try {
      await lumen.post(`/admin/assets/${assetId}/community/polls`, { question: poll.question, options: opts, closes_in_days: Number(poll.closes_in_days) || null });
      notify('Голосування створено');
      setPoll({ question: '', options: ['', ''], closes_in_days: 14 }); reload();
    } catch (e) { fail(e, 'Не вдалось створити'); } finally { setBusy(false); }
  };

  const answerPost = async (id) => {
    const answer = window.prompt('Відповідь оператора:');
    if (!answer) return;
    try { await lumen.post(`/admin/community/posts/${id}/answer`, { answer }); notify('Відповідь опубліковано'); reload(); }
    catch (e) { fail(e, 'Помилка'); }
  };
  const hidePost = async (id) => {
    if (!window.confirm('Приховати цей запис?')) return;
    try { await lumen.delete(`/admin/community/posts/${id}`); notify('Запис приховано'); reload(); }
    catch (e) { fail(e, 'Помилка'); }
  };
  const pinPost = async (id) => {
    try { await lumen.post(`/admin/community/posts/${id}/pin`); reload(); } catch (e) { fail(e, 'Помилка'); }
  };
  const closePoll = async (id) => {
    try { await lumen.post(`/admin/community/polls/${id}/close`); notify('Голосування закрито'); reload(); }
    catch (e) { fail(e, 'Помилка'); }
  };

  if (loading) return <div className="h-40 rounded-2xl bg-muted/40 animate-pulse" />;

  return (
    <div className="space-y-8" data-testid="community-admin-tab">
      {/* C7 Announcement */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1 flex items-center gap-2"><Megaphone className="w-4 h-4 text-[#2E5D4F]" />Оголошення (C7)</h3>
        <p className="text-xs text-token-muted mb-4">Публікація сповіщає всіх власників часток об'єкта.</p>
        <Input value={ann.title} onChange={(v) => setAnn({ ...ann, title: v })} placeholder="Заголовок (напр. «Новий орендар підписаний»)" testid="ann-title" />
        <div className="mt-2"><Area value={ann.body} onChange={(v) => setAnn({ ...ann, body: v })} placeholder="Деталі оголошення" rows={3} testid="ann-body" /></div>
        <button onClick={publishAnn} disabled={busy} data-testid="ann-publish"
          className="mt-3 inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 disabled:opacity-60">
          <Megaphone className="w-4 h-4" /> Опублікувати та сповістити
        </button>
      </section>

      {/* C4 Poll */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-1 flex items-center gap-2"><Vote className="w-4 h-4 text-[#2E5D4F]" />Голосування (C4)</h3>
        <p className="text-xs text-token-muted mb-4">Вага голосу = units власника. Рекомендаційне.</p>
        <Input value={poll.question} onChange={(v) => setPoll({ ...poll, question: v })} placeholder="Питання голосування" testid="poll-question" />
        <div className="mt-3 space-y-2">
          {poll.options.map((o, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input value={o} onChange={(v) => { const opts = [...poll.options]; opts[i] = v; setPoll({ ...poll, options: opts }); }} placeholder={`Варіант ${i + 1}`} testid={`poll-opt-${i}`} />
              {poll.options.length > 2 && (
                <button onClick={() => setPoll({ ...poll, options: poll.options.filter((_, j) => j !== i) })} className="p-2 rounded-lg border border-red-200 text-red-600"><Trash2 className="w-4 h-4" /></button>
              )}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-3">
          {poll.options.length < 6 && (
            <button onClick={() => setPoll({ ...poll, options: [...poll.options, ''] })} data-testid="poll-add-opt"
              className="inline-flex items-center gap-1 text-sm text-[#2E5D4F]"><Plus className="w-4 h-4" />Варіант</button>
          )}
          <label className="text-xs text-token-muted ml-auto">Закрити через
            <input type="number" value={poll.closes_in_days} onChange={(e) => setPoll({ ...poll, closes_in_days: e.target.value })}
              className="w-16 mx-2 h-8 px-2 rounded-lg border border-border bg-background text-sm" /> днів</label>
        </div>
        <button onClick={createPoll} disabled={busy} data-testid="poll-create"
          className="mt-3 inline-flex items-center gap-2 px-5 h-10 rounded-full bg-[#2E5D4F] text-white text-sm font-medium hover:opacity-90 disabled:opacity-60">
          <Plus className="w-4 h-4" /> Створити голосування
        </button>

        {polls.length > 0 && (
          <div className="mt-5 space-y-2">
            {polls.map((p) => (
              <div key={p.id} className="flex items-center gap-3 p-3 rounded-xl border border-border" data-testid={`admin-poll-${p.id}`}>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm">{p.question}</p>
                  <p className="text-xs text-token-muted">{p.total_voters} голосів · {Number(p.total_units).toLocaleString('uk-UA')} units · {p.status === 'open' ? 'відкрите' : 'закрите'}</p>
                </div>
                {p.status === 'open' && <button onClick={() => closePoll(p.id)} className="text-xs px-3 h-8 rounded-full border border-border">Закрити</button>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Moderation */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <h3 className="font-semibold mb-3">Модерація стрічки</h3>
        {feed.length === 0 ? <p className="text-sm text-token-muted">Записів ще немає.</p> : (
          <div className="space-y-2">
            {feed.map((p) => (
              <div key={p.id} className="flex items-start gap-3 p-3 rounded-xl border border-border" data-testid={`admin-post-${p.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-muted">{p.kind}</span>
                    {p.visibility === 'holders' && <span className="text-[10px] text-token-muted">lounge</span>}
                    {p.pinned && <Pin className="w-3 h-3 text-[#C99B3D]" />}
                    <span className="text-xs text-token-muted">{p.author_name}</span>
                  </div>
                  <p className="font-medium text-sm mt-1">{p.title || p.body?.slice(0, 60)}</p>
                  {p.answer && <p className="text-xs text-[#2E5D4F] mt-1">✓ відповідь надано</p>}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {p.kind === 'question' && !p.answer && (
                    <button onClick={() => answerPost(p.id)} data-testid={`answer-${p.id}`} className="text-xs px-3 h-8 rounded-full bg-[#2E5D4F] text-white">Відповісти</button>
                  )}
                  <button onClick={() => pinPost(p.id)} className="p-2 rounded-lg border border-border" title="Закріпити"><Pin className="w-4 h-4" /></button>
                  <button onClick={() => hidePost(p.id)} className="p-2 rounded-lg border border-red-200 text-red-600" title="Приховати"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

