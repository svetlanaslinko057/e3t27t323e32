/**
 * AdminSOP — Operations SOP center (LR-3a).
 * Internal compliance/operations documents the team follows day-to-day.
 * Left: list of SOPs. Right: full rendered document + inline editor (admin can
 * update copy; reset to seed). Backed by /api/admin/sop[/{key}].
 */
import { useEffect, useState, useCallback } from 'react';
import {
  BookOpenCheck, RefreshCw, Save, RotateCcw, Pencil, X,
  ShieldCheck, Banknote, ArrowUpFromLine, Coins, Scale, Clock, User, Tag,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import MarkdownLite from '@/components/MarkdownLite';

const SOP_ICON = {
  kyc_review: ShieldCheck,
  funding_verification: Banknote,
  withdrawal: ArrowUpFromLine,
  payout: Coins,
  secondary_dispute: Scale,
};

export default function AdminSOP() {
  const { toast } = useToast();
  const [list, setList] = useState([]);
  const [activeKey, setActiveKey] = useState(null);
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api.get('/admin/sop');
      const items = d?.items || [];
      setList(items);
      setActiveKey((prev) => prev || (items[0] && items[0].key) || null);
    } catch {
      toast.error('Не вдалось завантажити регламенти');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadDoc = useCallback(async (key) => {
    if (!key) return;
    try {
      const d = await api.get(`/admin/sop/${key}`);
      setDoc(d);
      setDraft(d?.body || '');
      setEditing(false);
    } catch {
      toast.error('Не вдалось завантажити документ');
    }
  }, [toast]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (activeKey) loadDoc(activeKey); }, [activeKey, loadDoc]);

  async function save() {
    if (!doc) return;
    setSaving(true);
    try {
      const updated = await api.put(`/admin/sop/${doc.key}`, { body: draft });
      setDoc(updated);
      setEditing(false);
      toast.success('Збережено');
      loadList();
    } catch {
      toast.error('Не вдалось зберегти');
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (!doc) return;
    if (!window.confirm('Повернути цей регламент до початкової редакції?')) return;
    try {
      const r = await api.post(`/admin/sop/${doc.key}/reset`, {});
      setDoc(r);
      setDraft(r?.body || '');
      setEditing(false);
      toast.success('Відновлено до базової редакції');
      loadList();
    } catch {
      toast.error('Не вдалось відновити');
    }
  }

  return (
    <div className="px-[50px] py-8 pb-20" data-testid="admin-sop">
      <div className="flex items-start justify-between gap-6 mb-6 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-token-kicker"><BookOpenCheck className="w-4 h-4" /> Operations SOP</div>
          <h1 className="text-h1 mb-1 mt-1">Регламенти (SOP)</h1>
          <p className="text-small-token max-w-2xl">
            Внутрішні операційні регламенти, за якими працює команда комплаєнс та фінансів.
            Керівник може редагувати текст регламенту.
          </p>
        </div>
        <button
          onClick={loadList}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition disabled:opacity-50"
          data-testid="sop-refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Оновити
        </button>
      </div>

      <div className="grid lg:grid-cols-12 gap-6 items-start">
        {/* List */}
        <aside className="lg:col-span-4 xl:col-span-3 space-y-2" data-testid="sop-list">
          {list.map((s) => {
            const Icon = SOP_ICON[s.key] || BookOpenCheck;
            const active = s.key === activeKey;
            return (
              <button
                key={s.key}
                onClick={() => setActiveKey(s.key)}
                data-testid={`sop-item-${s.key}`}
                className={`w-full text-left rounded-xl border p-4 transition ${
                  active ? 'border-[#2E5D4F]/50 bg-[#2E5D4F]/[0.06]' : 'border-app bg-app-surface hover:border-app-strong'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${active ? 'bg-[#2E5D4F] text-white' : 'bg-app-elevated text-token-secondary'}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-token-primary truncate">{s.title}</div>
                    <div className="text-[11px] text-token-muted">{s.category}</div>
                  </div>
                </div>
              </button>
            );
          })}
        </aside>

        {/* Document */}
        <section className="lg:col-span-8 xl:col-span-9 min-w-0">
          {!doc ? (
            <div className="rounded-2xl border border-app bg-app-surface p-10 text-center text-small-token">
              {loading ? 'Завантаження…' : 'Оберіть регламент'}
            </div>
          ) : (
            <div className="rounded-2xl border border-app bg-app-surface overflow-hidden">
              <header className="px-6 py-5 border-b border-app">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <h2 className="text-h3 text-token-primary">{doc.title}</h2>
                    <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-token-muted">
                      <span className="inline-flex items-center gap-1.5"><Tag className="w-3.5 h-3.5" /> {doc.category}</span>
                      <span className="inline-flex items-center gap-1.5"><User className="w-3.5 h-3.5" /> {doc.owner}</span>
                      <span className="inline-flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> SLA: {doc.sla}</span>
                      <span className="inline-flex items-center gap-1.5">версія {doc.version}{doc.auto_seeded === false ? ' · редаговано' : ''}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!editing ? (
                      <button
                        onClick={() => { setDraft(doc.body || ''); setEditing(true); }}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary hover:border-app-strong transition"
                        data-testid="sop-edit"
                      >
                        <Pencil className="w-4 h-4" /> Редагувати
                      </button>
                    ) : (
                      <>
                        <button
                          onClick={() => { setEditing(false); setDraft(doc.body || ''); }}
                          className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-app text-sm font-semibold text-token-secondary hover:text-token-primary transition"
                          data-testid="sop-cancel"
                        >
                          <X className="w-4 h-4" /> Скасувати
                        </button>
                        <button
                          onClick={save}
                          disabled={saving}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-semibold transition disabled:opacity-50"
                          data-testid="sop-save"
                        >
                          <Save className="w-4 h-4" /> {saving ? 'Зберігаємо…' : 'Зберегти'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </header>

              <div className="p-6 md:p-8">
                {editing ? (
                  <>
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      data-testid="sop-editor"
                      className="w-full px-4 py-3 rounded-xl bg-app-elevated border border-app text-sm text-token-primary leading-relaxed outline-none focus:border-app-strong transition resize-y font-mono"
                      style={{ minHeight: 480 }}
                    />
                    <div className="mt-3 flex items-center justify-between">
                      <button
                        onClick={reset}
                        className="inline-flex items-center gap-1.5 text-xs text-token-secondary hover:text-rose-400 transition"
                        data-testid="sop-reset"
                      >
                        <RotateCcw className="w-3.5 h-3.5" /> Повернути до базової редакції
                      </button>
                      <span className="text-[11px] text-token-muted">Markdown: # заголовки, **жирний**, - списки</span>
                    </div>
                  </>
                ) : (
                  <div className="text-token-primary" data-testid="sop-body">
                    <MarkdownLite text={doc.body} />
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
