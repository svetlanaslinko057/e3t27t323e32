/**
 * AdminManagerInstructions — F4 authoring console.
 * Admins create/edit rich-text (markdown) team instructions, publish, view
 * version history and acknowledgement coverage (who read the current version).
 */
import { useEffect, useState, useCallback } from 'react';
import { lumen, lumenError, formatDateUk } from '@/lib/lumenApi';
import { useLang } from '@/contexts/LanguageContext';
import MarkdownLite from '@/components/MarkdownLite';
import {
  BookOpen, Loader2, RefreshCw, Plus, Pencil, Eye, History, Users,
  CheckCircle2, Pin, Archive, Send, X, FileText,
} from 'lucide-react';

const CATEGORY_LABEL = {
  onboarding: { uk: 'Як вести інвестора', en: 'Leading an investor' },
  kyc: { uk: 'KYC та верифікація', en: 'KYC & verification' },
  objections: { uk: 'Робота з запереченнями', en: 'Handling objections' },
  documents: { uk: 'Оформлення документів', en: 'Document preparation' },
  handoff: { uk: 'Передача лідів', en: 'Lead handoff' },
  general: { uk: 'Загальне', en: 'General' },
};
const CATS = Object.keys(CATEGORY_LABEL);

const STATUS_BADGE = {
  published: 'bg-emerald-500/10 text-emerald-700',
  draft: 'bg-amber-500/10 text-amber-700',
  archived: 'bg-slate-500/10 text-slate-500',
};

export default function AdminManagerInstructions() {
  const { bi, lang } = useLang();
  const [list, setList] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [statusF, setStatusF] = useState('');
  const [catF, setCatF] = useState('');
  const [editor, setEditor] = useState(null);   // doc being edited (or {} for new)
  const [viewer, setViewer] = useState(null);    // {acks, versions} side panel

  const cat = (k) => (CATEGORY_LABEL[k] ? (lang === 'en' ? CATEGORY_LABEL[k].en : CATEGORY_LABEL[k].uk) : k);

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const qs = `?${statusF ? `status=${statusF}&` : ''}${catF ? `category=${catF}` : ''}`;
      const [l, o] = await Promise.all([
        lumen.get(`/manager/instructions${qs}`),
        lumen.get('/admin/manager/instructions-overview'),
      ]);
      setList(l.data?.instructions || []);
      setOverview(o.data);
    } catch (e) { setErr(lumenError(e)); }
    finally { setLoading(false); }
  }, [statusF, catF]);
  useEffect(() => { load(); }, [load]);

  const save = async (form) => {
    try {
      if (form.instruction_id) await lumen.put(`/admin/manager/instructions/${form.instruction_id}`, form);
      else await lumen.post('/admin/manager/instructions', form);
      setEditor(null); await load();
    } catch (e) { alert(lumenError(e)); }
  };
  const publish = async (d) => { try { await lumen.post(`/admin/manager/instructions/${d.instruction_id}/publish`); await load(); } catch (e) { alert(lumenError(e)); } };
  const archive = async (d) => { if (!window.confirm(bi('Архівувати інструкцію?', 'Archive instruction?'))) return; try { await lumen.post(`/admin/manager/instructions/${d.instruction_id}/archive`); await load(); } catch (e) { alert(lumenError(e)); } };

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-manager-instructions">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-token-muted flex items-center gap-2"><BookOpen className="w-3.5 h-3.5" /> F4 · {bi('Інструкції менеджера', 'Manager Instructions')}</div>
          <h1 className="mt-2 text-2xl font-bold">{bi('Операційні інструкції команди', 'Team operational instructions')}</h1>
          <p className="mt-1 text-token-muted text-sm max-w-2xl">{bi('Єдине місце: як вести інвестора, робити KYC, працювати з запереченнями, оформляти документи та передавати ліди.', 'One place: leading investors, KYC, objections, documents, lead handoff.')}</p>
        </div>
        <button onClick={() => setEditor({ category: 'general', status: 'draft', body: '', title: '', tags: [], pinned: false })} data-testid="mi-new"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43] transition"><Plus className="w-4 h-4" /> {bi('Нова інструкція', 'New instruction')}</button>
      </div>

      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label={bi('Усього', 'Total')} value={overview.total} />
          <Stat label={bi('Опубліковано', 'Published')} value={overview.published} accent="text-emerald-600" />
          <Stat label={bi('Чернетки', 'Drafts')} value={overview.drafts} accent="text-amber-600" />
          <Stat label={bi('Покриття підтверджень', 'Ack coverage')} value={`${Math.round((overview.avg_ack_coverage || 0) * 100)}%`} accent="text-[#2E5D4F]" />
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <select value={statusF} onChange={(e) => setStatusF(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-1.5 text-sm" data-testid="mi-status-filter">
          <option value="">{bi('Усі статуси', 'All statuses')}</option>
          <option value="published">{bi('Опубліковані', 'Published')}</option>
          <option value="draft">{bi('Чернетки', 'Drafts')}</option>
          <option value="archived">{bi('Архів', 'Archived')}</option>
        </select>
        <select value={catF} onChange={(e) => setCatF(e.target.value)} className="bg-card border border-border rounded-lg px-3 py-1.5 text-sm" data-testid="mi-cat-filter">
          <option value="">{bi('Усі категорії', 'All categories')}</option>
          {CATS.map((c) => <option key={c} value={c}>{cat(c)}</option>)}
        </select>
        <button onClick={load} className="h-9 px-3 rounded-lg text-sm border border-border hover:bg-muted inline-flex items-center gap-1.5">{loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} {bi('Оновити', 'Refresh')}</button>
      </div>

      {err && <p className="text-sm text-rose-600">{err}</p>}

      <div className="space-y-2">
        {loading && !list.length ? <Loading /> : list.length === 0 ? <Empty bi={bi} /> : list.map((d) => (
          <div key={d.instruction_id} className="rounded-xl border border-border bg-card p-4 flex items-center gap-3" data-testid="mi-row">
            {d.pinned && <Pin className="w-4 h-4 text-[#2E5D4F] shrink-0" />}
            <FileText className="w-4 h-4 text-token-muted shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-token-primary truncate">{d.title}</div>
              <div className="text-[11px] text-token-muted flex items-center gap-2 flex-wrap">
                <span className="px-1.5 py-0.5 rounded bg-muted">{cat(d.category)}</span>
                <span>v{d.version}</span>
                <span>· {d.updated_at ? formatDateUk(d.updated_at) : ''}</span>
                {typeof d.ack_count === 'number' && <span className="inline-flex items-center gap-1"><Users className="w-3 h-3" /> {d.ack_count}</span>}
              </div>
            </div>
            <span className={`text-[11px] px-2 py-0.5 rounded-full ${STATUS_BADGE[d.status]}`}>{d.status}</span>
            <div className="flex items-center gap-1 shrink-0">
              <IconBtn onClick={() => setViewer({ doc: d })} title={bi('Підтвердження / версії', 'Acks / versions')} testid={`mi-view-${d.instruction_id}`}><Eye className="w-4 h-4" /></IconBtn>
              <IconBtn onClick={() => setEditor(d)} title={bi('Редагувати', 'Edit')} testid={`mi-edit-${d.instruction_id}`}><Pencil className="w-4 h-4" /></IconBtn>
              <IconBtn onClick={() => publish(d)} title={d.status === 'published' ? bi('Зняти з публікації', 'Unpublish') : bi('Опублікувати', 'Publish')} testid={`mi-publish-${d.instruction_id}`}><Send className={`w-4 h-4 ${d.status === 'published' ? 'text-emerald-600' : ''}`} /></IconBtn>
              <IconBtn onClick={() => archive(d)} title={bi('Архівувати', 'Archive')} testid={`mi-archive-${d.instruction_id}`}><Archive className="w-4 h-4" /></IconBtn>
            </div>
          </div>
        ))}
      </div>

      {editor && <EditorModal doc={editor} onClose={() => setEditor(null)} onSave={save} bi={bi} cat={cat} />}
      {viewer && <CoveragePanel doc={viewer.doc} onClose={() => setViewer(null)} bi={bi} />}
    </div>
  );
}

function Stat({ label, value, accent }) {
  return <div className="rounded-xl border border-border bg-card p-4"><div className="text-[11px] uppercase tracking-wider text-token-muted">{label}</div><div className={`mt-1 text-2xl font-bold tabular-nums ${accent || ''}`}>{value}</div></div>;
}
function IconBtn({ children, onClick, title, testid }) {
  return <button onClick={onClick} title={title} data-testid={testid} className="w-8 h-8 grid place-items-center rounded-lg hover:bg-muted text-token-muted hover:text-token-primary transition">{children}</button>;
}

function EditorModal({ doc, onClose, onSave, bi, cat }) {
  const [form, setForm] = useState({
    instruction_id: doc.instruction_id, title: doc.title || '', category: doc.category || 'general',
    body: doc.body || '', tags: (doc.tags || []).join(', '), pinned: !!doc.pinned, status: doc.status || 'draft', change_note: '',
  });
  const [preview, setPreview] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
  const submit = () => onSave({ ...form, tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean) });

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="mi-editor">
      <div className="bg-card rounded-2xl border border-border w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between sticky top-0 bg-card">
          <h3 className="font-semibold">{doc.instruction_id ? bi('Редагувати інструкцію', 'Edit instruction') : bi('Нова інструкція', 'New instruction')}</h3>
          <button onClick={onClose} className="w-8 h-8 grid place-items-center rounded-lg hover:bg-muted"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-3">
          <input value={form.title} onChange={set('title')} placeholder={bi('Заголовок', 'Title')} className="w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="mi-input-title" />
          <div className="grid grid-cols-2 gap-3">
            <select value={form.category} onChange={set('category')} className="bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="mi-input-category">
              {Object.keys(CATEGORY_LABEL).map((c) => <option key={c} value={c}>{cat(c)}</option>)}
            </select>
            <input value={form.tags} onChange={set('tags')} placeholder={bi('Теги (через кому)', 'Tags (comma)')} className="bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-token-muted">Markdown: # {bi('заголовки', 'headings')}, **{bi('жирний', 'bold')}**, - {bi('списки', 'lists')}</span>
            <button onClick={() => setPreview((p) => !p)} className="text-xs px-2 py-1 rounded-lg border border-border hover:bg-muted">{preview ? bi('Редагувати', 'Edit') : bi('Перегляд', 'Preview')}</button>
          </div>
          {preview ? (
            <div className="min-h-[200px] border border-border rounded-lg p-3 bg-app-surface"><MarkdownLite text={form.body} /></div>
          ) : (
            <textarea value={form.body} onChange={set('body')} rows={12} className="w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm font-mono" data-testid="mi-input-body" />
          )}
          {doc.instruction_id && (
            <input value={form.change_note} onChange={set('change_note')} placeholder={bi('Опис зміни (для історії версій)', 'Change note (for version history)')} className="w-full bg-app-surface border border-border rounded-lg px-3 py-2 text-sm" data-testid="mi-input-note" />
          )}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.pinned} onChange={set('pinned')} /> {bi('Закріпити', 'Pin')}</label>
        </div>
        <div className="px-5 py-3 border-t border-border flex items-center justify-end gap-2 sticky bottom-0 bg-card">
          <select value={form.status} onChange={set('status')} className="bg-app-surface border border-border rounded-lg px-3 py-2 text-sm">
            <option value="draft">{bi('Чернетка', 'Draft')}</option>
            <option value="published">{bi('Опублікувати', 'Published')}</option>
          </select>
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted">{bi('Скасувати', 'Cancel')}</button>
          <button onClick={submit} data-testid="mi-save" className="px-4 py-2 rounded-lg bg-[#2E5D4F] text-white text-sm font-semibold hover:bg-[#274f43]">{bi('Зберегти', 'Save')}</button>
        </div>
      </div>
    </div>
  );
}

function CoveragePanel({ doc, onClose, bi }) {
  const [acks, setAcks] = useState(null);
  const [versions, setVersions] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const [a, v] = await Promise.all([
          lumen.get(`/admin/manager/instructions/${doc.instruction_id}/acks`),
          lumen.get(`/admin/manager/instructions/${doc.instruction_id}/versions`),
        ]);
        setAcks(a.data); setVersions(v.data?.versions || []);
      } catch (_) { /* */ }
    })();
  }, [doc.instruction_id]);
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="mi-coverage">
      <div className="bg-card rounded-2xl border border-border w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between sticky top-0 bg-card">
          <h3 className="font-semibold truncate">{doc.title}</h3>
          <button onClick={onClose} className="w-8 h-8 grid place-items-center rounded-lg hover:bg-muted"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-5">
          <div>
            <h4 className="text-sm font-semibold mb-2 flex items-center gap-2"><Users className="w-4 h-4" /> {bi('Підтвердження', 'Acknowledgements')} (v{acks?.version}) — {acks?.ack_count || 0}/{(acks?.ack_count || 0) + (acks?.pending_count || 0)}</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] text-emerald-700 mb-1">{bi('Підтвердили', 'Acknowledged')}</div>
                {(acks?.acknowledged || []).map((a, i) => <div key={i} className="text-sm flex items-center gap-1.5 py-0.5"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />{a.name}</div>)}
                {acks?.acknowledged?.length === 0 && <div className="text-xs text-token-muted">—</div>}
              </div>
              <div>
                <div className="text-[11px] text-amber-700 mb-1">{bi('Очікують', 'Pending')}</div>
                {(acks?.pending || []).map((a, i) => <div key={i} className="text-sm py-0.5 text-token-muted">{a.name}</div>)}
                {acks?.pending?.length === 0 && <div className="text-xs text-token-muted">—</div>}
              </div>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-2 flex items-center gap-2"><History className="w-4 h-4" /> {bi('Історія версій', 'Version history')}</h4>
            <ul className="space-y-1.5">
              {versions.map((v) => (
                <li key={v.version} className="text-sm flex items-center gap-2 py-1 border-b border-border last:border-0">
                  <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-muted">v{v.version}</span>
                  <span className="text-token-secondary flex-1 truncate">{v.change_note || '—'}</span>
                  <span className="text-[11px] text-token-muted">{v.edited_by_name} · {v.at ? formatDateUk(v.at) : ''}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function Loading() { return <div className="py-12 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-token-muted" /></div>; }
function Empty({ bi }) { return <p className="py-10 text-sm text-token-muted text-center">{bi('Інструкцій ще немає.', 'No instructions yet.')}</p>; }
